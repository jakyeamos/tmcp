# TMCP Project Truth

## Current State

- Branch: `codex/skill-eval-dogfood`
- Last completed change: `86d5792` makes the cost-rejudge JSON Schema accepted by the Codex service after `40f8f17` split the harness into thin CLI, source-validation, and execution modules.
- Verification: 525 tests (3 skipped), full Ruff/basedpyright/compile checks, score replay, TMCP doctor, the 72-source rejudge dry-run, and Pre-CR changed-line readiness pass. The first approved live attempt exposed the service-compatible schema gap before any judgment completed; its fixed-artifact evidence is retained separately.

## Current Position

- Plan/report v0.2 validates stable row identity, canonical pattern contracts, exact original/one-section-ablation attachments, blinded provenance, judge evidence, paired repetitions, and actual intervention-control lift.
- Whole-section ablations can support only section-granularity claims. Static detections and legacy v0.1 plans remain hypotheses.
- Corpus promotion remains manual and requires 72 runs, a clustered 95% lift interval above zero, no agent-configuration reversal, no safety or adjudicated cost regression, and at least 50% aggregate plus per-fixture intact-control reliability.
- Dogfood experiment `skill-eval-af3806a4873b77a0` completed 8 blind judged traces: intact `eval-skills` passed 4/4 and the `Workflow`-section ablation passed 0/4.
- The scorer reports a controlled-single-configuration section claim with intervention-control lift `-1.0` and 95% interval `[-1.0, -0.02]`; promotion remains on hold.
- The checked-in catalog and guidebook preserve the candidate status, evidence scope, promotion gaps, suspected-only static finding, and reproducible evidence bundle.
- Route inference now uses lexical-start matching for objectives and source evidence, so promotion-oriented evaluation prompts no longer activate motion guidance.
- Revised experiment `skill-eval-95cfdd0ee52ff673` contains six semantically distinct workflow-stage fixtures across original and exact one-section-ablation conditions, three pinned reasoning configurations, and two repetitions.
- The 72-cell matrix completed with 144 unique runner/judge threads and no invalidated stages; raw evidence, catalog, and guidebook are committed on the isolated branch.
- Statistical contrast prose now composes as `general_task`; genuine color/browser contrast still activates accessibility behavior.
- TMCP receipt `packet-eb6a2d737fc2` records the final validations and intentionally ignored unrelated approval atoms.
- Remote `origin/codex/skill-eval-dogfood` contains the complete isolated dogfood branch.
- The fixture-block replay is `[-0.750, -0.194]`; it supports the relative section effect but records a 0/6 regression-retest and 1/6 failure-diagnosis intact-control rate, so promotion remains held independently of cost.
- Incidental bare `SKILL.md` mentions no longer load every harvested skill, and detailed objectives require meaningful source overlap unless explicit routing metadata applies.

## Next Step

- Rerun the explicitly approved blind cost rejudge against the fixed 72 artifacts using the service-compatible schema, then score a complete sidecar without changing raw labels. Do not run `Workflow` micro-ablations unless a fresh baseline clears all control-reliability gates.

## Blockers

- None; the approved rejudge is in progress.

## Risks

- The same-model multi-configuration result supports an internal section-level candidate but cannot establish a corpus-wide tried-and-true pattern.
- Two raw judges flagged the required live-checkout sweep as a cost regression; the formal cost decision remains held until the complete blind sidecar exists.
- The historical 72-cell plan did not predeclare the clustered analysis policy, so its cluster interval is diagnostic only and cannot upgrade promotion.
- Anti-pattern claims still require a future isolated removal or presence intervention; static matches remain suspected only.
