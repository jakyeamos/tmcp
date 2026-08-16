#!/usr/bin/env python3
"""Run structural validation over a fixture artifact batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

try:
    from scripts.validate_skill_fixture_artifact import validate_fixture_artifact
except ModuleNotFoundError:  # Direct execution places scripts/ before the project root.
    from validate_skill_fixture_artifact import validate_fixture_artifact


SCHEMA = "tmcp-skill-fixture-artifact-batch-validation-v0.1"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise SystemExit("spec must contain a JSON object")

    results: list[dict[str, object]] = []
    for artifact_path in args.artifacts:
        artifact_bytes = artifact_path.read_bytes()
        artifact = json.loads(artifact_bytes)
        if not isinstance(artifact, dict):
            raise SystemExit(f"artifact must contain a JSON object: {artifact_path}")
        result = validate_fixture_artifact(artifact, spec)
        result["artifact"] = {
            "path": str(artifact_path),
            "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        }
        results.append(result)

    passed_count = sum(bool(result["passed"]) for result in results)
    report = {
        "schema": SCHEMA,
        "spec": str(args.spec),
        "artifact_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "passed": passed_count == len(results),
        "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
