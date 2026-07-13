"""Pure report assembly for TMCP readiness and capability diagnostics."""

from __future__ import annotations

from typing import Any


def build_doctor_report(
    client: str,
    plugin_root_display: str,
    *,
    plugin_root_exists: bool,
    node_launcher_exists: bool,
    node_available: bool,
    python_server_exists: bool,
    python_available: bool,
    artifact_persistence: bool,
    aios_available: bool,
    aios_root_display: str | None,
) -> dict[str, Any]:
    """Assemble a doctor response from adapter-supplied environment facts."""

    normalized_checks: list[dict[str, object]] = [
        {
            "id": "plugin_root",
            "status": "pass" if plugin_root_exists else "fail",
            "detail": plugin_root_display,
        },
        {
            "id": "node_launcher",
            "status": "pass" if node_launcher_exists else "fail",
            "detail": "scripts/tmcp_launcher.mjs",
        },
        {
            "id": "node_runtime",
            "status": "pass" if node_available else "fail",
            "detail": "Install Node.js 20+ if the MCP host cannot launch node.",
        },
        {
            "id": "python_server",
            "status": "pass" if python_server_exists else "fail",
            "detail": "scripts/tmcp_mcp_server.py",
        },
        {
            "id": "python_runtime",
            "status": "pass" if python_available else "fail",
            "detail": "Set TMCP_PYTHON if automatic Python discovery fails.",
        },
        {
            "id": "secure_artifact_persistence",
            "status": "pass" if artifact_persistence else "limited",
            "detail": (
                "Secure local artifact writes are available."
                if artifact_persistence
                else "Secure artifact writes are unavailable on this platform; "
                "rerun write-capable tools with write_artifacts=false."
            ),
        },
        {
            "id": "aios_adapter",
            "status": "pass" if aios_available else "optional",
            "detail": (
                f"AIOS_ROOT={aios_root_display}"
                if aios_root_display is not None
                else "AIOS_ROOT is not set; standalone TMCP is available."
            ),
        },
    ]
    failed = [
        check for check in normalized_checks if check.get("status") == "fail"
    ]
    install_paths = {
        "skill_only": (
            "Copy skills/tmcp into a skills directory. Use manual packet synthesis "
            "unless the host also exposes this package's launcher."
        ),
        "repo_checkout": (
            "Clone TMCP and run node scripts/tmcp_launcher.mjs doctor from the repo root."
        ),
        "codex_plugin_cache": (
            "Install as a Codex plugin; MCP config should launch relative "
            "scripts/tmcp_launcher.mjs from the plugin root."
        ),
        "claude_code": "Run: claude plugin marketplace add jakyeamos/tmcp && claude plugin install tmcp@tmcp",
        "claude_desktop": "Add the node launcher as a local stdio MCP server in claude_desktop_config.json.",
        "plain_mcp": "Use command node with args [scripts/tmcp_launcher.mjs] and cwd set to the TMCP repo.",
        "aios_backed": (
            "Set AIOS_ROOT explicitly only when you want optional AIOS storage/adapter behavior."
        ),
    }
    codex_tool_discovery = {
        "known_gap": (
            "Some Codex personal-plugin installs expose TMCP skills while deferred "
            "tool discovery does not surface the plugin MCP tools. In that case, "
            "the installed launcher can still be used directly."
        ),
        "symptom": (
            "tool_search for tmcp_explain, tmcp_doctor, or "
            "expert_rubric_review_plan returns no TMCP tools."
        ),
        "verify_launcher": [
            "node scripts/tmcp_launcher.mjs doctor --client codex",
            "node scripts/tmcp_launcher.mjs list-tools",
        ],
        "codex_mcp_config": {
            "mcp_servers": {
                "tmcp": {
                    "command": "node",
                    "args": ["scripts/tmcp_launcher.mjs"],
                    "cwd": plugin_root_display,
                }
            }
        },
        "fallback": (
            "Run the equivalent node scripts/tmcp_launcher.mjs CLI command from "
            "the TMCP plugin root, then cite the generated JSON/artifacts in the "
            "agent response."
        ),
    }
    return {
        "ok": not failed,
        "schema": "tmcp-doctor-v0.1",
        "client": client,
        "plugin_root": plugin_root_display,
        "checks": normalized_checks,
        "recommended_install_paths": install_paths,
        "codex_tool_discovery": codex_tool_discovery
        if client in {"auto", "codex"}
        else None,
        "smoke_test": {
            "tool": "tmcp_status",
            "expected": "structuredContent.standalone.available == true",
        },
        "next_action": (
            "Run tmcp_status, then tmcp_explain with your objective."
            if not failed
            else "Fix failing checks, then rerun tmcp_doctor."
        ),
        "missing_launcher_remediation": (
            "If no MCP tool, local CLI, repo/plugin launcher, or AIOS adapter is available, "
            "clone or copy TMCP, run node scripts/tmcp_launcher.mjs doctor from the TMCP root, "
            "and set TMCP_PYTHON if Python discovery fails. Until then, synthesize packets "
            "manually using sources inspected, skipped sources, packet summary, behavior atoms, "
            "evidence gaps, recommendation/remediation, and verification expectations."
        ),
    }


def build_status_report(
    plugin_root_display: str,
    artifact_persistence: bool,
    aios_available: bool,
    *,
    aios_root_display: str | None,
) -> dict[str, Any]:
    """Assemble a status response from adapter-supplied capability facts."""

    capabilities = [
        "packet_compile",
        "packet_composition",
        "runtime_next",
        "receipt_recording",
        "portable_skill_harvest",
        "multi_root_harvest",
        "global_cache",
        "source_type_classification",
        "workflow_recommendation",
        "harvest_promotion",
        "expert_rubric_review_plan",
    ]
    if artifact_persistence:
        capabilities.append("artifact_write")
    return {
        "ok": True,
        "schema": "tmcp-status-v0.1",
        "standalone": {
            "available": True,
            "plugin_root": plugin_root_display,
            "capabilities": capabilities,
            "artifact_persistence": {
                "available": artifact_persistence,
                "detail": (
                    "Secure descriptor-relative no-follow artifact writes are available."
                    if artifact_persistence
                    else "Secure artifact writes are unavailable on this platform; "
                    "write-capable tools fail closed."
                ),
            },
        },
        "aios_adapter": {
            "available": aios_available,
            "aios_root": aios_root_display,
            "configured": aios_root_display is not None,
            "role": "optional storage and adapter layer",
        },
    }
