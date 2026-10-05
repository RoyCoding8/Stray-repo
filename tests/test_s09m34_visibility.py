"""S09-M34 red-first: sealed visibility plus binding staleness.

Desired invariants (currently violated, tests must stay red until fixed):
- hidden-answer perturbation leaves the provider-bound request unchanged.
- sealed observations never enter constructor packets or prompts.
- protected references are refused in visible context.
- stale concurrent bind cannot replace a newer binding; selection follows
  the active eligible binding, never first family match.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

from experiments.ad01.s09_run_isolation import DB_PREFIX, \
    create_disposable_db, disposable_db, drop_disposable_db

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
LOCAL_HOST = "/var/run/postgresql"
LOCAL_DSN = "dbname=postgres host=%s user=ubuntu" % LOCAL_HOST

RUN_TOKEN = "m34vis%s" % uuid.uuid4().hex[:10]

DEV_TASK = "ad01-w0-dev-sw-00"
USE_TASK = "ad01-w0-within-sw-00"
PROTOCOL = "s09-revision-v1"
EVALUATOR = "ad01-method-exec-v1"

GOOD_SOURCE = (
    "def m34v_good_entry(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
GOOD_ENTRY = "m34v_good_entry"


def _dbname(dsn: str) -> str:
    return dict(field.split("=", 1) for field in dsn.split()
                if "=" in field).get("dbname", "").strip("'\"")


def _admin_dsn() -> str:
    """The DSN names the instance to create on, never a store to empty."""
    return os.environ.get("SETTLEMENT_TEST_DSN") or LOCAL_DSN


@pytest.fixture(scope="module")
def store():
    admin = _admin_dsn()
    assert "live" not in _dbname(admin)
    database = create_disposable_db(RUN_TOKEN, admin_dsn=admin,
                                    migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database, admin_dsn=admin)


def test_the_store_is_named_for_this_run_not_for_the_file(store):
    """Two concurrent runs of this module must not share a store.

    Sealed visibility is asserted over persisted rows. The fixture used to
    create and drop one fixed name, so a sibling's teardown destroyed this
    run's store mid-module and the failures read as product defects rather
    than as the collision they are. Only the per-run suffix keeps the two
    disjoint, so that is what this pins.
    """
    mine = _dbname(store)

    assert mine.startswith(DB_PREFIX + "_" + RUN_TOKEN), mine

    with disposable_db(RUN_TOKEN, admin_dsn=_admin_dsn()) as fresh:
        assert fresh.name != mine
        assert fresh.name.startswith(DB_PREFIX + "_" + RUN_TOKEN)
        assert re.fullmatch(r"[0-9a-f]{12}", fresh.name.rsplit("_", 1)[1])
    assert mine != _dbname(LOCAL_DSN), mine


def _task():
    from experiments.ad01 import worlds
    return worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")


def _authorize(dsn, cid):
    """The grant whose allocation the proposal is executed under.

    Production opens the proposal for the campaign that runs the assessment
    and names that campaign's own allocation (`trajectory.py:833-835`). The
    name alone is not enough: the executor looks the allocation up and
    refuses an unknown one, so a proposal naming a grant nobody opened fails
    with "refused: unknown allocation" instead of exercising the panel.
    """
    from experiments.ad01 import trajectory
    return trajectory.authorize_campaign(
        dsn, cid, authorized=100000)["allocation_id"]


def test_hidden_answer_perturbation_leaves_request_unchanged():
    from experiments.ad01 import packet
    base = _task()
    task_a = dict(base, hidden_answer="answer-A")
    task_b = dict(base, hidden_answer="answer-B")
    packet_a = packet.construction_packet(
        task=task_a, experience={"observations": []},
        budget={"max_queries": 4}, prior_failure=None)
    packet_b = packet.construction_packet(
        task=task_b, experience={"observations": []},
        budget={"max_queries": 4}, prior_failure=None)
    text_a = packet.render_construction_prompt(packet_a)
    text_b = packet.render_construction_prompt(packet_b)
    assert text_a == text_b
    assert "answer-A" not in text_a
    assert "answer-B" not in text_b


def test_sealed_observation_excluded_from_provider_request():
    from experiments.ad01 import learner
    sealed = {"observation_id": "obs-sealed-1",
              "task_id": "ad01-w0-dev-sw-00",
              "capability_id": "seed-sw-greedy",
              "verdict": "preserved",
              "access_label": "hidden",
              "hidden_answer": "sealed-bytes-xyz"}
    experience = {"observations": [sealed]}
    prompt = learner.visible_prompt(
        charter={"objective": "x", "freeze_id": "ad01"},
        visible=["ad01-w0-dev-sw-00"],
        experience=experience, retained=[],
        remaining={"queries": 16},
        curriculum=None)
    assert "sealed-bytes-xyz" not in prompt
    assert "obs-sealed-1" not in prompt


def test_protected_reference_refused_in_visible_context():
    from experiments.ad01 import packet
    from experiments.ad01 import worlds
    target = next(p.stem for p in sorted(
        worlds.FROZEN_DIR.rglob("*.json")) if "w0-transfer-sw" in p.stem)
    protected = {"observation_id": "obs-protected-1",
                 "task_id": target,
                 "capability_id": "seed-sw-greedy",
                 "verdict": "preserved"}
    with pytest.raises(ValueError, match="protected"):
        packet.visible_context(
            observations=[protected],
            basis_references=["obs-protected-1"])


def test_stale_bind_cannot_replace_newer(store):
    from experiments.ad01 import records, selection
    from settlement.common import Command
    scope = {"family": "software"}
    cid = "m34v-inv-stale"
    proposal = records.open_revision_proposal(
        store, investigation_id=cid,
        parent_digest="seed-sw-greedy",
        failure_record={"task_id": USE_TASK,
                        "parent_digest": "seed-sw-greedy",
                        "verdict": "not_preserved"},
        scope=dict(scope),
        allocation_id=_authorize(store, cid))
    freeze = records.freeze_candidate(
        store, proposal_id=proposal["proposal_id"],
        source_bytes=GOOD_SOURCE, entry=GOOD_ENTRY)
    assessment = records.assess_frozen(
        store, proposal_id=proposal["proposal_id"], tasks=[DEV_TASK],
        evaluator_version=EVALUATOR, protocol_id=PROTOCOL)
    assert assessment["outcome"] == "bind", assessment

    def _bind(versions, expected):
        return selection.bind_revision(
            store, release_id="s09-test-bind", versions=list(versions),
            scope=dict(scope), disposition="default",
            fallback="seed-sw-greedy", expected_versions=expected,
            policy_version="p1", protocol_id=PROTOCOL,
            evaluator_version=EVALUATOR,
            evidence_refs=[assessment["attempt_id"]],
            proposal_id=proposal["proposal_id"],
            candidate_digest=freeze["candidate_digest"])

    _bind(["v-old"], None)
    _bind(["v-new"], ["v-old"])
    with pytest.raises(selection.StaleBind):
        _bind(["v-stale"], ["v-old"])
    active = selection.active_binding_for(store, "software",
                                          release_id="s09-test-bind")
    assert active["versions"] == ["v-new"]
    repertoire = {"members": [
        {"capability_id": "v-old", "scope": {"family": "software"},
         "method_source": GOOD_SOURCE, "entry": GOOD_ENTRY,
         "source_digest": hashlib.sha256(GOOD_SOURCE.encode()).hexdigest()},
        {"capability_id": "v-new", "scope": {"family": "software"},
         "method_source": GOOD_SOURCE, "entry": GOOD_ENTRY,
         "source_digest": hashlib.sha256(GOOD_SOURCE.encode()).hexdigest()}]}
    chosen = selection.select_member(repertoire, {"family": "software"},
                                     dsn=store,
                                     release_id="s09-test-bind")
    assert chosen["capability_id"] == "v-new"
    _ = Command(request_id="noop", payload={})
