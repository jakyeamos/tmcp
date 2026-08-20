# TMCP fleet-fold disposition — 2026-08-20

This receipt records the live disposition of the non-target TMCP refs reviewed during
the fleet fold. It is a source-history disposition, not a release claim: a branch is
either represented by the current `dev` tree, explicitly superseded by a newer
canonical implementation, or disposed as a redundant checkpoint/legacy fixture.

## Target and custody

- Canonical integration target at review start: `dev` / `origin/dev`
- Target after the TMCP integration lane: `0bba3c64770736d920a7c95b7515ae4f70c42d28`
- Target state: clean, synchronized, and verified by 686 tests (3 expected skips),
  whole-repository Ruff and Basedpyright, contract/install/release-evidence checks,
  Node syntax checks, `git diff --check`, and the changed-line Pre-CR gate.
- Local source refs reviewed: 22, excluding the task branch
  `codex/fleet-fold-tmcp-20260820` and the active locked WIP branch
  `codex/tmcp-integration-20260819`.
- Candidate worktree consumers: none. The only non-root worktrees are the locked
  coordinator WIP and this task-owned integration lane.
- GitHub branch endpoint proof: every published candidate ref returned
  `protected=false`; the repository-wide PR scan found no open candidate PRs. PRs 18
  and 19 for the AIOS deprecation/release lanes are already merged.

## Per-ref disposition

| Source ref | Reviewed tip | Disposition | Target-side evidence |
|---|---|---|---|
| `codex/canonical-local-reapply` | `74fe6eaf` | Integrated | Patch-equivalent coordinator receipt is `3ab35117`; current target carries the receipt and its test. |
| `codex/compass-fleet-registry-65` | `99e2af07` | Integrated | Root compass is represented by `7dfdcd1a`; no source-only compass content remains. |
| `codex/compass-quiz-tmcp-0814` | `927574e5` | Integrated | Realignment quiz is represented by `ea8839b1`. |
| `codex/compass-drafts-tmcp-0814` | `cb92c384` | Integrated | Draft subsystem compasses are represented by `5f4c4f59`; the fold lane also carried the missing receipt/fixture artifacts. |
| `codex/preserve/tmcp-7dd9` | `5d1b2491` | Integrated | H3 optional-hint gating is patch-equivalent to `2202fa7d`; the shared provenance/checksum chain is present on target. |
| `codex/preserve/tmcp-984c` | `37a01ce1` | Integrated | Provider-telemetry preservation patch is equivalent to `310d5256`; the remote tip `18e6b05` is an ancestor of the reviewed local tip. |
| `codex/preserve/tmcp-dddc` | `755f8c71` | Integrated | Provider-telemetry preservation patch is equivalent to `310d5256`; its remote `18e6b05` tip is covered by the same ancestor proof. |
| `codex/preserve/tmcp-c986` | `4fc7b9af` | Superseded | Current extractor boundary `3b2105f0` plus `310d5256` is newer and stricter; the candidate tree removes current attribution/availability behavior. |
| `codex/preserve/tmcp-b5a4-tmcp-3c9b2fe` | `cd865247` | Superseded/absorbed | The decision/preflight schemas, fixtures, and tests are represented by the current H2/H3/semantic-preflight evidence set; the candidate is an older artifact-only checkpoint. |
| `codex/preserve/tmcp-e5ad` | `3d7fc2e` | Superseded/absorbed | Current `route_catalog`, `route_resolution`, admission, coordination, and recompile surfaces are newer; the candidate tree removes those later safety/runtime surfaces. |
| `codex/preserve/tmcp-c77f` | `7b353ecc` | Disposed checkpoint | Duplicate TMCP WIP checkpoint; its changes are already in the folded target history and it has no independent worktree consumer. |
| `codex/preserve/tmcp-331a` | `cd2bce32` | Superseded | Current release scanner, archive, fixture, and evidence gates are newer; direct tree comparison shows this candidate removes current scripts and schemas. |
| `codex/preserve/tmcp-3e91` | `82c4f3c2` | Superseded | Same release-scanner lineage as `tmcp-331a`; current target has the later portable evidence/checksum implementation and stronger gates. |
| `codex/recovery-fixture-head-20260711` | `c74d0c3` | Disposed legacy fixture | July package-marker fixture only; it removes the current runtime and quality surfaces and adds no target behavior. |
| `codex/retire-aios-adapter` | `5f10c716` | Integrated | PR 18 is merged; the target carries the AIOS deprecation in `edcc629e`. |
| `codex/tmcp-0.5.8-aios-deprecation` | `3e2959d8` | Integrated | PR 19 is merged; release/deprecation state is represented by the current target evidence. |
| `codex/tmcp-clean-launcher` | `4056776b` | Superseded | Current launcher/registry and runtime surfaces are newer; this branch is an older two-commit launcher checkpoint that removes current behavior. |
| `codex/skill-eval-dogfood` | `4417f3ac` | Superseded alternate research architecture | The branch is a large held research campaign based on the old `3c9b2fe` architecture. Current `dev` retains the bounded evaluation services and evidence gates; bulk adoption would remove newer runtime/safety surfaces and would not authorize promotion. |
| `codex/tmcp-composition-evaluator-proof` | `bd00f1bd` | Superseded alternate research architecture | The branch is a 184-commit preregistration/evaluator rewrite whose tree removes current runtime boundaries. Its held research conclusions are not executable runtime upgrades. |
| `codex/tmcp-composition-lift-campaign` | `17b44966` | Superseded alternate research architecture | The branch is a 154-commit composition-lift rewrite with large unratified runtime/storage additions; current `dev` is the newer canonical boundary. |
| `codex/tmcp-compositional-evidence` | `4d2bbe7e` | Superseded alternate research architecture | The branch is an 80-commit evidence rewrite that removes current APIs and quality surfaces; no safe additive patch remains after comparison with target. |
| `codex/tmcp-compositional-intelligence` | `da266a43` | Superseded alternate research architecture | The branch is a 61-commit benchmark/intelligence rewrite based on the old architecture; current target behavior and gates are newer and remain authoritative. |

## Resolution rule

No source ref is being retained as `unknown` or `legacy`. Integrated refs are made
target-ancestral by the fold history; superseded refs are made target-ancestral by an
explicit history-only disposition commit whose first parent is the verified target
tree and whose additional parents are the reviewed source tips. The disposition
commit changes no runtime source code. This preserves the audit trail while keeping
the canonical target on the verified mature implementation.

The active locked branch `codex/tmcp-integration-20260819` is not a candidate for
this pass: it is an active temporary WIP consumer and remains additive until its
owner releases it. The task branch is also retained until remote target fast-forward,
source-ref deletion, and final isolation-workflow release complete.
