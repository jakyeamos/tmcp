"""Pure evaluator mode orchestration over injected plan/report boundaries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


EvaluationPlanBuilder = Callable[[dict[str, Any]], dict[str, Any]]
EvaluationPlanLoader = Callable[[dict[str, Any]], dict[str, Any]]
EvaluationReportBuilder = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
EvaluationArtifactWriter = Callable[
    [dict[str, Any] | None, dict[str, Any] | None], dict[str, str]
]


def evaluate_mode(
    arguments: dict[str, Any],
    *,
    build_plan: EvaluationPlanBuilder,
    load_plan: EvaluationPlanLoader,
    build_report: EvaluationReportBuilder,
    artifact_writer: EvaluationArtifactWriter | None = None,
) -> dict[str, Any]:
    """Select and run one evaluator mode without owning I/O or persistence."""

    mode = str(arguments.get("mode") or "auto")
    if mode == "auto":
        mode = "score" if bool(arguments.get("run_evidence_json")) else "plan"

    if mode == "plan":
        plan = build_plan(arguments)
        result: dict[str, Any] = {"mode": "plan", **plan}
        if bool(arguments.get("write_artifacts", False)):
            if artifact_writer is None:
                raise ValueError(
                    "Evaluation artifact persistence requires the TMCP adapter."
                )
            result["artifact_paths"] = artifact_writer(plan, None)
        return result

    if mode == "score":
        plan = load_plan(arguments)
        report = build_report(arguments, plan)
        result = {"mode": "score", **report}
        if bool(arguments.get("write_artifacts", False)):
            if artifact_writer is None:
                raise ValueError(
                    "Evaluation artifact persistence requires the TMCP adapter."
                )
            result["artifact_paths"] = artifact_writer(plan, report)
        return result

    raise ValueError(f"Unsupported mode: {mode}")
