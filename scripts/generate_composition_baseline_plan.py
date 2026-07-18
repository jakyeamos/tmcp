#!/usr/bin/env python3
"""Derive the exact original-only baseline plan for a composition study."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tmcp_runtime.api.evaluation import validate_evaluation_plan  # noqa: E402


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def _stable_baseline_id(source_plan: dict[str, Any], control_rows: list[dict[str, Any]]) -> str:
    experiment = source_plan.get("experiment")
    source_id = experiment.get("experiment_id") if isinstance(experiment, dict) else None
    payload = {
        "source_experiment_id": source_id,
        "control_rows": control_rows,
        "campaign_policy": experiment.get("campaign_policy")
        if isinstance(experiment, dict)
        else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "composition-baseline-" + hashlib.sha256(encoded).hexdigest()[:16]


def build_baseline_plan(source_plan: dict[str, Any]) -> dict[str, Any]:
    """Create a baseline-reliability plan without changing source evidence."""

    validate_evaluation_plan(source_plan)
    experiment = source_plan.get("experiment")
    if not isinstance(experiment, dict):
        raise ValueError("Source composition plan has no experiment object.")
    policy = experiment.get("campaign_policy")
    if not isinstance(policy, dict) or policy.get("design") != "causal_contrast":
        raise ValueError("Source composition plan must be a causal contrast plan.")
    dependency = experiment.get("baseline_dependency")
    if not isinstance(dependency, dict) or dependency.get("required") is not True:
        raise ValueError("Source composition plan must require a baseline receipt.")
    control_variant = str(
        (policy.get("baseline_reliability") or {}).get("control_variant") or ""
    )
    if not control_variant:
        raise ValueError("Source composition plan has no baseline control variant.")
    task_matrix = source_plan.get("task_matrix")
    if not isinstance(task_matrix, list):
        raise ValueError("Source composition plan has no task matrix.")
    control_rows = [
        row
        for row in task_matrix
        if isinstance(row, dict) and row.get("variant_id") == control_variant
    ]
    if len(control_rows) != len({str(row.get("task_id") or "") for row in control_rows}):
        raise ValueError("Source composition plan has duplicate control fixtures.")
    if len(control_rows) < 3:
        raise ValueError("Baseline plan requires at least three reviewed fixtures.")
    baseline_id = _stable_baseline_id(source_plan, control_rows)
    baseline_plan = copy.deepcopy(source_plan)
    baseline_experiment = baseline_plan["experiment"]
    baseline_experiment["experiment_id"] = baseline_id
    baseline_experiment["campaign_policy"]["design"] = "baseline_reliability"
    baseline_experiment.pop("baseline_dependency", None)
    baseline_experiment["baseline_source_experiment_id"] = experiment["experiment_id"]
    baseline_experiment["study_phase"] = "baseline_reliability"
    cost_policy = baseline_experiment.get("cost_rejudge_policy")
    if isinstance(cost_policy, dict):
        campaign_policy = baseline_experiment.get("campaign_policy")
        cross_model = campaign_policy.get("cross_model_confirmation", {}) if isinstance(campaign_policy, dict) else {}
        runner_count = len(campaign_policy.get("runner_configurations", [])) if isinstance(campaign_policy, dict) else 0
        repetitions = int(cross_model.get("minimum_repetitions_per_cell") or 1) if isinstance(cross_model, dict) else 1
        expected_trace_count = len(control_rows) * runner_count * repetitions
        cost_policy["expected_trace_count"] = expected_trace_count
        claim_boundary = str(cost_policy.get("claim_boundary") or "")
        cost_policy["claim_boundary"] = claim_boundary.replace("72 runner artifacts", f"{expected_trace_count} runner artifacts")
    for row in baseline_plan["task_matrix"]:
        row["experiment_id"] = baseline_id
    validate_evaluation_plan(baseline_plan)
    return baseline_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build_baseline_plan(_load_object(args.source_plan))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
