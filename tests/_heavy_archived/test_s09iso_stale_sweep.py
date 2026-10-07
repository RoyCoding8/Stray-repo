"""The sweep must reclaim a killed run's databases and nothing else.

A run killed with a signal it cannot handle never reaches
``pytest_unconfigure``, so the databases it created outlive it. The harness
answers that with an advisory lock per run token: a live run holds its token
locked for as long as it lives, and a sweeper in any other process sees that
lock cluster-wide. Reclamation is therefore a liveness test, and the age bound
is only a filter on which abandoned databases are worth re-examining.

Everything here acts on a real server with real processes and real SIGKILL,
because the property under test is precisely whether a signal-killed process
leaves server-side state behind. A mock would assert nothing about that.

Two constraints shaped the design of this file. The PostgreSQL on this box is
shared with other lanes, and the data directory is not writable, so a test
cannot age a database by touching it. Every mutating call therefore passes
``only``, which restricts the sweep to names this module minted. A test that
asked "what is stale?" without that filter would, on a box carrying 550 leaked
databases, answer by dropping all of them -- so the tests exercise the age
predicate by passing the bound as a parameter, and never by aging anything.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tests.conftest_isolation as iso  # noqa: E402

from tests.conftest_isolation import (  # noqa: E402
    FORBIDDEN,
    LOCK_NAMESPACE,
    STALE_AFTER,
    RunClaim,
    derived_token,
    lock_key,
    stale_plan,
    sweep_stale,
)

REPO = Path(__file__).resolve().parents[2]
VENV_PYTHON = Path(sys.executable)
HOLDER_SCRIPT = REPO / ".s09iso_sweep_holder.py"

pytestmark = pytest.mark.skipif(
    not os.environ.get("SETTLEMENT_TEST_DSN"),
    reason="needs a live PostgreSQL; run under the isolation harness",
)


# --------------------------------------------------------------------------
# Server helpers. Each opens its own short connection; nothing is held across
# a test boundary except the RunClaim the test is deliberately exercising.
# --------------------------------------------------------------------------

def _connect():
    import psycopg

    return psycopg.connect(iso.admin_dsn(), autocommit=True)


def _create(name: str) -> None:
    with _connect() as conn:
        conn.execute('CREATE DATABASE "%s"' % name)


def _drop(name: str) -> None:
    with _connect() as conn:
        conn.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % name)


def _exists(name: str) -> bool:
    with _connect() as conn:
        return bool(conn.execute(
            "select 1 from pg_database where datname = %s", (name,)).fetchone())


def _names() -> set[str]:
    with _connect() as conn:
        return {row[0] for row in conn.execute("select datname from pg_database")}


def _namespace_locks() -> int:
    with _connect() as conn:
        return conn.execute(
            "select count(*) from pg_locks "
            "where locktype = 'advisory' and classid = %s",
            (LOCK_NAMESPACE,)).fetchone()[0]


def _token_is_locked(token: str) -> bool:
    with _connect() as conn:
        return bool(conn.execute(
            "select 1 from pg_locks where locktype = 'advisory' "
            "and classid = %s and objsubid = 1 "
            "and objid = ('x' || %s)::bit(32)::bigint::oid",
            (LOCK_NAMESPACE, token)).fetchone())


def _wait_for(predicate, seconds: float = 30.0, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _name_for(token: str, tag: str) -> str:
    return "s09iso_%s_%s" % (token, tag)


def _write_holder_script() -> None:
    # The child removes its own marker when it is asked to stop. It exists to
    # be killed with a signal it cannot handle, so a cleanup in the parent never
    # runs on the SIGKILL path and the marker outlived the run that wrote it.
    # A ``finally`` is not enough: ``RunClaim.acquire`` installs its own
    # SIGTERM/SIGINT/SIGHUP handler that re-raises the signal after releasing
    # the lock, so the interpreter dies at the signal and never unwinds. The
    # unlink has to be in that handler, ahead of the re-raise, which means
    # chaining onto RunClaim's rather than replacing it.
    #
    # SIGKILL is still unhandled and still leaves the marker. That path is
    # covered by the sweep's own clear: the marker's token is the one the
    # sweep already proved unlocked, so a killed child's marker is reclaimed by
    # name like any other dead run's.
    HOLDER_SCRIPT.write_text(
        "import os, signal, sys, time\n"
        "sys.path.insert(0, %r)\n"
        "from tests.conftest_isolation import RunClaim, admin_dsn\n"
        "marker = sys.argv[2]\n"
        "claim = RunClaim(sys.argv[1], admin_dsn()).acquire()\n"
        "previous = {}\n"
        "for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):\n"
        "    previous[signum] = signal.getsignal(signum)\n"
        "def _cleanup_then_chain(signum, frame):\n"
        "    try:\n"
        "        os.unlink(marker)\n"
        "    except OSError:\n"
        "        pass\n"
        "    signal.signal(signum, previous[signum])\n"
        "    claim._on_signal(signum, frame)\n"
        "for signum in previous:\n"
        "    signal.signal(signum, _cleanup_then_chain)\n"
        "open(marker, 'w').write('held')\n"
        "time.sleep(600)\n" % str(REPO),
        encoding="utf-8")


def _spawn_holder(token: str):
    """A separate process holding ``token``'s lock, returned once it is held."""
    _write_holder_script()
    ready = REPO / (".s09iso_ready_%s" % token)
    ready.unlink(missing_ok=True)
    child = subprocess.Popen([str(VENV_PYTHON), str(HOLDER_SCRIPT), token, str(ready)])
    if not _wait_for(lambda: _token_is_locked(token), seconds=60):
        child.kill()
        child.wait(timeout=30)
        raise AssertionError("the lock holder never took a visible lock")
    return child


def _kill(child) -> None:
    child.kill()
    child.wait(timeout=30)


# --------------------------------------------------------------------------
# Name shape: the sweep may only consider names this module created.
# --------------------------------------------------------------------------

def test_a_derived_name_yields_its_token():
    assert derived_token("s09iso_79eec8f3_verif") == "79eec8f3"
    assert derived_token("s09iso_79eec8f3_s09_durstate") == "79eec8f3"


def test_a_foreign_name_sharing_the_prefix_is_not_a_candidate():
    # ``experiments/ad01`` builds ``s09iso_<its token>_<uuid12>`` under a
    # different token grammar. Its token is not one this module locks, so
    # treating it as reclaimable would mean guessing at another component's
    # liveness from a name shape we do not own.
    assert derived_token("s09iso_c23eval_f3ae73582f28") is None
    assert derived_token("s09iso_o-pilot_d66db0dfcfce") is None
    assert derived_token("s09iso_o-pilot_d66db0dfcfce_extra") is None


def test_a_non_isolated_database_is_never_a_candidate():
    for name in ("ec02test_live", "postgres", "settlement", "s09iso", "s09iso_"):
        assert derived_token(name) is None, name
    assert "ec02test_live" in FORBIDDEN


def test_the_lock_namespace_cannot_collide_with_a_low_bit_caller():
    # ``experiments/coord02/experience.py`` locks ``hashtext(name)``, which
    # occupies only the low 32 bits. This namespace is in the high 32, so the
    # two can never be the same key.
    assert lock_key("00000000") >> 32 == LOCK_NAMESPACE
    assert (lock_key("ffffffff") >> 32) == LOCK_NAMESPACE
    assert lock_key("ffffffff") & 0xFFFFFFFF == 0xFFFFFFFF


# --------------------------------------------------------------------------
# The lock is what makes a live run safe, and it survives no process.
# --------------------------------------------------------------------------

def test_a_held_lock_is_visible_to_another_backend():
    token = "a11ce001"
    child = _spawn_holder(token)
    try:
        assert _token_is_locked(token), (
            "the lock is not visible from another backend, so a sweeper "
            "cannot tell a live run from a dead one")
    finally:
        _kill(child)


def test_sigkill_releases_the_lock_so_a_killed_run_counts_as_abandoned():
    """A signal-killed run must become reclaimable. This is the whole leak."""
    token = "a11ce002"
    child = _spawn_holder(token)
    _kill(child)                                     # SIGKILL: no cleanup runs
    assert _wait_for(lambda: not _token_is_locked(token), seconds=30), (
        "the lock survived SIGKILL of its holder, so a killed run would look "
        "live forever and its databases would leak permanently")


def test_a_live_run_is_excluded_even_when_its_database_passes_the_age_bound():
    """The age bound is a filter, not a permission: the lock outranks it."""
    token = "a11ce003"
    name = _name_for(token, "oldbutlive")
    _create(name)
    child = _spawn_holder(token)
    try:
        offered = {s.name for s in stale_plan(
            iso.admin_dsn(), age=timedelta(seconds=0), only=frozenset({name}))}
        assert name not in offered, (
            "a database belonging to a live run was offered for dropping "
            "because it passed the age bound; age must never override a lock")
    finally:
        _kill(child)
        _drop(name)


def test_a_claim_in_this_process_protects_its_own_database():
    token = "a11ce004"
    name = _name_for(token, "claimed")
    _create(name)
    try:
        with RunClaim(token, iso.admin_dsn()):
            assert _token_is_locked(token)
            dropped = sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                                  only=frozenset({name}))
        assert dropped == [], (
            "the sweep dropped a database whose run was demonstrably live")
        assert _exists(name)
    finally:
        _drop(name)


# --------------------------------------------------------------------------
# Selectivity. The negative case matters more than the positive one: a sweep
# that cannot be shown to *decline* is the dangerous kind.
# --------------------------------------------------------------------------

def test_red_the_database_survives_when_the_reclaim_condition_is_false():
    """RED half of the red-before-green pair.

    The reclaim condition is forced false -- the age bound is set to a decade,
    which nothing can be older than -- and the database must survive. If this
    failed, the sweep would be dropping databases on grounds other than
    staleness, which is the failure mode that destroys a live run.
    """
    name = _name_for("a11ce0f0", "selneg")
    _create(name)
    try:
        plan = stale_plan(iso.admin_dsn(), age=timedelta(days=3650),
                          only=frozenset({name}))
        assert plan == [], (
            "a ten-year-old bound still offered this database, so the "
            "condition being false is not actually being honoured")
        assert sweep_stale(iso.admin_dsn(), age=timedelta(days=3650),
                           only=frozenset({name})) == []
        assert _exists(name), "the database was dropped with the condition false"
    finally:
        _drop(name)


def test_green_the_same_database_is_dropped_once_the_condition_is_restored():
    """GREEN half. Same database, same sweep, condition restored."""
    name = _name_for("a11ce0f0", "selneg")
    _create(name)
    try:
        dropped = sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                              only=frozenset({name}))
        assert dropped == [name], (
            "an abandoned database past the age bound was not reclaimed")
        assert not _exists(name)
    finally:
        _drop(name)


def test_the_sweep_never_offers_a_protected_or_foreign_database():
    offered = {s.name for s in stale_plan(
        iso.admin_dsn(), age=timedelta(seconds=0))}
    for name in ("ec02test_live", "postgres", "settlement",
                 "s09iso_c23eval_f3ae73582f28", "s09iso_o-pilot_d66db0dfcfce"):
        assert name not in offered, (
            "%s was offered for dropping; the sweep must not reach outside "
            "the names this module creates" % name)


def test_a_protected_name_is_refused_even_if_it_looked_like_a_candidate():
    """FORBIDDEN is enforced at the drop, not only by the name predicate."""
    name = _name_for("a11ce0f1", "shielded")
    _create(name)
    try:
        dropped = sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                              only=frozenset({name}),
                              protected=frozenset({name}))
        assert dropped == [] and _exists(name), (
            "a caller-supplied protected name was dropped anyway")
    finally:
        _drop(name)


def test_a_dry_run_reports_without_dropping():
    name = _name_for("a11ce0f2", "dryrun")
    _create(name)
    try:
        assert sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                           only=frozenset({name}), dry_run=True) == [name]
        assert _exists(name), "a dry run dropped a database"
    finally:
        _drop(name)


def test_only_narrows_the_sweep_to_the_named_set():
    """A single-name query must not act on everything else on the server."""
    name = _name_for("a11ce0f3", "narrow")
    other = _name_for("a11ce0f4", "untouched")
    _create(name)
    _create(other)
    try:
        dropped = sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                              only=frozenset({name}), dry_run=True)
        assert dropped == [name]
        assert _exists(other), "a narrowed sweep still reached another database"
    finally:
        _drop(name)
        _drop(other)


def test_the_shipped_bound_is_four_hours_and_something():
    """The bound is part of the contract, and it is stated in hours on purpose.

    Four hours is above every run this suite is known to take: the longest
    span measured across the leaked tokens on this box was 427 minutes for a
    token that was still working, and ``tests/test_s09_swe_experiment.py`` runs
    57 tests that spawn real subprocess episodes.
    """
    assert STALE_AFTER == timedelta(hours=4)


# --------------------------------------------------------------------------
# The leak itself, produced the way it actually happened: a real pytest
# process killed with a real signal, leaving a real database behind.
# --------------------------------------------------------------------------

def test_a_sigkilled_pytest_run_leaves_a_database_the_next_run_reclaims():
    """End to end: kill a real pytest session, then let a later sweep reclaim.

    The victim is given a *pinned* token and isolation disabled, so the test
    observes the raw leak -- a session that dies without teardown -- rather
    than the harness already cleaning up after itself.
    """
    token = "a11ce005"
    name = _name_for(token, "e2e")
    victim = REPO / ".s09iso_sweep_victim"
    shutil.rmtree(victim, ignore_errors=True)
    victim.mkdir(parents=True)
    (victim / "test_killed.py").write_text(
        "import os\n"
        "import psycopg\n"
        "from tests.conftest_isolation import admin_dsn\n"
        "def test_creates_a_database():\n"
        "    with psycopg.connect(admin_dsn(), autocommit=True) as conn:\n"
        "        conn.execute('CREATE DATABASE \"%s\"' % os.environ['S09ISO_VICTIM_DB'])\n",
        encoding="utf-8")

    env = dict(os.environ)
    env.update({"S09ISO_VICTIM_DB": name, "S09ISO_TOKEN": token,
                "S09ISO_DISABLE": "1", "PYTHONPATH": ".:src",
                "S09ISO_DISABLE_SWEEP": "1"})
    proc = None
    try:
        proc = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "pytest",
             str(victim / "test_killed.py"), "-q", "-p", "no:cacheprovider"],
            cwd=str(REPO), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        if not _wait_for(lambda: _exists(name), seconds=120):
            proc.kill()
            output = proc.communicate(timeout=30)[0]
            raise AssertionError(
                "the victim never created its database (exit %s), so the rest "
                "of this test would assert against a fixture never set up:\n%s"
                % (proc.returncode, output))
        # The session is still alive holding the database; kill it the way a
        # `timeout` escalation or a `pkill` would.
        proc.send_signal(9)
        proc.wait(timeout=30)
        assert _exists(name), (
            "the killed session's database vanished on its own, so this test "
            "is not exercising the leak it claims to exercise")

        # The bound here is zero rather than the shipped four hours. The data
        # directory is not writable by the test user, so a database cannot be
        # aged into the past, and a database created seconds ago is
        # legitimately not four hours old. What is under test is the liveness
        # half of the predicate, which zero preserves and which is the half
        # that must never be wrong: with the claim held the same database must
        # survive, and with the claim gone it must be reclaimed.
        with RunClaim(token, iso.admin_dsn()):
            assert sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                               only=frozenset({name})) == [], (
                "a live run's database was offered for reclamation")
            assert _exists(name)

        reclaimed = sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                                only=frozenset({name}))
        assert reclaimed == [name], (
            "the next run did not reclaim the database the killed run left")
        assert not _exists(name)
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
        _drop(name)
        shutil.rmtree(victim, ignore_errors=True)
        HOLDER_SCRIPT.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# The ready markers. A killed run leaves one behind on the filesystem as well
# as on the server, and only the server half is reclaimed.
# --------------------------------------------------------------------------

def _marker_for(token: str) -> Path:
    return REPO / (".s09iso_ready_%s" % token)


def _plant_marker(token: str) -> Path:
    marker = _marker_for(token)
    marker.write_text("held", encoding="utf-8")
    return marker


def test_a_dropped_databases_marker_is_cleared():
    """A dead run's marker goes when the sweep reclaims its databases."""
    token = "a11ce00a"
    name = _name_for(token, "mkrdrop")
    marker = _plant_marker(token)
    _create(name)
    try:
        assert sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                           only=frozenset({name})) == [name]
        assert not marker.exists(), (
            "the sweep reclaimed the database and left the marker, so a "
            "reviewer finding a stray .s09iso_ready_* concludes the reclaim "
            "is broken")
    finally:
        marker.unlink(missing_ok=True)
        _drop(name)


def test_a_live_runs_marker_survives_its_own_sweep():
    """The safety property, on the filesystem half.

    This is the one that must not weaken. The marker is the only record that
    a run was mid-flight, and the run holding the lock is the run still
    working. Clearing its marker because the database was old would be the
    same error as dropping its database.
    """
    token = "a11ce00b"
    name = _name_for(token, "mkrlive")
    marker = _plant_marker(token)
    child = _spawn_holder(token)
    try:
        assert sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                           only=frozenset({name})) == []
        assert marker.exists(), (
            "the sweep cleared a live run's marker while refusing its "
            "database; the liveness test must gate the marker too")
    finally:
        _kill(child)
        marker.unlink(missing_ok=True)
        _drop(name)


def test_a_claim_in_this_process_protects_its_own_marker():
    token = "a11ce00c"
    name = _name_for(token, "mkrclaim")
    marker = _plant_marker(token)
    _create(name)
    try:
        with RunClaim(token, iso.admin_dsn()):
            assert sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                               only=frozenset({name})) == []
        assert marker.exists(), "a claimed run's marker was cleared"
    finally:
        marker.unlink(missing_ok=True)
        _drop(name)


def test_a_marker_is_not_cleared_on_the_age_bound_alone():
    """Red half. The bound never grants permission, for a marker as for a db."""
    token = "a11ce00d"
    name = _name_for(token, "mkrselneg")
    marker = _plant_marker(token)
    _create(name)
    try:
        assert sweep_stale(iso.admin_dsn(), age=timedelta(days=3650),
                           only=frozenset({name})) == []
        assert marker.exists(), (
            "a ten-year-old bound cleared a marker, so the age test is "
            "reaching the filesystem without the liveness test")
    finally:
        marker.unlink(missing_ok=True)
        _drop(name)


def test_a_dry_run_clears_no_marker():
    token = "a11ce00e"
    name = _name_for(token, "mkrdry")
    marker = _plant_marker(token)
    _create(name)
    try:
        assert sweep_stale(iso.admin_dsn(), age=timedelta(seconds=0),
                           only=frozenset({name}), dry_run=True) == [name]
        assert marker.exists(), "a dry run removed a marker"
    finally:
        marker.unlink(missing_ok=True)
        _drop(name)


def test_only_a_marker_carrying_a_run_token_is_ever_a_candidate():
    """The marker name is a grammar, and a file outside it is not ours."""
    token = "a11ce00f"
    stranger = REPO / ".s09iso_ready_notatoken"
    stranger.write_text("x", encoding="utf-8")
    try:
        assert iso.ready_markers(REPO, tokens={token}) == []
        assert iso.marker_token(".s09iso_ready_notatoken") is None
        assert iso.marker_token(".s09iso_ready_%s" % token) == token
    finally:
        stranger.unlink(missing_ok=True)


def test_a_live_holders_marker_survives_the_clear_itself():
    """The gate, exercised where it lives.

    ``sweep_stale`` never reaches it: a locked token is already excluded by
    ``stale_plan``, so replacing the probe with a constant leaves that path
    green. The probe is the second check, for the window between the plan and
    the clear, and only a direct call reaches it. It uses the default probe, so
    the advisory-lock test it runs is the shipped one and not a stand-in.
    """
    token = "a11ce011"
    marker = _plant_marker(token)
    child = _spawn_holder(token)
    try:
        assert iso.clear_ready_markers(REPO, {token}) == [], (
            "the default probe cleared a live holder's marker, so the "
            "advisory-lock liveness test is not what gates the filesystem")
        assert marker.exists()
    finally:
        _kill(child)
    assert iso.clear_ready_markers(REPO, {token}) == [token], (
        "once the holder is gone the same marker was not cleared")
    assert not marker.exists()


def test_a_marker_with_no_database_is_still_reclaimable():
    """The database can be gone while the marker survives.

    That is the common order: ``teardown`` drops the stores, then the killed
    child's marker outlives them. Gating the marker clear on the database
    still existing would leave exactly the leak being fixed.
    """
    token = "a11ce010"
    marker = _plant_marker(token)
    name = _name_for(token, "mkrlone")
    _create(name)
    try:
        _drop(name)
        assert iso.clear_ready_markers(REPO, {token}) == [token]
        assert not marker.exists()
    finally:
        marker.unlink(missing_ok=True)
        _drop(name)


@pytest.mark.parametrize("given, expected", [
    ("0", timedelta(0)),
    ("0.5", timedelta(minutes=30)),
    (None, STALE_AFTER),
])
def test_the_age_bound_on_the_command_line_is_the_one_that_runs(
        monkeypatch, given, expected):
    """``--older-than-hours 0`` means now, not the shipped four hours.

    A truth test on the argument read zero as unset, so an operator asking
    for an immediate sweep got the four-hour bound and an empty plan, which
    looks like a clean server rather than a sweep that declined to run.
    """
    from scripts import sweep_stale_test_databases as cli

    seen = {}
    monkeypatch.setattr(cli, "stale_plan",
                        lambda dsn, *, age: (seen.setdefault("age", age), [])[1])
    argv = ["--dry-run", "--admin-dsn", "dbname=postgres"] if given is None \
        else ["--dry-run", "--admin-dsn", "dbname=postgres",
              "--older-than-hours", given]
    assert cli.main(argv) == 0
    assert seen["age"] == expected


def test_a_holder_that_exits_on_its_own_leaves_no_marker():
    """A SIGTERM'd holder cleans up after itself.

    The holder exists to be killed, and a parent-side cleanup never runs on
    the SIGKILL path. The child chains onto ``RunClaim``'s own handler, so the
    exit it *can* take leaves nothing. The script is the shipped one, not a
    copy, so this cannot pass against a helper nobody spawns.
    """
    token = "a11ce012"
    marker = _marker_for(token)
    marker.unlink(missing_ok=True)
    _write_holder_script()
    child = subprocess.Popen([str(VENV_PYTHON), str(HOLDER_SCRIPT),
                              token, str(marker)])
    try:
        assert _wait_for(lambda: marker.exists(), seconds=60)
        child.terminate()
        child.wait(timeout=30)
        assert not marker.exists(), (
            "a holder that exited on a signal it can handle left its marker, "
            "so the leak does not even need a SIGKILL to happen")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=30)
        marker.unlink(missing_ok=True)


def test_the_repo_scratch_directories_are_ignored():
    """A scratch tree in the repo root that nobody cleans is a dirty worktree.

    ``.ad01-walk-runs`` is one, and it is in the same class as the leaked
    databases: the walk runner drops its database in a ``finally`` and nothing
    ever removes the directory the study wrote.
    """
    import subprocess as sp

    for entry in (".ad01-walk-runs/", ".ad01-runs/"):
        ignored = sp.run(["git", "check-ignore", "-q", entry],
                         cwd=str(REPO), capture_output=True)
        assert ignored.returncode == 0, (
            "%s is untracked scratch that nothing cleans and is not ignored, "
            "so every run dirties the worktree" % entry)


def test_the_startup_sweep_is_skipped_when_disabled(monkeypatch):
    """The sweep is a policy, and the operator can turn it off."""
    import tests.conftest_isolation as iso

    monkeypatch.setenv(iso.DISABLE_SWEEP_ENV, "1")
    calls = []
    monkeypatch.setattr(iso, "sweep_stale",
                        lambda *a, **k: calls.append(a) or [])

    class _Config:
        pass

    config = _Config()
    iso._startup_sweep(config, iso.plan(token="a11ce006"))
    assert calls == [], "the sweep ran while disabled"
    assert not hasattr(config, "_s09iso_swept")


def test_a_sweep_failure_is_reported_and_skips_rather_than_raising(monkeypatch):
    """A sweep that cannot run must not take the session down with it."""
    import tests.conftest_isolation as iso

    monkeypatch.delenv(iso.DISABLE_SWEEP_ENV, raising=False)

    def _explode(*args, **kwargs):
        raise RuntimeError("no permission")

    monkeypatch.setattr(iso, "sweep_stale", _explode)

    class _Config:
        pass

    config = _Config()
    iso._startup_sweep(config, iso.plan(token="a11ce007"))
    assert not hasattr(config, "_s09iso_swept")


def test_the_dry_run_environment_variable_selects_a_plan_without_dropping(
        monkeypatch):
    """``S09ISO_SWEEP=1`` reports the plan and drops nothing."""
    import tests.conftest_isolation as iso

    token = "a11ce008"
    name = _name_for(token, "envdry")
    _create(name)
    monkeypatch.delenv(iso.DISABLE_SWEEP_ENV, raising=False)
    monkeypatch.setenv(iso.SWEEP_ENV, "1")
    monkeypatch.setenv(iso.SWEEP_AGE_ENV, "0")
    try:
        class _Config:
            pass

        config = _Config()
        iso._startup_sweep(config, iso.plan(token=token))
        assert name in getattr(config, "_s09iso_swept", []), (
            "a dry run did not report the database as a candidate")
        assert _exists(name), "a dry run dropped a database"
    finally:
        _drop(name)


def test_a_malformed_age_override_falls_back_to_the_shipped_bound(monkeypatch):
    """A typo in the environment must not silently widen the sweep."""
    import tests.conftest_isolation as iso

    monkeypatch.delenv(iso.DISABLE_SWEEP_ENV, raising=False)
    monkeypatch.setenv(iso.SWEEP_AGE_ENV, "not-a-number")
    seen = {}

    def _capture(admin_dsn, *, age, **kwargs):
        seen["age"] = age
        return []

    monkeypatch.setattr(iso, "sweep_stale", _capture)

    class _Config:
        pass

    iso._startup_sweep(_Config(), iso.plan(token="a11ce009"))
    assert seen["age"] == STALE_AFTER
