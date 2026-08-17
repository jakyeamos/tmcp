from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.domain.admission import (
    apply_packet_utility_gate,
    decide_admission,
)
from tmcp_runtime.domain.routes import derive_task_identity


class TmcpAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_typed_route_matrix_separates_implementation_from_audits(self) -> None:
        cases = {
            "Implement a REST API endpoint in the backend service.": "backend_api_implementation",
            "Run a schema migration and database backfill.": "data_database_migration",
            "Fix vulnerability exposure with a security remediation.": "security_remediation",
            "Update API documentation and the developer guide.": "documentation",
            "Create a test strategy and test coverage plan.": "test_strategy",
            "Record an architecture decision for the system architecture.": "architecture_decision",
            "Design an agent workflow and agent handoff.": "agent_workflow",
            "Audit security and release readiness before shipping.": "explicit_audit",
        }
        for objective, expected in cases.items():
            with self.subTest(objective=objective):
                identity = derive_task_identity(objective)
                self.assertEqual(identity["primary"], expected)
                self.assertGreaterEqual(identity["confidence"], 0.6)

    def test_creation_stays_primary_when_audit_is_a_subordinate_phase(self) -> None:
        objective = (
            "Design the agent workflow, define routing, audit safety boundaries, "
            "and verify receipts before promotion."
        )
        identity = derive_task_identity(objective)

        self.assertEqual(identity["primary"], "agent_workflow")
        self.assertIn("explicit_audit", identity["secondary"])
        self.assertEqual(
            derive_task_identity(
                "Audit agent workflow safety and review findings before promotion."
            )["primary"],
            "explicit_audit",
        )

    def test_research_writing_review_sequence_is_multi_phase(self) -> None:
        objective = (
            "Research sources, write the domain artifact, review the draft, "
            "and verify all citations."
        )
        identity = derive_task_identity(objective)
        decision = decide_admission(objective, identity, mode="automatic", context={})

        self.assertEqual(identity["primary"], "freshness_research")
        self.assertEqual(decision["action"], "compose")
        self.assertGreaterEqual(decision["complexity_score"], 2)

    def test_admission_routing_corpus_covers_positive_negative_and_ambiguous_prompts(self) -> None:
        fixture_path = (
            Path(__file__).parent
            / "fixtures"
            / "admission-routing-matrix-v0.1.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema"], "tmcp-admission-routing-matrix-v0.1")
        self.assertGreaterEqual(len(fixture["cases"]), 30)

        for case in fixture["cases"]:
            objective = case["objective"]
            with self.subTest(objective=objective):
                identity = derive_task_identity(objective)
                admission = decide_admission(
                    objective,
                    identity,
                    mode="automatic",
                    context={},
                )
                self.assertEqual(identity["primary"], case["primary"])
                self.assertEqual(admission["action"], case["automatic_action"])

    def test_backend_and_database_signals_negate_frontend_false_positives(self) -> None:
        for objective in (
            "Implement a REST API endpoint in the backend.",
            "Build a database schema migration and backfill.",
        ):
            with self.subTest(objective=objective):
                identity = derive_task_identity(objective)
                self.assertNotIn(
                    "frontend_implementation", identity["active_routes"]
                )

    def test_scope_exclusions_do_not_create_release_routes_or_complexity(self) -> None:
        observed_objective = (
            "Dogfood TMCP invocation admission again using held-out source-bound "
            "tasks, fresh blinded runners, separate judges, repeated trials, and "
            "no release or publication."
        )
        identity = derive_task_identity(observed_objective)
        decision = decide_admission(
            observed_objective, identity, mode="automatic", context={}
        )

        self.assertEqual(identity["primary"], "test_strategy")
        self.assertNotIn("release_readiness", identity["active_routes"])
        self.assertEqual(decision["action"], "compose")

        excluded = derive_task_identity(
            "Do not release or deploy this change; return the requested explanation."
        )
        self.assertNotIn("release_readiness", excluded["active_routes"])

    def test_release_route_remains_for_positive_and_ambiguous_language(self) -> None:
        for objective in (
            "Prepare the production release and verify the changelog.",
            "The release is not blocked; verify the changelog before shipping.",
            "Do not claim release readiness until hosted evidence is recorded.",
        ):
            with self.subTest(objective=objective):
                self.assertIn(
                    "release_readiness",
                    derive_task_identity(objective)["active_routes"],
                )

    def test_automatic_admission_bypasses_trivial_and_unresolved_requests(self) -> None:
        for objective in (
            "Translate this sentence to French.",
            "Explain dependency injection.",
            "Improve this.",
        ):
            with self.subTest(objective=objective):
                identity = derive_task_identity(objective)
                decision = decide_admission(
                    objective, identity, mode="automatic", context={}
                )
                self.assertEqual(decision["action"], "bypass")

    def test_shadow_reports_recommendation_without_authorizing_injection(self) -> None:
        objective = (
            "Implement a REST API endpoint, update API documentation, then verify "
            "failure behavior across services."
        )
        identity = derive_task_identity(objective)
        decision = decide_admission(objective, identity, mode="shadow", context={})

        self.assertEqual(decision["action"], "shadow")
        self.assertEqual(decision["recommended_action"], "compose")
        self.assertEqual(decision["expected_value"], "high")

    def test_forced_mode_discloses_low_expected_value(self) -> None:
        objective = "Translate this sentence to French."
        decision = decide_admission(
            objective,
            derive_task_identity(objective),
            mode="forced",
            context={},
        )

        self.assertEqual(decision["action"], "forced")
        self.assertEqual(decision["recommended_action"], "bypass")
        self.assertEqual(decision["expected_value"], "low")

    def test_packet_utility_gate_downgrades_empty_automatic_composition(self) -> None:
        decision = {
            "mode": "automatic",
            "action": "compose",
            "recommended_action": "compose",
            "expected_value": "high",
            "reasons": [],
        }
        gated = apply_packet_utility_gate(
            decision,
            selected_source_count=1,
            task_specific_contribution_count=0,
        )

        self.assertEqual(gated["action"], "bypass")
        self.assertEqual(gated["packet_utility"], "insufficient")

    def test_automatic_bypass_skips_sources_and_emits_a_small_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "audit" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("# Audit\nRun a detailed audit.\n", encoding="utf-8")
            packet = self.server._compose_packet(
                {
                    "objective": "Translate this sentence to French.",
                    "project_path": str(root),
                    "source_path": str(root),
                    "admission_mode": "automatic",
                    "cache_policy": "none",
                }
            )

        self.assertEqual(packet["status"], "bypassed")
        self.assertEqual(packet["evidence_citations"], [])
        self.assertFalse(packet["shortcut_candidate"]["matched"])
        self.assertLess(len(packet["packet_markdown"]), 1000)

    def test_harvest_excludes_test_and_fixture_sources_without_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            production = root / "skills" / "backend" / "SKILL.md"
            fixture = root / "tests" / "fixtures" / "audit" / "SKILL.md"
            production.parent.mkdir(parents=True)
            fixture.parent.mkdir(parents=True)
            production.write_text("# Backend\nImplement API endpoints.\n", encoding="utf-8")
            fixture.write_text("# Fixture Audit\nStop for audit.\n", encoding="utf-8")

            default = self.server._harvest_skills({"source_path": str(root)})
            opted_in = self.server._harvest_skills(
                {"source_path": str(root), "include_test_sources": True}
            )

        default_paths = {node["relative_path"] for node in default["source_nodes"]}
        opted_in_paths = {node["relative_path"] for node in opted_in["source_nodes"]}
        self.assertIn("skills/backend/SKILL.md", default_paths)
        self.assertNotIn("tests/fixtures/audit/SKILL.md", default_paths)
        self.assertIn("tests/fixtures/audit/SKILL.md", opted_in_paths)

    def test_invocation_policy_pilot_is_balanced_and_blinded(self) -> None:
        root = Path(__file__).parents[1]
        pilot_path = (
            root
            / "examples"
            / "workflows"
            / "invocation-admission-pilot.json"
        )
        pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
        rows = (
            len(pilot["tasks"])
            * len(pilot["policies"])
            * pilot["repeats_per_cell"]
        )

        self.assertEqual(pilot["schema"], "tmcp-invocation-admission-pilot-v0.2")
        self.assertEqual(rows, pilot["matrix_rows"])
        self.assertEqual(rows, 36)
        self.assertTrue(pilot["assignment"]["randomized"])
        self.assertTrue(pilot["assignment"]["judge_blinded_to_policy"])
        self.assertFalse(pilot["assignment"]["runner_receives_bar"])
        self.assertFalse(pilot["assignment"]["judge_receives_policy_label"])
        self.assertTrue(pilot["assignment"]["fresh_runner_per_row"])
        self.assertTrue(pilot["assignment"]["fresh_judge_per_artifact"])
        self.assertEqual(
            {policy["id"] for policy in pilot["policies"]},
            {"explicit-only", "always-on", "admission-controlled"},
        )
        self.assertIn("evidence_boundary", pilot)

        composition_fixture = json.loads(
            (root / "tests" / "fixtures" / "composition_behavioral_fixtures_v0_6.json")
            .read_text(encoding="utf-8")
        )
        individual_fixture = json.loads(
            (
                root
                / "tests"
                / "fixtures"
                / "skill-fixtures"
                / "individual-skill-admission-cases-v0.1.json"
            ).read_text(encoding="utf-8")
        )
        composition_cases = {
            case["fixture_id"]: case for case in composition_fixture["fixtures"]
        }
        individual_cases = {
            case["case_id"]: case for case in individual_fixture["cases"]
        }

        for task in pilot["tasks"]:
            with self.subTest(task=task["id"]):
                if task["fixture_id"] in composition_cases:
                    case = composition_cases[task["fixture_id"]]
                    objective = case["objective"]
                    context = case["task_context"]
                    self.assertEqual(task["prompt"], objective)
                    self.assertGreaterEqual(
                        len(case["quality_rubric"]["dimensions"]), 3
                    )
                    self.assertTrue(case["expected_order"])
                    self.assertTrue(case["incompatible_skill_pairs"])
                else:
                    case = individual_cases[task["fixture_id"]]
                    objective = case["prompt"]
                    context = {}
                    self.assertEqual(task["prompt"], objective)
                    self.assertTrue(case["bar"])
                    self.assertTrue(case["smells"])
                    self.assertEqual(case["execution_boundary"]["status"], "complete")
                identity = derive_task_identity(objective, context)
                admission = decide_admission(
                    objective,
                    identity,
                    mode="automatic",
                    context=context,
                )
                # This manifest freezes the v0.2 experimental assignment. Its
                # recorded expectation is historical evidence, not a permanent
                # contract that prevents later admission-policy improvements.
                self.assertIn(task["expected_automatic_action"], {"compose", "bypass"})
                self.assertIn(admission["action"], {"compose", "bypass"})


if __name__ == "__main__":
    unittest.main()
