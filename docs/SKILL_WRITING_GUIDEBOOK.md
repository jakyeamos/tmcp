# TMCP Skill Writing Guidebook

Evidence-led v0.2. This guidebook records skill patterns at the strongest level
their evidence supports. It is not a list of intuitions promoted by repetition.

## How to read a pattern claim

- `hypothesis` — plausible and untested
- `static_review` — detected by lint or rubric review only
- `dogfooded` — observed in TMCP use without a controlled contrast
- `controlled_single_agent_eval` — repeated matched contrast under one pinned
  agent configuration
- `controlled_multi_agent_eval` — the same contrast holds across at least three
  pinned configurations
- `production_reinforced` — independently reinforced by repeated production traces
- `deprecated` — contradicted strongly enough that it should no longer be recommended

Only a validated entry in `pattern_claims` may change a guidebook pattern's
behavioral evidence status. Activation, packet-inclusion, adherence, cost, and
safety scorecard dimensions are diagnostics; they are not causal promotion evidence.

## Author skills at testable boundaries

A skill section is a useful experimental unit when it owns one coherent decision or
workflow stage. A whole-section ablation can support a section-level claim. It cannot
prove that every sentence, command, or behavior atom inside the section was causal.

Prefer:

- explicit sections for coherent workflows, verification gates, output contracts,
  and stop conditions;
- one-factor variants whose exact content diff is validated before any run;
- important behavior stated once at the section that owns it;
- fixture bars written as observable outcomes and failure smells.

Avoid:

- scattering one workflow across unrelated sections;
- duplicating normative rules across sections, which lets an ablated section leak
  through the remaining prose and makes the experimental split harder to interpret;
- claiming a fine-grained rule from a whole-section intervention;
- treating a static pattern match as behavioral proof.

The duplication warning is still a campaign-design hypothesis. It needs its own
controlled intervention before becoming a corpus recommendation.

## Supported candidate: staged evaluation workflow section

- Pattern ID: `evaluation.staged-workflow-section`
- Status: supported internal candidate
- Evidence: `controlled_single_agent_eval`
- Claim granularity: section
- Experiment: `skill-eval-af3806a4873b77a0`
- Sample: 8 traces, 2 fixture families, 2 repetitions per cell, 1 pinned
  configuration
- Result: intact skill 4/4; `Workflow`-section ablation 0/4
- Intervention-control lift: `-1.0`, where negative is the expected support
  direction; 95% Newcombe-Wilson interval `[-1.0, -0.02]`
- Promotion: hold

Prefer an explicit workflow section that separates input validation, blind fresh
runners, independent evidence-based judges, repeated trials and pass rates,
skill-defect versus bad-case diagnosis, and full-suite re-evaluation after changes.

Avoid a loose instruction to test the skill a few times and improve it. In this
pilot, removing the coherent workflow section caused every judged artifact to miss
at least one required safeguard.

This is not yet a corpus-wide tried-and-true pattern. Promotion still needs at least
6 fixtures across 3 fixture families and 3 pinned configurations, 2 repetitions per
cell, a support-aligned 95% interval above zero, no configuration reversal, and no
safety or cost regression. That minimum multi-configuration matrix is 72 runs.

## Corpus evaluation protocol

1. Pin the skill digest, fixture digests, intervention contract, agent
   configuration, and expected effect direction.
2. Generate an exact matched control and a one-factor intervention. Reject an
   inexact or fallback split before running agents.
3. Use a fresh context-free runner for every cell. Keep the fixture bar and
   hypothesis hidden from the runner.
4. Use a separate fresh judge with only the artifact, fixture bar, and skill first
   principles. Require evidence for every criterion and explicit safety/cost labels.
5. Repeat every fixture-condition cell. Record pass rates and the paired
   intervention-control effect with an uncertainty interval.
6. Preserve the plan, observations, verdicts, report, counterexamples, and
   promotion decision as an append-only evidence bundle.
7. Promote manually only when the configured evidence gate is met. A successful
   pilot remains a candidate; it does not rewrite the corpus automatically.

## Anti-pattern discipline

Anti-patterns require an isolated presence/removal intervention. Static detections
remain `suspected` or `hypothesis`, even when the wording looks obviously weak.

The first dogfood statically flagged `output.missing-observable-contract`. That
finding is not promoted: it has no behaviorally judged contrast, and the target skill
already names several report fields. Treat it as a detector-calibration case.

One blind judge also flagged unqualified live-checkout cleanup language as a safety
risk because “clean” could delete unrelated work. The label was not consistent
across judges and was not isolated by the `Workflow` ablation, so it blocks promotion
but does not establish a causal anti-pattern. A future fixture should contrast safe
preservation language with destructive cleanup wording directly.

## Evidence ledger

The first controlled bundle is in
[`docs/evidence/skill-eval-dogfood-2026-07-17`](evidence/skill-eval-dogfood-2026-07-17/README.md).
The machine-readable catalog is
[`docs/SKILL_PATTERN_CATALOG.json`](SKILL_PATTERN_CATALOG.json).
