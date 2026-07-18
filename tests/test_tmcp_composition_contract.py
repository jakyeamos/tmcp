from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.domain.harvest_nodes import harvest_priority
from tmcp_runtime.domain.routes import derive_task_identity


FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "composition-contract-v1.json"
)


def _cases_by_id() -> dict[str, dict[str, Any]]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {str(case["id"]): case for case in payload["cases"]}


class CompositionContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()
        cls.cases = _cases_by_id()

    def test_preregistered_task_identity_cases(self) -> None:
        for case_id in (
            "research_goal_is_not_frontend",
            "explicit_frontend_control_remains_routed",
            "user_reaction_is_not_react",
            "implementation_evidence_is_not_frontend",
            "source_bundle_is_not_performance",
        ):
            with self.subTest(case_id=case_id):
                case = self.cases[case_id]
                expected = case["expected"]
                identity = derive_task_identity(str(case["objective"]))

                self.assertEqual(identity["primary"], expected["primary"])
                if "active_routes" in expected:
                    self.assertEqual(
                        identity["active_routes"], expected["active_routes"]
                    )
                else:
                    for route in expected["active_routes_include"]:
                        self.assertIn(route, identity["active_routes"])

    def test_test_fixture_remains_evidence_only_during_composition(self) -> None:
        case = self.cases["test_fixture_is_evidence_only"]
        expected = case["expected"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active_source = root / str(case["active_source"])
            active_source.parent.mkdir(parents=True)
            active_source.write_text(
                "# Composition Research\n"
                "Use skill composition evidence and read "
                "`tests/fixtures/skills/approval-before-edit/SKILL.md`.\n",
                encoding="utf-8",
            )
            fixture_source = root / str(case["fixture_source"])
            fixture_source.parent.mkdir(parents=True)
            fixture_source.write_text(
                "# Approval Fixture\n"
                f"{case['fixture_directive']}: never include this in a live packet.\n",
                encoding="utf-8",
            )

            harvested = self.server._harvest_skills(
                {
                    "source_path": str(root),
                    "objective": str(case["objective"]),
                    "limit": 20,
                }
            )
            packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "project_path": str(root),
                    "objective": str(case["objective"]),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 20,
                }
            )

        fixture_node = next(
            node
            for node in harvested["source_nodes"]
            if node["relative_path"] == case["fixture_source"]
        )
        citations = {citation["source"] for citation in packet["evidence_citations"]}
        active_text = "\n".join(packet["active_instructions"])

        self.assertEqual(fixture_node["source_type"], expected["source_type"])
        self.assertIn(case["active_source"], citations)
        self.assertNotIn(case["fixture_source"], citations)
        self.assertNotIn(case["fixture_directive"], active_text)
        self.assertNotIn(case["fixture_source"], packet["required_reads"])
        self.assertGreater(
            harvest_priority(
                fixture_source,
                str(case["fixture_source"]),
                fixture_node["source_type"],
            )[0],
            harvest_priority(
                active_source, str(case["active_source"]), "skill_definition"
            )[0],
        )

    def test_owner_consumer_source_projects_consumer_verification_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "SKILL.md"
            source.write_text(
                "---\nname: clean-refactor\n---\n"
                "# Clean Refactoring\n"
                "Identify every owner and consumer, then verify behavior through "
                "consumers rather than only the new owner.\n",
                encoding="utf-8",
            )
            packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "project_path": str(root),
                    "objective": (
                        "Plan removal of an obsolete owner only after mapping "
                        "consumers and verification."
                    ),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 20,
                }
            )

        self.assertEqual(packet["task_identity"]["primary"], "general_task")
        self.assertIn(
            "Verify behavior through identified consumers, not only the owner.",
            packet["verification_gates"],
        )
        self.assertEqual(packet["evidence_citations"][0]["source"], "SKILL.md")

    def test_wizard_source_projects_confirmation_and_static_trace_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "SKILL.md"
            source.write_text(
                "---\nname: wizard\n---\n"
                "# Wizard\n"
                "Use `confirm` before any irreversible action.\n"
                "Don't run it end-to-end yourself; trace it statically.\n",
                encoding="utf-8",
            )
            packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "project_path": str(root),
                    "objective": (
                        "Design a dry-run wizard handoff using synthetic values, "
                        "a static trace, and confirmation."
                    ),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 20,
                }
            )

        self.assertEqual(packet["task_identity"]["primary"], "general_task")
        self.assertIn(
            "Wait for explicit user confirmation before irreversible or external actions.",
            packet["stop_conditions"],
        )
        self.assertIn(
            "Do not run a human-interactive wizard end-to-end; trace it statically.",
            packet["verification_gates"],
        )
        self.assertEqual(packet["evidence_citations"][0]["source"], "SKILL.md")

    def test_branch_fold_source_projects_preservation_and_proof_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "SKILL.md"
            source.write_text(
                "---\nname: fold-feature-branches\n---\n"
                "# Fold Feature Branches\n"
                "Treat the fetched remote target as canonical truth; verify the live "
                "remote head again before promotion and pruning.\n"
                "Preserve every dirty worktree and every branch with unique or "
                "ambiguous work.\n"
                "Never force-push, rebase a source branch, use `git branch -D`, or "
                "bypass hooks on uncertain evidence.\n"
                "Use ancestry and `git cherry` patch equivalence before claiming "
                "that work is redundant.\n",
                encoding="utf-8",
            )
            packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "project_path": str(root),
                    "objective": (
                        "Run a read-only synthetic branch fold audit with remote "
                        "truth and patch equivalence checks."
                    ),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 20,
                }
            )

        self.assertEqual(packet["task_identity"]["primary"], "general_task")
        self.assertIn(
            "Preserve dirty worktrees and branches with unique or ambiguous work; "
            "do not prune on uncertain evidence.",
            packet["stop_conditions"],
        )
        self.assertIn(
            "Do not force-push, force-delete branches, or bypass hooks while "
            "branch evidence is uncertain.",
            packet["stop_conditions"],
        )
        self.assertIn(
            "Verify the live remote target head before any promotion or pruning.",
            packet["verification_gates"],
        )
        self.assertIn(
            "Verify ancestry and git cherry patch equivalence before declaring a "
            "branch superseded.",
            packet["verification_gates"],
        )
        self.assertEqual(packet["evidence_citations"][0]["source"], "SKILL.md")

    def test_opencli_autofix_source_projects_hard_stops_and_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "SKILL.md"
            source.write_text(
                "---\nname: opencli-autofix\n---\n"
                "# OpenCLI AutoFix\n"
                "AUTH_REQUIRED and BROWSER_CONNECT are hard stops: do not modify "
                "code.\n"
                "Only modify the file at `RepairContext.adapter.sourcePath`.\n"
                "Never modify `src/`, `extension/`, `tests/`, `package.json`, or "
                "`tsconfig.json`.\n"
                "Max 3 repair rounds per failure.\n"
                "Ask the user before filing an upstream issue.\n",
                encoding="utf-8",
            )
            packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "project_path": str(root),
                    "objective": (
                        "Plan a synthetic OpenCLI repair for BROWSER_CONNECT with "
                        "an adapter scope and a retry boundary."
                    ),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 20,
                }
            )

        self.assertEqual(packet["task_identity"]["primary"], "general_task")
        self.assertIn(
            "On AUTH_REQUIRED or BROWSER_CONNECT, do not modify code; ask the user "
            "to restore the local environment.",
            packet["stop_conditions"],
        )
        self.assertIn(
            "Modify only RepairContext.adapter.sourcePath.",
            packet["stop_conditions"],
        )
        self.assertIn(
            "Do not modify OpenCLI core, extension, test, or package configuration "
            "files during adapter repair.",
            packet["stop_conditions"],
        )
        self.assertIn(
            "Stop after three failed repair rounds and report what was tried.",
            packet["stop_conditions"],
        )
        self.assertIn(
            "Obtain explicit user confirmation before filing an upstream issue.",
            packet["stop_conditions"],
        )
        self.assertNotIn("ui-browser-verification", packet["active_atoms"])
        self.assertNotIn(
            "Verify contrast on visible UI states.", packet["verification_gates"]
        )
        self.assertIn("## Stop Conditions", packet["packet_markdown"])
        self.assertIn(
            "Modify only RepairContext.adapter.sourcePath.",
            packet["packet_markdown"],
        )
        self.assertEqual(packet["evidence_citations"][0]["source"], "SKILL.md")
