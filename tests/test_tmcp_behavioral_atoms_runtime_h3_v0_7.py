"""Structural guard for the private, decision-only H3 v0.7 boundary."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs/experiments/behavioral-atoms-runtime-h3-boundary-evidence-ladder-v0.7.json"
DECISION_SCHEMA_PATH = ROOT / "schemas/tmcp-behavioral-atoms-runtime-h3-decision-v0.7.schema.json"
FIXTURE_SCHEMA_PATH = ROOT / "schemas/tmcp-behavioral-atoms-runtime-h3-fixtures-v0.7.schema.json"
FIXTURE_PATH = ROOT / "tests/fixtures/behavioral-atoms-runtime-h3-v0.7.json"


class BehavioralAtomsRuntimeH3V07Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.decision = json.loads(DECISION_PATH.read_text(encoding="utf-8"))
        cls.decision_schema = json.loads(
            DECISION_SCHEMA_PATH.read_text(encoding="utf-8")
        )
        cls.fixture_schema = json.loads(
            FIXTURE_SCHEMA_PATH.read_text(encoding="utf-8")
        )
        cls.fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_versioned_private_boundary_and_schema_ids_match(self) -> None:
        self.assertEqual(
            self.decision["schema"],
            "tmcp-behavioral-atoms-runtime-h3-decision-v0.7",
        )
        self.assertEqual(self.decision["version"], "0.7.0")
        self.assertEqual(self.decision["status"], "decision_only_private_additive")
        self.assertEqual(
            self.decision_schema["properties"]["schema"]["const"],
            self.decision["schema"],
        )
        self.assertEqual(
            self.decision_schema["properties"]["version"]["const"],
            self.decision["version"],
        )
        self.assertEqual(
            self.fixture_schema["properties"]["schema"]["const"],
            self.fixtures["schema"],
        )
        self.assertEqual(
            self.fixture_schema["properties"]["version"]["const"],
            self.fixtures["version"],
        )

    def test_inherited_baselines_are_hash_pinned_and_unchanged(self) -> None:
        baselines = self.decision["base"]["immutable_baselines"]
        expected = {
            "h1_semantic_preflight": {
                "sha256": "5bc28d734e9b5903d55b166cb4a1e124c9f740e2a2ac9da8e306d88bfd65857e"
            },
            "h1_fixture_schema": {
                "sha256": "6b8df833b14b44416ce151674e4bac334e798b2e0ffa2645627606c8796a30f9"
            },
            "h1_fixtures": {
                "sha256": "172c761fcc5fb8f4814a2e9783b5322ad724b81ebec3ac0c74a1c03e9f9c652f"
            },
            "h2_decision": {
                "sha256": "8b521e07628628ba84df1816fc5315fdf8cb31b080d23acd40dd8b95d73a988c"
            },
        }
        for name, expected_hash in expected.items():
            expected_hash = expected_hash["sha256"]
            with self.subTest(name=name):
                item = baselines[name]
                self.assertEqual(item["sha256"], expected_hash)
                self.assertEqual(self._sha256(ROOT / item["path"]), expected_hash)

        self.assertEqual(
            self.decision["base"]["worktree_state"],
            "dirty_existing_changes_preserved",
        )
        self.assertEqual(self.decision["base"]["public_runtime_version"], "0.5.7")

    def test_h3_delta_is_distinct_and_has_preregistered_arms(self) -> None:
        decision = self.decision["decision"]
        atom_ids = [item["id"] for item in decision["source_atoms"]]
        self.assertEqual(
            atom_ids,
            [
                "domain.security_privacy.secret_boundary@0.4.0",
                "domain.release_readiness.evidence_ladder@0.4.0",
            ],
        )
        self.assertEqual(len(decision["valid_arms"]), 2)
        self.assertTrue(all(arm["unique_delta"] for arm in decision["valid_arms"]))
        self.assertTrue(
            all(arm["status"] == "eligible_advisory" for arm in decision["valid_arms"])
        )
        self.assertTrue(
            all(
                arm["provider_outcome"] == "not_run"
                and arm["cross_skill_composition"] == "closed_gate"
                for arm in decision["valid_arms"]
            )
        )
        self.assertEqual(len(decision["invalid_arms"]), 4)
        self.assertTrue(
            all(item["status"] == "rejected_before_cell" for item in decision["invalid_arms"])
        )
        proof = self.decision["delta"]["non_duplicate_proof"]
        self.assertTrue(any("redaction" in item for item in proof))
        self.assertTrue(any("ship_gate" in item for item in proof))

    def test_fixture_boundary_is_frozen_and_covers_required_cases(self) -> None:
        fixture_list = self.fixtures["fixtures"]
        self.assertEqual(len(fixture_list), 7)
        self.assertEqual(
            {item["classification"] for item in fixture_list},
            {"positive", "negative", "ambiguous"},
        )
        self.assertTrue(all(item["frozen_label"] for item in fixture_list))
        self.assertEqual(
            self.decision["fixture_boundary"]["sha256"], self._sha256(FIXTURE_PATH)
        )
        combined = next(
            item
            for item in fixture_list
            if item["id"] == "h3_combined_positive_secret_boundary_evidence_ladder"
        )
        self.assertEqual(combined["classification"], "positive")
        self.assertEqual(combined["interaction"], "h3_combined_domain")
        self.assertTrue(combined["expected_outcome"]["absent_from_current_evidence"])
        self.assertEqual(
            combined["expected_outcome"]["required_h3_atoms"],
            [
                "domain.security_privacy.secret_boundary@0.4.0",
                "domain.release_readiness.evidence_ladder@0.4.0",
            ],
        )
        self.assertEqual(combined["expected_outcome"]["provider_outcome"], "not_run")
        self.assertEqual(
            combined["expected_outcome"]["cross_skill_composition"], "closed_gate"
        )

    def test_negative_and_ambiguous_cases_fail_closed(self) -> None:
        by_id = {item["id"]: item["expected_outcome"] for item in self.fixtures["fixtures"]}
        self.assertEqual(
            by_id["h3_security_negative_redaction_only"]["decision"], "reject"
        )
        self.assertEqual(
            by_id["h3_release_negative_ship_gate_only"]["decision"], "reject"
        )
        for fixture_id in (
            "h3_security_ambiguous_inferred_authority",
            "h3_release_ambiguous_partial_ladder",
        ):
            with self.subTest(fixture_id=fixture_id):
                expected = by_id[fixture_id]
                self.assertEqual(expected["decision"], "hold_for_evidence")
                self.assertTrue(expected["stop"])
                self.assertEqual(expected["required_h3_atoms"], [])
                self.assertTrue(expected["missing_evidence"])

    def test_all_required_fail_closed_gates_and_compatibility_boundaries_are_present(
        self,
    ) -> None:
        gate_ids = {item["id"] for item in self.decision["fail_closed_gates"]}
        for required in (
            "input.explicit_semantic_context",
            "read.source_and_owner",
            "evidence.required_obligations",
            "verification.boundary_and_freshness",
            "trust.source_scoped",
            "conflict.authority_or_partial_evidence",
            "dependency.h2_and_process_baseline",
            "phase.compatible",
            "stop.ambiguous_negative_and_unowned",
            "budget.required_content",
        ):
            self.assertIn(required, gate_ids)
        self.assertEqual(
            self.decision["compatibility"]["default_behavior"],
            "unchanged_default_disabled",
        )
        self.assertTrue(self.decision["compatibility"]["provider_off"])
        self.assertTrue(self.decision["compatibility"]["cross_skill_off"])
        self.assertEqual(self.decision["compatibility"]["admission_routing"], "unchanged")
        self.assertEqual(
            self.decision["decision"]["cross_skill_composition"], "closed_gate"
        )

    def test_h3_is_not_registered_in_the_current_h2_runtime_registry(self) -> None:
        from tmcp_runtime.domain.behavioral_atoms import build_h2_registry

        ids = build_h2_registry().ids
        self.assertNotIn("domain.security_privacy.secret_boundary@0.4.0", ids)
        self.assertNotIn("domain.release_readiness.evidence_ladder@0.4.0", ids)
        self.assertEqual(self.decision["decision"]["runtime_implementation"], "not_started")


if __name__ == "__main__":
    unittest.main()
