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
| TMCP compiler + `refactor-clean` | Remove an obsolete owner and verify consumers | Selection-only | The refactor source is cited with its preservation and verification atoms; its richer ownership rule still needs blind behavioral fixtures. |
| TMCP compiler + `repo-behavior-spec-loop` | Audit a canonical evidence ledger; stop before fixes | Pass after route fix | The packet is `general_task`, requires `references/loop.md`, retains the canonical-ledger instruction, output contract, audit checkpoints, and test gates. |
| TMCP compiler + `write-docs` | Draft source-grounded documentation that cites implementation evidence | Pass after route fix | The packet is `general_task`, cites the documentation source, and does not activate frontend behavior from the generic implementation stem. |

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

## Interpretation

This is a necessary early gate for combination testing. A future blind campaign
must still use reviewed golden cases and separate runner/judge sessions to test
whether a composed packet changes an agent's actual work.
