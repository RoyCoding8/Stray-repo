"""INV-R2 S2: interrupted corrections resume with full meaning.

A fresh DecisionConsumer (or fresh process) after one rejected proposal must
restore the rejected target, the actual failure, the correction index and the
remaining allowance from the durable journal. The next real provider request
carries the failure with the refused target pinned. Real Postgres in
databases named inv_r2_*; doubles sit at the provider seam only.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from settlement import db  # noqa: E402

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 60,
        "agenda_authorized": 100000}
FUNDED = 100000
MODEL = "inv-r2-double"
SW0 = "ad01-w0-dev-sw-00"
SW1 = "ad01-w0-dev-sw-01"
MAINT = "dbname=postgres host=/var/run/postgresql user=ubuntu"


def _dsn(name):
    return "dbname=%s host=/var/run/postgresql user=ubuntu" % name


def _create(name):
    conn = db.connect(MAINT)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute('CREATE DATABASE "%s"' % name)
    conn.close()


def _drop(name):
    conn = db.connect(MAINT)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE datname = %s AND pid <> pg_backend_pid()", (name,))
        cur.execute('DROP DATABASE IF EXISTS "%s"' % name)
    conn.close()


def _fresh_db(dsn, seq):
    from experiments.ad01 import trajectory as T
    from experiments.coord02 import experience as E
    assert "live" not in dsn
    db.apply_migrations(dsn, ROOT / "migrations")
    E.designate_db(dsn, kind="disposable", purpose="inv-r2 correction")
    E.prepare_disposable_db(dsn, ROOT / "migrations")
    T.authorize_campaign(dsn, T.campaign_id(0, "I", seq), authorized=FUNDED)


def _invalid_text():
    return json.dumps({
        "basis_references": ["obs-invented-999"],
        "question": "leap at %s" % SW0,
        "next_action": {"kind": "diagnostic", "diagnostic": "software",
                        "task_id": SW0},
        "requested_resources": {"diagnostic_queries": 1}}, sort_keys=True)


def _valid_text(task_id, family="software"):
    return json.dumps({
        "basis_references": ["obs-%s-seed" % task_id],
        "question": "diagnose %s" % task_id,
        "next_action": {"kind": "diagnostic", "diagnostic": family,
                        "task_id": task_id},
        "requested_resources": {"diagnostic_queries": 1}}, sort_keys=True)


def _correction_rows(dsn, aid):
    from experiments.ad01 import trajectory as T
    with T._read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT content FROM attempt_observations WHERE attempt_id = %s"
            " ORDER BY id", (aid,)).fetchall()
    return [dict(r["content"] or {}) for r in rows
            if dict(r.get("content") or {}).get("kind") == "correction"]


def _receipts(dsn, operation_id):
    from experiments.ad01 import trajectory as T
    with T._read_conn(dsn) as conn:
        return conn.execute(
            "SELECT receipt_identity, outcome FROM receipts"
            " WHERE operation_id = %s ORDER BY receipt_identity",
            (operation_id,)).fetchall()


def _aid(cid, seq=0):
    from experiments.ad01 import trajectory as T
    return T._attempt_id(cid, seq)


def _boundary(world=0, seq=0):
    return {"world": world, "arm": "I", "seq": seq}


def _learner_op(cid, attempt=0):
    from experiments.ad01.learner import _learner_op_id
    return _learner_op_id(cid, 0, attempt)


def _unit_consumer(dsn, cid, proposer, aid=None):
    from experiments.ad01 import agenda_policy, trajectory as T
    seed = T.ensure_campaign(dsn, cid, 0, "I", dict(CHARTER), dict(CAPS),
                             tasks=[SW0, SW1])
    return agenda_policy.DecisionConsumer(
        proposer=proposer, dsn=dsn, cid=cid,
        allocation_id=seed["allocation_id"], study_root=cid,
        policy_version=agenda_policy.MODEL_POLICY_VERSION)


def _seen(task_id):
    return {"observations": [{"observation_id": "obs-%s-seed" % task_id,
                              "task_id": task_id,
                              "capability_id": "seed-sw-greedy",
                              "verdict": "unmeasured"}]}


def _boundary(world=0, seq=0):
    return {"world": world, "arm": "I", "seq": seq}


def test_resumed_consumer_pins_refused_target():
    from experiments.ad01 import trajectory as T
    _create("inv_r2_corr_unit")
    try:
        dsn = _dsn("inv_r2_corr_unit")
        _fresh_db(dsn, 50)
        cid = T.campaign_id(0, "I", 50)
        aid = _aid(cid)

        def bad_then_good(seen, asked):
            if seen.get("prior_failure") is None:
                return {"basis_references": ["obs-invented-999"],
                        "question": "leap",
                        "next_action": {"kind": "diagnostic",
                                        "diagnostic": "software",
                                        "task_id": SW0},
                        "requested_resources": {"diagnostic_queries": 1}}
            seed = seen["observations"][0]
            return {"basis_references": [seed["observation_id"]],
                    "question": "diagnose %s again" % SW0,
                    "next_action": {"kind": "diagnostic",
                                    "diagnostic": "software",
                                    "task_id": SW0},
                    "requested_resources": {"diagnostic_queries": 1}}

        first = _unit_consumer(dsn, cid, bad_then_good)
        out = first.decide(_seen(SW0), dict(CHARTER), boundary=_boundary(),
                           experience=_seen(SW0), aid=aid)
        assert out["status"] == "admitted"
        assert out["corrections"] == 1
        rows = _correction_rows(dsn, aid)
        assert len(rows) == 1
        assert rows[0]["failure"]["target"] == SW0
        assert "invented basis references" in rows[0]["failure"]["reason"]

        def poach(seen, asked):
            seed = seen["observations"][0]
            return {"basis_references": [seed["observation_id"]],
                    "question": "poach %s" % SW1,
                    "next_action": {"kind": "diagnostic",
                                    "diagnostic": "software",
                                    "task_id": SW1},
                    "requested_resources": {"diagnostic_queries": 1}}

        fresh = _unit_consumer(dsn, cid, poach)
        refused = fresh.decide(_seen(SW0), dict(CHARTER),
                               boundary=_boundary(), experience=_seen(SW0),
                               aid=aid)
        assert refused["status"] == "refused"
        assert "correction-changed-target" in refused["reason"]
        assert SW0 in refused["reason"]

        def same_target(seen, asked):
            seed = seen["observations"][0]
            assert seen["prior_failure"]["target"] == SW0
            assert "invented basis references" in \
                seen["prior_failure"]["reason"]
            return {"basis_references": [seed["observation_id"]],
                    "question": "diagnose %s again" % SW0,
                    "next_action": {"kind": "diagnostic",
                                    "diagnostic": "software",
                                    "task_id": SW0},
                    "requested_resources": {"diagnostic_queries": 1}}

        resumed = _unit_consumer(dsn, cid, same_target)
        aid1 = _aid(cid, 1)
        setup = _unit_consumer(dsn, cid, bad_then_good)
        assert setup.decide(_seen(SW0), dict(CHARTER),
                            boundary=_boundary(seq=1),
                            experience=_seen(SW0),
                            aid=aid1)["status"] == "admitted"
        admitted = resumed.decide(_seen(SW0), dict(CHARTER),
                                  boundary=_boundary(seq=1),
                                  experience=_seen(SW0), aid=aid1)
        assert admitted["status"] == "admitted"
        assert admitted["corrections"] == 1
        assert admitted["investigation"]["next_action"]["task_id"] == SW0
    finally:
        _drop("inv_r2_corr_unit")


def test_correction_budget_still_exhausts_after_resume():
    from experiments.ad01 import trajectory as T
    _create("inv_r2_corr_unitb")
    try:
        dsn = _dsn("inv_r2_corr_unitb")
        _fresh_db(dsn, 51)
        cid = T.campaign_id(0, "I", 51)
        aid = _aid(cid)

        def stubborn(seen, asked):
            return {"basis_references": ["obs-invented-999"],
                    "question": "leap",
                    "next_action": {"kind": "diagnostic",
                                    "diagnostic": "software",
                                    "task_id": SW0},
                    "requested_resources": {"diagnostic_queries": 1}}

        first = _unit_consumer(dsn, cid, stubborn)
        out = first.decide(_seen(SW0), dict(CHARTER), boundary=_boundary(),
                           experience=_seen(SW0), aid=aid)
        assert out["status"] == "refused"
        assert len(_correction_rows(dsn, aid)) == 2

        def must_not_run(seen, asked):
            pytest.fail("exhausted budget must not call the proposer")

        fresh = _unit_consumer(dsn, cid, must_not_run)
        refused = fresh.decide(_seen(SW0), dict(CHARTER),
                               boundary=_boundary(), experience=_seen(SW0),
                               aid=aid)
        assert refused["status"] == "refused"
        assert "exhausted" in refused["reason"]
    finally:
        _drop("inv_r2_corr_unitb")


def _launch(mode, *args):
    return subprocess.Popen(
        [sys.executable, __file__, mode, *map(str, args)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True)


def _wait_correction(dsn, aid, deadline_s=300):
    from experiments.ad01 import trajectory as T
    deadline = time.monotonic() + deadline_s
    with T._read_conn(dsn) as conn:
        while time.monotonic() < deadline:
            rows = conn.execute(
                "SELECT content FROM attempt_observations"
                " WHERE attempt_id = %s ORDER BY id", (aid,)).fetchall()
            conn.commit()
            found = [dict(r["content"] or {}) for r in rows
                     if dict(r.get("content") or {}).get("kind")
                     == "correction"]
            if found:
                return found
            time.sleep(0.5)
    raise AssertionError("victim never journaled its first correction")


def test_kill_before_correction_resumes_failure_in_next_request(tmp_path):
    from experiments.ad01 import trajectory as T
    _create("inv_r2_corr")
    try:
        dsn = _dsn("inv_r2_corr")
        seq = 40
        cid = T.campaign_id(0, "I", seq)
        aid = _aid(cid)
        _fresh_db(dsn, seq)
        victim = _launch("victim_corr", dsn, str(seq))
        try:
            found = _wait_correction(dsn, aid)
        except BaseException:
            if victim.poll() is None:
                victim.kill()
            raise
        assert len(found) == 1
        assert found[0]["failure"]["target"] == SW0
        os.killpg(os.getpgid(victim.pid), signal.SIGKILL)
        victim.wait()
        settled, pending = T._read_campaign(dsn, cid)
        assert settled == {}
        assert pending == {}
        base_receipts = _receipts(dsn, _learner_op(cid))
        assert len(base_receipts) == 1
        assert base_receipts[0]["outcome"] == "success"
        assert _receipts(dsn, _learner_op(cid, 1)) == []
        out = str(tmp_path / "resumed.json")
        resumed = _launch("resume_corr", dsn, cid, out)
        rc = resumed.wait(timeout=300)
        assert rc == 0, resumed.stdout.read().decode()[-3000:]
        got = json.loads(Path(out).read_text())
        assert len(got["prompts"]) == 1
        prompt = got["prompts"][0]
        assert "PRIOR FAILURE (correct it)" in prompt
        assert SW0 in prompt
        assert "invented basis references: obs-invented-999" in prompt
        assert got["boundaries"][0]["task_id"] == SW0
        assert got["episodes"][0]["disposition"] == "inspected"
        assert len(_correction_rows(dsn, aid)) == 1
        assert len(_receipts(dsn, _learner_op(cid))) == 1
        assert _receipts(dsn, _learner_op(cid, 1)) == []
        retried = _receipts(dsn, _learner_op(cid, 2))
        assert len(retried) == 1
        assert retried[0]["outcome"] == "success"
    finally:
        _drop("inv_r2_corr")


class _StallGateway:
    label = "INV-R2-STALL-LEARNER"

    def __init__(self, scripts):
        from experiments.ad01.learner import RecordingGatewayAdapter
        self._inner = RecordingGatewayAdapter(scripts)

    def check_discovery(self):
        return self._inner.check_discovery()

    def check_auth(self):
        return self._inner.check_auth()

    def infer(self, request):
        if len(self._inner.calls) == 1:
            time.sleep(600)
        return self._inner.infer(request)

    def cancel(self, operation_id):
        return False


def _propose_kwargs(dsn, cid, gateway):
    from experiments.ad01 import trajectory as T
    from experiments.ad01.learner import propose_from_model
    seed = T.ensure_campaign(dsn, cid, 0, "I", dict(CHARTER), dict(CAPS),
                             tasks=[SW0])
    propose = propose_from_model(
        dsn, cid=cid, gateway=gateway, model=MODEL, charter=dict(CHARTER),
        world=0, arm="I", allocation_id=seed["allocation_id"])
    return propose


def _driver_victim_corr(dsn, seq):
    from experiments.ad01 import trajectory as T
    from experiments.ad01.learner import RecordingGatewayAdapter
    cid = T.campaign_id(0, "I", int(seq))
    gateway = _StallGateway([{"text": _invalid_text()},
                             {"text": _valid_text(SW0)}])
    propose = _propose_kwargs(dsn, cid, gateway)
    T.run_campaign(0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0],
                   campaign_seq=int(seq), dsn=dsn, propose=propose,
                   gateway=gateway, model=MODEL)


def _driver_resume_corr(dsn, cid, out):
    from experiments.ad01 import trajectory as T
    from experiments.ad01.learner import RecordingGatewayAdapter
    gateway = RecordingGatewayAdapter([{"text": _valid_text(SW0)}])
    propose = _propose_kwargs(dsn, cid, gateway)
    campaign = T.resume_campaign(
        dsn, cid, dict(CHARTER), dict(CAPS), tasks=[SW0], propose=propose,
        gateway=gateway, model=MODEL)
    prompts = []
    for request in gateway.calls:
        try:
            prompts.append(request.messages[-1]["content"])
        except (IndexError, TypeError, KeyError):
            prompts.append("")
    Path(out).write_text(json.dumps({
        "prompts": prompts,
        "boundaries": [{"task_id": b["task_id"]} for b in
                       campaign["boundaries"]],
        "episodes": [{"disposition": e.get("disposition")} for e in
                     campaign["episodes"]]}))


def _main(argv):
    mode = argv[1]
    if mode == "victim_corr":
        _driver_victim_corr(argv[2], argv[3])
    elif mode == "resume_corr":
        _driver_resume_corr(argv[2], argv[3], argv[4])
    else:
        raise SystemExit("unknown mode %r" % mode)


if __name__ == "__main__":
    _main(sys.argv)
