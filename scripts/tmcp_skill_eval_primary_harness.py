"""Independent verification for an archived primary campaign harness."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.tmcp_skill_eval_campaign_protocol import _sha256_file, _sha256_text


PRIMARY_HARNESS_BINDING_SCHEMA = "tmcp-skill-eval-primary-harness-binding-v0.1"
PRIMARY_HARNESS_SNAPSHOT_SCHEMA = "tmcp-skill-eval-campaign-harness-snapshot-v0.1"
PRIMARY_HARNESS_SNAPSHOT_DIRECTORY = "campaign-harness"
PRIMARY_HARNESS_FILES = frozenset(
    {
        "tmcp_skill_eval_campaign.py",
        "tmcp_skill_eval_campaign_protocol.py",
        "tmcp_skill_eval_campaign_planning.py",
        "tmcp_skill_eval_campaign_runtime.py",
        "tmcp_skill_eval_composition.py",
    }
)


def _is_sha256_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _canonical_json_digest(payload: Any) -> str:
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def primary_harness_binding(
    harness_files: Mapping[str, object]
) -> dict[str, Any]:
    """Normalize the complete local primary-harness binding for a study plan."""

    if set(harness_files) != PRIMARY_HARNESS_FILES or not all(
        _is_sha256_digest(digest) for digest in harness_files.values()
    ):
        raise ValueError("Primary harness files must be a complete digest map.")
    normalized = {name: str(harness_files[name]) for name in sorted(harness_files)}
    return {
        "schema": PRIMARY_HARNESS_BINDING_SCHEMA,
        "harness_files": normalized,
        "harness_sha256": _canonical_json_digest(normalized),
    }


def validate_primary_harness_binding(value: Any) -> dict[str, Any]:
    """Reject an incomplete or self-inconsistent preregistered harness binding."""

    if not isinstance(value, dict) or value.get("schema") != PRIMARY_HARNESS_BINDING_SCHEMA:
        raise ValueError("Primary harness binding schema does not match.")
    harness_files = value.get("harness_files")
    if not isinstance(harness_files, dict):
        raise ValueError("Primary harness binding files must be an object.")
    expected = primary_harness_binding(harness_files)
    if value != expected:
        raise ValueError("Primary harness binding does not match its digest map.")
    return expected


def verify_preregistered_primary_harness(
    plan: Mapping[str, Any], harness_files: Mapping[str, object]
) -> None:
    """Fail closed when a primary campaign harness differs from its study plan."""

    experiment = plan.get("experiment")
    binding = (
        experiment.get("source_study_binding")
        if isinstance(experiment, Mapping)
        else None
    )
    expected = binding.get("primary_harness") if isinstance(binding, Mapping) else None
    if validate_primary_harness_binding(expected) != primary_harness_binding(
        harness_files
    ):
        raise ValueError(
            "Source-bundle campaign primary harness does not match preregistration."
        )


def verify_primary_harness_snapshot(
    manifest: dict[str, Any], source_runs: Path
) -> None:
    """Require inspectable, byte-pinned local harness modules for the primary run."""

    harness_files = manifest.get("harness_files")
    snapshot = manifest.get("harness_snapshot")
    if (
        not isinstance(harness_files, dict)
        or set(harness_files) != PRIMARY_HARNESS_FILES
        or manifest.get("harness_sha256")
        != primary_harness_binding(harness_files)["harness_sha256"]
        or not isinstance(snapshot, dict)
        or snapshot.get("schema") != PRIMARY_HARNESS_SNAPSHOT_SCHEMA
        or snapshot.get("directory") != PRIMARY_HARNESS_SNAPSHOT_DIRECTORY
        or snapshot.get("files") != sorted(PRIMARY_HARNESS_FILES)
    ):
        raise ValueError("Source-bundle campaign harness declaration is invalid.")
    snapshot_dir = source_runs / PRIMARY_HARNESS_SNAPSHOT_DIRECTORY
    if not snapshot_dir.is_dir() or {
        path.name for path in snapshot_dir.iterdir()
    } != PRIMARY_HARNESS_FILES:
        raise ValueError("Source-bundle campaign harness snapshot is incomplete.")
    for name, digest in harness_files.items():
        snapshot_path = snapshot_dir / name
        if not snapshot_path.is_file() or _sha256_file(snapshot_path) != digest:
            raise ValueError("Source-bundle campaign harness snapshot does not match.")
