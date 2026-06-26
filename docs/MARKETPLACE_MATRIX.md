# Marketplace Matrix

TMCP ships through multiple surfaces because each client uses a different install model. The runtime is the same: a Node stdio launcher starts the Python MCP server from the plugin root.

| Surface | Primary User | Install Shape | Update Shape | Notes |
| --- | --- | --- | --- | --- |
| GitHub source | Developers and registry reviewers | Clone or release tag | Git pull or new tag | Canonical source, tests, docs, and registry draft |
| Codex plugin | Codex users | Codex plugin metadata plus bundled skills and MCP | Codex plugin version/cachebuster | Best path for Codex skill routing |
| Claude Code plugin | Claude Code users | `.claude-plugin/plugin.json` and `.claude-plugin/mcp.json` | Plugin version bump | Best path for Claude Code slash commands and plugin MCP tools |
| Claude Desktop MCP | Claude Desktop users | Manual `claude_desktop_config.json` server entry | Pull repo or update local path | No marketplace support needed |
| MCP Registry | Generic MCP users | Registry server metadata | Registry version/release process | Submit after official schema review |

## Decision Rule

- Use the client-native plugin when the client supports plugins.
- Use Claude Desktop manual MCP config when the client supports MCP but not plugins.
- Use the plain MCP command when integrating with an arbitrary MCP host.
- Use the GitHub release tag as the canonical source for review, reproducibility, and registry submissions.

## Shared Smoke Test

Every install path should pass the same sequence:

1. `tmcp_doctor`
2. `tmcp_status`
3. `tmcp_explain` with a simple objective
4. `tmcp_harvest_skills` against a small local repo
5. `tmcp_recommend_workflows` against the same harvested repo
