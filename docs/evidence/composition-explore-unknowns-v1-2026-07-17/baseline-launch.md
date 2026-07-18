# Original-only baseline launch handoff

Status: **ready for a fresh external-call approval; not run.** The derived
baseline plan is locally verified and the launcher reports 36 cells with no
readiness gaps. This handoff authorizes no model call by itself.

## Pinned inputs

- Causal study: `generated/tmcp-composition-study-plan.json`
- Baseline plan: `generated/tmcp-composition-baseline-plan.json`
- First principles: `inputs/first-principles.txt`
- Source-study verification: this directory with `--composition-study-dir`
- Runner configurations: `gpt-5.6-sol:high`, `gpt-5.6-terra:high`, and
  `gpt-5.6-luna:high`
- Independent judge: `gpt-5.5:high`
- Expected cells: 36 (six fixtures × three runners × two repetitions)

## Approval-gated launch

After fresh approval for these external runner and judge calls, run from the
TMCP root:

```sh
python3 scripts/tmcp_skill_eval_campaign.py \
  --plan docs/evidence/composition-explore-unknowns-v1-2026-07-17/generated/tmcp-composition-baseline-plan.json \
  --output-dir <baseline-runs> \
  --codex-home <codex-home> \
  --cleanroom <empty-cleanroom> \
  --first-principles-file docs/evidence/composition-explore-unknowns-v1-2026-07-17/inputs/first-principles.txt \
  --pattern-id composition.source-bundle-inclusion \
  --intervention-target source_bundle \
  --runner-config gpt-5.6-sol:high \
  --runner-config gpt-5.6-terra:high \
  --runner-config gpt-5.6-luna:high \
  --design baseline_reliability \
  --judge-model gpt-5.5 \
  --judge-effort high \
  --expected-fixtures 6 \
  --repetitions 2 \
  --composition-study-dir docs/evidence/composition-explore-unknowns-v1-2026-07-17 \
  --require-preregistered
```

The output directory must remain immutable after completion. Preserve its
manifest, harness snapshot, remote-schema receipts, event streams, traces, and
report. Do not resume a drifted run or replace failed artifacts in place.

## Receipt and promotion boundary

Build the receipt from the exact persisted baseline artifacts:

```sh
python3 scripts/build_baseline_receipt.py \
  --plan docs/evidence/composition-explore-unknowns-v1-2026-07-17/generated/tmcp-composition-baseline-plan.json \
  --manifest <baseline-runs>/campaign-manifest.json \
  --traces <baseline-runs>/traces.json \
  --report <baseline-report.json> \
  --output <baseline-runs>/baseline-receipt.json
```

Independently inspect that receipt before attaching it to the causal plan. It
must be completed, `causal_applicable: false`, clear on raw and adjudicated
safety/cost status, and meet the predeclared aggregate and per-fixture floors.
A held receipt remains useful evidence but cannot authorize the 72-cell causal
study. The receipt is an eligibility dependency, not a composition effect.

After the receipt passes those checks, update the causal study's pinned
`baseline_dependency.receipt_sha256`, regenerate its plan, and obtain a new
fresh approval for the separate 72-cell runner/judge campaign. Request the
72-trace cost rejudge separately after the primary campaign completes.
