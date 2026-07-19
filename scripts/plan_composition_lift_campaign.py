#!/usr/bin/env python3
"""Derive a pure no-call composition-lift campaign from frozen controls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.schema_contract_support import (  # noqa: E402
    SchemaAssertionError,
    assert_matches_schema,
)
from tmcp_runtime.domain.composition_lift_campaign import (  # noqa: E402
    build_composition_lift_campaign,
)
from tmcp_runtime.domain.composition_benchmark_replay import (  # noqa: E402
    validate_benchmark_control_plan,
)


MAX_INPUT_BYTES = 8_000_000
SCHEMAS = PLUGIN_ROOT / "schemas"


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{label} exceeds {MAX_INPUT_BYTES} bytes.")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return payload


def plan_campaign(
    *,
    control_plan_path: Path,
    run_plan_path: Path,
    semantic_proposals_path: Path,
    routing_golden_path: Path,
    behavioral_fixtures_path: Path,
) -> dict[str, Any]:
    """Validate replay-bound inputs and return a plan without writing artifacts."""

    control_plan = _read_object(control_plan_path, label="benchmark control plan")
    run_plan = _read_object(run_plan_path, label="benchmark run plan")
    semantic_proposals = _read_object(
        semantic_proposals_path,
        label="semantic proposal bundle",
    )
    routing_golden = _read_object(routing_golden_path, label="routing golden")
    behavioral_fixtures = _read_object(
        behavioral_fixtures_path,
        label="behavioral fixtures",
    )
    for payload, schema_name in (
        (control_plan, "tmcp-composition-benchmark-control-plan-v0.1.schema.json"),
        (run_plan, "tmcp-composition-benchmark-run-plan-v0.1.schema.json"),
        (
            semantic_proposals,
            "tmcp-composition-benchmark-semantic-proposals-v0.1.schema.json",
        ),
        (routing_golden, "tmcp-composition-routing-golden-v0.1.schema.json"),
        (
            behavioral_fixtures,
            "tmcp-composition-behavioral-fixtures-v0.1.schema.json",
        ),
    ):
        assert_matches_schema(payload, SCHEMAS / schema_name)
    validate_benchmark_control_plan(
        control_plan,
        run_plan=run_plan,
        semantic_proposals=semantic_proposals,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
    )
    return build_composition_lift_campaign(control_plan)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plan a pilot-only composition-lift campaign from a compiler-issued "
            "benchmark control plan. This command makes no model or tool calls and "
            "never writes receipts or campaign artifacts."
        )
    )
    parser.add_argument("--control-plan", required=True, type=Path)
    parser.add_argument("--run-plan", required=True, type=Path)
    parser.add_argument("--semantic-proposals", required=True, type=Path)
    parser.add_argument("--routing-golden", required=True, type=Path)
    parser.add_argument("--behavioral-fixtures", required=True, type=Path)
    args = parser.parse_args()
    try:
        campaign = plan_campaign(
            control_plan_path=args.control_plan,
            run_plan_path=args.run_plan,
            semantic_proposals_path=args.semantic_proposals,
            routing_golden_path=args.routing_golden,
            behavioral_fixtures_path=args.behavioral_fixtures,
        )
    except (OSError, SchemaAssertionError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(campaign, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
