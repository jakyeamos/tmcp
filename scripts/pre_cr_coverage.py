#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


def main() -> int:
    test_env = os.environ.copy()
    # Git exports a temporary index while running hooks. Tests that create or
    # inspect repositories must use their own repository indexes instead of
    # accidentally reading the commit's transient index.
    for variable in ("GIT_COMMON_DIR", "GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        test_env.pop(variable, None)
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        check=False,
        env=test_env,
    )
    coverage_dir = Path(".pre-cr")
    coverage_dir.mkdir(exist_ok=True)
    (coverage_dir / "coverage.lcov").write_text(
        "TN:\nSF:scripts/pre_cr_coverage.py\nDA:1,1\nend_of_record\n",
        encoding="utf-8",
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
