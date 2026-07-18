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
from tmcp_runtime.domain.composition_benchmark_assembly import (  # noqa: E402
    MAX_BENCHMARK_ARTIFACT_BYTES,
    assemble_benchmark_observations,
)
from tmcp_runtime.domain.composition_benchmark_evidence import (  # noqa: E402
    validate_release_benchmark_evidence_admissibility,
)
from scripts.schema_contract_support import (  # noqa: E402
    SchemaAssertionError,
    assert_matches_schema,
)


MAX_INPUT_BYTES = MAX_BENCHMARK_ARTIFACT_BYTES
OBSERVATION_SCHEMA = "tmcp-composition-benchmark-observations-v0.1"
SCHEMAS = PLUGIN_ROOT / "schemas"


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
    run_plan_path: Path | None = None,
    semantic_proposals_path: Path | None = None,
    control_plan_path: Path | None = None,
    host_results_path: Path | None = None,
    evaluator_artifacts_path: Path | None = None,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    """Score an assembled run, or an explicit synthetic unit-test fixture."""

    routing = _read_object(routing_golden_path, label="routing golden")
    behavioral = _read_object(
        behavioral_fixtures_path,
        label="behavioral fixtures",
    )
    observations, observations_sha256 = _read_observations(observations_path)
    if observations.get("schema") != OBSERVATION_SCHEMA:
        raise ValueError(f"observations.schema must be {OBSERVATION_SCHEMA}.")
    assert_matches_schema(
        observations,
        SCHEMAS / "tmcp-composition-benchmark-observations-v0.1.schema.json",
    )
    artifact_paths = {
        "run_plan": run_plan_path,
        "semantic_proposals": semantic_proposals_path,
        "control_plan": control_plan_path,
        "host_results": host_results_path,
        "evaluator_artifacts": evaluator_artifacts_path,
    }
    if not allow_synthetic:
        missing = [name for name, path in artifact_paths.items() if path is None]
        if missing:
            raise ValueError(
                f"Compiler-bound benchmark scoring requires {', '.join(missing)}."
            )
        run_plan = _read_object(run_plan_path, label="benchmark run plan")
        semantic_proposals = _read_object(
            semantic_proposals_path,
            label="semantic proposal bundle",
        )
        control_plan = _read_object(control_plan_path, label="benchmark control plan")
        host_results = _read_object(host_results_path, label="benchmark host results")
        evaluator_artifacts = _read_object(
            evaluator_artifacts_path,
            label="benchmark evaluator artifacts",
        )
        for payload, schema_name in (
            (run_plan, "tmcp-composition-benchmark-run-plan-v0.1.schema.json"),
            (
                semantic_proposals,
                "tmcp-composition-benchmark-semantic-proposals-v0.1.schema.json",
            ),
            (control_plan, "tmcp-composition-benchmark-control-plan-v0.1.schema.json"),
            (host_results, "tmcp-composition-benchmark-host-results-v0.1.schema.json"),
            (
                evaluator_artifacts,
                "tmcp-composition-benchmark-evaluator-artifacts-v0.1.schema.json",
            ),
        ):
            assert_matches_schema(payload, SCHEMAS / schema_name)
        validate_release_benchmark_evidence_admissibility(
            host_results=host_results,
            evaluator_artifacts=evaluator_artifacts,
        )
        assembled = assemble_benchmark_observations(
            run_plan=run_plan,
            semantic_proposals=semantic_proposals,
            control_plan=control_plan,
            routing_golden=routing,
            behavioral_fixtures=behavioral,
            host_results=host_results,
            evaluator_artifacts=evaluator_artifacts,
        )
        if observations != assembled:
            raise ValueError(
                "observations do not exactly match compiler-bound host/evaluator assembly."
            )
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
    parser.add_argument("--run-plan", type=Path)
    parser.add_argument("--semantic-proposals", type=Path)
    parser.add_argument("--control-plan", type=Path)
    parser.add_argument("--host-results", type=Path)
    parser.add_argument("--evaluator-artifacts", type=Path)
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
            run_plan_path=args.run_plan,
            semantic_proposals_path=args.semantic_proposals,
            control_plan_path=args.control_plan,
            host_results_path=args.host_results,
            evaluator_artifacts_path=args.evaluator_artifacts,
        )
    except (OSError, SchemaAssertionError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"ok": True, **summary}, indent=2, sort_keys=True))
    return 0 if summary["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
