from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.domain import families


def _product_design_family_seed() -> dict[str, object]:
    return {
        "schema": "tmcp-scoped-packet-seeds-v0.1",
        "status": "proposal_not_promoted",
        "seeds": [
            {
                "id": "product_design_runtime_v1",
                "name": "Product design runtime",
                "sources": [".agents/skills/product-design-runtime/SKILL.md"],
                "loads": [
                    "product-decisions/surfaces/**",
                    "product-decisions/standards/**",
                    "coverage-gaps.md",
                ],
                "use_when": [
                    "Load product decisions before UI implementation or review.",
                ],
                "chains_before": [
                    "ui-implementation",
                    "ui-polish-verification",
                    "ui-product-review",
                ],
                "chains_after": ["ui-implementation"],
                "do_not_activate_with": [
                    "ui-polish-verification",
                    "product-decision-interview",
                ],
                "phase_transitions": {
                    "runtime": {
                        "next_phases": ["implementation"],
                        "activate_skills": ["ui-implementation"],
                        "verification_gates": [
                            "Product runtime brief produced before implementation."
                        ],
                    },
                    "start": {
                        "next_phases": ["implementation"],
                        "activate_skills": ["ui-implementation"],
                        "verification_gates": [
                            "Product runtime brief produced before implementation."
                        ],
                    },
                    "implementation": {
                        "next_phases": ["polish-verify"],
                        "activate_skills": ["ui-polish-verification"],
                        "verification_gates": [
                            "Reachable states implemented before polish verification."
                        ],
                    },
                    "polish-verify": {
                        "next_phases": ["review"],
                        "activate_skills": ["ui-product-review"],
                        "verification_gates": [
                            "Screenshot or browser evidence captured before review."
                        ],
                    },
                },
                "behavior_atoms": [
                    "source-traceability",
                    "behavior-verification",
                ],
            }
        ],
    }


def _write_product_design_family(root: Path) -> None:
    skills = root / ".agents" / "skills"
    for name in (
        "product-judgment",
        "product-design-runtime",
        "ui-implementation",
        "ui-polish-verification",
        "ui-product-review",
        "product-decision-interview",
    ):
        skill_dir = skills / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        if name == "product-judgment":
            content = "\n".join(
                [
                    "# Product Judgment Skill Family",
                    "Choose exactly one primary mode.",
                    "Need to understand which decisions apply before work starts?",
                    "→ product-design-runtime",
                    "Need to build UI or modify behavior?",
                    "→ ui-implementation",
                    "Need to verify rendered polish?",
                    "→ ui-polish-verification",
                ]
            )
        elif name == "ui-polish-verification":
            content = "\n".join(
                [
                    "# UI Polish Verification",
                    "Read references/frame-audit-checklist.md before polish verification.",
                    "Capture screenshot evidence for primary states.",
                ]
            )
            (skill_dir / "references").mkdir(parents=True, exist_ok=True)
            (skill_dir / "references" / "frame-audit-checklist.md").write_text(
                "# Frame audit checklist",
                encoding="utf-8",
            )
        elif name == "product-design-runtime":
            content = "\n".join(
                [
                    "# Product Design Runtime",
                    "Search `product-decisions/surfaces/` for direct surface guidance.",
                    "Search `product-decisions/standards/` for global product rules.",
                    "Check `coverage-gaps.md` for unresolved decisions.",
                ]
            )
        else:
            content = f"# {name}\n\nSpecialized product design skill for {name}."
        skill_dir.joinpath("SKILL.md").write_text(content, encoding="utf-8")

    decisions = root / "product-decisions"
    (decisions / "surfaces").mkdir(parents=True)
    (decisions / "standards").mkdir(parents=True)
    (decisions / "surfaces" / "onboarding.md").write_text("# Onboarding", encoding="utf-8")
    (decisions / "surfaces" / "settings.md").write_text("# Settings", encoding="utf-8")
    (decisions / "standards" / "ui-quality.md").write_text("# UI Quality", encoding="utf-8")
    (decisions / "coverage-gaps.md").write_text("# Coverage gaps", encoding="utf-8")
    (root / "EXAMPLE_WORKFLOW.md").write_text("# Example workflow", encoding="utf-8")
    (root / "INSTALL.md").write_text("# Install", encoding="utf-8")
    (root / "scoped-packet-seeds.json").write_text(
        json.dumps(_product_design_family_seed(), indent=2),
        encoding="utf-8",
    )


class TmcpSkillFamilyComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_harvest_scoped_seed_includes_family_chain_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            harvest = self.server._harvest_skills(
                {"source_path": str(root), "limit": 30, "include_globs": ["scoped-packet-seeds.json"]}
            )

        seed = next(
            node
            for node in harvest["source_nodes"]
            if node.get("seed_id") == "product_design_runtime_v1"
        )
        self.assertEqual(
            seed["loads"],
            [
                "product-decisions/surfaces/**",
                "product-decisions/standards/**",
                "coverage-gaps.md",
            ],
        )
        self.assertEqual(seed["chains_before"], ["ui-implementation", "ui-polish-verification", "ui-product-review"])
        self.assertEqual(seed["chains_after"], ["ui-implementation"])
        self.assertIn(
            "product-decisions/surfaces/**",
            seed["routing_metadata"]["declared_loads"],
        )

    def test_compose_suppresses_sibling_skills_when_scoped_seed_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": "Use product-design-runtime before implementing onboarding UI",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        selected = {citation["source"] for citation in result["evidence_citations"]}
        self.assertIn(".agents/skills/product-design-runtime/SKILL.md", selected)
        self.assertNotIn(".agents/skills/ui-implementation/SKILL.md", selected)
        self.assertNotIn(".agents/skills/ui-polish-verification/SKILL.md", selected)
        self.assertNotIn("INSTALL.md", selected)
        self.assertNotIn("EXAMPLE_WORKFLOW.md", selected)
        family_context = result["family_context"]
        self.assertEqual(family_context["kind"], "scoped_packet_seed")
        self.assertEqual(family_context["active_seed_id"], "product_design_runtime_v1")
        self.assertIn("ui-implementation", family_context["chains_after"])
        self.assertIn("ui-polish-verification", family_context["deferred_skill_slugs"])

    def test_compose_allows_explicitly_named_sibling_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": (
                        "Use product-design-runtime, then ui-polish-verification "
                        "for onboarding polish"
                    ),
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        selected = {citation["source"] for citation in result["evidence_citations"]}
        self.assertIn(".agents/skills/product-design-runtime/SKILL.md", selected)
        self.assertIn(".agents/skills/ui-polish-verification/SKILL.md", selected)

    def test_compose_uses_router_skill_without_scoped_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            (root / "scoped-packet-seeds.json").unlink()
            result = self.server._compose_packet(
                {
                    "source_path": str(root),
                    "objective": "Use product-design-runtime before implementing onboarding UI",
                    "project_path": str(root),
                    "phase": "start",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        selected = {citation["source"] for citation in result["evidence_citations"]}
        self.assertIn(".agents/skills/product-design-runtime/SKILL.md", selected)
        self.assertNotIn(".agents/skills/ui-implementation/SKILL.md", selected)
        self.assertEqual(result["family_context"]["kind"], "router_skill")
        self.assertIn(
            ".agents/skills/product-judgment/SKILL.md",
            result["family_context"]["router_relative_paths"],
        )


class TmcpSkillFamilyRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_harvest_scoped_seed_includes_phase_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            harvest = self.server._harvest_skills(
                {"source_path": str(root), "limit": 30, "include_globs": ["scoped-packet-seeds.json"]}
            )

        seed = next(
            node
            for node in harvest["source_nodes"]
            if node.get("seed_id") == "product_design_runtime_v1"
        )
        self.assertIn("runtime", seed["phase_transitions"])
        self.assertEqual(
            seed["phase_transitions"]["runtime"]["activate_skills"],
            ["ui-implementation"],
        )

    def test_runtime_family_fallback_uses_transition_seed_below_compose_threshold(self) -> None:
        source_nodes = [
            {
                "source_type": "scoped_packet_seed",
                "seed_id": "runtime_only_seed",
                "title": "Runtime-only seed",
                "source_references": ["skills/product-design-runtime/SKILL.md"],
                "phase_transitions": {
                    "runtime": {
                        "next_phases": ["implementation"],
                        "activate_skills": ["ui-implementation"],
                    }
                },
            }
        ]

        family_context, seed_node = families.runtime_family_seed_context(
            source_nodes,
            "Inspect unrelated service logs.",
            "runtime",
            node_signal_text=lambda node: str(node.get("signal") or ""),
        )

        self.assertEqual(seed_node["seed_id"], "runtime_only_seed")
        self.assertEqual(family_context["active_seed_id"], "runtime_only_seed")
        self.assertEqual(
            family_context["primary_source_patterns"],
            ["skills/product-design-runtime/SKILL.md"],
        )

    def test_runtime_next_suggests_implementation_after_runtime_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            result = self.server._runtime_next(
                {
                    "source_path": str(root),
                    "objective": "Use product-design-runtime before implementing onboarding UI",
                    "project_path": str(root),
                    "current_phase": "runtime",
                    "previous_packet_id": "packet-runtime",
                    "latest_user_message": "Product runtime brief is ready.",
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        self.assertEqual(result["suggested_phase"], "implementation")
        delta = result["packet_delta"]
        self.assertEqual(delta["suggested_skills"], ["ui-implementation"])
        self.assertIn("ui-polish-verification", delta["deferred_skills"])
        self.assertIn(
            ".agents/skills/ui-implementation/SKILL.md",
            delta["newly_required_reads"],
        )
        self.assertIn(
            "product runtime brief",
            " ".join(result["next_verification_gate"]).lower(),
        )

    def test_runtime_next_prefers_polish_phase_after_implementation_with_ui_changes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_product_design_family(root)
            result = self.server._runtime_next(
                {
                    "source_path": str(root),
                    "objective": "Implement onboarding UI from product runtime brief",
                    "project_path": str(root),
                    "current_phase": "implementation",
                    "files_changed": ["app/onboarding/page.tsx"],
                    "cache_policy": "none",
                    "limit": 30,
                }
            )

        self.assertEqual(result["suggested_phase"], "polish-verify")
        self.assertEqual(
            result["packet_delta"]["suggested_skills"],
            ["ui-polish-verification"],
        )
        self.assertIn(
            "references/frame-audit-checklist.md",
            " ".join(result["packet_delta"]["newly_required_reads"]),
        )

    def test_runtime_next_without_family_harvest_stays_context_only(self) -> None:
        result = self.server._runtime_next(
            {
                "objective": "fix the dashboard UI bug",
                "project_path": "/tmp/project",
                "current_phase": "final",
                "files_changed": ["app/page.tsx"],
                "failures": ["vitest failed"],
                "browser_evidence": ["screenshot shows overlap"],
                "cache_policy": "none",
            }
        )

        self.assertEqual(result.get("suggested_phase"), "")
        self.assertEqual(result["packet_delta"].get("suggested_skills"), [])
        self.assertIn("ui-browser-verification", result["packet_delta"]["activated_atoms"])
