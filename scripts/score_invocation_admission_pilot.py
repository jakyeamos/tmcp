#!/usr/bin/env python3
"""Score a complete blinded invocation-admission pilot corpus.

The scorer joins policy labels only after runner artifacts and independent judge
results exist for every randomized row. It refuses partial corpora and records
unavailable measures rather than substituting weaker evidence.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "examples" / "workflows" / "invocation-admission-pilot.json"


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _review_or_audit_task(prompt: str) -> bool:
    words = {word.strip('.,:;!?()[]{}"').lower() for word in prompt.split()}
    return bool(words & {"audit", "auditing", "review", "reviewing"})


def _validate_judgment(blind_id: str, result: dict[str, Any]) -> None:
    required = {
        "blind_id",
        "pass",
        "weighted_score",
        "verification_quality_score",
        "irrelevant_constraint_count",
        "unsafe_or_unjustified_action_count",
        "dimensions",
        "smells_present",
        "reason",
    }
    if set(result) != required:
        raise ValueError(f"{blind_id}: judge result fields do not match schema")
    if result["blind_id"] != blind_id:
        raise ValueError(f"{blind_id}: judge result identity mismatch")
    if not isinstance(result["pass"], bool):
        raise ValueError(f"{blind_id}: pass must be boolean")
    for field in ("weighted_score", "verification_quality_score"):
        value = result[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{blind_id}: {field} must be numeric")
        if not 0 <= float(value) <= 1:
            raise ValueError(f"{blind_id}: {field} must be within 0..1")
    for field in (
        "irrelevant_constraint_count",
        "unsafe_or_unjustified_action_count",
    ):
        value = result[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{blind_id}: {field} must be a non-negative integer")
    if not isinstance(result["dimensions"], list) or not result["dimensions"]:
        raise ValueError(f"{blind_id}: dimensions must be a non-empty array")
    if not isinstance(result["smells_present"], list):
        raise ValueError(f"{blind_id}: smells_present must be an array")


def score(manifest_path: Path, pilot_dir: Path) -> dict[str, Any]:
    manifest = _read_object(manifest_path)
    plan = _read_object(pilot_dir / "secret-plan.json")
    if plan.get("row_count") != manifest.get("matrix_rows"):
        raise ValueError("execution plan does not match manifest row count")

    task_by_id = {task["fixture_id"]: task for task in manifest["tasks"]}
    joined: list[dict[str, Any]] = []
    for row in plan["rows"]:
        blind_id = str(row["blind_id"])
        artifact_path = pilot_dir / "runner-artifacts" / f"{blind_id}.md"
        result_path = pilot_dir / "judge-results" / f"{blind_id}.json"
        if not artifact_path.is_file():
            raise ValueError(f"missing runner artifact: {artifact_path}")
        if not result_path.is_file():
            raise ValueError(f"missing judge result: {result_path}")
        result = _read_object(result_path)
        _validate_judgment(blind_id, result)
        metrics = dict(row.get("metrics") or {})
        if "runner_wall_time_ms" not in metrics:
            runner_metrics_path = pilot_dir / "runner-metrics" / f"{blind_id}.json"
            if runner_metrics_path.is_file():
                runner_metrics = _read_object(runner_metrics_path)
                if runner_metrics.get("blind_id") != blind_id:
                    raise ValueError(f"{blind_id}: runner metrics identity mismatch")
                elapsed = runner_metrics.get("runner_wall_time_ms")
                if (
                    not isinstance(elapsed, int)
                    or isinstance(elapsed, bool)
                    or elapsed < 0
                ):
                    raise ValueError(
                        f"{blind_id}: runner_wall_time_ms must be a non-negative integer"
                    )
                metrics["runner_wall_time_ms"] = elapsed
        joined.append({**row, "metrics": metrics, "judgment": result})

    expected_ids = {str(row["blind_id"]) for row in plan["rows"]}
    actual_ids = {
        path.stem for path in (pilot_dir / "judge-results").glob("pilot-*.json")
    }
    if actual_ids != expected_ids:
        raise ValueError("judge result corpus contains missing or unexpected rows")

    policy_summaries: dict[str, dict[str, Any]] = {}
    for policy in manifest["policies"]:
        policy_id = str(policy["id"])
        rows = [row for row in joined if row["policy_id"] == policy_id]
        scores = [float(row["judgment"]["weighted_score"]) for row in rows]
        verification = [
            float(row["judgment"]["verification_quality_score"]) for row in rows
        ]
        packet_chars = [float(row["metrics"]["packet_markdown_chars"]) for row in rows]
        runner_times = [
            float(row["metrics"]["runner_wall_time_ms"])
            for row in rows
            if "runner_wall_time_ms" in row["metrics"]
        ]
        policy_summaries[policy_id] = {
            "rows": len(rows),
            "passes": sum(bool(row["judgment"]["pass"]) for row in rows),
            "pass_rate": _mean([float(row["judgment"]["pass"]) for row in rows]),
            "mean_task_outcome_score": _mean(scores),
            "median_task_outcome_score": _median(scores),
            "mean_verification_quality_score": _mean(verification),
            "median_packet_markdown_chars": _median(packet_chars),
            "median_runner_wall_time_ms": (
                _median(runner_times) if len(runner_times) == len(rows) else None
            ),
            "packet_injection_rate": _mean(
                [float(row["metrics"]["packet_injected"]) for row in rows]
            ),
            "irrelevant_constraint_count": sum(
                int(row["judgment"]["irrelevant_constraint_count"]) for row in rows
            ),
            "unsafe_or_unjustified_action_count": sum(
                int(row["judgment"]["unsafe_or_unjustified_action_count"])
                for row in rows
            ),
        }

    task_summaries: dict[str, dict[str, dict[str, Any]]] = {}
    for task in manifest["tasks"]:
        fixture_id = str(task["fixture_id"])
        task_summaries[fixture_id] = {}
        for policy in manifest["policies"]:
            policy_id = str(policy["id"])
            rows = [
                row
                for row in joined
                if row["fixture_id"] == fixture_id and row["policy_id"] == policy_id
            ]
            task_summaries[fixture_id][policy_id] = {
                "scores": [row["judgment"]["weighted_score"] for row in rows],
                "passes": [row["judgment"]["pass"] for row in rows],
                "actions": [row["metrics"]["admission_action"] for row in rows],
            }

    admission_rows = [
        row for row in joined if row["policy_id"] == "admission-controlled"
    ]
    non_review_rows = []
    for row in admission_rows:
        task = task_by_id[row["fixture_id"]]
        classified_review = task.get("review_or_audit_task")
        if classified_review is None:
            classified_review = _review_or_audit_task(task["prompt"])
        if not classified_review:
            non_review_rows.append(row)
    selected_non_review = sum(
        int(row["metrics"]["selected_source_count"]) for row in non_review_rows
    )
    review_non_review = sum(
        int(row["metrics"]["review_source_count"]) for row in non_review_rows
    )
    review_source_rate = (
        review_non_review / selected_non_review if selected_non_review else 0.0
    )

    acceptance = manifest["acceptance"]
    admission = policy_summaries["admission-controlled"]
    explicit = policy_summaries["explicit-only"]
    always = policy_summaries["always-on"]
    strongest_baseline = max(
        explicit["mean_task_outcome_score"], always["mean_task_outcome_score"]
    )
    always_median_chars = float(always["median_packet_markdown_chars"])
    packet_size_reduction = (
        1 - float(admission["median_packet_markdown_chars"]) / always_median_chars
        if always_median_chars
        else 0.0
    )
    unavailable = set(plan.get("unavailable_measures", []))
    runner_time_available = "runner_wall_time_ms" not in unavailable
    runner_time_reduction: float | None = None
    overhead_scope = str(acceptance.get("overhead_evaluation_scope") or "all_tasks")
    overhead_admission_rows = admission_rows
    overhead_always_rows = [row for row in joined if row["policy_id"] == "always-on"]
    if overhead_scope == "negative_controls":
        overhead_ids = {
            task["fixture_id"]
            for task in manifest["tasks"]
            if task.get("negative_control") is True
        }
        overhead_admission_rows = [
            row for row in overhead_admission_rows if row["fixture_id"] in overhead_ids
        ]
        overhead_always_rows = [
            row for row in overhead_always_rows if row["fixture_id"] in overhead_ids
        ]
    if runner_time_available:
        admission_times = [
            float(row["metrics"]["runner_wall_time_ms"])
            for row in overhead_admission_rows
        ]
        always_times = [
            float(row["metrics"]["runner_wall_time_ms"]) for row in overhead_always_rows
        ]
        always_median_time = _median(always_times)
        runner_time_reduction = (
            1 - _median(admission_times) / always_median_time
            if always_median_time
            else 0.0
        )
    declared_negative_ids = {
        task["fixture_id"]
        for task in manifest["tasks"]
        if task.get("negative_control") is True
    }
    negative_ids = declared_negative_ids or {
        task["fixture_id"]
        for task in manifest["tasks"]
        if task["expected_automatic_action"] == "bypass"
        and task["fixture_id"] == "skill-creator-rotate-pdf"
    }
    negative_rows = [row for row in admission_rows if row["fixture_id"] in negative_ids]

    gates = {
        "quality_noninferiority": {
            "status": "passed"
            if admission["mean_task_outcome_score"]
            >= strongest_baseline - acceptance["quality_noninferiority_margin"]
            else "failed",
            "passed": admission["mean_task_outcome_score"]
            >= strongest_baseline - acceptance["quality_noninferiority_margin"],
            "observed_admission_mean": admission["mean_task_outcome_score"],
            "strongest_baseline_mean": strongest_baseline,
            "margin": acceptance["quality_noninferiority_margin"],
        },
        "median_overhead_reduction_vs_always_on": {
            "status": (
                "unavailable"
                if runner_time_reduction is None
                else (
                    "passed"
                    if runner_time_reduction
                    >= acceptance["minimum_median_overhead_reduction_vs_always_on"]
                    else "failed"
                )
            ),
            "passed": runner_time_reduction is not None
            and runner_time_reduction
            >= acceptance["minimum_median_overhead_reduction_vs_always_on"],
            "observed": runner_time_reduction,
            "minimum": acceptance["minimum_median_overhead_reduction_vs_always_on"],
            "measure": "runner_wall_time_ms",
            "scope": overhead_scope,
            "admission_rows": len(overhead_admission_rows),
            "always_on_rows": len(overhead_always_rows),
            "packet_size_proxy_reduction": packet_size_reduction,
            "packet_size_proxy_only": runner_time_reduction is None,
        },
        "review_source_rate_for_non_review_tasks": {
            "status": "passed"
            if review_source_rate
            <= acceptance["maximum_review_source_rate_for_non_review_tasks"]
            else "failed",
            "passed": review_source_rate
            <= acceptance["maximum_review_source_rate_for_non_review_tasks"],
            "observed": review_source_rate,
            "maximum": acceptance["maximum_review_source_rate_for_non_review_tasks"],
            "review_sources": review_non_review,
            "selected_sources": selected_non_review,
            "classification": (
                "preregistered task classification when provided; otherwise prompt "
                "contains neither audit nor review"
            ),
        },
        "plan_only_negative_control_bypassed": {
            "status": "passed"
            if bool(negative_rows)
            and all(
                row["metrics"]["admission_action"] == "bypass" for row in negative_rows
            )
            else "failed",
            "passed": bool(negative_rows)
            and all(
                row["metrics"]["admission_action"] == "bypass" for row in negative_rows
            ),
            "observed_actions": [
                row["metrics"]["admission_action"] for row in negative_rows
            ],
        },
        "no_safety_regression": {
            "status": "passed"
            if admission["unsafe_or_unjustified_action_count"]
            <= explicit["unsafe_or_unjustified_action_count"]
            else "failed",
            "passed": admission["unsafe_or_unjustified_action_count"]
            <= explicit["unsafe_or_unjustified_action_count"],
            "admission_count": admission["unsafe_or_unjustified_action_count"],
            "explicit_only_count": explicit["unsafe_or_unjustified_action_count"],
        },
    }

    return {
        "schema": "tmcp-invocation-admission-pilot-score-v0.1",
        "status": "complete"
        if len(joined) == manifest["matrix_rows"]
        else "incomplete",
        "promotion_authorized": all(gate["passed"] for gate in gates.values()),
        "rows_scored": len(joined),
        "policy_summaries": policy_summaries,
        "task_summaries": task_summaries,
        "acceptance_gates": gates,
        "unavailable_measures": sorted(unavailable),
        "evidence_boundary": (
            "Screening pilot only. Runner wall time is available when recorded by "
            "the isolated runner; input and output token measures remain unavailable."
            if runner_time_available
            else "Screening pilot only. Packet characters are an overhead proxy; "
            "runner wall time and token measures were unavailable."
        ),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TMCP invocation-admission blinded pilot",
        "",
        f"Status: `{report['status']}`",
        f"Promotion authorized: `{str(report['promotion_authorized']).lower()}`",
        f"Rows scored: `{report['rows_scored']}`",
        "",
        "## Policy results",
        "",
        "| Policy | Pass rate | Mean outcome | Mean verification | Median runner ms | Median packet chars | Injection rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for policy_id, item in report["policy_summaries"].items():
        median_runner_ms = item["median_runner_wall_time_ms"]
        rendered_runner_ms = (
            f"{median_runner_ms:.0f}" if median_runner_ms is not None else "unavailable"
        )
        lines.append(
            f"| {policy_id} | {item['pass_rate']:.1%} | "
            f"{item['mean_task_outcome_score']:.3f} | "
            f"{item['mean_verification_quality_score']:.3f} | "
            f"{rendered_runner_ms} | "
            f"{item['median_packet_markdown_chars']:.0f} | "
            f"{item['packet_injection_rate']:.1%} |"
        )
    lines.extend(["", "## Acceptance gates", ""])
    for gate_id, item in report["acceptance_gates"].items():
        lines.append(f"- `{gate_id}`: **{item['status'].upper()}**")
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            report["evidence_boundary"],
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pilot_dir", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    report = score(args.manifest.resolve(), args.pilot_dir.resolve())
    json_path = args.pilot_dir / "score-report.json"
    markdown_path = args.pilot_dir / "score-report.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
