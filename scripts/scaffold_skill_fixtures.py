#!/usr/bin/env python3
"""Create isolated, versioned skill fixtures without inventing evaluation bars."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "tmcp-skill-fixture-manifest-v0.1"
VARIANTS = ("baseline", "original", "negative_control", "candidate")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().replace("/", "__"))
    return value.strip("-").lower() or "skill"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", required=True, type=Path)
    parser.add_argument("--extra-skill", action="append", type=Path, default=[])
    parser.add_argument("--seed-cases", type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="replace an existing generated output directory")
    return parser.parse_args()


def source_id(path: Path, roots: list[Path], extras: set[Path]) -> str:
    resolved = path.resolve()
    if resolved in extras:
        return slug(f"fixture__{path.parent.name}")
    for root in roots:
        root = root.resolve()
        if root == resolved.parent or root in resolved.parents:
            return slug(f"{root.parent.name}__{resolved.relative_to(root).parent}")
    raise ValueError(f"skill is outside configured roots: {path}")


def load_seed_cases(path: Path | None, project_root: Path) -> dict[str, list[dict[str, Any]]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") not in {
        "tmcp-skill-fixture-seed-cases-v0.1",
        "tmcp-individual-skill-admission-cases-v0.1",
    }:
        raise ValueError("seed cases have the wrong schema")
    result: dict[str, list[dict[str, Any]]] = {}
    for case in payload.get("cases", []):
        source = str((project_root / str(case["source_path"])).resolve())
        clean = {key: case[key] for key in ("case_id", "mode", "prompt", "bar", "smells")}
        if "observables" in case:
            clean["observables"] = case["observables"]
        if "provenance" in case:
            clean["provenance"] = case["provenance"]
        if "execution_boundary" in case:
            clean["execution_boundary"] = case["execution_boundary"]
        if not clean["bar"].strip():
            raise ValueError(f"seed case {clean['case_id']} has an empty bar")
        result.setdefault(source, []).append(clean)
    return result


def write_variant(root: Path, variant: str, source: Path, digest: str) -> dict[str, str]:
    variant_root = root / "versions" / variant
    variant_root.mkdir(parents=True, exist_ok=True)
    if variant in {"original", "candidate"}:
        target = variant_root / "SKILL.md"
        shutil.copy2(source, target)
        selection = "included"
    else:
        target = variant_root / "variant.json"
        target.write_text(
            json.dumps({
                "variant_id": variant,
                "selection": "omitted" if variant == "baseline" else "replaced",
                "reason": "controlled fixture variant; no target skill body is supplied",
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        selection = "omitted" if variant == "baseline" else "replaced"
    return {
        "version_id": variant,
        "kind": variant,
        "selection": selection,
        "path": str(target.relative_to(root.parent.parent)),
        "parent_sha256": digest,
        "content_sha256": sha256(target),
    }


def main() -> None:
    args = parse_args()
    roots = [root.resolve() for root in args.root]
    extras = {path.resolve() for path in args.extra_skill}
    skills = sorted(
        {path.resolve() for root in roots for path in root.rglob("SKILL.md") if path.is_file()}
        | {path for path in extras if path.is_file()},
        key=str,
    )
    if not skills:
        raise SystemExit("no SKILL.md files found")
    seed_cases = load_seed_cases(args.seed_cases, args.project_root.resolve())
    output = args.output_dir.resolve()
    if output.exists() and not args.force:
        raise SystemExit(f"output already exists; pass --force to replace it: {output}")
    if output.exists():
        shutil.rmtree(output)
    (output / "skills").mkdir(parents=True)
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source in skills:
        skill_id = source_id(source, roots, extras)
        if skill_id in seen_ids:
            raise ValueError(f"duplicate generated skill_id: {skill_id}")
        seen_ids.add(skill_id)
        digest = sha256(source)
        skill_root = output / "skills" / skill_id
        versions = {variant: write_variant(skill_root, variant, source, digest) for variant in VARIANTS}
        cases = seed_cases.get(str(source), [])
        readiness = "ready" if cases else "needs_golden_case_and_bar"
        records.append({
            "skill_id": skill_id,
            "source_path": str(source),
            "source_sha256": digest,
            "versions": versions,
            "cases": cases,
            "readiness": readiness,
        })
    manifest = {
        "schema": SCHEMA,
        "fixture_set_id": f"skill-corpus-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "policy": {
            "blind": True,
            "requires_golden_case": True,
            "requires_bar": True,
            "auto_rewrite": False,
        },
        "skills": records,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "manifest": str(output / "manifest.json"),
        "skill_count": len(records),
        "ready_count": sum(item["readiness"] == "ready" for item in records),
        "needs_case_or_bar_count": sum(item["readiness"] != "ready" for item in records),
    }, indent=2))


if __name__ == "__main__":
    main()
