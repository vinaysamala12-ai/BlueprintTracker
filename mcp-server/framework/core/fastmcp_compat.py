"""Helpers that paper over FastMCP's internal-component shapes.

Centralizes the small bits of introspection the framework needs against
FastMCP private/internal models (resource components, list-method
``run_middleware`` kwarg). When FastMCP changes those shapes, this is the
single file to update. ``requirements.txt`` pins a compatible release range.
"""

from __future__ import annotations

import inspect
from typing import Any


_RESOURCE_KEY_PREFIXES = ("resource:", "template:")


def resource_uri_key(component: Any) -> str:
    """Return the URI string for a FastMCP resource or resource template.

    Concrete resources expose ``uri``; templates expose ``uri_template`` (in
    FastMCP internals) or ``uriTemplate`` (over the MCP wire). When nothing
    matches, falls back to the FastMCP ``key`` attribute (format:
    ``"<prefix>:<uri>@<version>"`` with ``@`` always present per FastMCP's
    component contract), stripping the prefix and the version trailer.
    """
    for attr in ("uri", "uriTemplate", "uri_template"):
        value = getattr(component, attr, None)
        if value is not None:
            return str(value)

    key = getattr(component, "key", None)
    if isinstance(key, str):
        for prefix in _RESOURCE_KEY_PREFIXES:
            if key.startswith(prefix):
                return key[len(prefix):].rsplit("@", 1)[0]
        return key

    return str(component)


async def list_mcp_items_unfiltered(mcp: Any, method_name: str) -> list[Any]:
    """Call a FastMCP ``list_*`` method without running registered middleware.

    Returns ``[]`` when the method is missing on the installed FastMCP build.
    Older builds may not accept the ``run_middleware`` kwarg; this helper
    introspects the signature and only passes the kwarg when supported.
    """
    method = getattr(mcp, method_name, None)
    if not callable(method):
        return []

    try:
        sig = inspect.signature(method)
        kwargs = (
            {"run_middleware": False}
            if "run_middleware" in sig.parameters
            else {}
        )
    except (TypeError, ValueError):
        kwargs = {}
    return list(await method(**kwargs))
