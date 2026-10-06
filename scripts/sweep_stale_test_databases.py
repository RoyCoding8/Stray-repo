#!/usr/bin/env python3
"""Reclaim per-run test databases that a killed pytest run left behind.

``tests/conftest_isolation.py`` drops exactly the databases it created, which
is the only rule that keeps one run from destroying another's work. The cost of
that rule is that a run killed with a signal it cannot handle -- SIGKILL, a
``timeout`` escalation, a ``pkill`` -- never reaches teardown and leaves its
whole set behind. This is the same sweep ``pytest_configure`` performs, with
no pytest session around it, for the case where nobody is about to start one.

Safety does not rest on the age bound. A database is dropped only if its name
carries a run token that no live process holds a lock on; the bound decides
which abandoned databases are worth re-examining, never whether a live one may
be dropped. ``--dry-run`` reports the plan without touching the server.

    PYTHONPATH=.:src python scripts/sweep_stale_test_databases.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterable
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest_isolation import (  # noqa: E402
    STALE_AFTER,
    StaleDatabase,
    _admin_connection,
    _token_locked,
    stale_plan,
)


class LivenessUnavailable(RuntimeError):
    """The server could not be asked whether a run is still alive.

    Distinct from "the run is not alive", which is an answer. This is the
    absence of one, and the two must not be conflated: a caller that cannot
    distinguish them either leaks a database forever or, worse, reads an
    unanswered question as permission.
    """


def _cluster_probe(admin_dsn: str) -> Callable[[str], bool]:
    """Answer "is this token locked?" against the cluster, or decline to.

    Every failure mode here -- no server, no permission to read ``pg_locks``,
    a connection lost mid-query -- becomes a refusal to answer rather than a
    silent ``False``. ``False`` is a claim that nobody holds the lock, and that
    claim is what authorises a drop.
    """

    def probe(token: str) -> bool:
        try:
            conn = _admin_connection(admin_dsn)
        except Exception as error:
            raise LivenessUnavailable("cannot reach the server: %s" % (error,))
        try:
            return _token_locked(conn, token)
        except Exception as error:
            raise LivenessUnavailable("cannot read the lock table: %s" % (error,))
        finally:
            conn.close()

    return probe


def reclaimable(plan: Iterable[StaleDatabase],
                probe: Callable[[str], bool],
                ) -> tuple[list[StaleDatabase], list[tuple[StaleDatabase, str]]]:
    """Split a stale plan into what may be dropped and what must survive.

    Two signals reach a candidate and they are not peers. The *name grammar* is
    a necessary condition and grants nothing: it says only that a name is
    shaped like a pytest run's, which is a statement about spelling. The
    *lock* is the only thing that can grant permission, because it is the only
    evidence that a run was alive at all. So the lock wins wherever the two can
    be compared, and a candidate the lock cannot speak for survives.

    The grammar is deliberately not allowed to win in the other direction
    either. It is what makes a name a candidate; it is never what makes one
    droppable. That is the whole reason the two can disagree safely: the
    grammar failing to match a live database only costs disk, while the grammar
    matching a database it does not own is the error that destroys a run.
    """
    droppable: list[StaleDatabase] = []
    surviving: list[tuple[StaleDatabase, str]] = []
    for candidate in plan:
        try:
            live = probe(candidate.token)
        except LivenessUnavailable as error:
            surviving.append((candidate, "liveness unavailable: %s" % (error,)))
            continue
        if live:
            surviving.append((candidate, "token %s is locked" % (candidate.token,)))
        else:
            droppable.append(candidate)
    return droppable, surviving


def _drop(admin_dsn: str, name: str) -> None:
    with _admin_connection(admin_dsn) as conn:
        conn.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)'
                     % name.replace('"', '""'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Required, not defaulted. A default named a route the operator never
    # chose, and this tool drops databases: a sweep aimed by a guess is the
    # one place the socket default was most dangerous.
    parser.add_argument("--admin-dsn", required=True,
                        help="conninfo with rights to drop databases")
    parser.add_argument("--older-than-hours", type=float, default=None,
                        help="reclaim databases untouched for this long "
                             "(default %d hours)" % int(STALE_AFTER.total_seconds() // 3600))
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be dropped, drop nothing")
    args = parser.parse_args(argv)

    # ``is None``, not a truth test. Zero is a bound an operator can mean: it
    # is how a caller asks for everything reclaimable now. Reading it as
    # falsy made ``--older-than-hours 0`` silently become the shipped four
    # hours and report an empty plan, which looks like a clean server rather
    # than a sweep that declined to run.
    age = (timedelta(hours=args.older_than_hours)
           if args.older_than_hours is not None else STALE_AFTER)

    plan = stale_plan(args.admin_dsn, age=age)
    droppable, surviving = reclaimable(plan, _cluster_probe(args.admin_dsn))

    if args.dry_run:
        for candidate in droppable:
            print("would drop %s (token %s, last modified %s)"
                  % (candidate.name, candidate.token, candidate.modified))
        for candidate, why in surviving:
            print("keeping %s: %s" % (candidate.name, why))
        return 0

    dropped: list[str] = []
    for candidate in droppable:
        _drop(args.admin_dsn, candidate.name)
        dropped.append(candidate.name)
    for candidate, why in surviving:
        print("keeping %s: %s" % (candidate.name, why))
    print("S09ISO: reclaimed %d abandoned database(s) older than %s"
          % (len(dropped), age))
    if surviving:
        print("S09ISO: %d candidate(s) survived; a database that cannot be "
              "proven abandoned is never dropped" % len(surviving))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
