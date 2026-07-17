from __future__ import annotations

import json
import unittest
from typing import Any

from tmcp_runtime.domain import recompile


class RecompileDomainTests(unittest.TestCase):
    def test_parse_previous_packet_accepts_objects_and_json(self) -> None:
        packet = {"packet_id": "packet-1"}

        self.assertIs(
            recompile.parse_previous_packet({"previous_packet": packet}), packet
        )
        self.assertEqual(
            recompile.parse_previous_packet(
                {"previous_packet": '{"packet_id": "packet-2"}'}
            ),
            {"packet_id": "packet-2"},
        )
        self.assertIsNone(recompile.parse_previous_packet({"previous_packet": "[]"}))
        with self.assertRaises(json.JSONDecodeError):
            recompile.parse_previous_packet({"previous_packet": "{not-json"})

    def test_resolve_recompile_reason_uses_stable_priority(self) -> None:
        state: dict[str, Any] = {
            "task_identity_delta": {"reason": "task_identity_primary_changed"},
            "suggested_phase": "implementation",
        }
        self.assertEqual(
            recompile.resolve_recompile_reason(
                {
                    "latest_user_message": "Actually, use a different direction.",
                    "failures": ["test failed"],
                    "browser_evidence": ["screenshot"],
                    "files_changed": ["app/page.tsx"],
                },
                state,
            ),
            "user_redirect",
        )
        self.assertEqual(
            recompile.resolve_recompile_reason(
                {"user_redirect": {"reason": "Use the migration instead."}}, state
            ),
            "user_redirect",
        )
        self.assertEqual(
            recompile.resolve_recompile_reason({"failures": ["test failed"]}, state),
            "task_identity_shift",
        )
        self.assertEqual(
            recompile.resolve_recompile_reason(
                {"failures": ["test failed"], "browser_evidence": ["screenshot"]},
                {"suggested_phase": "implementation"},
            ),
            "verification_failure",
        )
        self.assertEqual(
            recompile.resolve_recompile_reason(
                {"browser_evidence": ["screenshot"]},
                {"suggested_phase": "implementation"},
            ),
            "browser_evidence_available",
        )
        self.assertEqual(
            recompile.resolve_recompile_reason(
                {"files_changed": ["app/page.tsx"]},
                {"suggested_phase": "implementation"},
            ),
            "implementation_phase_detected",
        )
        self.assertEqual(
            recompile.resolve_recompile_reason({}, {"suggested_phase": "verification"}),
            "phase_transition",
        )
        self.assertEqual(
            recompile.resolve_recompile_reason({"files_changed": ["app/page.tsx"]}, {}),
            "implementation_phase_detected",
        )
        self.assertEqual(
            recompile.resolve_recompile_reason({}, {}), "runtime_context_changed"
        )
        self.assertEqual(
            recompile.resolve_recompile_reason(
                {"failures": ["test failed"]},
                {
                    "task_identity_delta": {
                        "changed_facets": ["verification"],
                        "reason": "runtime_context_changed",
                    }
                },
            ),
            "task_identity_shift",
        )

    def test_packet_diff_records_sorted_changes_and_reasons(self) -> None:
        previous = {
            "active_atoms": ["keep", "research", "remove"],
            "task_identity": {"active_routes": ["keep-route", "old-route"]},
            "phase": "research",
        }
        current = {
            "active_atoms": ["keep", "new"],
            "task_identity": {"active_routes": ["keep-route", "new-route"]},
            "phase": "implementation",
            "required_reads": ["AGENTS.md", "skills/implement/SKILL.md"],
        }
        result = recompile.packet_diff(
            previous,
            current,
            packet_delta={
                "deactivated_atoms": ["remove"],
                "suggested_skills": ["ui-implementation"],
            },
            recompile_reason="implementation_phase_detected",
        )

        self.assertEqual(
            result["dropped"],
            [
                {
                    "kind": "atom",
                    "id": "remove",
                    "reason": "Deactivated by family phase transition.",
                },
                {
                    "kind": "atom",
                    "id": "research",
                    "reason": "Implementation files changed; exploration atoms deferred.",
                },
                {
                    "kind": "route",
                    "id": "old-route",
                    "reason": "Not required after implementation_phase_detected.",
                },
            ],
        )
        self.assertEqual(
            result["added"],
            [
                {
                    "kind": "atom",
                    "id": "new",
                    "reason": "Activated after runtime recompile.",
                },
                {
                    "kind": "skill",
                    "id": "ui-implementation",
                    "reason": "phase_transitions.activate_skills",
                },
                {
                    "kind": "route",
                    "id": "new-route",
                    "reason": "Route activated from runtime evidence.",
                },
            ],
        )
        self.assertEqual(result["unchanged"], ["keep"])
        self.assertEqual(
            result["phase_change"], {"from": "research", "to": "implementation"}
        )
        self.assertEqual(
            result["required_reads"],
            {
                "added": ["AGENTS.md", "skills/implement/SKILL.md"],
                "dropped": [],
                "unchanged": [],
                "all": ["AGENTS.md", "skills/implement/SKILL.md"],
            },
        )

    def test_packet_diff_tracks_task_facet_changes(self) -> None:
        result = recompile.packet_diff(
            {"task_identity": {"intent_facets": ["discovery", "planning"]}},
            {"task_identity": {"intent_facets": ["planning", "verification"]}},
            packet_delta={},
            recompile_reason="task_identity_shift",
        )

        self.assertIn(
            {
                "kind": "task_facet",
                "id": "discovery",
                "reason": "Not required after task_identity_shift.",
            },
            result["dropped"],
        )
        self.assertIn(
            {
                "kind": "task_facet",
                "id": "verification",
                "reason": "Task facet activated from runtime evidence.",
            },
            result["added"],
        )

    def test_packet_diff_includes_all_graph_runtime_surfaces(self) -> None:
        graph_diff = {
            "phase_change": {"from": "discovery", "to": "implementation"},
            "skills": {
                "added": ["implement"],
                "dropped": ["research"],
                "unchanged": [],
                "deferred": ["verify"],
            },
            "relationships": {
                "added": ["relationship-new"],
                "dropped": [],
                "unchanged": [],
                "active": [],
            },
            "instructions": {
                "added": ["instruction-new"],
                "dropped": ["instruction-old"],
                "unchanged": [],
                "active": [],
            },
            "reads": {"added": ["docs/brief.md"], "all": ["docs/brief.md"]},
            "gates": {
                "newly_fulfilled": ["gate-research"],
                "failed": [],
                "pending": ["gate-implementation"],
                "bypassed": [],
            },
            "handoffs": {
                "added": ["handoff-implementation"],
                "dropped": [],
                "unchanged": [],
                "active": [],
                "newly_available": ["handoff-implementation"],
                "available": ["handoff-implementation"],
                "failed": [],
                "pending": [],
                "bypassed": [],
                "invalid_contracts": [],
            },
            "conflicts": {"active": []},
            "fulfilled_obligations": {
                "added": ["gate-research"],
                "all": ["gate-research"],
            },
        }

        result = recompile.packet_diff(
            {"phase": "discovery"},
            {"phase": "implementation"},
            packet_delta={},
            recompile_reason="phase_transition",
            graph_diff=graph_diff,
        )

        self.assertEqual(result["phase_change"], graph_diff["phase_change"])
        self.assertTrue(
            any(
                item["kind"] == "skill" and item["id"] == "implement"
                for item in result["added"]
            )
        )
        self.assertTrue(
            any(
                item["kind"] == "skill" and item["id"] == "research"
                for item in result["dropped"]
            )
        )
        for field in (
            "skills",
            "relationships",
            "instructions",
            "reads",
            "gates",
            "handoffs",
            "conflicts",
            "fulfilled_obligations",
        ):
            self.assertEqual(result[field], graph_diff[field])

    def test_fresh_graph_diff_keeps_structural_changes_and_runtime_gate_truth(
        self,
    ) -> None:
        previous = {
            "phase": "discovery",
            "composition_plan": {
                "skill_roles": [
                    {
                        "node_id": "research",
                        "source_role": "active_skill",
                        "activation": "active",
                    }
                ],
                "typed_edges": [],
                "ordered_stages": [],
            },
        }
        current = {
            "phase": "implementation",
            "composition_plan": {
                "skill_roles": [
                    {
                        "node_id": "implement",
                        "source_role": "active_skill",
                        "activation": "active",
                    }
                ],
                "typed_edges": [],
                "ordered_stages": [],
            },
        }
        runtime_graph_diff = {
            "skills": {
                "added": [],
                "dropped": [],
                "unchanged": ["implement"],
                "deferred": ["verify"],
            },
            "relationships": {"active": []},
            "instructions": {"active": []},
            "reads": {"added": ["docs/brief.md"], "all": ["docs/brief.md"]},
            "gates": {
                "newly_fulfilled": [],
                "failed": ["gate-failed"],
                "pending": ["gate-pending"],
                "bypassed": ["gate-bypassed"],
            },
            "handoffs": {
                "added": [],
                "dropped": [],
                "unchanged": [],
                "active": [],
                "newly_available": ["handoff-implementation"],
                "available": ["handoff-implementation"],
                "failed": [],
                "pending": [],
                "bypassed": [],
                "invalid_contracts": [],
            },
            "conflicts": {"active": []},
            "fulfilled_obligations": {"added": [], "all": []},
        }

        result = recompile.packet_diff(
            previous,
            current,
            packet_delta={},
            recompile_reason="phase_transition",
            graph_diff=runtime_graph_diff,
            merge_graph_runtime=True,
        )

        self.assertEqual(result["skills"]["added"], ["implement"])
        self.assertEqual(result["skills"]["dropped"], ["research"])
        self.assertEqual(result["skills"]["deferred"], ["verify"])
        self.assertEqual(result["gates"], runtime_graph_diff["gates"])
        self.assertEqual(result["handoffs"], runtime_graph_diff["handoffs"])
        self.assertEqual(result["reads"], runtime_graph_diff["reads"])

    def test_merge_packet_delta_preserves_order_limits_and_context(self) -> None:
        packet = {
            "active_atoms": ["first", "remove", "second"],
            "deferred_atoms": ["first", "existing-deferred"],
            "required_reads": [f"existing-{index}" for index in range(10)],
            "verification_gates": [f"existing gate {index}" for index in range(8)],
            "family_context": {"seed": "existing", "retain": True},
            "phase": "runtime",
        }
        merged = recompile.merge_packet_delta(
            packet,
            {
                "activated_atoms": [f"new-{index}" for index in range(20)],
                "deactivated_atoms": ["remove"],
                "stale_atoms": ["stale"],
                "newly_required_reads": [f"new-read-{index}" for index in range(8)],
                "suggested_phase": "implementation",
                "family_context": {"seed": "updated", "phase": "implementation"},
            },
            next_gates=[f"new gate {index}" for index in range(8)],
        )

        self.assertEqual(merged["phase"], "implementation")
        self.assertEqual(merged["active_atoms"][:2], ["first", "second"])
        self.assertNotIn("remove", merged["active_atoms"])
        self.assertEqual(len(merged["active_atoms"]), 16)
        self.assertIn("existing-deferred", merged["deferred_atoms"])
        self.assertIn("remove", merged["deferred_atoms"])
        self.assertIn("stale", merged["deferred_atoms"])
        self.assertEqual(len(merged["required_reads"]), 12)
        self.assertEqual(merged["required_reads"][:10], packet["required_reads"])
        self.assertEqual(len(merged["verification_gates"]), 10)
        self.assertEqual(merged["verification_gates"][:8], packet["verification_gates"])
        self.assertEqual(
            merged["family_context"],
            {"seed": "updated", "retain": True, "phase": "implementation"},
        )

    def test_apply_validated_proposals_updates_route_identity(self) -> None:
        packet = {
            "task_identity": {
                "primary": "primary-route",
                "secondary": ["existing-route"],
                "active_routes": ["primary-route", "existing-route"],
            }
        }
        result = recompile.apply_validated_proposals(
            packet,
            [
                {"action": "add_route", "route": "accessibility_validation"},
                {"action": "add_route", "route": "existing-route"},
                {"action": "ignore", "route": "performance_validation"},
            ],
        )

        identity = result["task_identity"]
        self.assertEqual(
            identity["active_routes"],
            ["primary-route", "existing-route", "accessibility_validation"],
        )
        self.assertEqual(identity["validated_routes"], ["accessibility_validation"])
        self.assertEqual(
            identity["secondary"],
            ["existing-route", "accessibility_validation"],
        )

    def test_render_recompiled_packet_markdown_uses_composed_renderer(self) -> None:
        rendered_packets: list[dict[str, Any]] = []

        def compose_markdown(packet: dict[str, Any]) -> str:
            rendered_packets.append(packet)
            return "# TMCP Packet\n\n## Base\n"

        self.assertEqual(
            recompile.render_recompiled_packet_markdown(
                {}, compose_markdown=compose_markdown
            ),
            "",
        )
        packet = {"packet_id": "packet-1"}
        rendered = recompile.render_recompiled_packet_markdown(
            {
                "packet": packet,
                "recompile_reason": "phase_transition",
                "recompile_detail": "Family phase transition activated the next skill layer.",
                "packet_diff": {
                    "dropped": [{"kind": "atom", "id": "old", "reason": "stale"}],
                    "added": [{"kind": "atom", "id": "new", "reason": "active"}],
                },
            },
            compose_markdown=compose_markdown,
        )

        self.assertEqual(rendered_packets, [packet])
        self.assertIn("## Recompile", rendered)
        self.assertIn("### Dropped", rendered)
        self.assertIn("### Added", rendered)
        self.assertIn("## Base", rendered)


if __name__ == "__main__":
    unittest.main()
