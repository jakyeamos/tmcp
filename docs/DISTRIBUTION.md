# Distribution Plan

TMCP ships through portable layouts that all use the same launcher:

```bash
node scripts/tmcp_launcher.mjs
```

## GitHub Source Repository

The repository contains source, docs, license, CI, plugin metadata, examples, and release checks. A fresh clone should pass:

```bash
node scripts/tmcp_launcher.mjs doctor
python3 scripts/check_release_package.py . --verify-reproducible
```

Release archives are built only from a clean committed Git tree. The builder
uses a reviewed allowlist, rejects unsafe tracked inputs, excludes untracked and
ignored local state, and emits a deterministic archive manifest and digest.

The release sequence is:

1. Commit the release candidate and ensure no staged or unstaged tracked files remain.
2. Run the package check with `--verify-reproducible` and inspect its source commit, manifest, first archive digest, and repeat archive digest.
3. Record successful release-PR evidence for the active manifest version, then run the PR checks again; merge only after that second PR verification passes its evidence gate.
4. Extract the archive, run the install/MCP smoke checks, and publish the verified archive.

Plugin caches and copied packages are valid installation targets, not release
sources.

## Versioned Central Runtime

For a local workspace with multiple agent hosts, install the verified archive
through `scripts/tmcp_runtime.mjs`. It keeps immutable release directories under
`~/.tmcp/runtime/versions/`, records the active and previous releases in
`state.json`, and exposes the active package through a checked compatibility
symlink. See [CENTRAL_RUNTIME.md](CENTRAL_RUNTIME.md) for the update, parity, and
rollback contract.

The legacy `$HOME/plugins/tmcp` alias may remain as a generated compatibility
surface for existing repository `.mcp.json` files. It must resolve to the
versioned runtime's `active` symlink and must pass `tmcp_runtime.mjs doctor`; it
is not a source checkout or an independent server.

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
