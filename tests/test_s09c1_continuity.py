"""S09-C1 continuity gates: durable STEP state plus cumulative limits plus resume.

Independently supplied STEP bytes run through real child execution and
real PostgreSQL. Each gate fails on the base where decide rebuilds
remaining from the packet, restarts private state, prepares repeated
model operations, and leaves exhausted plus refused paths unrecorded.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01.agenda_policy import step_policy_consumer
from experiments.ad01.policy_step import make_policy_artifact
from experiments.ad01.s09_run_isolation import DB_PREFIX, create_disposable_db, \
    drop_disposable_db, disposable_db

LOCAL_HOST = "/var/run/postgresql"
LOCAL_DSN = "dbname=postgres host=%s user=ubuntu" % LOCAL_HOST

RUN_TOKEN = "c1%s" % uuid.uuid4().hex[:10]
RUNS = ROOT / ".ad01-runs"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
TASK = "ad01-w0-dev-sw-00"
TASK2 = "ad01-w0-dev-sw-01"

LOOP_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    n = int(state.get(\"n\", 0))\n"
    "    action = {\"kind\": \"request_model\", \"target\": target,\n"
    "              \"inputs\": {\"prompt\": \"bounded reasoning %d\" % n,\n"
    "                         \"max_output_tokens\": 32},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"model_calls\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"n\": n + 1}}\n"
)

COUNTER_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    seen = int(state.get(\"counter\", 0))\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"does the seed disagree\",\n"
    "                         \"question\": \"why this verdict\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"counter\": seen + 1}}\n"
)

ROUNDTRIP_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    if not state.get(\"asked\"):\n"
    "        action = {\"kind\": \"request_model\", \"target\": target,\n"
    "                  \"inputs\": {\"prompt\": \"summarize witness\",\n"
    "                             \"max_output_tokens\": 32},\n"
    "                  \"evidence_refs\": [],\n"
    "                  \"requested_resources\": {\"model_calls\": 1}}\n"
    "        return {\"action\": action, \"state\": {\"asked\": True}}\n"
    "    action = {\"kind\": \"diagnose\", \"target\": target,\n"
    "              \"inputs\": {\"diagnostic\": \"software\",\n"
    "                         \"unknown\": \"does the seed disagree\",\n"
    "                         \"question\": \"why this verdict\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {\"queries\": 1}}\n"
    "    return {\"action\": action, \"state\": {\"asked\": True}}\n"
)

CRASH_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view[\"task_content\"][\"task_id\"]\n"
    "    if not state.get(\"asked\"):\n"
    "        action = {\"kind\": \"request_model\", \"target\": target,\n"
    "                  \"inputs\": {\"prompt\": \"stable prompt bytes\",\n"
    "                             \"max_output_tokens\": 32},\n"
    "                  \"evidence_refs\": [],\n"
    "                  \"requested_resources\": {\"model_calls\": 1}}\n"
    "        return {\"action\": action, \"state\": {\"asked\": True}}\n"
    "    action = {\"kind\": \"stop\", \"target\": target,\n"
    "              \"inputs\": {\"reason\": \"done\"},\n"
    "              \"evidence_refs\": [],\n"
    "              \"requested_resources\": {}}\n"
    "    return {\"action\": action, \"state\": {\"asked\": True}}\n"
)


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src",
                                      ROOT / "experiments")
    return env


def _dbname(dsn: str) -> str:
    parsed = urlparse(dsn)
    if parsed.scheme:
        return (parsed.path or "/").lstrip("/")
    fields = dict(field.split("=", 1) for field in dsn.split()
                  if "=" in field)
    return fields.get("dbname", "").strip("'\"")


def test_the_store_is_named_for_this_run_not_for_the_file():
    """Two concurrent runs of this module must not share a store.

    The same file ships in every worktree, and each one used to create and
    drop one fixed name on one shared cluster, so a sibling's teardown
    destroyed this run's store mid-module. Only the per-run suffix keeps the
    two disjoint, so that is what this pins.
    """
    with disposable_db(RUN_TOKEN) as database:
        assert database.name.startswith(DB_PREFIX + "_")
        assert RUN_TOKEN in database.name
        assert re.fullmatch(r"[0-9a-f]{12}", database.name.rsplit("_", 1)[1])

    again = create_disposable_db(RUN_TOKEN)
    try:
        assert again.name != database.name
    finally:
        drop_disposable_db(again)


def test_a_run_never_reuses_the_store_it_did_not_create():
    """The suite points every file at one DSN, so a module must not reuse it.

    Taking ``SETTLEMENT_TEST_DSN`` as the store meant a module-scoped fixture
    truncating whatever an earlier file had written, which is the hazard
    ``s09_test_db_safety.py`` measures. The DSN is honoured as the admin
    connection instead, so this run lands on the operator's cluster and still
    owns the only database it drops.
    """
    with disposable_db(RUN_TOKEN) as database:
        assert database.name != _dbname(LOCAL_DSN)
        assert database.name != _dbname(
            "dbname=operator_store host=/var/run/postgresql user=ubuntu")
        assert database.name not in ("s09_c1_continuity", "operator_store")


@pytest.fixture(scope="module")
def store():
    """A store this run creates, on whichever cluster the operator named.

    ``SETTLEMENT_TEST_DSN`` is taken as the admin connection rather than as
    the store, so an operator pointing at a particular PostgreSQL gets this
    run on that instance without handing the tests a database they would have
    to empty. Reusing that database is what made this module interfere: the
    campaign suite points every file at one DSN, so a module-scoped store
    that truncates it destroys the rows of whichever file ran before.
    """
    env_dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    admin_dsn = env_dsn or LOCAL_DSN
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    before = set(p.name for p in RUNS.iterdir()) if RUNS.is_dir() else set()
    database = create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                    migrations_dir=migrations)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database, admin_dsn=admin_dsn)
        _scrub_new_runs(before)


def _scrub_new_runs(before: set) -> None:
    if not RUNS.is_dir():
        return
    import shutil
    for child in RUNS.iterdir():
        if child.name not in before:
            shutil.rmtree(child, ignore_errors=True)


def _consumer(dsn, cid, source, gateway=None, max_steps=6):
    from experiments.ad01 import trajectory
    artifact = make_policy_artifact(
        source, origin="authored-control",
        applicability={"world": 0, "arm": "I"})
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return step_policy_consumer(
        artifact, dsn=dsn, cid=cid, charter=dict(CHARTER),
        world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid),
        study_root=cid, gateway=gateway, model="recorded-double",
        max_policy_steps=max_steps)


def _admit_campaign(dsn, cid, tasks):
    """The admission `run_campaign` performs before any boundary runs.

    Three gates here drive `consumer.decide` directly rather than through
    `run_campaign`, so the investigation row `resume_campaign` restores from
    was never written and the resume refused with "no mission". This is the
    call `run_campaign` itself makes, reached here so the restart has the
    same admission a live run would have left behind. `tasks` must be the
    schedule the resuming run supplies, because the schedule is journalled
    under `schedule-<cid>` and a different payload for one request id is a
    conflict rather than an update.
    """
    from experiments.ad01 import trajectory
    return trajectory.ensure_campaign(
        dsn, cid, 0, "I", CHARTER,
        {"max_boundaries": 6, "diagnostic_queries": 16}, tasks=list(tasks))


def _s09_row(dsn, cid, seq):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        return conn.execute(
            "SELECT * FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = %s",
            (cid, seq)).fetchone()


def _model_ops(dsn, cid, seq):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        return conn.execute(
            "SELECT id FROM operations WHERE id LIKE %s ORDER BY id",
            ("ad01-%s-policy-s%d-model-%%" % (cid, seq),)).fetchall()


def _step_ops(dsn, cid, seq):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        return conn.execute(
            "SELECT id FROM operations WHERE starts_with(id, %s)"
            " ORDER BY id",
            ("ad01-%s-policy-s%d-k" % (cid, seq),)).fetchall()


def _receipt_text(dsn, operation_id):
    from settlement import db
    with db.connect(dsn) as conn:
        row = conn.execute(
            "SELECT content FROM receipts WHERE operation_id = %s"
            " AND receipt_identity = %s AND outcome = 'success'",
            (operation_id, "gw:%s" % operation_id)).fetchone()
        conn.commit()
    if row is None:
        return None
    return str(dict(row[0] or {}).get("text", ""))


def test_allowance_one_prepares_once(store):
    from experiments.ad01 import trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter
    cid = trajectory.campaign_id(0, "I", 80)
    gateway = RecordingGatewayAdapter(
        [{"text": "response %d" % i} for i in range(6)])
    out = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1, "diagnostic_queries": 16,
                          "model_calls": 1},
        tasks=[TASK], campaign_seq=80, dsn=store,
        consumer=_consumer(store, cid, LOOP_SOURCE, gateway=gateway))
    assert len(_model_ops(store, cid, 0)) == 1
    assert len(gateway.calls) == 1
    assert len(_step_ops(store, cid, 0)) <= 6
    row = _s09_row(store, cid, 0)
    assert row is not None
    results = dict(row["policy_output"])["results"]
    assert len(results) <= 6
    views = dict(row["policy_input"])["views"]
    assert views[1]["last_result"]["kind"] == "model_response"
    assert views[2]["last_result"]["status"] == "refused"


def test_private_state_survives_boundary(store):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 81)
    out = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 2, "diagnostic_queries": 16,
                          "model_calls": 60},
        tasks=[TASK, TASK2], campaign_seq=81, dsn=store,
        consumer=_consumer(store, cid, COUNTER_SOURCE))
    assert [b["seq"] for b in out["boundaries"]] == [0, 1]
    first = _s09_row(store, cid, 0)
    second = _s09_row(store, cid, 1)
    assert first is not None
    assert second is not None
    first_final = dict(first["state_transition"])["final_state"]
    second_prev = dict(second["state_transition"])["transitions"][0]["previous"]
    assert first_final == {"counter": 1}
    assert second_prev == {"counter": 1}
    assert dict(second["state_transition"])["final_state"] == {"counter": 2}


def test_resume_reuses_model_text_after_restart(store, tmp_path):
    from experiments.ad01 import trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter
    cid = trajectory.campaign_id(0, "I", 82)
    gateway = RecordingGatewayAdapter([{"text": "stable witness bytes"}])
    first = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1, "diagnostic_queries": 16,
                          "model_calls": 60},
        tasks=[TASK], campaign_seq=82, dsn=store,
        consumer=_consumer(store, cid, ROUNDTRIP_SOURCE, gateway=gateway))
    assert first["boundaries"][0]["observation_id"].startswith("obs-")
    before_ops = _model_ops(store, cid, 0)
    assert len(before_ops) == 1
    before_text = _receipt_text(store, before_ops[0]["id"])
    assert before_text == "stable witness bytes"
    source_path = tmp_path / "policy.py"
    source_path.write_text(ROUNDTRIP_SOURCE)
    script = (
        "import json, sys\n"
        "dsn, cid, source_path = sys.argv[1:4]\n"
        "from experiments.ad01 import trajectory\n"
        "from experiments.ad01.agenda_policy import step_policy_consumer\n"
        "from experiments.ad01.policy_step import make_policy_artifact\n"
        "source = open(source_path).read()\n"
        "artifact = make_policy_artifact(source, origin='authored-control',\n"
        "    applicability={'world': 0, 'arm': 'I'})\n"
        "consumer = step_policy_consumer(artifact, dsn=dsn, cid=cid,\n"
        "    charter=%s, world=0, arm='I',\n"
        "    allocation_id=trajectory._alloc_id(cid), study_root=cid,\n"
        "    gateway=__import__('experiments.ad01.learner', fromlist=['x'])."
        "RecordingGatewayAdapter([{'text': 'changed bytes'}]),\n"
        "    model='recorded-double')\n"
        "out = trajectory.resume_campaign(dsn, cid, %s,\n"
        "    {'max_boundaries': 1, 'diagnostic_queries': 16,\n"
        "     'model_calls': 60},\n"
        "    tasks=['%s'], consumer=consumer)\n"
        "print(json.dumps(out, default=str))\n"
        % (repr(CHARTER), repr(CHARTER), TASK))
    proc = subprocess.run(
        [sys.executable, "-c", script, store, cid, str(source_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    resumed = json.loads(proc.stdout)
    assert resumed["boundaries"][0]["observation_id"] == \
        first["boundaries"][0]["observation_id"]
    assert _model_ops(store, cid, 0) == before_ops
    assert _receipt_text(store, before_ops[0]["id"]) == \
        "stable witness bytes"


def test_pending_action_survives_preparation_crash(store):
    from experiments.ad01 import trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter
    from settlement import broker
    cid = trajectory.campaign_id(0, "I", 83)
    gateway = RecordingGatewayAdapter([{"text": "crash-path bytes"}])
    consumer = _consumer(store, cid, CRASH_SOURCE, gateway=gateway)
    out = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1, "diagnostic_queries": 16,
                          "model_calls": 60},
        tasks=[TASK], campaign_seq=83, dsn=store, consumer=consumer)
    assert out["stop"]["reason"] == "learner stop"
    model_ops = _model_ops(store, cid, 0)
    assert len(model_ops) == 1
    operation_id = model_ops[0]["id"]
    assert broker.read_operation(store, operation_id) is not None
    assert _receipt_text(store, operation_id) == "crash-path bytes"
    row = _s09_row(store, cid, 0)
    assert row is not None
    output = dict(row["policy_output"])
    assert output["source_digest"] == hashlib.sha256(
        CRASH_SOURCE.encode()).hexdigest()
    assert [r["action"]["kind"] for r in output["results"]] == [
        "request_model", "stop"]
    assert row["status"] in ("accepted", "incorporated")


def test_exhausted_and_refused_paths_stay_in_history(store):
    from experiments.ad01 import trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter
    cid = trajectory.campaign_id(0, "I", 84)
    gateway = RecordingGatewayAdapter([{"text": "only one"}])
    out = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1, "diagnostic_queries": 16,
                          "model_calls": 0},
        tasks=[TASK], campaign_seq=84, dsn=store,
        consumer=_consumer(store, cid, LOOP_SOURCE, gateway=gateway))
    assert len(_model_ops(store, cid, 0)) == 0
    row = _s09_row(store, cid, 0)
    assert row is not None
    assert dict(row["policy_input"]) != {}
    assert dict(row["policy_output"]) != {}
    assert len(gateway.calls) == 0


@pytest.mark.xfail(
    strict=True,
    reason="the settlement store refuses to admit a success model receipt "
           "whose text is empty (src/settlement/store.py _validate_receipt), "
           "added by 9f6ec8a three days after this gate was written. The "
           "integrity rule is deliberate and holds at both layers, so an "
           "empty-text response can no longer settle; it stays an unsettled "
           "operation. test_empty_text_is_refused_rather_than_settled pins "
           "what the product now guarantees. This xfail stays strict, so a "
           "store that starts admitting empty-text successes again turns the "
           "suite red instead of passing quietly.")
def test_settled_receipt_stays_attributable_on_empty_text(store):
    from experiments.ad01 import trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter
    cid = trajectory.campaign_id(0, "I", 85)
    gateway = RecordingGatewayAdapter([{"text": ""}])
    out = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1, "diagnostic_queries": 16,
                          "model_calls": 60},
        tasks=[TASK], campaign_seq=85, dsn=store,
        consumer=_consumer(store, cid, ROUNDTRIP_SOURCE, gateway=gateway))
    model_ops = _model_ops(store, cid, 0)
    assert len(model_ops) == 1
    assert _receipt_text(store, model_ops[0]["id"]) == ""
    row = _s09_row(store, cid, 0)
    assert row is not None
    views = dict(row["policy_input"])["views"]
    assert views[1]["last_result"]["digest"] == hashlib.sha256(
        "".encode()).hexdigest()


def test_empty_text_is_refused_rather_than_settled(store):
    """An empty model response must leave an operation the policy can name.

    A success receipt with no text is indistinguishable from a lost response,
    so the store refuses it. What the refusal used to leave behind was worse
    than the refusal: the broker filed the success anyway, the store threw it
    away, and the operation was left `dispatching` holding a reservation with
    no receipt and no way to settle it. The response had arrived, so that
    hold was never a measured exposure.

    The operation is now `observed` as a decided `failure`, carrying the
    response class and a digest of the bytes that did arrive. The policy
    property this test exists for is unchanged and asserted below on all
    three counts: no success receipt, no text, and a step that still
    refuses and names the operation.
    """
    from experiments.ad01 import trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter
    from settlement import broker, db
    cid = trajectory.campaign_id(0, "I", 89)
    gateway = RecordingGatewayAdapter([{"text": ""}])
    trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1, "diagnostic_queries": 16,
                          "model_calls": 60},
        tasks=[TASK], campaign_seq=89, dsn=store,
        consumer=_consumer(store, cid, ROUNDTRIP_SOURCE, gateway=gateway))

    model_ops = _model_ops(store, cid, 0)
    assert len(model_ops) == 1
    operation_id = model_ops[0]["id"]
    assert _receipt_text(store, operation_id) is None, \
        "an empty answer must never be filed as a success"
    operation = broker.read_operation(store, operation_id)
    assert operation["dispatch_state"] == "observed"
    assert operation["settled"] is True
    assert operation["reconcile_state"] == "none"

    with db.connect(store) as conn:
        rows = conn.execute(
            "SELECT receipt_identity, outcome, content FROM receipts"
            " WHERE operation_id = %s", (operation_id,)).fetchall()
        conn.commit()
    assert [row[1] for row in rows] == ["failure"]
    content = dict(rows[0][2])
    assert content["response_class"] == "empty-response"
    assert content["response_received"] is True
    assert content["text"] == ""
    assert content["response_digest"] == hashlib.sha256(b"").hexdigest()

    row = _s09_row(store, cid, 0)
    assert row is not None
    views = dict(row["policy_input"])["views"]
    assert views[1]["last_result"] == {
        "status": "refused",
        "reason": "model call %s left no settled response" % operation_id,
        "operation_id": operation_id}


def test_pre_effect_step_resumes_without_rerunning_accepted_step(store,
                                                                 monkeypatch,
                                                                 tmp_path):
    from experiments.ad01 import learner, packet, policy_step, trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter

    cid = trajectory.campaign_id(0, "I", 86)
    gateway = RecordingGatewayAdapter([{"text": "resumed bytes"}])
    consumer = _consumer(store, cid, CRASH_SOURCE, gateway=gateway)
    _admit_campaign(store, cid, [TASK])
    boundary = {"world": 0, "arm": "I", "seq": 0}
    seen = packet.decision_packet(
        charter=CHARTER, visible=learner.visible_opportunities(0),
        experience={"observations": [{"task_id": TASK}]}, retained=[],
        remaining={"model_calls": 60, "queries": 16, "boundaries": 1},
        curriculum=learner.curriculum_item(0, "I", 0), boundary=boundary)
    calls = []
    original = policy_step.run_policy_step

    def count_steps(*args, **kwargs):
        calls.append("step")
        return original(*args, **kwargs)

    monkeypatch.setattr(policy_step, "run_policy_step", count_steps)
    def crash_dispatch(*args, **kwargs):
        raise SystemExit("injected dispatch boundary")

    monkeypatch.setattr(consumer, "_model_request", crash_dispatch)
    with pytest.raises(SystemExit, match="injected dispatch boundary"):
        consumer.decide(seen, CHARTER, boundary=boundary,
                        experience=seen)
    row = _s09_row(store, cid, 0)
    assert dict(row["accepted_action"])["status"] == "pending"
    source_path = tmp_path / "policy.py"
    source_path.write_text(CRASH_SOURCE)
    seen_path = tmp_path / "seen.json"
    seen_path.write_text(json.dumps(seen))
    script = (
        "import json, sys\n"
        "dsn, cid, source_path, seen_path = sys.argv[1:5]\n"
        "from experiments.ad01 import policy_step, trajectory\n"
        "from experiments.ad01.agenda_policy import step_policy_consumer\n"
        "from experiments.ad01.learner import RecordingGatewayAdapter\n"
        "from experiments.ad01.policy_step import make_policy_artifact\n"
        "source = open(source_path).read()\n"
        "seen = json.load(open(seen_path))\n"
        "artifact = make_policy_artifact(source, origin='authored-control',\n"
        "    applicability={'world': 0, 'arm': 'I'})\n"
        "gateway = RecordingGatewayAdapter([{'text': 'resumed bytes'}])\n"
        "steps = []\n"
        "original = policy_step.run_policy_step\n"
        "def count_step(*args, **kwargs):\n"
        "    steps.append(kwargs.get('operation_id'))\n"
        "    return original(*args, **kwargs)\n"
        "policy_step.run_policy_step = count_step\n"
        "consumer = step_policy_consumer(artifact, dsn=dsn, cid=cid,\n"
        "    charter=%s, world=0, arm='I',\n"
        "    allocation_id=trajectory._alloc_id(cid), study_root=cid,\n"
        "    gateway=gateway, model='recorded-double')\n"
        "out = trajectory.resume_campaign(dsn, cid, %s,\n"
        "    {'max_boundaries': 1, 'diagnostic_queries': 16,\n"
        "     'model_calls': 60}, tasks=['%s'], consumer=consumer)\n"
        "print(json.dumps({'status': out['stop']['reason'],\n"
        "    'calls': 0 if gateway is None else len(gateway.calls),\n"
        "    'steps': steps}))\n"
        % (repr(CHARTER), repr(CHARTER), TASK))
    proc = subprocess.run(
        [sys.executable, "-c", script, store, cid, str(source_path),
         str(seen_path)], cwd=str(ROOT), capture_output=True, text=True,
        timeout=300, env=_env())
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {
        "status": "learner stop", "calls": 1,
        "steps": ["ad01-%s-policy-s0-k1" % cid]}
    assert len(calls) == 1
    assert len(_model_ops(store, cid, 0)) == 1


def test_settled_receipt_replays_at_zero_remaining(store, monkeypatch,
                                                   tmp_path):
    from experiments.ad01 import learner, packet, trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter

    cid = trajectory.campaign_id(0, "I", 87)
    gateway = RecordingGatewayAdapter([{"text": "settled before crash"}])
    consumer = _consumer(store, cid, CRASH_SOURCE, gateway=gateway)
    _admit_campaign(store, cid, [TASK])
    boundary = {"world": 0, "arm": "I", "seq": 0}
    seen = packet.decision_packet(
        charter=CHARTER, visible=learner.visible_opportunities(0),
        experience={"observations": [{"task_id": TASK}]}, retained=[],
        remaining={"model_calls": 1, "queries": 16, "boundaries": 1},
        curriculum=learner.curriculum_item(0, "I", 0), boundary=boundary)
    original = consumer._model_request

    def crash_after_settle(*args, **kwargs):
        original(*args, **kwargs)
        raise SystemExit("injected after settlement")

    monkeypatch.setattr(consumer, "_model_request", crash_after_settle)
    with pytest.raises(SystemExit, match="injected after settlement"):
        consumer.decide(seen, CHARTER, boundary=boundary,
                        experience=seen)
    model_ops = _model_ops(store, cid, 0)
    assert len(model_ops) == 1
    assert len(gateway.calls) == 1
    operation_id = model_ops[0]["id"]
    assert _receipt_text(store, operation_id) == "settled before crash"
    source_path = tmp_path / "policy.py"
    source_path.write_text(CRASH_SOURCE)
    script = (
        "import json, sys\n"
        "dsn, cid, source_path = sys.argv[1:4]\n"
        "from experiments.ad01 import policy_step, trajectory\n"
        "from experiments.ad01.agenda_policy import step_policy_consumer\n"
        "from experiments.ad01.learner import RecordingGatewayAdapter\n"
        "from experiments.ad01.policy_step import make_policy_artifact\n"
        "source = open(source_path).read()\n"
        "artifact = make_policy_artifact(source, origin='authored-control',\n"
        "    applicability={'world': 0, 'arm': 'I'})\n"
        "steps = []\n"
        "original = policy_step.run_policy_step\n"
        "def count_step(*args, **kwargs):\n"
        "    steps.append(kwargs.get('operation_id'))\n"
        "    return original(*args, **kwargs)\n"
        "policy_step.run_policy_step = count_step\n"
        "gateway = None\n"
        "consumer = step_policy_consumer(artifact, dsn=dsn, cid=cid,\n"
        "    charter=%s, world=0, arm='I',\n"
        "    allocation_id=trajectory._alloc_id(cid), study_root=cid,\n"
        "    gateway=gateway, model='recorded-double')\n"
        "out = trajectory.resume_campaign(dsn, cid, %s,\n"
        "    {'max_boundaries': 1, 'diagnostic_queries': 16,\n"
        "     'model_calls': 1}, tasks=['%s'], consumer=consumer)\n"
        "print(json.dumps({'status': out['stop']['reason'],\n"
        "    'calls': 0 if gateway is None else len(gateway.calls),\n"
        "    'steps': steps}))\n"
        % (repr(CHARTER), repr(CHARTER), TASK))
    proc = subprocess.run(
        [sys.executable, "-c", script, store, cid, str(source_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {
        "status": "learner stop", "calls": 0,
        "steps": ["ad01-%s-policy-s0-k1" % cid]}
    assert _model_ops(store, cid, 0) == model_ops
    assert _receipt_text(store, operation_id) == "settled before crash"
    row = _s09_row(store, cid, 0)
    assert dict(row["policy_input"])["views"][-1]["last_result"][
        "kind"] == "model_response"


def test_prepared_operation_replays_at_zero_remaining(store, monkeypatch,
                                                      tmp_path):
    from experiments.ad01 import learner, packet, trajectory
    from experiments.ad01.learner import RecordingGatewayAdapter
    from settlement import broker

    cid = trajectory.campaign_id(0, "I", 88)
    gateway = RecordingGatewayAdapter([{"text": "prepared before crash"}])
    consumer = _consumer(store, cid, CRASH_SOURCE, gateway=gateway)
    _admit_campaign(store, cid, [TASK])
    boundary = {"world": 0, "arm": "I", "seq": 0}
    seen = packet.decision_packet(
        charter=CHARTER, visible=learner.visible_opportunities(0),
        experience={"observations": [{"task_id": TASK}]}, retained=[],
        remaining={"model_calls": 1, "queries": 16, "boundaries": 1},
        curriculum=learner.curriculum_item(0, "I", 0), boundary=boundary)

    original_dispatch = broker.dispatch_operation

    def crash_dispatch(dsn, operation_id, *args, **kwargs):
        if operation_id.endswith("-model-k0"):
            raise SystemExit("injected after preparation")
        return original_dispatch(dsn, operation_id, *args, **kwargs)

    monkeypatch.setattr(broker, "dispatch_operation", crash_dispatch)
    with pytest.raises(SystemExit, match="injected after preparation"):
        consumer.decide(seen, CHARTER, boundary=boundary,
                        experience=seen)
    model_ops = _model_ops(store, cid, 0)
    assert len(model_ops) == 1
    operation_id = model_ops[0]["id"]
    assert broker.read_operation(store, operation_id)[
        "dispatch_state"] == "prepared"
    assert _receipt_text(store, operation_id) is None
    source_path = tmp_path / "policy.py"
    source_path.write_text(CRASH_SOURCE)
    script = (
        "import json, sys\n"
        "dsn, cid, source_path = sys.argv[1:4]\n"
        "from experiments.ad01 import policy_step, trajectory\n"
        "from experiments.ad01.agenda_policy import step_policy_consumer\n"
        "from experiments.ad01.learner import RecordingGatewayAdapter\n"
        "from experiments.ad01.policy_step import make_policy_artifact\n"
        "source = open(source_path).read()\n"
        "artifact = make_policy_artifact(source, origin='authored-control',\n"
        "    applicability={'world': 0, 'arm': 'I'})\n"
        "steps = []\n"
        "original = policy_step.run_policy_step\n"
        "def count_step(*args, **kwargs):\n"
        "    steps.append(kwargs.get('operation_id'))\n"
        "    return original(*args, **kwargs)\n"
        "policy_step.run_policy_step = count_step\n"
        "gateway = RecordingGatewayAdapter([{'text': 'prepared resumed'}])\n"
        "consumer = step_policy_consumer(artifact, dsn=dsn, cid=cid,\n"
        "    charter=%s, world=0, arm='I',\n"
        "    allocation_id=trajectory._alloc_id(cid), study_root=cid,\n"
        "    gateway=gateway, model='recorded-double')\n"
        "out = trajectory.resume_campaign(dsn, cid, %s,\n"
        "    {'max_boundaries': 1, 'diagnostic_queries': 16,\n"
        "     'model_calls': 1}, tasks=['%s'], consumer=consumer)\n"
        "print(json.dumps({'status': out['stop']['reason'],\n"
        "    'calls': len(gateway.calls), 'steps': steps}))\n"
        % (repr(CHARTER), repr(CHARTER), TASK))
    proc = subprocess.run(
        [sys.executable, "-c", script, store, cid, str(source_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {
        "status": "learner stop", "calls": 1,
        "steps": ["ad01-%s-policy-s0-k1" % cid]}
    assert _model_ops(store, cid, 0) == model_ops
    assert _receipt_text(store, operation_id) == "prepared resumed"
    row = _s09_row(store, cid, 0)
    assert dict(row["policy_input"])["views"][-1]["last_result"][
        "kind"] == "model_response"
