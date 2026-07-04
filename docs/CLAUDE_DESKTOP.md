# Claude Desktop Manual MCP Install

Claude Desktop does not use the Claude Code plugin marketplace. Install TMCP manually as a local stdio MCP server.

## Prerequisites

- Node.js 20+
- Python 3.10+
- A local checkout or copied package of this repository

## Configuration

Add this to `claude_desktop_config.json`, replacing `/absolute/path/to/tmcp` with your TMCP checkout or package path:

```json
{
  "mcpServers": {
    "tmcp": {
      "command": "node",
      "args": ["/absolute/path/to/tmcp/scripts/tmcp_launcher.mjs"],
      "cwd": "/absolute/path/to/tmcp"
    }
  }
}
```

If Python is installed in a non-standard location, set `TMCP_PYTHON`:

```json
{
  "mcpServers": {
    "tmcp": {
      "command": "node",
      "args": ["/absolute/path/to/tmcp/scripts/tmcp_launcher.mjs"],
      "cwd": "/absolute/path/to/tmcp",
      "env": {
        "TMCP_PYTHON": "/absolute/path/to/python3"
      }
    }
  }
}
```

Set `AIOS_ROOT` only if you explicitly want the optional AIOS adapter.

## Smoke Test

After restarting Claude Desktop, call `tmcp_doctor`, then `tmcp_status`.

Expected:

- `standalone.available` is `true`
- `aios_adapter.available` may be `false`
