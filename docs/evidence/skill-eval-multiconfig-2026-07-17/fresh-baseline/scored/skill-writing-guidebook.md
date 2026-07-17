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
**Status:** candidate
**Evidence level:** static_review
**Applies to:** skill_evaluation, skill_writing
**Internal atoms:** behavior-verification, evidence-backed-claims, quality-gate-disclosure
**Sample:** 0 traces, 0 fixtures, 0 agent configurations
**Promotion:** hold

- Promotion gap: cross-model confirmation: runner model gpt-5.6-luna fixture count 0 is below required 6
- Promotion gap: cross-model confirmation: runner model gpt-5.6-luna repetitions are below required 2
- Promotion gap: cross-model confirmation: runner model gpt-5.6-sol fixture count 0 is below required 6
- Promotion gap: cross-model confirmation: runner model gpt-5.6-sol repetitions are below required 2
- Promotion gap: cross-model confirmation: runner model gpt-5.6-terra fixture count 0 is below required 6
- Promotion gap: cross-model confirmation: runner model gpt-5.6-terra repetitions are below required 2
- Promotion gap: fixture_count 0 is below required 6
- Promotion gap: fixture_family_count 0 is below required 3
- Promotion gap: agent_configuration_count 0 is below required 3
- Promotion gap: minimum_repetitions_per_cell 0 is below required 2
- Promotion gap: aligned absolute lift missing is below required 0.100
- Promotion gap: aligned 95% lift interval lower bound missing does not clear zero
- Promotion gap: aligned clustered 95% lift interval lower bound missing does not clear zero
- Promotion gap: control pass rate missing is below required 0.500
- Promotion gap: minimum fixture control pass rate missing is below required 0.500

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
