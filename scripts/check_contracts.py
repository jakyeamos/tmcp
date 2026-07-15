#!/usr/bin/env python3
"""Verify that every published TMCP transport contract has one owner."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.tmcp_mcp_framing import encode_message, read_message  # noqa: E402
from tmcp_runtime.api.registry import (  # noqa: E402
    PUBLIC_TOOL_NAMES,
    VERSION,
    mcp_server_info,
    mcp_tools,
)


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CITATION_VERSION_RE = re.compile(r'^version:\s*"?([^"\s]+)"?\s*$', re.MULTILINE)


def read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return payload


def json_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value


def check_semver() -> list[str]:
    if SEMVER_RE.fullmatch(VERSION.release) is None:
        return [f"canonical release version is not strict semver: {VERSION.release!r}"]
    expected_codex = f"{VERSION.release}+"
    if not VERSION.codex_plugin.startswith(expected_codex):
        return [
            "canonical Codex plugin version must use the release version plus build metadata"
        ]
    return []


def check_manifest_metadata(plugin_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        codex = read_json_object(plugin_root / ".codex-plugin" / "plugin.json")
        if codex.get("name") != VERSION.server_name:
            errors.append("Codex manifest name does not match canonical server name")
        if codex.get("version") != VERSION.codex_plugin:
            errors.append(
                "Codex manifest version does not match canonical Codex version"
            )
        if codex.get("mcpServers") != "./.mcp.json":
            errors.append("Codex manifest mcpServers must reference ./.mcp.json")

        claude = read_json_object(plugin_root / ".claude-plugin" / "plugin.json")
        if claude.get("version") != VERSION.release:
            errors.append(
                "Claude manifest version does not match canonical release version"
            )

        marketplace = read_json_object(
            plugin_root / ".claude-plugin" / "marketplace.json"
        )
        if marketplace.get("version") != VERSION.release:
            errors.append(
                "Claude marketplace version does not match canonical release version"
            )
        plugins = marketplace.get("plugins")
        if not isinstance(plugins, list):
            raise RuntimeError("Claude marketplace plugins must be an array")
        matches = [
            json_object(plugin, "Claude marketplace plugin")
            for plugin in plugins
            if isinstance(plugin, dict) and plugin.get("name") == VERSION.server_name
        ]
        if len(matches) != 1 or matches[0].get("version") != VERSION.release:
            errors.append(
                "Claude marketplace TMCP plugin version does not match release"
            )
        source = (
            json_object(matches[0].get("source"), "Claude marketplace TMCP source")
            if len(matches) == 1
            else {}
        )
        if (
            source.get("source") != "github"
            or source.get("repo") != "jakyeamos/tmcp"
            or source.get("ref") != f"v{VERSION.release}"
        ):
            errors.append(
                "Claude marketplace TMCP source must be the canonical GitHub repository pinned to the release tag"
            )

        registry = read_json_object(plugin_root / "mcp-registry" / "draft-server.json")
        if registry.get("version") != VERSION.release:
            errors.append(
                "MCP registry version does not match canonical release version"
            )
        packages = registry.get("packages")
        if not isinstance(packages, list) or not packages:
            raise RuntimeError("MCP registry packages must be a non-empty array")
        for index, package in enumerate(packages):
            package_object = json_object(package, f"MCP registry package {index}")
            if package_object.get("version") != VERSION.release:
                errors.append(
                    f"MCP registry package {index} version does not match canonical release version"
                )
        metadata = json_object(registry.get("_meta"), "MCP registry _meta")
        tool_names = metadata.get("io.github.jakyeamos.tmcp/toolNames")
        if not isinstance(tool_names, list) or set(tool_names) != PUBLIC_TOOL_NAMES:
            errors.append("MCP registry toolNames do not match the canonical registry")
        runtime = json_object(
            metadata.get("io.github.jakyeamos.tmcp/runtime"),
            "MCP registry runtime metadata",
        )
        if runtime.get("node") != VERSION.minimum_node:
            errors.append(
                "MCP registry Node policy does not match canonical version metadata"
            )
        if runtime.get("python") != VERSION.minimum_python:
            errors.append(
                "MCP registry Python policy does not match canonical version metadata"
            )

        citation_text = (plugin_root / "CITATION.cff").read_text(encoding="utf-8")
        citation_match = CITATION_VERSION_RE.search(citation_text)
        if citation_match is None or citation_match.group(1) != VERSION.release:
            errors.append(
                "CITATION.cff version does not match canonical release version"
            )

        evidence = read_json_object(plugin_root / "docs" / "RELEASE_EVIDENCE.json")
        if evidence.get("version") != VERSION.release:
            errors.append(
                "release evidence version does not match canonical release version"
            )
    except RuntimeError as exc:
        errors.append(str(exc))
    except FileNotFoundError as exc:
        errors.append(f"missing metadata file: {exc.filename}")
    return errors


def _hermetic_environment(temp_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    home = temp_root / "home"
    tmcp_home = temp_root / "tmcp-home"
    home.mkdir()
    tmcp_home.mkdir()
    environment["HOME"] = str(home)
    environment["TMCP_HOME"] = str(tmcp_home)
    environment["AIOS_ROOT"] = str(temp_root / "missing-aios")
    environment.pop("XDG_CONFIG_HOME", None)
    environment.pop("XDG_CACHE_HOME", None)
    return environment


def _mcp_responses(plugin_root: Path) -> list[dict[str, object]]:
    requests = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    raw = b"".join(encode_message(request) for request in requests)
    with tempfile.TemporaryDirectory(prefix="tmcp-contracts-") as temporary:
        completed = subprocess.run(
            ["node", "scripts/tmcp_launcher.mjs"],
            cwd=plugin_root,
            env=_hermetic_environment(Path(temporary)),
            input=raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP launcher exited {completed.returncode}: {stderr}")
    stream = io.BytesIO(completed.stdout)
    responses: list[dict[str, object]] = []
    while stream.tell() < len(completed.stdout):
        message = read_message(stream)
        if message is None:
            break
        if not isinstance(message, dict):
            raise RuntimeError("MCP launcher emitted a non-object response")
        responses.append(message)
    return responses


def check_transport(plugin_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        responses = _mcp_responses(plugin_root)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return [str(exc)]
    if len(responses) != 2:
        return [
            f"MCP launcher returned {len(responses)} contract responses; expected 2"
        ]
    initialize_result = responses[0].get("result")
    if not isinstance(initialize_result, dict):
        return ["MCP initialize response does not contain an object result"]
    if initialize_result.get("serverInfo") != mcp_server_info():
        errors.append(
            "MCP initialize serverInfo does not match canonical version metadata"
        )
    tools_result = responses[1].get("result")
    if not isinstance(tools_result, dict) or tools_result.get("tools") != mcp_tools():
        errors.append("MCP tools/list does not match the canonical tool registry")
    return errors


def check_install_contract() -> list[str]:
    from scripts.check_install import EXPECTED_MCP_TOOLS

    if EXPECTED_MCP_TOOLS != PUBLIC_TOOL_NAMES:
        return ["install check tool set does not derive from the canonical registry"]
    return []


def check_contracts(plugin_root: Path) -> dict[str, object]:
    errors = check_semver()
    errors.extend(check_manifest_metadata(plugin_root))
    errors.extend(check_install_contract())
    errors.extend(check_transport(plugin_root))
    return {
        "schema": "tmcp-contract-check-v0.1",
        "plugin_root": str(plugin_root),
        "version": VERSION.release,
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that TMCP's published metadata and live transports share one contract."
    )
    parser.add_argument(
        "plugin_root", nargs="?", default=".", help="Path to the TMCP plugin root"
    )
    args = parser.parse_args()
    result = check_contracts(Path(args.plugin_root).expanduser().resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
