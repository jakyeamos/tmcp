# Independent fixture review — v2

Status: approved for preregistration on 2026-07-17.

An independent fixture-review pass examined the two historical failure families
against the unedited `eval-skills` target. It found bad-case defects, not target
skill defects. The reviewed fixtures are pinned in
[`inputs/fixtures-reviewed-v2.json`](inputs/fixtures-reviewed-v2.json).

## Review contract

For every fixture, the reviewer checked that:

1. each required observable and failure smell describes an event present in the
   prompt;
2. each bar is expressible by the unedited target skill; and
3. the runner can answer from only the target skill and task while the judge can
   assess it from the predeclared bar without seeing the condition.

## Repaired family: `failure_diagnosis`

The historical prompt asked only for the pre-edit response, but O5 graded the
conditions for a later edit. The reviewed prompt now explicitly supplies the
sequence: resolve first principles and mode with the user; replace the template
bar; observe a fresh corrected run with one-pass/no-rate behavior; diagnose that
named defect; then state the full verification sweep after a justified edit.

The exact-template mismatch remains a bad-bar diagnosis. It does not authorize
rewriting the skill to output seven headings.

## Repaired family: `regression_retest`

The historical prompt omitted the new post-edit miss that O4 graded. The
reviewed prompt now states the complete sweep, B's pass, and A's new miss before
asking for the next revision decision. It therefore grades the required
diagnose-revise-full-sweep loop without inventing a later event.

## Attestation

The two repaired prompts are event-direct; all six fixture bars are expressible
by the target `eval-skills` workflow; and the attached policy must not be
generated or launched with different fixture content. This review approves a
fresh intact-only reliability baseline, not a causal promotion claim.
