from __future__ import annotations

import uuid

import pytest

from settlement import agenda, broker, steward, store
from settlement.common import Command, ResultCode, SettlementError


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def test_seed_rotation_is_fair_and_stable(migrated_db):
    pending = [{"id": f"p{i}", "seed_class": c}
               for i, c in enumerate(["speculative", "bottleneck", "transfer",
                                      "instrument-gaps", "bottleneck"])]
    first = agenda.seed_order(pending, cursor=0)
    assert [p["id"] for p in first["ordered"]] == ["p1", "p2", "p3", "p0", "p4"]
    again = agenda.seed_order(list(pending), cursor=0)
    assert [p["id"] for p in again["ordered"]] == [p["id"] for p in first["ordered"]]
    with pytest.raises(SettlementError):
        agenda.seed_order([{"id": "x", "seed_class": "fashionable"}])


def test_frontier_proposal_requires_caps_and_renewal_names_change():
    good = agenda.propose_frontier("bottleneck", "q", "h", "b", "o", 50, "d")
    assert good["cap"] == 50
    with pytest.raises(SettlementError):
        agenda.propose_frontier("bottleneck", "q", "h", "b", "o", 0, "d")
    with pytest.raises(SettlementError):
        agenda.propose_frontier("bottleneck", "", "h", "b", "o", 50, "d")
    renewed = agenda.renew_proposal(good, "the transfer test failed on group 2")
    assert renewed["renewal_changed"].startswith("the transfer")
    with pytest.raises(SettlementError):
        agenda.renew_proposal(good, "  ")


def test_team_proposal_states_benefit_and_commits_before_reveal():
    with pytest.raises(SettlementError):
        agenda.propose_team("", ["a", "b"])
    with pytest.raises(SettlementError):
        agenda.propose_team("faster", ["solo"])
    team = agenda.propose_team("separable branches", ["a", "b"], ["corpus-v1"])
    assert not agenda.reveal_allowed(team)
    agenda.commit_member_result(team, "a", "obs-1")
    assert not agenda.reveal_allowed(team)
    agenda.commit_member_result(team, "b", "obs-2")
    assert agenda.reveal_allowed(team)


def test_repair_scan_reconciles_stranded_dispatching_op(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                                  "allocation_id": "a1"}))
    # The operation names the attempt's allocation. An attempt-bound
    # operation with no allocation of its own is refused at prepare, so the
    # stranded `dispatching` state this scan reconciles would not exist.
    store.prepare_operation(dsn, _cmd({"operation_id": "op1", "attempt_id": "w1",
                                       "allocation_id": "a1",
                                       "operation": {"effect": "note"}}))
    assert store.advance_dispatch(dsn, _cmd({"operation_id": "op1"})).code == ResultCode.APPLIED

    agenda.repair_scan(dsn, {})

    # The scan leaves the operation `unresolved`, holding its exposure rather
    # than guessing. An `unresolved-liability` decision is deliberately not
    # reported as a repair: nothing was recovered, and listing it as one
    # would claim a settlement that did not happen.
    reconciled = broker.read_operation(dsn, "op1")
    assert reconciled["dispatch_state"] == "unresolved"
    assert reconciled["reconcile_state"] == "unresolved"


def test_wakeups_fire_on_completed_ops_and_due_deadlines(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                                  "allocation_id": "a1"}))
    store.complete_attempt(dsn, _cmd({"attempt_id": "w1", "outcome": "completed"}))
    first = agenda.collect_wakeups(dsn, messages=[{"id": "m1", "text": "operator ping"}])
    kinds = {w["kind"] for w in first["wakeups"]}
    assert {"event", "completed-op", "message"} <= kinds
    second = agenda.collect_wakeups(dsn, cursor_epoch=first["cursor_epoch"],
                                    cursor_ordinal=first["cursor_ordinal"])
    assert second["wakeups"] == []


def test_capacity_scopes_are_separate_with_protected_supervision(migrated_db):
    dsn = migrated_db
    agenda.ensure_capacity(dsn, {"obligations": 60, "development": 30, "supervision": 10})
    view = agenda.capacity_view(dsn)
    assert set(view) == {"obligations", "development", "supervision"}
    assert view["supervision"]["available"] == 10
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    refused = agenda.admit_task(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                                           "allocation_id": "agenda-root-supervision",
                                           "kind": "task"}))
    assert refused.code == ResultCode.INSUFFICIENT_RESOURCES
    assert agenda.supervision_available(dsn) == 10


def test_agenda_snapshot_reads_durable_records(migrated_db):
    dsn = migrated_db
    agenda.ensure_capacity(dsn)
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    snap = agenda.agenda_snapshot(dsn)
    assert snap["obligations"] == 1
    assert snap["capacity"]["development"]["available"] == 1000
