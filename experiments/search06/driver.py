"""Collect supported P06 branches and run its bounded prospective pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "scenario.json"
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
MODEL = "openrouter/openrouter/free"
INTERFACE = "integer-sum/1"
POLICY_INTERFACE = "exploration-policy/1"
ROUTE_FILE = Path("D:/AI/tools/rsi-openrouter-route.env")
CODEX = Path("C:/Users/roysh/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe")
SOURCE_PATHS = (
    "src/rsi/agenda.py", "src/rsi/capability.py", "src/rsi/context.py",
    "src/rsi/experience.py", "src/rsi/genome.py", "src/rsi/investigate.py",
    "src/rsi/investigation.py", "src/rsi/search.py", "src/rsi/task.py",
    "src/rsi/verifier.py", "src/rsi/episode.py", "src/rsi/_method_runner.py",
    "src/settlement/broker.py", "src/settlement/store.py",
    "src/settlement/launcher_codex.py", "src/settlement/launcher_local.py",
    "experiments/search06/scenario.json", "experiments/search06/driver.py",
    "experiments/search06/freeze.py",
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2,
                               ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return value


def _scenario(path: Path = SCENARIO) -> dict:
    value = read_json(path)
    if value.get("schema") != "p06-search-experiment/1" or value.get("model") != MODEL:
        raise ValueError("unsupported P06 scenario or model")
    if len(value.get("worlds", [])) != 3 or value.get("caps", {}).get("max_model_admissions") != 2:
        raise ValueError("scenario differs from the frozen three-world, two-admission pilot")
    return value


def _agenda_use_deadline(existing_agenda: dict | None, window_seconds: int,
                         *, now: datetime | None = None) -> str:
    if existing_agenda is not None:
        deadline = (existing_agenda.get("charter") or {}).get("deadline")
        if not isinstance(deadline, str):
            raise ValueError("existing agenda has no durable use deadline")
        return deadline
    if type(window_seconds) is not int or window_seconds <= 0:
        raise ValueError("agenda use window must be a positive number of seconds")
    return ((now or datetime.now(UTC)) + timedelta(seconds=window_seconds)).isoformat()


def _roots(dsn: str, tag: str, *, tokens: int, cpu: int,
           identities: dict[str, str] | None = None) -> dict:
    from settlement import store
    from settlement.common import Command

    result = {}
    for domain, amount in (("tokens", tokens), ("cpu", cpu)):
        identity = ((identities or {}).get(domain) or f"p06-{tag}-{domain}")
        store.seed_allocation(dsn, Command(
            request_id="p06-seed:" + identity,
            payload={"allocation_id": identity, "domain": domain,
                     "authorized": amount, "owner_scope": "p06-search06"}))
        result[domain] = identity
    return result


def _claim_run(frozen: dict, freeze_path: Path, output: Path) -> str:
    expected_output = Path(frozen["live_plan"]["run_output"]).resolve()
    if output.resolve() != expected_output:
        raise ValueError(f"run output must be the frozen directory: {expected_output}")
    output.mkdir(parents=True, exist_ok=True)
    claim_path = output / "run-claim.json"
    claim = {"schema": "p06-run-claim/1", "run_id": frozen["live_plan"]["run_id"],
             "freeze_sha256": frozen["freeze_sha256"],
             "freeze_path": str(freeze_path.resolve())}
    if claim_path.exists():
        if read_json(claim_path) != claim:
            raise ValueError("live output is claimed by a different P06 freeze")
    else:
        try:
            with claim_path.open("x", encoding="utf-8") as stream:
                json.dump(claim, stream, sort_keys=True)
                stream.write("\n")
        except FileExistsError:
            if read_json(claim_path) != claim:
                raise ValueError("live output is claimed by a different P06 freeze")
    return claim["run_id"]


def _sum_task(task_module, label: str, left: int, right: int, expected: int):
    test = ("import json, pathlib, unittest\n"
            "class SumTest(unittest.TestCase):\n"
            "    def test_result(self):\n"
            "        self.assertEqual(json.loads(pathlib.Path('answer.json').read_text()), "
            f"{expected!r})\n")
    return task_module.Task(
        "p06-" + label, "dev", f"Return {left} + {right} as JSON in answer.json.",
        {"answer.json": b"null"}, {"test_sum.py": test.encode("utf-8")},
        {"answer.json": json.dumps(expected).encode("utf-8")}, ("test_sum.py",))


def _method_genome(genome_module, *, restricted: bool):
    body = (
        "import json\n"
        "def invoke(request):\n"
        "    value = request['value']\n"
        + ("    total = value['left'] + value['right'] if min(value.values()) >= 0 else 0\n"
           if restricted else "    total = value['left'] + value['right']\n")
        + "    return {'value': total, 'files': {'answer.json': json.dumps(total)}}\n"
    )
    name = "integer-sum"
    descriptor = {"schema": "rsi-capability/1", "interface": INTERFACE,
                  "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
                  "effects": ["return", "solution-files"],
                  "limits": {"timeout_ms": 5000, "max_output_bytes": 65536}}
    return genome_module.Genome({
        "AGENTS.md": b"Use the declared public request only.\n",
        f"skills/{name}/SKILL.md": b"---\nname: integer-sum\ndescription: Add two integers.\n---\n",
        f"skills/{name}/capability.json": canonical(descriptor),
        f"skills/{name}/method.py": body.encode("utf-8"),
    })


def _policy_genome(genome_module, *, adaptive: bool):
    name = "choose-branch"
    choose = "general" if adaptive else "restricted"
    body = (
        "def invoke(request):\n"
        "    frame = request['value']\n"
        f"    selected = next(item for item in frame['menu'] if item['opportunity_id'] == '{choose}')\n"
        "    return {'value': {'action': 'choose', 'opportunity_id': selected['opportunity_id']}, 'files': {}}\n"
    )
    descriptor = {"schema": "rsi-capability/1", "interface": POLICY_INTERFACE,
                  "entrypoint": "method.py:invoke", "dependencies": ["python-stdlib"],
                  "effects": ["return", "solution-files"],
                  "limits": {"timeout_ms": 5000, "max_output_bytes": 65536}}
    return genome_module.Genome({
        "AGENTS.md": b"Choose one eligible opportunity using only the visible frame.\n",
        f"skills/{name}/SKILL.md": b"---\nname: choose-branch\ndescription: Select a visible branch.\n---\n",
        f"skills/{name}/capability.json": canonical(descriptor),
        f"skills/{name}/method.py": body.encode("utf-8"),
    })


def _publish_genome(dsn, item, staging, artifacts, *, parent=None, origin):
    from rsi import genome
    genome.publish(dsn, item, parent=parent, origin=origin,
                   staging_root=staging, artifacts_root=artifacts)
    return item.digest


def _qualify_method(dsn, candidate, task_item, value, roots, native,
                    staging, artifacts, label):
    from rsi import capability, episode, verifier
    checked = episode.run_method_episode(
        dsn, native, candidate, name="integer-sum",
        request={"interface": INTERFACE, "value": value,
                 "files": {"answer.json": "null"}, "context": {}},
        operation_id="p06-qualify-" + label, task=task_item,
        allocation_id=roots["cpu"], attempt_id=None,
        timeout_ms=5000,
        staging_root=staging, artifacts_root=artifacts)
    verdict = verifier.verify_episode(
        dsn, native, native, checked.operation_id,
        allocation_id=roots["cpu"], attempt_id=None,
        staging_root=staging, artifacts_root=artifacts)
    retained = capability.retain(
        dsn, "p06-retain-" + label, genome=candidate, name="integer-sum",
        episode_id=checked.operation_id, artifacts_root=artifacts)
    if verdict.passed is not True or retained.get("status") != "retained":
        raise RuntimeError(f"authored native fixture failed qualification: {label}")


def _construction_action(result: dict) -> str:
    status = result.get("status")
    if status == "completed" and result.get("child"):
        return "screen"
    if status == "invalid":
        return "repair"
    if status in {"timeout", "infra_failed", "unresolved"}:
        return "stop-unscored"
    return "stop-no-acquisition"


def _construction_admissions(dsn: str, operation_ids: list[str]) -> int:
    from settlement import broker
    return sum(broker.read_operation(dsn, operation_id) is not None
               for operation_id in operation_ids)


def _construction_evidence(dsn: str, operation_ids: list[str]) -> dict:
    """Export durable constructor accounting through settlement's read APIs."""
    from psycopg.rows import dict_row

    from settlement import broker, db, store

    operations = []
    for operation_id in operation_ids:
        operation = broker.read_operation(dsn, operation_id)
        if operation is None:
            operations.append({"operation_id": operation_id, "found": False,
                               "reservation": None, "receipts": []})
            continue
        receipts = store.operation_receipts(dsn, operation_id)
        with db.read_connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT amount, state FROM reservations WHERE id = %s",
                        (operation.get("reservation_id"),))
            reservation = cur.fetchone()
            conn.commit()
        operations.append({
            "operation_id": operation_id, "found": True,
            "dispatch_state": operation.get("dispatch_state"),
            "reconcile_state": operation.get("reconcile_state"),
            "settled": bool(operation.get("settled")),
            "reservation": (None if reservation is None else {
                "amount": int(reservation["amount"]), "state": reservation["state"]}),
            "receipts": [{"receipt_identity": row["receipt_identity"],
                          "outcome": row["outcome"]} for row in receipts],
        })
    return {"operations": operations,
            "admissions": sum(item["found"] for item in operations),
            "reserved_units_known": sum(
                item["reservation"]["amount"] for item in operations
                if item["reservation"] is not None),
            "reserved_units_unknown": sum(
                item["found"] and item["reservation"] is None for item in operations)}


def _save_live_report(dsn: str, output: Path, report: dict, operation_ids: list[str]) -> None:
    evidence = _construction_evidence(dsn, operation_ids)
    report["construction_accounting"] = evidence
    report["admissions"] = evidence["admissions"]
    write_json(output / "live-result.json", report)


def _start(dsn, roots, task_item, candidate, value, investigation_id, native,
           staging, artifacts, scenario):
    from rsi import capability, investigate
    state = investigate.create(
        dsn, None, candidate, investigation_id=investigation_id, task=task_item,
        token_allocation=roots["tokens"], cpu_allocation=roots["cpu"],
        max_steps=1, timeout_ms=scenario["caps"]["action_timeout_ms"],
        token_ceiling=scenario["caps"]["action_token_units"],
        method={"name": "integer-sum", "interface": INTERFACE, "value": value},
        staging_root=staging, artifacts_root=artifacts)
    prepared = investigate.prepare_context(
        dsn, investigation_id, target_revision=0, artifacts_root=artifacts)
    if "visible_input" not in prepared:
        raise RuntimeError("P01 failed to prepare a fresh native-method start")
    request = {"interface": INTERFACE, "value": value,
               "files": {"answer.json": "null"},
               "context": {"continuation": {
                   "objective": prepared["objective"],
                   "objective_revision": prepared["objective_revision"],
                   "state_revision": prepared["revision"],
                   "open_questions": prepared["open_questions"],
                   "artifact_refs": prepared["artifact_refs"],
                   "previous_observation": prepared["last_observation"],
                   "context_packet": prepared["visible_input"]["context_packet"]},
                   "task_digest": task_item.digest}}
    plan = capability.plan_invocation(
        native, candidate, "integer-sum", request,
        timeout_ms=5000, max_output_bytes=65536)
    config = prepared["config"]
    return state, {"investigation_id": investigation_id, "target_revision": 0,
                   "visible_input": prepared["visible_input"], "task": task_item.digest,
                   "genome": candidate.digest, "model": "",
                   "method": prepared["visible_input"].get("capability"),
                   "runtime": {**dict(plan.runtime), "execution_version": plan.execution_version},
                   "evaluator_version": task_item.evaluator_version,
                   "limits": {key: config[key] for key in
                              ("timeout_ms", "token_ceiling", "max_steps",
                               "token_allocation", "cpu_allocation")}}


def collect(dsn: str, output: Path, *, scenario_path: Path = SCENARIO) -> dict:
    """Publish each complete visible frame before executing its P01 branches."""
    from rsi import experience, genome, investigate, search, task
    from settlement.launcher_local import LocalLauncher

    scenario = _scenario(scenario_path)
    run_id = uuid.uuid4().hex[:10]
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "collection-runtime"
    staging, artifacts = runtime / "stage", runtime / "art"
    staging.mkdir(parents=True, exist_ok=False)
    artifacts.mkdir()
    native = LocalLauncher(runtime / "native")
    roots = _roots(dsn, "collect-" + run_id, tokens=1_200_000, cpu=2_000_000)
    qualification = _sum_task(task, "qualification-" + run_id, 2, 3, 5)
    task.publish(dsn, qualification, staging_root=staging, artifacts_root=artifacts)
    methods = {kind: _method_genome(genome, restricted=(kind == "restricted"))
               for kind in ("restricted", "general")}
    for kind, candidate in methods.items():
        _publish_genome(dsn, candidate, staging, artifacts,
                        origin="p06-authored-method:" + kind)
        _qualify_method(dsn, candidate, qualification, {"left": 2, "right": 3},
                        roots, native, staging, artifacts, run_id + "-" + kind)

    frames, branches = [], []
    for world in scenario["worlds"]:
        task_item = _sum_task(task, world["id"], world["left"], world["right"], world["expected"])
        task.publish(dsn, task_item, staging_root=staging, artifacts_root=artifacts)
        frame_id = "p06-frame-" + run_id + "-" + world["id"]
        roots_world = _roots(dsn, world["id"] + "-" + run_id, tokens=800_000, cpu=1_200_000)
        starts = {}
        inputs = {"left": world["left"], "right": world["right"]}
        prepared = {}
        for kind, opportunity in (("restricted", "restricted"), ("general", "general"),
                                  ("general", "unexecuted")):
            investigation_id = frame_id + "-" + opportunity
            state, start = _start(dsn, roots_world, task_item, methods[kind], inputs,
                                  investigation_id, native, staging, artifacts, scenario)
            prepared[opportunity] = (state, start)
            starts[opportunity] = start
        visible = {"objective": "p06-world:" + world["id"],
                   "menu": [{"opportunity_id": key, "eligible": True}
                            for key in sorted(starts)],
                   "prefix": [], "limits": scenario["caps"]}
        digest = search.publish_frame(
            dsn, visible, starts,
            {"kind": "authored-native-collection", "world": world["id"],
             "task": task_item.digest, "model": ""},
            staging_root=staging, artifacts_root=artifacts)
        frames.append(digest)
        # All starts and P03 contexts above exist before the first native branch runs.
        for opportunity in ("general", "restricted"):
            state, start = prepared[opportunity]
            result = investigate.step(
                dsn, None, native, start["investigation_id"], target_revision=0,
                staging_root=staging, artifacts_root=artifacts)
            observation = result.get("last_observation") or {}
            if (observation.get("status") not in {"passed", "failed"}
                    or type(observation.get("passed")) is not bool):
                raise RuntimeError(
                    f"native P01 branch has no checked outcome: {json.dumps(result, sort_keys=True)}")
            experience.capture_investigation(
                dsn, start["investigation_id"], artifacts_root=artifacts)
            evidence = search.capture(dsn, digest, opportunity,
                                     staging_root=staging, artifacts_root=artifacts)
            branches.append(evidence["digest"])
    policies = {}
    for label, adaptive in (("authored-restricted", False), ("authored-general", True)):
        policy_genome = _policy_genome(genome, adaptive=adaptive)
        _publish_genome(dsn, policy_genome, staging, artifacts,
                        origin="p06-authored-policy:" + label)
        policies[label] = {"genome": policy_genome.digest, "name": "choose-branch",
                           "interface": POLICY_INTERFACE, "timeout_ms": 5000,
                           "max_output_bytes": 65536}
    collection = {"schema": "p06-collection/1", "run_id": run_id,
                  "scenario_sha256": sha(canonical(scenario)),
                  "frames": frames, "branches": branches,
                  "methods": {key: value.digest for key, value in methods.items()},
                  "policies": policies, "policy_parent": "separate-authored-genomes",
                  "provenance": {"collection": "authored-native-fixture",
                                 "model_acquisition": "not-run"},
                  "gaps": {"unexecuted_opportunity": "prepared-but-unexecuted",
                           "missing_continuation": "no-child-recorded"},
                  "costs": {"native_work": "recorded-per-branch", "model_admissions": 0},
                  "private_result_evidence": {
                      "protected_future_marker": "P06-FUTURE-ONLY-8F23A1"}}
    write_json(output / "collection.json", collection)
    return collection


def screen(dsn: str, collection_path: Path, output: Path, *, checker,
           scenario_path: Path = SCENARIO) -> dict:
    from rsi import search
    collection = read_json(collection_path)
    if collection.get("schema") != "p06-collection/1":
        raise ValueError("unsupported P06 collection")
    scenario = _scenario(scenario_path)
    output.mkdir(parents=True, exist_ok=True)
    (output / "stage").mkdir()
    artifact_source = collection_path.parent / "collection-runtime" / "art"
    artifact_target = output / "art"
    artifact_target.mkdir(parents=True, exist_ok=True)
    for artifact in artifact_source.iterdir():
        if artifact.is_file() and len(artifact.name) == 64:
            shutil.copy2(artifact, artifact_target / artifact.name)
    roots = _roots(dsn, "screen-" + collection["run_id"], tokens=500_000, cpu=2_000_000)
    evaluations = {}
    for label, policy in collection["policies"].items():
        evaluation = search.evaluate(
            dsn, checker, policy, collection["frames"], collection["branches"],
            evaluation_id=f"p06-{label}-{collection['run_id']}",
            allocation_id=roots["cpu"], max_decisions=2,
            staging_root=output / "stage", artifacts_root=output / "art")
        recomputed = search.recompute(evaluation)
        rows = evaluation["results"]
        evaluations[label] = {
            "evaluation": evaluation, "offline": recomputed,
            "coverage": {
                "supported": sum(row.get("branch_status") == "supported" for row in rows),
                "gaps": sum(row.get("branch_status") == "gap" for row in rows),
                "missing_continuations": sum(
                    (row.get("continuation_query") or {}).get("status") == "gap" for row in rows),
                "closed_actions": all(row.get("status") in {"choose", "stop"} for row in rows),
            },
            "quality": {
                "passed": sum(row.get("quality", {}).get("passed") is True for row in rows),
                "failed": sum(row.get("quality", {}).get("passed") is False for row in rows),
                "unknown": sum(row.get("quality") is None for row in rows),
            },
            "costs": {
                "known": all(isinstance(row.get("resources"), dict)
                             and type(row["resources"].get("amount")) is int for row in rows),
                "reservations": [row.get("resources") for row in rows],
            },
        }
    report = {"schema": "p06-screening/1", "collection_sha256": sha(canonical(collection)),
              "frames": collection["frames"], "branches": collection["branches"],
              "evaluations": evaluations,
              "same_corpus": True,
              "limits": scenario["caps"]}
    write_json(output / "screening.json", report)
    return report


def recompute(bundle_path: Path, output: Path) -> dict:
    """Offline audit path. This does not inspect environment or connect to PostgreSQL."""
    from rsi.search import recompute as search_recompute
    bundle = read_json(bundle_path)
    if bundle.get("schema") == "p06-screening/1":
        if (bundle.get("same_corpus") is not True
                or not isinstance(bundle.get("frames"), list)
                or not isinstance(bundle.get("branches"), list)
                or set(bundle.get("evaluations", {})) !=
                {"authored-restricted", "authored-general"}):
            raise ValueError("screening bundle has incomplete shared-corpus identities")
        values = {}
        for label, row in bundle["evaluations"].items():
            evaluation = row.get("evaluation")
            if (not isinstance(evaluation, dict)
                    or evaluation.get("frames") != bundle["frames"]
                    or evaluation.get("branches") != bundle["branches"]):
                raise ValueError(f"screening corpus identity differs for {label}")
            computed = search_recompute(evaluation)
            if row.get("offline") != computed:
                raise ValueError(f"saved offline result differs for {label}")
            values[label] = computed
        report = {"schema": "p06-offline-recompute/1", "evaluations": values}
    elif bundle.get("schema") == "p06-live-result/1":
        nested = bundle.get("screening", {})
        accounting = _recompute_construction_accounting(bundle)
        if nested:
            if set(nested) != {"candidate", "incumbent", "candidate_diagnostic", "recomputed"}:
                raise ValueError("live result has incomplete screening evidence")
            computed = {label: search_recompute(nested[label]) for label in
                        ("candidate", "incumbent", "candidate_diagnostic")}
            if nested.get("recomputed") != computed:
                raise ValueError("live screening recomputation differs from its saved report")
            report = {"schema": "p06-offline-recompute/1", "evaluations": computed,
                      "construction_accounting": accounting,
                      "result_status": bundle.get("status")}
        else:
            report = {"schema": "p06-offline-recompute/1", "evaluations": {},
                      "construction_accounting": accounting,
                      "result_status": bundle.get("status"),
                      "quality": "unscored"}
    else:
        report = {"schema": "p06-offline-recompute/1",
                  "evaluations": {"evaluation": search_recompute(bundle)}}
    write_json(output, report)
    return report


def _recompute_construction_accounting(bundle: dict) -> dict:
    ids = bundle.get("construction_operation_ids")
    evidence = bundle.get("construction_accounting")
    if (not isinstance(ids, list) or len(ids) != 2
            or len(set(ids)) != 2 or not all(isinstance(item, str) for item in ids)
            or not isinstance(evidence, dict)
            or not isinstance(evidence.get("operations"), list)
            or len(evidence["operations"]) != 2):
        raise ValueError("live result lacks both durable constructor operation records")
    if [item.get("operation_id") for item in evidence["operations"]] != ids:
        raise ValueError("constructor operation evidence differs from frozen identities")
    attempts = bundle.get("construction_attempts")
    if (not isinstance(attempts, list) or len(attempts) > 2
            or any(not isinstance(item, dict) for item in attempts)):
        raise ValueError("live result must preserve no more than two construction attempts")
    attempt_ids = [item.get("operation_id") for item in attempts]
    if (attempt_ids != ids[:len(attempts)]
            or any(item.get("status") not in {
                "completed", "invalid", "timeout", "infra_failed", "unresolved"
            } for item in attempts)):
        raise ValueError("construction attempts do not follow the frozen operation order")
    admissions = 0
    known = unknown = 0
    for item in evidence["operations"]:
        if item.get("found") is not True:
            if item.get("found") is not False or item.get("receipts") != []:
                raise ValueError("missing constructor operation has contradictory evidence")
            continue
        admissions += 1
        receipts = item.get("receipts")
        if not isinstance(receipts, list) or any(
                not isinstance(row, dict) or not isinstance(row.get("outcome"), str)
                for row in receipts):
            raise ValueError("constructor receipts are malformed")
        reservation = item.get("reservation")
        if reservation is None:
            unknown += 1
        elif (not isinstance(reservation, dict)
              or type(reservation.get("amount")) is not int
              or reservation["amount"] < 0
              or not isinstance(reservation.get("state"), str)):
            raise ValueError("constructor reservation evidence is malformed")
        else:
            known += reservation["amount"]
    if evidence.get("admissions") != admissions or bundle.get("admissions") != admissions:
        raise ValueError("constructor admission count differs from durable operations")
    if (evidence.get("reserved_units_known") != known
            or evidence.get("reserved_units_unknown") != unknown):
        raise ValueError("constructor spend totals differ from durable reservation evidence")
    return {"operation_ids": ids, "admissions": admissions,
            "reserved_units_known": known, "reserved_units_unknown": unknown,
            "attempts": attempts,
            "outcomes": [
                {"operation_id": item["operation_id"],
                 "dispatch_state": item.get("dispatch_state"),
                 "reconcile_state": item.get("reconcile_state"),
                 "settled": item.get("settled"),
                 "receipt_outcomes": [row["outcome"] for row in item.get("receipts", [])],
                 "reservation": item.get("reservation")}
                for item in evidence["operations"]]}


def _prospective_use_result(outcome: dict, investigation_state: dict | None) -> dict:
    selected = outcome.get("opportunity_id") if isinstance(outcome, dict) else None
    acknowledgement = outcome.get("acknowledgement") if isinstance(outcome, dict) else None
    observation = (acknowledgement.get("observation")
                   if isinstance(acknowledgement, dict) else None)
    last = (investigation_state.get("last_observation")
            if isinstance(investigation_state, dict) else None)
    checked = (
        outcome.get("status") == "acknowledged"
        and selected in {"restricted", "general"}
        and isinstance(observation, dict)
        and observation.get("status") in {"passed", "failed"}
        and type(observation.get("passed")) is bool
        and observation["status"] == ("passed" if observation["passed"] else "failed")
        and isinstance(last, dict)
        and last.get("episode") == observation.get("episode")
        and last.get("verdict") == observation.get("verdict")
        and last.get("passed") is observation["passed"]
        and last.get("status") == observation["status"])
    return {"status": "complete" if checked else "unscored",
            "checked": checked, "passed": observation["passed"] if checked else None,
            "selected_opportunity": selected,
            "observation": observation if checked else None}


def _screen_eligibility(candidate: dict, incumbent: dict, frame_count: int,
                        cost_ceiling: int) -> dict:
    def coverage(value):
        return (value.get("supported") == frame_count and value.get("gaps") == 0
                and value.get("stops") == 0 and value.get("refusals") == 0)

    def cost(value):
        known = (value.get("screening_cpu_units_unknown") == 0
                 and type(value.get("screening_cpu_units")) is int)
        bounded = known and value["screening_cpu_units"] <= cost_ceiling
        return known, bounded

    candidate_coverage, incumbent_coverage = coverage(candidate), coverage(incumbent)
    candidate_cost_known, candidate_cost_bounded = cost(candidate)
    incumbent_cost_known, incumbent_cost_bounded = cost(incumbent)
    comparable = incumbent_coverage and incumbent_cost_known and incumbent_cost_bounded
    quality_ok = comparable and candidate.get("passed", -1) >= incumbent.get("passed", 0)
    eligible = (candidate_coverage and candidate_cost_bounded and quality_ok)
    return {"eligible": eligible, "coverage_all_frames": candidate_coverage,
            "incumbent_coverage_all_frames": incumbent_coverage,
            "no_worse_checked_quality": quality_ok,
            "costs_known": candidate_cost_known,
            "costs_bounded": candidate_cost_bounded,
            "incumbent_costs_known": incumbent_cost_known,
            "incumbent_costs_bounded": incumbent_cost_bounded,
            "reason": None if eligible else
            "candidate or incumbent lacked complete comparable coverage or bounded costs, "
            "or candidate checked quality was lower"}


def _route_provider(route_file: Path):
    from settlement.launcher_codex import Provider
    values = {}
    for raw in route_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            key, sep, value = line.partition("=")
            if not sep:
                raise ValueError("route file contains a malformed assignment")
            values[key.strip()] = value.strip().strip("\"'")
    if (values.get("SETTLEMENT_GATEWAY_MODEL") != MODEL
            or not values.get("SETTLEMENT_GATEWAY_KEY")
            or not values.get("SETTLEMENT_GATEWAY_ENDPOINT")):
        raise ValueError("live mode requires the approved free OpenRouter route")
    return Provider(values["SETTLEMENT_GATEWAY_ENDPOINT"], MODEL,
                    values["SETTLEMENT_GATEWAY_KEY"])


def _grant(dsn: str, agenda_id: str, charter: dict, policy_genome: str,
           worker_genomes: list[str]) -> None:
    from settlement import broker, store
    from settlement.common import Command
    store.seed_grant(dsn, Command(
        request_id="p06-grant:" + agenda_id,
        payload={"version": charter["grant_version"],
                 "charter_text": charter["objective"],
                 "authority_grant": {
                     "kind": "rsi-agenda", "agenda_id": agenda_id,
                     "development_task_ids": sorted({item["task_id"]
                                                      for item in charter["opportunities"]}),
                     "genome_ids": sorted(set(worker_genomes + [policy_genome])),
                     "effects": [broker.AGENT_RUN, broker.SANDBOX_EXEC]},
                 "envelopes": {
                     "tokens": {"allocation_id": charter["allocations"]["tokens"]["id"],
                                "units": charter["allocations"]["tokens"]["units"]},
                     "cpu": {"allocation_id": charter["allocations"]["cpu"]["id"],
                             "units": charter["allocations"]["cpu"]["units"]},
                     "max_turns": charter["max_turns"]}}))


def run_live(dsn: str, freeze_path: Path, collection_path: Path, output: Path,
             route_file: Path = ROUTE_FILE) -> dict:
    """Construct once, screen unchanged bytes, then use only an eligible policy."""
    from experiments.search06.freeze import verify_freeze
    frozen = verify_freeze(ROOT, freeze_path, collection_path, route_file=route_file)
    if frozen["mode"] != "live":
        raise ValueError("live run requires a live-mode prospective freeze")
    plan = frozen["live_plan"]
    run_id = _claim_run(frozen, freeze_path, output)
    scenario = _scenario()
    collection = read_json(collection_path)
    from rsi import agenda, capability, experience, genome, investigate, search, task
    from settlement.launcher_codex import CodexLauncher
    from settlement.launcher_local import LocalLauncher

    root = output / "runtime"
    staging, artifacts = root / "stage", root / "art"
    staging.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    artifact_source = collection_path.parent / "collection-runtime" / "art"
    for artifact in artifact_source.iterdir():
        if artifact.is_file() and len(artifact.name) == 64:
            target = artifacts / artifact.name
            if target.exists():
                if target.read_bytes() != artifact.read_bytes():
                    raise ValueError("runtime artifact differs from the frozen collection")
            else:
                shutil.copy2(artifact, target)
    native = LocalLauncher(root / "native")
    provider = _route_provider(route_file)
    agent = CodexLauncher(root / "constructor", codex_cmd=[str(CODEX)], provider=provider,
                          allowed_overrides=genome.HARNESS_KEYS)
    roots = _roots(dsn, run_id, tokens=800_000, cpu=2_400_000,
                   identities=plan["allocations"]["construction"])

    # Use all six captured outcomes: both executed methods in every frozen frame.
    source_observations, source_branches = [], []
    seen_observations = set()
    for frame_digest in collection["frames"]:
        frame = search.load_frame(dsn, frame_digest, artifacts_root=artifacts)
        for opportunity in ("general", "restricted"):
            start = frame["starts"][opportunity]
            rows = experience.capture_investigation(
                dsn, start["investigation_id"], artifacts_root=artifacts)
            if not rows:
                raise RuntimeError("a collected P01 branch has no captured experience")
            for row in rows:
                observation_id = row["observation_id"]
                if observation_id not in seen_observations:
                    seen_observations.add(observation_id)
                    source_observations.append(row)
            source_branches.append({"frame": frame_digest,
                                    "opportunity_id": opportunity,
                                    "investigation_id": start["investigation_id"],
                                    "observation_ids": [row["observation_id"] for row in rows]})
    if len(source_branches) != 6 or len(source_observations) != 6:
        raise RuntimeError("construction requires six distinct captured branch observations")
    qualification = _sum_task(task, run_id + "-construction", 2, 3, 5)
    task.publish(dsn, qualification, staging_root=staging, artifacts_root=artifacts)
    parent = genome.Genome({
        "AGENTS.md": (
            b"Construct one exploration-policy/1 method that selects exactly one ID "
            b"from the visible menu using public development history. The request value "
            b"contains objective, menu, prefix, and limits. Return one object with value "
            b"equal to {action: choose, opportunity_id: selected_id} and empty files. "
            b"Use only the visible frame. Do not refer to hidden outcomes or claim checks.\n"
        )})
    _publish_genome(dsn, parent, staging, artifacts, origin="p06-constructor-parent:" + run_id)
    owner_id = run_id + "-context-owner"
    owner = investigate.create(
        dsn, agent, parent, investigation_id=owner_id, task=qualification,
        token_allocation=roots["tokens"], cpu_allocation=roots["cpu"],
        max_steps=1, timeout_ms=scenario["caps"]["action_timeout_ms"],
        token_ceiling=scenario["caps"]["action_token_units"],
        objective="Use the captured addition branches as development evidence for a visible-frame policy.",
        memory={"scope": {"domain": "task"}, "view": "raw-history", "limit": 10},
        context={"policy": "raw-history/1", "required_observation_ids": [
            row["observation_id"] for row in source_observations]},
        staging_root=staging, artifacts_root=artifacts)
    prepared = investigate.prepare_context(
        dsn, owner_id, target_revision=owner["revision"], artifacts_root=artifacts)
    if "visible_input" not in prepared or prepared["visible_input"]["context_packet"].get("status") != "ready":
        raise RuntimeError("actual P01 evidence did not produce a ready P03 construction packet")
    packet = prepared["visible_input"]["context_packet"]
    report = {"schema": "p06-live-result/1", "run_id": run_id,
              "freeze_sha256": frozen["freeze_sha256"],
              "construction_operation_ids": plan["operations"]["construction"],
              "construction_attempts": [],
              "construction": {"status": "not-started"},
              "admissions": _construction_admissions(dsn, plan["operations"]["construction"]),
              "provenance": {"source_observation_ids": [
                  row["observation_id"] for row in source_observations],
                  "source_branches": source_branches,
                  "model_candidate": "not-yet-screened"}}
    try:
        construction = capability.construct(
            dsn, agent, parent, name="choose-branch", interface=POLICY_INTERFACE,
            context_packet=packet, operation_id=plan["operations"]["construction"][0],
            allocation_id=roots["tokens"], token_ceiling=scenario["caps"]["action_token_units"],
            timeout_ms=scenario["caps"]["action_timeout_ms"],
            staging_root=staging, artifacts_root=artifacts)
    except Exception as exc:  # noqa: BLE001 - unknown dispatch exceptions must stop safely
        unresolved = {"status": "unresolved", "detail": type(exc).__name__,
                      "operation_id": plan["operations"]["construction"][0]}
        report["construction_attempts"].append(unresolved)
        report.update(status="unscored", stop="construction effect unresolved",
                      construction=unresolved,
                      admissions=_construction_admissions(
                          dsn, plan["operations"]["construction"]))
        _save_live_report(dsn, output, report, plan["operations"]["construction"])
        return report
    report["construction_attempts"].append(construction)
    report["construction"] = construction
    if _construction_action(construction) == "repair":
        repair_parent = genome.Genome({
            **parent.files,
            "AGENTS.md": (parent.files["AGENTS.md"].decode("utf-8") +
                          "The prior completed response was unusable. Return one complete "
                          "method package that obeys the stated interface and action shape.\n").encode("utf-8")})
        _publish_genome(dsn, repair_parent, staging, artifacts,
                        parent=parent.digest, origin="p06-constructor-repair-parent:" + run_id)
        try:
            construction = capability.construct(
                dsn, agent, repair_parent, name="choose-branch", interface=POLICY_INTERFACE,
                context_packet=packet, operation_id=plan["operations"]["construction"][1],
                allocation_id=roots["tokens"], token_ceiling=scenario["caps"]["action_token_units"],
                timeout_ms=scenario["caps"]["action_timeout_ms"],
                staging_root=staging, artifacts_root=artifacts)
        except Exception as exc:  # noqa: BLE001 - unknown repair dispatch must stop safely
            unresolved = {"status": "unresolved", "detail": type(exc).__name__,
                          "operation_id": plan["operations"]["construction"][1]}
            report["construction_attempts"].append(unresolved)
            report.update(status="unscored", stop="repair effect unresolved",
                          construction=unresolved,
                          admissions=_construction_admissions(
                              dsn, plan["operations"]["construction"]))
            _save_live_report(dsn, output, report, plan["operations"]["construction"])
            return report
        report["construction_attempts"].append(construction)
        report["construction"] = construction
        report["admissions"] = _construction_admissions(
            dsn, plan["operations"]["construction"])
    if _construction_action(construction) != "screen":
        report.update(status=("unscored" if construction.get("status") in
                              ("timeout", "infra_failed") else "no-acquisition"),
                      stop="constructor did not produce a complete candidate")
        _save_live_report(dsn, output, report, plan["operations"]["construction"])
        return report
    candidate = genome.load(dsn, artifacts, construction["child"])
    method, = (item for item in capability.catalogue(candidate)
               if item.name == "choose-branch" and item.interface == POLICY_INTERFACE)
    if construction.get("method_digest") != method.digest:
        raise RuntimeError("constructed policy bytes changed after response")
    report["candidate"] = {"genome": candidate.digest, "method_digest": method.digest,
                            "bytes_unchanged": True}
    screen_roots = _roots(dsn, run_id + "-candidate-screen", tokens=100_000, cpu=2_400_000,
                          identities=plan["allocations"]["candidate_screen"])
    incumbent_roots = _roots(dsn, run_id + "-incumbent-screen", tokens=100_000, cpu=2_400_000,
                             identities=plan["allocations"]["incumbent_screen"])
    diagnostic_roots = _roots(dsn, run_id + "-diagnostic-screen", tokens=100_000, cpu=2_400_000,
                              identities=plan["allocations"]["diagnostic_screen"])
    policy = {"genome": candidate.digest, "name": "choose-branch",
              "interface": POLICY_INTERFACE, "timeout_ms": 5000,
              "max_output_bytes": 65536}
    primary_id = plan["operations"]["candidate_screen"]
    incumbent_id = plan["operations"]["incumbent_screen"]
    diagnostic_id = plan["operations"]["diagnostic_screen"]
    try:
        screening = search.evaluate(
            dsn, native, policy, collection["frames"], collection["branches"],
            evaluation_id=primary_id, allocation_id=screen_roots["cpu"],
            max_decisions=1, staging_root=staging, artifacts_root=artifacts)
        incumbent = search.evaluate(
            dsn, native, collection["policies"]["authored-general"],
            collection["frames"], collection["branches"],
            evaluation_id=incumbent_id, allocation_id=incumbent_roots["cpu"],
            max_decisions=1, staging_root=staging, artifacts_root=artifacts)
        diagnostic = search.evaluate(
            dsn, native, policy, collection["frames"], collection["branches"],
            evaluation_id=diagnostic_id, allocation_id=diagnostic_roots["cpu"],
            max_decisions=2, staging_root=staging, artifacts_root=artifacts)
    except Exception as exc:  # noqa: BLE001 - replay effects stay unscored on uncertainty
        report.update(status="unscored", stop="screening effect unresolved",
                      screening={"status": "unresolved", "detail": type(exc).__name__},
                      admissions=_construction_admissions(
                          dsn, plan["operations"]["construction"]))
        _save_live_report(dsn, output, report, plan["operations"]["construction"])
        return report
    candidate_result = search.recompute(screening)
    incumbent_result = search.recompute(incumbent)
    diagnostic_result = search.recompute(diagnostic)
    frames_count = len(collection["frames"])
    eligibility = _screen_eligibility(
        candidate_result, incumbent_result, frames_count, plan["screening_cpu_ceiling"])
    costs_bounded = eligibility["costs_bounded"]
    eligible = eligibility["eligible"]
    report["screening"] = {"candidate": screening, "incumbent": incumbent,
                           "candidate_diagnostic": diagnostic,
                           "recomputed": {"candidate": candidate_result,
                                          "incumbent": incumbent_result,
                                          "candidate_diagnostic": diagnostic_result}}
    report["coverage"] = {"supported": candidate_result["supported"],
                          "gaps": candidate_result["gaps"],
                          "stops": candidate_result["stops"],
                          "refusals": candidate_result["refusals"],
                          "frames": frames_count}
    report["quality"] = {"candidate_passed": candidate_result["passed"],
                         "candidate_failed": candidate_result["failed"],
                         "incumbent_passed": incumbent_result["passed"],
                         "incumbent_failed": incumbent_result["failed"]}
    report["costs"] = {"candidate_screen_cpu_units": candidate_result["screening_cpu_units"],
                       "candidate_screen_cpu_units_unknown":
                       candidate_result["screening_cpu_units_unknown"],
                       "ceiling": plan["screening_cpu_ceiling"],
                       "bounded": costs_bounded}
    report["eligibility"] = eligibility
    if not eligible:
        report.update(status="rejected", stop=report["eligibility"]["reason"])
        _save_live_report(dsn, output, report, plan["operations"]["construction"])
        return report

    fresh = _sum_task(task, run_id + "-fresh-use", -3, 8, 5)
    task.publish(dsn, fresh, staging_root=staging, artifacts_root=artifacts)
    use_value = {"left": -3, "right": 8}
    agenda_roots = _roots(dsn, run_id + "-agenda", tokens=400_000, cpu=900_000,
                          identities=plan["allocations"]["agenda"])
    workers = {kind: genome.load(dsn, artifacts, collection["methods"][kind])
               for kind in ("restricted", "general")}
    method_eligibility = {
        kind: capability.eligibility(
            dsn, genome=worker, name="integer-sum", interface=INTERFACE,
            task_id=fresh.digest, value=use_value, artifacts_root=artifacts)
        for kind, worker in workers.items()}
    report["worker_method_eligibility"] = method_eligibility
    if any(value.get("status") != "selected" for value in method_eligibility.values()):
        report.update(status="rejected", stop="fresh native alternatives were not eligible")
        _save_live_report(dsn, output, report, plan["operations"]["construction"])
        return report
    opportunities = []
    for kind, worker in workers.items():
        investigation_id = run_id + "-fresh-" + kind
        investigate.create(
            dsn, None, worker, investigation_id=investigation_id, task=fresh,
            token_allocation=agenda_roots["tokens"], cpu_allocation=agenda_roots["cpu"],
            max_steps=1, timeout_ms=5000, token_ceiling=50_000,
            method={"name": "integer-sum", "interface": INTERFACE, "value": use_value},
            staging_root=staging, artifacts_root=artifacts)
        opportunities.append({
            "id": kind, "task_id": fresh.digest, "genome_id": worker.digest,
            "objective": "Run the retained integer-sum method on a changed public input.",
            "question": "Does the selected method return the exact sum?",
            "priority": 1 if kind == "general" else 2,
            "expected_observation": "The pristine verifier result.",
            "stop_condition": "One checked native method use.", "max_steps": 1,
            "timeout_ms": 5000,
            "resource_ceilings": {"tokens": 50_000, "cpu": 100_000},
            "investigation_id": investigation_id,
            "method_request": {"name": "integer-sum", "interface": INTERFACE,
                               "value": use_value}})
    agenda_id = plan["operations"]["agenda"]
    charter = {"grant_version": 1,
               "objective": "Use the screened policy for one fresh checked method use.",
               "allocations": {"tokens": {"id": agenda_roots["tokens"], "units": 400_000},
                               "cpu": {"id": agenda_roots["cpu"], "units": 900_000}},
               "policy": {"genome": candidate.digest, "name": "choose-branch",
                          "interface": POLICY_INTERFACE, "timeout_ms": 5000,
                          "max_output_bytes": 65536},
               "max_turns": 1,
               "opportunities": opportunities}
    _grant(dsn, agenda_id, charter, candidate.digest,
           [worker.digest for worker in workers.values()])
    charter["deadline"] = _agenda_use_deadline(
        agenda.read(dsn, agenda_id), frozen["caps"]["max_use_seconds"])
    agenda.create(dsn, agenda_id=agenda_id, charter=charter, artifacts_root=artifacts)
    try:
        used = agenda.wake(dsn, agent, native, agenda_id,
                           staging_root=staging, artifacts_root=artifacts)
    except Exception as exc:  # noqa: BLE001 - agenda effects stay unscored on uncertainty
        report.update(status="unscored", stop="prospective-use effect unresolved",
                      prospective_use={"agenda_id": agenda_id,
                                       "status": "unresolved",
                                       "detail": type(exc).__name__})
        _save_live_report(dsn, output, report, plan["operations"]["construction"])
        return report
    end_state = agenda.read(dsn, agenda_id)
    outcome = end_state.get("last_result") or used
    selected = outcome.get("opportunity_id")
    observation = (investigate.read(dsn, run_id + "-fresh-" + selected)
                   if selected in {"restricted", "general"} else None)
    classified = _prospective_use_result(outcome, observation)
    report.update(status=classified["status"], prospective_use={
        "wake": used, "outcome": outcome, "agenda_id": agenda_id, **classified})
    _save_live_report(dsn, output, report, plan["operations"]["construction"])
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    collect_cmd = commands.add_parser("collect")
    collect_cmd.add_argument("--dsn", default=os.environ.get("SETTLEMENT_TEST_DSN"))
    collect_cmd.add_argument("--output", type=Path, required=True)
    collect_cmd.add_argument("--scenario", type=Path, default=SCENARIO)
    screen_cmd = commands.add_parser("screen")
    screen_cmd.add_argument("--dsn", default=os.environ.get("SETTLEMENT_TEST_DSN"))
    screen_cmd.add_argument("--collection", type=Path, required=True)
    screen_cmd.add_argument("--output", type=Path, required=True)
    screen_cmd.add_argument("--scenario", type=Path, default=SCENARIO)
    offline_cmd = commands.add_parser("recompute")
    offline_cmd.add_argument("--bundle", type=Path, required=True)
    offline_cmd.add_argument("--output", type=Path, required=True)
    for name in ("freeze", "run"):
        command = commands.add_parser(name)
        command.add_argument("--freeze", type=Path, required=True)
        command.add_argument("--collection", type=Path, required=True)
        if name == "freeze":
            command.add_argument("--mode", choices=("fixture", "live"), required=True)
            command.add_argument("--route-file", type=Path, default=ROUTE_FILE)
            command.add_argument("--scenario", type=Path, default=SCENARIO)
        else:
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--dsn", default=os.environ.get("SETTLEMENT_TEST_DSN"))
            command.add_argument("--route-file", type=Path, default=ROUTE_FILE)
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.command == "collect":
        if not args.dsn:
            raise SystemExit("collect requires --dsn or SETTLEMENT_TEST_DSN")
        value = collect(args.dsn, args.output, scenario_path=args.scenario)
    elif args.command == "screen":
        if not args.dsn:
            raise SystemExit("screen requires --dsn or SETTLEMENT_TEST_DSN")
        from settlement.launcher_local import LocalLauncher
        checker = LocalLauncher(args.output / "policy-runs")
        value = screen(args.dsn, args.collection, args.output, checker=checker,
                       scenario_path=args.scenario)
    elif args.command == "recompute":
        value = recompute(args.bundle, args.output)
    elif args.command == "freeze":
        try:
            from .freeze import freeze
        except ImportError:
            from freeze import freeze
        value = freeze(ROOT, args.freeze, args.collection, mode=args.mode,
                       route_file=args.route_file, scenario_path=args.scenario)
    else:
        if not args.dsn:
            raise SystemExit("run requires --dsn or SETTLEMENT_TEST_DSN")
        value = run_live(args.dsn, args.freeze, args.collection, args.output,
                         route_file=args.route_file)
    print(json.dumps({"schema": value.get("schema"), "status": value.get("status", "complete"),
                      "frames": len(value.get("frames", [])),
                      "branches": len(value.get("branches", []))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
