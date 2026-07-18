"""Curated workflow catalog, stability, and candidate-selection policy."""

from __future__ import annotations

from typing import Any


STABLE_WORKFLOW_IDS = {
    "release_readiness_workflow",
    "developer_experience_workflow",
}

EXPERIMENTAL_WORKFLOW_IDS = {
    "expert_ui_rubric_workflow",
    "security_privacy_review_workflow",
    "public_sector_readiness_workflow",
    "test_strategy_and_regression_workflow",
    "maintainability_workflow",
    "performance_review_workflow",
    "data_integrity_workflow",
    "incident_postmortem_workflow",
    "architecture_decision_workflow",
    "migration_readiness_workflow",
    "agent_handoff_workflow",
    "pr_risk_review_workflow",
    "repo_behavior_spec_loop_workflow",
}

WORKFLOW_SIGNAL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "signal_family": "ui_quality",
        "workflow_id": "expert_ui_rubric_workflow",
        "name": "Expert UI Rubric Workflow",
        "keywords": (
            "ui",
            "ux",
            "frontend",
            "visual",
            "polish",
            "visual design",
            "ui design",
            "interface design",
            "design-system",
            "responsive",
            "screen",
            "screenshot",
            "layout",
            "ui component",
            "frontend component",
            "component state",
            "visible state",
            "interaction state",
            "interaction",
            "button",
            "buttons",
            "controls",
            "input",
            "toolbar",
            "tooltip",
        ),
        "behavior_atoms": (
            "evidence-backed-claims",
            "concrete-citations",
            "artifact-contract",
        ),
        "profile": "visual_polish",
        "starter_prompt": "Use the TMCP expert UI rubric on this project.",
        "expected_artifacts": (
            "expertise packet",
            "scored visual rubric",
            "evidence-backed UI audit",
            "ordered remediation plan",
        ),
    },
    {
        "signal_family": "security_privacy",
        "workflow_id": "security_privacy_review_workflow",
        "name": "Security And Privacy Review Workflow",
        "keywords": (
            "security",
            "privacy",
            "redact",
            "redaction",
            "secret",
            "permission",
            "auth",
            "token",
            "credential",
            "data flow",
            "audit log",
            "retention",
        ),
        "behavior_atoms": (
            "bounded-tool-side-effects",
            "approval-before-implementation",
        ),
        "profile": "security_privacy",
        "starter_prompt": "Use TMCP to audit security and privacy risks in this project.",
        "expected_artifacts": (
            "expertise packet",
            "scored security/privacy rubric",
            "evidence-backed risk audit",
            "ordered remediation plan",
        ),
    },
    {
        "signal_family": "public_sector_readiness",
        "workflow_id": "public_sector_readiness_workflow",
        "name": "Public Sector Readiness Workflow",
        "keywords": (
            "government",
            "public sector",
            "public-sector",
            "compliance",
            "governance",
            "policy",
            "uat",
            "user acceptance",
            "accessibility",
            "section 508",
            "wcag",
            "auditability",
            "audit log",
            "legal",
            "calculation",
            "tenant",
            "risk register",
            "release blocker",
            "acceptance criteria",
            "readiness",
        ),
        "behavior_atoms": (
            "source-traceability",
            "explicit-evidence-gaps",
            "quality-gate-disclosure",
        ),
        "profile": "public_sector_readiness",
        "starter_prompt": "Use TMCP to review public-sector readiness for this project.",
        "expected_artifacts": (
            "expertise packet",
            "public-sector readiness rubric",
            "evidence-backed governance, compliance, UAT, and accessibility audit",
            "ordered readiness remediation plan",
        ),
    },
    {
        "signal_family": "testing_quality",
        "workflow_id": "test_strategy_and_regression_workflow",
        "name": "Test Strategy And Regression Workflow",
        "keywords": (
            "test",
            "testing",
            "tdd",
            "regression",
            "coverage",
            "quality gate",
            "vitest",
            "jest",
            "pytest",
            "unit test",
            "integration",
            "e2e",
        ),
        "behavior_atoms": ("behavior-verification", "quality-gate-disclosure"),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to review test strategy and regression risk in this project.",
        "expected_artifacts": (
            "expertise packet",
            "test strategy rubric",
            "coverage and regression audit",
            "verification-focused remediation plan",
        ),
    },
    {
        "signal_family": "release_readiness",
        "workflow_id": "release_readiness_workflow",
        "name": "Release Readiness Workflow",
        "keywords": (
            "release",
            "ship",
            "deploy",
            "deployment",
            "ci",
            "cd",
            "checklist",
            "package",
            "version",
            "changelog",
            "tag",
            "verification",
        ),
        "behavior_atoms": (
            "quality-gate-disclosure",
            "ordered-next-actions",
            "artifact-contract",
        ),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to plan release readiness for this project.",
        "expected_artifacts": (
            "expertise packet",
            "release readiness rubric",
            "evidence gap audit",
            "ordered release remediation plan",
        ),
    },
    {
        "signal_family": "developer_experience",
        "workflow_id": "developer_experience_workflow",
        "name": "Developer Experience Workflow",
        "keywords": (
            "developer",
            "dx",
            "onboarding",
            "setup",
            "install",
            "command",
            "cli",
            "readme",
            "docs",
            "troubleshooting",
        ),
        "behavior_atoms": (
            "local-context-first",
            "source-traceability",
            "artifact-contract",
        ),
        "profile": "developer_experience",
        "starter_prompt": "Use TMCP to review developer onboarding commands and CLI docs.",
        "expected_artifacts": (
            "expertise packet",
            "developer-experience rubric",
            "command and docs audit",
            "onboarding remediation plan",
        ),
    },
    {
        "signal_family": "maintainability",
        "workflow_id": "maintainability_workflow",
        "name": "Maintainability Workflow",
        "keywords": (
            "maintainability",
            "refactor",
            "architecture",
            "modular",
            "boundary",
            "dead code",
            "duplication",
            "complexity",
            "abstraction",
            "cleanup",
        ),
        "behavior_atoms": (
            "smallest-effective-change",
            "avoid-speculative-abstractions",
        ),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to review maintainability, boundaries, and dead-code risk.",
        "expected_artifacts": (
            "expertise packet",
            "maintainability rubric",
            "codebase structure audit",
            "scoped refactor plan",
        ),
    },
    {
        "signal_family": "performance",
        "workflow_id": "performance_review_workflow",
        "name": "Performance Review Workflow",
        "keywords": (
            "performance",
            "latency",
            "profiling",
            "profile",
            "bundle size",
            "runtime",
            "load test",
            "speed",
            "memory",
            "optimize",
        ),
        "behavior_atoms": ("evidence-backed-claims", "behavior-verification"),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to review performance risks and verification signals.",
        "expected_artifacts": (
            "expertise packet",
            "performance rubric",
            "evidence-backed performance audit",
            "measurement-first remediation plan",
        ),
    },
    {
        "signal_family": "data_correctness",
        "workflow_id": "data_integrity_workflow",
        "name": "Data Integrity Workflow",
        "keywords": (
            "data",
            "schema",
            "migration",
            "validation",
            "invariant",
            "pipeline",
            "etl",
            "backfill",
            "database",
            "integrity",
        ),
        "behavior_atoms": (
            "source-traceability",
            "behavior-verification",
            "explicit-evidence-gaps",
        ),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to review data integrity, migrations, and pipeline correctness.",
        "expected_artifacts": (
            "expertise packet",
            "data integrity rubric",
            "schema and pipeline audit",
            "verification-first remediation plan",
        ),
    },
    {
        "signal_family": "incident_postmortem",
        "workflow_id": "incident_postmortem_workflow",
        "name": "Incident Postmortem Workflow",
        "keywords": (
            "incident",
            "postmortem",
            "post-mortem",
            "outage",
            "regression analysis",
            "root cause",
            "timeline",
            "blast radius",
            "rollback",
            "remediation",
        ),
        "behavior_atoms": (
            "evidence-backed-claims",
            "explicit-evidence-gaps",
            "ordered-next-actions",
        ),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to create an incident postmortem packet for this project.",
        "expected_artifacts": (
            "expertise packet",
            "incident timeline",
            "cause and contributing-factor audit",
            "ordered follow-up remediation plan",
        ),
    },
    {
        "signal_family": "architecture_decision",
        "workflow_id": "architecture_decision_workflow",
        "name": "Architecture Decision Workflow",
        "keywords": (
            "architecture",
            "adr",
            "architecture decision",
            "decision record",
            "alternative",
            "tradeoff",
            "constraint",
            "migration cost",
            "design decision",
        ),
        "behavior_atoms": (
            "source-traceability",
            "conflict-preservation",
            "evidence-backed-claims",
        ),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to review this architecture decision and produce an ADR packet.",
        "expected_artifacts": (
            "expertise packet",
            "decision context",
            "alternatives and tradeoff audit",
            "recommended ADR outcome",
        ),
    },
    {
        "signal_family": "migration_readiness",
        "workflow_id": "migration_readiness_workflow",
        "name": "Migration Readiness Workflow",
        "keywords": (
            "migration",
            "upgrade",
            "deprecation",
            "refactor plan",
            "rollback",
            "compatibility",
            "sequencing",
            "backfill",
            "cutover",
        ),
        "behavior_atoms": (
            "ordered-next-actions",
            "behavior-verification",
            "explicit-evidence-gaps",
        ),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to review migration readiness and sequencing for this project.",
        "expected_artifacts": (
            "expertise packet",
            "migration readiness rubric",
            "compatibility and rollback audit",
            "sequenced migration plan",
        ),
    },
    {
        "signal_family": "agent_handoff",
        "workflow_id": "agent_handoff_workflow",
        "name": "Agent Handoff Workflow",
        "keywords": (
            "handoff",
            "continuity",
            "resume",
            "state",
            "blocker",
            "next command",
            "open question",
            "context packet",
            "pause",
        ),
        "behavior_atoms": (
            "artifact-contract",
            "ordered-next-actions",
            "source-traceability",
        ),
        "profile": "developer_experience",
        "starter_prompt": "Use TMCP to create an agent handoff and continuity packet for this work.",
        "expected_artifacts": (
            "expertise packet",
            "current-state summary",
            "blockers and open questions",
            "next-action handoff packet",
        ),
    },
    {
        "signal_family": "pr_risk_review",
        "workflow_id": "pr_risk_review_workflow",
        "name": "PR Risk Review Workflow",
        "keywords": (
            "pr",
            "pull request",
            "diff",
            "review",
            "merge",
            "changed contract",
            "regression risk",
            "risk review",
            "ci",
        ),
        "behavior_atoms": (
            "evidence-backed-claims",
            "quality-gate-disclosure",
            "scope-control",
        ),
        "profile": "general_review",
        "starter_prompt": "Use TMCP to review PR risk, changed contracts, and merge readiness.",
        "expected_artifacts": (
            "expertise packet",
            "changed-surface map",
            "risk and regression audit",
            "merge-readiness remediation plan",
        ),
    },
    {
        "signal_family": "repo_behavior_spec_loop",
        "workflow_id": "repo_behavior_spec_loop_workflow",
        "name": "Repo Behavior Spec Loop Workflow",
        "keywords": (
            "repo behavior spec loop",
            "behavior spec",
            "behavioral spec",
            "canonical spreadsheet",
            "single source of truth",
            "feature id",
            "feature ids",
            "code-derived",
            "source files/functions",
            "expected behavior",
            "user-acceptable behavior",
            "observed behavior",
            "defect id",
            "defect type",
            "tested-pass",
            "tested-fail",
            "verified",
            "regression-covered",
            "last tested commit",
            "test fix re-test",
            "complexity review",
        ),
        "behavior_atoms": (
            "artifact-contract",
            "behavior-verification",
            "concrete-citations",
            "evidence-backed-claims",
            "quality-gate-disclosure",
            "source-traceability",
        ),
        "profile": "repo_behavior_spec_loop",
        "starter_prompt": "Use TMCP to run the repo behavior spec loop for this project.",
        "expected_artifacts": (
            "expertise packet",
            "canonical behavior spreadsheet contract",
            "feature inventory and status-machine audit",
            "test/fix/re-test/regression remediation loop",
        ),
    },
)


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value if str(item)] if isinstance(value, list) else []


def workflow_catalog() -> list[dict[str, Any]]:
    """Return isolated copies of every curated workflow definition."""
    return [dict(item) for item in WORKFLOW_SIGNAL_CATALOG]


def select_workflow_catalog(candidate_workflows: object) -> list[dict[str, Any]]:
    """Select curated workflows by identifier or signal family."""
    requested = {item for item in _string_list(candidate_workflows) if item.strip()}
    if not requested:
        return workflow_catalog()
    return [
        dict(item)
        for item in WORKFLOW_SIGNAL_CATALOG
        if item["workflow_id"] in requested or item["signal_family"] in requested
    ]


def workflow_catalog_by_id() -> dict[str, dict[str, Any]]:
    """Index isolated workflow definitions by their stable identifier."""
    return {str(item["workflow_id"]): dict(item) for item in WORKFLOW_SIGNAL_CATALOG}


def workflow_stability(workflow: dict[str, Any]) -> str:
    """Classify a workflow with the established stable/experimental precedence."""
    workflow_id = str(workflow.get("workflow_id") or "")
    if workflow_id in STABLE_WORKFLOW_IDS:
        return "stable"
    if workflow_id in EXPERIMENTAL_WORKFLOW_IDS:
        return "experimental"
    return str(workflow.get("stability") or "experimental")


def stable_workflow_ids() -> list[str]:
    """Return stable public workflow identifiers in deterministic order."""
    return sorted(STABLE_WORKFLOW_IDS)


def experimental_workflow_ids() -> list[str]:
    """Return experimental workflow identifiers in deterministic order."""
    return sorted(EXPERIMENTAL_WORKFLOW_IDS)
