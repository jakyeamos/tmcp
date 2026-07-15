# Central Runtime

TMCP has one canonical source repository and one versioned local runtime. Plugin
caches and repository MCP configuration files are generated consumers; they are
not alternate TMCP source trees.

## Authority map

| Surface | Authority | Policy |
| --- | --- | --- |
| Source | The TMCP Git repository and tagged release commit | Maintained and reviewed source of truth. |
| Package | The deterministic release archive and its SHA-256 | Immutable input to installation. |
| Runtime | `$TMCP_RUNTIME_HOME/versions/<release>` | One directory per release; never overwrite a version. |
| Active switch | `$TMCP_RUNTIME_HOME/state.json` plus `active` | POSIX uses an atomic symlink swap; Windows uses a guarded junction replacement, state records the selected release, and `doctor` detects an interrupted switch. |
| Plugin caches | Codex and Claude generated cache snapshots | Refreshed from the active runtime and checked for parity. |
| Project overlays | Repository-local `AGENTS.md`, domain skills, evidence, and `.mcp.json` | Keep project behavior local; do not copy TMCP core skills into projects. |

The default runtime home is `TMCP_RUNTIME_HOME`, or `~/.tmcp/runtime` when the
variable is unset. The `active` symlink is a compatibility path, not a version
authority; `state.json` and the per-version `runtime-manifest.json` are the
authority used by `status` and `doctor`.

## Install and cut over

Install from a verified release archive. The archive digest is mandatory so a
local update cannot silently replace the package with an unreviewed build:

```bash
node scripts/tmcp_runtime.mjs install \
  --source /path/to/tmcp-v0.5.5.tar.gz \
  --sha256 <release-sha256> \
  --source-commit <tagged-commit> \
  --runtime-home "$HOME/.tmcp/runtime" \
  --activate
```

Then refresh generated surfaces and verify them. Codex's native Git marketplace
checkout is owned by Codex; when it is already pinned to the active tag, the
runtime manager validates it in place rather than replacing it:

```bash
node scripts/tmcp_runtime.mjs sync \
  --runtime-home "$HOME/.tmcp/runtime" \
  --legacy-alias "$HOME/plugins/tmcp" \
  --codex-cache-root "$HOME/.codex/plugins/cache/personal/tmcp" \
  --claude-cache-root "$HOME/.claude/plugins/cache/tmcp/tmcp"
node scripts/tmcp_runtime.mjs doctor \
  --runtime-home "$HOME/.tmcp/runtime" \
  --expected-version 0.5.5 \
  --codex-config "$HOME/.codex/config.toml" \
  --claude-installed-record "$HOME/.claude/plugins/installed_plugins.json"
```

`sync` only adds a new versioned cache entry or replaces a generated marketplace
snapshot after staging it. Existing version directories remain available. A
native Codex marketplace checkout passes only when its
`.codex-marketplace-install.json` source, `v<release>` ref, recorded revision, and non-marker Git
state match the active runtime; stale or dirty native checkouts are rejected and
left untouched. Host metadata such as a Codex marketplace ref or Claude
installed-plugin record must also name the same release and commit. The Claude
marketplace plugin source is pinned to the matching `v<release>` tag; modern
packages with a missing or mutable source ref fail during install. `doctor`
reports any generated cache or skill surface that does not match the active
content digest, and optionally checks native Codex/Claude metadata when those
paths are supplied.

## Automatic update pipeline

The release/update workflow is:

1. Build from the exact tagged commit.
2. Validate the archive, package manifest, launcher, MCP initialize/tools list,
   and representative TMCP workflows.
3. Verify the archive SHA-256 and install it into a new immutable version path.
4. Run `doctor`, `status`, and `list-tools` against the staged version.
5. Sync generated Codex/Claude caches and the compatibility alias.
6. Refresh native Codex/Claude marketplace clients to the same tag, then run
   native provenance and generated parity checks for package content and
   `skills/tmcp/SKILL.md`.
7. Atomically activate the new version only after all checks pass.
8. Retain the previous active version and record the exact source commit and
   digests in the runtime state.

An update fails closed before activation when the archive digest, release
metadata, content digest, skill digest, or MCP smoke check disagrees.

## Rollback

Rollback is local and does not require the network:

```bash
node scripts/tmcp_runtime.mjs rollback --runtime-home "$HOME/.tmcp/runtime"
node scripts/tmcp_runtime.mjs sync --runtime-home "$HOME/.tmcp/runtime" --legacy-alias "$HOME/plugins/tmcp"
node scripts/tmcp_runtime.mjs doctor --runtime-home "$HOME/.tmcp/runtime"
```

Rollback changes the active pointer only. It does not delete the failed version,
so the failed manifest and digest remain available for diagnosis. A second
successful install may prune old versions only after an explicit retention
policy is in place; this package does not perform that cleanup automatically.

## Mismatch rules

- The runtime release is authoritative for executable behavior.
- A skill copy whose digest differs from the active `skills/tmcp/SKILL.md` is
  stale and must not be treated as a current package contract.
- A plugin cache with a different content digest is stale, even when its folder
  name looks current.
- A modern package marketplace source must point at `v<release>`; `main`, a
  missing ref, or another tag is a provenance mismatch. Legacy 0.5.3 metadata
  remains accepted only so the retained rollback version can be activated.
- A Codex native marketplace marker must name the canonical Git source, active
  release tag, and active source commit; any other checkout state is a
  mismatch. Valid native checkouts remain native surfaces instead of being
  compared with the deterministic package digest.
- Project-local instructions may intentionally differ from TMCP core; they are
  overlays, not mismatches.
- The compatibility alias is valid only when it resolves to the active runtime
  and is reported as `pass` by `doctor`.

## Security and offline behavior

The manager rejects unsafe archive paths and package symlinks, requires a digest
for archives, stages copies before replacement, and never overwrites an existing
release version with different content. Installing from a previously verified
local archive and rolling back require no network. Network publication and host
marketplace refresh remain separate from the local activation step. Windows
junction replacement has a brief guarded gap because the platform does not
replace directory links atomically through Node's portable rename API; the
version directories and state file remain intact and `doctor` is the recovery
check.
