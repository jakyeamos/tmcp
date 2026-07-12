from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests import test_tmcp_mcp_server as helpers
from tmcp_runtime.storage import artifact_persistence_available


class TmcpArtifactIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_opaque_storage_key_preserves_identity_with_a_long_display_name(
        self,
    ) -> None:
        common_prefix = "release-" + "x" * 300
        raw_values = [f"{common_prefix}-left", f"{common_prefix}-right"]
        keys = [
            self.server._opaque_storage_key(raw_value, raw_value)
            for raw_value in raw_values
        ]

        self.assertEqual(len(set(keys)), 2)
        self.assertTrue(all(len(key) <= 113 for key in keys))
        for raw_value, key in zip(raw_values, keys):
            self.assertTrue(
                key.endswith(hashlib.sha256(raw_value.encode()).hexdigest()[:32])
            )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_redacted_receipt_ids_keep_distinct_opaque_storage_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmcp_home = Path(tmp) / "tmcp-home"
            secret_ids = ["sk-" + letter * 40 for letter in ("A", "B")]
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                results = [
                    self.server._record_receipt(
                        {"packet_id": packet_id, "outcome": "passed"}
                    )
                    for packet_id in secret_ids
                ]
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

            paths = [Path(result["artifact_paths"]["receipt_json"]) for result in results]
            contents = [path.read_text(encoding="utf-8") for path in paths]
            paths_exist = [path.exists() for path in paths]

        self.assertEqual(len(set(paths)), 2)
        self.assertTrue(all(paths_exist))
        for packet_id, path, content, result in zip(
            secret_ids, paths, contents, results
        ):
            self.assertIn(
                hashlib.sha256(packet_id.encode()).hexdigest()[:32],
                path.name,
            )
            self.assertNotIn(packet_id, path.name)
            self.assertNotIn(packet_id, content)
            self.assertNotIn(packet_id, json.dumps(result))

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_redacted_promotion_names_keep_distinct_artifact_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            source_root = sandbox / "project"
            tmcp_home = sandbox / "tmcp-home"
            source_root.mkdir()
            (source_root / "SKILL.md").write_text(
                "# Release readiness\n\nUse release checks and package verification.\n",
                encoding="utf-8",
            )
            secret_names = ["sk-" + letter * 40 for letter in ("C", "D")]
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                results = [
                    self.server._promote_harvest(
                        {
                            "source_path": str(source_root),
                            "candidate_workflows": ["release_readiness"],
                            "selected_workflows": ["release_readiness_workflow"],
                            "min_confidence": 0.1,
                            "promotion_name": promotion_name,
                        }
                    )
                    for promotion_name in secret_names
                ]
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

            local_paths = [
                Path(result["artifact_paths"]["promotion_graph_json"]) for result in results
            ]
            global_paths = [
                Path(result["global_artifact_paths"]["promotion_graph_json"])
                for result in results
            ]
            artifact_paths_exist = [
                path.exists() for path in [*local_paths, *global_paths]
            ]

        self.assertEqual(len({path.parent for path in local_paths}), 2)
        self.assertEqual(len({path.parent for path in global_paths}), 2)
        self.assertTrue(all(artifact_paths_exist))
        for promotion_name, local_path, global_path, result in zip(
            secret_names, local_paths, global_paths, results
        ):
            expected_digest = hashlib.sha256(promotion_name.encode()).hexdigest()[:32]
            self.assertIn(expected_digest, local_path.parent.name)
            self.assertIn(expected_digest, global_path.parent.name)
            self.assertNotIn(promotion_name, json.dumps(result))

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_long_promotion_name_uses_a_bounded_storage_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            source_root = sandbox / "project"
            tmcp_home = sandbox / "tmcp-home"
            source_root.mkdir()
            (source_root / "SKILL.md").write_text(
                "# Release readiness\n\nUse release checks and package verification.\n",
                encoding="utf-8",
            )
            promotion_name = "release-" + "x" * 300
            original_home = getattr(self.server, "TMCP_HOME", None)
            setattr(self.server, "TMCP_HOME", tmcp_home)
            try:
                result = self.server._promote_harvest(
                    {
                        "source_path": str(source_root),
                        "candidate_workflows": ["release_readiness"],
                        "selected_workflows": ["release_readiness_workflow"],
                        "min_confidence": 0.1,
                        "promotion_name": promotion_name,
                    }
                )
                local_path = Path(result["artifact_paths"]["promotion_graph_json"])
                global_path = Path(
                    result["global_artifact_paths"]["promotion_graph_json"]
                )
                paths_exist = local_path.exists() and global_path.exists()
            finally:
                setattr(self.server, "TMCP_HOME", original_home)

        expected_digest = hashlib.sha256(promotion_name.encode()).hexdigest()[:32]
        self.assertTrue(paths_exist)
        self.assertLessEqual(len(local_path.parent.name), 113)
        self.assertEqual(local_path.parent.name, global_path.parent.name)
        self.assertTrue(local_path.parent.name.endswith(expected_digest))


if __name__ == "__main__":
    unittest.main()
