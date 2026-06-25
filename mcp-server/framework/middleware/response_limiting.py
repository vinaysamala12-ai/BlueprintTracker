"""Response-size limiting middleware.

FastMCP versions before the newer response-limiting middleware do not ship
``fastmcp.server.middleware.response_limiting``. This local implementation
keeps the framework wiring stable and applies a conservative text-content
truncation to tool results.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware


class ResponseLimitingMiddleware(Middleware):
    """Truncate oversized text content returned from tool calls."""

    def __init__(self, max_size: int):
        self.max_size = max_size

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        result = await call_next(context)
        return self._truncate_result(result)

    def _truncate_result(self, result: Any) -> Any:
        content = getattr(result, "content", None)
        if not isinstance(content, list):
            return result

        total = sum(
            len(block.text.encode("utf-8"))
            for block in content
            if isinstance(getattr(block, "text", None), str)
        )
        if total <= self.max_size:
            return result

        suffix = "\n\n[response truncated]"
        budget = max(self.max_size - len(suffix.encode("utf-8")), 0)
        used = 0
        truncated = False
        new_content = []

        for block in content:
            text = getattr(block, "text", None)
            if truncated:
                continue
            if not isinstance(text, str):
                new_content.append(block)
                continue

            encoded = text.encode("utf-8")
            remaining = max(budget - used, 0)
            if len(encoded) <= remaining:
                new_content.append(block)
                used += len(encoded)
                continue

            clipped = encoded[:remaining].decode("utf-8", errors="ignore") + suffix
            if hasattr(block, "model_copy"):
                new_content.append(block.model_copy(update={"text": clipped}))
            else:
                block.text = clipped
                new_content.append(block)
            truncated = True

        if not new_content:
            return result

        result.content = new_content
        # Structured content can be as large as the original payload. Drop it
        # once truncation occurs so the MCP response is actually bounded.
        if hasattr(result, "structured_content"):
            result.structured_content = None
        return result
