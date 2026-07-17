# TMCP Project Truth

## Current State

- Branch: `codex/skill-eval-dogfood`
- Last completed change: `9cff7bf` makes skill-evaluation rows uniquely identifiable, preserves one-factor variant contracts, and carries output contracts through composed packets.
- Verification: 100 focused evaluator/composition tests passed; CLI plan smoke wrote `/private/tmp/tmcp-foundation-smoke-20260717-a/tmcp-skill-evaluation-plan.json` with unique row IDs and non-redacted content digests.

## Current Position

- The static planner and packet-contract comparison are operational.
- Behavioral evidence and guidebook promotion are not yet trustworthy because legacy scoring still infers controlled evidence from trace presence instead of validated provenance, repetitions, paired controls, and judged case verdicts.

## Next Step

- Replace optimistic guidebook promotion with paired, blinded evidence analysis and run repeated blind dogfood trials before promoting any skill pattern.

## Blockers

- None.

## Risks

- `evaluation_policy.py` and `evaluation_scoring.py` exceed the changed-line quality gate's preferred source-size limit; split them by responsibility during the evidence-analysis change.
- Static findings remain hypotheses and must not be described as tried-and-true patterns.
