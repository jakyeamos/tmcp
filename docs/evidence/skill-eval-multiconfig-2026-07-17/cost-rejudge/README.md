# Independent cost rejudge

## Status

The approved condition-blind rejudge completed 72 fresh isolated judge threads
and its retained cell artifacts report `cost_regression=false`. It is now
classified as **diagnostic history, not reproducible promotion evidence**: the
bundle records cost-bar digest `sha256:3412…e053c`, but the checked-in
[`cost-evaluation-bar.md`](cost-evaluation-bar.md) is
`sha256:bf4d…f2c6`. Because the exact bar used by the rejudge is no longer
available, a read-only verifier cannot reconstruct or promote the bundle. Do
not use its adjudicated cost result to support a current claim.

The first sandbox-only attempt produced zero completed judgments because the
sandbox could not resolve the Codex service. Its invalidated stage artifacts
remain under [`run/`](run/) and are not evidence. The first externally approved
attempt then surfaced an invalid response-schema contract before any judgment
completed; it remains under [`approved-run/`](approved-run/) as invalidated
diagnostic evidence. The service-compatible completed bundle is
[`approved-run-v2/`](approved-run-v2/), with its resulting score under
[`approved-score/`](approved-score/).

## Fixed input boundary

- Source plan: [`../generated/tmcp-skill-evaluation-plan.json`](../generated/tmcp-skill-evaluation-plan.json)
- Source artifacts and traces: [`../runs/`](../runs/)
- Fixed traces: exactly 72, each checked against its manifest, cell aggregate,
  runner output, raw judge output, stage marker, event stream, stderr digest,
  usage record, and unique source thread IDs.
- Judge input: only the task, one runner artifact, and the predeclared
  [cost bar](cost-evaluation-bar.md). The prompt excludes the condition,
  attachment, original judge decision, trace path, and variant labels.

## Output contract

`scripts/tmcp_skill_eval_cost_rejudge.py` creates a separate output bundle and
a complete `cost-rejudgments.json` sidecar. Every entry contains the source
trace digest, one C1 citation, an internally consistent cost verdict, and
fresh blinded-session provenance. The scorer accepts this sidecar only when it
covers every supplied trace and its digests agree; it retains both the raw and
adjudicated cost summaries instead of mutating `runs/traces.json`.

The rejudge does not make the existing campaign promotable on its own. The
cluster/reliability replay records a 0% intact-control pass rate on the
regression-retest fixture and 16.7% on failure diagnosis, below the new 50%
per-fixture floor. The historical plan also did not predeclare its clustered
analysis policy, so its cluster interval remains diagnostic only.
