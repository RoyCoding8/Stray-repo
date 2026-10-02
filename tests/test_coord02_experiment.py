"""coord02 experiment-contract tests (lane E, EC02 early work).

Contract-level only: shared trial/record schema, cost-union math,
promising-rule unit vectors, freeze-assembly helper, preflight gate.
Durable tests run on real PostgreSQL (ec02test_e). No live model
calls anywhere: no grant exists (no TEAM01_LIVE_API_KEY), and the
preflight tests prove the entry refuses live panels without one.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from experiments.coord02 import checker
from experiments.coord02 import freeze as freeze_mod
from experiments.coord02 import oracle
from experiments.coord02 import preflight as P
from experiments.coord02 import schemas_evidence as E

DSN = os.environ.get("EC02_E_DSN",
                     "dbname=ec02test_e host=/var/run/postgresql user=ubuntu")
MIGRATIONS = Path(__file__).parent.parent / "migrations"


@pytest.fixture()
def dsn():
    from settlement import db as _db
    _db.apply_migrations(DSN, MIGRATIONS)
    with _db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname ="
                        " 'public' AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{row[0]}" CASCADE')
        conn.commit()
    return DSN

DEV_TASK = oracle.SPLITS["development"][0]

BASE_COSTS = {"model_tokens_in": 100, "model_tokens_out": 20,
              "model_calls": 1, "tool_invocations": 2, "sandbox_ops": 9,
              "policy_exec_ops": 4, "protected_check_ops": 2,
              "cpu_seconds": 1.0, "wall_seconds": 2.0,
              "elapsed_seconds": 2.0, "abandoned_ops": 0}

BASE_PROTECTED = {"passed": 3, "failed": 0, "total": 3}


def _record(**over) -> dict:
    fields = {"freeze_id": "coord02-e-test", "panel": "evaluation",
              "task_id": DEV_TASK, "repeat": 1, "arm": "L",
              "source_sha": "base-sha", "config_digest": "cfg-digest",
              "package_digest": "pkg-digest", "outcome": "success",
              "solved": True, "protected": dict(BASE_PROTECTED),
              "failures": [], "costs": dict(BASE_COSTS),
              "receipts": ["op-1", "op-2"]}
    fields.update(over)
    return E.build_trial_record(**fields)


def _vec(solved: int, tokens: int = 100, tools: int = 10,
         ops: int = 50) -> dict:
    return {"solved": solved, "model_tokens": tokens,
            "tool_invocations": tools, "sandbox_ops": ops}


def test_trial_record_round_trip():
    record = _record()
    raw = E.trial_record_bytes(record)
    assert E.trial_record_bytes(record) == raw
    back = E.validate_trial_record(json.loads(raw.decode("utf-8")))
    assert back == record
    assert back["external_billing"] == {"model": "unknown",
                                        "infra": "unknown"}


def test_trial_record_rejects_bad_identity():
    for field, value in (("panel", "heldout"), ("arm", "X"),
                         ("repeat", 3), ("outcome", "maybe")):
        with pytest.raises(E.TrialError):
            _record(**{field: value})


def test_trial_record_refusal_timeout_keep_costs_zero_success():
    record = _record(outcome="refusal", solved=False,
                     protected={"passed": 0, "failed": 1, "total": 1},
                     failures=["declined incompatible binding"])
    assert record["costs"]["model_calls"] == 1
    with pytest.raises(E.TrialError):
        _record(outcome="refusal", solved=True)
    with pytest.raises(E.TrialError):
        _record(outcome="timeout", solved=True)
    with pytest.raises(E.TrialError):
        _record(outcome="success", solved=False)


def test_trial_record_protected_arithmetic():
    with pytest.raises(E.TrialError):
        _record(protected={"passed": 2, "failed": 2, "total": 3})
    with pytest.raises(E.TrialError):
        _record(protected={"passed": 2, "failed": 1, "total": 3})
    with pytest.raises(E.TrialError):
        _record(outcome="failure", solved=False,
                 protected={"passed": 2, "failed": 1, "total": 3},
                 failures=[])


def test_trial_record_cost_rules():
    costs = dict(BASE_COSTS, model_calls=-1)
    with pytest.raises(E.TrialError):
        _record(costs=costs)
    costs = dict(BASE_COSTS, policy_exec_ops=8, protected_check_ops=2)
    with pytest.raises(E.TrialError):
        _record(costs=costs)
    with pytest.raises(E.TrialError):
        _record(receipts=[])
    record = _record(costs={**BASE_COSTS, "cpu_seconds": None})
    assert record["costs"]["cpu_seconds"] is None


def test_trial_record_billing_unknown_not_zero():
    assert _record()["external_billing"]["model"] == "unknown"
    record = _record(external_billing={"model": 12.5, "infra": 0.0})
    assert record["external_billing"] == {"model": 12.5, "infra": 0.0}
    with pytest.raises(E.TrialError):
        _record(external_billing={"model": -1.0})


def test_checker_bridge(tmp_path):
    freeze = freeze_mod.build_freeze("coord02-e-bridge",
                                     source_sha="bridge-base")
    w_record = checker.make_record(freeze, tmp_path, panel="development",
                                   task=DEV_TASK, repeat=1, arm="L",
                                   kind="valid")
    record = E.from_checker_record(w_record, source_sha="bridge-base",
                                   config_digest="cfg")
    assert record["freeze_id"] == "coord02-e-bridge"
    assert record["package_digest"] == w_record["procedure_digest"]
    assert record["task_id"] == DEV_TASK
    costs = E.to_checker_costs(record)
    assert costs["model_tokens"] == {"in": 100, "out": 20}
    assert costs["model_calls"] == 1


def test_freeze_assembly_declares_baselines_first(tmp_path):
    package_bytes = b"package entry bytes v1"
    digest = __import__("hashlib").sha256(package_bytes).hexdigest()
    freeze = E.assemble_freeze_contents(
        "coord02-e-freeze", source_sha="base-sha",
        package_bytes=package_bytes,
        input_contract={"task": DEV_TASK, "contract": "public-io/1"},
        exposure_manifest={"package_digest": digest,
                           "exposure": "dev-only"},
        selector={"rule": "frozen-schedule",
                  "declared": "before-acquisition"},
        baselines={"S": "single", "A": "memory", "F": "conditional",
                   "declared_before_inspection": True})
    assert freeze["package"] == {"kind": "learned", "digest": digest}
    assert freeze["baselines"]["package_digest"] == digest
    path = freeze_mod.write_freeze(tmp_path / "freeze.json", freeze)
    assert freeze_mod.verify_freeze(path) == []
    with pytest.raises(E.TrialError):
        E.assemble_freeze_contents(
            "coord02-e-bad", source_sha="base-sha",
            package_bytes=package_bytes,
            input_contract={"task": DEV_TASK},
            exposure_manifest={"package_digest": "wrong"},
            selector={"rule": "x"},
            baselines={"declared_before_inspection": True})
    with pytest.raises(E.TrialError):
        E.assemble_freeze_contents(
            "coord02-e-bad", source_sha="base-sha",
            package_bytes=package_bytes,
            input_contract={"task": DEV_TASK},
            exposure_manifest={"package_digest": digest},
            selector={"rule": "x"},
            baselines={"S": "single"})


def test_cost_union_dedups_shared_operations():
    ops = [{"operation_id": "op-shared", "kind": "episode",
            "costs": {"model_calls": 1}},
           {"operation_id": "op-shared", "kind": "episode",
            "costs": {"model_calls": 1}},
           {"operation_id": "op-fail", "kind": "failed",
            "costs": {"model_calls": 2}}]
    union = E.reconcile_cost_union(ops)
    assert union["n_operations"] == 2
    assert union["totals"]["model_calls"] == 3
    assert union["operation_ids"] == ["op-fail", "op-shared"]
    with pytest.raises(E.TrialError):
        E.reconcile_cost_union(
            [{"operation_id": "op-x", "kind": "episode",
              "costs": {"model_calls": 1}},
             {"operation_id": "op-x", "kind": "episode",
              "costs": {"model_calls": 9}}])


def test_cost_union_unknown_not_zero():
    union = E.reconcile_cost_union(
        [{"operation_id": "op-a", "kind": "episode",
          "costs": {"model_calls": 1, "cpu_seconds": None}}])
    assert union["totals"]["cpu_seconds"] == "unknown"
    assert union["totals"]["model_calls"] == 1
    assert union["totals"]["tool_invocations"] == 0
    union = E.reconcile_cost_union(
        [{"operation_id": "op-a", "kind": "episode",
          "costs": {"model_calls": 1, "wall_seconds": 2.0}},
         {"operation_id": "op-b", "kind": "validation",
          "costs": {"model_calls": 1}}])
    assert union["totals"]["wall_seconds"] == "unknown"


def test_cost_union_includes_failed_cancelled_builds():
    union = E.reconcile_cost_union(
        [{"operation_id": "op-%d" % i, "kind": kind, "costs": costs}
         for i, (kind, costs) in enumerate(
             [("build", {"sandbox_ops": 5}),
              ("validation", {"sandbox_ops": 3}),
              ("episode", {"sandbox_ops": 9}),
              ("failed", {"sandbox_ops": 4}),
              ("cancelled", {"sandbox_ops": 1})])])
    assert union["totals"]["sandbox_ops"] == 22
    assert union["by_kind"] == {"build": 1, "validation": 1, "episode": 1,
                                "failed": 1, "cancelled": 1}


def test_promising_win_within_ratio_passes():
    verdict = E.promising_versus(_vec(9), _vec(7))
    assert verdict["verdict"] == "pass"


def test_promising_win_over_ratio_fails():
    verdict = E.promising_versus(_vec(9, tokens=130), _vec(7, tokens=100))
    assert verdict["verdict"] == "fail"
    assert any("1.25x" in reason for reason in verdict["reasons"])


def test_promising_tie_vectors():
    assert E.promising_versus(
        _vec(7, tokens=80), _vec(7, tokens=100))["verdict"] == "pass"
    assert E.promising_versus(
        _vec(7, tokens=100), _vec(7, tokens=100))["verdict"] == "fail"
    assert E.promising_versus(
        _vec(7, tokens=80, tools=11), _vec(7, tokens=100),
        )["verdict"] == "fail"


def test_promising_loss_and_refusal_vectors_fail():
    assert E.promising_versus(_vec(6), _vec(7))["verdict"] == "fail"
    refused = _vec(0, tokens=5, tools=1, ops=8)
    verdict = E.promising_versus(refused, _vec(3))
    assert verdict["verdict"] == "fail"
    assert "fewer (0 vs 3)" in verdict["reasons"][0]


def test_promising_zero_denominator():
    assert E.promising_versus(
        _vec(1, tokens=0, tools=0, ops=0),
        _vec(0, tokens=0, tools=0, ops=0))["verdict"] == "pass"
    assert E.promising_versus(
        _vec(1, tokens=4, tools=0, ops=0),
        _vec(0, tokens=0, tools=0, ops=0))["verdict"] == "fail"


def test_promising_unknown_unevaluable():
    learned = _vec(9)
    learned["model_tokens"] = None
    verdict = E.promising_versus(learned, _vec(7))
    assert verdict["verdict"] == "unevaluable"


def test_promising_family_caps():
    assert E.promising_versus(
        _vec(9), _vec(7),
        family_losses={"sep": 2}, family_cap=1)["verdict"] == "fail"
    assert E.promising_versus(
        _vec(9), _vec(7),
        family_losses={"sep": 1}, family_cap=0)["verdict"] == "fail"
    assert E.promising_versus(
        _vec(9), _vec(7),
        family_losses={"sep": 1}, family_cap=1)["verdict"] == "pass"


def test_promising_joint_rule():
    def cell(l_solved: int, c_solved: int, l_tokens: int = 80,
             c_tokens: int = 100):
        return [_vec(l_solved, tokens=l_tokens), _vec(c_solved,
                                                      tokens=c_tokens)]
    matchups = {arm: {"evaluation": cell(9, 7), "transfer": cell(5, 4)}
                for arm in ("S", "A", "F")}
    report = E.promising_rule(matchups)
    assert report["promising"] is True
    assert set(report["raw"]) == {"S", "A", "F"}
    matchups["F"]["transfer"] = cell(3, 4)
    report = E.promising_rule(matchups)
    assert report["promising"] is False
    assert report["by_comparator"]["F"]["pass"] is False
    assert report["by_comparator"]["S"]["pass"] is True
    with pytest.raises(E.TrialError):
        E.promising_rule({"S": matchups["S"]})


def test_preflight_refuses_without_grant():
    verdict = P.preflight_live(env={})
    assert verdict["admitted"] is False
    assert any("TEAM01_LIVE_API_KEY" in p for p in verdict["problems"])
    assert any("EC02_LIVE_GRANT_EPISODES" in p
               for p in verdict["problems"])
    assert "experiments.coord02.entry" in verdict["blocked_command"]
    assert verdict["remaining_cells"] == {"evaluation": 96,
                                          "transfer": 48}
    with pytest.raises(PermissionError):
        P.require_live(env={})


def test_preflight_grant_too_small_refuses():
    env = {"SETTLEMENT_GATEWAY_ENDPOINT": "http://localhost:6446/v1",
           "TEAM01_LIVE_API_KEY": "grant", "TEAM01_LIVE_MODEL": "m",
           "EC02_LIVE_GRANT_EPISODES": "10"}
    verdict = P.preflight_live(env=env)
    assert verdict["admitted"] is False
    assert any("covers 10 episodes" in p for p in verdict["problems"])


def test_preflight_admits_with_full_grant():
    env = {"SETTLEMENT_GATEWAY_ENDPOINT": "http://localhost:6446/v1",
           "TEAM01_LIVE_API_KEY": "grant", "TEAM01_LIVE_MODEL": "m",
           "EC02_LIVE_GRANT_EPISODES": "144", "EC02_LIVE_GRANT_CALLS": "4"}
    verdict = P.require_live(env=env)
    assert verdict["admitted"] is True
    assert verdict["grant"] == {"episodes": 144,
                                "construction_calls": 4}


def test_preflight_refuses_construction_grant_below_demand():
    env = {"SETTLEMENT_GATEWAY_ENDPOINT": "http://localhost:6446/v1",
           "TEAM01_LIVE_API_KEY": "grant", "TEAM01_LIVE_MODEL": "m",
           "EC02_LIVE_GRANT_EPISODES": "144", "EC02_LIVE_GRANT_CALLS": "2"}
    verdict = P.preflight_live(env=env,
                               construction_calls=P.CONSTRUCTION_CALLS)
    assert verdict["admitted"] is False
    assert any("construction grant covers 2 calls" in p
               for p in verdict["problems"])
    with pytest.raises(PermissionError):
        P.require_live(env=env, construction_calls=P.CONSTRUCTION_CALLS)


def test_construction_budget_binds_the_authorized_ceiling():
    from experiments.coord02 import experience as X
    assert X.construction_budget(
        live_calls_authorized=2)["live_calls_authorized"] == 2
    with pytest.raises(ValueError):
        X.construction_budget(live_calls_authorized=0)
    with pytest.raises(ValueError):
        X.construction_budget(live_calls_authorized=5)


def _table(suffix: str) -> str:
    return "coord02_e_%s_%s" % (suffix, uuid.uuid4().hex[:8])


def test_reconciliation_from_db_union():
    from settlement import db

    table = _table("ops")
    rows = [("trial-1", "op-shared", "episode", {"model_calls": 1}),
            ("trial-2", "op-shared", "episode", {"model_calls": 1}),
            ("trial-1", "op-fail", "failed", {"model_calls": 2}),
            ("trial-2", "op-cancel", "cancelled",
             {"tool_invocations": 3}),
            ("trial-1", "op-build", "build", {"sandbox_ops": 5})]
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE %s (trial_ref TEXT NOT NULL, "
                        "operation_id TEXT NOT NULL, kind TEXT NOT NULL, "
                        "costs JSONB NOT NULL)" % table)
            for trial, op_id, kind, costs in rows:
                cur.execute("INSERT INTO %s VALUES (%%s, %%s, %%s, %%s)"
                            % table, (trial, op_id, kind,
                                      json.dumps(costs)))
        conn.commit()
    try:
        with db.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT operation_id, kind, costs FROM %s"
                            % table)
                stored = [{"operation_id": op_id, "kind": kind,
                           "costs": costs}
                          for op_id, kind, costs in cur.fetchall()]
            conn.commit()
        union = E.reconcile_cost_union(stored)
        assert union["n_operations"] == 4
        assert union["totals"]["model_calls"] == 3
        assert union["totals"]["tool_invocations"] == 3
        assert union["totals"]["sandbox_ops"] == 5
        assert union["by_kind"]["failed"] == 1
        assert union["by_kind"]["cancelled"] == 1
        naive = sum(costs.get("model_calls", 0)
                    for _, _, _, costs in rows)
        assert naive == 4
        assert union["totals"]["model_calls"] == 3 != naive
    finally:
        with db.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS %s" % table)
            conn.commit()


def test_freeze_anchor_pg_roundtrip():
    from settlement import db

    table = _table("freeze")
    freeze = freeze_mod.build_freeze("coord02-e-anchor",
                                     source_sha="anchor-base")
    manifest_digest = freeze["corpus"]["manifest_digest"]
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE %s (freeze_id TEXT PRIMARY KEY, "
                        "manifest_digest TEXT NOT NULL)" % table)
            cur.execute("INSERT INTO %s VALUES (%%s, %%s)"
                        % table, ("coord02-e-anchor", manifest_digest))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT manifest_digest FROM %s WHERE freeze_id "
                        "= %%s" % table, ("coord02-e-anchor",))
            row = cur.fetchone()
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("DROP TABLE %s" % table)
        conn.commit()
    assert row[0] == manifest_digest


def test_checker_receipt_crosscheck_db(tmp_path):
    from settlement import db

    freeze = freeze_mod.build_freeze("coord02-e-db", source_sha="db-base")
    root = tmp_path / "db-evidence"
    records = [checker.make_record(freeze, root, panel="development",
                                   task=DEV_TASK, repeat=repeat, arm="S",
                                   kind="valid")
               for repeat in freeze_mod.REPEATS]
    anchored = [r for record in records for r in record["receipts"]]
    table = _table("receipts")
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE %s (receipt_identity TEXT PRIMARY "
                        "KEY)" % table)
            for ref in anchored:
                cur.execute("INSERT INTO %s VALUES (%%s)" % table, (ref,))
        conn.commit()
    try:
        freeze_path = freeze_mod.write_freeze(tmp_path / "db-freeze.json",
                                              freeze)
        report = checker.check_evidence(root, freeze_path, dsn=DSN,
                                        receipt_table=table,
                                        panels=("development",))
        assert report["records"] == 2
        assert not [p for p in report["problems"]
                    if p.startswith("altered-receipt")
                    or "db-evidence" in p and "missing" in p], \
            report["problems"]
        with db.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM %s WHERE receipt_identity = %%s"
                            % table, (anchored[0],))
            conn.commit()
        report = checker.check_evidence(root, freeze_path, dsn=DSN,
                                        receipt_table=table,
                                        panels=("development",))
        assert any(p.startswith("altered-receipt")
                   for p in report["problems"])
    finally:
        with db.connect(DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS %s" % table)
            conn.commit()


def test_no_live_grant_in_environment():
    assert not os.environ.get("TEAM01_LIVE_API_KEY")
    assert P.preflight_live()["admitted"] is False


def _launchers(tmp_path):
    from settlement.launcher_local import LocalLauncher
    base = tmp_path / "asm"
    base.mkdir(exist_ok=True)

    def _factory(tag):
        return {"local-process": LocalLauncher(base / tag)}
    return _factory


def _freeze_for(panel):
    freeze = freeze_mod.build_freeze("coord02-e-entry-test",
                                     source_sha="entry-test")
    freeze["schedule"] = [c for c in freeze["schedule"]
                          if c["panel"] == panel]
    return freeze


def test_entry_arms_differ_only_as_declared(tmp_path):
    from experiments.coord02 import entry as EN
    seen = {}
    for arm in ("S", "A", "F", "L"):
        seen[arm] = EN.arm_policy_entry(arm, task_id=DEV_TASK,
                                        package_entry=b"pkg",
                                        package_digest="d")
    assert len(set(seen.values())) == 4
    assert seen["L"] == b"pkg"
    with pytest.raises(ValueError):
        EN.arm_policy_entry("L")
    with pytest.raises(ValueError, match="unknown arm"):
        EN.run_cell("unused-dsn", freeze={"freeze_id": "x"},
                    task_id=DEV_TASK, panel="development", repeat=1,
                    arm="Z", launcher_factory=lambda tag: {})


def test_entry_refuses_live_without_grant(tmp_path):
    from experiments.coord02 import entry as EN
    assert EN.main(["--panel", "evaluation"]) == 2
    assert EN.main(["--panel", "transfer"]) == 2


def test_entry_doubled_dev_cell(dsn, tmp_path):
    from experiments.coord02 import entry as EN
    freeze = _freeze_for("development")
    task_id = oracle.SPLITS["development"][0]
    cell = EN.run_cell(DSN, freeze=freeze, task_id=task_id,
                       panel="development", repeat=1, arm="S",
                       launcher_factory=_launchers(tmp_path))
    clean = E.validate_trial_record(cell.record)
    assert clean["freeze_id"] == "coord02-e-entry-test"
    assert cell.record["receipts"]
    assert EN.check_ceilings(clean["costs"]) == []


def test_entry_write_evidence_round_trip(dsn, tmp_path):
    from experiments.coord02 import entry as EN
    freeze = freeze_mod.build_freeze("coord02-e-entry-test",
                                     source_sha="entry-test")
    factory = _launchers(tmp_path)
    cells = EN.run_panel(DSN, freeze=freeze, panel="development",
                         launcher_factory=factory,
                         package_text="doubled-dev")
    summary = EN.write_evidence(cells, freeze=freeze,
                                evidence_root=tmp_path / "ev", dsn=DSN)
    assert summary["records"] == 12 * 2 * 4
    problems = summary["checker"]["problems"]
    unknown_costs = sorted(
        "omitted-cost-%s %s-%s-%s-r%d-%s" % (
            field, freeze["freeze_id"], c.record["panel"],
            c.record["task_id"], c.record["repeat"], c.record["arm"])
        for c in cells
        for field in ("model_calls", "model_tokens-in",
                      "model_tokens-out"))
    assert sorted(problems) == unknown_costs
    view = EN.status_view(DSN, freeze=freeze,
                          evidence_root=tmp_path / "ev",
                          panels=("development",))
    assert view["evidence"]["problems"] == problems


def test_entry_pair_identity_unique(dsn, tmp_path):
    from experiments.coord02 import entry as EN
    freeze = _freeze_for("development")
    factory = _launchers(tmp_path)
    cells = EN.run_panel(DSN, freeze=freeze, panel="development",
                         launcher_factory=factory, arms=("S",),
                         repeats=(1,))
    keys = [(c.record["freeze_id"], c.record["panel"],
             c.record["task_id"], c.record["repeat"], c.record["arm"])
            for c in cells]
    assert len(set(keys)) == len(keys) == len(cells)
    assert len(cells) == len(oracle.SPLITS["development"])
