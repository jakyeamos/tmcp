"""Bounded, source-backed phase handoff formatting for lift campaigns.

The lift runner is an external diagnostic harness, but its phase prompt must
mirror the runtime packet boundary closely enough to test composition rather
than prompt leakage.  These helpers keep the bridge and handoff rendering
deterministic and independently testable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence


DEFAULT_PHASE_ARTIFACT_LIMIT = 4000
# Keep cumulative handoffs below the lift-campaign contract's 16,000-character
# artifact ceiling while leaving room for serialization and validation metadata.
DEFAULT_COMPOSITION_HANDOFF_LIMIT = 15_000
DEFAULT_COMPOSITION_INDEX_DELIVERABLE_LIMIT = 300
DEFAULT_COMPOSITION_INDEX_HANDOFF_LIMIT = 180
DEFAULT_COMPOSITION_PRIOR_CAPSULE_LIMIT = 650
DEFAULT_COMPOSITION_CURRENT_CAPSULE_LIMIT = 3_200
_PHASE_HEADINGS = (
    "PHASE_RESULT",
    "STATUS",
    "INPUT_HANDOFF",
    "DELIVERABLES",
    "EVIDENCE_BOUNDARY",
    "PRODUCED_HANDOFF",
    "EXIT_GATE",
    "NEXT_ENTRY",
    "UNRESOLVED_GAPS",
)
_PHASE_HEADING_RE = re.compile(
    rf"^({'|'.join(map(re.escape, _PHASE_HEADINGS))})(?::\s*(.*))?$"
)
_SECTION_BUDGETS = {
    "PHASE_RESULT": 220,
    "STATUS": 140,
    "INPUT_HANDOFF": 320,
    "DELIVERABLES": 720,
    "EVIDENCE_BOUNDARY": 300,
    "PRODUCED_HANDOFF": 720,
    "EXIT_GATE": 600,
    "NEXT_ENTRY": 260,
    "UNRESOLVED_GAPS": 440,
}
_CAPSULE_SECTION_BUDGETS = {
    "PHASE_RESULT": 140,
    "STATUS": 100,
    "DELIVERABLES": 320,
    "EVIDENCE_BOUNDARY": 140,
    "PRODUCED_HANDOFF": 220,
    "EXIT_GATE": 180,
    "NEXT_ENTRY": 180,
    "UNRESOLVED_GAPS": 240,
}


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _text(value: object) -> str:
    return str(value or "").strip()


def _strings(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [_text(item) for item in value if _text(item)]


def _source_contract_lines(source: str) -> list[str]:
    """Extract the bounded output contract without inventing semantics."""

    lines = source.splitlines()
    contract_start = next(
        (
            index + 1
            for index, line in enumerate(lines)
            if _text(line).casefold() == "output contract:"
        ),
        None,
    )
    if contract_start is None:
        return []
    result: list[str] = []
    for line in lines[contract_start:]:
        normalized = _text(line)
        if not normalized:
            if result:
                break
            continue
        if normalized.endswith(":") and not normalized.startswith(("-", "*")):
            break
        result.append(normalized)
    return result[:8]


def phase_contract_text(
    stage: Mapping[str, object],
    stage_skill_ids: Sequence[str],
    sources: Mapping[str, str],
) -> str:
    """Render the active phase's typed role and source output contracts."""

    lines: list[str] = []
    for skill_id in stage_skill_ids:
        body = str(sources.get(skill_id) or "")
        source_lines = body.splitlines()
        typed = {
            "inputs": next(
                (
                    _text(line)[len("Inputs:") :].strip()
                    for line in source_lines
                    if _text(line).startswith("Inputs:")
                ),
                "",
            ),
            "outputs": next(
                (
                    _text(line)[len("Outputs:") :].strip()
                    for line in source_lines
                    if _text(line).startswith("Outputs:")
                ),
                "",
            ),
            "exit_gate": next(
                (
                    _text(line)[len("Exit gate:") :].strip()
                    for line in source_lines
                    if _text(line).startswith("Exit gate:")
                ),
                "",
            ),
        }
        lines.append(f"Role source: {skill_id}")
        if typed["inputs"]:
            lines.append(f"  typed inputs: {typed['inputs']}")
        if typed["outputs"]:
            lines.append(f"  typed output: {typed['outputs']}")
        if typed["exit_gate"]:
            lines.append(f"  typed exit gate: {typed['exit_gate']}")
        for contract_line in _source_contract_lines(body):
            lines.append(f"  source contract: {contract_line}")
    if not lines:
        lines.append(
            "No active source contract is available; report this phase as BLOCKED."
        )
    return "\n".join(lines)


def handoff_contract_text(stage: Mapping[str, object]) -> str:
    """Render structured incoming contracts, including provenance citations."""

    raw_contracts = stage.get("handoff_contracts")
    if not isinstance(raw_contracts, Sequence) or isinstance(
        raw_contracts, (str, bytes)
    ):
        return "- none"
    lines: list[str] = []
    for raw in raw_contracts:
        contract = _mapping(raw)
        if contract is None:
            continue
        producer = _text(contract.get("producer_node_id")) or "unknown producer"
        consumer = _text(contract.get("consumer_node_id")) or "unknown consumer"
        relation = _text(contract.get("relationship_type")) or "handoff"
        required = ", ".join(_strings(contract.get("required_inputs"))) or "none"
        produced = ", ".join(_strings(contract.get("produced_outputs"))) or "none"
        gates = ", ".join(_strings(contract.get("producer_exit_gates"))) or "none"
        citations = ", ".join(_strings(contract.get("citations"))) or "none"
        handoff_id = _text(contract.get("handoff_id")) or "unidentified"
        lines.append(
            f"- {handoff_id}: {producer} {relation} {consumer}; "
            f"required input={required}; produced output={produced}; "
            f"producer exit gate={gates}; citations={citations}"
        )
    return "\n".join(lines) if lines else "- none"


def bridge_obligation_text(stage: Mapping[str, object]) -> str:
    """Render the active bridge as explicit typed obligations."""

    raw_bridges = stage.get("bridge_instructions")
    if not isinstance(raw_bridges, Sequence) or isinstance(
        raw_bridges, (str, bytes)
    ):
        return "- none"
    lines: list[str] = []
    for raw in raw_bridges:
        bridge = _mapping(raw)
        if bridge is None:
            continue
        role = _text(bridge.get("role")) or "active role"
        required = ", ".join(_strings(bridge.get("required_inputs"))) or "none"
        produced = ", ".join(_strings(bridge.get("produced_outputs"))) or "none"
        criteria = ", ".join(_strings(bridge.get("covered_criteria"))) or "none"
        gates = ", ".join(_strings(bridge.get("exit_gates"))) or "none"
        citations = ", ".join(_strings(bridge.get("citations"))) or "none"
        lines.append(
            f"- {role}: required input={required}; produced handoff={produced}; "
            f"cover criterion={criteria}; exit gate={gates}; citations={citations}"
        )
    return "\n".join(lines) if lines else "- none"


def evidence_index_text(task_context: Mapping[str, object]) -> str:
    """Expose only fixture evidence identifiers and provenance labels."""

    evidence = task_context.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return "- none supplied"
    lines: list[str] = []
    for raw in evidence:
        item = _mapping(raw)
        if item is None:
            continue
        evidence_id = _text(item.get("evidence_id"))
        kind = _text(item.get("kind"))
        provenance = _text(item.get("provenance")) or "unspecified"
        if evidence_id:
            lines.append(f"- {evidence_id} ({kind or 'evidence'}; {provenance})")
    return "\n".join(lines) if lines else "- none supplied"


def phase_handoff_requirements(
    stage: Mapping[str, object],
    stage_skill_ids: Sequence[str],
    sources: Mapping[str, str],
    task_context: Mapping[str, object],
) -> str:
    """Return a compact directive for a phase worker's complete handoff."""

    entry_conditions = _strings(stage.get("entry_conditions"))
    return "\n".join(
        [
            "Typed phase contract (source-backed; satisfy this phase before downstream work):",
            phase_contract_text(stage, stage_skill_ids, sources),
            "Current bridge obligations (source-backed; do not omit these handoff fields):",
            bridge_obligation_text(stage),
            "Incoming handoff contracts:",
            handoff_contract_text(stage),
            "Entry conditions:",
            "\n".join(f"- {condition}" for condition in entry_conditions) or "- none",
            "Available fixture evidence identifiers (cite these inline; not host execution):",
            evidence_index_text(task_context),
            "Required handoff envelope headings:",
            "PHASE_RESULT; STATUS; INPUT_HANDOFF; DELIVERABLES; EVIDENCE_BOUNDARY; "
            "PRODUCED_HANDOFF; EXIT_GATE: PASS|FAIL|BLOCKED; NEXT_ENTRY; "
            "UNRESOLVED_GAPS",
        ]
    )


def _compact_text(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    marker = "\n[section body elided]\n"
    if budget <= len(marker) + 2:
        return text[:budget]
    available = budget - len(marker)
    head_limit = available // 2
    tail_limit = available - head_limit
    return text[:head_limit].rstrip() + marker + text[-tail_limit:].lstrip()


def _phase_sections(artifact: str) -> tuple[str, list[tuple[str, str, str]]]:
    preamble: list[str] = []
    sections: list[tuple[str, str, str]] = []
    current_heading = ""
    current_suffix = ""
    current_body: list[str] = []
    for line in artifact.splitlines():
        match = _PHASE_HEADING_RE.match(line.strip())
        if match:
            if current_heading:
                sections.append(
                    (current_heading, current_suffix, "\n".join(current_body).strip())
                )
            current_heading = match.group(1)
            current_suffix = str(match.group(2) or "").strip()
            current_body = []
        elif current_heading:
            current_body.append(line)
        else:
            preamble.append(line)
    if current_heading:
        sections.append(
            (current_heading, current_suffix, "\n".join(current_body).strip())
        )
    return "\n".join(preamble).strip(), sections


def phase_exit_gate_status(artifact: str) -> str:
    """Return the first machine-readable exit-gate status from a phase artifact."""

    _preamble, sections = _phase_sections(artifact)
    for heading, suffix, body in sections:
        if heading != "EXIT_GATE":
            continue
        candidate = suffix or body
        match = re.search(r"\b(PASS|FAIL|BLOCKED)\b", candidate, re.IGNORECASE)
        if match:
            return match.group(1).casefold()
    return "unknown"


def phase_deliverable_index(
    phase_artifacts: Sequence[tuple[Mapping[str, object], str]],
    *,
    deliverable_limit: int = 420,
    handoff_limit: int = 260,
) -> str:
    """Quote each phase's concrete deliverable and produced handoff."""

    lines = [
        "# Composition deliverable index",
        "This index quotes the phase handoffs below; it adds no execution evidence.",
    ]
    for index, (stage, artifact) in enumerate(phase_artifacts, 1):
        _preamble, sections = _phase_sections(artifact)
        bodies = {heading: body for heading, _suffix, body in sections}
        phase = _text(stage.get("phase")) or "unknown"
        gate = phase_exit_gate_status(artifact).upper()
        deliverables = _compact_text(
            bodies.get("DELIVERABLES", "") or "- none", deliverable_limit
        )
        handoff = _compact_text(
            bodies.get("PRODUCED_HANDOFF", "") or "- none", handoff_limit
        )
        lines.append(
            f"- phase {index} {phase} | gate={gate} | "
            f"deliverable: {deliverables} | handoff: {handoff}"
        )
    return "\n".join(lines)


def _phase_capsule(artifact: str, *, limit: int) -> str:
    """Keep prior-phase decisions without replaying every incoming detail."""

    preamble, sections = _phase_sections(artifact)
    wanted = tuple(_CAPSULE_SECTION_BUDGETS)
    selected: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for heading, suffix, body in sections:
        if heading in wanted and heading not in seen:
            selected.append((heading, suffix, body))
            seen.add(heading)
    if not selected:
        return _compact_text(artifact.strip(), limit)
    return _bounded_phase_sections(
        preamble,
        selected,
        limit=limit,
        section_budgets=_CAPSULE_SECTION_BUDGETS,
    )


def render_composition_handoff(
    phase_artifacts: Sequence[tuple[Mapping[str, object], str]],
    *,
    limit: int = DEFAULT_COMPOSITION_HANDOFF_LIMIT,
) -> str:
    """Render a bounded phase-aware handoff without replaying prior contexts."""

    sections = [
        phase_deliverable_index(
            phase_artifacts,
            deliverable_limit=DEFAULT_COMPOSITION_INDEX_DELIVERABLE_LIMIT,
            handoff_limit=DEFAULT_COMPOSITION_INDEX_HANDOFF_LIMIT,
        ),
        "# Phase-aware composition handoff",
        "Each section is a handoff from a fresh isolated phase context. "
        "Fixture-supplied evidence is not host execution. Prior phases are "
        "represented by quote-only capsules; the current phase retains its "
        "complete bounded envelope.",
    ]
    last_index = len(phase_artifacts) - 1
    for index, (stage, artifact) in enumerate(phase_artifacts, 1):
        if index - 1 == last_index:
            body = bound_phase_artifact(
                artifact,
                limit=DEFAULT_COMPOSITION_CURRENT_CAPSULE_LIMIT,
            )
        else:
            body = _phase_capsule(
                artifact,
                limit=DEFAULT_COMPOSITION_PRIOR_CAPSULE_LIMIT,
            )
        sections.append(
            f"## Phase {index}: {stage.get('phase')} ({stage.get('status')})\n{body}"
        )
    rendered = "\n\n".join(sections)
    if len(rendered) <= limit:
        return rendered
    # Small caller-supplied limits are diagnostic bounds. Preserve the index,
    # phase headings, and the current phase's gate before compacting the body.
    compacted = _compact_text(rendered, limit)
    return compacted[:limit]


def _bounded_phase_sections(
    preamble: str,
    sections: list[tuple[str, str, str]],
    *,
    limit: int,
    section_budgets: Mapping[str, int] | None = None,
) -> str:
    fixed_parts = [
        (heading + (f": {suffix}" if suffix else ""))
        for heading, suffix, _body in sections
    ]
    fixed_length = (
        sum(len(part) for part in fixed_parts)
        + sum(1 for _heading, _suffix, body in sections if body)
        + max(0, (len(fixed_parts) - 1) * 2)
    )
    preamble_budget = min(len(preamble), 160) if preamble else 0
    if preamble_budget:
        fixed_length += preamble_budget + 2
    available = max(0, limit - fixed_length)
    desired = [
        (section_budgets or _SECTION_BUDGETS).get(heading, 280)
        for heading, _suffix, _body in sections
    ]
    minimum = 16 * len(sections)
    if available < minimum:
        return ""
    budgets = [min(value, available) for value in desired]
    while sum(budgets) > available:
        index = max(range(len(budgets)), key=lambda item: budgets[item])
        if budgets[index] <= 16:
            break
        budgets[index] -= 1
    parts: list[str] = []
    if preamble:
        parts.append(_compact_text(preamble, preamble_budget))
    for (heading, suffix, body), budget in zip(sections, budgets, strict=True):
        title = heading + (f": {suffix}" if suffix else "")
        parts.append(title if not body else f"{title}\n{_compact_text(body, budget)}")
    return "\n\n".join(parts)


def bound_phase_artifact(
    artifact: str, *, limit: int = DEFAULT_PHASE_ARTIFACT_LIMIT
) -> str:
    """Bound an artifact while retaining both deliverables and exit gates."""

    normalized = artifact.strip()
    if len(normalized) <= limit:
        return normalized
    if limit < 200:
        raise ValueError("phase artifact limit must leave room for a handoff")
    marker = "\n\n[phase handoff body elided by bounded runner]\n\n"
    available = limit - len(marker)
    if available < 2:
        raise ValueError("phase artifact limit is too small for the elision marker")
    preamble, sections = _phase_sections(normalized)
    if sections:
        bounded = _bounded_phase_sections(
            preamble,
            sections,
            limit=limit,
        )
        if bounded and len(bounded) <= limit:
            return bounded
    head_limit = available // 2
    tail_limit = available - head_limit
    head = normalized[:head_limit].rstrip()
    tail = normalized[-tail_limit:].lstrip()
    if "EXIT_GATE" in normalized and "EXIT_GATE" not in tail:
        exit_line = next(
            (line.strip() for line in normalized.splitlines() if "EXIT_GATE" in line),
            "EXIT_GATE: UNRESOLVED",
        )
        reserved_tail = max(0, tail_limit - len(exit_line) - 1)
        tail = exit_line + ("\n" + tail[:reserved_tail] if reserved_tail else "")
    result = head + marker + tail
    return result[:limit]
