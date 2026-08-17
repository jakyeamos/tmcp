#!/usr/bin/env python3
"""Validate a selected fixture corpus and compare with recorded judge outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from scripts.validate_skill_fixture_artifact import validate_fixture_artifact
except ModuleNotFoundError:  # Direct execution places scripts/ before the project root.
    from validate_skill_fixture_artifact import (  # pyright: ignore[reportImplicitRelativeImport]
        validate_fixture_artifact,
    )


SCHEMA = "tmcp-skill-fixture-corpus-validation-v0.1"


def validate_corpus(
    manifest: Mapping[str, object],
    *,
    project_root: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    families = manifest.get("families")
    if not isinstance(families, list):
        raise ValueError("manifest families must be a list")

    family_reports: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for family in families:
        if not isinstance(family, dict):
            errors.append("family entry is not an object")
            continue
        family_id = family.get("id")
        spec_path = project_root / str(family.get("spec"))
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{family_id}: unable to load spec {spec_path}: {exc}")
            continue
        if not isinstance(spec, dict):
            errors.append(f"{family_id}: spec is not a JSON object")
            continue

        runs = family.get("runs")
        if not isinstance(runs, list):
            errors.append(f"{family_id}: runs must be a list")
            continue
        rows: list[dict[str, Any]] = []
        for run in runs:
            if not isinstance(run, dict) or not isinstance(run.get("artifact"), str):
                errors.append(f"{family_id}: malformed run entry")
                continue
            artifact_path = artifact_root / str(run["artifact"])
            try:
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(
                    f"{family_id}/{artifact_path.name}: unable to load artifact: {exc}"
                )
                continue
            if not isinstance(artifact, dict):
                errors.append(
                    f"{family_id}/{artifact_path.name}: artifact is not a JSON object"
                )
                continue
            structural = validate_fixture_artifact(artifact, spec)
            expected_judge = run.get("judge_pass")
            agreement = (
                expected_judge == structural["passed"]
                if isinstance(expected_judge, bool)
                else None
            )
            judge_provenance: dict[str, Any] | None = None
            judge_artifact = run.get("judge_artifact")
            judge_record_index = run.get("judge_record_index")
            if judge_artifact is not None:
                if not isinstance(judge_artifact, str):
                    errors.append(
                        f"{family_id}/{artifact_path.name}: judge_artifact must be a string"
                    )
                elif not isinstance(judge_record_index, int) or judge_record_index < 0:
                    errors.append(
                        f"{family_id}/{artifact_path.name}: judge_record_index must be a non-negative integer"
                    )
                else:
                    judge_path = Path(judge_artifact)
                    if not judge_path.is_absolute():
                        judge_path = artifact_root / judge_path
                    try:
                        judge_bytes = judge_path.read_bytes()
                        judge_payload = json.loads(judge_bytes)
                        if isinstance(judge_payload, list):
                            judge_record = judge_payload[judge_record_index]
                        elif judge_record_index == 0:
                            judge_record = judge_payload
                        else:
                            raise IndexError(
                                "record index is greater than zero for an object judge artifact"
                            )
                        if not isinstance(judge_record, dict) or not isinstance(
                            judge_record.get("pass"), bool
                        ):
                            raise ValueError(
                                "judge record must be an object with a boolean pass field"
                            )
                        record_pass = judge_record["pass"]
                        if (
                            isinstance(expected_judge, bool)
                            and record_pass is not expected_judge
                        ):
                            errors.append(
                                f"{family_id}/{artifact_path.name}: recorded judge_pass disagrees with "
                                f"judge artifact record {judge_artifact}[{judge_record_index}]"
                            )
                        judge_provenance = {
                            "path": str(judge_path),
                            "sha256": hashlib.sha256(judge_bytes).hexdigest(),
                            "record_index": judge_record_index,
                            "record_pass": record_pass,
                            "run_id": judge_record.get("run_id"),
                        }
                    except (
                        OSError,
                        json.JSONDecodeError,
                        IndexError,
                        TypeError,
                        ValueError,
                    ) as exc:
                        errors.append(
                            f"{family_id}/{artifact_path.name}: unable to load judge artifact "
                            f"{judge_artifact}[{judge_record_index}]: {exc}"
                        )
            row = {
                "artifact": str(run["artifact"]),
                "structural_pass": structural["passed"],
                "failed_observables": structural["failed_observables"],
                "judge_pass": expected_judge,
                "judge_agreement": agreement,
            }
            if judge_provenance is not None:
                row["judge_provenance"] = judge_provenance
            rows.append(row)
            all_rows.append({"family": family_id, **row})

        family_reports.append(
            {
                "id": family_id,
                "coverage": family.get("coverage"),
                "artifact_count": len(rows),
                "structural_pass_count": sum(
                    bool(row["structural_pass"]) for row in rows
                ),
                "judge_pass_count": sum(row["judge_pass"] is True for row in rows),
                "judge_agreement_count": sum(
                    row["judge_agreement"] is True for row in rows
                ),
                "judge_disagreement_count": sum(
                    row["judge_agreement"] is False for row in rows
                ),
                "rows": rows,
            }
        )

    disagreements = [row for row in all_rows if row["judge_agreement"] is False]
    return {
        "schema": SCHEMA,
        "manifest_schema": manifest.get("schema"),
        "family_count": len(family_reports),
        "artifact_count": len(all_rows),
        "structural_pass_count": sum(bool(row["structural_pass"]) for row in all_rows),
        "judge_pass_count": sum(row["judge_pass"] is True for row in all_rows),
        "judge_agreement_count": sum(
            row["judge_agreement"] is True for row in all_rows
        ),
        "judge_disagreement_count": len(disagreements),
        "errors": errors,
        "gate_pass": not errors and not disagreements,
        "families": family_reports,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path, default=Path("/private/tmp"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise SystemExit("manifest must contain a JSON object")
    report = validate_corpus(
        manifest,
        project_root=args.project_root,
        artifact_root=args.artifact_root,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
