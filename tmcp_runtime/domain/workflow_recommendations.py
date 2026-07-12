"""Pure workflow-recommendation scoring, templates, and candidate policy."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from typing import Any

from .review_profiles import profile_dimensions
from .workflow_catalog import workflow_stability


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _string_sequence(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    return []


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


def _matched_signal_terms(text: str, terms: tuple[str, ...] | list[str]) -> list[str]:
    return [term for term in terms if _contains_signal_term(text, str(term))]


def source_scope_for(path: str) -> str:
    lower = path.lower()
    if any(
        marker in lower for marker in ("/.agents/", "/.codex/", "/.claude/", "/aios/")
    ):
        return "user_or_agent_skill"
    return "repo_or_project_local"


def score_workflow_signal(
    workflow: dict[str, Any],
    source_nodes: list[dict[str, Any]],
    *,
    node_signal_text: Callable[[dict[str, Any]], str],
    signal_guidance_label_ids: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    keywords = tuple(str(item).lower() for item in workflow.get("keywords", ()))
    expected_atoms = set(_string_sequence(workflow.get("behavior_atoms")))
    expected_label_ids = set(
        signal_guidance_label_ids.get(
            str(workflow.get("signal_family") or ""), ()
        )
    )
    score = 0.0
    evidence_candidates: list[dict[str, Any]] = []
    for node in source_nodes:
        text = node_signal_text(node)
        matched_terms = _matched_signal_terms(text, list(keywords))
        matched_atoms = sorted(
            expected_atoms.intersection(_string_list(node.get("behavior_atoms")))
        )
        if not matched_terms:
            continue
        guidance_labels = _json_list(node.get("guidance_labels"))
        node_score = float(len(matched_terms)) + float(len(matched_atoms))
        matching_label_count = sum(
            1
            for label in guidance_labels
            if str(label.get("id") or "") in expected_label_ids
        )
        node_score += min(2.0, float(matching_label_count))
        if not node_score:
            continue
        score += node_score
        evidence_candidates.append(
            {
                "_score": node_score,
                "source_path": node.get("path"),
                "relative_path": node.get("relative_path"),
                "title": node.get("title"),
                "source_type": node.get("source_type"),
                "source_scope": source_scope_for(str(node.get("path") or "")),
                "matched_terms": matched_terms[:8],
                "matched_behavior_atoms": matched_atoms,
                "guidance_labels": guidance_labels,
                "excerpt": str(node.get("excerpt") or "")[:360],
            }
        )
    evidence: list[dict[str, Any]] = []
    for item in sorted(
        evidence_candidates,
        key=lambda value: (
            -float(value.get("_score") or 0.0),
            str(value.get("relative_path") or ""),
        ),
    )[:6]:
        item.pop("_score", None)
        evidence.append(item)
    confidence = round(min(0.99, score / (score + 6.0)), 2) if score else 0.0
    return {
        "signal_family": workflow["signal_family"],
        "workflow_id": workflow["workflow_id"],
        "name": workflow["name"],
        "stability": workflow_stability(workflow),
        "score": round(score, 2),
        "confidence": confidence,
        "evidence": evidence,
    }


def recommendation_reason(score: dict[str, Any]) -> str:
    evidence = _json_list(score.get("evidence"))
    if not evidence:
        return "No meaningful harvested evidence matched this workflow's signal family."
    terms = sorted(
        {
            term
            for item in evidence
            if isinstance(item, dict)
            for term in _string_list(item.get("matched_terms"))
        }
    )
    if terms:
        return f"Harvest matched {', '.join(terms[:8])} signals across {len(evidence)} source nodes."
    return f"Harvest matched behavior atoms across {len(evidence)} source nodes."


def workflow_rubric_seed(workflow: dict[str, Any], objective: str) -> dict[str, Any]:
    profile = str(workflow.get("profile") or "general_review")
    dimensions = profile_dimensions(profile)
    return {
        "workflow_id": workflow["workflow_id"],
        "stability": workflow_stability(workflow),
        "profile": profile,
        "objective": objective,
        "starter_prompt": workflow["starter_prompt"],
        "dimension_seeds": [
            {
                "id": dimension["id"],
                "name": dimension["name"],
                "weight": dimension["weight"],
                "evidence_expectations": dimension["expectations"],
            }
            for dimension in dimensions
        ],
    }


def workflow_template(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": workflow["workflow_id"],
        "kind": "default_template",
        "name": workflow["name"],
        "stability": workflow_stability(workflow),
        "signal_family": workflow["signal_family"],
        "profile": workflow.get("profile", "general_review"),
        "starter_prompt": workflow["starter_prompt"],
        "expected_artifacts": list(workflow["expected_artifacts"]),
    }


def required_evidence_for_workflow(workflow: dict[str, Any]) -> list[str]:
    signal_family = str(workflow.get("signal_family") or "")
    evidence_by_family = {
        "ui_quality": [
            "Rendered UI evidence such as screenshots or browser inspection.",
            "Relevant component/source paths.",
            "Responsive and state coverage expectations.",
        ],
        "security_privacy": [
            "Security/privacy docs, auth/data-flow boundaries, and redacted secrets handling.",
            "Permission, token, and sensitive-data evidence.",
            "Known compliance or policy constraints.",
        ],
        "public_sector_readiness": [
            "Governance, policy, compliance, and decision-owner evidence.",
            "Security/privacy, tenant-boundary, auditability, and legal calculation evidence.",
            "UAT, accessibility, release-blocker, and acceptance-gate evidence.",
        ],
        "testing_quality": [
            "Public contracts and high-risk behavior paths.",
            "Current tests, CI checks, and coverage or quality-gate output.",
            "Recent regressions or known untested edge cases.",
        ],
        "release_readiness": [
            "Release checklist, CI/build/package output, and deployment constraints.",
            "Known blockers, warnings, changelog/version evidence, and rollback expectations.",
            "Final verification commands.",
        ],
        "developer_experience": [
            "README, setup docs, contribution flow, and command discovery evidence.",
            "Fresh-clone or onboarding failure points.",
            "Maintainer handoff expectations.",
        ],
        "incident_postmortem": [
            "Incident timeline, observed impact, logs, commits, and rollback notes.",
            "Reproduction or verification evidence.",
            "Follow-up constraints and owner expectations.",
        ],
        "architecture_decision": [
            "Current architecture, decision constraints, and alternatives.",
            "Migration cost and compatibility evidence.",
            "Verification expectations for the chosen direction.",
        ],
        "migration_readiness": [
            "Current and target states, affected surfaces, and compatibility constraints.",
            "Rollback/cutover and data/backfill requirements.",
            "Sequenced validation gates.",
        ],
        "agent_handoff": [
            "Current state, touched files, decisions, and commands already run.",
            "Blockers, open questions, and next commands.",
            "Verification status and remaining risk.",
        ],
        "pr_risk_review": [
            "Diff summary, touched contracts, CI status, and test/doc changes.",
            "Regression and release constraints.",
            "Merge blockers and required follow-up.",
        ],
        "repo_behavior_spec_loop": [
            "Current repo feature surface, route/API/action inventory, and test infrastructure evidence.",
            "Canonical spreadsheet path, required columns, stable Feature IDs, status machine, and source file/function citations.",
            "Running-app or e2e verification actions, observed behavior, defect metadata, regression coverage, iteration, and last tested commit.",
        ],
        "performance": [
            "Profiling data, hot paths, runtime metrics, and load expectations.",
            "Measurement gaps and cache/query/bundle evidence.",
            "Acceptance thresholds.",
        ],
        "data_correctness": [
            "Schemas, migrations, invariants, pipelines, and reconciliation checks.",
            "Backfill/idempotency and data-loss risk evidence.",
            "Verification queries or fixtures.",
        ],
    }
    return evidence_by_family.get(
        signal_family,
        [
            "Relevant source evidence from the harvested skill corpus.",
            "Current project state and known constraints.",
            "Verification commands or acceptance gates.",
        ],
    )


def routing_trigger_for_workflow(workflow: dict[str, Any]) -> str:
    signal_family = str(workflow.get("signal_family") or "workflow")
    name = str(workflow.get("name") or "TMCP workflow").replace(" Workflow", "")
    return (
        f"Prefer TMCP {name.lower()} when harvested `{signal_family}` signals are strong "
        "and the user asks for a packet, rubric, audit, or remediation plan."
    )


def workflow_instance(
    *,
    workflow: dict[str, Any],
    objective: str,
    harvest: dict[str, Any],
    score: dict[str, Any],
) -> dict[str, Any]:
    source_paths = _string_list(harvest.get("source_paths"))
    identity = hashlib.sha256(
        "|".join([str(workflow["workflow_id"]), objective, *source_paths]).encode()
    ).hexdigest()[:10]
    evidence = [
        {
            "relative_path": item.get("relative_path"),
            "source_type": item.get("source_type"),
            "matched_terms": item.get("matched_terms", []),
            "matched_behavior_atoms": item.get("matched_behavior_atoms", []),
            "guidance_labels": item.get("guidance_labels", []),
        }
        for item in _json_list(score.get("evidence"))[:4]
        if isinstance(item, dict)
    ]
    return {
        "id": f"{workflow['workflow_id']}.{identity}",
        "status": "candidate",
        "stability": workflow_stability(workflow),
        "template_id": workflow["workflow_id"],
        "adapted_from": {
            "source_paths": source_paths,
            "source_count": harvest.get("source_count", 0),
            "matched_source_count": harvest.get("matched_source_count", 0),
            "evidence": evidence,
        },
        "generated_rubric": workflow_rubric_seed(workflow, objective),
        "required_evidence": required_evidence_for_workflow(workflow),
        "routing_trigger": routing_trigger_for_workflow(workflow),
        "approval_required": True,
        "next_step": "Ask the user to approve this workflow before running expert_rubric_review_plan.",
    }
