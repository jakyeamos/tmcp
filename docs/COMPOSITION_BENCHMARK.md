# Composition Benchmark Contract

TMCP 0.6 is release-eligible only after real host-run observations pass the compositional acceptance gate. Golden prompts and behavioral fixture definitions describe what to run; they contain no quality scores and are not evidence by themselves.

Run:

```bash
python3 scripts/run_composition_benchmark.py path/to/observations.json
```

For a release-package check, pass the same real observations explicitly:

```bash
python3 scripts/check_release_package.py . \
  --composition-benchmark-observations path/to/observations.json \
  --verify-reproducible
```

The package checker keeps 0.5.x behavior compatible when this option is absent.
Starting with 0.6.0 it fails closed without the option, and it fails whenever the
bundled benchmark runner does not return a fully eligible summary. Supplying the
option for an earlier release still runs the benchmark check.

The observations object uses schema `tmcp-composition-benchmark-observations-v0.1` and contains complete `routing_results` for every golden case plus complete `behavioral_results` for all five fixtures. Missing or unexpected IDs are malformed evidence. Every routing case and every behavioral control carries a content-derived execution record, a hash-bound run receipt, and inline digest-verified evidence. Each behavioral result must include selected and ordered skills, active stages, provenance-backed typed relationships, compiled and naive context tokens, and observed quality for no-skill, naive union, every singleton, full composition, every leave-one-out ablation, and wrong-order controls.

## Materialized fixture and run provenance

Every behavioral fixture declares `skill_sources` for all candidates. Materialize each `relative_path` with its exact behavior-bearing `content` before harvesting. Observed `source_slices` retain the materialized source path, exact content, and full-slice offsets. TMCP recomputes each harvested `source_node_id`, source/slice digest, and slice ID, then recomputes graph identity from normalized source content and typed relationship edges. Relationship `citations` must reference that inventory and cover both endpoint skills.

Each behavioral observation also carries the actual `preflight_id`, `composition_plan_id`, 32-character `graph_digest`, and `task_identity`. Its `run_receipt` must use `tmcp-run-receipt-v0.1`, bind the same recipe/task/graph/content and harvested source-node selection, contain a non-blocked phase trace plus explicit passing gates, reproduce the scored quality and context metrics, and contain no user override. This benchmark does not accept a plan description without matching run evidence.

## External evaluator contract

Quality is an external observed judgment, not a TMCP-generated value. Each fixture supplies a versioned weighted rubric with review criteria and required evidence. For every control variant, `evaluation_provenance` must record:

- evaluator identity/version, evaluation run ID, timestamp, and method;
- the exact fixture rubric ID, version, and canonical digest;
- evidence references for that variant;
- a 0–1 score for every rubric dimension.

TMCP recomputes each weighted mean and rejects a reported quality score that does not match its per-dimension scores. Every reference must resolve to an inline evidence-manifest record whose content digest and content-derived ID match, whose execution ID is valid, and whose execution record binds its input, artifact, result, and receipt digests. This cryptographic linkage makes the reviewed bundle tamper-evident; the external evaluator remains responsible for the judgment itself. Synthetic records and scores in unit tests prove contract math only.

The runner exits `0` only when all gates pass:

- expected-skill recall `1.00`, precision at least `0.90`, and no active conflict violations;
- every expected/non-root relationship has harvested-slice provenance and expected ordering matches exactly;
- median synergy lift at least `0.10`, compiler lift at least `0.05`, and order lift at least `0.05`;
- aggregate and per-fixture compiled context ratios at or below `0.75`.

It exits `1` for a complete but ineligible run and `2` for malformed or incomplete evidence. The scorer never generates, fills, or infers observations. Synthetic unit data in `tests/test_tmcp_composition_benchmarks.py` verifies calculations only and must never be cited as release evidence.

Retain the exact successful CLI output, including top-level `ok: true` and the SHA-256 digest of the exact observations bytes parsed by the runner, as the reviewed benchmark summary. Published schemas cover the [routing golden](../schemas/tmcp-composition-routing-golden-v0.1.schema.json), [behavioral fixtures](../schemas/tmcp-composition-behavioral-fixtures-v0.1.schema.json), [observations](../schemas/tmcp-composition-benchmark-observations-v0.1.schema.json), and [summary](../schemas/tmcp-composition-benchmark-summary-v0.1.schema.json).

## Reviewed release evidence

Before changing the active version to 0.6.0 or newer, preserve the exact eligible
runner output as `docs/COMPOSITION_BENCHMARK_SUMMARY.json` and commit it. Add and
commit a `composition_benchmark` record in `docs/RELEASE_EVIDENCE.json` with:

- schema `tmcp-composition-benchmark-release-evidence-v0.1` and the active release
  version;
- status `reviewed` and summary path
  `docs/COMPOSITION_BENCHMARK_SUMMARY.json`;
- SHA-256 digests of the external observations and committed summary;
- an approved review containing a non-empty reviewer and UTC review timestamp.

The release-evidence record has this shape; replace every placeholder with the
reviewed run's exact value:

```json
{
  "composition_benchmark": {
    "schema": "tmcp-composition-benchmark-release-evidence-v0.1",
    "version": "0.6.0",
    "status": "reviewed",
    "summary_path": "docs/COMPOSITION_BENCHMARK_SUMMARY.json",
    "observations_sha256": "<sha256-of-external-observations>",
    "summary_sha256": "<sha256-of-committed-summary>",
    "review": {
      "status": "approved",
      "reviewer": "<reviewer>",
      "reviewed_at": "<UTC-timestamp>"
    }
  }
}
```

`scripts/check_release_evidence.py` rejects an untracked or changed summary, a
summary that does not match the exact bundled contract, a mismatch between the
recorded observation digest and the digest embedded by the runner, incomplete
routing or behavioral metrics, an ineligible summary, or missing review metadata.
Raw observations remain explicit external input; do not replace them with
unit-test fixtures or inferred scores.
