"""Decorators package for MCP server."""

from .auth import require_api_key
from .logging import log_requests
from .exceptions import handle_exceptions
from .prompts import (
    log_prompt_requests,
    require_api_key_prompt,
    handle_prompt_exceptions,
)
from .resources import (
    log_resource_requests,
    require_api_key_resource,
    handle_resource_exceptions,
)

__all__ = [
    "require_api_key",
    "log_requests",
    "handle_exceptions",
    "log_prompt_requests",
    "require_api_key_prompt",
    "handle_prompt_exceptions",
    "log_resource_requests",
    "require_api_key_resource",
    "handle_resource_exceptions",
]
