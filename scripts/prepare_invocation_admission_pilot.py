#!/usr/bin/env python3
"""Prepare blinded runner envelopes for the invocation-admission pilot.

This command makes no model calls. It freezes source-bound task inputs, compiles
the policy interventions, randomizes rows, and keeps policy labels out of runner
envelopes. A new output directory is required so prior evidence is never
overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "examples" / "workflows" / "invocation-admission-pilot.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _fixture_catalog(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for relative in manifest["preregistration"]["source_fixtures"]:
        path = ROOT / relative
        fixture = _read_json(path)
        for case in fixture.get("fixtures", []):
            case_id = str(case["fixture_id"])
            catalog[case_id] = {
                "source": relative,
                "objective": case["objective"],
                "runner_context": case["task_context"],
                "bar": {
                    "quality_rubric": case["quality_rubric"],
                    "expected_order": case["expected_order"],
                    "expected_relationships": case["expected_relationships"],
                    "incompatible_skill_pairs": case["incompatible_skill_pairs"],
                    "pass_rule": (
                        "Pass only when every rubric criterion is satisfied by the "
                        "artifact and no incompatible behavior is present."
                    ),
                },
            }
        for case in fixture.get("cases", []):
            case_id = str(case["case_id"])
            if "runner_context" in case and "bar" in case:
                catalog[case_id] = {
                    "source": relative,
                    "objective": case["objective"],
                    "runner_context": case["runner_context"],
                    "bar": case["bar"],
                    "source_path": case.get("source_path"),
                    "workspace_template": case.get("workspace_template"),
                }
                continue
            catalog[case_id] = {
                "source": relative,
                "objective": case["prompt"],
                "runner_context": {
                    "mode": "bounded_plan_only",
                    "execution_boundary": case["execution_boundary"],
                },
                "bar": {
                    "bar": case["bar"],
                    "smells": case["smells"],
                    "pass_rule": (
                        "Pass only when the full bar is satisfied and none of the "
                        "listed smells is present."
                    ),
                },
            }
    return catalog


def _compose(
    objective: str,
    mode: str,
    *,
    source_path: Path = ROOT,
) -> tuple[dict[str, Any], int]:
    command = [
        "node",
        str(ROOT / "scripts" / "tmcp_launcher.mjs"),
        "compose-packet",
        objective,
        "--project-path",
        str(source_path),
        "--source-path",
        str(source_path),
        "--phase",
        "start",
        "--admission-mode",
        mode,
        "--compact",
    ]
    started = time.monotonic_ns()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    elapsed_ms = round((time.monotonic_ns() - started) / 1_000_000)
    packet = json.loads(completed.stdout)
    if not packet.get("ok"):
        raise RuntimeError(f"TMCP composition failed: {packet}")
    return packet, elapsed_ms


def prepare(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    if manifest.get("schema") not in {
        "tmcp-invocation-admission-pilot-v0.2",
        "tmcp-invocation-admission-pilot-v0.3",
        "tmcp-invocation-admission-pilot-v0.4",
    }:
        raise ValueError("pilot manifest must use schema v0.2, v0.3, or v0.4")
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")

    catalog = _fixture_catalog(manifest)
    runner_dir = output_dir / "runner-inputs"
    judge_dir = output_dir / "judge-bars"
    runner_dir.mkdir(parents=True)
    judge_dir.mkdir()

    tasks: list[dict[str, Any]] = []
    for index, declared in enumerate(manifest["tasks"], start=1):
        fixture_id = str(declared["fixture_id"])
        case = catalog.get(fixture_id)
        if case is None:
            raise ValueError(f"missing source fixture {fixture_id}")
        if case["objective"] != declared["prompt"]:
            raise ValueError(f"prompt drift for {fixture_id}")
        alias = f"case-{index:02d}"
        tasks.append({"alias": alias, "declared": declared, "case": case})
        _write_json(
            judge_dir / f"{alias}.json",
            {
                "schema": "tmcp-invocation-admission-judge-bar-v0.1",
                "case_alias": alias,
                "objective": case["objective"],
                "bar": case["bar"],
            },
        )

    compiled: dict[tuple[str, str], dict[str, Any]] = {}
    for task in tasks:
        objective = str(task["case"]["objective"])
        source_path = ROOT
        if task["case"].get("source_path"):
            source_path = (ROOT / str(task["case"]["source_path"])).resolve()
        for policy_id, mode in (
            ("always-on", "forced"),
            ("admission-controlled", "automatic"),
        ):
            packet, elapsed_ms = _compose(
                objective,
                mode,
                source_path=source_path,
            )
            compiled[(task["alias"], policy_id)] = {
                "packet": packet,
                "elapsed_ms": elapsed_ms,
            }
            if policy_id == "admission-controlled":
                observed = packet["admission"]["action"]
                expected = task["declared"]["expected_automatic_action"]
                if observed != expected:
                    raise ValueError(
                        f"automatic action drift for {task['alias']}: "
                        f"expected {expected}, observed {observed}"
                    )

    rows: list[dict[str, Any]] = []
    repeats = int(manifest["repeats_per_cell"])
    for task in tasks:
        for policy in manifest["policies"]:
            policy_id = str(policy["id"])
            for repeat in range(1, repeats + 1):
                rows.append(
                    {
                        "case_alias": task["alias"],
                        "fixture_id": task["declared"]["fixture_id"],
                        "policy_id": policy_id,
                        "repeat": repeat,
                    }
                )
    if len(rows) != int(manifest["matrix_rows"]):
        raise ValueError("prepared row count does not match manifest")
    random.Random(manifest["preregistration"]["randomization_seed"]).shuffle(rows)

    secret_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        blind_id = f"pilot-{index:03d}"
        task = next(item for item in tasks if item["alias"] == row["case_alias"])
        packet: dict[str, Any] | None = None
        compose_ms = 0
        if row["policy_id"] != "explicit-only":
            result = compiled[(row["case_alias"], row["policy_id"])]
            packet = result["packet"]
            compose_ms = result["elapsed_ms"]
        inject_packet = bool(packet and packet["admission"]["action"] != "bypass")
        operating_packet = (
            packet["packet_markdown"] if packet is not None and inject_packet else None
        )
        workspace_path: Path | None = None
        workspace_template = task["case"].get("workspace_template")
        if workspace_template:
            workspace_path = output_dir / "workspaces" / blind_id
            shutil.copytree((ROOT / str(workspace_template)).resolve(), workspace_path)
        runner_context = dict(task["case"]["runner_context"])
        if workspace_path is not None:
            runner_context["workspace_path"] = str(workspace_path)
        envelope = {
            "schema": "tmcp-invocation-admission-runner-input-v0.1",
            "blind_id": blind_id,
            "instruction": (
                "Produce the requested user-facing artifact using only the bounded "
                "task input below. Follow its execution boundary exactly. If a "
                "workspace_path is supplied, tools may inspect it and may modify it "
                "only when the boundary authorizes edits. Do not inspect other files. "
                "Return only the artifact, with no policy analysis."
            ),
            "task": {
                "objective": task["case"]["objective"],
                "context": runner_context,
            },
            "operating_packet": operating_packet,
        }
        envelope_path = runner_dir / f"{blind_id}.json"
        _write_json(envelope_path, envelope)
        metrics = {
            "compose_wall_time_ms": compose_ms,
            "packet_injected": inject_packet,
            "packet_markdown_chars": len(operating_packet or ""),
            "selected_source_count": (
                packet["observability"]["selected_source_count"] if packet else 0
            ),
            "review_source_count": (
                packet["observability"]["review_source_count"] if packet else 0
            ),
            "test_fixture_source_count": (
                packet["observability"]["test_fixture_source_count"] if packet else 0
            ),
            "admission_action": (
                packet["admission"]["action"] if packet else "disabled"
            ),
        }
        secret_rows.append(
            {
                **row,
                "blind_id": blind_id,
                "runner_input": str(envelope_path.relative_to(output_dir)),
                "judge_bar": f"judge-bars/{row['case_alias']}.json",
                "runner_input_digest": _digest(envelope),
                "metrics": metrics,
            }
        )

    plan = {
        "schema": "tmcp-invocation-admission-execution-plan-v0.1",
        "status": "prepared_no_model_calls",
        "manifest": str(manifest_path.relative_to(ROOT)),
        "manifest_digest": _digest(manifest),
        "randomization_seed": manifest["preregistration"]["randomization_seed"],
        "row_count": len(secret_rows),
        "rows": secret_rows,
        "unavailable_measures": ["input_tokens", "output_tokens"],
    }
    _write_json(output_dir / "secret-plan.json", plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        plan = prepare(args.manifest.resolve(), args.output_dir.resolve())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "output_dir": str(args.output_dir.resolve()),
                "row_count": plan["row_count"],
                "status": plan["status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
