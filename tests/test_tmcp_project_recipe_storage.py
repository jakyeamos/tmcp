from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tmcp_runtime.services.composition_evaluation import (
    assess_project_recipe_promotion,
)
from tmcp_runtime.services.project_recipes import (
    build_project_composition_recipe_record,
)
from tmcp_runtime.storage import ArtifactStorageError, artifact_persistence_available
from tmcp_runtime.storage.project_recipes import (
    ProjectCompositionRecipeStore,
    ProjectRecipeError,
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
        "ordered_stages": [
            {
                "stage_id": "stage-1",
                "node_ids": ["research"],
                "bridge_instructions": [
                    {
                        "node_id": "research",
                        "instruction": (
                            "Use api_"
                            + "key="
                            + "abcdefgh"
                            + "12345678 for the fixture."
                        ),
                    }
                ],
            }
        ],
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


def _record() -> dict[str, Any]:
    eligibility = assess_project_recipe_promotion(
        _receipts(),
        recipe_id="research-review",
        graph_digest=GRAPH_DIGEST,
    )
    return build_project_composition_recipe_record(
        recipe_id="research-review",
        composition_plan=_plan(),
        promotion_eligibility=eligibility,
        created_at="2026-07-17T00:00:00Z",
    )


class ProjectCompositionRecipeStoreTests(unittest.TestCase):
    def test_project_and_recipe_identity_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            with self.assertRaisesRegex(ProjectRecipeError, "absolute"):
                ProjectCompositionRecipeStore.open(".", "research-review")
            for recipe_id in ("", "../escape", "name/child", "a" * 81):
                with self.subTest(recipe_id=recipe_id):
                    with self.assertRaises(ProjectRecipeError):
                        ProjectCompositionRecipeStore.open(project, recipe_id)
            with self.assertRaisesRegex(ProjectRecipeError, "sensitive"):
                ProjectCompositionRecipeStore.open(project, "sk-" + "A1" * 20)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_create_and_exact_load_are_opaque_bounded_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = ProjectCompositionRecipeStore.open(project, "research-review")
            original = _record()
            untouched = copy.deepcopy(original)

            created = store.create(original)
            loaded = store.load(
                expected_graph_digest=GRAPH_DIGEST,
                expected_composition_plan_id=PLAN_ID,
            )
            raw = store.path.read_text(encoding="utf-8")
            mode = store.path.stat().st_mode & 0o777

        self.assertEqual(original, untouched)
        self.assertEqual(created.record, loaded.record)
        self.assertRegex(store.key, r"^recipe-[a-f0-9]{32}$")
        self.assertNotIn("research-review", str(store.path.parent))
        self.assertNotIn("abcdefgh12345678", raw)
        self.assertIn("[REDACTED:secret_assignment]", raw)
        self.assertGreater(loaded.record["redaction_summary"]["secret_assignment"], 0)
        self.assertNotIn("content_digests", raw)
        self.assertEqual(loaded.metadata()["activation_policy"], "explicit_load_only")
        if os.name != "nt":
            self.assertEqual(mode, 0o600)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_create_is_explicit_and_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = ProjectCompositionRecipeStore.open(project, "research-review")
            store.create(_record())

            with self.assertRaises(ArtifactStorageError):
                store.create(_record())

            other = ProjectCompositionRecipeStore.open(project, "another-recipe")
            with self.assertRaises(ProjectRecipeError):
                other.load(expected_graph_digest=GRAPH_DIGEST)
            self.assertFalse(hasattr(store, "list"))
            self.assertFalse(hasattr(store, "scan"))

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_load_rejects_stale_tampered_and_malformed_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = ProjectCompositionRecipeStore.open(project, "research-review")
            store.create(_record())

            with self.assertRaisesRegex(ProjectRecipeError, "stale"):
                store.load(expected_graph_digest="d" * 32)

            original_payload = json.loads(store.path.read_text(encoding="utf-8"))
            payload = copy.deepcopy(original_payload)
            payload["promotion_eligibility"]["evidence"].pop(
                "missing_safety_gate_receipts"
            )
            store.path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ProjectRecipeError, "promotion evidence"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

            payload = copy.deepcopy(original_payload)
            payload["promotion_eligibility"]["evidence"]["verified_receipt_count"] = 2
            store.path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ProjectRecipeError, "promotion evidence"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

            store.path.write_text(
                json.dumps({"schema": "unexpected"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProjectRecipeError, "unsupported schema"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

    def test_schema_is_published_as_a_closed_record_contract(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "tmcp-project-composition-recipe-v0.1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertFalse(schema["additionalProperties"])
        self.assertIn("promotion_eligibility", schema["required"])
        self.assertIn(
            "missing_safety_gate_receipts",
            schema["$defs"]["promotion_eligibility"]["properties"]["evidence"][
                "required"
            ],
        )
        self.assertEqual(schema["properties"]["cache_policy"]["const"], "project")
        self.assertEqual(
            schema["properties"]["activation_policy"]["const"],
            "explicit_load_only",
        )


if __name__ == "__main__":
    unittest.main()
