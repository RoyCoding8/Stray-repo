from __future__ import annotations

from datetime import datetime, timedelta, timezone

from rsi import agenda
from settlement import broker, store
from settlement.common import Command
from test_rsi_investigate import _scenario


def _charter(run, *, agenda_id="p05-one", max_turns=1, priority=10):
    config = run["state"]["config"]
    token_id, cpu_id = config["token_allocation"], config["cpu_allocation"]
    return {
        "grant_version": 1,
        "objective": "Select and verify one investigation from a bounded portfolio.",
        "allocations": {
            "tokens": {"id": token_id, "units": 100_000},
            "cpu": {"id": cpu_id, "units": 100_000},
        },
        "policy": "seed/1",
        "max_turns": max_turns,
        "deadline": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "opportunities": [{
            "id": "first", "task_id": config["task"], "genome_id": config["genome"],
            "investigation_id": run["state"]["investigation_id"],
            "objective": run["state"]["objective"], "question": "Does the solution pass?",
            "priority": priority, "resource_ceilings": {"tokens": 5_000, "cpu": 200},
            "timeout_ms": 30_000, "max_steps": 2,
            "expected_observation": "A pristine verifier result.",
            "stop_condition": "Pass or use the finite step cap.",
        }],
    }


def _grant(migrated_db, charter, agenda_id="p05-one"):
    item, = charter["opportunities"]
    store.seed_grant(migrated_db, Command(
        request_id="p05-grant:" + agenda_id,
        payload={
            "version": charter["grant_version"],
            "charter_text": "bounded P05 fixture grant",
            "authority_grant": {
                "kind": "rsi-agenda", "agenda_id": agenda_id,
                "development_task_ids": [item["task_id"]],
                "genome_ids": [item["genome_id"]],
                "effects": [broker.AGENT_RUN, broker.SANDBOX_EXEC],
            },
            "envelopes": {
                "tokens": {"allocation_id": charter["allocations"]["tokens"]["id"], "units": 100_000},
                "cpu": {"allocation_id": charter["allocations"]["cpu"]["id"], "units": 100_000},
                "max_turns": charter["max_turns"],
            },
        }))


def test_agenda_persists_choice_runs_p01_and_exports_exact_ack(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "p01", "p05-existing", "pass-first")
    charter = _charter(run)
    _grant(migrated_db, charter)
    created = agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                            artifacts_root=run["roots"]["artifacts_root"])
    assert created["agenda_id"] == "p05-one"
    assert agenda.create(migrated_db, agenda_id="p05-one", charter=charter,
                         artifacts_root=run["roots"]["artifacts_root"]) == created

    result = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-one",
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"])

    assert result["status"] == "acknowledged"
    assert result["investigation"]["status"] == "completed"
    assert result["acknowledgement"]["observation"]["passed"] is True
    exported = agenda.export(migrated_db, "p05-one")
    assert [item["kind"] for item in exported["decisions"]] == ["p05.choice", "p05.ack"]
    assert exported["agenda"]["flight"] is None
    assert exported["agenda"]["turns"] == 1
    assert agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-one",
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"])["status"] == "complete"
