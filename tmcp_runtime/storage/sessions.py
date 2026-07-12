"""Protected project-local packet session persistence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tmcp_runtime.safety import (
    collect_harvest_roots,
    redact_json_value,
    redact_path,
    read_json_input,
)
from tmcp_runtime.storage.artifacts import AtomicArtifactStore


PACKET_SESSION_SCHEMA = "tmcp-run-session-v0.1"
PACKET_SESSION_FORMAT_VERSION = 1
COMPOSED_PACKET_SCHEMA = "tmcp-composed-packet-v0.1"
MAX_PACKET_SESSION_BYTES = 262_144
MAX_PACKET_SESSION_DEPTH = 32
MAX_PACKET_SESSION_NODES = 2_048
_SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
_SESSION_KEY_PATTERN = re.compile(r"session-[0-9a-f]{32}")
_COMPOSED_PACKET_STRING_FIELDS = (
    "packet_id",
    "objective",
    "project_path",
    "phase",
)
_COMPOSED_PACKET_LIST_FIELDS = (
    "active_instructions",
    "required_reads",
    "tool_script_prompts",
    "verification_gates",
    "stop_conditions",
    "active_atoms",
    "deferred_atoms",
    "ignored_sources",
    "conflicts",
    "evidence_citations",
)
_COMPOSED_PACKET_OBJECT_FIELDS = (
    "global_cache",
    "receipt_template",
    "safety",
)


class PacketSessionError(ValueError):
    """Raised when a packet session violates its project-local boundary."""


@dataclass(frozen=True)
class PacketSessionSnapshot:
    """One validated, redacted latest-packet session record."""

    path: Path
    display_path: str
    key: str
    revision: int
    record: dict[str, Any]

    @property
    def packet(self) -> dict[str, Any]:
        packet = self.record.get("packet")
        return dict(packet) if isinstance(packet, dict) else {}

    def metadata(self) -> dict[str, Any]:
        return {
            "record_schema": PACKET_SESSION_SCHEMA,
            "key": self.key,
            "path": self.display_path,
            "revision": self.revision,
            "packet_id": self.packet.get("packet_id"),
            "state_effect": "project_local_write",
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _session_id(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise PacketSessionError("session_id must be a non-empty string.")
    session_id = value.strip()
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise PacketSessionError(
            "session_id must use 1-80 letters, numbers, dots, underscores, or hyphens."
        )
    return session_id


def _session_key(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode()).hexdigest()[:32]
    return f"session-{digest}"


def _project_root(project_path: str | Path) -> Path:
    path = Path(project_path).expanduser()
    if not path.is_absolute():
        raise PacketSessionError("project_path must be absolute for packet sessions.")
    roots, warnings = collect_harvest_roots([path], follow_symlinks=False)
    if warnings:
        raise PacketSessionError(
            "Could not validate project path for packet session: "
            f"{redact_path('; '.join(warnings))}"
        )
    if len(roots) != 1 or roots[0].kind != "directory":
        raise PacketSessionError("project_path must be one real directory for packet sessions.")
    return roots[0].logical_path


def _bounded_json(value: object) -> bool:
    pending: list[tuple[object, int]] = [(value, 1)]
    node_count = 0
    while pending:
        current, depth = pending.pop()
        node_count += 1
        if node_count > MAX_PACKET_SESSION_NODES or depth > MAX_PACKET_SESSION_DEPTH:
            return False
        if isinstance(current, dict):
            for key, item in current.items():
                pending.append((key, depth + 1))
                pending.append((item, depth + 1))
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    return True


def _composed_packet_is_valid(packet: object) -> bool:
    if not isinstance(packet, dict) or packet.get("schema") != COMPOSED_PACKET_SCHEMA:
        return False
    for field in _COMPOSED_PACKET_STRING_FIELDS:
        if not isinstance(packet.get(field), str):
            return False
    for field in _COMPOSED_PACKET_LIST_FIELDS:
        if not isinstance(packet.get(field), list):
            return False
    return all(isinstance(packet.get(field), dict) for field in _COMPOSED_PACKET_OBJECT_FIELDS)


def _recompile_record_is_valid(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    previous_packet_id = value.get("previous_packet_id")
    return (
        (previous_packet_id is None or isinstance(previous_packet_id, str))
        and isinstance(value.get("recompile_reason"), str)
        and bool(str(value.get("recompile_reason")).strip())
        and isinstance(value.get("updated_at"), str)
        and bool(str(value.get("updated_at")).strip())
    )


def _record_snapshot(path: Path, payload: dict[str, Any]) -> PacketSessionSnapshot:
    if not _bounded_json(payload):
        raise PacketSessionError("Packet session exceeds the supported JSON complexity.")
    if payload.get("schema") != PACKET_SESSION_SCHEMA:
        raise PacketSessionError("Packet session has an unsupported schema.")
    format_version = payload.get("format_version")
    if isinstance(format_version, bool) or format_version != PACKET_SESSION_FORMAT_VERSION:
        raise PacketSessionError("Packet session has an unsupported format version.")
    revision = payload.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise PacketSessionError("Packet session has an invalid revision.")
    for field in ("created_at", "updated_at"):
        if not isinstance(payload.get(field), str) or not str(payload[field]).strip():
            raise PacketSessionError(f"Packet session is missing {field}.")
    packet = payload.get("packet")
    if not _composed_packet_is_valid(packet):
        raise PacketSessionError("Packet session does not contain a composed packet.")
    last_recompile = payload.get("last_recompile")
    if not _recompile_record_is_valid(last_recompile):
        raise PacketSessionError("Packet session has an invalid recompile record.")
    key = path.parent.name
    if not _SESSION_KEY_PATTERN.fullmatch(key):
        raise PacketSessionError("Packet session has an invalid opaque key.")
    return PacketSessionSnapshot(
        path=path,
        display_path=redact_path(path),
        key=key,
        revision=revision,
        record=dict(payload),
    )


@dataclass(frozen=True)
class PacketSessionStore:
    """A verified, project-local latest-packet record for one serialized run."""

    project_root: Path
    session_id: str
    path: Path
    key: str

    @classmethod
    def open(cls, project_path: str | Path, session_id: object) -> PacketSessionStore:
        root = _project_root(project_path)
        identifier = _session_id(session_id)
        key = _session_key(identifier)
        return cls(
            project_root=root,
            session_id=identifier,
            path=root / ".tmcp" / "runs" / key / "latest-packet.json",
            key=key,
        )

    def load(self) -> PacketSessionSnapshot:
        try:
            source = read_json_input(
                self.path,
                project_path=self.project_root,
                max_file_bytes=MAX_PACKET_SESSION_BYTES,
            )
        except (MemoryError, RecursionError, ValueError) as exc:
            raise PacketSessionError(
                "Could not load packet session: " f"{redact_path(str(exc))}"
            ) from exc
        return _record_snapshot(self.path, source.payload)

    def create(
        self,
        packet: dict[str, Any],
        *,
        now: str | None = None,
    ) -> PacketSessionSnapshot:
        timestamp = now or _now_iso()
        return self._write(
            packet,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
            last_recompile=None,
            create=True,
        )

    def update(
        self,
        snapshot: PacketSessionSnapshot,
        packet: dict[str, Any],
        *,
        last_recompile: dict[str, Any],
        now: str | None = None,
    ) -> PacketSessionSnapshot:
        if snapshot.path != self.path:
            raise PacketSessionError("Packet session snapshot belongs to another session.")
        created_at = snapshot.record.get("created_at")
        if not isinstance(created_at, str) or not created_at:
            raise PacketSessionError("Packet session is missing created_at.")
        return self._write(
            packet,
            revision=snapshot.revision + 1,
            created_at=created_at,
            updated_at=now or _now_iso(),
            last_recompile=last_recompile,
            create=False,
        )

    def _write(
        self,
        packet: dict[str, Any],
        *,
        revision: int,
        created_at: str,
        updated_at: str,
        last_recompile: dict[str, Any] | None,
        create: bool,
    ) -> PacketSessionSnapshot:
        if not _composed_packet_is_valid(packet):
            raise PacketSessionError("Packet sessions require a composed packet.")
        if not _recompile_record_is_valid(last_recompile):
            raise PacketSessionError("Packet session has an invalid recompile record.")
        record: dict[str, Any] = {
            "schema": PACKET_SESSION_SCHEMA,
            "format_version": PACKET_SESSION_FORMAT_VERSION,
            "revision": revision,
            "created_at": created_at,
            "updated_at": updated_at,
            "packet": packet,
            "last_recompile": last_recompile,
        }
        if not _bounded_json(record):
            raise PacketSessionError("Packet session exceeds the supported JSON complexity.")
        try:
            safe_record, _ = redact_json_value(record, enabled=True)
        except (MemoryError, RecursionError) as exc:
            raise PacketSessionError("Could not redact packet session safely.") from exc
        if not isinstance(safe_record, dict):
            raise PacketSessionError("Packet session must be a JSON object.")
        snapshot = _record_snapshot(self.path, safe_record)
        runs_store = AtomicArtifactStore.explicit(self.path.parent.parent)
        with runs_store.locked(f"{self.key}.lock"):
            if create:
                AtomicArtifactStore.write_json_bundle(
                    self.path.parent,
                    {self.path.name: safe_record},
                )
            else:
                current = self.load()
                if current.revision != revision - 1:
                    raise PacketSessionError(
                        "Packet session changed before this recompile could be saved."
                    )
                AtomicArtifactStore.explicit(self.path.parent).write_json(
                    self.path.name,
                    safe_record,
                )
        return snapshot
