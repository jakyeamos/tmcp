# Backfill Quality Gate Proposal

Status: separate proposal, not the current AIOS backfill workflow.

This note captures a TMCP idea from the assistant during discussion. It should not be treated as the user's intended design until that design is separately explained and reviewed.

## Idea

Create a TMCP-governed quality gate for any workflow that backfills local skill, agent-instruction, or workflow-document evidence into a durable system such as AIOS.

The premise is that local skills and agent instructions are useful operational evidence. They can reveal routing preferences, quality bars, safety boundaries, tool habits, and workflow conventions. They should not be interpreted as complete truth about a person.

## Proposed Flow

```text
harvest local skill/instruction sources
-> compile TMCP packet seed
-> classify behavior atoms
-> redact and hash source evidence
-> generate dry-run backfill plan
-> score against quality gates
-> require approval for writes
-> write batch with receipt
-> verify retrieval and idempotence
```

## Candidate Gates

- Scope gate: exact roots, include rules, and exclude rules are explicit.
- Privacy gate: redaction is enabled; raw secrets are not written to durable storage.
- Provenance gate: every backfilled behavior atom links to source path, source type, and excerpt hash.
- Interpretation gate: direct instructions are separated from inferred preferences.
- Conflict gate: conflicting instructions are preserved instead of flattened.
- Deduplication gate: repeated rules collapse into canonical behavior atoms with multiple sources.
- Idempotence gate: reruns do not duplicate records or churn stable IDs.
- Dry-run gate: proposed inserts, updates, and deletes are visible before writes.
- Rollback gate: each write batch has a receipt, batch id, and reversible change set.
- Quality score gate: low-scoring batches block writes; warnings require documented risk.
- Post-write verification gate: durable records can be queried back with expected provenance.

## Candidate Output Shape

```json
{
  "schema": "tmcp-backfill-quality-gate-v1",
  "decision": "pass | warn | block",
  "score": 92,
  "hard_gate_failures": [],
  "source_summary": {},
  "behavior_atoms": [],
  "conflicts": [],
  "redaction_summary": {},
  "dry_run_plan": {},
  "write_receipt": null,
  "verification": {}
}
```

## Open Questions

- Which backfill targets should be supported first: AIOS only, or any durable knowledge store?
- Should this be implemented as a TMCP MCP tool, an AIOS adapter workflow, or both?
- What fields define a stable behavior atom identity across reruns?
- What evidence should be stored directly versus represented only by hash and provenance?
- Which gates are hard blockers for a first version?

