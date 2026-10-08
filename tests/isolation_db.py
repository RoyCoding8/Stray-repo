"""Disposable PostgreSQL databases for kernel tests."""

from __future__ import annotations

import contextlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse, urlunparse

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"

DB_PREFIX = "s09iso"

TOKEN_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,23}\Z")
NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")

# The bare 8-hex token space belongs to the pytest harness and to nothing else.
# ``tests/conftest_isolation.DERIVED_NAME_RE`` reads exactly eight hex digits
# after ``s09iso_`` as "this database belongs to a pytest run", and the stale
# sweep will reclaim any such database whose token no live process holds a lock
# on. A direct runner mints no such lock, so a name in that space is a live
# run's stores with no way to prove they are abandoned.
#
# The grammar was carrying the safety by accident, not by construction: every
# runner that happens to prefix its token with text (``ctlwalk``, ``r4diag``,
# ``e3ladder``) falls outside the pattern, so the sweep has never selected one.
# A caller-supplied token removes the accident. ``experiments/ad01/s09_m3_pilot``
# takes ``--token`` from the command line, and ``--token deadbeef`` mints
# ``s09iso_deadbeef_<uuid12>`` -- indistinguishable, to the sweep, from a pytest
# run's own database. Refusing the space here closes it for every caller at the
# one point they all pass through.
#
# It cannot be the lock instead. ``lock_key`` requires a token matching the
# harness's own 8-hex ``TOKEN_RE``, so a direct runner's ``ctlwalk1a2b3c4d``
# cannot take a ``RunClaim`` at all; and a lock held by a process that
# ``run_bounded.py`` kills with SIGKILL is released by the server without ever
# running a cleanup path, so it is not a durable claim either. A name is a
# property of the database and outlives every process that could have made it.
#
# This mirrors ``tests/conftest_isolation.DERIVED_NAME_RE``. The two cannot
# import each other -- the harness already imports this module -- so
# ``tests/test_sweep_token_grammar.py`` asserts they still agree.
SWEEP_SELECTED_TOKEN_RE = re.compile(r"\A[0-9a-f]{8}\Z")

GATEWAY_MODES = ("doubles", "live", "controlled")

MODEL_INFERENCE = "model-inference"

DEFAULT_AUTHORIZED = 1_000_000


class DisposableDatabaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class DisposableDatabase:
    """A uniquely named store that exists for the length of one ``with``."""

    name: str
    dsn: str
    token: str

    def __post_init__(self) -> None:
        if not self.name.startswith(DB_PREFIX + "_"):
            raise DisposableDatabaseError(
                "refusing a database that is not marked disposable: %r"
                % (self.name,))
        if self.token not in self.name:
            raise DisposableDatabaseError(
                "disposable database name %r omits its caller token %r"
                % (self.name, self.token))


def _checked_token(token: str) -> str:
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        raise ValueError("isolation token must match %s, got %r"
                         % (TOKEN_RE.pattern, token))
    if SWEEP_SELECTED_TOKEN_RE.match(token):
        raise ValueError(
            "isolation token %r is 8 bare hex digits, which is the pytest "
            "harness's own run-token space: a store named s09iso_%s_... is "
            "indistinguishable from a pytest run's, and the stale sweep would "
            "reclaim it with no lock to prove this run is not live. Use a "
            "token with a text prefix, e.g. 'm3dry'." % (token, token))
    return token


def _quoted(name: str) -> str:
    if '"' in name:
        raise DisposableDatabaseError(
            "disposable database name carries a quote: %r" % name)
    return '"%s"' % name


class MissingRouteError(RuntimeError):
    """No route was named for reaching a PostgreSQL server.

    A caller that reaches this never guessed: ``SETTLEMENT_TEST_DSN`` (or the
    ``admin_dsn`` argument) is the one way to name the route, and a session
    with none configured has no database to reach. The string this replaces
    was a ``host=/var/run/postgresql user=ubuntu`` default, which turned
    "no route named" into "connect to the author's WSL box" on every host
    that never had that socket -- the measured 554-line portable noise
    floor (run 37367150028).
    """


def _admin_dsn(admin_dsn: str | None) -> str:
    import os

    route = admin_dsn or os.environ.get("SETTLEMENT_TEST_DSN") or ""
    if not route:
        raise MissingRouteError(
            "no route to a PostgreSQL server: set SETTLEMENT_TEST_DSN"
            " (conninfo, e.g. 'dbname=postgres host=127.0.0.1"
            " port=5432 user=postgres')")
    return route


def admin_dsn() -> str:
    """The connection ``SETTLEMENT_TEST_DSN`` names, or a refusal.

    Exposed as a function so a test module can resolve the admin once and
    pass the same value to create and drop, rather than letting each call
    re-read the environment and land on a different instance mid-test.

    There is deliberately no local default. A default names a route the
    caller never chose, so an unconfigured session refuses here instead of
    connecting somewhere it cannot reach.
    """
    return _admin_dsn(None)


def _dsn_for(admin: str, name: str) -> str:
    parts = urlparse(admin)
    if parts.scheme:
        return urlunparse((parts.scheme, parts.netloc, "/" + name, "",
                           parts.query, ""))
    fields = admin.split()
    return " ".join([f for f in fields if not f.startswith("dbname=")]
                    + ["dbname=%s" % name])


def create_disposable_db(token: str, *, admin_dsn: str | None = None,
                         migrations_dir: str | Path | None = None) -> DisposableDatabase:
    """Create, migrate and return a store whose name carries ``token``."""
    import psycopg

    from settlement import db

    name = "%s_%s_%s" % (DB_PREFIX, _checked_token(token),
                         uuid.uuid4().hex[:12])
    admin = _admin_dsn(admin_dsn)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute("CREATE DATABASE %s" % _quoted(name))
    database = DisposableDatabase(name=name, dsn=_dsn_for(admin, name),
                                  token=_checked_token(token))
    try:
        db.apply_migrations(database.dsn, migrations_dir or MIGRATIONS)
    except Exception:
        drop_disposable_db(database, admin_dsn=admin)
        raise
    return database


def drop_disposable_db(database: DisposableDatabase, *,
                       admin_dsn: str | None = None) -> None:
    import psycopg

    if not isinstance(database, DisposableDatabase) \
            or not database.name.startswith(DB_PREFIX + "_"):
        raise DisposableDatabaseError(
            "refusing to drop a database that is not marked disposable: %r"
            % (getattr(database, "name", database),))
    with psycopg.connect(_admin_dsn(admin_dsn), autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS %s WITH (FORCE)"
                     % _quoted(database.name))


@contextlib.contextmanager
def disposable_db(token: str, *, admin_dsn: str | None = None,
                  migrations_dir: str | Path | None = None) -> Iterator[DisposableDatabase]:
    database = create_disposable_db(token, admin_dsn=admin_dsn,
                                    migrations_dir=migrations_dir)
    try:
        yield database
    finally:
        drop_disposable_db(database, admin_dsn=admin_dsn)


__all__ = [
    "Contamination",
    "DisposableDatabase",
    "DisposableDatabaseError",
    "FrozenRun",
    "GateVerdict",
    "IsolationRefusal",
    "RunIdentity",
    "RunIsolation",
    "admin_dsn",
    "admit_live_run",
    "allocation_for",
    "campaign_for",
    "check_namespace",
    "create_disposable_db",
    "disposable_db",
    "drop_disposable_db",
    "isolated_run",
    "study_root_for",
]
