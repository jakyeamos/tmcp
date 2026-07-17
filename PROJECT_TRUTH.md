# TMCP Project Truth

## Current State

- Branch: `codex/skill-eval-dogfood`
- Last completed change: `bb8041a` makes skill-evaluation evidence claim-specific, paired, blinded, repeatable, and promotion-gated.
- Verification: 492 tests passed, 3 skipped, and 108 subtests passed; Ruff formatting/lint, basedpyright, contract, install-shape, and release-evidence checks passed.

## Current Position

- Plan/report v0.2 validates stable row identity, canonical pattern contracts, exact original/one-section-ablation attachments, blinded provenance, judge evidence, paired repetitions, and actual intervention-control lift.
- Whole-section ablations can support only section-granularity claims. Static detections and legacy v0.1 plans remain hypotheses.
- Corpus promotion remains manual and requires 72 runs, a 95% lift interval above zero, no agent-configuration reversal, and no safety or cost regression.

## Next Step

- Run the repeated blind `eval-skills` Workflow-section dogfood and record its plan, artifacts, judged traces, report, and bounded guidebook conclusion.

## Blockers

- None.

## Risks

- A controlled single-agent dogfood result can support an internal section-level candidate but cannot establish a corpus-wide tried-and-true pattern.
- Anti-pattern claims still require a future isolated removal or presence intervention; static matches remain suspected only.
