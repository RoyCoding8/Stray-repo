from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

from rsi import episode as ep
from rsi import genome as g
from rsi import task as t
from settlement import artifacts, broker, store
from settlement.common import Command, ResultCode
from settlement.launcher_codex import CodexLauncher, Provider, summarize_events

FAKE = str(Path(__file__).parent / "fixtures" / "fake_codex.py")
GENOME = g.Genome({
    "AGENTS.md": b"# Rules\n",
    "skills/fix/SKILL.md": b"---\nname: fix\ndescription: fix bugs\n---\nbody\n",
    "harness.toml": b'model_reasoning_effort = "low"\n',
})
TASK = t.Task("calc", "dev", "fix it", {"calc.py": b"x = 1\n"},
              {"calc_test.py": b"import unittest\n"}, {"calc.py": b"x = 2\n"},
              ("calc_test.py",))
CEILING = 5_000


def _cmd(payload):
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


@pytest.fixture
def env(migrated_db, tmp_path):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "tokens",
                                     "authorized": 100_000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    g.publish(dsn, GENOME, parent=None, origin="seed", **roots)
    t.publish(dsn, TASK, **roots)

    def launcher(mode):
        return CodexLauncher(tmp_path / "runs", codex_cmd=[sys.executable, FAKE, mode],
                             provider=Provider("http://127.0.0.1:9/v1", "m", "k"),
                             allowed_overrides=g.HARNESS_KEYS)

    def run(mode, op="ep1", timeout_ms=30_000, **episode_inputs):
        return ep.run_episode(dsn, launcher(mode), GENOME, operation_id=op, task=TASK,
                              allocation_id="a1", attempt_id="att1", timeout_ms=timeout_ms,
                              token_ceiling=CEILING, **roots, **episode_inputs)
    return dsn, run, launcher, tmp_path


def _calls(tmp_path, op):
    path = tmp_path / "runs" / op / "fake-calls.txt"
    return path.read_text().splitlines() if path.exists() else []


def _publish_solution(env, files, *, task_digest=None):
    dsn, _, _, tmp = env
    task_digest = TASK.digest if task_digest is None else task_digest
    manifest = {"kind": "rsi-solution", "task": task_digest,
                "files": t.file_manifest(files)}
    receipt = artifacts.stage_package(
        dsn, tmp / "stage", manifest=manifest, files=dict(files),
        scope="rsi-solution", access_label="candidate", format="rsi-solution")
    result = artifacts.publish_package(
        dsn, _cmd({"digest": receipt["digest"]}), tmp / "art", receipt)
    assert result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED)
    return receipt["digest"]


def test_completed_run_settles_real_tokens_once(env):
    dsn, run, _, tmp = env
    first = run("ok")
    assert first.status == "completed"
    assert first.tokens == {"input_tokens": 1000, "cached_input_tokens": 200,
                            "output_tokens": 50, "reasoning_output_tokens": 10}
    assert store.allocation_status(dsn, "a1")["consumed"] == 1050
    assert store.allocation_status(dsn, "a1")["reserved"] == 0
    assert (first.workspace / "done.txt").read_text() == "agents=True\n"
    assert (first.workspace / "calc.py").read_bytes() == b"x = 1\n"
    assert "- fix: fix bugs (file: .agents/skills/fix/SKILL.md)" in \
        (first.workspace / "AGENTS.md").read_text()
    again = run("ok")
    assert again == first
    assert len(_calls(tmp, "ep1")) == 1
    assert broker.read_operation(dsn, "ep1")["payload"]["payload"]["instruction"] == TASK.instruction
    package = json.loads((tmp / "art" / first.trajectory).read_bytes())
    assert b"turn.completed" in bytes.fromhex(package["files"]["events.jsonl"])


def test_continuation_and_solution_are_worker_inputs_and_replay_bound(env):
    dsn, run, _, tmp = env
    continuation = {"open_question": "Which branch handles zero?", "observed": "base case absent"}
    solution_bytes = b"def calc(x):\n    return 7\n"
    solution = _publish_solution(env, {"calc.py": solution_bytes})

    result = run("ok", op="continued", continuation=continuation, solution=solution)

    assert (result.workspace / "calc.py").read_bytes() == solution_bytes
    operation = broker.read_operation(dsn, "continued")
    instruction = operation["payload"]["payload"]["instruction"]
    assert json.dumps(continuation, sort_keys=True, separators=(",", ":")) in instruction
    files = {**g.workspace_view(GENOME), "calc.py": solution_bytes}
    manifest = [{"path": path, "size": len(raw), "digest": hashlib.sha256(raw).hexdigest()}
                for path, raw in sorted(files.items())]
    input_digest = hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert f"Input digest: {input_digest}" in instruction
    assert len(_calls(tmp, "continued")) == 1

    with pytest.raises(ep.EpisodeError, match="different input"):
        run("ok", op="continued", continuation={"open_question": "Changed"},
            solution=solution)
    changed_solution = _publish_solution(env, {"calc.py": b"def calc(x):\n    return 8\n"})
    with pytest.raises(ep.EpisodeError, match="different input"):
        run("ok", op="continued", continuation=continuation, solution=changed_solution)
    assert len(_calls(tmp, "continued")) == 1


def test_solution_artifact_is_rehashed_and_bound_to_task_and_slots(env):
    dsn, run, _, tmp = env
    tampered = _publish_solution(env, {"calc.py": b"x = 3\n"})
    (tmp / "art" / tampered).write_bytes(b"changed after publication")
    with pytest.raises(ep.EpisodeError, match="digest"):
        run("ok", op="tampered-solution", solution=tampered)
    assert broker.read_operation(dsn, "tampered-solution") is None

    wrong_task = _publish_solution(env, {"calc.py": b"x = 4\n"}, task_digest="0" * 64)
    with pytest.raises(ep.EpisodeError, match="another task"):
        run("ok", op="wrong-task-solution", solution=wrong_task)
    assert broker.read_operation(dsn, "wrong-task-solution") is None

    wrong_slot = _publish_solution(env, {"other.py": b"x = 5\n"})
    with pytest.raises(ep.EpisodeError, match="task workspace"):
        run("ok", op="wrong-slot-solution", solution=wrong_slot)
    assert broker.read_operation(dsn, "wrong-slot-solution") is None


def test_completed_run_without_usage_charges_ceiling_once(env):
    dsn, run, _, tmp = env
    result = run("no-usage")
    assert result.status == "completed" and result.tokens is None
    assert store.allocation_status(dsn, "a1")["consumed"] == CEILING
    assert store.allocation_status(dsn, "a1")["reserved"] == 0
    assert run("no-usage") == result
    assert store.allocation_status(dsn, "a1")["consumed"] == CEILING
    assert len(_calls(tmp, "ep1")) == 1


def test_leaked_skill_catalog_refuses_before_any_send(env):
    dsn, run, launcher, tmp = env
    with pytest.raises(ep.EpisodeError, match="settled without a launcher result"):
        run("leak")
    assert _calls(tmp, "ep1") == []
    assert store.allocation_status(dsn, "a1")["consumed"] == 0
    assert store.allocation_status(dsn, "a1")["reserved"] == 0
    assert launcher("leak").prove_never_sent("ep1") is True


def test_upstream_503_is_infra_failure_charged_at_ceiling(env):
    dsn, run, _, _ = env
    done = run("infra")
    assert done.status == "infra_failed"
    assert "503" in done.infra_reason
    assert store.allocation_status(dsn, "a1")["consumed"] == CEILING


def test_timeout_kills_the_run(env):
    _, run, _, _ = env
    done = run("hang", timeout_ms=3_000)
    assert done.status == "timeout"
    assert done.seconds < 30


def test_kernel_owned_config_is_refused_by_launcher(env):
    dsn, _, launcher, tmp = env
    broker.ensure_operation(dsn, operation_id="ep2", effect=broker.AGENT_RUN, payload={
        "harness": "codex", "genome": GENOME.digest, "task": TASK.digest, "instruction": "x",
        "config": {"model": "other"}, "timeout_ms": 1000, "token_ceiling": 10},
        allocation_id="a1", attempt_id="att1")
    status = broker.dispatch_operation(dsn, "ep2", launchers={"codex": launcher("ok")})
    assert status.next_decision == "config sets kernel-owned keys ['model']"
    assert _calls(tmp, "ep2") == []


def test_summarize_classifies_non_infra_failure():
    raw = b'{"type":"turn.failed","error":{"message":"tool exploded"}}\n'
    assert summarize_events(raw)["status"] == "failed"


def test_provider_rejection_is_infrastructure_failure():
    message = json.dumps(
        {
            "error": {
                "code": 400,
                "message": "Provider returned error",
                "metadata": {
                    "provider_name": "Cohere",
                    "raw": "invalid tool call provided: tool arguments must be a stringified JSON object",
                },
            }
        }
    )
    raw = (json.dumps({"type": "turn.failed", "error": {"message": message}}) + "\n").encode()
    result = summarize_events(raw)
    assert result["status"] == "infra_failed"
    assert result["infra_reason"] == message
    assert result["tokens"] is None


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": 100},
                                 {"input_tokens": -1, "output_tokens": 5},
                                 {"input_tokens": True, "output_tokens": 5}])
def test_completed_without_valid_usage_keeps_tokens_unknown(usage):
    raw = (json.dumps({"type": "turn.completed", "usage": usage}) + "\n").encode()
    result = summarize_events(raw)
    assert result["status"] == "completed"
    assert result["tokens"] is None
