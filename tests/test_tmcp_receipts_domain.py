from __future__ import annotations

import ast
import copy
import inspect
import json
import unittest
from pathlib import Path

import tmcp_runtime.domain.receipts as receipts_domain
from tmcp_runtime.domain.receipts import (
    RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
    RECEIPT_TRUST,
    RUN_RECEIPT_SCHEMA,
    build_recorded_receipt_result,
    build_receipt_template,
    build_run_receipt,
)


class TmcpReceiptsDomainTests(unittest.TestCase):
    def test_build_run_receipt_normalizes_inputs_without_mutating_them(self) -> None:
        arguments: dict[str, object] = {
            "packet_id": " packet-123 ",
            "activated_atoms": ["verify", 7, ""],
            "ignored_atoms": ["defer"],
            "commands_run": ["python3 -m unittest", 0],
            "verification_results": ["passed"],
            "user_overrides": "not-a-list",
            "outcome": "passed",
        }
        original_arguments = copy.deepcopy(arguments)

        receipt = build_run_receipt(
            arguments,
            created_at="2026-07-12T16:00:00Z",
        )

        self.assertEqual(arguments, original_arguments)
        self.assertEqual(
            receipt,
            {
                "schema": RUN_RECEIPT_SCHEMA,
                "created_at": "2026-07-12T16:00:00Z",
                "packet_id": "packet-123",
                "activated_atoms": ["verify", "7"],
                "ignored_atoms": ["defer"],
                "commands_run": ["python3 -m unittest", "0"],
                "verification_results": ["passed"],
                "user_overrides": [],
                "outcome": "passed",
                "trust": RECEIPT_TRUST,
                "instruction_override_policy": RECEIPT_INSTRUCTION_OVERRIDE_POLICY,
            },
        )

    def test_build_run_receipt_requires_a_nonempty_packet_id(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "tmcp_record_receipt requires packet_id.",
        ):
            build_run_receipt({"packet_id": "   "}, created_at="2026-07-12T00:00:00Z")

    def test_build_run_receipt_adds_structured_composition_evidence(self) -> None:
        arguments: dict[str, object] = {
            "packet_id": "packet-123",
            "recipe_id": " recipe-123 ",
            "task_identity": {"primary": "compound_task", "secondary": ["review"]},
            "graph_digest": " graph-123 ",
            "content_digests": ["a" * 64, "b" * 64],
            "selected_skill_ids": ["research", "writing", "review"],
            "phase_trace": [
                {"phase": "research", "status": "passed"},
                "not-structured",
            ],
            "gate_results": [{"gate_id": "safety", "passed": True}],
            "quality_metrics": {
                "synergy_lift": 0.12,
                "compiler_lift": 0.08,
                "order_lift": 0.06,
            },
            "cost_metrics": {"context_ratio": 0.70},
            "composition_fixture_id": " fixture-a ",
            "benchmark_control_input_digest": "a" * 64,
            "benchmark_execution_recipe_digest": "b" * 64,
        }
        original = copy.deepcopy(arguments)

        receipt = build_run_receipt(
            arguments,
            created_at="2026-07-12T16:00:00Z",
        )

        self.assertEqual(arguments, original)
        self.assertEqual(receipt["recipe_id"], "recipe-123")
        self.assertEqual(receipt["graph_digest"], "graph-123")
        self.assertEqual(receipt["content_digests"], ["a" * 64, "b" * 64])
        self.assertEqual(receipt["composition_fixture_id"], "fixture-a")
        self.assertEqual(receipt["benchmark_control_input_digest"], "a" * 64)
        self.assertEqual(receipt["benchmark_execution_recipe_digest"], "b" * 64)
        self.assertEqual(
            receipt["selected_skill_ids"], ["research", "writing", "review"]
        )
        self.assertEqual(
            receipt["phase_trace"], [{"phase": "research", "status": "passed"}]
        )
        self.assertEqual(receipt["quality_metrics"]["synergy_lift"], 0.12)
        arguments["task_identity"]["secondary"].append("later-change")  # type: ignore[index]
        self.assertEqual(receipt["task_identity"]["secondary"], ["review"])

    def test_receipt_template_copies_activated_atoms(self) -> None:
        activated_atoms = ["behavior-verification"]

        template = build_receipt_template(
            packet_id="packet-123",
            activated_atoms=activated_atoms,
        )
        activated_atoms.append("later-change")

        self.assertEqual(
            template,
            {
                "schema": RUN_RECEIPT_SCHEMA,
                "packet_id": "packet-123",
                "activated_atoms": ["behavior-verification"],
                "ignored_atoms": [],
                "commands_run": [],
                "verification_results": [],
                "user_overrides": [],
                "outcome": "",
            },
        )

    def test_receipt_template_accepts_optional_composition_fields(self) -> None:
        composition_fields = {
            "recipe_id": "recipe-123",
            "graph_digest": "graph-123",
            "content_digests": ["c" * 64],
            "selected_skill_ids": ["research", "review"],
            "composition_fixture_id": "fixture-a",
        }

        template = build_receipt_template(
            packet_id="packet-123",
            activated_atoms=["behavior-verification"],
            composition_fields=composition_fields,
        )

        self.assertEqual(template["recipe_id"], "recipe-123")
        self.assertEqual(template["graph_digest"], "graph-123")
        self.assertEqual(template["content_digests"], ["c" * 64])
        self.assertEqual(template["selected_skill_ids"], ["research", "review"])
        self.assertEqual(template["composition_fixture_id"], "fixture-a")

    def test_receipt_schema_keeps_composition_fields_optional(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "tmcp-run-receipt-v0.1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        composition_fields = {
            "recipe_id",
            "task_identity",
            "graph_digest",
            "content_digests",
            "selected_skill_ids",
            "phase_trace",
            "gate_results",
            "quality_metrics",
            "cost_metrics",
            "composition_fixture_id",
        }

        self.assertTrue(composition_fields.issubset(schema["properties"]))
        self.assertTrue(composition_fields.isdisjoint(schema["required"]))

    def test_recorded_receipt_result_uses_only_safe_public_fields(self) -> None:
        safe_receipt: dict[str, object] = {
            "packet_id": "[REDACTED:openai_key]",
            "outcome": "passed",
            "commands_run": ["must not be returned"],
        }
        redactions = {"openai_key": 1}
        original_receipt = copy.deepcopy(safe_receipt)
        original_redactions = copy.deepcopy(redactions)

        result = build_recorded_receipt_result(
            safe_receipt,
            redacted_receipt_path="[REDACTED:path]",
            redaction_summary=redactions,
        )

        self.assertEqual(safe_receipt, original_receipt)
        self.assertEqual(redactions, original_redactions)
        self.assertEqual(
            result,
            {
                "ok": True,
                "schema": RUN_RECEIPT_SCHEMA,
                "packet_id": "[REDACTED:openai_key]",
                "outcome": "passed",
                "artifact_paths": {"receipt_json": "[REDACTED:path]"},
                "trust": RECEIPT_TRUST,
                "redaction_summary": {"openai_key": 1},
            },
        )

    def test_receipt_domain_has_no_adapter_storage_or_io_imports(self) -> None:
        source_path = Path(inspect.getfile(receipts_domain))
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
            "hashlib",
            "os",
            "pathlib",
            "scripts",
            "shutil",
            "subprocess",
            "tmcp_runtime.safety",
            "tmcp_runtime.storage",
            "uuid",
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
