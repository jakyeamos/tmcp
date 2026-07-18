from __future__ import annotations

import copy
import unittest
from typing import Any

from tmcp_runtime.domain.composition_runtime_capsules import (
    RuntimeCapsuleError,
    rehydrate_runtime_capsule,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.harvest_nodes import content_digest_for
from tmcp_runtime.services.compose import prepare_composition_from_source_nodes
from tests import test_tmcp_composition_integration as composition_integration


class CompositionRuntimeCapsuleTests(unittest.TestCase):
    def setUp(self) -> None:
        harness = composition_integration.CompositionIntegrationTests()
        harness.setUp()
        self.arguments = copy.deepcopy(harness.arguments)
        self.nodes = copy.deepcopy(harness.nodes)
        self.preflight = prepare_composition_from_source_nodes(
            self.arguments,
            source_nodes=self.nodes,
        )
        harness.nodes = self.nodes
        packet = harness._compose(
            {
                **self.arguments,
                "semantic_proposal": harness._proposal(self.preflight),
            }
        )
        self.plan = copy.deepcopy(packet["composition_plan"])

    @staticmethod
    def _slice(preflight: dict[str, Any], node_id: str) -> dict[str, Any]:
        return next(
            item
            for item in preflight["candidate_source_slices"]
            if item["source_node_id"] == node_id
        )

    def _prepare(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return prepare_composition_from_source_nodes(
            self.arguments,
            source_nodes=nodes,
        )

    def test_exact_fresh_snapshot_rehydrates_the_closed_capsule(self) -> None:
        result = rehydrate_runtime_capsule(
            self.plan,
            self.preflight,
            self.nodes,
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["aliases"], [])
        self.assertEqual(result["composition_preflight"], self.preflight)

    def test_same_content_rename_aliases_the_original_plan_node(self) -> None:
        renamed_nodes = copy.deepcopy(self.nodes)
        for node in renamed_nodes:
            if node["id"] == "implement":
                node["id"] = "implement-renamed"
                break
        fresh_preflight = self._prepare(renamed_nodes)

        result = rehydrate_runtime_capsule(
            self.plan,
            fresh_preflight,
            renamed_nodes,
        )

        self.assertTrue(result["accepted"])
        self.assertIn(
            {"from_node_id": "implement-renamed", "to_node_id": "implement"},
            result["aliases"],
        )
        self.assertTrue(
            any(node.get("id") == "implement" for node in result["source_nodes"])
        )

    def test_changed_cited_source_is_rejected(self) -> None:
        changed_nodes = copy.deepcopy(self.nodes)
        replacement = "Implement a changed and independently verified plan."
        digest = content_digest_for(replacement)
        for node in changed_nodes:
            if node["id"] == "implement":
                node["signal_excerpt"] = replacement
                node["content_digest"] = digest
                break
        fresh_preflight = self._prepare(changed_nodes)

        result = rehydrate_runtime_capsule(
            self.plan,
            fresh_preflight,
            changed_nodes,
        )

        self.assertFalse(result["accepted"])
        self.assertIn(
            "runtime_capsule_source_unavailable",
            {issue["code"] for issue in result["issues"]},
        )

    def test_missing_cited_source_is_rejected(self) -> None:
        fresh_preflight = copy.deepcopy(self.preflight)
        fresh_preflight["candidate_source_slices"] = [
            item
            for item in fresh_preflight["candidate_source_slices"]
            if item["source_node_id"] != "implement"
        ]
        missing_nodes = [node for node in self.nodes if node["id"] != "implement"]

        result = rehydrate_runtime_capsule(
            self.plan,
            fresh_preflight,
            missing_nodes,
        )

        self.assertFalse(result["accepted"])
        self.assertIn(
            "runtime_capsule_source_unavailable",
            {issue["code"] for issue in result["issues"]},
        )

    def test_ambiguous_fresh_slice_is_rejected(self) -> None:
        fresh_preflight = copy.deepcopy(self.preflight)
        fresh_preflight["candidate_source_slices"].append(
            copy.deepcopy(self._slice(fresh_preflight, "implement"))
        )

        result = rehydrate_runtime_capsule(
            self.plan,
            fresh_preflight,
            self.nodes,
        )

        self.assertFalse(result["accepted"])
        self.assertIn(
            "runtime_capsule_source_ambiguous",
            {issue["code"] for issue in result["issues"]},
        )

    def test_one_fresh_source_cannot_rehydrate_two_original_nodes(self) -> None:
        forged_plan = copy.deepcopy(self.plan)
        capsule = forged_plan["runtime_capsule"]
        duplicate = copy.deepcopy(
            next(
                item
                for item in capsule["cited_source_slices"]
                if item["original_node_id"] == "implement"
            )
        )
        duplicate["original_node_id"] = "implement-shadow"
        capsule["cited_source_slices"] = sorted(
            [*capsule["cited_source_slices"], duplicate],
            key=lambda item: (
                item["original_node_id"],
                item["source_digest"],
                item["slice_digest"],
                item["char_start"],
                item["char_end"],
            ),
        )
        capsule["capsule_digest"] = stable_digest(
            {
                key: value
                for key, value in capsule.items()
                if key != "capsule_digest"
            }
        )

        result = rehydrate_runtime_capsule(
            forged_plan,
            self.preflight,
            self.nodes,
        )

        self.assertFalse(result["accepted"])
        self.assertIn(
            "runtime_capsule_source_ambiguous",
            {issue["code"] for issue in result["issues"]},
        )

    def test_controls_objective_and_task_identity_mismatches_fail_closed(self) -> None:
        cases: list[tuple[str, dict[str, Any], str]] = []
        controls = copy.deepcopy(self.preflight)
        controls["preparation_controls"]["candidate_limit"] += 1
        cases.append(("controls", controls, "preparation controls changed"))
        objective = copy.deepcopy(self.preflight)
        objective["objective"] = "Draft a different implementation plan."
        cases.append(("objective", objective, "objective changed"))
        identity = copy.deepcopy(self.preflight)
        identity["task_identity"] = {"primary": "different_task"}
        cases.append(("task identity", identity, "task identity changed"))

        for label, preflight, message in cases:
            with self.subTest(label=label), self.assertRaisesRegex(
                RuntimeCapsuleError, message
            ):
                rehydrate_runtime_capsule(self.plan, preflight, self.nodes)

    def test_task_identity_ignores_scores_but_binds_routes_and_facets(self) -> None:
        volatile_identity = copy.deepcopy(self.preflight)
        volatile_identity["task_identity"]["confidence"] = 0.99
        volatile_identity["task_identity"]["signals"] = [
            {
                "route": "frontend_implementation",
                "score": 99.0,
                "evidence": ["runtime: changed files"],
            }
        ]

        rehydrated = rehydrate_runtime_capsule(
            self.plan,
            volatile_identity,
            self.nodes,
        )

        self.assertTrue(rehydrated["accepted"])

        for field, value in (
            ("active_routes", ["different_route"]),
            ("intent_facets", ["different_facet"]),
        ):
            changed_identity = copy.deepcopy(self.preflight)
            changed_identity["task_identity"][field] = value

            with self.subTest(field=field), self.assertRaisesRegex(
                RuntimeCapsuleError, "task identity changed"
            ):
                rehydrate_runtime_capsule(self.plan, changed_identity, self.nodes)


if __name__ == "__main__":
    unittest.main()
