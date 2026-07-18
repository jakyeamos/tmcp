# Refactor-clean composition candidate v0

Status: **approved for preregistration only; not preregistered or behaviorally
evaluated.** The candidate was author-drafted and then independently reviewed;
No runner, judge, or external model call has been made for it.

This is the next admissible step for the packet-probed TMCP compiler plus
`refactor-clean` pair. It preserves one small, synthetic dependency-graph case
for a future behavioral study.

## Target and bounded question

- Target source: `/Users/jakyeamos/skills/engineering/refactor-clean/SKILL.md`
- Source digest at drafting: `sha256:90709ad4daf33b34ded487de2a5e666e130969c1abb431306efc20d3388000d0`
- Packet evidence already established: TMCP preserves the source's
  consumer-surface verification gate in a local packet. That is not an artifact
  outcome.

If admitted to a later study, the question may be whether adding
the exact, byte-pinned `refactor-clean` source bundle to the same shared TMCP
packet changes the quality of refactor-planning artifacts on reviewed synthetic
fixtures. The only possible claim would be a **source-bundle delivery effect**.
It would not measure live TMCP selection, individual instruction adherence,
code-change quality, or corpus-wide skill quality.

## Review packet

- [First principles](first-principles.md) is a faithful, compact account of the
  target skill's relevant judgment standard.
- [Synthetic fixture and bar](fixtures/refactor-clean-dependency-graph-v0.json)
  contains the only task evidence a future blind runner would receive and the
  separate bar a judge would receive.

The fixture must remain synthetic and read-only. A future runner should return a
plan inline, not inspect a repository, write files, or execute a refactor.

## Candidate-readiness gate

[`preregistration-readiness.json`](preregistration-readiness.json) is the
no-call readiness record for this candidate. It binds the live source digest,
first-principles digest, independent review record, fixture digest, and
synthetic/no-tool boundary. It intentionally reports `ready: false`: the
candidate has one fixture in one family, no archived source bundle, and no
dedicated packet-probe receipt. `model_calls_authorized` remains `false`; the
next admissible gate is to extend the independently reviewed fixture set.

## Independent-review decision

An independent reviewer recorded a decision in `fixture-review.md`. Before a
study directory, source bundle, model matrix, or launch command is created, a
future preregistration must also answer all of these questions:

1. Is the prompt direct enough that each bar outcome can be evaluated from the
   supplied graph alone?
2. Is the bar a fair test of `refactor-clean`'s first principles without
   prescribing one exact module layout or plan wording?
3. Does the graph contain enough genuine ambiguity to test ownership judgment,
   rather than merely reward repeating the prompt?
4. Are the failure smells real violations rather than defensible design choices?
5. Does the synthetic/no-tool boundary eliminate live-repository and side-effect
   risk?

`approved` means only that this fixture may enter a future preregistration. It
does not authorize a model call or promote the pair. `revise` or `reject` keeps
the candidate out of every behavioral plan.

## Evidence boundary

This candidate is evidence-design work. It supports neither a behavioral claim
nor a guidebook pattern. The campaign ledger remains authoritative for promotion
state and must continue to list TMCP plus `refactor-clean` as `packet-probed`
until a separately approved, preregistered, independently reviewed campaign
clears its reliability, replication, safety, cost, and human-review gates.
