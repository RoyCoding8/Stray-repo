"""The action graph is a graph interpreter, not a reducer with a graph label.

The expansion document forbids acquiring a representation label the bytes do
not support: "Do not hide an authored algorithm under an acquired graph
label." An action graph is the easiest of the three representations to fake,
because a fixed chain of nodes with a label is a program.

The discriminating question is whether execution follows the authored
topology. A reducer embeds the answer; a graph follows wiring. So every
witness here holds the node set, the actions, the guards, and the start node
fixed and varies one thing the graph owns, then reads the episode score.

A fixed-schedule policy fails every one of these.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_graph_policy as graph
from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import policy_action
from experiments.ad01 import policy_step

ROOT = Path(__file__).resolve().parent.parent
ALWAYS = {"always": True}


def _action(kind, target, inputs=None, resources=None):
    return {
        "kind": kind,
        "target": target,
        "inputs": {} if inputs is None else inputs,
        "evidence_refs": [],
        "requested_resources": {} if resources is None else resources,
    }


def _probe(x):
    return _action("probe", "boolean.query", {"x": x}, {"queries": 1})


def _commit(bits):
    return _action("construct", "boolean.commit", {
        "specs": [{"const": bit, "mask": 0, "pair": None} for bit in bits],
    })


def _stop():
    return _action("stop", "boolean.task")


def _arm(guard, action, next_node, progress=1):
    return {"guard": guard, "action": action, "next": next_node,
            "progress": progress}


def _node(*arms):
    return {"kind": "action", "arms": list(arms)}


def _graph(policy_id, start, nodes):
    return {"policy_id": policy_id, "start": start, "nodes": nodes}


def _run(record, seed=4):
    return active.run_episode(
        graph.choose_action(record), split="dev", seed=seed)


def _session(seed=4):
    return rules.RuleSession(rules.make_task("dev", seed))


def _public(seed=4):
    return active.public_state(_session(seed=seed))


def _observed_at(bit, seed=4):
    public = _public(seed)
    public["observed"] = [{"x": 3, "y": [bit, 0, 0, 1]}]
    return public


def _one_step(record, public):
    return graph.choose_action(copy.deepcopy(record))(copy.deepcopy(public))


def _score_of(commit_bits, seed=4):
    session = _session(seed)
    session.query(3)
    session.commit_predictor({"specs": [
        {"const": value, "mask": 0, "pair": None} for value in commit_bits]})
    return session.score(session._committed)["overall"]


def _differing(left, right, *, by="next"):
    """Assert two graphs are identical except in the named field.

    `by` is the per-arm field the witness is allowed to vary. Everything
    else, including the node set and the start node, must match at the same
    position, so a difference in episode score can only be attributed to
    what the witness varied. Returns the names of the nodes that differ.

    `by="arm"` compares whole arms as a multiset per node, which is the
    right mode when the witness reorders arms inside a node rather than
    changing one.
    """
    assert set(left["nodes"]) == set(right["nodes"]), "node sets must match"
    assert left["start"] == right["start"], "start nodes must match"
    differences = []
    for name, node in left["nodes"].items():
        other = right["nodes"][name]
        assert len(node["arms"]) == len(other["arms"]), name
        if by == "arm":
            if sorted(map(json.dumps, node["arms"])) != \
                    sorted(map(json.dumps, other["arms"])):
                differences.append(name)
            continue
        for mine, theirs in zip(node["arms"], other["arms"]):
            for field in ("guard", "action", "next", "progress"):
                if field == by:
                    continue
                assert mine[field] == theirs[field], f"{name}.{field}"
            if mine[by] != theirs[by]:
                differences.append(name)
    return differences


# ---------------------------------------------------------------------------
# 1. The topology witness: wiring decides the outcome, not an embedded answer
# ---------------------------------------------------------------------------


def _topology_pair(first_next):
    """Same node set, same actions, same guards. `p`'s first edge is the only
    free variable, and the second arm keeps `d` reachable so both graphs load
    under the reachability rule."""
    return _graph("topology", "p", {
        "p": _node(
            _arm({"field": "observed.count", "op": "eq", "value": 0},
                 _probe(3), first_next, 1),
            _arm({"field": "observed.count", "op": "eq", "value": 1},
                 _probe(7), "d", 1),
            _arm(ALWAYS, _stop(), "stn", 0),
        ),
        "d": _node(_arm(ALWAYS, _commit((1, 0, 0, 1)), "w", 1)),
        "w": _node(_arm(ALWAYS, _stop(), "stn", 0)),
        "stn": _node(_arm(ALWAYS, _stop(), "stn", 0)),
    })


def test_the_first_edge_alone_decides_whether_a_predictor_is_ever_committed():
    scoring = _topology_pair("d")
    wandering = _topology_pair("w")

    assert _differing(scoring, wandering) == ["p"]
    scoring_result = _run(scoring)
    wandering_result = _run(wandering)

    assert [turn["action"]["kind"] for turn in scoring_result["trace"]] == [
        "probe", "construct"]
    assert [turn["action"]["kind"]
            for turn in wandering_result["trace"]] == ["probe", "stop"]
    assert scoring_result["committed"] is True
    assert scoring_result["final"]["overall"] == 0.1875
    assert wandering_result["committed"] is False
    assert wandering_result["final"] is None


def test_the_route_through_the_graph_selects_which_payload_is_committed():
    """Both graphs are the same shape: probe, then hand off to a successor
    that commits, then stop. The successor's payload is fixed per graph and
    the two payloads are worth different scores. Only the first edge names
    a different successor, and the score follows the route. An interpreter
    carrying an embedded answer would score the same either way."""
    def variant(successor, payload):
        return _graph("routing", "p", {
            "p": _node(
                _arm({"field": "observed.count", "op": "eq", "value": 0},
                     _probe(3), successor, 1),
                _arm(ALWAYS, _stop(), "stn", 0),
            ),
            successor: _node(_arm(ALWAYS, _commit(payload), "stn", 1)),
            "stn": _node(_arm(ALWAYS, _stop(), "stn", 0)),
        })

    assert _score_of((1, 0, 0, 1)) == 0.1875
    assert _score_of((1, 1, 1, 1)) == 0.0625
    good = _run(variant("good", (1, 0, 0, 1)))
    poor = _run(variant("poor", (1, 1, 1, 1)))

    assert good["committed"] is True
    assert poor["committed"] is True
    assert good["final"]["overall"] == 0.1875
    assert poor["final"]["overall"] == 0.0625
    assert poor["final"]["overall"] < good["final"]["overall"]


def test_a_graph_whose_only_arm_commits_the_wrong_vector_scores_zero():
    def variant(bits):
        return _graph("decline", "d", {
            "d": _node(
                _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                     _commit(bits), "dn", 1),
                _arm(ALWAYS, _stop(), "dn", 0),
            ),
            "dn": _node(_arm(ALWAYS, _stop(), "dn", 0)),
        })

    good = variant((1, 0, 0, 1))
    bad = variant((0, 0, 0, 0))

    assert _differing(good, bad, by="action") == ["d"]
    good_action = _one_step(good, _observed_at(1))
    bad_action = _one_step(bad, _observed_at(1))
    good_session = _session()
    good_session.query(3)
    active.apply_action(good_session, good_action)
    bad_session = _session()
    bad_session.query(3)
    active.apply_action(bad_session, bad_action)

    assert good_action["kind"] == bad_action["kind"] == policy_action.CONSTRUCT
    assert good_session.score(good_session._committed)["overall"] == 0.1875
    assert bad_session.score(bad_session._committed)["overall"] == 0.0


def test_a_graph_wired_to_keep_probing_commits_and_keeps_spending_budget():
    """Same node set, same start, same edges, same guards. The fallback arm
    of the decision node is the only difference, and it decides whether the
    budget is spent on another query or banked into a predictor."""
    def variant(fallback):
        return _graph("budget", "p", {
            "p": _node(
                _arm({"field": "observed.count", "op": "eq", "value": 0},
                     _probe(3), "d", 1),
                _arm(ALWAYS, _stop(), "d", 0),
            ),
            "d": _node(
                _arm({"field": "observed.count", "op": "eq", "value": 1},
                     _probe(7), "d", 1),
                _arm(ALWAYS, fallback, "d", 1),
            ),
        })

    committing = variant(_commit((1, 0, 0, 1)))
    declining = variant(_stop())

    assert _differing(committing, declining, by="action") == ["d"]
    committing_result = _run(committing)
    declining_result = _run(declining)

    assert committing_result["queried"] == [3, 7]
    assert declining_result["queried"] == [3, 7]
    assert committing_result["committed"] is True
    assert committing_result["final"]["n_queried"] == 2
    assert declining_result["committed"] is False
    assert declining_result["final"] is None


# ---------------------------------------------------------------------------
# 2. Arm order within a node decides which admissible action wins
# ---------------------------------------------------------------------------


def test_the_first_admissible_arm_wins_even_when_a_later_arm_scores_higher():
    good = (1, 0, 0, 1)
    bad = (0, 0, 0, 0)
    first_is_worse = _graph("order", "d", {
        "d": _node(
            _arm({"field": "observed.count", "op": "eq", "value": 1},
                 _commit(bad), "dn", 1),
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit(good), "dn", 1),
            _arm(ALWAYS, _stop(), "dn", 0),
        ),
        "dn": _node(_arm(ALWAYS, _stop(), "dn", 0)),
    })
    second_is_worse = _graph("order", "d", {
        "d": _node(
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit(good), "dn", 1),
            _arm({"field": "observed.count", "op": "eq", "value": 1},
                 _commit(bad), "dn", 0),
            _arm(ALWAYS, _stop(), "dn", 0),
        ),
        "dn": _node(_arm(ALWAYS, _stop(), "dn", 0)),
    })

    chose_bad = _one_step(first_is_worse, _observed_at(1))
    chose_good = _one_step(second_is_worse, _observed_at(1))

    assert [spec["const"]
            for spec in chose_bad["inputs"]["specs"]] == list(bad)
    assert [spec["const"]
            for spec in chose_good["inputs"]["specs"]] == list(good)
    assert _score_of(bad) == 0.0
    assert _score_of(good) == 0.1875


def test_a_graph_that_finds_one_action_whatever_its_wiring_is_not_evidence():
    """The control for the witnesses above. Same node set, same actions, same
    guards, both probe arms admissible on the first step; only the order of
    two arms inside one node differs. A reducer replaying a fixed sequence
    picks the same input either way."""
    def ordered(first, second):
        return _graph("arm-order", "s", {
            "s": _node(
                _arm({"field": "observed.count", "op": "eq", "value": 0},
                     _probe(first), "a", 1),
                _arm({"field": "observed.count", "op": "eq", "value": 1},
                     _probe(second), "b", 1),
                _arm(ALWAYS, _stop(), "a", 0),
            ),
            "a": _node(_arm(ALWAYS, _stop(), "a", 0)),
            "b": _node(_arm(ALWAYS, _stop(), "b", 0)),
        })

    low_first = _run(ordered(3, 7))
    high_first = _run(ordered(7, 3))

    assert low_first["queried"] == [3]
    assert high_first["queried"] == [7]
    assert low_first["queried"] != high_first["queried"]


# ---------------------------------------------------------------------------
# 3. Contingent actions: different observation, different admitted action
# ---------------------------------------------------------------------------


def test_one_observation_bit_selects_between_two_construct_payloads():
    record = _graph("contingent", "d", {
        "d": _node(
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 0},
                 _commit((1, 1, 1, 1)), "dn", 1),
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit((1, 0, 0, 1)), "d", 0),
            _arm(ALWAYS, _stop(), "dn", 0)),
        "dn": _node(_arm(ALWAYS, _stop(), "dn", 0)),
    })

    on_one = _one_step(record, _observed_at(1))
    on_zero = _one_step(record, _observed_at(0))

    assert on_one["kind"] == on_zero["kind"] == policy_action.CONSTRUCT
    assert [spec["const"]
            for spec in on_one["inputs"]["specs"]] == [1, 0, 0, 1]
    assert [spec["const"]
            for spec in on_zero["inputs"]["specs"]] == [1, 1, 1, 1]
    assert on_one["inputs"]["specs"] != on_zero["inputs"]["specs"]
    assert _score_of((1, 0, 0, 1)) == 0.1875
    assert _score_of((1, 1, 1, 1)) == 0.0625


def test_observation_substitution_changes_the_actual_world_effect():
    """One graph. It is entered twice at the same node, once with a real
    observation at the queried input and once with the observation
    substituted for an input the graph has not seen. The same guard, the
    same edges, the same nodes, and two different world effects: a commit
    worth 0.1875, and a traceable refusal that changes nothing. A policy
    replaying a fixed schedule would not notice the substitution."""
    record = _graph("substitution", "d", {
        "d": _node(
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit((1, 0, 0, 1)), "dn", 1),
            _arm(ALWAYS, _stop(), "dn", 0)),
        "dn": _node(_arm(ALWAYS, _stop(), "dn", 0)),
    })

    direct = _one_step(record, _observed_at(1))
    substituted = _one_step(record, _public())
    good_session = _session()
    good_session.query(3)
    effect_good = active.apply_action(good_session, direct)
    good_score = good_session.score(good_session._committed)
    bad_session = _session()
    bad_session.query(3)
    effect_bad = active.apply_action(bad_session, substituted)

    assert direct["kind"] == policy_action.CONSTRUCT
    assert effect_good == {"kind": "commit", "committed": True}
    assert good_score["overall"] == 0.1875
    assert substituted["kind"] == policy_action.STOP
    assert "bridge_refusal" in substituted["inputs"]
    assert bad_session._committed is None
    assert effect_bad == {"kind": "stop", "remaining": 7}


def test_the_policy_branches_on_its_own_carried_state_not_only_on_the_view():
    record = _graph("self-state", "s", {
        "s": _node(
            _arm({"field": "state.progress", "op": "eq", "value": 0},
                 _probe(3), "s", 1),
            _arm({"field": "state.progress", "op": "eq", "value": 1},
                 _probe(7), "s", 1),
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit((1, 0, 0, 1)), "s", 1),
            _arm(ALWAYS, _stop(), "s", 0),
        ),
    })

    result = _run(record)

    assert [turn["action"]["kind"] for turn in result["trace"]] == [
        "probe", "probe", "construct"]
    assert result["queried"] == [3, 7]
    assert result["final"]["overall"] == 0.1875
    assert result["final"]["n_queried"] == 2


def test_every_guard_is_measured_before_the_fallback_fires():
    """A graph that only ever compared one field would still pass the tests
    above. This one gives a node fifteen arms: thirteen never-true equalities,
    then one true equality at position fourteen, then the fallback. Only a
    node that reads all fifteen guards in order can reach the fourteenth."""
    arms = [
        _arm({"field": "observed.count", "op": "eq", "value": value},
             _probe(value + 1), "s", 0)
        for value in range(1, 14)
    ]
    arms.append(_arm({"field": "observed.count", "op": "eq", "value": 0},
                     _probe(14), "s", 0))
    arms.append(_arm(ALWAYS, _stop(), "s", 0))
    record = _graph("wide", "s", {"s": _node(*arms)})

    action = graph.choose_action(record)(_public())

    assert len(arms) == 15
    assert action["inputs"]["x"] == 14


def test_a_node_evaluates_guards_in_order_and_takes_the_first_match():
    """Two guards that are both true, distinguished only by which comes
    first. The earlier arm wins regardless of the later arm's value."""
    earlier = _graph("earlier", "d", {
        "d": _node(
            _arm({"field": "observed.count", "op": "eq", "value": 1},
                 _commit((0, 0, 0, 0)), "dn", 1),
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit((1, 0, 0, 1)), "dn", 1),
            _arm(ALWAYS, _stop(), "dn", 0)),
        "dn": _node(_arm(ALWAYS, _stop(), "dn", 0)),
    })
    later = _graph("later", "d", {
        "d": _node(
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit((1, 0, 0, 1)), "dn", 1),
            _arm({"field": "observed.count", "op": "eq", "value": 1},
                 _commit((0, 0, 0, 0)), "dn", 1),
            _arm(ALWAYS, _stop(), "dn", 0)),
        "dn": _node(_arm(ALWAYS, _stop(), "dn", 0)),
    })

    assert _differing(earlier, later, by="arm") == []
    assert earlier["nodes"]["d"]["arms"] != later["nodes"]["d"]["arms"]
    chose_zero = _one_step(earlier, _observed_at(1))
    chose_one = _one_step(later, _observed_at(1))

    assert [spec["const"] for spec in chose_zero["inputs"]["specs"]] == [
        0, 0, 0, 0]
    assert [spec["const"] for spec in chose_one["inputs"]["specs"]] == [
        1, 0, 0, 1]


# ---------------------------------------------------------------------------
# 4. Bounds. The boundary is load-time admission, not a sandboxed child
# ---------------------------------------------------------------------------


def _sized(node_count, arm_count):
    nodes = {}
    for index in range(node_count):
        name = "n%d" % index
        successor = "n%d" % (index + 1) if index + 1 < node_count else "n0"
        arms = [
            _arm({"field": "state.progress", "op": "eq", "value": 1},
                 _stop(), successor, 0)
            for _ in range(arm_count - 1)
        ]
        arms.append(_arm(ALWAYS, _stop(), successor, 0))
        nodes[name] = _node(*arms)
    return _graph("sized", "n0", nodes)


def test_graph_size_is_capped_and_the_cap_is_enforced_by_exceeding_it():
    at_cap = _sized(64, 16)

    assert len(at_cap["nodes"]) == 64
    assert len(at_cap["nodes"]["n0"]["arms"]) == 16
    assert len(graph.load_policy(at_cap).nodes) == 64
    with pytest.raises(graph.GraphPolicyRefused, match="between 1 and 64"):
        graph.load_policy(_sized(65, 16))
    with pytest.raises(graph.GraphPolicyRefused, match="between 1 and 16"):
        graph.load_policy(_sized(64, 17))


def test_no_field_outside_the_declared_legitimate_list_can_be_guarded_on():
    declared = {
        "instrument", "task_id", "remaining", "public_world.split",
        "public_world.max_queries", "public_world.hypothesis_class.class_size",
        "observed.count", "state.at", "state.progress",
    }
    assert set(graph.FIELD_TYPES) == declared

    for field in ("tables", "seed", "private.tables", "grader", "fault",
                  "witness", "final", "score", "state.tables",
                  "public_world.tables", "observed.tables",
                  "action_schema.tables", "task_id.tables"):
        record = _graph("field", "s", {"s": _node(
            _arm({"field": field, "op": "eq", "value": 0},
                 _stop(), "s", 0),
            _arm(ALWAYS, _stop(), "s", 0))})
        with pytest.raises(graph.GraphPolicyRefused, match="unknown field"):
            graph.load_policy(record)


def test_the_state_cap_is_enforced_at_the_exact_byte_boundary():
    cap = policy_step.STATE_LIMIT_BYTES

    def sized(name_length):
        oversized = "n" * name_length
        return _graph("state-cap", "first", {
            "first": _node(_arm(ALWAYS, _probe(3), oversized, 1)),
            oversized: _node(_arm(ALWAYS, _stop(), oversized, 0)),
        })

    def state_bytes(name_length):
        return len(json.dumps(
            {"at": "n" * name_length, "progress": 1},
            sort_keys=True).encode("utf-8"))

    under = graph.choose_action(sized(4060))(_public())
    refused = graph.choose_action(sized(4090))(_public())

    assert state_bytes(4060) <= cap
    assert state_bytes(4090) > cap
    assert under["kind"] == policy_action.PROBE
    assert refused["kind"] == policy_action.STOP
    assert refused["inputs"]["bridge_refusal"]["reason"].startswith(
        "policy state exceeds 4096 bytes")


def test_the_boundary_is_load_time_admission_not_a_sandboxed_child():
    """This representation runs in the host interpreter. Nothing here claims
    OS containment, and the test says so by asserting the opposite: no
    launcher, no child driver, and no timeout plumbing."""
    source = (ROOT / "experiments/ad01/boolean_graph_policy.py").read_text()

    assert "LocalLauncher" not in source
    assert "run_policy_step" not in source
    assert "_STEP_DRIVER" not in source
    assert "timeout_ms" not in source
    assert "cpu_seconds" not in source
    assert "memory_bytes" not in source
    assert policy_step.STEP_TIMEOUT_MS == 10_000
    assert "LocalLauncher" not in dir(graph)


# ---------------------------------------------------------------------------
# 5. Retention and reload across a real process boundary
# ---------------------------------------------------------------------------

_CHILD = """
import json, sys
sys.path.insert(0, {root!r})
sys.path.insert(0, {src!r})
from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_graph_policy as graph
from experiments.ad01 import boolean_rule as rules

record = json.loads({record!r})
session = rules.RuleSession(rules.make_task("dev", 4))
public = active.public_state(session)
decide = graph.choose_action(record)
emitted = [decide(public)]
public["observed"] = [{{"x": 3, "y": [1, 0, 0, 1]}}]
emitted.append(decide(public))
for action in emitted:
    print(json.dumps({{"action": action, "effect": active.apply_action(
        session, action)}}))
"""


def _in_fresh_interpreter(record):
    script = _CHILD.format(root=str(ROOT), src=str(ROOT / "src"),
                           record=json.dumps(record))
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True,
        cwd=str(ROOT), timeout=180)
    assert completed.returncode == 0, completed.stderr
    return [json.loads(line)
            for line in completed.stdout.strip().splitlines()]


def test_the_loaded_graph_survives_a_fresh_interpreter_that_never_saw_it():
    record = _graph("retained", "s", {
        "s": _node(
            _arm({"field": "observed.count", "op": "eq", "value": 0},
                 _probe(3), "s", 1),
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit((1, 0, 0, 1)), "s", 1),
            _arm(ALWAYS, _stop(), "s", 0),
        ),
    })

    lines = _in_fresh_interpreter(record)

    assert len(lines) == 2
    assert lines[0]["action"]["kind"] == policy_action.PROBE
    assert lines[0]["action"]["inputs"]["x"] == 3
    assert lines[0]["effect"] == {"kind": "probe", "x": 3,
                                  "observation": [1, 0, 0, 1]}
    assert lines[1]["action"]["kind"] == policy_action.CONSTRUCT
    assert [spec["const"]
            for spec in lines[1]["action"]["inputs"]["specs"]] == [1, 0, 0, 1]
    assert lines[1]["effect"] == {"kind": "commit", "committed": True}


def test_a_graph_record_survives_a_json_round_trip_into_a_new_interpreter():
    record = _graph("round-trip", "s", {
        "s": _node(
            _arm({"field": "observed.count", "op": "eq", "value": 0},
                 _probe(3), "s", 1),
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit((1, 0, 0, 1)), "s", 1),
            _arm(ALWAYS, _stop(), "s", 0),
        ),
    })
    reloaded = json.loads(json.dumps(record))

    assert reloaded == record
    lines = _in_fresh_interpreter(reloaded)

    assert [line["action"]["kind"] for line in lines] == [
        policy_action.PROBE, policy_action.CONSTRUCT]


def test_loading_snapshots_the_record_so_a_later_edit_cannot_steer_it():
    record = _graph("snapshot", "s", {
        "s": _node(
            _arm({"field": "observed.count", "op": "eq", "value": 0},
                 _probe(3), "s", 1),
            _arm(ALWAYS, _stop(), "s", 0),
        ),
    })
    decide = graph.choose_action(record)
    assert decide(_public())["inputs"]["x"] == 3

    record["nodes"]["s"]["arms"][0]["action"]["inputs"]["x"] = 12

    assert decide(_public())["inputs"]["x"] == 3


def test_the_emitted_action_is_not_a_live_window_into_the_loaded_policy():
    record = _graph("window", "s", {
        "s": _node(
            _arm({"field": "observed.count", "op": "eq", "value": 0},
                 _probe(3), "s", 1),
            _arm(ALWAYS, _stop(), "s", 0),
        ),
    })
    decide = graph.choose_action(record)

    first = decide(_public())
    first["inputs"]["x"] = 99

    assert decide(_public())["inputs"]["x"] == 3


# ---------------------------------------------------------------------------
# 6. The policy view carries no answer
# ---------------------------------------------------------------------------


def test_the_view_is_exactly_the_declared_public_field_list():
    view = graph.make_view(_public())

    assert set(view) == {"instrument", "task_id", "observed", "remaining",
                         "public_world", "action_schema"}
    assert set(view["public_world"]) == {
        "split", "max_queries", "hypothesis_class"}
    assert view["action_schema"]["budget"]["max_queries"] == \
        view["public_world"]["max_queries"]
    assert set(view) == set(policy_action.view_contract()["fields"])


def test_the_view_omits_the_hidden_target_the_seed_and_the_verdict():
    public = _public()
    view = graph.make_view(public)
    serialized = json.dumps(view, sort_keys=True)
    task = rules.make_task("dev", 4)

    assert set(task) - set(public) == {"tables", "seed"}
    for hidden in ("tables", "seed", "grader", "fault", "witness", "score",
                   "final"):
        assert '"%s"' % hidden not in serialized


def test_the_view_does_not_expose_hidden_tables_even_if_a_caller_injects_one():
    polluted = _public()
    polluted["tables"] = [1, 2, 3]

    with pytest.raises(ValueError, match="hidden tables"):
        graph.make_view(polluted)


def test_a_policy_record_cannot_smuggle_the_answer_past_the_view():
    """The record carries the action payloads, so a graph could in principle
    be handed the target. The guard vocabulary is what stops it: no field
    outside the public list resolves, whatever the record contains."""
    record = _graph("smuggle", "d", {
        "d": _node(
            _arm({"field": "observed.0.y.0", "op": "eq", "value": 1},
                 _commit((1, 0, 0, 1)), "dn", 1),
            _arm(ALWAYS, _stop(), "dn", 0)),
        "dn": _node(_arm(ALWAYS, _stop(), "dn", 0)),
    })
    record["target"] = list(rules.make_task("dev", 4)["tables"])

    with pytest.raises(graph.GraphPolicyRefused, match="unknown fields"):
        graph.load_policy(record)
