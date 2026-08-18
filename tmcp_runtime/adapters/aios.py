"""Explicit, redaction-aware subprocess adapter for deprecated AIOS compatibility."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from tmcp_runtime.safety import redact_json_value, redact_path
from tmcp_runtime.safety.redaction import merge_redactions


def is_available(root: Path | None) -> bool:
    """Return whether an AIOS checkout exposes its Python entrypoint."""

    return root is not None and (root / "bin" / "aios.py").exists()


def should_use(adapter: str) -> bool:
    """Return whether the caller explicitly selected the AIOS adapter."""

    return adapter == "aios"


def command_redactions(args: list[str]) -> dict[str, int]:
    """Detect sensitive values before they can enter subprocess arguments."""

    redactions: dict[str, int] = {}
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == "--evidence-json" and index + 1 < len(args):
            evidence_json = args[index + 1]
            try:
                evidence_value = json.loads(evidence_json)
            except json.JSONDecodeError:
                evidence_value = evidence_json
            _, evidence_redactions = redact_json_value(evidence_value, enabled=True)
            merge_redactions(redactions, evidence_redactions)
            index += 2
            continue
        _, argument_redactions = redact_json_value(argument, enabled=True)
        merge_redactions(redactions, argument_redactions)
        index += 1
    return redactions


def run(
    args: list[str],
    *,
    root: Path | None,
    available: bool | None = None,
) -> dict[str, Any]:
    """Run an explicitly requested AIOS command with fail-closed input checks."""

    configured = is_available(root) if available is None else available
    if not configured:
        return {
            "ok": False,
            "adapter": "aios",
            "error": (
                "Deprecated AIOS adapter requested but its compatibility gate is "
                "disabled or AIOS_ROOT/bin/aios.py was not found."
            ),
            "aios_root": redact_path(root) if root is not None else None,
            "remediation": (
                "Continue with --adapter standalone. Temporary legacy compatibility "
                "requires both TMCP_ENABLE_DEPRECATED_AIOS_ADAPTER=1 and AIOS_ROOT "
                "pointing to an AIOS checkout."
            ),
        }
    redactions = command_redactions(args)
    if redactions:
        return {
            "ok": False,
            "adapter": "aios",
            "error": (
                "AIOS adapter cannot receive sensitive request values through "
                "command arguments."
            ),
            "remediation": (
                "Use --adapter standalone, or configure AIOS with a protected "
                "request-input protocol."
            ),
            "redaction_summary": redactions,
        }
    command = (
        ["uv", "run", "python", "bin/aios.py", *args]
        if shutil.which("uv")
        else [sys.executable, "bin/aios.py", *args]
    )
    try:
        completed = subprocess.run(
            command,
            cwd=cast(Path, root),
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "adapter": "aios",
            "error": "AIOS adapter command did not complete.",
            "error_type": type(exc).__name__,
        }
    if completed.returncode != 0:
        return {
            "ok": False,
            "adapter": "aios",
            "returncode": completed.returncode,
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": completed.stdout, "stderr": completed.stderr}
    if isinstance(payload, dict):
        response = cast(dict[str, object], payload)
        response.setdefault("ok", True)
        response.setdefault("adapter", "aios")
        return response
    return {"ok": True, "adapter": "aios", "data": payload}
