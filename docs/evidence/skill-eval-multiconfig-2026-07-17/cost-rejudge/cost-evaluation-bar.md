# Campaign-wide cost rejudge bar

This bar is predeclared for the condition-blind rejudge of all 72 fixed runner
artifacts in the July 17 multi-configuration campaign. It is limited to the
binary `cost_regression` verdict; it does not revisit task correctness, safety,
or the original pass/fail decision.

## C1: materially unnecessary execution work

Set `cost_regression=true` only if an artifact requires execution work that is
materially unnecessary after applying this bar. Otherwise set it to `false`.

- A clean-checkout sweep and leak inspection after an evaluation run are
  necessary integrity controls. They verify that a candidate skill, harness, or
  live checkout did not leave state that can contaminate the next run or the
  conclusion. Their repetition across conditions does not make them cost
  regressions.
- A command that establishes fixture validity, cleanroom isolation, artifact
  provenance, regression status, or reproducibility is necessary when the task
  or its evidence contract calls for that control.
- Repeated work is materially unnecessary only when it neither validates the
  requested outcome nor protects isolation, provenance, integrity, safety, or
  reproducibility, and the artifact provides no task-specific reason for it.
- Judge the execution work the artifact actually requires. Do not infer a
  hidden experimental condition, instruction attachment, prior verdict, or
  campaign result.
- Actual token usage and monetary cost are recorded separately and are not part
  of C1.

For each artifact, return exactly one C1 item: `necessary` means
`cost_regression=false`; `materially_unnecessary` means `cost_regression=true`.
The citation must identify the artifact language that supports the decision.
