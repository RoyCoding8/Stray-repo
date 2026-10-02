"""The preflight dispatch has to be a durable operation, not a bare send.

`experiments/ad01/live_construct.py:_preflight_dispatch` used to hand a
hand-built `ModelRequest` straight to `LiveGuard.infer`, which called the
adapter directly. The operation id was minted by `preflight_operation_id`
and never admitted anywhere, so a send on this path had no operation row,
no reservation, no receipt and no exposure. Every other branch of
`inv-a.md` S1 is the same shape, but this is the one the shipped preflight
runs, so it is the one the study's evidence rests on.

The requirement being made true is the assignment's: an accepted operation
has persistent identity, an allocation, a result-or-unknown outcome, and
exposure. `broker.ensure_operation` supplies the first two and writes the
reservation; `broker.dispatch_operation` supplies the third and fourth
through the broker's own receipt path. Those are the calls
`experiments/ad01/construct.py:_call` and
`experiments/ad01/learner_revision.py:_dispatch` already make, and this file
holds them to the same three claims they have to carry.

Three properties are asserted against a real database, because each is a
statement about a row and a query rather than about a return value:

  * an operation id that was sent appears in `operations`, carries a
    reservation, and holds exactly one receipt whose outcome is decided;
  * asking twice for one operation id sends once, because the second
    dispatch finds a settled operation rather than a prepared one;
  * the ceiling is answered by the store. A spend the store records but
    the guard's process never saw still closes the ceiling, which is the
    resume case an in-process integer cannot represent.

The adapter is an offline stub throughout, so nothing here reaches a network
or a paid route. The guard is still the shipped `LiveGuard`, so
what is under test is the preflight route and not a reimplementation of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import live_construct as live
from settlement import broker, store
from settlement.gateway import FakeGatewayAdapter, ModelResponse, Usage

ROUTE = live.OUTPUT_ROUTE

#: Four specs that all predict zero. The bytes parse and they solve nothing,
#: so a dispatched preflight lands on `poor-task-result`, which proves the
#: send happened, cleared the route check and was carried to the parser.
ZERO_PROGRAM = json.dumps(
    {"specs": [{"const": 0, "mask": 0, "pair": None}] * 4})


class _RoutedAdapter:
    """An offline adapter whose responses carry the frozen route.

    `FakeGatewayAdapter` answers with `{"simulated": True}` and no route
    fields at all, so the shipped guard refuses it on the route check before
    any of this file's claims could be observed. The guard is the one under
    test for its evidence duties, so the adapter has to return a body that
    passes it, and returning exactly the frozen route is the smallest such
    body.

    It counts its own sends, because two of the three requirements are
    claims about how many times the wire was touched.
    """

    def __init__(self, text: str = ZERO_PROGRAM, route: dict | None = None):
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
            Usage(input_tokens=11, output_tokens=7, charge_units=0,
                  charge_scale=1000, billed=False,
                  provider_enforced_ceiling=None),
            "stop")

    def check_discovery(self):
        return "configured"

    def check_auth(self):
        return "authenticated"

    def cancel(self, operation_id):
        return True


def _allocate(dsn: str, allocation_id: str = "a1", authorized: int = 10_000):
    """A study-bound allocation, because `operation_receipts` demands one.

    `store.operation_receipts` runs `_require_study_operation_binding`, which
    walks the allocation lineage and refuses an operation whose payload names
    a different study root. Seeding through `authority.authorize_study` is
    what binds the two together; a bare `seed_allocation` would leave the
    receipt read refusing an operation the dispatch had just settled.
    """
    from settlement import authority

    handle = authority.authorize_study(
        dsn, "invl02-preflight-study", authorized=authorized,
        allocation_id=allocation_id, ceilings={"model_calls": authorized})
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


def _guard(dsn: str, allocation_id: str, *, ceiling: int | None = None,
           gateway=None):
    """The guard `preflight_run` builds, so the test drives the shipped shape.

    Wrapping the adapter is what makes the send durable, and handing the
    guard a `spend_reader` is what makes its ceiling answer to the store.
    Building anything else here would test a preflight nobody runs.
    """
    gateway = gateway if gateway is not None else _RoutedAdapter()
    spent = live.spent_dispatches(dsn, allocation_id)
    return live.LiveGuard(
        live.preflight_dispatch_gateway(dsn, gateway,
                                        allocation_id=allocation_id),
        pinned_model=ROUTE["requested_model"],
        ceiling=1 + spent if ceiling is None else ceiling,
        automatic_retries=0, expected_route=dict(ROUTE),
        spend_reader=lambda: live.spent_dispatches(dsn, allocation_id))


def test_a_preflight_send_is_an_operation_with_a_receipt_and_exposure(migrated_db):
    """Requirement one, read off the rows rather than off a return value.

    The preflight returns the same taxonomy it always did, so a test on the
    return value would pass on the raw send that this replaces. The claim is
    about what the store holds afterwards: one operation row under the study
    allocation, a reservation carrying the exposure the effect scheduled,
    and one decided receipt.
    """
    dsn = migrated_db
    allocation_id = _allocate(dsn)

    attempt = live._preflight_dispatch(
        _guard(dsn, allocation_id), arm="P1", attempt=1,
        dsn=dsn, allocation_id=allocation_id)

    assert attempt["outcome"] == "poor-task-result", attempt["reason"]
    operation_id = attempt["operation_id"]
    assert operation_id == live.preflight_operation_id("P1", 1)

    operations = _rows(dsn, "SELECT * FROM operations WHERE id = %s",
                       (operation_id,))
    assert len(operations) == 1, "the preflight send admitted no operation row"
    operation = operations[0]
    assert operation["allocation_id"] == allocation_id
    assert operation["payload"]["effect"] == "model-inference"

    exposure = _rows(
        dsn, "SELECT amount FROM reservations WHERE operation_id = %s",
        (operation_id,))
    assert exposure and int(exposure[0]["amount"]) > 0, (
        "an admitted operation with no reservation carries no exposure")

    receipts = store.operation_receipts(dsn, operation_id)
    assert len(receipts) == 1, receipts
    assert receipts[0]["outcome"] in ("success", "failure", "unknown")
    settled = broker.read_operation(dsn, operation_id)
    assert settled["settled"] is True, (
        "the operation settled nothing, so a resume could not tell what the "
        "preflight spent")


def test_a_second_dispatch_of_one_operation_id_sends_once(migrated_db):
    """Requirement two: the identity is what prevents the second send.

    A preflight that is retried, or a run that resumes and reaches the same
    attempt, arrives here with an operation id the store already holds. The
    send count is read from the adapter the broker actually called, so this
    fails on a second wire contact rather than on a bookkeeping difference.
    """
    dsn = migrated_db
    allocation_id = _allocate(dsn)
    gateway = _RoutedAdapter()
    guard = _guard(dsn, allocation_id, gateway=gateway)

    first = live._preflight_dispatch(guard, arm="P1", attempt=1, dsn=dsn,
                                     allocation_id=allocation_id)
    second = live._preflight_dispatch(guard, arm="P1", attempt=1, dsn=dsn,
                                      allocation_id=allocation_id)

    assert gateway.sent == [first["operation_id"]], (
        "the same operation identity reached the gateway %d times: %r"
        % (len(gateway.sent), gateway.sent))
    assert second["operation_id"] == first["operation_id"]
    assert len(_rows(dsn, "SELECT * FROM operations WHERE id = %s",
                     (first["operation_id"],))) == 1
    assert len(store.operation_receipts(dsn, first["operation_id"])) == 1


def test_the_ceiling_is_the_stores_count_and_not_this_processs_integer(
        migrated_db):
    """Requirement three: the ceiling answers to the store.

    The guard's own integer counts what this process did. A spend recorded by
    an earlier process, or by an operation admitted before a crash, is in the
    store and not in the integer. Here the store already holds two sends the
    guard never saw, the ceiling is three, and one further send has to be
    admitted and then refused.
    """
    dsn = migrated_db
    allocation_id = _allocate(dsn, authorized=10_000)

    # Two sends this process will never see. They are admitted and dispatched
    # through the broker, so they are real operations rather than counted rows.
    for index in (1, 2):
        prior = "preflight-prior-%d" % index
        broker.ensure_operation(
            dsn, operation_id=prior, effect=broker.MODEL_INFERENCE,
            payload={"model": ROUTE["requested_model"],
                     "messages": [{"role": "user", "content": "prior"}],
                     "max_output_tokens": 64, "deadline_ms": 10_000},
            allocation_id=allocation_id)
        broker.dispatch_operation(dsn, prior, launchers={},
                                  gateway=_RoutedAdapter(text="prior"))

    # The ceiling is 2 and the store already holds 2, so the next send is
    # over it. The guard is constructed with no `already_spent` at all, so
    # an in-process integer would read zero and would send.
    gateway = _RoutedAdapter()
    guard = _guard(dsn, allocation_id, ceiling=2, gateway=gateway)

    attempt = live._preflight_dispatch(guard, arm="P1", attempt=1, dsn=dsn,
                                       allocation_id=allocation_id)
    assert attempt["outcome"] == "pre-dispatch-refusal", attempt
    assert attempt["refusal_kind"] == "ceiling", attempt

    operation_id = attempt["operation_id"]
    assert _rows(dsn, "SELECT * FROM operations WHERE id = %s",
                 (operation_id,)) == [], (
        "a ceiling the store had already reached still admitted an operation")
    assert gateway.sent == [], (
        "the guard refused on the ceiling but the wire was touched anyway")

    # And the position it enforced is the store's, not a seed it was handed.
    assert guard.guard_status()["spent_dispatch_count"] == 2, (
        "the guard's ceiling position is still its own integer, not the "
        "store's count: %r" % guard.guard_status())
