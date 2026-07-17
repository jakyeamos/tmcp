"""Execute the condition-blind cost rejudge after source validation."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.tmcp_skill_eval_campaign_protocol as campaign_protocol  # noqa: E402
import scripts.tmcp_skill_eval_campaign_runtime as campaign_runtime  # noqa: E402
from scripts.tmcp_skill_eval_campaign_protocol import (
    COST_REJUDGE_PROTOCOL,
    COST_REJUDGE_SCHEMA_VERSION,
    DISABLED_CODEX_FEATURES,
    _atomic_json,
    _load_json,
    _sha256_file,
    _sha256_text,
    cost_rejudge_output_schema,
    cost_rejudge_prompt,
    remote_schema_preflight,
    validate_cost_rejudgment,
)  # noqa: E402
from scripts.tmcp_skill_eval_campaign_runtime import (
    _assert_empty_cleanroom,
    _invalidate_stage,
    _load_completed_stage,
    _run_stage,
)  # noqa: E402
from scripts.tmcp_skill_eval_cost_rejudge_source import (
    COST_REJUDGMENTS_SCHEMA,
    CostRejudgeCell,
    SourceTrace,
    _aggregate_usage,
    _load_source_traces,
    _source_summary,
    _unexpected_output_entries,
    _validate_args,
    build_cost_rejudge_cells,
)  # noqa: E402


def _harness_digests() -> dict[str, str]:
    paths = (
        Path(__file__).with_name("tmcp_skill_eval_cost_rejudge.py"),
        Path(__file__),
        Path(__file__).with_name("tmcp_skill_eval_cost_rejudge_source.py"),
        Path(campaign_protocol.__file__),
        Path(campaign_runtime.__file__),
    )
    return {path.name: _sha256_file(path) for path in paths}


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(item.get("text") or "") for item in content if isinstance(item, dict)
    )


def _prompt_input_preflight(args: argparse.Namespace) -> dict[str, Any]:
    probe = "TMCP_COST_REJUDGE_CLEANROOM_PROBE"
    auth_path = args.codex_home / "auth.json"
    if not auth_path.is_file():
        raise ValueError(f"Codex auth file is missing: {auth_path}")
    with tempfile.TemporaryDirectory(
        prefix="tmcp-codex-cost-rejudge-preflight-"
    ) as temporary:
        run_home = Path(temporary)
        (run_home / "auth.json").symlink_to(auth_path)
        command = [
            args.codex_bin,
            "debug",
            "prompt-input",
            "-c",
            "skills.include_instructions=false",
        ]
        for feature in DISABLED_CODEX_FEATURES:
            command.extend(["--disable", feature])
        command.append(probe)
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            cwd=args.cleanroom,
            env={**os.environ, "CODEX_HOME": str(run_home)},
            timeout=min(args.timeout_seconds, 60),
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list) or not all(
        isinstance(message, dict) for message in payload
    ):
        raise ValueError("Prompt-input preflight did not return a message list.")
    messages = [dict(message) for message in payload]
    user_messages = [message for message in messages if message.get("role") == "user"]
    if not user_messages or _message_text(user_messages[-1]).strip() != probe:
        raise ValueError("Prompt-input preflight did not preserve the probe boundary.")
    if any(message.get("role") == "assistant" for message in messages):
        raise ValueError("Prompt-input preflight contains prior assistant context.")
    rendered = "\n".join(_message_text(message) for message in messages)
    forbidden_markers = (
        "<skills_instructions>",
        "### Available skills",
        "# AGENTS.md instructions",
    )
    matched = [marker for marker in forbidden_markers if marker in rendered]
    if matched:
        raise ValueError(
            "Prompt-input preflight contains injected instructions: "
            + ", ".join(matched)
        )
    normalized = [
        {
            "type": message.get("type"),
            "role": message.get("role"),
            "content": message.get("content"),
        }
        for message in messages
    ]
    return {
        "audit": {
            "passed": True,
            "message_count": len(messages),
            "roles": [str(message.get("role") or "") for message in messages],
            "forbidden_markers": list(forbidden_markers),
            "prompt_context_sha256": _sha256_text(
                json.dumps(normalized, sort_keys=True, separators=(",", ":"))
            ),
        },
        "prompt_input": payload,
        "stderr": completed.stderr,
    }


async def _execute_cell(
    cell: CostRejudgeCell,
    *,
    source: SourceTrace,
    cost_bar: str,
    args: argparse.Namespace,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    cell_dir = args.output_dir / "cells" / cell.cell_id
    output_path = cell_dir / "cost-rejudge.json"
    schema_path = cell_dir / "cost-rejudge-output.schema.json"
    async with semaphore:
        cell_dir.mkdir(parents=True, exist_ok=True)
        _assert_empty_cleanroom(args.cleanroom)
        expected_schema = cost_rejudge_output_schema()
        if schema_path.is_file() and _load_json(schema_path) != expected_schema:
            raise ValueError(
                "Existing cost rejudge schema does not match the protocol."
            )
        _atomic_json(schema_path, expected_schema)
        artifact = source.runner_path.read_text(encoding="utf-8").strip()
        prompt = cost_rejudge_prompt(source.row["prompt"], artifact, cost_bar=cost_bar)
        stage = _load_completed_stage(cell_dir, "cost-rejudge", output_path)
        if stage is not None and (
            stage.get("prompt_sha256") != _sha256_text(prompt)
            or stage.get("output_schema_sha256") != _sha256_file(schema_path)
        ):
            _invalidate_stage(
                cell_dir,
                "cost-rejudge",
                output_path,
                reason="cost rejudge prompt or schema digest does not match",
            )
            stage = None
        verdict: dict[str, Any] | None = None
        if stage is not None:
            try:
                verdict = validate_cost_rejudgment(_load_json(output_path))
            except (ValueError, json.JSONDecodeError) as exc:
                _invalidate_stage(
                    cell_dir,
                    "cost-rejudge",
                    output_path,
                    reason=f"invalid cost rejudge verdict: {exc}",
                )
                stage = None
        if stage is None:
            stage = await _run_stage(
                cell_dir=cell_dir,
                stage="cost-rejudge",
                output_path=output_path,
                output_schema=schema_path,
                prompt=prompt,
                effort=args.judge_effort,
                args=args,
            )
            try:
                verdict = validate_cost_rejudgment(_load_json(output_path))
            except (ValueError, json.JSONDecodeError) as exc:
                _invalidate_stage(
                    cell_dir,
                    "cost-rejudge",
                    output_path,
                    reason=f"invalid cost rejudge verdict: {exc}",
                )
                raise
        assert verdict is not None
        _assert_empty_cleanroom(args.cleanroom)
        entry = {
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
                "prompt_context_sha256": args.prompt_context_sha256,
                "disabled_features": list(DISABLED_CODEX_FEATURES),
                "judge_event_audit": stage["event_audit"],
                "rejudge_artifact_sha256": stage["output_sha256"],
                "usage": stage["usage"],
            },
        }
        print(
            f"[{cell.order:02d}] completed {cell.cell_id} "
            f"cost_regression={verdict['cost_regression']}",
            flush=True,
        )
        return entry


async def run(args: argparse.Namespace) -> int:
    _validate_args(args)
    cost_bar = args.cost_bar_file.read_text(encoding="utf-8").strip()
    if not cost_bar:
        raise ValueError("Cost bar must be non-empty.")
    plan, source_manifest, source_traces, source_thread_ids = _load_source_traces(
        source_plan=args.source_plan,
        source_runs=args.source_runs,
        expected_trace_count=args.expected_trace_count,
    )
    del plan
    cells = build_cost_rejudge_cells(source_traces, seed=args.seed)
    if len(cells) != args.expected_trace_count:
        raise ValueError("Cost rejudge cell count does not match source trace count.")
    source_by_trace = {
        str(source.trace["trace_id"]): source for source in source_traces
    }
    if len(source_by_trace) != len(source_traces):
        raise ValueError("Source trace IDs are not unique.")
    if args.dry_run:
        preflight = {
            "audit": {
                "passed": False,
                "status": "not_run_in_dry_run",
                "prompt_context_sha256": "not-run",
            }
        }
        codex_version = "not-run-in-dry-run"
        remote_schema = {
            "schema": "tmcp-remote-schema-preflight-v0.1",
            "passed": False,
            "status": "not_run_in_dry_run",
        }
    else:
        args.cleanroom.mkdir(parents=True, exist_ok=True)
        _assert_empty_cleanroom(args.cleanroom)
        preflight = _prompt_input_preflight(args)
        codex_version = subprocess.run(
            [args.codex_bin, "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    args.prompt_context_sha256 = preflight["audit"]["prompt_context_sha256"]
    source_manifest_path = args.source_runs / "campaign-manifest.json"
    source_traces_path = args.source_runs / "traces.json"
    source_metadata = _source_summary(
        source_plan=args.source_plan,
        source_runs=args.source_runs,
        source_manifest=source_manifest_path,
        source_traces=source_traces_path,
        expected_trace_count=args.expected_trace_count,
        cost_bar=cost_bar,
    )
    harness_files = _harness_digests()
    prompt_digest = _sha256_text(
        cost_rejudge_prompt("<TASK>", "<ARTIFACT>", cost_bar="<COST_BAR>")
    )
    schema = cost_rejudge_output_schema()
    if not args.dry_run:
        remote_schema = await remote_schema_preflight(
            codex_bin=args.codex_bin,
            model=args.model,
            effort=args.judge_effort,
            base_codex_home=args.codex_home,
            timeout_seconds=args.timeout_seconds,
            output_schema=schema,
            prompt=cost_rejudge_prompt(
                "State whether the sentence requires unnecessary work.",
                "The sentence states one necessary verification step.",
                cost_bar=(
                    "Necessary verification work is not a cost regression; mark a "
                    "regression only for material unnecessary execution work."
                ),
            ),
            validate_output=validate_cost_rejudgment,
        )
    manifest = {
        "schema": COST_REJUDGE_PROTOCOL,
        "cost_rejudgments_schema": COST_REJUDGMENTS_SCHEMA,
        "experiment_id": source_manifest.get("experiment_id"),
        "source": source_metadata,
        "harness_sha256": _sha256_text(
            json.dumps(harness_files, sort_keys=True, separators=(",", ":"))
        ),
        "harness_files": harness_files,
        "cost_rejudge_schema_version": COST_REJUDGE_SCHEMA_VERSION,
        "cost_rejudge_schema_sha256": _sha256_text(
            json.dumps(schema, sort_keys=True, separators=(",", ":"))
        ),
        "cost_rejudge_protocol_sha256": prompt_digest,
        "model": args.model,
        "judge_effort": args.judge_effort,
        "max_transient_retries": args.max_transient_retries,
        "retry_backoff_seconds": args.retry_backoff_seconds,
        "codex_version": codex_version,
        "seed": args.seed,
        "cell_count": len(cells),
        "cells": [asdict(cell) for cell in cells],
        "isolation": {
            "ephemeral_process_per_role": True,
            "temporary_codex_home_per_role": True,
            "skills_include_instructions": False,
            "disabled_features": list(DISABLED_CODEX_FEATURES),
            "event_stream_audited": True,
            "cleanroom": str(args.cleanroom),
            "sandbox": "read-only",
            "prompt_input_preflight": preflight["audit"],
            "remote_schema_preflight_required": True,
        },
    }
    if args.dry_run:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    manifest_path = args.output_dir / "cost-rejudge-manifest.json"
    if args.output_dir.is_dir():
        unexpected_entries = _unexpected_output_entries(
            args.output_dir, args.cost_bar_file
        )
        if unexpected_entries and not manifest_path.is_file():
            raise ValueError(
                "Cost rejudge output directory is non-empty but has no manifest."
            )
        if manifest_path.is_file() and _load_json(manifest_path) != manifest:
            raise ValueError("Existing cost rejudge manifest does not match this run.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(manifest_path, manifest)
    _atomic_json(args.output_dir / "cost-rejudge-output.schema.json", schema)
    _atomic_json(args.output_dir / "prompt-input-preflight.json", preflight)
    _atomic_json(args.output_dir / "remote-schema-preflight.json", remote_schema)
    selected_cells = cells[: args.max_cells] if args.max_cells else cells
    semaphore = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(
        *[
            _execute_cell(
                cell,
                source=source_by_trace[cell.trace_id],
                cost_bar=cost_bar,
                args=args,
                semaphore=semaphore,
            )
            for cell in selected_cells
        ],
        return_exceptions=True,
    )
    errors = [
        {"cell_id": cell.cell_id, "order": cell.order, "error": str(result)}
        for cell, result in zip(selected_cells, results, strict=True)
        if isinstance(result, BaseException)
    ]
    if errors:
        _atomic_json(args.output_dir / "cost-rejudge-errors.json", errors)
        for error in errors:
            print(
                f"[{error['order']:02d}] failed {error['cell_id']}: {error['error']}",
                flush=True,
            )
    else:
        (args.output_dir / "cost-rejudge-errors.json").unlink(missing_ok=True)
    completed_entries: list[dict[str, Any]] = []
    for cell in cells:
        cell_dir = args.output_dir / "cells" / cell.cell_id
        output_path = cell_dir / "cost-rejudge.json"
        stage = _load_completed_stage(cell_dir, "cost-rejudge", output_path)
        if stage is None:
            continue
        source_trace = source_by_trace[cell.trace_id]
        artifact = source_trace.runner_path.read_text(encoding="utf-8").strip()
        prompt = cost_rejudge_prompt(
            source_trace.row["prompt"], artifact, cost_bar=cost_bar
        )
        schema_path = cell_dir / "cost-rejudge-output.schema.json"
        if (
            not schema_path.is_file()
            or _load_json(schema_path) != schema
            or stage.get("prompt_sha256") != _sha256_text(prompt)
            or stage.get("output_schema_sha256") != _sha256_file(schema_path)
        ):
            raise ValueError(
                "Completed cost rejudge stage does not match its contract."
            )
        verdict = validate_cost_rejudgment(_load_json(output_path))
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
                    "prompt_context_sha256": args.prompt_context_sha256,
                    "disabled_features": list(DISABLED_CODEX_FEATURES),
                    "judge_event_audit": stage["event_audit"],
                    "rejudge_artifact_sha256": stage["output_sha256"],
                    "usage": stage["usage"],
                },
            }
        )
    completed_thread_ids = [
        str(entry["provenance"]["judge_event_audit"]["thread_id"])
        for entry in completed_entries
    ]
    if len(completed_thread_ids) != len(set(completed_thread_ids)):
        raise ValueError("Cost rejudge reused a Codex thread ID.")
    if any(thread_id in source_thread_ids for thread_id in completed_thread_ids):
        raise ValueError("Cost rejudge reused a source campaign Codex thread ID.")
    sidecar = {
        "schema": COST_REJUDGMENTS_SCHEMA,
        "source": source_metadata,
        "rejudgments": completed_entries,
    }
    _atomic_json(args.output_dir / "cost-rejudgments.json", sidecar)
    summary = {
        "planned_cells": len(cells),
        "selected_cells": len(selected_cells),
        "completed_cells": len(completed_entries),
        "errors": len(errors),
        "cost_regressions": sum(
            1 for entry in completed_entries if entry["cost_regression"]
        ),
        "unique_judge_threads": len(completed_thread_ids),
        "expected_judge_threads_at_completion": len(cells),
        "usage": _aggregate_usage(completed_entries),
    }
    _atomic_json(args.output_dir / "cost-rejudge-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if errors else 0
