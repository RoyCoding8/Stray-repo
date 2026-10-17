from __future__ import annotations

import copy
import sys

import pytest
from rsi_search_fixture import bundle
from test_rsi_capability_integration import _genome, _qualify, _task
from test_rsi_investigate import _scenario
from test_rsi_search_agenda import _charter_with_policy, _grant, _policy

from rsi import agenda, genome, search, task
from settlement import broker, store
from settlement.common import Command


def test_offline_replay_does_not_relabel_an_executed_policy():
    baseline = bundle()
    baseline["results"][0]["invocation"]["method_digest"] = baseline["policy"]["method_digest"]
    assert search.recompute(baseline)["supported"] == 1
    changed = copy.deepcopy(baseline)
    for identity in (changed["policy"], changed["pinned_evaluation"]):
        identity.update(genome="another-policy", name="another-method",
                        method_digest="another-closure")

    result = search.recompute(changed)

    assert (result["supported"], result["gaps"]) == (0, 1)


def _native_agenda(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path / "run", "sol-native", "pass-first")
    policy, checker = _policy(run, tmp_path, action="choose", opportunity_id="first")
    for domain in ("tokens", "cpu"):
        store.seed_allocation(migrated_db, Command(
            request_id=f"sol-native-allocation:{domain}",
            payload={"allocation_id": domain, "domain": domain, "authorized": 100_000}))
    organism = _genome()
    item = _task("sol-native-task", 9)
    genome.publish(migrated_db, organism, parent=None, origin="sol-native", **run["roots"])
    task.publish(migrated_db, item, **run["roots"])
    checked, retained = _qualify((migrated_db, run["roots"], organism, checker, tmp_path))
    assert checked.passed is True and retained["status"] == "retained"

    def create(identity, grant_version):
        charter = _charter_with_policy(run, identity, policy, grant_version=grant_version)
        charter["opportunities"] = charter["opportunities"][:1]
        charter["allocations"] = {domain: {"id": domain, "units": 100_000}
                                  for domain in ("tokens", "cpu")}
        charter["opportunities"][0].update(
            task_id=item.digest, genome_id=organism.digest,
            objective=item.instruction, timeout_ms=5_000,
            method_request={"name": "maximum", "interface": "sequence-maximum/1",
                            "value": [-5, 9, 2]})
        _grant(migrated_db, charter, identity)
        agenda.create(migrated_db, agenda_id=identity, charter=charter,
                      artifacts_root=run["roots"]["artifacts_root"])

    return run, checker, create


def test_pending_work_rechecks_the_policy_pinned_native_runtime(
        migrated_db, tmp_path, monkeypatch):
    run, checker, create = _native_agenda(migrated_db, tmp_path)
    create("sol-baseline", 1)
    baseline = agenda.wake(migrated_db, None, checker, "sol-baseline", **run["roots"])
    assert baseline["status"] == "acknowledged"
    choice = next(row for row in agenda.export(migrated_db, "sol-baseline")["decisions"]
                  if row["kind"] == "p05.choice")
    captured = search.capture(migrated_db, choice["data"]["frame_digest"], "first", **run["roots"])
    assert captured["status"] == "supported"

    create("sol-resume", 2)
    finish = agenda._finish

    def crash_after_work_choice(*args, **kwargs):
        if kwargs["flight"].get("kind") == "work":
            raise RuntimeError("crash before native worker dispatch")
        return finish(*args, **kwargs)

    monkeypatch.setattr(agenda, "_finish", crash_after_work_choice)
    with pytest.raises(RuntimeError, match="crash before native worker dispatch"):
        agenda.wake(migrated_db, None, checker, "sol-resume", **run["roots"])
    flight = agenda.read(migrated_db, "sol-resume")["flight"]
    assert flight["kind"] == "work"
    assert broker.read_operation(migrated_db, flight["start"]["operation_id"]) is None
    assert checker.staged_python() != sys._base_executable

    monkeypatch.setattr(agenda, "_finish", finish)
    monkeypatch.setattr(checker, "staged_python", lambda: sys._base_executable)
    agenda.wake(migrated_db, None, checker, "sol-resume", **run["roots"])

    operation = broker.read_operation(migrated_db, flight["start"]["operation_id"])
    expected_runtime = flight["start"]["runtime"]["execution_version"]
    assert operation is None or operation["execution_version"] == expected_runtime
