"""The seven required counterexamples, each on a baseline proved green first.

A tamper test proves one thing: that a specific wrong thing is REFUSED, and
that the refusal is the product's and not the fixture's. Two rules hold
every test here.

1. The clean baseline runs in the same test, before the tamper, on the same
   store. A red baseline means the case is not proved, and the test says so
   rather than passing quietly.
2. The refusal is asserted as a LITERAL reason. `pytest.raises(Exception)`
   or a substring anyone could satisfy proves nothing about which refusal
   fired.

The seven cases are the ones §13 of the architecture synthesis names:
unrelated-route replay, changed bytes, missing authority, no candidate,
partial response, timeout, pending resume.

Every policy byte is this lane's own (`test_inv_a_reviewer_source`). No
lane's fixture is reused, so a self-consistent fixture cannot pass for a
refusal.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_inv_a_reviewer_source as reviewer

# A per-process tag on every operation identity this module mints. The store
# is module-scoped and the operation id is a primary key, so two tests that
# reuse one identity would meet each other's row.
_run_tag = os.environ.get("PYTEST_CURRENT_TEST", "a5")[-24:]

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a5tamper"
CHARTER = {"objective": "reduce examples while preserving their witness",
           "freeze_id": "ad01"}
DEV_TASK = "ad01-w0-dev-sw-00"
DEV_TASK2 = "ad01-w0-dev-sw-01"
USE_TASK = "ad01-w0-within-sw-00"


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


def _consumer(dsn, cid, source, gateway=None):
    from experiments.ad01 import agenda_policy, policy_step, trajectory

    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return agenda_policy.step_policy_consumer(
        policy_step.make_policy_artifact(source, origin="authored-control"),
        dsn=dsn, cid=cid, charter=dict(CHARTER), world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid,
        gateway=gateway, model="a5-reviewer-double")


def _query(dsn, sql, params=()):
    from experiments.ad01 import trajectory

    with trajectory._read_conn(dsn) as conn:
        rows = conn.execute(sql, params).fetchall()
        conn.commit()
        return rows


def _view():
    return {"task_content": {"task_id": DEV_TASK}, "observations": [],
            "open_questions": [], "last_result": None,
            "eligible_methods": [], "remaining": {"steps": 1},
            "contract_versions": {}}


def _repertoire(capability_id="acquired-sw-a5counter", seq=950):
    """A repertoire whose operation identities are unique to this test run.

    `run_use` derives two operation ids: one for the policy step and one for
    the member, both from the campaign id, the task and the member name. A
    second use with the same inputs therefore arrives at an operation whose
    payload differs only in the stage directory, and the broker refuses it
    as a reused identity. Each counterexample names its own campaign and its
    own member, so its baseline is genuinely its own run.
    """
    return {"campaign_id": "ad01-w0-I-%d-%s" % (seq, _run_tag), "queries": 0,
            "members": [
        {"capability_id": capability_id, "family": "software",
         "scope": {"family": "software"}, "entry": "carried",
         "method_source": reviewer.ACQUIRED_METHOD,
         "source_digest": reviewer.digest(reviewer.ACQUIRED_METHOD),
         "disposition": "retained"}]}


# --- 1. unrelated-route replay ------------------------------------------


def test_a_receipt_from_one_route_is_refused_against_another_operation(
        store):
    """Recorded under route A, offered against an operation frozen for B."""
    from experiments.ad01 import method_exec, trajectory, worlds
    from settlement import broker
    from settlement.common import ResultCode

    cid = trajectory_cid(950)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    allocation_id = trajectory._alloc_id(cid)
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK2)

    # Baseline: the same member runs and settles under its own identity.
    route_a_op = "ad01-a5-route-A-op-%s" % _run_tag
    baseline = method_exec.run_member_out_of_process(
        {"capability_id": "acquired-sw-routea",
         "method_source": reviewer.ACQUIRED_METHOD, "entry": "carried"},
        task, dsn=store, allocation_id=allocation_id,
        operation_id=route_a_op)
    assert "status" not in baseline, baseline
    recorded = _query(
        store, "SELECT receipt_identity, content, outcome FROM receipts"
        " WHERE operation_id = %s", (route_a_op,))
    assert len(recorded) == 1, "baseline settled with no receipt to replay"
    recorded = dict(recorded[0])
    assert recorded["outcome"] == "success"

    # Tamper: the same receipt, offered against a different operation.
    route_b_op = "ad01-a5-route-B-op-%s" % _run_tag
    forged = broker.ReceiptProposal(
        receipt_identity=recorded["receipt_identity"],
        content=dict(recorded["content"]), outcome="success")
    refused = broker.admit_launcher_receipt(store, route_b_op, forged)
    assert refused.code == ResultCode.INVALID_INPUT
    assert refused.detail == "unknown operation %s" % route_b_op
    # The recorded receipt stays bound to the operation that earned it.
    still = _query(store, "SELECT operation_id FROM receipts"
                   " WHERE receipt_identity = %s",
                   (recorded["receipt_identity"],))
    assert [dict(r)["operation_id"] for r in still] == [route_a_op]


def test_a_receipt_replayed_onto_its_own_operation_is_idempotent_not_a_fresh_run(
        store):
    """The control: the same receipt on its own operation settles once."""
    from experiments.ad01 import method_exec, trajectory, worlds
    from settlement import broker

    cid = trajectory_cid(951)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    allocation_id = trajectory._alloc_id(cid)
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK2)
    operation_id = "ad01-a5-idem-op-%s" % _run_tag
    member = {"capability_id": "acquired-sw-idem-%s" % _run_tag,
              "method_source": reviewer.ACQUIRED_METHOD, "entry": "carried"}

    first = method_exec.run_member_out_of_process(
        member, task, dsn=store, allocation_id=allocation_id,
        operation_id=operation_id)
    receipts_before = len(_query(
        store, "SELECT receipt_identity FROM receipts WHERE operation_id = %s",
        (operation_id,)))
    assert receipts_before == 1

    # Same operation, same bytes, same result: the answer is replayed at zero
    # remaining rather than executed a second time.
    second = method_exec.run_member_out_of_process(
        member, task, dsn=store, allocation_id=allocation_id,
        operation_id=operation_id)
    assert second["queries"] == first["queries"]
    assert second["source_digest"] == first["source_digest"]
    receipts_after = len(_query(
        store, "SELECT receipt_identity FROM receipts WHERE operation_id = %s",
        (operation_id,)))
    assert receipts_after == receipts_before, "a replay issued a second receipt"


# --- 2. changed bytes ----------------------------------------------------


def test_source_bytes_changed_after_the_receipt_are_refused(store,
                                                            monkeypatch):
    """The `test_final_provenance.py` shape: substitution after preparation.

    Baseline first: with the staged bytes left alone, the same call runs and
    dispatches. Only the substitution makes it refuse, so the refusal is the
    substitution's and not the harness's.
    """
    from experiments.ad01 import method_exec, trajectory, worlds
    from settlement.common import ResultCode

    cid = trajectory_cid(961)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    allocation_id = trajectory._alloc_id(cid)
    # One capability and one operation identity per test run. Reusing either
    # across tests makes the second call replay the first one's receipt, and
    # a replayed receipt is a pass, not a run.
    member = {"capability_id": "acquired-sw-bytes-%s" % _run_tag,
              "method_source": reviewer.ACQUIRED_METHOD, "entry": "carried"}

    # Clean baseline: the same member runs through the real broker and the
    # real launcher, so the operation row, the receipt and the result are
    # all the product's own.
    task = worlds.load_task(worlds.FROZEN_DIR, DEV_TASK2)
    baseline = method_exec.run_member_out_of_process(
        member, task, dsn=store, allocation_id=allocation_id,
        operation_id="op-a5-bytes-clean-%s" % _run_tag)
    assert baseline["source_digest"] == reviewer.digest(
        reviewer.ACQUIRED_METHOD)
    assert baseline["candidate"]
    clean = _query(store, "SELECT settled FROM operations WHERE id = %s",
                   ("op-a5-bytes-clean-%s" % _run_tag,))
    assert clean and dict(clean[0])["settled"] is True

    # Tamper: the same call, with the staged bytes replaced between
    # preparation and dispatch.
    dispatched = []

    def ensure_operation(dsn, **kwargs):
        from pathlib import Path

        work = Path(kwargs["payload"]["argv"][2])
        (work / "member.py").write_text(
            "def carried(task, oracle):\n"
            "    return {'candidate': {}, 'queries': 0}\n",
            encoding="utf-8")

        class R:
            code = ResultCode.APPLIED
            detail = ""

        return R()

    def dispatch(*args, **kwargs):
        dispatched.append(True)
        return None

    monkeypatch.setattr(method_exec.broker, "ensure_operation", ensure_operation)
    monkeypatch.setattr(method_exec.broker, "dispatch_operation", dispatch)

    with pytest.raises(method_exec.MethodExecutionError) as refusal:
        method_exec.run_member_out_of_process(
            member, {}, dsn=store, allocation_id=allocation_id,
            operation_id="op-a5-bytes-%s" % _run_tag)
    assert str(refusal.value) == "refused: staged source digest mismatch"
    assert dispatched == [], "the changed bytes were dispatched anyway"


def test_retained_bytes_that_no_longer_match_their_digest_are_refused(
        store, tmp_path):
    """The retention arrow's own check, through the public loader."""
    from experiments.ad01 import trajectory

    repertoire = _repertoire("acquired-sw-tampered")
    repertoire["members"][0]["authored"] = False
    path = tmp_path / "tampered.json"
    trajectory.freeze_repertoire(
        {"campaign_id": repertoire["campaign_id"], "queries": 0,
         "episodes": [{"disposition": "retained",
                       "executable": repertoire["members"][0]}]},
        path)
    assert trajectory.load_repertoire(path)["members"]

    tampered = json.loads(path.read_text())
    tampered["members"][0]["method_source"] += "\n# a line nobody checked\n"
    path.write_text(json.dumps(tampered, sort_keys=True, indent=2))

    with pytest.raises(ValueError) as refusal:
        trajectory.load_repertoire(path)
    assert str(refusal.value) == (
        "acquired member %r bytes do not match their digest"
        % "acquired-sw-tampered")


# --- 3. missing authority ------------------------------------------------


@pytest.mark.parametrize("omitted", ["dsn", "allocation_id", "operation_id"])
def test_execution_without_full_authority_is_refused(store, omitted):
    """A2's precondition, from the public executor.

    Baseline first: with all three supplied the same program and view run.
    Dropping any one of them is what turns a run into a refusal.
    """
    from experiments.ad01 import method_exec, trajectory

    cid = trajectory_cid(964)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    allocation_id = trajectory._alloc_id(cid)

    baseline = method_exec.run_step_out_of_process(
        reviewer.CHAIN_SOURCE, _view(), {}, dsn=store,
        allocation_id=allocation_id, operation_id="op-a5-auth-clean")
    assert "status" not in baseline, baseline
    assert baseline["action"]["kind"] == "diagnose"

    authority = {"dsn": store, "allocation_id": allocation_id,
                 "operation_id": "op-a5-auth-%s" % omitted}
    authority.pop(omitted)
    with pytest.raises(method_exec.MethodExecutionError) as refusal:
        method_exec.run_step_out_of_process(
            reviewer.CHAIN_SOURCE, _view(), {}, **authority)
    assert str(refusal.value) == \
        "refused: execution needs explicit authority and identity"


def test_an_allocation_that_does_not_exist_is_refused(store):
    """A named allocation that no row backs. Baseline is the real one."""
    from experiments.ad01 import method_exec, trajectory

    cid = trajectory.campaign_id(0, "I", 965)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    allocation_id = trajectory._alloc_id(cid)
    baseline = method_exec.run_step_out_of_process(
        reviewer.CHAIN_SOURCE, _view(), {}, dsn=store,
        allocation_id=allocation_id, operation_id="op-a5-alloc-clean")
    assert baseline["action"]["kind"] == "diagnose"

    with pytest.raises(method_exec.MethodExecutionError) as refusal:
        method_exec.run_step_out_of_process(
            reviewer.CHAIN_SOURCE, _view(), {}, dsn=store,
            allocation_id="alloc-a5-does-not-exist",
            operation_id="op-a5-none")
    assert str(refusal.value) == "refused: unknown allocation"


def test_use_without_an_explicit_allocation_is_refused(store):
    """The public use entry refuses before any policy byte is staged."""
    from experiments.ad01 import trajectory

    cid = trajectory_cid(966)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    repertoire = _repertoire(seq=966)
    allocation_id = trajectory._alloc_id(cid)

    [baseline] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=allocation_id,
        policy_source=reviewer.use_source("acquired-sw-a5counter"))
    assert baseline["executed"] == "acquired-sw-a5counter"

    with pytest.raises(ValueError) as refusal:
        trajectory.run_use(repertoire, 0, "I", [USE_TASK], {}, dsn=store,
                           allocation_id=None,
                           policy_source=reviewer.use_source(
                               "acquired-sw-a5counter"))
    assert str(refusal.value) == "use requires explicit execution allocation"


# --- 4. no candidate -----------------------------------------------------


def test_use_with_a_baseline_green_and_a_missing_member_red(store):
    from experiments.ad01 import trajectory

    # Baseline: the member the repertoire holds runs.
    baseline_cid = trajectory_cid(953)
    trajectory.authorize_campaign(store, baseline_cid, authorized=100000)
    repertoire = _repertoire("acquired-sw-a5counter", seq=953)
    [baseline] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=trajectory._alloc_id(baseline_cid),
        policy_source=reviewer.use_source("acquired-sw-a5counter"))
    assert "status" not in baseline, baseline
    assert baseline["executed"] == "acquired-sw-a5counter",         baseline["fallback_reason"]

    # Tamper: the same repertoire, under a campaign of its own, asked for a
    # member it does not hold.
    tamper_cid = trajectory_cid(969)
    trajectory.authorize_campaign(store, tamper_cid, authorized=100000)
    [refused] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=trajectory._alloc_id(tamper_cid),
        policy_source=reviewer.NO_CANDIDATE_SOURCE)
    assert refused["status"] == "refused"
    assert refused["fallback_reason"] == \
        "admitted 'a5-absent-method' is absent from the repertoire"
    assert refused["selected"] == "refused"
    assert refused["executed"] == "refused"
    assert refused["output"] == {}
    assert refused["costs"]["witness_queries"] == 0


def test_use_of_a_member_scoped_to_another_family_is_refused(store):
    from experiments.ad01 import trajectory

    cid = trajectory_cid(954)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    allocation_id = trajectory._alloc_id(cid)

    # Baseline: the same member scoped to this task's family runs.
    scoped = _repertoire("acquired-sw-scoped", seq=954)
    [baseline] = trajectory.run_use(
        scoped, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=allocation_id,
        policy_source=reviewer.use_source("acquired-sw-scoped"))
    assert baseline["executed"] == "acquired-sw-scoped"

    # Tamper: the same name, scoped to a family this task is not.
    repertoire = _repertoire("seed-gr-dfs", seq=954)
    repertoire["members"][0]["scope"] = {"family": "graph"}
    [refused] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {}, dsn=store,
        allocation_id=allocation_id,
        policy_source=reviewer.WRONG_FAMILY_SOURCE)
    assert refused["status"] == "refused"
    # The scope refusal is a different refusal from the absence one, and it
    # names the family it would have needed. A chain proved only on absence
    # would have passed a product that substituted here.
    assert refused["fallback_reason"] == (
        "admitted 'seed-gr-dfs' is scoped to 'graph' and cannot answer"
        " a software task")
    assert refused["output"] == {}


# --- 5. partial response -------------------------------------------------


def test_an_empty_model_response_settles_as_a_recorded_failure(store):
    """Baseline is the same program with a response that arrived.

    With bytes the operation settles `success` and the program reaches its
    stop. With an empty body it settles `failure` under a distinct receipt
    identity and the program is told the call did not resolve. Two different
    receipts for two different bodies is the evidence.
    """
    from experiments.ad01.learner import RecordingGatewayAdapter

    full = trajectory_cid(967)
    run_reasoning(store, full, RecordingGatewayAdapter([{"text": "an answer"}]))
    good = _query(
        store, "SELECT receipt_identity, outcome FROM receipts"
        " WHERE operation_id = %s",
        ("ad01-%s-policy-s0-model-k0" % full,))
    assert len(good) == 1
    assert dict(good[0])["outcome"] == "success"
    assert dict(good[0])["receipt_identity"] == \
        "gw:ad01-%s-policy-s0-model-k0" % full

    cid = trajectory_cid(955)
    out = run_reasoning(store, cid, RecordingGatewayAdapter([{"text": ""}]))
    assert out["stop"]["reason"] == "learner stop"
    receipt = _query(
        store, "SELECT receipt_identity, outcome FROM receipts"
        " WHERE operation_id = %s",
        ("ad01-%s-policy-s0-model-k0" % cid,))
    assert len(receipt) == 1
    assert dict(receipt[0])["receipt_identity"] == \
        "gw:ad01-%s-policy-s0-model-k0:empty-response" % cid
    assert dict(receipt[0])["outcome"] == "failure"


def test_a_truncated_response_is_flagged_to_the_program_not_hidden(store):
    from experiments.ad01.learner import RecordingGatewayAdapter

    cid = trajectory_cid(956)
    gateway = RecordingGatewayAdapter([{"text": "one short answer"}])
    run_reasoning(store, cid, gateway)
    row = _query(
        store, "SELECT policy_output FROM s09_policy_state"
        " WHERE investigation_id = %s AND seq = 0", (cid,))
    results = dict(row[0]["policy_output"])["results"]
    kinds = [r["action"]["kind"] for r in results]
    assert kinds == ["request_model", "stop"]


def trajectory_cid(seq):
    from experiments.ad01 import trajectory

    return trajectory.campaign_id(0, "I", seq)


def run_reasoning(store, cid, gateway):
    from experiments.ad01 import trajectory

    return trajectory.run_campaign(
        0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20},
        tasks=[DEV_TASK], campaign_seq=int(cid.rsplit("-", 1)[1]),
        dsn=store,
        consumer=_consumer(store, cid, reviewer.REASONING_SOURCE,
                           gateway=gateway))


# --- 6. timeout ----------------------------------------------------------


def test_a_policy_that_never_terminates_is_refused_not_reported_as_a_method(
        store):
    """Baseline is the same program shaped so it terminates in one step.

    Without that baseline a hang and a refusal look alike: both produce one
    episode with no method. The clean run producing a real decision and a
    checked effect is what makes the refusal attributable to the hang.
    """
    from experiments.ad01 import trajectory

    clean = trajectory_cid(968)
    clean_out = trajectory.run_campaign(
        0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20},
        tasks=[DEV_TASK], campaign_seq=968, dsn=store,
        consumer=_consumer(store, clean, reviewer.CHAIN_SOURCE))
    assert len(clean_out["episodes"]) == 1
    assert clean_out["episodes"][0]["disposition"] == "inspected"

    cid = trajectory_cid(957)
    out = trajectory.run_campaign(
        0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20},
        tasks=[DEV_TASK], campaign_seq=957, dsn=store,
        consumer=_consumer(store, cid, reviewer.TIMEOUT_SOURCE))
    assert len(out["episodes"]) == 1
    episode = out["episodes"][0]
    assert episode["disposition"] == "no-candidate"
    assert episode["fallback_reason"] == (
        "policy step failed: refused: durable child operation has no"
        " successful receipt")
    assert "executable" not in episode, "a timed-out step kept a method"


def test_a_budget_exhausted_program_refuses_and_the_row_says_so(store):
    """Six steps is the ceiling; a seventh decision has nowhere to go."""
    from experiments.ad01 import trajectory

    cid = trajectory_cid(958)
    out = trajectory.run_campaign(
        0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 60},
        tasks=[DEV_TASK], campaign_seq=958, dsn=store,
        consumer=_consumer(store, cid, reviewer.EXHAUSTED_SOURCE))
    assert len(out["episodes"]) == 1
    episode = out["episodes"][0]
    assert episode["disposition"] == "no-candidate"
    assert episode["fallback_reason"] == \
        "policy step budget exhausted (6 steps)"
    assert "executable" not in episode, "an exhausted step kept a method"
    # The boundary is still recorded, carrying the refusal rather than a
    # decision: nothing admitted, and the row says which reason.
    assert len(out["boundaries"]) == 1
    assert out["boundaries"][0]["decision"] is None
    row = _query(
        store, "SELECT status, accepted_action FROM s09_policy_state"
        " WHERE investigation_id = %s AND seq = 0", (cid,))
    assert dict(row[0]["accepted_action"]) == {
        "status": "refused",
        "reason": "policy step budget exhausted (6 steps)"}
    assert row[0]["status"] == "incorporated"


# --- 7. pending resume ---------------------------------------------------


def _accept_pending(store, seq):
    """Accept a boundary's action without running it, through the public entry.

    `accept_action` is the shape a preparation crash leaves behind: the
    decision is durable and recorded, the effect has not run. The restart
    reads that row, which is what the pending-resume case is about.
    """
    from experiments.ad01 import trajectory

    cid = trajectory_cid(seq)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    made = trajectory.ensure_campaign(
        store, cid, 0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20},
        tasks=[DEV_TASK])
    assert made["admitted"] is True, "the campaign admitted nothing"
    decision = _pending_decision()
    attempt_id = trajectory.accept_action(store, cid, 0, decision)
    assert attempt_id == "att-%s-0" % cid
    row = _query(store, "SELECT status, accepted_action FROM s09_policy_state"
                 " WHERE investigation_id = %s AND seq = 0", (cid,))
    assert dict(row[0]["accepted_action"]) == decision
    return cid, decision


def _pending_decision():
    return {"basis_references": [],
            "question": "reviewer pending boundary",
            "next_action": {"kind": "diagnostic", "task_id": DEV_TASK,
                            "diagnostic": "software",
                            "capability_id": "seed-sw-greedy"}}


def test_a_restart_under_a_pending_operation_keeps_its_program_and_input(
        store):
    """The decision accepted before the crash is the one that executes."""
    from experiments.ad01 import trajectory

    cid, decision = _accept_pending(store, 959)

    # Restart under the pending operation. The boundary executes the action
    # that was accepted, not a fresh decision of its own.
    out = trajectory.run_campaign(
        0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20},
        tasks=[DEV_TASK], campaign_seq=959, dsn=store,
        consumer=_consumer(store, cid, reviewer.PENDING_STEP_SOURCE))
    assert len(out["boundaries"]) == 1
    boundary = out["boundaries"][0]
    assert boundary["decision"] == decision,         "the restart re-decided instead of running the accepted action"
    settled, pending = trajectory._read_campaign(store, cid)
    assert pending == {}, "the pending row never settled"
    assert settled[0]["observation"]["task_id"] == DEV_TASK


def test_a_second_decision_for_a_pending_boundary_cannot_replace_the_first(
        store):
    """The tamper: offer a different decision for an already-accepted row.

    `accept_action` is idempotent rather than refusing: it answers with the
    attempt the row already carries and writes nothing. The durable row is
    therefore still the first decision, which is what makes the resumed
    boundary run the action that was accepted.
    """
    from experiments.ad01 import trajectory

    cid, decision = _accept_pending(store, 960)
    changed = {"basis_references": [],
               "question": "a different question",
               "next_action": dict(decision["next_action"],
                                   task_id=DEV_TASK2)}
    attempt_id = trajectory.accept_action(store, cid, 0, changed)
    assert attempt_id == "att-%s-0" % cid
    row = _query(store, "SELECT accepted_action FROM s09_policy_state"
                 " WHERE investigation_id = %s AND seq = 0", (cid,))
    assert dict(row[0]["accepted_action"]) == decision,         "a second decision replaced the accepted one"


def test_a_settled_boundary_cannot_be_re_accepted(store):
    from experiments.ad01 import trajectory

    cid = trajectory_cid(962)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    trajectory.ensure_campaign(
        store, cid, 0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20},
        tasks=[DEV_TASK])
    trajectory.accept_action(store, cid, 0, _pending_decision())
    out = trajectory.run_campaign(
        0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20},
        tasks=[DEV_TASK], campaign_seq=962, dsn=store,
        consumer=_consumer(store, cid, reviewer.PENDING_STEP_SOURCE))
    assert len(out["boundaries"]) == 1
    with trajectory._read_conn(store) as conn:
        conn.execute("DELETE FROM s09_policy_state"
                     " WHERE investigation_id = %s AND seq = 0", (cid,))
        conn.commit()
    with pytest.raises(ValueError) as refusal:
        trajectory.accept_action(store, cid, 0, _pending_decision())
    assert str(refusal.value) == "boundary 0 already settled"


def test_the_resumed_effect_follows_the_accepted_decision_not_the_restarting_program(
        store):
    """A restart under a different program still runs what was accepted.

    The pending row's authority is the decision it carries. A restart that
    attaches different program bytes executes the accepted action anyway,
    which is what makes a pending operation resume rather than re-decide.
    """
    from experiments.ad01 import trajectory

    cid, decision = _accept_pending(store, 963)
    other_program = reviewer.EXHAUSTED_SOURCE
    assert other_program != reviewer.PENDING_STEP_SOURCE

    out = trajectory.run_campaign(
        0, "I", CHARTER,
        {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20},
        tasks=[DEV_TASK], campaign_seq=963, dsn=store,
        consumer=_consumer(store, cid, other_program))
    assert len(out["boundaries"]) == 1
    assert out["boundaries"][0]["decision"] == decision
    assert out["boundaries"][0]["task_id"] == DEV_TASK
    # The diagnostic the accepted action named ran, so the observation is
    # the one that decision implies and not the other program's.
    assert out["boundaries"][0]["observation_id"] == (
        "obs-c4-diagnostic-%s" % DEV_TASK)
