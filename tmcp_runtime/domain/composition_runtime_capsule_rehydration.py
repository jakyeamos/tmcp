"""Fail-closed replay of capsule-bound source slices."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .composition_preflight import stable_digest
from .composition_runtime_capsules import (
    RuntimeCapsuleError,
    _controls,
    _descriptor_from_slice,
    _preflight_slices,
    _task_identity_projection,
    validate_runtime_capsule,
)
from .harvest_nodes import normalized_source_content


def _rehydration_issue(code: str, descriptor: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "node_id": descriptor["original_node_id"],
        "source_role": descriptor["source_role"],
        "source_digest": descriptor["source_digest"],
        "slice_digest": descriptor["slice_digest"],
    }


def _matches_cited_descriptor(
    candidate: Mapping[str, Any], descriptor: Mapping[str, Any]
) -> bool:
    """Compare immutable source-slice evidence while permitting a node rename."""

    candidate_descriptor = _descriptor_from_slice(
        candidate, field="fresh_candidate_source_slice"
    )
    return all(
        candidate_descriptor[field] == descriptor[field]
        for field in (
            "source_role",
            "source_digest",
            "slice_digest",
            "char_start",
            "char_end",
            "relative_path",
            "behavior_atoms",
        )
    )


def _runtime_source_type(source_role: str) -> str:
    """Use a canonical activation class, never live source-node metadata."""

    return (
        "agent_operating_contract"
        if source_role == "governing_instruction"
        else "skill_definition"
    )


def _runtime_source_projection(
    matched_slices: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project only source behavior bound in the issued capsule.

    Fresh harvest routing metadata is deliberately omitted: it was not present
    in the capsule and therefore cannot become active merely by matching text.
    """

    by_node: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    for descriptor, source_slice in matched_slices:
        node_id = str(descriptor["original_node_id"])
        content = source_slice.get("content")
        if not isinstance(content, str) or not normalized_source_content(content):
            issues.append(_rehydration_issue("runtime_capsule_source_unavailable", descriptor))
            continue
        current = by_node.get(node_id)
        metadata = {
            "source_role": descriptor["source_role"],
            "source_digest": descriptor["source_digest"],
            "relative_path": descriptor["relative_path"],
            "behavior_atoms": list(descriptor["behavior_atoms"]),
        }
        if current is None:
            current = {**metadata, "chunks": []}
            by_node[node_id] = current
        elif any(current[field] != value for field, value in metadata.items()):
            issues.append(
                _rehydration_issue("runtime_capsule_source_activation_changed", descriptor)
            )
            continue
        current["chunks"].append(
            (
                int(descriptor["char_start"]),
                int(descriptor["char_end"]),
                str(descriptor["slice_digest"]),
                content,
            )
        )
    if issues:
        return [], issues
    projected: list[dict[str, Any]] = []
    for node_id, current in sorted(by_node.items()):
        chunks = sorted(current["chunks"])
        excerpt = "\n\n".join(chunk[3] for chunk in chunks)
        projected.append(
            {
                "id": node_id,
                "relative_path": current["relative_path"],
                "path": current["relative_path"],
                "source_type": _runtime_source_type(current["source_role"]),
                "source_role": current["source_role"],
                "content_digest": current["source_digest"],
                "excerpt": excerpt,
                "signal_excerpt": excerpt,
                "behavior_atoms": list(current["behavior_atoms"]),
                "routing_metadata": {},
                "trust": "advisory_untrusted",
            }
        )
    return projected, []


def rehydrate_runtime_capsule(
    composition_plan: Mapping[str, Any],
    composition_preflight: Mapping[str, Any],
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rehydrate only a fresh, exact snapshot for a persisted semantic plan.

    A matching source rename is represented as a temporary alias to the original
    plan node id. Changed, missing, or ambiguous source content is never reused.
    """

    capsule = validate_runtime_capsule(
        composition_plan.get("runtime_capsule"), composition_plan=composition_plan
    )
    fresh_controls = _controls(composition_preflight.get("preparation_controls"))
    if fresh_controls != capsule["preparation_controls"]:
        raise RuntimeCapsuleError("runtime_capsule preparation controls changed.")
    if stable_digest(fresh_controls) != capsule["preparation_controls_digest"]:
        raise RuntimeCapsuleError("runtime_capsule preparation controls changed.")
    objective = composition_preflight.get("objective")
    identity = composition_preflight.get("task_identity")
    if not isinstance(objective, str) or stable_digest(objective) != capsule["objective_digest"]:
        raise RuntimeCapsuleError("runtime_capsule objective changed.")
    if stable_digest(_task_identity_projection(identity)) != capsule["task_identity_digest"]:
        raise RuntimeCapsuleError("runtime_capsule task identity changed.")
    fresh_slices = _preflight_slices(composition_preflight.get("candidate_source_slices"))
    nodes_by_id = {
        str(node.get("id") or ""): node for node in source_nodes if node.get("id")
    }
    aliases: list[dict[str, str]] = []
    alias_pairs: set[tuple[str, str]] = set()
    matched_node_owners: dict[str, str] = {}
    matched_slices: list[tuple[dict[str, Any], dict[str, Any]]] = []
    issues: list[dict[str, Any]] = []
    for descriptor in capsule["cited_source_slices"]:
        matches = [
            item
            for item in fresh_slices
            if _matches_cited_descriptor(item, descriptor)
        ]
        exact = [
            item
            for item in matches
            if str(item.get("source_node_id") or "") == descriptor["original_node_id"]
        ]
        if len(exact) == 1:
            match = exact[0]
        elif len(exact) > 1 or len(matches) > 1:
            issues.append(_rehydration_issue("runtime_capsule_source_ambiguous", descriptor))
            continue
        elif not matches:
            role_matches = [
                item
                for item in fresh_slices
                if str(item.get("source_digest") or "") == descriptor["source_digest"]
            ]
            code = (
                "runtime_capsule_source_role_changed"
                if role_matches
                else "runtime_capsule_source_unavailable"
            )
            issues.append(_rehydration_issue(code, descriptor))
            continue
        else:
            match = matches[0]
        fresh_node_id = str(match.get("source_node_id") or "")
        node = nodes_by_id.get(fresh_node_id)
        if node is None:
            issues.append(_rehydration_issue("runtime_capsule_source_unavailable", descriptor))
            continue
        original_node_id = str(descriptor["original_node_id"])
        previous_owner = matched_node_owners.get(fresh_node_id)
        if previous_owner is not None and previous_owner != original_node_id:
            issues.append(_rehydration_issue("runtime_capsule_source_ambiguous", descriptor))
            continue
        matched_node_owners[fresh_node_id] = original_node_id
        matched_slices.append((descriptor, match))
        alias_pair = (fresh_node_id, original_node_id)
        if fresh_node_id != original_node_id and alias_pair not in alias_pairs:
            aliases.append(
                {"from_node_id": fresh_node_id, "to_node_id": original_node_id}
            )
            alias_pairs.add(alias_pair)
    projected_nodes, projection_issues = _runtime_source_projection(matched_slices)
    issues.extend(projection_issues)
    if issues:
        return {
            "accepted": False,
            "issues": issues,
            "composition_preflight": None,
            "source_nodes": [],
            "aliases": [],
            "compiler_phase": "",
        }
    if str(composition_preflight.get("preflight_id") or "") != capsule["preflight_id"]:
        return {
            "accepted": False,
            "issues": [{"code": "runtime_capsule_preflight_identity_changed"}],
            "composition_preflight": None,
            "source_nodes": [],
            "aliases": [],
            "compiler_phase": "",
        }
    return {
        "accepted": True,
        "issues": [],
        "composition_preflight": deepcopy(dict(composition_preflight)),
        "source_nodes": projected_nodes,
        "aliases": aliases,
        "compiler_phase": capsule["compiler_phase"],
    }
