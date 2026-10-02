"""Active Boolean discovery for the Stage 9 representation campaign.

The frozen INVL02 output round cannot test autonomous investigation: its
prompt is rendered from a session the host `VersionSpaceLearner` has
already saturated, and the model is asked only for a final predictor.
That is the arrangement the campaign assignment rules out as a
treatment.

This module provides the same instrument with the agent driving the
probe loop. The host still enforces legality, charges the budget, and
grades protected outcomes; it does not choose queries.
"""

from __future__ import annotations

from . import boolean_rule as rules
from . import policy_action

PROBE = "probe"
COMMIT = "commit"
STOP = "stop"

ACTION_VOCABULARY = (PROBE, COMMIT, STOP)


class ActionRefused(Exception):
    pass


def action_schema(max_queries: int) -> dict:
    return {
        "version": 1,
        "format": "s09-boolean-action-v1",
        "actions": {
            PROBE: {"x": "integer 0..15, not yet queried"},
            COMMIT: {"specs": "exactly %d hypothesis-class members"
                              % rules.N_OUTPUTS},
            STOP: {},
        },
        "budget": {"max_queries": max_queries},
    }


def public_state(session: rules.RuleSession) -> dict:
    return {
        "instrument": rules.INSTRUMENT_ID,
        "task_id": session._task["task_id"],
        "split": session._task["split"],
        "max_queries": rules.MAX_QUERIES,
        "remaining": session.remaining,
        "observed": session._observed(),
        "hypothesis_class": session._class_descriptor(),
        "action_schema": action_schema(rules.MAX_QUERIES),
    }


def apply_action(session: rules.RuleSession, action: dict) -> dict:
    """Apply one agent-chosen action, validated through the shared contract.

    The world-local `probe`/`commit`/`stop` names are adapters onto the
    campaign's single `policy_action` contract, so an arm written for
    this world and an arm written for any other world produce the same
    action type. The host still enforces legality only.
    """
    try:
        shared = policy_action.parse_action(action)
    except policy_action.ActionRefused as exc:
        raise ActionRefused(str(exc)) from exc
    kind = shared.kind
    if kind == policy_action.PROBE:
        x = shared.inputs.get("x")
        if type(x) is not int or not 0 <= x <= 15:
            raise ActionRefused("probe x must be an integer in 0..15")
        if x in session.queried:
            raise ActionRefused("input %d was already queried" % x)
        if session.remaining <= 0:
            raise ActionRefused("query budget is exhausted")
        return {"kind": PROBE, "x": x, "observation": session.query(x)}
    if kind == policy_action.CONSTRUCT:
        specs = shared.inputs.get("specs")
        try:
            session.commit_predictor({"specs": specs})
        except rules.RuleRefused as exc:
            raise ActionRefused(str(exc)) from exc
        return {"kind": COMMIT, "committed": True}
    return {"kind": STOP, "remaining": session.remaining}


def _to_shared(kind: str, target: str, inputs: dict,
               resources: dict | None = None) -> dict:
    return {"kind": kind, "target": target, "inputs": inputs,
            "evidence_refs": [],
            "requested_resources": dict(resources or {})}


def as_shared_action(world_action: dict) -> dict:
    """Convert a world-local action into the shared campaign contract."""
    kind = world_action.get("kind")
    if kind == PROBE:
        return _to_shared(policy_action.PROBE, "boolean.query",
                          {"x": world_action.get("x")}, {"queries": 1})
    if kind == COMMIT:
        return _to_shared(policy_action.CONSTRUCT, "boolean.commit",
                          {"specs": world_action.get("specs")})
    if kind == STOP:
        return _to_shared(policy_action.STOP, "boolean.task", {})
    raise ActionRefused("unknown world action %r" % (kind,))


def is_terminal(session: rules.RuleSession) -> bool:
    return session._committed is not None or session.remaining <= 0


def run_episode(choose_action, *, split: str, seed: int) -> dict:
    """Drive a discovery episode where `choose_action` owns the decisions.

    The host supplies observations and grades the protected outcome. It
    never selects a query, decides when to stop, or supplies a predictor.
    """
    task = rules.make_task(split, int(seed))
    session = rules.RuleSession(task)
    trace = []
    max_steps = rules.MAX_QUERIES + 2
    stopped = False
    while not stopped and not is_terminal(session) and len(trace) < max_steps:
        before = {"remaining": session.remaining,
                  "queried": sorted(session.queried)}
        action = choose_action(public_state(session))
        try:
            effect = apply_action(session, action)
        except ActionRefused as exc:
            trace.append({"action": action, "refused": str(exc),
                          "state_before": before})
            break
        trace.append({"action": action, "effect": effect,
                      "state_before": before})
        stopped = effect["kind"] == STOP
    return {
        "task_id": task["task_id"],
        "split": split,
        "seed": int(seed),
        "trace": trace,
        "committed": session._committed is not None,
        "queried": sorted(session.queried),
        "final": (session.score(session._committed)
                  if session._committed is not None else None),
    }
