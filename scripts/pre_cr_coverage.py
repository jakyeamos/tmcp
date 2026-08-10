#!/usr/bin/env python3
"""Run the stdlib test suite and emit evidence-backed LCOV coverage.

The repository intentionally has no third-party coverage dependency.  Python's
``trace`` module is sufficient for the changed-line gate when its real line
counts are converted to the small LCOV subset consumed by Pre-CR.  Untested
files remain absent from the report, so this adapter cannot manufacture
coverage for new code.
"""

from __future__ import annotations

import sys
import trace
import unittest
from collections.abc import Mapping
from pathlib import Path


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


WORKSPACE_ROOT = _workspace_root()
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


def _project_path(filename: str, workspace_root: Path) -> str | None:
    path = Path(filename).resolve()
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return None


def render_lcov(
    counts: Mapping[tuple[str, int], int], workspace_root: Path
) -> str:
    """Render traced project files as deterministic LCOV line records."""

    files: dict[str, dict[int, int]] = {}
    for (filename, line_number), hit_count in counts.items():
        relative = _project_path(filename, workspace_root)
        if relative is None or not relative.endswith(".py"):
            continue
        files.setdefault(relative, {})[line_number] = hit_count

    records = ["TN:"]
    for filename in sorted(files):
        lines = files[filename]
        records.append(f"SF:{filename}")
        for line_number in sorted(lines):
            records.append(f"DA:{line_number},{lines[line_number]}")
        records.append(f"LF:{len(lines)}")
        records.append(f"LH:{sum(count > 0 for count in lines.values())}")
        records.append("end_of_record")
    return "\n".join(records) + "\n"


def _run_tests() -> unittest.TestResult:
    suite = unittest.defaultTestLoader.discover("tests")
    return unittest.TextTestRunner(verbosity=1).run(suite)


def main() -> int:
    workspace_root = WORKSPACE_ROOT
    coverage_dir = workspace_root / ".pre-cr"
    coverage_dir.mkdir(exist_ok=True)

    tracer = trace.Trace(
        count=True,
        trace=False,
        ignoredirs=(sys.prefix,),
    )
    result = tracer.runfunc(_run_tests)
    coverage = render_lcov(tracer.results().counts, workspace_root)
    (coverage_dir / "coverage.lcov").write_text(coverage, encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
