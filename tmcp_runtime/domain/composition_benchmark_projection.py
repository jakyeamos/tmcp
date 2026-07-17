"""Project compiler replay controls into benchmark observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.composition_benchmark_boundaries import (
    MAX_SOURCE_SLICE_CHARS,
    _bounded_text,
    _finite_number,
    _mapping_list,
    _nonempty,
    _string_list,
)
from tmcp_runtime.domain.composition_benchmark_manifests import (
    evidence_record_digest,
    execution_record_digest,
    required_behavioral_variants,
)
from tmcp_runtime.domain.composition_benchmark_protocol import (
    fixture_workspace_relative_path,
)
from tmcp_runtime.domain.composition_benchmark_sources import (
    graph_digest_for_observation,
)
from tmcp_runtime.domain.composition_preflight import stable_digest


def _source_slices(
    fixture: Mapping[str, Any],
    control: Mapping[str, Any],
) -> list[dict[str, Any]]:
    replay = control.get("replay")
    if not isinstance(replay, Mapping):
        raise ValueError("Behavioral control is missing compiler replay evidence.")
    preflight = replay.get("preflight")
    if not isinstance(preflight, Mapping):
        raise ValueError("Behavioral control is missing its replay preflight.")
    candidates = {
        _nonempty(item.get("source_node_id"), field="preflight.source_node_id"): item
        for item in _mapping_list(
            preflight.get("candidate_source_slices"),
            field="preflight.candidate_source_slices",
        )
    }
    workspace = fixture_workspace_relative_path(fixture)
    result: list[dict[str, Any]] = []
    for binding in _mapping_list(
        control.get("source_bindings"), field="source_bindings"
    ):
        skill_id = _nonempty(binding.get("skill_id"), field="source_binding.skill_id")
        source_node_id = _nonempty(
            binding.get("source_node_id"), field="source_binding.source_node_id"
        )
        candidate = candidates.get(source_node_id)
        if candidate is None:
            raise ValueError(
                "Selected control source is missing from the replay preflight."
            )
        content = _bounded_text(
            candidate.get("content"),
            field=f"preflight.{source_node_id}.content",
            maximum=MAX_SOURCE_SLICE_CHARS,
        )
        if candidate.get("char_start") != 0 or candidate.get("char_end") != len(
            content
        ):
            raise ValueError(
                "Benchmark observations require a complete selected source."
            )
        source_digest = _nonempty(
            candidate.get("source_digest"),
            field=f"preflight.{source_node_id}.source_digest",
        )
        if source_digest != binding.get("content_digest"):
            raise ValueError("Replay source digest does not match its control binding.")
        relative_path = _nonempty(
            binding.get("relative_path"), field="source_binding.relative_path"
        )
        result.append(
            {
                "skill_id": skill_id,
                "source_node_id": source_node_id,
                "relative_path": relative_path,
                "source_path": f"/tmcp-benchmark/{workspace}/{relative_path}",
                "content": content,
                "char_start": 0,
                "char_end": len(content),
                "slice_id": _nonempty(
                    candidate.get("slice_id"),
                    field=f"preflight.{source_node_id}.slice_id",
                ),
                "source_digest": source_digest,
                "slice_digest": _nonempty(
                    candidate.get("slice_digest"),
                    field=f"preflight.{source_node_id}.slice_digest",
                ),
                "content_digest": source_digest,
            }
        )
    return result


def _packet_id_for_phase(
    packet: Mapping[str, Any],
    plan: Mapping[str, Any],
    phase: str,
) -> str:
    """Mirror the compiler's stable packet identity for one permitted phase."""

    return "packet-" + stable_digest(
        {
            "objective": packet.get("objective"),
            "phase": phase,
            "composition_plan_id": plan.get("composition_plan_id"),
            "graph_digest": dict(plan.get("provenance") or {}).get("graph_digest"),
        }
    )[:12]


def _behavioral_projection(
    fixture: Mapping[str, Any],
    control: Mapping[str, Any],
) -> dict[str, Any]:
    replay = control.get("replay")
    if not isinstance(replay, Mapping):
        raise ValueError("Behavioral control is missing replay evidence.")
    packet = replay.get("packet")
    if not isinstance(packet, Mapping):
        raise ValueError("Behavioral control is missing its replay packet.")
    plan = packet.get("composition_plan")
    if not isinstance(plan, Mapping):
        raise ValueError("Behavioral replay packet is missing a composition plan.")
    source_slices = _source_slices(fixture, control)
    skill_by_node = {
        str(item["source_node_id"]): str(item["skill_id"]) for item in source_slices
    }
    relationships: list[dict[str, Any]] = []
    for edge in _mapping_list(
        plan.get("typed_edges"), field="composition_plan.typed_edges"
    ):
        source_node_id = _nonempty(edge.get("from"), field="composition_plan.edge.from")
        target_node_id = _nonempty(edge.get("to"), field="composition_plan.edge.to")
        source_skill_id = skill_by_node.get(source_node_id)
        target_skill_id = skill_by_node.get(target_node_id)
        if source_skill_id is None or target_skill_id is None:
            raise ValueError(
                "Compiler edge references a source outside the selected graph."
            )
        relationships.append(
            {
                "source_id": source_skill_id,
                "target_id": target_skill_id,
                "relation": _nonempty(
                    edge.get("type"), field="composition_plan.edge.type"
                ),
                "citations": list(edge.get("citations") or []),
            }
        )
    active_stages: list[dict[str, Any]] = []
    for stage in _mapping_list(
        plan.get("ordered_stages"), field="composition_plan.stages"
    ):
        node_ids = _string_list(
            stage.get("node_ids"), field="composition_plan.stage.node_ids"
        )
        active_skill_ids = [skill_by_node[node_id] for node_id in node_ids]
        active_stages.append(
            {
                "stage_id": _nonempty(
                    stage.get("stage_id"), field="composition_plan.stage.id"
                ),
                "active_skill_ids": active_skill_ids,
            }
        )
    selected_skill_ids = _string_list(
        control.get("selected_skill_ids"), field="control.selected_skill_ids"
    )
    ordered_skill_ids = _string_list(
        control.get("ordered_skill_ids"), field="control.ordered_skill_ids"
    )
    stage_order = [
        skill_id for stage in active_stages for skill_id in stage["active_skill_ids"]
    ]
    if stage_order != ordered_skill_ids or ordered_skill_ids != selected_skill_ids:
        raise ValueError(
            "Compiler stages must preserve the selected logical skill order."
        )
    source_nodes = {item["skill_id"]: item["source_node_id"] for item in source_slices}
    source_slices_by_id = {item["slice_id"]: item for item in source_slices}
    graph_digest = graph_digest_for_observation(
        selected_skill_ids,
        relationships,
        source_node_by_skill=source_nodes,
        slices_by_id=source_slices_by_id,
    )
    provenance = plan.get("provenance")
    if not isinstance(provenance, Mapping) or graph_digest != provenance.get(
        "graph_digest"
    ):
        raise ValueError(
            "Observation graph projection does not match compiler provenance."
        )
    full_variant = next(
        (
            item
            for item in _mapping_list(control.get("variants"), field="control.variants")
            if item.get("variant_id") == "full_composition"
        ),
        None,
    )
    if not isinstance(full_variant, Mapping):
        raise ValueError("Behavioral control is missing full-composition evidence.")
    recipe = full_variant.get("execution_recipe")
    if not isinstance(recipe, Mapping):
        raise ValueError("Full-composition control is missing its execution recipe.")
    accounting = recipe.get("context_accounting")
    if not isinstance(accounting, Mapping):
        raise ValueError("Full-composition control is missing context accounting.")
    compiled = _finite_number(
        accounting.get("compiled_context_tokens"),
        field="context_accounting.compiled_context_tokens",
    )
    naive = _finite_number(
        accounting.get("naive_context_tokens"),
        field="context_accounting.naive_context_tokens",
    )
    if compiled < 0 or naive <= 0:
        raise ValueError("Compiler context accounting is invalid.")
    task_identity = packet.get("task_identity")
    if not isinstance(task_identity, Mapping):
        raise ValueError("Replay packet is missing task identity.")
    preflight = replay.get("preflight")
    if not isinstance(preflight, Mapping):
        raise ValueError("Behavioral replay is missing its preflight.")
    receipt_template = packet.get("receipt_template")
    if not isinstance(receipt_template, Mapping):
        raise ValueError("Behavioral replay packet is missing its receipt template.")
    permitted_atoms = _string_list(
        _string_list(packet.get("active_atoms"), field="replay.packet.active_atoms")
        + _string_list(
            packet.get("deferred_atoms"), field="replay.packet.deferred_atoms"
        ),
        field="replay.packet.composition_atoms",
    )
    permitted_packet_ids = {
        _nonempty(packet.get("packet_id"), field="replay.packet.packet_id"),
        *(
            _packet_id_for_phase(
                packet,
                plan,
                _nonempty(stage.get("phase"), field="composition_plan.stage.phase"),
            )
            for stage in _mapping_list(
                plan.get("ordered_stages"), field="composition_plan.stages"
            )
        ),
    }
    return {
        "fixture_id": _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id"),
        "preflight_id": _nonempty(preflight.get("preflight_id"), field="preflight.id"),
        "composition_plan_id": _nonempty(
            plan.get("composition_plan_id"), field="composition_plan.id"
        ),
        "graph_digest": graph_digest,
        "task_identity": dict(task_identity),
        "selected_skill_ids": selected_skill_ids,
        "source_slices": source_slices,
        "ordered_skill_ids": ordered_skill_ids,
        "active_stages": active_stages,
        "relationships": relationships,
        "compiled_context_tokens": compiled,
        "naive_context_tokens": naive,
        "permitted_packet_ids": sorted(permitted_packet_ids),
        "permitted_atoms": permitted_atoms,
        "full_variant": dict(full_variant),
        "plan": dict(plan),
    }


def _evidence_ids(values: Sequence[Mapping[str, str]], *, field: str) -> list[str]:
    result: list[str] = []
    for index, item in enumerate(values, start=1):
        record = {
            "media_type": item["media_type"],
            "content": item["content"],
            "content_digest": stable_digest(item["content"]),
        }
        evidence_id = "evidence-" + evidence_record_digest(record)[:20]
        if evidence_id in result:
            raise ValueError(f"{field} contains duplicate evidence content.")
        result.append(evidence_id)
    return result


def _evidence_manifest(
    values: Sequence[Mapping[str, str]],
    *,
    execution_id: str,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for item in values:
        record = {
            "execution_id": execution_id,
            "media_type": item["media_type"],
            "content": item["content"],
            "content_digest": stable_digest(item["content"]),
        }
        record["evidence_id"] = "evidence-" + evidence_record_digest(record)[:20]
        records.append(record)
    return records


def _execution_record(
    *,
    variant_id: str,
    input_digest: str,
    control_input_digest: str,
    execution_recipe_digest: str | None,
    artifact: str,
    result_digest: str,
    run_id: str,
    tmcp_run_receipt: Mapping[str, Any] | None,
    evidence_values: Sequence[Mapping[str, str]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    artifact_digest = stable_digest(artifact)
    receipt: dict[str, Any] = {
        "run_id": "host-run-" + stable_digest(run_id)[:20],
        "variant_id": variant_id,
        "outcome": "passed",
        "artifact_digest": artifact_digest,
    }
    if tmcp_run_receipt is not None:
        receipt["tmcp_run_receipt"] = dict(tmcp_run_receipt)
    evidence_ids = _evidence_ids(evidence_values, field=f"{variant_id}.evidence")
    record: dict[str, Any] = {
        "variant_id": variant_id,
        "input_digest": input_digest,
        "control_input_digest": control_input_digest,
        "artifact": artifact,
        "artifact_digest": artifact_digest,
        "result_digest": result_digest,
        "run_receipt": receipt,
        "receipt_digest": stable_digest(receipt),
        "evidence_ids": evidence_ids,
    }
    if execution_recipe_digest is not None:
        record["execution_recipe_digest"] = execution_recipe_digest
    record["execution_digest"] = execution_record_digest(record)
    record["execution_id"] = "execution-" + record["execution_digest"][:20]
    return record, _evidence_manifest(
        evidence_values, execution_id=record["execution_id"]
    )


def _quality_from_evaluation(
    fixture: Mapping[str, Any],
    *,
    selected_skill_ids: Sequence[str],
    variants: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    rubric = fixture.get("quality_rubric")
    if not isinstance(rubric, Mapping):
        raise ValueError(f"{fixture.get('fixture_id') or 'fixture'}.quality_rubric is required.")
    weights = {
        _nonempty(
            item.get("dimension_id"), field="rubric.dimension_id"
        ): _finite_number(item.get("weight"), field="rubric.dimension.weight")
        for item in _mapping_list(rubric.get("dimensions"), field="rubric.dimensions")
    }
    scores_by_variant: dict[str, float] = {}
    dimensions_by_variant: dict[str, dict[str, float]] = {}
    required = required_behavioral_variants(selected_skill_ids)
    if set(variants) != required:
        raise ValueError("Evaluator variants do not match the compiler controls.")
    for variant_id, variant in variants.items():
        raw = variant.get("dimension_scores")
        if not isinstance(raw, Mapping):
            raise ValueError(f"Evaluator dimensions are missing for {variant_id}.")
        normalized = {
            str(key): _finite_number(value, field=f"{variant_id}.{key}")
            for key, value in raw.items()
        }
        if set(normalized) != set(weights):
            raise ValueError(f"Evaluator dimensions are incomplete for {variant_id}.")
        dimensions_by_variant[variant_id] = normalized
        scores_by_variant[variant_id] = sum(
            normalized[dimension_id] * weight
            for dimension_id, weight in weights.items()
        )
    return (
        {
            "no_skill": scores_by_variant["no_skill"],
            "singletons": {
                skill_id: scores_by_variant[f"singleton:{skill_id}"]
                for skill_id in selected_skill_ids
            },
            "naive_union": scores_by_variant["naive_union"],
            "full_composition": scores_by_variant["full_composition"],
            "leave_one_out": {
                skill_id: scores_by_variant[f"leave_one_out:{skill_id}"]
                for skill_id in selected_skill_ids
            },
            "wrong_order": scores_by_variant["wrong_order"],
        },
        dimensions_by_variant,
    )


def _receipt_quality_metrics(quality_scores: Mapping[str, Any]) -> dict[str, float]:
    full = _finite_number(
        quality_scores.get("full_composition"), field="quality.full_composition"
    )
    naive = _finite_number(quality_scores.get("naive_union"), field="quality.naive")
    wrong_order = _finite_number(
        quality_scores.get("wrong_order"), field="quality.wrong_order"
    )
    singletons = quality_scores.get("singletons")
    if not isinstance(singletons, Mapping) or not singletons:
        raise ValueError("Quality metrics require singleton scores.")
    best_singleton = max(
        _finite_number(value, field=f"quality.singleton.{skill_id}")
        for skill_id, value in singletons.items()
    )
    return {
        "synergy_lift": round(full - best_singleton, 4),
        "compiler_lift": round(full - naive, 4),
        "order_lift": round(full - wrong_order, 4),
    }
