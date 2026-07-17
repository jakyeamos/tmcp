#!/usr/bin/env python3
"""Assemble compiler-derived composition benchmark controls without host execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tmcp_runtime.domain.composition_benchmark_replay import (  # noqa: E402
    build_benchmark_control_plan,
)
from tmcp_runtime.storage.artifacts import (  # noqa: E402
    ArtifactStorageError,
    AtomicArtifactStore,
)


MAX_INPUT_BYTES = 16 * 1024 * 1024


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{label} exceeds {MAX_INPUT_BYTES} bytes.")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return payload


def assemble_control_plan(
    *,
    run_plan_path: Path,
    semantic_proposals_path: Path,
    routing_golden_path: Path,
    behavioral_fixtures_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Replay a prepared run and write one fresh control-plan artifact."""

    run_plan = _read_object(run_plan_path, label="benchmark run plan")
    semantic_proposals = _read_object(
        semantic_proposals_path,
        label="semantic proposal bundle",
    )
    routing = _read_object(routing_golden_path, label="routing golden")
    behavioral = _read_object(behavioral_fixtures_path, label="behavioral fixtures")
    control_plan = build_benchmark_control_plan(
        run_plan=run_plan,
        semantic_proposals=semantic_proposals,
        routing_golden=routing,
        behavioral_fixtures=behavioral,
    )
    paths = AtomicArtifactStore.write_json_bundle(
        output_dir,
        {"benchmark-control-plan.json": control_plan},
    )
    return {
        "schema": "tmcp-composition-benchmark-control-assembly-v0.1",
        "ok": True,
        "control_plan_id": control_plan["control_plan_id"],
        "control_plan_digest": control_plan["control_plan_digest"],
        "control_plan_path": paths["benchmark-control-plan.json"],
        "routing_control_count": len(control_plan["routing_controls"]),
        "behavioral_control_count": len(control_plan["behavioral_controls"]),
        "automatic_tool_execution": False,
        "receipt_persistence": "not_performed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay prepared TMCP composition inputs into an explicit control plan. "
            "This command never executes host tools or writes receipts."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    control_parser = subparsers.add_parser("control-plan")
    control_parser.add_argument("--run-plan", required=True, type=Path)
    control_parser.add_argument("--semantic-proposals", required=True, type=Path)
    control_parser.add_argument("--output-dir", required=True, type=Path)
    control_parser.add_argument(
        "--routing-golden",
        type=Path,
        default=PLUGIN_ROOT
        / "tests"
        / "fixtures"
        / "composition_routing_golden_v0_6.json",
    )
    control_parser.add_argument(
        "--behavioral-fixtures",
        type=Path,
        default=PLUGIN_ROOT
        / "tests"
        / "fixtures"
        / "composition_behavioral_fixtures_v0_6.json",
    )
    args = parser.parse_args()
    try:
        if args.command != "control-plan":
            raise ValueError(f"Unsupported benchmark assembly command: {args.command}")
        result = assemble_control_plan(
            run_plan_path=args.run_plan,
            semantic_proposals_path=args.semantic_proposals,
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
