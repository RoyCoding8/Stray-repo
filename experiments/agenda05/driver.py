"""Run one frozen P05 arm through the public agenda and P01 APIs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from experiments.agenda05.freeze import verify_freeze
from rsi import agenda, experience, genome, investigate, investigation, memory, task
from settlement import broker, db, store
from settlement.common import Command
from settlement.launcher_codex import CodexLauncher, Provider
from settlement.launcher_local import LocalLauncher

MODEL = "openrouter/openrouter/free"
CLAIM = "p05-addition-rule"


def _task(name: str, a: int, b: int, *, starter: int = 0) -> task.Task:
    expected = a + b
    test = ("import unittest\nfrom calc import add\n"
            "class AddTests(unittest.TestCase):\n"
            f"    def test_add(self): self.assertEqual(add({a}, {b}), {expected})\n").encode()
    instruction = f"Implement add(a, b) so add({a}, {b}) returns {expected}."
    return task.Task("p05-" + name, "dev", instruction,
                     {"calc.py": f"def add(a, b):\n    return {starter}\n".encode()},
                     {"test_add.py": test},
                     {"calc.py": b"def add(a, b):\n    return a + b\n"},
                     ("test_add.py",))


def _genome() -> genome.Genome:
    return genome.Genome({"AGENTS.md": b"Solve only the assigned addition task.\n"})


def _roots(dsn: str, agenda_id: str) -> tuple[str, str]:
    token, cpu = f"{agenda_id}-tokens", f"{agenda_id}-cpu"
    for identity, domain, amount in ((token, "tokens", 300_000),
                                     (cpu, "cpu", 3_000_000)):
        store.seed_allocation(dsn, Command(
            request_id="seed-" + identity,
            payload={"allocation_id": identity, "domain": domain,
                     "authorized": amount, "owner_scope": agenda_id}))
    return token, cpu


def _grant(dsn: str, agenda_id: str, charter: dict) -> None:
    store.seed_grant(dsn, Command(
        request_id="p05-grant:" + agenda_id,
        payload={"version": charter["grant_version"], "charter_text": charter["objective"],
                 "authority_grant": {
                     "kind": "rsi-agenda", "agenda_id": agenda_id,
                     "development_task_ids": sorted({o["task_id"] for o in charter["opportunities"]}),
                     "genome_ids": [charter["opportunities"][0]["genome_id"]],
                     "effects": [broker.AGENT_RUN, broker.SANDBOX_EXEC]},
                 "envelopes": {
                     "tokens": {"allocation_id": charter["allocations"]["tokens"]["id"],
                                "units": charter["allocations"]["tokens"]["units"]},
                     "cpu": {"allocation_id": charter["allocations"]["cpu"]["id"],
                             "units": charter["allocations"]["cpu"]["units"]},
                     "max_turns": charter["max_turns"]}}))


def _route(path: Path) -> Provider:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, sep, value = line.partition("=")
            if not sep:
                raise ValueError("route file has a malformed assignment")
            values[key.strip()] = value.strip().strip("\"'")
    keys = {"SETTLEMENT_GATEWAY_ENDPOINT", "SETTLEMENT_GATEWAY_MODEL",
            "SETTLEMENT_GATEWAY_KEY"}
    if keys - values.keys() or values["SETTLEMENT_GATEWAY_MODEL"] != MODEL:
        raise ValueError("route must name the frozen free OpenRouter model")
    return Provider(values["SETTLEMENT_GATEWAY_ENDPOINT"], MODEL,
                    values["SETTLEMENT_GATEWAY_KEY"])


def _preflight(provider: Provider) -> None:
    endpoint = provider.endpoint.rstrip("/")
    url = endpoint if endpoint.endswith("/models") else endpoint + "/models"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + provider.api_key, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=8) as response:
        body = json.loads(response.read(2_000_000))
    rows = body.get("data", body.get("models", [])) if isinstance(body, dict) else []
    if MODEL not in {row.get("id", row.get("slug")) for row in rows if isinstance(row, dict)}:
        raise RuntimeError("frozen free route is not listed by the single preflight")


def _fixture_agent(repo: Path, root: Path, *, fail_pairs: str = "") -> CodexLauncher:
    root.mkdir(parents=True, exist_ok=True)
    return CodexLauncher(
        root / "runs", codex_cmd=[sys.executable,
                                  str(repo / "experiments/agenda05/fixture_worker.py"),
                                  str(root / "calls.jsonl"), fail_pairs],
        provider=Provider("http://fixture.invalid/v1", "fixture:free", "fixture"),
        allowed_overrides=genome.HARNESS_KEYS)


def _claim(dsn: str, organism: genome.Genome, candidate: task.Task,
           roots: dict, agent: CodexLauncher) -> tuple[dict, dict]:
    from rsi import investigate

    prior = investigate.create(
        dsn, agent, organism, investigation_id="p05-prior", task=candidate,
        token_allocation=roots["token"], cpu_allocation=roots["cpu"],
        max_steps=1, timeout_ms=30_000, token_ceiling=5_000,
        objective="Check the addition rule on a passing development example.",
        staging_root=roots["stage"], artifacts_root=roots["art"])
    result = investigate.step(dsn, agent, LocalLauncher(roots["verifiers"]),
                              prior["investigation_id"],
                              staging_root=roots["stage"], artifacts_root=roots["art"])
    if result["status"] != "completed" or result["last_observation"]["passed"] is not True:
        raise RuntimeError(f"authored seed experience failed its pristine verifier: {result}")
    captured, = experience.capture_investigation(
        dsn, "p05-prior", artifacts_root=roots["art"])
    claim = memory.revise(
        dsn, claim_id=CLAIM, expected_version=0,
        text="Addition returns the sum of its two operands.",
        scope={"domain": "task"}, status="supported",
        support=[captured["observation_id"]], artifacts_root=roots["art"])
    return claim, investigation.export(dsn, "p05-prior")


def _charter(agenda_id: str, policy: str, token: str, cpu: str,
             organism: genome.Genome, tasks: dict, investigations: dict,
             deadline: str) -> dict:
    shared = {"genome_id": organism.digest, "max_steps": 1,
              "timeout_ms": 30_000,
              "resource_ceilings": {"tokens": 5_000, "cpu": 3_000_000}}
    def item(option_id, name, question, priority, *, source=None, investigation_id=None):
        value = {**shared, "id": option_id, "task_id": tasks[name].digest,
                 "objective": question, "question": question, "priority": priority,
                 "expected_observation": "The pristine addition verifier result.",
                 "stop_condition": "One checked P01 step.",
                 "investigation_id": investigation_id}
        if source is not None:
            value["scope_probe"] = {
                "source_opportunity_id": source,
                "lesson_refs": [{"claim_id": CLAIM, "version": 1}],
                "changed_condition": tasks[name].instruction,
                "competing_explanations": ["the lesson generalizes", "the lesson is task-specific"],
            }
        return value

    return {"grant_version": 1,
            "objective": "Use checked experience to select a discriminating addition probe.",
            "allocations": {"tokens": {"id": token, "units": 300_000},
                            "cpu": {"id": cpu, "units": 3_000_000}},
            "policy": policy, "max_turns": 3,
            "deadline": deadline,
            "opportunities": [
                item("source", "source", "Use the checked addition rule on a contrasting input.",
                     30, investigation_id=investigations["source"]),
                item("priority-task", "priority", "Check a routine addition case.", 20),
                item("scope-probe", "probe", "Discriminate general from narrow addition behavior.",
                     1, source="source", investigation_id=investigations["probe"]),
                item("followup-probe", "followup", "Check the probe lesson on a changed input.",
                     1, source="scope-probe"),
            ]}


def build_scenario(deadline: str) -> dict:
    try:
        parsed_deadline = datetime.fromisoformat(
            deadline[:-1] + "+00:00" if deadline.endswith("Z") else deadline)
    except (AttributeError, ValueError) as exc:
        raise ValueError("scenario deadline must be an RFC3339 UTC timestamp") from exc
    if (parsed_deadline.tzinfo is None or parsed_deadline.utcoffset().total_seconds() != 0
            or parsed_deadline <= datetime.now(UTC)):
        raise ValueError("scenario deadline must be future UTC")
    tasks = {"source": _task("source", 2, 3),
             "priority": _task("priority", 4, 5),
             "probe": _task("probe", 3, 8),
             "followup": _task("followup", 7, 11)}
    organism = _genome()
    arms = {}
    for policy in ("seed/1", "adaptive/1"):
        short = policy.split("/", 1)[0]
        agenda_id = "p05-" + short
        token, cpu = _roots_names(agenda_id)
        investigations = {"source": "p05-source", "probe": "p05-probe"}
        charter = _charter(agenda_id, policy, token, cpu, organism, tasks,
                           investigations, deadline)
        arms[short] = {"agenda_id": agenda_id, "policy": policy,
                       "charter": charter,
                       "task_ids": {name: item.digest for name, item in tasks.items()},
                       "genome_id": organism.digest}
    initial = {"claim_id": CLAIM, "version": 1,
               "task_id": tasks["source"].digest, "genome_id": organism.digest,
               "source": "authored-from-scripted-pristine-example"}
    return {"schema": "p05-agenda-scenario/1", "arms": arms,
            "initial_evidence": initial,
            "initial_evidence_sha256": hashlib.sha256(json.dumps(
                initial, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                allow_nan=False).encode()).hexdigest(),
            "choice_cap": 3,
            "outcome_labels": {"fixture": "authored-scripted", "live": "openrouter-free"}}


def _roots_names(agenda_id: str) -> tuple[str, str]:
    return f"{agenda_id}-tokens", f"{agenda_id}-cpu"


def _include_operations(dsn: str, history: dict, output: dict) -> None:
    operation_ids = {row.get("data", {}).get("operation_id")
                     for row in history.get("decisions", [])}
    operation_ids.update(row.get("content", {}).get("verdict")
                         for row in history.get("observations", []))
    for operation_id in operation_ids - {None}:
        output[operation_id] = {
            "operation": broker.read_operation(dsn, operation_id),
            "receipts": store.operation_receipts(dsn, operation_id),
        }


def run_arm(repo: Path, bundle: Path, output: Path, dsn: str, arm_id: str, mode: str,
            route_file: Path | None = None, codex: str = "codex") -> dict:
    if arm_id not in {"seed", "adaptive"} or mode not in {"fixture", "live"}:
        raise ValueError("unsupported policy or arm mode")
    if mode == "live" and route_file is None:
        raise ValueError("live arm requires an external route file")
    frozen = verify_freeze(repo, bundle)
    try:
        scenario = json.loads(base64.b64decode(frozen["scenario"], validate=True))
        arm = scenario["arms"][arm_id]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("frozen scenario does not name this arm") from exc
    if scenario.get("schema") != "p05-agenda-scenario/1" or scenario.get("choice_cap") != 3:
        raise ValueError("unsupported or unbounded P05 scenario")
    policy, agenda_id, charter = arm["policy"], arm["agenda_id"], arm["charter"]
    organism = _genome()
    tasks = {"source": _task("source", 2, 3, starter=0),
             "priority": _task("priority", 4, 5, starter=0),
             "probe": _task("probe", 3, 8, starter=0),
             "followup": _task("followup", 7, 11, starter=0)}
    if (organism.digest != arm["genome_id"]
            or {name: item.digest for name, item in tasks.items()} != arm["task_ids"]):
        raise ValueError("frozen task or genome identities differ from current source")
    if (agenda_id != "p05-" + arm_id or policy != f"{arm_id}/1"
            or charter.get("policy") != policy or charter.get("max_turns") != 3):
        raise ValueError("frozen arm identity or bound differs from this CLI arm")
    db.apply_migrations(dsn, repo / "migrations")
    root = output / agenda_id
    roots = {"stage": root / "stage", "art": root / "art",
             "verifiers": root / "verifiers"}
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
    token, cpu = _roots(dsn, agenda_id)
    if (token != charter["allocations"]["tokens"]["id"]
            or cpu != charter["allocations"]["cpu"]["id"]):
        raise ValueError("frozen charter resource identities differ from the arm")
    genome.publish(dsn, organism, parent=None, origin="p05-genome-v1",
                   staging_root=roots["stage"], artifacts_root=roots["art"])
    for candidate in tasks.values():
        task.publish(dsn, candidate, staging_root=roots["stage"], artifacts_root=roots["art"])
    _grant(dsn, agenda_id, charter)
    priors = _fixture_agent(repo, root / "prior")
    claim, prior_history = _claim(
        dsn, organism, tasks["source"], {**roots, "token": token, "cpu": cpu}, priors)

    provider = (_route(route_file) if mode == "live" else
                Provider("http://fixture.invalid/v1", "fixture:free", "fixture"))
    if mode == "live":
        _preflight(provider)
        command = [codex]
    else:
        command = [sys.executable, str(repo / "experiments/agenda05/fixture_worker.py"),
                   str(root / "calls.jsonl"), "2,3;3,8"]
    agent = CodexLauncher(root / "agent-runs", codex_cmd=command, provider=provider,
                          allowed_overrides=genome.HARNESS_KEYS)
    investigations = {"source": "p05-source", "probe": "p05-probe"}
    for key, task_name in (("source", "source"), ("probe", "probe")):
        investigate.create(
            dsn, agent, organism, investigation_id=investigations[key],
            task=tasks[task_name], token_allocation=token, cpu_allocation=cpu,
            max_steps=1, timeout_ms=30_000, token_ceiling=5_000,
            objective="Use the supported addition rule and check the assigned input.",
            context={"required_claim_ids": [CLAIM]},
            staging_root=roots["stage"], artifacts_root=roots["art"])
    created = agenda.create(dsn, agenda_id=agenda_id, charter=charter,
                            artifacts_root=roots["art"])
    checker = LocalLauncher(roots["verifiers"])
    results = []
    for _ in range(scenario["choice_cap"]):
        result = agenda.wake(dsn, agent, checker, agenda_id,
                             staging_root=roots["stage"], artifacts_root=roots["art"])
        results.append(result)
        state = agenda.read(dsn, agenda_id)
        if result.get("status") in {"deferred", "stopped", "complete", "unchanged"}:
            break
        if state["status"] in {"complete", "stopped"}:
            break
    exported = agenda.export(dsn, agenda_id)
    p01_exports, operations = {}, {}
    for decision in exported["decisions"]:
        data = decision["data"]
        if decision["kind"] != "p05.ack":
            continue
        history = investigation.export(dsn, data["investigation_id"])
        p01_exports[data["investigation_id"]] = history
        _include_operations(dsn, history, operations)
    _include_operations(dsn, prior_history, operations)
    report = {"schema": "p05-agenda-arm/1", "freeze_sha256": hashlib.sha256(
              json.dumps(frozen, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode()).hexdigest(),
              "arm_id": arm_id, "agenda_id": agenda_id,
              "policy": policy, "mode": mode,
              "initial_claim": {**claim, "source": "authored-from-scripted-pristine-example"},
              "initial_evidence_sha256": scenario["initial_evidence_sha256"],
              "initial_investigation": prior_history, "created": created,
              "results": results, "result": results[-1] if results else None,
              "agenda_export": exported,
              "investigations": p01_exports, "operations": list(operations.values()),
              "task_packages": {t.digest: base64.b64encode((roots["art"] / t.digest).read_bytes()).decode("ascii")
                                for t in tasks.values()},
              "genome_package": base64.b64encode((roots["art"] / organism.digest).read_bytes()).decode("ascii"),
              "artifacts": {p.name: base64.b64encode(p.read_bytes()).decode("ascii")
                            for p in roots["art"].iterdir() if p.is_file()},
              "fixture_calls": {
                  "initial": json.loads((root / "prior" / "calls.jsonl").read_text(encoding="utf-8")),
                  "campaign": (json.loads((root / "calls.jsonl").read_text(encoding="utf-8"))
                               if (root / "calls.jsonl").exists() else []),
              }}
    output.mkdir(parents=True, exist_ok=True)
    (output / (agenda_id + ".json")).write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--prepare-scenario", type=Path,
                        help="write a prospective, effect-free scenario JSON")
    parser.add_argument("--deadline", default="2026-10-31T00:00:00+00:00")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dsn", help="one isolated database for this arm")
    parser.add_argument("--arm", choices=("seed", "adaptive"))
    parser.add_argument("--mode", choices=("fixture", "live"), required=True)
    parser.add_argument("--route-file", type=Path)
    parser.add_argument("--codex", default="codex")
    args = parser.parse_args()
    if args.prepare_scenario is not None:
        scenario = build_scenario(args.deadline)
        args.prepare_scenario.parent.mkdir(parents=True, exist_ok=True)
        args.prepare_scenario.write_text(json.dumps(
            scenario, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"schema": scenario["schema"], "arms": sorted(scenario["arms"]),
                          "choice_cap": scenario["choice_cap"]}, sort_keys=True))
        return
    if not all((args.bundle, args.dsn, args.arm, args.mode)):
        parser.error("run requires --bundle, --dsn, --arm and --mode")
    report = run_arm(args.repo.resolve(), args.bundle.resolve(), args.output.resolve(),
                     args.dsn, args.arm, args.mode, args.route_file, args.codex)
    print(json.dumps({"agenda_id": report["agenda_id"],
                      "choices": [d["data"]["opportunity_id"] for d in
                                  report["agenda_export"]["decisions"] if d["kind"] == "p05.choice"],
                      "status": report["agenda_export"]["agenda"]["status"],
                      "policy": report["policy"], "mode": report["mode"]}, sort_keys=True))


if __name__ == "__main__":
    main()
