#!/usr/bin/env python3
"""Run a resumable blind Codex campaign for one TMCP skill-pattern contrast."""

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
from scripts.tmcp_skill_eval_campaign_protocol import (  # noqa: E402
    CAMPAIGN_PROTOCOL,
    DISABLED_CODEX_FEATURES,
    JUDGE_SCHEMA_VERSION,
    _atomic_json,
    _load_json,
    _sha256_file,
    _sha256_text,
    build_cells,
    judge_output_schema,
    judge_prompt,
    runner_prompt,
    selected_rows,
)
from scripts.tmcp_skill_eval_campaign_runtime import (  # noqa: E402
    _assert_empty_cleanroom,
    _validate_trace,
    execute_cell,
)


def _add_usage(
    buckets: dict[str, dict[str, int]], key: str, usage: dict[str, Any]
) -> None:
    bucket = buckets.setdefault(key, {"traces": 0})
    bucket["traces"] += 1
    for metric, value in usage.items():
        if isinstance(value, int) and not isinstance(value, bool):
            bucket[str(metric)] = bucket.get(str(metric), 0) + value


def _aggregate_usage(traces: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, dict[str, int]] = {"runner": {}, "judge": {}}
    by_variant: dict[str, dict[str, dict[str, int]]] = {
        "runner": {},
        "judge": {},
    }
    by_configuration: dict[str, dict[str, dict[str, int]]] = {
        "runner": {},
        "judge": {},
    }
    for trace in traces:
        usage_by_role = trace.get("campaign", {}).get("usage", {})
        variant_id = str(trace.get("variant_id") or "unspecified")
        agent = trace.get("agent")
        configuration_id = (
            str(agent.get("configuration_id") or "unspecified")
            if isinstance(agent, dict)
            else "unspecified"
        )
        for role in totals:
            usage = usage_by_role.get(role, {})
            if not isinstance(usage, dict):
                continue
            for key, value in usage.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    totals[role][str(key)] = totals[role].get(str(key), 0) + value
            _add_usage(by_variant[role], variant_id, usage)
            _add_usage(by_configuration[role], configuration_id, usage)
    return {
        "totals": totals,
        "by_variant": by_variant,
        "by_configuration": by_configuration,
    }


def _validate_campaign_args(args: argparse.Namespace) -> None:
    if args.concurrency < 1:
        raise ValueError("concurrency must be at least 1.")
    if args.timeout_seconds < 1:
        raise ValueError("timeout-seconds must be at least 1.")
    if args.max_cells is not None and args.max_cells < 1:
        raise ValueError("max-cells must be at least 1 when supplied.")
    if args.repetitions != 2:
        raise ValueError("This promotion campaign requires exactly two repetitions.")
    if args.expected_fixtures != 6:
        raise ValueError("This promotion campaign requires exactly six fixtures.")
    if len(args.runner_effort) != 3:
        raise ValueError(
            "This promotion campaign requires exactly three configurations."
        )
    if not args.first_principles.strip():
        raise ValueError("first-principles must be non-empty.")
    if args.cleanroom.resolve() == args.output_dir.resolve():
        raise ValueError("cleanroom and output-dir must be distinct.")


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
    probe = "TMCP_EVAL_CLEANROOM_PROBE"
    auth_path = args.codex_home / "auth.json"
    if not auth_path.is_file():
        raise ValueError(f"Codex auth file is missing: {auth_path}")
    with tempfile.TemporaryDirectory(prefix="tmcp-codex-preflight-") as temporary:
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
    matched_markers = [marker for marker in forbidden_markers if marker in rendered]
    if matched_markers:
        raise ValueError(
            "Prompt-input preflight contains injected instructions: "
            + ", ".join(matched_markers)
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--cleanroom", type=Path, required=True)
    parser.add_argument("--first-principles", required=True)
    parser.add_argument("--pattern-id", required=True)
    parser.add_argument("--intervention-target", required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--runner-effort", action="append", required=True)
    parser.add_argument("--judge-effort", default="high")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--expected-fixtures", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--max-cells", type=int)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _harness_digests() -> dict[str, str]:
    paths = (
        Path(__file__),
        Path(campaign_protocol.__file__),
        Path(campaign_runtime.__file__),
    )
    return {path.name: _sha256_file(path) for path in paths}


async def _main(args: argparse.Namespace) -> int:
    _validate_campaign_args(args)
    plan = _load_json(args.plan)
    codex_version = subprocess.run(
        [args.codex_bin, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    cells = build_cells(
        plan,
        pattern_id=args.pattern_id,
        intervention_target=args.intervention_target,
        model=args.model,
        runner_efforts=args.runner_effort,
        repetitions=args.repetitions,
        expected_fixtures=args.expected_fixtures,
        seed=args.seed,
        codex_version=codex_version,
    )
    if len(cells) != 72:
        raise ValueError(
            f"Promotion campaign must contain 72 cells, found {len(cells)}."
        )
    if args.max_cells is not None and args.max_cells > len(cells):
        raise ValueError("max-cells cannot exceed the planned campaign size.")
    rows = {
        str(row["matrix_row_id"]): row
        for row in selected_rows(
            plan,
            pattern_id=args.pattern_id,
            intervention_target=args.intervention_target,
        )
    }
    preflight: dict[str, Any]
    if args.dry_run:
        preflight = {
            "audit": {
                "passed": False,
                "status": "not_run_in_dry_run",
                "prompt_context_sha256": "not-run",
            }
        }
    else:
        args.cleanroom.mkdir(parents=True, exist_ok=True)
        _assert_empty_cleanroom(args.cleanroom)
        preflight = _prompt_input_preflight(args)
    args.prompt_context_sha256 = preflight["audit"]["prompt_context_sha256"]
    example_schema = judge_output_schema(
        ["O1: <OBSERVABLE>", "S1 (failure smell must be absent): <SMELL>"]
    )
    schema_digest = _sha256_text(
        json.dumps(example_schema, sort_keys=True, separators=(",", ":"))
    )
    runner_protocol_digest = _sha256_text(
        runner_prompt({"skill_attachment": "<ATTACHMENT>", "prompt": "<TASK>"})
    )
    judge_protocol_digest = _sha256_text(
        judge_prompt(
            {
                "prompt": "<TASK>",
                "expected_observables": ["<OBSERVABLE>"],
                "failure_smells": ["<SMELL>"],
            },
            "<ARTIFACT>",
            first_principles="<FIRST_PRINCIPLES>",
        )
    )
    harness_files = _harness_digests()
    manifest = {
        "schema": CAMPAIGN_PROTOCOL,
        "experiment_id": plan["experiment"]["experiment_id"],
        "plan_path": str(args.plan),
        "plan_sha256": _sha256_file(args.plan),
        "harness_sha256": _sha256_text(
            json.dumps(harness_files, sort_keys=True, separators=(",", ":"))
        ),
        "harness_files": harness_files,
        "first_principles_sha256": _sha256_text(args.first_principles),
        "judge_schema_version": JUDGE_SCHEMA_VERSION,
        "judge_schema_sha256": schema_digest,
        "runner_protocol_sha256": runner_protocol_digest,
        "judge_protocol_sha256": judge_protocol_digest,
        "pattern_id": args.pattern_id,
        "intervention_target": args.intervention_target,
        "model": args.model,
        "runner_efforts": args.runner_effort,
        "judge_effort": args.judge_effort,
        "codex_version": codex_version,
        "seed": args.seed,
        "repetitions": args.repetitions,
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
        },
    }
    if args.dry_run:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    manifest_path = args.output_dir / "campaign-manifest.json"
    if args.output_dir.is_dir():
        existing_entries = [
            path for path in args.output_dir.iterdir() if path.name != ".DS_Store"
        ]
        if existing_entries and not manifest_path.is_file():
            raise ValueError(
                "Campaign output directory is non-empty but has no campaign manifest."
            )
        if manifest_path.is_file() and _load_json(manifest_path) != manifest:
            raise ValueError("Existing campaign manifest does not match this run.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(manifest_path, manifest)
    _atomic_json(args.output_dir / "judge-output.schema.example.json", example_schema)
    _atomic_json(args.output_dir / "prompt-input-preflight.json", preflight)
    selected_cells = cells[: args.max_cells] if args.max_cells else cells
    preexisting_cells = {
        cell.cell_id
        for cell in selected_cells
        if (args.output_dir / "cells" / cell.cell_id / "trace.json").is_file()
    }
    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = [
        execute_cell(
            cell,
            row=rows[cell.matrix_row_id],
            plan=plan,
            args=args,
            semaphore=semaphore,
        )
        for cell in selected_cells
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    errors = [
        {
            "cell_id": cell.cell_id,
            "order": cell.order,
            "error": str(result),
        }
        for cell, result in zip(selected_cells, results, strict=True)
        if isinstance(result, BaseException)
    ]
    traces = [result for result in results if isinstance(result, dict)]
    if errors:
        _atomic_json(args.output_dir / "campaign-errors.json", errors)
        for error in errors:
            print(
                f"[{error['order']:02d}] failed {error['cell_id']}: {error['error']}",
                flush=True,
            )
    else:
        (args.output_dir / "campaign-errors.json").unlink(missing_ok=True)
    expected_cell_ids = {cell.cell_id for cell in cells}
    all_trace_paths = list((args.output_dir / "cells").glob("*/trace.json"))
    orphan_paths = [
        path for path in all_trace_paths if path.parent.name not in expected_cell_ids
    ]
    if orphan_paths:
        raise ValueError(f"Orphan campaign trace detected: {orphan_paths[0]}")
    all_traces = [
        _validate_trace(
            _load_json(args.output_dir / "cells" / cell.cell_id / "trace.json"),
            cell=cell,
            row=rows[cell.matrix_row_id],
            plan=plan,
            args=args,
        )
        for cell in cells
        if (args.output_dir / "cells" / cell.cell_id / "trace.json").is_file()
    ]
    thread_ids = [
        str(trace["provenance"][f"{role}_event_audit"]["thread_id"])
        for trace in all_traces
        for role in ("runner", "judge")
    ]
    if len(thread_ids) != len(set(thread_ids)):
        raise ValueError("Campaign contains a reused Codex thread ID.")
    _atomic_json(args.output_dir / "traces.json", all_traces)
    newly_completed = sum(
        1
        for cell, result in zip(selected_cells, results, strict=True)
        if isinstance(result, dict) and cell.cell_id not in preexisting_cells
    )
    summary = {
        "planned_cells": len(cells),
        "selected_cells": len(selected_cells),
        "completed_cells": len(all_traces),
        "completed_this_run": newly_completed,
        "resumed_this_run": len(traces) - newly_completed,
        "errors": len(errors),
        "passed": sum(1 for trace in all_traces if trace["case_verdict"]["passed"]),
        "unique_thread_ids": len(thread_ids),
        "expected_thread_ids_at_completion": len(cells) * 2,
        "usage": _aggregate_usage(all_traces),
    }
    _atomic_json(args.output_dir / "campaign-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if errors else 0


def main() -> int:
    args = _parser().parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
