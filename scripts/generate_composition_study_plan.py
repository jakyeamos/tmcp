#!/usr/bin/env python3
"""Build a byte-pinned plan for one source-bundle composition study."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tmcp_runtime.services.evaluation_plan import displayed_content_digest  # noqa: E402


REQUIRED_INPUT_DIGESTS = frozenset(
    {
        "campaign-policy.json",
        "cost-evaluation-bar.md",
        "cost-rejudge-policy.json",
        "first-principles.txt",
        "fixtures-reviewed-v1.json",
        "packet-base.md",
        "source-bundle.md",
    }
)
SOURCE_STUDY_BINDING_SCHEMA = "tmcp-composition-study-binding-v0.1"


def _read_json(path: Path) -> dict[str, Any] | list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, (dict, list)):
        raise ValueError(f"Expected JSON object or list in {path}.")
    return value


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_id(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "composition-study-" + hashlib.sha256(payload).hexdigest()[:16]


def _load_object(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return value


def _load_list(path: Path) -> list[dict[str, Any]]:
    value = _read_json(path)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Expected JSON object list in {path}.")
    return value


def verify_study_input_digests(
    study_dir: Path, definition: Mapping[str, Any]
) -> dict[str, str]:
    """Reject a plan when any preregistered study input has changed."""

    inputs = study_dir / "inputs"
    expected = definition.get("input_digests")
    if not isinstance(expected, Mapping) or set(expected) != REQUIRED_INPUT_DIGESTS:
        raise ValueError(
            "study.json input_digests must pin every required composition study input."
        )
    actual: dict[str, str] = {}
    for name in sorted(REQUIRED_INPUT_DIGESTS):
        expected_digest = expected.get(name)
        if not isinstance(expected_digest, str) or not expected_digest.startswith(
            "sha256:"
        ):
            raise ValueError(f"study.json input_digests.{name} must be a sha256 digest.")
        actual_digest = _sha256_file(inputs / name)
        if actual_digest != expected_digest:
            raise ValueError(f"study input digest does not match for {name}.")
        actual[name] = actual_digest
    receipt_digest = _sha256_file(inputs / "packet-receipt.json")
    if definition.get("receipt_sha256") != receipt_digest:
        raise ValueError("study input digest does not match for packet-receipt.json.")
    actual["packet-receipt.json"] = receipt_digest
    return actual


def validate_cost_rejudge_policy(
    study_dir: Path, policy: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the preregistered, all-trace cost-sidecar commitment."""

    if policy.get("schema") != "tmcp-composition-cost-rejudge-policy-v0.1":
        raise ValueError("cost rejudge policy schema does not match.")
    experiment = plan.get("experiment")
    campaign_policy = (
        experiment.get("campaign_policy") if isinstance(experiment, Mapping) else None
    )
    if not isinstance(campaign_policy, Mapping):
        raise ValueError("cost rejudge policy requires a campaign policy.")
    configurations = campaign_policy.get("runner_configurations")
    cross_model = campaign_policy.get("cross_model_confirmation")
    if not isinstance(configurations, list) or not isinstance(cross_model, Mapping):
        raise ValueError("cost rejudge policy requires runner configurations.")
    repetitions = cross_model.get("minimum_repetitions_per_cell")
    if not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("cost rejudge policy requires positive repetitions.")
    matrix = plan.get("task_matrix")
    if not isinstance(matrix, list):
        raise ValueError("cost rejudge policy requires a task matrix.")
    expected_trace_count = len(matrix) * len(configurations) * repetitions
    if policy.get("expected_trace_count") != expected_trace_count:
        raise ValueError("cost rejudge policy trace count does not match the campaign.")
    if not isinstance(policy.get("model"), str) or not policy["model"].strip():
        raise ValueError("cost rejudge policy model must be non-empty.")
    if not isinstance(policy.get("judge_effort"), str) or not policy[
        "judge_effort"
    ].strip():
        raise ValueError("cost rejudge policy judge_effort must be non-empty.")
    if not isinstance(policy.get("seed"), int):
        raise ValueError("cost rejudge policy seed must be an integer.")
    if policy.get("cost_bar_file") != "cost-evaluation-bar.md":
        raise ValueError("cost rejudge policy cost bar filename is invalid.")
    cost_bar_digest = _sha256_file(study_dir / "inputs" / "cost-evaluation-bar.md")
    if policy.get("cost_bar_sha256") != cost_bar_digest:
        raise ValueError("cost rejudge policy cost bar digest does not match.")
    if policy.get("raw_labels_preserved") is not True or policy.get(
        "complete_before_promotion"
    ) is not True:
        raise ValueError("cost rejudge policy must preserve raw labels and gate promotion.")
    independence = policy.get("process_independence")
    required_independence = (
        "fresh_judge",
        "fresh_session",
        "judge_blinded",
        "condition_hidden",
        "source_artifact_only",
        "isolated_session",
    )
    if not isinstance(independence, Mapping) or any(
        independence.get(field) is not True for field in required_independence
    ):
        raise ValueError("cost rejudge policy independence contract is incomplete.")
    if independence.get("model_identity_independence_claimed") is not False:
        raise ValueError("cost rejudge policy must not claim model identity independence.")
    if not isinstance(policy.get("claim_boundary"), str) or not policy[
        "claim_boundary"
    ].strip():
        raise ValueError("cost rejudge policy claim_boundary must be non-empty.")
    return {
        "expected_trace_count": expected_trace_count,
        "model": policy["model"],
        "judge_effort": policy["judge_effort"],
        "cost_bar_sha256": cost_bar_digest,
        "claim_boundary": policy["claim_boundary"],
    }


def build_plan(study_dir: Path) -> dict[str, Any]:
    inputs = study_dir / "inputs"
    definition = _load_object(inputs / "study.json")
    study_input_digests = verify_study_input_digests(study_dir, definition)
    fixtures = _load_list(inputs / "fixtures-reviewed-v1.json")
    policy = _load_object(inputs / "campaign-policy.json")
    cost_rejudge_policy = _load_object(inputs / "cost-rejudge-policy.json")
    base_attachment = (inputs / "packet-base.md").read_text(encoding="utf-8").strip()
    source_bundle = (inputs / "source-bundle.md").read_text(encoding="utf-8").strip()
    if not base_attachment or not source_bundle:
        raise ValueError("Packet base and source bundle must be non-empty.")
    source_entries = definition.get("selected_sources")
    if not isinstance(source_entries, list) or not all(
        isinstance(item, dict) for item in source_entries
    ):
        raise ValueError("study.json selected_sources must be an object list.")
    source_study_binding = {
        "schema": SOURCE_STUDY_BINDING_SCHEMA,
        "input_digests": study_input_digests,
        "selected_sources": [dict(item) for item in source_entries],
    }
    treatment_attachment = f"{base_attachment}\n\n{source_bundle}"
    base_digest = displayed_content_digest(base_attachment)
    source_bundle_digest = displayed_content_digest(source_bundle)
    pattern_contract = {
        "tested_atom": "materialized_source_bundle",
        "allowed_targets": ["source_bundle"],
        "allowed_kinds": ["source_bundle_inclusion"],
        "claim_granularity": "source_bundle_delivery",
        "expected_support_direction": "positive",
    }
    experiment_id = _stable_id(
        {
            "definition": definition,
            "fixture_sha256": _sha256_file(inputs / "fixtures-reviewed-v1.json"),
            "policy_sha256": _sha256_file(inputs / "campaign-policy.json"),
            "packet_base_sha256": _sha256_file(inputs / "packet-base.md"),
            "source_bundle_sha256": _sha256_file(inputs / "source-bundle.md"),
        }
    )
    task_matrix: list[dict[str, Any]] = []
    for fixture in fixtures:
        fixture_id = str(fixture.get("id") or "")
        if not fixture_id:
            raise ValueError("Every fixture requires id.")
        prompt = str(fixture.get("prompt") or "")
        if not prompt:
            raise ValueError(f"Fixture {fixture_id} requires prompt.")
        fixture_digest = displayed_content_digest(
            json.dumps(fixture, sort_keys=True, separators=(",", ":"))
        )
        shared = {
            "experiment_id": experiment_id,
            "task_id": fixture_id,
            "fixture_family": str(fixture.get("fixture_family") or "unspecified"),
            "fixture_digest": fixture_digest,
            "pattern_id": "composition.source-bundle-inclusion",
            "tested_atom": "materialized_source_bundle",
            "intervention_target": "source_bundle",
            "intervention_variant": "packet_plus_explore",
            "control_variant": "packet_only",
            "claim_granularity": "source_bundle_delivery",
            "expected_effect_direction": "positive",
            "pattern_intervention_contract": pattern_contract,
            "skill_path": "tmcp://composition/explore-unknowns-stage-1",
            "skill_digest": base_digest,
            "prompt": prompt,
            "expected_observables": list(fixture["expected_observables"]),
            "failure_smells": list(fixture["failure_smells"]),
        }
        common_provenance = {
            "schema": "tmcp-composition-source-bundle-v0.1",
            "delivery_mode": "materialized_packet_attachment",
            "packet_sha256": str(definition["packet_sha256"]),
            "receipt_sha256": str(definition["receipt_sha256"]),
            "task_evidence_bundle_sha256": displayed_content_digest(prompt),
            "base_attachment_sha256": base_digest,
        }
        task_matrix.extend(
            (
                {
                    **shared,
                    "matrix_row_id": f"{fixture_id}-packet-only",
                    "contrast_id": f"{fixture_id}-source-bundle",
                    "variant_id": "packet_only",
                    "ablation_section": None,
                    "intervention": {"kind": "control"},
                    "skill_attachment": base_attachment,
                    "composition_provenance": {
                        **common_provenance,
                        "packet_id": str(definition["packet_id"]),
                        "attachment_sha256": base_digest,
                        "source_bundle_sha256": displayed_content_digest(""),
                        "source_bundle_text": "",
                        "selected_sources": [],
                    },
                },
                {
                    **shared,
                    "matrix_row_id": f"{fixture_id}-packet-plus-explore",
                    "contrast_id": f"{fixture_id}-source-bundle",
                    "variant_id": "packet_plus_explore",
                    "ablation_section": None,
                    "intervention": {
                        "kind": "source_bundle_inclusion",
                        "target": "source_bundle",
                        "causal_attribution": True,
                    },
                    "skill_attachment": treatment_attachment,
                    "composition_provenance": {
                        **common_provenance,
                        "packet_id": str(definition["packet_id"]),
                        "attachment_sha256": displayed_content_digest(
                            treatment_attachment
                        ),
                        "source_bundle_sha256": source_bundle_digest,
                        "source_bundle_text": source_bundle,
                        "selected_sources": source_entries,
                    },
                },
            )
        )
    plan = {
        "schema": "tmcp-skill-evaluation-plan-v0.2",
        "experiment": {
            "experiment_id": experiment_id,
            "campaign_policy": policy,
            "cost_rejudge_policy": cost_rejudge_policy,
            "analysis_policy": definition["analysis_policy"],
            "promotion_thresholds": definition["promotion_thresholds"],
            "study_scope": definition["study_scope"],
            "source_study_binding": source_study_binding,
        },
        "evaluated_skills": [],
        "task_matrix": task_matrix,
        "observable_behavior_contract": [],
        "packet_inclusion_contracts": [],
    }
    validate_cost_rejudge_policy(study_dir, cost_rejudge_policy, plan)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build_plan(args.study_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
