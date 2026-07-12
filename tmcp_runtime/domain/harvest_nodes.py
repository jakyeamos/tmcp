"""Pure source-node construction and harvest routing policy."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .declared_loads import declared_load_patterns_from_text, normalize_declared_load_pattern
from .harvest_labels import guidance_labels_for, positive_signal_text
from .standalone_packets import MODULE_BEHAVIOR_ATOMS


SourceAdvisories = Callable[[Path, str, str, str], list[dict[str, Any]]]


def json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    return [str(item) for item in json_list(value) if str(item)]


def text_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", value.lower()))


def estimate_tokens(value: str) -> int:
    return max(1, len(value) // 4)


HARVEST_SOURCE_TYPE_ATOMS: dict[str, tuple[str, ...]] = {
    "skill_definition": (
        "skill-routing",
        "behavior-preservation",
        "source-traceability",
    ),
    "agent_operating_contract": (
        "agent-operating-contract",
        "instruction-precedence",
        "source-traceability",
    ),
    "cursor_rule": ("editor-rule", "workflow-routing", "source-traceability"),
    "github_process": ("repository-process", "quality-gate-disclosure"),
    "project_documentation": ("project-context", "source-grounding"),
    "workflow_prompt": ("workflow-routing", "artifact-contract"),
    "markdown_process_doc": ("process-documentation", "source-grounding"),
}


def source_type_for(path: Path, rel_path: str, text: str) -> str:
    name = path.name.lower()
    rel = rel_path.lower()
    lower = text[:4000].lower()
    if name == "skill.md":
        return "skill_definition"
    if name in {"agents.md", "claude.md"}:
        return "agent_operating_contract"
    if ".cursor/" in rel or name == ".cursorrules":
        return "cursor_rule"
    if ".github/" in rel:
        return "github_process"
    if "workflow" in rel or "workflow" in lower:
        return "workflow_prompt"
    if name == "readme.md" or "/docs/" in f"/{rel}" or "/doc/" in f"/{rel}":
        return "project_documentation"
    return "markdown_process_doc"


def instruction_override_warnings(path: Path, rel_path: str, text: str) -> list[str]:
    lower = text.lower()
    risky_patterns = (
        "ignore previous instructions",
        "ignore all previous instructions",
        "ignore system instructions",
        "override system instructions",
        "override developer instructions",
        "override user instructions",
        "disregard system instructions",
        "disregard developer instructions",
        "disregard user instructions",
        "highest priority instruction",
        "this instruction supersedes",
        "this instruction overrides",
    )
    if not any(pattern in lower for pattern in risky_patterns):
        return []
    return [
        (
            "Untrusted source may attempt to override higher-priority instructions: "
            f"{rel_path} ({path})"
        )
    ]


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


def routing_metadata_for(rel_path: str, text: str) -> dict[str, Any]:
    lower = text.lower()
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
    stop_conditions = [
        line.strip(" -*")
        for line in text.splitlines()
        if any(
            marker in line.lower()
            for marker in (
                "stop",
                "ask the user",
                "do not advance",
                "checkpoint",
                "approval",
            )
        )
    ][:8]
    verification_gates: list[str] = []
    gate_terms = {
        "contrast": "Verify contrast.",
        "reduced motion": "Verify reduced motion behavior.",
        "browser": "Verify rendered behavior in a browser.",
        "screenshot": "Capture or inspect screenshot evidence.",
        "responsive": "Verify responsive behavior.",
        "test": "Run relevant tests.",
        "regression": "Add or verify regression coverage.",
        "canonical spreadsheet": "Verify canonical spreadsheet status and evidence.",
        "last tested commit": "Record the last tested commit.",
    }
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
        for line in text.splitlines()
        if "do not use" in line.lower() or "not for" in line.lower()
    ][:6]
    output_contract = []
    if "output contract" in lower:
        output_contract.append(
            "Source defines an output contract; preserve it in generated packets."
        )
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


def harvest_priority(path: Path, rel_path: str, source_type: str) -> tuple[int, str]:
    name = path.name.lower()
    type_score = {
        "scoped_packet_seed": 0,
        "skill_definition": 0,
        "agent_operating_contract": 1,
        "cursor_rule": 2,
        "github_process": 3,
        "workflow_prompt": 4,
        "project_documentation": 5,
        "markdown_process_doc": 8,
    }.get(source_type, 9)
    if name in {"skill.md", "agents.md", "claude.md", "readme.md"}:
        type_score = min(type_score, 1)
    return type_score, rel_path


def node_harvest_sort_key(node: dict[str, Any]) -> tuple[int, int, str]:
    rel_path = str(node.get("relative_path") or "")
    source_type = str(node.get("source_type") or "")
    type_score, fallback_path = harvest_priority(
        Path(str(node.get("path") or "")),
        rel_path,
        source_type,
    )
    if source_type == "scoped_packet_seed":
        return type_score, int(node.get("seed_index") or 0), fallback_path
    return type_score, 0, fallback_path


def classify_atoms(text: str, source_type: str = "") -> list[str]:
    lower = text.lower()
    atoms: set[str] = set(HARVEST_SOURCE_TYPE_ATOMS.get(source_type, ()))
    for atom_source, atom_values in MODULE_BEHAVIOR_ATOMS.items():
        if atom_source.replace("_", " ") in lower or atom_source in lower:
            atoms.update(atom_values)
    if any(term in lower for term in ("test", "verify", "validate", "quality")):
        atoms.update(MODULE_BEHAVIOR_ATOMS["test_gate"])
    if any(term in lower for term in ("evidence", "source", "citation", "screenshot")):
        atoms.update(MODULE_BEHAVIOR_ATOMS["evidence_first"])
    if any(term in lower for term in ("approval", "ask before", "do not edit")):
        atoms.update(MODULE_BEHAVIOR_ATOMS["user_approval_gate"])
    if any(term in lower for term in ("routing", "workflow", "skill", "agent")):
        atoms.update(MODULE_BEHAVIOR_ATOMS["tool_use_policy"])
    if any(term in lower for term in ("conflict", "precedence", "override", "branch")):
        atoms.add("conflict-preservation")
    if any(
        term in lower for term in ("artifact", "output contract", "schema", "handoff")
    ):
        atoms.add("artifact-contract")
    return sorted(atoms)[:10]


def title_for(path: Path, text: str) -> str:
    frontmatter = frontmatter_for(text)
    for key in ("name", "title", "description"):
        value = frontmatter.get(key)
        if value:
            return value[:100]
    for line in text.splitlines():
        clean = line.strip("# ").strip()
        if clean and not clean.startswith("---"):
            return clean[:100]
    return path.stem


def frontmatter_for(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    frontmatter: dict[str, str] = {}
    for raw_line in text[3:end].splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        clean_key = key.strip().lower()
        clean_value = value.strip().strip("\"'")
        if clean_key and clean_value and len(clean_value) <= 300:
            frontmatter[clean_key] = clean_value
    return frontmatter


SCOPED_PACKET_SEEDS_SCHEMA = "tmcp-scoped-packet-seeds-v0.1"



def scoped_seed_signal_text(seed: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in (
        "id",
        "name",
        "sources",
        "loads",
        "chains_before",
        "chains_after",
        "do_not_activate_with",
        "phase_transitions",
        "use_when",
        "modes",
        "behavior_atoms",
        "minimum_spec_fields",
        "ticket_types",
        "route_affinity",
        "objective_patterns",
        "verification_expectations",
    ):
        value = seed.get(key)
        if isinstance(value, list):
            pieces.extend(str(item) for item in value if str(item))
        elif isinstance(value, dict):
            for phase, details in value.items():
                pieces.append(str(phase))
                if isinstance(details, dict):
                    pieces.extend(
                        str(item)
                        for item in string_list(details.get("activate_skills"))
                        + string_list(details.get("verification_gates"))
                        + string_list(details.get("next_phases"))
                    )
        elif value:
            pieces.append(str(value))
    return "\n".join(pieces)


def scoped_packet_seed_nodes(
    *,
    root_path: str,
    source_path: str,
    rel_path: str,
    payload: dict[str, Any],
    max_excerpt_chars: int,
    redactions: dict[str, int],
) -> list[dict[str, Any]]:
    promotion = payload.get("promotion_recommendation")
    promotion_map = promotion if isinstance(promotion, dict) else {}
    receipt_map = promotion_map.get("required_receipts")
    required_receipts = receipt_map if isinstance(receipt_map, dict) else {}
    promotion_status = str(payload.get("status") or "proposal_not_promoted")
    promote_as_single_global_graph = bool(
        promotion_map.get("promote_as_single_global_graph", False)
    )
    nodes: list[dict[str, Any]] = []
    for index, seed in enumerate(json_list(payload.get("seeds"))):
        if not isinstance(seed, dict):
            continue
        seed_id = str(seed.get("id") or "").strip()
        if not seed_id:
            continue
        signal_text = scoped_seed_signal_text(seed)
        virtual_rel_path = f"{rel_path}#{seed_id}"
        seed_loads = [
            normalize_declared_load_pattern(pattern)
            for pattern in string_list(seed.get("loads"))
        ]
        routing_metadata = routing_metadata_for(virtual_rel_path, signal_text)
        routing_metadata["declared_loads"] = ordered_unique(
            string_list(routing_metadata.get("declared_loads")) + seed_loads
        )
        nodes.append(
            {
                "id": seed_id,
                "root_path": root_path,
                "path": source_path,
                "relative_path": virtual_rel_path,
                "title": str(seed.get("name") or seed_id),
                "source_type": "scoped_packet_seed",
                "source_tier": "scoped_packet_seed",
                "frontmatter": {
                    "schema": SCOPED_PACKET_SEEDS_SCHEMA,
                    "status": promotion_status,
                },
                "token_estimate": estimate_tokens(signal_text),
                "behavior_atoms": ordered_unique(
                    string_list(seed.get("behavior_atoms"))
                )[:20],
                "guidance_labels": guidance_labels_for(virtual_rel_path, signal_text),
                "keywords": sorted(text_tokens(signal_text))[:20],
                "routing_metadata": routing_metadata,
                "excerpt": signal_text[:max_excerpt_chars],
                "signal_excerpt": signal_text[:max_excerpt_chars],
                "redactions": redactions,
                "trust": "untrusted_harvested_text",
                "seed_index": index,
                "seed_id": seed_id,
                "canonical_source": rel_path,
                "source_references": string_list(seed.get("sources")),
                "loads": [pattern for pattern in seed_loads if pattern],
                "chains_before": string_list(seed.get("chains_before")),
                "chains_after": string_list(seed.get("chains_after")),
                "do_not_activate_with": string_list(seed.get("do_not_activate_with")),
                "phase_transitions": (
                    dict(seed.get("phase_transitions"))
                    if isinstance(seed.get("phase_transitions"), dict)
                    else {}
                ),
                "use_when": string_list(seed.get("use_when")),
                "route_affinity": string_list(seed.get("route_affinity")),
                "objective_patterns": string_list(seed.get("objective_patterns")),
                "modes": string_list(seed.get("modes")),
                "minimum_spec_fields": string_list(seed.get("minimum_spec_fields")),
                "ticket_types": string_list(seed.get("ticket_types")),
                "verification_expectations": string_list(
                    seed.get("verification_expectations")
                ),
                "promotion_status": promotion_status,
                "promote_as_single_global_graph": promote_as_single_global_graph,
                "required_receipts": string_list(required_receipts.get(seed_id)),
                "constraints": string_list(payload.get("constraints")),
            }
        )
    return nodes


def skill_eval_advisory_summary(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    advisories: list[dict[str, Any]] = []
    for node in nodes:
        advisories.extend(json_list(node.get("skill_eval_advisories")))
    pattern_ids = sorted(
        {
            str(item.get("pattern_id"))
            for item in advisories
            if str(item.get("pattern_id") or "").strip()
        }
    )
    return {
        "warning_count": len(advisories),
        "patterns_detected": pattern_ids,
        "policy": "advisory_only_no_auto_rewrite",
        "notes": (
            "Skill evaluation advisories warn about likely no-ops or anti-patterns. "
            "They do not mutate harvested text or promote routing state."
        ),
    }


def source_node_from_text(
    *,
    root_path: str,
    source_path: str,
    relative_path: str,
    text: str,
    max_excerpt_chars: int,
    redactions: dict[str, int],
    source_type: str,
    source_advisories: SourceAdvisories | None = None,
) -> dict[str, Any]:
    """Build one already-redacted source node without filesystem access."""

    display_path = Path(source_path)
    signal_text = positive_signal_text(text)
    node_id = hashlib.sha256(
        f"{source_path}:{hashlib.sha256(text.encode()).hexdigest()}".encode()
    ).hexdigest()[:12]
    skill_eval_advisories = (
        source_advisories(display_path, text, relative_path, source_type)
        if source_advisories is not None
        else []
    )
    node: dict[str, Any] = {
        "id": node_id,
        "root_path": root_path,
        "path": source_path,
        "relative_path": relative_path,
        "title": title_for(display_path, text),
        "source_type": source_type,
        "source_tier": source_type,
        "frontmatter": frontmatter_for(text),
        "token_estimate": estimate_tokens(text),
        "behavior_atoms": classify_atoms(text, source_type),
        "guidance_labels": guidance_labels_for(relative_path, text),
        "keywords": sorted(text_tokens(signal_text))[:20],
        "routing_metadata": routing_metadata_for(relative_path, text),
        "excerpt": text[:max_excerpt_chars],
        "signal_excerpt": signal_text[:max_excerpt_chars],
        "redactions": dict(redactions),
        "trust": "untrusted_harvested_text",
    }
    if skill_eval_advisories:
        node["skill_eval_advisories"] = skill_eval_advisories
    return node


def node_signal_text(node: dict[str, Any]) -> str:
    frontmatter_values = " ".join(
        str(value) for value in dict(node.get("frontmatter") or {}).values()
    )
    signal_excerpt = str(
        node.get("signal_excerpt")
        or positive_signal_text(str(node.get("excerpt") or ""))
    )
    signal_frontmatter = positive_signal_text(frontmatter_values)
    return " ".join(
        [
            str(node.get("title") or ""),
            str(node.get("relative_path") or ""),
            str(node.get("source_type") or ""),
            " ".join(string_list(node.get("behavior_atoms"))),
            " ".join(string_list(node.get("keywords"))),
            signal_frontmatter,
            signal_excerpt,
        ]
    ).lower()
