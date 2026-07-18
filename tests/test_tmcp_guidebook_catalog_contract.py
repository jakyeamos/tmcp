from __future__ import annotations

import json
import unittest
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[1] / "docs" / "SKILL_PATTERN_CATALOG.json"


class GuidebookCatalogContractTests(unittest.TestCase):
    def test_duplicate_pattern_projections_cannot_strengthen_promotion_state(self) -> None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        entries = {
            entry["pattern_id"]: entry
            for entry in catalog["guidebook_entries"]
            if isinstance(entry, dict) and isinstance(entry.get("pattern_id"), str)
        }
        for projection in catalog["patterns"]:
            if not isinstance(projection, dict):
                continue
            source = entries.get(projection.get("pattern_id"))
            if source is None:
                continue
            source_promotion = source.get("promotion") or {}
            projection_promotion = projection.get("promotion") or {}
            self.assertEqual(
                projection_promotion.get("decision"), source_promotion.get("decision")
            )
            self.assertEqual(
                projection_promotion.get("eligible"), source_promotion.get("eligible")
            )
            self.assertTrue(
                set(source_promotion.get("gaps") or []).issubset(
                    set(projection_promotion.get("gaps") or [])
                ),
                f"projection weakened promotion gaps for {projection.get('pattern_id')}",
            )


if __name__ == "__main__":
    unittest.main()
