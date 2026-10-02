"""A receipt must name whoever produced it, whatever the outcome.

N-302 is a receipt whose provenance identifies nobody. `_validate_receipt`
required `provenance` only when `outcome == "failure"`, so a `success` or
`unknown` receipt carried any string, or none, and the store could not tell an
admitted receipt from a fabricated one. The reviewer settled a reservation with
`provenance='somebody-who-never-ran-anything'` on an operation whose
`launcher_id` was `local-1`, and admission said yes.

The second half is durability. `receipts` has no provenance column and
`operations.receipt_provenance` is last-writer-wins, so N receipts admitted on
one operation overwrite each other and the trail records a string rather than an
identity.

What the store cannot do is check *who*. The obvious stronger rule - hold the
receipt's provenance to the admitted `launcher_id` with `_provenance_attested` -
was implemented and measured, and it is wrong: the broker's own receipts
(`broker-fence`, `broker`, `broker-inline`, `gateway`, `<launcher>-recovery`)
all arrive on operations whose `launcher_id` is the launcher's, and all five
N-43/N-47/N-48 controls in `tests/test_s09_controls.py` went red on it. A
`success` receipt may be written by the gateway, by the broker inline, or by a
launcher, and only the first two of those are ever named by `launcher_id`. The
store cannot ask a launcher who wrote a receipt, and N-55 already records that
a launcher id is a naming convention rather than a secret. Requiring the field
is the part the store can actually establish; the identity behind it is a
judgement this file deliberately does not pretend to settle.
"""

from __future__ import annotations

import uuid

import pytest

from settlement import broker, store
from settlement.broker import ReceiptProposal
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher


def _cmd(payload: dict, tag: str) -> Command:
    return Command(request_id=f"n302_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn: str, tag: str) -> tuple[str, str]:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "n302",
                                "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 10_000}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "n302"}, f"{tag}i"))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                         "investigation_id": f"{tag}-i"},
                                        f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", str(gen)


def _dispatched(dsn: str, operation_id: str, alloc: str, gen: str,
                attempt: str, tag: str, tmp_path) -> None:
    broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id=attempt)
    broker.dispatch_operation(dsn, operation_id,
                              launchers={"local-process": LocalLauncher(tmp_path / tag)},
                              ownership_generation=int(gen), _crash_after_send=True)


@pytest.mark.parametrize("outcome", ["success", "unknown", "failure"])
def test_a_receipt_with_no_provenance_is_refused_for_every_outcome(
        migrated_db, tmp_path, outcome):
    dsn = migrated_db
    alloc, gen = _env(dsn, "noprov")
    operation_id = "n302-noprov-op"
    _dispatched(dsn, operation_id, alloc, gen, "noprov-att", "noprov", tmp_path)

    result = store.admit_receipt(dsn, _cmd({
        "operation_id": operation_id,
        "receipt_identity": f"noprov-rc-{outcome}",
        "content": {"parse": "ok", "data": {"returncode": 0}},
        "outcome": outcome}, "noprov"))

    assert result.code == ResultCode.INVALID_INPUT
    assert "provenance" in result.detail
    assert store.operation_receipts(dsn, operation_id) == []


@pytest.mark.parametrize("outcome", ["success", "unknown"])
def test_a_blank_provenance_is_refused_where_a_failure_already_was(
        migrated_db, tmp_path, outcome):
    """A whitespace string is the shape the old failure rule already refused.

    Hoisting the rule must not weaken it for `failure`, and must apply the same
    standard to the other two outcomes.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "blank")
    operation_id = "n302-blank-op"
    _dispatched(dsn, operation_id, alloc, gen, "blank-att", "blank", tmp_path)

    result = store.admit_receipt(dsn, _cmd({
        "operation_id": operation_id,
        "receipt_identity": f"blank-rc-{outcome}",
        "content": {"parse": "ok", "data": {"returncode": 0}},
        "outcome": outcome,
        "provenance": "   "}, "blank"))

    assert result.code == ResultCode.INVALID_INPUT
    assert "provenance" in result.detail
    assert store.operation_receipts(dsn, operation_id) == []


def test_each_receipt_row_carries_its_own_provenance(migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "durable")
    operation_id = "n302-durable-op"
    _dispatched(dsn, operation_id, alloc, gen, "durable-att", "durable", tmp_path)

    first = broker.admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
        receipt_identity="durable:unknown", content={"recovered": False},
        outcome="unknown", provenance="local-1:prove_never_sent"))
    assert first.code is ResultCode.APPLIED
    second = broker.admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
        receipt_identity="durable:recovered", content={"recovered": True},
        outcome="success", provenance="local-1-recovery"))
    assert second.code is ResultCode.APPLIED

    rows = {row["receipt_identity"]: row for row in store.operation_receipts(dsn, operation_id)}
    assert rows["durable:unknown"]["provenance"] == "local-1:prove_never_sent"
    assert rows["durable:recovered"]["provenance"] == "local-1-recovery"
    assert (broker.read_operation(dsn, operation_id) or {})["receipt_provenance"] == "local-1-recovery"
