"""Compiler replay primitives used to derive composition benchmark controls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .composition_benchmark_protocol import (
    fixture_source_nodes,
    fixture_workspace_relative_path,
    prepare_fixture_preflight,
)
from .composition_preflight import stable_digest
from .composition_validation import ordering_pair
from ..services.compose import compose_packet_from_source_nodes


SEMANTIC_PROPOSAL_BUNDLE_SCHEMA = "tmcp-composition-benchmark-semantic-proposals-v0.1"


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
