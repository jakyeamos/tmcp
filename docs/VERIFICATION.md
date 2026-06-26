# Verification Record

Date: 2026-06-26

Plugin version: `0.2.0+codex.20260626183129`

## Commands

```bash
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
python3 -m unittest discover -s tests
python3 scripts/check_install.py .
python3 scripts/check_release_package.py .
pre-cr run --json --workspace /Users/jakyeamos/plugins/tmcp
claude plugin validate .
/private/tmp/tmcp-validator-venv/bin/python /Users/jakyeamos/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py /Users/jakyeamos/plugins/tmcp
/private/tmp/tmcp-validator-venv/bin/python /Users/jakyeamos/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/jakyeamos/plugins/tmcp/skills/tmcp
/private/tmp/tmcp-validator-venv/bin/python /Users/jakyeamos/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/jakyeamos/.agents/skills/tmcp
```

## Results

- Python compile: pass.
- Node launcher syntax: pass.
- Install shape check: pass.
- Release package check: pass.
- Pre-CR commit readiness: pass with repo-local unittest adapter and threshold `0`.
- Unit and MCP protocol tests: pass, 14 tests.
- Claude Code marketplace validation: pass.
- Claude Code plugin manifest validation: pass with a temporary plugin-only copy.
- Plugin JSON syntax: pass.
- MCP JSON syntax: pass.
- Marketplace example JSON syntax: pass.
- Official plugin validator: pass in a temporary validator venv with `PyYAML`.
- Official plugin skill validator: pass in a temporary validator venv with `PyYAML`.
- Official global skill validator: pass in a temporary validator venv with `PyYAML`.
- Plugin logo assets: pass, manifest references `./assets/logo.svg` and `./assets/logo-dark.svg`.
- Claude Code plugin manifest and marketplace catalog are present.
- Claude Desktop manual MCP install doc is present.
- MCP Registry draft metadata is present and marked as draft.
- `.pre-cr.json` is present for local source-commit readiness.
- `.quality-gate-exceptions` documents the current monolithic MCP server size exception.

## Covered Behavior

- Expert UI rubric requests route to an `audit` packet and `visual_polish` rubric profile.
- Portable harvest works on a synthetic non-AIOS, non-Codex project shape.
- Harvest prunes dependency directories.
- Harvest reports missing roots as warnings.
- Harvest redacts common sensitive values before output.
- Review plan writes expected artifacts.
- MCP `tools/list` and `tmcp_status` work through `Content-Length` framing.
- MCP protocol tests launch through `node scripts/tmcp_launcher.mjs`.
- MCP rejects non-object tool arguments.
- Launcher selection covers explicit `TMCP_PYTHON` and Windows `py -3` preference.
- Golden packet fixtures cover audit/UI, implementation, planning, harvest, security/privacy, and developer-experience routing.
- Review plan no-evidence behavior creates explicit evidence-gap remediation.
- Install checker validates manifest shape and MCP launch without AIOS.
- Clean-copy install check passes from a copied plugin directory.
- Release tarball check passes after unpacking into a temporary directory.
- Redaction and MCP framing are separated into dedicated modules.
- CI workflow is present for macOS, Linux, and Windows.
- License and marketplace example are present.
- AIOS adapter absent and present behavior is covered with deterministic fixtures.

## Residual Risk

- Hosted Linux and Windows CI have not been observed running from a remote repository.
- Windows support is launcher-ready and CI-declared, but still needs hosted or manual Windows execution evidence.
- Claude community marketplace submission has not been sent.
- MCP Registry draft has not been accepted by the official registry.
