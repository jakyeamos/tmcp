from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from scripts import bootstrap_codex_validation as bootstrap


class CodexValidationBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "codex"
        self.source.mkdir()
        (self.source / "justfile").write_text(
            "default:\n\t@echo ok\n", encoding="utf-8"
        )
        self.lock = self.root / "toolchain.json"
        self.lock.write_text(
            json.dumps(
                {
                    "schema": bootstrap.TOOLCHAIN_SCHEMA,
                    "tools": [
                        {
                            "name": "just",
                            "package": "just",
                            "executable": "just",
                            "version": "1.2.3",
                        },
                        {
                            "name": "dotslash",
                            "package": "dotslash",
                            "executable": "dotslash",
                            "version": "4.5.6",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.tool_dir = self.root / "task-tools"
        self.calls: list[tuple[list[str], Path | None]] = []

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _find_tool(self, name: str) -> str | None:
        return f"/usr/bin/{name}"

    def _disk_usage(self, _path: str | bytes | Path) -> SimpleNamespace:
        return SimpleNamespace(free=90 * bootstrap.GIB)

    def _runner(
        self, argv: list[str] | tuple[str, ...], cwd: Path | None, _env: Any
    ) -> Any:
        command = list(argv)
        self.calls.append((command, cwd))
        if len(command) >= 2 and command[1:3] == ["install", "--locked"]:
            root = Path(command[command.index("--root") + 1])
            package = command[command.index("--root") + 2]
            executable = {
                "just": "just",
                "dotslash": "dotslash",
            }[package]
            (root / "bin").mkdir(parents=True, exist_ok=True)
            (root / "bin" / executable).touch()
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        executable = Path(command[0]).name
        if command[0] == "just" and command[1:] == ["--list"]:
            return SimpleNamespace(returncode=0, stdout="default\n", stderr="")
        versions = {
            "cargo": "cargo 1.80.0",
            "bazel": "bazel 9.0.0",
            "just": "just 1.2.3",
            "dotslash": "dotslash 4.5.6",
        }
        return SimpleNamespace(
            returncode=0,
            stdout=versions.get(executable, "tool 1.0.0"),
            stderr="",
        )

    def _report(self, **overrides: Any) -> dict[str, object]:
        arguments: dict[str, Any] = {
            "source_root": self.source,
            "toolchain_path": self.lock,
            "tool_dir": self.tool_dir,
            "minimum_free_gib": 80.0,
            "external_tools": ("bazel",),
            "find_tool": self._find_tool,
            "disk_usage": self._disk_usage,
            "runner": self._runner,
        }
        arguments.update(overrides)
        return bootstrap.build_report(**arguments)

    def test_storage_is_checked_before_any_install_side_effect(self) -> None:
        report = self._report(
            disk_usage=lambda _path: SimpleNamespace(free=79 * bootstrap.GIB)
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(self.tool_dir.exists())
        self.assertFalse(any("install" in call for call, _cwd in self.calls))

    def test_missing_external_tool_blocks_before_install(self) -> None:
        report = self._report(
            find_tool=lambda name: None if name == "bazel" else f"/usr/bin/{name}"
        )

        self.assertFalse(report["ok"])
        checks = cast(dict[str, Any], report["checks"])
        self.assertEqual(checks["external_tools"]["status"], "blocked")
        self.assertFalse(self.tool_dir.exists())
        self.assertFalse(any("install" in call for call, _cwd in self.calls))

    def test_invalid_lock_blocks_without_creating_task_directory(self) -> None:
        self.lock.write_text("{}", encoding="utf-8")

        report = self._report()

        self.assertFalse(report["ok"])
        checks = cast(dict[str, Any], report["checks"])
        self.assertEqual(checks["toolchain_lock"]["status"], "blocked")
        self.assertFalse(self.tool_dir.exists())

    def test_ready_bootstrap_installs_locked_tools_and_runs_bare_smoke(self) -> None:
        report = self._report()

        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "ready")
        checks = cast(dict[str, Any], report["checks"])
        self.assertEqual(checks["installation"]["status"], "pass")
        self.assertEqual(checks["source_smoke"]["status"], "pass")
        install_calls = [call for call, _cwd in self.calls if "install" in call]
        self.assertEqual(len(install_calls), 2)
        self.assertIn(["just", "--list"], [call for call, _cwd in self.calls])
        self.assertIn(["just", "--version"], [call for call, _cwd in self.calls])
        self.assertTrue((self.tool_dir / "cargo-home").is_dir())

    def test_existing_exact_versions_are_reused(self) -> None:
        (self.tool_dir / "bin").mkdir(parents=True)
        (self.tool_dir / "bin" / "just").touch()
        (self.tool_dir / "bin" / "dotslash").touch()

        report = self._report()

        self.assertTrue(report["ok"])
        self.assertFalse(any("install" in call for call, _cwd in self.calls))

    def test_toolchain_lock_requires_safe_names_and_unique_entries(self) -> None:
        self.lock.write_text(
            json.dumps(
                {
                    "schema": bootstrap.TOOLCHAIN_SCHEMA,
                    "tools": [
                        {
                            "name": "../escape",
                            "package": "just",
                            "executable": "just",
                            "version": "1.2.3",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(ValueError):
            bootstrap.load_toolchain(self.lock)

    def test_cli_emits_bootstrap_schema_without_leaking_runner_output(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = bootstrap.main(
                [
                    "--source-root",
                    str(self.root / "missing-source"),
                    "--toolchain",
                    str(self.lock),
                    "--tool-dir",
                    str(self.tool_dir),
                    "--no-external-tools",
                    "--compact",
                ]
            )

        self.assertIn(
            '"schema":"tmcp-codex-validation-bootstrap-v0.1"', output.getvalue()
        )
        self.assertIn(exit_code, (0, 1))


if __name__ == "__main__":
    unittest.main()
