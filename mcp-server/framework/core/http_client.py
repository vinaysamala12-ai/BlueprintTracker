"""Shared httpx.AsyncClient managed by the FastMCP server lifespan.

Tool code that fans out to downstream Aptean APIs should reuse a single pooled
client instead of constructing a new one per request. This module exposes:

* ``shared_http_lifespan`` — an ``asynccontextmanager`` wired into
  ``FastMCP(lifespan=...)``. It constructs the pooled client once at server
  startup and closes it at shutdown.
* ``get_shared_http_client`` — accessor for tool code. Raises clearly when the
  lifespan has not started, which protects against accidental use outside the
  server process (e.g. in unit tests that do not boot the lifespan).

Headers are not attached to the client — per-request identity is added at the
call site via ``get_outbound_headers()``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

import httpx

from .config import app_config
from .utils import get_app_logger

_shared_client: Optional[httpx.AsyncClient] = None


def get_shared_http_client() -> httpx.AsyncClient:
    """Return the framework-managed ``httpx.AsyncClient``.

    Raises:
        RuntimeError: the lifespan has not started. Construct your own client
            (or mock) for unit tests that do not run the server.
    """
    if _shared_client is None:
        raise RuntimeError(
            "Shared HTTP client is not initialised. The FastMCP lifespan owns "
            "this client; it is only available while the server is running."
        )
    return _shared_client


@asynccontextmanager
async def shared_http_lifespan(_server):
    """Own a pooled ``httpx.AsyncClient`` for the server's lifetime.

    Timeouts, connection limits, and the retry stance are read from
    ``app_config`` so operators can tune them via environment variables
    without touching the framework code.
    """
    global _shared_client
    logger = get_app_logger()

    timeout = httpx.Timeout(app_config.http_client_timeout_seconds)
    limits = httpx.Limits(
        max_connections=app_config.http_client_max_connections,
        max_keepalive_connections=app_config.http_client_max_keepalive,
    )

    _shared_client = httpx.AsyncClient(timeout=timeout, limits=limits)
    if logger:
        logger.info(
            f"Shared HTTP client initialised "
            f"(timeout={app_config.http_client_timeout_seconds}s, "
            f"max_connections={app_config.http_client_max_connections})"
        )

    try:
        yield
    finally:
        client = _shared_client
        _shared_client = None
        if client is not None:
            await client.aclose()
            if logger:
                logger.info("Shared HTTP client closed")
