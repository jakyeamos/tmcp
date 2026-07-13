from __future__ import annotations

import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOT = PLUGIN_ROOT / "tmcp_runtime" / "domain"
MAX_DOMAIN_MODULE_NONBLANK_LINES = 600


class DomainSizeBudgetTests(unittest.TestCase):
    def test_domain_modules_remain_within_the_size_budget(self) -> None:
        oversized: dict[str, int] = {}
        for path in DOMAIN_ROOT.glob("*.py"):
            if path.name == "__init__.py":
                continue
            line_count = sum(
                bool(line.strip())
                for line in path.read_text(encoding="utf-8").splitlines()
            )
            if line_count > MAX_DOMAIN_MODULE_NONBLANK_LINES:
                oversized[path.name] = line_count

        self.assertEqual(oversized, {})
