# Distribution Plan

TMCP ships through five surfaces.

## 1. GitHub Source Repository

Canonical repository:

```text
https://github.com/jakyeamos/tmcp
```

The repository contains source, docs, license, CI, Codex plugin metadata, Claude Code plugin metadata, and release checks.

## 2. Codex Plugin

Codex uses:

- [.codex-plugin/plugin.json](../.codex-plugin/plugin.json)
- [.mcp.json](../.mcp.json)
- [skills/tmcp/SKILL.md](../skills/tmcp/SKILL.md)

The local personal Codex marketplace entry points to this plugin from `/Users/jakyeamos/.agents/plugins/marketplace.json`.

## 3. Claude Code Plugin And Marketplace

Claude Code uses:

- [.claude-plugin/plugin.json](../.claude-plugin/plugin.json)
- [.claude-plugin/mcp.json](../.claude-plugin/mcp.json)
- [.claude-plugin/marketplace.json](../.claude-plugin/marketplace.json)

Install after the public GitHub repo exists:

```bash
claude plugin marketplace add jakyeamos/tmcp
claude plugin install tmcp@tmcp
```

## 4. Claude Desktop Manual MCP Install

Claude Desktop users install TMCP by adding a local MCP server entry to `claude_desktop_config.json`.

See [CLAUDE_DESKTOP.md](CLAUDE_DESKTOP.md).

## 5. MCP Registry Submission

The registry draft lives at [mcp-registry/draft-server.json](../mcp-registry/draft-server.json).

Submit only after:

- The public GitHub repository exists.
- A release tag exists.
- The registry's current server schema is confirmed.
- The install command is tested from a clean clone.
