from __future__ import annotations

import hashlib
import hmac
import random

from . import policy_action

MAX_QUERIES = 8
INSTRUMENT_ID = "ordering-constraints-v1"
JOB_IDS = ("analysis", "build", "deploy", "verify")
SPLITS = ("dev", "qual", "audit")


from experiments.ad01 import worlds as _worlds  # noqa: E402
_ID_KEY = _worlds.TASK_ID_KEY


def _opaque_id(key: str) -> str:
    """A task id suffix a policy holding only the view cannot invert.

    Keyed for the same reason as `boolean_rule.key_id`, and by the same
    key: the plain sha256 was a partial repair (N-01) that N-34 measured
    as reversible by enumerating the 0..9999 seed space. Closing one
    instrument and not the other would leave the study half open.
    """
    return hmac.new(_ID_KEY, key.encode(), hashlib.sha256).hexdigest()[:12]


class ActionRefused(Exception):
    pass


def action_schema(max_queries: int) -> dict:
    return {
        "version": 1,
        "format": "s09-ordering-action-v1",
        "actions": {
            policy_action.PROBE: {
                "target": "schedule.compare",
                "inputs": {"left": "job id", "right": "distinct job id"},
            },
            policy_action.CONSTRUCT: {
                "target": "schedule.commit",
                "inputs": {"order": "a permutation of the four job ids"},
            },
            policy_action.STOP: {"target": "schedule.task"},
        },
        "budget": {"max_queries": max_queries},
    }


def make_task(split: str, seed: int) -> dict:
    if split not in SPLITS:
        raise ActionRefused("unknown-split")
    if type(seed) is not int or seed < 0:
        raise ActionRefused("illegal-seed")
    key = "%s/%s/%d" % (INSTRUMENT_ID, split, seed)
    rng = random.Random(int(hashlib.sha256(key.encode()).hexdigest(), 16))
    # The public id must not carry the seed. `order-dev-0005` hands a policy
    # the recipe for the answer, and a policy that reads it scores 1.0 with no
    # comparison spent. The seed stays on the task, where the grader needs it.
    return {
        "task_id": "order-%s-%s" % (split, _opaque_id(key)),
        "split": split,
        "seed": seed,
        "order": tuple(rng.sample(JOB_IDS, len(JOB_IDS))),
    }


class ScheduleSession:
    def __init__(self, task: dict):
        self._task = task
        self._comparisons: dict = {}
        self._committed = None

    @property
    def remaining(self) -> int:
        return MAX_QUERIES - len(self._comparisons)

    @property
    def comparisons(self) -> dict:
        return dict(self._comparisons)

    def compare(self, left: str, right: str) -> str:
        if self._task["order"].index(left) < self._task["order"].index(right):
            earlier = left
        else:
            earlier = right
        self._comparisons[(left, right)] = earlier
        return earlier

    def commit(self, order: list) -> None:
        self._committed = tuple(order)

    def score(self, order: tuple) -> dict:
        exact = order == self._task["order"]
        return {
            "overall": float(exact),
            "exact": exact,
            "n_comparisons": len(self._comparisons),
        }


def public_state(session: ScheduleSession) -> dict:
    return {
        "instrument": INSTRUMENT_ID,
        "task_id": session._task["task_id"],
        "split": session._task["split"],
        "max_queries": MAX_QUERIES,
        "remaining": session.remaining,
        "observed": [
            {"left": left, "right": right, "earlier": earlier}
            for (left, right), earlier in sorted(session._comparisons.items())
        ],
        "hypothesis_class": {
            "relation": "strict-total-order",
            "job_ids": list(JOB_IDS),
        },
        "action_schema": action_schema(MAX_QUERIES),
    }


def _validate_comparison(session: ScheduleSession, shared: policy_action.Action) -> tuple:
    if shared.target != "schedule.compare":
        raise ActionRefused("probe target must be schedule.compare")
    left = shared.inputs.get("left")
    right = shared.inputs.get("right")
    if left not in JOB_IDS or right not in JOB_IDS:
        raise ActionRefused("comparison jobs must be named job ids")
    if left == right:
        raise ActionRefused("comparison jobs must be distinct")
    if (left, right) in session.comparisons or (right, left) in session.comparisons:
        raise ActionRefused("job pair was already compared")
    if session.remaining <= 0:
        raise ActionRefused("query budget is exhausted")
    return left, right


def _validate_order(shared: policy_action.Action) -> list:
    if shared.target != "schedule.commit":
        raise ActionRefused("construct target must be schedule.commit")
    order = shared.inputs.get("order")
    if not isinstance(order, list):
        raise ActionRefused("construct order must be a list")
    if len(order) != len(JOB_IDS) or any(job not in JOB_IDS for job in order) \
            or len(set(order)) != len(JOB_IDS):
        raise ActionRefused("construct order must be a permutation of job ids")
    return order


def apply_action(session: ScheduleSession, action: dict) -> dict:
    try:
        shared = policy_action.parse_action(action)
    except policy_action.ActionRefused as exc:
        raise ActionRefused(str(exc)) from exc
    if shared.kind == policy_action.PROBE:
        left, right = _validate_comparison(session, shared)
        earlier = session.compare(left, right)
        return {"kind": policy_action.PROBE, "left": left, "right": right,
                "earlier": earlier}
    if shared.kind == policy_action.CONSTRUCT:
        session.commit(_validate_order(shared))
        return {"kind": policy_action.CONSTRUCT, "committed": True}
    return {"kind": policy_action.STOP, "remaining": session.remaining}


def as_shared_action(world_action: dict) -> dict:
    kind = world_action.get("kind")
    if kind not in policy_action.ACTION_KINDS:
        raise ActionRefused("unknown world action %r" % (kind,))
    return {
        "kind": kind,
        "target": world_action.get("target", "schedule.task"),
        "inputs": dict(world_action.get("inputs", {})),
        "evidence_refs": list(world_action.get("evidence_refs", [])),
        "requested_resources": dict(world_action.get("requested_resources", {})),
    }


def is_terminal(session: ScheduleSession) -> bool:
    return session._committed is not None or session.remaining <= 0


def run_episode(choose_action, *, split: str, seed: int) -> dict:
    task = make_task(split, int(seed))
    session = ScheduleSession(task)
    trace = []
    turn_cap = MAX_QUERIES + 2
    stopped = False
    while not stopped and not is_terminal(session) and len(trace) < turn_cap:
        before = {
            "remaining": session.remaining,
            "comparisons": [
                {"left": left, "right": right, "earlier": earlier}
                for (left, right), earlier in sorted(session.comparisons.items())
            ],
        }
        action = choose_action(public_state(session))
        try:
            effect = apply_action(session, action)
        except ActionRefused as exc:
            trace.append({"action": action, "refused": str(exc),
                          "state_before": before})
            break
        trace.append({"action": action, "effect": effect,
                      "state_before": before})
        stopped = effect["kind"] == policy_action.STOP
    return {
        "task_id": task["task_id"],
        "split": split,
        "seed": int(seed),
        "trace": trace,
        "turns": len(trace),
        "committed": session._committed is not None,
        "comparisons": sorted(
            ({"left": left, "right": right, "earlier": earlier}
             for (left, right), earlier in session.comparisons.items()),
            key=lambda item: (item["left"], item["right"]),
        ),
        "final": session.score(session._committed)
        if session._committed is not None else None,
    }
