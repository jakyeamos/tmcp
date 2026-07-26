#!/usr/bin/env python3
"""Deterministic offline fixture for the last30days conformance case.

This is an executable smoke fixture rather than a unit-test module; its emitted
contract is asserted by the blind runner and independent campaign judges.
"""

from __future__ import annotations

import sys


def main() -> int:
    if "--emit=compact" not in sys.argv:
        print("fixture requires --emit=compact", file=sys.stderr)
        return 2
    print("""🌐 last30days v3.8.3 · synced 2026-07-25

<!-- EVIDENCE FOR SYNTHESIS -->
## Ranked Evidence Clusters

### 1. NVIDIA earnings reaction (score 42, 2 items, sources: Reddit, Web)

1. [web] NVIDIA reports record quarterly revenue
  - 2026-07-24 | Web | [source: https://fixture.test/nvidia-earnings]
  - \"Data-center demand remained the central explanation for the beat.\"

2. [reddit] How are people reading the NVDA print?
  - 2026-07-24 | r/stocks | [source: https://fixture.test/reddit-nvda-reaction]
  - \"The reaction is less about one quarter and more about whether demand can stay this broad.\"

### Top Community Comments

- u/fixture_analyst (18 votes): \"The reaction is less about one quarter and more about whether demand can stay this broad.\"
- u/fixture_longterm (11 votes): \"Data-center demand is still the through-line, but expectations are doing a lot of the work.\"
<!-- END EVIDENCE FOR SYNTHESIS -->

<!-- PASS-THROUGH FOOTER -->
---
✅ All agents reported back!
---
<!-- END PASS-THROUGH FOOTER -->""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
