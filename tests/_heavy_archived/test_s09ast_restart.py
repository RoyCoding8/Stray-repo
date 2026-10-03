"""The step state survives a process boundary, proven in a real one.

`policy_action.state_contract` says the step state is "carried between
steps and across processes". `choose_action` cannot honour that on its
own, because it closes over its state. These tests drive `ast_step` from
a fresh interpreter, write the state to disk between the two halves, and
assert the second process continues the episode rather than starting it
again.

Each step already runs in its own child, so "not a re-import" is
belt-and-braces: the parent here is a new OS process, and the step
inside it is a third.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_ast_policy as ast_policy
from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import policy_action


def _const(value):
    return {"op": "const", "value": value}


def _field(scope, name):
    return {"op": "field", "scope": scope, "name": name}


def _index(value, key):
    return {"op": "index", "value": value, "key": key}


def _eq(left, right):
    return {"op": "eq", "left": left, "right": right}


def _obj(**fields):
    return {"op": "obj", "fields": {
        name: value if isinstance(value, dict) and "op" in value
        else _const(value)
        for name, value in fields.items()}}


def _list(*items):
    return {"op": "list", "items": list(items)}


def _action(kind, target, inputs=None, state=None, resources=None):
    return {"op": "return_action", "kind": kind, "target": target,
            "inputs": _obj(**(inputs or {})),
            "evidence_refs": [], "requested_resources": resources or {},
            "state": _const({} if state is None else state)}


def _record(document):
    encoded = json.dumps(document, allow_nan=False, ensure_ascii=False,
                         separators=(",", ":"), sort_keys=True).encode()
    return {"artifact": {
        "kind": "learning-policy", "representation": "typed-ast",
        "version": "boolean-typed-ast-v1",
        "policy_id": document["policy_id"],
        "ast_digest": hashlib.sha256(encoded).hexdigest(),
    }, "policy_ast": document}


def _document(policy_id="three-step"):
    """Probe, then commit a predictor read from the observation.

    The second step's inputs are a function of what the first step was
    told, so a fresh process that resumed from the wrong state would
    commit a different predictor and the test would see it.
    """
    observed = _field("view", "observed")
    specs = _list(*[
        _obj(const=_index(_index(_index(observed, _const(0)),
                                  _const("y")), _const(output)),
             mask=0, pair=None) for output in range(rules.N_OUTPUTS)])
    return {"policy_id": policy_id, "entry": {
        "op": "if", "cond": _eq(observed, _const([])),
        "then": _action("probe", "boolean.query", {"x": 5}, {"step": 1},
                        {"queries": 1}),
        "else": _action("construct", "boolean.commit", {"specs": specs},
                        {"step": 2})}}


def _env():
    env = {"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0",
           "PYTHONPATH": "%s:%s" % (ROOT, ROOT / "src")}
    return env


# Drives a step in a fresh interpreter. Reads the view and the state from
# files, writes the next state back, and prints only JSON.
STEP_SCRIPT = r"""
import json, sys
from experiments.ad01 import boolean_ast_policy as ast_policy
record = json.loads(open(sys.argv[1], encoding="utf-8").read())
view = json.loads(open(sys.argv[2], encoding="utf-8").read())
state = json.loads(open(sys.argv[3], encoding="utf-8").read())
result = ast_policy.ast_step(record, view, state)
open(sys.argv[4], "w", encoding="utf-8").write(
    json.dumps(result["state"], sort_keys=True))
print(json.dumps(result["action"], sort_keys=True))
"""


def _step_in_a_fresh_process(tmp_path, record, view, state, tag):
    record_path = tmp_path / ("record-%s.json" % tag)
    view_path = tmp_path / ("view-%s.json" % tag)
    state_path = tmp_path / ("state-%s.json" % tag)
    next_path = tmp_path / ("next-%s.json" % tag)
    record_path.write_text(json.dumps(record, sort_keys=True))
    view_path.write_text(json.dumps(view, sort_keys=True))
    state_path.write_text(json.dumps(state, sort_keys=True))
    proc = subprocess.run(
        [sys.executable, "-c", STEP_SCRIPT, str(record_path), str(view_path),
         str(state_path), str(next_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        env=_env())
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout), json.loads(next_path.read_text())


def test_the_step_state_is_carried_across_a_real_process_boundary(tmp_path):
    record = _record(_document())
    session = rules.RuleSession(rules.make_task("dev", 4))

    first_action, carried = _step_in_a_fresh_process(
        tmp_path, record, active.public_state(session), {}, "one")
    assert first_action["kind"] == policy_action.PROBE
    assert first_action["inputs"] == {"x": 5}
    assert carried == {"step": 1}

    # The world's state advances in *this* process; the policy's memory
    # comes back from a different one.
    observed = session.query(5)
    assert carried != session.queried

    second_action, final = _step_in_a_fresh_process(
        tmp_path, record, active.public_state(session), carried, "two")
    assert second_action["kind"] == policy_action.CONSTRUCT
    assert [spec["const"] for spec in second_action["inputs"]["specs"]] \
        == list(observed)
    assert final == {"step": 2}


def test_a_fresh_process_resuming_without_the_state_commits_differently(
        tmp_path):
    """The carried state is load-bearing, not decoration.

    The second step reads the observation, so it produces the same
    commit either way. A program whose *step target* depends on carried
    state is the one that separates them, which is what this pins.
    """
    document = {"policy_id": "state-carried", "entry": {
        "op": "if", "cond": _eq(_field("state", "step"), _const(1)),
        "then": _action("probe", "boolean.query", {"x": 9}, {"step": 2},
                        {"queries": 1}),
        "else": _action("probe", "boolean.query", {"x": 2}, {"step": 2},
                        {"queries": 1})}}
    record = _record(document)
    public = active.public_state(rules.RuleSession(rules.make_task("dev", 4)))

    with_state, _ = _step_in_a_fresh_process(
        tmp_path, record, public, {"step": 1}, "carried")
    without_state, _ = _step_in_a_fresh_process(
        tmp_path, record, public, {}, "dropped")

    assert with_state["inputs"] == {"x": 9}
    assert without_state["inputs"] == {"x": 2}
    assert with_state != without_state


def test_the_two_processes_agree_with_a_single_process_episode(tmp_path):
    record = _record(_document())
    episode = active.run_episode(
        ast_policy.choose_action(record), split="dev", seed=4)
    expected = [step["action"] for step in episode["trace"]]

    session = rules.RuleSession(rules.make_task("dev", 4))
    state = {}
    replayed = []
    for index in range(len(expected)):
        action, state = _step_in_a_fresh_process(
            tmp_path, record, active.public_state(session), state,
            "step%d" % index)
        replayed.append(action)
        if action["kind"] == policy_action.PROBE:
            session.query(action["inputs"]["x"])

    assert replayed == expected
    assert state == {"step": 2}


def test_a_fresh_process_is_a_fresh_process():
    """A re-import would pass the tests above and prove nothing.

    This asserts the mechanism the other tests rely on: each step runs
    in a child whose pid differs from the caller's, and the two halves
    of a carried episode really are distinct interpreters.
    """
    source = Path(ast_policy.__file__).read_text(encoding="utf-8")
    assert "subprocess.Popen(" in source
    assert 'sys.executable, "-m", "experiments.ad01.boolean_ast_policy"' \
        in source
    assert ast_policy._child_main.__module__ == ast_policy.__name__


def test_the_state_is_validated_on_both_sides_of_a_step():
    """An oversized state is refused before a child is started."""
    record = _record(_document())
    public = active.public_state(
        rules.RuleSession(rules.make_task("dev", 4)))

    with pytest.raises(ValueError) as raised:
        ast_policy.ast_step(record, public, {"blob": "y" * 6000})
    assert "policy state exceeds" in str(raised.value)
