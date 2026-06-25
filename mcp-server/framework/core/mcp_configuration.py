"""MCP server configuration — named tool/prompt/resource subsets for agent scoping.

Implements the agentMCPConfiguration pattern: an admin defines named
configurations, each listing which tools and prompts are visible. Clients
select one or more configurations via the ``X-APTEAN-MCP-TOOLSETS`` HTTP
header, and only items in those configurations are exposed via list operations
and allowed via call/get operations.

The framework ships a file-based provider (``FileConfigurationProvider``) that
reads from a JSON file. ERPs that store configurations in their own database
can subclass ``ConfigurationProvider`` and supply their own implementation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.utils import get_app_logger


def _logger() -> logging.Logger:
    """Return the app logger, falling back to a stdlib logger."""
    return get_app_logger() or logging.getLogger(__name__)

# Header name used by clients to select one or more configurations. Stored
# lowercase because header matching in the middleware is case-insensitive.
CONFIGURATION_HEADER = "x-aptean-mcp-toolsets"


@dataclass(frozen=True)
class MCPConfiguration:
    """A named subset of tools, prompts, and resources for an agent / use-case.

    Three states are load-bearing for the prompts and resources surfaces:

    * ``prompts is None`` — **unrestricted**. The configuration does not
      mention prompts at all (the JSON file omitted the ``prompts`` key).
      This is the back-compat default for configuration files written before
      prompt support landed; they keep exposing every registered prompt.
    * ``prompts == frozenset()`` — **explicit deny-all**. The JSON had
      ``"prompts": []``, opting out of every prompt for this configuration.
    * ``prompts == frozenset({...names...})`` — explicit allowlist.

    ``resources`` follows the same ``None``/empty/allowlist semantic, but
    stores resource URIs exactly as written instead of uppercasing them.

    Tool and prompt names are stored UPPERCASE so middleware matching is
    case-insensitive. The ``None`` wildcard is **prompt-only** — the
    ``ConfigurationMiddleware`` treats ``tools=None`` as a provider contract
    violation and fails the request closed (logs an error, contributes
    nothing to the allowed set). ``FileConfigurationProvider`` always
    constructs ``tools`` as a frozenset; custom providers should do the same.

    See :meth:`is_prompts_unrestricted` and :meth:`allows_prompt` for the
    derived predicates the middleware uses.
    """

    name: str
    description: str = ""
    active: bool = True
    tools: frozenset[str] = field(default_factory=frozenset)
    prompts: frozenset[str] | None = None
    resources: frozenset[str] | None = None

    @property
    def is_prompts_unrestricted(self) -> bool:
        """True when this configuration places no restriction on prompts."""
        return self.prompts is None

    @property
    def is_resources_unrestricted(self) -> bool:
        """True when this configuration places no restriction on resources."""
        return self.resources is None

    def allows_tool(self, tool_name: str) -> bool:
        return tool_name.upper() in self.tools

    def allows_prompt(self, prompt_name: str) -> bool:
        if self.is_prompts_unrestricted:
            return True
        return prompt_name.upper() in self.prompts

    def allows_resource(self, resource_uri: str) -> bool:
        if self.is_resources_unrestricted:
            return True
        return resource_uri in self.resources


@dataclass(frozen=True)
class ConfigurationProviderStatus:
    """Health and activation status for a configuration source."""

    enabled: bool = True
    valid: bool = True
    source: str | None = None
    configuration_count: int = 0
    error: str | None = None


class ConfigurationProvider:
    """Abstract base for configuration sources.

    Subclass and override ``load_configurations`` to fetch from an ERP
    database, REST API, or any other backing store.
    """

    async def load_configurations(self) -> dict[str, MCPConfiguration]:
        """Return ``{CONFIG_NAME_UPPER: MCPConfiguration, ...}``."""
        raise NotImplementedError

    async def get_configuration(self, name: str) -> MCPConfiguration | None:
        configs = await self.load_configurations()
        return configs.get(name.upper())

    async def list_configurations(self) -> list[MCPConfiguration]:
        configs = await self.load_configurations()
        return list(configs.values())

    async def get_status(self) -> ConfigurationProviderStatus:
        configs = await self.load_configurations()
        return ConfigurationProviderStatus(
            enabled=True,
            valid=True,
            configuration_count=len(configs),
        )


class FileConfigurationProvider(ConfigurationProvider):
    """Load configurations from a JSON file on disk.

    Expected format::

        {
          "configurations": [
            {
              "name": "SalesOrderAgent",
              "description": "Tools for sales order processing",
              "active": true,
              "tools": ["get_customers", "create_sales_order", "get_items"],
              "prompts": ["summarize_order"],
              "resources": ["metadata://sample/schema"]
            }
          ]
        }

    The ``prompts`` and ``resources`` fields are optional. Omitted means
    unrestricted access for that surface; an explicit empty list means deny all.

    If the file does not exist, configuration filtering is disabled and all
    tools/prompts/resources remain visible (backward-compatible default).
    Invalid files also fail open, but the provider status is marked invalid
    for health reporting.
    """

    def __init__(self, path: str = "mcp-configurations.json"):
        self._path = Path(path)
        self._cache: dict[str, MCPConfiguration] | None = None
        self._status = ConfigurationProviderStatus(
            enabled=False,
            valid=True,
            source=str(self._path),
            configuration_count=0,
        )

    async def load_configurations(self) -> dict[str, MCPConfiguration]:
        if self._cache is not None:
            return self._cache

        logger = _logger()
        source = str(self._path)

        if not self._path.exists():
            logger.info(
                f"No MCP configuration file at '{self._path}' — "
                "configuration filtering is disabled and all tools/prompts remain visible"
            )
            self._cache = {}
            self._status = ConfigurationProviderStatus(
                enabled=False,
                valid=True,
                source=source,
                configuration_count=0,
            )
            return self._cache

        try:
            data: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Top-level JSON must be an object")

            entries = data.get("configurations", [])
            if not isinstance(entries, list):
                raise ValueError("'configurations' must be a list")
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.error(f"Failed to read MCP configuration file '{self._path}': {exc}")
            self._cache = {}
            self._status = ConfigurationProviderStatus(
                enabled=False,
                valid=False,
                source=source,
                configuration_count=0,
                error=str(exc),
            )
            return self._cache

        configs: dict[str, MCPConfiguration] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                logger.warning("Skipping MCP configuration entry that is not an object")
                continue

            name = entry.get("name", "").strip()
            if not name:
                logger.warning("Skipping MCP configuration entry with empty name")
                continue

            tools_raw = entry.get("tools", [])
            tools = frozenset(t.upper() for t in tools_raw if isinstance(t, str) and t.strip())

            # Distinguish "no prompts key" (unrestricted) from "empty list"
            # (explicit deny-all). This is the fail-open semantic for
            # backward compatibility — see MCPConfiguration.prompts docstring.
            prompts: frozenset[str] | None = None
            if "prompts" in entry:
                prompts_raw = entry.get("prompts") or []
                prompts = frozenset(
                    p.upper() for p in prompts_raw if isinstance(p, str) and p.strip()
                )

            resources: frozenset[str] | None = None
            if "resources" in entry:
                resources_raw = entry.get("resources") or []
                resources = frozenset(
                    r.strip() for r in resources_raw if isinstance(r, str) and r.strip()
                )

            config = MCPConfiguration(
                name=name,
                description=entry.get("description", ""),
                active=entry.get("active", True),
                tools=tools,
                prompts=prompts,
                resources=resources,
            )
            configs[name.upper()] = config
            prompt_count = "unrestricted" if prompts is None else f"{len(prompts)} prompt(s)"
            resource_count = (
                "unrestricted" if resources is None else f"{len(resources)} resource(s)"
            )
            logger.debug(
                f"Loaded MCP configuration '{name}' — {len(tools)} tool(s), "
                f"{prompt_count}, {resource_count}, active={config.active}"
            )

        self._cache = configs
        self._status = ConfigurationProviderStatus(
            enabled=True,
            valid=True,
            source=source,
            configuration_count=len(configs),
        )
        logger.info(f"MCP configuration loading complete — {len(configs)} configuration(s)")
        return self._cache

    async def get_status(self) -> ConfigurationProviderStatus:
        if self._cache is None:
            await self.load_configurations()
        return self._status

    def reload(self) -> None:
        """Clear the cache so the next access re-reads the file."""
        self._cache = None
        self._status = ConfigurationProviderStatus(
            enabled=False,
            valid=True,
            source=str(self._path),
            configuration_count=0,
        )


def serialize_configuration(config: MCPConfiguration) -> dict[str, Any]:
    """Convert a configuration object into API response shape.

    ``*_unrestricted`` distinguishes "field omitted, all items visible" from
    "explicit deny-all" — the former is the back-compat default for legacy
    configuration files. Counts are always ints (0 when unrestricted), which
    keeps the JSON schema homogeneous for clients.
    """
    prompts_unrestricted = config.is_prompts_unrestricted
    resources_unrestricted = config.is_resources_unrestricted
    return {
        "name": config.name,
        "description": config.description,
        "active": config.active,
        "tool_count": len(config.tools),
        "prompts_unrestricted": prompts_unrestricted,
        "prompt_count": 0 if prompts_unrestricted else len(config.prompts),
        "resources_unrestricted": resources_unrestricted,
        "resource_count": 0 if resources_unrestricted else len(config.resources),
    }


def serialize_provider_status(status: ConfigurationProviderStatus) -> dict[str, Any]:
    """Convert provider status into API response shape."""
    return {
        "enabled": status.enabled,
        "valid": status.valid,
        "source": status.source,
        "configuration_count": status.configuration_count,
        "error": status.error,
    }


_DISABLED_STATUS = ConfigurationProviderStatus(
    enabled=False, valid=True, configuration_count=0
)


async def get_provider_status(
    provider: ConfigurationProvider | None,
) -> ConfigurationProviderStatus:
    """Return provider status only — cheaper than listing configurations."""
    if not provider:
        return _DISABLED_STATUS
    try:
        return await provider.get_status()
    except Exception as exc:
        return ConfigurationProviderStatus(
            enabled=False, valid=False, configuration_count=0, error=str(exc)
        )


async def get_configuration_listing(
    provider: ConfigurationProvider | None,
) -> tuple[ConfigurationProviderStatus, list[dict[str, Any]]]:
    """Load configuration summaries plus provider status."""
    if not provider:
        return _DISABLED_STATUS, []

    try:
        status = await provider.get_status()
        configs = await provider.list_configurations()
        return status, [serialize_configuration(config) for config in configs]
    except Exception as exc:
        return (
            ConfigurationProviderStatus(
                enabled=False, valid=False, configuration_count=0, error=str(exc)
            ),
            [],
        )
