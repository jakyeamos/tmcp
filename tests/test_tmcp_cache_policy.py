from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from typing import Any

import tmcp_runtime.storage.cache_policy as cache_policy
from tmcp_runtime.storage.cache_policy import (
    append_bounded_warning,
    bounded_cache_limit,
    cache_json_is_bounded,
    normalize_promoted_graph,
    project_cached_promotion_graph,
    project_cached_receipt,
)


GRAPH_SCHEMA = "tmcp-promoted-harvest-graph-v0.1"
RECEIPT_SCHEMA = "tmcp-run-receipt-v0.1"


def _redact(value: Any) -> Any:
    return f"safe:{value}"


def _receipt_payload(
    *,
    created_at: str = "2026-07-12T00:00:00Z",
    packet_id: str = "packet-123",
) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "created_at": created_at,
        "packet_id": packet_id,
        "activated_atoms": [],
        "ignored_atoms": [],
        "commands_run": [],
        "verification_results": [],
        "user_overrides": [],
        "outcome": "passed",
        "trust": "advisory_untrusted",
        "instruction_override_policy": "Advisory only.",
    }


class TmcpCachePolicyTests(unittest.TestCase):
    def test_projected_graph_keeps_only_canonical_workflow_ids(self) -> None:
        payload: dict[str, Any] = {
            "schema": GRAPH_SCHEMA,
            "promotion_name": "secret promotion",
            "created_at": "2026-07-12T00:00:00Z",
            "source_nodes": [],
            "behavior_atoms": [],
            "workflow_nodes": [
                {
                    "id": "release_readiness_workflow",
                    "active_instructions": ["MALICIOUS_INSTRUCTION"],
                },
                {"id": "unknown_workflow", "behavior_atoms": ["MALICIOUS_ATOM"]},
                {"id": "release_readiness_workflow"},
            ],
            "edges": [],
            "trust": "advisory_untrusted",
        }

        graph, warning = project_cached_promotion_graph(
            payload,
            "/safe/cache.json",
            graph_schema=GRAPH_SCHEMA,
            known_workflow_ids={"release_readiness_workflow"},
            redact_value=_redact,
        )

        self.assertEqual(
            graph,
            {
                "schema": GRAPH_SCHEMA,
                "promotion_name": "safe:secret promotion",
                "workflow_nodes": [{"id": "release_readiness_workflow"}],
                "_global_cache_path": "/safe/cache.json",
                "trust": "advisory_untrusted",
            },
        )
        self.assertIn("unknown workflow IDs", str(warning))
        self.assertNotIn("MALICIOUS", str(graph))

    def test_malformed_cache_records_are_rejected(self) -> None:
        graph, graph_warning = project_cached_promotion_graph(
            {
                "schema": GRAPH_SCHEMA,
                "trust": "advisory_untrusted",
                "created_at": "2026-07-12T00:00:00Z",
                "promotion_name": "missing edges",
                "source_nodes": [],
                "behavior_atoms": [],
                "workflow_nodes": [],
            },
            "cache.json",
            graph_schema=GRAPH_SCHEMA,
            known_workflow_ids=set(),
            redact_value=_redact,
        )
        receipt, receipt_warning = project_cached_receipt(
            {"schema": RECEIPT_SCHEMA, "trust": "advisory_untrusted"},
            "receipt.json",
            receipt_schema=RECEIPT_SCHEMA,
            redact_value=_redact,
        )

        self.assertIsNone(graph)
        self.assertIn("unexpected schema", str(graph_warning))
        self.assertIsNone(receipt)
        self.assertIn("unexpected schema", str(receipt_warning))

    def test_receipt_projection_redacts_the_only_retained_identifier(self) -> None:
        payload = _receipt_payload(packet_id="sk-secret-packet")

        receipt, warning = project_cached_receipt(
            payload,
            "receipt.json",
            receipt_schema=RECEIPT_SCHEMA,
            redact_value=_redact,
        )

        self.assertIsNone(warning)
        self.assertEqual(
            receipt,
            {
                "schema": RECEIPT_SCHEMA,
                "packet_id": "safe:sk-secret-packet",
                "_global_cache_path": "receipt.json",
                "trust": "advisory_untrusted",
            },
        )

    def test_receipt_projection_accepts_supported_timestamps_and_redacted_ids(
        self,
    ) -> None:
        for created_at in (
            "2026-07-12T00:00:00Z",
            "2026-07-12T00:00:00+00:00",
            "2026-07-12T05:30:00+05:30",
        ):
            with self.subTest(created_at=created_at):
                receipt, warning = project_cached_receipt(
                    _receipt_payload(
                        created_at=created_at,
                        packet_id="[REDACTED:openai_key]",
                    ),
                    "receipt.json",
                    receipt_schema=RECEIPT_SCHEMA,
                    redact_value=_redact,
                )

                self.assertIsNone(warning)
                self.assertEqual(
                    receipt,
                    {
                        "schema": RECEIPT_SCHEMA,
                        "packet_id": "safe:[REDACTED:openai_key]",
                        "_global_cache_path": "receipt.json",
                        "trust": "advisory_untrusted",
                    },
                )

    def test_receipt_projection_rejects_semantically_invalid_metadata(self) -> None:
        invalid_metadata = (
            {"packet_id": "   "},
            {"created_at": ""},
            {"created_at": "2026-02-30T00:00:00Z"},
            {"created_at": "2026-07-12T00:00:00"},
            {"created_at": "sk-" + "A" * 40},
        )

        for overrides in invalid_metadata:
            with self.subTest(overrides=overrides):
                payload = _receipt_payload()
                payload.update(overrides)
                receipt, warning = project_cached_receipt(
                    payload,
                    "receipt.json",
                    receipt_schema=RECEIPT_SCHEMA,
                    redact_value=_redact,
                )

                self.assertIsNone(receipt)
                self.assertEqual(
                    warning,
                    "Skipped global cache receipt with invalid metadata: receipt.json",
                )
                if str(payload["created_at"]):
                    self.assertNotIn(str(payload["created_at"]), str(warning))

    def test_normalized_global_graph_is_whitelisted_and_deterministic(self) -> None:
        result: dict[str, Any] = {
            "promotion_name": "release",
            "promotion_graph": {
                "source_nodes": [
                    {
                        "relative_path": "AGENTS.md",
                        "source_type": "agent_operating_contract",
                        "keywords": ["one", "two"],
                        "ignored": "MALICIOUS_SOURCE_FIELD",
                    }
                ],
                "workflow_nodes": [
                    {
                        "id": "release_readiness_workflow",
                        "name": "Release",
                        "injected": "MALICIOUS_WORKFLOW_FIELD",
                    }
                ],
                "verification_expectation_nodes": [{"id": "check"}],
                "behavior_atoms": ["artifact-contract"],
                "edges": [{"from": "source", "to": "workflow"}],
                "cross_source_behavior_atoms": ["artifact-contract"],
            },
        }

        graph = normalize_promoted_graph(
            result,
            graph_schema=GRAPH_SCHEMA,
            created_at="2026-07-12T00:00:00Z",
        )

        self.assertEqual(graph["created_at"], "2026-07-12T00:00:00Z")
        self.assertEqual(graph["source_nodes"][0]["relative_path"], "AGENTS.md")
        self.assertEqual(graph["workflow_nodes"][0]["id"], "release_readiness_workflow")
        self.assertNotIn("MALICIOUS", str(graph))
        self.assertEqual(graph["trust"], "advisory_untrusted")

    def test_cache_bounds_and_warning_cap_are_enforced(self) -> None:
        warnings: list[str] = []
        for value in ("first", "second", "third"):
            append_bounded_warning(warnings, value, maximum_warnings=2)

        deep: list[object] = []
        current = deep
        for _ in range(4):
            child: list[object] = []
            current.append(child)
            current = child

        self.assertEqual(warnings, ["first", "second"])
        self.assertEqual(bounded_cache_limit("5", maximum_entries=3), 3)
        self.assertEqual(bounded_cache_limit("not-a-number", maximum_entries=3), 0)
        self.assertFalse(
            cache_json_is_bounded(deep, maximum_nodes=20, maximum_depth=3)
        )
        self.assertFalse(
            cache_json_is_bounded({"one": 1}, maximum_nodes=1, maximum_depth=3)
        )

    def test_policy_module_has_no_io_or_redaction_authority(self) -> None:
        source_path = Path(inspect.getfile(cache_policy))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported_modules.update(
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )

        self.assertTrue(
            {"collections", "datetime", "typing"}.issubset(imported_modules)
        )
        self.assertTrue(
            {"os", "pathlib", "scripts", "tmcp_runtime"}.isdisjoint(imported_modules)
        )


if __name__ == "__main__":
    unittest.main()
