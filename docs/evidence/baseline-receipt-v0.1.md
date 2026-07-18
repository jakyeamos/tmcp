# Baseline receipt contract v0.1

`tmcp-skill-eval-baseline-receipt-v0.1` is an eligibility artifact for a later
causal campaign. It is not a causal result, a guidebook claim, or permission to
make a remote call.

## Required evidence

The receipt must identify a completed original-only campaign and preserve
digests for its plan, manifest, raw traces, and scored report. Its compatibility
object must match the later causal plan's control rows exactly for:

- control variant;
- fixture, task-evidence, and control-attachment digests;
- source and packet digests when the plan exposes them;
- clustered-analysis policy and reliability thresholds; and
- runner configurations plus the independent judge configuration.

The receipt also records per-fixture and per-runner coverage, raw and
adjudicated safety/cost status, `causal_applicable: false`, and
`meets_predeclared_floors`. A causal launcher must reject a missing, held,
digest-drifted, incomplete, or unresolved receipt before remote schema
preflight or any runner/judge cell.

Build one from a completed original-only campaign with:

```bash
python3 scripts/build_baseline_receipt.py \
  --plan <baseline-plan.json> \
  --manifest <campaign-manifest.json> \
  --traces <traces.json> \
  --report <baseline-report.json> \
  --output <baseline-receipt.json>
```

## Evidence boundary

Passing the receipt gate means only that the planned control is sufficiently
reliable and compatible to make a later contrast interpretable. It does not
show that an intervention works, that a source was selected or followed, or
that any guidebook entry should be promoted. Preserve the baseline's raw
artifacts and any independent rejudge separately from the later causal bundle.
