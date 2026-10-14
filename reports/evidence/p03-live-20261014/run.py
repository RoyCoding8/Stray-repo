"""Coordinator for the single frozen P03 qualification; never retries a cell."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=("prepare", "run"))
parser.add_argument("--repository", type=Path, required=True)
parser.add_argument("--private-root", type=Path, required=True)
parser.add_argument("--evidence-root", type=Path, required=True)
parser.add_argument("--route-envfile", type=Path)
parser.add_argument("--codex-cmd", nargs="+")
parser.add_argument("--admin-dsn", default="dbname=postgres host=127.0.0.1 port=55432 user=postgres")
args = parser.parse_args()
repository = args.repository.resolve()
sys.path[:0] = [str(repository), str(repository / "src")]
from experiments.context03 import driver, recompute  # noqa: E402


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def source_hashes():
    paths = [*driver._source_digests(repository), "experiments/context03/driver.py",
             "experiments/context03/recompute.py"]
    return {path: hashlib.sha256((repository / path).read_bytes()).hexdigest() for path in paths}


manifest_path = args.evidence_root / "manifest.json"
if args.command == "prepare":
    if manifest_path.exists():
        raise SystemExit("The prospective manifest already exists; do not refreeze.")
    order = list(driver.MATRIX)
    random.Random(20261014).shuffle(order)
    manifest = {
        "schema": "p03-live-campaign/1", "matrix": [list(pair) for pair in driver.MATRIX],
        "run_order": [list(pair) for pair in order], "order_seed": 20261014,
        "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip(),
        "source_sha256": source_hashes(), "model_alias": driver.LIVE_ALIAS,
        "live_worker_actions_max": 6, "worker_actions_per_cell_max": 1,
        "worker_timeout_ms": driver.TIMEOUT_MS, "worker_token_allowance": driver.LIVE_TOKEN_CAP,
        "request_retries": 0, "stream_retries": 0,
        "limits": "Six bounded worker invocations, not six provider HTTP turns or an invoice ceiling.",
        "grading": "Unchanged pristine maximum task; fixture priors and authored claims.",
        "underlying_model": "Dynamic free router; underlying provider model is not pinned.",
        "databases": {driver.Cell(*pair).id: "p03_live_20261014_" + str(i + 1)
                      for i, pair in enumerate(order)},
    }
    save(manifest_path, manifest)
    print("Prospective manifest prepared; no database or model effect.")
else:
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["source_sha256"] != source_hashes():
        raise SystemExit("Runtime source differs from the prospective freeze.")
    if not args.route_envfile or not args.codex_cmd:
        raise SystemExit("Run requires the external route envfile and Codex command.")
    records = []
    for policy, condition in manifest["run_order"]:
        cell = driver.Cell(policy, condition)
        database = manifest["databases"][cell.id]
        with psycopg.connect(args.admin_dsn, autocommit=True) as conn:
            # Existing databases cause refusal. No cell, operation or allocation is replayed.
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        dsn = make_conninfo(**{**conninfo_to_dict(args.admin_dsn), "dbname": database})
        options = SimpleNamespace(dsn=dsn, run_root=args.private_root,
                                  evidence_root=args.evidence_root, policy=policy,
                                  condition=condition, mode="live", route_envfile=args.route_envfile,
                                  codex_cmd=args.codex_cmd)
        print(f"Starting {cell.id}", flush=True)
        path = driver.run_cell(options)
        record = json.loads(path.read_text(encoding="utf-8"))
        records.append(record)
        print(f"Completed {cell.id}: {record['build_status']}", flush=True)
    save(args.evidence_root / "result.json", recompute.recompute(manifest, records))
    print("Nine-cell bounded comparison exported and recomputed.", flush=True)
