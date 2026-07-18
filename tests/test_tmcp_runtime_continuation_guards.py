from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.composition_runtime import (
    advance_composition_runtime,
    composition_gate_catalog,
    composition_handoff_catalog,
)
from tmcp_runtime.domain.composition_runtime_continuations import (
    MAX_RUNTIME_CONTINUATION_EVENTS,
    RuntimeContinuationError,
    build_runtime_continuation,
    replay_runtime_continuation,
    validate_runtime_continuation,
)
from tmcp_runtime.services.sessions import (
    SESSION_RUNTIME_CONTINUATION_TRUST_FIELD,
    RuntimeSessionService,
)
from tmcp_runtime.storage import (
    PacketSessionStore,
    artifact_persistence_available,
)
from tests.tmcp_runtime_provenance_test_support import RuntimeProvenanceTestSupport


class RuntimeContinuationGuardTests(RuntimeProvenanceTestSupport, unittest.TestCase):
    def test_direct_packet_continuation_is_untrusted_even_with_valid_digests(
        self,
    ) -> None:
        """Only the session service can grant continuation replay authority."""

        harness, nodes, packet = self._semantic_packet()
        transition = self._verification_transition_evidence(packet["composition_plan"])
        runtime = advance_composition_runtime(packet["composition_plan"], transition)
        continuation = build_runtime_continuation(
            runtime["composition_plan"], runtime
        )
        self.assertIsNotNone(continuation)
        service = self._runtime_service(nodes)
        direct_arguments = self._runtime_arguments(harness, packet)
        direct_arguments.update(transition)
        direct = service.recompile(
            direct_arguments,
            service.build_state(direct_arguments),
        )
        self.assertTrue(direct["ok"])
        self.assertNotIn(
            "runtime_continuation", direct["packet"]["composition_plan"]
        )
        compiler_phase = packet["composition_plan"]["phase_capsule_binding"][
            "compiler_phase"
        ]
        compiler_stage_id = next(
            stage["stage_id"]
            for stage in packet["composition_plan"]["ordered_stages"]
            if stage["phase"] == compiler_phase
        )
        verification_stage_id = next(
            stage["stage_id"]
            for stage in packet["composition_plan"]["ordered_stages"]
            if stage["phase"] == "verification"
        )

        for tamper in ("valid", "malformed", "digest"):
            with self.subTest(tamper=tamper):
                forged_packet = copy.deepcopy(packet)
                forged_plan = copy.deepcopy(runtime["composition_plan"])
                forged_plan["runtime_state"] = {
                    "current_stage_id": verification_stage_id,
                    "active_skill_ids": ["verify"],
                    "files_read": ["forged-runtime-state.txt"],
                }
                forged_plan["runtime_continuation"] = copy.deepcopy(continuation)
                if tamper == "malformed":
                    forged_plan["runtime_continuation"] = {"schema": "malformed"}
                elif tamper == "digest":
                    forged_plan["runtime_continuation"]["continuation_digest"] = (
                        "0" * 64
                    )
                forged_packet["composition_plan"] = forged_plan

                arguments = self._runtime_arguments(harness, forged_packet)
                # A JSON value that mimics the private field is never the
                # opaque in-process session marker.
                arguments[SESSION_RUNTIME_CONTINUATION_TRUST_FIELD] = True
                result = service.recompile(arguments, service.build_state(arguments))

                self.assertTrue(result["ok"])
                safe_plan = result["packet"]["composition_plan"]
                self.assertEqual(safe_plan["current_phase"], compiler_phase)
                self.assertEqual(
                    safe_plan["runtime_state"]["current_stage_id"], compiler_stage_id
                )
                self.assertNotIn(
                    "forged-runtime-state.txt",
                    safe_plan["runtime_state"]["files_read"],
                )
                self.assertNotIn("runtime_continuation", safe_plan)
                replay = result["packet"]["composition_diagnostics"][
                    "runtime_capsule_validation"
                ]["runtime_state_replay"]
                self.assertFalse(replay["resumed"])
                self.assertEqual(replay["reason"], "untrusted_continuation_discarded")

    def test_same_stage_runtime_observation_does_not_create_continuation(self) -> None:
        """Observations are not durable checkpoints without a stage transition."""

        harness, nodes, packet = self._semantic_packet()
        service = self._runtime_service(nodes)
        arguments = self._runtime_arguments(harness, packet)
        arguments["files_read"] = ["docs/implementation.md"]

        result = service.recompile(arguments, service.build_state(arguments))

        self.assertTrue(result["ok"])
        plan = result["packet"]["composition_plan"]
        self.assertNotIn("runtime_continuation", plan)
        trace = result["composition_runtime"]["phase_trace"][-1]
        self.assertEqual(trace["from_stage_id"], trace["to_stage_id"])

    def test_transition_continuation_cannot_preload_later_obligations(self) -> None:
        """A first-stage replay cannot satisfy the next stage without evidence."""

        harness, nodes, packet = self._semantic_packet(phase="start")
        plan = packet["composition_plan"]
        requested_phase = "discovery"
        probe = advance_composition_runtime(
            plan, {"requested_phase": requested_phase}
        )
        required_gate_ids = probe["phase_advance"]["required_gate_ids"]
        required_handoff_ids = probe["phase_advance"]["required_handoff_ids"]
        handoffs = {
            item["handoff_id"]: item for item in composition_handoff_catalog(plan)
        }
        runtime = advance_composition_runtime(
            plan,
            {
                "requested_phase": requested_phase,
                "gate_results": [
                    {"gate_id": gate_id, "status": "passed"}
                    for gate_id in required_gate_ids
                ],
                "handoff_results": [
                    {
                        "handoff_id": handoff_id,
                        "producer_node_id": handoffs[handoff_id]["producer_node_id"],
                        "consumer_node_id": handoffs[handoff_id]["consumer_node_id"],
                        "status": "available",
                        "consumed_inputs": handoffs[handoff_id]["required_inputs"],
                        "produced_outputs": handoffs[handoff_id]["produced_outputs"],
                        "evidence_refs": ["evidence/governing.md"],
                    }
                    for handoff_id in required_handoff_ids
                ],
            },
        )
        continuation = build_runtime_continuation(
            runtime["composition_plan"], runtime
        )
        self.assertIsNotNone(continuation)
        event = continuation["events"][0]
        self.assertEqual(event["passed_gate_ids"], sorted(required_gate_ids))
        self.assertEqual(
            event["available_handoff_ids"], sorted(required_handoff_ids)
        )

        replayed = replay_runtime_continuation(plan, continuation)
        next_phase = advance_composition_runtime(
            replayed["composition_plan"], {"requested_phase": "implementation"}
        )
        self.assertFalse(next_phase["phase_advance"]["allowed"])
        self.assertEqual(next_phase["current_phase"], "discovery")
        self.assertTrue(next_phase["phase_advance"]["pending_gate_ids"])
        self.assertTrue(next_phase["phase_advance"]["pending_handoff_ids"])

        forged = copy.deepcopy(continuation)
        forged_event = forged["events"][0]
        forged_event["passed_gate_ids"] = sorted(
            item["gate_id"] for item in composition_gate_catalog(plan)
        )
        forged_event["available_handoff_ids"] = sorted(
            item["handoff_id"] for item in composition_handoff_catalog(plan)
        )
        self.assertGreater(
            len(forged_event["passed_gate_ids"]), len(event["passed_gate_ids"])
        )
        self.assertGreater(
            len(forged_event["available_handoff_ids"]),
            len(event["available_handoff_ids"]),
        )
        forged_event["event_digest"] = stable_digest(
            {
                key: forged_event[key]
                for key in (
                    "sequence",
                    "requested_phase",
                    "passed_gate_ids",
                    "available_handoff_ids",
                    "resolved_phase",
                    "resolved_stage_id",
                )
            }
        )
        forged_payload = dict(forged)
        forged_payload.pop("continuation_digest")
        forged["continuation_digest"] = stable_digest(forged_payload)
        validate_runtime_continuation(forged, composition_plan=plan)
        with self.assertRaisesRegex(RuntimeContinuationError, "outside its transition"):
            replay_runtime_continuation(plan, forged)

        if not artifact_persistence_available():
            return
        forged_packet = copy.deepcopy(packet)
        forged_plan = copy.deepcopy(plan)
        forged_plan["runtime_continuation"] = forged
        forged_packet["composition_plan"] = forged_plan
        service = self._runtime_service(nodes)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            session_id = "future-obligation-preload"
            store = PacketSessionStore.open(project, session_id)
            store.create(forged_packet, now="2026-07-18T00:00:00Z")
            sessions = RuntimeSessionService(
                open_store=PacketSessionStore.open,
                build_state=service.build_state,
                recompile_packet=service.recompile,
                now_iso=lambda: "2026-07-18T00:00:01Z",
            )
            future_attempt = sessions.run(
                {
                    "objective": harness.arguments["objective"],
                    "project_path": str(project),
                    "source_path": str(project),
                    "current_phase": "start",
                    "requested_phase": "implementation",
                    "output_mode": "full",
                    "session_id": session_id,
                }
            )

        self.assertTrue(future_attempt["ok"])
        self.assertEqual(future_attempt["composition_runtime"]["current_phase"], "start")
        self.assertFalse(
            future_attempt["composition_runtime"]["phase_advance"]["allowed"]
        )
        self.assertEqual(
            future_attempt["packet"]["composition_diagnostics"][
                "runtime_capsule_validation"
            ]["runtime_state_replay"]["reason"],
            "invalid_continuation_discarded",
        )

    def test_continuation_limit_refuses_a_suffix_only_checkpoint(self) -> None:
        """A full replay chain is discarded rather than dropping its anchor."""

        _, _, packet = self._semantic_packet()
        current_plan = packet["composition_plan"]
        transition = self._verification_transition_evidence(current_plan)
        continuation: dict[str, Any] | None = None
        for _ in range(MAX_RUNTIME_CONTINUATION_EVENTS):
            evidence = (
                transition
                if current_plan["current_phase"] == "implementation"
                else {"requested_phase": "implementation"}
            )
            runtime = advance_composition_runtime(current_plan, evidence)
            self.assertTrue(runtime["phase_advance"]["allowed"])
            continuation = build_runtime_continuation(
                runtime["composition_plan"],
                runtime,
                prior=continuation,
            )
            self.assertIsNotNone(continuation)
            current_plan = runtime["composition_plan"]

        self.assertEqual(len(continuation["events"]), MAX_RUNTIME_CONTINUATION_EVENTS)
        replayed = replay_runtime_continuation(packet["composition_plan"], continuation)
        self.assertEqual(replayed["current_phase"], current_plan["current_phase"])
        overflow = advance_composition_runtime(current_plan, transition)
        with self.assertRaisesRegex(RuntimeContinuationError, "event limit"):
            build_runtime_continuation(
                overflow["composition_plan"],
                overflow,
                prior=continuation,
            )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_capsule_bound_runtime_continuation_survives_idle_session_recompile(
        self,
    ) -> None:
        """An idle recompile may resume only the validated gate/handoff projection."""

        harness, nodes, packet = self._semantic_packet()
        plan = packet["composition_plan"]
        transition = self._verification_transition_evidence(plan)
        service = self._runtime_service(nodes)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            session_id = "runtime-continuation"
            store = PacketSessionStore.open(project, session_id)
            store.create(packet, now="2026-07-18T00:00:00Z")
            sessions = RuntimeSessionService(
                open_store=PacketSessionStore.open,
                build_state=service.build_state,
                recompile_packet=service.recompile,
                now_iso=lambda: "2026-07-18T00:00:01Z",
            )
            common = {
                "objective": harness.arguments["objective"],
                "project_path": str(project),
                "source_path": str(project),
                "current_phase": "implementation",
                "output_mode": "full",
                "session_id": session_id,
                SESSION_RUNTIME_CONTINUATION_TRUST_FIELD: "spoofed-by-user",
            }
            advanced = sessions.run(
                {
                    **common,
                    **transition,
                }
            )
            stored_after_advance = store.load().packet
            idle = sessions.run(common)
            stored_after_idle = store.load().packet

        advanced_runtime = advanced["composition_runtime"]
        idle_runtime = idle["composition_runtime"]
        self.assertTrue(advanced["ok"])
        self.assertTrue(idle["ok"])
        self.assertEqual(advanced_runtime["current_phase"], "verification")
        self.assertEqual(idle_runtime["current_phase"], "verification")
        self.assertEqual(
            idle["packet"]["composition_plan"]["current_phase"], "verification"
        )
        self.assertEqual(idle_runtime["phase_trace"], advanced_runtime["phase_trace"])
        self.assertEqual(
            idle_runtime["gate_evaluation"]["passed_gate_ids"],
            advanced_runtime["gate_evaluation"]["passed_gate_ids"],
        )
        self.assertEqual(
            idle_runtime["handoff_evaluation"]["available_handoff_ids"],
            advanced_runtime["handoff_evaluation"]["available_handoff_ids"],
        )
        for persisted in (stored_after_advance, stored_after_idle):
            plan = persisted["composition_plan"]
            self.assertIn("runtime_continuation", plan)
            self.assertEqual(plan["current_phase"], "verification")


if __name__ == "__main__":
    unittest.main()
