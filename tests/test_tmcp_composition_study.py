from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.generate_composition_study_plan import build_plan
from scripts.tmcp_skill_eval_campaign import _verify_source_bundle_study
from scripts.verify_composition_study import verify_study
from scripts.tmcp_skill_eval_campaign_protocol import build_cells
from tmcp_runtime.api.evaluation import validate_evaluation_plan
from tmcp_runtime.services.evaluation_evidence import analyze_pattern_evidence
from tmcp_runtime.services.evaluation_plan import displayed_content_digest


PATTERN_ID = "composition.source-bundle-inclusion"
INTERVENTION_TARGET = "source_bundle"
CONTROL_VARIANT = "packet_only"
INTERVENTION_VARIANT = "packet_plus_explore"
CONFIGURATIONS = (
    ("runner-a", "high"),
    ("runner-b", "high"),
    ("runner-c", "high"),
)
STUDY_DIR_NAME = "composition-explore-unknowns-v1" + "-2026-07-17"
STUDY_DIR = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / STUDY_DIR_NAME
)


def _policy() -> dict:
    return {
        "schema": "tmcp-skill-eval-campaign-policy-v0.1",
        "design": "causal_contrast",
        "runner_configurations": [
            {"model": model, "reasoning_effort": effort}
            for model, effort in CONFIGURATIONS
        ],
        "baseline_reliability": {
            "control_variant": CONTROL_VARIANT,
            "minimum_control_pass_rate": 0.5,
            "minimum_per_fixture_control_pass_rate": 0.5,
            "require_predeclared_clustered_interval": True,
        },
        "fixture_review": {
            "independent_reviewer": True,
            "prompt_event_directness": True,
            "bar_skill_expressibility": True,
        },
        "judge_configuration": {"model": "judge-model", "reasoning_effort": "high"},
        "cross_model_confirmation": {
            "required": True,
            "minimum_distinct_runner_models": 3,
            "minimum_fixture_count_per_model": 6,
            "minimum_repetitions_per_cell": 2,
            "require_directional_replication": True,
        },
    }


def _provenance(
    attachment: str,
    *,
    source_bundle_text: str,
    selected_sources: list[dict[str, str]],
    packet_id: str,
) -> dict:
    return {
        "schema": "tmcp-composition-source-bundle-v0.1",
        "delivery_mode": "materialized_packet_attachment",
        "packet_id": packet_id,
        "packet_sha256": "sha256:packet",
        "receipt_sha256": "sha256:receipt",
        "task_evidence_bundle_sha256": "sha256:task-evidence",
        "base_attachment_sha256": displayed_content_digest("Use the shared packet."),
        "attachment_sha256": displayed_content_digest(attachment),
        "source_bundle_sha256": displayed_content_digest(source_bundle_text),
        "source_bundle_text": source_bundle_text,
        "selected_sources": selected_sources,
    }


def composition_plan() -> dict:
    base_attachment = "Use the shared packet."
    source_bundle = "Use stage one: state known knowns and stop for the user."
    intervention_attachment = f"{base_attachment}\n\n{source_bundle}"
    contract = {
        "tested_atom": "materialized_source_bundle",
        "allowed_targets": [INTERVENTION_TARGET],
        "allowed_kinds": ["source_bundle_inclusion"],
        "claim_granularity": "source_bundle_delivery",
        "expected_support_direction": "positive",
    }
    rows: list[dict] = []
    for index in range(6):
        shared = {
            "experiment_id": "composition-study-test",
            "task_id": f"fixture-{index}",
            "fixture_family": f"family-{index % 3}",
            "fixture_digest": f"sha256:fixture-{index}",
            "pattern_id": PATTERN_ID,
            "tested_atom": "materialized_source_bundle",
            "intervention_target": INTERVENTION_TARGET,
            "intervention_variant": INTERVENTION_VARIANT,
            "control_variant": CONTROL_VARIANT,
            "claim_granularity": "source_bundle_delivery",
            "expected_effect_direction": "positive",
            "pattern_intervention_contract": contract,
            "skill_path": "tmcp://composition/explore-unknowns",
            "skill_digest": displayed_content_digest(base_attachment),
            "prompt": f"Use the supplied evidence packet for fixture {index}.",
            "expected_observables": ["The stage-one response is evidence-grounded."],
            "failure_smells": ["claims a durable result without evidence"],
        }
        rows.extend(
            (
                {
                    **shared,
                    "matrix_row_id": f"row-{index}-control",
                    "contrast_id": f"contrast-{index}",
                    "variant_id": CONTROL_VARIANT,
                    "ablation_section": None,
                    "intervention": {"kind": "control"},
                    "skill_attachment": base_attachment,
                    "composition_provenance": _provenance(
                        base_attachment,
                        source_bundle_text="",
                        selected_sources=[],
                        packet_id=f"packet-{index}",
                    ),
                },
                {
                    **shared,
                    "matrix_row_id": f"row-{index}-intervention",
                    "contrast_id": f"contrast-{index}",
                    "variant_id": INTERVENTION_VARIANT,
                    "ablation_section": None,
                    "intervention": {
                        "kind": "source_bundle_inclusion",
                        "target": INTERVENTION_TARGET,
                        "causal_attribution": True,
                    },
                    "skill_attachment": intervention_attachment,
                    "composition_provenance": _provenance(
                        intervention_attachment,
                        source_bundle_text=source_bundle,
                        selected_sources=[
                            {
                                "path": "skills/explore-unknowns/SKILL.md",
                                "sha256": "sha256:skill",
                            },
                            {
                                "path": "skills/explore-unknowns/references/stage-1-known-knowns.md",
                                "sha256": "sha256:stage-1",
                            },
                        ],
                        packet_id=f"packet-{index}",
                    ),
                },
            )
        )
    return {
        "schema": "tmcp-skill-evaluation-plan-v0.2",
        "experiment": {
            "experiment_id": "composition-study-test",
            "campaign_policy": _policy(),
            "analysis_policy": {
                "clustered_interval": {
                    "method": "fixture_block_bootstrap_by_configuration",
                    "confidence": 0.95,
                    "cluster_unit": "fixture_digest",
                    "resamples": 10000,
                    "seed": 7,
                }
            },
        },
        "evaluated_skills": [],
        "task_matrix": rows,
        "observable_behavior_contract": [],
        "packet_inclusion_contracts": [],
    }


def controlled_traces(plan: dict) -> list[dict]:
    traces: list[dict] = []
    for row in plan["task_matrix"]:
        for model, _ in CONFIGURATIONS:
            for replicate in range(1, 3):
                control_pass = replicate == 2
                passed = (
                    True
                    if row["variant_id"] == INTERVENTION_VARIANT
                    else control_pass
                )
                traces.append(
                    {
                        "schema": "tmcp-skill-eval-trace-v0.1",
                        "trace_id": (
                            f"trace-{row['matrix_row_id']}-{model}-replicate-{replicate}"
                        ),
                        "experiment_id": "composition-study-test",
                        "matrix_row_id": row["matrix_row_id"],
                        "replicate_id": f"replicate-{replicate}",
                        "task_id": row["task_id"],
                        "variant_id": row["variant_id"],
                        "agent": {
                            "name": "codex-cli-blind-runner",
                            "model": model,
                            "configuration_id": f"{model}-reasoning-high",
                        },
                        "provenance": {
                            "runner_blinded": True,
                            "judge_blinded": True,
                            "isolated_session": True,
                            "composition_provenance": row["composition_provenance"],
                        },
                        "observations": [
                            {"kind": "assistant_message", "value": "artifact"}
                        ],
                        "case_verdict": {
                            "passed": passed,
                            "evidence": [{"criterion": "O1", "status": "pass"}],
                            "safety_regression": False,
                            "cost_regression": False,
                        },
                    }
                )
    return traces


class CompositionStudyTests(unittest.TestCase):
    def test_source_bundle_plan_is_valid_and_builds_a_72_cell_campaign(self) -> None:
        plan = composition_plan()

        validated = validate_evaluation_plan(plan)
        cells = build_cells(
            validated,
            pattern_id=PATTERN_ID,
            intervention_target=INTERVENTION_TARGET,
            model="fallback",
            runner_efforts=[],
            runner_configurations=list(CONFIGURATIONS),
            design="causal_contrast",
            repetitions=2,
            expected_fixtures=6,
            seed=7,
            codex_version="codex-test",
        )

        self.assertEqual(len(cells), 72)
        self.assertEqual(
            {cell.variant_id for cell in cells},
            {CONTROL_VARIANT, INTERVENTION_VARIANT},
        )

    def test_source_bundle_plan_rejects_any_unpinned_attachment_delta(self) -> None:
        plan = composition_plan()
        intervention = next(
            row
            for row in plan["task_matrix"]
            if row["variant_id"] == INTERVENTION_VARIANT
        )
        intervention["skill_attachment"] += "\nUnpinned instruction."

        with self.assertRaisesRegex(ValueError, "attachment digest"):
            validate_evaluation_plan(plan)

    def test_source_bundle_plan_rejects_packet_provenance_delta(self) -> None:
        plan = composition_plan()
        intervention = next(
            row
            for row in plan["task_matrix"]
            if row["variant_id"] == INTERVENTION_VARIANT
        )
        intervention["composition_provenance"]["packet_id"] = "packet-other"

        with self.assertRaisesRegex(ValueError, "packet_id"):
            validate_evaluation_plan(plan)

    def test_source_bundle_effect_is_causally_attributable_after_provenance_binding(
        self,
    ) -> None:
        plan = validate_evaluation_plan(composition_plan())

        claims = analyze_pattern_evidence(plan, controlled_traces(plan))

        self.assertEqual(len(claims), 1)
        self.assertTrue(claims[0]["causal_contrast_valid"])
        self.assertEqual(
            claims[0]["claim_granularity"], "source_bundle_delivery"
        )

    def test_preregistered_cost_rejudge_is_required_before_promotion(self) -> None:
        plan = composition_plan()
        plan["experiment"]["cost_rejudge_policy"] = {
            "expected_trace_count": 72,
            "complete_before_promotion": True,
        }
        plan = validate_evaluation_plan(plan)
        traces = controlled_traces(plan)

        without_sidecar = analyze_pattern_evidence(plan, traces)[0]
        self.assertEqual(
            without_sidecar["cost_rejudge_requirement"]["status"], "missing"
        )
        self.assertIn(
            "predeclared cost rejudge sidecar is missing",
            without_sidecar["promotion_gaps"],
        )

        with_sidecar = analyze_pattern_evidence(
            plan,
            traces,
            cost_rejudgments={str(trace["trace_id"]): False for trace in traces},
        )[0]
        self.assertEqual(
            with_sidecar["cost_rejudge_requirement"]["status"], "complete"
        )
        self.assertNotIn(
            "predeclared cost rejudge sidecar is missing",
            with_sidecar["promotion_gaps"],
        )

        incomplete_source = traces[:-1]
        with_incomplete_source = analyze_pattern_evidence(
            plan,
            incomplete_source,
            cost_rejudgments={
                str(trace["trace_id"]): False for trace in incomplete_source
            },
        )[0]
        self.assertEqual(
            with_incomplete_source["cost_rejudge_requirement"]["status"],
            "incomplete_source_traces",
        )
        self.assertIn(
            "predeclared cost rejudge sidecar is incomplete",
            with_incomplete_source["promotion_gaps"],
        )

    def test_source_bundle_trace_with_mismatched_provenance_is_excluded(self) -> None:
        plan = validate_evaluation_plan(composition_plan())
        traces = controlled_traces(plan)
        traces[0]["provenance"]["composition_provenance"] = {"tampered": True}

        claims = analyze_pattern_evidence(plan, traces)

        self.assertEqual(claims[0]["excluded_controlled_trace_count"], 1)
        self.assertIn(
            {
                "reason": "provenance.composition_provenance does not match matrix row",
                "count": 1,
            },
            claims[0]["controlled_exclusion_reasons"],
        )

    def test_checked_in_study_plan_is_reproducible_and_valid(self) -> None:
        if not STUDY_DIR.is_dir():
            self.skipTest("source-only composition study evidence is not packaged")
        generated = build_plan(STUDY_DIR)
        checked_in = json.loads(
            (
                STUDY_DIR / "generated" / "tmcp-composition-study-plan.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(generated, checked_in)
        validated = validate_evaluation_plan(generated)
        self.assertEqual(
            validated["experiment"]["experiment_id"],
            "composition-study-2b35bb34abeb431f",
        )
        self.assertEqual(len(validated["task_matrix"]), 12)
        self.assertEqual(
            validated["experiment"]["cost_rejudge_policy"]["expected_trace_count"],
            72,
        )

    def test_study_verifier_binds_inputs_and_live_sources(self) -> None:
        if not STUDY_DIR.is_dir():
            self.skipTest("source-only composition study evidence is not packaged")

        report = verify_study(STUDY_DIR, check_live_sources=True)

        self.assertTrue(report["static"]["plan_matches_generated"])
        self.assertEqual(report["live_sources"]["status"], "matched")
        self.assertEqual(report["static"]["cost_rejudge"]["expected_trace_count"], 72)
        self.assertEqual(report["static"]["cost_rejudge"]["model"], "gpt-5.6-sol")

    def test_study_input_drift_rejects_regeneration(self) -> None:
        if not STUDY_DIR.is_dir():
            self.skipTest("source-only composition study evidence is not packaged")
        with tempfile.TemporaryDirectory() as temporary:
            copied_study = Path(temporary) / "study"
            shutil.copytree(STUDY_DIR, copied_study)
            (copied_study / "inputs" / "first-principles.txt").write_text(
                "tampered first principles\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "first-principles.txt"):
                build_plan(copied_study)

    def test_source_bundle_campaign_rejects_other_first_principles(self) -> None:
        if not STUDY_DIR.is_dir():
            self.skipTest("source-only composition study evidence is not packaged")
        plan = json.loads(
            (STUDY_DIR / "generated" / "tmcp-composition-study-plan.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            other = Path(temporary) / "other-first-principles.txt"
            other.write_text("different first principles\n", encoding="utf-8")
            args = Namespace(
                composition_study_dir=STUDY_DIR,
                plan=STUDY_DIR / "generated" / "tmcp-composition-study-plan.json",
                intervention_target="source_bundle",
                first_principles_source={"kind": "file", "path": str(other)},
            )

            with self.assertRaisesRegex(ValueError, "first-principles file"):
                _verify_source_bundle_study(args, plan)


if __name__ == "__main__":
    unittest.main()
