"""The r123 record's two false claims, pinned against regression.

Every other acquisition assertion in tests/test_r123_gates.py and
tests/test_invl02_causality.py runs on doubles. Nothing in the committed tree
read reports/evidence/invl02-r123/, so the archive's own account of itself went
uncheck. These tests read it and assert what the frozen bytes actually show.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "reports" / "evidence" / "invl02-r123"


def _load(name):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def e0():
    return _load("e0-run.json")


@pytest.fixture(scope="module")
def live_store():
    return _load("frontier-live.json")


def test_the_bound_program_cannot_act(live_store):
    """acquired-live-live-r1 is 66 bytes that return no action at all."""
    arm = next(a for a in live_store["treatment_arms"]["acquired"]
               if a["control_id"] == "acquired-live-live-r1")
    source = arm["imp_source"]

    assert len(source) == 66
    assert source == 'def STEP(view, state):\n    return {"action": None, "state": state}'

    namespace: dict = {}
    exec(compile(source, "<acquired-live-live-r1>", "exec"), namespace)
    result = namespace["STEP"](
        {"experience": [], "frontier": [{"opportunity_id": "opp-first"}]},
        {"step": 0})

    assert result["action"] is None
    assert "kind" not in (result["action"] or {})


def test_the_bound_package_never_became_active(e0, live_store):
    """The digest recorded as bound is absent from active package and lineage."""
    bound_digest = e0["revision"]["bound_digest"]

    assert e0["revision"]["disposition"] == "bound"
    assert e0["live"]["frontier"]["acquisition"]["status"] == "retained"

    assert live_store["active_package"]["package_digest"] != bound_digest
    assert bound_digest not in {entry["package_digest"]
                                for entry in live_store["lineage"]}


def test_the_acquired_arm_holds_authored_bytes():
    """acquired-high-r1 is the authored menu member under an acquired label."""
    from experiments.ad01 import improve_channel as channel

    store = _load("frontier-live.json")
    arm = next(a for a in store["treatment_arms"]["acquired"]
               if a["control_id"] == "acquired-high-r1")

    assert arm["imp_source"] == channel.IMPROVE_HIGH_SOURCE
    assert arm["imp_digest"] == hashlib.sha256(
        arm["imp_source"].encode("utf-8")).hexdigest()
    assert arm["origin"] == "acquired"
    assert "source_kind" not in arm


def test_the_archive_is_not_reproducible_from_committed_source(live_store):
    """Every store in the archive predates the committed frontier version."""
    from experiments.ad01 import frontier as frontier_module

    assert live_store["frontier_version"] == "invl02-frontier-v1"
    assert frontier_module.FRONTIER_VERSION == "invl02-frontier-v2"

    with pytest.raises(frontier_module.Refused, match="frontier version"):
        frontier_module.FrontierStore(EVIDENCE / "frontier-live.json")


def test_the_bound_outcome_carries_no_reason(e0):
    """The empty reason is in the archive, and nothing emits it today."""
    import inspect

    from experiments.ad01 import live_construct

    assert e0["revision"]["reason"] == ""

    literal = inspect.getsource(live_construct.bind_live_revision).split(
        "return {", 1)[1].split("}", 1)[0]
    for key in ("reason", "bound_digest", "construction_calls"):
        assert f'"{key}"' not in literal


def test_m4_verification_failed_and_narrow_recompute_passed():
    """The document claimed zero problems; the bundle verifier recorded 55."""
    verify = _load("e12/m4-verify.json")
    recompute = _load("e12/recompute.json")

    assert verify["status"] == "fail"
    assert len(verify["problems"]) == 55
    assert recompute["status"] == "pass"
    assert recompute["problems"] == []


def test_a_test_does_not_cover_the_archive():
    """The unguarded claim, stated as a lower bound instead of a census.

    This file previously asserted that it was the *only* test in the tree
    mentioning `invl02-r123`. That was a closed-world census, and it was
    already wrong on the integration tip: `test_c8_gate_review.py` and
    `test_c5_executable_bound.py` read the archive directly, both added at
    `d421c58`, after the base this lane measured on. A census over file
    names goes stale the moment a second lane lands, which is a false red
    with no finding behind it.

    The claim worth keeping is the weaker one it was standing in for: the
    archive had no guard, and this file adds one. A lower bound is what
    that claim can honestly assert, so it is asserted as a lower bound -
    this file is among the readers - and the guard itself is the six tests
    above.
    """
    names = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    readers = {name for name in names
               if "invl02-r123" in (ROOT / "tests" / name).read_text(
                   encoding="utf-8", errors="ignore")}

    assert Path(__file__).name in readers
