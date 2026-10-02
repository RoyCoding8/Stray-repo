from __future__ import annotations

import os
from pathlib import Path

import psycopg


def resolve_dsn(explicit: str | None = None) -> str:
    dsn = explicit or os.environ.get("SETTLEMENT_DSN", "")
    if not dsn:
        raise RuntimeError("SETTLEMENT_DSN is not configured")
    return dsn


READ_CONNECT_TIMEOUT_S = 10
READ_STATEMENT_TIMEOUT = "60s"
# The write path gets a longer budget than a read because it holds locks
# while it works, but it is still bounded: an unbounded connect is a
# silent hang rather than a slow test, and nothing here needs to wait
# indefinitely for a socket. Overridable per call for a caller that
# genuinely needs longer.
WRITE_CONNECT_TIMEOUT_S = 30


def connect(dsn: str, **kwargs):
    kwargs.setdefault("autocommit", False)
    kwargs.setdefault("connect_timeout", WRITE_CONNECT_TIMEOUT_S)
    return psycopg.connect(dsn, **kwargs)


def read_connect(dsn: str):
    return connect(dsn, connect_timeout=READ_CONNECT_TIMEOUT_S,
                   options=f"-c statement_timeout={READ_STATEMENT_TIMEOUT}")


_AUTHORITY_FIELDS = ("user", "password", "host", "port", "dbname")


def database_url(dsn: str) -> str:
    """The SQLAlchemy URL for a libpq conninfo, losslessly.

    psycopg reads either form; SQLAlchemy reads only the URL, so a conninfo
    passed to it raises rather than degrades. The two spellings carry the same
    fields, so the conversion moves rather than edits them: a password that
    went missing here would connect as an anonymous local user and read a
    fixture's store as though it were empty.

    A ``host`` that names a socket directory has no place in the authority,
    where it would be percent-encoded and resolved as a DNS name. libpq takes
    it as a connection parameter instead, and the per-run test DSN is in
    exactly that form, so this is the common case here and not a corner.
    """
    from psycopg.conninfo import conninfo_to_dict
    from sqlalchemy.engine import URL

    params = conninfo_to_dict(dsn)
    if "dbname" not in params:
        raise ValueError("conninfo names no database: %r" % (dsn,))
    host = params.get("host", "")
    socket_dir = host.startswith("/")
    carried = {k: v for k, v in params.items() if k not in _AUTHORITY_FIELDS}
    if socket_dir:
        carried["host"] = host
    port = params.get("port")
    return URL.create(
        "postgresql+psycopg",
        username=params.get("user"),
        password=params.get("password"),
        host=None if socket_dir else host,
        port=int(port) if port else None,
        database=params["dbname"],
        query=carried,
    ).render_as_string(hide_password=False)


class MigrationSetEmpty(RuntimeError):
    """The migration directory yielded no `.sql` files at all.

    Raised by `apply_migrations` rather than reported as an empty success.
    A directory that exists and is empty and a directory that was never
    the migrations directory produce the same glob result, and the
    difference is a schema that was silently never migrated.
    """


def apply_migrations(dsn: str, migrations_dir: str | Path) -> list[str]:
    files = sorted(Path(migrations_dir).glob("*.sql"))
    if not files:
        # An empty glob and a directory that exists but is empty are the same
        # list, so the two cannot be told apart by their contents. The cost of
        # guessing wrong is a schema that is silently not migrated: the loop
        # below never runs, the function reports success, and the failure
        # surfaces much later as a missing relation. `apply_migrations` is
        # called with a path assembled from `Path(__file__).parent.parent`
        # in 31 archived tests, and archiving the tree moved those files one
        # level deeper -- so the wrong path is a state this repository has
        # actually been in. Refuse rather than report an empty success.
        raise MigrationSetEmpty(
            "no migrations found at %r; refusing to report an empty success"
            " for a schema that was never migrated" % (str(migrations_dir),))
    applied: list[str] = []
    with connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations"
                " (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            for path in files:
                cur.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (path.name,))
                if cur.fetchone():
                    continue
                cur.execute(path.read_text())
                cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
                applied.append(path.name)
    return applied
