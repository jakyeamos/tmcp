from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from tmcp_runtime.domain import compositional_intelligence as ci

from tests.test_tmcp_compositional_intelligence import _edge, _node, _proposal, _role


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


class CompositionPlanTests(unittest.TestCase):
    def _build_fixture(
        self,
        *,
        renamed: bool = False,
        edited: bool = False,
        declared_build_digest: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        suffix = "-renamed" if renamed else ""
        nodes = [
            _node(
                f"root{suffix}",
                "agent_operating_contract",
                f"rules{suffix}/AGENTS.md",
                "Preserve task scope.",
            ),
            _node(
                f"build{suffix}",
                "skill_definition",
                f"skills{suffix}/build/SKILL.md",
                "Build the verified implementation."
                + (" Confirm edited behavior." if edited else ""),
                **(
                    {"content_digest": declared_build_digest}
                    if declared_build_digest is not None
                    else {}
                ),
            ),
            _node(
                f"verify{suffix}",
                "skill_definition",
                f"skills{suffix}/verify/SKILL.md",
                "Verify the implementation.",
            ),
        ]
        preflight = ci.prepare_composition(nodes, "Build and verify")
        root, build, verify = [str(node["id"]) for node in nodes]
        criterion = "Verification passes"
        roles = [
            _role(
                preflight,
                root,
                "governing authority",
                "start",
                inputs=["objective"],
                outputs=["scope"],
                exit_gates=["Scope is established"],
            ),
            _role(
                preflight,
                build,
                "builder",
                "implementation",
                inputs=["scope"],
                outputs=["implementation"],
                exit_gates=["Implementation is ready"],
            ),
            _role(
                preflight,
                verify,
                "verifier",
                "verification",
                inputs=["implementation"],
                outputs=["evidence"],
                covers=[criterion],
                exit_gates=[criterion],
            ),
        ]
        edges = [
            _edge(preflight, root, build, "enables"),
            _edge(preflight, verify, build, "verifies"),
        ]
        return preflight, _proposal(
            preflight, roles, edges, success_criteria=[criterion]
        )

    def test_plan_contains_stages_bridges_coverage_and_advisory_provenance(
        self,
    ) -> None:
        preflight, proposal = self._build_fixture()

        plan = ci.build_composition_plan(proposal, preflight)

        self.assertEqual(plan["schema"], ci.COMPOSITION_PLAN_SCHEMA)
        self.assertEqual(
            [stage["node_ids"][0] for stage in plan["ordered_stages"]],
            ["root", "build", "verify"],
        )
        self.assertEqual(
            [stage["status"] for stage in plan["ordered_stages"]],
            ["deferred", "active", "deferred"],
        )
        build_stage = plan["ordered_stages"][1]
        self.assertIn("Complete `root`", build_stage["entry_conditions"][-1])
        bridge = build_stage["bridge_instructions"][0]
        self.assertIn("using scope", bridge["instruction"])
        self.assertIn("produce implementation", bridge["instruction"])
        self.assertTrue(bridge["citations"])
        self.assertEqual(plan["coverage"]["uncovered_criteria"], [])
        self.assertEqual(plan["coverage"]["unresolved_gaps"], [])
        self.assertEqual(plan["trust"], "advisory_untrusted")
        self.assertEqual(
            plan["provenance"]["identity_policy"],
            "normalized_source_content_typed_relationships_and_declared_dependencies",
        )

    def test_same_phase_successor_stays_deferred_until_its_handoff_gate(self) -> None:
        preflight, proposal = self._build_fixture()
        proposal["skill_roles"][2]["phase_affinity"] = ["implementation"]

        plan = ci.build_composition_plan(proposal, preflight)

        self.assertEqual(
            [stage["phase"] for stage in plan["ordered_stages"]],
            ["start", "implementation", "implementation"],
        )
        self.assertEqual(
            [stage["status"] for stage in plan["ordered_stages"]],
            ["deferred", "active", "deferred"],
        )
        self.assertEqual(
            {role["node_id"]: role["activation"] for role in plan["skill_roles"]},
            {"root": "active", "build": "active", "verify": "deferred"},
        )
        self.assertIn(
            "Complete `build`",
            plan["ordered_stages"][2]["entry_conditions"][-1],
        )

    def test_optimizer_prunes_only_strictly_dominated_complement(self) -> None:
        nodes = [
            _node("root", "agent_operating_contract", "AGENTS.md", "Keep scope."),
            _node(
                "build",
                "skill_definition",
                "skills/build/SKILL.md",
                "Build the implementation.",
            ),
            _node(
                "duplicate-build",
                "skill_definition",
                "skills/duplicate/SKILL.md",
                "Build the implementation with the same handoff.",
            ),
            _node(
                "verify",
                "skill_definition",
                "skills/verify/SKILL.md",
                "Verify the implementation.",
            ),
        ]
        preflight = ci.prepare_composition(nodes, "Build and verify")
        criterion = "Working behavior is verified"
        root = _role(
            preflight,
            "root",
            "authority",
            "start",
            inputs=["objective"],
            outputs=["scope"],
            exit_gates=["Scope is ready"],
        )
        build = _role(
            preflight,
            "build",
            "builder",
            "implementation",
            inputs=["scope"],
            outputs=["implementation"],
        )
        duplicate = _role(
            preflight,
            "duplicate-build",
            "builder",
            "implementation",
            inputs=["scope"],
            outputs=["implementation"],
            exit_gates=["build handoff is ready"],
        )
        duplicate["context_cost"] = 500
        verify = _role(
            preflight,
            "verify",
            "verifier",
            "verification",
            inputs=["implementation"],
            outputs=["evidence"],
            covers=[criterion],
        )
        proposal = _proposal(
            preflight,
            [root, build, duplicate, verify],
            [
                _edge(preflight, "root", "build", "enables"),
                _edge(preflight, "build", "duplicate-build", "complements"),
                _edge(preflight, "build", "verify", "enables"),
            ],
            success_criteria=[criterion],
        )

        plan = ci.build_composition_plan(proposal, preflight)
        selection = plan["composition_diagnostics"]["subgraph_selection"]

        self.assertEqual(
            [role["node_id"] for role in plan["skill_roles"]],
            ["root", "build", "verify"],
        )
        self.assertEqual(
            selection["rejected_nodes"],
            [
                {
                    "node_id": "duplicate-build",
                    "reason": "strictly_dominated_redundant_complement",
                    "dominated_by": "build",
                }
            ],
        )
        self.assertLess(selection["context_ratio"], 1.0)
        self.assertEqual(
            selection["host_context_costs_ignored"]["duplicate-build"], 500
        )
        self.assertGreater(
            selection["source_context_costs"]["duplicate-build"],
            selection["source_context_costs"]["build"],
        )
        self.assertTrue(selection["required_dependency_closure_preserved"])

    def test_graph_identity_ignores_paths_but_changes_with_content(self) -> None:
        first_preflight, first_proposal = self._build_fixture()
        renamed_preflight, renamed_proposal = self._build_fixture(renamed=True)
        edited_preflight, edited_proposal = self._build_fixture(edited=True)

        first = ci.build_composition_plan(first_proposal, first_preflight)
        renamed = ci.build_composition_plan(renamed_proposal, renamed_preflight)
        edited = ci.build_composition_plan(edited_proposal, edited_preflight)

        self.assertEqual(
            first["provenance"]["graph_digest"],
            renamed["provenance"]["graph_digest"],
        )
        self.assertEqual(first["composition_plan_id"], renamed["composition_plan_id"])
        self.assertNotEqual(
            first["provenance"]["graph_digest"],
            edited["provenance"]["graph_digest"],
        )

    def test_visible_source_edits_cannot_reuse_a_stale_declared_digest(self) -> None:
        declared_digest = "a" * 64
        initial_preflight, initial_proposal = self._build_fixture(
            declared_build_digest=declared_digest
        )
        edited_preflight, edited_proposal = self._build_fixture(
            edited=True,
            declared_build_digest=declared_digest,
        )

        initial_slice = next(
            item
            for item in initial_preflight["candidate_source_slices"]
            if item["source_node_id"] == "build"
        )
        edited_slice = next(
            item
            for item in edited_preflight["candidate_source_slices"]
            if item["source_node_id"] == "build"
        )
        initial = ci.build_composition_plan(initial_proposal, initial_preflight)
        edited = ci.build_composition_plan(edited_proposal, edited_preflight)

        self.assertNotEqual(initial_slice["source_digest"], declared_digest)
        self.assertNotEqual(
            initial_slice["source_digest"], edited_slice["source_digest"]
        )
        self.assertNotEqual(
            initial_slice["visible_content_digest"],
            edited_slice["visible_content_digest"],
        )
        self.assertNotEqual(
            initial_preflight["preflight_id"], edited_preflight["preflight_id"]
        )
        self.assertNotEqual(
            initial["provenance"]["graph_digest"],
            edited["provenance"]["graph_digest"],
        )

    def test_recipe_identity_changes_when_handoff_or_gate_semantics_change(
        self,
    ) -> None:
        preflight, proposal = self._build_fixture()
        changed = copy.deepcopy(proposal)
        changed["skill_roles"][1]["outputs"] = ["verified implementation"]
        changed["skill_roles"][1]["exit_gates"] = ["Implementation is verified"]

        first = ci.build_composition_plan(proposal, preflight)
        second = ci.build_composition_plan(changed, preflight)

        self.assertEqual(
            first["provenance"]["graph_digest"],
            second["provenance"]["graph_digest"],
        )
        self.assertNotEqual(first["composition_plan_id"], second["composition_plan_id"])
        self.assertNotEqual(
            first["provenance"]["recipe_digest"],
            second["provenance"]["recipe_digest"],
        )

    def test_uncovered_criteria_and_process_only_roles_surface_diagnostics(
        self,
    ) -> None:
        preflight, proposal = self._build_fixture()
        proposal["task_model"]["success_criteria"].append("Accessibility passes")
        proposal["skill_roles"][1]["covers"] = []

        plan = ci.build_composition_plan(proposal, preflight)

        self.assertEqual(
            plan["coverage"]["uncovered_criteria"], ["Accessibility passes"]
        )
        self.assertIn(
            "Accessibility passes",
            plan["composition_diagnostics"]["missing_capabilities"],
        )
        self.assertIn("build", plan["composition_diagnostics"]["process_only_warnings"])

    def test_invalid_plan_raises_and_compile_envelope_stays_structured(self) -> None:
        preflight, proposal = self._build_fixture()
        proposal["relationships"][0]["citations"] = []

        with self.assertRaises(ci.SemanticProposalValidationError) as raised:
            ci.build_composition_plan(proposal, preflight)
        self.assertIn(
            "missing_citations", {item["code"] for item in raised.exception.errors}
        )

        compiled = ci.compile_semantic_composition(proposal, preflight)
        self.assertFalse(compiled["accepted"])
        self.assertIsNone(compiled["composition_plan"])
        self.assertFalse(compiled["validation"]["valid"])

    def test_experimental_schema_files_are_valid_json_and_match_runtime_names(
        self,
    ) -> None:
        expected = {
            "tmcp-composition-preflight-v0.1.schema.json": ci.PREFLIGHT_SCHEMA,
            "tmcp-semantic-proposal-v0.1.schema.json": ci.SEMANTIC_PROPOSAL_SCHEMA,
            "tmcp-composition-plan-v0.1.schema.json": ci.COMPOSITION_PLAN_SCHEMA,
        }
        for filename, schema_name in expected.items():
            with self.subTest(filename=filename):
                payload = json.loads(
                    (PLUGIN_ROOT / "schemas" / filename).read_text(encoding="utf-8")
                )
                self.assertEqual(payload["properties"]["schema"]["const"], schema_name)


if __name__ == "__main__":
    unittest.main()
