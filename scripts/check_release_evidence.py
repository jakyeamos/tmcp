#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tmcp_runtime.api.registry import VERSION  # noqa: E402

VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
EVIDENCE_PATH = Path("docs") / "RELEASE_EVIDENCE.json"
WORKFLOW_PATH = Path(".github") / "workflows" / "verify.yml"
WORKFLOW_CONTRACT_PATH = ".github/workflows/verify.yml"
REQUIRED_RELEASE_TAG_PATTERNS = ("v*", "[0-9]*")
REQUIRED_RELEASE_EVIDENCE_COMMAND = "python scripts/check_release_evidence.py ."
REQUIRED_RELEASE_EVIDENCE_STEP_NAME = "Active release evidence"
VERSION_SOURCES = (
    Path(".codex-plugin") / "plugin.json",
    Path(".claude-plugin") / "plugin.json",
    Path(".claude-plugin") / "marketplace.json",
    Path("mcp-registry") / "draft-server.json",
)


def read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return payload


def string_field(payload: dict[str, object], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{path} must define string field {key!r}")
    return value


def release_version(raw_version: str) -> str:
    release, separator, build = raw_version.partition("+")
    if separator and not build:
        raise RuntimeError(f"version has empty build metadata: {raw_version}")
    if VERSION_RE.fullmatch(release) is None:
        raise RuntimeError(f"version is not a semver release: {raw_version}")
    return release


def active_release_version(plugin_root: Path) -> tuple[str | None, list[str]]:
    versions: dict[str, str] = {}
    errors: list[str] = []
    for relative in VERSION_SOURCES:
        path = plugin_root / relative
        try:
            payload = read_json_object(path)
            versions[str(relative)] = release_version(
                string_field(payload, "version", path)
            )
        except RuntimeError as exc:
            errors.append(str(exc))
    unique_versions = sorted(set(versions.values()))
    if len(unique_versions) != 1:
        errors.append(f"release version mismatch across manifests: {versions}")
        return None, errors
    if unique_versions[0] != VERSION.release:
        errors.append(
            "release version does not match the canonical version descriptor: "
            f"{unique_versions[0]} != {VERSION.release}"
        )
    return unique_versions[0], errors


def workflow_has_release_tags(plugin_root: Path) -> list[str]:
    workflow = plugin_root / WORKFLOW_PATH
    try:
        text = workflow.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing workflow file: {WORKFLOW_CONTRACT_PATH}"]
    errors: list[str] = []
    for pattern in REQUIRED_RELEASE_TAG_PATTERNS:
        if pattern not in text:
            errors.append(
                f"{WORKFLOW_CONTRACT_PATH} does not include tag trigger pattern {pattern!r}"
            )
    return errors


def workflow_has_release_evidence_gate(plugin_root: Path) -> list[str]:
    workflow = plugin_root / WORKFLOW_PATH
    try:
        text = workflow.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"missing workflow file: {WORKFLOW_CONTRACT_PATH}"]
    lines = text.splitlines()
    errors: list[str] = []
    if not any(line.strip() == "pull_request:" for line in lines):
        errors.append(
            f"{WORKFLOW_CONTRACT_PATH} must verify release evidence on pull requests"
        )
    step_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == f"- name: {REQUIRED_RELEASE_EVIDENCE_STEP_NAME}"
        ),
        None,
    )
    if step_index is None:
        return errors + [
            f"{WORKFLOW_CONTRACT_PATH} must define an {REQUIRED_RELEASE_EVIDENCE_STEP_NAME!r} step"
        ]
    next_step = next(
        (
            index
            for index in range(step_index + 1, len(lines))
            if lines[index].startswith("      - ")
        ),
        len(lines),
    )
    step_lines = lines[step_index:next_step]
    if f"run: {REQUIRED_RELEASE_EVIDENCE_COMMAND}" not in {
        line.strip() for line in step_lines
    }:
        errors.append(
            f"{WORKFLOW_CONTRACT_PATH} must run {REQUIRED_RELEASE_EVIDENCE_COMMAND!r}"
        )
    if any(line.strip().startswith("if:") for line in step_lines):
        errors.append(
            f"{WORKFLOW_CONTRACT_PATH} must run active release evidence on pull requests"
        )
    return errors


def positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_hosted_evidence(
    plugin_root: Path, version: str, evidence: dict[str, object]
) -> list[str]:
    errors: list[str] = []
    schema = evidence.get("schema")
    if schema != "tmcp-release-evidence-v0.1":
        errors.append(
            "docs/RELEASE_EVIDENCE.json schema must be tmcp-release-evidence-v0.1"
        )
    if evidence.get("version") != version:
        errors.append(
            f"docs/RELEASE_EVIDENCE.json version must match active release {version}"
        )
    hosted = evidence.get("hosted_verification")
    if not isinstance(hosted, dict):
        return errors + [
            "docs/RELEASE_EVIDENCE.json hosted_verification must be an object"
        ]

    if hosted.get("workflow") != WORKFLOW_CONTRACT_PATH:
        errors.append(f"hosted_verification.workflow must be {WORKFLOW_CONTRACT_PATH}")
    if hosted.get("status") != "completed":
        errors.append("hosted_verification.status must be completed")
    if hosted.get("conclusion") != "success":
        errors.append("hosted_verification.conclusion must be success")

    run_id = hosted.get("run_id")
    if not positive_int(run_id):
        errors.append("hosted_verification.run_id must be a positive integer")
    url = hosted.get("url")
    if not isinstance(url, str) or not url:
        errors.append("hosted_verification.url must be a non-empty string")
    elif positive_int(run_id) and f"/actions/runs/{run_id}" not in url:
        errors.append("hosted_verification.url must contain the recorded run_id")

    source = hosted.get("source")
    ref = hosted.get("ref")
    if source == "tag":
        if ref not in {version, f"v{version}"}:
            errors.append(
                f"tag release evidence ref must be {version!r} or {f'v{version}'!r}"
            )
    elif source == "pull_request":
        if not isinstance(ref, str) or not ref:
            errors.append("pull request release evidence requires a non-empty ref")
        if not positive_int(hosted.get("pr_number")):
            errors.append("pull request release evidence requires a positive pr_number")
    elif source == "main":
        if ref != "main":
            errors.append("main release evidence ref must be 'main'")
        if hosted.get("pr_number") is not None:
            errors.append("main release evidence must not set pr_number")
    else:
        errors.append("hosted_verification.source must be tag, pull_request, or main")

    errors.extend(workflow_has_release_tags(plugin_root))
    errors.extend(workflow_has_release_evidence_gate(plugin_root))
    return errors


def check_release_evidence(plugin_root: Path) -> dict[str, object]:
    version, errors = active_release_version(plugin_root)
    if version is None:
        return {
            "schema": "tmcp-release-evidence-check-v0.1",
            "plugin_root": str(plugin_root),
            "active_version": None,
            "hosted_release_evidence": "fail",
            "errors": errors,
        }
    try:
        evidence = read_json_object(plugin_root / EVIDENCE_PATH)
    except RuntimeError as exc:
        errors.append(str(exc))
        evidence = {}
    if evidence:
        errors.extend(validate_hosted_evidence(plugin_root, version, evidence))
    return {
        "schema": "tmcp-release-evidence-check-v0.1",
        "plugin_root": str(plugin_root),
        "active_version": version,
        "hosted_release_evidence": "pass" if not errors else "fail",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that the active TMCP release has recorded hosted CI evidence."
    )
    parser.add_argument(
        "plugin_root", nargs="?", default=".", help="Path to the TMCP plugin root"
    )
    args = parser.parse_args()
    plugin_root = Path(args.plugin_root).expanduser().resolve()
    result = check_release_evidence(plugin_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["hosted_release_evidence"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
