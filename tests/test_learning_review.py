import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "experiments"))

from fastapi.testclient import TestClient

from settlement import api, broker, capabilities, evidence, run, steward, store, trials
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_local import LocalLauncher

from test_s3_helpers import EXPERIMENTS, acquire, publish_method, seed_env, stage_method


def _cmd(payload=None, tag=None):
    return Command(request_id=f"{tag or 'lreq'}_{uuid.uuid4().hex[:10]}", payload=payload or {})


def _launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _publish(dsn, tag, launcher, env, tmp_roots, version_id="lcap-v1"):
    receipt = stage_method(dsn, tmp_roots["staging"], EXPERIMENTS / "offbyone_fixer.py",
                           "offbyone_fixer.py")
    publish_method(dsn, tag, tmp_roots["artifacts"], receipt)
    return capabilities.publish_candidate(
        dsn, _cmd(tag=f"{tag}-pubcap"), tmp_roots["artifacts"], launcher,
        env["allocation_id"], version_id=version_id, family="off_by_one",
        invocation={"entry": "offbyone_fixer.py"}, effect={"sandbox": "local-process"},
        resource={"cpu_seconds": 30}, artifact_digest=receipt["digest"],
        applicability={"family": "off_by_one"}, reference_version="lcap-v0",
        change="fix", hypothesis="h", scope={"family": "off_by_one"},
        dependencies=[], protocol_id=f"{tag}-p", budget={"units": 50})


def test_steward_quarantine_blocks_pinned_dispatch(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    launcher = _launcher(tmp_path)
    env = seed_env(dsn, "lq")
    acquire(dsn, "lq", "lq-att", env)
    _publish(dsn, "lq", launcher, env, tmp_roots)
    capabilities.pin_capability(dsn, "lq-att", "lcap-v1")
    out = steward.quarantine_subject(
        dsn, _cmd({"version_id": "lcap-v1", "reason": "suspect"}, tag="lq-q"))
    assert out.code == ResultCode.APPLIED
    comp = run.Composition(
        revision=1, root={"kind": "sequence", "node_id": "root", "steps": []},
        allocation_id=env["allocation_id"], authority_version=1,
        budget={"rounds": 1, "model_invocations": 0, "sandbox_seconds": 10})
    eligibility = run.check_eligibility(dsn, "lq-att", comp)
    assert eligibility["eligible"] is False
    assert any("lcap-v1" in reason for reason in eligibility["reasons"])
    client = TestClient(api.create_app(dsn, gateway=None, token="t"))
    body = client.post("/commands/quarantine", data={"subject": "lcap-v1", "reason": "ui"},
                       headers={"x-operator-token": "t"}).text
    assert "accepted" in body


def test_steward_release_wrapper_releases(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    launcher = _launcher(tmp_path)
    env = seed_env(dsn, "lr")
    acquire(dsn, "lr", "lr-att", env)
    _publish(dsn, "lr", launcher, env, tmp_roots)
    trials.freeze_protocol(
        dsn, _cmd(tag="lr-frz"), protocol_id="lr-p", candidate_version="lcap-v1",
        reference_version="lcap-v0", evaluator_version="v9",
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions={}, uncertainty={})
    out = steward.release_subject(dsn, _cmd({
        "release_id": "lr-rel", "protocol_id": "lr-p", "versions": ["lcap-v1"],
        "scope": {"family": "off_by_one"}, "disposition": "experimental",
        "fallback": "lcap-v0", "evaluator_version": "v9"}, tag="lr-rel"))
    assert out.code == ResultCode.APPLIED
    assert capabilities.releases_for_scope(dsn, "off_by_one")[0]["id"] == "lr-rel"


def test_release_wrapper_rejects_missing_keys(migrated_db):
    out = steward.release_subject(migrated_db, _cmd({"release_id": "x"}, tag="lr-bad"))
    assert out.code == ResultCode.INVALID_INPUT


def test_regression_refuses_limited_release(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    launcher = _launcher(tmp_path)
    env = seed_env(dsn, "lreg")
    acquire(dsn, "lreg", "lreg-att", env)
    _publish(dsn, "lreg", launcher, env, tmp_roots)
    trials.freeze_protocol(
        dsn, _cmd(tag="lreg-frz"), protocol_id="lreg-p", candidate_version="lcap-v1",
        reference_version="lcap-v0", evaluator_version="v9",
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions={}, uncertainty={})
    trials.assign(dsn, _cmd(tag="lreg-a1"), "lreg-p", "t1", "panel", "candidate")
    trials.assign(dsn, _cmd(tag="lreg-a2"), "lreg-p", "t1", "panel", "reference")
    trials.record_result(dsn, _cmd(tag="lreg-r1"), assignment_id="lreg-p:candidate:t1",
                         outcome="failure")
    trials.record_result(dsn, _cmd(tag="lreg-r2"), assignment_id="lreg-p:reference:t1",
                         outcome="success")
    assert trials.verdict(dsn, "lreg-p")["label"] == "regression"
    with pytest.raises(SettlementError):
        capabilities.scoped_release(
            dsn, _cmd(tag="lreg-rel"), release_id="lreg-rel", protocol_id="lreg-p",
            versions=["lcap-v1"], scope={"family": "off_by_one"}, disposition="limited",
            fallback="lcap-v0", evaluator_version="v9")
    assert capabilities.releases_for_scope(dsn, "off_by_one") == []


def test_retraction_blocks_evidence_bound_release(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    launcher = _launcher(tmp_path)
    env = seed_env(dsn, "lev")
    acquire(dsn, "lev", "lev-att", env)
    _publish(dsn, "lev", launcher, env, tmp_roots)
    obs = evidence.register_observation(
        dsn, _cmd(tag="lev-obs"), "lev-att", {"note": "panel reviewed"},
        source_identity="evaluator-1")
    evidence.propose_claim(dsn, _cmd(tag="lev-cl"), "lev-claim", {"text": "gain"}, scope={})
    evidence.admit_warrant(dsn, _cmd(tag="lev-w"), "lev-w", "lev-claim", "panel-review",
                           "v1", [[(obs.data["receipt_id"], "observation")]], scope={})
    trials.freeze_protocol(
        dsn, _cmd(tag="lev-frz"), protocol_id="lev-p", candidate_version="lcap-v1",
        reference_version="lcap-v0", evaluator_version="v9",
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions={}, uncertainty={})
    first = capabilities.scoped_release(
        dsn, _cmd(tag="lev-rel1"), release_id="lev-rel1", protocol_id="lev-p",
        versions=["lcap-v1"], scope={"family": "off_by_one"}, disposition="experimental",
        fallback="lcap-v0", evaluator_version="v9", evidence_refs=["lev-claim"])
    assert first.code == ResultCode.APPLIED
    evidence.retract(dsn, _cmd(tag="lev-ret"), obs.data["receipt_id"], "bad source")
    second = capabilities.scoped_release(
        dsn, _cmd(tag="lev-rel2"), release_id="lev-rel2", protocol_id="lev-p",
        versions=["lcap-v1"], scope={"family": "off_by_one"}, disposition="experimental",
        fallback="lcap-v0", evaluator_version="v9", evidence_refs=["lev-claim"])
    assert second.code == ResultCode.MISSING_EVIDENCE


def test_learning_views_render_real_rows(migrated_db, tmp_roots, tmp_path):
    dsn = migrated_db
    launcher = _launcher(tmp_path)
    env = seed_env(dsn, "lv")
    acquire(dsn, "lv", "lv-att", env)
    _publish(dsn, "lv", launcher, env, tmp_roots)
    trials.freeze_protocol(
        dsn, _cmd(tag="lv-frz"), protocol_id="lv-p", candidate_version="lcap-v1",
        reference_version="lcap-v0", evaluator_version="v9",
        task_groups=[{"name": "development", "kind": "development"},
                     {"name": "panel", "kind": "protected-eval"}],
        budgets={}, metrics=["success_rate"], stopping={}, exclusions={}, uncertainty={})
    trials.assign(dsn, _cmd(tag="lv-a1"), "lv-p", "t1", "panel", "candidate")
    trials.record_result(dsn, _cmd(tag="lv-r1"), assignment_id="lv-p:candidate:t1",
                         outcome="success")
    client = TestClient(api.create_app(dsn, gateway=None, token="t"))
    headers = {"x-operator-token": "t"}
    trials_page = client.get("/trials", headers=headers)
    assert trials_page.status_code == 200
    assert "lv-p" in trials_page.text
    assert "learning slice pending" not in trials_page.text
    learning_page = client.get("/learning", headers=headers)
    assert learning_page.status_code == 200


def test_live_entry_refuses_without_inputs(monkeypatch, capsys):
    import run_live_abc

    monkeypatch.delenv("SETTLEMENT_GATEWAY_ENDPOINT", raising=False)
    monkeypatch.delenv("SETTLEMENT_GATEWAY_URL", raising=False)
    monkeypatch.delenv("SETTLEMENT_GATEWAY_KEY", raising=False)
    monkeypatch.delenv("SETTLEMENT_GRANT_UNITS", raising=False)
    monkeypatch.setattr("sys.argv", ["run_live_abc.py", "--dsn", "x", "--allocation", "y",
                                     "--artifacts-root", "z"])
    assert run_live_abc.main() == 2
    assert "SETTLEMENT_GATEWAY_ENDPOINT" in capsys.readouterr().out
