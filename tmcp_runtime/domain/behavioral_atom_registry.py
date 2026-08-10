"""Versioned H1 and H2 typed atom registry records."""

from __future__ import annotations

from functools import lru_cache
from collections.abc import Iterable

from tmcp_runtime.domain.behavioral_atom_types import (
    ApplicabilitySpec,
    ConflictSpec,
    DATA_INVARIANTS_ID,
    DATA_RECONCILIATION_ID,
    DomainSemantics,
    EstimatedTokenCost,
    MIGRATION_COMPATIBILITY_ID,
    MIGRATION_ROLLBACK_ID,
    PROCESS_CAPTURE_ID,
    PROCESS_READ_ID,
    PROCESS_STOP_ID,
    PROCESS_VERIFY_ID,
    ProvenanceTrust,
    RenderingBoundary,
    RequiredInput,
    RUNTIME_ATOM_VERSION,
    RELEASE_SHIP_GATE_ID,
    SECURITY_REDACTION_ID,
    TypedAtom,
    _text,
    _unique,
    full_atom_id,
    normalize_atom_ref,
)


class AtomRegistry:
    """Immutable-by-convention registry for the narrow v0.4 runtime slice."""

    def __init__(self, atoms: Iterable[TypedAtom]):
        ordered = tuple(atoms)
        by_id: dict[str, TypedAtom] = {}
        for atom in ordered:
            if atom.version != RUNTIME_ATOM_VERSION:
                raise ValueError(f"Typed atom has unsupported version: {atom.full_id}")
            if atom.full_id in by_id:
                raise ValueError(f"Duplicate typed atom: {atom.full_id}")
            if not atom.stable_identity or not atom.family:
                raise ValueError("Typed atom requires stable identity and family")
            if not atom.rendering_boundary.renderable_to:
                raise ValueError(
                    f"Typed atom has no rendering boundary: {atom.full_id}"
                )
            by_id[atom.full_id] = atom
        self._atoms = ordered
        self._by_id = by_id

    @property
    def atoms(self) -> tuple[TypedAtom, ...]:
        return self._atoms

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(atom.full_id for atom in self._atoms)

    def get(self, reference: object) -> TypedAtom | None:
        item = _text(reference)
        if not item:
            return None
        return self._by_id.get(item) or self._by_id.get(normalize_atom_ref(item))

    def for_family(self, family: str) -> tuple[TypedAtom, ...]:
        return tuple(atom for atom in self._atoms if atom.family == family)


def _atom(
    *,
    stable_identity: str,
    family: str,
    target: str,
    risk: Iterable[str],
    expected_output: Iterable[str],
    positive: Iterable[str],
    negative: Iterable[str],
    ambiguous: Iterable[str],
    ambiguous_action: str,
    dependencies: Iterable[str],
    conflicts: Iterable[ConflictSpec],
    required_inputs: Iterable[RequiredInput],
    required_reads: Iterable[str],
    evidence_obligations: Iterable[str],
    verification_obligations: Iterable[str],
    stop_conditions: Iterable[str],
    source_path: str,
    source_sha256: str,
    token_min: int,
    token_max: int,
    kind: str = "domain",
    allowed_phases: Iterable[str] = (),
    supersedes: Iterable[str] = (),
) -> TypedAtom:
    return TypedAtom(
        stable_identity=stable_identity,
        version=RUNTIME_ATOM_VERSION,
        family=family,
        domain_semantics=DomainSemantics(
            target=target,
            risk=_unique(risk),
            expected_output=_unique(expected_output),
        ),
        applicability=ApplicabilitySpec(
            positive=_unique(positive),
            negative=_unique(negative),
            ambiguous=_unique(ambiguous),
            ambiguous_action=ambiguous_action,
        ),
        dependencies=_unique(normalize_atom_ref(item) for item in dependencies),
        conflicts=tuple(conflicts),
        required_inputs=tuple(required_inputs),
        required_reads=_unique(required_reads),
        evidence_obligations=_unique(evidence_obligations),
        verification_obligations=_unique(verification_obligations),
        stop_conditions=_unique(stop_conditions),
        provenance_trust=ProvenanceTrust(
            source_path=source_path,
            source_sha256=source_sha256,
            trust="committed_source_backed",
            input_policy="accept only scoped, owner-recorded evidence; never infer from harvested wording",
        ),
        rendering_boundary=RenderingBoundary(
            renderable_to=("packet", "receipt", "advisory_trace"),
            forbidden=(
                "runtime_instruction",
                "provider_prompt",
                "provider_outcome",
                "cross_skill_composition",
            ),
        ),
        estimated_token_cost=EstimatedTokenCost(
            unit="tokens",
            minimum=token_min,
            maximum=token_max,
            measure="deterministic rendered atom record",
        ),
        supersedes=_unique(supersedes),
        kind=kind,
        allowed_phases=_unique(allowed_phases),
    )


_DECISION_SOURCE = (
    "docs/experiments/behavioral-atoms-runtime-implementation-decision-v0.4.json"
)
_DECISION_SHA256 = "fd79c1f56fbbc64719cd130706cdf55a56c47ee10222ccf2b025327bad3f6542"
_ALLOWED_PHASES = (
    "start",
    "planning",
    "runtime",
    "verification",
    "review",
    "preflight",
    "migration",
    "audit",
)


@lru_cache(maxsize=1)
def build_h1_registry() -> AtomRegistry:
    """Build the six records owned by this first typed runtime slice."""

    process_common = {
        "target": "evidence-first process boundary",
        "risk": ("unread source", "unverified claim"),
        "expected_output": ("bounded evidence record",),
        "positive": ("the process obligation is explicitly requested",),
        "negative": ("the process obligation is not requested",),
        "ambiguous": ("the obligation is named but its boundary is not explicit",),
        "ambiguous_action": "hold and identify the missing process boundary",
        "dependencies": (),
        "conflicts": (),
        "required_inputs": (),
        "required_reads": (),
        "evidence_obligations": (),
        "verification_obligations": (),
        "stop_conditions": ("process boundary is not observable",),
        "source_path": _DECISION_SOURCE,
        "source_sha256": _DECISION_SHA256,
        "allowed_phases": _ALLOWED_PHASES,
        "kind": "process",
    }
    process_atoms = (
        _atom(
            stable_identity=PROCESS_READ_ID,
            family="process",
            token_min=8,
            token_max=18,
            **process_common,
        ),
        _atom(
            stable_identity=PROCESS_CAPTURE_ID,
            family="process",
            token_min=8,
            token_max=18,
            **{**process_common, "dependencies": (PROCESS_READ_ID,)},
        ),
        _atom(
            stable_identity=PROCESS_VERIFY_ID,
            family="process",
            token_min=8,
            token_max=18,
            **{**process_common, "dependencies": (PROCESS_CAPTURE_ID,)},
        ),
        _atom(
            stable_identity=PROCESS_STOP_ID,
            family="process",
            token_min=6,
            token_max=14,
            **process_common,
        ),
    )
    data_atom = _atom(
        stable_identity=DATA_RECONCILIATION_ID,
        family="data_integrity",
        target="reconcile pre/post state across an import, migration, backfill, or pipeline replay",
        risk=(
            "silent mismatch",
            "duplicates",
            "missing records",
            "non-repeatable replay",
        ),
        expected_output=("reconciliation gap list", "bounded remediation record"),
        positive=("semantic data-integrity reconciliation is required",),
        negative=("the task has no data state or correctness obligation",),
        ambiguous=(
            "data mismatch is mentioned but comparison states or rule are not owned",
        ),
        ambiguous_action="hold and identify both states plus the reconciliation rule owner",
        dependencies=(PROCESS_READ_ID, full_atom_id(DATA_INVARIANTS_ID)),
        conflicts=(
            ConflictSpec(
                stable_identity="conflict.data_integrity.no_reconciliation",
                when="post-change correctness is accepted without pre/post evidence",
                resolution="stop/request reconciliation",
            ),
        ),
        required_inputs=(
            RequiredInput("before_state", "bounded snapshot or count"),
            RequiredInput("after_state", "bounded snapshot or count"),
            RequiredInput("reconciliation_rule", "domain-owned comparison rule"),
        ),
        required_reads=(
            "skills/tmcp-data-integrity-audit/SKILL.md",
            "reconciliation checks, import/export jobs, or backfill evidence",
        ),
        evidence_obligations=(
            "before/after boundary is recorded",
            "mismatches, exclusions, and unresolved gaps are recorded",
        ),
        verification_obligations=(
            "reconciliation check is run and inspected",
            "idempotency risk is repeated when applicable",
        ),
        stop_conditions=(
            "comparison unavailable",
            "mismatch unclassified or reconciliation rule absent",
        ),
        source_path="skills/tmcp-data-integrity-audit/SKILL.md",
        source_sha256="84fa7f2ad5aac85233d96aae31bc70412630a891715578213a91b1c4b93daf77",
        token_min=20,
        token_max=48,
        allowed_phases=_ALLOWED_PHASES,
        supersedes=("domain.data_integrity.reconciliation@0.3.0",),
    )
    migration_atom = _atom(
        stable_identity=MIGRATION_ROLLBACK_ID,
        family="migration_readiness",
        target="rollback and cutover readiness for an irreversible or compatibility-sensitive transition",
        risk=(
            "irreversible data change",
            "failed cutover",
            "no restore",
            "unbounded recovery",
        ),
        expected_output=("rollback gap list", "validation gate record"),
        positive=("semantic migration rollback or cutover readiness is required",),
        negative=(
            "the task has no transition, cutover, fallback, or recovery obligation",
        ),
        ambiguous=(
            "rollback is named but owner, trigger, or recoverable boundary is unspecified",
        ),
        ambiguous_action="hold and define rollback owner, trigger, and recoverable boundary",
        dependencies=(PROCESS_READ_ID, full_atom_id(MIGRATION_COMPATIBILITY_ID)),
        conflicts=(
            ConflictSpec(
                stable_identity="conflict.migration_readiness.no_rollback",
                when="cutover is accepted without tested and bounded rollback",
                resolution="stop/record blocker",
            ),
        ),
        required_inputs=(
            RequiredInput("rollback_owner", "named owner"),
            RequiredInput("rollback_trigger", "observable failure condition"),
            RequiredInput("recoverable_boundary", "snapshot or compatibility state"),
        ),
        required_reads=(
            "skills/tmcp-migration-readiness/SKILL.md",
            "rollback path, cutover, and validation commands",
        ),
        evidence_obligations=(
            "rollback owner, trigger, path, and limitations are recorded",
            "cutover validation and recovery evidence is recorded",
        ),
        verification_obligations=(
            "rollback conditions are observable and bounded",
            "acceptance gate covers cutover and recovery",
        ),
        stop_conditions=(
            "rollback owner or trigger missing",
            "recoverable boundary unidentified",
        ),
        source_path="skills/tmcp-migration-readiness/SKILL.md",
        source_sha256="8cc1eb80974ebcb098e5ef65ca0f3582f860e108d952f073e96b171557bf90f7",
        token_min=22,
        token_max=54,
        allowed_phases=_ALLOWED_PHASES,
        supersedes=("domain.migration_readiness.rollback_path@0.3.0",),
    )
    return AtomRegistry((*process_atoms, data_atom, migration_atom))


@lru_cache(maxsize=1)
def build_h2_registry() -> AtomRegistry:
    """Extend the H1 registry with only the preregistered H2 seed records."""

    security_atom = _atom(
        stable_identity=SECURITY_REDACTION_ID,
        family="security_privacy",
        target="secret-handling and privacy-preserving evidence boundaries",
        risk=(
            "credential exposure",
            "sensitive-data leakage",
            "unverifiable redaction claims",
        ),
        expected_output=(
            "redaction summary",
            "evidence gaps",
            "bounded remediation",
        ),
        positive=(
            "semantic secret handling, privacy, redaction, auth, or sensitive-evidence review is required",
        ),
        negative=("the task has no secret, privacy, auth, or sensitive-data boundary",),
        ambiguous=(
            "possible sensitive values exist but ownership, authorization, or redaction policy is unclear",
        ),
        ambiguous_action="hold before reading or returning sensitive content and establish the handling boundary",
        dependencies=(PROCESS_READ_ID,),
        conflicts=(
            ConflictSpec(
                stable_identity="conflict.security_privacy.unredacted_output",
                when="a proposed output contains sensitive values or unverified redaction",
                resolution="stop/redact/preserve summary",
            ),
        ),
        required_inputs=(
            RequiredInput("sensitive_boundary", "authored privacy or security rule"),
            RequiredInput("evidence_owner", "authorized data owner"),
        ),
        required_reads=(
            "skills/tmcp-security-privacy-audit/SKILL.md",
            "security, privacy, CI, auth, payment, or data-flow evidence",
        ),
        evidence_obligations=(
            "what was redacted and why is recorded",
            "security and privacy evidence gaps are recorded without sensitive values",
        ),
        verification_obligations=(
            "outputs contain no unredacted sensitive values",
            "each material security claim points to bounded evidence",
        ),
        stop_conditions=(
            "handling authorization or data owner missing",
            "redaction cannot be verified at the output boundary",
        ),
        source_path="skills/tmcp-security-privacy-audit/SKILL.md",
        source_sha256="18c7b963bb400250a3461f306616a53c603e299dafb29afc06c0e411f88e88d7",
        token_min=20,
        token_max=50,
        allowed_phases=_ALLOWED_PHASES,
        supersedes=("domain.security_privacy.redaction@0.3.0",),
    )
    release_atom = _atom(
        stable_identity=RELEASE_SHIP_GATE_ID,
        family="release_readiness",
        target="ship or no-ship readiness for a branch, feature, milestone, or product",
        risk=(
            "release decision without current CI or tests",
            "missing build or package evidence",
            "unresolved launch blocker",
        ),
        expected_output=(
            "evidence-backed release rubric",
            "blockers",
            "ordered remediation",
        ),
        positive=(
            "semantic ship, merge, release, or quality-evidenced handoff review is required",
        ),
        negative=(
            "the task is isolated debugging with no release or handoff decision",
        ),
        ambiguous=(
            "a handoff is requested but current quality evidence or release ownership is missing",
        ),
        ambiguous_action="hold and refresh current release evidence before a readiness decision",
        dependencies=(PROCESS_READ_ID,),
        conflicts=(
            ConflictSpec(
                stable_identity="conflict.release_readiness.unverified_ship",
                when="a ship or no-ship claim uses stale or missing quality evidence",
                resolution="stop/name evidence gap and blocker",
            ),
        ),
        required_inputs=(
            RequiredInput("release_scope", "branch, feature, milestone, or product"),
            RequiredInput(
                "current_quality_evidence", "CI, tests, build, and release output"
            ),
        ),
        required_reads=(
            "skills/tmcp-release-readiness/SKILL.md",
            "project instructions, README, CI, tests, build scripts, and release docs",
        ),
        evidence_obligations=(
            "current quality and release evidence is recorded",
            "observed blockers, risks, and unknowns are separated",
        ),
        verification_obligations=(
            "required release checks are run or inspected",
            "every ship blocker has a disposition and next gate",
        ),
        stop_conditions=(
            "release scope or owner missing",
            "current quality evidence unavailable or stale",
        ),
        source_path="skills/tmcp-release-readiness/SKILL.md",
        source_sha256="54d435ed0f551048cccd47c3093aa0734aff0fda8a15627ff3fb1d8bc8ca11ff",
        token_min=22,
        token_max=52,
        allowed_phases=_ALLOWED_PHASES,
        supersedes=("domain.release_readiness.ship_gate@0.3.0",),
    )
    return AtomRegistry((*build_h1_registry().atoms, security_atom, release_atom))


__all__ = ["AtomRegistry", "build_h1_registry", "build_h2_registry"]
