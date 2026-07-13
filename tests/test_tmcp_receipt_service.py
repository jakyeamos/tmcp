from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from typing import Any

import tmcp_runtime.services.receipts as receipts_service
from tmcp_runtime.services.receipts import ReceiptService, ReceiptServiceContext


class ReceiptServiceTests(unittest.TestCase):
    def test_record_redacts_before_building_storage_path_and_writing(self) -> None:
        calls: list[tuple[str, object]] = []

        def build_receipt(arguments: dict[str, Any], created_at: str) -> dict[str, Any]:
            calls.append(("build", (arguments, created_at)))
            return {"packet_id": arguments["packet_id"], "outcome": "passed"}

        def redact_receipt(
            receipt: dict[str, Any],
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
            safe_receipt: dict[str, Any],
        ) -> Path:
            calls.append(("path", (created_at, key, safe_receipt)))
            return Path("/receipts/2026-07/safe-key.json")

        def write_receipt(path: Path, payload: dict[str, Any]) -> Path:
            calls.append(("write", (path, payload)))
            return path

        service = ReceiptService(
            ReceiptServiceContext(
                build_receipt=build_receipt,
                redact_receipt=redact_receipt,
                storage_key=storage_key,
                build_path=build_path,
                write_receipt=write_receipt,
                present_path=lambda path: f"shown:{path}",
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
