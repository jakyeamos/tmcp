#!/usr/bin/env python3
"""Apply explicitly approved, hash-chained skill proposals to candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


SCHEMA = "tmcp-skill-fixture-proposals-v0.1"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def load_bundle(path: Path, skill_id: str, source_sha256: str) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("schema") != SCHEMA:
        raise SystemExit(f"{path}: invalid proposal schema")
    if payload.get("skill_id") != skill_id:
        raise SystemExit(f"{path}: skill_id does not match {skill_id}")
    if payload.get("source_sha256") != source_sha256:
        raise SystemExit(f"{path}: source_sha256 does not match fixture source")
    proposals = payload.get("proposals")
    if not isinstance(proposals, list):
        raise SystemExit(f"{path}: proposals must be an array")
    ids: set[str] = set()
    for proposal in proposals:
        proposal_id = proposal.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id or proposal_id in ids:
            raise SystemExit(f"{path}: proposal IDs must be unique and non-empty")
        ids.add(proposal_id)
        if proposal.get("target") != "SKILL.md":
            raise SystemExit(f"{path}/{proposal_id}: target must be SKILL.md")
        if proposal.get("status") not in {"proposed", "approved", "rejected"}:
            raise SystemExit(f"{path}/{proposal_id}: invalid review status")
        replacement = proposal.get("replacement")
        if not isinstance(replacement, str) or not replacement:
            raise SystemExit(f"{path}/{proposal_id}: replacement must be non-empty text")
        if digest_bytes(replacement.encode("utf-8")) != proposal.get("after_sha256"):
            raise SystemExit(f"{path}/{proposal_id}: replacement hash does not match after_sha256")
    return payload, digest_bytes(raw)


def apply_bundle(
    manifest_path: Path,
    skill: dict[str, Any],
    bundle_path: Path,
    replace_candidate: bool,
) -> dict[str, Any]:
    skill_id = str(skill["skill_id"])
    source_sha256 = str(skill["source_sha256"])
    versions = skill["versions"]
    original = (manifest_path.parent / str(versions["original"]["path"])).resolve()
    candidate = (manifest_path.parent / str(versions["candidate"]["path"])).resolve()
    if manifest_path.parent not in original.parents or manifest_path.parent not in candidate.parents:
        raise SystemExit(f"{skill_id}: fixture version escapes output root")
    if not original.is_file() or not candidate.is_file():
        raise SystemExit(f"{skill_id}: original or candidate fixture is missing")
    if digest(original) != source_sha256:
        raise SystemExit(f"{skill_id}: original fixture is not the recorded source")
    payload, bundle_sha256 = load_bundle(bundle_path.resolve(), skill_id, source_sha256)
    candidate_info = versions["candidate"]
    candidate_digest = digest(candidate)
    if candidate_digest != candidate_info.get("content_sha256"):
        raise SystemExit(f"{skill_id}: candidate changed without recording its digest")
    if candidate_info.get("proposal_bundle_sha256") == bundle_sha256:
        return {
            "skill_id": skill_id,
            "bundle_sha256": bundle_sha256,
            "applied_proposal_ids": candidate_info.get("applied_proposal_ids", []),
            "skipped_proposal_ids": candidate_info.get("skipped_proposal_ids", []),
            "changed": False,
        }
    if candidate_digest != source_sha256 and not replace_candidate:
        raise SystemExit(
            f"{skill_id}: candidate already differs from original; pass --replace-candidate explicitly"
        )

    content = original.read_text(encoding="utf-8")
    current_sha256 = source_sha256
    applied: list[str] = []
    skipped: list[str] = []
    for proposal in payload["proposals"]:
        proposal_id = str(proposal["proposal_id"])
        if proposal["status"] != "approved":
            skipped.append(proposal_id)
            continue
        if proposal["before_sha256"] != current_sha256:
            raise SystemExit(
                f"{skill_id}/{proposal_id}: before_sha256 does not match the preceding content"
            )
        content = str(proposal["replacement"])
        current_sha256 = str(proposal["after_sha256"])
        applied.append(proposal_id)

    candidate.write_text(content, encoding="utf-8")
    proposal_copy = manifest_path.parent / "proposals" / f"{skill_id}.json"
    proposal_copy.parent.mkdir(parents=True, exist_ok=True)
    if bundle_path.resolve() != proposal_copy.resolve():
        shutil.copy2(bundle_path, proposal_copy)
    candidate_info["content_sha256"] = current_sha256
    candidate_info["proposal_bundle_sha256"] = bundle_sha256
    candidate_info["proposal_path"] = str(proposal_copy.relative_to(manifest_path.parent))
    candidate_info["applied_proposal_ids"] = applied
    candidate_info["skipped_proposal_ids"] = skipped
    return {
        "skill_id": skill_id,
        "bundle_sha256": bundle_sha256,
        "applied_proposal_ids": applied,
        "skipped_proposal_ids": skipped,
        "changed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--proposals-dir", required=True, type=Path)
    parser.add_argument("--skill-id", action="append", default=[])
    parser.add_argument("--all", action="store_true", help="apply every proposal bundle found")
    parser.add_argument("--replace-candidate", action="store_true")
    args = parser.parse_args()
    if not args.all and not args.skill_id:
        raise SystemExit("select skills with --skill-id or use --all")
    manifest_path = args.manifest.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    skills = {str(item.get("skill_id")): item for item in payload.get("skills", [])}
    selected = sorted(
        skills if args.all else set(args.skill_id),
    )
    if not selected:
        raise SystemExit("no skills selected")
    results = []
    for skill_id in selected:
        if skill_id not in skills:
            raise SystemExit(f"unknown skill_id: {skill_id}")
        bundle = args.proposals_dir / f"{skill_id}.json"
        if not bundle.is_file():
            raise SystemExit(f"missing proposal bundle for {skill_id}: {bundle}")
        results.append(apply_bundle(manifest_path, skills[skill_id], bundle, args.replace_candidate))
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": "tmcp-skill-fixture-proposal-application-v0.1",
        "manifest": str(manifest_path),
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
