#!/usr/bin/env python3
"""Verify and score a completed source-bundle composition study."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tmcp_skill_eval_campaign_protocol import (  # noqa: E402
    _atomic_json,
    _load_json,
    _sha256_file,
)
from scripts.verify_cost_rejudge import (  # noqa: E402
    VERIFICATION_SCHEMA,
    verify_cost_rejudge,
)
from tmcp_runtime.api.evaluation import score_evidence  # noqa: E402


VERIFIED_SCORE_SCHEMA = "tmcp-composition-verified-score-v0.1"


def _object(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object.")
    return value


def _trace_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or not all(
        isinstance(trace, dict) for trace in value
    ):
        raise ValueError("Source traces must be a non-empty JSON object list.")
    return value


def score_verified_study(
    *,
    plan: Mapping[str, Any],
    traces: list[dict[str, Any]],
    sidecar: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    """Score only a sidecar bundle that was verified in the same local process."""

    static = verification.get("static")
    experiment = plan.get("experiment")
    if (
        verification.get("schema") != VERIFICATION_SCHEMA
        or not isinstance(static, Mapping)
        or static.get("promotion_ready") is not True
        or not isinstance(experiment, Mapping)
        or verification.get("experiment_id") != experiment.get("experiment_id")
    ):
        raise ValueError(
            "Composition study scoring requires a promotion-ready verified sidecar."
        )
    report = score_evidence(
        {
            "evaluation_plan": dict(plan),
            "run_evidence_json": traces,
            "cost_rejudgments_json": dict(sidecar),
            "compose_packet": False,
        },
        plan=dict(plan),
    )
    return {
        "schema": VERIFIED_SCORE_SCHEMA,
        "ok": True,
        "verification": dict(verification),
        "evaluation_report": report,
    }


def _validate_output_path(
    output: Path, *, source_runs: Path, rejudge_runs: Path
) -> None:
    resolved = output.resolve()
    if resolved.exists():
        raise ValueError("Verified score output already exists; choose a new path.")
    for root in (source_runs.resolve(), rejudge_runs.resolve()):
        if resolved == root or resolved.is_relative_to(root):
            raise ValueError(
                "Verified score output must be outside source and rejudge evidence."
            )


def score_composition_study(
    *,
    source_plan: Path,
    source_runs: Path,
    cost_bar_file: Path,
    rejudge_runs: Path,
    expected_trace_count: int,
) -> dict[str, Any]:
    """Verify the persisted source/rejudge artifacts then produce one score payload."""

    verification = verify_cost_rejudge(
        source_plan=source_plan,
        source_runs=source_runs,
        cost_bar_file=cost_bar_file,
        rejudge_runs=rejudge_runs,
        expected_trace_count=expected_trace_count,
    )
    plan = _object(_load_json(source_plan), context="Source plan")
    traces_path = source_runs / "traces.json"
    sidecar_path = rejudge_runs / "cost-rejudgments.json"
    traces = _trace_list(_load_json(traces_path))
    sidecar = _object(_load_json(sidecar_path), context="Cost rejudgments sidecar")
    score = score_verified_study(
        plan=plan,
        traces=traces,
        sidecar=sidecar,
        verification=verification,
    )
    return {
        **score,
        "inputs": {
            "source_plan": str(source_plan.resolve()),
            "source_plan_sha256": _sha256_file(source_plan),
            "source_traces": str(traces_path.resolve()),
            "source_traces_sha256": _sha256_file(traces_path),
            "cost_rejudgments": str(sidecar_path.resolve()),
            "cost_rejudgments_sha256": _sha256_file(sidecar_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--source-runs", type=Path, required=True)
    parser.add_argument("--cost-bar-file", type=Path, required=True)
    parser.add_argument("--rejudge-runs", type=Path, required=True)
    parser.add_argument("--expected-trace-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        _validate_output_path(
            args.output,
            source_runs=args.source_runs,
            rejudge_runs=args.rejudge_runs,
        )
        score = score_composition_study(
            source_plan=args.source_plan,
            source_runs=args.source_runs,
            cost_bar_file=args.cost_bar_file,
            rejudge_runs=args.rejudge_runs,
            expected_trace_count=args.expected_trace_count,
        )
        _atomic_json(args.output, score)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": VERIFIED_SCORE_SCHEMA, "ok": False, "error": str(error)}))
        return 1
    print(json.dumps(score, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
