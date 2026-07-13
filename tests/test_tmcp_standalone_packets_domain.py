from __future__ import annotations

import copy
import unittest

from tmcp_runtime.domain import standalone_packets


class StandalonePacketDomainTests(unittest.TestCase):
    def test_compiler_routes_tmcp_ui_work_to_audit_with_provenance(self) -> None:
        packet = standalone_packets.compile_standalone_packet(
            objective="Use the TMCP expert UI rubric on the dashboard.",
            project_path="/tmp/project",
            created_at="2026-07-12T12:00:00Z",
        )

        self.assertEqual(packet["task_id"], "audit")
        self.assertIn("@task:audit", packet["selected_nodes"])
        self.assertIn("@module:provenance_policy", packet["selected_nodes"])
        self.assertEqual(
            packet["selected_branches"][0]["branch"],
            "@branch:evidence_first_review",
        )
        self.assertEqual(packet["created_at"], "2026-07-12T12:00:00Z")

    def test_compiler_caps_source_projection_and_keeps_fingerprint_stable(self) -> None:
        harvested_nodes = [
            {
                "id": f"source-{index}",
                "relative_path": f"docs/{index}.md",
                "behavior_atoms": [f"atom-{index}"],
                "keywords": ["audit", f"keyword-{index}"],
            }
            for index in range(9)
        ]
        before = copy.deepcopy(harvested_nodes)
        first = standalone_packets.compile_standalone_packet(
            objective="Audit the project.",
            project_path="/tmp/project",
            harvested_nodes=harvested_nodes,
            created_at="2026-07-12T12:00:00Z",
        )
        second = standalone_packets.compile_standalone_packet(
            objective="Audit the project.",
            project_path="/tmp/project",
            harvested_nodes=harvested_nodes,
            created_at="2026-07-12T12:00:00Z",
        )

        self.assertEqual(len(first["source_skill_nodes"]), 8)
        self.assertEqual(
            [node["id"] for node in first["source_skill_nodes"]],
            [f"@source:source-{index}" for index in range(8)],
        )
        self.assertEqual(
            first["traversal_fingerprint"], second["traversal_fingerprint"]
        )
        self.assertEqual(harvested_nodes, before)

    def test_substance_check_distinguishes_source_backed_playbooks(self) -> None:
        packet = standalone_packets.compile_standalone_packet(
            objective="Audit government compliance readiness.",
            project_path="/tmp/project",
            harvested_nodes=[
                {
                    "id": "readiness",
                    "source_type": "skill_definition",
                    "title": "Government readiness playbook",
                    "keywords": ["government", "compliance", "security"],
                    "excerpt": "Audit evidence, verify security controls, and review readiness.",
                }
            ],
            created_at="2026-07-12T12:00:00Z",
        )

        substance = packet["substance_check"]
        self.assertEqual(substance["level"], "source_backed_playbook")
        self.assertTrue(substance["has_domain_playbook"])
        self.assertEqual(substance["substantive_source_count"], 1)

    def test_defaults_and_markdown_share_one_packet_contract(self) -> None:
        packet = standalone_packets.compile_standalone_packet(
            objective="Implement the dashboard.",
            project_path=None,
            created_at="2026-07-12T12:00:00Z",
        )

        self.assertEqual(packet["phase"], "unspecified")
        self.assertEqual(packet["domain"], "general")
        self.assertEqual(
            packet["packet_markdown"],
            standalone_packets.render_standalone_packet_markdown(packet),
        )
        self.assertEqual(
            packet["token_estimates"]["estimated_token_delta"],
            packet["token_estimates"]["baseline_skill_tokens"]
            - packet["token_estimates"]["custom_skill_tokens"],
        )


if __name__ == "__main__":
    unittest.main()
