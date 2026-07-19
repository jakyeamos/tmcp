from __future__ import annotations

import ast
import copy
import inspect
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.plan_composition_lift_campaign import plan_campaign
from scripts.schema_contract_support import assert_matches_schema
from tests.test_tmcp_composition_benchmark_protocol import _semantic_proposal_bundle
from tmcp_runtime.domain.composition_benchmark_manifests import variant_skill_order
from tmcp_runtime.domain.composition_benchmark_protocol import (
    build_benchmark_preparation,
)
from tmcp_runtime.domain.composition_benchmark_replay import (
    build_benchmark_control_plan,
)
from tmcp_runtime.domain.composition_lift_campaign import (
    BASELINE_CONFIGURATION_SLOTS,
    REPLICATE_INDICES,
    build_composition_lift_campaign,
    validate_composition_lift_campaign,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
import tmcp_runtime.domain.composition_lift_campaign as lift_campaign
import tmcp_runtime.domain.composition_lift_campaign_support as lift_campaign_support


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCHEMAS = ROOT / "schemas"


def _payload(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{name} must be an object")
    return payload


def _refresh_control_plan_identity(control_plan: dict[str, object]) -> None:
    identity = {
        key: value
        for key, value in control_plan.items()
        if key not in {"control_plan_id", "control_plan_digest"}
    }
    control_plan["control_plan_digest"] = stable_digest(identity)
    control_plan["control_plan_id"] = "benchmark-control-" + stable_digest(identity, 20)


def _refresh_campaign_identity(campaign: dict[str, object]) -> None:
    identity = {
        key: value
        for key, value in campaign.items()
        if key not in {"campaign_id", "campaign_digest"}
    }
    campaign["campaign_digest"] = stable_digest(identity)
    campaign["campaign_id"] = "composition-lift-campaign-" + stable_digest(identity, 20)


class CompositionLiftCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routing = _payload("composition_routing_golden_v0_6.json")
        cls.behavioral = _payload("composition_behavioral_fixtures_v0_6.json")
        cls.run_plan, _artifacts = build_benchmark_preparation(
            routing_golden=cls.routing,
            behavioral_fixtures=cls.behavioral,
        )
        cls.semantic_proposals = _semantic_proposal_bundle(
            cls.run_plan, cls.routing, cls.behavioral
        )
        cls.control_plan = build_benchmark_control_plan(
            run_plan=cls.run_plan,
            semantic_proposals=cls.semantic_proposals,
            routing_golden=cls.routing,
            behavioral_fixtures=cls.behavioral,
        )

    def test_campaign_derives_the_preregistered_factorial_and_schema(self) -> None:
        campaign = build_composition_lift_campaign(self.control_plan)
        assert_matches_schema(
            campaign,
            SCHEMAS / "tmcp-composition-lift-campaign-v0.1.schema.json",
        )

        self.assertEqual(campaign["campaign_mode"], "pilot_only")
        self.assertFalse(campaign["model_calls_authorized"])
        self.assertFalse(campaign["automatic_tool_execution"])
        self.assertEqual(campaign["receipt_persistence"], "not_performed")
        self.assertEqual(campaign["causal_claim_status"], "not_evaluated")
        self.assertEqual(
            campaign["counts"],
            {
                "block_count": 5,
                "baseline_cell_count": 180,
                "causal_cell_count": 360,
                "baseline_runner_cell_count": 180,
                "baseline_blind_judge_cell_count": 180,
                "causal_runner_cell_count": 360,
                "causal_blind_judge_cell_count": 360,
            },
        )
        self.assertEqual(len(campaign["blocks"]), 5)

        controls_by_fixture = {
            control["fixture_id"]: control
            for control in self.control_plan["behavioral_controls"]
        }
        for block in campaign["blocks"]:
            control = controls_by_fixture[block["fixture_id"]]
            selected = list(control["selected_skill_ids"])
            all_variants = [variant["variant_id"] for variant in control["variants"]]
            baseline_variants = [
                "no_skill",
                "naive_union",
                *(f"singleton:{skill_id}" for skill_id in selected),
            ]
            self.assertEqual(len(block["baseline_cells"]), 36)
            self.assertEqual(len(block["causal_cells"]), 72)
            self.assertEqual(
                Counter(
                    cell["binding"]["variant_id"] for cell in block["baseline_cells"]
                ),
                Counter({variant_id: 6 for variant_id in baseline_variants}),
            )
            self.assertEqual(
                Counter(
                    cell["binding"]["variant_id"] for cell in block["causal_cells"]
                ),
                Counter({variant_id: 6 for variant_id in all_variants}),
            )
            for cells in (block["baseline_cells"], block["causal_cells"]):
                for cell in cells:
                    binding = cell["binding"]
                    self.assertEqual(binding["fixture_id"], block["fixture_id"])
                    self.assertEqual(binding["request_id"], block["request_id"])
                    self.assertEqual(binding["selected_skill_ids"], selected)
                    self.assertEqual(
                        binding["ordered_skill_ids"],
                        variant_skill_order(binding["variant_id"], selected),
                    )
                    self.assertIn(
                        cell["configuration_slot"], BASELINE_CONFIGURATION_SLOTS
                    )
                    self.assertIn(cell["replicate_index"], REPLICATE_INDICES)
                    self.assertEqual(
                        binding["quality_rubric_digest"],
                        block["quality_rubric_digest"],
                    )
                    self.assertEqual(
                        binding["source_control_plan_id"],
                        campaign["source_control_plan"]["control_plan_id"],
                    )
                    self.assertEqual(
                        binding["source_control_plan_digest"],
                        campaign["source_control_plan"]["control_plan_digest"],
                    )
                    self.assertEqual(
                        binding["source_run_manifest_id"],
                        campaign["source_control_plan"]["run_manifest_id"],
                    )
                    self.assertEqual(
                        binding["source_run_manifest_digest"],
                        campaign["source_control_plan"]["run_manifest_digest"],
                    )
                    self.assertRegex(
                        cell["runner_cell_id"],
                        r"^composition-lift-runner-[a-f0-9]{20}$",
                    )
                    self.assertRegex(
                        cell["blind_judge_cell_id"],
                        r"^composition-lift-judge-[a-f0-9]{20}$",
                    )
                    self.assertNotIn("runner_cell", cell)
                    self.assertNotIn("blind_judge_cell", cell)
            all_cells = [*block["baseline_cells"], *block["causal_cells"]]
            self.assertEqual(len(block["runner_dispatches"]), len(all_cells))
            self.assertEqual(len(block["blind_judge_dispatches"]), len(all_cells))
            self.assertEqual(
                {item["runner_cell_id"] for item in block["runner_dispatches"]},
                {cell["runner_cell_id"] for cell in all_cells},
            )
            self.assertEqual(
                {
                    item["blind_judge_cell_id"]
                    for item in block["blind_judge_dispatches"]
                },
                {cell["blind_judge_cell_id"] for cell in all_cells},
            )
            self.assertTrue(
                all(
                    cell["comparator_cell_id"] != cell["cell_id"]
                    for cell in block["causal_cells"]
                )
            )
            baseline_by_signature = {
                (
                    cell["binding"]["variant_id"],
                    cell["configuration_slot"],
                    cell["replicate_index"],
                ): cell["cell_id"]
                for cell in block["baseline_cells"]
            }
            causal_by_signature = {
                (
                    cell["binding"]["variant_id"],
                    cell["configuration_slot"],
                    cell["replicate_index"],
                ): cell["cell_id"]
                for cell in block["causal_cells"]
            }
            for cell in block["causal_cells"]:
                signature = (
                    cell["binding"]["variant_id"],
                    cell["configuration_slot"],
                    cell["replicate_index"],
                )
                variant_id = signature[0]
                if variant_id == "full_composition":
                    expected = causal_by_signature[("naive_union", *signature[1:])]
                elif variant_id == "wrong_order" or variant_id.startswith(
                    "leave_one_out:"
                ):
                    expected = causal_by_signature[("full_composition", *signature[1:])]
                else:
                    expected = baseline_by_signature[signature]
                self.assertEqual(cell["comparator_cell_id"], expected)

    def test_dispatch_views_are_opaque_blind_and_cover_each_controller_once(
        self,
    ) -> None:
        campaign = build_composition_lift_campaign(self.control_plan)
        for block in campaign["blocks"]:
            runners = block["runner_dispatches"]
            judges = block["blind_judge_dispatches"]
            for runner in runners:
                self.assertEqual(
                    set(runner),
                    {
                        "schema",
                        "runner_cell_id",
                        "execution_input_ref",
                        "instruction",
                        "instruction_digest",
                    },
                )
                self.assertEqual(
                    runner["schema"],
                    "tmcp-composition-lift-runner-dispatch-v0.1",
                )
                lift_campaign_support._assert_label_free(
                    runner, field="test.runner_dispatch"
                )
            for judge in judges:
                self.assertEqual(
                    set(judge),
                    {
                        "schema",
                        "blind_judge_cell_id",
                        "artifact_slot_id",
                        "quality_rubric",
                        "quality_rubric_digest",
                        "instruction",
                        "instruction_digest",
                    },
                )
                self.assertEqual(
                    judge["schema"],
                    "tmcp-composition-lift-blind-judge-dispatch-v0.1",
                )
                self.assertEqual(judge["quality_rubric"], block["quality_rubric"])
                self.assertEqual(
                    judge["quality_rubric_digest"], block["quality_rubric_digest"]
                )
                lift_campaign_support._assert_label_free(
                    judge, field="test.judge_dispatch"
                )

    def test_control_plan_extension_carries_the_exact_fixture_rubric(self) -> None:
        fixtures_by_id = {
            fixture["fixture_id"]: fixture for fixture in self.behavioral["fixtures"]
        }
        for control in self.control_plan["behavioral_controls"]:
            rubric = fixtures_by_id[control["fixture_id"]]["quality_rubric"]
            self.assertEqual(control["quality_rubric"], rubric)
            self.assertEqual(control["quality_rubric_digest"], stable_digest(rubric))

    def test_planner_rejects_noncanonical_and_live_control_claims(self) -> None:
        non_four = copy.deepcopy(self.control_plan)
        control = non_four["behavioral_controls"][0]
        control["selected_skill_ids"].pop()
        control["ordered_skill_ids"].pop()
        _refresh_control_plan_identity(non_four)
        with self.assertRaisesRegex(ValueError, "exactly 4"):
            build_composition_lift_campaign(non_four)

        duplicate = copy.deepcopy(self.control_plan)
        control = duplicate["behavioral_controls"][0]
        control["selected_skill_ids"][-1] = control["selected_skill_ids"][-2]
        control["ordered_skill_ids"][-1] = control["ordered_skill_ids"][-2]
        _refresh_control_plan_identity(duplicate)
        with self.assertRaisesRegex(ValueError, "unique"):
            build_composition_lift_campaign(duplicate)

        reordered = copy.deepcopy(self.control_plan)
        reordered["behavioral_controls"][0]["ordered_skill_ids"].reverse()
        _refresh_control_plan_identity(reordered)
        with self.assertRaisesRegex(ValueError, "reordered"):
            build_composition_lift_campaign(reordered)

        recipe_drift = copy.deepcopy(self.control_plan)
        recipe_drift["behavioral_controls"][0]["variants"][0]["execution_recipe"][
            "graph_digest"
        ] = "0" * 32
        _refresh_control_plan_identity(recipe_drift)
        with self.assertRaisesRegex(ValueError, "recipe digest drifted"):
            build_composition_lift_campaign(recipe_drift)

        two_arm = copy.deepcopy(self.control_plan)
        two_arm["two_arm_claim"] = True
        _refresh_control_plan_identity(two_arm)
        with self.assertRaisesRegex(ValueError, "not allowed"):
            build_composition_lift_campaign(two_arm)

        source_bundle = copy.deepcopy(self.control_plan)
        source_bundle["source_bundle_claim"] = "forbidden"
        _refresh_control_plan_identity(source_bundle)
        with self.assertRaisesRegex(ValueError, "not allowed"):
            build_composition_lift_campaign(source_bundle)

        persistence = copy.deepcopy(self.control_plan)
        persistence["receipt_persistence"] = "performed"
        _refresh_control_plan_identity(persistence)
        with self.assertRaisesRegex(ValueError, "not persist"):
            build_composition_lift_campaign(persistence)

    def test_validator_rejects_rehashed_replaced_factorial_variant(self) -> None:
        campaign = build_composition_lift_campaign(self.control_plan)
        tampered = copy.deepcopy(campaign)
        causal = tampered["blocks"][0]["causal_cells"]
        replacement = next(
            cell
            for cell in causal
            if cell["binding"]["variant_id"] == "naive_union"
            and cell["configuration_slot"] == causal[0]["configuration_slot"]
            and cell["replicate_index"] == causal[0]["replicate_index"]
        )
        self.assertNotEqual(
            causal[0]["binding"]["variant_id"], replacement["binding"]["variant_id"]
        )
        causal[0] = copy.deepcopy(replacement)
        _refresh_campaign_identity(tampered)
        with self.assertRaisesRegex(ValueError, "factorial"):
            validate_composition_lift_campaign(tampered)

    def test_cli_requires_replay_bound_inputs_without_output_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            control_path = Path(temporary) / "benchmark-control-plan.json"
            run_plan_path = Path(temporary) / "benchmark-run-plan.json"
            semantic_path = Path(temporary) / "semantic-proposals.json"
            routing_path = Path(temporary) / "routing-golden.json"
            behavioral_path = Path(temporary) / "behavioral-fixtures.json"
            control_path.write_text(json.dumps(self.control_plan), encoding="utf-8")
            run_plan_path.write_text(json.dumps(self.run_plan), encoding="utf-8")
            semantic_path.write_text(
                json.dumps(self.semantic_proposals), encoding="utf-8"
            )
            routing_path.write_text(json.dumps(self.routing), encoding="utf-8")
            behavioral_path.write_text(json.dumps(self.behavioral), encoding="utf-8")
            campaign = plan_campaign(
                control_plan_path=control_path,
                run_plan_path=run_plan_path,
                semantic_proposals_path=semantic_path,
                routing_golden_path=routing_path,
                behavioral_fixtures_path=behavioral_path,
            )

        self.assertEqual(
            campaign["source_control_plan"]["control_plan_id"],
            self.control_plan["control_plan_id"],
        )
        self.assertFalse(campaign["model_calls_authorized"])

    def test_cli_rejects_a_self_digested_but_noncanonical_control_plan(self) -> None:
        tampered = copy.deepcopy(self.control_plan)
        tampered["routing_controls"].reverse()
        _refresh_control_plan_identity(tampered)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {
                "control": root / "benchmark-control-plan.json",
                "run_plan": root / "benchmark-run-plan.json",
                "semantic": root / "semantic-proposals.json",
                "routing": root / "routing-golden.json",
                "behavioral": root / "behavioral-fixtures.json",
            }
            paths["control"].write_text(json.dumps(tampered), encoding="utf-8")
            paths["run_plan"].write_text(json.dumps(self.run_plan), encoding="utf-8")
            paths["semantic"].write_text(
                json.dumps(self.semantic_proposals), encoding="utf-8"
            )
            paths["routing"].write_text(json.dumps(self.routing), encoding="utf-8")
            paths["behavioral"].write_text(
                json.dumps(self.behavioral), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "does not match"):
                plan_campaign(
                    control_plan_path=paths["control"],
                    run_plan_path=paths["run_plan"],
                    semantic_proposals_path=paths["semantic"],
                    routing_golden_path=paths["routing"],
                    behavioral_fixtures_path=paths["behavioral"],
                )

    def test_domain_module_is_pure_and_has_no_io_or_runtime_imports(self) -> None:
        forbidden = (
            "json",
            "os",
            "pathlib",
            "subprocess",
            "tmcp_runtime.services",
            "tmcp_runtime.storage",
            "tmcp_runtime.adapters",
        )
        for module in (lift_campaign, lift_campaign_support):
            source_path = Path(inspect.getfile(module))
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            imports = {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            imports.update(
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            self.assertTrue(
                all(
                    not imported.startswith(prefix)
                    for imported in imports
                    for prefix in forbidden
                )
            )


if __name__ == "__main__":
    unittest.main()
