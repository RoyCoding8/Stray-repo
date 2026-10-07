"""A cap sheet is a finite authorization whose every number is traceable.

The assignment states a dispatch ceiling for the connected study: two initial
constructions and one repair per cell, four route calls, twelve transfer calls,
64 physical sends including retries and failures. It states no unit ceiling and
no conversion rate, so the sheet has to derive one from the real broker
schedule applied to real frozen request bounds, or refuse.

The three denominations are separate types. A count of sends is not a count of
units and neither is a price, and the sheet cannot be serialized into a shape
where those are interchangeable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import s09_cap_sheet as sheet
from experiments.ad01 import s09_route_cost as cost
from settlement import broker

SHEET = sheet.new_campaign_sheet()


def test_the_sheet_states_the_assignments_counts_and_derives_the_rest():
    """Every line is either quoted from the assignment or recomputed by call."""
    provenance = {line.name: line.origin for line in SHEET.allowance}
    bounds = {line.name: line.origin for line in SHEET.bounds}

    assert provenance == {
        "initial_constructions_per_cell": sheet.STATED,
        "repairs_per_construction": sheet.STATED,
        "cells": sheet.STATED,
        "route_calibration_calls": sheet.STATED,
        "target_adaptation_calls": sheet.STATED,
        "physical_sends_ceiling": sheet.STATED,
    }
    assert bounds == {
        "construction_max_output_tokens": sheet.DERIVED,
        "construction_input_characters": sheet.DERIVED,
        "construction_deadline_ms": sheet.DERIVED,
        "construction_reasoning_effort": sheet.DERIVED,
    }


def test_the_sends_ceiling_is_the_sum_of_the_stated_parts_and_64():
    """24 initial plus 24 repairs plus 4 calibration plus 12 transfer is 64."""
    by_name = {line.name: line for line in SHEET.allowance}

    assert by_name["initial_constructions_per_cell"].sends == 2
    assert by_name["repairs_per_construction"].sends == 1
    assert by_name["cells"].sends == 12, "3 representations times 2 worlds times 2 experience arms"
    assert by_name["route_calibration_calls"].sends == 4
    assert by_name["target_adaptation_calls"].sends == 12
    assert by_name["physical_sends_ceiling"].sends == 64
    assert SHEET.total_sends() == 64, (
        "24 initial + 24 repair + 4 calibration + 12 transfer is the 64 the "
        "assignment states, and the sheet must not exceed it")
    with pytest.raises(TypeError, match="may not be"):
        by_name["cells"].sends * by_name["initial_constructions_per_cell"].sends, (
            "24 initial constructions is a product of two send counts the"
            " validator may do and this assertion may not")


def test_the_unit_allowance_is_the_broker_schedule_on_real_bounds():
    """The unit figure is derived by calling, never typed."""
    bounds = SHEET.construction_bounds()
    units, kind = broker.exposure_schedule(
        broker.MODEL_INFERENCE, bounds.as_request(), 0)

    assert units == bounds.reservation_units
    assert kind == "estimated-budget"
    assert units == 3269, (
        "4880 characters and 2048 output tokens is the construction request "
        "the older AD01 campaign actually made, and it reserved 3269")
    assert SHEET.unit_allowance.units == 64 * units
    assert SHEET.unit_allowance.unit_kind == "estimated-budget"


def test_a_send_count_cannot_be_read_as_units_or_as_a_price():
    """The denominations are separate types, not three names for one int."""
    sends = SHEET.total_sends()
    units = SHEET.unit_allowance.units

    assert isinstance(SHEET.total_sends(), sheet.Sends)
    assert isinstance(SHEET.unit_allowance.units, int)
    assert units != sends
    with pytest.raises(TypeError, match="may not be"):
        sends * 2
    with pytest.raises(TypeError, match="may not be"):
        sends + 1

    payload = SHEET.to_dict()
    assert payload["total_sends"] == sends
    assert payload["unit_allowance"]["units"] == units
    assert "price" not in payload["unit_allowance"], (
        "a reservation estimate is not a price and must not be named one")
    assert "no provider price is derivable" in json.dumps(payload)


def test_it_round_trips_and_is_content_addressed(tmp_path):
    """A second sheet over the same inputs has the same address, and so does
    the sheet that came back from disk."""
    again = sheet.new_campaign_sheet()
    assert again.sheet_digest == SHEET.sheet_digest

    reloaded = sheet.CapSheet.from_dict(SHEET.to_dict())
    assert reloaded.sheet_digest == SHEET.sheet_digest
    assert reloaded.to_dict() == SHEET.to_dict()

    written = SHEET.write(tmp_path)
    assert written.name == "invl02-s09-cap.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["sheet_digest"] == SHEET.sheet_digest
    assert sheet.CapSheet.from_dict(payload).validate(
        expected_digest=payload["sheet_digest"]).ok
    assert sheet.load().sheet_digest == SHEET.sheet_digest


def test_reading_a_committed_sheet_checks_its_address(tmp_path, monkeypatch):
    """A sheet edited after it was frozen is refused on read, not trusted."""
    committed = json.loads(
        (ROOT / "reports" / "cap-sheets" / "invl02-s09-cap.json").read_text(
            encoding="utf-8"))
    (tmp_path / "tampered.json").write_text(
        json.dumps(dict(committed, total_sends=512)), encoding="utf-8")
    monkeypatch.setattr(sheet, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="edited after it was frozen"):
        sheet.load("tampered.json")


def test_a_sheet_that_disagrees_with_its_own_lines_is_refused(tmp_path,
                                                              monkeypatch):
    """Redundant fields are checked too, even with a correct address.

    `total_sends` restates the allowance lines. A body that keeps its own
    address but changes the restatement has been edited with the digest
    recomputed, so the digest alone would accept it.
    """
    body = SHEET.to_dict()
    body["total_sends"] = 512
    body["sheet_digest"] = sheet.digest_of(body)
    (tmp_path / "resigned.json").write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(sheet, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="internally inconsistent"):
        sheet.load("resigned.json")


def test_a_number_that_cannot_be_derived_is_rejected_by_name():
    """The sheet says which line is not traceable instead of shipping it."""
    tampered = SHEET.to_dict()
    tampered["unit_allowance"]["units"] = 64 * 25
    tampered["sheet_digest"] = SHEET.sheet_digest

    result = sheet.CapSheet.from_dict(tampered).validate()

    assert not result.ok
    assert "unit_allowance_units_not_derivable" in result.failures
    assert "1600" in result.details["unit_allowance_units_not_derivable"], (
        "the rejection has to name the invented figure it caught")
    assert "209216" in result.details["unit_allowance_units_not_derivable"]


def test_a_tampered_body_is_caught_by_its_address_before_its_numbers():
    """A body whose figures all recompute still fails if its address moved."""
    tampered = SHEET.to_dict()
    tampered["sources"]["counts"] = "somewhere else"

    result = sheet.CapSheet.from_dict(tampered).validate(
        expected_digest=SHEET.sheet_digest)

    assert not result.ok
    assert "sheet_digest_mismatch" in result.failures
    assert result.details["sheet_digest_mismatch"].startswith("recorded ")


def test_the_repair_allowance_multiplies_constructions_not_cells():
    """One repair per construction, so 24 repairs, and the parts reach 64."""
    by_name = {line.name: line.sends.value for line in SHEET.allowance}
    initial = by_name["initial_constructions_per_cell"] * by_name["cells"]
    repairs = by_name["repairs_per_construction"] * initial
    flat = by_name["route_calibration_calls"] + by_name["target_adaptation_calls"]

    assert initial == 24
    assert repairs == 24
    assert initial + repairs + flat == 64
    assert SHEET.validate().ok, (
        "the stated ceiling is only consistent if repairs multiply"
        " constructions; multiplying cells instead would total 52")


def test_a_derived_count_may_not_disguise_itself_as_a_stated_one():
    origin = sheet.STATED
    bound = sheet.RequestBounds(
        model="m", message_characters=100, max_output_tokens=200,
        deadline_ms=1000, reasoning_effort="low")

    with pytest.raises(ValueError, match="STATED"):
        origin.require_derivation("construction_max_output_tokens", bound)
    sheet.DERIVED.require_derivation("construction_max_output_tokens", bound)


def test_a_stale_or_missing_probe_makes_the_billing_line_unmeasured():
    """The cap sheet does not carry a charge figure it cannot support."""
    charge = cost.measurement(cost.probe_record())["charge"]

    assert charge.state is cost.ChargeState.NOT_REPORTED
    billing = SHEET.provider_billing
    assert billing.state is cost.ChargeState.NOT_REPORTED
    assert billing.authorized_to_spend is True, (
        "using a confirmed free route is authorized; its receipt measured "
        "no price, which is a different claim")
    assert billing.units_derivable is False


def test_the_sheet_records_the_frozen_request_and_the_real_probe_disagree():
    """A 33-character smoke request and a 4880-character construction request
    are different reservations, and the sheet must not average them."""
    smoke = cost.probe_reservation_units()[0]
    construction = SHEET.construction_bounds().reservation_units

    assert smoke == 25
    assert construction == 3269
    assert smoke * 64 < construction
