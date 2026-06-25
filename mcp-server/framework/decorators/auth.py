"""API key and JWT Bearer authentication decorator for MCP tool functions."""

import functools

from ._common import authenticate_request


def require_api_key(func):
    """
    Decorator to protect a tool with authentication.

    Supports two auth methods (checked in order):
    1. Bearer JWT in the Authorization header — decodes the token, stores
       ``coid`` and ``uoid`` claims in request context, and forwards the raw
       token so tools can pass it downstream via ``get_outbound_headers()``.
    2. API key in the configured header (legacy / fallback).

    Shares the underlying ``authenticate_request`` helper with
    :func:`require_api_key_prompt` so the two pipelines cannot drift apart.
    """
    @functools.wraps(func)
    async def wrapper(params):
        await authenticate_request(kind="tool")
        return await func(params)

    return wrapper
