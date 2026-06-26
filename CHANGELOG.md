# Changelog

## Unreleased

- Added a direct CLI surface through `node scripts/tmcp_launcher.mjs <command>` for doctor, status, explain, harvest, recommend, and review-plan workflows.
- Improved CLI argument handling so schema array flags accept both single and repeated values.
- Pruned generated `.aios` and `.tmcp` run artifacts from default skill harvests.
- Narrowed high-entropy redaction to avoid corrupting normal markdown workflow links.
- Expanded agent-facing CLI and TMCP routing instructions.

## 0.2.2 - 2026-06-26

- Added `tmcp_recommend_workflows` to infer coding-quality priority signals from harvested skill sources and recommend custom expert workflows with evidence.
- Added workflow recommendation examples and updated quickstart/docs.

## 0.2.1 - 2026-06-26

- Added `tmcp_doctor` for first-run readiness checks across Codex, Claude Code, Claude Desktop, and plain MCP clients.
- Added quickstart, marketplace matrix, packet stability policy, and machine-readable packet schema.
- Added non-UI example workflows for developer onboarding, security/privacy harvest review, and release readiness planning.

## 0.2.0 - 2026-06-26

- Added standalone TMCP MCP server with packet explain, skill harvest, status, and expert rubric remediation tools.
- Added Codex plugin metadata, marketplace-ready assets, and cross-platform Node launcher.
- Added Claude Code plugin metadata and GitHub-hosted Claude marketplace catalog.
- Added Claude Desktop manual MCP install documentation.
- Added release/package validation for clean-copy installs.
