"""Compiler-only replay and control derivation for composition benchmarks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.composition_benchmark_manifests import (
    required_behavioral_variants,
    variant_skill_order,
)
from tmcp_runtime.domain.composition_benchmark_protocol import (
    BENCHMARK_RUN_PLAN_SCHEMA,
    fixture_source_nodes,
    fixture_workspace_relative_path,
    prepare_fixture_preflight,
    validate_benchmark_run_plan,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.composition_validation import ordering_pair
from tmcp_runtime.domain.harvest_nodes import estimate_tokens
from tmcp_runtime.services.compose import compose_packet_from_source_nodes


BENCHMARK_CONTROL_PLAN_SCHEMA = "tmcp-composition-benchmark-control-plan-v0.1"
SEMANTIC_PROPOSAL_BUNDLE_SCHEMA = "tmcp-composition-benchmark-semantic-proposals-v0.1"
EXECUTION_RECIPE_SCHEMA = "tmcp-composition-benchmark-execution-recipe-v0.1"


def _mapping_list(value: object, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of objects.")
    result = [item for item in value if isinstance(item, Mapping)]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only objects.")
    return result


def _nonempty(value: object, *, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is required.")
    return result


def _fixture_index(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    fixtures = _mapping_list(payload.get("fixtures"), field="behavioral.fixtures")
    result: dict[str, Mapping[str, Any]] = {}
    for fixture in fixtures:
        fixture_id = _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id")
        if fixture_id in result:
            raise ValueError(f"behavioral.fixtures has duplicate fixture {fixture_id}.")
        result[fixture_id] = fixture
    return result


def _request_index(
    run_plan: Mapping[str, Any],
    *,
    field: str,
    subject_field: str,
) -> dict[str, Mapping[str, Any]]:
    requests = _mapping_list(run_plan.get(field), field=field)
    result: dict[str, Mapping[str, Any]] = {}
    for request in requests:
        subject_id = _nonempty(
            request.get(subject_field), field=f"{field}.{subject_field}"
        )
        if subject_id in result:
            raise ValueError(f"{field} has duplicate {subject_field} {subject_id}.")
        result[subject_id] = request
    return result


def _proposal_index(
    proposal_bundle: Mapping[str, Any],
    *,
    field: str,
    subject_field: str,
    expected_subject_ids: set[str],
) -> dict[str, dict[str, Any]]:
    records = _mapping_list(proposal_bundle.get(field), field=field)
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        subject_id = _nonempty(
            record.get(subject_field), field=f"{field}.{subject_field}"
        )
        proposal = record.get("semantic_proposal")
        if not isinstance(proposal, Mapping):
            raise ValueError(f"{field}.{subject_id}.semantic_proposal is required.")
        if subject_id in result:
            raise ValueError(f"{field} has duplicate proposal for {subject_id}.")
        result[subject_id] = dict(proposal)
    observed_subject_ids = set(result)
    if observed_subject_ids != expected_subject_ids:
        raise ValueError(
            f"{field} must cover each prepared request exactly; "
            f"missing={sorted(expected_subject_ids - observed_subject_ids)}, "
            f"unexpected={sorted(observed_subject_ids - expected_subject_ids)}."
        )
    return result


def _validate_proposal_bundle(
    proposal_bundle: Mapping[str, Any],
    run_plan: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if proposal_bundle.get("schema") != SEMANTIC_PROPOSAL_BUNDLE_SCHEMA:
        raise ValueError(
            f"semantic proposal bundle.schema must be {SEMANTIC_PROPOSAL_BUNDLE_SCHEMA}."
        )
    for key in ("run_manifest_id", "run_manifest_digest"):
        if proposal_bundle.get(key) != run_plan.get(key):
            raise ValueError(
                f"semantic proposal bundle.{key} must match the prepared run plan."
            )
    routing_requests = _request_index(
        run_plan,
        field="routing_requests",
        subject_field="case_id",
    )
    behavioral_requests = _request_index(
        run_plan,
        field="behavioral_requests",
        subject_field="fixture_id",
    )
    routing = _proposal_index(
        proposal_bundle,
        field="routing_proposals",
        subject_field="case_id",
        expected_subject_ids=set(routing_requests),
    )
    behavioral = _proposal_index(
        proposal_bundle,
        field="behavioral_proposals",
        subject_field="fixture_id",
        expected_subject_ids=set(behavioral_requests),
    )
    return routing, behavioral


def _replay_packet(
    *,
    fixture: Mapping[str, Any],
    request: Mapping[str, Any],
    proposal: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture_id = _nonempty(fixture.get("fixture_id"), field="fixture.fixture_id")
    objective = _nonempty(request.get("objective"), field=f"{fixture_id}.objective")
    preflight = prepare_fixture_preflight(fixture=fixture, objective=objective)
    expected_preflight_id = _nonempty(
        request.get("preflight_id"), field=f"{fixture_id}.preflight_id"
    )
    expected_preflight_digest = _nonempty(
        request.get("preflight_digest"), field=f"{fixture_id}.preflight_digest"
    )
    if preflight.get("preflight_id") != expected_preflight_id:
        raise ValueError(f"{fixture_id} prepared preflight id is stale.")
    if stable_digest(preflight) != expected_preflight_digest:
        raise ValueError(f"{fixture_id} prepared preflight digest is stale.")
    request_phase = _nonempty(request.get("phase"), field=f"{fixture_id}.phase")
    if str(proposal.get("current_phase") or "").strip() != request_phase:
        raise ValueError(
            f"{fixture_id} semantic proposal current_phase must match the prepared request phase."
        )
    packet = compose_packet_from_source_nodes(
        {
            "objective": objective,
            "project_path": "/tmcp-benchmark/"
            + fixture_workspace_relative_path(fixture),
            "phase": request_phase,
            "cache_policy": "none",
            "candidate_limit": 24,
            "max_excerpt_chars": 48_000,
            "max_total_chars": 48_000,
            "max_total_tokens": 12_000,
            "explicitly_scoped_paths": ["skills"],
            "include_all_active_source_slices": True,
            "semantic_proposal": dict(proposal),
        },
        source_nodes=fixture_source_nodes(fixture),
        global_graphs=[],
        receipts=[],
        cache_warnings=[],
        cache_home="[REDACTED:path]",
    )
    validation = packet.get("semantic_proposal_validation")
    plan = packet.get("composition_plan")
    if not isinstance(validation, Mapping) or validation.get("accepted") is not True:
        errors = validation.get("errors") if isinstance(validation, Mapping) else []
        raise ValueError(f"{fixture_id} semantic proposal was rejected: {errors}")
    if not isinstance(plan, Mapping):
        raise ValueError(f"{fixture_id} replay did not produce a composition plan.")
    if plan.get("preflight_id") != preflight.get("preflight_id"):
        raise ValueError(f"{fixture_id} replay plan is not bound to its preflight.")
    return preflight, packet


def _role_projection(
    fixture: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[str], set[tuple[str, str]]]:
    plan = packet.get("composition_plan")
    if not isinstance(plan, Mapping):
        raise ValueError("Replay packet does not have a composition plan.")
    nodes = {str(node.get("id") or ""): node for node in fixture_source_nodes(fixture)}
    roles = _mapping_list(plan.get("skill_roles"), field="composition_plan.skill_roles")
    source_by_node_id: dict[str, dict[str, str]] = {}
    for role in roles:
        node_id = _nonempty(role.get("node_id"), field="composition_plan.role.node_id")
        node = nodes.get(node_id)
        if node is None:
            raise ValueError(f"Replay plan selected unknown fixture source {node_id}.")
        skill_id = _nonempty(node.get("skill_id"), field=f"{node_id}.skill_id")
        if node_id in source_by_node_id:
            raise ValueError(f"Replay plan has duplicate source role {node_id}.")
        source_by_node_id[node_id] = {
            "skill_id": skill_id,
            "source_node_id": node_id,
            "relative_path": _nonempty(
                node.get("relative_path"), field=f"{node_id}.relative_path"
            ),
            "content_digest": _nonempty(
                node.get("content_digest"), field=f"{node_id}.content_digest"
            ),
            "activation": str(role.get("activation") or "deferred"),
        }
    ordered_node_ids: list[str] = []
    for stage in _mapping_list(
        plan.get("ordered_stages"), field="composition_plan.stages"
    ):
        node_ids = stage.get("node_ids")
        if isinstance(node_ids, (str, bytes)) or not isinstance(node_ids, Sequence):
            raise ValueError("Replay plan stage node_ids must be a sequence.")
        for node_id in node_ids:
            normalized = _nonempty(node_id, field="composition_plan.stage.node_id")
            if normalized in ordered_node_ids:
                raise ValueError(f"Replay plan stages repeat source {normalized}.")
            ordered_node_ids.append(normalized)
    if set(ordered_node_ids) != set(source_by_node_id):
        raise ValueError("Replay plan stages must cover selected roles exactly once.")
    source_bindings = [source_by_node_id[node_id] for node_id in ordered_node_ids]
    selected_skill_ids = [item["skill_id"] for item in source_bindings]
    if len(selected_skill_ids) != len(set(selected_skill_ids)):
        raise ValueError("Replay plan selects duplicate logical fixture skills.")
    ordering_edges: set[tuple[str, str]] = set()
    for edge in _mapping_list(plan.get("typed_edges"), field="composition_plan.edges"):
        pair = ordering_pair(dict(edge))
        if pair is None:
            continue
        source = source_by_node_id.get(pair[0])
        target = source_by_node_id.get(pair[1])
        if source is None or target is None:
            raise ValueError("Replay ordering edge references an unselected source.")
        ordering_edges.add((source["skill_id"], target["skill_id"]))
    return source_bindings, selected_skill_ids, ordering_edges


def _ordered_variant_ids(selected_skill_ids: Sequence[str]) -> list[str]:
    return [
        "no_skill",
        "naive_union",
        *(f"singleton:{skill_id}" for skill_id in selected_skill_ids),
        "full_composition",
        *(f"leave_one_out:{skill_id}" for skill_id in selected_skill_ids),
        "wrong_order",
    ]


def _packet_plan(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    plan = packet.get("composition_plan")
    if not isinstance(plan, Mapping):
        raise ValueError("Replay packet does not have a composition plan.")
    return plan


def _skill_by_node(source_bindings: Sequence[Mapping[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for binding in source_bindings:
        node_id = _nonempty(binding.get("source_node_id"), field="source_binding.node")
        skill_id = _nonempty(binding.get("skill_id"), field="source_binding.skill")
        if node_id in result or skill_id in result.values():
            raise ValueError(
                "Replay source bindings must have one-to-one skill identities."
            )
        result[node_id] = skill_id
    return result


def _logical_handoff(
    contract: Mapping[str, Any],
    *,
    skill_by_node: Mapping[str, str],
) -> dict[str, Any]:
    producer_node_id = _nonempty(
        contract.get("producer_node_id"), field="handoff.producer_node_id"
    )
    consumer_node_id = _nonempty(
        contract.get("consumer_node_id"), field="handoff.consumer_node_id"
    )
    producer_skill_id = skill_by_node.get(producer_node_id)
    consumer_skill_id = skill_by_node.get(consumer_node_id)
    if producer_skill_id is None or consumer_skill_id is None:
        raise ValueError(
            "Replay handoff references a source outside the selected graph."
        )
    return {
        "handoff_id": _nonempty(contract.get("handoff_id"), field="handoff.id"),
        "relationship_id": _nonempty(
            contract.get("relationship_id"), field="handoff.relationship_id"
        ),
        "producer_skill_id": producer_skill_id,
        "consumer_skill_id": consumer_skill_id,
        "relationship_type": _nonempty(
            contract.get("relationship_type"), field="handoff.relationship_type"
        ),
        "required_inputs": list(contract.get("required_inputs") or []),
        "produced_outputs": list(contract.get("produced_outputs") or []),
        "producer_exit_gates": list(contract.get("producer_exit_gates") or []),
        "citations": list(contract.get("citations") or []),
    }


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


def _replay_record(
    *,
    preflight: Mapping[str, Any],
    proposal: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    plan = packet.get("composition_plan")
    if not isinstance(plan, Mapping):
        raise ValueError("Replay packet does not have a composition plan.")
    return {
        "preflight": dict(preflight),
        "preflight_digest": stable_digest(dict(preflight)),
        "semantic_proposal": dict(proposal),
        "semantic_proposal_digest": stable_digest(dict(proposal)),
        "packet": dict(packet),
        "packet_digest": stable_digest(dict(packet)),
        "composition_plan_digest": stable_digest(dict(plan)),
    }


def _control_plan_identity(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in plan.items()
        if key not in {"control_plan_id", "control_plan_digest"}
    }


def build_benchmark_control_plan(
    *,
    run_plan: Mapping[str, Any],
    semantic_proposals: Mapping[str, Any],
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay compiler outputs and derive host controls without executing them."""

    if run_plan.get("schema") != BENCHMARK_RUN_PLAN_SCHEMA:
        raise ValueError(f"run_plan.schema must be {BENCHMARK_RUN_PLAN_SCHEMA}.")
    validate_benchmark_run_plan(
        run_plan,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
    )
    routing_proposals, behavioral_proposals = _validate_proposal_bundle(
        semantic_proposals,
        run_plan,
    )
    fixtures = _fixture_index(behavioral_fixtures)
    routing_requests = _request_index(
        run_plan,
        field="routing_requests",
        subject_field="case_id",
    )
    behavioral_requests = _request_index(
        run_plan,
        field="behavioral_requests",
        subject_field="fixture_id",
    )

    routing_controls: list[dict[str, Any]] = []
    for case_id, request in routing_requests.items():
        fixture_id = _nonempty(request.get("fixture_id"), field=f"{case_id}.fixture_id")
        fixture = fixtures.get(fixture_id)
        if fixture is None:
            raise ValueError(f"{case_id} references unknown fixture {fixture_id}.")
        preflight, packet = _replay_packet(
            fixture=fixture,
            request=request,
            proposal=routing_proposals[case_id],
        )
        _bindings, selected_skill_ids, _edges = _role_projection(fixture, packet)
        routing_controls.append(
            {
                "case_id": case_id,
                "request_id": request["request_id"],
                "input_digest": request["input_digest"],
                "selected_skill_ids": selected_skill_ids,
                "replay": _replay_record(
                    preflight=preflight,
                    proposal=routing_proposals[case_id],
                    packet=packet,
                ),
            }
        )

    behavioral_controls: list[dict[str, Any]] = []
    for fixture_id, request in behavioral_requests.items():
        fixture = fixtures.get(fixture_id)
        if fixture is None:
            raise ValueError(f"Unknown behavioral fixture {fixture_id}.")
        preflight, packet = _replay_packet(
            fixture=fixture,
            request=request,
            proposal=behavioral_proposals[fixture_id],
        )
        source_bindings, selected_skill_ids, ordering_edges = _role_projection(
            fixture,
            packet,
        )
        behavioral_controls.append(
            {
                "fixture_id": fixture_id,
                "request_id": request["request_id"],
                "selected_skill_ids": selected_skill_ids,
                "ordered_skill_ids": list(selected_skill_ids),
                "source_bindings": source_bindings,
                "ordering_edges": [
                    {"source_skill_id": source, "target_skill_id": target}
                    for source, target in sorted(ordering_edges)
                ],
                "variants": _variant_controls(
                    fixture_id=fixture_id,
                    request_id=str(request["request_id"]),
                    source_bindings=source_bindings,
                    preflight=preflight,
                    packet=packet,
                ),
                "replay": _replay_record(
                    preflight=preflight,
                    proposal=behavioral_proposals[fixture_id],
                    packet=packet,
                ),
            }
        )

    control_plan: dict[str, Any] = {
        "schema": BENCHMARK_CONTROL_PLAN_SCHEMA,
        "run_manifest_id": run_plan["run_manifest_id"],
        "run_manifest_digest": run_plan["run_manifest_digest"],
        "semantic_proposals_digest": stable_digest(dict(semantic_proposals)),
        "routing_controls": routing_controls,
        "behavioral_controls": behavioral_controls,
        "automatic_tool_execution": False,
        "receipt_persistence": "not_performed",
    }
    identity = _control_plan_identity(control_plan)
    control_plan["control_plan_digest"] = stable_digest(identity)
    control_plan["control_plan_id"] = "benchmark-control-" + stable_digest(
        identity,
        20,
    )
    return control_plan


def validate_benchmark_control_plan(
    control_plan: Mapping[str, Any],
    *,
    run_plan: Mapping[str, Any],
    semantic_proposals: Mapping[str, Any],
    routing_golden: Mapping[str, Any],
    behavioral_fixtures: Mapping[str, Any],
) -> None:
    """Reject controls that were not deterministically derived from compiler replay."""

    if control_plan.get("schema") != BENCHMARK_CONTROL_PLAN_SCHEMA:
        raise ValueError(
            f"control_plan.schema must be {BENCHMARK_CONTROL_PLAN_SCHEMA}."
        )
    expected = build_benchmark_control_plan(
        run_plan=run_plan,
        semantic_proposals=semantic_proposals,
        routing_golden=routing_golden,
        behavioral_fixtures=behavioral_fixtures,
    )
    if dict(control_plan) != expected:
        raise ValueError(
            "Benchmark control plan does not match the replayed compiler outputs."
        )
