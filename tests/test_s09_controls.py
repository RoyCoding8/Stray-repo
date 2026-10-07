"""Five controls the behavioural pass found absent, written so they can fail.

A skipped or absent regression test proves nothing (WORKER-EC02-AD01-BEHAVIORAL-
COMPLETION.md:105). Each test below names the input that makes it fail, and
each was shown red by breaking the behaviour deliberately.

Two controls, 2 and 3, describe defects a sibling lane is repairing. They are
written against CURRENT behaviour on purpose. The assertion a repair will
change is marked ``REPAIR 2 CHANGES THIS`` and ``REPAIR 3 CHANGES THIS``.
"""

from __future__ import annotations

import sys

import threading
import uuid
from pathlib import Path

import pytest

from settlement import broker, store
from settlement.broker import LaunchOutcome, ReceiptProposal
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_local import LocalLauncher


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"s09ctl_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn: str, tag: str, authorized: int = 10_000) -> tuple[str, int]:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "s09ctl",
                                 "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "s09ctl"}, f"{tag}i"))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                         "investigation_id": f"{tag}-i"},
                                        f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", int(gen)


def _sandbox(dsn: str, operation_id: str, alloc: str, *,
             attempt: str, execution_version: str = "") -> CommandResult:
    return broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": [sys.executable, "-c", "pass"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id=attempt,
        execution_version=execution_version)


def _state(dsn: str, operation_id: str) -> dict:
    row = broker.read_operation(dsn, operation_id) or {}
    return {k: row.get(k) for k in ("dispatch_state", "reconcile_state", "settled")}


def _outbox_delivered(dsn: str, operation_id: str) -> bool | None:
    from psycopg.rows import dict_row
    with store.db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT delivered FROM outbox WHERE workflow_identity = %s",
                        (f"dispatch:{operation_id}",))
            row = cur.fetchone()
    return None if row is None else bool(row["delivered"])


def _fenced_unknown_plus_decided(dsn: str, tag: str, run_dir: Path) -> str:
    """Drive a real operation into the N-43 shape through the real boundary.

    No receipt is written by hand. The launcher sends, the broker is fenced by
    a store checkpoint, a stale receipt arrives, and reconciliation admits the
    launcher's own result on top. The fenced `unknown` and the decided receipt
    then coexist on one operation.
    """
    alloc, gen = _env(dsn, tag)
    operation_id = f"{tag}-op"
    _sandbox(dsn, operation_id, alloc, attempt=f"{tag}-att")
    launcher = LocalLauncher(run_dir)
    broker.dispatch_operation(dsn, operation_id,
                              launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    store.restore_fence(dsn, _cmd({"reason": "s09ctl-fence"}, f"{tag}rf"))
    store.resume_dispatch(dsn, _cmd({"reason": "s09ctl-resume"}, f"{tag}rd"))
    live = int((broker.read_operation(dsn, operation_id) or {})["payload"]["_dispatch_generation"])
    broker._finish_send(dsn, operation_id, LaunchOutcome(
        sent=True, receipt=ReceiptProposal(
            receipt_identity=f"stale-{operation_id}",
            content={"parse": "rejected", "data": {"returncode": 1}},
            outcome="failure", provenance="stale-launcher")),
        admitted_generation=live - 1)
    broker.reconcile(dsn, operation_id, {"local-process": launcher})
    return operation_id


# ---------------------------------------------------------------------------
# Control 1. Multi-receipt readback: a fenced `unknown` PLUS a decided receipt.
# ---------------------------------------------------------------------------

def test_a_fenced_unknown_and_a_decided_receipt_both_survive_on_one_operation(
        migrated_db, tmp_path):
    dsn = migrated_db
    op = _fenced_unknown_plus_decided(dsn, "c1", tmp_path / "runs")

    receipts = store.operation_receipts(dsn, op)
    by_outcome = {r["outcome"] for r in receipts}
    assert by_outcome == {"unknown", "success"}, (
        "the fence receipt and the reconciled receipt must both be readable; "
        f"got {[(r['receipt_identity'], r['outcome']) for r in receipts]}")
    fenced = [r for r in receipts if r["outcome"] == "unknown"]
    decided = [r for r in receipts if r["outcome"] in ("success", "failure")]
    assert len(fenced) == 1 and len(decided) == 1
    assert fenced[0]["content"]["fenced"] is True
    assert decided[0]["receipt_identity"].startswith("reconciled:")

    # A consumer that filters on the outcome does not double-count and does not
    # treat the fenced `unknown` as a decision. This is the read
    # experiments/coord02/controller.py:451 performs.
    hits = [r["receipt_identity"] for r in receipts if r["outcome"] == "success"]
    assert hits == [decided[0]["receipt_identity"]], (
        "one decided receipt must yield exactly one hit, not zero (unknown "
        "counted as a decision) and not two (the fence counted as a decision)")

    # The broker's own decision predicate agrees: the operation IS decided.
    assert broker._decided_receipt(dsn, op) is True

    # Nothing was diverted into receipt_conflicts, so the decided receipt is
    # not merely counted but actually retained.
    assert store.operation_receipt_conflicts(dsn, op) == []


def test_a_consumer_reading_only_the_first_receipt_reads_the_fence_not_the_decision(
        migrated_db, tmp_path):
    """The N-43 shape defeats a first-receipt read. This test REVEALS the defect.

    experiments/ad01/s09_e3_selection.py:556-558 reads `receipts[0]` and
    `receipts[0]["outcome"]`, then admits a binding only on `== "success"`.
    `operation_receipts` orders by `(created_at, receipt_identity)`, and the
    fence identity `fenced:<op>:g<n>` sorts before `reconciled:<op>`, so the
    UNKNOWN is always first. A settled, observed operation is therefore
    recorded as unadmitted.

    There is no sibling repair assigned to this site. The failing assertion is
    the LAST one, and it asserts the defect rather than the behaviour.
    """
    dsn = migrated_db
    op = _fenced_unknown_plus_decided(dsn, "c1f", tmp_path / "runs")

    assert _state(dsn, op) == {"dispatch_state": "observed",
                               "reconcile_state": "none", "settled": True}, (
        "precondition: the operation is genuinely observed and settled")

    receipts = store.operation_receipts(dsn, op)
    first_identity = receipts[0]["receipt_identity"]
    first_outcome = receipts[0]["outcome"]
    admitted = bool(first_identity) and first_outcome == "success"

    assert first_outcome == "unknown", (
        "DEFECT GUARD. This control passes only while the defect is present. "
        "If it now reads 'success', a sibling repaired the consumer and this "
        "control must be inverted, not deleted.")
    assert admitted is False, (
        "DEFECT. A settled operation is recorded as unadmitted because the "
        "consumer read the fence. Fix belongs at the consumer: select the "
        "decided receipt, do not index position 0.")


# ---------------------------------------------------------------------------
# Control 2. reset_dispatch with an unbacked never_sent_proof.
# ---------------------------------------------------------------------------

def test_b_reset_dispatch_refuses_a_proof_naming_no_real_launcher(migrated_db, tmp_path):
    """The store's never-sent proof must be attested by the admitted launcher.

    Before the repair, store.py:1813 required a proof and _never_sent_proof
    only required that `provenance` be a non-empty string. Nothing asked a
    launcher, so store.reset_dispatch accepted a proof naming a caller that
    never existed and returned a really-sent operation to `prepared`.

    Written against the pre-repair behaviour first, with the assertions the
    repair was predicted to change, then updated when the repair landed. The
    prediction was right: `result.code` became `MISSING_EVIDENCE`, naming
    the operation's own launcher.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "c2")
    op = "c2-op"
    _sandbox(dsn, op, alloc, attempt="c2-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)

    # The launcher DID send. It has a result file, a spawn record and a
    # generation file on disk, and it says so if anyone asks.
    assert launcher.prove_never_sent(op, 1) is False
    assert (run_dir / f"{op}_exec-default.result.json").exists()
    assert (run_dir / f"{op}_exec-default.spawns").read_text().strip() == "1"

    generation = int((broker.read_operation(dsn, op) or {})["payload"]["_dispatch_generation"])
    admitted_launcher = (broker.read_operation(dsn, op) or {})["launcher_id"]
    assert admitted_launcher == launcher.launcher_id

    result = store.reset_dispatch(dsn, _cmd({
        "operation_id": op,
        "expected_generation": generation,
        "never_sent_proof": {
            "claim": "never-sent",
            "subject": op,
            "provenance": "a-caller-that-never-existed-and-never-ran",
            "dispatch_generation": generation,
        }}, "c2r"))
    # store.transact converts a SettlementError into a result code, so the
    # refusal arrives as MISSING_EVIDENCE and not as a raise.
    assert result.code == ResultCode.MISSING_EVIDENCE
    assert admitted_launcher in result.detail, (
        "the refusal must name the launcher that could have attested the claim")

    # The invariant the repair did not change: the operation did not move, so
    # the work is still the launcher's to finish.
    assert _state(dsn, op)["dispatch_state"] == "dispatching"
    assert "_never_sent_proof" not in (broker.read_operation(dsn, op) or {})["payload"]


def test_b_the_broker_path_and_the_store_path_agree(migrated_db, tmp_path):
    """Both paths refuse now, and they refuse for the same reason.

    broker.redispatch_after_reset asks the launcher through
    _structured_never_sent_proof. store.reset_dispatch checks the one thing it
    can check itself, that the provenance is the admitted launcher's own name.
    Before the repair these disagreed, and the test asserted the disagreement.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "c2b")
    op = "c2b-op"
    _sandbox(dsn, op, alloc, attempt="c2b-att")
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    generation = int((broker.read_operation(dsn, op) or {})["payload"]["_dispatch_generation"])

    status = broker.redispatch_after_reset(dsn, op, {"local-process": launcher},
                                           expected_generation=generation)
    assert status.dispatch_state == "dispatching"
    assert status.next_decision == "refused-never-sent-proof", (
        "the broker path asks the launcher and the launcher denies the claim")

    direct = store.reset_dispatch(dsn, _cmd({
        "operation_id": op,
        "expected_generation": generation,
        "never_sent_proof": {
            "claim": "never-sent",
            "subject": op,
            "provenance": "a-caller-that-never-existed-and-never-ran",
            "dispatch_generation": generation,
        }}, "c2bd"))
    assert direct.code == ResultCode.MISSING_EVIDENCE
    assert _state(dsn, op)["dispatch_state"] == "dispatching"


def test_b_an_erased_run_directory_does_not_make_a_sent_operation_provable(
        migrated_db, tmp_path):
    """A send cannot be un-sent by erasing the directory that recorded it.

    This control was originally inverted. It erased the launcher's record and
    asserted the launcher would then honestly attest that nothing was ever
    sent, on the reasoning that a refusal nothing satisfies is an outage. That
    reasoning is sound and the conclusion it reached is not: erasure is a write
    the uncontained worker can already do, so "the record is gone" was never
    evidence that "the work never ran". The launcher's own claim ledger, held
    outside the run directory and written before the spawn, is what makes the
    two different. See tests/test_s09_n201_claim_ledger.py.

    The refusal is the visible bounded leak the design chose over an invisible
    breach, and the operation stays `dispatching` with its exposure held, so
    `verify_ledger` can still name it.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "c2ok")
    op = "c2ok-op"
    _sandbox(dsn, op, alloc, attempt="c2ok-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)

    st = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                   ownership_generation=gen, _crash_after_send=True)
    assert st.dispatch_state == "dispatching"
    for marker in run_dir.rglob("*"):
        if marker.is_file():
            marker.unlink()
    assert list(run_dir.rglob("*.result.json")) == [], (
        "precondition: the launcher's record of the send really is gone")

    assert launcher.prove_never_sent(op, 1) is False, (
        "erased evidence is not evidence of absence. A launcher that answers "
        "yes here lets redispatch_after_reset re-run work that really ran.")

    status = broker.redispatch_after_reset(dsn, op, {"local-process": launcher},
                                           expected_generation=1)
    assert status.next_decision == "refused-never-sent-proof", (
        "the redispatch must be refused; got "
        f"{status.dispatch_state}/{status.next_decision}")
    assert status.sent_this_call is False
    assert _state(dsn, op)["dispatch_state"] == "dispatching"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0, (
        "the strand must retain the exposure, or it is a forged refund")


def test_b_a_dispatch_that_never_reached_the_spawn_is_still_reclaimable(
        migrated_db, tmp_path, monkeypatch):
    """The half the erased-directory control used to stand in for.

    The old control asserted an honest proof was accepted, which is a real
    requirement, but it built the state by erasing evidence rather than by
    producing a dispatch that never sent. This builds it honestly: a real
    dispatch, parked inside `LocalLauncher._claim`, which is the one window
    where the work is admitted, nothing has been spawned, and no claim exists.

    If the claim ledger were written too eagerly or consulted too broadly,
    this control fails and the crash path is dead. A repair that cannot
    distinguish "the evidence was deleted" from "nothing was sent" has traded
    a double execution for a permanent strand.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "c2ok2")
    op = "c2ok2-op"
    _sandbox(dsn, op, alloc, attempt="c2ok2-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    launchers = {"local-process": launcher, "local": launcher}
    real_claim, entered, release, calls = (
        LocalLauncher._claim, threading.Event(), threading.Event(), [])

    def gated(self, path):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=30)
        return real_claim(self, path)

    monkeypatch.setattr(LocalLauncher, "_claim", gated)
    holder: dict = {}
    worker = threading.Thread(target=lambda: holder.setdefault(
        "status", broker.dispatch_operation(dsn, op, launchers=launchers)))
    worker.start()
    try:
        assert entered.wait(timeout=30), "the dispatch never reached _claim"
        assert launcher.prove_never_sent(op, 1) is True, (
            "a dispatch that never reached the spawn must stay reclaimable")

        status = broker.redispatch_after_reset(dsn, op, launchers,
                                               expected_generation=1)
        assert status.next_decision != "refused-never-sent-proof", (
            "an honest proof must be accepted; otherwise the reset path is dead")
        assert status.sent_this_call is True
        assert status.dispatch_state == "observed", (
            "an accepted proof must actually restore the operation to work")
        assert [r["outcome"] for r in store.operation_receipts(dsn, op)] == ["success"]
    finally:
        release.set()
        worker.join(timeout=60)
    assert store.allocation_status(dsn, alloc)["reserved"] == 0


# ---------------------------------------------------------------------------
# Control 3. dispatch_pending stranding.
#
# broker.py:1094 hardcodes repair=False. The prepared scan only reaches an
# operation in `prepared`, the outbox pass only reaches one with an UNDELIVERED
# dispatch:<op> intent, and the repair pass is the only code that walks
# restart_reconciliation's unfinished_operations. A racing thread that records
# the delivery (broker.py:519 `_deliver` on the prior-send branch) and then
# dies before reconciling leaves the operation with nothing left to find it.
# ---------------------------------------------------------------------------

def test_c_delivered_outbox_strands_the_operation_for_every_dispatch_pending_pass(
        migrated_db, tmp_path):
    """The stranding, measured. Four passes, an empty outbox, zero progress."""
    dsn = migrated_db
    alloc, gen = _env(dsn, "c3")
    op = "c3-op"
    _sandbox(dsn, op, alloc, attempt="c3-att")
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)

    # A racing thread records the delivery and then dies before reconciling.
    # Both halves are reachable in the shipped code: `_deliver` is called on the
    # prior-send branch of _send_sandbox (broker.py:519) and on _park_decided
    # (broker.py:388), and neither is in the same transaction as the state
    # change that follows it.
    assert broker._deliver(dsn, f"dispatch:{op}") is True
    assert _outbox_delivered(dsn, op) is True
    assert store.scan_outbox(dsn) == []
    assert _state(dsn, op) == {"dispatch_state": "dispatching",
                               "reconcile_state": "none", "settled": False}

    first = broker.dispatch_pending(dsn, {"local-process": launcher},
                                    ownership_generation=gen)
    # Written against the pre-repair broker first. These are the assertions the
    # repair was predicted to change, and the prediction was right.
    #   predicted: repaired == [op], next_decision names a repair,
    #              dispatch_state becomes observed
    #   observed:  repaired and dispatch_state as predicted. The label is
    #              "work-done", not "repair-done": broker.py:1224 sets
    #              repair-done only when nothing else fired, and line 1226
    #              overwrites it. The label is cosmetic. The repair is the
    #              recovered state.
    assert first.repaired == [op]
    assert first.next_decision in ("repair-done", "work-done")
    assert _state(dsn, op)["dispatch_state"] == "observed"
    # The repair recovers the observation, it does not re-run the work.
    assert (tmp_path / "runs" / f"{op}_exec-default.spawns").read_text().strip() == "1"
    assert _outbox_delivered(dsn, op) is True
    assert store.restart_reconciliation(dsn)["unfinished_operations"] == []

    # The driver is total, not merely eventually right: a second pass finds
    # nothing to do, and the state does not move again.
    for attempt in range(3):
        again = broker.dispatch_pending(dsn, {"local-process": launcher},
                                        ownership_generation=gen)
        assert again.repaired == [], f"pass {attempt + 2} invented work"
        assert again.dispatched == []
        assert again.next_decision == "idle"
        assert _state(dsn, op)["dispatch_state"] == "observed"
        assert (tmp_path / "runs" / f"{op}_exec-default.spawns").read_text().strip() == "1"

    # The decided receipt is the launcher's own recorded result, recovered.
    receipts = store.operation_receipts(dsn, op)
    assert [r["outcome"] for r in receipts] == ["success"]
    assert _state(dsn, op) == {"dispatch_state": "observed",
                               "reconcile_state": "none", "settled": True}
    # The exposure is released, not held.
    assert store.allocation_status(dsn, "c3-a")["reserved"] == 0


def test_c_the_stranding_reproduction_is_now_unreachable(migrated_db, tmp_path):
    """The pre-repair state, asserted to have been driven out of existence.

    Written against the repaired broker. The block below is the exact state the
    old control produced: `dispatching` with a delivered intent. It is
    reconstructed here, not merely assumed, so the control still has teeth if a
    later change reintroduces the hole.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "c3s")
    op = "c3s-op"
    _sandbox(dsn, op, alloc, attempt="c3s-att")
    launcher = LocalLauncher(tmp_path / "runs")
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    assert broker._deliver(dsn, f"dispatch:{op}") is True
    assert _state(dsn, op)["dispatch_state"] == "dispatching"
    assert store.scan_outbox(dsn) == []

    report = broker.dispatch_pending(dsn, {"local-process": launcher},
                                     ownership_generation=gen)
    assert report.repaired == [op]
    assert _state(dsn, op)["dispatch_state"] == "observed"
    assert (tmp_path / "runs" / f"{op}_exec-default.spawns").read_text().strip() == "1"


def test_c_an_unbacked_reset_is_now_refused_and_the_stall_is_unreachable(
        migrated_db, tmp_path):
    """Controls 2 and 3 composed. The stall is now closed at its source.

    Written against the repaired store. Under the old code this test asserted
    the whole path was reachable; the repair refuses the unbacked proof, so the
    operation never returns to `prepared` and the stranding state cannot be
    built from a reset at all.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "c3u")
    op = "c3u-op"
    _sandbox(dsn, op, alloc, attempt="c3u-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    generation = int((broker.read_operation(dsn, op) or {})["payload"]["_dispatch_generation"])

    refused = store.reset_dispatch(dsn, _cmd({
        "operation_id": op,
        "expected_generation": generation,
        "never_sent_proof": {"claim": "never-sent", "subject": op,
                             "provenance": "never-existed",
                             "dispatch_generation": generation}}, "c3u"))
    assert refused.code == ResultCode.MISSING_EVIDENCE

    # The operation was not moved, so the launcher still owns the work and the
    # driver still reaches it.
    assert _state(dsn, op)["dispatch_state"] == "dispatching"
    report = broker.dispatch_pending(dsn, {"local-process": launcher},
                                     ownership_generation=gen)
    assert (run_dir / f"{op}_exec-default.spawns").read_text().strip() == "1", (
        "the launcher must not re-run work it already did")
    assert report.repaired == [op]
    assert _state(dsn, op)["settled"] is True


# ---------------------------------------------------------------------------
# Control 4. Traversal characters in execution_version.
#
# The store accepts execution_version verbatim and writes it to the operations
# column. Nothing at the accepting boundary validates it. The safety lives in
# `native_id`, whose `_sanitize` maps every character outside [A-Za-z0-9_.-]
# to "_", in both launcher_local.py:44 and launcher_runsc.py:37. The result is
# containment by accident of a character class, not by containment logic: "."
# is explicitly ALLOWED by the filter, so the whole defence rests on ".." being
# destroyed by the "/" -> "_" substitution rather than on a path check.
# ---------------------------------------------------------------------------

_TRAVERSAL_VERSIONS = [
    "../../etc/passwd",
    "/etc/shadow",
    "..",
    "a/../../../tmp/evil",
    "x/..",
]


@pytest.mark.parametrize("execution_version", _TRAVERSAL_VERSIONS)
def test_d_a_traversal_execution_version_is_refused_at_the_boundary(
        migrated_db, tmp_path, execution_version):
    """The accepting boundary now refuses, so the consumer is no longer the defence.

    This control was originally written the other way round: it asserted that a
    traversing `execution_version` WAS stored verbatim and that containment came
    from `launcher_local.native_id` mapping "/" to "_". That was true when the
    store wrote the column without validation, and it is the defect finding N-49
    named - a boundary that accepts what it does not contain, with the safety
    property living in a consumer that can change. N-49 added
    `_require_execution_version`, so a traversing value never reaches the column
    at all and the downstream filter is no longer load-bearing.

    **The control was inverted rather than relaxed**, and it is strictly
    stronger than before: it now asserts the refusal happens AT the boundary AND
    that no operation row was written carrying the bad value. The old version
    could not have caught a boundary that stored the value and relied on a
    consumer, because that is exactly what it asserted.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "c4")
    op = "c4-op"
    prepared = _sandbox(dsn, op, alloc, attempt="c4-att",
                        execution_version=execution_version)

    assert prepared.code != ResultCode.APPLIED, (
        "the store accepted a traversing execution_version; the boundary is "
        "the defence and it must refuse before anything is written")
    row = broker.read_operation(dsn, op) or {}
    assert not row, (
        "an operation row exists after a refused preparation: %r" % (row,))

    # And the value is refused by the validating rule directly, so the refusal
    # is the boundary's own rather than an artefact of the surrounding command.
    with pytest.raises(SettlementError):
        store._require_execution_version(execution_version)


@pytest.mark.parametrize("execution_version", ["run/v1", "exec-v1", "v1"])
def test_d_a_real_execution_version_is_accepted_and_still_contained_downstream(
        migrated_db, tmp_path, execution_version):
    """The accepting case keeps its end-to-end containment check.

    Split out from the traversal control so the consumer guarantee is still
    tested - on the values production actually passes - rather than being lost
    when the traversal case was inverted. "run/v1" carries a separator, so this
    is the case a narrower character class would have broken.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "c4")
    op = "c4-op"
    prepared = _sandbox(dsn, op, alloc, attempt="c4-att",
                        execution_version=execution_version)

    assert prepared.code == ResultCode.APPLIED
    row = broker.read_operation(dsn, op) or {}
    assert row["execution_version"] == execution_version, (
        "the store is the accepting boundary and it must store what it was "
        "given, unchanged: a rule that trims or normalises stores something the "
        "caller never sent")

    # The safety lives in a consumer, not at the boundary. What that consumer
    # actually guarantees is ONE PATH SEGMENT: "/" is gone, so the sanitised
    # string can never be a multi-component path, however many dots it holds.
    launcher = LocalLauncher(tmp_path / "runs")
    safe = launcher.native_id(op, row["execution_version"])
    assert "/" not in safe
    assert Path(safe).name == safe
    assert launcher.native_id(op, row["execution_version"]) == safe
    for key, path in launcher._paths(op, row["execution_version"]).items():
        assert Path(path).resolve().is_relative_to((tmp_path / "runs").resolve()), (
            f"{key} escaped the run directory: {path}")

    # And the run completes inside the run directory.
    status = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                       ownership_generation=gen)
    assert status.dispatch_state == "observed"
    written = {p.relative_to(tmp_path / "runs").parts[0]
               for p in (tmp_path / "runs").rglob("*")}
    assert all("/" not in name for name in written), written
    for name in written:
        assert (tmp_path / "runs" / name).resolve().is_relative_to(
            (tmp_path / "runs").resolve()), name


def test_d_containment_rests_on_the_separator_and_not_on_a_path_check():
    """The filter permits '.', so the dots survive. The separator is what holds.

    This is the fragility, stated as an executable property. It needs no
    database. It is not a defect: containment does hold, and the test above
    proves it end to end. What the test records is WHERE the property lives.
    A sanitizer that allowed "/" as a literal character would defeat
    containment, and nothing at the accepting boundary would notice.

    It also fails if someone tightens the filter to reject dots, which would be
    a better rule. If that lands, invert this test rather than delete it.
    """
    from settlement.launcher_local import _sanitize

    assert _sanitize("..") == "..", (
        "the filter permits '.', so bare traversal dots survive it. Containment "
        "holds only because the path separator is replaced first.")
    assert _sanitize("a/../b") == "a_.._b", (
        "the separator is what is destroyed, not the dots")


def test_d_the_runsc_launcher_applies_the_same_filter_so_both_paths_are_covered(
        tmp_path, monkeypatch):
    """The filter is duplicated in both launchers and neither is a boundary check."""
    from settlement import launcher_runsc

    monkeypatch.setattr(launcher_runsc, "probe_gvisor",
                        lambda: type("P", (), {"available": False, "reason": "absent",
                                               "detail": {"docker": "docker"}})())
    launcher = launcher_runsc.RunscLauncher(
        image_digest="sha256:" + "0" * 64, run_dir=tmp_path / "runsc")
    for version in _TRAVERSAL_VERSIONS:
        safe = launcher.native_id("c4-op", version)
        assert "/" not in safe
        assert Path(safe).name == safe
        for key, path in launcher._paths("c4-op", version).items():
            assert Path(path).resolve().is_relative_to((tmp_path / "runsc").resolve()), (
                f"runsc {key} escaped for {version!r}: {path}")


# ---------------------------------------------------------------------------
# Control 5. The refusing path, reachable from real execution.
#
# Every refusal below is produced by driving broker.dispatch_operation or
# broker.admit_launcher_receipt against a real store. None of them calls a
# validator directly.
# ---------------------------------------------------------------------------

def test_e_a_stale_ownership_generation_refuses_dispatch_without_sending(
        migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "c5")
    op = "c5-op"
    _sandbox(dsn, op, alloc, attempt="c5-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)

    # A real fence bumps the attempt's ownership generation.
    store.restore_fence(dsn, _cmd({"reason": "c5-fence"}, "c5rf"))
    store.resume_dispatch(dsn, _cmd({"reason": "c5-resume"}, "c5rd"))

    status = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                       ownership_generation=gen)
    assert status.next_decision == "stale-ownership"
    assert status.dispatch_state == "prepared"
    assert status.sent_this_call is False
    assert store.operation_receipts(dsn, op) == []
    # Nothing ran. The refusal is containment, not a silent resend.
    assert not run_dir.exists() or list(run_dir.glob("*")) == []

    # The passing driver honours the same refusal.
    report = broker.dispatch_pending(dsn, {"local-process": launcher},
                                     ownership_generation=gen)
    assert report.dispatched == []
    assert _state(dsn, op)["dispatch_state"] == "prepared"

    # And a current generation is admitted, so the refusal was about the
    # generation and not about the operation.
    from psycopg.rows import dict_row
    with store.db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT ownership_generation FROM attempts WHERE id = %s",
                        ("c5-att",))
            current = int(cur.fetchone()["ownership_generation"])
    assert current != gen
    admitted = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                         ownership_generation=current)
    assert admitted.dispatch_state == "observed"
    assert admitted.next_decision == "terminal"


def test_e_a_dispatch_pause_refuses_dispatch_from_the_real_boundary(
        migrated_db, tmp_path):
    dsn = migrated_db
    alloc, gen = _env(dsn, "c5p")
    op = "c5p-op"
    _sandbox(dsn, op, alloc, attempt="c5p-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)

    store.checkpoint_barrier(dsn, _cmd({}, "c5pcb"))
    status = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                       ownership_generation=gen)
    assert status.next_decision == "refused-invalid_input"
    assert status.dispatch_state == "prepared"
    assert store.operation_receipts(dsn, op) == []
    assert not run_dir.exists() or list(run_dir.glob("*")) == []

    store.resume_dispatch(dsn, _cmd({"reason": "operator"}, "c5prd"))
    admitted = broker.dispatch_operation(dsn, op, launchers={"local-process": launcher},
                                         ownership_generation=gen)
    assert admitted.dispatch_state == "observed"


def test_e_a_receipt_naming_another_operation_is_refused_and_leaves_no_receipt(
        migrated_db):
    dsn = migrated_db
    alloc, gen = _env(dsn, "c5r")
    _sandbox(dsn, "c5r-op", alloc, attempt="c5r-att")
    _sandbox(dsn, "c5r-other", alloc, attempt="c5r-att")

    result = broker.admit_launcher_receipt(dsn, "c5r-op", ReceiptProposal(
        receipt_identity="c5r-crossed",
        content={"operation_id": "c5r-other", "parse": "typed-json",
                 "data": {"returncode": 0}},
        outcome="success", provenance="misrouted-launcher"))
    assert result.code == ResultCode.INVALID_INPUT
    assert "does not match" in result.detail

    # The refusal is total: neither operation carries the receipt, and neither
    # is marked as conflicted. A refused receipt must not leave a trace that a
    # later reader mistakes for an observation.
    assert store.operation_receipts(dsn, "c5r-op") == []
    assert store.operation_receipts(dsn, "c5r-other") == []
    assert store.operation_receipt_conflicts(dsn, "c5r-op") == []
    assert store.operation_receipt_conflicts(dsn, "c5r-other") == []
    for oid in ("c5r-op", "c5r-other"):
        assert _state(dsn, oid) == {"dispatch_state": "prepared",
                                    "reconcile_state": "none", "settled": False}


def test_e_a_receipt_for_an_operation_that_was_never_dispatched_is_refused(
        migrated_db):
    dsn = migrated_db
    alloc, gen = _env(dsn, "c5n")
    op = "c5n-op"
    _sandbox(dsn, op, alloc, attempt="c5n-att")
    assert (broker.read_operation(dsn, op) or {})["payload"].get(
        "_dispatch_generation") is None

    result = broker.admit_launcher_receipt(dsn, op, ReceiptProposal(
        receipt_identity="c5n-phantom",
        content={"parse": "typed-json", "data": {"returncode": 0}},
        outcome="success", provenance="nowhere"))
    assert result.code == ResultCode.INVALID_INPUT
    assert "never dispatched" in result.detail
    assert store.operation_receipts(dsn, op) == []
    assert _state(dsn, op)["dispatch_state"] == "prepared"
