# Eval-skills multi-configuration dogfood

This bundle answers a narrow question: does the explicit `Workflow` section in
`eval-skills` materially improve the quality of evaluation-procedure answers under
matched blind conditions?

## Result

Yes, within the tested boundary. The intact skill passed 20 of 36 judged runs
(`55.6%`); the exact `Workflow`-section ablation passed 3 of 36 (`8.3%`). The
intervention-control lift is `-0.473`, where negative is the expected support
direction. Its 95% Newcombe-Wilson interval is `[-0.676, -0.178]`.

All three pinned configurations agreed:

| Codex runner configuration | Original | Ablated | Ablated - original |
| --- | ---: | ---: | ---: |
| `gpt-5.6-sol`, low reasoning | 7/12 | 1/12 | `-0.500` |
| `gpt-5.6-sol`, high reasoning | 5/12 | 1/12 | `-0.333` |
| `gpt-5.6-sol`, max reasoning | 8/12 | 1/12 | `-0.583` |

TMCP v0.2 therefore assigns the section-level claim
`controlled_multi_agent_eval`. That name means three pinned agent
configurations in the current protocol. This campaign used one model with three
reasoning settings, not three independent models. It tests production of
evaluation procedures, not whether those procedures were later executed correctly.

The reported interval pools repetitions and configurations as independent outcomes.
An independent audit identified fixture/configuration clustering as a manual-review
limitation. Five fixture-level effects favor the original and one is tied, but the
current report does not contain a predeclared cluster-aware interval. Treat the
reported interval as the protocol's score, not the last word on generalization.

Promotion remains on hold. Two of 72 judges marked `cost_regression=true` because
original-skill artifacts required a clean-checkout sweep after every run. That
operation is explicitly required by the target skill, but the first-principles
summary supplied to judges did not state the rule. The labels are therefore a
real conservative gate and a judge-calibration counterexample, not evidence that
the workflow section is corpus-wide tried-and-true.

## Experiment design

- Experiment: `skill-eval-95cfdd0ee52ff673`
- Pattern: `evaluation.staged-workflow-section`
- Tested atom: `staged_evaluation_workflow`
- Intervention: exact one-section `Workflow` ablation
- Fixtures: 6 semantically distinct workflow stages
- Conditions: original and ablated
- Runner configurations: `gpt-5.6-sol` reasoning `low`, `high`, and `max`
- Repetitions: 2 per fixture-condition-configuration cell
- Cells: 72
- Sessions: one fresh runner and one fresh judge per cell, 144 unique threads
- Judge configuration: `gpt-5.6-sol`, high reasoning
- Codex CLI: `0.144.2`

The fixtures cover:

| Fixture | Workflow stage |
| --- | --- |
| `named-defect-minimal-revision` | targeted revision discipline |
| `single-green-claim-calibration` | nondeterminism and claim calibration |
| `contaminated-run-and-live-checkout-leak` | contamination recovery |
| `judgment-skill-with-prescriptive-bar` | skill-defect versus bad-case diagnosis |
| `targeted-fix-regression-retest` | full-suite regression retest |
| `ambiguous-judgment-versus-conformance-mode` | evaluation-mode resolution |

The exact first-principles summary supplied to every judge was:

> Trustworthy skill evaluation validates concrete inputs and a defensible bar, keeps fresh context-free runners separate from evidence-based judges, repeats important cases and reports pass rates, distinguishes skill defects from bad cases, tests judgment rather than memorized answers, and reruns the whole suite after any change.

That text is preserved verbatim because its omission of the target skill's explicit
live-checkout sweep rule is material to interpreting the two cost labels.

## Integrity audit

- 72 of 72 cells completed in one campaign invocation.
- 0 current campaign errors.
- 144 unique thread IDs; no runner/judge thread reuse.
- 72 of 72 TMCP case scores have valid judge evidence and controlled provenance.
- No stage was invalidated or retried.
- The cleanroom was empty after the campaign.
- Runner prompts contained only the instruction attachment and task; bars, smells,
  variant names, and hypotheses were withheld.
- Judges received the task, first principles, observable bar, failure smells, and
  artifact, but not the condition or instruction attachment.
- Every trace is digest-bound to the runner output, judge output, prompt, schema,
  event streams, usage records, and completion markers.
- The original dirty checkout at `/Users/jakyeamos/projects/tmcp` was inspected and
  left untouched; the campaign ran from the isolated worktree.

The canonical score and a `--no-compose-packet` replay produced identical
`pattern_claims`. Packet inclusion changed from high-confidence composition to a
low-confidence fallback, as expected, without changing the causal result.

## Per-fixture outcomes

| Fixture | Original | Ablated |
| --- | ---: | ---: |
| evaluation mode | 4/6 | 2/6 |
| contamination handling | 6/6 | 0/6 |
| failure diagnosis | 1/6 | 0/6 |
| revision discipline | 3/6 | 0/6 |
| claim calibration | 6/6 | 1/6 |
| regression retest | 0/6 | 0/6 |

The last row is an important counterexample. The workflow section strongly moves
aggregate behavior, but it does not make every workflow stage reliable. Original
artifacts repeatedly omitted the explicit skill-defect-versus-bad-case loop after a
new regression. This remains a target-skill weakness or fixture-calibration question,
not something the positive section-level lift can erase.

## Cost and safety

No judge reported a safety regression. Two original-condition judges, both on the
regression-retest fixture, reported a cost regression. They cited the instruction to
perform a clean-checkout sweep after every run as materially unnecessary. The target
skill explicitly says both “After every run, sweep the live checkout” and “the sweep
is the guarantee.” Because the judge's first-principles summary omitted that safety
standard, the campaign cannot determine whether the two labels represent a genuine
cost problem or a bad cost bar. TMCP correctly keeps the automatic/manual-review gate
closed instead of silently discarding the labels.

An independent manual audit against the target skill contract adjudicated both
labels as false positives caused by the incomplete judge bar. The raw judge outputs
and canonical TMCP report remain unchanged, so the formal promotion decision remains
on hold pending a predeclared rejudge rather than a post-hoc label edit.

The matched evidence makes calibration noise likely: all 12 regression-retest
artifacts mention checkout or leak inspection, and only two received the cost label.
Across the whole campaign, 47 artifacts mention checkout, `git status`, or leaks;
45 were labeled cost-free. The labels must not be hand-flipped after seeing the
result. A predeclared campaign-wide rejudge with a faithful cost bar is the clean
resolution.

The hardened evaluator now supports that rejudge as a complete digest-bound
sidecar rather than a raw-label mutation. Its campaign-wide [cost bar](cost-rejudge/cost-evaluation-bar.md)
and [execution contract](cost-rejudge/README.md) are predeclared. The only
remaining live step requires explicit authorization to send the 72 fixed
runner artifacts to the Codex service; until then, no rejudged verdict is
claimed.

The same replay adds a fixture-block interval of `[-0.750, -0.194]` and
explicit 50% aggregate/per-fixture intact-control floors. It confirms the
relative section effect but holds promotion independently of cost: regression
retest is 0/6 and failure diagnosis is 1/6 for the intact condition. See the
[cluster/reliability replay](cluster-reliability-replay.md). The planned
smaller causal interventions are intentionally not run while this baseline is
unreliable; their activation contract is recorded in the
[micro-ablation protocol](workflow-microablation-protocol.md).

Actual campaign usage is recorded separately from TMCP's heuristic cost score:

| Role | Input tokens | Output tokens | Reasoning output tokens |
| --- | ---: | ---: | ---: |
| runners | 780,568 | 22,306 | 8,140 |
| judges | 749,250 | 52,073 | 17,857 |

Original runner outputs used 11,988 output tokens versus 10,318 for ablated outputs.
That descriptive difference is not a causal monetary-cost estimate and does not
adjudicate the checkout-sweep labels.

Across runner and judge roles, original cells used 781,561 input and 37,716 output
tokens; ablated cells used 748,257 input and 36,663 output tokens. The differences
are `+4.45%` input and `+2.87%` output for the longer intact attachment.

## Dogfooded patterns

These operating patterns survived the live campaign and its resume/integrity checks.
They are dogfooded evaluation practices, not all separately causal skill-writing
claims:

- validate an exact one-factor intervention before spending runner calls;
- use a neutral runner wrapper and keep condition, hypothesis, bar, and smells hidden;
- separate fresh runners from fresh evidence-based judges;
- key every judge criterion and require a citation for every pass or fail;
- bind traces to raw artifacts and event streams instead of asserting provenance;
- archive invalid attempts and resume only digest-valid completed stages;
- stratify effects by configuration and reject direction reversals;
- report actual token usage separately from heuristic cost diagnostics;
- preserve counterexamples and promotion holds instead of optimizing the report for a
  desired conclusion.

## Dogfooded anti-patterns and failure modes

The work exposed these reusable warnings. Unless explicitly identified as a causal
pattern above, they remain process findings or hypotheses:

- substring routing (`motion` inside `promotion`) instead of lexical token matching;
- projecting overloaded terms (`contrast`) into UI guidance without nearby domain
  context;
- priming a runner by saying it is blind, experimental, or being graded;
- showing the runner the bar or failure smells;
- accepting free-form or missing criterion IDs and citations;
- claiming isolation without event-stream and thread evidence;
- treating partial output as a resumable completed stage;
- omitting plan, protocol, schema, or harness-module hashes from the resume manifest;
- mechanically renaming fixtures and calling them distinct families;
- grading against requirements not supported by the task or skill contract;
- duplicating normative behavior outside the ablated section, weakening attribution;
- calling reasoning settings “multiple models”;
- treating TMCP's heuristic cost score as actual campaign usage;
- asking for a safety/cost verdict without a complete, faithful bar for that verdict;
- letting one noisy regression label disappear merely because the aggregate lift is
  attractive.

Two additional promotion-design gaps remain hypotheses for the next protocol
revision: use cluster-aware uncertainty for repeated fixture/configuration outcomes,
and set an explicit control/per-fixture sufficiency floor so a strong relative lift
cannot be mistaken for a generally reliable skill.

## Reproduction

Generate the plan into a new directory:

```bash
node scripts/tmcp_launcher.mjs evaluate-skills \
  --mode plan \
  --skill-paths /Users/jakyeamos/skills/authoring/eval-skills/SKILL.md \
  --task-fixtures "$(jq -c . docs/evidence/skill-eval-multiconfig-2026-07-17/fixtures.json)" \
  --variants original \
  --variants ablated \
  --write-artifacts \
  --output-dir /private/tmp/tmcp-skill-eval-plan-replay
```

The live campaign command and all pinned arguments are represented in
[`runs/campaign-manifest.json`](runs/campaign-manifest.json). Score the persisted
traces with:

```bash
node scripts/tmcp_launcher.mjs evaluate-skills \
  --mode score \
  --evaluation-plan docs/evidence/skill-eval-multiconfig-2026-07-17/generated/tmcp-skill-evaluation-plan.json \
  --run-evidence-json "$(jq -c . docs/evidence/skill-eval-multiconfig-2026-07-17/runs/traces.json)" \
  --project-path /private/tmp/tmcp-skill-eval-dogfood \
  --write-artifacts \
  --output-dir /private/tmp/tmcp-skill-eval-score-replay
```

## Evidence map

- [`fixtures.json`](fixtures.json) — human-authored cases, bars, and smells
- [`generated/tmcp-skill-evaluation-plan.json`](generated/tmcp-skill-evaluation-plan.json) — pinned variants and intervention contracts
- [`runs/campaign-manifest.json`](runs/campaign-manifest.json) — protocol, cell matrix, harness digests, and isolation preflight
- [`runs/campaign-summary.json`](runs/campaign-summary.json) — completion, thread, pass, and token totals
- [`runs/traces.json`](runs/traces.json) — 72 normalized, artifact-bound traces
- [`runs/cells/`](runs/cells/) — raw runner/judge outputs, event streams, schemas, usage, and stage markers
- [`scored/tmcp-skill-evaluation-report.json`](scored/tmcp-skill-evaluation-report.json) — canonical TMCP score and promotion hold
- [`scored/skill-pattern-catalog.json`](scored/skill-pattern-catalog.json) — generated candidate catalog
- [`scored/skill-writing-guidebook.md`](scored/skill-writing-guidebook.md) — generated compact guidebook

Key SHA-256 digests:

- plan: `55dba97e0fe77aed178baf55384a4c2f6a482b1062ef777adabb73e776d86926`
- campaign manifest: `ebe9256faca0e03b2e5ad24fb379a51d7a486d976bddaa671be646ab81b55cb1`
- traces: `364f998fac7509432a3890bff3c958b3ee781ddcd727e4513a410a43f26195ad`
- score report: `fd5844a59c209d386c15e61441d8adbed36d22e92c79c99c0966399e1790619d`
