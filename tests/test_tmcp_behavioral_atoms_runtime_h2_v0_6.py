from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from tmcp_runtime.domain.behavioral_atoms import (
    RELEASE_SHIP_GATE_ID,
    SECURITY_REDACTION_ID,
    SemanticContext,
    build_h1_registry,
    build_h2_registry,
    compile_behavioral_atoms,
    render_atoms,
)
from tmcp_runtime.services.behavioral_atom_runtime import (
    build_h2_advisory_evaluator_mapping,
    evaluate_sealed_behavioral_fixtures,
    evaluate_transplant_arm,
)


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = (
    next(
        path
        for path in (ROOT / "docs" / "experiments").iterdir()
        if path.name.endswith("ship-gate-v0.6.json")
    )
)


class BehavioralAtomRuntimeH2V06Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.decision = json.loads(DECISION_PATH.read_text(encoding="utf-8"))

    @staticmethod
    def _context(
        family: str,
        applicability: str = "positive",
        *,
        token_budget: int = 512,
        **overrides: object,
    ) -> SemanticContext:
        owner = "sealed-h2-owner"
        if family == "security_privacy":
            inputs = {
                "sensitive_boundary": {
                    "value": "owned-redaction-policy",
                    "owner": owner,
                },
                "evidence_owner": {"value": owner, "owner": owner},
            }
            reads = [
                {
                    "reference": "skills/tmcp-security-privacy-audit/SKILL.md",
                    "status": "available",
                    "trust": "committed_source_backed",
                    "owner": owner,
                },
                {
                    "reference": "security, privacy, CI, auth, payment, or data-flow evidence",
                    "status": "available",
                    "trust": "sealed_fixture",
                    "owner": owner,
                },
            ]
            evidence = [
                {
                    "obligation": "what was redacted and why is recorded",
                    "status": "recorded",
                    "source": "sealed-h2",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "security and privacy evidence gaps are recorded without sensitive values",
                    "status": "recorded",
                    "source": "sealed-h2",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
            ]
            verification = [
                {
                    "obligation": "outputs contain no unredacted sensitive values",
                    "status": "passed",
                    "source": "sealed-h2",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "each material security claim points to bounded evidence",
                    "status": "passed",
                    "source": "sealed-h2",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
            ]
        else:
            inputs = {
                "release_scope": {"value": "owned-release-scope", "owner": owner},
                "current_quality_evidence": {
                    "value": "current-quality-output",
                    "owner": owner,
                },
            }
            reads = [
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
            ]
            evidence = [
                {
                    "obligation": "current quality and release evidence is recorded",
                    "status": "recorded",
                    "source": "sealed-h2",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "observed blockers, risks, and unknowns are separated",
                    "status": "recorded",
                    "source": "sealed-h2",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
            ]
            verification = [
                {
                    "obligation": "required release checks are run or inspected",
                    "status": "passed",
                    "source": "sealed-h2",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
                {
                    "obligation": "every ship blocker has a disposition and next gate",
                    "status": "passed",
                    "source": "sealed-h2",
                    "owner": owner,
                    "trust": "sealed_fixture",
                },
            ]
        raw: dict[str, object] = {
            "objective": "Review the owned boundary using semantic records.",
            "phase": "planning",
            "semantic_signals": {family: applicability},
            "lexical_candidates": ["redaction", "ship gate"],
            "inputs": inputs,
            "reads": reads,
            "evidence": evidence,
            "verification": verification,
            "token_budget": token_budget,
        }
        raw.update(overrides)
        return SemanticContext.from_mapping(raw)

    def test_versioned_decision_is_h2(self) -> None:
        self.assertRegex(self.decision["schema"], r"^tmcp-[a-z0-9-]+-v\d+\.\d+$")
        self.assertEqual(self.decision["schema"].rsplit("-v", 1)[-1], "0.6")
        admitted = self.decision["decision"]["admitted_atoms"]
        self.assertEqual(
            [item["id"] for item in admitted],
            [
                "domain.security_privacy.redaction@0.4.0",
                "domain.release_readiness.ship_gate@0.4.0",
            ],
        )
        for item in admitted:
            source = ROOT / item["source_path"]
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(), item["source_sha256"]
            )
        self.assertFalse(self.decision["compatibility"]["provider_execution"])
        self.assertFalse(self.decision["compatibility"]["cross_skill_composition"])
        self.assertFalse(self.decision["compatibility"]["public_contract_change"])

    def test_h2_registry_extends_h1(self) -> None:
        h1_ids = build_h1_registry().ids
        h2_ids = build_h2_registry().ids
        self.assertEqual(h2_ids[: len(h1_ids)], h1_ids)
        self.assertEqual(
            h2_ids[len(h1_ids) :],
            (
                "domain.security_privacy.redaction@0.4.0",
                "domain.release_readiness.ship_gate@0.4.0",
            ),
        )
        security = build_h2_registry().get(SECURITY_REDACTION_ID)
        release = build_h2_registry().get(RELEASE_SHIP_GATE_ID)
        assert security is not None
        assert release is not None
        self.assertEqual(
            security.supersedes,
            ("domain.security_privacy.redaction@0.3.0",),
        )
        self.assertEqual(
            release.supersedes,
            ("domain.release_readiness.ship_gate@0.3.0",),
        )
        self.assertNotIn("domain.security_privacy.secret_boundary@0.4.0", h2_ids)
        self.assertNotIn("domain.release_readiness.evidence_ladder@0.4.0", h2_ids)

    def test_positive_h2_applicability(self) -> None:
        cases = {
            "security_privacy": "domain.security_privacy.redaction@0.4.0",
            "release_readiness": "domain.release_readiness.ship_gate@0.4.0",
        }
        for family, atom_id in cases.items():
            with self.subTest(family=family):
                context = self._context(
                    family,
                    objective="Inspect the owned boundary using current records.",
                    lexical_candidates=(),
                )
                first = compile_behavioral_atoms(context)
                second = compile_behavioral_atoms(context)
                self.assertEqual(first.decision, "admit")
                self.assertIn(atom_id, first.domain_selected_ids)
                self.assertEqual(first.to_dict(), second.to_dict())
                self.assertEqual(
                    render_atoms(first, target="packet").to_dict(),
                    render_atoms(second, target="packet").to_dict(),
                )

    def test_negative_and_ambiguous_h2(self) -> None:
        for family in ("security_privacy", "release_readiness"):
            with self.subTest(family=family, applicability="negative"):
                result = compile_behavioral_atoms(self._context(family, "negative"))
                self.assertEqual(result.decision, "reject")
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
                self.assertEqual(result.domain_selected_ids, ())
                self.assertTrue(result.stops)

    def test_h2_gates_fail_closed(self) -> None:
        contexts = (
            self._context("security_privacy", phase_status="incompatible"),
            self._context("security_privacy", inputs={}),
            self._context("security_privacy", reads=()),
            self._context(
                "security_privacy",
                evidence=(
                    {
                        "obligation": "what was redacted and why is recorded",
                        "status": "recorded",
                        "source": "sealed-h2",
                        "owner": "sealed-h2-owner",
                        "trust": "harvested_untrusted",
                    },
                ),
            ),
            self._context(
                "release_readiness",
                verification=(
                    {
                        "obligation": "required release checks are run or inspected",
                        "status": "failed",
                        "owner": "sealed-h2-owner",
                        "trust": "sealed_fixture",
                    },
                ),
            ),
            self._context("release_readiness", token_budget=10),
            self._context(
                "release_readiness",
                active_conflicts=("conflict.release_readiness.unverified_ship",),
            ),
        )
        for context in contexts:
            with self.subTest(context=context):
                result = compile_behavioral_atoms(context)
                self.assertEqual(result.decision, "hold_for_evidence")
                self.assertEqual(result.domain_selected_ids, ())
                self.assertTrue(result.stops)
        resolved = compile_behavioral_atoms(
            self._context(
                "release_readiness",
                active_conflicts=("conflict.release_readiness.unverified_ship",),
                conflict_resolutions={
                    "conflict.release_readiness.unverified_ship": "stop/name evidence gap and blocker"
                },
            )
        )
        self.assertEqual(resolved.decision, "admit")

    def test_h2_mapping_stays_static(self) -> None:
        mapping = build_h2_advisory_evaluator_mapping()
        self.assertEqual(mapping["original"]["id"], "H2.redaction_and_ship_gate")
        self.assertEqual(len(mapping["ablated"]), 2)
        self.assertEqual(len(mapping["transplant"]), 2)
        self.assertEqual(mapping["provider_cells"], "not_run")
        self.assertEqual(mapping["cross_skill_composition"], "closed_gate")
        for arm in mapping["transplant"]:
            evaluated = evaluate_transplant_arm(arm)
            self.assertEqual(evaluated["status"], "eligible_advisory")
            self.assertEqual(evaluated["provider_outcome"], "not_run")
            self.assertEqual(evaluated["cross_skill_composition"], "closed_gate")
        for arm in mapping["invalid_arms"]:
            self.assertEqual(
                evaluate_transplant_arm(arm)["status"], "rejected_before_cell"
            )
        h3 = compile_behavioral_atoms(
            SemanticContext.from_mapping(
                {
                    "requested_atoms": [
                        "domain.security_privacy.secret_boundary@0.4.0",
                        "domain.release_readiness.evidence_ladder@0.4.0",
                    ]
                }
            )
        )
        self.assertEqual(h3.decision, "hold_for_evidence")
        self.assertEqual(h3.domain_selected_ids, ())
        self.assertTrue(all(item.startswith("unregistered:") for item in h3.missing))

    def test_all_sealed_fixtures_are_statically_supported_without_provider_calls(
        self,
    ) -> None:
        fixture_path = ROOT / "tests/fixtures/behavioral-atoms-held-out-v0.3.json"
        fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))["fixtures"]
        report = evaluate_sealed_behavioral_fixtures(fixtures)
        self.assertEqual(report["fixture_count"], 12)
        self.assertTrue(report["all_fixtures_consumed"])
        self.assertTrue(all(case["supported"] for case in report["cases"]))
        self.assertTrue(all(case["score"]["score"] == 1.0 for case in report["cases"]))
        self.assertFalse(
            any(case.get("provider_execution") for case in report["cases"])
        )
        self.assertEqual(report["provider_cells"], "not_run")
        self.assertEqual(report["cross_skill_composition"], "closed_gate")


if __name__ == "__main__":
    unittest.main()
