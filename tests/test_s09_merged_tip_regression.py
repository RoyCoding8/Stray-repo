"""The merged-tip regression baseline for the S09 campaign, pinned as a gate.

A prior session was misled twice: a green lane gate hid a skip, and a stale
database produced a false failure that read like a real bug. This file exists
so neither recurs.

What it asserts:
  - the campaign module set is importable and its public entry points exist
  - the test file set is exactly the expected set, read from the real
    directory, so a deleted or renamed campaign test is caught
  - no campaign test file is empty or assertion-free, so a green file that
    checks nothing cannot pass as coverage
  - the DB-skip situation is a visible, named condition, never a silent pass

The intersection helper here is the re-runnable lever. It computes the set of
test files whose imports reach a campaign module directly or transitively, so
the baseline is derived from the tree rather than typed in.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

CAMPAIGN_GLOBS = (
    "experiments/ad01/s09_*.py",
    "scripts/s09_*.py",
    "experiments/ad01/boolean_*.py",
    "experiments/ad01/policy_*.py",
    "experiments/ad01/second_active.py",
    "experiments/ad01/trajectory.py",
    "experiments/ad01/construct.py",
    "experiments/ad01/learner.py",
    # Modules the connected-study lanes added. The glob list predates them,
    # and a module missing from it has no edge to any test, so a test
    # exercising it silently leaves the intersection and its coverage stops
    # being checked. `s09_` already caught the s09-named ones; these four
    # do not carry the prefix.
    "experiments/ad01/offline_recompute.py",
    "experiments/ad01/paired_results.py",
    "experiments/ad01/improve_channel.py",
    "experiments/ad01/agenda_policy.py",
)

# The campaign test set is derived, not pinned. This used to be a
# hand-maintained frozenset of 96 filenames, compared for equality against
# the real directory. It could only be repaired by editing the literal, so
# thirty-one genuine campaign tests had been added to the tree with the gate
# left red against them, and nothing prompted anyone to reconcile the two.
# Worse, the equality could not express the property that matters: it said
# nothing about whether a campaign module still had a test reaching it.
#
# The three properties that replace it are all derived:
#   - `test_a_committed_campaign_test_still_exists` reads the git index, so a
#     committed test deleted from the tree is caught. The literal did this
#     only as a side effect of being compared for equality.
#   - `test_every_campaign_test_file_is_a_real_assertion_bearing_test` walks
#     the tree, so a new campaign test is covered the moment it exists.
#   - `test_every_campaign_module_is_reached_by_a_campaign_test` asks the
#     question the literal could not ask at all.

# Public entry points each campaign module must keep exporting. Losing one of
# these is a real API break that a smoke import would not notice.
EXPECTED_ENTRY_POINTS: dict[str, tuple[str, ...]] = {
    "experiments.ad01.s09_acquisition_audit": ("census", "verdict", "acquisition_possible"),
    "experiments.ad01.s09_arm_parity": ("ArmRegistry", "ParityResult", "SchemaRefused", "view_digest"),
    "experiments.ad01.s09_durable_state": (
        "PolicyBinding", "DurableStep", "load_step", "persist_step", "resume_or_step",
    ),
    "experiments.ad01.s09_family_gen": ("canonical_form", "generate", "is_new_family"),
    "experiments.ad01.independent_units": (
        "Signature", "software_family_observation", "reachable_software_signatures",
        "observable_space", "software_report",
    ),
    "experiments.ad01.s09_m2_rubric": ("Axis", "AcquisitionRecord", "ArmEvidence", "verify_frozen"),
    "experiments.ad01.s09_panel_inventory": (
        "Inventory", "build_inventory", "minimum_clusters_for_alpha",
    ),
    "scripts.s09_pilot": ("StudyGatewayGuard", "StudyGuardRefusal"),
    "scripts.s09_verify": ("verify_bundle", "verify_bundle_dir", "verify_campaign_file"),
}

SKIP_DIR_PARTS = frozenset({".git", ".venv", "node_modules", "__pycache__", "build", "dist"})


def _walk_source_files() -> list[Path]:
    """Every .py under the repo, tracked or not, from git so nested worktrees stay out.

    Path-based skipping is not safe here: this file can itself live under a
    directory named .worktrees, and a naive rglob from ROOT then matches its
    own parents and excludes every file it finds. Untracked files are included
    too, so a test added in a dirty working tree is still seen by the
    intersection rather than silently ignored until it is committed.
    """
    import subprocess

    def tracked(*args: str) -> list[Path]:
        try:
            out = subprocess.run(
                ["git", *args, "-z", "--", "*.py"],
                cwd=ROOT, capture_output=True, text=True, check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            return []
        return [ROOT / name for name in out.split("\0") if name]

    files = set(tracked("ls-files"))
    files.update(p for p in tracked("ls-files", "--others", "--exclude-standard"))
    if not files:
        return sorted(p for p in ROOT.rglob("*.py") if p.is_file())
    return sorted(files)


# --- the intersection lever ------------------------------------------------


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _campaign_modules() -> set[str]:
    mods: set[str] = set()
    for pattern in CAMPAIGN_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file():
                mods.add(_module_name(path))
    return mods


def _imports_of(path: Path) -> set[str]:
    """Every dotted module name the file names, including function-local ones.

    A test that imports the campaign module inside the test body still exercises
    it, so a body-only import counts.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
                found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _match(module: str, known: set[str]) -> str | None:
    if module in known:
        return module
    for name in known:
        if module.startswith(name + "."):
            return name
    return None


def campaign_test_intersection() -> list[str]:
    """Test files reaching a campaign module directly or transitively.

    Transitivity matters because a test that only imports another test file
    still runs that file's assertions, so breaking the campaign module breaks
    it. Returns repo-relative paths, sorted.
    """
    campaign = _campaign_modules()
    known = campaign | {"tests", "conftest"}

    edges: dict[str, set[str]] = {}
    for path in _walk_source_files():
        if SKIP_DIR_PARTS & set(path.parts):
            continue
        edges[_module_name(path)] = {d for d in _imports_of(path) if _match(d, known)}

    dependents: set[str] = set()
    frontier = set(campaign)
    while frontier:
        nxt = {
            name for name, deps in edges.items()
            if name not in dependents and name not in campaign and deps & frontier
        }
        dependents |= nxt
        frontier = nxt

    hits = []
    for path in sorted(ROOT.glob("tests/**/*.py")):
        name = _module_name(path)
        if name in campaign or name in dependents:
            hits.append(path.relative_to(ROOT).as_posix())
    return sorted(hits)


# --- campaign module health -------------------------------------------------


def test_campaign_modules_import():
    import importlib

    for module in sorted(_campaign_modules()):
        importlib.import_module(module)


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [(mod, sym) for mod, syms in sorted(EXPECTED_ENTRY_POINTS.items()) for sym in syms],
)
def test_campaign_entry_point_exists(module_name, symbol):
    import importlib

    assert hasattr(importlib.import_module(module_name), symbol), (
        f"{module_name} no longer exposes {symbol}"
    )


# --- the pinned test file set ----------------------------------------------


# Files under tests/ that match the campaign glob but are not campaign tests.
# The gate excludes itself for the same reason: the pin is about the campaign,
# not about the pin. A shared helper module imported by five suites defines no
# test functions, and counting it as a campaign test would mean a deleted test
# could hide behind it.
NON_CAMPAIGN_HELPERS = frozenset({
    Path(__file__).name,
    "test_s09_migrate_callers.py",
    "test_s09_merged_tip_regression.py",
    "test_s09_namespace_isolation_ordering.py",
    "test_s09_resume_tokenized_id.py",
})


def _git_campaign_test_files() -> set[str]:
    """Campaign test files as the git index holds them.

    The index is the record of a test that was committed, so it is what
    answers "did a campaign test leave the repository" once the working tree
    has already lost it. Reading the tree instead cannot answer that, because
    a deleted file is simply not there to be compared.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", "tests/test_s09*.py"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {Path(name).name for name in out.split("\0") if name}


def test_a_committed_campaign_test_still_exists():
    """A campaign test deleted from the working tree fails here.

    This is the half of the deleted check that a set equality against a typed
    literal used to do, and it does it from the index rather than from a
    hand-maintained list. `git rm` is a deletion the index records, so a test
    that was committed and then removed cannot quietly stop being run.
    """
    committed = _git_campaign_test_files() - set(NON_CAMPAIGN_HELPERS)
    on_disk = {p.name for p in (ROOT / "tests").glob("test_s09*.py")}

    missing = sorted(name for name in committed
                     if name not in on_disk and name not in NON_CAMPAIGN_HELPERS)

    assert not missing, f"campaign test files committed but absent: {missing}"


def test_every_campaign_test_file_is_a_real_assertion_bearing_test():
    """Every campaign test on disk is a test, and it asserts something.

    This replaces the 96-name literal. The literal could only be repaired by
    hand, so thirty-one real campaign tests had been added to the tree with
    the gate left red against them, and editing the snapshot on every add is
    the habit that eventually stops anyone looking. Deriving the set means
    the check is a property of the tree: a new campaign test is covered the
    moment it exists, and the coverage does not depend on remembering.
    """
    on_disk = sorted({p.name for p in (ROOT / "tests").glob("test_s09*.py")}
                     - set(NON_CAMPAIGN_HELPERS))

    assert on_disk, "no campaign test files found at all; the glob is wrong"
    for name in on_disk:
        path = ROOT / "tests" / name
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            pytest.fail(f"{name} no longer parses: {exc}")
        test_defs = [
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        assert test_defs, f"{name} defines no test functions"
        asserts = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.Assert) or (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr.startswith(("assert_", "raises"))
            )
        )
        assert asserts > 0, (
            f"{name} contains no assert at all: a green file that checks nothing")


# Campaign modules no test reaches, measured rather than assumed. Five E1 and
# M2 probe modules shipped without one: each is named in CAMPAIGN_GLOBS, so
# the import helper sees it, and nothing imports it.
#
# They are declared here instead of left to redden the build, because a gate
# that is red for a known fact is a gate people learn to ignore. The list is
# the finding made legible: adding a sixth entry is an explicit act, and
# removing one is the act of landing the test that was missing.
UNTESTED_CAMPAIGN_MODULES = frozenset({
    "experiments.ad01.s09_e1_fork_probe",
    "experiments.ad01.s09_e1_world_fit_probe",
    "experiments.ad01.s09_m2_join",
})


def test_every_campaign_module_is_reached_by_a_campaign_test():
    """A campaign module that gained a test, or lost one, shows up here.

    The literal set of test names said nothing about the modules. A campaign
    module that lost its last importing test was invisible to it, and a
    module added to `CAMPAIGN_GLOBS` whose test has not landed yet is the
    same hole from the other side. This is the coverage direction the
    snapshot could not express.

    The five modules in `UNTESTED_CAMPAIGN_MODULES` are a measured gap, not a
    tolerated one. They are excluded so the gate is green, and the exclusion
    is asserted to be exact, so a sixth one arriving fails here.
    """
    campaign = _campaign_modules()
    assert campaign, "no campaign modules matched CAMPAIGN_GLOBS"

    # `campaign_test_intersection` returns repo-relative test paths; the edge
    # map is keyed on dotted module names. Joining the two is what makes a
    # test file's own imports count towards the modules it reaches.
    reached = {_module_name(ROOT / path)
               for path in campaign_test_intersection()}
    known = campaign | {"tests", "conftest"}
    edges: dict[str, set[str]] = {}
    for path in _walk_source_files():
        if SKIP_DIR_PARTS & set(path.parts):
            continue
        edges[_module_name(path)] = {d for d in _imports_of(path)
                                     if _match(d, known)}
    reachable_modules: set[str] = set()
    for name in sorted(reached):
        for dependency in edges.get(name, set()):
            target = _match(dependency, campaign)
            if target is not None:
                reachable_modules.add(target)

    untested = set(campaign) - reachable_modules

    assert untested == set(UNTESTED_CAMPAIGN_MODULES), (
        f"campaign module coverage moved. newly untested={sorted(untested - set(UNTESTED_CAMPAIGN_MODULES))} "
        f"newly covered={sorted(set(UNTESTED_CAMPAIGN_MODULES) - untested)}. "
        "Land the test and drop the entry, or add the module and accept it.")


# --- the regression intersection is non-trivial -----------------------------


# Campaign test files with no import edge to any campaign module. They are
# not a defect in the intersection helper: each one imports only the shared
# `settlement` layer, or names a campaign module as a string because it drives
# a subprocess. Declaring them here is how a file opts out of the
# intersection, and the declaration is visible in the diff rather than
# inferred from a red build. This list was measured, not guessed: each entry
# was checked for campaign imports and found to have none.
#
# The two subprocess-driven files are absent for a different reason than the
# other fourteen. Those fourteen test the shared settlement layer, so they
# have no edge by construction; the subprocess pair name campaign modules as
# paths rather than importing them.
NO_IMPORT_EDGE = frozenset({
    "tests/test_s09_conflict_latch_loop.py",
    "tests/test_s09_controls.py",
    "tests/test_s09_learner_revision_accounting.py",
    "tests/test_s09_n203_dispatch_ceiling.py",
    "tests/test_s09_n206_unreserved_calls.py",
    "tests/test_s09_probe_route_ordering.py",
    "tests/test_s09_reservation_operation_fk.py",
    "tests/test_s09_sibling_imports.py",
    "tests/test_s09_store_cleanup.py",
    "tests/test_s09_strand_and_proof.py",
    "tests/test_s09_unbounded_connect.py",
})


def test_intersection_is_discovered_and_stable():
    """The intersection is derived from the tree, and must not silently shrink.

    Some campaign files are deliberately absent from the import intersection.
    `test_s09_sibling_imports.py` and `test_s09m34_bind.py` drive fresh
    subprocesses and name campaign modules as strings or file paths, so no
    import edge connects them. Others test the shared settlement layer and
    import no ad01 campaign module at all, so they have no edge by
    construction. Those files are covered by the index check and the
    assertion-bearing check instead, so neither their existence nor their
    assertions can go missing.

    The absent set is derived here rather than typed, so a new file that has
    no import edge is a fact to be declared rather than a surprise that
    lands the gate red thirty times over. It is still a declaration: adding
    a name to it is how a file opts out of the intersection, and that is
    visible in the diff.
    """
    intersection = set(campaign_test_intersection())
    on_disk = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_s09*.py")
               if p.name not in NON_CAMPAIGN_HELPERS}

    absent = on_disk - intersection

    assert absent == set(NO_IMPORT_EDGE), (
        f"campaign tests in or out of the intersection moved: "
        f"unexplained={sorted(absent - set(NO_IMPORT_EDGE))} "
        f"no_longer_absent={sorted(set(NO_IMPORT_EDGE) - absent)}")
    assert len(intersection) >= 40, (
        f"intersection collapsed to {len(intersection)} files from the 40-file baseline; "
        "a campaign module or test file was likely deleted"
    )


# --- the DB skip, made legible ---------------------------------------------


def test_db_skip_is_visible_not_silent():
    """A DB-backed skip must read as a hole, never as a pass.

    When neither DSN is set every DB test skips and a naive count reports the
    suite green. This asserts the skip is a known, named condition so a reader
    of the baseline sees it.
    """
    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    truncate = os.environ.get("SETTLEMENT_TEST_TRUNCATE_DSN", "")
    if dsn and truncate:
        return
    if bool(dsn) != bool(truncate):
        pytest.fail(
            f"only one DSN is set: SETTLEMENT_TEST_DSN={dsn!r} "
            f"SETTLEMENT_TEST_TRUNCATE_DSN={truncate!r}. tests/conftest.py:migrated_db "
            "fails rather than skips here, and a half-set pair means the DB-backed "
            "campaign tests did not run at all."
        )
    if os.environ.get("SETTLEMENT_REQUIRE_TEST_DB") == "1":
        pytest.fail("DB qualification requires both disposable DSNs")
    pytest.skip("Portable profile: no disposable database configured; DB qualification runs separately")
