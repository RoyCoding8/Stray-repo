from __future__ import annotations

import json
import uuid

import pytest

from rsi import episode as ep
from rsi import genome as g
from rsi import task as t
from rsi import verifier
from settlement import broker, db, store
from settlement.common import Command, SettlementError
from settlement.launcher_local import LocalLauncher

INTERFACE = "rsi-files/1"
SOLUTION = "def solve(value):\n    return value + 3\n"
METHOD_SOURCE = '''from pathlib import Path

def invoke(request):
    value = int(request["files"]["input.txt"].strip())
    return {"value": {"answer": value + 3,
                       "task_digest": request["context"]["task_digest"],
                       "continuation": request["context"]["continuation"]}, "files": {
        "calc.py": "def solve(value):\\n    return value + 3\\n",
        "input.txt": f"{value}\\n",
    }}
'''
NOOP_SOURCE = '''def invoke(request):
    return {"value": request["value"], "files": {}}
'''


def _cmd(payload):
    return Command(request_id=f"p04-{uuid.uuid4().hex[:12]}", payload=payload)


def _genome(source: str = METHOD_SOURCE) -> g.Genome:
    return g.Genome({
        "AGENTS.md": b"# Rules\n",
        "skills/add-three/SKILL.md": (
            b"---\nname: add-three\ndescription: Add three to an integer\n---\n"
            b"Read the public input and return a solution file.\n"),
        "skills/add-three/capability.json": json.dumps({
            "schema": "rsi-capability/1",
            "interface": INTERFACE,
            "entrypoint": "method.py:invoke",
            "dependencies": ["python-stdlib"],
            "effects": ["return", "solution-files"],
            "limits": {"timeout_ms": 5000, "max_output_bytes": 65536},
        }, sort_keys=True, separators=(",", ":")).encode(),
        "skills/add-three/method.py": source.encode(),
    })


def _task(value: int) -> t.Task:
    return t.Task(
        "add-three", "dev", "Implement solve(value) to add three.",
        {"calc.py": b"", "input.txt": f"{value}\n".encode()},
        {"test_calc.py": b'''import unittest
from pathlib import Path
from calc import solve

class AddThree(unittest.TestCase):
    def test_public_input(self):
        value = int(Path("input.txt").read_text())
        self.assertEqual(solve(value), value + 3)
'''},
        {"calc.py": b"def solve(value):\n    return value + 3\n",
         "input.txt": f"{value}\n".encode()},
        ("test_calc.py",))


class CountingLauncher(LocalLauncher):
    def __init__(self, run_dir):
        super().__init__(run_dir)
        self.dispatches: dict[str, int] = {}

    def dispatch(self, op, **kwargs):
        self.dispatches[op.operation_id] = self.dispatches.get(op.operation_id, 0) + 1
        return super().dispatch(op, **kwargs)


@pytest.fixture
def env(migrated_db, tmp_path):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "tokens",
                                     "authorized": 100_000}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    store.acquire_work(dsn, _cmd({"attempt_id": "att1", "investigation_id": "i1"}))
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    genome = _genome()
    task = _task(4)
    g.publish(dsn, genome, parent=None, origin="seed", **roots)
    t.publish(dsn, task, **roots)
    launcher = CountingLauncher(tmp_path / "runs")
    return dsn, genome, task, launcher, roots


def _request(task: t.Task, *, answer: int = 4, **changes):
    files = {path: raw.decode("utf-8") for path, raw in task.workspace.items()}
    files.update(changes.pop("files", {}))
    return {"interface": INTERFACE, "value": {"answer": answer},
            "files": files, "context": {}, **changes}


def _run(env, *, operation_id="method-episode", genome=None, task=None, request=None):
    dsn, original_genome, original_task, launcher, roots = env
    genome = genome or original_genome
    task = task or original_task
    request = request or _request(task)
    return ep.run_method_episode(
        dsn, launcher, genome, name="add-three", request=request,
        operation_id=operation_id, task=task, allocation_id="a1", attempt_id="att1",
        timeout_ms=10_000, **roots)


def test_method_output_reaches_pristine_verifier_and_native_trajectory(env):
    dsn, genome, task, launcher, roots = env
    episode = _run(env)

    assert episode.status == "completed"
    assert episode.tokens is None
    assert (episode.workspace / "calc.py").read_text() == SOLUTION
    checked = verifier.verify_episode(
        dsn, launcher, launcher, episode.operation_id, allocation_id="a1",
        attempt_id="att1", timeout_ms=30_000, **roots)
    assert (checked.status, checked.passed) == ("passed", True)

    package = json.loads((roots["artifacts_root"] / episode.trajectory).read_bytes())
    event = json.loads(bytes.fromhex(package["files"]["events.jsonl"]).decode().strip())
    operation = broker.read_operation(dsn, episode.operation_id)
    assert event["type"] == "method.invocation.result"
    assert event["value"] == {"answer": 7, "task_digest": task.digest,
                              "continuation": {}}
    assert event["task"] == task.digest
    assert event["genome"] == genome.digest
    assert event["output_digest"]
    assert event["execution_version"] == operation["execution_version"]
    assert operation["payload"]["effect"] == broker.SANDBOX_EXEC
    with db.connect(dsn) as conn:
        artifact_format = conn.execute(
            "SELECT format FROM artifact_versions WHERE digest = %s",
            (episode.trajectory,)).fetchone()[0]
    assert artifact_format == "native-jsonl"


def test_noop_method_fails_the_same_pristine_verifier(env):
    dsn, _, task, launcher, roots = env
    noop = _genome(NOOP_SOURCE)
    g.publish(dsn, noop, parent=None, origin="test-noop", **roots)
    episode = _run(env, operation_id="method-noop", genome=noop,
                   request=_request(task, answer=4))

    assert episode.status == "completed"
    checked = verifier.verify_episode(
        dsn, launcher, launcher, episode.operation_id, allocation_id="a1",
        attempt_id="att1", timeout_ms=30_000, **roots)
    assert (checked.status, checked.passed) == ("failed", False)


def test_changed_public_input_gets_a_new_invocation_and_result(env):
    dsn, _, _, _, roots = env
    changed_task = _task(9)
    t.publish(dsn, changed_task, **roots)
    first = _run(env)
    second = _run(env, operation_id="method-episode-changed", task=changed_task,
                  request=_request(changed_task, answer=9))

    assert first.operation_id != second.operation_id
    assert second.status == "completed"
    package = json.loads((roots["artifacts_root"] / second.trajectory).read_bytes())
    event = json.loads(bytes.fromhex(package["files"]["events.jsonl"]).decode().strip())
    first_package = json.loads((roots["artifacts_root"] / first.trajectory).read_bytes())
    first_event = json.loads(bytes.fromhex(
        first_package["files"]["events.jsonl"]).decode().strip())
    assert event["value"] == {"answer": 12, "task_digest": changed_task.digest,
                              "continuation": {}}
    assert event["input_digest"] != first_event["input_digest"]
    assert second.workspace.joinpath("calc.py").read_text() == SOLUTION
    assert broker.read_operation(dsn, second.operation_id)["payload"]["effect"] == broker.SANDBOX_EXEC


def test_same_operation_replays_once_and_rejects_changed_inputs(env):
    dsn, genome, task, launcher, _ = env
    first = _run(env)
    (first.workspace / "calc.py").write_text("def solve(value): return -1\n")
    again = _run(env)
    assert again == first
    assert (again.workspace / "calc.py").read_text() == SOLUTION
    assert launcher.dispatches[first.operation_id] == 1

    with pytest.raises(SettlementError):
        _run(env, request=_request(task, answer=5))

    # Simulate a crash after method settlement but before the episode row exists.
    with db.connect(dsn) as conn:
        conn.execute("DELETE FROM rsi_episodes WHERE operation_id = %s",
                     (first.operation_id,))
        conn.commit()
    changed_task = _task(8)
    t.publish(dsn, changed_task, **env[4])
    with pytest.raises(SettlementError):
        _run(env, task=changed_task, request=_request(changed_task, answer=8))
    with db.connect(dsn) as conn:
        assert conn.execute("SELECT 1 FROM rsi_episodes WHERE operation_id = %s",
                            (first.operation_id,)).fetchone() is None
    changed_genome = _genome(METHOD_SOURCE + "\n# changed package identity\n")
    g.publish(dsn, changed_genome, parent=genome.digest, origin="changed", **env[4])
    with pytest.raises(SettlementError):
        _run(env, genome=changed_genome)
    assert launcher.dispatches[first.operation_id] == 1


def test_request_files_outside_task_slots_refuse_before_dispatch(env):
    dsn, _, task, launcher, _ = env
    request = _request(task, files={"secret.txt": "not public"})
    with pytest.raises(ep.EpisodeError, match="task workspace slots"):
        _run(env, request=request)
    assert broker.read_operation(dsn, "method-episode") is None
    assert launcher.dispatches == {}
