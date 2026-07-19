from __future__ import annotations

import ast
import copy
import inspect
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tmcp_runtime.services.project_recipes as project_recipes
from tmcp_runtime.domain import compositional_intelligence as ci
from tmcp_runtime.domain.composition_planning import build_composition_plan
from tmcp_runtime.domain.composition_benchmark_receipt_projection import (
    build_benchmark_receipt_provenance,
)
from tmcp_runtime.domain.composition_phase_bindings import build_phase_capsule_binding
from tmcp_runtime.domain.composition_runtime_capsules import build_runtime_capsule
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.harvest_nodes import content_digest_for
from tmcp_runtime.services.project_recipes import (
    ProjectCompositionRecipeService,
    build_project_composition_recipe_record,
    rehydrate_project_recipe_for_preflight,
)
from tests.test_tmcp_compositional_intelligence import (
    _node as composition_node,
    _proposal as composition_proposal,
    _role as composition_role,
)


GRAPH_DIGEST = "a" * 32
PLAN_ID = "composition-" + "b" * 20


def _plan() -> dict[str, Any]:
    plan = {
        "schema": "tmcp-composition-plan-v0.1",
        "composition_plan_id": PLAN_ID,
        "preflight_id": "preflight-" + "f" * 20,
        "current_phase": "discovery",
        "task_model": {"deliverables": ["reviewed report"]},
        "skill_roles": [
            {
                "node_id": "research",
                "role": "producer",
                "citations": ["slice-" + "c" * 20],
            }
        ],
        "typed_edges": [],
        "handoff_contracts": [],
        "ordered_stages": [
            {
                "stage_id": "stage-1",
                "order": 1,
                "phase": "discovery",
                "status": "active",
                "entry_conditions": [],
                "node_ids": ["research"],
                "bridge_instructions": [],
                "handoff_contracts": [],
            }
        ],
        "coverage": {"covered_criteria": ["cited"]},
        "provenance": {
            "graph_digest": GRAPH_DIGEST,
            "recipe_digest": "f" * 32,
            "content_digests": ["c" * 64],
        },
        "trust": "advisory_untrusted",
        "instruction_override_policy": "Never override governing instructions.",
    }
    plan["phase_capsule_binding"] = build_phase_capsule_binding(plan, _preflight())
    plan["runtime_capsule"] = build_runtime_capsule(plan, _preflight())
    return plan


def _receipts() -> list[dict[str, Any]]:
    binding = _plan()["phase_capsule_binding"]
    receipts: list[dict[str, Any]] = []
    for index, fixture in enumerate(("fixture-a", "fixture-a", "fixture-b"), 1):
        receipt: dict[str, Any] = {
            "packet_id": f"packet-{index}",
            "recipe_id": PLAN_ID,
            "graph_digest": GRAPH_DIGEST,
            "composition_fixture_id": fixture,
            "outcome": "passed",
            "verification_results": ["focused tests passed"],
            "gate_results": [
                {"gate_id": "safety", "category": "safety", "passed": True}
            ],
            "user_overrides": [],
            "context_execution_mode": "isolated_phase_capsule",
            "composition_plan_digest": binding["composition_plan_digest"],
            "phase_capsule_binding_digest": binding["binding_digest"],
            "context_accounting_digest": binding["context_accounting_digest"],
            "preflight_capsule_digest": binding["preflight_capsule_digest"],
            "phase_capsule_trace": binding["phase_capsule_trace"],
            "benchmark_control_input_digest": "1" * 64,
            "benchmark_execution_recipe_digest": "2" * 64,
            "quality_metrics": {
                "synergy_lift": 0.12,
                "compiler_lift": 0.08,
                "order_lift": 0.07,
            },
            "cost_metrics": {"context_ratio": 0.70},
        }
        receipt["benchmark_receipt_provenance"] = build_benchmark_receipt_provenance(
            receipt,
            fixture_digest=stable_digest({"fixture_id": fixture}),
            control_plan_id="benchmark-control-" + "3" * 20,
            control_plan_digest="4" * 64,
            host_artifact_digest="5" * 64,
            host_receipt_digest="6" * 64,
        )
        receipts.append(receipt)
    return receipts


def _preflight() -> dict[str, Any]:
    content = "Research with cited sources."
    return {
        "schema": "tmcp-composition-preflight-v0.1",
        "preflight_id": "preflight-" + "f" * 20,
        "objective": "Review a cited research report.",
        "task_identity": {"primary": "research"},
        "preparation_controls": {
            "schema": "tmcp-composition-preparation-controls-v0.1",
            "candidate_limit": 12,
            "max_excerpt_chars": 1200,
            "max_total_chars": 12000,
            "max_total_tokens": 3000,
            "include_all_active_source_slices": False,
            "explicitly_scoped_paths": [],
        },
        "candidate_source_slices": [
            {
                "slice_id": "slice-" + "c" * 20,
                "source_node_id": "research",
                "relative_path": "skills/research/SKILL.md",
                "source_digest": "d" * 64,
                "slice_digest": content_digest_for(content),
                "behavior_atoms": [],
                "source_role": "active_skill",
                "content": content,
                "char_start": 0,
                "char_end": len(content),
                "mandatory": False,
            }
        ],
        "diagnostics": {},
    }


def _proposal() -> dict[str, Any]:
    return {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": "preflight-" + "f" * 20,
        "current_phase": "start",
        "task_model": {
            "deliverables": ["report"],
            "success_criteria": ["cited"],
            "constraints": [],
            "subgoals": ["research"],
            "evidence_needs": ["sources"],
        },
        "skill_roles": [
            {
                "node_id": "research",
                "role": "researcher",
                "inputs": ["task objective"],
                "outputs": ["sources"],
                "phase_affinity": ["start"],
                "entry_gates": [],
                "exit_gates": ["sources cited"],
                "context_cost": 100,
                "covers": ["cited"],
                "citations": ["slice-" + "c" * 20],
            }
        ],
        "relationships": [],
        "coverage": {"facets": ["cited"], "unresolved_gaps": []},
        "trust": "advisory_untrusted",
    }


def _aliasable_preflight() -> dict[str, Any]:
    content = "Research with cited sources."
    source_digest = "d" * 64
    slice_digest = content_digest_for(content)
    source_node_id = "research"
    slice_id = "slice-" + stable_digest(
        [source_digest, slice_digest, 0, len(content), source_node_id], 20
    )
    return {
        "schema": "tmcp-composition-preflight-v0.1",
        "preflight_id": "preflight-" + "f" * 20,
        "objective": "Review a cited research report.",
        "task_identity": {"primary": "research"},
        "preparation_controls": {
            "schema": "tmcp-composition-preparation-controls-v0.1",
            "candidate_limit": 12,
            "max_excerpt_chars": 1200,
            "max_total_chars": 12000,
            "max_total_tokens": 3000,
            "include_all_active_source_slices": False,
            "explicitly_scoped_paths": [],
        },
        "candidate_source_slices": [
            {
                "slice_id": slice_id,
                "source_node_id": source_node_id,
                "relative_path": "skills/research/SKILL.md",
                "source_digest": source_digest,
                "slice_digest": slice_digest,
                "behavior_atoms": [],
                "source_role": "active_skill",
                "content": content,
                "char_start": 0,
                "char_end": len(content),
                "mandatory": False,
            }
        ],
        "diagnostics": {},
    }


def _aliasable_proposal(preflight: Mapping[str, Any]) -> dict[str, Any]:
    source_slice = preflight["candidate_source_slices"][0]
    return {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": preflight["preflight_id"],
        "current_phase": "start",
        "task_model": {
            "deliverables": ["report"],
            "success_criteria": ["cited"],
            "constraints": [],
            "subgoals": ["research"],
            "evidence_needs": ["sources"],
        },
        "skill_roles": [
            {
                "node_id": source_slice["source_node_id"],
                "role": "researcher",
                "inputs": ["task objective"],
                "outputs": ["sources"],
                "phase_affinity": ["start"],
                "entry_gates": [],
                "exit_gates": ["sources cited"],
                "context_cost": 100,
                "covers": ["cited"],
                "citations": [source_slice["slice_id"]],
            }
        ],
        "relationships": [],
        "coverage": {"facets": ["cited"], "unresolved_gaps": []},
        "trust": "advisory_untrusted",
    }


def _aliasable_record() -> dict[str, Any]:
    preflight = _aliasable_preflight()
    plan = build_composition_plan(_aliasable_proposal(preflight), preflight)
    return build_project_composition_recipe_record(
        recipe_id="research-review",
        composition_plan=plan,
        promotion_eligibility={
            "eligible": True,
            "recipe_id": "research-review",
            "graph_digest": plan["provenance"]["graph_digest"],
            "phase_capsule_binding_digest": plan["phase_capsule_binding"][
                "binding_digest"
            ],
        },
        created_at="2026-07-17T00:00:00Z",
    )


def _renamed_aliasable_preflight(node_id: str = "research-renamed") -> dict[str, Any]:
    preflight = _aliasable_preflight()
    source_slice = preflight["candidate_source_slices"][0]
    source_slice["source_node_id"] = node_id
    source_slice["slice_id"] = "slice-" + stable_digest(
        [
            source_slice["source_digest"],
            source_slice["slice_digest"],
            source_slice["char_start"],
            source_slice["char_end"],
            node_id,
        ],
        20,
    )
    return preflight


def _handoff_preflight() -> dict[str, Any]:
    research_content = "Produce a cited research brief."
    implementation_content = "Implement from the research brief."
    return {
        "schema": "tmcp-composition-preflight-v0.1",
        "preflight_id": "preflight-" + "1" * 20,
        "objective": "Research, implement, and verify a bounded change.",
        "task_identity": {"primary": "research-implementation"},
        "preparation_controls": {
            "schema": "tmcp-composition-preparation-controls-v0.1",
            "candidate_limit": 12,
            "max_excerpt_chars": 1200,
            "max_total_chars": 12000,
            "max_total_tokens": 3000,
            "include_all_active_source_slices": False,
            "explicitly_scoped_paths": [],
        },
        "candidate_source_slices": [
            {
                "slice_id": "slice-" + "1" * 20,
                "source_node_id": "research",
                "relative_path": "skills/research/SKILL.md",
                "source_digest": "1" * 64,
                "slice_digest": content_digest_for(research_content),
                "behavior_atoms": [],
                "source_role": "active_skill",
                "content": research_content,
                "char_start": 0,
                "char_end": len(research_content),
                "mandatory": False,
            },
            {
                "slice_id": "slice-" + "2" * 20,
                "source_node_id": "implement",
                "relative_path": "skills/implement/SKILL.md",
                "source_digest": "2" * 64,
                "slice_digest": content_digest_for(implementation_content),
                "behavior_atoms": [],
                "source_role": "active_skill",
                "content": implementation_content,
                "char_start": 0,
                "char_end": len(implementation_content),
                "mandatory": False,
            },
        ],
        "diagnostics": {},
    }


def _handoff_proposal() -> dict[str, Any]:
    return {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": "preflight-" + "1" * 20,
        "current_phase": "discovery",
        "task_model": {
            "deliverables": ["working implementation"],
            "success_criteria": ["focused verification"],
            "constraints": [],
            "subgoals": ["research", "implement"],
            "evidence_needs": ["research brief"],
        },
        "skill_roles": [
            {
                "node_id": "research",
                "role": "researcher",
                "inputs": ["task objective"],
                "outputs": ["research brief"],
                "phase_affinity": ["discovery"],
                "entry_gates": [],
                "exit_gates": ["research brief"],
                "context_cost": 100,
                "covers": ["research brief"],
                "citations": ["slice-" + "1" * 20],
            },
            {
                "node_id": "implement",
                "role": "implementation specialist",
                "inputs": ["research brief"],
                "outputs": ["working implementation"],
                "phase_affinity": ["implementation"],
                "entry_gates": [],
                "exit_gates": ["focused verification"],
                "context_cost": 100,
                "covers": ["focused verification"],
                "citations": ["slice-" + "2" * 20],
            },
        ],
        "relationships": [
            {
                "from": "research",
                "to": "implement",
                "type": "produces",
                "citations": ["slice-" + "1" * 20],
                "rationale": "The research brief enables implementation.",
            }
        ],
        "coverage": {
            "facets": ["research brief", "focused verification"],
            "unresolved_gaps": [],
        },
        "trust": "advisory_untrusted",
    }


def _reusable_record() -> dict[str, Any]:
    plan = build_composition_plan(_proposal(), _preflight())
    return build_project_composition_recipe_record(
        recipe_id="research-review",
        composition_plan=plan,
        promotion_eligibility={
            "eligible": True,
            "recipe_id": "research-review",
            "graph_digest": plan["provenance"]["graph_digest"],
            "phase_capsule_binding_digest": plan["phase_capsule_binding"][
                "binding_digest"
            ],
        },
        created_at="2026-07-17T00:00:00Z",
    )


@dataclass
class _Snapshot:
    record: dict[str, Any]

    def metadata(self) -> dict[str, Any]:
        return {"key": "recipe-opaque", "state_effect": "project_local_write"}


class _Store:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None
        self.load_arguments: dict[str, Any] | None = None
        self.record: dict[str, Any] | None = None

    def create(self, record: Mapping[str, Any]) -> _Snapshot:
        self.created = copy.deepcopy(dict(record))
        return _Snapshot(copy.deepcopy(dict(record)))

    def load(
        self,
        *,
        expected_graph_digest: str,
        expected_composition_plan_id: str | None = None,
    ) -> _Snapshot:
        self.load_arguments = {
            "expected_graph_digest": expected_graph_digest,
            "expected_composition_plan_id": expected_composition_plan_id,
        }
        return _Snapshot({"recipe_id": "research-review"})

    def load_record(self) -> _Snapshot:
        if self.record is None:
            raise AssertionError("test record was not configured")
        return _Snapshot(copy.deepcopy(self.record))


class ProjectCompositionRecipeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _Store()
        self.opened: list[tuple[object, object]] = []

        def open_store(project_path: object, recipe_id: object) -> _Store:
            self.opened.append((project_path, recipe_id))
            return self.store

        self.service = ProjectCompositionRecipeService(
            open_store=open_store,
            now_iso=lambda: "2026-07-17T00:00:00Z",
        )

    def test_explicit_eligible_promotion_builds_a_bounded_plan_projection(self) -> None:
        plan = _plan()
        original = copy.deepcopy(plan)

        result = self.service.promote(
            {
                "project_path": "/project",
                "recipe_id": "research-review",
                "composition_plan": plan,
                "receipts": _receipts(),
                "explicit_promotion": True,
            }
        )

        self.assertEqual(plan, original)
        self.assertEqual(self.opened, [("/project", "research-review")])
        self.assertEqual(result["status"], "promoted")
        self.assertTrue(result["promotion_eligibility"]["eligible"])
        self.assertIsNotNone(self.store.created)
        assert self.store.created is not None
        projection = self.store.created["composition_recipe"]
        self.assertEqual(projection["graph_digest"], GRAPH_DIGEST)
        self.assertIn("runtime_capsule", projection)
        self.assertNotIn("objective", projection["runtime_capsule"])
        self.assertNotIn("task_identity", projection["runtime_capsule"])
        self.assertNotIn("content", str(projection["runtime_capsule"]))
        self.assertNotIn("provenance", projection)
        self.assertNotIn("content_digests", str(projection))
        self.assertEqual(self.store.created["activation_policy"], "explicit_load_only")

    def test_promotion_requires_explicit_consent_and_fixed_eligibility(self) -> None:
        arguments = {
            "project_path": "/project",
            "recipe_id": "research-review",
            "composition_plan": _plan(),
            "receipts": _receipts(),
        }
        with self.assertRaisesRegex(ValueError, "explicit_promotion"):
            self.service.promote(arguments)
        self.assertEqual(self.opened, [])

        arguments["explicit_promotion"] = True
        arguments["receipts"] = _receipts()[:2]
        with self.assertRaisesRegex(ValueError, "not eligible"):
            self.service.promote(arguments)
        self.assertEqual(self.opened, [])

    def test_promotion_rejects_mismatched_graph_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.service.promote(
                {
                    "project_path": "/project",
                    "recipe_id": "research-review",
                    "composition_plan": _plan(),
                    "graph_digest": "d" * 32,
                    "receipts": _receipts(),
                    "explicit_promotion": True,
                }
            )

    def test_promotion_requires_a_valid_runtime_capsule(self) -> None:
        plan = _plan()
        plan.pop("runtime_capsule")
        with self.assertRaisesRegex(ValueError, "runtime capsule"):
            self.service.promote(
                {
                    "project_path": "/project",
                    "recipe_id": "research-review",
                    "composition_plan": plan,
                    "receipts": _receipts(),
                    "explicit_promotion": True,
                }
            )
        self.assertEqual(self.opened, [])

    def test_promotion_rejects_missing_structured_safety_gate_evidence(self) -> None:
        receipts = _receipts()
        receipts[1]["gate_results"] = []

        with self.assertRaisesRegex(ValueError, "not eligible"):
            self.service.promote(
                {
                    "project_path": "/project",
                    "recipe_id": "research-review",
                    "composition_plan": _plan(),
                    "receipts": receipts,
                    "explicit_promotion": True,
                }
            )

        self.assertEqual(self.opened, [])

    def test_promotion_rejects_malformed_safe_phase_capsule_evidence(self) -> None:
        receipts = _receipts()
        receipts[0]["phase_capsule_trace"][0]["capsule_digest"] = "invalid"

        with self.assertRaisesRegex(ValueError, "invalid_phase_capsule_evidence"):
            self.service.promote(
                {
                    "project_path": "/project",
                    "recipe_id": "research-review",
                    "composition_plan": _plan(),
                    "receipts": receipts,
                    "explicit_promotion": True,
                }
            )

        self.assertEqual(self.opened, [])

    def test_load_is_exact_id_and_current_graph_only(self) -> None:
        result = self.service.load(
            {
                "project_path": "/project",
                "recipe_id": "research-review",
                "graph_digest": GRAPH_DIGEST,
                "composition_plan_id": PLAN_ID,
            }
        )

        self.assertEqual(result["status"], "loaded")
        self.assertEqual(self.opened, [("/project", "research-review")])
        self.assertEqual(
            self.store.load_arguments,
            {
                "expected_graph_digest": GRAPH_DIGEST,
                "expected_composition_plan_id": PLAN_ID,
            },
        )

    def test_recipe_rehydrates_only_against_current_cited_source_content(self) -> None:
        record = _reusable_record()

        hydrated = rehydrate_project_recipe_for_preflight(record, _preflight())

        self.assertEqual(
            hydrated["graph_digest"],
            record["graph_digest"],
        )
        self.assertEqual(
            hydrated["semantic_proposal"]["preflight_id"],
            _preflight()["preflight_id"],
        )

        edited = _preflight()
        edited["candidate_source_slices"][0]["source_digest"] = "9" * 64
        with self.assertRaisesRegex(ValueError, "stale"):
            rehydrate_project_recipe_for_preflight(record, edited)

        missing_citation = _preflight()
        missing_citation["candidate_source_slices"][0]["slice_id"] = "slice-" + "8" * 20
        with self.assertRaisesRegex(ValueError, "unknown_citation"):
            rehydrate_project_recipe_for_preflight(record, missing_citation)

    def test_recipe_rehydrates_with_immutable_proposal_coverage(self) -> None:
        preflight = _preflight()
        proposal = _proposal()
        proposal["coverage"] = {"facets": ["research"], "unresolved_gaps": []}
        plan = build_composition_plan(proposal, preflight)
        record = build_project_composition_recipe_record(
            recipe_id="research-review",
            composition_plan=plan,
            promotion_eligibility={
                "eligible": True,
                "recipe_id": "research-review",
                "graph_digest": plan["provenance"]["graph_digest"],
                "phase_capsule_binding_digest": plan["phase_capsule_binding"][
                    "binding_digest"
                ],
            },
            created_at="2026-07-17T00:00:00Z",
        )

        self.assertEqual(plan["proposal_coverage"], proposal["coverage"])
        self.assertEqual(plan["coverage"]["facets"], ["research", "cited"])
        self.assertEqual(
            record["composition_recipe"]["proposal_coverage"], proposal["coverage"]
        )
        hydrated = rehydrate_project_recipe_for_preflight(record, preflight)

        self.assertEqual(
            hydrated["composition_plan"]["composition_plan_id"],
            plan["composition_plan_id"],
        )
        legacy = copy.deepcopy(record)
        legacy["composition_recipe"].pop("proposal_coverage")
        with self.assertRaisesRegex(ValueError, "immutable proposal coverage"):
            rehydrate_project_recipe_for_preflight(legacy, preflight)

    def test_legacy_scoped_seed_recipe_without_closure_stays_inert(self) -> None:
        seed = composition_node(
            "migration-seed",
            "scoped_packet_seed",
            "scoped-packet-seeds.json#migration-seed",
            "Migration coordinator prepares migration evidence.",
        )
        preflight = ci.prepare_composition([seed], "Prepare migration evidence.")
        role = composition_role(
            preflight,
            "migration-seed",
            "migration coordinator",
            "implementation",
            inputs=["migration evidence"],
            outputs=["migration evidence"],
            exit_gates=["migration evidence is ready"],
            covers=["migration evidence"],
        )
        proposal = composition_proposal(preflight, [role], [])
        proposal["task_model"] = {
            "deliverables": ["migration evidence"],
            "success_criteria": ["migration evidence"],
            "constraints": [],
            "subgoals": ["migration evidence"],
            "evidence_needs": ["migration evidence"],
        }
        proposal["coverage"] = {
            "facets": ["migration evidence"],
            "unresolved_gaps": [],
        }
        validation = ci.validate_semantic_proposal(proposal, preflight)
        self.assertTrue(validation["valid"], validation["errors"])
        plan = ci.build_composition_plan(proposal, preflight)
        record = build_project_composition_recipe_record(
            recipe_id="migration-evidence",
            composition_plan=plan,
            promotion_eligibility={
                "eligible": True,
                "recipe_id": "migration-evidence",
                "graph_digest": plan["provenance"]["graph_digest"],
                "phase_capsule_binding_digest": plan["phase_capsule_binding"][
                    "binding_digest"
                ],
            },
            created_at="2026-07-17T00:00:00Z",
        )
        legacy = copy.deepcopy(record)
        legacy["composition_recipe"]["scoped_seed_graph_hints"].pop(
            "declared_dependency_closure"
        )

        with self.assertRaisesRegex(
            ValueError,
            "legacy scoped-seed metadata.*explicitly re-promote",
        ):
            rehydrate_project_recipe_for_preflight(legacy, preflight)

    def test_recipe_rehydrates_at_its_stored_compiler_phase(self) -> None:
        preflight = _handoff_preflight()
        plan = build_composition_plan(_handoff_proposal(), preflight)
        record = build_project_composition_recipe_record(
            recipe_id="research-implementation",
            composition_plan=plan,
            promotion_eligibility={
                "eligible": True,
                "recipe_id": "research-implementation",
                "graph_digest": plan["provenance"]["graph_digest"],
                "phase_capsule_binding_digest": plan["phase_capsule_binding"][
                    "binding_digest"
                ],
            },
            created_at="2026-07-17T00:00:00Z",
        )

        hydrated = rehydrate_project_recipe_for_preflight(
            record,
            preflight,
            current_phase="implementation",
        )

        self.assertEqual(hydrated["compiler_phase"], "discovery")
        self.assertEqual(hydrated["requested_runtime_phase"], "implementation")
        self.assertEqual(
            hydrated["semantic_proposal"]["current_phase"],
            record["composition_recipe"]["runtime_capsule"]["compiler_phase"],
        )
        self.assertEqual(
            hydrated["composition_plan"]["current_phase"],
            "discovery",
        )
        self.assertEqual(
            hydrated["composition_plan"]["phase_capsule_binding"]["binding_digest"],
            record["composition_recipe"]["phase_capsule_binding"]["binding_digest"],
        )
        self.assertEqual(
            hydrated["composition_plan"]["runtime_capsule"]["capsule_digest"],
            record["composition_recipe"]["runtime_capsule"]["capsule_digest"],
        )

    def test_recipe_rehydrate_restores_a_content_bound_node_alias(self) -> None:
        record = _aliasable_record()
        renamed_preflight = _renamed_aliasable_preflight()

        hydrated = rehydrate_project_recipe_for_preflight(record, renamed_preflight)

        self.assertEqual(
            renamed_preflight["candidate_source_slices"][0]["source_node_id"],
            "research-renamed",
        )
        self.assertEqual(
            hydrated["source_aliases"],
            [{"from_node_id": "research-renamed", "to_node_id": "research"}],
        )
        self.assertEqual(hydrated["aliases"], hydrated["source_aliases"])
        replay_slice = hydrated["composition_preflight"]["candidate_source_slices"][0]
        original_slice = _aliasable_preflight()["candidate_source_slices"][0]
        self.assertEqual(replay_slice["source_node_id"], "research")
        self.assertEqual(replay_slice["slice_id"], original_slice["slice_id"])
        self.assertEqual(
            hydrated["composition_plan"]["composition_plan_id"],
            record["composition_plan_id"],
        )
        self.assertEqual(
            hydrated["graph_digest"],
            record["graph_digest"],
        )

    def test_recipe_rehydrate_rejects_changed_or_ambiguous_node_aliases(self) -> None:
        record = _aliasable_record()
        changed = _renamed_aliasable_preflight()
        changed["candidate_source_slices"][0]["content"] = "Changed research guidance."
        with self.assertRaisesRegex(ValueError, "stale for current cited source"):
            rehydrate_project_recipe_for_preflight(record, changed)

        ambiguous = _renamed_aliasable_preflight()
        duplicate = copy.deepcopy(ambiguous["candidate_source_slices"][0])
        duplicate["source_node_id"] = "research-relocated-again"
        duplicate["slice_id"] = "slice-" + stable_digest(
            [
                duplicate["source_digest"],
                duplicate["slice_digest"],
                duplicate["char_start"],
                duplicate["char_end"],
                duplicate["source_node_id"],
            ],
            20,
        )
        ambiguous["candidate_source_slices"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "aliases are ambiguous"):
            rehydrate_project_recipe_for_preflight(record, ambiguous)

    def test_recipe_rehydrate_requires_a_valid_runtime_capsule(self) -> None:
        record = _reusable_record()
        missing = copy.deepcopy(record)
        missing["composition_recipe"].pop("runtime_capsule")
        with self.assertRaisesRegex(ValueError, "runtime capsule"):
            rehydrate_project_recipe_for_preflight(missing, _preflight())

        tampered = copy.deepcopy(record)
        tampered["composition_recipe"]["runtime_capsule"]["capsule_digest"] = (
            "a" * 64
        )
        with self.assertRaisesRegex(ValueError, "runtime capsule"):
            rehydrate_project_recipe_for_preflight(tampered, _preflight())

    def test_recipe_rehydrate_preserves_and_validates_typed_handoffs(self) -> None:
        preflight = _handoff_preflight()
        plan = build_composition_plan(_handoff_proposal(), preflight)
        record = build_project_composition_recipe_record(
            recipe_id="research-implementation",
            composition_plan=plan,
            promotion_eligibility={
                "eligible": True,
                "recipe_id": "research-implementation",
                "graph_digest": plan["provenance"]["graph_digest"],
                "phase_capsule_binding_digest": plan["phase_capsule_binding"][
                    "binding_digest"
                ],
            },
            created_at="2026-07-17T00:00:00Z",
        )

        hydrated = rehydrate_project_recipe_for_preflight(record, preflight)

        self.assertEqual(
            record["composition_recipe"]["handoff_contracts"],
            hydrated["composition_plan"]["handoff_contracts"],
        )
        tampered = copy.deepcopy(record)
        tampered["composition_recipe"]["handoff_contracts"][0]["produced_outputs"] = [
            "forged artifact"
        ]
        with self.assertRaisesRegex(ValueError, "handoff contracts"):
            rehydrate_project_recipe_for_preflight(tampered, preflight)

    def test_service_load_for_preflight_uses_exact_record_and_fresh_plan(self) -> None:
        self.store.record = _reusable_record()

        result = self.service.load_for_preflight(
            {
                "project_path": "/project",
                "recipe_id": "research-review",
                "composition_preflight": _preflight(),
            }
        )

        self.assertEqual(result["status"], "loaded_and_revalidated")
        self.assertEqual(
            result["composition_plan"]["schema"],
            "tmcp-composition-plan-v0.1",
        )
        self.assertEqual(self.opened, [("/project", "research-review")])

    def test_service_has_no_filesystem_or_storage_authority(self) -> None:
        source_path = Path(inspect.getfile(project_recipes))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden = (
            "os",
            "pathlib",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
        )
        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in modules
                for prefix in forbidden
            )
        )


if __name__ == "__main__":
    unittest.main()
