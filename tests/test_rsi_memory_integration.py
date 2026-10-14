from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rsi import genome, investigate, memory, task
from rsi import investigation as state_store
from settlement import store
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "tests" / "fixtures" / "p02_worker.py"
RESUME_CHILD = ROOT / "tests" / "fixtures" / "p02_resume.py"
NONEMPTY_INSTRUCTION = (
    "Implement maximum(xs) for a nonempty list and return its largest value."
)
EMPTY_INSTRUCTION = (
    "Implement maximum(xs) and return 0 when xs is empty; otherwise return the largest value."
)
LATER_INSTRUCTION = (
    "Implement maximum including its empty-input convention by applying relevant prior checked experience."
)
LESSON = (
    "sorted(xs)[-1] returns the maximum for nonempty lists but fails on empty lists; "
    "use a zero default when the input is empty."
)
SEALED_MARKER = "P02-SEALED-CANARY-7319"


def _task(task_id: str, instruction: str, *, empty: bool = False, split: str = "dev"):
    tests = (
        b"import unittest\n"
        b"from solution import maximum\n"
        b"class MaximumTests(unittest.TestCase):\n"
        b"    def test_values(self):\n"
        b"        self.assertEqual(maximum([-8, 2, 5]), 5)\n"
    )
    if empty:
        tests += (
            b"    def test_empty_default(self):\n"
            b"        self.assertEqual(maximum([]), 0)\n"
        )
    reference = b"def maximum(xs):\n    return max(xs) if xs else 0\n"
    return task.Task(
        task_id,
        split,
        instruction,
        {"solution.py": b"def maximum(xs):\n    return 0\n"},
        {"test_maximum.py": tests},
        {"solution.py": reference},
        ("test_maximum.py",),
    )


def _create(tmp_path, dsn, investigation_id, candidate, *, objective=None, memory_options=None):
    root = tmp_path / investigation_id
    staging_root = root / "stage"
    artifacts_root = tmp_path / "p02-artifacts"
    staging_root.mkdir(parents=True)
    artifacts_root.mkdir(exist_ok=True)
    genome_root = genome.Genome({"AGENTS.md": b"Work only on the assigned task.\n"})
    genome.publish(dsn, genome_root, parent=None, origin="p02-test",
                   staging_root=staging_root, artifacts_root=artifacts_root)
    task.publish(dsn, candidate, staging_root=staging_root,
                 artifacts_root=artifacts_root)
    store.seed_allocation(dsn, Command(
        request_id="p02-token-" + investigation_id,
        payload={"allocation_id": "p02-tokens-" + investigation_id,
                 "domain": "tokens", "authorized": 100_000}))
    store.seed_allocation(dsn, Command(
        request_id="p02-cpu-" + investigation_id,
        payload={"allocation_id": "p02-cpu-" + investigation_id,
                 "domain": "cpu", "authorized": 100_000}))
    agent = CodexLauncher(
        root / "runs",
        codex_cmd=[sys.executable, str(WORKER), str(root / "worker-inputs.jsonl"), "conditioned"],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS,
    )
    checker = LocalLauncher(root / "verifiers")
    state = investigate.create(
        dsn, agent, genome_root, investigation_id=investigation_id,
        task=candidate, token_allocation="p02-tokens-" + investigation_id,
        cpu_allocation="p02-cpu-" + investigation_id, max_steps=1,
        timeout_ms=30_000, token_ceiling=5_000,
        objective=objective or candidate.instruction,
        staging_root=staging_root, artifacts_root=artifacts_root,
        memory=memory_options,
    )
    return {
        "dsn": dsn,
        "id": investigation_id,
        "root": root,
        "state": state,
        "task": candidate,
        "agent": agent,
        "checker": checker,
        "staging_root": staging_root,
        "artifacts_root": artifacts_root,
        "worker_log": root / "worker-inputs.jsonl",
    }


def _step(run):
    return investigate.step(
        run["dsn"], run["agent"], run["checker"], run["id"],
        staging_root=run["staging_root"], artifacts_root=run["artifacts_root"],
    )


def _worker_calls(run):
    path = run["worker_log"]
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sources(tmp_path, dsn):
    original = _create(
        tmp_path, dsn, "p02-source-nonempty",
        _task("p02-maximum-nonempty", NONEMPTY_INSTRUCTION),
    )
    original_result = _step(original)
    assert original_result["status"] == "completed", (
        original_result.get("execution_error", original_result)
    )
    assert original_result["last_observation"]["passed"] is True
    changed = _create(
        tmp_path, dsn, "p02-source-empty",
        _task("p02-maximum-empty", EMPTY_INSTRUCTION, empty=True),
    )
    changed_result = _step(changed)
    assert changed_result["status"] == "unresolved", (
        changed_result.get("execution_error", changed_result)
    )
    assert changed_result["last_observation"]["passed"] is False
    original_observation = state_store.export(dsn, original["id"])["observations"][0]["id"]
    changed_observation = state_store.export(dsn, changed["id"])["observations"][0]["id"]
    return original, original_result, changed, changed_result, original_observation, changed_observation


def _revise_lesson(dsn, artifacts_root, support, opposition, *, claim_id="p02-max-lesson",
                   scope=None, text=LESSON, status="challenged"):
    return memory.revise(
        dsn, claim_id=claim_id, expected_version=0, text=text,
        scope=scope or {"domain": "task"}, status=status,
        support=(support,), opposition=(opposition,), artifacts_root=artifacts_root,
    )


def _query(run, purpose=LATER_INSTRUCTION, *, scope=None, revision=None, view="structured"):
    return memory.query(
        run["dsn"], purpose="task: " + purpose,
        investigation_id=run["id"], scope=scope or {"domain": "task"},
        artifacts_root=run["artifacts_root"], visibility="learner",
        revision=revision, view=view, limit=10,
    )


def test_p02_a_success_on_nonempty_input_is_preserved_when_empty_input_fails(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("p02")
    original, success, changed, failure, support, opposition = _sources(tmp_path, migrated_db)

    assert success["last_observation"]["passed"] is True
    assert failure["last_observation"]["passed"] is False
    assert success["last_observation"]["episode"] != failure["last_observation"]["episode"]
    _revise_lesson(migrated_db, original["artifacts_root"], support, opposition)
    result = _query(changed, scope={"domain": "task"})
    claim, = [item for item in result["claims"] if item["claim_id"] == "p02-max-lesson"]

    assert claim["status"] == "challenged"
    assert claim["text"] == LESSON
    assert claim["support"] == [support]
    assert claim["opposition"] == [opposition]
    assert {item["observation_id"] for item in result["observations"]} == {support, opposition}
    rows = {item["observation_id"]: item for item in result["observations"]}
    assert rows[support]["content"]["passed"] is True
    assert rows[opposition]["content"]["passed"] is False


def test_p02_b_later_consumer_uses_lesson_and_opposition_roots(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("p02")
    original, _, _, _, support, opposition = _sources(tmp_path, migrated_db)
    _revise_lesson(migrated_db, original["artifacts_root"], support, opposition)

    structured = _create(
        tmp_path, migrated_db, "p02-later-structured",
        _task("p02-maximum-later", LATER_INSTRUCTION, empty=True),
    )
    assert structured["state"]["config"]["memory"] == {
        "scope": {"domain": "task"}, "view": "structured", "limit": 10,
    }
    completed = _step(structured)
    call, = _worker_calls(structured)
    snapshot = call["continuation"]["memory"]
    claim, = [item for item in snapshot["claims"] if item["claim_id"] == "p02-max-lesson"]
    observation_ids = {item["observation_id"] for item in snapshot["observations"]}

    assert completed["status"] == "completed"
    assert completed["last_observation"]["passed"] is True
    assert call["used_memory"] is True
    assert claim["status"] == "challenged"
    assert claim["support"] == [support] and claim["opposition"] == [opposition]
    assert observation_ids == {support, opposition}
    assert len(snapshot["observations"]) == len(observation_ids)

    raw = _create(
        tmp_path, migrated_db, "p02-later-history",
        _task("p02-maximum-history", LATER_INSTRUCTION, empty=True),
        memory_options={"scope": {"domain": "task"}, "view": "raw-history", "limit": 10},
    )
    assert raw["state"]["config"]["memory"]["view"] == "raw-history"
    raw_result = _step(raw)
    raw_call, = _worker_calls(raw)
    raw_snapshot = raw_call["continuation"]["memory"]
    assert raw_result["last_observation"]["passed"] is True
    assert raw_snapshot["view"] == "raw-history" and raw_snapshot["claims"] == []
    assert {support, opposition} <= {
        item["observation_id"] for item in raw_snapshot["observations"]
    }
    assert raw_call["used_memory"] is True

    disconnected = _create(
        tmp_path, migrated_db, "p02-later-disconnected",
        _task("p02-maximum-disconnected", LATER_INSTRUCTION, empty=True),
        memory_options={"scope": {"domain": "task", "case": "not-recorded"}},
    )
    disconnected_result = _step(disconnected)
    disconnected_call, = _worker_calls(disconnected)
    assert disconnected_result["last_observation"]["passed"] is False
    assert disconnected_call["continuation"]["memory"]["claims"] == []

    memory.revise(
        migrated_db, claim_id="p02-max-wrong-source", expected_version=0,
        text=LESSON, scope={"domain": "task", "case": "wrong-source"},
        status="challenged", support=(opposition,), opposition=(support,),
        artifacts_root=original["artifacts_root"],
    )
    wrong_source = _create(
        tmp_path, migrated_db, "p02-later-wrong-source",
        _task("p02-maximum-wrong-source", LATER_INSTRUCTION, empty=True),
        memory_options={"scope": {"domain": "task", "case": "wrong-source"}},
    )
    wrong_result = _step(wrong_source)
    wrong_call, = _worker_calls(wrong_source)
    wrong_snapshot = wrong_call["continuation"]["memory"]
    wrong_claim, = wrong_snapshot["claims"]
    assert wrong_result["last_observation"]["passed"] is False
    assert wrong_claim["claim_id"] == "p02-max-wrong-source"
    assert wrong_claim["support"] == [opposition]
    assert wrong_claim["opposition"] == [support]
    assert wrong_call["used_memory"] is False


def test_p02_c_and_e_pending_replay_keeps_withdrawn_lesson_snapshot_after_restart(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("p02")
    original, _, _, _, support, opposition = _sources(tmp_path, migrated_db)
    artifacts_root = original["artifacts_root"]
    _revise_lesson(migrated_db, artifacts_root, support, opposition)
    target = _create(
        tmp_path, migrated_db, "p02-pending-withdrawn",
        _task("p02-maximum-pending", LATER_INSTRUCTION, empty=True),
    )
    pinned = _query(target)
    state = target["state"]
    visible = {
        "objective": state["objective"],
        "objective_revision": state["objective_revision"],
        "state_revision": state["revision"],
        "open_questions": state["open_questions"],
        "artifact_refs": state["artifact_refs"],
        "previous_observation": state["last_observation"],
        "memory": pinned,
    }
    decided = state_store.decide(migrated_db, Command(
        request_id="p02-pending-decision",
        expected_revision=state["revision"],
        payload={
            "investigation_id": target["id"],
            "decision_id": "p02-pending-decision",
            "attempt_id": "p02-pending-attempt",
            "operation_id": "p02-pending-operation",
            "action": {"kind": "worker", "explanation": "Use remembered evidence.",
                       "intended_observation": "Check maximum behavior on empty input."},
            "visible_input": visible,
        },
    ))
    assert decided.code == ResultCode.APPLIED
    memory.revise(
        migrated_db, claim_id="p02-max-lesson", expected_version=1,
        text=LESSON, scope={"domain": "task"}, status="withdrawn",
        support=(support,), opposition=(opposition,), artifacts_root=artifacts_root,
    )
    current = _query(target)
    historical = memory.history(
        migrated_db, "p02-max-lesson", artifacts_root=artifacts_root,
        visibility="learner",
    )
    assert all(item["claim_id"] != "p02-max-lesson" for item in current["claims"])
    assert [item["status"] for item in historical] == ["challenged", "withdrawn"]

    child = subprocess.run(
        [sys.executable, str(RESUME_CHILD), target["id"], str(target["root"]),
         str(target["artifacts_root"]), str(WORKER)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(
            filter(None, (str(ROOT / "src"), os.environ.get("PYTHONPATH", ""))))},
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    resumed = investigate.read(migrated_db, target["id"])
    call, = _worker_calls(target)
    assert resumed["status"] == "completed"
    assert resumed["last_observation"]["passed"] is True
    assert call["operation_id"] == "p02-pending-operation"
    assert call["continuation"]["memory"] == pinned
    assert call["continuation"]["memory"]["revision"] < current["revision"]


def test_p02_pending_dispatch_revalidates_memory_artifacts(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("p02")
    original, _, _, _, support, opposition = _sources(tmp_path, migrated_db)
    _revise_lesson(migrated_db, original["artifacts_root"], support, opposition)
    target = _create(
        tmp_path, migrated_db, "p02-pending-corrupt-source",
        _task("p02-maximum-corrupt-source", LATER_INSTRUCTION, empty=True),
    )
    pinned = _query(target)
    state = target["state"]
    visible = {
        "objective": state["objective"],
        "objective_revision": state["objective_revision"],
        "state_revision": state["revision"],
        "open_questions": state["open_questions"],
        "artifact_refs": state["artifact_refs"],
        "previous_observation": state["last_observation"],
        "memory": pinned,
    }
    decided = state_store.decide(migrated_db, Command(
        request_id="p02-corrupt-source-decision",
        expected_revision=state["revision"],
        payload={
            "investigation_id": target["id"],
            "decision_id": "p02-corrupt-source-decision",
            "attempt_id": "p02-corrupt-source-attempt",
            "operation_id": "p02-corrupt-source-operation",
            "action": {"kind": "worker", "explanation": "Use checked memory.",
                       "intended_observation": "Check empty maximum behavior."},
            "visible_input": visible,
        },
    ))
    assert decided.code == ResultCode.APPLIED
    digests = {
        digest
        for observation in pinned["observations"]
        for digest in observation["artifacts"]
    }
    assert digests
    path = target["artifacts_root"] / next(iter(digests))
    assert path.is_file()
    path.write_bytes(b"corrupted source evidence")

    with pytest.raises(SettlementError, match="evidence|artifact|observation"):
        _step(target)
    assert _worker_calls(target) == []
    assert investigate.read(migrated_db, target["id"])["pending_decision"] is not None


def test_p02_d_sealed_task_package_does_not_enter_learner_memory(
    migrated_db, tmp_path_factory
):
    tmp_path = tmp_path_factory.mktemp("p02")
    target = _create(
        tmp_path, migrated_db, "p02-public-query",
        _task("p02-public-task", "Assess maximum behavior using normal integer inputs."),
    )
    sealed = _task("p02-sealed-task", "Assess maximum behavior using normal integer inputs.",
                   empty=True, split="anchor")
    sealed = task.Task(
        sealed.name, sealed.split, sealed.instruction, sealed.workspace,
        sealed.verifier,
        {"solution.py": (
            f"def maximum(xs):\n    raise RuntimeError('{SEALED_MARKER}')\n"
        ).encode()},
        sealed.test_files,
    )
    task.publish(
        migrated_db, sealed, staging_root=target["staging_root"],
        artifacts_root=target["artifacts_root"],
    )

    state = _step(target)
    call, = _worker_calls(target)
    memory_text = json.dumps(call["continuation"]["memory"], sort_keys=True)
    prompt = call["prompt"]

    assert state["status"] == "completed"
    assert SEALED_MARKER not in memory_text and SEALED_MARKER not in prompt
    assert "return max(xs) if xs else 0" not in memory_text
    assert call["continuation"]["memory"]["claims"] == []
    assert call["continuation"]["memory"]["observations"] == []
