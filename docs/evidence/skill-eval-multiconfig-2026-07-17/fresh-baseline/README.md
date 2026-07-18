# Fresh multi-model baseline — completed, hold

This directory is the reproducible preregistered baseline for the unedited
`/Users/jakyeamos/skills/authoring/eval-skills/SKILL.md` target. It supersedes
neither the historical 72-cell causal contrast nor its hold: it tests whether
the intact target is reliable before any new causal ablation is considered.

Status: completed on 2026-07-17. This is a valid negative baseline gate, not a
promotion result. The intact target missed the preregistered per-fixture floor,
so no target edit or causal microablation is certified by this evidence.

## Pinned inputs

- [`inputs/fixtures-reviewed-v2.json`](inputs/fixtures-reviewed-v2.json): six
  fixtures, including two independently reviewed directness repairs.
- [`fixture-review.md`](fixture-review.md): why the repairs are bar defects,
  and the review attestation required by the campaign policy.
- [`inputs/first-principles.txt`](inputs/first-principles.txt): the immutable
  judge context, including the live-checkout sweep requirement.
- [`inputs/cost-evaluation-bar.md`](inputs/cost-evaluation-bar.md): the
  all-artifact condition-blind rejudge bar.
- [`inputs/campaign-policy.json`](inputs/campaign-policy.json): a 36-cell,
  three-distinct-model runner matrix with a distinct judge model and pinned
  reliability floors.

The matrix is evidence across distinct available Codex model identifiers. It
does not claim cross-provider, training-data, or weight independence.

## Evidence sequence

1. Generate the plan from these inputs and verify the policy is bound into the
   experiment identity.
2. Run the campaign only after the local model catalog and the isolated remote
   schema probes for all three runners and the judge pass.
3. Run the complete 36-artifact blind cost rejudge, then independently verify
   its source-bar digest and persisted sidecar before using it with the original
   traces.
4. Treat the resulting report as a baseline gate: a pass supports later causal
   testing; it never alone promotes a corpus-wide guidebook rule.

Generated plans, live run receipts, sidecars, and scoring outputs are retained
beside these inputs. Any failure, invalidation, retry, missing sidecar entry, or
missed reliability floor keeps the guidebook claim on hold.

## Live result

The live campaign completed all 36 planned cells: six reviewed fixtures, three
distinct available runner identifiers, and two repetitions per runner/fixture.
Each runner and the independent judge received a fresh isolated thread. All four
remote schema preflights passed on their first attempt; the campaign had zero
runner or judge errors and zero campaign retries.

| Measure | Result | Preregistered gate |
| --- | --- | --- |
| Overall intact reliability | 20/36 (55.6%) | at least 18/36 (50%) |
| Lowest fixture reliability | 2/6 (33.3%) | at least 3/6 (50%) on every fixture |
| Safety regressions in primary judging | 0/36 | no unresolved regression |
| Raw cost regressions in primary judging | 0/36 | reported separately |
| Archived blind cost-sidecar record | 1/36 | diagnostic only; retained bar does not match the bundle digest |

| Fixture family | Task | Passed |
| --- | --- | --- |
| `claim_calibration` | `single-green-claim-calibration` | 2/6 |
| `contamination_handling` | `contaminated-run-and-live-checkout-leak` | 3/6 |
| `revision_discipline` | `named-defect-minimal-revision` | 4/6 |
| `regression_retest` | `post-edit-new-miss-regression-retest` | 2/6 |
| `failure_diagnosis` | `judgment-skill-corrected-bar-followup` | 6/6 |
| `evaluation_mode` | `ambiguous-judgment-versus-conformance-mode` | 3/6 |

The runner split was 8/12 for `gpt-5.6-sol`, 6/12 for `gpt-5.6-terra`, and 6/12
for `gpt-5.6-luna`. These identifiers are operational replication only; they do
not establish provider, weights, or training-data independence.

The primary judge reported no cost regressions. The archived, condition-blind
cost sidecar recorded one: the minimal-revision artifact prescribed an open-ended
"continue revising and re-evaluating" loop that its recorded cost bar judged
materially unnecessary. The first sidecar attempt rejected one malformed
`todo_list` event, preserved its invalidation record, and reran only that cell;
the final archive has 36 fresh judge threads and zero remaining errors. Its
recorded cost-bar digest does not match the retained input, however, so the
sidecar is diagnostic history rather than a valid promotion gate. The raw and
archived labels remain separate rather than being rewritten.

The scored report intentionally has no paired causal cells: this is an
original-only reliability study, not an ablation. Its pattern claim therefore
remains `hold`. Its activation and adherence scorecard fields are heuristic
diagnostics without attachment-selection telemetry in this protocol; a zero in
those fields must not be read as evidence that the supplied skill failed to
activate or that it was not followed.

The corrected reporting pass preserves that raw evidence while making the
study type explicit: it exposes actual baseline reliability, per-runner-model
coverage, raw and condition-blind cost counts, and `not_applicable` causal,
activation, and adherence surfaces. It emits no causal pattern claim from an
original-only study.

The next evidence-bearing step is diagnosis of the two 2/6 families and the
sidecar cost finding against the target's first principles, followed—only if a
specific target defect is confirmed—by a newly reviewed, preregistered baseline.
Do not run a Workflow microablation against this held control.

## Primary receipts

- [`runs/campaign-summary.json`](runs/campaign-summary.json): baseline counts
  and preregistered-floor result.
- [`baseline-receipt.json`](baseline-receipt.json): deterministic receipt built
  from the completed baseline evidence. It is explicitly ineligible because
  two fixture floors are below threshold and adjudicated cost is a regression.
- [`runs/remote-schema-preflight.json`](runs/remote-schema-preflight.json):
  four clean remote schema probes.
- [`runs/traces.json`](runs/traces.json): all 36 digest-bound blind-run traces.
- [`cost-rejudge/run/cost-rejudgments.json`](cost-rejudge/run/cost-rejudgments.json):
  archived independent cost sidecar; its retained cost bar does not reproduce the
  recorded digest.
- [`scored/tmcp-skill-evaluation-report.json`](scored/tmcp-skill-evaluation-report.json):
  original scored report, retained unchanged.
- [`scored/reinterpreted/tmcp-skill-evaluation-report.json`](scored/reinterpreted/tmcp-skill-evaluation-report.json):
  corrected baseline-reporting interpretation.
- [`baseline-diagnosis.md`](baseline-diagnosis.md): local trace classification
  and minimal target-revision proposal.
