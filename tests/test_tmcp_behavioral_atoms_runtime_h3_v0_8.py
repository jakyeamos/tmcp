from __future__ import annotations

import json
import unittest
from pathlib import Path

from tmcp_runtime.domain.behavioral_atoms import (
    PROCESS_READ_ID,
    RELEASE_EVIDENCE_LADDER_ID,
    RELEASE_SHIP_GATE_ID,
    SECURITY_REDACTION_ID,
    SECURITY_SECRET_BOUNDARY_ID,
    SemanticContext,
    build_h2_registry,
    build_h3_registry,
    compile_behavioral_atoms,
    render_atoms,
)
from tmcp_runtime.services.behavioral_atom_runtime import (
    build_h3_advisory_evaluator_mapping,
    evaluate_h3_boundary_fixtures,
    evaluate_transplant_arm,
    project_compile_result_to_packet,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests/fixtures/behavioral-atoms-runtime-h3-v0.7.json"


class BehavioralAtomRuntimeH3V08Tests(unittest.TestCase):
    @staticmethod
    def _context(scope: str = "security", **overrides: object) -> SemanticContext:
        owner = "h3-test-owner"
        security = scope in {"security", "combined"}
        release = scope in {"release", "combined"}
        signals: dict[str, str] = {}
        inputs: dict[str, object] = {}
        reads: list[dict[str, str]] = []
        evidence: list[dict[str, str]] = []
        verification: list[dict[str, str]] = []

        def add_input(name: str) -> None:
            inputs[name] = {
                "value": f"owned-{name}",
                "status": "available",
                "owner": owner,
                "trust": "sealed_fixture",
            }

        def add_read(name: str, trust: str = "sealed_fixture") -> None:
            reads.append(
                {
                    "reference": name,
                    "status": "available",
                    "owner": owner,
                    "trust": trust,
                }
            )

        def add_evidence(name: str, trust: str = "sealed_fixture") -> None:
            evidence.append(
                {
                    "obligation": name,
                    "status": "recorded",
                    "source": "tests/fixtures/h3-v0.8-sealed",
                    "owner": owner,
                    "trust": trust,
                }
            )

        def add_verification(name: str, status: str = "passed") -> None:
            verification.append(
                {
                    "obligation": name,
                    "status": status,
                    "source": "tests/fixtures/h3-v0.8-sealed",
                    "owner": owner,
                    "trust": "sealed_fixture",
                }
            )

        if security:
            signals.update(
                {
                    "security_privacy": "positive",
                    "secret_boundary": "positive",
                }
            )
            for name in (
                "authorized_scope",
                "boundary_evidence",
                "sensitive_boundary",
                "evidence_owner",
            ):
                add_input(name)
            add_read(
                "skills/tmcp-security-privacy-audit/SKILL.md", "committed_source_backed"
            )
            add_read(
                "security docs, privacy docs, environment docs, and relevant code boundaries"
            )
            add_read("security, privacy, CI, auth, payment, or data-flow evidence")
            for name in (
                "authorized boundary and evidence gaps are recorded",
                "observed findings are separated from inferred risk",
                "what was redacted and why is recorded",
                "security and privacy evidence gaps are recorded without sensitive values",
            ):
                add_evidence(name)
            for name in (
                "scope ownership is checked before sensitive evidence is used",
                "remediation is checked against the recorded boundary",
                "outputs contain no unredacted sensitive values",
                "each material security claim points to bounded evidence",
            ):
                add_verification(name)

        if release:
            signals.update(
                {
                    "release_readiness": "positive",
                    "evidence_ladder": "positive",
                }
            )
            for name in (
                "quality_ladder",
                "verification_freshness",
                "release_scope",
                "current_quality_evidence",
            ):
                add_input(name)
            add_read(
                "skills/tmcp-release-readiness/SKILL.md", "committed_source_backed"
            )
            add_read(
                "CI config, tests, build scripts, package metadata, and release checklist"
            )
            add_read(
                "project instructions, README, CI, tests, build scripts, and release docs"
            )
            for name in (
                "passed, failed, blocked, not-run, and unknown gates are inventoried",
                "evidence needed for each remediation slice is recorded",
                "current quality and release evidence is recorded",
                "observed blockers, risks, and unknowns are separated",
            ):
                add_evidence(name)
            for name in (
                "quality ladder completeness is checked for the declared release scope",
                "each remediation slice has an acceptance check",
                "required release checks are run or inspected",
                "every ship blocker has a disposition and next gate",
            ):
                add_verification(name)

        raw: dict[str, object] = {
            "objective": "Review the owned boundary using current semantic records.",
            "phase": "planning",
            "semantic_signals": signals,
            "lexical_candidates": [
                "secret",
                "redaction",
                "ship gate",
                "quality ladder",
            ],
            "inputs": inputs,
            "reads": reads,
            "evidence": evidence,
            "verification": verification,
            "token_budget": 1024,
        }
        raw.update(overrides)
        return SemanticContext.from_mapping(raw)

    def test_h3_registry_and_mapping_are_private_and_preregistered(self) -> None:
        h2_ids = build_h2_registry().ids
        h3_ids = build_h3_registry().ids
        self.assertEqual(h3_ids[: len(h2_ids)], h2_ids)
        self.assertEqual(
            h3_ids[-2:],
            (
                "domain.security_privacy.secret_boundary@0.4.0",
                "domain.release_readiness.evidence_ladder@0.4.0",
            ),
        )
        self.assertNotIn("domain.security_privacy.secret_boundary@0.4.0", h2_ids)
        self.assertNotIn("domain.release_readiness.evidence_ladder@0.4.0", h2_ids)
        mapping = build_h3_advisory_evaluator_mapping()
        self.assertEqual(
            [item["id"] for item in mapping["transplant"]],
            [
                "arm.valid.h3.release_receives_secret_boundary",
                "arm.valid.h3.security_receives_evidence_ladder",
            ],
        )
        self.assertEqual(
            [item["id"] for item in mapping["invalid_arms"]],
            [
                "arm.invalid.h3.redaction_alias",
                "arm.invalid.h3.ship_gate_alias",
                "arm.invalid.h3.generic_process_shell",
                "arm.invalid.h3.no_target_obligation",
            ],
        )
        self.assertEqual(mapping["provider_cells"], "not_run")
        self.assertEqual(mapping["cross_skill_composition"], "closed_gate")
        for arm in (*mapping["transplant"], *mapping["invalid_arms"]):
            evaluated = evaluate_transplant_arm(arm)
            self.assertEqual(evaluated["status"], arm.get("status"))
            if arm in mapping["transplant"]:
                self.assertEqual(evaluated["provider_outcome"], "not_run")
                self.assertEqual(evaluated["cross_skill_composition"], "closed_gate")

    def test_positive_secret_release_and_combined_cases_are_deterministic(self) -> None:
        cases = (
            ("security", {SECURITY_SECRET_BOUNDARY_ID, SECURITY_REDACTION_ID}),
            ("release", {RELEASE_EVIDENCE_LADDER_ID, RELEASE_SHIP_GATE_ID}),
            (
                "combined",
                {
                    SECURITY_SECRET_BOUNDARY_ID,
                    SECURITY_REDACTION_ID,
                    RELEASE_EVIDENCE_LADDER_ID,
                    RELEASE_SHIP_GATE_ID,
                },
            ),
        )
        for scope, expected_domain_ids in cases:
            with self.subTest(scope=scope):
                context = self._context(scope)
                first = compile_behavioral_atoms(context, registry=build_h3_registry())
                second = compile_behavioral_atoms(context, registry=build_h3_registry())
                self.assertEqual(first.decision, "admit")
                self.assertEqual(
                    set(first.domain_selected_ids),
                    {f"{item}@0.4.0" for item in expected_domain_ids},
                )
                self.assertIn(f"{PROCESS_READ_ID}@0.4.0", first.selected_ids)
                self.assertEqual(first.to_dict(), second.to_dict())

    def test_frozen_v07_boundary_is_consumed_without_provider_or_composition(
        self,
    ) -> None:
        fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
        report = evaluate_h3_boundary_fixtures(fixtures)
        self.assertEqual(report["fixture_count"], 7)
        self.assertTrue(report["all_fixtures_consumed"])
        self.assertTrue(report["all_fixtures_passed"])
        self.assertEqual(report["provider_cells"], "not_run")
        self.assertEqual(report["cross_skill_composition"], "closed_gate")
        self.assertTrue(all(not case["provider_execution"] for case in report["cases"]))

    def test_h3_aliases_ambiguous_authority_and_generic_process_fail_closed(
        self,
    ) -> None:
        alias = self._context(
            "security",
            semantic_signals={
                "security_privacy": "positive",
                "redaction": "output_transformation_only",
            },
        )
        alias_result = compile_behavioral_atoms(alias, registry=build_h3_registry())
        self.assertNotIn(
            f"{SECURITY_SECRET_BOUNDARY_ID}@0.4.0", alias_result.domain_selected_ids
        )

        generic = self._context(
            "security",
            semantic_signals={
                "security_privacy": "positive",
                "secret_boundary": "generic_process_shell",
            },
        )
        generic_result = compile_behavioral_atoms(generic, registry=build_h3_registry())
        self.assertNotIn(
            f"{SECURITY_SECRET_BOUNDARY_ID}@0.4.0", generic_result.domain_selected_ids
        )

        inferred = self._context(
            "security",
            inputs={
                **dict(self._context("security").inputs),
                "authorized_scope": {
                    "status": "available",
                    "owner": "h3-test-owner",
                    "trust": "sealed_fixture",
                    "authority": "inferred",
                },
            },
        )
        inferred_result = compile_behavioral_atoms(
            inferred, registry=build_h3_registry()
        )
        self.assertEqual(inferred_result.decision, "hold_for_evidence")
        self.assertEqual(inferred_result.domain_selected_ids, ())

    def test_h3_missing_trust_stale_dependency_phase_conflict_and_budget_hold(
        self,
    ) -> None:
        variants = (
            self._context(
                "security",
                inputs={
                    **dict(self._context("security").inputs),
                    "boundary_evidence": {
                        "status": "available",
                        "owner": "h3-test-owner",
                        "trust": "harvested_untrusted",
                    },
                },
            ),
            self._context(
                "release",
                inputs={
                    **dict(self._context("release").inputs),
                    "verification_freshness": {
                        "status": "stale",
                        "owner": "h3-test-owner",
                        "trust": "sealed_fixture",
                    },
                },
            ),
            self._context("security", phase_status="incompatible"),
            self._context("combined", token_budget=1),
            self._context(
                "security",
                active_conflicts=("conflict.security_privacy.inferred_authority",),
            ),
            self._context(
                "security",
                semantic_signals={
                    "security_privacy": "negative",
                    "secret_boundary": "positive",
                },
            ),
        )
        for context in variants:
            with self.subTest(context=context):
                result = compile_behavioral_atoms(context, registry=build_h3_registry())
                self.assertEqual(result.decision, "hold_for_evidence")
                self.assertEqual(result.selected_ids, ())
                self.assertTrue(result.stops)

        incomplete_combined = self._context(
            "combined",
            inputs={
                **dict(self._context("combined").inputs),
                "quality_ladder": {
                    "status": "partial",
                    "owner": "h3-test-owner",
                    "trust": "sealed_fixture",
                },
            },
        )
        incomplete_result = compile_behavioral_atoms(
            incomplete_combined, registry=build_h3_registry()
        )
        self.assertEqual(incomplete_result.decision, "hold_for_evidence")
        self.assertEqual(incomplete_result.selected_ids, ())

    def test_h3_optional_hint_cannot_bypass_semantic_admission(self) -> None:
        context = self._context(
            "security",
            optional_atoms=(RELEASE_EVIDENCE_LADDER_ID,),
        )
        result = compile_behavioral_atoms(context, registry=build_h3_registry())
        h3_optional_id = f"{RELEASE_EVIDENCE_LADDER_ID}@0.4.0"

        self.assertEqual(result.decision, "admit")
        self.assertNotIn(h3_optional_id, result.domain_selected_ids)
        self.assertIn(h3_optional_id, result.deferred)
        rendered = render_atoms(result, target="advisory_trace")
        self.assertNotIn(h3_optional_id, rendered.selected_ids)

    def test_h3_is_opt_in_and_private_projection_is_closed(self) -> None:
        context = self._context("security")
        default_result = compile_behavioral_atoms(context)
        self.assertNotIn(
            f"{SECURITY_SECRET_BOUNDARY_ID}@0.4.0", default_result.selected_ids
        )
        self.assertNotIn(
            f"{RELEASE_EVIDENCE_LADDER_ID}@0.4.0", default_result.selected_ids
        )

        private_result = compile_behavioral_atoms(context, registry=build_h3_registry())
        packet = {"active_atoms": ["legacy.atom"], "stop_conditions": []}
        projected = project_compile_result_to_packet(packet, private_result)
        self.assertEqual(
            projected, {"active_atoms": ["legacy.atom"], "stop_conditions": []}
        )


if __name__ == "__main__":
    unittest.main()
