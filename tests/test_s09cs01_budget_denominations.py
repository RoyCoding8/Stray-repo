"""CS-01: the three budget quantities stay three quantities.

The budget chain read a missing provider report as a measured zero, then
multiplied that zero by a dispatch count to invent a unit ceiling, then
subtracted carried reservation units from that ceiling and called the
remainder a count of dispatches. Each step was arithmetically legal and each
was dimensionally false.

The seven tests below pin the corrected shape. They are grouped by the defect
they prevent, not by the module they call.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from experiments.ad01 import s09_exposure_ledger as ledger

REPO_ROOT = Path(__file__).parents[1]


# --- 1. a missing report is not a measured zero ----------------------------


def test_a_settled_receipt_with_no_charge_field_reads_as_not_reported():
    """The confirmed free route returned nulls on every charge field."""
    charge = ledger.charge_from_receipt({
        "outcome": "success",
        "usage": {"billed": None, "charge_units": None,
                  "charge_scale": None, "input_tokens": 23,
                  "output_tokens": 16},
    })

    assert charge.state is ledger.ChargeState.NOT_REPORTED
    assert charge.units is None
    assert charge.budget_units is None


def test_not_reported_is_never_a_verified_zero_capacity():
    """`int(charge or 0)` marked VERIFIED is the source of the whole collapse.

    The type has to make that conversion impossible rather than merely
    discouraged, so the constructor refuses an amount on an absent state and
    the absent states expose no number to coerce.
    """
    not_reported = ledger.charge_from_receipt(
        {"outcome": "success", "usage": {"charge_units": None}})

    assert not_reported.budget_units is None
    assert not_reported.budget_units is None
    with pytest.raises(ValueError):
        ledger.ProviderCharge(ledger.ChargeState.NOT_REPORTED, units=0)


def test_a_null_charge_cannot_become_a_capacity_anywhere_in_the_ledger():
    """No integer coercion of a charge survives anywhere in the module.

    The old code reached zero through `int(charge or 0)` and then multiplied
    it. Pinning the string is cheap but the coercion can be spelled other
    ways, so the check is structural: the module never passes a charge to
    `int()` and never floors one.
    """
    source = (REPO_ROOT / "experiments/ad01/s09_exposure_ledger.py").read_text()
    tree = ast.parse(source)
    coercions = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id in ("int", "round", "math.floor")
                 and _touches_charge(node)]
    unparsed = [node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "int" and "or 0" in ast.dump(node)]

    assert coercions == [], [ast.dump(node) for node in coercions]
    assert unparsed == []


def _touches_charge(node: ast.Call) -> bool:
    return "charge" in ast.dump(node).lower()


def test_a_capacity_needing_a_price_refuses_rather_than_defaulting_to_zero():
    """A route with no reported price yields no unit ceiling at all.

    This is the inverse of the old behavior. There, a zero price produced a
    zero ceiling, which was a confident answer. Here the absence of a price
    leaves the ceiling absent, which is a refusal the caller must see.
    """
    capacity = ledger.route_capacity_from_freeze(REPO_ROOT)

    assert capacity.charge.state is ledger.ChargeState.NOT_REPORTED
    assert capacity.charge.budget_units is None
    assert not hasattr(capacity, "authorized_ceiling_units")
    assert not hasattr(capacity, "units_per_dispatch")


# --- 2. a reported zero is a zero, and is not the absence ------------------


def test_a_reported_charge_of_zero_stays_zero():
    charge = ledger.charge_from_receipt(
        {"outcome": "success",
         "usage": {"charge_units": 0, "billed": True, "charge_scale": 1000}})

    assert charge.state is ledger.ChargeState.REPORTED
    assert charge.units == 0
    assert charge.budget_units == 0


def test_a_reported_zero_and_an_unreported_charge_are_different_states():
    """Null-versus-zero, both directions.

    The whole defect is the failure to tell these apart, so both directions
    are asserted rather than one.
    """
    zero = ledger.charge_from_receipt(
        {"outcome": "success", "usage": {"charge_units": 0, "billed": True,
                                         "charge_scale": 1000}})
    absent = ledger.charge_from_receipt(
        {"outcome": "success", "usage": {"charge_units": None, "billed": None,
                                         "charge_scale": None}})

    assert zero.state is not absent.state
    assert zero.budget_units == 0
    assert absent.budget_units is None
    assert zero != absent
    reported_zero = ledger.ProviderCharge(ledger.ChargeState.REPORTED, units=0)
    assert reported_zero != ledger.ProviderCharge.not_reported()
    assert reported_zero.budget_units == 0


def test_a_reported_charge_cannot_be_constructed_without_its_amount():
    with pytest.raises(ValueError):
        ledger.ProviderCharge(ledger.ChargeState.REPORTED)


def test_no_committed_receipt_is_unmeasured_rather_than_not_reported():
    """No receipt at all is a third state, distinct from a silent receipt."""
    charge = ledger.charge_from_receipt(None)

    assert charge.state is ledger.ChargeState.UNMEASURED
    assert charge.budget_units is None
    assert charge.state is not ledger.ChargeState.NOT_REPORTED


# --- 3. the reservation is sized from the real request ---------------------


def test_two_different_output_allowances_reserve_differently():
    """A stand-in multiplier is the failure Jev named at 0.78.

    If the per-request estimate came from a constant, these two would be
    equal, and the whole sizing would be a fiction.
    """
    small = ledger.ReservationAllowance.for_request(
        message_characters=981, max_output_tokens=512, retries=0)
    large = ledger.ReservationAllowance.for_request(
        message_characters=981, max_output_tokens=2048, retries=0)

    assert small.total_units != large.total_units
    assert small.total_units < large.total_units


def test_the_estimate_matches_the_broker_schedule_exactly():
    """Not a re-implementation of the formula. The broker's own answer.

    `reserve_units` in this module is the arithmetic the ledger states, and
    the broker's `exposure_schedule` is what the store will actually take.
    They are asserted equal so a drift in either is caught here.
    """
    allowance = ledger.ReservationAllowance.for_request(
        message_characters=1319, max_output_tokens=2048, retries=0)
    estimate = allowance.per_request[0]

    assert allowance.total_units == ledger.reserve_units(1319, 2048, 0)
    assert estimate.units == allowance.total_units
    assert estimate.kind == "estimated-budget"
    assert not hasattr(estimate, "broker_units"), (
        "an alias with no production caller is the surface this cleanup"
        " removed; a second spelling of the same number invites drift")


def test_the_r4_freeze_no_longer_re_renders_against_current_source():
    """r4's sizing is history, and history does not follow the source.

    Its eight prompts embed the task identifiers the instrument worlds used
    to publish. Those are opaque now, so re-rendering them from current source
    reproduces different bytes, and the sizing refuses with the prompt named
    rather than pricing a bound the campaign would not send. A frozen
    campaign's allowance stays exactly where it was left; a new campaign is
    sized from the cap sheet instead.
    """
    sizing = ledger._allowance_from_freeze(
        REPO_ROOT, ledger.R4_EVIDENCE + "/freeze.json", None, "free-550b")

    assert sizing.is_derived is False
    assert sizing.total_units is None
    assert "does not match the prompt the frozen source re-renders" \
        in sizing.refusal_reason


def test_the_broker_schedule_reproduces_the_reservation_r4_actually_held():
    """The strongest available check that the schedule is real.

    r4's durable store holds 2294 units for a 981-character, 2048-token
    request. Priced directly rather than through a freeze that can no longer
    re-render, the broker's own schedule must still produce that number.
    """
    units, kind = ledger._broker_exposure(
        {"model": "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
         "messages": [{"role": "user", "content": "x" * 981}],
         "max_output_tokens": 2048}, 0)

    assert units == 2294
    assert kind == "estimated-budget"


def test_a_campaign_is_sized_by_its_own_request_bounds():
    """One total over the sends the campaign authorizes, not a per-call rate.

    The two arms of r4 are history and cannot be re-rendered. What has to
    hold now is the property those tests were reaching for: the total is the
    sum over real requests at real bounds, and it is a different number from
    a bare per-call rate.
    """
    sizing = ledger.reservation_allowance_for_freeze(REPO_ROOT)

    assert sizing.is_derived
    assert len(sizing.per_request) == 1
    assert sizing.total_units == 64 * sizing.per_request[0].units
    assert sizing.total_units != sizing.per_request[0].units


def test_a_freeze_whose_prompts_do_not_re_render_refuses_instead_of_defaulting():
    """Jev's constraint, in the negative direction.

    A prompt the freeze cannot vouch for has no known bound, so sizing from
    it would be a guess. The refusal names the unknown rather than falling
    back to a constant.
    """
    import json

    freeze = json.loads(
        (REPO_ROOT / (ledger.R4_EVIDENCE + "/freeze.json")).read_text())
    freeze["prompt"]["rendered_digests"] = {
        key: "0" * 64 for key in freeze["prompt"]["rendered_digests"]}

    sizing = ledger._allowance_from_freeze(REPO_ROOT, "", freeze, "free-550b")

    assert sizing.is_derived is False
    assert "rendered_digest" in sizing.refusal_reason
    assert sizing.total_units is None


# --- 4. the quantities cannot be added to one another ----------------------


def test_dispatches_and_reservation_units_are_different_types():
    allowance = ledger.route_capacity_from_freeze(REPO_ROOT)
    reservation = ledger.ReservationAllowance.for_request(
        message_characters=981, max_output_tokens=2048, retries=0)

    assert isinstance(allowance, ledger.DispatchAllowance)
    assert isinstance(reservation, ledger.ReservationAllowance)
    assert not isinstance(allowance, ledger.ReservationAllowance)
    assert not isinstance(reservation, ledger.DispatchAllowance)


def test_subtracting_reservation_units_from_a_dispatch_allowance_is_impossible():
    """The dimensional error, pinned at the type level.

    The old `Budget` read `ceiling - already_spent - exposure` where ceiling
    was a unit figure and the other two were counts, and printed the result
    as "dispatches". Python cannot stop that arithmetic on dataclasses, so
    the exposure-bearing type refuses the operation instead.
    """
    allowance = ledger.route_capacity_from_freeze(REPO_ROOT)
    reservation = ledger.ReservationAllowance.for_request(
        message_characters=981, max_output_tokens=2048, retries=0)

    # There is no operator to call. Each method existed only to raise, was
    # reachable only from a test, and proved nothing a `hasattr` does not.
    for gone in ("minus_units", "remaining_after_units", "as_units",
                 "plus_units", "unit_ceiling"):
        assert not hasattr(allowance, gone), "%s is still exposed" % gone
    assert not hasattr(reservation, "remaining_after_units")
    assert allowance.max_dispatches == 8
    assert not any("unit" in name for name in vars(type(allowance))), (
        "a dispatch allowance exposes no unit at all, so the two currencies"
        " cannot meet")


def test_the_module_exposes_no_ceiling_minus_carry_headroom():
    """The old arithmetic is gone, not merely unused.

    `headroom_units` was a unit figure described as remaining dispatches, so
    the name itself is what invited the dimensional mistake back.
    """
    for gone in ("Budget", "RefusedBudget", "BudgetInput", "BudgetResult",
                 "RouteCapacity", "budget_for_new_study"):
        assert not hasattr(ledger, gone), "%s is still exposed" % gone
    for absent in ("headroom_units", "ceiling_units", "carry_units",
                   "authorized_ceiling_units", "units_per_dispatch"):
        assert not hasattr(ledger, absent), "%s is still exposed" % absent


def test_a_dispatch_allowance_answers_dispatches_only():
    """What the freeze actually decides, in the only unit it decides."""
    allowance = ledger.route_capacity_from_freeze(REPO_ROOT)

    assert allowance.max_dispatches == 8
    assert allowance.remaining_dispatches(1) == 7
    assert allowance.remaining_dispatches(8) == 0
    assert "8" in allowance.arithmetic
    assert "unit" not in allowance.arithmetic.lower()


# --- 5. the old uncertain holds survive untouched ---------------------------


def test_the_prior_exposure_is_still_5563_in_the_same_terms():
    total = ledger.conservative_total(ledger.prior_exposure(REPO_ROOT))

    assert total.value == 5563
    assert total.all_verified is True
    assert dict(total.terms)["r4"].value == 2294
    assert dict(total.terms)["older-ad01"].value == 3269
    assert total.arithmetic == (
        "r4 2294 VERIFIED + older-ad01 3269 VERIFIED = 5563 units")


def test_each_held_unit_carries_its_grant_and_study_root():
    """5563 is debt owed to named allocations, not a free-floating total.

    The brief requires the grant and root scope recorded on the hold. A
    number with no owner cannot be carried into a new freeze honestly.
    """
    prior = ledger.prior_exposure(REPO_ROOT)
    by_label = {study.study_label: study for study in prior.studies}

    r4 = by_label["r4"].held_reservation
    assert r4.grant is not None
    assert r4.study_root == "invl02-output-shape-550b-r4"
    assert r4.state == "uncertain"
    assert r4.settled is False

    older = by_label["older-ad01"].held_reservation
    assert older.grant is not None
    assert older.grant.grant_id == "ad01-campaign-invl02-live-e0"
    assert older.grant.authorized_units == 200000
    assert older.study_root == "invl02-live-e0"
    assert older.state == "uncertain"
    assert older.settled is False


def test_the_holds_are_counted_once_and_never_released_or_settled():
    prior = ledger.prior_exposure(REPO_ROOT)
    total = ledger.conservative_total(prior)

    held = [study.held_reservation for study in prior.studies
            if study.held_reservation is not None]
    assert sum(reservation.units for reservation in held) == 5563
    assert total.value == sum(reservation.units for reservation in held)
    assert {reservation.state for reservation in held} == {"uncertain"}
    assert not any(reservation.settled for reservation in held)
    # Counting is decided by the study's own flag, read where the total is
    # built, rather than by a method on the reservation that nothing called.
    assert all(study.contributes_to_liability
               for study in prior.studies if study.held_reservation is not None)


def test_the_older_hold_honors_the_reconciliation_agrees_flag():
    """`agrees: true` is a precondition for the verified figure, not a hint."""
    prior = ledger.prior_exposure(REPO_ROOT)
    older = prior.study("older-ad01")

    assert older.held_reservation.computed_from_inputs is True
    assert older.units_uncertain.evidence is ledger.Evidence.VERIFIED
    assert older.units_uncertain.value == 3269


# --- 6. a new campaign is sized and launched without settling the old ------


def test_a_new_campaign_gets_a_finite_allowance_while_the_holds_stand():
    """The point of separating the quantities.

    Under the old chain the new study's ceiling was 0 and 5563 verified
    units sat above it, so the study could not be sized at all. Here the
    dispatch allowance and the reservation allowance are each finite on
    their own terms.
    """
    prior = ledger.prior_exposure(REPO_ROOT)
    dispatches = ledger.route_capacity_from_freeze(REPO_ROOT)
    sizing = ledger.reservation_allowance_for_freeze(REPO_ROOT)

    assert dispatches.max_dispatches == 8
    assert sizing.is_derived
    assert sizing.total_units > 0
    assert ledger.conservative_total(prior).value == 5563


def test_launching_a_new_campaign_needs_no_settlement_of_the_old_holds():
    """Nothing in sizing a new campaign releases, settles, or reduces 5563.

    The liability and the new campaign's own allowance are separate records.
    A caller that sizes the new campaign must leave the old rows alone.
    """
    prior = ledger.prior_exposure(REPO_ROOT)
    before = {study.study_label: study.held_reservation.units
              for study in prior.studies if study.held_reservation is not None}
    before_states = {study.study_label: study.held_reservation.state
                     for study in prior.studies
                     if study.held_reservation is not None}

    sizing = ledger.reservation_allowance_for_freeze(REPO_ROOT)
    allowance = ledger.route_capacity_from_freeze(REPO_ROOT)
    plan = ledger.launch_plan(
        allowance, sizing,
        carried_units=ledger.conservative_total(prior).value)

    after = ledger.prior_exposure(REPO_ROOT)
    assert {study.study_label: study.held_reservation.units
            for study in after.studies if study.held_reservation is not None} \
        == before
    assert {study.study_label: study.held_reservation.state
            for study in after.studies if study.held_reservation is not None} \
        == before_states
    assert plan.may_launch is True
    assert plan.dispatches.max_dispatches == 8
    assert plan.reservation.total_units > 0
    assert plan.carried_units_unchanged == 5563


def test_a_launch_plan_refuses_when_the_reservation_cannot_be_sized():
    unsized = ledger.ReservationAllowance.unsized(
        "the freeze commits no prompt digest, so no request bound is known")
    allowance = ledger.route_capacity_from_freeze(REPO_ROOT)

    plan = ledger.launch_plan(allowance, unsized)

    assert plan.may_launch is False
    assert "no request bound is known" in plan.refusal_reason


def test_a_launch_plan_refuses_a_dispatch_allowance_with_no_frozen_count():
    unlimited = ledger.DispatchAllowance(
        label="free-550b", max_dispatches=None,
        source=ledger.Source("no freeze", "absent",
                             "a dispatch count nobody authorized"),
        charge=ledger.ProviderCharge.not_reported())
    sizing = ledger.reservation_allowance_for_freeze(REPO_ROOT)

    plan = ledger.launch_plan(unlimited, sizing)

    assert plan.may_launch is False
    assert "dispatch" in plan.refusal_reason


# --- 7. durable resume consumes only the dispatch count --------------------


def test_resume_spends_dispatches_and_never_looks_at_units():
    allowance = ledger.route_capacity_from_freeze(REPO_ROOT)

    resumed = ledger.resume_dispatch_budget(allowance, spent=1)

    assert resumed.spent_dispatches == 1
    assert resumed.remaining_dispatches == 7
    assert resumed.ceiling_dispatches == 8
    assert "1" in resumed.arithmetic and "7" in resumed.arithmetic
    assert "unit" not in resumed.arithmetic.lower()


def test_a_spent_count_beyond_the_allowance_refuses_rather_than_going_negative():
    allowance = ledger.route_capacity_from_freeze(REPO_ROOT)

    budget = ledger.resume_dispatch_budget(allowance, spent=9)

    assert budget.remaining_dispatches is None
    assert "9" in budget.refusal_reason
    assert "8" in budget.refusal_reason


def test_no_unit_figure_reaches_the_resume_path():
    """Structural: the resume type has no field a unit could be put in."""
    resumed = ledger.resume_dispatch_budget(
        ledger.route_capacity_from_freeze(REPO_ROOT), spent=1)

    fields = set(resumed.__dataclass_fields__)
    assert fields == {"ceiling_dispatches", "spent_dispatches",
                      "remaining_dispatches", "arithmetic", "refusal_reason"}
    assert not any("unit" in name for name in fields)
    assert not any("token" in name for name in fields)
