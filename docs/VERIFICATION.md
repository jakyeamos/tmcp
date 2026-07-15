# Verification Record

## 2026-07-15 0.5.2 Archive Install Fix

The 0.5.2 patch fixes central-runtime validation for deterministic archives
whose files are rooted at `tmcp/` without a standalone root-directory member.
The focused regression test now creates that exact archive shape and verifies
digest-pinned installation. The published 0.5.1 archive was installed with
the patched validator as a pre-release smoke check. The 0.5.2 hosted PR
matrix `29452086899` and the evidence-pointer rerun `29452217943` passed across
Ubuntu, macOS, and Windows for Python 3.10 and 3.13. The tagged artifact was
then verified by tag run `29452495677` at merge commit
`ba093f5f1c0396d90bfcd7742a8cf3f62b4245b6`.

Final artifact proof:

- `/private/tmp/tmcp-v0.5.2.tar.gz` SHA-256:
  `f6e39ab52c82739474fc0a0c1942828f215f86dde8df84bb0b161fd241e5ec63`.
- GitHub Release: `https://github.com/jakyeamos/tmcp/releases/tag/v0.5.2`.
- Downloaded public asset matched the local artifact byte-for-byte and GitHub's
  asset digest.
- MCP Registry draft now carries the same `fileSha256`; publication is the
  remaining external release step.

## 2026-07-15 0.5.1 Central Runtime Migration

The 0.5.1 migration adds the versioned central runtime, immutable install
manifests, generated cache synchronization, active/previous rollback state, and
runtime/skill parity diagnostics. Public MCP tools and the portable relative
launcher remain unchanged. Repository-local instructions and evidence remain
consumer overlays.

Local proof completed before hosted verification:

```bash
node --check scripts/tmcp_runtime.mjs
python3 -m unittest tests.test_tmcp_runtime -v
python3 -m unittest discover -s tests
python3 scripts/release_package_compile.py .
python3 scripts/check_install.py .
python3 scripts/check_contracts.py .
python3 scripts/check_release_evidence.py .
```

The focused runtime suite covers archive digest pinning, immutable install and
activation, generated-surface refresh, skill mismatch detection, corrupt-state
fail-closed behavior, and offline rollback. The first hosted migration PR matrix
run `29450815213` passed all seven jobs across Ubuntu, macOS, and Windows for
Python 3.10 and 3.13. The evidence record now points to that run; a second
evidence-pointer verification is required before merge.

A clean pre-tag package check at source commit `e2d7583` produced
`/private/tmp/tmcp-v0.5.1-final.tar.gz` with SHA-256
`489bf65bc86062fff2e76a9660f54d7df5056f732f1c2af00d9161ec4da5828e`; its repeat
build matched. Because the archive manifest embeds its source commit, the
published artifact must be rebuilt from the final merge tag. The final tagged
artifact was published at
`https://github.com/jakyeamos/tmcp/releases/tag/v0.5.1` with SHA-256
`feafe836a8d1ac06611612ecca1aaca9b270091a39df6722fe4de7d598b881dd`.
The first install attempt against that public artifact exposed the archive
root-entry validation defect fixed by 0.5.2, so 0.5.1 is retained for rollback
evidence and 0.5.2 is the supported install target.

## 2026-07-13 0.5.0 Compatibility Release Candidate

The 0.5.0 compatibility candidate updates the canonical registry, Codex and
Claude manifests, marketplace metadata, MCP Registry draft, citation metadata,
and public-contract fixture together. The post-cutover hosted matrix passed in
PR run `29285497867`; final evidence-pointer rerun `29285802846` also passed.

```bash
python3 -m unittest discover -s tests
ruff check scripts tmcp_runtime tests
python3 scripts/check_contracts.py .
python3 scripts/check_install.py .
python3 scripts/check_release_evidence.py .
python3 scripts/check_release_package.py . --verify-reproducible
```

Date: 2026-07-13

Plugin version: `0.5.0+codex.20260713210431`

## 2026-07-07 0.4.0 Release Candidate

Commands run for this change:

```bash
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/check_release_evidence.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py scripts/tmcp_route_catalog.py scripts/tmcp_skill_evaluate.py
node --check scripts/tmcp_launcher.mjs
python3 -m unittest discover -s tests
python3 scripts/check_install.py .
python3 scripts/check_release_package.py . --output /private/tmp/tmcp-v0.4.0.tar.gz
shasum -a 256 /private/tmp/tmcp-v0.4.0.tar.gz
python3 scripts/check_release_package.py . --output /private/tmp/tmcp-v0.4.0.second.tar.gz
shasum -a 256 /private/tmp/tmcp-v0.4.0.second.tar.gz
```

Results:

- Version metadata updated for `0.4.0` in the Codex plugin, Claude plugin, Claude marketplace, MCP Registry draft, and hosted verification tag filters.
- Unit tests: pass (`120` tests, `21` subtests).
- Install check: pass.
- Release package check: pass.
- Deterministic package check: a second generated artifact at `/private/tmp/tmcp-v0.4.0.second.tar.gz` produced the same SHA-256 (`a24fb730fb50bb6249f47918f01cc4d82cb0bd1346c4edd32908916edaecb149`).
- Release package artifact: `/private/tmp/tmcp-v0.4.0.tar.gz` with digest `sha256:a24fb730fb50bb6249f47918f01cc4d82cb0bd1346c4edd32908916edaecb149`.
- Release evidence checker: pass for active version `0.4.0` using hosted main `verify.yml` run `28871545129` at `b0e68c0cc2392a967598f15fee41153ac8e44ce2`.
- Residual risks: `tmcp_evaluate_skills` remains experimental; full recompile mode is additive and should not break delta-only `tmcp_runtime_next` consumers.

## 2026-07-07 0.4.0 Published Release

Commands run for this change:

```bash
gh pr merge 1 --merge
git pull origin main
gh run watch 28871545129 --repo jakyeamos/tmcp --exit-status
python3 scripts/check_release_package.py . --output /private/tmp/tmcp-v0.4.0.tar.gz
shasum -a 256 /private/tmp/tmcp-v0.4.0.tar.gz
git tag -a v0.4.0 -m "TMCP 0.4.0"
git push origin v0.4.0
gh release create v0.4.0 /private/tmp/tmcp-v0.4.0.tar.gz --repo jakyeamos/tmcp --title "TMCP 0.4.0" --notes "TMCP 0.4.0 ships the compiler-first adaptive packet runtime with task identity, full recompile mode, route-aware compose, declared loads, skill-family orchestration, and experimental tmcp_evaluate_skills."
gh run list --repo jakyeamos/tmcp --workflow verify.yml --branch v0.4.0 --limit 5 --json databaseId,status,conclusion,event,headBranch,headSha,displayTitle,url,createdAt,updatedAt
curl -sL https://github.com/jakyeamos/tmcp/releases/download/v0.4.0/tmcp-v0.4.0.tar.gz -o /private/tmp/tmcp-v0.4.0.release.tar.gz
shasum -a 256 /private/tmp/tmcp-v0.4.0.release.tar.gz
```

Results:

- GitHub release published: `https://github.com/jakyeamos/tmcp/releases/tag/v0.4.0`.
- GitHub release asset `tmcp-v0.4.0.tar.gz` digest: `sha256:fab7d19af407c3c9ef41b3753545c9a48b83659214f18bac837e81d50187c5b7`.
- Tag verification run `28871784926` completed successfully for `v0.4.0` at commit `ed63ec796a48649b48e0dc2000c97f69569482b8`.
- Release evidence checker: pass for active version `0.4.0` using hosted tag `verify.yml` run `28871784926`.
- Release smoke from published asset: `check_install`, `doctor`, `status`, and `list-tools` passed from `/private/tmp/tmcp-v0.4.0.release-smoke/tmcp`.
- MCP Registry validation: `mcp-publisher validate mcp-registry/draft-server.json` passed.
- MCP Registry publish: blocked because the stored Registry JWT is expired; rerun `mcp-publisher login github` before `mcp-publisher publish mcp-registry/draft-server.json`.

---

Date: 2026-07-04

Plugin version: `0.3.3+codex.20260704154108`

## 2026-07-04 0.3.3 Release Candidate

Commands run for this change:

```bash
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/check_release_evidence.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
python3 -m json.tool .codex-plugin/plugin.json
python3 -m json.tool .claude-plugin/plugin.json
python3 -m json.tool .claude-plugin/marketplace.json
python3 -m json.tool mcp-registry/draft-server.json
python3 -m json.tool docs/RELEASE_EVIDENCE.json
TMCP_HOME=/private/tmp/tmcp-release-test-home python3 -m unittest discover -s tests
python3 scripts/check_release_package.py . --output /private/tmp/tmcp-v0.3.3.tar.gz
shasum -a 256 /private/tmp/tmcp-v0.3.3.tar.gz
python3 scripts/check_release_package.py . --output /private/tmp/tmcp-v0.3.3.second.tar.gz
shasum -a 256 /private/tmp/tmcp-v0.3.3.second.tar.gz
tar -tzf /private/tmp/tmcp-v0.3.3.tar.gz | rg '^tmcp/(mcp-registry|docs/VERIFICATION.md|docs/RELEASE_EVIDENCE.json)'
tar -tzf /private/tmp/tmcp-v0.3.3.tar.gz | rg '^tmcp/(README.md|scripts/check_release_package.py|docs/DISTRIBUTION.md|docs/TIER_ONE_RELEASE_RUBRIC.md)$'
gh run list --repo jakyeamos/tmcp --workflow verify.yml --branch main --limit 10 --json databaseId,status,conclusion,event,headBranch,headSha,displayTitle,url,createdAt,updatedAt
gh run watch 28711514414 --repo jakyeamos/tmcp --exit-status
gh run view 28711514414 --repo jakyeamos/tmcp --json status,conclusion,url,headSha,updatedAt,createdAt,event,displayTitle
gh run view 28711514414 --repo jakyeamos/tmcp --json jobs --jq '.jobs[] | [.name, .conclusion] | @tsv'
gh run list --repo jakyeamos/tmcp --workflow verify.yml --branch v0.3.3 --limit 10 --json databaseId,status,conclusion,event,headBranch,headSha,displayTitle,url,createdAt,updatedAt
gh run watch 28711603903 --repo jakyeamos/tmcp --exit-status
python3 scripts/check_release_evidence.py .
mcp-publisher validate mcp-registry/draft-server.json
claude plugin validate --strict .
gh release create v0.3.3 /private/tmp/tmcp-v0.3.3.tar.gz --repo jakyeamos/tmcp --title "TMCP 0.3.3" --notes "TMCP 0.3.3 promotes curated scoped packet seeds into first-class graph and recommendation nodes, adds scoped seed promotion-preview edges, tightens workflow selector overlap handling, fixes direct file-root harvest identity, and makes release packages deterministic with stable artifact hashes."
gh release view v0.3.3 --repo jakyeamos/tmcp --json tagName,targetCommitish,isDraft,isPrerelease,name,url,createdAt,publishedAt,assets
git tag -f -a v0.3.3 -m "TMCP 0.3.3" HEAD
git push origin v0.3.3 --force
gh release upload v0.3.3 /private/tmp/tmcp-v0.3.3.tar.gz --clobber --repo jakyeamos/tmcp
gh run list --repo jakyeamos/tmcp --workflow verify.yml --branch v0.3.3 --limit 5 --json databaseId,status,conclusion,event,headBranch,headSha,displayTitle,url,createdAt,updatedAt
curl -sL https://github.com/jakyeamos/tmcp/releases/download/v0.3.3/tmcp-v0.3.3.tar.gz -o /private/tmp/tmcp-v0.3.3.release.tar.gz
shasum -a 256 /private/tmp/tmcp-v0.3.3.release.tar.gz
mkdir -p /private/tmp/tmcp-v0.3.3.release-smoke
tar -xzf /private/tmp/tmcp-v0.3.3.release.tar.gz -C /private/tmp/tmcp-v0.3.3.release-smoke
python3 /private/tmp/tmcp-v0.3.3.release-smoke/tmcp/scripts/check_install.py /private/tmp/tmcp-v0.3.3.release-smoke/tmcp
node /private/tmp/tmcp-v0.3.3.release-smoke/tmcp/scripts/tmcp_launcher.mjs doctor --client codex --compact
node /private/tmp/tmcp-v0.3.3.release-smoke/tmcp/scripts/tmcp_launcher.mjs status --compact
node /private/tmp/tmcp-v0.3.3.release-smoke/tmcp/scripts/tmcp_launcher.mjs list-tools
git diff --check
```

Results:

- Version metadata updated for `0.3.3` in the Codex plugin, Claude plugin, Claude marketplace, MCP Registry draft, and hosted verification tag filters.
- Python compile, Node launcher syntax, JSON syntax checks, and `git diff --check`: pass.
- Full unit and MCP protocol suite: pass, 75 tests, with `TMCP_HOME` isolated to `/private/tmp/tmcp-release-test-home`.
- Release package check: pass, including extracted package install/test/smoke coverage, doctor, harvest, recommendation, expert-rubric, composition/runtime/receipt, frontmatter, link, hardcoded-path, and private-name gates.
- Release package artifact: `/private/tmp/tmcp-v0.3.3.tar.gz`.
- Release package SHA-256: `125cbd4b86c9c2bbc585b11ebe5a95674d71d7f567d81343421350168f54f38c`.
- Deterministic package check: a second generated artifact at `/private/tmp/tmcp-v0.3.3.second.tar.gz` produced the same SHA-256.
- Release package intentionally excludes `mcp-registry/`, `docs/VERIFICATION.md`, and `docs/RELEASE_EVIDENCE.json` so the registry draft and release evidence can record the package hash without self-reference; runtime package files such as `README.md`, `docs/DISTRIBUTION.md`, `docs/TIER_ONE_RELEASE_RUBRIC.md`, and `scripts/check_release_package.py` are present.
- MCP Registry draft validation: pass against `https://registry.modelcontextprotocol.io`.
- Claude Code marketplace validation: pass with `claude plugin validate --strict .`.
- Hosted `main` verification run `28711767260` completed successfully at commit `de185a1c62ba8bbb8fe928112832b653f0c6aea5`.
- Matrix jobs passed on Ubuntu, macOS, and Windows for Python 3.10 and 3.13.
- Release evidence checker: pass for active version `0.3.3`.
- Updated tag verification run `28711865883` completed successfully for `v0.3.3` at commit `de185a1c62ba8bbb8fe928112832b653f0c6aea5`.
- GitHub release published: `https://github.com/jakyeamos/tmcp/releases/tag/v0.3.3`.
- GitHub release asset `tmcp-v0.3.3.tar.gz` replaced with digest `sha256:125cbd4b86c9c2bbc585b11ebe5a95674d71d7f567d81343421350168f54f38c`.
- Downloaded public release asset SHA-256 matched `125cbd4b86c9c2bbc585b11ebe5a95674d71d7f567d81343421350168f54f38c`.
- Extracted public release asset smokes passed: install check, Codex doctor fallback diagnostics, status, and tools list.
- Folded-in scope: Codex MCP discovery-gap diagnostics and skill/docs guidance from `de185a1`.

## 2026-07-04 Post-Publish Marketplace And Registry Smokes

Commands run for this change:

```bash
codex plugin marketplace remove tmcp
codex plugin marketplace add jakyeamos/tmcp@v0.3.3
python3 -m json.tool /Users/jakyeamos/.codex/.tmp/marketplaces/tmcp/.codex-plugin/plugin.json
python3 /Users/jakyeamos/.codex/.tmp/marketplaces/tmcp/scripts/check_install.py /Users/jakyeamos/.codex/.tmp/marketplaces/tmcp
node /Users/jakyeamos/.codex/.tmp/marketplaces/tmcp/scripts/tmcp_launcher.mjs doctor --client codex --compact
node /Users/jakyeamos/.codex/.tmp/marketplaces/tmcp/scripts/tmcp_launcher.mjs status --compact
node /Users/jakyeamos/.codex/.tmp/marketplaces/tmcp/scripts/tmcp_launcher.mjs compose-packet "Improve release readiness" --project-path /private/tmp/tmcp-smoke-source --source-path /private/tmp/tmcp-smoke-source --phase start --cache-policy none --compact
claude plugin validate --strict .
claude plugin marketplace update tmcp
claude plugin update tmcp@tmcp
claude plugin list
claude plugin details tmcp
python3 /Users/jakyeamos/.claude/plugins/cache/tmcp/tmcp/0.3.3/scripts/check_install.py /Users/jakyeamos/.claude/plugins/cache/tmcp/tmcp/0.3.3
node /Users/jakyeamos/.claude/plugins/cache/tmcp/tmcp/0.3.3/scripts/tmcp_launcher.mjs doctor --client claude_code --compact
node /Users/jakyeamos/.claude/plugins/cache/tmcp/tmcp/0.3.3/scripts/tmcp_launcher.mjs status --compact
node /Users/jakyeamos/.claude/plugins/cache/tmcp/tmcp/0.3.3/scripts/tmcp_launcher.mjs explain "Review release readiness" --project-path /private/tmp/tmcp-smoke-source --adapter standalone --compact
node /Users/jakyeamos/.claude/plugins/cache/tmcp/tmcp/0.3.3/scripts/tmcp_launcher.mjs harvest /private/tmp/tmcp-smoke-source --limit 5 --no-write-artifacts --compact
node /Users/jakyeamos/.claude/plugins/cache/tmcp/tmcp/0.3.3/scripts/tmcp_launcher.mjs recommend /private/tmp/tmcp-smoke-source --candidate-workflows release_readiness --min-confidence 0.1 --no-write-artifacts --compact
mcp-publisher validate mcp-registry/draft-server.json
mcp-publisher login github
mcp-publisher validate mcp-registry/draft-server.json
curl -sL https://github.com/jakyeamos/tmcp/releases/download/v0.3.3/tmcp-v0.3.3.tar.gz -o /private/tmp/tmcp-v0.3.3.registry-check.tar.gz
shasum -a 256 /private/tmp/tmcp-v0.3.3.registry-check.tar.gz
mcp-publisher publish mcp-registry/draft-server.json
```

Results:

- Codex marketplace: old `tmcp` marketplace entry pinned to `v0.3.2` was removed; `jakyeamos/tmcp@v0.3.3` was added successfully.
- Codex installed marketplace root reports `.codex-plugin` version `0.3.3+codex.20260704154108`.
- Codex installed marketplace smokes passed: install check, Codex doctor fallback diagnostics, status, and composition.
- Claude Code marketplace validation: pass with `claude plugin validate --strict .`.
- Claude Code marketplace update: `claude plugin marketplace update tmcp` passed.
- Claude Code installed plugin update: `tmcp@tmcp` updated from `0.3.2` to `0.3.3`.
- Claude installed plugin inventory: 20 skills, one MCP server, and projected always-on cost about 865 tokens.
- Claude installed launcher smokes: doctor, status, explain, harvest, and release-readiness recommendation passed from the local Claude marketplace cache.
- MCP Registry draft digest was corrected to the folded `0.3.3` release asset SHA-256 `125cbd4b86c9c2bbc585b11ebe5a95674d71d7f567d81343421350168f54f38c`.
- MCP Registry validation: `mcp-publisher validate mcp-registry/draft-server.json` passed against `https://registry.modelcontextprotocol.io`.
- MCP Registry authentication: `mcp-publisher login github` completed successfully.
- MCP Registry publish: `mcp-publisher publish mcp-registry/draft-server.json` published `io.github.jakyeamos/tmcp` version `0.3.3`.

## 2026-07-04 Main Evidence And 0.3.2 Publish Prep

Commands run for this change:

```bash
gh run view 28694857109 --repo jakyeamos/tmcp --json status,conclusion,url,headSha,updatedAt
gh run view 28694857109 --repo jakyeamos/tmcp --json jobs --jq '.jobs[] | [.name, .conclusion] | @tsv'
git rev-list -n1 v0.3.1
git ls-remote --tags origin 'v0.3.1*'
gh release view v0.3.1 --repo jakyeamos/tmcp --json tagName,targetCommitish,isDraft,isPrerelease,name,url,createdAt,publishedAt,body
python3 -m unittest tests.test_release_evidence
python3 scripts/check_release_evidence.py .
python3 -m unittest discover -s tests
python3 scripts/check_release_package.py . --output /private/tmp/tmcp-v0.3.2.tar.gz
python3 scripts/check_install.py .
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/check_release_evidence.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
ruff check .
ruff format --check .
basedpyright
claude plugin validate .
git diff --check
```

Results:

- Hosted `main` verification run `28694857109` completed successfully at commit `749cb9958d15e8e494df4a9bd90c98943203e39d`.
- Matrix jobs passed on Ubuntu, macOS, and Windows for Python 3.10 and 3.13.
- Existing `v0.3.1` GitHub release points at commit `321fee69b16544b05167e46ff77c5c089c9657f7`, which predates the composition release work.
- Release-owner override accepts the successful `main` run as hosted release evidence, so the non-destructive publish path is a new `0.3.2` release rather than rewriting `v0.3.1`.
- Release evidence checker: pass for active version `0.3.2`.
- Release evidence unit tests: pass, 5 tests.
- Full unit and MCP protocol suite: pass, 62 tests.
- Release package check: pass, including extracted package install/test/smoke coverage; package artifact written to `/private/tmp/tmcp-v0.3.2.tar.gz`.
- Install shape check: pass; MCP `tools/list` passes without AIOS.
- Python compile, Node launcher syntax, Ruff lint, Ruff format, Basedpyright, Claude marketplace validation, and `git diff --check`: pass.

## 2026-07-04 Composition Release Hardening

Commands run for this change:

```bash
node scripts/tmcp_launcher.mjs compose-packet "Improve TMCP release readiness before release" --project-path . --source-path . --phase start --cache-policy global --limit 12 --compact
node scripts/tmcp_launcher.mjs runtime-next "Improve TMCP release readiness before release" --project-path . --current-phase verification --files-changed scripts/tmcp_mcp_server.py --files-changed scripts/check_release_package.py --files-changed scripts/check_install.py --files-changed tests/test_tmcp_workflow_recommendation.py --files-changed tests/test_tmcp_mcp_server.py --files-changed docs/RELEASE_EVIDENCE.json --commands-run "python3 -m unittest discover -s tests" --commands-run "python3 scripts/check_release_package.py ." --failures "python3 scripts/check_release_evidence.py . failed because hosted release evidence is pending" --latest-user-message "dogfood tmcp and iterate improvements until we are satisfied" --cache-policy global --compact
gh run list --repo jakyeamos/tmcp --workflow verify.yml --limit 20 --json databaseId,status,conclusion,event,headBranch,headSha,displayTitle,url,createdAt,updatedAt
gh run list --repo jakyeamos/tmcp --workflow verify.yml --branch v0.3.1 --limit 10 --json databaseId,status,conclusion,event,headBranch,headSha,displayTitle,url,createdAt,updatedAt
git ls-remote --tags origin v0.3.1
gh pr list --repo jakyeamos/tmcp --state all --limit 20 --json number,title,headRefName,baseRefName,state,url,updatedAt
ruff check .
ruff format --check .
python3 -m unittest tests.test_tmcp_mcp_server tests.test_tmcp_workflow_recommendation tests.test_release_evidence
python3 -m unittest discover -s tests
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/check_release_evidence.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
python3 scripts/check_install.py .
python3 scripts/check_release_package.py .
python3 scripts/check_release_evidence.py .
git diff --check
```

Results:

- Start-packet dogfood: pass; release-readiness composition cites `skills/tmcp-release-readiness/SKILL.md` only and does not activate PR-risk, repo-behavior, migration-readiness, performance-readiness, UI/browser, screenshot, or canonical-spreadsheet gates.
- Runtime dogfood: pass; pending hosted release evidence activates `explicit-evidence-gaps` rather than `debugging-regression`.
- GitHub hosted evidence discovery: no qualifying `verify.yml` pull request or `v0.3.1` tag run found. Remote tag `refs/tags/v0.3.1` exists.
- Targeted unit suites: pass, 60 tests.
- Full unit and MCP protocol suite: pass, 60 tests.
- Ruff lint and format checks: pass.
- Python compile: pass.
- Node launcher syntax: pass.
- Install shape check: pass; MCP `tools/list` includes composition/runtime/receipt tools.
- Release package check: pass; extracted package includes composition/runtime/receipt smoke coverage.
- Release evidence check: expected fail until hosted evidence records a successful pull request or `0.3.1`/`v0.3.1` tag run.
- `git diff --check`: pass.

## 2026-07-04 Portable Skill Package

Commands run for this change:

```bash
python3 -m unittest discover -s tests
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/check_release_evidence.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
ruff check .
ruff format --check .
python3 scripts/check_install.py .
python3 scripts/check_release_package.py .
node scripts/tmcp_launcher.mjs doctor --compact
node scripts/tmcp_launcher.mjs harvest skills --limit 5 --no-write-artifacts --compact
node scripts/tmcp_launcher.mjs recommend skills --candidate-workflows release_readiness --candidate-workflows developer_experience --min-confidence 0.1 --no-write-artifacts --compact
node scripts/tmcp_launcher.mjs recommend skills --candidate-workflows agent_handoff --min-confidence 0.1 --no-write-artifacts --compact
node scripts/tmcp_launcher.mjs review-plan "Review release portability" --project-path . --evidence-json '[]' --no-write-artifacts --compact
git diff --check
```

Results:

- Full unit and MCP protocol suite: pass, 45 tests.
- Python compile: pass.
- Node launcher syntax: pass.
- Ruff lint and format checks: pass.
- Install shape check: pass; MCP `tools/list` passes without AIOS.
- Release package check: pass from an extracted package, including frontmatter, hardcoded-user-path, private-name, markdown-link, doctor, harvest, workflow recommendation, expert-rubric, stable workflow, and experimental workflow gates.
- `tmcp doctor`: pass; reports the repo/plugin launcher, supported install layouts, optional AIOS adapter, and manual packet synthesis remediation when no launcher path is available.
- Sample harvest: pass; default exclusions include secrets, private caches, dependency trees, build outputs, VCS data, and generated TMCP/AIOS artifacts. Harvested text is marked untrusted.
- Stable recommendation smoke: pass; `release_readiness` and `developer_experience` recommendations include `stability: stable`.
- Experimental recommendation smoke: pass; explicit `agent_handoff` candidate remains callable and is labeled `stability: experimental`.
- Expert rubric review-plan smoke: pass; empty evidence produces `status: needs_evidence` with evidence-gap remediation instead of a false completed audit.
- `git diff --check`: pass.

Covered behavior:

- The canonical public command is `node scripts/tmcp_launcher.mjs doctor`.
- Main `skills/tmcp/SKILL.md` is 83 lines and delegates details to progressive-disclosure references.
- TMCP is described as source nodes -> behavior atoms -> packets -> workflows, with AIOS documented only as an optional adapter.
- Stable public workflows are documented and labeled stable.
- Experimental workflows are preserved, shipped, callable, documented separately, and labeled experimental.
- Workflow outputs expose the expected sections: sources inspected, skipped sources and why, packet summary, extracted behavior atoms, evidence gaps, recommendation or remediation plan, and verification expectations.
- Package validation now checks release portability from an extracted package before release.

## 2026-07-04 Hosted Release Evidence Gate

Commands run for this change:

```bash
python3 -m unittest tests.test_release_evidence
python3 -m py_compile scripts/check_release_evidence.py tests/test_release_evidence.py
python3 -m unittest discover -s tests
python3 scripts/check_release_package.py .
ruff check .
ruff format --check .
basedpyright
python3 scripts/check_release_evidence.py .
git diff --check
```

Results:

- Release evidence unit tests: pass, 3 tests.
- Release evidence checker compile: pass.
- Full unit and MCP protocol suite: pass, 42 tests.
- Release package check: pass.
- Ruff lint and format checks: pass.
- Basedpyright: pass.
- Release evidence check: expected fail until `docs/RELEASE_EVIDENCE.json` records a successful hosted `verify.yml` pull request or `0.3.1`/`v0.3.1` tag run for active version `0.3.1`.
- `git diff --check`: pass.
- Hosted GitHub Actions verification tag filters now target `0.3.1` and `v0.3.1`.

## 2026-07-02 Release Path Hardening

Commands run for this change:

```bash
python3 -m unittest tests.test_tmcp_mcp_server tests.test_tmcp_workflow_recommendation
python3 -m unittest discover -s tests
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
ruff check .
ruff format --check .
basedpyright
vulture . --min-confidence 70
python3 scripts/check_install.py .
python3 scripts/check_release_package.py .
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows release_readiness --min-confidence 0.1 --no-write-artifacts --compact
python3 scripts/pre_cr_coverage.py
git diff --check
```

Results:

- Release path hardening unit tests: pass, 39 tests.
- Full unit and MCP protocol suite: pass, 39 tests.
- Python compile and Node launcher syntax checks: pass.
- Ruff lint and format checks: pass.
- Basedpyright: pass.
- Vulture dead-code scan: pass.
- Install shape check: pass; MCP `tools/list` now must include `tmcp_recommend_workflows`.
- Release package check: pass; the extracted package now runs the adaptive workflow-pack smoke through `tmcp_recommend_workflows` and excludes local `.aios/`, `.codex/`, and `.quality-runner/` artifact directories.
- Direct workflow recommendation CLI smoke: pass; output includes `adaptive_workflow_pack.schema == tmcp-adaptive-workflow-pack-v0.1`.
- Pre-CR coverage adapter: pass with normal filesystem access to the existing `uv` cache.
- `git diff --check`: pass.
- The sandboxed runs of unittest/package/pre-CR hit the existing AIOS adapter fixture's `uv` cache permission issue; reruns with normal local filesystem access passed.
- Hosted GitHub Actions verification now triggers on pull requests, `main`, and `0.3.1`/`v0.3.1` tags. The 0.3.1 PR/tag hosted run remains external-only until pushed.

## 2026-07-02 Public-Sector Readiness Recommendation Update

Commands run for this change:

```bash
python3 -m unittest tests.test_tmcp_workflow_recommendation
python3 -m unittest discover -s tests
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
ruff check .
ruff format tests/test_tmcp_workflow_recommendation.py
ruff format --check scripts/tmcp_mcp_server.py tests/test_tmcp_workflow_recommendation.py
ruff check scripts/tmcp_mcp_server.py tests/test_tmcp_workflow_recommendation.py
git diff --check
```

Results:

- Public-sector readiness recommendation tests: pass, 9 tests.
- Full unit and MCP protocol suite: pass, 36 tests. The full suite requires normal access to the existing `uv` cache because the AIOS adapter fixture invokes `uv`.
- Python compile and Node launcher syntax checks: pass.
- Ruff lint: pass.
- Changed-file Ruff format check: pass.
- Repo-wide `ruff format --check .` still reports pre-existing formatting drift in `scripts/check_release_package.py`; this change did not modify that file.
- `tmcp_recommend_workflows` now recognizes government, compliance, UAT, and accessibility signals as `public_sector_readiness`, emits `public_sector_readiness_workflow`, and reuses the existing `public_sector_readiness` rubric profile.
- Public-sector readiness example: present in `examples/workflows/public-sector-readiness.md`.

## Commands

```bash
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
ruff check .
ruff format --check .
basedpyright
vulture . --min-confidence 70
python3 -m unittest discover -s tests
python3 scripts/check_install.py .
python3 scripts/check_release_package.py .
node scripts/tmcp_launcher.mjs recommend . --candidate-workflows release_readiness --min-confidence 0.1 --no-write-artifacts --compact
node scripts/tmcp_launcher.mjs expert-ui-rubric --project-path . --no-write-artifacts --compact
node scripts/tmcp_launcher.mjs review-plan "Use TMCP to audit government readiness for this repo" --project-path . --no-write-artifacts --adapter standalone --compact
pre-cr run --json --workspace <tmcp-checkout>
python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path
from scripts.tmcp_mcp_framing import encode_message
request = {
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'tools/call',
    'params': {
        'name': 'tmcp_recommend_workflows',
        'arguments': {'source_path': '.', 'candidate_workflows': ['developer_experience_workflow'], 'limit': 8},
    },
}
env = os.environ.copy()
env['AIOS_ROOT'] = '/tmp/tmcp-aios-missing'
completed = subprocess.run(['node', 'scripts/tmcp_launcher.mjs'], input=encode_message(request), cwd=Path.cwd(), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
assert completed.returncode == 0
PY
gh run view 28304950178 --repo jakyeamos/tmcp --json status,conclusion,jobs
claude plugin validate .
<validator-venv>/bin/python <codex-skill-validator>/plugin-creator/scripts/validate_plugin.py <tmcp-checkout>
<validator-venv>/bin/python <codex-skill-validator>/skill-creator/scripts/quick_validate.py <tmcp-checkout>/skills/tmcp
<validator-venv>/bin/python <codex-skill-validator>/skill-creator/scripts/quick_validate.py <skill-only-install>/tmcp
<validator-venv>/bin/python <codex-skill-validator>/skill-creator/scripts/quick_validate.py <codex-plugin-cache>/tmcp/skills/tmcp
python3 - <<'PY'
import json
from pathlib import Path
for name in ['.codex-plugin/plugin.json', '.claude-plugin/plugin.json', '.claude-plugin/marketplace.json', '.mcp.json', 'mcp-registry/draft-server.json', 'schemas/tmcp-skill-packet-v0.2.schema.json', 'schemas/tmcp-adaptive-workflow-pack-v0.1.schema.json', 'schemas/tmcp-composed-packet-v0.1.schema.json', 'schemas/tmcp-runtime-next-v0.1.schema.json', 'schemas/tmcp-run-receipt-v0.1.schema.json', 'schemas/tmcp-promoted-harvest-graph-v0.1.schema.json', 'tests/fixtures/golden_packets.json']:
    json.loads(Path(name).read_text(encoding='utf-8'))
PY
```

## Results

- Python compile: pass.
- Node launcher syntax: pass.
- Ruff lint: pass.
- Ruff format check: pass.
- Basedpyright: pass.
- Vulture dead-code scan: pass.
- Install shape check: pass.
- Release package check: pass.
- Release package adaptive workflow surface smoke: pass; the packaged CLI must expose `tmcp_recommend_workflows` and emit `adaptive_workflow_pack.schema == tmcp-adaptive-workflow-pack-v0.1`.
- Release package composition surface smoke: pass; the packaged CLI must expose `compose-packet`, `runtime-next`, `record-receipt`, `explain --compose`, and `recommend --compose`.
- Pre-CR commit readiness: pass with repo-local unittest adapter and threshold `0`.
- Unit and MCP protocol tests: pass, 34 tests.
- Direct expert UI rubric CLI alias smoke: pass, routes to standalone `expert_rubric_review_plan` with no artifact writes when `--no-write-artifacts` is set.
- Direct government-readiness review smoke: pass, selects `public_sector_readiness` while reporting `thin_domain_signals` when no source-backed government playbook is present.
- Claude Code marketplace validation: pass.
- Claude Code plugin manifest validation: pass with a temporary plugin-only copy.
- Plugin JSON syntax: pass.
- MCP JSON syntax: pass.
- Marketplace example JSON syntax: pass.
- Packet JSON Schema syntax: pass.
- Official plugin validator: pass in a temporary validator venv with `PyYAML`.
- Official plugin skill validator: pass in a temporary validator venv with `PyYAML`.
- Official global skill validator: pass in a temporary validator venv with `PyYAML`.
- Cached Codex plugin skill validator: pass in a temporary validator venv with `PyYAML`.
- Plugin logo assets: pass, manifest references `./assets/logo.svg` and `./assets/logo-dark.svg`.
- Claude Code plugin manifest and marketplace catalog are present.
- Claude Desktop manual MCP install doc is present.
- MCP Registry draft metadata is present and marked as draft.
- `.pre-cr.json` is present for local source-commit readiness.
- `.quality-gate-exceptions` documents the current monolithic MCP server size exception.
- Quickstart, marketplace matrix, packet stability policy, and non-UI workflow examples are present.
- Workflow recommendation example and `tmcp_recommend_workflows` docs are present.
- Adaptive workflow-pack schema, examples, router skills, and docs are present.

## Covered Behavior

- Expert UI rubric requests route to an `audit` packet and `visual_polish` rubric profile.
- Expert UI rubric CLI aliases default to the standalone TMCP expert rubric workflow instead of requiring MCP tool discovery.
- Expert rubric reviews fail profile coverage validation when the selected profile lacks profile-specific evidence and add a profile-coverage remediation slice.
- Packet `substance_check` distinguishes process-only, thin-domain, and source-backed playbook packets.
- Review plans harvest target project sources by default before synthesizing rubrics.
- Government/compliance/readiness audits route to the public-sector readiness rubric profile.
- `tmcp_doctor` reports first-run readiness and shared smoke-test guidance.
- `tmcp_recommend_workflows` infers priority signals from harvested sources, recommends workflows with evidence, emits adaptive workflow packs and custom workflow ideas, separates workflow templates from candidate instances, filters candidate workflows, and writes artifacts.
- Machine-readable packet schema required fields match the compiled standalone packet.
- Portable harvest works on a synthetic non-AIOS, non-Codex project shape.
- Harvest prunes dependency directories.
- Harvest reports missing roots as warnings.
- Harvest redacts common sensitive values before output.
- Review plan writes expected artifacts.
- MCP `tools/list`, `tmcp_status`, and `tmcp_recommend_workflows` work through `Content-Length` framing; install checks fail when `tmcp_recommend_workflows` is absent from `tools/list`.
- MCP protocol tests launch through `node scripts/tmcp_launcher.mjs`.
- MCP rejects non-object tool arguments.
- Launcher selection covers explicit `TMCP_PYTHON` and Windows `py -3` preference.
- Golden packet fixtures cover audit/UI, implementation, planning, harvest, security/privacy, and developer-experience routing.
- Review plan no-evidence behavior creates explicit evidence-gap remediation.
- Install checker validates manifest shape and MCP launch without AIOS.
- Clean-copy install check passes from a copied plugin directory.
- Release tarball check passes after unpacking into a temporary directory.
- Redaction and MCP framing are separated into dedicated modules.
- Public GitHub Actions verification with release-package and adaptive workflow-pack gates runs on pull requests, `main`, and `0.3.1`/`v0.3.1` tags. Last observed pass remains run `28305312874` for macOS, Ubuntu, and Windows across Python 3.10 and 3.13 for `0.2.5`; `0.3.1` still needs hosted CI after release PR or tag push.
- License and marketplace example are present.
- AIOS adapter absent and present behavior is covered with deterministic fixtures.

## Residual Risk

- Windows support is hosted-CI observed, but still needs manual end-user install evidence before it can be called field-proven.
- Claude community marketplace submission has not been sent.
- MCP Registry draft has not been accepted by the official registry.
