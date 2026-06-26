#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


EXCLUDE_DIRS = {"__pycache__", ".git", ".pre-cr", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
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


def check_package(package_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="tmcp-package-check-") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(package_path, "r:gz") as archive:
            archive.extractall(tmp_path, filter="data")
        plugin_root = tmp_path / "tmcp"
        install_ok, install_output = run(["python3", "scripts/check_install.py", "."], plugin_root)
        tests_ok, tests_output = run(["python3", "-m", "unittest", "discover", "-s", "tests"], plugin_root)
        compile_ok, compile_output = run(
            [
                "python3",
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
        launcher_ok, launcher_output = run(["node", "--check", "scripts/tmcp_launcher.mjs"], plugin_root)
    return {
        "install_check": "pass" if install_ok else "fail",
        "tests": "pass" if tests_ok else "fail",
        "compile": "pass" if compile_ok else "fail",
        "launcher_syntax": "pass" if launcher_ok else "fail",
        "output": {
            "install": install_output,
            "tests": tests_output,
            "compile": compile_output,
            "launcher_syntax": launcher_output,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and verify a TMCP release package.")
    parser.add_argument("plugin_root", nargs="?", default=".", help="Path to plugin root")
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
    )
    if not args.output:
        try:
            output_path.unlink()
        except OSError:
            pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
