"""N-56: what a dispatch reset owes, and who may say the work was never sent.

The fork this file settles: N-48 made ``store.reset_dispatch`` hold the
caller's never-sent proof to the launcher the operation was admitted to, and
one pre-existing test that reset with no proof went red. The two readings were
that the test was stale or that the repair had narrowed a real public entry
point.

The evidence settled it as the test, and the rule is this:

  A dispatch reset returns an operation to ``prepared`` only when the proof
  names the launcher that operation was admitted to, bound to the operation's
  current dispatch generation.

``prepared`` is the state a sandbox execution starts from, so a reset that was
not earned buys a second run of work already done. The store cannot ask a
launcher, so it holds the proof to the one name it does know.

Every assertion below is paired with the edit that makes it fail, and each was
demonstrated by breaking that edit and watching the file go red. The three
demonstrations are recorded in the lane report, not here.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from settlement import broker, store
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"s09n56_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn: str, tag: str) -> tuple[str, str, int]:
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "s09n56",
                                 "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": 10_000}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "s09n56"}, f"{tag}i"))
    gen = store.acquire_work(dsn, _cmd({"attempt_id": f"{tag}-att",
                                         "investigation_id": f"{tag}-i"},
                                        f"{tag}q")).data["ownership_generation"]
    return f"{tag}-a", f"{tag}-att", int(gen)


def _sandbox(dsn: str, operation_id: str, alloc: str, attempt: str) -> None:
    assert broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 30_000, "max_output_bytes": 4096},
        allocation_id=alloc, attempt_id=attempt).code == ResultCode.APPLIED


def _state(dsn: str, operation_id: str) -> dict:
    row = broker.read_operation(dsn, operation_id) or {}
    return {k: row.get(k) for k in ("dispatch_state", "launcher_id")}


def _paused_before_claim(monkeypatch, dsn: str, tag: str,
                         run_dir: Path) -> tuple[str, LocalLauncher, dict]:
    """Park a real dispatch inside ``LocalLauncher._claim``, before any send.

    A gated ``_claim`` holds the worker between the store's admission and the
    launcher's own send, which is the one window where the work is admitted,
    nothing has been sent, and an honest never-sent proof exists. Both facts
    are read back rather than assumed.
    """
    alloc, attempt, _ = _env(dsn, tag)
    operation_id = f"{tag}-op"
    _sandbox(dsn, operation_id, alloc, attempt)
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
        "status", broker.dispatch_operation(dsn, operation_id, launchers=launchers)))
    worker.start()
    assert entered.wait(timeout=30)
    return operation_id, launcher, {"release": release, "worker": worker,
                                    "holder": holder, "launchers": launchers}


def test_an_admitted_launcher_may_attest_and_the_reset_then_applies(
        migrated_db, tmp_path, monkeypatch):
    """The positive half of the rule, at the store boundary.

    The operation is parked before its launcher claims, so nothing was sent
    and the operation's own launcher is entitled to say so. The store takes
    that proof and returns the operation to ``prepared``.

    This is the half that must not be over-tightened. A store that refused
    every proof would pass every other test in this file and still be wrong,
    because it would strand the only work it is safe to re-run. Fails while
    the honest proof is refused, for instance if the store held the caller to
    a name the broker does not write.
    """
    dsn = migrated_db
    operation_id, launcher, held = _paused_before_claim(monkeypatch, dsn, "n56a",
                                                        tmp_path / "runs")
    try:
        row = broker.read_operation(dsn, operation_id)
        assert row["launcher_id"] == launcher.launcher_id
        assert launcher.prove_never_sent(operation_id, 1) is True, (
            "the fixture must park the worker before any send, or there is "
            "no honest proof to give")
        proof = broker._structured_never_sent_proof(
            dsn, operation_id, {"local-process": launcher}, expected_generation=1)
        assert proof is not None and \
            proof["provenance"] == f"{launcher.launcher_id}:prove_never_sent"

        result = store.reset_dispatch(dsn, _cmd({
            "operation_id": operation_id, "expected_generation": 1,
            "never_sent_proof": proof}, "a"))
        assert result.code == ResultCode.APPLIED, (
            f"the operation's own launcher must be enough; got "
            f"{result.code.value}: {result.detail}")
        assert _state(dsn, operation_id) == {"dispatch_state": "prepared",
                                             "launcher_id": ""}, (
            "an applied reset must land on prepared with the admission cleared")
    finally:
        held["release"].set()
        held["worker"].join(timeout=60)


def test_a_reset_on_that_state_still_runs_the_work_exactly_once(
        migrated_db, tmp_path, monkeypatch):
    """The consequence, measured on the launcher rather than on a return code.

    The paused worker resumes, finds its claim superseded, and must not spawn.
    The fresh dispatch runs the operation once. ``spawns`` is the launcher's
    own count of real executions, so a fence that leaked shows up here as 2.

    Fails while the generation written by the reset is not the one the launcher
    fences on, or while the reset leaves the old admission in place: the
    resumed worker then claims and spawns.
    """
    dsn = migrated_db
    operation_id, _, held = _paused_before_claim(monkeypatch, dsn, "n56b",
                                                 tmp_path / "runs")
    launchers = held["launchers"]
    run_dir = tmp_path / "runs"
    try:
        status = broker.redispatch_after_reset(dsn, operation_id, launchers,
                                               expected_generation=1)
        assert status.sent_this_call is True, (
            f"the honest path must run the work; got {status.next_decision}")
        assert _state(dsn, operation_id)["dispatch_state"] == "observed"
    finally:
        held["release"].set()
        held["worker"].join(timeout=60)
    assert not held["worker"].is_alive()
    assert held["holder"]["status"].sent_this_call is False, (
        "the worker parked before its claim must not send after the reset")
    assert (run_dir / f"{operation_id}_exec-default.spawns").read_text().strip() == "1", (
        "one reset and one recovery is one execution, not two")
    assert (run_dir / f"{operation_id}_exec-default.gen").read_text().strip() == "3"
    assert [r["outcome"] for r in store.operation_receipts(dsn, operation_id)] == ["success"]


def test_a_reset_with_no_proof_is_refused_and_moves_nothing(
        migrated_db, tmp_path, monkeypatch):
    """The negative half, which is the case N-48 was written for.

    A caller with nothing to say gets nothing. The refusal leaves the
    operation exactly where it was, because a reset that half-applied would
    strand the work without having earned the right to re-run it.

    Fails while ``_never_sent_proof`` tolerates an absent proof, or while a
    refusal still updates the operation.
    """
    dsn = migrated_db
    operation_id, _, held = _paused_before_claim(monkeypatch, dsn, "n56c",
                                                 tmp_path / "runs")
    try:
        before = _state(dsn, operation_id)
        result = store.reset_dispatch(dsn, _cmd({
            "operation_id": operation_id, "expected_generation": 1}, "c"))
        assert result.code == ResultCode.MISSING_EVIDENCE, (
            f"a reset with no proof must be refused; got {result.code.value}")
        assert "provenance" in result.detail
        assert _state(dsn, operation_id) == before
        assert "_never_sent_proof" not in \
            (broker.read_operation(dsn, operation_id) or {})["payload"]
    finally:
        held["release"].set()
        held["worker"].join(timeout=60)


def test_a_proof_for_a_different_dispatch_is_refused(
        migrated_db, tmp_path, monkeypatch):
    """Attribution is not enough. The proof must describe the dispatch it gates.

    A proof names one dispatch generation. A different generation is a claim
    about a different send, and ``expected_generation`` only fences the caller
    against the store, not the proof. Consuming a mismatched pair would return
    the operation to ``prepared`` on evidence about a send that is not the one
    being cancelled.

    Fails while ``_never_sent_proof`` stops comparing the proof's generation
    with the operation's current one.
    """
    dsn = migrated_db
    operation_id, launcher, held = _paused_before_claim(monkeypatch, dsn, "n56e",
                                                        tmp_path / "runs")
    try:
        current = int((broker.read_operation(dsn, operation_id) or {})
                      ["payload"]["_dispatch_generation"])
        result = store.reset_dispatch(dsn, _cmd({
            "operation_id": operation_id, "expected_generation": current,
            "never_sent_proof": {
                "claim": "never-sent", "subject": operation_id,
                "provenance": f"{launcher.launcher_id}:prove_never_sent",
                "dispatch_generation": current + 1}}, "e"))
        assert result.code == ResultCode.MISSING_EVIDENCE, (
            f"a proof for generation {current + 1} must not gate generation "
            f"{current}; got {result.code.value}")
        assert _state(dsn, operation_id) == {"dispatch_state": "dispatching",
                                             "launcher_id": launcher.launcher_id}
    finally:
        held["release"].set()
        held["worker"].join(timeout=60)


def test_an_operation_admitted_to_no_launcher_fails_closed(
        migrated_db):
    """The one case the repair narrowed past the honest use, pinned as closed.

    ``steward.dispatch_guarded`` and any direct ``store.advance_dispatch`` name
    no launcher, so an operation can reach ``dispatching`` with an empty
    ``launcher_id``. No launcher can speak for it, so no proof of its own can
    be accepted. Refusing strands the operation for an explicit reconcile, and
    that is the safe direction: the alternative accepts a reset whose evidence
    nobody produced.

    Pinned rather than changed, because the safe direction is the one to leave
    in place while it is load-bearing. Fails while an empty admission is
    treated as though it had a launcher to name.
    """
    dsn = migrated_db
    alloc, attempt, gen = _env(dsn, "n56d")
    operation_id = "n56d-op"
    _sandbox(dsn, operation_id, alloc, attempt)
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": operation_id, "ownership_generation": gen}, "dadv"))
    assert advanced.code == ResultCode.APPLIED
    assert _state(dsn, operation_id) == {"dispatch_state": "dispatching",
                                         "launcher_id": ""}, (
        "precondition: this test is worthless unless the operation really "
        "reached dispatching with no launcher")

    result = store.reset_dispatch(dsn, _cmd({
        "operation_id": operation_id, "expected_generation": 1,
        "never_sent_proof": {
            "claim": "never-sent", "subject": operation_id,
            "provenance": "local-1:prove_never_sent",
            "dispatch_generation": 1}}, "d"))
    assert result.code == ResultCode.MISSING_EVIDENCE
    assert _state(dsn, operation_id) == {"dispatch_state": "dispatching",
                                         "launcher_id": ""}
