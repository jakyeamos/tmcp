"""Pure applicability, dependency, rendering, and legacy projection compiler."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from tmcp_runtime.domain.behavioral_atom_registry import AtomRegistry, build_h2_registry
from tmcp_runtime.domain.behavioral_atom_types import (
    ApplicabilityResult,
    ApplicabilitySpec,
    CompileResult,
    ConflictSpec,
    DATA_INVARIANTS_ID,
    DATA_RECONCILIATION_ID,
    DomainSemantics,
    EstimatedTokenCost,
    H1_DOMAIN_IDS,
    H1_FAMILY_IDS,
    H2_DOMAIN_IDS,
    H2_FAMILY_IDS,
    INTERNAL_CONTRACT_SCHEMA,
    INTERNAL_CONTRACT_VERSION,
    MIGRATION_COMPATIBILITY_ID,
    MIGRATION_ROLLBACK_ID,
    PROCESS_CAPTURE_ID,
    PROCESS_READ_ID,
    PROCESS_STOP_ID,
    PROCESS_VERIFY_ID,
    ProvenanceTrust,
    ReadRecord,
    RenderRecord,
    RenderingBoundary,
    RequiredInput,
    RUNTIME_ATOM_SCHEMA,
    RUNTIME_ATOM_VERSION,
    RELEASE_SHIP_GATE_ID,
    SECURITY_REDACTION_ID,
    SUPPORTED_DOMAIN_IDS,
    SUPPORTED_FAMILY_IDS,
    SemanticContext,
    TypedAtom,
    _text,
    _unique,
    full_atom_id,
    normalize_atom_ref,
)

_TRUSTED_EVIDENCE = frozenset(
    {
        "committed_source_backed",
        "committed",
        "source_backed",
        "sealed_fixture",
        "trusted",
        "internal",
    }
)
_SATISFIED_STATUSES = frozenset(
    {"available", "current", "recorded", "satisfied", "verified", "passed"}
)
_VERIFICATION_STATUSES = frozenset({"passed", "satisfied", "verified", "recorded"})
_INTERNAL_VERIFICATION_STATUSES = _VERIFICATION_STATUSES | {"not_run"}


def _signal_for(atom: TypedAtom, context: SemanticContext) -> str:
    candidates: list[Any] = [
        context.semantic_signals.get(atom.full_id),
        context.semantic_signals.get(atom.stable_identity),
        context.semantic_signals.get(atom.family),
    ]
    for item in candidates:
        if isinstance(item, Mapping):
            for key in ("applicability", "decision", "status", "result"):
                if key in item:
                    item = item[key]
                    break
            else:
                if item.get("positive") is True:
                    return "positive"
                if item.get("negative") is True:
                    return "negative"
                if item.get("ambiguous") is True:
                    return "ambiguous"
                continue
        if isinstance(item, bool):
            return "positive" if item else "negative"
        normalized = _text(item).lower().replace("-", "_")
        if normalized in {"positive", "admit", "applicable", "required", "true"}:
            return "positive"
        if normalized in {"negative", "reject", "not_applicable", "false", "none"}:
            return "negative"
        if normalized in {"ambiguous", "hold", "unknown", "uncertain"}:
            return "ambiguous"
    requested = {normalize_atom_ref(item) for item in context.requested_atoms}
    if atom.full_id in requested:
        return "ambiguous"
    return "negative"


def _records_match(obligation: str, record_value: str) -> bool:
    wanted = _text(obligation).lower()
    actual = _text(record_value).lower()
    if not wanted or not actual:
        return False
    return wanted == actual or wanted in actual or actual in wanted


def _read_satisfied(
    atom: TypedAtom, context: SemanticContext
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []
    read_map = {item.reference: item for item in context.reads}
    allowed = set(context.allowed_reads)
    for required in atom.required_reads:
        matching = [
            record
            for reference, record in read_map.items()
            if _records_match(required, reference)
        ]
        if not matching:
            missing.append(f"read:{required}")
            continue
        record = matching[0]
        if allowed and not any(_records_match(required, item) for item in allowed):
            missing.append(f"authorized-read:{required}")
        if record.status.lower() not in _SATISFIED_STATUSES:
            missing.append(f"read-status:{required}")
        if record.trust and record.trust.lower() not in _TRUSTED_EVIDENCE:
            missing.append(f"read-trust:{required}")
        if not record.owner:
            missing.append(f"read-owner:{required}")
    if missing:
        reasons.append("required reads are missing, unauthorized, stale, or unowned")
    return missing, reasons


def _evidence_satisfied(
    obligations: Iterable[str], context: SemanticContext
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []
    for obligation in obligations:
        matching = [
            record
            for record in context.evidence
            if _records_match(obligation, record.obligation)
        ]
        if not matching:
            missing.append(f"evidence:{obligation}")
            continue
        record = matching[0]
        if record.status.lower() not in _SATISFIED_STATUSES:
            missing.append(f"evidence-status:{obligation}")
        if not record.source:
            missing.append(f"evidence-source:{obligation}")
        if not record.owner:
            missing.append(f"evidence-owner:{obligation}")
        if record.trust.lower() not in _TRUSTED_EVIDENCE:
            missing.append(f"evidence-trust:{obligation}")
    if missing:
        reasons.append("evidence obligations are missing or not trusted")
    return missing, reasons


def _verification_satisfied(
    obligations: Iterable[str], context: SemanticContext
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []
    for obligation in obligations:
        matching = [
            record
            for record in context.verification
            if _records_match(obligation, record.obligation)
        ]
        if not matching:
            missing.append(f"verification:{obligation}")
            continue
        record = matching[0]
        status = record.status.lower()
        if status not in _INTERNAL_VERIFICATION_STATUSES:
            missing.append(f"verification-status:{obligation}")
        if not record.owner:
            missing.append(f"verification-owner:{obligation}")
        if record.trust and record.trust.lower() not in _TRUSTED_EVIDENCE:
            missing.append(f"verification-trust:{obligation}")
    if missing:
        reasons.append("verification obligations are missing or not passed")
    return missing, reasons


def _input_satisfied(
    atom: TypedAtom, context: SemanticContext
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []
    for required in atom.required_inputs:
        value = context.inputs.get(required.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(f"input:{required.name}")
        elif isinstance(value, Mapping):
            if value.get("available") is False or value.get("status") in {
                "missing",
                "unavailable",
                "untrusted",
            }:
                missing.append(f"input-status:{required.name}")
            if not _text(value.get("owner")):
                missing.append(f"input-owner:{required.name}")
    if missing:
        reasons.append("required semantic inputs are missing or unowned")
    return missing, reasons


def _dependency_state(
    atom: TypedAtom, context: SemanticContext, registry: AtomRegistry
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []
    provided = set(context.provided_dependencies)
    selected = set(context.requested_atoms)
    for dependency in atom.dependencies:
        normalized = normalize_atom_ref(dependency)
        if normalized in provided or dependency in provided:
            continue
        dependency_atom = registry.get(normalized)
        if dependency_atom is not None and dependency_atom.kind == "process":
            # Process support is compiled into the typed boundary after the
            # domain predicate passes; it is not a domain dependency that a
            # caller can satisfy with a legacy string.
            continue
        if dependency_atom is not None and dependency_atom.full_id in selected:
            continue
        missing.append(normalized)
    if missing:
        reasons.append("typed dependency is not explicitly available")
    return missing, reasons


def _conflict_state(
    atom: TypedAtom, context: SemanticContext
) -> tuple[list[str], list[str]]:
    active = set(context.active_conflicts)
    missing: list[str] = []
    reasons: list[str] = []
    ids: list[str] = []
    for conflict in atom.conflicts:
        if conflict.stable_identity not in active and conflict.full_id not in active:
            continue
        ids.append(conflict.full_id)
        resolution = context.conflict_resolutions.get(
            conflict.full_id
        ) or context.conflict_resolutions.get(conflict.stable_identity)
        if resolution != conflict.resolution:
            missing.append(f"conflict-resolution:{conflict.full_id}")
    if missing:
        reasons.append(
            "explicit conflict resolution is absent or does not match stop policy"
        )
    return missing, reasons


def _candidate_atoms(
    context: SemanticContext, registry: AtomRegistry
) -> tuple[TypedAtom, ...]:
    requested = {normalize_atom_ref(item) for item in context.requested_atoms}
    candidates: list[TypedAtom] = []
    for atom in registry.atoms:
        if atom.is_domain:
            signal = _signal_for(atom, context)
            if signal != "negative" or atom.full_id in requested:
                candidates.append(atom)
    return tuple(candidates)


def _applicability(
    atom: TypedAtom, context: SemanticContext, registry: AtomRegistry
) -> ApplicabilityResult:
    signal = _signal_for(atom, context)
    if signal == "negative":
        return ApplicabilityResult(
            atom_id=atom.full_id,
            family=atom.family,
            decision="reject",
            status="negative",
            reasons=("explicit semantic negative or no semantic obligation",),
        )
    if signal == "ambiguous":
        ambiguous_missing = tuple(
            _unique((*context.declared_missing_evidence, *atom.stop_conditions))
        )
        return ApplicabilityResult(
            atom_id=atom.full_id,
            family=atom.family,
            decision="hold",
            status="ambiguous",
            reasons=(
                "semantic signal is ambiguous or only requested without predicate",
            ),
            missing=ambiguous_missing,
            stops=atom.stop_conditions,
            dependency_ids=atom.dependencies,
            conflict_ids=tuple(conflict.full_id for conflict in atom.conflicts),
        )

    missing: list[str] = []
    reasons: list[str] = []
    phase = context.phase.lower()
    if context.phase_status.lower() not in {"compatible", "ready", "active"}:
        missing.append("phase-status")
        reasons.append("phase is explicitly incompatible")
    if atom.allowed_phases and phase not in {
        item.lower() for item in atom.allowed_phases
    }:
        return ApplicabilityResult(
            atom_id=atom.full_id,
            family=atom.family,
            decision="reject",
            status="negative",
            reasons=(f"phase is outside atom boundary: {context.phase}",),
        )
    input_missing, input_reasons = _input_satisfied(atom, context)
    read_missing, read_reasons = _read_satisfied(atom, context)
    evidence_missing, evidence_reasons = _evidence_satisfied(
        atom.evidence_obligations, context
    )
    verification_missing, verification_reasons = _verification_satisfied(
        atom.verification_obligations, context
    )
    dependency_missing, dependency_reasons = _dependency_state(atom, context, registry)
    conflict_missing, conflict_reasons = _conflict_state(atom, context)
    missing.extend(
        (
            *input_missing,
            *read_missing,
            *evidence_missing,
            *verification_missing,
            *dependency_missing,
            *conflict_missing,
        )
    )
    reasons.extend(
        (
            *input_reasons,
            *read_reasons,
            *evidence_reasons,
            *verification_reasons,
            *dependency_reasons,
            *conflict_reasons,
        )
    )
    stops: list[str] = []
    if missing:
        stops.extend(atom.stop_conditions)
        if dependency_missing:
            stops.append(
                "dependency missing; do not substitute a generic or legacy atom"
            )
        if conflict_missing:
            stops.append("conflict unresolved; stop before execution")
    return ApplicabilityResult(
        atom_id=atom.full_id,
        family=atom.family,
        decision="admit" if not missing else "hold",
        status="positive" if not missing else "blocked",
        reasons=tuple(_unique(reasons)),
        missing=tuple(_unique(missing)),
        stops=tuple(_unique(stops)),
        dependency_ids=atom.dependencies,
        conflict_ids=tuple(conflict.full_id for conflict in atom.conflicts),
    )


def _topological_order(atoms: Iterable[TypedAtom]) -> tuple[TypedAtom, ...]:
    by_id = {atom.full_id: atom for atom in atoms}
    result: list[TypedAtom] = []
    pending = set(by_id)
    while pending:
        ready = [
            by_id[item]
            for item in pending
            if not any(dep in pending for dep in by_id[item].dependencies)
        ]
        if not ready:
            raise ValueError("typed atom dependency cycle")
        ready.sort(key=lambda atom: (atom.kind != "process", atom.family, atom.full_id))
        result.extend(ready)
        pending.difference_update(atom.full_id for atom in ready)
    return tuple(result)


def legacy_string_projection(value: object) -> dict[str, str]:
    """Project a legacy string into a separate, untrusted namespace."""

    original = _text(value)
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:16]
    return {
        "id": f"legacy.string.{digest}",
        "original": original,
        "trust": "legacy_untrusted",
        "kind": "legacy_string",
    }


def _legacy_projection(values: Iterable[str]) -> tuple[dict[str, str], ...]:
    return tuple(legacy_string_projection(value) for value in values if _text(value))


def _support_atoms(
    selected_domains: tuple[TypedAtom, ...], registry: AtomRegistry, *, blocked: bool
) -> tuple[TypedAtom, ...]:
    ids = {PROCESS_READ_ID}
    if selected_domains:
        ids.add(PROCESS_CAPTURE_ID)
    if selected_domains and not blocked:
        ids.add(PROCESS_VERIFY_ID)
    if blocked:
        ids.add(PROCESS_STOP_ID)
    atoms = tuple(atom for atom in registry.atoms if atom.stable_identity in ids)
    return _topological_order(atoms)


def compile_behavioral_atoms(
    context: SemanticContext | Mapping[str, Any],
    *,
    registry: AtomRegistry | None = None,
) -> CompileResult:
    """Compile typed atoms with fail-closed applicability and dependencies."""

    semantic_context = (
        context
        if isinstance(context, SemanticContext)
        else SemanticContext.from_mapping(context)
    )
    active_registry = registry or build_h2_registry()
    candidates = _candidate_atoms(semantic_context, active_registry)
    applicability = tuple(
        _applicability(atom, semantic_context, active_registry) for atom in candidates
    )
    positive = tuple(
        atom
        for atom, result in zip(candidates, applicability)
        if result.decision == "admit"
    )
    blocked = any(result.decision == "hold" for result in applicability)
    stops: list[str] = []
    missing: list[str] = []
    for result in applicability:
        stops.extend(result.stops)
        missing.extend(result.missing)
    support = (
        _support_atoms(positive, active_registry, blocked=blocked)
        if positive or blocked
        else ()
    )
    selected = (*support, *positive)
    selected = _topological_order(selected)
    max_cost = sum(atom.estimated_token_cost.maximum for atom in selected)
    budget = semantic_context.token_budget
    deferred: list[str] = []
    if selected and max_cost > budget:
        stops.append("budget.required_atoms_exceed_budget")
        missing.append(f"token-budget:{max_cost}>{budget}")
        selected = ()
        blocked = True
    if selected and semantic_context.optional_atoms:
        optional_ids = {
            normalize_atom_ref(item) for item in semantic_context.optional_atoms
        }
        required_ids = {atom.full_id for atom in selected}
        remaining = budget - max_cost
        optional_candidates = sorted(
            (
                atom
                for atom in active_registry.atoms
                if atom.full_id in optional_ids and atom.full_id not in required_ids
            ),
            key=lambda atom: (
                atom.estimated_token_cost.maximum,
                atom.family,
                atom.full_id,
            ),
        )
        optional_selected: list[TypedAtom] = []
        for atom in optional_candidates:
            if atom.estimated_token_cost.maximum <= remaining:
                optional_selected.append(atom)
                remaining -= atom.estimated_token_cost.maximum
            else:
                deferred.append(atom.full_id)
        selected = _topological_order((*selected, *optional_selected))
    decision = "hold_for_evidence" if blocked else ("admit" if selected else "reject")
    status = "blocked" if blocked else ("compiled" if selected else "rejected")
    if not candidates and semantic_context.requested_atoms:
        decision = "hold_for_evidence"
        status = "blocked"
        stops.append("requested typed atom is not registered in the H1/H2 slice")
        missing.extend(
            f"unregistered:{item}" for item in semantic_context.requested_atoms
        )
    if blocked:
        selected = ()
        max_cost = 0
    return CompileResult(
        schema=RUNTIME_ATOM_SCHEMA,
        version=RUNTIME_ATOM_VERSION,
        decision=decision,
        status=status,
        selected=selected,
        applicability=applicability,
        stops=_unique(stops),
        missing=_unique(missing),
        legacy_projection=_legacy_projection(semantic_context.legacy_atoms),
        total_token_cost=max_cost,
        token_budget=budget,
        deferred=_unique(deferred),
    )


def render_atoms(
    result: CompileResult,
    *,
    target: str = "packet",
    token_budget: int | None = None,
) -> CompileResult:
    """Render selected internal records into only an approved string boundary."""

    if target not in {"packet", "receipt", "advisory_trace"}:
        raise ValueError(f"Forbidden typed atom rendering target: {target}")
    budget = result.token_budget if token_budget is None else max(0, int(token_budget))
    records: list[RenderRecord] = []
    used = 0
    stops = list(result.stops)
    selected: list[TypedAtom] = []
    for atom in result.selected:
        cost = atom.estimated_token_cost.maximum
        if used + cost > budget:
            stops.append("budget.rendered_atoms_exceed_budget")
            break
        selected.append(atom)
        used += cost
        records.append(
            RenderRecord(
                atom_id=atom.full_id,
                target=target,
                text=atom.full_id,
                token_cost=cost,
            )
        )
    if len(selected) != len(result.selected):
        return CompileResult(
            schema=result.schema,
            version=result.version,
            decision="hold_for_evidence",
            status="blocked",
            selected=tuple(selected),
            applicability=result.applicability,
            stops=_unique(stops),
            missing=_unique((*result.missing, "render-token-budget")),
            legacy_projection=result.legacy_projection,
            total_token_cost=used,
            token_budget=budget,
            render_records=tuple(records),
            deferred=result.deferred,
        )
    return CompileResult(
        schema=result.schema,
        version=result.version,
        decision=result.decision,
        status=result.status,
        selected=tuple(selected),
        applicability=result.applicability,
        stops=result.stops,
        missing=result.missing,
        legacy_projection=result.legacy_projection,
        total_token_cost=used,
        token_budget=budget,
        render_records=tuple(records),
        deferred=result.deferred,
    )


def compile_typed_atoms(
    context: SemanticContext | Mapping[str, Any],
    *,
    registry: AtomRegistry | None = None,
) -> CompileResult:
    """Compatibility alias for callers that use the shorter compiler name."""

    return compile_behavioral_atoms(context, registry=registry)


compile_semantic_context = compile_behavioral_atoms
legacy_atom_projection = legacy_string_projection
render_typed_atoms = render_atoms


__all__ = [
    "ApplicabilityResult",
    "ApplicabilitySpec",
    "AtomRegistry",
    "CompileResult",
    "ConflictSpec",
    "DATA_INVARIANTS_ID",
    "DATA_RECONCILIATION_ID",
    "DomainSemantics",
    "EstimatedTokenCost",
    "H1_DOMAIN_IDS",
    "H1_FAMILY_IDS",
    "H2_DOMAIN_IDS",
    "H2_FAMILY_IDS",
    "INTERNAL_CONTRACT_SCHEMA",
    "INTERNAL_CONTRACT_VERSION",
    "MIGRATION_COMPATIBILITY_ID",
    "MIGRATION_ROLLBACK_ID",
    "PROCESS_CAPTURE_ID",
    "PROCESS_READ_ID",
    "PROCESS_STOP_ID",
    "PROCESS_VERIFY_ID",
    "ProvenanceTrust",
    "ReadRecord",
    "RenderRecord",
    "RenderingBoundary",
    "RequiredInput",
    "SemanticContext",
    "TypedAtom",
    "RUNTIME_ATOM_SCHEMA",
    "RUNTIME_ATOM_VERSION",
    "RELEASE_SHIP_GATE_ID",
    "SECURITY_REDACTION_ID",
    "SUPPORTED_DOMAIN_IDS",
    "SUPPORTED_FAMILY_IDS",
    "build_h2_registry",
    "compile_behavioral_atoms",
    "compile_semantic_context",
    "compile_typed_atoms",
    "full_atom_id",
    "legacy_atom_projection",
    "legacy_string_projection",
    "normalize_atom_ref",
    "render_atoms",
    "render_typed_atoms",
]
