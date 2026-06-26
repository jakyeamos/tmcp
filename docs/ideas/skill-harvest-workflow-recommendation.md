# Skill Harvest Workflow Recommendation

Status: user-originated concept.

This note captures the idea that a TMCP skill harvest can reveal a person's or team's coding-quality priorities, and that TMCP should use those signals to recommend custom expert workflows.

This is separate from [backfill-quality-gate-proposal.md](backfill-quality-gate-proposal.md). The backfill quality gate is about safe durable ingestion. This idea is about using harvested skill signals to decide which expert workflows an agent should become unusually good at.

## Thesis

The skills, agent instructions, editor rules, and workflow documents on a machine say a lot about what the operator values in software work.

If a harvest contains many UI, design-system, frontend, screenshot, and visual-polish signals, then a UI audit workflow is a natural recommendation. If the harvest instead contains stronger security, privacy, testing, release, maintainability, or developer-experience signals, TMCP should recommend a different workflow.

TMCP should therefore move beyond fixed workflows and support this loop:

```text
skill harvest
-> priority signal extraction
-> operator/repo quality profile
-> custom workflow recommendations
-> expert packet for selected workflow
-> codebase audit/remediation plan
-> optional implementation after approval
```

## Why This Matters

The high-value TMCP idea is not only "make the agent expert at UI audits." The high-value idea is:

> Use TMCP to infer what expertise this agent should develop from the user's own skill corpus, then apply that expertise to improve codebase quality.

That makes TMCP adaptive. It can recommend the right expert workflow for the person, repo, or team rather than assuming a universal default.

## Priority Signals

Candidate signal families:

| Signal Family | Harvest Evidence | Recommended Workflow |
| --- | --- | --- |
| UI quality | frontend rules, screenshots, visual polish, design systems, responsive layout | `expert_ui_rubric_workflow` |
| Security/privacy | redaction, permissions, secrets, data flow, auth, audit logs | `security_privacy_review_workflow` |
| Testing/quality | TDD, regression tests, coverage, quality gates, CI checks | `test_strategy_and_regression_workflow` |
| Release readiness | release checklists, CI/CD, packaging, deployment, changelogs | `release_readiness_workflow` |
| Developer experience | setup docs, command discovery, onboarding, CLI ergonomics | `developer_experience_workflow` |
| Maintainability | dead code, refactoring, architecture, boundaries, modularity | `maintainability_workflow` |
| Performance | profiling, latency, bundle size, runtime metrics, load tests | `performance_review_workflow` |
| Data correctness | migrations, schemas, validation, pipelines, invariants | `data_integrity_workflow` |

## Recommendation Output

Candidate MCP output shape:

```json
{
  "schema": "tmcp-workflow-recommendation-v1",
  "source_harvest": {
    "source_count": 42,
    "redaction_summary": {},
    "warnings": []
  },
  "priority_profile": {
    "primary_signals": ["ui_quality", "developer_experience"],
    "secondary_signals": ["testing", "release_readiness"],
    "weak_signals": ["security_privacy"],
    "evidence": []
  },
  "recommended_workflows": [
    {
      "id": "expert_ui_rubric_workflow",
      "confidence": 0.91,
      "why": "Harvest contains repeated visual polish, frontend, screenshot, and design-system rules.",
      "starter_prompt": "Use the TMCP expert UI rubric on this project.",
      "expected_artifacts": [
        "expertise packet",
        "scored rubric",
        "evidence-backed audit",
        "ordered remediation plan"
      ]
    }
  ],
  "not_recommended": [
    {
      "id": "security_privacy_review_workflow",
      "reason": "Only weak security/privacy signals were found."
    }
  ]
}
```

## Proposed MCP Tool

Future tool:

```text
tmcp_recommend_workflows
```

Inputs:

- `source_path` or `source_paths`
- `objective`
- `include_globs`
- `exclude_globs`
- `limit`
- `redact_sensitive`
- `candidate_workflows`
- `write_artifacts`
- `output_dir`

Outputs:

- harvest summary
- priority profile
- evidence-backed signal scores
- recommended workflows
- not-recommended workflows with reasons
- starter prompts
- workflow-specific rubric seeds

## Quality Rules

- Recommendations must cite harvest evidence.
- Weak signals should not be overstated.
- The output must separate user-specific evidence from repo-specific evidence when both are present.
- Privacy redaction remains enabled by default.
- Recommendations are advisory until the user selects a workflow.
- Implementation remains approval-gated.

## Example

If a harvest finds strong UI/frontend evidence:

```text
Recommended: expert_ui_rubric_workflow
Reason: repeated UI polish, design-system, responsive-layout, and screenshot-verification instructions.
Starter prompt: Use the TMCP expert UI rubric on this project.
```

If a different machine has stronger security/privacy evidence:

```text
Recommended: security_privacy_review_workflow
Reason: repeated redaction, permission-boundary, secret-handling, and data-flow rules.
Starter prompt: Use TMCP to audit security and privacy risks in this project.
```

## Open Questions

- Should recommendations be based on global user skills, repo-local skills, or a weighted blend?
- Should TMCP persist a reusable priority profile, or recompute it from each harvest?
- How many workflows should be recommended by default?
- What confidence threshold should separate recommended, exploratory, and not-recommended workflows?
- Should recommended workflows be generated dynamically or selected from a curated catalog?

