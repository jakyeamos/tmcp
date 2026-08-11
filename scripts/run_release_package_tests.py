#!/usr/bin/env python3
"""Run the tests that are actually shipped in a TMCP release package."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


def is_repository_evidence_test(path: Path) -> bool:
    """Identify the tests whose imports require the repository-only evidence."""

    if path.name == "test_tmcp_coordination.py":
        return True
    parts = path.stem.split("_")
    if parts[:4] != ["test", "tmcp", "behavioral", "atoms"]:
        return False
    return parts[4:] in [
        ["preflight"],
        ["runtime", "decision", "v0", "4"],
        ["runtime", "h2", "v0", "6"],
        ["runtime", "h3", "v0", "7"],
    ]


def package_test_suite(plugin_root: Path) -> tuple[unittest.TestSuite, list[str]]:
    """Load shipped tests while excluding tests whose evidence is repo-only."""

    test_root = plugin_root / "tests"
    has_repository_evidence = (plugin_root / "docs" / "experiments").is_dir()
    excluded: list[str] = []
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for path in sorted(test_root.glob("test*.py")):
        if not has_repository_evidence and is_repository_evidence_test(path):
            excluded.append(path.relative_to(plugin_root).as_posix())
            continue
        suite.addTests(loader.loadTestsFromName(path.stem))
    return suite, excluded


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[1]
    test_root = plugin_root / "tests"
    if str(test_root) not in sys.path:
        sys.path.insert(0, str(test_root))
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))
    suite, excluded = package_test_suite(plugin_root)
    if excluded:
        print(
            "Skipping repository-only evidence tests: "
            + ", ".join(excluded)
        )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
