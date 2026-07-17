"""Pure evaluator trace scoring and report assembly.

All filesystem access, input redaction, and callback wiring stay outside this module.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

from tmcp_runtime.services.evaluation_evidence import (
    aggregate_lift,
    analyze_pattern_evidence,
    case_scores,
    validated_case_verdict,
)
from tmcp_runtime.services.evaluation_guidebook import guidebook_entries
from tmcp_runtime.services.evaluation_packets import (
    compose_packet_for_eval_row,
    diff_packet_inclusion,
    expectations_for_plan_row as _expectations_for_plan_row,
    task_matrix_row as _task_matrix_row,
)
from tmcp_runtime.services.evaluation_reporting import (
    aggregate_dimension,
    harvest_feedback,
)

EVAL_TRACE_SCHEMA = "tmcp-skill-eval-trace-v0.1"
ComposeEvaluationRow = Callable[[dict[str, Any], str | None], dict[str, Any]]


def _normalize_trace(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("schema") == EVAL_TRACE_SCHEMA:
        raw_observations = item.get("observations")
        if not isinstance(raw_observations, list) or not all(
            isinstance(observation, dict) for observation in raw_observations
        ):
            raise ValueError(
                "Schema-tagged evaluation traces require observations as a list of objects."
            )
        agent = item.get("agent")
        if agent is not None and not isinstance(agent, dict):
            raise ValueError("Schema-tagged evaluation trace agent must be an object.")
        human_labels = item.get("human_labels")
        if human_labels is not None and (
            not isinstance(human_labels, list)
            or not all(isinstance(label, dict) for label in human_labels)
        ):
            raise ValueError(
                "Schema-tagged evaluation trace human_labels must be a list of objects."
            )
        return item
    observations: list[dict[str, Any]] = []
    if isinstance(item.get("observations"), list):
        for observation in item["observations"]:
            if isinstance(observation, dict):
                observations.append(observation)
            elif isinstance(observation, str):
                observations.append(_trace_line_to_observation(observation))
    elif isinstance(item.get("trace"), list):
        for line in item["trace"]:
            observations.append(_trace_line_to_observation(str(line)))
    normalized = {
        "schema": EVAL_TRACE_SCHEMA,
        "trace_id": item.get("trace_id"),
        "experiment_id": item.get("experiment_id"),
        "matrix_row_id": item.get("matrix_row_id"),
        "replicate_id": item.get("replicate_id"),
        "task_id": item.get("task_id"),
        "variant_id": item.get("variant_id"),
        "skill_path": item.get("skill_path"),
        "ablation_section": item.get("ablation_section"),
        "agent": item.get("agent") or {"name": "unspecified", "model": "unspecified"},
        "provenance": item.get("provenance"),
        "observations": observations,
        "human_labels": list(item.get("human_labels") or []),
        "case_verdict": item.get("case_verdict"),
        "outcome": item.get("outcome"),
    }
    if not all(isinstance(label, dict) for label in normalized["human_labels"]):
        raise ValueError("Evaluation trace human_labels must be a list of objects.")
    if not isinstance(normalized["agent"], dict):
        raise ValueError("Evaluation trace agent must be an object.")
    return normalized


def _trace_line_to_observation(line: str) -> dict[str, str]:
    lower = line.lower()
    if lower.startswith("agent read ") or " read " in lower:
        value = line.split("read", 1)[-1].strip()
        return {"kind": "file_read", "value": value}
    if "edited " in lower or "wrote " in lower or "write" in lower:
        value = line.split()[-1]
        return {"kind": "file_write", "value": value}
    if "ran " in lower or "run " in lower:
        value = line.split("ran", 1)[-1].strip() if "ran " in lower else line
        return {"kind": "command_run", "value": value}
    return {"kind": "assistant_message", "value": line}


def _observation_text(trace: dict[str, Any]) -> str:
    return "\n".join(
        str(item.get("value") or "")
        for item in trace.get("observations", [])
        if isinstance(item, dict)
    ).lower()


def _bind_trace_to_row(trace: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    matrix_row_id = str(trace.get("matrix_row_id") or "") or None
    row = _task_matrix_row(
        plan,
        str(trace.get("task_id") or ""),
        str(trace.get("variant_id") or ""),
        str(trace.get("skill_path") or "") or None,
        matrix_row_id=matrix_row_id,
        ablation_section=(
            str(trace.get("ablation_section"))
            if trace.get("ablation_section") is not None
            else None
        ),
    )
    if row is None:
        identifier = matrix_row_id or (
            f"task={trace.get('task_id')}, variant={trace.get('variant_id')}"
        )
        raise ValueError(
            f"Evaluation trace does not match the task matrix: {identifier}."
        )

    plan_experiment = plan.get("experiment")
    expected_experiment_id = (
        str(plan_experiment.get("experiment_id") or "")
        if isinstance(plan_experiment, dict)
        else ""
    )
    supplied_experiment_id = str(trace.get("experiment_id") or "")
    if (
        supplied_experiment_id
        and expected_experiment_id
        and supplied_experiment_id != expected_experiment_id
    ):
        raise ValueError("Evaluation trace experiment_id does not match the plan.")

    for field in ("task_id", "variant_id", "skill_path", "ablation_section"):
        supplied = trace.get(field)
        expected = row.get(field)
        if supplied is None or supplied == "":
            continue
        if str(supplied) != str(expected):
            raise ValueError(f"Evaluation trace {field} does not match matrix_row_id.")

    bound = dict(trace)
    bound["_controlled_fields_supplied"] = {
        field: trace.get(field) is not None and str(trace.get(field)).strip() != ""
        for field in ("trace_id", "experiment_id", "matrix_row_id", "replicate_id")
    }
    bound["experiment_id"] = expected_experiment_id or supplied_experiment_id or None
    bound["matrix_row_id"] = row.get("matrix_row_id")
    bound["task_id"] = row.get("task_id")
    bound["variant_id"] = row.get("variant_id")
    bound["skill_path"] = row.get("skill_path")
    bound["ablation_section"] = row.get("ablation_section")
    return bound


def _bind_traces_to_rows(
    traces: list[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    explicit_trace_ids: set[str] = set()
    bound: list[dict[str, Any]] = []
    for trace in traces:
        trace_id = str(trace.get("trace_id") or "")
        if trace_id:
            if trace_id in explicit_trace_ids:
                raise ValueError(f"Duplicate evaluation trace_id: {trace_id}.")
            explicit_trace_ids.add(trace_id)
        bound.append(_bind_trace_to_row(trace, plan))
    return bound


def _row_for_bound_trace(
    plan: dict[str, Any], trace: dict[str, Any]
) -> dict[str, Any] | None:
    matrix_row_id = str(trace.get("matrix_row_id") or "")
    if matrix_row_id:
        return _task_matrix_row(plan, matrix_row_id=matrix_row_id)
    return _task_matrix_row(
        plan,
        str(trace.get("task_id") or ""),
        str(trace.get("variant_id") or ""),
        str(trace.get("skill_path") or "") or None,
        ablation_section=(
            str(trace.get("ablation_section"))
            if trace.get("ablation_section") is not None
            else None
        ),
    )


def _score_activation(trace: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    text = _observation_text(trace)
    row = _row_for_bound_trace(plan, trace)
    skill_terms: list[str] = []
    if row is not None:
        skill = next(
            (
                item
                for item in plan.get("evaluated_skills", [])
                if str(item.get("skill_path")) == str(row.get("skill_path"))
            ),
            None,
        )
        if isinstance(skill, dict):
            skill_terms.append(str(skill.get("title") or "").lower())
            normalized_path = str(skill.get("skill_path") or "").replace("\\", "/")
            path_parts = [part for part in normalized_path.split("/") if part]
            if len(path_parts) > 1:
                skill_terms.append(path_parts[-2].lower())
    matched = [term for term in skill_terms if term and term in text]
    skill_selected = bool(matched) or any(
        label.get("observable_id") == "skill_selected" and label.get("passed")
        for label in trace.get("human_labels", [])
        if isinstance(label, dict)
    )
    should_select = str(trace.get("variant_id")) not in {
        "baseline",
        "negative_control",
    }
    false_positive = not should_select and skill_selected
    false_negative = should_select and not skill_selected
    score = 1.0 if skill_selected == should_select else 0.0
    return {
        "matrix_row_id": trace.get("matrix_row_id"),
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": score,
        "confidence": "medium",
        "signals": {
            "skill_selected": skill_selected,
            "skill_should_be_selected": should_select,
            "matched_trigger_terms": matched,
            "false_positive_activation": false_positive,
            "false_negative_activation": false_negative,
        },
    }


def _score_packet_inclusion(
    trace: dict[str, Any],
    plan: dict[str, Any],
    *,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
    compose_cache: dict[str, dict[str, Any]] | None = None,
    project_path: str | None = None,
    use_compose_packet: bool = True,
    redact_composed: Callable[[Any], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task_id = str(trace.get("task_id") or "")
    variant_id = str(trace.get("variant_id") or "")
    matrix_row_id = str(trace.get("matrix_row_id") or "")
    row = _row_for_bound_trace(plan, trace)
    if row is None:
        return {
            "matrix_row_id": matrix_row_id,
            "task_id": task_id,
            "variant_id": variant_id,
            "score": 0.0,
            "confidence": "low",
            "signals": {
                "included_required_reads": False,
                "included_stop_conditions": False,
                "included_verification_gates": False,
                "ignored_sources": [],
                "conflicts": [],
            },
            "notes": "No matching task_matrix row for packet inclusion scoring.",
        }

    if use_compose_packet and compose_evaluation_row is not None:
        cache = compose_cache if compose_cache is not None else {}
        cache_key = json.dumps(
            {
                "matrix_row_id": matrix_row_id,
                "task_id": task_id,
                "variant_id": variant_id,
                "skill_path": row.get("skill_path"),
                "prompt": row.get("prompt"),
                "project_path": str(project_path) if project_path is not None else None,
            },
            sort_keys=True,
        )
        composed = cache.get(cache_key)
        try:
            if composed is None:
                composed = compose_packet_for_eval_row(
                    row,
                    compose_evaluation_row,
                    project_path=project_path,
                )
                safe_composed = (
                    redact_composed(composed) if redact_composed else composed
                )
                if not isinstance(safe_composed, dict):
                    raise ValueError("Data-only composition did not return an object.")
                composed = safe_composed
                cache[cache_key] = composed
            expectations = _expectations_for_plan_row(plan, row)
            diff = diff_packet_inclusion(
                expectations,
                composed,
                skill_path=str(row.get("skill_path") or ""),
                variant_id=variant_id,
            )
            return {
                "matrix_row_id": matrix_row_id,
                "task_id": task_id,
                "variant_id": variant_id,
                "score": diff["score"],
                "confidence": diff["confidence"],
                "signals": diff["signals"],
                "packet_inclusion_diff": diff,
                "notes": "Scored from the injected data-only tmcp_compose_packet service.",
            }
        except RuntimeError:
            pass

    text = _observation_text(trace)
    contract = plan.get("observable_behavior_contract") or []
    required_reads = "read_required_file" in {
        str(item.get("observable_id")) for item in contract
    }
    verification = "ran_required_command" in {
        str(item.get("observable_id")) for item in contract
    }
    return {
        "matrix_row_id": matrix_row_id,
        "task_id": task_id,
        "variant_id": variant_id,
        "score": 0.7,
        "confidence": "low",
        "signals": {
            "included_required_reads": required_reads
            and ("agents.md" in text or ".md" in text),
            "included_stop_conditions": "approval" in text or "ask" in text,
            "included_verification_gates": verification
            and ("test" in text or "verify" in text),
            "ignored_sources": [],
            "conflicts": [],
        },
        "notes": (
            "Packet inclusion fell back to trace approximation because compose_packet "
            "was unavailable or disabled."
        ),
    }


def _label_map(trace: dict[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for label in trace.get("human_labels", []):
        if not isinstance(label, dict):
            continue
        observable_id = str(label.get("observable_id") or "")
        if observable_id:
            result[observable_id] = bool(label.get("passed"))
    return result


def _score_adherence(trace: dict[str, Any]) -> dict[str, Any]:
    text = _observation_text(trace)
    labels = _label_map(trace)
    signals = {
        "asked_for_approval_before_edit": labels.get(
            "asked_approval_before_edit",
            "approval" in text and "before" in text,
        ),
        "read_required_file": labels.get(
            "read_required_file", ".md" in text and "read" in text
        ),
        "ran_required_command": labels.get(
            "ran_required_command", "test" in text or "pytest" in text
        ),
        "reported_pass_fail": labels.get(
            "reported_pass_fail", "pass" in text or "fail" in text
        ),
        "preserved_output_contract": labels.get(
            "preserved_output_contract", "summary" in text or "sources" in text
        ),
    }
    passed = sum(1 for value in signals.values() if value)
    score = passed / max(len(signals), 1)
    return {
        "matrix_row_id": trace.get("matrix_row_id"),
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": round(score, 2),
        "confidence": "medium" if labels else "low",
        "signals": signals,
    }


def _score_outcome(trace: dict[str, Any]) -> dict[str, Any]:
    judged_passed, verdict_gaps = validated_case_verdict(trace)
    judged = isinstance(judged_passed, bool) and not verdict_gaps
    outcome = str(trace.get("outcome") or "").lower()
    labels = _label_map(trace)
    human_quality: float | None = None
    for label in trace.get("human_labels", []):
        if not isinstance(label, dict) or label.get("human_quality_score") is None:
            continue
        try:
            human_quality = float(label["human_quality_score"])
        except (TypeError, ValueError) as exc:
            raise ValueError("human_quality_score must be numeric.") from exc
        if not math.isfinite(human_quality):
            raise ValueError("human_quality_score must be finite.")
        break
    if judged:
        base = 1.0 if judged_passed else 0.0
    else:
        base = {
            "passed": 1.0,
            "partial": 0.5,
            "failed": 0.0,
        }.get(outcome, 0.5 if outcome else 0.3)
    if human_quality is not None and not judged:
        base = max(0.0, min(1.0, human_quality / 5.0))
    return {
        "matrix_row_id": trace.get("matrix_row_id"),
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": round(base, 2),
        "confidence": (
            "high" if judged else "medium" if human_quality is not None else "low"
        ),
        "signals": {
            "case_verdict_passed": judged_passed,
            "case_verdict_valid": judged,
            "case_verdict_gaps": verdict_gaps,
            "tests_passed": outcome == "passed",
            "fewer_unrelated_changes": labels.get("fewer_unrelated_changes"),
            "better_citations": labels.get("better_citations"),
            "fewer_user_corrections": labels.get("fewer_user_corrections"),
            "human_quality_score": human_quality,
        },
    }


def _score_cost(trace: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    variant_id = str(trace.get("variant_id") or "")
    matrix_row = _row_for_bound_trace(plan, trace)
    matrix_rows = [matrix_row] if matrix_row is not None else []
    token_estimate = max(
        (len(str(row.get("skill_attachment") or "").split()) for row in matrix_rows),
        default=0,
    )
    contradictions = sum(
        1
        for skill in plan.get("evaluated_skills", [])
        for finding in skill.get("static_findings", [])
        if finding.get("pattern_id") == "approval.contradictory-edit-instructions"
    )
    overactivation = (
        "high"
        if variant_id == "negative_control"
        else "medium"
        if variant_id == "trigger-only"
        else "low"
    )
    score = 1.0
    if token_estimate > 400:
        score -= 0.2
    if contradictions:
        score -= 0.3
    if overactivation == "high":
        score -= 0.2
    return {
        "matrix_row_id": trace.get("matrix_row_id"),
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": round(max(0.0, min(1.0, score)), 2),
        "confidence": "medium",
        "signals": {
            "token_cost_delta": token_estimate,
            "unnecessary_sections": max(
                0, len(matrix_rows[0].get("skill_attachment", "").split("\n## ")) - 4
            )
            if matrix_rows
            else 0,
            "contradictions_detected": contradictions,
            "instruction_precedence_risk": any(
                finding.get("pattern_id") == "precedence.override-hazard"
                for skill in plan.get("evaluated_skills", [])
                for finding in skill.get("static_findings", [])
            ),
            "overactivation_risk": overactivation,
        },
    }


def score_traces(
    plan: dict[str, Any],
    traces: list[dict[str, Any]],
    *,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
    project_path: str | None = None,
    use_compose_packet: bool = True,
    redact_composed: Callable[[Any], dict[str, Any]] | None = None,
    anti_pattern_catalog: list[dict[str, Any]],
    effective_patterns: list[dict[str, Any]],
    report_schema: str,
    created_at: str,
) -> dict[str, Any]:
    traces = _bind_traces_to_rows(traces, plan)
    compose_cache: dict[str, dict[str, Any]] = {}
    activation_scores = [_score_activation(trace, plan) for trace in traces]
    adherence_scores = [_score_adherence(trace) for trace in traces]
    outcome_scores = [_score_outcome(trace) for trace in traces]
    packet_scores = [
        _score_packet_inclusion(
            trace,
            plan,
            compose_evaluation_row=compose_evaluation_row,
            compose_cache=compose_cache,
            project_path=project_path,
            use_compose_packet=use_compose_packet,
            redact_composed=redact_composed,
        )
        for trace in traces
    ]
    cost_scores = [_score_cost(trace, plan) for trace in traces]
    packet_inclusion_diffs = [
        item["packet_inclusion_diff"]
        for item in packet_scores
        if isinstance(item.get("packet_inclusion_diff"), dict)
    ]

    anti_patterns: list[dict[str, Any]] = []
    no_op_patterns: list[dict[str, Any]] = []
    static_findings: list[dict[str, Any]] = []
    static_pattern_effects: list[dict[str, Any]] = []
    for skill in plan.get("evaluated_skills", []):
        for finding in skill.get("static_findings", []):
            entry = dict(finding)
            static_findings.append(entry)
            if finding.get("classification") == "anti_pattern":
                anti_patterns.append(entry)
            if finding.get("classification") == "effective_pattern":
                static_pattern_effects.append(entry)

    for row in plan.get("task_matrix", []):
        if row.get("variant_id") == "negative_control":
            no_op_patterns.append(
                {
                    "pattern_id": "negative-control.stub",
                    "skill_path": row.get("skill_path"),
                    "message": "Negative control variant uses vague no-op language by design.",
                    "classification": "control",
                }
            )

    pattern_claims = analyze_pattern_evidence(plan, traces)
    judged_case_scores = case_scores(plan, traces)
    rendered_guidebook_entries = guidebook_entries(
        static_findings=static_findings,
        claims=pattern_claims,
        effective_patterns=effective_patterns,
        anti_pattern_catalog=anti_pattern_catalog,
    )
    harvest_feedback_items = harvest_feedback(
        anti_patterns,
        anti_pattern_catalog=anti_pattern_catalog,
    )
    recommended_rewrites = [
        {
            "skill_path": skill.get("skill_path"),
            "rewrite_variant": "rewritten",
            "reason": "Apply guidebook concrete gates, scannable required reads, and output contract.",
        }
        for skill in plan.get("evaluated_skills", [])
        if any(
            finding.get("pattern_id") == "verification.vague-quality-language"
            for finding in skill.get("static_findings", [])
        )
    ]

    scorecard = {
        "claim_boundary": {
            "promotion_source": "pattern_claims",
            "diagnostic_only_dimensions": [
                "activation",
                "packet_inclusion",
                "adherence",
                "cost",
                "safety",
            ],
            "notes": (
                "Only validated, behaviorally judged pattern_claims can change "
                "guidebook evidence status. Other scorecard dimensions are "
                "heuristic diagnostics and must not be read as causal effects."
            ),
        },
        "activation": aggregate_dimension(activation_scores),
        "packet_inclusion": aggregate_dimension(packet_scores),
        "adherence": aggregate_dimension(adherence_scores),
        "outcome_lift": aggregate_lift(pattern_claims),
        "cost": aggregate_dimension(cost_scores),
        "safety": {
            "score": 1.0
            if not any(
                item.get("pattern_id") == "precedence.override-hazard"
                for item in anti_patterns
            )
            else 0.4,
            "confidence": "high",
        },
    }
    return {
        "ok": True,
        "stability": "experimental",
        "schema": report_schema,
        "created_at": created_at,
        "evaluation_plan_schema": plan.get("schema"),
        "scorecard": scorecard,
        "activation_scores": activation_scores,
        "packet_inclusion_scores": packet_scores,
        "packet_inclusion_diffs": packet_inclusion_diffs,
        "adherence_scores": adherence_scores,
        "outcome_scores": outcome_scores,
        "case_scores": judged_case_scores,
        "cost_scores": cost_scores,
        "pattern_effects": static_pattern_effects,
        "pattern_claims": pattern_claims,
        "static_pattern_findings": static_findings,
        "anti_patterns": anti_patterns,
        "no_op_patterns": no_op_patterns,
        "recommended_rewrites": recommended_rewrites,
        "guidebook_entries": rendered_guidebook_entries,
        "skill_harvest_feedback": harvest_feedback_items,
        "promotion_policy": {
            "auto_promote": False,
            "applied_changes": [],
            "notes": "Evaluation findings are never auto-promoted.",
        },
    }
