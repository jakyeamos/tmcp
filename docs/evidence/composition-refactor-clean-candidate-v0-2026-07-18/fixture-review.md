# Independent fixture review record

Status: **pending**.

This file is intentionally empty of a review verdict. The author who drafted
the fixture must not self-certify its directness or bar fairness.

Before a behavioral-study plan is generated, a fresh reviewer must inspect:

- `README.md`
- `first-principles.md`
- `fixtures/refactor-clean-dependency-graph-v0.json`

Record one decision:

| Decision | Reviewer evidence required | Consequence |
| --- | --- | --- |
| `approved` | Directness, first-principles expressibility, judgment-level bar, real failure smells, and no-tool safety all supported with fixture-specific reasoning. | A new, separately preregistered study may use this fixture. |
| `revise` | Identify the exact prompt, bar, or safety defect. | Amend the candidate, then obtain a new independent review. |
| `rejected` | Explain why the fixture cannot fairly test the source. | Do not convert it into a study. |

No decision may claim a behavioral effect, approve a model call, or promote the
pair or guidebook.
