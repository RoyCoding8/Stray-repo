"""ENG-SOLV live baseline smoke: ONE model attempt on panel-triangular.

Drives the real incumbent-use path (experiment.run_subsequent_use) with a
live Responses-API gateway adapter: broker admission, inference dispatch,
shared solver validation, sandbox grade, settlement. No retries: whatever
one attempt returns becomes the classified result.

Reads META_API_KEY from the environment; the key is never written to the
evidence bundle. Writes reports/evidence/eng-solv/smoke_result.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
WORKTREE = HERE.parents[3]
sys.path.insert(0, str(WORKTREE / "src"))
sys.path.insert(0, str(WORKTREE / "experiments"))

from fault_tasks import BY_ID
from settlement import db, experiment, store
from settlement.common import Command, ResultCode
from settlement.gateway_http import HttpGatewayAdapter
from settlement.launcher_local import LocalLauncher

EVIDENCE_DIR = WORKTREE / "reports" / "evidence" / "eng-solv"
DSN = "postgresql://ubuntu@/settlement_engsolv?host=/var/run/postgresql"
TASK_ID = "panel-triangular"
GRANT_UNITS = 2_000_000


def _allocation_status(dsn, allocation_id):
    try:
        return store.allocation_status(dsn, allocation_id)
    except Exception as exc:
        return {"error": str(exc)}


def _table(dsn, sql, params=()):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [d[0] for d in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            conn.commit()
    return rows


def main() -> int:
    dsn = DSN
    api_key = os.environ.get("META_API_KEY", "")
    if not api_key:
        raise SystemExit("smoke refused: META_API_KEY is not set")
    model = os.environ.get("SETTLEMENT_MODEL",
                           "muse-spark-1.3-contributor-free")
    endpoint = os.environ.get("SETTLEMENT_GATEWAY_URL",
                              "http://localhost:6446/v1")
    token_cap = experiment.model_token_budget()
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(WORKTREE)).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True,
        cwd=str(WORKTREE)).stdout.strip()
    db.apply_migrations(dsn, WORKTREE / "migrations")
    tag = "engsolv"
    store.seed_grant(dsn, Command(request_id=f"{tag}-grant", payload={
        "version": 1, "charter_text": "eng-solv smoke",
        "authority_grant": {}, "envelopes": {}}))
    seed = store.seed_allocation(dsn, Command(
        request_id=f"{tag}-alloc", payload={
            "allocation_id": f"{tag}-alloc", "domain": "engsolv",
            "authorized": GRANT_UNITS, "max_occupancy": 64}))
    if seed.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SystemExit(f"smoke refused: allocation not admitted: {seed.detail}")
    store.admit_commitment(dsn, Command(request_id=f"{tag}-inv", payload={
        "investigation_id": f"{tag}-inv", "objective": "engsolv",
        "scope": {}, "obligations": {}}))
    before = _allocation_status(dsn, f"{tag}-alloc")
    adapter = HttpGatewayAdapter(endpoint=endpoint, api_key=api_key,
                                 api="responses")
    discovery = str(adapter.check_discovery())
    auth = str(adapter.check_auth())
    task = BY_ID[TASK_ID]
    prompt = experiment._arm_prompt("A", task, {}, None)
    launcher = LocalLauncher(tempfile.mkdtemp(prefix="engsolv-smoke-"))
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tempfile.mkdtemp(prefix="engsolv-artifacts-"),
        launcher=launcher, adapter=adapter, model=model,
        allocation_id=f"{tag}-alloc", investigation_id=f"{tag}-inv",
        episode_id=f"{tag}-smoke", bindings={}, use_task=task,
        grader_path=str(WORKTREE / "experiments" / "run_tests.py"),
        protocol_prefix=tag)
    ops = use["ops"]
    model_rows = _table(
        dsn, "SELECT operation_id, outcome, content FROM receipts"
        " WHERE operation_id = %s ORDER BY created_at",
        (ops["model_op"],))
    grade_rows = _table(
        dsn, "SELECT operation_id, outcome, content FROM receipts"
        " WHERE operation_id = %s ORDER BY created_at",
        (ops["grade_op"],))
    for rows in (model_rows, grade_rows):
        for row in rows:
            content = row.get("content")
            row["content"] = json.loads(json.dumps(content, default=str))
    after = _allocation_status(dsn, f"{tag}-alloc")
    accounting = {op: experiment._op_accounting(dsn, op)
                  for op in (ops["model_op"], ops["grade_op"])}
    bundle = {
        "task": TASK_ID,
        "reference_sha256": hashlib.sha256(
            task["fixed"].encode()).hexdigest(),
        "effective_config": {
            "api": "responses",
            "endpoint_host": "http://localhost:6446/v1",
            "model_requested": model,
            "model_token_cap": token_cap,
            "grant_units": GRANT_UNITS,
            "launcher": "local --allow-uncontained (explicit smoke LS-01)",
            "grader": "experiments/run_tests.py",
            "source_revision": revision,
            "worktree_dirty_at_run": dirty,
            "gateway_timeouts_ms": {
                "connect": 5_000, "read": 60_000, "total": 300_000},
            "discovery": discovery, "auth": auth,
        },
        "request_prompt": prompt,
        "model_receipts": model_rows,
        "accepted_source": use.get("raw_text"),
        "solver_status": use.get("solver_status"),
        "solver_detail": use.get("solver_detail"),
        "grade_class": use.get("grade_class"),
        "grade_detail": use.get("grade_detail"),
        "grade_receipts": grade_rows,
        "outcome": use.get("outcome"),
        "accounting": accounting,
        "allocation_before": before,
        "allocation_after": after,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / "smoke_result.json"
    path.write_text(json.dumps(bundle, indent=2, default=str),
                    encoding="utf-8")
    print(json.dumps({
        "task": TASK_ID, "solver_status": use.get("solver_status"),
        "grade_class": use.get("grade_class"),
        "outcome": use.get("outcome"),
        "evidence": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
