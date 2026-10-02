"""The route cost is measured, not assumed, and the caveats are pinned.

The preflight would not issue a budget because no units-per-dispatch figure
existed. Inventing one would have been the failure this campaign is about,
so it was measured with one live call on the free route.

The receipt came back reporting no charge field at all. This file used to
assert that the provider "charges nothing" and that the resulting zero is
VERIFIED. Both assertions encoded the defect the assignment describes: a
receipt that reported nothing was being rendered as a measurement of free, and
the resulting integer zero was certified on the strength of a settled
receipt that had verified a call and no price. The assertions below now hold
the absence as an absence.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_route_cost as cost


def test_the_measurement_is_read_from_the_settled_receipt():
    measured = cost.measurement()

    assert measured["status"] == "measured"
    assert measured["outcome"] == "success"
    assert measured["model"] == cost.FREE_MODEL
    assert measured["response_text"] == "ready"
    assert measured["input_tokens"] > 0
    assert measured["output_tokens"] > 0


def test_the_provider_reported_no_charge_and_that_is_not_a_measured_zero():
    """The receipt settled, succeeded, and carried no charge field.

    An absence is not an observed zero, and reading it as one is what put a
    verified integer 0 into the budget arithmetic.
    """
    measured = cost.measurement()

    assert measured["provider_charge_state"] == cost.ChargeState.NOT_REPORTED
    assert measured["provider_charge_units"] is None
    assert measured["provider_billed"] is None
    assert "not a measured zero" in measured["reads_as"]


def test_the_capacity_derives_no_units_from_an_unreported_charge():
    """No price in the receipt, so nothing may be converted into units.

    The old assertion was `value == 0` and `evidence is Evidence.VERIFIED`,
    which is the defect: a receipt verified that the call happened, and zero
    verified a price it never carried. The projection this test used to read
    is gone, and a dispatch allowance is now a count of sends that refuses to
    become a unit figure.
    """
    charge = cost.measurement()["charge"]

    assert charge.state is cost.ChargeState.NOT_REPORTED
    assert charge.budget_units is None
    assert not hasattr(cost, "route_capacity"), (
        "a per-dispatch cost projection is the converted number; the ledger"
        " sizes a reservation from a freeze's own request bounds instead")


def test_the_reservation_requirement_is_recomputed_from_the_real_request():
    """The 25 was real, and it was one 33-character request's answer.

    The number is now produced by calling the broker's exposure schedule on
    the probe's own request, so it is a property of that request rather than a
    constant that any future dispatch inherits.
    """
    units, kind = cost.probe_reservation_units()
    caveats = " ".join(cost.caveats())

    assert (units, kind) == (25, "estimated-budget")
    assert "the free route reports unknown usage" in caveats or \
        "reports unknown usage" in caveats
    assert "reservation units come from" in caveats
    assert "never from a per-dispatch constant" in caveats
    assert not hasattr(cost, "RESERVATION_UNITS_PER_DISPATCH"), (
        "the invented per-dispatch constant is gone from the module")


def test_a_zero_measured_today_is_not_a_promise_about_tomorrow():
    caveats = " ".join(cost.caveats())

    assert "not a guarantee" in caveats
    assert "says nothing about what a longer construction response" in caveats
    assert "computed for that one 33-character request" in caveats, (
        "the reservation headroom must be stated with the request it came from")
    assert "no authorized unit ceiling" not in caveats, (
        "the ceiling is None in the capacity, not a caveat string")


def test_the_key_is_never_part_of_the_measurement():
    measured = str(cost.measurement()) + str(cost.caveats())

    assert "SETTLEMENT_GATEWAY_KEY" not in measured
    # The key itself is deliberately not named here. A negative assertion
    # that spells the secret out still puts it in git, and the assignment
    # says never put the key in git, reports or evidence. The env var name
    # is the whole of what a leak would carry into a measurement.
    assert "sk-" not in measured


def test_a_missing_probe_refuses_rather_than_defaulting_to_zero():
    """A missing receipt must not read as a measured zero, or as a free route.

    That distinction is the whole point: "we measured nothing" and "we
    measured zero" are different facts, and now "we measured an absence" is a
    third one that is neither of them.
    """
    original = cost.EVIDENCE
    try:
        cost.EVIDENCE = ROOT / "evidence_s09_route_probe" / "absent.json"
        measured = cost.measurement()

        assert measured["status"] == "unavailable"
        assert measured["provider_charge_state"] == cost.ChargeState.UNMEASURED
        assert measured["charge"].budget_units is None
    finally:
        cost.EVIDENCE = original


def test_the_measurement_survives_the_probe_database_being_dropped():
    """It is read from committed evidence, not from a disposable store.

    An earlier version read the receipt out of a live database, so dropping
    that database turned a real measurement back into "unknown". A number the
    project will rely on has to outlive the machine that produced it.
    """
    assert cost.EVIDENCE.is_file()
    assert "dbname=" not in str(cost.EVIDENCE)
    assert cost.measurement()["status"] == "measured"
