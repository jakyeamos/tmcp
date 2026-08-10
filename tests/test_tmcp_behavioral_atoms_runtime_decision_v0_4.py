"""Structural guard for the behavioral-atoms runtime decision packet."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    ROOT / "docs/experiments/behavioral-atoms-runtime-implementation-decision-v0.4.json"
)
ADR_PATH = (
    ROOT / "docs/experiments/BEHAVIORAL_ATOMS_RUNTIME_IMPLEMENTATION_DECISION_V0.4.md"
)
SCHEMA_PATH = (
    ROOT
    / "schemas/tmcp-behavioral-atoms-runtime-implementation-decision-v0.4.schema.json"
)
GIT_BASE_COMMIT = "3c9b2fe8cc0fe72ed947c447e4ea549094d810c3"


class BehavioralAtomsRuntimeDecisionV04Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_version_and_base_are_explicit(self) -> None:
        self.assertEqual(
            self.plan["schema"],
            "tmcp-behavioral-atoms-runtime-implementation-decision-v0.4",
        )
        self.assertEqual(self.plan["version"], "0.4.0")
        self.assertEqual(self.plan["status"], "implementation_decision_only")
        self.assertEqual(
            self.plan["base"]["commit"],
            GIT_BASE_COMMIT,
        )
        self.assertEqual(self.plan["base"]["source_branch"], "main")
        self.assertFalse(self.plan["base"]["public_runtime_schema_changed"])

    def test_internal_strategy_is_unambiguous_and_public_contract_is_stable(
        self,
    ) -> None:
        decision = self.plan["decision"]
        self.assertEqual(
            decision["version_strategy"],
            "internal_additive_compatibility_projection",
        )
        self.assertEqual(
            decision["internal_contract"]["schema"],
            "tmcp-behavioral-atom-runtime-v0.4",
        )
        self.assertEqual(decision["internal_contract"]["version"], "0.4.0")
        public = decision["public_contract"]
        self.assertTrue(public["unchanged"])
        self.assertTrue(public["tool_surfaces_unchanged"])
        self.assertEqual(public["runtime_version"], "0.5.7")
        self.assertIn(
            "schemas/tmcp-composed-packet-v0.1.schema.json", public["schemas_unchanged"]
        )
        self.assertIn(
            "schemas/tmcp-run-receipt-v0.1.schema.json", public["schemas_unchanged"]
        )

    def test_manifest_has_exact_six_replayed_hashes(self) -> None:
        expected = {
            "docs/experiments/BEHAVIORAL_ATOMS_SEMANTIC_PREFLIGHT_V0.3.md": "edd6443bd02e255b002a479bfd2f2a67e59dbb64c52aece467701674ce1d28e5",
            "docs/experiments/behavioral-atoms-semantic-preflight-v0.3.json": "5bc28d734e9b5903d55b166cb4a1e124c9f740e2a2ac9da8e306d88bfd65857e",
            "schemas/tmcp-behavioral-atoms-held-out-fixtures-v0.3.schema.json": "6b8df833b14b44416ce151674e4bac334e798b2e0ffa2645627606c8796a30f9",
            "schemas/tmcp-behavioral-atoms-semantic-preflight-v0.3.schema.json": "abecbd424720733af8028d214b34314f1f0aab280abb5ecd8187103ceac3f86f",
            "tests/fixtures/behavioral-atoms-held-out-v0.3.json": "172c761fcc5fb8f4814a2e9783b5322ad724b81ebec3ac0c74a1c03e9f9c652f",
            "tests/test_tmcp_behavioral_atoms_preflight.py": "66dc471e51c312ee0826284ac248f336eafc3f8ca696fbe79d63c6e043e5c254",
        }
        files = self.plan["intake"]["files"]
        self.assertEqual(len(files), 6)
        self.assertEqual({item["path"] for item in files}, set(expected))
        for item in files:
            self.assertTrue(item["replayed_exactly"])
            self.assertEqual(item["sha256"], expected[item["path"]])
            actual = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            self.assertEqual(actual, item["sha256"], item["path"])

    def test_layers_and_flow_keep_semantic_boundaries(self) -> None:
        self.assertEqual(
            {item["layer"] for item in self.plan["layer_boundaries"]},
            {
                "domain_atoms",
                "generic_process_atoms",
                "workflows_and_routes",
                "provenance_labels",
            },
        )
        flow = self.plan["data_flow"]
        self.assertEqual([stage["order"] for stage in flow], list(range(1, 10)))
        self.assertEqual(
            [stage["stage"] for stage in flow],
            [
                "durable_source_semantics",
                "typed_atom_registry_and_model",
                "applicability_compilation",
                "dependency_and_conflict_resolution",
                "deterministic_rendering_boundary",
                "token_budget_selection",
                "packet_projection",
                "receipt_projection",
                "advisory_evaluation",
            ],
        )
        fail_closed = self.plan["fail_closed_policy"]
        self.assertEqual(len(fail_closed["applicability"]), 3)
        self.assertIn(
            "literal trigger word", fail_closed["domain_without_trigger_words"]
        )
        self.assertIn("holds/stops", fail_closed["cost"])

    def test_slice_is_h1_and_excludes_public_surfaces(self) -> None:
        slice_plan = self.plan["smallest_implementation_slice"]
        self.assertEqual(
            slice_plan["id"], "runtime-v0.4-h1-typed-compile-and-projection"
        )
        self.assertTrue(
            any(
                "data_integrity.reconciliation@0.4.0" in atom
                for atom in slice_plan["seed_atoms"]
            )
        )
        self.assertTrue(
            any(
                "migration_readiness.rollback_path@0.4.0" in atom
                for atom in slice_plan["seed_atoms"]
            )
        )
        self.assertEqual(len(slice_plan["ordered_changes"]), 7)
        excluded = set(slice_plan["files"]["explicitly_not_modified"])
        self.assertIn("tmcp_runtime/api/tool_schemas.py", excluded)
        self.assertIn("tmcp_runtime/api/registry.py", excluded)
        self.assertIn("schemas/tmcp-*.schema.json", excluded)
        self.assertIn("tmcp_runtime/domain/receipts.py", excluded)
        self.assertNotIn("tmcp_runtime/api/tool_schemas.py", slice_plan["files"]["new"])
        self.assertNotIn(
            "tmcp_runtime/api/tool_schemas.py", slice_plan["files"]["modify"]
        )

    def test_future_evaluation_is_sealed_and_complete(self) -> None:
        evaluation = self.plan["future_evaluation"]
        self.assertEqual(len(evaluation["fixture_mapping"]), 12)
        self.assertEqual(len(evaluation["valid_arms"]), 4)
        self.assertEqual(len(evaluation["invalid_arms"]), 4)
        self.assertEqual(len(evaluation["hypotheses"]), 3)
        self.assertEqual(evaluation["provider_cells"], "not_run")
        self.assertEqual(evaluation["cross_skill_composition"], "closed_gate")
        self.assertEqual(
            {item["applicability"] for item in evaluation["fixture_mapping"]},
            {"positive", "negative", "ambiguous"},
        )
        self.assertTrue(
            all(
                item["status"] == "rejected_before_cell"
                for item in evaluation["invalid_arms"]
            )
        )
        self.assertTrue(
            all(
                item["selection_basis"] == "domain_logic"
                for item in evaluation["hypotheses"]
            )
        )

    def test_schema_and_handoff_point_to_the_same_packet(self) -> None:
        self.assertEqual(self.schema["$id"].rsplit("/", 1)[-1], SCHEMA_PATH.name)
        self.assertEqual(
            self.schema["properties"]["schema"]["const"], self.plan["schema"]
        )
        self.assertEqual(
            self.schema["properties"]["version"]["const"], self.plan["version"]
        )
        handoff = self.plan["handoff"]
        self.assertEqual(handoff["machine_plan"], str(PLAN_PATH.relative_to(ROOT)))
        self.assertEqual(
            handoff["conceptual_schema"], str(SCHEMA_PATH.relative_to(ROOT))
        )
        self.assertIn("copy only", handoff["replay_command"])
        adr = ADR_PATH.read_text(encoding="utf-8")
        for required_text in (
            "internal/additive compatibility projection",
            GIT_BASE_COMMIT,
            "runtime-v0.4-h1-typed-compile-and-projection",
            "Provider\npreflight requires",
        ):
            self.assertIn(required_text, adr)


if __name__ == "__main__":
    unittest.main()
