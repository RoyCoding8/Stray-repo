"""E2 retained policy against a cold reacquisition, costed honestly.

The comparison is only worth running if construction and use are
separated. A retained policy amortises one construction over every use;
a cold arm pays it again. Reporting one total hides which arm is paying
for what, and a total that mixes the two is the number a reader will
quote, so both are reported and each is traceable to the dispatches that
produced it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import worlds
from experiments.ad01.learner import TreatmentRefused
from experiments.ad01.learner import acquisition_cost_arms
from experiments.ad01.learner import cost_of
from experiments.ad01.learner import cost_report
from experiments.ad01.learner import total_cost
from experiments.ad01.s09_cap_sheet import load

# The per-dispatch constant this used to import was a 33-character smoke
# request measured once. A construction call is 4880 characters and 2048
# output tokens, which the broker prices at 3269 units. The cost arms take
# their unit figure from the committed cap sheet instead of a per-call rate.
_PER_REQUEST_UNITS = load().unit_allowance.per_request

TASK = "ad01-w1-dev-sw-01"
BUDGET = {"model_calls": 2, "queries": 8, "steps": 4}
USES = 6


def _task() -> dict:
    return worlds.load_task(worlds.FROZEN_DIR, TASK)


def test_the_two_arms_differ_only_in_whether_the_policy_was_built():
    arms = acquisition_cost_arms(_task(), BUDGET, uses=USES)

    assert arms["retained"]["construction_dispatches"] == 0, (
        "a retained policy was already built, so building it again is a"
        " different condition, not a retained one")
    assert arms["cold"]["construction_dispatches"] == \
        BUDGET["model_calls"]
    for name in ("retained", "cold"):
        assert arms[name]["uses"] == USES
        assert arms[name]["use_dispatches"] == \
            USES * arms[name]["dispatches_per_use"]
        assert arms[name]["task_id"] == TASK
        assert arms[name]["budget"] == BUDGET


def test_construction_and_use_costs_are_reported_separately():
    arms = acquisition_cost_arms(_task(), BUDGET, uses=USES)

    for name in ("retained", "cold"):
        cost = cost_of(arms[name])
        assert cost["construction"]["dispatches"] == \
            arms[name]["construction_dispatches"]
        assert cost["use"]["dispatches"] == arms[name]["use_dispatches"]
        assert cost["construction"]["units"] == \
            arms[name]["construction_dispatches"] \
            * _PER_REQUEST_UNITS
        assert cost["use"]["units"] == arms[name]["use_dispatches"] \
            * _PER_REQUEST_UNITS
        assert cost["construction"]["units"] + cost["use"]["units"] == \
            cost["total"]["units"]


def test_the_cold_arm_always_costs_more_and_the_gap_is_the_construction():
    arms = acquisition_cost_arms(_task(), BUDGET, uses=USES)
    retained = cost_of(arms["retained"])
    cold = cost_of(arms["cold"])

    assert retained["construction"]["units"] == 0
    assert cold["construction"]["units"] > 0
    assert cold["use"]["units"] == retained["use"]["units"], (
        "the two arms must spend the same on use, or the comparison is"
        " measuring a different policy rather than a different history")
    assert cold["total"]["units"] - retained["total"]["units"] == \
        cold["construction"]["units"]
    assert retained["total"]["units"] < cold["total"]["units"]


def test_the_break_even_point_is_where_the_cold_arm_catches_up():
    """Retained wins only while the construction is not yet amortised.

    The crossover is the number a reader needs to judge the contrast, and
    deriving it from the two rates is what makes it checkable rather than
    asserted.
    """
    arms = acquisition_cost_arms(_task(), BUDGET, uses=USES)
    report = cost_report(arms, uses=USES)
    construction = arms["cold"]["construction_dispatches"] \
        * _PER_REQUEST_UNITS
    per_use = (arms["retained"]["dispatches_per_use"]
               * _PER_REQUEST_UNITS)
    assert report["break_even_uses"] == -(-construction // per_use)
    assert report["retained_wins_through_uses"] == \
        report["break_even_uses"]


def test_the_total_is_the_sum_of_the_parts_not_a_third_number():
    arms = acquisition_cost_arms(_task(), BUDGET, uses=USES)
    for name in ("retained", "cold"):
        cost = cost_of(arms[name])
        assert cost["total"]["units"] == total_cost(cost)
        assert cost["total"]["dispatches"] == \
            cost["construction"]["dispatches"] \
            + cost["use"]["dispatches"]


def test_a_declared_use_count_of_one_still_shows_the_construction():
    arms = acquisition_cost_arms(_task(), BUDGET, uses=1)
    retained = cost_of(arms["retained"])
    cold = cost_of(arms["cold"])
    assert retained["construction"]["units"] == 0
    assert cold["construction"]["units"] > 0
    assert cold["total"]["units"] - retained["total"]["units"] == \
        cold["construction"]["units"], (
        "at one use the retained arm still spends the same on use; only"
        " the construction is missing, and that is the whole difference")


def test_the_use_count_must_be_a_positive_integer():
    for bad in (0, -3, "6", 2.5, None):
        with pytest.raises(TreatmentRefused) as caught:
            acquisition_cost_arms(_task(), BUDGET, uses=bad)
        assert "uses" in str(caught.value)


def test_a_budget_with_no_construction_allowance_cannot_be_built():
    with pytest.raises(TreatmentRefused) as caught:
        acquisition_cost_arms(_task(), {"model_calls": 0}, uses=USES)
    assert "model_calls" in str(caught.value)


def test_the_report_names_the_denomination_it_is_counting():
    """A unit that is a reservation and not a charge must say so.

    The route reports no charge at all, so a number presented as a cost
    would be read as money. It is the denomination the reservation system
    needs in order to admit a dispatch, and both are reported because
    reporting only the flattering one understates the headroom a run needs.
    """
    arms = acquisition_cost_arms(_task(), BUDGET, uses=USES)
    report = cost_report(arms, uses=USES)
    assert report["denomination"] == "reservation-units"
    assert report["units_per_dispatch"] == _PER_REQUEST_UNITS
    assert report["provider_charge_units_per_dispatch"] is None, (
        "the route reported no charge, which is an absence and not a zero")
    assert report["provider_charge_state"] == "NOT_REPORTED"
    assert report["source"] == "reports/cap-sheets/invl02-s09-cap.json"
    assert "charge" in report["reads_as"] or "reservation" \
        in report["reads_as"]
