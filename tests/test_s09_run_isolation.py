"""S09 run isolation: unique durable identity and a live/doubles admission gate.

The gate creates its own disposable database, so it never skips on an
unconfigured DSN and never truncates a pre-existing store.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from experiments.ad01 import construct
from experiments.ad01 import s09_run_isolation as iso
from settlement import authority, broker, db, store

from tests.conftest_isolation import admin_dsn

LIVE_MODEL = "openrouter/live:1"
DOUBLES_MODEL = "recorded-double"
ADAPTER = "settlement.gateway_http.HttpGatewayAdapter"
AUTHORIZED = iso.DEFAULT_AUTHORIZED


def _pg_route_fields() -> str:
    """The route with its dbname stripped -- the connection fields a store
    name plugs into. Resolved at call time: an import-time binding would
    raise on a routeless session and kill collection of the whole suite."""
    return " ".join(f for f in admin_dsn().split()
                    if not f.startswith("dbname="))

REQUEST = {"model": DOUBLES_MODEL,
           "messages": [{"role": "user", "content": "look"}],
           "max_output_tokens": 8, "deadline_ms": 10_000}


def token() -> str:
    return "t%s" % uuid.uuid4().hex[:10]


def test_failed_migration_does_not_leave_a_disposable_database(tmp_path):
    route = admin_dsn()
    prefix = "s09iso_%s_" % token()
    run_token = prefix[len("s09iso_"):-1]
    try:
        with pytest.raises(db.MigrationSetEmpty):
            iso.create_disposable_db(
                run_token, admin_dsn=route, migrations_dir=tmp_path)
        with psycopg.connect(route) as conn:
            left = conn.execute(
                "SELECT datname FROM pg_database WHERE starts_with(datname, %s)",
                (prefix,)).fetchall()
        assert left == [], "failed migration leaked its newly created database"
    finally:
        with psycopg.connect(route, autocommit=True) as conn:
            for (name,) in conn.execute(
                    "SELECT datname FROM pg_database WHERE starts_with(datname, %s)",
                    (prefix,)).fetchall():
                conn.execute(psycopg.sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    psycopg.sql.Identifier(name)))


def expected_migrations() -> int:
    """How many migrations the store was built from, asked rather than pinned.

    A disposable database is migrated from the directory, so the count in
    `schema_migrations` is the number of `.sql` files there. Two migrations
    landed in this batch and a literal written before them re-broke this
    file twice. Reading the same glob `apply_migrations` reads keeps the
    assertion true through the next migration: what would fail is a store
    that took the wrong directory, or a migration that failed to record
    itself, not the arrival of a new file.
    """
    return len(sorted(Path(iso.MIGRATIONS).glob("*.sql")))


def rows(dsn: str, sql: str, params=()) -> list[dict]:
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            found = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return found


def one(dsn: str, sql: str, params=()) -> dict:
    found = rows(dsn, sql, params)
    assert len(found) == 1, found
    return found[0]


def insert_operation(dsn: str, operation_id: str, *, allocation_id: str,
                     study_root: str, model: str) -> str:
    payload = {"effect": iso.MODEL_INFERENCE, "study_root": study_root,
               "payload": dict(REQUEST, model=model)}
    with db.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO operations (id, allocation_id, payload_digest, payload,"
            " dispatch_state, settled) VALUES (%s, %s, %s, %s, 'observed', TRUE)",
            (operation_id, allocation_id, "digest-" + operation_id,
             Jsonb(payload)))
        conn.commit()
    return operation_id


def insert_receipt(dsn: str, operation_id: str, *, created_at: datetime,
                   outcome: str = "success") -> str:
    identity = "gw:%s" % operation_id
    with db.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO receipts (receipt_identity, operation_id, content_digest,"
            " content, outcome, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (identity, operation_id, "cd-" + operation_id,
             Jsonb({"operation_id": operation_id, "text": "doubled"}), outcome,
             created_at))
        conn.commit()
    return identity


def study_created_at(dsn: str) -> datetime:
    return one(dsn, "SELECT created_at FROM study_authority")["created_at"]


def seed_request(dsn: str, identity: iso.RunIdentity, *, model: str) -> str:
    return insert_operation(dsn, identity.construction_operation_id(1, "init"),
                            allocation_id=identity.allocation_id,
                            study_root=identity.study_root, model=model)


def seed_old_receipt(dsn: str, identity: iso.RunIdentity, *, model: str,
                     age: timedelta) -> tuple[str, str]:
    operation_id = seed_request(dsn, identity, model=model)
    identity_of_receipt = insert_receipt(
        dsn, operation_id, created_at=study_created_at(dsn) - age)
    return operation_id, identity_of_receipt


def other_namespace(live_run):
    return iso.RunIdentity(
        **{**live_run.identity.as_dict(),
           "study_root": "s09iso-other-root",
           "allocation_id": "s09iso-other-alloc",
           "gateway_mode": "doubles"})


@pytest.fixture()
def live_run():
    with iso.isolated_run(token(), model=LIVE_MODEL, adapter=ADAPTER,
                          gateway_mode="live") as run:
        yield run


def test_legacy_construct_id_ignores_mode_and_directory():
    doubles = construct._op_id("ad01-w0-P1-54", 1, "init")
    live = construct._op_id("ad01-w0-P1-54", 1, "init")
    assert doubles == "ad01-ad01-w0-P1-54-construct-l1-init"
    assert live == doubles


def test_identity_op_id_is_determined_by_study_structure_not_mode(live_run):
    doubles = live_run.identity.__class__(
        **{**live_run.identity.as_dict(), "gateway_mode": "doubles"})
    assert doubles.operation_id("policy", "l0", "init") == \
        live_run.identity.operation_id("policy", "l0", "init")
    assert doubles.campaign_id == live_run.identity.campaign_id


def test_two_tokens_mint_different_operation_ids():
    # Text-prefixed tokens, not "a" * 8: an 8-hex-digit token is the pytest
    # harness's own run-token space and `_checked_token` refuses it, because a
    # store named after it would be reclaimable by the stale sweep with no lock
    # to prove this run is live. The property under test is that two DIFFERENT
    # tokens mint different ids, which a text prefix preserves.
    tokens = ("toka", "tokb")
    identities = [iso.RunIdentity(
        token=t, study_root=iso.study_root_for(t),
        campaign_id=iso.campaign_for(t), allocation_id=iso.allocation_for(t),
        store_fingerprint="fp", model="m", adapter="a", gateway_mode="live")
        for t in tokens]
    left, right = identities
    assert left.construction_operation_id(1, "init") == \
        "s09iso-toka-w0-construct-l1-init"
    assert right.construction_operation_id(1, "init") == \
        "s09iso-tokb-w0-construct-l1-init"
    assert left.study_root != right.study_root
    assert left.allocation_id != right.allocation_id


def test_live_run_needs_a_disposable_store():
    with pytest.raises(ValueError):
        iso.RunIsolation("not-a-database", live_run_identity(),
                         datetime.now(timezone.utc))


def live_run_identity():
    return iso.RunIdentity(
        token="t1", study_root="s09iso-t1-root", campaign_id="s09iso-t1-w0",
        allocation_id="s09iso-t1-alloc", store_fingerprint="fp", model="m",
        adapter="a", gateway_mode="live")


def test_disposable_name_carries_the_caller_token(live_run):
    assert live_run.database.name.startswith(iso.DB_PREFIX + "_")
    assert live_run.database.token in live_run.database.name
    assert live_run.database.token in live_run.identity.study_root
    assert live_run.database.token in live_run.identity.allocation_id
    assert one(live_run.dsn, "SELECT count(*) AS n FROM schema_migrations")["n"] \
        == expected_migrations()


def test_store_refuses_a_name_that_is_not_disposable():
    with pytest.raises(iso.DisposableDatabaseError):
        iso.DisposableDatabase(name="postgres", dsn="dbname=postgres",
                               token="t123")
    with pytest.raises(iso.DisposableDatabaseError):
        iso.drop_disposable_db(iso.DisposableDatabase(
            name="ad01_live", dsn="dbname=ad01_live", token="t123"))


def test_empty_namespace_admits(live_run):
    verdict = live_run.admit()
    assert verdict.admitted is True
    assert verdict.operations_scanned == 0
    assert verdict.receipts_scanned == 0
    assert verdict.findings == ()


def test_gate_refuses_a_persisted_model_that_differs(live_run):
    operation_id = seed_request(live_run.dsn, live_run.identity,
                                model=DOUBLES_MODEL)
    verdict = live_run.admit()
    assert verdict.admitted is False
    assert verdict.operations_scanned == 1
    assert [(f.kind, f.operation_id) for f in verdict.findings] == [
        ("foreign-model", operation_id)]
    assert verdict.refusal_reason() == (
        "foreign-model %s: persisted request model %r is not the frozen %r"
        % (operation_id, DOUBLES_MODEL, LIVE_MODEL))


def test_gate_accepts_a_persisted_model_that_matches(live_run):
    operation_id = seed_request(live_run.dsn, live_run.identity,
                                model=LIVE_MODEL)
    assert iso.admit_live_run(live_run).admitted is True
    assert live_run.admit().operations_scanned == 1
    assert one(live_run.dsn, "SELECT count(*) AS n FROM operations WHERE id = %s",
               (operation_id,))["n"] == 1


def test_admit_live_run_raises_instead_of_warning(live_run):
    seed_request(live_run.dsn, live_run.identity, model=DOUBLES_MODEL)
    with pytest.raises(iso.IsolationRefusal) as raised:
        iso.admit_live_run(live_run)
    assert raised.value.args[0] == (
        "store %s contradicts the live freeze of %s: foreign-model %s: "
        "persisted request model %r is not the frozen %r"
        % (live_run.database.name, LIVE_MODEL,
           live_run.identity.construction_operation_id(1, "init"),
           DOUBLES_MODEL, LIVE_MODEL))


def test_check_detects_a_receipt_predating_the_freeze(live_run):
    operation_id, receipt = seed_old_receipt(
        live_run.dsn, live_run.identity, model=LIVE_MODEL,
        age=timedelta(seconds=1))
    verdict = iso.check_namespace(live_run.dsn, live_run.freeze())
    assert verdict.admitted is False
    assert verdict.operations_scanned == 1
    assert verdict.receipts_scanned == 1
    assert [f.kind for f in verdict.findings] == ["receipt-predates-freeze"]
    assert verdict.findings[0].operation_id == operation_id
    assert receipt in verdict.refusal_reason()


def test_a_receipt_written_after_the_freeze_is_admitted(live_run):
    seed_old_receipt(live_run.dsn, live_run.identity, model=LIVE_MODEL,
                     age=timedelta(seconds=-3600))
    verdict = iso.check_namespace(live_run.dsn, live_run.freeze())
    assert verdict.admitted is True
    assert verdict.receipts_scanned == 1


def test_gate_ignores_another_studys_namespace(live_run):
    foreign = other_namespace(live_run)
    seed_same_study_root(live_run.dsn, live_run.dsn, foreign.study_root,
                         foreign.allocation_id)
    operation_id = seed_request(live_run.dsn, foreign, model=DOUBLES_MODEL)
    assert live_run.admit().operations_scanned == 0
    assert live_run.admit().admitted is True
    assert iso.check_namespace(live_run.dsn, live_run.freeze()._replace(
        study_root=foreign.study_root)).admitted is False
    assert one(live_run.dsn, "SELECT count(*) AS n FROM operations WHERE id = %s",
               (operation_id,))["n"] == 1


def test_gate_reads_the_nested_request_payload(live_run):
    operation_id = live_run.identity.operation_id("construct", "l1", "init")
    with db.connect(live_run.dsn) as conn:
        conn.execute(
            "INSERT INTO operations (id, allocation_id, payload_digest, payload)"
            " VALUES (%s, %s, %s, %s)",
            (operation_id, live_run.identity.allocation_id, "d",
             Jsonb({"effect": iso.MODEL_INFERENCE,
                    "study_root": live_run.identity.study_root,
                    "payload": {"model": DOUBLES_MODEL}})))
        conn.commit()
    verdict = live_run.admit()
    assert verdict.admitted is False
    assert [(f.kind, f.operation_id) for f in verdict.findings] == [
        ("foreign-model", operation_id)]


def test_gate_reports_a_foreign_study_root_on_a_bound_operation(live_run):
    operation_id = live_run.identity.operation_id("construct", "l1", "init")
    with db.connect(live_run.dsn) as conn:
        conn.execute(
            "INSERT INTO operations (id, allocation_id, payload_digest, payload)"
            " VALUES (%s, %s, %s, %s)",
            (operation_id, live_run.identity.allocation_id, "d",
             Jsonb({"effect": iso.MODEL_INFERENCE, "study_root": "s09iso-other-root",
                    "payload": dict(REQUEST, model=LIVE_MODEL)})))
        conn.commit()
    assert [f.kind for f in live_run.admit().findings] == ["foreign-study-root"]


def test_two_concurrent_runs_do_not_collide():
    with iso.disposable_db(token()) as first, iso.disposable_db(token()) as second:
        assert first.name != second.name
        assert first.dsn != second.dsn
        left = iso.RunIsolation.build(first, model=LIVE_MODEL, adapter=ADAPTER,
                                      gateway_mode="live")
        right = iso.RunIsolation.build(second, model=LIVE_MODEL,
                                       adapter=ADAPTER, gateway_mode="live")
        assert left.identity.study_root != right.identity.study_root
        assert left.identity.operation_id("construct", "l1", "init") \
            != right.identity.operation_id("construct", "l1", "init")
        assert left.identity.store_fingerprint != right.identity.store_fingerprint


def test_disposable_db_is_dropped_even_when_the_body_raises():
    name = ""
    with pytest.raises(RuntimeError):
        with iso.disposable_db(token()) as database:
            name = database.name
            assert one(database.dsn,
                       "SELECT count(*) AS n FROM schema_migrations")["n"] \
                == expected_migrations()
            raise RuntimeError("run failed")
    with pytest.raises(psycopg.OperationalError):
        with db.read_connect("dbname=%s %s" % (name, _pg_route_fields())) as conn:
            conn.execute("SELECT 1")


def test_an_identity_refuses_a_store_it_was_not_minted_for():
    with iso.disposable_db(token()) as left, iso.disposable_db(token()) as right:
        minted = iso.RunIsolation.build(left, model=LIVE_MODEL,
                                        adapter=ADAPTER, gateway_mode="live")
        assert minted.bind() is minted
        seed_same_study_root(left.dsn, right.dsn,
                             minted.identity.study_root,
                             minted.identity.allocation_id)
        impostor = iso.RunIsolation(right, minted.identity,
                                    datetime.now(timezone.utc))
        with pytest.raises(iso.IsolationRefusal) as raised:
            impostor.bind()
        held = one(right.dsn, "SELECT store_fingerprint FROM study_authority"
                   " WHERE study_root = %s",
                   (minted.identity.study_root,))["store_fingerprint"]
        assert str(raised.value) == (
            "study %s is bound to another store: identity pinned %s,"
            " store holds %s"
            % (minted.identity.study_root, minted.identity.store_fingerprint,
               held))
        assert held != minted.identity.store_fingerprint


def seed_same_study_root(source: str, target: str, study_root: str,
                         allocation_id: str) -> None:
    """Give ``target`` the same study root, bound to its own store."""
    with db.connect(target) as conn:
        conn.execute(
            "INSERT INTO allocations (id, domain, authorized)"
            " VALUES (%s, 'study', %s) ON CONFLICT (id) DO NOTHING",
            (allocation_id, AUTHORIZED))
        conn.execute(
            "INSERT INTO study_authority (study_root, allocation_id, authorized,"
            " store_fingerprint)"
            " SELECT %s, %s, %s, fingerprint FROM store_identity WHERE id = 1",
            (study_root, allocation_id, AUTHORIZED))
        conn.commit()
    assert one(source, "SELECT study_root FROM study_authority"
                 " WHERE study_root = %s", (study_root,))["study_root"] \
        == study_root
    assert one(target, "SELECT study_root FROM study_authority"
                 " WHERE study_root = %s", (study_root,))["study_root"] \
        == study_root


def test_binding_a_run_to_its_own_store_is_accepted(live_run):
    assert live_run.bind() is live_run
    assert iso.admit_live_run(live_run).admitted is True


def test_broker_admission_writes_a_model_the_freeze_did_not_declare(live_run):
    operation_id = live_run.identity.operation_id("construct", "l1", "init")
    granted = authority.admit_study_call(
        live_run.dsn, live_run.identity.study_root, kind="development",
        operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload=REQUEST)
    assert granted.operation_id == operation_id
    stored = one(live_run.dsn, "SELECT payload->'payload'->>'model' AS model"
                           " FROM operations WHERE id = %s", (operation_id,))
    assert stored["model"] == DOUBLES_MODEL
    verdict = live_run.admit()
    assert verdict.admitted is False
    assert [f.kind for f in verdict.findings] == ["foreign-model"]
    with pytest.raises(iso.IsolationRefusal):
        iso.admit_live_run(live_run)
    assert store.operation_receipts(live_run.dsn, operation_id) == []


def test_check_namespace_needs_a_store_and_a_typed_freeze():
    frozen = iso.FrozenRun(study_root="s", model="m", adapter="a",
                           frozen_at=datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        iso.check_namespace("", frozen)
    with pytest.raises(ValueError):
        iso.check_namespace("dbname=x " + _pg_route_fields(), {"study_root": "s"})
    with pytest.raises(ValueError):
        iso.check_namespace("dbname=x " + _pg_route_fields(),
                            frozen._replace(frozen_at=datetime(2026, 1, 1)))


def test_unknown_gateway_mode_is_refused_before_any_write():
    with pytest.raises(ValueError):
        iso.RunIsolation.build(
            iso.DisposableDatabase(name="s09iso_x_1", dsn="dbname=nope",
                                   token="x"),
            model="m", adapter="a", gateway_mode="simulated")


def test_broken_tokens_cannot_name_a_store():
    for bad in ("", "Upper", "has space", "a" * 40, "-leading"):
        for name_of_token in (iso.study_root_for, iso.campaign_for,
                              iso.allocation_for):
            with pytest.raises(ValueError):
                name_of_token(bad)
