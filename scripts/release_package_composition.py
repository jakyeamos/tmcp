"""Composition and runtime surface checks for release packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.release_package_sessions import RunJson, check_session_surface
from tmcp_runtime.storage import artifact_persistence_available


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
    if not governing or not skills:
        raise ValueError(
            "composition release smoke requires governing and active-skill slices"
        )

    criterion = "Installed-package composition verification passes"
    roles: list[dict[str, Any]] = []
    for item in governing:
        roles.append(
            {
                "node_id": item["source_node_id"],
                "role": "Preserve governing project constraints",
                "inputs": ["task objective"],
                "outputs": ["bounded project constraints"],
                "phase_affinity": ["start"],
                "entry_gates": [],
                "exit_gates": ["Governing constraints are available"],
                "context_cost": item["token_estimate"],
                "covers": [],
                "citations": [item["slice_id"]],
            }
        )
    for item in skills:
        roles.append(
            {
                "node_id": item["source_node_id"],
                "role": "Verify the installed composition workflow",
                "inputs": ["bounded project constraints"],
                "outputs": ["installed-package verification evidence"],
                "phase_affinity": ["implementation"],
                "entry_gates": ["Governing constraints are available"],
                "exit_gates": [criterion],
                "context_cost": item["token_estimate"],
                "covers": [criterion],
                "citations": [item["slice_id"]],
            }
        )

    relationships: list[dict[str, Any]] = []
    for root in governing:
        for skill in skills:
            relationships.append(
                {
                    "from": root["source_node_id"],
                    "to": skill["source_node_id"],
                    "type": "enables",
                    "citations": [root["slice_id"], skill["slice_id"]],
                    "rationale": (
                        "The active skill must operate within the governing project "
                        "constraints."
                    ),
                }
            )

    return {
        "schema": "tmcp-semantic-proposal-v0.1",
        "preflight_id": preflight["preflight_id"],
        "current_phase": "implementation",
        "task_model": {
            "deliverables": ["Installed-package composition smoke result"],
            "success_criteria": [criterion],
            "constraints": ["Preserve governing project instructions"],
            "subgoals": ["Compose", "Recompile", "Verify provenance"],
            "evidence_needs": ["Structured package verification result"],
        },
        "skill_roles": roles,
        "relationships": relationships,
        "coverage": {"facets": [criterion], "unresolved_gaps": []},
        "trust": "advisory_untrusted",
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
    skill_root.mkdir(parents=True, exist_ok=True)
    (source_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# Agent Rules",
                "Use pnpm only.",
                "Read before modifying and search existing behavior first.",
                "Release readiness requires CI evidence, package checks, changelog review, and hosted verification.",
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
            '{"gate":"Installed-package composition verification passes","status":"passed"}',
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
            "composition surface smoke passed",
        ]
    )
