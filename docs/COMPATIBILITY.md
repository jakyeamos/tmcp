# Compatibility Notes

## Runtime

- Python 3.10+ recommended.
- Node.js 20+ recommended for the cross-platform MCP launcher.
- The MCP server uses only the Python standard library.
- No network access is required for standalone mode.
- `TMCP_PYTHON` may be set to an explicit Python executable when automatic discovery is not enough.

## Operating Systems

Current verification:

- macOS: tested locally with Node and Python 3.
- Linux: hosted GitHub Actions pass on `ubuntu-latest` with Node 20 and Python 3.10/3.13.
- Windows: the launcher and non-persisting workflows are supported. The launcher prefers the Windows `py -3` launcher before falling back to `python` and `python3`.

## Filesystem Assumptions

- Plugin launch `cwd` is the plugin root.
- Codex MCP config declares `"type": "stdio"` and then launches the bundled Node entrypoint.
- MCP launcher path is relative: `scripts/tmcp_launcher.mjs`.
- Python server path is relative from the launcher: `scripts/tmcp_mcp_server.py`.
- Harvest roots may be files or directories.
- Symlink traversal is disabled by default.
- Dependency, build, cache, VCS, coverage, and generated plugin-cache directories are pruned by default.
- Adaptive workflow recommendations are derived from harvested text, frontmatter, paths, source types, keywords, behavior atoms, and source contribution labels. Overlapping labels are reported in adaptive workflow packs so duplicate sources can be consolidated or ranked. Recommendations remain advisory until the user selects a workflow.

## Secure Artifact Persistence

TMCP separates portable analysis from durable local artifacts. A host that exposes
descriptor-relative, no-follow directory operations can safely persist harvests,
evaluations, reviews, promotions, receipts, and explicitly requested packet
sessions. On a host without those
primitives, write-capable operations fail closed before creating an output path;
continue with `write_artifacts=false` for preview and analysis workflows.

`doctor` and `status` report this capability. A successful launcher check does
not imply that the host can safely persist artifacts.

Packet sessions additionally require an explicit absolute project path. They retain one
redacted latest-packet record for a single serialized run under that project;
they are not a portable fallback, history store, or concurrent-run registry.
Use inline `previous_packet` data for full recompiles when durable writes are
unavailable.

## 0.5.0 Compatibility Preparation

The planned 0.5.0 release preserves the public MCP tools, CLI aliases, launcher,
and v0.1 packet schemas while changing implementation ownership and state-effect
defaults. Composition and runtime adaptation default to `cache_policy=none`;
global cache reads and durable writes are explicit opt-ins. `adapter=auto` stays
standalone, and explicit AIOS requests fail closed for known sensitive values.

Legacy `promoted-harvest.json` summaries remain readable through an in-memory
projection to the current promotion graph. Current graph files take precedence,
and migration never rewrites or deletes source artifacts. Receipts and
project-local sessions have no alternate shipped schema and remain strict.

The 0.5.0 release-candidate version surfaces are now updated together, and the
evidence record points to successful post-cutover hosted PR run `29285497867`,
and final rerun `29285802846` passed. The draft PR is ready for review.

## 0.5.1 Central Runtime Migration

The 0.5.1 distribution surface adds a versioned local runtime manager without
changing the public MCP tool names, packet schemas, or portable relative
launcher contract. Runtime activation is local and explicit: a verified archive
is installed under an immutable release directory, `state.json` records the
active/previous releases, and `active` is switched atomically. The previous
release remains available for offline rollback.

Codex and Claude caches are generated install surfaces. Repository-specific
`AGENTS.md`, domain skills, evidence, and project instructions remain local. A
compatibility alias may continue serving existing absolute `.mcp.json` entries,
but `tmcp_runtime.mjs doctor` must prove that it resolves to the active release.

## Known Gaps

- The current storage implementation intentionally denies artifact persistence on
  Windows rather than using a pathname-based fallback vulnerable to reparse-point
  races. Read-only exact-file inputs use validated path reads on Windows because
  the platform lacks `O_NOFOLLOW`; descriptor identity checks still close the
  ordinary read path if a file changes before or during open. A dedicated, tested
  Windows backend is required before durable artifact writes can be claimed
  there; a manual install cannot remove that limitation.
