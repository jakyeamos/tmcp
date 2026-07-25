# TMCP Skill Writing Guidebook

Experimental v0.1 seed for skill evaluation outputs. Generated reports may update
`docs/SKILL_PATTERN_CATALOG.json` and this guidebook with evidence levels.

## 1. Skill activation patterns

Prefer narrow trigger descriptions tied to task evidence. Avoid frontmatter that
matches any task class.

## 2. Verification gate patterns

Prefer concrete commands with pass/fail reporting. Avoid vague quality language
such as "make sure everything works."

## 3. Evidence levels and confidence

Label every pattern claim with an evidence level:

- `hypothesis` — plausible, not tested
- `static_review` — rubric or lint review only
- `dogfooded` — seen in TMCP usage
- `controlled_single_agent_eval` — A/B tested on one agent/host
- `controlled_multi_agent_eval` — tested across agents or hosts
- `production_reinforced` — repeated real-world traces
- `deprecated` — previously recommended but contradicted

## 4. Harvest feedback boundary

Evaluation may propose harvest warnings. It must not auto-promote or silently
rewrite durable routing state.

## 5. Full-corpus dogfood gate

The available fixture corpus is now exercised as one provenance-aware gate, not
only as isolated composition examples. Run it from the repository root:

```bash
python3 scripts/validate_skill_fixture_corpus.py \
  --manifest tests/fixtures/skill-fixtures/full-corpus-v0.1.json \
  --project-root . \
  --artifact-root /private/tmp
```

The checked-in baseline is
`tests/fixtures/skill-fixtures/full-corpus-baseline-v0.1.json`. It covers eight
single-skill families and 42 available runner artifacts at `gpt-5.5` with low
reasoning. The structural validator passes 31/42, the independent judge passes
31/42, and the two agree on 42/42 runs. Every run can point to a specific judge
record; the gate records that judge file's SHA-256 and record index so a copied
boolean cannot silently drift from its source.

This is a readiness gate for the fixture/evaluator apparatus, not a claim that
all skills are good. The 11 failures are behavior signals: the ambiguous
approval prompt remains a no-target failure, required-read and precedence
controls expose original-version gaps, and the candidate versions pass the
tested explicit controls. Untyped variants remain outside the gate until their
evidence scope is explicit; keep those exclusions visible rather than weakening
the bar or treating structural agreement as causal proof.

## 6. Neutral evidence and discovered-corpus coverage

Neutral artifacts are now admitted through
`tests/fixtures/skill-fixtures/neutral-corpus-v0.1.json`. The validator can
scope exact values and disclosure patterns to the complete artifact while still
requiring a final-response readiness statement. This matches the judge's bar
for evidence distributed across `observations`, `actions`, and a structured
`final_response`: the original control is 0/3, the first candidate is 2/3, and
the corrected candidate variant is 3/3, with 9/9 structural–judge agreement.

Coverage of the discovered corpus is a separate gate. Audit a scaffolded
manifest with:

```bash
python3 scripts/audit_skill_fixture_coverage.py \
  /path/to/fixture-set/manifest.json
```

The recorded [coverage baseline](/private/tmp/tmcp-skill-fixtures-20260722/tests/fixtures/skill-fixtures/corpus-coverage-baseline-v0.1.json)
finds 158 discovered skills but only 1 ready skill and 1 golden case in the
full discovery manifest; 157 still need a case and bar. The later calibrated
subset contains 7 skills and 8 cases. That gap is an explicit promotion stop,
not missing evidence to be inferred from static rewrites.

## 7. Mine real task shapes before admitting a new skill case

When a skill has no golden case, mine a completed, provenance-preserving task
source before writing a fixture. Record the source campaign/objective, selected
runner artifact, independent judge handoff, source hashes, and the evidence
boundary. Derive the bar from the skill's output contract and the independent
judge dimensions; do not copy an expected answer into the runner prompt.

The mined TMCP tranche is recorded in
`tests/fixtures/skill-fixtures/mined-corpus-v0.1.json` and its three-repeat
subscription baseline in
`tests/fixtures/skill-fixtures/mined-corpus-baseline-v0.1.json`. It covers four
TMCP plugin skills with 24 blind runner cells and 24 independent judge cells at
`gpt-5.5` low reasoning. Both variants passed the no-fabrication bars, but the
candidate hashes were identical because static review produced no proposals.
Therefore the score movement is a behavior baseline and variance signal, not
rewrite lift. Keep the automatic rewrite gate closed until a later mined case
has a real, reviewable candidate delta and repeats it without regression.

The reusable campaign command is:

```bash
PYTHONPATH=. python3 scripts/run_mined_skill_fixture_campaign.py \
  /path/to/mined-manifest.json \
  --output-dir /private/tmp/tmcp-mined-campaign \
  --repeats 3 --model gpt-5.5 --reasoning-effort low
```

## 8. Individual corpus audit and failure linkage

The per-skill registry is
`tests/fixtures/skill-fixtures/individual-skill-audit-v0.1.json`. It covers
156 unique skills and preserves each source hash, warning, proposed change,
definition-of-done status, and next fixture shape. The current static inventory
contains 134 warnings across 100 skills; 56 skills have no static finding.

The registry deliberately records `observed_failure_status` as
`not_established` for every entry. A static finding such as a broad trigger,
buried required read, or missing output contract is a failure hypothesis—not a
runtime failure. The registry also does not infer that a definition of done is
present or absent. It marks only the narrower case where the static audit found
no observable output contract, then requires a concrete case and independent
judge to establish behavior.

Rebuild the registry after refreshing the source audit:

```bash
python3 scripts/build_individual_skill_audit.py \
  /path/to/audit.json \
  --output tests/fixtures/skill-fixtures/individual-skill-audit-v0.1.json
```

Use each entry's `recommended_next_case` to admit targeted tests. Only after a
case produces a repeatable failure should a proposal be treated as a targeted
skill improvement candidate.
