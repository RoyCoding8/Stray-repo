"""Thin coord02 study controller: admission-before-inference execution path.

DEC-EC02-01: reuse representation invocation helpers, capabilities
retention and team admission. No duplicate scheduler, plugin framework,
registry or per-arm solver clones. Causal order on this path is policy
step -> validate -> team.propose_team_plan -> admitted child ownership ->
child bytes -> submit -> join -> freeze. The old team01 solver built child
bytes before proposing; that order is reversed here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from settlement import artifacts, broker, capabilities, store, team
from settlement.common import Command, ResultCode, SettlementError
from settlement.representation import canonical_bytes, sha_hex

from .policy_exec import (
    PROBE_RECEIPT_KIND,
    STEP_RECEIPT_KIND,
    invoke_policy_step,
    run_probe_call,
    step_op_id,
)
from .schemas import (
    ALLOWED,
    MAX_POLICY_STEPS,
    PHASE_POST_FAIL_JOIN,
    PHASE_POST_FAIL_PROBE,
    PHASE_POST_PROBE,
    PHASE_PRE_PLAN,
    PHASE_TERMINAL,
    PROFILE,
    PROFILE_VERSION,
    PolicyError,
    build_request,
)

POLICY_ENTRY = "policy.py"


@dataclass
class EpisodeConfig:
    run_id: str
    task_id: str
    allocation_id: str
    investigation_id: str
    snapshot: dict
    interface_contract: dict
    join_rules: dict
    bindings: list = field(default_factory=list)
    source_interfaces: dict = field(default_factory=dict)
    package: dict = field(default_factory=dict)
    snapshot_digest: str = ""
    max_steps: int = MAX_POLICY_STEPS
    step_timeout_ms: int = 2000
    probe_timeout_ms: int = 5000
    s_fallback_outputs: dict | None = None


class Halted(Exception):
    pass


def _cmd(payload: Any = None) -> Command:
    return Command(request_id=f"coord02-{uuid.uuid4().hex}",
                   payload=payload or {})


def seed_episode(dsn: str, tag: str, snapshot: dict,
                 authorized: int = 100000) -> dict:
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-root",
                                    "domain": "cpu",
                                    "authorized": authorized,
                                    "max_occupancy": 16}))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-inv",
                                     "objective": f"coord02 {tag}",
                                     "obligations": {"repair": True}}))
    snap = team.register_snapshot(dsn, _cmd(), dict(snapshot))
    if snap.code != ResultCode.APPLIED:
        raise SettlementError(f"snapshot refused: {snap.detail}")
    return {"allocation_id": f"{tag}-root",
            "investigation_id": f"{tag}-inv",
            "snapshot_digest": snap.data["snapshot_digest"]}


def render_task_input(cfg: EpisodeConfig, *, observations: list,
                      accepted_plan: dict | None,
                      residual: dict, remaining: dict) -> dict:
    return {"task_snapshot": dict(cfg.snapshot),
            "public_contract": dict(cfg.interface_contract),
            "interface_bindings": [dict(b) for b in cfg.bindings],
            "accepted_plan": accepted_plan,
            "observations": list(observations),
            "residual_obligations": dict(residual),
            "remaining_allocation": dict(remaining),
            "dependency_versions": {b["name"]: b.get("version", "")
                                    for b in cfg.bindings}}


def render_child_obligation(child: dict, observations: list) -> dict:
    return {"node_id": child["node_id"], "obligation": child["obligation"],
            "owned_paths": list(child["owned_paths"]),
            "input_bindings": dict(child["input_bindings"]),
            "output_contract": dict(child["output_contract"]),
            "admitted_observations": [o.get("interface") for o in observations
                                      if isinstance(o, dict)]}


def check_bindings(snapshot: dict, bindings: list, requires: dict,
                   dsn: str, version_id: str) -> dict:
    if capabilities.quarantine_status(dsn, version_id) is not None:
        return {"ok": False, "reason": f"package {version_id} is quarantined"}
    by_name = {b.get("name"): b for b in bindings if isinstance(b, dict)}
    for role, need in (requires or {}).items():
        have = by_name.get(role)
        if have is None or have.get("path") not in snapshot:
            return {"ok": False,
                    "reason": f"role {role} has no bound input"}
        live = sha_hex(snapshot[have["path"]].encode())
        if live != need.get("digest"):
            return {"ok": False,
                    "reason": f"role {role} is incompatible with this input"}
        if have.get("abi") != need.get("abi"):
            return {"ok": False,
                    "reason": f"role {role} ABI does not match"}
        if str(have.get("version", "")) != str(need.get("version", "")):
            return {"ok": False,
                    "reason": f"role {role} version is not supported"}
    return {"ok": True}


def stage_package(staging_root: Any, *, entry_bytes: bytes,
                  description: bytes, requires: dict) -> dict:
    from settlement.representation import sha_hex as _sha
    manifest = {"files": [
        {"path": POLICY_ENTRY, "digest": _sha(entry_bytes),
         "size": len(entry_bytes)},
        {"path": "DESCRIPTION.md", "digest": _sha(description),
         "size": len(description)}],
        "entry": POLICY_ENTRY, "verify_args": ["--selftest"],
        "profile": PROFILE, "profile_version": PROFILE_VERSION,
        "coordination_requires": dict(requires or {})}
    return artifacts.stage_package(
        None, staging_root, manifest=manifest,
        files={POLICY_ENTRY: entry_bytes, "DESCRIPTION.md": description},
        scope="coord02", access_label="public", format=PROFILE,
        version=PROFILE_VERSION,
        dependencies=[f"policy:{_sha(entry_bytes)}"])


def publish_package_version(dsn: str, artifacts_root: Any, receipt: dict,
                            launcher: Any, allocation_id: str, *,
                            version_id: str, requires: dict) -> Any:
    staged = artifacts.publish_package(
        dsn, _cmd(), artifacts_root, receipt)
    if staged.code != ResultCode.APPLIED:
        return staged
    return capabilities.publish_candidate(
        dsn, _cmd(), artifacts_root, launcher, allocation_id,
        version_id=version_id, family="coordination",
        invocation={"profile": PROFILE, "profile_version": PROFILE_VERSION,
                    "entry": POLICY_ENTRY},
        artifact_digest=receipt["digest"],
        applicability={"requires": dict(requires or {})},
        scope={"study": "coord02"}, dependencies=[receipt["digest"]])


def load_frozen_package(dsn: str, artifacts_root: Any,
                        version_id: str) -> dict:
    if capabilities.quarantine_status(dsn, version_id) is not None:
        raise SettlementError(f"package {version_id} is quarantined")
    row = capabilities.get_version(dsn, version_id)
    if row is None:
        raise SettlementError(f"unknown package {version_id}")
    digest = row.get("artifact_digest") or ""
    checked = artifacts.verify_bytes(dsn, artifacts_root, digest)
    if not checked.get("ok"):
        raise SettlementError(f"package {version_id} bytes do not verify")
    import json
    from pathlib import Path
    package = json.loads((Path(artifacts_root) / digest).read_bytes()
                         .decode("utf-8"))
    files = {rel: bytes.fromhex(hexed)
             for rel, hexed in package["files"].items()}
    return {"version_id": version_id, "package_digest": digest,
            "entry_bytes": files[POLICY_ENTRY],
            "requires": dict((row.get("applicability") or {})
                             .get("requires", {}))}


def list_step_receipts(dsn: str, run_id: str, task_id: str) -> list[dict]:
    from psycopg.rows import dict_row
    from settlement import db
    out = []
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT operation_id, receipt_identity, content FROM receipts"
                        " WHERE receipt_identity LIKE %s ORDER BY operation_id",
                        (f"{STEP_RECEIPT_KIND}:coord:{run_id}:{task_id}:%",))
            for row in cur.fetchall():
                content = dict(row.get("content") or {})
                content["_operation_id"] = row["operation_id"]
                out.append(content)
            conn.commit()
    return out


def list_probe_observations(dsn: str, run_id: str, task_id: str) -> list[dict]:
    from psycopg.rows import dict_row
    from settlement import db
    out = []
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT content FROM receipts"
                        " WHERE receipt_identity LIKE %s ORDER BY receipt_identity",
                        (f"{PROBE_RECEIPT_KIND}:coord:{run_id}:{task_id}:%",))
            for row in cur.fetchall():
                content = dict(row.get("content") or {})
                if "observation" in content:
                    out.append(content["observation"])
            conn.commit()
    return out


def _residual_of(join: dict | None) -> dict:
    if not join:
        return {}
    return {"join_failed": True,
            "observed_output": join.get("observed_output", {}),
            "failing_input": join.get("failing_input", {})}


def derive_status(dsn: str, cfg: EpisodeConfig) -> dict:
    decisions = list_step_receipts(dsn, cfg.run_id, cfg.task_id)
    observations = list_probe_observations(dsn, cfg.run_id, cfg.task_id)
    state = team.team_state(dsn, cfg.investigation_id)
    plans = state["plans"]
    plan_id = plans[-1]["plan_id"] if plans else None
    revision, frozen, passed, join = 1, None, None, None
    carried_state: dict = {}
    if plan_id is not None:
        revision = int(plans[-1]["revision"])
        frozen = plans[-1]["frozen_candidate"]
        try:
            join = team.join_record(dsn, plan_id, revision)
            passed = bool(join.get("passed"))
        except LookupError:
            join, passed = None, None
        try:
            carried_state = {"r1": team.join_record(dsn, plan_id, 1)}
        except LookupError:
            pass
    probe_pre = any(d.get("action") == "probe"
                    and d.get("request", {}).get("phase") == PHASE_PRE_PLAN
                    for d in decisions)
    probe_fail = any(d.get("action") == "probe" and d.get("request", {})
                     .get("phase") == PHASE_POST_FAIL_JOIN for d in decisions)
    if plan_id is None:
        phase = PHASE_POST_PROBE if probe_pre else PHASE_PRE_PLAN
    elif passed is True or frozen:
        phase = PHASE_TERMINAL
    elif join is not None and not passed and revision >= 2:
        phase = PHASE_TERMINAL
    elif join is not None and not passed:
        phase = PHASE_POST_FAIL_PROBE if probe_fail else PHASE_POST_FAIL_JOIN
    elif join is None and not frozen:
        phase = "executing"
    else:
        phase = PHASE_TERMINAL
    sentinel = None
    if decisions:
        first = decisions[0]
        sentinel = {"decision_id": first.get("decision_id"),
                    "request_digest": first.get("request_digest"),
                    "operation_id": first.get("_operation_id")}
    return {"phase": phase, "plan_id": plan_id, "revision": revision,
            "frozen": frozen, "join_passed": passed, "join": join,
            "first_join": carried_state.get("r1"),
            "decisions": decisions, "observations": observations,
            "steps_used": len(decisions), "sentinel": sentinel,
            "probe_pre": probe_pre, "probe_fail": probe_fail}


def _remaining(dsn: str, allocation_id: str) -> dict:
    try:
        row = store.allocation_status(dsn, allocation_id)
        return {"allocation_id": allocation_id,
                "authorized": row.get("authorized"),
                "consumed": row.get("consumed"),
                "reserved": row.get("reserved")}
    except SettlementError:
        return {"allocation_id": allocation_id}


def _revalidate(dsn: str, cfg: EpisodeConfig, status: dict) -> dict | None:
    live_entry = sha_hex(cfg.package.get("entry_bytes", b""))
    if live_entry != cfg.package.get("package_digest"):
        return {"status": "stale-inputs",
                "reason": "selected package bytes changed during execution"}
    if team.snapshot_digest(cfg.snapshot) != cfg.snapshot_digest:
        return {"status": "stale-inputs",
                "reason": "task inputs changed during execution"}
    bound = check_bindings(cfg.snapshot, cfg.bindings,
                           cfg.package.get("requires", {}), dsn,
                           cfg.package.get("version_id", ""))
    if not bound["ok"]:
        return {"status": "stale-inputs", "reason": bound["reason"]}
    return None


def _outcome(status: str, cfg: EpisodeConfig, base: dict,
             reason: str = "", liable: list | None = None) -> dict:
    out = {"status": status, "reason": reason, "run_id": cfg.run_id,
           "task_id": cfg.task_id, "plan_id": base.get("plan_id"),
           "revision": base.get("revision", 1), "candidate_digest": None,
           "steps": base.get("steps_used", 0),
           "probe_calls": len(base.get("observations", [])),
           "liabilities": list(liable or []),
           "live_source": "simulated (FakeGatewayAdapter; no live grant)"}
    out.update({k: v for k, v in base.items()
                if k in ("carried", "invalidated", "child_ops")})
    if base.get("join") and base["join"].get("passed"):
        out["candidate_digest"] = base["join"].get("candidate_digest")
    return out


def _liable(party: str, reason: str, operation: str) -> dict:
    return {"party": party, "reason": reason, "operation": operation}


def _source_digest(cfg: EpisodeConfig, observations: list) -> str:
    return sha_hex(canonical_bytes(
        {"snapshot": cfg.snapshot_digest, "observations": observations}))


def _take_step(dsn: str, cfg: EpisodeConfig, launchers: dict, status: dict,
               phase: str, revision: int) -> dict:
    launcher = launchers["local-process"]
    seq = status["steps_used"]
    decision_id = f"{cfg.run_id}:{cfg.task_id}:d{seq:04d}"
    source_digest = _source_digest(cfg, status["observations"])
    request = build_request(
        decision_id=decision_id,
        package_digest=cfg.package["package_digest"],
        source_digest=source_digest, plan_revision=revision, phase=phase,
        allowed=list(ALLOWED[phase]), state=status["decisions"][-1]["state"]
        if status["decisions"] and "state" in status["decisions"][-1] else {},
        task=render_task_input(
            cfg, observations=status["observations"],
            accepted_plan=(team.plan_summary(dsn, status["plan_id"])
                           if status["plan_id"] else None),
            residual=_residual_of(status.get("join") or status.get("first_join")),
            remaining=_remaining(dsn, cfg.allocation_id)))
    return invoke_policy_step(
        dsn, launcher, run_id=cfg.run_id, task_id=cfg.task_id, seq=seq,
        entry_bytes=cfg.package["entry_bytes"], request=request,
        allocation_id=cfg.allocation_id,
        timeout_ms=cfg.step_timeout_ms)


def _run_probes(dsn: str, cfg: EpisodeConfig, launchers: dict, status: dict,
                proposal: dict) -> list[dict]:
    launcher = launchers["local-process"]
    seq = status["steps_used"] - 1
    out = []
    for idx, call in enumerate(proposal["invocations"]):
        name = call["interface"]
        if name not in cfg.source_interfaces:
            raise PolicyError("malformed",
                              f"probe interface {name!r} is not bound")
        out.append(run_probe_call(
            dsn, launcher, run_id=cfg.run_id, task_id=cfg.task_id,
            seq=seq, idx=idx, interface=name,
            interface_bytes=cfg.source_interfaces[name],
            call_input=call["input"], allocation_id=cfg.allocation_id,
            timeout_ms=cfg.probe_timeout_ms)["observation"])
    return out


def _join_rules_for_shape(cfg: EpisodeConfig, shape: str,
                          children: list) -> dict:
    join = {"single": "accept", "alternatives": "select-one",
            "decompose": "conjunctive"}[shape]
    rules = dict(cfg.join_rules)
    rules["join"] = join
    rules["integration_owner"] = children[0]["node_id"]
    return rules


def _admit_plan(dsn: str, cfg: EpisodeConfig, proposal: dict,
                decision_id: str) -> Any:
    return team.propose_team_plan(
        dsn, _cmd(), parent_obligation=f"{cfg.investigation_id}:repair",
        snapshot_digest=cfg.snapshot_digest, shape=proposal["shape"],
        children=proposal["children"],
        interface_contract=dict(cfg.interface_contract),
        join_rules=_join_rules_for_shape(cfg, proposal["shape"],
                                         proposal["children"]),
        allocation_id=cfg.allocation_id,
        policy_response={"shape": proposal["shape"],
                         "decision_id": decision_id,
                         "package_digest": cfg.package["package_digest"]})


def _cancelled_op(dsn: str, operation_id: str) -> bool:
    row = broker.read_operation(dsn, operation_id)
    return row is not None and (row.get("cancel_state") or "none") != "none"


def _dispatch_children(dsn: str, cfg: EpisodeConfig, launchers: dict,
                       plan_id: str, revision: int,
                       nodes: list | None = None) -> dict[str, str]:
    receipts: dict[str, str] = {}
    for node in nodes if nodes is not None else team.child_nodes(dsn, plan_id):
        op_id = team.child_operation(dsn, plan_id, node)
        if _cancelled_op(dsn, op_id):
            raise Halted(f"cancelled:{op_id}")
        gen = team.child_attempt(dsn, plan_id, node)["ownership_generation"]
        broker.dispatch_operation(dsn, op_id, launchers=launchers,
                                  ownership_generation=gen)
        if _cancelled_op(dsn, op_id):
            raise Halted(f"cancelled:{op_id}")
        hits = [r["receipt_identity"] for r in
                store.operation_receipts(dsn, op_id) if r["outcome"] == "success"]
        if not hits:
            raise SettlementError(f"child {node} left no success receipt")
        receipts[node] = hits
    return receipts


def _submitted_nodes(dsn: str, cfg: EpisodeConfig, plan_id: str,
                     revision: int) -> set[str]:
    state = team.team_state(dsn, cfg.investigation_id)
    return {s["node_id"] for s in state["submissions"]
            if s["plan_id"] == plan_id and int(s["plan_revision"]) == revision
            and not s.get("invalidated")}


def _submit_missing(dsn: str, cfg: EpisodeConfig, plan_id: str, revision: int,
                    receipts: dict, child_factory: Callable) -> dict:
    try:
        have = _submitted_nodes(dsn, cfg, plan_id, revision)
    except LookupError:
        have = set()
    results = {}
    for node in team.child_nodes(dsn, plan_id):
        if node in have:
            continue
        child = next(c for c in team.plan_summary(dsn, plan_id)["children"]
                     if c["node_id"] == node)
        rendered = render_child_obligation(
            child, list_probe_observations(dsn, cfg.run_id, cfg.task_id))
        produced = child_factory(node, child, rendered)
        if produced is None:
            return {"refused": f"no constructor artifact for {node}"}
        reg = team.register_output(dsn, _cmd(), dict(produced))
        if reg.code != ResultCode.APPLIED:
            return {"refused": f"output for {node} refused: {reg.detail}"}
        attempt = team.child_attempt(dsn, plan_id, node)
        done = team.submit_child(
            dsn, _cmd({"plan_id": plan_id}), plan_revision=revision,
            node_id=node,
            input_digests=team.expected_inputs(dsn, plan_id, node),
            ownership_generation=attempt["ownership_generation"],
            output_digest=reg.data["output_digest"],
            receipt_refs=receipts[node])
        if done.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            return {"refused": f"submit for {node} refused: {done.detail}"}
        results[node] = reg.data["output_digest"]
    return results


def _join_and_freeze(dsn: str, cfg: EpisodeConfig, launchers: dict,
                     plan_id: str, revision: int) -> dict:
    joined = team.assemble_and_join(dsn, _cmd(), plan_id=plan_id,
                                    launchers=launchers)
    if joined.code == ResultCode.APPLIED:
        frozen = team.freeze_candidate(
            dsn, _cmd(), plan_id=plan_id,
            candidate_digest=joined.data["candidate_digest"])
        if frozen.code != ResultCode.APPLIED:
            raise SettlementError(f"freeze refused: {frozen.detail}")
        return {"passed": True, "join": team.join_record(dsn, plan_id, revision)}
    if joined.code == ResultCode.OBSERVED_FAILURE:
        return {"passed": False, "join": team.join_record(dsn, plan_id, revision)}
    raise SettlementError(f"join undecided: {joined.detail}")


def run_s_fallback(dsn: str, cfg: EpisodeConfig, launchers: dict,
                   prior_status: str, prior_reason: str) -> dict:
    if cfg.s_fallback_outputs is None:
        return _outcome(prior_status, cfg, derive_status(dsn, cfg),
                        reason=prior_reason,
                        liable=[_liable("policy", prior_reason, "no-operation")])
    whole = sorted(cfg.snapshot)
    proposal = {"shape": "single",
                "children": [{"node_id": "w1", "obligation": "frozen single repair",
                              "owned_paths": whole,
                              "output_contract": {"entry": "whole-tree",
                                                  "checks": ["public"]},
                              "input_bindings": {f"base_{i}": p
                                                 for i, p in enumerate(whole)}}]}
    admitted = _admit_plan(dsn, cfg, proposal, "s-fallback")
    if admitted.code != ResultCode.APPLIED:
        base = derive_status(dsn, cfg)
        return _outcome("budget-exhausted" if admitted.code
                        == ResultCode.INSUFFICIENT_RESOURCES else "plan-refused",
                        cfg, base, reason=admitted.detail,
                        liable=[_liable("controller", admitted.detail,
                                        "s-fallback")])
    plan_id = admitted.data["plan_id"]
    receipts = _dispatch_children(dsn, cfg, launchers, plan_id, 1)
    reg = team.register_output(dsn, _cmd(), dict(cfg.s_fallback_outputs))
    attempt = team.child_attempt(dsn, plan_id, "w1")
    done = team.submit_child(
        dsn, _cmd({"plan_id": plan_id}), plan_revision=1, node_id="w1",
        input_digests=team.expected_inputs(dsn, plan_id, "w1"),
        ownership_generation=attempt["ownership_generation"],
        output_digest=reg.data["output_digest"],
        receipt_refs=receipts["w1"])
    if done.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        base = derive_status(dsn, cfg)
        return _outcome("submit-refused", cfg, base, reason=done.detail,
                        liable=[_liable("controller", done.detail, plan_id)])
    final = _join_and_freeze(dsn, cfg, launchers, plan_id, 1)
    base = derive_status(dsn, cfg)
    if final["passed"]:
        return _outcome("s-fallback-success", cfg, base,
                        reason=prior_reason,
                        liable=[_liable("policy", prior_reason, plan_id)])
    return _outcome("s-fallback-failed", cfg, base, reason=prior_reason,
                    liable=[_liable("policy", prior_reason, plan_id)])


_FAILURE_STATUS = {"timeout": "policy-timeout", "empty": "policy-empty",
                   "oversize": "policy-oversize"}


def _execute_plan(dsn: str, cfg: EpisodeConfig, launchers: dict,
                  plan_id: str, revision: int,
                  child_factory: Callable) -> dict:
    try:
        have = _submitted_nodes(dsn, cfg, plan_id, revision)
    except LookupError:
        have = set()
    missing = [n for n in team.child_nodes(dsn, plan_id) if n not in have]
    try:
        receipts = _dispatch_children(dsn, cfg, launchers, plan_id, revision,
                                      missing)
    except Halted as exc:
        return {"cancelled": str(exc)}
    missing = _submit_missing(dsn, cfg, plan_id, revision, receipts,
                              child_factory)
    if "refused" in missing:
        return {"refused": missing["refused"], "child_ops": receipts}
    final = _join_and_freeze(dsn, cfg, launchers, plan_id, revision)
    return {"passed": final["passed"], "join": final["join"],
            "child_ops": receipts}


def run_episode(dsn: str, cfg: EpisodeConfig, launchers: dict,
                child_factory: Callable,
                progress: Callable | None = None) -> dict:
    def _note(status: dict) -> None:
        if progress is not None:
            progress(status)

    bound = check_bindings(cfg.snapshot, cfg.bindings,
                           cfg.package.get("requires", {}), dsn,
                           cfg.package.get("version_id", ""))
    if not bound["ok"]:
        base = derive_status(dsn, cfg)
        return _outcome("unsupported", cfg, base, reason=bound["reason"],
                        liable=[_liable("controller", bound["reason"],
                                        "binding-check")])
    while True:
        status = derive_status(dsn, cfg)
        _note(status)
        if status["frozen"] and status["join_passed"]:
            return _outcome("success", cfg, status)
        if status["plan_id"] is not None and status["phase"] == "executing":
            stale = _revalidate(dsn, cfg, status)
            if stale is not None:
                return _outcome(stale["status"], cfg, status,
                                reason=stale["reason"],
                                liable=[_liable("controller", stale["reason"],
                                                status["plan_id"])])
            try:
                result = _execute_plan(dsn, cfg, launchers, status["plan_id"],
                                       status["revision"], child_factory)
            except Halted as exc:
                return _outcome("cancelled", cfg, status, reason=str(exc),
                                liable=[_liable("external", str(exc),
                                                status["plan_id"])])
            if "cancelled" in result:
                return _outcome("cancelled", cfg, status,
                                reason=result["cancelled"],
                                liable=[_liable("external", result["cancelled"],
                                                status["plan_id"])])
            if "refused" in result:
                base = derive_status(dsn, cfg)
                base["child_ops"] = result.get("child_ops", {})
                return _outcome("submit-refused", cfg, base,
                                reason=result["refused"],
                                liable=[_liable("constructor", result["refused"],
                                                status["plan_id"])])
            if result["passed"]:
                return _outcome("success", cfg, derive_status(dsn, cfg))
            continue
        if status["phase"] == PHASE_TERMINAL:
            base = status
            if base["join"] is not None and not base["join_passed"]:
                return _outcome("join-failed-terminal", cfg, base,
                                reason="rework join failed; intervention ends",
                                liable=[_liable("controller", "join failed",
                                                base["plan_id"] or "")])
            return _outcome("stopped", cfg, base, reason="no further action")
        if status["steps_used"] >= cfg.max_steps:
            return _outcome("budget-exhausted", cfg, status,
                            reason="policy step budget exhausted",
                            liable=[_liable("controller", "budget exhausted",
                                            "no-operation")])
        stale = _revalidate(dsn, cfg, status)
        if stale is not None:
            return _outcome(stale["status"], cfg, status,
                            reason=stale["reason"],
                            liable=[_liable("controller", stale["reason"],
                                            "no-operation")])
        try:
            taken = _take_step(dsn, cfg, launchers, status, status["phase"],
                               status["revision"])
        except PolicyError as exc:
            op = step_op_id(cfg.run_id, cfg.task_id, status["steps_used"])
            failed = _FAILURE_STATUS.get(exc.reason, "policy-invalid")
            if status["phase"] in (PHASE_PRE_PLAN, PHASE_POST_PROBE) \
                    and status["plan_id"] is None:
                return run_s_fallback(
                    dsn, cfg, launchers, failed, exc.detail or exc.reason)
            return _outcome(failed, cfg, derive_status(dsn, cfg),
                            reason=exc.detail or exc.reason,
                            liable=[_liable("policy", exc.reason, op)])
        action, proposal = taken["action"], taken["proposal"]
        if action == "probe":
            try:
                _run_probes(dsn, cfg, launchers, derive_status(dsn, cfg),
                            proposal)
            except PolicyError as exc:
                return _outcome("policy-invalid", cfg,
                                derive_status(dsn, cfg),
                                reason=exc.detail or exc.reason,
                                liable=[_liable("policy", exc.reason,
                                                taken["op_id"])])
            continue
        if action in ("stop", "unsupported"):
            if status["plan_id"] is None:
                prior = "stopped" if action == "stop" else "unsupported"
                return run_s_fallback(
                    dsn, cfg, launchers, prior,
                    proposal.get("reason", action))
            base = derive_status(dsn, cfg)
            return _outcome("stopped", cfg, base,
                            reason=proposal.get("reason", action),
                            liable=[_liable("policy", action,
                                            base["plan_id"] or "")])
        if action == "plan":
            if status["plan_id"] is not None:
                base = derive_status(dsn, cfg)
                return _outcome("policy-invalid", cfg, base,
                                reason="second initial plan is not allowed",
                                liable=[_liable(
                                    "policy", "duplicate plan",
                                    taken["op_id"])])
            admitted = _admit_plan(dsn, cfg, proposal, taken["decision_id"])
            if admitted.code != ResultCode.APPLIED:
                base = derive_status(dsn, cfg)
                if admitted.code == ResultCode.INSUFFICIENT_RESOURCES:
                    return _outcome("budget-exhausted", cfg, base,
                                    reason=admitted.detail,
                                    liable=[_liable("controller",
                                                    admitted.detail,
                                                    "no-operation")])
                return _outcome("plan-refused", cfg, base,
                                reason=admitted.detail,
                                liable=[_liable("policy", admitted.detail,
                                                "no-operation")])
            continue
        base = derive_status(dsn, cfg)
        if status["phase"] not in (PHASE_POST_FAIL_JOIN,
                                   PHASE_POST_FAIL_PROBE):
            return _outcome("policy-invalid", cfg, base,
                            reason="rework is only allowed after a failed join",
                            liable=[_liable("policy", "rework out of phase",
                                            taken["op_id"])])
        revised = team.revise_team_plan(
            dsn, _cmd(), plan_id=status["plan_id"],
            children=_rework_children(dsn, status["plan_id"], proposal),
            interface_contract=dict(cfg.interface_contract),
            reason=f"policy rework {taken['decision_id']}",
            launchers=launchers, rework=proposal["rework"])
        if revised.code != ResultCode.APPLIED:
            return _outcome("plan-refused", cfg, derive_status(dsn, cfg),
                            reason=revised.detail,
                            liable=[_liable("policy", revised.detail,
                                            status["plan_id"] or "")])
        base = derive_status(dsn, cfg)
        base["carried"] = revised.data.get("carried", [])
        base["invalidated"] = [s for s in
                               _superseded_nodes(revised.data, base["carried"])]
        stale = _revalidate(dsn, cfg, base)
        if stale is not None:
            return _outcome(stale["status"], cfg, base,
                            reason=stale["reason"],
                            liable=[_liable("controller", stale["reason"],
                                            base["plan_id"] or "")])
        try:
            result = _execute_plan(dsn, cfg, launchers, base["plan_id"],
                                   base["revision"], child_factory)
        except Halted as exc:
            return _outcome("cancelled", cfg, base, reason=str(exc),
                            liable=[_liable("external", str(exc),
                                            base["plan_id"] or "")])
        if "cancelled" in result:
            return _outcome("cancelled", cfg, base, reason=result["cancelled"],
                            liable=[_liable("external", result["cancelled"],
                                            base["plan_id"] or "")])
        if "refused" in result:
            base = derive_status(dsn, cfg)
            return _outcome("submit-refused", cfg, base,
                            reason=result["refused"],
                            liable=[_liable("constructor", result["refused"],
                                            base["plan_id"] or "")])
        final = derive_status(dsn, cfg)
        final["carried"] = base.get("carried", [])
        final["invalidated"] = base.get("invalidated", [])
        if result["passed"]:
            return _outcome("success", cfg, final)
        return _outcome("join-failed-terminal", cfg, final,
                        reason="rework join failed; intervention ends",
                        liable=[_liable("controller", "join failed",
                                        final["plan_id"] or "")])


def _rework_children(dsn: str, plan_id: str, proposal: dict) -> list[dict]:
    current = team.plan_summary(dsn, plan_id)["children"]
    keep = []
    for child in current:
        keep.append({"node_id": child["node_id"],
                     "obligation": child["obligation"],
                     "owned_paths": list(child["owned_paths"]),
                     "output_contract": dict(child["output_contract"]),
                     "input_bindings": dict(child["input_bindings"])})
    names = {c["node_id"] for c in keep}
    if not set(proposal["rework"]) <= names:
        raise SettlementError("rework names unknown nodes")
    return keep


def _superseded_nodes(revised_data: dict, carried: list) -> list[str]:
    ops = revised_data.get("child_operations", {})
    return sorted(n for n in ops if n not in set(carried or []))


def resume_episode(dsn: str, cfg: EpisodeConfig, launchers: dict,
                   child_factory: Callable,
                   progress: Callable | None = None) -> dict:
    return run_episode(dsn, cfg, launchers, child_factory, progress)


def build_experience_packet(dsn: str, *, run_id: str, task_id: str,
                            investigation_id: str) -> dict:
    state = team.team_state(dsn, investigation_id)
    return {"packet_version": "coord02-experience/1", "run_id": run_id,
            "task_id": task_id, "investigation_id": investigation_id,
            "decisions": list_step_receipts(dsn, run_id, task_id),
            "probe_observations": list_probe_observations(dsn, run_id, task_id),
            "plans": state["plans"], "submissions": state["submissions"],
            "joins": state["joins"]}


def construction_call_spec(packet: dict, budget: dict) -> dict:
    return {"abi": {"argv": ["python", "<entry>", "<request.json>",
                             "<response.json>"],
                    "request_fields": ["profile", "profile_version",
                                       "decision_id", "package_digest",
                                       "source_digest", "plan_revision",
                                       "phase", "allowed_actions", "state",
                                       "task"],
                    "response_fields": ["profile", "profile_version",
                                        "decision_id", "package_digest",
                                        "source_digest", "plan_revision",
                                        "phase", "proposal", "state"],
                    "actions": ["probe", "plan", "rework", "stop",
                                "unsupported"],
                    "state_limit_bytes": 16 * 1024},
            "action_semantics": {
                "probe": "up to four bounded JSON calls of bound interfaces",
                "plan": "one single|alternatives|decompose team for admission",
                "rework": "name failed-join children for fresh attempts",
                "stop": "end intervention preserving residual obligation",
                "unsupported": "decline for a missing binding or scope"},
            "transport_examples": {
                "probe": {"action": "probe",
                          "invocations": [{"interface": "<bound-name>",
                                           "input": {}}]},
                "plan": {"action": "plan", "shape": "single", "children": []},
                "rework": {"action": "rework", "rework": ["<node>"]}},
            "development_observations": packet.get("probe_observations", []),
            "budget": dict(budget)}
