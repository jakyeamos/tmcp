from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest

from scripts import check_codex_validation_preflight as preflight


class CodexValidationPreflightTests(unittest.TestCase):
    def _report(
        self,
        *,
        free_gib: float = 90.0,
        tools: tuple[str, ...] = preflight.DEFAULT_REQUIRED_TOOLS,
        missing: frozenset[str] = frozenset(),
        version_failures: frozenset[str] = frozenset(),
        paths: tuple[Path, ...] = (Path("/build"),),
        desktop_bridge_manifest: Path | None = None,
        desktop_bridge_source: Path | None = None,
        require_desktop_bridge: bool = False,
    ) -> dict[str, Any]:
        def find_tool(name: str) -> str | None:
            return None if name in missing else f"/bin/{name}"

        def version_probe(executable: str) -> tuple[int, str, str]:
            name = executable.removeprefix("/bin/")
            if name in version_failures:
                return 1, "", "probe failed"
            return 0, f"{name} 1.2.3\nextra line", ""

        def disk_usage(_path: str | bytes | Path) -> SimpleNamespace:
            return SimpleNamespace(free=int(free_gib * preflight.GIB))

        return preflight.build_report(
            paths=paths,
            minimum_free_gib=80.0,
            required_tools=tools,
            find_tool=find_tool,
            version_probe=version_probe,
            disk_usage=disk_usage,
            desktop_bridge_manifest=desktop_bridge_manifest,
            desktop_bridge_source=desktop_bridge_source,
            require_desktop_bridge=require_desktop_bridge,
        )

    def test_ready_report_requires_tools_and_storage(self) -> None:
        report = self._report()

        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "ready")
        checks = report["checks"]
        self.assertIsInstance(checks, dict)
        self.assertEqual(checks["toolchain"]["status"], "pass")
        self.assertEqual(checks["storage"]["status"], "pass")
        self.assertEqual(checks["desktop_bridge"]["status"], "not_requested")
        self.assertEqual(report["remediation"], [])

    def test_required_desktop_bridge_blocks_without_manifest(self) -> None:
        report = self._report(require_desktop_bridge=True)

        self.assertFalse(report["ok"])
        bridge = report["checks"]["desktop_bridge"]
        self.assertEqual(bridge["status"], "blocked")
        self.assertEqual(
            bridge["reason"], "Desktop bridge build manifest was not provided"
        )

    def test_valid_desktop_bridge_manifest_passes_read_only_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "desktop-bridge"
            source.mkdir()
            manifest = root / "bridge-build.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": preflight.DESKTOP_BRIDGE_MANIFEST_SCHEMA,
                        "source_root": "desktop-bridge",
                        "protocol_method": preflight.DESKTOP_BRIDGE_SETUP_STATUS_METHOD,
                        "build_command": ["just", "build-bridge"],
                        "test_command": ["just", "test-bridge"],
                    }
                ),
                encoding="utf-8",
            )

            report = self._report(
                paths=(root,),
                desktop_bridge_manifest=manifest,
                desktop_bridge_source=source,
            )

        self.assertTrue(report["ok"])
        bridge = report["checks"]["desktop_bridge"]
        self.assertEqual(bridge["status"], "pass")
        self.assertEqual(bridge["protocol_method"], "thread/setupStatus/read")
        self.assertTrue(bridge["build_command_present"])
        self.assertTrue(bridge["test_command_present"])

    def test_desktop_bridge_source_manifest_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_source = root / "first-bridge"
            second_source = root / "second-bridge"
            first_source.mkdir()
            second_source.mkdir()
            manifest = root / "bridge-build.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": preflight.DESKTOP_BRIDGE_MANIFEST_SCHEMA,
                        "source_root": str(first_source),
                        "protocol_method": preflight.DESKTOP_BRIDGE_SETUP_STATUS_METHOD,
                        "build_command": ["just", "build-bridge"],
                        "test_command": ["just", "test-bridge"],
                    }
                ),
                encoding="utf-8",
            )

            report = self._report(
                paths=(root,),
                desktop_bridge_manifest=manifest,
                desktop_bridge_source=second_source,
            )

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["checks"]["desktop_bridge"]["reason"],
            "Desktop bridge source does not match the build manifest",
        )

    def test_desktop_bridge_manifest_requires_canonical_protocol_method(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "desktop-bridge"
            source.mkdir()
            manifest = root / "bridge-build.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": preflight.DESKTOP_BRIDGE_MANIFEST_SCHEMA,
                        "source_root": str(source),
                        "protocol_method": "thread/list",
                        "build_command": ["just", "build-bridge"],
                        "test_command": ["just", "test-bridge"],
                    }
                ),
                encoding="utf-8",
            )

            report = self._report(
                paths=(root,),
                desktop_bridge_manifest=manifest,
            )

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["checks"]["desktop_bridge"]["reason"],
            "Desktop bridge build manifest does not declare thread/setupStatus/read",
        )

    def test_desktop_bridge_manifest_rejects_unsupported_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "desktop-bridge"
            source.mkdir()
            manifest = root / "bridge-build.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": preflight.DESKTOP_BRIDGE_MANIFEST_SCHEMA,
                        "source_root": str(source),
                        "protocol_method": preflight.DESKTOP_BRIDGE_SETUP_STATUS_METHOD,
                        "build_command": ["just", "build-bridge"],
                        "test_command": ["just", "test-bridge"],
                        "secret": "must-not-be-accepted",
                    }
                ),
                encoding="utf-8",
            )

            report = self._report(
                paths=(root,),
                desktop_bridge_manifest=manifest,
            )

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["checks"]["desktop_bridge"]["reason"],
            "Desktop bridge build manifest contains unsupported fields",
        )

    def test_missing_tool_blocks_without_running_install(self) -> None:
        report = self._report(missing=frozenset({"dotslash"}))

        self.assertFalse(report["ok"])
        toolchain = report["checks"]["toolchain"]
        dotslash = next(
            item for item in toolchain["tools"] if item["name"] == "dotslash"
        )
        self.assertEqual(dotslash["status"], "blocked")
        self.assertEqual(dotslash["reason"], "executable not found")
        self.assertIn("cargo install --locked dotslash", report["remediation"])

    def test_failed_version_probe_blocks_even_when_executable_exists(self) -> None:
        report = self._report(version_failures=frozenset({"just"}))

        self.assertFalse(report["ok"])
        just = next(
            item
            for item in report["checks"]["toolchain"]["tools"]
            if item["name"] == "just"
        )
        self.assertEqual(just["status"], "blocked")
        self.assertEqual(just["reason"], "--version probe failed")

    def test_storage_below_floor_blocks_without_remediation_side_effects(self) -> None:
        report = self._report(free_gib=79.99)

        self.assertFalse(report["ok"])
        storage = report["checks"]["storage"]
        self.assertEqual(storage["status"], "blocked")
        filesystem = storage["filesystems"][0]
        self.assertEqual(
            filesystem["reason"], "free space is below the configured floor"
        )
        self.assertIn("do not bypass the storage guard", filesystem["remediation"])

    def test_storage_inspection_failure_is_blocked(self) -> None:
        def disk_usage(_path: str | bytes | Path) -> SimpleNamespace:
            raise OSError("private diagnostic detail")

        report: dict[str, Any] = preflight.build_report(
            paths=(Path("/missing"),),
            required_tools=(),
            find_tool=lambda _name: None,
            disk_usage=disk_usage,
        )

        self.assertFalse(report["ok"])
        filesystem = report["checks"]["storage"]["filesystems"][0]
        self.assertEqual(
            filesystem["reason"], "filesystem usage could not be inspected"
        )
        self.assertNotIn("private diagnostic detail", json.dumps(report))

    def test_duplicate_tools_are_deduplicated_in_report(self) -> None:
        report = self._report(tools=("just", "just", "dotslash"))

        toolchain = report["checks"]["toolchain"]
        self.assertEqual(toolchain["required_tools"], ["just", "dotslash"])
        self.assertEqual(
            [item["name"] for item in toolchain["tools"]], ["just", "dotslash"]
        )

    def test_empty_paths_blocks_the_storage_check(self) -> None:
        report = self._report(paths=())

        self.assertFalse(report["ok"])
        self.assertEqual(report["checks"]["storage"]["status"], "blocked")
        self.assertEqual(report["checks"]["storage"]["filesystems"], [])
        self.assertTrue(
            any(
                "Pass an existing filesystem path" in item
                for item in report["remediation"]
            )
        )

    def test_cli_parser_rejects_non_positive_storage_floor(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                preflight.build_parser().parse_args(["--min-free-gib", "0"])

        self.assertEqual(raised.exception.code, 2)

    def test_schema_and_cli_output_shape_are_machine_readable(self) -> None:
        schema_path = (
            Path(__file__).parents[1]
            / "schemas"
            / ("tmcp-codex-validation-preflight-v0.1.schema.json")
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$defs"]["toolchain"]["type"], "object")
        self.assertIn("desktop_bridge", schema["properties"]["checks"]["properties"])

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = preflight.main(
                [
                    "--tool",
                    "just",
                    "--path",
                    "/build",
                    "--min-free-gib",
                    "1",
                    "--compact",
                ]
            )
        self.assertIn(
            '"schema":"tmcp-codex-validation-preflight-v0.1"', output.getvalue()
        )
        self.assertIn(exit_code, (0, 1))


if __name__ == "__main__":
    unittest.main()
