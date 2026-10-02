"""D-EP episode-core (DEV-01..DEV-04, episode half of DEV-09).

One caller-admitted development episode over durable primitives. The record
lives in PostgreSQL (``development_episodes``) and every lifecycle step
commits through :func:`settlement.store.transact`, so the command journal
binds request identity and domain events carry the version/exposure trace.
Investigations hold the continuing identity, artifacts/capabilities hold
candidate bytes, trials hosts the frozen development ledger, and the broker
admits every model and sandbox effect. No second workflow engine: this
module issues domain transitions and broker operations only.

Lifecycle (LEARNING-MODEL §4, episode side; compare/dispose/use are owned
by the compare lane consuming the bindings)::

    observed -> proposed -> admitted -> diagnosed
        -> constructed -> checked -> selected -> bound

Seed ceilings: at most 2 explanations, 1 diagnostic probe, 2 constructed
candidate versions; a revision consumes one of the 2 candidate slots.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from . import artifacts, broker, capabilities, context, db, evidence, experiment, store, trials
from .common import Command, CommandResult, ResultCode, SettlementError

CEIL_EXPLANATIONS = 2
CEIL_PROBES = 1
CEIL_CANDIDATES = 2

PACKET_BUDGET = {"input_chars": 24000, "output_reserve": 2000}


def packet_budget() -> dict:
    raw = os.environ.get("SETTLEMENT_PACKET_BUDGET_CHARS", "")
    if not raw:
        return dict(PACKET_BUDGET)
    try:
        chars = int(raw)
    except ValueError:
        raise SettlementError(f"SETTLEMENT_PACKET_BUDGET_CHARS={raw!r} is not an integer")
    if chars <= 0:
        raise SettlementError(
            f"SETTLEMENT_PACKET_BUDGET_CHARS={raw!r} must be a positive integer")
    return {"input_chars": chars, "output_reserve": PACKET_BUDGET["output_reserve"]}

STATES = ("observed", "proposed", "admitted", "diagnosed",
          "constructed", "checked", "selected", "bound")

_JSON_FIELDS = ("trigger_refs", "access_policy", "explanations",
                "intervention", "probe_ops", "candidates",
                "comparison_policy", "checks", "selection", "bindings")

METHOD_ABI = {
    "staged_as": "method.py",
    "companion": "broken.py",
    "invoke": "python method.py <in-dir>/broken.py <out-dir>/fixed.py",
    "reads": "broken source from input_path argv[1]",
    "writes": "fixed source to output_path argv[2], read back as fixed.py",
    "selftest": "argv ['--selftest'] exits 0 printing typed JSON {status: ok}",
    "effects": "sandbox-only",
    "shape": "reusable file-to-file procedure,"
             " never the repaired task function",
}

RESPONSE_FORMAT = (
    "Respond with raw JSON only: no prose, no commentary. "
    "A single ```json fenced block with nothing outside it is tolerated. "
    "Prose around the block, multiple blocks, or non-JSON output is invalid. "
    "A deliberate abstention stays honest: construct returns "
    '{"no_candidate": "<reason>"} and consumes no candidate slot.'
)


def _single_fence(stripped: str) -> str | None:
    if len(stripped) < 6 or not stripped.startswith("```") \
            or not stripped.endswith("```"):
        return None
    inner = stripped[3:-3]
    if "```" in inner:
        return None
    text = inner.strip()
    if not text:
        return None
    head, sep, tail = text.partition("\n")
    if sep:
        if head.strip().lower() not in ("json", "jsonc"):
            return None
        return tail.strip()
    if text.lower().startswith("json") and text[4:5] in \
            ("", " ", "\t", "{", "["):
        return text[4:].strip()
    return text


def _parse_envelope(text: str | None) -> Any:
    try:
        return json.loads(text or "")
    except ValueError:
        pass
    fenced = _single_fence((text or "").strip())
    if fenced is None:
        return None
    try:
        return json.loads(fenced)
    except ValueError:
        return None


def _j(value: Any) -> Json:
    return Json(value if value is not None else {})


def get_episode(dsn: str, episode_id: str) -> dict | None:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM development_episodes WHERE id = %s",
                        (episode_id,))
            row = cur.fetchone()
            conn.commit()
    if row is None:
        return None
    out = dict(row)
    for field in _JSON_FIELDS:
        value = out.get(field)
        out[field] = dict(value) if isinstance(value, dict) else (
            list(value) if isinstance(value, list) else value)
    return out


def _require_episode(dsn: str, episode_id: str) -> dict:
    episode = get_episode(dsn, episode_id)
    if episode is None:
        raise SettlementError(f"unknown development episode {episode_id}")
    return episode


def dev_protocol_id(episode_id: str) -> str:
    return f"{episode_id}-dev"


def panel_protocol_id(episode_id: str) -> str:
    return f"{episode_id}-panel"


def eval_protocol_id(episode_id: str) -> str:
    return f"{panel_protocol_id(episode_id)}-eval"


def panel_policy_for(dev_ids: list[str], panel_ids: list[str],
                     transfer_ids: list[str], *, families: list[str],
                     evaluator_version: str = "v1") -> dict:
    groups = [
        {"name": "development", "kind": "development",
         "tasks": list(dev_ids)},
        {"name": "panel", "kind": "visible-regression",
         "tasks": list(panel_ids)},
        {"name": "transfer", "kind": "visible-regression",
         "tasks": list(transfer_ids)},
        {"name": "protected-eval", "kind": "protected-eval",
         "evaluator_version": evaluator_version},
    ]
    return {
        "task_groups": groups,
        "access": {"families": sorted(set(families))},
        "outcomes": {"metrics": ["success_rate"],
                     "grades": ["success", "failure"]},
        "thresholds": {"release_label": "observed-gain"},
        "stopping": {"rule": "fixed-panel"},
        "release": {"fallback": "baseline-v0",
                    "quarantine_excludes": True},
        "evaluator_version": evaluator_version,
    }


def _norm_groups(groups: Any) -> list[tuple]:
    rows = []
    for group in groups or []:
        if not isinstance(group, dict):
            raise SettlementError("panel policy groups must be objects")
        rows.append((group.get("name", ""), group.get("kind", ""),
                     tuple(group.get("tasks") or [])))
    return sorted(rows)


def _applied(result: CommandResult, what: str) -> CommandResult:
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise SettlementError(
            f"{what} refused: {result.code.value}: {result.detail}")
    return result


def _step(dsn: str, cmd: Command, episode_id: str, expect: tuple[str, ...],
          nxt: str | None, patch: dict, kind: str) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT state FROM development_episodes WHERE id = %s",
                    (episode_id,))
        row = cur.fetchone()
        if row is None:
            raise SettlementError(f"unknown development episode {episode_id}")
        if row["state"] not in expect:
            raise SettlementError(
                f"episode {episode_id} is {row['state']},"
                f" needs one of {sorted(expect)}")
        sets = []
        args: list[Any] = []
        for key, value in patch.items():
            sets.append(f"{key} = %s")
            args.append(_j(value) if isinstance(value, (dict, list)) else value)
        if nxt is not None:
            sets.append("state = %s")
            args.append(nxt)
        sets.append("updated_at = now()")
        args.append(episode_id)
        cur.execute("UPDATE development_episodes SET " + ", ".join(sets)
                    + " WHERE id = %s", args)
        state = nxt if nxt is not None else row["state"]
        return (ResultCode.APPLIED,
                f"episode {episode_id} now {state}",
                {"episode_id": episode_id, "state": state},
                [(kind, {"episode_id": episode_id, "state": state})], [])
    return _applied(store.transact(dsn, cmd, _fn),
                    f"episode {episode_id} transition")


def _dev_groups() -> list[dict]:
    return [{"name": "development", "kind": "development"},
            {"name": "protected-eval", "kind": "protected-eval"}]


def observe(dsn: str, cmd: Command, *, episode_id: str,
            investigation_id: str, trigger_refs: list[dict],
            bottleneck: str = "") -> CommandResult:
    if not episode_id:
        raise SettlementError("an episode needs an id")
    if not isinstance(trigger_refs, list) or not trigger_refs or not all(
            isinstance(ref, dict) and ref.get("task_id") for ref in trigger_refs):
        raise SettlementError(
            "admission needs non-empty trigger experience refs with task ids")

    def _fn(cur, control):
        cur.execute("SELECT 1 FROM investigations WHERE id = %s",
                    (investigation_id,))
        if cur.fetchone() is None:
            raise SettlementError(f"unknown investigation {investigation_id}")
        cur.execute("SELECT 1 FROM development_episodes WHERE id = %s",
                    (episode_id,))
        if cur.fetchone() is not None:
            raise SettlementError(f"episode {episode_id} already exists")
        cur.execute(
            "INSERT INTO development_episodes (id, investigation_id,"
            " trigger_refs, bottleneck, state, disposition)"
            " VALUES (%s, %s, %s, %s, 'observed', 'open')",
            (episode_id, investigation_id, _j(trigger_refs), bottleneck))
        return (ResultCode.APPLIED, f"episode {episode_id} observed",
                {"episode_id": episode_id, "state": "observed"},
                [("development.episode_observed",
                  {"episode_id": episode_id,
                   "triggers": [ref["task_id"] for ref in trigger_refs]})], [])
    return _applied(store.transact(dsn, cmd, _fn),
                    f"episode {episode_id} observe")


def propose(dsn: str, cmd: Command, *, episode_id: str,
            predicted_effect: str = "", competing: str = "",
            uncertainty: str = "") -> CommandResult:
    if not predicted_effect and not uncertainty:
        raise SettlementError(
            "a proposal needs a predicted intervention effect"
            " or explicit uncertainty")
    return _step(dsn, cmd, episode_id, ("observed",), "proposed",
                 {"predicted_effect": predicted_effect,
                  "intervention": {"competing": competing,
                                   "uncertainty": uncertainty}},
                 "development.episode_proposed")


def admit(dsn: str, cmd: Command, *, episode_id: str,
          reference_version: str, access_policy: dict,
          allocation_id: str, max_explanations: int = CEIL_EXPLANATIONS,
          max_probes: int = CEIL_PROBES,
          max_candidates: int = CEIL_CANDIDATES,
          panel_policy: dict | None = None) -> CommandResult:
    if not reference_version:
        raise SettlementError("admission needs a reference version")
    if not isinstance(access_policy, dict) or not access_policy:
        raise SettlementError("admission needs a non-empty access policy")
    for name, value, ceil in (("explanations", max_explanations, CEIL_EXPLANATIONS),
                              ("probes", max_probes, CEIL_PROBES),
                              ("candidates", max_candidates, CEIL_CANDIDATES)):
        if not isinstance(value, int) or value < 0 or value > ceil:
            raise SettlementError(
                f"{name} limit {value!r} outside seed bounds 0..{ceil}")

    def _fn(cur, control):
        cur.execute("SELECT state FROM development_episodes WHERE id = %s",
                    (episode_id,))
        row = cur.fetchone()
        if row is None:
            raise SettlementError(f"unknown development episode {episode_id}")
        if row["state"] != "proposed":
            raise SettlementError(
                f"episode {episode_id} is {row['state']}, needs proposed")
        cur.execute("SELECT authorized FROM allocations WHERE id = %s",
                    (allocation_id,))
        alloc = cur.fetchone()
        if alloc is None:
            raise SettlementError(f"unknown allocation {allocation_id}")
        if int(alloc["authorized"]) <= 0:
            raise SettlementError(
                f"allocation {allocation_id} admits no finite ceiling")
        cur.execute(
            "UPDATE development_episodes SET state = 'admitted',"
            " reference_version = %s, access_policy = %s, allocation_id = %s,"
            " max_explanations = %s, max_probes = %s, max_candidates = %s,"
            " development_protocol_id = %s, updated_at = now() WHERE id = %s",
            (reference_version, _j(access_policy), allocation_id,
             max_explanations, max_probes, max_candidates,
             dev_protocol_id(episode_id), episode_id))
        if panel_policy is not None:
            if not isinstance(panel_policy, dict) or not panel_policy.get("task_groups"):
                raise SettlementError(
                    "admission panel policy needs task groups")
            _norm_groups(panel_policy["task_groups"])
            cur.execute(
                "UPDATE development_episodes SET comparison_policy = %s,"
                " updated_at = now() WHERE id = %s",
                (_j({"panel_protocol": panel_protocol_id(episode_id),
                     "panel": panel_policy}), episode_id))
        return (ResultCode.APPLIED, f"episode {episode_id} admitted",
                {"episode_id": episode_id, "state": "admitted"},
                [("development.episode_admitted",
                  {"episode_id": episode_id,
                   "reference_version": reference_version,
                   "allocation_id": allocation_id})], [])
    result = _applied(store.transact(dsn, cmd, _fn),
                        f"episode {episode_id} admit")
    if result.code in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        episode = _require_episode(dsn, episode_id)
        trials.freeze_protocol(
            dsn, Command(request_id=f"devproto-{episode_id}", payload={}),
            protocol_id=dev_protocol_id(episode_id),
            candidate_version="", reference_version=episode["reference_version"],
            evaluator_version="", task_groups=_dev_groups(),
            budgets={}, metrics=["success_rate"], stopping={}, exclusions=[],
            uncertainty={})
        frozen = episode.get("comparison_policy") or {}
        if frozen.get("panel_protocol") and frozen.get("panel"):
            panel = frozen["panel"]
            trials.freeze_protocol(
                dsn, Command(request_id=f"devpanel-{episode_id}", payload={}),
                protocol_id=panel_protocol_id(episode_id),
                candidate_version="",
                reference_version=episode["reference_version"],
                evaluator_version=str(panel.get("evaluator_version", "")),
                task_groups=panel["task_groups"],
                budgets={"per_task_sandbox_ms": experiment.GRADER_TIMEOUT_MS,
                         "per_task_tokens": experiment.MODEL_TOKENS},
                metrics=["success_rate"], stopping=dict(panel.get("stopping", {})),
                exclusions=[], uncertainty={"treatment": "finite-panel-only"},
                supported_scope=dict(panel.get("access", {})))
    return result


def _collect_task(dsn: str, episode: dict, adapter: Any, launcher: Any,
                  model: str, task: dict, grader_path: str,
                  allocation_id: str, investigation_id: str,
                  transcripts: dict, claims: list) -> None:
    episode_id = episode["id"]
    task_id = str(task["id"])
    tag = f"{episode_id}-exp-{task_id}"
    attempt_id = experiment._fresh_worker(
        dsn, tag=tag, investigation_id=investigation_id,
        allocation_id=allocation_id)
    infer_op = f"{tag}-infer"
    _, text, _ = experiment._infer_via_broker(
        dsn, adapter, operation_id=infer_op, model=model,
        prompt=json.dumps({"arm": "DEV", "task_id": task_id,
                           "prompt": task["broken"],
                           "response_contract":
                               experiment.SOLVER_SOURCE_CONTRACT}),
        allocation_id=allocation_id, attempt_id=attempt_id)
    experiment._settle_costs(dsn, [dev_protocol_id(episode_id)], infer_op,
                             "construction",
                             f"experience inference {episode_id} {task_id}")
    validation, grade_op, staged = experiment.begin_solver_grade(
        dsn, launcher, model_op=infer_op, raw=text, cases=task["cases"],
        tag=tag, allocation_id=allocation_id, attempt_id=attempt_id,
        grader_path=grader_path)
    finished = experiment.finish_solver_grade(
        dsn, launcher, grade_op, len(task["cases"]), staged)
    outcome = finished["outcome"]
    experiment._settle_costs(dsn, [dev_protocol_id(episode_id)], grade_op,
                             "construction" if outcome == "success"
                             else "failed_trials",
                             f"experience grade {episode_id} {task_id}")
    obs = evidence.register_observation(
        dsn, Command(request_id=f"{tag}-obs", payload={}), attempt_id,
        {"task_id": task_id, "family": task.get("family", ""),
         "outcome": outcome, "grade_op": grade_op, "model_op": infer_op},
        source_identity=f"dev-batch-grade:{grade_op}")
    receipt_id = obs.data["receipt_id"]
    claim_id = f"{tag}-claim"
    evidence.propose_claim(
        dsn, Command(request_id=f"{tag}-claim", payload={}), claim_id,
        {"task_id": task_id, "family": task.get("family", ""),
         "broken": task["broken"], "cases": task["cases"],
         "model_text": (text or "")[:2000], "outcome": outcome,
         "solver_status": validation["status"],
         "grade_class": finished["grade_class"],
         "grade_op": grade_op, "model_op": infer_op},
        scope={"episode": episode_id,
               "family": task.get("family", "")},
        access_label="candidate")
    evidence.admit_warrant(
        dsn, Command(request_id=f"{tag}-warrant", payload={}),
        f"{tag}-warrant", claim_id, "dev-batch-grade", "v1",
        [[(receipt_id, "observation")]],
        scope={"episode": episode_id})
    claims.append(claim_id)
    transcripts[task_id] = {
        "task_id": task_id, "family": task.get("family", ""),
        "broken": task["broken"], "model_text": text, "outcome": outcome,
        "model_op": infer_op, "grade_op": grade_op,
        "solver_status": validation["status"],
        "grade_class": finished["grade_class"]}


def collect_experience(dsn: str, cmd: Command, adapter: Any,
                       launcher: Any, *, episode_id: str, model: str,
                       dev_tasks: list[dict], grader_path: str) -> dict:
    episode = _require_episode(dsn, episode_id)
    if episode["state"] != "admitted":
        raise SettlementError(
            f"episode {episode_id} is {episode['state']},"
            " experience collects in admitted before diagnosis")
    if not isinstance(dev_tasks, list) or not dev_tasks or not all(
            isinstance(t, dict) and t.get("id") and t.get("broken") is not None
            and isinstance(t.get("cases"), list) for t in dev_tasks):
        raise SettlementError(
            f"episode {episode_id} experience needs tasks with broken code and cases")
    trigger_ids = [ref["task_id"] for ref in episode["trigger_refs"]]
    if sorted(t["id"] for t in dev_tasks) != sorted(trigger_ids):
        raise SettlementError(
            f"episode {episode_id} experience batch must cover exactly"
            " the admitted trigger tasks")
    allocation_id = episode["allocation_id"]
    investigation_id = episode["investigation_id"]
    transcripts: dict[str, dict] = {}
    claims: list[str] = []
    try:
        for task in dev_tasks:
            _collect_task(dsn, episode, adapter, launcher, model, task,
                          grader_path, allocation_id, investigation_id,
                          transcripts, claims)
    except SettlementError as exc:
        if _refused_before_dispatch(exc):
            _mark(dsn, episode_id, "budget-exhausted",
                  "development.episode-budget-exhausted")
        raise

    linked = {task["id"]: claim for task, claim in zip(dev_tasks, claims)}
    refs = [dict(ref, claim_id=linked[str(ref.get("task_id"))])
            if str(ref.get("task_id")) in linked else dict(ref)
            for ref in episode["trigger_refs"]]

    def _fn(cur, control):
        cur.execute("UPDATE development_episodes SET trigger_refs = %s,"
                    " updated_at = now() WHERE id = %s", (_j(refs), episode_id))
        return (ResultCode.APPLIED,
                f"episode {episode_id} experience collected",
                {"episode_id": episode_id, "claims": claims},
                [("development.experience_collected",
                  {"episode_id": episode_id, "claims": claims})], [])
    _applied(store.transact(dsn, cmd, _fn),
             f"episode {episode_id} experience")
    return {"episode_id": episode_id, "state": "admitted",
            "transcripts": transcripts, "claims": claims,
            "trigger_refs": refs}


def _gateway_receipt(dsn: str, operation_id: str) -> dict | None:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT outcome, content FROM receipts"
                        " WHERE operation_id = %s ORDER BY created_at",
                        (operation_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return rows[-1] if rows else None


def _provenance(dsn: str, operation_id: str, model: str) -> dict:
    receipt = _gateway_receipt(dsn, operation_id)
    meta = dict(((receipt or {}).get("content") or {}).get("model_meta") or {})
    return {"op": operation_id, "model": model,
            "simulated": bool(meta.get("simulated", False)),
            "meta": meta}


def _mark(dsn: str, episode_id: str, disposition: str, kind: str) -> None:
    def _fn(cur, control):
        cur.execute("UPDATE development_episodes SET disposition = %s,"
                    " updated_at = now() WHERE id = %s", (disposition, episode_id))
        return (ResultCode.APPLIED, f"episode {episode_id} {disposition}",
                {"episode_id": episode_id, "disposition": disposition},
                [(kind, {"episode_id": episode_id,
                         "disposition": disposition})], [])
    store.transact(
        dsn, Command(request_id=f"{kind}-{episode_id}", payload={}), _fn)


def _refused_before_dispatch(exc: SettlementError) -> bool:
    return "refused before dispatch" in str(exc)


def _packet_for(dsn: str, episode: dict, kind: str,
                contract: dict | None = None) -> dict:
    decision: dict[str, Any] = {
        "decision_kind": kind,
        "purpose": f"{kind} {episode['id']} bottleneck",
        "required_inputs": [],
        "allowed_actions": ["propose-intervention"],
        "access": "candidate",
        "budget": packet_budget(),
        "current_versions": {
            "reference_version": episode["reference_version"]},
        "investigation_id": episode["investigation_id"],
        "episode_id": episode["id"],
    }
    if contract is not None:
        decision["candidate_contract"] = contract
    made = context.build_packet(
        dsn, Command(request_id=f"{episode['id']}-pkt-{kind}", payload={}),
        decision=decision)
    data = made.data
    if data["outcome"] != "ready":
        raise SettlementError(
            f"{kind} for {episode['id']} refused: context packet"
            f" {data['outcome']}: {data['gaps']}")
    return data


def _bind_packet(dsn: str, packet: dict, operation_id: str) -> None:
    _applied(context.bind_packet_invocation(
        dsn, Command(request_id=f"{operation_id}-pktbind", payload={}),
        packet["packet_id"], operation_id),
        f"packet {packet['packet_id']} bind")


def diagnose(dsn: str, cmd: Command, adapter: Any, *, episode_id: str,
             model: str, attempt_id: str | None = None,
             probe: dict | None = None,
             launcher: Any = None) -> dict:
    episode = _require_episode(dsn, episode_id)
    if episode["state"] != "admitted":
        raise SettlementError(
            f"episode {episode_id} is {episode['state']}, needs admitted")
    allocation_id = episode["allocation_id"]
    ceiling = int(episode["max_explanations"])
    packet = _packet_for(dsn, episode, "diagnose")
    prompt = json.dumps({"episode": episode_id, "phase": "diagnose",
                         "packet_id": packet["packet_id"],
                         "packet": packet["rendered"],
                         "ceilings": {"explanations": ceiling},
                         "response_contract": context._OUTPUT_CONTRACTS[
                             "diagnose"]["response_shape"],
                         "format": RESPONSE_FORMAT,
                         "ask": "explanations and one intervention"
                                " as raw JSON"})
    op_id = f"{episode_id}-explain"
    try:
        _, text, _ = experiment._infer_via_broker(
            dsn, adapter, operation_id=op_id, model=model, prompt=prompt,
            allocation_id=allocation_id, attempt_id=attempt_id)
    except SettlementError as exc:
        if _refused_before_dispatch(exc):
            _mark(dsn, episode_id, "budget-exhausted",
                  "development.episode-budget-exhausted")
        raise
    provenance = _provenance(dsn, op_id, model)
    experiment._settle_costs(dsn, [dev_protocol_id(episode_id)], op_id,
                             "construction", f"diagnosis inference {episode_id}")
    _bind_packet(dsn, packet, op_id)
    body = _parse_envelope(text)
    if body is None:
        raise SettlementError(
            f"diagnosis for {episode_id} is not typed JSON")
    if not isinstance(body, dict):
        raise SettlementError(f"diagnosis for {episode_id} is not an object")
    explanations = body.get("explanations", [])
    intervention = body.get("intervention", {})
    if not isinstance(explanations, list) or len(explanations) > ceiling:
        raise SettlementError(
            f"diagnosis proposes {len(explanations) if isinstance(explanations, list) else '?'}"
            f" explanations, ceiling is {ceiling}")
    if not isinstance(intervention, (dict, str)) or isinstance(intervention, list):
        raise SettlementError(f"diagnosis needs a single intervention")
    if isinstance(intervention, str):
        intervention = {"action": intervention}
    prior = episode["intervention"] or {}
    for key in ("competing", "uncertainty"):
        if prior.get(key) and not intervention.get(key):
            intervention[key] = prior[key]
    probe_ops: list[dict] = []
    probes_used = 0
    if probe is not None:
        if int(episode["max_probes"]) < 1:
            raise SettlementError(
                f"episode {episode_id} admits no diagnostic probe")
        if launcher is None:
            raise SettlementError("a diagnostic probe needs a launcher")
        raw = probe.get("code", b"")
        raw = raw.encode() if isinstance(raw, str) else bytes(raw)
        probe_op = f"{episode_id}-probe"
        host_path = str(launcher.stage_input(probe_op, "", "probe.py", raw))
        staged = {"probe.py": (host_path, hashlib.sha256(raw).hexdigest())}
        in_dir, _ = launcher.exec_dirs(probe_op, "")
        experiment._ensure_sandbox_op(
            dsn, launcher, probe_op,
            [launcher.staged_python(), f"{in_dir}/probe.py"],
            allocation_id, attempt_id, 30_000)
        experiment._verify_staged(probe_op, staged)
        broker.dispatch_operation(dsn, probe_op,
                                  launchers={launcher.profile: launcher})
        receipt = _gateway_receipt(dsn, probe_op)
        probe_ops.append({"op": probe_op,
                          "outcome": (receipt or {}).get("outcome", "missing")})
        experiment._settle_costs(dsn, [dev_protocol_id(episode_id)], probe_op,
                                 "construction", f"diagnostic probe {episode_id}")
        probes_used = 1
    result = _step(dsn, cmd, episode_id, ("admitted",), "diagnosed",
                   {"explanations": explanations,
                    "intervention": intervention,
                    "probes_used": probes_used, "probe_ops": probe_ops,
                    "disposition": "open"},
                   "development.episode_diagnosed")
    return {"episode_id": episode_id, "state": "diagnosed",
            "explanations": explanations, "intervention": intervention,
            "probes_used": probes_used, "provenance": provenance,
            "packet_id": packet["packet_id"],
            "rendered_digest": packet["rendered_digest"],
            "result": result.detail}


def _check_policy_scope(episode: dict) -> None:
    allowed = set((episode["access_policy"] or {}).get("families", []))
    if not allowed:
        return
    used = {ref.get("family", "") for ref in episode["trigger_refs"]}
    if not used <= allowed:
        raise SettlementError(
            f"episode {episode['id']} trigger families {sorted(used)}"
            f" exceed access policy {sorted(allowed)}")


def _record_candidate(dsn: str, cmd: Command, episode_id: str,
                      entry: dict, nxt: str, disposition: str,
                      kind: str) -> CommandResult:
    def _fn(cur, control):
        cur.execute("SELECT candidates, state, comparison_exposed"
                    " FROM development_episodes WHERE id = %s", (episode_id,))
        row = cur.fetchone()
        if row is None:
            raise SettlementError(f"unknown development episode {episode_id}")
        if row["state"] not in ("diagnosed", "constructed", "checked"):
            raise SettlementError(
                f"episode {episode_id} is {row['state']},"
                " construction needs diagnosed, constructed or checked")
        if row["comparison_exposed"]:
            raise SettlementError(
                f"episode {episode_id} already exposed comparison feedback:"
                " construction retry refused")
        known = list(row["candidates"] or [])
        known.append(entry)
        cur.execute("UPDATE development_episodes SET candidates = %s,"
                    " state = %s, disposition = %s, updated_at = now()"
                    " WHERE id = %s",
                    (_j(known), nxt, disposition, episode_id))
        return (ResultCode.APPLIED,
                f"episode {episode_id} candidate slot {entry.get('slot')}"
                f" now {nxt}",
                {"episode_id": episode_id, "state": nxt},
                [(kind, {"episode_id": episode_id, "slot": entry.get("slot"),
                         "state": nxt,
                         "version_id": entry.get("version_id", "")})], [])
    return _applied(store.transact(dsn, cmd, _fn),
                    f"episode {episode_id} construction")


def construct(dsn: str, cmd: Command, adapter: Any, launcher: Any, *,
              episode_id: str, model: str, artifacts_root: str | Path,
              staging_root: str | Path, version_stem: str,
              entry: str = "candidate.py",
              attempt_id: str | None = None,
              family: str = "") -> dict:
    episode = _require_episode(dsn, episode_id)
    if episode["comparison_exposed"] or episode["state"] in ("selected", "bound"):
        raise SettlementError(
            f"episode {episode_id} already exposed comparison feedback:"
            " construction retry refused")
    if episode["state"] not in ("diagnosed", "constructed", "checked"):
        raise SettlementError(
            f"episode {episode_id} is {episode['state']},"
            " construction needs diagnosed, constructed or checked")
    _check_policy_scope(episode)
    slot = len(episode["candidates"])
    if slot >= int(episode["max_candidates"]):
        raise SettlementError(
            f"episode {episode_id} candidate slots exhausted"
            f" ({slot}/{episode['max_candidates']})")
    allocation_id = episode["allocation_id"]
    access = episode["access_policy"] or {}
    abi = dict(METHOD_ABI, entry=entry)
    packet = _packet_for(dsn, episode, "construct", contract={
        "invocation": {"entry": entry, "verify_args": ["--selftest"],
                       "invoke_args": ["<in-dir>/broken.py",
                                       "<out-dir>/fixed.py"],
                       "reads": abi["reads"], "writes": abi["writes"],
                       "selftest": abi["selftest"], "effects": abi["effects"],
                       "shape": abi["shape"]},
        "applicability": dict(access.get("applicability")
                              or {"family": family}),
        "effect": {"sandbox": launcher.profile},
        "resource": {},
    })
    prompt = json.dumps({"episode": episode_id, "phase": "construct",
                         "slot": slot, "packet_id": packet["packet_id"],
                         "packet": packet["rendered"],
                         "file_abi": abi,
                         "response_shape": context._OUTPUT_CONTRACTS[
                             "construct"]["response_shape"],
                         "format": RESPONSE_FORMAT,
                         "ask": "candidate procedure bytes honoring the"
                                " access policy as raw JSON"})
    model_op = f"{episode_id}-construct-{slot}"
    try:
        _, text, _ = experiment._infer_via_broker(
            dsn, adapter, operation_id=model_op, model=model, prompt=prompt,
            allocation_id=allocation_id, attempt_id=attempt_id)
    except SettlementError as exc:
        if _refused_before_dispatch(exc):
            _mark(dsn, episode_id, "budget-exhausted",
                  "development.episode-budget-exhausted")
        raise
    provenance = _provenance(dsn, model_op, model)
    experiment._settle_costs(dsn, [dev_protocol_id(episode_id)], model_op,
                             "construction",
                             f"candidate construction {episode_id} slot {slot}")
    _bind_packet(dsn, packet, model_op)
    body = _parse_envelope(text)
    if isinstance(body, dict) and body.get("no_candidate") is not None:
        _mark(dsn, episode_id, "no-candidate",
              "development.episode-no-candidate")
        return {"status": "no-candidate",
                "reason": body.get("no_candidate", ""),
                "slot_consumed": False, "provenance": provenance}
    raw = None
    if isinstance(body, dict) and isinstance(body.get("code"), str) \
            and body["code"].encode():
        raw = body["code"].encode()
    if raw is None:
        entry_rec = {"slot": slot, "status": "invalid-output",
                     "model_op": model_op, "provenance": provenance,
                     "detail": "constructor returned no usable code"}
        _record_candidate(dsn, cmd, episode_id, entry_rec, "constructed",
                          "invalid-output", "development.episode-invalid-output")
        return {"status": "invalid-output", "slot_consumed": True,
                "provenance": provenance}
    digest = hashlib.sha256(raw).hexdigest()
    stage_op = f"{episode_id}-stage-{slot}"
    host_path = str(launcher.stage_input(stage_op, "", entry, raw))
    staged = {entry: (host_path, digest)}
    in_dir, _ = launcher.exec_dirs(stage_op, "")
    experiment._ensure_sandbox_op(
        dsn, launcher, stage_op,
        [launcher.staged_python(), f"{in_dir}/{entry}", "--selftest"],
        allocation_id, attempt_id, 30_000)
    experiment._verify_staged(stage_op, staged)
    broker.dispatch_operation(dsn, stage_op,
                              launchers={launcher.profile: launcher})
    receipt = _gateway_receipt(dsn, stage_op)
    experiment._settle_costs(dsn, [dev_protocol_id(episode_id)], stage_op,
                             "construction",
                             f"candidate staging {episode_id} slot {slot}")
    worker = (((receipt or {}).get("content") or {}).get("data")
              or {}).get("worker") or {}
    if (receipt or {}).get("outcome") != "success" \
            or worker.get("status") != "ok":
        entry_rec = {"slot": slot, "status": "invalid-output",
                     "model_op": model_op, "stage_op": stage_op,
                     "code_digest": digest, "provenance": provenance,
                     "detail": "staged selftest did not succeed"
                               " (need exit 0 with typed JSON status ok)"}
        _record_candidate(dsn, cmd, episode_id, entry_rec, "constructed",
                          "invalid-output", "development.episode-invalid-output")
        return {"status": "invalid-output", "slot_consumed": True,
                "stage_op": stage_op, "provenance": provenance}
    version_id = f"{version_stem}-s{slot}"
    manifest = {"files": [{"path": entry, "kind": "file",
                           "digest": digest, "size": len(raw)}],
                "entry": entry, "verify_args": ["--selftest"]}
    try:
        receipt_pkg = artifacts.stage_package(
            dsn, staging_root, manifest=manifest, files={entry: raw},
            access_label="public")
        artifacts.publish_package(
            dsn, Command(request_id=f"{episode_id}-pub-{slot}", payload={}),
            artifacts_root, receipt_pkg)
        capabilities.publish_candidate(
            dsn, Command(request_id=f"{episode_id}-pubcap-{slot}", payload={}),
            artifacts_root, launcher, allocation_id, version_id=version_id,
            family=family, invocation={"entry": entry},
            effect={"sandbox": launcher.profile}, resource={},
            artifact_digest=receipt_pkg["digest"],
            applicability=dict((episode["access_policy"] or {}).get(
                "applicability", {})),
            reference_version=episode["reference_version"],
            change="development construction",
            hypothesis=json.dumps(episode["intervention"])[:500],
            protocol_id=dev_protocol_id(episode_id),
            budget={"units": 500})
    except SettlementError as exc:
        entry_rec = {"slot": slot, "status": "invalid-output",
                     "model_op": model_op, "stage_op": stage_op,
                     "code_digest": digest, "provenance": provenance,
                     "detail": f"packaging refused: {exc}"}
        _record_candidate(dsn, cmd, episode_id, entry_rec, "constructed",
                          "invalid-output", "development.episode-invalid-output")
        return {"status": "invalid-output", "slot_consumed": True,
                "stage_op": stage_op, "provenance": provenance}
    entry_rec = {"slot": slot, "status": "constructed",
                 "version_id": version_id,
                 "artifact_digest": receipt_pkg["digest"],
                 "code_digest": digest, "model_op": model_op,
                 "stage_op": stage_op,
                 "receipt": {"outcome": receipt.get("outcome", ""),
                             "provenance": provenance},
                 "provenance": provenance}
    _record_candidate(dsn, cmd, episode_id, entry_rec, "constructed",
                      "open", "development.episode_constructed")
    return {"status": "constructed", "slot": slot, "version_id": version_id,
            "artifact_digest": receipt_pkg["digest"], "code_digest": digest,
            "stage_op": stage_op, "model_op": model_op,
            "packet_id": packet["packet_id"],
            "rendered_digest": packet["rendered_digest"],
            "provenance": provenance}


def check(dsn: str, cmd: Command, launcher: Any, *, episode_id: str,
          artifacts_root: str | Path, grader_path: str, tasks: list,
          repair_probe: dict | None = None,
          attempt_id: str | None = None) -> dict:
    episode = _require_episode(dsn, episode_id)
    if episode["state"] != "constructed":
        raise SettlementError(
            f"episode {episode_id} is {episode['state']}, needs constructed")
    built = [c for c in episode["candidates"] if c.get("status") == "constructed"]
    if not built:
        raise SettlementError(
            f"episode {episode_id} has no constructed candidate to check")
    if not isinstance(tasks, list) or not tasks or not all(
            isinstance(t, dict) and t.get("broken") is not None
            and isinstance(t.get("cases"), list) for t in tasks):
        raise SettlementError(
            f"episode {episode_id} check needs tasks with broken code and cases")
    target = built[-1]
    capability = capabilities.get_version(dsn, target["version_id"])
    if capability is None:
        raise SettlementError(
            f"episode {episode_id} candidate {target['version_id']}"
            " has no published capability")
    allocation_id = episode["allocation_id"]
    n = len(episode["checks"])
    applied: list[dict] = []
    for task in tasks:
        task_id = str(task.get("id", f"task-{len(applied)}"))
        invoke_tag = f"{episode_id}-check-{n}-{task_id}"
        try:
            fixed, _ = experiment._invoke_method(
                dsn, launcher, Path(artifacts_root), capability,
                task["broken"], invoke_tag, allocation_id, attempt_id)
        except SettlementError as exc:
            applied.append({"task": task_id,
                            "invoke_op": f"invoke-{invoke_tag}",
                            "invoke_outcome": "failed",
                            "detail": str(exc)})
            continue
        experiment._settle_costs(dsn, [dev_protocol_id(episode_id)],
                                 f"invoke-{invoke_tag}", "evaluation",
                                 f"development apply {episode_id} {task_id}")
        grade_tag = f"{episode_id}-grade-{n}-{task_id}"
        op_id, outcome = experiment._grade(
            dsn, launcher, None, fixed, task["cases"], grade_tag,
            allocation_id, attempt_id, grader_path)
        experiment._settle_costs(
            dsn, [dev_protocol_id(episode_id)], op_id,
            "evaluation" if outcome == "success" else "failed_trials",
            f"development check {episode_id} {task_id}")
        applied.append({"task": task_id,
                        "invoke_op": f"invoke-{invoke_tag}",
                        "invoke_outcome": "success",
                        "grade_op": op_id, "grade_outcome": outcome})
    repair: dict = {}
    if repair_probe is not None:
        invoke_tag = f"{episode_id}-repair-{n}"
        try:
            fixed, _ = experiment._invoke_method(
                dsn, launcher, Path(artifacts_root), capability,
                repair_probe["broken"], invoke_tag, allocation_id,
                attempt_id)
            experiment._settle_costs(dsn, [dev_protocol_id(episode_id)],
                                     f"invoke-{invoke_tag}", "evaluation",
                                     f"repair probe {episode_id}")
            repair = {"invoke_op": f"invoke-{invoke_tag}",
                      "match": fixed == repair_probe["expected"]}
        except SettlementError as exc:
            repair = {"invoke_op": f"invoke-{invoke_tag}",
                      "match": False, "detail": str(exc)}
    outcome = "success" if applied and all(
        a.get("invoke_outcome") == "success"
        and a.get("grade_outcome") == "success" for a in applied) else "failure"
    record = {"candidate": target["version_id"], "grade_outcome": outcome,
              "grade_ops": [a["grade_op"] for a in applied
                            if a.get("grade_op")],
              "applied": applied, "repair": repair}
    result = _step(dsn, cmd, episode_id, ("constructed",), "checked",
                   {"checks": [*episode["checks"], record]},
                   "development.episode_checked")
    return {"episode_id": episode_id, "state": "checked",
            "candidate": target["version_id"], "grade_outcome": outcome,
            "applied": applied, "repair": repair, "result": result.detail}


def freeze_comparison(dsn: str, cmd: Command, *, episode_id: str,
                      policy: dict) -> CommandResult:
    if not isinstance(policy, dict) or not policy.get("task_groups"):
        raise SettlementError(
            "comparison freeze needs a policy with task groups")
    episode = _require_episode(dsn, episode_id)
    if episode["state"] != "checked":
        raise SettlementError(
            f"episode {episode_id} is {episode['state']},"
            " comparison freezes in checked before selection")
    frozen = episode.get("comparison_policy") or {}
    panel_pid = frozen.get("panel_protocol")
    panel = frozen.get("panel")
    if not panel_pid or not panel:
        raise SettlementError(
            f"episode {episode_id}: the finite-panel policy must be frozen"
            " at admission before development feedback")
    if _norm_groups(policy.get("task_groups")) != _norm_groups(
            panel.get("task_groups")):
        raise SettlementError(
            f"episode {episode_id}: submitted comparison groups differ from"
            " the admission-frozen panel policy: declare an amendment")
    eval_pid = eval_protocol_id(episode_id)
    try:
        trials.amend_protocol(
            dsn, Command(request_id=f"{eval_pid}-freeze", payload={}),
            protocol_id=eval_pid, supersedes=panel_pid,
            evaluator_version=str(policy.get("evaluator_version")
                                  or panel.get("evaluator_version", "")))
    except SettlementError as exc:
        if "already exists" not in str(exc):
            raise
    return _step(dsn, cmd, episode_id, ("checked",), None,
                 {"comparison_policy": {**frozen, "eval_protocol": eval_pid,
                                        "frozen_policy": policy}},
                 "development.comparison_frozen")


def select(dsn: str, cmd: Command, *, episode_id: str) -> dict:
    episode = _require_episode(dsn, episode_id)
    if episode["state"] != "checked":
        raise SettlementError(
            f"episode {episode_id} is {episode['state']}, needs checked")
    if not (episode.get("comparison_policy") or {}).get("eval_protocol"):
        raise SettlementError(
            f"episode {episode_id}: comparison policy must be frozen"
            " before development-only selection")
    if not episode["checks"]:
        raise SettlementError(f"episode {episode_id} has no development checks")
    latest = episode["checks"][-1]
    repair = latest.get("repair") or {}
    passed = latest.get("grade_outcome") == "success" and \
        ("match" not in repair or repair["match"])
    selection = {"decision": "select" if passed else "reject",
                 "version_id": latest["candidate"] if passed else None,
                 "basis": "development-checks", "check": latest,
                 "comparison_policy_ref": "frozen-before-selection"}
    result = _step(dsn, cmd, episode_id, ("checked",), "selected",
                   {"selection": selection, "disposition": "ready"},
                   "development.episode_selected")
    return {"episode_id": episode_id, "state": "selected",
            "selection": selection, "result": result.detail}


def bind(dsn: str, cmd: Command, *, episode_id: str) -> dict:
    episode = _require_episode(dsn, episode_id)
    if episode["state"] != "selected":
        raise SettlementError(
            f"episode {episode_id} is {episode['state']}, needs selected")
    selection = episode["selection"] or {}
    bindings = {"version_id": selection.get("version_id"),
                "reference_version": episode["reference_version"],
                "development_protocol": dev_protocol_id(episode_id),
                "comparison_policy": episode["comparison_policy"],
                "selection": selection}
    eval_pid = (episode.get("comparison_policy") or {}).get("eval_protocol")
    if eval_pid:
        bound_pid = f"{eval_pid}-bound"
        try:
            trials.amend_protocol(
                dsn, Command(request_id=f"{bound_pid}-freeze", payload={}),
                protocol_id=bound_pid, supersedes=eval_pid,
                candidate_version=selection.get("version_id") or "")
        except SettlementError as exc:
            if "already exists" not in str(exc):
                raise
        bindings["comparison_protocol"] = bound_pid
    if selection.get("version_id"):
        found = next((c for c in episode["candidates"]
                      if c.get("version_id") == selection["version_id"]), {})
        bindings["artifact_digest"] = found.get("artifact_digest", "")
        bindings["code_digest"] = found.get("code_digest", "")
    result = _step(dsn, cmd, episode_id, ("selected",), "bound",
                   {"bindings": bindings, "comparison_exposed": True,
                    "disposition": "bound"},
                   "development.episode_bound")
    return {"episode_id": episode_id, "state": "bound",
            "bindings": bindings, "result": result.detail}


def resume_episode(dsn: str, episode_id: str,
                   artifacts_root: str | Path | None = None) -> dict:
    episode = _require_episode(dsn, episode_id)
    ops: dict[str, dict] = {}
    op_ids = [f"{episode_id}-explain"]
    if episode["probes_used"]:
        op_ids.append(f"{episode_id}-probe")
    for entry in episode["candidates"]:
        for key in ("model_op", "stage_op"):
            if entry.get(key):
                op_ids.append(entry[key])
    for record in episode["checks"]:
        for key in ("grade_op",):
            if record.get(key):
                op_ids.append(record[key])
        for op_id in record.get("grade_ops", []) or []:
            op_ids.append(op_id)
        invoke_op = (record.get("repair") or {}).get("invoke_op")
        if invoke_op:
            op_ids.append(invoke_op)
    for op_id in op_ids:
        try:
            ops[op_id] = experiment._op_accounting(dsn, op_id)
        except Exception:
            ops[op_id] = {"operation_id": op_id, "dispatch_state": "unknown"}
    availability: dict[str, dict] = {}
    if artifacts_root is not None:
        for entry in episode["candidates"]:
            digest = entry.get("artifact_digest", "")
            if not digest:
                continue
            present = capabilities.get_version(
                dsn, entry.get("version_id", "")) is not None
            availability[entry.get("version_id", "")] = {
                "artifact_available": artifacts.artifact_available(
                    dsn, artifacts_root, digest),
                "capability_published": present}
    ledger: dict = {}
    try:
        ledger = trials.development_expenditure(
            dsn, dev_protocol_id(episode_id))
    except SettlementError:
        ledger = {"protocol_id": dev_protocol_id(episode_id),
                  "by_category": {}, "development_total": 0}
    return {"episode": episode, "ops": ops, "availability": availability,
            "ledger": ledger}


def episode_trace(dsn: str, episode_id: str) -> list[dict]:
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT epoch, ordinal, kind, payload FROM domain_events"
                        " WHERE payload->>'episode_id' = %s"
                        " ORDER BY epoch, ordinal", (episode_id,))
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()
    return rows
