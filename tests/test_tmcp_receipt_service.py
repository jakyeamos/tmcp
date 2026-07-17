from __future__ import annotations

import ast
import inspect
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tmcp_runtime.services.receipts as receipts_service
from tmcp_runtime.services.receipts import ReceiptService, ReceiptServiceContext


class ReceiptServiceTests(unittest.TestCase):
    def test_record_redacts_before_building_storage_path_and_writing(self) -> None:
        calls: list[tuple[str, object]] = []

        def build_receipt(
            arguments: Mapping[str, Any], created_at: str
        ) -> dict[str, Any]:
            calls.append(("build", (arguments, created_at)))
            return {"packet_id": arguments["packet_id"], "outcome": "passed"}

        def redact_receipt(
            receipt: Mapping[str, Any],
        ) -> tuple[dict[str, Any], dict[str, int]]:
            calls.append(("redact", receipt))
            return (
                {"packet_id": "[REDACTED:id]", "outcome": receipt["outcome"]},
                {"secret": 1},
            )

        def storage_key(raw_id: str, safe_id: str) -> str:
            calls.append(("key", (raw_id, safe_id)))
            return "safe-key"

        def build_path(
            created_at: str,
            key: str,
            safe_receipt: Mapping[str, Any],
        ) -> Path:
            calls.append(("path", (created_at, key, safe_receipt)))
            return Path("/receipts/2026-07/safe-key.json")

        def write_receipt(path: Path, payload: Mapping[str, Any]) -> Path:
            calls.append(("write", (path, payload)))
            return path

        service = ReceiptService(
            ReceiptServiceContext(
                build_receipt=build_receipt,
                redact_receipt=redact_receipt,
                storage_key=storage_key,
                build_path=build_path,
                write_receipt=write_receipt,
                present_path=lambda path: f"shown:{Path(path).as_posix()}",
                build_result=lambda safe, path, redactions: {
                    "safe": safe,
                    "path": path,
                    "redactions": dict(redactions),
                },
                redact_result=lambda result: {**result, "final": True},
                now_iso=lambda: "2026-07-13T12:00:00Z",
            )
        )

        result = service.record({"packet_id": "secret-packet"})

        self.assertEqual(result["safe"]["packet_id"], "[REDACTED:id]")
        self.assertEqual(result["path"], "shown:/receipts/2026-07/safe-key.json")
        self.assertEqual(
            [name for name, _value in calls],
            ["build", "redact", "key", "path", "write"],
        )
        self.assertEqual(calls[2][1], ("secret-packet", "[REDACTED:id]"))
        self.assertNotIn("secret-packet", repr(calls[3][1]))
        self.assertNotIn("secret-packet", repr(calls[4][1]))

    def test_record_rejects_raw_benchmark_context_before_redaction_or_write(self) -> None:
        calls: list[str] = []

        def build_receipt(
            _arguments: Mapping[str, Any], _created_at: str
        ) -> dict[str, Any]:
            calls.append("build")
            return {
                "packet_id": "packet-123",
                "outcome": "passed",
                "benchmark_host_receipt": "tmcp-composition-benchmark-host-only-v0.1",
                "execution_context": {
                    "preflight_context_instance_id": "host-private-context"
                },
            }

        service = ReceiptService(
            ReceiptServiceContext(
                build_receipt=build_receipt,
                redact_receipt=lambda receipt: (
                    dict(receipt),
                    {},
                ),
                storage_key=lambda _raw, _safe: "safe-key",
                build_path=lambda _created, _key, _safe: Path("/receipts/test.json"),
                write_receipt=lambda path, _payload: path,
                present_path=lambda path: str(path),
                build_result=lambda _safe, _path, _redactions: {},
                redact_result=lambda result: result,
                now_iso=lambda: "2026-07-13T12:00:00Z",
            )
        )

        with self.assertRaisesRegex(ValueError, "Benchmark qualification fields"):
            service.record({"packet_id": "packet-123"})

        self.assertEqual(calls, ["build"])

    def test_record_rejects_claimed_benchmark_mode_before_redaction_or_write(
        self,
    ) -> None:
        calls: list[str] = []

        def build_receipt(
            _arguments: Mapping[str, Any], _created_at: str
        ) -> dict[str, Any]:
            calls.append("build")
            return {
                "packet_id": "packet-123",
                "outcome": "passed",
                "context_execution_mode": "isolated_phase_capsule",
            }

        service = ReceiptService(
            ReceiptServiceContext(
                build_receipt=build_receipt,
                redact_receipt=lambda receipt: (dict(receipt), {}),
                storage_key=lambda _raw, _safe: "safe-key",
                build_path=lambda _created, _key, _safe: Path("/receipts/test.json"),
                write_receipt=lambda path, _payload: path,
                present_path=lambda path: str(path),
                build_result=lambda _safe, _path, _redactions: {},
                redact_result=lambda result: result,
                now_iso=lambda: "2026-07-13T12:00:00Z",
            )
        )

        with self.assertRaisesRegex(ValueError, "Benchmark qualification fields"):
            service.record({"packet_id": "packet-123"})

        self.assertEqual(calls, ["build"])

    def test_record_rejects_raw_phase_capsule_context_before_redaction_or_write(
        self,
    ) -> None:
        calls: list[str] = []

        def build_receipt(
            _arguments: Mapping[str, Any], _created_at: str
        ) -> dict[str, Any]:
            calls.append("build")
            return {
                "packet_id": "packet-123",
                "outcome": "passed",
                "phase_capsule_trace": [
                    {
                        "stage_id": "stage-1",
                        "capsule_digest": "a" * 64,
                        "incoming_handoff_digests": [],
                        "context_instance_id": "host-private-context",
                    }
                ],
            }

        service = ReceiptService(
            ReceiptServiceContext(
                build_receipt=build_receipt,
                redact_receipt=lambda receipt: (dict(receipt), {}),
                storage_key=lambda _raw, _safe: "safe-key",
                build_path=lambda _created, _key, _safe: Path("/receipts/test.json"),
                write_receipt=lambda path, _payload: path,
                present_path=lambda path: str(path),
                build_result=lambda _safe, _path, _redactions: {},
                redact_result=lambda result: result,
                now_iso=lambda: "2026-07-13T12:00:00Z",
            )
        )

        with self.assertRaisesRegex(ValueError, "phase_capsule_trace"):
            service.record({"packet_id": "packet-123"})

        self.assertEqual(calls, ["build"])

    def test_service_has_no_storage_or_adapter_imports(self) -> None:
        source_path = Path(inspect.getfile(receipts_service))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_prefixes = (
            "os",
            "shutil",
            "subprocess",
            "scripts",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
        )
        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )


if __name__ == "__main__":
    unittest.main()
