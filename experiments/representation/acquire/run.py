"""Deterministic acquisition/transfer panel runner for Lane D (RPR-03/06/08).

Runs every arm-task pair through existing primitives only: development
episodes carry parent experience refs, capability rows carry component
identities, trial protocols carry assignments and outcomes, and the Lane C
runner executes representation compositions through real broker operations
with the independent checker. Nothing here invents model output; the live
campaign stays an exact-blocker record. Runs are idempotent: completed
pairs (trial outcome plus verified evidence) are skipped, partial broker
work resumes from durable receipts, so killing and rerunning this command
is a genuine fresh-process resume.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from experiments.representation import checkers, graphs, reducers, software
from experiments.representation.acquire import contexts, panel, retention
from experiments.representation.experiment import freeze
from settlement import broker, development, launcher_local, store, trials
from settlement import representation as R
from settlement.common import Command, ResultCode, SettlementError
from settlement import db as _db

REP = ROOT / "experiments" / "representation"
ACQUIRE = REP / "acquire"
EXPERIMENT = REP / "experiment"
FIXTURES = REP / "fixtures"

OUTCOME = {"improved": "success", "no_improvement": "failure",
           "unsupported": "failure", "refused": "failure",
           "budget_exhausted": "timeout", "paused": "infra"}

RETENTION_MODES = ("authored-fixture", "retained")
STAGE_OF_FAMILY = {family: stage for stage, families
                   in retention.STAGE_FAMILIES.items()
                   for family in families}
PROCEDURE_TIMEOUT_MS = 2000
PROCEDURE_WALL_S = 30.0
REFUSED_PROCEDURE = "refused-no-candidate"

PROCEDURE_DRIVER = (
    "import importlib.util\n"
    "import json\n"
    "import sys\n"
    "proc_path, req_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]\n"
    "measure = json.load(open(req_path))[\"measure\"]\n"
    "spec = importlib.util.spec_from_file_location(\"retained_procedure\","
    " proc_path)\n"
    "module = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(module)\n"
    "json.dump({\"method\": module.select(measure)}, open(out_path, \"w\"))\n"
)


def _cmd() -> Command:
    return Command(request_id="rpr-acq-%s" % uuid.uuid4().hex, payload={})


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _comp_id(base: str, tag: str) -> str:
    return base if tag == "main" else "%s-%s" % (base, tag)


def _alloc_id(tag: str) -> str:
    return "rpr-acq-alloc" if tag == "main" else "rpr-acq-alloc-%s" % tag


def _inv_id(tag: str) -> str:
    return "rpr-acq-inv" if tag == "main" else "rpr-acq-inv-%s" % tag


def _att_id(tag: str) -> str:
    return "rpr-acq-att" if tag == "main" else "rpr-acq-att-%s" % tag


def _episode_id(base: str, tag: str) -> str:
    return base if tag == "main" else "%s-%s" % (base, tag)


def _protocol_id(base: str, tag: str) -> str:
    return base if tag == "main" else "%s-%s" % (base, tag)


def _run_id(tag: str, arm: str, task_id: str) -> str:
    return "rprD-%s-%s-%s" % (tag, arm, task_id)


def _ignore_exists(fn):
    try:
        return fn()
    except SettlementError as exc:
        text = str(exc)
        if "already exists" in text or "already recorded" in text \
                or "already applied" in text or "duplicate key" in text:
            return None
        raise
    except Exception as exc:
        if type(exc).__name__ == "UniqueViolation":
            return None
        raise


def ensure_foundation(dsn: str, tag: str) -> dict:
    problems = freeze.verify_committed()
    if problems:
        raise SettlementError("frozen inputs invalid: %s" % problems)
    manifest = json.loads((EXPERIMENT / "manifest.json").read_bytes())
    manifest_sha = (EXPERIMENT / "manifest.sha256").read_text().strip()
    by_component = {e.get("component"): e for e in manifest["files"]
                    if e.get("component")}
    for key, rel in panel.COMPONENTS.items():
        raw = (REP / rel).read_bytes()
        if _digest(raw) != by_component[key]["digest"]:
            raise SettlementError("component %s drifted from manifest" % key)
    alloc, inv, att = _alloc_id(tag), _inv_id(tag), _att_id(tag)
    _ignore_exists(lambda: store.seed_allocation(
        dsn, Command(request_id="rpr-acq-seed-%s-%s" % (tag, uuid.uuid4().hex[:8]),
                     payload={"allocation_id": alloc, "domain": "cpu",
                              "authorized": 100000})))
    _ignore_exists(lambda: store.admit_commitment(
        dsn, Command(request_id="rpr-acq-inv-%s-%s" % (tag, uuid.uuid4().hex[:8]),
                     payload={"investigation_id": inv, "objective": "rpr-acquire"})))
    _ignore_exists(lambda: store.acquire_work(
        dsn, Command(request_id="rpr-acq-att-%s-%s" % (tag, uuid.uuid4().hex[:8]),
                     payload={"attempt_id": att, "investigation_id": inv})))
    return {"manifest": manifest, "manifest_sha": manifest_sha,
            "allocation_id": alloc, "investigation_id": inv, "attempt_id": att}


def _trigger_refs(task_ids: list, lane_b_digest: str, family: str) -> list:
    refs = []
    for task_id in task_ids:
        rel = contexts._fixture_digest(FIXTURES, task_id)
        refs.append({"task_id": task_id, "family": family,
                     "fixture": rel[0], "digest": rel[1],
                     "lane_b_manifest": lane_b_digest})
    return refs


def ensure_episodes(dsn: str, tag: str, lane_b_digest: str) -> None:
    specs = [
        (panel.EPISODE_SOURCE, contexts.SOURCE_TASKS, ["software"],
         [t for t in contexts.SOURCE_TASKS], ["sw-che-00"], []),
        (panel.EPISODE_TRANSFER, contexts.TRANSFER_TASKS, ["graph"],
         [t for t in contexts.TRANSFER_TASKS], ["gr-che-00"], []),
    ]
    inv = _inv_id(tag)
    alloc = _alloc_id(tag)
    for base, tasks, families, dev, check, transfer in specs:
        episode_id = _episode_id(base, tag)
        episode = development.get_episode(dsn, episode_id)
        if episode is None:
            development.observe(
                dsn, _cmd(), episode_id=episode_id, investigation_id=inv,
                trigger_refs=_trigger_refs(tasks, lane_b_digest, families[0]),
                bottleneck="authored witness-preserving reduction experience")
            episode = development.get_episode(dsn, episode_id)
        if episode["state"] == "observed":
            development.propose(
                dsn, _cmd(), episode_id=episode_id,
                predicted_effect="coarse atom search trims distractors",
                competing="domain-aware greedy keeps the edge",
                uncertainty="transfer to odd-cycle witnesses unproven")
            episode = development.get_episode(dsn, episode_id)
        if episode["state"] == "proposed":
            development.admit(
                dsn, _cmd(), episode_id=episode_id,
                reference_version="RPR-01/1:%s" % lane_b_digest,
                access_policy={"families": families}, allocation_id=alloc,
                panel_policy=development.panel_policy_for(
                    dev, check, transfer, families=families,
                    evaluator_version=panel.CHECKER_VERSION))


def _composition_bytes(comp: dict) -> tuple:
    core_name = "atom_core" if comp["core"] == "core" else comp["core"]
    core_raw = (ACQUIRE / ("%s.py" % core_name)).read_bytes()
    adapter_raw = (ACQUIRE / ("%s.py" % comp["adapter"])).read_bytes()
    desc_raw = (REP / comp["description"]).read_bytes()
    return core_raw, adapter_raw, desc_raw


def ensure_compositions(dsn: str, tag: str, staging_root: Path,
                        artifacts_root: Path) -> dict:
    manifest = json.loads((EXPERIMENT / "manifest.json").read_bytes())
    pinned = {c["composition_id"]: c for c in manifest["compositions"]}
    staged = {}
    for comp in freeze.COMPOSITIONS:
        comp_id = _comp_id(comp["composition_id"], tag)
        core_raw, adapter_raw, desc_raw = _composition_bytes(comp)
        expect = pinned[comp["composition_id"]]
        assert _digest(core_raw) == expect["core_digest"], comp_id
        assert _digest(adapter_raw) == expect["adapter_digest"], comp_id
        receipt = R.stage_composition(
            staging_root, core_bytes=core_raw, adapter_bytes=adapter_raw,
            description=desc_raw, dsn=dsn)
        published = R.publish_composition(dsn, _cmd(), artifacts_root,
                                          receipt)
        assert published.code in (ResultCode.APPLIED,
                                  ResultCode.ALREADY_APPLIED), published.detail
        recorded = R.record_composition(
            dsn, _cmd(), artifacts_root, composition_id=comp_id,
            package_digest=receipt["digest"], role=comp["role"],
            protocol_id=_protocol_id(panel.PROTOCOL_C, tag))
        if recorded.code != ResultCode.APPLIED:
            if "already recorded" not in recorded.detail:
                raise SettlementError("composition %s refused: %s" %
                                      (comp_id, recorded.detail))
        checked = R.check_composition(dsn, artifacts_root, comp_id)
        assert checked["core_digest"] == expect["core_digest"], comp_id
        assert checked["adapter_digest"] == expect["adapter_digest"], comp_id
        staged[comp["composition_id"]] = comp_id
    return staged


def ensure_protocols(dsn: str, tag: str, manifest: dict) -> dict:
    core_digest = next(c["core_digest"] for c in manifest["compositions"]
                       if c["composition_id"] == "rpr-C-source-v1")
    selector_sha = _digest(_canon(manifest["selectors"]))
    versions = {_protocol_id(panel.PROTOCOL_B, tag): "arm-B-procedure:%s" % selector_sha[:16],
                _protocol_id(panel.PROTOCOL_C, tag): "core:%s" % core_digest[:16]}
    groups = [{"name": "development", "kind": "development",
               "tasks": panel.MECHANICS_SW + panel.MECHANICS_GR},
              {"name": "check", "kind": "visible-regression",
               "tasks": panel.ACQUIRE_SW + panel.ACQUIRE_GR},
              {"name": "protected-eval", "kind": "protected-eval",
               "tasks": panel.USE[:2]}]
    for protocol_id, candidate in versions.items():
        _ignore_exists(lambda protocol_id=protocol_id, candidate=candidate:
                       trials.freeze_protocol(
                           dsn, _cmd(), protocol_id=protocol_id,
                           candidate_version=candidate,
                           reference_version="arm-A-native:greedy",
                           evaluator_version=panel.CHECKER_VERSION,
                           task_groups=groups, budgets=dict(panel.BUDGETS),
                           metrics=["improvement_u"],
                           stopping={"rule": "fixed-panel"},
                           supported_scope={"family": "representation"}))
    return versions


def _existing_outcome(dsn: str, protocol_id: str, arm: str, task_id: str):
    rows = trials.protocol_results(dsn, protocol_id)
    want = "%s:%s:%s" % (protocol_id, arm, task_id)
    for row in rows:
        if row["id"] == want:
            return row["outcome"], row["id"]
    return None, want


def _assign(dsn: str, protocol_id: str, arm: str, task_id: str, instance: dict):
    trials.assign(dsn, _cmd(), protocol_id, task_id,
                  panel.trial_group(task_id), arm, instance=instance)
    return "%s:%s:%s" % (protocol_id, arm, task_id)


def _package_file(artifacts_root, digest: str, name: str) -> bytes:
    try:
        raw = (Path(artifacts_root) / digest).read_bytes()
    except OSError:
        raise SettlementError("retained artifact %s missing" % digest[:12])
    if _digest(raw) != digest:
        raise SettlementError("retained artifact %s mismatch" % digest[:12])
    try:
        files = json.loads(raw.decode("utf-8"))["files"]
        return bytes.fromhex(files[name])
    except (ValueError, KeyError, TypeError):
        raise SettlementError("retained artifact %s unreadable" % digest[:12])


def ensure_retained_composition(dsn: str, ctx: dict, entry: dict,
                                stage: str) -> dict:
    comp_id = entry["identities"]["composition_id"]
    try:
        checked = R.check_composition(dsn, ctx["artifacts_root"], comp_id)
    except SettlementError:
        checked = None
    if checked is None:
        try:
            raw = (Path(ctx["artifacts_root"])
                   / entry["identities"]["package_digest"]).read_bytes()
        except OSError:
            raise SettlementError(
                "retained composition %s has no package bytes" % comp_id)
        if _digest(raw) != entry["identities"]["package_digest"]:
            raise SettlementError(
                "retained composition %s package mismatch" % comp_id)
        try:
            files = json.loads(raw.decode("utf-8"))["files"]
            core_raw = bytes.fromhex(files["core.py"])
            adapter_raw = bytes.fromhex(files["adapter.py"])
            desc_raw = bytes.fromhex(files["DESCRIPTION.md"])
        except (ValueError, KeyError, TypeError):
            raise SettlementError(
                "retained composition %s package unreadable" % comp_id)
        receipt = R.stage_composition(
            ctx["staging_root"], core_bytes=core_raw,
            adapter_bytes=adapter_raw, description=desc_raw, dsn=dsn)
        published = R.publish_composition(dsn, _cmd(), ctx["artifacts_root"],
                                          receipt)
        if published.code not in (ResultCode.APPLIED,
                                  ResultCode.ALREADY_APPLIED):
            raise SettlementError("retained composition %s not published: %s"
                                  % (comp_id, published.detail))
        recorded = R.record_composition(
            dsn, _cmd(), ctx["artifacts_root"], composition_id=comp_id,
            package_digest=receipt["digest"], role=stage,
            protocol_id="rpr-camp-%s" % ctx["tag"])
        if recorded.code != ResultCode.APPLIED \
                and "already recorded" not in recorded.detail:
            raise SettlementError("retained composition %s refused: %s"
                                  % (comp_id, recorded.detail))
        checked = R.check_composition(dsn, ctx["artifacts_root"], comp_id)
    identities = entry.get("identities") or {}
    if checked["core_digest"] != identities.get("core_digest") \
            or checked["adapter_digest"] != identities.get("adapter_digest") \
            or checked["package_digest"] != identities.get("package_digest"):
        raise SettlementError(
            "retained composition %s binds other bytes" % comp_id)
    return checked


def bind_retention(dsn: str, ctx: dict) -> dict:
    entries = ctx["retention"]["entries"]
    binding: dict = {}
    for key in retention.ENTRY_KEYS:
        arm, stage = key.split("-")
        entry = entries[key]
        identities = entry.get("identities") or {}
        if arm == "A":
            deal = entry["directive"]
            family = retention.STAGE_FAMILIES[stage][0]
            binding[key] = {"method": deal["directive"][family],
                            "source": deal["source"],
                            "reason": entry.get("reason", "")}
        elif arm == "B":
            if entry.get("selected") is None:
                binding[key] = {"bound": False,
                                "reason": entry.get("reason", "")}
            else:
                body = _package_file(ctx["artifacts_root"],
                                     identities["artifact_digest"],
                                     "procedure.py")
                try:
                    text = body.decode("utf-8")
                except UnicodeDecodeError:
                    raise SettlementError(
                        "retained procedure for %s not text" % key)
                checked = retention.validate_procedure(text)
                if checked["status"] != "valid":
                    binding[key] = {
                        "bound": False,
                        "reason": "rejected-procedure: " + checked["reason"]}
                else:
                    binding[key] = {"bound": True,
                                    "procedure_source": body}
        elif entry.get("selected") is None:
            binding[key] = {"bound": False,
                            "reason": entry.get("reason", "")}
        else:
            binding[key] = {"bound": True, "composition":
                            ensure_retained_composition(dsn, ctx, entry,
                                                        stage)}
    ctx["binding"] = binding
    return binding


def _procedure_op_id(run_tag: str, task_id: str) -> str:
    return "rpr:%s:%s:procedure:0000" % (run_tag, task_id)


def _op_receipts(dsn: str, operation_id: str) -> list:
    from psycopg.rows import dict_row

    with _db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT receipt_identity, outcome, content"
                        " FROM receipts WHERE operation_id = %s"
                        " ORDER BY created_at", (operation_id,))
            rows = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return rows


def run_retained_procedure(dsn: str, ctx: dict, *, key: str, task_id: str,
                           measure: float, entry: dict) -> dict:
    body = ctx["binding"][key]["procedure_source"]
    procedure_digest = _digest(body)
    if procedure_digest != entry["identities"]["file_digest"]:
        raise SettlementError("retained procedure for %s changed" % key)
    op_id = _procedure_op_id(ctx["run_tag"], task_id)
    identity = "rpr-procedure:%s" % op_id
    for receipt in _op_receipts(dsn, op_id):
        if receipt.get("receipt_identity") == identity:
            method = (receipt.get("content") or {}).get("method")
            if method not in retention.METHODS:
                raise SettlementError(
                    "retained procedure for %s returned %r" % (key, method))
            return {"method": method, "procedure_digest": procedure_digest,
                    "op_id": op_id, "elapsed_s": 0.0, "reused": True}
    launcher = ctx["launcher"]
    wall = time.time()
    in_dir, out_dir = launcher.exec_dirs(op_id, "")
    ensured = broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.SANDBOX_EXEC,
        payload={"profile": launcher.profile,
                 "argv": [launcher.staged_python(),
                          "%s/driver.py" % in_dir,
                          "%s/procedure.py" % in_dir,
                          "%s/request.json" % in_dir,
                          "%s/response.json" % out_dir],
                 "timeout_ms": PROCEDURE_TIMEOUT_MS,
                 "max_output_bytes": 65536},
        allocation_id=ctx["allocation_id"], attempt_id=ctx["attempt_id"])
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError("retained procedure for %s not admitted: %s"
                              % (key, ensured.detail))
    launcher.stage_input(op_id, "", "procedure.py", body)
    launcher.stage_input(op_id, "", "driver.py", PROCEDURE_DRIVER.encode())
    launcher.stage_input(op_id, "", "request.json",
                         _canon({"measure": measure}))
    broker.dispatch_operation(dsn, op_id,
                              launchers={launcher.profile: launcher})
    try:
        raw_response = launcher.read_output(op_id, "", "response.json")
        method = json.loads(raw_response.decode("utf-8"))["method"]
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise SettlementError("retained procedure for %s gave no method"
                              % key)
    elapsed = round(time.time() - wall, 3)
    if elapsed > PROCEDURE_WALL_S:
        raise SettlementError(
            "retained procedure for %s exceeded its bound" % key)
    if method not in retention.METHODS:
        raise SettlementError("retained procedure for %s returned %r"
                              % (key, method))
    broker.admit_launcher_receipt(
        dsn, op_id, broker.ReceiptProposal(
            receipt_identity=identity,
            content={"kind": "rpr-procedure", "run_tag": ctx["run_tag"],
                     "task_id": task_id, "method": method,
                     "procedure_digest": procedure_digest,
                     "artifact_digest": entry["identities"]["artifact_digest"],
                     "elapsed_s": elapsed},
            outcome="unknown", provenance="representation-01"))
    return {"method": method, "procedure_digest": procedure_digest,
            "op_id": op_id, "elapsed_s": elapsed, "reused": False}


def _native_outcome(native: dict) -> str:
    outcome = "success" if native["u"] > 0 else "failure"
    if native["status"] == "initial-not-preserved":
        outcome = "invalid"
    return outcome


def _refused_record(manifest_sha: str, arm: str, task: dict, task_id: str,
                    family: str, stage: str, ctx: dict, reason: str) -> tuple:
    incumbent, initial = incumbent_of(task)
    record = {"arm": arm, "task_id": task_id, "family": family,
              "stage": stage, "trial_group": panel.trial_group(task_id),
              "manifest_sha256": manifest_sha,
              "checker_version": panel.CHECKER_VERSION,
              "inputs_digest": _inputs_for(task_id, family, ctx["manifest"],
                                           None),
              "composition": {"native": True,
                              "procedure": REFUSED_PROCEDURE,
                              "directive_source": "refused-no-candidate",
                              "response_digest": None,
                              "artifact_digest": None, "reason": reason},
              "initial": {"measure": initial},
              "result": {"disposition": "refused", "reason": reason,
                         "improvement_u": 0.0,
                         "verified": False,
                         "delivered_digest": _digest(_canon(incumbent))},
              "oracle_queries": [], "invocations": [],
              "costs": {"invocations_used": 0, "queries_used": 0,
                        "validation_used": 0, "elapsed_s": 0.0,
                        "model_calls": 0,
                        "model_tokens": {"in": 0, "out": 0}},
              "operator": None,
              "acquired": {"retention_digest": ctx["retention_digest"],
                           "selected": None, "response_digest": None,
                           "artifact_digest": None}}
    return record, "failure"


def _retained_native_pair(dsn: str, ctx: dict, arm: str, task: dict,
                          task_id: str, family: str, stage: str,
                          manifest: dict, manifest_sha: str) -> tuple:
    key = "%s-%s" % (arm, STAGE_OF_FAMILY[family])
    entry = ctx["retention"]["entries"][key]
    identities = entry.get("identities") or {}
    lineage = entry.get("lineage") or {}
    if arm == "B" and not ctx["binding"][key]["bound"]:
        return _refused_record(manifest_sha, arm, task, task_id, family,
                               stage, ctx,
                               ctx["binding"][key].get("reason")
                               or entry.get("reason") or "no-candidate")
    if arm == "A":
        deal = ctx["binding"][key]
        method = deal["method"]
        native = run_native(task, method)
        procedure = None
        extras = {"selector": manifest["selectors"]["arm-A"][family],
                  "directive_source": deal["source"],
                  "response_digest": lineage.get("response_digest"),
                  "artifact_digest": identities.get("artifact_digest"),
                  "reason": deal["reason"]}
        inputs = _inputs_for(task_id, family, manifest, None)
        inputs["directive_artifact"] = identities.get("artifact_digest")
        costs = {"invocations_used": 0, "queries_used": native["queries"],
                 "validation_used": 0, "elapsed_s": native["elapsed_s"],
                 "model_calls": 0, "model_tokens": {"in": 0, "out": 0}}
    else:
        proc = run_retained_procedure(dsn, ctx, key=key, task_id=task_id,
                                      measure=incumbent_of(task)[1],
                                      entry=entry)
        native = run_native(task, proc["method"])
        procedure = {"op_id": proc["op_id"], "method": proc["method"],
                     "procedure_digest": proc["procedure_digest"],
                     "elapsed_s": proc["elapsed_s"],
                     "reused": proc["reused"]}
        extras = {"selector": manifest["selectors"]["arm-B"][family],
                  "directive_source": "acquired",
                  "response_digest": lineage.get("response_digest"),
                  "artifact_digest": identities.get("artifact_digest"),
                  "reason": entry.get("reason", "")}
        inputs = _inputs_for(task_id, family, manifest, None)
        inputs["procedure_artifact"] = identities.get("artifact_digest")
        costs = {"invocations_used": 1, "queries_used": native["queries"],
                 "validation_used": 0,
                 "elapsed_s": round(native["elapsed_s"]
                                    + proc["elapsed_s"], 3),
                 "model_calls": 0, "model_tokens": {"in": 0, "out": 0}}
    record = {"arm": arm, "task_id": task_id, "family": family,
              "stage": stage, "trial_group": panel.trial_group(task_id),
              "manifest_sha256": manifest_sha,
              "checker_version": panel.CHECKER_VERSION,
              "inputs_digest": inputs,
              "composition": {"native": True, "procedure": native["method"],
                              **extras},
              "initial": {"measure": native["initial_measure"]},
              "result": {"disposition": "improved" if native["u"] > 0
                         else "no_improvement",
                         "reason": native["status"],
                         "best_measure": native["verdict"].get("measure"),
                         "improvement_u": native["u"],
                         "verified": native["verdict"].get("verdict")
                         == "preserved",
                         "delivered_digest": native["delivered_digest"]},
              "oracle_queries": native["history"], "invocations": [],
              "costs": costs, "operator": None,
              "native_detail": {"accepted": native["accepted"],
                                "final_verdict": native["verdict"]},
              "acquired": {"retention_digest": ctx["retention_digest"],
                           "selected": entry.get("selected"),
                           "response_digest": lineage.get("response_digest"),
                           "artifact_digest": identities.get("artifact_digest")}}
    if procedure is not None:
        record["procedure"] = procedure
    return record, _native_outcome(native)


def _retained_composition_pair(dsn: str, ctx: dict, task: dict,
                               task_id: str, family: str, stage: str,
                               manifest: dict, manifest_sha: str) -> tuple:
    key = "C-%s" % STAGE_OF_FAMILY[family]
    entry = ctx["retention"]["entries"][key]
    identities = entry.get("identities") or {}
    lineage = entry.get("lineage") or {}
    if not ctx["binding"][key]["bound"]:
        record, outcome = _refused_record(
            manifest_sha, "C", task, task_id, family, stage, ctx,
            entry.get("reason") or "no-candidate")
        return record, outcome, ""
    composed = run_composition(dsn, ctx["launcher"], ctx["artifacts_root"],
                               tag=ctx["run_tag"], task=task,
                               composition_id=identities["composition_id"],
                               manifest=manifest,
                               allocation_id=ctx["allocation_id"],
                               attempt_id=ctx["attempt_id"])
    outcome_fresh = OUTCOME[composed["disposition"]]
    if composed["disposition"] == "improved" and not composed["verified"]:
        outcome_fresh = "failure"
    record = {"arm": "C", "task_id": task_id, "family": family,
              "stage": stage, "trial_group": panel.trial_group(task_id),
              "manifest_sha256": manifest_sha,
              "checker_version": panel.CHECKER_VERSION,
              "inputs_digest": _inputs_for(task_id, family, manifest,
                                           composed),
              "composition": {"native": False,
                              "composition_id": identities["composition_id"],
                              "role": composed["role"],
                              "core_digest": composed["core_digest"],
                              "adapter_digest": composed["adapter_digest"],
                              "package_digest": composed["package_digest"],
                              "checker_id": composed["checker_id"],
                              "response_digest":
                              lineage.get("response_digest"),
                              "lineage": lineage},
              "initial": {"measure": composed["initial_measure"]},
              "result": {"disposition": composed["disposition"],
                         "reason": composed["reason"],
                         "best_measure": composed["best_measure"],
                         "improvement_u": composed["u"],
                         "verified": composed["verified"],
                         "delivered_digest": composed["delivered_digest"]},
              "oracle_queries": composed["queries"],
              "oracle_validations": composed["validations"],
              "invocations": composed["invocations"],
              "costs": composed["costs"],
              "operator": composed["operator"],
              "acquired": {"retention_digest": ctx["retention_digest"],
                           "selected": entry.get("selected"),
                           "response_digest": lineage.get("response_digest"),
                           "package_digest": identities.get("package_digest")}}
    invocation_ref = composed["invocations"][0]["op_id"] \
        if composed["invocations"] else ""
    return record, outcome_fresh, invocation_ref


def _retained_use_record(dsn: str, ctx: dict, task: dict, task_id: str,
                         family: str, incumbent: dict, initial: float,
                         manifest: dict, manifest_sha: str) -> dict:
    retained = ctx["retention"]
    disp = ctx.get("disposition")
    if not isinstance(disp, dict) or not disp:
        raise SettlementError("retained use requires a disposition record")
    stage = STAGE_OF_FAMILY[family]
    a_key, c_key = "A-%s" % stage, "C-%s" % stage
    a_entry = retained["entries"][a_key]
    c_entry = retained["entries"][c_key]
    a_deal = ctx["binding"][a_key]
    a_lineage = a_entry.get("lineage") or {}
    c_bound = ctx["binding"][c_key]["bound"]
    use_tag = "%s-use" % ctx["run_tag"]
    if disp.get("use_authorized") is True and disp.get("use_composition_id"):
        composed = run_composition(
            dsn, ctx["launcher"], ctx["artifacts_root"], tag=use_tag,
            task=task, composition_id=disp["use_composition_id"],
            manifest=manifest, allocation_id=ctx["allocation_id"],
            attempt_id=ctx["attempt_id"])
        inputs = _inputs_for(task_id, family, manifest, composed)
        attempt = {"composition_id": disp["use_composition_id"],
                   "disposition": composed["disposition"],
                   "reason": composed["reason"], "u": composed["u"],
                   "verified": composed["verified"], "trial_only": True,
                   "invocations": composed["invocations"],
                   "queries": composed["queries"],
                   "costs": composed["costs"]}
        selected = {"route": "selected-use",
                    "reason": "disposition-authorized",
                    "delivered_digest": _digest(_canon(composed["delivered"]))}
        fallback = None
    else:
        if c_bound:
            composed = run_composition(
                dsn, ctx["launcher"], ctx["artifacts_root"], tag=use_tag,
                task=task, composition_id=c_entry["identities"]["composition_id"],
                manifest=manifest, allocation_id=ctx["allocation_id"],
                attempt_id=ctx["attempt_id"])
            inputs = _inputs_for(task_id, family, manifest, composed)
            attempt = {"composition_id": c_entry["identities"]["composition_id"],
                       "disposition": composed["disposition"],
                       "reason": composed["reason"], "u": composed["u"],
                       "verified": composed["verified"], "trial_only": True,
                       "invocations": composed["invocations"],
                       "queries": composed["queries"],
                       "costs": composed["costs"]}
        else:
            composed = None
            inputs = _inputs_for(task_id, family, manifest, None)
            attempt = {"composition_id": None, "disposition": "refused",
                       "reason": ctx["binding"][c_key].get("reason")
                       or "no-candidate", "u": 0.0, "verified": False,
                       "trial_only": True, "invocations": [], "queries": [],
                       "costs": {"invocations_used": 0, "queries_used": 0,
                                 "validation_used": 0, "elapsed_s": 0.0,
                                 "model_calls": 0,
                                 "model_tokens": {"in": 0, "out": 0}}}
        if composed is not None and composed["disposition"] == "unsupported":
            selected = {"route": "incumbent",
                        "reason": "unsupported-scope",
                        "delivered_digest": _digest(_canon(incumbent))}
            fallback = None
        else:
            native = run_native(task, a_deal["method"])
            fallback = {"procedure": a_deal["method"], "u": native["u"],
                        "delivered_digest": native["delivered_digest"],
                        "queries": native["queries"],
                        "response_digest": a_lineage.get("response_digest"),
                        "artifact_digest": (a_entry.get("identities") or {}).get("artifact_digest"),
                        "directive_source": a_deal["source"]}
            if c_bound or "out-of-scope" not in task_id:
                selected = {"route": "A-fallback",
                            "reason": "no-release-trial-only",
                            "delivered_digest": native["delivered_digest"]}
            else:
                selected = {"route": "incumbent",
                            "reason": "no-candidate-out-of-scope",
                            "delivered_digest": _digest(_canon(incumbent))}
    return {"task_id": task_id, "family": family, "stage": "subsequent-use",
            "manifest_sha256": manifest_sha,
            "checker_version": panel.CHECKER_VERSION,
            "inputs_digest": inputs,
            "release": "none: representation unreleased",
            "c_attempt": attempt, "fallback": fallback,
            "selected": selected,
            "acquired": {"retention_digest": ctx["retention_digest"],
                         "campaign_tag": retained["tag"],
                         "disposition_digest":
                         ctx.get("disposition_digest"),
                         "selected": c_entry.get("selected")}}


def load_task(task_id: str) -> tuple:
    for sub in ("software/development", "graphs/development", "software/check",
                "graphs/check", "software/evaluation", "graphs/evaluation",
                "controls", "use"):
        path = FIXTURES / sub / ("%s.json" % task_id)
        if path.is_file():
            return json.loads(path.read_bytes()), "fixtures/%s/%s.json" % (sub, task_id)
    raise KeyError(task_id)


def family_of(task: dict) -> str:
    return task.get("family", "")


def incumbent_of(task: dict) -> tuple:
    if family_of(task) == "software":
        incumbent = {"family": "software", "task_id": task["task_id"],
                     "fault": task["fault"], "ops": task["ops"],
                     "witness": task["witness"], "seed": task.get("seed")}
        try:
            initial = software.measure(software.parse_task(task)["ops"])
        except software.SoftwareInvalid:
            initial = len(task["ops"])
        return incumbent, initial
    try:
        parsed = graphs.parse_graph(task)
    except graphs.GraphInvalid:
        parsed = {"vertices": task["vertices"], "edges": task["edges"]}
    incumbent = {"family": "graph", "task_id": task["task_id"],
                 "vertices": parsed["vertices"], "edges": parsed["edges"],
                 "seed": task.get("seed")}
    return incumbent, graphs.measure(parsed)


def check_task(task: dict, candidate: dict) -> dict:
    if family_of(task) == "software":
        return checkers.check_software(task, candidate)
    return checkers.check_graph(task, candidate)


def improvement_u(initial: float, verdict: dict) -> float:
    if verdict.get("verdict") == "preserved" and verdict.get("measure") is not None:
        return round(max(0.0, (initial - verdict["measure"]) / initial), 6)
    return 0.0


def method_for(selectors: dict, arm: str, task: dict, initial: float) -> str:
    if arm == "A":
        return selectors["arm-A"][family_of(task)]["method"]
    bucket = selectors["arm-B"][family_of(task)]
    which = "small" if initial <= bucket["threshold"] else "large"
    return bucket["buckets"][which]["method"]


def run_native(task: dict, method: str) -> dict:
    wall = time.time()
    if family_of(task) == "software":
        oracle = checkers.SoftwareOracle(task, max_queries=16)
        result = reducers.reduce_software(task, oracle, method=method,
                                          max_queries=16)
    else:
        oracle = checkers.GraphOracle(task, max_queries=16)
        result = reducers.reduce_graph(task, oracle, method=method,
                                       max_queries=16)
    elapsed = time.time() - wall
    candidate = result["candidate"]
    verdict = check_task(task, candidate)
    incumbent, initial = incumbent_of(task)
    delivered = candidate if verdict.get("verdict") == "preserved" else incumbent
    return {"method": method, "queries": oracle.queries_used,
            "accepted": result["accepted"], "status": result["status"],
            "history": [{"verdict": h["verdict"], "measure": h["measure"],
                         "reason": h["reason"]} for h in oracle.history],
            "verdict": verdict, "initial_measure": initial,
            "u": improvement_u(initial, verdict),
            "delivered": delivered,
            "delivered_digest": _digest(_canon(delivered)),
            "elapsed_s": round(elapsed, 3)}


def _checker_bytes(family: str, manifest: dict) -> tuple:
    key = "sw_checker" if family == "software" else "gr_checker"
    entry = next(e for e in manifest["files"] if e.get("component") == key)
    raw = (ROOT / entry["path"]).read_bytes()
    assert _digest(raw) == entry["digest"], key
    checker_id = "rpr-%s-checker/1" % ("sw" if family == "software" else "gr")
    return raw, checker_id


def run_composition(dsn: str, launcher, artifacts_root: Path, *, tag: str,
                    task: dict, composition_id: str, manifest: dict,
                    allocation_id: str, attempt_id: str) -> dict:
    wall = time.time()
    family = family_of(task)
    incumbent, initial = incumbent_of(task)
    checker_raw, checker_id = _checker_bytes(family, manifest)
    result = R.run_task(
        dsn, launcher, artifacts_root, run_id=_run_id(tag, "C", task["task_id"]),
        task_id=task["task_id"], composition_id=composition_id,
        source_task=task, domain_spec=dict(panel.DOMAIN_SPECS[family]),
        checker_bytes=checker_raw, checker_id=checker_id,
        initial_incumbent=incumbent, initial_measure=initial,
        allocation_id=allocation_id, attempt_id=attempt_id, max_advances=8)
    elapsed = time.time() - wall
    best = result["best_measure"]
    u = round(max(0.0, (initial - best) / initial), 6) \
        if best is not None else 0.0
    queries = [{"op_id": s["op_id"], "verdict": (s.get("verdict") or {}).get("verdict"),
                "measure": (s.get("verdict") or {}).get("measure"),
                "reason": (s.get("verdict") or {}).get("reason")}
               for s in result["steps"] if s.get("kind") == "rpr-check"]
    validations = [{"op_id": s["op_id"], "verdict": (s.get("verdict") or {}).get("verdict"),
                    "measure": (s.get("verdict") or {}).get("measure"),
                    "reason": (s.get("verdict") or {}).get("reason")}
                   for s in result["steps"] if s.get("kind") == "rpr-validate"]
    invocations = [{"op_id": s["op_id"], "action": s.get("action"),
                    "seq": s.get("seq")} for s in result["steps"]
                   if s.get("kind") == "rpr-step"]
    composition = R.check_composition(dsn, artifacts_root, composition_id)
    return {"composition_id": composition_id, "role": composition["role"],
            "core_digest": composition["core_digest"],
            "adapter_digest": composition["adapter_digest"],
            "package_digest": composition["package_digest"],
            "checker_id": checker_id, "disposition": result["disposition"],
            "reason": result["reason"], "initial_measure": initial,
            "best_measure": best, "u": u, "verified": result["verified"],
            "delivered": result["incumbent"],
            "delivered_digest": _digest(_canon(result["incumbent"])),
            "queries": queries, "validations": validations,
            "invocations": invocations,
            "costs": {"invocations_used": result["invocations_used"],
                      "queries_used": result["queries_used"],
                      "validation_used": result["validation_used"],
                      "elapsed_s": round(result["elapsed_s"], 3),
                      "wall_s": round(elapsed, 3),
                      "model_calls": 0, "model_tokens": {"in": 0, "out": 0}},
            "operator": R.operator_view(dsn, _run_id(tag, "C", task["task_id"]),
                                        task["task_id"])}


def _inputs_for(task_id: str, family: str, manifest: dict, comp: dict | None) -> dict:
    by_task = {e.get("task_id"): e for e in manifest["files"]
               if e.get("task_id")}
    by_comp = {e.get("component"): e for e in manifest["files"]
               if e.get("component")}
    context_key = "source_context" if family == "software" else "transfer_context"
    checker_key = "sw_checker" if family == "software" else "gr_checker"
    inputs = {"context": by_comp[context_key]["digest"],
              "fixture": by_task[task_id]["digest"],
              "checker": by_comp[checker_key]["digest"]}
    if comp is not None:
        inputs.update({"core": comp["core_digest"],
                       "adapter": comp["adapter_digest"],
                       "package": comp["package_digest"]})
    return inputs


def evidence_record(record: dict, evidence_root: Path, sub: str, name: str) -> Path:
    target = evidence_root / sub / ("%s.json" % name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(record, sort_keys=True, indent=2) + "\n")
                       .encode())
    return target


def _receipts_present(dsn: str, op_ids: list) -> bool:
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            for op_id in op_ids:
                cur.execute("SELECT 1 FROM receipts WHERE operation_id = %s"
                            " LIMIT 1", (op_id,))
                if cur.fetchone() is None:
                    conn.commit()
                    return False
            conn.commit()
    return True


def run_benefit_pair(dsn: str, ctx: dict, arm: str, task_id: str) -> dict:
    ctx.setdefault("run_tag", ctx["tag"])
    manifest, manifest_sha = ctx["manifest"], ctx["manifest_sha"]
    task, fixture_rel = load_task(task_id)
    family = family_of(task)
    group = panel.trial_group(task_id)
    if group == "protected-eval":
        stage = "evaluation"
    else:
        stage = "acquisition" if task_id in panel.ACQUIRE_SW + panel.ACQUIRE_GR \
            else "mechanics"
        if family == "graph" and stage == "acquisition":
            stage = "transfer"
    record_path = ctx["evidence_root"] / "arm_task" / ("%s-%s.json" % (arm, task_id))
    protocol_bases = [panel.PROTOCOL_B, panel.PROTOCOL_C] if arm == "A" \
        else [panel.PROTOCOL_B if arm == "B" else panel.PROTOCOL_C]
    trial_arm = "reference" if arm == "A" else "candidate"
    protocol_ids = [_protocol_id(base, ctx["tag"]) for base in protocol_bases]
    existing = [_existing_outcome(dsn, protocol_id, trial_arm, task_id)
                for protocol_id in protocol_ids]
    if all(outcome is not None for outcome, _ in existing) \
            and record_path.is_file():
        record = json.loads(record_path.read_bytes())
        if record.get("manifest_sha256") == manifest_sha and \
                _receipts_present(dsn, [i["op_id"] for i in
                                        record.get("invocations", [])]):
            return {"skipped": True, "outcome": existing[0][0], "record": record}
    outcome = existing[0][0]
    if ctx.get("retention") is not None:
        if arm in ("A", "B"):
            record, outcome_fresh = _retained_native_pair(
                dsn, ctx, arm, task, task_id, family, stage, manifest,
                manifest_sha)
            invocation_ref = ""
        else:
            record, outcome_fresh, invocation_ref = \
                _retained_composition_pair(
                    dsn, ctx, task, task_id, family, stage, manifest,
                    manifest_sha)
    elif arm in ("A", "B"):
        method = method_for(manifest["selectors"], arm, task,
                            incumbent_of(task)[1])
        native = run_native(task, method)
        outcome_fresh = "success" if native["u"] > 0 else "failure"
        if native["status"] == "initial-not-preserved":
            outcome_fresh = "invalid"
        record = {"arm": arm, "task_id": task_id, "family": family,
                  "stage": stage, "trial_group": panel.trial_group(task_id),
                  "manifest_sha256": manifest_sha,
                  "checker_version": panel.CHECKER_VERSION,
                  "inputs_digest": _inputs_for(task_id, family, manifest, None),
                  "composition": {"native": True, "procedure": method,
                                  "selector": manifest["selectors"]["arm-%s" % arm][family]},
                  "initial": {"measure": native["initial_measure"]},
                  "result": {"disposition": "improved" if native["u"] > 0
                             else "no_improvement",
                             "reason": native["status"],
                             "best_measure": native["verdict"].get("measure"),
                             "improvement_u": native["u"],
                             "verified": native["verdict"].get("verdict") == "preserved",
                             "delivered_digest": native["delivered_digest"]},
                  "oracle_queries": native["history"], "invocations": [],
                  "costs": {"invocations_used": 0,
                            "queries_used": native["queries"],
                            "validation_used": 0,
                            "elapsed_s": native["elapsed_s"],
                            "model_calls": 0,
                            "model_tokens": {"in": 0, "out": 0}},
                  "trial": [],
                  "operator": None, "native_detail": {
                      "accepted": native["accepted"],
                      "final_verdict": native["verdict"]}}
        invocation_ref = ""
    else:
        comp_base = "rpr-C-source-v1" if family == "software" else "rpr-C-transfer-v1"
        comp_id = _comp_id(comp_base, ctx["tag"])
        composed = run_composition(dsn, ctx["launcher"], ctx["artifacts_root"],
                                   tag=ctx["run_tag"], task=task,
                                   composition_id=comp_id, manifest=manifest,
                                   allocation_id=ctx["allocation_id"],
                                   attempt_id=ctx["attempt_id"])
        outcome_fresh = OUTCOME[composed["disposition"]]
        if composed["disposition"] == "improved" and not composed["verified"]:
            outcome_fresh = "failure"
        record = {"arm": arm, "task_id": task_id, "family": family,
                  "stage": stage, "trial_group": panel.trial_group(task_id),
                  "manifest_sha256": manifest_sha,
                  "checker_version": panel.CHECKER_VERSION,
                  "inputs_digest": _inputs_for(task_id, family, manifest, composed),
                  "composition": {"native": False,
                                  "composition_id": comp_id,
                                  "role": composed["role"],
                                  "core_digest": composed["core_digest"],
                                  "adapter_digest": composed["adapter_digest"],
                                  "package_digest": composed["package_digest"],
                                  "checker_id": composed["checker_id"]},
                  "initial": {"measure": composed["initial_measure"]},
                  "result": {"disposition": composed["disposition"],
                             "reason": composed["reason"],
                             "best_measure": composed["best_measure"],
                             "improvement_u": composed["u"],
                             "verified": composed["verified"],
                             "delivered_digest": composed["delivered_digest"]},
                  "oracle_queries": composed["queries"],
                  "oracle_validations": composed["validations"],
                  "invocations": composed["invocations"],
                  "costs": composed["costs"],
                  "trial": [],
                  "operator": composed["operator"]}
        invocation_ref = composed["invocations"][0]["op_id"] \
            if composed["invocations"] else ""
    trials_entries = []
    for protocol_id, (prior, assignment_id) in zip(protocol_ids, existing):
        _assign(dsn, protocol_id, trial_arm, task_id,
                {"composition": record["composition"].get(
                    "composition_id",
                    record["composition"].get("procedure")),
                 "run_id": _run_id(ctx["run_tag"], arm, task_id)})
        if prior is None:
            trials.record_result(
                dsn, _cmd(), assignment_id=assignment_id,
                outcome=outcome_fresh, invocation_ref=invocation_ref,
                conditions={"disposition": record["result"]["disposition"],
                            "u": record["result"]["improvement_u"]},
                cost={"invocations": record["costs"]["invocations_used"],
                      "queries": record["costs"]["queries_used"],
                      "elapsed_s": record["costs"]["elapsed_s"]},
                detail={"evidence": "arm_task/%s-%s.json" % (arm, task_id),
                        "manifest_sha256": manifest_sha,
                        "verified": record["result"]["verified"]})
        trials_entries.append({"protocol_id": protocol_id,
                               "assignment_id": assignment_id,
                               "outcome": outcome_fresh,
                               "invocation_ref": invocation_ref})
    record["trial"] = trials_entries
    evidence_record(record, ctx["evidence_root"], "arm_task",
                    "%s-%s" % (arm, task_id))
    if outcome is None:
        outcome = outcome_fresh
    return {"skipped": False, "outcome": outcome, "record": record}


def run_control(dsn: str, ctx: dict, arm: str, task_id: str) -> dict:
    ctx.setdefault("run_tag", ctx["tag"])
    manifest, manifest_sha = ctx["manifest"], ctx["manifest_sha"]
    task, _ = load_task(task_id)
    family = family_of(task)
    incumbent, initial = incumbent_of(task)
    record_path = ctx["evidence_root"] / "controls" / ("%s-%s.json" % (arm, task_id))
    if record_path.is_file():
        record = json.loads(record_path.read_bytes())
        if record.get("manifest_sha256") == manifest_sha and \
                _receipts_present(dsn, [i["op_id"] for i in
                                        record.get("invocations", [])]):
            return {"skipped": True, "record": record}
    if ctx.get("retention") is not None:
        if arm in ("A", "B"):
            record, _ = _retained_native_pair(
                dsn, ctx, arm, task, task_id, family, "control", manifest,
                manifest_sha)
        else:
            record, _, _ = _retained_composition_pair(
                dsn, ctx, task, task_id, family, "control", manifest,
                manifest_sha)
    elif arm in ("A", "B"):
        method = method_for(manifest["selectors"], arm, task, initial)
        native = run_native(task, method)
        record = {"arm": arm, "task_id": task_id, "family": family,
                  "stage": "control", "manifest_sha256": manifest_sha,
                  "checker_version": panel.CHECKER_VERSION,
                  "inputs_digest": _inputs_for(task_id, family, manifest, None),
                  "composition": {"native": True, "procedure": method},
                  "initial": {"measure": initial},
                  "result": {"status": native["status"],
                             "improvement_u": native["u"],
                             "final_verdict": native["verdict"],
                             "delivered_digest": native["delivered_digest"]},
                  "oracle_queries": native["history"], "invocations": [],
                  "costs": {"invocations_used": 0,
                            "queries_used": native["queries"],
                            "validation_used": 0,
                            "elapsed_s": native["elapsed_s"],
                            "model_calls": 0,
                            "model_tokens": {"in": 0, "out": 0}}}
    else:
        comp_base = "rpr-C-source-v1" if family == "software" else "rpr-C-transfer-v1"
        composed = run_composition(
            dsn, ctx["launcher"], ctx["artifacts_root"], tag=ctx["run_tag"],
            task=task, composition_id=_comp_id(comp_base, ctx["tag"]),
            manifest=manifest, allocation_id=ctx["allocation_id"],
            attempt_id=ctx["attempt_id"])
        record = {"arm": arm, "task_id": task_id, "family": family,
                  "stage": "control", "manifest_sha256": manifest_sha,
                  "checker_version": panel.CHECKER_VERSION,
                  "inputs_digest": _inputs_for(task_id, family, manifest, composed),
                  "composition": {"native": False,
                                  "composition_id": _comp_id(comp_base, ctx["tag"]),
                                  "role": composed["role"],
                                  "core_digest": composed["core_digest"],
                                  "adapter_digest": composed["adapter_digest"],
                                  "package_digest": composed["package_digest"],
                                  "checker_id": composed["checker_id"]},
                  "initial": {"measure": initial},
                  "result": {"disposition": composed["disposition"],
                             "reason": composed["reason"],
                             "improvement_u": composed["u"],
                             "verified": composed["verified"],
                             "delivered_digest": composed["delivered_digest"]},
                  "oracle_queries": composed["queries"],
                  "oracle_validations": composed["validations"],
                  "invocations": composed["invocations"],
                  "costs": composed["costs"],
                  "operator": composed["operator"]}
    record["control_pass"] = _control_pass(task, record)
    evidence_record(record, ctx["evidence_root"], "controls",
                    "%s-%s" % (arm, task_id))
    return {"skipped": False, "record": record}


def _control_pass(task: dict, record: dict) -> bool:
    incumbent, _ = incumbent_of(task)
    queries = list(record.get("oracle_queries", []))
    if any((q.get("verdict") if isinstance(q, dict) else None) == "preserved"
           for q in queries):
        return False
    if isinstance(record.get("result", {}).get("final_verdict"), dict) and \
            record["result"]["final_verdict"].get("verdict") == "preserved":
        return False
    return record["result"].get("delivered_digest") == _digest(_canon(incumbent))


def run_attribution(dsn: str, ctx: dict, task_id: str, family: str) -> dict:
    manifest, manifest_sha = ctx["manifest"], ctx["manifest_sha"]
    task, _ = load_task(task_id)
    incumbent, initial = incumbent_of(task)
    record_path = ctx["evidence_root"] / "attribution" / ("%s.json" % task_id)
    if record_path.is_file():
        record = json.loads(record_path.read_bytes())
        if record.get("manifest_sha256") == manifest_sha and \
                _receipts_present(dsn, [i["op_id"] for i in
                                        record.get("invocations", [])]):
            return {"skipped": True, "record": record}
    comp_base = "rpr-CTRL-nullsw-v1" if family == "software" else "rpr-CTRL-nullgr-v1"
    composed = run_composition(
        dsn, ctx["launcher"], ctx["artifacts_root"],
        tag="%s-null-%s" % (ctx["tag"], task_id), task=task,
        composition_id=_comp_id(comp_base, ctx["tag"]),
        manifest=manifest, allocation_id=ctx["allocation_id"],
        attempt_id=ctx["attempt_id"])
    record = {"arm": "CTRL", "task_id": task_id, "family": family,
              "stage": "attribution", "manifest_sha256": manifest_sha,
              "checker_version": panel.CHECKER_VERSION,
              "inputs_digest": _inputs_for(task_id, family, manifest, composed),
              "composition": {"native": False,
                              "composition_id": _comp_id(comp_base, ctx["tag"]),
                              "core_digest": composed["core_digest"],
                              "adapter_digest": composed["adapter_digest"],
                              "package_digest": composed["package_digest"]},
              "initial": {"measure": initial},
              "result": {"disposition": composed["disposition"],
                         "reason": composed["reason"],
                         "improvement_u": composed["u"],
                         "verified": composed["verified"],
                         "delivered_digest": composed["delivered_digest"]},
              "oracle_queries": composed["queries"],
              "invocations": composed["invocations"],
              "costs": composed["costs"]}
    evidence_record(record, ctx["evidence_root"], "attribution", task_id)
    return {"skipped": False, "record": record}


def run_use_task(dsn: str, ctx: dict, task_id: str) -> dict:
    ctx.setdefault("run_tag", ctx["tag"])
    manifest, manifest_sha = ctx["manifest"], ctx["manifest_sha"]
    task, _ = load_task(task_id)
    family = family_of(task)
    incumbent, initial = incumbent_of(task)
    record_path = ctx["evidence_root"] / "use" / ("%s.json" % task_id)
    if record_path.is_file():
        record = json.loads(record_path.read_bytes())
        if record.get("manifest_sha256") == manifest_sha and \
                _receipts_present(dsn, [i["op_id"] for i in
                                        record.get("c_attempt", {})
                                        .get("invocations", [])]):
            return {"skipped": True, "record": record}
    if ctx.get("retention") is not None:
        record = _retained_use_record(dsn, ctx, task, task_id, family,
                                      incumbent, initial, manifest,
                                      manifest_sha)
        evidence_record(record, ctx["evidence_root"], "use", task_id)
        return {"skipped": False, "record": record}
    comp_base = "rpr-C-source-v1" if family == "software" else "rpr-C-transfer-v1"
    checked = R.check_composition(dsn, ctx["artifacts_root"],
                                  _comp_id(comp_base, ctx["tag"]))
    assert checked["ok"]
    composed = run_composition(
        dsn, ctx["launcher"], ctx["artifacts_root"],
        tag="%s-use" % ctx["run_tag"], task=task,
        composition_id=_comp_id(comp_base, ctx["tag"]),
        manifest=manifest, allocation_id=ctx["allocation_id"],
        attempt_id=ctx["attempt_id"])
    attempt = {"composition_id": _comp_id(comp_base, ctx["tag"]),
               "disposition": composed["disposition"],
               "reason": composed["reason"], "u": composed["u"],
               "verified": composed["verified"],
               "trial_only": True,
               "invocations": composed["invocations"],
               "queries": composed["queries"],
               "costs": composed["costs"]}
    if composed["disposition"] == "unsupported":
        selected = {"route": "incumbent", "reason": "unsupported-scope",
                    "delivered_digest": _digest(_canon(incumbent))}
        fallback = None
    else:
        method = method_for(manifest["selectors"], "A", task, initial)
        native = run_native(task, method)
        fallback = {"procedure": method, "u": native["u"],
                    "delivered_digest": native["delivered_digest"],
                    "queries": native["queries"]}
        selected = {"route": "A-fallback", "reason": "no-release-trial-only",
                    "delivered_digest": native["delivered_digest"]}
    record = {"task_id": task_id, "family": family, "stage": "subsequent-use",
              "manifest_sha256": manifest_sha,
              "checker_version": panel.CHECKER_VERSION,
              "inputs_digest": _inputs_for(task_id, family, manifest, composed),
              "release": "none: representation unreleased",
              "c_attempt": attempt, "fallback": fallback, "selected": selected}
    evidence_record(record, ctx["evidence_root"], "use", task_id)
    return {"skipped": False, "record": record}


def _load_evidence(evidence_root: Path, sub: str) -> list:
    out = []
    target = evidence_root / sub
    if not target.is_dir():
        return out
    for path in sorted(target.glob("*.json")):
        if path.name == "index.json":
            continue
        out.append(json.loads(path.read_bytes()))
    return out


def _means(records: list) -> dict:
    grouped: dict = {}
    for record in records:
        key = (record["arm"], record["family"])
        grouped.setdefault(key, []).append(record["result"]["improvement_u"])
    return {"%s-%s" % key: round(sum(v) / len(v), 6)
            for key, v in sorted(grouped.items())}


def _cost_sums(records: list) -> dict:
    sums = {"invocations": 0, "queries": 0, "elapsed_s": 0.0}
    for record in records:
        costs = record.get("costs", {})
        sums["invocations"] += costs.get("invocations_used", 0)
        sums["queries"] += costs.get("queries_used", 0)
        sums["elapsed_s"] += costs.get("elapsed_s", 0.0)
    sums["elapsed_s"] = round(sums["elapsed_s"], 3)
    return sums


def build_index(dsn: str, ctx: dict, stats: dict) -> dict:
    manifest, manifest_sha = ctx["manifest"], ctx["manifest_sha"]
    arm_task = _load_evidence(ctx["evidence_root"], "arm_task")
    controls = _load_evidence(ctx["evidence_root"], "controls")
    attribution = _load_evidence(ctx["evidence_root"], "attribution")
    use = _load_evidence(ctx["evidence_root"], "use")
    verdicts = {}
    for base in (panel.PROTOCOL_B, panel.PROTOCOL_C):
        protocol_id = _protocol_id(base, ctx["tag"])
        try:
            verdicts[base] = trials.verdict(dsn, protocol_id)
        except SettlementError as exc:
            verdicts[base] = {"error": str(exc)}
    benefit = [r for r in arm_task if r.get("stage") in
               ("mechanics", "acquisition", "transfer", "evaluation")]
    by_arm: dict = {}
    for record in benefit:
        by_arm.setdefault(record["arm"], []).append(record)
    horizons = {}
    transcript_queries = 0
    for name in ("source_context.json", "transfer_context.json"):
        doc = json.loads((ACQUIRE / name).read_bytes())
        for runs in doc["transcripts"].values():
            transcript_queries += runs["ddmin"]["queries"] + runs["greedy"]["queries"]
    for arm, records in by_arm.items():
        deploy = {"queries": transcript_queries, "invocations": 0,
                  "elapsed_s": 0.0}
        panel_cost = _cost_sums(records)
        horizons["arm-%s" % arm] = {
            "deployment": deploy, "panel": panel_cost,
            "hypothetical": {
                str(h): {"queries": deploy["queries"] + h * panel_cost["queries"],
                         "invocations": deploy["invocations"] + h * panel_cost["invocations"],
                         "elapsed_s": round(deploy["elapsed_s"] + h * panel_cost["elapsed_s"], 3)}
                for h in (1, 10, 100)}}
    ops: set = set()
    for records in (arm_task, controls, attribution, use):
        for record in records:
            for key in ("invocations", "oracle_queries", "oracle_validations"):
                for entry in record.get(key, []) or []:
                    if isinstance(entry, dict) and entry.get("op_id"):
                        ops.add(entry["op_id"])
            attempt = record.get("c_attempt") or {}
            for entry in attempt.get("invocations", []) or []:
                if entry.get("op_id"):
                    ops.add(entry["op_id"])
    comps = {c["composition_id"]: c for c in manifest["compositions"]}
    core_equal = (comps["rpr-C-source-v1"]["core_digest"]
                  == comps["rpr-C-transfer-v1"]["core_digest"])
    index = {"panel_version": panel.PANEL_VERSION,
             "checker_version": panel.CHECKER_VERSION,
             "manifest_sha256": manifest_sha, "tag": ctx["tag"],
             "arm_task_records": len(arm_task),
             "control_records": len(controls),
             "attribution_records": len(attribution),
             "use_records": len(use),
             "trial_verdicts": verdicts,
             "means": _means(benefit),
             "costs_by_arm": {arm: _cost_sums(records)
                              for arm, records in sorted(by_arm.items())},
             "horizons": horizons,
             "physical_operation_union": len(ops),
             "unchanged_core": {"source": comps["rpr-C-source-v1"]["core_digest"],
                                "transfer": comps["rpr-C-transfer-v1"]["core_digest"],
                                "equal": core_equal},
             "controls_pass": {r["task_id"] + ":" + r["arm"]: r["control_pass"]
                               for r in controls},
             "use_selected": {r["task_id"]: r["selected"]["route"] for r in use},
             "release": "none",
             "live": "blocked: see live_blocker.json",
             "pairs": stats}
    evidence_record(index, ctx["evidence_root"], ".", "index")
    return index


def run_panel(dsn: str, *, tag: str, artifacts_root: Path, staging_root: Path,
              runs_root: Path, evidence_root: Path,
              mode: str = "authored-fixture", retention_path=None) -> dict:
    if mode not in RETENTION_MODES:
        raise SettlementError("unknown panel mode %r" % (mode,))
    if mode == "authored-fixture" and retention_path is not None:
        raise SettlementError("retention path without retained mode")
    if mode == "retained" and not retention_path:
        raise SettlementError("retained mode requires a retention path")
    for path in (artifacts_root, staging_root, runs_root, evidence_root):
        path.mkdir(parents=True, exist_ok=True)
    wall = time.time()
    for name, builder in (("source_context.json", contexts.build_source_context),
                          ("transfer_context.json", contexts.build_transfer_context)):
        built = (json.dumps(builder(FIXTURES), sort_keys=True, indent=2) + "\n").encode()
        committed = (ACQUIRE / name).read_bytes()
        assert _digest(built) == _digest(committed), name
    base = ensure_foundation(dsn, tag)
    manifest = base["manifest"]
    lane_b_digest = manifest["lane_b"]["manifest_digest"]
    ensure_episodes(dsn, tag, lane_b_digest)
    ensure_compositions(dsn, tag, staging_root, artifacts_root)
    ensure_protocols(dsn, tag, manifest)
    launcher = launcher_local.LocalLauncher(str(runs_root))
    ctx = {**base, "tag": tag, "run_tag": tag, "launcher": launcher,
           "artifacts_root": artifacts_root, "staging_root": staging_root,
           "evidence_root": evidence_root, "retention": None}
    if mode == "retained":
        loaded = retention.load_retention(str(retention_path), dsn,
                                          artifacts_root)
        retention_digest = _digest(Path(retention_path).read_bytes())
        ctx.update(retention=loaded, retention_digest=retention_digest,
                   retention_path=str(retention_path),
                   run_tag="%s-ret" % tag)
        bind_retention(dsn, ctx)
    stats: dict = {"ran": 0, "skipped": 0}
    for task_id in panel.BENEFIT_SW + panel.BENEFIT_GR:
        for arm in panel.ARMS:
            result = run_benefit_pair(dsn, ctx, arm, task_id)
            stats["ran" if not result["skipped"] else "skipped"] += 1
    for task_id in panel.CONTROLS:
        for arm in panel.ARMS:
            result = run_control(dsn, ctx, arm, task_id)
            stats["ran" if not result["skipped"] else "skipped"] += 1
    for task_id, family in panel.ATTRIBUTION:
        result = run_attribution(dsn, ctx, task_id, family)
        stats["ran" if not result["skipped"] else "skipped"] += 1
    if ctx["retention"] is None:
        for task_id in panel.USE:
            result = run_use_task(dsn, ctx, task_id)
            stats["ran" if not result["skipped"] else "skipped"] += 1
    index = build_index(dsn, ctx, stats)
    index["wall_s"] = round(time.time() - wall, 3)
    evidence_record(index, evidence_root, ".", "index")
    return index


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="Lane D acquisition panel")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--tag", default="main")
    parser.add_argument("--artifacts-root", default="var/rpr-acq-artifacts")
    parser.add_argument("--staging-root", default="var/rpr-acq-staging")
    parser.add_argument("--runs-root", default="var/rpr-acq-runs")
    parser.add_argument("--evidence-root",
                        default=str(REP / "evidence"))
    parser.add_argument("--mode", default="authored-fixture")
    parser.add_argument("--retention-path", default="")
    args = parser.parse_args(argv)
    import os
    dsn = args.dsn or os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        print("no DSN: pass --dsn or set SETTLEMENT_TEST_DSN")
        return 2
    index = run_panel(dsn, tag=args.tag,
                      artifacts_root=Path(args.artifacts_root),
                      staging_root=Path(args.staging_root),
                      runs_root=Path(args.runs_root),
                      evidence_root=Path(args.evidence_root),
                      mode=args.mode,
                      retention_path=args.retention_path or None)
    print(json.dumps({"tag": index["tag"], "pairs": index["pairs"],
                      "means": index["means"],
                      "trial_verdicts": index["trial_verdicts"],
                      "unchanged_core": index["unchanged_core"]["equal"],
                      "release": index["release"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
