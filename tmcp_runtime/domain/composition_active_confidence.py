"""Deterministic confidence policy for automatic active-skill hydration."""

from __future__ import annotations

import re


_NEGATIVE_CONSTRAINT_IGNORED_TERMS = frozenset(
    {
        "a",
        "an",
        "and",
        "any",
        "for",
        "it",
        "not",
        "or",
        "the",
        "to",
        "use",
    }
)


def declared_skill_phrase_source_ids(
    source_nodes: list[dict[str, object]], objective: str
) -> set[str]:
    """Return active skill ids explicitly named by a multiword skill phrase."""

    objective_text = objective.lower()
    source_ids: set[str] = set()
    for node in source_nodes:
        if str(node.get("source_type") or "") != "skill_definition":
            continue
        source_id = str(node.get("id") or "")
        content = str(node.get("excerpt") or node.get("signal_excerpt") or "")
        name_match = re.search(r"(?mi)^name:\s*([^\n#]+)$", content)
        raw_name = name_match.group(1).strip() if name_match else ""
        terms = [
            term
            for term in re.findall(r"[a-z0-9]+", raw_name.lower())
            if term and term != "tmcp"
        ]
        for length in range(2, len(terms) + 1):
            phrase = " ".join(terms[:length])
            phrase_pattern = re.escape(phrase).replace(r"\ ", r"[\s_/-]+")
            if re.search(
                rf"(?<![a-z0-9]){phrase_pattern}(?![a-z0-9])", objective_text
            ):
                source_ids.add(source_id)
                break
    return source_ids


def negative_constraint_source_ids(
    source_nodes: list[dict[str, object]], objective: str
) -> set[str]:
    """Return active skill ids whose declared negative clause matches exactly."""

    objective_terms = set(re.findall(r"[a-z0-9]+", objective.lower()))
    source_ids: set[str] = set()
    for node in source_nodes:
        if str(node.get("source_type") or "") != "skill_definition":
            continue
        routing = node.get("routing_metadata")
        if not isinstance(routing, dict):
            continue
        constraints = routing.get("do_not_use_when")
        if not isinstance(constraints, list):
            continue
        for constraint in constraints:
            negative_text = str(constraint).lower().split("unless", 1)[0]
            tail = re.split(r"\b(?:for|to)\b", negative_text, maxsplit=1)
            if len(tail) != 2:
                continue
            for clause in re.split(r"\s*,\s*|\s+\bor\b\s+", tail[1]):
                clause_terms = set(re.findall(r"[a-z0-9]+", clause)).difference(
                    _NEGATIVE_CONSTRAINT_IGNORED_TERMS
                )
                if clause_terms and clause_terms.issubset(objective_terms):
                    source_ids.add(str(node.get("id") or ""))
                    break
    return source_ids


def shared_only_active_deferment(
    active_objective_terms: dict[str, set[str]],
    prunable_active_source_ids: set[str],
    *,
    include_all_active_source_slices: bool,
    high_confidence_active_source_ids: set[str],
) -> tuple[list[str], set[str], bool, bool]:
    """Defer weak automatic skills and report when none has positive evidence."""

    source_ids_by_term: dict[str, set[str]] = {}
    for source_node_id, terms in active_objective_terms.items():
        for term in terms:
            source_ids_by_term.setdefault(term, set()).add(source_node_id)
    discriminative_terms = sorted(
        term
        for term, source_ids in source_ids_by_term.items()
        if len(source_ids) == 1
    )
    if include_all_active_source_slices:
        return discriminative_terms, set(), False, False
    declared_skill_source_ids = (
        prunable_active_source_ids.intersection(high_confidence_active_source_ids)
    )
    if declared_skill_source_ids:
        return (
            discriminative_terms,
            prunable_active_source_ids.difference(declared_skill_source_ids),
            False,
            False,
        )
    if not discriminative_terms:
        if 0 < len(prunable_active_source_ids) <= 3:
            return discriminative_terms, set(), False, True
        deferred_source_ids = set(prunable_active_source_ids)
        return discriminative_terms, deferred_source_ids, bool(deferred_source_ids), False
    discriminative_term_set = set(discriminative_terms)
    return (
        discriminative_terms,
        {
            source_node_id
            for source_node_id, terms in active_objective_terms.items()
            if source_node_id in prunable_active_source_ids
            and terms
            and terms.isdisjoint(discriminative_term_set)
        },
        False,
        False,
    )
