from __future__ import annotations

from copy import deepcopy

import pytest

from rsi.agenda_policy import rank


def _option(option_id: str, *, eligible: bool = True, priority: int = 0,
            kind: str = "seed", triggered: bool = False,
            last_selected: int | None = None, reason: str = "") -> dict:
    return {
        "id": option_id,
        "eligible": eligible,
        "priority": priority,
        "kind": kind,
        "triggered": triggered,
        "last_selected": last_selected,
        "reason": reason,
    }


def test_seed_orders_eligible_options_by_priority_fairness_and_id():
    options = [
        _option("z", priority=4, last_selected=1),
        _option("b", priority=7, last_selected=8),
        _option("a", priority=7, last_selected=8),
        _option("new", priority=4),
        _option("deferred", eligible=False, priority=99, reason="missing source"),
    ]

    ranked = rank(options, "seed/1")

    assert [option["id"] for option in ranked] == ["a", "b", "new", "z", "deferred"]
    assert ranked[-1]["rank_reason"] == "deferred: missing source"
    assert all(option["rank_reason"].startswith("policy: seed/1") for option in ranked[:-1])


def test_adaptive_raises_only_eligible_triggered_probe_and_instrument_options():
    options = [
        _option("seed", priority=20),
        _option("probe", priority=1, kind="scope-probe", triggered=True),
        _option("instrument", priority=2, kind="instrument", triggered=True),
        _option("untriggered", priority=30, kind="scope-probe"),
        _option("deferred-probe", eligible=False, priority=100, kind="scope-probe",
                triggered=True, reason="source unavailable"),
    ]

    ranked = rank(options, "adaptive/1")

    assert [option["id"] for option in ranked] == [
        "instrument", "probe", "untriggered", "seed", "deferred-probe",
    ]
    assert ranked[0]["rank_reason"] == "policy: adaptive/1 triggered instrument"
    assert ranked[1]["rank_reason"] == "policy: adaptive/1 triggered scope-probe"
    assert ranked[-1]["rank_reason"] == "deferred: source unavailable"


def test_seed_does_not_apply_adaptive_trigger_preference():
    options = [
        _option("probe", priority=1, kind="scope-probe", triggered=True),
        _option("seed", priority=2),
    ]

    assert [option["id"] for option in rank(options, "seed/1")] == ["seed", "probe"]


def test_repeated_calls_are_deterministic_and_leave_options_unchanged():
    options = [_option("b", priority=3), _option("a", priority=3)]
    before = deepcopy(options)

    first = rank(options, "adaptive/1")
    second = rank(options, "adaptive/1")

    assert [option["id"] for option in first] == ["a", "b"]
    assert first == second
    assert options == before
    assert all("rank_reason" not in option for option in options)


def test_unknown_policy_fails_at_boundary():
    with pytest.raises(ValueError, match="policy"):
        rank([], "adaptive/2")
