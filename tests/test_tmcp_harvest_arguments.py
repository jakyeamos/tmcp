from __future__ import annotations

import unittest

from tmcp_runtime.services.harvest import read_only_harvest_arguments


class HarvestArgumentProjectionTests(unittest.TestCase):
    def test_projection_filters_source_paths_and_forces_preview_mode(self) -> None:
        arguments = {
            "objective": "Harvest the project guidance",
            "project_path": "/tmp/project",
            "source_path": "/tmp/fallback",
            "source_paths": [0, "", "docs"],
            "include_globs": ["**/AGENTS.md"],
            "exclude_globs": ["**/.git/**"],
            "limit": 12,
            "max_file_bytes": 4096,
            "max_excerpt_chars": 240,
            "follow_symlinks": 1,
            "redact_sensitive": 0,
            "write_artifacts": True,
        }

        projected = read_only_harvest_arguments(arguments)

        self.assertEqual(projected["source_paths"], ["0", "docs"])
        self.assertEqual(projected["objective"], "Harvest the project guidance")
        self.assertEqual(projected["include_globs"], ["**/AGENTS.md"])
        self.assertEqual(projected["exclude_globs"], ["**/.git/**"])
        self.assertEqual(projected["limit"], 12)
        self.assertEqual(projected["max_file_bytes"], 4096)
        self.assertEqual(projected["max_excerpt_chars"], 240)
        self.assertTrue(projected["follow_symlinks"])
        self.assertFalse(projected["redact_sensitive"])
        self.assertFalse(projected["write_artifacts"])
        self.assertTrue(arguments["write_artifacts"])

    def test_projection_falls_back_from_empty_source_paths(self) -> None:
        for source_paths in (None, [], [""], "not-a-list"):
            with self.subTest(source_paths=source_paths):
                projected = read_only_harvest_arguments(
                    {
                        "source_paths": source_paths,
                        "source_path": "/tmp/source",
                        "project_path": "/tmp/project",
                    }
                )

                self.assertEqual(projected["source_paths"], ["/tmp/source"])

    def test_projection_uses_project_path_when_source_path_is_absent(self) -> None:
        projected = read_only_harvest_arguments({"project_path": "/tmp/project"})

        self.assertEqual(projected["source_paths"], ["/tmp/project"])
        self.assertEqual(projected["objective"], "")
        self.assertEqual(projected["limit"], 40)
        self.assertEqual(projected["max_file_bytes"], 262144)
        self.assertEqual(projected["max_excerpt_chars"], 1200)
        self.assertFalse(projected["follow_symlinks"])
        self.assertTrue(projected["redact_sensitive"])
        self.assertFalse(projected["write_artifacts"])

    def test_projection_preserves_explicit_numeric_values(self) -> None:
        projected = read_only_harvest_arguments(
            {
                "limit": None,
                "max_file_bytes": 0,
                "max_excerpt_chars": 0,
            }
        )

        self.assertIsNone(projected["limit"])
        self.assertEqual(projected["max_file_bytes"], 0)
        self.assertEqual(projected["max_excerpt_chars"], 0)


if __name__ == "__main__":
    unittest.main()
