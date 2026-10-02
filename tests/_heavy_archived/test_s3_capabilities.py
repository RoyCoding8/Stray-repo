from __future__ import annotations

import sys

import pytest

from settlement import broker, capabilities, evidence, run, store, trials
from settlement.common import Command, SettlementError
from settlement.launcher_local import LocalLauncher

from test_s3_helpers import EXPERIMENTS, acquire, bind_assignment, publish_method, seed_env, stage_method


@pytest.fixture()
def launcher(tmp_path):
    return LocalLauncher(tmp_path / "runs")


def _mini_protocol(dsn, tag, cand="cap-v1", ref="cap-v0", evaluator="s3-eval",
                   group="panel"):
    trials.freeze_protocol(dsn, Command(request_id=f"{tag}-frz"), protocol_id=f"{tag}-p",
                           candidate_version=cand, reference_version=ref,
                           evaluator_version="v1",
                           task_groups=[{"name": "development", "kind": "development"},
                                        {"name": group, "kind": "protected-eval"}],
                           budgets={"amortization_horizon": {"tasks": 50}},
                           metrics=["success_rate"], stopping={}, exclusions=[],
                           uncertainty={})
    return f"{tag}-p"


def _observed_op(dsn, launcher, env, tag, argv=None, assignment_id=None):
    op = f"{tag}-op"
    broker.ensure_operation(dsn, operation_id=op, effect=broker.SANDBOX_EXEC,
                            payload={"profile": "local-process",
                                     "argv": argv or ["true"],
                                     "timeout_ms": 30_000,
                                     "max_output_bytes": 1024},
                            allocation_id=env["allocation_id"])
    if assignment_id is not None:
        bind_assignment(dsn, tag, assignment_id, op)
    broker.dispatch_operation(dsn, op, launchers={"local-process": launcher})
    return op


def _supported_claim(dsn, tag):
    evidence.register_observation(dsn, Command(request_id=f"{tag}-obs",
                                               payload={}), f"{tag}-att",
                                  {"note": "trial ledger reviewed"},
                                  source_identity="evaluator-1")
    evidence.propose_claim(dsn, Command(request_id=f"{tag}-claim",
                                        payload={}), f"{tag}-claim",
                           {"text": "panel gain observed"}, scope={})
    evidence.admit_warrant(dsn, Command(request_id=f"{tag}-war", payload={}),
                           f"{tag}-war", f"{tag}-claim", "s3-panel-review", "v1",
                           [[(f"obs_{tag}-obs", "observation")]], scope={})
    return f"{tag}-claim"


def _publish_fixer(dsn, launcher, env, tmp_roots, tag, version_id="cap-v1"):
    receipt = stage_method(dsn, tmp_roots["staging"],
                           EXPERIMENTS / "offbyone_fixer.py", "offbyone_fixer.py")
    publish_method(dsn, tag, tmp_roots["artifacts"], receipt)
    return capabilities.publish_candidate(
        dsn, Command(request_id=f"{tag}-pubcap"), tmp_roots["artifacts"], launcher,
        env["allocation_id"], version_id=version_id, family="off_by_one",
        invocation={"entry": "offbyone_fixer.py"},
        effect={"sandbox": "local-process"}, resource={"cpu_seconds": 30},
        artifact_digest=receipt["digest"],
        applicability={"family": "off_by_one"}, reference_version="cap-v0",
        change="bound-inclusion rewrites", hypothesis="off-by-one faults fixed",
        scope={"family": "off_by_one"}, dependencies=["run/v1"],
        protocol_id=f"{tag}-p", budget={"units": 500})


def test_publish_candidate_executes_artifact(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "s3pub")
    result = _publish_fixer(dsn, launcher, env, tmp_roots, "s3pub")
    assert result.code.value == "applied"
    op = broker.read_operation(dsn, result.data["verification_op"])
    assert op["dispatch_state"] == "observed"
    assert "offbyone_fixer" not in sys.modules
    assert "candidate" not in sys.modules
    row = capabilities.get_version(dsn, "cap-v1")
    assert row["reference_version"] == "cap-v0"
    assert row["change_desc"] == "bound-inclusion rewrites"
    assert row["hypothesis"] == "off-by-one faults fixed"
    assert dict(row["scope"]) == {"family": "off_by_one"}
    assert list(row["dependencies"]) == ["run/v1"]
    assert row["protocol_id"] == "s3pub-p"
    assert dict(row["budget"]) == {"units": 500}
    assert row["verification_op"] == result.data["verification_op"]


def test_scoped_release_preserves_outside_scope(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "s3rel")
    acquire(dsn, "s3rel", "s3rel-att", env)
    _publish_fixer(dsn, launcher, env, tmp_roots, "s3rel", "cap-v1")
    pid = _mini_protocol(dsn, "s3rel")
    from settlement import evaluation
    evaluation.register_evaluator(dsn, Command(request_id="s3rel-eval"),
                                  "s3-eval", "v1")
    trials.assign(dsn, Command(request_id="s3rel-a1", payload={}), pid,
                  "t1", "panel", "candidate", {})
    trials.assign(dsn, Command(request_id="s3rel-a2", payload={}), pid,
                  "t1", "panel", "reference", {})
    op_ok = _observed_op(dsn, launcher, env, "s3rel-ok",
                         assignment_id=f"{pid}:candidate:t1")
    op_bad = _observed_op(dsn, launcher, env, "s3rel-bad", ["false"],
                          assignment_id=f"{pid}:reference:t1")
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id="s3rel-r1", payload={}), receipt_id="s3rel-r1",
        assignment_id=f"{pid}:candidate:t1", evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref=op_ok,
        result={"outcome": "success", "detail": {"task_id": "t1"}})
    evaluation.submit_evaluator_receipt(
        dsn, Command(request_id="s3rel-r2", payload={}), receipt_id="s3rel-r2",
        assignment_id=f"{pid}:reference:t1", evaluator_id="s3-eval",
        evaluator_version="v1", invocation_ref=op_bad,
        result={"outcome": "failure", "detail": {"task_id": "t1"}})
    claim = _supported_claim(dsn, "s3rel")
    assert trials.verdict(dsn, pid)["label"] == "observed-gain"
    capabilities.scoped_release(
        dsn, Command(request_id="s3rel-rel1", payload={}), release_id="rel-1",
        protocol_id=pid, versions=["cap-v1"], scope={"family": "off_by_one"},
        disposition="limited", fallback="cap-v0", policy_version="sel-v1",
        invalidation={"on": "regression"}, evidence_refs=[claim],
        evaluator_version="v1")
    capabilities.scoped_release(
        dsn, Command(request_id="s3rel-rel2", payload={}), release_id="rel-2",
        protocol_id=pid, versions=["cap-v1"], scope={"family": "other"},
        disposition="experimental", fallback="cap-v0", policy_version="sel-v1",
        invalidation={}, evidence_refs=[claim], evaluator_version="v1")
    scoped = capabilities.releases_for_scope(dsn, "off_by_one")
    assert [r["id"] for r in scoped] == ["rel-1"]
    assert {r["id"] for r in capabilities.releases_for_scope(dsn, "")} == \
        {"rel-1", "rel-2"}


def test_quarantine_blocks_pinned_and_release(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "s3q")
    acquire(dsn, "s3q", "s3q-att", env)
    _publish_fixer(dsn, launcher, env, tmp_roots, "s3q", "cap-q1")
    capabilities.pin_capability(dsn, "s3q-att", "cap-q1")
    from settlement.run import Composition, SuspendNode
    comp = Composition(revision=1, root=SuspendNode(node_id="s",
                                                   pending_observation="o"),
                       authority_version=1)
    assert run.check_eligibility(dsn, "s3q-att", comp)["eligible"]
    capabilities.quarantine(dsn, Command(request_id="s3q-q", payload={}),
                            "cap-q1", "panel regression")
    assert capabilities.quarantine_status(dsn, "cap-q1")["reason"] == "panel regression"
    decision = run.check_eligibility(dsn, "s3q-att", comp)
    assert not decision["eligible"]
    assert any("quarantined capability cap-q1" in r for r in decision["reasons"])
    pid = _mini_protocol(dsn, "s3qr")
    with pytest.raises(SettlementError):
        capabilities.scoped_release(
            dsn, Command(request_id="s3q-rel", payload={}), release_id="rel-q",
            protocol_id=pid, versions=["cap-q1"], scope={"family": "off_by_one"},
            disposition="limited", fallback="cap-v0", policy_version="sel-v1",
            invalidation={}, evidence_refs=[], evaluator_version="v1")


def test_consolidation_retains_history(migrated_db, tmp_roots, launcher):
    dsn = migrated_db
    env = seed_env(dsn, "s3c")
    _publish_fixer(dsn, launcher, env, tmp_roots, "s3c", "cap-c1")
    capabilities.propose_consolidation(
        dsn, Command(request_id="s3c-con", payload={}), proposal_id="con-1",
        subject_versions=["cap-c1"], action="retire",
        costs={"migration": 40}, affected=["rel-1"], rationale="superseded")
    assert capabilities.get_version(dsn, "cap-c1")["artifact_digest"] != ""
    with pytest.raises(SettlementError):
        capabilities.propose_consolidation(
            dsn, Command(request_id="s3c-bad", payload={}), proposal_id="con-2",
            subject_versions=[], action="retire")
