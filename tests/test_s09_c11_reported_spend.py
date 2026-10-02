"""The preflight's already-spent count must be the store's, not a declaration.

`reported_spend` read `S09_STUDY_CALLS_ALREADY_SPENT`, and nothing in the
repository writes that name. `invl02_live._load_live_env` copies four gateway
and grant variables out of the environment file and that name is not one of
them, so the value was hand-authored from a cap sheet, and a crash between
sends and a resume left it reading what it read before the first send. The
preflight then handed the study a ceiling measured from a fiction, which is
the failure the freeze exists to prevent.

The preflight already opens the study's store and already counts every
operation row it reads, so the durable derivation costs one subtraction and
no new connection.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import s09_study_preflight as preflight
from experiments.ad01.s09_run_isolation import disposable_db
from experiments.ad01.s09_study_preflight import (
    Observations,
    Precondition,
    Verdict,
)

PG_HOST = "/var/run/postgresql"
RUN_TOKEN = "c11reported"
MODEL = "frozen-model-under-test"
STUDY_ROOT = "s09-m5-pilot"
FROZEN_AT = "2000-01-01T00:00:00+00:00"
DECLARED = "S09_STUDY_CALLS_ALREADY_SPENT"


@pytest.fixture()
def dsn():
    with disposable_db(RUN_TOKEN,
                       migrations_dir=ROOT / "migrations") as database:
        yield "postgresql:///?%s" % urlencode(
            {"host": PG_HOST, "dbname": database.name})


def _freezer() -> preflight.StudyFreeze:
    return preflight.StudyFreeze(study_id="s09-preflight",
                                 study_root=STUDY_ROOT, model=MODEL,
                                 frozen_at=FROZEN_AT, digest="d" * 64)


def _send(dsn: str, operation_id: str) -> None:
    from settlement import db
    payload = {"effect": "model-inference", "study_root": STUDY_ROOT,
               "model": MODEL}
    with db.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO operations (id, payload_digest, payload, created_at)"
            " VALUES (%s, 'digest', %s, now())",
            (operation_id, psycopg.types.json.Json(payload)))
        conn.commit()


def _ledger(carried: int) -> preflight.ExposureLedger:
    return preflight.ExposureLedger(
        study_id="prior-exposure", source="ledger", carried_units=carried,
        all_verified=True, arithmetic="%d" % carried,
        terms=(preflight.ExposureTerm(label="held", units=carried,
                                       evidence="v"),))


def _observed(dsn: str) -> Observations:
    """What `collect` builds, with the two unavailable probes left absent."""
    database = preflight.observe_database(
        preflight.study_database(dsn), _freezer())
    return Observations(
        freeze=_freezer(), database=database, exposure=_ledger(3), ceiling=20,
        already_spent=preflight.already_spent_in_store(database))


def test_three_sends_in_the_store_leave_seventeen(dsn) -> None:
    for attempt in range(3):
        _send(dsn, "ad01-%s-b0-construct-%d" % (STUDY_ROOT, attempt))

    outcome = preflight.evaluate(
        _observed(dsn)).outcome(Precondition.EXPOSURE_BUDGET)

    assert outcome.verdict.status is Verdict.PASS
    assert outcome.verdict.evidence == (
        "ceiling of 20 dispatches less 3 already spent leaves 17 dispatches "
        "for study prior-exposure; the 3 held reservation units under ledger "
        "are a separate currency and are not charged against sends")
    assert json.loads(outcome.detail) == {
        "already_spent_dispatches": 3, "ceiling_dispatches": 20,
        "remaining_dispatches": 17}


def test_a_send_the_env_var_never_saw_still_closes_the_ceiling(dsn) -> None:
    _send(dsn, "ad01-%s-b0-construct" % STUDY_ROOT)

    outcome = preflight.evaluate(
        _observed(dsn)).outcome(Precondition.EXPOSURE_BUDGET)

    assert outcome.verdict.status is Verdict.PASS
    assert json.loads(outcome.detail)["already_spent_dispatches"] == 1


def test_the_ceiling_is_enforced_against_the_store_not_the_declaration(
        dsn, monkeypatch) -> None:
    """A run that over-spent is refused, however it was told it had not.

    Three sends reached the gateway and the declaration still reads zero,
    which is the state a crash between send and resume leaves behind. A
    ceiling of 2 is already spent three times over.
    """
    monkeypatch.setenv(DECLARED, "0")
    for attempt in range(3):
        _send(dsn, "ad01-%s-b0-construct-%d" % (STUDY_ROOT, attempt))

    observations = dataclasses.replace(_observed(dsn), ceiling=2)
    outcome = preflight.evaluate(observations).outcome(
        Precondition.EXPOSURE_BUDGET)

    assert os.environ[DECLARED] == "0"
    assert outcome.verdict.status is Verdict.FAIL
    assert outcome.verdict.refusal is preflight.Refusal.BUDGET_UNRESOLVED
    assert json.loads(outcome.detail) == {
        "already_spent_dispatches": 3, "ceiling_dispatches": 2,
        "remaining_dispatches": -1}


def test_a_declaration_contradicting_the_store_does_not_move_the_count(
        dsn, monkeypatch) -> None:
    monkeypatch.setenv(DECLARED, "17")
    for attempt in range(3):
        _send(dsn, "ad01-%s-b0-construct-%d" % (STUDY_ROOT, attempt))

    observations = dataclasses.replace(_observed(dsn), ceiling=20)
    outcome = preflight.evaluate(observations).outcome(
        Precondition.EXPOSURE_BUDGET)

    assert outcome.verdict.status is Verdict.PASS
    assert json.loads(outcome.detail) == {
        "already_spent_dispatches": 3, "ceiling_dispatches": 20,
        "remaining_dispatches": 17}


def test_a_store_the_preflight_could_not_read_spends_nothing(dsn) -> None:
    """An unreadable store must be an unknown, not a zero.

    Defaulting the count to zero here would re-open the same hole for every
    database that is briefly unreachable, which is the more common case.
    """
    name = "s09iso_%s-unreadable" % RUN_TOKEN
    refused = preflight.DatabaseObservation(
        database=preflight.StudyDatabase("postgresql:///%s?dbname=%s"
                                         % (PG_HOST, name), name),
        refused="could not connect to server")

    spent = preflight.already_spent_in_store(refused)

    assert spent is None
    observations = dataclasses.replace(_observed(dsn), database=refused,
                                       already_spent=spent)
    outcome = preflight.evaluate(observations).outcome(
        Precondition.EXPOSURE_BUDGET)

    assert outcome.verdict.status is Verdict.UNKNOWN
    assert outcome.verdict.refusal is preflight.Refusal.BUDGET_UNRESOLVED
    assert "an already-spent count" in outcome.verdict.reported


def test_the_declaration_env_var_is_gone_from_the_preflight() -> None:
    assert not hasattr(preflight, "REPORTED_SPENT_VAR")
    assert not hasattr(preflight, "reported_spend")
    import ast
    tree = ast.parse(Path(preflight.__file__).read_text(encoding="utf-8"))
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)}
    assert DECLARED not in literals
