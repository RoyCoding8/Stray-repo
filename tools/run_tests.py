"""Run one test file against this worktree's own src, without a shell env var.

CI installs the package (`pip install -e ".[test]"`), so `settlement` imports
from `src` there. On a host with no install, `settlement` is unimportable and
`tests/conftest.py` fails before collection, which is a property of the host
rather than of the test.

This puts `ROOT` and `ROOT/src` on `sys.path` before pytest imports conftest,
which is what an editable install does. It changes nothing about which code is
under test: both entries are inside this worktree.

    python tools/run_tests.py tests/test_evidence_integrity.py -k eligibility
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    for entry in (ROOT, ROOT / "src"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    import pytest

    return int(pytest.main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
