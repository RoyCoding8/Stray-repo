"""A guard on a single-segment field can never fire.

`boolean_graph_policy._field_value` resolves `observed.count` and
`observed.N.y.M` by dedicated cases, then falls through to walking
`field.split(".")` over the view. For a single-segment name that walk
never enters the loop, so `value` is still the *whole view* and the
function returns a dict where a caller expects a field.

The loader admits and type-checks these names, so a graph can be written
whose guard compares `remaining` (an int in the world's public state)
against an int and is handed a dict instead. The comparison is False, the
arm falls through to its next arm, and the failure reads as a policy
decision rather than a broken read — which is the worst shape for a bug,
because nothing in the trace says the guard was unreachable.

Measured:

    _field_value({"remaining": 5, ...}, state, "remaining")
    -> {'remaining': 5, 'instrument': ..., 'observed': []}

This was found by a worker porting the graph executor to a second world,
walking the whole guard vocabulary the loader admits and finding that one
of its own fields was unreadable. The port did not copy the bug; this test
and the fix are the integration owner's.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import boolean_graph_policy as graph


VIEW = {"remaining": 5, "instrument": "boolean-rule-v1",
        "task_id": "rule-dev-1", "observed": []}
STATE = {"at": "node", "progress": 0}


def test_a_single_segment_field_reads_that_field_not_the_whole_view():
    assert graph._field_value(VIEW, STATE, "remaining") == 5
    assert graph._field_value(VIEW, STATE, "instrument") == "boolean-rule-v1"
    assert graph._field_value(VIEW, STATE, "task_id") == "rule-dev-1"


def test_a_multi_segment_field_still_walks():
    """`public_world.*` names a field *inside* the view's public_world entry.

    The shared view already nests split, max_queries and hypothesis_class
    under one `public_world` key, so these are single lookups on the view
    rather than a descent from its root.
    """
    view = dict(VIEW, public_world={
        "split": "dev", "max_queries": 8,
        "hypothesis_class": {"class_digest": "d", "class_size": 224}})

    assert graph._field_value(view, STATE, "public_world.split") == "dev"
    assert graph._field_value(view, STATE, "public_world.max_queries") == 8
    assert graph._field_value(
        view, STATE, "public_world.hypothesis_class.class_size") == 224


def test_a_state_field_still_reads_the_cursor():
    assert graph._field_value(VIEW, STATE, "state.at") == "node"
    assert graph._field_value(VIEW, STATE, "state.progress") == 0


def test_a_guard_on_remaining_can_actually_fire():
    """The whole point: a guard on a scalar must be able to be true.

    Before the fix this compared a dict to an int and was always false, so
    the arm below silently took its fallback no matter what the world said.
    """
    evaluate = graph._evaluate_guard

    def guard(value):
        return {"field": "remaining", "op": "eq", "value": value}

    assert evaluate(guard(5), VIEW, STATE) is True, \
        "a guard on a scalar field must be reachable"
    assert evaluate(guard(0), VIEW, STATE) is False


def test_every_field_the_loader_admits_is_readable():
    """Walk the guard vocabulary, because a field can be admitted and unread.

    This is the test that found the bug. The loader type-checks a field
    name, so admitting one implies it can be read; that implication held
    for every field except the single-segment ones.
    """
    # Every name the loader admits. If the loader types a name, a policy
    # can be written against it, and a name admitted but unreadable is a
    # guard that can never fire.
    #
    # The view is the world's own, not a hand-rolled dict. A fixture that
    # omitted a real field made this test fail for the wrong reason twice
    # before it was built from the world - which is the test working.
    from experiments.ad01 import boolean_policy

    readable = sorted(graph.FIELD_TYPES)
    view = boolean_policy._shared_view({
        "instrument": "boolean-rule-v1", "task_id": "rule-dev-1",
        "split": "dev", "max_queries": 8, "remaining": 5, "observed": [],
        "hypothesis_class": {"class_digest": "285113caf4ab",
                             "class_size": 224},
        "action_schema": {"actions": {"probe": {}, "commit": {}, "stop": {}}},
    })
    for field in readable:
        try:
            graph._field_value(view, STATE, field)
        except Exception as exc:  # noqa: BLE001 - the point is any failure
            pytest.fail("field %r is admitted but unreadable: %s" % (field, exc))
