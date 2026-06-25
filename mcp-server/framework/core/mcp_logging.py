"""MCP `notifications/message` emission helper.

The MCP 2025-11-25 spec defines a server→client logging channel
(`notifications/message`) that this framework uses to surface per-call
diagnostics — request lifecycle, errors, and structured metadata — to
clients (e.g. AIS) without bleeding details into the LLM-visible response.

Notifications emitted via :func:`mcp_log` reach the connected client only
when there is an active FastMCP request context (per-call, by design — the
server runs short-lived MCP sessions per spec). Outside an active context
the call is a server-side no-op so unit tests and background tasks need
no special-casing.

FastMCP honors `logging/setLevel` automatically: notifications below the
client's selected minimum severity are dropped before they hit the wire.

Two correlation IDs ride alongside every emitted message:

- ``correlation_id`` — the inbound HTTP-header trace ID (or its
  server-generated UUID fallback). Cross-system pivot key.
- ``mcp_diagnostic_id`` — AIS-supplied per-call ID from
  ``params._meta.mcp_diagnostic_id``. Routes the notification to the right
  Studio diagnostics record. Both keys are included in ``data.extra`` for
  easy inspection AND in ``params._meta`` per the AIS spec, so clients can
  use either pivot.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import mcp.types as mcp_types
from fastmcp.server.dependencies import get_context

from .config import get_mcp_master_api_key_name
from .context import get_correlation_id, get_mcp_diagnostic_id
from .utils import get_app_logger


_REDACT = "***"
# Headers / key names that always carry credentials; never echoed into
# notifications. Matched case-insensitively as a *whole word* (so e.g.
# ``cookie`` matches ``Cookie`` but not ``cookieMonster``). Kept in sync
# with the "Sanitization" bullet under "Diagnostics" in OPERATIONS.md.
_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie"}
# Generic key fragments — redacted whenever the lowercased key contains any
# of these substrings (regardless of position / casing). Also documented in
# OPERATIONS.md under the same "Sanitization" bullet; if you add or remove a
# fragment here, update the doc in the same change.
_SENSITIVE_KEY_FRAGMENTS = ("token", "secret", "password", "api_key", "apikey")


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    if lower in _SENSITIVE_HEADERS:
        return True
    if lower == get_mcp_master_api_key_name().lower():
        return True
    return any(fragment in lower for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _sanitize(value: Any) -> Any:
    """Redact credentials from arbitrary log payloads.

    Recurses dicts and lists. Strings are passed through (we do not attempt
    to detect tokens in free text — server-side application logs are the
    place for that).
    """
    if isinstance(value, dict):
        return {
            k: _REDACT if _is_sensitive_key(str(k)) else _sanitize(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


async def emit_lifecycle_notification(
    *,
    kind: str,
    name: str,
    phase: str,
    elapsed_ms: Optional[float] = None,
    status: Optional[str] = None,
) -> None:
    """Shared start/end debug-level notification emitter.

    The tool, prompt, and resource decorators each emit identical-shape
    lifecycle notifications around their wrapped function. This helper is
    the single source of truth for the on-wire payload — the per-decorator
    callsites only supply ``kind`` (``"tool"`` / ``"prompt"`` / ``"resource"``)
    and the function name.
    """
    data: dict[str, Any] = {kind: name, "phase": phase}
    if status is not None:
        data["status"] = status
    if elapsed_ms is not None:
        data["elapsed_ms"] = elapsed_ms
    suffix = "started" if phase == "start" else status or phase
    await mcp_log(
        "debug",
        f"{kind} {name} {suffix}",
        logger_name=kind,
        data=data,
    )


async def mcp_log(
    level: str,
    message: str,
    *,
    logger_name: Optional[str] = None,
    data: Optional[Mapping[str, Any]] = None,
) -> None:
    """Emit an MCP ``notifications/message`` to the connected client.

    Args:
        level: One of ``"debug"``, ``"info"``, ``"notice"``, ``"warning"``,
            ``"error"``, ``"critical"``, ``"alert"``, ``"emergency"`` per the
            MCP spec. Lower-severity messages are dropped client-side when a
            higher minimum is set via ``logging/setLevel``.
        message: Human-readable message string. Stack traces stay in server
            logs only — never embed them here.
        logger_name: Optional category tag (``"tool"`` / ``"prompt"`` /
            ``"resource"``) so clients can group related notifications.
        data: Optional structured payload merged into ``extra``. Keys that
            look like credentials are redacted before send.

    The notification carries ``correlation_id`` and ``mcp_diagnostic_id``
    (when set on the active request) in two places: inside ``data.extra``
    (so existing clients see them via the legacy fallback path AIS
    documents) AND on the JSON-RPC ``params._meta`` envelope (the AIS-
    preferred routing channel).

    Failure to emit (e.g. transport closed mid-call) is logged at debug
    level and swallowed — diagnostic notifications must never fail a tool
    call. Outside an active MCP request context the call is a no-op.
    """
    try:
        ctx = get_context()
    except RuntimeError:
        return

    extra: dict[str, Any] = {}
    correlation_id = get_correlation_id()
    diagnostic_id = get_mcp_diagnostic_id()
    if correlation_id:
        extra["correlation_id"] = correlation_id
    if diagnostic_id:
        extra["mcp_diagnostic_id"] = diagnostic_id
    if data:
        extra.update(_sanitize(dict(data)))

    notification_meta: dict[str, Any] = {}
    if diagnostic_id:
        notification_meta["mcp_diagnostic_id"] = diagnostic_id
    if correlation_id:
        notification_meta["correlation_id"] = correlation_id

    try:
        if notification_meta:
            await _send_notification_with_meta(
                ctx,
                level=level,
                message=message,
                logger_name=logger_name,
                extra=extra or None,
                notification_meta=notification_meta,
            )
        else:
            # No diagnostic IDs in scope (e.g. unauthenticated probe before
            # middleware ran). Fall back to FastMCP's helper which handles
            # the standard send_log_message path.
            await ctx.log(
                message=message,
                level=level,  # type: ignore[arg-type]  # FastMCP narrows to LoggingLevel
                logger_name=logger_name,
                extra=extra or None,
            )
    except Exception:
        get_app_logger().debug(
            "Failed to emit MCP notifications/message", exc_info=True
        )


async def _send_notification_with_meta(
    ctx: Any,
    *,
    level: str,
    message: str,
    logger_name: Optional[str],
    extra: Optional[Mapping[str, Any]],
    notification_meta: Mapping[str, Any],
) -> None:
    """Bypass FastMCP's ``send_log_message`` so we can stamp ``params._meta``.

    The MCP SDK helper does not accept ``_meta``; the spec defines it on
    every notification's params. AIS reads ``params._meta.mcp_diagnostic_id``
    to route notifications to the right diagnostics record, so we have to
    construct the notification by hand.

    Two routing requirements ride on top of that:

    1. **``related_request_id``** — under Streamable HTTP, the MCP SDK uses
       this to route per-call notifications onto the active POST response
       stream. Notifications without it are pushed to the standalone GET
       stream, which POST-only clients (the common AIS deployment shape)
       never consume. ``ctx.log`` passes ``ctx.origin_request_id`` for this
       reason; we mirror that so the routing properties of the standard
       log path are preserved when we take the ``_meta``-stamping path.
    2. **Minimum-level filtering.** FastMCP applies the client's
       ``logging/setLevel`` floor in ``ctx.log``; we re-apply the same
       gate here so ``setLevel`` is honored on this path too.
    """
    if not _passes_min_level(ctx, level):
        return

    data_payload: dict[str, Any] = {"msg": message}
    if extra:
        data_payload["extra"] = dict(extra)

    notification = mcp_types.LoggingMessageNotification(
        method="notifications/message",
        params=mcp_types.LoggingMessageNotificationParams(
            level=level,  # type: ignore[arg-type]
            logger=logger_name,
            data=data_payload,
            _meta=mcp_types.NotificationParams.Meta(**notification_meta),  # type: ignore[call-arg]
        ),
    )
    # Route over the active request's response stream by attaching
    # ``related_request_id``. Going through ``ctx.session.send_notification``
    # (rather than ``ctx.send_notification``) is required because the
    # FastMCP helper does not expose the related-request-id parameter.
    related_request_id = getattr(ctx, "origin_request_id", None)
    await ctx.session.send_notification(
        mcp_types.ServerNotification(notification),
        related_request_id=related_request_id,
    )


_MCP_LEVEL_SEVERITY = {
    "debug": 0,
    "info": 1,
    "notice": 2,
    "warning": 3,
    "error": 4,
    "critical": 5,
    "alert": 6,
    "emergency": 7,
}


def _passes_min_level(ctx: Any, level: str) -> bool:
    """Mirror FastMCP's ``_log_to_server_and_client`` minimum-level gate.

    Returns False when the level is below the client's ``logging/setLevel``
    floor (or the server's configured floor). Defensive on attribute lookups
    so a future FastMCP refactor doesn't break diagnostics emission.

    Both attribute names probed below
    (``session._minimum_logging_level`` and
    ``session.fastmcp.client_log_level``) are FastMCP-internal. They are
    legitimately ``None`` until the client sends a ``logging/setLevel``,
    so a ``None`` return is **not** a drift signal — we fail-open in that
    case and don't warn. We DO warn (once, then stay silent) when:

    * Neither attribute *name* exists on the session at all — a rename
      would manifest this way, so it's worth flagging.
    * A probe raises — exceptional, but a sturdy upgrade signal.
    """
    session = None
    try:
        session = getattr(ctx, "session", None)
        if session is None:
            return True
        if not _session_has_min_level_attr(session):
            _warn_min_level_drift_once(session)
            return True
        min_level = getattr(session, "_minimum_logging_level", None)
        if min_level is None:
            fastmcp = getattr(session, "fastmcp", None)
            min_level = getattr(fastmcp, "client_log_level", None)
        if min_level is None:
            return True
        return _MCP_LEVEL_SEVERITY.get(level, 0) >= _MCP_LEVEL_SEVERITY.get(
            min_level, 0
        )
    except Exception:
        get_app_logger().warning(
            "Failed to read FastMCP minimum-log-level on session of type %s "
            "— diagnostics level filtering will fail-open until restart. "
            "Check ``_passes_min_level`` in framework/core/mcp_logging.py "
            "if this persists across a FastMCP upgrade.",
            type(session).__name__ if session is not None else "<unknown>",
            exc_info=True,
        )
        return True


def _session_has_min_level_attr(session: Any) -> bool:
    """True iff at least one of the probed names resolves on the session.

    Uses ``hasattr`` rather than reading the value so we can distinguish
    "attribute exists but is currently ``None``" (normal) from "attribute
    name has been renamed away" (drift).
    """
    if hasattr(session, "_minimum_logging_level"):
        return True
    fastmcp = getattr(session, "fastmcp", None)
    return fastmcp is not None and hasattr(fastmcp, "client_log_level")


# One-shot guard so we don't spam server logs on every call once drift is
# detected. The first occurrence is enough to alert operators.
_min_level_drift_warning_logged = False


def _warn_min_level_drift_once(session: Any) -> None:
    global _min_level_drift_warning_logged
    if _min_level_drift_warning_logged:
        return
    _min_level_drift_warning_logged = True
    get_app_logger().warning(
        "Neither ``session._minimum_logging_level`` nor "
        "``session.fastmcp.client_log_level`` exists on a session of "
        "type %s. The framework probes these FastMCP-internal "
        "attributes to honour ``logging/setLevel``; their absence "
        "almost certainly means a FastMCP upgrade renamed them. "
        "Diagnostics-level filtering is now fail-open (every "
        "notification is sent regardless of client setLevel). Update "
        "``_passes_min_level`` in framework/core/mcp_logging.py to "
        "the new attribute names.",
        type(session).__name__,
    )
