from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from settlement import db

from conftest_isolation import pytest_configure, pytest_unconfigure  # noqa: F401


TRUNCATE_DSN_ENV = "SETTLEMENT_TEST_TRUNCATE_DSN"


def _dsn() -> str:
    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    return dsn


@pytest.fixture()
def dsn():
    return _dsn()


@pytest.fixture()
def migrated_db(dsn):
    truncate_dsn = os.environ.get(TRUNCATE_DSN_ENV, "")
    if not truncate_dsn:
        pytest.fail(
            f"{TRUNCATE_DSN_ENV} must be set to authorize test truncation")
    if truncate_dsn != dsn:
        pytest.fail(
            f"{TRUNCATE_DSN_ENV} must match SETTLEMENT_TEST_DSN")
    db.apply_migrations(dsn, Path(__file__).parent.parent / "migrations")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            for table in _tables(cur):
                cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        conn.commit()
    yield dsn


def _tables(cur) -> list[str]:
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'schema_migrations'"
    )
    return [row[0] for row in cur.fetchall()]


@pytest.fixture()
def tmp_roots(tmp_path):
    artifacts = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    artifacts.mkdir()
    staging.mkdir()
    return {"artifacts": artifacts, "staging": staging}


def unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def live_mission(objective: str, environments: list) -> dict:
    """The charter shape `ensure_live_store` accepts, for fixtures.

    This was `live_construct.live_mission`, deleted in 8d354a5 because it had
    zero production callers: the live entry passes `None` and the declaration is
    read from `investigations`. Nine test files still need the shape, and
    inlining it nine times is worse than the one function it replaces, so it
    lives here where it is honestly labelled a fixture.

    The refusals are kept because they are the contract: an empty objective or
    an empty environment list names no mission, and a fixture that built such a
    dict would be asserting against a store that refuses to open.
    """
    from experiments.ad01.live_construct import LiveRefused

    if not isinstance(objective, str) or not objective.strip():
        raise LiveRefused("live mission needs an objective")
    if not isinstance(environments, list) or not environments:
        raise LiveRefused("live mission needs frozen environments")
    return {"objective": objective,
            "environments": list(environments),
            "constraints": [],
            "success_criteria": []}


@pytest.fixture(autouse=True)
def _isolate_campaign_namespace():
    """Reset the process-global campaign namespace around every test.

    `trajectory.NAMESPACE_TOKEN` is module state, and `s09_pilot.run_study`
    sets it without ever clearing it. Without this, the first test that runs a
    study leaves its token behind and every later test in the session mints
    campaign ids carrying someone else's token. That is how one test file's
    leak reached nine others as `malformed campaign id`, and it is a property
    of the ordering rather than of any one file.

    Resetting per test is the only place that can hold: pinning it in each
    file leaves the next file exposed to whichever ran first.
    """
    from experiments.ad01 import trajectory
    previous = trajectory.NAMESPACE_TOKEN
    trajectory.set_namespace_token("")
    try:
        yield
    finally:
        trajectory.set_namespace_token(previous)
