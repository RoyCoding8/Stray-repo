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

The sources read are this checkout's and every sibling lane's own. The list
comes from the repository index rather than from a walk, so the answer is the
same whichever checkout the test runs in and a lane's uncommitted creator is
read before it merges rather than after. A directory skip list was never what
gave that property; measured, it gave the opposite one, and the emptiness
assertion below is what notices.
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
sys.path.insert(0, str(REPO / "tests"))

from experiments.ad01 import s09_run_isolation as iso  # noqa: E402
from tests.conftest_isolation import (  # noqa: E402
    DERIVED_NAME_RE,
    derived_token,
    derived_name,
)
import worktree_checkouts as checkouts  # noqa: E402

# The directories that hold this repository's own code. A ``.py`` file in any
# other top-level directory is evidence, a report or a probe, and the grammar
# does not govern what a past run recorded: ``reports/evidence/`` is an
# immutable artifact tree, ``reviews/probes/`` is a dated assessment, and
# ``evidence-live/`` is experiment output. These are whole top-level components
# of a repository-relative path, which is what makes them a statement about the
# repository rather than a filter over whatever directory the file happens to
# sit in.
SOURCE_ROOTS = ("experiments", "scripts", "src", "tools", "tests", "migrations")


def _own_sources() -> list[tuple[Path, str]]:
    """This checkout's sources, and every sibling lane's own, keyed for a message.

    The list comes from the repository index rather than from a walk of ``REPO``,
    and the bytes are read from whichever checkout holds them. That split is
    what makes the answer the same in a lane worktree as in the integration
    checkout, and what lets a lane's own edit to a tracked file still fail here.

    The walk this replaces tested each FOREIGN name for equality against every
    component of the *absolute* path, so the component naming the checkout a
    file lives in was enough to exclude it. A lane sitting under
    ``.claude/worktrees`` excluded all of its own files on the component
    ``.claude``: the scan found zero of 930 sources, and every inventory
    assertion reported an empty list rather than a disagreement. Measured at the
    four roots that matter, the same code finds 930 sources at the integration
    root and at a throwaway clone, 1 in a lane under ``.claude`` and 0 in a lane
    under ``.worktrees`` -- so the exclusion was not hiding a sibling's copy, it
    was deleting the checkout's own tree. A directory skip list never did that
    job. Asking a sibling only for the files it does not track does, because the
    repository index already covers the rest.

    ``reports`` and ``evidence-live`` stay excluded, and they stay excluded by
    being outside ``SOURCE_ROOTS`` rather than by being named. That is the same
    policy stated as a fact about the repository instead of a filter over a
    walk, and it cannot be widened by a directory appearing somewhere else.
    """
    canonical = checkouts.canonical_root(REPO)

    def own(checkout: Path, names: list[str]) -> list[tuple[Path, str]]:
        found = []
        for relative in sorted(set(names)):
            if relative.split("/")[0] not in SOURCE_ROOTS:
                continue
            path = checkout / relative
            if path.is_file():
                found.append((path, relative))
        return found

    found = own(REPO, checkouts.tracked_paths(canonical, ("*.py",)))
    for lane in checkouts.sibling_checkouts(canonical, REPO):
        prefix = checkouts.label_for(canonical, lane)
        found.extend(
            (path, "%s/%s" % (prefix, relative))
            for path, relative in
            own(lane, checkouts.untracked_paths(canonical, lane, ("*.py",))))
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
    for path, _key in SOURCES:
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
    key: str = ""

    @property
    def where(self) -> str:
        """Where to send a reader who wants to see the site.

        The key comes from the scan rather than from ``path.relative_to(REPO)``,
        because a sibling lane's file is not under this checkout and that call
        would raise. A lane's own creator is named under the lane's own prefix,
        which is the path that opens.
        """
        if self.key:
            return "%s:%d" % (self.key, self.lineno)
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
    for path, key in SOURCES:
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
                                 is_creator=_is_create_site(node, enclosing),
                                 key=key))
    return sorted(found, key=lambda c: (c.key, c.lineno))


ALL_SITES = creators()
NAMESPACES = [c for c in ALL_SITES if c.is_creator]


def test_the_enumeration_is_not_empty():
    """A scan that finds nothing is a scan that is looking in the wrong place.

    Without this, deleting the one line that anchors the walk would turn the
    whole file green: every other test would iterate an empty list and pass.
    """
    assert NAMESPACES, (
        "found no %s_ name-synthesis site in %d sources; the scan is looking "
        "in the wrong place, not the code" % (iso.DB_PREFIX, len(SOURCES)))


def test_the_scan_reads_a_plausible_number_of_sources():
    """The emptiness assertion has a hole, and this is what closes it.

    Inside a lane worktree the scan used to find *zero* sources, which the
    assertion above caught. It could equally have found four, or thirty, and
    every inventory assertion would still have passed over the short list: an
    assertion that iterates a short list does not know it is short. So the
    floor is pinned against the repository's own index, which is the one count
    that does not depend on where this file happens to be.

    The bar is deliberately loose -- a quarter of the tracked code roots, not
    the exact total -- because the point is to catch a scan that lost a whole
    tree, not to fail when a lane legitimately adds files. The exact figure is
    printed on failure so the reader can see what was found.
    """
    canonical = checkouts.canonical_root(REPO)
    tracked = [name for name in checkouts.tracked_paths(canonical, ("*.py",))
               if name.split("/")[0] in SOURCE_ROOTS]
    assert len(SOURCES) >= max(1, len(tracked) // 4), (
        "the scan read %d sources where the repository tracks %d under %s, so "
        "it is reading a fraction of the tree and every inventory assertion "
        "over it is being decided by a short list" % (
            len(SOURCES), len(tracked), ", ".join(SOURCE_ROOTS)))


def test_the_scan_covers_every_checkout_the_repository_knows_about():
    """A sibling lane's own file is read, and keyed so a reader can open it.

    This is the property the ``.worktrees`` exclusion was supposed to buy, and
    it is asserted here rather than described. Whether any lane exists is the
    environment's business -- a throwaway clone registers one checkout and has
    no sibling -- so what is asserted is that every lane git does report
    contributes its untracked sources, under a key carrying the lane's own name
    rather than a bare relative path that would point somewhere else.

    Whether the cross-lane half actually ran is a separate claim, and it is
    ``test_the_cross_lane_half_runs_whenever_there_is_a_sibling_to_reach``.
    """
    canonical = checkouts.canonical_root(REPO)
    for lane in checkouts.sibling_checkouts(canonical, REPO):
        prefix = checkouts.label_for(canonical, lane)
        for relative in checkouts.untracked_paths(canonical, lane, ("*.py",)):
            key = "%s/%s" % (prefix, relative)
            assert (prefix + "/") in key and key != relative, (
                "lane %s contributed %r unkeyed, so a failure would name a path "
                "that does not open" % (lane.name, relative))
            if relative.split("/")[0] in SOURCE_ROOTS:
                path, scanned = next(
                    ((p, k) for p, k in SOURCES if p == lane / relative),
                    (None, None))
                assert scanned == key, (
                    "lane %s holds %r under a code root and the scan read it as "
                    "%r; a sibling's own creator is invisible to this grammar" % (
                        lane.name, relative, scanned))


def _registered_checkouts(canonical: Path) -> list[str]:
    """Every checkout the registry names, read raw.

    Raw, so that a discovery which returns nothing can be told apart from a
    repository that has nothing. Those are different failures and the test
    below reports them differently.
    """
    import subprocess

    out = subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(canonical),
         "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=True, cwd=str(canonical)).stdout
    return [line[len("worktree "):]
            for line in out.splitlines() if line.startswith("worktree ")]


def test_the_cross_lane_half_runs_whenever_there_is_a_sibling_to_reach():
    """In the batch checkout this is the assertion that the scan reaches the
    other lanes; in a standalone clone it says so and stops.

    Seventeen lanes are registered here, and each of them has a path component
    the old ``FOREIGN`` tuple named. A scan that reports green while reading
    one tree is exactly the defect this lane exists to repair, so the clone
    case skips rather than passes -- a green here would otherwise be read as
    "the cross-lane scan ran".
    """
    canonical = checkouts.canonical_root(REPO)
    registered = _registered_checkouts(canonical)
    if len(registered) < 2:
        pytest.skip("a standalone clone registers one checkout and has no "
                    "sibling to scan; the cross-lane claim is vacuous here")

    lanes = checkouts.sibling_checkouts(canonical, REPO)
    assert lanes, (
        "the repository registers %d checkouts but none were discovered, so "
        "the scan is reading one tree and reporting it as the batch" % (
            len(registered),))


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
    Creator(REPO / "tests" / "conftest_isolation.py", 162, "", True),
    Creator(REPO / "tests" / "conftest_isolation.py", 169, "", True),
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

    ``test_s09_verdict.py`` and ``test_a42_chain_demonstration.py`` are on the
    list because they pin the inheritance behaviour itself: both set or pop
    the variable to assert that a nested suite run neither claims its parent's
    token nor presents a different one. ``s09_verdict.py`` is not, because
    production names only ``S09ISO_DISABLE``; a production file on this list
    would hide the next real reader behind an entry that only ever held a
    comment.

    The archived entry is at the path it now holds. It read
    ``tests/test_s09iso_stale_sweep.py`` until the heavy-archive move of
    2026-09-29, and the stale spelling is why this assertion was red in the
    integration checkout before this lane touched it: the scan could not see a
    file whose recorded name had stopped existing.
    """
    self_path = Path(__file__).resolve()
    offenders = sorted(key for path, key in SOURCES
                       if path != self_path
                       and "S09ISO_TOKEN" in path.read_text(encoding="utf-8"))
    assert offenders == ["tests/_heavy_archived/test_s09iso_stale_sweep.py",
                         "tests/conftest_isolation.py",
                         "tests/test_a42_chain_demonstration.py",
                         "tests/test_conftest_isolation.py",
                         "tests/test_s09_verdict.py"], (
        "only the harness and the files that pin its behaviour may read "
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
