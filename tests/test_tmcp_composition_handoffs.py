from __future__ import annotations

import copy
import unittest
from pathlib import Path
from typing import Any

from scripts.schema_contract_support import assert_matches_schema
from tmcp_runtime.domain import compositional_intelligence as ci
from tmcp_runtime.domain.composition_handoffs import (
    build_handoff_contracts,
    handoff_identity_projection,
    relationship_id_for,
)
from tmcp_runtime.domain.composition_runtime import evaluate_composition_handoffs


ROOT = Path(__file__).resolve().parents[1]


def _role(
    node_id: str,
    *,
    inputs: list[str],
    outputs: list[str],
    exit_gates: list[str],
    citation: str,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "role": f"{node_id} role",
        "inputs": inputs,
        "outputs": outputs,
        "phase_affinity": ["discovery"],
        "entry_gates": [],
        "exit_gates": exit_gates,
        "context_cost": 100,
        "covers": [],
        "citations": [citation],
    }


class CompositionHandoffContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.producer_citation = "slice-" + "a" * 20
        self.consumer_citation = "slice-" + "b" * 20
        self.edge_citation = "slice-" + "c" * 20
        self.roles = [
            _role(
                "producer",
                inputs=["task objective"],
                outputs=["evidence brief"],
                exit_gates=["Evidence brief approved"],
                citation=self.producer_citation,
            ),
            _role(
                "consumer",
                inputs=["evidence brief"],
                outputs=["verified result"],
                exit_gates=["Verification complete"],
                citation=self.consumer_citation,
            ),
        ]
        self.source_digests = {"producer": "a" * 64, "consumer": "b" * 64}
        self.slice_digests = {
            self.producer_citation: "c" * 64,
            self.consumer_citation: "d" * 64,
            self.edge_citation: "e" * 64,
        }

    def _edge(self, relation: str, *, reverse: bool = False) -> dict[str, Any]:
        source, target = (
            ("consumer", "producer")
            if reverse
            else (
                "producer",
                "consumer",
            )
        )
        return {
            "from": source,
            "to": target,
            "type": relation,
            "citations": [self.edge_citation],
            "rationale": f"{source} {relation} {target}",
        }

    def test_ordering_edges_become_source_cited_producer_consumer_contracts(
        self,
    ) -> None:
        edges = [
            self._edge("requires", reverse=True),
            self._edge("precedes"),
            self._edge("enables"),
            self._edge("verifies", reverse=True),
            self._edge("produces"),
            self._edge("consumes", reverse=True),
            self._edge("complements"),
            self._edge("conflicts_with"),
        ]

        contracts = build_handoff_contracts(
            self.roles,
            edges,
            graph_digest="f" * 32,
            source_digests_by_node=self.source_digests,
            slice_digests_by_id=self.slice_digests,
        )

        self.assertEqual(
            {contract["relationship_type"] for contract in contracts},
            {"requires", "precedes", "enables", "verifies", "produces", "consumes"},
        )
        self.assertEqual(len(contracts), 6)
        for contract in contracts:
            self.assertEqual(contract["producer_node_id"], "producer")
            self.assertEqual(contract["consumer_node_id"], "consumer")
            self.assertEqual(contract["required_inputs"], ["evidence brief"])
            self.assertEqual(contract["produced_outputs"], ["evidence brief"])
            self.assertEqual(
                contract["producer_exit_gates"], ["Evidence brief approved"]
            )
            self.assertEqual(
                contract["citations"],
                sorted(
                    [
                        self.producer_citation,
                        self.consumer_citation,
                        self.edge_citation,
                    ]
                ),
            )
            self.assertEqual(contract["trust"], "advisory_untrusted")
            self.assertRegex(contract["handoff_id"], r"^handoff-[a-f0-9]{20}$")
            self.assertRegex(
                contract["relationship_id"], r"^relationship-[a-f0-9]{16}$"
            )

    def test_contracts_are_deterministic_and_handoff_ids_bind_role_semantics(
        self,
    ) -> None:
        edges = [self._edge("enables"), self._edge("verifies", reverse=True)]
        first = build_handoff_contracts(
            self.roles,
            edges,
            graph_digest="f" * 32,
            source_digests_by_node=self.source_digests,
            slice_digests_by_id=self.slice_digests,
        )
        reordered = build_handoff_contracts(
            list(reversed(self.roles)),
            list(reversed(edges)),
            graph_digest="f" * 32,
            source_digests_by_node=self.source_digests,
            slice_digests_by_id=self.slice_digests,
        )
        changed_roles = copy.deepcopy(self.roles)
        changed_roles[0]["outputs"] = ["reviewed evidence brief"]
        changed = build_handoff_contracts(
            changed_roles,
            edges,
            graph_digest="f" * 32,
            source_digests_by_node=self.source_digests,
            slice_digests_by_id=self.slice_digests,
        )

        self.assertEqual(first, reordered)
        self.assertNotEqual(
            {contract["handoff_id"] for contract in first},
            {contract["handoff_id"] for contract in changed},
        )
        self.assertEqual(
            first[0]["relationship_id"],
            relationship_id_for(
                next(
                    edge
                    for edge in edges
                    if edge["type"] == first[0]["relationship_type"]
                )
            ),
        )

    def test_duplicate_content_edges_keep_distinct_operational_handoffs(
        self,
    ) -> None:
        roles = [
            _role(
                "producer-a",
                inputs=["objective"],
                outputs=["brief"],
                exit_gates=["Brief approved"],
                citation=self.producer_citation,
            ),
            _role(
                "producer-b",
                inputs=["objective"],
                outputs=["brief"],
                exit_gates=["Brief approved"],
                citation=self.producer_citation,
            ),
            _role(
                "consumer-a",
                inputs=["brief"],
                outputs=["result"],
                exit_gates=["Result approved"],
                citation=self.consumer_citation,
            ),
            _role(
                "consumer-b",
                inputs=["brief"],
                outputs=["result"],
                exit_gates=["Result approved"],
                citation=self.consumer_citation,
            ),
        ]
        source_digests = {
            "producer-a": "a" * 64,
            "producer-b": "a" * 64,
            "consumer-a": "b" * 64,
            "consumer-b": "b" * 64,
        }
        edges = [
            {
                "from": "producer-a",
                "to": "consumer-a",
                "type": "produces",
                "citations": [self.edge_citation],
            },
            {
                "from": "producer-b",
                "to": "consumer-b",
                "type": "produces",
                "citations": [self.edge_citation],
            },
        ]

        contracts = build_handoff_contracts(
            roles,
            edges,
            graph_digest="f" * 32,
            source_digests_by_node=source_digests,
            slice_digests_by_id=self.slice_digests,
        )

        self.assertEqual(len(contracts), 2)
        self.assertEqual(
            {contract["consumer_node_id"] for contract in contracts},
            {"consumer-a", "consumer-b"},
        )
        self.assertEqual(len({contract["handoff_id"] for contract in contracts}), 2)
        self.assertEqual(
            handoff_identity_projection(
                contracts,
                source_digests_by_node=source_digests,
                slice_digests_by_id=self.slice_digests,
            )[0]["producer_source_digest"],
            "a" * 64,
        )

    def test_plan_attaches_consumer_contracts_and_bridge_metadata(self) -> None:
        nodes = [
            {
                "id": "governing",
                "source_type": "agent_operating_contract",
                "relative_path": "AGENTS.md",
                "title": "Governing instructions",
                "excerpt": (
                    "Read evidence before modifying the project. Governing role "
                    "exits when scope is approved and produces reviewed task scope."
                ),
                "behavior_atoms": [],
                "routing_metadata": {},
            },
            {
                "id": "research",
                "source_type": "skill_definition",
                "relative_path": "skills/research/SKILL.md",
                "title": "Research skill",
                "excerpt": (
                    "Produce a source-backed evidence brief. Research role exits "
                    "when the evidence brief is approved."
                ),
                "behavior_atoms": [],
                "routing_metadata": {},
            },
        ]
        preflight = ci.prepare_composition(nodes, "Research with governing scope")
        slices = {
            str(item["source_node_id"]): item
            for item in preflight["candidate_source_slices"]
        }
        governing = _role(
            "governing",
            inputs=["task objective"],
            outputs=["bounded task"],
            exit_gates=["Scope approved"],
            citation=str(slices["governing"]["slice_id"]),
        )
        governing["phase_affinity"] = ["start"]
        research = _role(
            "research",
            inputs=["bounded task"],
            outputs=["evidence brief"],
            exit_gates=["Evidence brief approved"],
            citation=str(slices["research"]["slice_id"]),
        )
        proposal = {
            "schema": ci.SEMANTIC_PROPOSAL_SCHEMA,
            "preflight_id": preflight["preflight_id"],
            "current_phase": "discovery",
            "task_model": {
                "deliverables": ["Evidence brief"],
                "success_criteria": ["Evidence is cited"],
                "constraints": ["Preserve governing scope"],
                "subgoals": ["Research"],
                "evidence_needs": ["Citations"],
            },
            "skill_roles": [governing, research],
            "relationships": [
                {
                    "from": "governing",
                    "to": "research",
                    "type": "enables",
                    "citations": [
                        slices["governing"]["slice_id"],
                        slices["research"]["slice_id"],
                    ],
                    "rationale": "Bounded scope enables research.",
                }
            ],
            "coverage": {
                "facets": ["Evidence is cited"],
                "unresolved_gaps": [],
            },
            "trust": ci.COMPOSITION_TRUST,
        }

        plan = ci.build_composition_plan(proposal, preflight)
        changed_proposal = copy.deepcopy(proposal)
        changed_proposal["skill_roles"][0]["outputs"] = ["reviewed task scope"]
        changed = ci.build_composition_plan(changed_proposal, preflight)
        contract = plan["handoff_contracts"][0]
        research_stage = next(
            stage
            for stage in plan["ordered_stages"]
            if stage["node_ids"] == ["research"]
        )
        research_bridge = research_stage["bridge_instructions"][0]

        self.assertEqual(research_stage["handoff_contracts"], [contract])
        self.assertEqual(research_bridge["role"], "research role")
        self.assertEqual(research_bridge["required_inputs"], ["bounded task"])
        self.assertEqual(research_bridge["produced_outputs"], ["evidence brief"])
        self.assertEqual(research_bridge["exit_gates"], ["Evidence brief approved"])
        self.assertEqual(research_bridge["handoff_ids"], [contract["handoff_id"]])
        self.assertEqual(
            plan["provenance"]["graph_digest"], changed["provenance"]["graph_digest"]
        )
        self.assertNotEqual(plan["composition_plan_id"], changed["composition_plan_id"])
        self.assertNotEqual(
            contract["handoff_id"], changed["handoff_contracts"][0]["handoff_id"]
        )
        evaluation = evaluate_composition_handoffs(plan, {})
        self.assertEqual(
            evaluation["catalog"],
            [{**contract, "consumer_stage_id": research_stage["stage_id"]}],
        )
        self.assertEqual(evaluation["invalid_contracts"], [])
        assert_matches_schema(
            plan,
            ROOT / "schemas" / "tmcp-composition-plan-v0.1.schema.json",
        )


if __name__ == "__main__":
    unittest.main()
