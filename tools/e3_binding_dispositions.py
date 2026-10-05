"""Drive the DB-free binding dispositions directly, without pytest.

`tests/conftest_isolation.py` opens an admin connection in
`pytest_configure`, so no test in this tree collects on a host without
PostgreSQL. These are the same assertions the binding tests make, run
against the same functions, so the dispositions can be checked here and the
DB-backed remainder is left to CI.

Everything here uses a nameless store, so `adopt_live_revision`'s
quiescence check returns before it can reach a row.

Run from the repo root:
    python tools/e3_binding_dispositions.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from conftest import live_mission

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live

FAILURES = []


def check(label, got, want):
    ok = got == want
    print("  %s %-58s got %r" % ("PASS" if ok else "FAIL", label, got))
    if not ok:
        print("       want %r" % (want,))
        FAILURES.append(label)


def acquired_package(store, parent, control_id, source):
    from settlement.gateway import ModelRequest, ModelResponse, Usage

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id, json.dumps({"entry": source}),
                {}, Usage(), "stop")

    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    operation_id = "op-acquire-%s" % control_id
    response = guard.infer(ModelRequest(
        model="test-model",
        messages=({"role": "user", "content": "construct"},),
        max_output_tokens=8, deadline_ms=1000,
        operation_id=operation_id),
        evidence={"arm": "test", "task": rules.make_task("dev", 4)["task_id"],
                  "attempt": 1, "raw_prompt": "construct"})
    dispatch = guard.provenance(operation_id)
    package = live.parse_and_build_live_package(
        dict(parent), response.text, control_id, dispatch=dispatch)
    store.record_evidence(dispatch)
    final = guard.finalize_evidence(
        operation_id, parse_outcome="accepted",
        accepted_candidate_digest=package["package_digest"],
        parsed_source_digest=package["imp_digest"],
        package_digest=package["package_digest"],
        parent_digest=package["parent_digest"], round_no=1)
    live.retain_acquired(store, package, final)
    return package


def new_store(tmp, name):
    path = os.path.join(tmp, name)
    store = live.ensure_live_store(
        path,
        live_mission(live.LIVE_MISSION_OBJECTIVE,
                     [{"instrument": "boolean-rule-v1",
                       "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))
    store.propose({
        "opportunity_id": "opp-first",
        "mission_link": live.LIVE_MISSION_OBJECTIVE,
        "question": "what does input 3 reveal",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}})
    return path, store


def acquisition_for(package, arm="test"):
    return {"status": "retained", "arm": arm,
            "control_id": package["control_id"],
            "package_digest": package["package_digest"],
            "response_digest": package["response_digest"]}


def case_unreadable_store(tmp):
    print("unreadable store")
    _, store = new_store(tmp, "unreadable-src.json")
    package = acquired_package(store, channel.make_control("low"),
                               "acq-unreadable", channel.IMPROVE_LOW_SOURCE)
    path = os.path.join(tmp, "unreadable.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("not-json")
    record = live.bind_retained_acquisition(
        str(path), acquisition_for(package), rules.make_task("dev", 4))
    check("disposition", record["disposition"], "retained")
    check("reason names unreadable", "unreadable" in record["reason"], True)


def case_package_not_retained(tmp):
    print("package not in treatment arms")
    path, store = new_store(tmp, "not-retained.json")
    package = acquired_package(store, channel.make_control("low"),
                               "acq-absent", channel.IMPROVE_LOW_SOURCE)
    missing = dict(acquisition_for(package), package_digest="0" * 64)
    record = live.bind_retained_acquisition(
        str(path), missing, rules.make_task("dev", 4))
    check("disposition", record["disposition"], "retained")
    check("reason names missing",
          "missing from treatment arms" in record["reason"], True)


def case_response_digest_mismatch(tmp):
    print("response digest mismatch")
    path, store = new_store(tmp, "digest.json")
    package = acquired_package(store, channel.make_control("low"),
                               "acq-digest", channel.IMPROVE_LOW_SOURCE)
    wrong = dict(acquisition_for(package), response_digest="0" * 64)
    record = live.bind_retained_acquisition(
        str(path), wrong, rules.make_task("dev", 4))
    check("disposition", record["disposition"], "retained")
    check("reason names digest",
          "response digest mismatch" in record["reason"], True)


def case_retained_but_inactive(tmp):
    """The sixth CI failure. A second adoption moved the active package."""
    print("retained but inactive never binds")
    path, store = new_store(tmp, "inactive.json")
    store.bind_active(channel.make_control("low"))
    first = acquired_package(store, channel.make_control("low"),
                             "acq-first", channel.IMPROVE_LOW_SOURCE)
    live.adopt_live_revision(store, first, arm="test")
    second = acquired_package(store, first, "acq-other",
                              channel.IMPROVE_HIGH_SOURCE)
    live.adopt_live_revision(store, second, arm="test")
    store.save()
    record = live.bind_retained_acquisition(
        str(path), acquisition_for(first), rules.make_task("dev", 4))
    check("disposition", record["disposition"], "retained")
    check("reason is about the parent or the diff",
          "differs" in record["reason"] or "parent" in record["reason"], True)


def case_round_refusals_are_not_marked_pre_round(_tmp=None):
    """A refusal from inside the round must stay on the round's side.

    Entering a round needs a disposable authority, and therefore
    PostgreSQL, so this is checked on the source instead of by running it.
    `bind_live_revision` wraps a round refusal in a plain `LiveRefused`, and
    the caller's new branch tests for the subclass. If a round refusal ever
    became a `PreRoundRefusal` it would be recorded as a fact about the
    document rather than an execution result, which is the confusion this
    class exists to prevent.
    """
    print("a refusal from inside a round is not PreRoundRefusal")
    import ast

    path = os.path.join(ROOT, "experiments", "ad01", "live_construct.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())

    binder = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "bind_live_revision")
    raised = [ast.unparse(node.exc.func) for node in ast.walk(binder)
              if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)]
    print("  raises in bind_live_revision: %s" % sorted(set(raised)))

    # Every `PreRoundRefusal` in the binder must come from the adoption call,
    # and every other raise must be a plain `LiveRefused`. A round refusal
    # marked pre-round would be recorded as a fact about the document rather
    # than an execution result.
    adoption_lines = [node.lineno for node in ast.walk(binder)
                      if isinstance(node, ast.Call)
                      and getattr(node.func, "id", None)
                      == "adopt_live_revision"]
    pre_round = {node.lineno for node in ast.walk(binder)
                 if isinstance(node, ast.Raise)
                 and isinstance(node.exc, ast.Call)
                 and ast.unparse(node.exc.func) == "PreRoundRefusal"}
    check("PreRoundRefusal is raised only from the adoption path",
          bool(pre_round) and all(
              any(abs(line - adopt) <= 6 for adopt in adoption_lines)
              for line in pre_round), True)
    check("the adoption path is the only source of PreRoundRefusal",
          len(pre_round) == len(adoption_lines), True)
    check("every other raise is a plain LiveRefused",
          all(name == "LiveRefused" for name in raised
              if name != "PreRoundRefusal"), True)

    caller = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "bind_retained_acquisition")
    branch = [ast.unparse(node.test) for node in ast.walk(caller)
              if isinstance(node, ast.If) and node.test is not None
              and "PreRoundRefusal" in ast.unparse(node.test)]
    print("  caller discriminates on: %s" % branch)
    check("the caller tests the subclass, not the message", branch != [], True)


def main() -> int:
    cases = [case_unreadable_store, case_package_not_retained,
             case_response_digest_mismatch, case_retained_but_inactive,
             case_round_refusals_are_not_marked_pre_round]
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                case(tmp)
            except Exception as exc:                    # noqa: BLE001
                print("  FAIL %s raised %s: %s" % (
                    case.__name__, type(exc).__name__, exc))
                FAILURES.append(case.__name__)
        print()
    if FAILURES:
        print("FAILURES: %d  %s" % (len(FAILURES), FAILURES))
        return 1
    print("all DB-free binding dispositions hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())