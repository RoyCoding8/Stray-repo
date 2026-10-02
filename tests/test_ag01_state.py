from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.agenda01 import launcher as _launcher
from settlement import agenda, broker, db, store
from settlement.common import Command, ResultCode

TRAJ = "state-traj"
ROOT_ID = "agenda-root"
INV = f"ag01-inv-{TRAJ}"
POLICY = "AG01-TEST-1"
DIGEST = "digest-test"
PLAN = [{"prop": "p", "scope": "transfer", "dep": "dep-seed"}]


def _ok(result, what):
    assert result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED), (what, result)
    return result


def _grant(dsn, root=ROOT_ID, authorized=64):
    _ok(store.seed_grant(
        dsn, Command(request_id=f"ag01-test-grant-{root}",
                     payload={"version": 1, "charter_text": "agenda01 state test",
                              "authority_grant": {}, "envelopes": {}})), "seed grant")
    _ok(store.seed_allocation(
        dsn, Command(request_id=f"ag01-test-seed-{root}",
                     payload={"allocation_id": root, "domain": "agenda01",
                              "authorized": authorized, "max_occupancy": 8})), "seed root")
    _ok(store.admit_commitment(
        dsn, Command(request_id=f"ag01-test-inv-{TRAJ}-{root}",
                     payload={"investigation_id": INV,
                              "objective": "agenda01 state test",
                              "scope": {"trajectory": TRAJ},
                              "obligations": {"tasks": 1},
                              "sponsor": "agenda01-test",
                              "origin": "test-setup"})), "admit investigation")


def _propose(dsn, key="q-1", rev=1, expected=None, body=None, rid=None,
             root=ROOT_ID, grant=True):
    if grant:
        _grant(dsn, root=root)
    return agenda.propose_option(
        dsn, Command(request_id=rid or f"ag01-propose-{key}-r{rev}",
                     expected_revision=expected,
                     payload={"option_key": key, "scope": "transfer", "question": "q?",
                              "revision": rev, "allocation_root": root, "body": body or {}}))


def _admit(dsn, key="q-1", probe="probe-a", decision="do-a", deps=None, cost=4,
           rid=None, slot=None, policy=POLICY, digest=DIGEST, plan=None,
           due=None, expected_rev=None):
    payload = {"trajectory": TRAJ, "option_id": key, "probe": probe,
               "intended_decision": decision, "replication_slot": slot,
               "policy_version": policy, "input_digest": digest,
               "evidence_refs": [], "dep_versions": deps or {"dep-seed": 3},
               "observed_plan": plan if plan is not None else [],
               "cost": cost}
    if due is not None:
        payload["due_epoch"] = due
    if expected_rev is not None:
        payload["expected_option_revision"] = expected_rev
    return agenda.select_and_admit(
        dsn, Command(request_id=rid or f"ag01-admit-{key}-{probe}", payload=payload))


def _sim(dsn, values=None, claims=None):
    table = dict(values or {})
    claimed = dict(claims or {})
    return _launcher.AgendaProbeLauncher(
        dsn,
        observe=lambda probe, sample, prop: table.get(prop, True),
        claim=lambda prop: claimed.get(prop, True))


def _dispatch(dsn, sim, operation_id, props=("p",)):
    status = broker.dispatch_operation(
        dsn, operation_id, launchers={_launcher.ADAPTER_KEY: sim})
    assert status.sent_this_call or status.dispatch_state in ("observed", "unresolved"), status
    got = sim.read_result(operation_id) or {}
    for prop in props:
        assert prop in got, (operation_id, got)
    return status


def _receipt(sim, operation_id, prop="p"):
    return sim.read_result(operation_id)[prop]["receipt"]


def _record(dsn, key, attempt, receipt, scored=True, tag=None):
    request_id = f"ag01-observe-{receipt}" + (f"-{tag}" if tag else "")
    return agenda.record_outcome(
        dsn, Command(request_id=request_id,
                     payload={"option_id": key, "attempt_id": attempt,
                              "receipt_identity": receipt, "scored": scored}))


def _continue(dsn, key, parent, cites, probe, residual, cons, cost=2, rid=None,
              slot=None, policy=POLICY, digest=DIGEST, plan=None):
    return agenda.submit_continuation(
        dsn, Command(request_id=rid or f"ag01-cont-{key}-{probe}",
                     payload={"option_id": key, "parent_attempt": parent,
                              "observation_refs": cites, "next_probe": probe,
                              "intended_decision": f"do-{probe}",
                              "residual_question": residual, "consequences": cons,
                              "policy_version": policy, "input_digest": digest,
                              "replication_slot": slot, "cost": cost,
                              "observed_plan": plan if plan is not None else []}))


def test_propose_replay_and_conflict(migrated_db):
    first = _propose(migrated_db)
    assert first.code == ResultCode.APPLIED
    assert first.data["disposition"] == "open"
    assert first.data["disposition_version"] == 1
    replay = _propose(migrated_db)
    assert replay.code == ResultCode.ALREADY_APPLIED
    clash = _propose(migrated_db, rid="ag01-propose-q-1-r1-other")
    assert clash.code == ResultCode.STALE_REVISION


def test_propose_unknown_root_refused(migrated_db):
    bad = _propose(migrated_db, root="no-such-root", grant=False,
                   rid="ag01-propose-q-1-r1-noroot")
    assert bad.code == ResultCode.INVALID_INPUT
    assert "unknown allocation root" in bad.detail


def test_propose_stale_expected_and_revision_bump(migrated_db):
    _propose(migrated_db)
    stale = _propose(migrated_db, rev=1, expected=0, rid="ag01-propose-q-1-r1-stale")
    assert stale.code == ResultCode.STALE_REVISION
    second = _propose(migrated_db, rev=2, expected=1, rid="ag01-propose-q-1-r2")
    assert second.code == ResultCode.APPLIED
    assert second.data["revision"] == 2
    with db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM agenda_option_revisions WHERE option_id = 'q-1'")
            assert cur.fetchone()[0] == 2
        conn.commit()


def test_admit_duplicate_slot_single_effect(migrated_db):
    _propose(migrated_db)
    admitted = _admit(migrated_db)
    assert admitted.code == ResultCode.APPLIED
    assert admitted.data["attempt_id"] == "att-q-1-probe-a"
    dup = _admit(migrated_db, rid="ag01-admit-q-1-probe-a-retry")
    assert dup.code == ResultCode.ALREADY_APPLIED
    assert dup.data["attempt_id"] == "att-q-1-probe-a"
    assert dup.data["dec_op"], "a new duplicate-effect decision is charged"
    with db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM agenda_attempt_links")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT COUNT(*) FROM reservations")
            assert cur.fetchone()[0] == 3
        conn.commit()


def test_admit_binds_policy_digest_revision(migrated_db):
    _propose(migrated_db)
    admitted = _admit(migrated_db)
    assert admitted.code == ResultCode.APPLIED
    with db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT policy_version, selection FROM agenda_decisions"
                        " WHERE trajectory = %s", (TRAJ,))
            row = cur.fetchone()
            assert row[0] == POLICY
            assert row[1]["input_digest"] == DIGEST
            assert row[1]["option_revision"] == 1
            cur.execute("SELECT allocation_id, lifecycle FROM attempts WHERE id = %s",
                        (admitted.data["attempt_id"],))
            attempt = cur.fetchone()
            assert attempt[0] == ROOT_ID
            assert attempt[1] == "running"
        conn.commit()


def test_admit_stale_revision_refused(migrated_db):
    _propose(migrated_db)
    _propose(migrated_db, rev=2, expected=1, rid="ag01-propose-q-1-r2")
    stale = _admit(migrated_db, expected_rev=1, rid="ag01-admit-q-1-probe-a-stale")
    assert stale.code == ResultCode.STALE_REVISION


def test_concurrent_admit_one_effect(migrated_db):
    _propose(migrated_db)
    results = []
    def worker(i):
        results.append(_admit(migrated_db, rid=f"ag01-admit-race-{i}"))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    codes = [r.code for r in results]
    assert codes.count(ResultCode.APPLIED) == 1
    assert codes.count(ResultCode.ALREADY_APPLIED) == 7
    assert {r.data["attempt_id"] for r in results} == {"att-q-1-probe-a"}


def test_outcome_links_durable_receipt_only(migrated_db):
    _propose(migrated_db)
    admitted = _admit(migrated_db, plan=PLAN)
    assert admitted.code == ResultCode.APPLIED
    attempt, op = admitted.data["attempt_id"], admitted.data["operation_id"]
    sim = _sim(migrated_db, {"p": True})
    _dispatch(migrated_db, sim, op)
    seen = _record(migrated_db, "q-1", attempt, _receipt(sim, op))
    assert seen.code == ResultCode.APPLIED
    assert seen.data["settled_probe"] == op
    forged = _record(migrated_db, "q-1", attempt, "rc-forged")
    assert forged.code == ResultCode.INVALID_INPUT
    assert "unknown receipt" in forged.detail
    probe_b = _admit(migrated_db, probe="probe-b", decision="do-b",
                     rid="ag01-admit-q-1-probe-b", plan=PLAN)
    assert probe_b.code == ResultCode.APPLIED
    attempt_b, op_b = probe_b.data["attempt_id"], probe_b.data["operation_id"]
    sim2 = _sim(migrated_db, {"p": None})
    _dispatch(migrated_db, sim2, op_b)
    unknown = _record(migrated_db, "q-1", attempt_b, _receipt(sim2, op_b))
    assert unknown.code == ResultCode.APPLIED
    assert unknown.data["settled_probe"] is None
    snap = agenda.agenda_snapshot(migrated_db)
    assert snap["liability"] == 4
    assert snap["remaining"] == 64 - 2 - 4 - 4


def test_outcome_refusals(migrated_db):
    _propose(migrated_db)
    first = _admit(migrated_db, plan=PLAN)
    op_a = first.data["operation_id"]
    second = _admit(migrated_db, probe="probe-b", decision="do-b",
                    rid="ag01-admit-q-1-probe-b", plan=PLAN)
    attempt_b, op_b = second.data["attempt_id"], second.data["operation_id"]
    sim = _sim(migrated_db, {"p": True})
    _dispatch(migrated_db, sim, op_a)
    receipt_a = _receipt(sim, op_a)
    wrong = _record(migrated_db, "q-1", attempt_b, receipt_a)
    assert wrong.code == ResultCode.INVALID_INPUT
    assert "wrong operation" in wrong.detail
    _dispatch(migrated_db, sim, op_b)
    receipt_b = _receipt(sim, op_b)
    replay = _record(migrated_db, "q-1", attempt_b, receipt_b)
    assert replay.code == ResultCode.APPLIED
    clash = broker.admit_launcher_receipt(
        migrated_db, op_b, broker.ReceiptProposal(
            receipt_identity=receipt_b,
            content={"kind": "observation", "prop": "p", "scope": "transfer",
                     "dep": "dep-seed", "dep_version": 3, "value": "false",
                     "source_attempt": attempt_b, "receipt": receipt_b, "epoch": 2,
                     "simulated": True},
            outcome="success", provenance="agenda-sim"))
    assert clash.code == ResultCode.APPLIED
    assert clash.data.get("conflict") is True
    conflicted = _record(migrated_db, "q-1", attempt_b, receipt_b, tag="conflict")
    assert conflicted.code == ResultCode.INVALID_INPUT
    assert "conflicting receipt" in conflicted.detail


def test_outcome_future_epoch_and_bad_value_refused(migrated_db):
    _propose(migrated_db)
    admitted = _admit(migrated_db, plan=PLAN, due=99, rid="ag01-admit-q-1-probe-a-future")
    attempt, op = admitted.data["attempt_id"], admitted.data["operation_id"]
    sim = _sim(migrated_db, {"p": True})
    _dispatch(migrated_db, sim, op)
    future = _record(migrated_db, "q-1", attempt, _receipt(sim, op))
    assert future.code == ResultCode.INVALID_INPUT
    assert "future-epoch" in future.detail
    manual = broker.admit_launcher_receipt(
        migrated_db, op, broker.ReceiptProposal(
            receipt_identity="state-traj:rc:manual",
            content={"kind": "observation", "prop": "p", "scope": "transfer",
                     "dep": "dep-seed", "dep_version": 3, "value": "maybe",
                     "source_attempt": attempt, "receipt": "state-traj:rc:manual",
                     "epoch": 1, "simulated": True},
            outcome="success", provenance="agenda-sim"))
    assert manual.code == ResultCode.APPLIED
    bad = _record(migrated_db, "q-1", attempt, "state-traj:rc:manual")
    assert bad.code == ResultCode.INVALID_INPUT


def test_stale_dependency_invalidates_receipt(migrated_db):
    _propose(migrated_db)
    first = _admit(migrated_db, plan=PLAN)
    attempt_a, op_a = first.data["attempt_id"], first.data["operation_id"]
    _admit(migrated_db, probe="probe-b", decision="do-b", rid="ag01-admit-q-1-probe-b",
           deps={"dep-seed": 4}, plan=PLAN)
    sim = _sim(migrated_db, {"p": True})
    _dispatch(migrated_db, sim, op_a)
    stale = _record(migrated_db, "q-1", attempt_a, _receipt(sim, op_a))
    assert stale.code == ResultCode.INVALID_INPUT
    assert "invalidated support" in stale.detail


def test_continuation_useful_and_refused(migrated_db):
    _propose(migrated_db)
    first = _admit(migrated_db, plan=PLAN)
    attempt_a, op_a = first.data["attempt_id"], first.data["operation_id"]
    sim = _sim(migrated_db, {"p": True})
    _dispatch(migrated_db, sim, op_a)
    receipt_a = _receipt(sim, op_a)
    assert _record(migrated_db, "q-1", attempt_a, receipt_a).code == ResultCode.APPLIED
    useful = _continue(migrated_db, "q-1", attempt_a, [receipt_a], "probe-b", "p2",
                       {"if_true": "fix", "if_false": "hold"})
    assert useful.code == ResultCode.APPLIED
    assert useful.data["decision"] == "useful-continuation"
    assert "useful continuation" in useful.detail
    second = _admit(migrated_db, probe="probe-c", decision="do-c",
                    rid="ag01-admit-q-1-probe-c", plan=PLAN)
    attempt_c, op_c = second.data["attempt_id"], second.data["operation_id"]
    sim2 = _sim(migrated_db, {"p": None})
    _dispatch(migrated_db, sim2, op_c)
    receipt_c = _receipt(sim2, op_c)
    assert _record(migrated_db, "q-1", attempt_c, receipt_c).code == ResultCode.APPLIED
    refused = _continue(migrated_db, "q-1", attempt_c, [receipt_c], "probe-d", "p2",
                        {"if_true": "fix", "if_false": "hold"})
    assert refused.code == ResultCode.INVALID_INPUT
    assert "remains unknown" in refused.detail
    wrong_parent = _continue(migrated_db, "q-1", "att-no-such", [receipt_a], "probe-e",
                             "p2", {"if_true": "fix", "if_false": "hold"})
    assert wrong_parent.code == ResultCode.INVALID_INPUT


def test_dormant_wake_reopen_and_dedup(migrated_db):
    _propose(migrated_db)
    _admit(migrated_db)
    dormant = agenda.set_dormant(
        migrated_db, Command(request_id="ag01-decline-q-1",
                             payload={"option_id": "q-1", "expected_disposition_version": 1,
                                      "reason": "waiting on evidence",
                                      "wake_condition": {"type": "evidence-change",
                                                         "dep": "dep-seed"}}))
    assert dormant.code == ResultCode.APPLIED
    assert dormant.data["disposition"] == "dormant"
    assert dormant.data["wake_condition"]["known_version"] == 3
    with db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state, operation_id FROM agenda_attempt_links")
            assert cur.fetchone()[0] == "admitted"
            cur.execute("SELECT SUM(reserved) FROM allocations")
            assert cur.fetchone()[0] == 4
        conn.commit()
    noise = agenda.process_wake(
        migrated_db, Command(request_id="ag01-wake-q-1-noise",
                             payload={"option_id": "q-1",
                                      "event": {"identity": "ev-noise", "kind": "message"}}))
    assert noise.code == ResultCode.APPLIED
    assert not noise.data["woke"]
    assert agenda.explain_eligibility(migrated_db, "q-1")["disposition"] == "dormant"
    relevant = agenda.process_wake(
        migrated_db, Command(request_id="ag01-wake-q-1-ev4",
                             payload={"option_id": "q-1",
                                      "event": {"identity": "ev-dep-v4",
                                                "kind": "evidence-changed",
                                                "dep": "dep-seed", "version": 4}}))
    assert relevant.code == ResultCode.APPLIED
    assert relevant.data["woke"]
    assert "reopened" in relevant.detail
    redeliver = agenda.process_wake(
        migrated_db, Command(request_id="ag01-wake-q-1-ev4-again",
                             payload={"option_id": "q-1",
                                      "event": {"identity": "ev-dep-v4",
                                                "kind": "evidence-changed",
                                                "dep": "dep-seed", "version": 4}}))
    assert redeliver.code == ResultCode.ALREADY_APPLIED
    _propose(migrated_db, key="q-doom", rid="ag01-propose-q-doom-r1")
    agenda.retire_option(migrated_db, Command(request_id="ag01-retire-q-doom",
                                              payload={"option_id": "q-doom",
                                                       "expected_disposition_version": 1,
                                                       "reason": "dead end"}))
    grave = agenda.process_wake(
        migrated_db, Command(request_id="ag01-wake-q-doom-ev",
                             payload={"option_id": "q-doom",
                                      "event": {"identity": "ev-x", "kind": "evidence-changed",
                                                "dep": "dep-seed", "version": 9}}))
    assert grave.code == ResultCode.INVALID_INPUT
    assert agenda.explain_eligibility(migrated_db, "q-doom")["disposition"] == "retired"


def test_stale_disposition_refused(migrated_db):
    _propose(migrated_db)
    stale = agenda.set_dormant(
        migrated_db, Command(request_id="ag01-decline-q-1-stale",
                             payload={"option_id": "q-1", "expected_disposition_version": 99,
                                      "reason": "stale", "wake_condition": {"type": "evidence-change",
                                                                            "dep": "dep-seed"}}))
    assert stale.code == ResultCode.STALE_REVISION
    assert agenda.explain_eligibility(migrated_db, "q-1")["disposition"] == "open"


def test_cursor_tick_and_budget_reconstruct(migrated_db):
    _propose(migrated_db)
    first = _admit(migrated_db, plan=PLAN)
    attempt_a, op_a = first.data["attempt_id"], first.data["operation_id"]
    sim = _sim(migrated_db, {"p": True})
    _dispatch(migrated_db, sim, op_a)
    receipt_a = _receipt(sim, op_a)
    assert _record(migrated_db, "q-1", attempt_a, receipt_a).code == ResultCode.APPLIED
    _continue(migrated_db, "q-1", attempt_a, [receipt_a], "probe-b", "p2",
              {"if_true": "fix", "if_false": "hold"})
    snap = agenda.agenda_snapshot(migrated_db)
    assert snap["cursor"]["tick"] == 2
    assert snap["liability"] == 2
    assert snap["remaining"] == 64 - 2 - 4 - 2
    assert any(o["option_id"] == "q-1" and o["disposition"] == "open" for o in snap["options"])


def test_idle_advances_tick(migrated_db):
    _propose(migrated_db)
    idle = agenda.note_idle(migrated_db, Command(request_id="ag01-idle-1",
                                                 payload={"trajectory": TRAJ,
                                                          "policy_version": "AG01-R-1"}))
    assert idle.code == ResultCode.APPLIED
    assert agenda.agenda_snapshot(migrated_db)["remaining"] == 64 - 1


def test_lineage_cap_no_reset(migrated_db):
    _propose(migrated_db)
    _propose(migrated_db, key="q-2", rid="ag01-propose-q-2-r1")
    with db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT authorized FROM allocations WHERE id = 'agenda-root'")
            assert cur.fetchone()[0] == 64
        conn.commit()
    assert _admit(migrated_db, cost=60).code == ResultCode.APPLIED
    assert _admit(migrated_db, key="q-2", probe="probe-a",
                  rid="ag01-admit-q-2-probe-a").code == ResultCode.INSUFFICIENT_RESOURCES


def test_fresh_process_resume(migrated_db):
    _propose(migrated_db)
    _admit(migrated_db)
    probe = ("from settlement import agenda;"
             "import json;"
             f"snap = agenda.agenda_snapshot({migrated_db!r});"
             "print(json.dumps({'tick': snap['cursor']['tick'],"
             " 'remaining': snap['remaining'],"
             " 'options': [(o['option_id'], o['disposition']) for o in snap['options']]}))")
    env = dict(os.environ, PYTHONPATH="src")
    first = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                           timeout=120, cwd=ROOT, env=env)
    assert first.returncode == 0, first.stderr
    import json as _json
    assert _json.loads(first.stdout) == {"tick": 1, "remaining": 64 - 1 - 4,
                                         "options": [["q-1", "open"]]}
    replay = ("from settlement import agenda;"
              "from settlement.common import Command;"
              f"r = agenda.propose_option({migrated_db!r},"
              " Command(request_id='ag01-propose-q-1-r1', expected_revision=None,"
              " payload={'option_key': 'q-1', 'scope': 'transfer', 'question': 'q?',"
              " 'revision': 1, 'allocation_root': 'agenda-root', 'body': {}}));"
              "print(r.code.value)")
    second = subprocess.run([sys.executable, "-c", replay], capture_output=True, text=True,
                            timeout=120, cwd=ROOT, env=env)
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "already_applied"


def test_killed_writer_leaves_no_partial_state(migrated_db):
    db.apply_migrations(migrated_db, "migrations")
    killer = ("import os;"
              "from settlement import db;"
              f"conn = db.connect({migrated_db!r});"
              "cur = conn.cursor();"
              "cur.execute(\"INSERT INTO agenda_options (option_id, allocation_root)\""
              " \" VALUES ('q-ghost', 'agenda-root')\");"
              "os._exit(9)")
    proc = subprocess.run([sys.executable, "-c", killer], capture_output=True, timeout=120,
                          cwd=ROOT,
                          env=dict(os.environ, PYTHONPATH="src"))
    assert proc.returncode != 0
    with db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM agenda_options WHERE option_id = 'q-ghost'")
            assert cur.fetchone()[0] == 0
        conn.commit()
