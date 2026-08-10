from __future__ import annotations

import ast
import copy
import inspect
import json
import unittest
from pathlib import Path

import tmcp_runtime.domain.coordination as coordination_domain
from tests.tmcp_test_client import TestWorkspace
from tmcp_runtime.domain.coordination import (
    COORDINATOR_INSTRUCTION_OVERRIDE_POLICY,
    COORDINATOR_STATE_SCHEMA,
    COORDINATOR_TRUST,
    normalize_coordinator_state,
    resolve_coordinator_state,
)
from tmcp_runtime.domain.receipts import build_run_receipt
from tmcp_runtime.domain.runtime_state import derive_runtime_state


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PLUGIN_ROOT / "schemas" / "tmcp-coordinator-state-v0.1.schema.json"
RECEIPT_PATH = (
    PLUGIN_ROOT
    / "docs"
    / "experiments"
    / "tmcp-coordinator-consolidation-receipt-v0.1.json"
)
CURRENT_RECEIPT_PATH = (
    PLUGIN_ROOT
    / "docs"
    / "experiments"
    / "tmcp-coordinator-verification-receipt-v0.2.json"
)


def _coordinator_state(
    *, next_stream: str = "tmcp", next_status: str = "ready"
) -> dict[str, object]:
    return {
        "schema": COORDINATOR_STATE_SCHEMA,
        "active_stream": "tmcp",
        "next_action": {
            "id": "integrate-coordinator-state",
            "stream": next_stream,
            "description": "Integrate and validate the consolidated coordinator state.",
            "status": next_status,
        },
        "external_blockers": [
            {
                "stream": "codex_provider_validation",
                "status": "blocked",
                "reason": "Provider-native exact item attribution is unavailable.",
                "resume_condition": "The provider exposes authoritative item accounting.",
            },
            {
                "stream": "desktop_bridge",
                "status": "blocked",
                "reason": "The proprietary bridge source is outside this repository.",
                "resume_condition": "A bridge-owned integration surface is available.",
            },
        ],
        "prohibited_lane_transitions": [
            {
                "from": "tmcp",
                "to": "codex_provider_validation",
                "unless": "explicit_user_selection",
                "reason": "External provider work must not displace TMCP-owned work.",
            },
            {
                "from": "tmcp",
                "to": "desktop_bridge",
                "unless": "explicit_user_selection",
                "reason": "External bridge work must not displace TMCP-owned work.",
            },
        ],
        "source_handoffs": [
            {
                "handoff_id": "tmcp-side-chat-validation-bootstrap-v0.1",
                "source_thread_id": "019fcdb1-8908-79b3-866c-4e3c9c635d36",
                "status": "consolidated",
                "summary": "Validation bootstrap and readiness gates.",
            },
            {
                "handoff_id": "tmcp-desktop-bridge-preflight-side-chat-v0.1",
                "source_thread_id": "019fcd67-3919-7c41-8c4c-2fa3628f3633",
                "status": "consolidated",
                "summary": "Desktop bridge preflight and fail-closed checks.",
            },
        ],
    }


class TmcpCoordinationTests(unittest.TestCase):
    def test_normalization_preserves_tmcp_lane_and_does_not_mutate_input(self) -> None:
        source = _coordinator_state()
        original = copy.deepcopy(source)

        state = normalize_coordinator_state(source)

        self.assertEqual(source, original)
        self.assertEqual(state["active_stream"], "tmcp")
        self.assertEqual(state["next_action"]["stream"], "tmcp")
        self.assertEqual(state["trust"], COORDINATOR_TRUST)
        self.assertEqual(
            state["instruction_override_policy"],
            COORDINATOR_INSTRUCTION_OVERRIDE_POLICY,
        )
        self.assertEqual(
            [item["stream"] for item in state["external_blockers"]],
            ["codex_provider_validation", "desktop_bridge"],
        )

    def test_blocker_does_not_implicitly_redirect_the_active_stream(self) -> None:
        state = resolve_coordinator_state(_coordinator_state())

        self.assertEqual(state["active_stream"], "tmcp")
        self.assertNotIn("transition", state)

    def test_prohibited_transition_fails_without_explicit_user_selection(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "tmcp -> codex_provider_validation requires explicit user selection",
        ):
            resolve_coordinator_state(
                _coordinator_state(
                    next_stream="codex_provider_validation",
                    next_status="blocked",
                )
            )

    def test_explicit_selection_records_transition_but_keeps_blocker_visible(
        self,
    ) -> None:
        state = resolve_coordinator_state(
            _coordinator_state(
                next_stream="codex_provider_validation",
                next_status="blocked",
            ),
            explicit_user_stream_selection=True,
        )

        self.assertEqual(state["active_stream"], "codex_provider_validation")
        self.assertEqual(
            state["transition"],
            {
                "from": "tmcp",
                "to": "codex_provider_validation",
                "authorization": "explicit_user_selection",
            },
        )
        self.assertEqual(state["next_action"]["status"], "blocked")

    def test_blocked_lane_cannot_be_presented_as_ready(self) -> None:
        with self.assertRaisesRegex(ValueError, "must have status blocked"):
            resolve_coordinator_state(
                _coordinator_state(next_stream="desktop_bridge"),
                explicit_user_stream_selection=True,
            )

    def test_runtime_state_exposes_coordination_and_recompile_trigger(self) -> None:
        state = derive_runtime_state(
            {
                "objective": "Continue TMCP runtime improvements",
                "coordinator_state": _coordinator_state(),
                "cache_policy": "none",
            },
            source_nodes=[],
            cache_warnings=[],
        )

        self.assertEqual(state["coordination"]["active_stream"], "tmcp")
        self.assertTrue(state["recompile_required"])
        self.assertIn("coordination_state_changed", state["recompile_triggers"])

    def test_receipt_preserves_the_normalized_coordinator_state(self) -> None:
        receipt = build_run_receipt(
            {
                "packet_id": "packet-123",
                "coordinator_state": _coordinator_state(),
                "outcome": "passed",
            },
            created_at="2026-08-04T00:00:00Z",
        )

        self.assertEqual(receipt["coordination"]["active_stream"], "tmcp")
        self.assertEqual(len(receipt["coordination"]["prohibited_lane_transitions"]), 2)

    def test_schema_declares_the_versioned_fail_closed_contract(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["properties"]["schema"]["const"], COORDINATOR_STATE_SCHEMA
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["prohibited_lane_transitions"]["items"]["properties"][
                "unless"
            ]["const"],
            "explicit_user_selection",
        )

    def test_consolidation_receipt_is_versioned_and_normalized(self) -> None:
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        coordination = receipt["coordination"]

        self.assertEqual(receipt["schema"], "tmcp-run-receipt-v0.1")
        self.assertEqual(receipt["packet_id"], "packet-db86e1145471")
        self.assertEqual(
            normalize_coordinator_state(coordination),
            coordination,
        )
        self.assertEqual(
            [item["status"] for item in coordination["source_handoffs"]],
            ["consolidated", "consolidated"],
        )

    def test_current_verification_receipt_carries_fresh_gate_evidence(self) -> None:
        receipt = json.loads(CURRENT_RECEIPT_PATH.read_text(encoding="utf-8"))
        coordination = receipt["coordination"]

        self.assertEqual(receipt["schema"], "tmcp-run-receipt-v0.1")
        self.assertEqual(receipt["packet_id"], "packet-b115bd80a3f5")
        self.assertEqual(
            receipt["outcome"], "tmcp_owned_verification_passed_external_lanes_held"
        )
        self.assertIn(
            "Full unittest discovery: 634 passed, 3 expected skips.",
            receipt["verification_results"],
        )
        self.assertEqual(
            normalize_coordinator_state(coordination),
            coordination,
        )
        self.assertEqual(
            coordination["next_action"]["id"], "coordinator-review-current-state"
        )

    def test_cli_runtime_next_accepts_same_lane_and_rejects_implicit_switch(
        self,
    ) -> None:
        with TestWorkspace() as workspace:
            accepted = workspace.run_cli(
                [
                    "runtime-next",
                    "Continue TMCP runtime improvements",
                    "--coordinator-state",
                    json.dumps(_coordinator_state(), separators=(",", ":")),
                    "--compact",
                ]
            )
            rejected = workspace.run_cli(
                [
                    "runtime-next",
                    "Validate the provider lane",
                    "--coordinator-state",
                    json.dumps(
                        _coordinator_state(
                            next_stream="codex_provider_validation",
                            next_status="blocked",
                        ),
                        separators=(",", ":"),
                    ),
                    "--compact",
                ]
            )

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        accepted_coordination = accepted.json()["coordination"]
        self.assertIsInstance(accepted_coordination, dict)
        assert isinstance(accepted_coordination, dict)
        self.assertEqual(accepted_coordination["active_stream"], "tmcp")
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("requires explicit user selection", rejected.stderr)

    def test_cli_receipt_persists_coordinator_state(self) -> None:
        with TestWorkspace() as workspace:
            completed = workspace.run_cli(
                [
                    "record-receipt",
                    "packet-123",
                    "--coordinator-state",
                    json.dumps(_coordinator_state(), separators=(",", ":")),
                    "--outcome",
                    "passed",
                    "--compact",
                ]
            )
            assert workspace.tmcp_home is not None
            receipt_paths = list(workspace.tmcp_home.rglob("*.json"))
            receipts = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in receipt_paths
                if "receipts" in path.parts
            ]

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["coordination"]["active_stream"], "tmcp")

    def test_coordination_domain_has_no_adapter_storage_or_io_imports(self) -> None:
        source_path = Path(inspect.getfile(coordination_domain))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden_prefixes = (
            "datetime",
            "os",
            "pathlib",
            "scripts",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.services",
            "tmcp_runtime.storage",
        )

        self.assertTrue(
            all(
                not module.startswith(prefix)
                for module in imported_modules
                for prefix in forbidden_prefixes
            )
        )


if __name__ == "__main__":
    unittest.main()
