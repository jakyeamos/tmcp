# Candidate skill campaign queue

Every target below needs reviewed, concrete golden cases and a defensible bar
before a live behavioral campaign. The order favors different kinds of
reusable behavior over a large run of closely related authoring skills.

| Priority | Target | Behavioral strength to test | Fixture caution |
| ---: | --- | --- | --- |
| 1 | `/Users/jakyeamos/skills/authoring/eval-skills/SKILL.md` | Blind evaluation, defect-vs-bar diagnosis, full re-evaluation | The preregistered 36-cell baseline is ready; do not replace its reviewed inputs. |
| 2 | `/Users/jakyeamos/skills/engineering/explore-unknowns/SKILL.md` | Staged user checkpoints and correct handoff | Use an ambiguous task with a real boundary; do not reward inventing unknowns. |
| 3 | `/Users/jakyeamos/skills/engineering/refactor-clean/SKILL.md` | One owner, stale-path removal, consumer verification | Supply a small real dependency graph and distinguish cleanup from a behavior change. |
| 4 | `/Users/jakyeamos/skills/engineering/write-docs/SKILL.md` | Source-grounded documentation without code transcription | Provide a real source tree and an audience/outcome bar, not a fixed prose template. |
| 5 | `/Users/jakyeamos/.agents/skills/repo-behavior-spec-loop/SKILL.md` | Canonical evidence state, source citations, audit checkpoints | Separate audit-only fixtures from fixtures that explicitly permit remediation. |
| 6 | `/Users/jakyeamos/.agents/skills/wizard/SKILL.md` | Deterministic human handoff with secret/irreversibility safety | Use synthetic credentials and a no-write dry path; never use a live secret or external account. |

## First composition campaigns

1. TMCP compiler + `explore-unknowns`: preserve staged user checkpoints and do
   not route an ambiguity walk into implementation.
2. TMCP compiler + `refactor-clean`: preserve ownership, deletion, and
   consumer-verification gates through a concrete refactor.
3. TMCP compiler + `repo-behavior-spec-loop`: preserve the single-writer
   evidence contract and activate only task-implied audit gates.

Each pair first clears a packet-level composition probe, then receives a
separate reviewed behavioral fixture set. Results may be compared across pairs,
but no pair is promoted to a corpus default from static or packet-level evidence.
