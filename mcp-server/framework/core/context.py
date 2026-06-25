"""Request context management using contextvars."""

import os
import uuid
from contextvars import ContextVar, Token
from typing import Any, Dict, Optional
from .utils import get_app_logger, ValidationError
from .config import get_mcp_master_api_key_name, get_correlation_id_name, app_config

# Context variable to store request information
request_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("request_context", default=None)

def get_request_context() -> Optional[Dict[str, Any]]:
    """Get the current request context."""
    return request_context.get()

def set_request_context(context: Dict[str, Any]):
    """Set the request context."""
    request_context.set(context)

def get_api_key_from_context() -> Optional[str]:
    """Get the API key from the current context."""
    context = get_request_context()
    if not context or not context.get("headers"):
        return None

    headers = context["headers"]

    api_key_name = get_mcp_master_api_key_name()
    if context.get(api_key_name):
        return context[api_key_name]    
    
    api_key_value = None

    for header_name, header_value in headers.items():
        if header_name.lower() == api_key_name.lower():
            api_key_value = header_value
            break

    if api_key_value:
        context[api_key_name] = api_key_value
        get_app_logger().debug("[AUTH] API key extracted from headers")
    return api_key_value


def setup_correlation_id(headers: Dict[str, Any]) -> str:
    """
    Setup and return a correlation ID for the current request.
    
    Extracts correlation ID from headers if present, otherwise generates a new one.
    
    Args:
        headers: Request headers dictionary
        
    Returns:
        str: The correlation ID for the current request
    """
    correlation_id_header_name = get_correlation_id_name()
    correlation_id_value = None
    
    # Try to get correlation ID from headers (case-insensitive)
    for header_name, header_value in headers.items():
        if header_name.lower() == correlation_id_header_name.lower():
            correlation_id_value = header_value
            break
    
    # Generate a new correlation ID if not found in headers
    if not correlation_id_value:
        correlation_id_value = str(uuid.uuid4())
    
    return correlation_id_value


def get_correlation_id() -> Optional[str]:
    """
    Get the correlation ID from the current request context.

    Returns:
        Optional[str]: The correlation ID if present in context, None otherwise
    """
    context = get_request_context()
    if not context:
        return None

    correlation_id_header_name = get_correlation_id_name()
    return context.get(correlation_id_header_name)


# AIS per-call diagnostic ID lives at the JSON-RPC
# ``params._meta.mcp_diagnostic_id`` layer (not an HTTP header), so it is
# captured by the framework's tool/prompt/resource request-handler patches
# rather than the HTTP middleware.
#
# **Why a dedicated ContextVar instead of a key on the request_context dict:**
# the request_context dict is itself a ContextVar value; when an asyncio task
# is spawned, the child inherits a *reference* to the parent's dict (the
# ContextVar value is copied, the dict is not). If two concurrent tool calls
# both mutated that shared dict via ``dict[KEY] = value``, the second write
# would overwrite the first — and since both tasks read from the same dict,
# both responses would carry the second call's diagnostic ID. That bug was
# observed end-to-end with two ``asyncio.gather``-ed tool calls. A dedicated
# ContextVar with the standard ``set()``/``reset(token)`` pattern fixes it:
# each ``set()`` only mutates the calling task's context, and ``reset(token)``
# guarantees the post-call clear regardless of how the call exited.
_mcp_diagnostic_id_var: ContextVar[Optional[str]] = ContextVar(
    "mcp_diagnostic_id", default=None
)


def set_mcp_diagnostic_id(value: Optional[str]) -> Token[Optional[str]]:
    """Stash the AIS per-call diagnostic ID for the active task / context.

    Returns a ``Token`` that callers MUST pass to
    :func:`reset_mcp_diagnostic_id` in a ``finally`` block so a later call
    sharing the same task cannot inherit this call's ID.

    The framework's request-handler patches call this at the start of every
    ``tools/call`` / ``prompts/get`` / ``resources/read`` and reset on the
    way out. ``value`` may be ``None`` — that explicitly stamps "no ID"
    into this task's context, masking any inherited value.
    """
    return _mcp_diagnostic_id_var.set(value)


def reset_mcp_diagnostic_id(token: Token[Optional[str]]) -> None:
    """Restore the diagnostic-ID ContextVar to its pre-``set()`` value.

    Pair with :func:`set_mcp_diagnostic_id` in a ``finally`` block. Safe
    to call with a token that originated in a different task — the
    ContextVar API is task-local.
    """
    _mcp_diagnostic_id_var.reset(token)


def get_mcp_diagnostic_id() -> Optional[str]:
    """Return the AIS per-call diagnostic ID for the active request, if any.

    Distinct from :func:`get_correlation_id`: the correlation ID is the
    transport-level (HTTP header) ID used for cross-system tracing; the
    diagnostic ID is AIS's per-MCP-call ID used to route notifications and
    response envelopes to the right Studio diagnostics record.
    """
    return _mcp_diagnostic_id_var.get()


def add_bearer_token(
    headers: Optional[Dict[str, str]] = None,
    token: Optional[str] = None,
) -> Dict[str, str]:
    """
    Add ``Authorization: Bearer <token>`` to a headers dictionary for downstream API calls.
    CAUTION: Downstream APIs must validate and sanitize the token as it comes from
    the client's token and could be spoofed if the token is compromised.

    - If ``headers`` is ``None``, a new dictionary is created.
    - If ``token`` is omitted, the function attempts to read
      ``authorization_token`` from the current request context, e.g the AppCentral IAM token.
    - If no token is available, the input headers are returned unchanged.

    Args:
        headers: Existing headers to augment, or ``None`` to initialize a new dict.
        token: Bearer token value without the ``Bearer `` prefix.

    Returns:
        Dict[str, str]: Headers including ``Authorization`` when a token is available.
    """
    logger = get_app_logger()
    resolved_headers: Dict[str, str] = dict(headers) if headers else {}

    resolved_token = token
    token_source = "argument" if token else "context"
    if not resolved_token:
        context = get_request_context()
        if context:
            resolved_token = context.get("authorization_token")

    if resolved_token:
        resolved_headers["Authorization"] = f"Bearer {resolved_token}"
        logger.debug(
            "Added bearer token to outbound headers using token_source=%s header_count=%s",
            token_source,
            len(resolved_headers),
        )
    else:
        logger.debug(
            "No bearer token available for outbound headers using token_source=%s",
            token_source,
        )

    return resolved_headers


def get_outbound_headers() -> Dict[str, str]:
    """
    Build headers for downstream API calls using the current request context.

    Returns a dict containing:
    - ``Authorization: Bearer <token>`` — the original JWT token from the client
    - ``X-APTEAN-COID`` — company/org ID extracted from the JWT
    - ``X-APTEAN-UOID`` — user ID extracted from the JWT
    CAUTION: Downstream APIs must validate and sanitize these headers as they are derived from
    the client's token and could be spoofed if the token is compromised.

    Only keys that are present in the context are included, so the result
    can be safely spread into any httpx / requests call.
    """
    logger = get_app_logger()
    context = get_request_context()
    if not context:
        logger.debug("No request context available when building outbound headers")
        return {}

    headers: Dict[str, str] = add_bearer_token()

    coid = context.get("coid")
    if coid:
        headers["X-APTEAN-COID"] = str(coid)

    uoid = context.get("uoid")
    if uoid:
        headers["X-APTEAN-UOID"] = str(uoid)

    logger.debug(
        "Built outbound headers authorization=%s coid=%s uoid=%s header_count=%s",
        "Authorization" in headers,
        "X-APTEAN-COID" in headers,
        "X-APTEAN-UOID" in headers,
        len(headers),
    )

    return headers


def _resolve_route(provider: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Lazy per-request route lookup for a named provider.

    Caches the result in the request context so repeated calls within the same
    request pay no extra cost.
    """
    provider_routes: Dict[str, Any] = context.setdefault("_provider_routes", {})
    if provider not in provider_routes:
        provider_routes[provider] = app_config.find_resource_route(context, provider)

    return provider_routes[provider]


def enforce_tenant_authorization(context: Dict[str, Any]) -> None:
    """Raise ``PermissionError`` if any enforce_authorization provider has no matching rule for this request.

    Called by ``authenticate_request`` on every successful auth path (Bearer JWT,
    API key, and dev bypass) so that every tool, prompt, and resource call is gated —
    including those that never read routing properties directly.  API-key and
    dev-bypass requests carry no JWT claims, so routing schemas using
    ``token_claim()`` or ``issuer_info()`` will never match → 403.  In practice
    ``enforce_authorization=True`` requires a Bearer JWT.
    The route lookup result is cached in the request context, so subsequent
    calls to ``get_tenant_routing_property`` within the same request pay no
    extra cost.
    """
    import logging as _logging
    from .tenant_routing_provider import get_named_provider_configs

    for name, cfg in get_named_provider_configs().items():
        if cfg.enforce_authorization and _resolve_route(name, context) is None:
            logger = get_app_logger() or _logging.getLogger(__name__)
            coid = str(context.get("coid", "<unknown>"))
            issuer_url = str(context.get("issuer_url", "<unknown>"))
            logger.warning(
                "Tenant routing: enforce_authorization provider '%s' matched no rule "
                "(coid=%s issuer=%s) — returning 403",
                name, coid, issuer_url,
            )
            raise PermissionError(
                f"No tenant routing rule matched for provider '{name}' "
                f"(coid={coid}, issuer={issuer_url})"
            )


def prefetch_tenant_routes(context: Dict[str, Any]) -> None:
    """Resolve every registered provider's route into the per-request cache.

    Run off the event loop during authentication so that later synchronous
    ``get_tenant_routing_property`` / ``get_tenant_routing_secret`` calls inside
    async tool code are pure in-memory cache hits and never block the loop on
    file or Azure App Configuration I/O — including ``enforce_authorization=False``
    providers, which are not visited by ``enforce_tenant_authorization``.

    Per-provider load errors are swallowed here (logged at DEBUG): a misconfigured
    provider the request never reads must not fail authentication, and a provider
    that is read will re-raise the same error at the property-read call.
    """
    import logging as _logging
    from .tenant_routing_provider import get_named_provider_configs

    for name in get_named_provider_configs():
        try:
            _resolve_route(name, context)
        except Exception as exc:  # noqa: BLE001 - best-effort warm-up
            logger = get_app_logger() or _logging.getLogger(__name__)
            logger.debug("Prefetch of tenant route '%s' failed (deferred to read): %s", name, exc)


def prefetch_and_enforce_tenant_routing(context: Dict[str, Any]) -> None:
    """Warm all provider routes, then enforce ``enforce_authorization`` providers.

    A single entry point so ``authenticate_request`` can do both in one worker-thread
    hop. Prefetch runs first so the subsequent enforcement reads from the warm cache.
    """
    prefetch_tenant_routes(context)
    enforce_tenant_authorization(context)


def get_tenant_routing_property(key: str, *, provider: str) -> Optional[str]:
    """Return a single value from the matched tenant routing properties for a named provider.

    Routes are prefetched off-thread during authentication, so this call is normally a
    cache hit; an unprefetched provider is resolved lazily on first access. Returns
    ``None`` when there is no context, no matching route, or the named property is absent.

    Args:
        key: The property name in the route's ``properties`` dict.
        provider: The name passed to ``add_tenant_routing_provider()``.
    """
    context = get_request_context()
    if not context:
        return None

    route = _resolve_route(provider, context)
    if route is None:
        return None

    props = route.get("properties")
    if not isinstance(props, dict):
        return None
    value = props.get(key)
    if value is None:
        return None
    return str(value)


_secret_resolvers: list = []


def register_secret_resolver(fn) -> None:
    """Register a secret resolver for ``get_tenant_routing_secret()``.

    ``fn`` must be callable as ``fn(value: str) -> Optional[str]``: return the
    resolved plaintext when the value is a URI this resolver handles, or
    ``None`` to pass through to the next resolver. Resolvers are tried in
    registration order.

    Call at startup (e.g. in ``src/custom/server.py``). For Azure Key Vault,
    use the ready-made helper::

        from framework.contrib.azure import register_key_vault_resolver
        register_key_vault_resolver()
    """
    _secret_resolvers.append(fn)


def get_tenant_routing_secret(key: str, *, provider: str) -> str:
    """Return a resolved secret from the matched tenant routing properties for a named provider.

    Always returns a ``str`` — never ``None``.  Callers should treat ``""`` as
    "unavailable":

    - **Non-empty string** — the resolved secret (or the raw property value if no
      resolver handled it; plain values in dev/file-mode work without any resolver).
    - **``""``** — one of: no active request context, no routing rule matched this
      request, the ``key`` property is absent in the matched rule, or a resolver
      recognised the URI but failed (e.g. auth error, secret not found).

    **For resolver authors** — registered resolvers are tried in registration order.
    A resolver signals its intent by return value:

    - Return a string → resolved; chain stops, value is used.
    - Return ``None`` → "not my URI scheme"; chain continues to the next resolver.
    - Raise → "I recognised this URI but failed"; chain stops and ``""`` is returned.

    The raise-stops-chain behaviour is intentional: a resolver that recognises a URI
    but cannot fetch the secret should not fall back to returning the raw URI as a
    plain-text value.

    Args:
        key: The property name in the route's ``properties`` dict.
        provider: The name passed to ``add_tenant_routing_provider()``.
    """
    logger = get_app_logger()
    secret_ref = get_tenant_routing_property(key, provider=provider)
    if not secret_ref:
        return ""

    secret_ref = secret_ref.strip()
    if not secret_ref:
        return ""

    for resolver in _secret_resolvers:
        try:
            resolved = resolver(secret_ref)
            if resolved is not None:
                return resolved
        except Exception as exc:
            logger.warning("Secret resolver %s failed for property=%s: %s", resolver, key, exc)
            return ""

    return secret_ref
