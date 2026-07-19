"""Content-bound source slicing for semantic composition preflight."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from .behavior_manifests import (
    build_behavior_manifest_index,
    compact_behavior_manifest_index,
    markdown_behavior_chunks,
    select_hydrated_behavior_blocks,
)
from .composition_active_confidence import (
    declared_skill_phrase_source_ids,
    negative_constraint_source_ids,
    shared_only_active_deferment,
)
from .composition import composition_evidence_terms
from .composition_declared_dependencies import (
    node_is_explicitly_scoped,
    required_dependency_source_ids,
)
from .composition_seed_roots import (
    seed_root_terms,
    select_scoped_seed_closure,
)
from .harvest_nodes import content_digest_for, node_source_role
from .source_activation_projection import project_source_node_for_composition


COMPOSITION_TRUST = "advisory_untrusted"
DEFAULT_MAX_BEHAVIOR_BLOCKS_PER_SOURCE = 24
SOURCE_DIGEST_BINDING_SCHEMA = "tmcp-composition-source-digest-binding-v0.1"
def json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: object) -> list[str]:
    return [str(item).strip() for item in json_list(value) if str(item).strip()]


def ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def stable_digest(value: object, length: int = 64) -> str:
    if isinstance(value, str):
        payload = normalized_text(value)
    else:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _tokens(value: object) -> set[str]:
    return composition_evidence_terms(str(value))


def _source_content(node: dict[str, Any]) -> str:
    return normalized_text(node.get("excerpt") or node.get("signal_excerpt") or "")


def _frontmatter_only_chunk(value: str) -> bool:
    """Identify YAML metadata blocks that should not crowd out skill behavior."""

    content = normalized_text(value)
    if not content.startswith("---\n"):
        return False
    closing = content.find("\n---", len("---\n"))
    return closing >= 0 and not content[closing + len("\n---") :].strip()


def _behavior_chunk_priority(value: str) -> int:
    """Prefer executable contracts over trigger-only introductions."""

    content = normalized_text(value).lower()
    heading = next(
        (
            line.lstrip("#").strip()
            for line in content.splitlines()
            if line.lstrip().startswith("#")
        ),
        "",
    )
    if "output contract" in heading or heading in {"handoff", "handoffs", "gates"}:
        return 0
    if any(
        marker in heading
        for marker in ("workflow", "procedure", "process", "runtime", "execution")
    ):
        return 1
    if any(
        marker in content
        for marker in ("inputs:", "outputs:", "exit gate", "entry gate")
    ):
        return 1
    if any(marker in heading for marker in ("verification", "safety", "evidence")):
        return 2
    return 3


def _source_digest(node: dict[str, Any], excerpt: str) -> str:
    """Bind harvest provenance and bounded visible evidence in one identity."""

    visible_digest = content_digest_for(excerpt)
    harvested_digest = str(node.get("content_digest") or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", harvested_digest):
        return visible_digest
    if harvested_digest == visible_digest:
        return harvested_digest
    return stable_digest(
        {
            "schema": SOURCE_DIGEST_BINDING_SCHEMA,
            "declared_content_digest": harvested_digest,
            "visible_content_digest": visible_digest,
        }
    )


def _identity_source_nodes(source_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **node,
            "content_digest": _source_digest(node, _source_content(node)),
        }
        for node in source_nodes
    ]


def source_role_for(node: dict[str, Any], *, explicitly_scoped: bool = False) -> str:
    """Delegate composition authority to the canonical harvest role policy."""

    return node_source_role(node, explicitly_scoped=explicitly_scoped)


def build_source_slices(
    source_nodes: list[dict[str, Any]],
    objective: str,
    *,
    explicitly_scoped_paths: list[str] | None = None,
    max_slices: int = 24,
    max_chars_per_slice: int = 1600,
    max_total_chars: int = 12000,
    max_total_tokens: int = 3000,
    include_all_active_source_slices: bool = False,
    reserved_metadata_tokens: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rank and bound immutable content slices for host semantic reasoning."""

    if (
        max_slices < 1
        or max_chars_per_slice < 64
        or max_total_chars < 64
        or max_total_tokens < 16
    ):
        raise ValueError("Composition slice limits must be positive and bounded.")
    if not isinstance(reserved_metadata_tokens, int) or isinstance(reserved_metadata_tokens, bool) or reserved_metadata_tokens < 0:
        raise ValueError("Composition reserved metadata tokens must be a nonnegative integer.")
    if not isinstance(include_all_active_source_slices, bool):
        raise ValueError("include_all_active_source_slices must be a boolean.")
    source_nodes = [project_source_node_for_composition(node) for node in source_nodes]
    identity_source_nodes = _identity_source_nodes(source_nodes)
    explicit_paths = tuple(explicitly_scoped_paths or [])
    objective_tokens = _tokens(objective)
    seed_root_objective_terms = seed_root_terms(objective)
    governing_source_count = sum(
        source_role_for(
            node,
            explicitly_scoped=node_is_explicitly_scoped(node, explicit_paths),
        )
        == "governing_instruction"
        for node in identity_source_nodes
    )
    if governing_source_count > max_slices:
        raise ValueError("Composition slice limit cannot include every governing source.")
    if governing_source_count and max_total_chars < governing_source_count * 64:
        raise ValueError("Composition character limit cannot include every governing source.")
    if governing_source_count and max_total_tokens < governing_source_count * 16:
        raise ValueError("Composition token limit cannot include every governing source.")
    metadata_limits = {
        "triggers": 8,
        "facets": 8,
        "phases": 4,
        "gates": 6,
        "inputs": 4,
        "outputs": 4,
        "references": 6,
    }
    bootstrap_manifest_index = compact_behavior_manifest_index(
        build_behavior_manifest_index(
            identity_source_nodes,
            metadata_limits=metadata_limits,
        )
    )
    bootstrap_index_tokens = int(
        bootstrap_manifest_index["cost_telemetry"]["always_on_index_tokens"]
    )
    if bootstrap_index_tokens + reserved_metadata_tokens > max_total_tokens:
        raise ValueError("Composition token limit cannot accommodate the behavior manifest index.")
    available_hydration_tokens = (
        max_total_tokens - bootstrap_index_tokens - reserved_metadata_tokens
    )
    if governing_source_count and available_hydration_tokens < governing_source_count * 16:
        raise ValueError(
            "Composition token limit cannot include every governing source with the behavior manifest index."
        )
    raw_candidates: list[dict[str, Any]] = []
    source_token_baselines: dict[str, int] = {}
    source_node_ids: set[str] = set()
    active_source_ids: set[str] = set()
    explicitly_scoped_source_ids: set[str] = set()
    source_block_truncations: list[dict[str, Any]] = []
    source_token_estimates_complete = True
    role_rank = {
        "governing_instruction": 0,
        "active_skill": 1,
        "supporting_reference": 2,
        "evidence_only": 3,
    }
    governing_chunk_limit = (
        min(
            max_total_chars // governing_source_count,
            (available_hydration_tokens * 4) // governing_source_count,
        )
        if governing_source_count
        else max_total_chars
    )
    chunk_limit = min(max_chars_per_slice, governing_chunk_limit)
    per_source_block_limit = max(DEFAULT_MAX_BEHAVIOR_BLOCKS_PER_SOURCE, max_slices)
    for node in identity_source_nodes:
        relative_path = str(node.get("relative_path") or node.get("path") or "")
        content = _source_content(node)
        source_digest = str(node["content_digest"])
        visible_content_digest = content_digest_for(content)
        source_node_id = str(node.get("id") or f"source-{source_digest[:16]}")
        source_node_ids.add(source_node_id)
        effective_explicit_scope = node_is_explicitly_scoped(node, explicit_paths)
        role = source_role_for(node, explicitly_scoped=effective_explicit_scope)
        if role == "active_skill":
            active_source_ids.add(source_node_id)
        if effective_explicit_scope:
            explicitly_scoped_source_ids.add(source_node_id)
        mandatory = role == "governing_instruction"
        node_candidates: list[dict[str, Any]] = []
        for start, end, chunk in markdown_behavior_chunks(content, chunk_limit):
            if not normalized_text(chunk):
                continue
            slice_digest = content_digest_for(chunk)
            slice_id = "slice-" + stable_digest(
                [source_digest, slice_digest, start, end, source_node_id], 20
            )
            candidate = {
                "slice_id": slice_id,
                "source_node_id": source_node_id,
                "source_digest": source_digest,
                "visible_content_digest": visible_content_digest,
                "slice_digest": slice_digest,
                "source_role": role,
                "source_type": str(node.get("source_type") or "unknown"),
                "relative_path": relative_path,
                "title": str(node.get("title") or relative_path or source_node_id),
                "content": chunk,
                "char_start": start,
                "char_end": end,
                "token_estimate": max(1, len(chunk) // 4),
                "behavior_atoms": string_list(node.get("behavior_atoms")),
                "phase_hints": string_list(
                    dict(node.get("routing_metadata") or {}).get("phase_hints")
                ),
                "incompatibilities": string_list(node.get("do_not_activate_with")),
                "mandatory": mandatory,
                "explicitly_scoped": effective_explicit_scope,
                "trust": COMPOSITION_TRUST,
            }
            node_candidates.append(candidate)
        node_candidates.sort(
            key=lambda candidate: (
                int(_frontmatter_only_chunk(str(candidate["content"]))),
                -len(
                    objective_tokens.intersection(
                        _tokens(
                            " ".join(
                                [
                                    str(candidate["title"]),
                                    str(candidate["relative_path"]),
                                    str(candidate["content"]),
                                    " ".join(candidate["behavior_atoms"]),
                                    " ".join(candidate["phase_hints"]),
                                ]
                            )
                        )
                    )
                ),
                _behavior_chunk_priority(str(candidate["content"])),
                int(candidate["char_start"]),
                str(candidate["slice_digest"]),
            )
        )
        if len(node_candidates) > per_source_block_limit:
            source_block_truncations.append(
                {
                    "source_node_id": source_node_id,
                    "available_block_count": len(node_candidates),
                    "indexed_block_count": per_source_block_limit,
                }
            )
        raw_candidates.extend(node_candidates[:per_source_block_limit])
        source_token_estimate = node.get("token_estimate")
        has_declared_source_tokens = not isinstance(
            source_token_estimate, bool
        ) and isinstance(source_token_estimate, int)
        if not has_declared_source_tokens:
            source_token_estimates_complete = False
        declared_source_tokens = int(source_token_estimate) if has_declared_source_tokens else 0
        source_token_baselines[source_node_id] = max(
            declared_source_tokens,
            sum(int(candidate["token_estimate"]) for candidate in node_candidates),
        )

    citable_source_ids = {
        str(candidate["source_node_id"]) for candidate in raw_candidates
    }
    uncitable_source_ids = sorted(source_node_ids.difference(citable_source_ids))
    missing_active_source_ids = sorted(active_source_ids.difference(citable_source_ids))
    if include_all_active_source_slices and missing_active_source_ids:
        raise ValueError(
            "Composition all-active evidence requires a citable nonempty slice for "
            f"every active source: {', '.join(missing_active_source_ids)}"
        )

    full_manifest_index = build_behavior_manifest_index(
        identity_source_nodes,
        raw_candidates,
        metadata_limits=metadata_limits,
        max_blocks=per_source_block_limit,
    )
    manifests_by_source = {
        str(manifest["source"]["source_node_id"]): manifest
        for manifest in full_manifest_index["manifests"]
    }
    candidates: list[tuple[tuple[int, int, int, int, str, int], dict[str, Any]]] = []
    objective_relevant_source_ids: set[str] = set()
    content_objective_relevant_source_ids: set[str] = set()
    seed_root_objective_terms_by_source: dict[str, set[str]] = {}
    active_objective_terms: dict[str, set[str]] = {}
    prunable_active_source_ids: set[str] = set()
    for candidate in raw_candidates:
        source_node_id = str(candidate["source_node_id"])
        manifest = manifests_by_source[source_node_id]
        block_by_locator = {
            str(block["source_locator"]): block for block in manifest["behavior_blocks"]
        }
        block = block_by_locator[str(candidate["slice_id"])]
        metadata = manifest["behavior_metadata"]
        signal = " ".join(
            [
                str(candidate["title"]),
                str(candidate["relative_path"]),
                str(candidate["content"]),
                " ".join(string_list(metadata.get("triggers"))),
                " ".join(string_list(metadata.get("facets"))),
                " ".join(string_list(block.get("facets"))),
                " ".join(string_list(block.get("phases"))),
            ]
        )
        content_signal = " ".join(
            [
                str(candidate["content"]),
                " ".join(string_list(metadata.get("triggers"))),
                " ".join(string_list(metadata.get("facets"))),
                " ".join(string_list(block.get("facets"))),
                " ".join(string_list(block.get("phases"))),
            ]
        )
        matched_terms = objective_tokens.intersection(_tokens(content_signal))
        relevance = len(objective_tokens.intersection(_tokens(signal)))
        if matched_terms:
            content_objective_relevant_source_ids.add(source_node_id)
        if candidate["source_type"] == "scoped_packet_seed":
            seed_root_objective_terms_by_source.setdefault(
                source_node_id,
                set(),
            ).update(
                seed_root_objective_terms.intersection(seed_root_terms(content_signal))
            )
        if relevance:
            objective_relevant_source_ids.add(source_node_id)
        if candidate["source_role"] == "active_skill":
            active_objective_terms.setdefault(source_node_id, set()).update(
                matched_terms
            )
            if (
                candidate["source_type"] != "scoped_packet_seed"
                and not candidate["explicitly_scoped"]
            ):
                prunable_active_source_ids.add(source_node_id)
        enriched = {
            **candidate,
            "behavior_manifest_id": manifest["manifest_id"],
            "behavior_manifest_digest": manifest["manifest_digest"],
            "behavior_block_id": block["block_id"],
            "behavior_block_digest": block["block_digest"],
            "behavior_block_facets": list(block["facets"]),
            "behavior_block_phases": list(block["phases"]),
        }
        key = (
            -int(bool(candidate["mandatory"])),
            int(candidate["char_start"]) if candidate["mandatory"] else 0,
            int(_frontmatter_only_chunk(str(candidate["content"]))),
            -relevance,
            _behavior_chunk_priority(str(candidate["content"])),
            role_rank[str(candidate["source_role"])],
            str(candidate["relative_path"]),
            int(candidate["char_start"]),
        )
        candidates.append((key, enriched))
    seed_selection = select_scoped_seed_closure(
        identity_source_nodes,
        citable_source_ids=citable_source_ids,
        explicitly_scoped_source_ids=explicitly_scoped_source_ids,
        seed_objective_terms_by_source=seed_root_objective_terms_by_source,
        objective=objective,
        explicitly_scoped_paths=explicit_paths,
        include_all_active_source_slices=include_all_active_source_slices,
    )
    dependency_closure = seed_selection["dependency_closure"]
    required_closure_ids = seed_selection["required_closure_source_ids"]
    deferred_nonroot_scoped_seed_ids = seed_selection[
        "deferred_nonroot_scoped_seed_ids"
    ]
    discriminative_seed_root_terms = seed_selection[
        "discriminative_seed_root_terms"
    ]
    declared_phrase_root_seed_ids = seed_selection["declared_phrase_root_seed_ids"]
    declared_skill_phrase_active_source_ids = (
        declared_skill_phrase_source_ids(identity_source_nodes, objective)
        .intersection(active_source_ids)
    )
    negative_constraint_active_source_ids = (
        negative_constraint_source_ids(identity_source_nodes, objective)
        .intersection(prunable_active_source_ids)
        .difference(declared_skill_phrase_active_source_ids)
    )
    (
        discriminative_active_objective_terms,
        deferred_shared_only_active_source_ids,
        no_high_confidence_active_skill,
        low_cardinality_active_fallback,
    ) = shared_only_active_deferment(
        active_objective_terms,
        prunable_active_source_ids,
        include_all_active_source_slices=include_all_active_source_slices,
        high_confidence_active_source_ids=declared_skill_phrase_active_source_ids,
    )
    deferred_shared_only_active_source_ids.difference_update(required_closure_ids)
    deferred_active_source_ids = deferred_shared_only_active_source_ids.union(
        deferred_nonroot_scoped_seed_ids
    ).union(negative_constraint_active_source_ids)
    no_high_confidence_active_skill = no_high_confidence_active_skill or (
        not include_all_active_source_slices
        and bool(prunable_active_source_ids)
        and prunable_active_source_ids.issubset(deferred_active_source_ids)
    )
    candidates.sort(key=lambda item: item[0])
    manifest_index = compact_behavior_manifest_index(full_manifest_index)
    manifest_cost = dict(manifest_index["cost_telemetry"])
    full_manifest_cost = dict(full_manifest_index["cost_telemetry"])
    naive_candidate_tokens = sum(source_token_baselines.values())
    manifest_index_tokens = int(manifest_cost["always_on_index_tokens"])
    if manifest_index_tokens > max_total_tokens:
        raise ValueError("Composition token limit cannot accommodate the behavior manifest index.")
    max_hydration_tokens = (
        max_total_tokens - manifest_index_tokens - reserved_metadata_tokens
    )
    target_context_tokens = (
        min(max_total_tokens, int(naive_candidate_tokens * 0.75))
        if source_token_estimates_complete
        else max_total_tokens
    )
    target_hydration_tokens = (
        max(0, target_context_tokens - manifest_index_tokens - reserved_metadata_tokens)
        if source_token_estimates_complete
        else max_hydration_tokens
    )
    selection = select_hydrated_behavior_blocks(
        [candidate for _, candidate in candidates],
        max_slices=max_slices,
        max_total_chars=max_total_chars,
        max_hydration_tokens=max_hydration_tokens,
        target_hydration_tokens=target_hydration_tokens,
        governing_source_count=governing_source_count,
        include_all_active_source_slices=include_all_active_source_slices,
        objective_relevant_source_ids=objective_relevant_source_ids,
        deferred_active_source_ids=deferred_active_source_ids,
        required_source_ids=required_closure_ids,
    )
    selected = selection["selected"]
    total_chars = int(selection["total_chars"])
    total_tokens = int(selection["total_tokens"])
    selected_source_ids = {str(item["source_node_id"]) for item in selected}
    selected_block_ids = {str(item["behavior_block_id"]) for item in selected}
    diagnostics = {
        "truncated": len(selected) < len(candidates),
        "candidate_slice_count": len(candidates),
        "returned_slice_count": len(selected),
        "excluded_slice_count": len(candidates) - len(selected),
        "excluded_source_count": len(
            {
                str(candidate["source_node_id"])
                for _, candidate in candidates
                if str(candidate["source_node_id"]) not in selected_source_ids
            }
        ),
        "total_chars": total_chars,
        "total_tokens": total_tokens,
        "source_block_truncations": source_block_truncations,
        "uncitable_source_ids": uncitable_source_ids,
        "unindexed_behavior_block_count": sum(
            item["available_block_count"] - item["indexed_block_count"]
            for item in source_block_truncations
        ),
        "behavior_manifest_index": manifest_index,
        "context_cost": {
            "always_on_index_tokens": manifest_index_tokens,
            "hydrated_candidate_tokens": total_tokens,
            "naive_candidate_tokens": naive_candidate_tokens,
            "target_context_tokens": target_context_tokens,
            "target_hydration_tokens": target_hydration_tokens,
            "max_hydration_tokens": max_hydration_tokens,
            "reserved_metadata_tokens": reserved_metadata_tokens,
            "preflight_total_tokens": (
                int(manifest_index_tokens) + total_tokens + reserved_metadata_tokens
            ),
            "deferred_behavior_block_count": int(full_manifest_cost["behavior_block_count"])
            - len(selected_block_ids),
            "selected_behavior_block_count": len(selected_block_ids),
            "context_target_computable": source_token_estimates_complete,
            "context_target_achievable": source_token_estimates_complete
            and manifest_index_tokens + reserved_metadata_tokens
            <= target_context_tokens,
            "context_target_met": source_token_estimates_complete
            and manifest_index_tokens + total_tokens + reserved_metadata_tokens
            <= target_context_tokens,
            "mandatory_context_overrides": selection["mandatory_context_overrides"],
            "minimum_active_context_override": selection["minimum_active_context_override"],
            "required_active_context_overrides": selection[
                "required_active_context_overrides"
            ],
            "required_dependency_context_overrides": selection[
                "required_dependency_context_overrides"
            ],
            "hydration_ratio": round(total_tokens / max(1, naive_candidate_tokens), 4),
            "preflight_context_ratio": round(
                (
                    int(manifest_cost["always_on_index_tokens"])
                    + total_tokens
                    + reserved_metadata_tokens
                )
                / max(1, naive_candidate_tokens),
                4,
            ),
            "cost_policy": "candidate_slices_manifest_index_and_reserved_metadata",
        },
        "semantic_evidence": {
            "selection_policy": (
                "all_active_source_candidates"
                if include_all_active_source_slices
                else "ranked_candidates"
            ),
            "eligible_active_source_count": len(
                {
                    str(candidate["source_node_id"])
                    for _, candidate in candidates
                    if candidate["source_role"] == "active_skill"
                }
            ),
            "selected_active_source_ids": selection["represented_active_source_ids"],
            "objective_relevant_source_ids": sorted(objective_relevant_source_ids),
            "discriminative_active_objective_terms": (
                discriminative_active_objective_terms
            ),
            "discriminative_scoped_seed_objective_terms": sorted(
                discriminative_seed_root_terms
            ),
            "declared_skill_phrase_active_source_ids": sorted(
                declared_skill_phrase_active_source_ids
            ),
            "negative_constraint_active_source_ids": sorted(
                negative_constraint_active_source_ids
            ),
            "declared_phrase_scoped_seed_root_ids": sorted(
                declared_phrase_root_seed_ids
            ),
            "deferred_shared_only_active_source_ids": sorted(
                deferred_shared_only_active_source_ids
            ),
            "no_high_confidence_active_skill": no_high_confidence_active_skill,
            "low_cardinality_active_fallback": low_cardinality_active_fallback,
            "deferred_nonroot_scoped_seed_ids": sorted(
                deferred_nonroot_scoped_seed_ids
            ),
            "declared_dependency_root_seed_ids": sorted(
                dependency_closure["root_seed_ids"]
            ),
            "required_declared_dependency_source_ids": sorted(
                required_dependency_source_ids(dependency_closure)
            ),
            "declared_dependency_closure": dependency_closure,
            "deferred_irrelevant_source_count": len(
                {
                    str(candidate["source_node_id"])
                    for _, candidate in candidates
                    if str(candidate["source_node_id"]) not in selected_source_ids
                    and str(candidate["source_node_id"])
                    not in objective_relevant_source_ids
                    and candidate["source_role"] != "governing_instruction"
                }
            ),
        },
        "limits": {
            "max_slices": max_slices,
            "max_chars_per_slice": max_chars_per_slice,
            "max_total_chars": max_total_chars,
            "max_total_tokens": max_total_tokens,
        },
    }
    return selected, diagnostics
