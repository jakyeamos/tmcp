"""Logical compiler projections and host recipe controls for benchmarks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .composition_benchmark_manifests import (
    required_behavioral_variants,
    variant_skill_order,
)
from .composition_benchmark_replay_support import (
    _logical_handoff,
    _mapping_list,
    _nonempty,
    _ordered_variant_ids,
    _packet_plan,
    _skill_by_node,
)
from .composition_preflight import stable_digest
from .composition_validation import ordering_pair
from .harvest_nodes import estimate_tokens


EXECUTION_RECIPE_SCHEMA = "tmcp-composition-benchmark-execution-recipe-v0.1"


def _logical_compiled_plan(
    plan: Mapping[str, Any],
    *,
    source_bindings: Sequence[Mapping[str, str]],
    included_skill_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Project compiler output into logical fixture identities for a host recipe."""

    skill_by_node = _skill_by_node(source_bindings)
    included = (
        set(skill_by_node.values())
        if included_skill_ids is None
        else set(included_skill_ids)
    )
    if not included.issubset(set(skill_by_node.values())):
        raise ValueError("Control recipe includes a skill outside the compiler replay.")
    typed_edges: list[dict[str, Any]] = []
    for edge in _mapping_list(plan.get("typed_edges"), field="composition_plan.edges"):
        source_node_id = _nonempty(edge.get("from"), field="edge.from")
        target_node_id = _nonempty(edge.get("to"), field="edge.to")
        source_skill_id = skill_by_node.get(source_node_id)
        target_skill_id = skill_by_node.get(target_node_id)
        if source_skill_id is None or target_skill_id is None:
            raise ValueError(
                "Replay edge references a source outside the selected graph."
            )
        if source_skill_id not in included or target_skill_id not in included:
            continue
        pair = ordering_pair(dict(edge))
        ordering = (
            {
                "ordering_before_skill_id": skill_by_node[pair[0]],
                "ordering_after_skill_id": skill_by_node[pair[1]],
            }
            if pair is not None
            else {}
        )
        typed_edges.append(
            {
                "source_skill_id": source_skill_id,
                "target_skill_id": target_skill_id,
                "relationship_type": _nonempty(edge.get("type"), field="edge.type"),
                "citations": list(edge.get("citations") or []),
                **ordering,
            }
        )
    handoffs = [
        _logical_handoff(contract, skill_by_node=skill_by_node)
        for contract in _mapping_list(
            plan.get("handoff_contracts"), field="composition_plan.handoff_contracts"
        )
    ]
    handoffs = [
        contract
        for contract in handoffs
        if contract["producer_skill_id"] in included
        and contract["consumer_skill_id"] in included
    ]
    stages: list[dict[str, Any]] = []
    for stage in _mapping_list(
        plan.get("ordered_stages"), field="composition_plan.stages"
    ):
        node_ids = [
            _nonempty(node_id, field="composition_plan.stage.node_id")
            for node_id in stage.get("node_ids") or []
        ]
        skill_ids = [
            skill_by_node[node_id]
            for node_id in node_ids
            if skill_by_node.get(node_id) in included
        ]
        if not skill_ids:
            continue
        bridges: list[dict[str, Any]] = []
        for bridge in _mapping_list(
            stage.get("bridge_instructions"), field="composition_plan.stage.bridges"
        ):
            node_id = _nonempty(bridge.get("node_id"), field="bridge.node_id")
            skill_id = skill_by_node.get(node_id)
            if skill_id not in included:
                continue
            bridges.append(
                {
                    "skill_id": skill_id,
                    "role": _nonempty(bridge.get("role"), field="bridge.role"),
                    "required_inputs": list(bridge.get("required_inputs") or []),
                    "produced_outputs": list(bridge.get("produced_outputs") or []),
                    "exit_gates": list(bridge.get("exit_gates") or []),
                    "handoff_ids": list(bridge.get("handoff_ids") or []),
                    "instruction": _nonempty(
                        bridge.get("instruction"), field="bridge.instruction"
                    ),
                    "citations": list(bridge.get("citations") or []),
                }
            )
        stages.append(
            {
                "stage_id": _nonempty(stage.get("stage_id"), field="stage.id"),
                "order": int(stage.get("order") or 0),
                "phase": _nonempty(stage.get("phase"), field="stage.phase"),
                "status": _nonempty(stage.get("status"), field="stage.status"),
                "active_skill_ids": skill_ids,
                "entry_conditions": list(stage.get("entry_conditions") or []),
                "bridge_instructions": bridges,
                "handoff_contracts": [
                    contract
                    for contract in handoffs
                    if contract["consumer_skill_id"] in skill_ids
                ],
            }
        )
    return {
        "composition_plan_id": _nonempty(
            plan.get("composition_plan_id"), field="composition_plan.id"
        ),
        "composition_plan_digest": stable_digest(dict(plan)),
        "graph_digest": _nonempty(
            dict(plan.get("provenance") or {}).get("graph_digest"),
            field="composition_plan.graph_digest",
        ),
        "stages": stages,
        "typed_edges": typed_edges,
        "handoff_contracts": handoffs,
    }


def _compiled_context_accounting(
    *,
    preflight: Mapping[str, Any],
    plan: Mapping[str, Any],
    source_bindings: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Derive full-plan context from compiler evidence, never host declarations."""

    skill_by_node = _skill_by_node(source_bindings)
    candidates = {
        _nonempty(item.get("source_node_id"), field="preflight.source_node_id"): item
        for item in _mapping_list(
            preflight.get("candidate_source_slices"),
            field="preflight.candidate_source_slices",
        )
    }
    source_tokens: list[dict[str, Any]] = []
    tokens_by_node: dict[str, int] = {}
    for node_id, skill_id in skill_by_node.items():
        candidate = candidates.get(node_id)
        if candidate is None:
            raise ValueError("Replay context is missing a selected source slice.")
        if str(candidate.get("source_digest") or "") != next(
            binding["content_digest"]
            for binding in source_bindings
            if binding["source_node_id"] == node_id
        ):
            raise ValueError("Replay context source digest does not match its binding.")
        token_count = estimate_tokens(str(candidate.get("content") or ""))
        tokens_by_node[node_id] = token_count
        source_tokens.append(
            {
                "skill_id": skill_id,
                "source_digest": str(candidate.get("source_digest") or ""),
                "tokens": token_count,
            }
        )
    stage_tokens: list[dict[str, Any]] = []
    for stage in _mapping_list(
        plan.get("ordered_stages"), field="composition_plan.stages"
    ):
        node_ids = [
            _nonempty(node_id, field="composition_plan.stage.node_id")
            for node_id in stage.get("node_ids") or []
        ]
        stage_tokens.append(
            {
                "stage_id": _nonempty(stage.get("stage_id"), field="stage.id"),
                "tokens": sum(tokens_by_node[node_id] for node_id in node_ids),
            }
        )
    index = preflight.get("behavior_manifest_index")
    if not isinstance(index, Mapping):
        raise ValueError("Replay context is missing the behavior manifest index.")
    telemetry = index.get("cost_telemetry")
    if not isinstance(telemetry, Mapping):
        raise ValueError("Replay context is missing behavior-index cost telemetry.")
    always_on_index_tokens = telemetry.get("always_on_index_tokens")
    if isinstance(always_on_index_tokens, bool) or not isinstance(
        always_on_index_tokens, int
    ):
        raise ValueError("Replay context behavior-index tokens are invalid.")
    naive_context_tokens = sum(item["tokens"] for item in source_tokens)
    peak_active_stage_tokens = max([item["tokens"] for item in stage_tokens], default=0)
    accounting: dict[str, Any] = {
        "policy": "always_on_manifest_index_plus_peak_active_stage_source_tokens",
        "always_on_index_tokens": always_on_index_tokens,
        "source_tokens": source_tokens,
        "stage_tokens": stage_tokens,
        "naive_context_tokens": naive_context_tokens,
        "peak_active_stage_tokens": peak_active_stage_tokens,
        "compiled_context_tokens": always_on_index_tokens + peak_active_stage_tokens,
    }
    accounting["context_digest"] = stable_digest(accounting)
    return accounting


def _recipe_with_identity(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        **recipe,
        "recipe_digest": stable_digest(recipe),
    }


def _ablation_obligations(
    *,
    source_projection: Mapping[str, Any],
    omitted_skill_ids: Sequence[str],
) -> list[dict[str, str]]:
    omitted = set(omitted_skill_ids)
    obligations: list[dict[str, str]] = []
    for contract in _mapping_list(
        source_projection.get("handoff_contracts"), field="recipe.handoff_contracts"
    ):
        producer = _nonempty(
            contract.get("producer_skill_id"), field="handoff.producer"
        )
        consumer = _nonempty(
            contract.get("consumer_skill_id"), field="handoff.consumer"
        )
        handoff_id = _nonempty(contract.get("handoff_id"), field="handoff.id")
        if producer in omitted and consumer not in omitted:
            obligations.append(
                {
                    "kind": "missing_required_handoff",
                    "handoff_id": handoff_id,
                    "producer_skill_id": producer,
                    "consumer_skill_id": consumer,
                }
            )
        elif consumer in omitted and producer not in omitted:
            obligations.append(
                {
                    "kind": "orphaned_handoff",
                    "handoff_id": handoff_id,
                    "producer_skill_id": producer,
                    "consumer_skill_id": consumer,
                }
            )
    for edge in _mapping_list(
        source_projection.get("typed_edges"), field="recipe.edges"
    ):
        if (
            str(edge.get("relationship_type") or "") == "verifies"
            and str(edge.get("source_skill_id") or "") in omitted
        ):
            obligations.append(
                {
                    "kind": "removed_verification_obligation",
                    "relationship_type": "verifies",
                    "producer_skill_id": str(edge.get("source_skill_id") or ""),
                    "consumer_skill_id": str(edge.get("target_skill_id") or ""),
                }
            )
    if not obligations:
        obligations.append(
            {
                "kind": "removed_role_coverage",
                "producer_skill_id": ",".join(sorted(omitted)),
                "consumer_skill_id": "",
            }
        )
    return obligations


def _execution_recipe(
    *,
    fixture_id: str,
    request_id: str,
    variant_id: str,
    skill_order: list[str],
    omitted_skill_ids: list[str],
    source_bindings: list[dict[str, str]],
    all_source_bindings: list[dict[str, str]],
    preflight: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    plan = _packet_plan(packet)
    full_projection = _logical_compiled_plan(
        plan,
        source_bindings=all_source_bindings,
    )
    base: dict[str, Any] = {
        "schema": EXECUTION_RECIPE_SCHEMA,
        "fixture_id": fixture_id,
        "request_id": request_id,
        "variant_id": variant_id,
        "cache_policy": "none",
        "source_composition_plan_id": full_projection["composition_plan_id"],
        "source_composition_plan_digest": full_projection["composition_plan_digest"],
        "graph_digest": full_projection["graph_digest"],
        "ordered_skill_ids": skill_order,
        "source_bindings": source_bindings,
    }
    if variant_id == "full_composition":
        return _recipe_with_identity(
            {
                **base,
                "execution_mode": "compiled_composition",
                "stages": full_projection["stages"],
                "typed_edges": full_projection["typed_edges"],
                "handoff_contracts": full_projection["handoff_contracts"],
                "phase_gate_policy": "block_phase_advancement_until_entry_gates_pass",
                "required_gate_overrides": [],
                "context_accounting": _compiled_context_accounting(
                    preflight=preflight,
                    plan=plan,
                    source_bindings=all_source_bindings,
                ),
            }
        )
    if variant_id == "wrong_order":
        position = {skill_id: index for index, skill_id in enumerate(skill_order)}
        violations = [
            edge
            for edge in full_projection["typed_edges"]
            if "ordering_before_skill_id" in edge
            and position[edge["ordering_before_skill_id"]]
            > position[edge["ordering_after_skill_id"]]
        ]
        if not violations:
            raise ValueError(
                f"{fixture_id} cannot derive a wrong-order control from its graph."
            )
        return _recipe_with_identity(
            {
                **base,
                "execution_mode": "counterfactual_wrong_order",
                "source_compiled_stages": full_projection["stages"],
                "counterfactual_execution_order": skill_order,
                "violated_ordering_edges": violations,
                "required_gate_overrides": [
                    {
                        "kind": "ordering_violation",
                        "before_skill_id": edge["ordering_before_skill_id"],
                        "after_skill_id": edge["ordering_after_skill_id"],
                        "relationship_type": edge["relationship_type"],
                    }
                    for edge in violations
                ],
            }
        )
    if variant_id.startswith("leave_one_out:"):
        available = set(skill_order)
        return _recipe_with_identity(
            {
                **base,
                "execution_mode": "counterfactual_ablation",
                "source_compiled_stages": full_projection["stages"],
                "available_stages": _logical_compiled_plan(
                    plan,
                    source_bindings=all_source_bindings,
                    included_skill_ids=available,
                )["stages"],
                "remaining_typed_edges": _logical_compiled_plan(
                    plan,
                    source_bindings=all_source_bindings,
                    included_skill_ids=available,
                )["typed_edges"],
                "missing_obligations": _ablation_obligations(
                    source_projection=full_projection,
                    omitted_skill_ids=omitted_skill_ids,
                ),
                "required_gate_overrides": [],
            }
        )
    if variant_id == "no_skill":
        mode = "no_skill_baseline"
    elif variant_id == "naive_union":
        mode = "naive_union_baseline"
    elif variant_id.startswith("singleton:"):
        mode = "singleton_baseline"
    else:
        raise ValueError(f"Unknown benchmark control variant {variant_id}.")
    return _recipe_with_identity(
        {
            **base,
            "execution_mode": mode,
            "required_gate_overrides": [],
        }
    )


def _variant_controls(
    *,
    fixture_id: str,
    request_id: str,
    source_bindings: list[dict[str, str]],
    preflight: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> list[dict[str, Any]]:
    selected_skill_ids = [item["skill_id"] for item in source_bindings]
    if len(selected_skill_ids) < 2:
        raise ValueError(f"{fixture_id} replay must select at least two skills.")
    expected_variants = required_behavioral_variants(selected_skill_ids)
    controls: list[dict[str, Any]] = []
    for variant_id in _ordered_variant_ids(selected_skill_ids):
        if variant_id not in expected_variants:
            raise ValueError(
                f"{fixture_id} has unsupported derived variant {variant_id}."
            )
        skill_order = variant_skill_order(variant_id, selected_skill_ids)
        bindings_by_skill_id = {
            binding["skill_id"]: binding for binding in source_bindings
        }
        selected = [bindings_by_skill_id[skill_id] for skill_id in skill_order]
        omitted = [
            skill_id for skill_id in selected_skill_ids if skill_id not in skill_order
        ]
        recipe = _execution_recipe(
            fixture_id=fixture_id,
            request_id=request_id,
            variant_id=variant_id,
            skill_order=skill_order,
            omitted_skill_ids=omitted,
            source_bindings=selected,
            all_source_bindings=source_bindings,
            preflight=preflight,
            packet=packet,
        )
        input_packet = {
            "schema": "tmcp-composition-benchmark-control-input-v0.1",
            "fixture_id": fixture_id,
            "request_id": request_id,
            "variant_id": variant_id,
            "cache_policy": "none",
            "composition_enabled": variant_id == "full_composition",
            "ordered_skill_ids": skill_order,
            "omitted_skill_ids": omitted,
            "source_bindings": selected,
            "replay_packet_id": packet.get("packet_id"),
            "replay_packet_digest": stable_digest(dict(packet)),
            "execution_recipe": recipe,
            "execution_recipe_digest": recipe["recipe_digest"],
        }
        controls.append(
            {
                **input_packet,
                "input_packet_digest": stable_digest(input_packet),
            }
        )
    return controls
