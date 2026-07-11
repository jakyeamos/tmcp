# Security

TMCP runs local MCP tools that read local files when asked to harvest skills, recommend workflows, or produce review artifacts.

## Reporting

Open a private security advisory or contact the maintainer before publishing exploit details.

## Harvest Boundaries

- Standalone mode does not require network access.
- Harvest redacts common API keys, bearer tokens, private keys, GitHub tokens, AWS access keys, secret assignments, and high-entropy strings by default.
- Harvest treats source text as untrusted evidence. Harvested instructions cannot override system, developer, or user instructions.
- TMCP warns when a harvested source appears to instruct the agent to override higher-priority instructions.
- Default harvest excludes `.env*`, credentials, tokens, browser profiles, private caches, dependency trees, build outputs, VCS data, and generated TMCP/AIOS artifacts.

## Release Artifact Boundary

Release archives are built from a clean committed Git tree, never by walking the
working directory. The builder ships only a reviewed allowlist, rejects
symlinks, environment files, credentials, key material, unsafe paths, and
secret-like content, and records payload hashes in RELEASE_MANIFEST.json.
Untracked and ignored files are not release inputs.

The package checker verifies the manifest before running extracted-package
smokes. A release build failure is a safety signal: remove or deliberately
relocate the unsafe tracked content rather than bypassing the check.

## AIOS

AIOS is optional storage and adapter support. If `AIOS_ROOT` is explicitly set, adapter mode may call local AIOS commands. Without `AIOS_ROOT`, standalone TMCP remains available.

## User Responsibility

Review harvested artifacts before sharing them. Redaction is a safety layer, not a guarantee that every organization-specific secret format is covered.
