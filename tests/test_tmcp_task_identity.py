from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tmcp_runtime.domain.routes import (
    derive_task_identity,
    score_routes,
    task_identity_delta,
)
from tests import test_tmcp_mcp_server as helpers


REDESIGN_OBJECTIVE = (
    "Redesign these pages. Make them visually striking, interactive, modern, "
    "motion-rich, and production-ready."
)


class TmcpRouteCatalogTests(unittest.TestCase):
    def test_redesign_prompt_scores_multiple_routes(self) -> None:
        signals = score_routes(REDESIGN_OBJECTIVE)
        routes = {item["route"] for item in signals}
        self.assertIn("ui_ux_redesign", routes)
        self.assertIn("motion_interaction", routes)
        self.assertIn("frontend_implementation", routes)

    def test_derive_task_identity_uses_composite_primary(self) -> None:
        identity = derive_task_identity(REDESIGN_OBJECTIVE)
        self.assertEqual(identity["primary"], "frontend_product_redesign")
        self.assertIn("motion_interaction", identity["active_routes"])
        self.assertIn("ui_ux_redesign", identity["active_routes"])
        self.assertIn("frontend_implementation", identity["active_routes"])
        self.assertGreater(float(identity["confidence"]), 0.5)

    def test_ui_file_changes_keep_implementation_route(self) -> None:
        intake = derive_task_identity(REDESIGN_OBJECTIVE)
        runtime = derive_task_identity(
            REDESIGN_OBJECTIVE,
            {"files_changed": ["app/page.tsx"]},
        )
        self.assertIn("frontend_implementation", runtime["active_routes"])
        self.assertIn("frontend_implementation", intake["active_routes"])

    def test_task_identity_delta_reports_primary_change(self) -> None:
        previous = derive_task_identity("Debug the failing login test")
        current = derive_task_identity("Redesign the login page")
        delta = task_identity_delta(previous, current, reason="user_redirect")
        self.assertIsNotNone(delta)
        assert delta is not None
        self.assertNotEqual(delta["previous"]["primary"], delta["current"]["primary"])
        self.assertEqual(delta["reason"], "user_redirect")


class TmcpComposedPacketIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_compose_packet_includes_task_identity_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / ".agents" / "skills" / "frontend-design"
            skill_dir.mkdir(parents=True)
            skill_dir.joinpath("SKILL.md").write_text(
                "# Frontend Design\nUse existing components before redesigning.\n",
                encoding="utf-8",
            )
            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": REDESIGN_OBJECTIVE,
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 10,
                }
            )

        identity = result["task_identity"]
        self.assertEqual(identity["primary"], "frontend_product_redesign")
        self.assertIn("task_identity", result)
        self.assertIn("compiled_from", result)
        self.assertIn("packet_markdown", result)
        markdown = result["packet_markdown"]
        self.assertIn("## Task Identity", markdown)
        self.assertIn("frontend_product_redesign", markdown)
        self.assertIn("## Active Routes", markdown)
        self.assertIn("## Selection Rationale", markdown)
        self.assertIn("## Required Receipts", markdown)

    def test_runtime_next_includes_task_identity_delta(self) -> None:
        previous_identity = derive_task_identity("Plan the onboarding redesign")
        result = self.server._runtime_next(
            {
                "objective": REDESIGN_OBJECTIVE,
                "project_path": ".",
                "current_phase": "runtime",
                "previous_packet_id": "packet-test",
                "previous_task_identity": previous_identity,
                "files_changed": ["app/onboarding/page.tsx"],
                "cache_policy": "none",
            }
        )
        self.assertIn("task_identity", result)
        self.assertIn("frontend_product_redesign", result["task_identity"]["primary"])
        if result.get("task_identity_delta") is not None:
            self.assertIn("current", result["task_identity_delta"])


if __name__ == "__main__":
    unittest.main()
