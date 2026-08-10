#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    # A Git hook exports a temporary GIT_INDEX_FILE while it runs. Test
    # fixtures create their own repositories; inheriting that index lets a
    # fixture rewrite the caller's commit index and can corrupt the commit.
    test_environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        check=False,
        env=test_environment,
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
