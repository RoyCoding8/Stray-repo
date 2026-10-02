"""Run isolation for S09: one disposable store and one unique identity per run.

A contaminated S09 live run exists because two different things were called
"the run". The doubles dry run and the live run shared one database, and
``experiments/ad01/construct.py:27`` derived its operation id from
``"ad01-%s-construct-l%d-%s" % (cid, lineage, attempt)`` where ``cid`` is
mode-independent. A live run could therefore read the doubles' already
settled receipt for the same key, and serve a ``recorded-double`` response
to a freeze that declared a live model.

An output directory and a ``mode`` label are not isolation. Both are
caller-written metadata: one is trivially pointed at the same place twice,
the other is a string. What makes two runs disjoint is that they never
share a store, and that every durable name they mint carries a token the
caller supplied rather than one it derived from mode or output path. So the
only way to get a run identity in this module is
:class:`RunIsolation`, and an identity is obtainable only from a
:class:`DisposableDatabase` whose name carries that token.

The gate closes the remaining hole. A run that reuses a store reuses the
store fingerprint, so a freeze can be compared against what the store
actually persisted: any operation bound to another study root, any
``model-inference`` request naming a model the freeze did not declare, and
any successful receipt older than the freeze is a refusal, not a warning.
"""

from __future__ import annotations

import contextlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, NamedTuple
from urllib.parse import urlparse, urlunparse

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"

DB_PREFIX = "s09iso"
DEFAULT_ADMIN_DSN = "dbname=postgres host=/var/run/postgresql user=ubuntu"

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


class IsolationRefusal(RuntimeError):
    """A proposed run does not match the store it would write to."""


class DisposableDatabaseError(RuntimeError):
    pass


class FrozenRun(NamedTuple):
    """What a freeze asserts about a run, and when it was asserted."""

    study_root: str
    model: str
    adapter: str
    frozen_at: datetime


class Contamination(NamedTuple):
    """One persisted fact that contradicts the proposed freeze."""

    kind: str
    operation_id: str
    detail: str


class GateVerdict(NamedTuple):
    """Refusal, or the evidence count that licensed admission."""

    admitted: bool
    findings: tuple[Contamination, ...]
    operations_scanned: int
    receipts_scanned: int

    def refusal_reason(self) -> str:
        if self.admitted:
            return ""
        return "; ".join("%s %s: %s" % (f.kind, f.operation_id, f.detail)
                         for f in self.findings)


@dataclass(frozen=True)
class RunIdentity:
    """Every durable name one run mints, all bound to one store."""

    token: str
    study_root: str
    campaign_id: str
    allocation_id: str
    store_fingerprint: str
    model: str
    adapter: str
    gateway_mode: str

    def operation_id(self, *parts: str) -> str:
        return "%s-%s" % (self.campaign_id, "-".join(_identifier(p, "operation part")
                                                     for p in parts))

    def construction_operation_id(self, lineage: int, attempt: str) -> str:
        if isinstance(lineage, bool) or not isinstance(lineage, int) \
                or lineage <= 0:
            raise ValueError("lineage must be a positive integer")
        return self.operation_id("construct", "l%d" % lineage, attempt)

    def as_dict(self) -> dict:
        return {"token": self.token, "study_root": self.study_root,
                "campaign_id": self.campaign_id,
                "allocation_id": self.allocation_id,
                "store_fingerprint": self.store_fingerprint,
                "model": self.model, "adapter": self.adapter,
                "gateway_mode": self.gateway_mode}


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


def _identifier(value: str, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % what)
    if not NAME_RE.match(value):
        raise ValueError("%s carries characters no store column accepts: %r"
                         % (what, value))
    return value


def _quoted(name: str) -> str:
    if '"' in name:
        raise DisposableDatabaseError(
            "disposable database name carries a quote: %r" % name)
    return '"%s"' % name


def _admin_dsn(admin_dsn: str | None) -> str:
    import os

    return admin_dsn or os.environ.get("SETTLEMENT_TEST_DSN") \
        or DEFAULT_ADMIN_DSN


def admin_dsn() -> str:
    """The connection ``SETTLEMENT_TEST_DSN`` names, defaulting to local.

    Exposed as a function so a test module can resolve the admin once and
    pass the same value to create and drop, rather than letting each call
    re-read the environment and land on a different instance mid-test.
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


def _as_utc(value: datetime, what: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("%s must be a datetime" % what)
    if value.tzinfo is None:
        raise ValueError("%s must carry a timezone" % what)
    return value.astimezone(timezone.utc)


def study_root_for(token: str) -> str:
    return "s09iso-%s-root" % _checked_token(token)


def campaign_for(token: str) -> str:
    return "s09iso-%s-w0" % _checked_token(token)


def allocation_for(token: str) -> str:
    return "s09iso-%s-alloc" % _checked_token(token)


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
    db.apply_migrations(database.dsn, migrations_dir or MIGRATIONS)
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


class RunIsolation:
    """A store, the identity bound to it, and the gate that guards both."""

    def __init__(self, database: DisposableDatabase, identity: RunIdentity,
                 frozen_at: datetime) -> None:
        if not isinstance(database, DisposableDatabase):
            raise ValueError("a run needs a disposable database")
        self._database = database
        self._identity = identity
        self._frozen_at = _as_utc(frozen_at, "frozen_at")

    @classmethod
    def build(cls, database: DisposableDatabase, *, model: str, adapter: str,
              gateway_mode: str, frozen_at: datetime | None = None,
              authorized: int = DEFAULT_AUTHORIZED) -> RunIsolation:
        """Authorize the study in ``database`` and mint the run's identity."""
        from settlement import authority

        if gateway_mode not in GATEWAY_MODES:
            raise ValueError("gateway mode must be one of %s"
                             % (", ".join(GATEWAY_MODES),))
        _identifier(model, "model")
        _identifier(adapter, "adapter")
        if isinstance(authorized, bool) or not isinstance(authorized, int) \
                or authorized <= 0:
            raise ValueError("authorized must be a positive integer")
        handle = authority.authorize_study(
            database.dsn, study_root_for(database.token),
            authorized=authorized,
            allocation_id=allocation_for(database.token))
        identity = RunIdentity(
            token=database.token,
            study_root=handle.study_root,
            campaign_id=campaign_for(database.token),
            allocation_id=handle.allocation_id,
            store_fingerprint=handle.store_fingerprint,
            model=model, adapter=adapter, gateway_mode=gateway_mode)
        return cls(database, identity,
                   frozen_at or datetime.now(timezone.utc))

    @property
    def dsn(self) -> str:
        return self._database.dsn

    @property
    def database(self) -> DisposableDatabase:
        return self._database

    @property
    def identity(self) -> RunIdentity:
        return self._identity

    @property
    def frozen_at(self) -> datetime:
        return self._frozen_at

    def freeze(self) -> FrozenRun:
        return FrozenRun(study_root=self._identity.study_root,
                         model=self._identity.model,
                         adapter=self._identity.adapter,
                         frozen_at=self._frozen_at)

    def bind(self) -> RunIsolation:
        """Refuse a store that is not the one this identity was minted for.

        The store fingerprint is the only durable fact that separates two
        databases carrying the same study root, and it is the one
        ``authorize_study`` silently accepts on a fresh store. A run that
        points at someone else's store therefore has to be refused here.
        """
        from settlement import authority

        handle = authority.bind_study(self.dsn, self._identity.study_root)
        if handle.store_fingerprint != self._identity.store_fingerprint:
            raise IsolationRefusal(
                "study %s is bound to another store: identity pinned %s,"
                " store holds %s"
                % (self._identity.study_root,
                   self._identity.store_fingerprint, handle.store_fingerprint))
        return self

    def admit(self) -> GateVerdict:
        return check_namespace(self.dsn, self.freeze())

    def admit_or_refuse(self) -> GateVerdict:
        verdict = self.admit()
        if not verdict.admitted:
            raise IsolationRefusal(
                "store %s contradicts the %s freeze of %s: %s"
                % (self._database.name, self._identity.gateway_mode,
                   self._identity.model, verdict.refusal_reason()))
        return verdict


@contextlib.contextmanager
def isolated_run(token: str, *, model: str, adapter: str,
                 gateway_mode: str, admin_dsn: str | None = None,
                 migrations_dir: str | Path | None = None,
                 frozen_at: datetime | None = None) -> Iterator[RunIsolation]:
    """A disposable store plus the one identity that may write to it."""
    with disposable_db(token, admin_dsn=admin_dsn,
                       migrations_dir=migrations_dir) as database:
        yield RunIsolation.build(database, model=model, adapter=adapter,
                                 gateway_mode=gateway_mode,
                                 frozen_at=frozen_at)


def _persisted_operations(dsn: str, study_root: str) -> list[dict]:
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT o.id, o.payload, r.receipt_identity, r.outcome,"
                " r.created_at AS receipt_created_at"
                " FROM operations o"
                " JOIN study_authority a"
                " ON a.allocation_id = ("
                "   WITH RECURSIVE up (id, parent_id) AS ("
                "     SELECT id, parent_id FROM allocations WHERE id = o.allocation_id"
                "     UNION ALL"
                "     SELECT l.id, l.parent_id FROM allocations l"
                "     JOIN up ON l.id = up.parent_id)"
                "   SELECT id FROM up WHERE id = a.allocation_id)"
                " LEFT JOIN receipts r ON r.operation_id = o.id"
                " WHERE a.study_root = %s ORDER BY o.id, r.receipt_identity",
                (study_root,))
            rows = [dict(row) for row in cur.fetchall()]
        conn.commit()
    return rows


def check_namespace(dsn: str, frozen: FrozenRun) -> GateVerdict:
    """Report every persisted fact that contradicts ``frozen``."""
    if not dsn:
        raise ValueError("namespace checks need a database DSN")
    if not isinstance(frozen, FrozenRun):
        raise ValueError("frozen must be a FrozenRun")
    cutoff = _as_utc(frozen.frozen_at, "frozen_at")
    findings: list[Contamination] = []
    operations = receipts = 0
    for row in _persisted_operations(dsn, frozen.study_root):
        operations += 1
        payload = dict(row.get("payload") or {})
        operation_id = str(row.get("id") or "")
        stored_root = payload.get("study_root")
        if stored_root is not None and stored_root != frozen.study_root:
            findings.append(Contamination(
                "foreign-study-root", operation_id,
                "persisted study root %r is not the frozen %r"
                % (stored_root, frozen.study_root)))
        if payload.get("effect") == MODEL_INFERENCE:
            request = dict(payload.get("payload") or {})
            model = str(request.get("model") or "")
            if model != frozen.model:
                findings.append(Contamination(
                    "foreign-model", operation_id,
                    "persisted request model %r is not the frozen %r"
                    % (model, frozen.model)))
        if row.get("outcome") != "success":
            continue
        receipts += 1
        created = row.get("receipt_created_at")
        if isinstance(created, datetime) \
                and _as_utc(created, "receipt_created_at") < cutoff:
            findings.append(Contamination(
                "receipt-predates-freeze", operation_id,
                "successful receipt %s at %s precedes the freeze at %s"
                % (row.get("receipt_identity"), created.isoformat(),
                   cutoff.isoformat())))
    return GateVerdict(admitted=not findings, findings=tuple(findings),
                       operations_scanned=operations,
                       receipts_scanned=receipts)


def admit_live_run(isolation: RunIsolation) -> GateVerdict:
    """Refuse a run whose store already contradicts its own freeze."""
    if not isinstance(isolation, RunIsolation):
        raise ValueError("admission needs a RunIsolation")
    return isolation.bind().admit_or_refuse()


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
