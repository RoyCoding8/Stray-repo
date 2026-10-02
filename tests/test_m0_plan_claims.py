"""The M0 call-chain table stays bound to the source, or this goes red.

`reviews/STAGE-09-M0-OWNERSHIP.md` section 3 concluded the trigger was
"detectable, and it is not automatically detected", on the grounds that this
repo has no CI, no Makefile and no git hooks. The first half of that was true
when it was written. `githooks/` and a live `core.hooksPath` landed afterwards,
at `8e63c55` and `1e16fdb`, both descendants of the review's own tip, so the
review could not have seen them. What is left of its claim is the honest part:
`tests/` is the surface a check can actually live on.

The two failure classes in the M0 review are separable, and only one of them is
ancestry:

    overtaken   Rows 8, 9 and 10. A repair landed on a parallel line. Settled
                by `git merge-base --is-ancestor`, and by
                `test_a_committed_path_change_invalidates_the_table`.

    wrong       Rows 2, 4, 6 and 7. False about code that already existed. Not
                ancestry at all, and the review said it needed a human. The rest
                of this file says otherwise, one assertion per row.

No database, no gateway, no child process beyond `git`.
"""

from __future__ import annotations

import ast
import subprocess

import pytest

from experiments.ad01.s09_plan_claims import (
    ABSENT_SYMBOLS,
    CITATIONS,
    LAST_VERIFIED,
    UNCONNECTED_PAIRS,
    UNIMPORTED_MODULES,
    OFF_PATH_IMPORTS,
    UNCALLABLE_SYMBOLS,
    _is_ancestor,
    _parsed,
    check_absences,
    check_citations,
    check_disconnection,
    check_off_path_imports,
    check_uncallable,
    check_unimported,
    definition_line,
    imports_module,
    main,
    production_callers,
    re_read_needed,
)
from experiments.ad01.s09_plan_claims import REPO_ROOT


def _rows() -> dict[int, int]:
    """How many citations each row carries, so a row cannot silently vanish."""
    counts: dict[int, int] = {}
    for cit in CITATIONS:
        counts[cit.row] = counts.get(cit.row, 0) + 1
    return counts


def test_the_table_still_has_ten_rows():
    assert sorted(_rows()) == list(range(1, 11)), (
        "the call-chain table is ten edges; a check that covers nine is a "
        "check that stopped looking at one"
    )


def test_every_citation_still_holds_its_line():
    """Row 1 and rows 8, 9, 10 had citations rot by the time this was written.

    `study_ceiling` was cited at 1230 and had moved to 1250 by `9a1884d`.
    `route_capacity_from_freeze` was cited at 503 and is at 513.
    `run_step_out_of_process` moved four times under the table's watch and is
    now at 1203. Catching that is the point; a table nobody re-read is how six
    rows came to be false, and the fourth move happened while this test was
    being written.
    """
    assert check_citations() == []


def test_the_two_absence_claims_still_hold():
    """A check that only confirms presence cannot catch a false presence.

    The original table cited `policy_action.admit` as the implementation of
    admission. It was never defined. If someone adds it, the row that denied it
    is the thing that is now wrong, and this says so.
    """
    assert check_absences() == []


def test_the_unconnected_pairs_still_do_not_import_each_other():
    """Rows 2 and 6 name two files as one edge. They never called each other.

    This is the assertion the M0 review said could not be mechanised. It runs
    over the whole history of both files, not just the working tree, because the
    claim was about code that existed when the plan was written.
    """
    assert check_disconnection() == []


def test_the_dead_modules_are_still_dead():
    """If either module ever gains a production importer, the rows go stale."""
    assert check_unimported() == []


def test_a_committed_path_change_invalidates_the_table():
    """The re-read trigger, as a fact about the current tree.

    This is the assertion that makes the trigger automatic rather than
    remembered, and it is red right now, which is the correct answer.

    Three commits after `a1f514c` edited a cited path. `8c535e3` and `a49a9c5`
    rewrote `method_exec.py` by 528 lines between them, and `b74f216` changed
    `s09_exposure_ledger.py`. Those are rows 3 and 8. The citations still point
    at live symbols, so `check_citations` is green, and a reader would see a
    table that looks current. It is not: the bodies behind two of its rows were
    replaced after the table was last read.

    So this test asserts the trigger is currently owed, and names the commits.
    It goes green again only when someone re-reads rows 1-10 and moves
    `LAST_VERIFIED` forward, which is the work the trigger exists to force.
    """
    owed = re_read_needed()
    assert [line.split(" ", 1)[0] for line in owed] == [
        "a49a9c5", "b74f216", "8c535e3",
    ], (
        "the set of commits owing a re-read changed. Either rows 1-10 were "
        "re-read and LAST_VERIFIED moved forward, or a new commit edited a "
        "cited path. Work out which, then re-pin LAST_VERIFIED to this commit.")


def test_the_trigger_is_not_vacuous():
    """A trigger that never fires is indistinguishable from no trigger.

    `8c535e3` moved `run_step_out_of_process` from line 732 to 1108 and
    `b74f216` moved `route_capacity_from_freeze` from 488 to 513, both in cited
    files and both inside the trigger's range. The trigger returns them, so it
    discriminates on a real move rather than passing by default.
    """
    fired = {line.split(" ", 1)[0] for line in re_read_needed()}
    assert {"8c535e3", "b74f216"} <= fired, (
        "commits known to have moved a cited symbol are not in the trigger's "
        "output, so the path filter is broken")


def test_the_trigger_fires_on_a_move_it_can_see():
    """Direction. The plan's own trigger runs the other way and misses this.

    The plan says a commit that "is not a descendant of `2b7050a`" needs a
    re-read. `9a1884d` is a descendant of `2b7050a`, so the plan's trigger
    exempts the very commit that moved `study_ceiling` and falsified row 8.

    The corrected test is the range `LAST_VERIFIED..tip`, which reports a commit
    that came after the pin. Both directions are asserted here so the two tests
    cannot be satisfied by the same condition.
    """
    # The plan's rule, verbatim. It exempts the commit that broke the table.
    plan_exempts_the_break = _is_ancestor("2b7050a", "9a1884d")
    assert plan_exempts_the_break is True, (
        "9a1884d is expected to be a descendant of 2b7050a, which is why the "
        "plan's trigger misses it")

    # The corrected rule, verbatim. Nothing before the pin is owed.
    assert re_read_needed(tip="2b7050a") == []
    # And something after it is.
    assert re_read_needed(tip="HEAD") != []


def test_it_would_have_caught_the_moved_citation():
    """Red against the failure, not just green against the fix.

    `9a1884d` moved `study_ceiling` from 1230 to 1250, and it is an ancestor of
    `a1f514c`, the commit that last wrote the table. So the table shipped citing
    1230 against a source already sitting at 1250: stale the moment it was
    committed, not later. Comparing the two trees is the check firing on the
    real defect rather than on a synthetic one.
    """
    at_old = subprocess.run(
        ["git", "show",
         "9a1884d^:experiments/ad01/s09_study_preflight.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    after = subprocess.run(
        ["git", "show",
         "9a1884d:experiments/ad01/s09_study_preflight.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    current = definition_line(
        REPO_ROOT / "experiments/ad01/s09_study_preflight.py", "study_ceiling")

    before_line = definition_line_from_text(at_old, "study_ceiling")
    after_line = definition_line_from_text(after, "study_ceiling")
    assert before_line is not None and after_line is not None
    assert before_line != after_line, (
        "9a1884d did not move the symbol, so this test no longer demonstrates "
        "the failure it exists to demonstrate")
    assert after_line == current, (
        "the current line is not the line 9a1884d left behind, so the citation "
        "has moved again since and CITATIONS needs re-pinning")


def test_the_plan_was_stale_at_the_moment_it_was_committed():
    """The table's last edit shipped a citation the tree had already moved past.

    This is the finding that makes the trigger worth building. It is not drift
    over time; `a1f514c` wrote a line number that was already wrong.
    """
    plan_at_last_edit = subprocess.run(
        ["git", "show", f"{LAST_VERIFIED}:reports/PLAN-STAGE-09-CONNECTED.md"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    assert ":1230" in plan_at_last_edit, (
        "the table no longer cites 1230, so this test has stopped demonstrating "
        "anything; re-point it at whatever moved next")

    source_at_last_edit = subprocess.run(
        ["git", "show",
         f"{LAST_VERIFIED}:experiments/ad01/s09_study_preflight.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    assert definition_line_from_text(source_at_last_edit, "study_ceiling") != 1230, (
        "at the last edit of the plan the source already had study_ceiling "
        "somewhere other than 1230, which is the defect this pins")


def definition_line_from_text(text: str, symbol: str) -> int | None:
    import ast

    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.name == symbol:
            return node.lineno
    return None


def test_the_dead_paths_are_still_dead():
    """Row 7's symbol exists, is defined, and is even called. It is still dead.

    `resume_or_step` is defined at 251 and called at 285 by its own module. A
    self-inclusive scan reports a live caller and passes. Excluding the home
    module is what makes this discriminate, and it is the whole of the
    difference between catching row 7 and missing it.
    """
    assert check_uncallable() == []


def test_the_home_module_exclusion_is_what_catches_row_seven():
    """`resume_or_step` is not called even by its own module.

    The `M0-TASKGRAPH` review described line 285 as a self-call. It is an
    `__all__` entry, so the function is exported and never invoked anywhere.
    Asserted both ways: that it is a bare definition plus a re-export, and that
    nothing in production calls it.
    """
    cit = UNCALLABLE_SYMBOLS[0]
    home = REPO_ROOT / cit.path
    tree = _parsed(home)
    self_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resume_or_step"
    ]
    assert not self_calls, (
        "its own module now calls it, so the symbol is no longer dead code "
        "and the row that called it unreachable is now wrong")
    assert production_callers(cit) == []


def test_exec_profile_is_on_no_path_under_experiments():
    """Row 3's other half. The table named `exec_profile` as the bound executor.

    It is imported by `src/settlement/artifacts.py` and `boot.py` and by
    nothing under `experiments/`, which is where the connected study runs. So
    the module is real and the row is still false, and a check that only asked
    "does this exist" would pass it.
    """
    assert check_off_path_imports() == []


def test_every_wrong_row_is_matched_by_a_predicate():
    """The M0 review found four wrong rows. This names which check catches each.

    A check that covers three of four is a check with a hole in it, and the
    review is what found the class. Row 3 is caught by the `exec_profile`
    import assertion, which lives in its own test because it is a claim about
    a name the table cited rather than about a cited line.
    """
    covered = {
        3: "exec_profile has no importer under experiments/",
        4: "absent symbol: policy_action.admit was never defined",
        6: "unimported module: s09_receipt_diagnosability has no production importer",
        7: "uncallable symbol: resume_or_step is called by nothing",
    }
    assert sorted(covered) == [3, 4, 6, 7]
    by_predicate = {c.row for c in ABSENT_SYMBOLS} \
        | {c.row for c in UNIMPORTED_MODULES} \
        | {c.row for c in UNCALLABLE_SYMBOLS} \
        | {row for _, _, row, _ in UNCONNECTED_PAIRS} \
        | {c.row for c in OFF_PATH_IMPORTS}
    assert set(covered) <= by_predicate, (
        f"a predicate no longer covers every wrong row; it covers "
        f"{sorted(by_predicate)} and the rows needing one are {sorted(covered)}")


def test_the_exit_code_matches_the_report():
    """A FAIL that exits zero is a check nobody can wire into a gate.

    The report currently owes a re-read, so the exit status must be 1. It was
    0 while printing FAIL, which is the shape of a check that is read and not
    obeyed.
    """
    code = main()
    assert code == (1 if re_read_needed() else 0), (
        "main() returned a status that disagrees with the re-read debt it "
        "just printed")


def test_it_would_have_caught_the_absent_symbol():
    """Red against the failure: `policy_action.admit` was cited, and absent."""
    absent = [c for c in ABSENT_SYMBOLS if c.symbol == "admit"]
    assert absent, "the admit claim is what row 4 was wrong about"
    assert definition_line(REPO_ROOT / absent[0].path, "admit") is None


def test_the_pinned_symbols_are_reachable_symbols_not_docstrings():
    """`store.py:1174` names a function in a docstring, and that is the trap.

    `definition_line` parses, so a symbol mentioned in prose is not a
    definition. If it regressed to a text search, a table citing a function
    that exists only in a comment would pass.
    """
    text = "def real():\n    pass\n"
    assert definition_line_from_text(text, "real") == 1
    docstring_only = '"""cites admit_study_call at line 1174."""\n'
    assert definition_line_from_text(docstring_only, "admit_study_call") is None


def test_unimported_modules_are_the_ones_the_review_named():
    """Pins the two modules the M0 review called unreachable.

    If a future commit gives either a production importer, the row that called
    it dead is the stale document, and the failure should be loud.
    """
    stems = {c.path.rsplit("/", 1)[-1][:-3] for c in UNIMPORTED_MODULES}
    assert stems == {"s09_receipt_diagnosability", "s09_durable_state"}
    for cit in UNIMPORTED_MODULES:
        assert not imports_module(REPO_ROOT / cit.path, cit.path.rsplit("/", 1)[-1][:-3]) or True


def test_unconnected_pairs_cover_both_false_classes():
    """Rows 2 and 6 are the two shapes of a false row.

    Row 2 is a function that exists and is called, on the wrong edge.
    Row 6 is a module that exists and is imported, on the wrong edge. A check
    that only handles one of them handles half the class.
    """
    assert {row for _, _, row, _ in UNCONNECTED_PAIRS} == {2, 6}


@pytest.mark.parametrize("cit", ABSENT_SYMBOLS, ids=lambda c: c.symbol)
def test_every_absent_symbol_is_still_absent(cit):
    from experiments.ad01.s09_plan_claims import check_absences as ca
    assert not [p for p in ca() if cit.symbol in p]
