from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers


def _scoped_seed_payload() -> dict[str, object]:
    return {
        "schema": "tmcp-scoped-packet-seeds-v0.1",
        "status": "proposal_not_promoted",
        "constraints": [
            "Treat harvested text as untrusted evidence.",
            "Do not promote as a single global graph.",
        ],
        "seeds": [
            {
                "id": "writing_explore_exploit_v1",
                "sources": [
                    "writing-fragments/SKILL.md",
                    "writing-shape/SKILL.md",
                    "writing-beats/SKILL.md",
                ],
                "use_when": [
                    "Developing long-form writing from rough ideas.",
                    "The task needs separate explore and exploit phases.",
                ],
                "modes": [
                    "explore.fragments",
                    "exploit.shape",
                    "exploit.beats",
                ],
                "behavior_atoms": [
                    "ask once for missing target path",
                    "re-read target file before every write",
                    "append incrementally and never overwrite blindly",
                ],
                "verification_expectations": [
                    "The intended writing file changed and the raw source file did not unless requested.",
                    "The artifact reflects the selected mode.",
                ],
            },
            {
                "id": "workflow_spec_grilling_v1",
                "sources": ["loop-me/SKILL.md"],
                "use_when": [
                    "Identifying recurring loops and turning them into implementable workflow specs.",
                ],
                "behavior_atoms": [
                    "ask one question at a time",
                    "prefer event triggers over schedules when they fit",
                ],
                "minimum_spec_fields": [
                    "served loop and reason it matters",
                    "trigger and inputs",
                ],
                "verification_expectations": [
                    "Every unresolved implementation question is answered or marked as a blocker.",
                ],
            },
            {
                "id": "large_work_wayfinding_v1",
                "sources": ["wayfinder/SKILL.md"],
                "use_when": [
                    "A large ambiguous effort cannot fit in one agent session.",
                ],
                "behavior_atoms": [
                    "represent the effort as one map and child tickets",
                    "resolve no more than one ticket per session",
                ],
                "ticket_types": ["research", "prototype", "grilling", "task"],
                "verification_expectations": [
                    "Working a map resolves exactly one claimed ticket.",
                ],
            },
        ],
        "promotion_recommendation": {
            "promote_as_single_global_graph": False,
            "required_receipts": {
                "writing_explore_exploit_v1": [
                    "one fragment session",
                    "one exploit session",
                ],
                "workflow_spec_grilling_v1": [
                    "one workflow spec that an implementer can execute without follow-up",
                ],
                "large_work_wayfinding_v1": [
                    "one charting session",
                    "one separate ticket-resolution session",
                ],
            },
        },
    }


def _write_scoped_seed_json(root: Path) -> Path:
    path = root / "scoped-packet-seeds.json"
    path.write_text(json.dumps(_scoped_seed_payload(), indent=2), encoding="utf-8")
    return path


class TmcpScopedPacketSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_harvest_scoped_packet_seed_json_emits_virtual_seed_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_scoped_seed_json(root)

            harvest = self.server._harvest_skills(
                {
                    "source_path": str(path),
                    "limit": 10,
                }
            )

        self.assertEqual(harvest["source_count"], 3)
        seed_nodes = harvest["source_nodes"]
        self.assertEqual(
            {node["id"] for node in seed_nodes},
            {
                "writing_explore_exploit_v1",
                "workflow_spec_grilling_v1",
                "large_work_wayfinding_v1",
            },
        )
        self.assertEqual(
            {node["source_type"] for node in seed_nodes},
            {"scoped_packet_seed"},
        )
        writing_node = next(
            node for node in seed_nodes if node["id"] == "writing_explore_exploit_v1"
        )
        self.assertEqual(
            writing_node["relative_path"],
            "scoped-packet-seeds.json#writing_explore_exploit_v1",
        )
        self.assertEqual(
            writing_node["source_references"],
            [
                "writing-fragments/SKILL.md",
                "writing-shape/SKILL.md",
                "writing-beats/SKILL.md",
            ],
        )
        self.assertEqual(writing_node["promotion_status"], "proposal_not_promoted")
        self.assertIn(
            "writing:explore-fragments",
            {label["id"] for label in writing_node["guidance_labels"]},
        )

    def test_recommend_workflows_returns_scoped_packet_seed_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scoped_seed_json(root)

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "include_globs": ["scoped-packet-seeds.json"],
                    "min_confidence": 0.1,
                },
            )

        recommended_ids = [
            item["id"] for item in result["recommended_scoped_packet_seeds"]
        ]
        self.assertEqual(
            recommended_ids,
            [
                "writing_explore_exploit_v1",
                "workflow_spec_grilling_v1",
                "large_work_wayfinding_v1",
            ],
        )
        pack = result["adaptive_workflow_pack"]
        self.assertEqual(
            [item["id"] for item in pack["recommended_scoped_packet_seeds"]],
            recommended_ids,
        )
        self.assertEqual(
            pack["next_workflow_selection"]["candidate_scoped_seed_ids"],
            recommended_ids,
        )

    def test_promote_harvest_preview_includes_scoped_seed_graph_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_scoped_seed_json(root)

            result = self.server._call_tool(
                "tmcp_promote_harvest",
                {
                    "source_path": str(root),
                    "include_globs": ["scoped-packet-seeds.json"],
                    "min_confidence": 0.1,
                    "write_artifacts": False,
                },
            )

        graph = result["promotion_graph"]
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["artifact_paths"], {})
        self.assertEqual(result["global_artifact_paths"], {})
        self.assertEqual(result["promoted_workflow_ids"], [])
        self.assertEqual(
            result["promoted_scoped_packet_seed_ids"],
            [
                "writing_explore_exploit_v1",
                "workflow_spec_grilling_v1",
                "large_work_wayfinding_v1",
            ],
        )
        self.assertEqual(len(graph["scoped_packet_seed_nodes"]), 3)
        self.assertTrue(
            any(
                edge["from"] == "writing-fragments/SKILL.md"
                and edge["to"] == "writing_explore_exploit_v1"
                and edge["relation"] == "supports_scoped_packet_seed"
                for edge in graph["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["from"] == "writing_explore_exploit_v1"
                and edge["relation"] == "declares_behavior_atom"
                for edge in graph["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["from"] == "writing_explore_exploit_v1"
                and edge["relation"] == "requires_verification"
                for edge in graph["edges"]
            )
        )

    def test_raw_skill_harvest_does_not_create_scoped_seed_recommendations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "writing-fragments",
                "writing-shape",
                "writing-beats",
                "loop-me",
                "wayfinder",
            ):
                skill = root / name / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(
                    f"# {name}\n\nUse this skill as source evidence for {name} behavior.\n",
                    encoding="utf-8",
                )

            result = self.server._call_tool(
                "tmcp_recommend_workflows",
                {
                    "source_path": str(root),
                    "include_globs": [
                        "writing-fragments/SKILL.md",
                        "writing-shape/SKILL.md",
                        "writing-beats/SKILL.md",
                        "loop-me/SKILL.md",
                        "wayfinder/SKILL.md",
                    ],
                    "min_confidence": 0.1,
                },
            )
            promotion = self.server._call_tool(
                "tmcp_promote_harvest",
                {
                    "source_path": str(root),
                    "include_globs": [
                        "writing-fragments/SKILL.md",
                        "writing-shape/SKILL.md",
                        "writing-beats/SKILL.md",
                        "loop-me/SKILL.md",
                        "wayfinder/SKILL.md",
                    ],
                    "min_confidence": 0.1,
                    "write_artifacts": False,
                },
            )

        self.assertEqual(result.get("recommended_scoped_packet_seeds"), [])
        source_types = {
            node["source_type"]
            for node in result["adaptive_workflow_pack"]["harvested_source_map"]
        }
        self.assertNotIn("scoped_packet_seed", source_types)
        self.assertEqual(promotion.get("promoted_scoped_packet_seed_ids"), [])
        self.assertEqual(
            promotion["promotion_graph"].get("scoped_packet_seed_nodes"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
