from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from rsi import experience, genome, investigate, task
from settlement import store
from settlement.common import Command, SettlementError
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fixtures" / "fake_investigate.py"


def _cmd(request_id: str, payload: dict) -> Command:
    return Command(request_id=request_id, payload=payload)


def _task(split: str = "dev") -> task.Task:
    return task.Task(
        "memory-add", split, "Implement add so it returns the sum.",
        {"calc.py": b"def add(a, b):\n    return 0\n"},
        {"test_add.py": b"import unittest\nfrom calc import add\n"
                         b"class AddTests(unittest.TestCase):\n"
                         b"    def test_add(self):\n"
                         b"        self.assertEqual(add(2, 3), 5)\n"},
        {"calc.py": b"def add(a, b):\n    return a + b\n"},
        ("test_add.py",),
    )


def _scenario(dsn: str, tmp_path: Path, investigation_id: str):
    stage = tmp_path / "stage"
    root = tmp_path / "artifacts"
    stage.mkdir(parents=True)
    root.mkdir()
    roots = {"staging_root": stage, "artifacts_root": root}
    candidate = _task()
    seed = genome.Genome({"AGENTS.md": b"Work only on the assigned task.\n"})
    genome.publish(dsn, seed, parent=None, origin="p02-test", **roots)
    task.publish(dsn, candidate, **roots)
    store.seed_allocation(dsn, _cmd("memory-token-" + investigation_id, {
        "allocation_id": "memory-tokens-" + investigation_id,
        "domain": "tokens", "authorized": 100_000,
    }))
    store.seed_allocation(dsn, _cmd("memory-cpu-" + investigation_id, {
        "allocation_id": "memory-cpu-" + investigation_id,
        "domain": "cpu", "authorized": 100_000,
    }))
    agent = CodexLauncher(
        tmp_path / "runs",
        codex_cmd=[sys.executable, str(FAKE), str(tmp_path / "worker.jsonl"),
                   "repair-after-feedback"],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS,
    )
    checker = LocalLauncher(tmp_path / "verifiers")
    investigate.create(
        dsn, agent, seed, investigation_id=investigation_id, task=candidate,
        token_allocation="memory-tokens-" + investigation_id,
        cpu_allocation="memory-cpu-" + investigation_id, max_steps=2,
        timeout_ms=30_000, token_ceiling=5_000, **roots,
    )
    return {"dsn": dsn, "agent": agent, "checker": checker,
            "investigation_id": investigation_id, "roots": roots,
            "task": candidate}


def _observe(run: dict) -> list[dict]:
    investigate.step(run["dsn"], run["agent"], run["checker"],
                     run["investigation_id"], **run["roots"])
    return investigate.export(run["dsn"], run["investigation_id"])["observations"]


def test_capture_is_idempotent_and_resolves_the_same_committed_revision(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path, "memory-revision")
    first = _observe(run)[0]
    captured_first = experience.capture_investigation(
        migrated_db, run["investigation_id"], artifacts_root=run["roots"]["artifacts_root"])
    first_ref, = captured_first
    assert first_ref["observation_id"] == first["id"]
    assert first_ref["revision"] == 1

    second = _observe(run)[1]
    captured = experience.capture_investigation(
        migrated_db, run["investigation_id"], artifacts_root=run["roots"]["artifacts_root"])
    assert [item["revision"] for item in captured] == [1, 2]
    assert experience.capture(
        migrated_db, first["id"], artifacts_root=run["roots"]["artifacts_root"]
    ) == first_ref

    old = experience.resolve(
        migrated_db, [first["id"], second["id"]], artifacts_root=run["roots"]["artifacts_root"],
        revision=1)
    assert old["revision"] == 1
    assert [item["observation_id"] for item in old["observations"]] == [first["id"]]
    assert old["observations"][0]["content"] == {
        "task_instruction": "Implement add so it returns the sum.",
        "status": "failed", "passed": False,
    }
    assert set(old["observations"][0]["identities"]) == {
        "decision_id", "attempt_id", "worker_operation_id", "task_digest",
        "evaluator_version", "verifier_operation_id",
    }
    assert len(old["missing_information"]) == 1
    assert old["missing_information"][0]["observation_id"] == second["id"]
    assert "test_add.py" not in str(old)
    assert "return a + b" not in str(old)

    current = experience.resolve(
        migrated_db, [first["id"], second["id"]], artifacts_root=run["roots"]["artifacts_root"])
    assert [item["content"]["status"] for item in current["observations"]] == [
        "failed", "passed"]
    assert [item["content"]["passed"] for item in current["observations"]] == [False, True]

    env = os.environ.copy()
    env["SETTLEMENT_DSN"] = migrated_db
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT)))
    script = (
        "from rsi.experience import resolve; import json, sys; "
        "r=resolve(sys.argv[1], [int(sys.argv[2]), int(sys.argv[3])], "
        "artifacts_root=sys.argv[4], revision=1); "
        "print(json.dumps(r, sort_keys=True))"
    )
    restarted = subprocess.run(
        [sys.executable, "-c", script, migrated_db, str(first["id"]),
         str(second["id"]), str(run["roots"]["artifacts_root"])],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True, timeout=30,
    )
    assert '"revision": 1' in restarted.stdout
    assert f'"observation_id": {first["id"]}' in restarted.stdout
    assert f'"observation_id": {second["id"]}' in restarted.stdout


def test_anchor_split_with_identical_instruction_is_not_captured(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path, "memory-anchor")
    observation, = _observe(run)
    with store.db.connect(migrated_db) as conn:
        conn.execute("UPDATE rsi_tasks SET split = 'anchor' WHERE digest = %s",
                     (run["task"].digest,))
        conn.commit()

    with pytest.raises(SettlementError, match="development-task|P01"):
        experience.capture(migrated_db, observation["id"],
                           artifacts_root=run["roots"]["artifacts_root"])


def test_protected_solution_ancestry_is_rejected_without_rendering_details(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path, "memory-protected")
    observation, = _observe(run)
    solution = observation["content"]["solution"]
    with store.db.connect(migrated_db) as conn:
        conn.execute("UPDATE artifact_versions SET access_label = 'hidden' WHERE digest = %s",
                     (solution,))
        conn.commit()

    with pytest.raises(SettlementError, match="protected or unavailable artifact ancestry") as error:
        experience.capture(migrated_db, observation["id"],
                           artifacts_root=run["roots"]["artifacts_root"])
    assert "test_add.py" not in str(error.value)
    assert "return a + b" not in str(error.value)


def test_refused_p01_observation_is_captured_as_uncertain_experience(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path, "memory-refused")
    run["agent"].codex_cmd = [str(tmp_path / "missing-codex-executable")]
    state = investigate.step(run["dsn"], run["agent"], run["checker"],
                             run["investigation_id"], **run["roots"])
    assert state["last_observation"]["status"] == "refused"
    observation, = investigate.export(migrated_db, run["investigation_id"])["observations"]

    captured, = experience.capture_investigation(
        migrated_db, run["investigation_id"], artifacts_root=run["roots"]["artifacts_root"])
    assert captured["observation_id"] == observation["id"]
    resolved = experience.resolve(
        migrated_db, [observation["id"]], artifacts_root=run["roots"]["artifacts_root"])
    item, = resolved["observations"]
    assert item["content"] == {
        "task_instruction": "Implement add so it returns the sum.",
        "status": "refused", "passed": None,
    }
    assert item["identities"]["verifier_operation_id"] is None
    assert len(item["artifacts"]) == 1


def test_missing_artifact_is_reported_and_resolution_does_not_mutate_registry(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path, "memory-missing")
    observation, = _observe(run)
    experience.capture(migrated_db, observation["id"],
                       artifacts_root=run["roots"]["artifacts_root"])
    digest = observation["content"]["solution"]
    (run["roots"]["artifacts_root"] / digest).unlink()

    resolved = experience.resolve(
        migrated_db, [observation["id"]], artifacts_root=run["roots"]["artifacts_root"])
    assert resolved["observations"] == []
    assert resolved["missing_information"] == [{
        "observation_id": observation["id"],
        "reason": "one or more source artifacts are unavailable",
        "artifacts": [{"kind": "solution", "digest": digest,
                       "reason": "artifact bytes are missing or changed"}],
    }]
    with store.db.connect(migrated_db) as conn:
        row = conn.execute("SELECT availability FROM artifact_versions WHERE digest = %s",
                           (digest,)).fetchone()
    assert row[0] == "available"
