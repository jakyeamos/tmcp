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
- Linux: CI recipe is included for `ubuntu-latest` with Node 20 and Python 3.10/3.13. The code uses only standard libraries and relative plugin-root paths.
- Windows: CI recipe is included for `windows-latest` with Node 20 and Python 3.10/3.13. The launcher prefers the Windows `py -3` launcher before falling back to `python` and `python3`.

## Filesystem Assumptions

- Plugin launch `cwd` is the plugin root.
- MCP launcher path is relative: `scripts/tmcp_launcher.mjs`.
- Python server path is relative from the launcher: `scripts/tmcp_mcp_server.py`.
- Harvest roots may be files or directories.
- Symlink traversal is disabled by default.
- Dependency, build, cache, VCS, coverage, and generated plugin-cache directories are pruned by default.

## Known Gaps

- CI workflow is present for macOS, Linux, and Windows, but has not been observed running from a hosted remote in this local workspace.
- Windows support is launcher-ready and CI-declared, but still needs a hosted or manual Windows run before it can be called field-proven.
