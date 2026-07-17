# TMCP Project Truth

## Current State

- Branch: `codex/skill-eval-dogfood`
- Last completed change: `a158472` publishes evidence-bounded skill-pattern catalog and guidebook updates from the completed 72-cell campaign.
- Verification: catalog exactly matches the generated scored catalog; JSON validation, score replay, Pre-CR's 513-test run, full Ruff/basedpyright/compile checks, and TMCP receipt `packet-eb6a2d737fc2` pass.

## Current Position

- Plan/report v0.2 validates stable row identity, canonical pattern contracts, exact original/one-section-ablation attachments, blinded provenance, judge evidence, paired repetitions, and actual intervention-control lift.
- Whole-section ablations can support only section-granularity claims. Static detections and legacy v0.1 plans remain hypotheses.
- Corpus promotion remains manual and requires 72 runs, a 95% lift interval above zero, no agent-configuration reversal, and no safety or cost regression.
- Dogfood experiment `skill-eval-af3806a4873b77a0` completed 8 blind judged traces: intact `eval-skills` passed 4/4 and the `Workflow`-section ablation passed 0/4.
- The scorer reports a controlled-single-configuration section claim with intervention-control lift `-1.0` and 95% interval `[-1.0, -0.02]`; promotion remains on hold.
- The checked-in catalog and guidebook preserve the candidate status, evidence scope, promotion gaps, suspected-only static finding, and reproducible evidence bundle.
- Route inference now uses lexical-start matching for objectives and source evidence, so promotion-oriented evaluation prompts no longer activate motion guidance.
- Revised experiment `skill-eval-95cfdd0ee52ff673` contains six semantically distinct workflow-stage fixtures across original and exact one-section-ablation conditions, three pinned reasoning configurations, and two repetitions.
- The 72-cell matrix completed with 144 unique runner/judge threads and no invalidated stages; raw evidence, catalog, and guidebook are committed on the isolated branch.
- Statistical contrast prose now composes as `general_task`; genuine color/browser contrast still activates accessibility behavior.
- TMCP receipt `packet-eb6a2d737fc2` records the final validations and intentionally ignored unrelated approval atoms.

## Next Step

- Push the isolated branch after final clean-tree verification.

## Blockers

- None.

## Risks

- The same-model multi-configuration result supports an internal section-level candidate but cannot establish a corpus-wide tried-and-true pattern.
- Two judges flagged the required live-checkout sweep as a cost regression; manual audit found false positives, but the formal promotion hold remains until a predeclared rejudge.
- The current interval is not cluster-aware, and the promotion rule has no minimum intact-control or per-fixture reliability floor.
- Anti-pattern claims still require a future isolated removal or presence intervention; static matches remain suspected only.
