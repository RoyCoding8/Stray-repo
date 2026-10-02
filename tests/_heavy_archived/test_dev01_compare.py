"""Dev01 comparison/use lane (D-CMP): DEV-05..DEV-10 use-side checks.

Runs the frozen ``run_abcs`` harness read-only with deterministic scripted
doubles (``experiments/doubles.py``: every model response carries
``simulated: True``) on real PostgreSQL plus real subprocess sandboxes
(``LocalLauncher``). Live inference is blocked environment-wide, so every
outcome here is labeled fixture evidence: ``simulated=True`` runs never
release, and the release/rejection paths use explicitly labeled
``dev01cmp-fixture-`` protocols.

Source groups (DEV-07): development uses ``fault_tasks`` off_by_one dev
IDs, the protected-eval panel uses ``fault_tasks`` off_by_one panel IDs
(disjoint IDs, known shared loop-bound structure), and subsequent use
uses ``dev01_tasks`` missing_guard IDs (disjoint IDs and disjoint fault
structure). See ``experiments/dev01_tasks.py`` GROUPING_RULE.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "experiments")

import pytest

from settlement import broker, capabilities, db, evaluation, experiment, store, trials
from settlement.common import (
    Command,
    ResultCode,
    SettlementError,
    Unauthorized,
    payload_digest,
)
from settlement.launcher_local import LocalLauncher

from dev01_tasks import BY_ID as DEV01_BY_ID
from dev01_tasks import GROUPING_RULE, USE_IDS as DEV01_USE_IDS
from doubles import ScriptedDouble
from fault_tasks import BY_ID
from test_s3_helpers import EXPERIMENTS, acquire, publish_method, seed_env, stage_method

GRADER = str(EXPERIMENTS / "run_tests.py")
DEV_IDS = ["dev-sum"]
PANEL_IDS = ["panel-triangular", "panel-batcher"]
TRANSFER_IDS = ["transfer-sign"] + list(DEV01_USE_IDS)
GROUPS = [{"name": "development", "kind": "development"},
          {"name": "panel", "kind": "protected-eval"}]


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _tasks():
    return [BY_ID[i] for i in DEV_IDS + PANEL_IDS + ["transfer-sign"]] + \
        [DEV01_BY_ID[i] for i in DEV01_USE_IDS]


def _double(tasks, dev_ids):
    fixes = {t["id"]: t["fixed"] for t in tasks}
    broken = {t["id"]: t["broken"] for t in tasks}
    competence = {(arm, task_id): True for arm in ("DEV",)
                  for task_id in dev_ids}
    return ScriptedDouble(competence, fixes, broken)


def _run_compare(dsn, launcher, roots, env, tag, double=None):
    tasks = _tasks()
    report = experiment.run_abcs(
        dsn, launcher=launcher, artifacts_root=roots["artifacts"],
        allocation_id=env["allocation_id"],
        investigation_id=env["investigation_id"], tasks=tasks,
        dev_ids=list(DEV_IDS), panel_ids=list(PANEL_IDS),
        transfer_ids=list(TRANSFER_IDS), lessons=None,
        double=double if double is not None else _double(tasks, DEV_IDS),
        grader_path=GRADER, protocol_prefix=tag,
        fixer_version=f"{tag}-fixer-v1")
    return report


def _count(dsn, sql, params=()):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            value = cur.fetchone()[0]
            conn.commit()
    return value


def _invoke_op_for(report, task_id):
    for op_id, entry in report["accounting"]["ops"].items():
        if entry.get("kind") == "invoke" and entry.get("task_id") == task_id \
                and not op_id.endswith("-noop"):
            return op_id
    raise AssertionError(f"no C invocation recorded for {task_id}")


def test_dev05_fresh_process_resume_after_publication(
        migrated_db, tmp_roots, launcher, tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "d05", authorized=2_000_000)
    report = _run_compare(dsn, launcher, tmp_roots, env, "d05")
    version = report["development"]["methods"]["off_by_one"]
    digest = report["development"]["acquisition"]["off_by_one"]["artifact_digest"]
    assert (tmp_roots["artifacts"] / digest).is_file()
    invoke_op = _invoke_op_for(report, "panel-triangular")
    expected_fixed = report["invocation_results"][invoke_op]["fixed"]
    constructions_before = _count(
        dsn, "SELECT COUNT(*) FROM receipts WHERE operation_id LIKE 'cap-verify-%%'")
    versions_before = _count(dsn, "SELECT COUNT(*) FROM capability_versions")
    cap_before = capabilities.get_version(dsn, version)

    resume_runs = tmp_path / "resume-runs"
    resume_runs.mkdir()
    assert list(resume_runs.iterdir()) == []
    root = Path(__file__).parents[2]
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "src"), str(root / "experiments")])
    script = (
        "import base64, hashlib, json, os\n"
        "from pathlib import Path\n"
        "from settlement import capabilities, experiment\n"
        "from settlement.launcher_local import LocalLauncher\n"
        "dsn = os.environ['DEV05_DSN']\n"
        "roots = Path(os.environ['DEV05_ARTIFACTS'])\n"
        "version = os.environ['DEV05_VERSION']\n"
        "broken = base64.b64decode(os.environ['DEV05_BROKEN']).decode()\n"
        "cap = capabilities.get_version(dsn, version)\n"
        "assert cap is not None, 'published version absent from durable state'\n"
        "raw = (roots / cap['artifact_digest']).read_bytes()\n"
        "assert hashlib.sha256(raw).hexdigest() == cap['artifact_digest'],"
        " 'artifact bytes lost'\n"
        "launcher = LocalLauncher(os.environ['DEV05_RUNDIR'])\n"
        "fixed, _ = experiment._invoke_method(dsn, launcher, roots, cap,"
        " broken, 'd05-resume', os.environ['DEV05_ALLOC'], None)\n"
        "print(json.dumps({'fixed': fixed,"
        " 'artifact_digest': cap['artifact_digest']}))\n")
    child_env["DEV05_DSN"] = dsn
    child_env["DEV05_ARTIFACTS"] = str(tmp_roots["artifacts"])
    child_env["DEV05_VERSION"] = version
    child_env["DEV05_ALLOC"] = env["allocation_id"]
    child_env["DEV05_RUNDIR"] = str(resume_runs)
    child_env["DEV05_BROKEN"] = base64.b64encode(
        BY_ID["panel-triangular"]["broken"].encode()).decode()
    proc = subprocess.run([sys.executable, "-c", script], env=child_env,
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr[-2000:]
    resumed = json.loads(proc.stdout)
    assert resumed["fixed"] == expected_fixed
    assert resumed["artifact_digest"] == digest
    assert any(resume_runs.iterdir())
    assert _count(
        dsn, "SELECT COUNT(*) FROM receipts WHERE operation_id LIKE 'cap-verify-%%'") == \
        constructions_before
    assert _count(dsn, "SELECT COUNT(*) FROM capability_versions") == versions_before
    cap_after = capabilities.get_version(dsn, version)
    assert cap_after["artifact_digest"] == cap_before["artifact_digest"]
    assert cap_after["verification_op"] == cap_before["verification_op"]


def test_dev06_abc_affordances_and_accounting(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "d06", authorized=2_000_000)
    report = _run_compare(dsn, launcher, tmp_roots, env, "d06")
    assert report["simulated"] is True
    assert report["development"]["acquisition"]["off_by_one"]["method_kind"] == \
        "exact-lookup-baseline"

    prompts = {}
    for arm in ("A", "B", "C"):
        for task_id in PANEL_IDS + TRANSFER_IDS:
            row = broker.read_operation(dsn, report["model_ops"][arm][task_id])
            prompts[(arm, task_id)] = json.loads(
                row["payload"]["payload"]["messages"][-1]["content"])
    assert len({json.dumps(p["tools"], sort_keys=True)
                for p in prompts.values()}) == 1
    for task_id in PANEL_IDS:
        invoke_op = _invoke_op_for(report, task_id)
        assert prompts[("C", task_id)]["retained_invocation"] == {
            "invoke_op": invoke_op,
            "fixed": report["invocation_results"][invoke_op]["fixed"]}
    assert set(report["ablation_noop"]) == set(PANEL_IDS)
    for task_id, ablation in report["ablation_noop"].items():
        assert ablation["invoke_op"] != _invoke_op_for(report, task_id)
        assert ablation["invoke_op"] in report["accounting"]["ops"]
        assert ablation["grade_op"] in report["accounting"]["ops"]

    totals = report["accounting"]["totals"]
    assert totals["unresolved"] == 0
    ops = report["accounting"]["ops"]
    assert {e["arm"] for e in ops.values()} == {"dev", "A", "B", "C"}
    assert sum(e["settled"] for e in ops.values()) == totals["settled"]

    dev_pid = "d06-dev"
    acquisition = trials.development_expenditure(dsn, dev_pid)
    dev_settled = sum(e["settled"] for e in ops.values() if e["arm"] == "dev")
    assert acquisition["development_total"] == dev_settled
    assert acquisition["use_total"] == 0
    standalone = {}
    for arm in ("A", "B", "C"):
        arm_settled = sum(e["settled"] for e in ops.values() if e["arm"] == arm)
        standalone[arm] = acquisition["development_total"] + arm_settled
        assert standalone[arm] > arm_settled
        ledger = report["budgets"][arm]["ledger_by_category"]
        assert set(ledger) == set(trials.CATEGORIES)
        assert report["budgets"][arm]["matched_caps"] == {
            "sandbox_ms": experiment.GRADER_TIMEOUT_MS, "tokens": experiment.MODEL_TOKENS}
        assert report["budgets"][arm]["token_estimates"]["basis"] == (
            "provider receipt usage; not a billing measure")
    cash_once = dev_settled + sum(
        e["settled"] for e in ops.values() if e["arm"] in ("A", "B", "C"))
    assert cash_once == totals["settled"]
    status = store.allocation_status(dsn, env["allocation_id"])
    assert status["consumed"] + status["reserved"] >= totals["settled"]
    assert status["authorized"] - status["consumed"] - status["reserved"] >= 0

    assert report["releases"]["panel-C"]["status"] == "skipped-synthetic"
    assert report["releases"]["transfer-C"]["status"] == "skipped-synthetic"
    for arm_tasks in report["arms"].values():
        for outcome in arm_tasks.values():
            assert outcome["simulated"] is True


def test_dev07_frozen_source_group_splits(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "d07", authorized=2_000_000)
    double = _double(_tasks(), DEV_IDS)
    report = _run_compare(dsn, launcher, tmp_roots, env, "d07", double=double)
    assert "disjoint fault structure" in GROUPING_RULE
    dev_set, panel_set, use_set = set(DEV_IDS), set(PANEL_IDS), set(TRANSFER_IDS)
    assert dev_set.isdisjoint(panel_set) and dev_set.isdisjoint(use_set) \
        and panel_set.isdisjoint(use_set)
    assert {BY_ID[i]["family"] for i in dev_set | panel_set} == {"off_by_one"}
    assert {DEV01_BY_ID[i]["family"] for i in DEV01_USE_IDS} == {"missing_guard"}
    assert {DEV01_BY_ID[i]["source_group"] for i in DEV01_USE_IDS} == {"dev01-guard"}

    frozen = report["development"]["methods"]["off_by_one"]
    digest = report["development"]["acquisition"]["off_by_one"]["artifact_digest"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, candidate_version, frozen FROM trial_protocols")
            protocols = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            conn.commit()
    assert protocols["d07-dev"] == ("", True)
    assert protocols["d07-panel-C"] == (frozen, True)
    assert protocols["d07-transfer-C"][0] == \
        report["selection"]["group_candidate"]["transfer-C"]
    assert all(frozen_flag for _, frozen_flag in protocols.values())

    for name in ("panel-C", "transfer-C"):
        verdict = trials.verdict(dsn, f"d07-{name}")
        assert verdict == report["verdicts"][name]
        rows = trials.protocol_results(dsn, f"d07-{name}")
        assert rows and all(r["outcome"] is not None for r in rows)
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT assignment_id, evaluator_version, invocation_ref"
                        " FROM evaluator_receipts WHERE assignment_id LIKE 'd07-%%'"
                        " ORDER BY assignment_id")
            receipts = cur.fetchall()
            cur.execute("SELECT assignment_id, content FROM candidate_submissions"
                        " WHERE assignment_id LIKE 'd07-%%'")
            submissions = {r[0]: dict(r[1]) for r in cur.fetchall()}
            conn.commit()
    assert receipts
    for assignment_id, evaluator_version, invocation_ref in receipts:
        assert evaluator_version == "v1"
        if assignment_id.startswith("d07-panel-C:candidate:"):
            submitted = submissions[assignment_id]
            assert submitted["method"]["version"] == frozen
            assert submitted["method"]["artifact_digest"] == digest
            assert invocation_ref == \
                report["grade_ops"]["C"][assignment_id.split(":")[-1]]
    assert len(report.get("abstentions", [])) == len(TRANSFER_IDS)

    with pytest.raises(Unauthorized, match="never served"):
        evaluation.hidden_answer(dsn, "panel-triangular", "candidate")
    hidden = evaluation.hidden_answer(dsn, "panel-triangular", "evaluator")
    assert hidden["cases"] == BY_ID["panel-triangular"]["cases"]
    visible_ids = [c["id"] for c in evaluation.candidate_view(dsn)]
    assert not any(v.startswith("s3-answer:") for v in visible_ids)
    dev_calls = [c for c in double.calls if c.get("arm") == "DEV"]
    assert {c["task_id"] for c in dev_calls} == set(DEV_IDS)
    lesson_row = broker.read_operation(dsn, "d07-DEV-lesson")
    dev_record = json.loads(
        lesson_row["payload"]["payload"]["messages"][-1]["content"])
    assert {r["task_id"] for r in dev_record["dev_transcripts"]} == set(DEV_IDS)


def _grader_pin():
    return hashlib.sha256(Path(GRADER).read_bytes()).hexdigest()


def _publish_fixture_method(dsn, launcher, roots, staging, tag, version_id,
                            source_path, entry, family, protocol_id):
    receipt = stage_method(dsn, staging, source_path, entry)
    publish_method(dsn, tag, roots["artifacts"], receipt)
    capabilities.publish_candidate(
        dsn, Command(request_id=f"{tag}-pubcap"), roots["artifacts"],
        launcher, f"{tag}-alloc", version_id=version_id, family=family,
        invocation={"entry": entry}, effect={"sandbox": "local-process"},
        resource={}, artifact_digest=receipt["digest"],
        applicability={"family": family}, reference_version="baseline-v0",
        change="dev01cmp labeled fixture", hypothesis="fixture mechanism probe",
        protocol_id=protocol_id, budget={"units": 500})
    return receipt


def _freeze_fixture_protocol(dsn, tag, candidate_version, task_ids):
    pid = f"{tag}-p"
    trials.freeze_protocol(
        dsn, Command(request_id=f"{tag}-frz"), protocol_id=pid,
        candidate_version=candidate_version, reference_version="baseline-v0",
        evaluator_version="v1", task_groups=GROUPS, budgets={},
        metrics=["success_rate"], stopping={"rule": "fixed-panel"},
        exclusions=[], uncertainty={"treatment": "fixture-only"})
    evaluation.register_evaluator(dsn, Command(request_id=f"{tag}-eval"),
                                  "s3-eval", "v1", code_digest=_grader_pin())
    for tid in task_ids:
        evaluation.propose_hidden_answer(
            dsn, Command(request_id=f"{tag}-answer-{tid}"), tid,
            {"cases": BY_ID[tid]["cases"]})
    return pid


def _fixture_arm(dsn, launcher, env, tag, pid, task, arm, code, method=None):
    tid = task["id"]
    assignment_id = f"{pid}:{arm}:{tid}"
    trials.assign(dsn, Command(request_id=f"{tag}-{arm}-{tid}-assign",
                               payload={}), pid, tid, "panel", arm,
                  {"entry_fn": task["entry_fn"]})
    content = {"code": code}
    if method is not None:
        content["method"] = method
    evaluation.submit_candidate(
        dsn, Command(request_id=f"{tag}-{arm}-{tid}-sub"), assignment_id,
        content)
    op_id, staged = experiment._prepare_grade(
        dsn, launcher, code, task["cases"], f"{tag}-{arm}-{tid}",
        env["allocation_id"], None, GRADER)
    evaluation.bind_evaluation(
        dsn, Command(request_id=f"{tag}-{arm}-{tid}-bind"), assignment_id,
        candidate_digest=payload_digest(content), evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref=op_id,
        executable_digest=staged["grader.py"][1],
        input_digest=staged["cases.json"][1])
    outcome = experiment._dispatch_grade(dsn, launcher, op_id,
                                         len(task["cases"]), staged)
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id=f"{tag}-{arm}-{tid}-rc"),
        receipt_id=f"{tag}-{arm}-{tid}-r", assignment_id=assignment_id,
        evaluator_id="s3-eval", evaluator_version="v1", invocation_ref=op_id,
        result={"outcome": outcome, "detail": {"task_id": tid},
                "conditions": {"arm": arm, "evidence": "dev01cmp-fixture"},
                "cost": {}})
    return outcome, op_id


def test_dev08_release_path_fixture(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "d08r", authorized=500_000)
    task = BY_ID["panel-triangular"]
    version = "d08r-fixer-v1"
    receipt = _publish_fixture_method(
        dsn, launcher, tmp_roots, tmp_roots["staging"], "d08r", version,
        EXPERIMENTS / "offbyone_fixer.py", "offbyone_fixer.py",
        "off_by_one", "d08r-p")
    pid = _freeze_fixture_protocol(dsn, "d08r", version, ["panel-triangular"])
    method = {"version": version, "artifact_digest": receipt["digest"]}
    cand_outcome, _ = _fixture_arm(dsn, launcher, env, "d08r", pid, task,
                                   "candidate", task["fixed"], method)
    ref_outcome, _ = _fixture_arm(dsn, launcher, env, "d08r", pid, task,
                                  "reference", task["broken"])
    assert (cand_outcome, ref_outcome) == ("success", "failure")
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    out = capabilities.scoped_release(
        dsn, Command(request_id="d08r-rel"), release_id="d08r-rel",
        protocol_id=pid, versions=[version],
        scope={"family": "off_by_one"}, disposition="limited",
        fallback="baseline-v0", policy_version="d08r-router",
        invalidation={}, evidence_refs=[], evaluator_version="v1")
    assert out.code == ResultCode.APPLIED
    capabilities.save_router_policy(
        dsn, Command(request_id="d08r-router"), version="d08r-router",
        mapping={"off_by_one": version})
    routed = capabilities.route(dsn, "d08r-router", "off_by_one")
    assert routed == {"family": "off_by_one", "decision": "select",
                      "version_id": version}
    attempt_id = "d08r-use-worker"
    acquire(dsn, "d08r", attempt_id, env)
    capabilities.pin_capability(dsn, attempt_id, version)
    capability = capabilities.get_version(dsn, version)
    fixed, source = experiment._invoke_method(
        dsn, launcher, tmp_roots["artifacts"], capability, task["broken"],
        "d08r-use", env["allocation_id"], attempt_id)
    assert "REWRITES" in source
    assert "range(n + 1)" in fixed
    use_op, _ = experiment._prepare_grade(
        dsn, launcher, fixed, task["cases"], "d08r-use-grade",
        env["allocation_id"], attempt_id, GRADER)
    assert experiment._dispatch_grade(dsn, launcher, use_op,
                                      len(task["cases"])) == "success"


def test_dev08_rejection_preserves_incumbent(
        migrated_db, tmp_roots, launcher, tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "d08j", authorized=500_000)
    noop_src = tmp_path / "noop.py"
    noop_src.write_text(experiment._synthesize_noop())
    version = "d08j-lose-v1"
    _publish_fixture_method(dsn, launcher, tmp_roots, tmp_roots["staging"],
                            "d08j", version, noop_src, "noop.py",
                            "off_by_one", "d08j-p")
    pid = _freeze_fixture_protocol(dsn, "d08j", version, ["panel-triangular"])
    task = BY_ID["panel-triangular"]
    cand_outcome, _ = _fixture_arm(dsn, launcher, env, "d08j", pid, task,
                                   "candidate", task["broken"],
                                   {"version": version, "artifact_digest":
                                    capabilities.get_version(
                                        dsn, version)["artifact_digest"]})
    ref_outcome, _ = _fixture_arm(dsn, launcher, env, "d08j", pid, task,
                                  "reference", task["fixed"])
    assert (cand_outcome, ref_outcome) == ("failure", "success")
    assert trials.verdict(dsn, pid)["label"] == "regression"
    with pytest.raises(SettlementError, match="regressed"):
        capabilities.scoped_release(
            dsn, Command(request_id="d08j-rel"), release_id="d08j-rel",
            protocol_id=pid, versions=[version],
            scope={"family": "off_by_one"}, disposition="limited",
            fallback="baseline-v0", policy_version="d08j-router",
            invalidation={}, evidence_refs=[], evaluator_version="v1")
    with pytest.raises(SettlementError, match="regressed"):
        capabilities.scoped_release(
            dsn, Command(request_id="d08j-rel-d"), release_id="d08j-rel-d",
            protocol_id=pid, versions=[version],
            scope={"family": "off_by_one"}, disposition="default",
            fallback="baseline-v0", policy_version="d08j-router",
            invalidation={}, evidence_refs=[], evaluator_version="v1")
    assert _count(dsn, "SELECT COUNT(*) FROM capability_releases") == 0
    assert capabilities.releases_for_scope(dsn, "off_by_one") == []


FAIL_METHOD_SRC = (
    "import json\nimport sys\n"
    "def main(argv):\n"
    "    if argv == ['--selftest']:\n"
    "        print(json.dumps({'status': 'ok', 'data': {}}))\n"
    "        return 0\n"
    "    print(json.dumps({'status': 'error', 'data': {},"
    " 'error': 'fixture crash'}))\n"
    "    return 1\n"
    "if __name__ == '__main__':\n"
    "    raise SystemExit(main(sys.argv[1:]))\n")


def test_dev09_use_failure_fallback_and_unknown_routing(
        migrated_db, tmp_roots, launcher, tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "d09", authorized=500_000)
    fail_src = tmp_path / "fail_method.py"
    fail_src.write_text(FAIL_METHOD_SRC)
    version = "d09-fail-v1"
    _publish_fixture_method(dsn, launcher, tmp_roots, tmp_roots["staging"],
                            "d09", version, fail_src, "fail_method.py",
                            "off_by_one", "d09-use-p")
    pid = _freeze_fixture_protocol(dsn, "d09-use", version, ["panel-batcher"])
    status_before = store.allocation_status(dsn, env["allocation_id"])
    attempt_id = "d09-use-worker"
    acquire(dsn, "d09", attempt_id, env)
    capability = capabilities.get_version(dsn, version)
    with pytest.raises(SettlementError, match="method invocation .* failed"):
        experiment._invoke_method(
            dsn, launcher, tmp_roots["artifacts"], capability,
            BY_ID["panel-batcher"]["broken"], "d09-invoke",
            env["allocation_id"], attempt_id)
    invoke_entry = experiment._op_accounting(dsn, "invoke-d09-invoke")
    assert invoke_entry["outcome"] == "failure"

    fallback_op, _ = experiment._prepare_grade(
        dsn, launcher, BY_ID["panel-batcher"]["broken"],
        BY_ID["panel-batcher"]["cases"], "d09-fallback",
        env["allocation_id"], attempt_id, GRADER)
    fallback_outcome = experiment._dispatch_grade(
        dsn, launcher, fallback_op, len(BY_ID["panel-batcher"]["cases"]))
    assert fallback_outcome == "failure"
    grade_entry = experiment._op_accounting(dsn, fallback_op)
    assert grade_entry["outcome"] == "success"
    assert grade_entry["unresolved"] == 0
    trials.record_expenditure(dsn, pid, "failed_trials",
                              invoke_entry["settled"],
                              "failed method invocation",
                              operation_id="invoke-d09-invoke")
    trials.record_expenditure(dsn, pid, "failed_trials",
                              grade_entry["settled"],
                              "incumbent fallback", operation_id=fallback_op)
    trials.assign(dsn, Command(request_id="d09-fb-assign", payload={}), pid,
                  "panel-batcher", "panel", "reference",
                  {"entry_fn": "batches"})
    trials.record_result(
        dsn, Command(request_id="d09-fb-result"), assignment_id=f"{pid}:reference:panel-batcher",
        outcome=fallback_outcome, invocation_ref=fallback_op,
        conditions={"routing": "incumbent-fallback",
                    "method_failure": "invoke-d09-invoke"},
        cost={"settled_units": grade_entry["settled"]})
    rows = trials.protocol_results(dsn, pid)
    assert rows[0]["outcome"] == "failure"
    assert rows[0]["conditions"]["routing"] == "incumbent-fallback"
    spent = trials.development_expenditure(dsn, pid)
    assert spent["by_category"]["failed_trials"] == \
        invoke_entry["settled"] + grade_entry["settled"]
    status_after = store.allocation_status(dsn, env["allocation_id"])
    assert status_after["consumed"] > status_before["consumed"]
    assert status_after["authorized"] - status_after["consumed"] - \
        status_after["reserved"] >= 0

    capabilities.save_router_policy(
        dsn, Command(request_id="d09-router"), version="d09-router",
        mapping={"off_by_one": version})
    assert capabilities.route(dsn, "d09-router", "off_by_one") == {
        "family": "off_by_one", "decision": "select", "version_id": version}
    unknown = capabilities.route(dsn, "d09-router", "missing_guard")
    assert unknown == {"family": "missing_guard", "decision": "abstain",
                       "version_id": None}


def test_dev10_rejected_episode_inspectable(
        migrated_db, tmp_roots, launcher, tmp_path):
    dsn = migrated_db
    env = seed_env(dsn, "d10", authorized=500_000)
    noop_src = tmp_path / "noop.py"
    noop_src.write_text(experiment._synthesize_noop())
    version = "d10-lose-v1"
    receipt = _publish_fixture_method(
        dsn, launcher, tmp_roots, tmp_roots["staging"], "d10", version,
        noop_src, "noop.py", "off_by_one", "d10-p")
    pid = _freeze_fixture_protocol(dsn, "d10", version, ["panel-batcher"])
    task = BY_ID["panel-batcher"]
    method = {"version": version, "artifact_digest": receipt["digest"]}
    cand_outcome, cand_op = _fixture_arm(dsn, launcher, env, "d10", pid,
                                         task, "candidate", task["broken"],
                                         method)
    ref_outcome, ref_op = _fixture_arm(dsn, launcher, env, "d10", pid, task,
                                       "reference", task["fixed"])
    assert (cand_outcome, ref_outcome) == ("failure", "success")
    trials.record_expenditure(
        dsn, pid, "failed_trials",
        experiment._op_accounting(dsn, cand_op)["settled"],
        "rejected candidate", operation_id=cand_op)
    trials.record_expenditure(
        dsn, pid, "evaluation",
        experiment._op_accounting(dsn, ref_op)["settled"],
        "incumbent reference", operation_id=ref_op)
    with pytest.raises(SettlementError, match="regressed"):
        capabilities.scoped_release(
            dsn, Command(request_id="d10-rel"), release_id="d10-rel",
            protocol_id=pid, versions=[version],
            scope={"family": "off_by_one"}, disposition="limited",
            fallback="baseline-v0", policy_version="d10-router",
            invalidation={}, evidence_refs=[], evaluator_version="v1")

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT frozen, candidate_version, evaluator_version"
                        " FROM trial_protocols WHERE id = %s", (pid,))
            frozen, pinned_candidate, pinned_evaluator = cur.fetchone()
            conn.commit()
    assert frozen is True and pinned_candidate == version
    assert pinned_evaluator == "v1"
    rows = trials.protocol_results(dsn, pid)
    assert len(rows) == 2 and all(r["outcome"] is not None for r in rows)
    verdict = trials.verdict(dsn, pid)
    assert verdict["label"] == "regression"
    assert verdict["candidate_successes"] == 0
    assert verdict["reference_successes"] == 1
    cap = capabilities.get_version(dsn, version)
    assert cap["hypothesis"] == "fixture mechanism probe"
    assert cap["reference_version"] == "baseline-v0"
    assert cap["protocol_id"] == "d10-p"
    assert cap["artifact_digest"] == receipt["digest"]
    assert cap["verification_op"] == f"cap-verify-{version}"
    from settlement import artifacts
    assert artifacts.bytes_match(tmp_roots["artifacts"], receipt["digest"])
    assert _count(dsn, "SELECT COUNT(*) FROM receipts WHERE operation_id = %s",
                  (f"cap-verify-{version}",)) >= 1
    spent = trials.development_expenditure(dsn, pid)
    assert spent["by_category"]["failed_trials"] > 0
    assert spent["by_category"]["evaluation"] > 0
    assert _count(dsn, "SELECT COUNT(*) FROM evaluator_receipts"
                       " WHERE assignment_id LIKE 'd10-p:%%'") == 2
    assert _count(dsn, "SELECT COUNT(*) FROM candidate_submissions"
                       " WHERE assignment_id LIKE 'd10-p:%%'") == 2
    assert _count(dsn, "SELECT COUNT(*) FROM attempt_capability_pins"
                       " WHERE version_id = %s", (version,)) == 0
    assert _count(dsn, "SELECT COUNT(*) FROM capability_releases") == 0
    capabilities.save_router_policy(
        dsn, Command(request_id="d10-router"), version="d10-router",
        mapping={"wrong_operator": "elsewhere-v9"})
    assert capabilities.route(dsn, "d10-router", "off_by_one") == {
        "family": "off_by_one", "decision": "abstain", "version_id": None}
