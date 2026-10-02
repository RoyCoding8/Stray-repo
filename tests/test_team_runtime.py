from __future__ import annotations

import hashlib
import json
import sys
import uuid

import pytest

from psycopg.rows import dict_row

from settlement import broker, context, db, run, store, team
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher


def _cmd(payload=None) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload or {})


BASE = {
    "pkg/__init__.py": "",
    "pkg/a.py": "MODE = 'X'\nVALUE = 1\n",
    "pkg/b.py": "MODE = 'X'\nVALUE = 2\n",
}

CHECK_SRC = """import importlib.util
import json
import sys

asm = sys.argv[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, asm + "/pkg/" + name + ".py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

try:
    a = load("a")
    b = load("b")
    assert a.MODE == b.MODE, "mode mismatch %r vs %r" % (a.MODE, b.MODE)
    assert (a.VALUE, b.VALUE) == (10, 20), "values %r" % ((a.VALUE, b.VALUE),)
    print(json.dumps({"status": "ok", "data": {"mode": a.MODE}}))
except Exception as exc:
    print(json.dumps({"status": "error", "data": {"message": str(exc)}}))
"""

SELECT_SRC = """import importlib.util
import json
import sys

root = sys.argv[1]
order = sys.argv[2].split(",")

def load(base, name):
    spec = importlib.util.spec_from_file_location(name, base + "/pkg/" + name + ".py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

picked = None
for node in order:
    try:
        a = load(root + "/" + node, "a")
        b = load(root + "/" + node, "b")
        assert a.MODE == b.MODE
        assert (a.VALUE, b.VALUE) == (10, 20)
        picked = node
        break
    except Exception:
        continue
if picked is None:
    print(json.dumps({"status": "error", "data": {"message": "no passing candidate"}}))
else:
    print(json.dumps({"status": "ok", "data": {"selected": picked}}))
"""


def _seed(dsn, tag, authorized=1000):
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-root", "domain": "cpu",
                                     "authorized": authorized, "max_occupancy": 16}))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-inv",
                                      "objective": "repair package",
                                      "obligations": {"repair": True}}))
    snap = team.register_snapshot(dsn, _cmd(), dict(BASE))
    assert snap.code == ResultCode.APPLIED
    return {"allocation_id": f"{tag}-root", "investigation_id": f"{tag}-inv",
            "snapshot_digest": snap.data["snapshot_digest"]}


WHOLE_TREE = ["pkg/__init__.py", "pkg/a.py", "pkg/b.py"]


def _children(shape="decompose"):
    if shape == "single":
        return [{"node_id": "w1", "obligation": "fix package",
                 "owned_paths": list(WHOLE_TREE),
                 "output_contract": {"entry": "pkg", "checks": ["public"]},
                 "input_bindings": {"base_a": "pkg/a.py", "base_b": "pkg/b.py"}}]
    if shape == "alternatives":
        return [{"node_id": "w1", "obligation": "whole-task attempt one",
                 "owned_paths": list(WHOLE_TREE),
                 "output_contract": {"entry": "pkg", "checks": ["public"]},
                 "input_bindings": {"base_a": "pkg/a.py", "base_b": "pkg/b.py"}},
                {"node_id": "w2", "obligation": "whole-task attempt two",
                 "owned_paths": list(WHOLE_TREE),
                 "output_contract": {"entry": "pkg", "checks": ["public"]},
                 "input_bindings": {"base_a": "pkg/a.py", "base_b": "pkg/b.py"}}]
    return [{"node_id": "w1", "obligation": "fix module a",
             "owned_paths": ["pkg/a.py"],
             "output_contract": {"entry": "pkg.a", "checks": ["public"]},
             "input_bindings": {"base_a": "pkg/a.py"}},
            {"node_id": "w2", "obligation": "fix module b",
             "owned_paths": ["pkg/b.py"],
             "output_contract": {"entry": "pkg.b", "checks": ["public"]},
             "input_bindings": {"base_b": "pkg/b.py"}}]


def _join_rules(shape="decompose", owner="w1", check_src=CHECK_SRC):
    join = {"single": "accept", "alternatives": "select-one",
            "decompose": "conjunctive"}[shape]
    return {"join": join, "integration_owner": owner,
            "check_entry": "check.py", "checks": {"check.py": check_src}}


def _iface():
    return {"modes": ["C"], "expected": {"a": 10, "b": 20}, "new_paths": []}


def _policy(shape):
    return {"shape": shape, "rationale": "test-selected"}


def _propose(dsn, seed, shape="decompose", **over):
    kw = {"parent_obligation": f"{seed['investigation_id']}:repair",
          "snapshot_digest": seed["snapshot_digest"], "shape": shape,
          "children": _children(shape), "interface_contract": _iface(),
          "join_rules": _join_rules(shape),
          "allocation_id": seed["allocation_id"], "policy_response": _policy(shape)}
    kw.update(over)
    return team.propose_team_plan(dsn, _cmd(), **kw)


def _launchers(tmp_path):
    return {"local-process": LocalLauncher(tmp_path / "runs")}


def _submit_outputs(dsn, plan_id, outputs):
    out = {}
    for node_id, tree in outputs.items():
        reg = team.register_output(dsn, _cmd(), dict(tree))
        assert reg.code == ResultCode.APPLIED
        out[node_id] = reg.data["output_digest"]
    return out


class FakeLauncher:
    launcher_id = "fake-team"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self):
        self.sends: list[str] = []

    def dispatch(self, op):
        from settlement.broker import LaunchOutcome, ReceiptProposal
        self.sends.append(op.operation_id)
        return LaunchOutcome(sent=True, receipt=ReceiptProposal(
            receipt_identity=f"fake:{op.operation_id}", content={"ok": True},
            outcome="success", provenance=self.launcher_id))

    def prior_send(self, operation_id):
        return operation_id in self.sends

    def stop(self, operation_id):
        return False

    def live_ids(self):
        return []

    def is_live(self, operation_id):
        return False

    def read_result(self, operation_id):
        return {"outcome": "success"} if operation_id in self.sends else None


def _dispatch_children(dsn, plan_id, launchers, revision=1):
    from settlement.broker import dispatch_operation
    receipts = {}
    for node in team.child_nodes(dsn, plan_id, revision):
        op_id = team.child_operation(dsn, plan_id, node, revision)
        gen = team.child_attempt(dsn, plan_id, node,
                                 revision)["ownership_generation"]
        status = dispatch_operation(dsn, op_id, launchers=launchers,
                                    ownership_generation=gen)
        assert status.sent_this_call or status.dispatch_state == "observed"
        receipts[node] = [r["receipt_identity"]
                          for r in store.operation_receipts(dsn, op_id)]
        assert receipts[node]
    return receipts


def _submit_node(dsn, plan_id, node, output_digest, receipt_refs, revision=1):
    return team.submit_child(
        dsn, _cmd({"plan_id": plan_id}), plan_revision=revision, node_id=node,
        input_digests=team.expected_inputs(dsn, plan_id, node, revision),
        ownership_generation=team.child_attempt(
            dsn, plan_id, node, revision)["ownership_generation"],
        output_digest=output_digest, receipt_refs=receipt_refs)


def test_policy_selects_shape_from_visible_features():
    solo = team.select_plan({"defect_count": 1, "modules": ["pkg/a.py"],
                             "interface_stable": True, "unclear_diagnosis": False})
    split = team.select_plan({"defect_count": 2, "modules": ["pkg/a.py", "pkg/b.py"],
                              "interface_stable": True, "unclear_diagnosis": False})
    vague = team.select_plan({"defect_count": 2, "modules": ["pkg/a.py", "pkg/b.py"],
                              "interface_stable": False, "unclear_diagnosis": True})
    assert solo["shape"] == "single"
    assert split["shape"] == "decompose"
    assert vague["shape"] == "alternatives"
    renamed = team.select_plan({"task_id": "other-fixture", "defect_count": 1,
                                "modules": ["pkg/a.py"], "interface_stable": True,
                                "unclear_diagnosis": False})
    assert renamed["shape"] == solo["shape"]


def test_propose_refuses_shape_policy_mismatch(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "mismatch")
    refused = _propose(dsn, seed, policy_response={"shape": "single",
                                                   "rationale": "wrong"})
    assert refused.code == ResultCode.INVALID_INPUT


def test_propose_refuses_undeclared_paths(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "undeclared")
    kids = _children()
    kids[0] = dict(kids[0], owned_paths=["pkg/elsewhere.py"])
    refused = _propose(dsn, seed, children=kids)
    assert refused.code == ResultCode.INVALID_INPUT
    assert broker.read_operation(dsn, refused.data.get("child_op", "~none")) is None


def test_propose_refuses_missing_inputs(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "missingin")
    kids = _children()
    kids[1] = dict(kids[1], input_bindings={"base_b": "pkg/ghost.py"})
    refused = _propose(dsn, seed, children=kids)
    assert refused.code == ResultCode.INVALID_INPUT


def test_propose_refuses_unsupported_join(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "badjoin")
    refused = _propose(dsn, seed, join_rules=_join_rules("alternatives"))
    assert refused.code == ResultCode.INVALID_INPUT


def test_propose_refuses_resource_excess_before_dispatch(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "poord", authorized=10)
    refused = _propose(dsn, seed)
    assert refused.code == ResultCode.INSUFFICIENT_RESOURCES
    assert "cover" in refused.detail


def test_propose_refuses_third_child_overlap_and_owner_and_contract(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "limits")
    three = _children() + [dict(_children()[0], node_id="w3",
                                owned_paths=["pkg/__init__.py"])]
    assert _propose(dsn, seed, children=three).code == ResultCode.INVALID_INPUT
    lap = _children()
    lap[1] = dict(lap[1], owned_paths=["pkg/a.py"])
    assert _propose(dsn, seed, children=lap).code == ResultCode.INVALID_INPUT
    assert _propose(dsn, seed,
                     join_rules=_join_rules(owner="")).code == ResultCode.INVALID_INPUT
    assert _propose(dsn, seed,
                     interface_contract={}).code == ResultCode.INVALID_INPUT
    assert _propose(dsn, seed, shape="single",
                     children=_children()).code == ResultCode.INVALID_INPUT


def test_propose_compiles_run_v1_with_paired_check(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "compile")
    proposed = _propose(dsn, seed)
    assert proposed.code == ResultCode.APPLIED
    comp = run.Composition.model_validate(proposed.data["composition"])
    assert comp.version == "run/v1"
    index = run.node_index(comp)
    joins = [n for n in index.values() if isinstance(n, run.JoinNode)]
    assert len(joins) == 1
    needs = set(joins[0].needs.values())
    paired = [index[n] for n in needs if n in index]
    assert any(isinstance(n, run.InvokeNode) and n.effect == "sandbox-exec"
               and "check" in n.node_id for n in paired)
    check = next(n for n in paired if "check" in n.node_id)
    assert "check.py" in json.dumps(check.payload)


def test_children_are_real_attempts_with_team_packets(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "wiring")
    proposed = _propose(dsn, seed)
    assert proposed.code == ResultCode.APPLIED
    plan_id = proposed.data["plan_id"]
    first = team.child_attempt(dsn, plan_id, "w1")
    second = team.child_attempt(dsn, plan_id, "w2")
    assert second["ownership_generation"] == first["ownership_generation"] + 1
    for node in ("w1", "w2"):
        packet = team.child_packet(dsn, plan_id, node)
        assert packet["decision_kind"] == "team"
        assert packet["outcome"] == "ready"
        bound = team.child_binding(dsn, plan_id, node)
        assert bound["rendered_digest"] == packet["rendered_digest"]
        assert bound["input_digest"]
    kinds = team.packet_kinds_used(dsn, plan_id)
    assert kinds == {"team"}


def test_submit_round_trip_and_stale_fencing(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "submit")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    receipts = _dispatch_children(dsn, plan_id, {"local-process": FakeLauncher()})
    outputs = {"w1": {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"},
               "w2": {"pkg/b.py": "MODE = 'C'\nVALUE = 20\n"}}
    digests = _submit_outputs(dsn, plan_id, outputs)
    ok = _submit_node(dsn, plan_id, "w1", digests["w1"], receipts["w1"])
    assert ok.code == ResultCode.APPLIED
    assert ok.data["accepted_for_join"] is True
    stored = team.submission_tuple(dsn, plan_id, 1, "w1")
    assert stored[:2] == (1, "w1") and stored[4] == digests["w1"]
    attempt = team.child_attempt(dsn, plan_id, "w1")
    ghost = team.submit_child(
        dsn, _cmd({"plan_id": plan_id}), plan_revision=1, node_id="w1",
        input_digests=team.expected_inputs(dsn, plan_id, "w1"),
        ownership_generation=attempt["ownership_generation"] + 99,
        output_digest=digests["w1"], receipt_refs=receipts["w1"])
    assert ghost.code == ResultCode.STALE_REVISION
    stale_rev = team.submit_child(
        dsn, _cmd({"plan_id": plan_id}), plan_revision=7, node_id="w2",
        input_digests=team.expected_inputs(dsn, plan_id, "w2"),
        ownership_generation=team.child_attempt(
            dsn, plan_id, "w2")["ownership_generation"],
        output_digest=digests["w2"], receipt_refs=receipts["w2"])
    assert stale_rev.code == ResultCode.STALE_REVISION
    bad_paths = team.register_output(
        dsn, _cmd(), {"pkg/b.py": "MODE = 'C'\n", "pkg/a.py": "hijack\n"})
    trespass = _submit_node(dsn, plan_id, "w2", bad_paths.data["output_digest"],
                            receipts["w2"])
    assert trespass.code == ResultCode.INVALID_INPUT
    forged = _submit_node(dsn, plan_id, "w2", "0" * 64, receipts["w2"])
    assert forged.code == ResultCode.INVALID_INPUT


def test_join_fails_on_incompatible_locals_then_passes_corrected(migrated_db,
                                                                 tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "joinfail")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    launchers = _launchers(tmp_path)
    receipts = _dispatch_children(dsn, plan_id, launchers)
    bad = {"w1": {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"},
           "w2": {"pkg/b.py": "MODE = 'K'\nVALUE = 20\n"}}
    digests = _submit_outputs(dsn, plan_id, bad)
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    assert _submit_node(dsn, plan_id, "w2", digests["w2"],
                        receipts["w2"]).code == ResultCode.APPLIED
    failed = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                    launchers=launchers)
    assert failed.code == ResultCode.OBSERVED_FAILURE
    assert failed.data["candidate_digest"]
    assert failed.data["join_receipt"]
    retained = team.join_record(dsn, plan_id, 1)
    assert retained["passed"] is False
    assert retained["failing_input"] and retained["observed_output"]
    frozen_early = team.freeze_candidate(dsn, _cmd(), plan_id=plan_id,
                                         candidate_digest=failed.data[
                                             "candidate_digest"])
    assert frozen_early.code == ResultCode.INVALID_INPUT


def test_corrected_combination_passes_and_freezes(migrated_db, tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "joinpass")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    launchers = _launchers(tmp_path)
    receipts = _dispatch_children(dsn, plan_id, launchers)
    good = {"w1": {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"},
            "w2": {"pkg/b.py": "MODE = 'C'\nVALUE = 20\n"}}
    digests = _submit_outputs(dsn, plan_id, good)
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    assert _submit_node(dsn, plan_id, "w2", digests["w2"],
                        receipts["w2"]).code == ResultCode.APPLIED
    joined = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                    launchers=launchers)
    assert joined.code == ResultCode.APPLIED
    assert team.join_record(dsn, plan_id, 1)["passed"] is True
    frozen = team.freeze_candidate(dsn, _cmd(), plan_id=plan_id,
                                   candidate_digest=joined.data[
                                       "candidate_digest"])
    assert frozen.code == ResultCode.APPLIED
    late = _submit_node(dsn, plan_id, "w1", digests["w1"], receipts["w1"])
    assert late.code == ResultCode.INVALID_INPUT


def test_single_shape_passes_and_freezes(migrated_db, tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "solo")
    proposed = _propose(dsn, seed, shape="single")
    assert proposed.code == ResultCode.APPLIED
    plan_id = proposed.data["plan_id"]
    assert team.child_nodes(dsn, plan_id) == ["w1"]
    launchers = _launchers(tmp_path)
    receipts = _dispatch_children(dsn, plan_id, launchers)
    whole = dict(BASE, **{"pkg/a.py": "MODE = 'C'\nVALUE = 10\n",
                          "pkg/b.py": "MODE = 'C'\nVALUE = 20\n"})
    digests = _submit_outputs(dsn, plan_id, {"w1": whole})
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    joined = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                    launchers=launchers)
    assert joined.code == ResultCode.APPLIED
    assert team.join_record(dsn, plan_id, 1)["passed"] is True
    frozen = team.freeze_candidate(dsn, _cmd(), plan_id=plan_id,
                                   candidate_digest=joined.data[
                                       "candidate_digest"])
    assert frozen.code == ResultCode.APPLIED
    assert team.team_state(dsn, seed["investigation_id"])["plans"][0][
        "frozen_candidate"] == joined.data["candidate_digest"]


def test_alternatives_selects_passing_tree_by_execution(migrated_db, tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "alt")
    proposed = _propose(dsn, seed, shape="alternatives",
                        join_rules=_join_rules("alternatives", check_src=SELECT_SRC))
    plan_id = proposed.data["plan_id"]
    launchers = _launchers(tmp_path)
    receipts = _dispatch_children(dsn, plan_id, launchers)
    good_tree = dict(BASE, **{"pkg/a.py": "MODE = 'C'\nVALUE = 10\n",
                              "pkg/b.py": "MODE = 'C'\nVALUE = 20\n"})
    bad_tree = dict(BASE, **{"pkg/a.py": "MODE = 'K'\nVALUE = 10\n",
                             "pkg/b.py": "MODE = 'C'\nVALUE = 20\n"})
    digests = _submit_outputs(dsn, plan_id, {"w1": bad_tree, "w2": good_tree})
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    assert _submit_node(dsn, plan_id, "w2", digests["w2"],
                        receipts["w2"]).code == ResultCode.APPLIED
    joined = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                    launchers=launchers)
    assert joined.code == ResultCode.APPLIED
    assert joined.data["candidate_digest"] == digests["w2"]


def test_revision_bounded_with_fencing_and_liability(migrated_db, tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "revise")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    launchers = _launchers(tmp_path)
    receipts = _dispatch_children(dsn, plan_id, launchers)
    digests = _submit_outputs(dsn, plan_id,
                              {"w1": {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"}})
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    kids = _children()
    revised = team.revise_team_plan(dsn, _cmd(), plan_id=plan_id,
                                    children=kids, reason="w2 failed")
    assert revised.code == ResultCode.APPLIED
    assert revised.data["revision"] == 2
    kept = team.submission_tuple(dsn, plan_id, 2, "w1")
    assert kept[4] == digests["w1"]
    with pytest.raises(LookupError):
        team.submission_tuple(dsn, plan_id, 2, "w2")
    again = team.revise_team_plan(dsn, _cmd(), plan_id=plan_id, children=kids,
                                  reason="second")
    assert again.code == ResultCode.INVALID_INPUT
    root = store.allocation_status(dsn, seed["allocation_id"])
    assert root["reserved"] == 0
    assert root["consumed"] >= 0


def test_revision_invalidates_changed_inputs(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "revinv")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    receipts = _dispatch_children(dsn, plan_id, {"local-process": FakeLauncher()})
    digests = _submit_outputs(dsn, plan_id,
                              {"w1": {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"}})
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    kids = _children()
    kids[0] = dict(kids[0], input_bindings={"base_a": "pkg/b.py"})
    revised = team.revise_team_plan(dsn, _cmd(), plan_id=plan_id,
                                    children=kids, reason="rebind w1")
    assert revised.code == ResultCode.APPLIED
    with pytest.raises(LookupError):
        team.submission_tuple(dsn, plan_id, 2, "w1")


def _save_root_continuation(dsn, seed, tmp_path, plan_id):
    roots = tmp_path / "artifacts"
    roots.mkdir(exist_ok=True)
    acquired = store.acquire_work(
        dsn, _cmd({"attempt_id": f"{seed['investigation_id']}-root",
                   "investigation_id": seed["investigation_id"],
                   "allocation_id": seed["allocation_id"]}))
    gen = acquired.data["ownership_generation"]
    saved = context.save_continuation(
        dsn, _cmd(), roots, seed["investigation_id"],
        f"{seed['investigation_id']}-root", team.PROFILE, {"team": plan_id}, [],
        [], {"repair": True}, {"next": "join"},
        ownership_generation=gen)
    assert saved.code == ResultCode.APPLIED


def test_resume_reuses_completed_child_without_resubmission(migrated_db,
                                                            tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "resume")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    _save_root_continuation(dsn, seed, tmp_path, plan_id)
    fake = FakeLauncher()
    receipts = _dispatch_children(dsn, plan_id, {"local-process": fake})
    digests = _submit_outputs(dsn, plan_id,
                              {"w1": {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"}})
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    before = list(fake.sends)
    resumed = team.resume_team(dsn, seed["investigation_id"])
    assert resumed["plans"][0]["plan_id"] == plan_id
    assert resumed["plans"][0]["completed"] == ["w1"]
    assert resumed["plans"][0]["pending"] == ["w2"]
    package = context.resume_package(dsn, seed["investigation_id"])
    assert package["team"]["plans"][0]["plan_id"] == plan_id
    assert package["team"]["submissions"][0]["node_id"] == "w1"
    again = _dispatch_children(dsn, plan_id, {"local-process": fake})
    assert [r for refs in again.values() for r in refs]
    assert fake.sends == before
    with pytest.raises(LookupError):
        team.submission_tuple(dsn, plan_id, 1, "w2")


def _events(dsn, kind):
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT kind, payload FROM domain_events WHERE kind = %s"
                        " ORDER BY epoch, ordinal", (kind,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return rows


def _reservation_state(dsn, reservation_id):
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT state FROM reservations WHERE id = %s",
                        (reservation_id,))
            row = cur.fetchone()
            conn.commit()
    return None if row is None else row["state"]


class NoReceiptLauncher:
    launcher_id = "no-receipt"
    profile = "local-process"
    idempotent_resend = False

    def __init__(self):
        self.sends: list[str] = []

    def dispatch(self, op):
        from settlement.broker import LaunchOutcome
        self.sends.append(op.operation_id)
        return LaunchOutcome(sent=True, receipt=None)

    def prior_send(self, operation_id):
        return False

    def stop(self, operation_id):
        return operation_id in self.sends

    def live_ids(self):
        return []

    def is_live(self, operation_id):
        return False

    def read_result(self, operation_id):
        return None


def test_revise_cancels_inflight_child_through_broker(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "cancelpath")
    proposed = _propose(dsn, seed)
    assert proposed.code == ResultCode.APPLIED
    plan_id = proposed.data["plan_id"]
    old_attempt = proposed.data["child_attempts"]["w1"]
    old_op = proposed.data["child_operations"]["w1"]
    gen = team.child_attempt(dsn, plan_id, "w1")["ownership_generation"]
    status = broker.dispatch_operation(
        dsn, old_op, launchers={"local-process": NoReceiptLauncher()},
        ownership_generation=gen)
    assert status.sent_this_call
    revised = team.revise_team_plan(dsn, _cmd(), plan_id=plan_id,
                                    children=_children(), reason="recall w1")
    assert revised.code == ResultCode.APPLIED
    assert broker.read_operation(dsn, old_op)["cancel_state"] == "confirmed"
    requested = [e for e in _events(dsn, "operation.cancel_requested")
                 if e["payload"].get("operation_id") == old_op]
    confirmed = [e for e in _events(dsn, "operation.cancel_confirmed")
                 if e["payload"].get("operation_id") == old_op]
    assert requested and confirmed
    ended = [e for e in _events(dsn, "work.cancelled")
             if e["payload"].get("attempt_id") == old_attempt]
    assert ended


def test_revise_releases_prepared_child_through_store(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "releasepath")
    proposed = _propose(dsn, seed)
    assert proposed.code == ResultCode.APPLIED
    plan_id = proposed.data["plan_id"]
    old_op = proposed.data["child_operations"]["w1"]
    assert broker.read_operation(dsn, old_op)["dispatch_state"] == "prepared"
    revised = team.revise_team_plan(dsn, _cmd(), plan_id=plan_id,
                                    children=_children(), reason="fresh workers")
    assert revised.code == ResultCode.APPLIED
    assert _reservation_state(dsn, f"res-{old_op}") == "released"
    released = [e for e in _events(dsn, "resources.released")
                if e["payload"].get("reservation_id") == f"res-{old_op}"]
    assert released
    root = store.allocation_status(dsn, seed["allocation_id"])
    assert root["reserved"] == 0


def test_join_refuses_prose_verdict_without_executing_launcher(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "prose")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    receipts = _dispatch_children(dsn, plan_id, {"local-process": FakeLauncher()})
    digests = _submit_outputs(dsn, plan_id,
                              {"w1": {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"},
                               "w2": {"pkg/b.py": "MODE = 'C'\nVALUE = 20\n"}})
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    assert _submit_node(dsn, plan_id, "w2", digests["w2"],
                        receipts["w2"]).code == ResultCode.APPLIED
    refused = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                     launchers={"local-process": FakeLauncher()})
    assert refused.code == ResultCode.INVALID_INPUT
    with pytest.raises(LookupError):
        team.join_record(dsn, plan_id, 1)


def test_children_execute_in_isolated_trees(migrated_db, tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "isolation")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    launcher = LocalLauncher(tmp_path / "runs")
    _dispatch_children(dsn, plan_id, {"local-process": launcher})
    first = launcher.exec_dirs(team.child_operation(dsn, plan_id, "w1"),
                               team.PROFILE)
    second = launcher.exec_dirs(team.child_operation(dsn, plan_id, "w2"),
                                team.PROFILE)
    assert first[0] != second[0] and first[1] != second[1]
    import os
    assert os.path.isdir(first[0]) and os.path.isdir(second[0])


def test_team_packets_are_byte_bound(migrated_db):
    dsn = migrated_db
    seed = _seed(dsn, "bytebound")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    for node in ("w1", "w2"):
        packet = team.child_packet(dsn, plan_id, node)
        assert packet["decision_kind"] == "team"
        assert packet["decision"]["budget"] == {"input_chars": 20000,
                                                "output_reserve": 2000}
        assert packet["token_estimate"]["chars"] <= 20000


def test_alternatives_missing_file_blocks_join(migrated_db, tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "altmissing")
    proposed = _propose(dsn, seed, shape="alternatives",
                        join_rules=_join_rules("alternatives",
                                               check_src=SELECT_SRC))
    plan_id = proposed.data["plan_id"]
    launchers = _launchers(tmp_path)
    receipts = _dispatch_children(dsn, plan_id, launchers)
    thin = {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n",
            "pkg/b.py": "MODE = 'C'\nVALUE = 20\n"}
    digests = _submit_outputs(dsn, plan_id, {"w1": thin,
                                             "w2": dict(BASE, **thin)})
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    assert _submit_node(dsn, plan_id, "w2", digests["w2"],
                        receipts["w2"]).code == ResultCode.APPLIED
    blocked = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                     launchers=launchers)
    assert blocked.code == ResultCode.MISSING_EVIDENCE


def test_failed_join_repeats_without_new_evidence(migrated_db, tmp_path):
    dsn = migrated_db
    seed = _seed(dsn, "repeatfail")
    proposed = _propose(dsn, seed)
    plan_id = proposed.data["plan_id"]
    launchers = _launchers(tmp_path)
    receipts = _dispatch_children(dsn, plan_id, launchers)
    digests = _submit_outputs(dsn, plan_id,
                              {"w1": {"pkg/a.py": "MODE = 'C'\nVALUE = 10\n"},
                               "w2": {"pkg/b.py": "MODE = 'K'\nVALUE = 20\n"}})
    assert _submit_node(dsn, plan_id, "w1", digests["w1"],
                        receipts["w1"]).code == ResultCode.APPLIED
    assert _submit_node(dsn, plan_id, "w2", digests["w2"],
                        receipts["w2"]).code == ResultCode.APPLIED
    first = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                   launchers=launchers)
    assert first.code == ResultCode.OBSERVED_FAILURE
    second = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                    launchers=launchers)
    assert second.code == ResultCode.OBSERVED_FAILURE
    assert second.data["candidate_digest"] == first.data["candidate_digest"]

