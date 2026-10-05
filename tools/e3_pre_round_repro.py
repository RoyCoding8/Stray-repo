"""The pre-round refusal case, at runtime, without a database.

`test_binding_provenance.py::test_retained_but_inactive_never_binds` builds a
nameless store, adopts one revision then a second one, and asks
`bind_retained_acquisition` to bind the first. The second adoption moved the
active package, so `bind_live_revision` refuses at
`adopt_live_revision` -- before any round is entered. The test asserts the
caller is told `retained`, because nothing about the package was decided.

That refusal leaves no `round_command`, which is the same store fact an
ownership refusal leaves. So the discriminator at
`bind_retained_acquisition` cannot tell them apart, and it raises on both.

No round runs in this scenario, so nothing here reaches PostgreSQL.

Run from the repo root:
    python tools/e3_pre_round_repro.py
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
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live


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


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "store.json")
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
        print("store identity: %r" % (getattr(store, "identity", None),))
        store.bind_active(channel.make_control("low"))

        first = acquired_package(store, channel.make_control("low"),
                                 "acquired-first-r1",
                                 channel.IMPROVE_LOW_SOURCE)
        live.adopt_live_revision(store, first, arm="test")
        second = acquired_package(store, first, "acquired-other-r1",
                                  channel.IMPROVE_HIGH_SOURCE)
        live.adopt_live_revision(store, second, arm="test")
        store.save()

        reopened = live.restart_store(str(path))
        version = int(first.get("version", 0))
        print("active is %s; the package asked for is %s" % (
            reopened.active_package["package_digest"][:12],
            first["package_digest"][:12]))
        print("round_command(version=%d, step=0) is %r  <-- the discriminator"
              % (version,
                 reopened.round_command(version, 0)))
        try:
            record = live.bind_retained_acquisition(
                str(path),
                {"status": "retained", "arm": "test",
                 "control_id": first["control_id"],
                 "package_digest": first["package_digest"],
                 "response_digest": first["response_digest"]},
                rules.make_task("dev", 4))
        except live.LiveRefused as exc:
            print("RESULT: raised %s: %s" % (type(exc).__name__, exc))
            print("test asserts disposition == 'retained'.  FAILS.")
            return 1
        print("RESULT: returned %r" % (record,))
        print("test asserts disposition == 'retained'.  PASSES.")
        return 0


if __name__ == "__main__":
    sys.exit(main())