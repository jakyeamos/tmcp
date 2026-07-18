"""Composition and runtime surface checks for release packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.release_package_sessions import RunJson, check_session_surface
from tmcp_runtime.domain.composition_runtime import composition_gate_catalog
from tmcp_runtime.storage import artifact_persistence_available


def _release_smoke_skill_slice(
    slices: list[dict[str, Any]], relative_path: str
) -> dict[str, Any]:
    candidates = [
        item
        for item in slices
        if str(item.get("relative_path") or "").endswith(relative_path)
    ]
    if not candidates:
        raise ValueError(f"composition release smoke is missing {relative_path}")
    return sorted(candidates, key=lambda item: str(item.get("slice_id") or ""))[0]


def _semantic_release_smoke_proposal(
    preflight: dict[str, Any],
) -> dict[str, Any]:
    slices = [
        item
        for item in preflight.get("candidate_source_slices", [])
        if isinstance(item, dict)
    ]
    governing = [
        item for item in slices if item.get("source_role") == "governing_instruction"
    ]
    skills = [item for item in slices if item.get("source_role") == "active_skill"]
    if not governing or len(skills) < 2:
        raise ValueError(
            "composition release smoke requires governing and two active-skill slices"
        )
    implementation = _release_smoke_skill_slice(
        skills, "skills/impeccable/SKILL.md"
    )
    verification = _release_smoke_skill_slice(
        skills, "skills/release-verification/SKILL.md"
    )

    # Keep this public release smoke proposal source-backed.  The composition
    # validator deliberately rejects synthetic operational claims that are not
    # present in its cited source slices, so the scratch sources below state
    # the small handoff contract this probe exercises.
    criterion = "verification evidence"
    roles: list[dict[str, Any]] = []
    for item in governing:
        roles.append(
            {
                "node_id": item["source_node_id"],
                "role": "Preserve governing constraints",
                "inputs": ["objective"],
                "outputs": ["constraints handoff"],
                "phase_affinity": ["start"],
                "entry_gates": [],
                "exit_gates": ["constraints handoff"],
                "context_cost": item["token_estimate"],
                "covers": [],
                "citations": [item["slice_id"]],
            }
        )
    roles.extend(
        [
            {
                "node_id": implementation["source_node_id"],
                "role": "Produce implementation handoff",
                "inputs": ["constraints handoff"],
                "outputs": ["implementation handoff"],
                "phase_affinity": ["implementation"],
                "entry_gates": ["constraints handoff"],
                "exit_gates": ["implementation handoff"],
                "context_cost": implementation["token_estimate"],
                "covers": [],
                "citations": [implementation["slice_id"]],
            },
            {
                "node_id": verification["source_node_id"],
                "role": "Verify verification evidence",
                "inputs": ["implementation handoff"],
                "outputs": [criterion],
                "phase_affinity": ["verification"],
                "entry_gates": ["implementation handoff"],
                "exit_gates": [criterion],
                "context_cost": verification["token_estimate"],
                "covers": [criterion],
                "citations": [verification["slice_id"]],
            },
        ]
    )

    relationships: list[dict[str, Any]] = []
    for root in governing:
        relationships.append(
            {
                "from": root["source_node_id"],
                "to": implementation["source_node_id"],
                "type": "enables",
                "citations": [root["slice_id"], implementation["slice_id"]],
                "rationale": "",
            }
        )
    relationships.append(
        {
            "from": implementation["source_node_id"],
            "to": verification["source_node_id"],
            "type": "produces",
            "citations": [implementation["slice_id"], verification["slice_id"]],
            "rationale": "",
        }
    )

    return {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": preflight["preflight_id"],
        "current_phase": "implementation",
        "task_model": {
            "deliverables": ["package verification"],
            "success_criteria": [criterion],
            "constraints": ["governing constraints"],
            "subgoals": ["composition", "verification"],
            "evidence_needs": [criterion],
        },
        "skill_roles": roles,
        "relationships": relationships,
        "coverage": {"facets": [criterion], "unresolved_gaps": []},
        "trust": "advisory_untrusted",
    }


def _session_transition_evidence(
    plan: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    stages = [
        item for item in plan.get("ordered_stages", []) if isinstance(item, dict)
    ]
    implementation = next(
        (item for item in stages if item.get("phase") == "implementation"), None
    )
    verification = next(
        (item for item in stages if item.get("phase") == "verification"), None
    )
    if implementation is None or verification is None:
        raise ValueError(
            "assisted session smoke requires implementation and verification stages"
        )
    implementation_nodes = set(implementation.get("node_ids") or [])
    verification_nodes = set(verification.get("node_ids") or [])
    contract = next(
        (
            item
            for item in plan.get("handoff_contracts", [])
            if isinstance(item, dict)
            and item.get("producer_node_id") in implementation_nodes
            and item.get("consumer_node_id") in verification_nodes
        ),
        None,
    )
    if contract is None:
        raise ValueError("assisted session smoke requires an implementation handoff")
    gate_results = [
        {"gate_id": gate["gate_id"], "status": "passed"}
        for gate in composition_gate_catalog(plan)
        if (
            gate.get("kind") == "exit"
            and gate.get("owner_stage_id") == implementation.get("stage_id")
        )
        or (
            gate.get("kind") == "entry"
            and gate.get("owner_stage_id") == verification.get("stage_id")
        )
    ]
    if not gate_results:
        raise ValueError("assisted session smoke requires transition gates")
    return {
        "gate_results": gate_results,
        "handoff_results": [
            {
                "handoff_id": contract["handoff_id"],
                "producer_node_id": contract["producer_node_id"],
                "consumer_node_id": contract["consumer_node_id"],
                "status": "available",
                "consumed_inputs": contract["required_inputs"],
                "produced_outputs": contract["produced_outputs"],
                "evidence_refs": ["release-package-session-handoff"],
            }
        ],
    }


def check_composition_surface(
    plugin_root: Path,
    scratch_root: Path,
    run_json: RunJson,
) -> tuple[bool, str]:
    """Verify composition, session, runtime, receipt, and additive surfaces."""

    source_root = scratch_root / "composition-release-surface"
    tmcp_home = scratch_root / "tmcp-home"
    skill_root = source_root / "skills" / "impeccable"
    verification_skill_root = source_root / "skills" / "release-verification"
    skill_root.mkdir(parents=True, exist_ok=True)
    verification_skill_root.mkdir(parents=True, exist_ok=True)
    (source_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Agent Rules",
                "Use pnpm only.",
                "Read before modifying and search existing behavior first.",
                "Release readiness requires CI evidence, package checks, changelog review, and hosted verification.",
                "Governing constraints produce a constraints handoff.",
            ]
        ),
        encoding="utf-8",
    )
    (skill_root / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: impeccable",
                "---",
                "# Impeccable",
                "For craft commands, run scripts/context.mjs and choose the brand or product register.",
                "Verify browser screenshots, contrast, reduced motion, and responsive behavior for UI work.",
                "Use the constraints handoff to produce an implementation handoff.",
                "Exit when the implementation handoff is ready for verification.",
            ]
        ),
        encoding="utf-8",
    )
    (verification_skill_root / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: release-verification",
                "---",
                "# Release Verification",
                "Use the implementation handoff to verify verification evidence.",
                "Exit when verification evidence is recorded.",
            ]
        ),
        encoding="utf-8",
    )
    env = {"TMCP_HOME": str(tmcp_home)}

    ok, output, compose = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "compose-packet",
            "Improve release readiness before release",
            "--project-path",
            str(source_root),
            "--source-path",
            str(source_root),
            "--phase",
            "start",
            "--cache-policy",
            "none",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or compose is None:
        return False, output
    if compose.get("schema") != "tmcp-composed-packet-v0.1":
        return False, f"unexpected compose schema: {compose.get('schema')}"
    if not isinstance(compose.get("receipt_template"), dict):
        return False, "compose output missing receipt_template"
    if not isinstance(compose.get("compiled_from"), dict):
        return False, "compose output missing compiled_from"
    if not isinstance(compose.get("shortcut_candidate"), dict):
        return False, "compose output missing shortcut_candidate"
    packet_markdown = compose.get("packet_markdown")
    if (
        not isinstance(packet_markdown, str)
        or "## Selection Rationale" not in packet_markdown
    ):
        return False, "compose output missing packet_markdown rationale"
    packet_id = compose.get("packet_id")
    if compose["receipt_template"].get("packet_id") != packet_id:
        return False, "compose receipt_template did not retain packet_id"
    if not isinstance(compose.get("safety"), dict) or not compose["safety"]:
        return False, "compose output missing safety metadata"
    if not isinstance(packet_id, str) or packet_id not in packet_markdown:
        return False, "compose packet_markdown did not retain packet_id"
    verification_text = " ".join(compose.get("verification_gates", [])).lower()
    if "browser" in verification_text:
        return False, "release composition smoke unexpectedly activated browser gate"

    ok, output, preflight = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "prepare-composition",
            "Compose and verify the installed package workflow",
            "--project-path",
            str(source_root),
            "--source-path",
            str(source_root),
            "--phase",
            "implementation",
            "--include-all-active-source-slices",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or preflight is None:
        return False, output
    if preflight.get("schema") != "tmcp-composition-preflight-v0.1":
        return (
            False,
            f"unexpected composition preflight schema: {preflight.get('schema')}",
        )
    try:
        semantic_proposal = _semantic_release_smoke_proposal(preflight)
    except (KeyError, TypeError, ValueError) as exc:
        return False, str(exc)

    ok, output, assisted_compose = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "compose-packet",
            "Compose and verify the installed package workflow",
            "--project-path",
            str(source_root),
            "--source-path",
            str(source_root),
            "--phase",
            "implementation",
            "--cache-policy",
            "none",
            "--semantic-proposal",
            json.dumps(semantic_proposal, separators=(",", ":")),
            "--include-all-active-source-slices",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or assisted_compose is None:
        return False, output
    plan = assisted_compose.get("composition_plan")
    validation = assisted_compose.get("semantic_proposal_validation")
    if not isinstance(plan, dict) or plan.get("schema") != "tmcp-composition-plan-v0.1":
        return False, "assisted compose output missing composition plan"
    if not isinstance(validation, dict) or validation.get("accepted") is not True:
        return False, "assisted compose semantic proposal was not accepted"

    ok, output, recompiled = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "recompile-packet",
            "Compose and verify the installed package workflow",
            "--project-path",
            str(source_root),
            "--source-path",
            str(source_root),
            "--current-phase",
            "implementation",
            "--previous-packet",
            json.dumps(assisted_compose, separators=(",", ":")),
            "--files-read",
            "AGENTS.md",
            "--commands-run",
            "python3 -m unittest",
            "--verification-results",
            '{"gate":"verification evidence","status":"passed"}',
            "--output-mode",
            "full",
            "--cache-policy",
            "none",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or recompiled is None:
        return False, output
    if recompiled.get("schema") != "tmcp-recompiled-packet-v0.1":
        return False, f"unexpected recompile schema: {recompiled.get('schema')}"
    recompiled_plan = recompiled.get("packet", {}).get("composition_plan")
    if not isinstance(recompiled_plan, dict):
        return False, "recompiled packet did not preserve the composition plan"
    if recompiled_plan.get("composition_plan_id") != plan.get("composition_plan_id"):
        return False, "recompile changed the deterministic composition plan identity"

    session_id = "release-assisted-session"
    session_compose_command = [
        "node",
        "scripts/tmcp_launcher.mjs",
        "compose-packet",
        "Compose and verify the installed package workflow",
        "--project-path",
        str(source_root),
        "--source-path",
        str(source_root),
        "--phase",
        "implementation",
        "--cache-policy",
        "none",
        "--semantic-proposal",
        json.dumps(semantic_proposal, separators=(",", ":")),
        "--include-all-active-source-slices",
        "--session-id",
        session_id,
        "--compact",
    ]
    ok, output, session_assisted_compose = run_json(
        session_compose_command,
        plugin_root,
        env,
    )
    if artifact_persistence_available():
        if not ok or session_assisted_compose is None:
            return False, output
        session_plan = session_assisted_compose.get("composition_plan")
        session_validation = session_assisted_compose.get("semantic_proposal_validation")
        if not isinstance(session_plan, dict):
            return False, "assisted session compose output missing composition plan"
        if (
            not isinstance(session_validation, dict)
            or session_validation.get("accepted") is not True
        ):
            return False, "assisted session compose semantic proposal was not accepted"
        if session_plan.get("composition_plan_id") != plan.get("composition_plan_id"):
            return False, "assisted session compose changed the deterministic plan identity"
        created_session = session_assisted_compose.get("session")
        if not isinstance(created_session, dict) or created_session.get("revision") != 1:
            return False, "assisted session compose did not create revision 1"
        try:
            transition_evidence = _session_transition_evidence(session_plan)
        except (KeyError, TypeError, ValueError) as exc:
            return False, str(exc)

        ok, output, session_transition = run_json(
            [
                "node",
                "scripts/tmcp_launcher.mjs",
                "recompile-packet",
                "Compose and verify the installed package workflow",
                "--project-path",
                str(source_root),
                "--source-path",
                str(source_root),
                "--current-phase",
                "implementation",
                "--requested-phase",
                "verification",
                "--files-read",
                "AGENTS.md",
                "--commands-run",
                "python3 -m unittest",
                "--gate-results",
                json.dumps(
                    transition_evidence["gate_results"], separators=(",", ":")
                ),
                "--handoff-results",
                json.dumps(
                    transition_evidence["handoff_results"], separators=(",", ":")
                ),
                "--output-mode",
                "full",
                "--cache-policy",
                "none",
                "--session-id",
                session_id,
                "--compact",
            ],
            plugin_root,
            env,
        )
        if not ok or session_transition is None:
            return False, output
        transition_plan = session_transition.get("packet", {}).get(
            "composition_plan"
        )
        if not isinstance(transition_plan, dict):
            return (
                False,
                "assisted session recompile did not preserve the composition plan",
            )
        if transition_plan.get("composition_plan_id") != session_plan.get(
            "composition_plan_id"
        ):
            return (
                False,
                "assisted session recompile changed the composition plan identity",
            )
        if transition_plan.get("current_phase") != "verification":
            return False, "assisted session recompile did not advance to verification"
        transition_session = session_transition.get("session")
        if (
            not isinstance(transition_session, dict)
            or transition_session.get("revision") != 2
        ):
            return False, "assisted session recompile did not create revision 2"
        if "runtime_continuation" not in transition_plan:
            return False, "assisted session recompile did not persist a continuation"

        ok, output, session_resume = run_json(
            [
                "node",
                "scripts/tmcp_launcher.mjs",
                "recompile-packet",
                "Compose and verify the installed package workflow",
                "--project-path",
                str(source_root),
                "--source-path",
                str(source_root),
                "--current-phase",
                "verification",
                "--output-mode",
                "full",
                "--cache-policy",
                "none",
                "--session-id",
                session_id,
                "--compact",
            ],
            plugin_root,
            env,
        )
        if not ok or session_resume is None:
            return False, output
        resumed_plan = session_resume.get("packet", {}).get("composition_plan")
        if not isinstance(resumed_plan, dict):
            return False, "assisted session resume did not preserve the composition plan"
        if resumed_plan.get("composition_plan_id") != session_plan.get(
            "composition_plan_id"
        ):
            return False, "assisted session resume changed the composition plan identity"
        if resumed_plan.get("current_phase") != "verification":
            return False, "assisted session resume did not retain verification"
        resumed_session = session_resume.get("session")
        if (
            not isinstance(resumed_session, dict)
            or resumed_session.get("revision") != 3
        ):
            return False, "assisted session resume did not create revision 3"
        replay = (
            session_resume.get("packet", {})
            .get("composition_diagnostics", {})
            .get("runtime_capsule_validation", {})
            .get("runtime_state_replay", {})
        )
        if (
            not isinstance(replay, dict)
            or replay.get("resumed") is not True
            or replay.get("reason") != "capsule_bound_continuation"
        ):
            return False, "assisted session resume did not use the trusted continuation"
        assisted_session_mode = "assisted session continuation smoke passed"
    else:
        if ok or session_assisted_compose is not None:
            return False, "assisted session compose unexpectedly wrote an artifact"
        if "Secure artifact persistence" not in output:
            return False, f"assisted session compose did not fail closed: {output}"
        assisted_session_mode = "portable assisted-session denial smoke passed"

    sessions_ok, session_mode = check_session_surface(
        plugin_root,
        source_root,
        tmcp_home,
        run_json,
    )
    if not sessions_ok:
        return False, session_mode

    ok, output, runtime = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "runtime-next",
            "Fix the dashboard UI bug",
            "--project-path",
            str(source_root),
            "--current-phase",
            "final",
            "--files-changed",
            "app/page.tsx",
            "--failures",
            "vitest failed",
            "--browser-evidence",
            "screenshot shows overlap",
            "--cache-policy",
            "none",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or runtime is None:
        return False, output
    if runtime.get("schema") != "tmcp-runtime-next-v0.1":
        return False, f"unexpected runtime-next schema: {runtime.get('schema')}"
    packet_delta = runtime.get("packet_delta")
    if not isinstance(packet_delta, dict):
        return False, "runtime-next output missing packet_delta"
    activated = set(packet_delta.get("activated_atoms", []))
    if not {
        "ui-browser-verification",
        "debugging-regression",
        "verification-before-completion",
    }.issubset(activated):
        return False, "runtime-next smoke missing contextual activated atoms"

    ok, output, receipt = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "record-receipt",
            str(compose.get("packet_id")),
            "--activated-atoms",
            "behavior-verification",
            "--commands-run",
            "python3 -m unittest",
            "--verification-results",
            "passed",
            "--outcome",
            "passed",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if artifact_persistence_available():
        if not ok or receipt is None:
            return False, output
        if receipt.get("schema") != "tmcp-run-receipt-v0.1":
            return False, f"unexpected receipt schema: {receipt.get('schema')}"
        receipt_json = receipt.get("artifact_paths", {}).get("receipt_json")
        if not isinstance(receipt_json, str) or not Path(receipt_json).exists():
            return False, "record-receipt did not write receipt_json"
    else:
        if ok or receipt is not None:
            return (
                False,
                "record-receipt unexpectedly wrote an artifact on this platform",
            )
        if "Secure artifact persistence" not in output:
            return False, f"record-receipt did not fail closed: {output}"
        if tmcp_home.exists() and any(tmcp_home.rglob("*")):
            return (
                False,
                "record-receipt created artifacts despite unavailable persistence",
            )

    ok, output, explain = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "explain",
            "Review release readiness",
            "--project-path",
            str(source_root),
            "--compose",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or explain is None:
        return False, output
    if explain.get("composed_packet", {}).get("schema") != "tmcp-composed-packet-v0.1":
        return False, "explain --compose output missing composed packet"

    ok, output, recommend = run_json(
        [
            "node",
            "scripts/tmcp_launcher.mjs",
            "recommend",
            str(source_root),
            "--candidate-workflows",
            "release_readiness",
            "--min-confidence",
            "0.1",
            "--no-write-artifacts",
            "--compose",
            "--compact",
        ],
        plugin_root,
        env,
    )
    if not ok or recommend is None:
        return False, output
    if (
        recommend.get("composed_packet", {}).get("schema")
        != "tmcp-composed-packet-v0.1"
    ):
        return False, "recommend --compose output missing composed packet"
    persistence_mode = (
        "persistent receipt smoke passed"
        if artifact_persistence_available()
        else "portable receipt denial smoke passed"
    )
    return True, "\n".join(
        [
            output,
            persistence_mode,
            session_mode,
            "assisted composition and recompile smoke passed",
            assisted_session_mode,
            "composition surface smoke passed",
        ]
    )
