# Roadmap: TMCP Modernization

**Created:** 2026-07-10
**Mode:** modernization
**Plan Format:** Vertical, independently verifiable milestones from
`docs/modernization/EXEC_PLAN.md`.

### Phase 0: Release safety emergency gate

**Goal:** Eliminate release-archive disclosure risk.
**Requirements:** MOD-SAFE, MOD-OPS
**Depends on:** None
**Plans:** Complete 2026-07-11

### Phase 1: Contract freeze and target baseline

**Goal:** Establish canonical tool/version metadata and hermetic compatibility
fixtures.
**Requirements:** MOD-CONTRACTS, MOD-OPS
**Depends on:** Phase 0
**Plans:** Ready to begin

### Phase 2: Safe input and storage foundation

**Goal:** Centralize path, redaction, and persistence safety.
**Requirements:** MOD-SAFE, MOD-STATE, MOD-ARCH
**Depends on:** Phase 1
**Plans:** Pending approval

### Phase 3: Compose/recompile vertical slice

**Goal:** Deliver the primary task journey with explicit sessions and readable
output.
**Requirements:** MOD-FLOW, MOD-CONTRACTS, MOD-ARCH
**Depends on:** Phase 2
**Plans:** Pending approval

### Phase 4: Advanced discovery migration

**Goal:** Migrate harvest, recommendation, promotion, and evaluation to the
safe core.
**Requirements:** MOD-SAFE, MOD-CONTRACTS, MOD-ARCH
**Depends on:** Phase 2
**Plans:** Pending approval

### Phase 5: Evidence-review vertical slice

**Goal:** Make review evidence, artifact writes, and AIOS choices explicit.
**Requirements:** MOD-STATE, MOD-FLOW
**Depends on:** Phase 2
**Plans:** Pending approval

### Phase 6: Thin-adapter cutover and deletion

**Goal:** Complete the modular migration and remove old implementations.
**Requirements:** MOD-ARCH, MOD-CONTRACTS
**Depends on:** Phases 3–5
**Plans:** Pending approval

### Phase 7: Release hardening and adversarial review

**Goal:** Complete validation, cleanup, and release readiness.
**Requirements:** MOD-OPS, MOD-SAFE
**Depends on:** Phase 6
**Plans:** Pending approval

---
*Last updated: 2026-07-11 after Milestone 0 release-safety verification*
