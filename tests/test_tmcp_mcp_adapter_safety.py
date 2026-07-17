from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tests import test_tmcp_mcp_server as helpers
import tmcp_runtime.adapters.aios as aios_adapter
from tmcp_runtime.adapters.cli import run_cli
from tmcp_runtime.storage import ArtifactStorageError


class TmcpMcpAdapterSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_aios_adapter_explicit_missing_returns_clear_error(self) -> None:
        original_root = getattr(self.server, "AIOS_ROOT")
        setattr(self.server, "AIOS_ROOT", Path("/tmp/tmcp-aios-definitely-missing"))
        try:
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )
        finally:
            setattr(self.server, "AIOS_ROOT", original_root)

        self.assertFalse(result["ok"])
        self.assertEqual(result["adapter"], "aios")
        self.assertIn("AIOS_ROOT", result["error"])
        self.assertIn("--adapter standalone", result["remediation"])

    def test_status_reports_aios_unconfigured_as_optional(self) -> None:
        original_root = getattr(self.server, "AIOS_ROOT")
        setattr(self.server, "AIOS_ROOT", None)
        try:
            result = self.server._call_tool("tmcp_status", {})
        finally:
            setattr(self.server, "AIOS_ROOT", original_root)

        self.assertTrue(result["standalone"]["available"])
        self.assertFalse(result["aios_adapter"]["available"])
        self.assertFalse(result["aios_adapter"]["configured"])
        self.assertIsNone(result["aios_adapter"]["aios_root"])

    def test_composition_redaction_preserves_only_canonical_digest_fields(
        self,
    ) -> None:
        digest = hashlib.sha256(b"public composition provenance").hexdigest()
        secret = "sk-" + "S" * 40

        result = self.server._redact_result(
            {
                "schema": "tmcp-composition-preflight-v0.1",
                "candidate_source_slices": [
                    {
                        "source_digest": digest,
                        "slice_digest": digest,
                        "content_digest": digest,
                    }
                ],
                "arbitrary_value": digest,
                "graph_digest": secret,
                "secret": secret,
            },
            preserve_composition_digests=True,
        )

        source_slice = result["candidate_source_slices"][0]
        self.assertEqual(source_slice["source_digest"], digest)
        self.assertEqual(source_slice["slice_digest"], digest)
        self.assertEqual(
            source_slice["content_digest"],
            "[REDACTED:long_high_entropy]",
        )
        self.assertEqual(
            result["arbitrary_value"],
            "[REDACTED:long_high_entropy]",
        )
        self.assertEqual(result["graph_digest"], "[REDACTED:openai_key]")
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result["redaction_summary"]["long_high_entropy"], 2)
        self.assertEqual(result["redaction_summary"]["openai_key"], 2)

        receipt, receipt_redactions = self.server._redact_receipt(
            {
                "schema": "tmcp-run-receipt-v0.1",
                "content_digests": [digest],
                "task_identity": {"content_digest": digest},
                "secret": secret,
            }
        )
        self.assertEqual(receipt["content_digests"], [digest])
        self.assertEqual(
            receipt["task_identity"]["content_digest"],
            "[REDACTED:long_high_entropy]",
        )
        self.assertNotIn(secret, json.dumps(receipt))
        self.assertEqual(receipt_redactions["long_high_entropy"], 1)
        self.assertEqual(receipt_redactions["openai_key"], 1)

    def test_runtime_user_payload_cannot_claim_a_digest_identity_location(self) -> None:
        secret = hashlib.sha256(b"user-controlled secret material").hexdigest()

        result = self.server._redact_result(
            {
                "schema": "tmcp-recompiled-packet-v0.1",
                "packet": {},
                "agent_proposals": [
                    {
                        "action": "unsupported",
                        "content_digest": secret,
                    }
                ],
                "validated_changes": [
                    {
                        "action": "add_route",
                        "content_digest": secret,
                    }
                ],
            },
            preserve_composition_digests=True,
        )

        self.assertEqual(
            result["agent_proposals"][0]["content_digest"],
            "[REDACTED:long_high_entropy]",
        )
        self.assertEqual(
            result["validated_changes"][0]["content_digest"],
            "[REDACTED:long_high_entropy]",
        )

    def test_cli_composition_packet_round_trips_through_full_recompile(
        self,
    ) -> None:
        def invoke(argv: list[str]) -> dict[str, Any]:
            output = io.StringIO()
            errors = io.StringIO()
            status = run_cli(
                argv,
                call_tool=self.server._call_tool,
                stdout=output,
                stderr=errors,
            )
            self.assertEqual(status, 0, errors.getvalue())
            return json.loads(output.getvalue())

        objective = "Implement and verify a reliable change"
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "AGENTS.md").write_text(
                "# Rules\n\nRead before modifying and verify results.\n",
                encoding="utf-8",
            )
            (project / "SKILL.md").write_text(
                "# Verification Skill\n\nImplement the task and run focused verification.\n",
                encoding="utf-8",
            )
            common = [
                objective,
                "--project-path",
                str(project),
                "--source-path",
                str(project),
                "--phase",
                "start",
                "--compact",
            ]
            preflight = invoke(["prepare-composition", *common])
            slices = preflight["candidate_source_slices"]
            self.assertIsInstance(slices, list)
            by_role = {
                str(item["source_role"]): item
                for item in slices
                if isinstance(item, dict)
            }
            governing = by_role["governing_instruction"]
            skill = by_role["active_skill"]
            for item in (governing, skill):
                self.assertEqual(len(str(item["source_digest"])), 64)
                self.assertEqual(len(str(item["slice_digest"])), 64)
                self.assertNotIn("[REDACTED:", str(item["source_digest"]))

            criterion = "Focused verification passes"

            def role(
                item: dict[str, object],
                name: str,
                *,
                covers: list[str] | None = None,
            ) -> dict[str, object]:
                covered = covers or []
                return {
                    "node_id": item["source_node_id"],
                    "role": name,
                    "inputs": ["task objective"],
                    "outputs": ["validated handoff"],
                    "phase_affinity": ["start"],
                    "entry_gates": [],
                    "exit_gates": [
                        criterion if covered else "Governing constraints are applied"
                    ],
                    "context_cost": 100,
                    "covers": covered,
                    "citations": [item["slice_id"]],
                }

            proposal = {
                "schema": "tmcp-semantic-proposal-v0.1",
                "preflight_id": preflight["preflight_id"],
                "current_phase": "start",
                "task_model": {
                    "deliverables": ["Verified change"],
                    "success_criteria": [criterion],
                    "constraints": ["Preserve governing instructions"],
                    "subgoals": ["Implement", "Verify"],
                    "evidence_needs": ["Focused verification"],
                },
                "skill_roles": [
                    role(governing, "governing constraints"),
                    role(skill, "implementation verifier", covers=[criterion]),
                ],
                "relationships": [
                    {
                        "from": governing["source_node_id"],
                        "to": skill["source_node_id"],
                        "type": "enables",
                        "citations": [
                            governing["slice_id"],
                            skill["slice_id"],
                        ],
                        "rationale": (
                            "Governing constraints enable safe implementation."
                        ),
                    }
                ],
                "coverage": {
                    "facets": [criterion],
                    "unresolved_gaps": [],
                },
                "trust": "advisory_untrusted",
            }
            packet = invoke(
                [
                    "compose-packet",
                    *common,
                    "--cache-policy",
                    "none",
                    "--semantic-proposal",
                    json.dumps(proposal),
                ]
            )
            citations = packet["evidence_citations"]
            self.assertIsInstance(citations, list)
            self.assertTrue(
                all(
                    len(str(item["content_digest"])) == 64
                    and "[REDACTED:" not in str(item["content_digest"])
                    for item in citations
                    if isinstance(item, dict)
                )
            )

            recompiled = invoke(
                [
                    "runtime-next",
                    objective,
                    "--project-path",
                    str(project),
                    "--source-path",
                    str(project),
                    "--cache-policy",
                    "none",
                    "--output-mode",
                    "full",
                    "--previous-packet",
                    json.dumps(packet),
                    "--compact",
                ]
            )

        self.assertTrue(recompiled["ok"])
        recompiled_packet = recompiled["packet"]
        self.assertIsInstance(recompiled_packet, dict)
        self.assertNotEqual(
            recompiled_packet.get("composition_plan_status"),
            "stale_source_provenance",
        )
        runtime_validation = dict(
            dict(recompiled_packet.get("composition_diagnostics") or {}).get(
                "runtime_source_validation"
            )
            or {}
        )
        self.assertFalse(
            any(
                error.get("code") == "composition_source_content_changed"
                for error in runtime_validation.get("errors", [])
                if isinstance(error, dict)
            )
        )

    def test_aios_auto_missing_falls_back_to_standalone(self) -> None:
        original_root = getattr(self.server, "AIOS_ROOT")
        setattr(self.server, "AIOS_ROOT", Path("/tmp/tmcp-aios-definitely-missing"))
        try:
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "auto",
                },
            )
        finally:
            setattr(self.server, "AIOS_ROOT", original_root)

        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "standalone")
        self.assertEqual(result["packet"]["schema"], "tmcp-skill-packet-v0.2")

    def test_aios_auto_stays_standalone_when_the_adapter_is_available(self) -> None:
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                self.server,
                "_run_aios",
            ) as run_aios,
        ):
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "auto",
                },
            )

        run_aios.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "standalone")

    def test_aios_rejects_sensitive_command_arguments_before_execution(self) -> None:
        secret = "sk-" + "J" * 40
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                aios_adapter.subprocess,
                "run",
            ) as run,
        ):
            result = self.server._run_aios(
                ["tmcp", "explain", secret, "--project-path", f"/tmp/{secret}"]
            )

        run.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("redaction_summary", result)

    def test_aios_explicitly_uses_the_optional_adapter(self) -> None:
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                self.server,
                "_run_aios",
                return_value={"ok": True, "adapter": "aios", "data": {}},
            ) as run_aios,
        ):
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )

        run_aios.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "aios")

    def test_explain_explicit_aios_rejects_sensitive_values_before_execution(
        self,
    ) -> None:
        secret = "sk-" + "K" * 40
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                aios_adapter.subprocess,
                "run",
            ) as run,
        ):
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": f"Explain {secret}",
                    "project_path": f"/tmp/{secret}/project",
                    "adapter": "aios",
                },
            )

        run.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("redaction_summary", result)

    def test_explain_aios_payloads_are_redacted_before_returning(self) -> None:
        secret = "sk-" + "B" * 40
        output_dir = f"/tmp/{secret}/aios-output"
        project_path = f"/tmp/{secret}/project"
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                self.server,
                "_run_aios",
                return_value={
                    "ok": True,
                    "adapter": "aios",
                    "detail": secret,
                    "output_dir": output_dir,
                    "artifact_paths": {"packet": output_dir},
                },
            ),
        ):
            success = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": project_path,
                    "adapter": "aios",
                    "compose": True,
                },
            )
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                self.server,
                "_run_aios",
                return_value={
                    "ok": False,
                    "adapter": "aios",
                    "command": ["aios", secret],
                    "stdout": secret,
                    "stderr": output_dir,
                },
            ),
        ):
            failure = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )

        self.assertTrue(success["ok"])
        self.assertFalse(failure["ok"])
        self.assertNotIn(secret, json.dumps({"success": success, "failure": failure}))
        self.assertNotIn(
            output_dir, json.dumps({"success": success, "failure": failure})
        )
        self.assertIn("redaction_summary", success)
        self.assertIn("redaction_summary", failure)

    def test_status_and_doctor_redact_sensitive_configured_paths(self) -> None:
        secret = "sk-" + "C" * 40
        original_aios_root = getattr(self.server, "AIOS_ROOT")
        original_plugin_root = getattr(self.server, "PLUGIN_ROOT")
        setattr(self.server, "AIOS_ROOT", Path("/tmp") / secret / "aios")
        setattr(self.server, "PLUGIN_ROOT", Path("/tmp") / secret / "plugin")
        try:
            status = self.server._call_tool("tmcp_status", {})
            doctor = self.server._call_tool("tmcp_doctor", {"client": "codex"})
        finally:
            setattr(self.server, "AIOS_ROOT", original_aios_root)
            setattr(self.server, "PLUGIN_ROOT", original_plugin_root)

        rendered = json.dumps({"status": status, "doctor": doctor})
        self.assertNotIn(secret, rendered)
        self.assertIn("[REDACTED:", rendered)

    def test_explain_aios_timeout_returns_a_redacted_structured_error(self) -> None:
        secret = "sk-" + "D" * 40
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                aios_adapter.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(["aios", secret], 120),
            ),
        ):
            result = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain packet",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "TimeoutExpired")
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("redaction_summary", result)

    def test_runtime_next_redacts_project_paths_after_internal_work(self) -> None:
        secret = "sk-" + "E" * 40
        project_path = f"/tmp/{secret}/project"
        delta = self.server._runtime_next(
            {
                "objective": "Implement a reliable project packet",
                "project_path": project_path,
                "source_path": project_path,
                "cache_policy": "none",
            }
        )
        full = self.server._runtime_next(
            {
                "objective": "Implement a reliable project packet",
                "project_path": project_path,
                "source_path": project_path,
                "cache_policy": "none",
                "output_mode": "full",
                "previous_packet": {
                    "packet_id": "prior-packet",
                    "project_path": project_path,
                },
            }
        )

        self.assertNotIn(secret, json.dumps({"delta": delta, "full": full}))
        self.assertIn("redaction_summary", delta)
        self.assertIn("redaction_summary", full)

    def test_runtime_next_requires_a_real_path_after_redacted_packet_output(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "explicit source_path or project_path"):
            self.server._runtime_next(
                {
                    "objective": "Implement a reliable project packet",
                    "cache_policy": "none",
                    "output_mode": "full",
                    "previous_packet": {
                        "packet_id": "prior-packet",
                        "project_path": "/tmp/[REDACTED:opaque_token]/project",
                    },
                }
            )

    def test_public_compose_and_standalone_explain_redact_project_paths(self) -> None:
        secret = "sk-" + "F" * 40
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / secret / "project"
            project_path.mkdir(parents=True)
            compose = self.server._call_tool(
                "tmcp_compose_packet",
                {
                    "objective": "Implement a reliable project packet",
                    "project_path": str(project_path),
                    "source_path": str(project_path),
                    "cache_policy": "none",
                },
            )
            standalone = self.server._call_tool(
                "tmcp_explain",
                {
                    "objective": "Explain a reliable project packet",
                    "project_path": str(project_path),
                    "source_path": str(project_path),
                    "adapter": "standalone",
                    "compose": True,
                },
            )

        self.assertNotIn(
            secret, json.dumps({"compose": compose, "standalone": standalone})
        )
        self.assertIn("redaction_summary", compose)
        self.assertIn("redaction_summary", standalone)

    def test_review_auto_never_uses_the_aios_adapter(self) -> None:
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                self.server,
                "_run_aios",
            ) as run_aios,
            patch.object(
                self.server,
                "artifact_persistence_available",
                return_value=False,
            ),
        ):
            result = self.server._call_tool(
                "expert_rubric_review_plan",
                {
                    "objective": "Review release safety",
                    "project_path": "/tmp/project",
                    "harvest_sources": False,
                    "write_artifacts": False,
                },
            )

        run_aios.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "standalone")

    def test_review_explicit_aios_write_is_denied_before_external_execution(
        self,
    ) -> None:
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                self.server,
                "_run_aios",
            ) as run_aios,
        ):
            with self.assertRaisesRegex(ArtifactStorageError, "write_artifacts=false"):
                self.server._call_tool(
                    "expert_rubric_review_plan",
                    {
                        "objective": "Review release safety",
                        "project_path": "/tmp/project",
                        "adapter": "aios",
                    },
                )

        run_aios.assert_not_called()

    def test_review_explicit_aios_missing_keeps_adapter_remediation(self) -> None:
        original_root = getattr(self.server, "AIOS_ROOT")
        setattr(self.server, "AIOS_ROOT", Path("/tmp/tmcp-aios-definitely-missing"))
        try:
            result = self.server._call_tool(
                "expert_rubric_review_plan",
                {
                    "objective": "Review release safety",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                },
            )
        finally:
            setattr(self.server, "AIOS_ROOT", original_root)

        self.assertFalse(result["ok"])
        self.assertEqual(result["adapter"], "aios")
        self.assertIn("--adapter standalone", result["remediation"])

    def test_review_explicit_aios_preview_redacts_and_omits_output_directory(
        self,
    ) -> None:
        secret = "sk-" + "A" * 40
        output_dir = f"/tmp/{secret}/review"
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                self.server,
                "_run_aios",
                return_value={
                    "ok": True,
                    "adapter": "aios",
                    "detail": secret,
                    "output_dir": output_dir,
                    "artifact_paths": {"report": output_dir},
                },
            ) as run_aios,
        ):
            result = self.server._call_tool(
                "expert_rubric_review_plan",
                {
                    "objective": f"Review {secret}",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                    "write_artifacts": False,
                    "output_dir": output_dir,
                },
            )

        command = run_aios.call_args.args[0]
        self.assertIn("--no-write-artifacts", command)
        self.assertNotIn("--output-dir", command)
        self.assertNotIn(output_dir, command)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("output_dir", result)
        self.assertEqual(result["artifact_paths"], {})

    def test_review_explicit_aios_rejects_sensitive_evidence_before_execution(
        self,
    ) -> None:
        secret = "sk-" + "L" * 40
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                aios_adapter.subprocess,
                "run",
            ) as run,
        ):
            result = self.server._call_tool(
                "expert_rubric_review_plan",
                {
                    "objective": "Review release safety",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                    "write_artifacts": False,
                    "evidence_json": json.dumps({"token": secret}),
                },
            )

        run.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result["artifact_paths"], {})

    def test_review_explicit_aios_rejects_escaped_sensitive_evidence_before_execution(
        self,
    ) -> None:
        escaped_secret = "sk-" + "\\u004d" * 40
        with (
            patch.object(self.server, "_aios_available", return_value=True),
            patch.object(
                aios_adapter.subprocess,
                "run",
            ) as run,
        ):
            result = self.server._call_tool(
                "expert_rubric_review_plan",
                {
                    "objective": "Review release safety",
                    "project_path": "/tmp/project",
                    "adapter": "aios",
                    "write_artifacts": False,
                    "evidence_json": '{"token":"' + escaped_secret + '"}',
                },
            )

        run.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertIn("redaction_summary", result)
        self.assertEqual(result["artifact_paths"], {})

    def test_status_omits_artifact_write_when_secure_persistence_is_unavailable(
        self,
    ) -> None:
        with patch.object(
            self.server,
            "artifact_persistence_available",
            return_value=False,
        ):
            result = self.server._call_tool("tmcp_status", {})

        standalone = result["standalone"]
        self.assertFalse(standalone["artifact_persistence"]["available"])
        self.assertNotIn("artifact_write", standalone["capabilities"])


if __name__ == "__main__":
    unittest.main()
