"""Compatibility exports for the private typed behavioral-atom runtime."""

from tmcp_runtime.services.behavioral_atom_evaluation import (
    build_h1_advisory_evaluator_mapping,
    build_h2_advisory_evaluator_mapping,
    evaluate_sealed_behavioral_fixtures,
    evaluate_transplant_arm,
)
from tmcp_runtime.services.behavioral_atom_h3 import (
    build_h3_advisory_evaluator_mapping,
    evaluate_h3_boundary_fixtures,
)
from tmcp_runtime.services.behavioral_atom_projection import (
    INTERNAL_SEMANTIC_BUNDLE_KEY,
    project_compile_result_to_packet,
    project_legacy_atoms,
    project_semantic_bundle_to_packet,
    semantic_bundle_from_arguments,
    static_projection_summary,
)

h1_advisory_evaluator_mapping = build_h1_advisory_evaluator_mapping
h2_advisory_evaluator_mapping = build_h2_advisory_evaluator_mapping
h3_advisory_evaluator_mapping = build_h3_advisory_evaluator_mapping

__all__ = [
    "INTERNAL_SEMANTIC_BUNDLE_KEY",
    "build_h1_advisory_evaluator_mapping",
    "build_h2_advisory_evaluator_mapping",
    "build_h3_advisory_evaluator_mapping",
    "evaluate_h3_boundary_fixtures",
    "evaluate_sealed_behavioral_fixtures",
    "evaluate_transplant_arm",
    "h1_advisory_evaluator_mapping",
    "h2_advisory_evaluator_mapping",
    "h3_advisory_evaluator_mapping",
    "project_compile_result_to_packet",
    "project_legacy_atoms",
    "project_semantic_bundle_to_packet",
    "semantic_bundle_from_arguments",
    "static_projection_summary",
]
