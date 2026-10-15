"""Freeze or run the bounded P04 summary-method acquisition experiment."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

MODEL = "openrouter/openrouter/free"
INTERFACE = "integer-summary/1"
NAME = "summary"
VALUES = ([3, -2, 7], [-8, -3], [], [4, 4, 1])
SOURCE_PATHS = (
    "pyproject.toml", "uv.lock",
    "AGENTS.md", "docs/plans/04-CAPABILITIES.md", "src/rsi/capability.py",
    "src/rsi/_method_runner.py", "src/rsi/genome.py", "src/rsi/task.py",
    "src/rsi/context.py", "src/rsi/investigate.py", "src/rsi/episode.py",
    "src/rsi/investigation.py", "src/rsi/archive.py", "src/rsi/verifier.py",
    "src/settlement/db.py", "src/settlement/store.py", "src/settlement/common.py",
    "src/settlement/broker.py", "src/settlement/artifacts.py",
    "src/settlement/launcher_codex.py", "src/settlement/launcher_local.py",
    "experiments/capability04/driver.py", "experiments/capability04/check.py",
    "tests/test_rsi_capability_campaign.py",
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, value):
    raw = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                     allow_nan=False, default=str) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(raw, encoding="utf-8", newline="\n")
    temp.replace(path)


def source_manifest(repo: Path):
    sources = {}
    for rel in SOURCE_PATHS:
        path = repo / rel
        if not path.is_file():
            raise RuntimeError(f"frozen source is missing: {rel}")
        sources[rel] = _sha(path.read_bytes())
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                            capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *SOURCE_PATHS],
                           cwd=repo, check=True, capture_output=True,
                           text=True).stdout.strip()
    if dirty:
        raise RuntimeError("freeze requires clean pinned source files")
    return {
        "schema": "p04-capability-source/1", "commit": commit,
        "sources": sources,
        "route_model": MODEL,
        "runtime_python": sys.version,
        "pinned": {"parent_genome": _public_parent().digest,
                   "development_task": _summary_task(VALUES[0], "dev").digest},
        "method": {"name": NAME, "interface": INTERFACE,
                   "objective": "For a finite JSON list of integers, return count, total, minimum and maximum; use null bounds for an empty list.",
                   "development_value": VALUES[0], "later_values": list(VALUES[1:]),
                   "solution_file": "summary.json", "parent_genome": ["AGENTS.md"]},
         "limits": {"max_construction_calls": 2, "constructor_timeout_ms": 180_000,
                   "constructor_tokens": 100_000, "allocation_tokens": 200_000,
                   "method_timeout_ms": 30_000, "max_steps": 1},
    }


def freeze(repo: Path, bundle: Path):
    bundle.mkdir(parents=True, exist_ok=True)
    manifest_path = bundle / "manifest.json"
    if manifest_path.exists():
        raise RuntimeError("frozen manifest already exists; refusing to replace it")
    manifest = source_manifest(repo.resolve())
    _write_json(manifest_path, manifest)
    return manifest


def verify_freeze(repo: Path, bundle: Path):
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = source_manifest(repo.resolve())
    frozen = {key: value for key, value in manifest.items() if key != "commit"}
    observed = {key: value for key, value in current.items() if key != "commit"}
    if observed != frozen:
        raise RuntimeError("pinned source, runtime, or experiment contract changed after freeze")
    return manifest


def _route(path: Path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise RuntimeError("route file has a malformed assignment")
        values[key.strip()] = value.strip().strip('"').strip("'")
    required = {"SETTLEMENT_GATEWAY_ENDPOINT", "SETTLEMENT_GATEWAY_MODEL",
                "SETTLEMENT_GATEWAY_KEY"}
    if required - values.keys():
        raise RuntimeError("route file is missing required gateway settings")
    if any(not values[key] for key in required):
        raise RuntimeError("route file contains an empty gateway setting")
    if values["SETTLEMENT_GATEWAY_MODEL"] != MODEL:
        raise RuntimeError("only the frozen free route is permitted")
    return values


def _check_route(route):
    endpoint = route["SETTLEMENT_GATEWAY_ENDPOINT"].rstrip("/")
    url = endpoint if endpoint.endswith("/models") else endpoint + "/models"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + route["SETTLEMENT_GATEWAY_KEY"],
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = json.loads(response.read(2_000_000))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise RuntimeError("free route availability check failed") from exc
    entries = body.get("data", body.get("models", [])) if isinstance(body, dict) else []
    names = {item.get("id", item.get("slug")) for item in entries if isinstance(item, dict)}
    if MODEL not in names:
        raise RuntimeError("free route is not listed by the single availability check")


def _refuse_used_database(dsn):
    from settlement import db

    with db.connect(dsn) as conn:
        tables = conn.execute(
            "SELECT schemaname, tablename FROM pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
        ).fetchall()
    if tables:
        raise RuntimeError("P04 requires an unused dedicated database; existing tables found")


def _record_artifact(artifacts_root: Path, digest: str):
    raw = (artifacts_root / digest).read_bytes()
    if _sha(raw) != digest:
        raise RuntimeError("published artifact bytes do not match their content digest")
    return raw


def _expected(values):
    return {"count": len(values), "total": sum(values),
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None}


def _public_parent():
    from rsi.genome import Genome

    specification = (
        "# Public method contract\n"
        "Methods receive request.interface, request.value, request.files and request.context. "
        "The requested method interface is integer-summary/1. For a finite JSON list of "
        "integers, return a JSON object containing count, total, minimum and maximum; "
        "minimum and maximum are null for an empty list. Write the same result as UTF-8 "
        "JSON to the declared summary.json solution slot. Use Python standard library only.\n"
    )
    return Genome({"AGENTS.md": specification.encode("utf-8")})


def _summary_task(values, run_id):
    from rsi.task import Task

    expected = _expected(values)
    reference = json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n"
    verifier = (
        "import json\nimport unittest\nfrom pathlib import Path\n"
        "class SummaryTest(unittest.TestCase):\n"
        "    def test_summary(self):\n"
        "        self.assertEqual(json.loads(Path('summary.json').read_text(encoding='utf-8')), "
        f"{expected!r})\n"
    ).encode()
    instruction = ("Implement the public integer-summary/1 method contract for the input "
                   + json.dumps(values) + ". Write summary.json.")
    return Task("p04-summary-" + run_id, "dev", instruction,
                {"summary.json": b""}, {"test_summary.py": verifier},
                {"summary.json": reference.encode("utf-8")}, ("test_summary.py",))


def _context_packet(dsn, state, artifacts_root):
    from rsi import context, investigate

    continuation = {
        "objective": state["objective"],
        "objective_revision": state["objective_revision"],
        "state_revision": state["revision"],
        "open_questions": state["open_questions"],
        "artifact_refs": state["artifact_refs"],
        "previous_observation": state["last_observation"],
    }
    suffix = uuid.uuid4().hex
    request = investigate._context_request(
        state["investigation_id"], state["objective_revision"], state["revision"],
        "p04-context-decision-" + suffix, "p04-context-attempt-" + suffix,
        "p04-context-operation-" + suffix, state["objective"], continuation,
        investigate._context_options(state["config"].get("context"),
                                     state["config"].get("memory"), stored=True),
    )
    packet = context.build(dsn, request, artifacts_root=artifacts_root)
    validation = context.validate(dsn, packet, artifacts_root=artifacts_root)
    if packet.get("status") != "ready" or validation.get("status") != "ready":
        raise RuntimeError("construction context packet is not ready")
    return packet


def _allocations(dsn, tag):
    from settlement import store
    from settlement.common import Command, ResultCode

    token, cpu = "p04-" + tag + "-tokens", "p04-" + tag + "-cpu"
    for allocation, domain, amount in ((token, "tokens", 200_000), (cpu, "cpu", 1_800_000)):
        result = store.seed_allocation(dsn, Command(
            request_id="seed-" + allocation,
            payload={"allocation_id": allocation, "domain": domain,
                      "authorized": amount, "owner_scope": "p04-capability-campaign"}))
        if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            raise RuntimeError("campaign allocation was not admitted")
    return token, cpu


def run(repo: Path, bundle: Path, dsn: str, route_file: Path,
        logs_root: Path, codex: str):
    manifest = verify_freeze(repo, bundle)
    route = _route(route_file)
    _check_route(route)
    _refuse_used_database(dsn)

    from rsi import capability, genome, investigate, task
    from settlement import db, store
    from settlement.launcher_codex import CodexLauncher, Provider
    from settlement.launcher_local import LocalLauncher

    root = bundle / "runtime"
    staging, artifacts_root = root / "stage", root / "art"
    native, local = LocalLauncher(root / "method-runs"), LocalLauncher(root / "verifiers")
    for path in (staging, artifacts_root, logs_root):
        path.mkdir(parents=True, exist_ok=True)
    db.apply_migrations(dsn, repo / "migrations")
    run_id = uuid.uuid4().hex[:12]
    token_allocation, cpu_allocation = _allocations(dsn, run_id)
    parent = _public_parent()
    genome.publish(dsn, parent, parent=None, origin="p04-parent:" + run_id,
                   staging_root=staging, artifacts_root=artifacts_root)
    dev_task = _summary_task(VALUES[0], "dev")
    task.publish(dsn, dev_task, staging_root=staging, artifacts_root=artifacts_root)
    provider = Provider(route["SETTLEMENT_GATEWAY_ENDPOINT"], MODEL,
                        route["SETTLEMENT_GATEWAY_KEY"])
    agent = CodexLauncher(root / "constructor-runs", codex_cmd=[codex], provider=provider,
                          allowed_overrides=genome.HARNESS_KEYS)
    objective = ("Construct a reusable method for the public integer-summary/1 contract: "
                 "for finite integer lists, return count, total, minimum and maximum, with "
                 "null minimum and maximum for an empty list. The development input is public.")
    owner_id = "p04-construction-owner-" + run_id
    owner = investigate.create(
        dsn, None, parent, investigation_id=owner_id, task=dev_task,
        token_allocation=token_allocation, cpu_allocation=cpu_allocation,
        max_steps=1, timeout_ms=180_000, token_ceiling=100_000,
        staging_root=staging, artifacts_root=artifacts_root, objective=objective,
        method={"name": NAME, "interface": INTERFACE, "value": VALUES[0]},
    )
    packet = _context_packet(dsn, owner, artifacts_root)
    report = {"schema": "p04-capability-campaign/1",
              "source_manifest_digest": _sha(_canonical(manifest)),
              "run_id": run_id, "route_model": MODEL,
              "construction_calls": 0,
              "allocations": {name: _allocation_summary(store.allocation_status(dsn, name))
                              for name in (token_allocation, cpu_allocation)},
              "parent": {"digest": parent.digest,
                         "files": {p: raw.hex() for p, raw in parent.files.items()},
                         "package": base64.b64encode(
                             _record_artifact(artifacts_root, parent.digest)).decode("ascii")},
              "construction_operation_id": "p04-construct-" + run_id,
              "construction": {"status": "not-started"},
              "task": {"digest": dev_task.digest, "split": "dev",
                       "reference": {p: raw.decode("utf-8")
                                     for p, raw in dev_task.reference.items()},
                       "package": base64.b64encode(
                           _record_artifact(artifacts_root, dev_task.digest)).decode("ascii")},
              "uses": []}
    try:
        report["construction_calls"] = 1
        construction = capability.construct(
            dsn, agent, parent, name=NAME, interface=INTERFACE,
            context_packet=packet, operation_id=report["construction_operation_id"],
            allocation_id=token_allocation, token_ceiling=100_000, timeout_ms=180_000,
            staging_root=staging, artifacts_root=artifacts_root,
        )
    except Exception as exc:  # noqa: BLE001 - preserve any unsettled constructor effect
        report["construction"] = {"status": "unresolved", "detail": type(exc).__name__}
        report["status"] = "unresolved"
        _checkpoint(report, bundle, dsn, artifacts_root, route)
        return {"status": "unresolved", "operation_id": report["construction_operation_id"]}
    report["construction"] = construction
    _checkpoint(report, bundle, dsn, artifacts_root, route)
    if construction.get("status") != "completed" or not construction.get("child"):
        report["status"] = ("unscored" if construction.get("status") in
                            ("timeout", "infra_failed") else "no-acquisition")
        _checkpoint(report, bundle, dsn, artifacts_root, route)
        return {"status": report["status"], "construction": construction.get("status")}

    child = genome.load(dsn, artifacts_root, construction["child"])
    report["child"] = {"digest": child.digest,
                       "files": {p: raw.hex() for p, raw in child.files.items()},
                       "package": base64.b64encode(
                           _record_artifact(artifacts_root, child.digest)).decode("ascii")}
    method, = (item for item in capability.catalogue(child) if item.name == NAME)
    report["method_digest"] = method.digest
    if method.interface != INTERFACE or construction.get("method_digest") != method.digest:
        raise RuntimeError("constructed method identity did not match the frozen contract")
    try:
        dev = _run_and_export_method(
            dsn, run_id + "-dev", child, dev_task, VALUES[0], native, local,
            cpu_allocation, staging, artifacts_root)
    except Exception as exc:  # noqa: BLE001 - preserve any unsettled method effect
        report["status"] = "unresolved"
        report["stop"] = {"operation_id": run_id + "-dev", "detail": type(exc).__name__}
        _checkpoint(report, bundle, dsn, artifacts_root, route)
        return {"status": "unresolved", "operation_id": run_id + "-dev"}
    report["uses"].append(dev)
    _checkpoint(report, bundle, dsn, artifacts_root, route)
    if dev.get("verdict", {}).get("passed") is not True:
        report["status"] = "candidate-failed-development"
        report["retention"] = {"status": "rejected", "episode_id": dev["episode"]["id"]}
        _checkpoint(report, bundle, dsn, artifacts_root, route)
        return {"status": "candidate-failed-development", "episode": dev["episode"]["id"]}
    report["retention"] = capability.retain(
        dsn, "p04-retain-" + run_id, genome=child, name=NAME,
        episode_id=dev["episode"]["id"], artifacts_root=artifacts_root)
    report["selection"] = capability.select(
        dsn, "p04-select-" + run_id, genome=child, name=NAME,
        interface=INTERFACE, artifacts_root=artifacts_root)
    _checkpoint(report, bundle, dsn, artifacts_root, route)
    if report["selection"].get("status") != "selected":
        raise RuntimeError("checked method was not selected for changed-input investigation")
    for index, values in enumerate(VALUES[1:], start=1):
        try:
            report["uses"].append(_run_later_in_fresh_process(
                dsn, run_id, index, child, values, token_allocation, cpu_allocation,
                root, staging, artifacts_root, logs_root))
        except Exception as exc:  # noqa: BLE001 - preserve any unsettled subprocess effect
            report["status"] = "unresolved"
            report["stop"] = {"investigation_id": f"p04-later-{run_id}-{index}",
                              "detail": type(exc).__name__}
            _checkpoint(report, bundle, dsn, artifacts_root, route)
            return {"status": "unresolved", **report["stop"]}
        _checkpoint(report, bundle, dsn, artifacts_root, route)
    report["status"] = "completed"
    _checkpoint(report, bundle, dsn, artifacts_root, route)
    return {"status": "completed", "uses": len(report["uses"]),
            "report": str(bundle / "report.json")}


def _run_and_export_method(dsn, operation_id, genome, task, values, launcher,
                           verifier_launcher, allocation_id, staging_root, artifacts_root):
    from rsi import episode, verifier

    request = {"interface": INTERFACE, "value": values,
               "files": {"summary.json": ""}, "context": {}}
    result = episode.run_method_episode(
        dsn, launcher, genome, name=NAME, request=request,
        operation_id=operation_id, task=task, allocation_id=allocation_id,
        attempt_id=None, staging_root=staging_root, artifacts_root=artifacts_root,
        timeout_ms=30_000,
    )
    checked = None
    if result.status == "completed":
        checked = verifier.verify_episode(
            dsn, launcher, verifier_launcher, result.operation_id,
            allocation_id=allocation_id, attempt_id=None,
            staging_root=staging_root, artifacts_root=artifacts_root,
        )
    return _export_use(dsn, launcher, artifacts_root, task, result.operation_id,
                       process={"model_calls": 0, "execution": "native-method-episode"},
                       checked=checked, workspace=result.workspace)


def _run_later_in_fresh_process(dsn, run_id, index, genome, values, token_allocation,
                                cpu_allocation, root, staging_root, artifacts_root, logs_root):
    from rsi import episode, investigate, task, verifier
    from settlement.launcher_local import LocalLauncher

    use_task = _summary_task(values, run_id + f"-later-{index}")
    task.publish(dsn, use_task, staging_root=staging_root, artifacts_root=artifacts_root)
    investigation_id = f"p04-later-{run_id}-{index}"
    investigate.create(
        dsn, None, genome, investigation_id=investigation_id, task=use_task,
        token_allocation=token_allocation, cpu_allocation=cpu_allocation,
        max_steps=1, timeout_ms=30_000, token_ceiling=1,
        staging_root=staging_root, artifacts_root=artifacts_root,
        objective="Apply the retained integer-summary/1 method to the supplied public input.",
        method={"name": NAME, "interface": INTERFACE, "value": values},
    )
    log_path = logs_root / (investigation_id + ".log")
    command = [sys.executable, "-m", "rsi.investigate", "resume", "--dsn", dsn,
               "--id", investigation_id, "--root", str(root)]
    env = dict(os.environ)
    for key in tuple(env):
        if (key.startswith(("SETTLEMENT_GATEWAY_", "OPENROUTER_", "OPENAI_", "ANTHROPIC_"))
                or key == "CODEX_API_KEY"):
            env.pop(key, None)
    src = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    timed_out = False
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        pid = process.pid
        try:
            process.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.communicate()
    state = investigate.investigation.read(dsn, investigation_id)
    episode_id = (state or {}).get("last_observation", {}).get("episode")
    if not episode_id:
        raise RuntimeError("fresh method investigation did not record an episode")
    launcher = LocalLauncher(root / "verifiers")
    ep = episode.read_episode(dsn, episode_id, launcher)
    if ep is None:
        raise RuntimeError("fresh method episode could not be read back")
    checked = verifier.read_verdict(dsn, episode_id, use_task.evaluator_version)
    record = _export_use(
        dsn, launcher, artifacts_root, use_task, episode_id,
        process={"pid": pid, "exit_code": process.returncode,
                 "model_calls": 0, "timed_out": timed_out},
        checked=checked, workspace=ep.workspace if ep else None,
    )
    record["task"] = {"digest": use_task.digest, "reference": {
        p: raw.decode("utf-8") for p, raw in use_task.reference.items()},
        "split": use_task.split,
        "package": base64.b64encode(
            _record_artifact(Path(artifacts_root), use_task.digest)).decode("ascii")}
    if timed_out or process.returncode != 0:
        raise RuntimeError("fresh method process did not exit successfully")
    return record


def _allocation_summary(status):
    return {key: status[key] for key in ("id", "domain", "authorized", "reserved", "consumed")}


def _checkpoint(report, bundle, dsn, artifacts_root, route):
    from settlement import store

    captured = report.setdefault("artifact_bytes", {})
    candidates = [report.get("construction", {})]
    for use in report.get("uses", []):
        if isinstance(use, dict):
            candidates.extend((use, use.get("episode", {})))
    for record in candidates:
        if not isinstance(record, dict):
            continue
        for key in ("evidence", "trajectory", "trajectory_digest"):
            digest = record.get(key)
            if isinstance(digest, str) and len(digest) == 64 and digest not in captured:
                path = Path(artifacts_root) / digest
                if path.is_file():
                    captured[digest] = base64.b64encode(_record_artifact(
                        Path(artifacts_root), digest)).decode("ascii")
    report["allocations"] = {
        name: _allocation_summary(store.allocation_status(dsn, name))
        for name in report.get("allocations", {})
    }
    _export_journal(report, dsn, artifacts_root, route)
    _write_json(bundle / "report.json", report)


def _export_use(dsn, launcher, artifacts_root, task, operation_id, *, process,
                checked, workspace=None):
    from rsi import archive, verifier
    from settlement import broker, db

    decision = archive.decision(dsn, "capability-use:" + operation_id)
    if decision is None:
        raise RuntimeError("method episode has no durable capability-use decision")
    identity = decision["data"]
    input_dir, _ = launcher.exec_dirs(operation_id, identity["execution_version"])
    dispatch_request = json.loads(
        (Path(input_dir) / "request.json").read_text(encoding="utf-8"))
    context = dispatch_request.get("context")
    if (not isinstance(context, dict) or set(context) != {"continuation", "task_digest"}
            or context["task_digest"] != task.digest):
        raise RuntimeError("method dispatch request lost its pinned Task identity")
    request = {**dispatch_request, "context": context["continuation"]}
    digest = identity.get("output_digest")
    if identity.get("status") == "completed" and not digest:
        raise RuntimeError("completed use lacks its published result artifact")
    result_artifact = _record_artifact(Path(artifacts_root), digest) if digest else b""
    output_doc = {}
    if result_artifact:
        package = json.loads(result_artifact)
        output_doc = json.loads(bytes.fromhex(package["files"]["result.json"]))
    with db.connect(dsn) as conn:
        row = conn.execute("SELECT trajectory FROM rsi_episodes WHERE operation_id=%s",
                           (operation_id,)).fetchone()
    use = {
        **identity, "decision": identity, "request": request,
        "dispatch_request": dispatch_request,
        "value": output_doc.get("value"), "files": output_doc.get("files", {}),
        "result_artifact": base64.b64encode(result_artifact).decode("ascii"),
        "episode": {"id": operation_id, "task_digest": task.digest,
                    "trajectory": row[0] if row else None,
                    "status": "completed" if identity.get("status") == "completed" else identity.get("status")},
        "fresh_process": process,
    }
    if checked is not None:
        use["verdict"] = {"passed": checked.passed, "status": checked.status,
                           "operation_id": checked.operation_id}
        if workspace is None:
            use["solution_files"] = use["files"]
        else:
            files = verifier.solution_files(task, Path(workspace))
            use["solution_files"] = {name: raw.decode("utf-8") for name, raw in files.items()}
    elif task:
        use["solution_files"] = use["files"]
    operation = broker.read_operation(dsn, operation_id)
    use["operation"] = operation
    return use


def _export_journal(report, dsn, artifacts_root, route):
    """Export durable decisions and operations without route credentials."""
    from settlement import broker, db

    with db.connect(dsn) as conn:
        decisions = conn.execute(
            "SELECT id, kind, actor, subject, data FROM rsi_decisions "
            "WHERE id LIKE 'capability-%' OR id LIKE 'p04-%' ORDER BY id"
        ).fetchall()
    secret, endpoint = route["SETTLEMENT_GATEWAY_KEY"], route["SETTLEMENT_GATEWAY_ENDPOINT"]
    def redact(value):
        if isinstance(value, str):
            return value.replace(secret, "[redacted]").replace(endpoint, "[endpoint-redacted]")
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value
    report["decisions"] = [redact(dict(zip(("id", "kind", "actor", "subject", "data"), row)))
                           for row in decisions]
    operation_ids = {item["data"].get("operation_id") for item in report["decisions"]
                     if isinstance(item.get("data"), dict)}
    operation_ids.add(report.get("construction_operation_id"))
    operation_ids.update(use.get("operation_id") for use in report.get("uses", []))
    with db.connect(dsn) as conn:
        operation_ids.update(row[0] for row in conn.execute(
            "SELECT id FROM operations").fetchall())
    exported = []
    for operation_id in sorted(item for item in operation_ids if item):
        operation = broker.read_operation(dsn, operation_id)
        if operation is None:
            continue
        with db.connect(dsn) as conn:
            receipts = conn.execute(
                "SELECT receipt_identity, content_digest, content, outcome "
                "FROM receipts WHERE operation_id=%s ORDER BY receipt_identity",
                (operation_id,),
            ).fetchall()
        exported.append(redact({"operation": operation,
                                "receipts": [dict(zip(("receipt_identity", "content_digest",
                                                        "content", "outcome"), row))
                                             for row in receipts]}))
    report["operations"] = exported
    safe_report = redact(report)
    report.clear()
    report.update(safe_report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--dsn")
    parser.add_argument("--route-file", type=Path)
    parser.add_argument("--logs-root", type=Path,
                        default=Path(tempfile.gettempdir()) / "agent-society-p04-logs")
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    args = parser.parse_args()
    try:
        if args.freeze:
            manifest = freeze(args.repo, args.bundle)
            result = {"status": "frozen", "commit": manifest["commit"],
                      "manifest": str(args.bundle / "manifest.json")}
        else:
            if not args.dsn or not args.route_file:
                parser.error("--run requires --dsn and --route-file")
            result = run(args.repo, args.bundle, args.dsn, args.route_file,
                         args.logs_root, args.codex)
        print(json.dumps(result, sort_keys=True))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "stopped", "detail": str(exc)}, sort_keys=True))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
