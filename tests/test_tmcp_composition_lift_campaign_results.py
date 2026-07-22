from __future__ import annotations

import ast
import copy
import inspect
import json
import unittest
from pathlib import Path

from scripts.check_install import REQUIRED_FILES
from scripts.release_package_compile import COMPILE_PATHS
from scripts.schema_contract_support import assert_matches_schema
from tests.test_tmcp_composition_benchmark_protocol import _semantic_proposal_bundle
from tmcp_runtime.domain.composition_benchmark_protocol import (
    build_benchmark_preparation,
)
from tmcp_runtime.domain.composition_benchmark_replay import (
    build_benchmark_control_plan,
)
from tmcp_runtime.domain.composition_lift_campaign import (
    build_composition_lift_campaign,
)
from tmcp_runtime.domain.composition_lift_campaign_results import (
    build_campaign_dispatch_bundle,
    validate_campaign_evaluator_artifacts,
    validate_campaign_host_results,
)
from tmcp_runtime.domain.composition_lift_campaign_scoring import (
    score_composition_lift_campaign,
)
from tmcp_runtime.domain.composition_preflight import stable_digest


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCHEMAS = ROOT / "schemas"


def _payload(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{name} must contain an object")
    return payload


def _campaign() -> dict[str, object]:
    routing = _payload("composition_routing_golden_v0_6.json")
    behavioral = _payload("composition_behavioral_fixtures_v0_6.json")
    run_plan, _artifacts = build_benchmark_preparation(
        routing_golden=routing,
        behavioral_fixtures=behavioral,
    )
    proposals = _semantic_proposal_bundle(run_plan, routing, behavioral)
    control_plan = build_benchmark_control_plan(
        run_plan=run_plan,
        semantic_proposals=proposals,
        routing_golden=routing,
        behavioral_fixtures=behavioral,
    )
    return build_composition_lift_campaign(control_plan)


def _results(
    campaign: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    source = campaign["source_control_plan"]
    if not isinstance(source, dict):
        raise AssertionError("campaign source control plan is missing")
    host_blocks: list[dict[str, object]] = []
    evaluator_blocks: list[dict[str, object]] = []
    for block in campaign["blocks"]:
        all_cells = [*block["baseline_cells"], *block["causal_cells"]]
        host_cells: list[dict[str, object]] = []
        evaluator_cells: list[dict[str, object]] = []
        for cell in all_cells:
            runner = next(
                item
                for item in block["runner_dispatches"]
                if item["runner_cell_id"] == cell["runner_cell_id"]
            )
            judge = next(
                item
                for item in block["blind_judge_dispatches"]
                if item["blind_judge_cell_id"] == cell["blind_judge_cell_id"]
            )
            variant_id = cell["binding"]["variant_id"]
            if variant_id == "full_composition":
                quality = 0.9
            elif variant_id.startswith("singleton:"):
                quality = 0.7
            elif variant_id == "naive_union":
                quality = 0.8
            elif variant_id == "wrong_order":
                quality = 0.75
            elif variant_id.startswith("leave_one_out:"):
                quality = 0.85
            else:
                quality = 0.3
            artifact = f"artifact for {cell['cell_id']}"
            host_cells.append(
                {
                    "cell_id": cell["cell_id"],
                    "runner_cell_id": cell["runner_cell_id"],
                    "blind_judge_cell_id": cell["blind_judge_cell_id"],
                    "execution_input_ref": runner["execution_input_ref"],
                    "runner_dispatch_digest": stable_digest(runner),
                    "configuration_slot": cell["configuration_slot"],
                    "replicate_index": cell["replicate_index"],
                    "run_id": f"run-{cell['cell_id']}",
                    "outcome": "passed",
                    "artifact": artifact,
                    "evidence": [
                        {"media_type": "text/plain", "content": "verified artifact"}
                    ],
                }
            )
            evidence_id = f"evidence-{cell['cell_id']}"
            dimensions = {
                item["dimension_id"] for item in block["quality_rubric"]["dimensions"]
            }
            evaluator_cells.append(
                {
                    "cell_id": cell["cell_id"],
                    "blind_judge_cell_id": cell["blind_judge_cell_id"],
                    "artifact_slot_id": judge["artifact_slot_id"],
                    "blind_judge_dispatch_digest": stable_digest(judge),
                    "configuration_slot": cell["configuration_slot"],
                    "replicate_index": cell["replicate_index"],
                    "execution_artifact_digest": stable_digest(artifact),
                    "dimension_scores": {
                        dimension: quality for dimension in dimensions
                    },
                    "evidence": [
                        {
                            "evidence_id": evidence_id,
                            "media_type": "text/plain",
                            "content": "judge evidence",
                        }
                    ],
                    "dimension_evidence": {
                        dimension: [
                            {
                                "requirement": "fixture requirement",
                                "evidence_ids": [evidence_id],
                                "claim": "artifact meets the rubric dimension",
                            }
                        ]
                        for dimension in dimensions
                    },
                }
            )
        host_blocks.append(
            {
                "block_id": block["block_id"],
                "fixture_id": block["fixture_id"],
                "cells": host_cells,
            }
        )
        evaluator_blocks.append(
            {
                "block_id": block["block_id"],
                "fixture_id": block["fixture_id"],
                "cells": evaluator_cells,
            }
        )
    host = {
        "schema": "tmcp-composition-lift-host-results-v0.1",
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": campaign["campaign_digest"],
        "source_control_plan": source,
        "evidence_class": "synthetic_test",
        "blocks": host_blocks,
    }
    evaluator = {
        "schema": "tmcp-composition-lift-evaluator-artifacts-v0.1",
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": campaign["campaign_digest"],
        "source_control_plan": source,
        "evaluator_execution": {
            "execution_class": "synthetic_test",
            "executor_id": "unit-test-evaluator",
            "execution_id": "unit-test-execution",
            "executed_at": "2026-07-19T00:00:00Z",
        },
        "blocks": evaluator_blocks,
    }
    return host, evaluator


class CompositionLiftCampaignResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.campaign = _campaign()
        cls.host, cls.evaluator = _results(cls.campaign)

    def test_cell_contracts_cover_the_factorial_and_validate_schema(self) -> None:
        assert_matches_schema(
            self.host,
            SCHEMAS / "tmcp-composition-lift-host-results-v0.1.schema.json",
        )
        assert_matches_schema(
            self.evaluator,
            SCHEMAS / "tmcp-composition-lift-evaluator-artifacts-v0.1.schema.json",
        )
        host_cells = validate_campaign_host_results(self.campaign, self.host)
        evaluator_cells = validate_campaign_evaluator_artifacts(
            self.campaign,
            self.evaluator,
            host_cells,
        )
        self.assertEqual(len(host_cells), 540)
        self.assertEqual(len(evaluator_cells), 540)

    def test_repeated_cell_lift_uses_matched_slot_and_replicate_pairs(self) -> None:
        summary = score_composition_lift_campaign(
            self.campaign,
            self.host,
            self.evaluator,
        )
        assert_matches_schema(
            summary, SCHEMAS / "tmcp-composition-lift-summary-v0.1.schema.json"
        )
        self.assertFalse(summary["eligible"])
        self.assertEqual(
            summary["failed_checks"],
            ["host_executed", "trusted_evaluator_execution"],
        )
        self.assertEqual(
            summary["quality_metrics"],
            {
                "synergy_lift": 0.2,
                "compiler_lift": 0.1,
                "order_lift": 0.15,
            },
        )
        self.assertEqual(
            summary["cell_counts"], {"baseline": 180, "causal": 360, "total": 540}
        )
        self.assertTrue(
            all(item["paired_replicate_count"] == 6 for item in summary["fixtures"])
        )

    def test_host_dispatch_tampering_is_rejected(self) -> None:
        tampered = copy.deepcopy(self.host)
        tampered["blocks"][0]["cells"][0]["runner_dispatch_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "runner_dispatch_digest"):
            validate_campaign_host_results(self.campaign, tampered)

    def test_evaluator_artifacts_must_match_host_output_digest(self) -> None:
        host_cells = validate_campaign_host_results(self.campaign, self.host)
        tampered = copy.deepcopy(self.evaluator)
        tampered["blocks"][0]["cells"][0]["execution_artifact_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "execution_artifact_digest"):
            validate_campaign_evaluator_artifacts(self.campaign, tampered, host_cells)

    def test_cell_results_cannot_cross_fixture_blocks(self) -> None:
        tampered = copy.deepcopy(self.host)
        first = tampered["blocks"][0]["cells"][0]
        second = tampered["blocks"][1]["cells"][0]
        tampered["blocks"][0]["cells"][0] = second
        tampered["blocks"][1]["cells"][0] = first
        with self.assertRaisesRegex(ValueError, "wrong campaign block"):
            validate_campaign_host_results(self.campaign, tampered)

    def test_domain_module_has_no_io_or_runtime_side_effect_imports(self) -> None:
        forbidden = (
            "json",
            "os",
            "pathlib",
            "subprocess",
            "tmcp_runtime.services",
            "tmcp_runtime.storage",
        )
        for module_name in (
            "tmcp_runtime.domain.composition_lift_campaign_results",
            "tmcp_runtime.domain.composition_lift_campaign_scoring",
        ):
            module = __import__(module_name, fromlist=["*"])
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

    def test_cell_contract_surface_is_installed_and_compiled(self) -> None:
        for path in (
            "schemas/tmcp-composition-lift-host-results-v0.1.schema.json",
            "schemas/tmcp-composition-lift-evaluator-artifacts-v0.1.schema.json",
            "schemas/tmcp-composition-lift-rejudge-envelope-v0.1.schema.json",
            "schemas/tmcp-composition-lift-summary-v0.1.schema.json",
            "schemas/tmcp-composition-lift-dispatch-bundle-v0.1.schema.json",
            "schemas/tmcp-guidebook-promotion-candidate-v0.1.schema.json",
        ):
            self.assertIn(path, REQUIRED_FILES)
        for path in (
            "scripts/score_composition_lift_campaign.py",
            "scripts/promote_guidebook_from_campaign.py",
            "tmcp_runtime/domain/composition_lift_campaign_results.py",
            "tmcp_runtime/domain/composition_lift_campaign_scoring.py",
            "tmcp_runtime/domain/composition_lift_host_packet.py",
            "tmcp_runtime/domain/guidebook_promotion.py",
        ):
            self.assertIn(path, COMPILE_PATHS)

    def test_dispatch_bundles_hide_controller_cells_from_external_audiences(
        self,
    ) -> None:
        runner = build_campaign_dispatch_bundle(self.campaign, audience="runner")
        judge = build_campaign_dispatch_bundle(self.campaign, audience="judge")
        assert_matches_schema(
            runner,
            SCHEMAS / "tmcp-composition-lift-dispatch-bundle-v0.1.schema.json",
        )
        assert_matches_schema(
            judge,
            SCHEMAS / "tmcp-composition-lift-dispatch-bundle-v0.1.schema.json",
        )
        self.assertEqual(len(runner["dispatches"]), 540)
        self.assertEqual(len(judge["dispatches"]), 540)
        self.assertTrue(
            all(
                set(item)
                == {
                    "schema",
                    "runner_cell_id",
                    "execution_input_ref",
                    "instruction",
                    "instruction_digest",
                }
                for item in runner["dispatches"]
            )
        )
        self.assertTrue(
            all(
                set(item)
                == {
                    "schema",
                    "blind_judge_cell_id",
                    "artifact_slot_id",
                    "quality_rubric",
                    "quality_rubric_digest",
                    "instruction",
                    "instruction_digest",
                }
                for item in judge["dispatches"]
            )
        )
        self.assertNotIn("baseline_cells", runner)
        self.assertNotIn("causal_cells", runner)
        self.assertNotIn("baseline_cells", judge)
        self.assertNotIn("causal_cells", judge)


if __name__ == "__main__":
    unittest.main()
