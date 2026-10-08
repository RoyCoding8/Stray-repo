from __future__ import annotations

from pathlib import Path

import pytest

from rsi import genome as g
from settlement import artifacts, db
from settlement.common import Command

SEED = {
    "AGENTS.md": b"# Rules\n- Edit files with apply_patch.\n",
    "skills/run-tests/SKILL.md": b"---\nname: run-tests\ndescription: run pytest\n---\nRun `python -m pytest -q`.\n",
    "harness.toml": b'model_reasoning_effort = "high"\n',
    "meta/IMPROVE.md": b"Read the failures, change one thing.\n",
}


def test_digest_is_content_identity():
    a = g.Genome(SEED)
    b = g.Genome(dict(reversed(list(SEED.items()))))
    c = g.Genome({**SEED, "AGENTS.md": b"# Rules\n"})
    assert a.digest == b.digest
    assert a.digest != c.digest
    assert len(a.digest) == 64


@pytest.mark.parametrize("rel", ["README.md", "skills", "src/x.py", "../AGENTS.md", "meta"])
def test_files_outside_layout_are_refused(rel):
    with pytest.raises(g.GenomeError):
        g.Genome({rel: b"x"})


def test_harness_toml_cannot_set_kernel_keys():
    with pytest.raises(g.GenomeError, match="kernel-owned"):
        g.Genome({"harness.toml": b'model = "gpt-6"\n'})
    with pytest.raises(g.GenomeError, match="parse"):
        g.Genome({"harness.toml": b"not = [toml"})
    assert g.settings(g.Genome(SEED)) == {"model_reasoning_effort": "high"}


def test_materialize_places_task_agent_view_only(tmp_path: Path):
    placed = g.materialize(g.Genome(SEED), tmp_path)
    assert sorted(placed) == [".agents/skills/run-tests/SKILL.md", "AGENTS.md"]
    assert (tmp_path / "AGENTS.md").read_text() == (
        "# Rules\n- Edit files with apply_patch.\n\n## Skills\n\n"
        "Each skill is a folder with a SKILL.md. Read the SKILL.md before starting"
        " a task its description matches.\n\n"
        "- run-tests: run pytest (file: .agents/skills/run-tests/SKILL.md)\n")
    assert not (tmp_path / "meta").exists()
    assert not (tmp_path / "harness.toml").exists()


def test_skill_without_frontmatter_is_refused():
    with pytest.raises(g.GenomeError, match="frontmatter"):
        g.Genome({"skills/x/SKILL.md": b"just text\n"})


def test_publish_load_round_trip_and_lineage(migrated_db, tmp_path: Path):
    dsn = migrated_db
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    seed = g.Genome(SEED)
    assert g.publish(dsn, seed, parent=None, origin="seed", **roots) == seed.digest
    assert g.publish(dsn, seed, parent=None, origin="seed", **roots) == seed.digest
    child = g.Genome({**SEED, "AGENTS.md": b"# Rules v2\n"})
    g.publish(dsn, child, parent=seed.digest, origin="meta-agent", **roots)
    loaded = g.load(dsn, roots["artifacts_root"], child.digest)
    assert loaded.files == child.files and loaded.digest == child.digest
    # Rediscovery from another parent keeps one content identity and its first edge.
    assert g.publish(dsn, child, parent=None, origin="rediscovered", **roots) == child.digest
    with pytest.raises(g.GenomeError, match="unknown parent"):
        g.publish(dsn, g.Genome({"AGENTS.md": b"orphan\n"}), parent="0" * 64,
                  origin="x", **roots)


def test_recorded_genome_survives_retirement_and_gc(migrated_db, tmp_path):
    seed = g.Genome(SEED)
    roots = {"staging_root": tmp_path / "stage", "artifacts_root": tmp_path / "art"}
    for _ in range(2):
        g.publish(migrated_db, seed, parent=None, origin="test", **roots)
    with db.connect(migrated_db) as conn:
        assert conn.execute("SELECT protection_count FROM artifact_versions WHERE digest = %s",
                            (seed.digest,)).fetchone()[0] == 1
    artifacts.retire_artifact(migrated_db, Command(request_id="retire-seed", payload={}), seed.digest)
    assert artifacts.collect_garbage(migrated_db, roots["artifacts_root"]) == {
        "removed": [], "kept": [seed.digest]}
    assert g.load(migrated_db, roots["artifacts_root"], seed.digest).files == SEED
