from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from tests import test_tmcp_mcp_server as helpers


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "kepano-normalization-stability"
).resolve()
HARVEST_INCLUDE_GLOBS = ["**/skills/**/SKILL.md", "**/docs/*.md"]
OBJECTIVE = "Use obsidian-markdown with obsidian-cli"


def _run_read_only(
    server: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    common = {
        "source_path": str(FIXTURE_ROOT),
        "project_path": str(FIXTURE_ROOT),
        "objective": OBJECTIVE,
        "phase": "start",
        "cache_policy": "none",
        "include_globs": HARVEST_INCLUDE_GLOBS,
        "write_artifacts": False,
    }
    harvest = server._harvest_skills(dict(common))
    packet = server._compose_packet(dict(common))
    recompiled = server._runtime_next(
        {
            **common,
            "current_phase": "start",
            "previous_packet_id": packet["packet_id"],
            "previous_packet": packet,
            "output_mode": "full",
        }
    )
    return harvest, packet, recompiled


def _harvest_projection(harvest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": node.get("id"),
            "relative_path": node.get("relative_path"),
            "source_type": node.get("source_type"),
            "behavior_atoms": tuple(node.get("behavior_atoms") or []),
            "guidance_labels": tuple(
                (
                    label.get("id"),
                    tuple(label.get("matched_terms") or []),
                )
                for label in node.get("guidance_labels") or []
                if isinstance(label, dict)
            ),
        }
        for node in harvest["source_nodes"]
    ]


def _packet_projection(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "packet_id": packet["packet_id"],
        "active_atoms": tuple(packet["active_atoms"]),
        "deferred_atoms": tuple(packet["deferred_atoms"]),
        "evidence_citations": tuple(
            (
                citation.get("source"),
                citation.get("path"),
                citation.get("trust"),
                tuple(citation.get("matched_atoms") or []),
            )
            for citation in packet["evidence_citations"]
        ),
        "ignored_sources": tuple(
            (source.get("source"), source.get("reason"))
            for source in packet["ignored_sources"]
        ),
    }


def _signal_projection(node: dict[str, Any]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (
            str(label.get("id") or ""),
            tuple(str(term) for term in label.get("matched_terms") or []),
        )
        for label in node.get("guidance_labels") or []
        if isinstance(label, dict)
    )


def _existing_provenance_projection(
    harvest: dict[str, Any], packet: dict[str, Any]
) -> list[dict[str, Any]]:
    nodes = {
        str(node.get("relative_path")): node
        for node in harvest["source_nodes"]
        if node.get("relative_path")
    }
    selected_paths = {
        str(citation.get("source"))
        for citation in packet["evidence_citations"]
        if citation.get("source")
    }
    deferred_atoms = set(packet["deferred_atoms"])
    trace: list[dict[str, Any]] = []

    for citation in packet["evidence_citations"]:
        source = str(citation.get("source") or "")
        node = nodes.get(source)
        if node is None:
            continue
        for atom in citation.get("matched_atoms") or []:
            trace.append(
                {
                    "decision": "selected",
                    "atom_id": atom,
                    "source": source,
                    "path": citation.get("path"),
                    "capability_kind": node.get("source_type"),
                    "matched_signal": _signal_projection(node),
                    "reason": "evidence_citations",
                }
            )

    for atom in packet["deferred_atoms"]:
        for source, node in nodes.items():
            if source in selected_paths or atom not in node.get("behavior_atoms", []):
                continue
            trace.append(
                {
                    "decision": "deferred",
                    "atom_id": atom,
                    "source": source,
                    "path": node.get("path"),
                    "capability_kind": node.get("source_type"),
                    "matched_signal": _signal_projection(node),
                    "reason": "deferred_atoms",
                }
            )

    ignored_reasons = {
        str(source.get("source")): str(source.get("reason") or "")
        for source in packet["ignored_sources"]
    }
    for source, reason in ignored_reasons.items():
        node = nodes.get(source)
        if node is None:
            continue
        for atom in node.get("behavior_atoms", []):
            if atom in deferred_atoms:
                continue
            trace.append(
                {
                    "decision": "ignored",
                    "atom_id": atom,
                    "source": source,
                    "path": node.get("path"),
                    "capability_kind": node.get("source_type"),
                    "matched_signal": _signal_projection(node),
                    "reason": reason,
                }
            )

    return trace


class TmcpKepanoStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = helpers.load_server_module()

    def test_repeated_read_only_harvest_compose_recompile_is_stable(self) -> None:
        before = {
            path.relative_to(FIXTURE_ROOT).as_posix(): path.read_bytes()
            for path in FIXTURE_ROOT.rglob("*")
            if path.is_file()
        }

        first_harvest, first_packet, first_recompiled = _run_read_only(self.server)
        second_harvest, second_packet, second_recompiled = _run_read_only(self.server)

        self.assertEqual(
            _harvest_projection(first_harvest), _harvest_projection(second_harvest)
        )
        self.assertEqual(
            _packet_projection(first_packet), _packet_projection(second_packet)
        )
        self.assertEqual(
            _packet_projection(first_recompiled["packet"]),
            _packet_projection(second_recompiled["packet"]),
        )
        self.assertEqual(
            first_recompiled["packet_diff"], second_recompiled["packet_diff"]
        )

        first_trace = _existing_provenance_projection(first_harvest, first_packet)
        second_trace = _existing_provenance_projection(second_harvest, second_packet)
        self.assertEqual(first_trace, second_trace)
        self.assertTrue(first_trace)
        for entry in first_trace:
            self.assertTrue(entry["atom_id"])
            self.assertTrue(entry["source"])
            self.assertTrue(entry["path"])
            self.assertTrue(entry["capability_kind"])
            self.assertTrue(entry["matched_signal"])
            self.assertTrue(entry["reason"])

        decisions = {entry["decision"] for entry in first_trace}
        self.assertEqual(decisions, {"selected", "deferred", "ignored"})
        selected_sources = {
            entry["source"] for entry in first_trace if entry["decision"] == "selected"
        }
        self.assertEqual(
            selected_sources,
            {
                "skills/obsidian-cli/SKILL.md",
                "skills/obsidian-markdown/SKILL.md",
            },
        )
        ignored_sources = {
            entry["source"] for entry in first_trace if entry["decision"] == "ignored"
        }
        self.assertEqual(
            ignored_sources,
            {
                "skills/defuddle/SKILL.md",
                "docs/defuddle-standardize.md",
            },
        )

        after = {
            path.relative_to(FIXTURE_ROOT).as_posix(): path.read_bytes()
            for path in FIXTURE_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertFalse((FIXTURE_ROOT / ".tmcp").exists())


if __name__ == "__main__":
    unittest.main()
