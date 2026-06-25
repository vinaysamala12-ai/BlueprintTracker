"""Shared building blocks for tool and prompt decorators.

Tools and prompts run through identical authentication: Bearer JWT first,
API-key fallback second, dev bypass when no master key is configured. The
substantive logic lives here once; the thin wrappers in :mod:`auth` and
:mod:`prompts` adapt this helper to their respective call shapes
(``func(params)`` for tools, ``func(*args, **kwargs)`` for prompts).

Logging is intentionally NOT shared — tools emit full request/response detail
at DEBUG, prompts emit a single line. See :mod:`logging` and :mod:`prompts`.
"""

from __future__ import annotations

import asyncio as _asyncio

import jwt
from fastmcp.exceptions import ResourceError
from starlette.exceptions import HTTPException
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from ..core.config import get_mcp_master_api_key, get_mcp_master_api_key_name
from ..core.context import get_api_key_from_context, get_request_context
from ..core.utils import APIError, ToolExecutionError, ValidationError, get_app_logger

# Module-level JWKS client cache (keyed by JWKS URL) and its creation lock.
_jwks_clients: dict[str, object] = {}
_jwks_clients_lock = _asyncio.Lock()


def classify_error(exc: Exception, *, include_resource: bool = False) -> str:
    """Map a raised exception to one of the framework's error_kind strings.

    Returned values are stable wire-level strings consumed by clients
    (logged, embedded in error envelopes, mapped to JSON-RPC codes); change
    them only with a deliberate spec bump.

    Args:
        exc: The exception caught by a decorator.
        include_resource: When True, ``ResourceError`` maps to
            ``"resource_error"``. The tool path leaves it as
            ``"unexpected_error"`` because resource-specific exceptions
            cannot legitimately reach a tool body — preserving that means
            an operational alert when one does.
    """
    if include_resource and isinstance(exc, ResourceError):
        return "resource_error"
    if isinstance(exc, ValidationError):
        return "validation_error"
    if isinstance(exc, APIError):
        return "api_error"
    if isinstance(exc, ToolExecutionError):
        return "execution_error"
    if isinstance(exc, (HTTPException, PermissionError)):
        return "auth_error"
    return "unexpected_error"


async def _get_or_create_jwks_client(jwks_url: str) -> object:
    """Return a cached JWKS client for the given URL, creating it under a lock if absent."""
    from jwt import PyJWKClient
    from ..core.config import get_jwks_user_agent

    if jwks_url in _jwks_clients:
        return _jwks_clients[jwks_url]

    async with _jwks_clients_lock:
        if jwks_url not in _jwks_clients:
            headers = {"Accept": "application/json", "User-Agent": get_jwks_user_agent()}
            try:
                _jwks_clients[jwks_url] = PyJWKClient(jwks_url, headers=headers, timeout=5)
            except TypeError:
                # Backward compat for older PyJWT without headers/timeout args.
                _jwks_clients[jwks_url] = PyJWKClient(jwks_url)
    return _jwks_clients[jwks_url]


async def _enforce_tenant_gate(context, kind: str) -> None:
    """Run enforce_authorization providers for non-Bearer auth paths.

    API-key and dev-bypass requests have no JWT claims in context, so any
    provider whose schema uses token_claim() or issuer_info() will return no
    match — which is the correct outcome: enforce_authorization=True means a
    matching routing rule is required, and that requires a Bearer JWT.

    The route lookups may read routing rules from a file or Azure App
    Configuration, so they run in a worker thread to avoid blocking the event
    loop — and warming all provider routes here keeps later
    ``get_tenant_routing_property`` reads on this request non-blocking too.
    """
    from ..core.context import prefetch_and_enforce_tenant_routing
    from starlette.status import HTTP_403_FORBIDDEN as _403

    if context is None:
        return
    try:
        await _asyncio.to_thread(prefetch_and_enforce_tenant_routing, context)
    except PermissionError as exc:
        logger = get_app_logger()
        logger.warning(
            "enforce_authorization gate rejected non-Bearer %s request: %s", kind, exc
        )
        raise HTTPException(status_code=_403, detail=str(exc))


async def authenticate_request(*, kind: str) -> None:
    """Verify the active request and populate ``coid`` / ``uoid`` in context.

    Implements the framework's two-tier auth: Bearer JWT first, API-key
    fallback second, dev bypass when no master key is configured. Raises
    :class:`HTTPException` on rejection. ``kind`` is interpolated into log
    lines so operators can see whether the failure was on a tool or prompt
    path.
    """
    # Lazy imports keep module-level import graph identical to the develop
    # baseline, avoiding a utils/config circular-import at load time.
    from jwt import PyJWKClientError

    from ..core.config import (
        app_config,
        get_auth_bearer_required,
        get_auth_bearer_verify_expiry,
        get_auth_bearer_verify_issuer,
        get_auth_bearer_verify_signature,
    )
    from ..core.context import prefetch_and_enforce_tenant_routing

    logger = get_app_logger()

    # ── 1. JWT Bearer auth ────────────────────────────────────────────────────
    context = get_request_context()
    bearer_is_required = get_auth_bearer_required()

    if context is not None:
        auth_header = context.get("headers", {}).get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            try:
                verify_signature = get_auth_bearer_verify_signature()
                verify_issuer = get_auth_bearer_verify_issuer()
                verify_expiry = get_auth_bearer_verify_expiry()

                # Decode without verification first to read the issuer claim.
                unverified_payload = jwt.decode(
                    token,
                    options={
                        "verify_signature": False,
                        "verify_exp": False,
                        "verify_aud": False,
                        "verify_iss": False,
                    },
                )
                if not isinstance(unverified_payload, dict):
                    raise jwt.InvalidTokenError("Token payload must be a JSON object")

                issuer_url = str(unverified_payload.get("iss", "")).strip()
                # The iss claim is only needed to look up issuer config for
                # allowlist/signature verification. In legacy HAProxy-trust mode
                # (both off) a token without iss stays valid, as on develop.
                if not issuer_url and (verify_issuer or verify_signature):
                    logger.warning("Token missing required claim: iss")
                    raise HTTPException(
                        status_code=HTTP_401_UNAUTHORIZED,
                        detail="Token missing required claim: iss",
                    )

                # Load issuer configs once, off the event loop — the backing
                # provider may read a file or call Azure App Configuration.
                issuer_configs = await _asyncio.to_thread(lambda: dict(app_config.issuer_configs))
                issuer_config = issuer_configs.get(issuer_url) if issuer_url else None
                issuer_environment_map = {
                    url: str(cfg.get("issuer_environment", "")).strip()
                    for url, cfg in issuer_configs.items()
                    if str(cfg.get("issuer_environment", "")).strip()
                }
                issuer_audience = str(issuer_config.get("audience", "")).strip() if issuer_config else ""

                decode_kwargs: dict = {
                    "options": {
                        "verify_signature": verify_signature,
                        "verify_iss": False,
                        "verify_aud": bool(issuer_audience),
                        "verify_exp": verify_expiry,
                    }
                }
                if issuer_audience:
                    decode_kwargs["audience"] = issuer_audience

                if verify_issuer:
                    if not issuer_environment_map:
                        logger.error(
                            "Token config source requires issuer verification but no issuer mappings were loaded"
                        )
                        raise HTTPException(
                            status_code=HTTP_401_UNAUTHORIZED,
                            detail="Server JWT auth is misconfigured: no issuer mappings were loaded",
                        )
                    if not issuer_url or not issuer_config:
                        logger.warning("Issuer is not configured: %s", issuer_url or "<missing>")
                        raise HTTPException(
                            status_code=HTTP_401_UNAUTHORIZED,
                            detail="Token issuer is not allowed",
                        )

                if verify_signature:
                    if not issuer_config:
                        logger.warning(
                            "Token issuer is not allowed (verify_signature enabled): issuer_url=%s",
                            issuer_url or "<missing>",
                        )
                        raise HTTPException(
                            status_code=HTTP_401_UNAUTHORIZED,
                            detail="Token issuer is not allowed",
                        )
                    jwks_url = str(issuer_config.get("jwks_url", "")).strip()
                    if not jwks_url:
                        logger.error(
                            "Token config requires signature verification but issuer %s has no jwks_url",
                            issuer_url,
                        )
                        raise HTTPException(
                            status_code=HTTP_401_UNAUTHORIZED,
                            detail="Server JWT auth is misconfigured: issuer jwks_url is missing",
                        )
                    try:
                        _jwks_client = await _get_or_create_jwks_client(jwks_url)
                        signing_key = await _asyncio.to_thread(
                            _jwks_client.get_signing_key_from_jwt, token
                        )
                    except (PyJWKClientError, jwt.InvalidTokenError) as exc:
                        logger.warning("Failed to resolve signing key from JWKS: %s", exc)
                        raise HTTPException(
                            status_code=HTTP_401_UNAUTHORIZED,
                            detail="Invalid token: unable to resolve signing key",
                        )
                    decode_kwargs["key"] = signing_key.key
                    algorithms = [a for a in issuer_config.get("algorithms", ["RS256"]) if str(a).lower() != "none"]
                    decode_kwargs["algorithms"] = algorithms or ["RS256"]
                else:
                    decode_kwargs["key"] = ""

                payload = jwt.decode(token, **decode_kwargs)

                coid = payload.get("coid")
                email = payload.get("email")
                uoid = payload.get("uoid")

                if not coid:
                    if verify_issuer:
                        logger.debug("Token missing claim: coid")
                    else:
                        logger.error("Token missing required claim: coid")
                        raise HTTPException(
                            status_code=HTTP_401_UNAUTHORIZED,
                            detail="Token missing required claim: coid",
                        )
                if not uoid:
                    if verify_issuer:
                        logger.debug("Token missing claim: uoid")
                    else:
                        logger.error("Token missing required claim: uoid")
                        raise HTTPException(
                            status_code=HTTP_401_UNAUTHORIZED,
                            detail="Token missing required claim: uoid",
                        )

                issuer_environment = issuer_environment_map.get(issuer_url)
                if issuer_environment_map and not issuer_environment:
                    logger.warning("Issuer is not configured: %s", issuer_url)
                    raise HTTPException(
                        status_code=HTTP_401_UNAUTHORIZED,
                        detail="Token issuer is not allowed",
                    )

                if coid:
                    context["coid"] = coid
                if uoid:
                    context["uoid"] = uoid
                if email:
                    context["email"] = email
                if issuer_url:
                    context["issuer_url"] = issuer_url
                if issuer_environment:
                    context["issuer_environment"] = issuer_environment
                context["authorization_token"] = token

                try:
                    # Route lookups read rules from file / App Config; warm all
                    # provider routes and enforce authorization off the event loop
                    # so later get_tenant_routing_property() reads never block it.
                    await _asyncio.to_thread(prefetch_and_enforce_tenant_routing, context)
                except PermissionError as exc:
                    raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail=str(exc))

                return

            except jwt.InvalidTokenError as exc:
                logger.warning("Invalid JWT token (%s): %s", kind, exc)
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token: {exc}",
                )

    # ── 2. Dev bypass / API-key fallback ─────────────────────────────────────
    master_key = get_mcp_master_api_key()

    # Token-config mode (issuer validation active) requires Bearer JWT regardless
    # of whether MCP_MASTER_API_KEY is configured. This check must come before
    # the dev-bypass so a keyless dev environment still enforces JWT auth when
    # MCP_TOKEN_CONFIG_SOURCE is set.
    if bearer_is_required:
        logger.warning(
            "Missing Bearer token while token-config mode requires JWT authentication (%s)", kind
        )
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token in Authorization header",
        )

    if not master_key:
        logger.warning("No MCP_MASTER_API_KEY set. Bypassing %s authentication.", kind)
        await _enforce_tenant_gate(context, kind)
        return

    provided = get_api_key_from_context()
    header_name = get_mcp_master_api_key_name()
    if provided and provided == master_key:
        await _enforce_tenant_gate(context, kind)
        return
    if provided:
        logger.warning("Invalid API key received")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"Invalid API key provided in '{header_name}' header.",
        )
    logger.warning("Missing authentication. No Bearer token or API key found.")
    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN,
        detail=(
            f"Missing authentication. Provide a Bearer token or API key in the "
            f"'{header_name}' header."
        ),
    )
