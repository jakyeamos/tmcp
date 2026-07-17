# Fresh baseline readiness contract — not run

This is the preregistration target for the next `eval-skills` reliability study.
It intentionally does not reuse the historical 72-cell campaign as a baseline:
that plan did not predeclare the clustered/reliability policy and used one model
with three reasoning settings.

## Scope

- Design: `baseline_reliability`; original attachment only.
- Size: 6 fixtures × 3 pinned runner configurations × 2 repetitions = 36 cells.
- Required runner matrix: three configuration pairs across at least two distinct
  runner models. The judge model must not be in the runner model set.
- Minimum reliability: 18/36 overall and at least 3/6 on every fixture, with the
  fixture-block clustered policy pinned before the first runner call.
- Cost: an all-artifact, digest-bound condition-blind sidecar using the faithful
  checkout-sweep bar. Raw judge labels remain unchanged.

## Fixture repair before pinning

Two historical families are not direct enough for a reliability claim:

- `regression_retest`: its O4 scored the loop after a *new* post-edit miss, while
  the prompt described only the first failed run. The revised prompt must introduce
  the new miss before grading that loop.
- `failure_diagnosis`: its O5 scored requirements for a later edit although the
  prompt asked what happens before an edit. The revised prompt must include the
  edit condition or drop that observable.

An independent reviewer must attest that each revised prompt contains every graded
event, every bar is expressible by the target skill, and its digest is final before
the campaign policy is generated.

## Launch gate

Generate the plan with a `tmcp-skill-eval-campaign-policy-v0.1` containing the
baseline thresholds, runner matrix, judge configuration, and cross-model contract.
Run `tmcp_skill_eval_campaign.py --design baseline_reliability
--require-preregistered` and retain both `remote-schema-preflight.json` and
`campaign-readiness.json`. Do not begin a causal microablation until this baseline
clears every stated floor.
