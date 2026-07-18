#!/usr/bin/env python3
"""Verify a baseline receipt is attached to the exact causal control bundle."""

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

from scripts.generate_composition_baseline_plan import build_baseline_plan  # noqa: E402
from scripts.tmcp_skill_eval_campaign_planning import validate_baseline_receipt  # noqa: E402
from tmcp_runtime.api.evaluation import validate_evaluation_plan  # noqa: E402


VERIFICATION_SCHEMA = "tmcp-skill-eval-baseline-bundle-verification-v0.1"
def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def _load_list(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Expected a JSON object list in {path}.")
    return value


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_baseline_bundle(
    causal_plan: dict[str, Any],
    baseline_plan: dict[str, Any],
    baseline_receipt: dict[str, Any] | None,
    *,
    baseline_plan_path: Path,
    manifest_path: Path | None,
    traces_path: Path | None,
    report_path: Path | None,
    receipt_path: Path | None,
) -> dict[str, Any]:
    """Return a no-call verification report for a completed baseline bundle."""

    gaps: list[str] = []
    try:
        validate_evaluation_plan(causal_plan)
    except ValueError:
        gaps.append("causal_plan_invalid")
    try:
        validate_evaluation_plan(baseline_plan)
    except ValueError:
        gaps.append("baseline_plan_invalid")
    try:
        if build_baseline_plan(causal_plan) != baseline_plan:
            gaps.append("baseline_plan_not_derived_from_causal_plan")
    except ValueError:
        gaps.append("baseline_plan_derivation_invalid")

    receipt_digest = _sha256_file(receipt_path) if receipt_path is not None else None
    gaps.extend(
        validate_baseline_receipt(
            causal_plan,
            baseline_receipt=baseline_receipt,
            baseline_receipt_digest=receipt_digest,
        )
    )

    artifact_paths = {
        "plan_sha256": baseline_plan_path,
        "manifest_sha256": manifest_path,
        "traces_sha256": traces_path,
        "report_sha256": report_path,
    }
    evidence = baseline_receipt.get("evidence") if isinstance(baseline_receipt, dict) else None
    if not isinstance(evidence, dict):
        gaps.append("baseline_evidence_digests_missing")
    else:
        for field, path in artifact_paths.items():
            if path is None or not path.is_file():
                gaps.append(f"{field}_artifact_missing")
                continue
            if evidence.get(field) != _sha256_file(path):
                gaps.append(f"{field}_artifact_digest_mismatch")

    manifest = _load_object(manifest_path) if manifest_path is not None and manifest_path.is_file() else None
    if manifest is None:
        gaps.append("baseline_manifest_missing")
    else:
        if manifest.get("plan_sha256") != _sha256_file(baseline_plan_path):
            gaps.append("baseline_manifest_plan_digest_mismatch")
        if manifest.get("experiment_id") != baseline_plan.get("experiment", {}).get("experiment_id"):
            gaps.append("baseline_manifest_experiment_mismatch")
        if manifest.get("design") != "baseline_reliability":
            gaps.append("baseline_manifest_design_mismatch")
        if manifest.get("cell_count") != 36:
            gaps.append("baseline_manifest_cell_count_mismatch")

    traces = _load_list(traces_path) if traces_path is not None and traces_path.is_file() else None
    if traces is None:
        gaps.append("baseline_traces_missing")
    elif len(traces) != 36:
        gaps.append("baseline_traces_cell_count_mismatch")
    if report_path is None or not report_path.is_file():
        gaps.append("baseline_report_missing")

    return {
        "schema": VERIFICATION_SCHEMA,
        "ready": not gaps,
        "gaps": sorted(set(gaps)),
        "causal_experiment_id": causal_plan.get("experiment", {}).get("experiment_id"),
        "baseline_experiment_id": baseline_plan.get("experiment", {}).get("experiment_id"),
        "baseline_receipt_digest": receipt_digest,
        "artifact_digests": {
            field: _sha256_file(path)
            for field, path in artifact_paths.items()
            if path is not None and path.is_file()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--causal-plan", type=Path, required=True)
    parser.add_argument("--baseline-plan", type=Path, required=True)
    parser.add_argument("--baseline-receipt", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--traces", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_baseline_bundle(
        _load_object(args.causal_plan),
        _load_object(args.baseline_plan),
        _load_object(args.baseline_receipt) if args.baseline_receipt else None,
        baseline_plan_path=args.baseline_plan,
        manifest_path=args.manifest,
        traces_path=args.traces,
        report_path=args.report,
        receipt_path=args.baseline_receipt,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
