"""Variant construction and observable contracts for skill evaluation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


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


def _variant_payload(
    variant_id: str,
    decomposition: dict[str, Any],
    text: str,
    ablation_section: str | None = None,
) -> dict[str, Any]:
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
            "kind": "routing_projection",
            "target": "frontmatter",
            "causal_attribution": False,
            "confounders": ["forced_attachment_bypasses_host_routing"],
        }
    elif variant_id == "instruction-only":
        content = _body_without_frontmatter(text)
        included = ["body"]
        intervention = {
            "kind": "slice_projection",
            "target": "body",
            "causal_attribution": False,
            "confounders": ["multi_instruction_body"],
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
            "kind": "slice_projection",
            "target": "output_contract",
            "causal_attribution": False,
            "confounders": ["frontmatter", "document_scaffold"],
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
            "kind": "slice_projection",
            "target": "verification_gates",
            "causal_attribution": False,
            "confounders": ["frontmatter", "document_scaffold"],
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
        content = _remove_section_losslessly(
            text, decomposition["sections"], section_id
        )
        included = [f"all_sections_except:{section_id}"]
        if content is None:
            content = _render_skill_sections(
                text,
                [
                    section
                    for section in decomposition["sections"]
                    if section["id"] != section_id
                ],
            )
            intervention = {
                "kind": "single_section_ablation",
                "target": section_id,
                "causal_attribution": False,
                "confounders": ["non_lossless_section_render"],
            }
        else:
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
    else:
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
    parts = [
        item for item in (_frontmatter_block(text), "\n\n".join(body_parts)) if item
    ]
    return "\n\n".join(parts).strip() + "\n"


def _remove_section_losslessly(
    text: str,
    sections: Sequence[Mapping[str, str]],
    section_id: str,
) -> str | None:
    body_start = 0
    if text.startswith("---"):
        frontmatter_end = text.find("\n---", 3)
        if frontmatter_end == -1:
            return None
        body_start = frontmatter_end + 4
    raw_body = text[body_start:]
    body = raw_body.lstrip("\n")
    body_start += len(raw_body) - len(body)
    headings = list(re.finditer(r"(?m)^## [^\r\n]*$", body))
    spans: list[tuple[str, str, int, int]] = []
    section_index = 0
    if not headings:
        if body and len(sections) == 1:
            section = sections[0]
            spans.append(
                (
                    str(section.get("id") or ""),
                    str(section.get("title") or ""),
                    0,
                    len(body),
                )
            )
    else:
        if headings[0].start() > 0:
            if not sections:
                return None
            section = sections[0]
            spans.append(
                (
                    str(section.get("id") or ""),
                    str(section.get("title") or ""),
                    0,
                    headings[0].start(),
                )
            )
            section_index = 1
        for heading_index, heading in enumerate(headings):
            if section_index >= len(sections):
                return None
            section = sections[section_index]
            title = heading.group(0)[3:].strip()
            if title != str(section.get("title") or ""):
                return None
            end = (
                headings[heading_index + 1].start()
                if heading_index + 1 < len(headings)
                else len(body)
            )
            spans.append(
                (
                    str(section.get("id") or ""),
                    title,
                    heading.start(),
                    end,
                )
            )
            section_index += 1
    if len(spans) != len(sections):
        return None
    matching = [span for span in spans if span[0] == section_id]
    if len(matching) != 1:
        return None
    _, _, start, end = matching[0]
    absolute_start = body_start + start
    absolute_end = body_start + end
    return text[:absolute_start] + text[absolute_end:]


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
        observables.extend(
            [
                {
                    "observable_id": "ran_required_command",
                    "description": "Agent runs a named verification command.",
                    "internal_atoms": ["behavior-verification"],
                },
                {
                    "observable_id": "reported_pass_fail",
                    "description": "Agent reports pass/fail for verification.",
                    "internal_atoms": ["quality-gate-disclosure"],
                },
            ]
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
