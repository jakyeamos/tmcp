# Cluster and control-reliability replay

This is a local replay of the fixed 72 raw traces with the hardened evaluator.
It is a retrospective diagnostic, not a promotion upgrade: the July 17 plan
did not predeclare the clustered analysis policy.

## Relative effect

The fixture-block bootstrap retains all three runner configurations inside each
sampled fixture block and averages paired repeat effects before resampling
fixtures. The result is a 95% intervention-minus-control interval of
`[-0.750, -0.194]` (`10,000` deterministic resamples, seed `20260717`). The
negative direction still supports the intact `Workflow` section.

## Absolute reliability

| Intact-control fixture family | Pass rate |
| --- | ---: |
| claim calibration | 6/6 (100.0%) |
| contamination handling | 6/6 (100.0%) |
| revision discipline | 3/6 (50.0%) |
| regression retest | 0/6 (0.0%) |
| failure diagnosis | 1/6 (16.7%) |
| evaluation mode | 4/6 (66.7%) |

Overall intact control reliability is 20/36 (55.6%), which clears the 50%
aggregate floor. The per-fixture floor is 50%, and the observed minimum is 0%,
so promotion remains held even if the pending cost rejudge resolves both raw
cost labels.

## Current hold set

- The original plan has no predeclared clustered-analysis policy.
- The original raw traces still contain cost labels until a complete sidecar is
  produced by the independent rejudge.
- Per-fixture intact-control reliability is below 50%.

The evaluator now requires those conditions to be explicit in plans generated
after this change and renders the clustered interval in preference to the
older Newcombe-Wilson diagnostic.
