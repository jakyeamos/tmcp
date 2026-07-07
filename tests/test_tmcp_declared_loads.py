from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers


class TmcpDeclaredLoadsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_routing_metadata_extracts_declared_directory_and_file_loads(self) -> None:
        text = "\n".join(
            [
                "# Runtime",
                "1. Search `product-decisions/surfaces/` for direct surface guidance.",
                "2. Search `product-decisions/components/` for component rules.",
                "3. Load `product-decisions/standards/visual-polish.md` when polish matters.",
                "4. Check `coverage-gaps.md` for unresolved decisions.",
                "5. Read from `product-decisions/copy/` before editing copy.",
            ]
        )
        metadata = self.server._routing_metadata_for(
            ".agents/skills/product-design-runtime/SKILL.md",
            text,
        )

        declared = metadata["declared_loads"]
        self.assertIn("product-decisions/surfaces/**", declared)
        self.assertIn("product-decisions/components/**", declared)
        self.assertIn("product-decisions/standards/visual-polish.md", declared)
        self.assertIn("coverage-gaps.md", declared)
        self.assertIn("product-decisions/copy/**", declared)

    def test_resolve_declared_loads_narrows_surface_files_from_objective(self) -> None:
        patterns = [
            "product-decisions/surfaces/**",
            "product-decisions/standards/**",
            "coverage-gaps.md",
        ]
        source_nodes = [
            {
                "relative_path": "product-decisions/surfaces/onboarding.md",
                "path": "/tmp/product-decisions/surfaces/onboarding.md",
            },
            {
                "relative_path": "product-decisions/surfaces/settings.md",
                "path": "/tmp/product-decisions/surfaces/settings.md",
            },
            {
                "relative_path": "product-decisions/standards/ui-quality.md",
                "path": "/tmp/product-decisions/standards/ui-quality.md",
            },
            {
                "relative_path": "product-decisions/coverage-gaps.md",
                "path": "/tmp/product-decisions/coverage-gaps.md",
            },
        ]

        paths, nodes = self.server._resolved_declared_load_nodes(
            selected_nodes=[{"relative_path": "runtime/SKILL.md", "routing_metadata": {"declared_loads": patterns}}],
            source_nodes=source_nodes,
            objective="Use product-design-runtime before implementing onboarding UI",
        )

        self.assertIn("product-decisions/surfaces/onboarding.md", paths)
        self.assertNotIn("product-decisions/surfaces/settings.md", paths)
        self.assertIn("product-decisions/standards/ui-quality.md", paths)
        self.assertIn("product-decisions/coverage-gaps.md", paths)
        self.assertEqual(
            {node["relative_path"] for node in nodes},
            set(paths),
        )

    def test_compose_packet_includes_declared_product_decision_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / ".agents" / "skills" / "product-design-runtime"
            skill_dir.mkdir(parents=True)
            decisions = root / "product-decisions"
            (decisions / "surfaces").mkdir(parents=True)
            (decisions / "standards").mkdir(parents=True)
            skill_dir.joinpath("SKILL.md").write_text(
                "\n".join(
                    [
                        "# Product Design Runtime",
                        "Search `product-decisions/surfaces/` for direct surface guidance.",
                        "Search `product-decisions/standards/` for global product rules.",
                        "Check `coverage-gaps.md` for unresolved decisions.",
                    ]
                ),
                encoding="utf-8",
            )
            (decisions / "surfaces" / "onboarding.md").write_text(
                "# Onboarding\n\nKeep first-run copy short.",
                encoding="utf-8",
            )
            (decisions / "surfaces" / "settings.md").write_text(
                "# Settings\n\nGroup advanced settings.",
                encoding="utf-8",
            )
            (decisions / "standards" / "ui-quality.md").write_text(
                "# UI Quality\n\nVerify reachable states.",
                encoding="utf-8",
            )
            (decisions / "coverage-gaps.md").write_text(
                "# Coverage Gaps\n\nNo billing decision yet.",
                encoding="utf-8",
            )

            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": "Use product-design-runtime before implementing onboarding UI",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 20,
                }
            )

        required_reads = result["required_reads"]
        self.assertIn("product-decisions/surfaces/onboarding.md", required_reads)
        self.assertNotIn("product-decisions/surfaces/settings.md", required_reads)
        self.assertIn("product-decisions/standards/ui-quality.md", required_reads)
        self.assertIn("product-decisions/coverage-gaps.md", required_reads)
        cited_sources = {
            citation["source"] for citation in result["evidence_citations"]
        }
        self.assertIn("product-decisions/surfaces/onboarding.md", cited_sources)

    def test_compose_packet_without_declared_loads_unchanged_for_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "skills" / "impeccable"
            refs = skill / "reference"
            refs.mkdir(parents=True)
            skill.joinpath("SKILL.md").write_text(
                "\n".join(
                    [
                        "# Impeccable",
                        "Read reference/craft.md before craft work.",
                    ]
                ),
                encoding="utf-8",
            )
            refs.joinpath("craft.md").write_text("# Craft", encoding="utf-8")

            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": "impeccable craft landing page",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 10,
                }
            )

        self.assertIn("reference/craft.md", result["required_reads"])
