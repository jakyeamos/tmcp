from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from scripts import replay_handoff
from scripts.replay_handoff import formatter_fingerprint, main


class HandoffReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.payload = self.bundle / "files" / "nested" / "example.txt"
        self.payload.parent.mkdir(parents=True)
        self.payload.write_bytes(b"stable handoff\n")
        self.receipt = self.bundle / "handoffs" / "h3-v0.8" / "RECEIPT.md"
        self.receipt.parent.mkdir(parents=True)
        self.receipt.write_bytes(b"owner-aware receipt\n")
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

    def owner_aware_manifest(
        self,
        *,
        status: str = "verified",
        overlap: str = "none",
        freshness: str = "current",
        include_file_custody: bool = True,
    ) -> Path:
        digest = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        file_record: dict[str, object] = {
            "path": "nested/example.txt",
            "artifact_path": "files/nested/example.txt",
            "bytes": self.payload.stat().st_size,
            "sha256": digest,
        }
        if include_file_custody:
            file_record["custody"] = {"status": status, "overlap": overlap}
        manifest = self.bundle / "owner-aware.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "tmcp-handoff-manifest-v0.2",
                    "exact_base": "d" * 40,
                    "custody": {
                        "stream": "behavioral_atoms",
                        "owner": "worker-h3-v0.8",
                        "receipt": {
                            "reference": "handoffs/h3-v0.8/RECEIPT.md",
                            "sha256": hashlib.sha256(
                                self.receipt.read_bytes()
                            ).hexdigest(),
                            "freshness": freshness,
                            "observed_at": "2026-08-08T12:00:00Z",
                        },
                        "formatter_fingerprint": formatter_fingerprint(self.bundle),
                    },
                    "files": [file_record],
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def invoke_result(self, arguments: list[str]) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    @staticmethod
    def error_text(result: dict[str, object]) -> str:
        return cast(str, result["error"])

    def test_owner_aware_manifest_reports_custody(self) -> None:
        manifest = self.owner_aware_manifest()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["verify", str(manifest), "--require-custody"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["schema"], "tmcp-handoff-manifest-v0.2")
        self.assertEqual(result["custody"]["stream"], "behavioral_atoms")
        self.assertEqual(result["custody"]["owner"], "worker-h3-v0.8")
        self.assertEqual(result["custody"]["receipt"]["freshness"], "current")
        self.assertEqual(
            result["custody"]["formatter_fingerprint"],
            formatter_fingerprint(self.bundle),
        )
        self.assertEqual(
            result["files"][0]["custody"],
            {"status": "verified", "overlap": "none"},
        )

    def test_cli_exercises_owner_aware_gate(self) -> None:
        manifest = self.owner_aware_manifest()
        replay_script = (
            Path(__file__).resolve().parents[1] / "scripts" / "replay_handoff.py"
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(replay_script),
                "verify",
                str(manifest),
                "--require-custody",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["custody"]["owner"], "worker-h3-v0.8")

    def test_owner_aware_replay_preserves_custody_report(self) -> None:
        manifest = self.owner_aware_manifest()
        output = io.StringIO()
        destination = self.root / "owner-aware-worktree"
        with contextlib.redirect_stdout(output):
            self.assertEqual(
                main(
                    [
                        "replay",
                        str(manifest),
                        "--destination-root",
                        str(destination),
                        "--require-custody",
                    ]
                ),
                0,
            )
        result = json.loads(output.getvalue())
        self.assertEqual(
            result["files"][0]["custody"],
            {"status": "verified", "overlap": "none"},
        )

    def test_require_custody_rejects_legacy_manifest(self) -> None:
        self.assertEqual(
            self.invoke(["verify", str(self.manifest), "--require-custody"]), 2
        )

    def test_require_custody_rejects_stale_receipt(self) -> None:
        manifest = self.owner_aware_manifest(freshness="stale")
        self.assertEqual(self.invoke(["verify", str(manifest), "--require-custody"]), 2)

    def test_require_custody_accepts_matching_referenced_receipt_bytes(self) -> None:
        manifest = self.owner_aware_manifest()
        code, result = self.invoke_result(
            ["verify", str(manifest), "--require-custody"]
        )
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])

    def test_require_custody_rejects_missing_referenced_receipt(self) -> None:
        manifest = self.owner_aware_manifest()
        self.receipt.unlink()
        code, result = self.invoke_result(
            ["verify", str(manifest), "--require-custody"]
        )
        self.assertEqual(code, 2)
        error = self.error_text(result)
        self.assertIn("referenced receipt is missing", error)
        self.assertNotIn(str(self.root), error)

    def test_require_custody_rejects_mismatched_referenced_receipt_hash(self) -> None:
        manifest = self.owner_aware_manifest()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["custody"]["receipt"]["sha256"] = "0" * 64
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        code, result = self.invoke_result(
            ["verify", str(manifest), "--require-custody"]
        )
        self.assertEqual(code, 2)
        error = self.error_text(result)
        self.assertIn("receipt bytes SHA-256 mismatch", error)
        self.assertNotIn(str(self.root), error)

    def test_require_custody_rejects_non_file_referenced_receipt(self) -> None:
        manifest = self.owner_aware_manifest()
        self.receipt.unlink()
        self.receipt.mkdir()
        code, result = self.invoke_result(
            ["verify", str(manifest), "--require-custody"]
        )
        self.assertEqual(code, 2)
        self.assertIn("not a regular file", self.error_text(result))

    def test_require_custody_rejects_unreadable_referenced_receipt(self) -> None:
        manifest = self.owner_aware_manifest()
        with patch.object(
            replay_handoff,
            "_digest",
            side_effect=PermissionError("receipt access denied"),
        ):
            code, result = self.invoke_result(
                ["verify", str(manifest), "--require-custody"]
            )
        self.assertEqual(code, 2)
        error = self.error_text(result)
        self.assertIn("referenced receipt is unreadable", error)
        self.assertNotIn(str(self.root), error)

    def test_require_custody_rejects_malformed_receipt_reference(self) -> None:
        manifest = self.owner_aware_manifest()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["custody"]["receipt"]["reference"] = "../RECEIPT.md"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        code, result = self.invoke_result(
            ["verify", str(manifest), "--require-custody"]
        )
        self.assertEqual(code, 2)
        error = self.error_text(result)
        self.assertIn("safe relative path", error)
        self.assertNotIn(str(self.root), error)

    def test_require_custody_rejects_missing_formatter_fingerprint(self) -> None:
        manifest = self.owner_aware_manifest()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["custody"].pop("formatter_fingerprint")
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.invoke(["verify", str(manifest)]), 0)
        self.assertEqual(self.invoke(["verify", str(manifest), "--require-custody"]), 2)

    def test_require_custody_rejects_mismatched_formatter_fingerprint(self) -> None:
        manifest = self.owner_aware_manifest()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["custody"]["formatter_fingerprint"]["version"] = "0.0.0"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.invoke(["verify", str(manifest), "--require-custody"]), 2)

    def test_formatter_fingerprint_is_deterministic(self) -> None:
        self.assertEqual(
            formatter_fingerprint(self.bundle), formatter_fingerprint(self.bundle)
        )

    def test_legacy_manifest_is_readable_without_formatter_fingerprint(self) -> None:
        self.assertEqual(self.invoke(["verify", str(self.manifest)]), 0)

    def test_require_custody_rejects_unverified_or_overlapping_file(self) -> None:
        for status, overlap in (("source_only", "none"), ("verified", "shared")):
            with self.subTest(status=status, overlap=overlap):
                manifest = self.owner_aware_manifest(
                    status=status,
                    overlap=overlap,
                )
                self.assertEqual(
                    self.invoke(["verify", str(manifest), "--require-custody"]), 2
                )

    def test_owner_aware_manifest_requires_file_custody(self) -> None:
        manifest = self.owner_aware_manifest(include_file_custody=False)
        self.assertEqual(self.invoke(["verify", str(manifest)]), 2)

    def test_owner_aware_manifest_requires_canonical_byte_field(self) -> None:
        manifest = self.owner_aware_manifest()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["files"][0]["size"] = payload["files"][0].pop("bytes")
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.invoke(["verify", str(manifest)]), 2)

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
