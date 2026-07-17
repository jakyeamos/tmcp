from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_composition_benchmark import prepare_benchmark
from scripts.assemble_composition_benchmark import assemble_control_plan
from scripts.schema_contract_support import assert_matches_schema
from tmcp_runtime.domain.composition_benchmark_protocol import (
    build_benchmark_preparation,
    fixture_source_nodes,
    prepare_fixture_preflight,
    validate_benchmark_run_plan,
)
from tmcp_runtime.domain.composition_benchmark_recipes import (
    _compiled_context_accounting,
)
from tmcp_runtime.domain.composition_benchmark_replay import (
    SEMANTIC_PROPOSAL_BUNDLE_SCHEMA,
    build_benchmark_control_plan,
    validate_benchmark_control_plan,
)
from tmcp_runtime.domain.composition_benchmark_replay_support import _role_projection
from tmcp_runtime.domain.composition_benchmark_sources import (
    graph_digest_for_observation,
    validate_fixture_skill_sources,
    validate_source_slice_bindings,
)
from tmcp_runtime.domain.composition_preflight import stable_digest
from tmcp_runtime.domain.harvest_nodes import content_digest_for
from tmcp_runtime.storage.artifacts import (
    ArtifactStorageError,
    AtomicArtifactStore,
    artifact_persistence_available,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCHEMAS = ROOT / "schemas"
ROUTING_PATH = FIXTURES / "composition_routing_golden_v0_6.json"
BEHAVIORAL_PATH = FIXTURES / "composition_behavioral_fixtures_v0_6.json"


def _payload(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must contain an object")
    return payload


def _proposal_for_fixture(
    fixture: dict[str, object],
    *,
    objective: str,
    selected_skill_ids: list[str],
) -> dict[str, object]:
    """Return a test-only host proposal with citations from its prepared input."""

    preflight = prepare_fixture_preflight(fixture=fixture, objective=objective)
    node_by_skill = {
        str(node["skill_id"]): str(node["id"]) for node in fixture_source_nodes(fixture)
    }
    slice_ids_by_node: dict[str, list[str]] = {}
    for item in preflight["candidate_source_slices"]:
        slice_ids_by_node.setdefault(str(item["source_node_id"]), []).append(
            str(item["slice_id"])
        )
    for slice_ids in slice_ids_by_node.values():
        slice_ids.sort()
    phases = ("discovery", "implementation", "verification", "final")
    roles = []
    for index, skill_id in enumerate(selected_skill_ids):
        node_id = node_by_skill[skill_id]
        roles.append(
            {
                "node_id": node_id,
                "role": f"{skill_id} benchmark role",
                "inputs": [
                    "bounded objective"
                    if index == 0
                    else f"{selected_skill_ids[index - 1]} handoff"
                ],
                "outputs": [f"{skill_id} handoff"],
                "phase_affinity": [phases[index]],
                "entry_gates": [],
                "exit_gates": [f"{skill_id} evidence is available"],
                "context_cost": 0,
                "covers": ["benchmark outcome"],
                "citations": slice_ids_by_node[node_id],
            }
        )
    relationships = []
    for relationship in fixture["expected_relationships"]:
        source_id = str(relationship["source_id"])
        target_id = str(relationship["target_id"])
        if source_id not in node_by_skill or target_id not in node_by_skill:
            continue
        if source_id not in selected_skill_ids or target_id not in selected_skill_ids:
            continue
        source_node_id = node_by_skill[source_id]
        target_node_id = node_by_skill[target_id]
        relationships.append(
            {
                "from": source_node_id,
                "to": target_node_id,
                "type": relationship["relation"],
                "citations": sorted(
                    set(slice_ids_by_node[source_node_id])
                    | set(slice_ids_by_node[target_node_id])
                ),
                "rationale": "Fixture host proposal uses prepared source evidence.",
            }
        )
    return {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": preflight["preflight_id"],
        "current_phase": "start",
        "task_model": {
            "deliverables": ["Benchmark outcome"],
            "success_criteria": ["benchmark outcome"],
            "constraints": ["Preserve prepared source authority"],
            "subgoals": ["Produce each compiled handoff"],
            "evidence_needs": ["Source-backed verification evidence"],
        },
        "skill_roles": roles,
        "relationships": relationships,
        "coverage": {"facets": ["benchmark outcome"], "unresolved_gaps": []},
        "trust": "advisory_untrusted",
    }


def _semantic_proposal_bundle(
    plan: dict[str, object],
    routing: dict[str, object],
    behavioral: dict[str, object],
) -> dict[str, object]:
    fixtures_by_id = {
        str(fixture["fixture_id"]): fixture for fixture in behavioral["fixtures"]
    }
    fixtures_by_domain = {
        str(fixture["domain"]): fixture for fixture in behavioral["fixtures"]
    }
    routing_proposals = []
    for case in routing["cases"]:
        fixture = fixtures_by_domain[str(case["domain"])]
        routing_proposals.append(
            {
                "case_id": case["case_id"],
                "semantic_proposal": _proposal_for_fixture(
                    fixture,
                    objective=str(case["objective"]),
                    selected_skill_ids=list(case["expected_skill_ids"]),
                ),
            }
        )
    behavioral_proposals = []
    for fixture_id, fixture in fixtures_by_id.items():
        behavioral_proposals.append(
            {
                "fixture_id": fixture_id,
                "semantic_proposal": _proposal_for_fixture(
                    fixture,
                    objective=str(fixture["objective"]),
                    selected_skill_ids=list(fixture["expected_skill_ids"]),
                ),
            }
        )
    return {
        "schema": SEMANTIC_PROPOSAL_BUNDLE_SCHEMA,
        "run_manifest_id": plan["run_manifest_id"],
        "run_manifest_digest": plan["run_manifest_digest"],
        "routing_proposals": routing_proposals,
        "behavioral_proposals": behavioral_proposals,
    }


def _replayed_source_slices(
    control: dict[str, object],
    *,
    workspace_root: str,
) -> list[dict[str, object]]:
    replay = control["replay"]
    preflight = replay["preflight"]
    candidates = {
        str(item["slice_id"]): item for item in preflight["candidate_source_slices"]
    }
    result = []
    for binding in control["source_bindings"]:
        for cited_slice in binding["cited_slices"]:
            candidate = candidates[str(cited_slice["slice_id"])]
            result.append(
                {
                    "skill_id": binding["skill_id"],
                    "source_node_id": binding["source_node_id"],
                    "relative_path": binding["relative_path"],
                    "source_path": f"{workspace_root}/{binding['relative_path']}",
                    "content": candidate["content"],
                    "char_start": candidate["char_start"],
                    "char_end": candidate["char_end"],
                    "slice_id": candidate["slice_id"],
                    "source_digest": candidate["source_digest"],
                    "slice_digest": candidate["slice_digest"],
                    "content_digest": candidate["source_digest"],
                }
            )
    return result


def _candidate_slice(
    node: dict[str, object],
    *,
    content: str,
    char_start: int,
    char_end: int,
) -> dict[str, object]:
    source_digest = str(node["content_digest"])
    slice_digest = content_digest_for(content)
    source_node_id = str(node["id"])
    return {
        "slice_id": "slice-"
        + stable_digest(
            [source_digest, slice_digest, char_start, char_end, source_node_id], 20
        ),
        "source_node_id": source_node_id,
        "source_digest": source_digest,
        "slice_digest": slice_digest,
        "source_role": "active_skill",
        "content": content,
        "char_start": char_start,
        "char_end": char_end,
    }


class CompositionBenchmarkProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routing = _payload(ROUTING_PATH)
        cls.behavioral = _payload(BEHAVIORAL_PATH)

    def test_preparation_is_schema_valid_and_hides_score_oracles(self) -> None:
        plan, artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )

        assert_matches_schema(
            plan,
            SCHEMAS / "tmcp-composition-benchmark-run-plan-v0.1.schema.json",
        )
        validate_benchmark_run_plan(
            plan,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        serialized_plan = json.dumps(plan, sort_keys=True)
        for forbidden in (
            "expected_skill_ids",
            "expected_order",
            "expected_relationships",
            "quality_rubric",
        ):
            self.assertNotIn(forbidden, serialized_plan)
        self.assertEqual(plan["protocol"]["cache_policy"], "none")
        self.assertFalse(plan["protocol"]["automatic_tool_execution"])
        self.assertEqual(len(plan["fixture_workspaces"]), 5)
        self.assertGreaterEqual(len(plan["routing_requests"]), 20)
        self.assertEqual(len(plan["behavioral_requests"]), 5)
        self.assertIn("benchmark-run-plan.json", artifacts)
        self.assertTrue(
            all(
                path.startswith("fixtures/") for path in artifacts if "/skills/" in path
            )
        )
        self.assertTrue(
            all(
                path.startswith("host-inputs/")
                for path in artifacts
                if path.endswith("-preflight.json")
            )
        )

    def test_protocol_identity_is_root_independent_and_content_sensitive(self) -> None:
        first, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        second, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        first_fixture = self.behavioral["fixtures"][0]
        first_nodes = fixture_source_nodes(
            first_fixture,
            logical_workspace_root=Path("/one/fixture-root"),
        )
        second_nodes = fixture_source_nodes(
            first_fixture,
            logical_workspace_root=Path("/another/fixture-root"),
        )
        changed = copy.deepcopy(self.behavioral)
        changed["fixtures"][0]["skill_sources"][0]["content"] += "\nChanged."
        changed_plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=changed,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            [node["id"] for node in first_nodes],
            [node["id"] for node in second_nodes],
        )
        self.assertEqual(first["run_manifest_id"], second["run_manifest_id"])
        self.assertNotEqual(
            first["run_manifest_digest"], changed_plan["run_manifest_digest"]
        )

    def test_benchmark_preflights_expose_every_active_fixture_source(self) -> None:
        for fixture in self.behavioral["fixtures"]:
            preflight = prepare_fixture_preflight(
                fixture=fixture,
                objective=str(fixture["objective"]),
            )
            self.assertEqual(
                {
                    item["source_node_id"]
                    for item in preflight["candidate_source_slices"]
                },
                {node["id"] for node in fixture_source_nodes(fixture)},
            )
            self.assertEqual(
                preflight["diagnostics"]["semantic_evidence"]["selection_policy"],
                "all_active_source_candidates",
            )

    def test_role_binding_keeps_multiple_bounded_citations_for_one_skill(self) -> None:
        fixture = copy.deepcopy(self.behavioral["fixtures"][0])
        fixture["skill_sources"][0]["content"] = (
            "# Discovery\n"
            + ("Capture source-backed constraints before editing.\n" * 90)
            + "# Handoff\n"
            + ("Record the produced handoff and exit gate.\n" * 90)
        )
        nodes = fixture_source_nodes(fixture)
        nodes_by_skill = {str(node["skill_id"]): node for node in nodes}
        first = nodes_by_skill[str(fixture["skill_sources"][0]["skill_id"])]
        second = nodes_by_skill[str(fixture["skill_sources"][1]["skill_id"])]
        first_content = str(fixture["skill_sources"][0]["content"])
        split_at = first_content.index("# Handoff")
        first_slices = [
            _candidate_slice(
                first,
                content=first_content[:split_at].strip(),
                char_start=0,
                char_end=split_at,
            ),
            _candidate_slice(
                first,
                content=first_content[split_at:].strip(),
                char_start=split_at,
                char_end=len(first_content),
            ),
        ]
        second_content = str(fixture["skill_sources"][1]["content"])
        second_slice = _candidate_slice(
            second,
            content=second_content,
            char_start=0,
            char_end=len(second_content),
        )
        plan = {
            "skill_roles": [
                {"node_id": first["id"], "citations": [first_slices[0]["slice_id"]]},
                {"node_id": second["id"], "citations": [second_slice["slice_id"]]},
            ],
            "typed_edges": [
                {
                    "from": first["id"],
                    "to": second["id"],
                    "type": "produces",
                    "citations": [first_slices[1]["slice_id"], second_slice["slice_id"]],
                }
            ],
            "handoff_contracts": [],
            "ordered_stages": [
                {
                    "node_ids": [first["id"]],
                    "bridge_instructions": [
                        {"node_id": first["id"], "citations": [first_slices[1]["slice_id"]]}
                    ],
                },
                {
                    "node_ids": [second["id"]],
                    "bridge_instructions": [
                        {"node_id": second["id"], "citations": [second_slice["slice_id"]]}
                    ],
                },
            ],
        }
        preflight = {"candidate_source_slices": [*first_slices, second_slice]}
        bindings, selected, _edges = _role_projection(
            fixture,
            {"composition_plan": plan},
            preflight,
        )
        self.assertEqual(selected, [first["skill_id"], second["skill_id"]])
        self.assertEqual(
            [item["slice_id"] for item in bindings[0]["cited_slices"]],
            [item["slice_id"] for item in first_slices],
        )
        self.assertEqual(
            [item["slice_digest"] for item in bindings[0]["cited_slices"]],
            [item["slice_digest"] for item in first_slices],
        )
        reordered, _selected, _reordered_edges = _role_projection(
            fixture,
            {"composition_plan": plan},
            {"candidate_source_slices": list(reversed(preflight["candidate_source_slices"]))},
        )
        self.assertEqual(bindings, reordered)

    def test_control_plan_replays_compiler_and_derives_real_variant_inputs(
        self,
    ) -> None:
        plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        proposals = _semantic_proposal_bundle(plan, self.routing, self.behavioral)
        assert_matches_schema(
            proposals,
            SCHEMAS / "tmcp-composition-benchmark-semantic-proposals-v0.1.schema.json",
        )
        controls = build_benchmark_control_plan(
            run_plan=plan,
            semantic_proposals=proposals,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        assert_matches_schema(
            controls,
            SCHEMAS / "tmcp-composition-benchmark-control-plan-v0.1.schema.json",
        )

        self.assertEqual(len(controls["routing_controls"]), 25)
        self.assertEqual(len(controls["behavioral_controls"]), 5)
        for control in controls["behavioral_controls"]:
            full = next(
                variant
                for variant in control["variants"]
                if variant["variant_id"] == "full_composition"
            )
            wrong_order = next(
                variant
                for variant in control["variants"]
                if variant["variant_id"] == "wrong_order"
            )
            self.assertEqual(full["ordered_skill_ids"], control["ordered_skill_ids"])
            self.assertEqual(
                wrong_order["ordered_skill_ids"],
                list(reversed(control["ordered_skill_ids"])),
            )
            self.assertEqual(
                [item["skill_id"] for item in wrong_order["source_bindings"]],
                wrong_order["ordered_skill_ids"],
            )
            self.assertEqual(full["cache_policy"], "none")
            self.assertNotEqual(
                full["input_packet_digest"], wrong_order["input_packet_digest"]
            )
            self.assertTrue(full["composition_enabled"])
            self.assertEqual(
                full["execution_recipe"]["execution_mode"],
                "compiled_composition",
            )
            self.assertTrue(full["execution_recipe"]["stages"])
            self.assertTrue(full["execution_recipe"]["handoff_contracts"])
            self.assertIn(
                "compiled_context_tokens",
                full["execution_recipe"]["context_accounting"],
            )
            self.assertFalse(wrong_order["composition_enabled"])
            self.assertEqual(
                wrong_order["execution_recipe"]["execution_mode"],
                "counterfactual_wrong_order",
            )
            self.assertTrue(wrong_order["execution_recipe"]["violated_ordering_edges"])
            self.assertTrue(wrong_order["execution_recipe"]["required_gate_overrides"])
            for variant in control["variants"]:
                self.assertEqual(
                    variant["execution_recipe_digest"],
                    variant["execution_recipe"]["recipe_digest"],
                )
                if variant["variant_id"].startswith("leave_one_out:"):
                    self.assertFalse(variant["composition_enabled"])
                    self.assertEqual(
                        variant["execution_recipe"]["execution_mode"],
                        "counterfactual_ablation",
                    )
                    self.assertTrue(variant["execution_recipe"]["missing_obligations"])
        validate_benchmark_control_plan(
            controls,
            run_plan=plan,
            semantic_proposals=proposals,
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )

    def test_control_plan_rejects_phase_mismatch_and_tampering(self) -> None:
        plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        proposals = _semantic_proposal_bundle(plan, self.routing, self.behavioral)
        proposals["behavioral_proposals"][0]["semantic_proposal"]["current_phase"] = (
            "verification"
        )
        with self.assertRaisesRegex(ValueError, "current_phase"):
            build_benchmark_control_plan(
                run_plan=plan,
                semantic_proposals=proposals,
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
            )

        controls = build_benchmark_control_plan(
            run_plan=plan,
            semantic_proposals=_semantic_proposal_bundle(
                plan,
                self.routing,
                self.behavioral,
            ),
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        tampered = copy.deepcopy(controls)
        tampered["behavioral_controls"][0]["variants"][0]["ordered_skill_ids"] = [
            "forged"
        ]
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_benchmark_control_plan(
                tampered,
                run_plan=plan,
                semantic_proposals=_semantic_proposal_bundle(
                    plan,
                    self.routing,
                    self.behavioral,
                ),
                routing_golden=self.routing,
                behavioral_fixtures=self.behavioral,
            )

    def test_context_accounting_binds_all_cited_source_slices_deterministically(
        self,
    ) -> None:
        plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        controls = build_benchmark_control_plan(
            run_plan=plan,
            semantic_proposals=_semantic_proposal_bundle(
                plan,
                self.routing,
                self.behavioral,
            ),
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        control = controls["behavioral_controls"][0]
        replay = control["replay"]
        preflight = copy.deepcopy(replay["preflight"])
        source_bindings = copy.deepcopy(control["source_bindings"])
        plan_projection = copy.deepcopy(replay["packet"]["composition_plan"])
        selected_node_id = source_bindings[0]["source_node_id"]
        selected = next(
            item
            for item in preflight["candidate_source_slices"]
            if item["source_node_id"] == selected_node_id
        )
        content = str(selected["content"])
        split_at = max(1, content.rfind("\n", 1, len(content) - 1))
        if split_at == 1:
            split_at = len(content) // 2
        parts = []
        for start, end in ((0, split_at), (split_at, len(content))):
            part_content = content[start:end].strip()
            self.assertTrue(part_content)
            part_start = int(selected["char_start"]) + start
            part_end = int(selected["char_start"]) + end
            part_digest = content_digest_for(part_content)
            parts.append(
                {
                    **selected,
                    "slice_id": "slice-"
                    + stable_digest(
                        [
                            selected["source_digest"],
                            part_digest,
                            part_start,
                            part_end,
                            selected_node_id,
                        ],
                        20,
                    ),
                    "slice_digest": part_digest,
                    "content": part_content,
                    "char_start": part_start,
                    "char_end": part_end,
                    "token_estimate": max(1, len(part_content) // 4),
                }
            )
        preflight["candidate_source_slices"] = [
            item
            for item in preflight["candidate_source_slices"]
            if item["slice_id"] != selected["slice_id"]
        ] + parts
        source_bindings[0]["cited_slices"] = [
            {
                key: part[key]
                for key in (
                    "slice_id",
                    "source_digest",
                    "slice_digest",
                    "char_start",
                    "char_end",
                )
            }
            for part in parts
        ]

        def replace_citation(citations: list[str]) -> list[str]:
            return [
                citation
                for source_slice_id in citations
                for citation in (
                    [part["slice_id"] for part in parts]
                    if source_slice_id == selected["slice_id"]
                    else [source_slice_id]
                )
            ]

        for role in plan_projection["skill_roles"]:
            role["citations"] = replace_citation(role["citations"])
        for edge in plan_projection["typed_edges"]:
            edge["citations"] = replace_citation(edge["citations"])
        for stage in plan_projection["ordered_stages"]:
            for bridge in stage["bridge_instructions"]:
                bridge["citations"] = replace_citation(bridge["citations"])
            for contract in stage.get("handoff_contracts", []):
                contract["citations"] = replace_citation(contract["citations"])
        for contract in plan_projection.get("handoff_contracts", []):
            contract["citations"] = replace_citation(contract["citations"])

        accounting = _compiled_context_accounting(
            preflight=preflight,
            plan=plan_projection,
            source_bindings=source_bindings,
            packet=replay["packet"],
        )
        reordered_preflight = copy.deepcopy(preflight)
        reordered_preflight["candidate_source_slices"].reverse()
        self.assertEqual(
            accounting,
            _compiled_context_accounting(
                preflight=reordered_preflight,
                plan=plan_projection,
                source_bindings=source_bindings,
                packet=replay["packet"],
            ),
        )
        stage_capsule = next(
            capsule
            for capsule in accounting["phase_capsules"]
            if selected_node_id in capsule["source_ids"]
        )
        self.assertTrue(
            {part["slice_id"] for part in parts}.issubset(
                set(stage_capsule["source_slice_ids"])
            )
        )
        fixture = next(
            item
            for item in self.behavioral["fixtures"]
            if item["fixture_id"] == control["fixture_id"]
        )
        replayed_slices = _replayed_source_slices(
            {
                **control,
                "source_bindings": source_bindings,
                "replay": {**replay, "preflight": preflight},
            },
            workspace_root="/bounded/fixture",
        )
        bound, _slice_ids, _source_nodes, _slices_by_id = validate_source_slice_bindings(
            str(fixture["fixture_id"]),
            list(control["selected_skill_ids"]),
            {"source_slices": replayed_slices},
            validate_fixture_skill_sources(str(fixture["fixture_id"]), fixture),
        )
        self.assertTrue(
            {part["slice_id"] for part in parts}.issubset(bound[source_bindings[0]["skill_id"]])
        )
        forged_slice = copy.deepcopy(replayed_slices)
        forged_slice[0]["content"] += " forged"
        with self.assertRaisesRegex(ValueError, "fixture source range"):
            validate_source_slice_bindings(
                str(fixture["fixture_id"]),
                list(control["selected_skill_ids"]),
                {"source_slices": forged_slice},
                validate_fixture_skill_sources(str(fixture["fixture_id"]), fixture),
            )
        self.assertEqual(
            [part["slice_digest"] for part in parts],
            [
                digest
                for slice_id, digest in zip(
                    stage_capsule["source_slice_ids"],
                    stage_capsule["source_slice_digests"],
                    strict=True,
                )
                if slice_id in {part["slice_id"] for part in parts}
            ],
        )
        uncited_preflight = copy.deepcopy(preflight)
        uncited_preflight["candidate_source_slices"].append(copy.deepcopy(selected))
        uncited = _compiled_context_accounting(
            preflight=uncited_preflight,
            plan=plan_projection,
            source_bindings=source_bindings,
            packet=replay["packet"],
        )
        uncited_runtime_sources = [
            source["source_slice_id"]
            for capsule in uncited["phase_capsules"]
            for source in capsule["capsule"]["sources"]
        ]
        self.assertNotIn(selected["slice_id"], uncited_runtime_sources)

    def test_replayed_graph_identity_matches_compiler_and_ignores_workspace_root(
        self,
    ) -> None:
        plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        controls = build_benchmark_control_plan(
            run_plan=plan,
            semantic_proposals=_semantic_proposal_bundle(
                plan,
                self.routing,
                self.behavioral,
            ),
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        control = controls["behavioral_controls"][0]
        fixture = next(
            item
            for item in self.behavioral["fixtures"]
            if item["fixture_id"] == control["fixture_id"]
        )
        source_slices = _replayed_source_slices(
            control,
            workspace_root="/one/fixtures",
        )
        bindings, _slice_ids, source_nodes, slices_by_id = (
            validate_source_slice_bindings(
                str(fixture["fixture_id"]),
                list(control["selected_skill_ids"]),
                {"source_slices": source_slices},
                validate_fixture_skill_sources(str(fixture["fixture_id"]), fixture),
            )
        )
        self.assertEqual(set(bindings), set(control["selected_skill_ids"]))
        node_to_skill = {
            item["source_node_id"]: item["skill_id"] for item in source_slices
        }
        compiler_plan = control["replay"]["packet"]["composition_plan"]
        relationships = [
            {
                "source_id": node_to_skill[edge["from"]],
                "target_id": node_to_skill[edge["to"]],
                "relation": edge["type"],
                "citations": edge["citations"],
            }
            for edge in compiler_plan["typed_edges"]
        ]
        graph_digest = graph_digest_for_observation(
            list(control["selected_skill_ids"]),
            relationships,
            source_node_by_skill=source_nodes,
            slices_by_id=slices_by_id,
        )
        relocated = copy.deepcopy(source_slices)
        for item in relocated:
            item["source_path"] = "/another/fixture-root/" + item["relative_path"]
        _bindings, _slice_ids, relocated_nodes, relocated_slices = (
            validate_source_slice_bindings(
                str(fixture["fixture_id"]),
                list(control["selected_skill_ids"]),
                {"source_slices": relocated},
                validate_fixture_skill_sources(str(fixture["fixture_id"]), fixture),
            )
        )

        self.assertEqual(
            graph_digest,
            compiler_plan["provenance"]["graph_digest"],
        )
        self.assertEqual(
            graph_digest,
            graph_digest_for_observation(
                list(control["selected_skill_ids"]),
                relationships,
                source_node_by_skill=relocated_nodes,
                slices_by_id=relocated_slices,
            ),
        )
        changed_behavioral = copy.deepcopy(self.behavioral)
        changed_behavioral["fixtures"][0]["skill_sources"][0]["content"] += (
            "\nCapture changed product evidence before the next stage."
        )
        changed_plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=changed_behavioral,
        )
        changed_controls = build_benchmark_control_plan(
            run_plan=changed_plan,
            semantic_proposals=_semantic_proposal_bundle(
                changed_plan,
                self.routing,
                changed_behavioral,
            ),
            routing_golden=self.routing,
            behavioral_fixtures=changed_behavioral,
        )
        changed_control = next(
            item
            for item in changed_controls["behavioral_controls"]
            if item["fixture_id"] == control["fixture_id"]
        )
        self.assertNotEqual(
            graph_digest,
            changed_control["replay"]["packet"]["composition_plan"]["provenance"][
                "graph_digest"
            ],
        )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_prepare_materializes_exact_isolated_fixture_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "benchmark"
            result = prepare_benchmark(
                routing_golden_path=ROUTING_PATH,
                behavioral_fixtures_path=BEHAVIORAL_PATH,
                output_dir=output_dir,
            )
            plan = json.loads(
                (output_dir / "benchmark-run-plan.json").read_text(encoding="utf-8")
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["automatic_tool_execution"])
            self.assertEqual(result["receipt_persistence"], "not_performed")
            self.assertEqual(plan["run_manifest_id"], result["run_manifest_id"])
            self.assertFalse(
                (output_dir / "fixtures" / "benchmark-run-plan.json").exists()
            )
            for fixture in self.behavioral["fixtures"]:
                fixture_root = output_dir / "fixtures" / fixture["fixture_id"]
                for source in fixture["skill_sources"]:
                    self.assertEqual(
                        (fixture_root / source["relative_path"]).read_text(
                            encoding="utf-8"
                        ),
                        source["content"],
                    )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_control_assembly_writes_only_replayed_control_plan(self) -> None:
        plan, _artifacts = build_benchmark_preparation(
            routing_golden=self.routing,
            behavioral_fixtures=self.behavioral,
        )
        proposals = _semantic_proposal_bundle(plan, self.routing, self.behavioral)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = root / "inputs"
            paths = AtomicArtifactStore.write_json_bundle(
                inputs,
                {
                    "run-plan.json": plan,
                    "semantic-proposals.json": proposals,
                },
            )
            result = assemble_control_plan(
                run_plan_path=Path(paths["run-plan.json"]),
                semantic_proposals_path=Path(paths["semantic-proposals.json"]),
                routing_golden_path=ROUTING_PATH,
                behavioral_fixtures_path=BEHAVIORAL_PATH,
                output_dir=root / "controls",
            )
            control_path = Path(result["control_plan_path"])
            control_plan = json.loads(control_path.read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertFalse(result["automatic_tool_execution"])
            self.assertEqual(result["receipt_persistence"], "not_performed")
            self.assertEqual(result["control_plan_id"], control_plan["control_plan_id"])
            assert_matches_schema(
                control_plan,
                SCHEMAS / "tmcp-composition-benchmark-control-plan-v0.1.schema.json",
            )

    @unittest.skipUnless(
        artifact_persistence_available(),
        "Secure artifact persistence is unavailable on this platform.",
    )
    def test_tree_bundle_rejects_escape_and_nonempty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "benchmark"
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_tree_bundle(
                    output_dir,
                    {"fixtures/../outside.txt": "unsafe"},
                )
            AtomicArtifactStore.write_tree_bundle(
                output_dir,
                {"fixtures/one/skills/example/SKILL.md": "safe"},
            )
            self.assertEqual(
                (
                    output_dir / "fixtures" / "one" / "skills" / "example" / "SKILL.md"
                ).read_text(encoding="utf-8"),
                "safe",
            )
            with self.assertRaises(ArtifactStorageError):
                AtomicArtifactStore.write_tree_bundle(
                    output_dir,
                    {"fixtures/two/skills/example/SKILL.md": "new"},
                )


if __name__ == "__main__":
    unittest.main()
