from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_composition_benchmark import prepare_benchmark
from scripts.assemble_composition_benchmark import assemble_control_plan
from scripts.schema_contract_support import assert_matches_schema
from tmcp_runtime.domain.composition_benchmark_protocol import (
    build_benchmark_preparation,
    fixture_source_nodes,
    prepare_fixture_preflight,
    validate_benchmark_run_plan,
)
from tmcp_runtime.domain.composition_benchmark_replay import (
    SEMANTIC_PROPOSAL_BUNDLE_SCHEMA,
    build_benchmark_control_plan,
    validate_benchmark_control_plan,
)
from tmcp_runtime.storage.artifacts import (
    ArtifactStorageError,
    AtomicArtifactStore,
    artifact_persistence_available,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCHEMAS = ROOT / "schemas"
ROUTING_PATH = FIXTURES / "composition_routing_golden_v0_6.json"
BEHAVIORAL_PATH = FIXTURES / "composition_behavioral_fixtures_v0_6.json"


def _payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must contain an object")
    return payload


def _proposal_for_fixture(
    fixture: dict[str, object],
    *,
    objective: str,
    selected_skill_ids: list[str],
) -> dict[str, object]:
    """Return a test-only host proposal with citations from its prepared input."""

    preflight = prepare_fixture_preflight(fixture=fixture, objective=objective)
    node_by_skill = {
        str(node["skill_id"]): str(node["id"]) for node in fixture_source_nodes(fixture)
    }
    slice_by_node = {
        str(item["source_node_id"]): str(item["slice_id"])
        for item in preflight["candidate_source_slices"]
    }
    phases = ("discovery", "implementation", "verification", "final")
    roles = []
    for index, skill_id in enumerate(selected_skill_ids):
        node_id = node_by_skill[skill_id]
        roles.append(
            {
                "node_id": node_id,
                "role": f"{skill_id} benchmark role",
                "inputs": [
                    "bounded objective"
                    if index == 0
                    else f"{selected_skill_ids[index - 1]} handoff"
                ],
                "outputs": [f"{skill_id} handoff"],
                "phase_affinity": [phases[index]],
                "entry_gates": [],
                "exit_gates": [f"{skill_id} evidence is available"],
                "context_cost": 0,
                "covers": ["benchmark outcome"],
                "citations": [slice_by_node[node_id]],
            }
        )
    relationships = []
    for relationship in fixture["expected_relationships"]:
        source_id = str(relationship["source_id"])
        target_id = str(relationship["target_id"])
        if source_id not in node_by_skill or target_id not in node_by_skill:
            continue
        if source_id not in selected_skill_ids or target_id not in selected_skill_ids:
            continue
        source_node_id = node_by_skill[source_id]
        target_node_id = node_by_skill[target_id]
        relationships.append(
            {
                "from": source_node_id,
                "to": target_node_id,
                "type": relationship["relation"],
                "citations": [
                    slice_by_node[source_node_id],
                    slice_by_node[target_node_id],
                ],
                "rationale": "Fixture host proposal uses prepared source evidence.",
            }
        )
    return {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": preflight["preflight_id"],
        "current_phase": "start",
        "task_model": {
            "deliverables": ["Benchmark outcome"],
            "success_criteria": ["benchmark outcome"],
            "constraints": ["Preserve prepared source authority"],
            "subgoals": ["Produce each compiled handoff"],
            "evidence_needs": ["Source-backed verification evidence"],
        },
        "skill_roles": roles,
        "relationships": relationships,
        "coverage": {"facets": ["benchmark outcome"], "unresolved_gaps": []},
        "trust": "advisory_untrusted",
    }


def _semantic_proposal_bundle(
    plan: dict[str, object],
    routing: dict[str, object],
    behavioral: dict[str, object],
) -> dict[str, object]:
    fixtures_by_id = {
        str(fixture["fixture_id"]): fixture for fixture in behavioral["fixtures"]
    }
    fixtures_by_domain = {
        str(fixture["domain"]): fixture for fixture in behavioral["fixtures"]
    }
    routing_proposals = []
    for case in routing["cases"]:
        fixture = fixtures_by_domain[str(case["domain"])]
        routing_proposals.append(
            {
                "case_id": case["case_id"],
                "semantic_proposal": _proposal_for_fixture(
                    fixture,
                    objective=str(case["objective"]),
                    selected_skill_ids=list(case["expected_skill_ids"]),
                ),
            }
        )
    behavioral_proposals = []
    for fixture_id, fixture in fixtures_by_id.items():
        behavioral_proposals.append(
            {
                "fixture_id": fixture_id,
                "semantic_proposal": _proposal_for_fixture(
                    fixture,
                    objective=str(fixture["objective"]),
                    selected_skill_ids=list(fixture["expected_skill_ids"]),
                ),
            }
        )
    return {
        "schema": SEMANTIC_PROPOSAL_BUNDLE_SCHEMA,
        "run_manifest_id": plan["run_manifest_id"],
        "run_manifest_digest": plan["run_manifest_digest"],
        "routing_proposals": routing_proposals,
        "behavioral_proposals": behavioral_proposals,
    }


class CompositionBenchmarkProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routing = _payload(ROUTING_PATH)
        cls.behavioral = _payload(BEHAVIORAL_PATH)

    def test_preparation_is_schema_valid_and_hides_score_oracles(self) -> None:
        plan, artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )

        assert_matches_schema(
            plan,
            SCHEMAS / "tmcp-composition-benchmark-run-plan-v0.1.schema.json",
        )
        validate_benchmark_run_plan(
            plan,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        serialized_plan = json.dumps(plan, sort_keys=True)
        for forbidden in (
            "expected_skill_ids",
            "expected_order",
            "expected_relationships",
            "quality_rubric",
        ):
            self.assertNotIn(forbidden, serialized_plan)
        self.assertEqual(plan["protocol"]["cache_policy"], "none")
        self.assertFalse(plan["protocol"]["automatic_tool_execution"])
        self.assertEqual(len(plan["fixture_workspaces"]), 5)
        self.assertGreaterEqual(len(plan["routing_requests"]), 20)
        self.assertEqual(len(plan["behavioral_requests"]), 5)
        self.assertIn("benchmark-run-plan.json", artifacts)
        self.assertTrue(
            all(
                path.startswith("fixtures/") for path in artifacts if "/skills/" in path
            )
        )
        self.assertTrue(
            all(
                path.startswith("host-inputs/")
                for path in artifacts
                if path.endswith("-preflight.json")
            )
        )

    def test_protocol_identity_is_root_independent_and_content_sensitive(self) -> None:
        first, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        second, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        first_fixture = self.behavioral["fixtures"][0]
        first_nodes = fixture_source_nodes(
            first_fixture,
            logical_workspace_root=Path("/one/fixture-root"),
        )
        second_nodes = fixture_source_nodes(
            first_fixture,
            logical_workspace_root=Path("/another/fixture-root"),
        )
        changed = copy.deepcopy(self.behavioral)
        changed["fixtures"][0]["skill_sources"][0]["content"] += "\nChanged."
        changed_plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=changed,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            [node["id"] for node in first_nodes],
            [node["id"] for node in second_nodes],
        )
        self.assertEqual(first["run_manifest_id"], second["run_manifest_id"])
        self.assertNotEqual(
            first["run_manifest_digest"], changed_plan["run_manifest_digest"]
        )

    def test_benchmark_preflights_expose_every_active_fixture_source(self) -> None:
        for fixture in self.behavioral["fixtures"]:
            preflight = prepare_fixture_preflight(
                fixture=fixture,
                objective=str(fixture["objective"]),
            )
            self.assertEqual(
                {
                    item["source_node_id"]
                    for item in preflight["candidate_source_slices"]
                },
                {node["id"] for node in fixture_source_nodes(fixture)},
            )
            self.assertEqual(
                preflight["diagnostics"]["semantic_evidence"]["selection_policy"],
                "all_active_source_candidates",
            )

    def test_control_plan_replays_compiler_and_derives_real_variant_inputs(
        self,
    ) -> None:
        plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        proposals = _semantic_proposal_bundle(plan, self.routing, self.behavioral)
        assert_matches_schema(
            proposals,
            SCHEMAS / "tmcp-composition-benchmark-semantic-proposals-v0.1.schema.json",
        )
        controls = build_benchmark_control_plan(
            run_plan=plan,
            semantic_proposals=proposals,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        assert_matches_schema(
            controls,
            SCHEMAS / "tmcp-composition-benchmark-control-plan-v0.1.schema.json",
        )

        self.assertEqual(len(controls["routing_controls"]), 25)
        self.assertEqual(len(controls["behavioral_controls"]), 5)
        for control in controls["behavioral_controls"]:
            full = next(
                variant
                for variant in control["variants"]
                if variant["variant_id"] == "full_composition"
            )
            wrong_order = next(
                variant
                for variant in control["variants"]
                if variant["variant_id"] == "wrong_order"
            )
            self.assertEqual(full["ordered_skill_ids"], control["ordered_skill_ids"])
            self.assertEqual(
                wrong_order["ordered_skill_ids"],
                list(reversed(control["ordered_skill_ids"])),
            )
            self.assertEqual(
                [item["skill_id"] for item in wrong_order["source_bindings"]],
                wrong_order["ordered_skill_ids"],
            )
            self.assertEqual(full["cache_policy"], "none")
            self.assertNotEqual(
                full["input_packet_digest"], wrong_order["input_packet_digest"]
            )
            self.assertTrue(full["composition_enabled"])
            self.assertEqual(
                full["execution_recipe"]["execution_mode"],
                "compiled_composition",
            )
            self.assertTrue(full["execution_recipe"]["stages"])
            self.assertTrue(full["execution_recipe"]["handoff_contracts"])
            self.assertIn(
                "compiled_context_tokens",
                full["execution_recipe"]["context_accounting"],
            )
            self.assertFalse(wrong_order["composition_enabled"])
            self.assertEqual(
                wrong_order["execution_recipe"]["execution_mode"],
                "counterfactual_wrong_order",
            )
            self.assertTrue(wrong_order["execution_recipe"]["violated_ordering_edges"])
            self.assertTrue(wrong_order["execution_recipe"]["required_gate_overrides"])
            for variant in control["variants"]:
                self.assertEqual(
                    variant["execution_recipe_digest"],
                    variant["execution_recipe"]["recipe_digest"],
                )
                if variant["variant_id"].startswith("leave_one_out:"):
                    self.assertFalse(variant["composition_enabled"])
                    self.assertEqual(
                        variant["execution_recipe"]["execution_mode"],
                        "counterfactual_ablation",
                    )
                    self.assertTrue(variant["execution_recipe"]["missing_obligations"])
        validate_benchmark_control_plan(
            controls,
            run_plan=plan,
            semantic_proposals=proposals,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )

    def test_control_plan_rejects_phase_mismatch_and_tampering(self) -> None:
        plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        proposals = _semantic_proposal_bundle(plan, self.routing, self.behavioral)
        proposals["behavioral_proposals"][0]["semantic_proposal"]["current_phase"] = (
            "verification"
        )
        with self.assertRaisesRegex(ValueError, "current_phase"):
            build_benchmark_control_plan(
                run_plan=plan,
                semantic_proposals=proposals,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
            )

        controls = build_benchmark_control_plan(
            run_plan=plan,
            semantic_proposals=_semantic_proposal_bundle(
                plan,
                self.routing,
                self.behavioral,
            ),
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        tampered = copy.deepcopy(controls)
        tampered["behavioral_controls"][0]["variants"][0]["ordered_skill_ids"] = [
            "forged"
        ]
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_benchmark_control_plan(
                tampered,
                run_plan=plan,
                semantic_proposals=_semantic_proposal_bundle(
                    plan,
                    self.routing,
                    self.behavioral,
                ),
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
            )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_prepare_materializes_exact_isolated_fixture_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "benchmark"
            result = prepare_benchmark(
                routing_golden_path=ROUTING_PATH,
                behavioral_fixtures_path=BEHAVIORAL_PATH,
                output_dir=output_dir,
            )
            plan = json.loads(
                (output_dir / "benchmark-run-plan.json").read_text(encoding="utf-8")
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["automatic_tool_execution"])
            self.assertEqual(result["receipt_persistence"], "not_performed")
            self.assertEqual(plan["run_manifest_id"], result["run_manifest_id"])
            self.assertFalse(
                (output_dir / "fixtures" / "benchmark-run-plan.json").exists()
            )
            for fixture in self.behavioral["fixtures"]:
                fixture_root = output_dir / "fixtures" / fixture["fixture_id"]
                for source in fixture["skill_sources"]:
                    self.assertEqual(
                        (fixture_root / source["relative_path"]).read_text(
                            encoding="utf-8"
                        ),
                        source["content"],
                    )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_control_assembly_writes_only_replayed_control_plan(self) -> None:
        plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        proposals = _semantic_proposal_bundle(plan, self.routing, self.behavioral)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            paths = AtomicArtifactStore.write_json_bundle(
                inputs,
                {
                    "run-plan.json": plan,
                    "semantic-proposals.json": proposals,
                },
            )
            result = assemble_control_plan(
                run_plan_path=Path(paths["run-plan.json"]),
                semantic_proposals_path=Path(paths["semantic-proposals.json"]),
                routing_golden_path=ROUTING_PATH,
                behavioral_fixtures_path=BEHAVIORAL_PATH,
                output_dir=root / "controls",
            )
            control_path = Path(result["control_plan_path"])
            control_plan = json.loads(control_path.read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertFalse(result["automatic_tool_execution"])
            self.assertEqual(result["receipt_persistence"], "not_performed")
            self.assertEqual(result["control_plan_id"], control_plan["control_plan_id"])
            assert_matches_schema(
                control_plan,
                SCHEMAS / "tmcp-composition-benchmark-control-plan-v0.1.schema.json",
            )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_tree_bundle_rejects_escape_and_nonempty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "benchmark"
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_tree_bundle(
                    output_dir,
                    {"fixtures/../outside.txt": "unsafe"},
                )
            AtomicArtifactStore.write_tree_bundle(
                output_dir,
                {"fixtures/one/skills/example/SKILL.md": "safe"},
            )
            self.assertEqual(
                (
                    output_dir / "fixtures" / "one" / "skills" / "example" / "SKILL.md"
                ).read_text(encoding="utf-8"),
                "safe",
            )
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_tree_bundle(
                    output_dir,
                    {"fixtures/two/skills/example/SKILL.md": "new"},
                )


if __name__ == "__main__":
    unittest.main()
