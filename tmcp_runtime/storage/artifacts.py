"""Atomic, symlink-aware text and JSON artifact output."""

from __future__ import annotations

import json
import os
import stat
import uuid
from collections.abc import Mapping
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tmcp_runtime.safety import redact_path

try:
    import fcntl
except ImportError:  # pragma: no cover - durable writes already fail closed here.
    fcntl = None


class ArtifactStorageError(RuntimeError):
    """Raised when an artifact destination violates the storage boundary."""


def _absolute_path(value: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(value).expanduser())))


def _normalized_path(value: str | Path) -> Path:
    path = _absolute_path(value)
    if os.name != "posix":
        return path
    for alias in (Path("/tmp"), Path("/var")):
        try:
            relative_path = path.relative_to(alias)
        except ValueError:
            continue
        try:
            target = alias.resolve(strict=True)
        except OSError:
            continue
        if target.is_dir():
            return target / relative_path
    return path


def _supports_descriptor_relative_operations() -> bool:
    required = (os.open, os.mkdir, os.stat, os.unlink, os.rmdir)
    return hasattr(os, "O_NOFOLLOW") and not any(
        operation not in os.supports_dir_fd for operation in required
    )


def artifact_persistence_available() -> bool:
    """Whether this runtime can provide TMCP's safe artifact-write guarantee."""

    return _supports_descriptor_relative_operations()


def _require_secure_directory_operations() -> None:
    if not artifact_persistence_available():
        raise ArtifactStorageError(
            "Secure artifact persistence requires descriptor-relative no-follow "
            "filesystem operations that are unavailable on this platform. This "
            "operation cannot create artifacts here."
        )


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW


def _open_directory(path: Path, *, create: bool) -> int:
    _require_secure_directory_operations()
    anchor = Path(path.anchor)
    try:
        descriptor = os.open(anchor, _directory_flags())
    except OSError as exc:
        raise ArtifactStorageError(
            f"Could not open artifact directory {redact_path(anchor)}."
        ) from exc
    try:
        for part in path.parts[1:]:
            try:
                child_descriptor = os.open(
                    part,
                    _directory_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise ArtifactStorageError(
                        f"Artifact directory does not exist: {redact_path(path)}"
                    )
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise ArtifactStorageError(
                        f"Could not create artifact directory {redact_path(path)}."
                    ) from exc
                try:
                    child_descriptor = os.open(
                        part,
                        _directory_flags(),
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise ArtifactStorageError(
                        f"Refusing unsafe artifact directory {redact_path(path)}."
                    ) from exc
            except OSError as exc:
                raise ArtifactStorageError(
                    f"Refusing unsafe artifact directory {redact_path(path)}."
                ) from exc
            os.close(descriptor)
            descriptor = child_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _entry_metadata(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ArtifactStorageError("Could not inspect artifact destination.") from exc


def _validate_name(name: str) -> None:
    candidate = Path(name)
    if not name or candidate.name != name or name in {".", ".."}:
        raise ArtifactStorageError(f"Artifact name must be a single filename: {name!r}")


def _validate_file_target(directory_fd: int, name: str) -> None:
    _validate_name(name)
    metadata = _entry_metadata(directory_fd, name)
    if metadata is None:
        return
    if stat.S_ISLNK(metadata.st_mode):
        raise ArtifactStorageError(f"Refusing symlinked artifact file: {redact_path(name)}")
    if not stat.S_ISREG(metadata.st_mode):
        raise ArtifactStorageError(
            f"Artifact destination is not a regular file: {redact_path(name)}"
        )


def _sync_directory(directory_fd: int) -> None:
    try:
        os.fsync(directory_fd)
    except OSError:
        pass


def _temporary_name(name: str) -> str:
    return f".{name}.{uuid.uuid4().hex}.tmp"


def _json_content(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _write_text_at(directory_fd: int, name: str, content: str) -> None:
    _validate_file_target(directory_fd, name)
    temporary_name = _temporary_name(name)
    descriptor = -1
    committed = False
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as artifact:
            descriptor = -1
            artifact.write(content)
            artifact.flush()
            os.fsync(artifact.fileno())
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        committed = True
        _sync_directory(directory_fd)
    except OSError as exc:
        raise ArtifactStorageError(
            f"Could not atomically write artifact {redact_path(name)}."
        ) from exc
    finally:
        if descriptor != -1:
            os.close(descriptor)
        if not committed:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _directory_is_empty(parent_fd: int, name: str) -> bool:
    try:
        directory_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise ArtifactStorageError(
            f"Refusing unsafe artifact directory {redact_path(name)}."
        ) from exc
    try:
        return not os.listdir(directory_fd)
    finally:
        os.close(directory_fd)


def _remove_staging_directory(parent_fd: int, name: str) -> None:
    try:
        directory_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError:
        return
    try:
        for entry_name in os.listdir(directory_fd):
            try:
                os.unlink(entry_name, dir_fd=directory_fd)
            except OSError:
                return
    finally:
        os.close(directory_fd)
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        pass


@dataclass(frozen=True)
class AtomicArtifactStore:
    """A verified directory that accepts atomic text and JSON artifact writes."""

    root: Path
    identity: tuple[int, int]

    @classmethod
    def explicit(cls, output_dir: str | Path) -> AtomicArtifactStore:
        root = _normalized_path(output_dir)
        directory_fd = _open_directory(root, create=True)
        try:
            metadata = os.fstat(directory_fd)
        finally:
            os.close(directory_fd)
        return cls(root=root, identity=(metadata.st_dev, metadata.st_ino))

    @classmethod
    def write_text_bundle(
        cls,
        output_dir: str | Path,
        artifacts: Mapping[str, str],
    ) -> dict[str, str]:
        if not artifacts:
            return {}
        names = list(artifacts)
        for name in names:
            _validate_name(name)
            if not isinstance(artifacts[name], str):
                raise ArtifactStorageError(
                    f"Artifact content must be text: {redact_path(name)}"
                )
        root = _normalized_path(output_dir)
        parent_fd = _open_directory(root.parent, create=True)
        stage_name = _temporary_name(root.name)
        stage_fd = -1
        committed = False
        try:
            existing = _entry_metadata(parent_fd, root.name)
            if existing is not None:
                if stat.S_ISLNK(existing.st_mode):
                    raise ArtifactStorageError(
                        "Refusing symlinked artifact bundle directory: "
                        f"{redact_path(root)}"
                    )
                if not stat.S_ISDIR(existing.st_mode) or not _directory_is_empty(
                    parent_fd,
                    root.name,
                ):
                    raise ArtifactStorageError(
                        "Artifact bundle destination must be absent or empty: "
                        f"{redact_path(root)}"
                    )
            os.mkdir(stage_name, mode=0o700, dir_fd=parent_fd)
            stage_fd = os.open(stage_name, _directory_flags(), dir_fd=parent_fd)
            for name in names:
                _write_text_at(stage_fd, name, artifacts[name])
            _sync_directory(stage_fd)
            os.close(stage_fd)
            stage_fd = -1
            os.replace(
                stage_name,
                root.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            committed = True
            _sync_directory(parent_fd)
        except OSError as exc:
            raise ArtifactStorageError(
                f"Could not atomically commit artifact bundle {redact_path(root)}."
            ) from exc
        finally:
            if stage_fd != -1:
                os.close(stage_fd)
            if not committed:
                _remove_staging_directory(parent_fd, stage_name)
            os.close(parent_fd)
        return {name: str(root / name) for name in names}

    @classmethod
    def write_json_bundle(
        cls,
        output_dir: str | Path,
        payloads: Mapping[str, Any],
    ) -> dict[str, str]:
        return cls.write_text_bundle(
            output_dir,
            {name: _json_content(payload) for name, payload in payloads.items()},
        )

    @classmethod
    def write_bundle(
        cls,
        output_dir: str | Path,
        *,
        json_artifacts: Mapping[str, Any] | None = None,
        text_artifacts: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        artifacts = {
            name: _json_content(payload)
            for name, payload in (json_artifacts or {}).items()
        }
        for name, content in (text_artifacts or {}).items():
            if name in artifacts:
                raise ArtifactStorageError(
                    f"Duplicate artifact name: {redact_path(name)}"
                )
            artifacts[name] = content
        return cls.write_text_bundle(output_dir, artifacts)

    def write_text(self, name: str, content: str) -> Path:
        if not isinstance(content, str):
            raise ArtifactStorageError(
                f"Artifact content must be text: {redact_path(name)}"
            )
        directory_fd = _open_directory(self.root, create=False)
        try:
            metadata = os.fstat(directory_fd)
            if (metadata.st_dev, metadata.st_ino) != self.identity:
                raise ArtifactStorageError(
                    "Artifact directory changed during write: "
                    f"{redact_path(self.root)}"
                )
            _write_text_at(directory_fd, name, content)
        finally:
            os.close(directory_fd)
        return self.root / name

    def write_json(self, name: str, payload: Any) -> Path:
        return self.write_text(name, _json_content(payload))

    @contextmanager
    def locked(self, name: str) -> Iterator[None]:
        """Serialize one named operation inside this verified directory."""

        _validate_name(name)
        if fcntl is None:
            raise ArtifactStorageError(
                "Secure artifact locking is unavailable on this platform."
            )
        directory_fd = _open_directory(self.root, create=False)
        descriptor = -1
        locked = False
        try:
            metadata = os.fstat(directory_fd)
            if (metadata.st_dev, metadata.st_ino) != self.identity:
                raise ArtifactStorageError(
                    "Artifact directory changed during lock: " f"{redact_path(self.root)}"
                )
            _validate_file_target(directory_fd, name)
            try:
                descriptor = os.open(
                    name,
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory_fd,
                )
                os.fchmod(descriptor, 0o600)
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                locked = True
            except OSError as exc:
                raise ArtifactStorageError(
                    f"Could not lock artifact {redact_path(name)}."
                ) from exc
            yield
        finally:
            if descriptor != -1:
                if locked:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    except OSError:
                        pass
                os.close(descriptor)
            os.close(directory_fd)
