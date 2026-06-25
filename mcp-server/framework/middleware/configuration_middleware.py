"""FastMCP middleware that filters MCP surfaces based on the active configuration.

When a client sends an ``X-APTEAN-MCP-TOOLSETS`` header, this middleware:

1. **on_list_tools** — returns the union of tools from every configuration
   named in the header (comma-separated values are supported).
2. **on_call_tool** — rejects calls to tools not in any of those configurations.
3. **on_list_prompts** — returns the union of prompts from every matched
   configuration. A configuration with no ``prompts`` field is unrestricted
   and exposes all prompts (backward-compatible default).
4. **on_get_prompt** — rejects ``prompts/get`` for prompts not in any matched
   configuration.
5. **on_list_resources / on_list_resource_templates** — filters resources and
   templates using the optional ``resources`` field.
6. **on_read_resource** — rejects reads outside the matched resource allowlist.

If no configuration header is sent, all tools, prompts, and resources are visible
(default). Unknown and inactive names in a comma-separated list are silently
dropped and logged; the remaining names still take effect. If every requested
name is unknown/inactive, the request fails closed (empty list,
``PermissionError`` on call). If configuration filtering is disabled because
no valid configuration source is available, the header is ignored and all
tools, prompts, and resources remain visible.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from fastmcp.resources.template import match_uri_template
from fastmcp.server.middleware import Middleware
from fastmcp.server.dependencies import get_http_request

from ..core.fastmcp_compat import resource_uri_key
from ..core.mcp_configuration import (
    CONFIGURATION_HEADER,
    ConfigurationProvider,
    ConfigurationProviderStatus,
    MCPConfiguration,
)
from ..core.utils import get_app_logger


def _logger() -> logging.Logger:
    return get_app_logger() or logging.getLogger(__name__)


class ConfigurationMiddleware(Middleware):
    """Filter list/get/call operations based on the active configuration header."""

    def __init__(self, provider: ConfigurationProvider):
        self._provider = provider

    # ------------------------------------------------------------------
    # Header extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _get_configuration_names() -> list[str]:
        """Read the X-APTEAN-MCP-TOOLSETS header and return its names.

        The header value is a comma-separated list; whitespace is trimmed and
        empty entries are dropped. Returns an empty list if no header is
        present or the request is not HTTP (e.g. stdio transport).
        """
        try:
            request = get_http_request()
        except RuntimeError:
            return []

        for key, value in request.headers.items():
            if key.lower() == CONFIGURATION_HEADER:
                return [part.strip() for part in value.split(",") if part.strip()]
        return []

    async def _resolve_configurations(
        self,
    ) -> tuple[list[str], list[MCPConfiguration], ConfigurationProviderStatus]:
        """Resolve header names to active configurations.

        Returns ``(requested_names, matched_active_configs, provider_status)``.
        Unknown names and inactive configurations are dropped from the matched
        list — callers are expected to log or reject based on both fields.
        """
        requested = self._get_configuration_names()
        status = await self._provider.get_status()
        if not requested or not status.enabled:
            return requested, [], status

        all_configs = await self._provider.load_configurations()
        matched: list[MCPConfiguration] = []
        for name in requested:
            config = all_configs.get(name.upper())
            if config is None or not config.active:
                continue
            matched.append(config)
        return requested, matched, status

    @staticmethod
    def _dropped_names(
        requested: list[str], matched: list[MCPConfiguration]
    ) -> list[str]:
        """Return the names in ``requested`` that did not resolve to an active config."""
        matched_upper = {c.name.upper() for c in matched}
        return [name for name in requested if name.upper() not in matched_upper]

    @staticmethod
    def _union_of(
        configs: list[MCPConfiguration],
        attr: str,
        *,
        allow_none_wildcard: bool,
    ) -> frozenset[str] | None:
        """Union the uppercase ``attr`` name-sets from matched configurations.

        ``attr`` is ``"tools"``, ``"prompts"``, or ``"resources"``. The
        ``None`` wildcard is opt-in via ``allow_none_wildcard``:

        * Prompts/resources pass ``allow_none_wildcard=True``: a configuration
          whose field is ``None`` (the JSON omitted the key) is treated as
          unrestricted — back-compat for legacy configuration files.
          ``None`` is returned in that case so callers know to skip filtering.
        * Tools pass ``allow_none_wildcard=False``: ``tools=None`` is invalid
          (the dataclass declares ``tools: frozenset[str]``). If a custom
          provider violates that contract, this method coerces ``None`` to an
          empty set so the matched configuration contributes nothing — the
          request fails closed instead of silently exposing every tool.
        """
        result: set[str] = set()
        for config in configs:
            value = getattr(config, attr)
            if value is None:
                if allow_none_wildcard:
                    return None
                _logger().error(
                    f"Configuration '{config.name}' has {attr}=None — "
                    f"treating as deny-all (provider contract violation)"
                )
                continue
            result.update(value)
        return frozenset(result)

    @staticmethod
    def _name_key(item: Any) -> str:
        return item.name.upper()

    @staticmethod
    def _resource_key(item: Any) -> str:
        return resource_uri_key(item)

    @staticmethod
    def _resource_uri_from_context(context: Any) -> str:
        return str(context.message.uri)

    @staticmethod
    def _resource_is_allowed(uri: str, allowed: frozenset[str]) -> bool:
        if uri in allowed:
            return True
        for candidate in allowed:
            if "{" not in candidate:
                continue
            try:
                if match_uri_template(uri, candidate):
                    return True
            except Exception as exc:
                # Operator-visible: a fat-fingered allowlist entry silently
                # never grants reads, which is hard to debug from request logs.
                _logger().warning(
                    f"Skipping malformed resource template allowlist entry "
                    f"{candidate!r}: {exc}"
                )
                continue
        return False

    async def _filter_list(
        self,
        *,
        kind: str,
        attr: str,
        all_items: Sequence[Any],
        allow_none_wildcard: bool,
        item_key: Callable[[Any], str],
        is_allowed: Callable[[str, frozenset[str]], bool] | None = None,
    ) -> Sequence[Any]:
        """Shared body for list hooks.

        Returns the unmodified ``all_items`` when no scoping applies (no
        header, provider disabled, or — for prompts and resources — any
        matched configuration is unrestricted). Returns ``[]`` if every
        requested name is unknown/inactive (fail-closed). Otherwise returns
        the items whose configured key is in the union of allowed sets.
        """
        requested, matched, provider_status = await self._resolve_configurations()
        if not requested or not provider_status.enabled:
            return all_items

        logger = _logger()
        dropped = self._dropped_names(requested, matched)
        if dropped:
            logger.warning(
                f"Ignoring unknown or inactive configurations ({kind}s): {dropped}"
            )

        if not matched:
            logger.warning(
                f"No active configurations matched {requested} — "
                f"returning empty {kind} list"
            )
            return []

        allowed = self._union_of(matched, attr, allow_none_wildcard=allow_none_wildcard)
        matched_names = [c.name for c in matched]
        if allowed is None:
            logger.info(
                f"MCP configurations {matched_names}: "
                f"{kind}s unrestricted — exposing all {len(all_items)} {kind}(s)"
            )
            return all_items

        allowed_check = is_allowed or (lambda key, allowed_set: key in allowed_set)
        filtered = [item for item in all_items if allowed_check(item_key(item), allowed)]
        logger.info(
            f"MCP configurations {matched_names}: "
            f"exposing {len(filtered)}/{len(all_items)} {kind}(s)"
        )
        return filtered

    async def _guard_call(
        self,
        *,
        kind: str,
        attr: str,
        operation: str,
        context: Any,
        call_next: Any,
        allow_none_wildcard: bool,
        item_key: Callable[[Any], str],
        display_key: Callable[[Any], str] | None = None,
        is_allowed: Callable[[str, frozenset[str]], bool] | None = None,
    ) -> Any:
        """Shared body for guarded call/get/read hooks.

        Forwards to ``call_next`` when scoping doesn't apply (or — for
        prompts and resources — when any matched configuration is
        unrestricted). Raises :class:`PermissionError` when the named item
        is outside every matched configuration. ``operation`` is the MCP
        method name used in log lines (``"tools/call"``, ``"prompts/get"``,
        or ``"resources/read"``).
        """
        requested, matched, provider_status = await self._resolve_configurations()
        if not requested or not provider_status.enabled:
            return await call_next(context)

        logger = _logger()
        item_lookup = item_key(context)
        item_name = display_key(context) if display_key else item_lookup

        if not matched:
            logger.warning(
                f"Rejected {operation} for '{item_name}' — "
                f"no active configurations matched {requested}"
            )
            raise PermissionError(
                f"No active configurations matched {requested}"
            )

        allowed = self._union_of(matched, attr, allow_none_wildcard=allow_none_wildcard)
        if allowed is None:
            return await call_next(context)

        allowed_check = is_allowed or (lambda key, allowed_set: key in allowed_set)
        if not allowed_check(item_lookup, allowed):
            matched_names = [c.name for c in matched]
            logger.warning(
                f"Rejected {operation} for '{item_name}' — "
                f"not in configurations {matched_names}"
            )
            raise PermissionError(
                f"{kind.capitalize()} '{item_name}' is not available "
                f"in configurations {matched_names}"
            )

        return await call_next(context)

    # ------------------------------------------------------------------
    # MCP hooks
    # ------------------------------------------------------------------

    async def on_list_tools(self, context: Any, call_next: Any) -> Sequence[Any]:
        all_tools = await call_next(context)
        # Tools never use the None wildcard — a missing/None ``tools`` field
        # would silently expose every registered tool, which is a security
        # regression. Fail closed on contract violations.
        return await self._filter_list(
            kind="tool",
            attr="tools",
            all_items=all_tools,
            allow_none_wildcard=False,
            item_key=self._name_key,
        )

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        return await self._guard_call(
            kind="tool",
            attr="tools",
            operation="tools/call",
            context=context,
            call_next=call_next,
            allow_none_wildcard=False,
            item_key=lambda ctx: ctx.message.name.upper(),
            display_key=lambda ctx: ctx.message.name,
        )

    async def on_list_prompts(self, context: Any, call_next: Any) -> Sequence[Any]:
        all_prompts = await call_next(context)
        # Prompts use the None wildcard for back-compat with configuration
        # files written before prompts existed (no ``prompts`` key = expose all).
        return await self._filter_list(
            kind="prompt",
            attr="prompts",
            all_items=all_prompts,
            allow_none_wildcard=True,
            item_key=self._name_key,
        )

    async def on_get_prompt(self, context: Any, call_next: Any) -> Any:
        return await self._guard_call(
            kind="prompt",
            attr="prompts",
            operation="prompts/get",
            context=context,
            call_next=call_next,
            allow_none_wildcard=True,
            item_key=lambda ctx: ctx.message.name.upper(),
            display_key=lambda ctx: ctx.message.name,
        )

    async def on_list_resources(self, context: Any, call_next: Any) -> Sequence[Any]:
        all_resources = await call_next(context)
        return await self._filter_list(
            kind="resource",
            attr="resources",
            all_items=all_resources,
            allow_none_wildcard=True,
            item_key=self._resource_key,
            is_allowed=self._resource_is_allowed,
        )

    async def on_list_resource_templates(
        self, context: Any, call_next: Any
    ) -> Sequence[Any]:
        all_templates = await call_next(context)
        # Plain key equality on purpose: only the concrete-URI surfaces
        # (on_list_resources / on_read_resource) need template-aware matching.
        return await self._filter_list(
            kind="resource template",
            attr="resources",
            all_items=all_templates,
            allow_none_wildcard=True,
            item_key=self._resource_key,
        )

    async def on_read_resource(self, context: Any, call_next: Any) -> Any:
        return await self._guard_call(
            kind="resource",
            attr="resources",
            operation="resources/read",
            context=context,
            call_next=call_next,
            allow_none_wildcard=True,
            item_key=self._resource_uri_from_context,
            display_key=self._resource_uri_from_context,
            is_allowed=self._resource_is_allowed,
        )
