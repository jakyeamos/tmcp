from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tmcp_runtime.domain.composition_benchmark_protocol import (
    build_benchmark_preparation,
    fixture_source_nodes,
    prepare_fixture_preflight,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
ROUTING_PATH = FIXTURES / "composition_routing_golden_v0_6.json"
BEHAVIORAL_PATH = FIXTURES / "composition_behavioral_fixtures_v0_6.json"


def _payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must contain an object")
    return payload


class CompositionFixtureQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routing = _payload(ROUTING_PATH)
        cls.behavioral = _payload(BEHAVIORAL_PATH)

    def test_expected_skills_have_observable_contracts_in_preflight(self) -> None:
        for fixture in self.behavioral["fixtures"]:
            expected = {str(skill_id) for skill_id in fixture["expected_skill_ids"]}
            sources = {
                str(source["skill_id"]): source
                for source in fixture["skill_sources"]
            }
            for skill_id in expected:
                self.assertIn("output contract", str(sources[skill_id]["content"]).casefold())

            preflight = prepare_fixture_preflight(
                fixture=fixture,
                objective=str(fixture["objective"]),
            )
            nodes = {
                str(node["skill_id"]): str(node["id"])
                for node in fixture_source_nodes(fixture)
            }
            selected = set(
                preflight["diagnostics"]["semantic_evidence"]["selected_active_source_ids"]
            )
            slices_by_skill = {
                str(item["title"]): item
                for item in preflight["candidate_source_slices"]
            }
            for skill_id in expected:
                self.assertIn(nodes[skill_id], selected)
                self.assertEqual(slices_by_skill[skill_id]["source_role"], "active_skill")
                self.assertTrue(slices_by_skill[skill_id]["explicitly_scoped"])
                self.assertIn("output contract", str(slices_by_skill[skill_id]["content"]).casefold())

    def test_preparation_rejects_expected_skill_without_observable_contract(self) -> None:
        behavioral = copy.deepcopy(self.behavioral)
        fixture = behavioral["fixtures"][0]
        source = fixture["skill_sources"][0]
        source["content"] = str(source["content"]).replace(
            "Output contract:", "Output specification:", 1
        )

        with self.assertRaisesRegex(ValueError, "Output contract"):
            build_benchmark_preparation(
                routing_golden=self.routing,
                behavioral_fixtures=behavioral,
            )


if __name__ == "__main__":
    unittest.main()
