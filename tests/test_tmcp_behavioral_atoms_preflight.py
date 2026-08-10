from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PLUGIN_ROOT
    / "schemas"
    / (
        "tmcp-behavioral-atoms-semantic-preflight-"
        + "v0.3.schema.json"
    )
)
FIXTURE_SCHEMA_PATH = (
    PLUGIN_ROOT
    / "schemas"
    / ("tmcp-behavioral-atoms-held-out-fixtures-" + "v0.3.schema.json")
)
PACKAGE_PATH = (
    PLUGIN_ROOT
    / "docs"
    / "experiments"
    / "behavioral-atoms-semantic-preflight-v0.3.json"
)
FIXTURE_PATH = (
    PLUGIN_ROOT / "tests" / "fixtures" / "behavioral-atoms-held-out-v0.3.json"
)

EXPECTED_FAMILIES = {
    "data_integrity",
    "security_privacy",
    "release_readiness",
    "migration_readiness",
}
EXPECTED_VALID_ARMS = {
    "arm.valid.migration_receives_data_reconciliation",
    "arm.valid.data_integrity_receives_migration_rollback",
    "arm.valid.release_receives_security_redaction",
    "arm.valid.security_privacy_receives_release_gating",
}
EXPECTED_INVALID_ARMS = {
    "arm.invalid.duplicate.test_to_security_local_context",
    "arm.invalid.duplicate.test_to_release_ordered_actions",
    "arm.invalid.no_variant.security_to_release",
    "arm.invalid.no_variant.release_to_security",
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} must contain an object")
    return value


def require_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    missing = fields - value.keys()
    if missing:
        raise AssertionError(f"{label} is missing fields: {sorted(missing)}")


def non_empty_strings(values: object, label: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise AssertionError(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in values):
        raise AssertionError(f"{label} must contain non-empty strings")
    return values


class BehavioralAtomsSemanticPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = read_json(SCHEMA_PATH)
        cls.fixture_schema = read_json(FIXTURE_SCHEMA_PATH)
        cls.package = read_json(PACKAGE_PATH)
        cls.fixtures = read_json(FIXTURE_PATH)

    def test_schema_and_artifacts_have_versioned_contract_identities(self) -> None:
        require_fields(
            self.schema,
            {"$schema", "$id", "title", "type", "required", "properties", "$defs"},
            "preflight schema",
        )
        self.assertEqual(self.schema["type"], "object")
        self.assertFalse(self.schema.get("additionalProperties"))
        self.assertEqual(
            self.schema["properties"]["schema"]["const"],
            "tmcp-behavioral-atoms-semantic-preflight-" + "v0.3",
        )
        self.assertEqual(
            self.package["schema"],
            "tmcp-behavioral-atoms-semantic-preflight-" + "v0.3",
        )
        self.assertEqual(self.package["version"], "0.3.0")
        self.assertEqual(
            self.fixtures["schema"],
            "tmcp-behavioral-atoms-held-out-fixtures-" + "v0.3",
        )
        self.assertEqual(self.fixtures["version"], "0.3.0")
        require_fields(
            self.fixture_schema,
            {"$schema", "$id", "title", "type", "required", "properties"},
            "held-out fixture schema",
        )
        self.assertFalse(self.fixture_schema.get("additionalProperties"))
        self.assertEqual(
            self.fixture_schema["properties"]["schema"]["const"],
            "tmcp-behavioral-atoms-held-out-fixtures-" + "v0.3",
        )

        required_contract_fields = {
            "stable_identity",
            "domain_semantics",
            "applicability",
            "dependencies",
            "conflicts",
            "required_inputs",
            "required_reads",
            "evidence_obligations",
            "verification_obligations",
            "stop_conditions",
            "provenance_trust",
            "rendering_boundary",
            "estimated_token_cost",
        }
        contract_fields = {
            field["name"]
            for field in self.package["typed_atom_contract"]["required_fields"]
        }
        self.assertEqual(contract_fields, required_contract_fields)
        self.assertTrue(
            all(
                field["required"]
                for field in self.package["typed_atom_contract"]["required_fields"]
            )
        )

    def test_family_signatures_are_distinct_from_the_generic_process_shell(
        self,
    ) -> None:
        shell = self.package["generic_process_shell"]
        self.assertFalse(shell["satisfies_domain_obligations"])
        shell_atoms = set(non_empty_strings(shell["atom_ids"], "process shell atoms"))
        signatures = self.package["family_signatures"]
        self.assertEqual(
            {signature["id"] for signature in signatures},
            EXPECTED_FAMILIES,
        )
        self.assertEqual(len(signatures), 4)

        distinct_fields = (
            "domain_target",
            "domain_risks",
            "domain_evidence_obligations",
            "domain_outputs",
            "domain_verification_obligations",
        )
        for field in distinct_fields:
            values = {
                json.dumps(signature[field], sort_keys=True) for signature in signatures
            }
            self.assertEqual(len(values), 4, field)

        for signature in signatures:
            self.assertEqual(
                signature["generic_process_shell_ref"],
                "process-shell.evidence-first@0.3.0",
            )
            domain_atoms = set(
                non_empty_strings(
                    signature["required_domain_atoms"],
                    f"{signature['id']} domain atoms",
                )
            )
            self.assertTrue(domain_atoms)
            self.assertFalse(domain_atoms & shell_atoms)
            self.assertTrue(signature["domain_evidence_obligations"])
            self.assertTrue(signature["domain_verification_obligations"])
            self.assertTrue(signature["stop_conditions"])

    def test_domain_atom_catalog_carries_all_typed_obligations(self) -> None:
        atoms = self.package["domain_atom_catalog"]
        self.assertEqual(len(atoms), 8)
        self.assertEqual({atom["family"] for atom in atoms}, EXPECTED_FAMILIES)
        for atom in atoms:
            require_fields(
                atom,
                {
                    "id",
                    "version",
                    "family",
                    "domain_semantics",
                    "applicability",
                    "dependencies",
                    "conflicts",
                    "required_inputs",
                    "required_reads",
                    "evidence_obligations",
                    "verification_obligations",
                    "stop_conditions",
                    "provenance_trust",
                    "rendering_boundary",
                    "estimated_token_cost",
                },
                atom["id"],
            )
            self.assertEqual(atom["version"], "0.3.0")
            applicability = atom["applicability"]
            for outcome in ("positive", "negative", "ambiguous"):
                non_empty_strings(
                    applicability[outcome],
                    f"{atom['id']} applicability.{outcome}",
                )
            self.assertTrue(applicability["ambiguous_action"])
            self.assertTrue(atom["dependencies"])
            self.assertTrue(atom["conflicts"])
            self.assertTrue(atom["required_inputs"])
            self.assertTrue(atom["required_reads"])
            self.assertTrue(atom["evidence_obligations"])
            self.assertTrue(atom["verification_obligations"])
            self.assertTrue(atom["stop_conditions"])
            self.assertEqual(
                atom["provenance_trust"]["trust"],
                "committed_source_backed",
            )
            self.assertTrue(atom["rendering_boundary"]["forbidden"])
            self.assertLessEqual(
                atom["estimated_token_cost"]["minimum"],
                atom["estimated_token_cost"]["maximum"],
            )

    def test_held_out_fixtures_have_explicit_owner_and_expected_outcome(self) -> None:
        self.assertEqual(self.fixtures["split"], "held_out")
        self.assertFalse(self.fixtures["non_tuning_boundary"]["tuning_allowed"])
        self.assertTrue(
            self.fixtures["non_tuning_boundary"]["labels_frozen_before_implementation"]
        )
        fixtures = self.fixtures["fixtures"]
        self.assertEqual(len(fixtures), 12)
        self.assertEqual(
            {fixture["family"] for fixture in fixtures},
            EXPECTED_FAMILIES,
        )
        self.assertEqual(
            {fixture["expected_outcome"]["applicability"] for fixture in fixtures},
            {"positive", "negative", "ambiguous"},
        )
        self.assertEqual(
            sum(
                fixture["expected_outcome"]["applicability"] == "positive"
                for fixture in fixtures
            ),
            4,
        )
        self.assertEqual(
            sum(
                fixture["expected_outcome"]["applicability"] == "negative"
                for fixture in fixtures
            ),
            4,
        )
        self.assertEqual(
            sum(
                fixture["expected_outcome"]["applicability"] == "ambiguous"
                for fixture in fixtures
            ),
            4,
        )

        fixture_ids = {fixture["id"] for fixture in fixtures}
        self.assertEqual(len(fixture_ids), 12)
        for fixture in fixtures:
            self.assertEqual(
                fixture["ownership"]["owner_id"],
                "behavioral_atoms_preflight",
            )
            self.assertEqual(fixture["ownership"]["status"], "sealed")
            expected = fixture["expected_outcome"]
            require_fields(
                expected,
                {
                    "applicability",
                    "decision",
                    "required_domain_atoms",
                    "required_obligations",
                    "stop",
                },
                f"{fixture['id']} expected outcome",
            )
            if expected["applicability"] == "positive":
                self.assertEqual(expected["decision"], "admit")
                self.assertFalse(expected["stop"])
                self.assertTrue(expected["required_domain_atoms"])
            elif expected["applicability"] == "negative":
                self.assertEqual(expected["decision"], "reject")
                self.assertFalse(expected["stop"])
                self.assertEqual(expected["required_domain_atoms"], [])
            else:
                self.assertEqual(expected["decision"], "hold_for_evidence")
                self.assertTrue(expected["stop"])
                self.assertTrue(expected["missing_evidence"])

    def test_transplant_registry_has_exact_valid_and_rejected_shapes(self) -> None:
        registry = self.package["transplant_arms"]
        valid = registry["valid"]
        rejected = registry["rejected_historical_shapes"]
        self.assertEqual({arm["id"] for arm in valid}, EXPECTED_VALID_ARMS)
        self.assertEqual({arm["id"] for arm in rejected}, EXPECTED_INVALID_ARMS)
        self.assertEqual(len(valid), 4)
        self.assertEqual(len(rejected), 4)

        signatures = set()
        for arm in valid:
            self.assertEqual(arm["status"], "valid")
            self.assertTrue(arm["source_family"])
            self.assertTrue(arm["target_family"])
            self.assertTrue(arm["source_atom_ref"])
            self.assertTrue(arm["target_obligation"])
            signature = arm["domain_delta_signature"]
            self.assertTrue(signature)
            self.assertNotIn(signature, signatures)
            signatures.add(signature)
            self.assertTrue(arm["predicted_semantic_delta"])
            self.assertTrue(arm["eligibility"]["unique_source_target_domain_delta"])
            self.assertTrue(arm["eligibility"]["non_empty_predicted_delta"])
            self.assertFalse(arm["eligibility"]["generic_only"])

        reasons = set()
        for arm in rejected:
            self.assertEqual(arm["status"], "invalid")
            self.assertIn(
                arm["reason_code"],
                {"duplicate_generic_condition", "no_eligible_variant"},
            )
            reasons.add(arm["reason_code"])
            self.assertTrue(arm["reason"])
            self.assertTrue(arm["evidence"])
        self.assertEqual(
            reasons,
            {"duplicate_generic_condition", "no_eligible_variant"},
        )

    def test_interaction_hypotheses_are_small_domain_selected_and_held_out(
        self,
    ) -> None:
        policy = self.package["interaction_selection_policy"]
        self.assertEqual(policy["selection_basis"], "domain_logic")
        self.assertEqual(policy["lexicographic_enumeration"], "forbidden")
        self.assertFalse(policy["exhaustive_pair_generation"])
        hypotheses = self.package["interaction_hypotheses"]
        self.assertEqual(len(hypotheses), 3)
        self.assertEqual(len({hypothesis["id"] for hypothesis in hypotheses}), 3)
        for hypothesis in hypotheses:
            self.assertEqual(hypothesis["selection_basis"], "domain_logic")
            self.assertEqual(len(hypothesis["families"]), 2)
            self.assertEqual(len(hypothesis["atom_refs"]), 2)
            self.assertTrue(hypothesis["predicted_direction"])
            self.assertTrue(hypothesis["mechanism"])
            self.assertTrue(hypothesis["falsifier"])
            boundary = hypothesis["held_out_evaluation_boundary"]
            self.assertTrue(boundary["fixture_ids"])
            self.assertFalse(boundary["tuning_allowed"])
            self.assertFalse(boundary["outcome_data_allowed"])
            self.assertEqual(boundary["owner"], "behavioral_atoms_preflight")

    def test_fail_closed_boundary_compatibility_and_dispositions_are_explicit(
        self,
    ) -> None:
        self.assertEqual(self.package["scope"]["runtime_implementation"], "not_started")
        self.assertEqual(self.package["scope"]["provider_cells"], "not_run")
        self.assertEqual(
            self.package["scope"]["cross_skill_composition_support"],
            "not_claimed",
        )
        self.assertTrue(
            self.package["compatibility_risk"]["no_public_runtime_schema_change"]
        )
        self.assertTrue(self.package["compatibility_risk"]["risks"])
        self.assertTrue(self.package["compatibility_risk"]["mitigations"])

        gate = self.package["validation_gate"]
        self.assertTrue(gate["fail_closed"])
        self.assertEqual(
            gate["implementation_boundary"]["runtime_registry"], "not_started"
        )
        self.assertEqual(gate["implementation_boundary"]["compiler"], "not_started")
        self.assertEqual(gate["implementation_boundary"]["evaluator"], "not_started")
        self.assertEqual(gate["implementation_boundary"]["provider_cells"], "not_run")
        self.assertTrue(gate["admission_rule"])

        dispositions = self.package["gate_dispositions"]
        disposition_ids = {item["id"] for item in dispositions}
        self.assertEqual(len(disposition_ids), len(dispositions))
        for item in dispositions:
            self.assertIn(
                item["status"], {"passed", "blocked", "not_run", "not_applicable"}
            )
            self.assertTrue(item["disposition"])
            if item["status"] in {"blocked", "not_run"}:
                self.assertTrue(item["disposition"])

    def test_source_and_fixture_hashes_bind_the_declared_evidence(self) -> None:
        expected_hashes = {
            "skills/tmcp-data-integrity-audit/SKILL.md": (
                "84fa7f2ad5aac85233d96aae31bc7041"
                + "2630a891715578213a91b1c4b93daf77"
            ),
            "skills/tmcp-security-privacy-audit/SKILL.md": (
                "18c7b963bb400250a3461f306616a53c"
                + "603e299dafb29afc06c0e411f88e88d7"
            ),
            "skills/tmcp-release-readiness/SKILL.md": (
                "54d435ed0f551048cccd47c3093aa073"
                + "4aff0fda8a15627ff3fb1d8bc8ca11ff"
            ),
            "skills/tmcp-migration-readiness/SKILL.md": (
                "8cc1eb80974ebcb098e5ef65ca0f3582"
                + "f860e108d952f073e96b171557bf90f7"
            ),
        }
        signatures = {
            signature["source_skill"]: signature["source_evidence"]["sha256"]
            for signature in self.package["family_signatures"]
        }
        self.assertEqual(signatures, expected_hashes)
        fixture_digest = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()
        self.assertEqual(
            self.package["fixture_artifact"]["sha256"],
            fixture_digest,
        )


if __name__ == "__main__":
    unittest.main()
