from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from settlement import broker, store, team
from settlement.common import Command, ResultCode, SettlementError
from settlement.gateway import GatewayError
from settlement.launcher_local import LocalLauncher

from experiments.team01 import oracle, panel, register, template
from experiments.team01 import checker as checker_mod

MODEL = "muse-spark-1.3-contributor-free"
ENDPOINT = "http://localhost:6446/v1"
API = "responses"
EFFORT = "low"
MAX_OUTPUT_TOKENS = 512
DEADLINE_MS = 290000
RETRIES = 0

CAPS = {"dev_episodes": 24, "template_builds": 2, "eval_episodes": 48,
        "transfer_episodes": 24, "probe_calls": 2}
DEV_PROBES = ("template-use", "diagnostic", "incompatible")
BUILD_IDS = [spec["id"] for spec in template.BUILDS]


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cmd(tag: str) -> Command:
    return Command(request_id="%s-%s" % (tag, uuid.uuid4().hex[:12]),
                   payload={})


def _receipt_contents(dsn: str, operation_id: str) -> list:
    from settlement import db
    from psycopg.rows import dict_row

    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT receipt_identity, outcome, content FROM receipts"
                        " WHERE operation_id = %s ORDER BY receipt_identity",
                        (operation_id,))
            rows = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return rows


def make_gateway(endpoint: str | None = None, api_key: str | None = None,
                 read_ms: int | None = None):
    from settlement.gateway_http import HttpGatewayAdapter

    key = api_key if api_key is not None else os.environ.get(
        "TEAM01_LIVE_API_KEY", "")
    if not key:
        raise SettlementError("live gateway needs TEAM01_LIVE_API_KEY")
    read = read_ms if read_ms is not None else int(
        os.environ.get("SETTLEMENT_GATEWAY_TIMEOUT_READ_MS", "290000"))
    return HttpGatewayAdapter(endpoint=endpoint or ENDPOINT, api_key=key,
                              timeout_read_ms=read, api=API)


def size_campaign_envelope(per_call_exposure: int) -> dict:
    calls = (CAPS["dev_episodes"] + CAPS["eval_episodes"]
             + CAPS["transfer_episodes"] + CAPS["template_builds"]
             + CAPS["probe_calls"])
    return {"caps": dict(CAPS), "planner_calls": calls,
            "per_call_exposure": int(per_call_exposure),
            "grant_authorized": calls * int(per_call_exposure),
            "retries": RETRIES, "model": MODEL,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "reasoning_effort": EFFORT}


class BudgetLedger:
    def __init__(self, caps: dict) -> None:
        self.caps = dict(caps)
        self.spent: dict = {key: 0 for key in caps}

    def spend(self, kind: str) -> int:
        if kind not in self.caps:
            raise SettlementError("unknown budget kind %r" % kind)
        if self.spent[kind] >= self.caps[kind]:
            raise SettlementError(
                "envelope exhausted: %s cap %d reached; stopping honestly"
                % (kind, self.caps[kind]))
        self.spent[kind] += 1
        return self.spent[kind]

    def used(self, kind: str) -> int:
        return self.spent[kind]

    def remaining(self, kind: str) -> int:
        return self.caps[kind] - self.spent[kind]


def _plan_prompt(arm: str, task_id: str, repeat: int, probe: str | None,
                 cold_shape: str, directive: str) -> str:
    info = panel._visible_info(task_id)
    lines = [
        "Choose one team shape for this repair task.",
        "visible: %s" % json.dumps(info, sort_keys=True),
        "arm=%s repeat=%d probe=%s cold-shape=%s" % (arm, repeat, probe,
                                                    cold_shape),
        "shapes: single (1 worker) | alternatives (2 whole-task attempts)"
        " | decompose (2 disjoint owners, needs stable interface)",
        "limits: at most 2 active children, 1 integration owner, 1 revision.",
    ]
    if directive:
        lines.append("frozen template directive: %s" % directive)
    lines.append('Reply with JSON only: {"shape": "<single|alternatives|'
                 'decompose>", "rationale": "<one sentence>"}.')
    return "\n".join(lines)


def _parse_envelope(text: str) -> dict | None:
    try:
        start, end = text.index("{"), text.rindex("}")
        parsed = json.loads(text[start:end + 1])
    except (ValueError, IndexError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _classify_error(message: str) -> str:
    lowered = (message or "").lower()
    if "no text" in lowered or "no message content" in lowered:
        return "empty-output"
    if "timed out" in lowered or "timeout" in lowered or "deadline" in lowered:
        return "timeout"
    if "auth" in lowered or "401" in lowered or "403" in lowered \
            or "credential" in lowered:
        return "auth"
    if "rate" in lowered or "429" in lowered:
        return "rate_limit"
    if "cancel" in lowered:
        return "cancelled"
    return "gateway-error"


def _cold_shape(task_id: str) -> str:
    return team.select_plan(panel._visible_info(task_id))["shape"]


def _kinds(arm: str, task_id: str, shape: str, probe: str | None) -> dict:
    family = oracle.TASK_FAMILY[task_id]
    key = arm.split("-")[-1]
    if probe == "incompatible":
        kinds = {"w1": "valid", "w2": "invalid"}
    elif key == "S":
        kind = "invalid" if family == "fam-seq" else "valid"
        kinds = {"w1": kind, "w2": kind}
    elif key == "P":
        kinds = {"w1": "invalid", "w2": "invalid"} \
            if family == "fam-cpl" else {"w1": "invalid", "w2": "valid"}
    else:
        kinds = {"w1": "valid", "w2": "valid"}
    if shape == "single":
        kinds = {"w1": kinds["w1"]}
    return kinds


class LivePlanner:
    def __init__(self, dsn: str, gateway, *, allocation_id: str, model: str,
                 tag: str, template_record: dict | None = None,
                 max_output_tokens: int = MAX_OUTPUT_TOKENS,
                 deadline_ms: int = DEADLINE_MS) -> None:
        self.dsn = dsn
        self.gateway = gateway
        self.allocation_id = allocation_id
        self.model = model
        self.tag = tag
        self.template_record = template_record
        self.max_output_tokens = max_output_tokens
        self.deadline_ms = deadline_ms
        self.calls: list = []

    def propose(self, arm: str, task_id: str, repeat: int,
                probe: str | None = None) -> dict:
        cold = _cold_shape(task_id)
        forced = {"S": "single", "P": "alternatives"}.get(arm)
        if forced is not None:
            call = {"operation_id": "", "arm": arm, "task_id": task_id,
                    "repeat": repeat, "probe": probe, "exposure": 0,
                    "usage": {"in": 0, "out": 0},
                    "outcome": "forced-%s" % forced, "stop_reason": "",
                    "shape": forced, "text_chars": 0}
            self.calls.append(call)
            kinds = _kinds(arm, task_id, forced, probe)
            return {"shape": forced, "kinds": kinds,
                    "costs": {"in": 0, "out": 0, "tools": 0, "calls": 0},
                    "template_used": False,
                    "template_changed_decision": False, "simulated": False,
                    "live_source": "forced",
                    "policy_rationale": "panel protocol fixes %s=%s" % (
                        arm, forced),
                    "kinds_source": "apparatus-overlay"}
        directive = ""
        applied = {"applicable": False}
        if arm == "warm-T" and self.template_record is not None:
            applied = template.apply_template(self.template_record, task_id)
            if applied["applicable"]:
                directive = self.template_record.get("directive", "")
        prompt = _plan_prompt(arm, task_id, repeat, probe, cold, directive)
        op_id = "%s-plan-%s-%s-r%d-%d" % (self.tag, arm, task_id, repeat,
                                          len(self.calls))
        ensured = broker.ensure_operation(
            self.dsn, operation_id=op_id, effect=broker.MODEL_INFERENCE,
            payload={"model": self.model,
                     "messages": [{"role": "user", "content": prompt}],
                     "max_output_tokens": self.max_output_tokens,
                     "deadline_ms": self.deadline_ms,
                     "reasoning_effort": EFFORT},
            allocation_id=self.allocation_id, retries=RETRIES)
        exposure = int((ensured.data or {}).get("exposure", 0))
        if ensured.code == ResultCode.INSUFFICIENT_RESOURCES:
            return self._record(op_id, arm, task_id, repeat, probe, exposure,
                                {"in": 0, "out": 0}, "fallback-%s" % (
                                    ensured.code.value,),
                                None, cold, "ensure refused: %s"
                                % ensured.detail)
        if ensured.code not in (ResultCode.APPLIED,
                                ResultCode.ALREADY_APPLIED):
            return self._record(op_id, arm, task_id, repeat, probe, exposure,
                                {"in": 0, "out": 0}, "fallback-ensure-refused",
                                None, cold, "ensure refused: %s"
                                % ensured.detail)
        broker.dispatch_operation(self.dsn, op_id, gateway=self.gateway)
        receipts = _receipt_contents(self.dsn, op_id)
        text, usage, stop = None, {"in": 0, "out": 0}, ""
        for receipt in receipts:
            content = dict(receipt.get("content") or {})
            if receipt.get("outcome") == "success" and "text" in content:
                text = content["text"]
                raw = dict(content.get("usage") or {})
                usage = {"in": int(raw.get("input_tokens", 0) or 0),
                         "out": int(raw.get("output_tokens", 0) or 0)}
                stop = str(content.get("stop_reason", ""))
                break
        if text is None:
            message = ""
            for receipt in receipts:
                content = dict(receipt.get("content") or {})
                if receipt.get("outcome") == "unknown" and content.get(
                        "error"):
                    message = str(content["error"])
                    break
            return self._record(op_id, arm, task_id, repeat, probe, exposure,
                                usage, "fallback-%s" % _classify_error(
                                    message), stop or None, cold,
                                "gateway gave no text: %s" % message)
        parsed = _parse_envelope(text)
        shape = (parsed or {}).get("shape", "")
        if shape not in ("single", "alternatives", "decompose"):
            return self._record(op_id, arm, task_id, repeat, probe, exposure,
                                usage, "fallback-invalid-shape", stop, cold,
                                "model shape %r unusable" % shape)
        return self._record(op_id, arm, task_id, repeat, probe, exposure,
                            usage, "model-shape", stop, shape,
                            (parsed or {}).get("rationale", ""), text=text)

    def _record(self, op_id: str, arm: str, task_id: str, repeat: int,
                probe: str | None, exposure: int, usage: dict, outcome: str,
                stop: str | None, shape: str, rationale: str,
                text: str | None = None) -> dict:
        template_used = arm == "warm-T" and self.template_record is not None
        applied = {"applicable": False}
        if template_used:
            applied = template.apply_template(self.template_record, task_id)
        changed = bool(applied.get("applicable")) and shape != _cold_shape(
            task_id)
        call = {"operation_id": op_id, "arm": arm, "task_id": task_id,
                "repeat": repeat, "probe": probe, "exposure": exposure,
                "usage": dict(usage), "outcome": outcome,
                "stop_reason": stop or "", "shape": shape,
                "text_chars": len(text or "")}
        self.calls.append(call)
        kinds = _kinds(arm, task_id, shape, probe)
        return {"shape": shape, "kinds": kinds,
                "costs": {"in": usage["in"], "out": usage["out"], "tools": 0,
                          "calls": 1},
                "template_used": template_used,
                "template_changed_decision": changed, "simulated": False,
                "live_source": "model" if outcome == "model-shape"
                else "fallback",
                "policy_rationale": rationale,
                "kinds_source": "apparatus-overlay"}


def seed_campaign(dsn: str, tag: str, envelope: dict,
                  evidence_root, charter_name: str = "charter.json") -> dict:
    allocation_id = "%s-live-root" % tag
    cmd = Command(request_id="%s-campaign-seed" % tag,
                  payload={"allocation_id": allocation_id, "domain": "cpu",
                           "authorized": envelope["grant_authorized"],
                           "max_occupancy": 16})
    try:
        store.seed_allocation(dsn, cmd)
    except SettlementError as exc:
        if "already exists" not in str(exc):
            raise
        status = store.allocation_status(dsn, allocation_id)
        if int(status["authorized"]) != envelope["grant_authorized"]:
            raise SettlementError("campaign grant mismatch: have %s want %s"
                                  % (status["authorized"],
                                     envelope["grant_authorized"]))
    charter = {"charter": "LIVE-03-07 Team 01 live campaign",
               "tag": tag, "allocation_id": allocation_id,
               "model": envelope["model"], "endpoint": ENDPOINT,
               "api": API, "envelope": envelope,
               "note": "planner model-inference reserves against this root;"
                       " per-episode child work uses per-episode roots",
               "at": _utcnow()}
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / charter_name).write_text(json.dumps(charter, indent=2))
    return charter


def _build_ledger(evidence_root) -> Path:
    return Path(evidence_root) / "template-builds.json"


def _read_builds(evidence_root) -> list:
    path = _build_ledger(evidence_root)
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return []


def build_live_template(dsn: str, gateway, dev_records: list, evidence_root,
                        *, allocation_id: str, tag: str,
                        model: str = MODEL) -> dict:
    prior = _read_builds(evidence_root)
    if len(prior) >= template.MAX_BUILDS:
        raise SettlementError("at most %d template builds" % template.MAX_BUILDS)
    wins = sum(1 for r in dev_records if r.get("outcome") == "success")
    public_failures = sum(r.get("public", {}).get("failed", 0)
                          for r in dev_records)
    known = sorted({r["episode_id"] for r in dev_records
                    if r.get("probe") == "incompatible"
                    and r.get("outcome") == "failure"})
    prompt = "\n".join([
        "Pick one coordination-template build from development evidence.",
        "dev episodes=%d wins=%d public-failures=%d known-failures=%s"
        % (len(dev_records), wins, public_failures, json.dumps(known)),
        "builds: %s" % json.dumps(
            [{"id": spec["id"], "directive": spec["directive"],
              "shape": spec["shape"],
              "boundary_probe": spec["boundary_probe"]}
             for spec in template.BUILDS]),
        'Reply with JSON only: {"build": "<id>", "rationale": "<why>"}.'])
    op_id = "%s-tmpl-%d" % (tag, len(prior))
    ensured = broker.ensure_operation(
        dsn, operation_id=op_id, effect=broker.MODEL_INFERENCE,
        payload={"model": model,
                 "messages": [{"role": "user", "content": prompt}],
                 "max_output_tokens": 256, "deadline_ms": DEADLINE_MS,
                 "reasoning_effort": EFFORT},
        allocation_id=allocation_id, retries=RETRIES)
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError("template build ensure refused: %s"
                              % ensured.detail)
    broker.dispatch_operation(dsn, op_id, gateway=gateway)
    text = ""
    for receipt in _receipt_contents(dsn, op_id):
        content = dict(receipt.get("content") or {})
        if receipt.get("outcome") == "success" and "text" in content:
            text = content["text"]
            break
    pick = (_parse_envelope(text) or {}).get("build", "")
    candidates = template.build_candidates(dev_records)
    by_id = {c["id"]: c for c in candidates}
    if pick in by_id:
        winner = by_id[pick]
        source = "model"
        rationale = (_parse_envelope(text) or {}).get("rationale", "")
        frozen_out = [{"id": c["id"],
                       "reason": "model-selected %s: %s" % (
                           winner["id"], rationale or "no rationale")}
                      for c in candidates if c["id"] != winner["id"]]
    else:
        winner, frozen_out = template.select_candidate(candidates,
                                                       dev_records)
        source = "fallback-dev-ranking"
        rationale = "model pick %r unusable; dev ranking kept" % pick
    frozen = template.freeze_template(evidence_root, winner=winner,
                                      frozen_out=frozen_out, builds=[winner])
    prior.append({"tag": tag, "operation_id": op_id, "model_pick": pick,
                  "winner": winner["id"], "live_source": source,
                  "rationale": rationale, "at": _utcnow()})
    _build_ledger(evidence_root).write_text(json.dumps(prior, indent=2))
    frozen["live_source"] = source
    frozen["live_rationale"] = rationale
    return frozen


def _submit_node(dsn: str, plan_id: str, task_id: str, snapshot: dict,
                 shape: str, node: str, kind: str, receipts: dict) -> None:
    files = dict(snapshot) if kind == "broken" else panel._tree_files(
        task_id, kind)
    if shape == "decompose":
        owned = next(c["owned_paths"] for c in
                     team.plan_summary(dsn, plan_id)["children"]
                     if c["node_id"] == node)
        files = {path: files[path] for path in owned}
    reg = team.register_output(dsn, panel._cmd(), dict(files))
    if reg.code != ResultCode.APPLIED:
        raise SettlementError("output refused: %s" % reg.detail)
    attempt = team.child_attempt(dsn, plan_id, node)
    result = team.submit_child(
        dsn, panel._cmd({"plan_id": plan_id}), plan_revision=1, node_id=node,
        input_digests=team.expected_inputs(dsn, plan_id, node),
        ownership_generation=attempt["ownership_generation"],
        output_digest=reg.data["output_digest"],
        receipt_refs=receipts[node])
    if result.code != ResultCode.APPLIED:
        raise SettlementError("submit refused: %s" % result.detail)


def continuity_stage_a(dsn: str, *, tag: str, task_id: str, runs_root,
                       state_path, gateway=None,
                       planner=None) -> dict:
    register.ensure_foundation(dsn)
    seed = panel._seed(dsn, "%s-cont" % tag)
    snapshot = panel._snapshot(task_id)
    snap = team.register_snapshot(dsn, panel._cmd(), dict(snapshot))
    if snap.code != ResultCode.APPLIED:
        raise SettlementError("snapshot refused: %s" % snap.detail)
    family = oracle.TASK_FAMILY[task_id]
    shape = "decompose"
    rationale = "continuity probe forces two owners"
    if planner is not None:
        decision = planner.propose("T", task_id, 1, "continuity")
        if decision["shape"] == "decompose":
            rationale = "live planner chose decompose"
    elif gateway is not None:
        probe_planner = LivePlanner(dsn, gateway, allocation_id=seed[
            "allocation_id"], model=MODEL, tag="%s-cont" % tag)
        decision = probe_planner.propose("T", task_id, 1, "continuity")
        if decision["shape"] == "decompose":
            rationale = "live planner chose decompose"
    launchers = {"local-process": LocalLauncher(str(runs_root))}
    proposed = team.propose_team_plan(
        dsn, panel._cmd(), parent_obligation="%s:repair %s" % (
            seed["investigation_id"], task_id),
        snapshot_digest=snap.data["snapshot_digest"], shape=shape,
        children=panel._children(shape, snapshot, family),
        interface_contract={"shapes": [shape], "new_paths": []},
        join_rules=panel._join_rules(shape, task_id),
        allocation_id=seed["allocation_id"],
        policy_response={"shape": shape, "rationale": rationale})
    if proposed.code != ResultCode.APPLIED:
        raise SettlementError("plan refused: %s" % proposed.detail)
    plan_id = proposed.data["plan_id"]
    receipts = panel._dispatch(dsn, plan_id, launchers)
    _submit_node(dsn, plan_id, task_id, snapshot, shape, "w1", "valid",
                 receipts)
    state = {"plan_id": plan_id, "task_id": task_id, "family": family,
             "allocation_id": seed["allocation_id"],
             "investigation_id": seed["investigation_id"],
             "snapshot_digest": snap.data["snapshot_digest"],
             "submitted": ["w1"], "pending": ["w2"], "tag": tag,
             "at": _utcnow()}
    target = Path(state_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, indent=2))
    return state


def continuity_stage_b(dsn: str, *, state_path, runs_root,
                       evidence_root=None, tag: str = "team01",
                       gateway=None) -> dict:
    state = json.loads(Path(state_path).read_bytes())
    plan_id = state["plan_id"]
    team.submission_tuple(dsn, plan_id, 1, "w1")
    try:
        team.submission_tuple(dsn, plan_id, 1, "w2")
        pending = []
    except LookupError:
        pending = ["w2"]
    task_id = state["task_id"]
    snapshot = panel._snapshot(task_id)
    launchers = {"local-process": LocalLauncher(str(runs_root))}
    resubmitted: list = []
    receipts = {}
    for node in team.child_nodes(dsn, plan_id):
        op_id = team.child_operation(dsn, plan_id, node)
        receipts[node] = [r["receipt_identity"]
                          for r in store.operation_receipts(dsn, op_id)]
    for node in pending:
        _submit_node(dsn, plan_id, task_id, snapshot, "decompose", node,
                     "valid", receipts)
    joined = team.assemble_and_join(dsn, panel._cmd(), plan_id=plan_id,
                                    launchers=launchers)
    join = team.join_record(dsn, plan_id, 1) if joined.data.get(
        "candidate_digest") else {"passed": False, "candidate_digest": "",
                                  "join_receipt": "",
                                  "check_operation": joined.data.get(
                                      "check_operation", "")}
    frozen_digest = None
    if joined.code == ResultCode.APPLIED:
        frozen = team.freeze_candidate(
            dsn, panel._cmd(), plan_id=plan_id,
            candidate_digest=joined.data["candidate_digest"])
        if frozen.code == ResultCode.APPLIED:
            frozen_digest = frozen.data["frozen_candidate"]
    final = panel._final_tree_real(dsn, plan_id, task_id, snapshot,
                                   "decompose", {"w1": "valid",
                                                 "w2": "valid"},
                                   joined.data.get("candidate_digest", ""))
    import tempfile

    with tempfile.TemporaryDirectory(prefix="team01-cont-") as tmp:
        src = panel._materialize(final, Path(tmp) / "tree")
        public = oracle.evaluate_tree(src, oracle.public_cases(task_id))
        protected = oracle.evaluate_tree(src, oracle.protected_cases(task_id))
    solved = bool(frozen_digest) and protected["failed"] == 0
    record = {"episode_id": "continuity-T-%s" % task_id, "panel": "continuity",
              "arm": "T", "task_id": task_id, "repeat": 1,
              "family": state["family"], "probe": "continuity",
              "plan_id": plan_id, "revision": 1, "shape": "decompose",
              "snapshot_digest": state["snapshot_digest"],
              "outcome": "success" if solved else "failure",
              "public": public, "protected": protected,
              "join": {"passed": bool(join.get("passed")),
                       "join_receipt": join.get("join_receipt", ""),
                       "check_operation": join.get("check_operation", ""),
                       "candidate_digest": join.get("candidate_digest", "")},
              "frozen_digest": frozen_digest, "resumed": True,
              "resubmitted": resubmitted, "simulated": gateway is None,
              "at": _utcnow()}
    if evidence_root is not None:
        root = Path(evidence_root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "continuity-probe.json").write_text(
            json.dumps(record, indent=2))
    return record


def reconcile_campaign(dsn: str, op_ids: list,
                       allocation_id: str | None = None) -> dict:
    from settlement import db
    from psycopg.rows import dict_row

    per_op: list = []
    reserved = consumed = retained = timeouts = refusals = empty = 0
    tokens_in = tokens_out = 0
    for op_id in op_ids:
        if not op_id:
            continue
        row = broker.read_operation(dsn, op_id)
        if row is None:
            per_op.append({"operation_id": op_id, "status": "missing"})
            continue
        receipts = _receipt_contents(dsn, op_id)
        amount, state = 0, ""
        with db.connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT amount, state FROM reservations"
                            " WHERE id = %s", ("res-%s" % op_id,))
                found = cur.fetchone()
                conn.commit()
        if found is not None:
            amount, state = int(found["amount"]), str(found["state"])
        spent = amount if state == "settled" else 0
        held = 0 if state == "settled" else amount
        reserved += amount
        consumed += spent
        retained += held
        usage = {"in": 0, "out": 0}
        error = ""
        for receipt in receipts:
            content = dict(receipt.get("content") or {})
            if receipt.get("outcome") == "success" and "usage" in content:
                raw = dict(content["usage"])
                usage = {"in": int(raw.get("input_tokens", 0) or 0),
                         "out": int(raw.get("output_tokens", 0) or 0)}
            if receipt.get("outcome") == "unknown" and content.get("error"):
                error = str(content["error"])
        tokens_in += usage["in"]
        tokens_out += usage["out"]
        kind = _classify_error(error) if error else ""
        if kind == "timeout":
            timeouts += 1
        if kind in ("auth", "rate_limit"):
            refusals += 1
        if kind == "empty-output":
            empty += 1
        per_op.append({"operation_id": op_id,
                       "dispatch_state": row["dispatch_state"],
                       "reservation": state or "none", "reserved": amount,
                       "consumed": spent, "retained": held, "usage": usage,
                       "error": error})
    missing = sum(1 for entry in per_op if entry.get("status") == "missing")
    bare = sum(1 for op_id in op_ids if op_id
               and not store.operation_receipts(dsn, op_id))
    balance = None
    if allocation_id is not None:
        status = store.allocation_status(dsn, allocation_id)
        balance = {"authorized": int(status["authorized"]),
                   "consumed": int(status["consumed"]),
                   "reserved": int(status["reserved"]),
                   "balance": int(status["authorized"])
                   - int(status["consumed"]) - int(status["reserved"])}
    return {"operations": len(op_ids), "reserved": reserved,
            "consumed": consumed, "retained": retained,
            "unresolved": reserved - consumed - retained,
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "timeouts": timeouts, "refusals": refusals, "empty": empty,
            "missing": missing,
            "without_receipt": bare,
            "agreement": missing == 0 and bare == 0
            and reserved == consumed + retained,
            "grant": balance, "operations_detail": per_op, "at": _utcnow()}


def run_live_episode(dsn: str, *, task_id: str, arm: str, repeat: int,
                     runs_root, panel_name: str, evidence_root,
                     tag: str, template_record=None, probe: str | None = None,
                     planner) -> dict:
    before = len(planner.calls)
    record = panel.run_episode(
        dsn, task_id=task_id, arm=arm, repeat=repeat, runs_root=runs_root,
        panel_name=panel_name, evidence_root=evidence_root, tag=tag,
        template=template_record, probe=probe, planner=planner)
    fresh = planner.calls[before:]
    path = Path(evidence_root) / "episodes" / ("%s.json"
                                               % record["episode_id"])
    record["live"] = {"planner_operations": [call["operation_id"]
                                             for call in fresh],
                      "calls": fresh}
    path.write_text(json.dumps(record, indent=2))
    return record


def run_live_development(dsn: str, *, evidence_root, runs_root, tag: str,
                         planner, ledger: BudgetLedger) -> list:
    records = []
    for task_id in oracle.SPLITS["development"]:
        for probe in DEV_PROBES:
            ledger.spend("dev_episodes")
            records.append(run_live_episode(
                dsn, task_id=task_id, arm="T", repeat=1, runs_root=runs_root,
                panel_name="dev", evidence_root=evidence_root, tag=tag,
                probe=probe, planner=planner))
    panel._write_index(evidence_root, records)
    return records


def run_live_comparison(dsn: str, *, evidence_root, runs_root, tag: str,
                        planner, ledger: BudgetLedger,
                        template_record=None) -> dict:
    records = [run_live_episode(
        dsn, task_id=task_id, arm=arm, repeat=repeat, runs_root=runs_root,
        panel_name="eval", evidence_root=evidence_root, tag=tag,
        template_record=template_record, planner=planner)
        for arm in panel.ARMS for task_id in oracle.SPLITS["evaluation"]
        for repeat in panel.REPEATS
        for _ in [ledger.spend("eval_episodes")]]
    if len(records) != 48:
        raise SettlementError("eval panel needs 48 episodes, have %d"
                              % len(records))
    return {"records": records,
            "index": str(panel._write_index(evidence_root, records))}


def run_live_transfer(dsn: str, *, evidence_root, runs_root, tag: str,
                      planner, ledger: BudgetLedger,
                      template_record=None) -> dict:
    records = [run_live_episode(
        dsn, task_id=task_id, arm=arm, repeat=repeat, runs_root=runs_root,
        panel_name="transfer", evidence_root=evidence_root, tag=tag,
        template_record=template_record, planner=planner)
        for arm in panel.TRANSFER_MODES
        for task_id in oracle.SPLITS["transfer"] for repeat in panel.REPEATS
        for _ in [ledger.spend("transfer_episodes")]]
    if len(records) != 24:
        raise SettlementError("transfer panel needs 24 episodes, have %d"
                              % len(records))
    return {"records": records,
            "index": str(panel._write_index(evidence_root, records))}


def summarize_verdicts(evidence_root, dsn: str = "") -> dict:
    report = checker_mod.check_all(evidence_root, dsn=dsn)
    return report


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Team 01 live driver")
    parser.add_argument("command", choices=(
        "measure", "seed", "dev", "build-template", "eval", "transfer",
        "continuity-a", "continuity-b", "reconcile", "check"))
    parser.add_argument("--dsn", default="")
    parser.add_argument("--tag", default="team01-live")
    parser.add_argument("--evidence-root", default="")
    parser.add_argument("--runs-root", default="")
    parser.add_argument("--task", default="team01-t05")
    parser.add_argument("--state", default="")
    args = parser.parse_args(argv)
    dsn = args.dsn or os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        print("need --dsn or SETTLEMENT_TEST_DSN")
        return 2
    evidence = Path(args.evidence_root or "evidence")
    runs = Path(args.runs_root or str(evidence))
    if args.command == "measure":
        gateway = make_gateway()
        alloc = "%s-measure" % args.tag
        try:
            store.seed_allocation(dsn, Command(
                request_id="%s-measure-seed" % args.tag,
                payload={"allocation_id": alloc, "domain": "cpu",
                         "authorized": 100000, "max_occupancy": 16}))
        except SettlementError as exc:
            if "already exists" not in str(exc):
                raise
        planner = LivePlanner(dsn, gateway, allocation_id=alloc,
                              model=MODEL, tag="%s-m" % args.tag)
        decision = planner.propose("T", args.task, 1, "diagnostic")
        call = planner.calls[0]
        envelope = size_campaign_envelope(call["exposure"])
        print(json.dumps({"decision": decision["shape"],
                          "live_source": decision["live_source"],
                          "exposure": call["exposure"],
                          "usage": call["usage"], "envelope": envelope},
                         indent=2))
        return 0
    if args.command == "check":
        print(json.dumps(summarize_verdicts(evidence, dsn), indent=2,
                         sort_keys=True, default=str)[:4000])
        return 0
    print("driver command %r runs inside the campaign runner" % args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
