"""Database-backed gates for the shared durable policy-state API."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DSN = os.environ.get("SETTLEMENT_TEST_DSN", "")
TRUNCATE_DSN = os.environ.get("SETTLEMENT_TEST_TRUNCATE_DSN", "")
if not DSN or not TRUNCATE_DSN:
    missing = [
        name
        for name, value in (
            ("SETTLEMENT_TEST_DSN", DSN),
            ("SETTLEMENT_TEST_TRUNCATE_DSN", TRUNCATE_DSN),
        )
        if not value
    ]
    pytest.skip(
        "LOUD SKIP: durable-state database tests did not run; missing "
        + ", ".join(missing),
        allow_module_level=True,
    )
if DSN != TRUNCATE_DSN:
    pytest.fail(
        "SETTLEMENT_TEST_DSN and SETTLEMENT_TEST_TRUNCATE_DSN must match"
    )

from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Json

from settlement import db
from experiments.ad01 import s09_durable_state as durable


DB = str(conninfo_to_dict(DSN).get("dbname") or "")
# The property under test is that this store is disposable and private to the
# run. `tests/conftest_isolation.py` derives every name as
# `s09iso_<token>_<original>`, so requiring the original prefix to be *leading*
# could never hold and a `pytest.fail` here is a collection error that stops
# every other file in the session -- one error, zero results, rather than one
# red file. The shared and live names are what actually must be refused, and
# the derived form excludes both by construction.
_SHARED = ("ec02test_", "postgres", "template", "s09iso_00000000_")
if not DB or DB.startswith(("live",)) or DB in _SHARED or DB.endswith("_live"):
    pytest.fail(
        "durable-state tests require a disposable per-run database, got %r" % DB
    )
MIGRATIONS = ROOT / "migrations"

SOURCE = b"shared durable policy"
DIGEST = hashlib.sha256(SOURCE).hexdigest()
BINDING = durable.PolicyBinding(
    policy_id="shared-policy-v1",
    digest=DIGEST,
    digest_kind="source",
)
VIEW = {
    "instrument": "boolean",
    "task_id": "task-1",
    "remaining": 3,
    "observed": [],
}
ACTION = {
    "kind": "probe",
    "target": "task-1",
    "inputs": {"hypothesis": "seen"},
    "evidence_refs": [],
    "requested_resources": {"queries": 1},
}
STATE = {"at": "start", "progress": 1}


CHILD_SCRIPT = r"""
import json
import os
import sys

from experiments.ad01 import s09_durable_state as durable

mode, dsn, cid, binding_json, marker = sys.argv[1:]
binding = durable.PolicyBinding.from_dict(json.loads(binding_json))
view = json.loads(os.environ["DURABLE_VIEW"])
action = json.loads(os.environ["DURABLE_ACTION"])
state = json.loads(os.environ["DURABLE_STATE"])

def execute(_view):
    with open(marker, "a", encoding="utf-8") as handle:
        handle.write(mode + "\n")
    return {"action": action, "state": state}

step = durable.resume_or_step(
    dsn, cid, 0, binding=binding, view=view, execute=execute)
print(json.dumps({"pid": os.getpid(), "step": step.as_dict()}))
"""


@pytest.fixture()
def store(migrated_db):
    db.apply_migrations(migrated_db, MIGRATIONS)
    return migrated_db


def _child(mode, dsn, marker):
    env = dict(os.environ)
    env["PYTHONPATH"] = "%s:%s" % (ROOT, ROOT / "src")
    env["DURABLE_VIEW"] = json.dumps(VIEW)
    env["DURABLE_ACTION"] = json.dumps(ACTION)
    env["DURABLE_STATE"] = json.dumps(STATE)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            CHILD_SCRIPT,
            mode,
            dsn,
            "durable-restart",
            json.dumps(BINDING.as_dict()),
            str(marker),
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_round_trip_uses_the_existing_s09_store(store):
    cid = "durable-round-trip"
    committed = durable.persist_step(
        store, cid, 0, binding=BINDING,
        view=VIEW, action=ACTION, state=STATE)
    loaded = durable.load_step(store, cid, 0, binding=BINDING)

    assert loaded == committed
    assert loaded.state == STATE
    assert loaded.action == ACTION
    assert loaded.view_digest == durable.view_digest(VIEW)
    assert loaded.attempt_id == "att-%s-0" % cid
    # A persisted step has run no effect yet, so there is no operation to name
    # and the identity is empty. This used to assert
    # `ad01-%s-b0-effect` % cid, a constant no `operations` row ever carried:
    # the effect column named an identity that had never existed, which is
    # RF-02. Asserting the empty value instead pins the honest state, and the
    # companion test below pins that a real operation is adopted once one
    # exists.
    assert loaded.effect_id == ""


def test_an_incorporated_effect_replaces_the_empty_identity_with_its_operation(
        store):
    """Once the boundary runs an operation, the row names that operation.

    This is the half of the round trip the constant used to fake. The step API
    writes no effect identity because no effect has run; incorporating the
    boundary sets the identity from the operation that actually ran, and this
    API reads that row back rather than recomputing an answer of its own.
    """
    from experiments.ad01 import trajectory

    cid = "durable-round-trip-incorporated"
    durable.persist_step(
        store, cid, 0, binding=BINDING,
        view=VIEW, action=ACTION, state=STATE)
    operation_id = _settled_operation(store, "durable-round-trip-incorporated")
    trajectory._s09_incorporate(
        store, cid, 0, decision={"next_action": {"kind": "diagnostic"}},
        observation={"observation_id": "obs-durable"},
        episode={"kind": "diagnostic", "operation_id": operation_id},
        spend=1, provenance="s09-m1")
    loaded = durable.load_step(store, cid, 0, binding=BINDING)
    assert loaded.effect_id == operation_id
    assert loaded.attempt_id == "att-%s-0" % cid


def _settled_operation(dsn, campaign):
    """One settled operation, admitted the way a boundary admits it.

    A real allocation and a real broker admission, so the identity this test
    pins is an operation the store actually holds rather than a row written
    for the test to find.
    """
    from settlement import broker
    from experiments.ad01 import trajectory

    trajectory.authorize_campaign(dsn, campaign, authorized=100000)
    operation_id = "durable-op-%s" % campaign
    result = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"]},
        allocation_id=trajectory._alloc_id(campaign))
    assert result.code.name in ("APPLIED", "ALREADY_APPLIED"), result.detail
    with trajectory._read_conn(dsn) as conn:
        conn.execute(
            "UPDATE operations SET settled = TRUE, dispatch_state = 'observed'"
            " WHERE id = %s", (operation_id,))
        conn.commit()
    return operation_id


def test_fresh_interpreter_resumes_without_re_execution(store, tmp_path):
    commit_marker = tmp_path / "commit.log"
    retry_marker = tmp_path / "retry.log"
    first = _child("commit", store, commit_marker)
    resumed = _child("resume", store, retry_marker)

    assert first["pid"] != resumed["pid"]
    assert resumed["step"] == first["step"]
    assert commit_marker.read_text().splitlines() == ["commit"]
    assert not retry_marker.exists()


def test_repeated_persist_is_idempotent_for_state_and_model_calls(store):
    cid = "durable-idempotent"
    operation_id = "ad01-%s-policy-s0-model-k0" % cid
    with db.connect(store) as conn:
        conn.execute(
            "INSERT INTO operations (id, payload_digest, payload)"
            " VALUES (%s, %s, %s)",
            (operation_id, "0" * 64, Json({"effect": "model-inference"})),
        )
        conn.commit()
    before = durable.durable_model_calls(store, cid, 0)

    first = durable.persist_step(
        store, cid, 0, binding=BINDING,
        view=VIEW, action=ACTION, state=STATE)
    second = durable.persist_step(
        store, cid, 0, binding=BINDING,
        view=VIEW, action=ACTION, state=STATE)

    assert before == 1
    assert second == first
    assert durable.durable_model_calls(store, cid, 0) == 1
    with db.connect(store) as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = 0",
            (cid,)).fetchone()
        conn.commit()
    assert count[0] == 1


@pytest.mark.parametrize(
    "resumed_binding",
    [
        replace(BINDING, policy_id="different-policy"),
        replace(BINDING, digest="f" * 64, digest_kind="ast"),
    ],
    ids=["policy-id-mismatch", "source-digest-mismatch"],
)
def test_load_refuses_a_different_policy(store, resumed_binding):
    cid = "durable-binding"
    durable.persist_step(
        store, cid, 0, binding=BINDING,
        view=VIEW, action=ACTION, state=STATE)

    with pytest.raises(durable.PolicyBindingMismatch):
        durable.load_step(store, cid, 0, binding=resumed_binding)


def test_durable_path_refuses_state_over_the_byte_cap(store):
    cid = "durable-oversized"
    oversized = {"payload": "x" * durable.policy_step.STATE_LIMIT_BYTES}

    with pytest.raises(ValueError, match="policy state exceeds 4096 bytes"):
        durable.persist_step(
            store, cid, 0, binding=BINDING,
            view=VIEW, action=ACTION, state=oversized)

    assert durable.load_step(store, cid, 0, binding=BINDING) is None
