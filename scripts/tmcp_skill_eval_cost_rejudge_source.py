"""Validate and normalize fixed source artifacts for the cost-rejudge harness."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tmcp_skill_eval_campaign_protocol import (
    CAMPAIGN_PROTOCOL,
    COST_REJUDGE_PROTOCOL,
    _audit_event_stream,
    _load_json,
    _sha256_file,
    _sha256_text,
    _stable_id,
)  # noqa: E402


COST_REJUDGMENTS_SCHEMA = "tmcp-skill-eval-cost-rejudgment-v0.1"


@dataclass(frozen=True)
class CostRejudgeCell:
    order: int
    cell_id: str
    trace_id: str
    source_trace_digest: str
    matrix_row_id: str
    runner_artifact: str
    runner_artifact_sha256: str
    raw_judge_artifact: str
    raw_judge_artifact_sha256: str


@dataclass(frozen=True)
class SourceTrace:
    trace: dict[str, Any]
    row: dict[str, Any]
    runner_path: Path
    runner_artifact: str
    runner_artifact_sha256: str
    raw_judge_artifact: str
    raw_judge_artifact_sha256: str
    source_trace_digest: str


def _canonical_json_digest(payload: Any) -> str:
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _safe_source_path(source_runs: Path, relative_path: str) -> Path:
    candidate = (source_runs / relative_path).resolve()
    try:
        candidate.relative_to(source_runs.resolve())
    except ValueError as exc:
        raise ValueError("Source artifact path escapes source-runs.") from exc
    if not candidate.is_file():
        raise ValueError(f"Source artifact is missing: {relative_path}")
    return candidate


def _read_completed_source_stage(
    cell_dir: Path, stage: str, output_path: Path
) -> dict[str, Any]:
    """Validate a source stage without mutating the historical campaign."""

    marker_path = cell_dir / f"{stage}-complete.json"
    events_path = cell_dir / f"{stage}-events.jsonl"
    stderr_path = cell_dir / f"{stage}-stderr.log"
    usage_path = cell_dir / f"{stage}-usage.json"
    if not all(
        path.is_file() for path in (marker_path, events_path, stderr_path, usage_path)
    ):
        raise ValueError(f"Source {stage} stage is incomplete.")
    marker = _load_json(marker_path)
    if not isinstance(marker, dict):
        raise ValueError(f"Source {stage} marker is not an object.")
    if marker.get("schema") != "tmcp-campaign-stage-v0.1":
        raise ValueError(f"Source {stage} marker schema does not match.")
    if marker.get("stage") != stage:
        raise ValueError(f"Source {stage} marker role does not match.")
    if marker.get("output_sha256") != _sha256_file(output_path):
        raise ValueError(f"Source {stage} output digest does not match.")
    if marker.get("events_sha256") != _sha256_file(events_path):
        raise ValueError(f"Source {stage} event digest does not match.")
    event_audit = _audit_event_stream(events_path.read_text(encoding="utf-8"))
    if marker.get("event_audit") != event_audit:
        raise ValueError(f"Source {stage} event audit does not match.")
    if marker.get("stderr_sha256") != _sha256_file(stderr_path):
        raise ValueError(f"Source {stage} stderr digest does not match.")
    usage = _load_json(usage_path)
    if marker.get("usage") != usage or not isinstance(usage, dict) or not usage:
        raise ValueError(f"Source {stage} usage does not match.")
    return marker


def _source_rows(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in plan.get("task_matrix", []):
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("matrix_row_id") or "")
        if not row_id:
            continue
        if row_id in rows:
            raise ValueError("Source plan contains duplicate matrix_row_id values.")
        if not isinstance(row.get("prompt"), str) or not row["prompt"].strip():
            raise ValueError(f"Source plan row {row_id} has an empty prompt.")
        rows[row_id] = row
    if not rows:
        raise ValueError("Source plan has no task matrix rows.")
    return rows


def _load_source_traces(
    *,
    source_plan: Path,
    source_runs: Path,
    expected_trace_count: int,
) -> tuple[dict[str, Any], dict[str, Any], list[SourceTrace], set[str]]:
    if not source_plan.is_file():
        raise ValueError(f"Source plan is missing: {source_plan}")
    manifest_path = source_runs / "campaign-manifest.json"
    traces_path = source_runs / "traces.json"
    if not manifest_path.is_file() or not traces_path.is_file():
        raise ValueError(
            "Source runs must contain campaign-manifest.json and traces.json."
        )
    plan = _load_json(source_plan)
    manifest = _load_json(manifest_path)
    traces = _load_json(traces_path)
    if not isinstance(plan, dict) or not isinstance(manifest, dict):
        raise ValueError("Source plan and campaign manifest must be JSON objects.")
    if manifest.get("schema") != CAMPAIGN_PROTOCOL:
        raise ValueError("Source campaign manifest schema does not match.")
    if manifest.get("plan_sha256") != _sha256_file(source_plan):
        raise ValueError("Source campaign manifest is not bound to source plan.")
    if not isinstance(traces, list) or len(traces) != expected_trace_count:
        raise ValueError(
            f"Expected {expected_trace_count} source traces, found "
            f"{len(traces) if isinstance(traces, list) else 'non-list'}."
        )
    manifest_cells = manifest.get("cells")
    if (
        not isinstance(manifest_cells, list)
        or len(manifest_cells) != expected_trace_count
    ):
        raise ValueError("Source campaign manifest cell count does not match.")
    manifest_by_cell: dict[str, dict[str, Any]] = {}
    for cell in manifest_cells:
        if not isinstance(cell, dict):
            raise ValueError("Source campaign manifest contains an invalid cell.")
        cell_id = str(cell.get("cell_id") or "")
        if not cell_id or cell_id in manifest_by_cell:
            raise ValueError("Source campaign manifest cell IDs are invalid.")
        manifest_by_cell[cell_id] = cell
    rows = _source_rows(plan)
    source_traces: list[SourceTrace] = []
    source_thread_ids: set[str] = set()
    seen_trace_ids: set[str] = set()
    seen_cell_ids: set[str] = set()
    for trace in traces:
        if not isinstance(trace, dict):
            raise ValueError("Source traces must contain objects.")
        trace_id = str(trace.get("trace_id") or "")
        if not trace_id or trace_id in seen_trace_ids:
            raise ValueError("Source trace IDs are invalid.")
        seen_trace_ids.add(trace_id)
        campaign = trace.get("campaign")
        if not isinstance(campaign, dict):
            raise ValueError("Source trace campaign metadata is missing.")
        cell_id = str(campaign.get("cell_id") or "")
        if not cell_id or cell_id in seen_cell_ids or cell_id not in manifest_by_cell:
            raise ValueError("Source trace does not match a unique manifest cell.")
        seen_cell_ids.add(cell_id)
        manifest_cell = manifest_by_cell[cell_id]
        if trace.get("experiment_id") != manifest.get("experiment_id") or trace.get(
            "matrix_row_id"
        ) != manifest_cell.get("matrix_row_id"):
            raise ValueError("Source trace does not match campaign manifest metadata.")
        row_id = str(trace.get("matrix_row_id") or "")
        row = rows.get(row_id)
        if row is None:
            raise ValueError("Source trace matrix row is absent from the source plan.")
        if trace.get("task_id") != row.get("task_id"):
            raise ValueError("Source trace task ID does not match its plan row.")
        cell_dir = source_runs / "cells" / cell_id
        aggregate_trace_path = cell_dir / "trace.json"
        if (
            not aggregate_trace_path.is_file()
            or _load_json(aggregate_trace_path) != trace
        ):
            raise ValueError(
                "Source trace aggregate does not match its cell trace artifact."
            )
        runner_artifact = campaign.get("runner_artifact")
        raw_judge_artifact = campaign.get("judge_artifact")
        if not isinstance(runner_artifact, str) or not isinstance(
            raw_judge_artifact, str
        ):
            raise ValueError("Source trace artifact paths are missing.")
        runner_path = _safe_source_path(source_runs, runner_artifact)
        raw_judge_path = _safe_source_path(source_runs, raw_judge_artifact)
        runner_stage = _read_completed_source_stage(cell_dir, "runner", runner_path)
        raw_judge_stage = _read_completed_source_stage(
            cell_dir, "judge", raw_judge_path
        )
        if (
            campaign.get("runner_artifact_sha256") != runner_stage["output_sha256"]
            or campaign.get("judge_artifact_sha256") != raw_judge_stage["output_sha256"]
        ):
            raise ValueError(
                "Source trace artifact digests do not match completed stages."
            )
        provenance = trace.get("provenance")
        if not isinstance(provenance, dict) or any(
            provenance.get(field) is not True
            for field in ("runner_blinded", "judge_blinded", "isolated_session")
        ):
            raise ValueError("Source trace controlled provenance is invalid.")
        if (
            provenance.get("runner_event_audit") != runner_stage["event_audit"]
            or provenance.get("judge_event_audit") != raw_judge_stage["event_audit"]
        ):
            raise ValueError("Source trace event audits do not match source stages.")
        for stage in (runner_stage, raw_judge_stage):
            thread_id = str(stage["event_audit"].get("thread_id") or "")
            if not thread_id or thread_id in source_thread_ids:
                raise ValueError("Source campaign reuses or omits a Codex thread ID.")
            source_thread_ids.add(thread_id)
        verdict = trace.get("case_verdict")
        if not isinstance(verdict, dict) or not isinstance(
            verdict.get("cost_regression"), bool
        ):
            raise ValueError("Source trace cost verdict is invalid.")
        source_traces.append(
            SourceTrace(
                trace=trace,
                row=row,
                runner_path=runner_path,
                runner_artifact=runner_artifact,
                runner_artifact_sha256=str(runner_stage["output_sha256"]),
                raw_judge_artifact=raw_judge_artifact,
                raw_judge_artifact_sha256=str(raw_judge_stage["output_sha256"]),
                source_trace_digest=_canonical_json_digest(trace),
            )
        )
    if set(manifest_by_cell) != seen_cell_ids:
        raise ValueError("Source traces do not cover the complete campaign manifest.")
    return plan, manifest, source_traces, source_thread_ids


def build_cost_rejudge_cells(
    source_traces: list[SourceTrace], *, seed: int
) -> list[CostRejudgeCell]:
    """Randomize fixed artifacts without surfacing their original condition to judges."""

    cells = [
        CostRejudgeCell(
            order=0,
            cell_id=_stable_id(
                str(source.trace["experiment_id"]),
                str(source.trace["trace_id"]),
                COST_REJUDGE_PROTOCOL,
                prefix="cost-rejudge-cell",
            ),
            trace_id=str(source.trace["trace_id"]),
            source_trace_digest=source.source_trace_digest,
            matrix_row_id=str(source.trace["matrix_row_id"]),
            runner_artifact=source.runner_artifact,
            runner_artifact_sha256=source.runner_artifact_sha256,
            raw_judge_artifact=source.raw_judge_artifact,
            raw_judge_artifact_sha256=source.raw_judge_artifact_sha256,
        )
        for source in source_traces
    ]
    if len({cell.cell_id for cell in cells}) != len(cells):
        raise ValueError("Cost rejudge cell IDs are not unique.")
    random.Random(seed).shuffle(cells)
    return [
        CostRejudgeCell(**{**asdict(cell), "order": index})
        for index, cell in enumerate(cells, start=1)
    ]


def _aggregate_usage(entries: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {"traces": len(entries)}
    for entry in entries:
        provenance = entry.get("provenance")
        usage = provenance.get("usage") if isinstance(provenance, dict) else None
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, int) and not isinstance(value, bool):
                totals[str(key)] = totals.get(str(key), 0) + value
    return totals


def _source_summary(
    *,
    source_plan: Path,
    source_runs: Path,
    source_manifest: Path,
    source_traces: Path,
    expected_trace_count: int,
    cost_bar: str,
) -> dict[str, Any]:
    return {
        "source_plan": str(source_plan),
        "source_plan_sha256": _sha256_file(source_plan),
        "source_runs": str(source_runs),
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": _sha256_file(source_manifest),
        "source_traces": str(source_traces),
        "source_traces_sha256": _sha256_file(source_traces),
        "expected_trace_count": expected_trace_count,
        "cost_bar_sha256": _sha256_text(cost_bar),
        "raw_labels_preserved": True,
    }


def _unexpected_output_entries(output_dir: Path, cost_bar_file: Path) -> list[Path]:
    if not output_dir.is_dir():
        return []
    permitted_inputs = (
        {cost_bar_file.resolve()}
        if cost_bar_file.resolve().parent == output_dir.resolve()
        else set()
    )
    return [
        path
        for path in output_dir.iterdir()
        if path.name != ".DS_Store" and path.resolve() not in permitted_inputs
    ]


def _validate_args(args: argparse.Namespace) -> None:
    if args.concurrency < 1:
        raise ValueError("concurrency must be at least 1.")
    if args.timeout_seconds < 1:
        raise ValueError("timeout-seconds must be at least 1.")
    if args.max_transient_retries < 0:
        raise ValueError("max-transient-retries must be non-negative.")
    if args.retry_backoff_seconds < 0:
        raise ValueError("retry-backoff-seconds must be non-negative.")
    if args.expected_trace_count != 72:
        raise ValueError("This campaign-wide cost rejudge requires exactly 72 traces.")
    if (
        args.max_cells is not None
        and not 1 <= args.max_cells <= args.expected_trace_count
    ):
        raise ValueError("max-cells must be between 1 and expected-trace-count.")
    source_runs = args.source_runs.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir == source_runs or output_dir.is_relative_to(source_runs):
        raise ValueError(
            "output-dir must be outside source-runs to preserve raw evidence."
        )
    if args.cleanroom.resolve() in {source_runs, output_dir}:
        raise ValueError("cleanroom must be distinct from source-runs and output-dir.")
    if not args.cost_bar_file.is_file():
        raise ValueError(f"Cost bar file is missing: {args.cost_bar_file}")
