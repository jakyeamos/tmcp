# Fresh multi-model baseline

This directory is the reproducible preregistered baseline for the unedited
`/Users/jakyeamos/skills/authoring/eval-skills/SKILL.md` target. It supersedes
neither the historical 72-cell causal contrast nor its hold: it tests whether
the intact target is reliable before any new causal ablation is considered.

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
3. Run the complete 36-artifact blind cost rejudge and score its digest-bound
   sidecar with the original traces.
4. Treat the resulting report as a baseline gate: a pass supports later causal
   testing; it never alone promotes a corpus-wide guidebook rule.

Generated plans, live run receipts, sidecars, and scoring outputs are retained
beside these inputs. Any failure, invalidation, retry, missing sidecar entry, or
missed reliability floor keeps the guidebook claim on hold.
