"""A7 and A8: a zero model-call ceiling, and a recorder the store cannot see.

Two defects the E3 ladder lane found while measuring its own run, and did
not fix.

A7 is a ceiling that refuses everything. `_study_operation_counts`
increments `model_calls` only for an operation whose stored effect is
`model-inference`, so a study declaring `max_model_calls: 0` is at the
ceiling before its first operation of any kind, and every operation it
tries is refused. In the E3 run that turned 42 admissions into 42
refusals, and on a summary line a refused study is indistinguishable
from one that made no model calls at all. A zero model-call ceiling is
supposed to mean zero MODEL calls, and the count it should be compared
against is the count of model calls the study has already made, not the
count of operations it is about to make.

A8 is instrumentation that under-reports its own system. `DecisionRecorder`
seeds a parentless per-cell allocation and admits under it, so the
operations it really created sit outside the study's allocation subtree.
The store's own contamination scanner resolves a study by walking
allocation parentage, so it cannot see them: the E3 lane's first
verification used exactly that query and reported `per_path:
{admit_study_call: 0}` on a run where every one of its 42 decisions went
through `admit_study_call`.

Every assertion names the break that fails it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest


def _model_payload() -> dict:
    return {"model": "test-model",
            "messages": [{"role": "user", "content": "hello"}],
            "max_output_tokens": 16}


def _admit(dsn: str, study_root: str, operation_id: str, effect: str) -> dict:
    from settlement import authority, broker, loop

    granted = authority.admit_study_call(
        dsn, study_root, kind="development", operation_id=operation_id,
        effect=effect,
        payload={"command": "note", "payload": {"decision": {"target": "x"}},
                 "idempotency_key": operation_id}
        if effect == broker.DOMAIN_COMMAND else _model_payload())
    if not isinstance(granted, loop.Grant):
        return {"operation_id": operation_id, "admitted": False,
                "refusal": getattr(granted, "reason", "unknown"),
                "detail": getattr(granted, "detail", "")}
    return {"operation_id": operation_id, "admitted": True}


def _studied(dsn: str, study_root: str, allocation_id: str, ceilings: dict):
    import contextlib

    from settlement import authority

    @contextlib.contextmanager
    def bind():
        handle = authority.authorize_study(
            dsn, study_root, authorized=1_000, allocation_id=allocation_id,
            ceilings=ceilings)
        try:
            yield handle.study_root
        finally:
            _wipe(dsn, study_root, allocation_id)

    return bind()


def _wipe(dsn: str, study_root: str, allocation_id: str) -> None:
    import contextlib

    from settlement import db

    with contextlib.suppress(Exception):
        with db.connect(dsn) as conn:
            conn.execute("DELETE FROM receipts WHERE operation_id LIKE %s"
                         " OR operation_id LIKE %s",
                         (allocation_id + "/%", study_root + "-%"))
            conn.execute("DELETE FROM operations WHERE id LIKE %s"
                         " OR allocation_id LIKE %s OR allocation_id LIKE %s",
                         (study_root + "-%", allocation_id + "/%",
                          allocation_id))
            conn.execute("DELETE FROM reservations WHERE allocation_id LIKE %s"
                         " OR allocation_id = %s",
                         (allocation_id + "/%", allocation_id))
            conn.execute("DELETE FROM allocations WHERE id = %s OR id LIKE %s",
                         (allocation_id, allocation_id + "/%"))
            conn.execute("DELETE FROM study_authority WHERE study_root = %s",
                         (study_root,))
            conn.commit()


def _counted_by_study_scanner(dsn: str, study_root: str) -> set:
    """The query `s09_run_isolation._persisted_operations` runs.

    That is the store's own contamination/adoption read: it resolves a
    study by walking allocation parentage up to `study_authority`. An
    operation the study really created has to appear here.
    """
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT o.id FROM operations o"
                " JOIN study_authority a"
                " ON a.allocation_id = ("
                "   WITH RECURSIVE up (id, parent_id) AS ("
                "     SELECT id, parent_id FROM allocations WHERE id = o.allocation_id"
                "     UNION ALL"
                "     SELECT l.id, l.parent_id FROM allocations l"
                "     JOIN up ON l.id = up.parent_id)"
                "   SELECT id FROM up WHERE id = a.allocation_id)"
                " WHERE a.study_root = %s", (study_root,))
            found = {r["id"] for r in cur.fetchall()}
        conn.commit()
    return found


# --- A7: a zero model-call ceiling bounds model calls ---------------------


def test_a_zero_model_call_ceiling_still_admits_a_domain_command(migrated_db):
    """A7. A cap sheet reading "no model calls" is not a cap sheet
    refusing all work.

    Break by comparing `used + 1 > limit` for every ceiling, instead of
    only for the ceilings whose counter this operation would spend.
    """
    from settlement import broker

    with _studied(migrated_db, "a7zero", "a7zero-alloc",
                  {"max_operations": 64, "max_model_calls": 0,
                   "max_development": 64}) as study_root:
        domain = _admit(migrated_db, study_root, "a7zero-op-domain",
                        broker.DOMAIN_COMMAND)
        model = _admit(migrated_db, study_root, "a7zero-op-model",
                       broker.MODEL_INFERENCE)

    assert domain["admitted"] is True, (
        "max_model_calls=0 refused a domain-command: %r" % domain)
    assert model["admitted"] is False, (
        "max_model_calls=0 admitted a model-inference: %r" % model)
    assert "max_model_calls=0" in model["detail"], (
        "the model call was refused by something other than the zero "
        "ceiling: %r" % model["detail"])


def test_a_positive_model_call_ceiling_bounds_only_model_calls(migrated_db):
    """The guard against over-correcting A7 into "ceilings do not apply".

    Break by skipping the ceiling loop for any effect that is not
    `model-inference`, or by comparing the count of model calls already
    made against the count of operations already made.
    """
    from settlement import broker

    with _studied(migrated_db, "a7one", "a7one-alloc",
                  {"max_operations": 64, "max_model_calls": 1,
                   "max_development": 64}) as study_root:
        first = _admit(migrated_db, study_root, "a7one-op-model-0",
                       broker.MODEL_INFERENCE)
        domain = _admit(migrated_db, study_root, "a7one-op-domain",
                        broker.DOMAIN_COMMAND)
        second = _admit(migrated_db, study_root, "a7one-op-model-1",
                        broker.MODEL_INFERENCE)

    assert first["admitted"] is True, (
        "the ceiling is 1 and no model call had been made: %r" % first)
    assert domain["admitted"] is True, (
        "a model-call ceiling refused a domain command: %r" % domain)
    assert second["admitted"] is False, (
        "the ceiling of 1 admitted a second model call: %r" % second)
    assert "max_model_calls=1" in second["detail"]


def test_a_non_zero_ceiling_still_bounds_every_kind_it_names(migrated_db):
    """A7 does not exempt the other counters.

    `max_development` counts operations admitted under `kind:
    development`, and it must keep refusing at its own limit while a
    model-call ceiling of zero lets domain commands through. Break by
    exempting every ceiling except the one under test.
    """
    from settlement import broker

    with _studied(migrated_db, "a7dev", "a7dev-alloc",
                  {"max_operations": 64, "max_model_calls": 0,
                   "max_development": 2}) as study_root:
        admitted = [_admit(migrated_db, study_root, "a7dev-op-%d" % i,
                           broker.DOMAIN_COMMAND) for i in range(3)]

    assert [a["admitted"] for a in admitted] == [True, True, False], (
        "max_development=2 admitted %r" % [a["admitted"] for a in admitted])
    assert "max_development=2" in admitted[2]["detail"]


# --- A8: the recorder is visible to the study that owns it ---------------


def test_recorder_operations_are_visible_to_the_study_scanner(migrated_db):
    """A8. The evidence must be countable by the system's own read.

    A `DecisionRecorder` whose allocation is parentless writes real,
    settled, receipted operations that the study's contamination scanner
    cannot see, so a run reports fewer operations than it made. Break by
    seeding the recorder's allocation without a parent, or by leaving the
    study root unbound on the operation payload.
    """
    from experiments.ad01 import agenda_policy, selection

    with _studied(migrated_db, "a8study", "a8study-alloc",
                  {"max_operations": 512, "max_development": 512,
                   "max_model_calls": 0}) as study_root:
        run = selection.run_investigations(
            selection.portfolio_for_world(0), agenda_policy.agenda_policy(),
            selection.Allocation(authorized=40), world=0, dsn=migrated_db,
            campaign="a8study-cell", study_root=study_root,
            study_allocation="a8study-alloc")

        recorded = [r["operation_id"] for r in run.operations]
        settled = [r for r in recorded if not r.startswith("x")]
        seen = _counted_by_study_scanner(migrated_db, study_root)

    assert settled, (
        "the recorder admitted nothing, so the parent's absence is "
        "untested rather than repaired")
    assert not run.refusals, (
        "the recorder was refused: %r" % run.refusals[:1])
    assert set(settled) <= seen, (
        "%d of %d operations the recorder really created are invisible to "
        "the study's own contamination scanner; invisible: %r"
        % (len(set(settled) - seen), len(set(settled)),
           sorted(set(settled) - seen)[:4]))


def test_a_parentless_recorder_allocation_is_reported_not_silently_blind(migrated_db):
    """A run with no study root still says its operations are unadopted.

    `run_investigations` is called without a `study_root` all over the
    suite, and those runs are real. The property is that the run reports
    the fact rather than leaving a blind spot nobody is told about. Break
    by reporting `adopted: 0` for a run whose operations were all
    adopted.
    """
    from experiments.ad01 import agenda_policy, selection

    run = selection.run_investigations(
        selection.portfolio_for_world(0), agenda_policy.agenda_policy(),
        selection.Allocation(authorized=40), world=0, dsn=migrated_db,
        campaign="a8orphan-cell")

    assert run.operations, "the recorder admitted nothing to orphan"
    assert run.orphaned_operations == len(run.operations), (
        "a run with no study root has %d operations and reports %d of them "
        "as orphaned"
        % (len(run.operations), run.orphaned_operations))
    assert run.adopted_operations == 0


@pytest.fixture
def migrated_db():
    from experiments.ad01 import s09_run_isolation as iso

    database = iso.create_disposable_db("a7a8")
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database)
