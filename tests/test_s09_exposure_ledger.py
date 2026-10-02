import json
from pathlib import Path

import pytest

from experiments.ad01 import s09_exposure_ledger as ledger

REPO_ROOT = Path(__file__).parents[1]


def _unverified_older(prior):
    """Put the older term back to prose, to exercise the refusal path.

    Both unsettled terms are verified against a durable row now, so the
    refusal has no live example left. Downgrading one term is how the
    property keeps a test: an unverified input must still stop a ceiling,
    and this is the only shape that can show it.
    """
    studies = {study.study_label: study for study in prior.studies}
    older = studies["older-ad01"]
    studies["older-ad01"] = ledger.replace(
        older,
        units_uncertain=ledger.Units(
            older.units_uncertain.value,
            ledger.Source(ledger.PROJECT_LEDGER, "live budget economics"),
            ledger.Evidence.CARRIED_FORWARD))
    return ledger.replace(prior, studies=tuple(
        studies[label] for label in sorted(studies)))


def test_prior_exposure_names_r4_and_the_older_ad01_study_with_their_sources():
    studies = {study.study_label: study
               for study in ledger.prior_exposure(REPO_ROOT).studies}

    assert set(studies) == {"r4", "older-ad01", "settled-output-shape"}

    r4 = studies["r4"]
    assert r4.study_root == "invl02-output-shape-550b-r4"
    assert r4.reservation_id == (
        "res-invl02-output-872608eb94c3-P1-audit-0023-a1")
    assert r4.operation_id == "invl02-output-872608eb94c3-P1-audit-0023-a1"
    assert (r4.dispatch_state, r4.reconcile_state, r4.settled) == (
        "unresolved", "unresolved", False)
    assert r4.units_uncertain.value == 2294
    assert r4.units_uncertain.source.artifact == ledger.R4_RECONCILIATION
    assert r4.receipt_outcome == "unknown"

    older = studies["older-ad01"]
    assert older.study_root == "invl02-live-e0"
    assert older.reservation_id == (
        "res-ad01-ad01-w0-I-72-b0-ad01-w0-dev-sw-00-construct-l1-init")
    assert (older.dispatch_state, older.reconcile_state, older.settled) == (
        "unresolved", "unresolved", False)
    assert older.units_uncertain.value == 3269
    assert older.units_uncertain.source.artifact == ledger.OLDER_RECONCILIATION

    settled = studies["settled-output-shape"]
    assert settled.settled is True
    assert settled.units_uncertain.value == 0


def test_both_unsettled_studies_are_verified_against_a_durable_row():
    """Neither term is prose any more.

    r4 was reconciled from `store-reconciliation.json` in an earlier pass.
    The older AD01 study carried 3269 units whose only evidence was the
    project ledger's prose until the durable store holding the operation was
    found and its reservation inputs recomputed, in
    `reports/evidence/invl02-live/store-reconciliation.json`.
    """
    prior = ledger.prior_exposure(REPO_ROOT)
    studies = {study.study_label: study for study in prior.studies}

    assert studies["r4"].units_uncertain.evidence is ledger.Evidence.VERIFIED
    assert studies["older-ad01"].units_uncertain.evidence is (
        ledger.Evidence.VERIFIED)

    bundled = json.loads(
        (REPO_ROOT / ledger.R4_RECONCILIATION).read_text())
    store_row = bundled["durable_store_rows"]["reservation"]
    assert studies["r4"].units_uncertain.value == store_row["amount"]
    assert store_row["state"] == "uncertain"
    assert store_row["settled"] is False

    older = json.loads(
        (REPO_ROOT / ledger.OLDER_RECONCILIATION).read_text())
    assert older["durable_store_rows"]["reservation"]["id"] == (
        studies["older-ad01"].reservation_id)
    assert older["reservation_recomputation"]["recomputed_units"] == (
        studies["older-ad01"].units_uncertain.value)


def test_conservative_total_sums_both_unsettled_studies_and_shows_the_arithmetic():
    total = ledger.conservative_total(ledger.prior_exposure(REPO_ROOT))

    assert total.value == 5563
    assert total.all_verified is True
    assert dict(total.terms)["r4"].value == 2294
    assert dict(total.terms)["older-ad01"].value == 3269
    assert total.arithmetic == (
        "r4 2294 VERIFIED + older-ad01 3269 VERIFIED = 5563 units")
    assert total.value >= sum(units.value for _, units in total.terms)


def test_conservative_total_excludes_the_settled_reservation():
    prior = ledger.prior_exposure(REPO_ROOT)
    total = ledger.conservative_total(prior)
    settled = [study for study in prior.studies if study.settled]

    assert prior.settled_units == 2294
    assert len(settled) == 1
    assert settled[0].reservation_id == "res-invl02-output-P1-audit-0023-a1"
    assert "settled-output-shape" not in dict(total.terms)
    assert total.value == 5563


def test_a_freeze_authorizes_a_count_of_dispatches_and_nothing_else():
    """The ceiling a freeze commits is a count of sends.

    It was also multiplied by a measured cost per dispatch to produce a unit
    ceiling, which made an eight-dispatch study claim a ceiling of zero units.
    A send count is not a denomination, so the multiplication is gone.
    """
    allowance = ledger.route_capacity_from_freeze(REPO_ROOT)

    assert allowance.max_dispatches == 8
    assert allowance.remaining_dispatches(1) == 7
    assert not hasattr(allowance, "authorized_ceiling_units")
    assert not hasattr(allowance, "units_per_dispatch")


def test_a_new_campaign_reserves_from_its_own_frozen_request_bounds():
    """The reservation allowance is sized by the broker, per request.

    A stand-in per-dispatch constant would make every campaign the same size
    regardless of what it sends, so the estimate is the broker's own answer
    for each prompt the freeze committed a digest for.
    """
    sizing = ledger.reservation_allowance_for_freeze(REPO_ROOT)

    assert sizing.is_derived
    assert {estimate.kind for estimate in sizing.per_request} == {
        "estimated-budget"}
    assert sizing.total_units > 0
    # The cap sheet is the source: 64 sends at the construction request's own
    # bounds, priced by the broker. r4's freeze priced 8 of its own prompts
    # at 18688 units and cannot price them against source that has moved on.
    assert sizing.total_units == 64 * sizing.per_request[0].units
    assert "cap-sheets" in sizing.source.artifact


def test_the_old_holds_are_reported_and_never_spent():
    """Nothing in sizing a new campaign discharges the 5563."""
    prior = ledger.prior_exposure(REPO_ROOT)
    plan = ledger.launch_plan(
        ledger.route_capacity_from_freeze(REPO_ROOT),
        ledger.reservation_allowance_for_freeze(REPO_ROOT),
        carried_units=ledger.conservative_total(prior).value)

    assert plan.may_launch is True
    assert plan.carried_units_unchanged == 5563
    assert all(study.held_reservation.state == "uncertain"
               for study in prior.studies if study.held_reservation)


def test_an_unverified_carried_term_does_not_become_a_larger_allowance():
    """A carried figure still cannot be consumed as a verified one.

    Nothing about separating the quantities lets a prose figure pass as
    evidence, so the conservative total still refuses to prefer it.
    """
    prior = _unverified_older(ledger.prior_exposure(REPO_ROOT))
    studies = {study.study_label: study for study in prior.studies}

    assert studies["older-ad01"].units_uncertain.evidence is (
        ledger.Evidence.CARRIED_FORWARD)
    assert ledger.conservative_total(prior).all_verified is False
    assert ledger.conservative_total(prior).value == 5563


def test_r4_crash_under_report_gap_is_flagged_as_a_provenance_warning():
    prior = ledger.prior_exposure(REPO_ROOT)
    warnings = {warning.code: warning
                for warning in ledger.provenance_warnings(prior)}

    assert "r4-crash-under-report" in warnings
    warning = warnings["r4-crash-under-report"]
    assert "dispatch_count=0" in warning.detail
    assert "1 physical dispatches" in warning.detail
    assert "unsound" in warning.consequence
    assert ledger.R4_BUNDLE in warning.detail
    assert prior.study("r4").bundle_under_reports_spend_by == 1


def test_r4_dispatch_count_conflict_is_reported_and_the_store_wins():
    prior = ledger.prior_exposure(REPO_ROOT)
    disputes = [conflict for conflict in ledger.conflicts(prior)
                if conflict.subject == "dispatch count for r4"]

    assert len(disputes) == 1
    assert disputes[0].positions == (
        "1 per %s" % ledger.R4_RECONCILIATION,
        "0 per %s" % ledger.R4_BUNDLE)
    assert "larger" in disputes[0].resolution
    assert prior.study("r4").max_dispatch_claims == 1


def test_conflicts_report_dispatch_disputes_and_the_settled_study_root():
    reported = ledger.conflicts(ledger.prior_exposure(REPO_ROOT))

    assert [conflict.subject for conflict in reported] == [
        "dispatch count for older-ad01",
        "dispatch count for r4",
        "study root of settled-output-shape",
    ]
    root_conflict = reported[-1]
    assert root_conflict.positions == (
        "invl02-output-shape-550b-r1", "held in invl02-output-shape-550b-r3")


def test_a_memory_total_below_the_recomputation_takes_the_larger_figure(tmp_path):
    for relative in (ledger.R4_RECONCILIATION, ledger.R4_BUNDLE,
                     ledger.OLDER_BUNDLE):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "stale-note.md").write_text("carries **2294 units** in total\n")

    prior = ledger.prior_exposure(REPO_ROOT)
    reported = {conflict.subject: conflict
                for conflict in ledger.conflicts(prior, memory)}

    assert ledger.conservative_total(prior).value == 5563
    stale = reported["stated unsettled total"]
    assert stale.positions == (
        "recomputed 5563 from reports/PROJECT-LEDGER.md",
        "2294 from stale-note.md")
    assert stale.resolution == "take the larger figure, 5563"


def test_a_memory_total_above_the_recomputation_takes_the_larger_figure(tmp_path):
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "overstated-note.md").write_text("carries **9000 units** in total\n")

    reported = {conflict.subject: conflict
                for conflict in ledger.conflicts(
                    ledger.prior_exposure(REPO_ROOT), memory)}

    assert reported["stated unsettled total"].positions == (
        "recomputed 5563 from reports/PROJECT-LEDGER.md",
        "9000 from overstated-note.md")
    assert reported["stated unsettled total"].resolution == (
        "take the larger figure, 9000")


def test_a_memory_total_that_agrees_is_not_reported_as_a_conflict(tmp_path):
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "agreed-note.md").write_text("carries **5563 units** in total\n")

    assert "stated unsettled total" not in {
        conflict.subject
        for conflict in ledger.conflicts(
            ledger.prior_exposure(REPO_ROOT), memory)}


def test_a_missing_memory_dir_reports_no_total_conflict():
    prior = ledger.prior_exposure(REPO_ROOT)
    reported = {conflict.subject for conflict in ledger.conflicts(
        prior, Path("/nonexistent-memory-dir"))}

    assert "stated unsettled total" not in reported
    assert ledger.conservative_total(prior).value == 5563


def test_older_ad01_attempt_count_dispute_raises_a_provenance_warning():
    warnings = {warning.code: warning
                for warning in ledger.provenance_warnings(
                    ledger.prior_exposure(REPO_ROOT))}

    assert "older-ad01-attempt-count-disputed" in warnings
    warning = warnings["older-ad01-attempt-count-disputed"]
    assert "4 per reports/evidence/invl02-live/e0-run.json" in warning.detail
    assert "may understate real sends" in warning.consequence


def test_every_reported_number_carries_a_source():
    report = ledger.ledger_report(REPO_ROOT)

    for row in report["prior_exposure"]:
        assert row["units_evidence"] in {"VERIFIED", "CARRIED_FORWARD"}
        assert row["units_source"]["artifact"]
        assert row["units_source"]["locator"]
        for claim in row["dispatch_claims"]:
            assert claim["source"]["artifact"]
    assert report["conservative_total"]["arithmetic"].endswith(
        "= 5563 units")
    for warning in report["provenance_warnings"]:
        assert warning["sources"]
        assert warning["consequence"]


def test_reserve_units_reproduces_both_historical_figures():
    assert ledger.reserve_units(981, 2048, 0) == 2294
    assert ledger.reserve_units(4880, 2048, 0) == 3269


def test_units_rejects_a_negative_figure():
    with pytest.raises(ValueError):
        ledger.Units(-1, ledger.Source("x", "y"), ledger.Evidence.VERIFIED)


def test_a_tie_between_a_verified_and_a_carried_figure_stays_carried_forward():
    verified = ledger.Units(2294, ledger.Source("a", "b"),
                            ledger.Evidence.VERIFIED)
    carried = ledger.Units(2294, ledger.Source("c", "d"),
                           ledger.Evidence.CARRIED_FORWARD)
    larger = ledger.Units(3000, ledger.Source("e", "f"),
                          ledger.Evidence.VERIFIED)

    assert verified.conservative_max(carried) is verified
    assert carried.conservative_max(verified).evidence is (
        ledger.Evidence.CARRIED_FORWARD)
    assert carried.conservative_max(larger) is larger
