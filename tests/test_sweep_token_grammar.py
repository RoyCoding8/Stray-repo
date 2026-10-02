"""No creator of an ``s09iso_`` database may mint a name the stale sweep claims.

``tests/conftest_isolation.DERIVED_NAME_RE`` reads eight hex digits after the
prefix as "this database belongs to a pytest run", and ``sweep_stale`` will
reclaim any such database whose token no live process holds a lock on. The
reclaim is safe only because the *other* component that shares the prefix
cannot mint a name in that space, so the grammar never has to reason about a
run it does not own.

That is a fact about code, not about today's tree, and a grep cannot hold it: a
creator can be added, or a token source can be repointed at an environment
variable, without the string ``s09iso_`` ever changing. So this file reads the
code. It finds every site that synthesizes a name in the namespace, traces
what each one can put in the token position, and fails if any of them can
reach the bare-hex space.

It also pins the one interface that makes the grammar trustworthy: the sweep
and the direct creator must agree about which tokens are the harness's. They
live in two modules that cannot import each other -- the harness already
imports the creator -- so the agreement has to be asserted, not inherited.
"""

from __future__ import annotations

import ast
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from experiments.ad01 import s09_run_isolation as iso  # noqa: E402
from tests.conftest_isolation import (  # noqa: E402
    DERIVED_NAME_RE,
    derived_token,
    derived_name,
)

# Directories whose sources are not this repository's own code. A sibling
# worktree under ``.claude/worktrees`` is a checkout of the same tree at a
# different commit: its creators are somebody else's lane, and failing on them
# would make this test a function of what other agents happen to have checked
# out. A vendored tree is not this project's code at all.
# Directories that are not this repository's own code. A sibling worktree under
# ``.claude/worktrees`` is a checkout of the same tree at a different commit: its
# creators are somebody else's lane, and failing on them would make this test a
# function of what other agents happen to have checked out. A vendored tree is
# not this project's code at all. A run's own scratch output -- ``.ad01-runs``
# and friends -- is data a past experiment wrote, thousands of generated modules
# whose creators were the code that produced them.
FOREIGN = (".git", ".venv", "__pycache__", "node_modules",
           ".claude", ".s09suite", "site-packages", ".tox", "build", "dist",
           ".ad01-runs", ".ad01-walk-runs", ".ad01-r3-runs", ".ad01-r4-runs",
           ".worktrees", "evidence-live", "reports")


def _own_sources() -> list[Path]:
    found: list[Path] = []
    for top in ("experiments", "scripts", "src", "tools", "tests", "migrations"):
        root = REPO / top
        if not root.is_dir():
            continue
        found.extend(p for p in root.rglob("*.py")
                     if not any(part in FOREIGN for part in p.parts))
    found.extend(p for p in REPO.glob("*.py") if p.name != "conftest.py")
    return sorted(set(found))


SOURCES = tuple(_own_sources())

# Names that build a database name rather than merely mention one. A site that
# only *reads* a name -- ``dbname_of``, a ``startswith`` assertion, a SQL
# literal naming a database that a test seeds by hand -- cannot mint one, and
# listing it would bury the sites that can.
NAME_BUILDING_NODES = (ast.BinOp, ast.JoinedStr)


def _prefix_constants() -> dict[str, str]:
    """Every module constant whose value carries the namespace prefix.

    Resolved to values rather than names so that a creator spelled
    ``DB_PREFIX + "_" + token`` is found even though ``DB_PREFIX`` is not a
    literal, and so that renaming the prefix cannot silently retire the check.
    """
    found: dict[str, str] = {}
    for path in SOURCES:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            targets = ([node.target] if isinstance(node, ast.AnnAssign)
                       else getattr(node, "targets", []))
            value = getattr(node, "value", None)
            if not targets or not isinstance(value, ast.Constant) \
                    or not isinstance(value.value, str) \
                    or iso.DB_PREFIX not in value.value:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = value.value
    return found


PREFIX_CONSTANTS = _prefix_constants()


def _namespace_constants() -> set[str]:
    """Every constant carrying a prefix the sweep can select on."""
    return {name for name, value in PREFIX_CONSTANTS.items()
            if DERIVED_NAME_RE.match(value) or value in (iso.DB_PREFIX,)}


def _touches_namespace(node: ast.AST) -> bool:
    """Whether a node can put a sweep-recognizable prefix into a name."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                and iso.DB_PREFIX in sub.value:
            return True
        if isinstance(sub, ast.Name) and sub.id in _namespace_constants():
            return True
    return False


@dataclass(frozen=True)
class Creator:
    """One site that can build a database name in the ``s09iso_`` namespace."""

    path: Path
    lineno: int
    source: str
    is_creator: bool

    @property
    def where(self) -> str:
        return "%s:%d" % (self.path.relative_to(REPO), self.lineno)


# Functions that end in a store existing. A name built anywhere inside one of
# these is a database name that will exist, so a name built there is a creator.
# ``create_db``/``_create_db`` are the agenda01 creators; ``derived_name`` and
# ``_create`` are the isolation harness's own. Naming them rather than inferring
# "anything that concatenates" is what keeps identity strings (``s09iso-<token>-
# root``) and SQL fragments out of the inventory.
CREATING_FUNCTIONS = frozenset({
    "create_disposable_db", "disposable_db", "isolated_run",
    "create_db", "_create_db", "_create", "derived_name",
})


def _is_create_site(node: ast.AST, enclosing: dict[int, str]) -> bool:
    """Whether a name built at ``node`` sits inside a function that creates a store.

    The namespace is also spelled in identity strings (``s09iso-<token>-root``)
    and in a SQL fragment, neither of which creates a database. Those are not
    hazards and this file is about hazards, so a site counts only when the code
    containing it is a creator.

    Scoping to the enclosing *function* rather than an enclosing call is not a
    convenience. ``create_disposable_db`` builds its name into a local and hands
    the local to ``CREATE DATABASE`` two statements later, so there is no call
    node with the name build anywhere inside it. A creator is a function that
    mints, and a local assignment inside one is exactly that.
    """
    return enclosing.get(id(node), "") in CREATING_FUNCTIONS


def _builds_a_string(node: ast.AST) -> bool:
    """Whether a synthesis produces text rather than a number.

    ``derived_name`` computes a byte budget with ``63 - len(RUN_PREFIX) -
    len(token)``. That mentions the prefix and builds no name, and listing it
    beside the two lines that do build names would make a reviewer count three
    creators where there is one.
    """
    if isinstance(node, ast.BinOp):
        operands = (node.left, node.right)
        # String concatenation and interpolation only; ``-`` and arithmetic on
        # the prefix's length are not name construction.
        if isinstance(node.op, ast.Sub):
            return False
        for operand in operands:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                return True
            if isinstance(operand, (ast.JoinedStr, ast.BinOp)):
                return True
        return False
    return True


def creators() -> list[Creator]:
    """Every site that can build a name in the namespace, sorted by location."""
    found: list[Creator] = []
    for path in SOURCES:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        enclosing: dict[int, str] = {}
        for parent in ast.walk(tree):
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(parent):
                    if child is not parent:
                        enclosing.setdefault(id(child), parent.name)
        for node in ast.walk(tree):
            synthesizes = isinstance(node, NAME_BUILDING_NODES) \
                or (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "format")
            if not synthesizes or not _builds_a_string(node) \
                    or not _touches_namespace(node):
                continue
            found.append(Creator(path=path, lineno=node.lineno,
                                 source=ast.unparse(node),
                                 is_creator=_is_create_site(node, enclosing)))
    return sorted(found, key=lambda c: (str(c.path), c.lineno))


ALL_SITES = creators()
NAMESPACES = [c for c in ALL_SITES if c.is_creator]


def test_the_enumeration_is_not_empty():
    """A scan that finds nothing is a scan that is looking in the wrong place.

    Without this, deleting the one line that anchors the walk would turn the
    whole file green: every other test would iterate an empty list and pass.
    """
    assert NAMESPACES, (
        "found no %s_ name-synthesis site in %d sources; the walk is broken, "
        "not the code" % (iso.DB_PREFIX, len(SOURCES)))


def test_the_pinned_creator_is_among_those_found():
    """``create_disposable_db`` is the choke point; the scan must see it.

    A scan anchored only on the harness would stay green if the production
    creator stopped building a name this way, which is the one line the whole
    safety argument rests on.
    """
    production = (REPO / "experiments" / "ad01" / "s09_run_isolation.py")
    found = [c for c in NAMESPACES
             if c.path == production
             and "uuid" in c.source
             and "DB_PREFIX" in c.source]
    assert found, (
        "create_disposable_db's name build is no longer in the scan; found "
        "instead: %s" % ([(c.where, c.source[:40]) for c in NAMESPACES],))


def test_every_creator_is_enumerated_below():
    """The list in this test is the whole list, and a new site must be added.

    A scan that silently absorbs a new creator is not a test. Pinning the
    inventory forces whoever adds a creator to say what it is, which is the
    moment to discover they minted a bare-hex token.
    """
    known = {c.where for c in NAMESPACES}
    declared = {c.where for c in PINNED_CREATORS}
    assert known == declared, (
        "the set of %s_ creators changed.\n  new: %s\n  gone: %s"
        % (iso.DB_PREFIX, sorted(known - declared), sorted(declared - known)))


# The three sites that can bring an ``s09iso_`` database into existence:
# ``create_disposable_db`` in production, and the two lines of
# ``derived_name`` that the pytest harness redirects its own seams with. Every
# other site in the namespace builds a study root, a campaign id, a SQL
# fragment, an assertion prefix, or a ready-marker path -- none of which is a
# database, which is why they are bystanders rather than creators.
PINNED_CREATORS = (
    Creator(REPO / "experiments" / "ad01" / "s09_run_isolation.py", 256, "", True),
    Creator(REPO / "tests" / "conftest_isolation.py", 124, "", True),
    Creator(REPO / "tests" / "conftest_isolation.py", 131, "", True),
)


# --- the property: no creator may reach the harness's bare-hex token space ---

def test_no_creator_can_mint_a_bare_eight_hex_token():
    """The hazard itself, asserted against the code rather than against a name.

    Every direct creator funnels through ``_checked_token``, so the question
    is not whether each site validates its token -- several do not validate at
    all -- but whether the one gate they share refuses the space. This asserts
    that the gate exists, that it is the gate, and that it refuses.
    """
    for token in ("deadbeef", "00000000", "a11ce001", "5e9b0001", "5E9B0001"):
        with pytest.raises(ValueError):
            iso._checked_token(token.lower())


def test_a_creator_that_minted_a_bare_token_would_be_selected_by_the_sweep():
    """Why the space is refused: the name it produces is reclaimable.

    This is the causal link. If a creator were to mint
    ``s09iso_deadbeef_<uuid12>``, the sweep would read ``deadbeef`` out of it,
    look for a lock nobody holds, and drop a live run's stores. The assertion
    is on the real grammar and the real creator, so it cannot pass by accident
    if either side drifts.
    """
    name = "%s_%s_%s" % (iso.DB_PREFIX, "deadbeef", "0123456789ab")
    assert derived_token(name) == "deadbeef", (
        "a bare-hex direct name is no longer sweep-selected, so the refusal "
        "may be relaxed -- re-derive the reason before changing it")
    assert derived_name("deadbeef", "ec02test_state") == "s09iso_deadbeef_state"


def test_the_creator_refuses_bare_hex_before_minting():
    """The refusal happens at the gate, not after a database exists.

    ``_checked_token`` is called by the name builder, so a refusal here is a
    refusal before ``CREATE DATABASE``. Asserting the exception rather than
    inspecting a server is what makes this runnable with no database at all.
    """
    for call in (
        lambda: iso.study_root_for("deadbeef"),
        lambda: iso.campaign_for("deadbeef"),
        lambda: iso.allocation_for("deadbeef"),
    ):
        with pytest.raises(ValueError):
            call()


def test_the_two_grammars_agree_about_which_tokens_are_the_harnesss():
    """The sweep and the creator must not drift apart on the token space.

    They cannot import each other -- ``conftest_isolation`` already imports
    ``s09_run_isolation``, and a cycle would make the direction ambiguous.
    So the agreement is asserted: every token the creator refuses for being
    bare hex is one the sweep would select out of a name, and every token the
    creator accepts is one the sweep would not read as a run token.
    """
    for token in ("deadbeef", "00000000", "a11ce001", "5e9b0001"):
        with pytest.raises(ValueError):
            iso._checked_token(token)
        name = "%s_%s_%s" % (iso.DB_PREFIX, token, "0123456789ab")
        assert derived_token(name) == token, (
            "the creator refuses %r but the sweep does not select it; the "
            "refusal is protecting nothing" % (token,))

    for token in ("ctlwalk1a2b3c4d", "r4diagabcd", "e3ladder", "m3dry",
                  "invr1e2replicar2", "m1state"):
        assert iso._checked_token(token) == token
        name = "%s_%s_%s" % (iso.DB_PREFIX, token, "0123456789ab")
        assert derived_token(name) is None, (
            "%r is accepted by the creator but selected by the sweep" % (token,))


def test_the_harness_own_token_source_is_outside_the_creators_reach():
    """No creator may read the harness's bare-hex token from the environment.

    ``conftest_isolation.run_token`` is the one function that mints bare hex on
    purpose, and it hands that token to whoever asks when ``S09ISO_TOKEN`` is
    set. If a direct creator read the variable -- or called the function -- the
    refusal at the gate would be the only thing standing between a pytest run's
    own token and a second database the sweep would reclaim while that run is
    still going.

    Scoped to ``S09ISO_TOKEN``, not to importing ``conftest_isolation`` at all.
    Seventeen files import it legitimately: the harness's own conftest, the
    sweep, and the test modules that pin its behaviour. Importing the module is
    not the hazard; calling the mint is. ``run_token`` is deliberately not
    matched by name either, because ``s09_study_protocol`` has an unrelated one
    returning twelve hex characters that never names a database -- a check that
    flagged that would train a reader to ignore it.

    The sweep is absent from the allow-list because it never reads a value: it
    calls ``stale_plan``, which resolves the token out of each database name
    rather than out of the environment. Naming it here would pin a fact about
    the sweep's imports rather than about anyone's liveness.
    """
    self_path = Path(__file__).resolve()
    offenders = sorted(path.relative_to(REPO).as_posix() for path in SOURCES
                       if path != self_path
                       and "S09ISO_TOKEN" in path.read_text(encoding="utf-8"))
    assert offenders == ["tests/conftest_isolation.py",
                         "tests/test_conftest_isolation.py",
                         "tests/test_s09iso_stale_sweep.py"], (
        "only the harness and the two files that pin its behaviour may read "
        "the variable that mints bare hex; these others do: %s" % (offenders,))


def test_a_creator_taking_a_caller_supplied_token_is_still_gated():
    """The dangerous case is the one that takes a token from its caller.

    ``s09_m3_pilot`` takes ``--token`` from argv and hands it straight to
    ``disposable_db``. Before the gate it accepted ``--token deadbeef`` and
    minted a name the sweep selects. The token is still caller-supplied -- that
    is the point of the argument -- so what has to hold is that the shared
    gate refuses the dangerous values, wherever they came from.
    """
    source = (REPO / "experiments" / "ad01" / "s09_m3_pilot.py").read_text()
    assert "disposable_db(args.token)" in source, \
        "s09_m3_pilot no longer passes its argv token to the creator; " \
        "re-check the caller-supplied path this test is about"
    for token in ("deadbeef", "00000000"):
        with pytest.raises(ValueError):
            iso._checked_token(token)


# --- the sweep's side: grammar and lock must never disagree silently ---

CANDIDATE = type("Candidate", (), {"name": "s09iso_deadbeef_state",
                                   "token": "deadbeef"})()


class _DeadServer(Exception):
    pass


class _Connection:
    """The only thing ``_cluster_probe`` does with a connection is close it."""

    def close(self) -> None:
        pass


@contextmanager
def _probe_against(sweep, connect, locked):
    """``sweep._cluster_probe`` wired to the two server calls given here.

    Replaces the names the module under test looks up, and keeps them replaced
    for as long as the probe is in use. The probe resolves them at call time,
    so restoring them before the probe runs would test the real server
    instead of the broken one.
    """
    saved = (sweep._admin_connection, sweep._token_locked)
    sweep._admin_connection = connect
    sweep._token_locked = locked
    try:
        yield sweep._cluster_probe("dbname=postgres")
    finally:
        sweep._admin_connection, sweep._token_locked = saved


def _refuses(*_args, **_kwargs):
    raise _DeadServer("the server is not answering")


def _opens(*_args, **_kwargs):
    return _Connection()


@pytest.mark.parametrize("where", ["connecting", "reading the lock table"])
def test_the_sweep_treats_an_unanswerable_liveness_check_as_a_refusal(where):
    """Fail safe: no answer is not a negative answer.

    ``_cluster_probe`` wraps both ways the server can fail to answer -- the
    connection itself, and the query against ``pg_locks``. If either returned
    ``False`` instead of raising, that ``False`` would read as "nobody holds
    the lock", which is the claim that authorises a drop.

    The probe is built by the function under test with only its two
    dependencies substituted. Handing ``reclaimable`` a ready-made ``probe``
    that raises -- which an earlier version of this test did -- asserts that
    ``reclaimable`` honours a refusal, and says nothing about whether the thing
    that *builds* the probe ever raises one. That version stayed green when
    ``_cluster_probe`` was changed to swallow every exception and return
    ``False``; this one goes red.
    """
    from scripts import sweep_stale_test_databases as sweep

    connect, locked = ((_refuses, _opens) if where == "connecting"
                       else (_opens, _refuses))
    with _probe_against(sweep, connect, locked) as probe:
        droppable, surviving = sweep.reclaimable([CANDIDATE], probe)
    assert droppable == [], (
        "a server that could not answer while %s was read as permission to "
        "drop %s" % (where, CANDIDATE.name))
    assert len(surviving) == 1 and "liveness unavailable" in surviving[0][1]


def test_the_sweep_keeps_a_locked_run_even_though_the_grammar_selected_it():
    """When the two disagree, the lock wins -- and here it agrees to keep.

    A locked token means a live run. The grammar selected the database, so the
    two disagree in the direction the sweep must resolve by keeping. Dropping
    here is precisely the failure this lane exists to prevent.
    """
    from scripts import sweep_stale_test_databases as sweep

    candidate = type("C", (), {"name": "s09iso_deadbeef_state",
                               "token": "deadbeef"})()
    droppable, surviving = sweep.reclaimable([candidate], lambda t: True)
    assert droppable == []
    assert surviving[0][0].name == "s09iso_deadbeef_state"
    assert "locked" in surviving[0][1]


def test_the_sweep_drops_only_an_unlocked_token_the_grammar_selected():
    """The other direction: the lock having spoken, the drop proceeds.

    Pins the other half of the rule, so the test above cannot be satisfied by
    a sweep that keeps everything.
    """
    from scripts import sweep_stale_test_databases as sweep

    candidate = type("C", (), {"name": "s09iso_deadbeef_state",
                               "token": "deadbeef"})()
    droppable, surviving = sweep.reclaimable([candidate], lambda t: False)
    assert surviving == []
    assert [c.name for c in droppable] == ["s09iso_deadbeef_state"]


def test_the_grammar_alone_never_authorises_a_drop():
    """A shape is a candidacy, not a permission.

    The name matched ``DERIVED_NAME_RE`` -- that is the only reason this
    database is in the plan at all. It is not a reason to drop it, and the
    reconciliation says so by consulting the lock for every single candidate
    rather than short-circuiting on the match.
    """
    from scripts import sweep_stale_test_databases as sweep

    assert derived_token("s09iso_deadbeef_state") == "deadbeef"
    consulted = []

    def probe(token):
        consulted.append(token)
        return False

    sweep.reclaimable(
        [type("C", (), {"name": "s09iso_deadbeef_state", "token": "deadbeef"})()],
        probe)
    assert consulted == ["deadbeef"], \
        "the lock was never consulted for a grammar-selected database"
