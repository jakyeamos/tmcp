from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_composition_benchmark import prepare_benchmark
from scripts.schema_contract_support import assert_matches_schema
from tmcp_runtime.domain.composition_benchmark_protocol import (
    build_benchmark_preparation,
    fixture_source_nodes,
    validate_benchmark_run_plan,
)
from tmcp_runtime.storage.artifacts import (
    ArtifactStorageError,
    AtomicArtifactStore,
    artifact_persistence_available,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCHEMAS = ROOT / "schemas"
ROUTING_PATH = FIXTURES / "composition_routing_golden_v0_6.json"
BEHAVIORAL_PATH = FIXTURES / "composition_behavioral_fixtures_v0_6.json"


def _payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must contain an object")
    return payload


class CompositionBenchmarkProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routing = _payload(ROUTING_PATH)
        cls.behavioral = _payload(BEHAVIORAL_PATH)

    def test_preparation_is_schema_valid_and_hides_score_oracles(self) -> None:
        plan, artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )

        assert_matches_schema(
            plan,
            SCHEMAS / "tmcp-composition-benchmark-run-plan-v0.1.schema.json",
        )
        validate_benchmark_run_plan(
            plan,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        serialized_plan = json.dumps(plan, sort_keys=True)
        for forbidden in (
            "expected_skill_ids",
            "expected_order",
            "expected_relationships",
            "quality_rubric",
        ):
            self.assertNotIn(forbidden, serialized_plan)
        self.assertEqual(plan["protocol"]["cache_policy"], "none")
        self.assertFalse(plan["protocol"]["automatic_tool_execution"])
        self.assertEqual(len(plan["fixture_workspaces"]), 5)
        self.assertGreaterEqual(len(plan["routing_requests"]), 20)
        self.assertEqual(len(plan["behavioral_requests"]), 5)
        self.assertIn("benchmark-run-plan.json", artifacts)
        self.assertTrue(
            all(
                path.startswith("fixtures/") for path in artifacts if "/skills/" in path
            )
        )
        self.assertTrue(
            all(
                path.startswith("host-inputs/")
                for path in artifacts
                if path.endswith("-preflight.json")
            )
        )

    def test_protocol_identity_is_root_independent_and_content_sensitive(self) -> None:
        first, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        second, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        first_fixture = self.behavioral["fixtures"][0]
        first_nodes = fixture_source_nodes(
            first_fixture,
            logical_workspace_root=Path("/one/fixture-root"),
        )
        second_nodes = fixture_source_nodes(
            first_fixture,
            logical_workspace_root=Path("/another/fixture-root"),
        )
        changed = copy.deepcopy(self.behavioral)
        changed["fixtures"][0]["skill_sources"][0]["content"] += "\nChanged."
        changed_plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=changed,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            [node["id"] for node in first_nodes],
            [node["id"] for node in second_nodes],
        )
        self.assertEqual(first["run_manifest_id"], second["run_manifest_id"])
        self.assertNotEqual(
            first["run_manifest_digest"], changed_plan["run_manifest_digest"]
        )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_prepare_materializes_exact_isolated_fixture_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "benchmark"
            result = prepare_benchmark(
                routing_golden_path=ROUTING_PATH,
                behavioral_fixtures_path=BEHAVIORAL_PATH,
                output_dir=output_dir,
            )
            plan = json.loads(
                (output_dir / "benchmark-run-plan.json").read_text(encoding="utf-8")
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["automatic_tool_execution"])
            self.assertEqual(result["receipt_persistence"], "not_performed")
            self.assertEqual(plan["run_manifest_id"], result["run_manifest_id"])
            self.assertFalse(
                (output_dir / "fixtures" / "benchmark-run-plan.json").exists()
            )
            for fixture in self.behavioral["fixtures"]:
                fixture_root = output_dir / "fixtures" / fixture["fixture_id"]
                for source in fixture["skill_sources"]:
                    self.assertEqual(
                        (fixture_root / source["relative_path"]).read_text(
                            encoding="utf-8"
                        ),
                        source["content"],
                    )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_tree_bundle_rejects_escape_and_nonempty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "benchmark"
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_tree_bundle(
                    output_dir,
                    {"fixtures/../outside.txt": "unsafe"},
                )
            AtomicArtifactStore.write_tree_bundle(
                output_dir,
                {"fixtures/one/skills/example/SKILL.md": "safe"},
            )
            self.assertEqual(
                (
                    output_dir / "fixtures" / "one" / "skills" / "example" / "SKILL.md"
                ).read_text(encoding="utf-8"),
                "safe",
            )
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_tree_bundle(
                    output_dir,
                    {"fixtures/two/skills/example/SKILL.md": "new"},
                )


if __name__ == "__main__":
    unittest.main()
