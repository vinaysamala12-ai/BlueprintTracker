#!/usr/bin/env python3
"""Entry point for the BlueprintTracker MCP server."""

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from framework import get_app_logger, get_app_config, get_project_metadata, get_mcp_server
from framework.health.http_health import register_health_routes
from framework.middleware.middleware import HeaderCaptureMiddleware
from framework.middleware.configuration_middleware import ConfigurationMiddleware
from framework.middleware.response_limiting import ResponseLimitingMiddleware
from framework.core.config import app_config
from framework.core.mcp_configuration import FileConfigurationProvider
from starlette.middleware import Middleware


def main() -> None:
    try:
        mcp = get_mcp_server()

        mcp.add_middleware(ResponseLimitingMiddleware(max_size=app_config.response_max_bytes))

        config_provider = FileConfigurationProvider(app_config.mcp_configurations_file)
        mcp.add_middleware(ConfigurationMiddleware(config_provider))

        path_prefix = app_config.mcp_path_prefix
        mcp_path = f"{path_prefix}/mcp"

        register_health_routes(mcp, base_path=app_config.mcp_base_path, configuration_provider=config_provider)

        logger = get_app_logger()
        config = get_app_config()
        project_metadata = get_project_metadata()

        project_version = project_metadata.get("version", "0.0.0")
        logger.info(f"Starting BlueprintTracker MCP Server v{project_version}")
        logger.info(f"Server configuration: {config}")
        base_url = f"http://{config['server_host']}:{config['server_port']}"
        logger.info(f"MCP Streamable HTTP endpoint: {base_url}{mcp_path}/")
        logger.info(f"Liveness: {base_url}{path_prefix}/health/liveness")
        logger.info(f"Readiness: {base_url}{path_prefix}/health/readiness")
        logger.info(f"Configuration discovery: {base_url}{path_prefix}/configurations")

        middleware_list: List[Middleware] = [Middleware(HeaderCaptureMiddleware)]

        log_level = config.get("log_level", "info").lower()

        mcp.run(
            host=config["server_host"],
            port=config["server_port"],
            transport="http",
            path=mcp_path,
            middleware=middleware_list,
            log_level=log_level,
            stateless_http=True,
        )
    except KeyboardInterrupt:
        logger = get_app_logger()
        logger.info("Shutdown requested")
    except Exception as e:
        logger = get_app_logger()
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger = get_app_logger()
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
