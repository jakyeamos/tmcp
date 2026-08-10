#!/usr/bin/env python3
"""Run the read-only prerequisites gate for Codex validation tasks.

The gate checks the small set of Codex validation helpers and the free space on
the filesystem that will host the build.  It never installs tools, changes
environment state, or removes files.  A blocked result must be resolved before
dispatching a Codex validation task.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "tmcp-codex-validation-preflight-v0.1"
DESKTOP_BRIDGE_MANIFEST_SCHEMA = "tmcp-codex-desktop-bridge-build-v0.1"
DESKTOP_BRIDGE_SETUP_STATUS_METHOD = "thread/setupStatus/read"
GIB = 1024**3
DEFAULT_MIN_FREE_GIB = 80.0
DEFAULT_REQUIRED_TOOLS: tuple[str, ...] = ("just", "cargo-nextest", "dotslash")
TOOL_REMEDIATIONS = {
    "just": "cargo install --locked just",
    "cargo-nextest": "cargo install --locked cargo-nextest",
    "dotslash": "cargo install --locked dotslash",
}

FindTool = Callable[[str], str | None]
VersionProbe = Callable[[str], tuple[int, str, str]]
DiskUsage = Callable[[str | bytes | Path], Any]


def _single_line(value: str, *, limit: int = 200) -> str:
    """Keep tool-provided text bounded and free of control-line surprises."""

    return " ".join(value.split())[:limit]


def _first_nonempty_line(value: str) -> str:
    return next((line for line in value.splitlines() if line.strip()), "")


def _run_version(executable: str) -> tuple[int, str, str]:
    """Probe one executable without invoking a shell or inheriting its output."""

    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, "", ""
    return completed.returncode, completed.stdout, completed.stderr


def _tool_result(
    name: str,
    *,
    find_tool: FindTool,
    version_probe: VersionProbe,
) -> dict[str, object]:
    executable = find_tool(name)
    if not executable:
        return {
            "name": name,
            "status": "blocked",
            "reason": "executable not found",
            "remediation": TOOL_REMEDIATIONS.get(
                name, f"Install or expose {name} before dispatch."
            ),
        }

    return_code, stdout, stderr = version_probe(executable)
    version = _single_line(_first_nonempty_line(stdout) or _first_nonempty_line(stderr))
    if return_code != 0 or not version:
        return {
            "name": name,
            "status": "blocked",
            "reason": "--version probe failed",
            "remediation": TOOL_REMEDIATIONS.get(
                name, f"Repair or expose {name} before dispatch."
            ),
        }
    return {"name": name, "status": "pass", "version": version}


def _storage_result(
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
            "remediation": "Pass an existing filesystem path with --path.",
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
            f"Restore at least {minimum_free_gib:g} GiB on this filesystem; "
            "do not bypass the storage guard or remove data automatically."
        )
    return result


def _blocked_desktop_bridge(reason: str, remediation: str) -> dict[str, object]:
    return {
        "status": "blocked",
        "required": True,
        "reason": reason,
        "remediation": remediation,
    }


def _desktop_bridge_result(
    *,
    manifest_path: Path | None,
    source_path: Path | None,
    required: bool,
) -> dict[str, object]:
    """Validate an explicit, read-only Desktop bridge build descriptor.

    The preflight never executes commands from the descriptor. It only proves
    that an editable source root, build/test command declarations, and the
    canonical setup-status method are present and internally consistent.
    """

    requested = required or manifest_path is not None or source_path is not None
    if not requested:
        return {"status": "not_requested", "required": False}

    if manifest_path is None:
        return _blocked_desktop_bridge(
            "Desktop bridge build manifest was not provided",
            "Pass --desktop-bridge-manifest with a supported bridge build descriptor.",
        )

    manifest = manifest_path.expanduser()
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return _blocked_desktop_bridge(
            "Desktop bridge build manifest could not be read",
            "Pass a readable JSON Desktop bridge build descriptor.",
        )
    except json.JSONDecodeError:
        return _blocked_desktop_bridge(
            "Desktop bridge build manifest is not valid JSON",
            "Repair the Desktop bridge build descriptor before validation.",
        )

    if not isinstance(payload, dict):
        return _blocked_desktop_bridge(
            "Desktop bridge build manifest must be a JSON object",
            "Use the tmcp-codex-desktop-bridge-build-v0.1 manifest shape.",
        )
    if payload.get("schema") != DESKTOP_BRIDGE_MANIFEST_SCHEMA:
        return _blocked_desktop_bridge(
            "Desktop bridge build manifest uses an unsupported schema",
            "Use schema tmcp-codex-desktop-bridge-build-v0.1.",
        )
    allowed_fields = {
        "schema",
        "source_root",
        "protocol_method",
        "build_command",
        "test_command",
    }
    unexpected_fields = sorted(set(payload) - allowed_fields)
    if unexpected_fields:
        return _blocked_desktop_bridge(
            "Desktop bridge build manifest contains unsupported fields",
            "Remove fields outside the tmcp-codex-desktop-bridge-build-v0.1 shape.",
        )

    source_value = payload.get("source_root")
    if not isinstance(source_value, str) or not source_value.strip():
        return _blocked_desktop_bridge(
            "Desktop bridge build manifest has no source_root",
            "Declare the editable Desktop bridge source checkout in the manifest.",
        )
    source_root = Path(source_value).expanduser()
    if not source_root.is_absolute():
        source_root = manifest.parent / source_root
    source_root = source_root.resolve()

    if source_path is not None and source_path.expanduser().resolve() != source_root:
        return _blocked_desktop_bridge(
            "Desktop bridge source does not match the build manifest",
            "Pass the same source checkout as --desktop-bridge-source and source_root.",
        )
    if not source_root.is_dir():
        return _blocked_desktop_bridge(
            "Desktop bridge source checkout is not an existing directory",
            "Provide an editable Desktop bridge source checkout before validation.",
        )

    for command_name in ("build_command", "test_command"):
        command = payload.get(command_name)
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(part, str) or not part.strip() for part in command)
        ):
            return _blocked_desktop_bridge(
                f"Desktop bridge build manifest has no valid {command_name}",
                "Declare non-empty argv arrays for the supported bridge build lane.",
            )

    if payload.get("protocol_method") != DESKTOP_BRIDGE_SETUP_STATUS_METHOD:
        return _blocked_desktop_bridge(
            "Desktop bridge build manifest does not declare thread/setupStatus/read",
            "Set protocol_method to thread/setupStatus/read before validation.",
        )

    return {
        "status": "pass",
        "required": True,
        "manifest_path": str(manifest.resolve()),
        "source_root": str(source_root),
        "protocol_method": DESKTOP_BRIDGE_SETUP_STATUS_METHOD,
        "build_command_present": True,
        "test_command_present": True,
    }


def build_report(
    *,
    paths: Sequence[Path],
    minimum_free_gib: float = DEFAULT_MIN_FREE_GIB,
    required_tools: Sequence[str] = DEFAULT_REQUIRED_TOOLS,
    find_tool: FindTool = shutil.which,
    version_probe: VersionProbe = _run_version,
    disk_usage: DiskUsage = shutil.disk_usage,
    desktop_bridge_manifest: Path | None = None,
    desktop_bridge_source: Path | None = None,
    require_desktop_bridge: bool = False,
) -> dict[str, object]:
    """Build a deterministic, read-only preflight report.

    The injectable probes keep the gate's positive and negative behavior
    testable without installing software or changing the host filesystem.
    """

    if not math.isfinite(minimum_free_gib) or minimum_free_gib <= 0:
        raise ValueError("minimum_free_gib must be a positive finite number")

    tool_names = tuple(dict.fromkeys(required_tools))
    tool_results = [
        _tool_result(name, find_tool=find_tool, version_probe=version_probe)
        for name in tool_names
    ]
    storage_results = [
        _storage_result(
            path,
            minimum_free_gib=minimum_free_gib,
            disk_usage=disk_usage,
        )
        for path in paths
    ]
    desktop_bridge = _desktop_bridge_result(
        manifest_path=desktop_bridge_manifest,
        source_path=desktop_bridge_source,
        required=require_desktop_bridge,
    )
    toolchain_ok = all(item["status"] == "pass" for item in tool_results)
    storage_ok = bool(storage_results) and all(
        item["status"] == "pass" for item in storage_results
    )
    desktop_bridge_ok = desktop_bridge["status"] in {"pass", "not_requested"}
    remediation = [
        str(item["remediation"])
        for item in [*tool_results, *storage_results, desktop_bridge]
        if item.get("status") != "pass" and item.get("remediation")
    ]
    if not storage_results:
        remediation.append("Pass an existing filesystem path with --path.")
    ok = toolchain_ok and storage_ok and desktop_bridge_ok
    return {
        "schema": SCHEMA,
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "checks": {
            "toolchain": {
                "status": "pass" if toolchain_ok else "blocked",
                "required_tools": list(tool_names),
                "tools": tool_results,
            },
            "storage": {
                "status": "pass" if storage_ok else "blocked",
                "filesystems": storage_results,
            },
            "desktop_bridge": desktop_bridge,
        },
        "remediation": list(dict.fromkeys(remediation)),
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
            "Read-only Codex validation preflight; blocked results must be "
            "resolved before source validation or task dispatch."
        )
    )
    parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        help="Filesystem path to inspect; repeat for separate build/cache volumes.",
    )
    parser.add_argument(
        "--tool",
        dest="tools",
        action="append",
        help="Required executable to probe; repeat to replace the default set.",
    )
    parser.add_argument(
        "--min-free-gib",
        type=_positive_gib,
        default=DEFAULT_MIN_FREE_GIB,
        help=f"Minimum free space per path in GiB (default: {DEFAULT_MIN_FREE_GIB:g}).",
    )
    parser.add_argument(
        "--desktop-bridge-manifest",
        type=Path,
        help=(
            "Read-only Desktop bridge build descriptor; providing it enables the "
            "bridge ownership check."
        ),
    )
    parser.add_argument(
        "--desktop-bridge-source",
        type=Path,
        help="Editable Desktop bridge source root to match against the manifest.",
    )
    parser.add_argument(
        "--require-desktop-bridge",
        action="store_true",
        help="Fail closed unless a valid Desktop bridge build descriptor is present.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit one compact JSON line.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = tuple(Path(value).expanduser() for value in (args.paths or ["."]))
    tools = tuple(args.tools) if args.tools else DEFAULT_REQUIRED_TOOLS
    report = build_report(
        paths=paths,
        minimum_free_gib=args.min_free_gib,
        required_tools=tools,
        desktop_bridge_manifest=args.desktop_bridge_manifest,
        desktop_bridge_source=args.desktop_bridge_source,
        require_desktop_bridge=args.require_desktop_bridge,
    )
    if args.compact:
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
