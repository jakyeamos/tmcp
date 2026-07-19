from __future__ import annotations

import unittest
from typing import Any

from tmcp_runtime.domain import composition, packets
from tmcp_runtime.domain.harvest_nodes import content_digest_for, source_node_from_text


class CompositionFoundationIdentityTests(unittest.TestCase):
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
