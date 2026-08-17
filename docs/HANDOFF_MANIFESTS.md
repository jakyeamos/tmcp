# Handoff manifests

TMCP iteration bundles use `tmcp-handoff-manifest-v0.1` for replay custody.
The manifest is intentionally small and provider-neutral:

```json
{
  "schema": "tmcp-handoff-manifest-v0.1",
  "exact_base": "<commit>",
  "files": [
    {
      "path": "repository/relative/path",
      "artifact_path": "files/repository/relative/path",
      "bytes": 123,
      "sha256": "<lowercase-sha256>"
    }
  ]
}
```

Run the stdlib-only helper from any checkout, including one with a minimal
`PATH`:

```bash
python3 scripts/replay_handoff.py verify /path/to/manifest.json
python3 scripts/replay_handoff.py replay /path/to/manifest.json \
  --destination-root /path/to/clean/worktree
```

Verification completes for every source file before replay writes anything.
Each copied file is staged beside its destination, flushed, hash-checked, and
installed with `os.replace`. Existing identical files are retained; differing
files require the explicit `--force` option. The helper accepts the two
historical Codex/TMCP manifest shapes as read-only compatibility adapters, but
new bundles must emit the canonical schema above. For Codex handoffs, the
adapter recognizes `handoff_version: "1.0"` and maps each `changed_files[]`
record's `repo_path`, `bundle_path`, `byte_size`, and `sha256` to the canonical
destination, source, size, and digest fields. Payloads are expected beneath the
handoff's `files/` directory; all paths remain relative and are
containment-checked before any write.
