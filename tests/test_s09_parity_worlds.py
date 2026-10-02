"""The parity harness can only compare arms on the Boolean world.

`_run_arm` called `boolean_active.run_episode` directly, so `compare_arms`
could not be pointed at any other instrument. The ordering-constraints
world has the same episode shape and an action graph was built for it, so
the harness could answer "does this representation work on a second
world" and could not — the question was unaskable rather than answered.

This is N-21, and it bounds what E1 can claim. The matrix showed the three
representations agree on the Boolean world; it says nothing about whether
that agreement survives a world whose action vocabulary differs, which is
exactly the axis the handoff's first question is about.

These tests pin that a second world is reachable and that asking for one
the harness cannot drive is a refusal rather than a silent Boolean run. A
harness that quietly ran the Boolean world when asked for another would
report a passing comparison for a world that was never exercised.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import s09_arm_parity as parity


def test_the_harness_names_the_world_it_runs():
    """No implicit default. The world is an argument, not a constant."""
    assert hasattr(parity.ComparisonConditions, "__dataclass_fields__")
    assert "world" in parity.ComparisonConditions.__dataclass_fields__, (
        "a comparison must be able to name the world it runs on")


def test_the_boolean_world_is_still_reachable_by_name():
    conditions = parity.ComparisonConditions(
        split="dev", seed=4, max_queries=8, world="boolean")
    runner = parity.episode_runner("boolean")

    assert callable(runner)
    assert runner is parity.episode_runner("boolean")


def test_an_unknown_world_is_refused_rather_than_silently_boolean():
    """The failure this guards against is a false pass.

    If an unrecognised world fell back to the Boolean world, a study that
    asked for a second instrument would get a clean comparison against the
    first one and read it as evidence about the second.
    """
    with pytest.raises(ValueError, match="unknown world"):
        parity.episode_runner("no-such-world")


def test_the_ordering_world_is_reachable():
    """The second instrument is runnable, which is the whole point."""
    runner = parity.episode_runner("ordering")

    assert callable(runner)
    assert runner is not parity.episode_runner("boolean")
