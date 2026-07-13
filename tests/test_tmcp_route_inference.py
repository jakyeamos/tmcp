from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers
from tests.test_tmcp_skill_family_compose import _write_product_design_family
from tests.test_tmcp_task_identity import REDESIGN_OBJECTIVE

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ADAPTIVE_RUNTIME_PATH = (
    PLUGIN_ROOT / "tests" / "fixtures" / "golden_adaptive_runtime.json"
)


def _frontend_redesign_seed() -> dict[str, object]:
    return json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "seeds"
            / "frontend-redesign-runtime.json"
        ).read_text(encoding="utf-8")
    )


def _write_frontend_redesign_family(root: Path) -> None:
    skills = root / ".agents" / "skills"
    skill_contents = {
        "ui-ux-pro-max": "# UI UX Pro Max\nSearch current visual patterns before redesigning pages.\n",
        "frontend-design": "# Frontend Design\nReuse existing components before redesigning pages.\n",
        "motion-system": "# Motion System\nPrefer reduced-motion-safe interactions.\n",
    }
    for name, content in skill_contents.items():
        skill_dir = skills / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_dir.joinpath("SKILL.md").write_text(content, encoding="utf-8")
    (root / "scoped-packet-seeds.json").write_text(
        json.dumps(_frontend_redesign_seed(), indent=2),
        encoding="utf-8",
    )


class TmcpRouteInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_compose_auto_matches_frontend_redesign_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_frontend_redesign_family(root)
            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": REDESIGN_OBJECTIVE,
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        family_context = result["family_context"]
        self.assertEqual(family_context["kind"], "scoped_packet_seed")
        self.assertEqual(
            family_context["active_seed_id"], "frontend_redesign_runtime_v1"
        )
        selected = {item["source"] for item in result["evidence_citations"]}
        self.assertIn(".agents/skills/ui-ux-pro-max/SKILL.md", selected)
        self.assertNotIn(".agents/skills/frontend-design/SKILL.md", selected)
        self.assertNotIn(".agents/skills/motion-system/SKILL.md", selected)
        rationale = result["packet_markdown"]
        self.assertIn("route scores", rationale.lower())
        self.assertIn("ui_ux_redesign", rationale)

    def test_shortcut_candidate_includes_compiled_from_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_frontend_redesign_family(root)
            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": REDESIGN_OBJECTIVE,
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        shortcut = result["shortcut_candidate"]
        self.assertEqual(shortcut["status"], "eligible")
        self.assertEqual(shortcut["shortcut_id"], "frontend_redesign_runtime_v1")
        self.assertTrue(shortcut["compiled_from"]["graph_version"])
        self.assertEqual(
            shortcut["compiled_from"]["route_catalog_version"],
            result["compiled_from"]["route_catalog_version"],
        )
        self.assertIn("graph_version changes", shortcut["regenerate_when"])
        composed_schema = json.loads(
            (
                PLUGIN_ROOT / "schemas" / "tmcp-composed-packet-v0.1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(set(composed_schema["required"]).issubset(result))
        self.assertEqual(result["receipt_template"]["packet_id"], result["packet_id"])
        self.assertTrue(result["safety"])
        self.assertIn("tmcp_home", result["global_cache"])

    def test_user_overrides_require_shortcut_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_frontend_redesign_family(root)
            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": REDESIGN_OBJECTIVE,
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "user_overrides": ["Keep the existing navigation labels."],
                    "limit": 30,
                }
            )

        shortcut = result["shortcut_candidate"]
        self.assertEqual(shortcut["status"], "needs_revalidation")
        self.assertFalse(shortcut["matched"])
        self.assertEqual(
            shortcut["reason"], "User overrides require full packet revalidation."
        )

    def test_graph_version_change_invalidates_shortcut_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_frontend_redesign_family(root)
            first = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": REDESIGN_OBJECTIVE,
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )
            skills = root / ".agents" / "skills" / "research-freshness"
            skills.mkdir(parents=True, exist_ok=True)
            skills.joinpath("SKILL.md").write_text(
                "# Research Freshness\nTrack current UI trends.\n",
                encoding="utf-8",
            )
            second = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": REDESIGN_OBJECTIVE
                    + " Include current trend research.",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        self.assertNotEqual(
            first["compiled_from"]["graph_version"],
            second["compiled_from"]["graph_version"],
        )

    def test_golden_adaptive_runtime_packets(self) -> None:
        cases = json.loads(GOLDEN_ADAPTIVE_RUNTIME_PATH.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case_id=case["id"]):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    if case["id"] == "frontend_redesign_natural_language":
                        _write_frontend_redesign_family(root)
                        objective = case["objective"]
                    else:
                        _write_product_design_family(root)
                        objective = case["objective"]
                    result = self.server._compose_packet(
                        {
                            "source_path": str(root),
                            "objective": objective,
                            "project_path": str(root),
                            "phase": case.get("phase", "start"),
                            "cache_policy": "none",
                            "limit": 30,
                        }
                    )
                cited = {
                    str(item.get("source") or "")
                    for item in result["evidence_citations"]
                }
                family_context = result["family_context"]
                self.assertEqual(
                    family_context.get("active_seed_id"),
                    case["expected_seed_id"],
                )
                if case.get("task_identity_primary"):
                    self.assertEqual(
                        result["task_identity"]["primary"],
                        case["task_identity_primary"],
                    )
                for route in case.get("required_routes", []):
                    self.assertIn(route, result["task_identity"]["active_routes"])
                for path in case.get("required_citations", []):
                    self.assertIn(path, cited)
                for path in case.get("excluded_citations", []):
                    self.assertNotIn(path, cited)
                if case.get("shortcut_status"):
                    self.assertEqual(
                        result["shortcut_candidate"]["status"],
                        case["shortcut_status"],
                    )
                self.assertIn("route scores", result["packet_markdown"].lower())


if __name__ == "__main__":
    unittest.main()
