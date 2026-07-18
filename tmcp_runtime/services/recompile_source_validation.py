"""Legacy source-provenance checks retained for unbound composition plans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tmcp_runtime.domain.harvest_nodes import json_list, node_source_role, ordered_unique, string_list


def _role_source_citation(
    role: Mapping[str, Any], packet: Mapping[str, Any]
) -> dict[str, Any]:
    role_citations = sorted(string_list(role.get("citations")))
    if not role_citations:
        return {}
    for item in json_list(packet.get("evidence_citations")):
        if not isinstance(item, Mapping):
            continue
        if sorted(string_list(item.get("relationship_citations"))) == role_citations:
            return dict(item)
    return {}


def bind_runtime_plan_sources(
    plan: Mapping[str, Any],
    source_nodes: list[dict[str, Any]],
    packet: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bind legacy plans to matching source content, including a safe rename alias."""

    by_id = {str(node.get("id") or ""): node for node in source_nodes}
    by_path = {
        str(node.get("relative_path") or node.get("path") or ""): node
        for node in source_nodes
    }
    bound_nodes = list(source_nodes)
    issues: list[dict[str, Any]] = []
    for role in json_list(plan.get("skill_roles")):
        if not isinstance(role, Mapping):
            continue
        node_id = str(role.get("node_id") or "")
        citation = _role_source_citation(role, packet)
        expected_digest = str(citation.get("content_digest") or "")
        expected_path = str(citation.get("source") or citation.get("path") or "")
        expected_role = str(citation.get("source_role") or role.get("source_role") or "")
        exact = by_id.get(node_id)
        if exact is not None:
            actual_digest = str(exact.get("content_digest") or "")
            actual_role = node_source_role(exact)
            if expected_digest and actual_digest != expected_digest:
                issues.append(
                    {
                        "code": "composition_source_content_changed",
                        "node_id": node_id,
                        "source": expected_path,
                        "expected_content_digest": expected_digest,
                        "actual_content_digest": actual_digest,
                    }
                )
            if expected_role and actual_role != expected_role:
                issues.append(
                    {
                        "code": "composition_source_role_changed",
                        "node_id": node_id,
                        "source": expected_path,
                        "expected_source_role": expected_role,
                        "actual_source_role": actual_role,
                    }
                )
            continue
        digest_matches = [
            node
            for node in source_nodes
            if expected_digest
            and str(node.get("content_digest") or "") == expected_digest
            and (not expected_role or node_source_role(node) == expected_role)
        ]
        path_match = by_path.get(expected_path)
        if path_match is not None and path_match in digest_matches:
            digest_matches = [path_match]
        if len(digest_matches) == 1:
            alias = dict(digest_matches[0])
            alias["id"] = node_id
            bound_nodes.append(alias)
            continue
        if len(digest_matches) > 1:
            issues.append(
                {
                    "code": "composition_source_rebind_ambiguous",
                    "node_id": node_id,
                    "source": expected_path,
                    "expected_content_digest": expected_digest,
                }
            )
            continue
        if path_match is not None:
            issues.append(
                {
                    "code": "composition_source_content_changed",
                    "node_id": node_id,
                    "source": expected_path,
                    "expected_content_digest": expected_digest,
                    "actual_content_digest": path_match.get("content_digest"),
                }
            )
            continue
        issues.append(
            {
                "code": "composition_source_unavailable",
                "node_id": node_id,
                "source": expected_path,
                "expected_content_digest": expected_digest,
            }
        )
    return bound_nodes, issues


def reject_stale_runtime_plan(
    packet: dict[str, Any],
    *,
    plan: dict[str, Any],
    issues: list[dict[str, Any]],
    metadata_packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an inert packet when a legacy plan's source provenance changed."""

    rejected = dict(packet)
    for key in ("composition_diagnostics", "semantic_proposal_validation"):
        value = metadata_packet.get(key)
        if isinstance(value, Mapping):
            rejected[key] = dict(value)
    diagnostics = rejected.get("composition_diagnostics")
    diagnostic_map = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
    diagnostic_map["runtime_source_validation"] = {
        "accepted": False,
        "errors": issues,
        "required_action": "Prepare and submit a fresh semantic proposal.",
    }
    rejected["ok"] = False
    rejected["composition_plan"] = plan
    rejected["composition_plan_status"] = "stale_source_provenance"
    rejected["composition_diagnostics"] = diagnostic_map
    rejected["deferred_atoms"] = ordered_unique(
        string_list(rejected.get("active_atoms"))
        + string_list(rejected.get("deferred_atoms"))
    )
    rejected["active_atoms"] = []
    rejected["active_instructions"] = []
    rejected["tool_script_prompts"] = []
    rejected["stop_conditions"] = []
    rejected["verification_gates"] = [
        "Prepare a fresh semantic proposal from the current source content."
    ]
    receipt = rejected.get("receipt_template")
    if isinstance(receipt, dict):
        rejected["receipt_template"] = {**receipt, "activated_atoms": []}
    shortcut = rejected.get("shortcut_candidate")
    shortcut_map = dict(shortcut) if isinstance(shortcut, Mapping) else {}
    shortcut_map.update(
        {
            "status": "ineligible",
            "matched": False,
            "reason": "Composition source provenance changed; fresh preparation is required.",
        }
    )
    rejected["shortcut_candidate"] = shortcut_map
    return rejected
