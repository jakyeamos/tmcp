# Behavioral-atoms runtime implementation decision v0.4

Status: implementation decision only. This packet is implementation-ready but
does not implement a registry, compiler, resolver, renderer, evaluator,
composition path, receipt change, provider cell, or public contract change.

## Decision

Use an internal/additive compatibility projection.

The future internal contract is:

- schema: `tmcp-behavioral-atom-runtime-v0.4`
- semantic version: `0.4.0`
- runtime public version: unchanged at `0.5.7`

The typed compiler must run and fail closed before any typed atom is projected
into an existing packet or receipt. The first vertical slice projects only
fields already represented by the current public contracts: string atom ids,
instructions, reads, gates, stops, citations, conflicts, and receipt string
fields. It does not add a public field, tool, input, output schema, or version.

A new public version is deliberately not selected. The current public packet
and receipt surfaces can carry a compatibility projection, while the typed
contract, source provenance, and compiler trace stay internal. Public version
expansion must wait for runtime behavior, evaluator validity, provider
preflight, and any later composition evidence.

## Exact base and intake

- Repository: `jakyeamos/tmcp`
- Git base commit: 3c9b2fe8cc0fe72ed947c447e4ea549094d810c3
- Intake state: detached HEAD at source branch `main`
- Authorized handoff:
  `/Users/jakyeamos/.codex/visualizations/2026/08/04/019fcab1-eb42-7d20-b6da-e6ec032b9cee/handoffs/behavioral-atoms-preflight-v0.3/HANDOFF.md`
- Authorized manifest:
  `/Users/jakyeamos/.codex/visualizations/2026/08/04/019fcab1-eb42-7d20-b6da-e6ec032b9cee/handoffs/behavioral-atoms-preflight-v0.3/manifest.json`
- Source snapshot: `/Users/jakyeamos/.codex/worktrees/2581/tmcp`

Only the six manifest-listed files were replayed. Their source and destination
SHA-256 values were compared byte-for-byte before this decision was written:

| Repository-relative path | SHA-256 |
| --- | --- |
| `docs/experiments/BEHAVIORAL_ATOMS_SEMANTIC_PREFLIGHT_V0.3.md` | sha256 digest: edd6443bd02e255b002a479bfd2f2a67e59dbb64c52aece467701674ce1d28e5 |
| `docs/experiments/behavioral-atoms-semantic-preflight-v0.3.json` | sha256 digest: 5bc28d734e9b5903d55b166cb4a1e124c9f740e2a2ac9da8e306d88bfd65857e |
| `schemas/tmcp-behavioral-atoms-held-out-fixtures-v0.3.schema.json` | sha256 digest: 6b8df833b14b44416ce151674e4bac334e798b2e0ffa2645627606c8796a30f9 |
| `schemas/tmcp-behavioral-atoms-semantic-preflight-v0.3.schema.json` | sha256 digest: abecbd424720733af8028d214b34314f1f0aab280abb5ecd8187103ceac3f86f |
| `tests/fixtures/behavioral-atoms-held-out-v0.3.json` | sha256 digest: 172c761fcc5fb8f4814a2e9783b5322ad724b81ebec3ac0c74a1c03e9f9c652f |
| `tests/test_tmcp_behavioral_atoms_preflight.py` | sha256 digest: 66dc471e51c312ee0826284ac248f336eafc3f8ca696fbe79d63c6e043e5c254 |

The handoff sha256 digest: 98a1dba6f485f3e624b056a891f3d414fcd820381a27878fc301fa6ff4ba89e0
The manifest sha256 digest: e7ae355b48b1cf53bd0fceeb77385eb9ec5916e73c960f4209e80649892c18bd.
Legacy v0.1 files were not copied or reconstructed; their evidence remains
negative research evidence only.

## What the current runtime actually owns

The implementation decision is grounded in the committed owners at the exact
base:

| Concern | Current owner and observed behavior | v0.4 disposition |
| --- | --- | --- |
| Harvest/classification | `tmcp_runtime/domain/harvest_nodes.py` (`classify_atoms`, `source_node_from_text`, `node_signal_text`) performs bounded lexical string classification and marks harvested material untrusted. | Keep it unchanged. A word match may nominate context but can never admit a typed domain atom. |
| Harvest service | `tmcp_runtime/services/harvest.py` redacts files, builds source nodes, and emits the standalone harvest result. | Keep it unchanged; source-semantic extraction is a later decision. |
| Workflow activation | `tmcp_runtime/domain/workflow_activation.py` selects catalog workflows from objective/family signals and emits workflow instructions/atoms. | Keep workflow activation separate; it cannot rewrite atom semantics or override a compiler stop. |
| Workflow catalog/routes | `tmcp_runtime/domain/workflow_catalog.py` and `tmcp_runtime/domain/routes.py` own stable workflow ids, route identity, thresholds, phase, and ordering. | Supply phase/task context only; workflow or route labels are not domain evidence. |
| Reads/composition | `tmcp_runtime/domain/declared_loads.py` and `tmcp_runtime/domain/composition.py` resolve declared reads and rank nodes with deterministic lexical/context rules. | Use explicit semantic context for typed admission; preserve lexical behavior as the legacy path. |
| Packet model/rendering | `tmcp_runtime/domain/packets.py` and `tmcp_runtime/services/compose.py` own `tmcp-composed-packet-v0.1`, bounded string arrays, markdown rendering, citations, conflicts, and receipt templates. | Add only an internal projection adapter in the compose service; reuse the current builder and renderer. |
| Receipts | `tmcp_runtime/domain/receipts.py` and `tmcp_runtime/services/receipts.py` own `tmcp-run-receipt-v0.1`, string fields, advisory trust, redaction, and storage. | Project typed ids/stops/verification into existing strings; do not alter the schema or trust policy. |
| Evaluator variants | `tmcp_runtime/services/evaluation_catalog.py`, `evaluation_packets.py`, and `evaluation_scoring.py` own advisory variants and trace-based inclusion/adherence/cost scoring. | Add one internal typed-static advisory variant; never run a provider cell or auto-promote. |
| Public tools | `tmcp_runtime/api/registry.py` and `tmcp_runtime/api/tool_schemas.py` own runtime `0.5.7`, frozen tool definitions, and public schema ids. | No public tool, argument, output, or version change. |

## Boundary model

Four layers must remain distinct.

1. Domain atoms own semantic obligations: family target, risk, applicability,
   required inputs and reads, evidence and verification, phase, stops, trust,
   conflicts, dependencies, rendering targets, and local cost.

2. Generic process atoms own reusable mechanics such as reading required
   sources, capturing evidence, verifying an obligation, and stopping on
   missing evidence. They cannot satisfy a data, security, release, or
   migration obligation by themselves.

3. Workflows and routes own task identity, route selection, workflow
   activation, phase transition, and composition order. They may request typed
   atom ids, but cannot change an atom's semantic contract or override a
   reject/hold/stop.

4. Provenance labels own source identity, hashes, trust, redaction, and
   advisory/provider labels. A label is metadata, not an atom, predicate,
   dependency, or evidence substitute. Trust does not upgrade untrusted text.

## Proposed data flow

The future implementation follows this order:

1. **Durable source semantics.** Load the immutable v0.3 semantic contract,
   its source hashes, sealed fixture identity, and the explicit migration map.
   Do not use legacy v0.1 implementation material. A hash establishes identity
   only; it does not establish runtime behavior.

2. **Typed registry/model.** Create versioned records keyed by semantic id and
   version. Every v0.3 required field remains required: stable identity,
   domain semantics, positive/negative/ambiguous applicability, dependencies,
   conflicts, inputs, reads, evidence, verification, stops, provenance/trust,
   rendering boundary, and estimated local cost. Runtime v0.4 records carry
   explicit `supersedes` references to v0.3 records; v0.3 is not mutated.

3. **Applicability compilation.** Compile an explicit semantic context with
   objective, task identity, phase, inputs, allowed reads, evidence state, and
   source references. A positive result requires a domain-owned semantic signal
   and all required obligations. A negative result rejects the atom. An
   ambiguous result becomes `hold_for_evidence` and emits the missing-evidence
   stop. Literal trigger words are candidate hints only: a domain obligation
   can apply without its literal words when structured semantic context and
   owned evidence satisfy the contract.

4. **Dependency/conflict resolution.** Resolve dependencies before dependents
   with a deterministic topological order. A missing, rejected, ambiguous, or
   conflicting dependency blocks its dependent. Conflicts require an explicit
   typed resolution or a stop; lexical priority, workflow order, source order,
   and token budget are not conflict resolution.

5. **Deterministic rendering.** Produce an internal render record for one of
   three allowed targets: packet, receipt, or advisory evaluator trace. Order
   by dependency depth, required-before-optional, family, and full versioned id,
   with id as only the final tie-breaker. Provider prompts and provider outcomes
   are forbidden render targets.

6. **Token-budget selection.** Reserve required domain atoms and dependencies
   first. Select optional atoms by semantic obligation coverage and evidence
   utility, then deterministic id. A required set that exceeds the local
   estimate is a hold/stop, not truncation or generic substitution. The estimate
   is local planning data, not provider token telemetry or an economics claim.

7. **Packet projection.** Feed the existing packet builder its current string
   arrays, instructions, reads, gates, stops, citations, conflicts, and receipt
   template. Typed ids are projected only after compilation. If the typed path
   is absent, current legacy composition is unchanged. If a required typed id
   cannot fit the existing public cap, hold/stop rather than silently evicting
   legacy or required content.

8. **Receipt projection.** Use existing `tmcp-run-receipt-v0.1` string fields
   for activated/ignored ids and verification statements. Preserve
   `advisory_untrusted` trust and the existing override policy. A receipt
   records compiled/projected/verified state; it does not prove a provider
   outcome or causal effect.

9. **Advisory evaluation.** Feed the internal compiler trace, sealed fixtures,
   arm registry, and preregistered hypotheses into one typed-static advisory
   variant. It validates decisions and projections without provider execution,
   tuning, auto-promotion, economics, or cross-skill composition.

## Fail-closed rules

- Positive applicability admits only when semantic predicates, required inputs,
  allowed reads, and evidence are satisfied.
- Negative applicability rejects and emits no domain obligations.
- Ambiguous applicability holds for evidence and emits a stop. It cannot be
  made positive by a generic process atom, route label, or lexical match.
- Missing or contradictory phase is ambiguous/stop when the atom is required;
  incompatible phase rejects.
- Every required read must resolve to an allowed source reference. A path name,
  excerpt, or untrusted summary cannot substitute for a read.
- Evidence must be source-scoped and trust-allowed. Missing, stale,
  contradictory, or ownerless evidence is not inferred.
- Verification requires an observable result or an explicitly recorded
  not-run state. A plan or hash is not a successful verification by itself.
- A required stop survives rendering and budget selection and is projected to
  current packet gates/stops and receipt verification fields.
- Harvested text, provider output, legacy strings, and third-party context are
  untrusted inputs. They cannot upgrade applicability or provenance.
- Required atoms and dependencies exceeding the local budget hold/stop. No
  required obligation is truncated or replaced.

## Legacy and public compatibility

Legacy strings remain available through the current compatibility path. For
internal bookkeeping only, the future compiler may normalize an exact original
UTF-8 string as `legacy.string.<first-16-hex-sha256>`, while preserving the
original string for output. Legacy records are generic/process-only and cannot
satisfy a typed domain atom, dependency, evidence obligation, verification
obligation, or conflict resolution. Typed and legacy namespaces are never
fuzzy-merged.

The projection order is exact: preserve the existing legacy atom sequence, then
append newly admitted typed ids in canonical typed order. No existing string is
evicted to make room. If an admitted required typed id would be lost at the
existing public cap, the compiler holds/stops.

The following remain unchanged in the first slice:

- public runtime version `0.5.7`;
- `tmcp-skill-packet-v0.2`;
- `tmcp-composed-packet-v0.1`;
- `tmcp-runtime-next-v0.1`;
- `tmcp-recompiled-packet-v0.1`;
- `tmcp-run-receipt-v0.1`;
- existing MCP tool names, input schemas, output schema ids, trust policy, and
  public-contract fixture hashes.

Migration is opt-in through an internal semantic-bundle path. When no bundle
is supplied, the baseline lexical/legacy path remains unchanged. A future
semantic field change, new family, conflict resolution, public field, or tool
argument requires a new versioned decision.

Rollback disables the typed adapter before removing its pure module. If the
baseline output or public contract changes, or any fail-closed gate fails, stop
the typed path. Do not migrate public schemas, receipts, packages, or stored
artifacts.

## Smallest future implementation slice

Slice id: `runtime-v0.4-h1-typed-compile-and-projection`.

The slice proves H1 only: data-integrity reconciliation plus
migration-readiness rollback, supported by the four generic process atoms. The
other six domain atoms remain future registry work; all four families still
remain represented in the sealed evaluator plan.

### Exact future file ownership

New files:

- `tmcp_runtime/domain/behavioral_atoms.py` — typed records, registry,
  applicability, dependency/conflict resolver, deterministic budget, and
  render records.
- `tmcp_runtime/services/behavioral_atom_runtime.py` — adapter that converts
  explicit semantic context and compiler results into existing compose,
  packet, receipt, and evaluator shapes.
- `tests/test_tmcp_behavioral_atoms_runtime_v0_4.py` — pure compiler and H1
  behavioral contract tests.
- `tests/test_tmcp_behavioral_atoms_public_projection_v0_4.py` — public
  packet/receipt/tool compatibility and typed-static evaluator tests.

Future modifications in this slice:

- `tmcp_runtime/services/compose.py` — invoke the adapter only when an
  explicit internal semantic bundle is supplied; assert the no-bundle baseline
  is unchanged.
- `tmcp_runtime/services/evaluation_catalog.py` — register one non-provider
  `typed-static-v0.4` advisory variant.
- `tmcp_runtime/services/evaluation_scoring.py` — score typed compiler
  decisions and trace projections without provider outcomes or promotion.

Explicitly excluded from the slice are harvest/classifier replacement,
workflow/catalog/route changes, packet/receipt/public schema edits, MCP server
and tool-schema edits, public version bumps, provider adapters, admission,
always-on behavior, telemetry, canary, cross-skill composition, and lifecycle
actions.

### Ordered changes

1. Add immutable typed models, registry validation, and explicit v0.3-to-v0.4
   `supersedes` refs for the H1 seed records.
2. Define explicit semantic context for inputs, evidence, phase, reads, and
   ownership. A lexical candidate cannot satisfy a domain predicate.
3. Implement applicability, dependencies, conflicts, phase/read/evidence/
   verification/trust/stops, and deterministic local cost selection.
4. Implement internal render records and projections into existing packet and
   receipt string fields.
5. Add an opt-in compose adapter. With no semantic bundle, assert legacy output
   and public-contract fixture stability.
6. Add the typed-static advisory variant and evaluate the sealed artifacts
   without provider/model execution.
7. Run focused tests, public-contract tests, full suite, quality gates, and
   whitespace checks. Stop before provider preflight on any failure.

### Acceptance gates and stop conditions

Acceptance requires the exact base, exact owned-file list, all positive,
negative, ambiguous, no-trigger-word, phase, read, evidence, verification,
trust, dependency, conflict, stop, and budget tests, H1 valid-arm deltas,
rejection of all four historical invalid arms, all 12 sealed fixture decisions,
baseline/public-contract stability, and the repository quality gates.

Stop immediately if a typed domain atom can be admitted from literal wording,
untrusted content, a legacy string, missing evidence, unresolved reads, or a
missing dependency; if ambiguous/negative fixtures are admitted; if a stop is
dropped; if an invalid arm becomes eligible; if a public contract changes; if
the fixture is tuned; or if provider, cross-skill, admission, telemetry,
package, install, release, promotion, merge, or commit work is introduced.

## Future evaluator validation map

The v0.3 fixture artifact remains sealed and tuning-disabled. The future
typed-static evaluator consumes all 12 records with these expected outcomes:

| Fixture family | Positive | Negative | Ambiguous |
| --- | --- | --- | --- |
| Data integrity | `data_integrity_positive_reconciliation` → admit invariants/reconciliation | `data_integrity_negative_ui_display` → reject | `data_integrity_ambiguous_unowned_mismatch` → hold; stop for schema/owner/rule |
| Security/privacy | `security_privacy_positive_redacted_harvest` → admit redaction/secret boundary | `security_privacy_negative_latency_benchmark` → reject | `security_privacy_ambiguous_unowned_log` → hold; stop for owner/policy/handling boundary |
| Release readiness | `release_readiness_positive_ship_gate` → admit ship gate/evidence ladder | `release_readiness_negative_unit_debug` → reject | `release_readiness_ambiguous_partial_ci` → hold; stop for current evidence/owner/CI |
| Migration readiness | `migration_readiness_positive_rollback_cutover` → admit compatibility/rollback | `migration_readiness_negative_isolated_edit` → reject | `migration_readiness_ambiguous_deprecation_owner` → hold; stop for target/surfaces/order/owner |

The four valid structural arms remain eligible only when their source atom,
target obligation, and unique non-empty domain delta are present:

- migration receives data reconciliation;
- data integrity receives migration rollback;
- release receives security redaction; and
- security/privacy receives release gating.

The four historical shapes remain rejected before any outcome cell: two
duplicate generic conditions and two atom-identical six-atom supersets with no
eligible target variant. The three preregistered hypotheses remain domain-logic
selection only: reconciliation plus rollback, redaction plus ship gate, and
secret boundary plus evidence ladder. No outcome or causal claim is attached.

## Risks and dispositions

- **Public contract:** contain typed fields internally, reuse current string
  projections, assert absent-bundle baseline equality, and gate on contract
  fixture hashes.
- **Security/privacy:** require source-scoped trust and evidence, preserve
  existing redaction, forbid provider prompts/outcomes as render targets, and
  stop on missing ownership.
- **Performance/context size:** reserve required atoms and dependencies, use
  local estimates, deterministically defer optional content, and stop if
  required content cannot fit. This is not provider token telemetry.
- **Evaluation validity:** keep fixtures tuning-disabled, use a typed-static
  advisory variant, reject invalid arms before cells, and hold provider and
  composition gates closed.
- **Compatibility/rollback:** keep namespaces separate, use explicit
  supersedes refs, preserve legacy order, and roll back adapter-first.

## Authorization ladder

Implementation is authorized only after owner approval of this exact slice,
green replay/focused/full/quality gates, and no public contract diff. Provider
preflight requires the implemented slice, typed-static evaluator, security and
ownership gates, public baseline, and separate human approval. Isolated provider
outcome cells require successful provider preflight plus frozen cell boundaries
and rubrics. Cross-skill composition remains a separate closed gate until the
valid arms and isolated evidence justify a new decision.

## Verification and handoff

Already verified at intake:

- exact HEAD and source branch;
- all six source/destination hashes;
- focused preflight: 8 tests passed;
- JSON parsing for the four replayed JSON artifacts;
- complete repository suite: 454 tests passed, 3 skipped;
- Ruff format/lint, Basedpyright, launcher syntax, contract, and install checks.

After adding this packet, run JSON parsing, the focused decision-artifact test,
complete suite, relevant quality gates, `git diff --check`, untracked-file
whitespace checks, and an exact changed-surface audit. Python `jsonschema` and
Node `ajv` are unavailable in this environment; no dependency is installed,
so stdlib JSON parsing and the focused structural test are the available
structured-artifact gate. Provider cells and cross-skill composition are not
run.

Machine-readable plan:
`docs/experiments/behavioral-atoms-runtime-implementation-decision-v0.4.json`

Conceptual schema:
`schemas/tmcp-behavioral-atoms-runtime-implementation-decision-v0.4.schema.json`

To replay the research intake, read the authorized manifest's six
`changed_files[].path` entries, copy only those paths from
`/Users/jakyeamos/.codex/worktrees/2581/tmcp` to the listed repository-relative
paths, and compare SHA-256 for every pair before semantic inspection. This
decision packet is a handoff, not authorization to implement, install, publish,
merge, or commit.
