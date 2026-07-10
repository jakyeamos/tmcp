# Requirements: tmcp

**Defined:** 2026-07-10
**Core Value:** Deliver a safe, coherent, portable packet compiler without
breaking its public MCP/CLI contracts.

## v1 Requirements

### Release and Safety

- [ ] **MOD-SAFE**: Prevent release archives, harvesting, and evaluation from
  reading or emitting out-of-bound/unredacted local content.
- [ ] **MOD-STATE**: Make local artifact, cache, and AIOS side effects explicit,
  bounded, and reversible.

### Product and Contracts

- [ ] **MOD-FLOW**: Deliver a coherent compose → recompile → receipt journey
  using explicit sessions or packet files rather than shell-pasted JSON.
- [ ] **MOD-CONTRACTS**: Preserve and test public tool names, aliases, schemas,
  framing, and installed launch paths through the migration.

### Runtime and Quality

- [ ] **MOD-ARCH**: Replace the monolithic server implementation with a modular
  stdlib-only core behind a thin transport adapter.
- [ ] **MOD-OPS**: Unify metadata/versioning and enforce release, type, lint,
  and documentation-contract verification.

## v2 Requirements

### Follow-up Quality

- **QR-FLEET-BASELINE**: Keep this repo in the recurring QR fleet after the
  modernization milestones close.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Browser dashboard | TMCP's scope is MCP/CLI/Markdown interaction. |
| Required remote service or database | Standalone portability is core product value. |
| Silent API break | Existing integrations require a versioned migration. |
| QR execution | Quality Runner remains advisory-only. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOD-SAFE | Phase 0–2 | Pending |
| MOD-STATE | Phase 2, 5 | Pending |
| MOD-FLOW | Phase 3 | Pending |
| MOD-CONTRACTS | Phase 1, 6 | Pending |
| MOD-ARCH | Phase 2–6 | Pending |
| MOD-OPS | Phase 0, 1, 7 | Pending |

**Coverage:**
- v1 requirements: 6 total
- Mapped to phases: 6
- Unmapped: 0

---
*Requirements defined: 2026-07-10*
*Last updated: 2026-07-10 after modernization audit*
