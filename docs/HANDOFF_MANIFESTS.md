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
new bundles must emit the canonical schema above.
