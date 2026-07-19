#!/usr/bin/env python3
"""Score a completed cell-level composition-lift campaign without side effects."""

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
from tmcp_runtime.domain.composition_lift_campaign_scoring import (  # noqa: E402
    score_composition_lift_campaign,
)


MAX_INPUT_BYTES = 16 * 1024 * 1024
SCHEMAS = PLUGIN_ROOT / "schemas"


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{label} exceeds {MAX_INPUT_BYTES} bytes.")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return payload


def score_campaign(
    *, campaign_path: Path, host_results_path: Path, evaluator_artifacts_path: Path
) -> dict[str, Any]:
    """Score a campaign and require real host/evaluator evidence for eligibility."""

    campaign = _read_object(campaign_path, label="composition-lift campaign")
    host_results = _read_object(
        host_results_path, label="composition-lift host results"
    )
    evaluator_artifacts = _read_object(
        evaluator_artifacts_path,
        label="composition-lift evaluator artifacts",
    )
    assert_matches_schema(
        campaign,
        SCHEMAS / "tmcp-composition-lift-campaign-v0.1.schema.json",
    )
    assert_matches_schema(
        host_results,
        SCHEMAS / "tmcp-composition-lift-host-results-v0.1.schema.json",
    )
    assert_matches_schema(
        evaluator_artifacts,
        SCHEMAS / "tmcp-composition-lift-evaluator-artifacts-v0.1.schema.json",
    )
    summary = score_composition_lift_campaign(
        campaign,
        host_results,
        evaluator_artifacts,
    )
    assert_matches_schema(
        summary,
        SCHEMAS / "tmcp-composition-lift-summary-v0.1.schema.json",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Score repeated composition-lift cells. The command never executes "
            "hosts, calls models, or writes receipts; synthetic evidence cannot "
            "qualify the campaign."
        )
    )
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--host-results", required=True, type=Path)
    parser.add_argument("--evaluator-artifacts", required=True, type=Path)
    args = parser.parse_args()
    try:
        summary = score_campaign(
            campaign_path=args.campaign,
            host_results_path=args.host_results,
            evaluator_artifacts_path=args.evaluator_artifacts,
        )
    except (OSError, SchemaAssertionError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"ok": True, **summary}, indent=2, sort_keys=True))
    return 0 if summary["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
