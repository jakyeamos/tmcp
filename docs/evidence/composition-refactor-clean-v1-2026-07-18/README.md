# TMCP + `refactor-clean` source-bundle study v1

Status: **preregistered design only; no runner, judge, cost-rejudge, or other
remote model call has been made.** The six-fixture candidate passed its
independent review, exact source-bundle gate, and local packet-probe gate.

## Bounded question

Does adding the byte-pinned `refactor-clean` source bundle to the same shared
TMCP packet change planning-artifact quality on the six reviewed synthetic
fixtures? The only admissible claim is a **source-bundle delivery effect**.
This study does not measure live skill selection, instruction adherence,
code-change quality, whole-corpus skill quality, or guidebook promotion.

## Preregistered design

- Study input: [`inputs/study.json`](inputs/study.json)
- Candidate readiness binding: six independently reviewed fixtures across six
  families, with `model_calls_authorized: false`.
- Control: `packet_only`.
- Treatment: exactly `packet_only +` the raw, byte-pinned `refactor-clean`
  source bundle.
- Fixture matrix: six fixtures, two variants, three runner configurations, and
  two repetitions per cell; the causal plan has 12 matrix rows and would yield
  72 runner artifacts if separately approved and executed.
- Judge: the pinned independent judge configuration in the campaign policy;
  judges receive the runner artifact and bar, not the arm label, source
  attachment, or other verdicts.
- Cost: a separate condition-blind rejudge is preregistered for the exact 72
  runner artifacts and cannot substitute for correctness judgment.
- Baseline: a compatible completed original-only baseline receipt and ready
  verifier record are required before causal launch.

## Verification

[`generated/study-verification.json`](generated/study-verification.json) is the
no-call verification artifact. It confirms the checked-in plan reproduces from
the pinned inputs, validates the 12-row matrix and 72-trace cost policy, and
matches the live source digest. It does not authorize calls.

The candidate readiness record and the study binding also preserve the secure
receipt persistence limitation: the local packet output and receipt are
available and digest-bound, while the CLI's unavailable durable global receipt
path remains explicitly recorded rather than silently treated as successful.

## Promotion boundary

Even a completed study could only support the preregistered source-bundle
effect after baseline reliability, safety, cost, replication, and human-review
gates clear. A result cannot become a corpus-wide skill or guidebook default
from this pair alone.
