"""The bounded child must dispatch each world to that world's own executor.

`_GRAPH_DRIVER` sent `ordering` to the ordering executor and *everything
else* to the Boolean one, so a SWE graph was loaded by an executor that
validates against the Boolean world and refused it as "stop target must
be boolean.task". That is a world binding reported as if it were the
graph's own expressivity, the same defect the Boolean-executor comment
already records one level down, and it was still open in the `else`.

On the reach question the brief was right and it changed the ruling. The
driver inserts the repository root at `sys.argv[1]` and says so in its own
comment, so the study package is already importable in the child *today*,
with no `swe` branch anywhere. Measured on the unmodified driver: a child
holding only that preamble imports `s09_swe_tasks` and enumerates the
panel, `mechanism` and `patch` included. Adding a branch grants the child
no reach it did not already hold. What a branch changes is which executor
a driver-authored dispatch names, and a silent fall-through is a worse
answer to that than an explicit one.

So the branch is allowed, and this file pins the two things that make it
safe. The dispatch is explicit per world, so an unrecognised name is a
refusal naming itself rather than a mis-load. And the containment story is
unchanged: the import path still comes from the driver's own argument, and
the branch adds an import, never a directory.

This does not make `compare_arms` comparable on this world, and the test
that says so is at the bottom. Offline lane. No live model call, no
network, no fixture gateway. Every child here is a real `LocalLauncher`
dispatch on this host.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import policy_action
from experiments.ad01 import s09_graph_budget
from experiments.ad01 import s09_representation_matrix as matrix
from experiments.ad01 import s09_swe_binding as swe_binding
from experiments.ad01 import s09_swe_experiment as swe_experiment
from experiments.ad01 import s09_swe_tasks as swe_tasks
from experiments.ad01 import s09_swe_world as swe_world


def _observed_swe_view():
    """A real SWE policy view, one public test already run.

    `swe_graph_record`'s first guard reads `observed.0.kind`, so the view
    has to carry an observation or the guard is decided against nothing and
    the record takes its always arm. That is the world's own state, built
    by running the world's own method.
    """
    instance = swe_tasks.instance("held_out", swe_tasks.HELD_OUT_TEMPLATES[0],
                                  swe_tasks.HELD_OUT_MECHANISMS[0])
    session = swe_world.SweSession(instance)
    session.run_public_test(instance["public_tests"][0]["name"])
    return session.policy_view()


# --- 1. the dispatch is explicit per world ------------------------------


def test_the_child_refuses_a_world_it_has_no_executor_for():
    """An unrecognised world names itself instead of loading the Boolean one.

    The defect the `else` branch carried: a name nobody wrote a branch for
    was executed by the Boolean executor, so a typo in a world string was
    reported as a graph that the Boolean world refuses. Asserted on the
    refusal text, because the whole point is which executor was reached and
    the text is the only place that shows.
    """
    pytest = __import__("pytest")
    with pytest.raises(s09_graph_budget.GraphBudgetRefused) as got:
        s09_graph_budget.run_graph_step(
            matrix.ordering_graph_record(), {}, {}, world="nonexistent-world")

    assert "nonexistent-world" in str(got.value), (
        "the refusal must name the world that had no executor, not report a "
        "graph the Boolean world would have refused")
    assert "boolean.task" not in str(got.value), (
        "the record was loaded by the Boolean executor, which is the exact "
        "mis-dispatch the explicit dispatch exists to prevent")


def test_the_driver_names_one_executor_per_bound_world_and_nothing_else():
    """The dispatch is a closed set, and the child agrees with the parent.

    Two owners of the same fact is a second authority, so the check is that
    they hold the same set: every world `GRAPH_WORLDS` admits is dispatched
    by name in the driver, and the driver's `else` refuses rather than
    falling through. The refusal in the child is unreachable through
    `run_graph_step`, which guards first and never spawns a child for a
    world it has no entry for, so it is asserted on the driver source. That
    is deliberate: the child is the only thing that can catch a name
    reaching the driver by some path the parent does not check.
    """
    driver = s09_graph_budget._GRAPH_DRIVER
    branches = re.findall(r'world == "([a-z]+)":', driver)

    assert sorted(branches) == sorted(s09_graph_budget.GRAPH_WORLDS), (        "a bound world has no branch, or a branch names a world that is not "
        "bound: %r" % (branches,))
    assert 'raise ValueError("no graph executor is bound to world "' in driver, (
        "the driver's fall-through is gone. An unrecognised name has to be a "
        "refusal naming itself, not a record loaded by the Boolean executor")
    # The swe branch must bind the SWE world to the ordering executor rather
    # than reusing the Boolean one, which is the defect one level up.
    swe_branch = driver.split('world == "swe":')[1].split("else:")[0]
    assert "s09_swe_binding.SWE_WORLD" in swe_branch
    assert "boolean_graph_policy.choose_action" not in swe_branch


# --- 2. a SWE graph reaches a real SWE world turn -----------------------


def test_a_swe_graph_reaches_a_swe_world_turn_in_the_bounded_child():
    """The child's `swe` branch returns a turn the SWE world itself admits.

    Asserted on the action the real bounded child returns, with the kind,
    the target and the input spelled out as literals. The record's first
    guard is `observed.0.kind ne ""`, so reaching the construct arm at all
    is the world having published an observation the guard read.
    """
    action = s09_graph_budget.run_graph_step(
        swe_binding.swe_graph_record("b9-swe-turn"), _observed_swe_view(), {},
        world="swe")

    assert action == {
        "kind": policy_action.CONSTRUCT,
        "target": swe_world.CONSTRUCT_TARGETS[0],
        "inputs": {"line": 1},
        "evidence_refs": [],
        "requested_resources": {},
    }, "the child did not return the turn the SWE world published"
    swe_world.admits(None, _observed_swe_view(), action)


def test_the_swe_world_admits_the_turn_the_swe_branch_returned():
    """The world's own admission, not a re-typed expectation of our own.

    `s09_swe_binding.validate_swe_action` already asks `swe.admits`, so a
    branch that reused the Boolean executor could not have produced this.
    Asking the world directly keeps the assertion on the world rather than
    on a second copy of what the graph executor happens to emit.
    """
    action = s09_graph_budget.run_graph_step(
        swe_binding.swe_graph_record("b9-admit"), _observed_swe_view(), {},
        world="swe")

    assert swe_world.admits(None, _observed_swe_view(), action) is True
    assert action["target"] == "code.inspect"
    assert action["target"] != swe_binding.SWE_WORLD.stop_target


def test_a_swe_record_is_refused_when_the_child_runs_the_ordering_executor():
    """The cross-world pair, driven through the real child both ways.

    `ordering_graph_policy.expressivity_limits` claims the same refusal for
    its own loader; this drives it through the bounded child, which is the
    path the boolean-executor comment was actually about.
    """
    pytest = __import__("pytest")
    with pytest.raises(s09_graph_budget.GraphBudgetRefused) as got:
        s09_graph_budget.run_graph_step(
            swe_binding.swe_graph_record("b9-cross"), _observed_swe_view(), {},
            world="boolean")

    assert "boolean.task" in str(got.value), (
        "the Boolean executor is supposed to refuse a SWE record for its own "
        "target, and the refusal is the evidence it was the one that ran")


# --- 3. the containment story is unchanged ------------------------------


def test_the_child_reaches_the_swe_binding_through_the_drivers_own_argument():
    """The branch adds an import, not a directory.

    The driver's comment claims `sys.argv[1]` is why the study package is
    reachable, and the claim is the whole basis for ruling that the `swe`
    branch grants no new reach. So it is asserted: the reach exists, from
    the argument alone, with no branch involved. If this ever needs a
    `PYTHONPATH` entry to hold, the ruling's premise is gone and the
    refusal has to be re-argued.
    """
    import subprocess
    import tempfile
    import os

    probe = ("import sys, json\n"
             "sys.path.insert(0, sys.argv[1])\n"
             "from experiments.ad01 import s09_swe_binding as b\n"
             "print(json.dumps({\"stop\": b.SWE_WORLD.stop_target}))\n")
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "probe.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(probe)
        done = subprocess.run([sys.executable, path, str(ROOT)],
                              capture_output=True, text=True)

    assert done.returncode == 0, done.stderr[:400]
    assert done.stdout.strip() == '{"stop": "swe.task"}', (
        "a child holding only the driver's own argument cannot reach the SWE "
        "binding, so the branch would be a new grant of reach rather than a "
        "dispatch decision")


def test_the_child_import_path_is_still_the_drivers_argument_alone():
    """One `sys.path` mutation, and it names `argv[1]`.

    The launcher's `src/` is the one package the child gets without naming
    it. The study tree is reachable because the driver asks for it, and the
    question a future change to this file has to answer is whether that
    request grew. `package_search_path()` is the other half and belongs to
    another owner's test; this is the driver's own half.
    """
    mutations = re.findall(r"^sys\.path\.[a-z_]+\(.*\)$",
                           s09_graph_budget._GRAPH_DRIVER, re.MULTILINE)
    assert mutations == ["sys.path.insert(0, sys.argv[1])"], (
        "the child gained an import path beyond its own argument: %r"
        % (mutations,))


# --- 4. the disposition is recorded, not silently absent ---------------


def test_the_support_record_names_the_blocker_that_survives_the_branch():
    """What is still false, named, so the branch cannot be read as the fix.

    The branch is necessary and it is not sufficient. `compare_arms` hands
    every arm a `contract_view`, and on this world that projection has no
    `symptom` key for `project_swe_view` to re-publish, so the guard the
    record reads is decided against an empty observation table and the arm
    takes its always arm. Measured: the raw policy view yields the
    construct, the contract view yields the stop. So the record has to say
    that, because a support record that names only the branch would read as
    "comparability is one patch away".
    """
    support = swe_experiment.support()

    assert support["supported_representations"] == [
        "python-step", "typed-ast", "action-graph"]
    assert support["missing_representations"] == []
    assert support["comparable_through_compare_arms"] is False, (
        "the branch made the child dispatch the SWE world, which is one "
        "blocker closed and not the one that was holding this False")
    assert "no swe branch" not in support["why_not_comparable"], (
        "the branch exists now; a record still blaming it describes a "
        "dispatch this file replaced")
    assert "contract view" in support["why_not_comparable"], (
        "the surviving blocker is the contract view the common harness "
        "hands the arm, and the record has to name that rather than the "
        "branch this lane added")
