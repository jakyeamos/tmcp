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

The first source-bound admission pass is recorded in
`tests/fixtures/skill-fixtures/individual-skill-admission-v0.1.json`. It found
five source examples with line-level provenance (`last30days`, `find-skills`,
`nlm-skill`, `skill-creator`, and `gsd-reapply-patches`), but none is runnable
yet because each lacks an execution boundary such as engine output, a live
search result, authenticated state, an attached file, or patch contents. The
other 151 skills still need a real golden case and bar. This distinction is
intentional: source provenance alone does not admit a behavioral case.

Rebuild and validate the queue with:

```bash
python3 scripts/build_individual_skill_admission.py \
  tests/fixtures/skill-fixtures/individual-skill-audit-v0.1.json \
  tests/fixtures/skill-fixtures/individual-skill-admission-cases-v0.1.json \
  --output tests/fixtures/skill-fixtures/individual-skill-admission-v0.1.json
```

This is an admission gate, not an evaluation result. A `case_ready` record is
eligible for a blind runner and independent judge; a
`needs_execution_boundary` record is not. A disposable five-skill campaign
confirmed why this matters: all 30 runner and 30 judge cells completed, but
the judges mostly saw refusal/no-op artifacts because the required external
inputs were absent. That is case-quality evidence, not five proven skill
failures, and it does not authorize rewrites.

### 9. Disposition campaign results before proposing a rewrite

Campaign completion is not the same as skill evidence. Record each completed
case in `individual-skill-behavior-dispositions-v0.1.json` with an explicit
classification, rationale, next action, original/candidate cell counts, and
independent-judge decisions. Use these dispositions:

- `case_boundary_blocked`: the golden case omitted an input, authenticated
  state, external result, or task target required by its own bar.
- `runner_boundary_blocked`: the case is complete, but the blind runner was
  not given the bounded repository/tool context needed to exercise it.
- `skill_failure`: only after a `case_ready` case has a repeatable independent
  judge failure with the required execution evidence.

The first six-case disposition pass completed 36 runner cells and 36 judge
cells with no harness failures. Five cases were `case_boundary_blocked`; the
read-only ownership case was initially `runner_boundary_blocked` because the
runner could not execute its scoped repository commands. After the runner
gained an explicit bounded read-only execution root, a second 6-runner/6-judge
rejudge passed all original and candidate cells for that case. Its final
disposition is `behavioral_baseline_pass` with `no_candidate_delta`: the
original and candidate hashes are identical, so this is a regression control,
not rewrite lift. The resulting summary is zero observed skill failures, one
behavioral baseline pass, and five rewrite holds.

The GSD case then received a disposable three-way fixture containing merge,
conflict, and incorporated files. Its first bounded 6-runner/6-judge campaign
was fixture evidence but not a skill result: the bar demanded
`preserved/changed/CONFLICT` labels while the source contract reports
`Merged/Conflict/Incorporated`, and the read-only boundary made actual writes
impossible. The case bar is now source-bound to those semantic labels and
requires explicit no-write reporting. Subsequent subscription reruns did not
produce a complete report, so the GSD disposition remains
`case_boundary_blocked`/`hold`; no skill failure or rewrite lift is claimed.
The timeout-guarded runner records slow or interrupted Codex cells as runner
boundary evidence instead of allowing an incomplete campaign to look like a
behavioral result.

Rebuild the disposition artifact with:

```bash
python3 scripts/build_skill_behavior_dispositions.py \
  tests/fixtures/skill-fixtures/individual-skill-admission-v0.1.json \
  tests/fixtures/skill-fixtures/individual-skill-behavior-disposition-input-v0.1.json \
  --campaign /private/tmp/tmcp-individual-admission-campaign-20260725/campaign-report.json \
  --campaign /private/tmp/tmcp-check-thread-campaign-v3-20260725/campaign-report.json \
  --campaign /private/tmp/tmcp-gsd-campaign-v2-20260725/campaign-report.json \
  --output tests/fixtures/skill-fixtures/individual-skill-behavior-dispositions-v0.1.json
```
