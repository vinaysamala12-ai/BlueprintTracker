"""
MCP Server Framework

This package contains the core framework components for building MCP servers.
Developers typically don't need to modify files in this package.
"""

# Import key framework components for easy access
from .core.utils import (
    MCPServerError,
    ToolExecutionError,
    APIError,
    ValidationError,
    setup_logging,
    get_uptime_seconds,
    get_app_config,
    set_app_config,
    get_app_logger,
    set_app_logger,
    get_project_metadata,
)

from .core.config import (
    Config,
    app_config,
    get_configuration,
    get_log_level,
    get_log_file,
    get_server_host,
    get_server_port,
    get_mcp_master_api_key,
    get_mcp_master_api_key_name,
    get_auth_bearer_required,
    get_auth_bearer_verify_signature,
    get_auth_bearer_verify_issuer,
    get_auth_bearer_verify_expiry,
    get_issuer_configs,
    get_issuer_environments,
)

from .decorators import (
    require_api_key,
    log_requests,
    handle_exceptions,
)

from .core.context import (
    get_request_context,
    set_request_context,
    get_api_key_from_context,
    get_correlation_id,
    get_mcp_diagnostic_id,
    add_bearer_token,
    get_outbound_headers,
    get_tenant_routing_property,
    get_tenant_routing_secret,
    register_secret_resolver,
)

from .core.mcp_logging import mcp_log

from .core.http_client import (
    get_shared_http_client,
    shared_http_lifespan,
)

from .core.telemetry import (
    setup_telemetry,
    shutdown_telemetry,
    is_telemetry_enabled,
)

from .core.mcp_configuration import (
    MCPConfiguration,
    ConfigurationProvider,
    ConfigurationProviderStatus,
    FileConfigurationProvider,
    CONFIGURATION_HEADER,
)

from .core.issuer_provider import (
    IssuerProvider,
    FileIssuerProvider,
    AppConfigIssuerProvider,
    set_issuer_provider,
)

from .core.tenant_routing_provider import (
    TenantRoutingProvider,
    FileTenantRoutingProvider,
    AppConfigTenantRoutingProvider,
    add_tenant_routing_provider,
)

from .core.routing_key import (
    RoutingKeySegment,
    RoutingKeySchema,
    literal,
    issuer_info,
    token_claim,
    header,
)

from .middleware.configuration_middleware import ConfigurationMiddleware

from .server import (
    create_mcp_server,
    register_tool,
    register_prompt,
    register_resource,
    register_resource_template,
    get_mcp_server,
    auto_discover_domains,
)

__all__ = [
    # Core utilities
    "MCPServerError",
    "ToolExecutionError", 
    "APIError",
    "ValidationError",
    "setup_logging",
    "get_uptime_seconds",
    "get_app_config",
    "set_app_config",
    "get_app_logger",
    "set_app_logger",
    "handle_exceptions",
    "get_project_metadata",
    
    # Configuration
    "Config",
    "app_config",
    "get_configuration",
    "get_log_level",
    "get_log_file",
    "get_server_host",
    "get_server_port",
    "get_mcp_master_api_key",
    "get_mcp_master_api_key_name",
    "get_auth_bearer_required",
    "get_auth_bearer_verify_signature",
    "get_auth_bearer_verify_issuer",
    "get_auth_bearer_verify_expiry",
    "get_issuer_configs",
    "get_issuer_environments",

    # Decorators
    "require_api_key",
    "log_requests", 
    "handle_exceptions",
    
    # Context
    "get_request_context",
    "set_request_context",
    "get_api_key_from_context",
    "get_correlation_id",
    "get_mcp_diagnostic_id",
    "add_bearer_token",
    "get_outbound_headers",

    # MCP diagnostics
    "mcp_log",

    # Shared HTTP client
    "get_shared_http_client",
    "shared_http_lifespan",

    # Observability
    "setup_telemetry",
    "shutdown_telemetry",
    "is_telemetry_enabled",
    
    # MCP Configuration
    "MCPConfiguration",
    "ConfigurationProvider",
    "ConfigurationProviderStatus",
    "FileConfigurationProvider",
    "ConfigurationMiddleware",
    "CONFIGURATION_HEADER",

    # Issuer providers
    "IssuerProvider",
    "FileIssuerProvider",
    "AppConfigIssuerProvider",
    "set_issuer_provider",

    # Tenant routing providers
    "TenantRoutingProvider",
    "FileTenantRoutingProvider",
    "AppConfigTenantRoutingProvider",
    "add_tenant_routing_provider",

    # Routing key schema
    "RoutingKeySegment",
    "RoutingKeySchema",
    "literal",
    "issuer_info",
    "token_claim",
    "header",

    # Tenant routing context helpers
    "get_tenant_routing_property",
    "get_tenant_routing_secret",
    "register_secret_resolver",

    # Server factory
    "create_mcp_server",
    "register_tool",
    "register_prompt",
    "register_resource",
    "register_resource_template",
    "get_mcp_server",
    "auto_discover_domains",
]
