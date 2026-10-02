from pathlib import Path
from experiments.ad01 import s09_exposure_ledger as ledger

REPO_ROOT = Path(__file__).parents[1]


def test_the_older_units_are_now_recomputed_from_the_durable_store():
    studies = {s.study_label: s for s in ledger.prior_exposure(REPO_ROOT).studies}
    older = studies["older-ad01"]
    assert older.units_uncertain.evidence is ledger.Evidence.VERIFIED
    assert older.units_uncertain.value == 3269
    assert older.units_uncertain.source.artifact == ledger.OLDER_RECONCILIATION


def test_the_recomputation_agrees_with_the_reservation_row():
    import json
    document = json.loads((REPO_ROOT / ledger.OLDER_RECONCILIATION).read_text())
    recomputed = document["reservation_recomputation"]
    assert recomputed["agrees"] is True
    assert recomputed["recomputed_units"] == recomputed["reservation_row_units"]
    assert recomputed["message_characters"] == 4880


def test_verifying_the_number_does_not_settle_the_debt():
    """The point of the change, stated so a later edit cannot undo it."""
    import json
    document = json.loads((REPO_ROOT / ledger.OLDER_RECONCILIATION).read_text())
    rows = document["durable_store_rows"]
    assert rows["reservation"]["state"] == "uncertain"
    assert rows["operation"]["settled"] is False
    studies = {s.study_label: s for s in ledger.prior_exposure(REPO_ROOT).studies}
    assert studies["older-ad01"].contributes_to_liability is True


def test_the_conservative_total_stays_the_same_number_with_a_verified_term():
    total = ledger.conservative_total(ledger.prior_exposure(REPO_ROOT))
    assert total.value == 5563
    assert total.all_verified is True
    assert total.arithmetic == "r4 2294 VERIFIED + older-ad01 3269 VERIFIED = 5563 units"
