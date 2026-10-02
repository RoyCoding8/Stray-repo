"""Suspend and resume on the mission entry, and one resume owner.

Lane C1 built one durable mission entry (`experiments/ad01/mission.py` over
`investigations`). This lane adds the two halves a restart needs and removes
the competing owners.

Before this, three places could answer "what was in flight, and how does it
resume":

- `s09_policy_state.accepted_action` holds the admitted decision, but nothing
  records the *program digest* that admitted it or the *input identity* it
  was admitted under, so a restart cannot know which program it is finishing;
- `context.resume_package` reads `continuation_docs`, a parallel
  continuation document with its own key and its own `unresolved_ops`;
- `run.suspend_for_barrier` suspends an attempt and writes nothing that names
  the operation it suspended.

The property under test is narrow and is the reason this lane exists: a
pending operation that crosses a restart keeps the program identity and input
identity it was admitted under. Not a recomputed one, not a default. A study
that resumes under a substituted program is measuring a different thing than
it claims, and nothing downstream would say so.

Every program byte here is this lane's own. No other lane's fixture is
reused, so a self-consistent fixture cannot pass for a retention check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "c6suspend"
CHARTER = {"objective": "hold a pending operation across a restart",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20}
DEV_TASK = "ad01-w0-dev-sw-00"
SEQ = 41

# The program that admits the pending operation, and the decision it admits
# under. Both are literals so the test asserts a retained identity rather
# than two digests that happen to agree.
C6_PROGRAM = (
    "def STEP(view, state):\n"
    "    return {'action': {'kind': 'stop', 'target': 'c6-barrier',\n"
    "                       'inputs': {'reason': 'held at the barrier'}},\n"
    "            'state': dict(state)}\n"
)
C6_PROGRAM_DIGEST = (
    "21bc17cde3811fd4d3fa0289278f63c3afe0108f0ef4438915040219cf390093")

C6_DECISION = {"basis_references": [],
               "question": "c6 held boundary",
               "next_action": {"kind": "diagnostic", "task_id": DEV_TASK,
                               "diagnostic": "software",
                               "capability_id": "seed-sw-greedy"}}
C6_DECISION_DIGEST = (
    "398b8f96218af6d1922c8202613b292a76b537b549c752261daeb297acf83bac")
C6_INPUT_IDENTITY = (
    "85273e1514b9f5cd370d91c73315b856be3a9a3c6a9189c81a548de7f1bf529b")

BARRIER_REF = "c6-barrier-ref-1"


def _import_hashlib():
    import hashlib

    return hashlib


def test_the_asserted_digests_are_the_real_ones():
    """The literals are computed, not trusted.

    A hand-copied digest is a comment. These three are derived from the
    bytes above with the same rule `mission` uses, so a later edit to the
    program or the decision cannot leave the test asserting a stale identity
    that nothing produces.
    """
    hashlib = _import_hashlib()
    assert hashlib.sha256(C6_PROGRAM.encode()).hexdigest() == C6_PROGRAM_DIGEST
    wire = json.dumps(C6_DECISION, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(wire).hexdigest() == C6_DECISION_DIGEST
    identity = json.dumps({"decision": C6_DECISION, "task_id": DEV_TASK,
                           "capability_id": "seed-sw-greedy"},
                          sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(identity).hexdigest() == C6_INPUT_IDENTITY


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


def _cid(seq: int) -> str:
    from experiments.ad01 import trajectory

    trajectory.set_namespace_token("")
    return trajectory.campaign_id(0, "I", seq)


def _held(store, seq):
    """Admit one operation and hold it, the way a crash mid-flight leaves it.

    `accept_action` is the seam: the decision is durable and its attempt is
    running, and the effect has not run. The program identity is declared
    here because the admitting caller is the only place that knows it.
    """
    from experiments.ad01 import mission, trajectory

    cid = _cid(seq)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    made = trajectory.ensure_campaign(store, cid, 0, "I", CHARTER, CAPS,
                                      tasks=[DEV_TASK])
    assert made["admitted"] is True, "the campaign admitted nothing"
    attempt_id = trajectory.accept_action(store, cid, 0, C6_DECISION,
                                          program_digest=C6_PROGRAM_DIGEST)
    assert attempt_id == "att-%s-0" % cid
    entry = mission.read_in_flight(store, cid)
    assert len(entry) == 1, "the held operation is not on the mission entry"
    return cid, entry[0]


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s:%s" % (ROOT, ROOT / "src", ROOT / "experiments")
    return env


# Phase A admits the operation and dies. Phase B is a second interpreter that
# resumes it. Nothing but the database crosses between them, so anything the
# second process knows about the program identity it read from the row.
_ACCEPT_PHASE = (
    "import json, os, sys\n"
    "from experiments.ad01 import mission, trajectory\n"
    "dsn, cid = sys.argv[1:3]\n"
    "decision = json.loads(sys.argv[3])\n"
    "trajectory.set_namespace_token('')\n"
    "trajectory.authorize_campaign(dsn, cid, authorized=100000)\n"
    "trajectory.ensure_campaign(dsn, cid, 0, 'I', %s, %s, tasks=[%r])\n"
    "trajectory.accept_action(dsn, cid, 0, decision, program_digest=%r)\n"
    "os._exit(0)\n" % (repr(CHARTER), repr(CAPS), DEV_TASK, C6_PROGRAM_DIGEST))

_RESUME_PHASE = (
    "import json, sys\n"
    "from experiments.ad01 import mission, trajectory\n"
    "dsn, cid = sys.argv[1:3]\n"
    "trajectory.set_namespace_token('')\n"
    "out = trajectory.resume_campaign(dsn, cid, %s, %s, tasks=[%r])\n"
    "print(json.dumps(out['resumed_in_flight'], default=str), flush=True)\n"
    % (repr(CHARTER), repr(CAPS), DEV_TASK))


def _run_phase(source: str, *args: str) -> str:
    done = subprocess.run([sys.executable, "-c", source, *args],
                          cwd=str(ROOT), env=_env(), capture_output=True,
                          text=True, timeout=300)
    assert done.returncode == 0, (
        "the restart phase failed: %s" % (done.stderr or done.stdout))
    return done.stdout


def test_pending_retains_program_identity_across_restart(store):
    """The operation keeps the program and inputs it was admitted under.

    Phase A admits it and dies. Phase B is a different interpreter that
    resumes it and reports the identity it resumed under. Both are compared
    against literals written above, so the test fails if either the program
    digest or the input identity is recomputed, defaulted or substituted on
    the way through the restart.
    """
    cid = _cid(SEQ)
    _run_phase(_ACCEPT_PHASE, store, cid,
               json.dumps(C6_DECISION, sort_keys=True, separators=(",", ":")))

    reported = json.loads(_run_phase(_RESUME_PHASE, store, cid))
    assert len(reported) == 1, (
        "the restart restored %d operations, not the one it was holding"
        % len(reported))
    reported = reported[0]

    assert reported["program_digest"] == C6_PROGRAM_DIGEST, (
        "the restart resumed under a different program: %r"
        % reported.get("program_digest"))
    assert reported["input_identity"] == C6_INPUT_IDENTITY, (
        "the restart recomputed the operation's inputs: %r"
        % reported.get("input_identity"))
    assert reported["decision_digest"] == C6_DECISION_DIGEST, (
        "the restart resumed a different decision: %r"
        % reported.get("decision_digest"))
    assert reported["status"] == "restored", (
        "the operation was never restored: %r" % reported.get("status"))

    from experiments.ad01 import mission, trajectory

    # Phase B ran the boundary, so the operation is no longer in flight and the
    # entry released it. That is the intended release, not a lost record: the
    # identity it carried moved into the effect record, and a resume that found
    # a settled operation still in flight would restore work that already ran.
    assert mission.read_in_flight(store, cid) == [], (
        "the entry still holds an operation whose effect already ran")

    with trajectory._read_conn(store) as conn:
        row = conn.execute(
            "SELECT effect_record FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = 0", (cid,)).fetchone()
        conn.commit()
    ran_under = dict(dict(row["effect_record"])["ran_under"])
    assert ran_under["program_digest"] == C6_PROGRAM_DIGEST, (
        "the settled boundary does not say which program produced it")
    assert ran_under["input_identity"] == C6_INPUT_IDENTITY
    assert ran_under["decision_digest"] == C6_DECISION_DIGEST


def test_resume_restores_pending_not_yet_effects(store):
    """Resume restores the work. It does not run it.

    An operation that was pending before the restart is still pending after
    it. If resume executed anything, the boundary would have settled and the
    durable row would say so; asserting the absence of an effect is what
    separates restoring from resuming-by-re-running.
    """
    from experiments.ad01 import mission, trajectory

    cid, held = _held(store, SEQ + 1)
    assert held.status == "held", (
        "admission left the operation in state %r" % held.status)

    restored = mission.resume_operation(store, cid)
    assert len(restored) == 1
    assert restored[0].status == "restored"
    assert restored[0].input_identity == C6_INPUT_IDENTITY

    with trajectory._read_conn(store) as conn:
        row = conn.execute(
            "SELECT status, effect_record FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = 0", (cid,)).fetchone()
        boundaries = conn.execute(
            "SELECT count(*) AS n FROM attempt_observations o"
            " JOIN attempts a ON a.id = o.attempt_id"
            " WHERE a.investigation_id = %s"
            " AND o.content->>'kind' = 'boundary'", (cid,)).fetchone()
        conn.commit()

    assert row["status"] == "accepted", (
        "resume changed the operation's status to %r" % row["status"])
    assert row["effect_record"] is None, (
        "resume wrote an effect record for an operation it did not run")
    assert int(boundaries["n"]) == 0, (
        "resume executed the pending boundary instead of restoring it")

    # Restoring twice is one restoration, not two.
    again = mission.resume_operation(store, cid)
    assert len(again) == 1
    assert again[0].restored_at == restored[0].restored_at


def test_the_continuation_document_is_no_longer_a_resume_owner(store, tmp_path):
    """One owner, checked structurally so a second cannot appear silently.

    Three assertions, each about the shape rather than about today's data.
    The column that carries an in-flight operation exists on one table. The
    package reports it with no continuation document present at all. And a
    continuation document that says something different cannot move it.
    """
    from settlement import context
    from settlement.common import Command

    cid, _held_entry = _held(store, SEQ + 2)

    with context.db.connect(store) as conn:
        with conn.cursor(row_factory=context.dict_row) as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND column_name = 'in_flight'")
            carriers = [r["table_name"] for r in cur.fetchall()]
            conn.commit()
    assert carriers == ["investigations"], (
        "an in-flight operation is carried by %s as well as the mission entry"
        % carriers)

    # No continuation document exists for this investigation at all.
    with context.db.connect(store) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM continuation_docs"
                        " WHERE investigation_id = %s", (cid,))
            assert int(cur.fetchone()[0]) == 0
            conn.commit()

    package = context.resume_package(store, cid)
    assert [entry["input_identity"] for entry in package["in_flight"]] \
        == [C6_INPUT_IDENTITY], (
            "the resume package reported %r without any continuation document"
            % package["in_flight"])

    # A continuation document is written saying something else. It is plan
    # position, not in-flight identity, so the package must not move.
    roots = tmp_path / "artifacts"
    context.save_continuation(
        store, Command(request_id="c6-cont-%s" % cid,
                       payload={"c6": True}),
        roots, cid, "att-%s-0" % cid, "comp-v1",
        {"node": 2}, [], ["op-c6-conflicting"], {"c6": True},
        {"next": "something else entirely"})
    package = context.resume_package(store, cid)
    assert [entry["input_identity"] for entry in package["in_flight"]] \
        == [C6_INPUT_IDENTITY], (
            "a continuation document overtook the mission entry: %r"
            % package["in_flight"])
    assert "op-c6-conflicting" in package["continuation"]["unresolved_ops"], (
        "the continuation document stopped carrying its own position, which is"
        " what it is for")


def test_suspend_for_barrier_routes_at_the_mission_entry(store):
    """The barrier names the operation it suspended, on the mission entry.

    `suspend_for_barrier` used to mark the attempt and leave nothing that
    said which operation was in flight, so the resume side had nothing to
    route at. It now records the barrier against the mission entry's own
    in-flight operation, and refuses when there is no such operation rather
    than inventing one.
    """
    from settlement import run
    from settlement.common import SettlementError
    from experiments.ad01 import mission, trajectory

    cid, held = _held(store, SEQ + 3)
    outcome = run.suspend_for_barrier(store, "att-%s-0" % cid, BARRIER_REF)
    assert outcome.code.name == "APPLIED", (
        "the barrier did not suspend: %s" % outcome.detail)

    entry = mission.read_in_flight(store, cid)[0]
    assert entry.barrier_ref == BARRIER_REF, (
        "the barrier was not recorded against the mission entry: %r"
        % entry.barrier_ref)
    assert entry.status == "suspended"
    assert entry.input_identity == C6_INPUT_IDENTITY, (
        "the barrier rewrote the suspended operation's identity")

    with trajectory._read_conn(store) as conn:
        lifecycle = conn.execute(
            "SELECT lifecycle FROM attempts WHERE id = %s",
            ("att-%s-0" % cid,)).fetchone()
        conn.commit()
    assert lifecycle["lifecycle"] == "suspended", (
        "the attempt itself was not suspended: %r" % lifecycle["lifecycle"])

    # An investigation with no held operation has nothing to suspend. That is
    # a refusal, not a barrier written over a default.
    from settlement.common import Command
    from settlement import store as settlement_store

    settlement_store.admit_commitment(
        store, Command(request_id="c6-empty",
                       payload={"investigation_id": "c6-empty-inv",
                                "objective": "nothing held"}))
    attempt_id = settlement_store.acquire_work(
        store, Command(request_id="c6-empty-attempt",
                       payload={"attempt_id": "c6-empty-att",
                                "investigation_id": "c6-empty-inv"})
    ).data["attempt_id"]
    with pytest.raises(SettlementError) as refusal:
        run.suspend_for_barrier(store, attempt_id, BARRIER_REF)
    assert str(refusal.value) == (
        "attempt c6-empty-att holds no admitted operation on its mission entry:"
        " a barrier suspends admitted work, so record it first")


def test_resume_refuses_a_campaign_it_did_not_mint(store, monkeypatch):
    """The id guard still fires, and it fires before anything else is reported.

    The inherited guard in `test_p2c_ad01_resweep` cannot reach this any more,
    because it names a database that does not exist and a resume that restores
    from the mission entry must be able to read a store. The guard is not
    weakened and not duplicated in spirit; it is pinned here against a store
    that exists, so a resume which minted the wrong campaign id still refuses
    rather than returning the other campaign's result.
    """
    from experiments.ad01 import trajectory

    cid, _held_entry = _held(store, SEQ + 4)
    monkeypatch.setattr(trajectory, "run_campaign",
                        lambda *a, **k: {"campaign_id": cid + "-wrong"})
    with pytest.raises(ValueError, match="unexpected campaign"):
        trajectory.resume_campaign(store, cid, CHARTER, CAPS,
                                   tasks=[DEV_TASK])
    # The restore did run, and the held operation is still held: a refusal over
    # a minted id is not a licence to discard the work the entry records.
    from experiments.ad01 import mission

    entry = mission.read_in_flight(store, cid)[0]
    assert entry.status == "restored"
    assert entry.program_digest == C6_PROGRAM_DIGEST