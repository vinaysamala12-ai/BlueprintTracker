"""MCP server factory and tool registration utilities."""

import importlib
import logging
import os
import shutil
import sys
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Optional, Union
from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.resources.template import match_uri_template
from mcp import types as mcp_types
from ..core.config import app_config
from ..core.context import (
    get_correlation_id,
    get_mcp_diagnostic_id,
    reset_mcp_diagnostic_id,
    set_mcp_diagnostic_id,
)
from ..core.fastmcp_compat import (
    list_mcp_items_unfiltered,
    resource_uri_key,
)
from ..core.http_client import shared_http_lifespan
from ..core.telemetry import setup_telemetry
from .. import (
    setup_logging,
    get_project_metadata,
    set_app_config,
    set_app_logger,
    require_api_key,
    log_requests,
    handle_exceptions,
    get_app_logger,
)
from ..decorators.prompts import (
    handle_prompt_exceptions,
    log_prompt_requests,
    require_api_key_prompt,
)
from ..decorators.resources import (
    handle_resource_exceptions,
    log_resource_requests,
    require_api_key_resource,
)

# Module state
_global_server: Optional[FastMCP] = None
_domains_discovered: bool = False


async def _get_resource_meta_for_uri(
    mcp: FastMCP, uri: Any
) -> dict[str, Any] | None:
    uri_str = str(uri)
    try:
        component = await _find_resource_component_for_uri(mcp, uri_str)
        return _component_meta(component) if component is not None else None
    except Exception:
        # Surfaces in production logs so AIS losing _meta.lastModified is
        # investigatable; the read itself does not fail.
        get_app_logger().exception(
            f"Failed to resolve resource metadata for '{uri_str}'"
        )
        return None


async def _find_resource_component_for_uri(mcp: FastMCP, uri: str) -> Any | None:
    # Concrete URIs resolve in O(1) via FastMCP's public getter when present;
    # builds without it fall through to a list scan.
    get_resource = getattr(mcp, "get_resource", None)
    if callable(get_resource):
        try:
            resource = await get_resource(uri)
        except Exception:
            get_app_logger().warning(
                f"FastMCP get_resource({uri!r}) failed", exc_info=True
            )
            resource = None
        if resource is not None:
            return resource
    else:
        for resource in await list_mcp_items_unfiltered(mcp, "list_resources"):
            if resource_uri_key(resource) == uri:
                return resource

    # Templates have no concrete URI to look up — scan and template-match.
    for template in await list_mcp_items_unfiltered(mcp, "list_resource_templates"):
        candidate = resource_uri_key(template)
        try:
            if match_uri_template(uri, candidate):
                return template
        except Exception as exc:
            # Programming/registration error — a malformed template URI never
            # participates in any read's meta lookup. Operator-visible.
            get_app_logger().warning(
                f"Skipping malformed registered resource template "
                f"{candidate!r}: {exc}"
            )
    return None


def _component_meta(component: Any) -> dict[str, Any] | None:
    get_meta = getattr(component, "get_meta", None)
    raw = get_meta() if callable(get_meta) else getattr(component, "meta", None)

    if not isinstance(raw, dict):
        return None

    # Drop FastMCP's internal namespace before exposing on the wire — the
    # ``fastmcp.tags`` payload changes shape across patch releases and would
    # bust prompt caching for clients that hash the meta envelope.
    return {k: v for k, v in raw.items() if k != "fastmcp"}


# JSON-RPC error code mapping used when shaping ``_meta.error`` on tool
# failures. Codes follow the JSON-RPC 2.0 spec: -32602 = Invalid params,
# -32603 = Internal error. AIS reads ``_meta.error.code`` to surface a
# canonical reason in its diagnostics pane.
_ERROR_KIND_TO_JSONRPC_CODE: dict[str, int] = {
    "validation_error": -32602,
    "api_error": -32603,
    "execution_error": -32603,
    "auth_error": -32603,
    "resource_error": -32603,
    "unexpected_error": -32603,
}


def _meta_to_dict(meta: Any) -> dict[str, Any]:
    """Best-effort conversion of an MCP ``_meta`` payload to a flat dict.

    The MCP SDK models ``_meta`` as a Pydantic model with ``extra="allow"``
    so it round-trips arbitrary keys; older shapes are plain dicts. Both
    are handled.
    """
    if meta is None:
        return {}
    if hasattr(meta, "model_dump"):
        try:
            return meta.model_dump(exclude_none=True, by_alias=True)
        except Exception:
            return {}
    if isinstance(meta, dict):
        return {k: v for k, v in meta.items() if v is not None}
    return {}


def _extract_mcp_diagnostic_id(req: Any) -> Optional[str]:
    """Pull ``mcp_diagnostic_id`` out of ``req.params._meta``.

    AIS sends the field as ``mcp_diagnostic_id``; we also accept the
    camelCase variant so future client revisions can rename without
    forcing a server bump. Returns ``None`` when neither key is present.
    """
    try:
        params = getattr(req, "params", None)
        if params is None:
            return None
        meta = getattr(params, "meta", None)
    except Exception:
        return None
    payload = _meta_to_dict(meta)
    return payload.get("mcp_diagnostic_id") or payload.get("mcpDiagnosticId")


def _install_call_tool_meta_handler(mcp: FastMCP) -> None:
    """Wrap the registered ``CallToolRequest`` handler with diagnostics enrichment.

    Two concerns:

    1. **Capture** ``params._meta.mcp_diagnostic_id`` (per AIS spec) into the
       framework's request context so tool bodies, ``mcp_log``, and the
       success/error envelope builders all see the same value.
    2. **Enrich** the response envelope:

       - Success path: add ``_meta.mcp_diagnostic_id`` if present, otherwise
         leave the ``_meta`` produced by ``handle_exceptions`` alone.
       - Error path: parse the structured JSON payload our wrapper raised
         (via ``ToolError(<json>)``) and reshape it into AIS's "Acceptable"
         error envelope — human-readable text in ``content[0].text`` plus
         ``_meta.error = {code, message}``, ``_meta.error_class``,
         ``_meta.error_kind``, ``_meta.correlation_id``, and
         ``_meta.mcp_diagnostic_id`` for support-pane pivots.
    """
    handlers = mcp._mcp_server.request_handlers
    original = handlers[mcp_types.CallToolRequest]

    async def handler(req: mcp_types.CallToolRequest):
        # Token-based set/reset: each task gets its own diagnostic-ID
        # ContextVar value, isolated from any concurrent tool call sharing
        # the parent context. ``reset`` in ``finally`` guarantees no bleed
        # into a later call that reuses this task / context (in-memory
        # ``Client``, embedded usage, tests, or any sequential dispatch).
        # ``set(None)`` is meaningful — it explicitly masks any inherited
        # value so an absent ``_meta.mcp_diagnostic_id`` cannot inherit a
        # previous call's ID.
        diagnostic_id = _extract_mcp_diagnostic_id(req)
        token = set_mcp_diagnostic_id(diagnostic_id)
        try:
            result = await original(req)

            # Default: pass through unchanged unless we can identify the
            # wrapped CallToolResult to enrich.
            call_result = getattr(result, "root", result)
            if not isinstance(call_result, mcp_types.CallToolResult):
                return result

            enriched = _enrich_call_tool_result(call_result, diagnostic_id)
            if enriched is call_result:
                return result
            return mcp_types.ServerResult(enriched)
        finally:
            reset_mcp_diagnostic_id(token)

    handlers[mcp_types.CallToolRequest] = handler


def _enrich_call_tool_result(
    result: mcp_types.CallToolResult, mcp_diagnostic_id: Optional[str]
) -> mcp_types.CallToolResult:
    """Return a new CallToolResult with enriched ``_meta`` per AIS spec.

    Returns the input unchanged when there's nothing to enrich; never
    raises so a malformed payload can never break tool dispatch.
    """
    base_meta: dict[str, Any] = dict(result.meta or {})

    if mcp_diagnostic_id and "mcp_diagnostic_id" not in base_meta:
        base_meta["mcp_diagnostic_id"] = mcp_diagnostic_id

    if not result.isError:
        if base_meta == (result.meta or {}):
            return result
        return result.model_copy(update={"meta": base_meta})

    # Error path: try to parse our wrapper's structured JSON payload from
    # the content text. If the payload didn't come from this framework,
    # leave the content untouched.
    payload = _parse_framework_error_payload(result.content)
    if payload is None:
        if base_meta == (result.meta or {}):
            return result
        return result.model_copy(update={"meta": base_meta})

    error_class = payload.get("error_class", "Error")
    error_message = payload.get("error", "")
    error_kind = payload.get("error_kind", "unexpected_error")
    code = _ERROR_KIND_TO_JSONRPC_CODE.get(error_kind, -32603)

    # ``error`` is overwritten unconditionally so the canonical {code, message}
    # form always wins over anything a tool body may have stamped on its own
    # ``_meta`` (the wire contract is fixed). ``error_class`` / ``error_kind``
    # use ``setdefault`` because tools are allowed to override the framework's
    # auto-classification when they have richer domain knowledge — the asymmetry
    # is intentional, not a typo.
    base_meta["error"] = {"code": code, "message": error_message}
    base_meta.setdefault("error_class", error_class)
    base_meta.setdefault("error_kind", error_kind)
    if "correlation_id" in payload and "correlation_id" not in base_meta:
        base_meta["correlation_id"] = payload["correlation_id"]
    if "elapsed_ms" in payload and "elapsed_ms" not in base_meta:
        base_meta["elapsed_ms"] = payload["elapsed_ms"]
    if "mcp_diagnostic_id" in payload and "mcp_diagnostic_id" not in base_meta:
        base_meta["mcp_diagnostic_id"] = payload["mcp_diagnostic_id"]

    new_text = f"{error_class}: {error_message}" if error_message else error_class
    new_content: list[Any] = [mcp_types.TextContent(type="text", text=new_text)]

    return result.model_copy(update={"content": new_content, "meta": base_meta})


def _parse_framework_error_payload(content: list[Any]) -> Optional[dict[str, Any]]:
    """Recover the structured payload our ``handle_exceptions`` raised.

    Tools that don't go through this framework (or that raised something
    other than our wrapper's ``ToolError``) won't match — the caller treats
    that as "leave the content alone".
    """
    if not content:
        return None
    first = content[0]
    text = getattr(first, "text", None)
    if not text:
        return None
    try:
        candidate = json.loads(text)
    except (TypeError, ValueError):
        return None
    if isinstance(candidate, dict) and "error_class" in candidate:
        return candidate
    return None


def _install_diagnostic_id_capture(
    mcp: FastMCP, request_type: type
) -> None:
    """Install a wrapper that captures ``_meta.mcp_diagnostic_id`` for one
    request type without touching the response shape.

    Used for ``GetPromptRequest`` and (alongside the existing
    ``_install_read_resource_meta_handler``) ``ReadResourceRequest`` so
    notifications emitted during prompt/resource reads can stamp the
    inbound diagnostic ID without us having to reshape success envelopes.
    """
    handlers = mcp._mcp_server.request_handlers
    original = handlers[request_type]

    async def handler(req: Any):
        # Token-based set/reset — see the rationale in
        # ``_install_call_tool_meta_handler``.
        diagnostic_id = _extract_mcp_diagnostic_id(req)
        token = set_mcp_diagnostic_id(diagnostic_id)
        try:
            return await original(req)
        finally:
            reset_mcp_diagnostic_id(token)

    handlers[request_type] = handler


def _install_read_resource_meta_handler(mcp: FastMCP) -> None:
    """Patch FastMCP's read-resource response so result/content _meta is preserved.

    FastMCP 3.2.4 stores resource metadata on list entries and per-content read
    entries, but omits top-level read-response metadata. AIS needs
    ``_meta.lastModified`` at read time, so the framework installs the standard
    read handler with top-level metadata copied from the matched resource or
    resource template.
    """

    async def handler(req: mcp_types.ReadResourceRequest):
        # Token-based set/reset — see the rationale in
        # ``_install_call_tool_meta_handler``.
        diagnostic_id = _extract_mcp_diagnostic_id(req)
        token = set_mcp_diagnostic_id(diagnostic_id)
        try:
            result = await mcp._read_resource_mcp(req.params.uri)
            # Async-resource reads return a CreateTaskResult (a task handle,
            # not content) — there's no payload to attach lastModified to, so
            # pass it through untouched. getattr keeps this compatible with
            # MCP SDK builds that predate the tasks surface.
            create_task_result = getattr(mcp_types, "CreateTaskResult", None)
            if create_task_result is not None and isinstance(
                result, create_task_result
            ):
                return mcp_types.ServerResult(result)

            meta = await _get_resource_meta_for_uri(mcp, req.params.uri)
            if meta is not None:
                merged_meta = dict(getattr(result, "meta", None) or {})
                merged_meta.update(meta)
                result = result.model_copy(update={"meta": merged_meta})
            return mcp_types.ServerResult(result)
        finally:
            reset_mcp_diagnostic_id(token)

    mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = handler


def _callable_accepts_keyword(func: Callable, keyword: str) -> bool:
    """Return True if ``func`` can accept ``keyword`` as a kwarg."""
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return True
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        or parameter.name == keyword
        for parameter in signature.parameters.values()
    )


def _configure_azure_startup_logging() -> None:
    """Reduce noisy Azure SDK startup warnings before app logging is initialized."""
    azure_loggers = [
        "azure",
        "azure.identity",
        "azure.core",
        "azure.core.pipeline.policies.http_logging_policy",
    ]

    for logger_name in azure_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.ERROR)


def _warn_local_appconfig_prereqs() -> None:
    """Emit an early warning when local App Configuration auth prerequisites are missing."""
    config_source = os.getenv("MCP_TOKEN_CONFIG_SOURCE", "").strip().lower()
    if config_source != "appconfig":
        return

    app_config_endpoint = os.getenv("MCP_TOKEN_APP_CONFIG_ENDPOINT", "").strip()
    if not app_config_endpoint:
        return

    server_host = os.getenv("SERVER_HOST", "localhost").strip().lower()
    is_localhost = server_host in {"localhost", "127.0.0.1", "::1"}
    if not is_localhost:
        return

    if shutil.which("az") is not None:
        return

    bootstrap_logger = logging.getLogger("mcp_server.bootstrap")
    if not bootstrap_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        bootstrap_logger.addHandler(handler)
        bootstrap_logger.setLevel(logging.INFO)
        bootstrap_logger.propagate = False

    bootstrap_logger.warning(
        "Azure App Configuration local preflight: MCP_TOKEN_CONFIG_SOURCE=appconfig, "
        "App Configuration endpoint is set, and SERVER_HOST looks local, but Azure CLI "
        "was not found on PATH. Local/localhost guidance is Azure CLI auth: install Azure "
        "CLI and run 'az login'.",
    )


def _validate_token_config_at_startup() -> None:
    """Fail fast when ``MCP_TOKEN_CONFIG_SOURCE=custom`` but no custom provider is registered.

    Issuer/routing config *loading* is intentionally deferred to request time, but a
    ``custom`` source with no registered provider can never succeed — so surface it at
    startup (as OPERATIONS.md documents) rather than as a 500 on every request. Must run
    after ``auto_discover_domains()`` so providers registered in ``src/custom/server.py``
    are visible. This only inspects the registry; it does not trigger any config load.
    """
    from ..core.issuer_provider import get_issuer_provider
    from ..core.tenant_routing_provider import get_named_provider_configs

    if app_config.issuer_source == "custom" and get_issuer_provider() is None:
        raise RuntimeError(
            "MCP_TOKEN_CONFIG_SOURCE=custom requires a custom IssuerProvider registered "
            "via set_issuer_provider() in src/custom/server.py before the server starts."
        )

    if app_config.tenant_routing_source == "custom":
        missing = [
            name
            for name, cfg in get_named_provider_configs().items()
            if cfg.explicit_provider is None
        ]
        if missing:
            raise RuntimeError(
                "MCP_TOKEN_CONFIG_SOURCE=custom requires a provider= instance for every tenant "
                "routing provider registered via add_tenant_routing_provider(); missing for: "
                f"{', '.join(sorted(missing))}."
            )


def create_mcp_server() -> FastMCP:
    """
    Create and configure a FastMCP server instance with all framework setup.
    
    This function handles all the framework initialization:
    - Environment loading
    - Configuration setup
    - Logging initialization
    - Server instance creation
    
    Returns:
        Configured FastMCP server instance ready for tool registration
        
    Raises:
        RuntimeError: If server creation fails
    """
    try:
        # Load environment variables
        load_dotenv()

        # Suppress verbose Azure SDK credential-chain logs during startup.
        _configure_azure_startup_logging()

        # Emit local-only prereq hints before configuration loading triggers Azure auth.
        _warn_local_appconfig_prereqs()

        # Capture only scalar startup settings; defer issuer/routing loads until request-time auth.
        config = app_config.to_dict(include_dynamic_config=False)
        # Remove sensitive fields before propagating/logging config-derived values.
        config = {
            key: value
            for key, value in config.items()
            if key not in {"mcp_master_api_key", "mcp_master_api_key_name"}
        }

        # Set up logging
        logger = setup_logging(
            log_level=app_config.log_level,
            log_file=app_config.log_file
        )

        # Initialize application-level config and logger
        set_app_config(config)
        set_app_logger(logger)

        # Configure OpenTelemetry SDK if OTEL_EXPORTER_OTLP_ENDPOINT is set.
        # Must happen before FastMCP is constructed so the server's own spans
        # are captured by the configured tracer provider.
        setup_telemetry()

        # Log configuration load status early for easier startup diagnostics.
        config_source = config.get("issuer_source", "")  # issuer_source and tenant_routing_source both read MCP_TOKEN_CONFIG_SOURCE
        cache_ttl = config.get("issuer_cache_ttl_seconds", 0)
        logger.info(
            "Token config source=%s cache_ttl_seconds=%s",
            config_source,
            cache_ttl,
        )

        issuers_file = os.getenv("MCP_TOKEN_ISSUERS_FILE", "").strip()
        if config_source == "file" and issuers_file:
            logger.info("Issuer mappings configured from %s (load deferred until auth)", issuers_file)
        elif config_source == "file":
            logger.info("No issuer mapping file configured (MCP_TOKEN_ISSUERS_FILE is empty)")
        elif config_source == "appconfig":
            issuer_endpoint = config.get("issuer_app_config_endpoint", "")
            issuer_prefix = config.get("issuer_app_config_key_prefix", "issuers/")
            logger.info(
                "App Configuration issuers endpoint=%s key_prefix=%s load=deferred",
                issuer_endpoint or "<empty>",
                issuer_prefix,
            )

        # Get project metadata
        project_metadata = get_project_metadata()

        # Initialize FastMCP server. The lifespan owns the shared outbound HTTP
        # client and tears it down on shutdown — see framework/core/http_client.py.
        mcp = FastMCP(
            name=project_metadata.get("name", "Next AI MCP Server"),
            instructions=project_metadata.get("description", "MCP Server"),
            lifespan=shared_http_lifespan,
        )
        _install_read_resource_meta_handler(mcp)
        _install_call_tool_meta_handler(mcp)
        _install_diagnostic_id_capture(mcp, mcp_types.GetPromptRequest)

        logger.info("MCP server instance created and configured")
        
        return mcp
    except Exception as e:
        raise RuntimeError(f"Failed to create MCP server: {e}") from e


def auto_discover_domains() -> None:
    """
    Auto-discover and import domain server modules from the src/ directory.
    
    This function scans the src/ directory for subdirectories containing a server.py file
    and automatically imports them to trigger tool registration.
    """
    global _domains_discovered
    if _domains_discovered:
        return
    
    logger = get_app_logger()
    logger.info("Starting domain auto-discovery...")
    
    # Get the src directory path
    src_path = Path("src")
    if not src_path.exists() or not src_path.is_dir():
        logger.warning("src/ directory not found, skipping domain discovery")
        _domains_discovered = True
        return
    
    discovered_domains = []
    failed_domains = []
    
    # Scan for domain directories
    try:
        for item in sorted(src_path.iterdir()):
            if not item.is_dir():
                continue
                
            # Skip special directories
            if item.name.startswith(('_', '.')) or item.name.endswith('.egg-info'):
                continue
                
            # Check if it has a server.py file
            server_file = item / "server.py"
            if not server_file.exists():
                continue
                
            # Try to import the domain's server module
            module_name = f"src.{item.name}.server"
            try:
                importlib.import_module(module_name)
                discovered_domains.append(item.name)
                logger.info(f"Registered domain: {item.name}")
            except ImportError as e:
                failed_domains.append((item.name, f"Import error: {e}"))
                logger.error(f"Failed to load domain '{item.name}': {e}")
            except Exception as e:
                failed_domains.append((item.name, f"Unexpected error: {type(e).__name__}: {e}"))
                logger.error(f"Unexpected error loading domain '{item.name}': {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error during domain discovery: {e}", exc_info=True)
    
    # Summary logging
    if discovered_domains:
        logger.info(f"Domain discovery complete. Registered {len(discovered_domains)} domain(s): {', '.join(discovered_domains)}")
    
    if failed_domains:
        logger.warning(f"Failed to load {len(failed_domains)} domain(s)")
        for domain, error in failed_domains:
            logger.debug(f"  - {domain}: {error}")
    
    if not discovered_domains and not failed_domains:
        logger.warning("No domains found. Ensure domain directories contain server.py files.")
    
    _domains_discovered = True


def get_mcp_server() -> FastMCP:
    """
    Get the global MCP server instance, creating it if needed.
    
    This function provides access to the framework-managed global server instance.
    The server is created lazily on first access with all framework setup applied.
    It also triggers auto-discovery of domains on first access.
    
    Returns:
        The global FastMCP server instance
        
    Raises:
        RuntimeError: If server creation fails
    """
    global _global_server
    if _global_server is None:
        _global_server = create_mcp_server()
        # Auto-discover domains after server creation
        auto_discover_domains()
        # Now that custom providers (if any) are registered, fail fast on
        # an unsatisfiable MCP_TOKEN_CONFIG_SOURCE=custom configuration.
        _validate_token_config_at_startup()
    return _global_server


def register_tool(
    tool_name: str,
    *,
    timeout_seconds: Optional[float] = None,
    version: Optional[Union[str, int]] = None,
) -> Callable:
    """
    Decorator to register a tool with the global MCP server.

    Automatically applies framework decorators:
    - FastMCP tool registration
    - Request logging
    - API key authentication
    - Exception handling

    Args:
        tool_name: Name of the tool for error handling
        timeout_seconds: Optional per-tool wall-clock deadline. Overrides the
            ``TOOL_TIMEOUT_SECONDS`` default; ``None`` falls back to that default
            (which itself defaults to no timeout).
        version: Optional semantic version (``"1.0"``, ``2``, etc.). Multiple
            versions of the same logical tool may coexist; clients calling
            the unversioned name receive the highest-version implementation.
            See ``DEVELOPER_GUIDE.md`` for the versioning policy.

    Returns:
        Decorator function

    Example:
        @register_tool("my_tool", timeout_seconds=30, version="2.0")
        async def my_tool_handler(params: MyParams):
            return await my_tool_function(params.param1, params.param2)
    """
    effective_timeout = (
        timeout_seconds if timeout_seconds is not None else app_config.tool_timeout_seconds
    )

    def decorator(func: Callable) -> Callable:
        # Get the global server instance
        server = get_mcp_server()

        # Apply decorators in correct order — server.tool() must be LAST.
        # Composition (outer → inner): log_requests → handle_exceptions →
        # require_api_key → func. ``handle_exceptions`` wraps
        # ``require_api_key`` so auth failures (HTTPException) flow through
        # the structured-error path: classified as ``auth_error``,
        # re-raised as ``ToolError(JSON)``, and reshaped by
        # ``_enrich_call_tool_result`` into the AIS error envelope. With
        # ``require_api_key`` outside, auth failures returned plain
        # FastMCP error text without ``_meta.error`` / ``error_class`` /
        # ``error_kind`` / ``correlation_id`` — breaking AIS routing.
        decorated_func = require_api_key(func)
        decorated_func = handle_exceptions(tool_name)(decorated_func)
        decorated_func = log_requests(decorated_func)
        tool_kwargs: dict = {}
        if effective_timeout:
            tool_kwargs["timeout"] = effective_timeout
        if version is not None:
            tool_kwargs["version"] = version
        supported_tool_kwargs = {
            key: value
            for key, value in tool_kwargs.items()
            if _callable_accepts_keyword(server.tool, key)
        }
        unsupported_tool_kwargs = sorted(set(tool_kwargs) - set(supported_tool_kwargs))
        if unsupported_tool_kwargs:
            get_app_logger().warning(
                f"FastMCP build does not support tool registration kwarg(s) "
                f"{unsupported_tool_kwargs}; registering '{tool_name}' without them"
            )
        decorated_func = server.tool(tool_name, **supported_tool_kwargs)(decorated_func)

        return decorated_func

    return decorator


def register_prompt(
    prompt_name: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    version: Optional[Union[str, int]] = None,
) -> Callable:
    """
    Decorator to register a prompt with the global MCP server.

    Mirrors :func:`register_tool` but for the MCP ``prompts/list`` /
    ``prompts/get`` surface defined in the 2025-11-25 specification. Applies
    the framework's standard decorator stack:

    - FastMCP prompt registration (handles capability declaration, listing,
      and argument schema generation from the function signature).
    - Request logging.
    - API-key / JWT authentication (same pipeline as tools — prompts honour
      the ``Authorization`` and ``MCP_MASTER_API_KEY_NAME`` headers).
    - Exception handling that logs framework errors and re-raises. FastMCP
      wraps the exception in ``PromptError``; the MCP lowlevel handler emits
      ``ErrorData(code=0, ...)`` with the stringified message. Clients see an
      ``McpError`` they can read, but the JSON-RPC code is not mapped to
      ``-32602`` / ``-32603`` in the current FastMCP build.

    Unlike tools, prompt functions take their arguments as keyword parameters
    matching the prompt's argument schema (not a single Pydantic params model).
    The function should return a list of ``PromptMessage`` instances, a single
    string (auto-wrapped as a user message), or any value FastMCP accepts.

    Args:
        prompt_name: Stable identifier returned in ``prompts/list``.
        title: Optional human-readable title shown in clients.
        description: Optional description (defaults to the function docstring).
        version: Optional semantic version. Multiple versions of the same
            prompt may coexist; clients calling the unversioned name receive
            the highest version.

    Returns:
        Decorator function.

    Example::

        from fastmcp.prompts import Message

        @register_prompt("code_review", title="Request Code Review")
        async def code_review(code: str, focus: str = "general") -> list[Message]:
            return [Message(f"Review this code (focus: {focus}):\\n{code}", role="user")]
    """

    def decorator(func: Callable) -> Callable:
        server = get_mcp_server()

        # Same composition as ``register_tool``: handle_*_exceptions wraps
        # require_api_key_* so auth failures flow through the framework's
        # error path (logged once with ``error_kind="auth_error"``). The
        # prompt/resource handlers retain their existing ``except
        # HTTPException: raise`` so notifications/message is *not* emitted
        # for auth rejections (clients see the McpError directly), but the
        # log entry carries the classified kind for parity with tools.
        decorated_func = require_api_key_prompt(func)
        decorated_func = handle_prompt_exceptions(prompt_name)(decorated_func)
        decorated_func = log_prompt_requests(decorated_func)

        prompt_kwargs = {
            k: v
            for k, v in {
                "title": title,
                "description": description,
                "version": version,
            }.items()
            if v is not None
        }

        decorated_func = server.prompt(prompt_name, **prompt_kwargs)(decorated_func)
        return decorated_func

    return decorator


def register_resource(
    uri: str,
    *,
    name: Optional[str] = None,
    title: Optional[str] = None,
    mime_type: Optional[str] = None,
    description: Optional[str] = None,
    annotations: Optional[dict[str, Any]] = None,
    meta: Optional[dict[str, Any]] = None,
) -> Callable:
    """Decorator to register an MCP resource with the global server.

    FastMCP treats a URI containing ``{param}``, or a function with non-context
    parameters, as a resource template. Use :func:`register_resource_template`
    when the template intent should be explicit at the call site.
    """

    def decorator(func: Callable) -> Callable:
        server = get_mcp_server()

        # Same composition as ``register_tool`` / ``register_prompt``.
        decorated_func = require_api_key_resource(func)
        decorated_func = handle_resource_exceptions(uri)(decorated_func)
        decorated_func = log_resource_requests(decorated_func)

        resource_kwargs = {
            k: v
            for k, v in {
                "name": name,
                "title": title,
                "description": description,
                "mime_type": mime_type,
                "annotations": annotations,
                "meta": meta,
            }.items()
            if v is not None
        }

        decorated_func = server.resource(uri, **resource_kwargs)(decorated_func)
        return decorated_func

    return decorator


def register_resource_template(
    uri_template: str,
    *,
    name: Optional[str] = None,
    title: Optional[str] = None,
    mime_type: Optional[str] = None,
    description: Optional[str] = None,
    annotations: Optional[dict[str, Any]] = None,
    meta: Optional[dict[str, Any]] = None,
) -> Callable:
    """Decorator to register an MCP resource template with the global server.

    FastMCP registers templates through ``resource(...)`` when the URI contains
    placeholders. This wrapper keeps template intent explicit and rejects
    concrete URIs so call sites do not accidentally publish a static resource.
    """

    if "{" not in uri_template or "}" not in uri_template:
        raise ValueError(
            "register_resource_template requires a URI template containing "
            "at least one '{name}' placeholder"
        )

    return register_resource(
        uri_template,
        name=name,
        title=title,
        mime_type=mime_type,
        description=description,
        annotations=annotations,
        meta=meta,
    )
