from __future__ import annotations

import copy
import json
import unittest

from tmcp_runtime.domain.composition_phase_capsules import (
    CONTEXT_ACCOUNTING_POLICY,
    CONTEXT_ACCOUNTING_SCHEMA,
    PhaseCapsuleError,
    build_phase_capsule_accounting,
)
from tmcp_runtime.domain.harvest_nodes import content_digest_for


def _sources() -> dict[str, dict[str, str]]:
    return {
        "govern": {
            "source_node_id": "node-govern",
            "source_slice_id": "slice-govern",
            "source_role": "governing_instruction",
            "content": "Preserve governing constraints and source authority. " * 180,
        },
        "discover": {
            "source_node_id": "node-discover",
            "source_slice_id": "slice-discover",
            "source_role": "active_skill",
            "content": "Discover bounded implementation evidence before editing. " * 180,
        },
        "verify": {
            "source_node_id": "node-verify",
            "source_slice_id": "slice-verify",
            "source_role": "active_skill",
            "content": "Verify the completed behavior with reproducible evidence. " * 180,
        },
    }


def _preflight(
    sources: dict[str, dict[str, str]] | list[dict[str, str]],
) -> dict[str, object]:
    candidates = []
    records = (
        [{"skill_id": skill_id, **source} for skill_id, source in sources.items()]
        if isinstance(sources, dict)
        else sources
    )
    for source in records:
        skill_id = source["skill_id"]
        content = source["content"]
        source_digest = source.get("source_digest") or content_digest_for(content)
        slice_digest = content_digest_for(content)
        candidates.append(
            {
                "slice_id": source["source_slice_id"],
                "source_node_id": source["source_node_id"],
                "source_role": source["source_role"],
                "source_digest": source_digest,
                "slice_digest": slice_digest,
                "content": content,
                "char_start": int(source.get("char_start") or 0),
                "char_end": int(source.get("char_end") or len(content)),
                "title": f"{skill_id} source",
            }
        )
    return {
        "objective": "Discover, implement, and verify a constrained change.",
        "semantic_proposal_contract": {
            "schema": "tmcp-semantic-proposal-v0.1",
            "trust": "advisory_untrusted",
        },
        "behavior_manifest_index": {"schema": "tmcp-behavior-manifest-index-v0.1"},
        "candidate_source_slices": candidates,
    }


def _multi_slice_sources(*, edited: bool = False) -> list[dict[str, object]]:
    sources = _sources()
    first = "Discover source evidence before changing implementation behavior. " * 80
    second = "Record the implementation handoff and its reproducible constraints. " * 80
    if edited:
        second += " A cited source edit changes this identity."
    combined = first + second
    discover_digest = content_digest_for(combined)
    return [
        {"skill_id": skill_id, **source}
        for skill_id, source in sources.items()
        if skill_id != "discover"
    ] + [
        {
            "skill_id": "discover",
            "source_node_id": "node-discover",
            "source_slice_id": "slice-discover-first",
            "source_role": "active_skill",
            "source_digest": discover_digest,
            "content": first,
            "char_start": 0,
            "char_end": len(first),
        },
        {
            "skill_id": "discover",
            "source_node_id": "node-discover",
            "source_slice_id": "slice-discover-second",
            "source_role": "active_skill",
            "source_digest": discover_digest,
            "content": second,
            "char_start": len(first),
            "char_end": len(combined),
        },
    ]


def _projection() -> dict[str, object]:
    handoff = {
        "handoff_id": "handoff-discover-verify",
        "producer_skill_id": "discover",
        "consumer_skill_id": "verify",
        "relationship_type": "produces",
        "required_inputs": ["discovery evidence"],
        "produced_outputs": ["implementation handoff"],
        "producer_exit_gates": ["discovery evidence is available"],
    }
    return {
        "composition_plan_id": "plan-example",
        "composition_plan_digest": "plan-digest-example",
        "graph_digest": "graph-digest-example",
        "stages": [
            {
                "stage_id": "stage-1",
                "order": 1,
                "phase": "discovery",
                "status": "active",
                "active_skill_ids": ["discover"],
                "entry_conditions": ["objective is bounded"],
                "bridge_instructions": [
                    {
                        "skill_id": "discover",
                        "instruction": "Find evidence for the next phase.",
                    }
                ],
            },
            {
                "stage_id": "stage-2",
                "order": 2,
                "phase": "verification",
                "status": "deferred",
                "active_skill_ids": ["verify"],
                "entry_conditions": ["discovery evidence is available"],
                "bridge_instructions": [
                    {
                        "skill_id": "verify",
                        "instruction": "Verify the produced handoff.",
                    }
                ],
            },
        ],
        "typed_edges": [
            {
                "source_skill_id": "discover",
                "target_skill_id": "verify",
                "relationship_type": "produces",
            }
        ],
        "handoff_contracts": [handoff],
    }


def _accounting(
    *,
    sources: dict[str, dict[str, str]] | None = None,
    projection: dict[str, object] | None = None,
    handoff_payloads: dict[str, object] | None = None,
) -> dict[str, object]:
    source_records = sources or _sources()
    return build_phase_capsule_accounting(
        task_model={
            "deliverables": ["verified constrained change"],
            "success_criteria": ["reproducible verification"],
        },
        preflight=_preflight(source_records),
        source_projection=projection or _projection(),
        source_contents=source_records,
        runtime_envelope={"packet_id": "packet-example", "session_mode": "isolated"},
        handoff_payloads=handoff_payloads
        or {"handoff-discover-verify": {"evidence_ref": "artifact:example"}},
    )


class CompositionPhaseCapsuleTests(unittest.TestCase):
    def test_builds_deterministic_phase_scoped_accounting(self) -> None:
        source_records = _sources()
        source_records["verify"]["source_digest"] = content_digest_for(
            source_records["verify"]["content"] + " full source provenance"
        )
        result = _accounting(sources=source_records)
        reordered_sources = dict(reversed(list(copy.deepcopy(source_records).items())))
        reordered_preflight = _preflight(reordered_sources)
        reordered_preflight["candidate_source_slices"] = list(
            reversed(reordered_preflight["candidate_source_slices"])
        )
        reordered_projection = _projection()
        reordered_projection["stages"] = list(reversed(reordered_projection["stages"]))
        reordered = build_phase_capsule_accounting(
            task_model={
                "deliverables": ["verified constrained change"],
                "success_criteria": ["reproducible verification"],
            },
            preflight=reordered_preflight,
            source_projection=reordered_projection,
            source_contents=reordered_sources,
            runtime_envelope={"packet_id": "packet-example", "session_mode": "isolated"},
            handoff_payloads={
                "handoff-discover-verify": {"evidence_ref": "artifact:example"}
            },
        )

        self.assertEqual(result, reordered)
        self.assertEqual(result["schema"], CONTEXT_ACCOUNTING_SCHEMA)
        self.assertEqual(result["policy"], CONTEXT_ACCOUNTING_POLICY)
        self.assertEqual(
            result["runtime_envelope"],
            {"packet_id": "packet-example", "session_mode": "isolated"},
        )
        self.assertEqual(
            result["compiled_context_tokens"], result["runtime_peak_context_tokens"]
        )
        self.assertEqual(
            result["naive_context_tokens"], result["naive_union_context_tokens"]
        )
        self.assertIsInstance(result["context_ratio"], float)
        self.assertLessEqual(result["context_ratio"], 0.75)
        self.assertEqual(
            result["same_host_transcript_tokens"],
            result["preflight_discovery_tokens"]
            + sum(item["estimated_tokens"] for item in result["phase_capsules"]),
        )
        self.assertEqual(
            result["preflight_capsule"]["capsule"]["candidate_source_slices"][0][
                "source_role"
            ],
            "governing_instruction",
        )

        first, second = result["phase_capsules"]
        self.assertEqual(first["source_skill_ids"], ["govern", "discover"])
        self.assertEqual(second["source_skill_ids"], ["govern", "verify"])
        self.assertFalse(first["incoming_handoff_digests"])
        self.assertEqual(len(second["incoming_handoff_digests"]), 1)
        self.assertEqual(first["capsule"]["objective"], _preflight(_sources())["objective"])
        self.assertEqual(first["capsule"]["stage"]["phase"], "discovery")
        self.assertEqual(second["capsule"]["stage"]["phase"], "verification")
        self.assertNotIn("status", first["capsule"]["stage"])
        self.assertNotIn("handoff_contracts", second["capsule"]["stage"])
        self.assertNotIn("runtime_envelope", first["capsule"])
        self.assertNotIn("composition_identity", first["capsule"])
        self.assertTrue(
            all(
                set(source) == {"skill_id", "source_role", "content"}
                for source in first["capsule"]["sources"]
            )
        )
        self.assertEqual(
            second["capsule"]["incoming_handoffs"],
            [
                {
                    "handoff_id": "handoff-discover-verify",
                    "producer_skill_id": "discover",
                    "required_inputs": ["discovery evidence"],
                    "produced_outputs": ["implementation handoff"],
                    "producer_exit_gates": ["discovery evidence is available"],
                    "payload": {"evidence_ref": "artifact:example"},
                }
            ],
        )
        naive_union = result["naive_union_capsule"]["capsule"]
        self.assertNotIn("stages", naive_union)
        self.assertNotIn("typed_edges", naive_union)
        self.assertNotIn("handoffs", naive_union)
        self.assertNotIn("composition_identity", naive_union)
        self.assertEqual(
            [item["skill_id"] for item in naive_union["sources"]],
            ["govern", "discover", "verify"],
        )
        self.assertEqual(
            json.loads(second["canonical_json"]), second["capsule"]
        )

    def test_source_content_edit_changes_phase_and_accounting_identity(self) -> None:
        original = _accounting()
        edited_sources = copy.deepcopy(_sources())
        edited_sources["verify"]["content"] += " A source edit changes this phase."
        edited = _accounting(sources=edited_sources)

        self.assertNotEqual(
            original["phase_capsules"][1]["capsule_digest"],
            edited["phase_capsules"][1]["capsule_digest"],
        )
        self.assertNotEqual(
            original["naive_union_capsule_digest"],
            edited["naive_union_capsule_digest"],
        )
        self.assertNotEqual(
            original["context_accounting_digest"],
            edited["context_accounting_digest"],
        )

    def test_keeps_every_cited_slice_for_a_multi_chunk_skill(self) -> None:
        sources = _multi_slice_sources()
        result = build_phase_capsule_accounting(
            task_model={"deliverables": ["verified constrained change"]},
            preflight=_preflight(sources),
            source_projection=_projection(),
            source_contents=sources,
            runtime_envelope={"packet_id": "packet-example", "session_mode": "isolated"},
        )
        first_phase = result["phase_capsules"][0]
        discover_slice_ids = {
            "slice-discover-first",
            "slice-discover-second",
        }
        self.assertTrue(discover_slice_ids.issubset(first_phase["source_slice_ids"]))
        self.assertEqual(
            {
                source["content"].strip()
                for source in sources
                if source["skill_id"] == "discover"
            },
            {
                source["content"]
                for source in first_phase["capsule"]["sources"]
                if source["source_role"] == "active_skill"
            },
        )
        self.assertTrue(
            all(
                set(source) == {"skill_id", "source_role", "content"}
                for source in first_phase["capsule"]["sources"]
            )
        )
        self.assertTrue(
            all(
                set(source) == {"skill_id", "source_role", "content"}
                for source in result["naive_union_capsule"]["capsule"]["sources"]
            )
        )
        reordered = build_phase_capsule_accounting(
            task_model={"deliverables": ["verified constrained change"]},
            preflight={
                **_preflight(list(reversed(sources))),
                "candidate_source_slices": list(
                    reversed(_preflight(list(reversed(sources)))["candidate_source_slices"])
                ),
            },
            source_projection=_projection(),
            source_contents=list(reversed(sources)),
            runtime_envelope={"packet_id": "packet-example", "session_mode": "isolated"},
        )
        self.assertEqual(result, reordered)
        edited = build_phase_capsule_accounting(
            task_model={"deliverables": ["verified constrained change"]},
            preflight=_preflight(_multi_slice_sources(edited=True)),
            source_projection=_projection(),
            source_contents=_multi_slice_sources(edited=True),
            runtime_envelope={"packet_id": "packet-example", "session_mode": "isolated"},
        )
        self.assertNotEqual(
            result["phase_capsules"][0]["capsule_digest"],
            edited["phase_capsules"][0]["capsule_digest"],
        )
        self.assertNotEqual(
            result["context_accounting_digest"], edited["context_accounting_digest"]
        )

    def test_stage_slice_closure_omits_uncited_chunks_from_runtime_capsules(self) -> None:
        sources = _multi_slice_sources()
        projection = _projection()
        projection["stage_source_slice_ids"] = {
            "stage-1": {
                "node-govern": ["slice-govern"],
                "node-discover": ["slice-discover-first"],
            },
            "stage-2": {
                "node-govern": ["slice-govern"],
                "node-verify": ["slice-verify"],
            },
        }
        result = build_phase_capsule_accounting(
            task_model={"deliverables": ["verified constrained change"]},
            preflight=_preflight(sources),
            source_projection=projection,
            source_contents=sources,
            runtime_envelope={"packet_id": "packet-example", "session_mode": "isolated"},
        )
        first_phase = result["phase_capsules"][0]
        self.assertIn("slice-discover-first", first_phase["source_slice_ids"])
        self.assertNotIn("slice-discover-second", first_phase["source_slice_ids"])

        edited_sources = _multi_slice_sources(edited=True)
        edited = build_phase_capsule_accounting(
            task_model={"deliverables": ["verified constrained change"]},
            preflight=_preflight(edited_sources),
            source_projection=projection,
            source_contents=edited_sources,
            runtime_envelope={"packet_id": "packet-example", "session_mode": "isolated"},
        )
        self.assertEqual(
            [
                source["content"]
                for source in first_phase["capsule"]["sources"]
            ],
            [
                source["content"]
                for source in edited["phase_capsules"][0]["capsule"]["sources"]
            ],
        )
        self.assertEqual(
            first_phase["estimated_tokens"],
            edited["phase_capsules"][0]["estimated_tokens"],
        )
        self.assertEqual(
            result["naive_union_capsule_digest"],
            edited["naive_union_capsule_digest"],
        )
        self.assertNotEqual(
            result["preflight_capsule_digest"], edited["preflight_capsule_digest"]
        )

    def test_stage_slice_closure_cannot_omit_or_expand_active_sources(self) -> None:
        projection = _projection()
        projection["stage_source_slice_ids"] = {
            "stage-1": {"node-govern": ["slice-govern"]},
            "stage-2": {
                "node-govern": ["slice-govern"],
                "node-verify": ["slice-verify"],
            },
        }
        with self.assertRaisesRegex(PhaseCapsuleError, "active and governing"):
            build_phase_capsule_accounting(
                task_model={"deliverables": ["verified constrained change"]},
                preflight=_preflight(_sources()),
                source_projection=projection,
                source_contents=_sources(),
            )

    def test_handoff_contract_and_payload_changes_affect_consumer_capsule(self) -> None:
        original = _accounting()
        changed_projection = _projection()
        changed_projection["handoff_contracts"][0]["required_inputs"] = [
            "revised discovery evidence"
        ]
        changed_contract = _accounting(projection=changed_projection)
        changed_payload = _accounting(
            handoff_payloads={
                "handoff-discover-verify": {"evidence_ref": "artifact:revised"}
            }
        )

        self.assertNotEqual(
            original["phase_capsules"][1]["incoming_handoff_digests"],
            changed_contract["phase_capsules"][1]["incoming_handoff_digests"],
        )
        self.assertNotEqual(
            original["phase_capsules"][1]["capsule_digest"],
            changed_contract["phase_capsules"][1]["capsule_digest"],
        )
        self.assertNotEqual(
            original["phase_capsules"][1]["incoming_handoff_digests"],
            changed_payload["phase_capsules"][1]["incoming_handoff_digests"],
        )
        self.assertNotEqual(
            original["phase_capsules"][1]["capsule_digest"],
            changed_payload["phase_capsules"][1]["capsule_digest"],
        )
        self.assertEqual(
            original["naive_union_capsule_digest"],
            changed_contract["naive_union_capsule_digest"],
        )
        self.assertEqual(
            original["naive_union_capsule_digest"],
            changed_payload["naive_union_capsule_digest"],
        )
        self.assertNotEqual(
            original["context_accounting_digest"],
            changed_payload["context_accounting_digest"],
        )

    def test_compacts_equivalent_handoffs_without_losing_any_identity(self) -> None:
        projection = _projection()
        duplicate = copy.deepcopy(projection["handoff_contracts"][0])
        duplicate["handoff_id"] = "handoff-discover-verify-secondary"
        projection["handoff_contracts"].append(duplicate)

        result = _accounting(
            projection=projection,
            handoff_payloads={
                "handoff-discover-verify": {"evidence_ref": "artifact:example"},
                "handoff-discover-verify-secondary": {
                    "evidence_ref": "artifact:example"
                },
            },
        )

        self.assertEqual(
            len(result["phase_capsules"][1]["incoming_handoff_digests"]), 2
        )
        self.assertEqual(
            len(set(result["phase_capsules"][1]["incoming_handoff_digests"])), 2
        )
        self.assertEqual(
            result["phase_capsules"][1]["capsule"]["incoming_handoffs"],
            [
                {
                    "handoff_id": "handoff-discover-verify",
                    "equivalent_handoff_ids": [
                        "handoff-discover-verify-secondary"
                    ],
                    "producer_skill_id": "discover",
                    "required_inputs": ["discovery evidence"],
                    "produced_outputs": ["implementation handoff"],
                    "producer_exit_gates": ["discovery evidence is available"],
                    "payload": {"evidence_ref": "artifact:example"},
                }
            ],
        )

        distinct_payloads = _accounting(
            projection=projection,
            handoff_payloads={
                "handoff-discover-verify": {"evidence_ref": "artifact:one"},
                "handoff-discover-verify-secondary": {
                    "evidence_ref": "artifact:two"
                },
            },
        )
        self.assertEqual(
            [
                handoff["handoff_id"]
                for handoff in distinct_payloads["phase_capsules"][1]["capsule"][
                    "incoming_handoffs"
                ]
            ],
            ["handoff-discover-verify", "handoff-discover-verify-secondary"],
        )
        self.assertTrue(
            all(
                "equivalent_handoff_ids" not in handoff
                for handoff in distinct_payloads["phase_capsules"][1]["capsule"][
                    "incoming_handoffs"
                ]
            )
        )

    def test_rejects_empty_stage_list_and_forged_candidate_digest(self) -> None:
        no_stages = _projection()
        no_stages["stages"] = []
        with self.assertRaisesRegex(PhaseCapsuleError, "at least one stage"):
            _accounting(projection=no_stages)

        preflight = _preflight(_sources())
        preflight["candidate_source_slices"][0]["slice_digest"] = "0" * 64
        with self.assertRaisesRegex(PhaseCapsuleError, "slice_digest"):
            build_phase_capsule_accounting(
                task_model={"deliverables": ["verified constrained change"]},
                preflight=preflight,
                source_projection=_projection(),
                source_contents=_sources(),
            )


if __name__ == "__main__":
    unittest.main()
