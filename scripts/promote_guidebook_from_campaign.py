#!/usr/bin/env python3
"""Emit a manual-review guidebook candidate from replicated lift evidence.

This command is deliberately non-mutating. It requires a completed host run,
trusted primary evaluation, and an independent rejudge bound to the same raw
artifacts before a held pattern can become eligible for human review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.schema_contract_support import SchemaAssertionError, assert_matches_schema  # noqa: E402
from tmcp_runtime.domain.composition_lift_campaign_results import (  # noqa: E402
    validate_campaign_host_results,
)
from tmcp_runtime.domain.guidebook_promotion import (  # noqa: E402
    build_guidebook_promotion_candidate,
    score_rejudge,
    validate_independent_rejudge,
)


SCHEMAS = PLUGIN_ROOT / "schemas"
MAX_INPUT_BYTES = 32 * 1024 * 1024


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{label} exceeds {MAX_INPUT_BYTES} bytes.")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return payload


def build_candidate_from_paths(
    *,
    campaign_path: Path,
    host_results_path: Path,
    primary_evaluator_path: Path,
    summary_path: Path,
    rejudge_path: Path,
    catalog_path: Path,
    pattern_ids: list[str],
) -> dict[str, Any]:
    campaign = _read_object(campaign_path, label="campaign")
    host_results = _read_object(host_results_path, label="host results")
    primary_evaluator = _read_object(primary_evaluator_path, label="primary evaluator")
    summary = _read_object(summary_path, label="composition summary")
    rejudge = _read_object(rejudge_path, label="independent rejudge")
    catalog = _read_object(catalog_path, label="guidebook catalog")

    assert_matches_schema(
        campaign, SCHEMAS / "tmcp-composition-lift-campaign-v0.1.schema.json"
    )
    assert_matches_schema(
        host_results, SCHEMAS / "tmcp-composition-lift-host-results-v0.1.schema.json"
    )
    assert_matches_schema(
        primary_evaluator,
        SCHEMAS / "tmcp-composition-lift-evaluator-artifacts-v0.1.schema.json",
    )
    assert_matches_schema(
        summary, SCHEMAS / "tmcp-composition-lift-summary-v0.1.schema.json"
    )
    assert_matches_schema(
        rejudge, SCHEMAS / "tmcp-composition-lift-rejudge-envelope-v0.1.schema.json"
    )

    host_cells = validate_campaign_host_results(campaign, host_results)
    rejudge_result = validate_independent_rejudge(
        campaign,
        host_cells,
        primary_evaluator,
        rejudge,
    )
    rejudge_summary = score_rejudge(campaign, host_results, rejudge["artifacts"])
    candidate = build_guidebook_promotion_candidate(
        campaign=campaign,
        summary=summary,
        rejudge_summary=rejudge_summary,
        primary_evaluator=primary_evaluator,
        rejudge_envelope=rejudge,
        pattern_ids=pattern_ids,
        catalog=catalog,
        agreement=rejudge_result["agreement"],
    )
    assert_matches_schema(
        candidate, SCHEMAS / "tmcp-guidebook-promotion-candidate-v0.1.schema.json"
    )
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--host-results", required=True, type=Path)
    parser.add_argument("--primary-evaluator", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--rejudge", required=True, type=Path)
    parser.add_argument(
        "--catalog", type=Path, default=PLUGIN_ROOT / "docs/SKILL_PATTERN_CATALOG.json"
    )
    parser.add_argument("--pattern-id", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        candidate = build_candidate_from_paths(
            campaign_path=args.campaign,
            host_results_path=args.host_results,
            primary_evaluator_path=args.primary_evaluator,
            summary_path=args.summary,
            rejudge_path=args.rejudge,
            catalog_path=args.catalog,
            pattern_ids=args.pattern_id,
        )
    except (OSError, SchemaAssertionError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"ok": True, **candidate}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
