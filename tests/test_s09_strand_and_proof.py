"""N-47 and N-48: work a driver can never reach, and a proof the store cannot back.

Both defects live in ``src/settlement``. Both are written against the public
driver entry points, ``broker.dispatch_pending`` and ``store.reset_dispatch``,
and both assert durable state rather than a return value alone.

N-47: a racing thread can record a dispatch intent's delivery while the
operation is still ``dispatching`` or ``unresolved``. The prepared scan only
reaches ``prepared``; the outbox pass only reaches an UNDELIVERED intent; the
repair pass is the only code that walks ``restart_reconciliation``. So an
operation whose intent is delivered but whose state is unfinished is invisible
to every ``repair=False`` caller, for as long as the exposure stays held.

N-48: ``_never_sent_proof`` validates the shape of a caller-supplied proof and
never asks whether the provenance names anything that could have run. A proof
naming nothing gets accepted, and the sandbox runs a second time.

The last two tests are the guard rail. Neither repair may cost a decided
receipt, a fenced ``unknown``, or a second decided receipt on one operation.
"""

from __future__ import annotations

import uuid

from settlement import broker, store
from settlement.broker import BrokerOp, LaunchOutcome, ReceiptProposal
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher


class ScriptLauncher:
    """A second launcher, so a hardcoded launcher id cannot pass the suite."""

    launcher_id = "strand-fake-2"
    profile = "local-process"

    def dispatch(self, op: BrokerOp) -> LaunchOutcome:
        raise AssertionError("this launcher must never run in these tests")

    def prior_send(self, operation_id: str) -> bool:
        return False

    def prove_never_sent(self, operation_id: str, dispatch_generation: int | None = None) -> bool:
        return True

    def live_ids(self) -> list[str]:
        return []

    def is_live(self, operation_id: str) -> bool:
        return False

    def read_result(self, operation_id: str) -> dict | None:
        return None


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"s09sp_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn: str, tag: str, authorized: int = 10_000) -> tuple[str, int]:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "s09strand",
                                 "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "s09strand"}, f"{tag}i"))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                         "investigation_id": f"{tag}-i"},
                                        f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", int(gen)


def _sandbox(dsn: str, operation_id: str, alloc: str, *, attempt: str) -> None:
    assert broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id=attempt).code == ResultCode.APPLIED


def _state(dsn: str, operation_id: str) -> dict:
    row = broker.read_operation(dsn, operation_id) or {}
    return {k: row.get(k) for k in ("dispatch_state", "reconcile_state", "settled")}


def _stranded(dsn: str, tag: str, run_dir) -> tuple[str, str, LocalLauncher]:
    """Drive one operation into the state no ``repair=False`` pass can reach.

    The launcher sends, the crash flag stops the broker before it admits the
    receipt, and a racing thread records the delivery. That is two real code
    paths (``_send_sandbox``'s crash branch and ``_deliver``), not a synthetic
    database write.
    """
    alloc, gen = _env(dsn, tag)
    operation_id = f"{tag}-op"
    _sandbox(dsn, operation_id, alloc, attempt=f"{tag}-att")
    launcher = LocalLauncher(run_dir)
    broker.dispatch_operation(dsn, operation_id, launchers={"local-process": launcher},
                              ownership_generation=gen, _crash_after_send=True)
    assert broker._deliver(dsn, f"dispatch:{operation_id}") is True
    assert store.scan_outbox(dsn) == []
    assert _state(dsn, operation_id) == {"dispatch_state": "dispatching",
                                        "reconcile_state": "none", "settled": False}
    return alloc, operation_id, launcher


def _advanced_unsent(dsn: str, tag: str, run_dir) -> tuple[str, int, LocalLauncher]:
    """Advance one operation to ``dispatching`` and never let it send.

    This is the only state a true ``never-sent`` proof describes, so it is the
    one the store must still accept a proof for. The launcher is asked and
    answers yes.
    """
    alloc, gen = _env(dsn, tag)
    operation_id = f"{tag}-op"
    _sandbox(dsn, operation_id, alloc, attempt=f"{tag}-att")
    launcher = LocalLauncher(run_dir)
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": operation_id, "launcher_id": launcher.launcher_id,
        "ownership_generation": gen}, f"{tag}adv"))
    assert advanced.code == ResultCode.APPLIED
    assert _state(dsn, operation_id)["dispatch_state"] == "dispatching"
    return operation_id, int(advanced.data["dispatch_generation"]), launcher


# ---------------------------------------------------------------------------
# N-47. A delivered intent must not hide an unfinished operation.
# ---------------------------------------------------------------------------

def test_dispatch_pending_recovers_an_operation_whose_intent_was_delivered(
        migrated_db, tmp_path):
    """The driver that dispatched the work must be able to recover it.

    Fails while the operation stays ``dispatching`` and its exposure stays
    held: ``report.repaired`` is empty and ``_state`` is not settled.
    """
    dsn = migrated_db
    alloc, operation_id, launcher = _stranded(dsn, "n47", tmp_path / "runs")

    report = broker.dispatch_pending(dsn, {"local-process": launcher})

    assert report.repaired == [operation_id], (
        "dispatch_pending dispatched this operation and then could not see it "
        f"again; report was {report.model_dump()}")
    assert _state(dsn, operation_id) == {"dispatch_state": "observed",
                                         "reconcile_state": "none", "settled": True}
    assert store.restart_reconciliation(dsn)["unfinished_operations"] == []


def test_dispatch_pending_never_resends_work_the_launcher_already_ran(
        migrated_db, tmp_path):
    """Recovery is a readback, not a second execution.

    Fails if the repair path reaches the launcher at all: the spawn count is 1
    after the dispatch that actually sent, and must still be 1 after recovery.
    """
    dsn = migrated_db
    run_dir = tmp_path / "runs"
    alloc, operation_id, launcher = _stranded(dsn, "n47b", run_dir)

    assert (run_dir / f"{operation_id}_exec-default.spawns").read_text().strip() == "1"
    broker.dispatch_pending(dsn, {"local-process": launcher})

    assert (run_dir / f"{operation_id}_exec-default.spawns").read_text().strip() == "1", (
        "the repair must read the launcher's recorded result, never re-run it")
    assert [r["receipt_identity"] for r in store.operation_receipts(dsn, operation_id)] \
        == [f"reconciled:{operation_id}"]


def test_dispatch_pending_releases_the_exposure_it_was_holding(
        migrated_db, tmp_path):
    """The stranded exposure is the whole cost of the defect.

    Fails while the reservation stays reserved: the allocation reports a
    non-zero ``reserved`` after a pass that reported the work done.
    """
    dsn = migrated_db
    alloc, operation_id, launcher = _stranded(dsn, "n47c", tmp_path / "runs")
    assert store.allocation_status(dsn, alloc)["reserved"] > 0

    report = broker.dispatch_pending(dsn, {"local-process": launcher})

    assert report.repaired == [operation_id]
    assert store.allocation_status(dsn, alloc)["reserved"] == 0


def test_a_second_dispatch_pending_is_a_no_op_once_recovered(
        migrated_db, tmp_path):
    """Recovery converges: it does not loop or re-assert on every pass.

    Fails if the repair keeps re-reporting the same operation, or if a second
    pass re-enters it and reports it again.
    """
    dsn = migrated_db
    alloc, operation_id, launcher = _stranded(dsn, "n47d", tmp_path / "runs")
    first = broker.dispatch_pending(dsn, {"local-process": launcher})
    second = broker.dispatch_pending(dsn, {"local-process": launcher})

    assert first.repaired == [operation_id]
    assert second.repaired == []
    assert second.dispatched == [] and second.delivered == []
    assert len(store.operation_receipts(dsn, operation_id)) == 1


def test_dispatch_pending_still_dispatches_prepared_work(
        migrated_db, tmp_path):
    """The repair must not cost the pass its original job.

    Fails if adding repair turned ``dispatch_pending`` into a repair-only
    driver: ``report.dispatched`` is empty and the prepared operation never
    leaves ``prepared``.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n47e")
    _sandbox(dsn, "n47e-op", alloc, attempt="n47e-att")
    launcher = LocalLauncher(tmp_path / "runs")

    report = broker.dispatch_pending(dsn, {"local-process": launcher},
                                     ownership_generation=gen)

    assert report.dispatched == ["n47e-op"]
    assert _state(dsn, "n47e-op")["dispatch_state"] == "observed"


# ---------------------------------------------------------------------------
# N-48. A never-sent proof must name something that could have run.
# ---------------------------------------------------------------------------

def test_reset_dispatch_refuses_a_proof_naming_no_launcher(migrated_db, tmp_path):
    """A proof the store cannot back must fail closed.

    Fails while the free-text provenance is accepted: the code comes back
    ``applied`` and the operation is returned to ``prepared``, which is the
    state a second execution starts from.
    """
    dsn = migrated_db
    operation_id, generation, _ = _advanced_unsent(dsn, "n48", tmp_path / "runs")

    result = store.reset_dispatch(dsn, _cmd({
        "operation_id": operation_id,
        "expected_generation": generation,
        "never_sent_proof": {
            "claim": "never-sent",
            "subject": operation_id,
            "provenance": "forged",
            "dispatch_generation": generation,
        }}, "n48a"))

    assert result.code == ResultCode.MISSING_EVIDENCE, (
        f"an unattested proof must be refused; got {result.code.value}: {result.detail}")
    assert "provenance" in result.detail
    assert _state(dsn, operation_id)["dispatch_state"] == "dispatching", (
        "a refused reset must leave the operation exactly where it was")
    assert "_never_sent_proof" not in broker.read_operation(dsn, operation_id)["payload"]


def test_a_forged_proof_cannot_buy_a_second_execution(migrated_db, tmp_path):
    """The consequence the store must prevent, measured on the launcher.

    This is the defect's own cost. The launcher sent once; a forged proof
    returns the operation to ``prepared``; the second dispatch is the second
    run. Fails while ``spawns`` reads 2.
    """
    dsn = migrated_db
    run_dir = tmp_path / "runs"
    alloc, operation_id, launcher = _stranded(dsn, "n48b", run_dir)
    assert (run_dir / f"{operation_id}_exec-default.spawns").read_text().strip() == "1"
    generation = int(broker.read_operation(dsn, operation_id)
                     ["payload"]["_dispatch_generation"])

    result = store.reset_dispatch(dsn, _cmd({
        "operation_id": operation_id,
        "expected_generation": generation,
        "never_sent_proof": {
            "claim": "never-sent",
            "subject": operation_id,
            "provenance": "forged",
            "dispatch_generation": generation,
        }}, "n48c"))

    assert result.code == ResultCode.MISSING_EVIDENCE
    broker.dispatch_pending(dsn, {"local-process": launcher})
    assert (run_dir / f"{operation_id}_exec-default.spawns").read_text().strip() == "1", (
        "a refused proof must not admit a second run of work already done")


def test_a_proof_naming_the_wrong_launcher_is_also_refused(migrated_db, tmp_path):
    """Provenance is a claim about WHO could have run, not a non-empty string.

    Fails while any non-empty string passes: a plausible-looking but
    unregistered launcher id is accepted today.
    """
    dsn = migrated_db
    operation_id, generation, _ = _advanced_unsent(dsn, "n48d", tmp_path / "runs")

    result = store.reset_dispatch(dsn, _cmd({
        "operation_id": operation_id,
        "expected_generation": generation,
        "never_sent_proof": {
            "claim": "never-sent",
            "subject": operation_id,
            "provenance": "some-other-launcher:prove_never_sent",
            "dispatch_generation": generation,
        }}, "n48e"))

    assert result.code == ResultCode.MISSING_EVIDENCE, (
        f"a proof from an unregistered launcher must be refused; got {result.code.value}")


def test_a_backed_proof_is_still_accepted(migrated_db, tmp_path):
    """The refusal must not break the real path.

    Fails if the check over-refuses: the launcher's own proof, whose
    provenance names it, must still return the operation to ``prepared``.
    """
    dsn = migrated_db
    operation_id, generation, launcher = _advanced_unsent(dsn, "n48f", tmp_path / "runs")
    assert launcher.prove_never_sent(operation_id, generation) is True

    result = broker.redispatch_after_reset(
        dsn, operation_id, {"local-process": launcher}, expected_generation=generation)

    assert result.dispatch_state == "observed", (
        "a real never-sent proof must still redispatch; got "
        f"{result.dispatch_state}/{result.next_decision}")


def test_the_attested_launcher_is_read_from_the_operation_not_hardcoded(
        migrated_db, tmp_path):
    """The check must follow the operation's admitted launcher, not a constant.

    Every other test in this file uses ``LocalLauncher``, whose id is
    ``local-1``. A store that hardcoded that one name would pass all of them.
    This one admits a different launcher, so the two readings separate.
    Fails while a hardcoded or otherwise fixed launcher id is accepted.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "n48i")
    operation_id = "n48i-op"
    _sandbox(dsn, operation_id, alloc, attempt="n48i-att")
    launcher = ScriptLauncher()
    assert launcher.launcher_id != LocalLauncher.launcher_id, (
        "precondition: this test is worthless if the launchers share an id")
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": operation_id, "launcher_id": launcher.launcher_id,
        "ownership_generation": gen}, "n48iadv"))
    assert advanced.code == ResultCode.APPLIED
    generation = int(advanced.data["dispatch_generation"])
    assert launcher.prove_never_sent(operation_id, generation) is True

    proof = broker._structured_never_sent_proof(
        dsn, operation_id, {"local-process": launcher}, expected_generation=generation)
    assert proof["provenance"] == f"{launcher.launcher_id}:prove_never_sent"

    result = store.reset_dispatch(dsn, _cmd({
        "operation_id": operation_id,
        "expected_generation": generation,
        "never_sent_proof": proof,
    }, "n48ireset"))

    assert result.code == ResultCode.APPLIED, (
        f"the operation's own launcher must attest; got {result.code.value}: "
        f"{result.detail}")
    # And the other launcher's name must not be accepted for it.
    forged = store.reset_dispatch(dsn, _cmd({
        "operation_id": operation_id,
        "expected_generation": generation + 1,
        "never_sent_proof": {
            "claim": "never-sent", "subject": operation_id,
            "provenance": f"{LocalLauncher.launcher_id}:prove_never_sent",
            "dispatch_generation": generation + 1,
        }}, "n48iforged"))
    assert forged.code != ResultCode.APPLIED, (
        "a launcher that was never given this operation must not attest to it")


def test_the_broker_proof_shape_is_what_the_store_now_requires(
        migrated_db, tmp_path):
    """The store's rule and the broker's construction must agree.

    ``_structured_never_sent_proof`` writes ``<launcher id>:prove_never_sent``.
    If the store checked a different shape, the real path would break and the
    refusal tests above would pass for the wrong reason. This drives the real
    broker proof into a real store reset and reads what the store persisted.
    """
    dsn = migrated_db
    operation_id, generation, launcher = _advanced_unsent(dsn, "n48g", tmp_path / "runs")
    proof = broker._structured_never_sent_proof(
        dsn, operation_id, {"local-process": launcher}, expected_generation=generation)
    assert proof is not None
    assert proof["provenance"] == f"{LocalLauncher.launcher_id}:prove_never_sent"

    result = store.reset_dispatch(dsn, _cmd({
        "operation_id": operation_id,
        "expected_generation": generation,
        "never_sent_proof": proof,
    }, "n48h"))

    assert result.code == ResultCode.APPLIED
    stored = broker.read_operation(dsn, operation_id)["payload"]["_never_sent_proof"]
    assert stored == proof


# ---------------------------------------------------------------------------
# Guard rail. Neither repair may cost a decided receipt.
# ---------------------------------------------------------------------------

def test_a_second_decided_receipt_on_one_operation_is_still_refused(
        migrated_db, tmp_path):
    """A decided outcome stays structurally unique per operation.

    This is the invariant the repairs were told not to weaken, and it lives in
    ``admit_receipt``, which neither repair touches. It is asserted here so the
    guarantee is measured rather than assumed. Fails if a second success or
    failure is ever admitted on one operation.
    """
    dsn = migrated_db
    alloc, gen = _env(dsn, "g1")
    operation_id = "g1-op"
    _sandbox(dsn, operation_id, alloc, attempt="g1-att")
    assert store.advance_dispatch(dsn, _cmd({
        "operation_id": operation_id, "launcher_id": "strand-fake-2",
        "ownership_generation": gen}, "g1adv")).code == ResultCode.APPLIED

    first = broker.admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
        receipt_identity="g1:first", content={"ok": True}, outcome="success",
        provenance="strand-fake-2"))
    # A `failure` must carry the evidence N-43 requires, or it is refused for
    # that reason and never reaches the second-receipt rule. `parse` is the
    # launcher's account of how it reached the verdict.
    second = broker.admit_launcher_receipt(dsn, operation_id, ReceiptProposal(
        receipt_identity="g1:second", content={"parse": "verdict", "ok": False},
        outcome="failure", provenance="strand-fake-2"))

    assert first.code == ResultCode.APPLIED
    assert second.code == ResultCode.APPLIED, (
        f"the failure receipt must pass evidence validation to reach the "
        f"second-receipt rule; got {second.code.value}: {second.detail}")
    assert second.data.get("conflict") is True, (
        f"a second decided receipt must be refused; got {second.code.value} "
        f"with data {second.data}")
    decided = [r for r in store.operation_receipts(dsn, operation_id)
               if r["outcome"] in ("success", "failure")]
    assert len(decided) == 1, f"decided receipt count must never exceed 1: {decided}"


def test_a_recovered_receipt_still_settles_the_operation(migrated_db, tmp_path):
    """The recovery N-47 relies on must still produce a real settlement.

    A strand that is reported repaired but never settled would look fixed and
    still hold the exposure. Fails while the recovered operation is not
    observed and settled with exactly one decided receipt.
    """
    dsn = migrated_db
    alloc, operation_id, launcher = _stranded(dsn, "g2", tmp_path / "runs")

    report = broker.dispatch_pending(dsn, {"local-process": launcher})

    assert report.repaired == [operation_id]
    assert _state(dsn, operation_id) == {"dispatch_state": "observed",
                                         "reconcile_state": "none", "settled": True}
    assert store.allocation_status(dsn, alloc)["reserved"] == 0
    decided = [r for r in store.operation_receipts(dsn, operation_id)
               if r["outcome"] in ("success", "failure")]
    assert len(decided) == 1, f"recovery must decide the operation exactly once: {decided}"
