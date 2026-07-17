"""Evaluator request adapter over safe inputs and pure runtime services."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tmcp_runtime.safety import read_json_input, read_skill_inputs, redact_json_value
from tmcp_runtime.services.evaluation_catalog import (
    DEFAULT_VARIANTS,
    EFFECTIVE_PATTERNS,
    V01_ANTI_PATTERNS,
)
from tmcp_runtime.services.evaluation_orchestration import evaluate_mode
from tmcp_runtime.services.evaluation_plan import (
    EVAL_PLAN_SCHEMA,
    EvaluationSource,
    build_evaluation_plan_from_sources,
)
from tmcp_runtime.services.evaluation_scoring import _normalize_trace, score_traces


EVAL_REPORT_SCHEMA = "tmcp-skill-evaluation-report-v0.1"
EVAL_TRACE_SCHEMA = "tmcp-skill-eval-trace-v0.1"
MAX_EVALUATION_PLAN_BYTES = 8_388_608
MAX_EVALUATION_TASK_FIXTURES = 64
MAX_EVALUATION_VARIANTS = 32
MAX_EVALUATION_MATRIX_ROWS = 4096
MAX_EVALUATION_TRACES = 256
MAX_EVALUATION_OBSERVATIONS_PER_TRACE = 256
MAX_EVALUATION_INPUT_BYTES = MAX_EVALUATION_PLAN_BYTES

ComposeEvaluationRow = Callable[[dict[str, Any], str | Path | None], dict[str, Any]]
EvaluationArtifactWriter = Callable[
    [dict[str, Any] | None, dict[str, Any] | None], dict[str, str]
]


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _merge_redactions(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def _json_text(payload: Any, *, label: str) -> str:
    try:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be JSON-serializable.") from exc


def _redact_output(
    payload: dict[str, Any],
    redactions: dict[str, int] | None = None,
) -> dict[str, Any]:
    safe_payload, output_redactions = redact_json_value(payload, enabled=True)
    if not isinstance(safe_payload, dict):
        raise ValueError("Evaluation output must be a JSON object.")
    summary = dict(redactions or {})
    _merge_redactions(summary, output_redactions)
    if summary:
        safe_payload["redaction_summary"] = summary
    return safe_payload


def _safe_json_value(value: Any, redactions: dict[str, int]) -> Any:
    safe_value, value_redactions = redact_json_value(value, enabled=True)
    _merge_redactions(redactions, value_redactions)
    return safe_value


def _safe_bounded_json_value(
    value: Any,
    *,
    label: str,
    redactions: dict[str, int],
    max_bytes: int | None = None,
) -> Any:
    limit = MAX_EVALUATION_INPUT_BYTES if max_bytes is None else max_bytes
    safe_value = _safe_json_value(value, redactions)
    serialized_size = len(_json_text(safe_value, label=label).encode("utf-8"))
    if serialized_size > limit:
        raise ValueError(
            f"{label} exceeds the maximum serialized size of {limit} bytes."
        )
    return safe_value


def build_evaluation_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_skill_paths = arguments.get("skill_paths")
    if not isinstance(raw_skill_paths, list) or not raw_skill_paths:
        raise ValueError("skill_paths is required for evaluation plan generation.")
    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    if len(raw_skill_paths) > MAX_EVALUATION_TASK_FIXTURES:
        raise ValueError(
            "skill_paths exceeds the maximum evaluation source count of "
            f"{MAX_EVALUATION_TASK_FIXTURES}."
        )
    skill_inputs = read_skill_inputs(raw_skill_paths, project_path=project_path)

    redactions: dict[str, int] = {}
    for skill_input in skill_inputs:
        _merge_redactions(redactions, skill_input.redactions)

    raw_task_fixtures = arguments.get("task_fixtures")
    if not isinstance(raw_task_fixtures, list) or not raw_task_fixtures:
        raise ValueError("task_fixtures is required for evaluation plan generation.")
    task_fixtures = _safe_bounded_json_value(
        raw_task_fixtures,
        label="task_fixtures",
        redactions=redactions,
    )
    if not isinstance(task_fixtures, list) or not all(
        isinstance(item, dict) for item in task_fixtures
    ):
        raise ValueError("task_fixtures must contain objects.")
    if len(task_fixtures) > MAX_EVALUATION_TASK_FIXTURES:
        raise ValueError(
            "task_fixtures exceeds the maximum evaluation fixture count of "
            f"{MAX_EVALUATION_TASK_FIXTURES}."
        )

    raw_variants = arguments.get("variants") or list(DEFAULT_VARIANTS)
    if not isinstance(raw_variants, list):
        raise ValueError("variants must be a list of strings.")
    variants = _safe_bounded_json_value(
        raw_variants,
        label="variants",
        redactions=redactions,
    )
    if not isinstance(variants, list) or not all(
        isinstance(item, str) for item in variants
    ):
        raise ValueError("variants must be a list of strings.")
    if len(variants) > MAX_EVALUATION_VARIANTS:
        raise ValueError(
            "variants exceeds the maximum evaluation variant count of "
            f"{MAX_EVALUATION_VARIANTS}."
        )

    sources = tuple(
        EvaluationSource(display_path=str(item.display_path), text=item.text)
        for item in skill_inputs
    )
    plan = build_evaluation_plan_from_sources(
        sources,
        task_fixtures,
        variants,
        anti_patterns=V01_ANTI_PATTERNS,
        effective_patterns=EFFECTIVE_PATTERNS,
        created_at=_iso_now(),
        max_matrix_rows=MAX_EVALUATION_MATRIX_ROWS,
    )
    safe_plan = _redact_output(plan, redactions)
    if len(_json_text(safe_plan, label="Evaluation plan").encode("utf-8")) > (
        MAX_EVALUATION_PLAN_BYTES
    ):
        raise ValueError(
            "Evaluation plan exceeds the maximum serialized size of "
            f"{MAX_EVALUATION_PLAN_BYTES} bytes."
        )
    return safe_plan


def _validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != EVAL_PLAN_SCHEMA:
        raise ValueError(f"evaluation_plan schema must be {EVAL_PLAN_SCHEMA}.")
    for key in (
        "evaluated_skills",
        "task_matrix",
        "observable_behavior_contract",
        "packet_inclusion_contracts",
    ):
        value = plan.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise ValueError(f"evaluation_plan {key} must be a list of objects.")
    for index, skill in enumerate(plan["evaluated_skills"]):
        findings = skill.get("static_findings")
        if findings is not None and (
            not isinstance(findings, list)
            or not all(isinstance(item, dict) for item in findings)
        ):
            raise ValueError(
                f"evaluation_plan evaluated_skills[{index}].static_findings "
                "must be a list of objects."
            )
    for index, contract in enumerate(plan["packet_inclusion_contracts"]):
        expected = contract.get("expected")
        if expected is not None and not isinstance(expected, dict):
            raise ValueError(
                f"evaluation_plan packet_inclusion_contracts[{index}].expected "
                "must be an object."
            )
    matrix_row_ids: set[str] = set()
    for index, row in enumerate(plan["task_matrix"]):
        matrix_row_id = str(row.get("matrix_row_id") or "")
        if not matrix_row_id:
            continue
        if matrix_row_id in matrix_row_ids:
            raise ValueError(
                "evaluation_plan task_matrix contains duplicate matrix_row_id values."
            )
        matrix_row_ids.add(matrix_row_id)
        expected_contract = row.get("expected_packet_contract")
        if expected_contract is not None and not isinstance(expected_contract, dict):
            raise ValueError(
                f"evaluation_plan task_matrix[{index}].expected_packet_contract "
                "must be an object."
            )
    return plan


def _load_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    plan_input = arguments.get("evaluation_plan")
    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    redactions: dict[str, int] = {}
    if isinstance(plan_input, dict):
        plan = _safe_bounded_json_value(
            plan_input,
            label="evaluation_plan",
            redactions=redactions,
        )
        if not isinstance(plan, dict):
            raise ValueError("evaluation_plan must be a JSON object.")
    elif isinstance(plan_input, str):
        plan_input_file = read_json_input(
            plan_input,
            project_path=project_path,
            max_file_bytes=MAX_EVALUATION_PLAN_BYTES,
        )
        plan = plan_input_file.payload
        _merge_redactions(redactions, plan_input_file.redactions)
    else:
        raise ValueError("evaluation_plan is required for evidence scoring.")
    if redactions:
        existing_summary = plan.get("redaction_summary")
        summary = (
            {
                str(label): count
                for label, count in existing_summary.items()
                if isinstance(label, str) and isinstance(count, int) and count >= 0
            }
            if isinstance(existing_summary, dict)
            else {}
        )
        _merge_redactions(summary, redactions)
        plan = {**plan, "redaction_summary": summary}
    return _validate_plan(plan)


def _redact_composed_payload(payload: Any) -> dict[str, Any]:
    safe_payload, _ = redact_json_value(payload, enabled=True)
    if not isinstance(safe_payload, dict):
        raise ValueError("Data-only composition did not return an object.")
    return safe_payload


def score_evidence(
    arguments: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
) -> dict[str, Any]:
    plan = _load_plan(arguments) if plan is None else _validate_plan(plan)
    raw_evidence = arguments.get("run_evidence_json")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("run_evidence_json is required for evidence scoring.")
    if len(raw_evidence) > MAX_EVALUATION_TRACES:
        raise ValueError(
            "run_evidence_json exceeds the maximum trace count of "
            f"{MAX_EVALUATION_TRACES}."
        )
    if not all(isinstance(item, dict) for item in raw_evidence):
        raise ValueError("run_evidence_json must contain trace objects.")
    redactions: dict[str, int] = {}
    safe_evidence = _safe_bounded_json_value(
        raw_evidence,
        label="run_evidence_json",
        redactions=redactions,
    )
    if not isinstance(safe_evidence, list):
        raise ValueError("run_evidence_json must contain trace objects.")
    for index, item in enumerate(safe_evidence):
        if not isinstance(item, dict):
            raise ValueError("run_evidence_json must contain trace objects.")
        for key in ("observations", "trace"):
            observations = item.get(key)
            if observations is not None and not isinstance(observations, list):
                raise ValueError(
                    f"run_evidence_json trace {index}.{key} must be a list."
                )
            if (
                isinstance(observations, list)
                and len(observations) > MAX_EVALUATION_OBSERVATIONS_PER_TRACE
            ):
                raise ValueError(
                    f"run_evidence_json trace {index}.{key} exceeds the maximum observation count of "
                    f"{MAX_EVALUATION_OBSERVATIONS_PER_TRACE}."
                )
    traces = [_normalize_trace(item) for item in safe_evidence]
    if not traces:
        raise ValueError("run_evidence_json must contain trace objects.")
    for trace in traces:
        if not trace.get("observations"):
            raise ValueError(
                "Each evidence trace must include observable observations; "
                "prose-only summaries are rejected in v0.1."
            )

    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    report = score_traces(
        plan,
        traces,
        compose_evaluation_row=compose_evaluation_row,
        project_path=str(project_path) if project_path is not None else None,
        use_compose_packet=bool(arguments.get("compose_packet", True)),
        redact_composed=_redact_composed_payload,
        anti_pattern_catalog=list(V01_ANTI_PATTERNS),
        effective_patterns=list(EFFECTIVE_PATTERNS),
        report_schema=EVAL_REPORT_SCHEMA,
        created_at=_iso_now(),
    )
    plan_redactions = plan.get("redaction_summary")
    if isinstance(plan_redactions, dict):
        _merge_redactions(
            redactions,
            {
                str(label): count
                for label, count in plan_redactions.items()
                if isinstance(label, str) and isinstance(count, int) and count >= 0
            },
        )
    return _redact_output(report, redactions)


def evaluate_skills(
    arguments: dict[str, Any],
    *,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
    artifact_writer: EvaluationArtifactWriter | None = None,
) -> dict[str, Any]:
    return evaluate_mode(
        arguments,
        build_plan=build_evaluation_plan,
        load_plan=_load_plan,
        build_report=lambda score_arguments, plan: score_evidence(
            score_arguments,
            plan=plan,
            compose_evaluation_row=compose_evaluation_row,
        ),
        artifact_writer=artifact_writer,
    )
