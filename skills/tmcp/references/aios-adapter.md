# AIOS Adapter

AIOS is optional storage and adapter support for TMCP. It is not required for the TMCP concept, the MCP server, skill harvest, workflow recommendation, or expert rubric planning.

Use AIOS only when `AIOS_ROOT` is explicitly configured and the user or workflow requests adapter behavior.

## Behavior

- `--adapter standalone` stays inside the TMCP package.
- `--adapter auto` always uses standalone behavior, even when AIOS is configured.
- `--adapter aios` must return a clear remediation error when `AIOS_ROOT/bin/aios.py` is missing.
- `--adapter aios` rejects known sensitive request values until AIOS supports a protected request-input protocol.

## Remediation

If the AIOS adapter is requested but unavailable, report:

- the configured `AIOS_ROOT`
- that standalone TMCP still works
- how to continue with `--adapter standalone`
- how to configure AIOS only if the user actually wants it
