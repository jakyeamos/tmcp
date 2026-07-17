"""Pure evaluator decomposition, variant, and static-review policy.

This module operates only on supplied text and pattern catalogs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    result: dict[str, str] = {}
    for raw_line in text[3:end].splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        clean_key = key.strip().lower()
        clean_value = value.strip().strip("\"'")
        if clean_key and clean_value:
            result[clean_key] = clean_value
    return result


def _body_without_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4 :].lstrip("\n")


def _frontmatter_block(text: str) -> str:
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    return text[: end + 4].strip()


def _sections(text: str) -> list[dict[str, str]]:
    body = _body_without_frontmatter(text)
    sections: list[dict[str, str]] = []
    id_counts: dict[str, int] = {}
    current_title = "preamble"
    current_lines: list[str] = []

    def append_section(title: str, lines: list[str]) -> None:
        base_id = _slug(title)
        occurrence = id_counts.get(base_id, 0) + 1
        id_counts[base_id] = occurrence
        section_id = base_id if occurrence == 1 else f"{base_id}-{occurrence}"
        sections.append(
            {
                "id": section_id,
                "title": title,
                "text": "\n".join(lines).strip(),
            }
        )

    for line in body.splitlines():
        if line.startswith("## "):
            if current_lines:
                append_section(current_title, current_lines)
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines or current_title != "preamble":
        append_section(current_title, current_lines)
    return sections


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "section"


def _classify_atoms(text: str) -> list[str]:
    lower = text.lower()
    atoms: set[str] = set()
    if any(term in lower for term in ("test", "verify", "validate", "quality")):
        atoms.update(("behavior-verification", "quality-gate-disclosure"))
    if any(term in lower for term in ("evidence", "source", "citation")):
        atoms.add("evidence-backed-claims")
    if any(term in lower for term in ("approval", "ask before", "do not edit")):
        atoms.add("user-approval-gate")
    if any(term in lower for term in ("output contract", "schema", "handoff")):
        atoms.add("artifact-contract")
    if any(term in lower for term in ("read", "context", "inspect")):
        atoms.add("local-context-first")
    if any(term in lower for term in ("stop", "checkpoint", "do not advance")):
        atoms.add("ordered-next-actions")
    if any(term in lower for term in ("conflict", "precedence", "override")):
        atoms.add("conflict-preservation")
    return sorted(atoms)


def _routing_slices(text: str) -> dict[str, Any]:
    lower = text.lower()
    required_reads = sorted(
        set(
            re.findall(r"(?:AGENTS\.md|references/[A-Za-z0-9_.-]+\.md)", text)
            + re.findall(r"read [`']?([A-Za-z0-9_./-]+\.md)", text, flags=re.I)
        )
    )
    stop_conditions = [
        line.strip(" -*")
        for line in text.splitlines()
        if any(
            marker in line.lower()
            for marker in ("stop", "ask the user", "approval", "checkpoint")
        )
    ][:8]
    verification_gates = [
        line.strip(" -*")
        for line in text.splitlines()
        if any(
            marker in line.lower()
            for marker in ("verify", "run ", "report pass", "pass/fail", "npm test")
        )
    ][:8]
    output_contract = [
        line.strip(" -*")
        for line in text.splitlines()
        if any(
            marker in line.lower()
            for marker in ("output contract", "return", "must include", "handoff")
        )
    ][:8]
    trigger_language = []
    frontmatter = _frontmatter(text)
    if frontmatter.get("description"):
        trigger_language.append(frontmatter["description"])
    if frontmatter.get("name"):
        trigger_language.append(frontmatter["name"])
    return {
        "trigger_language": trigger_language,
        "required_reads": required_reads,
        "stop_conditions": stop_conditions,
        "verification_gates": verification_gates,
        "output_contract": output_contract,
        "phase_hints": [
            hint
            for hint in ("implementation", "verification", "discovery", "final")
            if hint in lower
        ],
        "behavior_atoms": _classify_atoms(text),
    }


def decompose_skill(path: str, text: str) -> dict[str, Any]:
    frontmatter = _frontmatter(text)
    sections = _sections(text)
    routing = _routing_slices(text)
    path_name = str(path).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if path_name in {".", ".."} or (
        path_name.startswith(".") and path_name.count(".") == 1
    ):
        path_stem = path_name
    else:
        path_stem = path_name.rsplit(".", 1)[0] if "." in path_name else path_name
    return {
        "skill_path": str(path),
        "title": frontmatter.get("name") or path_stem,
        "frontmatter": frontmatter,
        "sections": sections,
        "routing_slices": routing,
        "behavior_atoms": routing["behavior_atoms"],
        "token_estimate": max(1, len(text.split()) // 0.75),
    }


def _paragraphs(text: str) -> list[str]:
    chunks: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        cleaned = block.strip()
        if cleaned:
            chunks.append(cleaned)
    return chunks


def _locate_excerpt(skill_path: str, text: str, needle: str) -> dict[str, str]:
    for paragraph in _paragraphs(text):
        if needle.lower() in paragraph.lower():
            return {
                "skill_path": skill_path,
                "location": "paragraph",
                "excerpt": paragraph[:400],
            }
    return {"skill_path": skill_path, "location": "document", "excerpt": text[:400]}


def static_review(
    decomposition: dict[str, Any],
    text: str,
    *,
    anti_patterns: Sequence[Mapping[str, Any]],
    effective_patterns: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    skill_path = str(decomposition["skill_path"])
    lower = text.lower()
    findings: list[dict[str, Any]] = []
    routing = decomposition["routing_slices"]
    frontmatter = decomposition["frontmatter"]

    for pattern in anti_patterns:
        pattern_id = str(pattern["pattern_id"])
        if pattern_id == "verification.vague-quality-language":
            has_vague = any(term in lower for term in pattern["detection_terms"])
            has_concrete = bool(
                re.search(r"`[^`]+`", text)
                or "report pass" in lower
                or "pass/fail" in lower
            )
            if has_vague and not has_concrete:
                needle = next(
                    term for term in pattern["detection_terms"] if term in lower
                )
                location = _locate_excerpt(skill_path, text, needle)
                findings.append(
                    {
                        "pattern_id": pattern_id,
                        "classification": pattern["classification"],
                        "evidence_level": "static_review",
                        "skill_path": skill_path,
                        "location": location,
                        "message": (
                            f"In {skill_path}, verification language is abstract and "
                            f"has no concrete command, observable condition, or pass/fail "
                            f"report requirement."
                        ),
                        "internal_atoms": list(pattern["internal_atoms"]),
                        "hypothesis": True,
                    }
                )
            continue

        if pattern_id == "trigger.overbroad-description":
            description = str(frontmatter.get("description") or "").lower()
            overbroad = bool(
                re.search(
                    r"\b(any task|all tasks|every task|always use|use for any|"
                    r"whenever (?:working on )?(?:a|any) task)\b",
                    description,
                )
            )
            if description and overbroad:
                findings.append(
                    {
                        "pattern_id": pattern_id,
                        "classification": pattern["classification"],
                        "evidence_level": "static_review",
                        "skill_path": skill_path,
                        "location": {
                            "skill_path": skill_path,
                            "location": "frontmatter.description",
                            "excerpt": frontmatter.get("description", "")[:400],
                        },
                        "message": (
                            f"In {skill_path}, the frontmatter description may "
                            f"over-activate because it uses broad trigger language."
                        ),
                        "internal_atoms": list(pattern["internal_atoms"]),
                        "hypothesis": True,
                    }
                )
            continue

        if pattern_id == "output.missing-observable-contract":
            mentions_output = (
                "output" in lower or "return" in lower or "handoff" in lower
            )
            has_contract_section = any(
                "output contract" in section["title"].lower()
                for section in decomposition["sections"]
            )
            has_bulleted_contract = bool(
                re.search(
                    r"(?m)^\s*[-*]\s+.+(sources|summary|verification)", text, re.I
                )
            )
            if (
                mentions_output
                and not has_contract_section
                and not has_bulleted_contract
            ):
                findings.append(
                    {
                        "pattern_id": pattern_id,
                        "classification": pattern["classification"],
                        "evidence_level": "static_review",
                        "skill_path": skill_path,
                        "location": {
                            "skill_path": skill_path,
                            "location": "document",
                            "excerpt": text[:400],
                        },
                        "message": (
                            f"In {skill_path}, output expectations are present but no "
                            f"observable output contract is defined."
                        ),
                        "internal_atoms": list(pattern["internal_atoms"]),
                        "hypothesis": True,
                    }
                )
            continue

        if pattern_id == "reads.buried-required-reads":
            if routing["required_reads"] and not re.search(
                r"(?im)^(required reads|## required reads)", text
            ):
                findings.append(
                    {
                        "pattern_id": pattern_id,
                        "classification": pattern["classification"],
                        "evidence_level": "static_review",
                        "skill_path": skill_path,
                        "location": _locate_excerpt(
                            skill_path, text, routing["required_reads"][0]
                        ),
                        "message": (
                            f"In {skill_path}, required reads are mentioned in prose "
                            f"instead of a scannable list."
                        ),
                        "internal_atoms": list(pattern["internal_atoms"]),
                        "hypothesis": True,
                    }
                )
            continue

        if pattern_id == "approval.contradictory-edit-instructions":
            asks_approval = any(
                term in lower
                for term in ("ask before", "approval before", "do not edit until")
            )
            immediate_edit = any(
                term in lower
                for term in ("edit immediately", "just edit", "start editing")
            )
            if asks_approval and immediate_edit:
                findings.append(
                    {
                        "pattern_id": pattern_id,
                        "classification": pattern["classification"],
                        "evidence_level": "static_review",
                        "skill_path": skill_path,
                        "location": {
                            "skill_path": skill_path,
                            "location": "document",
                            "excerpt": text[:400],
                        },
                        "message": (
                            f"In {skill_path}, approval and edit instructions contradict."
                        ),
                        "internal_atoms": list(pattern["internal_atoms"]),
                        "hypothesis": True,
                    }
                )
            continue

        if pattern_id == "host.tool-assumption":
            if any(term in lower for term in pattern["detection_terms"]):
                needle = next(
                    term for term in pattern["detection_terms"] if term in lower
                )
                findings.append(
                    {
                        "pattern_id": pattern_id,
                        "classification": pattern["classification"],
                        "evidence_level": "static_review",
                        "skill_path": skill_path,
                        "location": _locate_excerpt(skill_path, text, needle),
                        "message": (
                            f"In {skill_path}, instructions assume a host-specific tool."
                        ),
                        "internal_atoms": list(pattern["internal_atoms"]),
                        "hypothesis": True,
                    }
                )
            continue

        if pattern_id == "precedence.override-hazard":
            if any(term in lower for term in pattern["detection_terms"]):
                needle = next(
                    term for term in pattern["detection_terms"] if term in lower
                )
                findings.append(
                    {
                        "pattern_id": pattern_id,
                        "classification": pattern["classification"],
                        "evidence_level": "static_review",
                        "skill_path": skill_path,
                        "location": _locate_excerpt(skill_path, text, needle),
                        "message": (
                            f"In {skill_path}, language may attempt to override "
                            f"higher-priority instructions."
                        ),
                        "internal_atoms": list(pattern["internal_atoms"]),
                        "hypothesis": True,
                    }
                )
            continue

        if pattern_id == "structure.excessive-required-sections":
            mandatory_sections = len(
                re.findall(r"(?im)^\s*(must|always|required to)\b", text)
            )
            if mandatory_sections >= 8:
                findings.append(
                    {
                        "pattern_id": pattern_id,
                        "classification": pattern["classification"],
                        "evidence_level": "static_review",
                        "skill_path": skill_path,
                        "location": {
                            "skill_path": skill_path,
                            "location": "document",
                            "excerpt": text[:400],
                        },
                        "message": (
                            f"In {skill_path}, the skill may overload agents with "
                            f"{mandatory_sections} mandatory instruction markers."
                        ),
                        "internal_atoms": list(pattern["internal_atoms"]),
                        "hypothesis": True,
                    }
                )

    for pattern in effective_patterns:
        if any(term in lower for term in pattern["detection_terms"]):
            findings.append(
                {
                    "pattern_id": pattern["pattern_id"],
                    "classification": pattern["classification"],
                    "evidence_level": "static_review",
                    "skill_path": skill_path,
                    "location": {
                        "skill_path": skill_path,
                        "location": "document",
                        "excerpt": text[:400],
                    },
                    "message": (
                        f"In {skill_path}, concrete verification language was detected."
                    ),
                    "internal_atoms": list(pattern["internal_atoms"]),
                    "hypothesis": True,
                }
            )
    return findings


def _variant_payload(
    variant_id: str,
    decomposition: dict[str, Any],
    text: str,
    ablation_section: str | None = None,
) -> dict[str, Any]:
    frontmatter = decomposition["frontmatter"]
    routing = decomposition["routing_slices"]
    supported_variants = {
        "baseline",
        "original",
        "trigger-only",
        "instruction-only",
        "output-contract-only",
        "verification-only",
        "ablated",
        "rewritten",
        "negative_control",
    }
    if variant_id not in supported_variants:
        raise ValueError(f"Unsupported evaluation variant: {variant_id}.")

    intervention: dict[str, Any]
    if variant_id == "baseline":
        content = ""
        included = []
        intervention = {"kind": "control", "causal_attribution": True}
    elif variant_id == "original":
        content = text
        included = ["frontmatter", "body", "all_sections"]
        intervention = {"kind": "full_skill", "causal_attribution": False}
    elif variant_id == "trigger-only":
        content = _frontmatter_block(text)
        included = ["frontmatter"]
        intervention = {
            "kind": "slice_only",
            "target": "frontmatter",
            "causal_attribution": True,
        }
    elif variant_id == "instruction-only":
        content = _body_without_frontmatter(text)
        included = ["body"]
        intervention = {
            "kind": "slice_only",
            "target": "body",
            "causal_attribution": True,
        }
    elif variant_id == "output-contract-only":
        content = _minimal_variant_document(
            text,
            decomposition,
            "Output Contract",
            routing["output_contract"],
        )
        included = ["output_contract"]
        intervention = {
            "kind": "slice_only",
            "target": "output_contract",
            "causal_attribution": True,
        }
    elif variant_id == "verification-only":
        content = _minimal_variant_document(
            text,
            decomposition,
            "Verification",
            routing["verification_gates"],
        )
        included = ["verification_gates"]
        intervention = {
            "kind": "slice_only",
            "target": "verification_gates",
            "causal_attribution": True,
        }
    elif variant_id == "ablated":
        section_id = ablation_section or "preamble"
        matching = [
            section
            for section in decomposition["sections"]
            if section["id"] == section_id
        ]
        if len(matching) != 1:
            raise ValueError(
                f"Ablation section must identify exactly one section: {section_id}."
            )
        content = _render_skill_sections(
            text,
            [
                section
                for section in decomposition["sections"]
                if section["id"] != section_id
            ],
        )
        included = [f"all_sections_except:{section_id}"]
        intervention = {
            "kind": "single_section_ablation",
            "target": section_id,
            "causal_attribution": True,
        }
    elif variant_id == "negative_control":
        content = (
            "Use your best judgment. Make sure everything works and keep quality high."
        )
        included = ["negative_control_stub"]
        intervention = {"kind": "control", "causal_attribution": True}
    elif variant_id == "rewritten":
        content = _rewrite_with_guidebook_patterns(decomposition, text)
        included = ["guidebook_rewrite"]
        intervention = {
            "kind": "multi_factor_rewrite",
            "causal_attribution": False,
        }
    return {
        "variant_id": variant_id,
        "ablation_section": ablation_section,
        "included_slices": included,
        "intervention": intervention,
        "content": content,
        "token_estimate": max(0, len(content.split()) // 0.75),
    }


def _minimal_variant_document(
    text: str,
    decomposition: dict[str, Any],
    section_title: str,
    lines: Sequence[str],
) -> str:
    parts = [
        item
        for item in (
            _frontmatter_block(text),
            f"# {decomposition['title']}",
            f"## {section_title}\n" + "\n".join(lines),
        )
        if item.strip()
    ]
    return "\n\n".join(parts).strip() + "\n"


def _render_skill_sections(text: str, sections: Sequence[Mapping[str, str]]) -> str:
    body_parts: list[str] = []
    for section in sections:
        section_text = str(section.get("text") or "").strip()
        if section.get("title") == "preamble":
            if section_text:
                body_parts.append(section_text)
            continue
        rendered = f"## {section['title']}"
        if section_text:
            rendered += f"\n{section_text}"
        body_parts.append(rendered)
    parts = [item for item in (_frontmatter_block(text), "\n\n".join(body_parts)) if item]
    return "\n\n".join(parts).strip() + "\n"


def _rewrite_with_guidebook_patterns(decomposition: dict[str, Any], text: str) -> str:
    routing = decomposition["routing_slices"]
    lines = [
        f"# {decomposition['title']} (guidebook rewrite)",
        "",
        "## Trigger",
        decomposition["frontmatter"].get(
            "description", "Use for narrowly scoped tasks."
        ),
        "",
        "## Required reads",
    ]
    if routing["required_reads"]:
        lines.extend(f"- {item}" for item in routing["required_reads"])
    else:
        lines.append("- None beyond project defaults.")
    lines.extend(
        [
            "",
            "## Verification",
            "Run the targeted test or command and report pass/fail with evidence.",
            "",
            "## Output contract",
            "- Sources inspected",
            "- Skipped sources and why",
            "- Verification results",
            "- Next actions",
        ]
    )
    if "approval" in text.lower():
        lines.extend(
            [
                "",
                "## Stop conditions",
                "Ask for approval before any file mutation.",
            ]
        )
    return "\n".join(lines)


def _observable_contract(
    decomposition: dict[str, Any], static_findings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    routing = decomposition["routing_slices"]
    observables: list[dict[str, Any]] = []
    if routing["required_reads"]:
        observables.append(
            {
                "observable_id": "read_required_file",
                "description": "Agent reads a required file before acting.",
                "internal_atoms": ["local-context-first"],
            }
        )
    if any(term in json.dumps(routing).lower() for term in ("approval", "ask")):
        observables.append(
            {
                "observable_id": "asked_approval_before_edit",
                "description": "Agent asks for approval before editing.",
                "internal_atoms": ["user-approval-gate"],
            }
        )
    if routing["verification_gates"] or any(
        item["pattern_id"] == "verification.concrete-command"
        for item in static_findings
        if item["classification"] == "effective_pattern"
    ):
        observables.append(
            {
                "observable_id": "ran_required_command",
                "description": "Agent runs a named verification command.",
                "internal_atoms": ["behavior-verification"],
            }
        )
        observables.append(
            {
                "observable_id": "reported_pass_fail",
                "description": "Agent reports pass/fail for verification.",
                "internal_atoms": ["quality-gate-disclosure"],
            }
        )
    if routing["output_contract"]:
        observables.append(
            {
                "observable_id": "preserved_output_contract",
                "description": "Agent preserves the required response structure.",
                "internal_atoms": ["artifact-contract"],
            }
        )
    observables.append(
        {
            "observable_id": "skill_selected",
            "description": "Target skill activated for the task.",
            "internal_atoms": ["tool-use-policy"],
        }
    )
    return observables
