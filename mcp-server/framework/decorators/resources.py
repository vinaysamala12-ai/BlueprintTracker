"""Decorator wrappers for MCP resource functions.

Phase 1 (errors / diagnostics) shape mirrors :mod:`prompts`:

- Read failures are logged and re-raised. FastMCP wraps the exception
  appropriately for the resources surface; clients see ``isError`` /
  ``McpError`` per spec.
- Per-call ``notifications/message`` is emitted (debug on start/end,
  error on failure) tagged ``logger="resource"`` so AIS can group
  diagnostics by URI without parsing free text.
- Stack traces stay in server logs only — never on the MCP wire.
"""

from __future__ import annotations

import functools
import logging
import time

from starlette.exceptions import HTTPException

from ..core.mcp_logging import emit_lifecycle_notification, mcp_log
from ..core.utils import get_app_logger
from .logging import _format_token_claims_suffix, _get_token_claims_for_logging
from ._common import authenticate_request, classify_error


def log_resource_requests(func):
    """Add request/response logging to a resource reader.

    Emits per-call MCP ``notifications/message`` (debug-level) on start
    and end so clients can correlate reads with their session transcripts.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        logger = get_app_logger()
        is_debug = logger.isEnabledFor(logging.DEBUG)
        start = time.time()

        if is_debug:
            logger.debug(
                f"[RESOURCE] === RESOURCE REQUEST {func.__name__} === args={args} kwargs={kwargs}"
            )
        else:
            logger.info(f"[RESOURCE] Reading resource: {func.__name__}")

        await emit_lifecycle_notification(
            kind="resource", name=func.__name__, phase="start"
        )

        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            elapsed_ms = round(elapsed * 1000, 3)
            if is_debug:
                logger.debug(f"[RESOURCE] Resource {func.__name__} read in {elapsed:.3f}s")
            else:
                token_claims_suffix = _format_token_claims_suffix(_get_token_claims_for_logging())
                logger.info(
                    f"[RESOURCE] Resource {func.__name__} read successfully in {elapsed:.3f}s{token_claims_suffix}"
                )
            await emit_lifecycle_notification(
                kind="resource",
                name=func.__name__,
                phase="end",
                status="ok",
                elapsed_ms=elapsed_ms,
            )
            return result
        except Exception:
            elapsed = time.time() - start
            logger.info(f"[RESOURCE] Resource {func.__name__} failed after {elapsed:.3f}s{_format_token_claims_suffix(_get_token_claims_for_logging())}")
            raise

    return wrapper


def require_api_key_resource(func):
    """JWT/API-key auth for resources. Shares auth with tools and prompts."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        await authenticate_request(kind="resource")
        return await func(*args, **kwargs)

    return wrapper


def handle_resource_exceptions(resource_name: str):
    """Log resource errors, emit a diagnostic notification, and re-raise.

    The re-raise lets FastMCP mark the read as failed; the
    ``notifications/message`` gives AIS an out-of-band diagnostic surface
    independent of the JSON-RPC error.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_app_logger()
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Auth rejections are logged by authenticate_request.
                raise
            except Exception as exc:
                error_class = type(exc).__name__
                error_kind = classify_error(exc, include_resource=True)
                logger.error(
                    f"{error_kind} in resource {resource_name}: {error_class}: {exc}"
                )
                await mcp_log(
                    "error",
                    f"{resource_name}: {error_class}: {exc}",
                    logger_name="resource",
                    data={
                        "resource": resource_name,
                        "error_class": error_class,
                        "error_kind": error_kind,
                    },
                )
                raise

        return wrapper

    return decorator
