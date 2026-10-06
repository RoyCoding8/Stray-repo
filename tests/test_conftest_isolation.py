"""The isolation mechanism, demonstrated by a real pytest subprocess.

Every assertion reads a value the way a test module reads it: a DSN bound at
import time, in a process that imported it. Nothing here asserts which
functions were called, or restates a constant out of ``conftest_isolation``.

The RED and GREEN halves run the *plugin*, via ``pytest_configure``, against a
directory of test modules that bind the same hardcoded literal a real test
binds. RED sets ``S09ISO_DISABLE``. GREEN does not. If the mechanism did
nothing, both halves would print the same shared name and the GREEN
assertion would fail.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"

sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "experiments"))
sys.path.insert(0, str(TESTS))

import pytest

from conftest_isolation import (  # noqa: E402
    TESTS_DIR,
    admin_dsn,
    admin_dsn_or_empty,
    dbname_of,
    derived_name,
    plan,
    scan,
)

# The RED/GREEN probe runs the real plugin, which claims a lock and creates
# databases -- a live server, not a parsed one. A session with no route has
# nothing to redirect toward, so the probe battery skips rather than
# reporting the socket-era failure ("still bound the shared database")
# that the single-route repair turned into a refusal.
if not admin_dsn_or_empty():
    import pytest  # noqa: E402
    pytest.skip("SETTLEMENT_TEST_DSN is not configured",
                allow_module_level=True)

PROBE = '''\
import json
import os

DSN = os.environ.get(
    "PROBE_M3_DSN", "dbname=ec02test_m3 host=/var/run/postgresql user=ubuntu")


def test_probe_reports_the_name_it_bound():
    print("PROBE_DSN " + json.dumps(DSN))
'''


def _run_probe(scan_dir: Path, *, disable: bool,
               token: str | None = None) -> str:
    """Run pytest with the plugin over a module that binds a hardcoded literal.

    Returns the dbname the module actually bound, read out of the run's own
    stdout rather than recomputed from anything this repository defined. With
    ``token`` unset the run derives its own, which is the default path.
    """
    scan_dir.mkdir(parents=True, exist_ok=True)
    (scan_dir / "test_probe_isolation.py").write_text(PROBE, encoding="utf-8")
    (scan_dir / "conftest.py").write_text(
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import conftest_isolation\n"
        "pytest_configure = conftest_isolation.pytest_configure\n"
        "pytest_unconfigure = conftest_isolation.pytest_unconfigure\n"
        % str(TESTS), encoding="utf-8")

    env = dict(os.environ)
    env["S09ISO_SCAN_DIR"] = str(scan_dir)
    if token:
        env["S09ISO_TOKEN"] = token
    else:
        env.pop("S09ISO_TOKEN", None)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO / "src"), str(REPO / "experiments"), str(REPO),
         env.get("PYTHONPATH", "")]).strip(os.pathsep)
    if disable:
        env["S09ISO_DISABLE"] = "1"
    else:
        env.pop("S09ISO_DISABLE", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-s", "-q",
         "test_probe_isolation.py"],
        cwd=str(scan_dir), env=env, capture_output=True, text=True, timeout=300)
    for line in result.stdout.splitlines():
        if line.startswith("PROBE_DSN "):
            return dbname_of(json.loads(line[len("PROBE_DSN "):]))
    raise AssertionError(
        "probe module never reported a DSN. rc=%s\nstdout:\n%s\nstderr:\n%s"
        % (result.returncode, result.stdout[-2000:], result.stderr[-2000:]))


def _surviving_databases(token: str) -> list[str]:
    import psycopg

    with psycopg.connect(admin_dsn(), autocommit=True) as conn:
        rows = conn.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE %s",
            ("s09iso\\_%s\\_%%" % token,)).fetchall()
    return sorted(r[0] for r in rows)


def test_disabled_leaves_the_hardcoded_literal_in_place(tmp_path):
    """RED. With S09ISO_DISABLE=1 the module still binds the shared name."""
    assert _run_probe(tmp_path, disable=True) == "ec02test_m3"


def test_enabled_redirects_the_hardcoded_literal_and_cleans_up(tmp_path):
    """GREEN. The same module now binds a name this run owns, and it is gone.

    The name must be unique to the run, keep the `m3` suffix so the file's own
    containment assertion keeps holding, and not survive the session.
    """
    bound = _run_probe(tmp_path, disable=False, token="a1b2c3d4")
    assert bound != "ec02test_m3", (
        "the module still bound the shared database %r" % (bound,))
    assert bound == "s09iso_a1b2c3d4_m3"
    assert "m3" in bound
    assert _surviving_databases("a1b2c3d4") == [], (
        "the run leaked its databases: %s" % (_surviving_databases("a1b2c3d4"),))


def test_disabled_creates_no_databases(tmp_path):
    _run_probe(tmp_path, disable=True)
    assert _surviving_databases("a1b2c3d4") == []


def test_a_concurrent_run_cannot_see_this_runs_database(tmp_path):
    """The claim that matters: two runs deriving their own token never collide.

    Neither token is pinned here. The runs are separated by nothing but the
    derivation, which is the property the shared-database failures lacked.
    """
    first = _run_probe(tmp_path / "a", disable=False)
    second = _run_probe(tmp_path / "b", disable=False)
    assert first != second
    for name in (first, second):
        assert name.startswith("s09iso_")
        assert name != "ec02test_m3"
        assert name.split("_")[1] != name.split("_")[2]


def test_a_set_membership_assertion_blocks_a_redirect(tmp_path, monkeypatch):
    """`dbname in {"a", "b"}` names the database without ever comparing to a
    bare string, so a scanner that only reads the right operand misses it and
    redirects a file that cannot survive redirection. This is the shape
    test_coord02_m4_frozen uses."""
    monkeypatch.setenv("S09ISO_SCAN_DIR", str(tmp_path))
    seams = _scanned_seams(
        tmp_path,
        'import os\n'
        'DSN = os.environ.get("M4_DSN",'
        ' "dbname=ec02test_m4 host=/var/run/postgresql user=ubuntu")\n'
        'def frozen():\n'
        '    from psycopg.conninfo import conninfo_to_dict\n'
        '    assert conninfo_to_dict(DSN).get("dbname") in {"ec02test_m4",'
        ' "ec02test_acct"}\n'
        'def test_n():\n    assert True\n')
    assert seams["ec02test_m4"].mode == "pinned"
    with pytest.raises(ValueError):
        plan(token="a1b2c3d4").env_for(seams["ec02test_m4"])


def test_a_literal_with_no_assertion_is_redirectable(tmp_path, monkeypatch):
    """The negative case. A file that only reads its DSN must still redirect,
    or the scanner is simply refusing everything."""
    monkeypatch.setenv("S09ISO_SCAN_DIR", str(tmp_path))
    seams = _scanned_seams(
        tmp_path,
        'import os\n'
        'DSN = os.environ.get("PLAIN_DSN",'
        ' "dbname=ec02test_plain host=/var/run/postgresql user=ubuntu")\n'
        'def test_n():\n    assert DSN\n')
    assert seams["ec02test_plain"].mode == "redirectable"
    built = plan(token="a1b2c3d4").env_for(seams["ec02test_plain"])
    assert dbname_of(built) == "s09iso_a1b2c3d4_plain"
    # The connection fields come from the session's route, and this run has
    # none, so the built value is the dbname alone: the default's fields are
    # not consulted at all, and a routeless plan inherits no route it did
    # not earn. `test_a_redirected_seam_carries_the_session_route_and_not_
    # the_default` reads the routed half against a CI-shaped environment.
    assert set(built.split()) - {"dbname=s09iso_a1b2c3d4_plain"} == set()


def test_one_variable_shared_by_four_files_moves_all_four(tmp_path, monkeypatch):
    """EC02_AD01C_DSN is read by four files. Redirecting it moves all four, so
    a name pinned by any one of them has to pin it for every one. Last-writer-
    wins here would redirect three files on the strength of the fourth."""
    monkeypatch.setenv("S09ISO_SCAN_DIR", str(tmp_path))
    (tmp_path / "test_one.py").write_text(
        'import os\n'
        'A = os.environ.get("SHARED_DSN",'
        ' "dbname=ec02test_shared host=/var/run/postgresql user=ubuntu")\n'
        'def test_n():\n    assert A\n', encoding="utf-8")
    (tmp_path / "test_two.py").write_text(
        'import os\n'
        'B = os.environ.get("SHARED_DSN",'
        ' "dbname=ec02test_shared host=/var/run/postgresql user=ubuntu")\n'
        'def test_n():\n'
        '    assert B.split("dbname=")[1].split()[0] == "ec02test_shared"\n',
        encoding="utf-8")
    seams = _scanned_seams(tmp_path, "")
    assert seams["ec02test_shared"].mode == "pinned"
    assert "test_one.py" in seams["ec02test_shared"].source
    assert "test_two.py" in seams["ec02test_shared"].source


def test_derived_name_keeps_the_original_so_a_containment_assertion_survives():
    name = derived_name("a1b2c3d4", "ec02test_bauth")
    assert name == "s09iso_a1b2c3d4_bauth"
    assert name != "ec02test_bauth"
    assert "bauth" in name


def test_derived_name_of_a_nameless_seam_is_still_unique_per_run():
    assert derived_name("a1b2c3d4") != derived_name("ffff0000")


def _scanned_seams(directory: Path, source: str):
    """Classify one synthetic module the way a real test module is classified."""
    (directory / "test_synthetic.py").write_text(source, encoding="utf-8")
    return {s.db_name: s for s in scan(directory)}


def test_a_live_database_default_is_refused(tmp_path, monkeypatch):
    """No file in this repo defaults to ec02test_live, so scanning the real
    tests/ proves nothing. This feeds the scanner a module that does, and reads
    back what it decided."""
    monkeypatch.setenv("S09ISO_SCAN_DIR", str(tmp_path))
    seams = _scanned_seams(
        tmp_path,
        'import os\n'
        'DSN = os.environ.get("LIVE_DSN",'
        ' "dbname=ec02test_live host=/var/run/postgresql user=ubuntu")\n'
        'def test_n():\n    assert True\n')
    assert seams["ec02test_live"].mode == "pinned"
    with pytest.raises(ValueError):
        plan(token="a1b2c3d4").env_for(seams["ec02test_live"])


def test_a_refusal_input_default_is_never_turned_into_a_database(tmp_path, monkeypatch):
    """A default named ``_unused`` is an input to a test that asserts a refusal.

    Creating it would invert that test, so the scanner must mark it absent
    rather than redirect it. No file in this repo has such a default, so the
    scanner is fed one directly instead of being trusted on an empty case.
    """
    monkeypatch.setenv("S09ISO_SCAN_DIR", str(tmp_path))
    seams = _scanned_seams(
        tmp_path,
        'import os\n'
        'DSN = os.environ.get("GONE_DSN",'
        ' "dbname=ec02test_gone_unused host=/var/run/postgresql user=ubuntu")\n'
        'def test_n():\n    assert True\n')
    assert seams["ec02test_gone_unused"].mode == "absent-by-design"
    with pytest.raises(ValueError):
        plan(token="a1b2c3d4").env_for(seams["ec02test_gone_unused"])


def test_pinned_seams_are_reported_rather_than_worked_around(tmp_path,
                                                              monkeypatch):
    """A module asserting ``dbname == "ec02test_adtr"`` cannot be isolated.

    This is the finding the brief asked to be reported honestly. The mechanism
    marks the seam blocked rather than pointing it at a unique name to make the
    assertion fail, or silently leaving it on the shared database.

    The blocker used to be read off the real suite, which asserted that
    `test_ad01_traj` was pinned. Those two files were rewritten to assert the
    property rather than the name, so the real suite has no pinned seam left and
    the assertion could only ever fail. The property -- a pin is reported, never
    worked around -- is checked against a synthetic module that still pins one,
    the way the live-database and refusal-input cases above already are.
    """
    monkeypatch.setenv("S09ISO_SCAN_DIR", str(tmp_path))
    seams = _scanned_seams(
        tmp_path,
        'import os\n'
        'DSN = os.environ.get("ADTR_DSN",'
        ' "dbname=ec02test_adtr host=/var/run/postgresql user=ubuntu")\n'
        'def test_n():\n'
        '    assert DSN.split("dbname=")[1].split()[0] == "ec02test_adtr"\n')
    blocked = seams["ec02test_adtr"]
    assert blocked.mode == "pinned"
    assert "equal" in blocked.reason
    assert not blocked.redirectable
    # A pin that could be redirected would silently point a test that asserts
    # a fixed name at a name it cannot be given, so env_for must refuse rather
    # than produce a DSN the module would reject.
    with pytest.raises(ValueError):
        plan(token="a1b2c3d4").env_for(blocked)
    # The real suite used to pin this name too. It does not any more, and
    # saying so is the point: the pin was a name comparison, not a property,
    # so rewriting the test to check the property removed the blocker.
    monkeypatch.setenv("S09ISO_SCAN_DIR", "")
    live = {s.db_name: s for s in plan(token="a1b2c3d4").blocked}
    assert "ec02test_adtr" not in live, sorted(live)
    assert "ec02test_bauth" not in live
    assert "pinned" not in {s.db_name for s in
                            plan(token="a1b2c3d4").redirectable}


def test_every_seam_in_the_real_suite_is_accounted_for():
    seams = plan(token="a1b2c3d4").seams
    assert len(seams) >= 20
    assert len(seams) == len({s.env_var for s in seams})
    for seam in seams:
        assert seam.mode in {"redirectable", "pinned", "absent-by-design"}
        assert seam.db_name


def test_a_shared_store_is_a_seam_whatever_it_is_named():
    """The scan keys on a ``dbname``, never on a naming convention.

    It used to require the ``ec02test_`` prefix in both the file text and the
    default, and this assertion enforced that. So the seam was invisible
    unless its database happened to be spelled like the 25 that already were,
    which is the one thing a scanner must not depend on. ``inv_r3_export`` is
    the store that went missing for exactly this reason.
    """
    seams = {s.env_var: s for s in plan(token="a1b2c3d4").seams}
    assert "INV_R3_DSN" in seams, sorted(seams)
    assert seams["INV_R3_DSN"].db_name == "inv_r3_export"
    assert seams["INV_R3_DSN"].redirectable


def test_the_scan_reaches_the_archived_directory():
    """A file's location is not a property of its default.

    ``scan`` used to ``glob`` the top level, so the twenty-five defaults under
    ``_heavy_archived`` were invisible to it. Every one of them then bound a
    shared socket database on any host that has a socket, which is why the
    first CI run reported a connection failure for a socket that the runner
    does not have. ``EC02_L_DSN`` is asserted here by name because a seam that
    silently stops being scanned fails silently in exactly this way.
    """
    seams = {s.env_var: s for s in plan(token="a1b2c3d4").seams}
    assert "EC02_L_DSN" in seams, sorted(seams)
    assert seams["EC02_L_DSN"].source == "test_coord02_learning.py"
    assert seams["EC02_L_DSN"].redirectable


def test_a_redirected_seam_carries_the_session_route_and_not_the_default(
        tmp_path, monkeypatch):
    """The redirect must not inherit the unreachable socket from the default.

    ``env_for`` used to rebuild the DSN from ``seam.default_dsn``, keeping every
    field but the ``dbname``. A default is an ``os.environ.get`` fallback
    carrying whatever its author wrote, so every redirected seam inherited a
    socket that exists only where that author worked, and redirecting it
    changed the database without changing the route. This reads the built DSN
    against a CI-shaped environment rather than trusting that.
    """
    monkeypatch.setenv("SETTLEMENT_TEST_DSN",
                       "dbname=postgres host=127.0.0.1 port=5432 user=postgres")
    monkeypatch.setenv("S09ISO_SCAN_DIR", str(tmp_path))
    seams = _scanned_seams(
        tmp_path,
        'import os\n'
        'DSN = os.environ.get("TCP_DSN",'
        ' "dbname=ec02test_tcp host=/var/run/postgresql user=ubuntu")\n'
        'def test_n():\n    assert DSN\n')
    built = plan(token="a1b2c3d4").env_for(seams["ec02test_tcp"])
    assert "/var/run/postgresql" not in built, built
    assert "host=127.0.0.1" in built, built
    assert dbname_of(built) == "s09iso_a1b2c3d4_tcp"


def test_no_test_module_binds_a_socket_as_a_connection_route():
    """The sweep that missed this class, run against the real tree.

    Every remaining ``/var/run/postgresql`` in ``tests/`` is either this
    mechanism's own fallback or a fixture that is parsed rather than
    connected to. A literal that reaches ``psycopg.connect`` or
    ``apply_migrations`` connects nowhere on a host without a socket, so this
    asserts on the AST rather than on the text: the point is that no call is
    handed such a literal, not that the word is absent.
    """
    import ast

    routes = []
    for path in sorted(TESTS_DIR.glob("**/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if not (name.endswith("connect") or name.endswith("apply_migrations")):
                continue
            for literal in ast.walk(node):
                if (isinstance(literal, ast.Constant) and isinstance(literal.value, str)
                        and "/var/run/postgresql" in literal.value):
                    routes.append("%s:%d %s" % (path.name, node.lineno, name))
    assert routes == [], (
        "these connect through a literal socket that exists only on the "
        "author's host: %s" % (routes,))


def test_a_bare_dbname_is_not_a_route():
    """``dbname=x`` with no ``host`` is a socket DSN written without the socket.

    libpq resolves a conninfo carrying no host over the local Unix socket, so a
    string this short is the same defect spelled differently, and it is not
    caught by searching for the path. ``tests/test_p2c_ad01_resweep.py`` handed
    one to ``trajectory._publish_boundary``, which reads the boundary row
    before it refuses, so the read failed on a host with no socket.

    The assertion is narrower than "no such string exists" because five test
    modules spell one deliberately and none of them connects through it: two
    refuse on a parse that precedes any query, one replaces ``psycopg`` with a
    stub, one raises on an empty migrations directory before opening a
    connection, and one asserts that the connection it gets is refused. What
    these share is that they say so. What the repair changed is the file whose
    read happened for real, and that is what is named here -- the constant a
    refusal input is built from must carry a route, while its dbname stays the
    absent one the assertion depends on.
    """
    import ast
    import re

    target = TESTS_DIR / "test_p2c_ad01_resweep.py"
    source = target.read_text(encoding="utf-8")
    assigned = re.search(r"UNUSED_DSN = dsn_with_dbname\(\s*admin_dsn\(\),\s*"
                         r"\"([^\"]+)\"", source)
    assert assigned is not None, "the refusal input must be built from one route"
    assert assigned.group(1) == "ec02test_p2c_unused", assigned.group(1)
    assert 'trajectory.record_decision("dbname=' not in source, (
        "the absent dbname is passed inline again, which is a route libpq "
        "resolves over a local socket")
    ast.parse(source, filename=str(target))
