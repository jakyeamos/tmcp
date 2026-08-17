"""Compile surface shared by source and extracted-package release checks."""

from __future__ import annotations

import subprocess
import sys

COMPILE_PATHS: tuple[str, ...] = (
    "scripts/tmcp_mcp_server.py",
    "scripts/check_contracts.py",
    "scripts/check_install.py",
    "scripts/check_release_package.py",
    "scripts/release_package_composition.py",
    "scripts/release_package_sessions.py",
    "scripts/release_package_compile.py",
    "scripts/tmcp_release_archive.py",
    "scripts/check_release_evidence.py",
    "scripts/pre_cr_coverage.py",
    "scripts/tmcp_mcp_framing.py",
    "scripts/tmcp_redaction.py",
    "tmcp_runtime/__init__.py",
    "tmcp_runtime/adapters/__init__.py",
    "tmcp_runtime/adapters/aios.py",
    "tmcp_runtime/adapters/cli.py",
    "tmcp_runtime/adapters/dispatch.py",
    "tmcp_runtime/adapters/framing.py",
    "tmcp_runtime/adapters/mcp.py",
    "tmcp_runtime/domain/__init__.py",
    "tmcp_runtime/domain/admission.py",
    "tmcp_runtime/domain/declared_loads.py",
    "tmcp_runtime/domain/composition.py",
    "tmcp_runtime/domain/families.py",
    "tmcp_runtime/domain/harvest_labels.py",
    "tmcp_runtime/domain/harvest_nodes.py",
    "tmcp_runtime/domain/packets.py",
    "tmcp_runtime/domain/receipts.py",
    "tmcp_runtime/domain/recompile.py",
    "tmcp_runtime/domain/review_evidence.py",
    "tmcp_runtime/domain/review_profiles.py",
    "tmcp_runtime/domain/review_results.py",
    "tmcp_runtime/domain/runtime_state.py",
    "tmcp_runtime/domain/routes.py",
    "tmcp_runtime/domain/route_catalog.py",
    "tmcp_runtime/domain/standalone_packets.py",
    "tmcp_runtime/domain/workflow_activation.py",
    "tmcp_runtime/domain/workflow_adaptive.py",
    "tmcp_runtime/domain/workflow_catalog.py",
    "tmcp_runtime/domain/workflow_promotion.py",
    "tmcp_runtime/domain/workflow_recommendations.py",
    "tmcp_runtime/api/__init__.py",
    "tmcp_runtime/api/cli.py",
    "tmcp_runtime/api/evaluation.py",
    "tmcp_runtime/api/registry.py",
    "tmcp_runtime/api/tool_schemas.py",
    "tmcp_runtime/safety/__init__.py",
    "tmcp_runtime/safety/files.py",
    "tmcp_runtime/safety/fixed_files.py",
    "tmcp_runtime/safety/reader.py",
    "tmcp_runtime/safety/redaction.py",
    "tmcp_runtime/storage/__init__.py",
    "tmcp_runtime/storage/artifacts.py",
    "tmcp_runtime/storage/cache_policy.py",
    "tmcp_runtime/storage/global_cache.py",
    "tmcp_runtime/storage/migrations.py",
    "tmcp_runtime/storage/sessions.py",
    "tmcp_runtime/services/__init__.py",
    "tmcp_runtime/services/artifact_persistence.py",
    "tmcp_runtime/services/artifact_plans.py",
    "tmcp_runtime/services/compose.py",
    "tmcp_runtime/services/diagnostics.py",
    "tmcp_runtime/services/evaluation_catalog.py",
    "tmcp_runtime/services/evaluation_orchestration.py",
    "tmcp_runtime/services/evaluation_packets.py",
    "tmcp_runtime/services/evaluation_plan.py",
    "tmcp_runtime/services/evaluation_policy.py",
    "tmcp_runtime/services/evaluation_rendering.py",
    "tmcp_runtime/services/evaluation_scoring.py",
    "tmcp_runtime/services/explain.py",
    "tmcp_runtime/services/global_promotion.py",
    "tmcp_runtime/services/harvest.py",
    "tmcp_runtime/services/harvest_advisories.py",
    "tmcp_runtime/services/promotion.py",
    "tmcp_runtime/services/receipts.py",
    "tmcp_runtime/services/recompile.py",
    "tmcp_runtime/services/recommendations.py",
    "tmcp_runtime/services/review.py",
    "tmcp_runtime/services/runtime.py",
    "tmcp_runtime/services/sessions.py",
)


def compile_command(python_executable: str) -> list[str]:
    return [python_executable, "-m", "py_compile", *COMPILE_PATHS]


if __name__ == "__main__":
    raise SystemExit(
        subprocess.run(compile_command(sys.executable), check=False).returncode
    )
