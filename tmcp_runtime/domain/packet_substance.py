"""Domain-aware substance checks for standalone TMCP packets."""

from __future__ import annotations

from typing import Any

from .harvest_labels import contains_signal_term, matched_signal_terms


PROCESS_ONLY_MODULES = {
    "context_gathering",
    "evidence_first",
    "output_contract",
    "provenance_policy",
    "test_gate",
    "tool_use_policy",
    "user_approval_gate",
}

PLAYBOOK_ACTION_TERMS = (
    "audit",
    "blocker",
    "check",
    "criterion",
    "criteria",
    "evidence",
    "gate",
    "inspect",
    "must",
    "readiness",
    "require",
    "review",
    "risk",
    "score",
    "validate",
    "verify",
)

DOMAIN_PLAYBOOK_TERMS = (
    "accessibility",
    "audit log",
    "auditability",
    "auth",
    "calculation",
    "compliance",
    "deployment",
    "evidence gate",
    "government",
    "legal",
    "migration",
    "observability",
    "permission",
    "privacy",
    "public sector",
    "readiness",
    "release blocker",
    "retention",
    "rollback",
    "security",
    "tenant",
    "uat",
)

UI_DOMAIN_METADATA_TERMS = (
    "animation",
    "design",
    "frontend",
    "front-end",
    "interaction",
    "motion",
    "ui",
    "ui-design",
    "ux",
    "visual-design",
)

UI_DOMAIN_SIGNAL_TERMS = (
    "accessibility",
    "affordance",
    "animation",
    "button",
    "color palette",
    "component",
    "contrast",
    "design system",
    "empty state",
    "easing",
    "frontend",
    "front-end",
    "hierarchy",
    "interaction",
    "interface",
    "layout",
    "microinteraction",
    "motion",
    "responsive",
    "screen",
    "spacing",
    "state",
    "typography",
    "visual",
)

UI_PLAYBOOK_ACTION_TERMS = (
    "apply",
    "assess",
    "avoid",
    "build",
    "choose",
    "create",
    "define",
    "design",
    "determine",
    "evaluate",
    "group",
    "implement",
    "inspect",
    "prefer",
    "recommend",
    "reduce",
    "select",
    "specify",
    "use",
)

UI_GUIDANCE_LABEL_PREFIX = "ui:"

SUBSTANTIVE_SOURCE_TYPES = {
    "agent_operating_contract",
    "cursor_rule",
    "github_process",
    "project_documentation",
    "skill_definition",
    "workflow_prompt",
}

NON_SUBSTANTIVE_SOURCE_NAME_TERMS = (
    "changelog",
    "release_checklist",
    "verification",
)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _packet_source_signal_text(node: dict[str, Any]) -> str:
    frontmatter = node.get("frontmatter")
    frontmatter_text = " ".join(
        f"{key} {value}"
        for key, value in (frontmatter.items() if isinstance(frontmatter, dict) else ())
    )
    label_text = " ".join(
        " ".join(
            [
                str(label.get("id") or ""),
                str(label.get("label") or ""),
                " ".join(_string_list(label.get("matched_terms"))),
            ]
        )
        for label in _json_list(node.get("guidance_labels"))
        if isinstance(label, dict)
    )
    return " ".join(
        [
            str(node.get("path") or ""),
            str(node.get("relative_path") or ""),
            str(node.get("title") or ""),
            str(node.get("source_type") or ""),
            str(node.get("source_tier") or ""),
            " ".join(_string_list(node.get("keywords"))),
            frontmatter_text,
            label_text,
            str(node.get("excerpt") or ""),
            str(node.get("signal_excerpt") or ""),
        ]
    ).lower()


def _ui_source_evidence(
    node: dict[str, Any], text: str
) -> tuple[list[str], list[str], list[str], bool]:
    frontmatter = node.get("frontmatter")
    metadata_text = " ".join(
        str(value)
        for key, value in (frontmatter.items() if isinstance(frontmatter, dict) else ())
        if str(key).lower() in {"domain", "skill-type", "type", "category"}
    )
    metadata_hits = matched_signal_terms(metadata_text, UI_DOMAIN_METADATA_TERMS)
    signal_hits = matched_signal_terms(text, UI_DOMAIN_SIGNAL_TERMS)
    label_ids = sorted(
        {
            str(label.get("id"))
            for label in _json_list(node.get("guidance_labels"))
            if isinstance(label, dict)
            and str(label.get("id") or "").startswith(UI_GUIDANCE_LABEL_PREFIX)
        }
    )
    domain_hits = sorted(set(metadata_hits + signal_hits))
    action_hits = sorted(
        set(
            matched_signal_terms(text, UI_PLAYBOOK_ACTION_TERMS)
            + matched_signal_terms(text, PLAYBOOK_ACTION_TERMS)
        )
    )
    name_scope = " ".join(
        [
            str(node.get("path") or ""),
            str(node.get("relative_path") or ""),
            str(node.get("title") or ""),
        ]
    ).lower()
    is_non_substantive = any(
        contains_signal_term(name_scope, term)
        for term in NON_SUBSTANTIVE_SOURCE_NAME_TERMS
    )
    has_domain_specific_type = str(
        node.get("source_type") or ""
    ) in SUBSTANTIVE_SOURCE_TYPES or (
        str(node.get("source_type") or "") == "markdown_process_doc"
        and bool(metadata_hits or len(set(signal_hits)) >= 2)
    )
    is_candidate = (
        has_domain_specific_type
        and not is_non_substantive
        and bool(metadata_hits or label_ids or len(set(signal_hits)) >= 2)
        and len(action_hits) >= 2
    )
    return domain_hits, action_hits, label_ids, is_candidate


def packet_substance_check(
    *,
    objective: str,
    task_id: str,
    modules: list[str],
    source_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assess whether standalone packet sources contain domain playbook substance."""

    source_texts = [_packet_source_signal_text(node) for node in source_nodes]
    source_combined = " ".join(source_texts)
    objective_lower = objective.lower()
    requested_anchor_terms = sorted(
        {
            term
            for term in (
                "government",
                "public sector",
                "public-sector",
                "compliance",
                "legal",
                "calculation",
            )
            if term in objective_lower
        }
    )
    matched_domain_terms = sorted(
        set(matched_signal_terms(source_combined, DOMAIN_PLAYBOOK_TERMS))
    )
    matched_action_terms = sorted(
        set(matched_signal_terms(source_combined, PLAYBOOK_ACTION_TERMS))
    )
    matched_ui_domain_terms: set[str] = set()
    matched_ui_guidance_labels: set[str] = set()
    ui_candidate_nodes: list[dict[str, Any]] = []
    substantive_nodes: list[dict[str, Any]] = []
    for node, text in zip(source_nodes, source_texts):
        domain_hits = matched_signal_terms(text, DOMAIN_PLAYBOOK_TERMS)
        action_hits = matched_signal_terms(text, PLAYBOOK_ACTION_TERMS)
        has_required_anchor = not requested_anchor_terms or any(
            contains_signal_term(text, term) for term in requested_anchor_terms
        )
        has_substantive_type = (
            str(node.get("source_type", "")) in SUBSTANTIVE_SOURCE_TYPES
        )
        name_scope = " ".join(
            [
                str(node.get("path", "")),
                str(node.get("relative_path", "")),
                str(node.get("title", "")),
            ]
        ).lower()
        is_non_substantive = any(
            contains_signal_term(name_scope, term)
            for term in NON_SUBSTANTIVE_SOURCE_NAME_TERMS
        )
        if (
            has_substantive_type
            and not is_non_substantive
            and has_required_anchor
            and len(domain_hits) >= 2
            and len(action_hits) >= 2
        ):
            substantive_nodes.append(
                {
                    "id": node.get("id"),
                    "path": node.get("path"),
                    "title": node.get("title"),
                    "matched_domain_terms": sorted(set(domain_hits))[:8],
                    "matched_action_terms": sorted(set(action_hits))[:8],
                }
            )
        ui_domain_hits, ui_action_hits, ui_label_ids, is_ui_candidate = (
            _ui_source_evidence(node, text)
        )
        matched_ui_domain_terms.update(ui_domain_hits)
        matched_ui_guidance_labels.update(ui_label_ids)
        if is_ui_candidate:
            ui_candidate_nodes.append(
                {
                    "id": node.get("id"),
                    "path": node.get("path"),
                    "title": node.get("title"),
                    "matched_domain_terms": ui_domain_hits[:8],
                    "matched_action_terms": ui_action_hits[:8],
                    "matched_guidance_labels": ui_label_ids[:6],
                    "source_domain": "ui_design",
                }
            )
    coherent_ui_corpus = (
        len(ui_candidate_nodes) >= 2
        and len(matched_ui_domain_terms) >= 3
        and (
            len(matched_ui_guidance_labels) >= 2
            or any(
                contains_signal_term(
                    " ".join(
                        str(value)
                        for value in dict(node.get("frontmatter") or {}).values()
                    ),
                    "ui-design",
                )
                for node in source_nodes
                if isinstance(node.get("frontmatter"), dict)
            )
        )
    )
    if coherent_ui_corpus:
        substantive_nodes.extend(ui_candidate_nodes)
        matched_domain_terms = sorted(
            set(matched_domain_terms).union(matched_ui_domain_terms)
        )
        matched_action_terms = sorted(
            set(matched_action_terms).union(
                action
                for node in ui_candidate_nodes
                for action in _string_list(node.get("matched_action_terms"))
            )
        )
    unique_substantive_nodes: list[dict[str, Any]] = []
    seen_substantive_nodes: set[str] = set()
    for node in substantive_nodes:
        node_key = str(node.get("id") or node.get("path") or node.get("title") or "")
        if node_key in seen_substantive_nodes:
            continue
        seen_substantive_nodes.add(node_key)
        unique_substantive_nodes.append(node)
    substantive_nodes = unique_substantive_nodes
    process_modules = [module for module in modules if module in PROCESS_ONLY_MODULES]
    score = 0
    if source_nodes:
        score += 1
    if matched_action_terms:
        score += 1
    if len(matched_domain_terms) >= 2:
        score += 1
    if substantive_nodes:
        score += 1
    if coherent_ui_corpus:
        score += 1
    score = min(score, 4)
    if score >= 3 and substantive_nodes:
        level = "source_backed_playbook"
    elif score >= 2:
        level = "thin_domain_signals"
    else:
        level = "process_only"
    issues: list[str] = []
    if not source_nodes:
        issues.append(
            "No harvested source nodes were available for task-specific playbook content."
        )
    if not substantive_nodes:
        issues.append(
            "Selected TMCP modules are mostly process scaffolding, not a concrete domain playbook."
        )
    if task_id == "audit" and level != "source_backed_playbook":
        issues.append(
            "Audit rubric substance should be derived from target repo evidence and cited artifacts."
        )
    fallback_policy = (
        "Use TMCP for routing, evidence discipline, and output contract; derive rubric substance from target repo docs, code, tests, risk registers, and readiness gates."
        if level != "source_backed_playbook"
        else "Use harvested source nodes as substantive rubric guidance, then verify every finding against target evidence."
    )
    return {
        "schema": "tmcp-packet-substance-v0.1",
        "level": level,
        "score": score,
        "has_domain_playbook": level == "source_backed_playbook",
        "source_node_count": len(source_nodes),
        "substantive_source_count": len(substantive_nodes),
        "process_only_modules": process_modules,
        "matched_domain_terms": matched_domain_terms[:12],
        "matched_action_terms": matched_action_terms[:12],
        "matched_ui_domain_terms": sorted(matched_ui_domain_terms)[:16],
        "matched_ui_guidance_labels": sorted(matched_ui_guidance_labels)[:12],
        "ui_domain_source_count": len(ui_candidate_nodes),
        "inferred_domain": "ui_design" if coherent_ui_corpus else "general",
        "requested_anchor_terms": requested_anchor_terms,
        "substantive_source_nodes": substantive_nodes[:5],
        "issues": issues,
        "fallback_policy": fallback_policy,
        "recommended_next_step": (
            "Harvest the completed review into a reusable TMCP skill after the audit."
            if level != "source_backed_playbook"
            else "Run the review with evidence-backed scoring and preserve source citations."
        ),
    }
