from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Protocol, cast

from tmcp_runtime.domain.composition_phase_bindings import (
    validate_phase_capsule_binding,
)
from tmcp_runtime.services.compose import prepare_composition_from_source_nodes
from tmcp_runtime.storage import (
    ArtifactStorageError,
    AtomicArtifactStore,
    PACKET_SESSION_SCHEMA,
    PacketSessionError,
    PacketSessionStore,
    artifact_persistence_available,
)


def _packet(objective: str = "Review release safety") -> dict[str, object]:
    return {
        "schema": "tmcp-composed-packet-v0.1",
        "packet_id": "packet-123",
        "objective": objective,
        "project_path": "/tmp/project",
        "phase": "start",
        "active_instructions": [],
        "required_reads": [],
        "tool_script_prompts": [],
        "verification_gates": [],
        "stop_conditions": [],
        "active_atoms": [],
        "deferred_atoms": [],
        "ignored_sources": [],
        "conflicts": [],
        "evidence_citations": [],
        "global_cache": {},
        "receipt_template": {"schema": "tmcp-run-receipt-v0.1"},
        "safety": {},
    }


def _semantic_composition_packet() -> dict[str, Any]:
    """Compile one real semantic packet for persistence-boundary coverage."""

    from tests.test_tmcp_composition_integration import CompositionIntegrationTests

    harness = CompositionIntegrationTests()
    harness.setUp()
    prepared = prepare_composition_from_source_nodes(
        harness.arguments,
        source_nodes=harness.nodes,
    )
    return cast(
        dict[str, Any],
        harness._compose(
            {**harness.arguments, "semantic_proposal": harness._proposal(prepared)}
        ),
    )


def _symlink_or_skip(test_case: unittest.TestCase, link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (NotImplementedError, OSError) as exc:
        test_case.skipTest(f"Symlinks are unavailable in this environment: {exc}")


class _Event(Protocol):
    def set(self) -> None: ...

    def wait(self, timeout: float | None = None) -> bool: ...


def _hold_artifact_lock(root: str, entered: _Event, release: _Event) -> None:
    store = AtomicArtifactStore.explicit(root)
    with store.locked("session.lock"):
        entered.set()
        release.wait(10)


def _attempt_artifact_lock(root: str, attempting: _Event, acquired: _Event) -> None:
    store = AtomicArtifactStore.explicit(root)
    attempting.set()
    with store.locked("session.lock"):
        acquired.set()


class PacketSessionStoreTests(unittest.TestCase):
    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_create_load_and_update_keep_a_redacted_latest_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            secret = "sk-" + "S" * 40
            store = PacketSessionStore.open(project, secret)
            created = store.create(
                _packet(f"Review {secret}"), now="2026-07-11T00:00:00Z"
            )
            loaded = store.load()
            updated = store.update(
                loaded,
                _packet("Review the next release"),
                last_recompile={
                    "previous_packet_id": "packet-123",
                    "recompile_reason": "phase_transition",
                    "updated_at": "2026-07-11T00:01:00Z",
                },
                now="2026-07-11T00:01:00Z",
            )
            payload = json.loads(store.path.read_text(encoding="utf-8"))
            file_mode = store.path.stat().st_mode & 0o777

        self.assertEqual(created.revision, 1)
        self.assertEqual(loaded.revision, 1)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(payload["schema"], PACKET_SESSION_SCHEMA)
        self.assertEqual(payload["revision"], 2)
        self.assertEqual(payload["created_at"], "2026-07-11T00:00:00Z")
        self.assertEqual(payload["updated_at"], "2026-07-11T00:01:00Z")
        self.assertEqual(
            payload["last_recompile"]["recompile_reason"], "phase_transition"
        )
        self.assertNotIn(secret, json.dumps(payload))
        self.assertNotIn(secret, json.dumps(updated.metadata()))
        self.assertNotIn(secret, store.path.name)
        self.assertEqual(updated.metadata()["record_schema"], PACKET_SESSION_SCHEMA)
        self.assertEqual(updated.metadata()["state_effect"], "project_local_write")
        if os.name != "nt":
            self.assertEqual(file_mode, 0o600)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_semantic_phase_binding_survives_session_redaction_and_reload(
        self,
    ) -> None:
        packet = _semantic_composition_packet()
        plan_map = copy.deepcopy(
            cast(dict[str, Any], packet["composition_plan"])
        )
        receipt_map = copy.deepcopy(
            cast(dict[str, Any], packet["receipt_template"])
        )
        binding = copy.deepcopy(plan_map["phase_capsule_binding"])
        source_secret = "sk-" + "S" * 40
        arbitrary_hash = hashlib.sha256(b"unapproved-session-hash").hexdigest()
        plan_map["unapproved_source_prose"] = (
            f"Never persist this unapproved source prose: {source_secret}"
        )
        receipt_map["opaque_digest"] = arbitrary_hash
        receipt_map["execution_context"] = {
            "preflight_context_instance_id": "host-context-should-not-persist",
            "host_private_source": source_secret,
        }
        packet["composition_plan"] = plan_map
        packet["receipt_template"] = receipt_map
        packet["execution_context"] = {
            "host_context_id": "host-context-should-not-persist"
        }
        expected_receipt = {
            field: copy.deepcopy(receipt_map[field])
            for field in (
                "composition_plan_digest",
                "phase_capsule_binding_digest",
                "context_accounting_digest",
                "preflight_capsule_digest",
                "phase_capsule_trace",
            )
        }

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = PacketSessionStore.open(project, "semantic-phase-binding")
            created = store.create(packet, now="2026-07-17T00:00:00Z")
            loaded = store.load()
            serialized = store.path.read_text(encoding="utf-8")

        for snapshot in (created, loaded):
            persisted_packet = snapshot.packet
            persisted_plan = cast(
                dict[str, Any], persisted_packet["composition_plan"]
            )
            persisted_receipt = cast(
                dict[str, Any], persisted_packet["receipt_template"]
            )
            self.assertEqual(persisted_plan["phase_capsule_binding"], binding)
            self.assertEqual(
                {
                    field: persisted_receipt[field]
                    for field in expected_receipt
                },
                expected_receipt,
            )
            self.assertEqual(
                validate_phase_capsule_binding(
                    persisted_plan["phase_capsule_binding"]
                ),
                binding,
            )
            self.assertNotIn("execution_context", persisted_packet)
            self.assertNotIn("execution_context", persisted_receipt)
            self.assertEqual(
                persisted_receipt["opaque_digest"],
                "[REDACTED:long_high_entropy]",
            )
            self.assertNotIn(source_secret, json.dumps(persisted_plan))

        self.assertIn(binding["binding_digest"], serialized)
        self.assertIn(expected_receipt["composition_plan_digest"], serialized)
        self.assertNotIn(source_secret, serialized)
        self.assertNotIn(arbitrary_hash, serialized)
        self.assertNotIn("execution_context", serialized)
        self.assertIn("[REDACTED:openai_key]", serialized)

    def test_session_id_and_packet_shape_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            with self.assertRaises(PacketSessionError):
                PacketSessionStore.open(".", "run-1")
            for session_id in ("", "../escape", "/absolute", "name/child", "a" * 81):
                with self.subTest(session_id=session_id):
                    with self.assertRaises(PacketSessionError):
                        PacketSessionStore.open(project, session_id)

            store = PacketSessionStore.open(project, "run-1")
            with self.assertRaises(PacketSessionError):
                store.create({"schema": "not-a-packet"})

    def test_load_rejects_invalid_or_complex_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = PacketSessionStore.open(project, "run-1")
            store.path.parent.mkdir(parents=True)
            store.path.write_text(
                json.dumps({"schema": "unexpected"}), encoding="utf-8"
            )
            with self.assertRaises(PacketSessionError):
                store.load()

            deeply_nested = {"value": "x"}
            for _ in range(40):
                deeply_nested = {"nested": deeply_nested}
            store.path.write_text(
                json.dumps(
                    {
                        "schema": PACKET_SESSION_SCHEMA,
                        "format_version": 1,
                        "revision": 1,
                        "created_at": "2026-07-11T00:00:00Z",
                        "updated_at": "2026-07-11T00:00:00Z",
                        "packet": deeply_nested,
                        "last_recompile": None,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(PacketSessionError):
                store.load()

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_session_parent_symlink_cannot_receive_a_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            project = sandbox / "project"
            outside = sandbox / "outside"
            project.mkdir()
            outside.mkdir()
            _symlink_or_skip(self, project / ".tmcp", outside)
            store = PacketSessionStore.open(project, "run-1")
            with self.assertRaises(ArtifactStorageError):
                store.create(_packet())

            self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_create_refuses_to_replace_an_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = PacketSessionStore.open(project, "run-1")
            store.create(_packet())

            with self.assertRaises(ArtifactStorageError):
                store.create(_packet("Restart the run"))

            self.assertEqual(store.load().revision, 1)

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_update_rejects_a_stale_session_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = PacketSessionStore.open(project, "run-1")
            store.create(_packet())
            stale = store.load()
            store.update(
                stale,
                _packet("First recompile"),
                last_recompile={
                    "previous_packet_id": "packet-123",
                    "recompile_reason": "phase_transition",
                    "updated_at": "2026-07-11T00:01:00Z",
                },
            )

            with self.assertRaises(PacketSessionError):
                store.update(
                    stale,
                    _packet("Stale recompile"),
                    last_recompile={
                        "previous_packet_id": "packet-123",
                        "recompile_reason": "phase_transition",
                        "updated_at": "2026-07-11T00:02:00Z",
                    },
                )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_artifact_lock_serializes_separate_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = multiprocessing.get_context("spawn")
            entered = context.Event()
            release = context.Event()
            attempting = context.Event()
            acquired = context.Event()
            holder = context.Process(
                target=_hold_artifact_lock,
                args=(tmp, entered, release),
            )
            waiter = context.Process(
                target=_attempt_artifact_lock,
                args=(tmp, attempting, acquired),
            )
            holder.start()
            waiter_started = False
            try:
                self.assertTrue(entered.wait(10), "holder did not acquire the lock")
                waiter.start()
                waiter_started = True
                self.assertTrue(attempting.wait(10), "waiter did not attempt the lock")
                self.assertFalse(
                    acquired.wait(0.25), "second process acquired a held lock"
                )
                release.set()
                self.assertTrue(
                    acquired.wait(10), "waiter did not acquire the released lock"
                )
            finally:
                release.set()
                holder.join(10)
                if waiter_started:
                    waiter.join(10)
                if holder.is_alive():
                    holder.terminate()
                if waiter_started and waiter.is_alive():
                    waiter.terminate()

            self.assertEqual(holder.exitcode, 0)
            if waiter_started:
                self.assertEqual(waiter.exitcode, 0)

    def test_unsupported_platform_fails_closed_only_when_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            store = PacketSessionStore.open(project, "run-1")
            from unittest.mock import patch

            with patch(
                "tmcp_runtime.storage.artifacts._supports_descriptor_relative_operations",
                return_value=False,
            ):
                with self.assertRaises(ArtifactStorageError):
                    store.create(_packet())

            self.assertFalse((project / ".tmcp").exists())


if __name__ == "__main__":
    unittest.main()
