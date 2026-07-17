"""Public pure APIs for host-assisted semantic composition."""

from __future__ import annotations

from .composition_planning import (
    build_composition_plan,
    compile_semantic_composition,
)
from .composition_preflight import (
    ACTIVE_SOURCE_ROLES,
    ALLOWED_RELATIONSHIPS,
    COMPOSITION_PLAN_SCHEMA,
    COMPOSITION_TRUST,
    INSTRUCTION_OVERRIDE_POLICY,
    PHASE_ORDER,
    PREFLIGHT_SCHEMA,
    SEMANTIC_PROPOSAL_SCHEMA,
    SOURCE_ROLES,
    build_source_slices,
    prepare_composition,
    semantic_proposal_starter,
    scoped_seed_composition_hints,
    source_role_for,
)
from .composition_validation import (
    SemanticProposalValidationError,
    validate_semantic_proposal,
)


__all__ = [
    "ACTIVE_SOURCE_ROLES",
    "ALLOWED_RELATIONSHIPS",
    "COMPOSITION_PLAN_SCHEMA",
    "COMPOSITION_TRUST",
    "INSTRUCTION_OVERRIDE_POLICY",
    "PHASE_ORDER",
    "PREFLIGHT_SCHEMA",
    "SEMANTIC_PROPOSAL_SCHEMA",
    "SOURCE_ROLES",
    "SemanticProposalValidationError",
    "build_composition_plan",
    "build_source_slices",
    "compile_semantic_composition",
    "prepare_composition",
    "semantic_proposal_starter",
    "scoped_seed_composition_hints",
    "source_role_for",
    "validate_semantic_proposal",
]
