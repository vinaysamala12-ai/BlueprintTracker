"""Decorator wrappers for MCP prompt functions.

Mirror the tool decorator pipeline (logging, auth, exception handling) but
operate on functions whose signature is the prompt's argument list (``**kwargs``)
rather than a single Pydantic ``params`` object.

Errors in prompts are logged and re-raised. FastMCP wraps them in
``PromptError`` and the MCP lowlevel handler emits ``ErrorData(code=0, ...)``
with a stringified message — clients receive an ``McpError`` they can read,
but the JSON-RPC code is not currently mapped (FastMCP 3.2.x). See
``tests/test_prompts.py::test_failing_prompt_raises_mcperror_to_client`` for
the lock-in.
"""

from __future__ import annotations

import functools
import logging
import time

from .logging import _format_token_claims_suffix, _get_token_claims_for_logging

from starlette.exceptions import HTTPException

from ..core.mcp_logging import emit_lifecycle_notification, mcp_log
from ..core.utils import get_app_logger
from ._common import authenticate_request, classify_error


def log_prompt_requests(func):
    """Add request/response logging to a prompt function. Mirrors ``log_requests``.

    Also emits per-call MCP ``notifications/message`` (debug-level) so clients
    can correlate prompt renders with their session transcripts. Notifications
    are tagged ``logger="prompt"``.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        logger = get_app_logger()
        is_debug = logger.isEnabledFor(logging.DEBUG)
        start = time.time()

        if is_debug:
            logger.debug(f"[PROMPT] === PROMPT REQUEST {func.__name__} === kwargs={kwargs}")
        else:
            logger.info(f"[PROMPT] Rendering prompt: {func.__name__}")

        await emit_lifecycle_notification(
            kind="prompt", name=func.__name__, phase="start"
        )

        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            elapsed_ms = round(elapsed * 1000, 3)
            if is_debug:
                logger.debug(
                    f"[PROMPT] Prompt {func.__name__} rendered in {elapsed:.3f}s"
                )
            else:
                token_claims_suffix = _format_token_claims_suffix(_get_token_claims_for_logging())
                logger.info(
                    f"[PROMPT] Prompt {func.__name__} rendered successfully in {elapsed:.3f}s{token_claims_suffix}"
                )
            await emit_lifecycle_notification(
                kind="prompt",
                name=func.__name__,
                phase="end",
                status="ok",
                elapsed_ms=elapsed_ms,
            )
            return result
        except Exception:
            elapsed = time.time() - start
            logger.info(
                f"[PROMPT] Prompt {func.__name__} failed after {elapsed:.3f}s{_format_token_claims_suffix(_get_token_claims_for_logging())}"
            )
            # Emission of the ERROR-level notification happens in
            # ``handle_prompt_exceptions``; this branch only re-raises so the
            # outer decorator can stamp the right error_class / error_kind.
            raise

    return wrapper


def require_api_key_prompt(func):
    """JWT/API-key auth for prompts. Shares ``authenticate_request`` with tools."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        await authenticate_request(kind="prompt")
        return await func(*args, **kwargs)

    return wrapper


def handle_prompt_exceptions(prompt_name: str):
    """Log framework errors, emit a diagnostic notification, and re-raise.

    FastMCP wraps the re-raised exception in ``PromptError``; the MCP lowlevel
    handler then emits ``ErrorData(code=0, ...)`` with the stringified message.

    Before re-raising, an ERROR-level ``notifications/message`` is emitted
    with the correlation ID, error class, and error kind so clients have an
    out-of-band diagnostic surface independent of the JSON-RPC error.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_app_logger()
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Auth rejections are logged by ``authenticate_request`` —
                # re-raise without a second log entry, and do not emit a
                # notifications/message (clients see the HTTP status directly).
                raise
            except Exception as exc:
                error_class = type(exc).__name__
                error_kind = classify_error(exc)
                logger.error(
                    f"{error_kind} in prompt {prompt_name}: {error_class}: {exc}"
                )
                await mcp_log(
                    "error",
                    f"{prompt_name}: {error_class}: {exc}",
                    logger_name="prompt",
                    data={
                        "prompt": prompt_name,
                        "error_class": error_class,
                        "error_kind": error_kind,
                    },
                )
                raise

        return wrapper

    return decorator
