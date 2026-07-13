"""Source guidance-label policy for harvested content."""

from __future__ import annotations

import re
from typing import Any


NEGATIVE_SIGNAL_LINE_MARKERS = (
    "do not use",
    "don't use",
    "not for",
    "outside scope",
    "out of scope",
)


def contains_signal_term(text: str, term: str) -> bool:
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


def matched_signal_terms(text: str, terms: tuple[str, ...] | list[str]) -> list[str]:
    return [term for term in terms if contains_signal_term(text, str(term))]


def positive_signal_text(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not any(marker in line.lower() for marker in NEGATIVE_SIGNAL_LINE_MARKERS)
    )


SOURCE_GUIDANCE_LABEL_RULES: tuple[dict[str, object], ...] = (
    {
        "id": "release:readiness",
        "label": "Release readiness",
        "summary": "Source contributes release, ship/no-ship, CI, package, changelog, version, rollback, or readiness guidance.",
        "terms": (
            "release readiness",
            "release",
            "ship",
            "ship/no-ship",
            "ci evidence",
            "ci verification",
            "package check",
            "package checks",
            "version evidence",
            "changelog",
            "rollback",
        ),
    },
    {
        "id": "security:privacy",
        "label": "Security and privacy",
        "summary": "Source contributes security, privacy, permission, auth, redaction, credential, token, or secret-handling guidance.",
        "terms": (
            "security",
            "privacy",
            "permission",
            "permissions",
            "auth",
            "redact",
            "redaction",
            "credential",
            "credentials",
            "token",
            "tokens",
            "secret",
            "secrets",
        ),
    },
    {
        "id": "data:integrity",
        "label": "Data integrity",
        "summary": "Source contributes schema, migration, invariant, pipeline, reconciliation, idempotency, backfill, or data-loss guidance.",
        "terms": (
            "data integrity",
            "schema",
            "schemas",
            "migration",
            "migrations",
            "invariant",
            "invariants",
            "pipeline",
            "pipelines",
            "reconciliation",
            "idempotency",
            "backfill",
            "backfills",
            "data loss",
        ),
    },
    {
        "id": "performance:readiness",
        "label": "Performance readiness",
        "summary": "Source contributes latency, profiling, runtime, load, cache, query, bundle, scaling, or measurement guidance.",
        "terms": (
            "performance",
            "latency",
            "profiling",
            "runtime",
            "load test",
            "load-test",
            "cache",
            "query",
            "bundle",
            "scaling",
            "measurement",
        ),
    },
    {
        "id": "dx:onboarding",
        "label": "Developer experience",
        "summary": "Source contributes onboarding, setup, command discovery, README, contribution flow, CI clarity, or maintainer handoff guidance.",
        "terms": (
            "developer experience",
            "onboarding",
            "setup",
            "command discovery",
            "readme",
            "contribution",
            "ci clarity",
            "maintainer handoff",
        ),
    },
    {
        "id": "architecture:decision",
        "label": "Architecture decision",
        "summary": "Source contributes architecture, ADR, boundary, tradeoff, alternative, constraint, platform, or design-decision guidance.",
        "terms": (
            "architecture",
            "adr",
            "design decision",
            "boundary",
            "tradeoff",
            "alternative",
            "alternatives",
            "constraint",
            "constraints",
            "platform",
        ),
    },
    {
        "id": "testing:regression",
        "label": "Testing and regression",
        "summary": "Source contributes tests, regression coverage, verification commands, expected behavior, or acceptance checks.",
        "terms": (
            "test strategy",
            "test",
            "tests",
            "regression",
            "coverage",
            "expected behavior",
            "acceptance",
            "fixtures",
        ),
    },
    {
        "id": "verification:gates",
        "label": "Verification gates",
        "summary": "Source contributes explicit verification gates, quality gates, evidence requirements, command checks, or pass/fail criteria.",
        "terms": (
            "verification gate",
            "verification gates",
            "quality gate",
            "quality gates",
            "verify",
            "verification",
            "evidence",
            "command",
            "commands",
            "pass",
            "fail",
        ),
    },
    {
        "id": "repo:behavior-spec",
        "label": "Repo behavior spec",
        "summary": "Source contributes feature inventory, canonical spreadsheet, Feature IDs, observed behavior, status machine, or last-tested guidance.",
        "terms": (
            "repo behavior",
            "behavior spec",
            "canonical spreadsheet",
            "feature id",
            "feature ids",
            "observed behavior",
            "status machine",
            "last tested commit",
        ),
    },
    {
        "id": "agent:handoff",
        "label": "Agent handoff",
        "summary": "Source contributes handoff, continuity, current state, touched files, blockers, open questions, or next-command guidance.",
        "terms": (
            "handoff",
            "continuity",
            "current state",
            "touched files",
            "blockers",
            "open questions",
            "next commands",
        ),
    },
    {
        "id": "pr:risk",
        "label": "PR risk",
        "summary": "Source contributes changed-surface, merge-risk, diff, contract, blocker, CI, review, or regression-risk guidance.",
        "terms": (
            "pr risk",
            "pull request risk",
            "changed surface",
            "changed-surface",
            "merge risk",
            "diff",
            "touched contracts",
            "changed contracts",
            "contract change",
            "contract changes",
            "blocker",
            "blockers",
        ),
    },
    {
        "id": "migration:readiness",
        "label": "Migration readiness",
        "summary": "Source contributes migration, upgrade, deprecation, compatibility, rollout, rollback, or sequenced refactor guidance.",
        "terms": (
            "migration readiness",
            "migration",
            "upgrade",
            "deprecation",
            "compatibility",
            "rollout",
            "sequenced refactor",
        ),
    },
    {
        "id": "routing:workflow-selection",
        "label": "Workflow selection",
        "summary": "Source contributes workflow routing, skill harvest, promotion, packet composition, or agent-tool selection guidance.",
        "terms": (
            "workflow recommendation",
            "workflow routing",
            "skill harvest",
            "promote harvest",
            "compose packet",
            "runtime routing",
            "agent routing",
        ),
    },
    {
        "id": "writing:explore-fragments",
        "label": "Writing explore fragments",
        "summary": "Source contributes fragment mining, raw-material capture, interview, or explore-phase writing guidance.",
        "terms": (
            "writing_explore_exploit_v1",
            "explore fragments",
            "explore.fragments",
            "fragments",
            "fragment mining",
            "raw fragments",
            "raw material",
        ),
    },
    {
        "id": "writing:exploit-shape",
        "label": "Writing exploit shape",
        "summary": "Source contributes article shaping, paragraph-by-paragraph drafting, or exploit-phase structure guidance.",
        "terms": (
            "writing_explore_exploit_v1",
            "exploit shape",
            "exploit.shape",
            "shape article",
            "paragraph by paragraph",
            "article journey",
        ),
    },
    {
        "id": "writing:exploit-beats",
        "label": "Writing exploit beats",
        "summary": "Source contributes beat selection, candidate next moves, or one-beat-at-a-time writing guidance.",
        "terms": (
            "writing_explore_exploit_v1",
            "exploit beats",
            "exploit.beats",
            "beat sequence",
            "selected beat",
            "candidate next moves",
        ),
    },
    {
        "id": "workflow:spec-grilling",
        "label": "Workflow spec grilling",
        "summary": "Source contributes recurring-loop discovery, implementable workflow specs, one-question interviews, or checkpoint brief guidance.",
        "terms": (
            "workflow_spec_grilling_v1",
            "recurring loops",
            "workflow specs",
            "workflow spec",
            "one question at a time",
            "human checkpoints",
            "implementer can build",
        ),
    },
    {
        "id": "wayfinding:map-ticket",
        "label": "Wayfinding map and ticket",
        "summary": "Source contributes large-work maps, fog clearing, child tickets, claimed-ticket work, or frontier-ticket resolution guidance.",
        "terms": (
            "large_work_wayfinding_v1",
            "wayfinding",
            "map and child tickets",
            "child tickets",
            "frontier ticket",
            "claimed ticket",
            "fog",
            "ticket types",
        ),
    },
    {
        "id": "ui:buttons-controls",
        "label": "Buttons and controls",
        "summary": "Source contains concrete guidance for buttons, controls, inputs, menus, toolbars, or tooltips.",
        "terms": (
            "button",
            "buttons",
            "icon button",
            "cta",
            "controls",
            "segmented control",
            "toggle",
            "checkbox",
            "slider",
            "stepper",
            "input",
            "menu",
            "toolbar",
            "tooltip",
        ),
    },
    {
        "id": "ui:layout-hierarchy",
        "label": "Layout and hierarchy",
        "summary": "Source helps with scan order, visual hierarchy, spacing, density, cards, layout, or first-screen structure.",
        "terms": (
            "layout",
            "hierarchy",
            "scan",
            "spacing",
            "density",
            "grid",
            "card",
            "cards",
            "hero",
            "first viewport",
        ),
    },
    {
        "id": "ui:design-system-fit",
        "label": "Design-system fit",
        "summary": "Source helps choose or reuse design-system components, tokens, icons, badges, tables, modals, or shared UI patterns.",
        "terms": (
            "design system",
            "design-system",
            "tokens",
            "component",
            "components",
            "shared ui",
            "badge",
            "status pill",
            "table",
            "modal",
            "lucide",
            "shadcn",
        ),
    },
    {
        "id": "ui:responsive-accessibility",
        "label": "Responsive and accessibility",
        "summary": "Source helps verify mobile behavior, viewport fit, contrast, focus, keyboard, reduced motion, or accessibility.",
        "terms": (
            "responsive",
            "mobile",
            "viewport",
            "contrast",
            "focus",
            "keyboard",
            "reduced motion",
            "accessibility",
            "wcag",
        ),
    },
    {
        "id": "ui:browser-verification",
        "label": "Browser verification",
        "summary": "Source calls for rendered browser, screenshot, DOM, Playwright, canvas, or pixel evidence.",
        "terms": (
            "browser",
            "screenshot",
            "rendered",
            "dom",
            "playwright",
            "canvas",
            "pixel",
        ),
    },
    {
        "id": "ui:frontend-implementation",
        "label": "Frontend implementation",
        "summary": "Source carries framework or implementation guidance for React, Next.js, TSX, JSX, CSS, or client/server boundaries.",
        "terms": (
            "frontend",
            "front-end",
            "react",
            "next.js",
            "tsx",
            "jsx",
            "css",
            "server component",
            "use client",
        ),
    },
)


WORKFLOW_SIGNAL_GUIDANCE_LABEL_IDS: dict[str, tuple[str, ...]] = {
    "ui_quality": (
        "ui:buttons-controls",
        "ui:layout-hierarchy",
        "ui:design-system-fit",
        "ui:responsive-accessibility",
        "ui:browser-verification",
        "ui:frontend-implementation",
        "ui:general",
    ),
    "security_privacy": ("security:privacy",),
    "testing_quality": ("testing:regression", "verification:gates"),
    "release_readiness": ("release:readiness",),
    "developer_experience": ("dx:onboarding",),
    "performance": ("performance:readiness",),
    "data_correctness": ("data:integrity",),
    "architecture_decision": ("architecture:decision",),
    "migration_readiness": ("migration:readiness",),
    "agent_handoff": ("agent:handoff",),
    "pr_risk_review": ("pr:risk",),
    "repo_behavior_spec_loop": ("repo:behavior-spec",),
}


def guidance_labels_for(rel_path: str, text: str) -> list[dict[str, Any]]:
    signal_text = positive_signal_text(text)
    haystack = f"{rel_path}\n{signal_text}"
    labels: list[dict[str, Any]] = []
    for rule in SOURCE_GUIDANCE_LABEL_RULES:
        raw_terms = rule.get("terms")
        terms = (
            tuple(str(term) for term in raw_terms)
            if isinstance(raw_terms, (tuple, list))
            else ()
        )
        matched_terms = matched_signal_terms(haystack, terms)
        if not matched_terms:
            continue
        labels.append(
            {
                "id": str(rule["id"]),
                "label": str(rule["label"]),
                "summary": str(rule["summary"]),
                "matched_terms": matched_terms[:8],
            }
        )
    fallback_terms = matched_signal_terms(
        haystack,
        [
            "ui",
            "ux",
            "frontend",
            "front-end",
            "visual",
            "design",
            "interface",
        ],
    )
    path_terms = matched_signal_terms(
        rel_path,
        [
            "ui",
            "ux",
            "frontend",
            "front-end",
            "visual",
            "design",
            "interface",
        ],
    )
    if not labels and (path_terms or len(fallback_terms) >= 2):
        labels.append(
            {
                "id": "ui:general",
                "label": "General UI guidance",
                "summary": "Source is UI-related but does not map to a narrower UI guidance label yet.",
                "matched_terms": fallback_terms[:8],
            }
        )
    return labels[:6]
