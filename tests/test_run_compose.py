from __future__ import annotations

import uuid

import pytest

from settlement import run, store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _setup(dsn):
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 1000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    acquired = store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    return acquired.data["ownership_generation"]


def _invoke(node_id, effect="sandbox-exec", payload=None):
    payload = payload or {"profile": "local-process", "argv": ["/bin/true"],
                          "timeout_ms": 1_000, "max_output_bytes": 64}
    return {"kind": "invoke", "node_id": node_id, "effect": effect, "payload": payload}


def test_sequence_advances_through_recorded_completions():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1, "allocation_id": "a1", "authority_version": 1,
        "root": {"kind": "sequence", "node_id": "sq1",
                 "steps": [_invoke("n1"), _invoke("n2")]}})
    cont = run.fresh_continuation(comp, "att1")
    assert cont.next == {"decision": "invoke", "detail": "n1"}
    assert cont.position == ["sq1", "n1"]
    assert set(cont.model_dump()) == {"attempt_id", "composition_version", "composition_revision",
                                      "position", "completed", "observations", "unresolved_ops",
                                      "obligations", "next"}
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "n1",
                                    "result_ref": "rc-n1"})
    assert cont.next == {"decision": "invoke", "detail": "n2"}
    assert cont.completed == {"n1": "rc-n1"}
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "n2",
                                    "result_ref": "rc-n2"})
    assert cont.next == {"decision": "done", "detail": "sequence-complete"}
    assert cont.position == ["sq1"]


def test_choice_branches_on_recorded_observation():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1,
        "root": {"kind": "choice", "node_id": "ch1", "on": "temp", "equals": "high",
                 "then": _invoke("n_hot"), "otherwise": _invoke("n_cold")}})
    cont = run.fresh_continuation(comp, "att1")
    assert cont.next == {"decision": "await-observation", "detail": "temp"}
    cont = run.advance(comp, cont, {"type": "observation", "key": "temp", "value": "low"})
    assert cont.next == {"decision": "invoke", "detail": "n_cold"}
    assert cont.position == ["ch1", "n_cold"]
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "n_cold",
                                    "result_ref": "rc"})
    assert cont.next["decision"] == "done"


def test_repeat_bounds_iterations_and_honors_stop_flag():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1,
        "root": {"kind": "repeat", "node_id": "rp1", "body": _invoke("wk"),
                 "max_iterations": 2, "until": "done_flag"}})
    cont = run.fresh_continuation(comp, "att1")
    assert cont.next == {"decision": "invoke", "detail": "wk"}
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "wk",
                                    "result_ref": "r1"})
    assert cont.next == {"decision": "invoke", "detail": "wk"}
    cont = run.advance(comp, cont, {"type": "observation", "key": "done_flag", "value": True})
    assert cont.next == {"decision": "done", "detail": "repeat-until"}
    cont2 = run.fresh_continuation(comp, "att1")
    cont2 = run.advance(comp, cont2, {"type": "node_completed", "node_id": "wk",
                                      "result_ref": "r1"})
    cont2 = run.advance(comp, cont2, {"type": "node_completed", "node_id": "wk",
                                      "result_ref": "r2"})
    assert cont2.next == {"decision": "done", "detail": "repeat-exhausted"}


def test_parallel_tracks_each_alternative():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1,
        "root": {"kind": "parallel", "node_id": "par1",
                 "branches": [_invoke("b1"), _invoke("b2")]}})
    cont = run.fresh_continuation(comp, "att1")
    assert cont.next == {"decision": "fork", "detail": ["b1", "b2"]}
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "b1",
                                    "result_ref": "r1"})
    assert cont.next == {"decision": "fork", "detail": ["b2"]}
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "b2",
                                    "result_ref": "r2"})
    assert cont.next["decision"] == "done"


def test_join_names_unsatisfied_obligations():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1,
        "root": {"kind": "join", "node_id": "j1", "needs": {"o1": "n1", "o2": "n2"}}})
    cont = run.fresh_continuation(comp, "att1")
    assert cont.next == {"decision": "await-join", "detail": ["o1", "o2"]}
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "n1",
                                    "result_ref": "r1"})
    assert cont.next == {"decision": "await-join", "detail": ["o2"]}
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "n2",
                                    "result_ref": "r2"})
    assert cont.next == {"decision": "done", "detail": "join-satisfied"}


def test_suspend_waits_for_named_observation():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1,
        "root": {"kind": "suspend", "node_id": "s1", "pending_observation": "human"}})
    cont = run.fresh_continuation(comp, "att1")
    assert cont.next == {"decision": "await-observation", "detail": "human"}
    cont = run.advance(comp, cont, {"type": "observation", "key": "human", "value": "go"})
    assert cont.next == {"decision": "done", "detail": "suspend-released"}


def test_pending_invokes_skip_completed_and_unresolved():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1,
        "root": {"kind": "sequence", "node_id": "sq1",
                 "steps": [_invoke("n1"), _invoke("n2")]}})
    cont = run.fresh_continuation(comp, "att1")
    assert [n.node_id for n in run.pending_invokes(comp, cont)] == ["n1"]
    cont = run.advance(comp, cont, {"type": "node_completed", "node_id": "n1",
                                    "result_ref": "r1"})
    cont = run.register_ops(comp, cont, {"n2": "op-9"})
    assert run.pending_invokes(comp, cont) == []
    assert cont.unresolved_ops == ["n2:op-9"]
    assert cont.next == {"decision": "awaiting-op", "detail": "n2:op-9"}


def test_completion_for_unknown_node_rejected():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1, "root": _invoke("n1")})
    cont = run.fresh_continuation(comp, "att1")
    with pytest.raises(run.InvalidComposition):
        run.advance(comp, cont, {"type": "node_completed", "node_id": "ghost",
                                 "result_ref": "r"})


def test_revise_rejects_unknown_ops_and_generated_python():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1, "allocation_id": "a1", "authority_version": 1,
        "budget": {"units": 100}, "root": _invoke("n1")})
    with pytest.raises(run.InvalidComposition):
        run.revise(comp, _invoke("n2", effect="telepathy", payload={}))
    with pytest.raises(run.InvalidComposition):
        run.revise(comp, {"kind": "python", "node_id": "evil", "code": "import os"})
    with pytest.raises(run.InvalidComposition):
        run.revise(comp, {"kind": "invoke", "node_id": "evil", "effect": "sandbox-exec",
                          "payload": {"profile": "local-process", "argv": ["x"],
                                      "exec": "import os"}})
    deep = _invoke("leaf")
    for depth in range(6):
        deep = {"kind": "sequence", "node_id": f"sq{depth}", "steps": [deep]}
    with pytest.raises(run.InvalidComposition):
        run.revise(comp, deep)


def test_revise_inherits_allocation_authority_without_new_quota():
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1, "allocation_id": "a1", "authority_version": 1,
        "budget": {"units": 100}, "root": _invoke("n1")})
    nxt = run.revise(comp, {"kind": "sequence", "node_id": "sq9",
                            "steps": [_invoke("n1"), _invoke("n2")]})
    assert nxt.revision == 2 and nxt.version == "run/v1"
    assert nxt.allocation_id == "a1" and nxt.authority_version == 1
    assert nxt.budget == {"units": 100}


def test_eligibility_tracks_authority_and_lifecycle(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1, "authority_version": 1, "root": _invoke("n1")})
    assert run.check_eligibility(dsn, "att1", comp)["eligible"] is True
    store.seed_grant(dsn, _cmd({"version": 2, "charter_text": "c2"}))
    assert run.check_eligibility(dsn, "att1", comp)["eligible"] is False
    comp2 = run.Composition.model_validate({
        "version": "run/v1", "revision": 1, "authority_version": 2, "root": _invoke("n1")})
    assert run.check_eligibility(dsn, "att1", comp2)["eligible"] is True
    store.complete_attempt(dsn, _cmd({"attempt_id": "att1", "ownership_generation": gen,
                                      "outcome": "completed"}))
    assert run.check_eligibility(dsn, "att1", comp2)["eligible"] is False


def test_migration_records_old_and_new_continuations(migrated_db):
    dsn = migrated_db
    gen = _setup(dsn)
    comp = run.Composition.model_validate({
        "version": "run/v1", "revision": 1, "root": _invoke("n1")})
    cont = run.fresh_continuation(comp, "att1")
    result = run.record_continuation(dsn, "att1", cont, "ref-1", gen)
    assert result.code == ResultCode.APPLIED
    nxt = run.revise(comp, {"kind": "sequence", "node_id": "sq9",
                            "steps": [_invoke("n1"), _invoke("n2")]})
    cont2 = run.fresh_continuation(nxt, "att1")
    migrated = run.migrate_continuation(dsn, "att1", "ref-1", cont2, gen)
    assert migrated.code == ResultCode.APPLIED
    from settlement import db as _db
    from psycopg.rows import dict_row

    with _db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT continuation_ref FROM attempts WHERE id = 'att1'")
            stored = cur.fetchone()["continuation_ref"]
            conn.commit()
    assert "ref-1" in stored and "sq9" in stored


def test_invoke_maps_to_broker_arguments():
    node = run.InvokeNode.model_validate(_invoke("n7"))
    args = run.invoke_to_broker_args(node, attempt_id="att1", allocation_id="a1")
    assert args == {"operation_id": "att1:n7", "effect": "sandbox-exec",
                    "payload": node.payload, "allocation_id": "a1",
                    "attempt_id": "att1", "execution_version": "run/v1"}
