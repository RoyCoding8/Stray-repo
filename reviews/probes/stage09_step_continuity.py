"""Controller observations, with child, persistence and broker boundaries doubled.

Run from the repository with PYTHONPATH=.;src;experiments on Windows.
This observes defects at efe73a3; it does not validate a database or containment.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

from experiments.ad01 import agenda_policy as ap, policy_step as ps
from settlement import broker
from settlement.common import ResultCode


def observe():
    policy = ps.make_policy_artifact(
        'def STEP(view, state):\n    return {"action": {}, "state": state}\n',
        origin="fixture-stand-in")
    seen = {"observations": [{"task_id": "ad01-w0-dev-sw-00"}],
            "remaining": {"model_calls": 1}, "retained": []}
    prepared, settled, events, inputs, returned = [], set(), [], [], []

    def ensure(dsn, **kw):
        prepared.append(kw["operation_id"])
        events.append("prepare-model")
        return SimpleNamespace(code=ResultCode.APPLIED)

    def child(record, view, state, **kw):
        inputs.append(dict(state))
        returned.append({"counter": state.get("counter", 0) + 1})
        index = int(kw["operation_id"].rsplit("k", 1)[1])
        return {"action": {"kind": "request_model" if index < 3 else "stop",
                           "target": "ad01-w0-dev-sw-00",
                           "inputs": {"prompt": "bounded reasoning"}},
                "state": returned[-1],
                "source_digest": record["artifact"]["source_digest"]}

    with patch.object(ps, "run_policy_step", side_effect=child), \
            patch.object(ps, "persist_step_transition", side_effect=lambda *a, **k: events.append("persist-policy")), \
            patch.object(ap, "_policy_settled_text", side_effect=lambda d, op: "response" if op in settled else None), \
            patch.object(broker, "ensure_operation", side_effect=ensure), \
            patch.object(broker, "dispatch_operation", side_effect=lambda d, op, **k: settled.add(op)):
        consumer = ap.StepPolicyConsumer(policy=policy, dsn="review-double",
                                         cid="review", gateway=object(), max_policy_steps=4)
        consumer.decide(seen, {"objective": "review"}, boundary={"seq": 0}, experience=seen)
        first = {"declared_model_calls": 1, "prepared_model_calls": len(prepared),
                 "events": list(events), "last_returned_state": returned[-1]}
        before = len(inputs)
        consumer.decide(seen, {"objective": "review"}, boundary={"seq": 1}, experience=seen)
        return {**first, "next_boundary_initial_state": inputs[before],
                "boundaries_doubled": ["child", "broker", "receipt-read", "persistence"]}


if __name__ == "__main__":
    print(json.dumps(observe(), sort_keys=True))
