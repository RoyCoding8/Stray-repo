"""The SWE executor's three named capabilities, each driven rather than asserted.

The W1/E1 cap sheet records the typed-AST SWE cell as *missing* on the
strength of one sentence: "executor cannot read a file, run a test, or return
a value". Nothing in the repository had ever measured those three against the
code, so the sentence was a claim about an executor nobody had read at the
three points that matter.

Measuring them produced three different answers, and this file is what makes
those answers checkable. The capability surface is split along the line where
it actually splits:

* the **world** (`s09_swe_world.SweSession`) reads the program under repair,
  runs a public test and returns a value, in process, on any host. This is
  where all three capabilities live, and it is what the STEP cell and the
  graph cell both run through.
* the **typed-AST node set** (`boolean_ast_policy`) publishes no view field
  carrying the program and has no node that builds replacement source text, so
  the representation cannot reach the program even though the world can serve
  it. That is a limit of the frozen grammar, not of the executor, and the
  frozen loader's own refusal is the witness.
* the **bounded child** cannot be spawned on a host with no POSIX `resource`
  module and no `preexec_fn`. That is a platform limit, and it is named by the
  code that makes it rather than by this file.

Each test below runs the real code path and asserts a literal observed value.
The first three would all still pass against an executor that returned
`None`, so they assert on the value and not on the absence of an exception.
"""

from __future__ import annotations

import pytest

from experiments.ad01 import boolean_ast_policy as frozen
from experiments.ad01 import boolean_policy
from experiments.ad01 import policy_action
from experiments.ad01 import policy_step
from experiments.ad01 import s09_arm_parity as parity
from experiments.ad01 import s09_swe_ast as swe_ast
from experiments.ad01 import s09_swe_experiment as matrix
from experiments.ad01 import s09_swe_tasks as tasks
from experiments.ad01 import s09_swe_world as swe


def _session():
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    return record, swe.SweSession(record)


def _refusal(action: dict) -> dict:
    return action["inputs"]["bridge_refusal"]


def _populated_view() -> dict:
    """A real policy view with the public tests already observed.

    Built the way the episode builds it, so a driver is handed what a
    driver is actually handed rather than an empty projection that would
    take the same decisions for a different reason.
    """
    record, session = _session()
    for case in record["public_tests"]:
        session.run_public_test(case["name"])
    session.localize(record["public_tests"][0]["name"])
    return session.policy_view()


# --- (a) read a file ---------------------------------------------------
#
# "Read a file" on this world means the source of the program under repair.
# The world holds it as text lines, so the capability is: a policy can be
# handed the program's own bytes and the task's own source is the same bytes
# the assessor holds. Both are asserted as literal values, because a view
# that published line *numbers* without text would satisfy a weaker test
# and still be the gap the cap sheet describes.


def test_the_world_serves_the_program_under_repair_as_source_text():
    """(a) PRESENT. The policy view publishes the program's source lines."""
    record, session = _session()
    view = session.policy_view()

    assert "source" in view, (
        "the SWE policy view stopped publishing `source`; a policy can no "
        "longer read the program it is asked to repair")
    assert len(view["source"]) == len(record["source_text"])
    assert view["source"][0] == {"line": 1, "text": record["source_text"][0]}
    # Every line carries the text, not only a number.
    assert all(entry["text"] == record["source_text"][index]
               for index, entry in enumerate(view["source"]))


def test_a_read_is_bounded_by_the_inspect_budget():
    """(a) PRESENT, and reading is metered rather than free."""
    record, session = _session()
    before = session.policy_view()["remaining"]["inspect"]

    seen = session.inspect(1)

    assert seen == {"line": 1, "indent": 0,
                    "length": len(record["source_text"][0].rstrip("\n"))}
    assert session.policy_view()["remaining"]["inspect"] == before - 1


# --- (b) run a test ---------------------------------------------------


def test_the_world_runs_a_public_test_and_returns_the_observeration():
    """(b) PRESENT. A named public test runs and returns expected vs actual.

    Asserted against the task's own `expected`, not against "it returned
    something": the faulty program has to actually disagree, and the
    disagreement is what a solver is given.
    """
    record, session = _session()
    case = record["public_tests"][0]

    seen = session.run_public_test(case["name"])

    assert seen["test"] == case["name"]
    assert seen["expected"] == case["expected"]
    assert seen["actual"] != case["expected"], (
        "the injected fault stopped changing the answer; the panel no longer "
        "exercises a repair, and (b) would pass on a broken instrument")
    assert seen["kind"] == "value"


def test_running_a_test_spends_the_test_budget_and_running_it_twice_refuses():
    """(b) PRESENT, and metered. A second run of one test is refused."""
    record, session = _session()
    case = record["public_tests"][0]
    before = session.policy_view()["remaining"]["test"]

    session.run_public_test(case["name"])

    assert session.policy_view()["remaining"]["test"] == before - 1
    with pytest.raises(swe.ActionRefused):
        session.run_public_test(case["name"])


def test_running_a_test_is_reachable_through_the_worlds_action_boundary():
    """(b) PRESENT as an action, not only as a session method.

    The capability a solver needs is the action, because that is the only
    way a policy reaches it. Driving `apply_action` proves the action
    boundary carries it rather than restating a session method.
    """
    record, session = _session()
    name = record["public_tests"][0]["name"]

    effect = swe.apply_action(session, {
        "kind": policy_action.OBSERVE, "target": "test.run",
        "inputs": {"test": name}, "evidence_refs": [],
        "requested_resources": {}})

    assert effect["kind"] == policy_action.OBSERVE
    assert effect["observed"]["test"] == name
    assert session.policy_view()["symptom"]["failing_tests"], (
        "no failing test is published after observing a faulty program")


# --- (c) return a value ------------------------------------------------


def test_the_world_returns_a_value_from_every_public_operation():
    """(c) PRESENT. Each public operation returns a concrete result."""
    record, session = _session()
    for case in record["public_tests"]:
        session.run_public_test(case["name"])

    coverage = session.localize(record["public_tests"][0]["name"])

    assert coverage["test"] == record["public_tests"][0]["name"]
    assert coverage["executed_lines"], (
        "localize returned no executed lines; a solver would have nothing "
        "to rank and (b)+(c) would pass on an instrument that localises "
        "nothing")

    passed = session.run_all_public()
    assert passed == {"passed": 0, "total": len(record["public_tests"]),
                      "observed": [case["name"]
                                   for case in record["public_tests"]]}


def test_the_typed_ast_node_set_returns_a_world_published_value_in_an_action():
    """(c) PRESENT for the typed-AST cell, on the frozen interpreter.

    This drives `frozen._execute_document`, which is the exact function
    the child calls (`_child_main` runs it). Substituting for the child
    is the only substitution: the host has no POSIX `resource` module, so
    the bounded spawn is separately measured below. What is measured here
    is the capability, and the capability is whether a value the world
    published reaches an action input.
    """
    record, session = _session()
    for case in record["public_tests"]:
        session.run_public_test(case["name"])
    view = session.policy_view()
    ast_record = swe_ast.make_record("capability-probe", index=0)
    document, _entry = frozen._load(ast_record)
    projected = swe_ast.swe_view(view)

    result = frozen._execute_document(document, projected, {})

    published = [item["test"] for item in view["symptom"]["observed"]]
    assert result["action"]["kind"] in policy_action.ACTION_KINDS
    assert result["action"]["inputs"]["test"] in published, (
        "the typed-AST arm emitted a test name the world never published; "
        "it is running a committed table, not returning an observed value")


def test_every_swe_cell_records_an_executor_refusal_instead_of_a_bare_stop():
    """(c) The three arms report a step that could not run, naming why.

    This is the test that holds the honesty property. Each cell used to
    have its own answer for "the executor failed": two recorded a
    `bridge_refusal` and the STEP cell emitted a bare `stop`, which is
    indistinguishable from a policy that decided it was finished. A
    matrix built from that reports a host that never ran a child as a
    lineage that ran every episode and repaired nothing.

    The assertion is on the recorded text, so a cell that stops cleanly
    and a cell that cannot start are different rows.
    """
    lineage = matrix.supported_lineages()[0]
    action = matrix.lineage_driver(lineage)(_populated_view())

    assert action["kind"] == policy_action.STOP
    assert _refusal(action)["stage"] == "swe-step-policy-step"
    reason = _refusal(action)["reason"]
    assert reason, (
        "the STEP cell refused without saying why; an unreadable refusal "
        "is the same defect as a silent one")
    # A reason that is only a status token carries no diagnosis. The step
    # used to report `policy-step-failed: {}` here, which named the
    # failure mode and none of its cause, and a reader had no way to tell
    # a host that cannot spawn a child from a policy that raised.
    assert reason not in ("policy-step-failed: {}", "{}"), (
        "the refusal reason is a status token with no cause in it: %r" % reason)
    assert len(reason.split(": ", 1)[-1]) > len("policy-step-failed"), (
        "the refusal does not name what was refused: %r" % reason)


def test_a_step_refusal_is_counted_as_a_refusal_on_its_own_row():
    """A refusal reaches the evidence, not only the trace.

    The row is what the matrix counts and what `lineage_ledger` tallies.
    A driver that records a refusal and a row that drops it are the same
    lie in two places.
    """
    lineage = matrix.supported_lineages()[0]
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    episode = matrix.run_episode(matrix.lineage_driver(lineage),
                                 "held_out", 0)

    row = matrix._row(lineage, record, "held_out", episode)

    assert row.refused, (
        "the row recorded no refusal for an episode whose only turn was an "
        "executor refusal; the matrix would report it as an unrepaired "
        "attempt")
    assert "swe-step-policy-step" in row.refused

    result = matrix.MatrixResult()
    result.rows.append(row)
    ledger = matrix.lineage_ledger(result)
    assert ledger[0].refusals == 1, (
        "a recorded refusal was not counted as one; the ledger reports a "
        "lineage that ran every episode cleanly")


# --- the cap sheet's own claim -----------------------------------------


def test_the_typed_ast_node_set_refuses_to_read_the_program_under_repair():
    """The cap sheet's typed-AST gap, measured rather than quoted.

    The node set publishes no view field carrying the program, so an
    expression reading it is refused by the loader. That refusal is the
    witness; a docstring asserting the limit is not.
    """
    for name in ("source", "symptom", "public_tests"):
        with pytest.raises(Exception) as caught:
            frozen._expr({"op": "field", "scope": "view", "name": name},
                         "probe", frozen._Budget(), 1)
        assert "unknown view field" in str(caught.value)


def test_a_swe_view_with_the_program_still_refuses_to_widen_the_node_set():
    """The projection is the boundary: it cannot hand over what it lacks.

    A caller that reaches past the declared contract view must be refused,
    or the "no field carries the program" claim would be a property of the
    projection rather than of the node set.
    """
    record, session = _session()
    view = session.policy_view()

    with pytest.raises(frozen._ExecutionRefused):
        swe_ast.swe_view(dict(view, tables={"answers": []}))


def test_the_typed_ast_repair_limit_is_a_grammar_limit_not_a_missing_executor():
    """The cap sheet's three-part claim, resolved against the evidence.

    Read a file: the world serves it, the node set has no field for it.
    Run a test: the world runs it and returns the observation.
    Return a value: the frozen interpreter returns an action whose input
    is a value the world published.

    So the executor is not missing the capability. The typed-AST
    *representation* cannot express a repair, which is a different claim
    from the one the cap sheet makes, and the two must not be reported
    as one. This test fails if either half regresses.
    """
    limit = swe_ast.missing_cells()["typed-ast"]

    assert "no view field carrying the program" in limit["missing_cell"]
    assert swe_ast.expressivity()["cannot"], (
        "the expressivity report stopped naming the cell it cannot fill")
    # The world still serves all three, so the limit is the node set's.
    record, session = _session()
    assert "source" in session.policy_view()
    assert session.run_public_test(record["public_tests"][0]["name"])


def test_the_bounded_child_refusal_names_the_platform_rather_than_a_program():
    """The host limit is reported by the code that makes it.

    On this host there is no POSIX `resource` module, so the typed-AST
    executor refuses before a child exists. The refusal must name the
    platform. A step failure that reads as a program error sends a
    reader looking for a bug in the policy.
    """
    support = frozen.child_limit_support()
    assert isinstance(support.available, bool)
    if not support.available:
        assert support.reason, "an unavailable host must say why"
        assert "Linux" in support.reason or "POSIX" in support.reason


def test_a_step_refusal_on_this_host_survives_the_round_trip_to_the_row():
    """The end-to-end property, on whichever side of the limit this host is.

    Whether the host can spawn the bounded child is not this lane's to
    decide, so the assertion holds either way: a step that runs emits an
    action the world admits, and a step that cannot run emits a refusal
    that names itself. What must never happen is a bare `stop`.
    """
    lineage = matrix.supported_lineages()[0]
    episode = matrix.run_episode(matrix.lineage_driver(lineage),
                                 "held_out", 0)

    action = episode["trace"][0]["action"]
    assert action["kind"] == policy_action.STOP
    assert _refusal(action)["reason"], (
        "the STEP cell produced a stop with no reason on this host; either "
        "the child ran and returned an action, or the refusal must be named")


# --- staging fidelity --------------------------------------------------
#
# The defect that made the STEP cell unreadable on Windows. A text-mode
# `write_text` translates each `\n` to `os.linesep`, so the staged bytes
# were not the bytes the digest was taken from and the step refused
# itself before a child existed.


def test_staged_policy_bytes_are_the_bytes_the_digest_was_taken_from():
    """The staged source must hash to what the record says it hashes to.

    Driven through `_run_shared_policy_step` itself, with the launcher
    stubbed so the assertion is about the bytes on disk and not about
    whether this host can spawn a child.

    The staging directory is read at the point the step would dispatch,
    so a defect that refuses the step *before* dispatch is caught rather
    than skipped. A text-mode `write_text` translated every `\\n` to
    `os.linesep` on Windows; the step then compared the on-disk digest to
    the one it took in memory, they differed, and the step refused itself
    with "staged policy source digest mismatch" before any child existed.
    Asserting only that an exception was raised would pass on that
    refusal, so the assertion is on the bytes and the launcher capture is
    what makes them observable.
    """
    lineage = matrix.supported_lineages()[0]
    record, session = _session()
    view = session.policy_view()

    staged: dict[str, bytes] = {}
    reached_dispatch = []

    class _Launcher:
        def __init__(self, run_dir, *args, **kwargs):
            self.run_dir = run_dir

        def dispatch(self, op):
            staged.update(_read_tree(self.run_dir.parent))
            reached_dispatch.append(True)
            raise RuntimeError("dispatch reached; bytes captured above")

    original = boolean_policy.LocalLauncher
    boolean_policy.LocalLauncher = _Launcher
    try:
        with pytest.raises(Exception):
            boolean_policy._run_shared_policy_step(
                lineage.record, view, {},
                timeout_ms=policy_step.STEP_TIMEOUT_MS,
                cpu_seconds=policy_step.STEP_CPU_SECONDS,
                max_output_bytes=policy_step.STEP_MAX_OUTPUT_BYTES,
                memory_bytes=None)
    finally:
        boolean_policy.LocalLauncher = original

    assert reached_dispatch, (
        "the step refused before dispatch, so the staged bytes were never "
        "observed; the source is written in text mode, which translates "
        "every newline and makes the on-disk digest disagree with the one "
        "the record carries")
    assert b"policy.py" in staged, "the policy source was never staged"
    import hashlib
    expected = hashlib.sha256(
        lineage.record["policy_source"].encode("utf-8")).hexdigest()
    assert hashlib.sha256(staged[b"policy.py"]).hexdigest() == expected, (
        "the staged policy bytes are not the bytes their digest was taken "
        "from")


def _read_tree(root):
    """Every staged file in `root`, keyed by name, as raw bytes."""
    return {path.name.encode(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}
