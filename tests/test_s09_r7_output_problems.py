"""Six failures, one test per root cause, so none can drift back together.

Each test states a property the current code actually holds and names the
commit that established it. The value is not coverage. A reader who breaks
one of these properties sees which of the six it was, instead of a cascade
that reads like one broken subsystem.
"""

from __future__ import annotations

import copy
import json

import pytest

from experiments.ad01 import live_construct as live
from experiments.ad01 import offline_recompute as m4
from scripts import invl02_live as driver
from settlement.gateway import ModelRequest
from test_output_evidence import _OutputGateway, _responses


def _cmd(payload):
    """A request id derived from the payload, so a retry is one command.

    A bare counter is not enough. The per-run database outlives a single test,
    and the command journal refuses a reused identity whose payload changed.
    """
    from settlement.common import Command, payload_digest

    return Command(request_id="r7-" + payload_digest(payload)[:32],
                   payload=payload)


# `5577a89` made it a store invariant that a receipt cannot be admitted onto
# a `prepared` operation, because a prepared operation has provably sent
# nothing and a receipt is the record of a send. The operation stays
# unresolved and its reservation stays held, which is the truth. The r02
# accounting tests seeded a receipt straight onto a prepared operation, so
# they read the refusal as a settlement failure.


def test_receipt_onto_a_prepared_operation_is_refused(migrated_db):
    from settlement import store

    dsn = migrated_db
    store.seed_allocation(dsn, _cmd(
        {"allocation_id": "r7-a", "domain": "cpu", "authorized": 5000}))
    store.prepare_operation(dsn, _cmd({
        "operation_id": "r7-unbilled", "allocation_id": "r7-a",
        "reservation_id": "res-r7-unbilled", "exposure": 1000,
        "operation": {"effect": "model-inference"}}))

    refused = store.admit_receipt(dsn, _cmd({
        "operation_id": "r7-unbilled", "receipt_identity": "rc-r7",
        "content": {"text": "done", "usage": {
            "input_tokens": 10, "output_tokens": 20,
            "charge_units": None, "billed": None}},
        "outcome": "success", "provenance": "gateway"}))

    assert refused.code.name == "INVALID_INPUT"
    assert refused.detail == "operation r7-unbilled was not dispatched"
    status = store.allocation_status(dsn, "r7-a")
    assert (status["consumed"], status["reserved"]) == (0, 1000)


def test_dispatched_operation_settles_its_full_reservation(migrated_db):
    """What the accounting tests assert, reached through a real send.

    Same operation, same receipt, same expected settlement as the refused
    case above. The only difference is that the operation was dispatched
    first, so the receipt is a record of a send that happened.
    """
    from settlement import experiment, store

    dsn = migrated_db
    store.seed_allocation(dsn, _cmd(
        {"allocation_id": "r7-b", "domain": "cpu", "authorized": 5000}))
    store.prepare_operation(dsn, _cmd({
        "operation_id": "r7-unbilled", "allocation_id": "r7-b",
        "reservation_id": "res-r7-unbilled", "exposure": 1000,
        "operation": {"effect": "model-inference"}}))
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": "r7-unbilled", "launcher_id": "local-process"}))
    assert advanced.code.name == "APPLIED", advanced.detail

    admitted = store.admit_receipt(dsn, _cmd({
        "operation_id": "r7-unbilled", "receipt_identity": "rc-r7",
        "content": {"operation_id": "r7-unbilled", "text": "done", "usage": {
            "input_tokens": 10, "output_tokens": 20,
            "charge_units": None, "billed": None}},
        "outcome": "success", "provenance": "gateway"}))
    assert admitted.code.name == "APPLIED", admitted.detail

    status = store.allocation_status(dsn, "r7-b")
    assert (status["consumed"], status["reserved"]) == (1000, 0)
    entry = experiment._op_accounting(dsn, "r7-unbilled")
    assert entry["settled"] == 1000
    assert entry["unresolved"] == 0
    assert entry["billed"] is None
    assert entry["provider_charge_units"] is None
    assert entry["tokens"] == {"input": 10, "output": 20}


def test_billed_receipt_settles_the_provider_charge(migrated_db):
    from settlement import experiment, store

    dsn = migrated_db
    store.seed_allocation(dsn, _cmd(
        {"allocation_id": "r7-c", "domain": "cpu", "authorized": 5000}))
    store.prepare_operation(dsn, _cmd({
        "operation_id": "r7-billed", "allocation_id": "r7-c",
        "reservation_id": "res-r7-billed", "exposure": 1000,
        "operation": {"effect": "model-inference"}}))
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": "r7-billed", "launcher_id": "local-process"}))
    assert advanced.code.name == "APPLIED", advanced.detail

    admitted = store.admit_receipt(dsn, _cmd({
        "operation_id": "r7-billed", "receipt_identity": "rc-r7-billed",
        "content": {"operation_id": "r7-billed", "text": "done", "usage": {
            "input_tokens": 5, "output_tokens": 7,
            "charge_units": 42, "billed": True}},
        "outcome": "success", "provenance": "gateway", "actual_cost": 42}))
    assert admitted.code.name == "APPLIED", admitted.detail

    status = store.allocation_status(dsn, "r7-c")
    assert (status["consumed"], status["reserved"]) == (42, 0)
    entry = experiment._op_accounting(dsn, "r7-billed")
    assert entry["settled"] == 42
    assert entry["billed"] is True
    assert entry["provider_charge_units"] == 42
    assert entry["tokens"] == {"input": 5, "output": 7}


def test_conflicting_receipt_is_preserved_after_a_dispatched_operation(
        migrated_db):
    """The conflict is preserved, on an operation that actually ran.

    `test_receipt_outcome_conflict_is_preserved` asserted this against an
    operation that had never been dispatched, so the conflict branch was
    never reached. That test was reading a refusal as a preservation, and
    it is the assertion that deserved the suspicion.
    """
    from psycopg.rows import dict_row
    from settlement import db, store

    dsn = migrated_db
    content = {"operation_id": "r7-op", "text": "done", "usage": {
        "input_tokens": 10, "output_tokens": 20,
        "charge_units": None, "billed": False}}
    store.seed_allocation(dsn, _cmd(
        {"allocation_id": "r7-d", "domain": "cpu", "authorized": 5000}))
    store.prepare_operation(dsn, _cmd({
        "operation_id": "r7-op", "allocation_id": "r7-d",
        "reservation_id": "res-r7-op", "exposure": 1000,
        "operation": {"effect": "model-inference"}}))
    advanced = store.advance_dispatch(dsn, _cmd({
        "operation_id": "r7-op", "launcher_id": "local-process"}))
    assert advanced.code.name == "APPLIED", advanced.detail
    first = store.admit_receipt(dsn, _cmd({
        "operation_id": "r7-op", "receipt_identity": "rc-r7-op",
        "content": content, "outcome": "success", "provenance": "gateway"}))
    assert first.code.name == "APPLIED", first.detail

    conflict = store.admit_receipt(dsn, _cmd({
        "operation_id": "r7-op", "receipt_identity": "rc-r7-op",
        "content": content, "outcome": "failure",
        "provenance": "later-provider"}))

    assert conflict.code.name == "APPLIED"
    assert conflict.data["conflict"] is True
    # The projection carries `provenance` since N-302 (`a1e1fb3`).
    assert store.operation_receipts(dsn, "r7-op") == [{
        "receipt_identity": "rc-r7-op",
        "outcome": "success",
        "content": content,
        "provenance": "gateway",
    }]
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # `outcome` and `provenance` are fields of the preserved content
            # object, not columns.
            cur.execute(
                "SELECT content FROM receipt_conflicts"
                " WHERE receipt_identity = %s", ("rc-r7-op",))
            preserved = dict(cur.fetchone())
            conn.commit()
    assert preserved["content"] == {
        "receipt_content": content,
        "outcome": "failure",
        "provenance": "later-provider",
        "actual_cost": None,
    }


# `5577a89` also made an attempt's bound allocation mandatory. An operation
# prepared against an attempt that has no allocation has no authority to
# charge one, so prepare refuses and there is no stranded dispatching
# operation for the repair scan to reconcile.


def test_prepare_on_an_unbound_attempt_is_refused(migrated_db):
    from settlement import store

    dsn = migrated_db
    store.seed_allocation(dsn, _cmd(
        {"allocation_id": "r7-a1", "domain": "cpu", "authorized": 100}))
    store.admit_commitment(dsn, _cmd(
        {"investigation_id": "r7-i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({
        "attempt_id": "r7-w1", "investigation_id": "r7-i1",
        "allocation_id": "r7-a1"}))
    assert acquired.code.name == "APPLIED", acquired.detail

    refused = store.prepare_operation(dsn, _cmd({
        "operation_id": "r7-op1", "attempt_id": "r7-w1",
        "operation": {"effect": "note"}}))

    assert refused.code.name == "INVALID_INPUT"
    assert refused.detail == "attempt r7-w1 requires its bound allocation"


# `6d63d01` replaced a task id that ended in the seed with an HMAC-salted
# opaque id, because the old id let a policy holding only the view enumerate
# the seed back out of it. A test that recovers the seed from the id is
# reading a property the id was deliberately built to deny.


def test_frozen_task_ids_do_not_reveal_their_seed():
    from experiments.ad01 import boolean_rule as rules

    for split, seed in live.OUTPUT_TASKS.items():
        task_id = rules.make_task(split, int(seed))["task_id"]
        assert str(seed) not in task_id, task_id
        assert task_id == m4._task_id_for(split, seed)


def test_split_comes_from_the_producers_mapping_not_from_the_id_shape(
        tmp_path):
    """Only the producer's own mapping turns a task id back into a split.

    A caller holding the id cannot recover the split by pattern-matching it
    for a seed suffix, because the id no longer carries one.
    """
    freeze = driver.freeze_output(tmp_path)
    gateway = _OutputGateway(_responses(), freeze["route"])
    result = driver.run_output(
        tmp_path, gateway=gateway, model=freeze["route"]["requested_model"])
    first = next(entry for entry in result["candidate_view"]["dispatches"]
                 if entry["parse_outcome"] == "accepted"
                 and entry["attempt"] == 1)

    resolved = [split for split, seed in live.OUTPUT_TASKS.items()
                if m4._task_id_for(split, seed) == first["task_id"]]
    assert len(resolved) == 1
    assert resolved[0] in live.OUTPUT_TASKS


def test_repair_after_an_accepted_response_names_its_own_split(tmp_path):
    """`repair-after-accepted` is reported against the split it belongs to.

    The split comes from the producer's id mapping rather than from a pattern
    match on the id. The count fields the verifier cross-checks are kept
    consistent so the repair is what the verdict reports.
    """
    freeze = driver.freeze_output(tmp_path)
    gateway = _OutputGateway(_responses(), freeze["route"])
    result = driver.run_output(
        tmp_path, gateway=gateway, model=freeze["route"]["requested_model"])
    view = result["candidate_view"]
    first = next(entry for entry in view["dispatches"]
                 if entry["parse_outcome"] == "accepted"
                 and entry["attempt"] == 1)
    split = _split_of(first["task_id"])

    repair = copy.deepcopy(first)
    repair.update({
        "operation_id": live.output_operation_id(
            first["arm"], split, int(live.OUTPUT_TASKS[split]), 2,
            round_run_id=freeze["run_id"]),
        "attempt": 2,
        "parse_outcome": "parse-failed",
        "raw_response": "not json",
        "response_digest": m4.source_digest("not json"),
        "accepted_candidate_digest": None,
    })
    view["dispatches"].append(repair)
    view["dispatches"].sort(key=lambda row: (row["arm"], row["task_id"],
                                             row["attempt"]))
    view["dispatch_count"] = len(view["dispatches"])
    view["physical_dispatch_count"] = len(view["dispatches"])
    view["automatic_retry_count"] = 1
    view["durable_receipts"] = [
        receipt for receipt in view["durable_receipts"]
        if receipt.get("operation_id") != repair["operation_id"]]

    private = json.loads((tmp_path / "scorer-private.json").read_text())
    problems = m4.verify_bundle(result, private)["problems"]
    assert "repair-after-accepted %s-%s" % (first["arm"], split) in problems


# `c7d2952` made the dispatch count an accounting record rather than a tally.
# It reports the file's count only when the store agrees with it, and
# "unknown" otherwise. A bundle whose sends never reached the store cannot
# claim a reconciled count, and saying so is the property.


def test_unreconciled_dispatch_count_is_reported_as_unknown():
    accounting = driver._output_dispatch_accounting(
        [{"operation_id": "a"}], store_count=0)

    assert accounting.state == "incomplete"
    fields = accounting.candidate_fields()
    assert fields["dispatch_count"] == "unknown"
    assert fields["physical_dispatch_count"] == "unknown"
    assert fields["dispatch_evidence"] == {
        "state": "incomplete",
        "store_operation_count": 0,
        "file_dispatch_count": 1,
        "file_physical_dispatch_count": 1,
    }


def test_reconciled_dispatch_count_reports_the_store_number():
    accounting = driver._output_dispatch_accounting(
        [{"operation_id": "a"}, {"operation_id": "b"},
         {"operation_id": "c", "replay": True}], store_count=2)

    assert accounting.state == "reconciled"
    fields = accounting.candidate_fields()
    assert fields["dispatch_count"] == 3
    assert fields["physical_dispatch_count"] == 2


# A lost response is a real send with no observable outcome. The guard has to
# record it, and the record has to carry no raw response.


def test_lost_response_is_recorded_as_a_dispatch_with_no_response(tmp_path):
    freeze = driver.freeze_output(tmp_path)
    operation_id = live.output_operation_id(
        "P1", "audit", int(live.OUTPUT_TASKS["audit"]), 1,
        round_run_id=freeze["run_id"])

    def timeout(_request):
        raise TimeoutError("response lost after provider send")

    gateway = _OutputGateway([], freeze["route"])
    gateway.infer = timeout
    guard = driver._OutputGuard(
        gateway,
        pinned_model=freeze["route"]["requested_model"],
        ceiling=freeze["limits"]["max_dispatches"],
        automatic_retries=freeze["limits"]["automatic_retries"],
        expected_route=freeze["route"],
    )
    task, session = driver._output_public_task("audit", 23)
    prompt = live.render_output_prompt(session.model_input(), [], 1)
    with pytest.raises(TimeoutError):
        guard.infer(
            ModelRequest(
                model=freeze["route"]["requested_model"],
                messages=({"role": "user", "content": prompt},),
                max_output_tokens=2048,
                deadline_ms=300_000,
                operation_id=operation_id,
            ),
            evidence={"arm": "P1", "task": task["task_id"], "attempt": 1,
                      "raw_prompt": prompt, "round": freeze["round"]},
        )

    recorded = guard.finalized_dispatches()
    assert [entry["operation_id"] for entry in recorded] == [operation_id]
    assert recorded[0]["raw_response"] is None
    assert recorded[0]["parse_outcome"] == "transport-error"


def _split_of(task_id):
    return next((split for split, seed in live.OUTPUT_TASKS.items()
                 if m4._task_id_for(split, seed) == task_id), None)
