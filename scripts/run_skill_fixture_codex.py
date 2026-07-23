#!/usr/bin/env python3
"""Run one blind skill-fixture prompt through Codex without shell interpolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Sequence


SESSION_PATTERN = re.compile(r"session(?: id)?[:=]\s*([A-Za-z0-9._:-]+)", re.IGNORECASE)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--output-last-message", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "max"),
        default="low",
    )
    parser.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write"),
        default="read-only",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    prompt = args.prompt_file.read_text(encoding="utf-8")
    command = [
        args.codex,
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "-s",
        args.sandbox,
        "-m",
        args.model,
        "-c",
        f'model_reasoning_effort="{args.reasoning_effort}"',
        "-o",
        str(args.output_last_message),
        "-",
    ]
    completed = subprocess.run(
        command,
        cwd=args.cwd,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
    )
    combined_output = f"{completed.stdout}{completed.stderr}".encode("utf-8")
    session_match = SESSION_PATTERN.search(completed.stdout + completed.stderr)
    report = {
        "schema": "tmcp-skill-fixture-codex-run-v0.1",
        "prompt_file": str(args.prompt_file),
        "prompt_sha256": _sha256_bytes(prompt.encode("utf-8")),
        "prompt_bytes": len(prompt.encode("utf-8")),
        "output_last_message": str(args.output_last_message),
        "cwd": str(args.cwd),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "sandbox": args.sandbox,
        "shell_interpolation": False,
        "session_id": session_match.group(1) if session_match else None,
        "exit_code": completed.returncode,
        "combined_output_sha256": _sha256_bytes(combined_output),
        "stderr_tail": completed.stderr[-2000:],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
