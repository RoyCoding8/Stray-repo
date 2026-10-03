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


REPO_MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


class MigrationSetEmpty(RuntimeError):
    """The migration directory yielded no `.sql` files at all.

    Raised by `migration_files` rather than reported as an empty success.
    A directory that exists and is empty and a directory that was never
    the migrations directory produce the same glob result, and the
    difference is a schema that was silently never migrated.
    """


class MigrationSetStale(RuntimeError):
    """The store's recorded migrations are not the directory's migrations.

    Raised by `verify_current`, which refuses rather than reporting a
    store as migrated. `MigrationSetEmpty` answers "does this directory
    name any migrations"; this answers "is this store the schema this
    directory describes", and those are not the same failure. An empty
    directory is a path that was never right. A stale store is a schema
    that was right when it was built and is not now, and it is the state
    that surfaces much later as a missing column, inside a caller that
    has no reason to suspect its own schema.

    The comparison is equality in both directions rather than a
    high-water mark, because a mark moves forward and cannot say that a
    file was renamed or withdrawn, and because a subset check cannot see
    a migration the store never applied.
    """


def migration_files(migrations_dir: str | Path) -> list[Path]:
    """The migrations this directory names, or a refusal naming the path.

    An empty glob and a directory that exists but is empty are the same
    list, so the two cannot be told apart by their contents. The cost of
    guessing wrong is a schema that is silently not migrated: the apply
    loop never runs, the caller reports success, and the failure surfaces
    much later as a missing relation. `apply_migrations` is called with a
    path assembled from `Path(__file__).parent.parent` in 31 archived
    tests, and archiving the tree moved those files one level deeper -- so
    the wrong path is a state this repository has actually been in.
    Refuse rather than report an empty success.
    """
    files = sorted(Path(migrations_dir).glob("*.sql"))
    if not files:
        raise MigrationSetEmpty(
            "no migrations found at %r; refusing to report an empty success"
            " for a schema that was never migrated" % (str(migrations_dir),))
    return files


def _currency_gap(recorded: set[str], on_disk: set[str]) -> str:
    """What separates a store from this directory, or "" when nothing does."""
    unapplied = sorted(on_disk - recorded)
    withdrawn = sorted(recorded - on_disk)
    if not unapplied and not withdrawn:
        return ""
    said = []
    if unapplied:
        said.append("this store has not applied %s" % (", ".join(unapplied),))
    if withdrawn:
        said.append("this store records %s, which the directory does not name"
                    % (", ".join(withdrawn),))
    return "; ".join(said)


def verify_current(dsn: str, migrations_dir: str | Path) -> set[str]:
    """The migrations this store holds, or a refusal naming what it lacks.

    The question is asked of committed state over a connection of its own
    and never of what a caller believes it just wrote, so a store whose
    record did not take is one that fails here rather than one that
    reports itself migrated. `apply_migrations` commits each file before
    recording it, so a file that succeeded and a record that followed it
    are separate events and only the second is checked.

    Currency is relative to the directory it is asked against, and that is
    the whole of the difference between a store that means to be partial
    and one that is stale. A caller that means an older schema names an
    older directory, and then the two sides agree. A caller running this
    code against a store built from a directory this tree has since added
    to cannot reach a pass, because the directory it passes is the same
    argument that says which schema it means.
    """
    files = migration_files(migrations_dir)
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM schema_migrations")
            recorded = {row[0] for row in cur.fetchall()}
            conn.commit()
    gap = _currency_gap(recorded, {path.name for path in files})
    if gap:
        raise MigrationSetStale(
            "%s. The directory names %d migrations and the store records %d,"
            " so this store was not migrated from this directory."
            % (gap, len(files), len(recorded)))
    return recorded


def apply_migrations(dsn: str, migrations_dir: str | Path) -> list[str]:
    """Apply what the directory names, then refuse a store that is not it.

    The trailing `verify_current` is the point of the function rather than
    a courtesy. A store that applied its migrations is the one caller
    entitled to say the schema is current, and it can only say so by
    reading the record back. Without the read-back this function's
    return value and the store's actual state are the same claim made
    twice by the same writer, which is why a store left behind by a
    withheld trailing migration has been indistinguishable from a healthy
    one everywhere downstream.
    """
    files = migration_files(migrations_dir)
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
    verify_current(dsn, migrations_dir)
    return applied
