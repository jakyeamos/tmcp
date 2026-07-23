#!/usr/bin/env python3
"""Record the digest of an intentionally edited candidate fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--skill-id", required=True)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill = next((item for item in payload.get("skills", []) if item.get("skill_id") == args.skill_id), None)
    if skill is None:
        raise SystemExit(f"unknown skill_id: {args.skill_id}")
    version = skill.get("versions", {}).get("candidate")
    if not isinstance(version, dict):
        raise SystemExit(f"{args.skill_id} has no candidate version")
    target = (manifest_path.parent / str(version.get("path", ""))).resolve()
    if target.name != "SKILL.md" or not target.is_file() or manifest_path.parent not in target.parents:
        raise SystemExit("candidate target is missing or escapes fixture root")
    version["content_sha256"] = digest(target)
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": "tmcp-skill-fixture-candidate-record-v0.1",
        "skill_id": args.skill_id,
        "candidate": str(target),
        "content_sha256": version["content_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
