# Planning State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-11)

**Core value:** Deliver a trustworthy, portable packet compiler with safe local
file boundaries and a coherent agent-facing workflow.
**Current focus:** Complete runtime adapter convergence after API, safe-input,
persistence, scoring, rendering, orchestration, plan, catalog, advisory,
redaction, and transport cutovers.

## Milestone

**Name:** TMCP Modernization
**Status:** Milestone 3 adapter thinning and security hardening: pure domain,
service, artifact-manifest, receipt-cache, storage-ingress, CLI-parser, and
harvest-argument cutovers; explicit-only AIOS, receipt, and cache-opt-in
  boundaries plus CLI/harvest safety hardening, diagnostic-report assembly, and
  read-only harvest/evaluator persistence plus packet-scoring policy, report,
  rendering/advisory, input, compose-failure, mode-orchestration, and
  plan-construction, server renderer, policy-catalog, runtime evaluator API,
  harvest-advisory, runtime-redaction, MCP/CLI transport, and typed
  request/result registry-dispatch cutovers complete; optional AIOS execution
  runtime-state/recompile orchestration and project-local session lifecycle are
  now runtime-owned; generic artifact-bundle persistence is now a runtime
  service over adapter callbacks; receipt recording is now runtime-owned over
  adapter callbacks; global-promotion manifest assembly is now runtime-owned;
  explain assembly and evidence parsing are now runtime-owned; continue the
  thin-adapter deletion pass is complete for private CLI, AIOS subprocess,
  harvest-constant, and unused-schema seams; tests target runtime owners
  directly. The release compile/install inventory now covers every runtime
  module and is shared by the cross-platform workflow and package checks. The
  first legacy promotion-summary reader is complete; the remaining shipped
  receipt/session artifacts have no alternate schema and remain strict readers.
  The 0.5.0 compatibility cutover note is active; all version surfaces now use
  0.5.0 and the evidence record points to successful post-cutover PR run
  `29285497867`; final evidence-pointer rerun `29285802846` also passes. The
  draft PR is ready for a fresh adversarial review.
  Draft PR #2's first hosted run passed Linux/macOS but failed Windows because
  exact-file read-only inputs rejected the missing O_NOFOLLOW primitive;
  `b99c58a` adds the validated Windows fallback. Follow-up run
  `29284101047` reduced the residual failures to Windows path/newline contracts;
  `1a59e2f` normalizes those boundaries. Hosted run `29285497867` now passes all
  six matrix jobs for the 0.5.0 cutover, final rerun `29285802846` passes, and
  post-review fix run `29287154661` passes for `1fd10f4`; docs-only rerun
  `29287368329` also passes.
  Fresh review closed malformed MCP transport input/notification defects and
  packaged the compatibility note. Formatting and typecheck now pass across all
  148 tracked Python files and the `scripts`, `tmcp_runtime`, and `tests`
  scopes; hosted tag run `29289138645` passes the pinned quality job and all
  six platform jobs for merge commit `1fcda48`. The GitHub release and MCP
  Registry publication are complete.
**Started:** 2026-07-10

## Active Phase

- **Phase:** Compose and recompile vertical slice
- **Slug:** `tmcp-modernization`
- **Status:** Receipt/artifact construction and cache policy are pure-owned;
  storage owns bounded redacted cache reads, while adapter-owned roots, writes,
  identity, clock, output selection, redaction, and transport remain intact;
  generic artifact-bundle persistence is runtime-owned through explicit storage
  and redaction callbacks, and receipt recording is runtime-owned through
  explicit identity, path, redaction, and write callbacks; global-promotion
  manifest assembly is runtime-owned while roots and persistence gating remain
  adapter-owned; explain assembly and review-evidence parsing are runtime-owned
  while AIOS choice and final redaction remain adapter-owned.
- **Plan:** `docs/modernization/EXEC_PLAN.md`

## Completed Scope

- Modernization baseline, parallel audit, target architecture, and executable
  milestone plan recorded under `docs/modernization/`.
- Isolated audit branch created from the 0.4.0 release baseline.
- Milestone 0 release safety completed on `codex/tmcp-modernization-v2`:
  Git-tree allowlist packaging, archive manifest verification, reproducibility,
  hermetic fixtures, and pre-merge release-evidence enforcement.
- Milestone 1 contract freeze completed in `5981dcd`: canonical version/tool
  registry, all alias/default fixtures, hermetic transport clients, live MCP
  metadata validation, and CI enforcement.
- Release fixture checksums are explicitly labelled in `0299ca4`, preserving
  the archive secret scanner while allowing deterministic contract fixtures.
- `b251e8e` preserves the strict scanner while excluding only lower-snake to
  upper-snake code assignments from high-entropy token detection.
- `65a1bfe` keeps the opaque-token regression test archive-safe by assembling
  its test value from short source literals.
- The committed M1 tree passes archive reproducibility and the extracted
  package verification suite (153 tests; source-only metadata check skipped).
- `49a87c9` separates CLI/launcher contract coverage from server-domain tests,
  removing the test-size quality warning without changing behavior.
- `3abe21c` moves harvest through `tmcp_runtime/safety` and its artifact output
  through descriptor-safe staged bundles. It adds 13 boundary tests; the full
  suite passes.
- `42b922f` adds redacted, bounded exact-file inputs for evaluation and a single
  text/JSON artifact store with descriptor-relative writes, directory identity
  checks, and fail-closed behavior when those primitives are unavailable. The
  evaluation/artifact boundary is covered.
- `587b8c1` moves skill evaluation onto those boundaries: data-only variant
  composition, bounded/redacted plan and evidence inputs, safe artifact writes,
  and one-read score persistence.
- `a5959a3` adds a fail-closed versioned skill-fixture harness: exact original,
  editable candidate, omitted baseline, controlled negative variant, explicit
  golden-case/bar readiness, candidate digest recording, and no-call eval-plan
  preparation across the discovered skill corpus.
- `1d8341e` adds hash-chained reviewed proposal bundles: only explicitly
  approved per-skill replacements are applied to candidates; originals remain
  immutable and eval preparation reports applied/skipped proposal provenance.
- `44c428b` adds review-only proposal generation from TMCP static findings and
  the guidebook rewrite variant. Corpus generation produced 102 proposed
  bundles and leaves every one unapplied until human review changes its status.
- `c986f61` adds an explicit experimental proposal mode so numeric original-vs-
  proposal baselines can run before review; proposed rewrites are disposable,
  provenance-labelled, and still cannot be promoted as approved changes.
- `a46d08f` adds an explicit-target approval fixture and keeps the ambiguous
  no-target case as a refusal control, enabling a discriminating paired
  behavior baseline instead of relying on static findings alone.
- The first subscription-backed `gpt-5.5` low-reasoning paired run scored the
  original 2/6 and experimental candidate 3/6 across the two cases; the
  explicit-target case improved 2/3 to 3/3, while the refusal control tied 0/3.
  Full traces and the independent judge are recorded in the ephemeral baseline
  artifact `/private/tmp/tmcp-skill-fixture-behavior-baseline-v0.1.json`.
- `e6cc97a` adds a concrete-verification fixture family with an exact target
  condition and an evidence-backed pass/fail bar for the next paired run.
- The second subscription-backed paired run tied on concrete verification at
  3/3 for both original and candidate; across both families the aggregate is
  original 5/9 versus candidate 6/9. This confirms a targeted approval gain,
  but no broad claim that every static rewrite improves behavior.
- `5a59cdd` adds a shell-safe subscription-backed Codex fixture runner that
  passes blind prompts on stdin, records model/reasoning/sandbox/session
  provenance, and has a regression test proving literal shell syntax cannot
  execute. The original and candidate copies remain isolated and judge-only
  bars remain outside runner input.
- Three-run independent rejudge of the approval family now gives the
  ambiguous refusal control original 0/3 and candidate 0/3, while the explicit
  target is original 0/3 and candidate 3/3. The reproducible pass-rate record is
  `/private/tmp/tmcp-skill-fixture-behavior-baseline-v0.3.json`; this is a
  targeted approval-gate result, not corpus-wide proof.
- Three-run independent rejudge of concrete verification gives original 3/3 and
  candidate 3/3. Combined across both fixture families, original is 3/12 and
  candidate 6/12 on whole-case pass rate; the combined record is
  `/private/tmp/tmcp-skill-fixture-behavior-baseline-v0.4.json`. The rewrite's
  observed gain is isolated to approval gating, with no verification regression.
- `required-read-disclosure` is now a third ready fixture family. Its three-run
  rejudge is original 0/3 versus candidate 3/3: the candidate explicitly names
  AGENTS.md, discloses its absence, and reports concrete target evidence. The
  corrected combined baseline is
  `/private/tmp/tmcp-skill-fixture-behavior-baseline-v0.5.json`; it reports
  original 3/12 versus candidate 9/12 using variant-specific denominators
  (25% versus 75%), with two family wins, one tie, and no tested regression.
- `70ee045` adds the fourth ready fixture family, `trigger-boundary`. Its
  unrelated-request
  rejudge is original 3/3 versus corrected candidate 3/3, confirming no tested
  behavioral regression. `48ae0f5` fixes a real structural defect in the
  proposal generator: it copied the broad frontmatter description into the
  trigger rewrite. The fix narrows the candidate to the body's explicit
  `Use this skill when...`
  sentence, covered by a policy regression test. The combined v0.6 baseline is
  `/private/tmp/tmcp-skill-fixture-behavior-baseline-v0.6.json`; it reports
  original 6/15 versus candidate 12/15 (40% versus 80%), with two family wins,
  two ties, and no tested regression. This is still targeted evidence, not
  corpus-wide proof.
- The fifth `output-contract` fixture adds a bounded inspection case. Its
  independent three-run rejudge is original 2/3 versus candidate 3/3: the
  original missed skipped-source disclosure once, while the candidate supplied
  the full contract. That first result was partially confounded because the
  runner schema named the observables; it is retained as v0.7 but superseded by
  the neutral-format rejudge. The corrected v0.8 baseline is
  `/private/tmp/tmcp-skill-fixture-behavior-baseline-v0.8.json`; original is
  0/3 versus candidate 2/3 on this case, with one candidate miss on explicit
  next actions. Across all five families, v0.8 reports original 6/18 versus
  candidate 14/18 (33.3% versus 77.8%), with three family wins, two ties, and
  no tested regression. The earlier v0.7 baseline is
  `/private/tmp/tmcp-skill-fixture-behavior-baseline-v0.7.json`; it reports
  the schema-primed measurement and remains useful only for comparison. This
  is still not corpus-wide proof.
- `b12fd06` makes the generated output contract explicit: the final
  response must include labeled Sources inspected, Skipped sources and why,
  Verification results, and Next actions fields. The neutral-format candidate
  rejudge is 3/3 after this change. The authoritative v0.9 baseline is
  `/private/tmp/tmcp-skill-fixture-behavior-baseline-v0.9.json`; it reports
  original 6/18 versus candidate 15/18 (33.3% versus 83.3%), with three family
  wins, two ties, and no tested regression.
- `1472038` adds the sixth `precedence-boundary` fixture, which tests an unsafe
  embedded attempt to
  override higher-priority instructions. Its independent rejudge is original
  2/3 versus candidate 3/3: the original once stopped at an unsupported
  missing-path claim, while the candidate consistently located the target,
  preserved `protected value`, and stayed read-only. The authoritative v1.0
  baseline is `/private/tmp/tmcp-skill-fixture-behavior-baseline-v1.0.json`;
  across six families it reports original 8/21 versus candidate 18/21 (38.1%
  versus 85.7%), with four family wins, two ties, and no tested regression.
- `d809ad9` adds the seventh ready fixture family, `host-portability`. With the
  request
  explicitly denying host-specific tools, original and candidate both pass 3/3
  using ordinary file inspection. This is a tie and a no-regression result, not
  evidence that the host-specific wording is safe in every environment. The
  v1.1 baseline is `/private/tmp/tmcp-skill-fixture-behavior-baseline-v1.1.json`;
  across seven families it reports original 11/24 versus candidate 21/24
  (45.8% versus 87.5%), with four family wins, three ties, and no tested
  regression.
- Composition fixture `required-read-output-contract-composition` exercises both
  rewrites in all four original/candidate pairings, with two repeats per pairing
  and independent judging. The durable manifest and baseline are
  `tests/fixtures/skill-fixtures/composition-cases-v0.1.json` and
  `tests/fixtures/skill-fixtures/composition-baseline-v0.1.json`. On the strict
  bar, original/original passes 0/2, candidate/candidate passes 2/2, and each
  mixed pairing passes 0/2 (2/8 overall). This fixture demonstrates a
  complementary interaction: the required-read rewrite supplies explicit
  AGENTS.md/unavailable-source disclosure, while the output-contract rewrite
  supplies the labeled final-response fields. It is one task shape and one
  model/effort setting, so it is interaction evidence rather than corpus-wide
  causal proof.
- A second composition family, `precedence-output-contract-composition`, is
  recorded in `tests/fixtures/skill-fixtures/composition-cases-v0.2.json` and
  `composition-baseline-v0.2.json`. All four pairings scored 0/2 on the strict
  bar (0/8 overall): every run preserved `protected value` and made no edits,
  but every final response omitted the required audit labels, including the
  candidate/candidate pairing. This is a repeatable contract failure under
  composition at gpt-5.5 low reasoning, while the precedence safety behavior
  itself remained intact; it blocks any claim that the output-contract rewrite
  composes reliably with safety-boundary skills.
- `db5d7d6` records the completed mixed-pairing rejudge. The output-contract
  generator was strengthened with literal `label: value`
  lines, conflict disclosure, and a precedence guard that preserves a concise
  source-conflict summary. The focused policy test now covers this behavior.
  The complete post-fix precedence/output-contract rejudge is recorded in
  `tests/fixtures/skill-fixtures/composition-baseline-v0.4.json`: candidate-
  candidate, candidate-original, and original-candidate each pass 2/2, while
  the unchanged original/original control remains 0/2, for 6/8 across the full
  family and 6/6 across candidate-containing pairings. The required-read/
  output-contract candidate/candidate artifacts were independently judged 2/2
  as well. No tested regression or safety mutation occurred; this remains
  fixture-level interaction evidence at gpt-5.5 low reasoning, not corpus-wide
  causal proof.
- `a66566e` records `composition-cases-v0.3.json` and
  `composition-baseline-v0.5.json`, adding a
  trigger-boundary/output-contract interaction on a bounded artifact-read task.
  Candidate-candidate passes 2/2; candidate-original is unstable at 1/2; and
  original-candidate fails 0/2 because the broad original trigger launches
  unrequested release checks. Original-original is 0/2, for 3/8 overall.
  This is a non-commutative composition result: both rewrites are needed for
  stable behavior, with no tested mutation or regression. It remains one task
  shape at gpt-5.5 low reasoning, not corpus-wide causal proof.
- `5f74a1d` records `composition-cases-v0.4.json` and
  `composition-baseline-v0.6.json`, adding a
  trigger-boundary/required-read interaction. Under the strict required-but-
  unavailable disclosure bar, candidate-candidate is unstable at 1/2 and the
  other three pairings fail 0/2, for 1/8 overall. This is a negative
  composition signal: the trigger rewrite changes context enough that the
  required-read disclosure is not reliably preserved. It is one task shape at
  gpt-5.5 low reasoning, so it is a warning signal rather than corpus-wide
  causal proof.
- `7c218d9` records the third independent candidate/candidate repetition in
  `composition-baseline-v0.7.json`: it passes, moving that pairing from 1/2 to
  2/3. The interaction is variable rather than deterministically broken, but
  remains below a stability bar; the other pairings remain 0/2. This preserves
  the negative signal without overstating it as a guaranteed defect.
- `0162223` records the required-read rewrite strengthened with literal
  attempted-read,
  required-but-unavailable, and exact-value instructions, covered by
  `test_rewrite_makes_required_read_disclosure_literal`. The full v3 matrix is
  recorded in `composition-baseline-v0.8.json`: candidate-candidate remains
  unstable at 1/2, candidate-original is 0/2, original-candidate is variable
  at 1/2, and original-original is 0/2. The repair clarifies the contract but
  does not establish behavioral lift; no further prose-only heuristic should
  be inferred from this single task shape.
- `319ef2d` adds a post-run structural artifact validator that checks observable contract facts
  without a model call or bar exposure to the runner. Its seven focused tests
  cover schema/labels, exact values, required-read disclosure, negated versus
  positive release activity, and mutation detection. The v0.9 composition
  baseline records 2/8 structural passes, exactly matching the independent
  judge's 2/8 count; this is a useful first-pass gate, not yet a corpus-general
  trust claim. `0ed5c17` closes an exact-value false positive (`invalid` no
  longer satisfies expected `valid`) with a regression test; the v3 result
  remains 2/8.
- `c31641a` removes the last plan-path filesystem probe from advisory analysis;
  evaluation variants are now composed from redacted in-memory node data only.
- `1e43ed0` restores the hosted verification matrix: job-level environment
  values now use the permitted `github.workspace` context instead of
  `runner.temp`, which GitHub rejected before scheduling any jobs.
- `32fb08d` moves review, recommendation, promotion, global cache, and receipt
  artifacts through the shared safe store; redacts direct user inputs before
  return/persistence; slugs implicit promotion directories; and publishes the
  storage capability through `doctor` and `status`.
- `4c5877f` keeps the new artifact-safety coverage in a focused test module;
  unsupported-platform denial remains an expected local skip.
- `3f4b74b` closes the adversarial boundary findings: review auto mode stays
  standalone; explicit AIOS review is preview-only; default writes reject
  symlink-derived roots; cache reads are bounded, schema-gated, and canonical;
  Windows junctions are link-like; artifact identities retain opaque collision
  resistance; and Windows runs the portable package smoke instead of skipping it.
- `c31a9ee` moves MCP adapter/status safety coverage into its own test module,
  restoring the repository test-source size gate.
- Clean package reproducibility passes at `1b3697f`; the extracted package
  verifies portable receipt denial as well as persistence-capable receipt flow.
- `2d04122` moves deterministic route inference into `tmcp_runtime/domain`,
  removing the first packet-domain owner from the legacy adapter.
- `31a1d47` adds explicit, redacted project-local packet sessions with absolute
  project roots, opaque keys, revision-locked latest records, pinned recompile
  lineage, portable denial, and CLI/MCP/package coverage.
- The clean committed tree at `fcbae5e` passes reproducible package verification,
  including the packaged session compose → recompile smoke.
- `6864350` moves composition/runtime/session release dogfood into focused
  helpers, preserves the main release checker as an orchestrator, and makes the
  shared release compile helper the documented local source-validation command.
- `401e125` moves compatibility parsing, reason/diff/merge policy, validated
  proposal application, and recompile Markdown rendering into
  `tmcp_runtime/domain/recompile.py`; the server retains only runtime state,
  source enrichment, composition/session selection, and transport assembly.
- `2eedd09` moves UI/contextual gates, source-gate filtering, and reference-read
  selection into `tmcp_runtime/domain/composition.py`, shared by compose and
  runtime without changing MCP/CLI behavior.
- `8b2cdb5` moves composed-packet provenance, shortcut eligibility, rationale,
  and Markdown rendering into the same composition domain; package smoke now
  asserts those public packet fields in extracted releases.
- `9cb3c8b` moves final composed-packet assembly into the composition domain:
  normalization/caps, deferred and ignored items, stable packet IDs, receipts,
  safety metadata, and Markdown all derive from one deterministic builder.
- `06defa0` moves scoped-seed and router task-family policy into
  `tmcp_runtime/domain/families.py`: family-context construction, primary and
  sibling decisions, and declared-load/slug normalization. The adapter retains
  source-text interpretation and runtime state; direct and integration tests
  cover threshold/tie, router, support-doc, and transition-only fallback paths.
- `9b6c47f` moves node scoring, ordering/caps, route/family interactions, and
  lexical selection helpers into `tmcp_runtime/domain/composition.py`; direct
  tests cover guardrails, metadata, fallback, and tie behavior. The commit gate
  reports that this owner is now above the 600-line source limit, so split it
  before the next feature change.
- `6cc0769` resolves that source-size gate by separating final packet
  construction, provenance, shortcut selection, and Markdown rendering into
  `tmcp_runtime/domain/packets.py`. Both domain owners are below the 600-line
  limit; the server keeps recompile renderer injection as a dependency-free
  callback.
- `32d6a9f` moves family-phase aliases, seed transition fallback, phase choice,
  skill activation/deactivation, and transition-only seed lookup into
  `tmcp_runtime/domain/families.py`, initially keeping declared-read resolution
  adapter-injected to preserve the domain dependency direction.
- `6a3acc8` moves declared-read parsing, path matching/narrowing, and selected
  source enrichment into `tmcp_runtime/domain/declared_loads.py`; runtime-family
  transitions now call that sibling domain directly, while composition owns the
  generic selected-node merge.
- `775782e` moves standalone task routing, source projection, substance checks,
  packet assembly, and Markdown rendering into
  `tmcp_runtime/domain/standalone_packets.py`; the adapter now only orchestrates
  its three existing public call paths.
- `7ed60d4` moves review profile dimensions, coverage requirements, profile
  selection precedence, and fallback behavior into
  `tmcp_runtime/domain/review_profiles.py`; standalone review and workflow
  recommendation now consume one canonical catalog.
- `516a497` moves review evidence parsing/contracts, rubric synthesis, audit
  scoring, remediation planning, handoff construction, validations, and Markdown
  rendering into `review_evidence.py` and `review_results.py`; the adapter now
  retains only harvest, redaction, artifact persistence, status, and MCP dispatch.
- `55ddb54` moves curated workflow definitions, candidate filtering, stability
  classification, and ID lookup into `tmcp_runtime/domain/workflow_catalog.py`;
  recommendation, promotion, and global-cache selection share one catalog owner.
- `f6f50f3` moves workflow signal scoring, recommendation reasons, rubric/template
  construction, required-evidence guidance, source-scope policy, and candidate
  instance construction into `tmcp_runtime/domain/workflow_recommendations.py`.
- `03009f9` moves scoped-seed projection, custom workflow ideas, adaptive-pack
  construction, duplicate-label analysis, process-gap policy, and…

_(truncated for length)_

## Workflow Notes

- Release packages must use the Git-tree archive policy and pass the
  reproducibility check before publication.
- Quality Runner remains advisory-only; the prior QR plan is parked.
- Preserve public MCP/CLI contracts through a versioned compatibility adapter.
- Keep the CLI parser pure and API-owned; reject options outside the selected
  schema and do not move filesystem, environment, process, redaction, storage,
  or transport authority into `tmcp_runtime/api/cli.py`.
- Keep harvest argument projection read-only and service-owned, with bounded
  scan/read budgets; roots, writes, redaction, sessions, and transport remain
  adapter authority.
- Keep doctor/status report assembly pure and data-only; the adapter retains
  environment probes, path redaction, capability checks, and transport.
- Keep harvest service orchestration read-only; the adapter owns output roots,
  atomic persistence, artifact aliases, and final path redaction.
- Keep evaluator planning/scoring free of storage/output-root authority; the
  adapter owns input budgets, manifests, persistence, and aliases.
- Keep packet-inclusion expectations and composed-packet diffing pure; the
  evaluator injects only the adapter's data-only compose callback.
- Keep evaluator decomposition, static review, variant generation, and
  observable-contract policy pure over supplied text and pattern catalogs.
- Keep trace normalization, dimension scoring, aggregation, guidebook feedback,
  and report assembly pure; the facade retains input loading/redaction.
- Keep guidebook rendering, pattern-catalog merging, and advisory formatting
  runtime-owned over safe source text; legacy script aliases must not become
  server dependencies.
- Keep redaction primitives in `tmcp_runtime/safety`; the historical script
  module is a compatibility facade and must not be imported by runtime safety.
- Keep MCP framing/JSON-RPC, CLI output/error translation, and typed registry
  dispatch in `tmcp_runtime/adapters`; generic artifact-bundle persistence is
  runtime-owned while producer-specific output selection and capability checks
  remain adapter-owned.
- Keep optional AIOS execution in a redaction-aware runtime adapter; the legacy
  server may retain only compatibility wrappers and mutable test seams.
- Keep runtime-state/recompile orchestration in `tmcp_runtime.services.runtime`;
  inject source, cache-warning, and packet-composition callbacks from the
  adapter without moving filesystem or persistence authority into the service.
- Keep project-local session lifecycle orchestration in
  `tmcp_runtime.services.sessions`; inject the validated store factory and keep
  final response redaction at the adapter boundary.
- Keep generic artifact-bundle persistence in
  `tmcp_runtime.services.artifact_persistence`; inject redaction, path
  presentation, and verified storage callbacks without moving output-root
  selection or capability checks into the service.
- Keep receipt recording in `tmcp_runtime.services.receipts`; inject the clock,
  redaction, opaque identity, path creation, verified write, and public result
  callbacks while preserving adapter-owned seams.
- Keep global-promotion manifest assembly in
  `tmcp_runtime.services.global_promotion`; inject graph normalization,
  redaction, timestamp, and plan-building callbacks while retaining global-root
  selection, persistence gating, and cache authority in the adapter.
- Keep explain packet assembly and review-evidence parsing in runtime services;
  the adapter owns AIOS selection, source/cache access, persistence, and final
  response redaction.
- Treat legacy artifact migration as a read-only storage projection: normalize
  known old summaries into current contracts, prefer current files, never delete
  or rewrite source artifacts, and skip malformed inputs.
- Release composition/runtime/session dogfood lives in focused helpers; the
  main release checker remains an orchestration boundary and its size gate is clean.
- Artifact bundles accept only absent or empty destinations; reused artifact
  directories must use the verified per-file store rather than a bundle swap.
- Evaluation never re-reads a persisted plan's skill path while scoring; it
  composes the plan's redacted variant attachment through preharvested nodes.
- Artifact persistence is intentionally fail-closed without descriptor-relative
  no-follow primitives; a race-safe Windows implementation is required before
  cross-platform release claims can remain unconditional.
- Windows runs read-only and explicit fail-closed checks; the release-package
  smoke runs on every platform and verifies receipt denial where persistence is
  unavailable.
- MCP adapter/status safety coverage has a focused test module, keeping the
  server-domain test module below the repository source-size threshold.
- Packet sessions are explicit-only and latest-only: they require an absolute
  project root, do not replace an existing run, retain no global registry or
  history, and use a verified per-session lock for cooperative writers.
- Recompile policy is domain-owned and directly tested; source harvesting,
  composition, enrichment, and session persistence remain adapter/service work.
- Contextual composition policy, task-family routing, node ranking, and final
  packet construction/presentation are domain-owned and directly tested. Both
  composition owners are below the source-size limit.
- Family runtime transitions are domain-owned and directly tested; declared-read
  resolution and compose-node merging are now direct domain dependencies.
- The legacy standalone packet compiler is domain-owned; harvest classification
  consumes its behavior-atom catalog rather than maintaining a second copy.
- Review-profile vocabulary is domain-owned; standalone review and workflow
  recommendation consume its canonical selection and fallback policy.
- Review evidence, audit, remediation, validation, and rendering policy are
  domain-owned; the review adapter only orchestrates side effects and transport.
- Curated workflow catalog policy is domain-owned; recommendation, promotion,
  and global-cache selection no longer maintain adapter-local catalog copies.
- Workflow recommendation scoring is domain-owned and receives harvested-node
  text plus guidance-label mapping explicitly from the adapter.
- Adaptive workflow-pack construction and recommendation Markdown rendering are
  domain-owned; the adapter redacts results before persisting rendered artifacts.
- Promotion target selection and graph construction are domain-owned; graph
  edges derive workflow atoms from the canonical catalog, not harvested payloads.
- Global workflow activation is domain-owned; untrusted cache graphs contribute
  only validated canonical workflow IDs and retain advisory provenance.
- Composition provenance, shortcut eligibility, and rendering are domain-owned;
  recompile injects the domain renderer so both packet forms share one layout.
- Global promoted graphs and receipts are explicit opt-ins; no compose or runtime
  route reads them under the default `cache_policy=none`.
- Receipt construction and public acknowledgement are domain-owned. The adapter
  retains raw-to-redacted opaque identity, one UTC clock for receipt/path month,
  full nonce/path creation, persistence, cache ingress, and final redaction.
- Only literal `cache_policy=global` enables shared-cache reads; every other
  value is normalized to `none` before adapter, runtime, or compose use.
- Evaluation scoring receives a data-only composition callback from the adapter;
  it has no reverse import or introspection dependency on server internals.
- Skill-package, curated-template, and MCP-tool stability are separate scopes;
  their owners are frontmatter/package validation, the workflow catalog, and the
  public registry respectively.
- The domain-module size budget is test-enforced. Harvest, recommendation,
  promotion-planning, and review-plan policy are runtime-owned; the adapter
  retains source acquisition, redaction, and all durable-write authority.
- Optional-cache policy is runtime-owned and direct-tested. The adapter controls
  roots, catalog/schema injection, and persistence; storage owns bounded,
  redacted, TOCTOU-safe advisory cache ingestion.
- Optional AIOS execution remains adapter-only. Its child output, configured
  paths, optional composed packet, and execution errors are redacted before any
  MCP or CLI response is returned.
- `adapter=auto` never starts AIOS. Explicit AIOS requests reject known sensitive
  argument values until AIOS offers protected request input; decoded review
  evidence is checked before subprocess execution.
- Runtime state remains raw only inside the adapter until recompile/session work
  completes. Public runtime responses redact paths; callers must supply a real
  path instead of reusing a redacted packet location for an inline recompile.
- Runtime-state reduction is pure and receives only preharvested source nodes and
  cache warnings. The adapter retains cache-policy gating and all filesystem
  authority.
- Packet composition/source enrichment and recompile finalization are pure
  service work over adapter-supplied safe data. cache_policy=none discards
  injected cache inputs defensively; storage cache snapshots, TMCP_HOME redaction,
  raw-path checks, sessions, and final response redaction preserve their boundaries.
- Public compose and explain results redact complete response trees after internal
  session work, while the protected session record retains its existing redaction
  guarantees.

## Accumulated Context

### Roadmap Evolution
- 2026-07-10: Modernization audit identifies P0 package disclosure risk and
  proposes a parallel v2 runtime behind stable entrypoints.
- 2026-07-11: Milestone 0 closes the package-disclosure blocker; next work
  freezes public contracts before core migration.
- 2026-07-11: Milestone 1 freezes all public contracts and removes the stale
  `0.3.0` MCP initialize response; safe IO/storage extraction is next.
- 2026-07-11: M2 adds contained harvest reads, decoded-JSON/path redaction,
  exact evaluation input boundaries, and descriptor-safe artifacts; evaluation
  and remaining writers are pending migration.
- 2026-07-11: Evaluation now uses data-only composition and safe artifacts;
  review, recommendation, promotion, cache, and receipt writers remained.
- 2026-07-11: Adversarial review removed a plan-path probe and surfaced the
  Windows secure-persistence gap; both are explicit M2 release conditions.
- 2026-07-11: GitHub Actions validation was restored after a job-level
  `runner.temp` context reference prevented every matrix job from scheduling.
- 2026-07-11: All remaining durable writers and global cache reads use the safe
  storage boundary; compatibility docs now distinguish portable analysis from
  secure persistence, with Windows intentionally failing write requests closed.
- 2026-07-11: Adversarial hardening makes auto review standalone, rejects
  symlink-derived default writes, bounds and canonicalizes cache input, treats
  Windows junctions as links, and runs portable package verification on Windows.
- 2026-07-12: M3 adds an explicit project-local compose → full-recompile
  session path while retaining inline previous-packet compatibility; a fresh
  adversarial pass closes relative-root and forged-lineage findings, then
  `6864350` separates its release dogfood into focused composition/session helpers;
  `401e125` moves deterministic recompile policy and `2eedd09` moves contextual
  composition policy behind domain boundaries;…
_(truncated)_

## Next Command

```bash
# Monitor the published v0.5.0 release surfaces; no additional publication action is pending.
```
