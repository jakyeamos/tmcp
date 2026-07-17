#!/usr/bin/env python3
"""Score real host-supplied TMCP 0.6 composition benchmark observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from tmcp_runtime.domain.composition_benchmarks import (  # noqa: E402
    score_composition_benchmark,
)


MAX_INPUT_BYTES = 8 * 1024 * 1024
OBSERVATION_SCHEMA = "tmcp-composition-benchmark-observations-v0.1"


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{label} exceeds {MAX_INPUT_BYTES} bytes.")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return payload


def _read_observations(path: Path) -> tuple[dict[str, Any], str]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"observations exceeds {MAX_INPUT_BYTES} bytes.")
    content = path.read_bytes()
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("observations must contain a JSON object.")
    return payload, hashlib.sha256(content).hexdigest()


def run_benchmark(
    *,
    routing_golden_path: Path,
    behavioral_fixtures_path: Path,
    observations_path: Path,
) -> dict[str, Any]:
    routing = _read_object(routing_golden_path, label="routing golden")
    behavioral = _read_object(
        behavioral_fixtures_path,
        label="behavioral fixtures",
    )
    observations, observations_sha256 = _read_observations(observations_path)
    if observations.get("schema") != OBSERVATION_SCHEMA:
        raise ValueError(f"observations.schema must be {OBSERVATION_SCHEMA}.")
    for payload, key, label in (
        (routing, "cases", "routing golden"),
        (behavioral, "fixtures", "behavioral fixtures"),
        (observations, "routing_results", "routing observations"),
        (observations, "behavioral_results", "behavioral observations"),
    ):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"{label}.{key} must be an array.")
    summary = score_composition_benchmark(
        golden_cases=routing["cases"],
        fixture_definitions=behavioral["fixtures"],
        routing_results=observations["routing_results"],
        behavioral_results=observations["behavioral_results"],
    )
    return {**summary, "observations_sha256": observations_sha256}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Score complete observed TMCP composition runs. This command never "
            "generates or substitutes quality observations."
        )
    )
    parser.add_argument("observations", type=Path)
    parser.add_argument(
        "--routing-golden",
        type=Path,
        default=PLUGIN_ROOT
        / "tests"
        / "fixtures"
        / "composition_routing_golden_v0_6.json",
    )
    parser.add_argument(
        "--behavioral-fixtures",
        type=Path,
        default=PLUGIN_ROOT
        / "tests"
        / "fixtures"
        / "composition_behavioral_fixtures_v0_6.json",
    )
    args = parser.parse_args()
    try:
        summary = run_benchmark(
            routing_golden_path=args.routing_golden,
            behavioral_fixtures_path=args.behavioral_fixtures,
            observations_path=args.observations,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"ok": True, **summary}, indent=2, sort_keys=True))
    return 0 if summary["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
