"""Compile surface shared by source and extracted-package release checks."""

from __future__ import annotations


COMPILE_PATHS: tuple[str, ...] = (
    "scripts/tmcp_mcp_server.py",
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
    "tmcp_runtime/domain/__init__.py",
    "tmcp_runtime/domain/declared_loads.py",
    "tmcp_runtime/domain/composition.py",
    "tmcp_runtime/domain/families.py",
    "tmcp_runtime/domain/packets.py",
    "tmcp_runtime/domain/recompile.py",
    "tmcp_runtime/domain/review_evidence.py",
    "tmcp_runtime/domain/review_profiles.py",
    "tmcp_runtime/domain/review_results.py",
    "tmcp_runtime/domain/routes.py",
    "tmcp_runtime/domain/standalone_packets.py",
    "tmcp_runtime/domain/workflow_adaptive.py",
    "tmcp_runtime/domain/workflow_catalog.py",
    "tmcp_runtime/domain/workflow_recommendations.py",
    "tmcp_runtime/api/__init__.py",
    "tmcp_runtime/api/registry.py",
    "tmcp_runtime/api/tool_schemas.py",
    "tmcp_runtime/safety/__init__.py",
    "tmcp_runtime/safety/files.py",
    "tmcp_runtime/safety/fixed_files.py",
    "tmcp_runtime/safety/reader.py",
    "tmcp_runtime/storage/__init__.py",
    "tmcp_runtime/storage/artifacts.py",
    "tmcp_runtime/storage/sessions.py",
)


def compile_command(python_executable: str) -> list[str]:
    return [python_executable, "-m", "py_compile", *COMPILE_PATHS]
