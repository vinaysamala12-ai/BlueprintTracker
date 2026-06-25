"""Pluggable tenant-routing rule provider abstraction.

The framework ships two concrete implementations — ``FileTenantRoutingProvider``
(reads a local JSON file) and ``AppConfigTenantRoutingProvider`` (reads Azure
App Configuration) — but product teams can supply any backing store by subclassing
``TenantRoutingProvider`` and passing it via the ``provider=`` argument of
:func:`add_tenant_routing_provider`.

Use :func:`add_tenant_routing_provider` in ``src/custom/server.py`` to register
one or more named providers::

    from framework import add_tenant_routing_provider, RoutingKeySchema, issuer_info, token_claim, header

    add_tenant_routing_provider(
        "customer",
        schema=RoutingKeySchema(
            issuer_info("issuer_environment"),
            token_claim("coid"),
            header("x-aptean-database", default="*", wildcard_fallback=True),
        ),
        file="config/customer-resources.json",
        app_config_prefix="customer-routing",
    )

``MCP_TOKEN_CONFIG_SOURCE`` controls which backing store is used for all providers:

- ``file`` — loads from each provider's ``file=`` path.
- ``appconfig`` — loads from Azure App Configuration using each provider's
  ``app_config_prefix=`` key prefix.
- ``""`` (blank) — no rules loaded (development / no-auth mode).

Providers registered with an explicit ``provider=`` instance always use that
instance regardless of ``MCP_TOKEN_CONFIG_SOURCE``.

Providers return *raw* rule dicts; the framework normalises and deduplicates
them via ``Config._normalize_routing_rule`` before caching.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


class TenantRoutingProvider(ABC):
    """Abstract base for tenant routing rule sources.

    Subclass and override ``load_routing_rules`` to fetch rules from a
    database, REST API, external service, or any other backing store.

    Rules must be raw dicts with routing dimensions at the top level and
    domain-specific payload in a ``properties`` sub-dict.
    """

    @abstractmethod
    def load_routing_rules(self) -> List[Dict[str, Any]]:
        """Return a list of raw routing rule dicts."""
        ...


def _expand_file_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten ``{"key": {<dims>}, "properties": {<data>}}`` into a top-level dict."""
    if not isinstance(rule.get("key"), dict):
        raise ValueError(
            'Each routing rule must use {"key": {<dimensions>}, "properties": {<payload>}}. '
            f"Got keys: {sorted(rule.keys()) if isinstance(rule, dict) else rule!r}"
        )
    return {**rule["key"], "properties": rule.get("properties", {})}


class FileTenantRoutingProvider(TenantRoutingProvider):
    """Load routing rules from a local JSON file.

    Relative paths are resolved from the current working directory (project root).

    Each rule must use ``key`` for routing dimensions and ``properties`` for payload::

        [
          {
            "key": {
              "issuer_environment": "AC-PRODUCTION",
              "coid": "C0000000000000001",
              "database_name": "*"
            },
            "properties": {
              "label": "Customer A - Production",
              "api_base_url": "https://...",
              "database_connectionstring_secret_ref": "https://your-secret-store/secrets/..."
            }
          }
        ]
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def load_routing_rules(self) -> List[Dict[str, Any]]:
        source = f"file ({self._path})"
        try:
            raw = Path(self._path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Failed to read {source}: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {source}: {exc}") from exc

        if not isinstance(parsed, list):
            raise ValueError(f"{source} must contain a JSON array of routing rules")

        return [_expand_file_rule(rule) for rule in parsed]


class AppConfigTenantRoutingProvider(TenantRoutingProvider):
    """Load routing rules from Azure App Configuration.

    Key structure is driven by the :class:`~framework.core.routing_key.RoutingKeySchema`
    passed at construction.  The schema's ``app_config_prefix`` determines the key
    namespace.  For example, with prefix ``"customer-routing"`` and dimensions
    ``issuer_environment / coid / database_name``::

        customer-routing/AC-PRODUCTION/C0000000000000001/db-main

    The JSON *value* for each key is the domain payload and must be a JSON
    object.  Segment values are derived from the key path using the schema and
    do not need to be repeated in the value.

    If *endpoint* is omitted it is read from ``MCP_TOKEN_APP_CONFIG_ENDPOINT``.
    """

    def __init__(
        self,
        schema: Any,  # RoutingKeySchema
        endpoint: Optional[str] = None,
    ) -> None:
        self._schema = schema
        self._endpoint = endpoint

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
            "Azure App Configuration access failed while loading tenant routing rules. "
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

    def load_routing_rules(self) -> List[Dict[str, Any]]:
        endpoint = (
            self._endpoint
            or os.getenv("MCP_TOKEN_APP_CONFIG_ENDPOINT", "").strip()
        )
        if not endpoint:
            return []

        schema = self._schema
        key_filter = schema.build_key_filter()

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

        raw_rules: List[Dict[str, Any]] = []
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

                rule_fields = schema.parse_key_to_rule_fields(str(setting.key))
                if rule_fields is None:
                    raise ValueError(
                        f"App Configuration key '{setting.key}' does not match the routing key schema "
                        f"(expected {len(schema.segments)} segments separated by '{schema.separator}'). "
                        f"key_filter={key_filter!r}"
                    )

                raw_rules.append({**rule_fields, "properties": value})
        except json.JSONDecodeError as exc:
            raise ValueError(self._access_error_message(endpoint, key_filter, exc)) from exc
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(self._access_error_message(endpoint, key_filter, exc)) from exc

        return raw_rules


# ── Named provider registry ───────────────────────────────────────────────────


@dataclass
class _NamedProviderConfig:
    """Configuration for a single named tenant routing provider."""

    schema: Any  # RoutingKeySchema
    file: Optional[str]
    app_config_prefix: Optional[str]
    explicit_provider: Optional[TenantRoutingProvider]
    enforce_authorization: bool = False


_named_provider_configs: Dict[str, _NamedProviderConfig] = {}
_named_provider_registry_version: int = 0


def add_tenant_routing_provider(
    name: str,
    schema: Any,  # RoutingKeySchema
    *,
    file: Optional[str] = None,
    app_config_prefix: Optional[str] = None,
    provider: Optional[TenantRoutingProvider] = None,
    enforce_authorization: bool = False,
) -> None:
    """Register a named tenant routing provider.

    Call this at module level in ``src/custom/server.py``::

        from framework import add_tenant_routing_provider, RoutingKeySchema, issuer_info, token_claim, header

        add_tenant_routing_provider(
            "customer",
            schema=RoutingKeySchema(
                issuer_info("issuer_environment"),
                token_claim("coid"),
                header("x-aptean-database", default="*", wildcard_fallback=True),
            ),
            file="config/customer-resources.json",
            app_config_prefix="customer-routing",
            enforce_authorization=True,
        )

    ``MCP_TOKEN_CONFIG_SOURCE`` controls which backing store is used:

    - ``file`` — loads rules from the ``file=`` path (relative to project root).
    - ``appconfig`` — loads from Azure App Configuration using ``app_config_prefix=``
      (defaults to ``"tenant-routing"`` when omitted).
    - ``""`` (blank) — no rules loaded; properties always return ``None``.

    Providers with an explicit ``provider=`` instance always use that instance
    regardless of ``MCP_TOKEN_CONFIG_SOURCE``.

    When ``enforce_authorization=True``, any tool that calls ``get_tenant_routing_property()``
    or ``get_tenant_routing_secret()`` for this provider will raise ``PermissionError``
    (HTTP 403) if no routing rule matches the current request, rather than returning
    ``None`` / empty string silently.

    Tools read routing properties using the provider name::

        from framework import get_tenant_routing_property

        api_url = get_tenant_routing_property("api_base_url", provider="customer")
    """
    global _named_provider_registry_version
    _named_provider_configs[name] = _NamedProviderConfig(
        schema=schema,
        file=file,
        app_config_prefix=app_config_prefix,
        explicit_provider=provider,
        enforce_authorization=enforce_authorization,
    )
    _named_provider_registry_version += 1


def get_named_provider_configs() -> Dict[str, _NamedProviderConfig]:
    """Return a copy of all registered named provider configurations."""
    return dict(_named_provider_configs)


def get_named_provider_config(name: str) -> Optional[_NamedProviderConfig]:
    """Return the configuration for a single named provider, or ``None``."""
    return _named_provider_configs.get(name)


def _get_named_provider_registry_version() -> int:
    """Return the current registry version (incremented on each add or clear)."""
    return _named_provider_registry_version


def _clear_named_providers() -> None:
    """Remove all registered named providers.  Call this in test teardown."""
    global _named_provider_registry_version
    _named_provider_configs.clear()
    _named_provider_registry_version += 1
