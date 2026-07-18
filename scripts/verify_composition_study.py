#!/usr/bin/env python3
"""Verify a preregistered source-bundle composition study without remote calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_composition_study_plan import (  # noqa: E402
    _load_object,
    build_plan,
    validate_cost_rejudge_policy,
    verify_study_input_digests,
)
from tmcp_runtime.api.evaluation import validate_evaluation_plan  # noqa: E402


VERIFICATION_SCHEMA = "tmcp-composition-study-verification-v0.1"


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_plan(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return value


def _live_source_report(definition: dict[str, Any]) -> dict[str, Any]:
    selected_sources = definition.get("selected_sources")
    if not isinstance(selected_sources, list):
        raise ValueError("study.json selected_sources must be a list.")
    entries: list[dict[str, str]] = []
    for source in selected_sources:
        if not isinstance(source, dict):
            raise ValueError("study.json selected_sources entries must be objects.")
        path_text = source.get("path")
        expected = source.get("sha256")
        if not isinstance(path_text, str) or not path_text:
            raise ValueError("study.json selected source path must be non-empty.")
        if not isinstance(expected, str) or not expected.startswith("sha256:"):
            raise ValueError("study.json selected source sha256 must be a digest.")
        path = Path(path_text)
        if not path.is_file():
            entries.append(
                {"path": path_text, "expected_sha256": expected, "status": "missing"}
            )
            continue
        actual = _sha256_file(path)
        entries.append(
            {
                "path": path_text,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "status": "matched" if actual == expected else "drifted",
            }
        )
    status = (
        "matched" if all(entry["status"] == "matched" for entry in entries) else "drifted"
    )
    return {"checked": True, "status": status, "sources": entries}


def verify_study(
    study_dir: Path,
    *,
    plan_path: Path | None = None,
    check_live_sources: bool = False,
) -> dict[str, Any]:
    """Verify immutable study inputs and an optional live-source provenance check."""

    resolved_study_dir = study_dir.resolve()
    inputs = resolved_study_dir / "inputs"
    definition = _load_object(inputs / "study.json")
    input_digests = verify_study_input_digests(resolved_study_dir, definition)
    generated_plan = validate_evaluation_plan(build_plan(resolved_study_dir))
    experiment = generated_plan["experiment"]
    cost_rejudge = validate_cost_rejudge_policy(
        resolved_study_dir, experiment["cost_rejudge_policy"], generated_plan
    )
    resolved_plan_path = (
        plan_path.resolve()
        if plan_path is not None
        else resolved_study_dir / "generated" / "tmcp-composition-study-plan.json"
    )
    checked_in_plan = _load_plan(resolved_plan_path)
    if checked_in_plan != generated_plan:
        raise ValueError("generated plan does not match the byte-pinned study inputs.")
    live_sources = (
        _live_source_report(definition)
        if check_live_sources
        else {"checked": False, "status": "not_checked", "sources": []}
    )
    return {
        "schema": VERIFICATION_SCHEMA,
        "study_dir": str(resolved_study_dir),
        "plan_path": str(resolved_plan_path),
        "experiment_id": experiment["experiment_id"],
        "static": {
            "input_digests": input_digests,
            "plan_matches_generated": True,
            "plan_valid": True,
            "fixture_count": len(
                {str(row["task_id"]) for row in generated_plan["task_matrix"]}
            ),
            "matrix_row_count": len(generated_plan["task_matrix"]),
            "claim_boundary": experiment["study_scope"]["claim_boundary"],
            "primary_harness": experiment["source_study_binding"][
                "primary_harness"
            ],
            "cost_rejudge": cost_rejudge,
        },
        "live_sources": live_sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--check-live-sources", action="store_true")
    parser.add_argument("--require-live-sources", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.require_live_sources:
        args.check_live_sources = True
    try:
        report = verify_study(
            args.study_dir,
            plan_path=args.plan,
            check_live_sources=args.check_live_sources,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        rendered_error = json.dumps(
            {"schema": VERIFICATION_SCHEMA, "ok": False, "error": str(error)}
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered_error + "\n", encoding="utf-8")
        print(rendered_error)
        return 1
    if args.require_live_sources and report["live_sources"]["status"] != "matched":
        rendered = json.dumps({**report, "ok": False}, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 1
    rendered = json.dumps({**report, "ok": True}, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
