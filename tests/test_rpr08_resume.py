"""Fresh-process interruption and resume of a Lane D acquisition run.

Kills the panel runner with SIGKILL mid-task, then resumes it in a new
interpreter. Proof is database-first: sentinel rows committed before the
kill are reused after it (no duplicate step receipts, reused receipts
predate the resume), and the finished panel is checker-clean.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation.experiment import checker
from settlement import db as _db

RUN = str(ROOT / "experiments" / "representation" / "acquire" / "run.py")


def _results(dsn, tag):
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM trial_results"
                        " WHERE assignment_id LIKE %s", ("%%%s%%" % tag,))
            n = cur.fetchone()[0]
            conn.commit()
    return n


def _run_receipts(dsn, tag):
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT operation_id, receipt_identity, created_at"
                        " FROM receipts WHERE operation_id LIKE %s",
                        ("%%rprD-%s-%%" % tag,))
            rows = list(cur.fetchall())
            conn.commit()
    return rows


def _duplicates(dsn, tag):
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT operation_id, receipt_identity, count(*)"
                        " FROM receipts WHERE operation_id LIKE %s"
                        " GROUP BY 1, 2 HAVING count(*) > 1",
                        ("%%rprD-%s-%%" % tag,))
            rows = list(cur.fetchall())
            conn.commit()
    return rows


def test_sigkill_then_resume(migrated_db, tmp_path):
    dsn = migrated_db
    env = dict(os.environ, SETTLEMENT_TEST_DSN=dsn)
    roots = {}
    for key in ("artifacts", "staging", "runs", "evidence"):
        path = tmp_path / key
        path.mkdir(parents=True, exist_ok=True)
        roots[key] = str(path)
    log = open(tmp_path / "run.log", "wb")
    first = subprocess.Popen(
        [sys.executable, RUN, "--tag", "kill",
         "--artifacts-root", roots["artifacts"],
         "--staging-root", roots["staging"],
         "--runs-root", roots["runs"],
         "--evidence-root", roots["evidence"]],
        env=env, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 240
        killed = False
        while time.time() < deadline:
            time.sleep(0.5)
            if first.poll() is not None:
                break
            receipts = _run_receipts(dsn, "kill")
            if len(receipts) >= 3 and not (tmp_path / "evidence" / "index.json").exists():
                first.send_signal(signal.SIGKILL)
                killed = True
                break
        assert killed, "runner finished before the kill window"
        assert first.wait(timeout=60) == -signal.SIGKILL
    finally:
        if first.poll() is None:
            first.kill()
    sentinel_results = _results(dsn, "kill")
    sentinel_receipts = _run_receipts(dsn, "kill")
    assert sentinel_results >= 1
    assert len(sentinel_receipts) >= 3
    resume_start = time.time()
    second = subprocess.run(
        [sys.executable, RUN, "--tag", "kill",
         "--artifacts-root", roots["artifacts"],
         "--staging-root", roots["staging"],
         "--runs-root", roots["runs"],
         "--evidence-root", roots["evidence"]],
        env=env, cwd=str(ROOT), capture_output=True, text=True, timeout=290)
    assert second.returncode == 0, second.stdout[-3000:] + second.stderr[-3000:]
    assert _duplicates(dsn, "kill") == []
    after = _run_receipts(dsn, "kill")
    assert len(after) > len(sentinel_receipts)
    import datetime
    reused = [row for row in after
              if row[2].timestamp() < resume_start]
    assert len(reused) >= len(sentinel_receipts)
    index = json.loads((tmp_path / "evidence" / "index.json").read_bytes())
    assert index["pairs"]["ran"] + index["pairs"]["skipped"] == 45
    assert index["arm_task_records"] == 27
    report = checker.check_all(tmp_path / "evidence", dsn=dsn)
    assert report["clean"], report["problems"]
