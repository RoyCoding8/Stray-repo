"""A held operation runs the decision it was admitted under, or it refuses.

`mission.admit_operation` records `program_digest`, `input_identity` and
`decision_digest` when a decision is admitted and before its effect runs.
Until this file the record was written and read back by nobody:
`execute_pending` copied the three into `ran_under` and consulted none of
them, and no production tree compared any of them. A restart read the
recorded identity and still executed under whatever the restarting process
held, so a substituted operation was visible afterwards only as a report
field.

Two of the three are comparable by recomputation, because the bytes they are
derived from are durable and in hand at the moment the run is about to
happen. `mission._wire` derives `decision_digest` and `input_identity` from
`(decision, task_id, capability_id)`; at `execute_pending` all three are
available -- the decision from `s09_policy_state.accepted_action`, the task
and capability from the record. Those are a comparison in one digest space,
recomputed by the rule that wrote them, so a disagreement means the inputs
moved rather than that a convention changed.

`program_digest` is not compared, and this file states why rather than
implying coverage it does not have. Nothing in the repository maps a program
digest to the bytes that will execute: `execute_pending` is handed a
capability id, and `mission.seed_program_digest` is a digest over a declared
identity rather than over source. There is no second digest to compare it
against, so any check here would be a check of shape. `frontier.package_digest`
and `seed_program_digest` are both 64 lowercase hex and
`admit_operation` accepts any non-empty string, so the digest space already
admits substitution between two unrelated kinds of program. A comparison that
cannot fail for that reason is not a comparison.

The substitution here is behavioural, not a string swap. `ad01-w0-dev-sw-01`
reduces to the same op count under `seed-sw-greedy` and `seed-sw-ddmin` and
reaches it by different sequences, so a substituted decision produces a
different candidate -- which is what makes "it ran the other thing" a fact
about the effect rather than a claim about a field.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a36enforce"

CHARTER = {"objective": "hold a pending operation across a restart",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 1, "diagnostic_queries": 16, "model_calls": 20}
DEV_TASK = "ad01-w0-dev-sw-01"

# The two trees that compare a `program_digest` at all. Both compare a
# pending effect against the store's own currently active package, so each
# answers "is this effect still under the live program" and neither answers
# "was this effect admitted under the program its record names". An effect
# substituted after admission is invisible to both, which is the finding.
FRONTIER_READERS = {"experiments/ad01/frontier.py",
                    "experiments/ad01/improve_channel.py"}


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


def _decision(task_id: str = DEV_TASK, **overrides) -> dict:
    action = {"kind": "development", "task_id": task_id, "max_queries": 16}
    action.update(overrides)
    return {"basis_references": [],
            "question": "a36 held boundary",
            "next_action": action}


def _admit(store: str, seq: int, decision: dict, *,
           capability_id: str, program_digest: str = "") -> str:
    from experiments.ad01 import mission, trajectory

    cid = _cid(seq)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    made = trajectory.ensure_campaign(store, cid, 0, "I", CHARTER, CAPS,
                                      tasks=[DEV_TASK])
    assert made["admitted"] is True, "the campaign admitted nothing"
    trajectory.accept_action(store, cid, 0, decision,
                             capability_id=capability_id,
                             program_digest=program_digest)
    held = mission.held_operation(store, cid, "att-%s-0" % cid)
    assert held is not None, "the admitted operation is not on the entry"
    return cid


def _resume(store: str, cid: str, *, capability_id: str) -> dict:
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
    return dict(row["effect_record"] or {})


def _candidate(capability_id: str) -> list:
    from experiments.ad01 import trajectory

    episode = trajectory.dev_episode(DEV_TASK, capability_id, max_queries=15)
    assert episode["disposition"] == "retained", (
        "%s did not reduce %s: %r"
        % (capability_id, DEV_TASK,
           episode.get("fallback_reason") or episode.get("reason")))
    assert episode["lineage"][0]["capability_id"] == capability_id
    return episode["candidate"]["ops"]


def test_the_two_programs_actually_differ():
    """The premise, measured rather than assumed.

    Without this the substitution below could be undetectable: two programs
    that agreed on the candidate would let a swapped decision pass unnoticed.
    """
    assert _candidate("seed-sw-greedy") != _candidate("seed-sw-ddmin"), (
        "both programs produced the same candidate on %s, so this file "
        "cannot tell a substituted decision from an admitted one" % DEV_TASK)


def test_a_substituted_decision_is_refused(store):
    """The counterexample: admit one decision, run another.

    The durable decision in `s09_policy_state.accepted_action` is rewritten to
    a different one, leaving the mission entry's `decision_digest` naming the
    original. That is the state a boundary reaches when its decision is
    restated between admission and execution. The run must refuse rather than
    execute the restated decision and file the result under the original's
    identity.
    """
    from experiments.ad01 import mission, trajectory

    admitted_decision = _decision(max_queries=16)
    cid = _admit(store, 701, admitted_decision,
                 capability_id="seed-sw-greedy")

    held = mission.held_operation(store, cid, "att-%s-0" % cid)
    substituted = _decision(max_queries=8)
    assert mission._wire(substituted, DEV_TASK, "seed-sw-greedy")[
        "decision_digest"] != held.decision_digest, (
        "the substituted decision is the admitted one; nothing was substituted")

    _rewrite_accepted_action(store, cid, substituted)

    with pytest.raises(mission.MissionRefused) as caught:
        _resume(store, cid, capability_id="seed-sw-greedy")
    assert "decision_digest" in str(caught.value), (
        "the refusal does not name the field that disagreed: %s"
        % caught.value)

    assert _effect_record(store, cid) == {}, (
        "a refused substitution still recorded an effect")


def _rewrite_accepted_action(store: str, cid: str, decision: dict) -> None:
    from psycopg.types.json import Json

    from experiments.ad01 import trajectory

    with trajectory._read_conn(store) as conn:
        conn.execute(
            "UPDATE s09_policy_state SET accepted_action = %s"
            " WHERE investigation_id = %s AND seq = 0",
            (Json(decision), cid))
        conn.commit()


def test_a_substituted_task_is_refused(store):
    """The same substitution on the other recomputable field.

    The recorded `task_id` and `capability_id` are read back and used, so the
    decision digest is the field that names them. A capability the record does
    not name produces a different `input_identity`, and both are in the same
    space and both are compared.
    """
    from experiments.ad01 import mission

    cid = _admit(store, 702, _decision(),
                 capability_id="seed-sw-greedy")
    held = mission.held_operation(store, cid, "att-%s-0" % cid)
    assert held.capability_id == "seed-sw-greedy"

    supplied = dict(
        held.as_json(), input_identity=held.input_identity,
        capability_id="seed-sw-ddmin")
    wrong = mission.InFlightOperation.from_json(held.investigation_id, supplied)
    with pytest.raises(mission.MissionRefused) as caught:
        mission.require_admitted_identity(wrong, decision=_decision(),
                                          task_id=DEV_TASK,
                                          capability_id=wrong.capability_id)
    assert "input_identity" in str(caught.value), (
        "a capability the record does not name was accepted: %s"
        % caught.value)


def test_an_undisturbed_operation_still_runs(store):
    """The check is not a blanket refusal.

    An admitted operation presented with its own inputs must run. If this
    fails the guard refused everything and the refusal proves nothing.
    """
    cid = _admit(store, 703, _decision(), capability_id="seed-sw-greedy")
    out = _resume(store, cid, capability_id="seed-sw-ddmin")

    assert len(out["boundaries"]) == 1, (
        "an undisturbed operation did not run (%d boundaries)"
        % len(out["boundaries"]))
    ran = out["episodes"][0]["lineage"][0]["capability_id"]
    assert ran == "seed-sw-greedy", (
        "the undisturbed boundary ran %r" % ran)
    assert out["episodes"][0]["candidate"]["ops"] == _candidate(
        "seed-sw-greedy")
    assert _effect_record(store, cid)["ran_under"]["capability_id"] == (
        "seed-sw-greedy")


def test_the_restart_is_not_the_earliest_point(store):
    """Why the check is at `execute_pending` and not at resume.

    `resume_operation` runs nothing, so a refusal there would discard work
    the same store is about to finish. This measures that: a restart whose
    durable decision still agrees with the record restores cleanly and leaves
    the operation running rather than refusing it.
    """
    from experiments.ad01 import mission

    cid = _admit(store, 704, _decision(), capability_id="seed-sw-greedy")
    restored = mission.resume_operation(store, cid)
    assert len(restored) == 1, "the restore refused an intact operation"
    assert restored[0].status == "restored"
    assert restored[0].decision_digest == (
        mission.held_operation(store, cid, "att-%s-0" % cid).decision_digest)

    out = _resume(store, cid, capability_id="seed-sw-greedy")
    assert len(out["boundaries"]) == 1, (
        "a restart refused work it could finish; the boundary should have "
        "been the refusal point, not the restore")


def test_the_program_digest_has_no_second_value_to_check():
    """What is deliberately not compared, and why that is not a defect here.

    Two facts, both measured. Nothing maps a digest to executing bytes: the
    run boundary is handed a capability id and `seed_program_digest` digests a
    declared identity rather than source. And the digest space already admits
    substitution: `frontier.package_digest` and `seed_program_digest` are both
    64 lowercase hex, and `admit_operation` accepts any non-empty string, so
    either is silently accepted where the other belongs.
    """
    from experiments.ad01 import frontier, mission, trajectory

    package = frontier.package_digest("print(1)\n", "print(2)\n",
                                      parent_digest="0" * 64, version=1)
    seed = mission.seed_program_digest()
    for value in (package, seed):
        assert len(value) == 64 and all(
            c in "0123456789abcdef" for c in value)

    assert trajectory._admitting_program_digest(package) == package, (
        "a frontier package digest is refused where a program digest is "
        "required: the two spaces are distinguished after all, and this "
        "test's premise is wrong")

    import inspect
    signature = inspect.signature(mission.require_admitted_identity)
    assert "program_digest" not in str(signature), (
        "the guard claims to check a digest it has no second value for")


def test_no_production_tree_compares_a_recorded_program_digest():
    """The reader census, by AST, as an executable claim.

    A recorded identity compared anywhere beyond the two readers measured is
    a reader this lane has not accounted for. Read through the AST rather than
    by needle so a comparison spelled with any operator, through any alias, or
    inside a comprehension is found.
    """
    targets = {"program_digest", "input_identity", "decision_digest"}
    outside = []
    for top in ("src", "experiments", "scripts"):
        for path in (ROOT / top).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                names = set()
                for operand in [node.left] + list(node.comparators):
                    for sub in ast.walk(operand):
                        if isinstance(sub, ast.Attribute):
                            names.add(sub.attr)
                        elif isinstance(sub, ast.Subscript) and isinstance(
                                sub.slice, ast.Constant):
                            names.add(sub.slice.value)
                if names & targets:
                    rel = path.relative_to(ROOT).as_posix()
                    if rel not in FRONTIER_READERS:
                        outside.append((rel, node.lineno,
                                        sorted(names & targets)))
    assert outside == [], (
        "a recorded identity is compared outside the two readers measured "
        "here, so the census is out of date: %r" % outside)