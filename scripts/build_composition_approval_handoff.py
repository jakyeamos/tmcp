#!/usr/bin/env python3
"""Build a no-call approval boundary for a composition campaign.

The handoff is deliberately separate from campaign execution.  It checks the
byte-pinned plans and their local readiness records, calculates the exact
runner, judge, and cost-rejudge counts, and leaves execution disabled until a
fresh approval is recorded outside this artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_composition_study_plan import _load_object  # noqa: E402
from tmcp_runtime.api.evaluation import validate_evaluation_plan  # noqa: E402


HANDOFF_SCHEMA = "tmcp-composition-approval-handoff-v0.1"


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": _sha256_file(path)}


def _experiment(plan: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    experiment = plan.get("experiment")
    if not isinstance(experiment, Mapping):
        raise ValueError(f"{label} plan has no experiment object.")
    return experiment


def _campaign_policy(experiment: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    policy = experiment.get("campaign_policy")
    if not isinstance(policy, Mapping):
        raise ValueError(f"{label} plan has no campaign policy.")
    return policy


def _selected_rows(
    plan: Mapping[str, Any], *, label: str, baseline: bool
) -> list[dict[str, Any]]:
    rows = plan.get("task_matrix")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{label} plan task_matrix must be an object list.")
    if not baseline:
        selected = [dict(row) for row in rows]
    else:
        policy = _campaign_policy(_experiment(plan, label), label)
        baseline_policy = policy.get("baseline_reliability")
        control_variant = (
            baseline_policy.get("control_variant")
            if isinstance(baseline_policy, Mapping)
            else None
        )
        if not isinstance(control_variant, str) or not control_variant:
            raise ValueError("baseline control variant is missing.")
        selected = [
            dict(row) for row in rows if row.get("variant_id") == control_variant
        ]
    task_ids = [str(row.get("task_id") or "") for row in selected]
    if not selected or any(not task_id for task_id in task_ids):
        raise ValueError(f"{label} plan has no usable selected fixtures.")
    identity = (
        task_ids
        if baseline
        else [
            (task_id, str(row.get("variant_id") or ""))
            for task_id, row in zip(task_ids, selected, strict=True)
        ]
    )
    if len(identity) != len(set(identity)):
        raise ValueError(f"{label} plan has duplicate selected fixtures.")
    return selected


def _counts(plan: Mapping[str, Any], *, label: str, baseline: bool) -> dict[str, Any]:
    experiment = _experiment(plan, label)
    policy = _campaign_policy(experiment, label)
    design = policy.get("design")
    expected_design = "baseline_reliability" if baseline else "causal_contrast"
    if design != expected_design:
        raise ValueError(f"{label} design must be {expected_design}.")
    configurations = policy.get("runner_configurations")
    if not isinstance(configurations, list) or not configurations:
        raise ValueError(f"{label} runner configurations are missing.")
    cross_model = policy.get("cross_model_confirmation")
    if not isinstance(cross_model, Mapping):
        raise ValueError(f"{label} cross-model policy is missing.")
    repetitions = cross_model.get("minimum_repetitions_per_cell")
    if not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError(f"{label} repetitions must be positive.")
    rows = _selected_rows(plan, label=label, baseline=baseline)
    cell_count = len(rows) * len(configurations) * repetitions
    cost_policy = experiment.get("cost_rejudge_policy")
    if not isinstance(cost_policy, Mapping):
        raise ValueError(f"{label} cost rejudge policy is missing.")
    if cost_policy.get("expected_trace_count") != cell_count:
        raise ValueError(f"{label} cost trace count does not match selected cells.")
    return {
        "experiment_id": str(experiment.get("experiment_id") or ""),
        "design": design,
        "fixture_count": len({str(row["task_id"]) for row in rows}),
        "matrix_row_count": len(rows),
        "runner_configuration_count": len(configurations),
        "repetitions_per_cell": repetitions,
        "cell_count": cell_count,
        "runner_calls": cell_count,
        "primary_judge_calls": cell_count,
        "cost_rejudge_calls": cell_count,
        "selected_task_ids": [str(row["task_id"]) for row in rows],
    }


def build_handoff(study_dir: Path, output_path: Path | None = None) -> dict[str, Any]:
    """Validate the local study package and return a no-call approval handoff."""

    study_dir = study_dir.resolve()
    generated = study_dir / "generated"
    causal_path = generated / "tmcp-composition-study-plan.json"
    baseline_path = generated / "tmcp-composition-baseline-plan.json"
    verification_path = generated / "study-verification.json"
    readiness_path = generated / "baseline-readiness-gate.json"
    paths = {
        "causal_plan": causal_path,
        "baseline_plan": baseline_path,
        "study_verification": verification_path,
        "baseline_readiness": readiness_path,
    }
    if any(not path.is_file() for path in paths.values()):
        missing = [name for name, path in paths.items() if not path.is_file()]
        raise ValueError("approval inputs are missing: " + ", ".join(missing))

    causal_plan = _load_object(causal_path)
    baseline_plan = _load_object(baseline_path)
    validate_evaluation_plan(causal_plan)
    validate_evaluation_plan(baseline_plan)
    causal_experiment = _experiment(causal_plan, "causal")
    baseline_experiment = _experiment(baseline_plan, "baseline")
    causal_id = str(causal_experiment.get("experiment_id") or "")
    baseline_id = str(baseline_experiment.get("experiment_id") or "")
    if not causal_id or not baseline_id:
        raise ValueError("approval plans must have experiment IDs.")
    if baseline_experiment.get("baseline_source_experiment_id") != causal_id:
        raise ValueError("baseline plan is not derived from the causal experiment.")

    verification = _load_object(verification_path)
    if verification.get("ok") is not True:
        raise ValueError("study verification is not successful.")
    if verification.get("experiment_id") != causal_id:
        raise ValueError("study verification experiment does not match causal plan.")
    live_sources = verification.get("live_sources")
    if not isinstance(live_sources, Mapping) or live_sources.get("status") != "matched":
        raise ValueError("study verification does not match live sources.")

    readiness = _load_object(readiness_path)
    if (
        readiness.get("ready") is not True
        or readiness.get("design") != "baseline_reliability"
    ):
        raise ValueError("baseline readiness gate is not ready.")
    if readiness.get("gaps") != []:
        raise ValueError("baseline readiness gate has unresolved gaps.")

    baseline = _counts(baseline_plan, label="baseline", baseline=True)
    causal = _counts(causal_plan, label="causal", baseline=False)
    if baseline["cell_count"] != readiness.get("cell_count"):
        raise ValueError("baseline readiness cell count does not match the plan.")
    dependency = causal_experiment.get("baseline_dependency")
    if not isinstance(dependency, Mapping) or dependency.get("required") is not True:
        raise ValueError("causal plan must require a baseline dependency.")
    if (
        dependency.get("receipt_sha256") is not None
        or dependency.get("verification_sha256") is not None
    ):
        raise ValueError("causal plan unexpectedly has completed baseline evidence.")

    handoff = {
        "schema": HANDOFF_SCHEMA,
        "study_dir": str(study_dir),
        "status": "approval_required",
        "model_calls_authorized": False,
        "execution_started": False,
        "artifacts": {
            name: {
                **_artifact(path),
                "experiment_id": causal_id
                if name == "causal_plan"
                else baseline_id
                if name == "baseline_plan"
                else None,
            }
            for name, path in paths.items()
        },
        "baseline": {
            **baseline,
            "readiness_gate": _artifact(readiness_path),
            "receipt_required_before_causal": True,
            "receipt_sha256": None,
            "verification_sha256": None,
        },
        "causal": {
            **causal,
            "baseline_receipt_required": True,
            "baseline_verification_required": True,
            "baseline_dependency_status": dependency.get("status"),
        },
        "approval_sequence": [
            "execute the 36-cell baseline runner, primary-judge, and cost-rejudge sequence",
            "independently verify the baseline receipt and evidence bundle, then bind both digests",
            "obtain separate approval for the causal 72-cell runner and primary-judge sequence",
            "obtain separate approval for the causal 72-trace condition-blind cost rejudge",
        ],
        "claim_boundary": "No behavioral or guidebook promotion claim is permitted until the preregistered baseline and causal evidence gates clear.",
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_handoff(args.study_dir, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": HANDOFF_SCHEMA, "ok": False, "error": str(error)}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
