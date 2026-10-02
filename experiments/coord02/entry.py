"""Lane E full entry: four-arm shared execution path (EC02 design 8-13).

One entry module, one shared admitted path for S/A/F/L. Treatment
selection is one decision seam (arm_decision); every arm flows through
admit-then-construct-then-submit-then-join in the controller. Live
panels refuse without the grant (preflight); doubled runs on the fake
gateway prove the harness end to end on development tasks only.

Fixture route: constructor_label "fixture" with the solved child
factory exists ONLY for labeled mechanism tests. Live-capable arms
never read protected reference overlays; every live-capable arm
continues with those loaders poisoned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from settlement.gateway import FakeGatewayAdapter, GatewayError
from settlement.launcher_local import LocalLauncher

from . import checker
from . import freeze as freeze_mod
from . import oracle
from . import preflight
from . import schemas_evidence as SE
from .controller import EpisodeConfig, run_episode, seed_episode
from .experience import (
    _dev_bindings,
    _dev_interface_contract,
    _dev_join_rules,
    _dev_source_interfaces,
    _requires_for,
    snapshot_files,
)

ENTRY_VERSION = "coord02-entry/2"
DOUBLED_LABEL = "DOUBLED"
FIXTURE_LABEL = "FIXTURE"
ARMS = ("S", "A", "F", "L")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def plan_children(task_id: str, shape: str) -> list:
    workers = list(oracle.worker_files(task_id))
    if shape == "decompose":
        half = max(1, len(workers) // 2)
        groups = [sorted(workers[:half]), sorted(workers[half:])]
        return [
            {"node_id": "w%d" % (i + 1),
             "obligation": "repair owned partition",
             "owned_paths": group,
             "output_contract": {"entry": "partition",
                                 "checks": ["public"]},
             "input_bindings": {"base_%d" % j: p
                                for j, p in enumerate(group)}}
            for i, group in enumerate(groups) if group]
    return [{"node_id": "w1", "obligation": "repair whole tree",
             "owned_paths": workers,
             "output_contract": {"entry": "whole-tree",
                                 "checks": ["public"]},
             "input_bindings": {"base_%d" % j: p
                                for j, p in enumerate(workers)}}]


_POLICY_PREAMBLE = "\n".join([
    "import json",
    "import sys",
    "if len(sys.argv) == 2 and sys.argv[1] == '--selftest':",
    "    raise SystemExit(0)",
    "req = json.load(open(sys.argv[1]))",
    "phase = req.get('phase', '')",
    "state = req.get('state', {}) or {}",
    "task = req.get('task', {}) or {}",
    "obs = task.get('observations', [])",
    "snap = (task.get('task_snapshot', {}) or {})",
    "paths = sorted(p for p in snap if isinstance(p, str)",
    "               and p.startswith('src/'))",
    "ARM = %r",
    "PKG = %r",
    "CHILDREN = %r",
    "SRC = %r",
    "def _single():",
    "    return {'action': 'plan', 'shape': 'single',",
    "            'children': CHILDREN}",
])

_POLICY_SINGLE = "\n".join([
    "if phase == 'pre-plan':",
    "    proposal = {'action': 'probe', 'invocations': [",
    "        {'interface': 'observe-broken', 'input': {'path': ''}}]}",
    "elif phase == 'post-probe':",
    "    proposal = _single()",
    "elif phase in ('post-fail-join', 'post-fail-probe'):",
    "    proposal = {'action': 'rework', 'rework': ['w1']}",
    "else:",
    "    proposal = {'action': 'stop', 'reason': 'single pass done'}",
])

_POLICY_F_CONDITIONAL = "\n".join([
    "deps = task.get('dependency_versions', {}) or {}",
    "stale = [k for k, v in deps.items() if v in ('', None)]",
    "coupled = [o for o in obs",
    "           if isinstance(o, dict) and o.get('interface')",
    "           and o.get('error') is None]",
    "probed = [o for o in obs if isinstance(o, dict)]",
    "if phase == 'pre-plan':",
    "    proposal = {'action': 'probe', 'invocations': [",
    "        {'interface': 'observe-broken', 'input': {'path': ''}}]}",
    "elif phase == 'post-probe':",
    "    if len(paths) > 1 and not stale and (coupled or not probed):",
    "        half = max(1, len(paths) // 2)",
    "        groups = [sorted(paths[:half]), sorted(paths[half:])]",
    "        proposal = {'action': 'plan', 'shape': 'decompose',",
    "                    'children': [",
    "                        {'node_id': 'w%d' % (i + 1),",
    "                         'obligation': 'repair owned partition',",
    "                         'owned_paths': group,",
    "                         'output_contract': {'entry': 'partition',",
    "                                             'checks': ['public']},",
    "                         'input_bindings': {'base_%d' % j: p",
    "                                            for j, p in enumerate(group)}}",
    "                        for i, group in enumerate(groups) if group]}",
    "    else:",
    "        proposal = {'action': 'plan', 'shape': 'single',",
    "                    'children': CHILDREN}",
    "elif phase in ('post-fail-join', 'post-fail-probe'):",
    "    proposal = {'action': 'rework', 'rework': ['w1']}",
    "else:",
    "    proposal = {'action': 'stop', 'reason': 'F single pass'}",
])

_POLICY_A_MODEL = "\n".join([
    "model = state.get('model_proposal')",
    "if phase == 'pre-plan':",
    "    proposal = {'action': 'probe', 'invocations': [",
    "        {'interface': 'observe-broken', 'input': {'path': ''}}]}",
    "elif phase == 'post-probe':",
    "    if isinstance(model, dict) and model.get('action') == 'plan':",
    "        proposal = model",
    "    else:",
    "        proposal = _single()",
    "elif phase in ('post-fail-join', 'post-fail-probe'):",
    "    rework = None",
    "    if isinstance(model, dict) and model.get('action') == 'rework':",
    "        rework = model",
    "    proposal = rework or {'action': 'rework', 'rework': ['w1']}",
    "else:",
    "    proposal = {'action': 'stop', 'reason': 'A pass done'}",
])

_POLICY_EPILOGUE = "\n".join([
    "resp = {'profile': req['profile'],",
    "        'profile_version': req['profile_version'],",
    "        'decision_id': req['decision_id'],",
    "        'package_digest': req['package_digest'],",
    "        'source_digest': req['source_digest'],",
    "        'plan_revision': req['plan_revision'],",
    "        'phase': req['phase'], 'proposal': proposal,",
    "        'state': dict({'arm': ARM}, **_SEED_STATE)}",
    "json.dump(resp, open(sys.argv[2], 'w'))",
    ""])


def arm_policy_entry(arm: str, *, task_id: str = "",
                     package_entry: bytes | None = None,
                     package_digest: str = "",
                     model_proposal: dict | None = None) -> bytes:
    if arm == "L":
        if not package_entry:
            raise ValueError("arm L needs the acquired package entry bytes")
        return bytes(package_entry)
    if arm not in ("S", "A", "F"):
        raise ValueError("unknown arm %r" % (arm,))
    if arm == "F":
        body = _POLICY_F_CONDITIONAL
    elif arm == "A":
        body = _POLICY_A_MODEL + "\n" + "\n".join([
            "if proposal.get('action') == 'plan':",
            "    proposal = dict(proposal)",
            "    proposal['children'] = [",
            "        dict(c, obligation='A interpreted: ' + c.get(",
            "             'obligation', ''))",
            "        for c in proposal.get('children', [])]",
        ])
    else:
        body = _POLICY_SINGLE
    text = (_POLICY_PREAMBLE % (arm, package_digest or "",
                                plan_children(task_id, "single"),
                                selected_source_text(task_id))) \
        + "\n_SEED_STATE = %r\n" % (
            ({"model_proposal": dict(model_proposal)}
             if arm == "A" and isinstance(model_proposal, dict) else {}),) \
        + "\n" + body + "\n" + _POLICY_EPILOGUE
    return text.encode("utf-8")


def selected_source_text(task_id: str) -> str:
    snap = snapshot_files(task_id)
    return json.dumps({k: snap[k] for k in sorted(snap)},
                      sort_keys=True)


def refuse_gateway_error(status: Any, *, check: str) -> Any:
    if isinstance(status, GatewayError):
        raise ConnectionError("gateway %s failed: %s" % (
            check, status.message))
    return status


_DOUBLE_MODEL_HINTS = ("doubl", "recording", "simulat", "fake")


def _is_live_gateway(gateway: Any | None, model: str = "") -> bool:
    if gateway is None or isinstance(gateway, FakeGatewayAdapter):
        return False
    if str(getattr(gateway, "label", "") or ""):
        return False
    if isinstance(model, str) and model \
            and any(h in model.lower() for h in _DOUBLE_MODEL_HINTS):
        return False
    return True


def _grant_version(dsn: str) -> int | None:
    from settlement import store as _store
    try:
        return int(_store.get_control(dsn)["authority_version"])
    except Exception:
        return None


def _ownership_of(dsn: str, attempt_id: str | None) -> int | None:
    if not attempt_id:
        return None
    from settlement import db as _db
    try:
        with _db.connect(dsn) as _conn:
            with _conn.cursor() as _cur:
                _cur.execute("SELECT ownership_generation FROM attempts"
                             " WHERE id = %s", (attempt_id,))
                _row = _cur.fetchone()
                _conn.commit()
        if _row is None:
            return None
        return int(_row[0])
    except Exception:
        return None


def _require_live_spend(gateway: Any | None, model: str = "") -> None:
    if _is_live_gateway(gateway, model):
        preflight.require_live(panels=(), construction_calls=None)


def _interpret_with_model(*, gateway: Any, model: str, prompt: str,
                          operation_id: str, dsn: str,
                          allocation_id: str) -> dict:
    from settlement import broker
    from settlement.common import ResultCode
    from .experience import live_reasoning_effort
    if _settled_model_text(dsn, operation_id) is None:
        _require_live_spend(gateway, model)
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": model,
                 "messages": [{"role": "user", "content": prompt}],
                 "max_output_tokens": 16384, "deadline_ms": 300_000,
                 "reasoning_effort": live_reasoning_effort()},
        allocation_id=allocation_id)
    if ensured.code not in (ResultCode.APPLIED,
                            ResultCode.ALREADY_APPLIED):
        raise ValueError("A decision call not admitted: %s" % ensured.detail)
    broker.dispatch_operation(dsn, operation_id, launchers={},
                              gateway=gateway,
                              grant_version=_grant_version(dsn))
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s"
                        " AND receipt_identity = %s",
                        (operation_id, "gw:%s" % operation_id))
            row = cur.fetchone()
            conn.commit()
    content = dict((row or {}).get("content") or {})
    text = content.get("text", "")
    usage = dict(content.get("usage") or {})
    try:
        proposal = json.loads(text) if text.strip() else None
    except ValueError:
        proposal = None
    if not isinstance(proposal, dict) or "action" not in proposal:
        proposal = {"action": "unsupported",
                    "reason": "a-decision produced no parseable proposal"}
    return {"proposal": proposal, "usage": usage, "text": text}


def arm_decision(arm: str, *, task_id: str, package_entry: bytes | None,
                 package_digest: str, package_text: str,
                 gateway: Any, model: str, dsn: str, run_id: str,
                 allocation_id: str) -> dict:
    if arm not in ARMS:
        raise ValueError("unknown arm %r" % (arm,))
    if arm == "L":
        if package_entry is None:
            return {"kind": "none",
                    "reason": "no acquired package selected",
                    "fallback": "S"}
        return {"kind": "retained",
                "entry": bytes(package_entry),
                "digest": _sha(bytes(package_entry)),
                "provenance": "retained-acquired-bytes"}
    if arm == "S":
        return {"kind": "policy",
                "entry": arm_policy_entry(arm, task_id=task_id,
                                          package_digest=package_digest),
                "provenance": "single-owner-policy"}
    if arm == "F":
        return {"kind": "policy",
                "entry": arm_policy_entry(arm, task_id=task_id,
                                          package_digest=package_digest),
                "provenance": "frozen-conditional-policy"}
    prompt = ("Choose the next coordination proposal for task %s. "
              "Selected source and public description:\n%s\n"
              "Reply with ONLY a JSON proposal object "
              "({\"action\": ...})." % (
                  task_id, json.dumps({
                      "source": package_entry.decode("utf-8") if package_entry is not None else None,
                      "description": package_text,
                      "task": oracle.build_solver_payload(task_id)}, sort_keys=True)))
    decided = _interpret_with_model(
        gateway=gateway, model=model, prompt=prompt,
        operation_id="coord:%s:%s:a-decision" % (run_id, task_id),
        dsn=dsn, allocation_id=allocation_id)
    proposal = dict(decided["proposal"])
    if proposal.get("action") == "plan" and not proposal.get("children"):
        proposal["children"] = plan_children(task_id, "single")
    if proposal.get("action") == "stop":
        return {"kind": "stop",
                "reason": proposal.get("reason", "model stop"),
                "usage": decided["usage"],
                "provenance": "model-interpreted-decision"}
    if proposal.get("action") == "unsupported":
        return {"kind": "unsupported",
                "reason": proposal.get("reason", "model unsupported"),
                "usage": decided["usage"],
                "provenance": "model-interpreted-decision"}
    return {"kind": "interpreted", "proposal": proposal,
            "usage": decided["usage"],
            "provenance": "model-interpreted-decision"}


def _settled_model_text(dsn: str, operation_id: str) -> str | None:
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT content FROM receipts WHERE operation_id = %s"
                        " AND receipt_identity = %s AND outcome = 'success'",
                        (operation_id, "gw:%s" % operation_id))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        return None
    return str(dict(row.get("content") or {}).get("text", ""))


def dispatch_admitted_child(dsn: str, *, gateway: Any, model: str,
                               task_id: str, node: str, child: dict,
                               rendered: dict, allocation_id: str,
                               operation_id: str,
                               attempt_id: str | None = None,
                               ownership_generation: int | None = None,
                               grant_version: int | None = None) -> dict | None:
    from settlement import broker
    from settlement.common import ResultCode
    from . import packet as _packet
    from .experience import live_reasoning_effort
    settled = _settled_model_text(dsn, operation_id)
    if settled is None:
        _require_live_spend(gateway, model)
        prompt = _packet.render_child_prompt(task_id, node, rendered)
        ensured = broker.ensure_operation(
            dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
            payload={"model": model,
                     "messages": [{"role": "user", "content": prompt}],
                     "max_output_tokens": 8192, "deadline_ms": 300_000,
                     "reasoning_effort": live_reasoning_effort()},
            allocation_id=allocation_id, attempt_id=attempt_id)
        if ensured.code not in (ResultCode.APPLIED,
                                ResultCode.ALREADY_APPLIED):
            return None
        if ownership_generation is None:
            ownership_generation = _ownership_of(dsn, attempt_id)
        if grant_version is None:
            grant_version = _grant_version(dsn)
        broker.dispatch_operation(dsn, operation_id, launchers={},
                                  gateway=gateway,
                                  ownership_generation=ownership_generation,
                                  grant_version=grant_version)
        settled = _settled_model_text(dsn, operation_id)
        if settled is None:
            return None
    text = settled
    files, _ = _packet.parse_child_response(child, text)
    return files


def run_child_factory(dsn: str, *, task_id: str, gateway: Any,
                      model: str, allocation_id: str) -> Callable:
    def _build(node: str, child: dict, rendered: dict,
               operation_id: str, attempt_id: str | None = None,
               ownership_generation: int | None = None,
               grant_version: int | None = None,
               ) -> dict | None:
        return dispatch_admitted_child(
            dsn, gateway=gateway, model=model, task_id=task_id,
            node=node, child=child, rendered=rendered,
            allocation_id=allocation_id, operation_id=operation_id,
            attempt_id=attempt_id,
            ownership_generation=ownership_generation,
            grant_version=grant_version)
    return _build


def solved_child_factory(task_id: str) -> Callable:
    def _build(node: str, child: dict, rendered: dict,
               operation_id: str | None = None,
               attempt_id: str | None = None) -> dict | None:
        return None

    return _build


@dataclass
class CellResult:
    record: dict
    outcome: dict


def check_ceilings(costs: dict, ceilings: dict | None = None) -> list:
    ceilings = ceilings or dict(freeze_mod.CEILINGS)
    nested = costs.get("model_tokens", {})
    resources = {
        "model_calls": [costs.get("model_calls", 0)],
        "input_tokens": [costs.get("model_tokens_in", 0)],
        "output_tokens": [costs.get("model_tokens_out", 0)],
        "tool_invocations": [costs.get("tool_invocations", 0)],
        "sandbox_ops": [costs.get("sandbox_ops", 0)]}
    if isinstance(nested, dict):
        resources["input_tokens"].append(nested.get("in", 0))
        resources["output_tokens"].append(nested.get("out", 0))
    return ["ceiling-breach-%s" % resource
            for resource, values in resources.items()
            if any(value != SE.UNKNOWN and value > ceilings[resource]
                   for value in values)]


def _protected_of(outcome: dict) -> dict:
    if outcome.get("status") != "success":
        return {"passed": 0, "failed": 1, "total": 1}
    return {"passed": 1, "failed": 0, "total": 1}


def _admit_floor() -> dict:
    return {"model_tokens_in": 0, "model_tokens_out": 0, "model_calls": 0,
            "tool_invocations": 0, "sandbox_ops": 1, "policy_exec_ops": 1,
            "protected_check_ops": 0, "cpu_seconds": 0, "wall_seconds": 0,
            "elapsed_seconds": 0, "abandoned_ops": 0}


def _cell_costs(dsn: str, cell_ops: dict, outcome: dict) -> tuple:
    from settlement import broker as _broker
    model_ops = sorted(
        op_id for op_id, info in cell_ops.items()
        if info.get("effect") == _broker.MODEL_INFERENCE)
    unmeasured: list = []
    measured = {"in": 0, "out": 0, "calls": 0}
    for op_id in model_ops:
        try:
            usage = SE.costs_for_operations(dsn, [op_id])
        except SE.TrialError:
            unmeasured.append(op_id)
        else:
            for key in measured:
                measured[key] += usage[key]
    if unmeasured:
        measured = dict.fromkeys(measured, SE.UNKNOWN)
    steps = int(outcome.get("steps", 0))
    probes = int(outcome.get("probe_calls", 0))
    sandbox = sum(1 for info in cell_ops.values()
                  if info.get("effect") == _broker.SANDBOX_EXEC)
    costs = {"model_tokens_in": measured["in"],
             "model_tokens_out": measured["out"],
             "model_calls": measured["calls"],
             "tool_invocations": probes, "sandbox_ops": sandbox,
             "policy_exec_ops": steps,
             "protected_check_ops": 1 if sandbox else 0,
             "cpu_seconds": None, "wall_seconds": None,
             "elapsed_seconds": None, "abandoned_ops": 0}
    return costs, unmeasured


def stage_assembled_tree(task_id: str, tree: dict, dest: Any) -> Any:
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    src = dest / "src"
    src.mkdir(parents=True)
    for rel, body in tree.items():
        target = dest / rel if "/" in rel else src / Path(rel).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    for name in ("spec.md", "spec.json", "public.json", "convention.json"):
        if not (dest / name).is_file():
            ref = oracle.TASKS / task_id / name
            if ref.is_file():
                (dest / name).write_text(ref.read_text())
    return src


def stage_record(root: Any, trial: dict, tree: dict | None) -> dict:
    protected = {"passed": 0, "failed": 1, "total": 1}
    failures: list = [{"reason": "candidate tree not restaged"}]
    solved, digest = False, ""
    if tree is not None:
        with tempfile.TemporaryDirectory(prefix="coord02-cand-") as tmp:
            src = stage_assembled_tree(trial["task_id"], tree,
                                       Path(tmp) / "tree")
            graded = oracle.evaluate_tree(
                src, oracle.protected_cases(trial["task_id"]))
            digest = checker.candidate_digest_of(Path(tmp) / "tree")
            dest = Path(root) / "candidates" / digest
            if dest.is_dir():
                shutil.rmtree(dest)
            shutil.copytree(Path(tmp) / "tree", dest)
        protected = {"passed": int(graded["passed"]),
                     "failed": int(graded["failed"]),
                     "total": int(graded["total"])}
        failures = list(graded["failures"])
        solved = graded["failed"] == 0
    elif not trial["solved"]:
        protected, failures = dict(trial["protected"]), list(trial["failures"])
    return {
        "freeze_id": trial["freeze_id"], "panel": trial["panel"],
        "task_id": trial["task_id"], "repeat": trial["repeat"],
        "arm": trial["arm"],
        "executed_treatment": trial.get("executed_treatment",
                                        trial["arm"]),
        "fallback_reason": trial.get("fallback_reason"),
        "procedure_digest": trial["package_digest"],
        "input_digest": oracle.task_input_digest(trial["task_id"]),
        "outcome": "success" if solved else "failure",
        "protected": protected,
        "failures": failures,
        "costs": SE.to_checker_costs(trial),
        "receipts": list(trial["receipts"]),
        "candidate_digest": digest,
        "frozen_digest": digest if solved else "",
    }


def run_cell(dsn: str, *, freeze: dict, task_id: str, panel: str,
             repeat: int, arm: str, launcher_factory: Callable,
             package_entry: bytes | None = None,
             package_digest: str = "none",
             package_text: str = "",
             source_sha: str = "entry-base",
             config_digest: str = "entry-base",
             gateway: Any | None = None,
             model: str = "",
             constructor_label: str = FIXTURE_LABEL) -> CellResult:
    if arm not in ARMS:
        raise ValueError("unknown arm %r" % (arm,))
    tag = "e-%s-%s-%s-r%d-%s" % (
        _sha(freeze["freeze_id"].encode())[:12], panel, task_id, repeat, arm)
    seed = seed_episode(dsn, tag, snapshot_files(task_id))
    if gateway is None:
        gateway = FakeGatewayAdapter(text="")
    if not model:
        model = "doubled-default"
    decision = arm_decision(
        arm, task_id=task_id, package_entry=package_entry,
        package_digest=package_digest, package_text=package_text,
        gateway=gateway, model=model,
        dsn=dsn, run_id="run-%s" % tag,
        allocation_id=seed["allocation_id"])
    fallback_note = ""
    scheduled_arm = arm
    executed_treatment: str | None = None
    if decision["kind"] == "retained":
        executed_treatment = "L-acquired"
    if decision["kind"] == "none":
        fallback_note = "none-selection:S-fallback"
        executed_treatment = "S-fallback"
        arm = "S"
        decision = arm_decision(
            "S", task_id=task_id, package_entry=None,
            package_digest=package_digest, package_text=package_text,
            gateway=gateway, model=model,
            dsn=dsn, run_id="run-%s" % tag,
            allocation_id=seed["allocation_id"])
    elif decision["kind"] in ("stop", "unsupported"):
        fallback_note = "model-%s:S-fallback" % decision["kind"]
        executed_treatment = "S-fallback"
        arm = "S"
        decision = arm_decision(
            "S", task_id=task_id, package_entry=None,
            package_digest=package_digest, package_text=package_text,
            gateway=gateway, model=model,
            dsn=dsn, run_id="run-%s" % tag,
            allocation_id=seed["allocation_id"])
    entry = decision.get("entry") or arm_policy_entry(
        arm, task_id=task_id, package_entry=package_entry,
        package_digest=package_digest,
        model_proposal=(decision.get("proposal")
                        if decision.get("kind") == "interpreted" else None))
    snapshot = snapshot_files(task_id)
    payload = oracle.build_solver_payload(task_id)
    requires = _requires_for(task_id, snapshot)
    package = {"version_id": "coord02-E-%s" % tag,
               "package_digest": _sha(entry),
               "entry_bytes": entry, "requires": requires}
    cfg = EpisodeConfig(
        run_id="run-%s" % tag, task_id=task_id,
        allocation_id=seed["allocation_id"],
        investigation_id=seed["investigation_id"],
        snapshot=dict(snapshot),
        interface_contract=_dev_interface_contract(task_id, payload),
        join_rules=_dev_join_rules(task_id),
        bindings=_dev_bindings(requires, snapshot),
        source_interfaces=_dev_source_interfaces(task_id),
        package=package, snapshot_digest=seed["snapshot_digest"])
    problems = check_ceilings(_admit_floor())
    if problems:
        raise ValueError("pre-admit ceiling breach: %s" % problems)
    if constructor_label != FIXTURE_LABEL:
        raise ValueError("unknown constructor label %r" % (
            constructor_label,))
    factory = run_child_factory(
        dsn, task_id=task_id, gateway=gateway, model=model,
        allocation_id=seed["allocation_id"])
    outcome = run_episode(dsn, cfg, launcher_factory(tag), factory)
    solved = outcome.get("status") == "success"
    protected = _protected_of(outcome)
    failures = outcome.get("failures") or []
    if fallback_note:
        failures = list(failures) + [{"reason": fallback_note}]
    if not solved and protected.get("failed", 0) > len(failures):
        missing = protected["failed"] - len(failures)
        failures = list(failures) + [
            {"reason": outcome.get("reason")
             or outcome.get("status", "no-outcome"),
             "protected_case": i}
            for i in range(missing)]
    cell_ops = SE.cell_operation_ids(
        dsn, run_id=cfg.run_id, task_id=task_id,
        plan_id=outcome.get("plan_id"))
    costs, unmeasured = _cell_costs(dsn, cell_ops, outcome)
    receipts = sorted(cell_ops)
    if not receipts:
        raise SE.TrialError("cell %s left no durable operations to attest"
                            % cfg.run_id)
    trial_outcome = "success" if solved else "failure"
    liabilities = list(outcome.get("liabilities") or [])
    if unmeasured:
        liabilities = liabilities + [
            {"party": "campaign",
             "reason": "model-token usage unmeasured on operations: %s"
                       % ", ".join(sorted(unmeasured)),
             "operation": sorted(unmeasured)[0]}]
    trial = SE.build_trial_record(
        freeze_id=freeze["freeze_id"], panel=panel, task_id=task_id,
        repeat=repeat, arm=scheduled_arm, source_sha=source_sha,
        config_digest=config_digest, package_digest=package_digest,
        outcome=trial_outcome, solved=solved,
        protected={"passed": int(protected.get("passed", 0)),
                   "failed": int(protected.get("failed", 0)),
                   "total": int(protected.get("total", 0))},
        failures=failures, costs=costs, receipts=receipts,
        operations=[{"operation_id": r, "kind": cell_ops[r]["kind"]}
                    for r in receipts],
        liabilities=liabilities,
        executed_treatment=executed_treatment,
        fallback_reason=fallback_note or None)
    problems = check_ceilings(trial["costs"])
    if problems:
        raise ValueError("pre-admit ceiling breach: %s" % problems)
    return CellResult(record=trial, outcome=outcome)


def run_panel(dsn: str, *, freeze: dict, panel: str,
              launcher_factory: Callable, arms: tuple = ARMS,
              repeats: tuple | None = None,
              package_entry: bytes | None = None,
              package_digest: str = "none",
              package_text: str = "",
              source_sha: str = "entry-base",
              config_digest: str = "entry-base",
              gateway: Any | None = None,
              model: str = "") -> list:
    repeats = repeats if repeats is not None else freeze_mod.REPEATS
    wanted = {(c["task"], c["repeat"], c["arm"]) for c in freeze["schedule"]
              if c["panel"] == panel}
    results = []
    seen: set = set()
    for cell in freeze["schedule"]:
        if cell["panel"] != panel:
            continue
        if (cell["task"], cell["repeat"], cell["arm"]) not in wanted:
            continue
        if cell["repeat"] not in repeats or cell["arm"] not in arms:
            continue
        key = (freeze["freeze_id"], panel, cell["task"],
               cell["repeat"], cell["arm"])
        if key in seen:
            raise ValueError("duplicate pair %r" % (key,))
        seen.add(key)
        results.append(run_cell(
            dsn, freeze=freeze, task_id=cell["task"], panel=panel,
            repeat=cell["repeat"], arm=cell["arm"],
            launcher_factory=launcher_factory,
            package_entry=package_entry,
            package_digest=package_digest,
            package_text=package_text,
            source_sha=source_sha, config_digest=config_digest,
            gateway=gateway, model=model))
    return results


def restage_tree(dsn: str, outcome: dict) -> dict | None:
    from settlement import team as _team
    try:
        plan_id = outcome.get("plan_id") or ""
        rev = int(outcome.get("revision") or 1)
        summary = _team.plan_summary(dsn, plan_id)
        snap = _team._snapshot_of(dsn, summary["snapshot_digest"])
        tree = dict(snap)
        for child in summary["children"]:
            _r, _n, _i, _g, od, _f = _team.submission_tuple(
                dsn, plan_id, rev, child["node_id"])
            tree.update(_team._output_of(dsn, od))
        return tree
    except (LookupError, ValueError):
        return None


def write_evidence(cells: list, *, freeze: dict, evidence_root: Any,
                   dsn: str) -> dict:
    root = Path(evidence_root)
    records = []
    for cell in cells:
        trial = cell.record
        tree = restage_tree(dsn, cell.outcome) if dsn else None
        records.append(stage_record(root, trial, tree))
    episodes = root / "episodes"
    episodes.mkdir(parents=True, exist_ok=True)
    for record in records:
        pair = "%s-%s-%s-%s-r%d" % (record["freeze_id"], record["panel"],
                                    record["arm"], record["task_id"],
                                    record["repeat"])
        (episodes / ("%s.json" % pair)).write_text(
            json.dumps(record, indent=2) + "\n")
    freeze_path = root / "freeze.json"
    freeze_mod.write_freeze(freeze_path, freeze)
    present = sorted({str(trial["panel"]) for trial in
                      (c.record for c in cells)})
    report = checker.check_evidence(root, freeze_path,
                                    panels=tuple(present))
    union_cells = []
    for cell, record in zip(cells, records):
        pair = "%s-%s-%s-%s-r%d" % (record["freeze_id"], record["panel"],
                                    record["arm"], record["task_id"],
                                    record["repeat"])
        union_cells.append({
            "cell_id": pair,
            "operation_ids": [o["operation_id"]
                              for o in cell.record["operations"]]})
    union = SE.reconcile_campaign_union_from_store(
        dsn, union_cells,
        kinds={o["operation_id"]: o["kind"] for cell in cells
               for o in cell.record["operations"]})
    campaign_budgets = freeze.get("campaign_budgets")
    breaches = (check_ceilings(union["totals"], campaign_budgets)
                if campaign_budgets is not None else [])
    report["problems"] = list(dict.fromkeys(report["problems"] + breaches))
    report["clean"] = not report["problems"]
    return {"records": len(records), "checker": report, "union": union,
            "ceilings": {"breaches": breaches,
                         "checked": campaign_budgets is not None}}


def status_view(dsn: str, *, freeze: dict, evidence_root: Any,
                panels: tuple = ("evaluation", "transfer")) -> dict:
    root = Path(evidence_root)
    freeze_path = root / "freeze.json"
    if freeze_path.is_file():
        report = checker.check_evidence(root, freeze_path,
                                        panels=tuple(panels))
    else:
        report = {"clean": False, "problems": ["no-evidence"],
                  "records": 0, "summary": {}}
    return {"entry": ENTRY_VERSION, "freeze_id": freeze["freeze_id"],
            "arms": list(ARMS), "evidence": report}


def gateway_factory(*, doubled: bool = False) -> Any:
    if doubled:
        return FakeGatewayAdapter()
    from settlement.config import Settings
    from settlement.gateway_http import HttpGatewayAdapter
    return HttpGatewayAdapter.from_settings(
        Settings.from_env(), api="responses")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="coord02 four-arm entry")
    parser.add_argument("--panel", default="development",
                        choices=["development", "evaluation", "transfer"])
    parser.add_argument("--model", default="")
    parser.add_argument("--dsn", default=os.environ.get(
        "EC02_E_DSN",
        "dbname=ec02test_e host=/var/run/postgresql user=ubuntu"))
    parser.add_argument("--evidence-root", default="evidence-coord02")
    parser.add_argument("--freeze-id", default="coord02-live")
    parser.add_argument("--source-sha", default="entry-base")
    parser.add_argument("--doubled", action="store_true",
                        help="prove the harness on the fake gateway")
    args = parser.parse_args(argv)
    label = DOUBLED_LABEL if args.doubled or not args.model \
        else "LIVE"
    if not args.doubled and (label == "LIVE"
                             or args.panel in ("evaluation", "transfer")):
        try:
            preflight.require_live(panels=(args.panel,))
        except PermissionError as exc:
            print("blocked: %s" % exc)
            return 2
    if label == "LIVE":
        os.environ["TEAM01_LIVE_MODEL"] = args.model
    gateway = gateway_factory(doubled=(label == DOUBLED_LABEL))
    refuse_gateway_error(gateway.check_discovery(), check="discovery")
    freeze = freeze_mod.build_freeze(args.freeze_id,
                                     source_sha=args.source_sha)
    panel_cells = [c for c in freeze["schedule"]
                   if c["panel"] == args.panel]
    freeze_view = dict(freeze)
    root = Path(args.evidence_root)
    base = root / "runs"

    def _factory(tag: str) -> dict:
        return {"local-process": LocalLauncher(base / tag)}

    doubled = {"package_text": "doubled-dev"} \
        if label == DOUBLED_LABEL else {}
    cells = run_panel(args.dsn, freeze=freeze_view, panel=args.panel,
                      launcher_factory=_factory,
                      source_sha=args.source_sha,
                      config_digest=ENTRY_VERSION,
                      gateway=gateway, model=args.model or "doubled",
                      **doubled)
    summary = write_evidence(cells, freeze=freeze, evidence_root=root,
                             dsn=args.dsn)
    print(json.dumps({"label": label, "panel": args.panel,
                      "records": summary["records"],
                      "clean": summary["checker"]["clean"]}, indent=2))
    _ = (gateway, panel_cells)
    return 0 if summary["checker"]["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
