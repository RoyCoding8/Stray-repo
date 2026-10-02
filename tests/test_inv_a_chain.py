"""The milestone-A chain, entered through the public entry.

    permitted experience -> program decision -> admitted effect ->
    observation -> checked artifact -> retention/binding -> fresh-process use

Every arrow is asserted against a durable row read back from PostgreSQL,
and every policy byte is this lane's own
(`test_inv_a_reviewer_source`). Nothing here reuses the fixture of a lane
whose work it is verifying.

Method identity and policy identity are held apart deliberately. The
method release carries the constructed bytes; the use policy carries its
own digest; and the test asserts they differ, so a pass cannot come from
the two coinciding.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_inv_a_reviewer_source as reviewer

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "a5chain"
CHARTER = {"objective": "reduce examples while preserving their witness",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 4, "diagnostic_queries": 16, "model_calls": 20}
ACQUIRE_TASKS = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01", "ad01-w0-dev-sw-00"]
USE_TASK = "ad01-w0-within-sw-00"
CAMPAIGN_SEQ = 301


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


class Constructor:
    """The offline fixture gateway. No network, no credentials."""

    def __init__(self, source=reviewer.ACQUIRED_METHOD):
        from settlement.gateway import Usage

        self.calls = []
        self.source = source
        self.usage = Usage(input_tokens=10, output_tokens=20)

    def check_discovery(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus

        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        from settlement.gateway import ModelResponse

        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            json.dumps({"entry": self.source, "notes": "a5 reviewer"}),
            {}, self.usage, "stop")

    def cancel(self, operation_id):
        return False


def _consumer(dsn, cid, source, gateway=None):
    from experiments.ad01 import agenda_policy, policy_step, trajectory

    trajectory.authorize_campaign(dsn, cid, authorized=100000)
    return agenda_policy.step_policy_consumer(
        policy_step.make_policy_artifact(source, origin="authored-control"),
        dsn=dsn, cid=cid, charter=dict(CHARTER), world=0, arm="I",
        allocation_id=trajectory._alloc_id(cid), study_root=cid,
        gateway=gateway, model="a5-reviewer-double")


def _trajectory():
    from experiments.ad01 import trajectory

    return trajectory


def _query(dsn, sql, params=()):
    from experiments.ad01 import trajectory

    with trajectory._read_conn(dsn) as conn:
        rows = conn.execute(sql, params).fetchall()
        conn.commit()
        return rows


def _freeze(campaign, path):
    from experiments.ad01 import trajectory

    trajectory.freeze_repertoire(campaign, path)
    return trajectory.load_repertoire(path)


def _acquire(store, seq=CAMPAIGN_SEQ):
    from experiments.ad01 import trajectory

    cid = trajectory.campaign_id(0, "I", seq)
    gateway = Constructor()
    out = trajectory.run_campaign(
        0, "I", CHARTER, CAPS, tasks=list(ACQUIRE_TASKS), campaign_seq=seq,
        dsn=store, consumer=_consumer(store, cid, reviewer.CHAIN_SOURCE,
                                     gateway=gateway),
        constructor="model", gateway=gateway, model="a5-reviewer-double")
    return cid, out, gateway


@pytest.fixture(scope="module")
def acquired(store, tmp_path_factory):
    """One campaign, reused by the arrow tests so they read the same rows."""
    cid, out, gateway = _acquire(store)
    path = tmp_path_factory.mktemp("a5") / ("repertoire-%d.json" % CAMPAIGN_SEQ)
    repertoire = _freeze(out, path)
    return {"cid": cid, "campaign": out, "gateway": gateway,
            "path": path, "repertoire": repertoire}


# --- the arrows ---------------------------------------------------------


def test_permitted_experience_reaches_the_program_as_a_durable_row(acquired,
                                                                    store):
    """Arrow 1. The probe the policy admitted ran as an admitted operation."""
    cid = acquired["cid"]
    campaign = acquired["campaign"]
    probe = campaign["episodes"][0]
    assert probe["kind"] == "diagnostic"
    assert probe["disposition"] == "inspected"
    step_ops = _query(
        store,
        "SELECT id, dispatch_state, settled, payload->>'effect' AS effect"
        " FROM operations WHERE id = %s",
        ("ad01-%s-policy-s0-k0" % cid,))
    assert len(step_ops) == 1
    assert dict(step_ops[0])["effect"] == "sandbox-exec"
    assert dict(step_ops[0])["settled"] is True


def test_program_decision_is_recorded_before_the_effect_it_admitted(
        acquired, store):
    """Arrow 2. The decision row exists and names the action that ran."""
    cid = acquired["cid"]
    rows = _query(
        store,
        "SELECT seq, policy_output, accepted_action FROM s09_policy_state"
        " WHERE investigation_id = %s ORDER BY seq", (cid,))
    kinds = []
    for row in rows:
        output = dict(row["policy_output"] or {})
        kinds.extend(r["action"]["kind"] for r in output.get("results", []))
    assert kinds == ["diagnose", "construct_method", "use_method"]
    assert all(reviewer.digest(reviewer.CHAIN_SOURCE) ==
               dict(row["policy_output"])["source_digest"] for row in rows)


def test_admitted_effect_carries_a_receipt_for_every_operation(acquired,
                                                               store):
    """Arrow 3. Each admitted operation settled with a receipt of its own."""
    cid = acquired["cid"]
    ops = _query(
        store,
        "SELECT id, settled, dispatch_state FROM operations"
        " WHERE id LIKE %s ORDER BY id", ("ad01-%s%%" % cid,))
    assert ops, "the campaign ran no durable operation"
    for op in ops:
        assert dict(op)["settled"] is True, dict(op)["id"]
        receipts = _query(
            store, "SELECT receipt_identity FROM receipts"
            " WHERE operation_id = %s", (dict(op)["id"],))
        assert receipts, "operation %s settled with no receipt" % dict(op)["id"]


def test_observation_is_stored_and_the_next_boundary_reads_it_back(
        acquired, store):
    """Arrow 4. The observation is a row, and the campaign resumed on it."""
    cid = acquired["cid"]
    campaign = acquired["campaign"]
    observation_id = campaign["boundaries"][0]["observation_id"]
    stored = _query(
        store,
        "SELECT id, content FROM attempt_observations"
        " WHERE content->>'observation_id' = %s",
        (observation_id,))
    assert stored, "observation %s is not durable" % observation_id
    assert dict(stored[0]["content"])["kind"] == "boundary"
    durable = dict(stored[0]["content"])["observation"]
    assert durable["observation_id"] == observation_id
    assert durable["task_id"] == "ad01-w0-dev-sw-00"
    settled, _pending = _trajectory()._read_campaign(store, cid)
    assert settled[0]["observation"]["observation_id"] == observation_id


def test_checked_artifact_kept_only_what_the_checker_preserved(acquired,
                                                               store):
    """Arrow 5. Retention is the checker's verdict, and it is in the row."""
    cid = acquired["cid"]
    row = _query(
        store,
        "SELECT effect_record FROM s09_policy_state"
        " WHERE investigation_id = %s AND seq = 1", (cid,))
    episode = dict(dict(row[0]["effect_record"])["episode"])
    assert episode["disposition"] == "retained"
    assert episode["check"]["verdict"] == "preserved"
    executable = episode["executable"]
    assert executable["authored"] is False
    assert executable["source_digest"] == hashlib.sha256(
        executable["method_source"].encode("utf-8")).hexdigest()
    assert executable["method_source"] == reviewer.ACQUIRED_METHOD


def test_retention_binds_bytes_the_release_and_the_repertoire_agree_on(
        acquired, store):
    """Arrow 6. Bound bytes, and a release that is not the policy."""
    cid = acquired["cid"]
    member = acquired["repertoire"]["members"][0]
    assert member["capability_id"].startswith("acquired-sw-")
    assert member["authored"] is False
    assert member["source_digest"] == reviewer.digest(
        reviewer.ACQUIRED_METHOD)
    row = _query(
        store,
        "SELECT effect_record FROM s09_policy_state"
        " WHERE investigation_id = %s AND seq = 1", (cid,))
    episode = dict(dict(row[0]["effect_record"])["episode"])
    assert episode["disposition"] == "retained"
    releases = _query(
        store, "SELECT id, disposition FROM capability_releases")
    # Method release identity and policy identity are separate. Nothing in
    # this chain minted a release, and the policy digest is not one, so the
    # use record can carry a policy without a release standing in for it.
    assert [dict(r)["id"] for r in releases] == []
    assert member["source_digest"] != reviewer.digest(
        reviewer.use_source(member["capability_id"]))


def test_fresh_process_use_runs_the_bound_bytes_not_the_policy(store,
                                                               acquired):
    """Arrow 7. A separate interpreter ran the method; the use row says so."""
    from experiments.ad01 import trajectory

    cid = acquired["cid"]
    member = acquired["repertoire"]["members"][0]
    records = trajectory.run_use(
        acquired["repertoire"], 0, "I", [USE_TASK], {},
        policy_source=reviewer.use_source(member["capability_id"]),
        dsn=store, allocation_id=trajectory._alloc_id(cid))
    assert len(records) == 1
    record = records[0]
    # `status` is a refusal-only key: a record that ran has none, so
    # asserting its absence is what separates "used" from "refused".
    assert "status" not in record
    assert record["selected"] == member["capability_id"]
    assert record["executed"] == member["capability_id"]
    assert record["executed_source"] == reviewer.ACQUIRED_METHOD
    assert record["verdict"] == "preserved"
    assert record["fallback_reason"] == ""
    # The policy that admitted the use and the method that ran are two
    # operations with two receipts, not one column wearing two names.
    assert len(record["operation_ids"]) == 2
    assert record["policy_source_digest"] != member["source_digest"]
    for operation_id in record["operation_ids"]:
        row = _query(store, "SELECT settled FROM operations WHERE id = %s",
                     (operation_id,))
        assert row and dict(row[0])["settled"] is True


def test_the_retained_program_state_crossed_every_boundary_on_a_row(
        acquired, store):
    """The private state survived only because a row carried it."""
    cid = acquired["cid"]
    rows = _query(
        store,
        "SELECT seq, state_transition FROM s09_policy_state"
        " WHERE investigation_id = %s ORDER BY seq", (cid,))
    stages = [dict(dict(row["state_transition"]).get("final_state", {})
                  ).get("stage") for row in rows]
    assert stages == [1, 1, 3]


# --- the entry itself ----------------------------------------------------


def test_the_chain_was_entered_through_run_campaign(store, acquired):
    from experiments.ad01 import trajectory

    assert acquired["campaign"]["campaign_id"] == acquired["cid"]
    assert acquired["cid"] == trajectory.campaign_id(0, "I", CAMPAIGN_SEQ)
    assert [b["seq"] for b in acquired["campaign"]["boundaries"]] == [0, 1, 2]


def test_a_second_run_of_the_same_campaign_does_not_redo_the_work(store,
                                                                  acquired):
    """Re-entry is idempotent: the settled rows answer instead of re-running."""
    from experiments.ad01 import trajectory

    cid = acquired["cid"]
    before = len(_query(store, "SELECT id FROM operations WHERE id LIKE %s",
                        ("ad01-%s%%" % cid,)))
    again = trajectory.run_campaign(
        0, "I", CHARTER, CAPS, tasks=list(ACQUIRE_TASKS),
        campaign_seq=CAMPAIGN_SEQ, dsn=store,
        consumer=_consumer(store, cid, reviewer.CHAIN_SOURCE),
        constructor="model", gateway=Constructor(), model="a5-reviewer-double")
    after = len(_query(store, "SELECT id FROM operations WHERE id LIKE %s",
                       ("ad01-%s%%" % cid,)))
    assert again["campaign_id"] == cid
    assert after == before
    assert [b["seq"] for b in again["boundaries"]] == [0, 1, 2]
    assert all(b.get("resumed") for b in again["boundaries"])