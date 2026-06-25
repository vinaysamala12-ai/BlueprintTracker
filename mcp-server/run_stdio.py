#!/usr/bin/env python3
"""Stdio entry point for Claude Desktop integration.

Claude Desktop communicates via stdin/stdout using JSON-RPC.
Logs must go to stderr — not stdout — to keep the protocol stream clean.
"""

import os
import sys
from pathlib import Path

# Set working directory to the mcp-server root so auto_discover_domains()
# finds our src/ directory regardless of where Claude Desktop launches from.
ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Redirect stdout → stderr so the framework's setup_logging() creates its
# StreamHandler against stderr, keeping stdout clean for JSON-RPC.
_real_stdout = sys.stdout
sys.stdout = sys.stderr

from framework import get_mcp_server
mcp = get_mcp_server()

# Restore real stdout for JSON-RPC communication with Claude Desktop.
sys.stdout = _real_stdout

mcp.run(transport="stdio")
