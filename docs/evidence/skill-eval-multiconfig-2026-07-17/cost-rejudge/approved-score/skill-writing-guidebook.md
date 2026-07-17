# TMCP Skill Writing Guidebook

Experimental v0.1 artifact generated from skill evaluation findings.

## Evidence levels

Every pattern claim should carry an evidence level:

- `hypothesis`
- `static_review`
- `dogfooded`
- `controlled_single_agent_eval`
- `controlled_multi_agent_eval`
- `production_reinforced`

## Patterns

### Staged evaluation workflow section

**Pattern ID:** `evaluation.staged-workflow-section`
**Status:** supported
**Evidence level:** controlled_multi_agent_eval
**Applies to:** skill_evaluation, skill_writing
**Internal atoms:** behavior-verification, evidence-backed-claims, quality-gate-disclosure
**Observed intervention-control lift:** -0.473 (support direction: negative)
**Lift interval:** 95% [-0.75, -0.194] (fixture-block-bootstrap-by-configuration)
**Sample:** 72 traces, 6 fixtures, 3 agent configurations
**Promotion:** hold

- Promotion gap: clustered analysis policy was not predeclared
- Promotion gap: minimum fixture control pass rate 0.000 is below required 0.500

Prefer:

> Use an explicit workflow section that separates blind runs, judging, repetition, diagnosis, and re-evaluation.

Avoid:

> Test the skill a few times and improve it.

### Missing observable output contract

**Pattern ID:** `output.missing-observable-contract`
**Status:** suspected
**Evidence level:** static_review
**Applies to:** skill_writing
**Internal atoms:** artifact-contract
**Promotion:** hold

- Promotion gap: no behaviorally judged contrast

Prefer:

> Return sources inspected, skipped sources, packet summary, and verification expectations.

Avoid:

> Return a helpful summary.

