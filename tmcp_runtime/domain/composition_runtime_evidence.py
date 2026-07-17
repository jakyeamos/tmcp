"""Strict normalization and gate evaluation for composition runtime evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .composition_preflight import (
    COMPOSITION_PLAN_SCHEMA,
    json_list,
    ordered_unique,
    stable_digest,
    string_list,
)


COMPOSITION_RUNTIME_EVIDENCE_SCHEMA = "tmcp-composition-runtime-evidence-v0.1"
PASSED_STATUSES = frozenset({"pass", "passed", "satisfied", "success", "verified"})
FAILED_STATUSES = frozenset({"blocked", "error", "fail", "failed"})
PENDING_STATUSES = frozenset({"pending", "running", "skipped", "unknown"})


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
        "failures": _evidence_values(
            evidence.get("failures"), "failures", unstructured
        ),
        "browser_evidence": _evidence_values(
            evidence.get("browser_evidence"), "browser_evidence", unstructured
        ),
        "user_overrides": user_overrides,
        "latest_user_message": str(evidence.get("latest_user_message") or "").strip(),
        "requested_phase": str(evidence.get("requested_phase") or "").strip(),
        "unstructured_evidence": unstructured,
    }


def _require_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema") != COMPOSITION_PLAN_SCHEMA:
        raise ValueError(f"Expected {COMPOSITION_PLAN_SCHEMA}.")
    if not json_list(plan.get("ordered_stages")):
        raise ValueError("Composition plan requires at least one ordered stage.")


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
