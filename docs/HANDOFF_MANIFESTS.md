# Handoff manifests

TMCP iteration bundles use the owner-aware `tmcp-handoff-manifest-v0.2`
contract for new replay custody. The older `tmcp-handoff-manifest-v0.1`
contract and historical Codex/TMCP shapes remain readable compatibility
adapters.

```json
{
  "schema": "tmcp-handoff-manifest-v0.2",
  "exact_base": "<commit>",
  "custody": {
    "stream": "behavioral_atoms",
    "owner": "worker-h3-v0.8",
    "receipt": {
      "reference": "handoffs/h3-v0.8/RECEIPT.md",
      "sha256": "<receipt-sha256>",
      "freshness": "current",
      "observed_at": "2026-08-08T12:00:00Z"
    },
    "formatter_fingerprint": {
      "name": "ruff",
      "version": "0.15.10",
      "config_sha256": "<effective-config-sha256>",
      "invocation": "ruff format --check",
      "mode": "check"
    }
  },
  "files": [
    {
      "path": "repository/relative/path",
      "artifact_path": "files/repository/relative/path",
      "bytes": 123,
      "sha256": "<lowercase-sha256>",
      "custody": {
        "status": "verified",
        "overlap": "none"
      }
    }
  ]
}
```

Run the stdlib-only helper from any checkout, including one with a minimal
`PATH`:

```bash
python3 scripts/replay_handoff.py verify /path/to/manifest.json
python3 scripts/replay_handoff.py verify /path/to/manifest.json --require-custody
python3 scripts/replay_handoff.py replay /path/to/manifest.json \
  --destination-root /path/to/clean/worktree
python3 scripts/replay_handoff.py replay /path/to/manifest.json \
  --destination-root /path/to/clean/worktree --require-custody
```

Verification completes for every source file before replay writes anything.
Each copied file is staged beside its destination, flushed, hash-checked, and
installed with `os.replace`. Existing identical files are retained; differing
files require the explicit `--force` option. The helper accepts the two
historical Codex/TMCP manifest shapes as read-only compatibility adapters, but
new bundles must emit the owner-aware v0.2 schema above. Its manifest-level
custody records the authoritative stream, owner, receipt reference, receipt
hash, and freshness. Each file records whether its bytes are verified and
whether ownership is shared or unresolved. `--require-custody` is the strict
integration gate: it requires v0.2 metadata, a current receipt, `verified`
file status, `none` overlap for every file, and a matching
`custody.formatter_fingerprint`. The fingerprint records the resolved Ruff
name and version, the validation invocation (`ruff format --check`), the
validation mode (`check`), and `config_sha256`. The effective-config hash is
the SHA-256 of a canonical UTF-8 JSON payload with sorted keys, compact JSON
separators, and one trailing newline:
`{"default_profile":"ruff-format-defaults-v1","format_config_files":[{"path":"<root-relative-config>","sha256":"<config-file-sha256>"}]}`.
The config-file list is sorted by path and includes existing root-level
`.ruff.toml`, `pyproject.toml`, and `ruff.toml` files; an empty list records
Ruff's default profile. The parser resolves the live `ruff --version` and the
same root-level config inputs before accepting strict custody. Default
verification still reads v0.1 and historical manifests, and reads older v0.2
metadata without treating it as an integration authorization.

For Codex handoffs, the compatibility adapter recognizes
`handoff_version: "1.0"` and maps each `changed_files[]` record's `repo_path`,
`bundle_path`, `byte_size`, and `sha256` to the canonical destination, source,
size, and digest fields. Payloads are expected beneath the handoff's `files/`
directory; all paths remain relative and are containment-checked before any
write.
