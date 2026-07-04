# TMCP Tier One Release Rubric

Tier One means the plugin is safe, portable, explainable, and useful for someone who does not share the original author's machine, AIOS install, Codex cache, operating system, or project conventions.

Release scope for this rubric: Codex plugin environments with Node.js and Python 3 available. The MCP command is a Node launcher that discovers Python through `TMCP_PYTHON`, `py -3`, `python`, or `python3`, depending on platform. macOS behavior is locally verified; Linux and Windows behavior are hosted-CI verified through GitHub Actions.

## Release Gate

A Tier One release requires:

- Overall score: 90/100 or higher.
- No dimension below pass threshold.
- All hard gates pass.
- A fresh verification record exists for the release candidate.

## Scorecard

| Dimension | Weight | Pass | Current | Gate |
| --- | ---: | ---: | ---: | --- |
| Portable install and packaging | 12 | 10 | 12 | Hard |
| Standalone TMCP packet model | 12 | 10 | 12 | Hard |
| Skill harvest robustness | 12 | 10 | 12 | Hard |
| Privacy and sensitive data handling | 12 | 10 | 12 | Hard |
| MCP protocol reliability | 10 | 8 | 10 | Hard |
| Expert rubric workflow quality | 10 | 8 | 10 | Hard |
| Tests and compatibility matrix | 10 | 8 | 10 | Hard |
| Documentation and examples | 8 | 7 | 8 | Hard |
| Optional AIOS adapter quality | 6 | 4 | 6 | Soft |
| Maintainability and modularity | 5 | 4 | 5 | Soft |
| Release operations | 3 | 3 | 3 | Hard |

Current score: 100/100 for the scoped `0.3.3` release candidate. Hosted release evidence is recorded from successful `main` `verify.yml` run `28711514414`.

## Dimensions

### Portable Install And Packaging

Pass criteria:

- Plugin can be installed from a clean checkout or packaged artifact.
- No user-specific absolute paths are required.
- MCP launch works from installed plugin cache and source checkout.
- README explains install, update, uninstall, and troubleshooting.
- First-run doctor gives client-specific install and smoke-test guidance.
- License and marketplace metadata are present.

Required evidence:

- Plugin manifest validation.
- Clean install test from a temporary or cloned location.
- MCP `tools/list` after install.

### Standalone TMCP Packet Model

Pass criteria:

- Packet schema is documented and stable enough for external tools.
- A machine-readable packet schema and stability policy exist.
- Packet includes selected nodes, skipped nodes, source tiers, behavior atoms, traversal trace, output contract, token estimates, and shortcut governance.
- Packet compilation works without AIOS.
- AIOS enriches but does not define core behavior.
- Composition tools return small current-task packets, runtime deltas, and receipts with machine-readable schemas.
- Composer ranking avoids unrelated workflow spillover such as UI/browser checks or repo-behavior spreadsheets on release-readiness tasks.

Required evidence:

- Packet spec document.
- Tests for audit, implementation, planning, and harvest task routing.
- Golden packet fixtures for representative prompts.
- Golden composition tests for release readiness, repo behavior sweeps, UI work, runtime adaptation, receipts, and `--compose` compatibility.

### Skill Harvest Robustness

Pass criteria:

- Harvest accepts arbitrary roots and multiple roots.
- Harvest supports include/exclude globs, size limits, symlink policy, and artifact output.
- Harvest classifies source types without relying on Codex, AIOS, Claude, or a single folder layout.
- Harvest reports warnings instead of failing on missing or skipped sources.
- Vendor, dependency, cache, build, VCS, and generated plugin-cache trees are pruned by default.

Required evidence:

- Tests against synthetic generic repo layouts.
- Tests against missing paths, file roots, large files, and excluded dirs.
- Documented input schema and output schema.

### Privacy And Sensitive Data Handling

Pass criteria:

- Harvest does not return obvious secrets in excerpts, frontmatter, keywords, warnings, or artifact output.
- Secret-like values are redacted with stable labels.
- Redaction counts are reported.
- Users can disable or tune redaction only through explicit parameters.
- Binary files and large files are skipped before content processing.

Required evidence:

- Tests for API keys, bearer tokens, private keys, env assignments, GitHub tokens, OpenAI keys, and long high-entropy strings.
- Review of artifact output for redacted values.

### MCP Protocol Reliability

Pass criteria:

- Server handles `initialize`, `tools/list`, `tools/call`, `ping`, `resources/list`, and `prompts/list`.
- Tool errors return structured MCP errors or `isError` results.
- All tools and public runtime artifacts have JSON schemas with required fields.
- Protocol tests cover sequential calls in one process.

Required evidence:

- Protocol-level test that uses `Content-Length` framing.
- Negative test for invalid tool arguments.

### Expert Rubric Workflow Quality

Pass criteria:

- Review plan produces expertise packet, scored rubric, audit report, remediation plan, and approval-gated handoff.
- UI, security/privacy, developer experience, and general profiles are selected correctly.
- Evidence gaps are explicit when evidence is absent.
- Remediation slices are independently actionable and have verification expectations.

Required evidence:

- Tests for profile selection and no-evidence behavior.
- Example artifact bundle.

### Tests And Compatibility Matrix

Pass criteria:

- Tests run with only Python standard library.
- MCP launch goes through a cross-platform Node launcher.
- Tests cover macOS/Linux and Windows launcher selection semantics where possible.
- CI covers macOS, Linux, and Windows.

Required evidence:

- `python3 -m unittest discover` or equivalent.
- Manual compatibility notes.

### Documentation And Examples

Pass criteria:

- README explains what TMCP is, what the plugin does, and what AIOS adds.
- Distribution docs cover GitHub, Codex, Claude Code, Claude Desktop, and MCP Registry paths.
- Distribution docs include a decision matrix across client surfaces.
- Quickstart includes standalone harvest, packet explain, and expert rubric examples.
- Example workflows prove developer-experience, security/privacy, and release-planning use cases beyond UI review.
- Docs include packet schema and harvest output shape.
- Security/privacy behavior is documented.

Required evidence:

- README.
- Packet spec.
- Example command/request snippets.

### Optional AIOS Adapter Quality

Pass criteria:

- AIOS adapter checks availability without hard failure.
- Adapter failures fall back to standalone when adapter mode is `auto`.
- Adapter mode `aios` reports clear errors when AIOS is unavailable.
- Adapter output is normalized enough for callers to understand the source.

Required evidence:

- Tests or live checks for `auto`, `standalone`, and `aios` modes.

### Maintainability And Modularity

Pass criteria:

- MCP transport, packet compiler, harvester, rubric workflow, redaction, and AIOS adapter are separated or have clear internal boundaries.
- No hidden network dependency.
- No large generated artifacts are stored in the plugin.
- Functions are small enough to test directly.

Required evidence:

- Code organization review.
- Dead/generated file check.

### Release Operations

Pass criteria:

- Version and cachebuster are updated for release candidate.
- Codex and Claude plugin manifests are validated.
- Public GitHub release path is documented.
- MCP Registry draft is prepared and clearly marked until accepted.
- Release checklist is complete.
- Known limitations are documented.
- A fresh verification record links commands, outputs, and residual risks.
- `docs/RELEASE_EVIDENCE.json` records a successful hosted `verify.yml` main, pull request, or release-tag run for the active manifest version, and `python3 scripts/check_release_evidence.py .` passes.

Required evidence:

- Release notes or verification record.
- Clean file inventory.
- Hosted release evidence record.

## Work Order

1. Submit to Claude community marketplace after the GitHub repo is live.
2. Review and submit MCP Registry metadata against the current official schema.
3. Run a manual Windows end-user install and record results.
4. Expand semantic extraction beyond keyword heuristics.
5. Split packet compiler, harvester, and rubric workflow into separate modules if growth continues.
