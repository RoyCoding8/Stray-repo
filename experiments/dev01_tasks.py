"""Dev01 comparison-lane fixture family: missing precondition guards.

Third source group for the DEV-07 frozen splits, alongside
``experiments/fault_tasks.py`` (``off_by_one`` development/independent panel
plus ``wrong_operator`` transfer) and ``experiments/doubles.py`` (scripted
model responses). Every response and outcome derived from these tasks is
deterministic fixture evidence, never a live result.

Fault source: the broken program assumes a non-degenerate input and has no
guard for the empty/degenerate case (``IndexError``/``ZeroDivisionError``).
This is structurally disjoint from loop-bound inclusion (``off_by_one``)
and from sign/operator choice (``wrong_operator``): a bound-inclusion
repair cannot fix a missing guard, and vice versa.

Grouping rule (recorded for DEV-07): a task belongs to exactly one source
group named by its fixture file and fault family; development, panel and
use groups are disjoint by task ID, and the ``dev01-guard`` use group is
additionally disjoint by underlying fault structure. The ``off_by_one``
panel shares structure with ``off_by_one`` development by design (recorded
shared structure, independent task IDs); ``dev01-guard`` shares neither.
"""

from __future__ import annotations

FAMILY = "missing_guard"
SOURCE_GROUP = "dev01-guard"

GROUPING_RULE = (
    "source-group split: development uses fault_tasks off_by_one dev IDs, "
    "the protected-eval panel uses fault_tasks off_by_one panel IDs "
    "(disjoint IDs, known shared loop-bound structure), and subsequent use "
    "uses this file's missing_guard IDs (disjoint IDs and disjoint fault "
    "structure: missing precondition guard vs loop-bound inclusion vs "
    "operator choice)"
)

TASKS = [
    {
        "id": "dev01-guard-first",
        "family": FAMILY,
        "source_group": SOURCE_GROUP,
        "entry_fn": "first",
        "broken": 'def first(xs):\n    """First element of xs."""\n    return xs[0]\n',
        "fixed": 'def first(xs):\n    """First element of xs, None when empty."""\n'
                 '    return xs[0] if xs else None\n',
        "cases": [
            {"fn": "first", "args": [[3, 1]], "expected": 3},
            {"fn": "first", "args": [[]], "expected": None},
        ],
    },
    {
        "id": "dev01-guard-average",
        "family": FAMILY,
        "source_group": SOURCE_GROUP,
        "entry_fn": "average",
        "broken": 'def average(xs):\n    """Mean of xs."""\n    return sum(xs) / len(xs)\n',
        "fixed": 'def average(xs):\n    """Mean of xs, 0.0 when empty."""\n'
                 '    return sum(xs) / len(xs) if xs else 0.0\n',
        "cases": [
            {"fn": "average", "args": [[2.0, 4.0]], "expected": 3.0},
            {"fn": "average", "args": [[]], "expected": 0.0},
        ],
    },
    {
        "id": "dev01-guard-last",
        "family": FAMILY,
        "source_group": SOURCE_GROUP,
        "entry_fn": "last",
        "broken": 'def last(xs):\n    """Last element of xs."""\n    return xs[-1]\n',
        "fixed": 'def last(xs):\n    """Last element of xs, None when empty."""\n'
                 '    return xs[-1] if xs else None\n',
        "cases": [
            {"fn": "last", "args": [[1, 9]], "expected": 9},
            {"fn": "last", "args": [[]], "expected": None},
        ],
    },
]

BY_ID = {task["id"]: task for task in TASKS}

USE_IDS = ["dev01-guard-first", "dev01-guard-average", "dev01-guard-last"]
