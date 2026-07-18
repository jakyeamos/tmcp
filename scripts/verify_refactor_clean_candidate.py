#!/usr/bin/env python3
"""Verify that a reviewed refactor-clean candidate is ready to preregister."""

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


VERIFICATION_SCHEMA = "tmcp-refactor-clean-candidate-readiness-v0.1"
MIN_FIXTURES = 6
MIN_FIXTURE_FAMILIES = 3


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_digest(fixture: dict[str, Any]) -> str:
    payload = json.dumps(fixture, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fixture_gaps(fixture: dict[str, Any], *, expected_source_digest: str | None) -> list[str]:
    gaps: list[str] = []
    if fixture.get("schema") != "tmcp-refactor-clean-fixture-review-v0.1":
        gaps.append("fixture_schema_invalid")
    if fixture.get("review_status") != "approved_for_preregistration":
        gaps.append("fixture_review_not_approved")
    if fixture.get("evaluation_mode") != "judgment":
        gaps.append("fixture_evaluation_mode_invalid")
    target = fixture.get("target_source")
    if not isinstance(target, dict) or not target.get("path") or not target.get("sha256"):
        gaps.append("fixture_source_pin_missing")
    elif expected_source_digest is not None and target.get("sha256") != expected_source_digest:
        gaps.append("fixture_source_digest_mismatch")
    task = fixture.get("fixture")
    bar = fixture.get("outcome_bar")
    blindness = fixture.get("blindness_contract")
    if not isinstance(task, dict) or not task.get("id") or not task.get("fixture_family"):
        gaps.append("fixture_task_identity_missing")
    if not isinstance(bar, dict) or not bar.get("standard") or not bar.get("expected_observables") or not bar.get("failure_smells"):
        gaps.append("fixture_outcome_bar_incomplete")
    if not isinstance(blindness, dict):
        gaps.append("fixture_blindness_contract_missing")
    else:
        runner_must_not = set(blindness.get("runner_must_not_receive", []))
        judge_must_not = set(blindness.get("judge_must_not_receive", []))
        if {"outcome_bar", "failure_smells", "hypothesis or arm label"} - runner_must_not:
            gaps.append("runner_blindness_incomplete")
        if "fixture arm label" not in judge_must_not or not any(
            value.startswith("source-bundle") for value in judge_must_not
        ):
            gaps.append("judge_blindness_incomplete")
    prompt = str(task.get("runner_prompt", "")) if isinstance(task, dict) else ""
    lowered = prompt.lower()
    required_scope_phrases = ("do not use tools", "inspect a repository", "edit files")
    if not all(term in lowered for term in required_scope_phrases) or not (
        "execute a refactor" in lowered or "plan has been executed" in lowered
    ):
        gaps.append("fixture_runner_scope_not_read_only")
    return gaps


def verify_refactor_clean_candidate(
    candidate_dir: Path,
    fixture_paths: list[Path],
    *,
    source_path: Path | None = None,
    source_bundle_path: Path | None = None,
    first_principles_path: Path | None = None,
    packet_probe_receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Return a no-call readiness report for a future refactor-clean study."""

    gaps: list[str] = []
    if not fixture_paths:
        gaps.append("fixtures_missing")
    if len(fixture_paths) < MIN_FIXTURES:
        gaps.append("fixture_count_below_minimum")
    first_principles = first_principles_path or candidate_dir / "first-principles.md"
    if not first_principles.is_file():
        gaps.append("first_principles_missing")
    source = source_path
    expected_source_digest = _sha256_file(source) if source is not None and source.is_file() else None
    if source is not None and not source.is_file():
        gaps.append("target_source_missing")
    if source_bundle_path is None or not source_bundle_path.is_file():
        gaps.append("source_bundle_not_archived")
    packet_probe_receipt = packet_probe_receipt_path or candidate_dir / "packet-probe-receipt.json"
    if not packet_probe_receipt.is_file():
        gaps.append("packet_probe_receipt_missing")

    fixture_ids: list[str] = []
    fixture_families: list[str] = []
    fixture_digests: list[str] = []
    fixture_reports: list[dict[str, Any]] = []
    review_record_paths: set[Path] = set()
    for path in fixture_paths:
        if not path.is_file():
            gaps.append("fixture_file_missing")
            continue
        fixture = _load_object(path)
        fixture_gaps = _fixture_gaps(fixture, expected_source_digest=expected_source_digest)
        review_record_ref = fixture.get("review_record")
        review_record_path = (
            (path.parent / str(review_record_ref)).resolve()
            if isinstance(review_record_ref, str) and review_record_ref
            else None
        )
        if review_record_path is None or not review_record_path.is_file():
            fixture_gaps.append("fixture_review_record_missing")
        else:
            review_record_paths.add(review_record_path)
        gaps.extend(fixture_gaps)
        task = fixture.get("fixture")
        if isinstance(task, dict):
            fixture_ids.append(str(task.get("id") or ""))
            fixture_families.append(str(task.get("fixture_family") or ""))
        fixture_digest = _fixture_digest(fixture)
        fixture_digests.append(fixture_digest)
        fixture_reports.append(
            {
                "path": str(path),
                "digest": fixture_digest,
                "review_record": str(review_record_path) if review_record_path else None,
                "review_record_sha256": _sha256_file(review_record_path)
                if review_record_path is not None and review_record_path.is_file()
                else None,
                "gaps": fixture_gaps,
            }
        )

    if len(set(fixture_ids)) != len(fixture_ids) or "" in fixture_ids:
        gaps.append("fixture_ids_not_unique")
    if len(set(fixture_digests)) != len(fixture_digests):
        gaps.append("fixture_digests_not_unique")
    if len(set(fixture_families)) < MIN_FIXTURE_FAMILIES:
        gaps.append("fixture_family_count_below_minimum")

    if not review_record_paths:
        gaps.append("fixture_review_record_missing")
    review_records = [
        {
            "path": str(path),
            "sha256": _sha256_file(path),
        }
        for path in sorted(review_record_paths)
    ]
    unique_gaps = sorted(set(gaps))
    if any(gap.startswith("fixture_review") for gap in unique_gaps):
        next_gate = "complete_independent_fixture_review"
    elif len(fixture_paths) < MIN_FIXTURES:
        next_gate = "extend_reviewed_fixture_set"
    else:
        next_gate = "archive_source_bundle_and_packet_receipt"
    return {
        "schema": VERIFICATION_SCHEMA,
        "ready": not unique_gaps,
        "candidate_state": "approved_for_preregistration",
        "preregistration_ready": not unique_gaps,
        "model_calls_authorized": False,
        "next_gate": next_gate,
        "gaps": unique_gaps,
        "candidate_dir": str(candidate_dir),
        "fixture_count": len(fixture_paths),
        "fixture_family_count": len(set(fixture_families)),
        "fixture_digests": fixture_digests,
        "source_sha256": expected_source_digest,
        "first_principles_sha256": _sha256_file(first_principles) if first_principles.is_file() else None,
        "review_records": review_records,
        "packet_probe_receipt_sha256": _sha256_file(packet_probe_receipt) if packet_probe_receipt.is_file() else None,
        "synthetic_no_tool_boundary": True,
        "fixtures": fixture_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, action="append", dest="fixtures")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-bundle", type=Path)
    parser.add_argument("--first-principles", type=Path)
    parser.add_argument("--packet-probe-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture_paths = args.fixtures or sorted((args.candidate_dir / "fixtures").glob("*.json"))
    report = verify_refactor_clean_candidate(
        args.candidate_dir,
        fixture_paths,
        source_path=args.source,
        source_bundle_path=args.source_bundle,
        first_principles_path=args.first_principles,
        packet_probe_receipt_path=args.packet_probe_receipt,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
