# Independent expanded-fixture review

Status: **revise before preregistration**.

This is a read-only review of the five pending fixtures against the pinned
`refactor-clean` source (`sha256:90709ad4daf33b34ded487de2a5e666e130969c1abb431306efc20d3388000d0`).
No runner, judge, live-repository inspection, fixture-JSON edit, or model call
was used; this review record is the only file written.

## Review standard

I checked each fixture for (1) prompt-direct observables, (2) fidelity to the
skill's one-owner/stale-path/consumer-verification rules, (3) genuine ownership
ambiguity, (4) failure smells that are violations rather than preferences, and
(5) a synthetic, no-tool, no-side-effect boundary.

## Per-fixture decisions

### `flag-state-has-parallel-owners-v0` — **revise**

The graph directly supplies the canonical state machine, checkout duplicate,
operator duplicate, published v1 boundary, and consumer requirement (fixture
JSON lines 13–22). The consumer-verification and external-boundary smells are
faithful to the skill: owner-only tests, unexplained duplicate tables, and
unsupported v1 changes are real failures (lines 24–28). The no-tool contract is
complete (lines 31–35).

The defect is the second observable: it asks a runner to explain whether
`forceEnable` is a valid event or a stale duplicate (line 20), but the supplied
graph gives no semantics for that path beyond its operator-tool use. A plan
that chooses either classification would invent facts; a plan that preserves
the uncertainty could be unfairly marked incomplete. This is a first-principles
bar defect, not useful ambiguity.

Exact revision: change that observable to require the plan to mark
`forceEnable` as unresolved from the supplied evidence, name the contract or
behavioral evidence needed to classify it, and conditionally fold it into the
owner or retain a named short-lived seam with a removal condition. Alternatively,
add synthetic evidence that establishes the force semantics and supports both
candidate ownership decisions.

### `legacy-money-export-has-boundary-seam-v0` — **approved**

The prompt cleanly separates the maintained `minorUnits.ts` owner, copied
analytics map, and externally consumed CSV with an explicit support date and
unknown consumers (lines 13–14). The bar permits an external compatibility seam
but requires a concrete removal/migration condition and internal consolidation
(lines 17–22), matching the skill's external-boundary exception. KWD appears in
both owner and duplicate map, so consumer-level matrix verification can expose
the stated under-test without needing hidden numeric facts. The failure smells
(lines 24–28) are direct violations, and the blindness/no-tool contract is
adequate (lines 31–35).

### `dev-query-adapter-is-sediment-v0` — **approved**

Development-only status, no shipped package consumers, the unsupported CLI
prototype note, and repository-complete scope directly justify deleting or
collapsing the adapter rather than preserving it (lines 13–14). The bar maps to
the skill's explicit rejection of dev-only compatibility and its consumer
verification rule (lines 17–22); all listed smells are real (lines 24–28).
CLI and indexer are named separately, so owner-module tests cannot substitute
for consumer checks. No external consumer is smuggled in, and the no-tool
contract is explicit (lines 31–35).

Minor wording hardening before preregistration: the standard says “verify the
shipped search surfaces” (line 17) even though the CLI is explicitly
development-only. It should say “verify the CLI and indexer consumer surfaces”
to match the observable and avoid a scope contradiction. This does not change
the decision.

### `marker-geometry-has-placeholder-drift-v0` — **approved**

The prompt establishes one geometry owner, two named consumers, a symmetric
placeholder versus asymmetric production asset, and unknown outside consumers
(lines 13–14). The bar requires porting both consumers, removing independent
coordinate computation, and re-verifying with the real asymmetric asset
(lines 17–22), directly matching the skill's placeholder/orientation rule and
consumer-verification rule. The failure smells are concrete (lines 24–28), and
the missing production asset is safely treated as a future verification input,
not hidden repository state. The synthetic/no-tool boundary is adequate (lines
31–35).

### `render-phase-has-duplicate-labels-v0` — **approved**

The graph names the ordered pipeline owner, the preview label duplicate and
omitted `commit`, the debug re-derivation, and a separately supported external
plugin bridge (lines 13–14). The bar correctly distinguishes internal
consolidation from an external, time-bounded compatibility boundary and asks
for consumer checks against the owner's actual sequence (lines 17–22). Each
failure smell is a direct violation of one-owner, no-rederivation, or boundary
rules (lines 24–28). The plugin replacement is intentionally unknown rather
than invented, and the no-tool contract is complete (lines 31–35).

## Initial set-level decision (superseded by follow-up below)

**Revise.** Four fixtures are suitable as written; the flag-state fixture must
be repaired before the set can enter a preregistration. The dev-query wording
should also be tightened as noted above. After those text-only revisions, run a
fresh independent review; do not change fixture JSON in place under an existing
review record or start a study from this pending set.

## Follow-up review of revised fixtures

Follow-up status: **all five expanded fixtures approved for preregistration
only** (2026-07-18). No model call or behavioral authorization follows from
this update.

### Revised `flag-state-has-parallel-owners-v0` — **approved**

The revised observable now requires preserving `forceEnable` as unresolved,
naming the evidence needed to classify it, and supplying a conditional
fold-or-remove path with a removal condition (fixture JSON line 20). That fixes
the prior fairness defect: the runner can demonstrate epistemic restraint from
the graph alone, while the judge can still score ownership judgment and seam
handling. The remaining observables, failure smells, and synthetic/no-tool
contract remain direct and faithful (lines 17–35). No fixture revision remains.

### Revised `dev-query-adapter-is-sediment-v0` — **approved**

The standard now says to verify the CLI and indexer consumer surfaces (fixture
JSON line 17), resolving the prior wording mismatch with the explicitly
development-only CLI. The owner, unsupported adapter, complete repository-local
scope, consumer checks, failure smells, and no-tool boundary remain direct
(lines 13–35). No fixture revision remains.

## Follow-up set-level readiness

The expanded fixture set is **approved for preregistration only, not ready for
launch**. The candidate README and readiness record correctly retain the
no-call boundary; `preregistration-readiness.json` reports `ready: false`,
`preregistration_ready: false`, `model_calls_authorized: false`, and missing
packet-probe/source-bundle gates (lines 74–88 of that file). Its per-fixture
`fixture_review_not_approved` / `fixture_review_record_missing` gaps are now
stale because this follow-up record is the independent approval; regenerate the
readiness artifact so it binds this review digest and the revised fixture
digests. Archive the source bundle and packet receipt before any future study
plan. No remaining fixture-content revision is required.
