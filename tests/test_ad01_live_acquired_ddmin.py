"""What a model that writes `method="ddmin"` does to the distinctness gate.

Measured on 2026-09-29 against the two arms the live run had at the time,
both acquired from `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` on the
construction prompt. The model chose `ddmin` for both families, unprompted
by anything that named a strategy. Reproduced here from executed bytes
rather than read from a report, so the mechanism can be re-derived on a
panel that changes.

The measurement, over two tasks:

    ad01-w0-within-sw-00  control ctl-software-ddmin  size 3  q 4
                          acquired (ddmin)            size 3  q 4   TIE
    ad01-w0-within-gr-00  control ctl-graph-greedy    size 5  q 4
                          acquired (ddmin)            size 6  q 4   DIFFER

So the two arms are not uniformly the same. On software the control's
measured selector independently chose the strategy the model chose and the
two returned identical candidates; on graph the control chose the other
strategy and the sizes differ. `control_distinct` refuses, and the refusal
names all three of its own reasons at once.

That refusal is the honest reading, and it is a different finding from the
one the previous `not_comparable` demotions recorded. The previous demotions
were one authored constant on one side of every comparison. This one is a
real model policy that happened to converge with a real control on half the
panel and diverge on the other half. Calling it `not_comparable` would hide
the half that differed; calling it distinct would hide the half that did
not. The gate reports both, and the number a reader wants is how many tasks
each cause covers.

Nothing here dispatches a provider. The recorded member bytes run out of
process under one disposable caller-authorized store, the same executor
boundary `control_use` takes.

Run: PYTHONPATH=. .venv/bin/pytest tests/test_ad01_live_acquired_ddmin.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SOFTWARE_TASK = "ad01-w0-within-sw-00"
GRAPH_TASK = "ad01-w0-within-gr-00"

# The bytes the live provider returned, verbatim apart from the envelope
# framing the packet's own parser adds. Two different members by digest, one
# per family, and neither is the double's `ACQUIRED_ORDER_SOURCE`
# (b0bd83b7ec8...), which is what every prior comparison in this stage put
# on the acquired side.
ACQUIRED = {
    SOFTWARE_TASK: (
        "def ENTRY(task, oracle, max_queries=16):\n"
        "    result = reduce_software(task, oracle, max_queries=max_queries,"
        ' method="ddmin")\n'
        "    return {\"candidate\": result[\"candidate\"],"
        " \"queries\": result[\"queries\"]}"),
    GRAPH_TASK: (
        "def ENTRY(task, oracle, max_queries=16):\n"
        "    result = reduce_graph(task, oracle, max_queries=max_queries,"
        ' method="ddmin")\n'
        "    return {\"candidate\": result[\"candidate\"],"
        " \"queries\": result[\"queries\"]}"),
}


def _control_pick(task_id: str, execution_store: dict, operation_id: str) -> dict:
    """The member the control's own measured selector admits, for a task.

    `control_arm.selector_source` is built from `measured_tables`, which runs
    both strategies over the frozen panel in the host and keys the task's
    public shape to whichever produced the smaller candidate. So the pick is
    a measurement, not a position in a list, and the test reads the same
    decision `control_use` reads.
    """
    from experiments.ad01 import control_arm, policy_step, trajectory
    from experiments.ad01 import worlds

    repertoire = control_arm.control_repertoire("ad01-ctl")
    tables = control_arm.measured_tables(repertoire)
    source = control_arm.selector_source(
        repertoire, features=tables["shape"], coarse=tables["template"])
    policy = policy_step.compile_step(source, origin="<ctl-selector>")
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    view = policy_step.materialize_view(
        task=task, observations=[], open_questions=[], last_result=None,
        eligible_methods=[m["capability_id"]
                          for m in repertoire["members"]], remaining={})
    action = trajectory._use_policy_action(policy, view, {}, execution={
        "dsn": execution_store["dsn"],
        "allocation_id": execution_store["allocation_id"],
        "operation_id": operation_id})
    method_id = trajectory._use_admitted_method(action)
    return next(m for m in repertoire["members"]
                if m["capability_id"] == method_id)


@pytest.fixture(scope="module")
def execution_store():
    from execution_authority import execution_store as make_store

    with make_store("ci-ddmin") as store:
        yield store


def _run(task_id: str, source: str, capability_id: str,
         execution_store: dict, operation_id: str) -> dict:
    from experiments.ad01 import control_arm, method_exec, worlds

    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    member = {"capability_id": capability_id, "entry": "ENTRY",
              "method_source": source}
    result = method_exec.run_member_out_of_process(
        member, task, max_queries=control_arm.BUDGET,
        dsn=execution_store["dsn"],
        allocation_id=execution_store["allocation_id"],
        operation_id=operation_id)
    return {"task_id": task_id, "executed": capability_id,
            "executed_source": source, "output": result["candidate"],
            "costs": {"witness_queries": result["queries"]}}


def test_the_model_chose_ddmin_on_both_families_and_nobody_asked_it():
    """The strategy is in the model's bytes, not in a prompt or a selector.

    `control_arm._member_source` puts the strategy inside the reducer call
    for the control's own reasons, the C15 shape. So a strategy token in the
    acquired source is the model's, not a label the harness attached, and
    `_strategy_of` reads it from the same place on both arms.
    """
    from experiments.ad01 import control_distinctness

    for source in ACQUIRED.values():
        assert control_distinctness._strategy_of(
            {"executed_source": source}) == "ddmin"


def test_the_control_picks_a_different_member_per_family(execution_store):
    """The control is not a second ddmin; its selector splits by task shape.

    On software the selector independently lands on ddmin, and on graph it
    lands on greedy. That split is what makes the run a comparison at all:
    a control pinned to one strategy would be one method on two names.
    """
    software = _control_pick(SOFTWARE_TASK, execution_store, "selector-sw")
    graph = _control_pick(GRAPH_TASK, execution_store, "selector-gr")

    assert software["capability_id"] == "ctl-software-ddmin"
    assert graph["capability_id"] == "ctl-graph-greedy"


def test_the_two_arms_tie_on_software_and_differ_on_graph(execution_store):
    """One cause on each task, and they are different causes.

    Software ties because the two arms ran one strategy. Graph differs
    because they ran two, and the sizes differ as well. A run that reported
    only the tie would read as a uniform collision between a model and a
    control, which is not what the panel produced.
    """
    from experiments.ad01 import control_arm

    software_control = _control_pick(SOFTWARE_TASK, execution_store, "comparison-selector-sw")
    graph_control = _control_pick(GRAPH_TASK, execution_store, "comparison-selector-gr")
    sw = _run(SOFTWARE_TASK, software_control["method_source"],
              software_control["capability_id"], execution_store,
              "comparison-sw-control")
    gr = _run(GRAPH_TASK, graph_control["method_source"],
              graph_control["capability_id"], execution_store,
              "comparison-gr-control")
    sw_acq = _run(SOFTWARE_TASK, ACQUIRED[SOFTWARE_TASK], "acquired-sw",
                  execution_store, "comparison-sw-acquired")
    gr_acq = _run(GRAPH_TASK, ACQUIRED[GRAPH_TASK], "acquired-gr",
                  execution_store, "comparison-gr-acquired")

    def size(row):
        out = row["output"]
        return len(out.get("ops") or out.get("vertices") or [])

    assert sw["output"] == sw_acq["output"], (
        "the two arms stopped tying on software, so the recorded cause no "
        "longer describes the panel")
    assert size(gr) != size(gr_acq), (
        "the two arms stopped differing on graph, so the recorded cause no "
        "longer describes the panel")
    assert control_arm.BUDGET == 4


def test_the_gate_refuses_and_names_every_cause_rather_than_one(
        execution_store):
    """A refusal that collapses three causes into one sentence is the defect.

    `control_distinct` returns one boolean and up to nine named lists. The
    measured refusal names all three of its reasons at once, and the
    assertion is on the counts rather than the prose, so a gate that
    started reporting only the first cause would go red here.
    """
    from experiments.ad01 import control_distinctness

    control, acquired = [], []
    for task_id, source in ACQUIRED.items():
        picked = _control_pick(task_id, execution_store, "distinct-selector-" + task_id)
        control.append(_run(task_id, picked["method_source"],
                            picked["capability_id"], execution_store,
                            "gate-control-%s" % task_id))
        acquired.append(_run(task_id, source, "acquired", execution_store,
                             "gate-acquired-%s" % task_id))

    verdict = control_distinctness.control_distinct(control, acquired)

    assert verdict["distinct"] is False
    assert len(verdict["same_strategy"]) == 1
    assert len(verdict["same_candidate"]) == 1
    assert verdict["same_strategy"][0]["task_id"] == SOFTWARE_TASK
    assert verdict["same_candidate"][0]["task_id"] == SOFTWARE_TASK
    assert verdict["same_source"] == []
    assert verdict["same_executed_policy"] == []
    assert verdict["differing_budget"] == []
    # The gate saw no walk on either arm here, because these rows were built
    # in the host rather than through a use phase that records one. A tie
    # with no walk is refused, which is the safe direction and is a third
    # named reason rather than a silent pass.
    assert len(verdict["unmeasured_walk"]) == 2
    assert verdict["refusal"]
    for reason in ("one strategy on both arms", "byte-identical candidate"):
        assert reason in verdict["refusal"], verdict["refusal"]


def test_a_walk_turns_an_unmeasured_tie_into_a_convergence_not_a_refusal():
    """The classification the walk exists to make, on the tied task.

    Two arms that issued the same queries in the same order and were graded
    the same way are the C15 shape and refuse. Two that took different routes
    to one answer are a property of the panel and do not. Without a walk the
    gate cannot tell them and refuses both, which is why the same-run
    measurement above carries `unmeasured_walk` rather than a resolution.
    """
    from experiments.ad01 import control_distinctness as gates

    same_walk = [{"candidate_digest": "a", "verdict": "preserved",
                  "reason": "ok-preserved"}]
    other_walk = [{"candidate_digest": "b", "verdict": "preserved",
                   "reason": "ok-incumbent"}]
    candidate = {"ops": [1]}

    def rows(walk):
        return [{"task_id": SOFTWARE_TASK, "executed": "x",
                 "executed_source": "def ENTRY(task, oracle, max_queries=16):"
                                    " return x",
                 "output": candidate, "query_trace": walk,
                 "costs": {"witness_queries": len(walk)}}]

    tied = gates.control_distinct(rows(same_walk), rows(same_walk))
    converged = gates.control_distinct(rows(same_walk), rows(other_walk))

    # Both tie on the candidate, and `same_candidate` is reported for both.
    # The lists are not exclusive: the walk leg adds a classification to a
    # tie rather than replacing the candidate leg's record of it, so what
    # separates the two is which of `same_walk` and `converged` fired.
    assert len(tied["same_candidate"]) == 1
    assert len(converged["same_candidate"]) == 1

    assert len(tied["same_walk"]) == 1
    assert tied["converged"] == [], (
        "one walk over two answers is the C15 shape, not a convergence")
    assert len(converged["converged"]) == 1
    assert converged["converged"][0]["task_id"] == SOFTWARE_TASK
    assert converged["same_walk"] == []


def test_the_acquired_digests_are_not_the_doubles():
    """The arms are the model's, which is the whole reason this run exists.

    Every prior comparison in this stage put
    `experiments.doubles.ACQUIRED_ORDER_SOURCE` on the acquired side, so
    E1's `CONTROL_WINS` was one constant against two authored controls.
    """
    import hashlib

    from experiments import doubles

    for source in ACQUIRED.values():
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        assert digest != hashlib.sha256(
            doubles.ACQUIRED_ORDER_SOURCE.encode("utf-8")).hexdigest()
        assert not digest.startswith("b0bd83b7")
