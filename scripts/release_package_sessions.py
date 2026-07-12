"""Project-local packet-session smoke checks for release packages."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tmcp_runtime.storage import artifact_persistence_available


RunJson = Callable[
    [list[str], Path, dict[str, str] | None],
    tuple[bool, str, dict[str, Any] | None],
]


def check_session_surface(
    plugin_root: Path,
    source_root: Path,
    tmcp_home: Path,
    run_json: RunJson,
) -> tuple[bool, str]:
    """Verify the packaged compose-to-recompile session path."""

    session_id = "release-session"
    env = {"TMCP_HOME": str(tmcp_home)}
    ok, output, compose = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "compose-packet",
            "Improve release readiness before release",
            "--project-path",
            str(source_root),
            "--source-path",
            str(source_root),
            "--phase",
            "start",
            "--cache-policy",
            "none",
            "--session-id",
            session_id,
            "--compact",
        ],
        plugin_root,
        env,
    )
    if artifact_persistence_available():
        if not ok or compose is None:
            return False, output
        session = compose.get("session")
        if not isinstance(session, dict):
            return False, "session compose output missing session metadata"
        if session.get("record_schema") != "tmcp-run-session-v0.1":
            return False, "session compose record schema mismatch"
        if session.get("revision") != 1:
            return False, "session compose did not create revision 1"
        session_path = session.get("path")
        if not isinstance(session_path, str) or not Path(session_path).is_file():
            return False, "session compose did not write its project-local record"
        if session_id in Path(session_path).name:
            return False, "session compose exposed the raw session identifier"

        ok, output, recompile = run_json(
            [
                "node",
                "scripts/tmcp_launcher.mjs",
                "recompile-packet",
                "Improve release readiness before release",
                "--project-path",
                str(source_root),
                "--source-path",
                str(source_root),
                "--current-phase",
                "verification",
                "--files-changed",
                "scripts/check_release_package.py",
                "--cache-policy",
                "none",
                "--session-id",
                session_id,
                "--compact",
            ],
            plugin_root,
            env,
        )
        if not ok or recompile is None:
            return False, output
        updated_session = recompile.get("session")
        if not isinstance(updated_session, dict) or updated_session.get("revision") != 2:
            return False, "session recompile did not update revision 2"
        serialized_session = Path(session_path).read_text(encoding="utf-8")
        if session_id in serialized_session:
            return False, "session record exposed the raw session identifier"
        return True, "project-local session smoke passed"

    if ok or compose is not None:
        return False, "session compose unexpectedly wrote an artifact on this platform"
    if "Secure artifact persistence" not in output:
        return False, f"session compose did not fail closed: {output}"
    if (source_root / ".tmcp").exists():
        return False, "session compose created artifacts despite unavailable persistence"
    return True, "portable session denial smoke passed"
