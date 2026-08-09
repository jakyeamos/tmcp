# H3 v0.7 boundary decision handoff

Iteration: `runtime-h3-boundary-decision-v0.7`
Status: `eligible_advisory`, decision-only, private/additive
Base: current HEAD `4098ba504e63dd8d53f2a1f39827df1461fc425f`; sealed v0.6 declared base `3c9b2fe8cc0fe72ed947c447e4ea549094d810c3`
Public runtime contract preserved: `0.5.7`

## Exact changed-file inventory

| Path | SHA-256 |
| --- | --- |
| `docs/experiments/behavioral-atoms-runtime-h3-boundary-evidence-ladder-v0.7.json` | `763e5543537ba290624b0133785c48dcab489135e860b1bdfb6098a53a4a50a8` |
| `schemas/tmcp-behavioral-atoms-runtime-h3-decision-v0.7.schema.json` | `7a534143a8bc31fada5773885cde5e1d5c3eda305f0e544f6df115aee176fbfc` |
| `schemas/tmcp-behavioral-atoms-runtime-h3-fixtures-v0.7.schema.json` | `fe0b02a0419b7f9eb21339b54a5f929add5a9a686b2a87401910779ad317b455` |
| `tests/fixtures/behavioral-atoms-runtime-h3-v0.7.json` | `cbe0c7e2cc95047f5d01eb0f1468e0b9394ca1543b447ce4925f2953d7a4d7f2` |
| `tests/test_tmcp_behavioral_atoms_runtime_h3_v0_7.py` | `1ce94a79da5db2cba5227e08fc7edfd0ad358ffc8747bf8dfdd305d922024f0e` |
| `docs/experiments/behavioral-atoms-runtime-h3-boundary-evidence-ladder-v0.7-HANDOFF.md` | reported after final write in the coordinator event |

The v0.3 semantic/fixture baselines and v0.6 decision were not edited. Their verified hashes remain in the decision JSON and the structural test.

## Decision

H3 is justified as a later private typed-static slice with two distinct atoms:

- `domain.security_privacy.secret_boundary@0.4.0` adds authorized scope, ownership, and pre-read boundary obligations beyond H2 redaction.
- `domain.release_readiness.evidence_ladder@0.4.0` adds complete/fresh gate inventory and per-remediation acceptance checks beyond H2 ship_gate.

Two valid advisory arms are preregistered. The seven-fixture boundary freezes positive, negative, ambiguous, and a new positive combined interaction absent from the current v0.3/v0.6 evidence. The combined case is a static input only; cross-skill composition remains closed.

## Verification

- Four new JSON artifacts parse with `python3 -m json.tool`.
- Focused H3 structural test: 7 tests passed.
- H1, H2, public projection, and H3 focused regression set: 38 tests passed.
- No H3 IDs are registered in the current H2 runtime registry or runtime source surfaces.
- External `jsonschema`/`ajv` validation was unavailable and was not substituted by installation.

## Next authorization boundary

A later H3 implementation iteration is justified only as a private, opt-in, static-advisory extension. It requires fresh repository-owner authorization naming the exact runtime files, preserving H1/H2/no-bundle/public/default/admission/routing/provider-off/cross-skill-off boundaries, and passing the frozen v0.7 decision/fixture gates. This package grants no runtime, provider, composition, install, release, promotion, staging, commit, or push authority.
