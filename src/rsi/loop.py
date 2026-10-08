"""Bounded, replayable archive exploration at one frozen evaluation budget."""

from pathlib import Path

from settlement import db
from settlement.common import SettlementError

from . import archive, episode, gate, genome, improve, task, verifier


def run(
    dsn: str,
    agent,
    checker,
    *,
    run_id: str,
    epoch: str,
    seed: str,
    generations: int,
    token_allocation: str,
    cpu_allocation: str,
    staging_root: Path,
    artifacts_root: Path,
) -> dict:
    if generations <= 0:
        raise ValueError("generations must be positive")
    plan = {
        "epoch": epoch,
        "seed": seed,
        "generations": generations,
        "token_allocation": token_allocation,
        "cpu_allocation": cpu_allocation,
    }
    archive.record(
        dsn, "loop-start:" + run_id, kind="loop-start", actor="fixed", subject=seed, data=plan
    )
    known = archive.decision(dsn, "loop-end:" + run_id)
    if known:
        return known["data"]
    with db.connect(dsn) as conn:
        specs, raw_budget, scope = conn.execute(
            "SELECT tasks,budget,execution FROM rsi_gate_epochs WHERE digest=%s", (epoch,)
        ).fetchone()
    budget = gate.Budget(**raw_budget)
    if agent.provider.model != budget.model:
        raise SettlementError("loop model differs from frozen budget")
    roots = {"staging_root": staging_root, "artifacts_root": artifacts_root}
    dev = tuple(sorted(d for d, t in specs.items() if t["split"] == "dev"))
    report = {
        "run_id": run_id,
        "scope": scope,
        "epoch": epoch,
        "incumbent": seed,
        "rounds": [],
        "dev": [],
    }
    evaluated = set()

    def evaluate(subject):
        if subject in evaluated:
            return
        current = genome.load(dsn, artifacts_root, subject)
        for digest in dev:
            op = "rsi-dev-" + gate._digest({"run": run_id, "genome": subject, "task": digest})
            item = task.load(dsn, artifacts_root, digest)
            ep = episode.run_episode(
                dsn,
                agent,
                current,
                operation_id=op,
                task=item,
                allocation_id=token_allocation,
                attempt_id=None,
                token_ceiling=budget.token_ceiling,
                timeout_ms=budget.timeout_ms,
                **roots,
            )
            row = {
                "genome": subject,
                "task": digest,
                "episode": op,
                "status": ep.status,
                "passed": None,
                "tokens": ep.tokens,
            }
            report["dev"].append(row)
            if ep.status != "completed":
                if ep.status == "infra_failed":
                    raise SettlementError("dev agent has no outcome: " + ep.status)
                continue
            checked = verifier.verify_episode(
                dsn, agent, checker, op, allocation_id=cpu_allocation, attempt_id=None, **roots
            )
            row.update(status=checked.status, passed=checked.passed, verdict=checked.operation_id)
            if checked.passed is None:
                raise SettlementError("dev verifier has no outcome: " + checked.status)
        evaluated.add(subject)

    stop = "generation limit reached"
    try:
        evaluate(seed)
        for index in range(generations):
            label = run_id + "-" + str(index)
            parent = archive.select_parent(dsn, "parent:" + label, dev)
            # Selected archive nodes may not yet have results on this dev set.
            evaluate(parent)
            proposal = improve.propose(
                dsn,
                agent,
                parent,
                operation_id="rsi-proposal-" + label,
                allocation_id=token_allocation,
                token_ceiling=budget.token_ceiling,
                timeout_ms=budget.timeout_ms,
                **roots,
            )
            row = {"index": index, "parent": parent, "proposal": proposal.__dict__, "gate": None}
            report["rounds"].append(row)
            if proposal.status != "completed":
                if proposal.status in ("infra_failed", "timeout", "over_budget"):
                    stop = "proposal execution stopped: " + proposal.status
                    break
                continue
            evaluate(proposal.child)
            result = gate.run(
                dsn,
                agent,
                checker,
                gate_id="rsi-compare-" + label,
                epoch=epoch,
                parent=parent,
                candidate=proposal.child,
                token_allocation=token_allocation,
                cpu_allocation=cpu_allocation,
                **roots,
            )
            row["gate"] = result
            if result["disposition"] in ("promote", "experimental_gain"):
                report["incumbent"] = proposal.child
            if result["disposition"] == "blocked":
                stop = "gate blocked: " + result["reason"]
                break
            with db.connect(dsn) as conn:
                exposed = conn.execute(
                    "SELECT 1 FROM rsi_anchor_uses WHERE gate=%s", ("rsi-compare-" + label,)
                ).fetchone()
            if exposed:
                stop = "anchor exposure spent; a new comparison needs fresh anchor content"
                break
    except SettlementError as exc:
        stop = str(exc)
    report["stop"] = stop
    archive.record(
        dsn,
        "loop-end:" + run_id,
        kind="loop-end",
        actor="fixed",
        subject=report["incumbent"],
        data=report,
    )
    return report
