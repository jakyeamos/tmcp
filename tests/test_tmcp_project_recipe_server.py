from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.schema_contract_support import assert_matches_schema
from tmcp_runtime.storage import artifact_persistence_available


SERVER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tmcp_mcp_server.py"
PROJECT_RECIPE_PROMOTION_SCHEMA_PATH = (
    SERVER_PATH.parents[1]
    / "schemas"
    / "tmcp-project-recipe-promotion-v0.1.schema.json"
)
_SERVER_RUNTIME = tempfile.TemporaryDirectory(prefix="tmcp-recipe-server-tests-")


def _server_environment() -> dict[str, str]:
    root = Path(_SERVER_RUNTIME.name)
    home = root / "home"
    tmcp_home = root / "tmcp-home"
    home.mkdir(exist_ok=True)
    tmcp_home.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["TMCP_HOME"] = str(tmcp_home)
    environment["AIOS_ROOT"] = str(root / "missing-aios")
    return environment


def load_server_module():
    spec = importlib.util.spec_from_file_location("tmcp_mcp_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load tmcp_mcp_server module")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, _server_environment(), clear=False):
        spec.loader.exec_module(module)
    return module


class TmcpProjectRecipeServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = load_server_module()

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_project_recipe_promotes_loads_revalidates_and_rejects_stale_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / "AGENTS.md").write_text(
                "# Rules\nRead before modifying and preserve evidence.\n",
                encoding="utf-8",
            )
            skill = project / "skills" / "research" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "# Research\nProduce a cited evidence brief and verify sources.\n",
                encoding="utf-8",
            )
            arguments = {
                "objective": "Research and verify a cited report",
                "project_path": str(project),
                "source_path": str(project),
                "phase": "start",
                "cache_policy": "none",
            }
            preflight = self.server._prepare_composition(arguments)
            slices = preflight["candidate_source_slices"]
            by_role = {item["source_role"]: item for item in slices}
            governing = by_role["governing_instruction"]
            research = by_role["active_skill"]

            def role(item, name, phase, inputs, outputs, gate, covers=None):
                return {
                    "node_id": item["source_node_id"],
                    "role": name,
                    "inputs": inputs,
                    "outputs": outputs,
                    "phase_affinity": [phase],
                    "entry_gates": [],
                    "exit_gates": [gate],
                    "context_cost": 999999,
                    "covers": covers or [],
                    "citations": [item["slice_id"]],
                }

            proposal = {
                "schema": "tmcp-semantic-proposal-v0.1",
                "preflight_id": preflight["preflight_id"],
                "current_phase": "start",
                "task_model": {
                    "deliverables": ["Cited report"],
                    "success_criteria": ["Sources are verified"],
                    "constraints": ["Preserve governing instructions"],
                    "subgoals": ["Research evidence", "Verify sources"],
                    "evidence_needs": ["Citations and verification result"],
                },
                "skill_roles": [
                    role(
                        governing,
                        "governing authority",
                        "start",
                        ["task objective"],
                        ["bounded constraints"],
                        "constraints applied",
                    ),
                    role(
                        research,
                        "researcher and verifier",
                        "discovery",
                        ["bounded objective"],
                        ["cited evidence brief"],
                        "Sources are verified",
                        ["Sources are verified"],
                    ),
                ],
                "relationships": [
                    {
                        "from": governing["source_node_id"],
                        "to": research["source_node_id"],
                        "type": "enables",
                        "citations": [
                            governing["slice_id"],
                            research["slice_id"],
                        ],
                        "rationale": "The governing scope enables bounded research.",
                    }
                ],
                "coverage": {
                    "facets": ["Sources are verified"],
                    "unresolved_gaps": [],
                },
                "trust": "advisory_untrusted",
            }
            packet = self.server._compose_packet(
                {**arguments, "semantic_proposal": proposal}
            )
            plan = packet["composition_plan"]
            graph_digest = plan["provenance"]["graph_digest"]
            receipts = [
                {
                    "packet_id": f"packet-{index}",
                    "recipe_id": "research-review",
                    "graph_digest": graph_digest,
                    "composition_fixture_id": fixture,
                    "outcome": "passed",
                    "verification_results": ["focused verification passed"],
                    "gate_results": [
                        {
                            "gate_id": "safety",
                            "category": "safety",
                            "passed": True,
                        }
                    ],
                    "user_overrides": [],
                    "quality_metrics": {
                        "synergy_lift": 0.12,
                        "compiler_lift": 0.08,
                        "order_lift": 0.07,
                    },
                    "cost_metrics": {"context_ratio": 0.70},
                }
                for index, fixture in enumerate(
                    ("fixture-a", "fixture-a", "fixture-b"), start=1
                )
            ]
            promoted = self.server._tool_promote_composition_recipe(
                {
                    "project_path": str(project),
                    "recipe_id": "research-review",
                    "composition_plan": plan,
                    "receipts": receipts,
                    "explicit_promotion": True,
                }
            )
            cached = self.server._compose_packet(
                {
                    **arguments,
                    "cache_policy": "project",
                    "project_recipe_id": "research-review",
                }
            )
            compatibility = self.server._compose_packet(arguments)

            self.assertEqual(promoted["status"], "promoted")
            self.assertEqual(
                promoted["schema"],
                "tmcp-project-recipe-promotion-v0.1",
            )
            self.assertEqual(
                promoted["promotion_eligibility"]["schema"],
                "tmcp-project-recipe-promotion-eligibility-v0.1",
            )
            self.assertEqual(
                promoted["recipe"]["promotion_eligibility"]["schema"],
                "tmcp-project-recipe-promotion-eligibility-v0.1",
            )
            assert_matches_schema(promoted, PROJECT_RECIPE_PROMOTION_SCHEMA_PATH)
            self.assertEqual(cached["project_recipe"]["recipe_id"], "research-review")
            self.assertEqual(
                cached["composition_plan"]["provenance"]["graph_digest"],
                graph_digest,
            )
            self.assertNotIn("composition_plan", compatibility)
            self.assertEqual(compatibility["global_cache"]["cache_policy"], "none")

            skill.write_text(
                "# Research\nProduce a cited brief, verify sources, and audit claims.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "stale"):
                self.server._compose_packet(
                    {
                        **arguments,
                        "cache_policy": "project",
                        "project_recipe_id": "research-review",
                    }
                )


if __name__ == "__main__":
    unittest.main()
