from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tmcp_runtime.api.registry import VERSION, canonical_contract_fixture
from tmcp_runtime.services.behavioral_atom_runtime import (
    evaluate_sealed_behavioral_fixtures,
)
from tmcp_runtime.services.compose import compose_packet_from_source_nodes
from tmcp_runtime.services.evaluation_catalog import (
    ADVISORY_VARIANTS,
    DEFAULT_VARIANTS,
    TYPED_STATIC_VARIANT,
)


class BehavioralAtomPublicProjectionV04Tests(unittest.TestCase):
    @staticmethod
    def _arguments(
        *, semantic_bundle: dict[str, object] | None = None
    ) -> dict[str, object]:
        arguments: dict[str, object] = {
            "objective": "Review the bounded state transition using owned semantic records.",
            "project_path": "[REDACTED:path]",
            "phase": "planning",
            "cache_policy": "none",
        }
        if semantic_bundle is not None:
            arguments["runtime_context"] = {"semantic_bundle": semantic_bundle}
        return arguments

    @staticmethod
    def _bundle(*, applicability: str = "positive") -> dict[str, object]:
        return {
            "phase": "planning",
            "semantic_signals": {"data_integrity": applicability},
            "legacy_atoms": ["legacy.atom.from-public-packet"],
            "inputs": {
                "before_state": {"value": "before", "owner": "fixture-owner"},
                "after_state": {"value": "after", "owner": "fixture-owner"},
                "reconciliation_rule": {"value": "stable-id", "owner": "fixture-owner"},
            },
            "reads": [
                {
                    "reference": "skills/tmcp-data-integrity-audit/SKILL.md",
                    "status": "available",
                    "trust": "committed_source_backed",
                    "owner": "fixture-owner",
                },
                {
                    "reference": "reconciliation checks, import/export jobs, or backfill evidence",
                    "status": "available",
                    "trust": "sealed_fixture",
                    "owner": "fixture-owner",
                },
            ],
            "evidence": [
                {
                    "obligation": "before/after boundary is recorded",
                    "status": "recorded",
                    "source": "sealed-fixture",
                    "owner": "fixture-owner",
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "mismatches, exclusions, and unresolved gaps are recorded",
                    "status": "recorded",
                    "source": "sealed-fixture",
                    "owner": "fixture-owner",
                    "trust": "sealed_fixture",
                },
            ],
            "verification": [
                {
                    "obligation": "reconciliation check is run and inspected",
                    "status": "passed",
                    "source": "sealed-fixture",
                    "owner": "fixture-owner",
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "idempotency risk is repeated when applicable",
                    "status": "passed",
                    "source": "sealed-fixture",
                    "owner": "fixture-owner",
                    "trust": "sealed_fixture",
                },
            ],
            "provided_dependencies": ["domain.data_integrity.invariants@0.4.0"],
            "token_budget": 512,
        }

    @staticmethod
    def _h2_bundle() -> dict[str, object]:
        owner = "fixture-owner"
        return {
            "phase": "planning",
            "semantic_signals": {"release_readiness": "positive"},
            "inputs": {
                "release_scope": {"value": "feature", "owner": owner},
                "current_quality_evidence": {
                    "value": "current-checks",
                    "owner": owner,
                },
            },
            "reads": [
                {
                    "reference": "skills/tmcp-release-readiness/SKILL.md",
                    "status": "available",
                    "trust": "committed_source_backed",
                    "owner": owner,
                },
                {
                    "reference": "project instructions, README, CI, tests, build scripts, and release docs",
                    "status": "available",
                    "trust": "sealed_fixture",
                    "owner": owner,
                },
            ],
            "evidence": [
                {
                    "obligation": "current quality and release evidence is recorded",
                    "status": "recorded",
                    "source": "sealed-fixture",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "observed blockers, risks, and unknowns are separated",
                    "status": "recorded",
                    "source": "sealed-fixture",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
            ],
            "verification": [
                {
                    "obligation": "required release checks are run or inspected",
                    "status": "passed",
                    "source": "sealed-fixture",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "every ship blocker has a disposition and next gate",
                    "status": "passed",
                    "source": "sealed-fixture",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
            ],
            "token_budget": 512,
        }

    def test_absent_bundle_preserves_baseline_packet_byte_shape(self) -> None:
        arguments = self._arguments()
        baseline = compose_packet_from_source_nodes(
            arguments,
            source_nodes=[],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )
        repeated = compose_packet_from_source_nodes(
            copy.deepcopy(arguments),
            source_nodes=[],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )
        self.assertEqual(baseline, repeated)
        self.assertEqual(baseline["schema"], "tmcp-composed-packet-v0.1")
        self.assertEqual(
            baseline["receipt_template"]["schema"], "tmcp-run-receipt-v0.1"
        )

    def test_typed_projection_uses_existing_public_packet_and_receipt_fields(
        self,
    ) -> None:
        baseline = compose_packet_from_source_nodes(
            self._arguments(),
            source_nodes=[],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )
        projected = compose_packet_from_source_nodes(
            self._arguments(semantic_bundle=self._bundle()),
            source_nodes=[],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )
        self.assertEqual(set(projected), set(baseline))
        self.assertEqual(projected["schema"], baseline["schema"])
        self.assertEqual(
            projected["receipt_template"]["schema"], "tmcp-run-receipt-v0.1"
        )
        self.assertEqual(
            projected["active_atoms"][:1], ["legacy.atom.from-public-packet"]
        )
        self.assertIn(
            "domain.data_integrity.reconciliation@0.4.0",
            projected["active_atoms"],
        )
        self.assertEqual(
            projected["receipt_template"]["activated_atoms"],
            projected["active_atoms"],
        )
        self.assertNotIn("trust", projected["receipt_template"])
        self.assertNotIn("provider_prompt", str(projected))
        self.assertEqual(VERSION.release, "0.5.7")

    def test_ambiguous_projection_preserves_stop_and_does_not_emit_domain_atom(
        self,
    ) -> None:
        projected = compose_packet_from_source_nodes(
            self._arguments(semantic_bundle=self._bundle(applicability="ambiguous")),
            source_nodes=[],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )
        self.assertEqual(projected["active_atoms"], ["legacy.atom.from-public-packet"])
        self.assertTrue(projected["stop_conditions"])
        self.assertTrue(
            any("hold_for_evidence" in item for item in projected["stop_conditions"])
        )
        self.assertEqual(
            projected["receipt_template"]["activated_atoms"],
            ["legacy.atom.from-public-packet"],
        )

    def test_h2_projection_uses_public_fields(self) -> None:
        baseline = compose_packet_from_source_nodes(
            self._arguments(),
            source_nodes=[],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )
        projected = compose_packet_from_source_nodes(
            self._arguments(semantic_bundle=self._h2_bundle()),
            source_nodes=[],
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )
        self.assertEqual(set(projected), set(baseline))
        self.assertEqual(projected["schema"], baseline["schema"])
        self.assertEqual(
            projected["receipt_template"]["schema"], "tmcp-run-receipt-v0.1"
        )
        self.assertIn(
            "domain.release_readiness.ship_gate@0.4.0",
            projected["active_atoms"],
        )
        self.assertNotIn("provider_prompt", str(projected))
        self.assertEqual(VERSION.release, "0.5.7")

    def test_public_contract_fixture_and_default_variants_are_unchanged(self) -> None:
        fixture_path = Path("tests/fixtures/public-contract-v0.4.json")
        self.assertEqual(
            canonical_contract_fixture(),
            json.loads(fixture_path.read_text(encoding="utf-8")),
        )
        self.assertNotIn(TYPED_STATIC_VARIANT, DEFAULT_VARIANTS)
        self.assertIn(
            TYPED_STATIC_VARIANT,
            {str(item["id"]) for item in ADVISORY_VARIANTS},
        )

    def test_typed_static_evaluator_consumes_fixture_split_without_provider_cells(
        self,
    ) -> None:
        fixture_path = Path("tests/fixtures/behavioral-atoms-held-out-v0.3.json")
        fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))["fixtures"]
        report = evaluate_sealed_behavioral_fixtures(fixtures)
        self.assertEqual(report["variant_id"], TYPED_STATIC_VARIANT)
        self.assertEqual(report["fixture_count"], 12)
        self.assertTrue(report["all_fixtures_consumed"])
        self.assertEqual(report["provider_cells"], "not_run")
        self.assertEqual(report["cross_skill_composition"], "closed_gate")
        supported = [case for case in report["cases"] if case["supported"]]
        deferred = [case for case in report["cases"] if not case["supported"]]
        self.assertEqual(len(supported), 12)
        self.assertEqual(len(deferred), 0)
        self.assertTrue(all(case["score"]["score"] == 1.0 for case in supported))
        self.assertFalse(
            any(case.get("provider_execution") for case in report["cases"])
        )


if __name__ == "__main__":
    unittest.main()
