# Claude Code Distribution

TMCP can be loaded as a Claude Code plugin from this repository.

## Local Development

From a clone of this repository:

```bash
claude --plugin-dir .
```

Then reload plugins inside Claude Code if needed:

```text
/reload-plugins
```

The skill appears as:

```text
/tmcp:tmcp
```

Plugin-provided MCP tools appear under Claude Code's plugin MCP naming, for example:

```text
mcp__plugin_tmcp_tmcp__tmcp_status
```

Run the first-run check:

```text
mcp__plugin_tmcp_tmcp__tmcp_doctor
```

## Marketplace Install

After this repository is public, add it as a Claude Code marketplace:

```bash
claude plugin marketplace add jakyeamos/tmcp
claude plugin install tmcp@tmcp
```

Inside Claude Code, the equivalent commands are:

```text
/plugin marketplace add jakyeamos/tmcp
/plugin install tmcp@tmcp
```

## Claude-Specific MCP Config

Claude Code uses [.claude-plugin/mcp.json](../.claude-plugin/mcp.json). It points at the installed plugin cache with `${CLAUDE_PLUGIN_ROOT}`:

```json
{
  "mcpServers": {
    "tmcp": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/tmcp_launcher.mjs"],
      "cwd": "${CLAUDE_PLUGIN_ROOT}"
    }
  }
}
```

The shared launcher discovers Python with `TMCP_PYTHON`, `py -3`, `python`, or `python3`.

## Validation

Run:

```bash
claude plugin validate .
```
