from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MANAGER = ROOT / "scripts" / "tmcp_runtime.mjs"
JsonObject = dict[str, object]


class TmcpRuntimeManagerTests(unittest.TestCase):
    def make_package(self, root: Path, version: str, marker: str) -> Path:
        package = root / f"package-{version}"
        (package / ".claude-plugin").mkdir(parents=True)
        (package / ".codex-plugin").mkdir(parents=True)
        (package / "scripts").mkdir(parents=True)
        (package / "skills" / "tmcp").mkdir(parents=True)
        (package / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "tmcp", "version": version}), encoding="utf-8"
        )
        (package / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "tmcp",
                    "version": version,
                    "plugins": [
                        {
                            "name": "tmcp",
                            "version": version,
                            "source": {
                                "source": "github",
                                "repo": "jakyeamos/tmcp",
                                "ref": f"v{version}",
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (package / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "tmcp", "version": f"{version}+codex.test"}),
            encoding="utf-8",
        )
        (package / "tmcp_runtime").mkdir()
        (package / "tmcp_runtime" / "api").mkdir()
        (package / "tmcp_runtime" / "api" / "registry.py").write_text(
            f'release = "{version}"\n', encoding="utf-8"
        )
        (package / "scripts" / "tmcp_launcher.mjs").write_text(
            f"console.log({marker!r});\n", encoding="utf-8"
        )
        (package / "skills" / "tmcp" / "SKILL.md").write_text(
            f"# TMCP {version} {marker}\n", encoding="utf-8"
        )
        return package

    def run_manager_process(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(RUNTIME_MANAGER), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def run_manager(self, *arguments: str) -> JsonObject:
        completed = self.run_manager_process(*arguments)
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"runtime manager failed\nstdout={completed.stdout}\nstderr={completed.stderr}",
        )
        return json.loads(completed.stdout)

    def test_install_activation_status_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_home = root / "runtime"
            first = self.make_package(root, "1.0.0", "first")
            second = self.make_package(root, "1.0.1", "second")

            installed = self.run_manager(
                "install",
                "--source",
                str(first),
                "--source-commit",
                "commit-first",
                "--runtime-home",
                str(runtime_home),
                "--activate",
            )
            self.assertEqual(installed["version"], "1.0.0")
            self.assertEqual(
                (runtime_home / "active").resolve(),
                (runtime_home / "versions" / "1.0.0").resolve(),
            )

            self.run_manager(
                "install",
                "--source",
                str(second),
                "--source-commit",
                "commit-second",
                "--runtime-home",
                str(runtime_home),
                "--activate",
            )
            status = self.run_manager("status", "--runtime-home", str(runtime_home))
            self.assertEqual(status["active_version"], "1.0.1")
            self.assertEqual(status["previous_version"], "1.0.0")

            diagnosis = self.run_manager(
                "doctor",
                "--runtime-home",
                str(runtime_home),
                "--expected-version",
                "1.0.1",
                "--skill-path",
                str(second / "skills" / "tmcp" / "SKILL.md"),
            )
            self.assertTrue(diagnosis["ok"])

            self.run_manager("rollback", "--runtime-home", str(runtime_home))
            rolled_back = self.run_manager(
                "status", "--runtime-home", str(runtime_home)
            )
            self.assertEqual(rolled_back["active_version"], "1.0.0")
            self.assertEqual(rolled_back["previous_version"], "1.0.1")

    def test_sync_and_skill_mismatch_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_home = root / "runtime"
            package = self.make_package(root, "1.0.0", "sync")
            self.run_manager(
                "install",
                "--source",
                str(package),
                "--source-commit",
                "commit-sync",
                "--runtime-home",
                str(runtime_home),
                "--activate",
            )
            legacy_alias = root / "plugins" / "tmcp"
            codex_cache = root / "codex-cache"
            claude_cache = root / "claude-cache"
            codex_marketplace = root / "codex-marketplace"
            claude_marketplace = root / "claude-marketplace"
            skill_copy = root / "global-skills" / "tmcp" / "SKILL.md"
            codex_config = root / "codex-config.toml"
            claude_installed_record = root / "claude-installed.json"
            codex_config.write_text(
                '[marketplaces.tmcp]\nsource = "https://github.com/jakyeamos/tmcp.git"\nref = "v1.0.0"\n',
                encoding="utf-8",
            )
            claude_installed_record.write_text(
                json.dumps(
                    {
                        "plugins": {
                            "tmcp@tmcp": [
                                {
                                    "version": "1.0.0",
                                    "installPath": str(claude_cache / "1.0.0"),
                                    "gitCommitSha": "commit-sync",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            synced = self.run_manager(
                "sync",
                "--runtime-home",
                str(runtime_home),
                "--legacy-alias",
                str(legacy_alias),
                "--codex-cache-root",
                str(codex_cache),
                "--claude-cache-root",
                str(claude_cache),
                "--codex-marketplace",
                str(codex_marketplace),
                "--claude-marketplace",
                str(claude_marketplace),
                "--skill-path",
                str(skill_copy),
                "--codex-config",
                str(codex_config),
                "--claude-installed-record",
                str(claude_installed_record),
            )
            self.assertTrue(synced["ok"])
            self.assertEqual(
                legacy_alias.resolve(), (runtime_home / "active").resolve()
            )
            self.assertTrue(skill_copy.exists())

            diagnosis = self.run_manager(
                "doctor",
                "--runtime-home",
                str(runtime_home),
                "--legacy-alias",
                str(legacy_alias),
                "--codex-plugin",
                str(codex_cache / "1.0.0+codex.test"),
                "--claude-plugin",
                str(claude_cache / "1.0.0"),
                "--codex-marketplace",
                str(codex_marketplace),
                "--claude-marketplace",
                str(claude_marketplace),
                "--codex-config",
                str(codex_config),
                "--claude-installed-record",
                str(claude_installed_record),
                "--skill-path",
                str(skill_copy),
            )
            self.assertTrue(diagnosis["ok"])

            codex_config.write_text(
                codex_config.read_text(encoding="utf-8").replace(
                    'ref = "v1.0.0"', 'ref = "main"'
                ),
                encoding="utf-8",
            )
            drifted = self.run_manager(
                "doctor",
                "--runtime-home",
                str(runtime_home),
                "--codex-config",
                str(codex_config),
            )
            self.assertFalse(drifted["ok"])
            self.assertTrue(
                any(
                    check.get("id") == "codex_config" and check.get("status") == "fail"
                    for check in cast(list[JsonObject], drifted["checks"])
                )
            )

            skill_copy.write_text("stale skill\n", encoding="utf-8")
            stale = self.run_manager(
                "doctor",
                "--runtime-home",
                str(runtime_home),
                "--skill-path",
                str(skill_copy),
            )
            self.assertFalse(stale["ok"])
            checks = cast(list[JsonObject], stale["checks"])
            self.assertTrue(
                any(
                    check.get("label") == "skill" and check.get("status") == "fail"
                    for check in checks
                )
            )

            (
                codex_cache / "1.0.0+codex.test" / "scripts" / "tmcp_launcher.mjs"
            ).write_text("stale cache\n", encoding="utf-8")
            refreshed = self.run_manager(
                "sync",
                "--runtime-home",
                str(runtime_home),
                "--codex-cache-root",
                str(codex_cache),
            )
            self.assertTrue(refreshed["ok"])
            self.assertIn(
                "console.log('sync')",
                (
                    codex_cache / "1.0.0+codex.test" / "scripts" / "tmcp_launcher.mjs"
                ).read_text(encoding="utf-8"),
            )

    def test_archive_install_requires_matching_digest(self) -> None:
        if shutil.which("tar") is None:
            self.skipTest("tar is required by the runtime manager")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_home = root / "runtime"
            package = self.make_package(root, "1.2.0", "archive")
            archive = root / "tmcp-1.2.0.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                for file_path in sorted(package.rglob("*")):
                    if file_path.is_file():
                        relative = file_path.relative_to(package).as_posix()
                        handle.add(file_path, arcname=f"tmcp/{relative}")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()

            installed = self.run_manager(
                "install",
                "--source",
                str(archive),
                "--sha256",
                digest,
                "--source-commit",
                "archive-commit",
                "--runtime-home",
                str(runtime_home),
                "--activate",
            )
            manifest = cast(JsonObject, installed["manifest"])
            self.assertEqual(manifest["source_kind"], "archive")
            self.assertEqual(manifest["source_sha256"], digest)

            rejected = self.run_manager_process(
                "install",
                "--source",
                str(archive),
                "--sha256",
                "0" * 64,
                "--runtime-home",
                str(root / "rejected-runtime"),
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("SHA-256 mismatch", rejected.stdout)

    def test_native_codex_marketplace_provenance_is_a_valid_surface(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required by the native marketplace test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_home = root / "runtime"
            package = self.make_package(root, "1.0.0", "native")
            self.run_manager(
                "install",
                "--source",
                str(package),
                "--source-commit",
                "commit-native",
                "--runtime-home",
                str(runtime_home),
                "--activate",
            )
            marketplace = root / "codex-marketplace"
            self.run_manager(
                "sync",
                "--runtime-home",
                str(runtime_home),
                "--codex-marketplace",
                str(marketplace),
            )
            marker = {
                "source_type": "git",
                "source": "https://github.com/jakyeamos/tmcp.git",
                "ref_name": "v1.0.0",
                "revision": "commit-native",
            }
            (marketplace / ".codex-marketplace-install.json").write_text(
                json.dumps(marker), encoding="utf-8"
            )
            generated_diagnosis = self.run_manager(
                "doctor",
                "--runtime-home",
                str(runtime_home),
                "--codex-marketplace",
                str(marketplace),
            )
            self.assertTrue(generated_diagnosis["ok"])
            generated_check = next(
                check
                for check in cast(list[JsonObject], generated_diagnosis["checks"])
                if check.get("label") == "codex_marketplace"
            )
            self.assertEqual(generated_check["mode"], "generated-copy")

            (marketplace / "native-only.md").write_text(
                "Codex native checkout content\n", encoding="utf-8"
            )
            git = ["git", "-C", str(marketplace)]
            subprocess.run([*git, "init", "--quiet"], check=True)
            subprocess.run([*git, "config", "user.name", "TMCP Test"], check=True)
            subprocess.run(
                [*git, "config", "user.email", "tmcp@example.invalid"], check=True
            )
            hooks = root / "hooks"
            hooks.mkdir()
            subprocess.run([*git, "config", "core.hooksPath", str(hooks)], check=True)
            subprocess.run([*git, "add", "-A"], check=True)
            subprocess.run(
                [
                    *git,
                    "-c",
                    "user.name=TMCP Test",
                    "-c",
                    "user.email=tmcp@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "native checkout",
                ],
                check=True,
            )
            diagnosis = self.run_manager(
                "doctor",
                "--runtime-home",
                str(runtime_home),
                "--codex-marketplace",
                str(marketplace),
            )
            self.assertTrue(diagnosis["ok"])
            codex_check = next(
                check
                for check in cast(list[JsonObject], diagnosis["checks"])
                if check.get("label") == "codex_marketplace"
            )
            self.assertEqual(codex_check["mode"], "native-git")

            synced = self.run_manager(
                "sync",
                "--runtime-home",
                str(runtime_home),
                "--codex-marketplace",
                str(marketplace),
            )
            self.assertTrue(synced["ok"])
            self.assertTrue((marketplace / "native-only.md").exists())

            marker["ref_name"] = "main"
            (marketplace / ".codex-marketplace-install.json").write_text(
                json.dumps(marker), encoding="utf-8"
            )
            drifted = self.run_manager_process(
                "sync",
                "--runtime-home",
                str(runtime_home),
                "--codex-marketplace",
                str(marketplace),
            )
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn(
                "native Codex marketplace provenance mismatch", drifted.stdout
            )

    def test_modern_package_rejects_unpinned_marketplace_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self.make_package(root, "1.0.0", "unpinned")
            marketplace_path = package / ".claude-plugin" / "marketplace.json"
            marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
            marketplace["plugins"][0]["source"]["ref"] = "main"
            marketplace_path.write_text(json.dumps(marketplace), encoding="utf-8")

            result = self.run_manager_process(
                "install",
                "--source",
                str(package),
                "--runtime-home",
                str(root / "runtime"),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be pinned to v1.0.0", result.stdout)

    def test_legacy_package_can_remain_unpinned_for_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = self.make_package(root, "0.5.3", "legacy")
            marketplace_path = package / ".claude-plugin" / "marketplace.json"
            marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
            marketplace["plugins"][0]["source"]["ref"] = "main"
            marketplace_path.write_text(json.dumps(marketplace), encoding="utf-8")

            installed = self.run_manager(
                "install",
                "--source",
                str(package),
                "--runtime-home",
                str(root / "runtime"),
                "--activate",
            )

            self.assertEqual(installed["version"], "0.5.3")

    def test_corrupt_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_home = Path(temporary) / "runtime"
            runtime_home.mkdir(parents=True)
            (runtime_home / "state.json").write_text("{\n", encoding="utf-8")
            result = self.run_manager_process(
                "status", "--runtime-home", str(runtime_home)
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("could not read JSON", result.stdout)


if __name__ == "__main__":
    unittest.main()
