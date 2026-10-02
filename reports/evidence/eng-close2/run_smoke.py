"""CLOSE-2 recorded baseline smoke: ONE bounded inference-to-settlement run.

Path: inference -> validation -> source staging -> grading ->
settlement/reporting on panel-triangular via run_subsequent_use with a
live Responses-API gateway adapter. One attempt, no retries except
transport flakes with evidence. Positive outcome NOT required.

Refuses to run on a dirty tree: the recorded smoke needs a clean
recorded revision. Reads META_API_KEY from the environment only; the
bundle carries env-var names, never secret values.

Writes reports/evidence/eng-close2/smoke_close2.json,
reconciliation.json and PROVENANCE.md, then drops the smoke database.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
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

EVIDENCE_DIR = WORKTREE / "reports" / "evidence" / "eng-close2"
DB_NAME = "settlement_close2"
DSN = f"postgresql://ubuntu@/{DB_NAME}?host=/var/run/postgresql"
TASK_ID = "panel-triangular"
GRANT_UNITS = 2_000_000
TAG = "close2"


def _sh(*argv: str) -> str:
    out = subprocess.run(argv, capture_output=True, text=True,
                         cwd=str(WORKTREE))
    if out.returncode != 0:
        raise SystemExit(f"smoke refused: {' '.join(argv)} failed")
    return out.stdout.strip()


def _allocation_status(dsn, allocation_id):
    return store.allocation_status(dsn, allocation_id)


def _table(dsn, sql, params=()):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [d[0] for d in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            conn.commit()
    return rows


def _served_models(endpoint, api_key):
    req = urllib.request.Request(
        f"{endpoint}/models", headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    return [m["id"] for m in body.get("data", [])]


def main() -> int:
    api_key = os.environ.get("META_API_KEY", "")
    if not api_key:
        raise SystemExit("smoke refused: META_API_KEY is not set")
    dirty = _sh("git", "status", "--short")
    if dirty:
        raise SystemExit(f"smoke refused: tree is not clean:\n{dirty}")
    revision = _sh("git", "rev-parse", "HEAD")
    model = os.environ.get("SETTLEMENT_MODEL", "")
    if not model:
        raise SystemExit("smoke refused: SETTLEMENT_MODEL is not set")
    endpoint = os.environ.get("SETTLEMENT_GATEWAY_URL",
                              "http://localhost:6446/v1")
    served = _served_models(endpoint, api_key)
    if model not in served:
        raise SystemExit(
            f"smoke refused: model {model} not in served list {served}")
    token_cap = experiment.model_token_budget()
    subprocess.run(["dropdb", "--if-exists", DB_NAME], check=True)
    subprocess.run(["createdb", DB_NAME], check=True)
    dsn = DSN
    try:
        return _run(dsn, revision, model, endpoint, token_cap)
    finally:
        _verify_bundle()
        subprocess.run(["dropdb", "--if-exists", DB_NAME], check=True)


def _run(dsn, revision, model, endpoint, token_cap) -> int:
    db.apply_migrations(dsn, WORKTREE / "migrations")
    tag = TAG
    store.seed_grant(dsn, Command(request_id=f"{tag}-grant", payload={
        "version": 1, "charter_text": "eng-close2 recorded smoke",
        "authority_grant": {}, "envelopes": {}}))
    seed = store.seed_allocation(dsn, Command(
        request_id=f"{tag}-alloc", payload={
            "allocation_id": f"{tag}-alloc", "domain": "close2",
            "authorized": GRANT_UNITS, "max_occupancy": 64}))
    if seed.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SystemExit(f"smoke refused: allocation not admitted: {seed.detail}")
    store.admit_commitment(dsn, Command(request_id=f"{tag}-inv", payload={
        "investigation_id": f"{tag}-inv", "objective": "close2",
        "scope": {}, "obligations": {}}))
    before = _allocation_status(dsn, f"{tag}-alloc")
    adapter = HttpGatewayAdapter(endpoint=endpoint, api_key=os.environ.get(
        "META_API_KEY", ""), api="responses")
    discovery = str(adapter.check_discovery())
    auth = str(adapter.check_auth())
    task = BY_ID[TASK_ID]
    prompt = experiment._arm_prompt("A", task, {}, None)
    launcher = LocalLauncher(tempfile.mkdtemp(prefix="close2-smoke-"))
    use = experiment.run_subsequent_use(
        dsn, artifacts_root=tempfile.mkdtemp(prefix="close2-artifacts-"),
        launcher=launcher, adapter=adapter, model=model,
        allocation_id=f"{tag}-alloc", investigation_id=f"{tag}-inv",
        episode_id=f"{tag}-smoke", bindings={}, use_task=task,
        grader_path=str(WORKTREE / "experiments" / "run_tests.py"),
        protocol_prefix=tag)
    ops = use["ops"]
    op_ids = sorted(set(ops.values()))
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
            row["content"] = json.loads(json.dumps(row["content"],
                                                   default=str))
    after = _allocation_status(dsn, f"{tag}-alloc")
    accounting = {op: experiment._op_accounting(dsn, op) for op in op_ids}
    reservations = {op: _table(
        dsn, "SELECT r.id, r.amount, r.state, r.allocation_id FROM reservations r"
        " JOIN operations o ON o.reservation_id = r.id WHERE o.id = %s",
        (op,)) for op in op_ids}
    expenditures = _table(
        dsn, "SELECT protocol_id, category, amount, note FROM expenditure_ledger"
        " WHERE note LIKE %s", (f"%{tag}%",))
    contract_sha = hashlib.sha256(
        experiment.SOLVER_SOURCE_CONTRACT.encode()).hexdigest()
    bundle = {
        "task": TASK_ID,
        "reference_sha256": hashlib.sha256(
            task["fixed"].encode()).hexdigest(),
        "effective_config": {
            "api": "responses",
            "endpoint_host": "http://localhost:6446/v1",
            "endpoint_env": "SETTLEMENT_GATEWAY_URL",
            "key_env": "META_API_KEY",
            "model_env": "SETTLEMENT_MODEL",
            "model_requested": model,
            "model_token_cap": token_cap,
            "model_token_cap_env": "SETTLEMENT_MODEL_TOKENS",
            "grant_units": GRANT_UNITS,
            "launcher": "local --allow-uncontained (explicit smoke LS-01)",
            "launcher_profile": LocalLauncher.profile,
            "grader": "experiments/run_tests.py",
            "source_revision": revision,
            "worktree_dirty_at_run": "",
            "solver_contract": "experiment.SOLVER_SOURCE_CONTRACT",
            "solver_contract_sha256": contract_sha,
            "gateway_timeouts_ms": {
                "connect": 5_000, "read": 60_000, "total": 300_000},
            "discovery": discovery, "auth": auth,
        },
        "request_prompt": prompt,
        "model_receipts": model_rows,
        "raw_transport_note": "adapter captures decoded logical output text "
        "only; raw provider transport bytes are not retained",
        "accepted_source": use.get("raw_text"),
        "solver_status": use.get("solver_status"),
        "solver_detail": use.get("solver_detail"),
        "grade_class": use.get("grade_class"),
        "grade_detail": use.get("grade_detail"),
        "grade_receipts": grade_rows,
        "outcome": use.get("outcome"),
        "accounting": accounting,
        "reservations": reservations,
        "expenditures": expenditures,
        "allocation_before": before,
        "allocation_after": after,
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "smoke_close2.json").write_text(
        json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    recon = _reconcile(bundle)
    (EVIDENCE_DIR / "reconciliation.json").write_text(
        json.dumps(recon, indent=2, default=str), encoding="utf-8")
    (EVIDENCE_DIR / "PROVENANCE.md").write_text(
        _provenance(bundle, recon), encoding="utf-8")
    print(json.dumps({
        "task": TASK_ID, "solver_status": use.get("solver_status"),
        "grade_class": use.get("grade_class"),
        "outcome": use.get("outcome"),
        "consumed_delta": recon["consumed_delta"],
        "settled_sum": recon["settled_sum"],
        "reconciled": recon["reconciled"]}, indent=2))
    return 0


def _reconcile(bundle) -> dict:
    per_op = {}
    for op_id, entry in bundle["accounting"].items():
        reserved = int(entry.get("reserved", 0) or 0)
        settled = int(entry.get("settled", 0) or 0)
        unresolved = int(entry.get("unresolved", 0) or 0)
        per_op[op_id] = {
            "reserved": reserved, "settled": settled,
            "unresolved": unresolved,
            "parts_sum_to_reserved": settled + unresolved == reserved,
            "reservation_rows": bundle["reservations"].get(op_id, []),
        }
    ops = sorted(set(bundle["accounting"]))
    before = int((bundle["allocation_before"] or {}).get("consumed", 0) or 0)
    after = int((bundle["allocation_after"] or {}).get("consumed", 0) or 0)
    consumed_delta = after - before
    settled_sum = sum(v["settled"] for v in per_op.values())
    expended = sum(int(r.get("amount", 0) or 0)
                   for r in bundle.get("expenditures", []))
    historical = {
        "model_reserved": 8344, "grade_reserved": 111,
        "per_op_settled_sum": 111, "consumed_delta": 8455,
        "arithmetic": "8455 == 8344 + 111; per-op settled sum 111 != 8455 "
        "because the earlier lane state debited the released model "
        "reservation to consumed without a settled charge, while its "
        "per-operation record read settled 0 / unresolved 0. Preserved "
        "as observed; not recomputed.",
    }
    return {
        "unique_operations": ops,
        "unique_operation_count": len(ops),
        "per_operation": per_op,
        "consumed_before": before, "consumed_after": after,
        "consumed_delta": consumed_delta, "settled_sum": settled_sum,
        "expenditure_ledger_sum": expended,
        "reconciled": consumed_delta == settled_sum,
        "historical_lane_state": historical,
    }


def _provenance(bundle, recon) -> str:
    cfg = bundle["effective_config"]
    lines = [
        "# CLOSE-2 recorded smoke provenance",
        "",
        f"- task: {bundle['task']} (visible-regression, same as historical smoke)",
        f"- source_revision: {cfg['source_revision']} (tree clean at run)",
        f"- solver_contract_sha256: {cfg['solver_contract_sha256']}",
        f"- reference_sha256: {bundle['reference_sha256']}",
        f"- gateway: {cfg['endpoint_host']} api={cfg['api']} "
        f"discovery={cfg['discovery']} auth={cfg['auth']}",
        f"- env names only: {cfg['endpoint_env']}, {cfg['key_env']}, "
        f"{cfg['model_env']}, {cfg['model_token_cap_env']}",
        f"- model_requested: {cfg['model_requested']}",
        f"- launcher: {cfg['launcher']} profile={cfg['launcher_profile']}",
        f"- outcome: {bundle['outcome']} solver={bundle['solver_status']} "
        f"grade={bundle['grade_class']} ({bundle['grade_detail']})",
        f"- unique operations: {recon['unique_operation_count']} "
        f"{recon['unique_operations']}",
        f"- consumed {recon['consumed_before']} -> {recon['consumed_after']} "
        f"(delta {recon['consumed_delta']}); settled sum {recon['settled_sum']}; "
        f"reconciled={recon['reconciled']}",
        "",
        "Historical 8344/111/111/8455 reads under the integrated accounting "
        "as: model reservation 8344 released-or-settled per reservation row, "
        "grade 111 settled, consumed delta equal to the settled sum over "
        "unique operations. See reconciliation.json; the original "
        "reports/evidence/eng-solv/smoke_result.json is preserved untouched.",
        "",
    ]
    return "\n".join(lines)


def _verify_bundle() -> None:
    for name in ("smoke_close2.json", "reconciliation.json", "PROVENANCE.md"):
        path = EVIDENCE_DIR / name
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"bundle incomplete: {name} missing or empty")
    json.loads((EVIDENCE_DIR / "smoke_close2.json").read_text())
    json.loads((EVIDENCE_DIR / "reconciliation.json").read_text())


if __name__ == "__main__":
    raise SystemExit(main())
