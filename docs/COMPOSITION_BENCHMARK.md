# Composition Benchmark Contract

TMCP 0.6 is release-eligible only after real host-run observations pass the
compositional acceptance gate. Golden prompts and behavioral fixture definitions
describe what to run; they contain no quality scores and are not evidence by
themselves.

The benchmark is deliberately two-pass and host-assisted:

1. prepare a no-oracle run plan and have the host propose cited semantics;
2. replay the compiler into an exact control plan;
3. let the host explicitly execute those controls and let an external evaluator
   score the resulting artifacts;
4. assemble observations from the controls plus those two fact bundles; and
5. score the assembled artifact against the release thresholds.

The host never supplies graph identity, stage order, source slices, context
cost, or aggregate quality. The assembler derives those values from compiler
replay, and derives weighted quality from evaluator dimension scores. A host
does report an advisory execution-context mode and opaque context-instance IDs;
TMCP validates those only against compiler-issued capsule digests.

## Corpus readiness gate

Every expected skill in a behavioral fixture must carry a nonempty inline
`Output contract:` beside its inputs, outputs, and exit gate. Benchmark
preparation rejects a fixture that omits that contract, and its preflight test
requires every expected skill to remain an explicitly scoped, provenance-backed
active slice. Keep the contract inline in the bounded skill body: a separate
Markdown section can be ranked as a different behavior slice and leave the
host without evidence for the role or handoff claims it is proposing. Each
fixture must also include at least one bounded task-input evidence item (for
example a target contract, sample records, source excerpts, a routing case
table, or a code excerpt). A requirement narrative alone makes every no-tool
host block before the composition can demonstrate a useful handoff; bounded
inputs are still `fixture_supplied` preconditions and never host-run proof.

This is a deterministic corpus/readiness check only. It proves that the
benchmark can expose observable artifacts and cited handoffs; it does not
generate model results, receipts, lift, or release evidence.

Before preparing a campaign, audit the checked-in skill guidance and catalog:

```bash
python3 scripts/audit_skill_guidebook.py
```

This read-only audit requires every catalog projection to have a matching
guidebook entry, preserves evidence level/status/promotion state across the two
surfaces, and fails closed when a controlled claim has no experiment identifier
in the source-only evidence tree. A passing audit is a documentation-integrity
signal, not behavioral evidence. Only a completed, replicated, policy-bound
composition observation may update an entry's evidence level; campaign plans,
golden fixtures, synthetic traces, and dry runs remain held hypotheses.

## Preregistering a composition-lift campaign

Before any host or evaluator work, derive a no-call campaign only from the five
bound replay inputs:

```bash
python3 scripts/plan_composition_lift_campaign.py \
  --control-plan path/to/benchmark-control-plan.json \
  --run-plan path/to/benchmark-run-plan.json \
  --semantic-proposals path/to/semantic-proposals.json \
  --routing-golden tests/fixtures/composition_routing_golden_v0_6.json \
  --behavioral-fixtures tests/fixtures/composition_behavioral_fixtures_v0_6.json
```

The command schema-validates and replay-validates all five inputs before
printing a `tmcp-composition-lift-campaign-v0.1` object to standard output. It
makes no model or tool calls and writes neither campaign artifacts nor receipts.
The campaign is not behavioral evidence and remains `pilot_only` with
`causal_claim_status: not_evaluated` until separately executed and scored.

### Current no-call handoff

The latest fixture-bound handoff (2026-07-21) is:

- campaign: `composition-lift-campaign-01696e55d67fa8ecb6e5`
- campaign digest: `01696e55d67fa8ecb6e5b48ce5a919bdc8c68a2c239bdafd8a4389cf7514799a`
- run manifest: `benchmark-run-1a5c87a7a3761fdc926a`
- run manifest digest: `1a5c87a7a3761fdc926a08e49cd2b950a0bb8894f8265db4d3650af214766318`
- control plan: `benchmark-control-fa4e2c940b51ef125968`
- control plan digest: `fa4e2c940b51ef1259680cfe4c1537edd87c958e487fbb777defb828fbdde9ab`
- dimensions: 5 blocks, 180 baseline cells, 360 causal cells, 540 runner dispatches, and 540 blind-judge dispatches
- prepared runner bundle digest: `0ab32310f66f8f66c95431681790b4ea4d3f5d8d47b0954651c0caaae1e4663e`
- prepared blind-judge bundle digest: `9e2fd5cfd4fd18f3ff27a82fe0442ea1f1143cf4ef346a08fb69a5acd276ba21`

This handoff is a reproducibility anchor only. It has no model-call authority,
does not persist receipts, and cannot support a lift or guidebook-promotion
claim. A future host/evaluator run must bind its raw artifacts to these exact
digests before scoring or rejudging. The prepared bundles are opaque transport
surfaces only: the runner bundle exposes execution references and bounded
instructions; the judge bundle exposes artifact slots and the fixture rubric.
Neither contains controller condition identity, skill order, graph, or recipe.

### Authorized full campaign diagnostic (2026-07-21)

The first complete authorized host/evaluator run used the bounded-input,
phase-aware campaign:

- campaign: `composition-lift-campaign-91b9f99de690ec4cc908`
- campaign digest: `91b9f99de690ec4cc9089cbed3a4d785c77df82391ee7d0c9ab7bda5ebf39592`
- host artifact: 540/540 cells, SHA-256
  `01144e52192ee11155fc0cea4f0e2eff52a6297e8f1c73a516ad85ee77ab7c11`
- blind-judge artifact: 540/540 cells, SHA-256
  `ea234f22fb75a16ab3795940f4f0e073db1ba1a03680774aca17ab114b9af393`
- evidence classes: `host_executed` and `trusted_evaluator_execution`
- median lift: synergy `-0.0423`, compiler `+0.0235`, order `+0.1110`
- acceptance: order passed; synergy and compiler failed; eligibility `false`

This is real repeated-cell diagnostic evidence, not a receipt, promotion
candidate, or release claim. The corrected wrong-order recipe made order lift
meaningful, but the external harness still supplied every selected skill body
even when the compiled plan marked later stages deferred. That raw-source
union is broader than TMCP's active-stage hydration and can make redundant or
future instructions compete with the current handoff. The next rerun must bind
the host packet to active/governing source slices, retain deferred stages only
as cited entry-condition metadata, and record the resulting context boundary
before another 540-cell claim.

### Authorized phase-aware full campaign diagnostic (2026-07-22)

The follow-up run recompiled each semantic arm at every ordered stage, hydrated
only the current stage's source bodies, and carried the prior handoff forward in
a fresh phase context. It completed the full campaign before scoring:

- campaign: `composition-lift-campaign-91b9f99de690ec4cc908`
- campaign digest: `91b9f99de690ec4cc9089cbed3a4d785c77df82391ee7d0c9ab7bda5ebf39592`
- host artifact: 540/540 cells, SHA-256
  `3d6e110cde3a175407f530e9ea15c9d657cd779de772bbf53d8e8eef75bb5b56`
- blind-judge artifact: 540/540 cells, SHA-256
  `2ec10093bc089a01d8a17b8af1c2e39317f5d3caea1b2c5e68c1db84e2190f24`
- evidence classes: `host_executed` and `trusted_evaluator_execution`
- median lift: synergy `+0.097`, compiler `+0.010`, order `+0.2295`
- acceptance: order passed; synergy and compiler failed; eligibility `false`

The unchanged artifacts initially hit a narrow redaction false positive on a
normal prose token. `04e61e4` makes the scanner recognize bounded lowercase
assignment/path prose and the benchmark's content/task/source digest fields;
the same content-bound artifacts then pass safety validation and produce the
metrics above. This remains real repeated-cell diagnostic evidence only: no
receipt, promotion, or release claim follows. The result says phase ordering is
valuable, but the compiler does not yet beat naïve union and the synergy median
is just below threshold. The next slice must reduce fair active-context cost and
improve cross-skill handoffs rather than lower the preregistered gates.

### Authorized phase-envelope calibration (2026-07-22)

After the typed phase-contract slice, an explicitly authorized 15-cell
subscription calibration reran the same bounded host/evaluator harness:

- campaign: `composition-lift-campaign-91b9f99de690ec4cc908`
- campaign digest: `91b9f99de690ec4cc9089cbed3a4d785c77df82391ee7d0c9ab7bda5ebf39592`
- host cells: 15/15, SHA-256
  `33e05534138af8f8855a59634232323b252288f5d36ac72fdb608ccbbd161948`
- blind-judge cells: 15/15, SHA-256
  `35d2fda1c8e16fd9894e7e0e84f56bf4f94cd29c2ae4d574ef795542cce3831b`
- output directory: `/private/tmp/tmcp-composition-next2/.tmp/lift-next2/calibration-phase-handoffs-v4`

The calibration verified the artifact contract change: the migration and
diagnose full-composition artifacts each retain all nine typed headings
(`PHASE_RESULT`, `STATUS`, `INPUT_HANDOFF`, `DELIVERABLES`,
`EVIDENCE_BOUNDARY`, `PRODUCED_HANDOFF`, `EXIT_GATE`, `NEXT_ENTRY`, and
`UNRESOLVED_GAPS`) across four phases, without the legacy whole-body elision
marker. This is a bounded contract check, not proof that every body is
complete or that downstream gates passed.

The sample is intentionally not scored as campaign lift: it contains only 15
of 540 cells, and the available migration/diagnose spot comparisons do not
form the preregistered paired replicate set. The full scorer correctly rejects
the subset as incomplete. In the observed spot cells, migration full weighted
quality was `0.772` versus naïve `0.793`, while diagnose full was `0.4105` versus
naïve `0.391`; these directional values identify migration handoff quality as
the next target but cannot support a causal, receipt, promotion, or release
claim. No receipt was recorded.

### Authorized handoff-evidence budget calibration (2026-07-22)

The next bounded calibration kept the 4,000-character phase envelope but
reallocated space from status and repeated boundary prose to deliverables,
produced handoffs, and exit gates:

- campaign: `composition-lift-campaign-91b9f99de690ec4cc908`
- campaign digest: `91b9f99de690ec4cc9089cbed3a4d785c77df82391ee7d0c9ab7bda5ebf39592`
- host cells: 15/15, SHA-256
  `71689c0f59e9a5612e9b52404671b13a49f4c2b6a0856e7b72d46d17041c7c34`
- blind-judge cells: 15/15, SHA-256
  `9529310d80b9bc0d8f6fdaa674300d2d9803a7cdf5d0f0e0cd7b9d6452d25524`
- output directory: `/private/tmp/tmcp-composition-next2/.tmp/lift-next2/calibration-phase-handoffs-v5`

Migration full-composition quality in the observed spot pair was `0.782`
versus naïve `0.744`; diagnose full-composition quality was `0.357` versus
naïve `0.458`. Both comparisons are non-paired single cells from an incomplete
15/540 subset, and the full scorer rejects the subset. They are useful for
prioritizing handoff quality only, not for a causal lift, receipt, promotion, or
release claim. No receipt was recorded.

### Authorized machine-readable phase-gate calibration (2026-07-22)

The next bounded calibration kept the handoff envelope and made the external
runner parse each `EXIT_GATE` status before hydrating the next phase. A phase
worker receives only its current-stage sources when the preceding status is
`PASS`; after `FAIL`, `BLOCKED`, or an unparseable gate it receives a blocked
handoff without deferred skill bodies. This mirrors the tracked runtime's
active/deferred safety boundary.

- campaign: `composition-lift-campaign-91b9f99de690ec4cc908`
- campaign digest: `91b9f99de690ec4cc9089cbed3a4d785c77df82391ee7d0c9ab7bda5ebf39592`
- host cells: 15/15, SHA-256
  `874ea953a9ca3a84bd3cd3e4c4339c45ede41116d7f6064c8e2e38c1ba85f657`
- blind-judge cells: 15/15, SHA-256
  `e37f7d7954ec36a676250f6ec44147cfdf1964252c4bd1b8591c34542cf9dc22`
- output directory: `/private/tmp/tmcp-composition-next2/.tmp/lift-next2/calibration-phase-gates-v6`
- observed full-composition gate traces: migration `FAIL -> BLOCKED ->
  BLOCKED -> BLOCKED`; diagnose `PASS -> PASS -> FAIL -> BLOCKED`
- directional spot quality: migration `0.633` full versus `0.813` naive;
  diagnose `0.345` full versus `0.405` naive

The safety result is positive: deferred bodies were not activated after a
failed or blocked gate, and wrong-order controls stayed blocked after their
first phase. The quality result exposes a benchmark-design tension rather than
an excuse to weaken the gate: the current migration fixture intentionally
withholds production-scale evidence, so strict advancement stops later
assessment skills while its rubric still rewards a complete downstream matrix.
The next slice must make this distinction explicit—separating hard execution
advancement from source-backed reporting/assessment continuation, or revising
the fixture graph so a failed readiness gate is genuinely a prerequisite. This
15/540 subset is unpaired diagnostic evidence; the full scorer rejects it. No
receipt, promotion, or release claim was made.

### Authorized reporting-continuation phase-gate calibration (2026-07-22)

The semantic gate-policy slice makes the distinction explicit. Newly compiled
plans carry `entry_gates_and_handoffs`; legacy or hand-authored plans retain the
`strict_exit_and_entry_gates` default. Under the new policy, runtime advancement
still requires every target entry gate and every exact typed handoff. A failed
non-entry exit gate remains in the phase trace, diagnostics, and warning surface
but does not authorize downstream execution. The external harness hydrates later
full-composition stages only for reporting, assessment, or follow-up design and
keeps execution and authorization claims blocked.

- campaign: `composition-lift-campaign-99cf7ca99b308daa6bd2`
- campaign digest: `99cf7ca99b308daa6bd290fe7e6f8c7960ba8bb0d40fe8424bc0a781d3042002`
- control plan: `benchmark-control-cd3466603a14ae78e39e`
- control plan digest: `cd3466603a14ae78e39e1122f33ac64051069e259ca40150deedc8b522bef89d`
- host cells: 15/15, SHA-256
  `4f7086d8a4b928b04bd5bd929081d8a7f80d3d591b6b7373b99f1f63af6f3df3`
- blind-judge cells: 15/15, SHA-256
  `6f3a1cedc149e45a14b8b26eb85b7315870bf65fa7d50e6f5cdcf13d34d38cf4`
- full-composition traces: UI `PASS -> PASS -> FAIL -> BLOCKED`; migration
  `FAIL -> FAIL -> BLOCKED -> BLOCKED`; agent `PASS -> PASS -> PASS -> FAIL`;
  research `PASS -> PASS -> PASS -> PASS`; diagnose `PASS -> PASS -> PASS -> BLOCKED`

The bounded cells are intentionally unpaired directional observations, weighted
with the preregistered fixture rubrics:

| fixture | naive union | full composition | wrong order |
| --- | ---: | ---: | ---: |
| UI/product | 0.496 | 0.4595 | 0.2225 |
| migration/data | 0.736 | 0.558 | 0.410 |
| agent workflow | 0.940 | 0.926 | 0.5515 |
| research -> writing -> review | 0.908 | 0.806 | 0.088 |
| diagnose -> fix -> regression | 0.418 | 0.351 | 0.052 |

This calibration demonstrates the intended safety/product behavior: later
assessment can explain what remains blocked without pretending that a failed
prerequisite was executed or authorized, and a missing typed handoff still
blocks phase transition. It is not lift evidence: the sample is 15/540 and
unpaired, so no synergy, compiler, or order-lift claim is made. No receipt,
promotion, or release claim was recorded. The complete paired campaign and
independent rejudge remain required.

### Authorized bridge-obligation and cumulative-index calibrations (2026-07-22)

The next bounded checks measured two presentation fixes against the same
content-bound campaign/control plan. The first made each active phase's required
input, produced handoff, covered criterion, exit gate, and source citation
explicit in the phase contract. The second added a deterministic quote-only
cumulative deliverable index before the phase bodies so a composed packet keeps
its concrete diagnosis, fix, regression, and release outputs legible without
inventing execution evidence.

- campaign: `composition-lift-campaign-756054f78e2589944a3f`
- campaign digest: `756054f78e2589944a3fe46fc784d3890a97c5641e1bbcc39c443515d83d2fa9`
- control plan: `benchmark-control-c189f4c3bff573a2008aa0`
- v8 host/judge artifacts: 15/15 each, SHA-256
  `4d52b114832ed9c73592dc279f0e69540cb523a9778532142162152de1d13493` and
  `bdc71b11621622401ebd0cbbe059bccd50e1cfb3fe8c5d1ee0d3646d95e78895`
- v9 typed-obligation artifacts: 15/15 each, SHA-256
  `1b0e6459b09d9364a1a470d2be086176da8520700acf6b2af4fad3acd9606fc7` and
  `f90e079cd72c4ef331dfc81be4ed9f305c60a2ccf4a880566ec91fdf482ddaa9`
- v10 cumulative-index artifacts: 15/15 each, SHA-256
  `d0ada84ca479ab395d2cff9703d872e21f3591c3be22c372afd26eb0da79ef0c` and
  `4ccfbf1d05864894ab90ae24d6f292374eb251df47c2fae6132b748ac708ee54`

The v10 spot scores (one unpaired cell per arm and fixture) were:

| fixture | naive union | full composition | wrong order |
| --- | ---: | ---: | ---: |
| UI/product | 0.533 | 0.580 | 0.315 |
| migration/data | 0.200 | 0.843 | 0.710 |
| agent workflow | 0.878 | 0.953 | 0.673 |
| research -> writing -> review | 0.893 | 0.748 | 0.048 |
| diagnose -> fix -> regression | 0.405 | 0.370 | 0.070 |

These values are directional only: the 15/540 subset is unpaired, model
sampling varies between cells, and the full scorer rejects it as incomplete.
The index materially improved the migration and agent handoffs and narrowed the
diagnose gap, but diagnose remains the next quality target. No receipt,
promotion, causal lift, or release claim was recorded; the full paired campaign
and independent rejudge remain required.

### Authorized external-run pilot (2026-07-21)

After explicit authorization, one runner dispatch and its independent blind
judge were exercised through an isolated temporary Codex home. The pilot used
the `behavior-ui-product` fixture and preserved the opaque runner/judge
boundary; it was not expanded into the 540-cell campaign because TMCP has no
host supervisor that resolves opaque execution references, persists the cell
contracts, and safely schedules 540 external runner calls plus 540 independent
judgments.

The raw pilot artifacts remain outside the repository at
`/private/tmp/tmcp-external-pilot/`:

- runner artifact: `artifact.md`, SHA-256
  `61f22675b239d29e85ec37afc0ef826fb43e1e63fd877985c7b0aa223e261a08`
- blind-judge artifact: `judge.md`, SHA-256
  `e6e66081d2503a499720ce00c2befce36e2a343995e0eee80f2a089f9ab23279`
- independent judge result: weighted score `0.738` under
  `tmcp-ui-product-quality-v0.1`

The pilot is launchability evidence only. The runner reported source-level
accessibility and responsive checks but correctly marked rendered browser and
accessibility-tree verification blocked because the fixture has no browser
engine or accessibility package. The subprocess also retained visibility of
global skill descriptions despite `--ignore-user-config --ignore-rules`; strict
clean-room skill isolation therefore remains unproven. Neither artifact is a
`tmcp-composition-lift-host-results-v0.1` or
`tmcp-composition-lift-evaluator-artifacts-v0.1` campaign result, and no receipt,
lift, causal claim, promotion candidate, or release claim may be derived from
this pilot.

### Subscription calibration and artifact-boundary rejudge (2026-07-21)

The authorized subscription-only calibration exercised five behavioral fixtures
across the proposed runner slots before any campaign-scale dispatch:

- `slot-1-luna-low`: `gpt-5.6-luna`, low reasoning
- `slot-2-terra-low`: `gpt-5.6-terra`, low reasoning
- `slot-3-terra-medium`: `gpt-5.6-terra`, medium reasoning
- blind judge: `gpt-5.6-terra`, medium reasoning

All 15 runner calls and all 15 blind-judge calls exited successfully through
the logged-in ChatGPT subscription. The runner manifest is outside the
repository at `/private/tmp/tmcp-calibration-20260721/manifest.json`, digest
`7cef4f7cbe492c7305a15bcb263ea85229b53cf655530653644693d3c681bdcf`; the
bundle-aware blind-judge manifest is at
`/private/tmp/tmcp-calibration-20260721/judges-bundled/manifest.json`, digest
`7ef51746e9870731168cd5c1bfdc6c7c7b6fc8c50037f66165a575165e23072c`.

The first 15-cell judge pass was intentionally rejected as a harness result:
its mean score was `0.1664` because the judge received runner handoff text
that pointed to files without receiving those files. The repaired rejudge
materialized the handoff plus runner-created files, while excluding fixture
instruction files and campaign/controller metadata. Its mean score was
`0.5683` (median `0.5575`), with every cell parsed and every judge call exiting
zero. This is an artifact-contract and launchability finding, not a model
quality or causal-lift claim. Slot means were `0.6041` (Luna/low), `0.5489`
(Terra/low), and `0.5518` (Terra/medium); the spread does not justify changing
the preregistered slot assignments on this sample.

For every external run, the submitted host artifact must therefore be a
bounded materialized bundle: the runner handoff plus the files it created and
their verification evidence. A path-only pointer is an anti-pattern because
it makes blind scoring dependent on inaccessible runner state and can turn a
valid implementation into an unevaluable summary. The bundle must still omit
fixture instructions, controller identity, skill order, graph identity, and
execution recipes. The calibration remains outside the six required campaign
artifacts and cannot support receipt, lift, promotion, or release claims.

Promotion is a separate, non-mutating gate. After a complete eligible summary,
retain the primary evaluator artifacts and obtain a second blind judgment in
`tmcp-composition-lift-rejudge-envelope-v0.1`. The independent executor and
execution ID must differ from the primary evaluation, and the second judgment
must cover the same 540 cells and agree within the preregistered tolerance.
Only then may `scripts/promote_guidebook_from_campaign.py` emit an
`eligible_for_manual_review` candidate. The candidate is not an automatic
guidebook rewrite or a release receipt; raw artifacts remain the evidence of
record for human review and later replication.

The campaign's 540 cells are intentionally carried by separate experimental
cell-result contracts. The ordinary benchmark host/evaluator artifacts collapse
one result per variant, which is sufficient for the release benchmark but cannot
prove the campaign's three configuration slots and two replicates. A host
supervisor therefore returns one cell in
`tmcp-composition-lift-host-results-v0.1` for every opaque runner dispatch, and a
blind evaluator returns one cell in
`tmcp-composition-lift-evaluator-artifacts-v0.1` for every judge dispatch. Each
cell binds its dispatch digest, slot/replicate coordinate, artifact digest, and
rubric evidence. TMCP rejects missing cells, duplicate cells, crossed campaign
digests, dispatch drift, host/evaluator artifact mismatches, rubric omissions,
and secret-like evidence before scoring.

Score the completed cell bundle with:

```bash
python3 scripts/score_composition_lift_campaign.py \
  --campaign path/to/composition-lift-campaign.json \
  --host-results path/to/composition-lift-host-results.json \
  --evaluator-artifacts path/to/composition-lift-evaluator-artifacts.json
```

The scorer computes matched full-versus-singleton, naïve-union, and wrong-order
differences for all six slot/replicate pairs in each fixture, then reports the
median lift. Synthetic test classes remain useful for contract tests but always
fail the real-host and trusted-evaluator eligibility checks. The summary is
advisory lift evidence only; routing recall, provenance, context residency,
safety, receipts, promotion, and release admissibility remain separate gates.

Each of the five fixture blocks contains 36 baseline cells—no skill, naïve
union, and four singletons across three configuration slots and two
replicates—and 72 causal cells covering all twelve controls across the same
slots and replicates. Bind a concrete host configuration explicitly and keep it
matched within each comparator pair; TMCP reserves the slots but does not choose
or run host configurations.

To make the blind boundary operational, prepare one audience-specific bundle
for each external process:

```bash
python3 scripts/prepare_composition_lift_dispatches.py \
  --campaign path/to/composition-lift-campaign.json \
  --audience runner \
  --output-dir path/to/runner-dispatches

python3 scripts/prepare_composition_lift_dispatches.py \
  --campaign path/to/composition-lift-campaign.json \
  --audience judge \
  --output-dir path/to/judge-dispatches
```

The runner bundle contains only opaque execution references and the bounded
runner instruction. The judge bundle contains only opaque artifact slots and
the fixture rubric. Neither bundle contains controller cells, skill order,
graph identity, or execution recipes. The execution input may include a bounded
`task_context` artifact whose evidence is explicitly `fixture_supplied`; it is a
precondition, never proof that the runner performed the corresponding check.

Controller cells retain condition identity, recipe, graph, and provenance for
audit. Never send those cells to a runner or evaluator. Instead send only the
block's opaque `runner_dispatches` to runners and `blind_judge_dispatches` to
judges; the latter carry the exact quality rubric while neither dispatch surface
contains a condition label, skill order, graph, or execution recipe. Runners
must keep `fixture_supplied`, `host_executed`, and unavailable or unverified
evidence distinct in their artifact; judges must score only what the artifact
actually supports.

Run the final two steps with every bound artifact:

```bash
python3 scripts/assemble_composition_benchmark.py observations \
  --run-plan path/to/benchmark-run-plan.json \
  --semantic-proposals path/to/semantic-proposals.json \
  --control-plan path/to/benchmark-control-plan.json \
  --host-results path/to/host-results.json \
  --evaluator-artifacts path/to/evaluator-artifacts.json \
  --output-dir path/to/assembled

python3 scripts/run_composition_benchmark.py \
  path/to/assembled/benchmark-observations.json \
  --run-plan path/to/benchmark-run-plan.json \
  --semantic-proposals path/to/semantic-proposals.json \
  --control-plan path/to/benchmark-control-plan.json \
  --host-results path/to/host-results.json \
  --evaluator-artifacts path/to/evaluator-artifacts.json
```

For a 0.6+ release, commit the six exact bound artifacts in the canonical,
external-only bundle directory `docs/COMPOSITION_BENCHMARK_BUNDLE/`:

- `benchmark-run-plan.json`
- `semantic-proposals.json`
- `benchmark-control-plan.json`
- `host-results.json`
- `evaluator-artifacts.json`
- `benchmark-observations.json`

The directory must contain exactly those regular files, each must be
Git-tracked and unchanged from `HEAD`, and the host/evaluator serializations are
secret-scanned before use. It is intentionally excluded from the release
archive: the package runner consumes the source-worktree bundle during release
verification but does not distribute raw host or evaluator evidence.

With that canonical bundle present, run the package check without artifact
flags:

```bash
python3 scripts/check_release_package.py . --verify-reproducible
```

For an ad hoc review, the package checker also accepts a complete explicit set
of six paths:

```bash
python3 scripts/check_release_package.py . \
  --composition-benchmark-observations path/to/observations.json \
  --composition-benchmark-run-plan path/to/benchmark-run-plan.json \
  --composition-benchmark-semantic-proposals path/to/semantic-proposals.json \
  --composition-benchmark-control-plan path/to/benchmark-control-plan.json \
  --composition-benchmark-host-results path/to/host-results.json \
  --composition-benchmark-evaluator-artifacts path/to/evaluator-artifacts.json \
  --verify-reproducible
```

The package checker keeps 0.5.x behavior compatible when no artifact path is
supplied. Starting with 0.6.0 it resolves the canonical bundle when no paths
are supplied, rejects a partial explicit set, and fails whenever the bundled
benchmark runner does not return a fully eligible summary. Supplying any
artifact path for an earlier release still requires the same complete set.

The observations object uses schema `tmcp-composition-benchmark-observations-v0.1` and contains complete `routing_results` for every golden case plus complete `behavioral_results` for all five fixtures. Missing or unexpected IDs are malformed evidence. Every routing case and every behavioral control carries a content-derived execution record, a hash-bound run receipt, and inline digest-verified evidence. Each behavioral result must include selected and ordered skills, active stages, provenance-backed typed relationships, compiler-derived phase-capsule accounting, compatibility aliases for runtime-peak and naive-union context tokens, and observed quality for no-skill, naive union, every singleton, full composition, every leave-one-out ablation, and wrong-order controls.

## Phase-capsule context accounting

The compiler serializes and token-estimates three canonical context forms: a
bounded discovery capsule, one active capsule for each ordered stage, and a
fair naive-union capsule containing the standard runtime envelope plus all
selected skill sources—but no composition-only stages, graph edges, handoffs,
or plan identity. An active agent capsule carries only the objective, task
model, current phase's entry conditions and bridge instructions, active source
skill identity/role/text, and actionable incoming handoff facts. Equivalent
handoffs share their executable facts but retain every handoff identity; full
source provenance, controller identifiers, handoff contracts, and graph
identity remain in the outer compiler accounting and phase binding rather than
being charged as agent-loaded prompt context. The release ratio is the peak active runtime
capsule divided by the naive-union capsule. Discovery cost is reported
separately and is never counted as concurrent runtime residency; the same-host
transcript total remains visible for diagnosis.

Each full-composition host receipt must bind the compiler accounting digest,
preflight capsule digest, and every stage capsule in order.
`same_host_transcript` is valid diagnostic evidence but cannot qualify a
release or project recipe, even when its numeric ratio is below the threshold.
Only `isolated_phase_capsule` qualifies the execution-mode gate, and its
preflight and every phase must name distinct opaque context-instance IDs. These
IDs are structural, advisory evidence—not cryptographic proof that a model
provider discarded hidden transcript state. Safe assembled receipts retain mode
and digest traces but intentionally omit those IDs and raw handoff bodies.

## Materialized fixture and run provenance

Every behavioral fixture declares `skill_sources` for all candidates. Materialize each `relative_path` with its exact behavior-bearing `content` before harvesting. Observed `source_slices` retain the materialized source path, exact content, and full-slice offsets. TMCP recomputes each harvested `source_node_id`, source/slice digest, and slice ID, then recomputes graph identity from normalized source content and typed relationship edges. Relationship `citations` must reference that inventory and cover both endpoint skills.

Each behavioral observation also carries the actual `preflight_id`, `composition_plan_id`, 32-character `graph_digest`, and `task_identity`. Its `run_receipt` must use `tmcp-run-receipt-v0.1`, bind the same recipe/task/graph/content and harvested source-node selection, contain a non-blocked phase trace plus explicit passing gates, reproduce the scored quality and context metrics, and contain no user override. This benchmark does not accept a plan description without matching run evidence.

The receipt trace is the runtime trace, not a benchmark-specific imitation: every
record must name the compiler stage and its matching phase, request the phase it
advances to, and carry exactly the gate and typed-handoff obligations the
compiler derives for that transition. Benchmark recipes intentionally reject
user redirects, identity changes, and phase overrides so the original compiler
control remains replayable.

## External evaluator contract

Quality is an external observed judgment, not a TMCP-generated value. Each
fixture supplies a versioned weighted rubric with review criteria and required
evidence. The evaluator artifact binds every dimension score to the exact host
artifact digest and control input/recipe digest. The assembler then emits
`evaluation_provenance` with:

- evaluator identity/version, evaluation run ID, timestamp, and method;
- the exact fixture rubric ID, version, and canonical digest;
- evidence references for that variant;
- a 0–1 score for every rubric dimension.

TMCP recomputes each weighted mean and rejects a reported quality score that does
not match its per-dimension scores. Every required rubric item must cite
variant-local evaluator evidence, and every reference must resolve to an inline
evidence-manifest record whose content digest and content-derived ID match,
whose execution ID is valid, and whose execution record binds its legacy input,
compiler-control input, artifact, result, recipe, and receipt digests. Free-text
host/evaluator fields are bounded and rejected when TMCP's redactor detects
secret-like content; persisted receipts are safe projections that omit raw
commands, verification logs, and overrides.

This is content-bound, replayable evidence with
`evidence_trust: advisory_untrusted`, not cryptographic proof that an independent
host or evaluator performed the claimed work. A reviewed release therefore still
requires human scrutiny of the bound artifacts. The release runner also requires
`host-results.evidence_class: "host_executed"` and an
`evaluator-artifacts.evaluator_execution` record with
`execution_class: "trusted_evaluator_execution"`, executor ID, execution ID,
and UTC execution time. `synthetic_test` is a bounded contract-test class only;
it and test-only evaluator methods are rejected by the benchmark runner CLI,
package, and release-evidence replay. The programmatic `allow_synthetic=True`
mode remains unit-test-only. These declarations are a release admissibility
gate, not a cryptographic attestation of the host or evaluator.

The runner exits `0` only when all gates pass:

- expected-skill recall `1.00`, precision at least `0.90`, and no active conflict violations;
- every expected/non-root relationship has harvested-slice provenance and expected ordering matches exactly;
- median synergy lift at least `0.10`, compiler lift at least `0.05`, and order lift at least `0.05`;
- aggregate and per-fixture peak-runtime/naive-union context ratios at or below `0.75`;
- an `isolated_phase_capsule` execution-context trace for every behavioral fixture.

It exits `1` for a complete but ineligible run and `2` for malformed or
incomplete evidence. The scorer never generates, fills, or infers observations;
the separate assembler only projects compiler facts and evaluator evidence after
replaying and validating the controls. Synthetic unit data in
`tests/test_tmcp_composition_benchmarks.py` verifies calculations only and must
never be cited as release evidence.

Retain the exact successful CLI output, including top-level `ok: true` and the SHA-256 digest of the exact observations bytes parsed by the runner, as the reviewed benchmark summary. Published schemas cover the [routing golden](../schemas/tmcp-composition-routing-golden-v0.1.schema.json), [behavioral fixtures](../schemas/tmcp-composition-behavioral-fixtures-v0.1.schema.json), [observations](../schemas/tmcp-composition-benchmark-observations-v0.1.schema.json), and [summary](../schemas/tmcp-composition-benchmark-summary-v0.1.schema.json).

## Reviewed release evidence

Before changing the active version to 0.6.0 or newer, preserve the exact eligible
runner output as `docs/COMPOSITION_BENCHMARK_SUMMARY.json` and commit it. Commit
the canonical six-artifact bundle described above, then add and commit a
`composition_benchmark` record in `docs/RELEASE_EVIDENCE.json` with:

- schema `tmcp-composition-benchmark-release-evidence-v0.1` and the active release
  version;
- status `reviewed` and summary path
  `docs/COMPOSITION_BENCHMARK_SUMMARY.json`;
- SHA-256 digests of the canonical observations and committed summary;
- an exact `bundle` projection (the canonical paths, per-file hashes,
  `evidence_trust: advisory_untrusted`, and manifest digest);
- an approved review containing a non-empty reviewer, UTC review timestamp, and
  matching `bundle_manifest_digest`.

The release-evidence record has this shape; replace every placeholder with the
reviewed run's exact value:

```json
{
  "composition_benchmark": {
    "schema": "tmcp-composition-benchmark-release-evidence-v0.1",
    "version": "0.6.0",
    "status": "reviewed",
    "summary_path": "docs/COMPOSITION_BENCHMARK_SUMMARY.json",
    "observations_sha256": "<sha256-of-canonical-observations>",
    "summary_sha256": "<sha256-of-committed-summary>",
    "bundle": {
      "schema": "tmcp-composition-benchmark-bundle-v0.1",
      "path": "docs/COMPOSITION_BENCHMARK_BUNDLE",
      "artifacts": {
        "benchmark-run-plan.json": {"path": "docs/COMPOSITION_BENCHMARK_BUNDLE/benchmark-run-plan.json", "sha256": "<sha256>"},
        "semantic-proposals.json": {"path": "docs/COMPOSITION_BENCHMARK_BUNDLE/semantic-proposals.json", "sha256": "<sha256>"},
        "benchmark-control-plan.json": {"path": "docs/COMPOSITION_BENCHMARK_BUNDLE/benchmark-control-plan.json", "sha256": "<sha256>"},
        "host-results.json": {"path": "docs/COMPOSITION_BENCHMARK_BUNDLE/host-results.json", "sha256": "<sha256>"},
        "evaluator-artifacts.json": {"path": "docs/COMPOSITION_BENCHMARK_BUNDLE/evaluator-artifacts.json", "sha256": "<sha256>"},
        "benchmark-observations.json": {"path": "docs/COMPOSITION_BENCHMARK_BUNDLE/benchmark-observations.json", "sha256": "<sha256>"}
      },
      "evidence_trust": "advisory_untrusted",
      "manifest_digest": "<sha256-of-canonical-bundle-manifest>"
    },
    "review": {
      "status": "approved",
      "reviewer": "<reviewer>",
      "reviewed_at": "<UTC-timestamp>",
      "bundle_manifest_digest": "<same-canonical-manifest-digest>"
    }
  }
}
```

`scripts/check_release_evidence.py` resolves the Git-clean canonical bundle,
checks that its record and reviewer digest match exactly, replays all six files
through the current runner, and requires the replay output to exactly equal the
committed summary. It rejects an untracked or changed summary/bundle, incomplete
routing or behavioral metrics, an ineligible summary, secret-like raw
host/evaluator text, or missing review metadata. The evidence remains advisory,
not an authentication claim about the host or evaluator. Do not replace the
bound artifacts with unit-test fixtures or inferred scores.
