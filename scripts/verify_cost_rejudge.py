#!/usr/bin/env python3
"""Verify a persisted condition-blind cost-rejudge bundle without remote calls."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tmcp_skill_eval_campaign_protocol import (  # noqa: E402
    COST_REJUDGE_PROTOCOL,
    COST_REJUDGE_SCHEMA_VERSION,
    DISABLED_CODEX_FEATURES,
    _audit_event_stream,
    _load_json,
    _sha256_file,
    _sha256_text,
    cost_rejudge_output_schema,
    cost_rejudge_prompt,
    validate_cost_rejudgment,
)
from scripts.tmcp_skill_eval_cost_rejudge_source import (  # noqa: E402
    COST_REJUDGMENTS_SCHEMA,
    CostRejudgeCell,
    _aggregate_usage,
    _is_source_bundle_study,
    _load_source_traces,
    build_cost_rejudge_cells,
)
from tmcp_runtime.services.evaluation_cost_rejudge import (  # noqa: E402
    preregistered_cost_rejudge_binding,
    validate_cost_rejudgments,
    validate_preregistered_cost_rejudge_binding,
)


VERIFICATION_SCHEMA = "tmcp-cost-rejudge-verification-v0.1"
_STAGE_SCHEMA = "tmcp-campaign-stage-v0.1"
_REMOTE_SCHEMA_PREFLIGHT = "tmcp-remote-schema-preflight-v0.1"


def _object(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object.")
    return value


def _non_empty_string(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string.")
    return value


def _verify_source(
    source: Mapping[str, Any],
    *,
    source_plan: Path,
    source_runs: Path,
    cost_bar_file: Path,
    expected_trace_count: int,
) -> dict[str, Any]:
    manifest_path = source_runs / "campaign-manifest.json"
    traces_path = source_runs / "traces.json"
    expected = {
        "source_plan_sha256": _sha256_file(source_plan),
        "source_manifest_sha256": _sha256_file(manifest_path),
        "source_traces_sha256": _sha256_file(traces_path),
        "cost_bar_sha256": _sha256_file(cost_bar_file),
        "expected_trace_count": expected_trace_count,
        "raw_labels_preserved": True,
    }
    for field, value in expected.items():
        if source.get(field) != value:
            raise ValueError(f"Cost rejudge source {field} does not match inputs.")
    for field in ("source_plan", "source_runs", "source_manifest", "source_traces"):
        _non_empty_string(source.get(field), context=f"Cost rejudge source {field}")
    if "cost_bar_file" in source:
        _non_empty_string(
            source["cost_bar_file"], context="Cost rejudge source cost_bar_file"
        )
    if "cost_bar_prompt_sha256" in source and source[
        "cost_bar_prompt_sha256"
    ] != _sha256_text(cost_bar_file.read_text(encoding="utf-8").strip()):
        raise ValueError("Cost rejudge source cost bar prompt digest does not match.")
    return dict(source)


def _verify_isolation(
    output_dir: Path, manifest: Mapping[str, Any], schema_path: Path
) -> dict[str, bool]:
    isolation = _object(manifest.get("isolation"), context="Cost rejudge isolation")
    expected_flags = {
        "ephemeral_process_per_role": True,
        "temporary_codex_home_per_role": True,
        "skills_include_instructions": False,
        "event_stream_audited": True,
        "sandbox": "read-only",
    }
    for field, value in expected_flags.items():
        if isolation.get(field) != value:
            raise ValueError(f"Cost rejudge isolation {field} does not match.")
    if isolation.get("disabled_features") != list(DISABLED_CODEX_FEATURES):
        raise ValueError("Cost rejudge disabled features do not match the protocol.")
    preflight = _object(
        _load_json(output_dir / "prompt-input-preflight.json"),
        context="Prompt-input preflight",
    )
    audit = _object(preflight.get("audit"), context="Prompt-input preflight audit")
    if (
        audit.get("passed") is not True
        or isolation.get("prompt_input_preflight") != audit
    ):
        raise ValueError("Cost rejudge prompt-input preflight does not match manifest.")

    remote_required = isolation.get("remote_schema_preflight_required") is True
    remote_path = output_dir / "remote-schema-preflight.json"
    if remote_required:
        remote = _object(_load_json(remote_path), context="Remote-schema preflight")
        if (
            remote.get("schema") != _REMOTE_SCHEMA_PREFLIGHT
            or remote.get("passed") is not True
            or remote.get("model") != manifest.get("model")
            or remote.get("effort") != manifest.get("judge_effort")
            or remote.get("output_schema_sha256") != _sha256_file(schema_path)
        ):
            raise ValueError("Cost rejudge remote-schema preflight does not match.")
        expected_prompt = cost_rejudge_prompt(
            "State whether the sentence requires unnecessary work.",
            "The sentence states one necessary verification step.",
            cost_bar=(
                "Necessary verification work is not a cost regression; mark a "
                "regression only for material unnecessary execution work."
            ),
        )
        if remote.get("prompt_sha256") != _sha256_text(expected_prompt):
            raise ValueError("Cost rejudge remote-schema prompt digest does not match.")
    elif remote_path.exists():
        remote = _object(_load_json(remote_path), context="Remote-schema preflight")
        if remote.get("passed") is not True:
            raise ValueError("Cost rejudge remote-schema preflight did not pass.")
    return {
        "prompt_input_preflight": True,
        "remote_schema_preflight": remote_required,
    }


def _verify_stage(
    *,
    cell_dir: Path,
    cell: CostRejudgeCell,
    task_prompt: str,
    runner_artifact: str,
    cost_bar: str,
    output_schema: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage = "cost-rejudge"
    output_path = cell_dir / "cost-rejudge.json"
    schema_path = cell_dir / "cost-rejudge-output.schema.json"
    events_path = cell_dir / f"{stage}-events.jsonl"
    stderr_path = cell_dir / f"{stage}-stderr.log"
    usage_path = cell_dir / f"{stage}-usage.json"
    marker_path = cell_dir / f"{stage}-complete.json"
    if not all(
        path.is_file()
        for path in (
            output_path,
            schema_path,
            events_path,
            stderr_path,
            usage_path,
            marker_path,
        )
    ):
        raise ValueError(f"Cost rejudge cell {cell.cell_id} is incomplete.")
    if _load_json(schema_path) != output_schema:
        raise ValueError(f"Cost rejudge cell {cell.cell_id} schema does not match.")
    marker = _object(
        _load_json(marker_path), context=f"Cost rejudge cell {cell.cell_id} marker"
    )
    if marker.get("schema") != _STAGE_SCHEMA or marker.get("stage") != stage:
        raise ValueError(
            f"Cost rejudge cell {cell.cell_id} marker protocol is invalid."
        )
    prompt = cost_rejudge_prompt(task_prompt, runner_artifact, cost_bar=cost_bar)
    expected = {
        "prompt_sha256": _sha256_text(prompt),
        "output_schema_sha256": _sha256_file(schema_path),
        "output_sha256": _sha256_file(output_path),
        "events_sha256": _sha256_file(events_path),
        "stderr_sha256": _sha256_file(stderr_path),
    }
    for field, value in expected.items():
        if marker.get(field) != value:
            raise ValueError(
                f"Cost rejudge cell {cell.cell_id} {field} does not match."
            )
    event_audit = _audit_event_stream(events_path.read_text(encoding="utf-8"))
    if (
        marker.get("event_audit") != event_audit
        or event_audit.get("passed") is not True
    ):
        raise ValueError(
            f"Cost rejudge cell {cell.cell_id} event audit does not match."
        )
    usage = _load_json(usage_path)
    if marker.get("usage") != usage or not isinstance(usage, dict) or not usage:
        raise ValueError(f"Cost rejudge cell {cell.cell_id} usage does not match.")
    verdict = validate_cost_rejudgment(_load_json(output_path))
    return marker, verdict


def _verify_manifest(
    manifest: Mapping[str, Any],
    *,
    source_manifest: Mapping[str, Any],
    cells: list[CostRejudgeCell],
    source: Mapping[str, Any],
    plan: Mapping[str, Any],
    schema: Mapping[str, Any],
    expected_trace_count: int,
) -> dict[str, Any] | None:
    if manifest.get("schema") != COST_REJUDGE_PROTOCOL:
        raise ValueError("Cost rejudge manifest schema does not match.")
    if manifest.get("cost_rejudgments_schema") != COST_REJUDGMENTS_SCHEMA:
        raise ValueError("Cost rejudge manifest sidecar schema does not match.")
    if manifest.get("experiment_id") != source_manifest.get("experiment_id"):
        raise ValueError("Cost rejudge manifest experiment does not match source.")
    if manifest.get("source") != source:
        raise ValueError("Cost rejudge manifest source metadata does not match.")
    if manifest.get("cell_count") != expected_trace_count or manifest.get("cells") != [
        asdict(cell) for cell in cells
    ]:
        raise ValueError("Cost rejudge manifest cells do not match source traces.")
    if (
        manifest.get("cost_rejudge_schema_version") != COST_REJUDGE_SCHEMA_VERSION
        or manifest.get("cost_rejudge_schema_sha256")
        != _sha256_text(json.dumps(schema, sort_keys=True, separators=(",", ":")))
        or manifest.get("cost_rejudge_protocol_sha256")
        != _sha256_text(
            cost_rejudge_prompt("<TASK>", "<ARTIFACT>", cost_bar="<COST_BAR>")
        )
    ):
        raise ValueError("Cost rejudge manifest protocol contract does not match.")
    _non_empty_string(manifest.get("model"), context="Cost rejudge manifest model")
    _non_empty_string(
        manifest.get("judge_effort"), context="Cost rejudge manifest judge effort"
    )
    if not isinstance(manifest.get("seed"), int):
        raise ValueError("Cost rejudge manifest seed must be an integer.")
    binding = preregistered_cost_rejudge_binding(plan)
    observed_binding = manifest.get("preregistered_cost_rejudge")
    if binding is None:
        if observed_binding is not None:
            raise ValueError(
                "Cost rejudge manifest claims an undeclared policy binding."
            )
    else:
        validate_preregistered_cost_rejudge_binding(plan, observed_binding)
        if (
            Path(
                _non_empty_string(
                    source.get("cost_bar_file"),
                    context="Cost rejudge source cost_bar_file",
                )
            ).name
            != binding["cost_bar_file"]
            or source.get("cost_bar_sha256") != binding["cost_bar_sha256"]
        ):
            raise ValueError(
                "Cost rejudge source cost bar does not match policy binding."
            )
        for field in ("model", "judge_effort", "seed", "expected_trace_count"):
            observed = (
                manifest.get(field)
                if field != "expected_trace_count"
                else expected_trace_count
            )
            if observed != binding[field]:
                raise ValueError(
                    f"Cost rejudge manifest {field} does not match policy binding."
                )
    return binding


def verify_cost_rejudge(
    *,
    source_plan: Path,
    source_runs: Path,
    cost_bar_file: Path,
    rejudge_runs: Path,
    expected_trace_count: int,
) -> dict[str, Any]:
    """Verify a complete sidecar and report whether it meets current promotion gates."""

    if expected_trace_count < 1:
        raise ValueError("expected_trace_count must be at least 1.")
    if not cost_bar_file.is_file():
        raise ValueError(f"Cost bar file is missing: {cost_bar_file}")
    if not rejudge_runs.is_dir():
        raise ValueError(f"Cost rejudge runs directory is missing: {rejudge_runs}")
    manifest = _object(
        _load_json(rejudge_runs / "cost-rejudge-manifest.json"),
        context="Cost rejudge manifest",
    )
    source = _verify_source(
        _object(manifest.get("source"), context="Cost rejudge manifest source"),
        source_plan=source_plan,
        source_runs=source_runs,
        cost_bar_file=cost_bar_file,
        expected_trace_count=expected_trace_count,
    )
    plan, source_manifest, source_traces, source_thread_ids = _load_source_traces(
        source_plan=source_plan,
        source_runs=source_runs,
        expected_trace_count=expected_trace_count,
    )
    source_bundle_contract_verified = _is_source_bundle_study(plan)
    cells = build_cost_rejudge_cells(source_traces, seed=manifest.get("seed"))
    schema = cost_rejudge_output_schema()
    schema_path = rejudge_runs / "cost-rejudge-output.schema.json"
    if not schema_path.is_file() or _load_json(schema_path) != schema:
        raise ValueError("Cost rejudge root output schema does not match.")
    binding = _verify_manifest(
        manifest,
        source_manifest=source_manifest,
        cells=cells,
        source=source,
        plan=plan,
        schema=schema,
        expected_trace_count=expected_trace_count,
    )
    isolation = _verify_isolation(rejudge_runs, manifest, schema_path)
    if (rejudge_runs / "cost-rejudge-errors.json").exists():
        raise ValueError("Cost rejudge bundle retains failed cells.")
    cell_root = rejudge_runs / "cells"
    if not cell_root.is_dir():
        raise ValueError("Cost rejudge cells directory is missing.")
    expected_cell_ids = {cell.cell_id for cell in cells}
    actual_cell_ids = {
        path.name for path in cell_root.iterdir() if path.name != ".DS_Store"
    }
    if actual_cell_ids != expected_cell_ids:
        raise ValueError("Cost rejudge cell directory coverage does not match.")
    source_by_trace = {
        str(source.trace["trace_id"]): source for source in source_traces
    }
    cost_bar = cost_bar_file.read_text(encoding="utf-8").strip()
    completed_entries: list[dict[str, Any]] = []
    judge_thread_ids: set[str] = set()
    for cell in cells:
        source_trace = source_by_trace[cell.trace_id]
        marker, verdict = _verify_stage(
            cell_dir=cell_root / cell.cell_id,
            cell=cell,
            task_prompt=str(source_trace.row["prompt"]),
            runner_artifact=source_trace.runner_path.read_text(
                encoding="utf-8"
            ).strip(),
            cost_bar=cost_bar,
            output_schema=schema,
        )
        event_audit = marker["event_audit"]
        thread_id = str(event_audit["thread_id"])
        if thread_id in source_thread_ids or thread_id in judge_thread_ids:
            raise ValueError("Cost rejudge must use new unique judge thread IDs.")
        judge_thread_ids.add(thread_id)
        completed_entries.append(
            {
                "trace_id": cell.trace_id,
                "source_trace_digest": cell.source_trace_digest,
                "cost_regression": verdict["cost_regression"],
                "evidence": verdict["evidence"],
                "rationale": verdict["rationale"],
                "provenance": {
                    "fresh_judge": True,
                    "fresh_session": True,
                    "judge_blinded": True,
                    "condition_hidden": True,
                    "source_artifact_only": True,
                    "isolated_session": True,
                    "prompt_context_sha256": manifest["isolation"][
                        "prompt_input_preflight"
                    ]["prompt_context_sha256"],
                    "disabled_features": list(DISABLED_CODEX_FEATURES),
                    "judge_event_audit": event_audit,
                    "rejudge_artifact_sha256": marker["output_sha256"],
                    "usage": marker["usage"],
                },
            }
        )
    sidecar = _object(
        _load_json(rejudge_runs / "cost-rejudgments.json"),
        context="Cost rejudgments sidecar",
    )
    if (
        sidecar.get("schema") != COST_REJUDGMENTS_SCHEMA
        or sidecar.get("source") != source
    ):
        raise ValueError("Cost rejudgments sidecar metadata does not match manifest.")
    if sidecar.get("preregistered_cost_rejudge") != manifest.get(
        "preregistered_cost_rejudge"
    ):
        raise ValueError("Cost rejudgments sidecar policy binding does not match.")
    if sidecar.get("rejudgments") != completed_entries:
        raise ValueError("Cost rejudgments sidecar does not match cell artifacts.")
    validate_cost_rejudgments(
        [source.trace for source in source_traces], sidecar, plan=plan
    )
    summary = _object(
        _load_json(rejudge_runs / "cost-rejudge-summary.json"),
        context="Cost rejudge summary",
    )
    expected_summary = {
        "planned_cells": len(cells),
        "selected_cells": len(cells),
        "completed_cells": len(completed_entries),
        "errors": 0,
        "cost_regressions": sum(
            1 for entry in completed_entries if entry["cost_regression"]
        ),
        "unique_judge_threads": len(judge_thread_ids),
        "expected_judge_threads_at_completion": len(cells),
        "usage": _aggregate_usage(completed_entries),
    }
    if summary != expected_summary:
        raise ValueError("Cost rejudge summary does not match cell artifacts.")
    policy_bound = binding is not None
    promotion_ready = policy_bound and isolation["remote_schema_preflight"]
    return {
        "schema": VERIFICATION_SCHEMA,
        "source_plan": str(source_plan.resolve()),
        "source_runs": str(source_runs.resolve()),
        "rejudge_runs": str(rejudge_runs.resolve()),
        "experiment_id": str(source_manifest["experiment_id"]),
        "expected_trace_count": expected_trace_count,
        "static": {
            "source_traces_verified": len(source_traces),
            "rejudge_cells_verified": len(completed_entries),
            "unique_new_judge_threads": len(judge_thread_ids),
            "policy_binding": "bound" if policy_bound else "not_preregistered",
            "remote_schema_preflight": (
                "verified"
                if isolation["remote_schema_preflight"]
                else "legacy_not_required"
            ),
            "source_bundle_campaign_contract": (
                "verified" if source_bundle_contract_verified else "not_applicable"
            ),
            "promotion_ready": promotion_ready,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--source-runs", type=Path, required=True)
    parser.add_argument("--cost-bar-file", type=Path, required=True)
    parser.add_argument("--rejudge-runs", type=Path, required=True)
    parser.add_argument("--expected-trace-count", type=int, required=True)
    parser.add_argument("--require-promotion-ready", action="store_true")
    args = parser.parse_args()
    try:
        report = verify_cost_rejudge(
            source_plan=args.source_plan,
            source_runs=args.source_runs,
            cost_bar_file=args.cost_bar_file,
            rejudge_runs=args.rejudge_runs,
            expected_trace_count=args.expected_trace_count,
        )
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as error:
        print(
            json.dumps(
                {"schema": VERIFICATION_SCHEMA, "ok": False, "error": str(error)}
            )
        )
        return 1
    ok = not args.require_promotion_ready or report["static"]["promotion_ready"]
    print(json.dumps({**report, "ok": ok}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
