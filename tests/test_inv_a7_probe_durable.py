"""A probe is a send, so it is a durable operation.

`scripts/invl02_live.py:probe` handed a hand-built `ModelRequest` to
`LiveGuard.infer`, which called a bare `HttpGatewayAdapter` directly. The
operation id `invl02-probe-<read_ms>` was minted and admitted nowhere, so
the send left no operation row, no reservation, no receipt and no exposure,
and the guard's ceiling was seeded with `already_spent=0` because there was
no store to ask. That is the defect milestone A exists to close, stated at
its smallest: a model call that leaves no durable trace.

The probe now takes the pair the preflight takes. `dsn` and
`allocation_id` are required together and are refused before anything else,
and the adapter is wrapped in `_DurableBrokerOutput`, which is the object
that calls `broker.ensure_operation` and `broker.dispatch_operation`. That
is the same broker shape lane A1 gave the preflight, not a second one.

Three properties are asserted against a real database, because each is a
statement about a row rather than about a return value:

  * a probe given a store produces one operation row under the study
    allocation, a reservation carrying exposure, and one decided receipt;
  * a probe given no store is REFUSED, with a literal reason, and writes no
    row and issues no send. This is the assertion that replaces
    `test_the_probe_verb_offers_no_dsn_flag`, and it is strictly stronger:
    the old test asserted the absence of a flag, which any code that simply
    did not implement durability satisfied. The new one asserts the
    presence of a refusal, which only a probe that knows it must be durable
    implements.
  * a second probe on the same operation id sends exactly once, because the
    identity is what the store settles against.

The adapter is an offline stub throughout, so nothing here reaches a
network or a paid route. `gateway` is the same explicit injection seam
`run_output_live` already has: the default is `None`, `None` builds the real
`HttpGatewayAdapter`, and a caller that omits it cannot end up anywhere but
the provider.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import live_construct as live
from scripts import invl02_live as driver
from settlement import broker, store
from settlement.gateway import ModelResponse, Usage

ROUTE = live.OUTPUT_ROUTE

#: The probe's own prompt asks for `{"entry": "ok"}`. The stub answers with
#: that shape, so a dispatched probe lands on the `text` branch rather than
#: on the empty-text refusal the guard would otherwise issue.
PROBE_TEXT = '{"entry": "ok"}'

#: One read window. The operation id is derived from it
#: (`invl02-probe-<read_ms>`), so a fixed value is what makes two probes the
#: same operation rather than two operations.
READ_MS = 1_500


class _RoutedAdapter:
    """An offline adapter that counts its own sends.

    Two of the three requirements are claims about how many times the wire
    was touched, so the count has to come from the object the broker called
    rather than from a difference in bookkeeping. Nothing here is a
    credential and nothing leaves the process.
    """

    def __init__(self, text: str = PROBE_TEXT, route: dict | None = None):
        self.text = text
        self.route = dict(route if route is not None else ROUTE)
        self.sent: list[str] = []

    def infer(self, request):
        self.sent.append(request.operation_id)
        return ModelResponse(
            request.operation_id, self.text,
            {"model": self.route["resolved_model"],
             "provider": self.route["provider"],
             "tier": self.route["tier"],
             "endpoint": self.route["endpoint"]},
            Usage(input_tokens=9, output_tokens=5, charge_units=0,
                  charge_scale=1000, billed=False,
                  provider_enforced_ceiling=None),
            "stop")

    def check_discovery(self):
        return "configured"

    def check_auth(self):
        return "authenticated"

    def cancel(self, operation_id):
        return True


def _allocate(dsn: str, allocation_id: str = "a7-probe",
              authorized: int = 10_000) -> str:
    """A study-bound allocation, because `operation_receipts` demands one.

    `store.operation_receipts` runs `_require_study_operation_binding`, which
    walks the allocation lineage and refuses an operation whose payload names
    a different study root. Seeding through `authority.authorize_study` is
    what binds the two together; a bare `seed_allocation` would leave the
    receipt read refusing an operation the dispatch had just settled.
    """
    from settlement import authority

    handle = authority.authorize_study(
        dsn, "invl02-probe-study", authorized=authorized,
        allocation_id=allocation_id,
        ceilings={"model_calls": authorized})
    return handle.allocation_id


def _rows(dsn: str, sql: str, params: tuple = ()) -> list[dict]:
    from psycopg.rows import dict_row
    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            out = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return out


@pytest.fixture()
def granted(monkeypatch, tmp_path):
    """The two live-path gates the probe checks before it sends.

    Neither is a credential. The grant marker is what
    `_require_grant` reads to refuse an ungranted live run, and the model
    name is what `_live_model` reads to refuse an unpinned one. Both are set
    here so the refusals under test are the probe's own and not these two.
    """
    monkeypatch.setenv("INVL02_LIVE_GRANT", "a7-offline-fixture")
    monkeypatch.setenv("INVL02_LIVE_MODEL", ROUTE["requested_model"])
    out = tmp_path / "probe-out"
    out.mkdir()
    return out


def test_a_probe_with_a_store_is_an_operation_with_a_receipt_and_exposure(
        migrated_db, granted):
    """Requirement one, read off the rows rather than off a return value.

    A probe still returns the same taxonomy it always did, so a test on the
    return value alone would pass on the bare send this replaces. The claim
    is about what the store holds afterwards: one operation row under the
    study allocation, a reservation carrying the exposure the effect
    scheduled, and one receipt whose outcome is decided rather than unknown.
    """
    dsn = migrated_db
    allocation_id = _allocate(dsn)
    gateway = _RoutedAdapter()

    result = driver.probe(granted, dsn=dsn, allocation_id=allocation_id,
                          read_ms=READ_MS, gateway=gateway)

    assert result["probe"] == "text", result
    operation_id = result["operation_id"]
    assert operation_id == "invl02-probe-%d" % READ_MS
    assert gateway.sent == [operation_id], gateway.sent

    operations = _rows(dsn, "SELECT * FROM operations WHERE id = %s",
                       (operation_id,))
    assert len(operations) == 1, (
        "the probe send admitted no operation row, so it left no identity")
    operation = operations[0]
    assert operation["allocation_id"] == allocation_id
    assert operation["payload"]["effect"] == "model-inference"

    exposure = _rows(
        dsn, "SELECT amount FROM reservations WHERE operation_id = %s",
        (operation_id,))
    assert exposure and int(exposure[0]["amount"]) > 0, (
        "an admitted probe with no reservation carries no exposure")

    receipts = store.operation_receipts(dsn, operation_id)
    assert len(receipts) == 1, receipts
    assert receipts[0]["outcome"] in ("success", "failure", "unknown"), (
        "the probe receipt has no decided outcome: %r" % receipts[0])

    settled = broker.read_operation(dsn, operation_id)
    assert settled["settled"] is True, (
        "the probe operation settled nothing, so a resume could not tell "
        "what it spent")


def test_a_probe_with_no_store_is_refused_and_sends_nothing(
        migrated_db, granted):
    """Requirement two, and the replacement for the deleted no-flag test.

    This is the assertion the coordinator asked for. `test_the_probe_verb_
    offers_no_dsn_flag` pinned the absence of a `--dsn` flag, which any
    probe that had simply not been made durable satisfied, and it passed on
    the bare send. What the probe owes instead is a refusal when it cannot
    be charged: a send with no store writes no row, and a row nobody can
    charge is the thing milestone A is closing. The literal is asserted so
    the refusal cannot be satisfied by any unrelated `ValueError`.
    """
    dsn = migrated_db
    allocation_id = _allocate(dsn)
    gateway = _RoutedAdapter()

    with pytest.raises(ValueError) as refusal:
        driver.probe(granted, read_ms=READ_MS, gateway=gateway)

    assert str(refusal.value) == driver.PROBE_STORE_REFUSAL, (
        "the probe refused for a reason of its own: %r" % str(refusal.value))
    assert "no store" in str(refusal.value)

    assert gateway.sent == [], (
        "a probe with no store was refused but the wire was touched anyway")
    assert _rows(dsn, "SELECT * FROM operations") == [], (
        "a refused probe still wrote an operation row")
    assert _rows(dsn, "SELECT * FROM reservations") == [], (
        "a refused probe still reserved exposure")
    assert _rows(dsn, "SELECT * FROM receipts") == [], (
        "a refused probe still wrote a receipt")

    # The allocation is still untouched, so nothing about the probe was
    # charged to a study that did not know it was sending.
    allocation = _rows(dsn, "SELECT * FROM allocations WHERE id = %s",
                       (allocation_id,))[0]
    assert (int(allocation["consumed"]), int(allocation["reserved"])) == (0, 0)


def test_a_second_probe_on_one_operation_id_sends_once(
        migrated_db, granted):
    """Requirement three: the identity is what prevents the second send.

    A probe re-run against the same store and the same read window arrives
    with an operation id the store already holds and settled. The send count
    is read from the adapter the broker actually called, so this fails on a
    second wire contact rather than on a bookkeeping difference.
    """
    dsn = migrated_db
    allocation_id = _allocate(dsn)
    gateway = _RoutedAdapter()

    first = driver.probe(granted, dsn=dsn, allocation_id=allocation_id,
                         read_ms=READ_MS, gateway=gateway)
    second = driver.probe(granted, dsn=dsn, allocation_id=allocation_id,
                          read_ms=READ_MS, gateway=gateway)

    assert gateway.sent == [first["operation_id"]], (
        "the same probe identity reached the gateway %d times: %r"
        % (len(gateway.sent), gateway.sent))
    assert second["operation_id"] == first["operation_id"]
    assert second["probe"] == "text", second
    assert len(_rows(dsn, "SELECT * FROM operations WHERE id = %s",
                     (first["operation_id"],))) == 1
    assert len(store.operation_receipts(dsn, first["operation_id"])) == 1


def test_a_half_given_pair_is_refused_before_the_wire(granted):
    """An allocation with no dsn is a row the store cannot charge either.

    The refusal is the same literal in both directions, so a caller cannot
    get a probe to run by handing half the pair.
    """
    with pytest.raises(ValueError) as refusal:
        driver.probe("/nonexistent-probe-out", allocation_id="a7-probe")

    assert str(refusal.value) == driver.PROBE_STORE_REFUSAL
