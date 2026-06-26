# Claude Desktop Manual MCP Install

Claude Desktop does not use the Claude Code plugin marketplace. Install TMCP manually as a local stdio MCP server.

## Prerequisites

- Node.js 20+
- Python 3.10+
- A local checkout of this repository

## Configuration

Add this to `claude_desktop_config.json`, replacing `/absolute/path/to/tmcp` with this repository path:

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

On this machine, the local development value is:

```json
{
  "mcpServers": {
    "tmcp": {
      "command": "node",
      "args": ["/Users/jakyeamos/plugins/tmcp/scripts/tmcp_launcher.mjs"],
      "cwd": "/Users/jakyeamos/plugins/tmcp"
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

Restart Claude Desktop after editing the config.

## Smoke Test

After restart, call the `tmcp_doctor` MCP tool. Then call `tmcp_status`.

Expected result:

- `standalone.available` is `true`.
- `aios_adapter.available` may be `false`; AIOS is optional.
