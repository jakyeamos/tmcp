"""Pure packet-inclusion policy for skill evaluation."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


PacketComposer = Callable[[dict[str, Any], str | None], dict[str, Any]]


def packet_inclusion_expectations(decomposition: dict[str, Any]) -> dict[str, Any]:
    """Project a decomposition into the packet contract used by scoring."""

    routing = decomposition.get("routing_slices") or {}
    return {
        "skill_path": decomposition.get("skill_path"),
        "required_reads": list(routing.get("required_reads") or []),
        "verification_gates": list(routing.get("verification_gates") or []),
        "stop_conditions": list(routing.get("stop_conditions") or []),
        "output_contract": list(routing.get("output_contract") or []),
        "behavior_atoms": list(decomposition.get("behavior_atoms") or []),
    }


def variant_inclusion_expectations(
    expectations: dict[str, Any],
    variant_id: str,
) -> dict[str, Any]:
    """Apply baseline/negative-control selection policy to a packet contract."""

    if variant_id in {"baseline", "negative_control"}:
        return {
            "skill_should_be_selected": False,
            "required_reads": [],
            "verification_gates": [],
            "stop_conditions": [],
            "output_contract": [],
            "behavior_atoms": [],
        }
    return {
        "skill_should_be_selected": True,
        "required_reads": list(expectations.get("required_reads") or []),
        "verification_gates": list(expectations.get("verification_gates") or []),
        "stop_conditions": list(expectations.get("stop_conditions") or []),
        "output_contract": list(expectations.get("output_contract") or []),
        "behavior_atoms": list(expectations.get("behavior_atoms") or []),
    }


def task_matrix_row(
    plan: dict[str, Any],
    task_id: str = "",
    variant_id: str = "",
    skill_path: str | None = None,
    *,
    matrix_row_id: str | None = None,
    ablation_section: str | None = None,
) -> dict[str, Any] | None:
    """Find one task/variant row without reading any referenced path."""

    matches: list[dict[str, Any]] = []
    for row in plan.get("task_matrix", []):
        if matrix_row_id and str(row.get("matrix_row_id") or "") != matrix_row_id:
            continue
        if matrix_row_id:
            matches.append(row)
            continue
        if str(row.get("task_id")) != task_id:
            continue
        if str(row.get("variant_id")) != variant_id:
            continue
        if skill_path and str(row.get("skill_path")) != skill_path:
            continue
        if ablation_section is not None and str(
            row.get("ablation_section") or ""
        ) != str(ablation_section):
            continue
        matches.append(row)
    if len(matches) > 1:
        raise ValueError(
            "Evaluation trace matches multiple task-matrix rows; supply matrix_row_id."
        )
    return matches[0] if matches else None


def expectations_for_plan_row(
    plan: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    """Resolve one variant's expected packet content from a plan."""

    row_contract = row.get("expected_packet_contract")
    if isinstance(row_contract, dict):
        return variant_inclusion_expectations(
            dict(row_contract), str(row.get("variant_id") or "")
        )

    contracts = plan.get("packet_inclusion_contracts") or []
    skill_path = str(row.get("skill_path") or "")
    contract = next(
        (item for item in contracts if str(item.get("skill_path")) == skill_path),
        None,
    )
    base = dict(contract.get("expected") or {}) if contract else {}
    return variant_inclusion_expectations(base, str(row.get("variant_id") or ""))


def compose_packet_for_eval_row(
    row: dict[str, Any],
    compose_evaluation_row: PacketComposer | None,
    *,
    project_path: str | None = None,
) -> dict[str, Any]:
    """Invoke the adapter-injected, data-only compose callback."""

    if compose_evaluation_row is None:
        raise RuntimeError("Evaluation compose service is unavailable.")
    return compose_evaluation_row(row, project_path)


def _path_name(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1]


def _any_packet_match(needle: str, packet_values: list[str]) -> bool:
    needle_lower = needle.lower().strip()
    if not needle_lower:
        return True
    candidates = {needle_lower, _path_name(needle_lower)}
    keywords = [token for token in re.split(r"\W+", needle_lower) if len(token) > 3]
    for value in packet_values:
        value_lower = str(value).lower()
        if any(candidate and candidate in value_lower for candidate in candidates):
            return True
        if keywords and sum(1 for keyword in keywords if keyword in value_lower) >= min(
            2, len(keywords)
        ):
            return True
    return False


def _includes_expected_items(
    expected_items: list[str],
    packet_values: list[str],
    *,
    skill_selected: bool,
    should_select: bool,
) -> bool:
    if not expected_items:
        return True
    if should_select and not skill_selected:
        return False
    return all(_any_packet_match(item, packet_values) for item in expected_items)


def diff_packet_inclusion(
    expectations: dict[str, Any],
    composed: dict[str, Any],
    *,
    skill_path: str,
    variant_id: str,
) -> dict[str, Any]:
    """Compare a composed packet with the expected variant contract."""

    skill_path_name = _path_name(skill_path)
    citations = [
        item
        for item in (composed.get("evidence_citations") or [])
        if isinstance(item, dict)
    ]
    skill_selected = any(
        skill_path in str(item.get("path") or "")
        or skill_path_name in str(item.get("source") or "")
        for item in citations
    )
    ignored_sources = [
        str(item.get("source") or "")
        for item in (composed.get("ignored_sources") or [])
        if isinstance(item, dict)
    ]
    variant_expectations = variant_inclusion_expectations(expectations, variant_id)
    should_select = bool(variant_expectations.get("skill_should_be_selected"))
    packet_reads = [str(item) for item in (composed.get("required_reads") or [])]
    packet_gates = [str(item) for item in (composed.get("verification_gates") or [])]
    packet_stops = [str(item) for item in (composed.get("stop_conditions") or [])]
    packet_outputs = [str(item) for item in (composed.get("output_contract") or [])]
    packet_atoms = [str(item) for item in (composed.get("active_atoms") or [])]
    included_required_reads = _includes_expected_items(
        list(variant_expectations.get("required_reads") or []),
        packet_reads,
        skill_selected=skill_selected,
        should_select=should_select,
    )
    included_stop_conditions = _includes_expected_items(
        list(variant_expectations.get("stop_conditions") or []),
        packet_stops,
        skill_selected=skill_selected,
        should_select=should_select,
    )
    included_verification_gates = _includes_expected_items(
        list(variant_expectations.get("verification_gates") or []),
        packet_gates,
        skill_selected=skill_selected,
        should_select=should_select,
    )
    included_output_contract = _includes_expected_items(
        list(variant_expectations.get("output_contract") or []),
        packet_outputs,
        skill_selected=skill_selected,
        should_select=should_select,
    )
    expected_atoms = list(variant_expectations.get("behavior_atoms") or [])
    included_behavior_atoms = True
    if expected_atoms and should_select:
        if not skill_selected:
            included_behavior_atoms = False
        else:
            included_behavior_atoms = all(
                atom in packet_atoms for atom in expected_atoms
            )
    skill_selection_correct = skill_selected == should_select
    checks = [
        skill_selection_correct,
        included_required_reads,
        included_stop_conditions,
        included_verification_gates,
        included_output_contract,
        included_behavior_atoms,
    ]
    score = round(sum(1 for item in checks if item) / len(checks), 2)
    return {
        "skill_path": skill_path,
        "variant_id": variant_id,
        "score": score,
        "confidence": "high",
        "signals": {
            "skill_selected_in_packet": skill_selected,
            "skill_should_be_selected": should_select,
            "included_required_reads": included_required_reads,
            "included_stop_conditions": included_stop_conditions,
            "included_verification_gates": included_verification_gates,
            "included_output_contract": included_output_contract,
            "included_behavior_atoms": included_behavior_atoms,
            "ignored_sources": ignored_sources[:8],
            "conflicts": list(composed.get("conflicts") or []),
        },
        "composed_packet_id": composed.get("packet_id"),
        "expected": variant_expectations,
        "actual": {
            "required_reads": packet_reads,
            "verification_gates": packet_gates,
            "stop_conditions": packet_stops,
            "output_contract": packet_outputs,
            "active_atoms": packet_atoms,
            "selected_sources": [
                str(item.get("source") or item.get("path") or "") for item in citations
            ],
        },
    }
