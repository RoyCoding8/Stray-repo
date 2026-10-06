"""Give a pytest session its own databases instead of the shared ones.

The suite writes to 22 shared ``ec02test_*`` databases named by literals
inside the test files. Two runs on one PostgreSQL instance therefore share a
store, and a shared store is not a slow test. It is a serialization failure or
a deadlock, from two transactions taking the same rows in opposite orders. The
fix is one store per run, not a longer timeout.

The literals are reachable without editing the files. Each one is the
*default* of an ``os.environ.get`` call, so what a test module binds at import
time is already indirect. This module sets those names in the environment
before pytest imports the test modules, which is earlier than any fixture can
run. That is why the entry point is ``pytest_configure`` and not an autouse
fixture. A fixture resolves after collection, and collection is what imports
the modules that capture the value.

A default is a seam on the strength of its carrying a ``dbname`` field, not on
its name carrying a prefix. A test database does not have to be spelled
``ec02test_*`` to be shared: ``inv_r3_export`` was a module-level literal in an
``os.environ.get`` default like any other, and the scan missed it because it
screened on the prefix instead. Every ``dbname`` default is now a candidate.

The scan reaches ``_heavy_archived`` too. It used to ``glob`` the top level
only, so the twenty-five defaults under that directory were invisible to it and
each one bound a shared socket database on any host that has a socket. Nothing
about a file's location makes its default a different kind of seam.

A default supplies a ``dbname`` and nothing else. :meth:`SuitePlan.env_for`
builds the connection fields from :func:`admin_dsn` -- the route this session
reached its server over -- because the default is a fallback carrying whatever
its author wrote, and a redirected seam that inherited it would point at a path
that exists only where that author worked.

No seam in the real suite is pinned, which is the outcome the mechanism was
built to reach. :class:`Seam` records the reason and :meth:`SuitePlan.env_for`
refuses to build a DSN for one, so a future pin is reported rather than quietly
falling back to the shared database.

A default named ``*_unused`` or ``*_missing`` is an input to a test that
asserts a refusal. Creating the database would invert that test, so it is
classified ``absent-by-design`` and never redirected. No file in the suite
currently has such a default; the rule covers the case where one is added.
"""

from __future__ import annotations

import ast
import os
import re
import secrets
import signal
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Callable, Iterator

from experiments.ad01.s09_run_isolation import DisposableDatabase
from experiments.ad01.s09_run_isolation import MissingRouteError

TESTS_DIR = Path(__file__).resolve().parent
MIGRATIONS = TESTS_DIR.parent / "migrations"

RUN_PREFIX = "s09iso"
TOKEN_RE = re.compile(r"\A[0-9a-f]{8}\Z")

SHARED_PREFIX = "ec02test_"
FORBIDDEN = frozenset({"ec02test_live"})

ABSENT_SUFFIXES = ("_unused", "_missing")

DISABLE_ENV = "S09ISO_DISABLE"
TOKEN_ENV = "S09ISO_TOKEN"
ADMIN_ENV = "S09ISO_ADMIN_DSN"
SCAN_DIR_ENV = "S09ISO_SCAN_DIR"

DSN_ENV = "SETTLEMENT_TEST_DSN"
TRUNCATE_DSN_ENV = "SETTLEMENT_TEST_TRUNCATE_DSN"

# ``tests/test_s09_durable_state.py`` refuses at import unless the resolved
# ``dbname`` starts with this, and a ``pytest.fail`` during collection aborts
# the whole session rather than failing one file. The name is a safety
# property, not a label: it is how the file proves it is not pointed at a
# shared or live database. So the per-run store has to carry it, or the only
# ways to collect the file are to skip it (invisible) or to leave the
# variables unset, which is the N-415 skip this replaced.
REQUIRED_DB_PREFIX = "s09_durstate"

REDIRECTABLE = "redirectable"
PINNED = "pinned"
ABSENT = "absent-by-design"


def admin_dsn() -> str:
    """The route this session reaches its server over, or a refusal.

    The two spellings of the route (``S09ISO_ADMIN_DSN`` and
    ``SETTLEMENT_TEST_DSN``) are read here and nowhere else, so the route is
    named once rather than carried by each file. There is deliberately no
    local default: a default names a route the caller never chose, and the
    socket this used to fall back to exists only where the author worked.
    A caller that must not connect when no route is named catches
    :class:`MissingRouteError` and skips; a caller that intends to connect
    lets the refusal surface.
    """
    route = os.environ.get(ADMIN_ENV, "") or os.environ.get(DSN_ENV, "")
    if not route:
        raise MissingRouteError(
            "no route to a PostgreSQL server: set SETTLEMENT_TEST_DSN"
            " (conninfo, e.g. 'dbname=postgres host=127.0.0.1"
            " port=5432 user=postgres')")
    return route


def admin_dsn_or_empty() -> str:
    """The same route, but empty when none is named rather than refusing.

    The shape a caller that has not decided to connect yet needs: the plan
    computes before it touches the server, so it records "no route" as the
    empty string and the session gate decides what that means.
    """
    return os.environ.get(ADMIN_ENV, "") or os.environ.get(DSN_ENV, "")


def admin_url(dbname: str) -> str:
    """The same route in URL form, naming ``dbname``.

    Batteries that hand a URL to code which will not take keyword/value
    conninfo need the second spelling, and both spellings are built from
    :func:`admin_dsn` so they cannot disagree about where the server is.
    """
    from urllib.parse import urlencode

    from psycopg.conninfo import conninfo_to_dict

    params = {k: v for k, v in conninfo_to_dict(admin_dsn()).items()
              if k != "password"}
    params["dbname"] = dbname
    return "postgresql:///?%s" % urlencode(params)


def dbname_of(dsn: str) -> str:
    """The ``dbname`` field of a libpq conninfo string."""
    for field_ in dsn.split():
        if field_.startswith("dbname="):
            return field_.split("=", 1)[1]
    raise ValueError("conninfo carries no dbname: %r" % (dsn,))


def dsn_with_dbname(template: str, name: str) -> str:
    """The template with only its ``dbname`` replaced."""
    kept = [f for f in template.split() if not f.startswith("dbname=")]
    return " ".join(kept + ["dbname=%s" % name])


def run_token() -> str:
    """This run's token, or the one a caller pinned to keep a test honest."""
    pinned = os.environ.get(TOKEN_ENV, "")
    if pinned:
        if not TOKEN_RE.match(pinned):
            raise ValueError("%s must be 8 lowercase hex digits, got %r"
                             % (TOKEN_ENV, pinned))
        return pinned
    return secrets.token_hex(4)


def derived_name(token: str, original: str = "") -> str:
    """A per-run database name, carrying the original name when there is room.

    The original suffix is kept because two test files assert the resolved
    ``dbname`` *contains* it. Dropping the suffix would break an assertion
    about isolation, which is the one thing that must keep working. Where the
    assertion is an equality the suffix is useless and the seam is reported as
    pinned instead.
    """
    if not TOKEN_RE.match(token):
        raise ValueError("run token must be 8 lowercase hex digits, got %r"
                         % (token,))
    if not original:
        return "%s_%s" % (RUN_PREFIX, token)
    suffix = original
    if original.startswith(SHARED_PREFIX):
        suffix = original[len(SHARED_PREFIX):]
    budget = 63 - len(RUN_PREFIX) - len(token) - 2
    if len(suffix) > budget:
        raise ValueError("no room in a 63-byte identifier for %r" % (original,))
    return "%s_%s_%s" % (RUN_PREFIX, token, suffix)


@dataclass(frozen=True)
class Seam:
    """One ``os.environ.get`` default that names a database."""

    env_var: str
    default_dsn: str
    db_name: str
    source: str
    mode: str
    reason: str

    @property
    def redirectable(self) -> bool:
        return self.mode == REDIRECTABLE


@dataclass
class SuitePlan:
    """What a session would do, computed before it touches the server."""

    token: str
    seams: list[Seam] = field(default_factory=list)
    # The empty string is "no route named", a state the plan records rather
    # than one it repairs with a guessed default. `IsolatedSuite._admin`
    # refuses on it, so a plan that never starts a suite never connects.
    admin_dsn: str = ""

    @property
    def redirectable(self) -> list[Seam]:
        return [s for s in self.seams if s.redirectable]

    @property
    def blocked(self) -> list[Seam]:
        return [s for s in self.seams if s.mode == PINNED]

    @property
    def absent_by_design(self) -> list[Seam]:
        return [s for s in self.seams if s.mode == ABSENT]

    def env_for(self, seam: Seam) -> str:
        """The value to put in the environment for a redirectable seam.

        The connection fields are taken from the route this session actually
        reached its server over, not from the seam's own default. A default is
        an ``os.environ.get`` fallback and carries whatever the file's author
        wrote, which on any host without that socket names a path that does not
        exist. Reading the route from the default would make every redirected
        seam inherit an unreachable socket, so the default supplies the
        ``dbname`` and nothing else.
        """
        if not seam.redirectable:
            raise ValueError("%s is %s: %s" % (seam.env_var, seam.mode, seam.reason))
        # The plan's own route, not a fresh read of the environment. A plan
        # with no route builds a dbname-only value: the plugin never starts a
        # suite on such a plan (the configure gate steps aside), so this
        # value names the database and inherits no route it did not earn.
        return dsn_with_dbname(self.admin_dsn or "",
                              derived_name(self.token, seam.db_name))


def _literals_in(node: ast.AST) -> list[str]:
    """Every string literal reachable in one operand of a comparison.

    A set literal on the right of ``in`` is a ``Set`` node holding
    ``Constant`` children, not a single ``Constant``, so walking the operand
    rather than testing it is what finds ``dbname in {"a", "b"}``.
    """
    return [n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _pin_kind(tree: ast.AST, db_name: str) -> tuple[bool, str]:
    """Whether ``db_name`` appears in an ``==`` or ``in`` assertion, and how.

    Both forms make the file name-dependent, so both block a redirect, and for
    the same underlying reason: neither can hold for a per-run name.
    ``derived_name`` truncates to a fixed-width token, so
    ``s09iso_deadbeef_ec02test_state`` comes back as ``s09iso_deadbeef_state``
    and the original spelling is gone. An ``==`` can therefore never hold, and
    an ``in`` fails for the same reason.

    An earlier version of this docstring claimed the opposite for ``in`` - that
    it "would hold only because the derived name still carries x". That was
    false, and both the lanes that unpinned these seams found it independently
    by reading ``derived_name`` rather than this comment. The failure mode it
    described is real but belongs to a name scheme that embeds the original,
    which this one does not.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(db_name in _literals_in(o)
                   for o in (node.left, *node.comparators)):
            continue
        for op in node.ops:
            if not isinstance(op, (ast.Eq, ast.In)):
                continue
            if isinstance(node.left, ast.Constant) \
                    and node.left.value == db_name:
                return True, ("substring check cannot hold: derived_name "
                              "drops %r from the per-run name" % (db_name,))
            return True, "requires dbname to equal %r" % (db_name,)
    return False, ""


def _classify(db_name: str, tree: ast.AST) -> tuple[str, str]:
    if db_name in FORBIDDEN:
        return PINNED, "%s is never a test target" % (db_name,)
    if db_name.endswith(ABSENT_SUFFIXES):
        return ABSENT, ("a refusal input, expected never to exist;"
                        " creating it would invert the test")
    pinned, why = _pin_kind(tree, db_name)
    if pinned:
        return PINNED, why
    return REDIRECTABLE, "no assertion pins this name"


def scan(directory: Path | None = None) -> list[Seam]:
    """Every redirectable-looking ``os.environ.get`` database default on disk.

    This parses the test sources rather than importing them, because importing
    a test module is what captures the value being replaced.
    """
    root = directory or TESTS_DIR
    found: dict[str, Seam] = {}
    for path in sorted(root.rglob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "get"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "environ"):
                continue
            if len(node.args) < 2 or not isinstance(node.args[0], ast.Constant):
                continue
            env_var = node.args[0].value
            if not isinstance(env_var, str) or not env_var.isupper():
                continue
            try:
                default = ast.literal_eval(node.args[1])
            except (ValueError, TypeError):
                continue
            if not isinstance(default, str):
                continue
            try:
                db_name = dbname_of(default)
            except ValueError:
                continue
            mode, reason = _classify(db_name, tree)
            seam = Seam(env_var=env_var, default_dsn=default,
                        db_name=db_name, source=path.name,
                        mode=mode, reason=reason)
            previous = found.get(env_var)
            if previous is None:
                found[env_var] = seam
                continue
            found[env_var] = _merge(previous, seam)
    return [found[k] for k in sorted(found)]


def _merge(left: Seam, right: Seam) -> Seam:
    """Combine two files that read the same variable.

    ``EC02_AD01C_DSN`` is read by four files. Redirecting it moves all four at
    once, so a name pinned by any one of them pins it for every one. Merging
    to the more restrictive mode keeps that true, and records both sources so
    the reader can see why.
    """
    if left.mode == right.mode and left.db_name == right.db_name:
        return Seam(env_var=left.env_var, default_dsn=left.default_dsn,
                    db_name=left.db_name,
                    source="%s,%s" % (left.source, right.source),
                    mode=left.mode, reason=left.reason)
    return Seam(env_var=left.env_var, default_dsn=left.default_dsn,
                db_name=left.db_name,
                source="%s,%s" % (left.source, right.source),
                mode=PINNED,
                reason="%s pins this name and %s shares the variable"
                       % (left.source, right.source))


def plan(token: str | None = None, directory: Path | None = None) -> SuitePlan:
    """Decide every redirection, without connecting to anything."""
    admin = admin_dsn_or_empty()
    if directory is None:
        scanned = os.environ.get(SCAN_DIR_ENV, "")
        if scanned:
            directory = Path(scanned)
    return SuitePlan(token=token or run_token(), seams=scan(directory),
                     admin_dsn=admin)


def apply_environment(plan_: SuitePlan) -> dict[str, str]:
    """Set the redirectable seams in this process, returning what was set."""
    applied: dict[str, str] = {}
    for seam in plan_.redirectable:
        value = plan_.env_for(seam)
        os.environ[seam.env_var] = value
        applied[seam.env_var] = value
    return applied


# A live run holds one advisory lock per token, for its whole life, on a
# dedicated connection. The namespace occupies the high 32 bits of the
# bigint key so it cannot collide with a caller that packs a name into the low
# 32 bits, such as ``hashtext`` in ``experiments/coord02/experience.py``.
LOCK_NAMESPACE = 0x5


def lock_key(token: str) -> int:
    """The advisory-lock key a run holds for ``token``."""
    if not TOKEN_RE.match(token):
        raise ValueError("run token must match %s, got %r" % (TOKEN_RE.pattern, token))
    return (LOCK_NAMESPACE << 32) | int(token, 16)


# A run is not abandoned because it is old. It is abandoned because no
# process holds its token lock. The age bound exists only to keep the sweep
# from spending a session re-examining databases this run itself created, and
# to bound the damage if lock bookkeeping ever fails. It is deliberately far
# above any run this suite takes, because the only way being wrong here is
# dropping a live run's stores: measured spans across the 33 leaked tokens on
# this box reached 427 minutes for a token that was still working, and
# ``tests/test_s09_swe_experiment.py`` alone runs 57 tests that spawn real
# subprocess episodes. A bound that is merely large risks a live drop; a bound
# that is only plausible risks leaking again. Four hours is the first value
# that is neither.
STALE_AFTER = timedelta(hours=4)

SWEEP_ENV = "S09ISO_SWEEP"
SWEEP_AGE_ENV = "S09ISO_SWEEP_AGE_HOURS"
DISABLE_SWEEP_ENV = "S09ISO_DISABLE_SWEEP"

# The shape this module creates. A name that is not this shape was made by
# something else that merely shares the prefix -- ``experiments/ad01`` builds
# ``s09iso_<token>_<uuid12>`` from its own token grammar -- and guessing at
# another component's liveness is exactly the error that destroys a run.
DERIVED_NAME_RE = re.compile(r"\As09iso_([0-9a-f]{8})_[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def derived_token(name: str) -> str | None:
    """The token embedded in a per-run name, or None if this is not one."""
    match = DERIVED_NAME_RE.match(name)
    return match.group(1) if match else None


# ``classid``/``objid`` are what a single-bigint ``pg_advisory_lock`` occupies
# in ``pg_locks``; ``objsubid = 1`` is the marker separating the one-bigint
# form from the two-int form. The token is a 32-bit value, so it is compared
# as an ``oid``. Locks are cluster-wide, so this sees a holder in any
# database, which is what makes it a liveness test rather than a local one.
LOCKED_TOKEN_SQL = """
select 1
  from pg_locks
 where locktype = 'advisory'
   and classid = %(namespace)s
   and objsubid = 1
   and objid = ('x' || %(token)s)::bit(32)::bigint::oid
"""


def _admin_connection(admin_dsn: str):
    import psycopg

    return psycopg.connect(admin_dsn, autocommit=True)


def _latest_modification(admin_dsn: str) -> dict[str, datetime]:
    """``name -> last modification time`` for every database on the server.

    Read from the filesystem rather than trusted from ``pg_database``:
    ``pg_database`` has no creation column, and a name the harness derives is
    not otherwise recoverable from the catalog once the run is gone.
    """
    with _admin_connection(admin_dsn) as conn:
        rows = conn.execute(
            "select datname, (pg_stat_file('base/' || oid)).modification "
            "from pg_database order by datname").fetchall()
    return {name: modified for name, modified in rows if name and modified}


def _locked_tokens(admin_dsn: str) -> set[str]:
    """Tokens some live process currently holds a lock for."""
    locked: set[str] = set()
    with _admin_connection(admin_dsn) as conn:
        for (name,) in conn.execute("select datname from pg_database "
                                    "order by datname"):
            token = derived_token(name)
            if token is None or token in locked:
                continue
            if _token_locked(conn, token):
                locked.add(token)
    return locked


def _token_locked(conn, token: str) -> bool:
    """Whether any backend on the cluster holds ``token``'s advisory lock."""
    return bool(conn.execute(LOCKED_TOKEN_SQL,
                             {"namespace": LOCK_NAMESPACE,
                              "token": token}).fetchone())


# A killed run leaves two kinds of residue, and only one of them is a database.
# The ready marker is the filesystem half: ``tests/test_s09iso_stale_sweep.py``
# writes one beside a lock-holder child that ends its life in ``time.sleep(600)``
# with no cleanup, so a signal the child cannot handle leaves the file behind.
# A sweep that reclaims the databases and not the marker is half a fix, because
# the marker is what a reviewer sees when they go looking for the leak.
#
# The grammar is the same as a derived database name's, because both are keyed
# by the run token. A file that does not match it was written by something else
# and is not this module's to remove.
MARKER_PREFIX = ".s09iso_ready_"
MARKER_RE = re.compile(r"\A%s[0-9a-f]{8}\Z" % re.escape(MARKER_PREFIX))
MARKER_DIR = TESTS_DIR.parent


def marker_token(name: str) -> str | None:
    """The run token a marker names, or None if this is not one."""
    match = MARKER_RE.match(name)
    return match.group(0)[len(MARKER_PREFIX):] if match else None


def ready_markers(directory: Path, tokens: set[str]) -> list[Path]:
    """Markers in ``directory`` naming one of ``tokens``, sorted by name."""
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir()
                  if path.is_file() and marker_token(path.name) in tokens)


def clear_ready_markers(directory: Path, tokens: set[str], *,
                        probe: Callable[[str], bool] | None = None,
                        ) -> list[str]:
    """Remove markers for ``tokens``, skipping any token a live process holds.

    ``probe`` answers "is this token locked?". It defaults to the same
    cluster-wide advisory-lock test the databases are selected by, and a token
    it reports as locked keeps its marker. That is the whole reason this
    function may not be simpler: a marker is the only on-disk record that a
    run was in flight, so removing a live run's is the filesystem half of
    dropping a live run's database.

    The scope is one directory, by default this repository's root. A sibling
    worktree shares the PostgreSQL instance and therefore the tokens, but its
    markers are its own; a sweep here can only ever remove this tree's files.
    """
    candidates = ready_markers(directory, tokens)
    if not candidates:
        return []
    check = probe
    owned = None
    if check is None:
        owned = _admin_connection(admin_dsn())
        check = lambda t: _token_locked(owned, t)  # noqa: E731
    cleared: list[str] = []
    try:
        for path in candidates:
            token = marker_token(path.name)
            if check(token):
                continue
            path.unlink(missing_ok=True)
            cleared.append(token)
    finally:
        if owned is not None:
            owned.close()
    return cleared


@dataclass(frozen=True)
class StaleDatabase:
    name: str
    token: str
    modified: datetime


def stale_plan(admin_dsn: str, *,
               age: timedelta = STALE_AFTER,
               now: datetime | None = None,
               only: frozenset[str] | None = None,
               ) -> list[StaleDatabase]:
    """Per-run databases no live process owns, older than ``age``.

    The route is a required argument, not a defaulted one: the sweep drops
    databases, and a default would aim it at a server the caller never
    named.

    Selection is name shape, then lock, then age, in that order. The lock test
    comes before the age test so that a live run is refused even if it has
    been running longer than ``age``: age bounds the sweep, it never grants
    permission. A database whose modification time cannot be read is left
    alone, because a name this shape is presumed to be in use until shown
    otherwise.

    ``only`` narrows the sweep to a named set. It exists so a caller acting on
    a single database -- a test, or a one-off repair -- cannot drop the rest
    of the server as a side effect of asking about one name.
    """
    modified = _latest_modification(admin_dsn)
    locked = _locked_tokens(admin_dsn)
    cutoff = (now or datetime.now(timezone.utc)) - age
    plan: list[StaleDatabase] = []
    for name, stamp in modified.items():
        if only is not None and name not in only:
            continue
        token = derived_token(name)
        if token is None or token in locked or stamp >= cutoff:
            continue
        plan.append(StaleDatabase(name=name, token=token, modified=stamp))
    return sorted(plan, key=lambda s: s.name)


def sweep_stale(admin_dsn: str, *,
                age: timedelta = STALE_AFTER,
                dry_run: bool = False,
                only: frozenset[str] | None = None,
                protected: frozenset[str] = FORBIDDEN,
                ) -> list[str]:
    """Drop abandoned per-run databases. Returns what it dropped.

    ``FORBIDDEN`` is re-checked here rather than trusted from the caller: the
    sweep runs unattended, and a name that can never be redirected must not be
    droppable by a sweep of it.

    The same tokens then get their ready markers cleared, so one reclaim takes
    both halves of a killed run's residue. The marker clear runs on the tokens
    this call actually dropped, so a caller that narrowed the sweep with
    ``only`` cannot reach a marker it did not earn, and a dry run removes
    nothing on either side.
    """
    targets = [s for s in stale_plan(admin_dsn, age=age, only=only)
               if s.name not in protected]
    if not dry_run:
        for target in targets:
            with _admin_connection(admin_dsn) as conn:
                conn.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)'
                             % target.name.replace('"', '""'))
        if targets:
            conn = _admin_connection(admin_dsn)
            try:
                clear_ready_markers(MARKER_DIR, {t.token for t in targets},
                                    probe=lambda t: _token_locked(conn, t))
            finally:
                conn.close()
    return [t.name for t in targets]


class RunClaim:
    """A live run's exclusive claim on its own token, held until it exits.

    The databases for a run cannot be reclaimed by age alone, because a run
    that has been going ninety minutes looks exactly like a run that was
    killed an hour ago. What separates them is that the first still has a
    process attached. This holds a PostgreSQL session-level advisory lock on
    a connection of its own for the life of the run; the lock lives in the
    server, so it is visible to a sweeper in any other process, and it is
    released automatically when the connection dies -- including when the
    process is killed with a signal it cannot handle, which is the case the
    startup sweep exists to clean up after.
    """

    def __init__(self, token: str, admin_dsn: str) -> None:
        self.token = token
        self._admin_dsn = admin_dsn
        self._conn = None
        self._previous: dict[int, object] = {}

    def acquire(self) -> "RunClaim":
        conn = _admin_connection(self._admin_dsn)
        conn.execute("select pg_advisory_lock(%s)", (lock_key(self.token),))
        self._conn = conn
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            try:
                self._previous[signum] = signal.signal(signum, self._on_signal)
            except (ValueError, OSError):
                pass
        return self

    def _on_signal(self, signum, frame):
        self.release()
        signal.signal(signum, self._previous[signum])
        os.kill(os.getpid(), signum)

    def release(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "RunClaim":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


class IsolatedSuite:
    """One run's databases, created up front and dropped on teardown.

    The names are held on the instance rather than recomputed from a glob, so
    teardown drops exactly what this run created and cannot reach a database
    another run owns.
    """

    def __init__(self, plan_: SuitePlan) -> None:
        self.plan = plan_
        self.created: list[DisposableDatabase] = []
        self.env_applied: dict[str, str] = {}

    def _admin(self) -> str:
        if not self.plan.admin_dsn:
            raise MissingRouteError(
                "no route to a PostgreSQL server: set SETTLEMENT_TEST_DSN")
        return self.plan.admin_dsn

    def _create(self, name: str) -> DisposableDatabase:
        import psycopg

        from settlement import db as settlement_db

        with psycopg.connect(self._admin(), autocommit=True) as conn:
            conn.execute('CREATE DATABASE "%s"' % name.replace('"', '""'))
        handle = DisposableDatabase(name=name,
                                    dsn=dsn_with_dbname(self._admin(), name),
                                    token=self.plan.token)
        settlement_db.apply_migrations(handle.dsn, MIGRATIONS)
        self.created.append(handle)
        return handle

    def start(self) -> dict[str, str]:
        """Create every redirected store, then point the environment at it."""
        for seam in self.plan.redirectable:
            self._create(dbname_of(self.plan.env_for(seam)))
        self.env_applied = apply_environment(self.plan)
        self.env_applied.update(self._apply_conftest_stores())
        return self.env_applied

    def _apply_conftest_stores(self) -> dict[str, str]:
        """Point conftest's own fixtures at a per-run store.

        `tests/conftest.py` reads `SETTLEMENT_TEST_DSN` and
        `SETTLEMENT_TEST_TRUNCATE_DSN`, and its `_dsn()` calls
        `pytest.skip` when the first is unset. Those two names are not
        scanned seams, so before this existed nothing set them and every
        test using the `migrated_db` fixture skipped on a bare `pytest`
        invocation. A skip is not a failure, so 101 files reported
        without running. N-415.

        The same store serves both variables because `migrated_db`
        refuses to truncate unless they are equal, and a test that
        migrated a store is entitled to truncate it.

        The store is named for ``REQUIRED_DB_PREFIX`` rather than
        ``settlement`` so ``test_s09_durable_state.py`` collects instead of
        failing the session. Naming it ``settlement`` made that file's
        ``pytest.fail`` fire at import, which is a collection error and
        stops every other file too -- so the run below reported one error
        and zero results rather than a red file.
        """
        name = derived_name(self.plan.token, REQUIRED_DB_PREFIX)
        handle = self._create(name)
        dsn = handle.dsn
        applied = {DSN_ENV: dsn, TRUNCATE_DSN_ENV: dsn}
        for var, value in applied.items():
            os.environ[var] = value
        return applied

    def stop(self) -> list[str]:
        """Drop this run's databases. Never raises on a database that is gone."""
        from experiments.ad01.s09_run_isolation import drop_disposable_db

        dropped: list[str] = []
        while self.created:
            handle = self.created.pop()
            try:
                drop_disposable_db(handle, admin_dsn=self._admin())
            except Exception as error:  # a teardown must not mask a real failure
                print("S09ISO: could not drop %s: %s" % (handle.name, error))
                continue
            dropped.append(handle.name)
        return dropped


def pytest_configure(config) -> None:
    """Claim this run's token, reclaim what was abandoned, then create.

    A session with no route named (``SETTLEMENT_TEST_DSN`` empty) has no
    database to isolate toward, so the plugin steps aside entirely rather
    than dying at configure: it seeds nothing, and every test that needs a
    database refuses or skips on its own missing route. The route was a
    guessed socket default until this gate existed, which is what made a
    routeless runner error 554 lines instead of skipping.
    """
    if os.environ.get(DISABLE_ENV):
        return
    if not admin_dsn_or_empty():
        return
    suite = IsolatedSuite(plan())
    config._s09iso_suite = suite
    claim = RunClaim(suite.plan.token, suite.plan.admin_dsn).acquire()
    config._s09iso_claim = claim
    try:
        _startup_sweep(config, suite.plan)
        suite.start()
    except Exception:
        suite.stop()
        claim.release()
        raise
    config._s09iso_plan = suite.plan
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep("=", "S09ISO run isolation")
        for line in describe(suite.plan):
            reporter.write_line(line)


def _startup_sweep(config, plan_: SuitePlan) -> None:
    """Reclaim databases left by runs that were killed, before creating any.

    This runs before ``suite.start()`` so that this run's own databases, which
    are minutes old and locked, are never even candidates. A sweep that failed
    is reported and skipped: leaving a database behind costs disk, while a
    wrong drop costs another lane its work.
    """
    if os.environ.get(DISABLE_SWEEP_ENV):
        return
    age = STALE_AFTER
    override = os.environ.get(SWEEP_AGE_ENV, "")
    if override:
        try:
            age = timedelta(hours=float(override))
        except ValueError:
            pass
    dry = bool(os.environ.get(SWEEP_ENV))
    try:
        names = sweep_stale(plan_.admin_dsn, age=age, dry_run=dry)
    except Exception as error:
        print("S09ISO: stale sweep skipped: %s" % (error,))
        return
    if not names:
        return
    verb = "would drop" if dry else "reclaimed"
    print("S09ISO: %s %d abandoned database(s) older than %s"
          % (verb, len(names), age))
    config._s09iso_swept = names


def pytest_unconfigure(config) -> None:
    claim = getattr(config, "_s09iso_claim", None)
    suite = getattr(config, "_s09iso_suite", None)
    try:
        if suite is not None:
            dropped = suite.stop()
            if dropped:
                print("S09ISO: dropped %d database(s) for this run" % len(dropped))
    finally:
        if claim is not None:
            claim.release()


def describe(plan_: SuitePlan) -> Iterator[str]:
    """A record of the run: what was isolated, and what stayed shared."""
    yield "run token: %s" % plan_.token
    yield "redirected: %d of %d seams" % (len(plan_.redirectable), len(plan_.seams))
    for seam in plan_.redirectable:
        yield "  %-26s %-24s -> %s" % (seam.env_var, seam.db_name,
                                      dbname_of(plan_.env_for(seam)))
    for seam in plan_.blocked:
        yield "  BLOCKED %-21s %-24s %s" % (seam.env_var, seam.db_name, seam.reason)
    for seam in plan_.absent_by_design:
        yield "  absent  %-21s %-24s %s" % (seam.env_var, seam.db_name, seam.reason)
