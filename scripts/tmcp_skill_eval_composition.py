"""Immutable source-bundle verification for composition campaigns."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any

from scripts.tmcp_skill_eval_campaign_protocol import _sha256_file
from scripts.verify_composition_study import verify_study


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def verify_source_bundle_study(
    args: Namespace, plan: dict[str, Any]
) -> dict[str, Any] | None:
    """Verify immutable inputs for a causal or derived baseline campaign."""

    requires_study = any(
        row.get("pattern_id") == "composition.source-bundle-inclusion"
        and row.get("intervention_target") == args.intervention_target
        for row in plan.get("task_matrix", [])
        if isinstance(row, dict)
    )
    if not requires_study:
        return None
    if args.composition_study_dir is None:
        raise ValueError(
            "source-bundle campaigns require --composition-study-dir for "
            "immutable-input and live-source verification."
        )
    study_plan_path = (
        args.composition_study_dir / "generated" / "tmcp-composition-study-plan.json"
    ).resolve()
    plan_path = args.plan.resolve()
    verification_plan_path = plan_path
    if plan_path != study_plan_path:
        experiment = plan.get("experiment")
        source_experiment_id = (
            experiment.get("baseline_source_experiment_id")
            if isinstance(experiment, dict)
            else None
        )
        if not isinstance(source_experiment_id, str) or not study_plan_path.is_file():
            raise ValueError(
                "derived source-bundle plans must identify the checked-in source study plan."
            )
        source_plan = _load_json(study_plan_path)
        source_experiment = source_plan.get("experiment")
        if not isinstance(source_experiment, dict) or source_experiment.get(
            "experiment_id"
        ) != source_experiment_id:
            raise ValueError("derived source-bundle plan does not match its source study.")
        if not isinstance(experiment, dict) or experiment.get(
            "source_study_binding"
        ) != source_experiment.get("source_study_binding"):
            raise ValueError("derived source-bundle plan has a mismatched study binding.")
        verification_plan_path = study_plan_path
    report = verify_study(
        args.composition_study_dir,
        plan_path=verification_plan_path,
        check_live_sources=True,
    )
    if report["live_sources"]["status"] != "matched":
        raise ValueError("source-bundle campaign live sources do not match pinned digests.")
    first_principles_source = args.first_principles_source
    if (
        not isinstance(first_principles_source, dict)
        or first_principles_source.get("kind") != "file"
        or not isinstance(first_principles_source.get("path"), str)
    ):
        raise ValueError(
            "source-bundle campaigns require --first-principles-file from the "
            "pinned study evidence."
        )
    supplied_digest = _sha256_file(Path(first_principles_source["path"]))
    expected_digest = report["static"]["input_digests"]["first-principles.txt"]
    if supplied_digest != expected_digest:
        raise ValueError(
            "source-bundle campaign first-principles file does not match the "
            "pinned study input."
        )
    return report
