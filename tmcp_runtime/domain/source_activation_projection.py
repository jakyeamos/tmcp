"""Cited-source filtering for metadata that enters active semantic packets."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from .harvest_nodes import (
    classify_atoms,
    ordered_unique,
    routing_metadata_for,
)
from .harvest_node_policy import node_source_role


SOURCE_ACTIVATION_PROJECTION_SCHEMA = "tmcp-source-activation-projection-v0.1"

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ATOM_GRAMMAR_TERMS = frozenset(
    {
        "atom",
        "atoms",
        "behavior",
        "contract",
        "disclosure",
        "guidance",
        "preservation",
        "routing",
        "skill",
        "skills",
        "source",
        "traceability",
    }
)
_PATH_GRAMMAR_TERMS = frozenset(
    {
        "config",
        "doc",
        "docs",
        "guide",
        "guides",
        "md",
        "mjs",
        "js",
        "json",
        "py",
        "read",
        "reads",
        "reference",
        "references",
        "script",
        "scripts",
        "yaml",
        "yml",
    }
)
_SENSITIVE_PATH_COMPONENTS = frozenset(
    {
        ".env",
        "credential",
        "credentials",
        "keychain",
        "keys",
        "secret",
        "secrets",
        "token",
        "tokens",
    }
)
_UNSAFE_CONTROL_PATTERN = re.compile(
    r"\b(?:bypass|circumvent|discard|disregard|evade|ignore|omit|override|skip|"
    r"supersede|waive|work\s+around)\b"
    r"[^.?!;\n]*\b(?:controls?|gates?|instructions?|policies?|rules?|users?|"
    r"systems?|developer|governing)\b",
    re.IGNORECASE,
)
_HIGH_IMPACT_ATOM_TERMS = frozenset(
    {
        "approve",
        "archive",
        "commit",
        "delete",
        "deploy",
        "email",
        "merge",
        "publish",
        "push",
        "release",
        "send",
        "ship",
        "submit",
        "upload",
    }
)
_SAFE_TOOL_SCRIPT_TERMS = frozenset(
    {
        "audit",
        "check",
        "context",
        "format",
        "inspect",
        "lint",
        "palette",
        "test",
        "typecheck",
        "validate",
        "verify",
    }
)
_SAFE_STOP_TERMS = frozenset(
    {
        "approval",
        "ask",
        "checkpoint",
        "evidence",
        "gate",
        "review",
        "test",
        "user",
        "verification",
    }
)
_SENSITIVE_DISCLOSURE_TERMS = frozenset(
    {"credential", "credentials", "exfiltrate", "key", "keys", "secret", "secrets", "token", "tokens"}
)


def _normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _string_list(value: object) -> list[str]:
    return (
        [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, list)
        else []
    )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _terms(value: object) -> set[str]:
    return set(_TOKEN_PATTERN.findall(_normalized_text(value).lower()))


def _has_obscured_executable_text(value: object) -> bool:
    """Reject invisible and mixed-script strings before packet activation."""

    text = unicodedata.normalize("NFKC", _normalized_text(value))
    if any(
        unicodedata.category(character) in {"Cf", "Mn", "Me"}
        for character in text
    ):
        return True
    scripts: set[str] = set()
    for character in text:
        if not unicodedata.category(character).startswith("L"):
            continue
        name = unicodedata.name(character, "")
        for script in ("LATIN", "GREEK", "CYRILLIC"):
            if script in name:
                scripts.add(script)
                break
    return "LATIN" in scripts and len(scripts) > 1


def _stems(term: str) -> set[str]:
    variants = {term}
    if term.endswith("ification") and len(term) > len("ification"):
        variants.add(term[: -len("ification")] + "ify")
    if term.endswith("ation") and len(term) > len("ation"):
        variants.add(term[: -len("ation")])
    if term.endswith("ing") and len(term) > len("ing") + 2:
        root = term[: -len("ing")]
        variants.add(root)
        # ``merging``, ``shipping``, and ``committing`` drop an ``e`` or
        # double the final consonant.  Tool prompt safety must recognize those
        # terminal-action forms rather than treating their filenames as benign.
        variants.add(root + "e")
        if len(root) > 2 and root[-1] == root[-2]:
            variants.add(root[:-1])
    if term.endswith("ed") and len(term) > len("ed") + 2:
        root = term[: -len("ed")]
        variants.add(root)
        variants.add(root + "e")
        if len(root) > 2 and root[-1] == root[-2]:
            variants.add(root[:-1])
    if term.endswith("es") and len(term) > len("es") + 2:
        variants.add(term[: -len("es")])
    if term.endswith("s") and len(term) > len("s") + 2:
        variants.add(term[: -len("s")])
    return {variant for variant in variants if len(variant) >= 3}


def _term_is_grounded(term: str, evidence_terms: set[str]) -> bool:
    term_stems = _stems(term)
    return any(not term_stems.isdisjoint(_stems(candidate)) for candidate in evidence_terms)


def _cited_content(cited_source_slices: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(
        _normalized_text(item.get("content"))
        for item in cited_source_slices
        if _normalized_text(item.get("content"))
    )


def _identity_terms(node: Mapping[str, Any]) -> set[str]:
    """Return trusted classification terms, never mutable path or title labels."""

    role = node_source_role(dict(node)).replace("_", " ")
    return _terms(node.get("source_type")) | _terms(role)


def _safe_relative_path(value: str) -> bool:
    path = value.replace("\\", "/").strip()
    if (
        not path
        or _has_obscured_executable_text(path)
        or path.startswith(("/", "~"))
        or "://" in path
        or any(character in path for character in "\t\n\r;$|&")
    ):
        return False
    components = [component for component in path.split("/") if component]
    if not components or any(component in {".", ".."} for component in components):
        return False
    return not any(
        component.lower() in _SENSITIVE_PATH_COMPONENTS for component in components
    )


def _safe_atom(value: str) -> bool:
    """Keep opaque atoms declarative, not a second instruction channel."""

    if _has_obscured_executable_text(value) or not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", value
    ):
        return False
    return not _terms(value).intersection(_HIGH_IMPACT_ATOM_TERMS)


def _safe_tool_script_path(value: str) -> bool:
    """Only expose non-deploy verification helpers as agent tool suggestions."""

    name_terms = _terms(value.rsplit("/", 1)[-1])
    # A name such as ``test-and-deploy.py`` is not a verification helper just
    # because it also contains ``test``. Tool prompts are executable-adjacent
    # packet content, so reject a terminal-action script even when it has a
    # safe verification token.
    return bool(name_terms.intersection(_SAFE_TOOL_SCRIPT_TERMS)) and not _terms_include_action(
        name_terms
    )


def _terms_include_action(terms: set[str]) -> bool:
    action_stems = {
        stem for action in _HIGH_IMPACT_ATOM_TERMS for stem in _stems(action)
    }
    return any(not _stems(term).isdisjoint(action_stems) for term in terms)


def _matched_high_impact_actions(terms: set[str]) -> set[str]:
    return {
        action
        for action in _HIGH_IMPACT_ATOM_TERMS
        if any(not _stems(term).isdisjoint(_stems(action)) for term in terms)
    }


def _safe_stop_condition(value: str) -> bool:
    """Permit only a bounded pause-before-action or a benign review checkpoint."""

    terms = _terms(value)
    text = _normalized_text(value).lower()
    if (
        _has_obscured_executable_text(value)
        or _UNSAFE_CONTROL_PATTERN.search(text)
        or "stop" not in terms
    ):
        return False
    if {"ask", "user"}.issubset(terms):
        # A stop that asks before/until an action is a gate; an imperative to
        # ask the user *to perform* an action is not.  This preserves useful
        # "ask before publishing" policy without turning source prose into a
        # release/deploy instruction channel.
        pause = re.search(r"\b(?:before|until)\b", text)
        if pause is None:
            return False
        prefix_terms = _terms(text[: pause.start()])
        actions = _matched_high_impact_actions(terms)
        return (
            not _terms_include_action(prefix_terms)
            and len(actions) <= 1
            and not bool(terms.intersection(_SENSITIVE_DISCLOSURE_TERMS))
            and not re.search(r"\b(?:and\s+then|then)\b", text)
        )
    return (
        bool(terms.intersection(_SAFE_STOP_TERMS))
        and not _terms_include_action(terms)
        and not bool(terms.intersection(_SENSITIVE_DISCLOSURE_TERMS))
    )


def _path_is_grounded(value: str, evidence_terms: set[str]) -> bool:
    claim_terms = _terms(value).difference(_PATH_GRAMMAR_TERMS)
    return bool(claim_terms) and all(
        _term_is_grounded(term, evidence_terms) for term in claim_terms
    )


def _project_atoms(
    values: list[str],
    *,
    content: str,
    source_type: str,
    evidence_terms: set[str],
) -> tuple[list[str], list[str]]:
    canonical = set(classify_atoms(content, source_type))
    kept: list[str] = []
    rejected: list[str] = []
    for raw in values:
        atom = _normalized_text(raw)
        claim_terms = _terms(atom).difference(_ATOM_GRAMMAR_TERMS)
        if (
            atom
            and _safe_atom(atom)
            and not _UNSAFE_CONTROL_PATTERN.search(atom)
            and atom in canonical
        ):
            kept.append(atom)
        elif atom:
            rejected.append(atom)
    return ordered_unique(kept), ordered_unique(rejected)


def _project_source_path(
    node: Mapping[str, Any], cited_source_slices: Sequence[Mapping[str, Any]]
) -> tuple[str, list[str]]:
    """Allow an active source read only when its safe path is cited verbatim."""

    source_path = _normalized_text(node.get("relative_path"))
    cited_paths = {
        _normalized_text(item.get("relative_path"))
        for item in cited_source_slices
        if _normalized_text(item.get("relative_path"))
    }
    if _safe_relative_path(source_path) and source_path in cited_paths:
        return source_path, []
    return "", [source_path] if source_path else []


def _project_required_reads(
    values: list[str],
    *,
    canonical: Mapping[str, Any],
    evidence_terms: set[str],
) -> tuple[list[str], list[str]]:
    canonical_reads = {
        _normalized_text(item) for item in _string_list(canonical.get("required_reads"))
    }
    kept: list[str] = []
    rejected: list[str] = []
    for raw in values:
        read = _normalized_text(raw)
        if not read:
            continue
        if (
            _safe_relative_path(read)
            and not _has_obscured_executable_text(read)
            and read in canonical_reads
        ):
            kept.append(read)
        else:
            rejected.append(read)
    return ordered_unique(kept), ordered_unique(rejected)


def _project_tool_prompts(
    values: list[str], *, canonical: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    canonical_prompts = {
        _normalized_text(item)
        for item in _string_list(canonical.get("tool_script_prompts"))
    }
    kept: list[str] = []
    rejected: list[str] = []
    for raw in values:
        prompt = _normalized_text(raw)
        if (
            prompt
            and _safe_relative_path(prompt)
            and not _has_obscured_executable_text(prompt)
            and _safe_tool_script_path(prompt)
            and prompt in canonical_prompts
        ):
            kept.append(prompt)
        elif prompt:
            rejected.append(prompt)
    return ordered_unique(kept), ordered_unique(rejected)


def _project_stop_conditions(
    values: list[str], *, canonical: Mapping[str, Any]
) -> tuple[list[str], list[str]]:
    canonical_stops = {
        _normalized_text(item): item
        for item in _string_list(canonical.get("stop_conditions"))
    }
    kept: list[str] = []
    rejected: list[str] = []
    for raw in values:
        condition = _normalized_text(raw)
        canonical_condition = canonical_stops.get(condition)
        if (
            canonical_condition
            and _safe_stop_condition(condition)
            and not _has_obscured_executable_text(condition)
            and not _UNSAFE_CONTROL_PATTERN.search(condition)
        ):
            kept.append(canonical_condition)
        elif condition:
            rejected.append(condition)
    return ordered_unique(kept), ordered_unique(rejected)


def project_source_activation(
    node: Mapping[str, Any],
    cited_source_slices: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return only cited-source metadata that may enter an active packet."""

    content = _cited_content(cited_source_slices)
    if not content:
        metadata = _mapping(node.get("routing_metadata"))
        return {
            "schema": SOURCE_ACTIVATION_PROJECTION_SCHEMA,
            "source_path": "",
            "behavior_atoms": [],
            "routing_metadata": {
                "required_reads": [],
                "tool_script_prompts": [],
                "stop_conditions": [],
            },
            "rejected": {
                "source_path": [
                    _normalized_text(node.get("relative_path"))
                ]
                if _normalized_text(node.get("relative_path"))
                else [],
                "behavior_atoms": _string_list(node.get("behavior_atoms")),
                "required_reads": _string_list(metadata.get("required_reads")),
                "tool_script_prompts": _string_list(
                    metadata.get("tool_script_prompts")
                ),
                "stop_conditions": _string_list(metadata.get("stop_conditions")),
            },
        }
    evidence_terms = _terms(content).union(_identity_terms(node))
    metadata = _mapping(node.get("routing_metadata"))
    canonical = routing_metadata_for(str(node.get("relative_path") or ""), content)
    atoms, rejected_atoms = _project_atoms(
        _string_list(node.get("behavior_atoms")),
        content=content,
        source_type=str(node.get("source_type") or ""),
        evidence_terms=evidence_terms,
    )
    reads, rejected_reads = _project_required_reads(
        _string_list(metadata.get("required_reads")),
        canonical=canonical,
        evidence_terms=evidence_terms,
    )
    prompts, rejected_prompts = _project_tool_prompts(
        _string_list(metadata.get("tool_script_prompts")),
        canonical=canonical,
    )
    stops, rejected_stops = _project_stop_conditions(
        _string_list(metadata.get("stop_conditions")),
        canonical=canonical,
    )
    source_path, rejected_source_path = _project_source_path(
        node, cited_source_slices
    )
    return {
        "schema": SOURCE_ACTIVATION_PROJECTION_SCHEMA,
        "source_path": source_path,
        "behavior_atoms": atoms,
        "routing_metadata": {
            "required_reads": reads,
            "tool_script_prompts": prompts,
            "stop_conditions": stops,
        },
        "rejected": {
            "source_path": rejected_source_path,
            "behavior_atoms": rejected_atoms,
            "required_reads": rejected_reads,
            "tool_script_prompts": rejected_prompts,
            "stop_conditions": rejected_stops,
        },
    }


def project_source_node_activation(node: Mapping[str, Any]) -> dict[str, Any]:
    """Project a selected compatibility node against its visible source excerpt.

    Compatibility routing has no host proposal citations, but it still needs a
    source-backed activation boundary.  The harvested excerpt is the exact
    source material that direct composition can use, so bind metadata to that
    text rather than adapter-supplied labels.
    """

    relative_path = _normalized_text(node.get("relative_path") or node.get("path"))
    content = _normalized_text(node.get("excerpt") or node.get("signal_excerpt"))
    return project_source_activation(
        node,
        [
            {
                "source_node_id": _normalized_text(node.get("id")),
                "relative_path": relative_path,
                "content": content,
            }
        ],
    )


def project_source_node_for_composition(node: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with all activation-facing harvest metadata re-derived.

    Selection, compatibility packets, and semantic packets must all see the
    same bounded source-derived metadata.  This keeps adapter-provided atom
    labels, reads, prompts, stops, gates, and phase hints from becoming a
    parallel instruction plane.
    """

    projected = dict(node)
    content = _normalized_text(node.get("excerpt") or node.get("signal_excerpt"))
    relative_path = _normalized_text(node.get("relative_path") or node.get("path"))
    canonical = routing_metadata_for(relative_path, content)
    activation = project_source_node_activation(node)
    declared_loads = _string_list(canonical.get("declared_loads"))
    canonical["declared_loads"] = ordered_unique(declared_loads)[:12]
    canonical.update(dict(activation.get("routing_metadata") or {}))
    projected["behavior_atoms"] = _string_list(activation.get("behavior_atoms"))
    projected["routing_metadata"] = canonical
    projected["activation_source_path"] = str(activation.get("source_path") or "")
    return projected
