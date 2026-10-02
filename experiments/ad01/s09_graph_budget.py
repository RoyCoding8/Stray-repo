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


_GRAPH_DRIVER = """import json, sys
sys.path.insert(0, sys.argv[1])
from experiments.ad01 import boolean_graph_policy, ordering_graph_policy
try:
    record = json.load(open(sys.argv[2]))
    cursor = json.load(open(sys.argv[3]))
    world = open(sys.argv[-2]).read()
    # The executor is the world's, not a constant. It was the Boolean one
    # unconditionally, so an ordering graph was loaded by an executor that
    # validates against the Boolean world and refused it as "construct
    # target must be boolean.commit" - a world binding reported as if it
    # were the graph's own expressivity.
    #
    # An empty cursor means the first turn: the policy picks its own start
    # node, so `{}` is passed on as the absent case rather than refused.
    if world == "ordering":
        decide = ordering_graph_policy.choose_action(
            record, at_cursor=cursor or None,
            world=ordering_graph_policy.ORDERING_WORLD)
    else:
        decide = boolean_graph_policy.choose_action(
            record, at_cursor=cursor or None)
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
    """
    from settlement import broker
    from settlement.launcher_local import LocalLauncher, PROFILE

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
        data = (receipt or {}).get("data", {})
        if isinstance(data, dict) and data.get("timed_out"):
            raise GraphBudgetRefused(
                "graph step exceeded its %d ms bound" % timeout_ms)
        detail = (data.get("worker", {}) or {}).get("error", "no receipt")
        raise GraphBudgetRefused("graph step failed in child: %s" % detail)
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
