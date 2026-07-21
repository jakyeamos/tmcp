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
host without evidence for the role or handoff claims it is proposing.

This is a deterministic corpus/readiness check only. It proves that the
benchmark can expose observable artifacts and cited handoffs; it does not
generate model results, receipts, lift, or release evidence.

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
graph identity, or execution recipes.

Controller cells retain condition identity, recipe, graph, and provenance for
audit. Never send those cells to a runner or evaluator. Instead send only the
block's opaque `runner_dispatches` to runners and `blind_judge_dispatches` to
judges; the latter carry the exact quality rubric while neither dispatch surface
contains a condition label, skill order, graph, or execution recipe.

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
