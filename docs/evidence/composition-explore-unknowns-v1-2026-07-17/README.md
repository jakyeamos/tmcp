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

## Independent cost sidecar

The primary judge's raw cost labels remain preserved. Before this study may be
considered for promotion, a separate, condition-blind cost rejudge must cover all
72 completed runner artifacts using the exact
[cost bar](inputs/cost-evaluation-bar.md) and
[sidecar policy](inputs/cost-rejudge-policy.json). The policy records a fresh,
artifact-only, isolated judging process, but explicitly does not claim a
distinct-model replication because the rejudge model is one of the runner model
identifiers. TMCP scoring treats the required sidecar as a promotion gate, not a
documentation-only checklist.

The rejudge launcher must also match the policy's model, reasoning effort, seed,
exact cost-bar filename and byte digest, and expected trace count. Its manifest
and scored sidecar carry the resulting policy binding; scoring rejects a sidecar
without that exact binding. This prevents a self-consistent but drifted rejudge
from clearing the promotion gate.

After the sidecar completes, verify its persisted cells, source traces, policy
binding, prompt-input audit, and schema preflight before scoring:

```bash
python3 scripts/verify_cost_rejudge.py \
  --source-plan docs/evidence/composition-explore-unknowns-v1-2026-07-17/generated/tmcp-composition-study-plan.json \
  --source-runs <primary-runs> \
  --cost-bar-file docs/evidence/composition-explore-unknowns-v1-2026-07-17/inputs/cost-evaluation-bar.md \
  --rejudge-runs <independent-cost-rejudge-runs> \
  --expected-trace-count 72 \
  --require-promotion-ready
```

This command is read-only and must exit successfully; a valid but legacy bundle
is reported as not promotion-ready rather than inheriting the current study's
claim strength.

Score a completed source-bundle study only through the verified scoring path. It
runs the artifact verifier in-process, refuses any non-promotion-ready sidecar,
then records the exact source-plan, trace, and sidecar digests with the score.
It also rechecks that the **primary** campaign retained its matching
prompt-isolation audit, all four remote-schema preflights and their synthetic
prompt/output-schema digests, immutable/live-source verification bound to the
same pinned plan inputs and selected sources, policy-bound runner/judge
model-and-effort settings, clean completion, and unique runner/judge thread
coverage. The primary evidence must also retain the exact local campaign-harness
module bytes named by the manifest's harness digest; hashes alone are not a
replayable measurement-instrument record:

```bash
python3 scripts/score_composition_study.py \
  --source-plan docs/evidence/composition-explore-unknowns-v1-2026-07-17/generated/tmcp-composition-study-plan.json \
  --source-runs <primary-runs> \
  --cost-bar-file docs/evidence/composition-explore-unknowns-v1-2026-07-17/inputs/cost-evaluation-bar.md \
  --rejudge-runs <independent-cost-rejudge-runs> \
  --expected-trace-count 72 \
  --output <verified-score.json>
```

The output must be a new file outside both raw-evidence directories. Do not use
the generic evaluator alone to represent this study as promotion-ready.

The sidecar is a later external run and therefore needs separate fresh approval
after the primary 72 cells have completed. It may adjudicate only C1 cost labels;
it never rewrites raw labels or revisits correctness, safety, selection, or
adherence.

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
