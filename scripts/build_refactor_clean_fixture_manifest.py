#!/usr/bin/env python3
"""Project reviewed refactor-clean fixtures into a study-input manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}.")
    if value.get("review_status") != "approved_for_preregistration":
        raise ValueError(f"Fixture is not approved for preregistration: {path}")
    target = value.get("target_source")
    task = value.get("fixture")
    bar = value.get("outcome_bar")
    if not isinstance(target, dict) or not isinstance(task, dict) or not isinstance(bar, dict):
        raise ValueError(f"Fixture contract is incomplete: {path}")
    fixture_id = str(task.get("id") or "")
    fixture_family = str(task.get("fixture_family") or "")
    prompt = str(task.get("runner_prompt") or "")
    expected_observables = bar.get("expected_observables")
    failure_smells = bar.get("failure_smells")
    if not fixture_id or not fixture_family or not prompt:
        raise ValueError(f"Fixture identity or prompt is missing: {path}")
    if not isinstance(expected_observables, list) or not isinstance(failure_smells, list):
        raise ValueError(f"Fixture bar is incomplete: {path}")
    return {
        "id": fixture_id,
        "fixture_family": fixture_family,
        "prompt": prompt,
        "expected_observables": expected_observables,
        "failure_smells": failure_smells,
        "source_fixture": str(path),
        "source_sha256": str(target.get("sha256") or ""),
        "review_record": str(value.get("review_record") or ""),
    }


def build_manifest(fixtures_dir: Path) -> list[dict[str, Any]]:
    fixtures = [_load_fixture(path) for path in sorted(fixtures_dir.glob("*.json"))]
    if len(fixtures) < 6:
        raise ValueError("At least six approved fixtures are required.")
    ids = [str(item["id"]) for item in fixtures]
    families = [str(item["fixture_family"]) for item in fixtures]
    if len(set(ids)) != len(ids):
        raise ValueError("Fixture IDs must be unique.")
    if len(set(families)) < 3:
        raise ValueError("At least three fixture families are required.")
    return fixtures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.fixtures_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"fixture_count": len(manifest), "fixture_families": sorted({item["fixture_family"] for item in manifest})}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
