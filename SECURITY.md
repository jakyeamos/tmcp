# Security

TMCP runs local MCP tools that read local files when asked to harvest skills or produce review artifacts.

## Reporting

Open a private security advisory or contact the maintainer before publishing exploit details.

## Data Handling

- Standalone mode does not require network access.
- Skill harvest redacts common API keys, bearer tokens, private keys, GitHub tokens, AWS access keys, secret assignments, and high-entropy strings by default.
- AIOS is optional. If `AIOS_ROOT` points to an AIOS checkout, adapter mode may call local AIOS commands.

## User Responsibility

Review harvested artifacts before sharing them. Redaction is a safety layer, not a guarantee that every organization-specific secret format is covered.
