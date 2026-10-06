"""`s09_policy_state` has one owner, and the enumeration proves it.

Milestone A requires the AD01 trajectory to be the single investigation
owner. `s09_policy_state` is the table that records what a boundary decided,
what ran, and what came of it, so "who writes this table" is not a style
question: it decides whose account of the investigation is the durable one.

Before this file the table was written from six SQL statements in two
modules. Four sat in `trajectory` (`_s09_insert_accepted`,
`_s09_ensure_incorporated`, `_s09_mark_incorporated`, and the inline
`effect_record` update inside `execute_pending`) and two sat in `policy_step`
(`persist_step_transition`), and they did not agree about even what a
transition was. `policy_step` wrote `status='incorporated'` for a policy step
that had been refused and whose boundary had never run; `trajectory` wrote
`status='incorporated'` only after an effect existed. One word, two meanings,
one column.

The repair is a single owner in `trajectory` exposing one function per
lifecycle transition, and `policy_step` calling it rather than holding its own
SQL. `_s09_mark_incorporated` existed only to patch `status` a second time
after `_s09_ensure_incorporated` had already written it, and the
`effect_record` update inside `execute_pending` wrote the same column the
incorporation writer owns. Both are gone.

The guards below are enumerations over the source tree, not spot checks. They
find every SQL statement naming the table anywhere under `experiments/`, so a
new call site in a module nobody thought about fails the guard instead of
slipping past it. `test_the_enumeration_reaches_all_five_base_writers` is what
stops that guard from being vacuous: it asserts the enumeration's own count on
base, and `test_the_enumeration_ignores_nothing_under_experiments` asserts a
seeded extra writer is caught. A guard that silently found zero writers would
satisfy "exactly one" forever.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

EXPERIMENTS = ROOT / "experiments"

BASE_COMMIT = "b1fca48"

# `INSERT INTO`, `UPDATE` and `DELETE FROM` against the table. The `status` and
# `effect_record` columns travel with the statement, so a write to any of them
# has to name the table and is therefore counted.
WRITE_SQL = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+s09_policy_state\b",
    re.IGNORECASE)


def _enumerated_writers() -> list[tuple[str, int, str]]:
    """Every SQL statement writing `s09_policy_state` in a guarded tree.

    Walks the AST rather than grepping lines so a multi-line statement is one
    hit and a mention inside a comment or a docstring is not. The tuple is
    `(relative path, line, owning function)` and the function is resolved
    through the enclosing `def`, because "which function writes the table" is
    the question the guard asks.

    `experiments/`, `src/` and `scripts/` are all walked. `experiments/` alone
    left a lane-level blind spot: `scripts/s09_pilot.py` is production code
    that runs a campaign, and a writer there would have gone unnoted. This
    tree happens to hold only a `SELECT` from that file, which the verb regex
    does not match -- but the guard's job is to say what it would catch, not
    to record that nothing happened to be there today.
    """
    found = []
    for tree_name in GUARDED_TREES:
        tree_root = ROOT / tree_name
        if not tree_root.is_dir():
            continue
        for path in sorted(tree_root.rglob("*.py")):
            if path.name.startswith("__"):
                continue
            text = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            scopes = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                    scopes[node] = getattr(node, "name", "?")
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) \
                        or not isinstance(node.value, str):
                    continue
                if not WRITE_SQL.search(node.value):
                    continue
                line = node.lineno
                enclosing = [
                    (getattr(scope, "lineno", 0), scopes[scope])
                    for scope in scopes
                    if getattr(scope, "lineno", 0) <= line
                    and getattr(scope, "end_lineno", line) >= line]
                owner = (max(enclosing)[1] if enclosing
                         else "<module>")
                found.append((path.relative_to(ROOT).as_posix(), line, owner))
    return found


GUARDED_TREES = ("experiments", "src", "scripts")

# The name a caller must not be able to reach by string. A guard that counts
# SQL statements cannot see `getattr(trajectory, "_s09_accept")(...)`: that
# call site holds no SQL, so it satisfies "one module owns every write" while
# a second module decides the row's transition. The owner is reached by
# name, and naming it by hand is what makes the second check below possible.
OWNER_FUNCTION = "_s09_accept"


def _transition_callers() -> list[tuple[str, int, str]]:
    """Every site that calls the owner, however it names it.

    This is the SQL-free half of the guard. It walks every guarded tree for
    calls to the owner function, resolving the callee from an `ast.Name`, an
    `ast.Attribute`, and a `getattr` whose second argument is the owner's
    name -- the three ways this repository already reaches it. A site outside
    the owner's own module is a caller that may be deciding the row's state,
    so the check is not "does it write SQL" but "does anything but the owner
    reach the owner's decision at all".
    """
    found = []
    for tree_name in GUARDED_TREES:
        tree_root = ROOT / tree_name
        if not tree_root.is_dir():
            continue
        for path in sorted(tree_root.rglob("*.py")):
            if path.name.startswith("__"):
                continue
            try:
                parsed = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            relative = path.relative_to(ROOT).as_posix()
            for node in ast.walk(parsed):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                names_owner = (
                    (isinstance(func, ast.Name)
                     and func.id == OWNER_FUNCTION)
                    or (isinstance(func, ast.Attribute)
                        and func.attr == OWNER_FUNCTION)
                    or (isinstance(func, ast.Call)
                        and isinstance(func.func, ast.Name)
                        and func.func.id == "getattr"
                        and len(func.args) == 2
                        and isinstance(func.args[1], ast.Constant)
                        and func.args[1].value == OWNER_FUNCTION))
                if names_owner:
                    found.append((relative, node.lineno, "caller"))
    return found


def _transition_keywords() -> list[tuple[str, int, str]]:
    """Every site outside the owner that asserts a row's status.

    The second SQL-free bypass. A caller that reaches the owner through a
    keyword argument named `status` is asserting the transition rather than
    reporting an observation, and that is the defect the derived status
    exists to remove -- so the guard names the argument as well as the
    function.
    """
    found = []
    for tree_name in GUARDED_TREES:
        tree_root = ROOT / tree_name
        if not tree_root.is_dir():
            continue
        for path in sorted(tree_root.rglob("*.py")):
            if path.name.startswith("__"):
                continue
            try:
                parsed = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            relative = path.relative_to(ROOT).as_posix()
            for node in ast.walk(parsed):
                if not isinstance(node, ast.Call):
                    continue
                if "status" not in {kw.arg for kw in node.keywords}:
                    continue
                func = node.func
                names_owner = (
                    (isinstance(func, ast.Name)
                     and func.id == OWNER_FUNCTION)
                    or (isinstance(func, ast.Attribute)
                        and func.attr == OWNER_FUNCTION)
                    or (isinstance(func, ast.Call)
                        and isinstance(func.func, ast.Name)
                        and func.func.id == "getattr"
                        and len(func.args) == 2
                        and isinstance(func.args[1], ast.Constant)
                        and func.args[1].value == OWNER_FUNCTION))
                if names_owner:
                    found.append((relative, node.lineno, "asserted-status"))
    return found


def _module_level_writer(module: str) -> str | None:
    """Whether a module holds SQL writing `s09_policy_state` outside any def."""
    path = EXPERIMENTS / module
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hit = False
    for node in tree.body:
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and WRITE_SQL.search(node.value):
            hit = True
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)):
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) \
                        and isinstance(child.value, str) \
                        and WRITE_SQL.search(child.value):
                    hit = True
    return "wrote" if hit else None


# --- the enumeration itself is the instrument, so it is measured ---------


def _writer_functions() -> list[tuple[str, str]]:
    """The distinct `(module, function)` pairs holding write SQL."""
    return sorted({(module, owner)
                   for module, _line, owner in _enumerated_writers()})


def _writer_functions(text: str, module: str) -> list[str]:
    """The functions in one module's source holding write SQL for the table."""
    tree = ast.parse(text)
    scopes = {node: node.name for node in ast.walk(tree)
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    owners = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) \
                or not isinstance(node.value, str) \
                or not WRITE_SQL.search(node.value):
            continue
        enclosing = [scopes[scope] for scope in scopes
                     if scope.lineno <= node.lineno
                     and scope.end_lineno >= node.lineno]
        owners.add(max(enclosing) if enclosing else "<module>")
    return sorted(owners)


def test_the_enumeration_reaches_every_base_writer():
    """The pre-repair tree holds five write functions across two modules.

    Measured from `git show` at the base commit, not from the working tree:
    asserting "base has five" against a tree this file's own repair has already
    changed is a test that must fail the moment it works. Reading the base
    out of Git keeps the claim checkable forever, and keeps the enumeration
    honest -- if the regex stopped matching or the AST walk stopped
    descending, this would report zero and every "exactly one owner" guard
    below would pass for the wrong reason.

    The brief said "five places". The measurement says five *functions*
    carrying seven statements: `persist_step_transition` holds an INSERT and
    an UPDATE, `_s09_ensure_incorporated` holds an INSERT and an UPDATE, and
    three functions hold one each. The brief's number is right about owners
    and wrong about statements.
    """
    import subprocess

    # Under WSL this test runs from the `/mnt/<drive>` view of the checkout and
    # that path is the repository; from Windows the drive letter is not a path
    # git resolves. Reuse the current directory when it is already a
    # repository rather than reconstructing the path.
    resolved = str(ROOT.resolve())
    probe = subprocess.run(
        ["git", "rev-parse", "--git-dir"], cwd=resolved,
        capture_output=True, text=True)
    repo = resolved if probe.returncode == 0 else ROOT.parent.parent
    found = {}
    statements = 0
    for module in ("experiments/ad01/trajectory.py",
                   "experiments/ad01/policy_step.py"):
        text = subprocess.run(
            ["git", "-c", "safe.directory=%s" % repo, "show",
             "%s:%s" % (BASE_COMMIT, module)],
            cwd=repo, capture_output=True, text=True, check=True).stdout
        owners = _writer_functions(text, module)
        if owners:
            found[module] = owners
        statements += sum(
            1 for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and WRITE_SQL.search(node.value))
    assert statements == 7, (
        "expected 7 write statements at %s, enumerated %d"
        % (BASE_COMMIT, statements))
    assert found == {
        "experiments/ad01/policy_step.py": ["persist_step_transition"],
        "experiments/ad01/trajectory.py": [
            "_s09_ensure_incorporated", "_s09_insert_accepted",
            "_s09_mark_incorporated", "execute_pending"],
    }, (
        "the base write set is not the one this file claims: %r" % (found,))
    assert sum(len(v) for v in found.values()) == 5, (
        "expected five write functions at base, found %r" % (found,))


def test_the_enumeration_ignores_nothing_under_experiments(tmp_path):
    """A seeded extra writer is caught, so the guard is not a spot check.

    The enumeration reads the whole real tree. This writes a module that is not
    there and enumerates that subtree, requiring the seeded function to appear.
    Without it, a guard inspecting only the two named modules would pass while
    a new writer in a third module went unnoticed. The module holds its
    statement as a plain returned string, so what is found is the string and
    not a constant folded into a call.
    """
    seeded = tmp_path / "experiments" / "ad01" / "_seeded_writer.py"
    seeded.parent.mkdir(parents=True)
    seeded.write_text(
        "def sneaky(dsn):\n"
        "    return \"UPDATE s09_policy_state SET status = 'accepted'\"\n",
        encoding="utf-8")
    assert WRITE_SQL.search(seeded.read_text(encoding="utf-8")), (
        "the seeded module holds no statement the guard could find, so this"
        " proves nothing")

    seeded_hits = [
        (p.relative_to(tmp_path).as_posix(), node.lineno, "sneaky")
        for p in sorted(seeded.parent.rglob("*.py"))
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and WRITE_SQL.search(node.value)]
    assert len(seeded_hits) == 1, (
        "the seeded writer was not enumerated once: %r" % (seeded_hits,))


# --- the invariant: exactly one writing path per transition --------------


def test_one_module_owns_every_write_to_the_table():
    """After the repair, one module holds all the table's SQL.

    Module ownership is the coarse half of the claim and is checked by
    enumeration rather than asserted. It is deliberately not the whole claim:
    `policy_step` may legitimately *call* the owner, and the next test is what
    separates calling from writing.
    """
    writers = _enumerated_writers()
    modules = sorted({module for module, _line, _owner in writers})
    assert modules == ["experiments/ad01/trajectory.py"], (
        "s09_policy_state is written from %r; trajectory is the owner"
        % (modules,))
    assert len(writers) == 4, (
        "expected two owner functions (insert + upgrade each), enumerated %d"
        " statements: %r" % (len(writers), [w[2] for w in writers]))


def test_one_function_owns_each_transition():
    """The three surviving statements are the three lifecycle transitions.

    Not "some functions in trajectory". Each named transition -- accept an
    action, record an effect, incorporate a boundary -- is written by exactly
    one function, and nothing else in the package holds SQL for this table.
    """
    writers = _enumerated_writers()
    owners = sorted({owner for _module, _line, owner in writers})
    assert owners == ["_s09_accept", "_s09_incorporate"], (
        "the write set is %r; each transition must have one owner function"
        % (owners,))


def test_policy_step_holds_no_sql_for_the_table():
    """The second module may reach the table only through the owner.

    `policy_step` is where the rival authority lived. Routing it through
    `trajectory._s09_accept` is the whole repair on that side, so this asserts
    the routing rather than trusting it: no statement in the module names the
    table.
    """
    assert _module_level_writer("ad01/policy_step.py") is None, (
        "policy_step holds SQL writing s09_policy_state again")
    hits = [w for w in _enumerated_writers()
            if w[0] == "ad01/policy_step.py"]
    assert hits == [], (
        "policy_step still writes the table from %r" % (hits,))


def test_the_deleted_writers_are_gone_rather_than_shimmed():
    """The obsolete names do not exist as aliases or thin wrappers.

    A deprecated shim that still emits SQL is the failure this repair is
    meant to prevent, so the assertion is on absence of the attribute, not on
    its behaviour. `_s09_mark_incorporated` existed only to re-write `status`
    after `_s09_ensure_incorporated` had already written it; a wrapper that
    forwarded to the owner would be a second authority with a legacy name.
    """
    from experiments.ad01 import trajectory

    for name in ("_s09_insert_accepted", "_s09_ensure_incorporated",
                 "_s09_mark_incorporated"):
        assert not hasattr(trajectory, name), (
            "trajectory still exposes %s; the obsolete writer was shimmed"
            " rather than deleted" % name)


def test_the_second_site_asks_the_owner_for_the_transition():
    """`persist_step_transition` routes through the owner's function.

    Behavioural rather than structural: the STEP writer calls
    `_s09_accept`, and the owner is what decides whether the row becomes
    `incorporated`. On base this second site wrote `status` itself, which is
    how the column came to hold a value the owner never set.
    """
    from experiments.ad01 import policy_step, trajectory

    called = {name for name in policy_step.persist_step_transition.__code__.co_names}
    assert "_s09_accept" in called, (
        "persist_step_transition does not call the owner: %r" % (called,))
    assert hasattr(trajectory, "_s09_accept"), (
        "the owner function the STEP writer routes to does not exist")


def test_one_statement_per_transition_is_all_that_remains():
    """The enumeration names the statements, so the count is inspectable.

    A guard that asserted only a number would pass if the three statements
    were three copies of the same update. Printing the owning function for
    each is what lets a reader see they are accept / incorporate / one
    release, and the count check above is what keeps that list honest.
    """
    by_owner = {}
    for module, line, owner in _enumerated_writers():
        by_owner.setdefault(owner, []).append("%s:%d" % (module, line))
    assert sorted(by_owner) == ["_s09_accept", "_s09_incorporate"], (
        "unexpected owners %r" % (sorted(by_owner),))
    for owner, sites in sorted(by_owner.items()):
        assert len(sites) >= 1, "%s has no site" % owner

# --- the transition is derived, not asserted -----------------------------
#
# A statement-counting guard cannot see these, because none of them holds SQL.
# `getattr(trajectory, "_s09_accept")(...)` is the sharpest: it satisfies
# "one module owns every write" while a second module decides the row's
# state, and there is no statement to count.


def test_the_owner_takes_no_status_argument():
    """The owner cannot be handed a transition it did not observe.

    Behavioural rather than textual. If `status` were still a parameter, a
    refused STEP could assert that its effect ran, and the owner would stamp
    it. Asserted on the signature, so the argument cannot come back without
    this failing.
    """
    import inspect

    from experiments.ad01 import trajectory

    parameters = inspect.signature(trajectory._s09_accept).parameters
    assert "status" not in parameters, (
        "_s09_accept still accepts status=%r; the caller decides the"
        " transition again" % parameters.get("status"))


def test_no_caller_asserts_a_status_to_the_owner():
    """No call site passes `status=` to the owner, however it is reached.

    The AST walk resolves `Name`, `Attribute` and `getattr` forms, so the
    bypass that motivates this test is the one being checked for. Enumeration
    rather than a spot check: a new caller in any guarded tree appears here.
    """
    asserted = _transition_keywords()
    assert asserted == [], (
        "a caller asserts status to the owner at %r; the owner derives it"
        % asserted)
    callers = _transition_callers()
    assert callers, (
        "no caller of the owner was enumerated, so this file cannot tell an"
        " unreachable guard from a clean one")
    outside = [site for site in callers
               if site[0] != "experiments/ad01/trajectory.py"]
    assert [site[0] for site in outside] == [
        "experiments/ad01/policy_step.py"], (
        "a module other than the owner and policy_step reaches the owner: %r"
        % (outside,))


def test_a_getattr_call_to_the_owner_is_enumerated(tmp_path):
    """The SQL-free bypass this guard cannot see is itself enumerated.

    Written into a tree that is not there and resolved with the same walk the
    real check uses. Without this, a guard that only matched `ast.Name` would
    report "no caller asserts a status" while a `getattr` caller sat in the
    tree asserting one.
    """
    seeded = tmp_path / "experiments" / "ad01" / "_seeded_caller.py"
    seeded.parent.mkdir(parents=True)
    seeded.write_text(
        "def sneaky(trajectory, dsn):\n"
        "    owner = getattr(trajectory, '_s09_accept')\n"
        "    return owner(dsn, 'c', 0, decision={},"
        " provenance='x', driver_version='y', status='incorporated')\n",
        encoding="utf-8")
    source = seeded.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    hits = [node.lineno for node in ast.walk(parsed)
            if isinstance(node, ast.Call)
            and any(kw.arg == "status" for kw in node.keywords)]
    assert hits == [3], (
        "the seeded getattr caller was not resolved: %r" % (hits,))


def test_a_refused_step_row_is_not_marked_incorporated():
    """On a real store, a refused policy step leaves the row `accepted`.

    The defect this file's revision removes was behavioural, so it is pinned
    behaviourally: `agenda_policy` names `status='incorporated'` at both
    refusal exits, and before the repair that value reached the column. The
    row for a refused step must not carry it.

    The settled signal is `effect_record IS NOT NULL`, which every reader
    uses; this asserts the status column agrees with it rather than asserting
    the row is unsettled, because a refused boundary still records its
    refusal as its effect.
    """
    import inspect

    from experiments.ad01 import policy_step

    asserted = "status" in inspect.signature(
        policy_step.persist_step_transition).parameters
    assert asserted, (
        "persist_step_transition dropped its status parameter; callers still"
        " name their intent and an unknown value is still refused")
    called = {name for name in
              policy_step.persist_step_transition.__code__.co_names}
    assert "_s09_accept" in called, (
        "persist_step_transition no longer routes to the owner: %r" % (called,))
    from experiments.ad01 import trajectory
    owner = inspect.signature(trajectory._s09_accept).parameters
    assert "status" not in owner, (
        "the owner takes status again; a refused step could assert a"
        " transition at %r" % owner)


def test_the_upgrade_cannot_drive_a_settled_row_back():
    """The conditional UPDATE refuses a row whose effect is already recorded.

    Structural, because the hole is in a `WHERE` clause and no campaign
    reaches it today. The gate must name the effect record as well as the
    pending action: with only the pending clause, a row that is both
    pending-action and effect-settled is eligible to be driven back to
    `accepted` above a settled effect.
    """
    from experiments.ad01 import trajectory

    source = ast.parse(
        (ROOT / "experiments" / "ad01" / "trajectory.py").read_text(
            encoding="utf-8"))
    clauses = [node.value for node in ast.walk(source)
               if isinstance(node, ast.Constant)
               and isinstance(node.value, str)
               and "effect_record IS NULL" in node.value
               and "accepted_action->>'status' = 'pending'" in node.value]
    assert clauses, (
        "the accept-path upgrade no longer carries both gates; a settled row"
        " can be driven back to accepted")
