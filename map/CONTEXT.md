# TMCP system map

Status: proposal catalog; existing child Compasses remain draft/open and are
not ratified by this map.

## Decision record

- Selected form: ICM System map. TMCP combines a packet compiler/runtime,
  skill harvest/recommendation, MCP contracts, and release/distribution.
- Rejected smaller form: root context alone. It would hide the runtime path and
  release compatibility boundary.
- Authority: the root Compass, `README.md`, runtime docs, schemas, and release
  docs.
- Existing user gate: the active TMCP root quiz remains the intent gate.

## Universe inventory

- **live candidates:** `tmcp_runtime/`, `scripts/`, `skills/`,
  `mcp-registry/`, `schemas/`, docs, examples, and tests.
- **draft boundary:** the existing `packet-runtime` child is path-incomplete
  until `tmcp_runtime/`, `schemas/`, and `mcp-registry/` coverage is resolved.
- **experimental/unknown:** experimental workflows and tools, plus the
  disabled AIOS adapter/storage integration.
- **support layers:** examples, assets, and tests are not children by folder
  presence alone.

## Proposed target tree

```text
map/
├── AGENTS.md
├── CONTEXT.md
├── _meta/schema.md
├── _templates/object.md
└── objects/
    ├── CONTEXT.md
    └── _index.md
```

Candidate clusters:

- **packet-runtime** — launcher, packet composition, runtime protocol, MCP
  framing/server, schemas, registry, and `tmcp_runtime/`.
- **skill-harvest-recommendation** — skill packages and evaluation/
  recommendation tooling.
- **release-distribution** — release composition, archive, compatibility, and
  distribution documentation/scripts.
- **experimental-integrations** — explicitly labeled experimental workflows
  and optional/disabled AIOS integration; no automatic promotion.

## First-order impact

- **Hits:** changes to packet compilation, MCP framing, skill recommendation,
  or release compatibility hit the relevant cluster and root Compass.
- **Does not hit:** an experimental adapter does not redefine stable runtime
  semantics unless explicitly admitted.

## Open decisions

1. Confirm the complete packet-runtime source set.
2. Decide whether experimental surfaces remain root-scoped.
3. Decide whether AIOS integration is optional under the root or a child.

