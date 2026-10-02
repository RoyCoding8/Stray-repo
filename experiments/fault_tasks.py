"""S3 §11 task family: bounded software-fault reduction with checkable outcomes.

Two fault families split by underlying fault source, never by near-duplicate
surface text: ``off_by_one`` (development + independent panel) and
``wrong_operator`` (transfer). Each task carries broken source, hidden test
cases (served at evaluator scope only) and the reference fix the scripted
double replays for competent arms.
"""

from __future__ import annotations

TASKS = [
    {
        "id": "dev-sum",
        "family": "off_by_one",
        "entry_fn": "sum_to",
        "broken": 'def sum_to(n):\n    """Sum 1..n inclusive."""\n    return sum(range(n))\n',
        "fixed": 'def sum_to(n):\n    """Sum 1..n inclusive."""\n    return sum(range(n + 1))\n',
        "cases": [
            {"fn": "sum_to", "args": [1], "expected": 1},
            {"fn": "sum_to", "args": [5], "expected": 15},
            {"fn": "sum_to", "args": [10], "expected": 55},
        ],
    },
    {
        "id": "dev-collect",
        "family": "off_by_one",
        "entry_fn": "collect",
        "broken": 'def collect(n):\n    """Collect 1..n inclusive."""\n    out = []\n    i = 1\n    while i < n:\n        out.append(i)\n        i += 1\n    return out\n',
        "fixed": 'def collect(n):\n    """Collect 1..n inclusive."""\n    out = []\n    i = 1\n    while i <= n:\n        out.append(i)\n        i += 1\n    return out\n',
        "cases": [
            {"fn": "collect", "args": [1], "expected": [1]},
            {"fn": "collect", "args": [4], "expected": [1, 2, 3, 4]},
        ],
    },
    {
        "id": "dev-series",
        "family": "off_by_one",
        "entry_fn": "series",
        "broken": 'def series(n):\n    """Sum of squares 1..n inclusive."""\n    total = 0\n    for k in range(1, n):\n        total += k * k\n    return total\n',
        "fixed": 'def series(n):\n    """Sum of squares 1..n inclusive."""\n    total = 0\n    for k in range(1, n + 1):\n        total += k * k\n    return total\n',
        "cases": [
            {"fn": "series", "args": [1], "expected": 1},
            {"fn": "series", "args": [3], "expected": 14},
        ],
    },
    {
        "id": "panel-triangular",
        "family": "off_by_one",
        "entry_fn": "triangular",
        "broken": 'def triangular(n):\n    """Triangular number T(n) = n*(n+1)/2."""\n    if n <= 0:\n        return 0\n    return sum(range(n))\n',
        "fixed": 'def triangular(n):\n    """Triangular number T(n) = n*(n+1)/2."""\n    if n <= 0:\n        return 0\n    return sum(range(n + 1))\n',
        "cases": [
            {"fn": "triangular", "args": [0], "expected": 0},
            {"fn": "triangular", "args": [4], "expected": 10},
            {"fn": "triangular", "args": [6], "expected": 21},
        ],
    },
    {
        "id": "panel-batcher",
        "family": "off_by_one",
        "entry_fn": "batches",
        "broken": 'def batches(n):\n    """Batch ids 1..n inclusive."""\n    ids = []\n    i = 1\n    while i < n:\n        ids.append(f"batch-{i}")\n        i += 1\n    return ids\n',
        "fixed": 'def batches(n):\n    """Batch ids 1..n inclusive."""\n    ids = []\n    i = 1\n    while i <= n:\n        ids.append(f"batch-{i}")\n        i += 1\n    return ids\n',
        "cases": [
            {"fn": "batches", "args": [2], "expected": ["batch-1", "batch-2"]},
            {"fn": "batches", "args": [3],
             "expected": ["batch-1", "batch-2", "batch-3"]},
        ],
    },
    {
        "id": "panel-staircase",
        "family": "off_by_one",
        "entry_fn": "staircase",
        "broken": 'def staircase(n):\n    """Steps 1..n with heights k*k."""\n    steps = []\n    for k in range(1, n):\n        steps.append(k * k)\n    return steps\n',
        "fixed": 'def staircase(n):\n    """Steps 1..n with heights k*k."""\n    steps = []\n    for k in range(1, n + 1):\n        steps.append(k * k)\n    return steps\n',
        "cases": [
            {"fn": "staircase", "args": [1], "expected": [1]},
            {"fn": "staircase", "args": [4], "expected": [1, 4, 9, 16]},
        ],
    },
    {
        "id": "transfer-discount",
        "family": "wrong_operator",
        "entry_fn": "apply_discount",
        "broken": 'def apply_discount(price, pct):\n    """Price after pct (0..1) discount."""\n    return price * (1 + pct)\n',
        "fixed": 'def apply_discount(price, pct):\n    """Price after pct (0..1) discount."""\n    return price * (1 - pct)\n',
        "cases": [
            {"fn": "apply_discount", "args": [100, 0.2], "expected": 80.0},
            {"fn": "apply_discount", "args": [50, 0.0], "expected": 50.0},
        ],
    },
    {
        "id": "transfer-sign",
        "family": "wrong_operator",
        "entry_fn": "is_positive",
        "broken": 'def is_positive(n):\n    """True exactly for n > 0."""\n    return n <= 0\n',
        "fixed": 'def is_positive(n):\n    """True exactly for n > 0."""\n    return n > 0\n',
        "cases": [
            {"fn": "is_positive", "args": [3], "expected": True},
            {"fn": "is_positive", "args": [0], "expected": False},
            {"fn": "is_positive", "args": [-2], "expected": False},
        ],
    },
]

BY_ID = {task["id"]: task for task in TASKS}

DEV_IDS = ["dev-sum", "dev-collect", "dev-series"]
PANEL_IDS = ["panel-triangular", "panel-batcher", "panel-staircase"]
TRANSFER_IDS = ["transfer-discount", "transfer-sign"]

LESSON_OFF_BY_ONE = (
    "Off-by-one repair lesson. Python `range(n)` stops before n, so a loop "
    "meant to include n must use `range(n + 1)` or `range(1, n + 1)`. "
    "Likewise `while i < n:` excludes n; use `while i <= n:` when n is "
    "included. Check every loop bound against the documented inclusive range."
)
