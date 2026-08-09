# Codex validation preflight

Run the read-only gate before editing a Codex checkout or dispatching a Codex
validation task:

```bash
node scripts/tmcp_launcher.mjs codex-validation-preflight \
  --path /path/to/codex \
  --path /path/to/codex-build-cache

# Require an editable Desktop bridge source/build lane as well.
node scripts/tmcp_launcher.mjs codex-validation-preflight \
  --path /path/to/codex \
  --desktop-bridge-manifest /path/to/desktop-bridge-build.json \
  --desktop-bridge-source /path/to/desktop-bridge \
  --require-desktop-bridge
```

The default policy requires `just`, `cargo-nextest`, and `dotslash`, and at
least 80 GiB of free space on every inspected filesystem. The output is a
`tmcp-codex-validation-preflight-v0.1` JSON report. A non-zero exit code means
the task must remain blocked.

The gate only resolves executable paths, runs each tool's `--version` probe,
and reads filesystem usage. It does not install dependencies, change
configuration, run a build, or remove files. Use `--tool` to provide an
explicit required-tool set and `--min-free-gib` for a separately approved
storage policy; do not use either option to bypass a required project gate.

Desktop bridge readiness is separate from Codex toolchain readiness. The
bridge check is `not_requested` unless `--require-desktop-bridge`,
`--desktop-bridge-manifest`, or `--desktop-bridge-source` is supplied. When
requested, the gate fails closed unless the manifest names an existing editable
source root, non-empty build and test argv declarations, and the canonical
`thread/setupStatus/read` method. Commands in the manifest are never executed.
The descriptor must follow
[`tmcp-codex-desktop-bridge-build-v0.1.schema.json`](../schemas/tmcp-codex-desktop-bridge-build-v0.1.schema.json).
This descriptor gate does not claim that the proprietary Desktop bridge is
implemented: the bridge owner must still call the Core handle and exercise
pending, ready, and failed reads without a sidebar scan. Until that source and
its live integration tests are available, `--require-desktop-bridge` remains
blocked.

For example:

```json
{
  "schema": "tmcp-codex-desktop-bridge-build-v0.1",
  "source_root": "./desktop-bridge",
  "protocol_method": "thread/setupStatus/read",
  "build_command": ["just", "build-bridge"],
  "test_command": ["just", "test-bridge"]
}
```

If a tool is missing, the report includes the documented `cargo install
--locked ...` command as remediation. If storage is below the floor, restore
capacity or move the validation workspace to a filesystem with sufficient
space. Never replace the gate with an approximate build estimate or a local
tokenizer/accounting substitute.

The checked-in JSON contract is
[`schemas/tmcp-codex-validation-preflight-v0.1.schema.json`](../schemas/tmcp-codex-validation-preflight-v0.1.schema.json).

## Hermetic bootstrap

The read-only gate intentionally does not install anything. After it passes,
use the separate bootstrap command before replaying or building the Codex
source:

```bash
node scripts/tmcp_launcher.mjs codex-validation-bootstrap \
  --source-root /path/to/codex \
  --toolchain /path/to/codex-validation-toolchain.json \
  --tool-dir /private/tmp/codex-validation-tools
```

The toolchain lock is caller-owned and must have this shape. The example
versions are illustrative; use the versions pinned by the Codex checkout or
its CI configuration, and preserve them in the lock used for the run:

```json
{
  "schema": "tmcp-codex-validation-toolchain-v0.1",
  "tools": [
    {
      "name": "just",
      "package": "just",
      "executable": "just",
      "version": "1.2.3"
    },
    {
      "name": "cargo-nextest",
      "package": "cargo-nextest",
      "executable": "cargo-nextest",
      "version": "1.2.3"
    },
    {
      "name": "dotslash",
      "package": "dotslash",
      "executable": "dotslash",
      "version": "1.2.3"
    }
  ]
}
```

The bootstrap performs source-root and lock validation, checks the configured
free-space floor on both the checkout and tool filesystem, probes `cargo` and
`bazel` (or explicitly supplied `--external-tool` values), and only then runs
`cargo install --locked --root <tool-dir>` for missing or mismatched packages.
It sets a task-local `CARGO_HOME`, verifies every locked version, and exercises
the installed tools through the reported `PATH` with `--version` and
`just --list`. It leaves the task-local directory in place for the validation
run; cleanup is a separate, explicitly authorized lifecycle action.

The command emits a `tmcp-codex-validation-bootstrap-v0.1` report. A blocked
pre-install phase has no installation side effect. The bootstrap does not
install system Bazel/Bazelisk, refresh source locks, replay a handoff, or
claim live Codex validation; those remain separate gates.

Contracts:

- [`tmcp-codex-validation-bootstrap-v0.1`](../schemas/tmcp-codex-validation-bootstrap-v0.1.schema.json)
- [`tmcp-codex-validation-toolchain-v0.1`](../schemas/tmcp-codex-validation-toolchain-v0.1.schema.json)
