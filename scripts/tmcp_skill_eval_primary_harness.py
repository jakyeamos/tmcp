"""Independent verification for an archived primary campaign harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.tmcp_skill_eval_campaign_protocol import _sha256_file, _sha256_text


_PRIMARY_HARNESS_SNAPSHOT_SCHEMA = "tmcp-skill-eval-campaign-harness-snapshot-v0.1"
_PRIMARY_HARNESS_SNAPSHOT_DIRECTORY = "campaign-harness"
_PRIMARY_HARNESS_FILES = frozenset(
    {
        "tmcp_skill_eval_campaign.py",
        "tmcp_skill_eval_campaign_protocol.py",
        "tmcp_skill_eval_campaign_planning.py",
        "tmcp_skill_eval_campaign_runtime.py",
    }
)


def _is_sha256_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _canonical_json_digest(payload: Any) -> str:
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def verify_primary_harness_snapshot(
    manifest: dict[str, Any], source_runs: Path
) -> None:
    """Require inspectable, byte-pinned local harness modules for the primary run."""

    harness_files = manifest.get("harness_files")
    snapshot = manifest.get("harness_snapshot")
    if (
        not isinstance(harness_files, dict)
        or set(harness_files) != _PRIMARY_HARNESS_FILES
        or not all(_is_sha256_digest(digest) for digest in harness_files.values())
        or manifest.get("harness_sha256") != _canonical_json_digest(harness_files)
        or not isinstance(snapshot, dict)
        or snapshot.get("schema") != _PRIMARY_HARNESS_SNAPSHOT_SCHEMA
        or snapshot.get("directory") != _PRIMARY_HARNESS_SNAPSHOT_DIRECTORY
        or snapshot.get("files") != sorted(_PRIMARY_HARNESS_FILES)
    ):
        raise ValueError("Source-bundle campaign harness declaration is invalid.")
    snapshot_dir = source_runs / _PRIMARY_HARNESS_SNAPSHOT_DIRECTORY
    if not snapshot_dir.is_dir() or {
        path.name for path in snapshot_dir.iterdir()
    } != _PRIMARY_HARNESS_FILES:
        raise ValueError("Source-bundle campaign harness snapshot is incomplete.")
    for name, digest in harness_files.items():
        snapshot_path = snapshot_dir / name
        if not snapshot_path.is_file() or _sha256_file(snapshot_path) != digest:
            raise ValueError("Source-bundle campaign harness snapshot does not match.")
