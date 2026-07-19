"""Frozen, callback-friendly intake for host-assisted semantic composition."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.host_composition_provenance import (
    HOST_COMPOSITION_INTAKE_SCHEMA,
    build_host_composition_lineage,
    host_composition_receipt_provenance,
)
from tmcp_runtime.services.compose import (
    compose_packet_from_source_nodes,
    prepare_composition_from_source_nodes,
)

_IN_MEMORY_CACHE_HOME = "[HOST:in-memory]"
_RECEIPT_WRITE_ARGUMENTS = (
    "record_receipt",
    "receipt_persistence",
    "write_artifacts",
    "write_receipt",
)


def _source_nodes_snapshot(
    source_nodes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(source_nodes, (str, bytes)):
        raise ValueError("source_nodes must be a sequence of source-node objects.")
    copied: list[dict[str, Any]] = []
    for index, node in enumerate(source_nodes, start=1):
        if not isinstance(node, Mapping):
            raise ValueError(f"source_nodes[{index}] must be an object.")
        copied.append(deepcopy(dict(node)))
    return copied


def _intake_arguments(arguments: Mapping[str, Any]) -> dict[str, Any]:
    copied = deepcopy(dict(arguments))
    cache_policy = str(copied.get("cache_policy") or "none").strip()
    if cache_policy != "none":
        raise ValueError("Host composition intake requires cache_policy=none.")
    for field in ("project_recipe_id", "session_id"):
        if str(copied.get(field) or "").strip():
            raise ValueError(f"Host composition intake does not allow {field}.")
    if copied.get("semantic_proposal") is not None:
        raise ValueError("Host composition intake cannot receive semantic_proposal.")
    for field in _RECEIPT_WRITE_ARGUMENTS:
        if copied.get(field) not in (None, False, "", "not_performed"):
            raise ValueError(f"Host composition intake does not allow {field}.")
    copied["cache_policy"] = "none"
    return copied


@dataclass(frozen=True)
class HostCompositionIntake:
    """One immutable-by-contract preparation snapshot for a host proposal."""

    _arguments: dict[str, Any]
    _source_nodes: list[dict[str, Any]]
    _preflight: dict[str, Any]
    preflight_id: str
    preflight_digest: str
    source_snapshot_digest: str
    request_digest: str
    task_identity_digest: str

    def host_input(self) -> dict[str, Any]:
        """Return bounded host evidence without leaking the harvested snapshot."""

        return {
            "schema": HOST_COMPOSITION_INTAKE_SCHEMA,
            "preflight_id": self.preflight_id,
            "preflight_digest": self.preflight_digest,
            "source_snapshot_digest": self.source_snapshot_digest,
            "request_digest": self.request_digest,
            "task_identity_digest": self.task_identity_digest,
            "next_action": "propose_semantics",
            "automatic_tool_execution": False,
            "receipt_persistence": "not_performed",
            "preflight": deepcopy(self._preflight),
        }


def prepare_host_composition(
    arguments: Mapping[str, Any],
    *,
    source_nodes: Sequence[Mapping[str, Any]],
) -> HostCompositionIntake:
    """Freeze one cache-free source snapshot before host semantic reasoning."""

    frozen_arguments = _intake_arguments(arguments)
    frozen_nodes = _source_nodes_snapshot(source_nodes)
    preflight = prepare_composition_from_source_nodes(
        frozen_arguments,
        source_nodes=frozen_nodes,
    )
    task_identity = preflight.get("task_identity")
    if not isinstance(task_identity, Mapping):
        raise ValueError("Host composition preflight is missing task_identity.")
    return HostCompositionIntake(
        _arguments=frozen_arguments,
        _source_nodes=frozen_nodes,
        _preflight=preflight,
        preflight_id=str(preflight["preflight_id"]),
        preflight_digest=stable_digest(preflight),
        source_snapshot_digest=stable_digest(frozen_nodes),
        request_digest=stable_digest(frozen_arguments),
        task_identity_digest=stable_digest(dict(task_identity)),
    )


def _validate_intake_snapshot(intake: HostCompositionIntake) -> None:
    if stable_digest(intake._arguments) != intake.request_digest:
        raise ValueError("Host composition intake request snapshot changed.")
    if stable_digest(intake._source_nodes) != intake.source_snapshot_digest:
        raise ValueError("Host composition intake source snapshot changed.")
    if stable_digest(intake._preflight) != intake.preflight_digest:
        raise ValueError("Host composition intake preflight snapshot changed.")
    if str(intake._preflight.get("preflight_id") or "") != intake.preflight_id:
        raise ValueError("Host composition intake preflight identity changed.")
    task_identity = intake._preflight.get("task_identity")
    if not isinstance(task_identity, Mapping) or stable_digest(
        dict(task_identity)
    ) != intake.task_identity_digest:
        raise ValueError("Host composition intake task identity changed.")


def compose_host_composition(
    intake: HostCompositionIntake,
    semantic_proposal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one host proposal against the exact frozen intake snapshot."""

    if not isinstance(intake, HostCompositionIntake):
        raise ValueError("compose_host_composition requires HostCompositionIntake.")
    if not isinstance(semantic_proposal, Mapping):
        raise ValueError("semantic_proposal must be an object.")
    _validate_intake_snapshot(intake)
    arguments = deepcopy(intake._arguments)
    arguments["semantic_proposal"] = deepcopy(dict(semantic_proposal))
    packet = compose_packet_from_source_nodes(
        arguments,
        source_nodes=deepcopy(intake._source_nodes),
        global_graphs=[],
        receipts=[],
        cache_warnings=[],
        cache_home=_IN_MEMORY_CACHE_HOME,
        prepared_composition=deepcopy(intake._preflight),
    )
    origin = {
        "schema": HOST_COMPOSITION_INTAKE_SCHEMA,
        "preflight_id": intake.preflight_id,
        "preflight_digest": intake.preflight_digest,
        "source_snapshot_digest": intake.source_snapshot_digest,
        "request_digest": intake.request_digest,
        "task_identity_digest": intake.task_identity_digest,
        "reused_snapshot": True,
        "automatic_tool_execution": False,
        "receipt_persistence": "not_performed",
    }
    lineage = build_host_composition_lineage(
        origin,
        runtime_snapshot_status="initial_frozen_snapshot",
        current_preflight_id=intake.preflight_id,
        inherited_origin=False,
    )
    packet["host_composition"] = lineage
    receipt = packet.get("receipt_template")
    if isinstance(receipt, Mapping):
        packet["receipt_template"] = {
            **dict(receipt),
            "host_composition_provenance": host_composition_receipt_provenance(
                lineage
            ),
        }
    return packet


HostSemanticProposer = Callable[[dict[str, Any]], Mapping[str, Any]]


def run_host_composition(
    arguments: Mapping[str, Any],
    *,
    source_nodes: Sequence[Mapping[str, Any]],
    propose_semantics: HostSemanticProposer,
) -> dict[str, Any]:
    """Run one native host callback against one frozen source snapshot.

    This is intentionally an in-process host seam rather than a public MCP or
    CLI command: a portable call boundary cannot preserve a callback or the
    frozen intake object across processes.
    """

    if not callable(propose_semantics):
        raise ValueError("run_host_composition requires a callable propose_semantics.")
    intake = prepare_host_composition(arguments, source_nodes=source_nodes)
    semantic_proposal = propose_semantics(intake.host_input())
    if not isinstance(semantic_proposal, Mapping):
        raise ValueError("propose_semantics must return a semantic proposal object.")
    return compose_host_composition(intake, semantic_proposal)
