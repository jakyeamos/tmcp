# Distribution Plan

TMCP ships through portable layouts that all use the same launcher:

```bash
node scripts/tmcp_launcher.mjs
```

## GitHub Source Repository

The repository contains source, docs, license, CI, plugin metadata, examples, and release checks. A fresh clone should pass:

```bash
node scripts/tmcp_launcher.mjs doctor
python3 scripts/check_release_package.py .
```

## Codex Plugin

Codex uses:

- [.codex-plugin/plugin.json](../.codex-plugin/plugin.json)
- [.mcp.json](../.mcp.json)
- [skills/tmcp/SKILL.md](../skills/tmcp/SKILL.md)

The MCP server declaration launches `scripts/tmcp_launcher.mjs` relative to the plugin root.

## Claude Code Plugin

Claude Code uses:

- [.claude-plugin/plugin.json](../.claude-plugin/plugin.json)
- [.claude-plugin/mcp.json](../.claude-plugin/mcp.json)
- [.claude-plugin/marketplace.json](../.claude-plugin/marketplace.json)

## Claude Desktop Manual MCP Install

Claude Desktop users install TMCP by adding a local stdio MCP server entry to `claude_desktop_config.json`. See [CLAUDE_DESKTOP.md](CLAUDE_DESKTOP.md).

## Skill-Only Install

Skill-only installs copy `skills/tmcp` and its `references/` directory. They provide routing and manual packet synthesis. They do not expose MCP tools unless the host also has access to the launcher.

## AIOS-Backed Install

Set `AIOS_ROOT` only when optional AIOS storage/adapter behavior is wanted. AIOS is not required for standalone TMCP.

## MCP Registry Submission

The source repository registry draft lives at `mcp-registry/draft-server.json`. It uses the official `server.json` schema and should pass:

```bash
mcp-publisher validate mcp-registry/draft-server.json
```

Submit only after release validation passes from a clean checkout and extracted package.
