import unittest

from routes import normalize_route  # pyright: ignore[reportImplicitRelativeImport]


class NormalizeRouteTests(unittest.TestCase):
    def test_normalizes_underscores(self) -> None:
        self.assertEqual(normalize_route("AGENT_WORKFLOW"), "agent-workflow")

    def test_strips_boundary_whitespace(self) -> None:
        self.assertEqual(normalize_route("  AGENT_WORKFLOW  "), "agent-workflow")


if __name__ == "__main__":
    unittest.main()
