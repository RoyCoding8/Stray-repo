"""Use-episode policies for the lanes downstream of policy construction.

`run_use` refuses when nothing in hand admits a method, so a caller that
wants a method to run has to supply the decision. A real one comes from a
bound STEP artifact; these tests exercise acquisition, cost, checker and
release lanes rather than policy construction, so they read the method out
of `eligible_methods`, the field `run_use` builds from the repertoire it
was given. Which method runs stays the repertoire's and the release's call
in every caller here.
"""

from __future__ import annotations

MAX_QUERIES = 16


def _result(view, state, method_id):
    return {
        "action": {
            "kind": "use_method",
            "target": view["task_content"]["task_id"],
            "inputs": {"method_id": method_id, "max_queries": MAX_QUERIES},
            "evidence_refs": [],
            "requested_resources": {"queries": MAX_QUERIES},
        },
        "state": dict(state or {}),
    }


def first_eligible(view, state):
    """Admits whatever the repertoire this view was built from holds first."""
    return _result(view, state, view["eligible_methods"][0])


def admit(method_id):
    """Admits one named method, the way a policy bound to one release would.

    `run_use` still refuses a name the repertoire does not carry, so this
    cannot admit its way past selection, release pins or family scope.
    """
    def step(view, state):
        return _result(view, state, method_id)

    return step
