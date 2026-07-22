"""Bounded, source-backed phase handoff formatting for lift campaigns.

The lift runner is an external diagnostic harness, but its phase prompt must
mirror the runtime packet boundary closely enough to test composition rather
than prompt leakage.  These helpers keep the bridge and handoff rendering
deterministic and independently testable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


DEFAULT_PHASE_ARTIFACT_LIMIT = 4000


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
            "Incoming handoff contracts:",
            handoff_contract_text(stage),
            "Entry conditions:",
            "\n".join(f"- {condition}" for condition in entry_conditions) or "- none",
            "Available fixture evidence identifiers (cite these inline; not host execution):",
            evidence_index_text(task_context),
            "Required handoff envelope headings:",
            "PHASE_RESULT; STATUS; INPUT_HANDOFF; DELIVERABLES; EVIDENCE_BOUNDARY; "
            "PRODUCED_HANDOFF; EXIT_GATE; NEXT_ENTRY; UNRESOLVED_GAPS",
        ]
    )


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
