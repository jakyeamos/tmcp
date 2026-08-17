#!/usr/bin/env python3
"""Run the preregistered v0.5 TMCP admission-overhead confirmation.

The v0.4 pilot established blinded behavioral evidence but its self-reported
agent wall time was too noisy to identify compiler overhead. This follow-up
keeps that evidence digest-bound and measures the actual compose-packet process
in randomized adjacent policy pairs. No model calls are made.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "examples" / "workflows" / "invocation-admission-overhead-pilot-v0.5.json"
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _median(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot calculate a median from no observations")
    return float(statistics.median(values))


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") not in {
        "tmcp-invocation-admission-overhead-pilot-v0.5",
        "tmcp-invocation-admission-overhead-pilot-v0.6",
    }:
        raise ValueError("overhead pilot manifest must use schema v0.5 or v0.6")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or len(tasks) < 2:
        raise ValueError("overhead pilot requires at least two negative-control tasks")
    for task in tasks:
        if task.get("negative_control") is not True:
            raise ValueError(
                f"{task.get('id')}: every overhead-pilot task must be a negative control"
            )
        if task.get("expected_automatic_action") != "bypass":
            raise ValueError(f"{task.get('id')}: automatic action must be bypass")
    benchmark = manifest.get("benchmark") or {}
    if int(benchmark.get("measured_pairs_per_task", 0)) < 3:
        raise ValueError("overhead pilot requires at least three measured pairs per task")
    policies = benchmark.get("pair_policies")
    if not isinstance(policies, list) or {item.get("id") for item in policies} != {
        "always-on",
        "admission-controlled",
    }:
        raise ValueError(
            "overhead pilot requires always-on and admission-controlled pair policies"
        )
    if benchmark.get("transport", "cli_subprocess") not in {
        "cli_subprocess",
        "in_process_server",
    }:
        raise ValueError("unsupported benchmark transport")


def _load_behavioral_evidence(manifest: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    declared = manifest["behavioral_evidence"]
    path = (ROOT / str(declared["path"])).resolve()
    if not path.is_file():
        raise ValueError(f"missing behavioral evidence: {path}")
    observed_digest = _sha256(path)
    if observed_digest != declared["sha256"]:
        raise ValueError("behavioral evidence digest does not match preregistration")
    report = _read_object(path)
    if report.get("status") != "complete":
        raise ValueError("behavioral evidence is incomplete")
    gates = report.get("acceptance_gates") or {}
    for gate_id in declared["required_passed_gates"]:
        if not (gates.get(gate_id) or {}).get("passed"):
            raise ValueError(f"required behavioral gate did not pass: {gate_id}")
    return path, report


def _compose(
    objective: str,
    admission_mode: str,
    source_path: Path,
) -> dict[str, Any]:
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
        admission_mode,
        "--compact",
    ]
    started_ns = time.monotonic_ns()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    elapsed_ns = time.monotonic_ns() - started_ns
    packet = json.loads(completed.stdout)
    if not isinstance(packet, dict) or not packet.get("ok"):
        raise RuntimeError(f"TMCP composition failed: {packet}")
    return {
        "wall_time_ns": elapsed_ns,
        "admission_action": packet["admission"]["action"],
        "packet_injected": packet["admission"]["action"] != "bypass",
        "packet_markdown_chars": len(packet.get("packet_markdown") or ""),
    }


def _in_process_composer() -> Callable[[str, str, Path], dict[str, Any]]:
    """Load the server once, matching the lifecycle of a persistent MCP process."""

    server_path = ROOT / "scripts" / "tmcp_mcp_server.py"
    spec = importlib.util.spec_from_file_location(
        "tmcp_mcp_server_overhead_benchmark", server_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load TMCP server from {server_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def compose(objective: str, admission_mode: str, source_path: Path) -> dict[str, Any]:
        started_ns = time.monotonic_ns()
        packet = module._compose_packet(
            {
                "objective": objective,
                "project_path": str(source_path),
                "source_path": str(source_path),
                "phase": "start",
                "admission_mode": admission_mode,
                "cache_policy": "none",
                "redact_sensitive": True,
            }
        )
        elapsed_ns = time.monotonic_ns() - started_ns
        return {
            "wall_time_ns": elapsed_ns,
            "admission_action": packet["admission"]["action"],
            "packet_injected": packet["admission"]["action"] != "bypass",
            "packet_markdown_chars": len(packet.get("packet_markdown") or ""),
        }

    return compose


def _schedule(manifest: dict[str, Any], *, warmup: bool) -> list[dict[str, Any]]:
    benchmark = manifest["benchmark"]
    repetitions = int(
        benchmark["warmups_per_cell"]
        if warmup
        else benchmark["measured_pairs_per_task"]
    )
    blocks = [
        {"task": task, "repeat": repeat}
        for task in manifest["tasks"]
        for repeat in range(1, repetitions + 1)
    ]
    seed = int(benchmark["randomization_seed"]) + (1 if warmup else 0)
    rng = random.Random(seed)
    rng.shuffle(blocks)
    scheduled: list[dict[str, Any]] = []
    for block in blocks:
        policies = [dict(item) for item in benchmark["pair_policies"]]
        rng.shuffle(policies)
        for order, policy in enumerate(policies, start=1):
            scheduled.append(
                {
                    "task": block["task"],
                    "repeat": block["repeat"],
                    "pair_order": order,
                    "policy": policy,
                }
            )
    return scheduled


def _run_schedule(
    manifest: dict[str, Any],
    *,
    warmup: bool,
    compose: Callable[[str, str, Path], dict[str, Any]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for item in _schedule(manifest, warmup=warmup):
        task = item["task"]
        policy = item["policy"]
        source_path = (ROOT / str(task["source_path"])).resolve()
        result = compose(str(task["objective"]), str(policy["admission_mode"]), source_path)
        if result.get("admission_action") != policy["expected_action"]:
            raise ValueError(
                f"{task['id']} {policy['id']}: expected action "
                f"{policy['expected_action']}, observed {result.get('admission_action')}"
            )
        observations.append(
            {
                "task_id": task["id"],
                "repeat": item["repeat"],
                "pair_order": item["pair_order"],
                "policy_id": policy["id"],
                **result,
            }
        )
    return observations


def score(manifest: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    repetitions = int(manifest["benchmark"]["measured_pairs_per_task"])
    expected_count = len(manifest["tasks"]) * repetitions * 2
    if len(observations) != expected_count:
        raise ValueError(
            f"incomplete benchmark: expected {expected_count} observations, "
            f"received {len(observations)}"
        )
    by_pair: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for observation in observations:
        key = (str(observation["task_id"]), int(observation["repeat"]))
        policies = by_pair.setdefault(key, {})
        policy_id = str(observation["policy_id"])
        if policy_id in policies:
            raise ValueError(f"duplicate benchmark observation: {key} {policy_id}")
        elapsed = observation.get("wall_time_ns")
        if not isinstance(elapsed, int) or isinstance(elapsed, bool) or elapsed <= 0:
            raise ValueError(f"invalid wall_time_ns: {key} {policy_id}")
        policies[policy_id] = observation

    expected_pairs = {
        (str(task["id"]), repeat)
        for task in manifest["tasks"]
        for repeat in range(1, repetitions + 1)
    }
    if set(by_pair) != expected_pairs:
        raise ValueError("benchmark pair identities do not match preregistration")

    paired_reductions: list[float] = []
    per_task: dict[str, dict[str, Any]] = {}
    for task in manifest["tasks"]:
        task_id = str(task["id"])
        task_reductions: list[float] = []
        policy_times: dict[str, list[float]] = {
            "always-on": [],
            "admission-controlled": [],
        }
        for repeat in range(1, repetitions + 1):
            policies = by_pair[(task_id, repeat)]
            if set(policies) != {"always-on", "admission-controlled"}:
                raise ValueError(f"incomplete policy pair: {task_id} repeat {repeat}")
            forced_ns = float(policies["always-on"]["wall_time_ns"])
            automatic_ns = float(policies["admission-controlled"]["wall_time_ns"])
            reduction = 1 - automatic_ns / forced_ns
            task_reductions.append(reduction)
            paired_reductions.append(reduction)
            policy_times["always-on"].append(forced_ns)
            policy_times["admission-controlled"].append(automatic_ns)
        per_task[task_id] = {
            "pairs": repetitions,
            "median_paired_reduction": _median(task_reductions),
            "median_always_on_ms": _median(policy_times["always-on"]) / 1_000_000,
            "median_admission_controlled_ms": (
                _median(policy_times["admission-controlled"]) / 1_000_000
            ),
        }

    observed = _median(paired_reductions)
    minimum = float(
        manifest["acceptance"][
            "minimum_median_paired_overhead_reduction_vs_always_on"
        ]
    )
    per_task_minimum = float(
        manifest["acceptance"]["minimum_per_task_median_paired_reduction"]
    )
    gates = {
        "sample_integrity": {
            "passed": True,
            "status": "passed",
            "observations": len(observations),
            "pairs": len(by_pair),
        },
        "automatic_negative_controls_bypassed": {
            "passed": all(
                item["admission_action"] == "bypass" and not item["packet_injected"]
                for item in observations
                if item["policy_id"] == "admission-controlled"
            ),
        },
        "always_on_packets_injected": {
            "passed": all(
                item["admission_action"] == "forced" and item["packet_injected"]
                for item in observations
                if item["policy_id"] == "always-on"
            ),
        },
        "median_paired_overhead_reduction_vs_always_on": {
            "passed": observed >= minimum,
            "observed": observed,
            "minimum": minimum,
            "measure": manifest["benchmark"].get(
                "measurement", "monotonic compiler wall_time_ns"
            ),
        },
        "no_per_task_overhead_regression": {
            "passed": all(
                item["median_paired_reduction"] >= per_task_minimum
                for item in per_task.values()
            ),
            "minimum": per_task_minimum,
        },
    }
    for item in gates.values():
        item.setdefault("status", "passed" if item["passed"] else "failed")
    return {
        "schema": "tmcp-invocation-admission-overhead-score-v0.5",
        "status": "complete",
        "promotion_authorized": all(item["passed"] for item in gates.values()),
        "acceptance_gates": gates,
        "per_task": per_task,
        "evidence_boundary": manifest["evidence_boundary"],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TMCP invocation-admission overhead confirmation",
        "",
        f"Status: `{report['status']}`",
        f"Promotion authorized: `{str(report['promotion_authorized']).lower()}`",
        "",
        "## Task measurements",
        "",
        "| Task | Pairs | Always-on median ms | Admission median ms | Median paired reduction |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for task_id, item in report["per_task"].items():
        lines.append(
            f"| {task_id} | {item['pairs']} | {item['median_always_on_ms']:.1f} | "
            f"{item['median_admission_controlled_ms']:.1f} | "
            f"{item['median_paired_reduction']:.1%} |"
        )
    lines.extend(["", "## Acceptance gates", ""])
    for gate_id, item in report["acceptance_gates"].items():
        lines.append(f"- `{gate_id}`: **{item['status'].upper()}**")
    lines.extend(["", "## Evidence boundary", "", report["evidence_boundary"], ""])
    return "\n".join(lines)


def run(
    manifest_path: Path,
    output_dir: Path,
    *,
    compose: Callable[[str, str, Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    manifest = _read_object(manifest_path)
    _validate_manifest(manifest)
    evidence_path, behavioral_report = _load_behavioral_evidence(manifest)
    if compose is None:
        transport = manifest["benchmark"].get("transport", "cli_subprocess")
        compose = _in_process_composer() if transport == "in_process_server" else _compose
    output_dir.mkdir(parents=True)
    _run_schedule(manifest, warmup=True, compose=compose)
    observations = _run_schedule(manifest, warmup=False, compose=compose)
    report = score(manifest, observations)
    version = "v0.6" if manifest["schema"].endswith("v0.6") else "v0.5"
    report["schema"] = f"tmcp-invocation-admission-overhead-score-{version}"
    behavioral_gates = {
        gate_id: behavioral_report["acceptance_gates"][gate_id]
        for gate_id in manifest["behavioral_evidence"]["required_passed_gates"]
    }
    report["behavioral_evidence"] = {
        "path": str(evidence_path),
        "sha256": manifest["behavioral_evidence"]["sha256"],
        "gates": behavioral_gates,
    }
    report["promotion_authorized"] = report["promotion_authorized"] and all(
        item["passed"] for item in behavioral_gates.values()
    )
    _write_json(
        output_dir / "benchmark-results.json",
        {
            "schema": f"tmcp-invocation-admission-overhead-observations-{version}",
            "manifest_sha256": _sha256(manifest_path),
            "benchmark_implementation_sha256": _sha256(Path(__file__)),
            "transport": manifest["benchmark"].get("transport", "cli_subprocess"),
            "observations": observations,
        },
    )
    _write_json(output_dir / "score-report.json", report)
    (output_dir / "score-report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = run(args.manifest.resolve(), args.output_dir.resolve())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
