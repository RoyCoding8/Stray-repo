from __future__ import annotations

import uuid

import pytest
from psycopg.types.json import Json

from rsi import investigation, verifier
from settlement import broker, db, store
from settlement.common import Command, ResultCode


def _cmd(payload, *, expected_revision=None):
    return Command(request_id=f"p01-{uuid.uuid4().hex}",
                   expected_revision=expected_revision, payload=payload)


def _create(dsn, *, max_steps=2, token_authorized=100_000,
            cpu_authorized=100_000, genome="g" * 64, task="t" * 64):
    for allocation_id, domain in (("tokens", "tokens"), ("cpu", "cpu")):
        store.seed_allocation(dsn, _cmd({"allocation_id": allocation_id,
                                         "domain": domain,
                                         "authorized": token_authorized if domain == "tokens"
                                         else cpu_authorized}))
    payload = {
        "investigation_id": "inv-p01",
        "objective": "Solve the public task.",
        "domain": "task",
        "open_questions": ["Does the solution satisfy the task obligation?"],
        "artifact_refs": {},
        "allocation_id": "tokens",
        "policy": {"id": "task-seed/1"},
        "config": {"token_allocation": "tokens", "cpu_allocation": "cpu",
                   "genome": genome, "task": task,
                   "max_steps": max_steps, "timeout_ms": 30_000,
                   "token_ceiling": 5_000},
    }
    return payload, investigation.create(dsn, _cmd(payload))


def _reserve_worker(dsn, payload, *, operation_id, artifact_refs=None):
    return investigation.decide(
        dsn,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "attempt_id": "attempt-0",
              "operation_id": operation_id,
              "action": {"kind": "worker", "explanation": "try",
                         "intended_observation": "check"},
              "visible_input": {"objective": payload["objective"],
                                "objective_revision": 1, "state_revision": 0,
                                "open_questions": payload["open_questions"],
                                "artifact_refs": artifact_refs or {},
                                "previous_observation": None}},
             expected_revision=0),
    )


def _seed_completed_episode(dsn, payload, operation_id):
    genome, task, trajectory = (payload["config"]["genome"], payload["config"]["task"],
                                "c" * 64)
    evaluator_version = "public-evaluator/1"
    with db.connect(dsn) as conn:
        for digest in (genome, task, trajectory):
            conn.execute("INSERT INTO artifact_versions (digest, size, manifest, availability)"
                         " VALUES (%s, 0, '{}'::jsonb, 'available')", (digest,))
        conn.execute("INSERT INTO rsi_genomes (digest, harness) VALUES (%s, 'public')", (genome,))
        conn.execute("INSERT INTO rsi_tasks (digest, name, split, evaluator_version)"
                     " VALUES (%s, 'public-task', 'dev', %s)", (task, evaluator_version))
        conn.execute("INSERT INTO operations (id, attempt_id, payload_digest, dispatch_state, settled)"
                     " VALUES (%s, 'attempt-0', %s, 'observed', TRUE)",
                     (operation_id, "d" * 64))
        conn.execute("INSERT INTO rsi_episodes (operation_id, genome, task, status, seconds, trajectory)"
                     " VALUES (%s, %s, %s, 'completed', 1.0, %s)",
                     (operation_id, genome, task, trajectory))
    return evaluator_version, trajectory


def test_create_binds_objective_and_reads_initial_continuation(migrated_db):
    payload, result = _create(migrated_db)

    assert result.code == ResultCode.APPLIED
    state = investigation.read(migrated_db, payload["investigation_id"])
    assert state == {
        "investigation_id": "inv-p01",
        "objective": "Solve the public task.",
        "objective_revision": 1,
        "revision": 0,
        "status": "ready",
        "domain": "task",
        "config": payload["config"],
        "policy": payload["policy"],
        "open_questions": ["Does the solution satisfy the task obligation?"],
        "artifact_refs": {},
        "pending_decision": None,
        "last_observation": None,
    }


@pytest.mark.parametrize(("field", "value"), [
    ("objective", None),
    ("domain", None),
    ("allocation_id", None),
    ("config", None),
    ("policy", None),
    ("artifact_refs", None),
    ("open_questions", "question"),
    ("open_questions", []),
    ("open_questions", [None]),
])
def test_create_rejects_invalid_input_shapes(migrated_db, field, value):
    payload, _ = _create(migrated_db)
    # The fixture's valid row gives this case its real objective/allocation context;
    # use a new identity for the rejected request.
    payload["investigation_id"] = "inv-p01-invalid"
    payload[field] = value

    result = investigation.create(migrated_db, _cmd(payload))

    assert result.code == ResultCode.INVALID_INPUT
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM investigations"
                            " WHERE id = 'inv-p01-invalid'").fetchone()[0] == 0


def test_stale_decision_cannot_reserve_an_attempt_or_operation(migrated_db):
    payload, _ = _create(migrated_db)
    result = investigation.decide(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-stale", "attempt_id": "attempt-stale",
              "operation_id": "operation-stale", "action": {"kind": "worker", "explanation": "try", "intended_observation": "check"},
              "visible_input": {"objective": payload["objective"],
                                "objective_revision": 1, "state_revision": 0,
                                "open_questions": payload["open_questions"],
                                "artifact_refs": {}, "previous_observation": None}},
             expected_revision=99),
    )

    assert result.code == ResultCode.STALE_REVISION
    state = investigation.read(migrated_db, payload["investigation_id"])
    assert state["revision"] == 0 and state["pending_decision"] is None
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_decision_persists_exact_operation_identity_before_dispatch(migrated_db):
    payload, _ = _create(migrated_db)
    decision_payload = {
        "investigation_id": payload["investigation_id"],
        "decision_id": "decision-0", "attempt_id": "attempt-0",
        "operation_id": "operation-0", "action": {"kind": "worker", "explanation": "try", "intended_observation": "check"},
        "visible_input": {"objective": payload["objective"],
                           "objective_revision": 1, "state_revision": 0,
                           "open_questions": payload["open_questions"],
                           "artifact_refs": {}, "previous_observation": None},
    }

    result = investigation.decide(migrated_db, _cmd(decision_payload, expected_revision=0))
    state = investigation.read(migrated_db, payload["investigation_id"])

    assert result.code == ResultCode.APPLIED
    assert state["revision"] == 1 and state["status"] == "pending"
    assert state["pending_decision"] == {
        "id": "decision-0", "attempt_id": "attempt-0",
        "operation_id": "operation-0", "action": decision_payload["action"],
        "visible_input": decision_payload["visible_input"],
    }
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 0


def test_uncertain_or_unrecorded_effect_keeps_pending_identity(migrated_db):
    payload, _ = _create(migrated_db)
    investigation.decide(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "attempt_id": "attempt-0",
              "operation_id": "operation-0", "action": {"kind": "worker", "explanation": "try", "intended_observation": "check"},
              "visible_input": {"objective": payload["objective"],
                                "objective_revision": 1, "state_revision": 0,
                                "open_questions": payload["open_questions"],
                                "artifact_refs": {}, "previous_observation": None}},
             expected_revision=0),
    )
    result = investigation.observe(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "operation_id": "operation-0",
              "outcome": "completed", "open_questions": [], "artifact_refs": {},
              "observation": {"episode": "operation-0", "verdict": "missing",
                              "solution": "s" * 64, "status": "passed",
                              "passed": True, "reason": "claimed by caller"}},
             expected_revision=1),
    )

    state = investigation.read(migrated_db, payload["investigation_id"])
    assert result.code != ResultCode.APPLIED or result.data.get("status") == "pending"
    assert state["revision"] == 1 and state["status"] == "pending"
    assert state["pending_decision"]["operation_id"] == "operation-0"
    assert state["last_observation"] is None
    with db.connect(migrated_db) as conn:
        conn.execute("INSERT INTO command_journal (request_id, payload_digest, result_code, result_detail)"
                     " VALUES (%s, %s, 'outcome_unknown', 'prepare result uncertain')",
                     ("broker-prep-operation-0", "d" * 64))
    uncertain = investigation.observe(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "operation_id": "operation-0",
              "outcome": "unresolved", "open_questions": payload["open_questions"],
              "artifact_refs": {},
              "observation": {"episode": "operation-0", "status": "refused",
                              "passed": None, "verdict": None, "solution": None,
                              "reason": "untrusted caller text"}}, expected_revision=1),
    )
    assert uncertain.code == ResultCode.OUTCOME_UNKNOWN
    assert investigation.read(migrated_db, payload["investigation_id"])["status"] == "pending"


def test_durable_budget_refusal_ends_as_inspectable_unresolved(migrated_db):
    payload, _ = _create(migrated_db, token_authorized=1)
    investigation.decide(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "attempt_id": "attempt-0",
              "operation_id": "operation-refused",
              "action": {"kind": "worker", "explanation": "try",
                         "intended_observation": "check"},
              "visible_input": {"objective": payload["objective"],
                                "objective_revision": 1, "state_revision": 0,
                                "open_questions": payload["open_questions"],
                                "artifact_refs": {}, "previous_observation": None}},
             expected_revision=0),
    )
    refused = broker.ensure_operation(
        migrated_db, operation_id="operation-refused", effect=broker.AGENT_RUN,
        payload={"harness": "public", "genome": "a" * 64, "task": "b" * 64,
                 "instruction": payload["objective"], "config": {},
                 "timeout_ms": 30_000, "token_ceiling": 5_000},
        allocation_id="tokens", attempt_id="attempt-0",
    )
    assert refused.code == ResultCode.INSUFFICIENT_RESOURCES
    result = investigation.observe(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "operation_id": "operation-refused",
              "outcome": "unresolved", "open_questions": payload["open_questions"],
              "artifact_refs": {},
              "observation": {"episode": "operation-refused", "status": "refused",
                              "passed": None, "verdict": None, "solution": None,
                              "reason": "caller reason is ignored"}}, expected_revision=1),
    )

    state = investigation.read(migrated_db, payload["investigation_id"])
    assert result.code == ResultCode.APPLIED
    assert state["revision"] == 2 and state["status"] == "unresolved"
    assert state["pending_decision"] is None and state["artifact_refs"] == {}
    assert state["last_observation"]["reason"] == refused.detail
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 0
        assert conn.execute("SELECT lifecycle FROM attempts WHERE id = 'attempt-0'").fetchone()[0] == "failed"


def test_durable_verifier_budget_refusal_ends_completed_worker_unresolved(migrated_db):
    payload, _ = _create(migrated_db, cpu_authorized=1,
                         genome="a" * 64, task="b" * 64)
    previous_refs = {"solution": "e" * 64}
    with db.connect(migrated_db) as conn:
        conn.execute("UPDATE rsi_investigations SET artifact_refs = %s WHERE investigation_id = %s",
                     (Json(previous_refs), payload["investigation_id"]))
    worker_operation = "operation-worker-completed"
    assert _reserve_worker(migrated_db, payload, operation_id=worker_operation,
                           artifact_refs=previous_refs).code == ResultCode.APPLIED
    evaluator_version, _ = _seed_completed_episode(migrated_db, payload, worker_operation)
    verifier_operation = verifier.operation_id_for(worker_operation, evaluator_version)
    refused = broker.ensure_operation(
        migrated_db, operation_id=verifier_operation, effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["python", "-c", "pass"],
                 "timeout_ms": 30_000, "max_output_bytes": 65_536},
        allocation_id="cpu", attempt_id="attempt-0",
    )
    assert refused.code == ResultCode.INSUFFICIENT_RESOURCES
    result = investigation.observe(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "operation_id": worker_operation,
              "outcome": "unresolved", "open_questions": payload["open_questions"],
              "artifact_refs": previous_refs,
              "observation": {"episode": worker_operation, "status": "refused",
                              "passed": None, "verdict": None, "solution": None,
                              "reason": "caller reason is ignored"}}, expected_revision=1),
    )

    state = investigation.read(migrated_db, payload["investigation_id"])
    assert result.code == ResultCode.APPLIED
    assert state["status"] == "unresolved" and state["pending_decision"] is None
    assert state["artifact_refs"] == previous_refs
    assert state["last_observation"]["episode"] == worker_operation
    assert state["last_observation"]["refused_operation"] == verifier_operation
    assert state["last_observation"]["reason"] == refused.detail
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM rsi_verdicts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM operations WHERE id = %s",
                            (verifier_operation,)).fetchone()[0] == 0
        assert conn.execute("SELECT lifecycle FROM attempts WHERE id = 'attempt-0'").fetchone()[0] == "failed"


def test_uncertain_verifier_preparation_keeps_completed_worker_pending(migrated_db):
    payload, _ = _create(migrated_db, genome="a" * 64, task="b" * 64)
    worker_operation = "operation-worker-completed"
    assert _reserve_worker(migrated_db, payload, operation_id=worker_operation).code == ResultCode.APPLIED
    evaluator_version, _ = _seed_completed_episode(migrated_db, payload, worker_operation)
    verifier_operation = verifier.operation_id_for(worker_operation, evaluator_version)
    with db.connect(migrated_db) as conn:
        conn.execute("INSERT INTO command_journal (request_id, payload_digest, result_code, result_detail)"
                     " VALUES (%s, %s, 'outcome_unknown', 'verifier preparation is uncertain')",
                     ("broker-prep-" + verifier_operation, "f" * 64))
    result = investigation.observe(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "operation_id": worker_operation,
              "outcome": "unresolved", "open_questions": payload["open_questions"],
              "artifact_refs": {},
              "observation": {"episode": worker_operation, "status": "refused",
                              "passed": None, "verdict": None, "solution": None,
                              "reason": "untrusted caller reason"}}, expected_revision=1),
    )

    state = investigation.read(migrated_db, payload["investigation_id"])
    assert result.code == ResultCode.OUTCOME_UNKNOWN
    assert state["status"] == "pending" and state["revision"] == 1
    assert state["pending_decision"]["operation_id"] == worker_operation
    assert state["last_observation"] is None


def test_suspending_pending_effect_preserves_identity_and_resume_recovers_it(migrated_db):
    payload, _ = _create(migrated_db)
    investigation.decide(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-0", "attempt_id": "attempt-0",
              "operation_id": "operation-0", "action": {"kind": "worker", "explanation": "try", "intended_observation": "check"},
              "visible_input": {"objective": payload["objective"],
                                "objective_revision": 1, "state_revision": 0,
                                "open_questions": payload["open_questions"],
                                "artifact_refs": {}, "previous_observation": None}},
             expected_revision=0),
    )
    suspended = investigation.suspend(
        migrated_db, _cmd({"investigation_id": payload["investigation_id"]}, expected_revision=1))
    assert suspended.code == ResultCode.APPLIED
    state = investigation.read(migrated_db, payload["investigation_id"])
    assert state["revision"] == 2 and state["status"] == "suspended"
    assert state["pending_decision"]["operation_id"] == "operation-0"

    refused = investigation.decide(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-1", "attempt_id": "attempt-1",
              "operation_id": "operation-1", "action": {"kind": "worker", "explanation": "try", "intended_observation": "check"},
              "visible_input": {"objective": payload["objective"],
                                "objective_revision": 1, "state_revision": 2,
                                "open_questions": payload["open_questions"],
                                "artifact_refs": {}, "previous_observation": None}},
             expected_revision=2),
    )
    assert refused.code == ResultCode.INVALID_INPUT
    assert investigation.read(migrated_db, payload["investigation_id"])["revision"] == 2

    resumed = investigation.resume(
        migrated_db, _cmd({"investigation_id": payload["investigation_id"]}, expected_revision=2))
    assert resumed.code == ResultCode.APPLIED
    state = investigation.read(migrated_db, payload["investigation_id"])
    assert state["revision"] == 3 and state["status"] == "pending"
    assert state["pending_decision"]["operation_id"] == "operation-0"


def test_operation_identity_cannot_be_reserved_by_two_investigations(migrated_db):
    first, _ = _create(migrated_db)
    second = dict(first, investigation_id="inv-p01-second")
    created = investigation.create(migrated_db, _cmd(second))
    assert created.code == ResultCode.APPLIED

    def reserve(payload, decision, attempt, revision):
        return investigation.decide(
            migrated_db,
            _cmd({"investigation_id": payload["investigation_id"],
                  "decision_id": decision, "attempt_id": attempt,
                  "operation_id": "operation-shared",
                  "action": {"kind": "worker", "explanation": "try",
                             "intended_observation": "check"},
                  "visible_input": {"objective": payload["objective"],
                                    "objective_revision": 1, "state_revision": revision,
                                    "open_questions": payload["open_questions"],
                                    "artifact_refs": {}, "previous_observation": None}},
                 expected_revision=revision),
        )

    assert reserve(first, "decision-first", "attempt-first", 0).code == ResultCode.APPLIED
    refused = reserve(second, "decision-second", "attempt-second", 0)
    assert refused.code == ResultCode.INVALID_INPUT
    assert investigation.read(migrated_db, second["investigation_id"])["status"] == "ready"
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1


def test_amended_kernel_objective_cannot_be_used_by_old_continuation(migrated_db):
    payload, _ = _create(migrated_db)
    amended = store.amend_commitment(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "objective": "A different objective."}, expected_revision=1),
    )
    assert amended.code == ResultCode.APPLIED
    result = investigation.decide(
        migrated_db,
        _cmd({"investigation_id": payload["investigation_id"],
              "decision_id": "decision-old-objective", "attempt_id": "attempt-old-objective",
              "operation_id": "operation-old-objective",
              "action": {"kind": "worker", "explanation": "try",
                         "intended_observation": "check"},
              "visible_input": {"objective": payload["objective"],
                                "objective_revision": 1, "state_revision": 0,
                                "open_questions": payload["open_questions"],
                                "artifact_refs": {}, "previous_observation": None}},
             expected_revision=0),
    )
    assert result.code == ResultCode.STALE_REVISION
    state = investigation.read(migrated_db, payload["investigation_id"])
    assert state["objective"] == payload["objective"]
    assert state["objective_revision"] == 1 and state["revision"] == 0
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
