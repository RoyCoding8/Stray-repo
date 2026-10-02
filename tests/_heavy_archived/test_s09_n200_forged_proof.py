"""N-200: a never-sent proof the store cannot tell from a forged one.

``_never_sent_proof`` holds a caller-supplied proof to the operation's own
admitted launcher: the provenance must name ``operations.launcher_id``. That
was a real narrowing over N-48, which accepted any non-empty string. But
``launcher_id`` is written by the caller, readable on the operation row, and
for ``LocalLauncher`` it is the public class constant ``"local-1"``. So the
check proves only that the caller can spell a name it was handed, which is
evidence of nothing.

The consequence is concrete. Drive a sandbox so it really runs, admit an
``unknown`` receipt for the lost response, and the reservation is ``uncertain``
with 111 units still held. ``launcher.prove_never_sent`` correctly answers
False. A caller that reads the operation row can still build a
shape-valid, generation-correct, correctly-attributed proof out of the row it
just read, and the store refunds the whole exposure.

So the property under test is not "a proof is well shaped". It is: the store
must not return a refund on evidence it cannot distinguish from a forgery.
The store records no fact that a run started -- no column, no counter, no
launcher-held capability. That is the finding these tests pin, so they are
written to fail while the refund is reachable and to pass once it is not.

The two tests at the bottom are the guard rail: an honest never-sent proof,
and the two carve-outs in ``_never_sent_proof``'s docstring (a subject with no
operation behind it, and an operation admitted to no launcher), must keep
behaving exactly as documented. An over-refusing fix that strands real
recovery is not a fix.
"""

from __future__ import annotations

import sys
import time
import uuid

from settlement import broker, launcher_local, steward, store
from settlement.broker import BrokerOp
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher

SANDBOX_TIMEOUT_MS = 30_000
_ARGV_PLACEHOLDER = ["unused"]


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"n200_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn: str, tag: str, authorized: int = 10 ** 6) -> tuple[str, int]:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "n200",
                                 "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "n200"}, f"{tag}i"))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                         "investigation_id": f"{tag}-i"},
                                        f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", int(gen)


def _sandbox(dsn: str, operation_id: str, alloc: str, *, attempt: str,
             argv: list[str]) -> None:
    assert broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload=_sandbox_payload(argv),
        allocation_id=alloc, attempt_id=attempt).code == ResultCode.APPLIED


def _sandbox_payload(argv: list[str]) -> dict:
    return {"profile": launcher_local.PROFILE, "argv": argv,
            "timeout_ms": SANDBOX_TIMEOUT_MS, "cpu_seconds": 30}


def _sandbox_exposure() -> int:
    """The units a sandbox like these holds, from the schedule itself.

    Read from ``broker.exposure_schedule`` rather than written as 111, so the
    assertion tracks the real exposure instead of a number that stops
    matching when a timeout or a stop-settle term moves.
    """
    units, kind = broker.exposure_schedule(
        broker.SANDBOX_EXEC, _sandbox_payload([_ARGV_PLACEHOLDER]), 0)
    assert kind == "hard-ceiling"
    return units


def _ran_and_uncertain(dsn: str, tag: str, run_dir):
    """One real execution whose response was lost, and the exposure it left.

    The launcher dispatches for real and the sandbox really writes a file. An
    ``unknown`` receipt then marks the reservation ``uncertain`` -- the state
    the store holds specifically because it does not know what the run cost.
    That is the state a refund would be wrong in, and it is reached here
    through real code rather than a direct database write.
    """
    alloc, gen = _env(dsn, tag)
    operation_id = f"{tag}-op"
    counter = run_dir / "counter"
    argv = [sys.executable, "-c", f"open({str(counter)!r},'a').write('x')"]
    _sandbox(dsn, operation_id, alloc, attempt=f"{tag}-att", argv=argv)

    launcher = LocalLauncher(run_dir)
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": operation_id, "launcher_id": launcher.launcher_id,
        "ownership_generation": gen}, f"{tag}adv"))
    assert advanced.code == ResultCode.APPLIED
    generation = int(advanced.data["dispatch_generation"])

    launcher.dispatch(BrokerOp(
        operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload=dict(_sandbox_payload(argv), max_output_bytes=1048576,
                     memory_bytes=None),
        execution_version="", attempt_id=None, dispatch_generation=generation))

    for _ in range(500):
        if counter.exists() and counter.read_text():
            break
        time.sleep(0.02)
    assert counter.exists() and counter.read_text(), (
        "precondition: this test is worthless unless the sandbox really ran")

    store.admit_receipt(dsn, _cmd({
        "operation_id": operation_id,
        "receipt_identity": f"gw:{operation_id}:lost-response",
        "outcome": "unknown", "provenance": "gateway",
        "content": {"operation_id": operation_id,
                    "response_class": "lost-response",
                    "response_received": False, "error": "timeout"}},
        f"{tag}rcp"))

    return alloc, operation_id, generation, launcher


def _forged_from_the_row(dsn: str, operation_id: str) -> dict:
    """Build a proof using nothing a caller could not read off the store.

    Every field is drawn from the operation row or a public constant. This is
    the whole attack: no secret is stolen, because the design has none.
    """
    row = broker.read_operation(dsn, operation_id)
    return {
        "claim": "never-sent",
        "subject": operation_id,
        "provenance": f"{row['launcher_id']}:prove_never_sent",
        "dispatch_generation": int((row["payload"] or {})["_dispatch_generation"]),
    }


def test_a_sandbox_that_ran_is_not_refunded_on_a_proof_the_caller_wrote(
        migrated_db, tmp_path):
    """The refusal must be a property of the evidence, not of the spelling.

    The launcher says the work was sent. The store refunds it anyway, on a
    proof assembled entirely from values the caller can read. Units held for a
    run whose real cost nobody measured become free allocation again, so the
    budget stops bounding the work it is there to bound.

    Fails while ``steward.release_reservation`` applies a caller-written proof
    for an operation whose launcher reports a prior send.
    """
    dsn = migrated_db
    alloc, operation_id, generation, launcher = _ran_and_uncertain(
        dsn, "n200a", tmp_path / "runs")

    assert launcher.prove_never_sent(operation_id, generation) is False, (
        "precondition: the launcher must report a prior send, or there is "
        "nothing to refund in error")
    before = store.allocation_status(dsn, alloc)
    assert before["reserved"] == _sandbox_exposure(), (
        "precondition: the whole hard-ceiling exposure must still be held, "
        f"expected {_sandbox_exposure()}, got {before['reserved']}")

    result = steward.release_reservation(dsn, _cmd({
        "reservation_id": f"res-{operation_id}",
        "never_sent_proof": _forged_from_the_row(dsn, operation_id)}, "rel"))

    after = store.allocation_status(dsn, alloc)
    assert result.code != ResultCode.APPLIED, (
        "a proof the caller wrote from the operation row refunded a sandbox "
        f"that really ran; got {result.code.value}: {result.detail}")
    assert after["reserved"] == before["reserved"], (
        f"held units {before['reserved']} -> {after['reserved']}; a real "
        "execution was made free again")


def test_the_proof_cannot_be_rebuilt_from_the_public_launcher_id(
        migrated_db, tmp_path):
    """The refusal must not be a token the caller can copy from the class.

    ``LocalLauncher.launcher_id`` is a public constant, so "name the admitted
    launcher" is a spelling rule. Pin it separately from the test above: a
    fix that merely hardens the constant still fails this one.
    """
    dsn = migrated_db
    alloc, operation_id, generation, launcher = _ran_and_uncertain(
        dsn, "n200b", tmp_path / "runs")
    row = broker.read_operation(dsn, operation_id)

    assert LocalLauncher.launcher_id == "local-1", (
        "precondition: the launcher id must be the public constant this "
        "attack reads")
    assert row["launcher_id"] == "local-1", (
        "precondition: the operation must have been admitted to it")

    before = store.allocation_status(dsn, alloc)
    proof = {"claim": "never-sent", "subject": operation_id,
             "provenance": f"{LocalLauncher.launcher_id}:prove_never_sent",
             "dispatch_generation": generation}
    result = store.release_reservation(dsn, _cmd({
        "reservation_id": f"res-{operation_id}", "never_sent_proof": proof}, "rel"))

    after = store.allocation_status(dsn, alloc)
    assert result.code != ResultCode.APPLIED, (
        f"the constant {LocalLauncher.launcher_id!r} alone bought a refund; "
        f"got {result.code.value}: {result.detail}")
    assert after["reserved"] == before["reserved"]


def test_an_honest_never_sent_proof_still_releases(
        migrated_db, tmp_path):
    """The refusal must not strand work the launcher can vouch for.

    This is the only state a true never-sent proof describes: the operation
    is ``dispatching``, the launcher was asked, and it answered yes. If the
    fix over-refuses here it converts a recoverable crash into held exposure
    forever, which is a different defect and not a repair.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n200c")
    operation_id = "n200c-op"
    _sandbox(dsn, operation_id, alloc, attempt="n200c-att",
             argv=[sys.executable, "-c", "pass"])
    launcher = LocalLauncher(tmp_path / "runs-c")
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": operation_id, "launcher_id": launcher.launcher_id,
        "ownership_generation": gen}, "cadv"))
    assert advanced.code == ResultCode.APPLIED
    generation = int(advanced.data["dispatch_generation"])
    assert launcher.prove_never_sent(operation_id, generation) is True, (
        "precondition: nothing was ever sent, so the launcher must attest")

    proof = broker._structured_never_sent_proof(
        dsn, operation_id, {"local-process": launcher},
        expected_generation=generation)
    assert proof is not None and proof["provenance"] == \
        f"{launcher.launcher_id}:prove_never_sent"

    result = store.release_reservation(dsn, _cmd({
        "reservation_id": f"res-{operation_id}", "never_sent_proof": proof}, "crel"))

    assert result.code == ResultCode.APPLIED, (
        "a real never-sent proof must still release; got "
        f"{result.code.value}: {result.detail}")
    assert store.allocation_status(dsn, alloc)["reserved"] == 0


def test_a_reservation_with_no_operation_keeps_the_shape_check(
        migrated_db):
    """The ``attested_by is None`` carve-out, pinned as documented.

    A reservation reserved without an operation has no launcher that could
    have been given the work, so there is nothing to hold a proof to and the
    shape check stands alone. ``_never_sent_proof``'s docstring says so
    explicitly; this is the test that would notice it changing.
    """
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "n200d-a", "domain": "cpu",
                                     "authorized": 100}, "d1"))
    store.reserve(dsn, _cmd({"allocation_id": "n200d-a",
                             "reservation_id": "n200d-r", "amount": 30}, "d2"))
    store.settle_reservation(dsn, _cmd({"reservation_id": "n200d-r",
                                         "outcome": "unknown"}, "d3"))

    refused = store.release_reservation(dsn, _cmd({
        "reservation_id": "n200d-r"}, "d4"))
    assert refused.code == ResultCode.MISSING_EVIDENCE
    assert store.allocation_status(dsn, "n200d-a")["reserved"] == 30

    released = store.release_reservation(dsn, _cmd({
        "reservation_id": "n200d-r", "never_sent_proof": {
            "claim": "never-sent", "subject": "n200d-r",
            "provenance": "anyone-at-all:prove_never_sent"}}, "d5"))
    assert released.code == ResultCode.APPLIED, (
        "a subject with no operation has nothing to attest for it; got "
        f"{released.code.value}: {released.detail}")
    assert store.allocation_status(dsn, "n200d-a")["reserved"] == 0


def test_an_operation_admitted_to_no_launcher_fails_closed(
        migrated_db):
    """The empty-string carve-out, pinned as documented and in the other direction.

    An operation with no launcher could not have been given to anything, so no
    proof of its own can be accepted for it -- ``_provenance_attested``
    returns False for an empty ``attested_by``. Refusing strands the operation
    for an explicit reconcile, which is the safe direction.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n200e")
    operation_id = "n200e-op"
    _sandbox(dsn, operation_id, alloc, attempt="n200e-att",
             argv=[sys.executable, "-c", "pass"])
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": operation_id, "ownership_generation": gen}, "eadv"))
    assert advanced.code == ResultCode.APPLIED

    row = broker.read_operation(dsn, operation_id)
    assert row["launcher_id"] == "", (
        "precondition: the operation must be admitted to no launcher")

    result = store.release_reservation(dsn, _cmd({
        "reservation_id": f"res-{operation_id}", "never_sent_proof": {
            "claim": "never-sent", "subject": operation_id,
            "provenance": "local-1:prove_never_sent",
            "dispatch_generation": int(row["payload"]["_dispatch_generation"])}},
        "erel"))

    assert result.code == ResultCode.MISSING_EVIDENCE, (
        f"no launcher can attest for this operation; got {result.code.value}")
    assert store.allocation_status(dsn, alloc)["reserved"] > 0
