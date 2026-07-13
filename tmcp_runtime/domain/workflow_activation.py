"""Pure activation policy for canonical workflows from promoted graphs."""

from __future__ import annotations

import re
from typing import Any

from .composition import (
    REPO_BEHAVIOR_PHRASES,
    composition_terms,
    objective_has_phrase,
)
from .workflow_catalog import workflow_catalog_by_id


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_sequence(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    return []


def _text_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", value.lower()))


def _contains_signal_term(text: str, term: str) -> bool:
    needle = term.lower().strip()
    if not needle:
        return False
    pieces = [piece for piece in re.split(r"[\s_/-]+", needle) if piece]
    if len(pieces) > 1:
        pattern = (
            r"(?<![a-z0-9])"
            + r"[\s_/-]+".join(re.escape(piece) for piece in pieces)
            + r"(?![a-z0-9])"
        )
    else:
        pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def _workflow_objective_score(workflow: dict[str, Any], objective: str) -> float:
    objective_lower = objective.lower()
    objective_terms = composition_terms(objective)
    signal_family = str(workflow.get("signal_family") or "")
    if signal_family == "repo_behavior_spec_loop" and not objective_has_phrase(
        objective,
        REPO_BEHAVIOR_PHRASES,
    ):
        return -1.0
    if signal_family == "public_sector_readiness" and not any(
        term in objective_lower
        for term in (
            "public sector",
            "public-sector",
            "government",
            "gov",
            "civic",
            "policy",
            "compliance",
            "uat",
            "wcag",
        )
    ):
        return -1.0
    score = 0.0
    for keyword in _string_sequence(workflow.get("keywords")):
        if _contains_signal_term(objective_lower, keyword):
            score += 2.0 if " " in keyword else 1.0
    if _contains_signal_term(objective_lower, signal_family.replace("_", " ")):
        score += 3.0
    if _contains_signal_term(
        objective_lower,
        str(workflow.get("workflow_id") or "")
        .replace("_workflow", "")
        .replace("_", " "),
    ):
        score += 2.0
    workflow_signal_text = " ".join(
        [
            signal_family.replace("_", " "),
            str(workflow.get("workflow_id") or "").replace("_", " "),
            str(workflow.get("name") or ""),
            " ".join(_string_sequence(workflow.get("keywords"))),
        ]
    )
    shared_terms = objective_terms.intersection(_text_tokens(workflow_signal_text))
    if len(shared_terms) >= 2:
        score += float(len(shared_terms)) * 0.75
    return score


def select_global_workflows(
    graphs: list[dict[str, Any]], objective: str
) -> list[dict[str, Any]]:
    catalog = workflow_catalog_by_id()
    selected: list[tuple[float, str, dict[str, Any], dict[str, Any]]] = []
    for graph in graphs:
        for node in _json_list(graph.get("workflow_nodes")):
            if not isinstance(node, dict):
                continue
            workflow_id = str(node.get("id") or "")
            canonical_workflow = catalog.get(workflow_id)
            if canonical_workflow is None:
                continue
            workflow = dict(canonical_workflow)
            score = _workflow_objective_score(workflow, objective)
            if score <= 0:
                continue
            selected.append((score, workflow_id, workflow, graph))
    selected.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"workflow": workflow, "graph": graph, "score": score}
        for score, _, workflow, graph in selected[:4]
    ]


def _workflow_active_instruction(workflow: dict[str, Any]) -> str:
    signal_family = str(workflow.get("signal_family") or "")
    if signal_family == "repo_behavior_spec_loop":
        return (
            "Run the repo behavior sweep as a canonical spreadsheet/status-machine loop: "
            "stable Feature IDs, source files/functions, expected and observed behavior, "
            "status, evidence, last tested commit, and regression coverage."
        )
    if signal_family == "ui_quality":
        return (
            "Use UI-quality atoms for visual hierarchy, accessibility, responsive behavior, "
            "and browser-backed verification."
        )
    return (
        f"Use the promoted {signal_family or workflow.get('id', 'workflow')} "
        "workflow atoms only where they match this objective."
    )


def build_global_workflow_activation(
    selected_workflows: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    active_instructions: list[str] = []
    active_atoms: list[str] = []
    evidence_citations: list[dict[str, Any]] = []
    for item in selected_workflows:
        workflow = dict(item.get("workflow") or {})
        graph = dict(item.get("graph") or {})
        workflow_id = str(workflow.get("workflow_id") or workflow.get("id") or "")
        active_instructions.append(_workflow_active_instruction(workflow))
        active_atoms.extend(_string_sequence(workflow.get("behavior_atoms")))
        if workflow_id:
            active_atoms.append(workflow_id)
        evidence_citations.append(
            {
                "source": graph.get("_global_cache_path"),
                "promotion_name": graph.get("promotion_name"),
                "workflow_id": workflow_id,
                "trust": graph.get("trust", "advisory_untrusted"),
            }
        )
    return {
        "active_instructions": active_instructions,
        "active_atoms": active_atoms,
        "evidence_citations": evidence_citations,
    }
