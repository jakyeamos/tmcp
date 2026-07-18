# TMCP composition probes

Status: local packet-level evidence only. No target skill, fixture, runner
artifact, or judge call was sent to an external service.

These probes test whether TMCP preserves the constraints that make a skill pair
meaningful before spending a behavioral-campaign budget. They do not measure a
pair's behavioral effectiveness.

## Probe results

| Pair | Objective boundary | Result | What it establishes |
| --- | --- | --- | --- |
| TMCP compiler + `explore-unknowns` | Map four quadrants before any implementation | Pass after route fix | The packet is `general_task`, cites all staged exploration references, and retains stage-boundary stop conditions. |
| TMCP compiler + `refactor-clean` | Remove an obsolete owner and verify consumers | Pass after gate projection | The packet is `general_task`, cites the refactor source, and preserves a consumer-surface verification gate rather than reducing the source to generic tests. |
| TMCP compiler + `repo-behavior-spec-loop` | Audit a canonical evidence ledger; stop before fixes | Pass after route fix | The packet is `general_task`, requires `references/loop.md`, retains the canonical-ledger instruction, output contract, audit checkpoints, and test gates. |
| TMCP compiler + `write-docs` | Draft source-grounded documentation that cites implementation evidence | Pass after route fix | The packet is `general_task`, cites the documentation source, and does not activate frontend behavior from the generic implementation stem. |
| TMCP compiler + `wizard` | Plan a synthetic, no-write credential handoff | Pass after safety-gate projection | The packet is `general_task`, requires confirmation before irreversible or external actions, and forbids an end-to-end run of a human-interactive wizard. |
| TMCP compiler + `fold-feature-branches` | Classify a synthetic branch without mutation | Pass after safety-gate projection | The packet is `general_task`, cites the fold source, preserves dirty/ambiguous branch protection, and requires live-remote plus ancestry/`git cherry` supersession checks. |
| TMCP compiler + `opencli-autofix` | Plan a synthetic adapter repair without execution | Pass after safety-gate projection | The rendered packet is `general_task`, keeps AUTH/BROWSER hard stops, adapter-only scope, retry and issue-approval boundaries, and does not interpret `BROWSER_CONNECT` as UI work. |

## Regression found and corrected

The first and third probes initially activated `frontend_implementation` from
the word stem in “before any implementation” or “stop before implementing
fixes.” That contradicted the requested pre-action boundary. The route scorer
now ignores an objective term when every occurrence is explicitly pre-action
(`before`, `without`, `not`, `never`, or `no`), with a regression test covering
the two phrases. An affirmative occurrence still activates the matching route.

A later read-only `write-docs` probe showed that “implementation evidence” in a
documentation objective still activated frontend behavior through the generic
`implement` stem. The frontend route no longer treats that stem as sufficient
evidence; the explicit React-components control remains in the deterministic
contract. This is a routing correction, not a claim about documentation quality.

The `refactor-clean` source exposed a separate projection gap: “verify behavior
through consumers” was reduced to generic test guidance. When a selected source
contains owner, consumer, and verification language, its packet now carries a
consumer-surface verification gate. This preserves a source invariant locally;
it does not establish that a refactor outcome is better.

The `wizard` source then exposed a safety projection gap: its irreversible-action
confirmation and static-only verification rules did not reach the composed
packet. The confirmation rule used inline Markdown around `confirm`, so a
literal extractor missed it. TMCP now normalizes presentation formatting before
matching that rule and retains both safeguards. This proves only that TMCP
projects the source safeguards; it does not authorize secret handling, external
setup, or a behavioral safety claim.

The `fold-feature-branches` source exposed a destructive-workflow projection gap:
TMCP cited the skill but reduced its remote-truth, patch-equivalence, and
dirty-worktree rules to generic tests. The packet now projects those concrete
preservation and proof gates. This was a read-only, synthetic source probe; it
did not fetch, merge, delete, or modify a branch and says nothing about an
integration outcome.

The `opencli-autofix` source exposed a broader delivery defect. Its hard stops
were present only in the JSON field, not in the rendered packet, while
`BROWSER_CONNECT` also activated irrelevant UI checks and incidental `return`
mentions filled the output contract. TMCP now renders stop conditions, treats
that diagnostic code as non-UI, extracts only imperative output contracts, and
projects the repair scope, retry, and filing-approval rules. This was a
synthetic, no-execution probe: no OpenCLI command, adapter edit, browser action,
or GitHub issue occurred.

## Interpretation

This is a necessary early gate for combination testing. A future blind campaign
must still use reviewed golden cases and separate runner/judge sessions to test
whether a composed packet changes an agent's actual work.
