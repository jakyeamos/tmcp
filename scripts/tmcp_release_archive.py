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
    "docs/CODEX_VALIDATION_PREFLIGHT.md",
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
    "docs/release-notes/v0.5.4-runtime-provenance.md",
    "docs/release-notes/v0.5.5-native-marketplace.md",
    "docs/release-notes/v0.5.6-native-git-inference.md",
    "docs/release-notes/v0.5.7-risk-fixes.md",
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
DOCUMENTED_PATH_PREFIXES = (
    "docs/",
    "schemas/",
    "scripts/",
    "skills/",
    "examples/",
    "tests/",
)
DOCUMENTED_SCHEMA_PATH_PATTERN = r"(?:docs|schemas|scripts|skills|examples|tests)/"


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
            r"[\"']?\b(?:sha-?(?:1|224|256|384|512)?|checksum|digest)\b[\"']?"
            r"(?:\s+(?:hash|digest))?\s*[:=]\s*[\"']?\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        is not None
    )


def is_documented_repository_path(relative_path: str, match: re.Match[str]) -> bool:
    """Allow known repository paths in Markdown without weakening token scans."""

    if not relative_path.lower().endswith((".md", ".markdown")):
        return False
    value = match.group(0)
    return value.startswith(DOCUMENTED_PATH_PREFIXES)


def is_documented_manifest_path(
    relative_path: str, text: str, match: re.Match[str]
) -> bool:
    """Allow required-file paths in the install manifest's source tuple."""

    if relative_path != "scripts/check_install.py":
        return False
    block_start = text.rfind("REQUIRED_FILES = (", 0, match.start())
    block_end = text.find("\n)\n", block_start)
    if block_start == -1 or block_end == -1 or match.start() > block_end:
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    return re.fullmatch(
        rf"\s*[\"']{DOCUMENTED_SCHEMA_PATH_PATTERN}[A-Za-z0-9_.-]+"
        rf"(?:/[A-Za-z0-9_.-]+)*[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ) is not None


def is_documented_python_schema_constant(
    relative_path: str, text: str, match: re.Match[str]
) -> bool:
    """Allow a versioned schema identifier in a Python schema constant."""

    if not relative_path.lower().endswith(".py"):
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    previous_line_end = line_start - 1
    previous_line_start = text.rfind("\n", 0, previous_line_end) + 1
    previous_line = text[previous_line_start:previous_line_end]
    if re.fullmatch(
        r"\s*[\"']schema[\"']\s*:\s*[\"']tmcp-[A-Za-z0-9_.-]+"
        r"[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if re.fullmatch(
        r"\s*[A-Z][A-Z0-9_]*_SCHEMA\s*=\s*[\"']tmcp-[A-Za-z0-9_.-]+"
        r"[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if re.search(
        r"\.get\([\"']schema[\"']\)\s*(?:==|!=)\s*"
        r"[\"']tmcp-[A-Za-z0-9_.-]+[\"']",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    schema_set_start = text.rfind(
        'manifest.get("schema") not in {', 0, match.start()
    )
    if schema_set_start != -1:
        closing = re.search(
            r"\n[ \t]*\}\s*\n", text[schema_set_start:]
        )
        if closing is not None and match.start() < schema_set_start + closing.start():
            return True
    return (
        re.fullmatch(
            r"\s*[\"']tmcp-[A-Za-z0-9_.-]+[\"']\s*,?\s*",
            line,
            flags=re.IGNORECASE,
        )
        is not None
        and re.fullmatch(
            r"\s*(?:[A-Z][A-Z0-9_]*_SCHEMA\s*=\s*\(|"
            r"(?:if\s+)?manifest\.get\([\"']schema[\"']\)\s+not\s+in\s+\{)\s*",
            previous_line,
            flags=re.IGNORECASE,
        )
        is not None
    )


def is_documented_skill_fixture_path(
    relative_path: str, text: str, match: re.Match[str]
) -> bool:
    """Allow deterministic fixture PATH examples in the published case file."""

    if relative_path != "tests/fixtures/skill-fixtures/individual-skill-admission-cases-v0.1.json":
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    return (
        '"prompt": "' in line
        and re.fullmatch(
            r"PATH=/private/tmp/tmcp-skill-fixtures-[0-9]{8}/"
            r"tests/fixtures/skill-fixtures/[a-z0-9-]+-v0",
            match.group(0),
            flags=re.IGNORECASE,
        )
        is not None
    )


def is_documented_schema_identifier(
    relative_path: str, text: str, match: re.Match[str]
) -> bool:
    """Allow stable schema references without weakening token scans."""

    if not relative_path.lower().endswith(".json"):
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    value = match.group(0)
    if value.startswith("tmcp-") and re.search(
        r"[\"'](?:schema|const)[\"']\s*:\s*[\"']$",
        text[line_start : match.start()],
        flags=re.IGNORECASE,
    ):
        return True
    if re.fullmatch(
        r"\s*[\"']\$id[\"']\s*:\s*[\"']https://github\.com/"
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/schemas/tmcp-[A-Za-z0-9_.-]+\.json"
        r"[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if re.fullmatch(
        rf"\s*[\"']path[\"']\s*:\s*[\"']{DOCUMENTED_SCHEMA_PATH_PATTERN}"
        rf"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if re.fullmatch(
        r"\s*[\"'][A-Za-z0-9_.-]+[\"']\s*:\s*\{\s*"
        r"[\"']const[\"']\s*:\s*[\"']"
        rf"{DOCUMENTED_SCHEMA_PATH_PATTERN}[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
        r"[\"']\s*\}\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if relative_path == "tests/fixtures/behavioral-atoms-runtime-h3-v0.7.json" and re.fullmatch(
        r"\s*[\"']id[\"']\s*:\s*[\"']h3_[a-z0-9_]+[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    return re.fullmatch(
        r"\s*[\"']combined_fixture_id[\"']\s*:\s*\{\s*"
        r"[\"']const[\"']\s*:\s*[\"']"
        r"h3_combined_(?:positive|negative)_[a-z0-9_]+[\"']\s*\}\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ) is not None


def is_documented_behavioral_atoms_test_evidence(
    relative_path: str, text: str, match: re.Match[str]
) -> bool:
    """Allow immutable schema and evidence assertions in the replay-bound test."""

    if relative_path != "tests/test_tmcp_behavioral_atoms_preflight.py":
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    if re.fullmatch(
        r"\s*(?:PLUGIN_ROOT\s*/\s*)?(?:[\"']schemas[\"']\s*/\s*)?"
        r"(?:/\s*)?"
        r"[\"']tmcp-[a-z0-9-]+-v\d+\.\d+"
        r"\.schema\.json[\"']\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True

    def in_method(method_name: str) -> bool:
        method_start = text.rfind(f"def {method_name}", 0, match.start())
        if method_start == -1:
            return False
        next_method = text.find("\n    def ", method_start + 1)
        return next_method == -1 or match.start() < next_method

    if in_method("test_schema_and_artifacts_have_versioned_contract_identities"):
        return re.fullmatch(
            r"\s*[\"']tmcp-[a-z0-9-]+-v\d+\.\d+[\"']\s*,?\s*",
            line,
            flags=re.IGNORECASE,
        ) is not None

    if not in_method("test_source_and_fixture_hashes_bind_the_declared_evidence"):
        return False
    block_start = text.rfind("expected_hashes = {", 0, match.start())
    block_end = text.find("\n        }", block_start)
    if block_start == -1 or block_end == -1 or match.start() > block_end:
        return False
    return re.fullmatch(
        r"\s*[\"']skills/tmcp-[a-z0-9-]+/SKILL\.md[\"']\s*:\s*"
        r"[\"'][0-9a-f]{64}[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ) is not None


def is_documented_runtime_decision_test_evidence(
    relative_path: str, text: str, match: re.Match[str]
) -> bool:
    """Allow immutable replay evidence in the runtime decision test."""

    if relative_path != "tests/test_tmcp_behavioral_atoms_runtime_decision_v0_4.py":
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]

    def in_method(method_name: str) -> bool:
        method_start = text.rfind(f"def {method_name}", 0, match.start())
        if method_start == -1:
            return False
        next_method = text.find("\n    def ", method_start + 1)
        return next_method == -1 or match.start() < next_method

    if re.fullmatch(
        r"\s*/\s*[\"']schemas/tmcp-[a-z0-9-]+-v\d+\.\d+\.schema\.json"
        r"[\"']\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if in_method("test_version_and_base_are_explicit") and re.fullmatch(
        r"\s*[\"'](?:tmcp-[a-z0-9-]+-v\d+\.\d+|[0-9a-f]{40})"
        r"[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if in_method("test_schema_and_handoff_point_to_the_same_packet") and re.fullmatch(
        r"\s*[\"'][0-9a-f]{40}[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if not in_method("test_manifest_has_exact_six_replayed_hashes"):
        return False
    block_start = text.rfind("expected = {", 0, match.start())
    block_end = text.find("\n        }", block_start)
    if block_start == -1 or block_end == -1 or match.start() > block_end:
        return False
    return re.fullmatch(
        r"\s*[\"'](?:docs|schemas|tests)/[^\"']+[\"']\s*:\s*"
        r"[\"'][0-9a-f]{64}[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ) is not None


def is_documented_runtime_h3_test_evidence(
    relative_path: str, text: str, match: re.Match[str]
) -> bool:
    """Allow immutable H3 boundary evidence in its structural test."""

    if relative_path != "tests/test_tmcp_behavioral_atoms_runtime_h3_v0_7.py":
        return False
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    if re.fullmatch(
        r"\s*(?:DECISION_SCHEMA_PATH\s*=\s*ROOT\s*/\s*|"
        r"FIXTURE_SCHEMA_PATH\s*=\s*ROOT\s*/\s*)[\"']schemas/"
        r"tmcp-[a-z0-9-]+-v\d+\.\d+\.schema\.json[\"']\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if re.match(r"\s*def [a-z0-9_]+\(", line, flags=re.IGNORECASE) is not None:
        return True
    if "item[\"id\"] ==" in line and re.search(
        r"[\"']h3_[a-z0-9_]+[\"']", line, flags=re.IGNORECASE
    ):
        return True
    if re.fullmatch(
        r"\s*[\"']tmcp-[a-z0-9-]+-v\d+\.\d+[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    if re.fullmatch(
        r"\s*[\"']h3_[a-z0-9_]+[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ):
        return True
    return re.fullmatch(
        r"\s*[\"'][a-z0-9_]+[\"']\s*:\s*[\"'][0-9a-f]{64}[\"']\s*,?\s*",
        line,
        flags=re.IGNORECASE,
    ) is not None


def scan_release_content(relative_path: str, content: bytes) -> None:
    text = content.decode("utf-8", errors="replace")
    for label, pattern in PACKAGE_SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if label == "long_high_entropy" and (
                not looks_high_entropy(match.group(0))
                or is_documented_checksum(text, match)
                or is_documented_repository_path(relative_path, match)
                or is_documented_manifest_path(relative_path, text, match)
                or is_documented_python_schema_constant(relative_path, text, match)
                or is_documented_skill_fixture_path(relative_path, text, match)
                or is_documented_schema_identifier(relative_path, text, match)
                or is_documented_behavioral_atoms_test_evidence(
                    relative_path, text, match
                )
                or is_documented_runtime_decision_test_evidence(
                    relative_path, text, match
                )
                or is_documented_runtime_h3_test_evidence(
                    relative_path, text, match
                )
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
