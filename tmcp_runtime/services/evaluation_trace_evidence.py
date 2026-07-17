"""Trace validation and controlled-record assembly for evaluation evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def validated_case_verdict(
    trace: Mapping[str, Any],
) -> tuple[bool | None, list[str]]:
    """Validate the minimum judge verdict required for evidence scoring."""

    verdict = trace.get("case_verdict")
    gaps: list[str] = []
    if not isinstance(verdict, Mapping):
        return None, ["case_verdict is missing"]
    passed = verdict.get("passed")
    if not isinstance(passed, bool):
        gaps.append("case_verdict.passed must be boolean")
    evidence = verdict.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        gaps.append("case_verdict.evidence must be a non-empty list")
    elif not all(
        isinstance(item, Mapping) or (isinstance(item, str) and item.strip())
        for item in evidence
    ):
        gaps.append("case_verdict.evidence contains an invalid item")
    return (passed if isinstance(passed, bool) else None), gaps


def _controlled_trace_gaps(
    trace: Mapping[str, Any], row: Mapping[str, Any]
) -> list[str]:
    gaps: list[str] = []
    supplied = trace.get("_controlled_fields_supplied")
    for field in ("trace_id", "experiment_id", "matrix_row_id", "replicate_id"):
        explicitly_missing = (
            isinstance(supplied, Mapping) and supplied.get(field) is False
        )
        if (
            explicitly_missing
            or trace.get(field) is None
            or str(trace.get(field)).strip() == ""
        ):
            gaps.append(f"{field} is missing")
    agent = trace.get("agent")
    if (
        not isinstance(agent, Mapping)
        or not str(agent.get("configuration_id") or "").strip()
    ):
        gaps.append("agent.configuration_id is missing")
    provenance = trace.get("provenance")
    for field in ("runner_blinded", "judge_blinded", "isolated_session"):
        if not isinstance(provenance, Mapping) or provenance.get(field) is not True:
            gaps.append(f"provenance.{field} must be true")
    if (
        row.get("pattern_id") == "composition.source-bundle-inclusion"
        and (
            not isinstance(provenance, Mapping)
            or provenance.get("composition_provenance")
            != row.get("composition_provenance")
        )
    ):
        gaps.append("provenance.composition_provenance does not match matrix row")
    _, verdict_gaps = validated_case_verdict(trace)
    gaps.extend(verdict_gaps)
    return gaps


def _row_by_id(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("matrix_row_id")): dict(row)
        for row in plan.get("task_matrix", [])
        if isinstance(row, Mapping) and str(row.get("matrix_row_id") or "")
    }


def _configuration_id(trace: Mapping[str, Any], *, controlled: bool) -> str:
    agent = trace.get("agent")
    if isinstance(agent, Mapping):
        configured = str(agent.get("configuration_id") or "").strip()
        if configured:
            return configured
        if not controlled:
            name = str(agent.get("name") or "unspecified")
            model = str(agent.get("model") or "unspecified")
            return f"{name}:{model}"
    return "uncontrolled"


def records_for_plan(
    plan: Mapping[str, Any], traces: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Bind supplied traces to rows and mark controlled-evidence gaps."""

    rows = _row_by_id(plan)
    records: list[dict[str, Any]] = []
    seen_cells: set[tuple[str, str, str]] = set()
    for trace in traces:
        row_id = str(trace.get("matrix_row_id") or "")
        row = rows.get(row_id)
        if row is None:
            continue
        controlled_gaps = _controlled_trace_gaps(trace, row)
        controlled = not controlled_gaps
        configuration_id = _configuration_id(trace, controlled=controlled)
        agent = trace.get("agent")
        runner_model = (
            str(agent.get("model") or "").strip() if isinstance(agent, Mapping) else ""
        )
        replicate_id = str(trace.get("replicate_id") or "")
        if controlled:
            cell = (row_id, configuration_id, replicate_id)
            if cell in seen_cells:
                raise ValueError(
                    "Duplicate controlled evaluation cell: "
                    f"matrix_row_id={row_id}, configuration_id={configuration_id}, "
                    f"replicate_id={replicate_id}."
                )
            seen_cells.add(cell)
        passed, verdict_gaps = validated_case_verdict(trace)
        records.append(
            {
                "trace": trace,
                "row": row,
                "passed": passed,
                "verdict_gaps": verdict_gaps,
                "controlled": controlled,
                "controlled_gaps": controlled_gaps,
                "configuration_id": configuration_id,
                "runner_model": runner_model,
            }
        )
    return records
