# Fresh baseline diagnosis

This local diagnosis classifies the completed intact-only baseline before any
revision to `/Users/jakyeamos/skills/authoring/eval-skills/SKILL.md`. It does
not alter the pinned target, fixtures, raw traces, or original verdicts.

## Evidence inspected

- All 36 primary judge traces and their runner/judge artifacts.
- The independently reviewed v2 fixtures and first-principles text.
- The archived condition-blind 36-trace cost-sidecar record and its failed
  retained-cost-bar provenance check.
- The target skill's preflight, isolation, nondeterminism, diagnosis, revision,
  and full-suite re-evaluation instructions.

The repaired `failure_diagnosis` family passed 6/6 across all runner
identifiers. The remaining five families are event-direct and their bars are
expressible by the target skill. No miss is classified as a fixture/bar defect.

## Trace classification

| Repeated gap | Failed traces | Classification | Target surface |
| --- | ---: | --- | --- |
| First-principles/mode clarification and echo | 3 | target defect | Workflow step 1 |
| Contamination recovery: future sandbox + sweep | 2 | target defect | Workflow step 2 |
| Per-case before/after rate reporting | 7 | target defect | Steps 4, 7, Output |
| Repeat every material case, not only one case | 3 | target defect | Step 4, Output |
| Separate judge omitted during otherwise sound recovery | 1 | model variance | Step 3 regression probe |
| Exact leading-directive replacement omitted | 1 | model variance | Step 6 regression probe |
| Repeat the diagnose-revise-sweep cycle omitted | 1 | model variance | Step 7 regression probe |
| Defect-vs-bad-case diagnosis omitted once | 1 | model variance | Step 5 regression probe |

Counts overlap when one artifact misses both reporting dimensions.

The table has 19 criterion-level misses across 16 failed traces. Twelve traces
contain a repeated target-defect candidate; four contain only an isolated
model-sensitive omission. The isolated misses remain in the next baseline as
regression probes; they do not justify broadening the target.

## Archived cost record

The sidecar recorded one potential target-skill cost-control defect: Step 7 says
to loop until every case clears a rate bar, but neither the target nor its first
principles defines that bar, a revision budget, or a stop point. The retained
cost bar does not match the digest recorded by the sidecar, however, so that
observation cannot establish a defect or justify a target edit. Preserve it
unchanged as diagnostic history and re-test the bounded-cycle hypothesis only in
a new preregistered run with a verifiable cost bar.

## Proposed minimal target revision — not applied

1. Make Workflow step 1 require an explicit preflight handoff: confirm or ask
   for the target's first principles, settle judgment versus conformance, and
   echo the agreed mode and per-case bar before a runner is launched.
2. Make the contamination recovery invariant compact and non-optional: invalidate
   the contaminated result; preserve unrelated checkout work; use a fresh runner
   with only the skill and case input; use a sandbox as the only writable root;
   use a separate judge; sweep the live checkout after every run.
3. Make the nondeterminism/output contract state that every important or
   release-critical case receives its own repetitions and pass rate, with a
   per-case before/after report and cited gaps after a justified edit.
4. Treat a bounded replacement for the unbounded Step 7 loop as a hypothesis,
   not an evidence-backed correction, until a new cost sidecar verifies it:
   after each justified edit, run the preregistered full-suite/repetition
   schedule; if a case misses its predeclared rate bar, diagnose skill defect
   versus bad case; start another revision cycle only after naming the defect
   and its additional work/budget, otherwise report the unresolved or structural
   limit.

Each proposed change maps to an observed omission and preserves the target's
first principles. No edit should be made merely to improve a score.

## Harness correction applied locally

TMCP now reports a policy-bound original-only study as `baseline_reliability`:
real pass rates, per-fixture results, per-runner-model coverage, raw safety/cost
counts, and any separately verified sidecar cost counts. It omits causal pattern
claims and marks causal lift as not applicable. Direct-attachment traces also mark
activation/adherence heuristics not applicable when their protocol lacks the
telemetry those scores require.

Raw traces and the first scored report remain immutable. The regenerated scored
report is an interpretation correction, not a new model result.

## Required next proof

Before external execution, independently review a v3 fixture that exercises a
persistent post-edit miss and the bounded next-cycle rule. Then run the same
36-cell original-only baseline with a new pinned target digest and complete,
blind, independently verified cost sidecar. Do not run an ablation until every
baseline floor clears and the revised sidecar is reproducible.
