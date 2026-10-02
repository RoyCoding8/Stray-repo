"""Review-03 evaluation-lane regressions: staged execution, digest-bound
evaluation, honest A/B/C comparison, version-bound release selection."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "experiments")

import pytest

from settlement import broker, capabilities, db, evaluation, experiment, trials
from settlement.common import Command, ResultCode, SettlementError, payload_digest
from settlement.launcher_local import LocalLauncher

from doubles import ScriptedDouble
from fault_tasks import BY_ID
from test_s3_helpers import EXPERIMENTS, seed_env, stage_method, publish_method

GRADER = str(EXPERIMENTS / "run_tests.py")
CASES = [{"fn": "add", "args": [1, 2], "expected": 3}]
PASS_CODE = "def add(a, b):\n    return a + b\n"
GROUPS = [{"name": "development", "kind": "development"},
          {"name": "panel", "kind": "protected-eval"}]


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _grader_pin():
    return hashlib.sha256(Path(GRADER).read_bytes()).hexdigest()


def _freeze(dsn, tag, candidate="t-cand", evaluator="v1"):
    trials.freeze_protocol(
        dsn, Command(request_id=f"{tag}-frz"), protocol_id=f"{tag}-p",
        candidate_version=candidate, reference_version="t-ref",
        evaluator_version=evaluator, task_groups=GROUPS,
        budgets={}, metrics=["success_rate"], stopping={}, exclusions=[],
        uncertainty={})
    return f"{tag}-p"


def _assigned(dsn, tag, pid, task_id="t1", arm="candidate"):
    aid = f"{pid}:{arm}:{task_id}"
    trials.assign(dsn, Command(request_id=f"{tag}-a-{arm}", payload={}),
                  pid, task_id, "panel", arm, {"entry_fn": "add"})
    return aid


def test_staged_grading_binds_and_admits_real_tallies(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r03g")
    evaluation.register_evaluator(dsn, Command(request_id="r03g-eval"),
                                  "s3-eval", "v1", code_digest=_grader_pin())
    pid = _freeze(dsn, "r03g")
    aid = _assigned(dsn, "r03g", pid)
    op_id, staged = experiment._prepare_grade(
        dsn, launcher, PASS_CODE, CASES, "r03g", env["allocation_id"], None,
        GRADER)
    row = broker.read_operation(dsn, op_id)
    argv = row["payload"]["payload"]["argv"]
    assert argv[0] == launcher.staged_python() == sys.executable
    in_dir, _ = launcher.exec_dirs(op_id, "")
    assert argv[1:4] == [f"{in_dir}/grader.py", f"{in_dir}/candidate.py",
                         f"{in_dir}/cases.json"]
    assert all(Path(p).is_relative_to(launcher.run_dir) for p in
               [path for path, _ in staged.values()])
    content = {"code": PASS_CODE}
    evaluation.submit_candidate(dsn, Command(request_id="r03g-sub"), aid,
                                content)
    out = evaluation.bind_evaluation(
        dsn, Command(request_id="r03g-bind"), aid,
        candidate_digest=payload_digest(content), evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref=op_id,
        executable_digest=staged["grader.py"][1], input_digest=staged["cases.json"][1])
    assert out.code == ResultCode.APPLIED
    assert experiment._dispatch_grade(dsn, launcher, op_id, len(CASES),
                                      staged) == "success"
    admitted = evaluation.submit_evaluator_receipt(
        dsn, Command(request_id="r03g-rc"), receipt_id="r03g-r",
        assignment_id=aid, evaluator_id="s3-eval", evaluator_version="v1",
        invocation_ref=op_id,
        result={"outcome": "success", "detail": {"task_id": "t1"}})
    assert admitted.code == ResultCode.APPLIED


def test_tampered_staged_input_refused_at_launch(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r03t")
    op_id, staged = experiment._prepare_grade(
        dsn, launcher, PASS_CODE, CASES, "r03t", env["allocation_id"], None,
        GRADER)
    host_path, _ = staged["cases.json"]
    Path(host_path).write_bytes(b'[{"fn": "add", "args": [1, 2], "expected": 999}]')
    with pytest.raises(SettlementError, match="changed after binding"):
        experiment._dispatch_grade(dsn, launcher, op_id, len(CASES), staged)


def test_unrelated_op_refused_for_pinned_evaluator(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r03u")
    evaluation.register_evaluator(dsn, Command(request_id="r03u-eval"),
                                  "s3-eval", "v1", code_digest="pinned-grader")
    pid = _freeze(dsn, "r03u")
    aid = _assigned(dsn, "r03u", pid)
    content = {"code": PASS_CODE}
    evaluation.submit_candidate(dsn, Command(request_id="r03u-sub"), aid,
                                content)
    broker.ensure_operation(
        dsn, operation_id="r03u-op", effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["true"],
                 "timeout_ms": 30_000, "max_output_bytes": 1024},
        allocation_id=env["allocation_id"])
    with pytest.raises(SettlementError, match="proves no executable"):
        evaluation.bind_evaluation(
            dsn, Command(request_id="r03u-bad"), aid,
            candidate_digest=payload_digest(content), evaluator_id="s3-eval",
            evaluator_version="v1", invocation_ref="r03u-op")
    with pytest.raises(SettlementError, match="proves no executable"):
        evaluation.bind_evaluation(
            dsn, Command(request_id="r03u-wrong"), aid,
            candidate_digest=payload_digest(content), evaluator_id="s3-eval",
            evaluator_version="v1", invocation_ref="r03u-op",
            executable_digest="changed-grader-bytes", input_digest="x")
    out = evaluation.bind_evaluation(
        dsn, Command(request_id="r03u-ok"), aid,
        candidate_digest=payload_digest(content), evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref="r03u-op",
        executable_digest="pinned-grader", input_digest="x")
    assert out.code == ResultCode.APPLIED


def test_bare_success_refused_for_digest_bound_evaluation(migrated_db,
                                                         launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r03b")
    evaluation.register_evaluator(dsn, Command(request_id="r03b-eval"),
                                  "s3-eval", "v1", code_digest="pinned-grader")
    pid = _freeze(dsn, "r03b")
    aid = _assigned(dsn, "r03b", pid)
    content = {"code": "true"}
    evaluation.submit_candidate(dsn, Command(request_id="r03b-sub"), aid,
                                content)
    broker.ensure_operation(
        dsn, operation_id="r03b-op", effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process",
                 "argv": [sys.executable, "-c",
                          "print('{\"status\": \"ok\", \"data\": {}})"],
                 "timeout_ms": 30_000, "max_output_bytes": 1024},
        allocation_id=env["allocation_id"])
    evaluation.bind_evaluation(
        dsn, Command(request_id="r03b-bind"), aid,
        candidate_digest=payload_digest(content), evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref="r03b-op",
        executable_digest="pinned-grader", input_digest="x")
    broker.dispatch_operation(dsn, "r03b-op",
                              launchers={"local-process": launcher})
    with pytest.raises(SettlementError, match="bare process success"):
        evaluation.submit_evaluator_receipt(
            dsn, Command(request_id="r03b-rc"), receipt_id="r03b-r",
            assignment_id=aid, evaluator_id="s3-eval", evaluator_version="v1",
            invocation_ref="r03b-op",
            result={"outcome": "success", "detail": {"task_id": "t1"}})


def test_unpinned_binding_keeps_legacy_behavior(migrated_db, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r03l")
    evaluation.register_evaluator(dsn, Command(request_id="r03l-eval"),
                                  "s3-eval", "v1")
    pid = _freeze(dsn, "r03l")
    aid = _assigned(dsn, "r03l", pid)
    content = {"code": "true"}
    evaluation.submit_candidate(dsn, Command(request_id="r03l-sub"), aid,
                                content)
    broker.ensure_operation(
        dsn, operation_id="r03l-op", effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["true"],
                 "timeout_ms": 30_000, "max_output_bytes": 1024},
        allocation_id=env["allocation_id"])
    evaluation.bind_evaluation(
        dsn, Command(request_id="r03l-bind"), aid,
        candidate_digest=payload_digest(content), evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref="r03l-op")
    broker.dispatch_operation(dsn, "r03l-op",
                              launchers={"local-process": launcher})
    out = evaluation.submit_evaluator_receipt(
        dsn, Command(request_id="r03l-rc"), receipt_id="r03l-r",
        assignment_id=aid, evaluator_id="s3-eval", evaluator_version="v1",
        invocation_ref="r03l-op",
        result={"outcome": "success", "detail": {"task_id": "t1"}})
    assert out.code == ResultCode.APPLIED


def _publish_offbyone(dsn, launcher, env, tmp_roots, tag, version_id):
    receipt = stage_method(dsn, tmp_roots["staging"],
                           EXPERIMENTS / "offbyone_fixer.py",
                           "offbyone_fixer.py")
    publish_method(dsn, tag, tmp_roots["artifacts"], receipt)
    capabilities.publish_candidate(
        dsn, Command(request_id=f"{tag}-pubcap"), tmp_roots["artifacts"],
        launcher, env["allocation_id"], version_id=version_id,
        family="off_by_one", invocation={"entry": "offbyone_fixer.py"},
        effect={"sandbox": "local-process"}, resource={},
        artifact_digest=receipt["digest"],
        applicability={"family": "off_by_one"}, reference_version="baseline-v0",
        change="test method", hypothesis="fixes off-by-one",
        protocol_id=f"{tag}-p", budget={"units": 500})
    return receipt


def test_invoke_method_returns_mounted_output(migrated_db, tmp_roots,
                                             launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r03i")
    _publish_offbyone(dsn, launcher, env, tmp_roots, "r03i", "method-v1")
    capability = capabilities.get_version(dsn, "method-v1")
    row = broker.read_operation(dsn, "cap-verify-method-v1")
    assert row["payload"]["payload"]["argv"][0] == launcher.staged_python()
    broken = "def sum_to(n):\n    return sum(range(n))\n"
    fixed, source = experiment._invoke_method(
        dsn, launcher, tmp_roots["artifacts"], capability, broken, "r03i",
        env["allocation_id"], None)
    assert "range(n + 1)" in fixed
    assert "REWRITES" in source
    out_path = Path(launcher.run_dir) / "invoke-r03i_exec-default.work" \
        / "outputs" / "fixed.py"
    assert out_path.read_text() == fixed


def test_invoke_method_without_exported_output_refused(
        migrated_db, tmp_roots, launcher, tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "r03m")
    source = tmp_path / "silent.py"
    source.write_text(
        "import json, sys\n"
        "def main(a):\n"
        "    print(json.dumps({'status': 'ok', 'data': {}}))\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main(sys.argv[1:]))\n")
    receipt = stage_method(dsn, tmp_roots["staging"], source, "silent.py")
    publish_method(dsn, "r03m", tmp_roots["artifacts"], receipt)
    capabilities.publish_candidate(
        dsn, Command(request_id="r03m-pubcap"), tmp_roots["artifacts"],
        launcher, env["allocation_id"], version_id="silent-v1",
        family="off_by_one", invocation={"entry": "silent.py"},
        effect={"sandbox": "local-process"}, resource={},
        artifact_digest=receipt["digest"],
        applicability={"family": "off_by_one"}, reference_version="baseline-v0",
        change="test method", hypothesis="writes nothing",
        protocol_id="r03m-p", budget={"units": 500})
    capability = capabilities.get_version(dsn, "silent-v1")
    with pytest.raises(SettlementError, match="no exported output"):
        experiment._invoke_method(
            dsn, launcher, tmp_roots["artifacts"], capability,
            "def f(x): return x\n", "r03m", env["allocation_id"], None)


def test_arm_prompts_share_tools_and_c_carries_invocation():
    task = {"id": "t", "family": "off_by_one", "broken": "broken-src"}
    lessons = {"off_by_one": "lesson-text"}
    retained = {"source": "method-src",
                "invocation": {"invoke_op": "invoke-x", "fixed": "fixed-src"}}
    prompts = {arm: experiment._arm_prompt(arm, task, lessons, retained)
               for arm in ("A", "B", "C")}
    assert prompts["A"]["tools"] == prompts["B"]["tools"] == \
        prompts["C"]["tools"] == experiment._within_task_tools()
    assert prompts["C"]["retained_method"] == "method-src"
    assert prompts["C"]["retained_invocation"] == \
        {"invoke_op": "invoke-x", "fixed": "fixed-src"}
    assert "retained_method" not in prompts["A"]


def test_noop_method_is_identity(tmp_path):
    method = tmp_path / "noop.py"
    method.write_text(experiment._synthesize_noop())
    probe = tmp_path / "in.py"
    out = tmp_path / "out.py"
    probe.write_text("def f(x): return x - 1\n")
    selftest = subprocess.run([sys.executable, str(method), "--selftest"],
                              capture_output=True, text=True, timeout=30)
    assert selftest.returncode == 0
    assert json.loads(selftest.stdout)["status"] == "ok"
    run = subprocess.run([sys.executable, str(method), str(probe), str(out)],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0
    assert json.loads(run.stdout) == {"status": "ok", "data": {"known": False}}
    assert out.read_text() == "def f(x): return x - 1\n"


def test_group_candidate_and_multi_release_gate():
    by_id = {"a": {"family": "f1"}, "b": {"family": "f1"},
             "c": {"family": "f2"}}
    assert experiment._group_candidate(["a", "b"], by_id, {"f1": "v1"}) == "v1"
    assert experiment._group_candidate(["a"], by_id, {}) == ""
    multi = experiment._group_candidate(["a", "c"], by_id,
                                        {"f1": "v1", "f2": "v2"})
    assert multi == "multi:v1+v2"
    capabilities._check_tested_versions("p", multi, ["v2", "v1"])
    with pytest.raises(SettlementError, match="pin mismatch"):
        capabilities._check_tested_versions("p", multi, ["v1"])
    with pytest.raises(SettlementError, match="pin mismatch"):
        capabilities._check_tested_versions("p", "v1", ["v2"])


def _small_run(dsn, launcher, env, tmp_roots, tag):
    fixes = {t["id"]: t["fixed"] for t in
             [BY_ID[i] for i in ("dev-sum", "panel-triangular",
                                 "transfer-sign")]}
    broken = {t["id"]: t["broken"] for t in
              [BY_ID[i] for i in ("dev-sum", "panel-triangular",
                                  "transfer-sign")]}
    double = ScriptedDouble({("DEV", "dev-sum"): True}, fixes, broken)
    return experiment.run_abcs(
        dsn, launcher=launcher, artifacts_root=tmp_roots["artifacts"],
        allocation_id=env["allocation_id"], investigation_id=env["investigation_id"],
        tasks=[BY_ID[i] for i in ("dev-sum", "panel-triangular",
                                  "transfer-sign")],
        dev_ids=["dev-sum"], panel_ids=["panel-triangular"],
        transfer_ids=["transfer-sign"], lessons=None, double=double,
        grader_path=GRADER, protocol_prefix=tag, fixer_version="fixer-v1")


def _model_prompt(dsn, operation_id):
    row = broker.read_operation(dsn, operation_id)
    return json.loads(row["payload"]["payload"]["messages"][-1]["content"])


def test_r03_run_binds_actual_versions_and_honest_arms(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r03r", authorized=500_000)
    report = _small_run(dsn, launcher, env, tmp_roots, "r03r")
    assert report["development"]["methods"] == {"off_by_one": "fixer-v1"}
    acquisition = report["development"]["acquisition"]["off_by_one"]
    assert acquisition["method_kind"] == "exact-lookup-baseline"
    assert acquisition["version_conflict"] is None
    assert report["selection"]["group_candidate"]["panel-C"] == "fixer-v1"
    assert report["selection"]["method_set"] == {"off_by_one": "fixer-v1"}
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT candidate_version FROM trial_protocols"
                        " WHERE id = %s", ("r03r-panel-C",))
            assert cur.fetchone()[0] == "fixer-v1"
            cur.execute("SELECT code_digest FROM evaluator_packages"
                        " WHERE id = %s", ("s3-eval",))
            assert cur.fetchone()[0] == _grader_pin()
            cur.execute("SELECT content FROM candidate_submissions"
                        " WHERE assignment_id = %s",
                        ("r03r-panel-C:candidate:panel-triangular",))
            submitted = dict(cur.fetchone()[0])
            cur.execute("SELECT detail FROM trial_results"
                        " WHERE assignment_id = %s",
                        ("r03r-panel-C:candidate:panel-triangular",))
            detail = dict(cur.fetchone()[0])
            conn.commit()
    assert submitted["method"]["version"] == "fixer-v1"
    assert submitted["method"]["artifact_digest"] == \
        acquisition["artifact_digest"]
    assert detail["method"] == "fixer-v1"
    assert detail["artifact_digest"] == acquisition["artifact_digest"]
    assert report["arms"]["C"]["panel-triangular"]["outcome"] == "failure"
    invoke_op = report["invocations"][0]
    assert report["invocation_results"][invoke_op]["fixed"] == \
        BY_ID["panel-triangular"]["broken"]
    prompts = {(arm, task): _model_prompt(dsn, report["model_ops"][arm][task])
               for arm in ("A", "B", "C")
               for task in ("panel-triangular", "transfer-sign")}
    assert len({json.dumps(p["tools"], sort_keys=True) for p in
                prompts.values()}) == 1
    assert prompts[("C", "panel-triangular")]["retained_invocation"] == \
        {"invoke_op": invoke_op,
         "fixed": BY_ID["panel-triangular"]["broken"]}
    assert report["ablation_noop"]["panel-triangular"]["outcome"] == "failure"
    assert report["ablation_noop"]["panel-triangular"]["invoke_op"] != invoke_op
    assert report["releases"]["panel-C"]["status"] == "skipped-synthetic"
    assert report["releases"]["transfer-C"]["status"] == "skipped-synthetic"
    assert report["development"]["noop_ablation"]["off_by_one"] != "fixer-v1"


def test_stem_conflict_freezes_actual_and_protocol_names_it(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r03s", authorized=500_000)
    _publish_offbyone(dsn, launcher, env, tmp_roots, "r03s-pre", "fixer-v1")
    stem_digest = capabilities.get_version(dsn, "fixer-v1")["artifact_digest"]
    report = _small_run(dsn, launcher, env, tmp_roots, "r03s")
    frozen = report["development"]["methods"]["off_by_one"]
    assert frozen != "fixer-v1" and frozen.startswith("fixer-v1-")
    conflict = report["development"]["acquisition"]["off_by_one"][
        "version_conflict"]
    assert conflict == {"stem": "fixer-v1", "occupied_by": stem_digest}
    assert capabilities.get_version(dsn, "fixer-v1")["artifact_digest"] == \
        stem_digest
    assert report["selection"]["group_candidate"]["panel-C"] == frozen
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT candidate_version FROM trial_protocols"
                        " WHERE id = %s", ("r03s-panel-C",))
            assert cur.fetchone()[0] == frozen
            cur.execute("SELECT detail FROM trial_results"
                        " WHERE assignment_id = %s",
                        ("r03s-panel-C:candidate:panel-triangular",))
            detail = dict(cur.fetchone()[0])
            conn.commit()
    assert detail["method"] == frozen
