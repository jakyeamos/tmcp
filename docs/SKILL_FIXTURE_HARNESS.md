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

Generate review-only bundles from TMCP's static findings and guidebook rewrite
variant:

```bash
PYTHONPATH=. python3 scripts/generate_skill_fixture_proposals.py \
  /private/tmp/tmcp-skill-fixtures/run-20260722/manifest.json \
  --output-dir /private/tmp/tmcp-skill-fixtures/run-20260722/proposals-review
```

Generation never marks a proposal approved. Review each bundle, change only
the intended entries to `status: "approved"`, then run the apply command.

Apply reviewed proposal bundles explicitly; the original copy is never
modified, and only proposals with `status: "approved"` are applied:

```bash
python3 scripts/apply_skill_fixture_proposals.py \
  /private/tmp/tmcp-skill-fixtures/run-20260722/manifest.json \
  --proposals-dir /path/to/reviewed-proposals \
  --all
```

For the pre-review experiment, apply all `proposed` entries to the disposable
candidate and label the run experimental:

```bash
python3 scripts/apply_skill_fixture_proposals.py \
  /private/tmp/tmcp-skill-fixtures/run-20260722/manifest.json \
  --proposals-dir /private/tmp/tmcp-skill-fixtures/run-20260722/proposals-review \
  --all --include-proposed
```

This is the correct path for establishing the original-vs-proposal numeric
baseline. It does not approve or promote any rewrite.

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

For subscription-backed Codex runs, pass the prompt through stdin with the
shell-safe wrapper. This preserves literal backticks, substitutions, and other
fixture text while recording runner provenance:

```bash
python3 scripts/run_skill_fixture_codex.py \
  --prompt-file /path/to/blind-prompt.txt \
  --output-last-message /path/to/trace.txt \
  --cwd /private/tmp/isolated-run \
  --model gpt-5.5 \
  --reasoning-effort low \
  --sandbox read-only
```

The wrapper uses `subprocess.run(..., shell=False)`, so prompt content never
becomes shell syntax. Its JSON report includes the prompt digest, model,
reasoning effort, sandbox, exit code, session id when available, and an explicit
`shell_interpolation: false` provenance field. The Codex runner sees only the
prompt; bars remain judge-only inputs.

After editing a candidate copy, record its new digest before validation:

```bash
python3 scripts/record_skill_fixture_candidate.py \
  /private/tmp/tmcp-skill-fixtures/run-20260722/manifest.json \
  --skill-id fixture__approval-before-edit
```

Scaffolding refuses to replace an existing run unless `--force` is supplied.
