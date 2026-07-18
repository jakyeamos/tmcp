"""Deterministic phase-scoped context capsules for composition benchmarks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .composition_preflight import stable_digest
from .composition_phase_capsule_support import (
    PhaseCapsuleError,
    _agent_objective,
    _canonical_json,
    _capsule_record,
    _json_value,
    _mapping_list,
    _nonempty,
    _string_list,
)
from .composition_phase_slice_closures import (
    PhaseSliceClosureError,
    preflight_candidate_entries,
    source_capsule_entries,
    validate_stage_source_slice_closures,
)
from .harvest_nodes import content_digest_for, normalized_source_content


CONTEXT_ACCOUNTING_SCHEMA = "tmcp-composition-context-accounting-v0.1"
PHASE_CAPSULE_SCHEMA = "tmcp-composition-phase-capsule-v0.1"
CONTEXT_ACCOUNTING_POLICY = "phase_capsule_runtime_peak_vs_naive_union"
MAX_HANDOFF_PAYLOAD_CHARS = 16_384


def _source_catalog(
    source_contents: Mapping[str, object] | Sequence[Mapping[str, object]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    records: list[dict[str, object]] = []
    if isinstance(source_contents, Mapping):
        for key, raw in source_contents.items():
            skill_id = _nonempty(key, field="source_contents key")
            if isinstance(raw, Mapping):
                if raw.get("skill_id") is not None and str(raw["skill_id"]) != skill_id:
                    raise PhaseCapsuleError("source_contents key does not match skill_id.")
                record = {**raw, "skill_id": skill_id}
            elif isinstance(raw, str):
                record = {"skill_id": skill_id, "content": raw}
            else:
                raise PhaseCapsuleError(f"source_contents.{skill_id} is invalid.")
            records.append(record)
    elif isinstance(source_contents, Sequence) and not isinstance(
        source_contents, (str, bytes)
    ):
        for index, raw in enumerate(source_contents):
            if not isinstance(raw, Mapping):
                raise PhaseCapsuleError(f"source_contents[{index}] must be an object.")
            records.append(dict(raw))
    else:
        raise PhaseCapsuleError("source_contents must be a source mapping or sequence.")
    by_skill: dict[str, list[dict[str, Any]]] = {}
    skill_by_node: dict[str, str] = {}
    source_slice_ids: set[str] = set()
    for index, raw in enumerate(records):
        field = f"source_contents[{index}]"
        skill_id = _nonempty(raw.get("skill_id"), field=f"{field}.skill_id")
        source_node_id = _nonempty(
            raw.get("source_node_id") or raw.get("source_id") or skill_id,
            field=f"{field}.source_node_id",
        )
        source_slice_id = _nonempty(
            raw.get("source_slice_id") or raw.get("slice_id") or source_node_id,
            field=f"{field}.source_slice_id",
        )
        content = raw.get("content")
        if not isinstance(content, str):
            raise PhaseCapsuleError(f"{field}.content must be a string.")
        normalized_content = normalized_source_content(content)
        if not normalized_content:
            raise PhaseCapsuleError(f"{field}.content must not be empty.")
        content_digest = content_digest_for(normalized_content)
        if str(raw.get("content_digest") or "").strip() not in {"", content_digest}:
            raise PhaseCapsuleError(f"{field}.content_digest does not match content.")
        source_digest = str(raw.get("source_digest") or content_digest).strip()
        slice_digest = str(raw.get("slice_digest") or content_digest).strip()
        if slice_digest != content_digest:
            raise PhaseCapsuleError(f"{field}.slice_digest does not match content.")
        char_start = raw.get("char_start", 0)
        char_end = raw.get("char_end", len(content))
        if (
            isinstance(char_start, bool)
            or isinstance(char_end, bool)
            or not isinstance(char_start, int)
            or not isinstance(char_end, int)
            or char_start < 0
            or char_end <= char_start
        ):
            raise PhaseCapsuleError(f"{field} has an invalid source slice range.")
        existing_skill = skill_by_node.get(source_node_id)
        if existing_skill is not None and existing_skill != skill_id:
            raise PhaseCapsuleError(f"source node {source_node_id} binds multiple skills.")
        if source_slice_id in source_slice_ids:
            raise PhaseCapsuleError(f"source_contents repeats source slice {source_slice_id}.")
        source = {
            "skill_id": skill_id,
            "source_node_id": source_node_id,
            "source_slice_id": source_slice_id,
            "source_role": str(raw.get("source_role") or "active_skill").strip()
            or "active_skill",
            "content_digest": content_digest,
            "source_digest": source_digest,
            "slice_digest": slice_digest,
            "char_start": char_start,
            "char_end": char_end,
            "content": normalized_content,
        }
        existing_sources = by_skill.setdefault(skill_id, [])
        if existing_sources and (
            existing_sources[0]["source_node_id"] != source_node_id
            or existing_sources[0]["source_digest"] != source_digest
            or existing_sources[0]["source_role"] != source["source_role"]
        ):
            raise PhaseCapsuleError(f"source_contents has inconsistent {skill_id} slices.")
        existing_sources.append(source)
        skill_by_node[source_node_id] = skill_id
        source_slice_ids.add(source_slice_id)
    if not by_skill:
        raise PhaseCapsuleError("source_contents must include at least one source.")
    for sources in by_skill.values():
        sources.sort(key=lambda item: (int(item["char_start"]), int(item["char_end"]), str(item["slice_digest"]), str(item["source_slice_id"])))
    return by_skill, skill_by_node


def _resolve_skill_id(
    value: str,
    *,
    sources_by_skill: Mapping[str, Sequence[Mapping[str, Any]]],
    skill_by_node: Mapping[str, str],
    field: str,
) -> str:
    if value in sources_by_skill:
        return value
    resolved = skill_by_node.get(value)
    if resolved is not None:
        return resolved
    raise PhaseCapsuleError(f"{field} references unknown source {value}.")


def _stage_catalog(
    source_projection: Mapping[str, Any],
    *,
    sources_by_skill: Mapping[str, Sequence[Mapping[str, Any]]],
    skill_by_node: Mapping[str, str],
) -> list[dict[str, Any]]:
    raw_stages = _mapping_list(source_projection.get("stages"), field="stages")
    if not raw_stages:
        raise PhaseCapsuleError("source_projection.stages must include at least one stage.")
    stages: list[dict[str, Any]] = []
    stage_ids: set[str] = set()
    stage_orders: set[int] = set()
    for index, raw_stage in enumerate(raw_stages, start=1):
        field = f"stages[{index - 1}]"
        stage_id = _nonempty(raw_stage.get("stage_id"), field=f"{field}.stage_id")
        if stage_id in stage_ids:
            raise PhaseCapsuleError(f"source_projection.stages has duplicate {stage_id}.")
        raw_skill_ids = _string_list(
            raw_stage.get("active_skill_ids"), field=f"{field}.active_skill_ids"
        )
        if not raw_skill_ids:
            raw_skill_ids = _string_list(
                raw_stage.get("node_ids"), field=f"{field}.node_ids"
            )
        if not raw_skill_ids:
            raise PhaseCapsuleError(f"{field} must include an active source.")
        active_skill_ids = [
            _resolve_skill_id(
                skill_id,
                sources_by_skill=sources_by_skill,
                skill_by_node=skill_by_node,
                field=f"{field}.active_skill_ids",
            )
            for skill_id in raw_skill_ids
        ]
        if len(active_skill_ids) != len(set(active_skill_ids)):
            raise PhaseCapsuleError(f"{field} resolves duplicate active sources.")
        order = raw_stage.get("order", index)
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise PhaseCapsuleError(f"{field}.order must be a positive integer.")
        if order in stage_orders:
            raise PhaseCapsuleError(f"source_projection.stages has duplicate order {order}.")
        phase = _nonempty(raw_stage.get("phase"), field=f"{field}.phase")
        stage = {
            "stage_id": stage_id,
            "order": order,
            "phase": phase,
            "status": str(raw_stage.get("status") or "deferred"),
            "active_skill_ids": active_skill_ids,
            "entry_conditions": _json_value(
                raw_stage.get("entry_conditions") or [],
                field=f"{field}.entry_conditions",
            ),
            "bridge_instructions": _json_value(
                raw_stage.get("bridge_instructions") or [],
                field=f"{field}.bridge_instructions",
            ),
            "handoff_contracts": _json_value(
                raw_stage.get("handoff_contracts") or [],
                field=f"{field}.handoff_contracts",
            ),
        }
        stages.append(stage)
        stage_ids.add(stage_id)
        stage_orders.add(order)
    return sorted(stages, key=lambda item: (item["order"], item["stage_id"]))


def _contract_skill_id(
    contract: Mapping[str, Any],
    *,
    role: str,
    sources_by_skill: Mapping[str, Sequence[Mapping[str, Any]]],
    skill_by_node: Mapping[str, str],
    field: str,
) -> str:
    direct = str(contract.get(f"{role}_skill_id") or "").strip()
    if direct:
        return _resolve_skill_id(
            direct,
            sources_by_skill=sources_by_skill,
            skill_by_node=skill_by_node,
            field=f"{field}.{role}_skill_id",
        )
    node_id = str(contract.get(f"{role}_node_id") or "").strip()
    if node_id:
        return _resolve_skill_id(
            node_id,
            sources_by_skill=sources_by_skill,
            skill_by_node=skill_by_node,
            field=f"{field}.{role}_node_id",
        )
    raise PhaseCapsuleError(f"{field} must identify its {role} source.")


def _contract_catalog(
    source_projection: Mapping[str, Any],
    stages: Sequence[Mapping[str, Any]],
    *,
    sources_by_skill: Mapping[str, Sequence[Mapping[str, Any]]],
    skill_by_node: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Collect root and stage contracts while rejecting conflicting duplicates."""

    raw_contracts = _mapping_list(
        source_projection.get("handoff_contracts"), field="handoff_contracts"
    )
    for stage in stages:
        raw_contracts.extend(
            _mapping_list(
                stage.get("handoff_contracts"),
                field=f"{stage['stage_id']}.handoff_contracts",
            )
        )
    catalog: dict[str, dict[str, Any]] = {}
    for index, raw_contract in enumerate(raw_contracts):
        field = f"handoff_contracts[{index}]"
        handoff_id = _nonempty(raw_contract.get("handoff_id"), field=f"{field}.handoff_id")
        contract = _json_value(dict(raw_contract), field=field)
        record = {
            "handoff_id": handoff_id,
            "contract": contract,
            "producer_skill_id": _contract_skill_id(
                raw_contract,
                role="producer",
                sources_by_skill=sources_by_skill,
                skill_by_node=skill_by_node,
                field=field,
            ),
            "consumer_skill_id": _contract_skill_id(
                raw_contract,
                role="consumer",
                sources_by_skill=sources_by_skill,
                skill_by_node=skill_by_node,
                field=field,
            ),
        }
        existing = catalog.get(handoff_id)
        if existing is not None and _canonical_json(existing) != _canonical_json(record):
            raise PhaseCapsuleError(
                f"handoff contract {handoff_id} has conflicting definitions."
            )
        catalog[handoff_id] = record
    return catalog


def _payload_catalog(
    handoff_payloads: Mapping[str, object] | None,
    *,
    contract_ids: set[str],
) -> dict[str, Any]:
    if handoff_payloads is None:
        return {}
    if not isinstance(handoff_payloads, Mapping):
        raise PhaseCapsuleError("handoff_payloads must be an object keyed by handoff id.")
    payloads: dict[str, Any] = {}
    for raw_id, value in handoff_payloads.items():
        handoff_id = _nonempty(raw_id, field="handoff_payloads key")
        if handoff_id not in contract_ids:
            raise PhaseCapsuleError(
                f"handoff_payloads references unknown handoff {handoff_id}."
            )
        payload = _json_value(value, field=f"handoff_payloads.{handoff_id}")
        if len(_canonical_json(payload)) > MAX_HANDOFF_PAYLOAD_CHARS:
            raise PhaseCapsuleError(
                f"handoff_payloads.{handoff_id} exceeds the bounded payload limit."
            )
        payloads[handoff_id] = payload
    return payloads


def _handoff_entries(
    contracts: Sequence[Mapping[str, Any]],
    *,
    payloads: Mapping[str, Any],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for contract in sorted(contracts, key=lambda item: str(item["handoff_id"])):
        handoff_id = str(contract["handoff_id"])
        entry: dict[str, Any] = {
            "handoff_id": handoff_id,
            "producer_skill_id": contract["producer_skill_id"],
            "contract": contract["contract"],
            "contract_digest": stable_digest(contract["contract"]),
            "payload_present": handoff_id in payloads,
        }
        if handoff_id in payloads:
            entry["payload"] = payloads[handoff_id]
            entry["payload_digest"] = stable_digest(payloads[handoff_id])
        entry["handoff_digest"] = stable_digest(entry)
        entries.append(entry)
    return entries


def _agent_stage_context(stage: Mapping[str, Any]) -> dict[str, Any]:
    """Project a compiler stage into the instructions an agent must receive.

    The complete stage remains in the bound composition plan.  Repeating its
    controller ids, trust metadata, and handoff contracts inside every active
    capsule adds no executable instruction and defeats phase-scoped loading.
    Each compiler-issued bridge instruction already states the role, required
    input, produced handoff, and exit gate.
    """

    bridges: list[dict[str, str]] = []
    for raw_bridge in _mapping_list(
        stage.get("bridge_instructions"), field="stage.bridge_instructions"
    ):
        instruction = str(raw_bridge.get("instruction") or "").strip()
        if not instruction:
            continue
        bridge: dict[str, str] = {"instruction": instruction}
        role = str(raw_bridge.get("role") or "").strip()
        if role:
            bridge["role"] = role
        bridges.append(bridge)
    return {
        "phase": _nonempty(stage.get("phase"), field="stage.phase"),
        "entry_conditions": _json_value(
            stage.get("entry_conditions") or [], field="stage.entry_conditions"
        ),
        "bridge_instructions": bridges,
    }


def _agent_source_entries(
    sources: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Keep source behavior and its skill identity in the phase prompt."""

    return [
        {
            "skill_id": str(source["skill_id"]),
            "source_role": str(source["source_role"]),
            "content": str(source["content"]),
        }
        for source in sources
    ]


def _agent_handoff_entries(
    handoffs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Load actionable handoff facts without repeating equivalent obligations.

    A graph may yield multiple typed edges that compile to the same handoff
    obligation for one consumer.  The bound plan and accounting record retain
    every contract digest, while the active agent capsule carries one complete
    actionable instruction plus the identities of its equivalent handoffs.
    This avoids spending phase context on repeated prose without hiding an
    obligation the host may need to report or fulfill.
    """

    grouped: dict[str, list[dict[str, Any]]] = {}
    for handoff in handoffs:
        contract = handoff["contract"]
        entry: dict[str, Any] = {
            "handoff_id": _nonempty(
                handoff.get("handoff_id"), field="incoming_handoff.handoff_id"
            ),
            "producer_skill_id": _nonempty(
                handoff.get("producer_skill_id"),
                field="incoming_handoff.producer_skill_id",
            ),
            "required_inputs": _json_value(
                contract.get("required_inputs") or [],
                field="handoff_contract.required_inputs",
            ),
            "produced_outputs": _json_value(
                contract.get("produced_outputs") or [],
                field="handoff_contract.produced_outputs",
            ),
            "producer_exit_gates": _json_value(
                contract.get("producer_exit_gates") or [],
                field="handoff_contract.producer_exit_gates",
            ),
        }
        if handoff["payload_present"]:
            entry["payload"] = handoff["payload"]
        equivalence_key = _canonical_json(
            {key: value for key, value in entry.items() if key != "handoff_id"}
        )
        grouped.setdefault(equivalence_key, []).append(entry)

    result: list[dict[str, Any]] = []
    for entries in grouped.values():
        representative = dict(entries[0])
        equivalent_handoff_ids = [
            str(entry["handoff_id"]) for entry in entries[1:]
        ]
        if equivalent_handoff_ids:
            representative["equivalent_handoff_ids"] = equivalent_handoff_ids
        result.append(representative)
    return result


def build_phase_capsule_accounting(
    *,
    task_model: Mapping[str, Any],
    preflight: Mapping[str, Any],
    source_projection: Mapping[str, Any],
    source_contents: Mapping[str, object] | Sequence[Mapping[str, object]],
    runtime_envelope: Mapping[str, Any] | None = None,
    handoff_payloads: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    if not isinstance(task_model, Mapping):
        raise PhaseCapsuleError("task_model must be an object.")
    if not isinstance(preflight, Mapping):
        raise PhaseCapsuleError("preflight must be an object.")
    if not isinstance(source_projection, Mapping):
        raise PhaseCapsuleError("source_projection must be an object.")
    if runtime_envelope is not None and not isinstance(runtime_envelope, Mapping):
        raise PhaseCapsuleError("runtime_envelope must be an object.")

    normalized_task_model = _json_value(task_model, field="task_model")
    normalized_runtime_envelope = _json_value(
        runtime_envelope or {}, field="runtime_envelope"
    )
    agent_objective = _agent_objective(
        normalized_runtime_envelope, preflight=preflight
    )
    sources_by_skill, skill_by_node = _source_catalog(source_contents)
    stages = _stage_catalog(
        source_projection,
        sources_by_skill=sources_by_skill,
        skill_by_node=skill_by_node,
    )
    contracts = _contract_catalog(
        source_projection,
        stages,
        sources_by_skill=sources_by_skill,
        skill_by_node=skill_by_node,
    )
    payloads = _payload_catalog(handoff_payloads, contract_ids=set(contracts))
    governing_skill_ids = sorted(
        skill_id
        for skill_id, sources in sources_by_skill.items()
        if sources[0]["source_role"] == "governing_instruction"
    )
    try:
        stage_source_slice_closures = validate_stage_source_slice_closures(
            source_projection,
            stages,
            sources_by_skill=sources_by_skill,
            governing_skill_ids=governing_skill_ids,
        )
    except PhaseSliceClosureError as exc:
        raise PhaseCapsuleError(str(exc)) from exc

    try:
        candidate_entries = preflight_candidate_entries(
            preflight,
            sources_by_skill=sources_by_skill,
            skill_by_node=skill_by_node,
        )
    except PhaseSliceClosureError as exc:
        raise PhaseCapsuleError(str(exc)) from exc
    preflight_capsule = _capsule_record(
        {
            "schema": PHASE_CAPSULE_SCHEMA,
            "kind": "preflight_discovery",
            "objective": str(preflight.get("objective") or ""),
            "task_model": normalized_task_model,
            "semantic_proposal_contract": _json_value(
                preflight.get("semantic_proposal_contract")
                or {"schema": "tmcp-semantic-proposal-v0.1"},
                field="preflight.semantic_proposal_contract",
            ),
            "behavior_manifest_index": _json_value(
                preflight.get("behavior_manifest_index") or {},
                field="preflight.behavior_manifest_index",
            ),
            "candidate_source_slices": candidate_entries,
        }
    )

    phase_capsules: list[dict[str, Any]] = []
    selected_skill_ids: list[str] = []
    for stage in stages:
        current_skill_ids = list(stage["active_skill_ids"])
        source_skill_ids = list(
            dict.fromkeys(governing_skill_ids + current_skill_ids)
        )
        selected_skill_ids.extend(current_skill_ids)
        incoming_contracts = [
            contract
            for contract in contracts.values()
            if contract["consumer_skill_id"] in current_skill_ids
        ]
        incoming_handoffs = _handoff_entries(incoming_contracts, payloads=payloads)
        source_entries = source_capsule_entries(
            source_skill_ids,
            sources_by_skill=sources_by_skill,
            allowed_slice_ids_by_node=(
                stage_source_slice_closures.get(str(stage["stage_id"]))
                if stage_source_slice_closures is not None
                else None
            ),
        )
        capsule = _capsule_record(
            {
                "schema": PHASE_CAPSULE_SCHEMA,
                "kind": "runtime_phase",
                "objective": agent_objective,
                "task_model": normalized_task_model,
                "stage": _agent_stage_context(stage),
                "sources": _agent_source_entries(source_entries),
                "incoming_handoffs": _agent_handoff_entries(incoming_handoffs),
            }
        )
        phase_capsules.append(
            {
                "stage_id": stage["stage_id"],
                "stage_order": stage["order"],
                "phase": stage["phase"],
                "source_ids": list(
                    dict.fromkeys(item["source_node_id"] for item in source_entries)
                ),
                "source_skill_ids": source_skill_ids,
                "source_slice_ids": [item["source_slice_id"] for item in source_entries],
                "source_slice_digests": [item["slice_digest"] for item in source_entries],
                "source_digests": list(
                    dict.fromkeys(item["source_digest"] for item in source_entries)
                ),
                "content_digests": [item["content_digest"] for item in source_entries],
                "incoming_handoff_digests": [
                    handoff["handoff_digest"] for handoff in incoming_handoffs
                ],
                **capsule,
            }
        )

    all_selected_skill_ids = list(
        dict.fromkeys(governing_skill_ids + selected_skill_ids)
    )
    naive_union_slice_closure: dict[str, set[str]] | None = None
    if stage_source_slice_closures is not None:
        naive_union_slice_closure = {}
        for stage_closure in stage_source_slice_closures.values():
            for node_id, slice_ids in stage_closure.items():
                naive_union_slice_closure.setdefault(node_id, set()).update(slice_ids)
    naive_union_capsule = _capsule_record(
        {
            "schema": PHASE_CAPSULE_SCHEMA,
            "kind": "naive_union",
            "runtime_envelope": normalized_runtime_envelope,
            "task_model": normalized_task_model,
            "sources": [
                {
                    "skill_id": source["skill_id"],
                    "source_role": source["source_role"],
                    "content": source["content"],
                }
                for source in source_capsule_entries(
                    all_selected_skill_ids,
                    sources_by_skill=sources_by_skill,
                    allowed_slice_ids_by_node=naive_union_slice_closure,
                )
            ],
        }
    )
    runtime_peak_context_tokens = max(
        int(item["estimated_tokens"]) for item in phase_capsules
    )
    naive_union_context_tokens = int(naive_union_capsule["estimated_tokens"])
    accounting: dict[str, Any] = {
        "schema": CONTEXT_ACCOUNTING_SCHEMA,
        "policy": CONTEXT_ACCOUNTING_POLICY,
        "runtime_envelope": normalized_runtime_envelope,
        "preflight_capsule": preflight_capsule,
        "preflight_capsule_digest": preflight_capsule["capsule_digest"],
        "preflight_discovery_tokens": preflight_capsule["estimated_tokens"],
        "phase_capsules": phase_capsules,
        "naive_union_capsule": naive_union_capsule,
        "naive_union_capsule_digest": naive_union_capsule["capsule_digest"],
        "runtime_peak_context_tokens": runtime_peak_context_tokens,
        "naive_union_context_tokens": naive_union_context_tokens,
        "context_ratio": runtime_peak_context_tokens / naive_union_context_tokens,
        "same_host_transcript_tokens": int(preflight_capsule["estimated_tokens"])
        + sum(int(item["estimated_tokens"]) for item in phase_capsules),
        "compiled_context_tokens": runtime_peak_context_tokens,
        "naive_context_tokens": naive_union_context_tokens,
    }
    digest = stable_digest(accounting)
    accounting["context_accounting_digest"] = digest
    accounting["context_digest"] = digest
    return accounting
