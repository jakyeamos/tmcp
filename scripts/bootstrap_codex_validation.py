#!/usr/bin/env python3
"""Bootstrap an isolated, prerequisite-first Codex validation toolchain.

Unlike ``check_codex_validation_preflight.py``, this command may install the
toolchain, but only after storage, source-root, and external-tool checks pass.
Installs are rooted in an explicit task-local directory and never use the
user's global Cargo root.  The caller supplies the versions in a small JSON
lock file so the bootstrap cannot silently select a moving tool version.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA = "tmcp-codex-validation-bootstrap-v0.1"
TOOLCHAIN_SCHEMA = "tmcp-codex-validation-toolchain-v0.1"
DEFAULT_MIN_FREE_GIB = 80.0
DEFAULT_EXTERNAL_TOOLS: tuple[str, ...] = ("bazel",)
GIB = 1024**3
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")

FindTool = Callable[[str], str | None]
DiskUsage = Callable[[str | bytes | Path], Any]
Runner = Callable[[Sequence[str], Path | None, Mapping[str, str] | None], Any]


def _single_line(value: str, *, limit: int = 200) -> str:
    return " ".join(value.split())[:limit]


def _first_nonempty_line(value: str) -> str:
    return next((line for line in value.splitlines() if line.strip()), "")


def _run_command(
    argv: Sequence[str],
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            capture_output=True,
            check=False,
            text=True,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(
            list(argv),
            returncode=1,
            stdout="",
            stderr=str(exc),
        )


def _probe_version(
    executable: str,
    *,
    runner: Runner,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    completed = runner([executable, "--version"], None, env)
    return (
        int(getattr(completed, "returncode", 1)),
        str(getattr(completed, "stdout", "")),
        str(getattr(completed, "stderr", "")),
    )


def _version_matches(output: str, expected: str) -> bool:
    return (
        re.search(rf"(?<![A-Za-z0-9]){re.escape(expected)}(?![A-Za-z0-9])", output)
        is not None
    )


def _safe_name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or SAFE_NAME.fullmatch(value) is None:
        raise ValueError(f"toolchain {field} must be a safe non-empty name")
    return value


def load_toolchain(path: Path) -> list[dict[str, str]]:
    """Load and validate the caller-owned version lock without side effects."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("toolchain lock could not be read as JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema") != TOOLCHAIN_SCHEMA:
        raise ValueError(f"toolchain lock must use {TOOLCHAIN_SCHEMA}")
    raw_tools = payload.get("tools")
    if not isinstance(raw_tools, list) or not raw_tools:
        raise ValueError("toolchain lock tools must be a non-empty array")

    tools: list[dict[str, str]] = []
    names: set[str] = set()
    for raw in raw_tools:
        if not isinstance(raw, dict):
            raise ValueError("each toolchain entry must be an object")
        name = _safe_name(raw.get("name"), "name")
        package = _safe_name(raw.get("package"), "package")
        executable = _safe_name(raw.get("executable", name), "executable")
        version = raw.get("version")
        if (
            not isinstance(version, str)
            or not version.strip()
            or any(character.isspace() for character in version)
        ):
            raise ValueError("toolchain version must be a non-empty token")
        if name in names:
            raise ValueError(f"duplicate toolchain entry: {name}")
        names.add(name)
        tools.append(
            {
                "name": name,
                "package": package,
                "executable": executable,
                "version": version,
            }
        )
    return tools


def _resolve_inside(path: Path) -> Path:
    return path.expanduser().resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _storage_check(
    path: Path,
    *,
    minimum_free_gib: float,
    disk_usage: DiskUsage,
) -> dict[str, object]:
    try:
        usage = disk_usage(path)
        free_bytes = int(usage.free)
    except (OSError, TypeError, ValueError):
        return {
            "path": str(path),
            "status": "blocked",
            "reason": "filesystem usage could not be inspected",
            "minimum_free_gib": minimum_free_gib,
            "remediation": "Pass existing filesystem paths for --source-root and --tool-dir.",
        }
    free_gib = free_bytes / GIB
    status = "pass" if free_gib >= minimum_free_gib else "blocked"
    result: dict[str, object] = {
        "path": str(path),
        "status": status,
        "free_bytes": free_bytes,
        "free_gib": round(free_gib, 2),
        "minimum_free_gib": minimum_free_gib,
    }
    if status == "blocked":
        result["reason"] = "free space is below the configured floor"
        result["remediation"] = (
            f"Restore at least {minimum_free_gib:g} GiB before installing validation tools; "
            "the bootstrap will not remove data automatically."
        )
    return result


def _external_result(
    name: str,
    *,
    find_tool: FindTool,
    runner: Runner,
) -> dict[str, object]:
    executable = find_tool(name)
    if not executable:
        return {
            "name": name,
            "status": "blocked",
            "reason": "executable not found",
            "remediation": f"Install or expose {name} before validation bootstrap.",
        }
    return_code, stdout, stderr = _probe_version(executable, runner=runner)
    version = _single_line(_first_nonempty_line(stdout) or _first_nonempty_line(stderr))
    if return_code != 0 or not version:
        return {
            "name": name,
            "status": "blocked",
            "reason": "--version probe failed",
            "remediation": f"Repair or expose {name} before validation bootstrap.",
        }
    return {"name": name, "status": "pass", "version": version}


def _tool_result(
    spec: Mapping[str, str],
    *,
    bin_dir: Path,
    runner: Runner,
    env: Mapping[str, str],
) -> dict[str, object]:
    executable = bin_dir / spec["executable"]
    if not executable.exists():
        return {
            "name": spec["name"],
            "package": spec["package"],
            "expected_version": spec["version"],
            "status": "blocked",
            "reason": "task-local executable not found after install",
            "remediation": f"Install {spec['package']} into the reported task-local tool directory.",
        }
    return_code, stdout, stderr = _probe_version(
        str(executable), runner=runner, env=env
    )
    version_output = _single_line(
        _first_nonempty_line(stdout) or _first_nonempty_line(stderr)
    )
    if return_code != 0 or not _version_matches(version_output, spec["version"]):
        return {
            "name": spec["name"],
            "package": spec["package"],
            "expected_version": spec["version"],
            "status": "blocked",
            "reason": "task-local --version did not match the locked version",
            "remediation": f"Reinstall {spec['package']} at locked version {spec['version']}.",
        }
    return {
        "name": spec["name"],
        "package": spec["package"],
        "expected_version": spec["version"],
        "status": "pass",
        "version": version_output,
        "executable": str(executable),
    }


def _blocked_report(
    *,
    source_root: Path,
    tool_dir: Path,
    toolchain_path: Path,
    checks: dict[str, object],
    remediation: Sequence[str],
    commands: Sequence[Sequence[str]] = (),
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "ok": False,
        "status": "blocked",
        "source_root": str(source_root),
        "toolchain_path": str(toolchain_path),
        "tool_dir": str(tool_dir),
        "checks": checks,
        "commands": [list(command) for command in commands],
        "remediation": list(dict.fromkeys(remediation)),
    }


def build_report(
    *,
    source_root: Path,
    toolchain_path: Path,
    tool_dir: Path,
    minimum_free_gib: float = DEFAULT_MIN_FREE_GIB,
    external_tools: Sequence[str] = DEFAULT_EXTERNAL_TOOLS,
    find_tool: FindTool = shutil.which,
    disk_usage: DiskUsage = shutil.disk_usage,
    runner: Runner = _run_command,
) -> dict[str, object]:
    """Check prerequisites, then install and smoke-test a task-local toolchain."""

    if not math.isfinite(minimum_free_gib) or minimum_free_gib <= 0:
        raise ValueError("minimum_free_gib must be a positive finite number")
    source = _resolve_inside(source_root)
    lock = _resolve_inside(toolchain_path)
    local_tools = _resolve_inside(tool_dir)
    if not source.is_dir() or not (source / "justfile").is_file():
        return _blocked_report(
            source_root=source,
            tool_dir=local_tools,
            toolchain_path=lock,
            checks={
                "source": {
                    "status": "blocked",
                    "reason": "source root is missing a justfile",
                }
            },
            remediation=["Pass the Codex checkout root containing its justfile."],
        )
    if _is_relative_to(local_tools, source):
        return _blocked_report(
            source_root=source,
            tool_dir=local_tools,
            toolchain_path=lock,
            checks={
                "source": {"status": "pass"},
                "tool_dir": {
                    "status": "blocked",
                    "reason": "task-local tool directory must not be inside source root",
                },
            },
            remediation=[
                "Choose a separate task-local tool directory outside the source checkout."
            ],
        )
    try:
        specs = load_toolchain(lock)
    except ValueError as exc:
        return _blocked_report(
            source_root=source,
            tool_dir=local_tools,
            toolchain_path=lock,
            checks={
                "source": {"status": "pass"},
                "toolchain_lock": {"status": "blocked", "reason": str(exc)},
            },
            remediation=["Provide a valid caller-owned toolchain lock JSON."],
        )
    if not any(spec["name"] == "just" for spec in specs):
        return _blocked_report(
            source_root=source,
            tool_dir=local_tools,
            toolchain_path=lock,
            checks={
                "source": {"status": "pass", "marker": "justfile"},
                "toolchain_lock": {
                    "status": "blocked",
                    "reason": "toolchain lock must include just for source smoke",
                },
            },
            remediation=["Include the locked just package in the toolchain JSON."],
        )

    storage_paths = tuple(dict.fromkeys((source, local_tools.parent)))
    storage_results = [
        _storage_check(path, minimum_free_gib=minimum_free_gib, disk_usage=disk_usage)
        for path in storage_paths
    ]
    required_external = tuple(dict.fromkeys(("cargo", *external_tools)))
    external_results = [
        _external_result(name, find_tool=find_tool, runner=runner)
        for name in required_external
    ]
    storage_ok = all(item["status"] == "pass" for item in storage_results)
    external_ok = all(item["status"] == "pass" for item in external_results)
    checks: dict[str, object] = {
        "source": {"status": "pass", "marker": "justfile"},
        "storage": {
            "status": "pass" if storage_ok else "blocked",
            "filesystems": storage_results,
        },
        "external_tools": {
            "status": "pass" if external_ok else "blocked",
            "tools": external_results,
        },
        "toolchain_lock": {
            "status": "pass",
            "path": str(lock),
            "tools": specs,
        },
    }
    preflight_remediation = [
        str(item["remediation"])
        for item in [*storage_results, *external_results]
        if item.get("status") != "pass" and item.get("remediation")
    ]
    if not storage_ok or not external_ok:
        return _blocked_report(
            source_root=source,
            tool_dir=local_tools,
            toolchain_path=lock,
            checks=checks,
            remediation=preflight_remediation,
        )

    local_bin = local_tools / "bin"
    cargo_home = local_tools / "cargo-home"
    try:
        local_bin.mkdir(parents=True, exist_ok=True)
        cargo_home.mkdir(parents=True, exist_ok=True)
    except OSError:
        checks["installation"] = {
            "status": "blocked",
            "reason": "task-local tool directory could not be created",
        }
        return _blocked_report(
            source_root=source,
            tool_dir=local_tools,
            toolchain_path=lock,
            checks=checks,
            remediation=["Choose a writable task-local tool directory."],
        )

    existing_path = os.environ.get("PATH", "")
    path_prefix = os.pathsep.join(
        item for item in (str(local_bin), existing_path) if item
    )
    install_env = dict(os.environ)
    install_env.update(
        {
            "PATH": path_prefix,
            "CARGO_HOME": str(cargo_home),
        }
    )
    commands: list[list[str]] = []
    local_results: list[dict[str, object]] = []
    for spec in specs:
        current = _tool_result(spec, bin_dir=local_bin, runner=runner, env=install_env)
        if current["status"] != "pass":
            command = [
                str(find_tool("cargo") or "cargo"),
                "install",
                "--locked",
                "--root",
                str(local_tools),
                spec["package"],
                "--version",
                spec["version"],
            ]
            commands.append(command)
            completed = runner(command, source, install_env)
            if int(getattr(completed, "returncode", 1)) != 0:
                local_results.append(
                    {
                        "name": spec["name"],
                        "package": spec["package"],
                        "expected_version": spec["version"],
                        "status": "blocked",
                        "reason": "locked tool installation failed",
                        "remediation": "Repair the toolchain/network/cache and rerun this bootstrap.",
                    }
                )
                checks["installation"] = {
                    "status": "blocked",
                    "tools": local_results,
                }
                return _blocked_report(
                    source_root=source,
                    tool_dir=local_tools,
                    toolchain_path=lock,
                    checks=checks,
                    remediation=[
                        "Repair the toolchain/network/cache and rerun this bootstrap."
                    ],
                    commands=commands,
                )
        local_results.append(
            _tool_result(spec, bin_dir=local_bin, runner=runner, env=install_env)
        )
    local_ok = all(item["status"] == "pass" for item in local_results)
    checks["installation"] = {
        "status": "pass" if local_ok else "blocked",
        "tools": local_results,
    }
    if not local_ok:
        return _blocked_report(
            source_root=source,
            tool_dir=local_tools,
            toolchain_path=lock,
            checks=checks,
            remediation=[
                "Repair the task-local tool installation and rerun this bootstrap."
            ],
            commands=commands,
        )

    bare_smoke_results: list[dict[str, object]] = []
    for spec in specs:
        smoke_command = [spec["executable"], "--version"]
        commands.append(smoke_command)
        smoke = runner(smoke_command, source, install_env)
        smoke_ok = int(getattr(smoke, "returncode", 1)) == 0
        bare_smoke_results.append(
            {
                "name": spec["name"],
                "status": "pass" if smoke_ok else "blocked",
                "command": smoke_command,
                "reason": None if smoke_ok else "task-local bare command smoke failed",
            }
        )
    just_command = ["just", "--list"]
    commands.append(just_command)
    smoke = runner(just_command, source, install_env)
    just_smoke_ok = int(getattr(smoke, "returncode", 1)) == 0
    bare_smoke_results.append(
        {
            "name": "justfile",
            "status": "pass" if just_smoke_ok else "blocked",
            "command": just_command,
            "reason": None if just_smoke_ok else "task-local just --list smoke failed",
        }
    )
    smoke_ok = all(item["status"] == "pass" for item in bare_smoke_results)
    checks["source_smoke"] = {
        "status": "pass" if smoke_ok else "blocked",
        "commands": bare_smoke_results,
    }
    if not smoke_ok:
        return _blocked_report(
            source_root=source,
            tool_dir=local_tools,
            toolchain_path=lock,
            checks=checks,
            remediation=[
                "Repair the Codex checkout's justfile or validation prerequisites."
            ],
            commands=commands,
        )
    return {
        "schema": SCHEMA,
        "ok": True,
        "status": "ready",
        "source_root": str(source),
        "toolchain_path": str(lock),
        "tool_dir": str(local_tools),
        "path_prefix": path_prefix,
        "checks": checks,
        "commands": [list(command) for command in commands],
        "remediation": [],
    }


def _positive_gib(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive finite number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap a locked Codex validation toolchain in a task-local directory; "
            "storage and external tools are checked before installation."
        )
    )
    parser.add_argument("--source-root", "--path", required=True, dest="source_root")
    parser.add_argument(
        "--toolchain", required=True, help="Caller-owned version lock JSON."
    )
    parser.add_argument(
        "--tool-dir",
        help="Task-local install root (default: a new directory under the system temp root).",
    )
    parser.add_argument(
        "--external-tool",
        action="append",
        help="External executable to require; repeat to replace the default bazel check.",
    )
    parser.add_argument(
        "--no-external-tools",
        action="store_true",
        help="Skip external executable checks other than cargo (not suitable for full Codex validation).",
    )
    parser.add_argument(
        "--min-free-gib",
        type=_positive_gib,
        default=DEFAULT_MIN_FREE_GIB,
        help=f"Minimum free space per filesystem in GiB (default: {DEFAULT_MIN_FREE_GIB:g}).",
    )
    parser.add_argument(
        "--compact", action="store_true", help="Emit one compact JSON line."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tool_dir = (
        Path(args.tool_dir).expanduser()
        if args.tool_dir
        else Path(tempfile.gettempdir()) / f"tmcp-codex-validation-{uuid.uuid4().hex}"
    )
    if args.no_external_tools:
        external_tools: Sequence[str] = ()
    elif args.external_tool:
        external_tools = tuple(args.external_tool)
    else:
        external_tools = DEFAULT_EXTERNAL_TOOLS
    report = build_report(
        source_root=Path(args.source_root),
        toolchain_path=Path(args.toolchain),
        tool_dir=tool_dir,
        minimum_free_gib=args.min_free_gib,
        external_tools=external_tools,
    )
    if args.compact:
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
