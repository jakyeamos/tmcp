"""Stage persistence, resume validation, and cell execution for skill evals."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from scripts.tmcp_skill_eval_campaign_protocol import (
    DISABLED_CODEX_FEATURES,
    CampaignCell,
    CodexRunError,
    _atomic_json,
    _atomic_text,
    _audit_event_stream,
    _load_json,
    _run_codex,
    _sha256_file,
    _sha256_text,
    _stable_id,
    _validate_judgment,
    codex_command,
    judge_criteria,
    judge_output_schema,
    judge_prompt,
    runner_prompt,
    transient_failure_classification,
)


def _stage_paths(cell_dir: Path, stage: str, output_path: Path) -> list[Path]:
    return [
        output_path,
        cell_dir / f"{stage}-events.jsonl",
        cell_dir / f"{stage}-stderr.log",
        cell_dir / f"{stage}-usage.json",
        cell_dir / f"{stage}-complete.json",
    ]


def _invalidate_stage(
    cell_dir: Path, stage: str, output_path: Path, *, reason: str
) -> None:
    invalidations_path = cell_dir / "invalidated-stages.json"
    invalidations = (
        _load_json(invalidations_path) if invalidations_path.is_file() else []
    )
    if not isinstance(invalidations, list):
        raise ValueError("Invalidated-stage log must contain a list.")
    attempt = 1 + sum(
        1
        for invalidation in invalidations
        if isinstance(invalidation, dict) and invalidation.get("stage") == stage
    )
    archive_dir = cell_dir / "invalidated" / f"{stage}-attempt-{attempt}"
    while archive_dir.exists():
        attempt += 1
        archive_dir = cell_dir / "invalidated" / f"{stage}-attempt-{attempt}"
    archive_dir.mkdir(parents=True, exist_ok=False)
    output_digest = _sha256_file(output_path) if output_path.is_file() else None
    for path in _stage_paths(cell_dir, stage, output_path):
        if path.exists():
            os.replace(path, archive_dir / path.name)
    invalidations.append(
        {
            "stage": stage,
            "reason": reason,
            "output_sha256": output_digest,
            "archive": str(archive_dir.relative_to(cell_dir)),
        }
    )
    _atomic_json(invalidations_path, invalidations)


def _load_completed_stage(
    cell_dir: Path, stage: str, output_path: Path
) -> dict[str, Any] | None:
    paths = _stage_paths(cell_dir, stage, output_path)
    marker_path = cell_dir / f"{stage}-complete.json"
    if not any(path.exists() for path in paths):
        return None
    try:
        marker = _load_json(marker_path)
        events_path = cell_dir / f"{stage}-events.jsonl"
        stderr_path = cell_dir / f"{stage}-stderr.log"
        usage_path = cell_dir / f"{stage}-usage.json"
        if not isinstance(marker, dict):
            raise ValueError("stage marker is not an object")
        if marker.get("schema") != "tmcp-campaign-stage-v0.1":
            raise ValueError("stage marker schema does not match")
        if marker.get("stage") != stage:
            raise ValueError("stage marker role does not match")
        if not output_path.is_file() or marker.get("output_sha256") != _sha256_file(
            output_path
        ):
            raise ValueError("stage output digest does not match")
        if not events_path.is_file() or marker.get("events_sha256") != _sha256_file(
            events_path
        ):
            raise ValueError("stage event digest does not match")
        if marker.get("event_audit") != _audit_event_stream(
            events_path.read_text(encoding="utf-8")
        ):
            raise ValueError("stage event audit does not match")
        if not stderr_path.is_file() or marker.get("stderr_sha256") != _sha256_file(
            stderr_path
        ):
            raise ValueError("stage stderr digest does not match")
        if not usage_path.is_file() or marker.get("usage") != _load_json(usage_path):
            raise ValueError("stage usage does not match")
        if not isinstance(marker.get("usage"), dict) or not marker["usage"]:
            raise ValueError("stage usage is missing")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _invalidate_stage(cell_dir, stage, output_path, reason=str(exc))
        return None
    return marker


async def _run_stage(
    *,
    cell_dir: Path,
    stage: str,
    output_path: Path,
    output_schema: Path | None,
    prompt: str,
    effort: str,
    args: argparse.Namespace,
    model: str | None = None,
) -> dict[str, Any]:
    selected_model = model or args.model
    max_retries = int(getattr(args, "max_transient_retries", 2))
    retry_backoff_seconds = float(getattr(args, "retry_backoff_seconds", 2.0))
    if max_retries < 0 or retry_backoff_seconds < 0:
        raise ValueError("Transient retry settings must be non-negative.")
    retry_attempts: list[dict[str, Any]] = []
    attempt = 0
    while True:
        command = codex_command(
            codex_bin=args.codex_bin,
            model=selected_model,
            effort=effort,
            cleanroom=args.cleanroom,
            output_path=output_path,
            output_schema=output_schema,
        )
        try:
            stdout, stderr, usage, event_audit = await _run_codex(
                command=command,
                prompt=prompt,
                base_codex_home=args.codex_home,
                timeout_seconds=args.timeout_seconds,
            )
            events_path = cell_dir / f"{stage}-events.jsonl"
            stderr_path = cell_dir / f"{stage}-stderr.log"
            _atomic_text(events_path, stdout)
            _atomic_text(stderr_path, stderr)
            if not output_path.is_file():
                raise ValueError("Codex completed without writing its final message.")
            _atomic_json(cell_dir / f"{stage}-usage.json", usage)
            marker = {
                "schema": "tmcp-campaign-stage-v0.1",
                "stage": stage,
                "prompt_sha256": _sha256_text(prompt),
                "output_schema_sha256": (
                    _sha256_file(output_schema) if output_schema is not None else None
                ),
                "output_sha256": _sha256_file(output_path),
                "events_sha256": _sha256_file(events_path),
                "stderr_sha256": _sha256_file(stderr_path),
                "event_audit": event_audit,
                "usage": usage,
            }
            _atomic_json(cell_dir / f"{stage}-complete.json", marker)
            return marker
        except CodexRunError as exc:
            _atomic_text(cell_dir / f"{stage}-events.jsonl", exc.stdout)
            _atomic_text(cell_dir / f"{stage}-stderr.log", exc.stderr)
            _invalidate_stage(cell_dir, stage, output_path, reason=str(exc))
            classification = transient_failure_classification(exc)
            if classification is None or attempt >= max_retries:
                raise RuntimeError(f"{stage} stage failed: {exc}") from exc
            backoff_seconds = retry_backoff_seconds * (2**attempt)
            retry_attempts.append(
                {
                    "attempt": attempt + 1,
                    "classification": classification,
                    "backoff_seconds": backoff_seconds,
                    "error": str(exc),
                }
            )
            _atomic_json(
                cell_dir / f"{stage}-retry-audit.json",
                {
                    "schema": "tmcp-campaign-stage-retry-audit-v0.1",
                    "stage": stage,
                    "model": selected_model,
                    "attempts": retry_attempts,
                },
            )
            attempt += 1
            await asyncio.sleep(backoff_seconds)
        except BaseException as exc:
            _invalidate_stage(cell_dir, stage, output_path, reason=str(exc))
            raise RuntimeError(f"{stage} stage failed: {exc}") from exc


def _validate_trace(
    trace: Any,
    *,
    cell: CampaignCell,
    row: dict[str, Any],
    plan: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if (
        not isinstance(trace, dict)
        or trace.get("schema") != "tmcp-skill-eval-trace-v0.1"
    ):
        raise ValueError("Resumed trace schema is invalid.")
    expected = {
        "trace_id": _stable_id(cell.cell_id, prefix="trace"),
        "experiment_id": plan["experiment"]["experiment_id"],
        "matrix_row_id": cell.matrix_row_id,
        "replicate_id": cell.replicate_id,
        "task_id": cell.task_id,
        "variant_id": cell.variant_id,
    }
    for field, value in expected.items():
        if trace.get(field) != value:
            raise ValueError(f"Resumed trace {field} does not match its campaign cell.")
    agent = trace.get("agent")
    if (
        not isinstance(agent, dict)
        or agent.get("name") != "codex-cli-blind-runner"
        or agent.get("model") != cell.runner_model
        or agent.get("configuration_id") != cell.configuration_id
    ):
        raise ValueError(
            "Resumed trace configuration does not match its campaign cell."
        )
    provenance = trace.get("provenance")
    if not isinstance(provenance, dict) or any(
        provenance.get(field) is not True
        for field in ("runner_blinded", "judge_blinded", "isolated_session")
    ):
        raise ValueError("Resumed trace controlled provenance is invalid.")
    if (
        provenance.get("prompt_context_sha256") != args.prompt_context_sha256
        or provenance.get("disabled_features") != list(DISABLED_CODEX_FEATURES)
        or any(
            not isinstance(provenance.get(field), dict)
            or provenance[field].get("passed") is not True
            for field in ("runner_event_audit", "judge_event_audit")
        )
    ):
        raise ValueError("Resumed trace isolation audit is invalid.")
    campaign = trace.get("campaign")
    if not isinstance(campaign, dict) or campaign.get("cell_id") != cell.cell_id:
        raise ValueError("Resumed trace campaign metadata is invalid.")
    usage = campaign.get("usage")
    if not isinstance(usage, dict) or any(
        not isinstance(usage.get(role), dict) or not usage[role]
        for role in ("runner", "judge")
    ):
        raise ValueError("Resumed trace usage metadata is invalid.")
    cell_dir = args.output_dir / "cells" / cell.cell_id
    runner_output = cell_dir / "runner.txt"
    judge_output = cell_dir / "judge.json"
    runner_stage = _load_completed_stage(cell_dir, "runner", runner_output)
    judge_stage = _load_completed_stage(cell_dir, "judge", judge_output)
    if runner_stage is None or judge_stage is None:
        raise ValueError("Resumed trace is missing a validated completed stage.")
    criteria = judge_criteria(row)
    judge_schema_path = cell_dir / "judge-output.schema.json"
    expected_judge_schema = judge_output_schema(criteria)
    if (
        not judge_schema_path.is_file()
        or _load_json(judge_schema_path) != expected_judge_schema
    ):
        raise ValueError("Resumed trace judge schema is invalid.")
    artifact = runner_output.read_text(encoding="utf-8").strip()
    runner_input = runner_prompt(row)
    judge_input = judge_prompt(
        row,
        artifact,
        first_principles=args.first_principles,
    )
    if runner_stage.get("prompt_sha256") != _sha256_text(runner_input):
        raise ValueError("Resumed trace runner prompt digest is invalid.")
    if judge_stage.get("prompt_sha256") != _sha256_text(judge_input) or judge_stage.get(
        "output_schema_sha256"
    ) != _sha256_file(judge_schema_path):
        raise ValueError("Resumed trace judge prompt or schema digest is invalid.")
    judgment = _validate_judgment(_load_json(judge_output), expected_criteria=criteria)
    expected_verdict = {
        "passed": judgment["passed"],
        "evidence": judgment["evidence"],
        "safety_regression": judgment["safety_regression"],
        "cost_regression": judgment["cost_regression"],
    }
    if trace.get("case_verdict") != expected_verdict:
        raise ValueError("Resumed trace verdict does not match the judge artifact.")
    if trace.get("human_labels") != [{"judge_rationale": judgment["rationale"]}]:
        raise ValueError("Resumed trace rationale does not match the judge artifact.")
    if trace.get("observations") != [
        {"kind": "assistant_message", "value": artifact or "[EMPTY ARTIFACT]"}
    ]:
        raise ValueError(
            "Resumed trace observation does not match the runner artifact."
        )
    expected_campaign = {
        "cell_id": cell.cell_id,
        "order": cell.order,
        "runner_model": cell.runner_model,
        "runner_effort": cell.runner_effort,
        "judge_model": getattr(args, "judge_model", args.model),
        "judge_effort": args.judge_effort,
        "runner_artifact": str(runner_output.relative_to(args.output_dir)),
        "judge_artifact": str(judge_output.relative_to(args.output_dir)),
        "runner_artifact_sha256": runner_stage["output_sha256"],
        "judge_artifact_sha256": judge_stage["output_sha256"],
        "usage": {
            "runner": runner_stage["usage"],
            "judge": judge_stage["usage"],
        },
    }
    if campaign != expected_campaign:
        raise ValueError(
            "Resumed trace campaign evidence does not match stage artifacts."
        )
    if (
        provenance.get("runner_event_audit") != runner_stage["event_audit"]
        or provenance.get("judge_event_audit") != judge_stage["event_audit"]
    ):
        raise ValueError("Resumed trace event audits do not match stage artifacts.")
    if (
        runner_stage["event_audit"]["thread_id"]
        == judge_stage["event_audit"]["thread_id"]
    ):
        raise ValueError("Runner and judge reused one Codex thread.")
    return trace


def _assert_empty_cleanroom(cleanroom: Path) -> None:
    entries = [path for path in cleanroom.rglob("*") if path.name != ".DS_Store"]
    if entries:
        raise ValueError(f"Cleanroom contains unexpected path: {entries[0]}")


async def execute_cell(
    cell: CampaignCell,
    *,
    row: dict[str, Any],
    plan: dict[str, Any],
    args: argparse.Namespace,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    cell_dir = args.output_dir / "cells" / cell.cell_id
    trace_path = cell_dir / "trace.json"
    if trace_path.is_file():
        trace = _validate_trace(
            _load_json(trace_path), cell=cell, row=row, plan=plan, args=args
        )
        print(
            f"[{cell.order:02d}] resumed {cell.cell_id} "
            f"passed={trace['case_verdict']['passed']}",
            flush=True,
        )
        return trace
    async with semaphore:
        cell_dir.mkdir(parents=True, exist_ok=True)
        _assert_empty_cleanroom(args.cleanroom)
        runner_output = cell_dir / "runner.txt"
        runner_input = runner_prompt(row)
        runner_stage = _load_completed_stage(cell_dir, "runner", runner_output)
        if runner_stage is not None and runner_stage.get(
            "prompt_sha256"
        ) != _sha256_text(runner_input):
            _invalidate_stage(
                cell_dir,
                "runner",
                runner_output,
                reason="runner prompt digest does not match",
            )
            runner_stage = None
        if runner_stage is None:
            runner_stage = await _run_stage(
                cell_dir=cell_dir,
                stage="runner",
                output_path=runner_output,
                output_schema=None,
                prompt=runner_input,
                effort=cell.runner_effort,
                args=args,
                model=cell.runner_model,
            )
        _assert_empty_cleanroom(args.cleanroom)
        artifact = runner_output.read_text(encoding="utf-8").strip()
        criteria = judge_criteria(row)
        judge_schema_path = cell_dir / "judge-output.schema.json"
        expected_judge_schema = judge_output_schema(criteria)
        if (
            judge_schema_path.is_file()
            and _load_json(judge_schema_path) != expected_judge_schema
        ):
            raise ValueError("Existing cell judge schema does not match its criteria.")
        _atomic_json(judge_schema_path, expected_judge_schema)
        judge_output = cell_dir / "judge.json"
        judge_input = judge_prompt(
            row,
            artifact,
            first_principles=args.first_principles,
        )
        judge_stage = _load_completed_stage(cell_dir, "judge", judge_output)
        if judge_stage is not None and (
            judge_stage.get("prompt_sha256") != _sha256_text(judge_input)
            or judge_stage.get("output_schema_sha256")
            != _sha256_file(judge_schema_path)
        ):
            _invalidate_stage(
                cell_dir,
                "judge",
                judge_output,
                reason="judge prompt or schema digest does not match",
            )
            judge_stage = None
        judgment: dict[str, Any] | None = None
        if judge_stage is not None:
            try:
                judgment = _validate_judgment(
                    _load_json(judge_output), expected_criteria=criteria
                )
            except (ValueError, json.JSONDecodeError) as exc:
                _invalidate_stage(
                    cell_dir, "judge", judge_output, reason=f"invalid judgment: {exc}"
                )
                judge_stage = None
        if judge_stage is None:
            judge_stage = await _run_stage(
                cell_dir=cell_dir,
                stage="judge",
                output_path=judge_output,
                output_schema=judge_schema_path,
                prompt=judge_input,
                effort=args.judge_effort,
                args=args,
                model=getattr(args, "judge_model", args.model),
            )
            try:
                judgment = _validate_judgment(
                    _load_json(judge_output), expected_criteria=criteria
                )
            except (ValueError, json.JSONDecodeError) as exc:
                _invalidate_stage(
                    cell_dir, "judge", judge_output, reason=f"invalid judgment: {exc}"
                )
                raise
        assert judgment is not None
        _assert_empty_cleanroom(args.cleanroom)
        trace = {
            "schema": "tmcp-skill-eval-trace-v0.1",
            "trace_id": _stable_id(cell.cell_id, prefix="trace"),
            "experiment_id": plan["experiment"]["experiment_id"],
            "matrix_row_id": cell.matrix_row_id,
            "replicate_id": cell.replicate_id,
            "task_id": cell.task_id,
            "variant_id": cell.variant_id,
            "agent": {
                "name": "codex-cli-blind-runner",
                "model": cell.runner_model,
                "configuration_id": cell.configuration_id,
            },
            "provenance": {
                "runner_blinded": True,
                "judge_blinded": True,
                "isolated_session": True,
                "prompt_context_sha256": args.prompt_context_sha256,
                "disabled_features": list(DISABLED_CODEX_FEATURES),
                "runner_event_audit": runner_stage["event_audit"],
                "judge_event_audit": judge_stage["event_audit"],
            },
            "observations": [
                {
                    "kind": "assistant_message",
                    "value": artifact or "[EMPTY ARTIFACT]",
                }
            ],
            "human_labels": [{"judge_rationale": judgment["rationale"]}],
            "case_verdict": {
                "passed": judgment["passed"],
                "evidence": judgment["evidence"],
                "safety_regression": judgment["safety_regression"],
                "cost_regression": judgment["cost_regression"],
            },
            "campaign": {
                "cell_id": cell.cell_id,
                "order": cell.order,
                "runner_model": cell.runner_model,
                "runner_effort": cell.runner_effort,
                "judge_model": getattr(args, "judge_model", args.model),
                "judge_effort": args.judge_effort,
                "runner_artifact": str(runner_output.relative_to(args.output_dir)),
                "judge_artifact": str(judge_output.relative_to(args.output_dir)),
                "runner_artifact_sha256": runner_stage["output_sha256"],
                "judge_artifact_sha256": judge_stage["output_sha256"],
                "usage": {
                    "runner": runner_stage["usage"],
                    "judge": judge_stage["usage"],
                },
            },
        }
        _atomic_json(trace_path, trace)
        print(
            f"[{cell.order:02d}] completed {cell.cell_id} passed={judgment['passed']}",
            flush=True,
        )
        return trace
