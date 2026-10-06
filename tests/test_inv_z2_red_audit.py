"""Z2 red audit: the reds nobody had recorded, re-aimed at the current tip.

Lane `z2-redaudit` ran the 51 affected test files against `e442a02` and found
reds outside the reviewer's deliberate set. It committed four guards here, each
of the form "this condition no longer holds", plus the report at
`reports/workstreams/z2-red-audit.md`.

Five of the six guards have since gone red because their subjects were
repaired, not because a defect regressed. A guard whose subject is fixed has
outlived its finding: it must be re-aimed at the invariant it was protecting,
not deleted, and not left red. What each became:

  - Z2-01 (two guards). The `.worktrees in path.parts` exclusion really is
    gone, replaced by `tests/worktree_checkouts.py`, which resolves the
    canonical root structurally and asks git for each checkout's tracked and
    untracked paths. The gate's answer no longer depends on where the file
    lives. Re-aimed at the invariant the finding wanted: the census gives the
    same answer from any checkout, and it is not vacuous.

  - Z2-02a. `tests/test_m1_shared_executor.py` really was migrated, and the
    guard is correct about that one file. It was also only ever about one
    file, so it went green while the condition it names was violated three
    files over. Re-aimed at the whole test tree, where it is RED.

  - Z2-02a, a second repair. The re-aimed guard was still blind, for a
    different reason than the first. It named `run_policy_step` and
    `_shared_assessment_arm`, and neither is a guarded executor: the two
    functions that raise `refused: execution needs explicit authority and
    identity` are `run_step_out_of_process` and `run_member_out_of_process`,
    and a guard reading neither cannot see a single call site of either. It
    reported zero files over 84 call sites and read as green. `EXECUTORS` is
    now derived from the guarded executors and their forwarders, and the
    scope is `rglob`, which reaches the 85 files under
    `tests/_heavy_archived/` that the top-level glob skipped. It is RED, and
    it is no longer reading green over tests that are failing for exactly
    this reason.

  - Z2-02b. The authority is still forwarded, through a `**splat` of
    `_step_authority(...)` rather than three keywords, and `{kw.arg for kw in
    node.keywords}` reads a splat as `{None}`. `_construct_policy_revision` no
    longer reaches the executor at all; `_use_policy_action` does. Re-aimed at
    the chain that actually carries the authority.

  - Z2-03. The migration count really was un-pinned, by `expected_migrations()`
    reading the same glob `apply_migrations` reads. The guard's predicate was
    "any integer literal in an `==`", which matched eleven ordinary
    assertions and was red for a reason that was never true. Re-aimed at a
    comparison *about migrations* against an integer, across the whole tree.

  - Z2-04. The fixture really was migrated. The remaining mention is inside the
    docstring that explains why the symbol is gone, and that prose is the
    documentation the finding wanted preserved. Re-aimed at code position:
    the symbol may be named in a docstring, never loaded.

The C14 gate reached the same conclusion about its own subject and says so in
its own words: "the check is for a read, not a mention".
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DEAD = "S09_STUDY_CALLS_ALREADY_SPENT"
KNOWN_READER = "scripts/s09_pilot.py"
AUTHORITY = ("dsn", "allocation_id", "operation_id")

#: The production names that launch or stage bounded child execution, and so
#: are guarded on the authority triple. Derived, not chosen.
#:
#: Two seeds, both carrying all three keys as named parameters and both raising
#: `refused: execution needs explicit authority and identity` before a byte is
#: staged: `method_exec.run_step_out_of_process` and
#: `method_exec.run_member_out_of_process`. A third guard of the same shape
#: lives at `improve_channel._run_source`, which takes the pair as one
#: `authority` dict rather than as keywords; it is excluded here because no
#: test calls it, and `tests/test_inv_a8_improve_authority.py` already owns its
#: boundary.
#:
#: The four middle names are the forwarders: each carries all three keys as
#: named parameters and each forwards them by keyword into a seed, so a bare
#: call to one drops the authority just as surely as a bare call to a seed.
#: `trajectory._run_member` is in the set for the same reason the seeds are.
#::
#: The earlier tuple here was `("run_policy_step", "_shared_assessment_arm")`.
#: Only `run_policy_step` is a forwarder and neither is a seed, so the tuple
#: could not see a single call site of either guarded executor. It reported
#: zero files over 84 real call sites. A44's "34 sites across 10 files" was
#: measured against the same blind tuple.
EXECUTORS = (
    "run_member_out_of_process",
    "run_step_out_of_process",
    "_run_member",
    "run_policy_step",
    "_check_source",
    "_policy_evaluate",
)

#: What each forwarder forwards into. Measured off the production bodies: every
#: one of these names appears as the callee of a guarded executor, once.
FORWARDS_TO = {
    "run_member_out_of_process": (),
    "run_step_out_of_process": (),
    "_run_member": ("run_member_out_of_process",),
    "run_policy_step": ("run_step_out_of_process",),
    "_check_source": ("run_member_out_of_process",),
    "_policy_evaluate": ("run_step_out_of_process",),
}


def _reaches(name: str) -> set[str]:
    """`name` plus every executor it forwards into."""
    reached = {name}
    pending = [name]
    while pending:
        for callee in FORWARDS_TO.get(pending.pop(), ()):
            if callee not in reached:
                reached.add(callee)
                pending.append(callee)
    return reached


def _test_files() -> list[Path]:
    """Every test module, at any depth.

    `tests/_heavy_archived/` holds 85 files that CI runs one at a time, so it is
    part of the suite and not a graveyard. The top-level glob missed all of them,
    and `tests/conftest_isolation.scan` reaches them with `rglob`, which is the
    resolution this gate adopts: a file's location does not change what kind of
    call site it is.
    """
    return sorted((ROOT / "tests").rglob("test_*.py"))


def _parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


# --- Z2-01: the reader census must not depend on where it runs ------------


def _reader_census(canonical: Path, own: Path) -> list[str]:
    """The reader set, resolved the way the C14 gate resolves it.

    Read from `worktree_checkouts` rather than by walking `ROOT`, because the
    whole point of Z2-01 is that a walk from `__file__` answers a different
    question in every checkout. This re-runs the gate's own mechanism so a
    regression in the scoping shows up here as well as there.
    """
    import re

    import worktree_checkouts as checkouts

    reader = re.compile(
        r"""environ\s*\.?\s*(?:\.get\s*\(\s*)?\(?\s*['"]%s['"]""" % DEAD)
    hits: list[str] = []

    def scan(paths: list[tuple[Path, str]]) -> None:
        for path, key in paths:
            for number, line in enumerate(
                    path.read_text(encoding="utf-8", errors="ignore")
                    .splitlines(), 1):
                if reader.search(line):
                    hits.append("%s:%d" % (key, number))

    scan([(canonical / name, name)
          for name in checkouts.tracked_paths(canonical, ("*.py",))])
    for lane in checkouts.sibling_checkouts(canonical, own):
        prefix = checkouts.label_for(canonical, lane)
        scan([(lane / name, "%s/%s" % (prefix, name))
              for name in checkouts.untracked_paths(
                  canonical, lane, ("*.py",))])
    return sorted(hits)


def test_the_reader_census_is_not_vacuous_inside_a_lane_worktree():
    """The dead name's one live reader must be findable from any checkout.

    Z2-01 found the gate skipping `".worktrees" in path.parts`, which is true
    of a lane's own files, so the scan returned nothing from inside a worktree.
    The exclusion is gone and `worktree_checkouts` replaced it. This asserts
    the property that finding wanted rather than the shape of the fix: the
    census, run the way the gate runs it, still sees the reader.

    The original guard asserted the exclusion was still present, so it went red
    the moment the exclusion was fixed. That is a tripwire firing correctly, not
    a defect, and it is inverted here.
    """
    import worktree_checkouts as checkouts

    canonical = checkouts.canonical_root(ROOT)

    assert (ROOT / KNOWN_READER).exists(), (
        "%s is gone; re-derive this finding" % KNOWN_READER)

    hits = _reader_census(canonical, ROOT)

    assert [hit.rsplit(":", 1)[0] for hit in hits] == [KNOWN_READER], (
        "the reader census returned %r from inside a checkout. An empty list "
        "here is the defect Z2-01 named, and a longer one means a second "
        "reader exists that nothing has recorded." % (hits,))
    number = int(hits[0].rsplit(":", 1)[1])
    assert DEAD in (canonical / KNOWN_READER).read_text(encoding="utf-8").splitlines()[number - 1]


def test_the_census_scans_the_repository_rather_than_the_directory_it_lives_in():
    """A checkout's copy of a tracked file is not a second reader.

    A lane worktree holds every tracked file, so a scan that walks its own
    root sees the repository and every sibling at once and its answer depends
    on which lane is asking. What makes a file a copy rather than a second
    reader is that its checkout already tracks it, so the reader set is the
    repository's tracked sources plus each sibling's untracked ones.

    This asserts the mechanism, because the census being correct once is not
    evidence of how it got there. A gate that walks `ROOT` passes from the
    main checkout by accident and fails from every lane.
    """
    import worktree_checkouts as checkouts

    canonical = checkouts.canonical_root(ROOT)

    tracked = checkouts.tracked_paths(canonical, ("*.py",))

    assert tracked, (
        "git reported no tracked python under %s, so the census is reading "
        "nothing and would compare an empty list to an empty list" % canonical)
    assert KNOWN_READER in tracked, (
        "%s is not tracked by the repository, so the census cannot be reading "
        "it from the tracked set" % KNOWN_READER)

    # A lane's own copy of a tracked file must not be reachable as an
    # independent hit, which is what an unscoped path exclusion used to do.
    if (ROOT / ".git").is_file():
        assert canonical != ROOT, (
            "this is a linked worktree but resolves to itself, so the "
            "tracked/untracked split is not being exercised from here")
        untracked = checkouts.untracked_paths(canonical, ROOT, ("*.py",))
        assert KNOWN_READER not in untracked, (
            "%s is untracked in this checkout, so this lane's copy of it "
            "would be reported as a second reader" % KNOWN_READER)


# --- Z2-02: every executor call carries its execution authority -----------


def _executor_call_shape(tree: ast.Module, node: ast.Call) -> str:
    """Which of the three legitimate forms this bare call site is in.

    Lane A17's resolution: a test may assert the refusal, assert the effect
    under real authority, or be a helper. Only the second is a defect, and the
    predicate has to tell the three apart or the gate reports a contract test's
    own evidence as a defect. The classification is mechanical, from the parse:
    a `pytest.raises` block owns the call, and a `monkeypatch.setattr` of the
    executor or of anything it forwards into means the call never reaches the
    real child.
    """
    line = node.lineno
    name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
    enclosing = None
    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and candidate.lineno <= line <= (candidate.end_lineno or line):
            if enclosing is None or candidate.lineno > enclosing.lineno:
                enclosing = candidate

    for block in ast.walk(tree):
        if not isinstance(block, ast.With):
            continue
        if not any("pytest.raises" in ast.unparse(item.context_expr)
                   for item in block.items):
            continue
        if block.body[0].lineno <= line <= block.body[-1].end_lineno:
            return "asserts-the-refusal"

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        if "setattr" not in ast.unparse(call.func):
            continue
        if call.lineno > line:
            continue
        patched = {target for argument in call.args
                   for target in _reaches(name)
                   if target in ast.unparse(argument)}
        if patched:
            return "executor-patched-out"

    if enclosing is not None and enclosing.name.startswith("test_"):
        return "asserts-the-effect"
    return "helper"


def _executor_census(tree: ast.Module) -> list[tuple[str, int, str]]:
    """Every bare call to an executor, each with the form it is in.

    Returns `(name, line, shape)`. The shape is A17's three-form resolution, so
    the census is a record of all of them rather than of the defects alone: a
    reader who disagrees with one classification can see the other sites and
    the rule that sorted them.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name not in EXECUTORS:
            continue
        if any(kw.arg is None for kw in node.keywords):
            continue
        if {kw.arg for kw in node.keywords} & set(AUTHORITY):
            continue
        found.append((name, node.lineno, _executor_call_shape(tree, node)))
    return sorted(set(found))


def _bare_executor_calls(tree: ast.Module) -> list[str]:
    """The bare call sites that assert an effect rather than the refusal."""
    return ["%s:%d" % (name, line)
            for name, line, shape in _executor_census(tree)
            if shape == "asserts-the-effect"]


def _bare_executor_scripts(tree: ast.Module, docstrings: set[int]) -> list[str]:
    """Executor calls embedded in a subprocess script, carrying no authority.

    Docstrings are skipped by line, so prose that mentions a call is not a
    call. What is left is code written as a string and run by another
    interpreter, which is a real call site that no `Call` node reports.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) \
                or not isinstance(node.value, str):
            continue
        if node.lineno in docstrings:
            continue
        text = node.value
        if not any("%s(" % name in text for name in EXECUTORS):
            continue
        if any("%s=" % key in text for key in AUTHORITY):
            continue
        found.append("script:%d" % node.lineno)
    return sorted(set(found))


def _docstring_lines(tree: ast.Module) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            if node.body and isinstance(node.body[0], ast.Expr) \
                    and isinstance(node.body[0].value, ast.Constant) \
                    and isinstance(node.body[0].value.value, str):
                lines.update(range(node.body[0].lineno,
                                   node.body[0].end_lineno + 1))
    return lines


def test_no_test_calls_the_executor_without_execution_authority():
    """No test in the tree may execute policy source with no authority.

    `method_exec.run_step_out_of_process` refuses at line 1595 when any of
    `dsn`, `allocation_id` or `operation_id` is missing, before it stages a
    byte, and `run_member_out_of_process` refuses at line 1120 the same way.
    A test that calls either with none of them is asserting against the refusal
    rather than against the behaviour it names.

    Two things this gate got wrong before, both measured rather than argued.
    Its `EXECUTORS` named no guarded executor, so it could not see a call site
    of either; it reported zero files over 84 real ones. And its scope was a
    top-level glob, which excluded all 85 files under `tests/_heavy_archived/`
    that CI runs. Corrected, it reads 31 bare sites across 12 files: 13 assert
    the refusal on purpose, 3 are helpers, 2 call an executor the test has
    monkeypatched away, and 13 are defects -- a test asserting an effect
    against a refusal it never reaches.

    This is deliberately left red. The condition it names is true.
    """
    bare = {}
    excused = {}
    for path in _test_files():
        try:
            tree = _parsed(path)
            census = _executor_census(tree)
            scripts = _bare_executor_scripts(tree, _docstring_lines(tree))
        except SyntaxError as exc:
            bare.setdefault("unparseable", []).append(
                "%s: %s" % (path.name, exc))
            continue
        offenders = ["%s:%d" % (name, line)
                     for name, line, shape in census
                     if shape == "asserts-the-effect"]
        if offenders or scripts:
            bare[path.name] = sorted(offenders + scripts)
        allowed = ["%s:%d (%s)" % (name, line, shape)
                   for name, line, shape in census
                   if shape != "asserts-the-effect"]
        if allowed:
            excused[path.name] = sorted(allowed)

    assert not bare, (
        "these call sites execute policy source with no authority, so the "
        "tests around them measure the refusal at method_exec.py:1595 rather "
        "than the behaviour they were written to pin: %r. Supply dsn/"
        "allocation_id/operation_id -- tests.execution_authority.mint exists "
        "for exactly this -- and their assertions become meaningful again. "
        "Bare sites that are NOT defects, excluded by form: %r"
        % (bare, excused))


def _keys_forwarded_by_helper(module_source: str, helper: str) -> set[str]:
    """The authority keys a `**helper(...)` splat actually carries.

    A splat keyword has `arg is None`, so the plain keyword set reads it as
    `{None}` and the forwarding becomes invisible. Resolving the helper's
    returned dict literal is what lets the guard see a legitimate shape change
    as legitimate instead of as an omission.
    """
    tree = ast.parse(module_source)
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == helper), None)
    if fn is None:
        return set()
    keys: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            keys |= {k.value for k in node.value.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


def test_the_execution_authority_reaches_the_executor_through_whichever_helper_forwards_it():
    """The arm and the use path must hand the executor a real authority.

    `_shared_assessment_arm` builds it with `_step_authority(dsn,
    allocation_id, session, step_no)`, which returns the three keys or an empty
    dict when there is no store. `_use_policy_action` takes the authority as
    its `execution` argument and splats it whole. Neither names the keys at the
    call site any more, which is what made the original guard blind to both.

    The invariant is that no authority is dropped between the caller and
    `run_step_out_of_process`. A filtered splat, or a helper that stops
    returning `operation_id`, is the regression this catches.
    """
    from experiments.ad01 import assessment_profile, trajectory

    arm_source = inspect.getsource(assessment_profile._shared_assessment_arm)
    arm_keys = _keys_forwarded_by_helper(
        inspect.getsource(assessment_profile), "_step_authority")

    assert set(AUTHORITY) <= arm_keys, (
        "_step_authority returns %r, so _shared_assessment_arm splats an "
        "authority missing %s and every model action it stages is refused"
        % (sorted(arm_keys), sorted(set(AUTHORITY) - arm_keys)))

    splats = [
        node for node in ast.walk(ast.parse(arm_source))
        if isinstance(node, ast.Call)
        and (getattr(node.func, "attr", None)
             or getattr(node.func, "id", None)) == "run_policy_step"
        and any(kw.arg is None for kw in node.keywords)
    ]
    assert splats, (
        "_shared_assessment_arm no longer reaches run_policy_step through a "
        "splat; re-derive how the authority reaches the executor")

    use_source = inspect.getsource(trajectory._use_policy_action)
    use_calls = [
        node for node in ast.walk(ast.parse(use_source))
        if isinstance(node, ast.Call)
        and (getattr(node.func, "attr", None)
             or getattr(node.func, "id", None)) == "run_policy_step"
    ]
    assert use_calls, (
        "_use_policy_action no longer reaches run_policy_step; this finding "
        "is stale")

    for node in use_calls:
        splatted = [ast.unparse(kw.value) for kw in node.keywords
                    if kw.arg is None]
        assert splatted == ["execution or {}"], (
            "_use_policy_action reaches run_policy_step at line %d splatting "
            "%r rather than the `execution` it was handed. Rebuilding the "
            "dictionary at the call site is how a key gets dropped."
            % (node.lineno, splatted))


# --- Z2-03: a migration count is a property of the tree -------------------


def _pinned_migration_counts(tree: ast.Module) -> list[tuple[int, int]]:
    """Comparisons of a migration count against a written-down integer.

    The predicate has to name the migration count, not merely any integer in an
    `==`. The original guard matched the second, which is why it reported
    eleven ordinary assertions (`len(found) == 1`, `settled == 0`) and stayed
    red after the count it cared about had been un-pinned.
    """
    hits: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        try:
            left = ast.unparse(node.left)
        except Exception:
            continue
        if "migration" not in left.lower():
            continue
        for op, comparator in zip(node.ops, node.comparators):
            if not isinstance(op, (ast.Eq, ast.Gt, ast.Lt, ast.GtE, ast.LtE)):
                continue
            if isinstance(comparator, ast.Constant) \
                    and isinstance(comparator.value, int) \
                    and not isinstance(comparator.value, bool):
                hits.append((node.lineno, comparator.value))
    return hits


def test_no_test_pins_the_migration_count_as_a_literal():
    """A schema version is a property of the tree, not of a test.

    Two migrations landed in the batch and a literal written before them
    re-broke `tests/test_s09_run_isolation.py` twice. It now defines
    `expected_migrations()`, which reads the same directory glob
    `apply_migrations` reads, and both call sites use it.

    The guard's substance outlives the file it was written about, so it scans
    the whole test tree. What would fail here is a store built from the wrong
    directory or a migration that failed to record itself, not the arrival of
    a new `.sql` file.
    """
    pinned = {}
    for path in _test_files():
        try:
            hits = _pinned_migration_counts(_parsed(path))
        except SyntaxError as exc:
            pinned.setdefault("unparseable", []).append(
                "%s: %s" % (path.name, exc))
            continue
        if hits:
            pinned[path.name] = hits

    assert not pinned, (
        "these tests compare a migration count to a literal: %r. The count is "
        "a property of the tree and moves with every migration. Derive it "
        "from the migrations directory instead of writing it down."
        % (pinned,))


# --- Z2-04: a deleted private is named, never loaded ----------------------


def _loaded_names(tree: ast.Module) -> set[str]:
    """Every identifier the code actually loads, plus its attribute names.

    Docstrings and comments are excluded by construction: a `Constant` string
    is the only place prose reaches, and prose is not a load. This is the
    distinction the C14 gate draws for its own subject.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def test_the_e4_remediation_fixture_loads_no_private_a_repair_deleted():
    """`_substrate_with_a_real_effect` must not reach into a deleted private.

    `7c7b335` deleted `_STRATEGY_EVIDENCE` from
    `experiments/ad01/improve_channel.py`. The fixture used to copy it, so it
    raised `AttributeError` and took two E4 remediation tests with it. That
    call site is gone.

    What is left is the docstring at `tests/test_s09_e4_remediation.py:138`,
    which names the symbol to explain what replaced it and why
    (`construction_from_evidence`, at `improve_channel.py:879`). That prose is
    the documentation the finding wanted kept, so it is allowed here and only
    here. The original guard matched the substring anywhere in a line, so it
    matched the explanation and reported a repair as a defect.
    """
    deleted = "_STRATEGY_EVIDENCE"

    import experiments.ad01.improve_channel as channel

    assert not hasattr(sys.modules[channel.__name__], deleted), (
        "improve_channel carries a %s again, so the E4 remediation fixture "
        "binds again and this finding is stale" % deleted)

    path = ROOT / "tests/test_s09_e4_remediation.py"
    tree = _parsed(path)

    assert deleted not in _loaded_names(tree), (
        "%s loads %s, which the C4 repair deleted. Re-aim it through the "
        "construction path that installs the probe inputs now."
        % (path.name, deleted))

    source = path.read_text(encoding="utf-8")
    mentions = [n for n, line in enumerate(source.splitlines(), 1)
                if deleted in line]
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(node, clean=False)
            if doc and deleted in doc:
                docstrings.update(range(node.body[0].lineno,
                                        node.body[0].end_lineno + 1))
    unaccounted = [n for n in mentions if n not in docstrings]
    assert not unaccounted, (
        "%s mentions %s at %r outside a docstring. A mention in prose is how "
        "a removal is explained; a mention anywhere else is how a deleted "
        "name comes back." % (path.name, deleted, unaccounted))
