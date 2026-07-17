# TMCP Project Truth

## Current State

- Branch: `codex/skill-eval-dogfood`
- Last completed change: `f99934e` adds the revised six-fixture promotion matrix and its generated 36-row TMCP evaluation plan for experiment `skill-eval-95cfdd0ee52ff673`.
- Verification: a clean plan replay reproduced the same experiment and all 36 rows after excluding runtime timestamp/path metadata. Nine focused harness tests, Ruff, basedpyright, compile, the 72-cell dry-run, and Pre-CR also pass.

## Current Position

- Plan/report v0.2 validates stable row identity, canonical pattern contracts, exact original/one-section-ablation attachments, blinded provenance, judge evidence, paired repetitions, and actual intervention-control lift.
- Whole-section ablations can support only section-granularity claims. Static detections and legacy v0.1 plans remain hypotheses.
- Corpus promotion remains manual and requires 72 runs, a 95% lift interval above zero, no agent-configuration reversal, and no safety or cost regression.
- Dogfood experiment `skill-eval-af3806a4873b77a0` completed 8 blind judged traces: intact `eval-skills` passed 4/4 and the `Workflow`-section ablation passed 0/4.
- The scorer reports a controlled-single-configuration section claim with intervention-control lift `-1.0` and 95% interval `[-1.0, -0.02]`; promotion remains on hold.
- The checked-in catalog and guidebook preserve the candidate status, evidence scope, promotion gaps, suspected-only static finding, and reproducible evidence bundle.
- Route inference now uses lexical-start matching for objectives and source evidence, so promotion-oriented evaluation prompts no longer activate motion guidance.
- Revised experiment `skill-eval-95cfdd0ee52ff673` contains six semantically distinct workflow-stage fixtures across original and exact one-section-ablation conditions, three pinned reasoning configurations, and two repetitions.

## Next Step

- Run and score the six-family 72-cell promotion matrix, then update the evidence report and corpus guidance only to the level the controlled result earns.

## Blockers

- None. The full campaign requires live Codex API access and remains safely resumable if an infrastructure attempt is invalidated.

## Risks

- The controlled single-configuration result supports an internal section-level candidate but cannot establish a corpus-wide tried-and-true pattern.
- One blinded judge flagged live-checkout cleanup wording as a safety regression; treat it as an unresolved counterexample until the instruction and judge calibration are tested directly.
- Anti-pattern claims still require a future isolated removal or presence intervention; static matches remain suspected only.
