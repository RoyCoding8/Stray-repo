"""Frozen structural challenge panel for Development 02 (CTX-10).

Six scenarios with inspectable expected behavior, independent of model
agreement. The episode/compare tests in tests/test_dev02_episode.py execute
each one against real PostgreSQL/subprocesses. Task ids refer to
experiments/fault_tasks.py; claim/opposition ids are created by the tests.
"""

from __future__ import annotations

SCENARIOS = [
    {
        "id": "missing-content",
        "situation": "diagnose packet over trigger refs with no batch run",
        "expected_outcome": "needs_information",
        "expected_gap": "no attempted behaviors recorded",
    },
    {
        "id": "counterexample-preserved",
        "situation": "construct packet where a batch claim carries active opposition",
        "expected_outcome": "ready",
        "expected_qualification": "counterevidence",
    },
    {
        "id": "superseded-conclusion-alternative-route",
        "situation": "batch claim with one defeated route and one live route",
        "expected_outcome": "ready",
        "expected_route": "surviving derivation",
    },
    {
        "id": "oversized-mandatory-content",
        "situation": "construct packet with an input budget below mandatory size",
        "expected_outcome": "needs_information",
        "expected_proposal": "stage a narrower decision sequence",
    },
    {
        "id": "restart-unresolved-operation",
        "situation": "fresh process resumes with an unresolved sandbox operation",
        "expected_outcome": "stale",
    },
    {
        "id": "rejected-candidate-incumbent-use",
        "situation": "development check rejects the built candidate",
        "expected_outcome": "reject with incumbent subsequent use",
    },
]
