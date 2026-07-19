from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from typing import cast

from tests.tmcp_test_client import TestWorkspace


class CompositionPrepareServerTests(unittest.TestCase):
    def test_prepare_composition_is_available_over_mcp_without_writes(self) -> None:
        with TestWorkspace() as workspace:
            assert workspace.project is not None
            assert workspace.tmcp_home is not None
            (workspace.project / "AGENTS.md").write_text(
                "# Instructions\n\nRead before modifying. Verify focused tests.\n",
                encoding="utf-8",
            )
            for name, content in (
                ("review", "# Review\n\nInspect the implementation and verify behavior.\n"),
                ("generic", "# Generic\n\nUse the generic procedure.\n"),
            ):
                skill = workspace.project / "skills" / name / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text(content, encoding="utf-8")
            responses = workspace.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "tmcp_prepare_composition",
                            "arguments": {
                                "objective": "Implement and verify the change",
                                "project_path": str(workspace.project),
                                "source_path": str(workspace.project),
                                "include_all_active_source_slices": True,
                            },
                        },
                    }
                ]
            )

            result = cast(Mapping[str, object], responses[0]["result"])
            structured = cast(Mapping[str, object], result["structuredContent"])

            self.assertEqual(structured["schema"], "tmcp-composition-preflight-v0.1")
            self.assertEqual(
                cast(Mapping[str, object], structured["semantic_proposal_contract"])[
                    "schema"
                ],
                "tmcp-semantic-proposal-v0.1",
            )
            harvest_diagnostics = cast(
                Mapping[str, object], structured["harvest_diagnostics"]
            )
            self.assertTrue(harvest_diagnostics["ranked_before_limit"])
            source_roles = cast(Mapping[str, int], structured["source_roles"])
            self.assertEqual(source_roles["active_skill"], 2)
            self.assertEqual(list(workspace.tmcp_home.iterdir()), [])

    def test_prepare_composition_preserves_explicit_fixture_dependency_through_harvest(
        self,
    ) -> None:
        with TestWorkspace() as workspace:
            assert workspace.project is not None
            (workspace.project / "AGENTS.md").write_text(
                "# Instructions\n\nRead before modifying.\n",
                encoding="utf-8",
            )
            (workspace.project / "scoped-packet-seeds.json").write_text(
                json.dumps(
                    {
                        "schema": "tmcp-scoped-packet-seeds-v0.1",
                        "seeds": [
                            {
                                "id": "migration-seed",
                                "use_when": ["Prepare migration evidence."],
                                "chains_after": ["fixture-checksum"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fixture_path = "tests/fixtures/fixture-checksum/SKILL.md"
            fixture = workspace.project / fixture_path
            fixture.parent.mkdir(parents=True)
            fixture.write_text(
                "# Checksum\n\nVerify migration checksum evidence.\n",
                encoding="utf-8",
            )
            generic = workspace.project / "skills" / "generic" / "SKILL.md"
            generic.parent.mkdir(parents=True)
            generic.write_text("# Generic\n\nUse a generic procedure.\n", encoding="utf-8")

            responses = workspace.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "tmcp_prepare_composition",
                            "arguments": {
                                "objective": "Prepare migration evidence.",
                                "project_path": str(workspace.project),
                                "source_path": str(workspace.project),
                                "limit": 3,
                                "candidate_limit": 3,
                                "explicitly_scoped_paths": [fixture_path],
                            },
                        },
                    }
                ]
            )

            result = cast(Mapping[str, object], responses[0]["result"])
            structured = cast(Mapping[str, object], result["structuredContent"])
            slices = cast(list[Mapping[str, object]], structured["candidate_source_slices"])
            fixture_slice = next(
                item for item in slices if item["relative_path"] == fixture_path
            )
            self.assertIn("migration-seed", {str(item["source_node_id"]) for item in slices})
            hints = cast(Mapping[str, object], structured["scoped_seed_graph_hints"])
            closure = cast(Mapping[str, object], hints["declared_dependency_closure"])
            required = cast(list[Mapping[str, object]], closure["required_dependency_nodes"])
            self.assertEqual(required[0]["source_node_id"], fixture_slice["source_node_id"])

    def test_mcp_prepare_composition_reserves_rich_seed_metadata(self) -> None:
        with TestWorkspace() as workspace:
            assert workspace.project is not None
            (workspace.project / "AGENTS.md").write_text(
                "# Rules\n\nKeep migration evidence traceable.\n",
                encoding="utf-8",
            )
            (workspace.project / "scoped-packet-seeds.json").write_text(
                json.dumps(
                    {
                        "schema": "tmcp-scoped-packet-seeds-v0.1",
                        "seeds": [
                            {
                                "id": "migration-seed",
                                "use_when": [
                                    "Migrate a database schema with rollback evidence."
                                ],
                                "chains_after": ["checksum-verifier"],
                                "phase_transitions": {
                                    "implementation": {
                                        "next_phases": ["verification"],
                                        "activate_skills": ["checksum-verifier"],
                                        "verification_gates": [
                                            "Migration artifact is ready for checksum verification."
                                        ],
                                    }
                                },
                                "verification_expectations": [
                                    "Checksum verification passes."
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            verifier = workspace.project / "skills" / "checksum-verifier" / "SKILL.md"
            verifier.parent.mkdir(parents=True)
            verifier.write_text(
                "# Checksum verifier\n\nConsume the checksum handoff and verify it.\n",
                encoding="utf-8",
            )
            responses = workspace.run_mcp(
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "tmcp_prepare_composition",
                            "arguments": {
                                "objective": "Migrate a database schema with rollback evidence and checksum verification.",
                                "project_path": str(workspace.project),
                                "source_path": str(workspace.project),
                                "candidate_limit": 4,
                                "max_total_chars": 6000,
                                "max_total_tokens": 1600,
                            },
                        },
                    }
                ]
            )

        result = cast(Mapping[str, object], responses[0]["result"])
        structured = cast(Mapping[str, object], result["structuredContent"])
        diagnostics = cast(Mapping[str, object], structured["diagnostics"])
        costs = cast(Mapping[str, object], diagnostics["context_cost"])
        self.assertGreater(cast(int, costs["scoped_seed_hint_tokens"]), 0)
        self.assertEqual(
            costs["reserved_metadata_tokens"], costs["scoped_seed_hint_tokens"]
        )
        self.assertLessEqual(cast(int, costs["preflight_total_tokens"]), 1600)
        hints = cast(Mapping[str, object], structured["scoped_seed_graph_hints"])
        self.assertEqual(hints["typed_edges"], [])
        self.assertNotIn("phase_transition_nodes", hints)
