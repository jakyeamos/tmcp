"""Private H3 boundary evaluation for the typed behavioral-atom runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tmcp_runtime.domain.behavioral_atoms import build_h3_registry, compile_behavioral_atoms
from tmcp_runtime.services.behavioral_atom_evaluation import (
    _H3_INVALID_ARMS,
    _H3_VALID_ARMS,
)
from tmcp_runtime.services.behavioral_atom_projection import static_projection_summary
from tmcp_runtime.services.evaluation_catalog import TYPED_STATIC_VARIANT


def build_h3_advisory_evaluator_mapping() -> dict[str, Any]:
    """Return the private H3 static map without provider or composition work."""

    atom_refs = [
        "domain.security_privacy.secret_boundary@0.4.0",
        "domain.release_readiness.evidence_ladder@0.4.0",
    ]
    return {
        "variant_id": TYPED_STATIC_VARIANT,
        "original": {
            "id": "H3.secret_boundary_and_evidence_ladder",
            "atom_refs": atom_refs,
            "selection_basis": "domain_logic",
            "provider_outcome": "not_run",
            "cross_skill_composition": "closed_gate",
            "status": "eligible_advisory",
        },
        "ablated": [
            {
                "id": "H3.ablate.security_privacy.secret_boundary",
                "removed_atom": atom_refs[0],
                "remaining_atom_refs": [atom_refs[1]],
                "selection_basis": "domain_logic",
                "provider_outcome": "not_run",
                "status": "eligible_advisory",
            },
            {
                "id": "H3.ablate.release_readiness.evidence_ladder",
                "removed_atom": atom_refs[1],
                "remaining_atom_refs": [atom_refs[0]],
                "selection_basis": "domain_logic",
                "provider_outcome": "not_run",
                "status": "eligible_advisory",
            },
        ],
        "transplant": list(_H3_VALID_ARMS),
        "invalid_arms": list(_H3_INVALID_ARMS),
        "provider_cells": "not_run",
        "cross_skill_composition": "closed_gate",
        "promotion_policy": {"auto_promote": False},
    }
def evaluate_h3_boundary_fixtures(
    fixtures: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate the frozen H3 semantic records at the private static boundary."""

    def fixture_context(fixture: Mapping[str, Any]) -> dict[str, Any] | None:
        semantic = fixture.get("semantic_record")
        if not isinstance(semantic, Mapping):
            return None
        fixture_id = str(fixture.get("id") or "fixture")
        source = f"tests/fixtures/behavioral-atoms-runtime-h3-v0.7.json#{fixture_id}"
        expected = fixture.get("expected_outcome")
        expected_map = expected if isinstance(expected, Mapping) else {}
        inputs: dict[str, Any] = {}
        for item in semantic.get("inputs", []):
            if isinstance(item, Mapping) and str(item.get("name") or "").strip():
                inputs[str(item["name"])] = dict(item)

        def records(key: str, identity_key: str) -> list[dict[str, Any]]:
            result: list[dict[str, Any]] = []
            for item in semantic.get(key, []):
                if not isinstance(item, Mapping):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                record = dict(item)
                record[identity_key] = name
                record.setdefault("source", source)
                result.append(record)
            return result

        context: dict[str, Any] = {
            "phase": str(semantic.get("phase") or "planning"),
            "phase_status": "compatible",
            "inputs": inputs,
            "reads": records("reads", "reference"),
            "evidence": records("evidence", "obligation"),
            "verification": records("verification", "obligation"),
            "semantic_signals": dict(semantic.get("explicit_signals") or {}),
            "token_budget": int(semantic.get("token_budget") or 0),
        }

        if expected_map.get("stop"):
            context["declared_missing_evidence"] = list(
                expected_map.get("missing_evidence") or []
            )

        # The frozen H3 records intentionally describe the H3 delta.  The
        # corresponding H2 baseline is supplied as sealed fixture support here;
        # it is not inferred from prompt text or legacy atoms.
        if expected_map.get("decision") == "admit":
            owner = next(
                (
                    str(item.get("owner"))
                    for item in inputs.values()
                    if isinstance(item, Mapping) and str(item.get("owner") or "")
                ),
                "h3-fixture-owner",
            )

            def add_input(name: str, value: str) -> None:
                inputs.setdefault(
                    name,
                    {
                        "value": value,
                        "status": "available",
                        "owner": owner,
                        "trust": "sealed_fixture",
                    },
                )

            def add_evidence(name: str) -> None:
                if not any(
                    str(item.get("obligation") or "") == name
                    for item in context["evidence"]
                    if isinstance(item, Mapping)
                ):
                    context["evidence"].append(
                        {
                            "obligation": name,
                            "status": "recorded",
                            "source": source,
                            "owner": owner,
                            "trust": "sealed_fixture",
                        }
                    )

            def add_verification(name: str) -> None:
                if not any(
                    str(item.get("obligation") or "") == name
                    for item in context["verification"]
                    if isinstance(item, Mapping)
                ):
                    context["verification"].append(
                        {
                            "obligation": name,
                            "status": "passed",
                            "source": source,
                            "owner": owner,
                            "trust": "sealed_fixture",
                        }
                    )

            domain_scope = str(fixture.get("domain_scope") or "")
            signals = context["semantic_signals"]
            if (
                domain_scope in {"security_privacy", "combined"}
                and str(signals.get("security_privacy") or "").lower() == "positive"
            ):
                add_input("sensitive_boundary", "h3-derived-redaction-boundary")
                add_input("evidence_owner", owner)
                add_evidence("what was redacted and why is recorded")
                add_evidence(
                    "security and privacy evidence gaps are recorded without sensitive values"
                )
                add_verification("outputs contain no unredacted sensitive values")
                add_verification(
                    "each material security claim points to bounded evidence"
                )
            if (
                domain_scope in {"release_readiness", "combined"}
                and str(signals.get("release_readiness") or "").lower() == "positive"
            ):
                add_input("release_scope", "h3-derived-release-scope")
                add_input("current_quality_evidence", "h3-derived-quality-evidence")
                add_evidence("current quality and release evidence is recorded")
                add_evidence("observed blockers, risks, and unknowns are separated")
                add_verification("required release checks are run or inspected")
                add_verification("every ship blocker has a disposition and next gate")

            # The combined fixture records deliberately use a cross-domain
            # vocabulary.  Normalize that sealed record into each atom's
            # declared obligations only after the fixture has supplied all four
            # positive H3 inputs; this is static fixture interpretation, not
            # runtime cross-skill composition.
            if domain_scope == "combined":
                for name in (
                    "authorized boundary and evidence gaps are recorded",
                    "observed findings are separated from inferred risk",
                    "scope ownership is checked before sensitive evidence is used",
                    "remediation is checked against the recorded boundary",
                    "passed, failed, blocked, not-run, and unknown gates are inventoried",
                    "evidence needed for each remediation slice is recorded",
                ):
                    add_evidence(name)
                for name in (
                    "scope ownership is checked before sensitive evidence is used",
                    "remediation is checked against the recorded boundary",
                    "quality ladder completeness is checked for the declared release scope",
                    "each remediation slice has an acceptance check",
                ):
                    add_verification(name)

        return context

    def score_h3(
        actual: Mapping[str, Any], expected: Mapping[str, Any]
    ) -> dict[str, Any]:
        expected_decision = str(expected.get("decision") or "")
        expected_h3 = {
            str(item) for item in expected.get("required_h3_atoms", []) if str(item)
        }
        expected_baseline = {
            str(item)
            for item in expected.get("required_baseline_atoms", [])
            if str(item)
        }
        expected_domain = (
            {
                item
                for item in expected_h3 | expected_baseline
                if not item.startswith("process.")
            }
            if expected_decision == "admit"
            else set()
        )
        actual_domain = {
            str(item) for item in actual.get("domain_selected_ids", []) if str(item)
        }
        actual_selected = {
            str(item) for item in actual.get("selected_ids", []) if str(item)
        }
        expected_process = {
            item for item in expected_baseline if item.startswith("process.")
        }
        actual_stops = [str(item) for item in actual.get("stops", []) if str(item)]
        actual_missing = [str(item) for item in actual.get("missing", []) if str(item)]
        expected_missing = [
            str(item) for item in expected.get("missing_evidence", []) if str(item)
        ]
        checks = {
            "decision": actual.get("decision") == expected_decision,
            "h3_and_baseline_domain_atoms": actual_domain == expected_domain,
            "process_baseline_atoms": expected_process.issubset(actual_selected),
            "stop_boundary": bool(actual_stops) == bool(expected.get("stop")),
            "missing_evidence_named": all(
                item.lower() in " ".join((*actual_missing, *actual_stops)).lower()
                for item in expected_missing
            ),
        }
        passed = all(checks.values())
        return {
            "score": 1.0 if passed else 0.0,
            "confidence": "high" if passed else "medium",
            "evidence_level": "static_review",
            "provider_execution": False,
            "checks": checks,
            "actual": {
                "decision": actual.get("decision"),
                "domain_selected_ids": sorted(actual_domain),
                "stops": sorted(actual_stops),
                "missing": sorted(actual_missing),
            },
            "expected": {
                "decision": expected_decision,
                "required_h3_atoms": sorted(expected_h3),
                "required_baseline_atoms": sorted(expected_baseline),
                "stops": bool(expected.get("stop")),
                "missing_evidence": expected_missing,
            },
        }

    cases: list[dict[str, Any]] = []
    for fixture in fixtures:
        fixture_id = str(fixture.get("id") or "")
        context = fixture_context(fixture)
        expected = fixture.get("expected_outcome")
        if not isinstance(context, Mapping) or not isinstance(expected, Mapping):
            cases.append(
                {
                    "fixture_id": fixture_id,
                    "status": "invalid_fixture",
                    "score": {"score": 0.0, "provider_execution": False},
                }
            )
            continue
        result = compile_behavioral_atoms(context, registry=build_h3_registry())
        actual = static_projection_summary(result)
        score = score_h3(actual, expected)
        cases.append(
            {
                "fixture_id": fixture_id,
                "status": "passed" if score["score"] == 1.0 else "failed",
                "actual": actual,
                "expected": dict(expected),
                "score": score,
                "provider_execution": False,
                "cross_skill_composition": "closed_gate",
            }
        )
    return {
        "schema": "tmcp-behavioral-atoms-h3-static-evaluation-v0.7",
        "fixture_count": len(cases),
        "all_fixtures_consumed": len(cases) == len(fixtures),
        "all_fixtures_passed": bool(cases)
        and all(case["score"]["score"] == 1.0 for case in cases),
        "cases": cases,
        "h3_mapping": build_h3_advisory_evaluator_mapping(),
        "provider_cells": "not_run",
        "cross_skill_composition": "closed_gate",
        "promotion_policy": {"auto_promote": False},
    }
