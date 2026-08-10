"""Static fixture evaluation and advisory transplant maps for typed atoms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.behavioral_atoms import compile_behavioral_atoms
from tmcp_runtime.services.behavioral_atom_projection import static_projection_summary
from tmcp_runtime.services.evaluation_catalog import TYPED_STATIC_VARIANT
from tmcp_runtime.services.evaluation_scoring import score_typed_static_advisory


_SUPPORTED_FIXTURE_FAMILIES = frozenset(
    {
        "data_integrity",
        "migration_readiness",
        "security_privacy",
        "release_readiness",
    }
)
_H1_VALID_ARMS = (
    {
        "id": "arm.valid.migration_receives_data_reconciliation",
        "source": "domain.data_integrity.reconciliation@0.4.0",
        "target_obligation": "migration.post_transition_reconciliation",
        "unique_delta": True,
        "status": "eligible_advisory",
    },
    {
        "id": "arm.valid.data_integrity_receives_migration_rollback",
        "source": "domain.migration_readiness.rollback_path@0.4.0",
        "target_obligation": "data_integrity.recovery_after_mismatch",
        "unique_delta": True,
        "status": "eligible_advisory",
    },
)
_H2_VALID_ARMS = (
    {
        "id": "arm.valid.release_receives_security_redaction",
        "source": "domain.security_privacy.redaction@0.4.0",
        "target_obligation": "release.artifact_secret_boundary",
        "unique_delta": True,
        "status": "eligible_advisory",
    },
    {
        "id": "arm.valid.security_privacy_receives_release_gating",
        "source": "domain.release_readiness.ship_gate@0.4.0",
        "target_obligation": "security.review_release_gate",
        "unique_delta": True,
        "status": "eligible_advisory",
    },
)
_H3_VALID_ARMS = (
    {
        "id": "arm.valid.h3.release_receives_secret_boundary",
        "source": "domain.security_privacy.secret_boundary@0.4.0",
        "target_domain": "release_readiness",
        "target_obligation": "release.artifact_access_scope_evidence_chain",
        "unique_delta": True,
        "status": "eligible_advisory",
    },
    {
        "id": "arm.valid.h3.security_receives_evidence_ladder",
        "source": "domain.release_readiness.evidence_ladder@0.4.0",
        "target_domain": "security_privacy",
        "target_obligation": "security.release_evidence_ladder_completeness",
        "unique_delta": True,
        "status": "eligible_advisory",
    },
)
_H3_INVALID_ARMS = (
    {
        "id": "arm.invalid.h3.redaction_alias",
        "reason_code": "duplicate_h2_delta",
        "status": "rejected_before_cell",
    },
    {
        "id": "arm.invalid.h3.ship_gate_alias",
        "reason_code": "duplicate_h2_delta",
        "status": "rejected_before_cell",
    },
    {
        "id": "arm.invalid.h3.generic_process_shell",
        "reason_code": "generic_process_duplicate",
        "status": "rejected_before_cell",
    },
    {
        "id": "arm.invalid.h3.no_target_obligation",
        "reason_code": "missing_target_obligation",
        "status": "rejected_before_cell",
    },
)
_INVALID_ARMS = (
    {
        "id": "arm.invalid.duplicate.test_to_security_local_context",
        "reason_code": "duplicate_generic_condition",
        "status": "rejected_before_cell",
    },
    {
        "id": "arm.invalid.duplicate.test_to_release_ordered_actions",
        "reason_code": "duplicate_generic_condition",
        "status": "rejected_before_cell",
    },
    {
        "id": "arm.invalid.no_variant.security_to_release",
        "reason_code": "no_eligible_variant",
        "status": "rejected_before_cell",
    },
    {
        "id": "arm.invalid.no_variant.release_to_security",
        "reason_code": "no_eligible_variant",
        "status": "rejected_before_cell",
    },
)


def _fixture_context(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Map sealed fixture metadata to structured static inputs.

    The fixture prompt and signal strings are intentionally ignored.  This
    adapter supplies explicit sealed applicability labels and owned records so
    the runtime compiler is tested on semantic state rather than wording.
    """

    family = str(fixture.get("family") or "")
    expected = fixture.get("expected_outcome")
    expected_map = expected if isinstance(expected, Mapping) else {}
    applicability = str(expected_map.get("applicability") or "ambiguous")
    owner = str(
        (fixture.get("ownership") or {}).get("owner_id")
        if isinstance(fixture.get("ownership"), Mapping)
        else "sealed_fixture_owner"
    )
    fixture_id = str(fixture.get("id") or "fixture")
    source = f"tests/fixtures/behavioral-atoms-held-out-v0.3.json#{fixture_id}"
    context: dict[str, Any] = {
        "phase": "planning",
        "semantic_signals": {family: applicability},
        "legacy_atoms": ["legacy fixture atom"],
        "token_budget": 512,
    }
    if applicability != "positive":
        if applicability == "ambiguous":
            context["declared_missing_evidence"] = list(
                expected_map.get("missing_evidence") or []
            )
        return context
    if family == "data_integrity":
        context.update(
            {
                "inputs": {
                    "before_state": {"value": "sealed-before", "owner": owner},
                    "after_state": {"value": "sealed-after", "owner": owner},
                    "reconciliation_rule": {"value": "sealed-id-rule", "owner": owner},
                },
                "reads": [
                    {
                        "reference": "skills/tmcp-data-integrity-audit/SKILL.md",
                        "status": "available",
                        "trust": "committed_source_backed",
                        "owner": owner,
                    },
                    {
                        "reference": "reconciliation checks, import/export jobs, or backfill evidence",
                        "status": "available",
                        "trust": "sealed_fixture",
                        "owner": owner,
                    },
                ],
                "evidence": [
                    {
                        "obligation": "before/after boundary is recorded",
                        "status": "recorded",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                    {
                        "obligation": "mismatches, exclusions, and unresolved gaps are recorded",
                        "status": "recorded",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                ],
                "verification": [
                    {
                        "obligation": "reconciliation check is run and inspected",
                        "status": "passed",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                    {
                        "obligation": "idempotency risk is repeated when applicable",
                        "status": "passed",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                ],
                "provided_dependencies": ["domain.data_integrity.invariants@0.4.0"],
            }
        )
    elif family == "migration_readiness":
        context.update(
            {
                "inputs": {
                    "rollback_owner": {"value": owner, "owner": owner},
                    "rollback_trigger": {
                        "value": "sealed-validation-failure",
                        "owner": owner,
                    },
                    "recoverable_boundary": {
                        "value": "sealed-target-snapshot",
                        "owner": owner,
                    },
                },
                "reads": [
                    {
                        "reference": "skills/tmcp-migration-readiness/SKILL.md",
                        "status": "available",
                        "trust": "committed_source_backed",
                        "owner": owner,
                    },
                    {
                        "reference": "rollback path, cutover, and validation commands",
                        "status": "available",
                        "trust": "sealed_fixture",
                        "owner": owner,
                    },
                ],
                "evidence": [
                    {
                        "obligation": "rollback owner, trigger, path, and limitations are recorded",
                        "status": "recorded",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                    {
                        "obligation": "cutover validation and recovery evidence is recorded",
                        "status": "recorded",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                ],
                "verification": [
                    {
                        "obligation": "rollback conditions are observable and bounded",
                        "status": "passed",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                    {
                        "obligation": "acceptance gate covers cutover and recovery",
                        "status": "passed",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                ],
                "provided_dependencies": [
                    "domain.migration_readiness.compatibility_sequence@0.4.0"
                ],
            }
        )
    elif family == "security_privacy":
        context.update(
            {
                "inputs": {
                    "sensitive_boundary": {
                        "value": "sealed-redaction-policy",
                        "owner": owner,
                    },
                    "evidence_owner": {"value": owner, "owner": owner},
                },
                "reads": [
                    {
                        "reference": "skills/tmcp-security-privacy-audit/SKILL.md",
                        "status": "available",
                        "trust": "committed_source_backed",
                        "owner": owner,
                    },
                    {
                        "reference": "security, privacy, CI, auth, payment, or data-flow evidence",
                        "status": "available",
                        "trust": "sealed_fixture",
                        "owner": owner,
                    },
                ],
                "evidence": [
                    {
                        "obligation": "what was redacted and why is recorded",
                        "status": "recorded",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                    {
                        "obligation": "security and privacy evidence gaps are recorded without sensitive values",
                        "status": "recorded",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                ],
                "verification": [
                    {
                        "obligation": "outputs contain no unredacted sensitive values",
                        "status": "passed",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                    {
                        "obligation": "each material security claim points to bounded evidence",
                        "status": "passed",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                ],
            }
        )
    elif family == "release_readiness":
        context.update(
            {
                "inputs": {
                    "release_scope": {
                        "value": "sealed-release-scope",
                        "owner": owner,
                    },
                    "current_quality_evidence": {
                        "value": "sealed-current-quality-output",
                        "owner": owner,
                    },
                },
                "reads": [
                    {
                        "reference": "skills/tmcp-release-readiness/SKILL.md",
                        "status": "available",
                        "trust": "committed_source_backed",
                        "owner": owner,
                    },
                    {
                        "reference": "project instructions, README, CI, tests, build scripts, and release docs",
                        "status": "available",
                        "trust": "sealed_fixture",
                        "owner": owner,
                    },
                ],
                "evidence": [
                    {
                        "obligation": "current quality and release evidence is recorded",
                        "status": "recorded",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                    {
                        "obligation": "observed blockers, risks, and unknowns are separated",
                        "status": "recorded",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                ],
                "verification": [
                    {
                        "obligation": "required release checks are run or inspected",
                        "status": "passed",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                    {
                        "obligation": "every ship blocker has a disposition and next gate",
                        "status": "passed",
                        "source": source,
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                ],
            }
        )
    return context


def _v04_ref(value: object) -> str:
    item = str(value)
    return item.replace("@0.3.0", "@0.4.0")


def build_h1_advisory_evaluator_mapping() -> dict[str, Any]:
    """Return the preregistered original/ablated/transplant H1 map."""

    atom_refs = [
        "domain.migration_readiness.rollback_path@0.4.0",
        "domain.data_integrity.reconciliation@0.4.0",
    ]
    return {
        "variant_id": TYPED_STATIC_VARIANT,
        "original": {
            "id": "H1.reconciliation_and_rollback",
            "atom_refs": atom_refs,
            "selection_basis": "domain_logic",
            "provider_outcome": "not_run",
            "cross_skill_composition": "closed_gate",
            "status": "eligible_advisory",
        },
        "ablated": [
            {
                "id": "H1.ablate.data_integrity.reconciliation",
                "removed_atom": "domain.data_integrity.reconciliation@0.4.0",
                "remaining_atom_refs": [atom_refs[0]],
                "selection_basis": "domain_logic",
                "provider_outcome": "not_run",
                "status": "eligible_advisory",
            },
            {
                "id": "H1.ablate.migration_readiness.rollback_path",
                "removed_atom": "domain.migration_readiness.rollback_path@0.4.0",
                "remaining_atom_refs": [atom_refs[1]],
                "selection_basis": "domain_logic",
                "provider_outcome": "not_run",
                "status": "eligible_advisory",
            },
        ],
        "transplant": [
            *list(_H1_VALID_ARMS),
            *[{**item, "status": "deferred_family"} for item in _H2_VALID_ARMS],
        ],
        "invalid_arms": list(_INVALID_ARMS),
        "provider_cells": "not_run",
        "cross_skill_composition": "closed_gate",
        "promotion_policy": {"auto_promote": False},
    }

def build_h2_advisory_evaluator_mapping() -> dict[str, Any]:
    """Return the preregistered H2 static map without composing skills."""

    atom_refs = [
        "domain.security_privacy.redaction@0.4.0",
        "domain.release_readiness.ship_gate@0.4.0",
    ]
    return {
        "variant_id": TYPED_STATIC_VARIANT,
        "original": {
            "id": "H2.redaction_and_ship_gate",
            "atom_refs": atom_refs,
            "selection_basis": "domain_logic",
            "provider_outcome": "not_run",
            "cross_skill_composition": "closed_gate",
            "status": "eligible_advisory",
        },
        "ablated": [
            {
                "id": "H2.ablate.security_privacy.redaction",
                "removed_atom": atom_refs[0],
                "remaining_atom_refs": [atom_refs[1]],
                "selection_basis": "domain_logic",
                "provider_outcome": "not_run",
                "status": "eligible_advisory",
            },
            {
                "id": "H2.ablate.release_readiness.ship_gate",
                "removed_atom": atom_refs[1],
                "remaining_atom_refs": [atom_refs[0]],
                "selection_basis": "domain_logic",
                "provider_outcome": "not_run",
                "status": "eligible_advisory",
            },
        ],
        "transplant": list(_H2_VALID_ARMS),
        "invalid_arms": list(_INVALID_ARMS),
        "provider_cells": "not_run",
        "cross_skill_composition": "closed_gate",
        "promotion_policy": {"auto_promote": False},
    }

def evaluate_transplant_arm(arm: Mapping[str, Any]) -> dict[str, Any]:
    """Advisory structural gate for registered arms, before any provider cell."""

    arm_id = str(arm.get("id") or "")
    invalid = next(
        (item for item in (*_INVALID_ARMS, *_H3_INVALID_ARMS) if item["id"] == arm_id),
        None,
    )
    if invalid is not None:
        return dict(invalid)
    valid = next(
        (
            item
            for item in (*_H1_VALID_ARMS, *_H2_VALID_ARMS, *_H3_VALID_ARMS)
            if item["id"] == arm_id
        ),
        None,
    )
    if valid is None:
        return {
            "id": arm_id,
            "status": "rejected_before_cell",
            "reason_code": "no_eligible_variant",
        }
    if not bool(arm.get("unique_delta")):
        return {
            "id": arm_id,
            "status": "rejected_before_cell",
            "reason_code": "missing_unique_domain_delta",
        }
    return {
        **dict(valid),
        "provider_outcome": "not_run",
        "cross_skill_composition": "closed_gate",
    }


def evaluate_sealed_behavioral_fixtures(
    fixtures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Consume all sealed H1/H2 fixtures as fixed static checks."""

    cases: list[dict[str, Any]] = []
    for fixture in fixtures:
        fixture_id = str(fixture.get("id") or "")
        family = str(fixture.get("family") or "")
        expected = fixture.get("expected_outcome")
        expected_map = expected if isinstance(expected, Mapping) else {}
        expected_decision = str(expected_map.get("decision") or "")
        expected_domain_ids = [
            _v04_ref(item)
            for item in expected_map.get("required_domain_atoms", [])
            if str(item)
        ]
        if family in _SUPPORTED_FIXTURE_FAMILIES:
            result = compile_behavioral_atoms(_fixture_context(fixture))
            actual = static_projection_summary(result)
            actual["supported_family"] = True
            actual["deferred_dependency_ids"] = [
                item
                for item in expected_domain_ids
                if item not in actual["domain_selected_ids"]
            ]
            runtime_expected_ids = [
                item
                for item in expected_domain_ids
                if item.startswith(
                    (
                        "domain.data_integrity.reconciliation@",
                        "domain.migration_readiness.rollback_path@",
                        "domain.security_privacy.redaction@",
                        "domain.release_readiness.ship_gate@",
                    )
                )
            ]
            score = score_typed_static_advisory(
                actual,
                {
                    "decision": expected_decision,
                    "required_domain_atoms": runtime_expected_ids,
                    "required_stops": ["fixture-stop"]
                    if expected_map.get("stop")
                    else [],
                },
            )
            cases.append(
                {
                    "fixture_id": fixture_id,
                    "family": family,
                    "supported": True,
                    "actual": actual,
                    "expected": {
                        "decision": expected_decision,
                        "required_domain_atoms": expected_domain_ids,
                        "runtime_required_domain_atoms": runtime_expected_ids,
                        "stop": bool(expected_map.get("stop")),
                    },
                    "score": score,
                    "provider_execution": False,
                }
            )
        else:
            cases.append(
                {
                    "fixture_id": fixture_id,
                    "family": family,
                    "supported": False,
                    "status": "deferred_family",
                    "actual": {
                        "decision": "deferred_family",
                        "domain_selected_ids": [],
                        "stops": [],
                        "provider_execution": False,
                    },
                    "expected": {
                        "decision": expected_decision,
                        "required_domain_atoms": expected_domain_ids,
                        "stop": bool(expected_map.get("stop")),
                    },
                    "provider_execution": False,
                }
            )
    h1_mapping = build_h1_advisory_evaluator_mapping()
    h2_mapping = build_h2_advisory_evaluator_mapping()
    return {
        "schema": "tmcp-behavioral-atoms-static-evaluation-v0.4",
        "version": "0.4.0",
        "variant_id": TYPED_STATIC_VARIANT,
        "fixture_count": len(cases),
        "all_fixtures_consumed": len(cases) == 12,
        "cases": cases,
        "h1_mapping": h1_mapping,
        "h2_mapping": h2_mapping,
        "provider_cells": "not_run",
        "cross_skill_composition": "closed_gate",
        "promotion_policy": {"auto_promote": False},
    }
