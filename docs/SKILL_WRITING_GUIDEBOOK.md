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

## Controlled multi-configuration candidate: staged evaluation workflow section

- Pattern ID: `evaluation.staged-workflow-section`
- Status: supported internal candidate
- Evidence: `controlled_multi_agent_eval`
- Claim granularity: section
- Experiment: `skill-eval-95cfdd0ee52ff673`
- Sample: 72 traces, 6 fixtures in 6 families, 2 repetitions per cell, 3 pinned
  configurations of one model
- Result: intact skill 20/36; `Workflow`-section ablation 3/36
- Intervention-control lift: `-0.473`, where negative is the expected support
  direction; 95% Newcombe-Wilson interval `[-0.676, -0.178]`
- Configuration effects: high `-0.333`, low `-0.500`, max `-0.583`; no reversal
- Promotion: hold — historical plan lacks preregistered clustered/reliability
  gates; the intact control also misses the 50% floor on two fixture families

Prefer an explicit workflow section that separates input validation, blind fresh
runners, independent evidence-based judges, repeated trials and pass rates,
skill-defect versus bad-case diagnosis, and full-suite re-evaluation after changes.

Avoid a loose instruction to test the skill a few times and improve it. Removing
the coherent workflow section reduced judged pass rate by 47.3 percentage points
across the tested configurations.

This establishes the relative benefit of the coherent section. It does not establish
absolute reliability—the intact skill still failed 16/36 runs—or the causal value of
every sentence inside the section. The three configurations are reasoning settings
of the same `gpt-5.6-sol` model, not independent models.

The matrix, lift, interval, and no-reversal gates cleared. A complete blind cost
rejudge resolved the raw checkout-sweep labels as non-regressions without altering
the source traces. Promotion remains held because the historical plan did not
preregister clustered/reliability gates and the intact skill missed two fixture
families. Until a fresh baseline clears those gates, call this behaviorally supported
in a controlled multi-configuration evaluation, not corpus-wide tried-and-true.

The formal report preserves the raw labels and records the predeclared campaign-wide
blind rejudge separately; no post-hoc label edit was made.

The replay added a fixture-block interval and 50% aggregate/per-fixture control
floors, but those gates were not preregistered in the historical plan. The
regression-retest fixture passed 0/6 in both conditions. Future promotion-grade
protocols must pin the policy before launch and clear it before treating relative
lift as general reliability.

## Corpus evaluation protocol

1. Pin the skill digest, fixture digests, intervention contract, agent
   configuration, and expected effect direction.
2. Generate an exact matched control and a one-factor intervention. Reject an
   inexact or fallback split before running agents.
3. Use a fresh context-free runner for every cell. Keep the fixture bar and
   hypothesis hidden from the runner.
4. Use a separate fresh judge with only the artifact, fixture bar, and a faithful
   account of the skill's first principles. Require evidence for every criterion.
   Give safety and cost verdicts their own defensible bars; do not ask the judge to
   invent them from an incomplete principles summary.
5. Repeat every fixture-condition cell. Record pass rates and the paired
   intervention-control effect with an uncertainty interval.
6. Preserve the plan, observations, verdicts, report, counterexamples, and
   promotion decision as an append-only evidence bundle.
7. Promote manually only when the configured evidence gate is met. A successful
   pilot remains a candidate; it does not rewrite the corpus automatically.

## Dogfooded evaluator practices

The promotion campaign verified these practices operationally. They are useful
defaults for future corpus evaluations, but only the workflow-section claim above
has a controlled causal intervention.

- Validate the exact one-factor attachment diff before runner calls.
- Keep the runner wrapper neutral; hide condition, hypothesis, bar, and smells.
- Use a fresh runner and a separate fresh judge for every cell.
- Give every judge criterion a stable ID and require a citation for pass or fail.
- Bind claims of isolation to raw event streams and unique thread IDs.
- Treat partial or digest-mismatched stages as invalid; archive them and fail closed.
- Bind plan, protocol, schema, prompt context, and every harness module in the resume
  manifest.
- Stratify effects by configuration and reject support-direction reversals.
- Preserve valid failures and counterexamples; never resample to improve a result.
- Report actual usage separately from heuristic cost diagnostics.

Campaign-design failure modes observed while building the matrix include substring
routing, projecting overloaded terms such as `contrast` without nearby domain
context, runner priming, bar leakage, unkeyed judge evidence, asserted rather than
bound provenance, partial artifacts treated as complete, mechanically renamed
fixture families, off-contract bars, and calling same-model settings multiple models.
Treat these as dogfooded engineering warnings. Do not promote them as causal skill
anti-patterns without an isolated presence/removal contrast.

## Anti-pattern discipline

Anti-patterns require an isolated presence/removal intervention. Static detections
remain `suspected` or `hypothesis`, even when the wording looks obviously weak.

The first dogfood statically flagged `output.missing-observable-contract`. That
finding is not promoted: it has no behaviorally judged contrast, and the target skill
already names several report fields. Treat it as a detector-calibration case.

The multi-configuration campaign produced no safety-regression labels, so the pilot's
single cleanup-safety signal did not reproduce. Two of 36 intact artifacts and 0 of
36 ablated artifacts were instead labeled cost regressions because they required a
live-checkout sweep after every run. Cleanup cadence and wording were not isolated,
and similar guidance remains outside the ablated section. This is a cost-risk and
judge-calibration hypothesis, not a causal anti-pattern. A future contrast should
test safe preservation language and cleanup cadence directly with an explicit cost
bar.

## Evidence ledger

The source-checkout evidence bundles are
`docs/evidence/skill-eval-dogfood-2026-07-17` and
`docs/evidence/skill-eval-multiconfig-2026-07-17`; they are deliberately not
included in the immutable package.
The machine-readable catalog is
[`docs/SKILL_PATTERN_CATALOG.json`](SKILL_PATTERN_CATALOG.json).
