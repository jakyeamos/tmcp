from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "pre_cr_coverage.py"
SPEC = importlib.util.spec_from_file_location("pre_cr_coverage", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PreCrCoverageTests(unittest.TestCase):
    def test_render_lcov_keeps_project_paths_and_counts(self) -> None:
        counts = {
            (str(ROOT / "scripts" / "example.py"), 4): 3,
            (str(ROOT / "scripts" / "example.py"), 7): 0,
            ("/usr/local/lib/python3.12/site-packages/third_party.py", 2): 9,
        }

        rendered = MODULE.render_lcov(counts, ROOT)

        self.assertIn("SF:scripts/example.py", rendered)
        self.assertIn("DA:4,3", rendered)
        self.assertIn("DA:7,0", rendered)
        self.assertNotIn("third_party.py", rendered)
        self.assertIn("LF:2", rendered)
        self.assertIn("LH:1", rendered)


if __name__ == "__main__":
    unittest.main()
