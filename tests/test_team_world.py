from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

from experiments.team01 import barrier, freeze, oracle, register
from settlement import broker, evaluation, launcher_local, store, trials
from settlement.common import Command
from settlement.launcher_local import LocalLauncher

TEAM01 = Path(__file__).resolve().parent.parent / "experiments" / "team01"


def _cmd(payload: dict, tag: str) -> Command:
    import uuid
    return Command(request_id=f"team01-{tag}-{uuid.uuid4().hex[:8]}", payload=payload)


def test_corpus_census():
    assert set(oracle.FAMILIES) == {"fam-ind", "fam-cpl", "fam-seq", "fam-sng"}
    assert len(oracle.SPLITS["development"]) == 4
    assert len(oracle.SPLITS["evaluation"]) == 8
    assert len(oracle.SPLITS["transfer"]) == 4
    all_tasks = (oracle.SPLITS["development"] + oracle.SPLITS["evaluation"]
                 + oracle.SPLITS["transfer"])
    assert len(set(all_tasks)) == 16
    fams = {oracle.TASK_FAMILY[t] for t in all_tasks}
    assert fams == set(oracle.FAMILIES)
    for task_id in all_tasks:
        task = TEAM01 / "tasks" / task_id
        assert (task / "spec.md").is_file(), task_id
        assert (task / "public.json").is_file(), task_id
        src = task / "src"
        assert (src / "app.py").is_file(), task_id
        modules = sorted(p.name for p in src.glob("*.py") if p.name != "app.py")
        assert len(modules) >= 2, (task_id, modules)
        public = json.loads((task / "public.json").read_text())
        assert len(public) >= 3, task_id
        protected = json.loads((TEAM01 / "protected" / f"{task_id}.json").read_text())
        assert len(protected) >= 4, task_id
        pub_inputs = {json.dumps(c["input"], sort_keys=True) for c in public}
        pro_inputs = {json.dumps(c["input"], sort_keys=True) for c in protected}
        assert not (pub_inputs & pro_inputs), task_id


def test_participant_inputs_clean():
    problems = barrier.audit_barrier()
    assert problems == []


def test_participant_inputs_audit_detects_leak(tmp_path):
    target = tmp_path / "team01"
    shutil.copytree(TEAM01, target)
    leaked = json.loads((target / "protected" / "team01-t01.json").read_text())
    task_pub = json.loads((target / "tasks" / "team01-t01" / "public.json").read_text())
    task_pub.append(leaked[0])
    (target / "tasks" / "team01-t01" / "public.json").write_text(json.dumps(task_pub))
    problems = barrier.audit_barrier(target)
    assert problems != []


def test_oracle_agrees_with_frozen_expectations():
    checked = 0
    for split in ("development", "evaluation", "transfer"):
        for task_id in oracle.SPLITS[split]:
            fam = oracle.TASK_FAMILY[task_id]
            spec = oracle.load_spec(task_id)
            for case in oracle.public_cases(task_id) + oracle.protected_cases(task_id):
                got = oracle.reference(fam, spec, copy.deepcopy(case["input"]))
                assert got == case["expected"], (task_id, case["input"])
                checked += 1
    assert checked >= 16 * 7


def test_broken_trees_fail_public():
    failing = 0
    for split in ("development", "evaluation", "transfer"):
        for task_id in oracle.SPLITS[split]:
            report = oracle.evaluate_tree(TEAM01 / "tasks" / task_id / "src",
                                          oracle.public_cases(task_id))
            assert report["passed"] < report["total"], task_id
            failing += 1
    assert failing == 16


def test_oracle_selftest_per_family():
    results = oracle.selftest()
    assert set(results) == set(oracle.FAMILIES)
    for fam, outcome in results.items():
        assert outcome["valid"]["failed"] == 0, fam
        assert outcome["valid"]["passed"] > 0, fam
        assert outcome["invalid"]["failed"] > 0, fam


def test_manifest_frozen():
    manifest_raw = (TEAM01 / "manifest.json").read_bytes()
    pinned = (TEAM01 / "manifest.sha256").read_text().strip()
    import hashlib
    assert hashlib.sha256(manifest_raw).hexdigest() == pinned
    assert freeze.verify_committed() == []
    manifest = json.loads(manifest_raw)
    assert manifest["splits"] == oracle.SPLITS
    assert manifest["evaluator"]["id"] == register.EVALUATOR_ID
    assert manifest["evaluator"]["version"] == register.EVALUATOR_VERSION
    assert manifest["evaluator"]["code_digest"] == register.oracle_digest()
    assert len(manifest["files"]) >= 16 * 4


def test_register_freeze_and_hidden_answers(migrated_db):
    from settlement.common import Unauthorized

    dsn = migrated_db
    foundation = register.ensure_foundation(dsn)
    assert foundation["problems"] == []
    got = evaluation.hidden_answer(dsn, "team01-t01", "evaluator")
    assert got["task_id"] == "team01-t01"
    assert len(got["cases"]) >= 4
    with pytest.raises(Unauthorized):
        evaluation.hidden_answer(dsn, "team01-t01", "candidate")
    leaked = [c for c in evaluation.candidate_view(dsn) if "team01-t" in str(c)]
    assert leaked == []
    for protocol_id in (register.PROTOCOL_DEV, register.PROTOCOL_EVAL):
        protocol = trials._protocol(dsn, protocol_id)
        assert protocol["frozen"]
        kinds = {g.get("kind") for g in protocol["task_groups"]}
        assert "protected-eval" in kinds
        assert protocol["evaluator_version"] == register.EVALUATOR_VERSION


def test_candidate_runs_in_isolated_profile(migrated_db, tmp_path):
    dsn = migrated_db
    register.ensure_foundation(dsn)
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "team01",
                                "authority_grant": {}, "envelopes": {}}, "g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": "team01-a", "domain": "cpu",
                                     "authorized": 100_000}, "a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": "team01-i",
                                      "objective": "team01"}, "i"))
    staged = oracle.prepare_tree("team01-t01", "valid", tmp_path / "cand")
    case = oracle.public_cases("team01-t01")[0]
    req = tmp_path / "req.json"
    resp = tmp_path / "resp.json"
    req.write_text(json.dumps(case["input"]))
    broker.ensure_operation(
        dsn, operation_id="team01-op", effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process",
                 "argv": [sys.executable, str(staged / "app.py"),
                          str(req), str(resp)],
                 "timeout_ms": 30_000, "max_output_bytes": 65_536},
        allocation_id="team01-a")
    launcher = LocalLauncher(tmp_path / "runs")
    status = broker.dispatch_operation(dsn, "team01-op",
                                       launchers={"local-process": launcher})
    assert status.dispatch_state == "observed"
    assert json.loads(resp.read_text()) == case["expected"]
