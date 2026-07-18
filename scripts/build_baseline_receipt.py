#!/usr/bin/env python3
"""Build a digest-bound receipt that can gate a later causal campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tmcp_skill_eval_campaign_planning import (  # noqa: E402
    BASELINE_RECEIPT_SCHEMA,
    _json_sha256,
)
from tmcp_runtime.services.evaluation_evidence import (  # noqa: E402
    baseline_reliability_summary,
)
from tmcp_runtime.services.evaluation_plan import displayed_content_digest  # noqa: E402


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def _load_list(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Expected a JSON object list in {path}.")
    return value


def _control_rows(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    experiment = plan.get("experiment")
    policy = experiment.get("campaign_policy") if isinstance(experiment, Mapping) else None
    baseline = policy.get("baseline_reliability") if isinstance(policy, Mapping) else None
    control_variant = str(
        baseline.get("control_variant") if isinstance(baseline, Mapping) else "original"
    )
    rows = [
        dict(row)
        for row in plan.get("task_matrix", [])
        if isinstance(row, Mapping) and row.get("variant_id") == control_variant
    ]
    if not rows:
        raise ValueError("Baseline plan has no original-only control rows.")
    if len({str(row.get("task_id") or "") for row in rows}) != len(rows):
        raise ValueError("Baseline plan has duplicate control fixture rows.")
    return rows


def _status_from_report(report: Mapping[str, Any], *, role: str) -> str:
    scorecard = report.get("scorecard")
    surface = scorecard.get(role) if isinstance(scorecard, Mapping) else None
    if not isinstance(surface, Mapping):
        return "not_applicable"
    if role == "safety":
        regressions = surface.get("regressions")
        return "clear" if regressions in {0, 0.0, None} else "regression"
    source = surface.get("source")
    if source == "condition_blind_cost_rejudgment":
        regressions = surface.get("adjudicated_regressions")
        return "clear" if regressions in {0, 0.0} else "regression"
    if surface.get("raw_regressions") in {0, 0.0}:
        return "not_applicable"
    return "regression"


def build_baseline_receipt(
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
    traces: Sequence[Mapping[str, Any]],
    report: Mapping[str, Any],
    *,
    plan_path: Path,
    manifest_path: Path,
    traces_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    """Build a receipt without altering any source evidence."""

    summary = baseline_reliability_summary(plan, traces)
    if summary is None:
        raise ValueError("Receipt source plan is not a baseline reliability plan.")
    rows = _control_rows(plan)
    experiment = plan.get("experiment")
    if not isinstance(experiment, Mapping):
        raise ValueError("Receipt source plan has no experiment object.")
    policy = experiment.get("campaign_policy")
    if not isinstance(policy, Mapping):
        raise ValueError("Receipt source plan has no campaign policy.")
    runner_configurations = [
        dict(item)
        for item in policy.get("runner_configurations", [])
        if isinstance(item, Mapping)
    ]
    judge_configuration = policy.get("judge_configuration")
    if not isinstance(judge_configuration, Mapping):
        raise ValueError("Receipt source plan has no independent judge configuration.")
    compatibility = {
        "control_variant": str(summary["control_variant"]),
        "fixture_digests": sorted(
            {str(row.get("fixture_digest") or "") for row in rows}
        ),
        "task_evidence_digests": sorted(
            {displayed_content_digest(str(row.get("prompt") or "")) for row in rows}
        ),
        "control_attachment_digests": sorted(
            {
                displayed_content_digest(str(row.get("skill_attachment") or ""))
                for row in rows
            }
        ),
        "source_digests": sorted(
            {
                str(row.get("skill_digest") or "")
                for row in rows
                if str(row.get("skill_digest") or "")
            }
        ),
        "packet_digests": sorted(
            {
                str((row.get("composition_provenance") or {}).get("packet_sha256"))
                for row in rows
                if isinstance(row.get("composition_provenance"), Mapping)
                and (row.get("composition_provenance") or {}).get("packet_sha256")
            }
        ),
        "analysis_policy_sha256": _json_sha256(experiment.get("analysis_policy") or {}),
        "control_thresholds": (
            experiment.get("promotion_thresholds") or {}
        ).get("controlled_multi_agent_eval", {}),
        "runner_configurations": runner_configurations,
        "judge_configuration": dict(judge_configuration),
    }
    manifest_cell_count = manifest.get("cell_count")
    completed = (
        len(traces) == manifest_cell_count
        and summary.get("total") == manifest_cell_count
        and summary.get("valid_case_verdicts") == summary.get("total")
    )
    return {
        "schema": BASELINE_RECEIPT_SCHEMA,
        "evidence_state": "completed" if completed else "incomplete",
        "causal_applicable": False,
        "meets_predeclared_floors": summary.get("meets_predeclared_floors") is True,
        "control_variant": str(summary["control_variant"]),
        "compatibility": compatibility,
        "evidence": {
            "plan_sha256": _sha256_file(plan_path),
            "manifest_sha256": _sha256_file(manifest_path),
            "traces_sha256": _sha256_file(traces_path),
            "report_sha256": _sha256_file(report_path),
        },
        "counts": {
            "fixture_count": len(rows),
            "fixture_family_count": len(
                {str(row.get("fixture_family") or "") for row in rows}
            ),
            "per_fixture": summary.get("per_fixture", []),
            "per_runner_model": summary.get("per_runner_model", []),
        },
        "safety": {
            "raw_status": (
                "clear" if summary.get("raw_safety_regressions") == 0 else "regression"
            ),
            "adjudicated_status": _status_from_report(report, role="safety"),
        },
        "cost": {
            "raw_status": (
                "clear" if summary.get("raw_cost_regressions") == 0 else "regression"
            ),
            "adjudicated_status": _status_from_report(report, role="cost"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_baseline_receipt(
        _load_object(args.plan),
        _load_object(args.manifest),
        _load_list(args.traces),
        _load_object(args.report),
        plan_path=args.plan,
        manifest_path=args.manifest,
        traces_path=args.traces,
        report_path=args.report,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
