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
        ):
            with self.subTest(case_id=case_id):
                case = self.cases[case_id]
                expected = case["expected"]
                identity = derive_task_identity(str(case["objective"]))

                self.assertEqual(identity["primary"], expected["primary"])
                if "active_routes" in expected:
                    self.assertEqual(identity["active_routes"], expected["active_routes"])
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
            harvest_priority(active_source, str(case["active_source"]), "skill_definition")[
                0
            ],
        )
