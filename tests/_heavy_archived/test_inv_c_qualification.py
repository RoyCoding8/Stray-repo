"""INV-C qualification: doubles through the public entry, acquired program, envelope, replay.

Real Postgres (inv_c_qual via INV_C_DSN, inv_c_qual2 via INV_C_DSN2, never
live) in every brokered test. Doubles sit at the gateway seam only, from
experiments.doubles: every learner and construction call travels through
broker ensure, dispatch, settled receipts and measured costs. Every
assertion names a literal durable outcome: settled receipt bytes equal to
recorded script bytes, retained method bytes equal through freeze into
fresh-process use, zero new operations across completed-boundary replay,
refused rerun on an unbound database with zero new writes, sequenced
allowances, refused unbound-database reruns, and replay refusals.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

DSN = os.environ.get(
    "INV_C_DSN",
    "dbname=inv_c_qual host=/var/run/postgresql user=ubuntu")
DSN2 = os.environ.get(
    "INV_C_DSN2",
    "dbname=inv_c_qual2 host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 96,
        "model_calls": 60, "construction_tokens": 2048,
        "agenda_authorized": 100000}
MODEL = "inv-c-double"


def _use_policy_file(tmp_path, method_id: str):
    """A policy that admits the one use_method the repertoire holds.

    The use phase refuses without a policy, and that refusal is deliberate:
    a use record with no policy behind it is not a measurement of anything.
    These tests predate that requirement, so they now state a policy the way
    a user has to.
    """
    import hashlib
    source = (
        "def STEP(view, state):\n"
        "    task = view['task_content']\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                      'target': task['task_id'],\n"
        "                      'inputs': {'method_id': %r,"
        " 'max_queries': 16},\n"
        "                      'evidence_refs': [],\n"
        "                      'requested_resources': {'queries': 16}},\n"
        "            'state': {'used': True}}\n" % method_id
    )
    path = tmp_path / ("use_policy_%s.py"
                       % hashlib.sha256(source.encode()).hexdigest()[:8])
    path.write_text(source)
    return path
SW0 = "ad01-w0-dev-sw-00"
SW1 = "ad01-w0-dev-sw-01"
GR0 = "ad01-w0-dev-gr-00"


def _fresh_db(dsn: str):
    assert "live" not in dsn
    from settlement import db
    from experiments.coord02 import experience as E
    db.apply_migrations(dsn, MIGRATIONS)
    E.designate_db(dsn, kind="disposable",
                   purpose="INV-C qualification gate")
    E.prepare_disposable_db(dsn, MIGRATIONS)


def _double(learner_scripts, init=None, repair=None):
    from experiments import doubles as D
    return D.InvCQualificationDouble(
        learner_scripts=learner_scripts, init_scripts=init,
        repair_scripts=repair)


def _run(world, arm, tasks, scripts, dsn, seq=0, init=None, repair=None):
    from experiments.ad01 import learner, trajectory
    gateway = _double(scripts, init, repair)
    cid = trajectory.campaign_id(world, arm, seq)
    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    seed = trajectory.ensure_campaign(
        dsn, cid, world, arm, dict(CHARTER),
        dict(CAPS), tasks=list(tasks))
    propose = learner.propose_from_model(
        dsn, cid=cid, gateway=gateway, model=MODEL,
        charter=dict(CHARTER), world=world, arm=arm,
        allocation_id=seed["allocation_id"])
    campaign = trajectory.run_campaign(
        world, arm, dict(CHARTER), dict(CAPS), tasks=list(tasks),
        propose=propose, campaign_seq=seq, dsn=dsn,
        gateway=gateway, model=MODEL, constructor="model")
    return cid, gateway, campaign


def _op_ids(dsn, prefix):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        return sorted(r["id"] for r in conn.execute(
            "SELECT id FROM operations WHERE starts_with(id, %s)",
            (prefix,)).fetchall())


def _receipts(dsn, operation_id):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        return conn.execute(
            "SELECT receipt_identity, content, outcome FROM receipts"
            " WHERE operation_id = %s ORDER BY receipt_identity",
            (operation_id,)).fetchall()


def _counts(dsn):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(dsn) as conn:
        ops = conn.execute("SELECT count(*) AS n FROM operations").fetchone()["n"]
        receipts = conn.execute("SELECT count(*) AS n FROM receipts").fetchone()["n"]
    return ops, receipts


def test_entry_drives_learner_and_construction_through_broker(tmp_path):
    from experiments import doubles as D
    from experiments.ad01 import trajectory
    _fresh_db(DSN)
    tasks = [SW0, SW1, GR0]
    scripts = [D.learner_diagnostic_text(SW0, "software"),
               D.learner_development_text(SW1, "software"),
               D.learner_development_text(GR0, "graph")]
    cid, gateway, campaign = _run(0, "I", tasks, scripts, DSN)
    learner_ops = _op_ids(DSN, "ad01-%s-learner-" % cid)
    assert len(learner_ops) == 3, learner_ops
    for op_id in learner_ops:
        rows = _receipts(DSN, op_id)
        assert [r["receipt_identity"] for r in rows] == ["gw:%s" % op_id]
        assert rows[0]["outcome"] == "success"
        assert rows[0]["content"]["text"] == gateway.records[op_id]["response"]
        assert rows[0]["content"]["model_meta"]["simulated"] is True
        assert rows[0]["content"]["usage"]["billed"] is False
    construct_ops = [o for o in _op_ids(DSN, "ad01-%s-" % cid)
                     if "-construct-l" in o and o.endswith("-init")]
    assert len(construct_ops) == 2, construct_ops
    for op_id in construct_ops:
        rows = _receipts(DSN, op_id)
        assert rows and rows[0]["outcome"] == "success"
        assert rows[0]["content"]["text"] == gateway.records[op_id]["response"]
        assert rows[0]["content"]["model_meta"]["simulated"] is True
    validate_ops = [o for o in _op_ids(DSN, "ad01-%s-" % cid)
                    if "-validate-l" in o]
    assert len(validate_ops) == 2, validate_ops
    assert campaign["model_calls"] == len(learner_ops) + len(construct_ops) == 5
    assert [e["disposition"] for e in campaign["episodes"]] == \
        ["inspected", "retained", "retained"]
    assert campaign["boundaries"][0]["task_id"] == SW0
    assert not [o for o in _op_ids(DSN, "ad01-%s-b0-" % cid)
                if "-construct-" in o]
    members = [e["executable"] for e in campaign["episodes"]
               if e.get("disposition") == "retained"]
    assert len(members) == 2
    for member in members:
        source = member["method_source"]
        assert hashlib.sha256(source.encode()).hexdigest() == \
            member["source_digest"]
    frozen = tmp_path / "repertoire.json"
    repertoire = trajectory.freeze_repertoire(campaign, frozen)
    assert len(repertoire["members"]) == 2
    reloaded = trajectory.load_repertoire(frozen)
    membership = trajectory.worlds.world_membership(
        trajectory.worlds.FROZEN_DIR)
    use_tasks = [membership["0"]["within"]["software"][0],
                 membership["0"]["within"]["graph"][0]]
    # The use phase refuses without a policy, and the two families hold
    # different methods, so the CLI is driven once per family with a policy
    # that names the member that family actually holds.
    by_family = {}
    for family in ("software", "graph"):
        retained = next(m for m in reloaded["members"]
                        if m["scope"]["family"] == family)
        proc = subprocess.run(
            [sys.executable, "-m", "experiments.ad01.cli", "use",
             "--repertoire", str(frozen), "--world", "0", "--arm", "I",
             "--tasks", use_tasks[
                 0 if family == "software" else 1],
             "--dsn", DSN,
             "--policy-source", str(_use_policy_file(
                 tmp_path, retained["capability_id"])),
             "--allocation-id", trajectory._alloc_id(cid)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr
        [record] = json.loads(proc.stdout)
        by_family[record["domain"]] = record
    assert len(by_family) == 2
    for family in ("software", "graph"):
        retained = next(m for m in reloaded["members"]
                        if m["scope"]["family"] == family)
        assert by_family[family]["executed_source"] == \
            retained["method_source"]
        assert hashlib.sha256(
            by_family[family]["executed_source"].encode()).hexdigest() == \
            retained["source_digest"]
    accounting = trajectory.cost_union(campaign, [], dsn=DSN)
    assert accounting["total"]["model_calls"] == 5
    assert accounting["total"]["tokens"] is None


def test_rejected_then_corrected_proposal():
    from experiments import doubles as D
    _fresh_db(DSN)
    tasks = [SW0, GR0]
    scripts = [D.learner_text(
        {"basis_references": ["obs-invented-999"],
         "question": "invented leap at %s" % SW0,
         "next_action": {"kind": "development", "diagnostic": "software",
                         "task_id": SW0, "max_queries": 4},
         "requested_resources": {"diagnostic_queries": 1}}),
        D.learner_development_text(SW0, "software"),
        D.learner_development_text(GR0, "graph")]
    cid, gateway, campaign = _run(0, "R", tasks, scripts, DSN)
    assert campaign["episodes"][0]["disposition"] in ("retained", "rejected")
    if campaign["episodes"][0]["disposition"] == "rejected":
        assert "construction" in campaign["episodes"][0]["reason"]
    assert campaign["episodes"][1]["disposition"] in ("retained", "rejected")
    if campaign["episodes"][1]["disposition"] == "rejected":
        assert "construction" in campaign["episodes"][1]["reason"]
    learner_ops = _op_ids(DSN, "ad01-%s-learner-" % cid)
    assert len(learner_ops) == 3
    assert "invented basis references" in \
        gateway.records[learner_ops[1]]["prompt"]
    for op_id in learner_ops:
        rows = _receipts(DSN, op_id)
        assert rows and rows[0]["outcome"] == "success"
        assert rows[0]["content"]["text"] == gateway.records[op_id]["response"]
    assert len(gateway.calls) == len(learner_ops) + len(
        [o for o in _op_ids(DSN, "ad01-%s-" % cid)
         if "-construct-l" in o])


def test_no_candidate_incumbent_use():
    from experiments.ad01 import checker, trajectory
    from experiments.ad01.learner import LearnerRefused
    _fresh_db(DSN)

    def _refuse(experience, charter):
        raise LearnerRefused("zero budget at seq %s"
                             % experience["boundary"]["seq"])

    trajectory.authorize_campaign(
        DSN, trajectory.campaign_id(0, "I", 0), authorized=100000)
    campaign = trajectory.run_campaign(
        0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0],
        propose=_refuse, campaign_seq=0, dsn=DSN)
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "no-candidate"
    assert episode["fallback"] == "incumbent"
    assert episode["queries"] == 0
    cid = campaign["campaign_id"]
    empty = {"campaign_id": cid, "members": [], "queries": 0}
    trajectory.ensure_campaign(
        DSN, cid, 0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0])
    records = trajectory.run_use(
        empty, 0, "I", [SW0, GR0], {},
        dsn=DSN, allocation_id=trajectory._alloc_id(cid))
    assert len(records) == 2
    for record in records:
        # An empty repertoire and no policy used to answer `incumbent`, which
        # reads exactly like a method that ran and found nothing. The use
        # phase now refuses, and the refusal is a distinct `status` so a
        # caller branching on `selected` or `executed` alone cannot mistake
        # it for execution. A `preserved` verdict here would have claimed a
        # preservation that nothing measured.
        assert record["status"] == "refused"
        assert record["requested"] == "refused"
        assert record["selected"] == "refused"
        assert record["executed"] == "refused"
        assert record["executed_source"] == "refused"
        assert record["verdict"] == "refused"
        assert record["normalized_reduction"] == 0.0
        assert record["costs"]["witness_queries"] == 0
        assert record["fallback_reason"]
    membership = trajectory.worlds.world_membership(
        trajectory.worlds.FROZEN_DIR)
    sweep = []
    for world in (0, 1, 2):
        for arm in ("I", "R"):
            cid = trajectory.campaign_id(world, arm, 0)
            trajectory.authorize_campaign(DSN, cid, authorized=100000)
            trajectory.ensure_campaign(
                DSN, cid, world, arm, dict(CHARTER), dict(CAPS))
            use_tasks = []
            for pool in ("within", "transfer"):
                for domain in ("software", "graph"):
                    use_tasks.extend(
                        membership[str(world)][pool][domain][:3])
            sweep.extend(trajectory.run_use(
                {"campaign_id": cid, "members": [], "queries": 0},
                world, arm, use_tasks, {},
                dsn=DSN, allocation_id=trajectory._alloc_id(cid)))
    assert len(sweep) == 72
    assert {record["status"] for record in sweep} == {"refused"}
    verdict = checker.verify_use_records(
        sweep, trajectory.worlds.FROZEN_DIR)
    assert verdict["problems"] == []


def test_two_domain_packets():
    from experiments import doubles as D
    from experiments.ad01 import trajectory
    from experiments.representation import checkers
    _fresh_db(DSN)
    tasks = [SW0, GR0]
    scripts = [D.learner_development_text(SW0, "software"),
               D.learner_development_text(GR0, "graph")]
    cid, _gateway, campaign = _run(0, "I", tasks, scripts, DSN)
    assert [e["disposition"] for e in campaign["episodes"]] == \
        ["retained", "retained"]
    prompts = {}
    with trajectory._read_conn(DSN) as conn:
        for row in conn.execute(
                "SELECT id, payload FROM operations WHERE starts_with(id, %s)",
                ("ad01-%s-" % cid,)).fetchall():
            if "-construct-l" in row["id"] and row["id"].endswith("-init"):
                messages = row["payload"]["payload"]["messages"]
                prompts[row["id"]] = messages[-1]["content"]
    assert len(prompts) == 2
    sw_prompt = next(v for k, v in prompts.items() if "-sw-" in k)
    gr_prompt = next(v for k, v in prompts.items() if "-gr-" in k)
    for key in ("family", "task_id", "ops", "witness"):
        assert key in sw_prompt
    for key in ("family", "task_id", "vertices", "edges"):
        assert key in gr_prompt
    assert "reduce_software" in sw_prompt
    assert "reduce_graph" in gr_prompt
    assert "oracle.query" in sw_prompt and "oracle.query" in gr_prompt
    for reason in sorted(checkers.SOFTWARE_REASONS):
        assert reason in sw_prompt
    for reason in sorted(checkers.GRAPH_REASONS):
        assert reason in gr_prompt
    episodes = {e["task_id"]: e for e in campaign["episodes"]}
    assert episodes[SW0]["check"]["verdict"] == "preserved"
    assert episodes[GR0]["check"]["verdict"] == "preserved"
    assert "ops" in episodes[SW0]["candidate"]
    assert "vertices" in episodes[GR0]["candidate"]
    sw_task = trajectory.worlds.load_task(
        trajectory.worlds.FROZEN_DIR, SW0)
    gr_task = trajectory.worlds.load_task(
        trajectory.worlds.FROZEN_DIR, GR0)
    assert checkers.check_software(
        sw_task, episodes[SW0]["candidate"])["verdict"] == "preserved"
    assert checkers.check_graph(
        gr_task, episodes[GR0]["candidate"])["verdict"] == "preserved"


def test_completed_boundaries_replay_without_respend(tmp_path):
    from experiments import doubles as D
    from experiments.ad01 import trajectory
    _fresh_db(DSN)
    diag_cid, _diag_gateway, diag_campaign = _run(
        0, "I", [SW0], [D.learner_diagnostic_text(SW0, "software")], DSN,
        seq=7)
    assert [e["disposition"] for e in diag_campaign["episodes"]] == \
        ["inspected"]
    assert not [o for o in _op_ids(DSN, "ad01-%s-" % diag_cid)
                if "-construct-" in o]
    before = _counts(DSN)
    settled_before, _pending = trajectory._read_campaign(DSN, diag_cid)
    rec_path = tmp_path / "diag-recordings.json"
    rec_path.write_text(json.dumps(
        [{"text": D.learner_diagnostic_text(SW0, "software")}] ) + "\n")
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "resume",
         "--dsn", DSN, "--campaign", diag_cid, "--max-boundaries", "6",
         "--agenda-authorized", "100000", "--tasks", SW0,
         "--recordings", str(rec_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    resumed = json.loads(proc.stdout)
    assert [b["task_id"] for b in resumed["boundaries"]] == [SW0]
    assert all(b["resumed"] is True for b in resumed["boundaries"])
    assert _counts(DSN) == before
    settled_after, _pending = trajectory._read_campaign(DSN, diag_cid)
    assert settled_after == settled_before
    tasks = [SW0, "ad01-w0-dev-sw-02"]
    scripts = [D.learner_diagnostic_text(SW0, "software"),
               D.learner_development_text("ad01-w0-dev-sw-02", "software")]
    cid, _gateway, campaign = _run(0, "I", tasks, scripts, DSN, seq=8)
    assert [e["disposition"] for e in campaign["episodes"]] == \
        ["inspected", "retained"]
    before = _counts(DSN)
    settled_before, _pending = trajectory._read_campaign(DSN, cid)
    cost_before = trajectory.cost_union(campaign, [], dsn=DSN)
    rec_path = tmp_path / "recordings.json"
    rec_path.write_text(json.dumps([{"text": s} for s in scripts]) + "\n")
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "resume",
         "--dsn", DSN, "--campaign", cid, "--max-boundaries", "6",
         "--agenda-authorized", "100000", "--tasks", ",".join(tasks),
         "--recordings", str(rec_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    resumed = json.loads(proc.stdout)
    assert [e["disposition"] for e in resumed["episodes"]] == \
        ["inspected", "retained"]
    assert [e["queries"] for e in resumed["episodes"]] == \
        [e["queries"] for e in campaign["episodes"]]
    assert _counts(DSN) == before
    settled_after, _pending = trajectory._read_campaign(DSN, cid)
    assert settled_after == settled_before
    assert resumed["accounting"]["total"] == cost_before["total"]
    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps(
        {"campaign_id": cid, "members": [], "queries": 0}) + "\n")
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli", "use",
         "--repertoire", str(empty_path), "--world", "0", "--arm", "I",
         "--tasks", SW0, "--dsn", DSN,
         "--allocation-id", trajectory._alloc_id(cid)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    [record] = json.loads(proc.stdout)
    # An empty repertoire with no policy used to answer `incumbent`, which
    # reads exactly like a method that ran and preserved the task. It
    # refuses, and the refusal names why, because `preserved` here would
    # claim a measurement nobody made.
    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert record["executed_source"] == "refused"
    assert record["fallback_reason"]


def test_envelope_sequences_diagnostic_construction_repair(tmp_path):
    from settlement import broker, store
    from settlement.launcher_local import LocalLauncher
    from settlement.loop import ResourceEnvelope, admit_effect, \
        read_measured_costs
    from experiments import doubles as D
    from experiments.ad01 import controls
    _fresh_db(DSN)
    envelope = ResourceEnvelope.bind(DSN, "inv-c-seq", 100000)
    gateway = D.InvCQualificationDouble(
        learner_scripts=[{"text": "{\"answer\": 1}"}])
    launcher = LocalLauncher(tmp_path / "runs")
    start = envelope.remaining(DSN)
    granted = admit_effect(
        DSN, allocation_id="inv-c-seq", operation_id="inv-c-diag-1",
        effect=broker.MODEL_INFERENCE,
        payload={"model": MODEL,
                 "messages": [{"role": "user", "content": "diagnose"}],
                 "max_output_tokens": 16, "deadline_ms": 300_000},
        attempt_id=None, kind="diagnostic")
    assert granted.operation_id == "inv-c-diag-1"
    status = broker.dispatch_operation(
        DSN, "inv-c-diag-1", launchers={}, gateway=gateway)
    assert status.dispatch_state == "observed"
    measured = read_measured_costs(DSN, "inv-c-diag-1")
    assert measured["measured"] == 0
    assert measured["receipts"] == ["gw:inv-c-diag-1"]
    assert measured["unknown"] == []
    after_diagnostic = envelope.remaining(DSN)
    # The reservation is the broker's formula, not a number copied out of an
    # earlier run: `sum(len(content)) // 4 + 1 + max_output_tokens`, times
    # retries. Asking the broker what it charges keeps the test from going
    # quietly wrong when that formula changes.
    reserved, kind = broker.exposure_schedule(
        broker.MODEL_INFERENCE,
        {"model": MODEL,
         "messages": [{"role": "user", "content": "diagnose"}],
         "max_output_tokens": 16})
    assert kind == "estimated-budget"
    assert after_diagnostic == start - reserved
    spend = controls.novel_order_unproductive(GR0, 4)["queries"]
    assert spend == 4
    construction_granted = ResourceEnvelope.sequence_construction_allowance(
        6, spend)
    assert construction_granted == 1
    assert construction_granted <= 6 - spend - 1
    assert construction_granted + spend + 1 == 6
    build = admit_effect(
        DSN, allocation_id="inv-c-seq", operation_id="inv-c-build-1",
        effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 10_000, "max_output_bytes": 1024},
        attempt_id=None, kind="construction")
    assert broker.dispatch_operation(
        DSN, "inv-c-build-1",
        launchers={"local-process": launcher}).dispatch_state == "observed"
    repair = admit_effect(
        DSN, allocation_id="inv-c-seq", operation_id="inv-c-repair-1",
        effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 10_000, "max_output_bytes": 1024},
        attempt_id=None, kind="repair")
    assert broker.dispatch_operation(
        DSN, "inv-c-repair-1",
        launchers={"local-process": launcher}).dispatch_state == "observed"
    for operation_id in ("inv-c-build-1", "inv-c-repair-1"):
        costs = read_measured_costs(DSN, operation_id)
        assert len(costs["receipts"]) == 1
        assert costs["unknown"] == []
    ledger = store.allocation_status(DSN, "inv-c-seq")
    # `11 + 7` was copied out of an earlier run of this test and had been
    # wrong for some time: it is the consumed total, and consumption is the
    # exposure each admitted effect reserved, not a figure retyped by hand.
    assert ledger["consumed"] == reserved + build.exposure + repair.exposure
    assert ledger["consumed"] <= 100000
    assert envelope.remaining(DSN) == start - ledger["consumed"]


def test_cross_database_no_renewal():
    from settlement import broker
    from settlement.common import ResultCode
    from experiments import doubles as D
    from experiments.ad01 import learner, trajectory
    _fresh_db(DSN)
    _fresh_db(DSN2)
    tasks = [SW0, SW1, GR0]
    scripts = [D.learner_diagnostic_text(SW0, "software"),
               D.learner_development_text(SW1, "software"),
               D.learner_development_text(GR0, "graph")]
    cid, gateway, campaign = _run(0, "I", tasks, scripts, DSN)
    first = trajectory.cost_union(campaign, [], dsn=DSN)
    with trajectory._read_conn(DSN) as conn:
        authorized_first = conn.execute(
            "SELECT authorized FROM allocations WHERE id = %s",
            (trajectory._alloc_id(cid),)).fetchone()["authorized"]
    learner_op = "ad01-%s-learner-0" % cid
    with trajectory._read_conn(DSN) as conn:
        payload = conn.execute(
            "SELECT payload->'payload' AS effect_payload FROM operations"
            " WHERE id = %s",
            (learner_op,)).fetchone()["effect_payload"]
    restated = broker.ensure_operation(
        DSN, operation_id=learner_op, effect=broker.MODEL_INFERENCE,
        payload=payload, allocation_id=trajectory._alloc_id(cid))
    assert restated.code == ResultCode.ALREADY_APPLIED
    fresh = D.InvCQualificationDouble(learner_scripts=list(scripts))
    propose = learner.propose_from_model(
        DSN, cid=cid, gateway=fresh, model=MODEL,
        charter=dict(CHARTER), world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid))
    resumed = trajectory.resume_campaign(
        DSN, cid, dict(CHARTER), dict(CAPS), tasks=list(tasks),
        propose=propose, gateway=fresh, model=MODEL,
        constructor="model")
    assert fresh.calls == []
    assert [e["disposition"] for e in resumed["episodes"]] == \
        ["inspected", "retained", "retained"]
    assert trajectory.cost_union(resumed, [], dsn=DSN)["total"] == \
        first["total"]
    fresh = D.InvCQualificationDouble(learner_scripts=list(scripts))
    propose = learner.propose_from_model(
        DSN2, cid=cid, gateway=fresh, model=MODEL,
        charter=dict(CHARTER), world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid))
    with pytest.raises(ValueError, match="agenda authority"):
        trajectory.run_campaign(
            0, "I", dict(CHARTER), dict(CAPS), tasks=list(tasks),
            propose=propose, campaign_seq=0, dsn=DSN2,
            gateway=fresh, model=MODEL, constructor="model")
    assert fresh.calls == []
    with trajectory._read_conn(DSN2) as conn:
        assert conn.execute("SELECT id FROM allocations").fetchall() == []
        assert conn.execute("SELECT id FROM operations").fetchall() == []


def test_replay_boundary_refusals():
    from settlement import broker
    from settlement.gateway import GatewayError, GatewayErrorKind
    from settlement.loop import ExperienceTransition, ResourceEnvelope, \
        materialize_packet, run_boundary
    from experiments import doubles as D
    from experiments.ad01 import checker, packet
    from experiments.ad01 import worlds
    _fresh_db(DSN)
    envelope = ResourceEnvelope.bind(DSN, "inv-c-replay", 100000)
    assert envelope.remaining(DSN) == 100000

    class _Flaky:
        def __init__(self, texts):
            self._texts = list(texts)
            self.calls = []

        def infer(self, request):
            from settlement.gateway import ModelResponse, Usage
            self.calls.append(request)
            if len(self.calls) == 2:
                return GatewayError(GatewayErrorKind.TRANSPORT,
                                    "link down", False,
                                    request.operation_id)
            return ModelResponse(
                request.operation_id, self._texts[0],
                {"simulated": True},
                Usage(input_tokens=3, output_tokens=3), "stop")

        def cancel(self, operation_id):
            return False

    gateway = _Flaky(['{"answer": 1}'])
    versions = {"model": MODEL, "packet_version": packet.PACKET_VERSION,
                "protocol": "broker-v1", "profile": "local-process",
                "freeze_digest": checker.freeze_digest(worlds.FROZEN_DIR)}
    packets = [packet.decision_packet(
        charter=dict(CHARTER), visible=[SW0, GR0],
        experience={"observations": []}, retained=[],
        remaining={"queries": 6, "model_calls": 60},
        curriculum=None, boundary={"world": 0, "arm": "I", "seq": i})
        for i in (0, 1)]

    def _propose(deps, tag):
        def _go(materialized, state):
            return {"target": "t-replay", "instrument": "diagnose",
                    "inputs": {"model": MODEL, "prompt": "look-%s" % tag,
                               "max_output_tokens": 16, **versions},
                    "dependencies": list(deps), "requested": {"queries": 1},
                    "hypothesis": None}
        return _go

    first, _state = run_boundary(
        DSN, study_root="inv-c-replay", allocation_id="inv-c-replay",
        packet=packets[0], propose=_propose(["dep-a", "dep-b"], 0),
        gateway=gateway)
    assert first.admission == "admitted"
    second, _state = run_boundary(
        DSN, study_root="inv-c-replay", allocation_id="inv-c-replay",
        packet=packets[1], propose=_propose(["dep-a", "dep-b"], 1),
        gateway=gateway)
    assert second.admission == "admitted"
    assert second.costs_unknown == list(second.results) != []
    # 59a10df replaced `:unknown` with the response class, so a lost
    # response is now distinguishable from any other unpriced outcome.
    # `:unknown` no longer names anything the broker emits.
    assert second.results[0].endswith(":lost-response")
    recorded = ExperienceTransition.read_journal(DSN, "inv-c-replay")
    assert len(recorded) == 2
    assert packets[0] == packet.decision_packet(
        charter=dict(CHARTER), visible=[SW0, GR0],
        experience={"observations": []}, retained=[],
        remaining={"queries": 6, "model_calls": 60},
        curriculum=None, boundary={"world": 0, "arm": "I", "seq": 0})
    assert broker.read_operation(
        DSN, recorded[1]["operations"][0]) is not None
    assert recorded[1]["results"] == list(second.results) != []
    assert recorded[1]["costs_unknown"] == list(second.costs_unknown) != []

    def _probe(index, **overrides):
        rec = recorded[index]
        proposal = dict(rec["proposal"])
        base = {"index": index, "packet_digest": rec["packet_digest"],
                "action": {"target": proposal["target"],
                           "instrument": proposal["instrument"],
                           "inputs": dict(proposal["inputs"]),
                           "dependencies": list(
                               proposal.get("dependencies", [])),
                           "requested": dict(proposal.get("requested", {}))},
                "versions": dict(versions),
                "observations": list(recorded[index - 1]["results"])
                if index else []}
        base.update(overrides)
        return base

    supported = D.check_replay_prefix(recorded, _probe(1))
    assert supported["verdict"] == "supported"
    assert supported["results"] == recorded[1]["results"]
    assert supported["costs_unknown"] == recorded[1]["costs_unknown"]
    assert "lost-response" in supported["costs_unknown"][0]
    future = D.check_replay_prefix(
        recorded, _probe(0, observations=list(recorded[1]["results"])))
    assert future["verdict"] == "unsupported"
    assert "hidden-future" in future["reason"]
    assert future["results"] == []
    stale = dict(versions, model="other-model")
    mismatch = D.check_replay_prefix(recorded, _probe(1, versions=stale))
    assert mismatch["verdict"] == "unsupported"
    assert "version-mismatch" in mismatch["reason"]
    assert mismatch["results"] == []
    reordered = D.check_replay_prefix(
        recorded, _probe(1, action={**_probe(1)["action"],
                                    "dependencies": ["dep-b", "dep-a"]}))
    assert reordered["verdict"] == "unsupported"
    assert "reordered-dependents" in reordered["reason"]
    assert reordered["results"] == []
    rewritten = D.check_replay_prefix(
        recorded, _probe(1, action={**_probe(1)["action"], "inputs": {
            **_probe(1)["action"]["inputs"], "prompt": "forged"}}))
    assert rewritten["verdict"] == "unsupported"
    assert "new-code-bytes" in rewritten["reason"]
    assert rewritten["results"] == []
    malformed = D.check_replay_prefix(recorded, {"index": 1})
    assert malformed["verdict"] == "refused"
    assert malformed["reason"] != ""
    assert malformed["results"] == []
    stale_packet = dict(packets[0], packet_version="ad01-packet-v0")
    assert materialize_packet(stale_packet)["outcome"] == "stale"


def test_repair_lineage_uses_settled_bytes():
    from experiments import doubles as D
    from experiments.ad01 import construct, trajectory
    _fresh_db(DSN)
    cid = trajectory.campaign_id(0, "I", 40)
    trajectory.authorize_campaign(DSN, cid, authorized=100000)
    trajectory.ensure_campaign(
        DSN, cid, 0, "I", dict(CHARTER), dict(CAPS), tasks=[SW0])
    gateway = D.InvCQualificationDouble(
        learner_scripts=[],
        init_scripts=[{"text": "not python {{{",
                       "notes": "broken init"}])
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR, SW0)
    member = construct.construct_method(
        DSN, campaign_id=cid, task=task,
        experience={"observations": [],
                    "boundary": {"seq": 0}},
        budget={"max_output_tokens": 512, "max_queries": 16,
                "model_calls": 4},
        gateway=gateway, model=MODEL)
    lineage = member["lineage"]
    assert lineage["repair_operation"] is not None
    assert lineage["init_failure"] is not None
    assert lineage["calls_made"] == 2
    init_op = lineage["init_operation"]
    repair_op = lineage["repair_operation"]
    assert init_op.endswith("-init") and repair_op.endswith("-repair")
    for op_id in (init_op, repair_op):
        rows = _receipts(DSN, op_id)
        assert rows and rows[0]["outcome"] == "success"
        assert rows[0]["content"]["text"] == gateway.records[op_id]["response"]
        assert rows[0]["content"]["model_meta"]["simulated"] is True
    report = trajectory._check(task, member["validation"]["result"]["candidate"])
    assert report["verdict"] == "preserved"
    assert member["method_source"] == D.ACQUIRED_ORDER_SOURCE
