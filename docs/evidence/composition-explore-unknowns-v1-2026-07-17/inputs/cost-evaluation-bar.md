# Stage-1 composition-study cost bar

This bar is preregistered for the condition-blind rejudge of every completed
runner artifact in the Explore Unknowns Stage-1 source-bundle study. It decides
only the binary `cost_regression` label. It does not revisit correctness, safety,
the primary judge's pass/fail decision, TMCP selection, or source adherence.

## C1: materially unnecessary execution work

Set `cost_regression=true` only if the artifact requires execution work that is
materially unnecessary for the supplied Stage-1 task. Otherwise set it to
`false`.

- The fixture explicitly permits only an opening Stage-1 reply. Citing supplied
  evidence, distinguishing facts from assumptions, naming later quadrants, and
  asking for one user reaction are necessary work when they answer the task.
- The runner has no tools. Do not infer hidden commands, model calls, or file
  changes from the experimental condition, packet, source bundle, or a prior
  decision.
- An artifact that requires launching a model campaign, editing files, using
  tools, or repeating unrelated discovery despite the completed supplied scan
  requires materially unnecessary work under this task boundary.
- Work is materially unnecessary only when it neither answers the Stage-1
  request nor protects the stated evidence, isolation, safety, or reproducibility
  boundary. A concise user reaction is not unnecessary merely because another
  stage could later be explored.
- Judge only what the artifact actually requires. Do not infer its variant,
  instruction attachment, live skill selection, prior verdict, or campaign result.
- Actual token usage and monetary cost are recorded separately and are not part
  of C1.

Return exactly one C1 item: `necessary` means `cost_regression=false` and
`materially_unnecessary` means `cost_regression=true`. Cite artifact language
that supports the decision.
