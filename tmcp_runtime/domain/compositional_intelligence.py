"""Public pure APIs for host-assisted semantic composition."""

from __future__ import annotations

from .behavior_manifests import (
    BEHAVIOR_HYDRATION_SCHEMA,
    BEHAVIOR_MANIFEST_INDEX_SCHEMA,
    BEHAVIOR_MANIFEST_SCHEMA,
    build_behavior_manifest,
    build_behavior_manifest_index,
    hydrate_behavior_blocks,
)
from .composition_planning import (
    build_composition_plan,
    compile_semantic_composition,
)
from .composition_runtime_capsules import (
    PREPARATION_CONTROLS_SCHEMA,
    RUNTIME_CAPSULE_SCHEMA,
    RuntimeCapsuleError,
    build_runtime_capsule,
    rehydrate_runtime_capsule,
    validate_runtime_capsule,
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
    "BEHAVIOR_HYDRATION_SCHEMA",
    "BEHAVIOR_MANIFEST_INDEX_SCHEMA",
    "BEHAVIOR_MANIFEST_SCHEMA",
    "ACTIVE_SOURCE_ROLES",
    "ALLOWED_RELATIONSHIPS",
    "COMPOSITION_PLAN_SCHEMA",
    "COMPOSITION_TRUST",
    "INSTRUCTION_OVERRIDE_POLICY",
    "PHASE_ORDER",
    "PREFLIGHT_SCHEMA",
    "PREPARATION_CONTROLS_SCHEMA",
    "RUNTIME_CAPSULE_SCHEMA",
    "RuntimeCapsuleError",
    "SEMANTIC_PROPOSAL_SCHEMA",
    "SOURCE_ROLES",
    "SemanticProposalValidationError",
    "build_composition_plan",
    "build_runtime_capsule",
    "build_behavior_manifest",
    "build_behavior_manifest_index",
    "build_source_slices",
    "compile_semantic_composition",
    "prepare_composition",
    "rehydrate_runtime_capsule",
    "hydrate_behavior_blocks",
    "semantic_proposal_starter",
    "scoped_seed_composition_hints",
    "source_role_for",
    "validate_semantic_proposal",
    "validate_runtime_capsule",
]
