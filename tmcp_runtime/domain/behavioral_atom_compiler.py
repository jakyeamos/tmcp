"""Pure applicability, dependency, rendering, and legacy projection compiler."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from tmcp_runtime.domain.behavioral_atom_registry import (
    AtomRegistry,
    build_h2_registry,
)
from tmcp_runtime.domain.behavioral_atom_renderer import render_atoms
from tmcp_runtime.domain.behavioral_atom_types import (
    ApplicabilityResult,
    CompileResult,
    H3_DOMAIN_IDS,
    PROCESS_CAPTURE_ID,
    PROCESS_READ_ID,
    PROCESS_STOP_ID,
    PROCESS_VERIFY_ID,
    RUNTIME_ATOM_SCHEMA,
    RUNTIME_ATOM_VERSION,
    SECURITY_SECRET_BOUNDARY_ID,
    SemanticContext,
    TypedAtom,
    _text,
    _unique,
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
_H3_TRUSTED_EVIDENCE = frozenset({"committed_source_backed", "sealed_fixture"})
_H3_INVALID_MARKERS = frozenset(
    {
        "ambiguous",
        "blocked",
        "inferred",
        "incomplete",
        "missing",
        "partial",
        "stale",
        "unknown",
        "unavailable",
        "unowned",
        "untrusted",
        "unverified",
    }
)
_H3_NEGATIVE_MARKERS = frozenset(
    {
        "decision_only",
        "generic_process",
        "no_boundary",
        "no_release",
        "no_scope",
        "output_transformation",
        "process_only",
        "redaction_only",
    }
)
_H3_BAD_INPUT_STATUSES = frozenset(
    {
        "ambiguous",
        "blocked",
        "incomplete",
        "missing",
        "partial",
        "stale",
        "unknown",
        "unavailable",
        "untrusted",
    }
)


def _signal_for(atom: TypedAtom, context: SemanticContext) -> str:
    h3 = atom.stable_identity in H3_DOMAIN_IDS
    keys = (
        [atom.full_id, atom.stable_identity, atom.stable_identity.rsplit(".", 1)[-1]]
        if h3
        else [atom.full_id, atom.stable_identity, atom.family]
    )
    for item in (context.semantic_signals.get(key) for key in keys):
        if isinstance(item, Mapping):
            item = next(
                (
                    item[key]
                    for key in ("applicability", "decision", "status", "result")
                    if key in item
                ),
                "positive"
                if item.get("positive") is True
                else "negative"
                if item.get("negative") is True
                else "ambiguous"
                if item.get("ambiguous") is True
                else "",
            )
        if isinstance(item, bool):
            return "positive" if item else "negative"
        normalized = _text(item).lower().replace("-", "_")
        if normalized in {"positive", "admit", "applicable", "required", "true"}:
            return "positive"
        if normalized in {"negative", "reject", "not_applicable", "false", "none"}:
            return "negative"
        if normalized in {"ambiguous", "hold", "unknown", "uncertain"}:
            return "ambiguous"
        if h3 and normalized:
            if any(marker in normalized for marker in _H3_NEGATIVE_MARKERS):
                return "negative"
            if any(marker in normalized for marker in _H3_INVALID_MARKERS):
                return "ambiguous"
            positive_markers = (
                ("authorized_scope", "authorized_artifact", "boundary_evidence")
                if atom.stable_identity == SECURITY_SECRET_BOUNDARY_ID
                else ("quality_ladder", "complete_fresh", "evidence_ladder")
            )
            if any(marker in normalized for marker in positive_markers):
                return "positive"
            return "ambiguous"
    requested = {normalize_atom_ref(item) for item in context.requested_atoms}
    if atom.full_id in requested:
        return "ambiguous"
    return "negative"


_RECORD_ALIASES = {
    "boundaries": "boundary",
    "covered": "cover",
    "covers": "cover",
    "gates": "gate",
    "mapping": "record",
    "mapped": "record",
    "recorded": "record",
    "records": "record",
    "states": "state",
    "used": "use",
    "uses": "use",
}


def _record_tokens(value: str) -> set[str]:
    parts = value.replace("/", " ").replace("-", " ").split()
    return {
        _RECORD_ALIASES.get(token.strip(".,;:!?()[]{}"), token.strip(".,;:!?()[]{}"))
        for token in parts
        if token.strip(".,;:!?()[]{}")
    }


def _records_match(obligation: str, record_value: str) -> bool:
    wanted, actual = _text(obligation).lower(), _text(record_value).lower()
    if not wanted or not actual:
        return False
    if wanted == actual or wanted in actual or actual in wanted:
        return True
    expected, observed = _record_tokens(wanted), _record_tokens(actual)
    overlap = expected & observed
    if len(overlap) >= 2 and len(overlap) * 2 >= min(len(expected), len(observed)):
        return True
    if {"gate", "state"}.issubset(
        expected | observed
    ) and "gate" in expected & observed:
        return True
    if "boundary" in expected & observed and (
        {"security", "privacy", "auth", "data", "flow"} & (expected | observed)
    ):
        return True
    return {"auth", "data", "flow"}.issubset(observed) and bool(
        {"security", "privacy", "auth"} & expected
    )


def _is_h3(atom: TypedAtom) -> bool:
    return atom.stable_identity in H3_DOMAIN_IDS


def _trusted_record(atom: TypedAtom, trust: str, *, required: bool) -> bool:
    normalized = _text(trust).lower()
    if not normalized:
        return not required
    allowed = _H3_TRUSTED_EVIDENCE if _is_h3(atom) else _TRUSTED_EVIDENCE
    return normalized in allowed


def _contains_h3_invalid_marker(value: object) -> bool:
    normalized = _text(value).lower().replace("-", "_")
    return bool(normalized) and any(
        marker in normalized for marker in _H3_INVALID_MARKERS
    )


def _read_satisfied(
    atom: TypedAtom, context: SemanticContext
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []
    read_map = {item.reference: item for item in context.reads}
    allowed = set(context.allowed_reads)
    for required in atom.required_reads:
        record = next((record for reference, record in read_map.items() if _records_match(required, reference)), None)  # fmt: skip
        if record is None:
            missing.append(f"read:{required}")
            continue
        if allowed and not any(_records_match(required, item) for item in allowed):
            missing.append(f"authorized-read:{required}")
        if record.status.lower() not in _SATISFIED_STATUSES:
            missing.append(f"read-status:{required}")
        if not _trusted_record(atom, record.trust, required=_is_h3(atom)):
            missing.append(f"read-trust:{required}")
        if not record.owner:
            missing.append(f"read-owner:{required}")
    if missing:
        reasons.append("required reads are missing, unauthorized, stale, or unowned")
    return missing, reasons


def _records_satisfied(
    atom: TypedAtom, obligations: Iterable[str], records: Iterable[Any], kind: str
) -> tuple[list[str], list[str]]:
    evidence = kind == "evidence"
    prefix = "evidence" if evidence else "verification"
    allowed = (
        _SATISFIED_STATUSES
        if evidence
        else (
            _VERIFICATION_STATUSES if _is_h3(atom) else _INTERNAL_VERIFICATION_STATUSES
        )
    )
    missing: list[str] = []
    reasons: list[str] = []
    for obligation in obligations:
        record = next((record for record in records if _records_match(obligation, record.obligation)), None)  # fmt: skip
        if record is None:
            missing.append(f"{prefix}:{obligation}")
            continue
        if record.status.lower() not in allowed:
            missing.append(f"{prefix}-status:{obligation}")
        if evidence and not record.source:
            missing.append(f"{prefix}-source:{obligation}")
        if not record.owner:
            missing.append(f"{prefix}-owner:{obligation}")
        if not _trusted_record(atom, record.trust, required=evidence or _is_h3(atom)):
            missing.append(f"{prefix}-trust:{obligation}")
        if _is_h3(atom) and _contains_h3_invalid_marker(record.detail):
            missing.append(f"{prefix}-detail:{obligation}")
    if missing:
        reasons.append(
            "evidence obligations are missing or not trusted"
            if evidence
            else "verification obligations are missing or not passed"
        )
    return missing, reasons


def _input_satisfied(
    atom: TypedAtom, context: SemanticContext
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    reasons: list[str] = []
    bad_statuses = _H3_BAD_INPUT_STATUSES
    for required in atom.required_inputs:
        value = context.inputs.get(required.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(f"input:{required.name}")
        elif isinstance(value, Mapping):
            status = _text(value.get("status")).lower()
            if value.get("available") is False or status in bad_statuses:
                missing.append(f"input-status:{required.name}")
            if not _text(value.get("owner")):
                missing.append(f"input-owner:{required.name}")
            if _is_h3(atom):
                if not _trusted_record(atom, _text(value.get("trust")), required=True):
                    missing.append(f"input-trust:{required.name}")
                if any(_contains_h3_invalid_marker(value.get(key)) for key in ("authority", "authorization", "scope_status", "boundary_status")):  # fmt: skip
                    missing.append(f"input-authority:{required.name}")
                if any(value.get(key) is False or _text(value.get(key)).lower() in {"false", "unknown", "stale", "partial"} for key in ("complete", "fresh", "current", "scope_known")):  # fmt: skip
                    missing.append(f"input-completeness:{required.name}")
        elif _is_h3(atom):
            missing.append(f"input-record:{required.name}")
    if missing:
        reasons.append("required semantic inputs are missing or unowned")
    return missing, reasons


def _dependency_state(
    atom: TypedAtom,
    context: SemanticContext,
    registry: AtomRegistry,
    available_positive_ids: frozenset[str] = frozenset(),
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
        if dependency_atom is not None and (
            dependency_atom.full_id in selected
            or dependency_atom.full_id in available_positive_ids
        ):
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
    atom: TypedAtom,
    context: SemanticContext,
    registry: AtomRegistry,
    available_positive_ids: frozenset[str] = frozenset(),
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
    evidence_missing, evidence_reasons = _records_satisfied(
        atom, atom.evidence_obligations, context.evidence, "evidence"
    )
    verification_missing, verification_reasons = _records_satisfied(
        atom, atom.verification_obligations, context.verification, "verification"
    )
    dependency_missing, dependency_reasons = _dependency_state(
        atom, context, registry, available_positive_ids
    )
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
    available_positive_ids = frozenset(
        atom.full_id
        for atom in candidates
        if _signal_for(atom, semantic_context) == "positive"
    )
    applicability = tuple(
        _applicability(
            atom,
            semantic_context,
            active_registry,
            available_positive_ids,
        )
        for atom in candidates
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
            if _is_h3(atom):
                # H3 is private and evidence-bound: an optional hint cannot
                # substitute for its normal semantic applicability gates.
                deferred.append(atom.full_id)
            elif atom.estimated_token_cost.maximum <= remaining:
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


__all__ = ["compile_behavioral_atoms", "compile_semantic_context", "compile_typed_atoms", "legacy_atom_projection", "legacy_string_projection", "render_atoms", "render_typed_atoms"]  # fmt: skip
