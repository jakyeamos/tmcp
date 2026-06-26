---
name: tmcp
description: Invoke standalone TMCP skill-packet workflows, skill harvesting, and expert rubric remediation from any project or Codex thread.
---

# TMCP

Use this skill whenever the user asks for TMCP, a TMCP packet, TMCP traversal, TMCP skill harvest, TMCP expert workflow, TMCP expert rubric, expert rubric workflow, expert UI rubric, UI rubric workflow, or asks to judge/audit/review something "using TMCP".

TMCP is a skill-packet and skill-usage model. AIOS is an optional adapter and reference implementation, not a requirement for the concept.

## Routing

- `TMCP expert UI rubric`, `expert UI rubric`, `use the TMCP expert rubric on <project>`, and similar wording mean the TMCP `expert_rubric_remediation_v1` workflow.
- This is an audit-and-plan workflow: compile a TMCP expertise packet, synthesize a scored rubric, audit concrete evidence, and produce an ordered remediation plan.
- Do not treat expert-rubric requests as generic UI reviews, Browser-only visual checks, or immediate implementation requests unless the user explicitly asks for edits.
- If rendered UI evidence is needed, use the available Browser path for screenshots/runtime inspection, but keep TMCP as the governing workflow and record when rendered evidence was unavailable.
- When the user asks to harvest skills, gather local skill definitions, agent instruction files, editor rules, repository process docs, and markdown workflow docs into source nodes, classify behavior atoms, and compile the smallest useful packet. Do not assume AIOS, Codex, Claude, or any one directory layout exists.

## Preferred Tools

When the TMCP MCP tools are available, use:

- `tmcp_doctor` to check first-run readiness and client-specific install guidance.
- `tmcp_status` to check whether standalone TMCP and the optional AIOS adapter are available.
- `tmcp_explain` to compile and inspect the task-specific TMCP packet.
- `tmcp_harvest_skills` to turn local skills/docs into TMCP source nodes and a reusable packet seed.
- `tmcp_recommend_workflows` to infer priority signals from a skill harvest and recommend custom expert workflows.
- `expert_rubric_review_plan` for the expert rubric remediation workflow.

The MCP tools run standalone. When AIOS is available, they may use the AIOS adapter for richer graph traversal, persisted receipts, and workflow artifacts.

## Skill Harvest

`tmcp_harvest_skills` is portable. It accepts one `source_path` or many `source_paths`, optional `include_globs` and `exclude_globs`, file-size and excerpt limits, and optional artifact writing. The default harvest includes common skill and instruction surfaces such as `SKILL.md`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `.cursor/rules`, `.github`, `docs`, `planning`, `workflows`, and markdown files. It prunes dependency, build, cache, VCS, and generated plugin-cache directories by default.

Harvest output should include source paths, source types, source tiers, frontmatter when present, behavior atoms, excerpts, warnings for skipped or missing inputs, and a `packet_seed`. Treat warnings as part of the packet evidence, not as fatal errors unless no usable sources were found.

## Example Workflows

TMCP is not only a UI audit path. Use the same packet model for:

- Developer onboarding audits: harvest README, contribution, command, and CI docs; route to the developer-experience rubric.
- Security/privacy harvest audits: keep redaction enabled, inspect redaction summaries, and route to the security/privacy rubric.
- Release readiness planning: compile a planning packet, name evidence gaps, and produce ordered remediation slices before implementation.
- Skill-harvest workflow recommendation: infer coding-quality priorities from harvested skills and recommend UI, security, testing, release, DX, maintainability, performance, or data-integrity workflows.

When MCP tools are unavailable but AIOS exists, use the AIOS CLI directly:

```bash
cd "${AIOS_ROOT:-$HOME/AIOS}"
uv run python bin/aios.py tmcp explain "<objective>" --project-path "<project-path>" --json
```

```bash
cd "${AIOS_ROOT:-$HOME/AIOS}"
uv run python bin/aios.py tmcp review-plan "<objective>" --project-path "<project-path>" --output-dir "<project-path>/.aios/reviews/<run-id>" --evidence-json '<json>'
```

## Output Contract

For expert rubric work, produce or cite:

- TMCP expertise packet or `tmcp explain` output
- scored rubric
- evidence-backed audit findings or explicit evidence gaps
- ordered remediation plan with verification expectations
- implementation handoff only after explicit user approval

When neither MCP nor AIOS is available, still follow the same structure manually: task-specific packet, behavior atoms, selected/skipped nodes, scored rubric, evidence-backed audit or explicit evidence gaps, remediation slices, and approval-gated handoff.
