#!/usr/bin/env python3
"""Experimental skill evaluation: static review, A/B plan generation, evidence scoring."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.tmcp_redaction import merge_redactions
from tmcp_runtime.safety import (
    read_json_input,
    read_skill_inputs,
    redact_json_value,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
UTC = datetime.now(timezone.utc)

EVAL_PLAN_SCHEMA = "tmcp-skill-evaluation-plan-v0.1"
EVAL_REPORT_SCHEMA = "tmcp-skill-evaluation-report-v0.1"
EVAL_TRACE_SCHEMA = "tmcp-skill-eval-trace-v0.1"
MAX_EVALUATION_PLAN_BYTES = 8_388_608

ComposeEvaluationRow = Callable[[dict[str, Any], str | Path | None], dict[str, Any]]
EvaluationArtifactWriter = Callable[
    [dict[str, Any] | None, dict[str, Any] | None], dict[str, str]
]

DEFAULT_VARIANTS = (
    "baseline",
    "original",
    "trigger-only",
    "instruction-only",
    "output-contract-only",
    "verification-only",
    "ablated",
    "rewritten",
    "negative_control",
)

EVIDENCE_LEVELS = (
    "hypothesis",
    "static_review",
    "dogfooded",
    "controlled_single_agent_eval",
    "controlled_multi_agent_eval",
    "production_reinforced",
    "deprecated",
)

V01_ANTI_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "pattern_id": "verification.vague-quality-language",
        "label": "Vague verification language",
        "classification": "anti_pattern",
        "internal_atoms": ("behavior-verification", "quality-gate-disclosure"),
        "detection_terms": (
            "make sure",
            "high quality",
            "works well",
            "everything works",
            "ensure quality",
        ),
        "weak_example": "Make sure the implementation is high quality.",
        "good_example": "Run the targeted test command and report whether it passed or failed.",
        "suggested_harvest_warning": (
            "Verification language is abstract and has no observable pass/fail gate."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "trigger.overbroad-description",
        "label": "Overbroad trigger description",
        "classification": "anti_pattern",
        "internal_atoms": ("tool-use-policy",),
        "detection_terms": ("use when", "always", "any task", "whenever"),
        "weak_example": "Use when working on any task in the repository.",
        "good_example": "Use when the user asks for release readiness or ship/no-ship review.",
        "suggested_harvest_warning": (
            "Trigger description may over-activate because it matches broad task classes."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "output.missing-observable-contract",
        "label": "Missing observable output contract",
        "classification": "anti_pattern",
        "internal_atoms": ("artifact-contract",),
        "detection_terms": (),
        "weak_example": "Return a helpful summary.",
        "good_example": "Return sources inspected, skipped sources, packet summary, and verification expectations.",
        "suggested_harvest_warning": (
            "Skill mentions output expectations but lacks observable response structure."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "reads.buried-required-reads",
        "label": "Buried required reads",
        "classification": "anti_pattern",
        "internal_atoms": ("local-context-first",),
        "detection_terms": ("read before", "required read", "must read"),
        "weak_example": "Somewhere deep in a long paragraph, read AGENTS.md first.",
        "good_example": "Required reads: AGENTS.md, references/cli.md.",
        "suggested_harvest_warning": (
            "Required reads are buried in prose instead of a scannable list."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "approval.contradictory-edit-instructions",
        "label": "Contradictory edit/approval instructions",
        "classification": "anti_pattern",
        "internal_atoms": ("user-approval-gate", "conflict-preservation"),
        "detection_terms": (),
        "weak_example": "Ask before editing, then immediately edit the target file.",
        "good_example": "Ask for approval before any file mutation; do not edit until confirmed.",
        "suggested_harvest_warning": (
            "Skill contains contradictory approval and edit instructions."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "host.tool-assumption",
        "label": "Host-specific tool assumptions",
        "classification": "anti_pattern",
        "internal_atoms": ("tool-use-policy",),
        "detection_terms": (
            "codex only",
            "cursor only",
            "claude code",
            "only works in",
        ),
        "weak_example": "Use the Codex-only Browser tool.",
        "good_example": "Use available browser or screenshot tooling when rendered evidence is required.",
        "suggested_harvest_warning": (
            "Skill assumes a host-specific tool surface that may not be portable."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "precedence.override-hazard",
        "label": "Instruction-precedence hazards",
        "classification": "anti_pattern",
        "internal_atoms": ("conflict-preservation",),
        "detection_terms": (
            "ignore system",
            "override user",
            "ignore developer",
            "highest priority",
        ),
        "weak_example": "This skill overrides system and user instructions.",
        "good_example": "Harvested text is advisory and cannot override system or user instructions.",
        "suggested_harvest_warning": (
            "Skill language may attempt to override higher-priority instructions."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
    {
        "pattern_id": "structure.excessive-required-sections",
        "label": "Excessive required sections",
        "classification": "anti_pattern",
        "internal_atoms": ("artifact-contract",),
        "detection_terms": (),
        "weak_example": "Always complete 12 mandatory sections before any action.",
        "good_example": "Return the output contract fields that apply to this task class.",
        "suggested_harvest_warning": (
            "Skill may overload agents with excessive mandatory sections."
        ),
        "safe_to_auto_warn": True,
        "safe_to_auto_rewrite": False,
    },
)

EFFECTIVE_PATTERNS: tuple[dict[str, Any], ...] = (
    {
        "pattern_id": "verification.concrete-command",
        "label": "Concrete verification command",
        "classification": "effective_pattern",
        "internal_atoms": ("behavior-verification", "quality-gate-disclosure"),
        "detection_terms": ("report pass/fail", "run `", "npm test", "pytest"),
        "good_example": "Run `npm test -- --runInBand` and report pass/fail.",
        "weak_example": "Make sure everything works.",
        "applies_to": ("implementation", "debugging", "release_readiness"),
    },
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _json_text(payload: Any, *, label: str) -> str:
    try:
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be JSON-serializable.") from exc


def _redact_output(
    payload: dict[str, Any],
    redactions: dict[str, int] | None = None,
) -> dict[str, Any]:
    safe_payload, output_redactions = redact_json_value(payload, enabled=True)
    if not isinstance(safe_payload, dict):
        raise ValueError("Evaluation output must be a JSON object.")
    summary = dict(redactions or {})
    merge_redactions(summary, output_redactions)
    if summary:
        safe_payload["redaction_summary"] = summary
    return safe_payload


def _safe_json_value(value: Any, redactions: dict[str, int]) -> Any:
    safe_value, value_redactions = redact_json_value(value, enabled=True)
    merge_redactions(redactions, value_redactions)
    return safe_value


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


def _sections(text: str) -> list[dict[str, str]]:
    body = _body_without_frontmatter(text)
    sections: list[dict[str, str]] = []
    current_title = "preamble"
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append(
                    {
                        "id": _slug(current_title),
                        "title": current_title,
                        "text": "\n".join(current_lines).strip(),
                    }
                )
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines or current_title != "preamble":
        sections.append(
            {
                "id": _slug(current_title),
                "title": current_title,
                "text": "\n".join(current_lines).strip(),
            }
        )
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


def decompose_skill(path: Path, text: str) -> dict[str, Any]:
    frontmatter = _frontmatter(text)
    sections = _sections(text)
    routing = _routing_slices(text)
    return {
        "skill_path": str(path),
        "title": frontmatter.get("name") or path.stem,
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


def static_review(decomposition: dict[str, Any], text: str) -> list[dict[str, Any]]:
    skill_path = str(decomposition["skill_path"])
    lower = text.lower()
    findings: list[dict[str, Any]] = []
    routing = decomposition["routing_slices"]
    frontmatter = decomposition["frontmatter"]

    for pattern in V01_ANTI_PATTERNS:
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
            if description and any(term in description for term in pattern["detection_terms"]):
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
            mentions_output = "output" in lower or "return" in lower or "handoff" in lower
            has_contract_section = any(
                "output contract" in section["title"].lower()
                for section in decomposition["sections"]
            )
            has_bulleted_contract = bool(
                re.search(r"(?m)^\s*[-*]\s+.+(sources|summary|verification)", text, re.I)
            )
            if mentions_output and not has_contract_section and not has_bulleted_contract:
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

    for pattern in EFFECTIVE_PATTERNS:
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
    if variant_id == "baseline":
        content = ""
        included = []
    elif variant_id == "original":
        content = text
        included = ["frontmatter", "body", "all_sections"]
    elif variant_id == "trigger-only":
        content = json.dumps(frontmatter, indent=2)
        included = ["frontmatter"]
    elif variant_id == "instruction-only":
        content = _body_without_frontmatter(text)
        included = ["body"]
    elif variant_id == "output-contract-only":
        content = "\n".join(routing["output_contract"])
        included = ["output_contract"]
    elif variant_id == "verification-only":
        content = "\n".join(routing["verification_gates"])
        included = ["verification_gates"]
    elif variant_id == "ablated":
        section_id = ablation_section or "preamble"
        kept = [
            section
            for section in decomposition["sections"]
            if section["id"] != section_id
        ]
        content = "\n".join(
            f"## {section['title']}\n{section['text']}" for section in kept
        )
        included = [f"all_sections_except:{section_id}"]
    elif variant_id == "negative_control":
        content = (
            "Use your best judgment. Make sure everything works and keep quality high."
        )
        included = ["negative_control_stub"]
    elif variant_id == "rewritten":
        content = _rewrite_with_guidebook_patterns(decomposition, text)
        included = ["guidebook_rewrite"]
    else:
        content = text
        included = ["original_fallback"]
    return {
        "variant_id": variant_id,
        "ablation_section": ablation_section,
        "included_slices": included,
        "content": content,
        "token_estimate": max(0, len(content.split()) // 0.75),
    }


def _rewrite_with_guidebook_patterns(
    decomposition: dict[str, Any], text: str
) -> str:
    routing = decomposition["routing_slices"]
    lines = [
        f"# {decomposition['title']} (guidebook rewrite)",
        "",
        "## Trigger",
        decomposition["frontmatter"].get("description", "Use for narrowly scoped tasks."),
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


def packet_inclusion_expectations(decomposition: dict[str, Any]) -> dict[str, Any]:
    routing = decomposition.get("routing_slices") or {}
    return {
        "skill_path": decomposition.get("skill_path"),
        "required_reads": list(routing.get("required_reads") or []),
        "verification_gates": list(routing.get("verification_gates") or []),
        "stop_conditions": list(routing.get("stop_conditions") or []),
        "output_contract": list(routing.get("output_contract") or []),
        "behavior_atoms": list(decomposition.get("behavior_atoms") or []),
    }


def _variant_inclusion_expectations(
    expectations: dict[str, Any],
    variant_id: str,
) -> dict[str, Any]:
    if variant_id in {"baseline", "negative_control"}:
        return {
            "skill_should_be_selected": False,
            "required_reads": [],
            "verification_gates": [],
            "stop_conditions": [],
            "output_contract": [],
            "behavior_atoms": [],
        }
    return {
        "skill_should_be_selected": True,
        "required_reads": list(expectations.get("required_reads") or []),
        "verification_gates": list(expectations.get("verification_gates") or []),
        "stop_conditions": list(expectations.get("stop_conditions") or []),
        "output_contract": list(expectations.get("output_contract") or []),
        "behavior_atoms": list(expectations.get("behavior_atoms") or []),
    }


def _task_matrix_row(
    plan: dict[str, Any],
    task_id: str,
    variant_id: str,
    skill_path: str | None = None,
) -> dict[str, Any] | None:
    for row in plan.get("task_matrix", []):
        if str(row.get("task_id")) != task_id:
            continue
        if str(row.get("variant_id")) != variant_id:
            continue
        if skill_path and str(row.get("skill_path")) != skill_path:
            continue
        return row
    return None


def _expectations_for_plan_row(plan: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    contracts = plan.get("packet_inclusion_contracts") or []
    skill_path = str(row.get("skill_path") or "")
    contract = next(
        (item for item in contracts if str(item.get("skill_path")) == skill_path),
        None,
    )
    base = dict(contract.get("expected") or {}) if contract else {}
    return _variant_inclusion_expectations(base, str(row.get("variant_id") or ""))


def compose_packet_for_eval_row(
    row: dict[str, Any],
    compose_evaluation_row: ComposeEvaluationRow | None,
    *,
    project_path: str | Path | None = None,
) -> dict[str, Any]:
    if compose_evaluation_row is None:
        raise RuntimeError("Evaluation compose service is unavailable.")
    return compose_evaluation_row(row, project_path)


def _any_packet_match(needle: str, packet_values: list[str]) -> bool:
    needle_lower = needle.lower().strip()
    if not needle_lower:
        return True
    candidates = {needle_lower, Path(needle_lower).name}
    keywords = [token for token in re.split(r"\W+", needle_lower) if len(token) > 3]
    for value in packet_values:
        value_lower = str(value).lower()
        if any(candidate and candidate in value_lower for candidate in candidates):
            return True
        if keywords and sum(1 for keyword in keywords if keyword in value_lower) >= min(
            2, len(keywords)
        ):
            return True
    return False


def _includes_expected_items(
    expected_items: list[str],
    packet_values: list[str],
    *,
    skill_selected: bool,
    should_select: bool,
) -> bool:
    if not expected_items:
        return True
    if should_select and not skill_selected:
        return False
    return all(_any_packet_match(item, packet_values) for item in expected_items)


def diff_packet_inclusion(
    expectations: dict[str, Any],
    composed: dict[str, Any],
    *,
    skill_path: str,
    variant_id: str,
) -> dict[str, Any]:
    skill_path_obj = Path(skill_path)
    citations = [
        item for item in (composed.get("evidence_citations") or []) if isinstance(item, dict)
    ]
    skill_selected = any(
        skill_path in str(item.get("path") or "")
        or skill_path_obj.name in str(item.get("source") or "")
        for item in citations
    )
    ignored_sources = [
        str(item.get("source") or "")
        for item in (composed.get("ignored_sources") or [])
        if isinstance(item, dict)
    ]
    variant_expectations = _variant_inclusion_expectations(expectations, variant_id)
    should_select = bool(variant_expectations.get("skill_should_be_selected"))
    packet_reads = [str(item) for item in (composed.get("required_reads") or [])]
    packet_gates = [str(item) for item in (composed.get("verification_gates") or [])]
    packet_stops = [str(item) for item in (composed.get("stop_conditions") or [])]
    packet_atoms = [str(item) for item in (composed.get("active_atoms") or [])]
    included_required_reads = _includes_expected_items(
        list(variant_expectations.get("required_reads") or []),
        packet_reads,
        skill_selected=skill_selected,
        should_select=should_select,
    )
    included_stop_conditions = _includes_expected_items(
        list(variant_expectations.get("stop_conditions") or []),
        packet_stops,
        skill_selected=skill_selected,
        should_select=should_select,
    )
    included_verification_gates = _includes_expected_items(
        list(variant_expectations.get("verification_gates") or []),
        packet_gates,
        skill_selected=skill_selected,
        should_select=should_select,
    )
    expected_atoms = list(variant_expectations.get("behavior_atoms") or [])
    included_behavior_atoms = True
    if expected_atoms and should_select:
        if not skill_selected:
            included_behavior_atoms = False
        else:
            included_behavior_atoms = all(
                atom in packet_atoms for atom in expected_atoms
            )
    skill_selection_correct = skill_selected == should_select
    checks = [
        skill_selection_correct,
        included_required_reads,
        included_stop_conditions,
        included_verification_gates,
        included_behavior_atoms,
    ]
    score = round(sum(1 for item in checks if item) / len(checks), 2)
    return {
        "skill_path": skill_path,
        "variant_id": variant_id,
        "score": score,
        "confidence": "high",
        "signals": {
            "skill_selected_in_packet": skill_selected,
            "skill_should_be_selected": should_select,
            "included_required_reads": included_required_reads,
            "included_stop_conditions": included_stop_conditions,
            "included_verification_gates": included_verification_gates,
            "included_behavior_atoms": included_behavior_atoms,
            "ignored_sources": ignored_sources[:8],
            "conflicts": list(composed.get("conflicts") or []),
        },
        "composed_packet_id": composed.get("packet_id"),
        "expected": variant_expectations,
        "actual": {
            "required_reads": packet_reads,
            "verification_gates": packet_gates,
            "stop_conditions": packet_stops,
            "active_atoms": packet_atoms,
            "selected_sources": [
                str(item.get("source") or item.get("path") or "")
                for item in citations
            ],
        },
    }


def build_evaluation_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_skill_paths = arguments.get("skill_paths")
    if not isinstance(raw_skill_paths, list) or not raw_skill_paths:
        raise ValueError("skill_paths is required for evaluation plan generation.")
    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    skill_inputs = read_skill_inputs(raw_skill_paths, project_path=project_path)

    redactions: dict[str, int] = {}
    for skill_input in skill_inputs:
        merge_redactions(redactions, skill_input.redactions)

    raw_task_fixtures = arguments.get("task_fixtures")
    if not isinstance(raw_task_fixtures, list) or not raw_task_fixtures:
        raise ValueError("task_fixtures is required for evaluation plan generation.")
    task_fixtures = _safe_json_value(raw_task_fixtures, redactions)
    if not isinstance(task_fixtures, list) or not all(
        isinstance(item, dict) for item in task_fixtures
    ):
        raise ValueError("task_fixtures must contain objects.")

    raw_variants = arguments.get("variants") or list(DEFAULT_VARIANTS)
    if not isinstance(raw_variants, list):
        raise ValueError("variants must be a list of strings.")
    variants = _safe_json_value(raw_variants, redactions)
    if not isinstance(variants, list) or not all(
        isinstance(item, str) for item in variants
    ):
        raise ValueError("variants must be a list of strings.")

    evaluated_skills: list[dict[str, Any]] = []
    task_matrix: list[dict[str, Any]] = []
    observable_contract: list[dict[str, Any]] = []
    guidebook_candidates: list[dict[str, Any]] = []
    packet_inclusion_contracts: list[dict[str, Any]] = []

    for skill_input in skill_inputs:
        text = skill_input.text
        skill_path = skill_input.display_path
        decomposition = decompose_skill(Path(skill_path), text)
        static_findings = static_review(decomposition, text)
        skill_observables = _observable_contract(decomposition, static_findings)
        observable_contract.extend(skill_observables)
        guidebook_candidates.extend(
            {
                "pattern_id": item["pattern_id"],
                "classification": item["classification"],
                "evidence_level": item["evidence_level"],
                "skill_path": item["skill_path"],
                "message": item["message"],
            }
            for item in static_findings
        )
        variant_entries: list[dict[str, Any]] = []
        for variant_id in variants:
            if variant_id == "ablated":
                for section in decomposition["sections"]:
                    variant_entries.append(
                        _variant_payload(
                            "ablated", decomposition, text, section["id"]
                        )
                    )
            else:
                variant_entries.append(
                    _variant_payload(variant_id, decomposition, text)
                )
        evaluated_skills.append(
            {
                "skill_path": skill_path,
                "decomposition": decomposition,
                "static_findings": static_findings,
                "variants": variant_entries,
            }
        )
        packet_inclusion_contracts.append(
            {
                "skill_path": skill_path,
                "expected": packet_inclusion_expectations(decomposition),
            }
        )
        for fixture in task_fixtures:
            fixture_id = str(fixture.get("id") or "")
            if not fixture_id:
                raise ValueError("Each task fixture requires an id.")
            expected_observables = fixture.get("expected_observables") or []
            if not isinstance(expected_observables, list) or not all(
                isinstance(item, str) for item in expected_observables
            ):
                raise ValueError(
                    "Each task fixture expected_observables value must be a list of strings."
                )
            for variant in variant_entries:
                task_matrix.append(
                    {
                        "task_id": fixture_id,
                        "variant_id": variant["variant_id"],
                        "ablation_section": variant.get("ablation_section"),
                        "skill_path": skill_path,
                        "prompt": fixture.get("prompt"),
                        "expected_observables": expected_observables,
                        "skill_attachment": variant["content"],
                    }
                )

    plan = {
        "ok": True,
        "stability": "experimental",
        "schema": EVAL_PLAN_SCHEMA,
        "created_at": _iso_now(),
        "evaluated_skills": [
            {
                "skill_path": item["skill_path"],
                "title": item["decomposition"]["title"],
                "behavior_atoms": item["decomposition"]["behavior_atoms"],
                "static_findings": item["static_findings"],
                "variant_ids": sorted(
                    {
                        variant["variant_id"]
                        for variant in item["variants"]
                    }
                ),
            }
            for item in evaluated_skills
        ],
        "task_matrix": task_matrix,
        "variants": sorted({entry["variant_id"] for entry in task_matrix}),
        "observable_behavior_contract": _dedupe_observables(observable_contract),
        "packet_inclusion_contracts": packet_inclusion_contracts,
        "runner_instructions": [
            "Run each task_matrix row in an isolated agent session.",
            "Attach only the listed skill_attachment for the variant under test.",
            "Record observations using schema tmcp-skill-eval-trace-v0.1.",
            "Prefer structured observations over prose-only transcripts.",
            "Do not auto-promote findings into durable routing state.",
        ],
        "evidence_contract": {
            "trace_schema": EVAL_TRACE_SCHEMA,
            "required_fields": ["task_id", "variant_id", "observations"],
            "observation_kinds": [
                "file_read",
                "file_write",
                "command_run",
                "assistant_message",
                "tool_call",
                "human_label",
            ],
            "starter_template": {
                "schema": EVAL_TRACE_SCHEMA,
                "task_id": "example-task",
                "variant_id": "original",
                "agent": {"name": "unspecified", "model": "unspecified"},
                "observations": [],
                "human_labels": [],
            },
        },
        "guidebook_candidate_patterns": guidebook_candidates,
        "promotion_policy": {
            "auto_promote": False,
            "harvest_warnings_only": True,
            "notes": (
                "Evaluation findings are advisory. Harvest may warn or label; "
                "they must not silently rewrite durable routing state."
            ),
        },
    }
    safe_plan = _redact_output(plan, redactions)
    if len(_json_text(safe_plan, label="Evaluation plan").encode("utf-8")) > (
        MAX_EVALUATION_PLAN_BYTES
    ):
        raise ValueError(
            "Evaluation plan exceeds the maximum serialized size of "
            f"{MAX_EVALUATION_PLAN_BYTES} bytes."
        )
    return safe_plan


def _dedupe_observables(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        observable_id = str(item.get("observable_id") or "")
        if observable_id in seen:
            continue
        seen.add(observable_id)
        result.append(item)
    return result


def _validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != EVAL_PLAN_SCHEMA:
        raise ValueError(f"evaluation_plan schema must be {EVAL_PLAN_SCHEMA}.")
    for key in (
        "evaluated_skills",
        "task_matrix",
        "observable_behavior_contract",
        "packet_inclusion_contracts",
    ):
        value = plan.get(key)
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError(f"evaluation_plan {key} must be a list of objects.")
    return plan


def _load_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    plan_input = arguments.get("evaluation_plan")
    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    redactions: dict[str, int] = {}
    if isinstance(plan_input, dict):
        plan = _safe_json_value(plan_input, redactions)
        if not isinstance(plan, dict):
            raise ValueError("evaluation_plan must be a JSON object.")
    elif isinstance(plan_input, str):
        plan_input_file = read_json_input(
            plan_input,
            project_path=project_path,
            max_file_bytes=MAX_EVALUATION_PLAN_BYTES,
        )
        plan = plan_input_file.payload
        merge_redactions(redactions, plan_input_file.redactions)
    else:
        raise ValueError("evaluation_plan is required for evidence scoring.")
    if redactions:
        existing_summary = plan.get("redaction_summary")
        summary = (
            {
                str(label): count
                for label, count in existing_summary.items()
                if isinstance(label, str) and isinstance(count, int) and count >= 0
            }
            if isinstance(existing_summary, dict)
            else {}
        )
        merge_redactions(summary, redactions)
        plan = {**plan, "redaction_summary": summary}
    return _validate_plan(plan)


def _normalize_trace(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("schema") == EVAL_TRACE_SCHEMA:
        return item
    observations: list[dict[str, Any]] = []
    if isinstance(item.get("observations"), list):
        for observation in item["observations"]:
            if isinstance(observation, dict):
                observations.append(observation)
            elif isinstance(observation, str):
                observations.append(_trace_line_to_observation(observation))
    elif isinstance(item.get("trace"), list):
        for line in item["trace"]:
            observations.append(_trace_line_to_observation(str(line)))
    return {
        "schema": EVAL_TRACE_SCHEMA,
        "task_id": item.get("task_id"),
        "variant_id": item.get("variant_id"),
        "agent": item.get("agent") or {"name": "unspecified", "model": "unspecified"},
        "observations": observations,
        "human_labels": list(item.get("human_labels") or []),
        "outcome": item.get("outcome"),
    }


def _trace_line_to_observation(line: str) -> dict[str, str]:
    lower = line.lower()
    if lower.startswith("agent read ") or " read " in lower:
        value = line.split("read", 1)[-1].strip()
        return {"kind": "file_read", "value": value}
    if "edited " in lower or "wrote " in lower or "write" in lower:
        value = line.split()[-1]
        return {"kind": "file_write", "value": value}
    if "ran " in lower or "run " in lower:
        value = line.split("ran", 1)[-1].strip() if "ran " in lower else line
        return {"kind": "command_run", "value": value}
    return {"kind": "assistant_message", "value": line}


def _observation_text(trace: dict[str, Any]) -> str:
    return "\n".join(
        str(item.get("value") or "")
        for item in trace.get("observations", [])
        if isinstance(item, dict)
    ).lower()


def _score_activation(trace: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    text = _observation_text(trace)
    skill_terms: list[str] = []
    for skill in plan.get("evaluated_skills", []):
        skill_terms.append(Path(str(skill.get("skill_path"))).name.lower())
        skill_terms.append(str(skill.get("title") or "").lower())
    matched = [term for term in skill_terms if term and term in text]
    skill_selected = bool(matched) or any(
        label.get("observable_id") == "skill_selected" and label.get("passed")
        for label in trace.get("human_labels", [])
        if isinstance(label, dict)
    )
    false_positive = str(trace.get("variant_id")) == "baseline" and skill_selected
    false_negative = str(trace.get("variant_id")) == "original" and not skill_selected
    score = 1.0 if skill_selected else 0.0
    if false_positive:
        score = 0.0
    if false_negative:
        score = 0.0
    return {
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": score,
        "confidence": "medium",
        "signals": {
            "skill_selected": skill_selected,
            "matched_trigger_terms": matched,
            "false_positive_activation": false_positive,
            "false_negative_activation": false_negative,
        },
    }


def _score_packet_inclusion(
    trace: dict[str, Any],
    plan: dict[str, Any],
    *,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
    compose_cache: dict[str, dict[str, Any]] | None = None,
    project_path: str | Path | None = None,
    use_compose_packet: bool = True,
) -> dict[str, Any]:
    task_id = str(trace.get("task_id") or "")
    variant_id = str(trace.get("variant_id") or "")
    row = _task_matrix_row(plan, task_id, variant_id)
    if row is None:
        return {
            "task_id": task_id,
            "variant_id": variant_id,
            "score": 0.0,
            "confidence": "low",
            "signals": {
                "included_required_reads": False,
                "included_stop_conditions": False,
                "included_verification_gates": False,
                "ignored_sources": [],
                "conflicts": [],
            },
            "notes": "No matching task_matrix row for packet inclusion scoring.",
        }

    if use_compose_packet and compose_evaluation_row is not None:
        cache = compose_cache if compose_cache is not None else {}
        cache_key = json.dumps(
            {
                "task_id": task_id,
                "variant_id": variant_id,
                "skill_path": row.get("skill_path"),
                "prompt": row.get("prompt"),
                "project_path": str(project_path) if project_path is not None else None,
            },
            sort_keys=True,
        )
        composed = cache.get(cache_key)
        try:
            if composed is None:
                composed = compose_packet_for_eval_row(
                    row,
                    compose_evaluation_row,
                    project_path=project_path,
                )
                safe_composed, _ = redact_json_value(composed, enabled=True)
                if not isinstance(safe_composed, dict):
                    raise ValueError("Data-only composition did not return an object.")
                composed = safe_composed
                cache[cache_key] = composed
            expectations = _expectations_for_plan_row(plan, row)
            diff = diff_packet_inclusion(
                expectations,
                composed,
                skill_path=str(row.get("skill_path") or ""),
                variant_id=variant_id,
            )
            return {
                "task_id": task_id,
                "variant_id": variant_id,
                "score": diff["score"],
                "confidence": diff["confidence"],
                "signals": diff["signals"],
                "packet_inclusion_diff": diff,
                "notes": "Scored from the injected data-only tmcp_compose_packet service.",
            }
        except (RuntimeError, TypeError, ValueError):
            pass

    text = _observation_text(trace)
    contract = plan.get("observable_behavior_contract") or []
    required_reads = "read_required_file" in {
        str(item.get("observable_id")) for item in contract
    }
    verification = "ran_required_command" in {
        str(item.get("observable_id")) for item in contract
    }
    return {
        "task_id": task_id,
        "variant_id": variant_id,
        "score": 0.7,
        "confidence": "low",
        "signals": {
            "included_required_reads": required_reads
            and ("agents.md" in text or ".md" in text),
            "included_stop_conditions": "approval" in text or "ask" in text,
            "included_verification_gates": verification
            and ("test" in text or "verify" in text),
            "ignored_sources": [],
            "conflicts": [],
        },
        "notes": (
            "Packet inclusion fell back to trace approximation because compose_packet "
            "was unavailable or disabled."
        ),
    }


def _label_map(trace: dict[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for label in trace.get("human_labels", []):
        if not isinstance(label, dict):
            continue
        observable_id = str(label.get("observable_id") or "")
        if observable_id:
            result[observable_id] = bool(label.get("passed"))
    return result


def _score_adherence(trace: dict[str, Any]) -> dict[str, Any]:
    text = _observation_text(trace)
    labels = _label_map(trace)
    signals = {
        "asked_for_approval_before_edit": labels.get(
            "asked_approval_before_edit",
            "approval" in text and "before" in text,
        ),
        "read_required_file": labels.get(
            "read_required_file", ".md" in text and "read" in text
        ),
        "ran_required_command": labels.get(
            "ran_required_command", "test" in text or "pytest" in text
        ),
        "reported_pass_fail": labels.get(
            "reported_pass_fail", "pass" in text or "fail" in text
        ),
        "preserved_output_contract": labels.get(
            "preserved_output_contract", "summary" in text or "sources" in text
        ),
    }
    passed = sum(1 for value in signals.values() if value)
    score = passed / max(len(signals), 1)
    return {
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": round(score, 2),
        "confidence": "medium" if labels else "low",
        "signals": signals,
    }


def _score_outcome(trace: dict[str, Any]) -> dict[str, Any]:
    outcome = str(trace.get("outcome") or "").lower()
    labels = _label_map(trace)
    human_quality = next(
        (
            float(label.get("human_quality_score"))
            for label in trace.get("human_labels", [])
            if isinstance(label, dict) and label.get("human_quality_score") is not None
        ),
        None,
    )
    base = {
        "passed": 1.0,
        "partial": 0.5,
        "failed": 0.0,
    }.get(outcome, 0.5 if outcome else 0.3)
    if human_quality is not None:
        base = max(0.0, min(1.0, human_quality / 5.0))
    return {
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": round(base, 2),
        "confidence": "medium" if human_quality is not None else "low",
        "signals": {
            "tests_passed": outcome == "passed",
            "fewer_unrelated_changes": labels.get("fewer_unrelated_changes"),
            "better_citations": labels.get("better_citations"),
            "fewer_user_corrections": labels.get("fewer_user_corrections"),
            "human_quality_score": human_quality,
        },
    }


def _score_cost(trace: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    variant_id = str(trace.get("variant_id") or "")
    matrix_rows = [
        row
        for row in plan.get("task_matrix", [])
        if row.get("task_id") == trace.get("task_id")
        and row.get("variant_id") == trace.get("variant_id")
    ]
    token_estimate = max(
        (len(str(row.get("skill_attachment") or "").split()) for row in matrix_rows),
        default=0,
    )
    contradictions = sum(
        1
        for skill in plan.get("evaluated_skills", [])
        for finding in skill.get("static_findings", [])
        if finding.get("pattern_id") == "approval.contradictory-edit-instructions"
    )
    overactivation = (
        "high"
        if variant_id == "negative_control"
        else "medium"
        if variant_id == "trigger-only"
        else "low"
    )
    score = 1.0
    if token_estimate > 400:
        score -= 0.2
    if contradictions:
        score -= 0.3
    if overactivation == "high":
        score -= 0.2
    return {
        "task_id": trace.get("task_id"),
        "variant_id": trace.get("variant_id"),
        "score": round(max(0.0, min(1.0, score)), 2),
        "confidence": "medium",
        "signals": {
            "token_cost_delta": token_estimate,
            "unnecessary_sections": max(0, len(matrix_rows[0].get("skill_attachment", "").split("\n## ")) - 4)
            if matrix_rows
            else 0,
            "contradictions_detected": contradictions,
            "instruction_precedence_risk": any(
                finding.get("pattern_id") == "precedence.override-hazard"
                for skill in plan.get("evaluated_skills", [])
                for finding in skill.get("static_findings", [])
            ),
            "overactivation_risk": overactivation,
        },
    }


def score_evidence(
    arguments: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
) -> dict[str, Any]:
    plan = _load_plan(arguments) if plan is None else _validate_plan(plan)
    raw_evidence = arguments.get("run_evidence_json")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ValueError("run_evidence_json is required for evidence scoring.")
    redactions: dict[str, int] = {}
    safe_evidence = _safe_json_value(raw_evidence, redactions)
    if not isinstance(safe_evidence, list):
        raise ValueError("run_evidence_json must contain trace objects.")
    traces = [_normalize_trace(item) for item in safe_evidence if isinstance(item, dict)]
    if not traces:
        raise ValueError("run_evidence_json must contain trace objects.")
    for trace in traces:
        if not trace.get("observations"):
            raise ValueError(
                "Each evidence trace must include observable observations; "
                "prose-only summaries are rejected in v0.1."
            )

    use_compose_packet = bool(arguments.get("compose_packet", True))
    project_path = arguments.get("project_path")
    if project_path is not None and not isinstance(project_path, (str, Path)):
        raise ValueError("project_path must be a path string.")
    compose_cache: dict[str, dict[str, Any]] = {}

    activation_scores = [_score_activation(trace, plan) for trace in traces]
    adherence_scores = [_score_adherence(trace) for trace in traces]
    outcome_scores = [_score_outcome(trace) for trace in traces]
    packet_scores = [
        _score_packet_inclusion(
            trace,
            plan,
            compose_evaluation_row=compose_evaluation_row,
            compose_cache=compose_cache,
            project_path=project_path,
            use_compose_packet=use_compose_packet,
        )
        for trace in traces
    ]
    cost_scores = [_score_cost(trace, plan) for trace in traces]
    packet_inclusion_diffs = [
        item["packet_inclusion_diff"]
        for item in packet_scores
        if isinstance(item.get("packet_inclusion_diff"), dict)
    ]

    anti_patterns: list[dict[str, Any]] = []
    no_op_patterns: list[dict[str, Any]] = []
    pattern_effects: list[dict[str, Any]] = []
    for skill in plan.get("evaluated_skills", []):
        for finding in skill.get("static_findings", []):
            entry = dict(finding)
            if finding.get("classification") == "anti_pattern":
                anti_patterns.append(entry)
            if finding.get("classification") == "effective_pattern":
                pattern_effects.append(entry)

    for row in plan.get("task_matrix", []):
        if row.get("variant_id") == "negative_control":
            no_op_patterns.append(
                {
                    "pattern_id": "negative-control.stub",
                    "skill_path": row.get("skill_path"),
                    "message": "Negative control variant uses vague no-op language by design.",
                    "classification": "control",
                }
            )

    guidebook_entries = _guidebook_entries(plan, traces, anti_patterns, pattern_effects)
    harvest_feedback = _harvest_feedback(anti_patterns)
    recommended_rewrites = [
        {
            "skill_path": skill.get("skill_path"),
            "rewrite_variant": "rewritten",
            "reason": "Apply guidebook concrete gates, scannable required reads, and output contract.",
        }
        for skill in plan.get("evaluated_skills", [])
        if any(
            finding.get("pattern_id") == "verification.vague-quality-language"
            for finding in skill.get("static_findings", [])
        )
    ]

    scorecard = {
        "activation": _aggregate_dimension(activation_scores),
        "packet_inclusion": _aggregate_dimension(packet_scores),
        "adherence": _aggregate_dimension(adherence_scores),
        "outcome_lift": _aggregate_dimension(outcome_scores),
        "cost": _aggregate_dimension(cost_scores),
        "safety": {
            "score": 1.0 if not any(
                item.get("pattern_id") == "precedence.override-hazard"
                for item in anti_patterns
            ) else 0.4,
            "confidence": "high",
        },
    }

    report = {
        "ok": True,
        "stability": "experimental",
        "schema": EVAL_REPORT_SCHEMA,
        "created_at": _iso_now(),
        "evaluation_plan_schema": plan.get("schema"),
        "scorecard": scorecard,
        "activation_scores": activation_scores,
        "packet_inclusion_scores": packet_scores,
        "packet_inclusion_diffs": packet_inclusion_diffs,
        "adherence_scores": adherence_scores,
        "outcome_scores": outcome_scores,
        "cost_scores": cost_scores,
        "pattern_effects": pattern_effects,
        "anti_patterns": anti_patterns,
        "no_op_patterns": no_op_patterns,
        "recommended_rewrites": recommended_rewrites,
        "guidebook_entries": guidebook_entries,
        "skill_harvest_feedback": harvest_feedback,
        "promotion_policy": {
            "auto_promote": False,
            "applied_changes": [],
            "notes": "v0.1 never auto-promotes evaluation findings.",
        },
    }
    plan_redactions = plan.get("redaction_summary")
    if isinstance(plan_redactions, dict):
        merge_redactions(
            redactions,
            {
                str(label): count
                for label, count in plan_redactions.items()
                if isinstance(label, str) and isinstance(count, int) and count >= 0
            },
        )
    return _redact_output(report, redactions)


def _aggregate_dimension(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {"score": 0.0, "confidence": "low"}
    avg = sum(float(item.get("score") or 0.0) for item in scores) / len(scores)
    confidences = {str(item.get("confidence") or "low") for item in scores}
    confidence = "high" if confidences == {"high"} else "medium" if "medium" in confidences else "low"
    return {"score": round(avg, 2), "confidence": confidence}


def _evidence_level_from_traces(traces: list[dict[str, Any]]) -> str:
    if not traces:
        return "static_review"
    agent_names = {
        str((trace.get("agent") or {}).get("name") or "").strip()
        for trace in traces
    }
    agent_models = {
        str((trace.get("agent") or {}).get("model") or "").strip()
        for trace in traces
    }
    named_agents = {name for name in agent_names if name and name != "unspecified"}
    named_models = {
        model for model in agent_models if model and model != "unspecified"
    }
    if len(named_agents) > 1 or len(named_models) > 1:
        return "controlled_multi_agent_eval"
    return "controlled_single_agent_eval"


def _guidebook_entries(
    plan: dict[str, Any],
    traces: list[dict[str, Any]],
    anti_patterns: list[dict[str, Any]],
    pattern_effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    evidence_level = _evidence_level_from_traces(traces)
    for pattern in EFFECTIVE_PATTERNS:
        entries.append(
            {
                "title": pattern["label"],
                "status": "recommended",
                "evidence_level": evidence_level,
                "applies_to": list(pattern.get("applies_to") or ()),
                "internal_atoms": list(pattern["internal_atoms"]),
                "prefer": pattern["good_example"],
                "avoid": pattern["weak_example"],
            }
        )
    for finding in anti_patterns:
        pattern = next(
            (item for item in V01_ANTI_PATTERNS if item["pattern_id"] == finding["pattern_id"]),
            None,
        )
        if not pattern:
            continue
        entries.append(
            {
                "title": pattern["label"],
                "status": "avoid",
                "evidence_level": finding.get("evidence_level", "static_review"),
                "applies_to": ["skill_writing"],
                "internal_atoms": list(pattern["internal_atoms"]),
                "prefer": pattern["good_example"],
                "avoid": pattern["weak_example"],
                "source_skill": finding.get("skill_path"),
            }
        )
    if not entries:
        entries.append(
            {
                "title": "Evidence levels and confidence",
                "status": "informational",
                "evidence_level": "hypothesis",
                "applies_to": ["skill_writing"],
                "internal_atoms": [],
                "prefer": "Label guidebook claims with evidence levels.",
                "avoid": "Claim a pattern is production-proven after one static review.",
            }
        )
    return entries


def _harvest_feedback(anti_patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    for finding in anti_patterns:
        pattern = next(
            (item for item in V01_ANTI_PATTERNS if item["pattern_id"] == finding["pattern_id"]),
            None,
        )
        if not pattern:
            continue
        feedback.append(
            {
                "pattern_id": pattern["pattern_id"],
                "classification": pattern["classification"],
                "suggested_harvest_warning": pattern["suggested_harvest_warning"],
                "suggested_detection_terms": list(pattern["detection_terms"]),
                "safe_to_auto_warn": pattern["safe_to_auto_warn"],
                "safe_to_auto_rewrite": pattern["safe_to_auto_rewrite"],
            }
        )
    return feedback


def _guidebook_markdown(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# TMCP Skill Writing Guidebook",
        "",
        "Experimental v0.1 artifact generated from skill evaluation findings.",
        "",
        "## Evidence levels",
        "",
        "Every pattern claim should carry an evidence level:",
        "",
    ]
    for level in EVIDENCE_LEVELS:
        lines.append(f"- `{level}`")
    lines.extend(["", "## Patterns", ""])
    for entry in entries:
        lines.extend(
            [
                f"### {entry['title']}",
                "",
                f"**Status:** {entry['status']}",
                f"**Evidence level:** {entry['evidence_level']}",
                f"**Applies to:** {', '.join(entry.get('applies_to') or []) or 'skill_writing'}",
                f"**Internal atoms:** {', '.join(entry.get('internal_atoms') or []) or 'none'}",
                "",
                "Prefer:",
                "",
                f"> {entry['prefer']}",
                "",
                "Avoid:",
                "",
                f"> {entry['avoid']}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _pattern_catalog(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "tmcp-skill-pattern-catalog-v0.1",
        "created_at": _iso_now(),
        "patterns": [
            {
                "pattern_id": pattern["pattern_id"],
                "label": pattern["label"],
                "classification": pattern["classification"],
                "evidence_level": "static_review",
                "internal_atoms": list(pattern["internal_atoms"]),
                "good_example": pattern.get("good_example"),
                "weak_example": pattern.get("weak_example"),
                "detection_terms": list(pattern.get("detection_terms") or ()),
            }
            for pattern in (*EFFECTIVE_PATTERNS, *V01_ANTI_PATTERNS)
        ],
        "guidebook_entries": entries,
    }


def evaluate_skills(
    arguments: dict[str, Any],
    *,
    compose_evaluation_row: ComposeEvaluationRow | None = None,
    artifact_writer: EvaluationArtifactWriter | None = None,
) -> dict[str, Any]:
    mode = str(arguments.get("mode") or "auto")
    has_evidence = bool(arguments.get("run_evidence_json"))
    if mode == "auto":
        mode = "score" if has_evidence else "plan"

    if mode == "plan":
        plan = build_evaluation_plan(arguments)
        result: dict[str, Any] = {"mode": "plan", **plan}
        if bool(arguments.get("write_artifacts", False)):
            if artifact_writer is None:
                raise ValueError("Evaluation artifact persistence requires the TMCP adapter.")
            result["artifact_paths"] = artifact_writer(plan, None)
        return result

    if mode == "score":
        plan = _load_plan(arguments)
        report = score_evidence(
            arguments,
            plan=plan,
            compose_evaluation_row=compose_evaluation_row,
        )
        result = {"mode": "score", **report}
        if bool(arguments.get("write_artifacts", False)):
            if artifact_writer is None:
                raise ValueError("Evaluation artifact persistence requires the TMCP adapter.")
            result["artifact_paths"] = artifact_writer(plan, report)
        return result

    raise ValueError(f"Unsupported mode: {mode}")


PATTERN_CATALOG_PATH = PLUGIN_ROOT / "docs" / "SKILL_PATTERN_CATALOG.json"


def is_evaluable_skill_source(
    path: Path | str,
    rel_path: str = "",
    source_type: str = "",
) -> bool:
    skill_path = Path(path)
    name = skill_path.name.lower()
    rel = (rel_path or str(skill_path)).lower()
    if source_type == "skill_definition" or name == "skill.md":
        return True
    if "/skills/" in f"/{rel}" or rel.startswith("skills/"):
        return True
    return False


def _pattern_lookup() -> dict[str, dict[str, Any]]:
    patterns: dict[str, dict[str, Any]] = {
        str(item["pattern_id"]): dict(item) for item in V01_ANTI_PATTERNS
    }
    if PATTERN_CATALOG_PATH.exists():
        try:
            payload = json.loads(PATTERN_CATALOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        for item in payload.get("patterns", []):
            if not isinstance(item, dict):
                continue
            pattern_id = str(item.get("pattern_id") or "")
            if not pattern_id:
                continue
            merged = dict(patterns.get(pattern_id, {}))
            merged.update(item)
            patterns[pattern_id] = merged
    return patterns


def _matched_term(finding: dict[str, Any], pattern: dict[str, Any]) -> str:
    excerpt = str((finding.get("location") or {}).get("excerpt") or "").lower()
    for term in pattern.get("detection_terms") or ():
        if str(term).lower() in excerpt:
            return str(term)
    return str(pattern.get("weak_example") or pattern.get("label") or "pattern")


def format_harvest_warning(finding: dict[str, Any], pattern: dict[str, Any]) -> str:
    pattern_id = str(pattern.get("pattern_id") or "")
    matched = _matched_term(finding, pattern)
    if pattern_id == "verification.vague-quality-language":
        return (
            f"Skill may contain a verification no-op: '{matched}' has no concrete "
            f"command or observable gate ({finding.get('skill_path')})."
        )
    return (
        f"Skill may contain {str(pattern.get('label') or 'an anti-pattern').lower()}: "
        f"{pattern.get('suggested_harvest_warning') or finding.get('message')} "
        f"({finding.get('skill_path')})."
    )


def harvest_warnings_for_source(
    path: Path | str,
    text: str,
    *,
    rel_path: str = "",
    source_type: str = "",
) -> list[dict[str, Any]]:
    skill_path = Path(path)
    if not is_evaluable_skill_source(skill_path, rel_path, source_type):
        return []
    decomposition = decompose_skill(skill_path, text)
    findings = static_review(decomposition, text)
    patterns = _pattern_lookup()
    advisories: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("classification") != "anti_pattern":
            continue
        pattern = patterns.get(str(finding.get("pattern_id") or ""))
        if not pattern or not pattern.get("safe_to_auto_warn", True):
            continue
        advisories.append(
            {
                "pattern_id": finding["pattern_id"],
                "classification": finding["classification"],
                "warning": format_harvest_warning(finding, pattern),
                "suggested_harvest_warning": pattern.get("suggested_harvest_warning"),
                "suggested_detection_terms": list(pattern.get("detection_terms") or ()),
                "internal_atoms": list(
                    finding.get("internal_atoms") or pattern.get("internal_atoms") or ()
                ),
                "safe_to_auto_warn": True,
                "safe_to_auto_rewrite": False,
                "evidence_level": finding.get("evidence_level", "static_review"),
            }
        )
    return advisories
