"""Behaviour tests for the W2 retention and adaptation contrasts.

Each test calls the campaign the way a user does and asserts the result it
observes against a literal expected value. Nothing here asserts that an
imported function was called, and a test that would still pass if every
import returned `None` is not a test of this module.

The census is computed with no model and no dispatch, so these run offline
and cost a reducer walk each. The live campaign is not exercised here; it
needs a route and a store, and its artifact is verified by
`w2_retention_verify` instead.
"""

from __future__ import annotations

import copy
import json

import pytest

from experiments.ad01 import e2_replication as replica
from experiments.ad01 import w2_retention_campaign as campaign
from experiments.ad01 import w2_retention_verify as verify


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------


def test_the_frozen_contrast_verifies_against_the_module():
    body = campaign.verify_contrast(campaign.freeze())
    assert body["arms"] == ["relevant", "none", "irrelevant"]
    assert [p["name"] for p in body["panels"]] == ["retention", "adaptation"]


def test_an_edited_freeze_is_refused_rather_than_reported():
    frozen = campaign.freeze()
    # A field the panel actually carries. Editing the family would not
    # change the digest check on this freeze, because the budget is
    # recorded per panel and the run would refuse on the gate instead.
    frozen["body"]["panels"][0]["target_split"] = "within"
    with pytest.raises(campaign.W2Refused) as refusal:
        campaign.verify_contrast(frozen)
    # The digest check fires first, so the refusal names the two digests
    # rather than the drifted field. Both refusals are correct; the run
    # stops before any dispatch either way.
    assert "addresses as" in str(refusal.value)

def test_a_recomputed_digest_over_an_edited_body_is_still_refused():
    # The digest is not the seal. `verify_contrast` re-derives the body from
    # the panel and compares, so a forgery that recomputes its own digest
    # passes the digest check and fails the body check.
    frozen = campaign.freeze()
    frozen["body"]["budgets"] = [4, 8]
    frozen["freeze_digest"] = replica.digest_of(frozen["body"])
    with pytest.raises(campaign.W2Refused):
        campaign.verify_contrast(frozen)


# ---------------------------------------------------------------------------
# the retention blocker
# ---------------------------------------------------------------------------


def test_no_panel_target_can_name_a_retained_method():
    closure = campaign.measure_repertoire_closure()
    assert closure["repertoire_closed"] is True
    assert closure["rows"], "the closure measured no target at all"
    for row in closure["rows"]:
        assert row["eligible_count"] == 2, row
        assert row["retained_method_nameable"] is False, row


def test_every_arm_sees_the_same_eligible_methods_on_every_target():
    closure = campaign.measure_repertoire_closure()
    assert closure["every_arm_sees_the_same_eligible_methods"] is True
    assert len(closure["distinct_eligible_sets"]) == 1


# ---------------------------------------------------------------------------
# the census, and the inherited defect
# ---------------------------------------------------------------------------


def test_a_graph_panel_has_a_real_default_so_its_positive_side_can_open():
    # Graph is a ceiling-only panel: the qualification gate cannot read it,
    # but a ceiling needs no policy, so the census is still measured.
    spec = campaign.CENSUS_ONLY_PANELS[0]
    result = campaign.census(campaign.panel_targets(spec),
                             family=spec["family"])
    assert result["default_cell"] == "seed-gr-ddmin@8"
    assert result["open_rows"] == result["rows_measured"] > 0
    for row in result["rows"]:
        assert row["default"] is not None, row
        assert row["attainable_positive_delta"] is not None, row


def test_the_primary_panel_leaves_the_positive_side_open():
    # The prior lane's panel was software/within and was closed. The panel
    # the primary contrast runs on must not be that panel, or a null here
    # would be arithmetic rather than a measurement.
    panel = campaign.PANELS[0]
    result = campaign.census(campaign.panel_targets(panel),
                             family=panel["family"])
    assert result["open_rows"] > 0, result
    closed = campaign.census(
        campaign.panel_targets(campaign.CENSUS_ONLY_PANELS[2]),
        family="software")
    assert closed["open_rows"] == 0, closed


def test_both_w2_panels_run_on_a_family_the_gate_can_read():
    # The qualification gate's authored policies all name a `seed-sw-`
    # method, so a graph target cannot be read at all and a run on one
    # refuses rather than reporting a number.
    gate = campaign.qualification_census()
    assert gate["readable"] > 0, gate
    for panel in campaign.PANELS:
        assert panel["family"] in gate["readable_families"], panel
        for split in [panel["target_split"]] + (
                [panel["within_split"]] if panel.get("within_split") else []):
            for row in gate["rows"]:
                if (row["panel"] == panel["name"]
                        and row["split"] == split):
                    assert row["readable"] is True, row


def test_the_adaptation_within_side_is_reported_as_the_closed_bound_it_is():
    # §W2's adaptation contrast is within-domain against held-out-domain.
    # The within side here is the prior lane's panel, which is closed, and
    # that is reported rather than presented as a contrast that could move.
    panel = next(p for p in campaign.PANELS if p.get("within_split"))
    within = campaign.census(
        campaign.panel_targets(panel, split=panel["within_split"]),
        family=panel["family"])
    held = campaign.census(campaign.panel_targets(panel),
                           family=panel["family"])
    assert within["open_rows"] == 0, within
    assert held["open_rows"] > 0, held


def test_the_inherited_census_disagrees_exactly_where_the_default_is_nonzero():
    # The defect is a missing default cell, so it is invisible on a target
    # whose real default happens to be 0.0: measuring the gap from nothing
    # and measuring it from zero are the same number there. The rows that
    # disagree are exactly the rows whose true default is not zero, and on
    # every one of them the inherited number is the larger, because it
    # measures the gap from nothing.
    defect = campaign.defect_report()
    assert defect["rows"], "the defect report measured nothing"
    for row in defect["rows"]:
        if row["family"] != "graph":
            continue
        nonzero_default = (row["this_default_value"] or 0.0) != 0.0
        assert row["inherited_default_present"] is False, row
        assert row["agrees"] is (not nonzero_default), row
        if not row["agrees"]:
            assert (row["inherited_positive_delta"]
                    > row["this_positive_delta"]), row


def test_every_graph_target_measures_no_default_in_the_inherited_census():
    for panel in campaign.CENSUS_ONLY_PANELS:
        if panel["family"] != "graph":
            continue
        for task_id in campaign.panel_targets(panel):
            from experiments.ad01 import e2_contrast_campaign as experience

            theirs = experience.reachability_census(
                [task_id],
                method_ids=campaign.method_ids_for("graph"),
                budgets=list(campaign.BUDGETS))["rows"][0]
            assert theirs["default"] is None, theirs
            assert theirs["attainable_positive_delta"] is not None, theirs


def test_the_inherited_census_agrees_on_software_because_its_default_is_right():
    # The defect is specific to a family the inherited function never ran on.
    # If this ever agrees too, the discrepancy is not the one described.
    task_id = "ad01-w0-within-sw-00"
    mine = campaign.census([task_id], family="software")["rows"][0]
    from experiments.ad01 import e2_contrast_campaign as experience

    theirs = experience.reachability_census(
        [task_id], method_ids=["seed-sw-ddmin", "seed-sw-greedy"],
        budgets=list(campaign.BUDGETS))["rows"][0]
    assert mine["attainable_positive_delta"] == \
        theirs["attainable_positive_delta"]


# ---------------------------------------------------------------------------
# the adaptation pairing
# ---------------------------------------------------------------------------


def test_a_dropped_position_is_named_and_not_averaged_in():
    # The within side carries only t0 and t1, so position 2 has no within
    # reading and must be dropped and named. It must not become a zero in
    # the mean.
    left = {"family": "graph", "split": "within",
            "pools": {"target": ["t0", "t1", "t2"]},
            "readings": {n: {"t0": _reading(0.5), "t1": _reading(0.5)}
                         for n in replica.ARMS}}
    right = {"family": "graph", "split": "transfer",
             "pools": {"target": ["u0", "u1", "u2"]},
             "readings": {n: {"u0": _reading(0.1), "u1": _reading(0.1),
                              "u2": _reading(0.1)}
                          for n in replica.ARMS}}
    result = campaign.adaptation_contrast(
        {"adaptation/within": left, "adaptation/transfer": right})
    assert result["n_pairs"] == 2
    assert len(result["dropped_positions"]) == 1
    assert result["dropped_positions"][0]["position"] == 2
    # every arm's delta list holds exactly the two kept positions
    for arm in replica.ARMS:
        assert len(result["arm_deltas"][arm]) == 2
        assert all(abs(d - 0.4) < 1e-9 for d in result["arm_deltas"][arm])


def test_a_position_with_no_reading_on_either_side_is_never_a_zero():
    left = {"family": "graph", "split": "within",
            "pools": {"target": ["t0", "t1"]},
            "readings": {n: {"t0": _reading(0.5)} for n in replica.ARMS}}
    right = {"family": "graph", "split": "transfer",
             "pools": {"target": ["u0", "u1"]},
             "readings": {n: {"u0": _reading(0.1), "u1": _reading(0.1)}
                          for n in replica.ARMS}}
    result = campaign.adaptation_contrast(
        {"adaptation/within": left, "adaptation/transfer": right})
    assert result["n_pairs"] == 1
    for key, block in result["contrasts"].items():
        assert block["n"] == 1, key
        assert block["n_positions"] == 1, key


def test_the_two_experience_contrasts_are_counted_separately():
    # Pooling them would double every position and answer a question about
    # two arms together.
    left = {"family": "graph", "split": "within",
            "pools": {"target": ["t0", "t1"]},
            "readings": {n: {"t0": _reading(0.5), "t1": _reading(0.5)}
                         for n in replica.ARMS}}
    right = {"family": "graph", "split": "transfer",
             "pools": {"target": ["u0", "u1"]},
             "readings": {n: {"u0": _reading(0.1), "u1": _reading(0.1)}
                          for n in replica.ARMS}}
    result = campaign.adaptation_contrast(
        {"adaptation/within": left, "adaptation/transfer": right})
    assert set(result["contrasts"]) == {"relevant-minus-none",
                                        "irrelevant-minus-none"}
    for block in result["contrasts"].values():
        assert len(block["deltas"]) == 2
        assert block["n"] == 2


def test_the_adaptation_delta_is_held_out_minus_within_in_the_right_order():
    left = {"family": "graph", "split": "within",
            "pools": {"target": ["t0"]},
            "readings": {n: {"t0": _reading(0.8)} for n in replica.ARMS}}
    right = {"family": "graph", "split": "transfer",
             "pools": {"target": ["u0"]},
             "readings": {n: {"u0": _reading(0.2)} for n in replica.ARMS}}
    result = campaign.adaptation_contrast(
        {"adaptation/within": left, "adaptation/transfer": right})
    entry = result["pairs"][0]
    for arm in replica.ARMS:
        assert entry["arms"][arm]["within"] == pytest.approx(0.8)
        assert entry["arms"][arm]["held_out"] == pytest.approx(0.2)
        assert entry["arms"][arm]["delta"] == pytest.approx(0.6)


def _reading(reduction: float) -> dict:
    """A stored reading whose reduction is exactly `reduction`.

    Shaped like a real `Reading.as_dict`: the candidate's measure is under
    `candidate_measure` and there is **no** `measure` key at all.
    `replica._normalized_reduction` reads the checker's report shape, whose
    measure key *is* `measure`, so calling it on one of these returns 1.0
    for every reading. The first live run of this campaign used it that way
    in the adaptation pairing and in the readings check, and both passed
    while reporting a uniform 1.0 the campaign never observed.

    `initial_measure` is 100 so any two-decimal reduction is exactly
    representable in the measures. Rounding the measure to a coarser
    denominator would make the stored reduction disagree with the one the
    verifier re-derives, and the verifier is right to reject that.
    """
    initial = 100
    candidate = int(round(initial * (1 - reduction)))
    return {"verdict": "preserved", "scored": True,
            "initial_measure": initial,
            "candidate_measure": candidate,
            "normalized_reduction": (initial - candidate) / initial}


def test_an_absent_billing_field_read_as_the_string_none_is_not_a_cost():
    # The ledger records `repr(value)`, so an absent field is the string
    # "None". Reading that as a number would fail every honest report,
    # which is the opposite of what the check is for. A field carrying a
    # real value is still caught.
    report = _live_report()
    report["accounting"] = {
        "receipt_count": 1,
        "billed_values_seen": ["None"],
        "charge_units_values_seen": ["None"],
        "receipts": [{"operation_id": "op-1", "outcome": "success",
                      "usage": {"billed": None, "charge_units": None,
                                "input_tokens": 10}}],
    }
    outcome = verify.verify(report)
    assert outcome["checks"]["accounting"]["agrees"] is True

    report["accounting"]["charge_units_values_seen"] = ["7"]
    assert verify.verify(report)["checks"]["accounting"]["agrees"] is False


def test_a_receipt_claiming_a_price_is_rejected():
    report = _live_report()
    report["accounting"] = {
        "receipt_count": 1,
        "billed_values_seen": ["None"],
        "charge_units_values_seen": ["None"],
        "receipts": [{"operation_id": "op-1", "outcome": "success",
                      "usage": {"billed": True, "charge_units": None,
                                "input_tokens": 10}}],
    }
    assert verify.verify(report)["checks"]["accounting"]["agrees"] is False


def test_a_reading_carries_no_measure_key_and_the_reduction_rule_needs_one():
    # The pin on the bug this campaign shipped and fixed. The frozen rule
    # reads `measure`; a Reading has `candidate_measure`. Asking the frozen
    # rule for a Reading's reduction returns 1.0, which is why the first
    # live run's adaptation table was uniformly 1.0.
    reading = _reading(0.5)
    assert "measure" not in reading
    assert "candidate_measure" in reading
    assert replica._normalized_reduction(reading) == 1.0
    assert verify.campaign.replica._normalized_reduction(reading) == 1.0
    # the report's own field is the truth the campaign compares against
    assert reading["normalized_reduction"] == 0.5


# ---------------------------------------------------------------------------
# the verifier
# ---------------------------------------------------------------------------


def _census_report() -> dict:
    body = campaign.verify_contrast(campaign.freeze())
    panels = {}
    for panel in campaign.PANELS:
        for split in [panel["target_split"]] + (
                [panel["within_split"]] if panel.get("within_split") else []):
            key = "%s/%s" % (panel["name"], split)
            targets = campaign.panel_targets(panel, split=split)
            panels[key] = {
                "family": panel["family"], "split": split,
                "pools": {"target": targets},
                "readings": {}, "paired": None,
                "reachability_census": campaign.census(
                    targets, family=panel["family"]),
            }
    return campaign.build_report({
        "measured_live": False, "freeze": campaign.freeze(),
        "panels": panels,
        "repertoire_closure": campaign.measure_repertoire_closure(),
        "inherited_census_defect": campaign.defect_report(),
    }, namespace=campaign.NAMESPACE, campaign_kind="census-only")

def test_a_clean_offline_report_verifies_with_nothing_failed():
    outcome = verify.verify(_census_report())
    assert outcome["failed"] == []
    assert outcome["agrees"] is True
    assert outcome["offline_only"] is True


def test_a_skipped_check_is_not_reported_as_a_passed_check():
    outcome = verify.verify(_census_report())
    assert "readings" in outcome["skipped"]
    assert outcome["checks"]["readings"]["agrees"] is None
    assert "skipped" in outcome


def test_an_offline_report_without_the_declaration_is_not_skipped():
    # The skip is a declaration, not an inference. A census report that
    # loses it gets the live checks run, and fails them for want of
    # evidence rather than passing by being excused.
    report = _census_report()
    report["offline_only"] = None
    outcome = verify.verify(report)
    assert outcome["offline_only"] is False
    assert outcome["skipped"] == []
    # `adaptation` fails first because a census report carries no
    # adaptation contrast; both it and `readings` are evidence-dependent
    # and neither is excused.
    assert "adaptation" in outcome["failed"]
    assert outcome["checks"]["readings"]["agrees"] is not None


def test_an_inflated_census_ceiling_is_rejected():
    report = _census_report()
    key = sorted(report["panels"])[0]
    census_row = dict(report["panels"][key]["reachability_census"])
    census_row["max_attainable_positive_delta"] = 0.9
    census_row["rows"] = [dict(r, attainable_positive_delta=0.9)
                          for r in census_row["rows"]]
    report["panels"][key] = dict(report["panels"][key],
                                  reachability_census=census_row)
    outcome = verify.verify(report)
    assert "census" in outcome["failed"]


def test_withdrawing_the_retention_blocker_is_rejected():
    report = _census_report()
    report["measureability"] = dict(
        report["measureability"], retained_method_leg_measurable=True)
    outcome = verify.verify(report)
    assert "measureability" in outcome["failed"]


def test_a_fabricated_defect_report_is_rejected():
    report = _census_report()
    report["inherited_census_defect"] = dict(
        report["inherited_census_defect"], disagreements=0,
        disagreeing_task_ids=[])
    outcome = verify.verify(report)
    assert "defect" in outcome["failed"]


def test_an_edited_freeze_is_rejected_by_the_verifier():
    report = _census_report()
    frozen = copy.deepcopy(report["freeze"])
    frozen["body"]["budgets"] = [4]
    report["freeze"] = frozen
    outcome = verify.verify(report)
    assert "freeze" in outcome["failed"]


def test_a_live_report_with_no_readings_is_not_treated_as_offline_only():
    report = _census_report()
    report["measured_live"] = True
    report["offline_only"] = None
    outcome = verify.verify(report)
    # A live report must not pass the reading-dependent checks by being
    # empty; it fails them for want of the evidence, not by being skipped.
    assert outcome["offline_only"] is False
    assert "readings" in outcome["checks"]
    assert outcome["skipped"] == []


def test_the_red_proof_rejects_every_forgery_it_builds():
    report = _live_report()
    proofs = verify.red_proof(report)
    assert proofs, "the red proof built no forgery at all"
    for name, outcome in proofs.items():
        assert outcome["agrees"] is False, (name, outcome)


def test_the_red_proof_rejects_an_inflation_that_moves_its_own_measure():
    # Two forgeries of the same kind of claim, and each is caught by the
    # check that owns it. The one that moves its own measure is caught
    # downstream, because the paired deltas over that reading were not
    # recomputed with it. The one that leaves the measure alone is caught
    # by the readings check directly.
    report = _live_report()
    proofs = verify.red_proof(report)
    assert "self_consistent_inflation" in proofs
    assert "reduction_without_its_measure" in proofs
    assert proofs["self_consistent_inflation"]["agrees"] is False
    # Caught downstream rather than by the readings check, because the
    # forgery moved the measure with the reduction. Which check trips
    # depends on which panels the reading feeds; what matters is that
    # something re-derived does.
    assert proofs["self_consistent_inflation"]["failed"]
    assert proofs["self_consistent_inflation"]["failed"] != ["census"]
    assert "readings" in proofs["reduction_without_its_measure"]["failed"]


def test_a_reduction_moved_without_its_measure_is_caught_by_the_readings_check():
    report = _live_report()
    proofs = verify.red_proof(report)
    assert proofs["reduction_without_its_measure"]["failed"]


def test_the_clean_live_report_verifies():
    outcome = verify.verify(_live_report())
    assert outcome["failed"] == []
    assert outcome["agrees"] is True


def _live_report() -> dict:
    """A report shaped like the live one, with readings the checks can run.

    Built from the frozen panel and the campaign's own scorer so the
    reductions are real, and paired with the frozen `paired_report` so the
    stored numbers are the ones a live run would store.

    Every panel carries the targets of the split it names. Getting that
    wrong is not caught by a count, it is caught by the census check,
    which recomputes each panel's rows from the split and finds the task
    ids in a different order.
    """
    retention = campaign.PANELS[0]
    adaptation = next(p for p in campaign.PANELS if p.get("within_split"))

    def panel_rows(spec, split, offset):
        targets = campaign.panel_targets(spec, split=split)
        readings = {}
        for index, task_id in enumerate(targets):
            for arm_index, arm in enumerate(replica.ARMS):
                reduction = round(0.1 * (index + 1) + 0.05 * arm_index, 6)
                readings.setdefault(arm, {})[task_id] = _reading(reduction)
        return targets, readings, {
            "family": spec["family"], "split": split,
            "pools": {"target": targets}, "readings": readings,
            "paired": replica.paired_report(readings),
            "reachability_census": campaign.census(targets,
                                                   family=spec["family"])}

    retention_targets, retention_readings, retention_row = panel_rows(
        retention, retention["target_split"], 0)
    within_targets, within_readings, within_row = panel_rows(
        adaptation, adaptation["within_split"], 0)
    held_targets, held_readings, held_row = panel_rows(
        adaptation, adaptation["target_split"], 0)

    panels = {
        "retention/%s" % retention["target_split"]: retention_row,
        "adaptation/%s" % adaptation["within_split"]: within_row,
        "adaptation/%s" % adaptation["target_split"]: held_row,
    }
    bundle = {
        "measured_live": True, "freeze": campaign.freeze(),
        "panels": panels,
        "paired": campaign.merge_paired(panels),
        "adaptation": campaign.adaptation_contrast(panels),
        "repertoire_closure": campaign.measure_repertoire_closure(),
        "inherited_census_defect": campaign.defect_report(),
        "accounting": None,
    }
    return campaign.build_report(bundle, namespace=campaign.NAMESPACE,
                                 campaign_kind="test")


def test_the_report_carries_no_claim_resting_on_the_terminal_verdict():
    report = _live_report()
    claims = report["measureability"]
    assert claims["terminal_verdict_usable"] is False
    assert claims["retained_method_leg_measurable"] is False
    assert claims["retention_measurable"] is True
    assert "normalized_reduction" in claims["retention_observable"]


def test_the_route_key_is_absent_from_the_report():
    report = _live_report()
    outcome = verify.verify(report, key="sk-cx-local")
    assert outcome["checks"]["no_key"]["agrees"] is True
    # A string the report really carries must be found, or the check would
    # pass on every report including one holding the key.
    assert verify.verify(report, key="seed-gr-ddmin")["checks"][
        "no_key"]["agrees"] is False
