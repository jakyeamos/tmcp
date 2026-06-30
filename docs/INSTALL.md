# Install And Package Check

TMCP should work from a source checkout or installed plugin cache without user-specific paths.

For distribution-specific install instructions, see:

- [DISTRIBUTION.md](DISTRIBUTION.md)
- [CLAUDE_CODE.md](CLAUDE_CODE.md)
- [CLAUDE_DESKTOP.md](CLAUDE_DESKTOP.md)

## Local Source Check

From the plugin root:

```bash
python3 scripts/check_install.py .
```

Expected result:

- `.codex-plugin/plugin.json` exists and points to `./.mcp.json`.
- `.mcp.json` declares a stdio MCP server and launches `node scripts/tmcp_launcher.mjs` with `cwd` set to `.`.
- MCP `tools/list` succeeds with `AIOS_ROOT` pointed at a missing path.

## First-Run Smoke Test

After install, call `tmcp_doctor` in your MCP client. It should report:

- `ok: true`
- `node_launcher: pass`
- `python_server: pass`
- `python_runtime: pass`

Then call `tmcp_status`. Standalone mode should be available even when the AIOS adapter is absent.

Direct CLI equivalent:

```bash
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
```

The CLI uses the same tool implementations as MCP. See [CLI.md](CLI.md).

## Codex Plugin Shape

Required files:

- `.codex-plugin/plugin.json`
- `.mcp.json`
- `scripts/tmcp_launcher.mjs`
- `scripts/tmcp_mcp_server.py`
- `skills/tmcp/SKILL.md`
- focused Codex router skills for UI rubric, release readiness, skill harvest, workflow recommendation, DX audit, and security/privacy audit

The MCP launcher and server paths must remain relative to the plugin root. Do not hardcode a user home directory or AIOS checkout path. The Codex MCP server declaration should include `"type": "stdio"` so hosts that require explicit stdio discovery do not skip the bundled server.

## Claude Code Plugin Shape

Claude Code uses its own plugin manifest:

- `.claude-plugin/plugin.json`
- `.claude-plugin/mcp.json`
- `.claude-plugin/marketplace.json`

The Claude MCP config uses `${CLAUDE_PLUGIN_ROOT}` because Claude copies plugins into a versioned cache before launching bundled MCP servers.

## Python Discovery

Codex launches TMCP through Node so the plugin has one stable MCP command across operating systems. The launcher then finds Python:

- `TMCP_PYTHON`, when explicitly set.
- Windows: `py -3`, then `python`, then `python3`.
- macOS/Linux: `python3`, then `python`.

If Python is installed somewhere unusual, set `TMCP_PYTHON` to that executable path in the MCP server environment.

## Direct CLI

Use the direct CLI when an agent needs to test or invoke TMCP without MCP tool discovery:

```bash
node scripts/tmcp_launcher.mjs list-tools
node scripts/tmcp_launcher.mjs explain "Review developer onboarding commands" --project-path .
node scripts/tmcp_launcher.mjs harvest . --write-artifacts --output-dir .tmcp/harvest
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows security_privacy
node scripts/tmcp_launcher.mjs review-plan "Use the TMCP expert UI rubric on Hoopscout" --project-path . --evidence-json '[]'
node scripts/tmcp_launcher.mjs expert-ui-rubric --project-path . --evidence-json '[]'
```

With no arguments, `node scripts/tmcp_launcher.mjs` remains the MCP stdio entrypoint.

## Marketplace Example

`marketplace.example.json` shows the expected local marketplace entry shape. In a real marketplace root, the plugin source path should point from the marketplace root to the plugin directory:

```json
{
  "name": "tmcp",
  "source": {
    "source": "local",
    "path": "./plugins/tmcp"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

## AIOS Adapter

AIOS is optional. If `AIOS_ROOT` points to an AIOS checkout, `adapter: "auto"` may use AIOS for richer packet compilation. If AIOS is missing, `adapter: "auto"` must fall back to standalone behavior. `adapter: "aios"` should return a clear error when AIOS is unavailable.
