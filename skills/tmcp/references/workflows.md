# TMCP Workflows

TMCP ships stable public workflows and experimental workflows. Experimental means the workflow is included, callable, tested where coverage exists, and preserved for compatibility, but its public contract may still change.

## Composable Runtime Path

For most adaptive agent runs, prefer a composed packet over a dedicated workflow list:

1. Start with `tmcp_compose_packet` for the objective, project path, source paths, and phase.
2. Follow only the packet's active instructions, required reads, tool/script prompts, verification gates, and stop conditions that fit the current task.
3. Call `tmcp_runtime_next` when files changed, tests fail, browser evidence appears, the user redirects the goal, or the run enters verification/final. For an explicit serialized project run, use the same `session_id` and absolute `project_path` from compose through full recompile; otherwise pass the previous packet inline.
4. Call `tmcp_record_receipt` after meaningful verification or outcome so future ranking can learn from the run.

Composed packets and receipts are advisory. They never override system, developer, user, or project instructions.

## Stability Scopes

- **Stable skill packages:** `tmcp`, `tmcp-skill-harvest`, `tmcp-workflow-recommendation`, `tmcp-release-readiness`, and `tmcp-dx-audit` are stable routing packages.
- **Stable curated workflow templates:** `release-readiness` and `dx-audit` are the only stable recommendation-catalog templates.
- **Stable MCP tool contracts:** `tmcp_doctor`, `tmcp_status`, `tmcp_explain`, `tmcp_compose_packet`, and `tmcp_runtime_next` are stable. `tmcp_harvest_skills`, `tmcp_evaluate_skills`, `tmcp_recommend_workflows`, `tmcp_promote_harvest`, `tmcp_record_receipt`, and `expert_rubric_review_plan` are experimental.

Do not infer stability across these scopes. A stable skill package can route to an experimental tool, and an experimental tool can recommend a stable curated template.

## Stable Public Workflows: Curated Templates

- `release-readiness`: review release blockers, evidence gaps, package state, and verification expectations.
- `dx-audit`: review setup, onboarding, command discoverability, validation loops, and maintainer handoff readiness.

## Experimental Workflows: Curated Templates

- UI rubric.
- Security/privacy audit.
- Test strategy.
- Adaptive workflow pack.
- Custom rubric generation.
- Routing policy generation.
- Skill gap analysis.
- Incident postmortem.
- Architecture decision.
- Migration readiness.
- Agent handoff.
- PR risk review.
- Performance readiness.
- Data integrity audit.
- Public-sector readiness.
- Repo behavior spec loop.

These workflows remain shipped and callable through existing skill folders, CLI aliases, MCP behavior, recommendation catalog entries, examples, and tests. Do not delete or hide them. Label them experimental when recommended or cited.

## Required Output Sections

Every workflow should produce predictable sections:

- Sources inspected.
- Skipped sources and why.
- Packet summary.
- Extracted behavior atoms.
- Evidence gaps.
- Recommendation or remediation plan.
- Verification expectations.
