"""Module-level FastMCP instance for FastMCP CLI consumers (fastmcp dev / inspect)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from framework import get_mcp_server

mcp = get_mcp_server()
