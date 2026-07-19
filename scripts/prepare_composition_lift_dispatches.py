#!/usr/bin/env python3
"""Prepare an opaque runner or judge dispatch bundle from a lift campaign."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.schema_contract_support import (  # noqa: E402
    SchemaAssertionError,
    assert_matches_schema,
)
from tmcp_runtime.domain.composition_lift_campaign_results import (  # noqa: E402
    build_campaign_dispatch_bundle,
)
from tmcp_runtime.storage.artifacts import (  # noqa: E402
    ArtifactStorageError,
    AtomicArtifactStore,
)


MAX_INPUT_BYTES = 16 * 1024 * 1024
SCHEMAS = PLUGIN_ROOT / "schemas"


def _read_object(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"campaign exceeds {MAX_INPUT_BYTES} bytes.")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("campaign must contain a JSON object.")
    return payload


def prepare_dispatches(
    *, campaign_path: Path, audience: str, output_dir: Path
) -> dict[str, Any]:
    """Write one opaque dispatch bundle without exposing controller cells."""

    campaign = _read_object(campaign_path)
    assert_matches_schema(
        campaign,
        SCHEMAS / "tmcp-composition-lift-campaign-v0.1.schema.json",
    )
    bundle = build_campaign_dispatch_bundle(campaign, audience=audience)
    assert_matches_schema(
        bundle,
        SCHEMAS / "tmcp-composition-lift-dispatch-bundle-v0.1.schema.json",
    )
    filename = f"composition-lift-{audience}-dispatches.json"
    paths = AtomicArtifactStore.write_json_bundle(output_dir, {filename: bundle})
    return {
        "schema": "tmcp-composition-lift-dispatch-preparation-v0.1",
        "ok": True,
        "audience": audience,
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": campaign["campaign_digest"],
        "dispatch_count": len(bundle["dispatches"]),
        "dispatch_bundle_path": paths[filename],
        "automatic_tool_execution": False,
        "receipt_persistence": "not_performed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare opaque runner/judge dispatches from a validated campaign. "
            "This command never executes hosts, calls models, or writes receipts."
        )
    )
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--audience", required=True, choices=("runner", "judge"))
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = prepare_dispatches(
            campaign_path=args.campaign,
            audience=args.audience,
            output_dir=args.output_dir,
        )
    except (
        ArtifactStorageError,
        OSError,
        SchemaAssertionError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
