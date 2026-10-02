"""M2 inherited improvement behavior through the action interface.

Operational and improvement behavior share one executable package: two
STEP sources under one manifest digest. The improvement entry controls
later acquisition, construction and selection by returning probe,
construct and select actions that the driver executes through real
instruments. Menu selection and prompt advice are not involved.

Two authored controls share their operational bytes and differ in their
improvement bytes. Under matched inputs they request different real
probes. Both stay labeled and never enter acquired treatment arms.
Leaf construction maps a construct request to a revised package whose
improvement source follows the requested strategy. Adoption binds at a
quiescent boundary with reset private state and explicit retained
evidence plus obligations.
"""

from __future__ import annotations

import json
import sys

from . import boolean_rule as _boolean_rule
from . import frontier as _frontier
from . import method_exec as _method_exec

CHANNEL_VERSION = "invl02-improve-v1"

ORIGIN = "authored-control"
ACQUIRED = "acquired"

CONTROL_LOW_ID = "authored-control-low-01"
CONTROL_HIGH_ID = "authored-control-high-01"

IMPROVE_KINDS = ("probe", "construct", "select", "wait", "stop")

SHARED_OPERATE_SOURCE = """def STEP(view, state):
    frontier = view["frontier"]
    exp = view["experience"]
    rounds = state.get("rounds", 0)
    if not frontier:
        inner = {"kind": "stop",
                 "inputs": {"reason": "no admissible work"},
                 "requested_resources": {}}
        target = "open"
        outer = "stop"
    else:
        last = exp[-1] if exp else None
        if last is not None and last.get("verdict") == "mismatch":
            alt = [o for o in frontier
                   if o.get("task") != last.get("task")]
            choice = alt[0] if alt else frontier[0]
        else:
            choice = frontier[0]
        inner = {"kind": "investigate",
                 "inputs": {"opportunity_id":
                            choice["opportunity_id"]},
                 "requested_resources": {"steps": 1}}
        target = choice["opportunity_id"]
        outer = "diagnose"
    action = {"kind": outer, "target": target,
              "inputs": {"frontier_action": inner},
              "evidence_refs": [],
              "requested_resources": inner["requested_resources"]}
    return {"action": action,
            "state": {"rounds": rounds,
                      "last_choice": target}}
"""

IMPROVE_LOW_SOURCE = """def STEP(view, state):
    step = state.get("step", 0)
    if step == 0:
        inner = {"kind": "probe", "inputs": {"x": 3},
                 "requested_resources": {"queries": 1, "steps": 1}}
        state = {"step": 1}
    else:
        exp = view["experience"]
        if not exp:
            inner = {"kind": "wait",
                     "inputs": {"reason": "probe left no observation"},
                     "requested_resources": {}}
            state = {"step": 1}
        else:
            first = exp[-1].get("y", [0, 0, 0, 0])
            strategy = "high" if first[0] == 1 else "low"
            inner = {"kind": "construct",
                     "inputs": {"strategy": strategy},
                     "requested_resources": {"steps": 1}}
            state = {"step": 2, "strategy": strategy}
    action = {"kind": "diagnose", "target": "rule-improve",
              "inputs": {"frontier_action": inner},
              "evidence_refs": [],
              "requested_resources": inner["requested_resources"]}
    return {"action": action, "state": state}
"""

IMPROVE_HIGH_SOURCE = """def STEP(view, state):
    step = state.get("step", 0)
    if step == 0:
        inner = {"kind": "probe", "inputs": {"x": 11},
                 "requested_resources": {"queries": 1, "steps": 1}}
        state = {"step": 1}
    else:
        exp = view["experience"]
        if not exp:
            inner = {"kind": "wait",
                     "inputs": {"reason": "probe left no observation"},
                     "requested_resources": {}}
            state = {"step": 1}
        else:
            first = exp[-1].get("y", [0, 0, 0, 0])
            strategy = "high" if first[0] == 1 else "low"
            inner = {"kind": "construct",
                     "inputs": {"strategy": strategy},
                     "requested_resources": {"steps": 1}}
            state = {"step": 2, "strategy": strategy}
    action = {"kind": "diagnose", "target": "rule-improve",
              "inputs": {"frontier_action": inner},
              "evidence_refs": [],
              "requested_resources": inner["requested_resources"]}
    return {"action": action, "state": state}
"""

_CONTROLS = {
    "low": (CONTROL_LOW_ID, IMPROVE_LOW_SOURCE),
    "high": (CONTROL_HIGH_ID, IMPROVE_HIGH_SOURCE),
}

_STRATEGY_SOURCE = {"low": IMPROVE_LOW_SOURCE, "high": IMPROVE_HIGH_SOURCE}


def make_control(which: str) -> dict:
    try:
        control_id, imp_source = _CONTROLS[which]
    except KeyError:
        raise _frontier.Refused("unknown authored control %r" % (which,))
    return {
        "control_id": control_id,
        "origin": ORIGIN,
        "op_source": SHARED_OPERATE_SOURCE,
        "imp_source": imp_source,
        "op_digest": _frontier.source_digest(SHARED_OPERATE_SOURCE),
        "imp_digest": _frontier.source_digest(imp_source),
        "package_digest": _frontier.package_digest(
            SHARED_OPERATE_SOURCE, imp_source, None, 0, control_id),
        "parent_digest": None,
        "version": 0,
        "authority_request": {"queries": 16, "steps": 12},
        "obligations": ["re-test probe divergence on new seeds"],
        "channel": CHANNEL_VERSION,
    }


def validate_improve_action(action: dict) -> dict:
    if not isinstance(action, dict):
        raise _frontier.Refused("improve action must be an object")
    kind = action.get("kind")
    if kind not in IMPROVE_KINDS:
        raise _frontier.Refused("unknown improve action kind %r" % (kind,))
    inputs = action.get("inputs")
    if not isinstance(inputs, dict):
        raise _frontier.Refused("improve action inputs must be an object")
    if kind == "probe" and (not isinstance(inputs.get("x"), int)
                            or not 0 <= inputs["x"] < 16):
        raise _frontier.Refused("probe needs an input x in 0..15")
    if kind == "construct" and inputs.get("strategy") not in (
            "low", "high"):
        raise _frontier.Refused("construct needs a known strategy")
    if kind == "select" and not isinstance(
            inputs.get("candidate_id"), str):
        raise _frontier.Refused("select needs a candidate_id")
    resources = action.get("requested_resources")
    if not isinstance(resources, dict) or any(
            type(v) is not int or v < 0 for v in resources.values()):
        raise _frontier.Refused("improve action requested_resources must"
                                " hold nonnegative integers")
    return action


def _step_view(view: dict) -> dict:
    from . import policy_step as _policy_step
    remaining = dict(view.get("authority_remaining") or {})
    envelope = _policy_step.materialize_view(
        task={"family": "boolean",
              "task_id": (view["frontier"][0]["task"]
                          if view.get("frontier") else "open")},
        observations=list(view.get("experience") or []),
        open_questions=[],
        last_result=None,
        eligible_methods=[],
        remaining={"queries": int(remaining.get("queries", 0)),
                   "steps": int(remaining.get("steps", 0))})
    envelope.update(dict(view))
    return envelope


def _run_source(source: str, view: dict, state: dict) -> dict:
    _method_exec.verify_step_source(source, "STEP")
    stepped = _method_exec.run_step_out_of_process(
        source, _step_view(view), dict(state))
    return stepped


def _unwrap(outer: dict) -> dict:
    if not isinstance(outer, dict) or not isinstance(
            outer.get("inputs"), dict) or "frontier_action" not in \
            outer["inputs"]:
        raise _frontier.Refused("STEP envelope holds no frontier action")
    return dict(outer["inputs"]["frontier_action"])


def run_operate_step(package: dict, view: dict, state: dict) -> dict:
    _frontier.validate_view(view)
    if view["purpose"] != _frontier.OPERATE:
        raise _frontier.Refused("operate runner got a %s view" % (
            view.get("purpose"),))
    stepped = _run_source(package["op_source"], view, state)
    if stepped.get("source_digest") != package["op_digest"]:
        raise _frontier.Refused("executed bytes are not the bound"
                                " operational source")
    action = _frontier.validate_operate_action(_unwrap(
        stepped["action"]))
    return {"action": action, "state": stepped["state"],
            "executed_digest": package["op_digest"]}


def run_improve_step(package: dict, view: dict, state: dict) -> dict:
    _frontier.validate_view(view)
    if view["purpose"] != _frontier.IMPROVE:
        raise _frontier.Refused("improve runner got a %s view" % (
            view.get("purpose"),))
    stepped = _run_source(package["imp_source"], view, state)
    if stepped.get("source_digest") != package["imp_digest"]:
        raise _frontier.Refused("executed bytes are not the bound"
                                " improvement source")
    action = validate_improve_action(_unwrap(stepped["action"]))
    return {"action": action, "state": stepped["state"],
            "executed_digest": package["imp_digest"]}


def execute_operate_action(store, action: dict, task=None) -> dict:
    _frontier.validate_operate_action(action)
    try:
        store.spend(dict(action.get("requested_resources") or {}))
    except _frontier.Refused as exc:
        return {"status": "refused", "reason": str(exc)}
    kind = action["kind"]
    inputs = dict(action.get("inputs") or {})
    if kind == "probe":
        if task is None:
            raise _frontier.Refused("probe needs its frozen task")
        session = _boolean_rule.RuleSession(task)
        try:
            found = session.query(int(inputs["x"]))
        except _boolean_rule.RuleRefused as exc:
            return {"status": "refused", "reason": exc.reason}
        observation = {
            "observation_id": "obs-%s-x%d" % (
                inputs.get("opportunity_id", "open"), inputs["x"]),
            "task": inputs.get("opportunity_id", ""),
            "verdict": "observed",
            "x": inputs["x"],
            "y": list(found),
        }
        store.observe(observation)
        store.record_outcome(
            {"instrument": "boolean-rule-v1",
             "inputs": {"x": inputs["x"]},
             "environment": store.environment_digest},
            {"y": list(found)})
        return {"status": "observed", **observation}
    if kind == "investigate":
        active = store.active_digest
        if active is None:
            raise _frontier.Refused("investigation needs a bound program")
        effect = store.accept(inputs["opportunity_id"], active)
        return {"status": "accepted", **effect}
    if kind in ("wait", "stop"):
        return {"status": kind, "reason": inputs.get("reason", kind)}
    return {"status": "requested", "kind": kind,
            "reason": "deterministic lane records the request; live"
                      " construction stays outside this lane"}


def leaf_construct(strategy: str, parent: dict, round_no: int) -> dict:
    try:
        imp_source = _STRATEGY_SOURCE[strategy]
    except KeyError:
        raise _frontier.Refused("unknown construct strategy %r" % (
            strategy,))
    op_source = parent["op_source"]
    control_id = "acquired-%s-r%d" % (strategy, round_no)
    version = int(parent.get("version", 0)) + 1
    return {
        "control_id": control_id,
        "origin": ACQUIRED,
        "op_source": op_source,
        "imp_source": imp_source,
        "op_digest": _frontier.source_digest(op_source),
        "imp_digest": _frontier.source_digest(imp_source),
        "package_digest": _frontier.package_digest(
            op_source, imp_source, parent["package_digest"],
            version, control_id),
        "parent_digest": parent["package_digest"],
        "version": version,
        "authority_request": dict(parent.get("authority_request") or {
            "queries": 16, "steps": 12}),
        "obligations": ["re-test probe divergence on new seeds"],
        "channel": CHANNEL_VERSION,
    }


def drive_improve_round(store, task, package=None,
                        round_no=None) -> dict:
    active = dict(package) if package is not None \
        else store.active_package
    if active is None:
        raise _frontier.Refused("improvement needs a bound program")
    if round_no is None:
        round_no = len(store._doc["rounds"]) + 1
    session = _boolean_rule.RuleSession(task)
    round_obs: list = []
    log: list = []
    state: dict = {}
    candidate = None
    for step in range(3):
        view = store.step_view(_frontier.IMPROVE, active)
        view["experience"] = list(round_obs)
        view["round"] = round_no
        stepped = run_improve_step(active, view, state)
        action = stepped["action"]
        state = stepped["state"]
        try:
            store.spend(dict(action.get("requested_resources") or {}))
        except _frontier.Refused as exc:
            log.append({"round": round_no, "step": step,
                        "action": action["kind"], "inputs": {},
                        "executed_digest": stepped["executed_digest"],
                        "result": "refused: %s" % exc})
            break
        if action["kind"] == "probe":
            found = session.query(int(action["inputs"]["x"]))
            entry = {"x": int(action["inputs"]["x"]),
                     "y": list(found)}
            round_obs.append(entry)
            store.record_outcome(
                {"instrument": "boolean-rule-v1",
                 "inputs": {"x": entry["x"]},
                 "environment": store.environment_digest},
                {"y": list(found)})
            log.append({"round": round_no, "step": step,
                        "action": "probe", "inputs": {"x": entry["x"]},
                        "executed_digest": stepped["executed_digest"],
                        "result": "observed"})
        elif action["kind"] == "construct":
            candidate = leaf_construct(
                action["inputs"]["strategy"], active, round_no)
            store._doc["staged_candidate"] = dict(candidate)
            store.save()
            log.append({"round": round_no, "step": step,
                        "action": "construct",
                        "inputs": dict(action["inputs"]),
                        "executed_digest": stepped["executed_digest"],
                        "result": candidate["control_id"]})
        elif action["kind"] == "select":
            wanted = action["inputs"]["candidate_id"]
            staged = store._doc["staged_candidate"] or {}
            if staged.get("control_id") != wanted:
                log.append({"round": round_no, "step": step,
                            "action": "select",
                            "inputs": dict(action["inputs"]),
                            "executed_digest": stepped[
                                "executed_digest"],
                            "result": "unsupported: unknown candidate"})
                break
            log.append({"round": round_no, "step": step,
                        "action": "select",
                        "inputs": dict(action["inputs"]),
                        "executed_digest": stepped["executed_digest"],
                        "result": "selected"})
        else:
            log.append({"round": round_no, "step": step,
                        "action": action["kind"],
                        "inputs": dict(action.get("inputs") or {}),
                        "executed_digest": stepped["executed_digest"],
                        "result": "round-ended"})
            break
    if candidate is None:
        raise _frontier.Refused("improve round left no candidate")
    store._doc["rounds"].append(
        {"round": round_no, "candidate_id": candidate["control_id"],
         "parent_digest": candidate["parent_digest"],
         "executed_digest": active["imp_digest"]})
    store._doc["improvement_log"].extend(log)
    store.save()
    return {"candidate": candidate, "log": log,
            "observations": list(round_obs)}


def fresh_round(store_path: str, round_no: int) -> dict:
    store = _frontier.FrontierStore(store_path)
    active = store.active_package
    if active is None:
        raise _frontier.Refused("fresh process found no bound program")
    environment = dict(store._doc["environments"][0])
    task = _boolean_rule.make_task(environment["split"],
                                   environment["seed"])
    result = drive_improve_round(store, task, round_no=int(round_no))
    candidate = result["candidate"]
    return {"candidate_id": candidate["control_id"],
            "parent_digest": candidate["parent_digest"],
            "executed_digest": active["imp_digest"],
            "imp_source_digest": candidate["imp_digest"],
            "round": int(round_no)}


def main(argv) -> int:
    store_path, round_no = argv[1], int(argv[2])
    summary = fresh_round(store_path, round_no)
    sys.stdout.write(json.dumps(summary, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
