"""Server factory and utilities for MCP server creation."""

from .factory import (
    create_mcp_server,
    register_tool,
    register_prompt,
    register_resource,
    register_resource_template,
    get_mcp_server,
    auto_discover_domains,
)

__all__ = [
    "create_mcp_server",
    "register_tool",
    "register_prompt",
    "register_resource",
    "register_resource_template",
    "get_mcp_server",
    "auto_discover_domains",
]
