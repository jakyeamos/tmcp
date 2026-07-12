from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.safety import (
    collect_harvest_roots,
    iter_harvest_candidates,
    read_harvest_text,
    read_json_input,
    read_skill_inputs,
)
from tmcp_runtime.storage import (
    ArtifactStorageError,
    AtomicArtifactStore,
    artifact_persistence_available,
)


def _symlink_or_skip(test_case: unittest.TestCase, link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (NotImplementedError, OSError) as exc:
        test_case.skipTest(f"Symlinks are unavailable in this environment: {exc}")


class TmcpSafetyBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_external_file_symlink_is_never_harvested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            root = sandbox / "project"
            outside = sandbox / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "SKILL.md").write_text(
                "# In-root skill\n\nUse test evidence.\n",
                encoding="utf-8",
            )
            (outside / "secret.md").write_text(
                "# EXTERNAL_ONLY\n\nThis must never be harvested.\n",
                encoding="utf-8",
            )
            _symlink_or_skip(self, root / "linked.md", outside / "secret.md")

            for follow_symlinks in (False, True):
                with self.subTest(follow_symlinks=follow_symlinks):
                    result = self.server._harvest_skills(
                        {
                            "source_path": str(root),
                            "follow_symlinks": follow_symlinks,
                        }
                    )

                    self.assertEqual(result["source_count"], 1)
                    self.assertEqual(
                        [node["relative_path"] for node in result["source_nodes"]],
                        ["SKILL.md"],
                    )
                    self.assertNotIn("EXTERNAL_ONLY", json.dumps(result))
                    self.assertTrue(
                        any("symlink" in warning.lower() for warning in result["warnings"])
                    )

    def test_directory_symlink_and_cycle_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            root = sandbox / "project"
            outside = sandbox / "outside"
            skill = root / "docs" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            outside.mkdir()
            skill.write_text("# Internal\n\nUse verification.\n", encoding="utf-8")
            (outside / "SKILL.md").write_text(
                "# EXTERNAL_DIRECTORY\n\nDo not read.\n",
                encoding="utf-8",
            )
            _symlink_or_skip(self, root / "external-dir", outside)
            _symlink_or_skip(self, root / "loop", root)

            for follow_symlinks in (False, True):
                with self.subTest(follow_symlinks=follow_symlinks):
                    result = self.server._harvest_skills(
                        {
                            "source_path": str(root),
                            "follow_symlinks": follow_symlinks,
                        }
                    )

                    self.assertEqual(result["source_count"], 1)
                    self.assertEqual(
                        [node["relative_path"] for node in result["source_nodes"]],
                        ["docs/SKILL.md"],
                    )
                    self.assertNotIn("EXTERNAL_DIRECTORY", json.dumps(result))
                    self.assertTrue(
                        any("symlink" in warning.lower() for warning in result["warnings"])
                    )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_source_root_symlink_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            real_root = sandbox / "real-project"
            root_link = sandbox / "project-link"
            real_root.mkdir()
            (real_root / "SKILL.md").write_text(
                "# Linked root\n\nUse a test gate.\n",
                encoding="utf-8",
            )
            _symlink_or_skip(self, root_link, real_root)

            default_result = self.server._harvest_skills(
                {"source_path": str(root_link)}
            )
            followed_result = self.server._harvest_skills(
                {"source_path": str(root_link), "follow_symlinks": True}
            )
            followed_with_artifacts = self.server._harvest_skills(
                {
                    "source_path": str(root_link),
                    "follow_symlinks": True,
                    "write_artifacts": True,
                }
            )
            artifact_paths_exist = all(
                Path(path).exists()
                for path in followed_with_artifacts["artifact_paths"].values()
            )

        self.assertEqual(default_result["source_count"], 0)
        self.assertTrue(
            any("source-root symlink" in warning for warning in default_result["warnings"])
        )
        self.assertEqual(followed_result["source_count"], 1)
        self.assertEqual(
            followed_result["source_nodes"][0]["relative_path"],
            "SKILL.md",
        )
        self.assertEqual(
            followed_result["source_paths"],
            [str(root_link)],
        )
        self.assertTrue(artifact_paths_exist)

    def test_contained_file_symlink_is_harvested_only_with_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            target = root / "z-real.md"
            target.write_text("# In root\n\nUse a test gate.\n", encoding="utf-8")
            _symlink_or_skip(self, root / "00-alias.md", target)

            default_result = self.server._harvest_skills(
                {"source_path": str(root)}
            )
            followed_result = self.server._harvest_skills(
                {"source_path": str(root), "follow_symlinks": True}
            )

        self.assertEqual(
            [node["relative_path"] for node in default_result["source_nodes"]],
            ["z-real.md"],
        )
        self.assertEqual(
            [node["relative_path"] for node in followed_result["source_nodes"]],
            ["00-alias.md"],
        )

    def test_safe_reader_rejects_an_intermediate_symlink_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            root = sandbox / "project"
            original_directory = root / "sub"
            outside = sandbox / "outside"
            original_directory.mkdir(parents=True)
            outside.mkdir()
            (original_directory / "SKILL.md").write_text(
                "# Original\n\nUse verification.\n",
                encoding="utf-8",
            )
            (outside / "SKILL.md").write_text(
                "# EXTERNAL_SWAP\n\nDo not read this file.\n",
                encoding="utf-8",
            )
            roots, root_warnings = collect_harvest_roots(
                [str(root)],
                follow_symlinks=False,
            )
            candidates, candidate_warnings = iter_harvest_candidates(
                roots,
                self.server.DEFAULT_HARVEST_INCLUDE_GLOBS,
                self.server.DEFAULT_HARVEST_EXCLUDE_GLOBS,
                self.server.DEFAULT_HARVEST_EXCLUDE_DIR_NAMES,
                follow_symlinks=False,
            )
            self.assertEqual(root_warnings + candidate_warnings, [])
            self.assertEqual(len(candidates), 1)
            original_directory.rename(root / "sub-original")
            _symlink_or_skip(self, root / "sub", outside)

            source, warning = read_harvest_text(
                candidates[0],
                4096,
                redact_sensitive=True,
            )

        self.assertIsNone(source)
        self.assertIsNotNone(warning)
        self.assertIn("outside source root", str(warning))

    def test_source_path_with_symlinked_ancestor_requires_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            outside = sandbox / "outside"
            real_root = outside / "project"
            ancestor_link = sandbox / "linked-parent"
            real_root.mkdir(parents=True)
            (real_root / "SKILL.md").write_text(
                "# Skill\n\nUse a test gate.\n",
                encoding="utf-8",
            )
            _symlink_or_skip(self, ancestor_link, outside)
            source_path = ancestor_link / "project"

            default_result = self.server._harvest_skills(
                {"source_path": str(source_path)}
            )
            followed_result = self.server._harvest_skills(
                {"source_path": str(source_path), "follow_symlinks": True}
            )

        self.assertEqual(default_result["source_count"], 0)
        self.assertTrue(
            any("symlink component" in warning for warning in default_result["warnings"])
        )
        self.assertEqual(followed_result["source_count"], 1)

    def test_resolved_symlink_cannot_bypass_excluded_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            protected = root / ".aws"
            protected.mkdir(parents=True)
            (protected / "SKILL.md").write_text(
                "# Protected\n\nEXCLUDED_DIRECTORY_CONTENT\n",
                encoding="utf-8",
            )
            _symlink_or_skip(self, root / "docs", protected)

            result = self.server._harvest_skills(
                {"source_path": str(root), "follow_symlinks": True}
            )

        self.assertEqual(result["source_count"], 0)
        self.assertNotIn("EXCLUDED_DIRECTORY_CONTENT", json.dumps(result))
        self.assertTrue(any("Skipped directory" in warning for warning in result["warnings"]))

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_path_metadata_is_redacted_before_result_and_artifact_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            secret = "sk-" + "B" * 40
            root = sandbox / secret
            output_dir = sandbox / "artifacts"
            root.mkdir()
            (root / f"{secret}.md").write_text(
                "# Safe heading\n\nUse a verification gate.\n",
                encoding="utf-8",
            )

            result = self.server._harvest_skills(
                {
                    "source_path": str(root),
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                }
            )
            artifact_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output_dir.iterdir()
                if path.is_file()
            )

        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, artifact_text)
        self.assertIn("[REDACTED:", json.dumps(result))

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_redaction_precedes_titles_seed_parse_and_artifact_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            output_dir = Path(tmp) / "artifacts"
            root.mkdir()
            secret = "sk-" + "A" * 40
            (root / "AGENTS.md").write_text(
                "\n".join(
                    [
                        "---",
                        f"name: {secret}",
                        f"description: {secret}",
                        "---",
                        f"# {secret}",
                        "Use a test gate.",
                    ]
                ),
                encoding="utf-8",
            )
            scoped_payload = {
                "schema": "tmcp-scoped-packet-seeds-v0.1",
                "constraints": [secret],
                "seeds": [
                    {
                        "id": "safe_seed",
                        "name": secret,
                        "sources": [secret],
                        "use_when": [secret],
                        "behavior_atoms": [secret],
                        "verification_expectations": [secret],
                    }
                ],
            }
            encoded_secret = "sk-" + "\\u0041" * 40
            (root / "scoped-packet-seeds.json").write_text(
                json.dumps(scoped_payload).replace(secret, encoded_secret),
                encoding="utf-8",
            )

            result = self.server._harvest_skills(
                {
                    "source_path": str(root),
                    "write_artifacts": True,
                    "output_dir": str(output_dir),
                }
            )
            artifact_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output_dir.iterdir()
                if path.is_file()
            )

        serialized = json.dumps(result)
        self.assertNotIn(secret, serialized)
        self.assertNotIn(secret, artifact_text)
        self.assertIn("[REDACTED:", serialized)
        self.assertGreater(sum(result["redaction_summary"].values()), 0)
        seed_node = next(
            node for node in result["source_nodes"] if node["id"] == "safe_seed"
        )
        self.assertIn("[REDACTED:", seed_node["title"])
        self.assertNotIn(secret, " ".join(seed_node["source_references"]))

    def test_harvest_refuses_symlinked_artifact_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            root = sandbox / "project"
            outside = sandbox / "outside"
            output_link = sandbox / "artifact-link"
            output_dir = sandbox / "artifacts"
            root.mkdir()
            outside.mkdir()
            (root / "SKILL.md").write_text(
                "# Skill\n\nUse verification.\n",
                encoding="utf-8",
            )
            _symlink_or_skip(self, output_link, outside)

            with self.assertRaises(ArtifactStorageError):
                self.server._harvest_skills(
                    {
                        "source_path": str(root),
                        "write_artifacts": True,
                        "output_dir": str(output_link),
                    }
                )
            self.assertEqual(list(outside.iterdir()), [])

            parent_link = sandbox / "artifact-parent-link"
            _symlink_or_skip(self, parent_link, outside)
            with self.assertRaises(ArtifactStorageError):
                self.server._harvest_skills(
                    {
                        "source_path": str(root),
                        "write_artifacts": True,
                        "output_dir": str(parent_link / "nested"),
                    }
                )
            self.assertEqual(list(outside.iterdir()), [])

            output_dir.mkdir()
            sentinel = outside / "sentinel.json"
            sentinel.write_text("unchanged", encoding="utf-8")
            _symlink_or_skip(
                self,
                output_dir / "tmcp-packet-seed.json",
                sentinel,
            )
            with self.assertRaises(ArtifactStorageError):
                self.server._harvest_skills(
                    {
                        "source_path": str(root),
                        "write_artifacts": True,
                        "output_dir": str(output_dir),
                    }
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")
            self.assertFalse((output_dir / "tmcp-harvest-result.json").exists())

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_atomic_write_preserves_old_file_on_commit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "artifacts"
            store = AtomicArtifactStore.explicit(output_dir)
            target = store.write_json("artifact.json", {"state": "old"})

            with patch(
                "tmcp_runtime.storage.artifacts.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaises(ArtifactStorageError):
                    store.write_json("artifact.json", {"state": "new"})

            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"state": "old"})
            self.assertEqual(list(output_dir.glob(".artifact.json.*.tmp")), [])
            if os.name != "nt":
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_store_rejects_output_directory_swap_after_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            output_dir = sandbox / "artifacts"
            moved_output_dir = sandbox / "moved-artifacts"
            outside = sandbox / "outside"
            outside.mkdir()
            store = AtomicArtifactStore.explicit(output_dir)
            output_dir.rename(moved_output_dir)
            _symlink_or_skip(self, output_dir, outside)

            with self.assertRaises(ArtifactStorageError):
                store.write_json("artifact.json", {"state": "new"})

            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse((moved_output_dir / "artifact.json").exists())

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_store_rejects_ordinary_directory_swap_after_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            output_dir = sandbox / "artifacts"
            moved_output_dir = sandbox / "moved-artifacts"
            store = AtomicArtifactStore.explicit(output_dir)
            output_dir.rename(moved_output_dir)
            output_dir.mkdir()

            with self.assertRaises(ArtifactStorageError):
                store.write_json("artifact.json", {"state": "new"})

            self.assertFalse((output_dir / "artifact.json").exists())
            self.assertFalse((moved_output_dir / "artifact.json").exists())

    def test_storage_fails_closed_without_descriptor_relative_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "artifacts"
            bundle_dir = root / "bundle"
            with patch(
                "tmcp_runtime.storage.artifacts._supports_descriptor_relative_operations",
                return_value=False,
            ):
                with self.assertRaises(ArtifactStorageError):
                    AtomicArtifactStore.explicit(output_dir)
                with self.assertRaises(ArtifactStorageError):
                    AtomicArtifactStore.write_bundle(
                        bundle_dir,
                        json_artifacts={"report.json": {"ok": True}},
                        text_artifacts={"report.md": "# Report\n"},
                    )

            self.assertFalse(output_dir.exists())
            self.assertFalse(bundle_dir.exists())

    @unittest.skipIf(
        artifact_persistence_available(),
        "This platform provides descriptor-relative artifact persistence.",
    )
    def test_native_unsupported_platform_rejects_all_artifact_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "artifacts"
            bundle_dir = root / "bundle"

            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.explicit(output_dir)
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_bundle(
                    bundle_dir,
                    json_artifacts={"report.json": {"ok": True}},
                )

            self.assertFalse(output_dir.exists())
            self.assertFalse(bundle_dir.exists())

    def test_default_receipt_write_fails_closed_without_safe_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmcp_home = Path(tmp) / "tmcp-home"
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                with patch(
                    "tmcp_runtime.storage.artifacts._supports_descriptor_relative_operations",
                    return_value=False,
                ), self.assertRaises(ArtifactStorageError):
                    self.server._record_receipt(
                        {"packet_id": "packet-123", "outcome": "passed"}
                    )
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

            self.assertFalse(tmcp_home.exists())

    def test_default_review_and_promotion_writes_fail_closed_without_safe_storage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            review_dir = Path(tmp) / "review"
            promotion_dir = Path(tmp) / "promotion"
            root.mkdir()
            (root / "SKILL.md").write_text(
                "# Release\n\nUse package verification.\n",
                encoding="utf-8",
            )

            with patch(
                "tmcp_runtime.storage.artifacts._supports_descriptor_relative_operations",
                return_value=False,
            ):
                with self.assertRaises(ArtifactStorageError):
                    self.server._standalone_review_plan(
                        {
                            "objective": "Review release safety",
                            "project_path": str(root),
                            "output_dir": str(review_dir),
                            "harvest_sources": False,
                        }
                    )
                with self.assertRaises(ArtifactStorageError):
                    self.server._promote_harvest(
                        {
                            "source_path": str(root),
                            "output_dir": str(promotion_dir),
                            "persist_global": False,
                        }
                    )

            self.assertFalse(review_dir.exists())
            self.assertFalse(promotion_dir.exists())

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_atomic_bundle_replaces_an_empty_destination_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "artifacts"
            output_dir.mkdir()

            paths = AtomicArtifactStore.write_bundle(
                output_dir,
                json_artifacts={"report.json": {"ok": True}},
                text_artifacts={"report.md": "# Report\n"},
            )

            self.assertEqual(set(paths), {"report.json", "report.md"})
            self.assertTrue(all(Path(path).exists() for path in paths.values()))

    def test_exact_skill_inputs_are_bounded_to_real_skill_files_and_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            project = sandbox / "project"
            outside = sandbox / "outside"
            project.mkdir()
            outside.mkdir()
            secret = "sk-" + "A" * 40
            skill = project / "SKILL.md"
            skill.write_text(f"# {secret}\n\nUse a verification gate.\n", encoding="utf-8")
            not_a_skill = project / "notes.md"
            not_a_skill.write_text("# Notes\n", encoding="utf-8")
            external_skill = outside / "SKILL.md"
            external_skill.write_text("# External\n", encoding="utf-8")

            inputs = read_skill_inputs([skill], project_path=project)
            with self.assertRaises(ValueError):
                read_skill_inputs([not_a_skill], project_path=project)
            with self.assertRaises(ValueError):
                read_skill_inputs([external_skill], project_path=project)

        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0].display_relative_path, "SKILL.md")
        self.assertNotIn(secret, inputs[0].text)
        self.assertIn("[REDACTED:", inputs[0].text)

    def test_exact_file_inputs_reject_symlinks_and_redact_decoded_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            project = sandbox / "project"
            outside = sandbox / "outside"
            project.mkdir()
            outside.mkdir()
            external_skill = outside / "SKILL.md"
            external_skill.write_text("# External\n", encoding="utf-8")
            linked_skill = project / "SKILL.md"
            _symlink_or_skip(self, linked_skill, external_skill)
            secret = "sk-" + "B" * 40
            encoded_secret = "sk-" + "\\u0042" * 40
            plan_path = project / "plan.json"
            plan_path.write_text(
                json.dumps({"token": secret}).replace(secret, encoded_secret),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                read_skill_inputs([linked_skill], project_path=project)
            plan = read_json_input(plan_path)

        serialized = json.dumps(plan.payload)
        self.assertNotIn(secret, serialized)
        self.assertIn("[REDACTED:", serialized)
        self.assertGreater(sum(plan.redactions.values()), 0)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_atomic_bundle_never_publishes_a_partial_harvest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "artifacts"
            real_replace = os.replace
            replace_calls = 0

            def fail_second_replace(*args: object, **kwargs: object) -> None:
                nonlocal replace_calls
                replace_calls += 1
                if replace_calls == 2:
                    raise OSError("second write failed")
                real_replace(*args, **kwargs)

            with patch(
                "tmcp_runtime.storage.artifacts.os.replace",
                side_effect=fail_second_replace,
            ):
                with self.assertRaises(ArtifactStorageError):
                    AtomicArtifactStore.write_json_bundle(
                        output_dir,
                        {
                            "tmcp-harvest-result.json": {"result": True},
                            "tmcp-packet-seed.json": {"packet": True},
                        },
                    )

            self.assertFalse(output_dir.exists())
            self.assertEqual(list(Path(tmp).glob(".artifacts.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
