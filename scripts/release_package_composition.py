"""Composition and runtime surface checks for release packages."""

from __future__ import annotations

from pathlib import Path

from scripts.release_package_sessions import RunJson, check_session_surface
from tmcp_runtime.storage import artifact_persistence_available


def check_composition_surface(
    plugin_root: Path,
    scratch_root: Path,
    run_json: RunJson,
) -> tuple[bool, str]:
    """Verify composition, session, runtime, receipt, and additive surfaces."""

    source_root = scratch_root / "composition-release-surface"
    tmcp_home = scratch_root / "tmcp-home"
    skill_root = source_root / "skills" / "impeccable"
    skill_root.mkdir(parents=True, exist_ok=True)
    (source_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Agent Rules",
                "Use pnpm only.",
                "Read before modifying and search existing behavior first.",
                "Release readiness requires CI evidence, package checks, changelog review, and hosted verification.",
            ]
        ),
        encoding="utf-8",
    )
    (skill_root / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: impeccable",
                "---",
                "# Impeccable",
                "For craft commands, run scripts/context.mjs and choose the brand or product register.",
                "Verify browser screenshots, contrast, reduced motion, and responsive behavior for UI work.",
            ]
        ),
        encoding="utf-8",
    )
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
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or compose is None:
        return False, output
    if compose.get("schema") != "tmcp-composed-packet-v0.1":
        return False, f"unexpected compose schema: {compose.get('schema')}"
    if not isinstance(compose.get("receipt_template"), dict):
        return False, "compose output missing receipt_template"
    if not isinstance(compose.get("compiled_from"), dict):
        return False, "compose output missing compiled_from"
    if not isinstance(compose.get("shortcut_candidate"), dict):
        return False, "compose output missing shortcut_candidate"
    packet_markdown = compose.get("packet_markdown")
    if not isinstance(packet_markdown, str) or "## Selection Rationale" not in packet_markdown:
        return False, "compose output missing packet_markdown rationale"
    packet_id = compose.get("packet_id")
    if compose["receipt_template"].get("packet_id") != packet_id:
        return False, "compose receipt_template did not retain packet_id"
    if not isinstance(compose.get("safety"), dict) or not compose["safety"]:
        return False, "compose output missing safety metadata"
    if not isinstance(packet_id, str) or packet_id not in packet_markdown:
        return False, "compose packet_markdown did not retain packet_id"
    verification_text = " ".join(compose.get("verification_gates", [])).lower()
    if "browser" in verification_text:
        return False, "release composition smoke unexpectedly activated browser gate"

    sessions_ok, session_mode = check_session_surface(
        plugin_root,
        source_root,
        tmcp_home,
        run_json,
    )
    if not sessions_ok:
        return False, session_mode

    ok, output, runtime = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "runtime-next",
            "Fix the dashboard UI bug",
            "--project-path",
            str(source_root),
            "--current-phase",
            "final",
            "--files-changed",
            "app/page.tsx",
            "--failures",
            "vitest failed",
            "--browser-evidence",
            "screenshot shows overlap",
            "--cache-policy",
            "none",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or runtime is None:
        return False, output
    if runtime.get("schema") != "tmcp-runtime-next-v0.1":
        return False, f"unexpected runtime-next schema: {runtime.get('schema')}"
    packet_delta = runtime.get("packet_delta")
    if not isinstance(packet_delta, dict):
        return False, "runtime-next output missing packet_delta"
    activated = set(packet_delta.get("activated_atoms", []))
    if not {
        "ui-browser-verification",
        "debugging-regression",
        "verification-before-completion",
    }.issubset(activated):
        return False, "runtime-next smoke missing contextual activated atoms"

    ok, output, receipt = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "record-receipt",
            str(compose.get("packet_id")),
            "--activated-atoms",
            "behavior-verification",
            "--commands-run",
            "python3 -m unittest",
            "--verification-results",
            "passed",
            "--outcome",
            "passed",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if artifact_persistence_available():
        if not ok or receipt is None:
            return False, output
        if receipt.get("schema") != "tmcp-run-receipt-v0.1":
            return False, f"unexpected receipt schema: {receipt.get('schema')}"
        receipt_json = receipt.get("artifact_paths", {}).get("receipt_json")
        if not isinstance(receipt_json, str) or not Path(receipt_json).exists():
            return False, "record-receipt did not write receipt_json"
    else:
        if ok or receipt is not None:
            return False, "record-receipt unexpectedly wrote an artifact on this platform"
        if "Secure artifact persistence" not in output:
            return False, f"record-receipt did not fail closed: {output}"
        if tmcp_home.exists() and any(tmcp_home.rglob("*")):
            return False, "record-receipt created artifacts despite unavailable persistence"

    ok, output, explain = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "explain",
            "Review release readiness",
            "--project-path",
            str(source_root),
            "--compose",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or explain is None:
        return False, output
    if explain.get("composed_packet", {}).get("schema") != "tmcp-composed-packet-v0.1":
        return False, "explain --compose output missing composed packet"

    ok, output, recommend = run_json(
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
            "--compose",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or recommend is None:
        return False, output
    if (
        recommend.get("composed_packet", {}).get("schema")
        != "tmcp-composed-packet-v0.1"
    ):
        return False, "recommend --compose output missing composed packet"
    persistence_mode = (
        "persistent receipt smoke passed"
        if artifact_persistence_available()
        else "portable receipt denial smoke passed"
    )
    return True, "\n".join(
        [output, persistence_mode, session_mode, "composition surface smoke passed"]
    )
