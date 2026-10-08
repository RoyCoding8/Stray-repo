"""Run a cooperative RSI experiment on a qualified bank using an external route file."""

import argparse
import json
from pathlib import Path

from settlement import db, store
from settlement.common import Command, ResultCode, SettlementError
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

from . import archive, gate, genome, loop, task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--bank-report", type=Path, required=True)
    parser.add_argument("--route-file", type=Path, required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--generations", type=int, default=2)
    parser.add_argument("--tokens", type=int, default=150000)
    parser.add_argument("--timeout-ms", type=int, default=180000)
    parser.add_argument("--dev", nargs="+", required=True)
    parser.add_argument("--val", nargs="+", required=True)
    parser.add_argument("--anchor", nargs="+", required=True)
    parser.add_argument("--migrations", type=Path)
    args = parser.parse_args()
    if args.generations <= 0:
        parser.error("generations must be positive")
    root = args.root.resolve()
    roots = {"staging_root": root / "stage", "artifacts_root": root / "art"}
    bank = json.loads(args.bank_report.read_text(encoding="utf-8"))
    if bank["sanity_passed"] is not True:
        parser.error("bank references and stubs must qualify before model execution")
    rows = {r["name"]: r for r in bank["sanity"]}
    selected = []
    for split in task.SPLITS:
        for name in getattr(args, split):
            row = rows[name]
            if (
                row["split"] != split
                or row["reference"]["passed"] is not True
                or row["stub"]["passed"] is not False
            ):
                parser.error("task split or sanity mismatch: " + name)
            selected.append(task.load(args.dsn, roots["artifacts_root"], row["task"]))
    route = dict(
        line.split("=", 1)
        for line in args.route_file.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    provider = Provider(
        route["SETTLEMENT_GATEWAY_ENDPOINT"],
        route["SETTLEMENT_GATEWAY_MODEL"],
        route["SETTLEMENT_GATEWAY_KEY"],
    )
    budget = gate.Budget(provider.model, args.tokens, args.timeout_ms)
    if args.migrations:
        db.apply_migrations(args.dsn, args.migrations)
    seed = genome.from_dir(args.seed.resolve())
    genome.publish(args.dsn, seed, parent=None, origin="seed:" + args.run_id, **roots)
    epoch = gate.freeze(args.dsn, tuple(selected), budget, execution="benchmark")
    # Reserve the upper bound before execution, including validation/regression.
    calls = len(args.dev) + (
        args.generations * (1 + 3 * len(args.dev) + 3 * len(args.val) + 2 * len(args.anchor))
    )
    allocations = {}
    for domain, amount in (("tokens", calls * args.tokens), ("cpu", calls * 120)):
        allocation = "rsi-" + args.run_id + "-" + domain
        allocations[domain] = allocation
        if archive.decision(args.dsn, "loop-start:" + args.run_id) is None:
            result = store.seed_allocation(
                args.dsn,
                Command(
                    request_id=allocation,
                    payload={"allocation_id": allocation, "domain": domain, "authorized": amount},
                ),
            )
            if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
                raise SettlementError(result.detail)
    agent = CodexLauncher(
        root / "runs",
        codex_cmd=[args.codex],
        provider=provider,
        allowed_overrides=genome.HARNESS_KEYS,
    )
    checked = LocalLauncher(root / "verifiers")
    report = loop.run(
        args.dsn,
        agent,
        checked,
        run_id=args.run_id,
        epoch=epoch,
        seed=seed.digest,
        generations=args.generations,
        token_allocation=allocations["tokens"],
        cpu_allocation=allocations["cpu"],
        **roots,
    )
    report["allocations"] = {}
    for domain, allocation in allocations.items():
        status = store.allocation_status(args.dsn, allocation)
        report["allocations"][domain] = {
            field: status[field] for field in ("authorized", "reserved", "consumed")
        }
    output = root / (args.run_id + "-report.json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {"report": str(output), "rounds": len(report["rounds"]), "stop": report["stop"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
