from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.schema_contract_support import assert_matches_schema
from tmcp_runtime.services.composition_evaluation import (
    assess_project_recipe_promotion,
)
from tmcp_runtime.domain.composition_benchmark_receipt_projection import (
    build_benchmark_receipt_provenance,
)
from tmcp_runtime.domain.composition_phase_bindings import build_phase_capsule_binding
from tmcp_runtime.domain.composition_runtime_capsules import build_runtime_capsule
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.harvest_nodes import content_digest_for
from tmcp_runtime.services.project_recipes import (
    build_project_composition_recipe_record,
    rehydrate_project_recipe_for_preflight,
)
import tmcp_runtime.storage.project_recipes as project_recipe_storage
from tmcp_runtime.storage import ArtifactStorageError, artifact_persistence_available
from tmcp_runtime.storage.project_recipes import (
    ProjectCompositionRecipeStore,
    ProjectRecipeError,
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
        "ordered_stages": [
            {
                "stage_id": "stage-1",
                "order": 1,
                "phase": "discovery",
                "status": "active",
                "entry_conditions": [],
                "node_ids": ["research"],
                "bridge_instructions": [
                    {
                        "node_id": "research",
                        "citations": ["slice-" + "c" * 20],
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
            "recipe_digest": "f" * 32,
            "content_digests": ["c" * 64],
        },
        "trust": "advisory_untrusted",
        "instruction_override_policy": "Never override governing instructions.",
    }
    plan["phase_capsule_binding"] = build_phase_capsule_binding(plan, _preflight())
    plan["runtime_capsule"] = build_runtime_capsule(plan, _preflight())
    return plan


def _preflight() -> dict[str, Any]:
    content = "Research with citations."
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


def _record() -> dict[str, Any]:
    plan = _plan()
    eligibility = assess_project_recipe_promotion(
        _receipts(),
        recipe_id="research-review",
        graph_digest=GRAPH_DIGEST,
        phase_capsule_binding=plan["phase_capsule_binding"],
    )
    return build_project_composition_recipe_record(
        recipe_id="research-review",
        composition_plan=plan,
        promotion_eligibility=eligibility,
        created_at="2026-07-17T00:00:00Z",
    )


def _legacy_v01_record(record: dict[str, Any]) -> dict[str, Any]:
    """Remove exactly the additive phase-capsule fields from a v0.1 record."""

    legacy = copy.deepcopy(record)
    legacy["composition_recipe"].pop("phase_capsule_binding")
    legacy["composition_recipe"].pop("runtime_capsule")
    eligibility = legacy["promotion_eligibility"]
    eligibility.pop("phase_capsule_binding_digest")
    evidence = eligibility["evidence"]
    for field in (
        "isolated_phase_capsule_receipt_count",
        "structurally_valid_phase_capsule_evidence_receipt_count",
        "bound_phase_capsule_evidence_receipt_count",
        "structurally_valid_benchmark_receipt_provenance_receipt_count",
        "bound_benchmark_receipt_provenance_receipt_count",
        "unqualified_context_execution_receipts",
        "invalid_phase_capsule_evidence_receipts",
        "unmatched_phase_capsule_provenance_receipts",
        "missing_benchmark_receipt_provenance_receipts",
        "invalid_benchmark_receipt_provenance_receipts",
        "unmatched_benchmark_receipt_provenance_receipts",
    ):
        evidence.pop(field, None)
    rejected_counts = evidence.get("rejected_receipt_counts")
    if isinstance(rejected_counts, dict):
        for field in (
            "unqualified_context_execution",
            "invalid_phase_capsule_evidence",
            "unmatched_phase_capsule_provenance",
            "missing_benchmark_receipt_provenance",
            "invalid_benchmark_receipt_provenance",
            "unmatched_benchmark_receipt_provenance",
        ):
            rejected_counts.pop(field, None)
    return legacy


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
            original_capsule = copy.deepcopy(
                original["composition_recipe"]["runtime_capsule"]
            )

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
        self.assertNotIn('"objective":', raw)
        self.assertNotIn('"candidate_source_slices":', raw)
        self.assertEqual(
            loaded.record["composition_recipe"]["runtime_capsule"],
            original_capsule,
        )
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
            payload["promotion_eligibility"]["evidence"][
                "unqualified_context_execution_receipts"
            ] = ["packet-1"]
            store.path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ProjectRecipeError, "promotion evidence"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

            payload = copy.deepcopy(original_payload)
            payload["promotion_eligibility"]["evidence"][
                "invalid_phase_capsule_evidence_receipts"
            ] = ["packet-1"]
            store.path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ProjectRecipeError, "promotion evidence"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

            payload = copy.deepcopy(original_payload)
            payload["promotion_eligibility"]["evidence"]["verified_receipt_count"] = 2
            store.path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ProjectRecipeError, "promotion evidence"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

            payload = copy.deepcopy(original_payload)
            payload["composition_recipe"]["runtime_capsule"]["capsule_digest"] = (
                "a" * 64
            )
            store.path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ProjectRecipeError, "runtime capsule"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

            store.path.write_text(
                json.dumps({"schema": "unexpected"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProjectRecipeError, "unsupported schema"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_load_uses_one_protected_read_for_phase_binding_digests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = ProjectCompositionRecipeStore.open(project, "research-review")
            record = _record()
            original_binding = record["composition_recipe"][
                "phase_capsule_binding"
            ]
            original_runtime_capsule = record["composition_recipe"][
                "runtime_capsule"
            ]
            store.create(record)
            protected_read = project_recipe_storage.read_json_input

            def mutate_after_protected_read(*args: object, **kwargs: object) -> object:
                source = protected_read(*args, **kwargs)
                store.path.write_text('{"schema":"replaced-after-read"}', encoding="utf-8")
                return source

            with patch.object(
                project_recipe_storage,
                "read_json_input",
                side_effect=mutate_after_protected_read,
            ), patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("recipe loading must not reopen the path"),
            ):
                loaded = store.load(
                    expected_graph_digest=GRAPH_DIGEST,
                    expected_composition_plan_id=PLAN_ID,
                )

        loaded_binding = loaded.record["composition_recipe"][
            "phase_capsule_binding"
        ]
        self.assertEqual(loaded_binding["binding_digest"], original_binding["binding_digest"])
        self.assertEqual(
            loaded_binding["phase_capsule_trace"],
            original_binding["phase_capsule_trace"],
        )
        self.assertEqual(
            loaded.record["composition_recipe"]["runtime_capsule"],
            original_runtime_capsule,
        )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_legacy_records_stay_inert(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "tmcp-project-composition-recipe-v0.1.schema.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = ProjectCompositionRecipeStore.open(project, "research-review")
            store.create(_record())
            persisted = json.loads(store.path.read_text(encoding="utf-8"))
            legacy = _legacy_v01_record(persisted)
            store.path.write_text(json.dumps(legacy), encoding="utf-8")

            assert_matches_schema(legacy, schema_path)
            loaded = store.load(
                expected_graph_digest=GRAPH_DIGEST,
                expected_composition_plan_id=PLAN_ID,
            )
            loaded_record = store.load_record()

        self.assertNotIn(
            "phase_capsule_binding",
            loaded.record["composition_recipe"],
        )
        self.assertEqual(
            loaded.metadata()["phase_capsule_binding_status"], "legacy_unbound"
        )
        self.assertEqual(
            loaded.metadata()["activation_eligibility"], "blocked_legacy_unbound"
        )
        self.assertEqual(
            loaded_record.metadata()["phase_capsule_binding_status"], "legacy_unbound"
        )
        with self.assertRaisesRegex(ValueError, "phase-capsule binding"):
            rehydrate_project_recipe_for_preflight(loaded.record, _preflight())

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_phase_bound_records_without_runtime_capsules_stay_readable_and_inert(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = ProjectCompositionRecipeStore.open(project, "research-review")
            store.create(_record())
            persisted = json.loads(store.path.read_text(encoding="utf-8"))
            persisted["composition_recipe"].pop("runtime_capsule")
            store.path.write_text(json.dumps(persisted), encoding="utf-8")

            loaded = store.load(
                expected_graph_digest=GRAPH_DIGEST,
                expected_composition_plan_id=PLAN_ID,
            )

        self.assertEqual(
            loaded.metadata()["phase_capsule_binding_status"], "verified"
        )
        self.assertEqual(loaded.metadata()["runtime_capsule_status"], "legacy_unbound")
        self.assertEqual(
            loaded.metadata()["activation_eligibility"],
            "blocked_runtime_capsule_unbound",
        )
        with self.assertRaisesRegex(ValueError, "runtime capsule"):
            rehydrate_project_recipe_for_preflight(loaded.record, _preflight())

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_create_and_load_reject_phase_binding_downgrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = ProjectCompositionRecipeStore.open(project, "research-review")
            legacy = _legacy_v01_record(_record())
            with self.assertRaisesRegex(ProjectRecipeError, "required for new records"):
                store.create(legacy)

            missing_runtime_capsule = _record()
            missing_runtime_capsule["composition_recipe"].pop("runtime_capsule")
            with self.assertRaisesRegex(ProjectRecipeError, "runtime capsule"):
                store.create(missing_runtime_capsule)

            store.create(_record())
            persisted = json.loads(store.path.read_text(encoding="utf-8"))
            downgraded = copy.deepcopy(persisted)
            downgraded["composition_recipe"].pop("phase_capsule_binding")
            store.path.write_text(json.dumps(downgraded), encoding="utf-8")
            with self.assertRaisesRegex(ProjectRecipeError, "incomplete or downgraded"):
                store.load(expected_graph_digest=GRAPH_DIGEST)

            legacy_lookalike = _legacy_v01_record(persisted)
            legacy_lookalike["promotion_eligibility"]["evidence"][
                "rejected_receipt_counts"
            ]["invalid_phase_capsule_evidence"] = 0
            store.path.write_text(json.dumps(legacy_lookalike), encoding="utf-8")
            with self.assertRaisesRegex(ProjectRecipeError, "incomplete or downgraded"):
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
        self.assertNotIn(
            "phase_capsule_binding",
            schema["$defs"]["composition_recipe"]["required"],
        )
        self.assertIn(
            "phase_capsule_binding",
            schema["$defs"]["composition_recipe"]["properties"],
        )
        self.assertNotIn(
            "runtime_capsule",
            schema["$defs"]["composition_recipe"]["required"],
        )
        self.assertIn(
            "runtime_capsule",
            schema["$defs"]["composition_recipe"]["properties"],
        )
        self.assertNotIn(
            "phase_capsule_binding_digest",
            schema["$defs"]["promotion_eligibility"]["required"],
        )
        self.assertIn(
            "phase_capsule_binding_digest",
            schema["$defs"]["promotion_eligibility"]["properties"],
        )
        self.assertIn(
            "missing_safety_gate_receipts",
            schema["$defs"]["promotion_eligibility"]["properties"]["evidence"][
                "required"
            ],
        )
        self.assertNotIn(
            "isolated_phase_capsule_receipt_count",
            schema["$defs"]["promotion_eligibility"]["properties"]["evidence"][
                "required"
            ],
        )
        self.assertNotIn(
            "unqualified_context_execution_receipts",
            schema["$defs"]["promotion_eligibility"]["properties"]["evidence"][
                "required"
            ],
        )
        self.assertNotIn(
            "structurally_valid_phase_capsule_evidence_receipt_count",
            schema["$defs"]["promotion_eligibility"]["properties"]["evidence"][
                "required"
            ],
        )
        self.assertNotIn(
            "invalid_phase_capsule_evidence_receipts",
            schema["$defs"]["promotion_eligibility"]["properties"]["evidence"][
                "required"
            ],
        )
        self.assertNotIn(
            "bound_phase_capsule_evidence_receipt_count",
            schema["$defs"]["promotion_eligibility"]["properties"]["evidence"][
                "required"
            ],
        )
        self.assertNotIn(
            "unmatched_phase_capsule_provenance_receipts",
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
