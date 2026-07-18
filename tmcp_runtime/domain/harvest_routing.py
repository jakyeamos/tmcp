"""Pure routing-policy extraction for harvested source text."""

from __future__ import annotations

import re
from typing import Any

from .declared_loads import declared_load_patterns_from_text
from .routes import has_accessibility_contrast_context


def ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _directive_lines(text: str) -> list[str]:
    """Return prose lines that can carry a harvested instruction."""

    lines: list[str] = []
    fence_marker: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence_marker is None:
                fence_marker = marker
            elif marker == fence_marker:
                fence_marker = None
            continue
        if fence_marker is None and stripped:
            lines.append(line)
    return lines


def _has_stop_marker(line: str) -> bool:
    lower = line.lower()
    return (
        (
            re.search(r"(?<![_a-z])stop(?![_a-z])", lower) is not None
            and "stop condition" not in lower
        )
        or "ask the user" in lower
        or "do not advance" in lower
        or "checkpoint" in lower
        or "approval" in lower
    )


def routing_metadata_for(rel_path: str, text: str) -> dict[str, Any]:
    lower = text.lower()
    normalized_lower = re.sub(r"[^a-z0-9]+", " ", lower)
    commands = sorted(
        {
            match.strip().split()[0]
            for match in re.findall(r"`([a-z][a-z0-9_-]+(?:\s+[^`]*)?)`", text)
            if match.strip().split()[0]
            in {
                "adapt",
                "animate",
                "audit",
                "bolder",
                "clarify",
                "colorize",
                "craft",
                "critique",
                "delight",
                "distill",
                "document",
                "extract",
                "harden",
                "hooks",
                "init",
                "layout",
                "live",
                "onboard",
                "optimize",
                "overdrive",
                "polish",
                "quieter",
                "shape",
                "typeset",
            }
        }
    )
    required_reads = ordered_unique(
        re.findall(r"reference/[A-Za-z0-9_.-]+\.md", text)
        + re.findall(r"references/[A-Za-z0-9_.-]+\.md", text)
    )
    declared_loads = declared_load_patterns_from_text(text)
    script_prompts = ordered_unique(
        re.findall(r"(?:[\w./-]+/)?scripts/[A-Za-z0-9_./-]+\.(?:mjs|js|py)", text)
    )
    setup_blockers = []
    if "no_product_md" in lower:
        setup_blockers.append("NO_PRODUCT_MD requires init before design work.")
    if "update_available" in lower:
        setup_blockers.append(
            "UPDATE_AVAILABLE should be surfaced once before continuing."
        )
    directive_lines = _directive_lines(text)
    stop_conditions = [
        line.strip(" -*") for line in directive_lines if _has_stop_marker(line)
    ][:8]
    if "confirm before any irreversible action" in normalized_lower:
        stop_conditions.insert(
            0,
            "Wait for explicit user confirmation before irreversible or external actions.",
        )
    if (
        "preserve every dirty worktree and every branch with unique or ambiguous work"
        in normalized_lower
    ):
        stop_conditions.insert(
            0,
            (
                "Preserve dirty worktrees and branches with unique or ambiguous work; "
                "do not prune on uncertain evidence."
            ),
        )
    if "never force push" in normalized_lower and "git branch d" in normalized_lower:
        stop_conditions.insert(
            0,
            (
                "Do not force-push, force-delete branches, or bypass hooks while "
                "branch evidence is uncertain."
            ),
        )
    autofix_stops: list[str] = []
    if all(
        phrase in normalized_lower
        for phrase in ("auth required", "browser connect", "do not modify code")
    ):
        autofix_stops.append(
            (
                "On AUTH_REQUIRED or BROWSER_CONNECT, do not modify code; ask the "
                "user to restore the local environment."
            )
        )
    if "only modify the file at repaircontext adapter sourcepath" in normalized_lower:
        autofix_stops.append("Modify only RepairContext.adapter.sourcePath.")
    if all(
        phrase in normalized_lower
        for phrase in ("never modify", "package json", "tsconfig json")
    ):
        autofix_stops.append(
            (
                "Do not modify OpenCLI core, extension, test, or package "
                "configuration files during adapter repair."
            )
        )
    if "max 3 repair rounds per failure" in normalized_lower:
        autofix_stops.append(
            "Stop after three failed repair rounds and report what was tried."
        )
    if "ask the user before filing" in normalized_lower:
        autofix_stops.append(
            "Obtain explicit user confirmation before filing an upstream issue."
        )
    stop_conditions = autofix_stops + stop_conditions
    verification_gates: list[str] = []
    gate_terms = {
        "reduced motion": "Verify reduced motion behavior.",
        "browser": "Verify rendered behavior in a browser.",
        "screenshot": "Capture or inspect screenshot evidence.",
        "responsive": "Verify responsive behavior.",
        "test": "Run relevant tests.",
        "regression": "Add or verify regression coverage.",
        "canonical spreadsheet": "Verify canonical spreadsheet status and evidence.",
        "last tested commit": "Record the last tested commit.",
    }
    if has_accessibility_contrast_context(text):
        verification_gates.append("Verify contrast.")
    if all(term in lower for term in ("owner", "consumer", "verify")):
        verification_gates.append(
            "Verify behavior through identified consumers, not only the owner."
        )
    if "don't run it end-to-end yourself" in lower:
        verification_gates.append(
            "Do not run a human-interactive wizard end-to-end; trace it statically."
        )
    if (
        "verify the live remote head again before promotion and pruning"
        in normalized_lower
    ):
        verification_gates.append(
            "Verify the live remote target head before any promotion or pruning."
        )
    if (
        "use ancestry and git cherry patch equivalence before claiming that work is redundant"
        in normalized_lower
    ):
        verification_gates.append(
            (
                "Verify ancestry and git cherry patch equivalence before declaring a "
                "branch superseded."
            )
        )
    for term, gate in gate_terms.items():
        if term in lower:
            verification_gates.append(gate)
    phase_hints: list[str] = []
    rel_lower = rel_path.lower()
    if any(term in lower or term in rel_lower for term in ("craft", "implement")):
        phase_hints.append("implementation")
    if any(term in lower or term in rel_lower for term in ("shape", "discover")):
        phase_hints.append("discovery")
    if any(term in lower or term in rel_lower for term in ("audit", "critique")):
        phase_hints.append("verification")
    if any(term in lower or term in rel_lower for term in ("polish", "final")):
        phase_hints.append("final")
    do_not_use_when = [
        line.strip(" -*")
        for line in directive_lines
        if "do not use" in line.lower() or "not for" in line.lower()
    ][:6]
    output_contract_candidates: list[str] = []
    in_output_contract = False
    for line in directive_lines:
        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line.strip())
        if heading:
            in_output_contract = (
                re.sub(r"[^a-z0-9]+", " ", heading.group(1).lower()).strip()
                == "output contract"
            )
            continue
        item = line.strip(" -*#")
        normalized_item = re.sub(r"[^a-z0-9]+", " ", item.lower()).strip()
        if not item:
            continue
        if in_output_contract:
            if normalized_item not in {
                "output contract",
                "produce or cite",
                "every workflow answer should include or cite",
            }:
                output_contract_candidates.append(item)
            continue
        if (
            "must include" in normalized_item
            or normalized_item.startswith(
                ("report ", "provide ", "produce ", "handoff ")
            )
            or (item.startswith("Return ") and normalized_item.startswith("return "))
        ):
            output_contract_candidates.append(item)
    output_contract = ordered_unique(output_contract_candidates)[:8]
    trigger_phrases = commands + [
        term
        for term in (
            "frontend",
            "design",
            "dashboard",
            "landing page",
            "repo behavior",
            "canonical spreadsheet",
            "release",
            "debug",
            "verification",
        )
        if term in lower
    ]
    return {
        "commands": commands,
        "trigger_phrases": ordered_unique(trigger_phrases),
        "required_reads": required_reads,
        "declared_loads": declared_loads,
        "tool_script_prompts": script_prompts,
        "setup_blockers": setup_blockers,
        "stop_conditions": ordered_unique(stop_conditions),
        "output_contract": output_contract,
        "do_not_use_when": do_not_use_when,
        "verification_gates": ordered_unique(verification_gates),
        "phase_hints": ordered_unique(phase_hints),
    }
