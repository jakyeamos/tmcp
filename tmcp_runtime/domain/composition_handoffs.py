"""Deterministic handoff contracts derived from validated composition graphs."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .composition_preflight import (
    COMPOSITION_TRUST,
    json_list,
    ordered_unique,
    stable_digest,
    string_list,
)
from .composition_validation import ordering_pair


def relationship_id_for(edge: Mapping[str, Any]) -> str:
    """Return the stable runtime relationship identifier for one typed edge."""

    return "relationship-" + stable_digest(
        [
            str(edge.get("from") or ""),
            str(edge.get("type") or ""),
            str(edge.get("to") or ""),
            sorted(string_list(edge.get("citations"))),
        ],
        16,
    )


def _source_digest(source_digests_by_node: Mapping[str, str], node_id: str) -> str:
    return str(source_digests_by_node.get(node_id) or "")


def _citation_digests(
    citations: list[str], slice_digests_by_id: Mapping[str, str]
) -> list[str]:
    return sorted(
        {
            str(slice_digests_by_id.get(citation) or "")
            for citation in citations
            if str(slice_digests_by_id.get(citation) or "")
        }
    )


def _contract_citations(
    edge: Mapping[str, Any],
    producer: Mapping[str, Any],
    consumer: Mapping[str, Any],
) -> list[str]:
    return sorted(
        set(
            string_list(edge.get("citations"))
            + string_list(producer.get("citations"))
            + string_list(consumer.get("citations"))
        )
    )


def _handoff_id(
    *,
    graph_digest: str,
    relationship_id: str,
    producer_node_id: str,
    consumer_node_id: str,
    relationship_type: str,
    required_inputs: list[str],
    produced_outputs: list[str],
    producer_exit_gates: list[str],
    citations: list[str],
    source_digests_by_node: Mapping[str, str],
    slice_digests_by_id: Mapping[str, str],
) -> str:
    return "handoff-" + stable_digest(
        {
            "graph_digest": graph_digest,
            "relationship_id": relationship_id,
            "producer_source_digest": _source_digest(
                source_digests_by_node, producer_node_id
            ),
            "consumer_source_digest": _source_digest(
                source_digests_by_node, consumer_node_id
            ),
            "relationship_type": relationship_type,
            "required_inputs": required_inputs,
            "produced_outputs": produced_outputs,
            "producer_exit_gates": producer_exit_gates,
            "citation_digests": _citation_digests(citations, slice_digests_by_id),
        },
        20,
    )


def build_handoff_contracts(
    roles: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    graph_digest: str,
    source_digests_by_node: Mapping[str, str],
    slice_digests_by_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Compile source-cited producer-to-consumer contracts for ordering edges."""

    roles_by_id = {
        str(role.get("node_id") or ""): role
        for role in roles
        if str(role.get("node_id") or "")
    }
    contracts_by_id: dict[str, dict[str, Any]] = {}
    for edge in edges:
        pair = ordering_pair(edge)
        if pair is None:
            continue
        producer_node_id, consumer_node_id = pair
        producer = roles_by_id.get(producer_node_id)
        consumer = roles_by_id.get(consumer_node_id)
        if producer is None or consumer is None:
            continue
        required_inputs = ordered_unique(string_list(consumer.get("inputs")))
        produced_outputs = ordered_unique(string_list(producer.get("outputs")))
        producer_exit_gates = ordered_unique(string_list(producer.get("exit_gates")))
        citations = _contract_citations(edge, producer, consumer)
        relationship_id = relationship_id_for(edge)
        handoff_id = _handoff_id(
            graph_digest=graph_digest,
            relationship_id=relationship_id,
            producer_node_id=producer_node_id,
            consumer_node_id=consumer_node_id,
            relationship_type=str(edge.get("type") or ""),
            required_inputs=required_inputs,
            produced_outputs=produced_outputs,
            producer_exit_gates=producer_exit_gates,
            citations=citations,
            source_digests_by_node=source_digests_by_node,
            slice_digests_by_id=slice_digests_by_id,
        )
        contracts_by_id.setdefault(
            handoff_id,
            {
                "handoff_id": handoff_id,
                "relationship_id": relationship_id,
                "producer_node_id": producer_node_id,
                "consumer_node_id": consumer_node_id,
                "relationship_type": str(edge.get("type") or ""),
                "required_inputs": required_inputs,
                "produced_outputs": produced_outputs,
                "producer_exit_gates": producer_exit_gates,
                "citations": citations,
                "trust": COMPOSITION_TRUST,
            },
        )
    return [contracts_by_id[handoff_id] for handoff_id in sorted(contracts_by_id)]


def handoff_identity_projection(
    contracts: list[dict[str, Any]],
    *,
    source_digests_by_node: Mapping[str, str],
    slice_digests_by_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Normalize contracts for recipe identity without path or node-name dependence."""

    projection = [
        {
            "producer_source_digest": _source_digest(
                source_digests_by_node,
                str(contract.get("producer_node_id") or ""),
            ),
            "consumer_source_digest": _source_digest(
                source_digests_by_node,
                str(contract.get("consumer_node_id") or ""),
            ),
            "relationship_type": str(contract.get("relationship_type") or ""),
            "required_inputs": ordered_unique(
                string_list(contract.get("required_inputs"))
            ),
            "produced_outputs": ordered_unique(
                string_list(contract.get("produced_outputs"))
            ),
            "producer_exit_gates": ordered_unique(
                string_list(contract.get("producer_exit_gates"))
            ),
            "citation_digests": _citation_digests(
                string_list(contract.get("citations")), slice_digests_by_id
            ),
        }
        for contract in contracts
    ]
    return sorted(
        projection,
        key=lambda item: (
            item["producer_source_digest"],
            item["consumer_source_digest"],
            item["relationship_type"],
            tuple(item["required_inputs"]),
            tuple(item["produced_outputs"]),
        ),
    )


def attach_handoff_contracts_to_stages(
    stages: list[dict[str, Any]], contracts: list[dict[str, Any]]
) -> None:
    """Attach incoming contracts to consumers and relationship ids to bridges."""

    contracts_by_node: dict[str, list[str]] = {}
    for contract in contracts:
        handoff_id = str(contract.get("handoff_id") or "")
        if not handoff_id:
            continue
        for node_id in (
            str(contract.get("producer_node_id") or ""),
            str(contract.get("consumer_node_id") or ""),
        ):
            if node_id:
                contracts_by_node.setdefault(node_id, []).append(handoff_id)
    for stage in stages:
        node_ids = set(string_list(stage.get("node_ids")))
        incoming = [
            contract
            for contract in contracts
            if str(contract.get("consumer_node_id") or "") in node_ids
        ]
        if incoming:
            stage["handoff_contracts"] = copy.deepcopy(incoming)
        for bridge in stage.get("bridge_instructions", []):
            if not isinstance(bridge, dict):
                continue
            node_id = str(bridge.get("node_id") or "")
            bridge["handoff_ids"] = sorted(set(contracts_by_node.get(node_id, [])))


def _stage_catalog(
    plan: Mapping[str, Any],
) -> tuple[dict[str, tuple[str, int]], list[dict[str, Any]]]:
    stages_by_node: dict[str, tuple[str, int]] = {}
    invalid: list[dict[str, Any]] = []
    for index, stage in enumerate(json_list(plan.get("ordered_stages"))):
        if not isinstance(stage, Mapping):
            invalid.append({"index": index, "reason": "stage_not_object"})
            continue
        stage_id = str(stage.get("stage_id") or "").strip()
        for node_id in string_list(stage.get("node_ids")):
            if not stage_id or node_id in stages_by_node:
                invalid.append(
                    {
                        "index": index,
                        "node_id": node_id,
                        "reason": "missing_or_duplicate_stage_node",
                    }
                )
                continue
            stages_by_node[node_id] = (stage_id, index)
    return stages_by_node, invalid


def _contract_matches_graph(
    contract: Mapping[str, Any],
    producer: Mapping[str, Any],
    consumer: Mapping[str, Any],
    edge: Mapping[str, Any],
) -> str:
    if str(contract.get("relationship_type") or "") != str(edge.get("type") or ""):
        return "mismatched_handoff_relationship_type"
    if string_list(contract.get("required_inputs")) != ordered_unique(
        string_list(consumer.get("inputs"))
    ):
        return "mismatched_handoff_inputs"
    if string_list(contract.get("produced_outputs")) != ordered_unique(
        string_list(producer.get("outputs"))
    ):
        return "mismatched_handoff_outputs"
    if string_list(contract.get("producer_exit_gates")) != ordered_unique(
        string_list(producer.get("exit_gates"))
    ):
        return "mismatched_handoff_exit_gates"
    expected_citations = _contract_citations(edge, producer, consumer)
    if string_list(contract.get("citations")) != expected_citations:
        return "mismatched_handoff_citations"
    if str(contract.get("trust") or "") != COMPOSITION_TRUST:
        return "mismatched_handoff_trust"
    return ""


def handoff_contract_catalog(
    plan: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate runtime contracts against selected roles, stages, and typed edges."""

    roles_by_id = {
        str(role.get("node_id") or ""): role
        for role in json_list(plan.get("skill_roles"))
        if isinstance(role, Mapping) and str(role.get("node_id") or "")
    }
    stages_by_node, invalid = _stage_catalog(plan)
    edges_by_relationship_id = {
        relationship_id_for(edge): edge
        for edge in json_list(plan.get("typed_edges"))
        if isinstance(edge, Mapping) and ordering_pair(dict(edge)) is not None
    }
    contracts: list[dict[str, Any]] = []
    raw_by_handoff_id: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for index, value in enumerate(json_list(plan.get("handoff_contracts"))):
        if not isinstance(value, Mapping):
            invalid.append({"index": index, "reason": "contract_not_object"})
            continue
        contract = dict(value)
        handoff_id = str(contract.get("handoff_id") or "").strip()
        relationship_id = str(contract.get("relationship_id") or "").strip()
        producer_node_id = str(contract.get("producer_node_id") or "").strip()
        consumer_node_id = str(contract.get("consumer_node_id") or "").strip()
        if not handoff_id or handoff_id in seen:
            invalid.append(
                {
                    "index": index,
                    "handoff_id": handoff_id,
                    "reason": "missing_or_duplicate_handoff_id",
                }
            )
            continue
        seen.add(handoff_id)
        producer = roles_by_id.get(producer_node_id)
        consumer = roles_by_id.get(consumer_node_id)
        producer_stage = stages_by_node.get(producer_node_id)
        consumer_stage = stages_by_node.get(consumer_node_id)
        if not producer or not consumer or not producer_stage or not consumer_stage:
            invalid.append(
                {
                    "index": index,
                    "handoff_id": handoff_id,
                    "reason": "unknown_handoff_endpoint",
                }
            )
            continue
        edge = edges_by_relationship_id.get(relationship_id)
        pair = ordering_pair(dict(edge)) if edge is not None else None
        if pair != (producer_node_id, consumer_node_id):
            invalid.append(
                {
                    "index": index,
                    "handoff_id": handoff_id,
                    "reason": "unknown_handoff_relationship",
                }
            )
            continue
        if producer_stage[1] >= consumer_stage[1]:
            invalid.append(
                {
                    "index": index,
                    "handoff_id": handoff_id,
                    "reason": "invalid_handoff_stage_order",
                }
            )
            continue
        mismatch = _contract_matches_graph(contract, producer, consumer, edge)
        if mismatch:
            invalid.append(
                {"index": index, "handoff_id": handoff_id, "reason": mismatch}
            )
            continue
        raw_by_handoff_id[handoff_id] = contract
        contracts.append(
            {
                **contract,
                "handoff_id": handoff_id,
                "producer_node_id": producer_node_id,
                "consumer_node_id": consumer_node_id,
                "consumer_stage_id": consumer_stage[0],
            }
        )
    for stage_index, stage in enumerate(json_list(plan.get("ordered_stages"))):
        if not isinstance(stage, Mapping) or "handoff_contracts" not in stage:
            continue
        values = stage.get("handoff_contracts")
        if not isinstance(values, list):
            invalid.append(
                {"index": stage_index, "reason": "stage_handoff_contracts_not_array"}
            )
            continue
        stage_id = str(stage.get("stage_id") or "")
        for contract_index, value in enumerate(values):
            handoff_id = (
                str(value.get("handoff_id") or "") if isinstance(value, Mapping) else ""
            )
            if (
                not isinstance(value, Mapping)
                or raw_by_handoff_id.get(handoff_id) != dict(value)
                or str(dict(value).get("consumer_node_id") or "")
                not in string_list(stage.get("node_ids"))
                or stages_by_node.get(
                    str(dict(value).get("consumer_node_id") or ""), ("", -1)
                )[0]
                != stage_id
            ):
                invalid.append(
                    {
                        "index": stage_index,
                        "handoff_id": handoff_id,
                        "reason": "stage_handoff_contract_mismatch",
                        "stage_contract_index": contract_index,
                    }
                )
    return contracts, invalid
