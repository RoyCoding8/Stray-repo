"""N-200/N-201: the per-dispatch capability, and the store boundary it cannot cross.

``launcher_local.LocalLauncher`` now mints a per-dispatch capability and hands it
to ``broker._structured_never_sent_proof``, which carries it in the proof. The
capability is an HMAC over the operation id and dispatch generation under a
secret drawn once per launcher process, so it binds a proof to one launcher's
one dispatch and cannot be copied off the operation row.

These tests pin what that capability is worth at the two boundaries it touches.

The first boundary is the launcher, and there the capability is sound: a proof
synthesized from the operation row does not verify, a proof naming the public
``"local-1"`` constant does not verify, and an honest proof does. The last of
the five tests pins that it is bound to its generation and cannot be replayed
onto a different dispatch.

The second boundary is the store, and there it is worth nothing yet. ``store``
is outside this lane's scope, so this file records the gap rather than closing
it: the first two tests are the required refusal behaviour and they are RED
until ``store._never_sent_proof`` verifies the capability it is handed. They are
written as the refusal must eventually behave, not as a description of what
today's store does.
"""

from __future__ import annotations

import sys
import uuid

from settlement import broker, launcher_local, store
from settlement.broker import BrokerOp
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher

SANDBOX_TIMEOUT_MS = 30_000
_ARGV_PLACEHOLDER = ["unused"]


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"n200cap_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn: str, tag: str, authorized: int = 10 ** 6) -> tuple[str, int]:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "n200cap",
                                 "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "n200cap"}, f"{tag}i"))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                         "investigation_id": f"{tag}-i"},
                                        f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", int(gen)


def _sandbox_payload(argv: list[str]) -> dict:
    return {"profile": launcher_local.PROFILE, "argv": argv,
            "timeout_ms": SANDBOX_TIMEOUT_MS, "cpu_seconds": 30}


def _sandbox(dsn: str, operation_id: str, alloc: str, *, attempt: str,
             argv: list[str]) -> None:
    assert broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload=_sandbox_payload(argv),
        allocation_id=alloc, attempt_id=attempt).code == ResultCode.APPLIED


def _sandbox_exposure() -> int:
    units, kind = broker.exposure_schedule(
        broker.SANDBOX_EXEC, _sandbox_payload(_ARGV_PLACEHOLDER), 0)
    assert kind == "hard-ceiling"
    return units


def _ran_and_uncertain(dsn: str, tag: str, run_dir):
    """A real execution whose response was lost, and the exposure it left."""
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
    """Every field a caller can read off the store, and nothing else."""
    row = broker.read_operation(dsn, operation_id)
    return {
        "claim": "never-sent",
        "subject": operation_id,
        "provenance": f"{row['launcher_id']}:prove_never_sent",
        "dispatch_generation": int((row["payload"] or {})["_dispatch_generation"]),
    }


def test_a_proof_the_caller_wrote_from_the_operation_row_is_refused(
        migrated_db, tmp_path):
    """The store must not refund a real execution on evidence it can rebuild.

    Every field of this proof is on the operation row. A capability the store
    verifies would make it unspellable; a store that ignores the capability
    cannot tell it from one the launcher actually minted.

    RED until ``store._never_sent_proof`` checks the capability it is handed.
    """
    dsn = migrated_db
    alloc, operation_id, generation, launcher = _ran_and_uncertain(
        dsn, "capA", tmp_path / "runs")

    assert launcher.prove_never_sent(operation_id, generation) is False, (
        "precondition: the launcher must report a prior send, or there is "
        "nothing to refund in error")
    before = store.allocation_status(dsn, alloc)
    assert before["reserved"] == _sandbox_exposure()

    result = store.release_reservation(dsn, _cmd({
        "reservation_id": f"res-{operation_id}",
        "never_sent_proof": _forged_from_the_row(dsn, operation_id)}, "rel"))

    after = store.allocation_status(dsn, alloc)
    assert result.code != ResultCode.APPLIED, (
        "a proof assembled from the operation row refunded a sandbox that "
        f"really ran; got {result.code.value}: {result.detail}")
    assert after["reserved"] == before["reserved"], (
        f"held units {before['reserved']} -> {after['reserved']}")


def test_a_proof_naming_the_public_launcher_constant_is_refused(
        migrated_db, tmp_path):
    """Hardening the constant is not a fix; the capability is the fix.

    ``"local-1"`` is a class attribute, so any caller can spell it. A refusal
    that only checks the spelling passes this proof.

    RED until the store verifies the capability rather than the name.
    """
    dsn = migrated_db
    alloc, operation_id, generation, launcher = _ran_and_uncertain(
        dsn, "capB", tmp_path / "runs")
    assert LocalLauncher.launcher_id == "local-1"

    before = store.allocation_status(dsn, alloc)
    result = store.release_reservation(dsn, _cmd({
        "reservation_id": f"res-{operation_id}", "never_sent_proof": {
            "claim": "never-sent", "subject": operation_id,
            "provenance": f"{LocalLauncher.launcher_id}:prove_never_sent",
            "dispatch_generation": generation}}, "rel"))

    after = store.allocation_status(dsn, alloc)
    assert result.code != ResultCode.APPLIED, (
        f"the public constant bought a refund; got {result.code.value}: "
        f"{result.detail}")
    assert after["reserved"] == before["reserved"]


def test_the_launcher_refuses_to_mint_a_capability_for_a_run_that_started(
        migrated_db, tmp_path):
    """The capability is only as good as the launcher's willingness to mint it.

    A proof whose operation really ran must not come back with a capability at
    all. This is the launcher-side half of the refusal, and unlike the two above
    it is decided inside the launcher, so it is green today.
    """
    dsn = migrated_db
    _, operation_id, generation, launcher = _ran_and_uncertain(
        dsn, "capC", tmp_path / "runs")

    assert launcher.prove_never_sent(operation_id, generation) is False
    assert launcher.attest_never_sent(operation_id, generation) is None, (
        "a run that really started must never receive a never-sent attestation")


def test_an_honest_never_sent_proof_still_releases(
        migrated_db, tmp_path):
    """The repair must not strand work the launcher can vouch for (N-48).

    This is the only state a true never-sent proof describes: the operation is
    ``dispatching``, the launcher was asked, and it answered yes. Over-refusing
    here converts a recoverable crash into held exposure forever, which is a
    different defect and not a repair.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "capD")
    operation_id = "capD-op"
    _sandbox(dsn, operation_id, alloc, attempt="capD-att",
             argv=[sys.executable, "-c", "pass"])
    launcher = LocalLauncher(tmp_path / "runs-d")
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": operation_id, "launcher_id": launcher.launcher_id,
        "ownership_generation": gen}, "dadv"))
    assert advanced.code == ResultCode.APPLIED
    generation = int(advanced.data["dispatch_generation"])

    proof = broker._structured_never_sent_proof(
        dsn, operation_id, {"local-process": launcher},
        expected_generation=generation)
    assert proof is not None, (
        "an honest never-sent proof must be produced; otherwise the reset "
        "path is dead")
    assert proof["capability"], (
        "the broker must carry the launcher's capability, or the store has "
        "nothing to verify that a caller could not write")

    result = store.release_reservation(dsn, _cmd({
        "reservation_id": f"res-{operation_id}", "never_sent_proof": proof}, "drel"))
    assert result.code == ResultCode.APPLIED, (
        f"an honest proof must still release; got {result.code.value}: "
        f"{result.detail}")
    assert store.allocation_status(dsn, alloc)["reserved"] == 0


def test_an_operation_admitted_to_no_launcher_fails_closed(
        migrated_db, tmp_path):
    """An operation with no launcher has nothing that could attest for it.

    The empty-string carve-out is pinned in the other direction: refusing here
    strands the operation for an explicit reconcile, which is the safe side.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "capE")
    operation_id = "capE-op"
    _sandbox(dsn, operation_id, alloc, attempt="capE-att",
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


def test_a_capability_is_bound_to_its_dispatch_and_cannot_be_replayed(
        tmp_path):
    """N-201: one dispatch's evidence must not open another's refund.

    This is the distinguishability a capability buys, and it is the part that
    holds without any store change. The capability is an HMAC over the
    operation id and the dispatch generation, so it does not transfer between
    generations, between operations, or between launcher instances -- a caller
    holding a genuine capability for one dispatch cannot stretch it to
    describe a different one.

    What it does not settle is the deletion case. ``LocalLauncher`` keeps no
    durable record that outlives its run-directory files, so a run whose
    evidence is deleted afterwards is still indistinguishable from one that
    never claimed: ``prove_never_sent`` answers from the run directory alone.
    Closing that needs a launcher-held ledger that survives evidence deletion,
    which this lane cannot add without breaking the N-48 positive path pinned
    in ``tests/test_s09_controls.py``, where erasing the run-directory record
    is precisely what makes an honest attestation possible.
    """
    first = LocalLauncher(tmp_path / "runs-1")
    second = LocalLauncher(tmp_path / "runs-2")

    minted = first.attest_never_sent("op-one", 1)
    assert minted is not None and minted["capability"], (
        "precondition: an unclaimed operation must attest")

    assert first.verify_capability("op-one", 1, minted["capability"]) is True
    assert first.verify_capability("op-one", 2, minted["capability"]) is False, (
        "a capability must not carry to a later dispatch generation")
    assert first.verify_capability("op-two", 1, minted["capability"]) is False, (
        "a capability must not carry to another operation")
    assert second.verify_capability("op-one", 1, minted["capability"]) is False, (
        "a capability minted by one launcher must not verify against another")
    assert first.verify_capability("op-one", 1, "0" * 64) is False, (
        "a guessed capability must not verify")
