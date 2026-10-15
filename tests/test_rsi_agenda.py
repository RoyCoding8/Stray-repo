from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_rsi_investigate import _scenario

from rsi import agenda, experience, investigate, memory, task
from rsi.investigation import export as investigation_export
from settlement import broker, db, store
from settlement.common import Command, SettlementError


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
        "deadline": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
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


def _grant(migrated_db, charter, agenda_id="p05-one", *, envelope_turns=None):
    items = charter["opportunities"]
    store.seed_grant(migrated_db, Command(
        request_id=f"p05-grant:{agenda_id}:{charter['grant_version']}",
        payload={
            "version": charter["grant_version"],
            "charter_text": "bounded P05 fixture grant",
            "authority_grant": {
                "kind": "rsi-agenda", "agenda_id": agenda_id,
                "development_task_ids": sorted({item["task_id"] for item in items}),
                "genome_ids": sorted({item["genome_id"] for item in items}),
                "effects": [broker.AGENT_RUN, broker.SANDBOX_EXEC],
            },
            "envelopes": {
                "tokens": {"allocation_id": charter["allocations"]["tokens"]["id"], "units": 100_000},
                "cpu": {"allocation_id": charter["allocations"]["cpu"]["id"], "units": 100_000},
                "max_turns": charter["max_turns"] if envelope_turns is None else envelope_turns,
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


def test_stale_source_choice_can_be_rederived_on_a_later_wake(migrated_db, tmp_path, monkeypatch):
    from test_rsi_investigate import _worker_calls

    run = _scenario(migrated_db, tmp_path / "p01", "p05-race", "repair-after-feedback")
    charter = _charter(run, agenda_id="p05-race", max_turns=2)
    _grant(migrated_db, charter, "p05-race")
    agenda.create(migrated_db, agenda_id="p05-race", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    original = agenda._commit_choice
    raced = False

    def advance_source_then_commit(dsn, agenda_id, state, snapshot, choice):
        nonlocal raced
        if not raced:
            raced = True
            investigate.step(dsn, run["agent"], run["checker"], "p05-race", **run["roots"])
        return original(dsn, agenda_id, state, snapshot, choice)

    monkeypatch.setattr(agenda, "_commit_choice", advance_source_then_commit)
    first = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-race",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])
    assert first["status"] == "stale"
    assert len(_worker_calls(run["worker_log"])) == 1

    second = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-race",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])
    assert second["status"] == "acknowledged"
    assert second["acknowledgement"]["observation"]["passed"] is True
    assert len(_worker_calls(run["worker_log"])) == 2
    exported = agenda.export(migrated_db, "p05-race")
    assert [row["kind"] for row in exported["decisions"]] == ["p05.choice", "p05.ack"]


def test_definitive_pre_dispatch_refusal_closes_pinned_flight(migrated_db, tmp_path, monkeypatch):
    from test_rsi_investigate import _worker_calls

    run = _scenario(migrated_db, tmp_path / "p01", "p05-refusal", "pass-first")
    charter = _charter(run, agenda_id="p05-refusal")
    _grant(migrated_db, charter, "p05-refusal")
    agenda.create(migrated_db, agenda_id="p05-refusal", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    original = agenda._commit_choice

    def revoke_root_after_choice(dsn, agenda_id, state, snapshot, choice):
        flight = original(dsn, agenda_id, state, snapshot, choice)
        with db.connect(dsn) as conn:
            conn.execute("UPDATE allocations SET authorized=0 WHERE id=%s",
                         (charter["allocations"]["tokens"]["id"],))
        return flight

    monkeypatch.setattr(agenda, "_commit_choice", revoke_root_after_choice)
    result = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-refusal",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])

    assert result["status"] == "deferred"
    assert "definitively refused before dispatch" in result["reason"]
    assert agenda.read(migrated_db, "p05-refusal")["flight"] is None
    assert agenda.read(migrated_db, "p05-refusal")["turns"] == 1
    assert investigate.read(migrated_db, "p05-refusal")["last_observation"]["status"] == "refused"
    assert _worker_calls(run["worker_log"]) == []


def test_missing_catalogue_source_keeps_dispatched_flight_pinned(
    migrated_db, tmp_path, monkeypatch
):
    from test_rsi_investigate import _worker_calls

    run = _scenario(migrated_db, tmp_path / "p01", "p05-source-gap", "pass-first")
    charter = _charter(run, agenda_id="p05-source-gap")
    _grant(migrated_db, charter, "p05-source-gap")
    agenda.create(migrated_db, agenda_id="p05-source-gap", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    def interrupt_before_verification(*args, **kwargs):
        raise RuntimeError("interrupted after worker dispatch")

    verify = investigate.verifier.verify_episode
    monkeypatch.setattr(investigate.verifier, "verify_episode", interrupt_before_verification)
    with pytest.raises(RuntimeError, match="interrupted after worker dispatch"):
        agenda.wake(
            migrated_db, run["agent"], run["checker"], "p05-source-gap",
            staging_root=run["roots"]["staging_root"],
            artifacts_root=run["roots"]["artifacts_root"])

    before = agenda.read(migrated_db, "p05-source-gap")
    pending = investigate.read(migrated_db, "p05-source-gap")
    assert before["flight"] is not None
    assert pending["status"] == "pending"
    operation_id = pending["pending_decision"]["operation_id"]
    assert len(_worker_calls(run["worker_log"])) == 1

    load_task = task.load

    def unavailable_task(dsn, artifacts_root, digest):
        if digest == run["candidate"].digest:
            raise task.TaskError("published task artifact is unavailable")
        return load_task(dsn, artifacts_root, digest)

    monkeypatch.setattr(task, "load", unavailable_task)
    missing = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-source-gap",
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"])

    assert missing["status"] == "pending"
    assert "catalogue source is unavailable" in missing["reason"]
    assert agenda.read(migrated_db, "p05-source-gap")["flight"] == before["flight"]
    assert investigate.read(migrated_db, "p05-source-gap")["pending_decision"][
        "operation_id"] == operation_id
    assert len(_worker_calls(run["worker_log"])) == 1

    monkeypatch.setattr(task, "load", load_task)
    package_path = run["roots"]["artifacts_root"] / run["candidate"].digest
    package = package_path.read_bytes()
    package_path.unlink()
    try:
        absent = agenda.wake(
            migrated_db, run["agent"], run["checker"], "p05-source-gap",
            staging_root=run["roots"]["staging_root"],
            artifacts_root=run["roots"]["artifacts_root"])
    finally:
        package_path.write_bytes(package)
    assert absent["status"] == "pending"
    assert agenda.read(migrated_db, "p05-source-gap")["flight"] == before["flight"]
    assert len(_worker_calls(run["worker_log"])) == 1

    monkeypatch.setattr(investigate.verifier, "verify_episode", verify)
    resumed = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-source-gap",
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"])
    assert resumed["status"] == "acknowledged"
    assert resumed["acknowledgement"]["observation"]["passed"] is True
    assert len(_worker_calls(run["worker_log"])) == 1
    assert [row["kind"] for row in agenda.export(
        migrated_db, "p05-source-gap")["decisions"]] == ["p05.choice", "p05.ack"]


def test_ranked_competing_investigations_share_one_granted_root(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "p01", "p05-first", "repair-after-feedback")
    config = run["state"]["config"]
    investigate.create(
        migrated_db, run["agent"], run["seed"], investigation_id="p05-second",
        task=run["candidate"], token_allocation=config["token_allocation"],
        cpu_allocation=config["cpu_allocation"], max_steps=2, timeout_ms=30_000,
        token_ceiling=5_000, objective=run["state"]["objective"], **run["roots"])
    charter = _charter(run, agenda_id="p05-portfolio", max_turns=2)
    charter["opportunities"].append({
        **charter["opportunities"][0], "id": "second", "investigation_id": "p05-second",
        "question": "Does the competing investigation pass?",
    })
    _grant(migrated_db, charter, "p05-portfolio")
    agenda.create(migrated_db, agenda_id="p05-portfolio", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    first = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-portfolio",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])
    second = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-portfolio",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])

    assert first["status"] == second["status"] == "acknowledged"
    exported = agenda.export(migrated_db, "p05-portfolio")
    choices = [row["data"]["opportunity_id"] for row in exported["decisions"]
               if row["kind"] == "p05.choice"]
    assert choices == ["first", "second"]
    assert exported["agenda"]["turns"] == 2
    attempts = [first["acknowledgement"]["attempt_id"],
                second["acknowledgement"]["attempt_id"]]
    with db.connect(migrated_db) as conn:
        used = {row[0] for row in conn.execute(
            "SELECT DISTINCT allocation_id FROM operations WHERE attempt_id=ANY(%s)",
            (attempts,)).fetchall()}
    assert used == {config["token_allocation"], config["cpu_allocation"]}


def test_grant_turn_envelope_and_allocation_owner_are_authoritative(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "p01", "p05-owner", "pass-first")
    charter = _charter(run, agenda_id="p05-turn-cap", max_turns=2)
    _grant(migrated_db, charter, "p05-turn-cap", envelope_turns=1)
    with pytest.raises(SettlementError, match="does not authorize this catalogue"):
        agenda.create(migrated_db, agenda_id="p05-turn-cap", charter=charter,
                      artifacts_root=run["roots"]["artifacts_root"])

    charter["grant_version"] = 2
    _grant(migrated_db, charter, "p05-owner", envelope_turns=2)
    with db.connect(migrated_db) as conn:
        conn.execute("UPDATE allocations SET owner_scope='another-agenda' WHERE id=%s",
                     (charter["allocations"]["tokens"]["id"],))
    with pytest.raises(SettlementError, match="authorized root pool"):
        agenda.create(migrated_db, agenda_id="p05-owner", charter=charter,
                      artifacts_root=run["roots"]["artifacts_root"])


def test_missing_source_is_deferred_without_effect(migrated_db, tmp_path):
    from test_rsi_investigate import _worker_calls

    run = _scenario(migrated_db, tmp_path / "p01", "p05-unavailable", "pass-first")
    charter = _charter(run, agenda_id="p05-unavailable")
    missing = replace(run["candidate"], name="not-yet-published")
    charter["opportunities"][0]["task_id"] = missing.digest
    _grant(migrated_db, charter, "p05-unavailable")
    agenda.create(migrated_db, agenda_id="p05-unavailable", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    result = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-unavailable",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])
    assert result["status"] == "deferred"
    assert "source is unavailable" in result["ranked"][0]["reason"]
    assert agenda.read(migrated_db, "p05-unavailable")["turns"] == 0
    assert _worker_calls(run["worker_log"]) == []


@pytest.mark.parametrize("outcome", ["context_outcome", "capability_outcome"])
def test_p01_pre_effect_outcome_keeps_committed_flight(migrated_db, tmp_path, monkeypatch, outcome):
    from test_rsi_investigate import _worker_calls

    run = _scenario(migrated_db, tmp_path / "p01", "p05-outcome-" + outcome, "pass-first")
    agenda_id = "p05-outcome-" + outcome
    charter = _charter(run, agenda_id=agenda_id)
    _grant(migrated_db, charter, agenda_id)
    agenda.create(migrated_db, agenda_id=agenda_id, charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    monkeypatch.setattr(agenda, "_ensure_p01", lambda *_args, **_kwargs: {
        outcome: {"status": "needs_information"}})

    result = agenda.wake(
        migrated_db, run["agent"], run["checker"], agenda_id,
        staging_root=run["roots"]["staging_root"],
        artifacts_root=run["roots"]["artifacts_root"])

    assert result["status"] == "pending"
    assert agenda.read(migrated_db, agenda_id)["flight"] is not None
    assert [row["kind"] for row in agenda.export(
        migrated_db, agenda_id)["decisions"]] == ["p05.choice"]
    assert _worker_calls(run["worker_log"]) == []


def test_insufficient_shared_root_defers_without_effect(migrated_db, tmp_path):
    from test_rsi_investigate import _worker_calls

    run = _scenario(migrated_db, tmp_path / "p01", "p05-budget", "pass-first")
    charter = _charter(run, agenda_id="p05-budget")
    _grant(migrated_db, charter, "p05-budget")
    agenda.create(migrated_db, agenda_id="p05-budget", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    with db.connect(migrated_db) as conn:
        conn.execute("UPDATE allocations SET authorized=0 WHERE id=%s",
                     (charter["allocations"]["tokens"]["id"],))

    result = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-budget",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])

    assert result["status"] == "deferred"
    assert "token root has insufficient free units" in result["ranked"][0]["reason"]
    assert agenda.read(migrated_db, "p05-budget")["turns"] == 0
    assert _worker_calls(run["worker_log"]) == []


def test_adaptive_scope_probe_requires_checked_later_use_of_visible_lesson(
    migrated_db, tmp_path
):
    origin = _scenario(migrated_db, tmp_path / "origin", "p05-lesson-origin", "pass-first")
    origin_result = investigate.step(
        migrated_db, origin["agent"], origin["checker"], "p05-lesson-origin", **origin["roots"])
    experience.capture_investigation(
        migrated_db, "p05-lesson-origin", artifacts_root=origin["roots"]["artifacts_root"])
    origin_observation, = investigation_export(migrated_db, "p05-lesson-origin")["observations"]
    lesson = memory.revise(
        migrated_db, claim_id="p05-checked-lesson", expected_version=0,
        text="Use addition instead of subtraction.", scope={"domain": "task"},
        status="supported", support=(origin_observation["id"],),
        artifacts_root=origin["roots"]["artifacts_root"])
    assert origin_result["last_observation"]["passed"] is True

    run = _scenario(migrated_db, tmp_path / "later", "p05-later-source", "repair-after-feedback")
    # P02 verifies support artifacts from the same learner-visible root used
    # to publish this later campaign's task sources.
    roots = {**run["roots"], "artifacts_root": origin["roots"]["artifacts_root"]}
    learner_view = memory.query(
        migrated_db, purpose="task: " + run["state"]["objective"],
        investigation_id="p05-later-source", scope={"domain": "task"},
        claim_ids=[lesson["claim_id"]], artifacts_root=roots["artifacts_root"], limit=1)
    assert [(item["claim_id"], item["version"]) for item in learner_view["claims"]] == [
        (lesson["claim_id"], lesson["version"])], learner_view
    probe_task = replace(
        run["candidate"], name="add-four-six",
        instruction="Implement add(4, 6) so it returns 10.",
        verifier={"test_add.py": (
            b"import unittest\nfrom calc import add\n"
            b"class AddTests(unittest.TestCase):\n"
            b"    def test_add(self):\n"
            b"        self.assertEqual(add(4, 6), 10)\n")},
        reference={"calc.py": b"def add(a, b):\n    return a + b\n"})
    task.publish(migrated_db, run["candidate"], **roots)
    task.publish(migrated_db, probe_task, **roots)
    config = run["state"]["config"]
    source = {
        "id": "later-use", "task_id": run["candidate"].digest,
        "genome_id": config["genome"], "objective": run["state"]["objective"],
        "question": "Does the later use pass?", "priority": 5,
        "resource_ceilings": {"tokens": 5_000, "cpu": 200},
        "timeout_ms": 30_000, "max_steps": 1,
        "expected_observation": "A checked later-use result.",
        "stop_condition": "One checked use.",
    }
    probe = {
        **source, "id": "changed-input", "task_id": probe_task.digest,
        "objective": probe_task.instruction, "question": "Does the lesson transfer?",
        "scope_probe": {
            "source_opportunity_id": "later-use",
            "lesson_refs": [{"claim_id": lesson["claim_id"], "version": lesson["version"]}],
            "changed_condition": "The addends changed from (2, 3) to (4, 6).",
            "competing_explanations": ["the lesson transfers", "the original result was task-specific"],
        },
    }
    charter = {
        "grant_version": 1, "objective": "Test one checked lesson on a changed task.",
        "allocations": {
            "tokens": {"id": config["token_allocation"], "units": 100_000},
            "cpu": {"id": config["cpu_allocation"], "units": 100_000},
        },
        "policy": "adaptive/1", "max_turns": 2,
        "deadline": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "opportunities": [source, probe],
    }
    _grant(migrated_db, charter, "p05-scope")
    agenda.create(migrated_db, agenda_id="p05-scope", charter=charter,
                  artifacts_root=roots["artifacts_root"])

    source_result = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-scope",
        staging_root=roots["staging_root"], artifacts_root=roots["artifacts_root"])
    assert source_result["status"] == "acknowledged", source_result.get("reason")
    assert source_result["investigation"]["last_observation"]["passed"] is False

    probe_result = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-scope",
        staging_root=roots["staging_root"], artifacts_root=roots["artifacts_root"])
    assert probe_result["status"] == "acknowledged"
    assert probe_result["opportunity_id"] == "changed-input"
    assert probe_result["acknowledgement"]["observation"]["passed"] is False
    probe_history = investigation_export(
        migrated_db, probe_result["investigation"]["investigation_id"])
    visible_claims = probe_history["decisions"][0]["data"]["visible_input"][
        "context_packet"]["memory_view"]["claims"]
    assert {(item["claim_id"], item["version"]) for item in visible_claims} == {
        (lesson["claim_id"], lesson["version"])}
    choices = [row["data"]["opportunity_id"]
               for row in agenda.export(migrated_db, "p05-scope")["decisions"]
               if row["kind"] == "p05.choice"]
    assert choices == ["later-use", "changed-input"]


def test_unrelated_memory_revision_does_not_buy_an_agenda_turn(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "p01", "p05-unrelated-clock", "pass-first")
    charter = _charter(run, agenda_id="p05-unrelated-clock", max_turns=2)
    charter["opportunities"][0].pop("investigation_id")
    missing = replace(run["candidate"], name="not-yet-published")
    charter["opportunities"][0]["task_id"] = missing.digest
    _grant(migrated_db, charter, "p05-unrelated-clock")
    agenda.create(migrated_db, agenda_id="p05-unrelated-clock", charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    first = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-unrelated-clock",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])
    assert first["status"] == "deferred"
    before = agenda.read(migrated_db, "p05-unrelated-clock")
    origin = investigate.step(
        migrated_db, run["agent"], run["checker"], "p05-unrelated-clock", **run["roots"])
    experience.capture_investigation(
        migrated_db, "p05-unrelated-clock", artifacts_root=run["roots"]["artifacts_root"])
    observation, = investigation_export(migrated_db, "p05-unrelated-clock")["observations"]
    memory.revise(
        migrated_db, claim_id="unrelated-p05-claim", expected_version=0,
        text="An unrelated checked fact.", scope={"domain": "task"},
        status="supported", support=(observation["id"],),
        artifacts_root=run["roots"]["artifacts_root"])

    after_unrelated_claim = agenda.wake(
        migrated_db, run["agent"], run["checker"], "p05-unrelated-clock",
        staging_root=run["roots"]["staging_root"], artifacts_root=run["roots"]["artifacts_root"])
    after = agenda.read(migrated_db, "p05-unrelated-clock")
    with db.connect(migrated_db) as conn:
        memory_revision = conn.execute(
            "SELECT revision FROM rsi_memory_clock WHERE id=1").fetchone()[0]
    assert origin["last_observation"]["passed"] is True
    assert after_unrelated_claim["status"] == "deferred"
    assert after["revision"] == before["revision"]
    assert after["turns"] == 0
    assert after["memory_revision"] == memory_revision
