"""Prove the two refusal kinds still land on opposite sides.

`bind_retained_acquisition` has three outcomes and each one depends on the
guard that picks it:

  * refused before a round was entered -> recorded, `disposition: retained`
  * refused inside a round that executed nothing -> raised
  * refused inside a round that ran -> recorded, `disposition: rejected` or
    `retained` by the message marker

Guards that distinguish two of these and conflate the third are the defect
this leg repaired twice. So each outcome is forced here with the round
stubbed, which needs no PostgreSQL, and read off the real caller.

Run from the repo root:
    python tools/e3_refusal_routing.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from conftest import live_mission

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live

FAILURES = []


def check(label, ok, detail=""):
    print("  %s %s%s" % ("PASS" if ok else "FAIL", label,
                         ("  <- %s" % detail) if detail else ""))
    if not ok:
        FAILURES.append(label)


def make_store(tmp, name="store.json"):
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
    store.bind_active(channel.make_control("low"))
    return path, store


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


def acquisition_for(package, arm="test"):
    return {"status": "retained", "arm": arm,
            "control_id": package["control_id"],
            "package_digest": package["package_digest"],
            "response_digest": package["response_digest"]}


def stub_round(message, ran):
    """Replace the round with one that raises `message`.

    `ran` decides whether the store keeps a `round_command`, which is what
    the caller reads to tell a round that executed from one that refused
    before executing.
    """
    def _round(*args, **kwargs):
        raise live.LiveRefused(message)
    return _round


def main() -> int:
    task = rules.make_task("dev", 4)
    original_round = live.run_live_improve_round

    # 1. A round that executed nothing, refusing from inside the round.
    print("round refused before executing anything")
    with tempfile.TemporaryDirectory() as tmp:
        path, store = make_store(tmp)
        package = acquired_package(store, channel.make_control("low"),
                                   "acq-1", channel.IMPROVE_LOW_SOURCE)
        live.adopt_live_revision(store, package, arm="test")
        store.save()
        live.run_live_improve_round = stub_round(
            "rejected: post-restart round refused: live improvement"
            " refused: refused: an owned store executes under the authority"
            " its investigation authorizes", False)
        try:
            record = live.bind_retained_acquisition(
                str(path), acquisition_for(package), task)
            check("raised, not recorded", False,
                  "returned %r" % (record,))
        except live.LiveRefused as exc:
            check("raised, not recorded", True)
            check("the message names the round", "round refused before it"
                  " executed anything" in str(exc))
        finally:
            live.run_live_improve_round = original_round

    # 2. The same round, but it recorded a command, so it ran.
    print("round refused after recording its first step")
    with tempfile.TemporaryDirectory() as tmp:
        path, store = make_store(tmp)
        package = acquired_package(store, channel.make_control("low"),
                                   "acq-2", channel.IMPROVE_LOW_SOURCE)
        live.adopt_live_revision(store, package, arm="test")
        reopened = live.restart_store(str(path))
        # A `round_command` is only accepted with a real evidence record, so
        # one is minted the way a round's first step would mint it.
        receipt = frontier.make_evidence_record(
            "child-execution", "op-round-1", "success",
            receipt_identity="durable:op-round-1", arm="test",
            task_id=task["task_id"], source_digest=package["imp_digest"],
            artifact_digest=package["package_digest"],
            package_digest=package["package_digest"],
            parent_digest=package.get("parent_digest"),
            round_no=int(package.get("version", 0)),
            details={"raw_payload": {"action": {"inputs": {
                "frontier_action": {"kind": "construct"}}}}})
        reopened.record_round_command(
            int(package.get("version", 0)), 0,
            action={"kind": "construct", "inputs": {
                "frontier_action": {"kind": "construct"}}},
            state={}, receipt=receipt,
            executed_digest=package["imp_digest"])
        live.run_live_improve_round = stub_round(
            "rejected: post-restart round produced no usable candidate", True)
        try:
            record = live.bind_retained_acquisition(
                str(path), acquisition_for(package), task)
            check("recorded, not raised", True)
            check("disposition is rejected",
                  record.get("disposition") == "rejected",
                  repr(record.get("disposition")))
        except live.LiveRefused as exc:
            check("recorded, not raised", False, "raised %s" % exc)
        finally:
            live.run_live_improve_round = original_round

    # 3. Refused before any round is entered.
    print("refused before a round is entered")
    with tempfile.TemporaryDirectory() as tmp:
        path, store = make_store(tmp)
        first = acquired_package(store, channel.make_control("low"),
                                 "acq-3a", channel.IMPROVE_LOW_SOURCE)
        live.adopt_live_revision(store, first, arm="test")
        second = acquired_package(store, first, "acq-3b",
                                  channel.IMPROVE_HIGH_SOURCE)
        live.adopt_live_revision(store, second, arm="test")
        store.save()
        try:
            record = live.bind_retained_acquisition(
                str(path), acquisition_for(first), task)
            check("recorded, not raised", True)
            check("disposition is retained",
                  record.get("disposition") == "retained",
                  repr(record.get("disposition")))
        except live.LiveRefused as exc:
            check("recorded, not raised", False, "raised %s" % exc)

    print()
    if FAILURES:
        print("FAILURES: %d  %s" % (len(FAILURES), FAILURES))
        return 1
    print("all three refusal kinds land where they belong")
    return 0


if __name__ == "__main__":
    sys.exit(main())