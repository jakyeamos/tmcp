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
from tmcp_runtime.domain.composition_phase_capsules import (
    build_phase_capsule_accounting,
)
from tmcp_runtime.domain.composition_benchmark_receipt_projection import (
    build_benchmark_receipt_provenance,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.harvest_nodes import content_digest_for
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

    @staticmethod
    def _schema_instance_context_accounting(
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        """Build compiler-shaped phase accounting for the published instance test."""

        source_slices = observation["source_slices"]
        source_contents: dict[str, dict[str, Any]] = {}
        candidate_source_slices: list[dict[str, Any]] = []
        for source in source_slices:
            skill_id = str(source["skill_id"])
            content = str(source["content"])
            normalized_digest = content_digest_for(content)
            source_digest = str(source["source_digest"])
            source_contents[skill_id] = {
                "skill_id": skill_id,
                "source_node_id": str(source["source_node_id"]),
                "source_slice_id": str(source["slice_id"]),
                "source_role": "active_skill",
                "content": content,
                "content_digest": normalized_digest,
                "source_digest": source_digest,
            }
            candidate_source_slices.append(
                {
                    "slice_id": str(source["slice_id"]),
                    "source_node_id": str(source["source_node_id"]),
                    "source_role": "active_skill",
                    "source_digest": source_digest,
                    "slice_digest": normalized_digest,
                    "content": content,
                }
            )

        stages = [
            {
                "stage_id": str(stage["stage_id"]),
                "order": index,
                "phase": f"benchmark-phase-{index}",
                "status": "active" if index == 1 else "deferred",
                "active_skill_ids": list(stage["active_skill_ids"]),
                "entry_conditions": [],
                "bridge_instructions": [],
                "handoff_contracts": [],
            }
            for index, stage in enumerate(observation["active_stages"], start=1)
        ]
        typed_edges = [
            {
                "source_skill_id": str(relationship["source_id"]),
                "target_skill_id": str(relationship["target_id"]),
                "relationship_type": str(relationship["relation"]),
            }
            for relationship in observation["relationships"]
        ]
        composition_plan_id = str(observation["composition_plan_id"])
        return build_phase_capsule_accounting(
            task_model={
                "deliverables": [f"{observation['fixture_id']} benchmark result"],
                "success_criteria": ["phase-scoped execution is traceable"],
                "constraints": ["retain compiler-derived source provenance"],
            },
            preflight={
                "objective": f"Benchmark {observation['fixture_id']}",
                "semantic_proposal_contract": {
                    "schema": "tmcp-semantic-proposal-v0.1"
                },
                "behavior_manifest_index": {
                    "schema": "tmcp-behavior-manifest-index-v0.1"
                },
                "candidate_source_slices": candidate_source_slices,
            },
            source_projection={
                "composition_plan_id": composition_plan_id,
                "composition_plan_digest": stable_digest(
                    {"composition_plan_id": composition_plan_id}
                ),
                "graph_digest": str(observation["graph_digest"]),
                "stages": stages,
                "typed_edges": typed_edges,
                "handoff_contracts": [],
            },
            source_contents=source_contents,
            runtime_envelope={
                "schema": "tmcp-composition-phase-runtime-envelope-v0.1",
                "fixture_id": str(observation["fixture_id"]),
                "composition_plan_id": composition_plan_id,
                "graph_digest": str(observation["graph_digest"]),
            },
        )

    @classmethod
    def _attach_phase_capsule_schema_fields(
        cls,
        observation: dict[str, Any],
    ) -> None:
        """Attach a safe, compiler-shaped benchmark receipt to schema instances."""

        accounting = observation.get("context_accounting")
        if not isinstance(accounting, dict) or not {
            "phase_capsules",
            "context_accounting_digest",
            "preflight_capsule_digest",
            "runtime_peak_context_tokens",
            "naive_union_context_tokens",
        }.issubset(accounting):
            accounting = cls._schema_instance_context_accounting(observation)
            observation["context_accounting"] = accounting

        phase_capsules = accounting["phase_capsules"]
        safe_trace = [
            {
                "stage_id": str(capsule["stage_id"]),
                "capsule_digest": str(capsule["capsule_digest"]),
                "incoming_handoff_digests": list(
                    capsule["incoming_handoff_digests"]
                ),
            }
            for capsule in phase_capsules
        ]
        fixture_id = str(observation["fixture_id"])
        compiled_tokens = accounting["runtime_peak_context_tokens"]
        naive_tokens = accounting["naive_union_context_tokens"]
        run_receipt = observation["run_receipt"]
        run_receipt.update(
            {
                "cost_metrics": {
                    "context_tokens": compiled_tokens,
                    "context_ratio": round(compiled_tokens / naive_tokens, 4),
                },
                "context_execution_mode": "isolated_phase_capsule",
                "context_accounting_digest": accounting["context_accounting_digest"],
                "preflight_capsule_digest": accounting["preflight_capsule_digest"],
                "phase_capsule_trace": safe_trace,
            }
        )
        CompositionBenchmarkTests._refresh_benchmark_receipt_provenance(
            run_receipt,
            fixture_id=fixture_id,
        )
        observation["compiled_context_tokens"] = compiled_tokens
        observation["naive_context_tokens"] = naive_tokens
        observation["context_execution_mode"] = "isolated_phase_capsule"

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
        fixtures_by_id = {
            fixture["fixture_id"]: fixture for fixture in behavioral["fixtures"]
        }
        for result in behavioral_results:
            builder._refresh_behavioral_integrity(
                fixtures_by_id[result["fixture_id"]],
                result,
            )
            self._attach_phase_capsule_schema_fields(result)
            builder._refresh_behavioral_integrity(
                fixtures_by_id[result["fixture_id"]],
                result,
            )
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

        for result in behavioral_results:
            assert_matches_schema(
                result["context_accounting"],
                SCHEMAS / "tmcp-composition-context-accounting-v0.1.schema.json",
            )
            assert_matches_schema(
                result["run_receipt"],
                SCHEMAS / "tmcp-run-receipt-v0.1.schema.json",
            )

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
        phase_capsule_binding = plan["phase_capsule_binding"]
        receipts = [
            {
                "packet_id": f"packet-{index}",
                "recipe_id": plan["composition_plan_id"],
                "graph_digest": graph_digest,
                "composition_fixture_id": fixture,
                "outcome": "passed",
                "verification_results": ["focused verification passed"],
                "gate_results": [
                    {"gate_id": "safety", "category": "safety", "passed": True}
                ],
                "user_overrides": [],
                "context_execution_mode": "isolated_phase_capsule",
                "composition_plan_digest": phase_capsule_binding[
                    "composition_plan_digest"
                ],
                "phase_capsule_binding_digest": phase_capsule_binding[
                    "binding_digest"
                ],
                "context_accounting_digest": phase_capsule_binding[
                    "context_accounting_digest"
                ],
                "preflight_capsule_digest": phase_capsule_binding[
                    "preflight_capsule_digest"
                ],
                "phase_capsule_trace": phase_capsule_binding[
                    "phase_capsule_trace"
                ],
                "benchmark_control_input_digest": "1" * 64,
                "benchmark_execution_recipe_digest": "2" * 64,
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
        for receipt in receipts:
            receipt["benchmark_receipt_provenance"] = (
                build_benchmark_receipt_provenance(
                    receipt,
                    fixture_digest=stable_digest(
                        {"fixture_id": receipt["composition_fixture_id"]}
                    ),
                    control_plan_id="benchmark-control-" + "3" * 20,
                    control_plan_digest="4" * 64,
                    host_artifact_digest="5" * 64,
                    host_receipt_digest="6" * 64,
                )
            )
        eligibility = assess_project_recipe_promotion(
            receipts,
            recipe_id="research-review",
            graph_digest=graph_digest,
            phase_capsule_binding=phase_capsule_binding,
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
