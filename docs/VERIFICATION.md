# Verification Record

Date: 2026-06-26

Plugin version: `0.2.2+codex.20260626193000`

## Commands

```bash
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
python3 -m unittest discover -s tests
python3 scripts/check_install.py .
python3 scripts/check_release_package.py .
pre-cr run --json --workspace /Users/jakyeamos/plugins/tmcp
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
gh run view <pending-0.2.2-run-id> --repo jakyeamos/tmcp --json status,conclusion,jobs
claude plugin validate .
/private/tmp/tmcp-validator-venv/bin/python /Users/jakyeamos/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py /Users/jakyeamos/plugins/tmcp
/private/tmp/tmcp-validator-venv/bin/python /Users/jakyeamos/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/jakyeamos/plugins/tmcp/skills/tmcp
/private/tmp/tmcp-validator-venv/bin/python /Users/jakyeamos/.codex/skills/.system/skill-creator/scripts/quick_validate.py /Users/jakyeamos/.agents/skills/tmcp
python3 - <<'PY'
import json
from pathlib import Path
for name in ['.codex-plugin/plugin.json', '.claude-plugin/plugin.json', '.claude-plugin/marketplace.json', '.mcp.json', 'mcp-registry/draft-server.json', 'schemas/tmcp-skill-packet-v0.2.schema.json', 'tests/fixtures/golden_packets.json']:
    json.loads(Path(name).read_text(encoding='utf-8'))
PY
```

## Results

- Python compile: pass.
- Node launcher syntax: pass.
- Install shape check: pass.
- Release package check: pass.
- Pre-CR commit readiness: pass with repo-local unittest adapter and threshold `0`.
- Unit and MCP protocol tests: pass, 18 tests.
- Claude Code marketplace validation: pass.
- Claude Code plugin manifest validation: pass with a temporary plugin-only copy.
- Plugin JSON syntax: pass.
- MCP JSON syntax: pass.
- Marketplace example JSON syntax: pass.
- Packet JSON Schema syntax: pass.
- Official plugin validator: pass in a temporary validator venv with `PyYAML`.
- Official plugin skill validator: pass in a temporary validator venv with `PyYAML`.
- Official global skill validator: pass in a temporary validator venv with `PyYAML`.
- Plugin logo assets: pass, manifest references `./assets/logo.svg` and `./assets/logo-dark.svg`.
- Claude Code plugin manifest and marketplace catalog are present.
- Claude Desktop manual MCP install doc is present.
- MCP Registry draft metadata is present and marked as draft.
- `.pre-cr.json` is present for local source-commit readiness.
- `.quality-gate-exceptions` documents the current monolithic MCP server size exception.
- Quickstart, marketplace matrix, packet stability policy, and non-UI workflow examples are present.
- Workflow recommendation example and `tmcp_recommend_workflows` docs are present.

## Covered Behavior

- Expert UI rubric requests route to an `audit` packet and `visual_polish` rubric profile.
- `tmcp_doctor` reports first-run readiness and shared smoke-test guidance.
- `tmcp_recommend_workflows` infers priority signals from harvested sources, recommends workflows with evidence, filters candidate workflows, and writes artifacts.
- Machine-readable packet schema required fields match the compiled standalone packet.
- Portable harvest works on a synthetic non-AIOS, non-Codex project shape.
- Harvest prunes dependency directories.
- Harvest reports missing roots as warnings.
- Harvest redacts common sensitive values before output.
- Review plan writes expected artifacts.
- MCP `tools/list`, `tmcp_status`, and `tmcp_recommend_workflows` work through `Content-Length` framing.
- MCP protocol tests launch through `node scripts/tmcp_launcher.mjs`.
- MCP rejects non-object tool arguments.
- Launcher selection covers explicit `TMCP_PYTHON` and Windows `py -3` preference.
- Golden packet fixtures cover audit/UI, implementation, planning, harvest, security/privacy, and developer-experience routing.
- Review plan no-evidence behavior creates explicit evidence-gap remediation.
- Install checker validates manifest shape and MCP launch without AIOS.
- Clean-copy install check passes from a copied plugin directory.
- Release tarball check passes after unpacking into a temporary directory.
- Redaction and MCP framing are separated into dedicated modules.
- Public GitHub Actions verification with release-package gate: pending for `0.2.2`.
- License and marketplace example are present.
- AIOS adapter absent and present behavior is covered with deterministic fixtures.

## Residual Risk

- Windows support is hosted-CI observed, but still needs manual end-user install evidence before it can be called field-proven.
- Claude community marketplace submission has not been sent.
- MCP Registry draft has not been accepted by the official registry.
