# Release Checklist

Use this checklist before claiming a Tier One release.

## Package

- [ ] `LICENSE` exists.
- [ ] `README.md` explains standalone mode and optional AIOS adapter.
- [ ] `.codex-plugin/plugin.json` has current version/cachebuster.
- [ ] `.claude-plugin/plugin.json` has current version.
- [ ] `.claude-plugin/marketplace.json` points at the public GitHub repository.
- [ ] `.mcp.json` declares stdio and launches the Node launcher with relative plugin-root paths.
- [ ] Focused Codex router skills exist for default workflow templates and adaptive workflow-pack generation.
- [ ] `python3 scripts/check_install.py .` passes.
- [ ] Clean-copy install check passes.

## Verification

- [ ] `python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py` passes.
- [ ] `node --check scripts/tmcp_launcher.mjs` passes.
- [ ] `python3 -m unittest discover -s tests` passes.
- [ ] JSON syntax check passes for plugin, MCP, marketplace, and fixtures.
- [ ] `python3 scripts/check_release_package.py .` passes.
- [ ] `claude plugin validate .` passes for the marketplace.
- [ ] `claude plugin validate <plugin-only-copy>` passes for the plugin manifest.
- [ ] Official Codex plugin validator passes, or the validator runtime blocker is recorded.
- [ ] Official skill validator passes, or the validator runtime blocker is recorded.

## Compatibility

- [ ] macOS local run.
- [ ] Linux CI or container run.
- [ ] Windows CI or manual run.

## Release Evidence

- [ ] `docs/VERIFICATION.md` updated.
- [ ] `docs/TIER_ONE_RELEASE_RUBRIC.md` score updated.
- [ ] GitHub remote exists and CI has run.
- [ ] MCP Registry draft reviewed against the current official registry schema.
- [ ] Residual risks are explicit.
