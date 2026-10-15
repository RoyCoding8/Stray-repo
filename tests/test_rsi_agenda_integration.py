from __future__ import annotations

from datetime import UTC, datetime, timedelta

from test_rsi_agenda import _grant
from test_rsi_capability_integration import _genome, _qualify, _task
from test_rsi_investigate import _scenario, _worker_calls

from rsi import agenda, investigate, task
from settlement import broker, store
from settlement.common import Command
from settlement.launcher_local import LocalLauncher


def test_pinned_p01_revision_replays_its_observation_without_a_new_worker(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path / "p01", "p05-replay", "repair-after-feedback")
    target_revision = run["state"]["revision"]

    checked_failure = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p05-replay",
        target_revision=target_revision, **run["roots"]
    )
    before_replay = len(_worker_calls(run["worker_log"]))
    replayed = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p05-replay",
        target_revision=target_revision, **run["roots"]
    )

    assert checked_failure["status"] == "ready"
    assert checked_failure["last_observation"]["passed"] is False
    assert replayed["revision"] == checked_failure["revision"]
    assert replayed["last_observation"] == checked_failure["last_observation"]
    assert len(_worker_calls(run["worker_log"])) == before_replay == 1

    completed = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p05-replay", **run["roots"]
    )
    assert completed["status"] == "completed"
    assert len(_worker_calls(run["worker_log"])) == 2


def test_retained_native_method_triggers_and_runs_agenda_instrument(
    migrated_db, tmp_path
):
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    for domain in ("cpu", "tokens"):
        store.seed_allocation(migrated_db, Command(
            request_id="p05-instrument-" + domain,
            payload={"allocation_id": domain, "domain": domain, "authorized": 100_000}))
    candidate = _genome()
    task_item = _task("p05-instrument-use", 9)
    from rsi import genome

    genome.publish(migrated_db, candidate, parent=None,
                   origin="independent-authored-test", **roots)
    task.publish(migrated_db, task_item, **roots)
    env = (migrated_db, roots, candidate, LocalLauncher(tmp_path / "native"), tmp_path)
    opportunity = {
        "id": "maximum-use", "task_id": task_item.digest, "genome_id": candidate.digest,
        "objective": task_item.instruction, "question": "Does retained maximum pass?",
        "priority": 5, "resource_ceilings": {"tokens": 5_000, "cpu": 200},
        "timeout_ms": 5_000, "max_steps": 1,
        "expected_observation": "A passing pristine verifier result.",
        "stop_condition": "One checked method use.",
        "method_request": {"name": "maximum", "interface": "sequence-maximum/1",
                           "value": [-5, 9, 2]},
    }
    charter = {
        "grant_version": 1, "objective": "Use retained maximum capability.",
        "allocations": {"tokens": {"id": "tokens", "units": 100_000},
                        "cpu": {"id": "cpu", "units": 100_000}},
        "policy": "adaptive/1", "max_turns": 1,
        "deadline": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "opportunities": [opportunity],
    }
    _grant(migrated_db, charter, "p05-instrument")
    agenda.create(migrated_db, agenda_id="p05-instrument", charter=charter,
                  artifacts_root=roots["artifacts_root"])

    before_retention = agenda.wake(
        migrated_db, None, env[3], "p05-instrument", **roots)
    assert before_retention["status"] == "deferred"
    assert before_retention["ranked"][0]["reason"].startswith("no checked retention")
    assert agenda.read(migrated_db, "p05-instrument")["turns"] == 0

    checked, retained = _qualify(env)
    assert checked.passed is True
    assert retained["status"] == "retained"

    after_retention = agenda.wake(
        migrated_db, None, env[3], "p05-instrument", **roots)
    assert after_retention["status"] == "acknowledged"
    assert after_retention["investigation"]["last_observation"]["passed"] is True
    assert after_retention["acknowledgement"]["receipts"]["worker"]
    assert after_retention["acknowledgement"]["receipts"]["verifier"]
    choice, = [row for row in agenda.export(migrated_db, "p05-instrument")["decisions"]
               if row["kind"] == "p05.choice"]
    assert choice["data"]["ranked"][0]["rank_reason"] == "policy: adaptive/1 triggered instrument"
    operation = broker.read_operation(
        migrated_db, after_retention["investigation"]["last_observation"]["episode"])
    assert operation["payload"]["effect"] == broker.SANDBOX_EXEC
