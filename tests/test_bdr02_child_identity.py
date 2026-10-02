"""BDR-02 slice 1: durable child/revision operation identity.

Rejecting tests for review finding BDR-02: run_cell built one
operation_id per cell (coord02-child:<tag>:<task>) and reused it for
every node and invocation, so distinct accepted work shared one
immutable broker identity (INVALID_INPUT on conflicting prompts) while
a rework with the old prompt reused the prior operation instead of a
fresh attempt. DB ec02test_bdr02 only, never ec02test_live.

Required: distinct accepted work gets distinct identity derived from
the admitted plan (plan, revision, node); resuming the same work
preserves it and makes no duplicate model calls; a revision mints fresh
identity for reworked nodes.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from experiments.coord02 import entry
from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import oracle
from experiments.coord02.controller import seed_episode
from experiments.coord02.experience import snapshot_files
from settlement import db
from settlement.gateway import (
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get(
    "EC02_BDR02_DSN",
    "dbname=ec02test_bdr02 host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

TASK = oracle.SPLITS["development"][0]
MARKER = "\n\nBDR02_MODEL_REPAIR = 1\n"


def _fresh_db():
    assert "live" not in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % row[0])
        conn.commit()


class DecomposeRecordingAdapter(GatewayAdapter):
    """Model-seam double: decompose plan, then per-node repair bytes.

    The node served comes from the operation identity itself: the
    durable scheme carries the admitted node id, so each distinct
    child attempt is addressable without reading prompt contents.
    """

    label = "BDR02-RECORDING-DECOMPOSE"

    def __init__(self, task: str, partitions: dict):
        self._task = task
        self._partitions = {k: dict(v) for k, v in partitions.items()}
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        if "a-decision" in request.operation_id:
            proposal = {"action": "plan", "shape": "decompose",
                        "children": entry.plan_children(self._task,
                                                        "decompose")}
            return ModelResponse(request.operation_id, json.dumps(proposal),
                                 {}, Usage(input_tokens=1, output_tokens=1),
                                 "stop")
        match = re.search(r":(w\d+):", request.operation_id)
        node = match.group(1) if match else "w1"
        return ModelResponse(
            request.operation_id,
            json.dumps({"files": self._partitions[node],
                        "notes": "bdr02 per-node repair"}),
            {}, Usage(input_tokens=1, output_tokens=1), "stop")

    def cancel(self, operation_id):
        return False


def _launcher_factory(tag: str) -> dict:
    return {"local-process": LocalLauncher(
        Path(tempfile.mkdtemp(prefix="bdr02-")) / tag)}


def test_two_children_carry_distinct_plan_derived_identities():
    _fresh_db()
    snap = snapshot_files(TASK)
    children = entry.plan_children(TASK, "decompose")
    assert len(children) == 2, "need two admitted children for this test"
    partitions = {c["node_id"]: {p: snap[p] + MARKER
                                 for p in c["owned_paths"]}
                  for c in children}
    gw = DecomposeRecordingAdapter(TASK, partitions)
    freeze = freeze_mod.build_freeze("coord02-bdr02-decompose",
                                     source_sha="bdr02-base")
    cell = entry.run_cell(
        DSN, freeze=freeze, task_id=TASK, panel="development",
        repeat=1, arm="A", launcher_factory=_launcher_factory,
        package_digest="none", package_text="doubled-dev",
        source_sha="bdr02-base", config_digest="entry-bdr02",
        gateway=gw, model="bdr02-decompose-double")
    assert cell.outcome.get("status") in ("success", "join-failed-terminal"), \
        cell.outcome
    child_calls = [c for c in gw.calls if "a-decision" not in c.operation_id]
    assert cell.outcome.get("plan_id"), "no admitted plan on the outcome"
    plan_id = cell.outcome["plan_id"]
    first_round = [c.operation_id for c in child_calls
                   if ":r1:" in c.operation_id]
    assert sorted(first_round) == sorted(
        "%s:r1:%s:work:model" % (plan_id, child["node_id"])
        for child in children), \
        "first-round model calls are not one durable identity per child: %r" \
        % ([c.operation_id for c in child_calls],)
    for call in child_calls:
        assert call.operation_id.startswith(plan_id), \
            "model call %r is not derived from admitted plan %r" % (
                call.operation_id, plan_id)
    reworks = [c.operation_id for c in child_calls if ":r2:" in c.operation_id]
    for rework in reworks:
        node = re.search(r":(w\d+):", rework).group(1)
        assert rework != "%s:r1:%s:work:model" % (plan_id, node), \
            "reworked node reused its prior operation identity: %r" % rework


def test_same_work_resumed_makes_no_duplicate_model_call():
    _fresh_db()
    snap = snapshot_files(TASK)
    owned = sorted(oracle.worker_files(TASK))
    repair = {p: snap[p] + MARKER for p in owned}
    child = {"node_id": "w1", "obligation": "repair whole tree",
             "owned_paths": list(owned),
             "output_contract": {"entry": "whole-tree",
                                 "checks": ["public"]},
             "input_bindings": {"base_%d" % i: p
                                for i, p in enumerate(owned)}}
    seed = seed_episode(DSN, "bdr02-resume-%s" % uuid.uuid4().hex[:8],
                        dict(snap))
    gw = DecomposeRecordingAdapter(TASK, {"w1": repair, "w2": repair})
    op_id = "bdr02-resume-%s:w1" % uuid.uuid4().hex[:8]
    first = entry.dispatch_admitted_child(
        DSN, gateway=gw, model="bdr02-resume-double", task_id=TASK,
        node="w1", child=child, rendered={},
        allocation_id=seed["allocation_id"], operation_id=op_id)
    assert first == repair
    calls_after_first = len(gw.calls)
    second = entry.dispatch_admitted_child(
        DSN, gateway=gw, model="bdr02-resume-double", task_id=TASK,
        node="w1", child=child, rendered={},
        allocation_id=seed["allocation_id"], operation_id=op_id)
    assert second == repair
    assert len(gw.calls) == calls_after_first, \
        "resuming settled work dispatched a duplicate model call"


def test_child_requests_include_bound_contract_and_revision_source():
    _fresh_db()
    snap = snapshot_files(TASK)
    children = entry.plan_children(TASK, "decompose")
    partitions = {c["node_id"]: {p: snap[p] + MARKER
                                 for p in c["owned_paths"]}
                  for c in children}
    gw = DecomposeRecordingAdapter(TASK, partitions)
    cell = entry.run_cell(
        DSN, freeze=freeze_mod.build_freeze("coord02-child-inputs",
                                           source_sha="child-inputs"),
        task_id=TASK, panel="development", repeat=1, arm="A",
        launcher_factory=_launcher_factory, gateway=gw, model="double")
    calls = [c for c in gw.calls if "a-decision" not in c.operation_id]
    assert len(calls) == 3, [c.operation_id for c in calls]
    for call in calls:
        prompt = call.messages[0]["content"]
        assert "Work packet: " in prompt, prompt
        packet = json.loads(prompt.split("Work packet: ", 1)[1].split("\n", 1)[0])
        revision = 2 if ":r2:" in call.operation_id else 1
        assert packet["plan_revision"] == revision
        assert packet["plan_id"] == cell.outcome["plan_id"]
        assert packet["public_contract"]
        assert packet["admitted_observations"]
        assert "obligation" not in packet
        expected = partitions[packet["node_id"]] if revision == 2 else snap
        for path in packet["owned_paths"]:
            assert packet["current_source"][path] == expected[path]
        assert packet["input_digests"]


def test_revision_mints_fresh_child_identity_for_rework():
    from settlement import team
    from settlement.common import Command
    _fresh_db()
    snap = snapshot_files(TASK)
    seed = seed_episode(DSN, "bdr02-rev-%s" % uuid.uuid4().hex[:8],
                        dict(snap))
    children = entry.plan_children(TASK, "decompose")
    admitted = team.propose_team_plan(
        DSN, Command(request_id="bdr02-propose-%s" % uuid.uuid4().hex[:8]),
        parent_obligation="%s:repair" % seed["investigation_id"],
        snapshot_digest=seed["snapshot_digest"], shape="decompose",
        children=children,
        interface_contract={"new_paths": []},
        join_rules={"join": "conjunctive", "integration_owner": "w1",
                    "check_entry": "check.py",
                    "checks": {"check.py": "print('ok')"}},
        allocation_id=seed["allocation_id"],
        policy_response={"shape": "decompose"})
    assert admitted.code.value == "applied", admitted
    plan_id = admitted.data["plan_id"]
    before = {n: team.child_operation(DSN, plan_id, n) for n in ("w1", "w2")}
    revised = team.revise_team_plan(
        DSN, Command(request_id="bdr02-revise-%s" % uuid.uuid4().hex[:8]),
        plan_id=plan_id, children=children,
        interface_contract={"new_paths": []},
        reason="bdr02 rework probe",
        launchers=_launcher_factory("bdr02-rev"),
        rework=["w1"])
    assert revised.code.value == "applied", revised
    after = {n: team.child_operation(DSN, plan_id, n) for n in ("w1", "w2")}
    assert after["w1"] != before["w1"], \
        "reworked node kept its prior operation identity"
    assert ":r2:" in after["w1"], \
        "reworked identity carries no new revision: %r" % after["w1"]
