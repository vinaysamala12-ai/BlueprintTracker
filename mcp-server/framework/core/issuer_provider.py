"""Pluggable issuer configuration provider abstraction.

The framework ships two concrete implementations — ``FileIssuerProvider``
(reads a local JSON file) and ``AppConfigIssuerProvider`` (reads Azure
App Configuration) — but product teams can supply any backing store by
subclassing ``IssuerProvider`` and registering it in ``run_server.py``.

Providers return *raw* issuer config dicts; the framework normalises and
deduplicates them via ``Config._normalize_issuer_rule`` before caching.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


class IssuerProvider(ABC):
    """Abstract base for issuer configuration sources.

    Subclass and override ``load_issuer_configs`` to fetch issuer mappings
    from a database, REST API, external service, or any other backing store.

    Configs must be raw dicts with at least ``issuer_url`` and
    ``issuer_environment`` keys.  Normalisation and deduplication are handled
    by the framework after the provider returns.
    """

    @abstractmethod
    def load_issuer_configs(self) -> List[Dict[str, Any]]:
        """Return a list of raw issuer config dicts."""
        ...


class FileIssuerProvider(IssuerProvider):
    """Load issuer configs from a local JSON file.

    If *path* is omitted the provider reads the path from the
    ``MCP_TOKEN_ISSUERS_FILE`` environment variable.
    Returns an empty list (no error) when neither the argument nor the env var
    points to a file, so the framework can start without issuer validation configured.

    Expected format::

        [
          {
            "issuer_url": "https://appcentral.aptean.com/iam/auth/realms/aptean",
            "issuer_environment": "AC-PRODUCTION",
            "jwks_url": "https://...",
            "algorithms": ["RS256"]
          }
        ]
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path

    def load_issuer_configs(self) -> List[Dict[str, Any]]:
        issuers_file = self._path or os.getenv("MCP_TOKEN_ISSUERS_FILE", "").strip()
        if not issuers_file:
            return []

        source = f"MCP_TOKEN_ISSUERS_FILE ({issuers_file})"
        try:
            raw = Path(issuers_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Failed to read {source}: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {source}: {exc}") from exc

        if not isinstance(parsed, list):
            raise ValueError(f"{source} must contain a JSON array of issuer mappings")

        return parsed


class AppConfigIssuerProvider(IssuerProvider):
    """Load issuer configs from Azure App Configuration.

    Keys must follow the path format::

        <key_prefix><issuer_environment>

    For example, with the default prefix ``issuers/``::

        issuers/AC-PRODUCTION

    The JSON *value* for each key is the issuer payload and must be a JSON
    object containing at least ``issuer_url``.  The ``issuer_environment`` is
    taken from the key path and overrides any value in the payload.

    If *endpoint* or *key_prefix* are omitted, they are read from
    ``MCP_TOKEN_APP_CONFIG_ENDPOINT`` and
    ``MCP_TOKEN_ISSUERS_APP_CONFIG_PREFIX`` respectively.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        key_prefix: Optional[str] = None,
    ) -> None:
        self._endpoint = endpoint
        self._key_prefix = key_prefix

    # ── Azure error helpers (standalone, no Config dependency) ────────────────

    @staticmethod
    def _is_auth_error(error: Exception) -> bool:
        return (
            error.__class__.__name__ == "ClientAuthenticationError"
            and str(getattr(error.__class__, "__module__", "")).startswith("azure.")
        )

    @staticmethod
    def _is_http_response_error(error: Exception) -> bool:
        return (
            error.__class__.__name__ == "HttpResponseError"
            and str(getattr(error.__class__, "__module__", "")).startswith("azure.")
        )

    @staticmethod
    def _is_network_error(error: Exception) -> bool:
        return (
            error.__class__.__name__ in {"ServiceRequestError", "ServiceResponseError"}
            and str(getattr(error.__class__, "__module__", "")).startswith("azure.")
        )

    @staticmethod
    def _http_status(error: Exception) -> Optional[int]:
        code = getattr(error, "status_code", None)
        if isinstance(code, int):
            return code
        resp = getattr(error, "response", None)
        resp_code = getattr(resp, "status_code", None)
        return resp_code if isinstance(resp_code, int) else None

    @staticmethod
    def _is_local() -> bool:
        host = os.getenv("SERVER_HOST", "localhost").strip().lower()
        return host in {"localhost", "127.0.0.1", "::1"}

    def _access_error_message(self, endpoint: str, key_filter: str, error: Exception) -> str:
        prefix = (
            "Azure App Configuration access failed while loading issuer mappings. "
            f"endpoint={endpoint!r}, key_filter={key_filter!r}. "
        )
        if self._is_auth_error(error):
            msg = str(error)
            if self._is_local() and "AzureCliCredential" in msg:
                return prefix + "Local auth was not available. Install Azure CLI and run az login."
            if "ManagedIdentityCredential" in msg or "IMDS" in msg:
                return (
                    prefix
                    + "Managed identity was not available. Enable managed identity on the host "
                    "and grant the App Configuration Data Reader role."
                )
            return (
                prefix
                + "DefaultAzureCredential could not acquire a token. Local: install Azure CLI "
                "and run az login. Production: enable managed identity and grant the App "
                "Configuration Data Reader role."
            )
        if self._is_http_response_error(error):
            code = self._http_status(error)
            if code == 403:
                return (
                    prefix
                    + "Access was denied. Grant the current identity the App Configuration Data "
                    "Reader role on the App Configuration resource."
                )
            if code == 401:
                return (
                    prefix
                    + "The identity was not accepted. Verify the expected identity has access "
                    "in the correct tenant."
                )
            return (
                prefix
                + f"App Configuration returned HTTP {code or '<unknown>'}. Verify the configured "
                "identity has access and the endpoint is correct."
            )
        if self._is_network_error(error):
            return (
                prefix
                + "Network access to App Configuration failed. Check the endpoint URL, DNS, "
                "firewall/private endpoint configuration, and VNet integration."
            )
        if isinstance(error, json.JSONDecodeError):
            return (
                prefix
                + "Received a non-JSON or empty response from App Configuration. Verify the "
                "endpoint URL, the current identity's access, and any proxy, firewall, or "
                "private endpoint configuration."
            )
        return prefix + str(error)

    # ── Public interface ──────────────────────────────────────────────────────

    def load_issuer_configs(self) -> List[Dict[str, Any]]:
        endpoint = (
            self._endpoint
            or os.getenv("MCP_TOKEN_APP_CONFIG_ENDPOINT", "").strip()
        )
        if not endpoint:
            return []

        raw_prefix = (
            self._key_prefix
            or os.getenv("MCP_TOKEN_ISSUERS_APP_CONFIG_PREFIX", "issuers/").strip()
            or "issuers/"
        )
        key_prefix = raw_prefix if raw_prefix.endswith("/") else f"{raw_prefix}/"
        key_filter = f"{key_prefix}*"

        try:
            from azure.appconfiguration import AzureAppConfigurationClient
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise ValueError(
                "Azure App Configuration dependencies are missing. "
                "Install 'azure-appconfiguration' and 'azure-identity'."
            ) from exc

        umi_client_id = os.getenv("MCP_TOKEN_APP_CONFIG_CLIENT_ID") or None
        credential = DefaultAzureCredential(managed_identity_client_id=umi_client_id)
        client = AzureAppConfigurationClient(base_url=endpoint, credential=credential)

        raw_configs: List[Dict[str, Any]] = []
        try:
            for setting in client.list_configuration_settings(key_filter=key_filter):
                if setting.value is None:
                    continue

                try:
                    value = json.loads(setting.value)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSON for App Configuration key '{setting.key}': {exc}"
                    ) from exc

                if not isinstance(value, dict):
                    raise ValueError(
                        f"App Configuration key '{setting.key}' must contain a JSON object"
                    )

                key_parts = str(setting.key).split("/")
                prefix_parts = [p for p in key_prefix.split("/") if p]
                if (
                    key_parts[: len(prefix_parts)] != prefix_parts
                    or len(key_parts) <= len(prefix_parts)
                ):
                    raise ValueError(
                        "App Configuration key format is invalid for issuer mappings. "
                        f"Expected '{key_prefix}{{issuer_environment}}', got '{setting.key}'."
                    )

                issuer_environment_from_key = key_parts[len(prefix_parts)].strip()
                if not issuer_environment_from_key:
                    raise ValueError(
                        f"App Configuration key '{setting.key}' must include issuer_environment "
                        "in the key path"
                    )

                # issuer_environment is authoritative from the key path
                value = dict(value)
                value["issuer_environment"] = issuer_environment_from_key
                raw_configs.append(value)

        except json.JSONDecodeError as exc:
            raise ValueError(self._access_error_message(endpoint, key_filter, exc)) from exc
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(self._access_error_message(endpoint, key_filter, exc)) from exc

        return raw_configs


# ── Module-level provider registry ───────────────────────────────────────────

_issuer_provider: Optional[IssuerProvider] = None


def set_issuer_provider(provider: IssuerProvider) -> None:
    """Register a custom issuer provider.

    Call this in ``run_server.py`` before starting the server::

        from framework import set_issuer_provider
        from my_domain.auth import DatabaseIssuerProvider

        set_issuer_provider(DatabaseIssuerProvider())

    When a provider is registered it takes precedence over the built-in
    ``MCP_TOKEN_CONFIG_SOURCE`` env-var selection.  Caching (TTL) and
    normalisation are still handled by the framework.  Registering a provider
    also enables Bearer JWT validation (``auth_bearer_required`` becomes True).
    """
    global _issuer_provider
    _issuer_provider = provider


def get_issuer_provider() -> Optional[IssuerProvider]:
    """Return the currently registered provider, or ``None`` when using default env-var selection."""
    return _issuer_provider
