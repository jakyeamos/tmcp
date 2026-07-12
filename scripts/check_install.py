#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.tmcp_mcp_framing import encode_message  # noqa: E402
from tmcp_runtime.api.registry import PUBLIC_TOOL_NAMES  # noqa: E402


REQUIRED_FILES = (
    ".codex-plugin/plugin.json",
    ".mcp.json",
    "examples/workflows/adaptive-workflow-pack.md",
    "schemas/tmcp-adaptive-workflow-pack-v0.1.schema.json",
    "schemas/tmcp-composed-packet-v0.1.schema.json",
    "schemas/tmcp-promoted-harvest-graph-v0.1.schema.json",
    "schemas/tmcp-run-receipt-v0.1.schema.json",
    "schemas/tmcp-run-session-v0.1.schema.json",
    "schemas/tmcp-runtime-next-v0.1.schema.json",
    "scripts/tmcp_launcher.mjs",
    "scripts/tmcp_mcp_server.py",
    "scripts/release_package_compile.py",
    "scripts/release_package_composition.py",
    "scripts/release_package_sessions.py",
    "tmcp_runtime/domain/declared_loads.py",
    "tmcp_runtime/domain/composition.py",
    "tmcp_runtime/domain/families.py",
    "tmcp_runtime/domain/packets.py",
    "tmcp_runtime/domain/recompile.py",
    "tmcp_runtime/domain/review_profiles.py",
    "tmcp_runtime/domain/routes.py",
    "tmcp_runtime/domain/standalone_packets.py",
    "tmcp_runtime/api/registry.py",
    "tmcp_runtime/api/tool_schemas.py",
    "tmcp_runtime/safety/files.py",
    "tmcp_runtime/safety/fixed_files.py",
    "tmcp_runtime/safety/reader.py",
    "tmcp_runtime/storage/artifacts.py",
    "tmcp_runtime/storage/sessions.py",
    "skills/tmcp-adaptive-workflow-pack/SKILL.md",
    "skills/tmcp-agent-handoff/SKILL.md",
    "skills/tmcp-architecture-decision/SKILL.md",
    "skills/tmcp-custom-rubric-generator/SKILL.md",
    "skills/tmcp-data-integrity-audit/SKILL.md",
    "skills/tmcp-dx-audit/SKILL.md",
    "skills/tmcp-incident-postmortem/SKILL.md",
    "skills/tmcp-migration-readiness/SKILL.md",
    "skills/tmcp-performance-readiness/SKILL.md",
    "skills/tmcp-pr-risk-review/SKILL.md",
    "skills/tmcp-release-readiness/SKILL.md",
    "skills/tmcp-routing-policy-generator/SKILL.md",
    "skills/tmcp-security-privacy-audit/SKILL.md",
    "skills/tmcp-skill-harvest/SKILL.md",
    "skills/tmcp-skill-gap-analysis/SKILL.md",
    "skills/tmcp-test-strategy/SKILL.md",
    "skills/tmcp-ui-rubric/SKILL.md",
    "skills/tmcp-workflow-recommendation/SKILL.md",
    "skills/tmcp/SKILL.md",
)

EXPECTED_MCP_TOOLS = PUBLIC_TOOL_NAMES


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return payload


def framed_request(payload: dict[str, Any]) -> bytes:
    return encode_message(payload)


def parse_framed_response(stream: bytes) -> dict[str, Any]:
    header_end = stream.index(b"\r\n\r\n")
    headers = stream[:header_end].decode("ascii").split("\r\n")
    content_length = int(
        [
            header.split(":", 1)[1].strip()
            for header in headers
            if header.lower().startswith("content-length:")
        ][0]
    )
    start = header_end + 4
    return json.loads(stream[start : start + content_length].decode("utf-8"))


def check_plugin_root(plugin_root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (plugin_root / relative).exists():
            errors.append(f"missing required file: {relative}")
    if errors:
        return errors

    manifest = read_json(plugin_root / ".codex-plugin" / "plugin.json")
    if manifest.get("name") != "tmcp":
        errors.append("plugin manifest name must be 'tmcp'")
    if manifest.get("mcpServers") != "./.mcp.json":
        errors.append("plugin manifest mcpServers must point to './.mcp.json'")

    mcp_config = read_json(plugin_root / ".mcp.json")
    servers = mcp_config.get("mcpServers")
    if not isinstance(servers, dict) or "tmcp" not in servers:
        errors.append(".mcp.json must define mcpServers.tmcp")
    else:
        tmcp = servers["tmcp"]
        if not isinstance(tmcp, dict):
            errors.append("mcpServers.tmcp must be an object")
        else:
            if tmcp.get("type") != "stdio":
                errors.append(
                    "mcpServers.tmcp.type must be stdio for Codex MCP discovery"
                )
            if tmcp.get("command") != "node":
                errors.append("mcpServers.tmcp.command must be node")
            if tmcp.get("cwd") != ".":
                errors.append(
                    "mcpServers.tmcp.cwd must be '.' for portable plugin-root launch"
                )
            args = tmcp.get("args")
            if args != ["scripts/tmcp_launcher.mjs"]:
                errors.append(
                    "mcpServers.tmcp.args must use relative scripts/tmcp_launcher.mjs"
                )
    return errors


def check_mcp_launch(plugin_root: Path) -> tuple[bool, str]:
    env = os.environ.copy()
    env["AIOS_ROOT"] = "/tmp/tmcp-aios-missing"
    mcp_config = read_json(plugin_root / ".mcp.json")
    tmcp = mcp_config["mcpServers"]["tmcp"]
    command = tmcp["command"]
    args = tmcp["args"]
    if (
        not isinstance(command, str)
        or not isinstance(args, list)
        or not all(isinstance(arg, str) for arg in args)
    ):
        return False, ".mcp.json command and args must be strings"
    request = framed_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
    completed = subprocess.run(
        [command, *args],
        cwd=plugin_root,
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        return False, completed.stderr.decode("utf-8", errors="replace")
    try:
        response = parse_framed_response(completed.stdout)
    except Exception as exc:
        return False, f"could not parse MCP response: {exc}"
    result = response.get("result")
    if not isinstance(result, dict):
        return False, f"MCP response missing result: {response}"
    tools = result.get("tools")
    if not isinstance(tools, list):
        return False, f"MCP tools/list missing tools array: {response}"
    tool_names = {str(tool.get("name")) for tool in tools if isinstance(tool, dict)}
    missing = EXPECTED_MCP_TOOLS - tool_names
    if missing:
        return False, f"MCP tools/list missing tools: {sorted(missing)}"
    return True, "MCP tools/list passed without AIOS"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TMCP plugin install shape.")
    parser.add_argument(
        "plugin_root", nargs="?", default=".", help="Path to the TMCP plugin root"
    )
    args = parser.parse_args()
    plugin_root = Path(args.plugin_root).expanduser().resolve()
    errors = check_plugin_root(plugin_root)
    ok, message = check_mcp_launch(plugin_root) if not errors else (False, "")
    result = {
        "schema": "tmcp-install-check-v0.1",
        "plugin_root": str(plugin_root),
        "manifest": "pass" if not errors else "fail",
        "mcp_launch": "pass" if ok else "fail",
        "message": message,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors and ok else 1


if __name__ == "__main__":
    sys.exit(main())
