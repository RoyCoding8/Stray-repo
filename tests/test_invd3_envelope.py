"""INV-D3 M4: the construction prompt states the ENTRY return envelope.

The adapter/executor owns the envelope contract. The prompt text carries
the contract rule verbatim, so an independent author who returns the bare
candidate fails in the real child with the documented error instead of a
raw KeyError. Case B3 pins the no-authority CLI refusal with zero writes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from execution_authority import child_error, execution_authority

RUN_TOKEN = "invd3%s" % uuid.uuid4().hex[:8]
MIGRATIONS = ROOT / "migrations"

SW0 = "ad01-w0-dev-sw-00"

ENVELOPE_SW_SOURCE = (
    "def d3_sweep(task, oracle, max_queries=16):\n"
    "    ops = list(task.get(\"ops\", []))\n"
    "    keep = list(range(len(ops)))\n"
    "    used = 0\n"
    "    for pos in range(len(keep) - 1, -1, -1):\n"
    "        if used >= max_queries:\n"
    "            break\n"
    "        trial = [i for i in keep if i != pos]\n"
    "        cand = dict(task)\n"
    "        cand[\"ops\"] = [ops[i] for i in trial]\n"
    "        rep = oracle.query(cand)\n"
    "        used = used + 1\n"
    "        if isinstance(rep, dict) and rep.get(\"verdict\") "
    "== \"preserved\":\n"
    "            keep = trial\n"
    "    best = dict(task)\n"
    "    best[\"ops\"] = [ops[i] for i in keep]\n"
    "    return {\"candidate\": best, \"queries\": used}\n"
)

BARE_CANDIDATE_SOURCE = (
    "def d3_bare(task, oracle, max_queries=16):\n"
    "    return task\n"
)


def _member(source: str, entry: str) -> dict:
    return {"capability_id": "d3-probe",
            "method_source": source, "entry": entry,
            "params": {"max_queries": 16},
            "scope": {"family": "software"}, "authored": False}


def test_prompt_states_entry_envelope_verbatim():
    from experiments.ad01 import construct, method_exec, trajectory
    rule = method_exec.entry_contract()["result_envelope"]["rule"]
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    prompt = construct._prompt(
        task, {"observations": []}, {"max_output_tokens": 512}, None)
    assert rule in prompt


def test_prompt_restores_envelope_when_renderer_drops_it(monkeypatch):
    from experiments.ad01 import construct, method_exec, packet, trajectory
    rule = method_exec.entry_contract()["result_envelope"]["rule"]
    real_render = packet.render_construction_prompt
    monkeypatch.setattr(
        packet, "render_construction_prompt",
        lambda shaped: real_render(shaped).replace(rule, ""))
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    prompt = construct._prompt(
        task, {"observations": []}, {"max_output_tokens": 512}, None)
    assert rule in prompt


def test_documented_envelope_example_runs_through_child():
    from experiments.ad01 import method_exec, trajectory
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    with execution_authority("a56d3envelope") as auth:
        result = method_exec.run_member_out_of_process(
            _member(ENVELOPE_SW_SOURCE, "d3_sweep"), task, max_queries=16,
            dsn=auth["dsn"], allocation_id=auth["allocation_id"],
            operation_id=auth["operation_id"])
    report = trajectory._check(task, result["candidate"])
    assert report["verdict"] == "preserved"
    assert len(result["candidate"]["ops"]) < len(task["ops"])
    assert result["queries"] >= 1


def test_bare_candidate_passes_gate_and_fails_in_child():
    from experiments.ad01 import method_exec, trajectory
    task = trajectory.worlds.load_task(trajectory.worlds.FROZEN_DIR,
                                       SW0)
    assert method_exec.verify_member(
        _member(BARE_CANDIDATE_SOURCE, "d3_bare")) == "d3_bare"
    with execution_authority("a56d3bare") as auth:
        with pytest.raises(method_exec.MethodExecutionError):
            method_exec.run_member_out_of_process(
                _member(BARE_CANDIDATE_SOURCE, "d3_bare"), task,
                max_queries=16,
                dsn=auth["dsn"], allocation_id=auth["allocation_id"],
                operation_id=auth["operation_id"])
        assert "malformed-result-envelope" in child_error(
            auth["dsn"], auth["operation_id"]), (
            "the entry passed verify_member and returned the bare task, so the "
            "envelope refusal is the child's and lives in the receipt it "
            "settled")


def test_the_case_b3_store_is_named_for_this_run_not_for_the_file():
    """A name spelled once at module scope is a database the next run destroys.

    `inv_d3_b3` outlives this process, so whoever runs the suite next creates
    it, fails on "already exists", and on teardown drops the database a
    concurrent run is still writing to. The store this module's setup builds
    must carry this run's token, and a second store derived in the same
    process must differ.
    """
    first = _make_fresh_db()
    try:
        second = _make_fresh_db()
        try:
            assert first.name.startswith("s09iso_"), first.name
            assert RUN_TOKEN in first.name, first.name
            assert "inv_d3_b3" not in first.name, first.name
            assert second.name != first.name
        finally:
            _drop_db(second)
    finally:
        _drop_db(first)


def _make_fresh_db():
    from experiments.ad01.s09_run_isolation import create_disposable_db, \
        drop_disposable_db
    from settlement import db
    from experiments.coord02 import experience as E

    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    b3_dsn = database.dsn
    assert "live" not in b3_dsn, b3_dsn
    try:
        db.apply_migrations(b3_dsn, MIGRATIONS)
        E.designate_db(b3_dsn, kind="disposable",
                       purpose="INV-D3 case B3 no-authority refusal pin")
        E.prepare_disposable_db(b3_dsn, MIGRATIONS)
    except Exception:
        drop_disposable_db(database)
        raise
    return database


def _drop_db(database):
    from experiments.ad01.s09_run_isolation import drop_disposable_db

    drop_disposable_db(database)


def _row_counts(dsn):
    from settlement import db
    counts = {}
    with db.connect(dsn) as conn:
        for table in ("operations", "receipts", "allocations"):
            counts[table] = conn.execute(
                "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    return counts


def test_cli_run_without_authority_refuses_with_zero_writes():
    database = _make_fresh_db()
    b3_dsn = database.dsn
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get(
            "PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-m", "experiments.ad01.cli", "run",
             "--dsn", b3_dsn, "--world", "0", "--arm", "I",
             "--seq", "0", "--max-boundaries", "1"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=300, env=env)
        assert proc.returncode == 2, proc.stderr
        assert "explicit caller agenda authority" in proc.stderr
        assert _row_counts(b3_dsn) == {"operations": 0, "receipts": 0,
                                       "allocations": 0}
    finally:
        _drop_db(database)
