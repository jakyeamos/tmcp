from __future__ import annotations

import copy
import json
import unittest
from typing import Any

from tmcp_runtime.domain.behavior_manifests import (
    BEHAVIOR_HYDRATION_SCHEMA,
    BEHAVIOR_MANIFEST_INDEX_SCHEMA,
    BEHAVIOR_MANIFEST_SCHEMA,
    REFERENCE_POLICY,
    build_behavior_manifest,
    build_behavior_manifest_index,
    compact_behavior_manifest_index,
    hydrate_behavior_blocks,
    markdown_behavior_chunks,
)
from tmcp_runtime.domain.harvest_nodes import content_digest_for


def _node(node_id: str, content: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "skill_id": f"skill-{node_id}",
        "relative_path": f"skills/{node_id}/SKILL.md",
        "source_type": "skill_definition",
        "source_role": "active_skill",
        "content_digest": content_digest_for(content),
        "token_estimate": max(1, len(content) // 4),
        "signal_excerpt": "routing summary without the hydrated sentinel",
        "behavior_atoms": ["verification", "artifact-contract"],
        "guidance_labels": [{"id": "testing:regression"}],
        "route_affinity": ["implementation"],
        "use_when": ["change product behavior"],
        "objective_patterns": ["fix then verify"],
        "minimum_spec_fields": ["acceptance criteria"],
        "outputs": ["reviewable implementation"],
        "source_references": ["references/checklist.md"],
        "routing_metadata": {
            "commands": ["audit"],
            "trigger_phrases": ["regression fix"],
            "phase_hints": ["verification", "implementation"],
            "verification_gates": ["Run focused tests."],
            "required_reads": ["references/contract.md"],
            "declared_loads": ["references/*.md"],
            "output_contract": ["Report evidence."],
        },
    }


def _slices(node_id: str, first: str, second: str) -> list[dict[str, Any]]:
    return [
        {
            "slice_id": f"slice-{node_id}-2",
            "source_node_id": node_id,
            "slice_digest": content_digest_for(second),
            "content": second,
            "char_start": len(first) + 1,
            "char_end": len(first) + len(second) + 1,
            "token_estimate": max(1, len(second) // 4),
            "behavior_atoms": ["verification"],
            "phase_hints": ["verification"],
        },
        {
            "slice_id": f"slice-{node_id}-1",
            "source_node_id": node_id,
            "slice_digest": content_digest_for(first),
            "content": first,
            "char_start": 0,
            "char_end": len(first),
            "token_estimate": max(1, len(first) // 4),
            "behavior_atoms": ["artifact-contract"],
            "phase_hints": ["implementation"],
        },
    ]


class BehaviorManifestTests(unittest.TestCase):
    def test_manifest_is_deterministic_content_addressed_and_content_free(self) -> None:
        first = "Produce SENTINEL-ALPHA as a typed implementation artifact."
        second = "Verify SENTINEL-BETA with focused regression evidence."
        content = f"{first}\n{second}"
        node = _node("compose", content)
        slices = _slices("compose", first, second)

        manifest = build_behavior_manifest(node, slices)
        reordered = copy.deepcopy(node)
        reordered["behavior_atoms"] = list(reversed(reordered["behavior_atoms"]))
        reordered["routing_metadata"]["phase_hints"] = [
            "implementation",
            "verification",
        ]

        self.assertEqual(manifest, build_behavior_manifest(reordered, list(reversed(slices))))
        self.assertEqual(manifest["schema"], BEHAVIOR_MANIFEST_SCHEMA)
        self.assertEqual(manifest["source"]["source_node_id"], "compose")
        self.assertEqual(manifest["source"]["skill_id"], "skill-compose")
        self.assertEqual(manifest["source"]["source_role"], "active_skill")
        self.assertEqual(manifest["source"]["content_digest"], content_digest_for(content))
        self.assertEqual(len(manifest["manifest_digest"]), 64)
        self.assertTrue(manifest["manifest_id"].startswith("behavior-manifest-"))
        serialized = json.dumps(manifest, sort_keys=True)
        self.assertNotIn("SENTINEL-ALPHA", serialized)
        self.assertNotIn("SENTINEL-BETA", serialized)
        blocks = manifest["behavior_blocks"]
        self.assertEqual([item["source_locator"] for item in blocks], ["slice-compose-1", "slice-compose-2"])
        self.assertEqual(len({item["block_digest"] for item in blocks}), 2)
        self.assertTrue(all("content" not in item for item in blocks))

    def test_metadata_is_bounded_and_references_stay_advisory(self) -> None:
        node = _node("bounded", "A compact source body.")
        node["routing_metadata"]["commands"] = ["zeta", "beta", "alpha"]
        node["source_references"] = ["z.md", "a.md", "m.md"]

        manifest = build_behavior_manifest(
            node,
            metadata_limits={field: 1 for field in (
                "triggers", "facets", "phases", "gates", "inputs", "outputs", "references"
            )},
        )

        metadata = manifest["behavior_metadata"]
        for field in ("triggers", "facets", "phases", "gates", "inputs", "outputs", "references"):
            self.assertLessEqual(len(metadata[field]), 1)
        self.assertEqual(metadata["reference_policy"], REFERENCE_POLICY)
        self.assertTrue(manifest["bounds"]["metadata"]["truncated"]["references"])
        self.assertTrue(manifest["bounds"]["metadata"]["truncated"]["triggers"])

    def test_same_path_content_edit_changes_block_and_manifest_identity(self) -> None:
        before_text = "Produce the artifact."
        after_text = "Produce and verify the artifact."
        before = build_behavior_manifest(
            _node("identity", before_text),
            _slices("identity", before_text, "Verify once."),
        )
        after = build_behavior_manifest(
            _node("identity", after_text),
            _slices("identity", after_text, "Verify twice."),
        )

        self.assertNotEqual(before["manifest_digest"], after["manifest_digest"])
        self.assertNotEqual(before["manifest_id"], after["manifest_id"])
        self.assertNotEqual(
            [item["block_digest"] for item in before["behavior_blocks"]],
            [item["block_digest"] for item in after["behavior_blocks"]],
        )

    def test_rename_keeps_content_addressed_manifest_identity(self) -> None:
        content = "Produce a source-backed artifact."
        first = _node("first", content)
        renamed = {**_node("renamed", content), "skill_id": "other-skill"}
        first_slice = _slices("first", content, "Verify the artifact.")[0]
        renamed_slice = {
            **first_slice,
            "slice_id": "slice-renamed-1",
            "source_node_id": "renamed",
        }

        self.assertEqual(
            build_behavior_manifest(first, [first_slice])["manifest_digest"],
            build_behavior_manifest(renamed, [renamed_slice])["manifest_digest"],
        )

    def test_hydration_returns_requested_content_and_enforces_provenance(self) -> None:
        first = "Create the typed artifact."
        second = "Verify the typed artifact."
        content = f"{first}\n{second}"
        node = _node("hydrate", content)
        slices = _slices("hydrate", first, second)
        manifest = build_behavior_manifest(node, slices)
        requested = manifest["behavior_blocks"][1]["block_id"]

        hydrated = hydrate_behavior_blocks(
            manifest,
            source_node=node,
            source_slices=slices,
            block_ids=[requested],
        )

        self.assertEqual(hydrated["schema"], BEHAVIOR_HYDRATION_SCHEMA)
        self.assertEqual([item["content"] for item in hydrated["blocks"]], [second])
        self.assertEqual(hydrated["cost_telemetry"]["hydrated_block_count"], 1)
        self.assertFalse(hydrated["cost_telemetry"]["truncated"])

        source_bound_slices = [
            {**item, "source_digest": node["content_digest"]} for item in slices
        ]
        self.assertEqual(
            hydrate_behavior_blocks(
                manifest,
                source_node=node,
                source_slices=source_bound_slices,
                block_ids=[requested],
            )["blocks"][0]["content"],
            second,
        )

        tampered = copy.deepcopy(slices)
        tampered[0]["content"] = "Substituted behavior."
        tampered[0].pop("slice_digest")
        with self.assertRaisesRegex(ValueError, "block digest mismatch"):
            hydrate_behavior_blocks(
                manifest,
                source_node=node,
                source_slices=tampered,
                block_ids=[requested],
            )

    def test_hydration_rejects_manifest_and_source_digest_tampering(self) -> None:
        first = "Create the typed artifact."
        second = "Verify the typed artifact."
        content = f"{first}\n{second}"
        node = _node("tamper", content)
        slices = _slices("tamper", first, second)
        manifest = build_behavior_manifest(node, slices)
        target = next(
            item
            for item in manifest["behavior_blocks"]
            if item["source_locator"] == "slice-tamper-2"
        )
        tampered_manifest = copy.deepcopy(manifest)
        tampered_block = next(
            item
            for item in tampered_manifest["behavior_blocks"]
            if item["block_id"] == target["block_id"]
        )
        tampered_block["block_digest"] = content_digest_for("MALICIOUS")
        tampered_slices = copy.deepcopy(slices)
        tampered_slices[0]["content"] = "MALICIOUS"
        tampered_slices[0]["slice_digest"] = content_digest_for("MALICIOUS")

        with self.assertRaisesRegex(ValueError, "manifest digest"):
            hydrate_behavior_blocks(
                tampered_manifest,
                source_node=node,
                source_slices=tampered_slices,
                block_ids=[target["block_id"]],
            )

        wrong_source = [{**item, "source_digest": "f" * 64} for item in slices]
        with self.assertRaisesRegex(ValueError, "does not match source"):
            hydrate_behavior_blocks(
                manifest,
                source_node=node,
                source_slices=wrong_source,
                block_ids=[target["block_id"]],
            )

    def test_node_signal_fallback_is_lazy_and_hydratable(self) -> None:
        node = _node("signal", "Full source body is represented by its digest.")
        manifest = build_behavior_manifest(node)

        self.assertEqual(len(manifest["behavior_blocks"]), 1)
        descriptor = manifest["behavior_blocks"][0]
        self.assertEqual(descriptor["source_kind"], "node_signal")
        self.assertNotIn("content", descriptor)
        hydrated = hydrate_behavior_blocks(manifest, source_node=node)
        self.assertEqual(
            hydrated["blocks"][0]["content"],
            node["signal_excerpt"],
        )

    def test_manifest_index_has_canonical_order_and_aggregate_costs(self) -> None:
        alpha_text = "Alpha behavior."
        beta_text = "Beta behavior."
        alpha = _node("alpha", alpha_text)
        beta = _node("beta", beta_text)
        slices = _slices("alpha", alpha_text, "Alpha verification.") + _slices(
            "beta", beta_text, "Beta verification."
        )

        index = build_behavior_manifest_index([beta, alpha], slices)
        reordered = build_behavior_manifest_index(
            [alpha, beta], list(reversed(slices))
        )

        self.assertEqual(index, reordered)
        self.assertEqual(index["schema"], BEHAVIOR_MANIFEST_INDEX_SCHEMA)
        self.assertEqual(
            [item["source"]["source_node_id"] for item in index["manifests"]],
            ["alpha", "beta"],
        )
        costs = index["cost_telemetry"]
        self.assertEqual(costs["manifest_count"], 2)
        self.assertEqual(costs["behavior_block_count"], 4)
        self.assertGreater(costs["always_on_index_tokens"], 0)
        self.assertGreater(costs["hydration_tokens"], 0)
        self.assertGreater(costs["source_tokens"], 0)

    def test_index_digest_ignores_multi_source_renames_and_order(self) -> None:
        first = build_behavior_manifest_index(
            [_node("alpha", "Alpha behavior."), _node("beta", "Beta behavior.")]
        )
        renamed = build_behavior_manifest_index(
            [_node("second", "Beta behavior."), _node("first", "Alpha behavior.")]
        )

        self.assertEqual(first["index_digest"], renamed["index_digest"])
        self.assertEqual(first["index_id"], renamed["index_id"])

    def test_compact_index_omits_behavior_content_and_metadata(self) -> None:
        content = "SENTINEL-PRIVATE behavior must remain hydratable only."
        index = build_behavior_manifest_index(
            [_node("private", content)],
            _slices("private", content, "Verification behavior."),
        )

        compact = compact_behavior_manifest_index(index)

        self.assertEqual(compact["schema"], BEHAVIOR_MANIFEST_INDEX_SCHEMA)
        self.assertEqual(
            compact["manifest_summaries"],
            [{"source_node_id": "private", "behavior_block_count": 2}],
        )
        serialized = json.dumps(compact, sort_keys=True)
        self.assertNotIn("SENTINEL-PRIVATE", serialized)
        self.assertNotIn("behavior_metadata", serialized)
        self.assertLess(
            compact["cost_telemetry"]["always_on_index_tokens"],
            index["cost_telemetry"]["always_on_index_tokens"],
        )

    def test_markdown_chunks_keep_behavior_headings_together(self) -> None:
        text = "# Plan\nBuild the artifact.\n\n# Verify\nRun focused tests."

        chunks = markdown_behavior_chunks(text, 80)

        self.assertEqual(
            [content for _, _, content in chunks],
            ["# Plan\nBuild the artifact.", "# Verify\nRun focused tests."],
        )


if __name__ == "__main__":
    unittest.main()
