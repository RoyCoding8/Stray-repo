from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rsi import archive, capability, episode, genome, investigate, investigation, task, verifier
from settlement import broker, db, store
from settlement.common import Command
from settlement.launcher_local import LocalLauncher


def _genome(body=None):
    descriptor = {
        "schema": "rsi-capability/1", "interface": "sequence-maximum/1",
        "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
        "effects": ["return", "solution-files"],
        "limits": {"timeout_ms": 5000, "max_output_bytes": 65536},
    }
    body = body or (
        "import json\n"
        "def invoke(request):\n"
        "    result = max(request['value'], default=None)\n"
        "    return {'value': result, 'files': {'answer.json': json.dumps(result)}}\n"
    )
    return genome.Genome({
        "AGENTS.md": b"Use only the assigned public inputs.\n",
        "skills/maximum/SKILL.md": b"---\nname: maximum\ndescription: maximum of a sequence\n---\n",
        "skills/maximum/capability.json": json.dumps(descriptor).encode(),
        "skills/maximum/method.py": body.encode(),
    })


def _task(name, expected):
    test = (
        "import json, pathlib, unittest\n"
        "class Answer(unittest.TestCase):\n"
        "    def test_value(self):\n"
        f"        self.assertEqual(json.loads(pathlib.Path('answer.json').read_text()), {expected!r})\n"
    )
    return task.Task(name, "dev", "Write the sequence maximum as JSON in answer.json.",
                     {"answer.json": b"null"}, {"test_answer.py": test.encode()},
                     {"answer.json": json.dumps(expected).encode()}, ("test_answer.py",))


@pytest.fixture
def env(migrated_db, tmp_path):
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    for domain in ("cpu", "tokens"):
        store.seed_allocation(migrated_db, Command(
            request_id=domain, payload={"allocation_id": domain, "domain": domain,
                                        "authorized": 100_000}))
    candidate = _genome()
    genome.publish(migrated_db, candidate, parent=None, origin="independent-authored-test", **roots)
    return migrated_db, roots, candidate, LocalLauncher(tmp_path / "native"), tmp_path


def _qualify(env, candidate=None, expected=3):
    dsn, roots, original, launcher, _ = env
    candidate = candidate or original
    genome.publish(dsn, candidate, parent=None, origin="independent-authored-test", **roots)
    item = _task("qualification", expected)
    task.publish(dsn, item, **roots)
    ep = episode.run_method_episode(
        dsn, launcher, candidate, name="maximum",
        request={"interface": "sequence-maximum/1", "value": [-5, 3, 0],
                 "files": {"answer.json": "null"}, "context": {}},
        operation_id="qualification", task=item, allocation_id="cpu", attempt_id=None, **roots)
    checked = verifier.verify_episode(dsn, launcher, launcher, ep.operation_id,
                                      allocation_id="cpu", attempt_id=None, **roots)
    retained = capability.retain(dsn, "retain-maximum", genome=candidate, name="maximum",
                                 episode_id=ep.operation_id, artifacts_root=roots["artifacts_root"])
    return checked, retained


def _create(env, values, expected, *, interface="sequence-maximum/1"):
    dsn, roots, candidate, _, _ = env
    item = _task("later-use", expected)
    task.publish(dsn, item, **roots)
    return investigate.create(
        dsn, None, candidate, investigation_id="later-use", task=item,
        token_allocation="tokens", cpu_allocation="cpu", max_steps=1,
        timeout_ms=5000, token_ceiling=1,
        method={"name": "maximum", "interface": interface, "value": values}, **roots)


def test_checked_method_changes_later_investigation_without_model(env):
    dsn, roots, candidate, launcher, _ = env
    checked, retained = _qualify(env)
    assert checked.passed is True
    assert retained["status"] == "retained"
    _create(env, [9, -2, 7], 9)
    result = investigate.step(dsn, None, launcher, "later-use", **roots)
    assert result["status"] == "completed"
    assert result["last_observation"]["passed"] is True
    history = investigation.export(dsn, "later-use")
    selected = history["decisions"][0]["data"]["visible_input"]["capability"]["selection"]
    assert selected["status"] == "selected"
    assert selected["requested_genome"] == selected["executed_genome"] == candidate.digest
    op = result["last_observation"]["episode"]
    assert broker.read_operation(dsn, op)["payload"]["effect"] == broker.SANDBOX_EXEC
    ep = episode.read_episode(dsn, op, launcher)
    assert ep.tokens is None
    assert (ep.workspace / "answer.json").read_text() == "9"
    use = archive.decision(dsn, "capability-use:" + op)["data"]
    assert use["method_digest"] == selected["method_digest"]
    assert use["status"] == "completed"
    request = json.loads((Path(launcher.exec_dirs(op, use["execution_version"])[0]) / "request.json").read_text())
    continuation = request["context"]["continuation"]
    assert "capability" not in continuation
    packet = continuation["context_packet"]
    actual_bytes = len(json.dumps(continuation, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False).encode())
    assert actual_bytes == packet["counts"]["packet_bytes"]


def test_outside_interface_declines_instead_of_running_an_incumbent(env):
    dsn, roots, _, launcher, _ = env
    _qualify(env)
    _create(env, [9, 2], 9, interface="matrix-inverse/1")
    result = investigate.step(dsn, None, launcher, "later-use", **roots)
    assert result["status"] == "ready"
    assert result["pending_decision"] is None
    assert result["capability_outcome"]["status"] == "declined"
    assert "interface" in result["capability_outcome"]["reason"]
    with db.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM attempts WHERE investigation_id='later-use'").fetchone()[0] == 0


def test_noop_fails_the_same_check_and_is_not_retained(env):
    dsn, roots, _, _, _ = env
    noop = _genome("def invoke(request):\n    return {'value': None, 'files': request['files']}\n")
    checked, retained = _qualify(env, noop)
    assert checked.passed is False
    assert retained["status"] == "rejected"
    selected = capability.select(dsn, "no-op-selection", genome=noop, name="maximum",
                                 interface="sequence-maximum/1",
                                 task_id=_task("qualification", 3).digest,
                                 value=[-5, 3, 0], artifacts_root=roots["artifacts_root"])
    assert selected["status"] == "declined"
    assert store.allocation_status(dsn, "cpu")["consumed"] > 0


def test_retention_refuses_a_passing_check_of_substituted_output(env):
    dsn, roots, candidate, launcher, _ = env
    item = _task("substituted-check", 99)
    task.publish(dsn, item, **roots)
    ep = episode.run_method_episode(
        dsn, launcher, candidate, name="maximum",
        request={"interface": "sequence-maximum/1", "value": [-5, 3, 0],
                 "files": {"answer.json": "null"}, "context": {}},
        operation_id="substituted-check", task=item, allocation_id="cpu", attempt_id=None, **roots)
    (ep.workspace / "answer.json").write_text("99")
    checked = verifier.verify_episode(dsn, launcher, launcher, ep.operation_id,
                                      allocation_id="cpu", attempt_id=None, **roots)
    assert checked.passed is True
    retained = capability.retain(dsn, "substituted-check", genome=candidate, name="maximum",
                                 episode_id=ep.operation_id, artifacts_root=roots["artifacts_root"])
    assert retained["status"] == "rejected"
    assert "returned method files" in retained["reason"]


def test_admitted_selection_cannot_change_the_executed_identity(env):
    dsn, roots, candidate, _launcher, _ = env
    _qualify(env)
    selected = capability.select(dsn, "pinned-choice", genome=candidate, name="maximum",
                                 interface="sequence-maximum/1",
                                 task_id=_task("qualification", 3).digest,
                                 value=[-5, 3, 0],
                                 artifacts_root=roots["artifacts_root"])
    assert selected["status"] == "selected"
    forged = {**selected, "executed_genome": "0" * 64}
    with pytest.raises(capability.CapabilityError, match="recorded choice"):
        capability.validate_selection(dsn, forged, genome=candidate, name="maximum",
                                      interface="sequence-maximum/1",
                                      task_id=_task("qualification", 3).digest,
                                      value=[-5, 3, 0],
                                      artifacts_root=roots["artifacts_root"])


def test_fresh_process_resumes_the_same_method_operation(env):
    dsn, _roots, _, launcher, root = env
    _qualify(env)
    _create(env, [], None)
    child = Path(__file__).parent / "fixtures" / "method_resume.py"
    child_env = {**os.environ, "SETTLEMENT_TEST_DSN": dsn}
    first = subprocess.run([sys.executable, str(child), "interrupt", str(root)],
                           check=False, env=child_env, capture_output=True, text=True, timeout=40)
    assert first.returncode == 17, first.stderr
    pending = investigation.read(dsn, "later-use")["pending_decision"]
    op_id = pending["operation_id"]
    admitted = broker.read_operation(dsn, op_id)
    second = subprocess.run([sys.executable, str(child), "resume", str(root)],
                            check=False, env=child_env, capture_output=True, text=True, timeout=40)
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["status"] == "completed"
    ep = episode.read_episode(dsn, op_id, launcher)
    assert (ep.workspace / "answer.json").read_text() == "null"
    spawns = launcher.run_dir / (launcher.native_id(op_id, admitted["execution_version"]) + ".spawns")
    assert spawns.read_text() == "1"
    assert investigation.read(dsn, "later-use")["last_observation"]["episode"] == op_id
