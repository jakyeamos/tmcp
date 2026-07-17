# Explore Unknowns composition study v1

This directory preregisters a bounded behavioral composition study for the
materialized `explore-unknowns` Stage-1 source bundle. It is local preparation;
no runner or judge model call has been made from this study directory.

## Question and boundary

The study asks whether adding the exact pinned Stage-1 source bundle to one shared
TMCP packet changes judged Stage-1 behavior on six reviewed fixtures. It can
support only a **source-bundle delivery** claim. It does not measure live TMCP
selection, instruction-adherence telemetry, general skill quality, or corpus-wide
guidebook readiness.

The local packet is identified in [inputs/study.json](inputs/study.json), with the
corresponding advisory receipt copied in
[inputs/packet-receipt.json](inputs/packet-receipt.json). Those artifacts bind
inputs; they are not behavioral evidence.

## Preregistered design

Each fixture has two otherwise identical arms:

- `packet_only`: the byte-pinned packet attachment.
- `packet_plus_explore`: exactly `packet_only + source-bundle.md`.

The source bundle includes the Stage-1 operating material and an explicit
no-tools/stage-boundary preamble. Its complete digest, the individual selected
source path/digests, shared packet digest, advisory receipt digest, fixture digest,
and task evidence digest are embedded in every matrix row. Trace scoring excludes
a controlled trace when its provenance does not exactly match that row.

The campaign policy is three high-reasoning runner configurations, two repetitions,
and one separate high-reasoning judge: 6 fixtures × 2 arms × 3 runners × 2
repetitions = 72 cells. Control reliability floors, clustered analysis, independent
fixture review, and cost/safety handling are pinned in
[inputs/campaign-policy.json](inputs/campaign-policy.json) and
[inputs/study.json](inputs/study.json).

## Reproducibility

`scripts/generate_composition_study_plan.py` regenerates
[generated/tmcp-composition-study-plan.json](generated/tmcp-composition-study-plan.json)
only from the files in `inputs/`. The test suite rebuilds the plan and asserts it
is byte-for-byte equivalent after JSON decoding, then validates it through TMCP's
evaluation API.

Before a live campaign, verify both the immutable evidence bundle and (only when
you explicitly opt in) whether the live source paths still match their pinned
digests. This verifier makes no model call and prints only path/digest status, not
source contents.

```sh
python3 scripts/verify_composition_study.py \
  --study-dir docs/evidence/composition-explore-unknowns-v1-2026-07-17 \
  --require-live-sources
```

```sh
python3 scripts/generate_composition_study_plan.py \
  --study-dir docs/evidence/composition-explore-unknowns-v1-2026-07-17 \
  --output docs/evidence/composition-explore-unknowns-v1-2026-07-17/generated/tmcp-composition-study-plan.json
```

The campaign launcher has already accepted the generated plan in `--dry-run` mode.
Launching runners or a judge requires fresh approval because it spends external
model capacity and creates new behavioral evidence. Source-bundle launches also
require `--composition-study-dir` so the launcher records a successful immutable
input and live-source verification in its campaign manifest.
