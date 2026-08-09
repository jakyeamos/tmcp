# Behavioral-atoms semantic preflight v0.3

Status: structurally valid preflight package, scoped to research-contract
validation. This artifact does not implement atoms, a registry, a compiler, an
evaluator, composition, routing, receipts, admission, telemetry, provider
execution, or cross-skill composition support.

## Base and provenance

- Repository: 'jakyeamos/tmcp'
- Exact base: '3c9b2fe8cc0fe72ed947c447e4ea549094d810c3'
- Intake state: detached HEAD at source branch 'main'
- Machine-readable contract:
  'docs/experiments/behavioral-atoms-semantic-preflight-v0.3.json'
- Conceptual schema:
  'schemas/tmcp-behavioral-atoms-semantic-preflight-v0.3.schema.json'
- Held-out fixture artifact:
  'tests/fixtures/behavioral-atoms-held-out-v0.3.json'

The source evidence was read from the committed family skills at the exact
base. Their SHA-256 values are recorded in the machine-readable family
signatures and atom catalog:

- 'skills/tmcp-data-integrity-audit/SKILL.md'
- 'skills/tmcp-security-privacy-audit/SKILL.md'
- 'skills/tmcp-release-readiness/SKILL.md'
- 'skills/tmcp-migration-readiness/SKILL.md'

The coordinator handoff at semantic-preflight v0.2 was read. Its two legacy
files were hash-verified and are negative experimental evidence only:

- 'BEHAVIORAL_ATOMS_PILOT_EXECUTION_V0.1.md':
  'b13b9c0c507745db1e685da36c00b5a2374bf5bd9788338232acc4362e11176d'
- 'behavioral-atoms-pilot-preflight-v0.1.json':
  '7b11daf555228e4a274e36275c6fe25649900295bad97717120bb23bd1ab0c61'

No uncommitted v0.1 registry or compiler implementation was copied or
reconstructed.

## Contract boundary

The conceptual typed-atom contract requires every atom to carry:

1. stable identity and version;
2. domain semantics;
3. positive, negative, and ambiguous applicability with a fail-closed
   ambiguous action;
4. dependencies and conflicts;
5. required inputs and reads;
6. evidence and verification obligations;
7. stop conditions;
8. provenance and trust;
9. a rendering boundary; and
10. a local estimated-token cost that is not provider telemetry.

The generic process shell is deliberately separate. It covers reading declared
sources, capturing evidence, verifying obligations, and stopping on missing
evidence. Its machine-readable contract states that it cannot satisfy domain
obligations by itself. The four signatures each require domain-specific atoms,
inputs, evidence, outputs, and verification.

## Four family signatures

| Family | Domain target | Distinguishing risk | Required evidence/output |
| --- | --- | --- | --- |
| Data integrity | Correct schemas, pipelines, imports, backfills, and records | Loss, duplication, divergence, non-idempotent processing | Invariant map, reconciliation gaps, data-loss evidence, observable pre/post checks |
| Security/privacy | Secret, privacy, auth, and sensitive-evidence boundaries | Exposure, leakage, unauthorized access, unverified redaction | Redaction summary, authorized owner, bounded claims, output-boundary check |
| Release readiness | Ship/no-ship, launch blockers, quality ladder, handoff | Stale or partial release evidence mistaken for readiness | Current CI/test/build evidence, blocker dispositions, acceptance checks |
| Migration readiness | Sequenced transition, compatibility, cutover, rollback | Incompatibility, unsafe order, unowned backfill, irreversible recovery | Current/target map, affected surfaces, rollback owner/trigger, slice gates |

The signatures share one process-shell reference but have non-empty and
non-identical domain targets, risks, evidence obligations, outputs, and
verification obligations. The focused test fails if a generic process atom is
treated as a substitute for those domain obligations.

## Held-out applicability fixtures

The sealed fixture artifact contains 12 fixtures: one positive, one negative,
and one ambiguous fixture for each family. Every fixture has an explicit owner,
expected applicability outcome, decision, required obligations, and stop
behavior. All fixtures are marked held out and tuning-disabled.

The non-tuning boundary is explicit:

- fixture text, signals, labels, and expected outcomes are frozen before
  runtime or provider work;
- fixture outcomes cannot tune the contract or hypotheses;
- fixture text is not a provider prompt and labels are not provider evidence;
- any contract correction requires a new versioned fixture artifact.

## Transplant registry

Only domain-logic transplants with a committed source, target obligation, unique
source/target/domain-delta signature, and non-empty predicted delta are valid.

| ID | Source to target | Domain delta |
| --- | --- | --- |
| 'arm.valid.migration_receives_data_reconciliation' | Data integrity to migration readiness | Reconcile pre/post state at migration cutover and backfill |
| 'arm.valid.data_integrity_receives_migration_rollback' | Migration readiness to data integrity | Bound recovery when reconciliation finds a mismatch |
| 'arm.valid.release_receives_security_redaction' | Security/privacy to release readiness | Add artifact redaction and secret boundary to release evidence |
| 'arm.valid.security_privacy_receives_release_gating' | Release readiness to security/privacy | Require current release gate evidence for review completion |

The four historical v0.1 shapes remain in the registry as invalid, with
machine-readable reasons:

- duplicate generic 'local-context-first' condition;
- duplicate generic 'ordered-next-actions' condition;
- security to release with no eligible variant because the selections were
  atom-identical six-atom supersets;
- release to security with no eligible variant for the same reason.

These rejected shapes preserve the stopped-pilot evidence; they are not
replayable arms.

## Preregistered interaction hypotheses

The package contains only three hypotheses selected from domain logic:

- reconciliation plus rollback;
- redaction plus ship gate; and
- secret boundary plus evidence ladder.

Each hypothesis names its families and typed atoms, predicted direction,
mechanism, falsifier, and a held-out fixture boundary. The selection policy
explicitly disallows lexical enumeration or exhaustive pair generation.
No hypothesis has provider outcomes or causal support in this iteration.

## Validation and stop conditions

The validation gate is fail closed. Any schema, JSON, fixture,
family-distinguishability, generic-sufficiency, transplant, hypothesis, or
compatibility failure blocks runtime implementation and provider cells.

The package records dispositions for all in-scope gates, including:

- structural checks and the complete repository suite;
- runtime implementation, which is not run because it is excluded;
- provider cells, which are not run;
- cross-skill composition, which remains blocked and unclaimed; and
- whitespace validation.

The package is structurally valid only after the focused gate, JSON validation,
complete repository suite, and 'git diff --check' have passed. Those results
are recorded in the machine-readable validation gate and the handoff artifact
after execution.

Executed validation:

- Focused preflight gate: 8 tests passed.
- JSON parsing: all four added JSON artifacts passed Python 'json.tool'.
- Complete repository suite: 454 tests passed, 3 skipped, in an isolated
  TMCP home.
- Ruff format and lint: passed.
- Basedpyright: passed with 0 errors, warnings, or notes.
- Node launcher syntax, contract, and install checks: passed.
- Whitespace: tracked-tree 'git diff --check' passed; every untracked added
  file also passed 'git diff --no-index --check'.

The environment has no Python 'jsonschema' package or Node 'ajv' module. No
dependency was installed or added: the checked-in JSON Schema artifacts,
Python JSON parsing, and focused stdlib structural gate are the repository
validation boundary for this preflight. Full runtime/provider validation
remains outside scope.

## Compatibility risk

This is an additive research-contract package. No existing public runtime
schema, tool registry, compiler, evaluator, routing, or receipt schema changes.
The documented risks are that a future consumer could mistake this artifact for
an executable schema, reuse its identities without preserving their typed
fields, or overread held-out labels as provider evidence. The package mitigates
those risks with a new schema ID, explicit preflight-only status, forbidden
rendering targets, and a required new version before any runtime reference.
