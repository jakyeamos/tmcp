from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmcp_runtime.domain.routes import validate_proposed_changes
from tests import test_tmcp_mcp_server as helpers
from tests.test_tmcp_skill_family_compose import _write_product_design_family


class TmcpRecompilePacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_validate_proposed_changes_accepts_known_route(self) -> None:
        validated, warnings = validate_proposed_changes(
            [
                {
                    "action": "add_route",
                    "route": "accessibility_validation",
                    "reason": "Found missing aria labels",
                }
            ]
        )
        self.assertEqual(len(validated), 1)
        self.assertEqual(warnings, [])

    def test_validate_proposed_changes_rejects_unknown_route(self) -> None:
        validated, warnings = validate_proposed_changes(
            [{"action": "add_route", "route": "not-a-real-route"}]
        )
        self.assertEqual(validated, [])
        self.assertEqual(len(warnings), 1)

    def test_full_recompile_requires_previous_packet(self) -> None:
        with self.assertRaises(ValueError):
            self.server._runtime_next(
                {
                    "objective": "Implement onboarding UI",
                    "output_mode": "full",
                    "cache_policy": "none",
                }
            )

    def test_full_recompile_after_runtime_phase_adds_implementation_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            previous_packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": "Use product-design-runtime before implementing onboarding UI",
                    "project_path": str(root),
                    "phase": "runtime",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )
            result = self.server._runtime_next(
                {
                    "source_path": str(root),
                    "objective": "Use product-design-runtime before implementing onboarding UI",
                    "project_path": str(root),
                    "current_phase": "runtime",
                    "previous_packet_id": previous_packet["packet_id"],
                    "previous_packet": previous_packet,
                    "latest_user_message": "Product runtime brief is ready.",
                    "output_mode": "full",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        self.assertEqual(result["schema"], "tmcp-recompiled-packet-v0.1")
        self.assertEqual(result["recompile_reason"], "phase_transition")
        self.assertIn(
            "phase_transitions.activate_skills", str(result["packet_diff"]["added"])
        )
        packet = result["packet"]
        self.assertEqual(packet["phase"], "implementation")
        selected = {item["source"] for item in packet["evidence_citations"]}
        self.assertIn(".agents/skills/ui-implementation/SKILL.md", selected)
        markdown = packet["packet_markdown"]
        self.assertIn("## Recompile", markdown)
        self.assertIn("### Added", markdown)
        self.assertIn("ui-implementation", markdown)

    def test_full_recompile_with_ui_changes_moves_to_polish_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            previous_packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": "Implement onboarding UI from product runtime brief",
                    "project_path": str(root),
                    "phase": "implementation",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )
            result = self.server._runtime_next(
                {
                    "source_path": str(root),
                    "objective": "Implement onboarding UI from product runtime brief",
                    "project_path": str(root),
                    "current_phase": "implementation",
                    "previous_packet": previous_packet,
                    "files_changed": ["app/onboarding/page.tsx"],
                    "output_mode": "full",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        self.assertEqual(result["suggested_phase"], "polish-verify")
        packet = result["packet"]
        self.assertEqual(packet["phase"], "polish-verify")
        added = result["packet_diff"]["added"]
        self.assertTrue(
            any(item.get("id") == "ui-polish-verification" for item in added),
            added,
        )

    def test_full_recompile_harvests_once_and_shares_that_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "Read before modifying behavior.\n",
                encoding="utf-8",
            )
            previous_packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": "Implement the onboarding page",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                }
            )
            harvested_nodes: list[dict[str, object]] = []
            prepared_nodes: list[dict[str, object]] = []
            composed_nodes: list[dict[str, object]] = []
            prepared_compositions: list[dict[str, object]] = []
            composed_preflights: list[object] = []
            original_harvest = self.server._harvest_skills
            original_prepare = (
                self.server._runtime_prepare_composition_from_source_nodes
            )
            original_compose = self.server._compose_packet_from_source_nodes

            def harvest(arguments: dict[str, object]) -> dict[str, object]:
                result = original_harvest(arguments)
                harvested_nodes.extend(result["source_nodes"])
                return result

            def prepare(
                arguments: dict[str, object], *, source_nodes: list[dict[str, object]]
            ) -> dict[str, object]:
                prepared_nodes.extend(source_nodes)
                result = original_prepare(arguments, source_nodes=source_nodes)
                prepared_compositions.append(result)
                return result

            def compose(
                arguments: dict[str, object],
                *,
                source_nodes: list[dict[str, object]],
                prepared_composition: dict[str, object] | None = None,
            ) -> dict[str, object]:
                composed_nodes.extend(source_nodes)
                composed_preflights.append(prepared_composition)
                return original_compose(
                    arguments,
                    source_nodes=source_nodes,
                    prepared_composition=prepared_composition,
                )

            with (
                patch.object(
                    self.server, "_harvest_skills", side_effect=harvest
                ) as mocked_harvest,
                patch.object(
                    self.server,
                    "_runtime_prepare_composition_from_source_nodes",
                    side_effect=prepare,
                ),
                patch.object(
                    self.server,
                    "_compose_packet_from_source_nodes",
                    side_effect=compose,
                ),
            ):
                result = self.server._runtime_next(
                    {
                        "source_path": str(root),
                        "objective": "Implement the onboarding page",
                        "project_path": str(root),
                        "current_phase": "start",
                        "previous_packet": previous_packet,
                        "semantic_proposal": {
                            "schema": "tmcp-semantic-proposal-v0.1"
                        },
                        "output_mode": "full",
                        "cache_policy": "none",
                    }
                )

        self.assertFalse(result["ok"])
        self.assertEqual(mocked_harvest.call_count, 1)
        self.assertEqual(prepared_nodes, harvested_nodes)
        self.assertEqual(composed_nodes, harvested_nodes)
        self.assertEqual(len(prepared_compositions), 1)
        self.assertIs(composed_preflights[0], prepared_compositions[0])

    def test_full_recompile_keeps_a_validated_route_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "Read before modifying behavior.\n",
                encoding="utf-8",
            )
            previous_packet = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": "Implement the onboarding page",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                }
            )
            result = self.server._runtime_next(
                {
                    "source_path": str(root),
                    "objective": "Implement the onboarding page",
                    "project_path": str(root),
                    "current_phase": "start",
                    "previous_packet": previous_packet,
                    "output_mode": "full",
                    "cache_policy": "none",
                    "proposed_changes": [
                        {
                            "action": "add_route",
                            "route": "accessibility_validation",
                            "reason": "The form needs an accessibility check.",
                        }
                    ],
                }
            )

        active_routes = result["packet"]["task_identity"]["active_routes"]
        self.assertIn("accessibility_validation", active_routes)
        self.assertEqual(result["task_identity"], result["packet"]["task_identity"])


if __name__ == "__main__":
    unittest.main()
