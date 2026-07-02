#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


EXCLUDE_DIRS = {
    "__pycache__",
    ".aios",
    ".codex",
    ".git",
    ".pre-cr",
    ".pytest_cache",
    ".quality-runner",
    ".mypy_cache",
    ".ruff_cache",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def should_include(path: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    return True


def create_package(plugin_root: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz") as archive:
        for path in sorted(plugin_root.rglob("*")):
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(plugin_root)
            if not should_include(relative):
                continue
            archive.add(path, arcname=Path("tmcp") / relative)


def run(command: list[str], cwd: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    return completed.returncode == 0, completed.stdout + completed.stderr


def run_json(command: list[str], cwd: Path) -> tuple[bool, str, dict[str, Any] | None]:
    env = os.environ.copy()
    env["AIOS_ROOT"] = "/tmp/tmcp-aios-missing"
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        return False, output, None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return False, f"could not parse JSON output: {exc}\n{output}", None
    if not isinstance(payload, dict):
        return False, f"JSON output must be an object\n{output}", None
    return True, output, payload


def check_adaptive_workflow_surface(
    plugin_root: Path, scratch_root: Path
) -> tuple[bool, str]:
    source_root = scratch_root / "adaptive-release-surface"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Release Surface",
                "Release readiness requires CI verification, package checks, version evidence, changelog updates, and tag review.",
                "Keep ordered next actions and artifact contracts visible before ship decisions.",
            ]
        ),
        encoding="utf-8",
    )
    ok, output, payload = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "recommend",
            str(source_root),
            "--candidate-workflows",
            "release_readiness",
            "--min-confidence",
            "0.1",
            "--no-write-artifacts",
            "--compact",
        ],
        plugin_root,
    )
    if not ok or payload is None:
        return False, output
    if payload.get("schema") != "tmcp-workflow-recommendation-v1":
        return False, f"unexpected recommendation schema: {payload.get('schema')}"
    recommended = payload.get("recommended_workflows")
    if not isinstance(recommended, list) or not any(
        isinstance(item, dict) and item.get("id") == "release_readiness_workflow"
        for item in recommended
    ):
        return (
            False,
            "tmcp_recommend_workflows did not recommend release_readiness_workflow",
        )
    adaptive_pack = payload.get("adaptive_workflow_pack")
    if not isinstance(adaptive_pack, dict):
        return False, "tmcp_recommend_workflows output missing adaptive_workflow_pack"
    if adaptive_pack.get("schema") != "tmcp-adaptive-workflow-pack-v0.1":
        return False, "adaptive_workflow_pack schema mismatch"
    if adaptive_pack.get("artifact_type") != "adaptive_workflow_pack":
        return False, "adaptive_workflow_pack artifact_type mismatch"
    templates = adaptive_pack.get("recommended_default_templates")
    if not isinstance(templates, list) or not templates:
        return False, "adaptive_workflow_pack missing recommended_default_templates"
    if payload.get("artifact_paths") != {}:
        return False, "recommend smoke should not write artifacts"
    return True, output


def safe_extractall(archive: tarfile.TarFile, target: Path) -> None:
    target_root = target.resolve()
    for member in archive.getmembers():
        member_path = (target / member.name).resolve()
        if member_path != target_root and target_root not in member_path.parents:
            raise ValueError(f"Unsafe tar path: {member.name}")
        if member.issym() or member.islnk():
            raise ValueError(f"Refusing link in tar package: {member.name}")
    try:
        archive.extractall(target, filter="data")
    except TypeError:
        archive.extractall(target)


def check_package(package_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="tmcp-package-check-") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(package_path, "r:gz") as archive:
            safe_extractall(archive, tmp_path)
        plugin_root = tmp_path / "tmcp"
        install_ok, install_output = run(
            [sys.executable, "scripts/check_install.py", "."], plugin_root
        )
        tests_ok, tests_output = run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"], plugin_root
        )
        compile_ok, compile_output = run(
            [
                sys.executable,
                "-m",
                "py_compile",
                "scripts/tmcp_mcp_server.py",
                "scripts/check_install.py",
                "scripts/check_release_package.py",
                "scripts/pre_cr_coverage.py",
                "scripts/tmcp_mcp_framing.py",
                "scripts/tmcp_redaction.py",
            ],
            plugin_root,
        )
        launcher_ok, launcher_output = run(
            ["node", "--check", "scripts/tmcp_launcher.mjs"], plugin_root
        )
        adaptive_ok, adaptive_output = check_adaptive_workflow_surface(
            plugin_root, tmp_path
        )
    return {
        "install_check": "pass" if install_ok else "fail",
        "tests": "pass" if tests_ok else "fail",
        "compile": "pass" if compile_ok else "fail",
        "launcher_syntax": "pass" if launcher_ok else "fail",
        "adaptive_workflow_surface": "pass" if adaptive_ok else "fail",
        "output": {
            "install": install_output,
            "tests": tests_output,
            "compile": compile_output,
            "launcher_syntax": launcher_output,
            "adaptive_workflow_surface": adaptive_output,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create and verify a TMCP release package."
    )
    parser.add_argument(
        "plugin_root", nargs="?", default=".", help="Path to plugin root"
    )
    parser.add_argument("--output", help="Optional package output path")
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path(tempfile.gettempdir()) / "tmcp-release-check.tar.gz"
    )
    create_package(plugin_root, output_path)
    result = {
        "schema": "tmcp-release-package-check-v0.1",
        "package_path": str(output_path),
        **check_package(output_path),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    ok = (
        result["install_check"] == "pass"
        and result["tests"] == "pass"
        and result["compile"] == "pass"
        and result["launcher_syntax"] == "pass"
        and result["adaptive_workflow_surface"] == "pass"
    )
    if not args.output:
        try:
            output_path.unlink()
        except OSError:
            pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
