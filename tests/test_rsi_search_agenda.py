from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from rsi import agenda, genome, investigation, memory, search, task
from settlement import broker, db, store
from settlement.common import Command, SettlementError
from settlement.launcher_local import LocalLauncher
from test_rsi_capability_integration import _genome as _method_genome
from test_rsi_capability_integration import _qualify as _qualify_method
from test_rsi_capability_integration import _task as _method_task
from test_rsi_agenda import _charter
from test_rsi_investigate import _scenario, _worker_calls


_INTERFACE = "exploration-policy/1"


def _policy(run, tmp_path, *, action, opportunity_id=None):
    if action == "choose":
        value = {"action": action, "opportunity_id": opportunity_id}
        method = (
            "def invoke(request):\n"
            "    menu = request['value']['menu']\n"
            f"    if any(row['opportunity_id'] == {opportunity_id!r} "
            "and row['eligible'] for row in menu):\n"
            f"        return {{'value': {value!r}, 'files': {{}}}}\n"
            f"    return {{'value': {value!r}, 'files': {{}}}}\n"
        )
    elif action == "invalid":
        method = "def invoke(request):\n    return {'value': {'action': 'choose', 'opportunity_id': 'missing'}, 'files': {}}\n"
    else:
        method = f"def invoke(request):\n    return {{'value': {{'action': 'stop', 'reason': {action!r}}}, 'files': {{}}}}\n"
    organism = genome.Genome({
        "skills/explore/SKILL.md": b"---\nname: explore\ndescription: choose a prepared opportunity\n---\n",
        "skills/explore/capability.json": json.dumps({
            "schema": "rsi-capability/1", "interface": _INTERFACE,
            "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
            "effects": ["return", "solution-files"],
            "limits": {"timeout_ms": 10_000, "max_output_bytes": 65_536},
        }).encode(),
        "skills/explore/method.py": method.encode(),
    })
    genome.publish(run["dsn"], organism, parent=None, origin="p06-agenda-policy",
                   **run["roots"])
    run["checker"] = LocalLauncher(tmp_path / "policy")
    return organism, run["checker"]


def _charter_with_policy(run, agenda_id, organism, *, grant_version=1, max_turns=1):
    charter = _charter(run, agenda_id=agenda_id, max_turns=max_turns)
    charter["grant_version"] = grant_version
    charter["policy"] = {"genome": organism.digest, "name": "explore",
                         "interface": _INTERFACE, "timeout_ms": 10_000,
                         "max_output_bytes": 65_536}
    first = charter["opportunities"][0]
    first["investigation_id"] = agenda_id + "-first"
    charter["opportunities"].append({
        **first, "id": "second", "investigation_id": agenda_id + "-second",
        "question": "Does the other prepared investigation pass?",
    })
    return charter


def _grant(dsn, charter, agenda_id, *, include_policy=True):
    items = charter["opportunities"]
    genomes = {item["genome_id"] for item in items}
    if include_policy:
        genomes.add(charter["policy"]["genome"])
    store.seed_grant(dsn, Command(
        request_id=f"p06-policy-grant:{agenda_id}:{charter['grant_version']}",
        payload={
            "version": charter["grant_version"],
            "charter_text": "bounded executable exploration policy",
            "authority_grant": {
                "kind": "rsi-agenda", "agenda_id": agenda_id,
                "development_task_ids": sorted({item["task_id"] for item in items}),
                "genome_ids": sorted(genomes),
                "effects": [broker.AGENT_RUN, broker.SANDBOX_EXEC],
            },
            "envelopes": {
                "tokens": {"allocation_id": charter["allocations"]["tokens"]["id"],
                           "units": charter["allocations"]["tokens"]["units"]},
                "cpu": {"allocation_id": charter["allocations"]["cpu"]["id"],
                        "units": charter["allocations"]["cpu"]["units"]},
                "max_turns": charter["max_turns"],
            },
        }))


def _wake(run, agenda_id):
    return agenda.wake(run["dsn"], run["agent"], run["checker"], agenda_id,
                       **run["roots"])


def _policy_admission(dsn, agenda_id):
    return next(row for row in agenda.export(dsn, agenda_id)["decisions"]
                if row["kind"] == "p05.policy_admission")


def _spawn_count(launcher, operation):
    path = launcher.run_dir / (
        launcher.native_id(operation["id"], operation["execution_version"]) + ".spawns")
    return path.read_text(encoding="utf-8")


def _create(run, agenda_id, organism, *, grant_version=1, max_turns=1):
    charter = _charter_with_policy(run, agenda_id, organism,
                                   grant_version=grant_version, max_turns=max_turns)
    _grant(run["dsn"], charter, agenda_id)
    agenda.create(run["dsn"], agenda_id=agenda_id, charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])
    return charter


def test_native_policy_replays_once_and_admits_its_exact_prepared_start(
        migrated_db, tmp_path, monkeypatch):
    run = _scenario(migrated_db, tmp_path / "run", "p06-agenda-replay", "pass-first")
    organism, launcher = _policy(run, tmp_path, action="choose", opportunity_id="second")
    charter = _create(run, "p06-agenda-replay", organism)
    commit = agenda._commit_policy_choice
    interrupted = False

    def interrupt_after_policy(*args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise RuntimeError("crash after settled policy invocation")
        return commit(*args, **kwargs)

    monkeypatch.setattr(agenda, "_commit_policy_choice", interrupt_after_policy)
    with pytest.raises(RuntimeError, match="crash after settled policy invocation"):
        _wake(run, "p06-agenda-replay")

    flight = agenda.read(migrated_db, "p06-agenda-replay")["flight"]
    assert flight["kind"] == "policy"
    operation = broker.read_operation(migrated_db, flight["operation_id"])
    assert operation["settled"] is True
    assert _spawn_count(launcher, operation) == "1"
    assert _worker_calls(run["worker_log"]) == []

    monkeypatch.setattr(agenda, "_commit_policy_choice", commit)
    result = _wake(run, "p06-agenda-replay")
    assert result["status"] == "acknowledged"
    exported = agenda.export(migrated_db, "p06-agenda-replay")
    choice, = [row for row in exported["decisions"] if row["kind"] == "p05.choice"]
    assert choice["data"]["opportunity_id"] == "second"
    frame = search.load_frame(
        migrated_db, choice["data"]["frame_digest"],
        artifacts_root=run["roots"]["artifacts_root"])
    start = frame["starts"]["second"]
    p01 = investigation.export(migrated_db, start["investigation_id"])
    worker, = [row for row in p01["decisions"] if row["kind"] == "worker"]
    assert worker["data"]["visible_input"] == start["visible_input"]
    assert worker["data"]["operation_id"] == start["operation_id"]
    assert _spawn_count(launcher, operation) == "1"
    assert agenda.read(migrated_db, "p06-agenda-replay")["turns"] == 1


def test_different_executable_policies_admit_different_real_opportunities(
        migrated_db, tmp_path):
    left = _scenario(migrated_db, tmp_path / "left", "p06-policy-left", "pass-first")
    left_policy, _ = _policy(left, tmp_path / "left", action="choose", opportunity_id="first")
    _create(left, "p06-policy-left", left_policy, grant_version=1)
    assert _wake(left, "p06-policy-left")["status"] == "acknowledged"

    right = _scenario(migrated_db, tmp_path / "right", "p06-policy-right", "pass-first")
    right_policy, _ = _policy(right, tmp_path / "right", action="choose", opportunity_id="second")
    _create(right, "p06-policy-right", right_policy, grant_version=2)
    assert _wake(right, "p06-policy-right")["status"] == "acknowledged"

    left_choice, = [row for row in agenda.export(
        migrated_db, "p06-policy-left")["decisions"] if row["kind"] == "p05.choice"]
    right_choice, = [row for row in agenda.export(
        migrated_db, "p06-policy-right")["decisions"] if row["kind"] == "p05.choice"]
    assert left_choice["data"]["opportunity_id"] == "first"
    assert right_choice["data"]["opportunity_id"] == "second"
    assert len(_worker_calls(left["worker_log"])) == 1
    assert len(_worker_calls(right["worker_log"])) == 1


def test_policy_stop_closes_the_owner_without_a_p01_worker(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "run", "p06-agenda-stop", "pass-first")
    organism, _ = _policy(run, tmp_path, action="enough evidence")
    _create(run, "p06-agenda-stop", organism)

    result = _wake(run, "p06-agenda-stop")

    assert result["status"] == "stopped"
    assert agenda.read(migrated_db, "p06-agenda-stop")["flight"] is None
    assert [row["kind"] for row in agenda.export(
        migrated_db, "p06-agenda-stop")["decisions"]] == [
            "p05.policy_admission", "p05.policy_stop"]
    assert _worker_calls(run["worker_log"]) == []
    stop, = (row for row in agenda.export(
        migrated_db, "p06-agenda-stop")["decisions"]
             if row["kind"] == "p05.policy_stop")
    operation = broker.read_operation(migrated_db, stop["data"]["operation_id"])
    with db.read_connect(migrated_db) as conn:
        amount = conn.execute("SELECT amount FROM reservations WHERE id=%s",
                              (operation["reservation_id"],)).fetchone()[0]
    assert stop["data"]["operation_admitted"] is True
    assert stop["data"]["policy"]["execution_version"] == operation["execution_version"]
    assert amount == stop["data"]["policy_cpu_units"]


def test_invalid_choice_is_recorded_and_policy_admissions_are_finite(
        migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "run", "p06-agenda-invalid", "pass-first")
    organism, _ = _policy(run, tmp_path, action="invalid")
    _create(run, "p06-agenda-invalid", organism)

    first = _wake(run, "p06-agenda-invalid")
    second = _wake(run, "p06-agenda-invalid")

    assert first["status"] == "deferred"
    assert "ineligible opportunity" in first["reason"]
    assert second["status"] == "stopped"
    decisions = agenda.export(migrated_db, "p06-agenda-invalid")["decisions"]
    assert sum(row["kind"] == "p05.policy_admission" for row in decisions) == 1
    assert any(row["kind"] == "p05.policy_refusal" for row in decisions)
    assert agenda.read(migrated_db, "p06-agenda-invalid")["flight"] is None
    assert _worker_calls(run["worker_log"]) == []


def test_policy_genome_must_be_in_the_existing_agenda_grant(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "run", "p06-agenda-grant", "pass-first")
    organism, _ = _policy(run, tmp_path, action="choose", opportunity_id="first")
    charter = _charter_with_policy(run, "p06-agenda-grant", organism)
    _grant(migrated_db, charter, "p06-agenda-grant", include_policy=False)

    with pytest.raises(SettlementError, match="grant does not authorize"):
        agenda.create(migrated_db, agenda_id="p06-agenda-grant", charter=charter,
                      artifacts_root=run["roots"]["artifacts_root"])


def test_predispatch_policy_refusal_records_no_operation(migrated_db, tmp_path, monkeypatch):
    run = _scenario(migrated_db, tmp_path / "run", "p06-agenda-refusal", "pass-first")
    organism, _ = _policy(run, tmp_path, action="choose", opportunity_id="first")
    _create(run, "p06-agenda-refusal", organism)

    def refuse(*args, **kwargs):
        raise SettlementError("native policy was refused before dispatch")

    monkeypatch.setattr(agenda.capability, "invoke", refuse)
    result = _wake(run, "p06-agenda-refusal")
    refusal, = (row for row in agenda.export(migrated_db, "p06-agenda-refusal")["decisions"]
                if row["kind"] == "p05.policy_refusal")

    assert result["status"] == "deferred"
    assert refusal["data"]["operation_admitted"] is False
    assert broker.read_operation(migrated_db, refusal["data"]["operation_id"]) is None
    assert agenda.read(migrated_db, "p06-agenda-refusal")["flight"] is None
    assert _worker_calls(run["worker_log"]) == []


def test_native_method_choice_pins_the_dispatched_worker_identity(migrated_db, tmp_path):
    agenda_id = "p06-policy-native-worker"
    run = _scenario(migrated_db, tmp_path / "run", agenda_id, "pass-first")
    policy, checker = _policy(run, tmp_path, action="choose", opportunity_id="first")
    for domain in ("tokens", "cpu"):
        store.seed_allocation(migrated_db, Command(
            request_id=f"native-worker-allocation:{domain}",
            payload={"allocation_id": domain, "domain": domain, "authorized": 100_000}))

    organism = _method_genome()
    use_task = _method_task("p06-native-worker-task", 9)
    genome.publish(migrated_db, organism, parent=None, origin="p06-native-worker", **run["roots"])
    task.publish(migrated_db, use_task, **run["roots"])
    checked, retained = _qualify_method(
        (migrated_db, run["roots"], organism, checker, tmp_path))
    assert checked.passed is True and retained["status"] == "retained"

    charter = _charter(run, agenda_id=agenda_id)
    charter["allocations"] = {domain: {"id": domain, "units": 100_000}
                              for domain in ("tokens", "cpu")}
    charter["policy"] = {"genome": policy.digest, "name": "explore",
                         "interface": _INTERFACE, "timeout_ms": 10_000,
                         "max_output_bytes": 65_536}
    opportunity = charter["opportunities"][0]
    opportunity.update(task_id=use_task.digest, genome_id=organism.digest,
                       investigation_id=agenda_id + "-p01",
                       objective=use_task.instruction, timeout_ms=5_000,
                       method_request={"name": "maximum", "interface": "sequence-maximum/1",
                                       "value": [-5, 9, 2]})
    _grant(migrated_db, charter, agenda_id)
    agenda.create(migrated_db, agenda_id=agenda_id, charter=charter,
                  artifacts_root=run["roots"]["artifacts_root"])

    result = agenda.wake(migrated_db, None, checker, agenda_id, **run["roots"])

    assert result["status"] == "acknowledged"
    choice, = (row for row in agenda.export(migrated_db, agenda_id)["decisions"]
               if row["kind"] == "p05.choice")
    start = search.load_frame(
        migrated_db, choice["data"]["frame_digest"],
        artifacts_root=run["roots"]["artifacts_root"])["starts"]["first"]
    operation = broker.read_operation(migrated_db, start["operation_id"])
    assert operation["payload"]["effect"] == broker.SANDBOX_EXEC
    assert operation["attempt_id"] == start["attempt_id"]
    assert start["runtime"]["execution_version"] == operation["execution_version"]
    branch = search.capture(
        migrated_db, choice["data"]["frame_digest"], "first", **run["roots"])
    assert branch["status"] == "supported"


@pytest.mark.parametrize("mutation", ["support", "resource", "deadline"])
def test_changed_support_resource_or_deadline_blocks_the_pinned_choice(
        migrated_db, tmp_path, monkeypatch, mutation):
    run = _scenario(migrated_db, tmp_path / "run", f"p06-agenda-race-{mutation}", "pass-first")
    organism, _ = _policy(run, tmp_path, action="choose", opportunity_id="second")
    charter = _create(run, f"p06-agenda-race-{mutation}", organism)
    invoke = agenda.capability.invoke

    def invoke_then_change(dsn, launcher, genome_arg, name, request, **kwargs):
        result = invoke(dsn, launcher, genome_arg, name, request, **kwargs)
        if mutation == "support":
            memory.revise(
                dsn, claim_id=f"race-{mutation}", expected_version=0,
                text="New external support arrived during the policy run.",
                scope={"domain": "task"}, status="untested",
                artifacts_root=run["roots"]["artifacts_root"])
        elif mutation == "resource":
            store.subdivide_allocation(dsn, Command(
                request_id=f"race-resource:{charter['allocations']['cpu']['id']}",
                payload={"child_id": f"race-child:{charter['allocations']['cpu']['id']}",
                         "parent_id": charter["allocations"]["cpu"]["id"],
                         "domain": "cpu", "authorized": 1}))
        else:
            real_datetime = datetime

            class AfterDeadline(real_datetime):
                @classmethod
                def now(cls, tz=None):
                    return real_datetime.now(tz) + timedelta(days=2)

            monkeypatch.setattr(agenda, "datetime", AfterDeadline)
        return result

    monkeypatch.setattr(agenda.capability, "invoke", invoke_then_change)
    result = _wake(run, f"p06-agenda-race-{mutation}")

    decisions = agenda.export(migrated_db, f"p06-agenda-race-{mutation}")["decisions"]
    assert not any(row["kind"] == "p05.choice" for row in decisions)
    assert agenda.read(migrated_db, f"p06-agenda-race-{mutation}")["flight"] is None
    assert _worker_calls(run["worker_log"]) == []
    assert result["status"] == ("stopped" if mutation == "deadline" else "deferred")
