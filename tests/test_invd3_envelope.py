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
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

B3_DB = "inv_d3_b3"
B3_DSN = os.environ.get(
    "INV_D3_B3_DSN",
    "dbname=%s host=/var/run/postgresql user=ubuntu" % B3_DB)
PG_HOST = "/var/run/postgresql"
PG_USER = "ubuntu"
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
    result = method_exec.run_member_out_of_process(
        _member(ENVELOPE_SW_SOURCE, "d3_sweep"), task, max_queries=16)
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
    with pytest.raises(method_exec.MethodExecutionError,
                       match="malformed-result-envelope"):
        method_exec.run_member_out_of_process(
            _member(BARE_CANDIDATE_SOURCE, "d3_bare"), task,
            max_queries=16)


def _make_fresh_db():
    assert "live" not in B3_DSN
    subprocess.run(
        ["createdb", "-h", PG_HOST, "-U", PG_USER, B3_DB],
        check=True, capture_output=True, text=True, timeout=60)
    try:
        from settlement import db
        from experiments.coord02 import experience as E
        db.apply_migrations(B3_DSN, MIGRATIONS)
        E.designate_db(B3_DSN, kind="disposable",
                       purpose="INV-D3 case B3 no-authority refusal pin")
        E.prepare_disposable_db(B3_DSN, MIGRATIONS)
    except Exception:
        subprocess.run(
            ["dropdb", "-h", PG_HOST, "-U", PG_USER, B3_DB],
            capture_output=True, text=True, timeout=60)
        raise


def _drop_db():
    subprocess.run(
        ["dropdb", "-h", PG_HOST, "-U", PG_USER, B3_DB],
        capture_output=True, text=True, timeout=60)


def _row_counts():
    from settlement import db
    counts = {}
    with db.connect(B3_DSN) as conn:
        for table in ("operations", "receipts", "allocations"):
            counts[table] = conn.execute(
                "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    return counts


def test_cli_run_without_authority_refuses_with_zero_writes():
    _make_fresh_db()
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get(
            "PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-m", "experiments.ad01.cli", "run",
             "--dsn", B3_DSN, "--world", "0", "--arm", "I",
             "--seq", "0", "--max-boundaries", "1"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=300, env=env)
        assert proc.returncode == 2, proc.stderr
        assert "explicit caller agenda authority" in proc.stderr
        assert _row_counts() == {"operations": 0, "receipts": 0,
                                 "allocations": 0}
    finally:
        _drop_db()
