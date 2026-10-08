import json
import sys
from pathlib import Path

import pytest

from rsi import archive, episode, genome, synthesis, task, verifier
from settlement import db, store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher


@pytest.mark.parametrize(
    "mode,status,count",
    [("valid", "qualified", 2), ("bad-reference", "rejected", 1), ("passing-stub", "rejected", 1)],
)
def test_synthesized_task_is_qualified_before_dev_publication(
    migrated_db, tmp_path, monkeypatch, mode, status, count
):
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    seed = genome.Genome(
        {"AGENTS.md": b"Leave stub.", "meta/IMPROVE.md": b"Improve from failures."}
    )
    genome.publish(migrated_db, seed, parent=None, origin="test", **roots)
    base = task.Task(
        "calc",
        "dev",
        "Implement add.",
        {"calc.py": b"def add(a,b): pass\n"},
        {
            "test.py": b"import unittest\nfrom calc import add\nclass Test(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2,3),5)\n"
        },
        {"calc.py": b"def add(a,b): return a+b\n"},
        ("test.py",),
    )
    task.publish(migrated_db, base, **roots)
    for name, domain in (("tokens", "tokens"), ("cpu", "cpu")):
        store.seed_allocation(
            migrated_db,
            Command(
                request_id=name,
                payload={"allocation_id": name, "domain": domain, "authorized": 100000},
            ),
        )
    agent = CodexLauncher(
        tmp_path / "runs",
        codex_cmd=[sys.executable, str(Path(__file__).parent / "fixtures/fake_synthesis.py"), mode],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS,
    )
    checker = LocalLauncher(tmp_path / "verifiers")
    episode.run_episode(
        migrated_db,
        agent,
        seed,
        operation_id="failed-dev",
        task=base,
        allocation_id="tokens",
        attempt_id=None,
        token_ceiling=5000,
        timeout_ms=30000,
        **roots,
    )
    assert (
        verifier.verify_episode(
            migrated_db, agent, checker, "failed-dev", allocation_id="cpu", attempt_id=None, **roots
        ).passed
        is False
    )
    kw = dict(
        operation_id="synthesize",
        token_allocation="tokens",
        cpu_allocation="cpu",
        token_ceiling=5000,
        timeout_ms=30000,
        **roots,
    )
    if mode == "valid":
        with monkeypatch.context() as m:

            def crash(*args, **kwargs):
                raise RuntimeError("interrupted before dev publication")

            m.setattr(task, "publish", crash)
            with pytest.raises(RuntimeError, match="interrupted"):
                synthesis.run(migrated_db, agent, checker, seed.digest, **kw)
        ws, _ = agent.exec_dirs("synthesize", "")
        (Path(ws) / "task.json").write_text("{}")
    report = synthesis.run(migrated_db, agent, checker, seed.digest, **kw)
    assert report["status"] == status
    assert archive.decision(migrated_db, "synthesis-output:synthesize")["actor"] == "ai"
    assert archive.decision(migrated_db, "synthesis:synthesize")["actor"] == "fixed"
    assert report["checks"]["reference"]["passed"] is (mode != "bad-reference")
    assert report["checks"]["stub"]["passed"] is (mode == "passing-stub")
    if mode == "valid":
        current = task.load(migrated_db, roots["artifacts_root"], report["task"])
        assert current.name == "double" and current.split == "dev"
        assert current.reference["double.py"] == b"def double(n): return 2*n\n"
    else:
        assert report["task"] is None
    consumed = store.allocation_status(migrated_db, "tokens")["consumed"]
    assert synthesis.run(migrated_db, agent, checker, seed.digest, **kw) == report
    assert store.allocation_status(migrated_db, "tokens")["consumed"] == consumed
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM rsi_tasks").fetchone()[0] == count


def test_synthesis_cannot_choose_split_runtime_or_driver():
    with pytest.raises(ValueError, match="fixed schema"):
        synthesis.parse(
            json.dumps({"split": "anchor", "runtime": "fake", "driver": "skip tests"}).encode()
        )
