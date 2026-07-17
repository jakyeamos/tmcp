"""Activation eligibility for harvested source roles."""

from __future__ import annotations


EVIDENCE_ONLY_SOURCE_TYPES = frozenset({"test_fixture"})


def is_activation_eligible_source_type(value: object) -> bool:
    """Return whether a harvested source role may shape a live packet."""

    return str(value or "") not in EVIDENCE_ONLY_SOURCE_TYPES
