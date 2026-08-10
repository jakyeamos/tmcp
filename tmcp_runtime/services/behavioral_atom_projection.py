"""Public compatibility projection for the private typed behavioral-atom runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.behavioral_atoms import (
    CompileResult,
    SemanticContext,
    TypedAtom,
    compile_behavioral_atoms,
    legacy_string_projection,
    render_atoms,
)
from tmcp_runtime.domain.packets import render_composed_packet_markdown


INTERNAL_SEMANTIC_BUNDLE_KEY = "semantic_bundle"
PUBLIC_ATOM_CAP = 16
PUBLIC_READ_CAP = 12
PUBLIC_GATE_CAP = 10
PUBLIC_STOP_CAP = 8
PUBLIC_INSTRUCTION_CAP = 10


def semantic_bundle_from_arguments(
    arguments: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Return the explicit internal bundle, if a caller opted into it."""

    runtime_context = arguments.get("runtime_context")
    if not isinstance(runtime_context, Mapping):
        return None
    bundle = runtime_context.get(INTERNAL_SEMANTIC_BUNDLE_KEY)
    return bundle if isinstance(bundle, Mapping) else None


def _ordered_unique(values: Sequence[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _append_bounded(
    current: object,
    additions: Sequence[object],
    *,
    limit: int,
) -> tuple[list[str], list[str]]:
    existing = _ordered_unique(current if isinstance(current, list) else [])
    additions_unique = _ordered_unique(additions)
    combined = _ordered_unique((*existing, *additions_unique))
    return combined[:limit], combined[limit:]


def _atom_required_reads(atom: TypedAtom) -> list[str]:
    return list(atom.required_reads)


def _atom_verification_gates(atom: TypedAtom) -> list[str]:
    return [f"{atom.full_id}: {item}" for item in atom.verification_obligations]


def _atom_evidence_citation(atom: TypedAtom) -> dict[str, Any]:
    return {
        "source": atom.provenance_trust.source_path,
        "path": atom.provenance_trust.source_path,
        "trust": atom.provenance_trust.trust,
        "matched_atoms": [atom.full_id],
        "source_sha256": atom.provenance_trust.source_sha256,
        "projection": "internal_typed_atom_compatibility",
    }

def _merge_citations(
    packet: dict[str, Any], atoms: Sequence[TypedAtom]
) -> tuple[list[dict[str, Any]], list[str]]:
    current = packet.get("evidence_citations")
    citations = (
        [item for item in current if isinstance(item, dict)]
        if isinstance(current, list)
        else []
    )
    known: dict[str, dict[str, Any]] = {
        str(item.get("source") or item.get("path") or ""): item for item in citations
    }
    overflow: list[str] = []
    for atom in atoms:
        source = atom.provenance_trust.source_path
        existing = known.get(source)
        if existing is None:
            existing = _atom_evidence_citation(atom)
            citations.append(existing)
            known[source] = existing
        matched_value: object = existing.get("matched_atoms")
        matched = _ordered_unique(
            matched_value if isinstance(matched_value, list) else []
        )
        if atom.full_id not in matched:
            matched.append(atom.full_id)
        existing["matched_atoms"] = matched[:5]
    return citations, overflow


def _receipt_projection(
    packet: dict[str, Any], result: CompileResult, activated: Sequence[str]
) -> None:
    receipt = packet.get("receipt_template")
    if not isinstance(receipt, dict):
        return
    # These are existing v0.1 fields.  No trust policy or schema field is added.
    receipt["activated_atoms"] = list(activated)
    receipt["verification_results"] = [
        f"{item.atom_id}: selected for advisory verification"
        for item in result.render_records
    ]
    if result.stops:
        receipt["verification_results"].extend(f"STOP: {stop}" for stop in result.stops)


def project_compile_result_to_packet(
    packet: dict[str, Any], result: CompileResult
) -> dict[str, Any]:
    """Project a compiled result into only existing public string surfaces."""

    # H3 is private and advisory-trace-only.  Refuse the whole projection if a
    # caller attempts to hand a private result to the public packet boundary.
    if any(
        "packet" not in atom.rendering_boundary.renderable_to
        for atom in result.selected
    ):
        return packet
    rendered = render_atoms(result, target="packet") if result.selected else result
    existing_atoms = packet.get("active_atoms")
    legacy_from_result = [
        item.get("original")
        for item in result.legacy_projection
        if isinstance(item, dict) and item.get("original")
    ]
    legacy_atoms = _ordered_unique(
        (
            *(existing_atoms if isinstance(existing_atoms, list) else []),
            *legacy_from_result,
        )
    )
    typed_ids = [item.atom_id for item in rendered.render_records]
    projected_atoms, atom_overflow = _append_bounded(
        legacy_atoms, typed_ids, limit=PUBLIC_ATOM_CAP
    )
    packet["active_atoms"] = projected_atoms

    selected_atoms = rendered.selected
    required_reads: list[str] = []
    verification_gates: list[str] = []
    instructions: list[str] = []
    for atom in selected_atoms:
        required_reads.extend(_atom_required_reads(atom))
        verification_gates.extend(_atom_verification_gates(atom))
        instructions.append(
            f"Typed atom {atom.full_id} is advisory and requires its declared evidence boundary."
        )
    packet["required_reads"], read_overflow = _append_bounded(
        packet.get("required_reads"), required_reads, limit=PUBLIC_READ_CAP
    )
    packet["verification_gates"], gate_overflow = _append_bounded(
        packet.get("verification_gates"), verification_gates, limit=PUBLIC_GATE_CAP
    )
    packet["active_instructions"], instruction_overflow = _append_bounded(
        packet.get("active_instructions"), instructions, limit=PUBLIC_INSTRUCTION_CAP
    )
    packet["evidence_citations"], _ = _merge_citations(packet, selected_atoms)

    stops = list(result.stops)
    overflow = (*atom_overflow, *read_overflow, *gate_overflow, *instruction_overflow)
    if overflow:
        stops.append(
            "public compatibility projection would truncate required typed data"
        )
    if result.decision == "hold_for_evidence":
        stops.append(
            "typed applicability is hold_for_evidence; no domain atom was admitted"
        )
    if result.missing:
        stops.extend(f"missing: {item}" for item in result.missing)
    packet["stop_conditions"], stop_overflow = _append_bounded(
        packet.get("stop_conditions"), stops, limit=PUBLIC_STOP_CAP
    )
    if stop_overflow:
        # Preserve a deterministic visible marker if the legacy packet already
        # consumed every public stop slot.
        if packet["stop_conditions"]:
            packet["stop_conditions"][-1] = (
                "typed compatibility projection stopped; stop list at public cap"
            )

    _receipt_projection(packet, rendered, packet["active_atoms"])
    packet["packet_markdown"] = render_composed_packet_markdown(packet)
    return packet


def project_semantic_bundle_to_packet(
    packet: dict[str, Any], bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Compile and project one explicit semantic bundle.

    Existing packet atoms become legacy strings.  They are retained verbatim and
    are never used to satisfy typed dependencies or evidence obligations.
    """

    raw = dict(bundle)
    if "legacy_atoms" not in raw:
        raw["legacy_atoms"] = list(packet.get("active_atoms") or [])
    context = SemanticContext.from_mapping(raw)
    result = compile_behavioral_atoms(context)
    return project_compile_result_to_packet(packet, result)


def project_legacy_atoms(values: Sequence[object]) -> list[dict[str, str]]:
    """Expose the internal legacy normalization for static compatibility tests."""

    return [legacy_string_projection(value) for value in values if str(value).strip()]


def static_projection_summary(result: CompileResult) -> dict[str, Any]:
    """Return JSON-safe advisory data without provider or filesystem effects."""

    return {
        "schema": result.schema,
        "version": result.version,
        "decision": result.decision,
        "status": result.status,
        "selected_ids": list(result.selected_ids),
        "domain_selected_ids": list(result.domain_selected_ids),
        "stops": list(result.stops),
        "missing": list(result.missing),
        "legacy_projection": list(result.legacy_projection),
        "total_token_cost": result.total_token_cost,
        "token_budget": result.token_budget,
    }
