# Install And Package Check

TMCP must work from a fresh checkout or copied package without user-specific paths. The canonical first command is:

```bash
node scripts/tmcp_launcher.mjs doctor
```

## Supported Layouts

- Skill-only install: copy `skills/tmcp`; use manual packet synthesis unless the host also exposes this package's launcher.
- Repo checkout: clone TMCP and run commands from the checkout root.
- Codex plugin cache: install as a Codex plugin; MCP config launches `scripts/tmcp_launcher.mjs` relative to the plugin root.
- Central local runtime: install a verified archive into `~/.tmcp/runtime/versions/<release>` and activate it through `scripts/tmcp_runtime.mjs`; generated Codex/Claude caches and compatibility aliases must be parity-checked.
- Deprecated AIOS compatibility: requires both `TMCP_ENABLE_DEPRECATED_AIOS_ADAPTER=1` and `AIOS_ROOT`. New installations should use standalone TMCP.

## Local Source Check

From the package root:

```bash
python3 scripts/check_install.py .
```

Expected:

- `.codex-plugin/plugin.json` points to `./.mcp.json`
- `.mcp.json` declares stdio MCP and launches `node scripts/tmcp_launcher.mjs` with `cwd` set to `.`
- MCP `tools/list` succeeds with AIOS unavailable

## Release Package Build

`python3 scripts/check_release_package.py . --verify-reproducible` is a release-build
command, not an install check. Run it only from a clean Git worktree: it reads the committed
tree, excludes untracked and ignored local state, rejects unsafe tracked paths
and secret-like content, and writes a deterministic archive with
RELEASE_MANIFEST.json.

Copied and extracted plugin packages are installation surfaces. Verify those
with check_install.py, the launcher smoke commands, and the extracted-package
checks performed by the release builder; do not try to rebuild a release archive
without its Git source revision.

## First-Run Smoke Test

```bash
node scripts/tmcp_launcher.mjs doctor --client codex
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs list-tools
node scripts/tmcp_runtime.mjs status --runtime-home "$HOME/.tmcp/runtime"
node scripts/tmcp_runtime.mjs doctor --runtime-home "$HOME/.tmcp/runtime"
```

Standalone mode should be available even when AIOS is not configured.

The launcher can be available even when secure local artifact persistence is
not. Check `doctor` or `status` before a workflow that writes artifacts, and
use `--no-write-artifacts` for portable previews. See
[Compatibility](COMPATIBILITY.md#secure-artifact-persistence) for the boundary.

## Codex Tool Discovery

Codex may load TMCP skills before it exposes the plugin MCP tools through deferred
tool discovery. If `tool_search` cannot find `tmcp_explain`, `tmcp_doctor`, or
`expert_rubric_review_plan`, first run the smoke test above from the installed
TMCP plugin root. If it passes, continue with the equivalent CLI command and cite
the generated JSON/artifacts.

For explicit Codex MCP registration, add a server entry that points at the
installed TMCP root:

```toml
[mcp_servers.tmcp]
command = "node"
args = ["scripts/tmcp_launcher.mjs"]
cwd = "/absolute/path/to/tmcp"
```

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

For shared local agent access, use the central runtime manager and keep the
project `.mcp.json` as a consumer overlay. Do not copy `skills/tmcp` into each
repository. The runtime's release and content digests are authoritative when a
skill or cache copy disagrees.

## Python Discovery

The launcher finds Python in this order:

- `TMCP_PYTHON`, when explicitly set
- Windows: `py -3`, then `python`, then `python3`
- macOS/Linux: `python3`, then `python`

## Deprecated AIOS Adapter

The AIOS adapter is disabled by default. `AIOS_ROOT` alone is ignored, so existing project configurations cannot activate an AIOS subprocess. Temporary legacy compatibility requires both `TMCP_ENABLE_DEPRECATED_AIOS_ADAPTER=1` and `AIOS_ROOT`; `adapter: "auto"` and `adapter: "standalone"` still remain inside TMCP. New installations should not enable this compatibility path.

TMCP rejects known sensitive request values before passing an explicit AIOS request through process arguments. Use standalone mode until AIOS offers a protected request-input protocol.
