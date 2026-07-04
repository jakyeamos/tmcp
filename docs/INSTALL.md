# Install And Package Check

TMCP must work from a fresh checkout or copied package without user-specific paths. The canonical first command is:

```bash
node scripts/tmcp_launcher.mjs doctor
```

## Supported Layouts

- Skill-only install: copy `skills/tmcp`; use manual packet synthesis unless the host also exposes this package's launcher.
- Repo checkout: clone TMCP and run commands from the checkout root.
- Codex plugin cache: install as a Codex plugin; MCP config launches `scripts/tmcp_launcher.mjs` relative to the plugin root.
- AIOS-backed install: set `AIOS_ROOT` explicitly only when optional AIOS adapter behavior is wanted.

## Local Source Check

From the package root:

```bash
python3 scripts/check_install.py .
```

Expected:

- `.codex-plugin/plugin.json` points to `./.mcp.json`
- `.mcp.json` declares stdio MCP and launches `node scripts/tmcp_launcher.mjs` with `cwd` set to `.`
- MCP `tools/list` succeeds with AIOS unavailable

## First-Run Smoke Test

```bash
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
```

Standalone mode should be available even when AIOS is not configured.

## MCP Config Shape

Portable MCP config should use relative launcher paths when the host supports `cwd`:

```json
{
  "mcpServers": {
    "tmcp": {
      "type": "stdio",
      "command": "node",
      "args": ["scripts/tmcp_launcher.mjs"],
      "cwd": "."
    }
  }
}
```

Do not hardcode a home directory, user path, or AIOS checkout path in the generic package config.

## Python Discovery

The launcher finds Python in this order:

- `TMCP_PYTHON`, when explicitly set
- Windows: `py -3`, then `python`, then `python3`
- macOS/Linux: `python3`, then `python`

## AIOS Adapter

AIOS is optional. If `AIOS_ROOT` is set and `adapter: "auto"` is used, TMCP may use AIOS for richer packet compilation. If AIOS is missing, `adapter: "auto"` falls back to standalone behavior. `adapter: "aios"` returns a clear remediation error when unavailable.
