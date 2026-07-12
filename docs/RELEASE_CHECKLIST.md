# Release Checklist

Use this checklist before claiming a Tier One release.

## Package

- [ ] `LICENSE` exists.
- [ ] `README.md` explains the source nodes -> behavior atoms -> packets -> workflows model and optional AIOS adapter.
- [ ] `.codex-plugin/plugin.json` has current version/cachebuster.
- [ ] `.claude-plugin/plugin.json` has current version.
- [ ] `.claude-plugin/marketplace.json` points at the public GitHub repository.
- [ ] `.mcp.json` declares stdio and launches the Node launcher with relative plugin-root paths.
- [ ] Stable public workflows are labeled stable and documented.
- [ ] Experimental workflows remain shipped, callable, and labeled experimental.
- [ ] MCP `tools/list` includes `tmcp_recommend_workflows`, `tmcp_compose_packet`, `tmcp_runtime_next`, and `tmcp_record_receipt`.
- [ ] Public schemas exist for skill packets, adaptive workflow packs, composed packets, runtime deltas, run receipts, and promoted harvest graphs.
- [ ] `python3 scripts/check_contracts.py .` confirms the canonical registry, manifests, installer, live MCP initialize response, and tool list agree.
- [ ] `python3 scripts/check_install.py .` passes.
- [ ] Clean-copy install check passes with no hardcoded local user paths.
- [ ] Archive creation runs from a clean Git worktree with no staged or unstaged tracked changes.
- [ ] The generated RELEASE_MANIFEST.json lists only approved committed files and matches every archive payload digest and mode.
- [ ] Package safety tests prove that untracked local state, .env files, keys, credentials, symlinks, case/Unicode path collisions, and secret-like content cannot ship.
- [ ] Forged archives with unsafe, unlisted, tampered, or duplicate payloads fail before extraction.

## Verification

- [ ] `python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_contracts.py scripts/check_install.py scripts/check_release_package.py scripts/tmcp_release_archive.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py tmcp_runtime/__init__.py tmcp_runtime/api/__init__.py tmcp_runtime/api/registry.py tmcp_runtime/api/tool_schemas.py` passes.
- [ ] `node --check scripts/tmcp_launcher.mjs` passes.
- [ ] `python3 -m unittest discover -s tests` passes.
- [ ] JSON syntax check passes for plugin, MCP, marketplace, and fixtures.
- [ ] On a secure-persistence host, `python3 scripts/check_release_package.py . --verify-reproducible` passes, including Git-tree containment, a repeat archive digest comparison, manifest/digest validation, frontmatter, link, hardcoded-path, doctor, harvest, recommendation, expert-rubric, composition/runtime/receipt, stable, and experimental gates.
- [ ] Release composition dogfood shows release-readiness packets do not activate UI/browser or repo-behavior spreadsheet gates unless the objective or runtime context asks for them.
- [ ] `claude plugin validate .` passes for the marketplace.
- [ ] `claude plugin validate <plugin-only-copy>` passes for the plugin manifest.
- [ ] Official Codex plugin validator passes, or the validator runtime blocker is recorded.
- [ ] Official skill validator passes, or the validator runtime blocker is recorded.

## Compatibility

- [ ] macOS local run.
- [ ] Linux CI or container run.
- [ ] Windows CI or manual run.
- [ ] POSIX CI proves positive artifact writes, atomic bundles, and replacement safety.
- [ ] Windows CI proves launcher/read-only workflows and that unsupported artifact writes fail closed without creating output.

## Release Evidence

- [ ] `docs/VERIFICATION.md` updated.
- [ ] `docs/RELEASE_EVIDENCE.json` records a successful hosted `verify.yml` main, pull request, or release-tag run for the active manifest version.
- [ ] `python3 scripts/check_release_evidence.py .` passes.
- [ ] A version bump records successful release-PR evidence, then passes a second PR verification before merge; this keeps the evidence gate pre-merge without creating a tag-run self-reference cycle.
- [ ] Archive creation used a clean committed worktree; no dirty-path exception is accepted.
- [ ] `docs/TIER_ONE_RELEASE_RUBRIC.md` score updated.
- [ ] GitHub remote exists and CI has run for `main`, the release PR, or the active release tag.
- [ ] MCP Registry draft reviewed against the current official registry schema.
- [ ] Residual risks are explicit.
