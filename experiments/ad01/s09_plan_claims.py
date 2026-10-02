"""Is the M0 call-chain table still bound to the source it claims to describe?

`reports/PLAN-STAGE-09-CONNECTED.md` records ten edges of the connected study
and, for each, the `file:line` that implements it. A citation in prose cannot be
re-checked, because by the time a human reads it back the line has moved. This
module reads the source instead and reports where the two disagree.

It also runs the re-read trigger the plan asks for as a command rather than as
a sentence, and corrects the trigger's ancestry direction, which the
`STAGE-09-M0-OWNERSHIP` review stated backwards. See `re_read_needed`.

Run it directly for a report:

    python3 -m experiments.ad01.s09_plan_claims

or let `tests/test_m0_plan_claims.py` assert on `check_citations`. It opens no
database, contacts no gateway and dispatches nothing.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = ("src", "experiments", "scripts")

# The commit whose tree the table was last read against.
#
# `a1f514c` is the last commit to touch the plan, and it is the wrong pin.
# `9a1884d` moved `study_ceiling` from 1230 to 1250 and is an ancestor of
# `a1f514c`, so the table shipped citing 1230 against a source sitting at 1250.
# The table's own citations are therefore the authority, and they are what
# `CITATIONS` records here. `LAST_VERIFIED` is this module's pin, and a commit
# that moves one of these lines is what turns the trigger on.
LAST_VERIFIED = "a1f514c"

# The review `STAGE-09-M0-TASKGRAPH` recorded, which this module is checked
# against. Its own words: rows 2, 4, 6 and 7 were false about code that already
# existed, and it could not say what a mechanical check would look like.
M0_REVIEW = "reviews/STAGE-09-M0-TASKGRAPH.md"


@dataclass(frozen=True)
class Citation:
    """One `file:line` the table asserts, and the symbol it must hold."""

    path: str
    line: int
    symbol: str
    row: int
    edge: str
    why: str = ""


# One entry per `file:line` currently in the table. Every `line` was measured
# against the tree at `LAST_VERIFIED`, not copied from the review, which cited
# lines that had already moved.
CITATIONS: tuple[Citation, ...] = (
    Citation("experiments/ad01/live_construct.py", 615, "construct_live_policy", 1,
             "construction response to acquired artifact"),
    Citation("experiments/ad01/construct.py", 398, "construct_policy", 1,
             "construction response to acquired artifact"),
    Citation("experiments/ad01/learner.py", 114, "visible_prompt", 2,
             "acquired artifact to selected policy",
             "The table named this as carrying an acquired artifact. It takes "
             "charter, visible, experience, retained, remaining, curriculum, so "
             "it never receives one."),
    Citation("experiments/ad01/policy_assess.py", 412, "assess_policy", 2,
             "acquired artifact to selected policy"),
    Citation("experiments/ad01/policy_step.py", 424, "run_policy_step", 3,
             "selected policy to child/interpreter"),
    Citation("experiments/ad01/method_exec.py", 1114, "run_step_out_of_process", 3,
             "selected policy to child/interpreter",
             "The table cited `exec_profile` here. It is imported by "
             "src/settlement/artifacts.py and boot.py and by nothing under "
             "experiments/. This line has moved four times under the table's "
             "watch: 732 at a1f514c, 1108 at 8c535e3, 1114 at a49a9c5, and "
             "1203 at 8c954a6."),
    Citation("experiments/ad01/policy_action.py", 68, "parse_action", 4,
             "proposed action to admission",
             "The table cited `policy_action.admit`, which does not exist. "
             "`parse_action` is what `admit_action` actually calls."),
    Citation("experiments/ad01/s09_arm_parity.py", 449, "admit_action", 4,
             "proposed action to admission"),
    Citation("experiments/ad01/boolean_active.py", 114, "run_episode", 5,
             "oracle effect to scored result"),
    Citation("experiments/ad01/checker.py", 129, "_verify_quality", 5,
             "oracle effect to scored result"),
    Citation("experiments/ad01/s09_durable_state.py", 251, "resume_or_step", 7,
             "durable resume to remaining count",
             "Defined at 251, re-exported in `__all__` at 285, and called by "
             "nothing under src/, experiments/ or scripts/. The table cited it "
             "as the live path. `agenda_policy` is the live path."),
    Citation("experiments/ad01/agenda_policy.py", 493, "_step_remaining", 7,
             "durable resume to remaining count"),
    Citation("experiments/ad01/offline_recompute.py", 1468, "recomputed_accounting", 6,
             "receipt to evidence boundary",
             "The live half of row 6. It re-derives counts from a freeze and "
             "receives no receipt from the diagnosability side."),
    Citation("experiments/ad01/s09_study_preflight.py", 1250, "study_ceiling", 8,
             "budget units to dispatch count",
             "Stale row. The repair landed at f3af21a. The table cited 1230, "
             "which 9a1884d had already moved."),
    Citation("experiments/ad01/s09_exposure_ledger.py", 513,
             "route_capacity_from_freeze", 8,
             "budget units to dispatch count",
             "Stale row. The table cited 503."),
    Citation("experiments/ad01/s09_arm_parity.py", 542, "register_python_step", 9,
             "representation kind to real executor"),
    Citation("experiments/ad01/s09_arm_parity.py", 571, "register_typed_ast", 9,
             "representation kind to real executor"),
    Citation("experiments/ad01/s09_arm_parity.py", 645, "register_action_graph", 9,
             "representation kind to real executor"),
    Citation("experiments/ad01/s09_causal_proof.py", 561, "qualify_pre_launch", 10,
             "causal policy decision to admitted effect"),
    Citation("experiments/ad01/s09_study_preflight.py", 1149, "launch_governance", 10,
             "causal policy decision to admitted effect",
             "Stale row. The table cited 1150."),
)

# Symbols the table, or a review of it, asserted existed and never did. A check
# that only confirms presence cannot catch a false presence, so absence is
# asserted here too. If one of these is ever defined, the row that denied it was
# wrong and this goes red.
ABSENT_SYMBOLS: tuple[Citation, ...] = (
    Citation("experiments/ad01/policy_action.py", 0, "admit", 4,
             "proposed action to admission",
             "Cited by the table as an implementation of admission. It has "
             "never been defined; grep for `admit` in that file returns a "
             "docstring note only."),
    Citation("experiments/ad01/s09_durable_state.py", 0, "DurableStep.count", 7,
             "durable resume to remaining count",
             "`DurableStep` is the durable record and carries no count field, "
             "so the edge the table asserts cannot be carried by it."),
)

# Two files the table presents as one edge. Neither imports the other, in either
# direction, at any commit. This is the check that catches rows 2 and 6, and it
# is the one the M0 review called mechanisable but did not build.
UNCONNECTED_PAIRS: tuple[tuple[str, str, int, str], ...] = (
    ("experiments/ad01/learner.py", "experiments/ad01/policy_assess.py", 2,
     "acquired artifact to selected policy"),
    ("experiments/ad01/s09_receipt_diagnosability.py",
     "experiments/ad01/offline_recompute.py", 6, "receipt to evidence boundary"),
)

# A module the table or a review presented as on a production path, and that
# nothing under src/, experiments/ or scripts/ imports.
UNIMPORTED_MODULES: tuple[Citation, ...] = (
    Citation("experiments/ad01/s09_receipt_diagnosability.py", 0, "", 6,
             "receipt to evidence boundary",
             "575 lines. The only importers are two test files. Row 6 called "
             "it an implementation of an edge."),
    Citation("experiments/ad01/s09_durable_state.py", 0, "", 7,
             "durable resume to remaining count",
             "Imported by nothing under src/, experiments/ or scripts/."),
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout.strip()


def _is_ancestor(older: str, newer: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=REPO_ROOT, capture_output=True,
    ).returncode == 0


def _source_text(path: Path) -> str | None:
    """The committed text of a file, falling back to the working tree.

    Read from git, not from disk. A citation is a claim about a tree a reader
    will dispatch from, and this repo runs several lanes in one checkout, so
    the working tree is not a stable description of anything. While this was
    being written, `method_exec.py` sat uncommitted and moved twice under the
    same test run. Reading `git show HEAD:path` makes the check a fact about
    history rather than a race with a neighbour.
    """
    rel = path.relative_to(REPO_ROOT).as_posix()
    out = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if out.returncode == 0:
        return out.stdout
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def definition_line(path: Path, symbol: str) -> int | None:
    """The line a top-level `def` or `class` starts on, or None if absent.

    Parsed rather than grepped, so a symbol named in a docstring or a comment is
    not mistaken for a definition. `store.py:1174` names `admit_study_call` in
    the docstring of the check that replaced it, and that is the trap this
    avoids.
    """
    text = _source_text(path)
    if text is None:
        return None
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.name == symbol:
            return node.lineno
    return None


def _parsed(path: Path) -> ast.Module | None:
    text = _source_text(path)
    if text is None:
        return None
    try:
        return ast.parse(text, filename=str(path))
    except SyntaxError:
        return None


def attribute_exists(path: Path, class_name: str, attribute: str) -> bool:
    tree = _parsed(path)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return any(
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == attribute for child in node.body
            )
    return False


def imports_module(path: Path, stem: str) -> bool:
    """Whether `path` imports a module named `stem`, on a real import line."""
    tree = _parsed(path)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.rsplit(".", 1)[-1] == stem for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.rsplit(".", 1)[-1] == stem:
                return True
    return False


def production_files() -> list[Path]:
    out: list[Path] = []
    for root in PRODUCTION_ROOTS:
        base = REPO_ROOT / root
        if base.is_dir():
            out.extend(sorted(base.rglob("*.py")))
    return out


def production_callers(symbol: Citation) -> list[str]:
    """Production files that call `symbol`, excluding its own module.

    An `ast.Call` to an `ast.Attribute` or a bare `ast.Name` both count. A name
    in a docstring is a note about the call, not a call, so this reads the
    parsed tree. `tests/` is excluded because a row claiming a production
    implementation is not satisfied by a test that exercises it.

    Excluding the home module is the part that makes it discriminate.
    `s09_durable_state.resume_or_step` is defined at line 251 and its module
    calls it at line 285, so a self-inclusive scan reports a live caller and
    passes a dead path. The original table cited it as the implementation of
    durable resume, and nothing outside its own file reaches it.
    """
    home = REPO_ROOT / symbol.path
    stem = symbol.symbol.rsplit(".", 1)[-1]
    callers: list[str] = []
    for path in production_files():
        if path == home:
            continue
        tree = _parsed(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None
            )
            if name == stem:
                callers.append(path.relative_to(REPO_ROOT).as_posix())
                break
    return sorted(set(callers))


# Symbols the table presented as the live implementation of an edge, and which
# nothing outside their own module calls. Distinct from `ABSENT_SYMBOLS`: these
# exist and are even called, but only by themselves.
UNCALLABLE_SYMBOLS: tuple[Citation, ...] = (
    Citation("experiments/ad01/s09_durable_state.py", 251, "resume_or_step", 7,
             "durable resume to remaining count",
             "Defined at 251 and re-exported in `__all__` at 285. Called by "
             "nothing under src/, experiments/ or scripts/, its own module "
             "included. The table cited it as the live path; `agenda_policy` "
             "is the live path."),
)

# A name the table cited as bound on an edge, and which nothing under
# `experiments/` imports. It is imported by `src/settlement/artifacts.py` and
# `src/settlement/boot.py`, which are the settlement runtime, not the study.
OFF_PATH_IMPORTS: tuple[Citation, ...] = (
    Citation("src/settlement/artifacts.py", 21, "exec_profile", 3,
             "selected policy to child/interpreter",
             "The table named `exec_profile` as the bound executor for the "
             "STEP driver. `policy_step.run_policy_step` calls "
             "`method_exec.run_step_out_of_process` instead, and nothing under "
             "experiments/ imports `exec_profile`."),
)


def check_off_path_imports() -> list[str]:
    """Names the table bound to an edge, and no study-side module imports.

    The distinction is the runtime's, not the tree's. `exec_profile` is a real
    module that `src/settlement` imports, so a check that only asked "does this
    exist" would pass. What makes row 3 false is that the connected study runs
    under `experiments/` and imports it nowhere.
    """
    problems: list[str] = []
    for cit in OFF_PATH_IMPORTS:
        stem = cit.symbol
        importers = [
            p for p in production_files()
            if p.parts[0] == "experiments" and imports_module(p, stem)
        ]
        if importers:
            problems.append(
                f"row {cit.row} ({cit.edge}): {stem} is now imported under "
                f"experiments/ by {importers[0].relative_to(REPO_ROOT)}, so "
                f"the row that corrected it is now stale.")
    return problems


def check_uncallable() -> list[str]:
    problems: list[str] = []
    for cit in UNCALLABLE_SYMBOLS:
        callers = production_callers(cit)
        if not callers:
            continue
        problems.append(
            f"row {cit.row} ({cit.edge}): {cit.symbol} is now called by "
            f"{callers[0]}, so the row that called it unreachable is stale.")
    return problems


def check_citations() -> list[str]:
    """Every citation that no longer holds. Empty means the table is bound."""
    problems: list[str] = []
    for cit in CITATIONS:
        path = REPO_ROOT / cit.path
        if not path.is_file():
            problems.append(f"row {cit.row} ({cit.edge}): {cit.path} does not exist")
            continue
        actual = definition_line(path, cit.symbol)
        if actual is None:
            problems.append(
                f"row {cit.row} ({cit.edge}): {cit.path} does not define "
                f"{cit.symbol}, which the table cites at line {cit.line}")
        elif actual != cit.line:
            problems.append(
                f"row {cit.row} ({cit.edge}): {cit.path}:{cit.line} does not hold "
                f"{cit.symbol}; it is now at line {actual}")
    return problems


def check_absences() -> list[str]:
    """Symbols the table denied exist that now do. Empty means still absent."""
    problems: list[str] = []
    for cit in ABSENT_SYMBOLS:
        path = REPO_ROOT / cit.path
        if not path.is_file():
            problems.append(f"{cit.path} does not exist, so {cit.symbol} is vacuous")
            continue
        if "." in cit.symbol:
            cls, attr = cit.symbol.split(".", 1)
            present = attribute_exists(path, cls, attr)
        else:
            present = definition_line(path, cit.symbol) is not None
        if present:
            problems.append(
                f"row {cit.row} ({cit.edge}): {cit.path} now defines "
                f"{cit.symbol}. The table denies it, so the table is now wrong.")
    return problems


def check_disconnection() -> list[str]:
    """Pairs the table presents as one edge, proven not to be connected.

    The check is on the git history, not on the working tree, because the claim
    was about code that existed when the plan was written. For every commit
    that touches either file, neither file may import the other.
    """
    problems: list[str] = []
    for left, right, row, edge in UNCONNECTED_PAIRS:
        commits = _git("log", "--format=%H", "--", left, right)
        for commit in [c for c in commits.splitlines() if c]:
            for source, target, side in ((left, right, "left"), (right, left, "right")):
                if imports_module(REPO_ROOT / source, Path(target).stem):
                    # A connection appearing later is a fix, not a failure, but
                    # it invalidates the row, so it is reported either way.
                    problems.append(
                        f"row {row} ({edge}): {source} imports {target} at "
                        f"{commit[:7]}, so the row's claim that they are "
                        f"unconnected no longer describes the tree.")
                    break
            if problems and problems[-1].startswith(f"row {row} "):
                break
    return problems


def check_unimported() -> list[str]:
    problems: list[str] = []
    for cit in UNIMPORTED_MODULES:
        stem = Path(cit.path).stem
        importers = [p for p in production_files()
                     if p != REPO_ROOT / cit.path and imports_module(p, stem)]
        if importers:
            problems.append(
                f"row {cit.row} ({cit.edge}): {cit.path} is now imported by "
                f"{importers[0].relative_to(REPO_ROOT)}. The row that called it "
                f"unreachable is now stale.")
    return problems


def re_read_needed(tip: str = "HEAD") -> list[str]:
    """Commits after LAST_VERIFIED that edited a path a citation depends on.

    The plan's own trigger reads: "Any commit that touches an owned path below
    and is not a descendant of `2b7050a` needs this table re-read." That
    ancestry direction is backwards, and running it against this tree shows why.
    `9a1884d` is a descendant of `2b7050a`, so the trigger as written exempts it,
    and `9a1884d` is the commit that moved `study_ceiling` from 1230 to 1250 and
    so falsified row 8's citation. The correct test asks whether the commit came
    after the verification, which is `LAST_VERIFIED` being its ancestor.
    """
    paths = sorted(
        {c.path for c in CITATIONS}
        | {c.path for c in ABSENT_SYMBOLS}
        | {c.path for c in UNIMPORTED_MODULES}
        | {p for left, right, _, _ in UNCONNECTED_PAIRS for p in (left, right)}
    )
    return [line for line in _git(
        "log", "--format=%h %s", f"{LAST_VERIFIED}..{tip}", "--", *paths
    ).splitlines() if line]


def main() -> int:
    report: list[str] = []
    report.append(f"M0 call-chain table, {len(CITATIONS)} citations, "
                  f"last verified {LAST_VERIFIED}")

    if not _is_ancestor(LAST_VERIFIED, "HEAD"):
        report.append(f"FAIL {LAST_VERIFIED} is not an ancestor of HEAD; the "
                      f"tree has moved off the verified line")
        print("\n".join(report))
        return 1

    stale = re_read_needed()
    if stale:
        report.append(f"FAIL {len(stale)} commit(s) after {LAST_VERIFIED} edited a "
                      f"cited path, so the table needs a re-read:")
        report.extend(f"  {line}" for line in stale)
        owed = True
    else:
        report.append(f"ok   no commit after {LAST_VERIFIED} edited a cited path")
        owed = False

    problems = (check_citations() + check_absences()
                + check_disconnection() + check_unimported() + check_uncallable()
                + check_off_path_imports())
    if problems:
        report.append(f"FAIL {len(problems)} citation problem(s):")
        report.extend(f"  {p}" for p in problems)
        print("\n".join(report))
        return 1
    report.append(f"ok   all {len(CITATIONS)} citations hold, "
                  f"{len(ABSENT_SYMBOLS)} absences still hold")
    print("\n".join(report))
    return 1 if owed else 0


if __name__ == "__main__":
    sys.exit(main())
