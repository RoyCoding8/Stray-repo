from dataclasses import replace
import json
from pathlib import Path
import sys
import uuid

import pytest

from rsi import episode, genome, task, task_bank, verifier
from settlement import artifacts, db, store
from settlement.common import Command, SettlementError
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

TESTS = b"""import unittest
from calc import add
class CalcTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
"""
TASK = task.Task("calc", "dev", "Implement add.",
                 {"calc.py": b"def add(a, b):\n    pass\n"},
                 {"calc_test.py": TESTS},
                 {"calc.py": b"def add(a, b):\n    return a + b\n"}, ("calc_test.py",))
FAKE = str(Path(__file__).parent / "fixtures/fake_codex.py")


def cmd(payload):
    return Command(request_id=uuid.uuid4().hex, payload=payload)


def test_task_identity_pins_bytes_split_and_evaluator():
    assert replace(TASK).digest == TASK.digest
    for changed in (replace(TASK, instruction="new instruction"),
                    replace(TASK, split="anchor"),
                    replace(TASK, workspace={"calc.py": b"x = 2"}),
                    replace(TASK, reference={"calc.py": b"x = 3"}),
                    replace(TASK, verifier={"calc_test.py": TESTS + b"# new version\n"}),
                    replace(TASK, driver=TASK.driver + b"\n")):
        assert changed.digest != TASK.digest
    assert replace(TASK, split="anchor").evaluator_version == TASK.evaluator_version
    assert replace(TASK, driver=TASK.driver + b"\n").evaluator_version != TASK.evaluator_version
    with pytest.raises(TypeError):
        TASK.workspace["calc.py"] = b"changed"


@pytest.mark.parametrize("workspace", [
    {"../calc.py": b""}, {"C:/calc.py": b""}, {"C:calc.py": b""},
    {"dir\\..\\calc.py": b""}, {"\\calc.py": b""}, {"_rsi_verify.py": b""},
    {"calc.py": b"", "CALC.py": b""}, {"calc.py": b"", "calc.py/a": b""},
])
def test_task_rejects_unsafe_solution_slots(workspace):
    with pytest.raises(SettlementError, match="path|collide|reserved|rejected"):
        replace(TASK, workspace=workspace, reference=workspace)


def test_task_rejects_solution_verifier_directory_alias():
    with pytest.raises(task.TaskError, match="paths collide"):
        replace(TASK, workspace={"tests": b""}, reference={"tests": b""},
                verifier={"tests/calc_test.py": TESTS}, test_files=("tests/calc_test.py",))


def test_exercism_import_is_deterministic_and_keeps_helper_with_verifier(tmp_path):
    root = tmp_path / "paasio"
    (root / ".docs").mkdir(parents=True)
    (root / ".meta").mkdir()
    (root / ".docs/instructions.md").write_text("Implement paasio.")
    (root / ".docs/instructions.append.md").write_text("Extra instructions.")
    for rel, raw in {"paasio.py": b"pass", "paasio_test.py": b"import test_utils",
                     "test_utils.py": b"x = 1", ".meta/example.py": b"x = 2"}.items():
        (root / rel).write_bytes(raw)
    first, = task.from_exercism(tmp_path)
    again, = task.from_exercism(tmp_path)
    assert first == again
    assert set(first.workspace) == {"paasio.py"}
    assert set(first.verifier) == {"paasio_test.py", "test_utils.py"}
    assert first.instruction == "Implement paasio.\nExtra instructions."
    # These are fixed buckets, independent of ordering or which other tasks exist.
    assert task.split_for("calc") == "dev"


@pytest.fixture
def env(migrated_db, tmp_path):
    dsn = migrated_db
    store.seed_allocation(dsn, cmd({"allocation_id": "cpu", "domain": "cpu",
                                    "authorized": 10000}))
    store.seed_allocation(dsn, cmd({"allocation_id": "tokens", "domain": "tokens",
                                    "authorized": 100000}))
    store.admit_commitment(dsn, cmd({"investigation_id": "i", "objective": "verify"}))
    store.acquire_work(dsn, cmd({"attempt_id": "att", "investigation_id": "i"}))
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    task.publish(dsn, TASK, **roots)
    return dsn, LocalLauncher(tmp_path / "verify"), roots, tmp_path


def check(env, files, op="v1", selected=TASK, **kw):
    dsn, launcher, roots, _ = env
    task.publish(dsn, selected, **roots)
    return verifier.check(dsn, launcher, selected, files, operation_id=op,
                          allocation_id="cpu", attempt_id="att", **roots, **kw)


def test_bank_roundtrip_and_access_labels(env):
    dsn, _, roots, _ = env
    assert task.load(dsn, roots["artifacts_root"], TASK.digest) == TASK
    anchor = replace(TASK, split="anchor")
    task.publish(dsn, anchor, **roots)
    assert task.load(dsn, roots["artifacts_root"], anchor.digest) == anchor
    assert not {TASK.digest, anchor.digest} & {
        r["digest"] for r in artifacts.scoped_artifacts(dsn, "candidate")}
    with db.connect(dsn) as conn:
        assert conn.execute("SELECT access_label FROM artifact_versions WHERE digest = %s",
                            (anchor.digest,)).fetchone() == ("hidden",)
        assert conn.execute("SELECT count(*) FROM rsi_tasks").fetchone() == (2,)
    path = roots["artifacts_root"] / TASK.digest
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(task.TaskError, match="bytes do not match"):
        task.load(dsn, roots["artifacts_root"], TASK.digest)


def test_reference_passes_stub_and_missing_solution_fail_and_replay_never_sends(env):
    reference = check(env, TASK.reference)
    assert reference.passed is True
    assert reference.status == "passed"
    assert reference.detail["data"]["worker"]["data"]["tests"] == 1
    assert reference.detail["containment"] is False
    consumed = store.allocation_status(env[0], "cpu")["consumed"]
    assert check(env, TASK.reference) == reference
    assert store.allocation_status(env[0], "cpu")["consumed"] == consumed
    assert check(env, TASK.workspace, "v2").passed is False
    assert check(env, {}, "v3").passed is False
    with pytest.raises(verifier.VerifierError, match="not admitted"):
        check(env, TASK.workspace)  # same operation id cannot name different bytes
    with pytest.raises(verifier.VerifierError, match="only declared"):
        check(env, {**TASK.reference, "calc_test.py": b""}, "v4")


def test_timeout_empty_test_suite_and_skips_never_pass(env):
    timeout = check(env, {"calc.py": b"while True: pass\n"}, timeout_ms=1000)
    assert timeout.status == "timeout"
    assert timeout.passed is None
    empty = replace(TASK, verifier={"calc_test.py": b"import unittest\n"})
    assert check(env, empty.reference, "empty", empty).status == "infra_failed"
    skipped = replace(TASK, verifier={"calc_test.py": TESTS.replace(
        b"    def test_add", b"    @unittest.skip('disabled')\n    def test_add")})
    assert check(env, skipped.reference, "skipped", skipped).passed is False
    early_exit = check(env, {"calc.py": b"import os; os._exit(0)\n"}, "exit")
    assert early_exit.status == "infra_failed"
    assert early_exit.passed is None


def run_agent(env, selected=TASK, mode="ok"):
    dsn, _, roots, tmp = env
    task.publish(dsn, selected, **roots)
    seed = genome.Genome({"AGENTS.md": b"Implement the solution.\n"})
    genome.publish(dsn, seed, parent=None, origin="test", **roots)
    agent = CodexLauncher(tmp / "agent", codex_cmd=[sys.executable, FAKE, mode],
                          provider=Provider("http://127.0.0.1:9/v1", "m", "k"),
                          allowed_overrides=genome.HARNESS_KEYS)
    result = episode.run_episode(dsn, agent, seed, operation_id="ep", task=selected,
                                 allocation_id="tokens", attempt_id="att",
                                 timeout_ms=30000, token_ceiling=5000, **roots)
    return agent, result


def verify(env, agent):
    dsn, launcher, roots, _ = env
    return verifier.verify_episode(dsn, agent, launcher, "ep", allocation_id="cpu",
                                   attempt_id="att", **roots)


def test_agent_cannot_replace_tests_or_helpers_and_anchor_trajectory_is_hidden(env):
    dsn, _, roots, _ = env
    anchor = replace(TASK, split="anchor")
    agent, result = run_agent(env, anchor)
    assert not (result.workspace / "calc_test.py").exists()
    (result.workspace / "calc_test.py").write_bytes(b"# all tests deleted\n")
    (result.workspace / "sitecustomize.py").write_bytes(b"raise RuntimeError('injected')\n")
    (result.workspace / "calc.py").write_bytes(anchor.reference["calc.py"])
    verdict = verify(env, agent)
    assert verdict.passed is True
    with db.connect(dsn) as conn:
        labels = conn.execute("SELECT access_label FROM artifact_versions WHERE digest = ANY(%s)",
                              ([anchor.digest, result.trajectory, verdict.solution],)).fetchall()
        assert labels == [("hidden",)] * 3
        assert conn.execute("SELECT count(*) FROM rsi_verdicts").fetchone() == (1,)
    (result.workspace / "calc.py").unlink()
    assert verify(env, agent) == verdict
    package = json.loads((roots["artifacts_root"] / verdict.solution).read_bytes())
    assert set(package["files"]) == {"calc.py"}


def test_settled_verifier_recovers_record_after_workspace_changed(env, monkeypatch):
    dsn, _, _, _ = env
    agent, result = run_agent(env)
    (result.workspace / "calc.py").write_bytes(TASK.reference["calc.py"])
    transact = store.transact

    def crash(dsn, command, fn, **kwargs):
        if command.request_id.startswith("rsi-verdict-"):
            raise RuntimeError("crashed after settlement")
        return transact(dsn, command, fn, **kwargs)

    with monkeypatch.context() as m:
        m.setattr(store, "transact", crash)
        with pytest.raises(RuntimeError, match="crashed after settlement"):
            verify(env, agent)
    consumed = store.allocation_status(dsn, "cpu")["consumed"]
    (result.workspace / "calc.py").write_bytes(TASK.workspace["calc.py"])
    assert verify(env, agent).passed is True
    assert store.allocation_status(dsn, "cpu")["consumed"] == consumed


def test_infrastructure_failure_never_gets_task_verdict(env):
    agent, result = run_agent(env, mode="infra")
    assert result.status == "infra_failed"
    with pytest.raises(verifier.VerifierError, match="requires a completed episode"):
        verify(env, agent)
    with db.connect(env[0]) as conn:
        assert conn.execute("SELECT count(*) FROM rsi_verdicts").fetchone() == (0,)


def test_episode_replay_rejects_new_task_identity(env):
    dsn, _, roots, _ = env
    agent, _ = run_agent(env)
    changed = replace(TASK, instruction="Solve a different task.")
    task.publish(dsn, changed, **roots)
    seed = genome.Genome({"AGENTS.md": b"Implement the solution.\n"})
    with pytest.raises(episode.EpisodeError, match="another genome or task"):
        episode.run_episode(dsn, agent, seed, operation_id="ep", task=changed,
                            allocation_id="tokens", attempt_id="att",
                            timeout_ms=30000, token_ceiling=5000, **roots)


def test_episode_rejects_case_alias_for_genome_instructions(env):
    dsn, _, roots, tmp = env
    collision = replace(TASK, workspace={"agents.md": b""}, reference={"agents.md": b""})
    task.publish(dsn, collision, **roots)
    seed = genome.Genome({"AGENTS.md": b"Kernel selected genome instructions.\n"})
    with pytest.raises(episode.EpisodeError, match="collide"):
        episode.run_episode(dsn, LocalLauncher(tmp / "unused"), seed, operation_id="bad",
                            task=collision, allocation_id="tokens", attempt_id="att",
                            timeout_ms=30000, token_ceiling=5000, **roots)
    assert not (tmp / "unused/bad_exec-default.work/inputs/agents.md").exists()


def test_solution_snapshot_rejects_directory_and_link(env):
    tmp = env[3] / "solution"
    tmp.mkdir()
    (tmp / "calc.py").mkdir()
    with pytest.raises(verifier.VerifierError, match="not a regular file"):
        verifier.solution_files(TASK, tmp)
    (tmp / "calc.py").rmdir()
    outside = env[3] / "outside.py"
    outside.write_bytes(TASK.reference["calc.py"])
    try:
        (tmp / "calc.py").symlink_to(outside)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    with pytest.raises(verifier.VerifierError, match="escapes|link"):
        verifier.solution_files(TASK, tmp)


def test_bank_export_qualifies_reference_and_stub_and_uses_lf(migrated_db, tmp_path):
    source = tmp_path / "bank" / "calc"
    (source / ".docs").mkdir(parents=True)
    (source / ".meta").mkdir()
    (source / ".docs/instructions.md").write_text("Implement add.", encoding="utf-8")
    (source / "calc.py").write_bytes(TASK.workspace["calc.py"])
    (source / "calc_test.py").write_bytes(TESTS)
    (source / ".meta/example.py").write_bytes(TASK.reference["calc.py"])
    root = tmp_path / "kernel"
    report = task_bank.import_bank(migrated_db, source.parent, root)
    assert report["sanity_passed"] is True
    assert report["sanity"][0]["reference"]["passed"] is True
    assert report["sanity"][0]["stub"]["passed"] is False
    raw = (root / "bank-report.json").read_bytes()
    assert json.loads(raw)["tasks"] == 1
    assert b"\r" not in raw and raw.endswith(b"\n")
