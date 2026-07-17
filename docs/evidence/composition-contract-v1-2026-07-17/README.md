# Composition contract v1 — deterministic baseline

This evidence unit tests TMCP's deterministic compiler boundary before any
agent-behavior composition campaign. It is not a causal claim, a skill-quality
score, or a guidebook promotion candidate.

## Preregistered matrix

The canonical fixture matrix is
`tests/fixtures/composition-contract-v1.json`. It has three cases:

| Case | Contract |
| --- | --- |
| `research_goal_is_not_frontend` | A research/guidebook objective with a generic "build" verb remains `general_task`; it does not activate frontend behavior. |
| `explicit_frontend_control_remains_routed` | Explicit React components plus animation still activate frontend and motion routes. |
| `test_fixture_is_evidence_only` | A project-root `tests/fixtures/**/SKILL.md` source is retained as test evidence but cannot become a citation, active instruction, or declared read in a live packet. |

The first local composition probe exposed the two failure modes this matrix
captures: the research objective selected `frontend_implementation` from the
generic word "build", and an approval fixture appeared in the active packet.
That observation was recorded as an advisory failed receipt. The fixture matrix
turns it into a deterministic regression contract without relabeling it as a
model result.

## Local verification

After the contract change, the same project-root objective compiled as
`general_task` with no active routes, test-fixture citations, test-fixture
instructions, or test-fixture required reads. The filtered compiler output and
its advisory receipt identity are retained in
[`local-verification.json`](local-verification.json). This is a local compiler
verification, not a blind behavioral evaluation.

## Evidence boundary

Passing this matrix proves only that TMCP's route and source-role projection
holds for these exact compiler inputs. It does not prove that a pair or sequence
of skills improves an agent's artifact. A future behavioral composition campaign
must first preregister task inputs, bars, source-role expectations, runner/judge
isolation, repetitions, and an independent rejudge where cost or safety matters.

Until such a campaign replicates, this unit contributes an operational default:
test fixtures are evidence-only during project-root composition, and generic
verbs are not enough to activate a specialized route.

## Next evidence gate

Run a fresh, blind multi-model study using this clean compiler contract. Its
control should be the same task with no specialized skill pair; its intervention
should supply one compatible, source-role-validated pair. Score task outcome,
source selection, conflict handling, cost, and safety separately. Do not promote
the pair or a wording rule unless the preregistered reliability and causal gates
both clear.
