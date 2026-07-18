"""Activation eligibility for harvested source roles."""

from __future__ import annotations


EVIDENCE_ONLY_SOURCE_TYPES = frozenset({"test_fixture"})
INSTRUCTION_BEARING_SOURCE_TYPES = frozenset(
    {
        "agent_operating_contract",
        "cursor_rule",
        "github_process",
        "scoped_packet_seed",
        "skill_definition",
        "workflow_prompt",
    }
)


def is_activation_eligible_source_type(value: object) -> bool:
    """Return whether a harvested source role may shape a live packet."""

    return str(value or "") not in EVIDENCE_ONLY_SOURCE_TYPES


def is_instruction_bearing_source_type(value: object) -> bool:
    """Return whether a source role may directly define packet instructions."""

    return str(value or "") in INSTRUCTION_BEARING_SOURCE_TYPES
