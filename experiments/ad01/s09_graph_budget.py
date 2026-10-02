"""Run an action graph under the same compute bound as the other two representations.

`STEP` and the typed AST run in a child interpreter under `LocalLauncher`,
with a real timeout, CPU limit, output cap and memory cap. The action graph
ran in the host interpreter, so `s09_arm_parity._action_graph_factory`
accepted the four budget arguments and discarded them. An action graph could
therefore loop forever inside the parity harness, and the harness would
report the arm as `comparable` — a result produced under compute bounds the
other two arms were held to.

The graph is harder to bound than a STEP policy for one reason: it is not
source, it is a record. There is no module to import. So the record is
staged as JSON and a fixed driver reads it, and the driver's own source is
the only thing that runs. That makes the bound provable in the same sense
the AST's is: the bytes executed are not the policy's bytes, they are the
driver's.

The load-time limits in `boolean_graph_policy` — 64 nodes, 16 arms per
node, a 4096-byte state cap — are unchanged and still apply. They bound the
*shape* of a graph, not the time it takes to evaluate one. This bounds the
time.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from . import policy_step


class GraphBudgetRefused(RuntimeError):
    """The graph did not return an action inside its bound."""


# The worlds the child has a dispatch entry for. The driver's own `else`
# refuses any other name, so this is the list a caller has to stay inside
# rather than a hint. A world added here without a branch there is a graph
# loaded by no executor at all, which is the defect the per-world dispatch
# was written to remove.
GRAPH_WORLDS = ("boolean", "ordering", "swe")


_GRAPH_DRIVER = """import json, sys
# Two import sources, and the split is deliberate. `sys.argv[1]` is the
# repository root, which is where `experiments` lives, so the study
# package is reachable through the driver's own argument. `settlement`
# lives under `src/` instead, so the launcher publishes that directory on
# the child's `PYTHONPATH`; it is the one place the child gets a package
# from rather than naming it itself. The child used to be handed the root
# for both, could import neither, and died before loading a graph.
sys.path.insert(0, sys.argv[1])
from experiments.ad01 import boolean_graph_policy, ordering_graph_policy
# One dispatch entry per world, and the name is the key. The `else` branch
# this replaced sent everything it had no executor for to the Boolean one,
# so a SWE graph was loaded by an executor validating against the Boolean
# world and refused as "stop target must be boolean.task" - the same
# world-binding-reported-as-expressivity error the comment below records
# for `ordering`, still open one level up. A name nobody wrote a branch for
# is a refusal naming itself.
#
# Each branch names the executor that validates against that world. A
# world is never served by another world's executor, because the refusal a
# cross-load produces names the executor's target rather than the graph.
#
# The SWE executor is imported inside its branch, not at module scope.
# `s09_swe_binding` derives its observation vocabulary by enumerating the
# task panel at import time, which costs about 1.4s of a 10s CPU budget and
# reaches the fixtures; a Boolean or ordering child should not pay that or
# hold that.
try:
    record = json.load(open(sys.argv[2]))
    cursor = json.load(open(sys.argv[3]))
    world = open(sys.argv[-2]).read()
    # An empty cursor means the first turn: the policy picks its own start
    # node, so `{}` is passed on as the absent case rather than refused.
    if world == "boolean":
        decide = boolean_graph_policy.choose_action(
            record, at_cursor=cursor or None)
    elif world == "ordering":
        decide = ordering_graph_policy.choose_action(
            record, at_cursor=cursor or None,
            world=ordering_graph_policy.ORDERING_WORLD)
    elif world == "swe":
        from experiments.ad01 import s09_swe_binding
        decide = ordering_graph_policy.choose_action(
            record, at_cursor=cursor or None,
            world=s09_swe_binding.SWE_WORLD)
    else:
        raise ValueError("no graph executor is bound to world " + repr(world))
    action = decide(json.load(open(sys.argv[4])))
    print(json.dumps({"status": "ok", "data": {
        "action": action, "cursor": decide.s09_cursor()}}))
except Exception as exc:
    print(json.dumps({"status": "error",
                      "error": type(exc).__name__ + ": " + str(exc)}))
"""


def _positive(name: str, value) -> int:
    number = int(value)
    if number <= 0:
        raise ValueError("%s must be a positive integer" % name)
    return number


def _refuse_failed_receipt(receipt: dict | None, *,
                           timeout_ms: int) -> None:
    """Refuse a child that did not answer, naming which state it was in.

    `parse` is the receipt's own name for what happened to the child, and
    it separates the two states this module used to report as one string.
    `child-failed` is a child that exited nonzero, which includes one that
    died on its imports before loading a graph. `empty` is a child that ran
    and printed nothing. Both arrived as `no receipt`, so a graph arm that
    could not start was indistinguishable from one that ran and declined to
    answer -- and "produced nothing" is the answer a reader would take away
    for a program that never executed a line.

    Its own function so the two states have one owner and can be driven
    against real receipts without launching a child per case.
    """
    data = (receipt or {}).get("data", {})
    if isinstance(data, dict) and data.get("timed_out"):
        raise GraphBudgetRefused(
            "graph step exceeded its %d ms bound" % timeout_ms)
    parse = (receipt or {}).get("parse", "no-receipt")
    if parse == "child-failed":
        stderr = str(data.get("stderr", "")).strip() if isinstance(
            data, dict) else ""
        raise GraphBudgetRefused(
            "graph step failed in child: child-failed: %s" % stderr[:500])
    if parse == "empty":
        raise GraphBudgetRefused(
            "graph step failed in child: child-ran-and-returned-nothing")
    detail = (data.get("worker", {}) or {}).get("error", "no receipt")
    raise GraphBudgetRefused("graph step failed in child: %s" % detail)


def run_graph_step(record: dict, public_state: dict, state: dict, *,
                   world: str = "boolean",
                   timeout_ms: int = policy_step.STEP_TIMEOUT_MS,
                   cpu_seconds: int = policy_step.STEP_CPU_SECONDS,
                   max_output_bytes: int = policy_step.STEP_MAX_OUTPUT_BYTES,
                   memory_bytes: int | None = None) -> dict:
    """One graph step in a child interpreter, under the STEP budget.

    Returns the action dict. Raises `GraphBudgetRefused` on a timeout, a
    child error, or an action the shared contract does not admit — the same
    three ways the STEP path can fail, so an arm that fails here fails for a
    reason the other two could also have hit.

    `world` names the executor the child dispatches to, so it is checked
    here against `GRAPH_WORLDS` before a child is spawned. A name the child
    has no branch for is a refusal naming the name; spawning the child
    first would have produced the Boolean executor's opinion of a graph
    nobody asked the Boolean world about.
    """
    from settlement import broker
    from settlement.launcher_local import LocalLauncher, PROFILE

    if world not in GRAPH_WORLDS:
        raise GraphBudgetRefused(
            "graph step refused: no graph executor is bound to world %r; "
            "the bound worlds are %s"
            % (world, ", ".join(GRAPH_WORLDS)))
    timeout_ms = _positive("timeout_ms", timeout_ms)
    cpu_seconds = _positive("cpu_seconds", cpu_seconds)
    max_output_bytes = _positive("max_output_bytes", max_output_bytes)
    if memory_bytes is not None:
        memory_bytes = _positive("memory_bytes", memory_bytes)

    root = Path(__file__).resolve().parent.parent.parent
    with tempfile.TemporaryDirectory(prefix="ad01-graph-") as directory:
        work = Path(directory)
        launcher = LocalLauncher(work / "launcher")
        operation_id = "graph-step"
        generation = "1"
        (work / "graph.json").write_text(
            json.dumps(record, allow_nan=False, sort_keys=True),
            encoding="utf-8")
        (work / "state.json").write_text(
            json.dumps(state, allow_nan=False, sort_keys=True),
            encoding="utf-8")
        work.mkdir(parents=True, exist_ok=True)
        (work / "public.json").write_text(
            json.dumps(public_state, allow_nan=False, sort_keys=True),
            encoding="utf-8")
        (work / "world.json").write_text(world, encoding="utf-8")
        (work / "driver.py").write_text(_GRAPH_DRIVER, encoding="utf-8")
        payload = {
            "profile": PROFILE,
            "argv": [sys.executable, str(work / "driver.py"), str(root),
                     str(work / "graph.json"), str(work / "state.json"),
                     str(work / "public.json"), str(work / "world.json"),
                     world],
            "timeout_ms": timeout_ms,
            "max_output_bytes": max_output_bytes,
            "cpu_seconds": cpu_seconds,
            "memory_bytes": memory_bytes,
        }
        launcher.dispatch(broker.BrokerOp(
            operation_id=operation_id, effect=broker.SANDBOX_EXEC,
            payload=payload))
        receipt = launcher.read_result(operation_id)

    if receipt is None or receipt.get("outcome") != "success":
        _refuse_failed_receipt(receipt, timeout_ms=timeout_ms)
    worker = receipt.get("data", {}).get("worker", {})
    if worker.get("status") != "ok":
        raise GraphBudgetRefused(
            "graph step refused: %s" % worker.get("error", "unknown"))
    action = worker.get("data", {}).get("action")
    if not isinstance(action, dict):
        raise GraphBudgetRefused("graph step returned no action object")
    # An action graph emits *world* actions - probe, construct, stop - and
    # the shared contract has a different vocabulary. Only `commit` is
    # renamed by the parity adapter and `probe` has no shared counterpart,
    # so validating here against `policy_step.validate_action` would refuse
    # every well-formed graph. That is not a bound, it is a break.
    #
    # The graph needs no second validation either: `choose_action` already
    # calls `boolean_policy._validate_boolean_action` on the action it
    # returns, and it does so inside the child, where a refusal is caught
    # and reported as an error status. Re-validating in the parent would
    # re-read a public state the graph has already consumed.
    cursor = worker.get("data", {}).get("cursor")
    if isinstance(cursor, dict):
        state.clear()
        state.update(cursor)
    return action
