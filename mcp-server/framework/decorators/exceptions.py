"""Exception handling decorator for MCP server tools.

Phase 1 (errors / diagnostics) shape:

- Exceptions raised by tool bodies are **re-raised** (wrapped in
  ``ToolError``) so the lowlevel MCP handler marks the response with
  ``isError: true``. The previous behavior of returning ``{"error": "..."}``
  dicts hid failures from the client and forced the agent loop to infer
  errors from response shape. Re-raising is the spec-aligned path.
- The LLM-visible error content is a JSON object containing the error
  message, error class, error kind (validation / api / execution /
  unexpected), correlation_id, and the failing tool name — strictly more
  informative than the legacy single-string dict.
- Per-call ``notifications/message`` is emitted before the re-raise so
  clients (e.g. AIS) get an out-of-band diagnostic surface tagged
  ``logger="tool"`` that the LLM never sees.
- On success, the wrapper returns a :class:`ToolResult` with
  ``_meta.correlation_id`` and ``_meta.elapsed_ms`` — the response envelope
  metadata clients use to correlate transcripts with server-side traces.
"""

from __future__ import annotations

import functools
import json
import time
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult

from ..core.context import get_correlation_id, get_mcp_diagnostic_id
from ..core.mcp_logging import mcp_log
from ..core.utils import get_app_logger
from ._common import classify_error


def _build_meta(
    elapsed_ms: float,
    correlation_id: str | None,
    mcp_diagnostic_id: str | None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"elapsed_ms": elapsed_ms}
    if correlation_id:
        meta["correlation_id"] = correlation_id
    if mcp_diagnostic_id:
        meta["mcp_diagnostic_id"] = mcp_diagnostic_id
    return meta


def handle_exceptions(tool_name: str):
    """Standardised tool-level exception handling and per-call diagnostics.

    Args:
        tool_name: The registered tool name; embedded in error payloads and
            in the ``notifications/message`` emitted on failure so clients
            can route diagnostics without parsing free text.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(params):
            logger = get_app_logger()
            start = time.time()
            try:
                result = await func(params)
            except Exception as exc:
                elapsed_ms = round((time.time() - start) * 1000, 3)
                error_class = type(exc).__name__
                error_kind = classify_error(exc)
                correlation_id = get_correlation_id()
                mcp_diagnostic_id = get_mcp_diagnostic_id()

                logger.error(
                    f"{error_kind} in tool {tool_name}: {error_class}: {exc}"
                )

                payload: dict[str, Any] = {
                    "tool": tool_name,
                    "error": str(exc),
                    "error_class": error_class,
                    "error_kind": error_kind,
                    "elapsed_ms": elapsed_ms,
                }
                if correlation_id:
                    payload["correlation_id"] = correlation_id
                if mcp_diagnostic_id:
                    payload["mcp_diagnostic_id"] = mcp_diagnostic_id

                await mcp_log(
                    "error",
                    f"{tool_name}: {error_class}: {exc}",
                    logger_name="tool",
                    data={
                        "tool": tool_name,
                        "error_class": error_class,
                        "error_kind": error_kind,
                        "elapsed_ms": elapsed_ms,
                    },
                )

                # ToolError is a FastMCPError, so FastMCP's call_tool path
                # re-raises it without re-wrapping. The lowlevel handler then
                # converts it to CallToolResult(isError=True, content=[...
                # text=str(ToolError) ...]). The framework's
                # ``_install_call_tool_meta_handler`` parses that JSON back
                # out and reshapes the response per AIS's error envelope spec
                # (human-readable text + structured ``_meta``).
                raise ToolError(
                    json.dumps(payload, sort_keys=True, separators=(",", ":"))
                ) from exc

            elapsed_ms = round((time.time() - start) * 1000, 3)
            correlation_id = get_correlation_id()
            mcp_diagnostic_id = get_mcp_diagnostic_id()

            structured = (
                result.model_dump() if hasattr(result, "model_dump") else result
            )
            meta = _build_meta(elapsed_ms, correlation_id, mcp_diagnostic_id)

            if isinstance(structured, dict):
                return ToolResult(structured_content=structured, meta=meta)
            # Non-dict returns are rare in this framework (tool_dump() is the
            # convention) but bytes / lists / scalars must still flow through;
            # ToolResult.meta on a non-dict still surfaces _meta on the wire.
            return ToolResult(content=structured, meta=meta)

        return wrapper

    return decorator
