"""N-201: a claim the worker cannot erase, held outside the run directory.

``LocalLauncher.prove_never_sent`` answers "was this work ever sent?" and,
before this repair, it answered from ``run_dir`` alone. Every marker
``dispatch`` writes lives in that one directory, so deleting it converted
"cannot prove" into "was never sent", and ``broker.redispatch_after_reset``
then re-ran a side effect that really ran. ``114ac3e`` closed the other half,
the ``is_live`` read from the same doomed directory, but the directory is the
thing that is erased.

The fix is a launcher-held claim ledger written before ``subprocess.Popen``
and consulted by ``prove_never_sent``. A claim present in it means the work was
dispatched, so the proof is refused even against an empty run directory.

On location, stated plainly: **nothing in this design is unreachable by the
worker.** Production builds the run directory at
``experiments/ad01/method_exec.py:498`` and ``:769`` as
``LocalLauncher(work / "launcher")``, where ``work`` is the operation work
tree. The worker is spawned with ``cwd`` at or under ``work``, shares the
controller's uid, and every outcome this launcher produces is
``containment=False`` — measured on this box, ``os.access`` on both ``work``
and the run directory returns true for read, write and execute. A sibling of
``run_dir`` is inside ``work`` and so is reachable; ``run_dir`` itself is
reachable; the study's scratch root is reachable; ``/tmp`` is reachable.

So the ledger is not placed where the worker cannot reach it, because there is
nowhere the worker cannot reach. It is placed where the worker's own code has
no path to it, and where its deletion is not something a dispatch does. Two
properties are doing the work, and only the second is a security property:

1. **Durability across evidence deletion.** The ledger is keyed to the
   operation, not to the run directory, so erasing the run directory erases
   the launcher's working notes and not its record of having claimed.
2. **Cost of forgery.** A claim is refused, and the refusal is
   ``unresolved-liability`` with the exposure retained and named under
   ``stranded``. A worker that reaches the ledger and appends a claim for an
   operation it never ran strands that operation permanently. That is a
   denial, not a theft, and the system already chose visible leaks over
   invisible ones at ``broker.reconcile`` (``src/settlement/broker.py:1077``).

The honest statement, which the tests below record: this raises the cost of a
forged refund from "delete a directory" to "append a line to a file the worker
was never told about", and it does not make the refund unforgeable. Only a
capability the worker cannot hold, in a store that verifies it, does that, and
the store half is N-200 and outside this file.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from settlement import broker, store
from settlement.broker import BrokerOp
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"n201_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn: str, tag: str, authorized: int = 10_000) -> tuple[str, int]:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "n201",
                                 "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "n201"}, f"{tag}i"))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                         "investigation_id": f"{tag}-i"},
                                        f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", int(gen)


def _sandbox(dsn: str, operation_id: str, alloc: str, *, attempt: str,
             execution_version: str = "",
             argv: list[str] | None = None) -> object:
    return broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process",
                 "argv": argv or ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id=attempt,
        execution_version=execution_version)


def _op(operation_id: str, generation: int) -> BrokerOp:
    return BrokerOp(operation_id=operation_id, effect=broker.SANDBOX_EXEC,
                    payload={"profile": "local-process", "argv": [sys.executable, "-c", "pass"],
                             "timeout_ms": 10_000, "max_output_bytes": 1024},
                    execution_version="exec-default",
                    dispatch_generation=generation)


# ---------------------------------------------------------------------------
# The defect. A claim survives the erasure of the run directory.
# ---------------------------------------------------------------------------

def test_erasing_the_evidence_does_not_turn_a_send_into_a_never_sent(
        migrated_db, tmp_path):
    """The bug, on the real driver, end to end through the store.

    Every step is the shipped one: the launcher sends, the broker crashes after
    the send, the run directory's evidence is erased the way an uncontained
    worker can erase it, and ``redispatch_after_reset`` is asked to re-run the
    work. Before the repair the launcher attested and the operation's real
    outcome was discarded for a run that really happened.

    ``114ac3e`` closed the *directory* case: an absent ``run_dir`` is refused
    outright. The hole is the directory surviving with its contents gone, which
    is what a worker that erases files rather than the directory achieves, and
    what any caller recreating the run directory between the crash and the
    retry achieves. Both are constructed below.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n201a")
    operation_id = "n201a-op"
    _sandbox(dsn, operation_id, alloc, attempt="n201a-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)

    broker.dispatch_operation(dsn, operation_id, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    generation = int((broker.read_operation(dsn, operation_id) or {})["payload"]
                     ["_dispatch_generation"])
    assert (run_dir / f"{operation_id}_exec-default.result.json").exists(), (
        "precondition: the work really ran, or this test proves nothing")

    for marker in run_dir.rglob("*"):
        if marker.is_file():
            marker.unlink()
    assert list(run_dir.rglob("*.json")) == [] and \
        list(run_dir.rglob("*.pid")) == [] and \
        list(run_dir.rglob("*.spawns")) == [] and \
        list(run_dir.rglob("*.gen")) == [], (
        "precondition: every marker is gone, only the directory remains")

    assert launcher.prove_never_sent(operation_id, generation) is False, (
        "a send that happened cannot be un-sent by deleting its evidence")

    status = broker.redispatch_after_reset(dsn, operation_id,
                                           {"local-process": launcher},
                                           expected_generation=generation)
    assert status.next_decision == "refused-never-sent-proof", (
        "the redispatch must be refused; got "
        f"{status.dispatch_state}/{status.next_decision}")
    assert status.sent_this_call is False
    assert not list(run_dir.glob("*.result.json")), (
        "the operation's real outcome was overwritten by a second run")
    assert (broker.read_operation(dsn, operation_id) or {})["dispatch_state"] \
        == "dispatching"


def test_the_recreated_run_directory_is_the_shape_that_broke_it(tmp_path):
    """The exact precondition, isolated from the store.

    ``114ac3e``'s ``is_dir`` guard refuses an absent directory, so the deletion
    case is already closed. Deleting the *contents* and leaving the directory
    is not, and the difference is one line of cleanup code.
    """
    launcher = LocalLauncher(tmp_path / "runs")
    launcher.dispatch(_op("hole-op", 1))
    assert launcher.prove_never_sent("hole-op", 1) is False

    for marker in (tmp_path / "runs").rglob("*"):
        if marker.is_file():
            marker.unlink()
    assert launcher.prove_never_sent("hole-op", 1) is False, (
        "an emptied run directory is not evidence of absence")

    shutil.rmtree(tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    assert launcher.prove_never_sent("hole-op", 1) is False


def test_the_refusal_is_a_visible_bounded_leak_not_an_invisible_one(
        migrated_db, tmp_path):
    """Fail-closed strands the operation. That must be visible and retained.

    This is the cost the design accepts, asserted so a later change cannot
    quietly convert the strand into a silent drop: the exposure is still held
    and the operation is still the driver's to find.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n201b")
    operation_id = "n201b-op"
    _sandbox(dsn, operation_id, alloc, attempt="n201b-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    broker.dispatch_operation(dsn, operation_id, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    generation = int((broker.read_operation(dsn, operation_id) or {})["payload"]
                     ["_dispatch_generation"])
    for marker in run_dir.rglob("*"):
        if marker.is_file():
            marker.unlink()

    status = broker.redispatch_after_reset(dsn, operation_id,
                                           {"local-process": launcher},
                                           expected_generation=generation)
    assert status.next_decision == "refused-never-sent-proof"

    report = broker.reconcile(dsn, operation_id, {"local-process": launcher})
    assert report.decision == "unresolved-liability", (
        f"the strand must be reported, not dropped; got {report.decision}")
    assert store.allocation_status(dsn, alloc)["reserved"] > 0, (
        "held exposure is what makes the leak visible; a released reservation "
        "here would be a forged refund of work that really ran")


# ---------------------------------------------------------------------------
# The ledger itself.
# ---------------------------------------------------------------------------

def test_a_claim_is_recorded_before_the_worker_is_spawned(tmp_path, monkeypatch):
    """The claim must precede ``Popen``, or the crash window is still open.

    The window is checked by parking the launcher inside ``Popen`` and reading
    the ledger from another thread: at that instant the worker exists and the
    claim must already be on disk.
    """
    run_dir = tmp_path / "runs"
    ledger = tmp_path / "state" / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))
    launcher = LocalLauncher(run_dir)
    reached = threading.Event()
    release = threading.Event()

    def parked(*_args, **_kwargs):
        reached.set()
        assert release.wait(timeout=30)
        raise OSError("parked before spawn")

    monkeypatch.setattr(subprocess, "Popen", parked)
    holder: dict = {}
    worker = threading.Thread(
        target=lambda: holder.setdefault("out", launcher.dispatch(_op("claim-op", 4))))
    worker.start()
    try:
        assert reached.wait(timeout=30), "the launcher never reached Popen"
        assert launcher.claimed("claim-op", 4) is True, (
            "the claim must be durable before the spawn, not after it")
    finally:
        release.set()
        worker.join(timeout=30)

    assert holder["out"].sent is False
    assert "parked before spawn" in holder["out"].refused_reason
    assert launcher.claimed("claim-op", 4) is False
    assert launcher.prove_never_sent("claim-op", 4) is True
    assert not (run_dir / "claim-op_exec-default.spawns").exists()


def test_a_claim_does_not_answer_for_another_generation_or_operation(tmp_path,
                                                                     monkeypatch):
    """The ledger is bound to the operation and its generation, not to a name.

    The capability in ``mint_dispatch_capability`` is bound the same way. A
    ledger keyed only by operation id would let generation 1's claim silence
    generation 2, and would leak one operation's history into another's.
    """
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(tmp_path / "claims.jsonl"))
    launcher = LocalLauncher(tmp_path / "runs")
    launcher.dispatch(_op("bound-op", 1))
    launcher.dispatch(_op("other-op", 9))

    assert launcher.claimed("bound-op", 1) is True
    assert launcher.claimed("bound-op", 2) is False, (
        "a claim for generation 1 must not answer for generation 2")
    assert launcher.claimed("bound-op", 0) is False
    assert launcher.claimed("other-op", 9) is True
    assert launcher.claimed("other-op", 1) is False, (
        "another operation's generation must not answer for this one")
    assert launcher.claimed("never-dispatched", 1) is False


def test_the_ledger_is_outside_the_run_directory(tmp_path, monkeypatch):
    """Erasing the evidence directory must not reach the ledger.

    A ledger under ``run_dir`` would be erased by exactly the operation it
    exists to survive.
    """
    ledger = tmp_path / "state" / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    launcher.dispatch(_op("outside-op", 1))

    assert ledger.is_file(), "the claim ledger must exist after a send"
    assert not ledger.is_relative_to(run_dir), (
        "a ledger inside the run directory dies with the evidence it is meant "
        "to outlive")
    entries = [json.loads(line) for line in
               ledger.read_text().splitlines() if line.strip()]
    assert [e["operation_id"] for e in entries] == ["outside-op"]
    assert [e["dispatch_generation"] for e in entries] == [1]
    assert entries[0]["launcher_id"] == LocalLauncher.launcher_id

    shutil.rmtree(run_dir)
    assert launcher.claimed("outside-op", 1) is True
    assert launcher.prove_never_sent("outside-op", 1) is False


def test_the_ledger_is_appended_and_never_pruned(tmp_path, monkeypatch):
    """Re-dispatching one operation grows the ledger; it never shrinks.

    A prune step is where a claim gets lost, so the property is asserted
    directly: three sends under one operation leave three claims. Generation 1
    is cleared from disk by ``dispatch``, which is the only per-run state a
    second dispatch can legitimately clear.
    """
    ledger = tmp_path / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))
    launcher = LocalLauncher(tmp_path / "runs")
    assert launcher.dispatch(_op("grown-op", 1)).sent is True
    (tmp_path / "runs" / "grown-op_exec-default.result.json").unlink()
    assert launcher.dispatch(_op("grown-op", 2)).sent is True
    (tmp_path / "runs" / "grown-op_exec-default.result.json").unlink()
    assert launcher.dispatch(_op("grown-op", 3)).sent is True

    entries = [json.loads(line) for line in
               ledger.read_text().splitlines() if line.strip()]
    assert [e["dispatch_generation"] for e in entries] == [1, 2, 3]


def test_an_unreadable_ledger_refuses_the_proof(tmp_path, monkeypatch):
    """A launcher that cannot read its own ledger must not say "never sent".

    The rule is the one ``RunscLauncher`` already follows at
    ``launcher_runsc.py:271-284``: an error in the live-process check yields
    ``None``, the predicate is not True, and the proof is refused. Silence
    from the ledger is not evidence of absence, so ``claimed`` is three-valued
    and only a definite False lets a proof through.
    """
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(tmp_path / "claims.jsonl"))
    launcher = LocalLauncher(tmp_path / "runs")
    assert launcher.claimed("noread-op", 1) is False

    monkeypatch.setattr(LocalLauncher, "_read_claims",
                        lambda self: (_ for _ in ()).throw(OSError("unreadable")))
    assert launcher.claimed("noread-op", 1) is None, (
        "an unreadable ledger is unknown, not absent")
    assert launcher.prove_never_sent("noread-op", 1) is False
    assert launcher.attest_never_sent("noread-op", 1) is None


def test_an_unwritable_ledger_refuses_to_spawn_and_leaves_no_claim(
        tmp_path, monkeypatch):
    """The claim write gates the spawn, and a failure there is recoverable.

    If the claim cannot be made durable, the launcher must not send, because a
    send it cannot record is a send it can never prove it did not make. The
    refusal restores the pre-dispatch marker state, so the operation stays
    reclaimable instead of stranding on markers for work that never ran.
    """
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(tmp_path / "claims.jsonl"))
    launcher = LocalLauncher(tmp_path / "runs")
    monkeypatch.setattr(LocalLauncher, "_append_claim",
                        lambda self, **kw: False)

    out = launcher.dispatch(_op("unwritable-op", 1))
    assert out.sent is False
    assert out.refused_reason == "claim-not-durable"
    assert launcher.claimed("unwritable-op", 1) is False
    assert launcher.prove_never_sent("unwritable-op", 1) is True, (
        "nothing was sent, so the proof must survive a failed claim write")
    assert list((tmp_path / "runs").rglob("*.pid")) == [], (
        "the pid marker this dispatch wrote must be rolled back, or a launch "
        "that never ran leaves evidence of a send")
    assert list((tmp_path / "runs").rglob("*.spawns")) == []
    assert list((tmp_path / "runs").rglob("*.gen")) == []
    assert not (tmp_path / "runs" / "unwritable-op_exec-default.pid").exists()


def test_a_launcher_reads_claims_written_by_another_instance(tmp_path, monkeypatch):
    """The ledger outlives the launcher object, which is the point of holding it.

    A crash restart constructs a new ``LocalLauncher`` over the same run
    directory. It must still know the old one claimed.
    """
    ledger = tmp_path / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))
    run_dir = tmp_path / "runs"
    first = LocalLauncher(run_dir)
    first.dispatch(_op("restart-op", 2))
    shutil.rmtree(run_dir)

    second = LocalLauncher(run_dir)
    assert second.claimed("restart-op", 2) is True
    assert second.prove_never_sent("restart-op", 2) is False


# ---------------------------------------------------------------------------
# The positive path. A dispatch that never reached Popen must still be
# reclaimable, or the crash path is dead and this repair trades one bug for
# another.
# ---------------------------------------------------------------------------

def test_a_dispatch_that_never_reached_spawn_is_still_reclaimable(
        migrated_db, tmp_path, monkeypatch):
    """The honest proof survives the repair.

    The worker is parked inside ``_claim``, which is the one window where the
    work is admitted, nothing has been sent, and no claim exists. This is the
    state ``redispatch_after_reset`` exists for. A ledger that is written too
    eagerly, or consulted too broadly, breaks it, and the strand above becomes
    permanent for every crash.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n201c")
    operation_id = "n201c-op"
    _sandbox(dsn, operation_id, alloc, attempt="n201c-att")
    launcher = LocalLauncher(tmp_path / "runs")
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
        "status", broker.dispatch_operation(dsn, operation_id, launchers=launchers)))
    worker.start()
    try:
        assert entered.wait(timeout=30), "the worker never reached _claim"
        assert launcher.claimed(operation_id, 1) is False, (
            "precondition: nothing was claimed, or this test proves nothing")
        assert launcher.prove_never_sent(operation_id, 1) is True, (
            "a dispatch that never reached the spawn must stay reclaimable")

        status = broker.redispatch_after_reset(dsn, operation_id, launchers,
                                               expected_generation=1)
        assert status.sent_this_call is True, (
            "the reset path is dead: an honest proof was refused")
        assert status.dispatch_state == "observed"
        assert [r["outcome"] for r in
                store.operation_receipts(dsn, operation_id)] == ["success"]
    finally:
        release.set()
        worker.join(timeout=60)
    assert store.allocation_status(dsn, alloc)["reserved"] == 0


def test_a_refused_claim_leaves_an_operation_stranded_visibly(
        migrated_db, tmp_path):
    """The strand is a bounded leak, not a silent drop and not an outage.

    With the receipt erased there is nothing left to settle against, so the
    correct terminal answer is ``unresolved-liability`` with the exposure
    retained. What is asserted is that the operation is still *found*, still
    *charged*, and never re-sent.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n201d")
    operation_id = "n201d-op"
    _sandbox(dsn, operation_id, alloc, attempt="n201d-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    broker.dispatch_operation(dsn, operation_id, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    for marker in run_dir.rglob("*"):
        if marker.is_file():
            marker.unlink()

    report = broker.reconcile(dsn, operation_id, {"local-process": launcher})
    assert report.decision == "unresolved-liability"
    assert store.allocation_status(dsn, alloc)["reserved"] > 0, (
        "the exposure must stay held; releasing it here would be the forged "
        "refund this repair exists to prevent")

    unfinished = store.restart_reconciliation(dsn)["unfinished_operations"]
    assert operation_id in {row["id"] for row in unfinished}, (
        "a stranded operation must remain visible to the driver's recovery scan")

    again = broker.dispatch_pending(dsn, {"local-process": launcher},
                                    ownership_generation=gen)
    assert again.dispatched == [], (
        "recovery must never re-run work the claim ledger forbids re-running")


def test_a_crash_with_its_receipt_intact_is_still_settled_not_stranded(
        migrated_db, tmp_path):
    """The ordinary crash after a send must cost nothing.

    This is the case fail-closed is supposed to leave alone. The claim refuses
    a *re-send*; it must not stop the driver from adopting the receipt that
    already exists. A ledger consulted by ``dispatch_pending`` rather than by
    ``reconcile`` would strand every crashed dispatch in the system.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n201e")
    operation_id = "n201e-op"
    _sandbox(dsn, operation_id, alloc, attempt="n201e-att")
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)
    broker.dispatch_operation(dsn, operation_id, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    assert launcher.claimed(operation_id, 1) is True, (
        "precondition: the send really was claimed")

    report = broker.dispatch_pending(dsn, {"local-process": launcher},
                                     ownership_generation=gen)
    assert report.dispatched == [], (
        "the claim must forbid a second send even with the receipt present")
    assert (run_dir / f"{operation_id}_exec-default.spawns").read_text().strip() == "1", (
        "the launcher must not re-run work it already did")
    assert _state(dsn, operation_id)["settled"] is True
    assert store.allocation_status(dsn, alloc)["reserved"] == 0, (
        "a receipted send must settle; the claim is not a reason to hold it")


def _state(dsn: str, operation_id: str) -> dict:
    row = broker.read_operation(dsn, operation_id) or {}
    return {k: row.get(k) for k in ("dispatch_state", "reconcile_state", "settled")}


# ---------------------------------------------------------------------------
# ``prior_send``.
# ---------------------------------------------------------------------------

def test_prior_send_answers_false_before_a_send_and_true_after_one(tmp_path):
    """``prior_send`` is a predicate over the run directory, not its truthiness.

    It is written as ``any(glob(...))`` over a generator, and a generator is
    always truthy, so a reading of this line is that the call answers True
    unconditionally. It does not: ``any`` drains the iterator. Pinned here
    because a future edit to the shape is how the bug would arrive, and because
    ``broker._send_sandbox`` and ``_send_adapter`` both branch on it.
    """
    run_dir = tmp_path / "runs"
    launcher = LocalLauncher(run_dir)

    assert launcher.prior_send("prior-op") is False, (
        "an operation that never ran has no prior send")
    assert launcher.prior_send("other-op") is False

    launcher.dispatch(_op("prior-op", 1))
    assert launcher.prior_send("prior-op") is True
    assert launcher.prior_send("other-op") is False, (
        "prior_send must be per-operation, not per-directory")


def test_prior_send_is_false_against_a_directory_holding_other_operations(
        tmp_path):
    """The failure the truthiness reading predicts, made literal.

    A run directory with markers in it and nothing for the asked operation is
    the case that separates "the directory is non-empty" from "this operation
    was sent". The truthiness reading gets this wrong; the real code does not.
    """
    launcher = LocalLauncher(tmp_path / "runs")
    launcher.dispatch(_op("occupied-op", 1))
    assert launcher.prior_send("absent-op") is False
    assert launcher.prove_never_sent("absent-op", 1) is True


# ---------------------------------------------------------------------------
# Location. Stated as an executable property, not as an assertion of safety.
# ---------------------------------------------------------------------------

def test_the_worker_can_reach_the_ledger_location_and_that_is_known(tmp_path,
                                                                   monkeypatch):
    """The containment claim, measured, in the one direction that hurts.

    Production runs the worker with ``cwd`` at or under the operation work
    tree, and the run directory is a child of it. If the ledger can be reached
    from the worker's own working directory, the ledger is a denial target,
    not a secret, and the repair's guarantee is durability, not secrecy.
    """
    work = tmp_path / "work"
    work.mkdir()
    ledger = work / "state" / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))
    launcher = LocalLauncher(work / "launcher")
    launcher.dispatch(_op("reachable-op", 1))
    assert ledger.is_file()

    # Same uid, no containment: the worker can write here.
    assert os.access(ledger, os.W_OK), (
        "if this ever becomes false the guarantee changes and the reason for "
        "this file changes with it")

    reachable = os.path.commonpath(
        [str(ledger.resolve()), str(work.resolve())]) == str(work.resolve())
    assert reachable is True, (
        "the ledger sits under the operation work tree, which is the worker's "
        "own working directory. This is a known, measured limitation.")


def test_a_worker_that_erases_the_run_directory_cannot_erase_the_claim(
        tmp_path, monkeypatch):
    """The threat the repair is built against, driven by a real worker.

    The payload is a real subprocess handed the run directory's path. It
    removes the whole directory while the launcher is still talking to it, and
    the claim is still on disk afterwards.

    The dispatch itself does not survive this: the launcher's post-spawn writes
    land in a directory the worker deleted, so ``dispatch`` raises OSError
    rather than returning an outcome. That is pre-existing behaviour and out of
    this file's scope, so it is tolerated here and recorded, not asserted. What
    is asserted is the property this repair owns: the claim outlives the
    evidence.
    """
    work = tmp_path / "work"
    work.mkdir()
    run_dir = work / "launcher"
    ledger = tmp_path / "state" / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))

    staged_dir = tmp_path / "staged"
    staged_dir.mkdir()
    evil = staged_dir / "driver.py"
    evil.write_text(
        "import shutil\n"
        f"shutil.rmtree({str(run_dir)!r}, ignore_errors=True)\n"
        "print('erased')\n")
    launcher = LocalLauncher(run_dir)
    op = BrokerOp(operation_id="erasure-op", effect=broker.SANDBOX_EXEC,
                  payload={"profile": "local-process",
                           "argv": [sys.executable, str(evil)],
                           "timeout_ms": 30_000, "max_output_bytes": 4096},
                  execution_version="exec-default", dispatch_generation=1)
    try:
        launcher.dispatch(op)
    except OSError:
        pass

    assert not run_dir.exists(), "precondition: the worker erased the evidence"
    assert launcher.claimed("erasure-op", 1) is True, (
        "the claim must survive the erasure of the directory it describes")
    assert launcher.prove_never_sent("erasure-op", 1) is False


@pytest.mark.parametrize("run_dir_suffix", ["", "/sub"])
def test_the_ledger_default_does_not_sit_under_the_run_directory(
        run_dir_suffix, tmp_path, monkeypatch):
    """The default location must be keyed to the run directory, not inside it.

    An explicit ``SETTLEMENT_CLAIM_LEDGER`` wins, so the default only has to
    be right for callers that pass none. It is derived from the run directory's
    own path, so two launchers over different run directories never share a
    ledger, and the ledger is never inside either of them.
    """
    monkeypatch.delenv("SETTLEMENT_CLAIM_LEDGER", raising=False)
    launcher = LocalLauncher(tmp_path / ("runs" + run_dir_suffix))
    ledger = launcher.claim_ledger()
    assert not ledger.is_relative_to(launcher.run_dir)
    assert not launcher.run_dir.is_relative_to(ledger)
    assert ledger.is_absolute()
