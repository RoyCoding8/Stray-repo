"""A pending operation runs the program it was admitted under, not the one
the restarting process supplies.

Milestone A asks for one thing of pending work: it must retain its old
program/input identity through restart. The mechanism that could do this is
`mission.admit_operation`, which records `program_digest`, `input_identity`
and the capability at the moment of admission -- before any effect runs,
because a restart happens exactly when the effect has not run.

`execute_pending` reads that record, and it used to copy it into `ran_under`
on the effect row without consulting it before running. The task and
capability it handed to `_run_boundary` were the ones the *campaign schedule*
supplies at the running boundary, and the schedule is a caller argument: a
restart re-invokes `resume_campaign`, and nothing forced it to repeat the
capability the first process used. So a boundary could execute one program
while the row filed its result under another's digest, and the disagreement was
invisible unless you compared the record against the effect. It now runs the
admitted task and capability; these tests are what pins that.

The spine is the behavioural one. `ad01-w0-dev-sw-01` reduces to the same
number of ops under `seed-sw-greedy` and `seed-sw-ddmin` and reaches it by
different sequences, so a substituted program is not a field disagreement to
be argued about -- it is a different candidate produced and then filed under
the other program's digest. The episode's own `lineage` names the program
that actually ran, which is what makes this measurable rather than
rhetorical.

Every program here is a seed capability named by id. No other lane's fixture
is reused, so a self-consistent fixture cannot pass for an identity check.
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

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a5ident"

CHARTER = {"objective": "hold a pending operation across a restart",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20}

# Two different seed programs, both of which run a development boundary on
# this task and produce a *different* candidate. That is measured, not
# assumed, and it is specific to this task: on `ad01-w0-dev-sw-00` the two
# agree exactly, so a substitution there would be undetectable by candidate
# comparison. `test_the_two_programs_actually_differ` is what keeps the
# premise honest if either task or program is changed.
ADMITTED_PROGRAM = "seed-sw-greedy"
SUBSTITUTED_PROGRAM = "seed-sw-ddmin"
DEV_TASK = "ad01-w0-dev-sw-01"


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


def _development_decision() -> dict:
    return {"basis_references": [],
            "question": "a5 held boundary under one program",
            "next_action": {"kind": "development", "task_id": DEV_TASK,
                            "max_queries": 16}}


def _admit(store: str, seq: int, *, capability_id: str) -> str:
    """Admit a development boundary under one program and stop.

    `accept_action` is the admission seam. The decision is durable and the
    operation is held; the effect has not run. Everything after this point is
    what a restart does with it.
    """
    from experiments.ad01 import mission, trajectory

    cid = _cid(seq)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    made = trajectory.ensure_campaign(store, cid, 0, "I", CHARTER, CAPS,
                                      tasks=[DEV_TASK])
    assert made["admitted"] is True, "the campaign admitted nothing"
    trajectory.accept_action(store, cid, 0, _development_decision(),
                             capability_id=capability_id)
    held = mission.held_operation(store, cid, "att-%s-0" % cid)
    assert held is not None, "the admitted operation is not on the entry"
    assert held.capability_id == capability_id, (
        "the admission recorded %r, not the program named"
        % held.capability_id)
    return cid


def _resume(store: str, cid: str, *, capability_id: str) -> dict:
    """Restart through the public resume entry under a different program."""
    from experiments.ad01 import trajectory

    return trajectory.resume_campaign(store, cid, CHARTER, CAPS,
                                      tasks=[DEV_TASK],
                                      capability_id=capability_id)


def _effect_record(store: str, cid: str) -> dict:
    from experiments.ad01 import trajectory

    with trajectory._read_conn(store) as conn:
        row = conn.execute(
            "SELECT effect_record FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = 0", (cid,)).fetchone()
        conn.commit()
    assert row is not None, "the boundary left no policy row"
    assert row["effect_record"] is not None, (
        "the boundary left no effect record, so nothing ran")
    return dict(row["effect_record"])


def _ran_under(store: str, cid: str) -> dict:
    return dict(_effect_record(store, cid)["ran_under"])


def _candidate(capability_id: str) -> list:
    """The program this lane means by an id, executed the way a boundary would.

    A boundary runs under `sequence_construction_allowance`, which reserves one
    query of the cap, so the budget here is 15 rather than the 16 the episode
    helper defaults to. Measuring at the wrong budget compares two programs
    that happen to tie, which is how a substitution hides.
    """
    from experiments.ad01 import trajectory

    episode = trajectory.dev_episode(DEV_TASK, capability_id, max_queries=15)
    assert episode["disposition"] == "retained", (
        "%s did not reduce %s: %r"
        % (capability_id, DEV_TASK,
           episode.get("fallback_reason") or episode.get("reason")))
    assert episode["lineage"][0]["capability_id"] == capability_id
    return episode["candidate"]["ops"]


def test_the_two_programs_actually_differ():
    """The premise of the counterexample, measured rather than assumed.

    On this task the two programs reduce to the same number of ops and reach it
    differently, so the candidate content is what tells them apart. If they
    agreed on that too, a substitution would be undetectable here and the tests
    below would pass for the wrong reason. They agree exactly on
    `ad01-w0-dev-sw-00`, which is why the task is named rather than assumed.
    """
    assert _candidate(ADMITTED_PROGRAM) != _candidate(SUBSTITUTED_PROGRAM), (
        "both programs produced the same candidate on %s, so this file cannot "
        "tell them apart" % DEV_TASK)


def test_a_restart_runs_the_admitted_program_not_the_supplied_one(store):
    """The counterexample: the admitted program is the one that runs.

    Admitted under `ADMITTED_PROGRAM`. Restarted with the schedule supplying
    `SUBSTITUTED_PROGRAM`. The effect must be the admitted program's effect,
    because that is the program the record names as having run.
    """
    cid = _admit(store, 61, capability_id=ADMITTED_PROGRAM)
    out = _resume(store, cid, capability_id=SUBSTITUTED_PROGRAM)

    assert len(out["boundaries"]) == 1, (
        "the restart settled %d boundaries, expected the one it was holding"
        % len(out["boundaries"]))
    episode = out["episodes"][0]
    ran = episode["lineage"][0]["capability_id"]
    assert ran == ADMITTED_PROGRAM, (
        "the restart ran %r while the record names %r; the effect and the "
        "provenance disagree" % (ran, ADMITTED_PROGRAM))

    assert episode["candidate"]["ops"] == _candidate(ADMITTED_PROGRAM), (
        "the boundary's candidate came from %r, not %r"
        % (SUBSTITUTED_PROGRAM, ADMITTED_PROGRAM))


def test_the_record_names_the_program_that_actually_ran(store):
    """`ran_under` is a claim about the effect, so check it against the effect.

    The record is written from the admission, which is why it is worth
    nothing on its own: it would read the same whether or not the boundary
    honoured it. This asserts the two sides agree.
    """
    cid = _admit(store, 62, capability_id=ADMITTED_PROGRAM)
    out = _resume(store, cid, capability_id=SUBSTITUTED_PROGRAM)
    episode = out["episodes"][0]

    ran_under = _ran_under(store, cid)
    assert ran_under["capability_id"] == episode["lineage"][0]["capability_id"], (
        "the effect record names %r; the boundary ran %r"
        % (ran_under["capability_id"], episode["lineage"][0]["capability_id"]))
    assert ran_under["program_digest"], "the record names no program at all"


def test_an_unadmitted_pending_boundary_still_drains(store):
    """The substitution has no source when nothing was admitted.

    A pending decision recorded without an admission carries no identity on
    the entry, so there is nothing to retain. It drains under the supplied
    program exactly as before -- the repair adds no refusal where there is
    nothing to compare.

    The path is reachable, and the distinction matters: the investigation row
    is created by `ensure_campaign`, which the resume path itself calls, so a
    campaign can hold a pending decision with an empty `in_flight`. What a
    resume cannot survive is an investigation that was never admitted at all,
    which is a different state with no pending work in it.
    """
    from experiments.ad01 import mission, trajectory

    cid = _cid(63)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    trajectory.ensure_campaign(store, cid, 0, "I", CHARTER, CAPS,
                               tasks=[DEV_TASK])
    decision = _development_decision()
    trajectory.record_decision(store, cid, 0, decision)

    with trajectory._read_conn(store) as conn:
        entry = conn.execute(
            "SELECT in_flight FROM investigations WHERE id = %s",
            (cid,)).fetchone()
        conn.commit()
    assert entry is not None, "the campaign admitted no investigation to hold it"
    assert list(entry["in_flight"] or []) == [], (
        "a decision recorded without an admission is holding an operation")
    assert mission.held_operation(store, cid, "att-%s-0" % cid) is None

    out = trajectory.resume_campaign(store, cid, CHARTER, CAPS,
                                     tasks=[DEV_TASK],
                                     capability_id=SUBSTITUTED_PROGRAM)
    assert len(out["boundaries"]) == 1, "the legacy pending row did not drain"
    assert out["episodes"][0]["disposition"] == "retained"
    # No admission means no `ran_under`, so nothing claims a program ran under
    # an identity that was never recorded.
    assert "ran_under" not in _effect_record(store, cid), (
        "a boundary with no admission recorded one anyway")


def test_the_identity_survives_a_separate_process(store):
    """The counterexample across a real restart, not a second call.

    Admission and resume are separated by process and by `os._exit`, so
    nothing but the database crosses between them. The program the second
    process supplies is the only thing it holds, and it is not the program
    that ran.
    """
    cid = _admit(store, 64, capability_id=ADMITTED_PROGRAM)

    done = subprocess.run(
        [sys.executable, "-c", _RESUME_PHASE, store, cid,
         SUBSTITUTED_PROGRAM],
        cwd=str(ROOT), env=_env(), capture_output=True, text=True,
        timeout=300)
    assert done.returncode == 0, (
        "the restart process failed: %s" % (done.stderr or done.stdout))
    out = json.loads(done.stdout.strip().splitlines()[-1])

    assert out["ran"] == ADMITTED_PROGRAM, (
        "the fresh process ran %r while the record names %r"
        % (out["ran"], ADMITTED_PROGRAM))
    assert out["ops"] == _candidate(ADMITTED_PROGRAM), (
        "the fresh process's candidate came from %r, not %r"
        % (SUBSTITUTED_PROGRAM, ADMITTED_PROGRAM))


_RESUME_PHASE = (
    "import json, sys\n"
    "from experiments.ad01 import trajectory\n"
    "dsn, cid, supplied = sys.argv[1:4]\n"
    "trajectory.set_namespace_token('')\n"
    "out = trajectory.resume_campaign(dsn, cid, %s, %s, tasks=[%r],\n"
    "                                capability_id=supplied)\n"
    "episode = out['episodes'][0]\n"
    "print(json.dumps({'ran': episode['lineage'][0]['capability_id'],\n"
    "                  'ops': episode['candidate']['ops']}), flush=True)\n"
    % (repr(CHARTER), repr(CAPS), DEV_TASK))


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s" % (ROOT, ROOT / "src")
    return env