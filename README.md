# TMCP

TMCP is a standalone skill-packet workflow plugin. It compiles task-specific packets from local instructions and evidence, harvests reusable skill behavior from arbitrary repositories, and produces expert rubric remediation plans.

AIOS is optional. When `AIOS_ROOT` points to an AIOS checkout, the plugin can use AIOS for richer graph traversal and persistence. Without AIOS, the MCP server still supports packet compilation, skill harvest, expert rubric planning, and artifact writing.

## Install

TMCP is packaged for multiple runtimes:

- Codex plugin: install from the Codex plugin store or local personal marketplace.
- Claude Code plugin: install from the GitHub-hosted Claude marketplace once the repository is public.
- Claude Desktop: add TMCP as a local stdio MCP server.
- Raw MCP server: run `node scripts/tmcp_launcher.mjs` from a local checkout.

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md), [docs/CLAUDE_CODE.md](docs/CLAUDE_CODE.md), and [docs/CLAUDE_DESKTOP.md](docs/CLAUDE_DESKTOP.md).

## Tools

- `tmcp_status`: reports standalone capability and optional AIOS adapter availability.
- `tmcp_explain`: compiles a task-specific TMCP packet.
- `tmcp_harvest_skills`: harvests local skills, agent instructions, editor rules, repository process docs, and workflow docs into source nodes.
- `expert_rubric_review_plan`: creates an expertise packet, scored rubric, audit report, remediation plan, and approval-gated implementation handoff.

## Skill Harvest

Harvest is setup-agnostic. It does not assume Codex, Claude, AIOS, or a specific home directory layout.

Default harvest inputs include:

- `SKILL.md`
- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `.cursor/rules`
- `.github`
- `docs`
- `planning`
- `workflows`
- markdown process docs

Default exclusions include dependency, build, cache, VCS, coverage, and generated plugin-cache directories.

Sensitive-looking values are redacted by default before excerpts, frontmatter, keywords, or artifact output are returned. Redaction covers common API keys, bearer tokens, GitHub tokens, AWS access keys, private key blocks, secret assignments, and long high-entropy strings.

## Local Verification

Run the standard-library test suite:

```bash
python3 -m unittest discover -s tests
```

Run a syntax check:

```bash
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
```

Run the install-shape check:

```bash
python3 scripts/check_install.py .
```

Run the release-package check:

```bash
python3 scripts/check_release_package.py .
```

Validate Claude Code packaging:

```bash
claude plugin validate .
```

The MCP entrypoint is `node scripts/tmcp_launcher.mjs`. The launcher selects Python in this order:

- `TMCP_PYTHON`, when explicitly set.
- Windows: `py -3`, then `python`, then `python3`.
- macOS/Linux: `python3`, then `python`.

## Release Rubric

Tier One release readiness is tracked in [docs/TIER_ONE_RELEASE_RUBRIC.md](docs/TIER_ONE_RELEASE_RUBRIC.md).
