from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from tmcp_runtime.domain.behavioral_atoms import (
    DATA_INVARIANTS_ID,
    DATA_RECONCILIATION_ID,
    MIGRATION_COMPATIBILITY_ID,
    MIGRATION_ROLLBACK_ID,
    RUNTIME_ATOM_SCHEMA,
    RUNTIME_ATOM_VERSION,
    SemanticContext,
    build_h1_registry,
    compile_behavioral_atoms,
    legacy_string_projection,
    render_atoms,
)
from tmcp_runtime.services.behavioral_atom_runtime import (
    build_h1_advisory_evaluator_mapping,
    evaluate_sealed_behavioral_fixtures,
    evaluate_transplant_arm,
)


class BehavioralAtomRuntimeV04Tests(unittest.TestCase):
    @staticmethod
    def _context(
        family: str,
        applicability: str = "positive",
        *,
        include_dependency: bool = True,
        token_budget: int = 512,
        **overrides: object,
    ) -> SemanticContext:
        if family == "data_integrity":
            inputs = {
                "before_state": {"value": "before", "owner": "fixture-owner"},
                "after_state": {"value": "after", "owner": "fixture-owner"},
                "reconciliation_rule": {"value": "stable-id", "owner": "fixture-owner"},
            }
            reads = [
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
            ]
            evidence = [
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
            ]
            verification = [
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
            ]
            dependency = DATA_INVARIANTS_ID
        else:
            inputs = {
                "rollback_owner": {"value": "fixture-owner", "owner": "fixture-owner"},
                "rollback_trigger": {
                    "value": "validation-failure",
                    "owner": "fixture-owner",
                },
                "recoverable_boundary": {
                    "value": "target-snapshot",
                    "owner": "fixture-owner",
                },
            }
            reads = [
                {
                    "reference": "skills/tmcp-migration-readiness/SKILL.md",
                    "status": "available",
                    "trust": "committed_source_backed",
                    "owner": "fixture-owner",
                },
                {
                    "reference": "rollback path, cutover, and validation commands",
                    "status": "available",
                    "trust": "sealed_fixture",
                    "owner": "fixture-owner",
                },
            ]
            evidence = [
                {
                    "obligation": "rollback owner, trigger, path, and limitations are recorded",
                    "status": "recorded",
                    "source": "sealed-fixture",
                    "owner": "fixture-owner",
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "cutover validation and recovery evidence is recorded",
                    "status": "recorded",
                    "source": "sealed-fixture",
                    "owner": "fixture-owner",
                    "trust": "sealed_fixture",
                },
            ]
            verification = [
                {
                    "obligation": "rollback conditions are observable and bounded",
                    "status": "passed",
                    "source": "sealed-fixture",
                    "owner": "fixture-owner",
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "acceptance gate covers cutover and recovery",
                    "status": "passed",
                    "source": "sealed-fixture",
                    "owner": "fixture-owner",
                    "trust": "sealed_fixture",
                },
            ]
            dependency = MIGRATION_COMPATIBILITY_ID
        raw: dict[str, object] = {
            "objective": "Perform the state review without using trigger wording.",
            "phase": "planning",
            "semantic_signals": {family: applicability},
            "lexical_candidates": ["reconciliation", "rollback"],
            "inputs": inputs,
            "reads": reads,
            "evidence": evidence,
            "verification": verification,
            "provided_dependencies": [dependency] if include_dependency else [],
            "token_budget": token_budget,
        }
        raw.update(overrides)
        return SemanticContext.from_mapping(raw)

    def test_registry_contract_h1(self) -> None:
        registry = build_h1_registry()
        self.assertEqual(
            registry.ids,
            (
                "process.read.required-sources@0.4.0",
                "process.capture.evidence@0.4.0",
                "process.verify.obligation@0.4.0",
                "process.stop.missing-evidence@0.4.0",
                "domain.data_integrity.reconciliation@0.4.0",
                "domain.migration_readiness.rollback_path@0.4.0",
            ),
        )
        for atom in registry.atoms:
            record = atom.to_dict()
            self.assertEqual(record["schema"], RUNTIME_ATOM_SCHEMA)
            self.assertEqual(record["version"], RUNTIME_ATOM_VERSION)
            for field in (
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
            ):
                self.assertIn(field, record)
        data = registry.get(DATA_RECONCILIATION_ID)
        migration = registry.get(MIGRATION_ROLLBACK_ID)
        assert data is not None
        assert migration is not None
        self.assertIn("domain.data_integrity.reconciliation@0.3.0", data.supersedes)
        self.assertIn(
            "domain.migration_readiness.rollback_path@0.3.0", migration.supersedes
        )
        self.assertNotIn("domain.security_privacy.redaction@0.4.0", registry.ids)

    def test_positive_applicability_does_not_depend_on_literal_trigger_words(
        self,
    ) -> None:
        context = self._context(
            "data_integrity",
            objective="Review the bounded state transition using owned semantic records.",
            lexical_candidates=("",),
        )
        result = compile_behavioral_atoms(context)
        self.assertEqual(result.decision, "admit")
        self.assertIn("domain.data_integrity.reconciliation@0.4.0", result.selected_ids)
        self.assertNotIn("reconciliation", context.objective.lower())

    def test_negative_ambiguous_fail_closed(
        self,
    ) -> None:
        for family in ("data_integrity", "migration_readiness"):
            with self.subTest(family=family, applicability="negative"):
                result = compile_behavioral_atoms(self._context(family, "negative"))
                self.assertEqual(result.decision, "reject")
                self.assertEqual(result.selected_ids, ())
                self.assertEqual(result.domain_selected_ids, ())
            with self.subTest(family=family, applicability="ambiguous"):
                result = compile_behavioral_atoms(
                    self._context(
                        family,
                        "ambiguous",
                        declared_missing_evidence=("owner", "boundary"),
                    )
                )
                self.assertEqual(result.decision, "hold_for_evidence")
                self.assertEqual(result.selected_ids, ())
                self.assertTrue(result.stops)
                self.assertTrue(result.missing)

    def test_phase_reads_evidence_verification_and_trust_are_required(self) -> None:
        contexts = (
            self._context("data_integrity", phase_status="incompatible"),
            self._context("data_integrity", reads=()),
            self._context(
                "data_integrity",
                evidence=(
                    {
                        "obligation": "before/after boundary is recorded",
                        "status": "recorded",
                        "source": "sealed",
                        "owner": "fixture-owner",
                        "trust": "harvested_untrusted",
                    },
                ),
            ),
            self._context(
                "data_integrity",
                verification=(
                    {
                        "obligation": "reconciliation check is run and inspected",
                        "status": "failed",
                        "owner": "fixture-owner",
                        "trust": "sealed_fixture",
                    },
                ),
            ),
        )
        for context in contexts:
            with self.subTest(context=context):
                result = compile_behavioral_atoms(context)
                self.assertEqual(result.decision, "hold_for_evidence")
                self.assertTrue(result.stops)
                self.assertEqual(result.domain_selected_ids, ())

    def test_missing_dependency_and_conflict_resolution_are_fail_closed(self) -> None:
        missing_dependency = compile_behavioral_atoms(
            self._context("data_integrity", include_dependency=False)
        )
        self.assertEqual(missing_dependency.decision, "hold_for_evidence")
        self.assertTrue(
            any(
                "domain.data_integrity.invariants" in item
                for item in missing_dependency.missing
            )
        )

        conflict = compile_behavioral_atoms(
            self._context(
                "data_integrity",
                active_conflicts=("conflict.data_integrity.no_reconciliation",),
            )
        )
        self.assertEqual(conflict.decision, "hold_for_evidence")
        self.assertTrue(any("conflict-resolution" in item for item in conflict.missing))

        resolved = compile_behavioral_atoms(
            self._context(
                "data_integrity",
                active_conflicts=("conflict.data_integrity.no_reconciliation",),
                conflict_resolutions={
                    "conflict.data_integrity.no_reconciliation": "stop/request reconciliation"
                },
            )
        )
        self.assertEqual(resolved.decision, "admit")

    def test_rendering_is_deterministic_and_budget_is_a_hard_stop(self) -> None:
        context = self._context("migration_readiness")
        first = render_atoms(compile_behavioral_atoms(context), target="packet")
        second = render_atoms(compile_behavioral_atoms(context), target="packet")
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            [item.atom_id for item in first.render_records],
            list(first.selected_ids),
        )
        with self.assertRaises(ValueError):
            render_atoms(first, target="provider_prompt")
        budget = compile_behavioral_atoms(
            self._context("migration_readiness", token_budget=10)
        )
        self.assertEqual(budget.decision, "hold_for_evidence")
        self.assertIn("budget.required_atoms_exceed_budget", budget.stops)
        self.assertEqual(budget.selected_ids, ())

    def test_legacy_strings_are_separate_and_never_satisfy_typed_obligations(
        self,
    ) -> None:
        original = "domain.data_integrity.reconciliation"
        projected = legacy_string_projection(original)
        self.assertEqual(
            projected["id"],
            f"legacy.string.{hashlib.sha256(original.encode()).hexdigest()[:16]}",
        )
        self.assertEqual(projected["original"], original)
        self.assertEqual(projected["trust"], "legacy_untrusted")
        result = compile_behavioral_atoms(
            SemanticContext.from_mapping({"legacy_atoms": [original]})
        )
        self.assertEqual(result.decision, "reject")
        self.assertEqual(result.selected_ids, ())
        self.assertEqual(result.legacy_projection[0]["original"], original)

    def test_h1_mapping_invalid_arms(self) -> None:
        mapping = build_h1_advisory_evaluator_mapping()
        self.assertEqual(mapping["provider_cells"], "not_run")
        self.assertEqual(mapping["cross_skill_composition"], "closed_gate")
        self.assertEqual(len(mapping["original"]["atom_refs"]), 2)
        self.assertEqual(len(mapping["ablated"]), 2)
        self.assertEqual(len(mapping["invalid_arms"]), 4)
        for arm in mapping["invalid_arms"]:
            evaluated = evaluate_transplant_arm(arm)
            self.assertEqual(evaluated["status"], "rejected_before_cell")
            self.assertIn(
                evaluated["reason_code"],
                {"duplicate_generic_condition", "no_eligible_variant"},
            )
        for arm in mapping["transplant"][:2]:
            self.assertEqual(
                evaluate_transplant_arm(arm)["status"], "eligible_advisory"
            )
        self.assertEqual(mapping["cross_skill_composition"], "closed_gate")

    def test_cross_skill_composition_has_no_runtime_support(self) -> None:
        result = compile_behavioral_atoms(
            SemanticContext.from_mapping(
                {
                    "semantic_signals": {"cross_skill_composition": "positive"},
                    "requested_atoms": [
                        "domain.data_integrity.reconciliation",
                        "domain.migration_readiness.rollback_path",
                    ],
                }
            )
        )
        self.assertEqual(result.decision, "hold_for_evidence")
        self.assertEqual(result.selected_ids, ())
        self.assertTrue(result.stops)
        self.assertNotIn(
            "domain.data_integrity.reconciliation@0.4.0", result.domain_selected_ids
        )

    def test_sealed_fixtures_consumed(self) -> None:
        fixture_path = Path("tests/fixtures/behavioral-atoms-held-out-v0.3.json")
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        result = evaluate_sealed_behavioral_fixtures(payload["fixtures"])
        self.assertTrue(result["all_fixtures_consumed"])
        self.assertEqual(result["fixture_count"], 12)
        self.assertEqual(sum(1 for case in result["cases"] if case["supported"]), 12)
        for case in result["cases"]:
            self.assertEqual(case["score"]["score"], 1.0)
            self.assertFalse(case["provider_execution"])
        self.assertEqual(result["provider_cells"], "not_run")
        self.assertEqual(result["cross_skill_composition"], "closed_gate")


if __name__ == "__main__":
    unittest.main()
