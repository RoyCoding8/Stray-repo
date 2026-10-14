from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rsi import context, genome, investigate, memory, task
from rsi.investigation import export as export_investigation
from settlement import broker, db, store
from settlement.common import Command, SettlementError
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

POLICIES = ("structured/1", "raw-history/1", "adaptive/1")
CONDITIONS = ("complete", "misleading", "source-removed")
MATRIX = tuple((policy, condition) for policy in POLICIES for condition in CONDITIONS)
LIVE_ALIAS = "openrouter/openrouter/free"
TIMEOUT_MS = 180_000
LIVE_TOKEN_CAP = 500_000
FIXTURE_TOKEN_CAP = 5_000
CPU_CAP = 3_000
TASK_INSTRUCTION = (
    "Implement maximum(xs). Determine the empty-list convention from prior checked "
    "maximum experience and reflect it in the implementation."
)
SOURCE_NONEMPTY = "Implement maximum(xs) for a nonempty list and return its largest value."
SOURCE_EMPTY = (
    "Implement maximum(xs) and return 0 when xs is empty; otherwise return the largest value."
)
LESSON = (
    "sorted(xs)[-1] computes a maximum for nonempty lists but fails on empty lists. "
    "The checked empty-input task specifies a zero default."
)
MISLEADING_LESSON = (
    "The checked empty-input task means an empty list should raise IndexError; "
    "keep sorted(xs)[-1] as the maximum rule."
)


@dataclass(frozen=True)
class Cell:
    policy: str
    condition: str

    @property
    def id(self) -> str:
        return f"p03-context03-{self.policy.replace('/', '-')}-{self.condition}"


FIXTURE_CHILD = r'''from __future__ import annotations
import json, re, sys
from pathlib import Path

args = sys.argv[1:]
log_path = Path(args[0])
if len(args) >= 3 and args[1:3] == ["debug", "models"]:
    print(json.dumps({"models": [{"slug": "gpt-6.1-sol", "context_window": 1024}]}))
    raise SystemExit(0)
if len(args) >= 3 and args[1:3] == ["debug", "prompt-input"]:
    print("[]")
    raise SystemExit(0)
args = args[1:]
if not args or args[0] != "exec":
    raise SystemExit(f"unexpected Codex arguments: {args!r}")
workspace = Path(args[args.index("-C") + 1])
prompt = args[-1]
match = re.search(r"^Continuation \(JSON\):\n(.*?)(?:\n\nInput digest:|\Z)",
                  prompt, re.MULTILINE | re.DOTALL)
continuation = json.loads(match.group(1)) if match else None
packet = continuation.get("context_packet") if isinstance(continuation, dict) else None
view = packet.get("memory_view", {}) if isinstance(packet, dict) else {}
observations = view.get("observations", []) if isinstance(view, dict) else []
claims = view.get("claims", []) if isinstance(view, dict) else []
failed_ids = {
    item.get("observation_id") for item in observations
    if isinstance(item, dict) and item.get("content", {}).get("passed") is False
}
repair = any(
    isinstance(item, dict)
    and item.get("content", {}).get("passed") is False
    and "return 0 when xs is empty" in item.get("content", {}).get("task_instruction", "")
    for item in observations
)
misleading_claim = any(
    isinstance(item, dict) and "empty list should raise IndexError" in item.get("text", "")
    for item in claims
)
contradicted_distractor = any(
    isinstance(item, dict) and item.get("status") == "challenged"
    and "empty list should raise IndexError" in item.get("text", "")
    and failed_ids.intersection(item.get("opposition", []))
    for item in claims
)
repair = repair and (not misleading_claim or contradicted_distractor)
source = (b"def maximum(xs):\n    return max(xs) if xs else 0\n" if repair else
          b"def maximum(xs):\n    return sorted(xs)[-1]\n")
(workspace / "solution.py").write_bytes(source)
if log_path.exists():
    number = sum(1 for _ in log_path.open(encoding="utf-8")) + 1
else:
    number = 1
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"call": number, "prompt": prompt,
        "continuation": continuation, "context_packet": packet,
        "used_checked_empty_evidence": repair,
        "saw_misleading_claim": misleading_claim,
        "rejected_misleading_claim_with_opposition": contradicted_distractor,
        "solution": source.decode()},
        sort_keys=True) + "\n")
for event in ({"type": "thread.started", "thread_id": f"p03-{number}"},
              {"type": "turn.started"},
              {"type": "item.completed", "item": {
                  "type": "command_execution", "command": "write solution.py", "exit_code": 0}},
              {"type": "item.completed", "item": {
                  "type": "agent_message", "text": "Applied checked empty-input evidence." if repair
                  else "No checked empty-input evidence was available."}},
              {"type": "turn.completed", "usage": {"input_tokens": 800,
                  "cached_input_tokens": 0, "output_tokens": 60,
                  "reasoning_output_tokens": 0}}):
    print(json.dumps(event), flush=True)
'''


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8")


def _task(task_id: str, instruction: str, *, empty: bool) -> task.Task:
    tests = (b"import unittest\nfrom solution import maximum\n"
             b"class MaximumTests(unittest.TestCase):\n"
             b"    def test_values(self):\n"
             b"        self.assertEqual(maximum([-8, 2, 5]), 5)\n"
             b"        self.assertEqual(maximum([-8, -2, -5]), -2)\n")
    if empty:
        tests += b"    def test_empty_default(self):\n        self.assertEqual(maximum([]), 0)\n"
    return task.Task(
        task_id, "dev", instruction,
        {"solution.py": b"def maximum(xs):\n    return sorted(xs)[-1]\n"},
        {"test_maximum.py": tests},
        {"solution.py": b"def maximum(xs):\n    return max(xs) if xs else 0\n"},
        ("test_maximum.py",),
    )


def _fresh_database(dsn: str) -> str:
    db.apply_migrations(dsn, Path(__file__).resolve().parents[2] / "migrations")
    with db.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        database_id = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM investigations")
        if cur.fetchone()[0]:
            raise SettlementError("comparison database already contains investigations")
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        tables = [row[0] for row in cur.fetchall() if row[0].startswith("rsi_")]
        for table in tables:
            if table == "rsi_memory_clock":
                cur.execute("SELECT revision FROM rsi_memory_clock WHERE id=1")
                rows = cur.fetchall()
                if rows != [(0,)]:
                    raise SettlementError("comparison database memory revision is not fresh")
                continue
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            if cur.fetchone()[0]:
                raise SettlementError(f"comparison database contains prior {table} rows")
        conn.commit()
    return database_id


def _allocation(dsn: str, identity: str, domain: str, amount: int) -> str:
    allocation_id = f"{identity}-{domain}"
    store.seed_allocation(dsn, Command(
        request_id=f"p03-context03-allocation:{allocation_id}",
        payload={"allocation_id": allocation_id, "domain": domain, "authorized": amount},
    ))
    return allocation_id


def _create_and_step(dsn, agent, checker, item, seed, identity, roots, *, context_options,
                     token_cap=FIXTURE_TOKEN_CAP):
    task.publish(dsn, item, staging_root=roots["staging_root"],
                 artifacts_root=roots["artifacts_root"])
    token_allocation = _allocation(dsn, identity, "tokens", token_cap)
    cpu_allocation = _allocation(dsn, identity, "cpu", CPU_CAP)
    investigate.create(
        dsn, agent, seed, investigation_id=identity, task=item,
        token_allocation=token_allocation, cpu_allocation=cpu_allocation,
        max_steps=1, timeout_ms=TIMEOUT_MS, token_ceiling=token_cap,
        memory={"scope": {"domain": "task"}, "limit": 10},
        context=context_options, **roots,
    )
    started = time.monotonic_ns()
    state = investigate.step(dsn, agent, checker, identity, **roots)
    elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
    return state, elapsed_ms


def _fixture_agent(cell_root: Path, identity: str):
    return CodexLauncher(
        cell_root / f"fixture-runs-{identity}",
        codex_cmd=[sys.executable, str(cell_root / "p03_fixture_child.py"),
                   str(cell_root / f"{identity}.jsonl")],
        provider=Provider("http://fixture/v1", "fixture:p03-context03/1", "fixture",
                          catalog_template="gpt-6.1-sol",
                          request_retries=0, stream_retries=0),
        allowed_overrides=genome.HARNESS_KEYS,
    )


def _seed_cell(dsn, checker, seed, identity, roots, condition):
    original = _task("p03-maximum-nonempty", SOURCE_NONEMPTY, empty=False)
    changed = _task("p03-maximum-empty", SOURCE_EMPTY, empty=True)
    context_options = {"policy": "structured/1", "budget": dict(context.DEFAULT_BUDGET)}
    good, _ = _create_and_step(dsn, _fixture_agent(roots["staging_root"].parent, identity + "-source-nonempty"), checker, original, seed,
                               identity + "-source-nonempty", roots,
                               context_options=context_options)
    bad, _ = _create_and_step(dsn, _fixture_agent(roots["staging_root"].parent, identity + "-source-empty"), checker, changed, seed,
                              identity + "-source-empty", roots,
                              context_options=context_options)
    if good["status"] != "completed" or good["last_observation"].get("passed") is not True:
        raise SettlementError("labeled nonempty fixture experience did not pass: "
                              + json.dumps({"status": good.get("status"),
                                            "observation": good.get("last_observation"),
                                            "execution_error": good.get("execution_error")},
                                           sort_keys=True, default=str))
    if bad["status"] != "unresolved" or bad["last_observation"].get("passed") is not False:
        raise SettlementError("labeled empty-input fixture experience did not fail")
    prior = export_investigation(dsn, identity + "-source-nonempty")
    failed = export_investigation(dsn, identity + "-source-empty")
    support_id = prior["observations"][0]["id"]
    opposition_id = failed["observations"][0]["id"]
    artifacts_root = roots["artifacts_root"]
    memory.revise(dsn, claim_id="p03-maximum-rule", expected_version=0,
                  text="sorted(xs)[-1] computes maximum for nonempty lists.",
                  scope={"domain": "task"}, status="supported", support=[support_id],
                  artifacts_root=artifacts_root)
    claim = memory.revise(
        dsn, claim_id="p03-maximum-rule", expected_version=1,
        text=LESSON if condition != "misleading" else MISLEADING_LESSON,
        scope={"domain": "task"}, status="challenged", support=[support_id],
        opposition=[opposition_id], artifacts_root=artifacts_root,
    )
    corpus = {
        "tasks": [original.digest, changed.digest],
        "claim_id": claim["claim_id"], "claim_version": claim["version"],
        "claim_text": claim["text"], "claim_status": claim["status"],
        "prior_memory_revision": claim["revision"],
        "support_id": support_id, "opposition_id": opposition_id,
        "task_instruction": TASK_INSTRUCTION,
    }
    if condition == "source-removed":
        source_solution = bad["last_observation"].get("solution")
        if not isinstance(source_solution, str):
            raise SettlementError("failed source has no removable solution artifact")
        (artifacts_root / source_solution).unlink()
    return corpus, opposition_id


def _read_route(path: Path, repository: Path) -> dict[str, str]:
    path = path.resolve(strict=True)
    try:
        path.relative_to(repository.resolve())
    except ValueError:
        pass
    else:
        raise SettlementError("route envfile must be outside the Git worktree")
    route: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            raise SettlementError("route envfile contains a malformed entry")
        route[key.strip()] = value.strip().strip('"').strip("'")
    if route.get("SETTLEMENT_GATEWAY_MODEL") != LIVE_ALIAS:
        raise SettlementError("live mode accepts only openrouter/openrouter/free")
    if not all(route.get(key) for key in (
        "SETTLEMENT_GATEWAY_ENDPOINT", "SETTLEMENT_GATEWAY_KEY",
        "SETTLEMENT_GATEWAY_MODEL",
    )):
        raise SettlementError("route envfile is missing required values")
    return route


def _source_digests(repository: Path) -> dict[str, str]:
    paths = ("src/rsi/context.py", "src/rsi/investigate.py", "src/rsi/episode.py",
             "src/settlement/broker.py", "src/settlement/launcher_codex.py")
    result = {}
    for name in paths:
        path = repository / name
        if not path.is_file():
            raise SettlementError(f"source digest input is missing: {name}")
        result[name] = _digest(path.read_bytes())
    return result


def _step_record(dsn, identity, step_result, elapsed_ms, child_log):
    exported = export_investigation(dsn, identity)
    durable_state = exported["state"]
    decisions = exported["decisions"]
    worker_decisions = [d for d in decisions if d.get("kind") == "worker"]
    decision = worker_decisions[-1] if worker_decisions else None
    visible = (decision or {}).get("data", {}).get("visible_input", {})
    packet = visible.get("context_packet")
    if packet is None:
        packet = (step_result.get("context_outcome") or {}).get("packet")
    context_outcome = step_result.get("context_outcome")
    safe_outcome = {"status": step_result.get("status"),
                    "revision": step_result.get("revision")}
    if isinstance(context_outcome, dict):
        safe_outcome["context_outcome"] = {
            key: context_outcome[key] for key in ("status", "request_id", "packet", "needs")
            if key in context_outcome
        }
    operation_id = (decision or {}).get("data", {}).get("operation_id")
    invocation = None
    if operation_id:
        operation = broker.read_operation(dsn, operation_id)
        if operation is None:
            raise SettlementError("stored decision operation is missing")
        payload = operation["payload"].get("payload", {})
        instruction = payload.get("instruction")
        if not isinstance(instruction, str):
            raise SettlementError("stored broker payload has no rendered instruction")
        match = re.search(r"^Continuation \(JSON\):\n(.*?)(?:\n\nInput digest:|\Z)",
                          instruction, re.MULTILINE | re.DOTALL)
        consumed = json.loads(match.group(1)) if match else None
        consumed_packet = consumed.get("context_packet") if isinstance(consumed, dict) else None
        invocation = {
            "operation_id": operation_id,
            "payload_digest": operation.get("payload_digest"),
            "dispatch_state": operation.get("dispatch_state"),
            "reconcile_state": operation.get("reconcile_state"),
            "settled": operation.get("settled"),
            "instruction_sha256": _digest(instruction.encode("utf-8")),
            "instruction_bytes": len(instruction.encode("utf-8")),
            "instruction": instruction,
            "input_digest": re.search(r"Input digest: ([0-9a-f]{64})", instruction).group(1)
            if re.search(r"Input digest: ([0-9a-f]{64})", instruction) else None,
            "continuation": consumed,
            "continuation_sha256": _digest(_json_bytes(consumed)) if consumed is not None else None,
            "packet_sha256": (consumed_packet or {}).get("digest")
            if isinstance(consumed_packet, dict) else None,
            "connected": consumed_packet == packet and isinstance(packet, dict),
            "receipts": _receipt_summaries(dsn, operation_id),
        }
    child = []
    if child_log.is_file():
        child = [json.loads(line) for line in child_log.read_text(encoding="utf-8").splitlines() if line]
    record = {
        "schema": "p03-context-cell/1",
        "investigation_id": identity,
        "state": durable_state, "decisions": decisions,
        "attempt_observations": exported["observations"],
        "effects": exported["unresolved_effects"],
        "operations": _operation_summaries(dsn, identity),
        "step_outcome": safe_outcome,
        "context_packet": packet,
        "build_status": packet.get("status") if isinstance(packet, dict) else None,
        "build_counts": packet.get("counts") if isinstance(packet, dict) else None,
        "selected_sources": _selected_sources(packet),
        "invocation": invocation,
        "step_elapsed_ms": elapsed_ms,
        "child_inputs": child,
    }
    return record


def _selected_sources(packet):
    if not isinstance(packet, dict):
        return {"claims": [], "observations": []}
    view = packet.get("memory_view") or {}
    observations = []
    for item in view.get("observations", []):
        observations.append({"observation_id": item.get("observation_id"),
                             "artifacts": item.get("artifacts", []),
                             "task_instruction": item.get("content", {}).get("task_instruction"),
                             "passed": item.get("content", {}).get("passed")})
    claims = [{"claim_id": item.get("claim_id"), "version": item.get("version"),
               "status": item.get("status"), "text": item.get("text"),
               "support": item.get("support", []), "opposition": item.get("opposition", [])}
              for item in view.get("claims", [])]
    return {"claims": claims, "observations": observations}


def _receipt_summaries(dsn: str, operation_id: str) -> list[dict]:
    from psycopg.rows import dict_row

    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT receipt_identity, content_digest, outcome, content "
                    "FROM receipts WHERE operation_id=%s ORDER BY receipt_identity",
                    (operation_id,))
        rows = cur.fetchall()
    summaries = []
    for row in rows:
        content = row["content"] or {}
        summaries.append({
            "operation_id": operation_id,
            "receipt_identity": row["receipt_identity"],
            "content_digest": row["content_digest"], "outcome": row["outcome"],
            "status": content.get("status"),
            "tokens": content.get("tokens"), "seconds": content.get("seconds"),
            "actual_cost": content.get("actual_cost"),
        })
    return summaries


def _operation_summaries(dsn: str, investigation_id: str) -> list[dict]:
    from psycopg.rows import dict_row

    allowed = ("id", "effect", "payload_digest", "dispatch_state", "reconcile_state",
               "settled", "receipt_provenance", "created_at", "updated_at")
    with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT o.* FROM operations o JOIN attempts a ON a.id=o.attempt_id "
                    "WHERE a.investigation_id=%s ORDER BY o.created_at,o.id", (investigation_id,))
        rows = cur.fetchall()
    return [{**{key: row.get(key) for key in allowed if key in row},
             "receipts": _receipt_summaries(dsn, row["id"])} for row in rows]


def run_cell(args) -> Path:
    cell = Cell(args.policy, args.condition)
    repository = Path(__file__).resolve().parents[2]
    run_root = args.run_root.resolve()
    evidence_root = args.evidence_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    cell_root = run_root / cell.id
    cell_root.mkdir(parents=True, exist_ok=True)
    roots = {"staging_root": cell_root / "stage", "artifacts_root": cell_root / "artifacts"}
    roots["staging_root"].mkdir(exist_ok=True)
    roots["artifacts_root"].mkdir(exist_ok=True)
    evidence_dir = evidence_root / cell.id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    db_id = _fresh_database(args.dsn)
    route = _read_route(args.route_envfile, repository) if args.mode == "live" else None
    child_path = cell_root / "p03_fixture_child.py"
    child_path.write_text(FIXTURE_CHILD, encoding="utf-8")
    driver_digest = _digest(Path(__file__).read_bytes())
    child_digest = _digest(FIXTURE_CHILD.encode("utf-8"))
    source_digests = _source_digests(repository)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository,
                                     text=True).strip()
    model_alias = route["SETTLEMENT_GATEWAY_MODEL"] if route else "fixture:p03-context03/1"
    freeze = {
        "schema": "p03-context-freeze/1", "matrix": [list(item) for item in MATRIX],
        "cell_id": cell.id, "policy": cell.policy, "condition": cell.condition,
        "source": source, "driver_sha256": driver_digest, "fixture_child_sha256": child_digest,
        "source_sha256": source_digests, "mode": args.mode, "model_alias": model_alias,
        "budgets": {"live_worker_actions_total": 6, "live_worker_actions_per_cell": 1,
                    "fixture_worker_actions_per_cell": 3,
                    "fixture_verifier_actions_per_cell": 3,
                    "max_steps_per_investigation": 1,
                    "timeout_ms_per_cell": TIMEOUT_MS, "token_cap_per_live_cell": LIVE_TOKEN_CAP,
                    "fixture_token_cap_per_worker": FIXTURE_TOKEN_CAP,
                    "cpu_authorization_per_investigation": CPU_CAP,
                    "request_retries": 0, "stream_retries": 0},
        "context_packet_budget": dict(context.DEFAULT_BUDGET),
        "memory": {"scope": {"domain": "task"}, "limit": 10},
        "database_id": db_id, "corpus_contract": "authored maximum task, genome, two labeled fixture observations, one challenged claim",
    }
    freeze_path = evidence_dir / "freeze.json"
    if freeze_path.exists():
        raise SettlementError(f"freeze already exists for {cell.id}")
    _save(freeze_path, freeze)

    seed = genome.Genome({"AGENTS.md": (
        b"Work only on the public maximum task. Use the continuation context packet. "
        b"Treat lessons as scoped interpretations and inspect contrary checked evidence. "
        b"Do not seek hidden tests.\n")})
    genome.publish(args.dsn, seed, parent=None, origin="authored-p03-context03", **roots)
    checker = LocalLauncher(cell_root / "verifiers")
    corpus, required_observation_id = _seed_cell(
        args.dsn, checker, seed, cell.id, roots, cell.condition)
    candidate = _task("p03-maximum-comparison", TASK_INSTRUCTION, empty=True)
    task.publish(args.dsn, candidate, staging_root=roots["staging_root"],
                 artifacts_root=roots["artifacts_root"])
    token_cap = LIVE_TOKEN_CAP if args.mode == "live" else FIXTURE_TOKEN_CAP
    token_allocation = _allocation(args.dsn, cell.id + "-comparison", "tokens", token_cap)
    cpu_allocation = _allocation(args.dsn, cell.id + "-comparison", "cpu", CPU_CAP)
    context_options = {
        "policy": cell.policy, "budget": dict(context.DEFAULT_BUDGET),
        "required_observation_ids": [required_observation_id],
        "required_claim_ids": [],
    }
    agent = (_fixture_agent(cell_root, cell.id) if args.mode == "fixture"
             else _live_agent(args, route, cell_root))
    investigate.create(
        args.dsn, agent,
        seed, investigation_id=cell.id, task=candidate,
        token_allocation=token_allocation, cpu_allocation=cpu_allocation,
        max_steps=1, timeout_ms=TIMEOUT_MS, token_ceiling=token_cap,
        objective=TASK_INSTRUCTION, memory={"scope": {"domain": "task"}, "limit": 10},
        context=context_options, staging_root=roots["staging_root"],
        artifacts_root=roots["artifacts_root"],
    )
    started = time.monotonic_ns()
    state = investigate.step(args.dsn, agent, checker, cell.id,
                             staging_root=roots["staging_root"],
                             artifacts_root=roots["artifacts_root"])
    elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
    output_path = evidence_dir / "cell.json"
    record = _step_record(args.dsn, cell.id, state, elapsed_ms,
                          cell_root / f"{cell.id}.jsonl")
    corpus_export = {**corpus, "required_observation_id": required_observation_id}
    corpus_export["digest"] = _digest(_json_bytes(corpus_export))
    record.update({"cell_id": cell.id, "policy": cell.policy, "condition": cell.condition,
                   "database_id": db_id, "mode": args.mode, "model_alias": model_alias,
                   "freeze": freeze, "freeze_sha256": _digest(_json_bytes(freeze)),
                   "corpus": corpus_export,
                   "candidate_task_digest": candidate.digest,
                   "input_manifest": _input_manifest(candidate, seed),
                   "genome_digest": seed.digest})
    _save(output_path, record)
    return output_path


def _input_manifest(candidate, seed):
    staged = {**candidate.workspace, **genome.workspace_view(seed)}
    return [{"path": rel, "size": len(raw), "digest": _digest(raw)}
            for rel, raw in sorted(staged.items())]


def _live_agent(args, route, cell_root):
    if not args.codex_cmd:
        raise SettlementError("live mode requires --codex-cmd")
    return CodexLauncher(
        cell_root / "live-runs", codex_cmd=args.codex_cmd,
        provider=Provider(route["SETTLEMENT_GATEWAY_ENDPOINT"], route["SETTLEMENT_GATEWAY_MODEL"],
                          route["SETTLEMENT_GATEWAY_KEY"], catalog_template="gpt-6.1-sol",
                          request_retries=0, stream_retries=0),
        allowed_overrides=genome.HARNESS_KEYS,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one prospectively bounded P03 comparison cell.")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--policy", choices=POLICIES, required=True)
    parser.add_argument("--condition", choices=CONDITIONS, required=True)
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--route-envfile", type=Path)
    parser.add_argument("--codex-cmd", nargs="+")
    args = parser.parse_args()
    if args.mode == "live" and args.route_envfile is None:
        parser.error("live mode requires --route-envfile")
    try:
        path = run_cell(args)
    except (SettlementError, OSError, ValueError) as exc:
        raise SystemExit(f"P03 comparison cell failed: {exc}") from exc
    print(path)


if __name__ == "__main__":
    main()
