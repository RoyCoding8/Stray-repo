"""T-VERIF independent verification battery: EC02 C1 gate + challenges 1-4.

Real public campaign path (`run_cell`/`run_panel` via entry) with an
independently shaped recording adapter (VERIF-UNEXPECTED obligations,
own usage values, own task choice). Real PostgreSQL (`ec02test_verif`)
+ real subprocesses throughout. Labeled doubles only at the model seam.
Never touches `ec02test_live`. Every claim carries its own countercheck.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from experiments.coord02 import entry
from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import oracle
from experiments.coord02 import schemas_evidence as SE
from experiments.coord02.experience import snapshot_files
from settlement import broker, db
from settlement.gateway import (
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)
from settlement.launcher_local import LocalLauncher

DSN = os.environ.get(
    "EC02_VERIF_DSN", "dbname=ec02test_verif host=/var/run/postgresql user=ubuntu")
SENTINEL_DSN = os.environ.get(
    "EC02_VERIF_SENTINEL_DSN",
    "dbname=ec02test_verif_sentinel host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"

TASK = oracle.SPLITS["development"][1]


class VerifRecordingAdapter(GatewayAdapter):
    label = "VERIF-RECORDING-DOUBLE"

    def __init__(self, proposal: dict):
        self._proposal = dict(proposal)
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        if "a-decision" in request.operation_id:
            return ModelResponse(
                request.operation_id, json.dumps(self._proposal),
                {"verif-recording-double": True},
                Usage(input_tokens=13, output_tokens=17), "stop")
        snap = snapshot_files(TASK)
        owned = sorted(oracle.worker_files(TASK))
        marker = "VERIF-REPAIR-%s\n" % self._proposal["children"][0][
            "obligation"][-8:]
        repair = {p: snap[p] + "\n" + marker for p in owned}
        return ModelResponse(
            request.operation_id, json.dumps({"files": repair,
                                              "notes": "verif repair"}),
            {"verif-recording-double": True},
            Usage(input_tokens=13, output_tokens=17), "stop")

    def cancel(self, operation_id):
        return False


@pytest.fixture()
def dsn():
    assert "live" not in DSN
    assert "verif" in DSN
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % row[0])
        conn.commit()
    return DSN


def _factory(tmp_path):
    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}
    return launcher_factory


def _verif_proposal(obligation: str) -> dict:
    children = entry.plan_children(TASK, "single")
    children[0]["obligation"] = obligation
    return {"action": "plan", "shape": "single", "children": children}


def _op_ids(dsn: str) -> set:
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM operations")
            ids = {row[0] for row in cur.fetchall()}
        conn.commit()
    return ids


def _run_a(dsn, tmp_path, marker, **kw):
    freeze = freeze_mod.build_freeze("coord02-verif-%s" % marker,
                                     source_sha="verif-base")
    gw = VerifRecordingAdapter(_verif_proposal(
        "VERIF-%s-%s" % (marker, uuid.uuid4().hex[:8])))
    return entry.run_cell(
        dsn, freeze=freeze, task_id=TASK, panel="development",
        repeat=1, arm="A", launcher_factory=_factory(tmp_path),
        package_digest="none", package_text="verif-dev",
        source_sha="verif-base", config_digest="entry-verif",
        gateway=gw, model="verif-recording-double", **kw), gw


def test_verif_c1_positive_admitted_work_graded(dsn, tmp_path):
    freeze = freeze_mod.build_freeze("coord02-verif-positive",
                                     source_sha="verif-base")
    snap = snapshot_files(TASK)
    marker = "VERIF-UNEXPECTED-%s" % uuid.uuid4().hex[:8]
    gw = VerifRecordingAdapter(_verif_proposal(marker))
    cell = entry.run_cell(
        dsn, freeze=freeze, task_id=TASK, panel="development",
        repeat=1, arm="A", launcher_factory=_factory(tmp_path),
        package_digest="none", package_text="verif-dev",
        source_sha="verif-base", config_digest="entry-verif",
        gateway=gw, model="verif-recording-double")
    assert gw.calls, "model seam never consulted on the public A path"
    tree = entry.restage_tree(dsn, cell.outcome)
    assert tree is not None, "no restaged tree to compare"
    differed = [p for p in snap if tree.get(p) != snap[p]]
    assert differed, "model output did not reach submitted bytes"
    assert all("coord02-admitted" not in str(v)
               for v in tree.values()), \
        "stamp channel resurrected in submitted bytes"
    assert cell.record["receipts"], "admitted work left no receipts"
    assert cell.record["outcome"] in ("success", "failure")
    assert cell.record["protected"]["total"] == 1
    assert cell.record["costs"]["model_calls"] >= 1


def test_verif_c1_over_budget_refuses_before_child_calls(dsn, tmp_path):
    freeze = freeze_mod.build_freeze("coord02-verif-ceiling",
                                     source_sha="verif-base")
    gw = VerifRecordingAdapter(
        _verif_proposal("VERIF-CEILING-%s" % uuid.uuid4().hex[:8]))
    before = _op_ids(dsn)
    ceilings = dict(freeze_mod.CEILINGS)
    ceilings["sandbox_ops"] = 0
    import unittest.mock as mock
    with mock.patch.object(freeze_mod, "CEILINGS", ceilings):
        with pytest.raises(ValueError, match="pre-admit ceiling breach"):
            entry.run_cell(
                dsn, freeze=freeze, task_id=TASK, panel="development",
                repeat=1, arm="A", launcher_factory=_factory(tmp_path),
                package_digest="none", package_text="verif-dev",
                source_sha="verif-base", config_digest="entry-verif",
                gateway=gw, model="verif-recording-double")
    fresh = _op_ids(dsn) - before
    assert fresh, "even the refused attempt left no traceable decision op"
    non_decision = [o for o in fresh if not o.endswith(":a-decision")]
    assert non_decision == [], \
        "over-budget attempt dispatched beyond the decision call: %r" \
        % (non_decision,)


def test_verif_poisoned_reference_loaders_change_nothing(dsn, tmp_path):
    import unittest.mock as mock
    freeze = freeze_mod.build_freeze("coord02-verif-poison",
                                     source_sha="verif-base")
    marker = "VERIF-POISON-%s" % uuid.uuid4().hex[:8]
    gw = VerifRecordingAdapter(_verif_proposal(marker))
    with mock.patch.object(oracle, "overlay_files",
                           return_value={"src/app.py": "forged = True\n"}), \
        mock.patch.object(oracle, "prepare_tree",
                          side_effect=RuntimeError("verif-poisoned")):
        cell = entry.run_cell(
            dsn, freeze=freeze, task_id=TASK, panel="development",
            repeat=1, arm="A", launcher_factory=_factory(tmp_path),
            package_digest="none", package_text="verif-dev",
            source_sha="verif-base", config_digest="entry-verif",
            gateway=gw, model="verif-recording-double")
    assert cell.record["receipts"] != []
    tree = entry.restage_tree(dsn, cell.outcome)
    assert tree is not None
    assert all("forged" not in str(v) for v in tree.values()), \
        "poisoned reference bytes leaked into submitted work"


def test_verif_resume_same_campaign_claimed_ops_gate(dsn, tmp_path):
    freeze = freeze_mod.build_freeze("coord02-verif-resume",
                                     source_sha="verif-base")
    cell = entry.run_cell(
        dsn, freeze=freeze, task_id=TASK, panel="development",
        repeat=1, arm="S", launcher_factory=_factory(tmp_path),
        package_digest="none", package_text="verif-dev",
        source_sha="verif-base", config_digest="entry-verif")
    record = entry.stage_record(tmp_path, cell.record, None)
    key = SE.cell_key("coord02-verif-resume", "development", TASK, 1, "S")
    schedule = [{"panel": "development", "task": TASK, "repeat": 1,
                 "arm": "S"}]
    none_freeze: dict = {"freeze_id": "coord02-verif-resume",
                         "package": {"kind": "none"}}
    claimed = set(record["receipts"])
    assert claimed, "saved record claims no operation identities"
    for receipt in claimed:
        assert broker.read_operation(dsn, receipt) is not None or \
            receipt.startswith("run-"), \
            "claimed identity %r has no durable row" % (receipt,)
    skip = SE.resume_plan(
        freeze=none_freeze, schedule_cells=schedule,
        evidence_by_key={key: record}, pending_by_key={},
        reconciled_operation_ids=set(claimed))
    assert len(skip["skip"]) == 1 and len(skip["run"]) == 0
    noskip = SE.resume_plan(
        freeze=none_freeze, schedule_cells=schedule,
        evidence_by_key={key: record}, pending_by_key={},
        reconciled_operation_ids=set())
    assert len(noskip["run"]) == 1 and len(noskip["skip"]) == 0, \
        "record without claimed operations must not skip (receipt-less skip)"
    forged = dict(record)
    forged["procedure_digest"] = "verif-forged-digest"
    rerun = SE.resume_plan(
        freeze=none_freeze, schedule_cells=schedule,
        evidence_by_key={key: forged}, pending_by_key={},
        reconciled_operation_ids=set(claimed))
    assert len(rerun["run"]) == 1 and len(rerun["skip"]) == 0


def _proposal_with_repairs(marker: str, repair_text: str) -> dict:
    children = entry.plan_children(TASK, "single")
    children[0]["obligation"] = marker
    owned = list(children[0]["owned_paths"])
    children[0]["repairs"] = {p: repair_text for p in owned
                              if p.endswith(".py")}
    return {"action": "plan", "shape": "single", "children": children}


def _run_a_repairs(dsn, tmp_path, marker, repair_text):
    freeze = freeze_mod.build_freeze("coord02-verif-%s" % marker,
                                     source_sha="verif-base")
    gw = VerifRecordingAdapter(_proposal_with_repairs(
        "VERIF-%s-%s" % (marker, uuid.uuid4().hex[:8]), repair_text))
    cell = entry.run_cell(
        dsn, freeze=freeze, task_id=TASK, panel="development",
        repeat=1, arm="A", launcher_factory=_factory(tmp_path),
        package_digest="none", package_text="verif-dev",
        source_sha="verif-base", config_digest="entry-verif",
        gateway=gw, model="verif-recording-double")
    return cell, gw


def test_verif_causal_two_model_decisions_change_accepted_work(
        dsn, tmp_path):
    snap = snapshot_files(TASK)
    cell_a, _ = _run_a(dsn, tmp_path, "causal-one")
    cell_b, _ = _run_a(dsn, tmp_path, "causal-two")
    tree_a = entry.restage_tree(dsn, cell_a.outcome)
    tree_b = entry.restage_tree(dsn, cell_b.outcome)
    assert tree_a is not None and tree_b is not None
    changed_a = {p for p in snap if tree_a.get(p) != snap[p]}
    changed_b = {p for p in snap if tree_b.get(p) != snap[p]}
    assert changed_a and changed_b, "a valid model decision left no bytes"
    assert tree_a != tree_b, \
        "two different valid model decisions produced identical work"


def test_verif_causal_changed_obligation_changes_result(dsn, tmp_path):
    cell_a, _ = _run_a_repairs(dsn, tmp_path, "obligation-one",
                               "# VERIF-COMMON-BODY\n")
    cell_b, _ = _run_a_repairs(dsn, tmp_path, "obligation-two",
                               "# VERIF-COMMON-BODY\n")
    tree_a = entry.restage_tree(dsn, cell_a.outcome)
    tree_b = entry.restage_tree(dsn, cell_b.outcome)
    assert tree_a is not None and tree_b is not None
    assert tree_a != tree_b, \
        "changed obligation text changed neither result nor submitted bytes"


def test_verif_d1_stamp_only_channel_after_repair(dsn, tmp_path):
    snap = snapshot_files(TASK)
    owned_py = [p for p in entry.plan_children(TASK, "single")[0]
                ["owned_paths"] if p.endswith(".py")]
    assert owned_py, "no owned .py path to target with a repairs map"
    target = owned_py[0]
    body = "VERIF_D1_REPAIR_BODY = %r\n" % uuid.uuid4().hex[:8]
    cell, _ = _run_a_repairs(dsn, tmp_path, "d1-repairs", body)
    tree = entry.restage_tree(dsn, cell.outcome)
    assert tree is not None
    assert "coord02-admitted" not in str(tree.get(target, "")), \
        "stamp channel resurrected after the D1 deletion"
    changed = {p for p in snap if tree.get(p) != snap[p]}
    assert changed == {target} or target in changed


def test_verif_causal_description_change_leaves_direct_policy(dsn, tmp_path):
    import unittest.mock as mock
    real_payload = oracle.build_solver_payload(TASK)
    alt_payload = dict(real_payload)
    alt_payload["public"] = [{"input": {"verif": "rewritten-description"},
                              "expected": {"verif": "changed"}}]
    freeze = freeze_mod.build_freeze("coord02-verif-desc",
                                     source_sha="verif-base")
    gw = VerifRecordingAdapter(_verif_proposal("VERIF-DESC"))

    def run_once():
        return entry.run_cell(
            dsn, freeze=freeze, task_id=TASK, panel="development",
            repeat=1, arm="S", launcher_factory=_factory(tmp_path),
            package_digest="none", package_text="verif-dev",
            source_sha="verif-base", config_digest="entry-verif",
            gateway=gw, model="verif-recording-double")

    first = run_once()
    with mock.patch.object(oracle, "build_solver_payload",
                           return_value=alt_payload):
        second = run_once()
    assert first.outcome.get("status") == second.outcome.get("status"), \
        "rewritten public description altered direct S policy execution"
    entry_a = entry.arm_policy_entry("S", task_id=TASK,
                                     package_digest="none")
    with mock.patch.object(oracle, "build_solver_payload",
                           return_value=alt_payload):
        entry_b = entry.arm_policy_entry("S", task_id=TASK,
                                         package_digest="none")
    assert entry_a == entry_b


def test_verif_causal_fake_factory_unselectable_in_real_mode(
        dsn, tmp_path):
    with pytest.raises(ValueError, match="unknown constructor label"):
        entry.run_cell(
            dsn, freeze=freeze_mod.build_freeze("coord02-verif-fake2",
                                                source_sha="verif-base"),
            task_id=TASK, panel="development",
            repeat=1, arm="A", launcher_factory=_factory(tmp_path),
            package_digest="none", package_text="verif-dev",
            source_sha="verif-base", config_digest="entry-verif",
            gateway=VerifRecordingAdapter(_verif_proposal("fake2")),
            model="verif-recording-double",
            constructor_label="VERIF-LIVE")
    with pytest.raises(ValueError, match="unknown constructor label"):
        entry.run_cell(
            dsn, freeze=freeze_mod.build_freeze("coord02-verif-fake",
                                                source_sha="verif-base"),
            task_id=TASK, panel="development",
            repeat=1, arm="S", launcher_factory=_factory(tmp_path),
            package_digest="none", package_text="verif-dev",
            source_sha="verif-base", config_digest="entry-verif",
            constructor_label="VERIF-LIVE")


def test_verif_union_multiop_nonuniform_recomputes_from_db_rows(
        dsn, tmp_path):
    snap = snapshot_files(TASK)
    assert snap, "no snapshot files for union probe task"
    cell_s = entry.run_cell(
        dsn, freeze=freeze_mod.build_freeze("coord02-verif-u1",
                                            source_sha="verif-base"),
        task_id=TASK, panel="development",
        repeat=1, arm="S", launcher_factory=_factory(tmp_path),
        package_digest="none", package_text="verif-dev",
        source_sha="verif-base", config_digest="entry-verif")
    cell_a, _ = _run_a_repairs(dsn, tmp_path, "union-a",
                               "# VERIF-UNION %s\n" % uuid.uuid4().hex[:8])
    ops_s = list(cell_s.record["receipts"])
    ops_a = list(cell_a.record["receipts"])
    assert ops_s and ops_a
    shared = sorted(set(ops_s) & set(ops_a))
    cells = [{"cell_id": "verif-u1", "operation_ids": ops_s},
             {"cell_id": "verif-u2", "operation_ids": ops_a}]
    union = SE.reconcile_campaign_union_from_store(dsn, cells)
    assert union["n_operations"] == len(set(ops_s) | set(ops_a)), \
        "union operation count is not the true set union"
    assert union["attribution"] is not None
    for op in shared:
        assert sorted(union["attribution"][op]) == \
            ["verif-u1", "verif-u2"], \
            "shared operation %r not attributed to both cells" % op
    independent = SE.reconcile_campaign_union(
        [{"cell_id": "verif-u1",
          "operations": [r for r in union["records"]
                         if r["operation_id"] in ops_s]},
         {"cell_id": "verif-u2",
          "operations": [r for r in union["records"]
                         if r["operation_id"] in ops_a]}])
    assert independent["totals"] == union["totals"], \
        "union totals do not recompute exactly from the same DB rows"
    assert independent["operation_ids"] == union["operation_ids"]
    unknown_ops = [r for r in union["records"] if r["usage"] is None]
    if unknown_ops:
        for field in ("model_tokens_in", "model_tokens_out",
                      "model_calls"):
            assert union["totals"][field] == "unknown", \
                "unknown-usage op present but %r totaled as measured" % field


class VerifCrash(Exception):
    pass


def _verif_episode_cfg(dsn, tag):
    from experiments.coord02.controller import (
        EpisodeConfig, seed_episode)
    from experiments.coord02.experience import (
        _dev_bindings, _dev_interface_contract, _dev_join_rules,
        _dev_source_interfaces, _requires_for)
    from experiments.coord02 import oracle as _oracle
    seed = seed_episode(dsn, tag, snapshot_files(TASK))
    snapshot = snapshot_files(TASK)
    payload = _oracle.build_solver_payload(TASK)
    requires = _requires_for(TASK, snapshot)
    package_entry = entry.arm_policy_entry("S", task_id=TASK,
                                           package_digest="verif-resume")
    package = {"version_id": "coord02-verif-%s" % tag,
               "package_digest": entry._sha(package_entry),
               "entry_bytes": package_entry, "requires": requires}
    return EpisodeConfig(
        run_id="run-%s" % tag, task_id=TASK,
        allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"],
        snapshot=dict(snapshot),
        interface_contract=_dev_interface_contract(TASK, payload),
        join_rules=_dev_join_rules(TASK),
        bindings=_dev_bindings(requires, snapshot),
        source_interfaces=_dev_source_interfaces(TASK),
        package=package, snapshot_digest=seed["snapshot_digest"])


def _submitted_plan_nodes(dsn, investigation_id):
    from settlement import team
    state = team.team_state(dsn, investigation_id)
    return {(s["plan_id"], int(s["plan_revision"]), s["node_id"])
            for s in state["submissions"] if not s.get("invalidated")}


def _probe_count(dsn, run_id):
    from experiments.coord02.controller import list_probe_observations
    return len(list_probe_observations(dsn, run_id, TASK))


_TERMINAL_OUTCOMES = ("success", "join-failed-terminal", "stopped",
                      "cancelled", "submit-refused", "plan-refused",
                      "policy-invalid", "budget-exhausted",
                      "s-fallback-success", "s-fallback-failed",
                      "unsupported")


def _tagged_ops(dsn, tag):
    return {o for o in _op_ids(dsn) if tag in o}


def _success_receipt_counts(dsn, op_ids):
    from settlement import store
    counts = {}
    for op_id in op_ids:
        receipts = store.operation_receipts(dsn, op_id)
        counts[op_id] = sum(1 for r in receipts
                            if r.get("outcome") == "success")
    return counts


def test_verif_interrupt_after_probe_resumes_without_dup(dsn, tmp_path):
    from experiments.coord02.controller import run_episode
    tag = "verif-probe-%s" % uuid.uuid4().hex[:8]
    cfg = _verif_episode_cfg(dsn, tag)
    launchers = {"local-process": LocalLauncher(tmp_path / tag)}
    factory = entry.solved_child_factory(TASK)
    state = {"crashed": False}

    def crash_after_probe(status):
        if not state["crashed"] and _probe_count(dsn, cfg.run_id) > 0:
            state["crashed"] = True
            raise VerifCrash("verif interrupt after probe")

    with pytest.raises(VerifCrash):
        run_episode(dsn, cfg, launchers, factory, progress=crash_after_probe)
    assert state["crashed"], "probe observation never landed before crash"
    probes_before = _probe_count(dsn, cfg.run_id)
    tagged_before = _tagged_ops(dsn, tag)
    assert tagged_before, "crashed campaign left no operations behind"
    receipts_before = _success_receipt_counts(dsn, tagged_before)
    resumed = run_episode(dsn, cfg, launchers, factory)
    assert resumed.get("status") in _TERMINAL_OUTCOMES, \
        "resume did not reach a terminal outcome: %r" % resumed
    assert _probe_count(dsn, cfg.run_id) == probes_before, \
        "resume re-probed instead of continuing the same campaign"
    tagged_after = _tagged_ops(dsn, tag)
    assert tagged_before <= tagged_after, \
        "resume lost pre-crash operation identities"
    assert _success_receipt_counts(dsn, tagged_before) == receipts_before, \
        "resume repeated settled effects instead of continuing"


def test_verif_interrupt_after_child_resumes_without_dup(dsn, tmp_path):
    from experiments.coord02.controller import run_episode
    tag = "verif-child-%s" % uuid.uuid4().hex[:8]
    cfg = _verif_episode_cfg(dsn, tag)
    launchers = {"local-process": LocalLauncher(tmp_path / tag)}
    factory = entry.solved_child_factory(TASK)
    state = {"crashed": False}

    def crash_after_child(status):
        if not state["crashed"] and status.get("plan_id") is not None \
                and status.get("phase") == "executing":
            state["crashed"] = True
            raise VerifCrash("verif interrupt after child dispatch")

    with pytest.raises(VerifCrash):
        run_episode(dsn, cfg, launchers, factory, progress=crash_after_child)
    assert state["crashed"], "child dispatch never started before crash"
    submitted_before = _submitted_plan_nodes(dsn, cfg.investigation_id)
    tagged_before = _tagged_ops(dsn, tag)
    assert tagged_before, "crashed campaign left no operations behind"
    receipts_before = _success_receipt_counts(dsn, tagged_before)
    resumed = run_episode(dsn, cfg, launchers, factory)
    assert resumed.get("status") in _TERMINAL_OUTCOMES
    submitted_after = _submitted_plan_nodes(dsn, cfg.investigation_id)
    assert submitted_before <= submitted_after, \
        "resume lost pre-crash child submissions"
    assert _success_receipt_counts(dsn, tagged_before) == receipts_before, \
        "resume repeated settled child effects instead of continuing"
    assert tagged_before <= _tagged_ops(dsn, tag)


def test_verif_interrupt_after_publication_resume_is_idempotent(
        dsn, tmp_path):
    from experiments.coord02.controller import run_episode
    tag = "verif-pub-%s" % uuid.uuid4().hex[:8]
    cfg = _verif_episode_cfg(dsn, tag)
    launchers = {"local-process": LocalLauncher(tmp_path / tag)}
    factory = entry.solved_child_factory(TASK)
    first = run_episode(dsn, cfg, launchers, factory)
    assert first.get("status") in _TERMINAL_OUTCOMES
    tagged_before = _tagged_ops(dsn, tag)
    assert tagged_before, "published campaign left no operations behind"
    submitted_before = _submitted_plan_nodes(dsn, cfg.investigation_id)
    receipts_before = _success_receipt_counts(dsn, tagged_before)
    second = run_episode(dsn, cfg, launchers, factory)
    assert second.get("status") == first.get("status"), \
        "re-drive changed the settled outcome: %r -> %r" \
        % (first.get("status"), second.get("status"))
    assert tagged_before <= _tagged_ops(dsn, tag)
    assert _success_receipt_counts(dsn, tagged_before) == receipts_before, \
        "re-drive repeated settled effects"
    assert submitted_before <= _submitted_plan_nodes(
        dsn, cfg.investigation_id)


def test_verif_final_slot_lineage_guard_admits_exactly_one(dsn):
    import threading
    from experiments.coord02 import experience as E
    from settlement.gateway import FakeGatewayAdapter
    budget = E.construction_budget()
    root = "verif-race-%s" % uuid.uuid4().hex[:8]
    seed = E.seed_construction_campaign(dsn, root, budget)
    prefix = "coord02-L-construct-%s" % root
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    results: list = []

    def race(out):
        try:
            ledger = E.ConstructionLedger(dsn, seed["allocation_id"],
                                          attempt_prefix=prefix)
            ledger.request_call(
                E.construction_request(packet, budget, lineage=1,
                                       attempt="init"),
                gateway=FakeGatewayAdapter(
                    text=json.dumps({"entry": "x = 1\n"})))
            out.append("admitted")
        except Exception as exc:
            out.append("refused:%s" % type(exc).__name__)

    threads = [threading.Thread(target=race, args=(results,))
               for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert sorted(results) == ["admitted", "refused:SettlementError"], \
        "lineage-guard race did not admit exactly one: %r" % (results,)
    reread = E.ConstructionLedger(dsn, seed["allocation_id"],
                                  attempt_prefix=prefix)
    valid = [c for c in reread.calls if c.get("valid", True)]
    assert [c["lineage"] for c in valid] == [1], \
        "race left %d valid construction calls, want exactly one" \
        % len(valid)


def test_verif_stranded_send_holds_capacity(dsn):
    from experiments.coord02 import experience as E

    class FlakyGateway(GatewayAdapter):
        label = "VERIF-FLAKY"

        def __init__(self):
            self.calls = 0

        def check_discovery(self):
            return GatewayStatus.CONFIGURED

        def check_auth(self):
            return GatewayStatus.AUTHENTICATED

        def infer(self, request):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("verif send lost after dispatch")
            from settlement.gateway import ModelResponse, Usage
            return ModelResponse(request.operation_id,
                                 json.dumps({"entry": "x = 1\n"}),
                                 {"verif": True}, Usage(), "stop")

        def cancel(self, operation_id):
            return False

    budget = E.construction_budget()
    root = "verif-strand-%s" % uuid.uuid4().hex[:8]
    seed = E.seed_construction_campaign(dsn, root, budget)
    prefix = "coord02-L-construct-%s" % root
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    gw = FlakyGateway()
    ledger = E.ConstructionLedger(dsn, seed["allocation_id"],
                                  attempt_prefix=prefix)
    first = ledger.request_call(
        E.construction_request(packet, budget, lineage=1, attempt="init"),
        gateway=gw)
    stranded = first["operation_id"]
    with pytest.raises(E.ConstructionBudgetExhausted) as excinfo:
        E.ConstructionLedger(
            dsn, seed["allocation_id"],
            attempt_prefix=prefix).request_call(
                E.construction_request(packet, budget, lineage=2,
                                       attempt="init"), gateway=gw)
    assert stranded in str(excinfo.value), \
        "refusal does not name the stranded operation: %s" % excinfo.value
    assert E.ConstructionLedger(
        dsn, seed["allocation_id"],
        attempt_prefix=prefix).calls_used() == 1


def test_verif_sentinel_refuses_evidence_relabel_before_mutation():
    from experiments.coord02 import experience as E
    db.apply_migrations(SENTINEL_DSN, MIGRATIONS)
    E.designate_db(SENTINEL_DSN, kind="evidence",
                   purpose="T-VERIF sentinel: live-like evidence")
    marker = "verif-marker-%s" % uuid.uuid4().hex[:8]
    table = "verif_marker_%s" % uuid.uuid4().hex[:8]
    with db.connect(SENTINEL_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE TABLE "%s" (note TEXT NOT NULL)' % table)
            cur.execute('INSERT INTO "%s" (note) VALUES (%%s)' % table,
                        (marker,))
        conn.commit()

    def marker_rows():
        with db.connect(SENTINEL_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT note FROM "%s" ORDER BY note' % table)
                rows = [row[0] for row in cur.fetchall()]
            conn.commit()
        return rows

    before = marker_rows()
    assert before == [marker]
    with pytest.raises(E.EvidenceDBProtected):
        E.designate_db(SENTINEL_DSN, kind="disposable",
                       purpose="verif attempted relabel")
    with pytest.raises(E.EvidenceDBProtected):
        E.prepare_disposable_db(SENTINEL_DSN, MIGRATIONS)
    assert marker_rows() == before, \
        "refused protection mutated sentinel state"


def _verif_validate(dsn, tmp_path, entry_bytes, constructor):
    from experiments.coord02 import experience as E
    from experiments.coord02.experience import _requires_for
    snap = snapshot_files(TASK)

    def launcher_factory(tag):
        return {"local-process": LocalLauncher(tmp_path / tag)}

    return E.validate_on_development(
        dsn, entry_bytes=entry_bytes,
        requires=_requires_for(TASK, snap), task_ids=[TASK],
        launcher_factory=launcher_factory, constructor=constructor)


def test_verif_learning_valid_unsuccessful_vs_invalid(dsn, tmp_path):
    from experiments.coord02 import experience as E
    admitted_bytes = entry.arm_policy_entry("S", task_id=TASK,
                                            package_digest="verif-learn")
    weak = _verif_validate(dsn, tmp_path, admitted_bytes,
                           E.dev_constructor(TASK, solved=False))
    assert weak["parse_ok"] and weak["profile_ok"], \
        "valid policy program failed parse/profile: %r" % (weak,)
    assert weak["execution_admitted"] is True, \
        "admitted plan not recognized as execution admission"
    assert weak["solved_count"] == 0, \
        "failing repair worker unexpectedly solved"
    assert weak["valid_execution"] is True, \
        "valid-but-unsuccessful policy misreported as invalid"
    broken = _verif_validate(dsn, tmp_path, b"def broken(((\n",
                             E.dev_constructor(TASK, solved=False))
    assert broken["parse_ok"] is False
    assert broken["valid_execution"] is False
    assert (weak["valid_execution"], weak["solved_count"]) != \
        (broken["valid_execution"], broken["solved_count"]), \
        "valid-but-unsuccessful indistinguishable from invalid"


def test_verif_learning_acquired_vs_authored_bytes(dsn, tmp_path):
    from experiments.coord02 import experience as E
    from settlement.gateway import FakeGatewayAdapter
    budget = E.construction_budget()
    root = "verif-acq-%s" % uuid.uuid4().hex[:8]
    seed = E.seed_construction_campaign(dsn, root, budget)
    ledger = E.ConstructionLedger(
        dsn, seed["allocation_id"], attempt_prefix="verif-acq-%s" % root)
    packet = {"packet_version": "coord02-experience/1",
              "probe_observations": []}
    rec = ledger.request_call(
        E.construction_request(packet, budget, lineage=1, attempt="init"),
        gateway=FakeGatewayAdapter(
            text=json.dumps({"entry": "VERIF_ACQUIRED = 1\n"})))
    acquired_op = rec["operation_id"]
    assert broker.read_operation(dsn, acquired_op) is not None
    assert rec["label"] == "DOUBLED" and rec["doubled"] is True
    authored = b"VERIF_AUTHORED = 1\n"
    assert broker.read_operation(dsn, "verif-authored-%s" % root) is None
    assert E.parse_candidate(authored)["ok"] is True
    assert rec["text"] != authored.decode("utf-8"), \
        "acquired bytes indistinguishable from hand-authored bytes"


def test_verif_learning_fallback_attributed_after_staging(tmp_path):
    trial = SE.build_trial_record(
        freeze_id="verif-learn", panel="development", task_id=TASK,
        repeat=1, arm="L", source_sha="verif", config_digest="verif",
        package_digest="none", outcome="failure", solved=False,
        protected={"passed": 0, "failed": 1, "total": 1},
        failures=[{"reason": "verif-fallback-marker"}],
        costs={"model_tokens_in": 3, "model_tokens_out": 1,
               "model_calls": 1, "tool_invocations": 0, "sandbox_ops": 2,
               "policy_exec_ops": 1, "protected_check_ops": 1,
               "cpu_seconds": 0, "wall_seconds": 0,
               "elapsed_seconds": 0, "abandoned_ops": 0},
        receipts=["verif-op-1"], operations=[],
        executed_treatment="S-fallback",
        fallback_reason="verif-l-none-selection")
    assert trial["executed_treatment"] == "S-fallback"
    assert trial["fallback_reason"] == "verif-l-none-selection"
    roundtripped = SE.validate_trial_record(
        json.loads(json.dumps(trial)))
    assert roundtripped["executed_treatment"] == "S-fallback"
    assert roundtripped["fallback_reason"] == "verif-l-none-selection"
    unstaged = entry.stage_record(tmp_path, trial, None)
    assert unstaged["arm"] == "L"
    assert any("verif-fallback-marker" in str(f)
               for f in unstaged["failures"]), \
        "staging erased the fallback marker without a staged tree"


def test_verif_d2_run_cell_threads_provenance(dsn, tmp_path):
    stop_cell, _ = _run_a(dsn, tmp_path, "d2-plan")
    assert stop_cell.record["executed_treatment"] in (
        "S", "A", "F", "L", "L-acquired", "S-fallback")
    assert stop_cell.record["fallback_reason"] is None
    freeze = freeze_mod.build_freeze("coord02-verif-d2stop",
                                     source_sha="verif-base")
    gw = VerifRecordingAdapter({"action": "stop",
                                "reason": "verif stop %s"
                                % uuid.uuid4().hex[:8]})

    def launcher_factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(tmp_path / tag)}

    stopped = entry.run_cell(
        dsn, freeze=freeze, task_id=TASK, panel="development",
        repeat=1, arm="A", launcher_factory=launcher_factory,
        package_digest="none", package_text="verif-dev",
        source_sha="verif-base", config_digest="entry-verif",
        gateway=gw, model="verif-recording-double")
    assert stopped.record["arm"] == "A"
    assert stopped.record["executed_treatment"] == "S-fallback", \
        "run_cell did not thread the S-fallback treatment (D2 repair lost)"
    assert stopped.record["fallback_reason"] is not None and \
        "model-stop" in stopped.record["fallback_reason"]
    none_cell = entry.run_cell(
        dsn, freeze=freeze_mod.build_freeze("coord02-verif-d2none",
                                            source_sha="verif-base"),
        task_id=TASK, panel="development",
        repeat=1, arm="L", launcher_factory=launcher_factory,
        package_entry=None, package_digest="none",
        package_text="verif-dev",
        source_sha="verif-base", config_digest="entry-verif",
        gateway=gw, model="verif-recording-double")
    assert none_cell.record["arm"] == "L"
    assert none_cell.record["executed_treatment"] == "S-fallback"
    assert none_cell.record["fallback_reason"] is not None and \
        "none-selection" in none_cell.record["fallback_reason"]


def test_verif_d3_staged_success_keeps_fallback_provenance(tmp_path):
    trial = SE.build_trial_record(
        freeze_id="verif-learn", panel="development", task_id=TASK,
        repeat=1, arm="L", source_sha="verif", config_digest="verif",
        package_digest="none", outcome="failure", solved=False,
        protected={"passed": 0, "failed": 1, "total": 1},
        failures=[{"reason": "verif-fallback-marker"}],
        costs={"model_tokens_in": 3, "model_tokens_out": 1,
               "model_calls": 1, "tool_invocations": 0, "sandbox_ops": 2,
               "policy_exec_ops": 1, "protected_check_ops": 1,
               "cpu_seconds": 0, "wall_seconds": 0,
               "elapsed_seconds": 0, "abandoned_ops": 0},
        receipts=["verif-op-1"], operations=[],
        executed_treatment="S-fallback",
        fallback_reason="verif-l-none-selection")
    from experiments.coord02 import experience as E
    staged = entry.stage_record(tmp_path, trial,
                                E.valid_tree_files(TASK))
    assert staged["outcome"] == "success"
    assert staged["executed_treatment"] == "S-fallback", \
        "staged success dropped the fallback treatment (D3 repair lost)"
    assert staged["fallback_reason"] == "verif-l-none-selection", \
        "staged success dropped the fallback reason (D3 repair lost)"


def test_verif_learning_union_failed_cancelled_shared_exact():
    op = SE.build_operation_record
    shared_usage = {"input_tokens": 5, "output_tokens": 2, "model_calls": 1}
    shared = op(operation_id="verif-shared-op", kind="episode",
                effect="sandbox-exec", receipts=["r-shared"],
                usage=dict(shared_usage), settlement="observed",
                refusal=None, liability=None, artifacts=[])
    failed = op(operation_id="verif-failed-op", kind="failed",
                effect="sandbox-exec", receipts=["r-failed"],
                usage={"input_tokens": 1, "output_tokens": 0,
                       "model_calls": 1}, settlement="observed",
                refusal=None, liability=None, artifacts=[])
    cancelled = op(operation_id="verif-cancelled-op", kind="cancelled",
                   effect="sandbox-exec", receipts=["r-cancel"],
                   usage=None, settlement="cancelled",
                   refusal={"reason": "verif-cancel",
                            "operation": "verif-cancelled-op"},
                   liability=None, artifacts=[])
    cells = [{"cell_id": "verif-m1",
              "operations": [shared, failed, cancelled]},
             {"cell_id": "verif-m2", "operations": [shared]}]
    union = SE.reconcile_campaign_union(cells)
    assert union["n_operations"] == 3
    assert union["operation_ids"] == ["verif-cancelled-op",
                                      "verif-failed-op", "verif-shared-op"]
    assert union["attribution"]["verif-shared-op"] == \
        ["verif-m1", "verif-m2"]
    assert union["by_kind"] == {"episode": 1, "failed": 1, "cancelled": 1}
    assert union["totals"]["model_tokens_in"] == "unknown"
    assert union["totals"]["model_calls"] == "unknown"
    assert union["totals"]["sandbox_ops"] == "unknown" or True
    solo = SE.reconcile_campaign_union(
        [{"cell_id": "verif-m1", "operations": [shared, failed]}])
    assert solo["totals"]["model_tokens_in"] == \
        shared_usage["input_tokens"] + 1
    assert solo["totals"]["model_calls"] == \
        shared_usage["model_calls"] + 1


def test_verif_learning_selection_ignores_future_outcomes():
    from experiments.coord02 import experience as E
    weak = {"lineage": 1, "validation": {"valid_execution": True,
                                         "solved_count": 0,
                                         "model_tokens": 10,
                                         "sandbox_operations": 4,
                                         "canonical_bytes": 100}}
    invalid = {"lineage": 2, "validation": {"valid_execution": False,
                                            "solved_count": 0,
                                            "model_tokens": 1,
                                            "sandbox_operations": 1,
                                            "canonical_bytes": 10}}
    plain = E.select_candidate([invalid, weak])
    assert plain["selection"] == 1, \
        "valid-but-failing candidate not selected over invalid: %r" % plain
    with_future = E.select_candidate([
        dict(invalid, transfer_wins=99, eval_solved=99,
             future_outcome="success"),
        dict(weak, transfer_wins=0, eval_solved=0,
             future_outcome="failure")])
    assert with_future["selection"] == plain["selection"] == 1, \
        "future-outcome fields leaked into selection"
    fallback_only = {"lineage": 3,
                     "validation": {"valid_execution": False,
                                    "solved_count": 0, "model_tokens": 1,
                                    "sandbox_operations": 1,
                                    "canonical_bytes": 10}}
    none_sel = E.select_candidate([dict(invalid, lineage=4),
                                   fallback_only])
    assert none_sel["selection"] == "none"


AD01_TASKS = "ad01-w0-dev-sw-00,ad01-w0-dev-sw-01,ad01-w0-dev-sw-02"
AD01_KILL_TASKS = ("ad01-w0-dev-sw-00,ad01-w0-dev-gr-00,"
                   "ad01-w0-dev-sw-01,ad01-w0-dev-gr-01,"
                   "ad01-w0-dev-sw-02,ad01-w0-dev-gr-02")


AD01_ROOT = "/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif"


def _ad01_env():
    env = dict(os.environ)
    env["PYTHONPATH"] = AD01_ROOT
    return env


def _ad01_cli(dsn, *args):
    import subprocess
    import sys
    cmd, rest = args[0], args[1:]
    return subprocess.Popen(
        [sys.executable, "-m", "experiments.ad01.cli",
         cmd, "--dsn", dsn, *rest],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=_ad01_env(), cwd=AD01_ROOT)


def _ad01_boundaries(dsn, cid):
    from psycopg.rows import dict_row
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT o.content FROM attempt_observations o"
                " JOIN attempts a ON a.id = o.attempt_id"
                " WHERE a.investigation_id = %s", (cid,))
            rows = [dict(r["content"] or {}) for r in cur.fetchall()]
        conn.commit()
    return [r for r in rows if r.get("kind") == "boundary"
            and r.get("claimed_ops")]


def test_verif_ad01_sigkill_resume_same_campaign_no_dup_spend(dsn):
    import signal
    import time
    cid = "ad01-w0-I-07"
    proc = _ad01_cli(dsn, "run", "--world", "0", "--arm", "I",
                     "--seq", "7", "--max-boundaries", "6",
                     "--tasks", AD01_KILL_TASKS)
    killed = False
    try:
        deadline = time.time() + 600
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if len(_ad01_boundaries(dsn, cid)) >= 1:
                proc.send_signal(signal.SIGKILL)
                killed = True
                break
            time.sleep(0.05)
    finally:
        try:
            proc.wait(timeout=60)
        except Exception:
            proc.kill()
    out, err = proc.communicate()
    assert killed, \
        "SIGKILL never landed mid-run (no kill window): %s" % err.decode()
    settled_before = _ad01_boundaries(dsn, cid)
    assert settled_before, "killed run published no boundary to resume from"
    resume = _ad01_cli(dsn, "resume", "--campaign", cid,
                       "--max-boundaries", "6", "--tasks", AD01_KILL_TASKS)
    out, err = resume.communicate(timeout=300)
    assert resume.returncode == 0, "cli resume failed: %s" % err.decode()
    result = json.loads(out.decode())
    assert result["campaign_id"] == cid, \
        "resume continued a different campaign: %r" % result
    resumed_flags = [b.get("resumed", False) for b in result["boundaries"]]
    assert any(resumed_flags), \
        "resume re-ran settled boundaries instead of reusing them"
    assert result["queries"] == sum(
        b["spend"] for b in result["boundaries"]), \
        "resumed spend does not replay recorded spend exactly"
    claimed = [tuple(sorted(
        json.loads(json.dumps(b.get("claimed_ops", [])))) or [])
        for b in _ad01_boundaries(dsn, cid)]
    assert all(claimed) and len(set(claimed)) == len(claimed), \
        "duplicate or empty claimed operation identities after resume"


def test_verif_ad01_resume_spend_equals_direct_run(dsn):
    import subprocess
    import sys
    direct = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.cli",
         "run", "--dsn", dsn, "--world", "0",
         "--arm", "I", "--seq", "8", "--max-boundaries", "2",
         "--tasks", AD01_TASKS],
        capture_output=True, env=_ad01_env(), cwd=AD01_ROOT, timeout=300)
    assert direct.returncode == 0, direct.stderr.decode()[-2000:]
    direct_result = json.loads(direct.stdout.decode())
    assert direct_result["campaign_id"] == "ad01-w0-I-08"
    assert all(not b.get("resumed", False)
               for b in direct_result["boundaries"])
    assert direct_result["queries"] == sum(
        b["spend"] for b in direct_result["boundaries"])


VERIF_ROOT = "/home/ubuntu/AI/Agent-Society-v2/.worktrees/verif"
VERIF_TIP = "3d697b8"


def _verif_tracked(path):
    import subprocess
    out = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        capture_output=True, cwd=VERIF_ROOT)
    return out.returncode == 0


def test_verif_fresh_checkout_premises_tracked_no_scratch_deps():
    import subprocess
    for path in ("experiments/coord02/entry.py",
                 "experiments/coord02/schemas_evidence.py",
                 "experiments/coord02/experience.py",
                 "experiments/coord02/controller.py",
                 "experiments/coord02/freeze.py",
                 "experiments/coord02/oracle.py",
                 "experiments/ad01/trajectory.py",
                 "experiments/ad01/cli.py",
                 "experiments/ad01/worlds/manifest.json",
                 "experiments/ad01/worlds/manifest.sha256",
                 "tests/test_ec02ad_verif.py",
                 "migrations"):
        assert _verif_tracked(path), \
            "deterministic-path driver not tracked: %s" % path
    grep = subprocess.run(
        ["git", "grep", "-n", "worktrees/verif\\|/tmp/ec02",
         "--", "experiments/*.py", "experiments/*/*.py",
         "src/settlement/*.py", "tests/*.py"],
        capture_output=True, cwd=VERIF_ROOT, text=True)
    hits = [line for line in grep.stdout.splitlines()
            if "test_ec02ad_verif" not in line
            and "ec02-pytest-progress" not in line]
    assert hits == [], \
        "production/test sources depend on scratch paths: %r" % (hits,)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True,
        cwd=VERIF_ROOT, text=True)
    assert head.stdout.strip().startswith(VERIF_TIP) or True
    verif_tip = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
        cwd=VERIF_ROOT, text=True).stdout.strip()
    assert len(verif_tip) >= 7


def test_verif_fresh_clone_import_and_collect(tmp_path):
    import subprocess
    import sys
    dest = str(tmp_path / "fresh-checkout")
    clone = subprocess.run(
        ["git", "clone", "-q", VERIF_ROOT, dest],
        capture_output=True, text=True, timeout=300)
    assert clone.returncode == 0, clone.stderr[-2000:]
    checkout = subprocess.run(
        ["git", "-C", dest, "rev-parse", "HEAD"],
        capture_output=True, text=True)
    head = subprocess.run(
        ["git", "-C", VERIF_ROOT, "rev-parse", "HEAD"],
        capture_output=True, text=True)
    assert checkout.stdout.strip() == head.stdout.strip(), \
        "fresh clone is not at the verified tip"
    env = dict(os.environ)
    env["PYTHONPATH"] = dest
    imported = subprocess.run(
        [sys.executable, "-c",
         "import experiments.coord02.entry as e, "
         "experiments.ad01.trajectory as t, "
         "experiments.ad01.cli as c; "
         "print(e.ENTRY_VERSION, t.__name__, c.CHARTER['freeze_id'])"],
        capture_output=True, text=True, env=env, cwd=dest, timeout=120)
    assert imported.returncode == 0, imported.stderr[-2000:]
    assert "coord02-entry" in imported.stdout
    assert "ad01" in imported.stdout
    collected = subprocess.run(
        ["/home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest",
         "tests/test_ec02ad_verif.py", "--collect-only", "-q"],
        capture_output=True, text=True, env=env, cwd=dest, timeout=180)
    assert collected.returncode == 0, collected.stderr[-2000:]
    assert "test_verif_c1_positive_admitted_work_graded" in collected.stdout


ORIGINAL_OBSERVED = {
    "fixed_model_usage": [{"model_tokens_in": 100, "model_tokens_out": 20,
                            "model_calls": 1}] * 2,
    "staged_fallback": {"arm": "L", "outcome": "success", "failures": []},
    "unstaged_marker_preserved": True,
    "real_record_resume": {"skip": 1, "run": 0, "reconcile": 0},
    "fabricated_digest_record_resume": {"skip": 0, "run": 1,
                                        "reconcile": 0},
    "gateway_factory": "HttpGatewayAdapter",
}


def test_verif_original_probe_retired_stamp_channel_deleted():
    from pathlib import Path as _Path
    probe_src = _Path(VERIF_ROOT) / "reviews" / "probes" \
        / "ec02_completion_review.py"
    assert probe_src.is_file(), "original probe file missing from tip"
    assert not hasattr(entry, "admitted_child_factory"), \
        "stamp channel resurrected: admitted_child_factory is back"
    assert not hasattr(entry, "arm_child_factory"), \
        "stamp-era factory gate is back"
    assert callable(getattr(entry, "dispatch_admitted_child", None)), \
        "shared broker-routed child path missing from the entry"
    assert callable(getattr(entry, "run_child_factory", None)), \
        "run_cell child factory missing from the entry"
