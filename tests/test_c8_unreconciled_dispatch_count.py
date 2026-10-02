"""An unreconciled dispatch count propagates as unknown, not as a crash.

`_r4_study` read `bundle["dispatch_count"]` through `int()`. Since `c7d2952`
the bundle writer emits the string `"unknown"` for both counts unless the store
confirms them, so a future unreconciled bundle reaches `int("unknown")` and
dies with `ValueError: invalid literal for int() with base 10: 'unknown'`.

Nothing in the repository commits such a bundle today. Every `dispatch_count`
under `reports/evidence/` is an integer, which is why the crash is latent. The
hazard is the next one.

The ledger's own convention already answers what an unavailable number means.
`ProviderCharge` makes it a state rather than a zero, `already_spent_in_store`
returns `None` for a store it could not read, and `offline_recompute` carries
`"unknown"` through a bundle as a value a comparison can still test. So the
count propagates. It is not an error, and it is emphatically not a zero: a zero
here would enter `max_dispatch_claims` and could displace the durable store's
figure, which is the one number the ceiling is allowed to be built from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import s09_exposure_ledger as ledger

UNKNOWN = "unknown"


def _repo_with_r4(bundle_dispatch_count) -> Path:
    """A repo root carrying r4's reconciliation, with one field overridden."""
    import tempfile

    root = Path(tempfile.mkdtemp())
    document = json.loads((ROOT / ledger.R4_RECONCILIATION).read_text())
    if bundle_dispatch_count is not None:
        document["bundle_claim"]["dispatch_count"] = bundle_dispatch_count
    target = root / ledger.R4_RECONCILIATION
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document), encoding="utf-8")
    return root


def test_the_committed_r4_bundle_still_reads_as_a_dispute() -> None:
    """The guard on the fix: today's artifact is unchanged by it."""
    study = ledger._r4_study(ROOT, None)

    assert study.max_dispatch_claims == 1
    assert study.dispatch_count_disputed is True


def test_an_unreconciled_bundle_count_does_not_crash_the_ledger() -> None:
    study = ledger._r4_study(_repo_with_r4(UNKNOWN), None)

    assert {claim.value for claim in study.dispatch_claims} == {1, UNKNOWN}


def test_an_unknown_count_does_not_displace_the_durable_store_figure() -> None:
    """A zero here would let a bundle that knows nothing outrank the store.

    `max_dispatch_claims` feeds the r4-crash-under-report warning's detail
    string, which names the store's count as the one to trust. A max of 0
    there would print a ceiling figure no send ever supported.
    """
    study = ledger._r4_study(_repo_with_r4(UNKNOWN), None)

    assert study.max_dispatch_claims == 1


def test_an_unknown_count_does_not_read_as_a_dispute() -> None:
    """One position is unknown and one is 1; that is not two positions.

    `dispatch_count_disputed` gates a conflict entry that says the
    reservation "may understate real sends". The store already decided that
    for r4, so the warning belongs to the under-report branch instead.
    """
    study = ledger._r4_study(_repo_with_r4(UNKNOWN), None)

    assert study.dispatch_count_disputed is False


def test_a_bundle_count_that_is_still_numeric_is_read_as_a_dispatch() -> None:
    assert ledger._r4_study(_repo_with_r4(0), None).max_dispatch_claims == 1


def test_a_settled_bundle_with_an_unreconciled_count_does_not_crash() -> None:
    """The same field, on the writer `c7d2952` actually changed.

    `_settled_study` reads `candidate_view.dispatch_count`, which is the exact
    key `_OutputDispatchAccounting.candidate_fields` writes `"unknown"` into.
    It runs for every ledger row whose state is `settled`, so it is the
    reachable half of this defect: `bundle_claim` is hand-authored in a
    reconciliation document nobody regenerates, while `candidate_view` is
    written by every unavailable output run.
    """
    import tempfile

    root = Path(tempfile.mkdtemp())
    source = json.loads(
        (ROOT / "reports/evidence/invl02-output-shape-550b-r3"
         "/output-run.json").read_text())
    source["candidate_view"]["dispatch_count"] = UNKNOWN
    target = root / ledger.EVIDENCE_ROOT / "synthetic" / "output-run.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(source), encoding="utf-8")
    (root / ledger.PROJECT_LEDGER).write_text(
        (ROOT / ledger.PROJECT_LEDGER).read_text(encoding="utf-8"),
        encoding="utf-8")

    claim = ledger.ReservationClaim(
        reservation_id=source["candidate_view"]["durable_receipts"][0][
            "reservation_id"],
        amount=2294, state="settled",
        source=ledger.Source(ledger.PROJECT_LEDGER, "synthetic"))

    study = ledger._settled_study(root, claim)

    assert [entry.value for entry in study.dispatch_claims] == [UNKNOWN]
    assert study.max_dispatch_claims == 0
    assert study.dispatch_count_disputed is False
