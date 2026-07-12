#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tmcp_release_archive import (  # noqa: E402
    PACKAGE_POLICY_VERSION,
    ReleasePackageError,
    check_archive_manifest,
    create_package,
    safe_extractall,
    should_include,
    verify_reproducibility,
)
from scripts.release_package_compile import compile_command  # noqa: E402
from tmcp_runtime.storage import artifact_persistence_available  # noqa: E402

HARDCODED_USER_PATH_PATTERNS = (
    re.compile(r"/" r"Users/(?!example\b|you\b|your\b|name\b)[^\s)\"'`]+"),
    re.compile(r"~/" r"AIOS"),
)
PRIVATE_NAME_PATTERNS = (
    re.compile(r"\bHoopscout\b"),
    re.compile(r"\bCrimClock\b"),
)
STABLE_SKILLS = {
    "tmcp",
    "tmcp-skill-harvest",
    "tmcp-workflow-recommendation",
    "tmcp-release-readiness",
    "tmcp-dx-audit",
}
EXPERIMENTAL_SKILLS = {
    "tmcp-adaptive-workflow-pack",
    "tmcp-agent-handoff",
    "tmcp-architecture-decision",
    "tmcp-custom-rubric-generator",
    "tmcp-data-integrity-audit",
    "tmcp-incident-postmortem",
    "tmcp-migration-readiness",
    "tmcp-performance-readiness",
    "tmcp-pr-risk-review",
    "tmcp-routing-policy-generator",
    "tmcp-security-privacy-audit",
    "tmcp-skill-gap-analysis",
    "tmcp-test-strategy",
    "tmcp-ui-rubric",
}
PACKAGE_CHECK_NAMES = (
    "archive_manifest", "install_check", "tests", "compile",
    "launcher_syntax", "frontmatter", "hardcoded_user_paths",
    "private_names", "markdown_links", "doctor_surface",
    "sample_harvest", "sample_expert_rubric",
    "adaptive_workflow_surface", "composition_surface",
)
def run(
    command: list[str], cwd: Path, extra_env: dict[str, str] | None = None
) -> tuple[bool, str]:
    env = os.environ.copy()
    env.pop("AIOS_ROOT", None)
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    return completed.returncode == 0, completed.stdout + completed.stderr


def run_json(
    command: list[str], cwd: Path, extra_env: dict[str, str] | None = None
) -> tuple[bool, str, dict[str, Any] | None]:
    env = os.environ.copy()
    env.pop("AIOS_ROOT", None)
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        return False, output, None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return False, f"could not parse JSON output: {exc}\n{output}", None
    if not isinstance(payload, dict):
        return False, f"JSON output must be an object\n{output}", None
    return True, output, payload


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise RuntimeError(f"{path} missing frontmatter")
    end = text.find("\n---", 4)
    if end == -1:
        raise RuntimeError(f"{path} frontmatter is not closed")
    frontmatter: dict[str, str] = {}
    for raw_line in text[4:end].splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip("\"'")
    return frontmatter


def check_frontmatter_and_workflow_status(plugin_root: Path) -> tuple[bool, str]:
    errors: list[str] = []
    statuses: dict[str, str] = {}
    for path in sorted((plugin_root / "skills").glob("*/SKILL.md")):
        try:
            frontmatter = parse_frontmatter(path)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        name = frontmatter.get("name", "")
        status = frontmatter.get("status", "")
        if not name:
            errors.append(f"{path} missing name")
        if not frontmatter.get("description"):
            errors.append(f"{path} missing description")
        if status not in {"stable", "experimental"}:
            errors.append(f"{path} status must be stable or experimental")
        statuses[name] = status
        if status == "experimental" and "Status: experimental." not in path.read_text(
            encoding="utf-8"
        ):
            errors.append(f"{path} missing visible experimental status note")
    for name in sorted(STABLE_SKILLS):
        if statuses.get(name) != "stable":
            errors.append(f"{name} must be marked stable")
    for name in sorted(EXPERIMENTAL_SKILLS):
        if statuses.get(name) != "experimental":
            errors.append(f"{name} must be marked experimental")
    workflows_ref = plugin_root / "skills" / "tmcp" / "references" / "workflows.md"
    if not workflows_ref.exists():
        errors.append("skills/tmcp/references/workflows.md missing")
    else:
        text = workflows_ref.read_text(encoding="utf-8").lower()
        if (
            "stable public workflows" not in text
            or "experimental workflows" not in text
        ):
            errors.append(
                "workflows reference must separate stable and experimental workflows"
            )
    return not errors, "\n".join(errors)


def iter_shipped_text_files(plugin_root: Path) -> list[Path]:
    suffixes = {".md", ".json", ".toml", ".py", ".mjs", ".yml", ".yaml"}
    return [
        path
        for path in sorted(plugin_root.rglob("*"))
        if path.is_file()
        and should_include(path.relative_to(plugin_root))
        and path.suffix in suffixes
    ]


def check_no_hardcoded_user_paths(plugin_root: Path) -> tuple[bool, str]:
    errors: list[str] = []
    for path in iter_shipped_text_files(plugin_root):
        relative = path.relative_to(plugin_root).as_posix()
        if relative.startswith("tests/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in HARDCODED_USER_PATH_PATTERNS:
            for match in pattern.finditer(text):
                errors.append(f"{relative}: hardcoded local path {match.group(0)}")
    return not errors, "\n".join(errors[:20])


def check_no_private_names(plugin_root: Path) -> tuple[bool, str]:
    errors: list[str] = []
    for path in iter_shipped_text_files(plugin_root):
        relative = path.relative_to(plugin_root).as_posix()
        if relative.startswith("tests/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in PRIVATE_NAME_PATTERNS:
            for match in pattern.finditer(text):
                errors.append(f"{relative}: private example name {match.group(0)}")
    return not errors, "\n".join(errors[:20])


def check_markdown_links(plugin_root: Path) -> tuple[bool, str]:
    errors: list[str] = []
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for path in sorted(plugin_root.rglob("*.md")):
        if not should_include(path.relative_to(plugin_root)):
            continue
        text = path.read_text(encoding="utf-8")
        for match in link_pattern.finditer(text):
            target = match.group(1).strip()
            if (
                not target
                or target.startswith(("#", "http://", "https://", "mailto:"))
                or target.startswith("<")
            ):
                continue
            clean = target.split("#", 1)[0]
            if clean and not (path.parent / clean).resolve().exists():
                errors.append(
                    f"{path.relative_to(plugin_root).as_posix()}: unresolved link {target}"
                )
    return not errors, "\n".join(errors[:20])


def check_doctor_surface(plugin_root: Path) -> tuple[bool, str]:
    ok, output, payload = run_json(
        ["node", "scripts/tmcp_launcher.mjs", "doctor", "--compact"],
        plugin_root,
    )
    if not ok or payload is None:
        return False, output
    install_paths = payload.get("recommended_install_paths")
    if not isinstance(install_paths, dict):
        return False, "doctor output missing recommended_install_paths"
    for key in ("skill_only", "repo_checkout", "codex_plugin_cache", "aios_backed"):
        if key not in install_paths:
            return False, f"doctor output missing install layout {key}"
    return True, output


def check_sample_harvest(plugin_root: Path) -> tuple[bool, str]:
    ok, output, payload = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "harvest",
            "skills",
            "--limit",
            "5",
            "--no-write-artifacts",
            "--compact",
        ],
        plugin_root,
    )
    if not ok or payload is None:
        return False, output
    if payload.get("schema") != "tmcp-harvest-result-v0.1":
        return False, f"unexpected harvest schema: {payload.get('schema')}"
    safety = payload.get("safety")
    if (
        not isinstance(safety, dict)
        or safety.get("harvested_text_trust") != "untrusted"
    ):
        return False, "harvest output missing untrusted text safety marker"
    return True, output


def check_sample_expert_rubric(plugin_root: Path) -> tuple[bool, str]:
    evidence = json.dumps(
        [
            {
                "dimension_id": "source_grounding",
                "severity": "warning",
                "summary": "Release claims need package evidence.",
                "evidence": ["python3 scripts/check_release_package.py ."],
                "recommended_fix": "Run and cite the release package check.",
            }
        ]
    )
    ok, output, payload = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "review-plan",
            "Review release portability",
            "--project-path",
            ".",
            "--evidence-json",
            evidence,
            "--no-write-artifacts",
            "--compact",
        ],
        plugin_root,
    )
    if not ok or payload is None:
        return False, output
    if payload.get("schema") != "tmcp-review-plan-result-v0.1":
        return False, f"unexpected review schema: {payload.get('schema')}"
    output_contract = payload.get("output_contract")
    if (
        not isinstance(output_contract, list)
        or "verification expectations" not in output_contract
    ):
        return False, "review-plan output missing workflow output contract"
    return True, output


def check_adaptive_workflow_surface(
    plugin_root: Path, scratch_root: Path
) -> tuple[bool, str]:
    source_root = scratch_root / "adaptive-release-surface"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Release Surface",
                "Release readiness requires CI verification, package checks, version evidence, changelog updates, and tag review.",
                "Keep ordered next actions and artifact contracts visible before ship decisions.",
            ]
        ),
        encoding="utf-8",
    )
    ok, output, payload = run_json(
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
            "--compact",
        ],
        plugin_root,
    )
    if not ok or payload is None:
        return False, output
    if payload.get("schema") != "tmcp-workflow-recommendation-v1":
        return False, f"unexpected recommendation schema: {payload.get('schema')}"
    recommended = payload.get("recommended_workflows")
    if not isinstance(recommended, list) or not any(
        isinstance(item, dict) and item.get("id") == "release_readiness_workflow"
        for item in recommended
    ):
        return (
            False,
            "tmcp_recommend_workflows did not recommend release_readiness_workflow",
        )
    if not all(
        isinstance(item, dict) and item.get("stability") in {"stable", "experimental"}
        for item in recommended
    ):
        return False, "recommended workflows must include stability metadata"
    adaptive_pack = payload.get("adaptive_workflow_pack")
    if not isinstance(adaptive_pack, dict):
        return False, "tmcp_recommend_workflows output missing adaptive_workflow_pack"
    if adaptive_pack.get("schema") != "tmcp-adaptive-workflow-pack-v0.1":
        return False, "adaptive_workflow_pack schema mismatch"
    if adaptive_pack.get("artifact_type") != "adaptive_workflow_pack":
        return False, "adaptive_workflow_pack artifact_type mismatch"
    templates = adaptive_pack.get("recommended_default_templates")
    if not isinstance(templates, list) or not templates:
        return False, "adaptive_workflow_pack missing recommended_default_templates"
    if payload.get("artifact_paths") != {}:
        return False, "recommend smoke should not write artifacts"
    return True, output


def check_composition_surface(
    plugin_root: Path, scratch_root: Path
) -> tuple[bool, str]:
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
    verification_text = " ".join(compose.get("verification_gates", [])).lower()
    if "browser" in verification_text:
        return False, "release composition smoke unexpectedly activated browser gate"

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
            "--source-path",
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
    return True, "\n".join([output, persistence_mode, "composition surface smoke passed"])
def failed_package_check(manifest_output: str) -> dict[str, Any]:
    return {
        **{check: "fail" for check in PACKAGE_CHECK_NAMES},
        "output": {"archive_manifest": manifest_output},
    }


def check_package(package_path: Path) -> dict[str, Any]:
    manifest_ok, manifest_output = check_archive_manifest(package_path)
    if not manifest_ok:
        return failed_package_check(manifest_output)
    with tempfile.TemporaryDirectory(prefix="tmcp-package-check-") as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(package_path, "r:gz") as archive:
            safe_extractall(archive, tmp_path)
        plugin_root = tmp_path / "tmcp"
        package_env = {"TMCP_HOME": str(tmp_path / "tmcp-home")}
        install_ok, install_output = run(
            [sys.executable, "scripts/check_install.py", "."],
            plugin_root,
            package_env,
        )
        tests_ok, tests_output = run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            plugin_root,
            package_env,
        )
        compile_ok, compile_output = run(
            compile_command(sys.executable),
            plugin_root,
            package_env,
        )
        launcher_ok, launcher_output = run(
            ["node", "--check", "scripts/tmcp_launcher.mjs"],
            plugin_root,
            package_env,
        )
        frontmatter_ok, frontmatter_output = check_frontmatter_and_workflow_status(
            plugin_root
        )
        paths_ok, paths_output = check_no_hardcoded_user_paths(plugin_root)
        names_ok, names_output = check_no_private_names(plugin_root)
        links_ok, links_output = check_markdown_links(plugin_root)
        doctor_ok, doctor_output = check_doctor_surface(plugin_root)
        harvest_ok, harvest_output = check_sample_harvest(plugin_root)
        review_ok, review_output = check_sample_expert_rubric(plugin_root)
        adaptive_ok, adaptive_output = check_adaptive_workflow_surface(
            plugin_root, tmp_path
        )
        composition_ok, composition_output = check_composition_surface(
            plugin_root, tmp_path
        )
    return {
        "archive_manifest": "pass",
        "install_check": "pass" if install_ok else "fail",
        "tests": "pass" if tests_ok else "fail",
        "compile": "pass" if compile_ok else "fail",
        "launcher_syntax": "pass" if launcher_ok else "fail",
        "frontmatter": "pass" if frontmatter_ok else "fail",
        "hardcoded_user_paths": "pass" if paths_ok else "fail",
        "private_names": "pass" if names_ok else "fail",
        "markdown_links": "pass" if links_ok else "fail",
        "doctor_surface": "pass" if doctor_ok else "fail",
        "sample_harvest": "pass" if harvest_ok else "fail",
        "sample_expert_rubric": "pass" if review_ok else "fail",
        "adaptive_workflow_surface": "pass" if adaptive_ok else "fail",
        "composition_surface": "pass" if composition_ok else "fail",
        "output": {
            "archive_manifest": manifest_output,
            "install": install_output,
            "tests": tests_output,
            "compile": compile_output,
            "launcher_syntax": launcher_output,
            "frontmatter": frontmatter_output,
            "hardcoded_user_paths": paths_output,
            "private_names": names_output,
            "markdown_links": links_output,
            "doctor_surface": doctor_output,
            "sample_harvest": harvest_output,
            "sample_expert_rubric": review_output,
            "adaptive_workflow_surface": adaptive_output,
            "composition_surface": composition_output,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create and verify a TMCP release package."
    )
    parser.add_argument(
        "plugin_root", nargs="?", default=".", help="Path to plugin root"
    )
    parser.add_argument("--output", help="Optional package output path")
    parser.add_argument(
        "--verify-reproducible",
        action="store_true",
        help="Build a second archive from the same Git tree and compare digests",
    )
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).expanduser().resolve()
    generated_output = args.output is None
    if args.output:
        output_path = Path(args.output).expanduser()
    else:
        descriptor, temporary_output = tempfile.mkstemp(
            prefix="tmcp-release-check-", suffix=".tar.gz"
        )
        os.close(descriptor)
        output_path = Path(temporary_output)
    try:
        build = create_package(plugin_root, output_path)
        result = {
            "schema": "tmcp-release-package-check-v0.1",
            "package_path": str(output_path),
            "package_policy": PACKAGE_POLICY_VERSION,
            "source_commit": build["source_commit"],
            "source_tree": build["source_tree"],
            "archive_digest": build["archive_digest"],
            "manifest_path": build["manifest_path"],
            "manifest_digest": build["manifest_digest"],
            **check_package(output_path),
        }
        if args.verify_reproducible:
            reproducibility = verify_reproducibility(
                plugin_root, build
            )
            result["reproducibility"] = reproducibility["status"]
            result["repeat_archive_digest"] = reproducibility.get(
                "repeat_archive_digest"
            )
            result["repeat_manifest_digest"] = reproducibility.get(
                "repeat_manifest_digest"
            )
            result["output"]["reproducibility"] = reproducibility["message"]
    except ReleasePackageError as exc:
        result = {
            "schema": "tmcp-release-package-check-v0.1",
            "package_path": str(output_path),
            "package_policy": PACKAGE_POLICY_VERSION,
            "package_build": "fail",
            "errors": [str(exc)],
        }
        if generated_output:
            try:
                output_path.unlink()
            except OSError:
                pass
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    required_checks = PACKAGE_CHECK_NAMES
    if args.verify_reproducible:
        required_checks += ("reproducibility",)
    ok = all(
        result[key] == "pass"
        for key in required_checks
    )
    if generated_output:
        try:
            output_path.unlink()
        except OSError:
            pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
