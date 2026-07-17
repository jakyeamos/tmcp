from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from scripts.schema_contract_support import assert_matches_schema
from tests.test_tmcp_composition_benchmarks import CompositionBenchmarkTests
from tmcp_runtime.api.evaluation import evaluate_skills
from tmcp_runtime.domain.composition_runtime import advance_composition_runtime
from tmcp_runtime.domain.composition_benchmarks import score_composition_benchmark
from tmcp_runtime.domain.behavior_manifests import build_behavior_manifest_index
from tmcp_runtime.services.compose import (
    compose_packet_from_source_nodes,
    prepare_composition_from_source_nodes,
)
from tmcp_runtime.services.composition_evaluation import (
    assess_project_recipe_promotion,
)
from tmcp_runtime.services.project_recipes import (
    build_project_composition_recipe_record,
)
from tmcp_runtime.services.recompile import finalize_recompiled_packet
from tmcp_runtime.storage import artifact_persistence_available
from tmcp_runtime.storage.project_recipes import ProjectCompositionRecipeStore


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "tests" / "fixtures"


class CompositionSchemaInstanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = [
            {
                "id": "governing",
                "relative_path": "AGENTS.md",
                "path": "[REDACTED:path]/AGENTS.md",
                "source_type": "agent_operating_contract",
                "source_role": "governing_instruction",
                "activation_eligible": True,
                "title": "Governing rules",
                "signal_excerpt": "Read before modifying and preserve evidence.",
                "behavior_atoms": ["governing-scope"],
                "content_digest": "a" * 64,
                "token_estimate": 512,
                "routing_metadata": {},
                "trust": "untrusted_harvested_text",
            },
            {
                "id": "research",
                "relative_path": "skills/research/SKILL.md",
                "path": "[REDACTED:path]/skills/research/SKILL.md",
                "source_type": "skill_definition",
                "source_role": "active_skill",
                "activation_eligible": True,
                "title": "Research",
                "signal_excerpt": "Produce a cited brief and verify every source.",
                "behavior_atoms": ["source-verification"],
                "content_digest": "b" * 64,
                "token_estimate": 512,
                "routing_metadata": {},
                "trust": "untrusted_harvested_text",
            },
        ]
        self.arguments: dict[str, Any] = {
            "objective": "Research and verify a cited report",
            "project_path": "[REDACTED:path]",
            "phase": "start",
            "cache_policy": "none",
        }
        self.preflight = prepare_composition_from_source_nodes(
            self.arguments,
            source_nodes=self.nodes,
        )
        slices = {
            item["source_node_id"]: item
            for item in self.preflight["candidate_source_slices"]
        }
        self.proposal = {
            "schema": "tmcp-semantic-proposal-v0.1",
            "preflight_id": self.preflight["preflight_id"],
            "current_phase": "start",
            "task_model": {
                "deliverables": ["Cited report"],
                "success_criteria": ["Sources are verified"],
                "constraints": ["Preserve governing scope"],
                "subgoals": ["Research evidence", "Verify sources"],
                "evidence_needs": ["Citations and verification result"],
            },
            "skill_roles": [
                self._role(
                    slices["governing"],
                    "governing authority",
                    "start",
                    ["task objective"],
                    ["bounded constraints"],
                    "constraints applied",
                ),
                self._role(
                    slices["research"],
                    "research verifier",
                    "discovery",
                    ["bounded objective"],
                    ["cited evidence brief"],
                    "Sources are verified",
                    ["Sources are verified"],
                ),
            ],
            "relationships": [
                {
                    "from": "governing",
                    "to": "research",
                    "type": "enables",
                    "citations": [
                        slices["governing"]["slice_id"],
                        slices["research"]["slice_id"],
                    ],
                    "rationale": "Governing scope enables bounded research.",
                }
            ],
            "coverage": {
                "facets": ["Sources are verified"],
                "unresolved_gaps": [],
            },
            "trust": "advisory_untrusted",
        }

    @staticmethod
    def _role(
        source_slice: dict[str, Any],
        role: str,
        phase: str,
        inputs: list[str],
        outputs: list[str],
        exit_gate: str,
        covers: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "node_id": source_slice["source_node_id"],
            "role": role,
            "inputs": inputs,
            "outputs": outputs,
            "phase_affinity": [phase],
            "entry_gates": [],
            "exit_gates": [exit_gate],
            "context_cost": 999999,
            "covers": covers or [],
            "citations": [source_slice["slice_id"]],
        }

    def _compose(self, proposal: dict[str, Any] | None) -> dict[str, Any]:
        arguments = dict(self.arguments)
        if proposal is not None:
            arguments["semantic_proposal"] = proposal
        return compose_packet_from_source_nodes(
            arguments,
            source_nodes=self.nodes,
            global_graphs=[],
            receipts=[],
            cache_warnings=[],
            cache_home="[REDACTED:path]",
        )

    def test_prepare_accepted_rejected_and_recompiled_outputs_match_schemas(
        self,
    ) -> None:
        accepted = self._compose(self.proposal)
        rejected_proposal = copy.deepcopy(self.proposal)
        rejected_proposal["relationships"][0]["citations"] = []
        rejected = self._compose(rejected_proposal)
        runtime = advance_composition_runtime(accepted["composition_plan"], {})
        compatibility = self._compose(None)
        self.assertEqual(accepted["task_identity"]["primary"], "compound_task")
        self.assertEqual(
            accepted["task_identity"]["routing_status"], "compound_fallback"
        )
        self.assertEqual(accepted["task_identity"]["validated_routes"], [])
        state = {
            "objective": self.arguments["objective"],
            "combined_objective": self.arguments["objective"],
            "phase": "start",
            "suggested_phase": "start",
            "source_nodes": self.nodes,
            "task_identity": accepted["task_identity"],
            "task_identity_delta": None,
            "packet_delta": {
                "activated_atoms": [],
                "deactivated_atoms": [],
                "stale_atoms": [],
                "newly_required_reads": [],
                "suggested_phase": "start",
                "suggested_skills": [],
                "deferred_skills": ["research"],
                "family_context": {},
            },
            "next_verification_gate": [],
            "proposed_changes": [],
            "validated_changes": [],
            "warnings": [],
            "semantic_proposal_supplied": False,
            "composition_runtime": runtime,
            "runtime_evidence": {},
        }
        recompiled = finalize_recompiled_packet(
            {},
            state,
            previous_packet=accepted,
            composed_packet=compatibility,
            previous_packet_id=accepted["packet_id"],
        )

        assert_matches_schema(
            self.preflight,
            SCHEMAS / "tmcp-composition-preflight-v0.1.schema.json",
        )
        assert_matches_schema(
            self.preflight["behavior_manifest_index"],
            SCHEMAS / "tmcp-behavior-manifest-v0.1.schema.json",
        )
        assert_matches_schema(
            build_behavior_manifest_index(self.nodes),
            SCHEMAS / "tmcp-behavior-manifest-v0.1.schema.json",
        )
        legacy_preflight = copy.deepcopy(self.preflight)
        legacy_preflight.pop("behavior_manifest_index")
        legacy_preflight["diagnostics"].pop("context_cost")
        assert_matches_schema(
            legacy_preflight,
            SCHEMAS / "tmcp-composition-preflight-v0.1.schema.json",
        )
        assert_matches_schema(
            self.proposal,
            SCHEMAS / "tmcp-semantic-proposal-v0.1.schema.json",
        )
        assert_matches_schema(
            accepted["composition_plan"],
            SCHEMAS / "tmcp-composition-plan-v0.1.schema.json",
        )
        for packet in (accepted, rejected):
            assert_matches_schema(
                packet,
                SCHEMAS / "tmcp-composed-packet-v0.1.schema.json",
            )
        assert_matches_schema(
            recompiled,
            SCHEMAS / "tmcp-recompiled-packet-v0.1.schema.json",
        )

    def test_evaluation_plan_and_summary_match_published_schemas(self) -> None:
        plan = evaluate_skills(
            {
                "mode": "composition-plan",
                "composition_skill_ids": ["research", "review"],
            }
        )
        scores = {
            "baseline": 0.50,
            "naive_union": 0.70,
            "singleton:research": 0.62,
            "singleton:review": 0.60,
            "full_composition": 0.82,
            "leave_one_out:research": 0.68,
            "leave_one_out:review": 0.69,
            "wrong_order": 0.74,
        }
        results = [
            {
                **variant,
                "quality_score": scores[variant["variant_id"]],
                **(
                    {"context_tokens": 1000}
                    if variant["variant_id"] == "naive_union"
                    else {"context_tokens": 700}
                    if variant["variant_id"] == "full_composition"
                    else {}
                ),
            }
            for variant in plan["variants"]
        ]
        summary = evaluate_skills(
            {"mode": "composition-score", "composition_results": results}
        )

        assert_matches_schema(
            plan,
            SCHEMAS / "tmcp-composition-evaluation-plan-v0.1.schema.json",
        )
        assert_matches_schema(
            summary,
            SCHEMAS / "tmcp-composition-evaluation-summary-v0.1.schema.json",
        )

    def test_benchmark_assets_observations_and_summary_match_schemas(self) -> None:
        routing = json.loads(
            (FIXTURES / "composition_routing_golden_v0_6.json").read_text(
                encoding="utf-8"
            )
        )
        behavioral = json.loads(
            (FIXTURES / "composition_behavioral_fixtures_v0_6.json").read_text(
                encoding="utf-8"
            )
        )
        builder = CompositionBenchmarkTests()
        builder.setUpClass()
        routing_results = builder._routing_results()
        behavioral_results = builder._behavioral_results()
        observations = {
            "schema": "tmcp-composition-benchmark-observations-v0.1",
            "routing_results": routing_results,
            "behavioral_results": behavioral_results,
        }
        summary = score_composition_benchmark(
            golden_cases=routing["cases"],
            fixture_definitions=behavioral["fixtures"],
            routing_results=routing_results,
            behavioral_results=behavioral_results,
        )
        summary["observations_sha256"] = "a" * 64

        for payload, schema_name in (
            (routing, "tmcp-composition-routing-golden-v0.1.schema.json"),
            (
                behavioral,
                "tmcp-composition-behavioral-fixtures-v0.1.schema.json",
            ),
            (
                observations,
                "tmcp-composition-benchmark-observations-v0.1.schema.json",
            ),
            (
                {"ok": True, **summary},
                "tmcp-composition-benchmark-summary-v0.1.schema.json",
            ),
        ):
            assert_matches_schema(payload, SCHEMAS / schema_name)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_persisted_project_recipe_matches_published_schema(self) -> None:
        plan = self._compose(self.proposal)["composition_plan"]
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
                    {"gate_id": "safety", "category": "safety", "passed": True}
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
        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="research-review",
            graph_digest=graph_digest,
        )
        record = build_project_composition_recipe_record(
            recipe_id="research-review",
            composition_plan=plan,
            promotion_eligibility=eligibility,
            created_at="2026-07-17T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            persisted = ProjectCompositionRecipeStore.open(
                project,
                "research-review",
            ).create(record)

        assert_matches_schema(
            persisted.record,
            SCHEMAS / "tmcp-project-composition-recipe-v0.1.schema.json",
        )


if __name__ == "__main__":
    unittest.main()
