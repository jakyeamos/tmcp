"""Fail-closed resolution of scoped-seed skill dependencies."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from .harvest_nodes import node_source_role
from .scoped_seeds import normalize_scoped_seed


DECLARED_DEPENDENCY_CLOSURE_SCHEMA = "tmcp-declared-dependency-closure-v0.1"
DECLARED_DEPENDENCY_IDENTITY_SCHEMA = "tmcp-declared-dependency-identity-v0.1"
_ACTIVE_SOURCE_ROLES = frozenset({"active_skill", "governing_instruction"})


def _strings(value: object) -> list[str]:
    return (
        [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, list)
        else []
    )


def _skill_slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def _normalized_path(value: object) -> str:
    return str(value or "").replace("\\", "/").strip()


def _normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _stable_digest(value: object) -> str:
    payload = (
        _normalized_text(value)
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, separators=(",", ":"))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def node_is_explicitly_scoped(
    node: Mapping[str, Any],
    explicitly_scoped_paths: Sequence[str] | None = None,
) -> bool:
    """Return whether an exact caller scope authorizes this source activation."""

    if node.get("explicitly_scoped") is True:
        return True
    scoped_paths = {
        _normalized_path(path)
        for path in explicitly_scoped_paths or ()
        if _normalized_path(path)
    }
    return bool(
        scoped_paths.intersection(
            {
                _normalized_path(node.get("relative_path")),
                _normalized_path(node.get("path")),
            }
        )
    )


def _effective_node(
    node: Mapping[str, Any],
    explicitly_scoped_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Re-derive authority after applying only exact explicit caller scope."""

    effective = dict(node)
    explicitly_scoped = node_is_explicitly_scoped(
        effective,
        explicitly_scoped_paths,
    )
    source_role = node_source_role(
        effective,
        explicitly_scoped=explicitly_scoped,
    )
    effective["explicitly_scoped"] = explicitly_scoped
    effective["source_role"] = source_role
    if explicitly_scoped and source_role in _ACTIVE_SOURCE_ROLES:
        # A fixture harvested under a project root carries the conservative
        # evidence-only flag. An exact caller scope is the one intentional
        # exception, so stale harvest metadata cannot keep it inert.
        effective["activation_eligible"] = True
    return effective


def _node_skill_slug(node: Mapping[str, Any]) -> str:
    explicit = _skill_slug(node.get("skill_id"))
    if explicit:
        return explicit
    path = PurePosixPath(_normalized_path(node.get("relative_path")))
    if path.name.lower() == "skill.md":
        return _skill_slug(path.parent.name)
    return ""


def _activation_eligible(
    node: Mapping[str, Any],
    explicitly_scoped_paths: Sequence[str] | None = None,
) -> bool:
    effective = _effective_node(node, explicitly_scoped_paths)
    return (
        str(effective.get("source_role") or "") in _ACTIVE_SOURCE_ROLES
        and effective.get("activation_eligible") is not False
    )


def _dependency_references(seed: Mapping[str, Any]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for field, relation in (("chains_before", "precedes"), ("chains_after", "enables")):
        references.extend(
            {
                "reference": reference,
                "field": field,
                "relationship_type": relation,
                "phase": "",
            }
            for reference in _strings(seed.get(field))
        )
    transitions = seed.get("phase_transitions")
    if not isinstance(transitions, Mapping):
        return references
    for phase in sorted(str(key) for key in transitions):
        transition = transitions.get(phase)
        if not isinstance(transition, Mapping):
            continue
        references.extend(
            {
                "reference": reference,
                "field": "phase_transitions.activate_skills",
                "relationship_type": "enables",
                "phase": phase,
            }
            for reference in _strings(transition.get("activate_skills"))
        )
    return references


def _resolve_reference(
    reference: str,
    nodes: Sequence[Mapping[str, Any]],
    *,
    explicitly_scoped_paths: Sequence[str] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    exact = [node for node in nodes if str(node.get("id") or "") == reference]
    if exact:
        if len(exact) != 1:
            return None, "ambiguous"
        return (
            (_effective_node(exact[0], explicitly_scoped_paths), "resolved")
            if _activation_eligible(exact[0], explicitly_scoped_paths)
            else (None, "ineligible")
        )
    slug = _skill_slug(reference)
    matches = [
        node
        for node in nodes
        if str(node.get("source_type") or "") == "skill_definition"
        and _node_skill_slug(node) == slug
    ]
    if not matches:
        return None, "missing"
    if len(matches) != 1:
        return None, "ambiguous"
    return (
        (_effective_node(matches[0], explicitly_scoped_paths), "resolved")
        if _activation_eligible(matches[0], explicitly_scoped_paths)
        else (None, "ineligible")
    )


def _empty_closure() -> dict[str, Any]:
    return {
        "schema": DECLARED_DEPENDENCY_CLOSURE_SCHEMA,
        "root_seed_ids": [],
        "required_dependency_nodes": [],
        "unresolved_dependencies": [],
        "verification_obligations": [],
    }


def declared_dependency_closure(
    source_nodes: Sequence[Mapping[str, Any]],
    *,
    root_seed_ids: Sequence[str] | None = None,
    explicitly_scoped_paths: Sequence[str] | None = None,
    require_complete_seed_metadata: bool = False,
) -> dict[str, Any]:
    """Resolve exact curated seed dependencies without lexical inference.

    Only exact source-node IDs and unique normalized ``SKILL.md`` slugs are
    accepted. The closure follows a resolved scoped-seed target recursively,
    but leaves its ordering semantics to the cited host proposal. Bare
    verification prose remains an obligation, never an inferred verifier
    activation.
    """

    nodes = [dict(node) for node in source_nodes if isinstance(node, Mapping)]
    seed_nodes_by_id: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if str(node.get("source_type") or "") != "scoped_packet_seed":
            continue
        seed = normalize_scoped_seed(
            _effective_node(node, explicitly_scoped_paths)
        )
        seed_id = str(seed.get("id") or "")
        if seed_id:
            seed_nodes_by_id.setdefault(seed_id, []).append(seed)
    requested_roots = (
        {str(item).strip() for item in root_seed_ids if str(item).strip()}
        if root_seed_ids is not None
        else set(seed_nodes_by_id)
    )
    roots = {
        seed_id: seeds[0]
        for seed_id, seeds in seed_nodes_by_id.items()
        if seed_id in requested_roots
        and len(seeds) == 1
        and seeds[0].get("activation_eligible") is True
    }

    def require_complete_metadata(seed: Mapping[str, Any]) -> None:
        if not require_complete_seed_metadata:
            return
        truncated_fields = _strings(seed.get("metadata_truncated_fields"))
        if truncated_fields:
            raise ValueError(
                "Composition declared dependency closure cannot use truncated "
                "scoped seed metadata for "
                + str(seed.get("id") or "<unknown>")
                + ": "
                + ", ".join(sorted(set(truncated_fields)))
            )

    for seed in roots.values():
        require_complete_metadata(seed)
    resolved: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    seen_resolved: set[tuple[str, str, str, str, str, str]] = set()
    seen_unresolved: set[tuple[str, str, str, str, str]] = set()
    pending_seed_ids = sorted(roots)
    visited_seed_ids: set[str] = set()
    while pending_seed_ids:
        seed_id = pending_seed_ids.pop(0)
        if seed_id in visited_seed_ids:
            continue
        seed = roots.get(seed_id)
        if seed is None:
            candidates = seed_nodes_by_id.get(seed_id, [])
            if len(candidates) != 1 or candidates[0].get("activation_eligible") is not True:
                continue
            seed = candidates[0]
        require_complete_metadata(seed)
        visited_seed_ids.add(seed_id)
        for declaration in _dependency_references(seed):
            target, status = _resolve_reference(
                declaration["reference"],
                nodes,
                explicitly_scoped_paths=explicitly_scoped_paths,
            )
            record = {"seed_id": seed_id, **declaration}
            if target is None:
                unresolved_key = (
                    seed_id,
                    declaration["reference"],
                    declaration["field"],
                    declaration["relationship_type"],
                    status,
                )
                if unresolved_key not in seen_unresolved:
                    unresolved.append({**record, "status": status})
                    seen_unresolved.add(unresolved_key)
                continue
            target_id = str(target.get("id") or "")
            resolved_key = (
                seed_id,
                target_id,
                declaration["field"],
                declaration["relationship_type"],
                declaration["phase"],
                declaration["reference"],
            )
            if resolved_key not in seen_resolved:
                resolved.append(
                    {
                        **record,
                        "source_node_id": target_id,
                        "source_role": str(target.get("source_role") or ""),
                    }
                )
                seen_resolved.add(resolved_key)
            if (
                str(target.get("source_type") or "") == "scoped_packet_seed"
                and target_id not in visited_seed_ids
            ):
                pending_seed_ids.append(target_id)
                pending_seed_ids.sort()
    obligations = [
        {
            "seed_id": seed_id,
            "expectation": expectation,
            # A phase transition names when a skill may activate; it does not
            # prove that the target verifies arbitrary prose. Keep the gap
            # visible until an explicit verifier contract is introduced.
            "status": "unbound",
            "source_node_ids": [],
        }
        for seed_id in sorted(visited_seed_ids)
        for expectation in _strings(
            (roots.get(seed_id) or seed_nodes_by_id[seed_id][0]).get(
                "verification_expectations"
            )
        )
    ]
    return {
        "schema": DECLARED_DEPENDENCY_CLOSURE_SCHEMA,
        "root_seed_ids": sorted(roots),
        "required_dependency_nodes": sorted(
            resolved,
            key=lambda item: (
                item["seed_id"],
                item["source_node_id"],
                item["field"],
                item["reference"],
            ),
        ),
        "unresolved_dependencies": sorted(
            unresolved,
            key=lambda item: (
                item["seed_id"],
                item["field"],
                item["reference"],
            ),
        ),
        "verification_obligations": obligations,
    }


def _has_string_fields(record: Mapping[str, Any], fields: Sequence[str]) -> bool:
    return all(
        isinstance(record.get(field), str)
        and (field == "phase" or bool(str(record.get(field) or "").strip()))
        for field in fields
    )


def _has_optional_citations(record: Mapping[str, Any]) -> bool:
    if "citations" not in record:
        return True
    citations = record.get("citations")
    return isinstance(citations, list) and all(
        isinstance(item, str) and item.strip() for item in citations
    )


def declared_dependency_closure_is_well_formed(closure: object) -> bool:
    """Check the generated closure shape before it can enforce activation."""

    if not isinstance(closure, Mapping):
        return False
    if closure.get("schema") != DECLARED_DEPENDENCY_CLOSURE_SCHEMA:
        return False
    roots = closure.get("root_seed_ids")
    if not isinstance(roots, list) or not all(
        isinstance(item, str) and item.strip() for item in roots
    ):
        return False
    required = closure.get("required_dependency_nodes")
    unresolved = closure.get("unresolved_dependencies")
    obligations = closure.get("verification_obligations")
    if not all(isinstance(value, list) for value in (required, unresolved, obligations)):
        return False
    if not all(
        isinstance(record, Mapping)
        and _has_string_fields(
            record,
            (
                "seed_id",
                "reference",
                "field",
                "relationship_type",
                "phase",
                "source_node_id",
                "source_role",
            ),
        )
        and _has_optional_citations(record)
        for record in required
    ):
        return False
    if not all(
        isinstance(record, Mapping)
        and _has_string_fields(
            record,
            ("seed_id", "reference", "field", "relationship_type", "phase", "status"),
        )
        and _has_optional_citations(record)
        for record in unresolved
    ):
        return False
    return all(
        isinstance(record, Mapping)
        and _has_string_fields(record, ("seed_id", "expectation", "status"))
        and isinstance(record.get("source_node_ids"), list)
        and all(
            isinstance(item, str) and item.strip()
            for item in record.get("source_node_ids", [])
        )
        and _has_optional_citations(record)
        for record in obligations
    )


def required_dependency_source_ids(closure: Mapping[str, Any]) -> set[str]:
    """Return the resolved active sources that must survive bounded selection."""

    records = closure.get("required_dependency_nodes")
    if not isinstance(records, list):
        return set()
    return {
        str(record.get("source_node_id") or "")
        for record in records
        if isinstance(record, Mapping)
        and str(record.get("source_node_id") or "")
    }


def required_closure_source_ids(closure: Mapping[str, Any]) -> set[str]:
    """Return selected seed roots plus their resolved dependency targets."""

    roots = closure.get("root_seed_ids")
    root_ids = (
        {str(item).strip() for item in roots if str(item).strip()}
        if isinstance(roots, list)
        else set()
    )
    return root_ids.union(required_dependency_source_ids(closure))


def closure_for_selected_seeds(
    closure: Mapping[str, Any],
    selected_seed_ids: set[str],
) -> dict[str, Any]:
    """Project a closure without retaining inactive, unselected seed metadata."""

    if not closure:
        return _empty_closure()
    if not declared_dependency_closure_is_well_formed(closure):
        raise ValueError("Declared dependency closure has an invalid shape.")

    def for_selected(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [
            dict(item)
            for item in value
            if isinstance(item, Mapping)
            and str(item.get("seed_id") or "") in selected_seed_ids
        ]

    roots = closure.get("root_seed_ids")
    known_roots = (
        {str(item) for item in roots if str(item)} if isinstance(roots, list) else set()
    )
    return {
        "schema": DECLARED_DEPENDENCY_CLOSURE_SCHEMA,
        "root_seed_ids": sorted(selected_seed_ids.intersection(known_roots)),
        "required_dependency_nodes": for_selected(
            closure.get("required_dependency_nodes")
        ),
        "unresolved_dependencies": for_selected(closure.get("unresolved_dependencies")),
        "verification_obligations": for_selected(
            closure.get("verification_obligations")
        ),
    }


def _source_digest(
    source_node_id: str,
    source_digests_by_node: Mapping[str, str],
) -> str:
    digest = str(source_digests_by_node.get(source_node_id) or "").strip()
    if not digest:
        raise ValueError(
            "Declared dependency identity requires a source digest for every source."
        )
    return digest


def _citation_digests(
    record: Mapping[str, Any],
    slice_digests_by_id: Mapping[str, str],
) -> list[str]:
    citations = record.get("citations")
    if citations is None:
        return []
    if not isinstance(citations, list):
        raise ValueError("Declared dependency identity requires list citations.")
    digests: list[str] = []
    for citation in citations:
        digest = str(slice_digests_by_id.get(str(citation)) or "").strip()
        if not digest:
            raise ValueError(
                "Declared dependency identity requires digests for cited slices."
            )
        digests.append(digest)
    return sorted(set(digests))


def declared_dependency_identity_projection(
    closure: Mapping[str, Any],
    *,
    source_digests_by_node: Mapping[str, str],
    slice_digests_by_id: Mapping[str, str],
) -> dict[str, Any]:
    """Return content-only closure identity without node IDs or file paths."""

    if not declared_dependency_closure_is_well_formed(closure):
        raise ValueError("Declared dependency closure has an invalid shape.")
    roots = [
        _source_digest(str(seed_id), source_digests_by_node)
        for seed_id in closure["root_seed_ids"]
    ]
    required = [
        {
            "seed_source_digest": _source_digest(
                str(record["seed_id"]), source_digests_by_node
            ),
            "target_source_digest": _source_digest(
                str(record["source_node_id"]), source_digests_by_node
            ),
            "relationship_type": str(record["relationship_type"]),
            "field": str(record["field"]),
            "phase": str(record["phase"]),
            "source_role": str(record["source_role"]),
            "reference_digest": _stable_digest(str(record["reference"])),
            "citation_slice_digests": _citation_digests(
                record,
                slice_digests_by_id,
            ),
        }
        for record in closure["required_dependency_nodes"]
    ]
    unresolved = [
        {
            "seed_source_digest": _source_digest(
                str(record["seed_id"]), source_digests_by_node
            ),
            "relationship_type": str(record["relationship_type"]),
            "field": str(record["field"]),
            "phase": str(record["phase"]),
            "status": str(record["status"]),
            "reference_digest": _stable_digest(str(record["reference"])),
            "citation_slice_digests": _citation_digests(
                record,
                slice_digests_by_id,
            ),
        }
        for record in closure["unresolved_dependencies"]
    ]
    obligations = [
        {
            "seed_source_digest": _source_digest(
                str(record["seed_id"]), source_digests_by_node
            ),
            "expectation_digest": _stable_digest(str(record["expectation"])),
            "status": str(record["status"]),
            "target_source_digests": sorted(
                _source_digest(str(node_id), source_digests_by_node)
                for node_id in record["source_node_ids"]
            ),
            "citation_slice_digests": _citation_digests(
                record,
                slice_digests_by_id,
            ),
        }
        for record in closure["verification_obligations"]
    ]
    return {
        "schema": DECLARED_DEPENDENCY_IDENTITY_SCHEMA,
        "root_source_digests": sorted(roots),
        "required_dependency_nodes": sorted(
            required,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        ),
        "unresolved_dependencies": sorted(
            unresolved,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        ),
        "verification_obligations": sorted(
            obligations,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        ),
    }
