"""Internal typed behavioral-atom contracts for the opt-in H1/H2/H3 slices.

This module is deliberately separate from harvested strings, workflows, routes, and
the public packet schema.  It is a small, deterministic compiler boundary: a typed
atom is admitted only when an explicit semantic signal and all of its declared
obligations are present.  Text that merely contains a trigger word is never enough.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


RUNTIME_ATOM_SCHEMA = "tmcp-behavioral-atom-runtime-v0.4"
RUNTIME_ATOM_VERSION = "0.4.0"
INTERNAL_CONTRACT_SCHEMA = RUNTIME_ATOM_SCHEMA
INTERNAL_CONTRACT_VERSION = RUNTIME_ATOM_VERSION

DATA_RECONCILIATION_ID = "domain.data_integrity.reconciliation"
MIGRATION_ROLLBACK_ID = "domain.migration_readiness.rollback_path"
DATA_INVARIANTS_ID = "domain.data_integrity.invariants"
MIGRATION_COMPATIBILITY_ID = "domain.migration_readiness.compatibility_sequence"
SECURITY_REDACTION_ID = "domain.security_privacy.redaction"
RELEASE_SHIP_GATE_ID = "domain.release_readiness.ship_gate"
SECURITY_SECRET_BOUNDARY_ID = "domain.security_privacy.secret_boundary"
RELEASE_EVIDENCE_LADDER_ID = "domain.release_readiness.evidence_ladder"

PROCESS_READ_ID = "process.read.required-sources"
PROCESS_CAPTURE_ID = "process.capture.evidence"
PROCESS_VERIFY_ID = "process.verify.obligation"
PROCESS_STOP_ID = "process.stop.missing-evidence"

H1_DOMAIN_IDS = (DATA_RECONCILIATION_ID, MIGRATION_ROLLBACK_ID)
H1_FAMILY_IDS = ("data_integrity", "migration_readiness")
H2_DOMAIN_IDS = (SECURITY_REDACTION_ID, RELEASE_SHIP_GATE_ID)
H2_FAMILY_IDS = ("security_privacy", "release_readiness")
H3_DOMAIN_IDS = (SECURITY_SECRET_BOUNDARY_ID, RELEASE_EVIDENCE_LADDER_ID)
H3_FAMILY_IDS = H2_FAMILY_IDS
SUPPORTED_DOMAIN_IDS = (*H1_DOMAIN_IDS, *H2_DOMAIN_IDS, *H3_DOMAIN_IDS)
SUPPORTED_FAMILY_IDS = (*H1_FAMILY_IDS, *H2_FAMILY_IDS)

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


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _unique(values: Iterable[object]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _text(value)
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: object) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _nonempty_mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _named_records(value: object) -> dict[str, Any]:
    """Normalize mapping-or-record-list inputs without losing record metadata."""

    if isinstance(value, Mapping):
        return dict(value)
    records: dict[str, Any] = {}
    for item in _items(value):
        name = _text(item.get("name") or item.get("id") or item.get("type"))
        if name:
            records[name] = dict(item)
    return records


def full_atom_id(stable_identity: str, version: str = RUNTIME_ATOM_VERSION) -> str:
    """Return the canonical versioned identity used at internal boundaries."""

    return f"{_text(stable_identity)}@{_text(version)}"


def normalize_atom_ref(
    value: object, *, default_version: str = RUNTIME_ATOM_VERSION
) -> str:
    """Normalize a bare atom reference without treating old strings as typed atoms."""

    item = _text(value)
    if not item:
        return ""
    if "@" in item:
        return item
    return full_atom_id(item, default_version)


@dataclass(frozen=True)
class RequiredInput:
    name: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "kind": self.kind}


@dataclass(frozen=True)
class ConflictSpec:
    stable_identity: str
    when: str
    resolution: str

    @property
    def full_id(self) -> str:
        return full_atom_id(self.stable_identity)

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.stable_identity,
            "full_id": self.full_id,
            "when": self.when,
            "resolution": self.resolution,
        }


@dataclass(frozen=True)
class ApplicabilitySpec:
    positive: tuple[str, ...]
    negative: tuple[str, ...]
    ambiguous: tuple[str, ...]
    ambiguous_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive": list(self.positive),
            "negative": list(self.negative),
            "ambiguous": list(self.ambiguous),
            "ambiguous_action": self.ambiguous_action,
        }


@dataclass(frozen=True)
class DomainSemantics:
    target: str
    risk: tuple[str, ...]
    expected_output: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "risk": list(self.risk),
            "expected_output": list(self.expected_output),
        }


@dataclass(frozen=True)
class ProvenanceTrust:
    source_path: str
    source_sha256: str
    trust: str
    input_policy: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "trust": self.trust,
            "input_policy": self.input_policy,
        }


@dataclass(frozen=True)
class RenderingBoundary:
    renderable_to: tuple[str, ...]
    forbidden: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "renderable_to": list(self.renderable_to),
            "forbidden": list(self.forbidden),
        }


@dataclass(frozen=True)
class EstimatedTokenCost:
    unit: str
    minimum: int
    maximum: int
    measure: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "measure": self.measure,
        }


@dataclass(frozen=True)
class TypedAtom:
    """The complete internal contract for one typed atom."""

    stable_identity: str
    version: str
    family: str
    domain_semantics: DomainSemantics
    applicability: ApplicabilitySpec
    dependencies: tuple[str, ...]
    conflicts: tuple[ConflictSpec, ...]
    required_inputs: tuple[RequiredInput, ...]
    required_reads: tuple[str, ...]
    evidence_obligations: tuple[str, ...]
    verification_obligations: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    provenance_trust: ProvenanceTrust
    rendering_boundary: RenderingBoundary
    estimated_token_cost: EstimatedTokenCost
    supersedes: tuple[str, ...] = ()
    kind: str = "domain"
    allowed_phases: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.stable_identity

    @property
    def full_id(self) -> str:
        return full_atom_id(self.stable_identity, self.version)

    @property
    def is_domain(self) -> bool:
        return self.kind == "domain"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUNTIME_ATOM_SCHEMA,
            "version": self.version,
            "id": self.stable_identity,
            "full_id": self.full_id,
            "kind": self.kind,
            "family": self.family,
            "domain_semantics": self.domain_semantics.to_dict(),
            "applicability": self.applicability.to_dict(),
            "dependencies": list(self.dependencies),
            "conflicts": [item.to_dict() for item in self.conflicts],
            "required_inputs": [item.to_dict() for item in self.required_inputs],
            "required_reads": list(self.required_reads),
            "evidence_obligations": list(self.evidence_obligations),
            "verification_obligations": list(self.verification_obligations),
            "stop_conditions": list(self.stop_conditions),
            "provenance_trust": self.provenance_trust.to_dict(),
            "rendering_boundary": self.rendering_boundary.to_dict(),
            "estimated_token_cost": self.estimated_token_cost.to_dict(),
            "supersedes": list(self.supersedes),
            "allowed_phases": list(self.allowed_phases),
        }


@dataclass(frozen=True)
class ReadRecord:
    reference: str
    status: str = "available"
    trust: str = ""
    owner: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "reference": self.reference,
            "status": self.status,
            "trust": self.trust,
            "owner": self.owner,
        }


@dataclass(frozen=True)
class EvidenceRecord:
    obligation: str
    status: str = "recorded"
    source: str = ""
    owner: str = ""
    trust: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "obligation": self.obligation,
            "status": self.status,
            "source": self.source,
            "owner": self.owner,
            "trust": self.trust,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class VerificationRecord:
    obligation: str
    status: str = "passed"
    source: str = ""
    owner: str = ""
    trust: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "obligation": self.obligation,
            "status": self.status,
            "source": self.source,
            "owner": self.owner,
            "trust": self.trust,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SemanticContext:
    """Structured semantic input to the compiler.

    ``objective`` and ``lexical_candidates`` are intentionally not used for
    applicability.  Callers must provide an explicit semantic signal for a
    family/atom, which is how this opt-in path avoids literal-trigger admission.
    """

    objective: str = ""
    task_identity: str = ""
    phase: str = "start"
    inputs: Mapping[str, Any] = field(default_factory=dict)
    allowed_reads: tuple[str, ...] = ()
    reads: tuple[ReadRecord, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    verification: tuple[VerificationRecord, ...] = ()
    semantic_signals: Mapping[str, Any] = field(default_factory=dict)
    requested_atoms: tuple[str, ...] = ()
    provided_dependencies: tuple[str, ...] = ()
    active_conflicts: tuple[str, ...] = ()
    conflict_resolutions: Mapping[str, str] = field(default_factory=dict)
    token_budget: int = 512
    optional_atoms: tuple[str, ...] = ()
    phase_status: str = "compatible"
    declared_missing_evidence: tuple[str, ...] = ()
    legacy_atoms: tuple[str, ...] = ()
    source_refs: Mapping[str, str] = field(default_factory=dict)
    ownership: Mapping[str, str] = field(default_factory=dict)
    lexical_candidates: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "SemanticContext":
        value = raw if isinstance(raw, Mapping) else {}
        nested = value.get("semantic_context")
        if isinstance(nested, Mapping):
            value = nested

        def text_tuple(*keys: str) -> tuple[str, ...]:
            for key in keys:
                candidate = value.get(key)
                if isinstance(candidate, Sequence) and not isinstance(
                    candidate, (str, bytes, bytearray)
                ):
                    return _unique(candidate)
                if isinstance(candidate, str) and candidate.strip():
                    return (candidate.strip(),)
            return ()

        def parse_reads() -> tuple[ReadRecord, ...]:
            records: list[ReadRecord] = []
            raw_reads = value.get("reads", value.get("read_records"))
            for item in _items(raw_reads):
                reference = _text(
                    item.get("reference")
                    or item.get("name")
                    or item.get("read")
                    or item.get("path")
                )
                if reference:
                    records.append(
                        ReadRecord(
                            reference=reference,
                            status=_text(item.get("status") or "available"),
                            trust=_text(item.get("trust")),
                            owner=_text(item.get("owner")),
                        )
                    )
            if records:
                return tuple(records)
            return tuple(
                ReadRecord(reference=item, status="available")
                for item in text_tuple("read_sources", "required_reads")
            )

        def parse_evidence() -> tuple[EvidenceRecord, ...]:
            records: list[EvidenceRecord] = []
            for item in _items(value.get("evidence", value.get("evidence_records"))):
                obligation = _text(
                    item.get("obligation")
                    or item.get("name")
                    or item.get("id")
                    or item.get("type")
                )
                if obligation:
                    records.append(
                        EvidenceRecord(
                            obligation=obligation,
                            status=_text(item.get("status") or "recorded"),
                            source=_text(item.get("source") or item.get("path")),
                            owner=_text(item.get("owner")),
                            trust=_text(item.get("trust")),
                            detail=_text(item.get("detail") or item.get("description")),
                        )
                    )
            return tuple(records)

        def parse_verification() -> tuple[VerificationRecord, ...]:
            records: list[VerificationRecord] = []
            for item in _items(
                value.get("verification", value.get("verification_records"))
            ):
                obligation = _text(
                    item.get("obligation")
                    or item.get("name")
                    or item.get("id")
                    or item.get("type")
                )
                if obligation:
                    records.append(
                        VerificationRecord(
                            obligation=obligation,
                            status=_text(item.get("status") or "passed"),
                            source=_text(item.get("source") or item.get("path")),
                            owner=_text(item.get("owner")),
                            trust=_text(item.get("trust")),
                            detail=_text(item.get("detail") or item.get("description")),
                        )
                    )
            return tuple(records)

        def signal_mapping() -> Mapping[str, Any]:
            raw_signals = value.get(
                "semantic_signals",
                value.get("domain_signals", value.get("semantic_predicates", {})),
            )
            return dict(raw_signals) if isinstance(raw_signals, Mapping) else {}

        deps = text_tuple(
            "provided_dependencies", "available_dependencies", "dependencies"
        )
        normalized_deps = tuple(
            normalize_atom_ref(item) for item in deps if normalize_atom_ref(item)
        )
        requested = text_tuple("requested_atoms", "required_atoms", "atom_ids")
        normalized_requested = tuple(
            normalize_atom_ref(item) for item in requested if normalize_atom_ref(item)
        )
        optional = text_tuple("optional_atoms")
        normalized_optional = tuple(
            normalize_atom_ref(item) for item in optional if normalize_atom_ref(item)
        )
        active_conflicts = text_tuple("active_conflicts", "conflicts")
        normalized_conflicts = tuple(
            normalize_atom_ref(item) if "@" not in item else item
            for item in active_conflicts
        )
        raw_resolutions = value.get("conflict_resolutions", {})
        resolutions = {
            normalize_atom_ref(key) if "@" not in _text(key) else _text(key): _text(val)
            for key, val in _mapping(raw_resolutions).items()
            if _text(key) and _text(val)
        }
        raw_inputs = value.get("inputs", value.get("required_inputs", {}))
        raw_missing = text_tuple("declared_missing_evidence", "missing_evidence")
        source_refs = {
            _text(key): _text(val)
            for key, val in _mapping(value.get("source_refs", {})).items()
            if _text(key) and _text(val)
        }
        ownership = {
            _text(key): _text(val)
            for key, val in _mapping(value.get("ownership", {})).items()
            if _text(key) and _text(val)
        }
        raw_budget = value.get("token_budget", value.get("max_tokens", 512))
        try:
            budget = int(raw_budget)
        except (TypeError, ValueError):
            budget = 512
        return cls(
            objective=_text(value.get("objective")),
            task_identity=_text(value.get("task_identity")),
            phase=_text(value.get("phase") or "start"),
            inputs=_named_records(raw_inputs),
            allowed_reads=text_tuple("allowed_reads", "read_allowlist"),
            reads=parse_reads(),
            evidence=parse_evidence(),
            verification=parse_verification(),
            semantic_signals=signal_mapping(),
            requested_atoms=normalized_requested,
            provided_dependencies=normalized_deps,
            active_conflicts=normalized_conflicts,
            conflict_resolutions=resolutions,
            token_budget=max(0, budget),
            optional_atoms=normalized_optional,
            phase_status=_text(value.get("phase_status") or "compatible"),
            declared_missing_evidence=raw_missing,
            legacy_atoms=text_tuple("legacy_atoms", "active_atoms"),
            source_refs=source_refs,
            ownership=ownership,
            lexical_candidates=text_tuple("lexical_candidates", "trigger_words"),
        )


@dataclass(frozen=True)
class ApplicabilityResult:
    atom_id: str
    family: str
    decision: str
    status: str
    reasons: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    stops: tuple[str, ...] = ()
    dependency_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "family": self.family,
            "decision": self.decision,
            "status": self.status,
            "reasons": list(self.reasons),
            "missing": list(self.missing),
            "stops": list(self.stops),
            "dependency_ids": list(self.dependency_ids),
            "conflict_ids": list(self.conflict_ids),
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


@dataclass(frozen=True)
class RenderRecord:
    atom_id: str
    target: str
    text: str
    token_cost: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "target": self.target,
            "text": self.text,
            "token_cost": self.token_cost,
        }


@dataclass(frozen=True)
class CompileResult:
    schema: str
    version: str
    decision: str
    status: str
    selected: tuple[TypedAtom, ...]
    applicability: tuple[ApplicabilityResult, ...]
    stops: tuple[str, ...]
    missing: tuple[str, ...]
    legacy_projection: tuple[dict[str, str], ...]
    total_token_cost: int
    token_budget: int
    render_records: tuple[RenderRecord, ...] = ()
    deferred: tuple[str, ...] = ()

    @property
    def selected_ids(self) -> tuple[str, ...]:
        return tuple(atom.full_id for atom in self.selected)

    @property
    def domain_selected_ids(self) -> tuple[str, ...]:
        return tuple(atom.full_id for atom in self.selected if atom.is_domain)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "decision": self.decision,
            "status": self.status,
            "selected": [atom.to_dict() for atom in self.selected],
            "selected_ids": list(self.selected_ids),
            "domain_selected_ids": list(self.domain_selected_ids),
            "applicability": [item.to_dict() for item in self.applicability],
            "stops": list(self.stops),
            "missing": list(self.missing),
            "legacy_projection": list(self.legacy_projection),
            "total_token_cost": self.total_token_cost,
            "token_budget": self.token_budget,
            "render_records": [item.to_dict() for item in self.render_records],
            "deferred": list(self.deferred),
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


__all__ = [
    "ApplicabilityResult",
    "ApplicabilitySpec",
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
    "H3_DOMAIN_IDS",
    "H3_FAMILY_IDS",
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
    "RELEASE_EVIDENCE_LADDER_ID",
    "RELEASE_SHIP_GATE_ID",
    "SECURITY_REDACTION_ID",
    "SECURITY_SECRET_BOUNDARY_ID",
    "SUPPORTED_DOMAIN_IDS",
    "SUPPORTED_FAMILY_IDS",
    "full_atom_id",
    "normalize_atom_ref",
]
