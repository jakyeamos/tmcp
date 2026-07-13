"""Pure evaluator trace scoring and report assembly.

All filesystem access, input redaction, and callback wiring stay outside this module.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

from tmcp_runtime.services.evaluation_packets import (
    compose_packet_for_eval_row,
    diff_packet_inclusion,
    expectations_for_plan_row as _expectations_for_plan_row,
    task_matrix_row as _task_matrix_row,
)

EVAL_TRACE_SCHEMA = "tmcp-skill-eval-trace-v0.1"
ComposeEvaluationRow = Callable[[dict[str, Any], str | None], dict[str, Any]]


def _path_name(value: str) -> str:
    return value.replace(chr(92), "/").rsplit("/", 1)[-1]


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
        "task_id": item.get("task_id"),
        "variant_id": item.get("variant_id"),
        "agent": item.get("agent") or {"name": "unspecified", "model": "unspecified"},
        "observations": observations,
        "human_labels": list(item.get("human_labels") or []),
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


def _score_activation(trace: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    text = _observation_text(trace)
    skill_terms: list[str] = []
    for skill in plan.get("evaluated_skills", []):
        skill_terms.append(_path_name(str(skill.get("skill_path"))).lower())
        skill_terms.append(str(skill.get("title") or "").lower())
    matched = [term for term in skill_terms if term and term in text]
    skill_selected = bool(matched) or any(
        label.get("observable_id") == "skill_selected" and label.get("passed")
        for label in trace.get("human_labels", [])
        if isinstance(label, dict)
    )
    false_positive = str(trace.get("variant_id")) == "baseline" and skill_selected
    false_negative = str(trace.get("variant_id")) == "original" and not skill_selected
    score = 1.0 if skill_selected else 0.0
    if false_positive:
        score = 0.0
    if false_negative:
        score = 0.0
    return {
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": score,
        "confidence": "medium",
        "signals": {
            "skill_selected": skill_selected,
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
    row = _task_matrix_row(plan, task_id, variant_id)
    if row is None:
        return {
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
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": round(score, 2),
        "confidence": "medium" if labels else "low",
        "signals": signals,
    }


def _score_outcome(trace: dict[str, Any]) -> dict[str, Any]:
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
    base = {
        "passed": 1.0,
        "partial": 0.5,
        "failed": 0.0,
    }.get(outcome, 0.5 if outcome else 0.3)
    if human_quality is not None:
        base = max(0.0, min(1.0, human_quality / 5.0))
    return {
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": round(base, 2),
        "confidence": "medium" if human_quality is not None else "low",
        "signals": {
            "tests_passed": outcome == "passed",
            "fewer_unrelated_changes": labels.get("fewer_unrelated_changes"),
            "better_citations": labels.get("better_citations"),
            "fewer_user_corrections": labels.get("fewer_user_corrections"),
            "human_quality_score": human_quality,
        },
    }


def _score_cost(trace: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    variant_id = str(trace.get("variant_id") or "")
    matrix_rows = [
        row
        for row in plan.get("task_matrix", [])
        if row.get("task_id") == trace.get("task_id")
        and row.get("variant_id") == trace.get("variant_id")
    ]
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


def _aggregate_dimension(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {"score": 0.0, "confidence": "low"}
    avg = sum(float(item.get("score") or 0.0) for item in scores) / len(scores)
    confidences = {str(item.get("confidence") or "low") for item in scores}
    confidence = (
        "high"
        if confidences == {"high"}
        else "medium"
        if "medium" in confidences
        else "low"
    )
    return {"score": round(avg, 2), "confidence": confidence}


def _evidence_level_from_traces(traces: list[dict[str, Any]]) -> str:
    if not traces:
        return "static_review"
    agent_names = {
        str((trace.get("agent") or {}).get("name") or "").strip() for trace in traces
    }
    agent_models = {
        str((trace.get("agent") or {}).get("model") or "").strip() for trace in traces
    }
    named_agents = {name for name in agent_names if name and name != "unspecified"}
    named_models = {model for model in agent_models if model and model != "unspecified"}
    if len(named_agents) > 1 or len(named_models) > 1:
        return "controlled_multi_agent_eval"
    return "controlled_single_agent_eval"


def _guidebook_entries(
    plan: dict[str, Any],
    traces: list[dict[str, Any]],
    anti_patterns: list[dict[str, Any]],
    pattern_effects: list[dict[str, Any]],
    *,
    effective_patterns: list[dict[str, Any]],
    anti_pattern_catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    evidence_level = _evidence_level_from_traces(traces)
    for pattern in effective_patterns:
        entries.append(
            {
                "title": pattern["label"],
                "status": "recommended",
                "evidence_level": evidence_level,
                "applies_to": list(pattern.get("applies_to") or ()),
                "internal_atoms": list(pattern["internal_atoms"]),
                "prefer": pattern["good_example"],
                "avoid": pattern["weak_example"],
            }
        )
    for finding in anti_patterns:
        pattern = next(
            (
                item
                for item in anti_pattern_catalog
                if item["pattern_id"] == finding["pattern_id"]
            ),
            None,
        )
        if not pattern:
            continue
        entries.append(
            {
                "title": pattern["label"],
                "status": "avoid",
                "evidence_level": finding.get("evidence_level", "static_review"),
                "applies_to": ["skill_writing"],
                "internal_atoms": list(pattern["internal_atoms"]),
                "prefer": pattern["good_example"],
                "avoid": pattern["weak_example"],
                "source_skill": finding.get("skill_path"),
            }
        )
    if not entries:
        entries.append(
            {
                "title": "Evidence levels and confidence",
                "status": "informational",
                "evidence_level": "hypothesis",
                "applies_to": ["skill_writing"],
                "internal_atoms": [],
                "prefer": "Label guidebook claims with evidence levels.",
                "avoid": "Claim a pattern is production-proven after one static review.",
            }
        )
    return entries


def _harvest_feedback(
    anti_patterns: list[dict[str, Any]],
    *,
    anti_pattern_catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    for finding in anti_patterns:
        pattern = next(
            (
                item
                for item in anti_pattern_catalog
                if item["pattern_id"] == finding["pattern_id"]
            ),
            None,
        )
        if not pattern:
            continue
        feedback.append(
            {
                "pattern_id": pattern["pattern_id"],
                "classification": pattern["classification"],
                "suggested_harvest_warning": pattern["suggested_harvest_warning"],
                "suggested_detection_terms": list(pattern["detection_terms"]),
                "safe_to_auto_warn": pattern["safe_to_auto_warn"],
                "safe_to_auto_rewrite": pattern["safe_to_auto_rewrite"],
            }
        )
    return feedback


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
    pattern_effects: list[dict[str, Any]] = []
    for skill in plan.get("evaluated_skills", []):
        for finding in skill.get("static_findings", []):
            entry = dict(finding)
            if finding.get("classification") == "anti_pattern":
                anti_patterns.append(entry)
            if finding.get("classification") == "effective_pattern":
                pattern_effects.append(entry)

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

    guidebook_entries = _guidebook_entries(
        plan,
        traces,
        anti_patterns,
        pattern_effects,
        effective_patterns=effective_patterns,
        anti_pattern_catalog=anti_pattern_catalog,
    )
    harvest_feedback = _harvest_feedback(
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
        "activation": _aggregate_dimension(activation_scores),
        "packet_inclusion": _aggregate_dimension(packet_scores),
        "adherence": _aggregate_dimension(adherence_scores),
        "outcome_lift": _aggregate_dimension(outcome_scores),
        "cost": _aggregate_dimension(cost_scores),
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
        "cost_scores": cost_scores,
        "pattern_effects": pattern_effects,
        "anti_patterns": anti_patterns,
        "no_op_patterns": no_op_patterns,
        "recommended_rewrites": recommended_rewrites,
        "guidebook_entries": guidebook_entries,
        "skill_harvest_feedback": harvest_feedback,
        "promotion_policy": {
            "auto_promote": False,
            "applied_changes": [],
            "notes": "v0.1 never auto-promotes evaluation findings.",
        },
    }
