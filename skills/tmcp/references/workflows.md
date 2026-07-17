# TMCP Workflows

TMCP ships stable public workflows and experimental workflows. Experimental means the workflow is included, callable, tested where coverage exists, and preserved for compatibility, but its public contract may still change.

## Composable Runtime Path

For substantial multi-step, tool-using, high-stakes, or skill-relevant runs, the host should invisibly prefer compositional routing over a dedicated workflow list. Bypass trivial conversation and status-only replies.

1. Call `tmcp_prepare_composition` for bounded source slices and the semantic-proposal contract.
2. The host proposes cited task facets, skill roles, typed relationships, ordering, and gates. TMCP validates and compiles them through `tmcp_compose_packet`.
3. The agent executes the active stage only; supporting/evidence sources cannot become instructions, and unmet gates keep later stages deferred.
4. Call `tmcp_runtime_next` when files, commands, failures, browser evidence, verification, or user direction changes the graph. Use a full recompile when the operating contract may change.
5. Record meaningful outcomes. Review and promote project recipes separately; successful receipts never auto-promote.

Composed packets and receipts are advisory. They never override system, developer, user, or project instructions, and TMCP never executes the work.

## Stability Scopes

- **Stable skill packages:** `tmcp`, `tmcp-skill-harvest`, `tmcp-workflow-recommendation`, `tmcp-release-readiness`, and `tmcp-dx-audit` are stable routing packages.
- **Stable curated workflow templates:** `release-readiness` and `dx-audit` are the only stable recommendation-catalog templates.
- **Stable MCP tool contracts:** `tmcp_doctor`, `tmcp_status`, `tmcp_explain`, `tmcp_compose_packet`, and `tmcp_runtime_next` are stable. `tmcp_prepare_composition`, harvest, evaluation, recommendation, promotion, receipt, and expert-rubric tools are experimental.

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
