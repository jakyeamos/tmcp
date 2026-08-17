from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.replay_handoff import main


class HandoffReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.payload = self.bundle / "files" / "nested" / "example.txt"
        self.payload.parent.mkdir(parents=True)
        self.payload.write_bytes(b"stable handoff\n")
        digest = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        self.manifest = self.bundle / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema": "tmcp-handoff-manifest-v0.1",
                    "exact_base": "a" * 40,
                    "files": [
                        {
                            "path": "nested/example.txt",
                            "artifact_path": "files/nested/example.txt",
                            "bytes": self.payload.stat().st_size,
                            "sha256": digest,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def invoke(arguments: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return main(arguments)

    def test_verify_and_replay_use_one_canonical_contract(self) -> None:
        self.assertEqual(self.invoke(["verify", str(self.manifest)]), 0)
        destination = self.root / "worktree"
        self.assertEqual(
            self.invoke(
                [
                    "replay",
                    str(self.manifest),
                    "--destination-root",
                    str(destination),
                ]
            ),
            0,
        )
        self.assertEqual(
            (destination / "nested/example.txt").read_bytes(), b"stable handoff\n"
        )
        self.assertEqual(
            self.invoke(
                [
                    "replay",
                    str(self.manifest),
                    "--destination-root",
                    str(destination),
                ]
            ),
            0,
        )

    def test_legacy_tmcp_manifest_is_normalized(self) -> None:
        legacy = self.bundle / "legacy.json"
        digest = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        legacy.write_text(
            json.dumps(
                {
                    "schema": "tmcp-iteration-handoff-v0.1",
                    "base": {"commit": "b" * 40},
                    "files": [
                        {
                            "path": "nested/example.txt",
                            "artifact_path": "files/nested/example.txt",
                            "sha256": digest,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.invoke(["verify", str(legacy)]), 0)

    def test_legacy_codex_manifest_is_normalized(self) -> None:
        legacy = self.bundle / "codex-manifest.json"
        digest = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        legacy.write_text(
            json.dumps(
                {
                    "handoff_version": "1.0",
                    "base": "c" * 40,
                    "changed_files": [
                        {
                            "repo_path": "nested/example.txt",
                            "bundle_path": "files/nested/example.txt",
                            "byte_size": self.payload.stat().st_size,
                            "sha256": digest,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        destination = self.root / "codex-worktree"
        self.assertEqual(self.invoke(["verify", str(legacy)]), 0)
        self.assertEqual(
            self.invoke(
                [
                    "replay",
                    str(legacy),
                    "--destination-root",
                    str(destination),
                ]
            ),
            0,
        )
        self.assertEqual(
            (destination / "nested/example.txt").read_bytes(), b"stable handoff\n"
        )

    def test_hash_mismatch_fails_before_replay(self) -> None:
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["files"][0]["sha256"] = "b" * 64
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        destination = self.root / "worktree"
        self.assertEqual(
            self.invoke(
                [
                    "replay",
                    str(self.manifest),
                    "--destination-root",
                    str(destination),
                ]
            ),
            2,
        )
        self.assertFalse(destination.exists())

    def test_canonical_manifest_requires_exact_base(self) -> None:
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload.pop("exact_base")
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.invoke(["verify", str(self.manifest)]), 2)

    def test_unsafe_manifest_path_is_rejected(self) -> None:
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        payload["files"][0]["path"] = "../outside.txt"
        self.manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.invoke(["verify", str(self.manifest)]), 2)

    def test_differing_destination_requires_force(self) -> None:
        destination = self.root / "worktree"
        target = destination / "nested/example.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"different\n")
        self.assertEqual(
            self.invoke(
                [
                    "replay",
                    str(self.manifest),
                    "--destination-root",
                    str(destination),
                ]
            ),
            2,
        )
        self.assertEqual(target.read_bytes(), b"different\n")
        self.assertEqual(
            self.invoke(
                [
                    "replay",
                    str(self.manifest),
                    "--destination-root",
                    str(destination),
                    "--force",
                ]
            ),
            0,
        )
        self.assertEqual(target.read_bytes(), b"stable handoff\n")
