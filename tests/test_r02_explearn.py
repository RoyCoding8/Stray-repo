"""R02-007/010/011 experiment and learning regressions.

Covers the REVIEW-02 fix cycle for the experiment owner paths: grader-child
isolation (answer-lookup attack fails from unavailability), fair comparison
(C is graded on its own model text; unrelated registry entries are ignored
in favor of the frozen artifact), and CLI grant-cap binding.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg.rows import dict_row

sys.path.insert(0, "experiments")

from settlement import artifacts, capabilities, db, experiment, store
from settlement.common import Command, SettlementError
from settlement.launcher_local import LocalLauncher

from doubles import ScriptedDouble
from fault_tasks import BY_ID, TASKS
from run_live_abc import _bind_grant_cap, _select_launcher
from test_s3_helpers import EXPERIMENTS, seed_env

ROOT = Path(__file__).parent.parent
GRADER = str(EXPERIMENTS / "run_tests.py")


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _double(competence):
    fixes = {t["id"]: t["fixed"] for t in TASKS}
    broken = {t["id"]: t["broken"] for t in TASKS}
    return ScriptedDouble(competence, fixes, broken)


def _run(dsn, launcher, env, tmp_roots, tag, double, dev_ids, panel_ids,
         transfer_ids):
    return experiment.run_abcs(
        dsn, launcher=launcher, artifacts_root=tmp_roots["artifacts"],
        allocation_id=env["allocation_id"], investigation_id=env["investigation_id"],
        tasks=[BY_ID[i] for i in (dev_ids + panel_ids + transfer_ids)],
        dev_ids=dev_ids, panel_ids=panel_ids, transfer_ids=transfer_ids,
        lessons=None, double=double, grader_path=GRADER,
        protocol_prefix=tag, fixer_version="fixer-v1")


def test_answer_lookup_attack_fails_from_unavailability(tmp_path):
    tasks = BY_ID
    cases = tasks["panel-triangular"]["cases"]
    candidate = tmp_path / "oracle.py"
    candidate.write_text(
        "import runpy\n"
        "CASES = [c for t in runpy.run_path('experiments/fault_tasks.py')['TASKS']"
        " for c in t['cases']]\n"
        "def triangular(n):\n"
        "    return next(c['expected'] for c in CASES"
        " if c['fn'] == 'triangular' and c['args'] == [n])\n")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(cases))
    result = subprocess.run([sys.executable, str(ROOT / "experiments/run_tests.py"),
                             str(candidate), str(cases_path)], cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    assert data["passed"] == 0
    assert data["failed"] == data["total"] == len(cases)
    assert "fault_tasks" in json.dumps(data["failures"])


def test_grader_child_runs_outside_repository(tmp_path):
    candidate = tmp_path / "probe.py"
    candidate.write_text(
        "import os, sys\n"
        "def probe():\n"
        "    return {'cwd': os.getcwd(),\n"
        "            'pythonpath': 'PYTHONPATH' in os.environ,\n"
        "            'repo_on_path': any('experiments' in p or str(p).startswith('/home/ubuntu/AI/Agent-Society-v2') for p in sys.path)}\n")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([{"fn": "probe", "args": [],
                                       "expected": {"cwd": "repo"}}]))
    result = subprocess.run([sys.executable, str(ROOT / "experiments/run_tests.py"),
                             str(candidate), str(cases_path)], cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    assert data["failed"] == 1
    actual = data["failures"][0]["actual"]
    assert actual["cwd"] != str(ROOT)
    assert "grader-child" in actual["cwd"]
    assert actual["pythonpath"] is False
    assert actual["repo_on_path"] is False


def test_c_verdict_follows_c_model_text_not_method_output(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02c", authorized=500_000)
    competence = {("DEV", "dev-sum"): True}
    report = _run(dsn, launcher, env, tmp_roots, "r02c", _double(competence),
                  ["dev-sum"], ["panel-triangular"], [])
    frozen = report["development"]["methods"]["off_by_one"]
    assert report["development"]["acquisition"]["off_by_one"]["status"] == \
        "synthesized"
    assert len(report["invocations"]) == 1
    assert report["arms"]["C"]["panel-triangular"]["outcome"] == "failure"
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT detail FROM trial_results WHERE assignment_id = %s",
                        ("r02c-panel-C:candidate:panel-triangular",))
            detail = dict(cur.fetchone()[0])
            conn.commit()
    assert detail["method"] == frozen


def test_c_model_text_counts_without_retained_method(
        migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02n", authorized=500_000)
    competence = {("C", "panel-triangular"): True}
    report = _run(dsn, launcher, env, tmp_roots, "r02n", _double(competence),
                  ["dev-sum"], ["panel-triangular"], [])
    assert report["development"]["methods"] == {}
    assert report["development"]["acquisition"]["off_by_one"]["status"] == \
        "no-successful-transcript"
    assert any("no-applicable-method" in a
               for a in report.get("abstentions", []))
    assert report["arms"]["C"]["panel-triangular"]["outcome"] == "success"


def test_unrelated_registry_entry_ignored_for_frozen_artifact(
        migrated_db, tmp_roots, launcher):
    import hashlib

    dsn = migrated_db
    env = seed_env(dsn, "r02u", authorized=500_000)
    raw = (EXPERIMENTS / "offbyone_fixer.py").read_bytes()
    staging = tmp_roots["staging"] / "pre"
    staging.mkdir()
    manifest = {"files": [{"path": "offbyone_fixer.py", "kind": "file",
                           "digest": hashlib.sha256(raw).hexdigest(),
                           "size": len(raw)}],
                "entry": "offbyone_fixer.py", "verify_args": ["--selftest"]}
    receipt = artifacts.stage_package(dsn, staging, manifest=manifest,
                                      files={"offbyone_fixer.py": raw},
                                      access_label="public")
    artifacts.publish_package(dsn, Command(request_id="r02u-pre-pub"),
                              tmp_roots["artifacts"], receipt)
    capabilities.publish_candidate(
        dsn, Command(request_id="r02u-pre-cap"),
        tmp_roots["artifacts"], launcher, env["allocation_id"],
        version_id="fixer-v1", family="off_by_one",
        invocation={"entry": "offbyone_fixer.py"},
        effect={"sandbox": "local-process"}, resource={},
        artifact_digest=receipt["digest"], applicability={"family": "off_by_one"},
        reference_version="baseline-v0", change="unrelated pre-existing entry",
        hypothesis="should be ignored", protocol_id="r02u-pre",
        budget={"units": 500})
    before = capabilities.get_version(dsn, "fixer-v1")
    report = _run(dsn, launcher, env, tmp_roots, "r02u",
                  _double({("DEV", "dev-sum"): True,
                           ("C", "panel-triangular"): True}),
                  ["dev-sum"], ["panel-triangular"], [])
    frozen = report["development"]["methods"]["off_by_one"]
    acquisition = report["development"]["acquisition"]["off_by_one"]
    assert frozen != "fixer-v1"
    assert acquisition["version_id"] == frozen
    assert acquisition["artifact_digest"] != before["artifact_digest"]
    assert acquisition["provenance"] == "synthesized-from-dev-transcripts"
    assert capabilities.get_version(dsn, "fixer-v1")["artifact_digest"] == \
        before["artifact_digest"]
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT detail FROM trial_results WHERE assignment_id = %s",
                        ("r02u-panel-C:candidate:panel-triangular",))
            detail = dict(cur.fetchone()[0])
            conn.commit()
    assert detail["method"] == frozen


def test_grant_cap_binds_capped_suballocation(migrated_db):
    dsn = migrated_db
    env = seed_env(dsn, "r02g", authorized=100)
    child = _bind_grant_cap(dsn, env["allocation_id"], 7, "r02g")
    assert int(store.allocation_status(dsn, child)["authorized"]) == 7
    child2 = _bind_grant_cap(dsn, env["allocation_id"], 10_000, "r02g2")
    assert int(store.allocation_status(dsn, child2)["authorized"]) == 93
    env2 = seed_env(dsn, "r02h", authorized=100)
    child3 = _bind_grant_cap(dsn, env2["allocation_id"], 10_000, "r02h")
    assert int(store.allocation_status(dsn, child3)["authorized"]) == 100


def test_tiny_grant_cap_constrains_the_run(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "r02t", authorized=500_000)
    child = _bind_grant_cap(dsn, env["allocation_id"], 1, "r02t")
    env["allocation_id"] = child
    with pytest.raises(SettlementError):
        _run(dsn, launcher, env, tmp_roots, "r02t",
             _double({("DEV", "dev-sum"): True}),
             ["dev-sum"], ["panel-triangular"], [])


def test_launcher_selection_refusals():
    with pytest.raises(SettlementError, match="allow-uncontained"):
        _select_launcher(SimpleNamespace(launcher="local",
                                         allow_uncontained=False,
                                         runsc_image=""))
    with pytest.raises(SettlementError, match="runsc-image"):
        _select_launcher(SimpleNamespace(launcher="runsc",
                                         allow_uncontained=False,
                                         runsc_image=""))
    with pytest.raises(SettlementError, match="containment unavailable"):
        _select_launcher(SimpleNamespace(launcher="runsc",
                                         allow_uncontained=False,
                                         runsc_image="sha256:" + "0" * 64))
    fallback = _select_launcher(SimpleNamespace(launcher="runsc",
                                                allow_uncontained=True,
                                                runsc_image="sha256:" + "0" * 64))
    assert fallback.profile == "local-process"


def test_deterministic_run_reports_acquisition_and_estimates(
        migrated_db, tmp_roots):
    dsn = migrated_db
    env = seed_env(dsn, "r02d", authorized=500_000)
    root = EXPERIMENTS.parent
    proc = subprocess.run(
        [sys.executable, "experiments/run_live_abc.py", "--dsn", dsn,
         "--allocation", env["allocation_id"], "--artifacts-root",
         str(tmp_roots["artifacts"]), "--investigation",
         env["investigation_id"], "--protocol-prefix", "r02d",
         "--dev", "dev-sum", "--panel", "panel-triangular",
         "--transfer", "transfer-sign", "--deterministic"],
        cwd=root, capture_output=True, text=True, timeout=300, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["simulated"] is True
    assert payload["launcher"] == "local-process"
    assert payload["development"]["acquisition"]["off_by_one"]["status"] == \
        "synthesized"
    assert payload["development"]["acquisition"]["off_by_one"]["version_id"] == \
        payload["development"]["methods"]["off_by_one"]
    for arm, budget in payload["budgets"].items():
        assert "token_estimates_never_a_monetary_ceiling" in budget
        assert budget["token_estimates_never_a_monetary_ceiling"]["basis"] == \
            "token-length estimate; not a monetary ceiling"
