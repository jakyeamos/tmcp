"""Strict normalization and gate evaluation for composition runtime evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .composition_handoffs import handoff_contract_catalog
from .composition_preflight import (
    COMPOSITION_PLAN_SCHEMA,
    PHASE_GATE_POLICIES,
    PHASE_GATE_POLICY_DEFAULT,
    PHASE_GATE_POLICY_ENTRY_HANDOFF,
    json_list,
    ordered_unique,
    stable_digest,
    string_list,
)


COMPOSITION_RUNTIME_EVIDENCE_SCHEMA = "tmcp-composition-runtime-evidence-v0.1"
PASSED_STATUSES = frozenset({"pass", "passed", "satisfied", "success", "verified"})
FAILED_STATUSES = frozenset({"blocked", "error", "fail", "failed"})
PENDING_STATUSES = frozenset({"pending", "running", "skipped", "unknown"})
AVAILABLE_HANDOFF_STATUSES = frozenset(
    {"available", "produced", "pass", "passed", "success", "verified"}
)
PHASE_OVERRIDE_TERMS = (
    "advance phase",
    "advance to",
    "bypass gate",
    "override gate",
    "proceed despite",
    "skip the gate",
)


def evidence_summary(value: object) -> str:
    if isinstance(value, Mapping):
        text = json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
    else:
        text = str(value)
    return text[:500]


def _evidence_values(
    value: object,
    field: str,
    unstructured: list[dict[str, Any]],
) -> list[Any]:
    if isinstance(value, list):
        values = value
    elif value is None:
        return []
    else:
        values = [value]
        unstructured.append(
            {
                "field": field,
                "index": 0,
                "summary": evidence_summary(value),
                "reason": "Expected an array; value was retained as one observation.",
            }
        )
    return [item for item in values if item is not None]


def _string_evidence(
    value: object,
    field: str,
    unstructured: list[dict[str, Any]],
) -> list[str]:
    values = _evidence_values(value, field, unstructured)
    strings: list[str] = []
    for index, item in enumerate(values):
        if isinstance(item, str) and item.strip():
            strings.append(item.strip())
            continue
        unstructured.append(
            {
                "field": field,
                "index": index,
                "summary": evidence_summary(item),
                "reason": "Expected a non-empty string observation.",
            }
        )
    return ordered_unique(strings)


def _structured_results(
    value: object,
    field: str,
    unstructured: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(value, Mapping) and isinstance(value.get("results"), list):
        value = value.get("results")
    values = _evidence_values(value, field, unstructured)
    results: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        if isinstance(item, Mapping):
            results.append({**dict(item), "_source": f"{field}[{index}]"})
        else:
            unstructured.append(
                {
                    "field": field,
                    "index": index,
                    "summary": evidence_summary(item),
                    "reason": "Unstructured evidence cannot satisfy a named gate.",
                }
            )
    return results


def _handoff_results(
    value: object,
    unstructured: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize artifact-backed handoff observations without trusting prose."""

    values = _evidence_values(value, "handoff_results", unstructured)
    results: list[dict[str, Any]] = []
    for index, item in enumerate(values):
        source = f"handoff_results[{index}]"
        if not isinstance(item, Mapping):
            unstructured.append(
                {
                    "field": "handoff_results",
                    "index": index,
                    "summary": evidence_summary(item),
                    "reason": "Unstructured evidence cannot satisfy a typed handoff.",
                }
            )
            continue
        result = dict(item)
        handoff_id = str(result.get("handoff_id") or "").strip()
        producer_node_id = str(result.get("producer_node_id") or "").strip()
        consumer_node_id = str(result.get("consumer_node_id") or "").strip()
        status = _handoff_status(result.get("status") or result.get("outcome"))
        consumed_inputs = string_list(result.get("consumed_inputs"))
        produced_outputs = string_list(result.get("produced_outputs"))
        evidence_refs = string_list(result.get("evidence_refs"))
        reasons: list[str] = []
        if not handoff_id:
            reasons.append("missing_handoff_id")
        if not producer_node_id:
            reasons.append("missing_handoff_producer")
        if not consumer_node_id:
            reasons.append("missing_handoff_consumer")
        if status == "unknown":
            reasons.append("unknown_handoff_status")
        if status == "available" and not produced_outputs:
            reasons.append("missing_produced_outputs")
        if status == "available" and not consumed_inputs:
            reasons.append("missing_consumed_inputs")
        if status == "available" and not evidence_refs:
            reasons.append("missing_handoff_evidence")
        if reasons:
            unstructured.append(
                {
                    "field": "handoff_results",
                    "index": index,
                    "summary": evidence_summary(item),
                    "reason": ",".join(reasons),
                }
            )
            continue
        results.append(
            {
                "handoff_id": handoff_id,
                "producer_node_id": producer_node_id,
                "consumer_node_id": consumer_node_id,
                "status": status,
                "consumed_inputs": consumed_inputs,
                "produced_outputs": produced_outputs,
                "evidence_refs": evidence_refs,
                "_source": source,
            }
        )
    return results


def _handoff_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status in AVAILABLE_HANDOFF_STATUSES:
        return "available"
    if status in FAILED_STATUSES:
        return "failed"
    if status in PENDING_STATUSES:
        return "pending"
    return "unknown"


def _user_redirect(
    value: object, unstructured: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        redirect = {
            key: str(item).strip()
            for key, item in dict(value).items()
            if isinstance(key, str) and str(item).strip()
        }
        if redirect:
            return redirect
    elif isinstance(value, str) and value.strip():
        return {"reason": value.strip()}
    unstructured.append(
        {
            "field": "user_redirect",
            "index": 0,
            "summary": evidence_summary(value),
            "reason": "Expected a non-empty redirect string or object.",
        }
    )
    return None


def normalize_runtime_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize adapter-supplied evidence without treating prose as gate proof."""

    unstructured: list[dict[str, Any]] = []
    verification_results = _structured_results(
        evidence.get("verification_results"), "verification_results", unstructured
    )
    gate_results = _structured_results(
        evidence.get("gate_results"), "gate_results", unstructured
    )
    user_overrides = _evidence_values(
        evidence.get("user_overrides"), "user_overrides", unstructured
    )
    return {
        "schema": COMPOSITION_RUNTIME_EVIDENCE_SCHEMA,
        "files_read": _string_evidence(
            evidence.get("files_read"), "files_read", unstructured
        ),
        "files_changed": _string_evidence(
            evidence.get("files_changed"), "files_changed", unstructured
        ),
        "commands_run": _string_evidence(
            evidence.get("commands_run"), "commands_run", unstructured
        ),
        "verification_results": verification_results,
        "gate_results": gate_results,
        "handoff_results": _handoff_results(
            evidence.get("handoff_results"), unstructured
        ),
        "failures": _evidence_values(
            evidence.get("failures"), "failures", unstructured
        ),
        "browser_evidence": _evidence_values(
            evidence.get("browser_evidence"), "browser_evidence", unstructured
        ),
        "user_overrides": user_overrides,
        "latest_user_message": str(evidence.get("latest_user_message") or "").strip(),
        "requested_phase": str(evidence.get("requested_phase") or "").strip(),
        "user_redirect": _user_redirect(evidence.get("user_redirect"), unstructured),
        "unstructured_evidence": unstructured,
    }


def explicit_phase_override(
    values: list[Any], latest_user_message: str
) -> dict[str, Any] | None:
    """Accept a phase bypass only when it is linked to observed user text."""

    observed = latest_user_message.strip()
    observed_lower = observed.lower()
    if observed and any(term in observed_lower for term in PHASE_OVERRIDE_TERMS):
        return {
            "action": "advance_phase",
            "source": "latest_user_message",
            "message": observed,
        }
    for value in values:
        if not isinstance(value, Mapping):
            continue
        action = str(value.get("action") or value.get("type") or "").lower()
        source = str(value.get("source") or "").lower()
        message = str(value.get("message") or value.get("reason") or "").strip()
        if (
            action in {"advance_phase", "bypass_phase_gate", "phase_gate"}
            and source == "user"
            and message
            and message.lower() in observed_lower
        ):
            return {**dict(value), "message": message}
    return None


def _require_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema") != COMPOSITION_PLAN_SCHEMA:
        raise ValueError(f"Expected {COMPOSITION_PLAN_SCHEMA}.")
    if not json_list(plan.get("ordered_stages")):
        raise ValueError("Composition plan requires at least one ordered stage.")
    policy = str(plan.get("phase_gate_policy") or PHASE_GATE_POLICY_DEFAULT)
    if policy not in PHASE_GATE_POLICIES:
        raise ValueError(f"Unsupported phase_gate_policy: {policy!r}.")


def composition_gate_catalog(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build stable named entry and exit gates from a composition plan."""

    _require_plan(plan)
    plan_id = str(plan.get("composition_plan_id") or "composition")
    roles = {
        str(item.get("node_id") or ""): item
        for item in json_list(plan.get("skill_roles"))
        if isinstance(item, Mapping)
    }
    catalog: list[dict[str, Any]] = []
    for stage in json_list(plan.get("ordered_stages")):
        if not isinstance(stage, Mapping):
            continue
        stage_id = str(stage.get("stage_id") or "")
        for name in string_list(stage.get("entry_conditions")):
            catalog.append(
                {
                    "gate_id": "gate-"
                    + stable_digest([plan_id, "entry", stage_id, name], 16),
                    "name": name,
                    "kind": "entry",
                    "owner_id": stage_id,
                    "owner_stage_id": stage_id,
                }
            )
        for node_id in string_list(stage.get("node_ids")):
            role = roles.get(node_id, {})
            for name in string_list(role.get("exit_gates")):
                catalog.append(
                    {
                        "gate_id": "gate-"
                        + stable_digest([plan_id, "exit", node_id, name], 16),
                        "name": name,
                        "kind": "exit",
                        "owner_id": node_id,
                        "owner_stage_id": stage_id,
                    }
                )
    seen: set[str] = set()
    return [
        item
        for item in catalog
        if not (str(item["gate_id"]) in seen or seen.add(str(item["gate_id"])))
    ]


def transition_gate_ids(
    plan: Mapping[str, Any],
    catalog: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    current_index: int,
    target_index: int,
) -> list[str]:
    if target_index <= current_index:
        return []
    entry_stage_ids = {
        str(stages[index]["stage_id"])
        for index in range(current_index + 1, target_index + 1)
    }
    policy = str(plan.get("phase_gate_policy") or PHASE_GATE_POLICY_DEFAULT)
    if policy == PHASE_GATE_POLICY_ENTRY_HANDOFF:
        return [
            str(item["gate_id"])
            for item in catalog
            if item["kind"] == "entry" and item["owner_stage_id"] in entry_stage_ids
        ]
    exit_stage_ids = {
        str(stages[index]["stage_id"]) for index in range(current_index, target_index)
    }
    return [
        str(item["gate_id"])
        for item in catalog
        if (item["kind"] == "exit" and item["owner_stage_id"] in exit_stage_ids)
        or (item["kind"] == "entry" and item["owner_stage_id"] in entry_stage_ids)
    ]


def _normalized_gate_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _gate_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status in PASSED_STATUSES:
        return "passed"
    if status in FAILED_STATUSES:
        return "failed"
    if status in PENDING_STATUSES:
        return "pending"
    return "unknown"


def _carried_gate_ids(plan: Mapping[str, Any], known_ids: set[str]) -> set[str]:
    state = plan.get("runtime_state")
    if not isinstance(state, Mapping):
        return set()
    return {
        str(item.get("gate_id"))
        for item in json_list(state.get("fulfilled_obligations"))
        if isinstance(item, Mapping) and str(item.get("gate_id")) in known_ids
    }


def evaluate_composition_gates(
    plan: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate explicit structured results against stable named gates."""

    normalized = (
        dict(evidence)
        if evidence.get("schema") == COMPOSITION_RUNTIME_EVIDENCE_SCHEMA
        else normalize_runtime_evidence(evidence)
    )
    catalog = composition_gate_catalog(plan)
    by_id = {str(item["gate_id"]): item for item in catalog}
    by_name: dict[str, list[str]] = {}
    for item in catalog:
        by_name.setdefault(_normalized_gate_name(item["name"]), []).append(
            str(item["gate_id"])
        )
    carried_ids = _carried_gate_ids(plan, set(by_id))
    statuses = {
        gate_id: {
            **gate,
            "status": "passed" if gate_id in carried_ids else "pending",
            "evidence_refs": [],
            "carried": gate_id in carried_ids,
        }
        for gate_id, gate in by_id.items()
    }
    unmatched: list[dict[str, Any]] = []
    results = [
        item
        for field in ("verification_results", "gate_results")
        for item in json_list(normalized.get(field))
        if isinstance(item, Mapping)
    ]
    for result in results:
        gate_id = str(result.get("gate_id") or "").strip()
        gate_name = result.get("gate") or result.get("name")
        reason = ""
        if gate_id and gate_id not in by_id:
            reason = "unknown_gate_id"
        elif not gate_id and gate_name:
            matches = by_name.get(_normalized_gate_name(gate_name), [])
            if len(matches) == 1:
                gate_id = matches[0]
            elif matches:
                reason = "ambiguous_gate_name"
            else:
                reason = "unknown_gate_name"
        elif not gate_id:
            reason = "missing_gate_identifier"
        status = _gate_status(result.get("status") or result.get("outcome"))
        if status == "unknown":
            reason = reason or "unknown_gate_status"
        if reason:
            unmatched.append(
                {
                    "source": str(result.get("_source") or "result"),
                    "summary": evidence_summary(result),
                    "reason": reason,
                }
            )
            continue
        current = str(statuses[gate_id]["status"])
        if status == "failed" or (status == "passed" and current != "failed"):
            statuses[gate_id]["status"] = status
            statuses[gate_id]["carried"] = False
        statuses[gate_id]["evidence_refs"].append(
            str(result.get("_source") or "result")
        )
    evaluated = [statuses[str(item["gate_id"])] for item in catalog]
    return {
        "catalog": catalog,
        "evaluated_gates": evaluated,
        "passed_gate_ids": [
            item["gate_id"] for item in evaluated if item["status"] == "passed"
        ],
        "failed_gate_ids": [
            item["gate_id"] for item in evaluated if item["status"] == "failed"
        ],
        "pending_gate_ids": [
            item["gate_id"] for item in evaluated if item["status"] == "pending"
        ],
        "unmatched_results": unmatched,
        "unstructured_evidence": list(normalized.get("unstructured_evidence") or []),
    }


def _normalized_artifact_names(values: object) -> set[str]:
    return {
        re.sub(r"\s+", " ", item).casefold()
        for item in string_list(values)
        if item.strip()
    }


def composition_handoff_catalog(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose source-cited contracts that a later stage must receive."""

    _require_plan(plan)
    contracts, _invalid = handoff_contract_catalog(plan)
    return contracts


def _carried_handoff_results(
    plan: Mapping[str, Any], contracts_by_id: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    state = plan.get("runtime_state")
    if not isinstance(state, Mapping):
        return []
    carried: list[dict[str, Any]] = []
    for item in json_list(state.get("handoff_results")):
        if not isinstance(item, Mapping):
            continue
        handoff_id = str(item.get("handoff_id") or "")
        contract = contracts_by_id.get(handoff_id)
        if contract is None or str(item.get("status") or "") != "available":
            continue
        if _handoff_result_reason(contract, item):
            continue
        carried.append(dict(item))
    return carried


def _handoff_result_reason(
    contract: Mapping[str, Any], result: Mapping[str, Any]
) -> str:
    if str(result.get("producer_node_id") or "") != str(
        contract.get("producer_node_id") or ""
    ):
        return "wrong_handoff_producer"
    if str(result.get("consumer_node_id") or "") != str(
        contract.get("consumer_node_id") or ""
    ):
        return "wrong_handoff_consumer"
    if str(result.get("status") or "") != "available":
        return ""
    expected_inputs = _normalized_artifact_names(contract.get("required_inputs"))
    supplied_inputs = _normalized_artifact_names(result.get("consumed_inputs"))
    if supplied_inputs != expected_inputs:
        return "incomplete_or_unknown_consumed_input"
    expected_outputs = _normalized_artifact_names(contract.get("produced_outputs"))
    supplied_outputs = _normalized_artifact_names(result.get("produced_outputs"))
    if supplied_outputs != expected_outputs:
        return "incomplete_or_unknown_produced_output"
    if not string_list(result.get("evidence_refs")):
        return "missing_handoff_evidence"
    return ""


def evaluate_composition_handoffs(
    plan: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate artifact-backed results against compiled producer-consumer contracts."""

    normalized = (
        dict(evidence)
        if evidence.get("schema") == COMPOSITION_RUNTIME_EVIDENCE_SCHEMA
        else normalize_runtime_evidence(evidence)
    )
    catalog, invalid_contracts = handoff_contract_catalog(plan)
    by_id = {str(item["handoff_id"]): item for item in catalog}
    carried = {
        str(item.get("handoff_id") or ""): item
        for item in _carried_handoff_results(plan, by_id)
    }
    statuses: dict[str, dict[str, Any]] = {}
    for handoff_id, contract in by_id.items():
        carried_result = carried.get(handoff_id)
        statuses[handoff_id] = {
            **contract,
            "status": "available" if carried_result else "pending",
            "evidence_refs": string_list(
                carried_result.get("evidence_refs") if carried_result else []
            ),
            "evidence_sources": string_list(
                carried_result.get("evidence_sources") if carried_result else []
            ),
            "consumed_inputs": string_list(
                carried_result.get("consumed_inputs") if carried_result else []
            ),
            "carried": bool(carried_result),
        }
    unmatched: list[dict[str, Any]] = []
    for result in json_list(normalized.get("handoff_results")):
        if not isinstance(result, Mapping):
            continue
        handoff_id = str(result.get("handoff_id") or "").strip()
        contract = by_id.get(handoff_id)
        if contract is None:
            unmatched.append(
                {
                    "source": str(result.get("_source") or "handoff_result"),
                    "summary": evidence_summary(result),
                    "reason": "unknown_handoff_id",
                }
            )
            continue
        reason = _handoff_result_reason(contract, result)
        if reason:
            unmatched.append(
                {
                    "source": str(result.get("_source") or "handoff_result"),
                    "summary": evidence_summary(result),
                    "reason": reason,
                }
            )
            continue
        status = str(result.get("status") or "pending")
        current = str(statuses[handoff_id]["status"])
        if status == "failed" or (status == "available" and current != "failed"):
            statuses[handoff_id]["status"] = status
            statuses[handoff_id]["carried"] = False
        statuses[handoff_id]["evidence_refs"] = ordered_unique(
            string_list(statuses[handoff_id].get("evidence_refs"))
            + string_list(result.get("evidence_refs"))
        )
        statuses[handoff_id]["evidence_sources"] = ordered_unique(
            string_list(statuses[handoff_id].get("evidence_sources"))
            + [str(result.get("_source") or "handoff_result")]
        )
        statuses[handoff_id]["consumed_inputs"] = string_list(
            result.get("consumed_inputs")
        )
        statuses[handoff_id]["produced_outputs"] = string_list(
            result.get("produced_outputs")
        )
    evaluated = [statuses[str(item["handoff_id"])] for item in catalog]
    return {
        "catalog": catalog,
        "evaluated_handoffs": evaluated,
        "available_handoff_ids": [
            item["handoff_id"] for item in evaluated if item["status"] == "available"
        ],
        "failed_handoff_ids": [
            item["handoff_id"] for item in evaluated if item["status"] == "failed"
        ],
        "pending_handoff_ids": [
            item["handoff_id"] for item in evaluated if item["status"] == "pending"
        ],
        "invalid_contracts": invalid_contracts,
        "unmatched_results": unmatched,
        "unstructured_evidence": list(normalized.get("unstructured_evidence") or []),
    }
