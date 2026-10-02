"""The provider charge is tri-state, and the reservation is request-dependent.

The old module read a null `charge_units` as a measured zero, certified that
zero VERIFIED on the strength of a committed receipt, and carried a hardcoded
25 units per dispatch that was a smoke request's number promoted to a
conversion rate. Each of those is a way of inventing a fact.

The receipt committed at `evidence_s09_route_probe/probe.json` says three
things: the call happened, it succeeded, and it carried no charge field. Only
the first two are measured. The third is an absence, and the tests below hold
that line in both directions so an absence cannot drift back into a zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_route_cost as cost
from experiments.ad01 import s09_cap_sheet as sheet
from settlement import broker


def test_the_committed_probe_reported_no_charge_and_that_is_not_zero():
    """The real receipt. The third assertion is the defect being retired."""
    measured = cost.measurement()

    assert measured["status"] == "measured"
    assert measured["outcome"] == "success"
    assert measured["provider_charge_state"] == cost.ChargeState.NOT_REPORTED
    assert measured["provider_charge_units"] is None
    assert "not a measured zero" in measured["reads_as"]


def test_not_reported_yields_no_units_per_dispatch_and_no_verified_zero():
    """NOT_REPORTED is not 0, and it is not VERIFIED either.

    The old code turned the null into `int(0)` and stamped it VERIFIED. The
    receipt verified that the call happened. It verified no price.
    """
    charge = cost.measurement()["charge"]

    assert charge.state is cost.ChargeState.NOT_REPORTED
    assert charge.budget_units is None
    with pytest.raises(ValueError):
        cost.Charge(cost.ChargeState.NOT_REPORTED, units=0)


def test_a_reported_zero_stays_zero_and_is_distinguishable_from_not_reported():
    """A receipt that says 0 is an observed zero, and stays an observed zero."""
    zero = cost.Charge.reported(0)

    assert zero.state is cost.ChargeState.REPORTED
    assert zero.budget_units == 0
    assert zero.state is not cost.ChargeState.NOT_REPORTED
    assert zero.reads_as() != cost.Charge.not_reported().reads_as()

    synthesized = cost.measurement(_receipt_with_charge(0))
    assert synthesized["provider_charge_state"] == cost.ChargeState.REPORTED
    assert synthesized["provider_charge_units"] == 0
    assert synthesized["charge"].budget_units == 0

    positive = cost.measurement(_receipt_with_charge(41))
    assert positive["provider_charge_state"] == cost.ChargeState.REPORTED
    assert positive["charge"].budget_units == 41


def test_no_committed_receipt_is_unmeasured_and_yields_no_budget():
    """Three states, and the third is not a zero and not a not-reported."""
    charge = cost.Charge.unmeasured()

    assert charge.state is cost.ChargeState.UNMEASURED
    assert charge.budget_units is None
    assert "no budget may be derived" in charge.reads_as()

    measured = cost.measurement({})
    assert measured["status"] == "unavailable"
    assert measured["provider_charge_state"] == cost.ChargeState.UNMEASURED
    assert cost.measurement({})["charge"].budget_units is None


def test_the_reservation_estimate_follows_the_real_request():
    """Two different output bounds, two different reservations, from the broker."""
    small = sheet.RequestBounds(
        model="openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
        message_characters=4880, max_output_tokens=2048,
        deadline_ms=300_000, reasoning_effort="high")
    large = sheet.RequestBounds(
        model=small.model, message_characters=4880, max_output_tokens=4096,
        deadline_ms=300_000, reasoning_effort="high")

    assert cost.reservation_units(small.as_request()) == (
        broker.exposure_schedule(
            broker.MODEL_INFERENCE, small.as_request(), 0))
    assert small.reservation_units < large.reservation_units
    assert small.reservation_units == 3269
    assert large.reservation_units == 5317
    assert cost.reservation_units(small.as_request()) == (3269, "estimated-budget"), (
        "the same request must give the same number, not a fresh one")


def test_the_committed_probes_reservation_recomputes_to_the_25_on_record():
    """The hardcoded 25 was right once, for one 33-character request."""
    record = cost.probe_record()
    units, kind = cost.probe_reservation_units(record)

    assert (record["request"]["max_output_tokens"],
            len(record["request"]["prompt"])) == (16, 33)
    assert (units, kind) == (25, "estimated-budget")
    assert cost.probe_request(record)["max_output_tokens"] == 16
    assert "25 units" in record["reservation_note"], (
        "the committed note is the claim under test, not the source of it")


def test_the_25_is_not_a_per_dispatch_conversion_rate():
    """The same smoke request would have reserved 2049 units for a real answer."""
    smoke = sheet.RequestBounds(
        model="m", message_characters=33, max_output_tokens=16,
        deadline_ms=300_000, reasoning_effort="low")
    construction = sheet.RequestBounds(
        model="m", message_characters=4880, max_output_tokens=2048,
        deadline_ms=300_000, reasoning_effort="high")

    assert smoke.reservation_units == 25
    assert construction.reservation_units == 3269
    assert construction.reservation_units > 100 * smoke.reservation_units


def test_no_production_module_carries_the_hardcoded_25():
    """grep -rn RESERVATION_UNITS_PER_DISPATCH over production code: nothing."""
    offenders = []
    for directory in ("experiments", "scripts", "src"):
        for path in (ROOT / directory).rglob("*.py"):
            if "RESERVATION_UNITS_PER_DISPATCH" in path.read_text(
                    encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
    assert not hasattr(cost, "RESERVATION_UNITS_PER_DISPATCH")
    assert cost.probe_reservation_units()[0] == 25, (
        "the number is now computed, not stored")


def test_the_module_reads_committed_evidence_and_depends_on_no_ledger():
    """It has to be importable on its own to report what a receipt said.

    A charge is a fact about a receipt, not about a budget type, so this
    module imports no budget vocabulary at all. That also keeps it working
    when the ledger's allowance types are replaced.
    """
    source = (ROOT / "experiments" / "ad01" / "s09_route_cost.py").read_text(
        encoding="utf-8")

    assert "s09_exposure_ledger" not in source
    assert "units_per_dispatch" not in source, (
        "a units-per-dispatch figure is the converted number, and the type"
        " that carried it is gone from the ledger")
    assert "RESERVATION_UNITS_PER_DISPATCH" not in source


def test_the_caveats_report_a_derived_number_and_no_stored_one():
    caveats = " ".join(cost.caveats())

    assert "reports unknown usage" in caveats
    assert "reservation units come from" in caveats


def test_the_key_is_never_part_of_the_measurement():
    measured = str(cost.measurement()) + str(cost.caveats())

    assert "SETTLEMENT_GATEWAY_KEY" not in measured
    assert "sk-" not in measured


def test_the_measurement_survives_the_probe_database_being_dropped():
    """It is read from committed evidence, not from a disposable store."""
    assert cost.EVIDENCE.is_file()
    assert "dbname=" not in str(cost.EVIDENCE)
    assert cost.measurement()["status"] == "measured"


def _receipt_with_charge(charge_units: int) -> dict:
    return {
        "measured_at": "2026-09-26",
        "route": cost.FREE_MODEL,
        "request": {"prompt": "x", "max_output_tokens": 16,
                    "reasoning_effort": "low"},
        "receipt": {"outcome": "success", "text": "ready",
                    "usage": {"charge_units": charge_units, "billed": True,
                              "charge_scale": 1,
                              "input_tokens": 23, "output_tokens": 16}},
    }
