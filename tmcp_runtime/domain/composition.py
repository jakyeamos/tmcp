"""Deterministic composition policy shared by TMCP runtime adapters."""

from __future__ import annotations

import re
from typing import Any


UI_SIGNAL_TERMS = (
    "ui",
    "ux",
    "frontend",
    "front-end",
    "react",
    "next.js",
    "tsx",
    "jsx",
    "css",
    "dashboard",
    "landing page",
    "design",
    "browser",
    "responsive",
    "contrast",
    "button",
    "buttons",
    "controls",
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
    ".astro",
    ".html",
)
REPO_BEHAVIOR_PHRASES = (
    "repo behavior",
    "behavior sweep",
    "behavior spec",
    "canonical spreadsheet",
    "feature id",
    "feature ids",
    "status machine",
    "status-machine",
)
UI_VERIFICATION_TERMS = (
    "browser",
    "screenshot",
    "contrast",
    "reduced motion",
    "responsive",
)


def _json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item)]


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


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


def _objective_has_phrase(objective: str, phrases: tuple[str, ...]) -> bool:
    lower = objective.lower()
    normalized = lower.replace("-", " ").replace("_", " ")
    return any(phrase in lower or phrase in normalized for phrase in phrases)


def is_uiish_text(value: str) -> bool:
    return any(_contains_signal_term(value, term) for term in UI_SIGNAL_TERMS)


def is_ui_file(path: str) -> bool:
    return path.lower().endswith(UI_FILE_SUFFIXES)


def contextual_atoms_and_gates(
    objective: str,
    phase: str,
    context: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    files_changed = _string_list(context.get("files_changed"))
    failures = _string_list(context.get("failures"))
    browser_evidence = _string_list(context.get("browser_evidence"))
    objective_lower = objective.lower()
    failure_text = " ".join(failures).lower()
    pending_hosted_release_evidence = any(
        term in failure_text for term in ("hosted evidence", "release evidence")
    ) and any(
        term in failure_text
        for term in ("pending", "no hosted", "no matching", "external")
    )
    active_atoms: list[str] = []
    required_reads: list[str] = []
    verification_gates: list[str] = []
    if is_uiish_text(objective) or any(is_ui_file(path) for path in files_changed):
        active_atoms.append("ui-browser-verification")
        required_reads.append("UI/browser verification guidance for changed surfaces.")
        verification_gates.append(
            "Verify rendered UI in a browser with screenshot or DOM evidence."
        )
        if any(
            term in objective_lower
            for term in ("design", "landing", "frontend", "ui", "dashboard")
        ):
            verification_gates.extend(
                [
                    "Verify contrast on visible UI states.",
                    "Verify reduced motion behavior where animation is present.",
                    "Verify responsive behavior across relevant viewport sizes.",
                ]
            )
    if pending_hosted_release_evidence:
        active_atoms.append("explicit-evidence-gaps")
        required_reads.append(
            "Hosted release evidence record and release evidence checker output."
        )
        verification_gates.append(
            "Do not claim release readiness until hosted evidence is recorded for release."
        )
    elif failures or any(
        term in objective_lower for term in ("bug", "failing", "failure", "debug")
    ):
        active_atoms.append("debugging-regression")
        required_reads.append(
            "Debugging and regression evidence from the current failure."
        )
        verification_gates.append(
            "Re-run the failing command and capture the passing result."
        )
    if phase == "final" or "final" in objective_lower:
        active_atoms.append("verification-before-completion")
        verification_gates.append(
            "Run the highest-signal verification gate before final response."
        )
    if browser_evidence and "ui-browser-verification" not in active_atoms:
        active_atoms.append("ui-browser-verification")
        verification_gates.append("Use browser evidence to confirm the next claim.")
    return (
        _ordered_unique(active_atoms),
        _ordered_unique(required_reads),
        _ordered_unique(verification_gates),
    )


def filter_source_verification_gates(
    gates: list[str],
    objective: str,
    context: dict[str, Any],
) -> list[str]:
    ui_context = is_uiish_text(objective) or any(
        is_ui_file(path) for path in _string_list(context.get("files_changed"))
    )
    repo_behavior_context = _objective_has_phrase(objective, REPO_BEHAVIOR_PHRASES)
    filtered: list[str] = []
    for gate in gates:
        lower = gate.lower()
        if any(term in lower for term in UI_VERIFICATION_TERMS) and not ui_context:
            continue
        if "canonical spreadsheet" in lower and not repo_behavior_context:
            continue
        filtered.append(gate)
    return filtered


def matching_reference_reads(
    source_nodes: list[dict[str, Any]],
    objective: str,
) -> list[str]:
    objective_lower = objective.lower()
    reads: list[str] = []
    for node in source_nodes:
        rel_path = str(node.get("relative_path") or "")
        rel_lower = rel_path.lower()
        if (
            "/reference/" not in f"/{rel_lower}"
            and "/references/" not in f"/{rel_lower}"
        ):
            continue
        if "craft" in objective_lower and rel_lower.endswith("craft.md"):
            reads.append(rel_path)
        if any(
            term in objective_lower for term in ("landing", "brand", "site")
        ) and rel_lower.endswith("brand.md"):
            reads.append(rel_path)
        if any(
            term in objective_lower for term in ("dashboard", "product", "audit")
        ) and rel_lower.endswith("product.md"):
            reads.append(rel_path)
        if (
            any(
                term in objective_lower
                for term in ("verify", "verification", "browser")
            )
            and "verification" in rel_lower
        ):
            reads.append(rel_path)
    return reads
