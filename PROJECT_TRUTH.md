# TMCP Project Truth

## Current State

- Branch: `codex/skill-eval-dogfood`
- Last completed change: `73f0c03` adds a resumable 72-cell skill-evaluation campaign harness with blind prompt preflight, fresh runner/judge sessions, exact keyed judgments, artifact-bound traces, and usage accounting.
- Verification: 156 focused evaluator/routing tests, Ruff, basedpyright, compile, a live one-cell run, and an artifact-validating no-call resume replay passed. Pre-CR flagged the 1,296-line harness above the 700-line script budget.

## Current Position

- Plan/report v0.2 validates stable row identity, canonical pattern contracts, exact original/one-section-ablation attachments, blinded provenance, judge evidence, paired repetitions, and actual intervention-control lift.
- Whole-section ablations can support only section-granularity claims. Static detections and legacy v0.1 plans remain hypotheses.
- Corpus promotion remains manual and requires 72 runs, a 95% lift interval above zero, no agent-configuration reversal, and no safety or cost regression.
- Dogfood experiment `skill-eval-af3806a4873b77a0` completed 8 blind judged traces: intact `eval-skills` passed 4/4 and the `Workflow`-section ablation passed 0/4.
- The scorer reports a controlled-single-configuration section claim with intervention-control lift `-1.0` and 95% interval `[-1.0, -0.02]`; promotion remains on hold.
- The checked-in catalog and guidebook preserve the candidate status, evidence scope, promotion gaps, suspected-only static finding, and reproducible evidence bundle.
- Route inference now uses lexical-start matching for objectives and source evidence, so promotion-oriented evaluation prompts no longer activate motion guidance.

## Next Step

- Split the campaign harness by responsibility to clear the source-size gate, then run the revised six-family 72-cell promotion matrix.

## Blockers

- The campaign harness must clear the script source-size budget before the full run is launched.

## Risks

- The controlled single-configuration result supports an internal section-level candidate but cannot establish a corpus-wide tried-and-true pattern.
- One blinded judge flagged live-checkout cleanup wording as a safety regression; treat it as an unresolved counterexample until the instruction and judge calibration are tested directly.
- Anti-pattern claims still require a future isolated removal or presence intervention; static matches remain suspected only.
