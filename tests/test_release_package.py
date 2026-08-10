from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

from unittest.mock import patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ARCHIVE_PATH = PLUGIN_ROOT / "scripts" / "tmcp_release_archive.py"
CHECK_RELEASE_PACKAGE_PATH = PLUGIN_ROOT / "scripts" / "check_release_package.py"


class _ReleaseArchiveModule(Protocol):
    PACKAGE_MANIFEST_SCHEMA: str
    PACKAGE_POLICY_VERSION: str
    PACKAGE_MANIFEST_NAME: str
    ReleasePackageError: type[RuntimeError]

    def create_package(
        self, plugin_root: Path, output_path: Path
    ) -> dict[str, Any]: ...

    def check_archive_manifest(self, package_path: Path) -> tuple[bool, str]: ...

    def validate_tree_entry(
        self, path_text: str, git_mode: str, object_type: str
    ) -> None: ...

    def _validate_relative_path(self, path_text: str) -> PurePosixPath: ...

    def register_archive_path(self, seen: dict[str, str], path_text: str) -> None: ...

    def forbidden_path_reason(self, relative_path: PurePosixPath) -> str | None: ...

    def scan_release_content(self, relative_path: str, content: bytes) -> None: ...

    def validate_output_path(self, plugin_root: Path, output_path: Path) -> Path: ...


def load_release_archive_module() -> _ReleaseArchiveModule:
    spec = importlib.util.spec_from_file_location(
        "tmcp_release_archive", RELEASE_ARCHIVE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load tmcp_release_archive module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_ReleaseArchiveModule, module)


def load_release_package_check_module():
    spec = importlib.util.spec_from_file_location(
        "check_release_package", CHECK_RELEASE_PACKAGE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load check_release_package module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_git_environment(root: Path) -> dict[str, str]:
    home = root.parent / "git-home"
    home.mkdir(exist_ok=True)
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["HOME"] = str(home)
    environment["XDG_CONFIG_HOME"] = str(home / "config")
    return environment


def commit_fixture(root: Path, force_paths: tuple[str, ...] = ()) -> None:
    environment = fixture_git_environment(root)
    template = root.parent / "git-template"
    template.mkdir(exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet", f"--template={template}"],
        cwd=root,
        env=environment,
        check=True,
    )
    subprocess.run(["git", "add", "--all"], cwd=root, env=environment, check=True)
    if force_paths:
        subprocess.run(
            ["git", "add", "--force", *force_paths],
            cwd=root,
            env=environment,
            check=True,
        )
    subprocess.run(
        [
            "git",
            "-c",
            f"core.hooksPath={template}",
            "-c",
            "user.name=TMCP Test",
            "-c",
            "user.email=tmcp@example.test",
            "commit",
            "--quiet",
            "-m",
            "release package fixture",
        ],
        cwd=root,
        env=environment,
        check=True,
    )


def synthetic_secret_assignment(separator: str = "=") -> str:
    key = "api" + "_key"
    value = "not-a-real-" + "secret-123456"
    return f'{key}{separator}"{value}"\n'


def manifest_entry(
    path: str, content: bytes, git_mode: str = "100644"
) -> dict[str, object]:
    return {
        "path": path,
        "git_mode": git_mode,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def write_member(
    archive: tarfile.TarFile, name: str, content: bytes, mode: int
) -> None:
    member = tarfile.TarInfo(name)
    member.mode = mode
    member.size = len(content)
    archive.addfile(member, io.BytesIO(content))


def write_test_archive(
    package: _ReleaseArchiveModule,
    archive_path: Path,
    payloads: list[tuple[str, bytes, int]],
    entries: list[dict[str, object]],
) -> None:
    manifest = {
        "schema": package.PACKAGE_MANIFEST_SCHEMA,
        "policy_version": package.PACKAGE_POLICY_VERSION,
        "source": {"commit": "a" * 40, "tree": "b" * 40},
        "entries": entries,
        "excluded": [],
    }
    with tarfile.open(archive_path, "w:gz") as archive:
        for path, content, mode in payloads:
            write_member(archive, f"tmcp/{path}", content, mode)
        write_member(
            archive,
            f"tmcp/{package.PACKAGE_MANIFEST_NAME}",
            (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"),
            0o644,
        )


class ReleasePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = load_release_archive_module()
        cls.checker = load_release_package_check_module()

    def test_fixture_git_environment_scrubs_git_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            with patch.dict(
                os.environ,
                {
                    "GIT_DIR": "/unsafe/git-dir",
                    "GIT_WORK_TREE": "/unsafe/worktree",
                    "GIT_INDEX_FILE": "/unsafe/index",
                },
            ):
                environment = fixture_git_environment(root)

        self.assertNotIn("GIT_DIR", environment)
        self.assertNotIn("GIT_WORK_TREE", environment)
        self.assertNotIn("GIT_INDEX_FILE", environment)
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")

    def test_fixture_commits_ignore_inherited_template_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")
            hostile_template = Path(tmp) / "hostile-template" / "hooks"
            hostile_template.mkdir(parents=True)
            marker = Path(tmp) / "hook-ran"
            hook = hostile_template / "pre-commit"
            hook.write_text(
                '#!/bin/sh\ntouch "$TMCP_TEST_HOOK_MARKER"\nexit 1\n',
                encoding="utf-8",
            )
            hook.chmod(0o755)

            with patch.dict(
                os.environ,
                {
                    "GIT_TEMPLATE_DIR": str(hostile_template.parent),
                    "TMCP_TEST_HOOK_MARKER": str(marker),
                },
            ):
                commit_fixture(root)

        self.assertFalse(marker.exists())

    def test_package_uses_only_committed_allowlisted_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")
            (root / "scripts").mkdir()
            (root / "scripts" / "entry.py").write_text(
                "print('safe')\n", encoding="utf-8"
            )
            commit_fixture(root)

            (root / ".env.production").write_text(
                synthetic_secret_assignment(), encoding="utf-8"
            )
            (root / ".agents").mkdir()
            (root / ".agents" / "private.md").write_text(
                "private local state\n", encoding="utf-8"
            )
            (root / "notes.md").write_text("untracked notes\n", encoding="utf-8")
            output_path = Path(tmp) / "release.tar.gz"

            build = self.package.create_package(root, output_path)

            with tarfile.open(output_path, "r:gz") as archive:
                names = archive.getnames()
                manifest_file = archive.extractfile(
                    f"tmcp/{self.package.PACKAGE_MANIFEST_NAME}"
                )
                assert manifest_file is not None
                manifest = json.loads(manifest_file.read().decode("utf-8"))

        self.assertEqual(
            names,
            [
                "tmcp/README.md",
                "tmcp/scripts/entry.py",
                f"tmcp/{self.package.PACKAGE_MANIFEST_NAME}",
            ],
        )
        self.assertEqual(
            [entry["path"] for entry in manifest["entries"]],
            ["README.md", "scripts/entry.py"],
        )
        self.assertEqual(build["source_commit"], manifest["source"]["commit"])
        self.assertNotIn("tmcp/.env.production", names)
        self.assertNotIn("tmcp/.agents/private.md", names)
        self.assertNotIn("tmcp/notes.md", names)

    def test_package_rejects_dirty_tracked_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            readme = root / "README.md"
            readme.write_text("# Plugin\n", encoding="utf-8")
            commit_fixture(root)
            readme.write_text("# Plugin\nChanged after commit.\n", encoding="utf-8")

            with self.assertRaisesRegex(
                self.package.ReleasePackageError,
                "no staged or unstaged tracked changes",
            ):
                self.package.create_package(root, Path(tmp) / "release.tar.gz")

    def test_package_rejects_tracked_environment_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")
            (root / ".env").write_text(synthetic_secret_assignment(), encoding="utf-8")
            commit_fixture(root, force_paths=(".env",))

            with self.assertRaisesRegex(
                self.package.ReleasePackageError,
                "environment files are never releasable",
            ):
                self.package.create_package(root, Path(tmp) / "release.tar.gz")

    def test_package_rejects_tracked_secret_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text(
                synthetic_secret_assignment(" = "), encoding="utf-8"
            )
            commit_fixture(root)

            with self.assertRaisesRegex(
                self.package.ReleasePackageError,
                "detected secret-like content",
            ):
                self.package.create_package(root, Path(tmp) / "release.tar.gz")

    def test_package_rejects_symlink_git_mode_on_every_platform(self) -> None:
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "reject Git mode 120000",
        ):
            self.package.validate_tree_entry("linked.md", "120000", "blob")

    def test_package_rejects_cross_platform_path_collisions(self) -> None:
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "Windows-invalid",
        ):
            self.package._validate_relative_path("scripts/unsafe:name.py")
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "unsafe tracked path",
        ):
            self.package._validate_relative_path("scripts/control\x01.py")

        seen: dict[str, str] = {}
        self.package.register_archive_path(seen, "scripts/Foo.py")
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "archive path collision",
        ):
            self.package.register_archive_path(seen, "scripts/foo.py")

        unicode_seen: dict[str, str] = {}
        self.package.register_archive_path(unicode_seen, "docs/caf\u00e9.md")
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "archive path collision",
        ):
            self.package.register_archive_path(unicode_seen, "docs/cafe\u0301.md")

    def test_package_rejects_credential_like_path_tokens(self) -> None:
        for path in ("scripts/credentials.json", "scripts/secret-config.json"):
            with self.subTest(path=path):
                reason = self.package.forbidden_path_reason(
                    self.package._validate_relative_path(path)
                )
                self.assertIsNotNone(reason)

    def test_package_scans_fine_grained_and_high_entropy_secrets(self) -> None:
        github_token = ("github" + "_pat_") + ("Ab1_" * 12)
        raw_aws_secret = "AbCdEfGhIjKlMnOpQrSt" + "UvWxYz0123456789+/ab"
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "github_fine_grained_token",
        ):
            self.package.scan_release_content("README.md", github_token.encode())
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "long_high_entropy",
        ):
            self.package.scan_release_content("README.md", raw_aws_secret.encode())

    def test_package_allows_documented_checksum(self) -> None:
        checksum = "0123456789abcdef" * 4
        self.package.scan_release_content(
            "README.md", f"sha256 digest: {checksum}\n".encode("utf-8")
        )
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "long_high_entropy",
        ):
            self.package.scan_release_content(
                "README.md", f"hash note {checksum}\n".encode("utf-8")
            )

    def test_package_allows_path_shaped_placeholder(self) -> None:
        placeholder = "/absolute/path/to/tmcp/scripts/" + "tmcp_launcher.mjs"
        self.package.scan_release_content("README.md", placeholder.encode("utf-8"))
        relative_path = "workflows/" + "security-privacy-harvest-audit"
        self.package.scan_release_content("README.md", relative_path.encode("utf-8"))
        schema_path = "schemas/" + "tmcp-codex-validation-preflight-v0"
        self.package.scan_release_content(
            "docs/CODEX_VALIDATION_PREFLIGHT.md",
            f"See ../{schema_path}.schema.json\n".encode("utf-8"),
        )
        schema_identifier = "tmcp-invocation-admission-overhead-pilot-v0"
        self.package.scan_release_content(
            "examples/workflows/invocation-admission-overhead-pilot-v0.5.json",
            f'{{"schema": "{schema_identifier}.5"}}\n'.encode("utf-8"),
        )
        self.package.scan_release_content(
            "schemas/tmcp-behavioral-atoms-held-out-fixtures-v0.3.schema.json",
            b'  "const": "tmcp-behavioral-atoms-held-out-fixtures-v0.3"\n',
        )
        self.package.scan_release_content(
            "schemas/tmcp-behavioral-atoms-runtime-h3-decision-v0.7.schema.json",
            b'  "$id": "https://github.com/jakyeamos/tmcp/schemas/'
            b'tmcp-behavioral-atoms-runtime-h3-decision-v0.7.schema.json"\n',
        )
        self.package.scan_release_content(
            "schemas/tmcp-behavioral-atoms-runtime-h3-decision-v0.7.schema.json",
            b'  "decision_schema": {"const": '
            b'"schemas/tmcp-behavioral-atoms-runtime-h3-decision-v0.7.schema.json"}\n',
        )
        self.package.scan_release_content(
            "scripts/check_install.py",
            b'REQUIRED_FILES = (\n'
            b'    "schemas/tmcp-codex-validation-preflight-v0.1.schema.json",\n'
            b')\n',
        )
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "long_high_entropy",
        ):
            self.package.scan_release_content(
                "scripts/check_install.py",
                b'OTHER_FILES = (\n'
                b'    "schemas/tmcp-codex-validation-preflight-v0.1.schema.json",\n'
                b')\n',
            )
        self.package.scan_release_content(
            "scripts/extract_codex_rollout_metrics.py",
            b'ATTRIBUTION_AVAILABILITY_SCHEMA = (\n'
            b'    "tmcp-invocation-admission-attribution-availability-v0.11"\n'
            b')\n',
        )
        self.package.scan_release_content(
            "scripts/prepare_invocation_admission_pilot.py",
            b'        "schema": "tmcp-invocation-admission-runner-input-v0.1",\n',
        )
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "long_high_entropy",
        ):
            self.package.scan_release_content(
                "scripts/extract_codex_rollout_metrics.py",
                b'OTHER_VALUE = (\n'
                b'    "tmcp-invocation-admission-attribution-availability-v0.11"\n'
                b')\n',
            )
        self.package.scan_release_content(
            "schemas/tmcp-behavioral-atoms-runtime-h3-decision-v0.7.schema.json",
            b'  "combined_fixture_id": {"const": '
            b'"h3_combined_positive_secret_boundary_evidence_ladder"}\n',
        )
        with self.assertRaisesRegex(
            self.package.ReleasePackageError,
            "long_high_entropy",
        ):
            self.package.scan_release_content(
                "schemas/tmcp-behavioral-atoms-runtime-h3-decision-v0.7.schema.json",
                b'  "description": "tmcp-behavioral-atoms-runtime-h3-decision-v0.7"\n',
            )
        checksum = "0123456789abcdef" * 4
        self.package.scan_release_content(
            "examples/workflows/invocation-admission-overhead-pilot-v0.5.json",
            f'{{"sha256": "{checksum}"}}\n'.encode("utf-8"),
        )
        identifier = "recommended_scoped_packet_" + "seeds"
        self.package.scan_release_content("README.md", identifier.encode("utf-8"))
        assignment = identifier + "=" + identifier
        self.package.scan_release_content("README.md", assignment.encode("utf-8"))
        constant = "SEED_MATCH_THRESHOLD_WITH_" + "ROUTE_AFFINITY"
        self.package.scan_release_content("README.md", constant.encode("utf-8"))

    def test_manifest_and_archive_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")
            (root / "skills").mkdir()
            (root / "skills" / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            commit_fixture(root)
            first = Path(tmp) / "first.tar.gz"
            second = Path(tmp) / "second.tar.gz"

            self.package.create_package(root, first)
            self.package.create_package(root, second)
            manifest_ok, manifest_output = self.package.check_archive_manifest(first)
            first_digest = hashlib.sha256(first.read_bytes()).hexdigest()
            second_digest = hashlib.sha256(second.read_bytes()).hexdigest()

            with tarfile.open(first, "r:gz") as archive:
                manifest_file = archive.extractfile(
                    f"tmcp/{self.package.PACKAGE_MANIFEST_NAME}"
                )
                assert manifest_file is not None
                manifest = json.loads(manifest_file.read().decode("utf-8"))

        self.assertTrue(manifest_ok, manifest_output)
        self.assertEqual(first_digest, second_digest)
        self.assertEqual(
            [entry["path"] for entry in manifest["entries"]],
            sorted(entry["path"] for entry in manifest["entries"]),
        )

    def test_cli_reports_reproducibility_digests(self) -> None:
        checks: dict[str, object] = {
            key: "pass"
            for key in (
                "archive_manifest",
                "install_check",
                "tests",
                "compile",
                "launcher_syntax",
                "frontmatter",
                "hardcoded_user_paths",
                "private_names",
                "markdown_links",
                "doctor_surface",
                "sample_harvest",
                "sample_expert_rubric",
                "adaptive_workflow_surface",
                "composition_surface",
            )
        }
        checks["output"] = {}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")
            commit_fixture(root)
            stdout = io.StringIO()

            with (
                patch.object(self.checker, "check_package", return_value=checks),
                patch.object(
                    sys,
                    "argv",
                    [
                        "check_release_package.py",
                        str(root),
                        "--verify-reproducible",
                    ],
                ),
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = self.checker.main()

        result = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["reproducibility"], "pass")
        self.assertEqual(result["archive_digest"], result["repeat_archive_digest"])
        self.assertEqual(result["manifest_digest"], result["repeat_manifest_digest"])

    def test_package_uses_its_own_git_worktree_when_git_env_is_overridden(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            root = temp_root / "plugin"
            other_root = temp_root / "other-plugin"
            root.mkdir()
            other_root.mkdir()
            (root / "README.md").write_text("# Intended package\n", encoding="utf-8")
            (other_root / "README.md").write_text("# Other package\n", encoding="utf-8")
            (other_root / "scripts").mkdir()
            (other_root / "scripts" / "other.py").write_text(
                "print('other')\n", encoding="utf-8"
            )
            commit_fixture(root)
            commit_fixture(other_root)
            output_path = temp_root / "release.tar.gz"

            with patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(other_root / ".git"),
                    "GIT_WORK_TREE": str(other_root),
                    "GIT_INDEX_FILE": str(other_root / ".git" / "index"),
                },
            ):
                build = self.package.create_package(root, output_path)

        self.assertEqual(
            [entry["path"] for entry in build["manifest"]["entries"]],
            ["README.md"],
        )

    def test_package_refuses_to_overwrite_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            readme = root / "README.md"
            readme.write_text("# Plugin\n", encoding="utf-8")
            commit_fixture(root)
            original = readme.read_bytes()

            with self.assertRaisesRegex(
                self.package.ReleasePackageError,
                "outside the source Git worktree",
            ):
                self.package.create_package(root, readme)

            self.assertEqual(readme.read_bytes(), original)

    def test_package_refuses_symlink_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            target = Path(tmp) / "target.tar.gz"
            target.write_bytes(b"unchanged")
            output_path = Path(tmp) / "release.tar.gz"
            output_path.symlink_to(target)

            with self.assertRaisesRegex(
                self.package.ReleasePackageError,
                "must not be a symlink",
            ):
                self.package.validate_output_path(root, output_path)

            self.assertEqual(target.read_bytes(), b"unchanged")

    def test_package_replaces_external_hard_link_without_writing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            readme = root / "README.md"
            readme.write_text("# Plugin\n", encoding="utf-8")
            commit_fixture(root)
            output_path = Path(tmp) / "release.tar.gz"
            original = readme.read_bytes()
            os.link(readme, output_path)

            self.package.create_package(root, output_path)

            self.assertEqual(readme.read_bytes(), original)
            self.assertNotEqual(
                readme.stat().st_ino,
                output_path.stat().st_ino,
            )

    def test_archive_manifest_rejects_forged_unsafe_payload_before_execution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "forged.tar.gz"
            payload = synthetic_secret_assignment().encode("utf-8")
            write_test_archive(
                self.package,
                archive_path,
                [(".env", payload, 0o644)],
                [manifest_entry(".env", payload)],
            )

            valid, output = self.package.check_archive_manifest(archive_path)
            result = self.checker.check_package(archive_path)

        self.assertFalse(valid)
        self.assertIn("unsafe", output)
        self.assertEqual(result["archive_manifest"], "fail")
        self.assertEqual(result["tests"], "fail")
        self.assertNotIn("tests", result["output"])

    def test_archive_manifest_rejects_payload_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "tampered.tar.gz"
            claimed_content = b"# Expected\n"
            actual_content = b"# Tampered\n"
            write_test_archive(
                self.package,
                archive_path,
                [("README.md", actual_content, 0o644)],
                [manifest_entry("README.md", claimed_content)],
            )

            valid, output = self.package.check_archive_manifest(archive_path)

        self.assertFalse(valid)
        self.assertIn("digest mismatch", output)

    def test_archive_manifest_rejects_boolean_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "boolean-size.tar.gz"
            payload = b"x"
            entry = manifest_entry("README.md", payload)
            entry["size"] = True
            write_test_archive(
                self.package,
                archive_path,
                [("README.md", payload, 0o644)],
                [entry],
            )

            valid, output = self.package.check_archive_manifest(archive_path)

        self.assertFalse(valid)
        self.assertIn("size is invalid", output)

    def test_archive_manifest_rejects_unlisted_payload_and_duplicate_entry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            readme = b"# Plugin\n"
            entry = manifest_entry("README.md", readme)
            unlisted_archive = temp_root / "unlisted.tar.gz"
            duplicate_archive = temp_root / "duplicate.tar.gz"
            write_test_archive(
                self.package,
                unlisted_archive,
                [
                    ("README.md", readme, 0o644),
                    ("scripts/extra.py", b"print('extra')\n", 0o644),
                ],
                [entry],
            )
            write_test_archive(
                self.package,
                duplicate_archive,
                [("README.md", readme, 0o644)],
                [entry, entry],
            )

            unlisted_valid, unlisted_output = self.package.check_archive_manifest(
                unlisted_archive
            )
            duplicate_valid, duplicate_output = self.package.check_archive_manifest(
                duplicate_archive
            )

        self.assertFalse(unlisted_valid)
        self.assertIn("do not match archive payload", unlisted_output)
        self.assertFalse(duplicate_valid)
        self.assertIn("duplicates", duplicate_output)

    def test_package_excludes_local_artifact_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text("", encoding="utf-8")
            aios_audit = root / ".aios" / "audit"
            aios_audit.mkdir(parents=True)
            (aios_audit / "gate-events.jsonl").write_text("", encoding="utf-8")
            quality_run = root / ".quality-runner" / "runs" / "local"
            quality_run.mkdir(parents=True)
            (quality_run / "audit.json").write_text("{}", encoding="utf-8")
            registry = root / "mcp-registry"
            registry.mkdir()
            (registry / "draft-server.json").write_text("{}", encoding="utf-8")
            docs = root / "docs"
            docs.mkdir()
            (docs / "RELEASE_EVIDENCE.json").write_text("{}", encoding="utf-8")
            (docs / "VERIFICATION.md").write_text("# Verification\n", encoding="utf-8")
            (docs / "TIER_ONE_RELEASE_RUBRIC.md").write_text(
                "# Rubric\n", encoding="utf-8"
            )
            release_note = docs / "release-notes" / "v0.5.0-compatibility.md"
            release_note.parent.mkdir()
            release_note.write_text("# Compatibility\n", encoding="utf-8")
            output_path = Path(tmp) / "tmcp.tar.gz"

            commit_fixture(root)
            self.package.create_package(root, output_path)

            with tarfile.open(output_path, "r:gz") as archive:
                names = archive.getnames()

        self.assertIn("tmcp/README.md", names)
        self.assertNotIn("tmcp/.aios/audit/gate-events.jsonl", names)
        self.assertNotIn("tmcp/.codex/config.toml", names)
        self.assertNotIn("tmcp/.quality-runner/runs/local/audit.json", names)
        self.assertNotIn("tmcp/mcp-registry/draft-server.json", names)
        self.assertNotIn("tmcp/docs/RELEASE_EVIDENCE.json", names)
        self.assertNotIn("tmcp/docs/VERIFICATION.md", names)
        self.assertIn("tmcp/docs/TIER_ONE_RELEASE_RUBRIC.md", names)
        self.assertIn("tmcp/docs/release-notes/v0.5.0-compatibility.md", names)

    def test_release_package_check_smokes_adaptive_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok, output = self.checker.check_adaptive_workflow_surface(
                PLUGIN_ROOT, Path(tmp)
            )

        self.assertTrue(ok, output)

    def test_release_package_check_smokes_composition_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok, output = self.checker.check_composition_surface(PLUGIN_ROOT, Path(tmp))

        self.assertTrue(ok, output)

    def test_package_requires_git_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            root.mkdir()
            (root / "README.md").write_text("# Plugin\n", encoding="utf-8")

            with self.assertRaisesRegex(
                self.package.ReleasePackageError,
                "requires a Git worktree",
            ):
                self.package.create_package(root, Path(tmp) / "release.tar.gz")


if __name__ == "__main__":
    unittest.main()
