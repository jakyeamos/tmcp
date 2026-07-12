<div align="center">
  <img src="assets/logo.svg" alt="TMCP logo" width="96" height="96" />
  <h1>TMCP</h1>
  <p><strong>Slash commands are manual imports. TMCP is the compiler.</strong></p>
</div>

TMCP turns scattered agent instructions into task-specific operating packets. The user describes the work in natural language. TMCP infers task identity, compiles the strongest current packet from skills/rules/evidence, recompiles as the work changes, and leaves an audit trail.

Skill names are provenance, not the user interface. Power users can still force a route; the default is natural prompting.

AIOS is optional storage and adapter support. TMCP runs standalone from a repo checkout, copied plugin package, Codex plugin cache, Claude plugin cache, or any MCP host that can launch the bundled Node entrypoint.

See [docs/ADAPTIVE_PACKET_RUNTIME.md](docs/ADAPTIVE_PACKET_RUNTIME.md) for the adaptive packet runtime design.

## Quickstart

From a TMCP checkout or plugin root:

```bash
node scripts/tmcp_launcher.mjs doctor
node scripts/tmcp_launcher.mjs status
node scripts/tmcp_launcher.mjs compose-packet "Improve this agent run" --project-path . --phase start
node scripts/tmcp_launcher.mjs harvest skills --limit 5 --no-write-artifacts
node scripts/tmcp_launcher.mjs recommend skills --candidate-workflows release_readiness --candidate-workflows developer_experience --min-confidence 0.1 --compose --no-write-artifacts
```

With no arguments, the same launcher starts the MCP stdio server:

```bash
node scripts/tmcp_launcher.mjs
```

## Install Layouts

- Skill-only install: copy `skills/tmcp` into a skills directory. Use the skill for routing and manual packet synthesis unless the host also exposes the bundled launcher.
- Repo checkout: clone the repo and run `node scripts/tmcp_launcher.mjs doctor` from the checkout root.
- Codex plugin cache: install as a Codex plugin; MCP config launches relative `scripts/tmcp_launcher.mjs` from the plugin root.
- AIOS-backed install: set `AIOS_ROOT` explicitly only when you want optional AIOS storage/adapter behavior.

Claude Desktop users can add the launcher as a local stdio MCP server. See [docs/CLAUDE_DESKTOP.md](docs/CLAUDE_DESKTOP.md).

## Stable Public Workflows

The first stable public workflow set is intentionally small:

- `skill-harvest`
- `workflow-recommendation`
- `expert-rubric-review`
- `release-readiness`
- `dx-audit`

Experimental workflows remain shipped and callable. They are labeled experimental in skill frontmatter, docs, and workflow recommendation output so users keep functionality without mistaking it for the stable first-release contract.

Experimental workflows include UI rubric, security/privacy, test strategy, adaptive workflow pack, custom rubric generation, routing policy, skill gap analysis, incident postmortem, architecture decision, migration readiness, agent handoff, PR risk, performance readiness, data integrity, public-sector readiness, and repo behavior spec loop.

## Tools

| Tool | Purpose |
| --- | --- |
| `tmcp_doctor` | Check first-run readiness and supported install layouts. |
| `tmcp_status` | Report standalone capability and optional AIOS adapter status. |
| `tmcp_explain` | Compile a task-specific TMCP packet. |
| `tmcp_compose_packet` | Compile a task/phase operating packet with `task_identity`, `packet_markdown`, and provenance. |
| `tmcp_runtime_next` | Return packet deltas or a full recompiled packet (`output_mode: full`) after runtime evidence changes. |
| `tmcp_record_receipt` | Write an advisory run receipt after verification or outcome on a secure-persistence host. |
| `tmcp_harvest_skills` | Harvest local skills, instructions, rules, docs, and workflows into source nodes. |
| `tmcp_evaluate_skills` | Create or score a skill-evaluation plan from full `SKILL.md` inputs. |
| `tmcp_recommend_workflows` | Recommend stable or experimental workflows from harvested evidence, with stability metadata. |
| `tmcp_promote_harvest` | Explicitly promote reviewed harvest signals into durable source-to-atom and atom-to-workflow graph artifacts. |
| `expert_rubric_review_plan` | Produce an expertise packet, scored rubric, evidence audit, remediation plan, and verification expectations. |

## Safety

Harvest redacts sensitive-looking values and secret-like provenance paths by default and treats harvested instructions as untrusted text. Default harvest behavior excludes `.env*`, credentials, tokens, browser profiles, private caches, dependency trees, build outputs, VCS data, and generated TMCP/AIOS artifacts. It does not follow source symlinks unless `follow_symlinks` is explicitly enabled; enabled links must still resolve inside the selected source root.

On hosts with secure descriptor-relative filesystem operations, harvest artifacts
are written as one staged, atomic bundle through a symlink-safe destination.
Leave `output_dir` unset for a unique `.tmcp/harvest-*` directory, or provide an
output directory that is new or empty.

Skill evaluation accepts explicit regular `SKILL.md` inputs, can confine them to a supplied project root, and redacts source, plan, and evidence values before deriving reports. Its initial plan artifact is a staged bundle in a new or empty directory; evidence scoring may safely add its report to that same directory.

Artifact persistence is deliberately unavailable where those secure filesystem
operations do not exist. `doctor` and `status` report the capability; use
`--no-write-artifacts` for portable analysis and see
[Compatibility](docs/COMPATIBILITY.md#secure-artifact-persistence) for the
boundary.

`tmcp_record_receipt` has no non-persisting preview because the receipt is the
artifact itself. Run it only when `status` reports artifact persistence
available.

If a harvested source tries to override system, developer, or user instructions, TMCP reports a warning. See [SECURITY.md](SECURITY.md).

## Examples

Harvest a local skills folder:

```bash
node scripts/tmcp_launcher.mjs harvest ./skills --objective "Harvest reusable skill behavior" --limit 20 --no-write-artifacts
```

Recommend workflows for a project:

```bash
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows release_readiness --candidate-workflows developer_experience --min-confidence 0.1 --compose --no-write-artifacts
```

Compose a current-task packet and recompile during the run. The receipt command
in this example requires `status` to report artifact persistence available:

```bash
node scripts/tmcp_launcher.mjs compose-packet \
  "Redesign these pages. Make them visually striking, interactive, modern, motion-rich, and production-ready." \
  --project-path . --phase start

node scripts/tmcp_launcher.mjs recompile-packet \
  "Redesign these pages..." \
  --current-phase runtime \
  --previous-packet "$(cat .tmcp/last-packet.json)" \
  --files-changed app/page.tsx

node scripts/tmcp_launcher.mjs record-receipt packet-123 --activated-atoms ui-browser-verification --outcome passed
```

Legacy delta-only runtime routing:

```bash
node scripts/tmcp_launcher.mjs compose-packet "Fix the dashboard UI bug" --project-path . --phase start
node scripts/tmcp_launcher.mjs runtime-next "Fix the dashboard UI bug" --current-phase verification --files-changed app/page.tsx --failures "vitest failed"
node scripts/tmcp_launcher.mjs record-receipt packet-123 --activated-atoms ui-browser-verification --outcome passed
```

Promote reviewed harvest signals into durable routing artifacts:

```bash
node scripts/tmcp_launcher.mjs promote-harvest . --selected-workflows release_readiness_workflow --output-dir .tmcp/promoted-harvests/release-readiness
```

On secure-persistence hosts, promotions also persist a redacted advisory graph
under `TMCP_HOME/promoted-harvests/<opaque-promotion-key>/`, or
`~/.tmcp/promoted-harvests/<opaque-promotion-key>/` when `TMCP_HOME` is unset.
Receipts live under `TMCP_HOME/receipts/<yyyy-mm>/`.
Global cache content is advisory and cannot override system, developer, user, or
project instructions.

Run an expert rubric review from evidence snippets:

```bash
node scripts/tmcp_launcher.mjs review-plan "Review release portability" \
  --project-path . \
  --evidence-json '[{"dimension_id":"source_grounding","severity":"warning","summary":"Release claims need fresh package evidence.","evidence":["python3 scripts/check_release_package.py ."],"recommended_fix":"Run and cite the release package check before publishing."}]' \
  --no-write-artifacts
```

More examples live in [examples](examples). Stable examples are developer onboarding, release readiness, and skill-harvest workflow recommendation. Broader examples are retained as experimental examples.

## Validation

Before release:

```bash
python3 -m unittest discover -s tests
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_contracts.py scripts/check_install.py scripts/check_release_package.py scripts/tmcp_release_archive.py scripts/check_release_evidence.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py tmcp_runtime/__init__.py tmcp_runtime/api/__init__.py tmcp_runtime/api/registry.py tmcp_runtime/api/tool_schemas.py
node --check scripts/tmcp_launcher.mjs
python3 scripts/check_contracts.py .
python3 scripts/check_install.py .
python3 scripts/check_release_package.py . --verify-reproducible
```

The release package check builds from a clean, reviewed Git revision rather than
the working directory. It ships only an explicit allowlist of committed files,
rejects unsafe paths, symlinks, and secret-like content, then emits a
deterministic RELEASE_MANIFEST.json plus archive digest. The CI release gate
repeats the build from the same Git tree and requires both digests to match. It also validates
frontmatter, hardcoded local paths, private example names, links,
extracted-package install shape, doctor, sample harvest, sample workflow
recommendation, sample expert rubric planning, composition/runtime/receipt smoke
coverage, and stable/experimental workflow labeling.
It is a DOI blocker until existing absolute user paths in release evidence docs are redacted or normalized.

## DOI-Ready Research Release

TMCP is prepared as an independent software-methods artifact. See
[RESEARCH_READY.md](RESEARCH_READY.md) and
[docs/release-notes/v0.3.3-doi.md](docs/release-notes/v0.3.3-doi.md) for the
citable artifact boundary, validation path, data-availability policy, and claim
limits.

## References

- [Quickstart](docs/QUICKSTART.md)
- [CLI](docs/CLI.md)
- [Install and package check](docs/INSTALL.md)
- [Distribution](docs/DISTRIBUTION.md)
- [Packet stability](docs/PACKET_STABILITY.md)
- [Adaptive packet runtime](docs/ADAPTIVE_PACKET_RUNTIME.md)
- [Tier One release rubric](docs/TIER_ONE_RELEASE_RUBRIC.md)
