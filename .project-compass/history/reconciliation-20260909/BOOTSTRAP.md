# Subsystem bootstrap

Source baseline: `59f06d48a9ef98712f319badfaaee035e2c781be` on `dev`, inspected 2026-09-08.

TMCP supplies operating context to agents. Existing drafts under-represent the extracted runtime, storage, safety, and compatibility paths, so a migration could miss the actual consumers.

- **packet-runtime**: Compile and recompile bounded advisory task packets with explicit source selection and safe optional persistence. 33 observed paths; draft ownership. Sources: `docs/TMCP_PACKET_SPEC.md`, `docs/PACKET_STABILITY.md`, `docs/ADAPTIVE_PACKET_RUNTIME.md`.

- **skill-harvest-recommendation**: Evaluate reusable material and recommend task-relevant inputs with provenance, safety, and explicit promotion boundaries. 16 observed paths; draft ownership. Sources: `README.md`, `docs/TMCP_PACKET_SPEC.md`, `docs/PACKET_STABILITY.md`.

- **release-distribution**: Distribute identifiable portable TMCP artifacts with conservative compatibility and offline rollback. 12 observed paths; draft ownership. Sources: `docs/DISTRIBUTION.md`, `docs/CENTRAL_RUNTIME.md`, `docs/COMPATIBILITY.md`.

## Authority and evidence

Existing root intent and prior quiz sessions are preserved. Every new or refined subsystem remains draft; path bindings and decision records are proposed. Code supplies observed structure, and linked specifications supply documented constraints. This bootstrap neither ratifies ownership nor authorizes implementation, release, scheduling, or new blocking gates.

`development.json` enumerates exact observed paths against a broader source inventory. Proposed paths do not count as accepted coverage. Unmapped paths remain visible. Required commands are existing regression checks; they are not represented as current proof or sufficient admission evidence.

No canonical behaviors[].id inventory exists for the selected runtime; test and specification references are linked without inventing behavior IDs. This inspection does not certify packet relevance, a plugin installation, or experimental-tool maturity. Unselected skills, schemas, and runtime modules remain explicit inventory gaps.

## Focused reconciliation

The evidence digest above supplies the candidates for session `subsystem-bootstrap-20260908` in `quiz.json`. Prior unanswered sessions remain preserved. No answers were inferred.

1. The updated map puts packet compilation, safe storage, and protocol adapters together, with harvest/recommendation and distribution as neighbors. Should storage/safety remain inside packet runtime, or become a separate subsystem before further work?

2. README distinguishes stable packet tools from experimental harvest and promotion tools. Should the next usefulness check focus on packet relevance/recompilation, with experimental promotion remaining deferred unless separately selected?

## Maintenance

Use the installed Project Compass helper to read `family` and request `change-context` for exact task paths in the selected workspace. Follow its returned canonical references, neighboring constraints, and proof requirements. Reconcile ownership before promoting draft intent. Recompute after the actual diff; a rename or new path needs an explicit mapping, and changed shared inputs require consumer reassessment.

The bootstrap changes metadata and orientation only. It adds no application behavior, dependency, release gate, or runtime distribution change. The change-surface matrix records Compass closure for future add/change/remove/fold operations.
