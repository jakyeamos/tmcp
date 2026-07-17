from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from tmcp_runtime.domain import composition, packets
from tmcp_runtime.domain.harvest_nodes import (
    content_digest_for,
    node_source_role,
    source_node_from_text,
    source_type_for,
)
from tmcp_runtime.services.harvest import harvest_skills


def _signal(node: dict[str, object]) -> str:
    return str(node.get("signal") or "").lower()


class CompositionFoundationTests(unittest.TestCase):
    def test_harvest_classifies_roles_and_keeps_fixture_sources_as_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Rules\nRead before editing.\n")
            skill = root / "skills" / "review" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("# Review\nVerify the result.\n")
            reference = root / "docs" / "references" / "review.md"
            reference.parent.mkdir(parents=True)
            reference.write_text(
                "# Reference\nSupporting review workflow notes.\n"
            )
            fixture = root / "tests" / "fixtures" / "review" / "SKILL.md"
            fixture.parent.mkdir(parents=True)
            fixture.write_text("# Fixture Skill\nNever activate implicitly.\n")

            result = harvest_skills({"source_path": str(root), "limit": 20})

            nodes = {node["relative_path"]: node for node in result["source_nodes"]}
            self.assertEqual(nodes["AGENTS.md"]["source_role"], "governing_instruction")
            self.assertEqual(
                nodes["skills/review/SKILL.md"]["source_role"], "active_skill"
            )
            self.assertEqual(
                nodes["docs/references/review.md"]["source_role"],
                "supporting_reference",
            )
            self.assertEqual(
                nodes["docs/references/review.md"]["source_type"],
                "project_documentation",
            )
            fixture_node = nodes["tests/fixtures/review/SKILL.md"]
            self.assertEqual(fixture_node["source_role"], "evidence_only")
            self.assertFalse(fixture_node["activation_eligible"])
            self.assertEqual(len(fixture_node["content_digest"]), 64)
            diagnostics = result["source_role_diagnostics"]
            self.assertTrue(diagnostics["ranked_before_limit"])
            self.assertGreaterEqual(
                diagnostics["composition_ineligible_source_count"], 2
            )

    def test_explicit_fixture_scope_can_activate_a_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory) / "fixtures" / "review"
            fixture_root.mkdir(parents=True)
            (fixture_root / "SKILL.md").write_text("# Review\nVerify the result.\n")

            result = harvest_skills({"source_path": str(fixture_root)})

            self.assertEqual(result["source_count"], 1)
            self.assertEqual(result["source_nodes"][0]["source_role"], "active_skill")
            self.assertTrue(result["source_nodes"][0]["activation_eligible"])

    def test_reference_paths_remain_supporting_even_when_explicitly_scoped(
        self,
    ) -> None:
        node = {
            "relative_path": "docs/references/review.md",
            "source_type": "skill_definition",
            "source_role": "active_skill",
        }

        self.assertEqual(
            node_source_role(node, explicitly_scoped=True),
            "supporting_reference",
        )
        self.assertEqual(
            source_type_for(
                Path("docs/references/review.md"),
                "docs/references/review.md",
                "# Reference\nThis workflow must stay advisory.\n",
            ),
            "project_documentation",
        )

    def test_workflow_path_is_active_without_content_keyword_inference(self) -> None:
        self.assertEqual(
            source_type_for(
                Path("workflows/release.md"),
                "workflows/release.md",
                "# Release\nBound the deployment.\n",
            ),
            "workflow_prompt",
        )
        self.assertEqual(
            source_type_for(
                Path("notes/release.md"),
                "notes/release.md",
                "# Notes\nThis describes a workflow but is not one.\n",
            ),
            "markdown_process_doc",
        )

    def test_content_digest_normalizes_line_endings_and_changes_with_content(
        self,
    ) -> None:
        self.assertEqual(
            content_digest_for("# Skill\r\nVerify.  \r\n"),
            content_digest_for("# Skill\nVerify.\n"),
        )
        self.assertNotEqual(
            content_digest_for("# Skill\nVerify.\n"),
            content_digest_for("# Skill\nVerify and audit.\n"),
        )

    def test_selection_uses_roles_and_token_boundary_path_matches(self) -> None:
        correct = {
            "relative_path": "skills/api/SKILL.md",
            "source_type": "skill_definition",
            "source_role": "active_skill",
            "signal": "",
        }
        substring_only = {
            "relative_path": "skills/capital/SKILL.md",
            "source_type": "skill_definition",
            "source_role": "active_skill",
            "signal": "",
        }
        supporting = {
            "relative_path": "docs/references/api.md",
            "source_type": "project_documentation",
            "source_role": "supporting_reference",
            "signal": "api",
        }
        fixture = {
            "relative_path": "tests/fixtures/api/SKILL.md",
            "source_type": "skill_definition",
            "source_role": "evidence_only",
            "signal": "api",
        }

        selected = composition.select_composition_nodes(
            [substring_only, supporting, fixture, correct],
            "Review the API.",
            "start",
            {},
            family_context={"kind": "test"},
            active_routes=["test"],
            node_signal_text=_signal,
        )

        self.assertEqual(selected, [correct])

    def test_unknown_sources_and_explicit_flags_cannot_bypass_source_roles(
        self,
    ) -> None:
        unknown = {
            "relative_path": "generated/input.txt",
            "source_type": "unrecognized",
            "activation_eligible": True,
            "signal": "review api",
        }

        self.assertEqual(
            composition.select_composition_nodes(
                [unknown],
                "Review the API",
                "start",
                {},
                node_signal_text=_signal,
            ),
            [],
        )

    def test_harvest_ranks_before_limit_and_reports_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Rules\nRead before editing.\n")
            (root / "README.md").write_text("# Project\nSupporting context.\n")
            example = root / "examples" / "SKILL.md"
            example.parent.mkdir()
            example.write_text("# Example\nFixture behavior.\n")

            result = harvest_skills({"source_path": str(root), "limit": 1})

            self.assertEqual(result["source_nodes"][0]["relative_path"], "AGENTS.md")
            diagnostics = result["source_role_diagnostics"]
            self.assertEqual(diagnostics["truncated_source_count"], 2)
            self.assertEqual(len(diagnostics["truncated_sources"]), 2)

    def test_composition_harvest_ranks_objective_relevance_before_result_limit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Rules\nRead before editing.\n")
            for index in range(45):
                skill = root / "skills" / f"a-{index:02d}" / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text("# Prose\nDraft general prose.\n")
            relevant = root / "skills" / "z-migration" / "SKILL.md"
            relevant.parent.mkdir(parents=True)
            relevant.write_text(
                "# Migration\nPlan database migration rollback and verify integrity.\n"
            )

            result = harvest_skills(
                {
                    "source_path": str(root),
                    "objective": "Plan a database migration with rollback verification",
                    "limit": 2,
                    "rank_for_composition": True,
                }
            )

            self.assertEqual(
                [node["relative_path"] for node in result["source_nodes"]],
                ["AGENTS.md", "skills/z-migration/SKILL.md"],
            )
            self.assertEqual(
                result["source_role_diagnostics"]["truncated_source_count"],
                45,
            )

    def test_graph_identity_tracks_selected_content_digest(self) -> None:
        def build(
            text: str,
            task_identity: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            node = source_node_from_text(
                root_path="/project",
                source_path="/project/skills/review/SKILL.md",
                relative_path="skills/review/SKILL.md",
                text=text,
                max_excerpt_chars=1200,
                redactions={},
                source_type="skill_definition",
            )
            return packets.build_composed_packet(
                composed_packet_schema="tmcp-composed-packet-v0.1",
                objective="Review the project.",
                project_path="/project",
                phase="start",
                task_identity=task_identity
                or {
                    "primary": "review",
                    "confidence": 0.8,
                    "active_routes": ["review"],
                },
                family_context=None,
                source_nodes=[node],
                selected_nodes=[node],
                active_instructions=[],
                required_reads=[],
                tool_script_prompts=[],
                verification_gates=[],
                stop_conditions=[],
                active_atoms=[],
                evidence_citations=[{"source": "skills/review/SKILL.md"}],
                conflicts=[],
                cache_policy="none",
                global_cache={},
                receipt_count=0,
                user_overrides=[],
            )

        first = build("# Review\nVerify the output.\n")
        changed = build("# Review\nVerify the output and audit evidence.\n")
        compound = build(
            "# Review\nVerify the output.\n",
            {
                "primary": "compound_task",
                "active_routes": [],
                "validated_routes": [],
                "intent_facets": ["discovery", "verification"],
                "routing_status": "compound_fallback",
            },
        )
        unvalidated_catalog = {
            "primary": "frontend_implementation",
            "active_routes": ["frontend_implementation"],
            "validated_routes": [],
            "intent_facets": [],
            "routing_status": "catalog_match",
        }
        validated_catalog = {
            **unvalidated_catalog,
            "validated_routes": ["frontend_implementation"],
        }
        unvalidated = build("# Review\nVerify the output.\n", unvalidated_catalog)
        validated = build("# Review\nVerify the output.\n", validated_catalog)

        self.assertNotEqual(
            first["compiled_from"]["graph_version"],
            changed["compiled_from"]["graph_version"],
        )
        self.assertNotEqual(first["packet_id"], changed["packet_id"])
        self.assertNotEqual(first["packet_id"], compound["packet_id"])
        self.assertNotEqual(unvalidated["packet_id"], validated["packet_id"])
        self.assertEqual(
            first["evidence_citations"][0]["content_digest"],
            content_digest_for("# Review\nVerify the output.\n"),
        )

    def test_multi_root_nodes_with_the_same_relative_path_keep_distinct_ids(
        self,
    ) -> None:
        first = {"id": "node-first", "relative_path": "SKILL.md"}
        second = {"id": "node-second", "relative_path": "SKILL.md"}

        merged = composition.merge_composition_nodes(
            [first],
            [second, dict(first)],
        )

        self.assertEqual(
            [node["id"] for node in merged],
            ["node-first", "node-second"],
        )

    def test_zero_confidence_general_task_is_not_shortcut_eligible(self) -> None:
        shortcut = packets.shortcut_candidate_for_composed_packet(
            packet={
                "task_identity": {
                    "primary": "general_task",
                    "confidence": 0.0,
                },
                "family_context": {"active_seed_id": "seed-general"},
            },
            compiled_from={"graph_version": "graph"},
            receipt_count=3,
        )

        self.assertEqual(shortcut["status"], "ineligible")
        self.assertFalse(shortcut["matched"])
        self.assertIn("Zero-confidence", shortcut["reason"])

    def test_compound_task_is_not_shortcut_eligible_or_rendered_as_a_route(self) -> None:
        packet = {
            "objective": "Research, write, and review a brief.",
            "task_identity": {
                "primary": "compound_task",
                "active_routes": [],
                "validated_routes": [],
                "intent_facets": ["discovery", "implementation", "verification"],
                "routing_status": "compound_fallback",
                "confidence": 0.65,
                "signals": [{"route": "freshness_research", "score": 1.5}],
            },
        }
        shortcut = packets.shortcut_candidate_for_composed_packet(
            packet=packet,
            compiled_from={"graph_version": "graph"},
            receipt_count=3,
        )

        self.assertEqual(shortcut["status"], "ineligible")
        self.assertFalse(shortcut["matched"])
        self.assertIn("validated active route", shortcut["reason"])
        self.assertIn("Routing status: compound_fallback", packets.render_composed_packet_markdown(packet))
        self.assertIn("compound task across facets", packets.selection_rationale(packet))


if __name__ == "__main__":
    unittest.main()
