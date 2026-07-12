# TMCP Workflows

TMCP ships stable public workflows and experimental workflows. Experimental means the workflow is included, callable, tested where coverage exists, and preserved for compatibility, but its public contract may still change.

## Composable Runtime Path

For most adaptive agent runs, prefer a composed packet over a dedicated workflow list:

1. Start with `tmcp_compose_packet` for the objective, project path, source paths, and phase.
2. Follow only the packet's active instructions, required reads, tool/script prompts, verification gates, and stop conditions that fit the current task.
3. Call `tmcp_runtime_next` when files changed, tests fail, browser evidence appears, the user redirects the goal, or the run enters verification/final. For an explicit serialized project run, use the same `session_id` and absolute `project_path` from compose through full recompile; otherwise pass the previous packet inline.
4. Call `tmcp_record_receipt` after meaningful verification or outcome so future ranking can learn from the run.

Composed packets and receipts are advisory. They never override system, developer, user, or project instructions.

## Stable Public Workflows

- `skill-harvest`: harvest local skills, rules, prompts, and process docs into source nodes and behavior atoms.
- `workflow-recommendation`: recommend workflows from harvested evidence and include stability metadata.
- `expert-rubric-review`: produce an expertise packet, scored rubric, evidence audit, remediation plan, and verification expectations.
- `release-readiness`: review release blockers, evidence gaps, package state, and verification expectations.
- `dx-audit`: review setup, onboarding, command discoverability, validation loops, and maintainer handoff readiness.
- `tmcp_compose_packet`: compose small task/phase packets from harvested instructions and promoted cache evidence.
- `tmcp_runtime_next`: adapt packet deltas from runtime evidence.
- `tmcp_record_receipt`: persist advisory run receipts under `TMCP_HOME` or `~/.tmcp`.

## Experimental Workflows

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
