# TMCP Project Truth

## Current State

- Branch: `codex/skill-eval-dogfood`
- Last completed change: `fc063dd` records the controlled dogfood plan, traces, report, generated artifacts, pattern catalog, and evidence-led guidebook.
- Verification: 492 tests passed, 3 skipped, and 108 subtests passed; Ruff formatting/lint, basedpyright, contract, install-shape, and release-evidence checks passed.

## Current Position

- Plan/report v0.2 validates stable row identity, canonical pattern contracts, exact original/one-section-ablation attachments, blinded provenance, judge evidence, paired repetitions, and actual intervention-control lift.
- Whole-section ablations can support only section-granularity claims. Static detections and legacy v0.1 plans remain hypotheses.
- Corpus promotion remains manual and requires 72 runs, a 95% lift interval above zero, no agent-configuration reversal, and no safety or cost regression.
- Dogfood experiment `skill-eval-af3806a4873b77a0` completed 8 blind judged traces: intact `eval-skills` passed 4/4 and the `Workflow`-section ablation passed 0/4.
- The scorer reports a controlled-single-configuration section claim with intervention-control lift `-1.0` and 95% interval `[-1.0, -0.02]`; promotion remains on hold.
- The checked-in catalog and guidebook preserve the candidate status, evidence scope, promotion gaps, suspected-only static finding, and reproducible evidence bundle.

## Next Step

- Replace inherited npm example text with the repository's pnpm convention, regenerate catalog parity, then run the release-package and final branch gates.

## Blockers

- None.

## Risks

- The controlled single-configuration result supports an internal section-level candidate but cannot establish a corpus-wide tried-and-true pattern.
- One blinded judge flagged live-checkout cleanup wording as a safety regression; treat it as an unresolved counterexample until the instruction and judge calibration are tested directly.
- Anti-pattern claims still require a future isolated removal or presence intervention; static matches remain suspected only.
