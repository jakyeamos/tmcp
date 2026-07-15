# Changelog

## 0.5.5 - 2026-07-15

- Treat a clean Codex native marketplace checkout pinned to the active release
  ref and commit as a valid marketplace surface even when the checkout has
  Codex's install marker and non-package source files.
- Preserve native marketplace ownership during runtime sync, reject stale or
  dirty native checkout provenance, and keep generated-snapshot parity checks
  for non-native surfaces.

## 0.5.4 - 2026-07-15

- Pinned the Claude marketplace plugin source to the immutable release tag and
  made the runtime manager reject unpinned marketplace sources for modern
  releases.
- Recorded marketplace provenance in each runtime manifest so generated cache
  and marketplace surfaces cannot silently drift from the active package.
- Preserved installation of 0.5.3 marketplace metadata for offline rollback
  while requiring new releases to use release-tag provenance.

## 0.5.3 - 2026-07-15

- Fixed the Node launcher entrypoint guard when the launcher is invoked through
  the versioned runtime's `active` symlink or a compatibility alias.
- Added a regression test for symlinked launcher execution so status, doctor,
  and list-tools commands reach the bundled Python CLI.

## 0.5.2 - 2026-07-15

- Fixed central-runtime archive validation for deterministic release archives
  that contain `tmcp/<file>` entries without an explicit `tmcp/` directory
  member. The published 0.5.1 artifact remains retained for rollback evidence;
  0.5.2 is the supported archive-install release.

## 0.5.1 - 2026-07-15

- Added a version-pinned central runtime manager with immutable installs,
  atomic active/rollback switching, generated Codex/Claude cache sync, digest
  parity checks, and skill/runtime mismatch diagnostics.
- Kept repository-local instructions as overlays and documented the legacy
  runtime alias as a checked compatibility surface.

## 0.5.0 - 2026-07-13

- Changed AIOS dispatch so `auto` stays standalone, while explicit `aios` requests reject known sensitive values until a protected request-input protocol is available.
- Completed the 0.5.0 compatibility migration: runtime ownership is converged
  behind adapters and services, explicit state effects are documented, and
  legacy promotion summaries have a read-only migration path.

## 0.4.0 - 2026-07-07
- Added experimental `tmcp_evaluate_skills` with plan and score modes for full-skill behavioral evaluation, static anti-pattern review, A/B variant matrices, dimension scorecards, guidebook artifacts, and advisory harvest feedback without auto-promotion.
- Wired `tmcp_harvest_skills` to emit per-source `skill_eval_advisories` and top-level warnings from the evaluation anti-pattern catalog (`verification no-op`, overbroad triggers, precedence hazards, and related patterns).
- Packet inclusion scoring now diffs `tmcp_compose_packet` output against per-skill `packet_inclusion_contracts` instead of trace-only approximation.
- Added `tmcp-skill-evaluation-plan-v0.1`, `tmcp-skill-evaluation-report-v0.1`, and `tmcp-skill-eval-trace-v0.1` schemas plus seed guidebook and pattern catalog docs.
- Added first-class `task_identity` on composed and runtime packets via deterministic route-catalog scoring (`scripts/tmcp_route_catalog.py`).
- Added `compiled_from` provenance and `packet_markdown` audit rendering on every `tmcp_compose_packet` response.
- Added `tmcp_runtime_next` `output_mode=full` and `recompile-packet` CLI alias for full packet recompilation with `packet_diff`, `recompile_reason`, and audit markdown.
- Added `tmcp-recompiled-packet-v0.1` schema and agent `proposed_changes` validation against the route catalog.
- Added route-aware compose scoring, scoped-seed auto-matching via `route_affinity` / `objective_patterns`, `shortcut_candidate` provenance on composed packets, and `examples/seeds/frontend-redesign-runtime.json`.
- Updated README, skill contract, concepts, quickstart, and golden adaptive-runtime fixtures for the compiler-first agent loop.
- Added declared load-path extraction during harvest so skills that say `Search product-decisions/...` or `Check coverage-gaps.md` publish `routing_metadata.declared_loads`.
- Added compose-time declared load resolution with surface-aware narrowing, so runtime skills pull relevant decision-library files into `required_reads` and packet citations without flattening the whole family.
- Extended `scoped-packet-seeds` with `loads`, `chains_before`, `chains_after`, and `do_not_activate_with` for opt-in skill-family orchestration.
- Added router-aware compose selection that suppresses sibling skills and support docs unless explicitly named, while preserving router context and emitting `family_context` in composed packets.
- Fixed scoped packet seed harvesting to parse structural JSON before redaction so `.agents/...` source paths remain usable.
- Added `phase_transitions` on scoped packet seeds and family-aware `tmcp_runtime_next` deltas with `suggested_phase`, `suggested_skills`, deferred siblings, and next-step required reads.

## 0.3.3 - 2026-07-04

- Added Codex MCP discovery-gap diagnostics and skill guidance so agents can continue through the TMCP CLI when `tool_search` does not expose plugin MCP tools.
- Added scoped packet seed parsing for `tmcp-scoped-packet-seeds-v0.1` artifacts so curated seeds become first-class virtual `scoped_packet_seed` source nodes.
- Added `recommended_scoped_packet_seeds` to workflow recommendations and adaptive workflow packs so selectors can recommend exact curated seed IDs before falling back to generic workflow advice.
- Added scoped seed promotion-preview graph output with raw-source, behavior-atom, and verification-expectation edges while preserving proposal-only promotion requirements.
- Added domain labels for writing, spec-grilling, and wayfinding scoped seeds to make overlap analysis more explainable.
- Fixed file-root harvest identity so multiple direct `SKILL.md` inputs no longer collapse into one relative-path source node.
- Excluded source-repo release evidence and MCP Registry draft metadata from generated release packages so artifact hashes remain stable after evidence is finalized.
- Tightened workflow selector evidence scoring and overlap diagnostics so generic UI/default workflow matches are secondary when stronger scoped evidence is present.
- Added regression coverage for scoped seed harvesting, recommendation, promotion preview, raw skill evidence boundaries, workflow overlap reporting, selector scoring, and file-root identity.

## 0.3.2 - 2026-07-04

- Added composable skill packets through `tmcp_compose_packet`, `tmcp_runtime_next`, `tmcp_record_receipt`, and `--compose` support on explain/recommend.
- Added advisory global cache support for promoted harvest graphs and run receipts.
- Added deterministic routing metadata extraction so harvested skills can contribute command references, triggers, phase hints, boundaries, stop conditions, and verification gates.
- Added golden and release-package smoke coverage for composition, runtime adaptation, receipts, global cache behavior, and compatibility of legacy outputs.
- Made TMCP packaging portable-first: generic MCP config no longer sets `AIOS_ROOT`, `tmcp_doctor` documents skill-only, repo checkout, Codex plugin cache, and AIOS-backed layouts, and public docs avoid personal-machine paths.
- Split the main TMCP skill into a concise router plus progressive-disclosure references for concepts, CLI usage, workflows, and the optional AIOS adapter.
- Preserved all existing workflows while labeling the stable public set and marking non-stable router skills as experimental.
- Added workflow stability metadata to recommendations, templates, rubric seeds, workflow instances, adaptive packs, and custom workflow ideas.
- Strengthened harvest safety with broader default exclusions, untrusted-source metadata, and warnings for harvested text that attempts to override higher-priority instructions.
- Expanded release package validation to check frontmatter/status, hardcoded user paths, private example names, Markdown links, doctor, harvest, workflow recommendation, and expert rubric smoke runs.
- Accepted the successful `main` workflow run as hosted release evidence for this release by explicit release-owner override.

## 0.3.1 - 2026-07-02

- Excluded local `.aios/`, `.codex/`, and `.quality-runner/` artifact directories from generated release packages.
- Removed the environment-sensitive fake-AIOS adapter unit test and ignored local Codex/Quality Runner artifact directories.
- Added `evidence_contract` and `evidence_diagnostics` to expert rubric review results so coarse `evidence_json` records are reported before they produce uncited, low-value findings.

## 0.3.0 - 2026-06-29

- Added the adaptive workflow expansion: eight default workflow router skills for incidents, architecture decisions, test strategy, migrations, data integrity, agent handoffs, PR risk, and performance readiness.
- Added adaptive/meta router skills for workflow packs, custom rubric generation, routing-policy generation, and skill-gap analysis.
- Expanded `tmcp_recommend_workflows` to emit a first-class `adaptive_workflow_pack` artifact with schema `tmcp-adaptive-workflow-pack-v0.1`.
- Added additive recommendation fields for `custom_workflow_ideas`, default workflow `template`, and candidate `workflow_instance`.
- Added source-backed custom workflow ideas, routing triggers, required evidence lists, documented process gaps, and approval-gated next workflow selection.
- Updated docs, examples, install checks, and release-package validation for the adaptive workflow-pack surface.

## 0.2.5 - 2026-06-27

- Generalized profile coverage requirements beyond UI reviews so security/privacy, public-sector, developer-experience, and general reviews can reject off-profile evidence and request a profile-coverage evidence slice.

## 0.2.4 - 2026-06-27

- Added packet substance checks that distinguish process-only TMCP scaffolding from source-backed domain playbooks.
- Review plans now harvest target project sources by default before synthesizing rubrics.
- Added a public-sector readiness rubric profile for government/compliance/readiness audits.
- Review outputs now surface fallback policy when TMCP lacks substantive domain guidance and should derive rubric content from target repo evidence.

## 0.2.3 - 2026-06-27

- Added a direct CLI surface through `node scripts/tmcp_launcher.mjs <command>` for doctor, status, explain, harvest, recommend, and review-plan workflows.
- Added `expert-ui-rubric`, `tmcp-expert-ui-rubric`, `expert-ui-review`, `tmcp-ui-rubric`, and `ui-rubric` CLI aliases for the TMCP expert UI rubric workflow.
- Improved CLI argument handling so schema array flags accept both single and repeated values.
- Pruned generated `.aios` and `.tmcp` run artifacts from default skill harvests.
- Narrowed high-entropy redaction to avoid corrupting normal markdown workflow links.
- Expanded agent-facing CLI and TMCP routing instructions so missing MCP tool exposure does not downgrade TMCP requests to generic UI audits.

## 0.2.2 - 2026-06-26

- Added `tmcp_recommend_workflows` to infer coding-quality priority signals from harvested skill sources and recommend custom expert workflows with evidence.
- Added workflow recommendation examples and updated quickstart/docs.

## 0.2.1 - 2026-06-26

- Added `tmcp_doctor` for first-run readiness checks across Codex, Claude Code, Claude Desktop, and plain MCP clients.
- Added quickstart, marketplace matrix, packet stability policy, and machine-readable packet schema.
- Added non-UI example workflows for developer onboarding, security/privacy harvest review, and release readiness planning.

## 0.2.0 - 2026-06-26

- Added standalone TMCP MCP server with packet explain, skill harvest, status, and expert rubric remediation tools.
- Added Codex plugin metadata, marketplace-ready assets, and cross-platform Node launcher.
- Added Claude Code plugin metadata and GitHub-hosted Claude marketplace catalog.
- Added Claude Desktop manual MCP install documentation.
- Added release/package validation for clean-copy installs.
