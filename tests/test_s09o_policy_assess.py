import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DB = "s09o_assess"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"


def _source(kind="construct_method", queries=16):
    return (
        "def STEP(view, state):\n"
        "    task = view['task_content']\n"
        "    if state.get('done'):\n"
        "        action = {'kind': 'stop', 'target': task['task_id'],\n"
        "                  'inputs': {'reason': 'finished'},\n"
        "                  'evidence_refs': [], 'requested_resources': {}}\n"
        "        return {'action': action, 'state': state}\n"
        "    action = {'kind': %r, 'target': task['task_id'],\n"
        "              'inputs': {'max_queries': %d},\n"
        "              'evidence_refs': [],\n"
        "              'requested_resources': {'queries': %d}}\n"
        "    return {'action': action, 'state': {'done': True}}\n"
    ) % (kind, queries, queries)


@pytest.fixture(scope="module")
def store():
    assert DB == "s09o_assess"
    subprocess.run(["createdb", "-h", "/var/run/postgresql", "-U", "ubuntu", DB],
                   check=True, capture_output=True, text=True, timeout=60)
    try:
        from settlement import db
        db.apply_migrations(DSN, MIGRATIONS)
        yield DSN
    finally:
        subprocess.run(["dropdb", "-h", "/var/run/postgresql", "-U", "ubuntu", DB],
                       check=True, capture_output=True, text=True, timeout=60)


def _artifact(source):
    from experiments.ad01 import policy_step
    return policy_step.make_policy_artifact(source, origin="authored-control")


def _setup(store, tag, candidate, incumbent, rule=None):
    from experiments.ad01 import policy_assess
    panel = policy_assess.panel_for(scope={"family": "software"}, world=0,
                                   seed="worker-a-%s" % tag, size=2)
    rule = rule or policy_assess.rule_for()
    proposal_id = "s09o-proposal-%s" % tag
    policy_assess.freeze_protocol(store, proposal_id=proposal_id,
                                  panel=panel, rule=rule)
    candidate_artifact = _artifact(candidate)
    incumbent_artifact = _artifact(incumbent)
    return policy_assess.assess_policy(
        store, proposal_id=proposal_id,
        candidate_source=candidate,
        candidate_digest=hashlib.sha256(candidate.encode()).hexdigest(),
        candidate_artifact=candidate_artifact,
        incumbent_source=incumbent,
        incumbent_digest=hashlib.sha256(incumbent.encode()).hexdigest(),
        incumbent_artifact=incumbent_artifact,
        panel=panel, rule=rule, scope={"family": "software"},
        protocol_id=policy_assess.PANEL_PROTOCOL)


def test_better_candidate_binds_with_arm_evidence(store):
    from experiments.ad01 import policy_assess
    record = _setup(store, "bind", _source(), _source("diagnose", 1),
                    rule=policy_assess.rule_for(resource_ceiling=100))
    assert record["outcome"] == "bind"
    assert record["attempt_id"].startswith("s09-assess-")
    assert record["protocol_id"] == policy_assess.PANEL_PROTOCOL
    for arm in ("candidate", "incumbent"):
        assert len(record["arms"][arm]["decisions"]) >= 1
        assert len(record["arms"][arm]["effects"]) >= 1
        assert record["arms"][arm]["quality"]["tasks"] == 2
        assert record["arms"][arm]["resources"]["step_calls"] >= 1
        assert isinstance(record["arms"][arm]["resources"]["child_wall_ms"], int)
    assert record["arms"]["candidate"]["quality"]["reduced"] > record["arms"]["incumbent"]["quality"]["reduced"]


def test_invalid_candidate_is_unavailable_without_candidate_execution(store):
    from experiments.ad01 import policy_assess
    record = _setup(store, "unavailable", "not STEP source", _source("diagnose", 1))
    assert record["outcome"] == "unavailable"
    assert record["arms"]["candidate"]["resources"]["step_calls"] == 0
    assert record["arms"]["candidate"]["decisions"] == []
    assert "source" in record["reason"] or "entry" in record["reason"]


def test_exact_quality_tie_rejects(store):
    source = _source()
    record = _setup(store, "tie", source, source)
    assert record["outcome"] == "reject"
    assert "margin" in record["reason"] or "tie" in record["reason"]
    assert record["arms"]["candidate"]["quality"] == record["arms"]["incumbent"]["quality"]


def test_resource_overrun_rejects_even_with_quality_gain(store):
    from experiments.ad01 import policy_assess
    rule = policy_assess.rule_for(resource_ceiling=0)
    record = _setup(store, "resource", _source("construct_method", 16),
                    _source("construct_method", 1), rule=rule)
    assert record["outcome"] == "reject"
    assert "resource overrun" in record["reason"]
    cand = record["arms"]["candidate"]["resources"]
    inc = record["arms"]["incumbent"]["resources"]
    assert cand["queries"] + cand["model_calls"] > inc["queries"] + inc["model_calls"]


def test_exposure_requires_frozen_protocol(store):
    from experiments.ad01 import policy_assess
    panel = policy_assess.panel_for(scope={"family": "software"}, world=0,
                                   seed="worker-a-before-freeze", size=2)
    rule = policy_assess.rule_for()
    source = _source()
    with pytest.raises(ValueError, match="protocol"):
        policy_assess.assess_policy(
            store, proposal_id="s09o-never-frozen", candidate_source=source,
            candidate_digest=hashlib.sha256(source.encode()).hexdigest(),
            candidate_artifact=_artifact(source), incumbent_source=source,
            incumbent_digest=hashlib.sha256(source.encode()).hexdigest(),
            incumbent_artifact=_artifact(source), panel=panel, rule=rule,
            scope={"family": "software"}, protocol_id=policy_assess.PANEL_PROTOCOL)


def test_refreezing_different_panel_or_rule_fails(store):
    from experiments.ad01 import policy_assess
    first = policy_assess.panel_for(scope={"family": "software"}, world=0,
                                   seed="worker-a-refreeze-a", size=2)
    second = policy_assess.panel_for(scope={"family": "software"}, world=0,
                                    seed="worker-a-refreeze-b", size=2)
    rule = policy_assess.rule_for()
    proposal_id = "s09o-refreeze"
    policy_assess.freeze_protocol(store, proposal_id=proposal_id,
                                  panel=first, rule=rule)
    with pytest.raises(ValueError):
        policy_assess.freeze_protocol(store, proposal_id=proposal_id,
                                      panel=second, rule=rule)
    with pytest.raises(ValueError):
        policy_assess.freeze_protocol(store, proposal_id=proposal_id,
                                      panel=first,
                                      rule=policy_assess.rule_for(margin=2))


def test_record_does_not_contain_panel_solution_bytes(store):
    from experiments.ad01 import policy_assess, worlds
    panel = policy_assess.panel_for(scope={"family": "software"}, world=0,
                                   seed="worker-a-secret", size=2)
    secret = json.dumps(worlds.load_task(worlds.FROZEN_DIR, panel["task_ids"][0])["witness"],
                        sort_keys=True)
    record = _setup(store, "no-leak", _source(), _source("diagnose", 1))
    assert secret not in json.dumps(record, sort_keys=True)


def test_identical_assessment_is_idempotent(store):
    from experiments.ad01 import policy_assess
    candidate = _source()
    incumbent = _source("diagnose", 1)
    panel = policy_assess.panel_for(scope={"family": "software"}, world=0,
                                   seed="worker-a-idempotent", size=2)
    rule = policy_assess.rule_for()
    proposal_id = "s09o-idempotent"
    policy_assess.freeze_protocol(store, proposal_id=proposal_id,
                                  panel=panel, rule=rule)
    kwargs = dict(
        proposal_id=proposal_id, candidate_source=candidate,
        candidate_digest=hashlib.sha256(candidate.encode()).hexdigest(),
        candidate_artifact=_artifact(candidate), incumbent_source=incumbent,
        incumbent_digest=hashlib.sha256(incumbent.encode()).hexdigest(),
        incumbent_artifact=_artifact(incumbent), panel=panel, rule=rule,
        scope={"family": "software"}, protocol_id=policy_assess.PANEL_PROTOCOL)
    first = policy_assess.assess_policy(store, **kwargs)
    second = policy_assess.assess_policy(store, **kwargs)
    assert second == first
    assert second["attempt_id"] == first["attempt_id"]
