from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rsi import genome, investigate, task
from rsi import investigation as state_store
from settlement import broker, store
from settlement.common import Command, ResultCode
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fixtures" / "fake_investigate.py"
RESUME_CHILD = ROOT / "tests" / "fixtures" / "investigate_resume.py"
QUESTION = "Does the solution satisfy the task obligation?"
BAD_SOLUTION = "def add(a, b):\n    return a - b\n"


def _command(request_id: str, payload: dict) -> Command:
    return Command(request_id=request_id, payload=payload)


def _task() -> task.Task:
    tests = (
        b"import unittest\n"
        b"from calc import add\n"
        b"class AddTests(unittest.TestCase):\n"
        b"    def test_add(self):\n"
        b"        self.assertEqual(add(2, 3), 5)\n"
    )
    return task.Task(
        "investigate-add",
        "dev",
        "Implement add(2, 3) so it returns 5.",
        {"calc.py": b"def add(a, b):\n    return 0\n"},
        {"test_add.py": tests},
        {"calc.py": b"def add(a, b):\n    return a + b\n"},
        ("test_add.py",),
    )


def _scenario(migrated_db, tmp_path, investigation_id: str, scenario: str,
              *, objective: str | None = None, token_authorized: int = 100_000,
              cpu_authorized: int = 100_000):
    tmp_path.mkdir(parents=True, exist_ok=True)
    dsn = migrated_db
    staging_root = tmp_path / "stage"
    artifacts_root = tmp_path / "art"
    staging_root.mkdir()
    artifacts_root.mkdir()
    roots = {"staging_root": staging_root, "artifacts_root": artifacts_root}
    candidate = _task()
    seed = genome.Genome({"AGENTS.md": b"Work only on the assigned task.\n"})
    genome.publish(dsn, seed, parent=None, origin="p01-test", **roots)
    task.publish(dsn, candidate, **roots)
    store.seed_allocation(dsn, _command(
        "p01-token-" + investigation_id,
        {"allocation_id": "tokens-" + investigation_id,
         "domain": "tokens", "authorized": token_authorized},
    ))
    store.seed_allocation(dsn, _command(
        "p01-cpu-" + investigation_id,
        {"allocation_id": "cpu-" + investigation_id,
         "domain": "cpu", "authorized": cpu_authorized},
    ))
    run_root = tmp_path / "runs"
    agent = CodexLauncher(
        run_root,
        codex_cmd=[sys.executable, str(FAKE), str(tmp_path / "worker-inputs.jsonl"), scenario],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS,
    )
    checker = LocalLauncher(tmp_path / "verifiers")
    state = investigate.create(
        dsn,
        agent,
        seed,
        investigation_id=investigation_id,
        task=candidate,
        token_allocation="tokens-" + investigation_id,
        cpu_allocation="cpu-" + investigation_id,
        max_steps=2,
        timeout_ms=30_000,
        token_ceiling=5_000,
        objective=objective or
        "Complete the add task and use checked feedback to resolve uncertainty.",
        **roots,
    )
    return {
        "dsn": dsn,
        "agent": agent,
        "checker": checker,
        "state": state,
        "roots": roots,
        "run_root": run_root,
        "candidate": candidate,
        "seed": seed,
        "worker_log": tmp_path / "worker-inputs.jsonl",
    }


def _worker_calls(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_second_worker_uses_open_question_observation_and_saved_solution(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path, "p01-a", "repair-after-feedback")
    assert run["state"]["status"] == "ready"

    first = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p01-a", **run["roots"]
    )

    assert first["status"] == "ready"
    assert first["open_questions"] == [QUESTION]
    assert first["last_observation"]["passed"] is False
    first_observation = first["last_observation"]
    first_solution = first["artifact_refs"]["solution"]
    first_call, = _worker_calls(run["worker_log"])
    assert first_call["prior_solution"] == "def add(a, b):\n    return 0\n"
    assert first_call["continuation"]["open_questions"] == [QUESTION]
    assert first_call["continuation"]["previous_observation"] is None

    second = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p01-a", **run["roots"]
    )

    assert second["status"] == "completed"
    assert second["investigation_id"] == "p01-a"
    assert second["open_questions"] == []
    assert second["last_observation"]["passed"] is True
    assert second["artifact_refs"]["solution"] != first_solution
    first_call, second_call = _worker_calls(run["worker_log"])
    assert QUESTION in second_call["prompt"]
    assert second_call["continuation"]["objective"] == run["state"]["objective"]
    assert second_call["continuation"]["open_questions"] == first["open_questions"]
    assert second_call["continuation"]["previous_observation"] == first_observation
    assert second_call["prior_solution"] == BAD_SOLUTION
    assert second["last_observation"]["episode"] == second_call["operation_id"]
    history = investigate.export(run["dsn"], "p01-a")
    assert len(history["decisions"]) == 2
    assert len(history["observations"]) == 2
    assert [item["content"]["passed"] for item in history["observations"]] == [False, True]


def test_obsolete_revision_cannot_replace_continuation_or_admit_work(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path, "p01-c", "repair-after-feedback")
    created = run["state"]
    ready = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p01-c", **run["roots"]
    )
    operation_id = "p01-stale-operation"
    stale = state_store.decide(run["dsn"], Command(
        request_id="p01-stale-decision",
        expected_revision=created["revision"],
        payload={
            "investigation_id": "p01-c",
            "decision_id": "p01-stale-decision",
            "attempt_id": "p01-stale-attempt",
            "operation_id": operation_id,
            "action": {
                "kind": "worker",
                "explanation": "This decision observed an obsolete revision.",
                "intended_observation": QUESTION,
            },
            "visible_input": {
                "objective": created["objective"],
                "objective_revision": created["objective_revision"],
                "state_revision": created["revision"],
                "open_questions": created["open_questions"],
                "artifact_refs": created["artifact_refs"],
                "previous_observation": created["last_observation"],
            },
        },
    ))
    after = investigate.read(run["dsn"], "p01-c")

    assert ready["revision"] > created["revision"]
    assert stale.code == ResultCode.STALE_REVISION
    assert after == ready
    assert broker.read_operation(run["dsn"], operation_id) is None
    assert len(_worker_calls(run["worker_log"])) == 1


def test_concurrent_investigations_keep_objectives_workspaces_and_artifacts_separate(
    migrated_db, tmp_path
):
    left = _scenario(
        migrated_db, tmp_path / "left", "p01-d-left", "pass-first",
        objective="Finish the left add investigation.",
    )
    right = _scenario(
        migrated_db, tmp_path / "right", "p01-d-right", "pass-first",
        objective="Finish the right add investigation.",
    )

    def advance(run, investigation_id):
        return investigate.step(
            run["dsn"], run["agent"], run["checker"], investigation_id, **run["roots"]
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(advance, left, "p01-d-left"),
            pool.submit(advance, right, "p01-d-right"),
        ]
        left_state, right_state = (future.result(timeout=60) for future in futures)

    left_call, = _worker_calls(left["worker_log"])
    right_call, = _worker_calls(right["worker_log"])
    assert left_state["status"] == right_state["status"] == "completed"
    assert left_state["objective"] != right_state["objective"]
    assert left_call["continuation"]["objective"] == left_state["objective"]
    assert right_call["continuation"]["objective"] == right_state["objective"]
    assert left_call["operation_id"] != right_call["operation_id"]
    left_workspace = Path(left_call["workspace"])
    right_workspace = Path(right_call["workspace"])
    assert left_workspace != right_workspace
    assert (left_workspace / "worker-result.txt").read_text(encoding="utf-8") == \
        "Finish the left add investigation.\n"
    assert (right_workspace / "worker-result.txt").read_text(encoding="utf-8") == \
        "Finish the right add investigation.\n"
    assert left_state["artifact_refs"]["solution"] != right_state["artifact_refs"]["solution"]


def test_invalid_action_stays_inspectable_and_unresolved(migrated_db, tmp_path):
    run = _scenario(migrated_db, tmp_path, "p01-e", "repair-after-feedback")
    created = run["state"]
    decision = state_store.decide(run["dsn"], Command(
        request_id="p01-invalid-action",
        expected_revision=created["revision"],
        payload={
            "investigation_id": "p01-e",
            "decision_id": "p01-invalid-action",
            "attempt_id": "p01-invalid-attempt",
            "operation_id": "p01-invalid-operation",
            "action": {
                "kind": "teleport",
                "explanation": "Attempt an unsupported action.",
                "intended_observation": QUESTION,
            },
            "visible_input": {
                "objective": created["objective"],
                "objective_revision": created["objective_revision"],
                "state_revision": created["revision"],
                "open_questions": created["open_questions"],
                "artifact_refs": created["artifact_refs"],
                "previous_observation": created["last_observation"],
            },
        },
    ))
    unresolved = investigate.read(run["dsn"], "p01-e")
    history = investigate.export(run["dsn"], "p01-e")

    assert decision.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    assert unresolved["status"] == "unresolved"
    assert unresolved["pending_decision"] is None
    assert unresolved["last_observation"].get("passed") is None
    assert unresolved["last_observation"]["action"]["kind"] == "teleport"
    assert len(history["decisions"]) == 1
    assert _worker_calls(run["worker_log"]) == []


def test_insufficient_token_allocation_records_refusal_without_dispatch(migrated_db, tmp_path):
    run = _scenario(
        migrated_db, tmp_path, "p01-f", "pass-first", token_authorized=1_000
    )

    returned = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p01-f", **run["roots"]
    )
    reread = investigate.read(run["dsn"], "p01-f")

    assert {key: returned[key] for key in reread} == reread
    assert reread["status"] == "unresolved"
    assert reread["pending_decision"] is None
    assert reread["last_observation"]["status"] == "refused"
    assert reread["last_observation"]["passed"] is None
    assert "cannot cover" in reread["last_observation"]["reason"]
    assert _worker_calls(run["worker_log"]) == []


def test_insufficient_cpu_allocation_records_verifier_refusal(migrated_db, tmp_path):
    run = _scenario(
        migrated_db, tmp_path, "p01-g", "pass-first", cpu_authorized=1
    )

    returned = investigate.step(
        run["dsn"], run["agent"], run["checker"], "p01-g", **run["roots"]
    )
    reread = investigate.read(run["dsn"], "p01-g")

    assert {key: returned[key] for key in reread} == reread
    assert reread["status"] == "unresolved"
    assert reread["pending_decision"] is None
    assert reread["last_observation"]["status"] == "refused"
    assert reread["last_observation"]["passed"] is None
    assert reread["last_observation"]["verdict"] is None
    assert "cpu-p01-g" in reread["last_observation"]["reason"]
    assert len(_worker_calls(run["worker_log"])) == 1


def _child_env(dsn: str) -> dict[str, str]:
    env = os.environ.copy()
    # The pytest isolation hook rewrites the admin route to a per-run DB in
    # this process. A fresh Python interpreter does not inherit that rewrite,
    # so pass the already-isolated DSN explicitly.
    env["SETTLEMENT_TEST_DSN"] = dsn
    prior = env.get("PYTHONPATH", "")
    paths = [str(ROOT / "src"), str(ROOT)]
    if prior:
        paths.append(prior)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def test_fresh_process_resumes_settled_pending_operation_without_resend(
    migrated_db, tmp_path
):
    run = _scenario(migrated_db, tmp_path, "p01-b", "pass-first")
    crashing = subprocess.run(
        [sys.executable, str(RESUME_CHILD), "interrupt-before-check", "p01-b",
         str(tmp_path), str(FAKE)],
        check=False,
        cwd=ROOT,
        env=_child_env(run["dsn"]),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert crashing.returncode == 17, crashing.stderr

    pending = investigate.read(run["dsn"], "p01-b")
    assert pending["status"] == "pending"
    operation_id = pending["pending_decision"]["operation_id"]
    assert pending["last_observation"] is None
    calls, = _worker_calls(run["worker_log"])
    assert calls["call"] == 1
    assert pending["pending_decision"]["operation_id"] == calls["operation_id"]

    resumed = subprocess.run(
        [sys.executable, str(RESUME_CHILD), "resume", "p01-b", str(tmp_path), str(FAKE)],
        check=False,
        cwd=ROOT,
        env=_child_env(run["dsn"]),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert resumed.returncode == 0, resumed.stderr
    child_state = json.loads(resumed.stdout)
    final = investigate.read(run["dsn"], "p01-b")

    assert child_state["investigation_id"] == "p01-b"
    assert child_state["status"] == "completed"
    assert child_state["last_observation"]["episode"] == operation_id
    assert final["status"] == "completed"
    assert final["last_observation"]["passed"] is True
    assert len(_worker_calls(run["worker_log"])) == 1
