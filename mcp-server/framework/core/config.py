"""Configuration management for the MCP server."""

import logging
import os
import time
from functools import cached_property
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)


def _parse_log_levels(raw: str) -> Tuple[Dict[str, int], List[str]]:
    """Parse a ``LOG_LEVELS`` string into (overrides, error descriptions).

    Format: ``name=LEVEL,name2=LEVEL2`` (whitespace tolerant, case-insensitive
    levels). Returns the valid overrides plus a list of human-readable
    descriptions for malformed entries — callers decide whether/how to warn so
    messages can be routed through the project's configured logger.
    """
    raw = raw.strip()
    if not raw:
        return {}, []
    overrides: Dict[str, int] = {}
    errors: List[str] = []
    for entry in raw.split(","):
        if not entry.strip():
            continue
        if "=" not in entry:
            errors.append(f"{entry!r} (expected name=LEVEL)")
            continue
        name, level = entry.split("=", 1)
        name = name.strip()
        numeric = getattr(logging, level.strip().upper(), None)
        if not name or not isinstance(numeric, int):
            errors.append(f"{entry!r} (unknown level or empty name)")
            continue
        overrides[name] = numeric
    return overrides, errors


def _parse_int_env(var_name: str, default: int) -> int:
    """Parse a positive-int env var, warning (and falling back) on bad input."""
    raw = os.getenv(var_name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        _logger.warning(
            "Invalid %s=%r (expected int); falling back to %d", var_name, raw, default
        )
        return default
    if value <= 0:
        _logger.warning(
            "Invalid %s=%d (must be positive); falling back to %d",
            var_name,
            value,
            default,
        )
        return default
    return value


def _parse_float_env(var_name: str, default: float) -> float:
    """Parse a positive-float env var, warning (and falling back) on bad input."""
    raw = os.getenv(var_name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        _logger.warning(
            "Invalid %s=%r (expected float); falling back to %s",
            var_name,
            raw,
            default,
        )
        return default
    if value <= 0:
        _logger.warning(
            "Invalid %s=%s (must be positive); falling back to %s",
            var_name,
            value,
            default,
        )
        return default
    return value


class _ProviderRuleCache:
    """Per-named-provider routing rule cache entry."""

    __slots__ = ("rules", "expires_at", "source_signature")

    def __init__(self) -> None:
        self.rules: Optional[List[Dict[str, Any]]] = None
        self.expires_at: float = 0.0
        self.source_signature: str = ""


class Config:
    """
    Configuration class that provides type-safe access to configuration values.
    Eliminates the need for hardcoded configuration key strings throughout the codebase.
    """
    
    def __init__(self):
        """Initialize configuration with validation."""
        self._validate_environment()
        self._issuer_configs_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._issuer_configs_cache_expires_at: float = 0.0
        self._issuer_configs_cache_source_signature: str = ""
        self._provider_rule_caches: Dict[str, _ProviderRuleCache] = {}
    
    def _validate_environment(self) -> None:
        """Validate environment variables on initialization."""
        port_value = os.getenv("SERVER_PORT")
        if port_value:
            try:
                port = int(port_value)
                if not 1 <= port <= 65535:
                    raise ValueError("server port must be between 1 and 65535")
            except ValueError as e:
                raise ValueError(f"Invalid server port '{port_value}': {e}")
    
    @staticmethod
    def _debug(message: str, *args: Any) -> None:
        """Emit debug logs when the application logger is configured."""
        from .utils import get_app_logger  # lazy to break utils↔config circular import
        logger = get_app_logger()
        if logger and logger.isEnabledFor(10):  # logging.DEBUG
            logger.debug(message, *args)

    @staticmethod
    def _get_bool_env(var_name: str, default: bool) -> bool:
        """Parse boolean environment variables with safe defaults."""
        raw_value = os.getenv(var_name)
        if raw_value is None:
            return default

        # Tolerate inline comments from .env values, e.g. "true # explanation".
        value = raw_value.split("#", 1)[0].strip().lower()
        if value in {"1", "true", "yes", "y", "on"}:
            return True
        if value in {"0", "false", "no", "n", "off"}:
            return False

        raise ValueError(
            f"Invalid boolean for {var_name}: '{raw_value}'. "
            "Use one of: true/false, 1/0, yes/no, on/off"
        )

    @staticmethod
    def _normalize_routing_rule(rule: Dict[str, Any], index: int, schema: Any) -> Dict[str, Any]:
        """Validate and normalize one tenant routing rule using the given schema."""
        from .routing_key import literal as literal_seg, issuer_info as issuer_info_seg

        if not isinstance(rule, dict):
            raise ValueError(f"Routing rule at index {index} must be an object")

        normalized: Dict[str, Any] = {}

        for seg in schema.segments:
            if isinstance(seg, literal_seg):
                continue
            fn = seg.field_name
            if not fn:
                continue

            raw = rule.get(fn)
            val = str(raw).strip() if raw is not None else ""

            # issuer_environment is always stored uppercase for consistent matching
            if isinstance(seg, issuer_info_seg) or fn == "issuer_environment":
                val = val.upper()

            if not val:
                if seg.wildcard_fallback:
                    val = "*"
                else:
                    raise ValueError(
                        f"Routing rule at index {index} is missing required '{fn}'"
                    )

            normalized[fn] = val

        label = str(rule.get("label", "")).strip()

        # Domain-specific payload: prefer an explicit 'properties' key; otherwise collect
        # all non-framework fields so flat legacy rules continue to work unchanged.
        schema_field_names = {
            seg.field_name
            for seg in schema.segments
            if not isinstance(seg, literal_seg) and seg.field_name
        }
        _framework_keys = schema_field_names | {"label"}

        if "properties" in rule:
            properties: Dict[str, Any] = dict(rule["properties"]) if isinstance(rule.get("properties"), dict) else {}
        else:
            properties = {k: v for k, v in rule.items() if k not in _framework_keys}

        result: Dict[str, Any] = {**normalized, "properties": properties}
        if label:
            result["label"] = label

        return result

    @staticmethod
    def _normalize_issuer_rule(rule: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Validate and normalize one issuer mapping rule."""
        if not isinstance(rule, dict):
            raise ValueError(f"Issuer mapping at index {index} must be an object")

        issuer_url = str(rule.get("issuer_url", "")).strip()
        issuer_environment = str(rule.get("issuer_environment", "")).strip().upper()
        jwks_url = str(rule.get("jwks_url", "")).strip()
        audience_value = rule.get("audience")
        audience = str(audience_value).strip() if audience_value is not None else ""

        algorithms_value = rule.get("algorithms")
        if algorithms_value is None:
            algorithms: List[str] = ["RS256"]
        elif isinstance(algorithms_value, list):
            algorithms = [str(item).strip() for item in algorithms_value if str(item).strip()]
        elif isinstance(algorithms_value, str):
            algorithms = [item.strip() for item in algorithms_value.split(",") if item.strip()]
        else:
            raise ValueError(f"Issuer mapping at index {index} has invalid 'algorithms' value")

        if not issuer_url:
            raise ValueError(
                f"Issuer mapping at index {index} is missing required 'issuer_url'"
            )
        if not issuer_environment:
            raise ValueError(
                f"Issuer mapping at index {index} is missing required 'issuer_environment'"
            )

        if not algorithms:
            raise ValueError(f"Issuer mapping at index {index} must include at least one algorithm")

        normalized: Dict[str, Any] = {
            "issuer_url": issuer_url,
            "issuer_environment": issuer_environment,
            "algorithms": algorithms,
        }
        if jwks_url:
            normalized["jwks_url"] = jwks_url
        if audience:
            normalized["audience"] = audience

        return normalized

    def _load_issuer_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load and cache issuer JWT configuration via the registered provider.

        When a provider has been registered with ``set_issuer_provider`` it is
        used unconditionally.  Otherwise the framework auto-selects a built-in
        provider based on the ``MCP_TOKEN_CONFIG_SOURCE`` env var
        (``file`` → ``FileIssuerProvider``,
        ``appconfig`` → ``AppConfigIssuerProvider``).

        Normalisation and deduplication always happen here regardless of the
        provider, so providers only need to return raw config dicts.
        """
        from .issuer_provider import (
            get_issuer_provider,
            FileIssuerProvider,
            AppConfigIssuerProvider,
        )

        source = self.issuer_source
        source_signature = self._get_issuer_source_signature()
        now = time.time()
        ttl = self.issuer_cache_ttl_seconds

        self._debug(
            "Loading issuer configs: source=%s ttl=%ss",
            source,
            ttl,
        )

        if (
            self._issuer_configs_cache is not None
            and now < self._issuer_configs_cache_expires_at
            and source_signature == self._issuer_configs_cache_source_signature
        ):
            self._debug(
                "Issuer config cache hit: count=%s expires_at=%.3f",
                len(self._issuer_configs_cache),
                self._issuer_configs_cache_expires_at,
            )
            return self._issuer_configs_cache

        self._debug(
            "Issuer config cache miss/refresh: had_cache=%s source_signature_changed=%s",
            self._issuer_configs_cache is not None,
            source_signature != self._issuer_configs_cache_source_signature,
        )

        # Resolve which provider to use: registered custom provider takes precedence;
        # fall back to auto-selection based on MCP_TOKEN_CONFIG_SOURCE.
        provider = get_issuer_provider()
        if provider is None:
            if source == "":
                raw_list: List[Dict[str, Any]] = []
            elif source == "file":
                provider = FileIssuerProvider()
            elif source == "appconfig":
                provider = AppConfigIssuerProvider(
                    endpoint=self.issuer_app_config_endpoint,
                    key_prefix=self.issuer_app_config_key_prefix,
                )
            elif source == "custom":
                raise ValueError(
                    "MCP_TOKEN_CONFIG_SOURCE=custom requires a custom IssuerProvider "
                    "registered via set_issuer_provider() in run_server.py before the server starts."
                )
            else:
                raise ValueError(
                    f"Unsupported MCP_TOKEN_CONFIG_SOURCE '{source}'. "
                    "Supported values: blank, file, appconfig, custom."
                )

        if provider is not None:
            raw_list = provider.load_issuer_configs()

        mappings: Dict[str, Dict[str, Any]] = {}
        for idx, rule in enumerate(raw_list):
            normalized = self._normalize_issuer_rule(rule, idx)
            issuer_url = normalized["issuer_url"]
            if issuer_url in mappings:
                raise ValueError(
                    f"Duplicate issuer mapping detected for issuer_url: {issuer_url}"
                )
            mappings[issuer_url] = normalized

        self._issuer_configs_cache = mappings
        self._issuer_configs_cache_expires_at = now + ttl if ttl > 0 else 0.0
        self._issuer_configs_cache_source_signature = source_signature

        self._debug(
            "Issuer configs loaded: count=%s cache_expires_at=%.3f",
            len(mappings),
            self._issuer_configs_cache_expires_at,
        )

        return mappings

    def _load_named_provider_rules(self, provider_name: str) -> List[Dict[str, Any]]:
        """Load, normalise, and cache routing rules for a named provider."""
        from .tenant_routing_provider import (
            get_named_provider_config,
            _get_named_provider_registry_version,
            FileTenantRoutingProvider,
            AppConfigTenantRoutingProvider,
        )
        from .routing_key import RoutingKeySchema as _RoutingKeySchema, literal as literal_seg

        provider_config = get_named_provider_config(provider_name)
        if provider_config is None:
            raise ValueError(
                f"Tenant routing provider '{provider_name}' is not registered. "
                "Register it with add_tenant_routing_provider() in src/custom/server.py."
            )

        schema = provider_config.schema
        source = self.tenant_routing_source
        ttl = self.tenant_routing_cache_ttl_seconds
        reg_version = _get_named_provider_registry_version()
        cache_signature = (
            f"{source}|{self.tenant_routing_app_config_endpoint}"
            f"|{ttl}|v{reg_version}"
        )
        now = time.time()

        cache = self._provider_rule_caches.get(provider_name)
        if (
            cache is not None
            and cache.rules is not None
            and now < cache.expires_at
            and cache.source_signature == cache_signature
        ):
            self._debug(
                "Provider '%s' rule cache hit: count=%s expires_at=%.3f",
                provider_name,
                len(cache.rules),
                cache.expires_at,
            )
            return cache.rules

        self._debug(
            "Provider '%s' rule cache miss/refresh: source=%s",
            provider_name,
            source,
        )

        if provider_config.explicit_provider is not None:
            raw_rules = provider_config.explicit_provider.load_routing_rules()
        elif source == "":
            raw_rules = []
        elif source == "file":
            if provider_config.file:
                raw_rules = FileTenantRoutingProvider(path=provider_config.file).load_routing_rules()
            else:
                self._debug(
                    "Provider '%s': no file= configured for file mode; returning empty rules",
                    provider_name,
                )
                raw_rules = []
        elif source == "appconfig":
            effective_prefix = provider_config.app_config_prefix or schema.app_config_prefix or "tenant-routing"
            provider_schema = _RoutingKeySchema(
                *schema.segments,
                separator=schema.separator,
                app_config_prefix=effective_prefix,
            )
            raw_rules = AppConfigTenantRoutingProvider(
                schema=provider_schema,
                endpoint=self.tenant_routing_app_config_endpoint,
            ).load_routing_rules()
        elif source == "custom":
            raise ValueError(
                f"MCP_TOKEN_CONFIG_SOURCE=custom requires a provider= instance "
                f"registered via add_tenant_routing_provider('{provider_name}', ..., provider=...) "
                "in src/custom/server.py."
            )
        else:
            raise ValueError(
                f"Unsupported MCP_TOKEN_CONFIG_SOURCE '{source}'. "
                "Supported values: blank, file, appconfig, custom."
            )

        dedupe_fields = [
            seg.field_name
            for seg in schema.segments
            if not isinstance(seg, literal_seg) and seg.field_name
        ]

        normalized_rules: List[Dict[str, Any]] = []
        seen_keys: set = set()
        for idx, rule in enumerate(raw_rules):
            normalized = self._normalize_routing_rule(rule, idx, schema)
            dedupe_key = tuple(
                str(normalized.get(f, "")).casefold() for f in dedupe_fields
            )
            if dedupe_key in seen_keys:
                raise ValueError(
                    f"Duplicate routing rule in provider '{provider_name}': "
                    f"{dict(zip(dedupe_fields, dedupe_key))}"
                )
            seen_keys.add(dedupe_key)
            normalized_rules.append(normalized)

        new_cache = _ProviderRuleCache()
        new_cache.rules = normalized_rules
        new_cache.expires_at = now + ttl if ttl > 0 else 0.0
        new_cache.source_signature = cache_signature
        self._provider_rule_caches[provider_name] = new_cache

        self._debug(
            "Provider '%s' rules loaded: count=%s cache_expires_at=%.3f",
            provider_name,
            len(normalized_rules),
            new_cache.expires_at,
        )

        return normalized_rules

    def _get_issuer_source_signature(self) -> str:
        """Return a cache signature that changes when issuer source-related env vars change.

        Custom provider identity (registered via ``set_issuer_provider``) is intentionally
        not included. Providers are expected to be registered once at startup and never
        swapped at runtime; swapping a provider within the TTL window will serve stale
        mappings until the cache expires. If you need immediate effect, restart the server
        or reduce ``MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS``.
        """
        return "|".join(
            [
                self.issuer_source,
                os.getenv("MCP_TOKEN_ISSUERS_FILE", "").strip(),
                self.issuer_app_config_endpoint,
                self.issuer_app_config_key_prefix,
                str(self.issuer_cache_ttl_seconds),
            ]
        )

    @property
    def log_level(self) -> str:
        """Get the logging level."""
        return os.getenv("LOG_LEVEL", "INFO").upper()
    
    @property
    def log_file(self) -> Optional[str]:
        """Get the log file path."""
        return os.getenv("LOG_FILE")

    @cached_property
    def _log_levels_parsed(self) -> Tuple[Dict[str, int], List[str]]:
        """Parsed ``LOG_LEVELS`` as ``(overrides, error_descriptions)``.

        Cached so the env var is parsed exactly once per process — both for
        ``to_dict`` (config dump) and for ``setup_logging`` (level application
        + warning emission). The latter routes errors through the project
        logger so messages get the standard formatter and correlation field.
        """
        return _parse_log_levels(os.getenv("LOG_LEVELS", ""))

    @property
    def log_levels(self) -> Dict[str, int]:
        """Per-logger level overrides parsed from ``LOG_LEVELS``.

        Format: ``name=LEVEL,name2=LEVEL2`` (whitespace tolerant, case-
        insensitive). Malformed entries are dropped silently here; warnings
        are emitted by ``setup_logging`` so they go through the configured
        handler.
        """
        return self._log_levels_parsed[0]

    @property
    def log_levels_errors(self) -> List[str]:
        """Human-readable descriptions of malformed ``LOG_LEVELS`` entries."""
        return self._log_levels_parsed[1]
    
    @property
    def server_host(self) -> str:
        """Get the server host."""
        return os.getenv("SERVER_HOST", "localhost")
    
    @property
    def server_port(self) -> int:
        """Get the server port with validation."""
        try:
            return int(os.getenv("SERVER_PORT", "8000"))
        except ValueError:
            return 8000  # Fallback to default
    
    @property
    def mcp_master_api_key(self) -> Optional[str]:
        """Get the MCP master API key."""
        return os.getenv("MCP_MASTER_API_KEY")
    
    @property
    def mcp_master_api_key_name(self) -> str:
        """Get the MCP master API key header name."""
        return os.getenv("MCP_MASTER_API_KEY_NAME", "x-api-key")
    
    @property
    def correlation_id_name(self) -> str:
        """Get the correlation ID header name."""
        return os.getenv("CORRELATION_ID_NAME", "x-correlation-id")
    
    @property
    def mcp_configurations_file(self) -> str:
        """Get the path to the MCP configurations JSON file."""
        return os.getenv("MCP_CONFIGURATIONS_FILE", "mcp-configurations.json")

    @property
    def mcp_base_path(self) -> str:
        """Get the MCP server base path, normalized without leading/trailing slashes."""
        path = os.getenv("MCP_BASE_PATH", "").strip()
        return path.strip("/") if path else ""

    @property
    def mcp_path_prefix(self) -> str:
        """Base path as a URL prefix — leading slash and no trailing slash, or "" when unset."""
        base = self.mcp_base_path
        return f"/{base}" if base else ""

    # ── Reliability knobs ────────────────────────────────────────────────────

    @property
    def tool_timeout_seconds(self) -> Optional[float]:
        """Default wall-clock timeout for a single tool call, in seconds.

        Tools that declare their own timeout via ``@register_tool(timeout_seconds=...)``
        override this. ``None`` (the default) leaves FastMCP's built-in behaviour in place.
        """
        raw = os.getenv("TOOL_TIMEOUT_SECONDS")
        if raw is None or not raw.strip():
            return None
        try:
            value = float(raw)
        except ValueError:
            _logger.warning(
                "Invalid TOOL_TIMEOUT_SECONDS=%r (expected float); ignoring (no timeout)",
                raw,
            )
            return None
        if value <= 0:
            _logger.warning(
                "Invalid TOOL_TIMEOUT_SECONDS=%s (must be positive); ignoring (no timeout)",
                value,
            )
            return None
        return value

    @property
    def response_max_bytes(self) -> int:
        """Maximum tool-response size after which truncation kicks in."""
        return _parse_int_env("RESPONSE_MAX_BYTES", 1000000)

    @property
    def http_client_timeout_seconds(self) -> float:
        """Default per-request timeout on the shared outbound HTTP client."""
        return _parse_float_env("HTTP_CLIENT_TIMEOUT_SECONDS", 30.0)

    @property
    def http_client_max_connections(self) -> int:
        """Connection pool ceiling for the shared outbound HTTP client."""
        return _parse_int_env("HTTP_CLIENT_MAX_CONNECTIONS", 100)

    @property
    def http_client_max_keepalive(self) -> int:
        """Keepalive connection ceiling for the shared outbound HTTP client."""
        return _parse_int_env("HTTP_CLIENT_MAX_KEEPALIVE", 20)

    def _issuer_validation_active(self) -> bool:
        """Return True when an issuer provider is configured (custom or env-var selected)."""
        from .issuer_provider import get_issuer_provider
        return get_issuer_provider() is not None or self.issuer_source in {"file", "appconfig", "custom"}

    @property
    def auth_bearer_required(self) -> bool:
        """Whether a Bearer JWT is required on every request.

        Defaults to True when issuer validation is active.
        Override with MCP_TOKEN_REQUIRE_JWT=true/false.
        """
        return self._get_bool_env("MCP_TOKEN_REQUIRE_JWT", self._issuer_validation_active())

    @property
    def auth_bearer_verify_signature(self) -> bool:
        """Whether JWT cryptographic signature is verified against the issuer's JWKS.

        Defaults to True when issuer validation is active.
        Override with MCP_TOKEN_VERIFY_SIGNATURE=true/false.
        Only meaningful when an IssuerProvider is configured (JWKS URLs come from issuer config).
        """
        return self._get_bool_env("MCP_TOKEN_VERIFY_SIGNATURE", self._issuer_validation_active())

    @property
    def auth_bearer_verify_issuer(self) -> bool:
        """Whether the token's iss claim must match a configured issuer.

        This is the same concept as issuer validation being active — it cannot be
        disabled independently without disabling the issuer provider.
        """
        return self._issuer_validation_active()

    @property
    def auth_bearer_verify_expiry(self) -> bool:
        """Whether the token's exp claim is verified.

        Defaults to True when issuer validation is active.
        Override with MCP_TOKEN_VERIFY_EXPIRY=true/false.
        """
        return self._get_bool_env("MCP_TOKEN_VERIFY_EXPIRY", self._issuer_validation_active())

    @property
    def jwks_user_agent(self) -> str:
        """Get User-Agent used by JWKS HTTP requests."""
        default_agent = "Mozilla/5.0 (compatible; Next-AI-MCP-JWKS-Client/1.0)"
        value = os.getenv("MCP_TOKEN_ISSUERS_JWKS_USER_AGENT", "").strip()
        return value or default_agent

    # ── Issuer configuration ─────────────────────────────────────────────────

    @property
    def issuer_source(self) -> str:
        """Get source for issuer validation (MCP_TOKEN_CONFIG_SOURCE)."""
        return os.getenv("MCP_TOKEN_CONFIG_SOURCE", "").strip().lower()

    @property
    def issuer_cache_ttl_seconds(self) -> int:
        """Get cache TTL for issuer configs in seconds (MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS)."""
        raw_value = os.getenv("MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS", "")

        if raw_value:
            try:
                ttl = int(raw_value)
            except ValueError as e:
                raise ValueError(
                    f"Invalid MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS '{raw_value}': {e}"
                )
            if ttl < 0:
                raise ValueError("MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS must be >= 0")
            return ttl

        return 120 if self.issuer_source == "appconfig" else 0

    @property
    def issuer_app_config_endpoint(self) -> str:
        """Get Azure App Configuration endpoint (MCP_TOKEN_APP_CONFIG_ENDPOINT)."""
        return os.getenv("MCP_TOKEN_APP_CONFIG_ENDPOINT", "").strip()

    @property
    def issuer_app_config_key_prefix(self) -> str:
        """Get key prefix for issuer settings in App Configuration (MCP_TOKEN_ISSUERS_APP_CONFIG_PREFIX)."""
        prefix = os.getenv("MCP_TOKEN_ISSUERS_APP_CONFIG_PREFIX", "issuers/").strip()
        if not prefix:
            prefix = "issuers/"
        if not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return prefix

    @property
    def issuer_app_config_label(self) -> str:
        """Removed setting retained internally as an empty label filter."""
        return ""

    # ── Tenant routing configuration ─────────────────────────────────────────

    @property
    def tenant_routing_source(self) -> str:
        """Get source for tenant routing rules (MCP_TOKEN_CONFIG_SOURCE)."""
        return os.getenv("MCP_TOKEN_CONFIG_SOURCE", "").strip().lower()

    @property
    def tenant_routing_cache_ttl_seconds(self) -> int:
        """Get cache TTL for tenant routing rules in seconds (MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS)."""
        raw_value = os.getenv("MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS", "")

        if raw_value:
            try:
                ttl = int(raw_value)
            except ValueError as e:
                raise ValueError(
                    f"Invalid MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS '{raw_value}': {e}"
                )
            if ttl < 0:
                raise ValueError("MCP_TOKEN_CONFIG_CACHE_TTL_SECONDS must be >= 0")
            return ttl

        return 120 if self.tenant_routing_source == "appconfig" else 0

    @property
    def tenant_routing_app_config_endpoint(self) -> str:
        """Get Azure App Configuration endpoint (MCP_TOKEN_APP_CONFIG_ENDPOINT)."""
        return os.getenv("MCP_TOKEN_APP_CONFIG_ENDPOINT", "").strip()

    @property
    def tenant_routing_app_config_label(self) -> str:
        """Removed setting retained internally as an empty label filter."""
        return ""

    @property
    def issuer_environments(self) -> Dict[str, str]:
        """Get issuer_url-to-issuer_environment mappings used for authorization and routing."""
        return {
            issuer_url: str(config.get("issuer_environment", "")).strip()
            for issuer_url, config in self.issuer_configs.items()
            if str(config.get("issuer_environment", "")).strip()
        }

    @property
    def issuer_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get full issuer configuration keyed by issuer URL."""
        return self._load_issuer_configs()

    def get_issuer_config(self, issuer: str) -> Optional[Dict[str, Any]]:
        """Resolve full configuration for an issuer."""
        key = str(issuer).strip()
        if not key:
            return None
        return self.issuer_configs.get(key)

    def get_environment_for_issuer(self, issuer_url: str) -> Optional[str]:
        """Resolve configured issuer_environment value for an issuer URL."""
        key = str(issuer_url).strip()
        if not key:
            return None
        return self.issuer_environments.get(key)

    def find_resource_route(
        self,
        context: Dict[str, Any],
        provider: str,
    ) -> Optional[Dict[str, Any]]:
        """Resolve the best matching tenant route for the given provider and context.

        Uses the provider's :class:`~framework.core.routing_key.RoutingKeySchema`
        to extract match values from *context*, then searches the loaded routing
        rules in two passes:

        1. Exact match — all non-literal segment values match exactly.
        2. Wildcard fallback — segments with ``wildcard_fallback=True`` accept
           rules where the field equals ``"*"``.
        """
        from .tenant_routing_provider import get_named_provider_config
        from .routing_key import literal as literal_seg

        provider_config = get_named_provider_config(provider)
        if provider_config is None:
            raise ValueError(
                f"Tenant routing provider '{provider}' is not registered. "
                "Register it with add_tenant_routing_provider() in src/custom/server.py."
            )

        schema = provider_config.schema

        # Resolve match values from context via schema segments
        required_match: Dict[str, str] = {}   # must match exactly
        wildcard_match: Dict[str, str] = {}   # exact first, then rule's "*"

        for seg in schema.segments:
            if isinstance(seg, literal_seg):
                continue
            fn = seg.field_name
            if not fn:
                continue

            val = seg.resolve(context)
            if not val:
                if seg.wildcard_fallback:
                    val = getattr(seg, "default", None) or "*"
                else:
                    self._debug(
                        "tenant route lookup (provider=%s): required segment '%s' unresolvable; skipping",
                        provider, fn,
                    )
                    return None

            if seg.wildcard_fallback:
                wildcard_match[fn] = val
            else:
                required_match[fn] = val

        if not required_match and not wildcard_match:
            return None

        rules = self._load_named_provider_rules(provider)
        if not rules:
            self._debug("tenant route lookup (provider=%s): no routing rules loaded", provider)
            return None

        self._debug(
            "tenant route lookup (provider=%s): required=%s wildcard=%s rules=%d",
            provider, required_match, wildcard_match, len(rules),
        )

        # Pass 1: exact match on all segment fields
        for rule in rules:
            if (
                all(str(rule.get(k, "")).casefold() == v.casefold() for k, v in required_match.items())
                and all(str(rule.get(k, "")).casefold() == v.casefold() for k, v in wildcard_match.items())
            ):
                self._debug(
                    "Tenant route exact match (provider=%s): label=%s properties_keys=%s",
                    provider,
                    str(rule.get("properties", {}).get("label", "")) or "<none>",
                    list(rule.get("properties", {}).keys()),
                )
                return rule

        # Pass 2: wildcard fallback — rule's wildcard fields must equal "*"
        if wildcard_match:
            for rule in rules:
                if (
                    all(str(rule.get(k, "")).casefold() == v.casefold() for k, v in required_match.items())
                    and all(str(rule.get(k, "")).casefold() == "*" for k in wildcard_match)
                ):
                    self._debug(
                        "Tenant route wildcard match (provider=%s): label=%s properties_keys=%s",
                        provider,
                        str(rule.get("properties", {}).get("label", "")) or "<none>",
                        list(rule.get("properties", {}).keys()),
                    )
                    return rule

        self._debug("Tenant route: no match found (provider=%s)", provider)
        return None


    def to_dict(self, *, include_dynamic_config: bool = True) -> Dict[str, Any]:
        """
        Convert configuration to dictionary format for backward compatibility.
        
        Returns:
            Dictionary with configuration values
        """
        config = {
            "log_level": self.log_level,
            "log_file": self.log_file,
            "log_levels": self.log_levels,
            "server_host": self.server_host,
            "server_port": self.server_port,
            "mcp_master_api_key": self.mcp_master_api_key,
            "mcp_master_api_key_name": self.mcp_master_api_key_name,
            "correlation_id_name": self.correlation_id_name,
            "mcp_base_path": self.mcp_base_path,
            "mcp_configurations_file": self.mcp_configurations_file,
            "tool_timeout_seconds": self.tool_timeout_seconds,
            "response_max_bytes": self.response_max_bytes,
            "http_client_timeout_seconds": self.http_client_timeout_seconds,
            "http_client_max_connections": self.http_client_max_connections,
            "http_client_max_keepalive": self.http_client_max_keepalive,
            "auth_bearer_required": self.auth_bearer_required,
            "auth_bearer_verify_signature": self.auth_bearer_verify_signature,
            "auth_bearer_verify_issuer": self.auth_bearer_verify_issuer,
            "auth_bearer_verify_expiry": self.auth_bearer_verify_expiry,
            "jwks_user_agent": self.jwks_user_agent,
            "issuer_source": self.issuer_source,
            "issuer_cache_ttl_seconds": self.issuer_cache_ttl_seconds,
            "issuer_app_config_endpoint": self.issuer_app_config_endpoint,
            "issuer_app_config_key_prefix": self.issuer_app_config_key_prefix,
            "issuer_app_config_label": self.issuer_app_config_label,
            "tenant_routing_source": self.tenant_routing_source,
            "tenant_routing_cache_ttl_seconds": self.tenant_routing_cache_ttl_seconds,
            "tenant_routing_app_config_endpoint": self.tenant_routing_app_config_endpoint,
            "tenant_routing_app_config_label": self.tenant_routing_app_config_label,
        }

        if include_dynamic_config:
            config.update(
                {
                    "issuer_configs": self.issuer_configs,
                    "issuer_environments": self.issuer_environments,
                }
            )

        return config


# Global configuration instance - initialized once
try:
    app_config = Config()
except ValueError as e:
    # Log error and create with defaults if validation fails
    import sys
    print(f"Configuration error: {e}", file=sys.stderr)
    # Create a temporary config that will use defaults
    app_config = object.__new__(Config)


# Legacy function for backward compatibility only
def get_configuration() -> Dict[str, Any]:
    """
    Get configuration dictionary.
    
    Returns:
        Dictionary with configuration values
        
    Note: Deprecated - use app_config directly for new code.
    """
    return app_config.to_dict()


# The following getter functions are deprecated in favor of using app_config directly
# They are kept only for backward compatibility
get_log_level = lambda: app_config.log_level
get_log_file = lambda: app_config.log_file
get_server_host = lambda: app_config.server_host
get_server_port = lambda: app_config.server_port
get_mcp_master_api_key = lambda: app_config.mcp_master_api_key
get_mcp_master_api_key_name = lambda: app_config.mcp_master_api_key_name
get_correlation_id_name = lambda: app_config.correlation_id_name
get_mcp_base_path = lambda: app_config.mcp_base_path
get_auth_bearer_required = lambda: app_config.auth_bearer_required
get_auth_bearer_verify_signature = lambda: app_config.auth_bearer_verify_signature
get_auth_bearer_verify_issuer = lambda: app_config.auth_bearer_verify_issuer
get_auth_bearer_verify_expiry = lambda: app_config.auth_bearer_verify_expiry
get_jwks_user_agent = lambda: app_config.jwks_user_agent
get_issuer_source = lambda: app_config.issuer_source
get_issuer_cache_ttl_seconds = lambda: app_config.issuer_cache_ttl_seconds
get_issuer_app_config_endpoint = lambda: app_config.issuer_app_config_endpoint
get_tenant_routing_source = lambda: app_config.tenant_routing_source
get_tenant_routing_cache_ttl_seconds = lambda: app_config.tenant_routing_cache_ttl_seconds
get_tenant_routing_app_config_endpoint = lambda: app_config.tenant_routing_app_config_endpoint
get_tenant_routing_app_config_label = lambda: app_config.tenant_routing_app_config_label
get_issuer_app_config_key_prefix = lambda: app_config.issuer_app_config_key_prefix
get_issuer_app_config_label = lambda: app_config.issuer_app_config_label
get_issuer_configs = lambda: app_config.issuer_configs
get_issuer_environments = lambda: app_config.issuer_environments
