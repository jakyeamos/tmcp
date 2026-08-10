"""Small text-matching primitives shared by routing and admission policy."""

from __future__ import annotations

import re


_NEGATION_PREFIX = re.compile(
    r"(?:^|[\s,;:])(?:no|without|excluding|exclude|omit|omitting|avoid|avoiding|"
    r"never|not|do\s+not|don't)\s+(?:(?:a|an|any|the|actual|automatic|external|"
    r"final|production|public)\s+)?$",
    re.IGNORECASE,
)
_COORDINATED_NEGATION_PREFIX = re.compile(
    r"(?:^|[\s,;:])(?:no|without|excluding|exclude|omit|omitting|avoid|avoiding|"
    r"never|not|do\s+not|don't)\s+(?:[a-z0-9-]+\s+){0,3}(?:or|and)\s+$",
    re.IGNORECASE,
)
_NEGATION_SUFFIX = re.compile(
    r"^\s+(?:is\s+|are\s+)?(?:out\s+of\s+scope|excluded|not\s+requested|"
    r"not\s+authorized)\b",
    re.IGNORECASE,
)


def affirmed_terms_in_text(text: str, terms: tuple[str, ...]) -> list[str]:
    """Return signal terms present outside explicit local scope exclusions."""

    lower = text.lower()
    matched: list[str] = []
    for term in terms:
        pieces = [piece for piece in re.split(r"[\s_/-]+", term.lower()) if piece]
        if not pieces:
            continue
        pattern = re.compile(
            r"(?<![a-z0-9])"
            + r"[\s_/-]+".join(re.escape(piece) for piece in pieces)
            + r"(?![a-z0-9])"
        )
        for occurrence in pattern.finditer(lower):
            prefix = lower[max(0, occurrence.start() - 48) : occurrence.start()]
            suffix = lower[occurrence.end() : occurrence.end() + 32]
            if (
                _NEGATION_PREFIX.search(prefix)
                or _COORDINATED_NEGATION_PREFIX.search(prefix)
                or _NEGATION_SUFFIX.search(suffix)
            ):
                continue
            matched.append(term)
            break
    return matched
