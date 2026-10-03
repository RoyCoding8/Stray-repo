"""INV-B2 gate: one driver, one envelope, durable continuation.

Real Postgres (`inv_b2_loop`, never live) in every brokered test. Doubles
sit at the provider seam only: the recording gateway answers model calls,
LocalLauncher runs sandboxes. Every assertion names a literal durable
outcome: exactly one repair claim, post-effect balances, reused action
identity across a kill, and two visible journaled transitions for a
rejection followed by its correction.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DSN = os.environ.get(
    "INV_B2_DSN",
    "dbname=inv_b2_loop host=/var/run/postgresql user=ubuntu")
MIGRATIONS = ROOT / "migrations"


def _fresh_db():
    assert "live" not in DSN
    from settlement import db
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                " AND tablename != 'schema_migrations'")
            for (table,) in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        conn.commit()


def _cmd(payload):
    from settlement.common import Command
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _study(authorized=100_000):
    from settlement import store
    from settlement.loop import ResourceEnvelope
    store.admit_commitment(DSN, _cmd({"investigation_id": "i1", "objective": "o"}))
    return ResourceEnvelope.bind(DSN, "st1", authorized)


class DeadLauncher:
    launcher_id = "dead-1"
    profile = "local-process"
    idempotent_resend = False

    def dispatch(self, op):
        from settlement.common import ResultCode
        err = RuntimeError("no such profile on this host")
        err.code = ResultCode.INCOMPATIBLE_VERSION
        raise err

    def prior_send(self, operation_id):
        return False

    def stop(self, operation_id):
        return False

    def live_ids(self):
        return []

    def is_live(self, operation_id):
        return False

    def read_result(self, operation_id):
        return None


class RecordingGateway:
    def __init__(self, texts, billed=True):
        from settlement.gateway import Usage
        self._texts = list(texts)
        self._usage = Usage(input_tokens=11, output_tokens=7,
                            charge_units=3, billed=billed)
        self.calls: list = []

    def infer(self, request):
        from settlement.gateway import ModelResponse
        self.calls.append(request)
        return ModelResponse(
            request.operation_id,
            self._texts[min(len(self.calls) - 1, len(self._texts) - 1)],
            {}, self._usage, "stop")

    def cancel(self, operation_id):
        return False


def _packet():
    from experiments.ad01.packet import decision_packet
    return decision_packet(
        charter={"objective": "x", "freeze_id": "ad01"},
        visible=["t1"],
        experience={"observations": [{"observation_id": "obs-0", "task_id": "t1",
                                      "capability_id": "seed", "verdict": "unmeasured",
                                      "detail": "d"}]},
        retained=[], remaining={"queries": 6, "model_calls": 60},
        curriculum="t1", boundary={"world": 0, "arm": "I", "seq": 0})


def _note_propose(materialized, state):
    return {"target": "t1", "instrument": "note",
            "inputs": {"payload": {}, "idempotency_key": "k1"},
            "dependencies": [], "requested": {}, "hypothesis": None}


def test_one_driver_decides_stuck_op_once(tmp_path):
    _fresh_db()
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from scripts import scheduler as sched
    from settlement import agenda, broker, store

    _study()
    store.acquire_work(DSN, _cmd({"attempt_id": "att1", "investigation_id": "i1",
                                  "allocation_id": "st1"}))
    broker.ensure_operation(
        DSN, operation_id="op-hung", effect="sandbox-exec",
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 5000, "max_output_bytes": 65536},
        allocation_id="st1", attempt_id="att1")
    dead = DeadLauncher()
    broker.dispatch_operation(DSN, "op-hung", launchers={"local-process": dead})
    assert broker.read_operation(DSN, "op-hung")["dispatch_state"] == "dispatching"

    first = broker.sweep(DSN, {"local-process": dead}, repair=True, wake=True)
    assert first.repaired == []
    assert first.next_decision == "idle"
    assert broker.read_operation(DSN, "op-hung")["dispatch_state"] == "unresolved"

    assert broker.heartbeat(DSN, {"local-process": dead}, repair_due=True).repaired == []
    assert agenda.repair_scan(DSN, {"local-process": dead}).repaired == []
    once = sched.run_once(DSN, tmp_path / "runs", rounds=3)
    assert once["repaired"] == [] and once["rounds"] == 1

    events_before = store.read_events(DSN, 0, -1, limit=500)["events"]
    recovered = broker.recover(DSN, {"local-process": dead})
    events_after = store.read_events(DSN, 0, -1, limit=500)["events"]
    assert recovered.repaired == ["op-hung:unresolved-liability"]
    assert len(events_after) == len(events_before)
    assert broker.read_operation(DSN, "op-hung")["dispatch_state"] == "unresolved"
    assert store.allocation_status(DSN, "st1")["reserved"] == 86


def test_envelope_admits_every_effect_from_post_effect_reads(tmp_path):
    _fresh_db()
    from settlement import broker, store
    from settlement.launcher_local import LocalLauncher
    from settlement.loop import Grant, admit_effect, read_measured_costs

    _study()
    launcher = LocalLauncher(tmp_path / "runs")
    granted = admit_effect(
        DSN, allocation_id="st1", operation_id="sandbox-1",
        effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 10_000, "max_output_bytes": 1024},
        attempt_id=None, kind="construction")
    assert isinstance(granted, Grant)
    status = broker.dispatch_operation(DSN, "sandbox-1",
                                       launchers={"local-process": launcher})
    assert status.dispatch_state == "observed"
    costs = read_measured_costs(DSN, "sandbox-1")
    assert costs["dispatch_state"] == "observed"
    assert len(costs["receipts"]) == 1 and costs["unknown"] == []
    status_row = store.allocation_status(DSN, "st1")
    assert status_row["consumed"] == granted.exposure
    assert status_row["reserved"] == 0


def test_insufficient_authority_refuses_without_silent_underfunding():
    _fresh_db()
    from settlement import broker
    from settlement.loop import Refusal, admit_effect

    _study(authorized=10)
    refused = admit_effect(
        DSN, allocation_id="st1", operation_id="sandbox-big",
        effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process", "argv": ["/bin/true"],
                 "timeout_ms": 60_000, "max_output_bytes": 1024},
        attempt_id=None, kind="construction")
    assert isinstance(refused, Refusal)
    assert refused.reason == "insufficient-authority"
    assert broker.read_operation(DSN, "sandbox-big") is None


def test_kill_resume_continues_same_action_identity():
    _fresh_db()
    from settlement import broker, store
    from settlement.loop import resume_state, run_boundary

    envelope = _study()
    gateway = RecordingGateway(['{"answer": 1}'])
    packet = _packet()
    before = dict(packet)

    def _propose(materialized, state):
        return {"target": "t1", "instrument": "diagnose",
                "inputs": {"model": "scripted", "prompt": "look",
                           "max_output_tokens": 16},
                "dependencies": [], "requested": {}, "hypothesis": None}

    first, _ = run_boundary(DSN, study_root="st1", allocation_id="st1",
                            packet=packet, propose=_propose, gateway=gateway)
    assert first.admission == "admitted"
    assert gateway.calls and len(gateway.calls) == 1
    operation_id = first.operations[0]
    assert broker.read_operation(DSN, operation_id)["dispatch_state"] == "observed"

    broker.ATTEMPT_WORKFLOW_RESOURCES.clear()
    resumed, _ = run_boundary(DSN, study_root="st1", allocation_id="st1",
                              packet=packet, propose=_propose, gateway=gateway)
    assert resumed.operations == [operation_id]
    assert len(gateway.calls) == 1
    assert len(store.operation_receipts(DSN, operation_id)) == 1
    assert resumed.results == first.results

    restated = resume_state(DSN, "st1")
    assert any(o["operation_id"] == operation_id for o in restated.observations)
    assert packet == before
    assert envelope.remaining(DSN) < 100_000


def test_rejected_proposal_then_correction_both_take_visible_effect():
    _fresh_db()
    from settlement import broker
    from settlement.loop import ExperienceTransition, LoopState, run_boundary

    _study()
    packet = _packet()
    state = LoopState(objective="x")
    proposed: list[str] = []

    def malformed(materialized, s):
        proposed.append("malformed")
        return {"target": "t1", "instrument": "teleport",
                "inputs": {}, "dependencies": [], "requested": {}}

    def correction(materialized, s):
        proposed.append("correction")
        return _note_propose(materialized, s)

    refused, state = run_boundary(
        DSN, study_root="st1", allocation_id="st1", packet=packet,
        propose=malformed, state=state)
    assert refused.admission == "refused:malformed-action"
    assert refused.continuation["correction"] == "correction-budget-exhausted"
    assert refused.operations == []
    assert broker.scan_prepared(DSN) == []

    exhausted, state = run_boundary(
        DSN, study_root="st1", allocation_id="st1", packet=packet,
        propose=correction, state=state)
    assert "correction" not in proposed
    assert exhausted.admission == "refused:malformed-action"
    assert exhausted.continuation["correction"] == "correction-budget-exhausted"
    assert exhausted.operations == []
    assert exhausted.results == []
    assert state.observations == []
    assert broker.scan_prepared(DSN) == []

    journaled = ExperienceTransition.read_journal(DSN, "st1")
    assert [t["admission"] for t in journaled] == [
        "refused:malformed-action", "refused:malformed-action"]


def test_sequenced_allowance_caps_construction_after_diagnostic_spend():
    from settlement.loop import ResourceEnvelope

    assert ResourceEnvelope.sequence_construction_allowance(6, 4) == 1
    assert ResourceEnvelope.sequence_construction_allowance(6, 0) == 5
    assert ResourceEnvelope.sequence_construction_allowance(2, 5) == 0


def test_zero_budget_probe_never_eats_study_lineage():
    _fresh_db()
    from settlement import store
    from settlement.loop import ResourceEnvelope

    envelope = ResourceEnvelope.bind(DSN, "st1", 1000)
    probes = envelope.probe_allowance(DSN, 50)
    before = store.allocation_status(DSN, "st1")
    refused = envelope.admit_probe(DSN, operation_id="probe-0", amount=0,
                                   probe_allocation_id=probes)
    assert refused.reason == "zero-budget-probe"
    after = store.allocation_status(DSN, "st1")
    assert (after["consumed"], after["reserved"]) == \
        (before["consumed"], before["reserved"])
    granted = envelope.admit_probe(DSN, operation_id="probe-1", amount=5,
                                   probe_allocation_id=probes)
    assert granted.allowance.amount == 5
    assert store.allocation_status(DSN, "st1")["reserved"] == before["reserved"]


def test_underfunded_study_falls_back_to_no_candidate():
    _fresh_db()
    from settlement.loop import ResourceEnvelope, run_boundary

    ResourceEnvelope.bind(DSN, "st1", 100)
    envelope = ResourceEnvelope(study_root="st1", allocation_id="st1",
                                authorized=100)
    headroom = envelope.require_learner_headroom(DSN, 2)
    assert headroom.reason == "underfunded-study"

    def _hungry(materialized, state):
        return {"target": "t1", "instrument": "diagnose",
                "inputs": {"model": "scripted", "prompt": "x" * 20000,
                           "max_output_tokens": 8000},
                "dependencies": [], "requested": {}, "hypothesis": None}

    transition, _ = run_boundary(DSN, study_root="st1", allocation_id="st1",
                                 packet=_packet(), propose=_hungry, gateway=None)
    assert transition.admission == "refused:insufficient-authority"
    assert transition.operations == []
