#!/usr/bin/env python3
"""Materialize bounded composition-benchmark fixtures without running a host."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tmcp_runtime.domain.composition_benchmark_protocol import (  # noqa: E402
    build_benchmark_preparation,
)
from tmcp_runtime.storage.artifacts import (  # noqa: E402
    ArtifactStorageError,
    AtomicArtifactStore,
)


MAX_INPUT_BYTES = 8 * 1024 * 1024


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{label} exceeds {MAX_INPUT_BYTES} bytes.")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return payload


def prepare_benchmark(
    *,
    routing_golden_path: Path,
    behavioral_fixtures_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Write a fresh fixture workspace and return the deterministic run plan."""

    routing = _read_object(routing_golden_path, label="routing golden")
    behavioral = _read_object(behavioral_fixtures_path, label="behavioral fixtures")
    plan, artifacts = build_benchmark_preparation(
        routing_golden=routing,
        behavioral_fixtures=behavioral,
    )
    paths = AtomicArtifactStore.write_tree_bundle(output_dir, artifacts)
    return {
        "schema": "tmcp-composition-benchmark-preparation-v0.1",
        "ok": True,
        "run_manifest_id": plan["run_manifest_id"],
        "run_manifest_digest": plan["run_manifest_digest"],
        "run_manifest_path": paths["benchmark-run-plan.json"],
        "fixture_workspace_count": len(plan["fixture_workspaces"]),
        "routing_request_count": len(plan["routing_requests"]),
        "behavioral_request_count": len(plan["behavioral_requests"]),
        "automatic_tool_execution": False,
        "receipt_persistence": "not_performed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize composition benchmark fixtures and host intake preflights. "
            "This command never runs host tools or writes receipts."
        )
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--routing-golden",
        type=Path,
        default=PLUGIN_ROOT
        / "tests"
        / "fixtures"
        / "composition_routing_golden_v0_6.json",
    )
    parser.add_argument(
        "--behavioral-fixtures",
        type=Path,
        default=PLUGIN_ROOT
        / "tests"
        / "fixtures"
        / "composition_behavioral_fixtures_v0_6.json",
    )
    args = parser.parse_args()
    try:
        result = prepare_benchmark(
            routing_golden_path=args.routing_golden,
            behavioral_fixtures_path=args.behavioral_fixtures,
            output_dir=args.output_dir,
        )
    except (ArtifactStorageError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
