#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tmcp_redaction import SECRET_PATTERNS, looks_high_entropy  # noqa: E402


PACKAGE_ROOT = "tmcp"
PACKAGE_MANIFEST_NAME = "RELEASE_MANIFEST.json"
PACKAGE_MANIFEST_SCHEMA = "tmcp-release-manifest-v0.1"
PACKAGE_POLICY_VERSION = "tmcp-release-package-policy-v0.2"
ALLOWED_GIT_MODES = {"100644", "100755"}
SHIPPED_ROOT_FILES = {
    ".gitignore",
    ".mcp.json",
    ".pre-cr.json",
    ".quality-gate-exceptions",
    ".zenodo.json",
    "CHANGELOG.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "RESEARCH_READY.md",
    "SECURITY.md",
    "marketplace.example.json",
    "pyrightconfig.json",
}
SHIPPED_PREFIXES = (
    ".claude-plugin/",
    ".codex-plugin/",
    "assets/",
    "examples/",
    "schemas/",
    "scripts/",
    "skills/",
    "tests/",
    "tmcp_runtime/",
)
SHIPPED_DOC_PATHS = {
    "docs/ADAPTIVE_PACKET_RUNTIME.md",
    "docs/CLAUDE_CODE.md",
    "docs/CLAUDE_DESKTOP.md",
    "docs/CLI.md",
    "docs/COMPATIBILITY.md",
    "docs/CENTRAL_RUNTIME.md",
    "docs/DISTRIBUTION.md",
    "docs/INSTALL.md",
    "docs/MARKETPLACE_MATRIX.md",
    "docs/PACKET_STABILITY.md",
    "docs/QUICKSTART.md",
    "docs/RELEASE_CHECKLIST.md",
    "docs/SKILL_PATTERN_CATALOG.json",
    "docs/SKILL_WRITING_GUIDEBOOK.md",
    "docs/TIER_ONE_RELEASE_RUBRIC.md",
    "docs/TMCP_PACKET_SPEC.md",
    "docs/release-notes/v0.5.0-compatibility.md",
    "docs/release-notes/v0.5.1-central-runtime.md",
    "docs/release-notes/v0.5.2-archive-install.md",
    "docs/release-notes/v0.5.3-launcher-symlink.md",
    "docs/release-notes/v0.3.3-doi.md",
}
INTENTIONALLY_EXCLUDED_PATHS = {
    "docs/RELEASE_EVIDENCE.json",
    "docs/VERIFICATION.md",
}
INTENTIONALLY_EXCLUDED_PREFIXES = (
    ".aios/",
    ".codex/",
    ".github/",
    ".mypy_cache/",
    ".planning/",
    ".pre-cr/",
    ".pytest_cache/",
    ".quality-runner/",
    ".ruff_cache/",
    ".tmcp/",
    "docs/ideas/",
    "docs/modernization/",
    "mcp-registry/",
)
FORBIDDEN_PATH_PARTS = {
    ".agents",
    ".aws",
    ".cache",
    ".config",
    ".docker",
    ".git",
    ".gnupg",
    ".local",
    ".npm",
    ".nvm",
    ".pnpm-store",
    ".tox",
    ".turbo",
    ".venv",
    "application support",
    "build",
    "coverage",
    "credential",
    "credentials",
    "dist",
    "keychains",
    "keys",
    "library",
    "node_modules",
    "private",
    "profiles",
    "secret",
    "secrets",
    "target",
    "token",
    "tokens",
    "vendor",
    "venv",
}
FORBIDDEN_FILE_NAMES = {
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
FORBIDDEN_PATH_NAME_TOKENS = {
    "credential",
    "credentials",
    "key",
    "keys",
    "private",
    "secret",
    "secrets",
    "token",
    "tokens",
}
FORBIDDEN_SUFFIXES = {
    ".der",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".pyo",
    ".zip",
    ".tar",
    ".gz",
}
WINDOWS_RESERVED_NAMES = {
    "AUX",
    "CLOCK$",
    "CON",
    "NUL",
    "PRN",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
PACKAGE_SECRET_PATTERNS = SECRET_PATTERNS


class ReleasePackageError(RuntimeError):
    pass


class PackageEntry:
    def __init__(
        self, *, relative_path: str, object_id: str, git_mode: str, data: bytes
    ) -> None:
        self.relative_path = relative_path
        self.object_id = object_id
        self.git_mode = git_mode
        self.data = data


def _path_text(relative_path: Path) -> str:
    return relative_path.as_posix()


def _validate_relative_path(path_text: str) -> PurePosixPath:
    if (
        not path_text
        or path_text.startswith(("/", "\\"))
        or "\\" in path_text
        or any(ord(character) < 32 or ord(character) == 127 for character in path_text)
    ):
        raise ReleasePackageError(f"unsafe tracked path: {path_text!r}")
    path = PurePosixPath(path_text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleasePackageError(f"unsafe tracked path: {path_text!r}")
    for part in path.parts:
        if any(character in part for character in '<>:"|?*'):
            raise ReleasePackageError(
                f"unsafe Windows-invalid tracked path component: {path_text!r}"
            )
        if part.endswith((" ", ".")):
            raise ReleasePackageError(f"unsafe tracked path component: {path_text!r}")
        stem = part.split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            raise ReleasePackageError(
                f"unsafe Windows-reserved tracked path component: {path_text!r}"
            )
    return path


def archive_path_key(path_text: str) -> str:
    """Return a cross-platform identity suitable for archive collision checks."""
    return unicodedata.normalize("NFC", path_text).casefold()


def register_archive_path(seen: dict[str, str], path_text: str) -> None:
    key = archive_path_key(path_text)
    existing = seen.get(key)
    if existing is not None:
        raise ReleasePackageError(
            f"archive path collision between {existing!r} and {path_text!r}"
        )
    seen[key] = path_text


def forbidden_path_reason(relative_path: PurePosixPath) -> str | None:
    for part in relative_path.parts:
        lower_part = part.lower()
        if lower_part in FORBIDDEN_PATH_PARTS:
            return f"forbidden path component {part!r}"
        if lower_part == ".env" or lower_part.startswith(".env."):
            return "environment files are never releasable"
        if lower_part in FORBIDDEN_FILE_NAMES:
            return f"forbidden credential filename {part!r}"
        tokens = {token for token in re.split(r"[-_.\s]+", lower_part) if token}
        forbidden_tokens = sorted(tokens & FORBIDDEN_PATH_NAME_TOKENS)
        if forbidden_tokens:
            return (
                f"forbidden credential-like path token "
                f"{forbidden_tokens[0]!r} in {part!r}"
            )
    suffix = relative_path.suffix.lower()
    if suffix in FORBIDDEN_SUFFIXES:
        return f"forbidden file suffix {suffix!r}"
    return None


def inclusion_reason(relative_path: PurePosixPath) -> str | None:
    path_text = relative_path.as_posix()
    if path_text in INTENTIONALLY_EXCLUDED_PATHS:
        return "release evidence is external to the immutable package"
    if path_text.startswith(INTENTIONALLY_EXCLUDED_PREFIXES):
        return "outside the reviewed release surface"
    if path_text in SHIPPED_ROOT_FILES:
        return None
    if path_text in SHIPPED_DOC_PATHS:
        return None
    if path_text.startswith(SHIPPED_PREFIXES):
        return None
    return "not in the reviewed release allowlist"


def should_include(path: Path) -> bool:
    path_text = _path_text(path)
    try:
        relative_path = _validate_relative_path(path_text)
    except ReleasePackageError:
        return False
    return (
        forbidden_path_reason(relative_path) is None
        and inclusion_reason(relative_path) is None
    )


def normalized_tarinfo(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
    tarinfo.uid = 0
    tarinfo.gid = 0
    tarinfo.uname = ""
    tarinfo.gname = ""
    tarinfo.mtime = 0
    return tarinfo


def run_git(plugin_root: Path, args: list[str]) -> bytes:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    completed = subprocess.run(
        ["git", "-C", str(plugin_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ReleasePackageError(
            f"release packaging requires a Git worktree: {message or 'git command failed'}"
        )
    return completed.stdout


def require_clean_git_worktree(plugin_root: Path) -> None:
    canonical_root = plugin_root.resolve()
    git_root = Path(
        run_git(plugin_root, ["rev-parse", "--show-toplevel"])
        .decode("utf-8", errors="replace")
        .strip()
    ).resolve()
    if git_root != canonical_root:
        raise ReleasePackageError(
            "release packaging must run from the Git worktree root"
        )
    status = run_git(
        plugin_root,
        ["status", "--porcelain=v1", "--untracked-files=no"],
    ).decode("utf-8", errors="replace")
    if status.strip():
        raise ReleasePackageError(
            "release packaging requires no staged or unstaged tracked changes"
        )


def read_git_blob(plugin_root: Path, object_id: str) -> bytes:
    return run_git(plugin_root, ["cat-file", "blob", object_id])


def is_documented_checksum(text: str, match: re.Match[str]) -> bool:
    value = match.group(0)
    if len(value) not in {40, 64, 96, 128} or not re.fullmatch(r"[A-Fa-f0-9]+", value):
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    prefix = text[line_start : match.start()]
    return (
        re.search(
            r"\b(?:sha-?(?:1|224|256|384|512)?|checksum|digest)\b"
            r"(?:\s+(?:hash|digest))?\s*[:=]\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        is not None
    )


def scan_release_content(relative_path: str, content: bytes) -> None:
    text = content.decode("utf-8", errors="replace")
    for label, pattern in PACKAGE_SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if label == "long_high_entropy" and (
                not looks_high_entropy(match.group(0))
                or is_documented_checksum(text, match)
            ):
                continue
            raise ReleasePackageError(
                f"{relative_path}: detected secret-like content ({label})"
            )


def validate_tree_entry(path_text: str, git_mode: str, object_type: str) -> None:
    if object_type != "blob" or git_mode not in ALLOWED_GIT_MODES:
        raise ReleasePackageError(
            f"{path_text}: release packages reject Git mode {git_mode} ({object_type})"
        )


def release_package_plan(
    plugin_root: Path,
) -> tuple[str, str, list[PackageEntry], list[dict[str, str]]]:
    require_clean_git_worktree(plugin_root)
    commit = (
        run_git(plugin_root, ["rev-parse", "--verify", "HEAD"]).decode("ascii").strip()
    )
    tree = (
        run_git(plugin_root, ["rev-parse", "--verify", "HEAD^{tree}"])
        .decode("ascii")
        .strip()
    )
    raw_entries = run_git(plugin_root, ["ls-tree", "-r", "-z", tree])
    package_entries: list[PackageEntry] = []
    exclusions: list[dict[str, str]] = []
    seen_paths: dict[str, str] = {}

    for raw_entry in raw_entries.split(b"\0"):
        if not raw_entry:
            continue
        try:
            metadata, raw_path = raw_entry.split(b"\t", 1)
            git_mode, object_type, object_id = metadata.decode("ascii").split(" ")
            path_text = os.fsdecode(raw_path)
        except ValueError as exc:
            raise ReleasePackageError("malformed Git tree entry") from exc
        relative_path = _validate_relative_path(path_text)
        register_archive_path(seen_paths, path_text)
        forbidden_reason = forbidden_path_reason(relative_path)
        if forbidden_reason is not None:
            raise ReleasePackageError(f"{path_text}: {forbidden_reason}")
        validate_tree_entry(path_text, git_mode, object_type)
        exclusion_reason = inclusion_reason(relative_path)
        if exclusion_reason is not None:
            exclusions.append({"path": path_text, "reason": exclusion_reason})
            continue
        content = read_git_blob(plugin_root, object_id)
        scan_release_content(path_text, content)
        package_entries.append(
            PackageEntry(
                relative_path=path_text,
                object_id=object_id,
                git_mode=git_mode,
                data=content,
            )
        )

    if not package_entries:
        raise ReleasePackageError("release package allowlist selected no files")
    return commit, tree, package_entries, exclusions


def release_manifest(
    *,
    commit: str,
    tree: str,
    entries: list[PackageEntry],
    exclusions: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema": PACKAGE_MANIFEST_SCHEMA,
        "policy_version": PACKAGE_POLICY_VERSION,
        "source": {"commit": commit, "tree": tree},
        "entries": [
            {
                "path": entry.relative_path,
                "git_mode": entry.git_mode,
                "size": len(entry.data),
                "sha256": hashlib.sha256(entry.data).hexdigest(),
            }
            for entry in entries
        ],
        "excluded": exclusions,
    }


def add_archive_bytes(
    archive: tarfile.TarFile, *, name: str, content: bytes, mode: int
) -> None:
    tarinfo = tarfile.TarInfo(name)
    tarinfo.mode = mode
    tarinfo.size = len(content)
    archive.addfile(normalized_tarinfo(tarinfo), io.BytesIO(content))


def validate_output_path(plugin_root: Path, output_path: Path) -> Path:
    canonical_root = plugin_root.resolve()
    requested_output = output_path.expanduser()
    if not requested_output.is_absolute():
        requested_output = Path.cwd() / requested_output
    canonical_output = requested_output.parent.resolve() / requested_output.name
    if canonical_output.is_symlink():
        raise ReleasePackageError("release package output must not be a symlink")
    try:
        canonical_output.relative_to(canonical_root)
    except ValueError:
        return canonical_output
    raise ReleasePackageError(
        "release package output must be outside the source Git worktree"
    )


def write_release_archive(
    output_path: Path, entries: list[PackageEntry], manifest_bytes: bytes
) -> None:
    with output_path.open("wb") as raw_output:
        with gzip.GzipFile(
            filename="", fileobj=raw_output, mode="wb", mtime=0
        ) as gzip_output:
            with tarfile.open(fileobj=gzip_output, mode="w") as archive:
                for entry in entries:
                    add_archive_bytes(
                        archive,
                        name=f"{PACKAGE_ROOT}/{entry.relative_path}",
                        content=entry.data,
                        mode=int(entry.git_mode[-3:], 8),
                    )
                add_archive_bytes(
                    archive,
                    name=f"{PACKAGE_ROOT}/{PACKAGE_MANIFEST_NAME}",
                    content=manifest_bytes,
                    mode=0o644,
                )


def create_package(plugin_root: Path, output_path: Path) -> dict[str, Any]:
    output_path = validate_output_path(plugin_root, output_path)
    commit, tree, entries, exclusions = release_package_plan(plugin_root)
    manifest = release_manifest(
        commit=commit,
        tree=tree,
        entries=entries,
        exclusions=exclusions,
    )
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    archive_digest = ""
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        write_release_archive(temporary_path, entries, manifest_bytes)
        archive_digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
    return {
        "source_commit": commit,
        "source_tree": tree,
        "archive_digest": archive_digest,
        "manifest_digest": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_path": f"{PACKAGE_ROOT}/{PACKAGE_MANIFEST_NAME}",
        "manifest": manifest,
    }


def verify_reproducibility(
    plugin_root: Path, first_build: dict[str, Any]
) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="tmcp-package-reproducibility-") as tmp:
        second_path = Path(tmp) / "tmcp-release-second.tar.gz"
        second_build = create_package(plugin_root, second_path)
    if second_build["source_commit"] != first_build["source_commit"]:
        return {
            "status": "fail",
            "message": "repeat package used a different source commit",
        }
    if second_build["source_tree"] != first_build["source_tree"]:
        return {
            "status": "fail",
            "message": "repeat package used a different source tree",
        }
    if second_build["archive_digest"] != first_build["archive_digest"]:
        return {
            "status": "fail",
            "message": "repeat package archive digest differs",
            "repeat_archive_digest": second_build["archive_digest"],
            "repeat_manifest_digest": second_build["manifest_digest"],
        }
    if second_build["manifest_digest"] != first_build["manifest_digest"]:
        return {
            "status": "fail",
            "message": "repeat package manifest digest differs",
            "repeat_archive_digest": second_build["archive_digest"],
            "repeat_manifest_digest": second_build["manifest_digest"],
        }
    return {
        "status": "pass",
        "message": "repeat package digest and manifest matched",
        "repeat_archive_digest": second_build["archive_digest"],
        "repeat_manifest_digest": second_build["manifest_digest"],
    }


def safe_extractall(archive: tarfile.TarFile, target: Path) -> None:
    target_root = target.resolve()
    for member in archive.getmembers():
        member_path = (target / member.name).resolve()
        if member_path != target_root and target_root not in member_path.parents:
            raise ValueError(f"Unsafe tar path: {member.name}")
        if member.issym() or member.islnk():
            raise ValueError(f"Refusing link in tar package: {member.name}")
    try:
        archive.extractall(target, filter="data")
    except TypeError:
        archive.extractall(target)


def check_archive_manifest(package_path: Path) -> tuple[bool, str]:
    try:
        with tarfile.open(package_path, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                return False, "archive contains duplicate member paths"
            manifest_name = f"{PACKAGE_ROOT}/{PACKAGE_MANIFEST_NAME}"
            if manifest_name not in names:
                return False, f"archive is missing {manifest_name}"
            if any(
                not member.isfile() or not member.name.startswith(f"{PACKAGE_ROOT}/")
                for member in members
            ):
                return (
                    False,
                    "archive contains unexpected non-file or non-package member",
                )
            manifest_member = archive.getmember(manifest_name)
            if manifest_member.mode & 0o777 != 0o644:
                return False, "release manifest mode must be 0644"
            manifest_stream = archive.extractfile(manifest_member)
            if manifest_stream is None:
                return False, "could not read release manifest"
            manifest = json.loads(manifest_stream.read().decode("utf-8"))
            if not isinstance(manifest, dict):
                return False, "release manifest must be an object"
            expected_manifest_fields = {
                "schema",
                "policy_version",
                "source",
                "entries",
                "excluded",
            }
            if set(manifest) != expected_manifest_fields:
                return False, "release manifest has unexpected fields"
            if manifest.get("schema") != PACKAGE_MANIFEST_SCHEMA:
                return False, "release manifest schema mismatch"
            if manifest.get("policy_version") != PACKAGE_POLICY_VERSION:
                return False, "release manifest policy version mismatch"
            source = manifest.get("source")
            if (
                not isinstance(source, dict)
                or set(source) != {"commit", "tree"}
                or not all(
                    isinstance(source.get(key), str)
                    and re.fullmatch(r"[0-9a-f]{40,64}", source[key])
                    for key in ("commit", "tree")
                )
            ):
                return False, "release manifest source is invalid"
            raw_exclusions = manifest.get("excluded")
            if not isinstance(raw_exclusions, list):
                return False, "release manifest excluded entries must be a list"
            exclusion_paths: dict[str, str] = {}
            for raw_exclusion in raw_exclusions:
                if not isinstance(raw_exclusion, dict) or set(raw_exclusion) != {
                    "path",
                    "reason",
                }:
                    return False, "release manifest exclusion is invalid"
                path = raw_exclusion.get("path")
                reason = raw_exclusion.get("reason")
                if not isinstance(path, str) or not isinstance(reason, str):
                    return False, "release manifest exclusion fields must be strings"
                relative_path = _validate_relative_path(path)
                if forbidden_path_reason(relative_path) is not None:
                    return False, f"release manifest exclusion is unsafe: {path}"
                if inclusion_reason(relative_path) != reason:
                    return False, f"release manifest exclusion is invalid: {path}"
                register_archive_path(exclusion_paths, path)
            raw_entries = manifest.get("entries")
            if not isinstance(raw_entries, list):
                return False, "release manifest entries must be a list"

            expected: dict[str, dict[str, Any]] = {}
            expected_paths: dict[str, str] = {}
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict) or set(raw_entry) != {
                    "path",
                    "git_mode",
                    "size",
                    "sha256",
                }:
                    return False, "release manifest contains a non-object entry"
                path = raw_entry.get("path")
                if not isinstance(path, str):
                    return False, "release manifest entry path must be a string"
                if path in expected:
                    return False, f"release manifest duplicates {path}"
                relative_path = _validate_relative_path(path)
                register_archive_path(expected_paths, path)
                forbidden_reason = forbidden_path_reason(relative_path)
                if forbidden_reason is not None:
                    return False, f"release manifest entry is unsafe: {path}"
                if inclusion_reason(relative_path) is not None:
                    return (
                        False,
                        f"release manifest entry is outside the allowlist: {path}",
                    )
                git_mode = raw_entry.get("git_mode")
                if not isinstance(git_mode, str) or git_mode not in ALLOWED_GIT_MODES:
                    return False, f"release manifest mode is invalid for {path}"
                size = raw_entry.get("size")
                if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                    return False, f"release manifest size is invalid for {path}"
                digest = raw_entry.get("sha256")
                if not isinstance(digest, str) or not re.fullmatch(
                    r"[0-9a-f]{64}", digest
                ):
                    return False, f"release manifest digest is invalid for {path}"
                expected[path] = raw_entry

            payload_paths: dict[str, tarfile.TarInfo] = {}
            payload_seen: dict[str, str] = {}
            for member in members:
                if member.name == manifest_name:
                    continue
                path = member.name.removeprefix(f"{PACKAGE_ROOT}/")
                relative_path = _validate_relative_path(path)
                register_archive_path(payload_seen, path)
                forbidden_reason = forbidden_path_reason(relative_path)
                if forbidden_reason is not None:
                    return False, f"archive payload is unsafe: {path}"
                if inclusion_reason(relative_path) is not None:
                    return False, f"archive payload is outside the allowlist: {path}"
                payload_paths[path] = member
            if set(expected) != set(payload_paths):
                return False, "release manifest entries do not match archive payload"

            for path, entry in expected.items():
                member = payload_paths[path]
                stream = archive.extractfile(member)
                if stream is None:
                    return False, f"could not read archive payload {path}"
                content = stream.read()
                scan_release_content(path, content)
                if entry.get("size") != len(content):
                    return False, f"release manifest size mismatch for {path}"
                if entry.get("sha256") != hashlib.sha256(content).hexdigest():
                    return False, f"release manifest digest mismatch for {path}"
                git_mode = entry.get("git_mode")
                if (
                    not isinstance(git_mode, str)
                    or git_mode not in ALLOWED_GIT_MODES
                    or member.mode & 0o777 != int(git_mode[-3:], 8)
                ):
                    return False, f"release manifest mode mismatch for {path}"
    except (
        OSError,
        ReleasePackageError,
        tarfile.TarError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        return False, f"could not validate release manifest: {exc}"
    return True, f"validated release manifest with {len(expected)} payload files"
