"""Health check and configuration discovery routes registered on the MCP server.

Endpoints follow k8s probe conventions:

* ``/health`` and ``/health/liveness`` — simple "ok" response.
* ``/health/readiness`` — 200 when tools are loaded and the configuration
  provider is valid; 503 otherwise.
* ``/health/detailed`` — full payload (tools list, configurations, provider
  status, uptime, version) for dashboards and operators.
"""

import asyncio
from datetime import datetime
from typing import Any, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..core.fastmcp_compat import (
    list_mcp_items_unfiltered,
    resource_uri_key,
)
from ..core.mcp_configuration import (
    get_configuration_listing,
    get_provider_status,
    serialize_provider_status,
)
from ..core.utils import (
    get_app_config,
    get_app_logger,
    get_project_metadata,
    get_uptime_seconds,
)


async def _list_named_items(mcp: Any, method_name: str, kind: str) -> list[str]:
    """Return ``[item.name, ...]`` from a FastMCP list endpoint, bypassing middleware."""
    try:
        items = await list_mcp_items_unfiltered(mcp, method_name)
        return [item.name for item in items]
    except Exception:
        # ERROR (not WARNING) so log-based alerting catches a broken FastMCP
        # list path even when the readiness probe still returns 200.
        get_app_logger().exception(f"Failed to list {kind} for health probe")
        return []


async def _list_resource_uris(mcp: Any) -> list[str]:
    try:
        resources = await list_mcp_items_unfiltered(mcp, "list_resources")
        return sorted(resource_uri_key(resource) for resource in resources)
    except Exception:
        get_app_logger().exception("Failed to list resources for health probe")
        return []


async def _list_resource_template_uris(mcp: Any) -> list[str]:
    try:
        templates = await list_mcp_items_unfiltered(mcp, "list_resource_templates")
        return sorted(resource_uri_key(template) for template in templates)
    except Exception:
        get_app_logger().exception(
            "Failed to list resource templates for health probe"
        )
        return []


def register_health_routes(
    mcp: Any,
    base_path: str = "",
    configuration_provider: Optional[Any] = None,
) -> None:
    """Attach health and configuration discovery routes to the MCP server."""
    prefix = f"/{base_path.strip('/')}" if base_path.strip("/") else ""

    async def _ok(_request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    mcp.custom_route(f"{prefix}/health", methods=["GET"])(_ok)
    mcp.custom_route(f"{prefix}/health/liveness", methods=["GET"])(_ok)

    @mcp.custom_route(f"{prefix}/health/readiness", methods=["GET"])
    async def readiness(_request: Request) -> Response:
        try:
            status = await get_provider_status(configuration_provider)
            tool_names = await _list_named_items(mcp, "list_tools", "tools")
            checks = {
                "tools_loaded": len(tool_names) > 0,
                "configuration_valid": status.valid,
            }
            ready = all(checks.values())
            return JSONResponse(
                {"status": "ready" if ready else "not_ready", "checks": checks},
                status_code=200 if ready else 503,
            )
        except Exception as e:
            get_app_logger().error(f"Readiness check failed: {e}")
            return JSONResponse(
                {"status": "not_ready", "error": str(e)}, status_code=503
            )

    @mcp.custom_route(f"{prefix}/health/detailed", methods=["GET"])
    async def detailed(_request: Request) -> Response:
        try:
            tools, prompts, resources, resource_templates, listing = await asyncio.gather(
                _list_named_items(mcp, "list_tools", "tools"),
                _list_named_items(mcp, "list_prompts", "prompts"),
                _list_resource_uris(mcp),
                _list_resource_template_uris(mcp),
                get_configuration_listing(configuration_provider),
            )
            status, configurations_info = listing

            checks = {
                "mcp_server_responsive": True,
                "tools_loaded": len(tools) > 0,
                "configuration_valid": status.valid,
                "configuration_enabled": status.enabled,
            }
            healthy = checks["tools_loaded"] and checks["configuration_valid"]

            return JSONResponse(
                {
                    "status": "healthy" if healthy else "unhealthy",
                    "mcp_server": {
                        "running": True,
                        "transport": "Streamable HTTP",
                        "port": get_app_config().get("server_port", 8000),
                    },
                    "version": get_project_metadata().get("version", "1.0.0"),
                    "timestamp": datetime.now().isoformat(),
                    "uptime_seconds": get_uptime_seconds(),
                    "tools_available": tools,
                    "prompts_available": prompts,
                    "resources_available": resources,
                    "resource_templates_available": resource_templates,
                    "configurations": configurations_info,
                    "configuration_provider": serialize_provider_status(status),
                    "checks": checks,
                },
                status_code=200 if healthy else 503,
            )
        except Exception as e:
            get_app_logger().error(f"Detailed health check failed: {e}")
            return JSONResponse(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
                status_code=503,
            )

    async def _list_configurations(_request: Request) -> Response:
        status, configurations_info = await get_configuration_listing(
            configuration_provider
        )
        return JSONResponse(
            {
                "names": [config["name"] for config in configurations_info],
                "configurations": configurations_info,
                "configuration_provider": serialize_provider_status(status),
            },
            status_code=200 if status.valid else 503,
        )

    mcp.custom_route(f"{prefix}/configurations", methods=["GET"])(_list_configurations)
    mcp.custom_route(
        f"{prefix}/mcp/configurations", methods=["GET"], include_in_schema=False
    )(_list_configurations)

    @mcp.custom_route(f"{prefix}/" if prefix else "/", methods=["GET"])
    async def root(_request: Request) -> Response:
        return JSONResponse(
            {
                "service": "MCP Server",
                "endpoints": {
                    f"{prefix}/health": "Liveness (simple ok)",
                    f"{prefix}/health/liveness": "K8s liveness probe",
                    f"{prefix}/health/readiness": "K8s readiness probe",
                    f"{prefix}/health/detailed": "Detailed health (tools, configurations, provider)",
                    f"{prefix}/configurations": "MCP configuration discovery endpoint",
                    f"{prefix}/mcp/configurations": "MCP configuration discovery endpoint alias",
                    f"{prefix}/mcp/": "MCP Streamable HTTP endpoint",
                },
            }
        )
