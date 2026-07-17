#!/usr/bin/env python3
"""Run a condition-blind cost rejudge over fixed skill-evaluation artifacts."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tmcp_skill_eval_cost_rejudge_runtime import (
    _execute_cell,
    _harness_digests,
    _message_text,
    _prompt_input_preflight,
    run,
)  # noqa: E402
from scripts.tmcp_skill_eval_cost_rejudge_source import (
    COST_REJUDGMENTS_SCHEMA,
    CostRejudgeCell,
    SourceTrace,
    _aggregate_usage,
    _canonical_json_digest,
    _load_source_traces,
    _source_summary,
    _unexpected_output_entries,
    _validate_args,
    build_cost_rejudge_cells,
)  # noqa: E402


__all__ = (
    "COST_REJUDGMENTS_SCHEMA",
    "CostRejudgeCell",
    "SourceTrace",
    "_aggregate_usage",
    "_canonical_json_digest",
    "_execute_cell",
    "_harness_digests",
    "_load_source_traces",
    "_message_text",
    "_prompt_input_preflight",
    "_source_summary",
    "_unexpected_output_entries",
    "_validate_args",
    "build_cost_rejudge_cells",
    "main",
    "run",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--source-runs", type=Path, required=True)
    parser.add_argument("--cost-bar-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--cleanroom", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--judge-effort", default="high")
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--max-cells", type=int)
    parser.add_argument("--expected-trace-count", type=int, default=72)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def _main(args: argparse.Namespace) -> int:
    return await run(args)


def main() -> int:
    return asyncio.run(_main(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
