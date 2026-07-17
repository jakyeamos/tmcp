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
from tmcp_runtime.domain.composition_planning import build_composition_plan
from tmcp_runtime.services.project_recipes import (
    ProjectCompositionRecipeService,
    build_project_composition_recipe_record,
    rehydrate_project_recipe_for_preflight,
)


GRAPH_DIGEST = "a" * 32
PLAN_ID = "composition-" + "b" * 20


def _plan() -> dict[str, Any]:
    return {
        "schema": "tmcp-composition-plan-v0.1",
        "composition_plan_id": PLAN_ID,
        "current_phase": "research",
        "task_model": {"deliverables": ["reviewed report"]},
        "skill_roles": [{"node_id": "research", "role": "producer"}],
        "typed_edges": [],
        "ordered_stages": [{"stage_id": "stage-1", "node_ids": ["research"]}],
        "coverage": {"covered_criteria": ["cited"]},
        "provenance": {
            "graph_digest": GRAPH_DIGEST,
            "content_digests": ["c" * 64],
        },
        "trust": "advisory_untrusted",
        "instruction_override_policy": "Never override governing instructions.",
    }


def _receipts() -> list[dict[str, Any]]:
    return [
        {
            "packet_id": f"packet-{index}",
            "recipe_id": "research-review",
            "graph_digest": GRAPH_DIGEST,
            "composition_fixture_id": fixture,
            "outcome": "passed",
            "verification_results": ["focused tests passed"],
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
        for index, fixture in enumerate(("fixture-a", "fixture-a", "fixture-b"), 1)
    ]


def _preflight() -> dict[str, Any]:
    return {
        "schema": "tmcp-composition-preflight-v0.1",
        "preflight_id": "preflight-" + "f" * 20,
        "candidate_source_slices": [
            {
                "slice_id": "slice-" + "c" * 20,
                "source_node_id": "research",
                "source_digest": "d" * 64,
                "slice_digest": "e" * 64,
                "source_role": "active_skill",
                "content": "Research with citations.",
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


def _reusable_record() -> dict[str, Any]:
    plan = build_composition_plan(_proposal(), _preflight())
    return build_project_composition_recipe_record(
        recipe_id="research-review",
        composition_plan=plan,
        promotion_eligibility={
            "eligible": True,
            "recipe_id": "research-review",
            "graph_digest": plan["provenance"]["graph_digest"],
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
