# Skill fixture harness

The fixture harness creates isolated version slots for every discovered
`SKILL.md` without silently inventing evaluation cases or quality bars.

```bash
python3 scripts/scaffold_skill_fixtures.py \
  --root "$HOME/.agents/skills" \
  --root "$HOME/.codex/skills" \
  --root "$HOME/skills" \
  --extra-skill tests/fixtures/skills/approval-before-edit/SKILL.md \
  --seed-cases tests/fixtures/skill-fixtures/seed-cases-v0.1.json \
  --output-dir /private/tmp/tmcp-skill-fixtures/run-20260722

python3 scripts/validate_skill_fixtures.py \
  /private/tmp/tmcp-skill-fixtures/run-20260722/manifest.json
```

Apply reviewed proposal bundles explicitly; the original copy is never
modified, and only proposals with `status: "approved"` are applied:

```bash
python3 scripts/apply_skill_fixture_proposals.py \
  /private/tmp/tmcp-skill-fixtures/run-20260722/manifest.json \
  --proposals-dir /path/to/reviewed-proposals \
  --all
```

Each `<skill_id>.json` bundle is hash-chained: every proposal names its
reason, target, review status, exact preceding-content hash, and replacement
hash. Proposed or rejected entries remain recorded as skipped. A candidate
that already contains an unrecorded edit is refused unless
`--replace-candidate` is supplied explicitly.

Each skill receives four version slots:

- `original`: an exact digest-bound snapshot of the source skill;
- `candidate`: an editable copy whose lineage still points to the original;
- `baseline`: selection omitted, with no target skill body;
- `negative_control`: selection replaced by a non-operative marker.

Only skills with a concrete golden case and an explicit judgment/conformance bar
are marked `ready`. All others are `needs_golden_case_and_bar`, and preparation
fails closed rather than guessing what good looks like.

Prepare no-call plans for a ready skill:

```bash
PYTHONPATH=. python3 scripts/prepare_skill_fixture_eval.py \
  /private/tmp/tmcp-skill-fixtures/run-20260722/manifest.json \
  --skill-id fixture__approval-before-edit \
  --output-dir /private/tmp/tmcp-skill-fixtures/run-20260722/plans
```

The resulting plans are inputs to the blind runner. The case bar stays outside
the runner input and is supplied only to a separate judge. Candidate edits are
never auto-applied; they must be evaluated across all cases and compared with
the original version before promotion.

After editing a candidate copy, record its new digest before validation:

```bash
python3 scripts/record_skill_fixture_candidate.py \
  /private/tmp/tmcp-skill-fixtures/run-20260722/manifest.json \
  --skill-id fixture__approval-before-edit
```

Scaffolding refuses to replace an existing run unless `--force` is supplied.
