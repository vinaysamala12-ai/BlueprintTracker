# BlueprintTracker MCP Server

An MCP (Model Context Protocol) server that exposes the BlueprintTracker document approval workflow as tools for AI assistants like Claude. Built on [FastMCP](https://gofastmcp.com) following the Next AI MCP Server framework.

## What It Does

Allows Claude (or any MCP-compatible AI) to interact with BlueprintTracker through natural language:

- *"List all pending approval requests"*
- *"Submit this document for approval by Alice and Bob"*
- *"Send reminders for approval request [id]"*
- *"What are the document stats?"*
- *"Show me the notification logs"*

---

## Architecture

```
mcp-server/
├── framework/          # Stable MCP infrastructure (FastMCP, auth, logging, middleware)
├── src/
│   ├── shared/
│   │   └── client.py   # JWT token cache for BlueprintTracker API auth
│   ├── documents/      # Document management tools
│   ├── approvals/      # Approval workflow tools
│   ├── configuration/  # System configuration tools
│   └── storage/        # OneDrive/SharePoint storage tools
├── run_server.py       # HTTP server entry point (for direct API access)
├── run_stdio.py        # Stdio entry point (for Claude Desktop)
└── mcp-configurations.json  # Named toolset definitions
```

The `framework/` directory is stable infrastructure — add new features by creating domains under `src/` only.

---

## Tools (18 total)

### Documents
| Tool | Description |
|------|-------------|
| `list_documents` | List documents with status/search filtering and pagination |
| `get_document` | Get full details of a single document by ID |
| `submit_document` | Submit a document for approval by exactly 3 stakeholders |
| `delete_document` | Delete a document and its associated approval request |
| `get_document_stats` | Get document counts grouped by status |

### Approvals
| Tool | Description |
|------|-------------|
| `list_approvals` | List approval requests with filtering and pagination |
| `get_approval` | Get full details of an approval request including stakeholder statuses |
| `get_approval_stats` | Get approval counts grouped by status |
| `send_reminder` | Manually send reminder emails to pending stakeholders |
| `toggle_reminders` | Enable or disable automatic scheduled reminders |
| `get_approval_logs` | Get notification log for a specific approval request |
| `get_all_notification_logs` | Get all system notification logs with pagination |
| `get_scheduler_status` | Get current status of the reminder scheduler |
| `run_scheduler` | Manually trigger the reminder scheduler |

### Configuration
| Tool | Description |
|------|-------------|
| `get_configuration` | Get current system configuration (MS365, scheduler, storage) |
| `update_configuration` | Update system configuration settings |
| `test_email` | Send a test email to verify MS365 credentials |

### Storage
| Tool | Description |
|------|-------------|
| `list_storage_files` | List files in OneDrive/SharePoint storage |
| `get_storage_file` | Get metadata for a specific file by drive and file ID |
| `test_storage_connection` | Test OneDrive/SharePoint connectivity |

---

## Setup

### Prerequisites
- Python 3.12+
- BlueprintTracker backend running (Express + MongoDB)

### Install

```bash
cd mcp-server
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
# URL of the running BlueprintTracker Express server
BLUEPRINT_API_URL=https://your-backend-url.vercel.app

# Admin credentials for the MCP server to authenticate with the API
BLUEPRINT_USERNAME=admin
BLUEPRINT_PASSWORD=your-admin-password
```

---

## Running

### HTTP mode (standalone server)

```bash
python run_server.py
```

Endpoints:
- `GET  /blueprint-tracker/health/liveness` — liveness probe
- `GET  /blueprint-tracker/health/readiness` — readiness probe
- `GET  /blueprint-tracker/configurations` — list named toolsets
- `POST /blueprint-tracker/mcp/` — MCP JSON-RPC endpoint

### Stdio mode (Claude Desktop)

Claude Desktop manages the process automatically — no need to start it manually. See the Claude Desktop section below.

---

## Claude Desktop Integration

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "blueprint-tracker": {
      "command": "C:\\path\\to\\mcp-server\\venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\mcp-server\\run_stdio.py"]
    }
  }
}
```

Replace `C:\\path\\to\\mcp-server` with the actual path. Restart Claude Desktop after saving.

---

## Named Toolsets

Clients can send `X-APTEAN-MCP-TOOLSETS: <name>` to restrict which tools are exposed. Defined in `mcp-configurations.json`:

| Toolset | Tools included |
|---------|---------------|
| `documents` | Document management (5 tools) |
| `approvals` | Approval workflow (9 tools) |
| `configuration` | System config (3 tools) |
| `storage` | File storage (3 tools) |
| `readonly` | All read-only tools — safe for untrusted clients (12 tools) |

---

## Adding a New Domain

1. Create `src/<domain>/` with four files:
   - `__init__.py` — empty
   - `models.py` — Pydantic input/output models
   - `tools.py` — async functions calling the BlueprintTracker API
   - `server.py` — `@register_tool` wrappers

2. Follow the pattern in any existing domain (e.g. `src/documents/`).

3. Restart the server — auto-discovery picks it up automatically.

```python
# src/mydomain/server.py
from framework import register_tool
from .models import MyParams
from .tools import my_function

@register_tool("my_tool")
async def my_tool_handler(params: MyParams) -> dict:
    """Tool description shown to the AI."""
    result = await my_function(params.value)
    return result.model_dump()
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BLUEPRINT_API_URL` | `http://localhost:5000` | BlueprintTracker backend URL |
| `BLUEPRINT_USERNAME` | `admin` | Admin username |
| `BLUEPRINT_PASSWORD` | — | Admin password |
| `SERVER_HOST` | `localhost` | MCP server bind host |
| `SERVER_PORT` | `8001` | MCP server port |
| `MCP_BASE_PATH` | `blueprint-tracker` | URL path prefix |
| `LOG_LEVEL` | `INFO` | Logging level |
| `MCP_MASTER_API_KEY` | — | Optional API key to protect the MCP server |
| `TOOL_TIMEOUT_SECONDS` | — | Default per-tool timeout |
| `HTTP_CLIENT_TIMEOUT_SECONDS` | `30` | Outbound HTTP timeout |
