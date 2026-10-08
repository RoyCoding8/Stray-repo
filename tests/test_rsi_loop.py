import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from rsi import archive, episode, gate, genome, loop, task
from settlement import db, store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher


def setup(migrated_db, tmp_path):
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    seed = genome.Genome(
        {"AGENTS.md": b"Implement add.", "meta/IMPROVE.md": b"Improve from failures."}
    )
    genome.publish(migrated_db, seed, parent=None, origin="test", **roots)
    tests = b"import unittest\nfrom calc import add\nclass Test(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2,3),5)\n"
    base = task.Task(
        "dev",
        "dev",
        "Implement add.",
        {"calc.py": b"def add(a,b): pass\n"},
        {"test.py": tests},
        {"calc.py": b"def add(a,b): return a+b\n"},
        ("test.py",),
    )
    tasks = tuple(replace(base, name=s, split=s) for s in ("dev", "val", "anchor"))
    for t in tasks:
        task.publish(migrated_db, t, **roots)
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
        codex_cmd=[sys.executable, str(Path(__file__).parent / "fixtures/fake_loop.py")],
        provider=Provider("http://fixture/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS,
    )
    checker = LocalLauncher(tmp_path / "verifiers")
    epoch = gate.freeze(
        migrated_db, tasks, gate.Budget("fixture:free", 5000, 30000), execution="benchmark"
    )
    return roots, seed, tasks, agent, checker, epoch


def test_loop_quarantines_regression_retains_archive_and_replays(migrated_db, tmp_path):
    roots, seed, tasks, agent, checker, epoch = setup(migrated_db, tmp_path)
    kw = dict(
        run_id="run",
        epoch=epoch,
        seed=seed.digest,
        generations=1,
        token_allocation="tokens",
        cpu_allocation="cpu",
        **roots,
    )
    report = loop.run(migrated_db, agent, checker, **kw)
    assert [r["passed"] for r in report["dev"]] == [True, False]
    assert report["rounds"][0]["gate"]["reason"] == "validation score decreased"
    assert report["rounds"][0]["gate"]["disposition"] == "quarantine"
    assert report["incumbent"] == seed.digest
    before = store.allocation_status(migrated_db, "tokens")["consumed"]
    assert loop.run(migrated_db, agent, checker, **kw) == report
    assert store.allocation_status(migrated_db, "tokens")["consumed"] == before
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM rsi_genomes").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM rsi_anchor_uses").fetchone()[0] == 0
    assert archive.decision(migrated_db, "proposal:rsi-proposal-run-0")["actor"] == "ai"
    agent.codex_cmd = [
        sys.executable,
        str(Path(__file__).parent / "fixtures/fake_codex.py"),
        "infra",
    ]
    unknown = episode.run_episode(
        migrated_db,
        agent,
        seed,
        operation_id="latest-unknown",
        task=tasks[0],
        allocation_id="tokens",
        attempt_id=None,
        token_ceiling=5000,
        timeout_ms=30000,
        **roots,
    )
    assert unknown.status == "infra_failed"
    archive.select_parent(migrated_db, "after-unknown", (tasks[0].digest,), draw=0)
    node = next(
        n
        for n in archive.decision(migrated_db, "after-unknown")["data"]["nodes"]
        if n["digest"] == seed.digest
    )
    assert node["score"] == 0 and node["measured"] == 0


def test_loop_can_propose_from_a_dev_timeout_without_assigning_a_score(migrated_db, tmp_path):
    roots, seed, tasks, agent, checker, _ = setup(migrated_db, tmp_path)
    agent.codex_cmd = [
        sys.executable,
        str(Path(__file__).parent / "fixtures/fake_codex.py"),
        "hang",
    ]
    epoch = gate.freeze(
        migrated_db, tasks, gate.Budget("fixture:free", 5000, 1000), execution="benchmark"
    )
    report = loop.run(
        migrated_db,
        agent,
        checker,
        run_id="timeout",
        epoch=epoch,
        seed=seed.digest,
        generations=1,
        token_allocation="tokens",
        cpu_allocation="cpu",
        **roots,
    )
    assert report["dev"][0]["status"] == "timeout" and report["dev"][0]["passed"] is None
    assert report["rounds"][0]["proposal"]["status"] == "timeout"
    assert report["rounds"][0]["gate"] is None
    assert report["stop"] == "proposal execution stopped: timeout"


def test_archive_parent_gain_cannot_replace_an_equally_good_incumbent(
    migrated_db, tmp_path, monkeypatch
):
    roots, seed, tasks, agent, checker, _ = setup(migrated_db, tmp_path)
    weak = genome.Genome({"AGENTS.md": b"Leave stub.", "meta/IMPROVE.md": b"Improve."})
    child = genome.Genome({**seed.files, "meta/IMPROVE.md": b"Revised improver."})
    genome.publish(migrated_db, weak, parent=seed.digest, origin="fixture", **roots)
    genome.publish(migrated_db, child, parent=weak.digest, origin="fixture", **roots)
    # These repeated arithmetic fixtures test controller selection, not independent gain.
    anchors = tuple(replace(tasks[2], name=f"anchor-{i}", instruction=f"Add. Case {i}")
                    for i in range(6))
    for item in anchors:
        task.publish(migrated_db, item, **roots)
    epoch = gate.freeze(migrated_db, (*tasks[:2], *anchors),
                        gate.Budget("fixture:free", 5000, 30000), execution="benchmark")
    agent.codex_cmd = [sys.executable,
                      str(Path(__file__).parent / "fixtures/fake_gate.py")]
    monkeypatch.setattr(archive, "select_parent", lambda *args: weak.digest)
    monkeypatch.setattr(loop.improve, "propose", lambda *args, **kwargs:
                        SimpleNamespace(status="completed", child=child.digest))
    report = loop.run(migrated_db, agent, checker, run_id="incumbent", epoch=epoch,
                      seed=seed.digest, generations=1, token_allocation="tokens",
                      cpu_allocation="cpu", **roots)
    comparison = report["rounds"][0]["gate"]
    assert report["rounds"][0]["parent"] == weak.digest
    assert comparison["parent"] == seed.digest
    assert comparison["anchor_comparison"]["wins"] == 0
    assert comparison["disposition"] == "quarantine"
    assert report["incumbent"] == seed.digest
