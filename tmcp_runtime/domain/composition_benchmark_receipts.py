"""Validate runtime receipts against compiler-replayed benchmark controls."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.composition_benchmark_boundaries import (
    MAX_METADATA_CHARS,
    UTC_TIMESTAMP_RE,
    _assert_keys,
    _bounded_text,
    _finite_number,
    _mapping_list,
    _nonempty,
    _string_list,
)
from tmcp_runtime.domain.composition_benchmark_projection import (
    _receipt_quality_metrics,
)
from tmcp_runtime.domain.composition_benchmark_context import (
    validate_execution_context,
)
from tmcp_runtime.domain.composition_runtime_evidence import (
    COMPOSITION_RUNTIME_EVIDENCE_SCHEMA,
    composition_gate_catalog,
    composition_handoff_catalog,
    evaluate_composition_gates,
    evaluate_composition_handoffs,
)
from tmcp_runtime.domain.composition_runtime import transition_gate_ids
from tmcp_runtime.domain.receipts import (
    BENCHMARK_HOST_RECEIPT_MARKER,
    RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
    RECEIPT_TRUST,
)


def _validate_full_receipt_shape(receipt: Mapping[str, Any], *, field: str) -> None:
    """Enforce the recorded-receipt contract for direct domain callers too."""

    required = {
        "schema",
        "created_at",
        "packet_id",
        "activated_atoms",
        "ignored_atoms",
        "commands_run",
        "verification_results",
        "user_overrides",
        "outcome",
        "trust",
        "instruction_override_policy",
        "recipe_id",
        "task_identity",
        "graph_digest",
        "content_digests",
        "selected_skill_ids",
        "phase_trace",
        "gate_results",
        "handoff_results",
        "quality_metrics",
        "cost_metrics",
        "composition_fixture_id",
        "benchmark_control_input_digest",
        "benchmark_execution_recipe_digest",
        "benchmark_host_receipt",
        "execution_context",
    }
    missing = sorted(required.difference(receipt))
    if missing:
        raise ValueError(f"{field}.tmcp_run_receipt is missing {missing}.")
    if receipt.get("schema") != "tmcp-run-receipt-v0.1":
        raise ValueError(f"{field}.tmcp_run_receipt.schema is invalid.")
    if receipt.get("benchmark_host_receipt") != BENCHMARK_HOST_RECEIPT_MARKER:
        raise ValueError(
            f"{field}.tmcp_run_receipt is not a benchmark-host receipt."
        )
    if not isinstance(receipt.get("created_at"), str) or UTC_TIMESTAMP_RE.fullmatch(
        str(receipt.get("created_at"))
    ) is None:
        raise ValueError(f"{field}.tmcp_run_receipt.created_at must be UTC.")
    for key in ("packet_id", "recipe_id", "graph_digest", "composition_fixture_id"):
        _nonempty(receipt.get(key), field=f"{field}.tmcp_run_receipt.{key}")
    for key in ("activated_atoms", "ignored_atoms", "commands_run", "verification_results"):
        _string_list(
            receipt.get(key),
            field=f"{field}.tmcp_run_receipt.{key}",
            allow_empty=True,
        )
    if not isinstance(receipt.get("user_overrides"), list):
        raise ValueError(f"{field}.tmcp_run_receipt.user_overrides must be an array.")
    if not isinstance(receipt.get("task_identity"), Mapping):
        raise ValueError(f"{field}.tmcp_run_receipt.task_identity must be an object.")
    _string_list(
        receipt.get("content_digests"),
        field=f"{field}.tmcp_run_receipt.content_digests",
    )
    _string_list(
        receipt.get("selected_skill_ids"),
        field=f"{field}.tmcp_run_receipt.selected_skill_ids",
    )
    for key in ("phase_trace", "gate_results", "handoff_results"):
        _mapping_list(receipt.get(key), field=f"{field}.tmcp_run_receipt.{key}")
    for key in ("quality_metrics", "cost_metrics"):
        if not isinstance(receipt.get(key), Mapping):
            raise ValueError(f"{field}.tmcp_run_receipt.{key} must be an object.")
    if not isinstance(receipt.get("execution_context"), Mapping):
        raise ValueError(f"{field}.tmcp_run_receipt.execution_context must be an object.")
    if receipt.get("trust") != RECEIPT_TRUST:
        raise ValueError(f"{field}.tmcp_run_receipt.trust is invalid.")
    if receipt.get("instruction_override_policy") != RECEIPT_INSTRUCTION_OVERRIDE_POLICY:
        raise ValueError(
            f"{field}.tmcp_run_receipt.instruction_override_policy is invalid."
        )
    for key in (
        "benchmark_control_input_digest",
        "benchmark_execution_recipe_digest",
    ):
        value = str(receipt.get(key) or "")
        if re.fullmatch(r"[a-f0-9]{64}", value) is None:
            raise ValueError(f"{field}.tmcp_run_receipt.{key} must be a digest.")


def _requested_stage_index(
    stages: Sequence[Mapping[str, Any]],
    *,
    requested_phase: str,
    current_index: int,
) -> int:
    """Mirror runtime phase lookup so recorded obligations remain auditable."""

    matches = [
        index
        for index, stage in enumerate(stages)
        if str(stage.get("phase") or "") == requested_phase
    ]
    if not matches:
        raise ValueError("full receipt requested an unknown compiler phase.")
    later = [index for index in matches if index > current_index]
    if str(stages[current_index].get("phase") or "") == requested_phase:
        return later[0] if later else current_index
    return later[0] if later else matches[0]


def _transition_obligation_ids(
    plan: Mapping[str, Any],
    stages: Sequence[Mapping[str, Any]],
    *,
    current_index: int,
    requested_index: int,
) -> tuple[list[str], list[str]]:
    """Derive the exact runtime gate and handoff lists for one transition."""

    if requested_index <= current_index:
        return [], []
    entry_stage_ids = {
        _nonempty(stage.get("stage_id"), field="composition_plan.stage_id")
        for stage in stages[current_index + 1 : requested_index + 1]
    }
    gate_ids = transition_gate_ids(
        plan,
        composition_gate_catalog(plan),
        [dict(stage) for stage in stages],
        current_index,
        requested_index,
    )
    handoff_ids = [
        _nonempty(contract.get("handoff_id"), field="composition_plan.handoff_id")
        for contract in composition_handoff_catalog(plan)
        if contract.get("consumer_stage_id") in entry_stage_ids
    ]
    return gate_ids, handoff_ids


def _validate_phase_trace(
    receipt: Mapping[str, Any],
    *,
    fixture_id: str,
    plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate the actual transition records emitted by runtime recompilation."""

    stages = _mapping_list(plan.get("ordered_stages"), field="composition_plan.stages")
    expected_stage_ids = [
        _nonempty(stage.get("stage_id"), field="composition_plan.stage_id")
        for stage in stages
    ]
    stage_index = {stage_id: index for index, stage_id in enumerate(expected_stage_ids)}
    stage_phase = {
        stage_id: _nonempty(stage.get("phase"), field="composition_plan.stage.phase")
        for stage_id, stage in zip(expected_stage_ids, stages, strict=True)
    }
    trace = _mapping_list(receipt.get("phase_trace"), field="receipt.phase_trace")
    if not trace:
        raise ValueError(f"{fixture_id} full receipt phase trace is missing.")
    runtime_evidence = {
        "schema": COMPOSITION_RUNTIME_EVIDENCE_SCHEMA,
        "gate_results": receipt.get("gate_results"),
        "handoff_results": receipt.get("handoff_results"),
    }
    gate_evaluation = evaluate_composition_gates(plan, runtime_evidence)
    handoff_evaluation = evaluate_composition_handoffs(plan, runtime_evidence)
    passed_gate_ids = set(gate_evaluation["passed_gate_ids"])
    available_handoff_ids = set(handoff_evaluation["available_handoff_ids"])
    failed_handoff_ids = set(handoff_evaluation["failed_handoff_ids"])
    current_index = 0
    covered_stage_ids = {expected_stage_ids[0]}
    normalized: list[dict[str, Any]] = []
    for sequence, item in enumerate(trace, start=1):
        _assert_keys(
            item,
            field=f"receipt.phase_trace[{sequence}]",
            required={
                "sequence",
                "from_phase",
                "to_phase",
                "from_stage_id",
                "to_stage_id",
                "requested_phase",
                "status",
                "reason",
                "required_gate_ids",
                "pending_gate_ids",
                "required_handoff_ids",
                "pending_handoff_ids",
                "failed_handoff_ids",
                "override",
            },
        )
        if item.get("sequence") != sequence:
            raise ValueError(
                f"{fixture_id} full receipt phase trace sequence is invalid."
            )
        from_stage_id = _nonempty(
            item.get("from_stage_id"),
            field=f"receipt.phase_trace[{sequence}].from_stage_id",
        )
        to_stage_id = _nonempty(
            item.get("to_stage_id"),
            field=f"receipt.phase_trace[{sequence}].to_stage_id",
        )
        if from_stage_id not in stage_index or to_stage_id not in stage_index:
            raise ValueError(f"{fixture_id} full receipt phase trace has an unknown stage.")
        if stage_index[from_stage_id] != current_index:
            raise ValueError(
                f"{fixture_id} full receipt phase trace is not a contiguous compiler lineage."
            )
        from_phase = _nonempty(
            item.get("from_phase"),
            field=f"receipt.phase_trace[{sequence}].from_phase",
        )
        to_phase = _nonempty(
            item.get("to_phase"),
            field=f"receipt.phase_trace[{sequence}].to_phase",
        )
        if from_phase != stage_phase[from_stage_id] or to_phase != stage_phase[to_stage_id]:
            raise ValueError(
                f"{fixture_id} full receipt phase trace phases do not match compiler stages."
            )
        requested_phase = _bounded_text(
            item.get("requested_phase"),
            field=f"receipt.phase_trace[{sequence}].requested_phase",
            maximum=MAX_METADATA_CHARS,
        )
        if requested_phase not in set(stage_phase.values()):
            raise ValueError(
                f"{fixture_id} full receipt requested an unknown compiler phase."
            )
        requested_index = _requested_stage_index(
            stages,
            requested_phase=requested_phase,
            current_index=current_index,
        )
        expected_gate_ids, expected_handoff_ids = _transition_obligation_ids(
            plan,
            stages,
            current_index=current_index,
            requested_index=requested_index,
        )
        status = _nonempty(
            item.get("status"), field=f"receipt.phase_trace[{sequence}].status"
        ).lower()
        if item.get("override") is not None or status in {
            "advanced_with_override",
            "reverted",
        }:
            raise ValueError(f"{fixture_id} full receipt cannot use phase overrides.")
        to_index = stage_index[to_stage_id]
        required_gate_ids = _string_list(
            item.get("required_gate_ids"),
            field=f"receipt.phase_trace[{sequence}].required_gate_ids",
            allow_empty=True,
        )
        pending_gate_ids = _string_list(
            item.get("pending_gate_ids"),
            field=f"receipt.phase_trace[{sequence}].pending_gate_ids",
            allow_empty=True,
        )
        required_handoff_ids = _string_list(
            item.get("required_handoff_ids"),
            field=f"receipt.phase_trace[{sequence}].required_handoff_ids",
            allow_empty=True,
        )
        pending_handoff_ids = _string_list(
            item.get("pending_handoff_ids"),
            field=f"receipt.phase_trace[{sequence}].pending_handoff_ids",
            allow_empty=True,
        )
        trace_failed_handoff_ids = _string_list(
            item.get("failed_handoff_ids"),
            field=f"receipt.phase_trace[{sequence}].failed_handoff_ids",
            allow_empty=True,
        )
        if required_gate_ids != expected_gate_ids:
            raise ValueError(
                f"{fixture_id} full receipt required gates do not match compiler transition."
            )
        if required_handoff_ids != expected_handoff_ids:
            raise ValueError(
                f"{fixture_id} full receipt required handoffs do not match compiler transition."
            )
        expected_pending_gate_ids = [
            gate_id for gate_id in expected_gate_ids if gate_id not in passed_gate_ids
        ]
        expected_pending_handoff_ids = [
            handoff_id
            for handoff_id in expected_handoff_ids
            if handoff_id not in available_handoff_ids
        ]
        expected_failed_handoff_ids = [
            handoff_id
            for handoff_id in expected_handoff_ids
            if handoff_id in failed_handoff_ids
        ]
        if pending_gate_ids != expected_pending_gate_ids:
            raise ValueError(
                f"{fixture_id} full receipt pending gates do not match compiler transition."
            )
        if pending_handoff_ids != expected_pending_handoff_ids:
            raise ValueError(
                f"{fixture_id} full receipt pending handoffs do not match compiler transition."
            )
        if trace_failed_handoff_ids != expected_failed_handoff_ids:
            raise ValueError(
                f"{fixture_id} full receipt failed handoffs do not match compiler transition."
            )
        if status == "advanced":
            if to_index <= current_index:
                raise ValueError(f"{fixture_id} full receipt advanced to an invalid stage.")
            if requested_phase != to_phase:
                raise ValueError(
                    f"{fixture_id} full receipt advanced to a phase other than requested."
                )
            if item.get("reason") != "runtime_evidence_recorded":
                raise ValueError(
                    f"{fixture_id} full receipt advanced without runtime evidence."
                )
            if any(
                (pending_gate_ids, pending_handoff_ids, trace_failed_handoff_ids)
            ):
                raise ValueError(
                    f"{fixture_id} full receipt advanced with unresolved obligations."
                )
            if not set(required_gate_ids).issubset(passed_gate_ids):
                raise ValueError(
                    f"{fixture_id} full receipt advanced without passing required gates."
                )
            if not set(required_handoff_ids).issubset(available_handoff_ids):
                raise ValueError(
                    f"{fixture_id} full receipt advanced without available required handoffs."
                )
            current_index = to_index
        elif status in {"blocked", "unchanged"}:
            if to_index != current_index:
                raise ValueError(
                    f"{fixture_id} full receipt {status} trace changed stage."
                )
            if status == "unchanged" and requested_index != current_index:
                raise ValueError(
                    f"{fixture_id} full receipt left a requested transition unchanged."
                )
        else:
            raise ValueError(f"{fixture_id} full receipt phase status is invalid.")
        covered_stage_ids.update({from_stage_id, to_stage_id})
        normalized.append(
            {
                "sequence": sequence,
                "from_phase": from_phase,
                "to_phase": to_phase,
                "from_stage_id": from_stage_id,
                "to_stage_id": to_stage_id,
                "status": status,
            }
        )
    if (
        current_index != len(expected_stage_ids) - 1
        or set(expected_stage_ids) != covered_stage_ids
    ):
        raise ValueError(f"{fixture_id} full receipt did not complete every compiler stage.")
    return normalized


def _validate_handoff_artifact_refs(
    receipt: Mapping[str, Any],
    *,
    fixture_id: str,
    plan: Mapping[str, Any],
    full_artifact_digest: str,
) -> None:
    """Tie every typed runtime handoff to the host execution artifact."""

    expected_ref = f"artifact:{full_artifact_digest}"
    contracts = {
        str(contract.get("handoff_id") or "")
        for contract in composition_handoff_catalog(plan)
    }
    results = _mapping_list(receipt.get("handoff_results"), field="receipt.handoffs")
    for index, result in enumerate(results, start=1):
        handoff_id = _nonempty(
            result.get("handoff_id"), field=f"receipt.handoffs[{index}].handoff_id"
        )
        if handoff_id not in contracts:
            raise ValueError(f"{fixture_id} full receipt has an unknown handoff.")
        refs = _string_list(
            result.get("evidence_refs"),
            field=f"receipt.handoffs[{index}].evidence_refs",
        )
        if refs != [expected_ref]:
            raise ValueError(
                f"{fixture_id} full receipt handoff evidence must bind the host artifact."
            )


def _validate_full_receipt(
    receipt: Mapping[str, Any],
    *,
    fixture_id: str,
    projection: Mapping[str, Any],
    quality_scores: Mapping[str, Any],
    full_artifact_digest: str,
) -> dict[str, Any]:
    full_variant = projection["full_variant"]
    if not isinstance(full_variant, Mapping):
        raise ValueError("Full-composition control is invalid.")
    plan = projection["plan"]
    if not isinstance(plan, Mapping):
        raise ValueError("Replay composition plan is invalid.")
    _validate_full_receipt_shape(receipt, field=fixture_id)
    if receipt.get("packet_id") not in projection.get("permitted_packet_ids"):
        raise ValueError(f"{fixture_id} full receipt packet_id is outside compiler lineage.")
    if receipt.get("composition_fixture_id") != fixture_id:
        raise ValueError(
            f"{fixture_id} full receipt composition_fixture_id is invalid."
        )
    if receipt.get("recipe_id") != projection.get("composition_plan_id"):
        raise ValueError(f"{fixture_id} full receipt recipe_id must match replay.")
    if receipt.get("task_identity") != projection.get("task_identity"):
        raise ValueError(f"{fixture_id} full receipt task_identity must match replay.")
    if receipt.get("graph_digest") != projection.get("graph_digest"):
        raise ValueError(f"{fixture_id} full receipt graph_digest must match replay.")
    selected = list(projection["selected_skill_ids"])
    expected_source_nodes = [
        next(
            item["source_node_id"]
            for item in projection["source_slices"]
            if item["skill_id"] == skill_id
        )
        for skill_id in selected
    ]
    if receipt.get("selected_skill_ids") != expected_source_nodes:
        raise ValueError(f"{fixture_id} full receipt source selection is invalid.")
    expected_content_digests = sorted(
        {item["content_digest"] for item in projection["source_slices"]}
    )
    if sorted(receipt.get("content_digests") or []) != expected_content_digests:
        raise ValueError(f"{fixture_id} full receipt content digests are invalid.")
    activated_atoms = _string_list(
        receipt.get("activated_atoms"), field=f"{fixture_id}.receipt.activated_atoms"
    )
    permitted_atoms = set(
        _string_list(
            projection.get("permitted_atoms"), field=f"{fixture_id}.permitted_atoms"
        )
    )
    if not set(activated_atoms).issubset(permitted_atoms):
        raise ValueError(f"{fixture_id} full receipt activated atoms are invalid.")
    if receipt.get("user_overrides") != []:
        raise ValueError(f"{fixture_id} full receipt must not use user overrides.")
    if receipt.get("outcome") != "passed":
        raise ValueError(f"{fixture_id} full receipt outcome must be passed.")
    if receipt.get("benchmark_control_input_digest") != full_variant.get(
        "input_packet_digest"
    ):
        raise ValueError(f"{fixture_id} full receipt control input binding is invalid.")
    if receipt.get("benchmark_execution_recipe_digest") != full_variant.get(
        "execution_recipe_digest"
    ):
        raise ValueError(f"{fixture_id} full receipt recipe binding is invalid.")
    phase_trace = _validate_phase_trace(
        receipt, fixture_id=fixture_id, plan=plan
    )
    accounting = projection.get("context_accounting")
    if not isinstance(accounting, Mapping):
        raise ValueError(f"{fixture_id} full receipt is missing compiler context accounting.")
    execution_context = validate_execution_context(
        receipt["execution_context"],
        context_accounting=accounting,
    )
    runtime_evidence = {
        "schema": COMPOSITION_RUNTIME_EVIDENCE_SCHEMA,
        "gate_results": receipt.get("gate_results"),
        "handoff_results": receipt.get("handoff_results"),
    }
    gates = evaluate_composition_gates(plan, runtime_evidence)
    if (
        gates["failed_gate_ids"]
        or gates["pending_gate_ids"]
        or gates["unmatched_results"]
    ):
        raise ValueError(f"{fixture_id} full receipt has unresolved composition gates.")
    handoffs = evaluate_composition_handoffs(plan, runtime_evidence)
    if (
        handoffs["failed_handoff_ids"]
        or handoffs["pending_handoff_ids"]
        or handoffs["invalid_contracts"]
        or handoffs["unmatched_results"]
    ):
        raise ValueError(f"{fixture_id} full receipt has unresolved typed handoffs.")
    _validate_handoff_artifact_refs(
        receipt,
        fixture_id=fixture_id,
        plan=plan,
        full_artifact_digest=full_artifact_digest,
    )
    expected_quality = _receipt_quality_metrics(quality_scores)
    receipt_quality = receipt.get("quality_metrics")
    if not isinstance(receipt_quality, Mapping) or any(
        not math.isclose(
            _finite_number(receipt_quality.get(key), field=f"receipt.quality.{key}"),
            value,
            abs_tol=1e-9,
        )
        for key, value in expected_quality.items()
    ):
        raise ValueError(f"{fixture_id} full receipt quality metrics are invalid.")
    compiled = _finite_number(
        projection.get("compiled_context_tokens"), field="projection.compiled_context"
    )
    naive = _finite_number(
        projection.get("naive_context_tokens"), field="projection.naive_context"
    )
    receipt_cost = receipt.get("cost_metrics")
    if (
        not isinstance(receipt_cost, Mapping)
        or not math.isclose(
            _finite_number(receipt_cost.get("context_tokens"), field="receipt.context"),
            compiled,
            abs_tol=1e-9,
        )
        or not math.isclose(
            _finite_number(receipt_cost.get("context_ratio"), field="receipt.ratio"),
            round(compiled / naive, 4),
            abs_tol=1e-9,
        )
    ):
        raise ValueError(f"{fixture_id} full receipt context metrics are invalid.")
    return {
        "phase_trace": phase_trace,
        "gates": gates,
        "handoffs": handoffs,
        "activated_atoms": activated_atoms,
        "execution_context": execution_context,
    }
