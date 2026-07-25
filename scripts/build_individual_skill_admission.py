#!/usr/bin/env python3
"""Build a source-bound behavioral-admission queue for the individual skill audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "tmcp-individual-skill-admission-v0.1"
CASE_SCHEMA = "tmcp-individual-skill-admission-cases-v0.1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path, help="individual-skill-audit-v0.1 JSON")
    parser.add_argument("cases", type=Path, help="source-bound admission cases JSON")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def validate_case(case: dict[str, Any], skills: dict[str, dict[str, Any]]) -> dict[str, Any]:
    path = str(case.get("source_path", ""))
    if path not in skills:
        raise ValueError(f"admission case points outside audit: {path}")
    for field in ("case_id", "mode", "prompt", "bar", "smells", "provenance"):
        if field not in case:
            raise ValueError(f"admission case {case.get('case_id', '<unknown>')} lacks {field}")
    if not str(case["prompt"]).strip() or not str(case["bar"]).strip():
        raise ValueError(f"admission case {case['case_id']} has an empty prompt or bar")
    if not isinstance(case["provenance"], list) or not case["provenance"]:
        raise ValueError(f"admission case {case['case_id']} needs provenance")
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"admission case source does not exist: {path}")
    expected_hash = skills[path].get("source_sha256") or skills[path].get("sha256")
    actual_hash = sha256(source)
    if expected_hash != actual_hash:
        raise ValueError(f"source hash drift for {path}: audit={expected_hash} actual={actual_hash}")
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    for pointer in case["provenance"]:
        line = int(pointer.get("line", 0))
        excerpt = str(pointer.get("excerpt", ""))
        if line < 1 or line > len(lines) or excerpt not in lines[line - 1]:
            raise ValueError(f"invalid provenance for {case['case_id']}: line {line}")
    record = dict(case)
    record["source_sha256"] = actual_hash
    record["admission_status"] = "case_ready"
    record["bar_status"] = "source_bound"
    return record


def main() -> None:
    args = parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    if audit.get("schema") != "tmcp-individual-skill-audit-v0.1":
        raise SystemExit("audit input has the wrong schema")
    case_payload = json.loads(args.cases.read_text(encoding="utf-8"))
    if case_payload.get("schema") != CASE_SCHEMA:
        raise SystemExit("case input has the wrong schema")
    skills = {str(item["skill_path"]): item for item in audit.get("skills", [])}
    cases_by_skill: dict[str, list[dict[str, Any]]] = {}
    case_ids: set[str] = set()
    for raw_case in case_payload.get("cases", []):
        case = validate_case(raw_case, skills)
        if case["case_id"] in case_ids:
            raise ValueError(f"duplicate admission case id: {case['case_id']}")
        case_ids.add(case["case_id"])
        cases_by_skill.setdefault(case["source_path"], []).append(case)

    skills_out: list[dict[str, Any]] = []
    for path, audit_record in sorted(skills.items()):
        cases = cases_by_skill.get(path, [])
        skills_out.append({
            "skill_path": path,
            "source_sha256": audit_record.get("source_sha256") or audit_record.get("sha256"),
            "static_status": audit_record.get("static_status"),
            "static_warning_ids": audit_record.get("warning_ids", []),
            "admission_status": "case_ready" if cases else "needs_golden_case_and_bar",
            "cases": cases,
            "next_case_shape": audit_record.get("recommended_next_case", {}).get("case_shape"),
        })
    output = {
        "schema": SCHEMA,
        "source_audit": audit.get("source_audit"),
        "source_audit_sha256": audit.get("source_audit_sha256"),
        "case_source": str(args.cases.resolve()),
        "case_source_sha256": sha256(args.cases.resolve()),
        "policy": {
            "source_bound_cases_only": True,
            "provenance_checked": True,
            "static_findings_are_not_runtime_failures": True,
            "runner_bar_hidden": True,
            "independent_judge_required": True,
            "automatic_rewrite": False,
        },
        "summary": {
            "skill_count": len(skills_out),
            "case_ready_skill_count": sum(item["admission_status"] == "case_ready" for item in skills_out),
            "needs_case_or_bar_count": sum(item["admission_status"] != "case_ready" for item in skills_out),
            "case_count": len(case_ids),
        },
        "skills": skills_out,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), **output["summary"]}, indent=2))


if __name__ == "__main__":
    main()
