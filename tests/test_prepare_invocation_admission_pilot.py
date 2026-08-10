from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "prepare_invocation_admission_pilot.py"
SPEC = importlib.util.spec_from_file_location(
    "prepare_invocation_admission_pilot", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareInvocationAdmissionPilotTests(unittest.TestCase):
    def test_fixture_catalog_preserves_source_bound_case_bar(self) -> None:
        manifest = {
            "preregistration": {
                "source_fixtures": [
                    "tests/fixtures/invocation-admission-pilot-v0.3.json"
                ]
            }
        }

        catalog = MODULE._fixture_catalog(manifest)

        case = catalog["v03-agent-workflow"]
        self.assertEqual(
            case["source"], "tests/fixtures/invocation-admission-pilot-v0.3.json"
        )
        self.assertIn("workflow", {item["id"] for item in case["bar"]["dimensions"]})
        self.assertEqual(
            case["workspace_template"],
            "tests/fixtures/invocation-admission-v0.3/agent-workflow",
        )


if __name__ == "__main__":
    unittest.main()
