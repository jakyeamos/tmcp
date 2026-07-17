from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.schema_contract_support import SchemaAssertionError, assert_matches_schema


class SchemaContractSupportTests(unittest.TestCase):
    def test_if_then_else_selects_the_matching_branch(self) -> None:
        schema = {
            "type": "object",
            "allOf": [
                {
                    "if": {
                        "properties": {"mode": {"const": "strict"}},
                        "required": ["mode"],
                    },
                    "then": {"required": ["token"]},
                    "else": {"required": ["summary"]},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schema.json"
            path.write_text(json.dumps(schema), encoding="utf-8")

            assert_matches_schema(
                {"mode": "strict", "token": "approved"}, path
            )
            assert_matches_schema(
                {"mode": "relaxed", "summary": "approved"}, path
            )
            with self.assertRaisesRegex(SchemaAssertionError, "missing required"):
                assert_matches_schema({"mode": "strict"}, path)
            with self.assertRaisesRegex(SchemaAssertionError, "missing required"):
                assert_matches_schema({"mode": "relaxed"}, path)


if __name__ == "__main__":
    unittest.main()
