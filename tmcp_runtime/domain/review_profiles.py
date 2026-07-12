"""Review-profile vocabulary and deterministic profile-selection policy."""

from __future__ import annotations

from typing import Any


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value if str(item)] if isinstance(value, list) else []


PROFILE_DIMENSIONS: dict[str, list[dict[str, Any]]] = {
    "public_sector_readiness": [
        {
            "id": "governance_policy_fit",
            "name": "Governance And Policy Fit",
            "weight": 4,
            "expectations": [
                "Evidence for policy, rule ownership, authority boundaries, and acceptance criteria."
            ],
            "questions": [
                "Are governing rules and decision owners explicit?",
                "Can a reviewer trace readiness claims to source artifacts?",
            ],
        },
        {
            "id": "security_privacy_controls",
            "name": "Security And Privacy Controls",
            "weight": 4,
            "expectations": [
                "Evidence for auth, permissions, tenant boundaries, sensitive data handling, and retention."
            ],
            "questions": [
                "Can protected data cross an unauthorized boundary?",
                "Are privacy and permission risks release-gated?",
            ],
        },
        {
            "id": "auditability_provenance",
            "name": "Auditability And Provenance",
            "weight": 4,
            "expectations": [
                "Evidence for audit logs, source provenance, reproducible decisions, and review trails."
            ],
            "questions": [
                "Can important outputs be explained from source evidence?",
                "Are operational actions attributable and reviewable?",
            ],
        },
        {
            "id": "legal_calculation_safety",
            "name": "Legal Calculation Safety",
            "weight": 4,
            "expectations": [
                "Evidence for calculation rules, edge cases, tests, fixtures, and legal-domain assumptions."
            ],
            "questions": [
                "Are calculations protected by domain fixtures or examples?",
                "Are ambiguous legal assumptions surfaced instead of hidden?",
            ],
        },
        {
            "id": "operational_release_readiness",
            "name": "Operational Release Readiness",
            "weight": 3,
            "expectations": [
                "Evidence for CI, deployment, rollback, monitoring, support, and release blockers."
            ],
            "questions": [
                "Are blockers separated from follow-up improvements?",
                "Can the team verify readiness before launch?",
            ],
        },
        {
            "id": "accessibility_public_use",
            "name": "Accessibility And Public Use",
            "weight": 3,
            "expectations": [
                "Evidence for accessibility, user-facing language, error states, and public-service usability."
            ],
            "questions": [
                "Can target users complete critical paths accessibly?",
                "Are failure states understandable and recoverable?",
            ],
        },
    ],
    "visual_polish": [
        {
            "id": "surface_hierarchy",
            "name": "Surface Hierarchy",
            "weight": 4,
            "expectations": [
                "Screen, file, or screenshot evidence showing primary and supporting regions.",
                "Evidence for scan order, density, grouping, visual rhythm, and whether the most valuable workflow is visually dominant.",
            ],
            "questions": [
                "Is there one dominant work region?",
                "Are cards used only where they frame real repeated objects?",
                "Does the page visually communicate what matters first without relying on explanatory text?",
            ],
        },
        {
            "id": "interaction_architecture",
            "name": "Interaction Architecture",
            "weight": 4,
            "expectations": [
                "Evidence for containers, loading states, empty states, overlays, and actions."
            ],
            "questions": [
                "Does the container match the task?",
                "Are states decision-useful instead of decorative?",
                "Are actions, affordances, and feedback placed where the user naturally acts next?",
            ],
        },
        {
            "id": "data_realism",
            "name": "Data Realism",
            "weight": 4,
            "expectations": [
                "Evidence for source, freshness, deterministic data, and non-vanity metrics."
            ],
            "questions": [
                "Are metrics credible?",
                "Are visuals driven by real state rather than decoration?",
                "Does data presentation help comparison, triage, or decision-making?",
            ],
        },
        {
            "id": "product_evidence",
            "name": "Product Evidence",
            "weight": 3,
            "expectations": [
                "Evidence that the first screen reveals the actual product, object, or state.",
                "Evidence that the surface demonstrates the product's value through real objects, ranked work, or inspectable outcomes.",
            ],
            "questions": [
                "Can a viewer understand the product from the first screen?",
                "Is decoration replacing product proof?",
                "Does the first settled viewport show useful work rather than merely proving the route renders?",
            ],
        },
        {
            "id": "design_system_fit",
            "name": "Design System Fit",
            "weight": 3,
            "expectations": [
                "Evidence for tokens, component conventions, typography, spacing, color, contrast, and states.",
                "Evidence that visual styling feels intentional, polished, and consistent across desktop and mobile breakpoints.",
            ],
            "questions": [
                "Does the surface follow local tokens?",
                "Are generic utility colors or defaults leaking through?",
                "Do typography, spacing, contrast, and component affordances improve comprehension and trust?",
            ],
        },
    ],
    "security_privacy": [
        {
            "id": "secret_exposure",
            "name": "Secret Exposure",
            "weight": 4,
            "expectations": [
                "Evidence for env, logs, fixtures, configs, and generated artifacts."
            ],
            "questions": [
                "Can credentials leak through logs?",
                "Are sensitive values redacted?",
            ],
        },
        {
            "id": "permission_boundary",
            "name": "Permission Boundary",
            "weight": 4,
            "expectations": [
                "Evidence for file, network, auth, database, and tool side effects."
            ],
            "questions": [
                "Are mutations explicit?",
                "Are privileged operations approval-gated?",
            ],
        },
        {
            "id": "data_flow_privacy",
            "name": "Data Flow Privacy",
            "weight": 4,
            "expectations": [
                "Evidence for inputs, persistence, retention, and outbound data flow."
            ],
            "questions": [
                "Is sensitive data minimized?",
                "Can retained data be audited?",
            ],
        },
        {
            "id": "supply_chain",
            "name": "Supply Chain",
            "weight": 3,
            "expectations": [
                "Evidence for dependency changes, lockfiles, and provenance."
            ],
            "questions": [
                "Are dependencies justified?",
                "Do lockfiles match repo policy?",
            ],
        },
    ],
    "developer_experience": [
        {
            "id": "command_discoverability",
            "name": "Command Discoverability",
            "weight": 4,
            "expectations": [
                "Evidence for setup, test, lint, typecheck, build, and run commands."
            ],
            "questions": [
                "Can a developer find the right commands?",
                "Do docs match scripts?",
            ],
        },
        {
            "id": "validation_loop",
            "name": "Validation Loop",
            "weight": 4,
            "expectations": [
                "Evidence for fast targeted checks and complete release checks."
            ],
            "questions": ["Is the inner loop fast?", "Are failures actionable?"],
        },
        {
            "id": "interface_clarity",
            "name": "Interface Clarity",
            "weight": 3,
            "expectations": ["Evidence for API, CLI, schema, errors, and examples."],
            "questions": [
                "Are public interfaces predictable?",
                "Can errors guide next action?",
            ],
        },
    ],
    "general_review": [
        {
            "id": "source_grounding",
            "name": "Source Grounding",
            "weight": 4,
            "expectations": [
                "Evidence that findings cite concrete local or user-provided sources."
            ],
            "questions": ["Is each claim grounded?", "Are skipped scopes explicit?"],
        },
        {
            "id": "risk_priority",
            "name": "Risk Priority",
            "weight": 4,
            "expectations": [
                "Evidence that blockers, warnings, and observations are separated."
            ],
            "questions": [
                "Are correctness risks first?",
                "Are preferences separate from defects?",
            ],
        },
        {
            "id": "verification_readiness",
            "name": "Verification Readiness",
            "weight": 4,
            "expectations": [
                "Evidence that remediation can be verified by commands or checks."
            ],
            "questions": ["Can the next worker know when a slice is done?"],
        },
        {
            "id": "scope_control",
            "name": "Scope Control",
            "weight": 3,
            "expectations": [
                "Evidence for reviewed scope, deferred scope, and explicit gaps."
            ],
            "questions": [
                "Is the reviewed surface bounded?",
                "Are unreviewed areas named?",
            ],
        },
    ],
    "repo_behavior_spec_loop": [
        {
            "id": "code_derived_feature_inventory",
            "name": "Code-Derived Feature Inventory",
            "weight": 4,
            "expectations": [
                "Evidence for discovered routes, screens, actions, APIs, auth states, data preconditions, and stable feature IDs."
            ],
            "questions": [
                "Does every discoverable feature have a stable ID and source citation?",
                "Are expected behaviors derived from code instead of assumptions?",
            ],
        },
        {
            "id": "canonical_spreadsheet_contract",
            "name": "Canonical Spreadsheet Contract",
            "weight": 4,
            "expectations": [
                "Evidence that one canonical spreadsheet is updated in place with required status, defect, evidence, and iteration columns."
            ],
            "questions": [
                "Is the spreadsheet the single source of truth for the run?",
                "Are status transitions and defect metadata explicit?",
            ],
        },
        {
            "id": "running_app_verification_loop",
            "name": "Running-App Verification Loop",
            "weight": 4,
            "expectations": [
                "Evidence for test method, exact command or browser action, observed behavior, iteration, and last tested commit."
            ],
            "questions": [
                "Can a reviewer reproduce the observed result?",
                "Are failures fixed, re-tested, and reclassified through the status machine?",
            ],
        },
        {
            "id": "regression_and_complexity_gate",
            "name": "Regression And Complexity Gate",
            "weight": 3,
            "expectations": [
                "Evidence for regression coverage, smallest safe fixes, complexity review, and explicit reasons for manual-only coverage."
            ],
            "questions": [
                "Did fixes avoid unrelated refactors and speculative abstractions?",
                "Is each verified behavior regression-covered or explicitly dispositioned?",
            ],
        },
    ],
}

PROFILE_COVERAGE_REQUIREMENTS: dict[str, tuple[dict[str, object], ...]] = {
    "public_sector_readiness": (
        {
            "id": "public_governance_coverage",
            "label": "public-sector governance coverage",
            "terms": (
                "accessibility",
                "audit",
                "calculation",
                "compliance",
                "governance",
                "legal",
                "policy",
                "privacy",
                "readiness",
                "release",
                "security",
                "tenant",
            ),
            "issue": (
                "Public-sector readiness coverage is missing: include evidence about governance, "
                "security/privacy controls, auditability, legal calculation safety, release readiness, "
                "and accessibility."
            ),
        },
    ),
    "visual_polish": (
        {
            "id": "visual_product_quality",
            "label": "visual product-quality coverage",
            "terms": (
                "affordance",
                "alignment",
                "color",
                "contrast",
                "density",
                "hierarchy",
                "layout",
                "polish",
                "rhythm",
                "spacing",
                "typography",
                "visual",
            ),
            "issue": (
                "Visual product-quality coverage is missing: include evidence about typography, spacing, "
                "layout hierarchy, density, color/contrast, affordances, and responsive polish."
            ),
        },
        {
            "id": "whole_product_value",
            "label": "whole-product value coverage",
            "terms": (
                "compare",
                "decision",
                "inspect",
                "outcome",
                "prioritize",
                "product",
                "rank",
                "scan",
                "triage",
                "workflow",
            ),
            "issue": (
                "Whole-product value coverage is missing: include evidence that the UI helps users scan, "
                "compare, prioritize, inspect, or complete the core workflow."
            ),
        },
    ),
    "security_privacy": (
        {
            "id": "security_privacy_coverage",
            "label": "security/privacy coverage",
            "terms": (
                "auth",
                "credential",
                "data flow",
                "dependency",
                "lockfile",
                "permission",
                "privacy",
                "redact",
                "retention",
                "secret",
                "security",
                "sensitive",
                "supply chain",
                "token",
            ),
            "issue": (
                "Security/privacy coverage is missing: include evidence about secrets, credentials, "
                "auth, permission boundaries, sensitive data flow, retention, redaction, and supply chain risk."
            ),
        },
    ),
    "developer_experience": (
        {
            "id": "developer_experience_coverage",
            "label": "developer-experience coverage",
            "terms": (
                "build",
                "cli",
                "command",
                "docs",
                "error",
                "example",
                "install",
                "lint",
                "onboarding",
                "readme",
                "script",
                "setup",
                "test",
                "typecheck",
                "validation",
            ),
            "issue": (
                "Developer-experience coverage is missing: include evidence about setup, commands, "
                "documentation, validation loops, interfaces, examples, and actionable errors."
            ),
        },
    ),
    "general_review": (
        {
            "id": "general_review_coverage",
            "label": "general review coverage",
            "terms": (
                "blocker",
                "command",
                "evidence",
                "gap",
                "risk",
                "scope",
                "source",
                "test",
                "verify",
                "warning",
            ),
            "issue": (
                "General review coverage is missing: include evidence about source grounding, risk priority, "
                "verification readiness, and reviewed/deferred scope."
            ),
        },
    ),
    "repo_behavior_spec_loop": (
        {
            "id": "repo_behavior_spec_loop_coverage",
            "label": "repo behavior spec loop coverage",
            "terms": (
                "canonical spreadsheet",
                "feature id",
                "source files",
                "expected behavior",
                "observed behavior",
                "status",
                "defect",
                "regression",
                "verified",
                "last tested commit",
            ),
            "issue": (
                "Repo behavior spec loop coverage is missing: include evidence about the canonical spreadsheet, "
                "stable feature IDs, code-derived expected behavior, observed results, defect status, "
                "regression coverage, and last tested commit."
            ),
        },
    ),
}


def profile_dimensions(profile: str) -> list[dict[str, Any]]:
    """Return the configured dimensions for a profile with the legacy fallback."""
    return PROFILE_DIMENSIONS.get(profile, PROFILE_DIMENSIONS["general_review"])


def select_review_profile(objective: str, packet: dict[str, Any]) -> str:
    """Classify review work using the established profile precedence."""
    haystack = " ".join(
        [
            objective,
            str(packet.get("task_id", "")),
            " ".join(_string_list(packet.get("selected_nodes"))),
            " ".join(_string_list(packet.get("behavior_atoms"))),
        ]
    ).lower()
    if any(
        term in haystack
        for term in ("ui", "ux", "frontend", "visual", "screen", "design")
    ):
        return "visual_polish"
    if any(
        term in haystack
        for term in (
            "government",
            "public sector",
            "public-sector",
            "compliance",
            "tenant",
            "auditability",
            "legal",
            "calculation",
            "uat",
            "release blocker",
        )
    ) or (
        "readiness" in haystack
        and any(
            term in haystack
            for term in ("government", "public sector", "public-sector", "compliance")
        )
    ):
        return "public_sector_readiness"
    if any(
        term in haystack for term in ("security", "privacy", "secret", "permission")
    ):
        return "security_privacy"
    if any(
        term in haystack
        for term in ("developer", "docs", "cli", "command", "onboarding")
    ):
        return "developer_experience"
    return "general_review"
