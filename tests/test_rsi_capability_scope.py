from __future__ import annotations

import json

import pytest

from rsi import archive, capability, episode, genome, task, verifier
from settlement import db, store
from settlement.common import Command
from settlement.launcher_local import LocalLauncher


def _genome():
    method = (
        "import json\n"
        "def invoke(request):\n"
        "    result = max(request['value'], default=None)\n"
        "    if request['context']['continuation'].get('mode') == 'contrary':\n"
        "        result = None\n"
        "    return {'value': result, 'files': {'answer.json': json.dumps(result)}}\n"
    )
    files = {"AGENTS.md": b"Use only the assigned public inputs.\n"}
    for name, interface in (("maximum", "sequence-maximum/1"),
                            ("alternate", "sequence-maximum/2")):
        descriptor = {
            "schema": "rsi-capability/1", "interface": interface,
            "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
            "effects": ["return", "solution-files"],
            "limits": {"timeout_ms": 5000, "max_output_bytes": 65536},
        }
        files[f"skills/{name}/SKILL.md"] = (
            f"---\nname: {name}\ndescription: maximum\n---\n".encode())
        files[f"skills/{name}/capability.json"] = json.dumps(descriptor).encode()
        files[f"skills/{name}/method.py"] = method.encode()
    return genome.Genome(files)


def _task():
    test = (
        "import json, pathlib, unittest\n"
        "class Answer(unittest.TestCase):\n"
        "    def test_value(self):\n"
        "        self.assertEqual(json.loads(pathlib.Path('answer.json').read_text()), 3)\n"
    )
    return task.Task("applicability", "dev", "Write the sequence maximum in answer.json.",
                     {"answer.json": b"null"}, {"test_answer.py": test.encode()},
                     {"answer.json": b"3"}, ("test_answer.py",))


@pytest.fixture
def env(migrated_db, tmp_path):
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    for domain in ("cpu", "tokens"):
        store.seed_allocation(migrated_db, Command(
            request_id=domain, payload={"allocation_id": domain, "domain": domain,
                                        "authorized": 100_000}))
    candidate = _genome()
    genome.publish(migrated_db, candidate, parent=None,
                   origin="applicability-scope-test", **roots)
    item = _task()
    task.publish(migrated_db, item, **roots)
    return migrated_db, roots, candidate, item, LocalLauncher(tmp_path / "native")


def _use(env, operation_id, *, context, name="maximum", interface="sequence-maximum/1",
         verify=True):
    dsn, roots, candidate, item, launcher = env
    ep = episode.run_method_episode(
        dsn, launcher, candidate, name=name,
        request={"interface": interface, "value": [1, 3, 2],
                 "files": {"answer.json": "null"}, "context": context},
        operation_id=operation_id, task=item, allocation_id="cpu", attempt_id=None,
        **roots)
    checked = verifier.verify_episode(
        dsn, launcher, launcher, operation_id, allocation_id="cpu", attempt_id=None,
        **roots) if verify and ep.status == "completed" else None
    return ep, checked


def test_later_failed_native_use_vetoes_only_future_exact_scope(env):
    dsn, roots, candidate, item, _launcher = env
    ep, checked = _use(env, "scope-qualified-use", context={})
    assert checked is not None and checked.passed is True
    retained = capability.retain(
        dsn, "scope-retention", genome=candidate, name="maximum",
        episode_id=ep.operation_id, artifacts_root=roots["artifacts_root"])
    assert retained["status"] == "retained"

    condition = {"task_id": item.digest, "value": [1, 3, 2]}
    with db.connect(dsn) as conn:
        before = conn.execute(
            "SELECT count(*) FROM rsi_decisions WHERE kind='capability-selection'").fetchone()[0]
    eligible = capability.eligibility(
        dsn, genome=candidate, name="maximum", interface="sequence-maximum/1",
        **condition, artifacts_root=roots["artifacts_root"])
    with db.connect(dsn) as conn:
        after = conn.execute(
            "SELECT count(*) FROM rsi_decisions WHERE kind='capability-selection'").fetchone()[0]
    assert eligible["status"] == "selected"
    assert before == after
    unverified, unknown = _use(
        env, "scope-unverified-use", context={"mode": "contrary"}, verify=False)
    assert unverified.status == "completed" and unknown is None
    unknown_selection = capability.select(
        dsn, "scope-unverified-selection", genome=candidate, name="maximum",
        interface="sequence-maximum/1", **condition,
        artifacts_root=roots["artifacts_root"])
    assert unknown_selection["status"] == "selected"

    forged_ep, forged_verdict = _use(
        env, "scope-forged-use", context={"mode": "contrary"})
    assert forged_verdict is not None and forged_verdict.passed is False
    failed_use = archive.decision(dsn, "capability-use:" + forged_ep.operation_id)["data"]
    input_path = roots["artifacts_root"] / failed_use["input_artifact_digest"]
    input_path.write_bytes(input_path.read_bytes() + b" forged")
    stale_selection = capability.select(
        dsn, "scope-stale-evidence-selection", genome=candidate, name="maximum",
        interface="sequence-maximum/1", **condition,
        artifacts_root=roots["artifacts_root"])
    assert stale_selection["status"] == "selected"

    admitted = capability.select(
        dsn, "scope-admitted-before-failure", genome=candidate, name="maximum",
        interface="sequence-maximum/1", **condition,
        artifacts_root=roots["artifacts_root"])
    assert admitted["status"] == "selected"
    assert admitted["task_id"] == item.digest
    assert admitted["value"] == [1, 3, 2]

    failed_ep, failed_check = _use(env, "scope-later-failed-use", context={"mode": "contrary"})
    assert failed_ep.status == "completed"
    assert failed_check is not None and failed_check.passed is False

    capability.validate_selection(
        dsn, admitted, genome=candidate, name="maximum", interface="sequence-maximum/1",
        **condition, artifacts_root=roots["artifacts_root"])
    replayed = capability.select(
        dsn, "scope-admitted-before-failure", genome=candidate, name="maximum",
        interface="sequence-maximum/1", **condition,
        artifacts_root=roots["artifacts_root"])
    assert replayed == admitted

    future = capability.select(
        dsn, "scope-future-selection", genome=candidate, name="maximum",
        interface="sequence-maximum/1", **condition,
        artifacts_root=roots["artifacts_root"])
    assert future["status"] == "declined"
    assert future["contrary_use"]["episode_id"] == failed_ep.operation_id
    assert future["contrary_use"] == capability.eligibility(
        dsn, genome=candidate, name="maximum", interface="sequence-maximum/1",
        **condition, artifacts_root=roots["artifacts_root"])["contrary_use"]

    other_value = capability.select(
        dsn, "scope-other-value", genome=candidate, name="maximum",
        interface="sequence-maximum/1", task_id=item.digest, value=[1, 3, 4],
        artifacts_root=roots["artifacts_root"])
    assert other_value["status"] == "selected"

    other_task = task.Task(
        "applicability-other-task", "dev", "Same expected output under a distinct task identity.",
        {"answer.json": b"null"}, item.verifier, {"answer.json": b"3"}, item.test_files)
    task.publish(dsn, other_task, **roots)
    other_task_selection = capability.select(
        dsn, "scope-other-task", genome=candidate, name="maximum",
        interface="sequence-maximum/1", task_id=other_task.digest, value=[1, 3, 2],
        artifacts_root=roots["artifacts_root"])
    assert other_task_selection["status"] == "selected"

    alternate_retained_ep, alternate_check = _use(
        env, "scope-alternate-qualified-use", context={}, name="alternate",
        interface="sequence-maximum/2")
    assert alternate_check is not None and alternate_check.passed is True
    alternate_retained = capability.retain(
        dsn, "scope-alternate-retention", genome=candidate, name="alternate",
        episode_id=alternate_retained_ep.operation_id,
        artifacts_root=roots["artifacts_root"])
    assert alternate_retained["status"] == "retained"
    other_method = capability.select(
        dsn, "scope-other-method", genome=candidate, name="alternate",
        interface="sequence-maximum/2", **condition,
        artifacts_root=roots["artifacts_root"])
    assert other_method["status"] == "selected"
