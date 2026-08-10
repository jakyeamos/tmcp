"""Static data for deterministic task routing and skill-source affinity."""

ROUTE_CATALOG_VERSION = "2026-08-02.1"
ROUTE_SCORE_THRESHOLD = 2.0
MAX_SECONDARY_ROUTES = 6

CREATION_OR_RESEARCH_ROUTES = frozenset(
    {
        "ui_ux_redesign",
        "frontend_implementation",
        "backend_api_implementation",
        "data_database_migration",
        "security_remediation",
        "documentation",
        "test_strategy",
        "architecture_decision",
        "agent_workflow",
        "general_implementation",
        "motion_interaction",
        "freshness_research",
    }
)
CREATION_OR_RESEARCH_LEADS = (
    "design",
    "create",
    "build",
    "implement",
    "write",
    "draft",
    "record",
    "define",
    "research",
)

UI_FILE_SUFFIXES = (
    ".tsx",
    ".jsx",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
    ".html",
)

COMPOSITE_PRIMARY_ROUTES: dict[str, frozenset[str]] = {
    "frontend_product_redesign": frozenset(
        {"ui_ux_redesign", "frontend_implementation"}
    ),
}

COMPOSITE_TASK_PROFILES: dict[str, dict[str, str]] = {
    "frontend_product_redesign": {
        "domain": "frontend",
        "action": "redesign",
        "mode": "implementation",
    }
}

SEED_MATCH_THRESHOLD = 5.0
SEED_MATCH_THRESHOLD_WITH_ROUTE_AFFINITY = 3.5
LEGACY_SEED_MATCH_THRESHOLD = 4.0

ROUTE_SOURCE_SLUG_PATTERNS: dict[str, tuple[str, ...]] = {
    "explicit_audit": ("audit", "risk-review", "readiness-review", "rubric"),
    "ui_ux_redesign": (
        "ui-ux",
        "ui-ux-pro-max",
        "redesign",
        "frontend-design",
        "visual-design",
        "taste",
        "impeccable",
    ),
    "frontend_implementation": (
        "frontend",
        "ui-implementation",
        "react",
        "component",
        "nextjs",
        "next.js",
    ),
    "backend_api_implementation": ("backend", "api", "server", "webhook"),
    "data_database_migration": ("database", "data", "migration", "backfill"),
    "security_remediation": ("security", "privacy", "hardening"),
    "documentation": ("documentation", "docs", "writing"),
    "test_strategy": ("test-strategy", "testing", "quality"),
    "architecture_decision": ("architecture-decision", "architecture", "adr"),
    "agent_workflow": ("agent-handoff", "agent-workflow", "routing-policy"),
    "general_implementation": ("implementation", "engineering"),
    "motion_interaction": (
        "motion",
        "animation",
        "interaction",
        "micro-interaction",
    ),
    "freshness_research": (
        "research",
        "trend",
        "inspiration",
        "last30days",
    ),
    "accessibility_validation": (
        "accessibility",
        "a11y",
        "wcag",
        "contrast",
    ),
    "performance_validation": (
        "performance",
        "lighthouse",
        "bundle",
        "latency",
    ),
    "debugging_regression": (
        "debug",
        "regression",
        "diagnose",
    ),
    "release_readiness": (
        "release-readiness",
        "release_readiness",
        "release readiness",
        "ship",
        "changelog",
    ),
}
