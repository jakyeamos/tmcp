# `eval-skills` Workflow-section dogfood

## Conclusion

TMCP's split-skill evaluator produced a real behavioral distinction in this pilot.
Across two fixture families and two repetitions per cell, the intact skill passed
4/4 blind judgments and the exact `## Workflow` ablation passed 0/4. The scorer
recognized the matched section contrast, calculated an intervention-control lift of
`-1.0` with a 95% interval of `[-1.0, -0.02]`, and assigned
`controlled_single_agent_eval`.

That result supports an internal section-level candidate. It does not justify a
corpus-wide “tried and true” label. TMCP correctly held promotion because the run had
only two fixtures, two families, one agent configuration, and one safety label.

## Experiment

- Experiment ID: `skill-eval-af3806a4873b77a0`
- Target: `/Users/jakyeamos/skills/authoring/eval-skills/SKILL.md`
- Target digest:
  `sha256:2e9bf333.71fce396.b434f9f3.4d4b87cd.4761626c.30cc1f4f.64df55c7.26696074`
- Pattern: `evaluation.staged-workflow-section`
- Tested atom: `staged_evaluation_workflow`
- Control: complete original skill
- Intervention: exact deletion of the single `## Workflow` section
- Configuration: `codex-gpt5-desktop-20260717`
- Protocol: fresh context-free runner and separate fresh judge for every trace
- Matrix: 2 fixtures × 2 conditions × 2 repetitions = 8 judged traces

| Fixture family | Original | Workflow ablated |
|---|---:|---:|
| `execution_protocol` | 2/2 | 0/2 |
| `claim_calibration` | 2/2 | 0/2 |
| Total | 4/4 | 0/4 |

## What the command got right

- Stable experiment, row, fixture, skill, contrast, and replicate identities were
  validated on score import.
- The intervention was re-derived and checked as an exact one-section deletion.
- Only traces with blind-runner, blind-judge, isolated-session, evidence-bearing
  verdicts entered the controlled claim.
- The effect used paired condition outcomes rather than self-reported success text.
- The evidence tier matched the actual one-configuration coverage.
- The promotion gate stayed closed and reported the missing fixtures, families,
  configurations, and safety condition.
- Static anti-pattern findings remained suspected rather than becoming behavioral
  recommendations.

## Dogfood findings

The first generated report exposed an interpretation problem: generic activation and
adherence heuristics appeared beside the causal pattern claim without a boundary, and
the guidebook showed a raw negative lift without explaining that negative was the
support direction. Commits `222a3ae` and `3ab7510` now mark those scorecard dimensions
diagnostic-only and render the signed effect, interval, and promotion gaps explicitly.

One ablated artifact reconstructed much of the missing workflow from duplicated rules
elsewhere in the skill, but still failed its blind judgment. This is evidence that the
section has a measurable effect and a warning that duplicated instructions make
section experiments less clean. The duplication warning is not itself a controlled
anti-pattern claim.

One judge marked unqualified cleanup of live-checkout mutations as a safety regression.
The wording was not the intervention target and other judges did not label it
consistently. The scorer conservatively blocked promotion; a dedicated safety contrast
is required before drawing a causal conclusion.

The checked-in trace observations are normalized coordinator transcriptions of the
runner artifacts, paired with the blind judges' criterion evidence. The runner and
judge roles were genuinely separated, but future campaigns should persist raw agent
messages automatically to remove this transcription step.

## Artifacts

- [`traces.json`](traces.json) — eight judged trace records
- [`tmcp-skill-evaluation-plan.json`](generated/tmcp-skill-evaluation-plan.json) —
  immutable plan and exact skill attachments
- [`tmcp-skill-evaluation-report.json`](generated/tmcp-skill-evaluation-report.json) —
  scored report and promotion decision
- [`skill-writing-guidebook.md`](generated/skill-writing-guidebook.md) — generated
  evidence projection
- [`skill-pattern-catalog.json`](generated/skill-pattern-catalog.json) — generated
  machine-readable catalog

## Reproduce the score

From the repository root:

```bash
node scripts/tmcp_launcher.mjs evaluate-skills \
  --mode score \
  --evaluation-plan docs/evidence/skill-eval-dogfood-2026-07-17/generated/tmcp-skill-evaluation-plan.json \
  --run-evidence-json "$(jq -c . docs/evidence/skill-eval-dogfood-2026-07-17/traces.json)" \
  --write-artifacts \
  --output-dir /tmp/tmcp-eval-skill-dogfood-replay
```
