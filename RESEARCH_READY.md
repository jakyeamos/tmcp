# Research Readiness

TMCP is prepared as a DOI-grade software-methods artifact for portable
skill-packet workflows and MCP-agent routing. The citable release should archive
source code, plugin manifests, skills, workflow examples, packet specs,
verification docs, release evidence, and stable/experimental workflow labeling.
Runtime receipts, harvested local sources, and private packet evidence remain
local unless intentionally redacted and attached as examples.

## Artifact Map

| Surface | Purpose |
| --- | --- |
| `scripts/` | Standalone launcher, MCP server, install checks, release package checks, redaction, and evidence scripts. |
| `skills/` | TMCP routing and workflow skills. |
| `docs/TMCP_PACKET_SPEC.md` and `docs/PACKET_STABILITY.md` | Packet contract and stability policy. |
| `docs/RELEASE_EVIDENCE.json` and `docs/VERIFICATION.md` | Release evidence and verification expectations. |
| `examples/workflows/` | Stable and experimental workflow examples. |
| `.codex-plugin/` and `.claude-plugin/` | Plugin manifests and host integration metadata. |

## Validation

Non-network release validation:

```bash
python3 -m unittest discover -s tests
python3 -m py_compile scripts/tmcp_mcp_server.py scripts/check_install.py scripts/check_release_package.py scripts/check_release_evidence.py scripts/pre_cr_coverage.py scripts/tmcp_mcp_framing.py scripts/tmcp_redaction.py
node --check scripts/tmcp_launcher.mjs
python3 scripts/check_install.py .
```

The stricter package check is not yet part of the passing DOI validation path:
`python3 scripts/check_release_package.py .` currently fails
`hardcoded_user_paths` because existing release-evidence docs preserve absolute
local install paths. Redact or normalize those examples before DOI minting.

## Data Availability

Harvested sources, promoted graphs, receipts, and runtime packet evidence are
local run artifacts unless explicitly redacted and committed as examples. Public
workflow claims should cite the stable/experimental labeling and release
evidence docs.

## DOI Gate

Before minting a DOI, replace the placeholder ORCID in `CITATION.cff` and
`.zenodo.json` with the real author ORCID.
