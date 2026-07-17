# TMCP Project Truth

## Current State

- Branch: `codex/skill-eval-dogfood`
- Last completed change: `734c006` adds a verified source-bundle composition scorer, binds the persisted plan/trace/sidecar digests into its report, and fixes opaque trace-ID preservation during controlled scoring.
- Verification: 565 tests pass (3 skipped); source-bundle regeneration, digest/live-source verification, policy-bound rejudge dry run, verified-score wiring, API validation, guarded 72-cell dry-run, compiler checks, TMCP doctor, a project-root `reaction` replay, and targeted release-scanner checks pass. The commit hook ran changed-line Pre-CR successfully.

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
- TMCP receipt `packet-f48e7b611dac` records the campaign-hardening verification and artifact-free remote-schema smoke.
- Remote `origin/codex/skill-eval-dogfood` contains the complete isolated dogfood branch.
- The fixture-block replay is `[-0.750, -0.194]`; it supports the relative section effect but records a 0/6 regression-retest and 1/6 failure-diagnosis intact-control rate, so promotion remains held independently of cost.
- The historical 72-cell and fresh-baseline 36-cell cost sidecars are now diagnostic archives, not reproducible evidence: each records a cost-bar digest that does not match the retained input file. The 72-cell claim remains `hold` because its cluster policy was not predeclared and fixture-level control reliability is below the 0.5 floor.
- Incidental bare `SKILL.md` mentions no longer load every harvested skill, and detailed objectives require meaningful source overlap unless explicit routing metadata applies.
- Fresh plan generation can bind `tmcp-skill-eval-campaign-policy-v0.1` into experiment identity; launch readiness enforces the pinned matrix, cluster/control contract, baseline shape, and independent judge model before any campaign artifact is sent.
- The campaign harness accepts three explicit model/effort configurations, runs original-only baseline reliability studies as 36 cells, and treats cross-model confirmation as an explicit policy and scoring gate rather than a same-model reasoning sweep.
- A passed remote-schema preflight receipt is persisted alongside every non-dry campaign; capacity/rate-limit/network retries are bounded, classified, archived, and auditable.
- The fresh baseline used independently reviewed directness repairs, three distinct available Codex runner identifiers (`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`), a distinct `gpt-5.5` judge, an inspectable first-principles file, and an all-36-trace cost bar.
- The approved live original-only campaign completed 36/36 cells and passed the aggregate reliability floor at 20/36, but `claim_calibration` and `regression_retest` each scored 2/6 below the 3/6 per-fixture floor. It is a valid negative baseline gate and remains held.
- Primary judges reported 0/36 safety and raw-cost regressions. The archived condition-blind sidecar recorded 1/36 materially unnecessary iterative loop and preserved its malformed first attempt, but its cost-bar digest no longer matches the retained bar. Raw and archived sidecar labels remain distinct and neither sidecar result supports a current claim.
- Diagnosis classifies 12 traces as repeated target-defect candidates (first-principles handoff, contamination recovery, per-case reporting, or repeat-every-case discipline) and four as isolated model-sensitive omissions; no reviewed fixture or rate bar is defective.
- The reinterpreted report correctly marks this as `baseline_reliability`: no causal pattern or lift claim, no attachment-only activation/adherence heuristic, actual 20/36 aggregate and 2/6 minimum reliability, plus raw 0/36 and archived-sidecar 1/36 cost counts.
- Local TMCP + `explore-unknowns` and TMCP + `repo-behavior-spec-loop` packet probes retain their specialized evidence and stop conditions without activating `frontend_implementation` from pre-action wording. The `refactor-clean` probe is selection-only pending behavioral fixtures.
- Composition contract v1 is a deterministic regression baseline, not a behavioral claim: it preserves a valid React/motion control while keeping `tests/fixtures/**` harvest-visible but activation-ineligible, including through declared loads.
- The local project-root composition replay is recorded with advisory receipt `packet-f62c9fd667c8`; its deterministic pass does not promote a skill-pair or wording rule.
- The reviewed v1 composition plan has six Stage-1 fixtures across campaign sequencing, evidence-boundary, and promotion-gate families; `packet_only` versus exact `packet_plus_explore` yields 72 blinded cells. It can test only the delivery effect of the pinned source bundle, not live selection, adherence, or corpus quality.
- `verify_composition_study.py` now rejects input/receipt/first-principles drift, reports opted-in live-source drift without exposing source text, and is mandatory for source-bundle campaign manifests; the campaign rejects a different runner first-principles file.
- The corrected byte-pinned study is `composition-study-f6de333293fee3f7`. Its cost sidecar requires a fresh, condition-blind, artifact-only 72-trace review using `gpt-5.6-sol` at high effort. This is process-independent but not a distinct-model claim; launcher and scored sidecar must match the policy's model, effort, seed, bar filename/digest, and trace count before scoring can clear the coverage gate. A read-only verifier must also reconstruct the completed bundle and report promotion-ready.
- `score_composition_study.py` now runs that verifier in the same local process before scoring, refuses a non-promotion-ready sidecar, emits a new report outside raw-evidence directories, and records the exact source-plan, trace, and sidecar digests. Generic sidecar-only scores remain diagnostic. The scorer preserves opaque trace IDs until normalization, while returned reports remain redacted.

## Next Step

- Obtain fresh approval to run the preregistered `composition-study-f6de333293fee3f7` 72 runner and 72 primary-judge calls. Afterward, obtain separate approval for its 72 cost-rejudge calls, run `score_composition_study.py` against the independently verified persisted bundle, then inspect the score. Keep the external `eval-skills` v3 revision as a separate reviewed campaign.

## Blockers

- Corpus promotion is held: the historical plan lacks a predeclared clustered-analysis policy and its regression-retest intact-control rate is 0/6.
- The fresh baseline is held: `claim_calibration` and `regression_retest` are below the preregistered 0.5 per-fixture floor. Its archived sidecar cannot change that result because the retained cost bar fails the new provenance check. The minimal target revision is diagnosed but intentionally not yet applied.
- Composition guidebook promotion is held: the new behavioral pair/control study is preregistered and dry-run only; no external runner or judge evidence exists yet.

## Risks

- The same-model multi-configuration result supports an internal section-level candidate but cannot establish a corpus-wide tried-and-true pattern.
- Two raw judges flagged the required live-checkout sweep as a cost regression; preserve those raw labels and the archived sidecars separately, but do not treat either unverified sidecar outcome as reproducible adjudication.
- The historical 72-cell plan did not predeclare the clustered analysis policy, so its cluster interval is diagnostic only and cannot upgrade promotion.
- Cross-model confirmation remains model-level, not cross-provider evidence; a future plan must name available independent runner models and a distinct judge model.
- Anti-pattern claims still require a future isolated removal or presence intervention; static matches remain suspected only.
- The attachment-only campaign protocol has no selection/adherence telemetry, so its diagnostic scorecard cannot be repurposed as behavioral activation evidence.
- The next external model run needs fresh approval after the target revision and v3 fixture review; the corrected local report is not new remote evidence.
- A positive source-bundle result would still be a delivery effect with length/framing confounded inside the pinned bundle, not proof of TMCP live selection or independent source adherence.
- The source-bundle launcher intentionally fails closed when a source, input, generated plan, or supplied first-principles file drifts; a changed source requires a new reviewed preregistration rather than resume.
