"""Azure-specific secret resolution for tenant routing.

Register the Key Vault resolver in ``src/custom/server.py`` to enable
automatic resolution of Azure Key Vault URIs in ``get_tenant_routing_secret()``:

    from framework.contrib.azure import register_key_vault_resolver
    register_key_vault_resolver()

Once registered, any routing rule property value that is an Azure Key Vault
secret URI (``https://*.vault.azure.net/secrets/...``) will be resolved to
its plaintext value at request time. Non-URI values are passed through
unchanged.

The ``azure-keyvault-secrets`` and ``azure-identity`` packages must be
installed (they are included in ``requirements.txt``).
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from ..core.context import register_secret_resolver
from ..core.utils import ValidationError, get_app_logger


def _is_key_vault_secret_uri(value: str) -> bool:
    """Return True when the value is an Azure Key Vault secret URI."""
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not hostname:
        return False
    is_valid_kv_host = hostname == "vault.azure.net" or hostname.endswith(".vault.azure.net")
    path_parts = [p for p in parsed.path.split("/") if p]
    return is_valid_kv_host and len(path_parts) >= 2 and path_parts[0].lower() == "secrets"


def _resolve_kv_secret(secret_uri: str) -> str:
    """Fetch a secret value from Azure Key Vault. Raises ``ValidationError`` on failure."""
    logger = get_app_logger()
    parsed = urlparse(secret_uri)
    path_parts = [p for p in parsed.path.split("/") if p]
    secret_name = path_parts[1]
    secret_version = path_parts[2] if len(path_parts) >= 3 else None
    vault_url = f"{parsed.scheme}://{parsed.netloc}"

    logger.debug(
        "Resolving secret from Key Vault vault_url=%s secret_name=%s",
        vault_url,
        secret_name,
    )

    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except Exception as exc:
        raise ValidationError(
            "Azure Key Vault resolution requires 'azure-keyvault-secrets' and 'azure-identity' packages"
        ) from exc

    try:
        umi_client_id = os.getenv("MCP_TOKEN_APP_CONFIG_CLIENT_ID") or None
        credential = DefaultAzureCredential(managed_identity_client_id=umi_client_id)
        client = SecretClient(vault_url=vault_url, credential=credential)
        secret = client.get_secret(secret_name, secret_version)
    except Exception as exc:
        logger.error("Failed to fetch secret '%s' from Key Vault '%s': %s", secret_name, vault_url, exc)
        raise ValidationError(
            f"Failed to fetch secret '{secret_name}' from Key Vault '{vault_url}': {exc}"
        ) from exc

    secret_value = str(getattr(secret, "value", "") or "")
    if not secret_value:
        raise ValidationError(
            f"Key Vault secret '{secret_name}' in '{vault_url}' resolved to an empty value"
        )
    return secret_value


def _azure_kv_resolver(value: str):
    """Resolve an Azure Key Vault URI to its secret value, or return None if not a KV URI."""
    if not _is_key_vault_secret_uri(value):
        return None
    return _resolve_kv_secret(value)


def register_key_vault_resolver() -> None:
    """Opt in to Azure Key Vault secret resolution for ``get_tenant_routing_secret()``.

    Call once at startup in ``src/custom/server.py``. After registration, any
    routing rule property whose value is an Azure Key Vault secret URI is
    automatically resolved to its plaintext value at request time.
    """
    register_secret_resolver(_azure_kv_resolver)
