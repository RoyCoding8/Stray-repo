"""Real acquisition orchestration for Representation Lane D (CBR-01).

Finite broker-routed model construction: 2 source + 2 transfer calls per
arm (12 total, retries 0, fixed token caps, no capacity transfer between
arms or stages). Constructor responses become the executed bytes through
the existing stage/publish/record profile path; authored fixtures never
enter as candidates. Source construction freezes the shared core before
any graph material is exposed; transfer adapters stage against those
frozen bytes only. Unusable responses abstain explicitly; nothing is
invented to fill the panel.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from settlement import artifacts, broker, launcher_local, store
from settlement import representation as R
from settlement.common import Command, ResultCode, SettlementError
from settlement.gateway import GatewayError

from experiments.representation.acquire import contexts
from experiments.representation.acquire import retention
from experiments.representation.acquire import run as panel_run
from experiments.representation.experiment import freeze

REP = ROOT / "experiments" / "representation"

ARMS = ("A", "B", "C")
STAGES = ("source", "transfer")
SLOTS = (1, 2)

MODEL_CALLS = 12
MAX_INPUT_TOKENS = 16384
MAX_OUTPUT_TOKENS = 8192
RETRIES = 0
DEADLINE_MS = 300_000
REASONING_EFFORT = "low"

FILE_LIMIT_CHARS = 65536

KINDS = {("A", "source"): "lessons", ("A", "transfer"): "lessons",
         ("B", "source"): "procedure", ("B", "transfer"): "procedure",
         ("C", "source"): "core", ("C", "transfer"): "adapter"}

EXPECTED_FILES = {"lessons": ("lessons.md",),
                  "procedure": ("procedure.py",),
                  "core": ("core.py", "adapter.py", "DESCRIPTION.md"),
                  "adapter": ("adapter.py", "DESCRIPTION.md")}

SELECTION_TASK = {"source": "sw-dev-00", "transfer": "gr-dev-00"}

BUDGET = {"model_calls": MODEL_CALLS,
          "input_tokens_per_call": MAX_INPUT_TOKENS,
          "output_tokens_per_call": MAX_OUTPUT_TOKENS,
          "retries": RETRIES,
          "per_arm": {"source_calls": 2, "transfer_calls": 2},
          "unused_capacity_transfer": False}

EQUAL_OPPORTUNITY = ("2 source + 2 transfer calls per arm;"
                     " unused capacity never transferred")

ZERO_SPENT = {"model_calls": 0, "input_tokens": 0,
              "output_tokens": 0, "grant_units": 0}

CONTRACT = """Respond with one JSON object only, no prose, no fences.
To abstain: {"abstain": true, "reason": "<bounded reason>"}.
To propose: {"kind": "<kind>", "files": {"<name>": "<source text>"}}
where kind and file names match the assignment exactly. Python files must
be parseable Python. Each file must be nonempty and at most 65536 chars.
Any other shape is ignored and consumes the call."""


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _cmd() -> Command:
    return Command(request_id="rpr-camp-%s" % uuid.uuid4().hex, payload={})


def campaign_allocation(tag: str) -> str:
    return "rpr-camp-%s" % tag


def op_id(tag: str, arm: str, stage: str, slot: int) -> str:
    return "rpr-camp-%s-%s-%s-s%d" % (tag, arm, stage, slot)


def composition_id(tag: str, stage: str, slot: int) -> str:
    return "rpr-C-%s-%s-s%d" % (stage, tag, slot)


def estimate_input_tokens(prompt: str) -> int:
    return len(prompt) // 4 + 1


def model_exposure(prompt: str) -> int:
    return (estimate_input_tokens(prompt) + MAX_OUTPUT_TOKENS) * (RETRIES + 1)


def resolve_config(cli=None, env=None) -> dict:
    cli = dict(cli or {})
    env = dict(env or {})

    def _first(*names):
        for name in names:
            value = cli.get(name)
            if value:
                return value
        return ""

    def _env(*names):
        for name in names:
            value = env.get(name)
            if value:
                return value
        return ""
    return {
        "endpoint": _first("endpoint") or _env("SETTLEMENT_GATEWAY_ENDPOINT",
                                               "SETTLEMENT_GATEWAY_URL"),
        "gateway_key": _first("gateway_key") or _env("SETTLEMENT_GATEWAY_KEY"),
        "grant": _first("grant") or _env("SETTLEMENT_GRANT_UNITS"),
        "model": _first("model") or _env("SETTLEMENT_MODEL"),
        "dsn": _first("dsn") or _env("SETTLEMENT_TEST_DSN", "SETTLEMENT_DSN"),
    }


def _arm_brief(arm: str, stage: str) -> str:
    if arm == "A":
        return ("Arm A develops textual lessons: durable selection guidance "
                "for the two native reducers over %s reduction tasks. "
                "Propose kind \"lessons\" with lessons.md only." % stage)
    if arm == "B":
        return ("Arm B acquires a task-specific procedure: deterministic "
                "Python implementing one %s reduction procedure within the "
                "stated caps. Propose kind \"procedure\" with procedure.py "
                "only." % stage)
    if stage == "source":
        return ("Arm C acquires the shared core and its software adapter: "
                "domain-blind search over anonymous atom indices plus "
                "translation to and from software tasks. Propose kind "
                "\"core\" with core.py, adapter.py and DESCRIPTION.md.")
    return ("Arm C acquires the transfer adapter for the frozen core whose "
            "digest is stated below. The core is immutable: never return "
            "core.py, it is refused. Propose kind \"adapter\" with "
            "adapter.py and DESCRIPTION.md only.")


def source_prompt(arm: str, slot: int, source_context: dict) -> str:
    prompt = "\n\n".join([
        "Representation acquisition, source stage, arm %s call %d of 2." % (arm, slot),
        _arm_brief(arm, "source"),
        "Source experience (authored fixtures, software family only):",
        json.dumps(source_context, sort_keys=True),
        "Instruments: syntax, legal deletion rules, witness specification, "
        "source-check queries (16 per task), baseline reducers ddmin and "
        "greedy. Measure is sequence length; only strict decreases count.",
        CONTRACT,
    ])
    lowered = prompt.lower()
    leaked = [token for token in contexts.BARRIER_TOKENS if token in lowered]
    if leaked:
        raise SettlementError("source prompt leaks barrier tokens %s" % leaked)
    return prompt


def transfer_prompt(arm: str, slot: int, transfer_context: dict,
                    frozen_core_digest: str | None,
                    frozen_core_bytes: bytes | None = None) -> str:
    frozen = frozen_core_digest or ("0" * 64)
    sections = [
        "Representation acquisition, transfer stage, arm %s call %d of 2." % (arm, slot),
        _arm_brief(arm, "transfer"),
        "Frozen source core digest: %s" % frozen,
        "Transfer experience (authored fixtures, second family only):",
        json.dumps(transfer_context, sort_keys=True),
        "Instruments: syntax, legal subgraph rules, witness specification, "
        "source-check queries (16 per task), baseline reducers ddmin and "
        "greedy. Measure is vertices plus edges; only strict decreases "
        "count. Selection uses development and check data only.",
        CONTRACT,
    ]
    if frozen_core_bytes is not None:
        if not isinstance(frozen_core_bytes, bytes):
            raise SettlementError("frozen core bytes are not bytes")
        try:
            core_text = frozen_core_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise SettlementError("frozen core bytes are not UTF-8 text")
        if len(core_text) > retention.CORE_SOURCE_CAP_CHARS:
            raise SettlementError(
                "frozen core exceeds the transfer-prompt bound")
        sections.append(retention.transfer_enrichment(core_text))
    return "\n\n".join(sections)


def plan_prompts(source_context: dict, transfer_context: dict,
                 frozen_core_digest: str | None = None,
                 frozen_core_bytes: bytes | None = None) -> list:
    plan = []
    for stage in STAGES:
        for arm in ARMS:
            for slot in SLOTS:
                if stage == "source":
                    prompt = source_prompt(arm, slot, source_context)
                else:
                    prompt = transfer_prompt(arm, slot, transfer_context,
                                             frozen_core_digest,
                                             frozen_core_bytes)
                tokens = estimate_input_tokens(prompt)
                if tokens > MAX_INPUT_TOKENS:
                    raise SettlementError(
                        "construction prompt exceeds the input cap")
                plan.append({"arm": arm, "stage": stage, "slot": slot,
                             "kind": KINDS[(arm, stage)], "prompt": prompt,
                             "input_tokens": tokens,
                             "reasoning_effort": REASONING_EFFORT,
                             "exposure": model_exposure(prompt)})
    return plan


def required_grant(plan: list) -> int:
    return sum(entry["exposure"] for entry in plan)


def enrichment_reserve(plan: list) -> int:
    calls = sum(1 for entry in plan if entry["stage"] == "transfer")
    return retention.enrichment_reserve(calls)


def required_total(plan: list) -> int:
    return required_grant(plan) + enrichment_reserve(plan)


def load_contexts() -> tuple:
    source = json.loads(
        (REP / "acquire" / "source_context.json").read_bytes())
    transfer = json.loads(
        (REP / "acquire" / "transfer_context.json").read_bytes())
    return source, transfer


def required_grant_for_contexts() -> tuple:
    source, transfer = load_contexts()
    plan = plan_prompts(source, transfer)
    return required_total(plan), plan


def parse_construction_response(text, kind: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        return {"status": "ignored", "reason": "empty-response"}
    try:
        doc = json.loads(text)
    except ValueError:
        return {"status": "ignored", "reason": "not-json"}
    if not isinstance(doc, dict):
        return {"status": "ignored", "reason": "not-json-object"}
    if doc.get("abstain") is True:
        reason = doc.get("reason", "")
        if not isinstance(reason, str) or not reason:
            reason = "abstained"
        return {"status": "abstained", "reason": reason[:256]}
    if set(doc) != {"kind", "files"} or doc.get("kind") != kind:
        return {"status": "ignored", "reason": "wrong-kind"}
    files = doc.get("files")
    if not isinstance(files, dict):
        return {"status": "ignored", "reason": "files-not-object"}
    names = set(files)
    core_change_refused = False
    if kind == "adapter" and "core.py" in names:
        names = names - {"core.py"}
        core_change_refused = True
    if names != set(EXPECTED_FILES[kind]):
        return {"status": "ignored", "reason": "wrong-files",
                "core_change_refused": core_change_refused}
    parsed = {}
    for name in EXPECTED_FILES[kind]:
        body = files[name]
        if not isinstance(body, str) or not body.strip() \
                or len(body) > FILE_LIMIT_CHARS:
            return {"status": "ignored", "reason": "bad-file-%s" % name,
                    "core_change_refused": core_change_refused}
        if name.endswith(".py"):
            try:
                compile(body, "<constructor-response>", "exec")
            except (SyntaxError, ValueError, RecursionError):
                return {"status": "ignored", "reason": "unparseable-python",
                        "core_change_refused": core_change_refused}
        parsed[name] = body
    return {"status": "retained", "reason": "parsed",
            "core_change_refused": core_change_refused, "files": parsed}


def _receipts_for(dsn: str, operation_id: str) -> list:
    from psycopg.rows import dict_row

    from settlement import db as _db

    with _db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT receipt_identity, outcome, content FROM receipts"
                        " WHERE operation_id = %s ORDER BY created_at",
                        (operation_id,))
            rows = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return rows


def _gateway_text(receipts: list) -> tuple:
    for row in receipts:
        identity = row.get("receipt_identity") or ""
        if not identity.startswith("gw:"):
            continue
        content = dict(row.get("content") or {})
        usage = dict(content.get("usage") or {})
        tokens = {"input": int(usage.get("input_tokens", 0) or 0),
                  "output": int(usage.get("output_tokens", 0) or 0)}
        charge = usage.get("charge_units", 0)
        try:
            charge_units = int(charge or 0)
        except (TypeError, ValueError):
            charge_units = 0
        billed = bool(usage.get("billed", False)) and charge_units >= 0
        return (content.get("text"), tokens,
                charge_units if billed else 0, content.get("error", ""))
    return (None, {"input": 0, "output": 0}, 0, "no-gateway-receipt")


def construct_slot(dsn: str, gateway, entry: dict, tag: str, model: str,
                   allocation_id: str, attempt_id: str) -> dict:
    operation_id = op_id(tag, entry["arm"], entry["stage"], entry["slot"])
    ensured = broker.ensure_operation(
        dsn, operation_id=operation_id, effect=broker.MODEL_INFERENCE,
        payload={"model": model,
                 "messages": [{"role": "user", "content": entry["prompt"]}],
                 "max_output_tokens": MAX_OUTPUT_TOKENS,
                 "deadline_ms": DEADLINE_MS,
                 "reasoning_effort": entry.get("reasoning_effort")},
        allocation_id=allocation_id, attempt_id=attempt_id, retries=RETRIES)
    if ensured.code == ResultCode.INSUFFICIENT_RESOURCES:
        return {"arm": entry["arm"], "stage": entry["stage"],
                "slot": entry["slot"], "kind": entry["kind"],
                "operation_id": operation_id, "status": "error",
                "reason": "grant-refused-at-admission",
                "detail": ensured.detail}
    if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return {"arm": entry["arm"], "stage": entry["stage"],
                "slot": entry["slot"], "kind": entry["kind"],
                "operation_id": operation_id, "status": "error",
                "reason": "operation-not-admitted", "detail": ensured.detail}
    status = broker.dispatch_operation(dsn, operation_id, gateway=gateway)
    receipts = _receipts_for(dsn, operation_id)
    text, tokens, charge, error = _gateway_text(receipts)
    record = {"arm": entry["arm"], "stage": entry["stage"],
              "slot": entry["slot"], "kind": entry["kind"],
              "operation_id": operation_id,
              "dispatch_state": status.dispatch_state,
              "prompt_digest": _digest(entry["prompt"].encode()),
              "input_tokens": tokens["input"], "output_tokens": tokens["output"],
              "grant_units": charge, "exposure": entry["exposure"]}
    if text is None:
        record.update({"status": "error",
                       "reason": "transport: %s" % (error or "lost-response")})
        return record
    parsed = parse_construction_response(text, entry["kind"])
    record.update(parsed)
    record["response_digest"] = _digest(text.encode())
    return record


def stage_text(dsn: str, slot: dict, staging_root: Path,
               artifacts_root: Path) -> dict:
    name = EXPECTED_FILES[slot["kind"]][0]
    raw = slot["files"][name].encode()
    manifest = {"files": [{"path": name, "digest": _digest(raw),
                           "size": len(raw)}], "entry": name}
    receipt = artifacts.stage_package(
        dsn, staging_root, manifest=manifest, files={name: raw}, scope="rpr",
        access_label="public", format="acquisition-%s" % slot["kind"],
        version="1", dependencies=[])
    published = artifacts.publish_package(dsn, _cmd(), artifacts_root, receipt)
    if published.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return {"status": "error", "reason": "artifact-not-published",
                "detail": published.detail}
    checked = artifacts.verify_bytes(dsn, artifacts_root, receipt["digest"])
    if not checked.get("ok"):
        return {"status": "error", "reason": "artifact-unverifiable",
                "detail": checked.get("reason", "")}
    return {"status": "retained", "reason": slot["reason"],
            "artifact_digest": receipt["digest"], "file_digest": _digest(raw)}


def stage_composition(dsn: str, slot: dict, tag: str, staging_root: Path,
                      artifacts_root: Path, core_bytes: bytes) -> dict:
    adapter_raw = slot["files"]["adapter.py"].encode()
    desc_raw = slot["files"]["DESCRIPTION.md"].encode()
    if slot["stage"] == "source":
        core_raw = slot["files"]["core.py"].encode()
    else:
        core_raw = core_bytes
    if not core_raw:
        return {"status": "error", "reason": "no-frozen-core"}
    receipt = R.stage_composition(
        staging_root, core_bytes=core_raw, adapter_bytes=adapter_raw,
        description=desc_raw, dsn=dsn)
    published = R.publish_composition(dsn, _cmd(), artifacts_root, receipt)
    if published.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        return {"status": "error", "reason": "artifact-not-published",
                "detail": published.detail}
    comp_id = composition_id(tag, slot["stage"], slot["slot"])
    recorded = R.record_composition(
        dsn, _cmd(), artifacts_root, composition_id=comp_id,
        package_digest=receipt["digest"], role=slot["stage"],
        protocol_id="rpr-camp-%s" % tag)
    if recorded.code != ResultCode.APPLIED \
            and "already recorded" not in recorded.detail:
        return {"status": "error", "reason": "composition-refused",
                "detail": recorded.detail}
    try:
        checked = R.check_composition(dsn, artifacts_root, comp_id)
    except SettlementError as exc:
        return {"status": "error", "reason": "composition-unverifiable",
                "detail": str(exc)[:256]}
    want_core = _digest(core_raw)
    want_adapter = _digest(adapter_raw)
    if checked["core_digest"] != want_core \
            or checked["adapter_digest"] != want_adapter:
        return {"status": "error", "reason": "binding-conflict",
                "detail": "composition %s already binds other bytes" % comp_id,
                "composition_id": comp_id}
    if slot["stage"] == "source":
        return {"status": "retained", "reason": slot["reason"],
                "composition_id": comp_id,
                "package_digest": receipt["digest"],
                "core_digest": want_core, "adapter_digest": want_adapter,
                "core_adapted": False, "adaptation": None,
                "frozen_core_digest": None}
    frozen = _digest(core_bytes)
    adapted = checked["core_digest"] != frozen
    return {"status": "retained", "reason": slot["reason"],
            "composition_id": comp_id,
            "package_digest": receipt["digest"],
            "core_digest": want_core, "adapter_digest": want_adapter,
            "core_adapted": adapted,
            "adaptation": "transfer-core-differs-from-frozen" if adapted
                          else None,
            "frozen_core_digest": frozen}


def execute_candidate(dsn: str, launcher, artifacts_root: Path, slot: dict,
                      tag: str, manifest: dict, allocation_id: str,
                      attempt_id: str) -> dict:
    task, _ = panel_run.load_task(SELECTION_TASK[slot["stage"]])
    try:
        composed = panel_run.run_composition(
            dsn, launcher, artifacts_root,
            tag="%s-sel-s%d" % (tag, slot["slot"]), task=task,
            composition_id=slot["composition_id"], manifest=manifest,
            allocation_id=allocation_id, attempt_id=attempt_id)
    except SettlementError as exc:
        return {"executed": False,
                "reason": "execution-refused: %s" % str(exc)[:200]}
    return {"executed": True, "disposition": composed["disposition"],
            "reason": composed["reason"],
            "improvement_u": composed["u"], "verified": composed["verified"],
            "best_measure": composed["best_measure"],
            "delivered_digest": composed["delivered_digest"],
            "invocations_used": composed["costs"]["invocations_used"],
            "queries_used": composed["costs"]["queries_used"]}


def _select_text(slots: list) -> dict:
    for slot in sorted(slots, key=lambda entry: entry["slot"]):
        if slot.get("status") == "retained" and slot.get("artifact_digest"):
            return {"selected": slot["slot"],
                    "artifact_digest": slot["artifact_digest"],
                    "file_digest": slot["file_digest"],
                    "reason": "first-parseable-%s" % slot["kind"]}
    reasons = sorted({slot.get("reason", "missing") for slot in slots})
    return {"selected": None, "reason": "abstained: %s" % ",".join(reasons)}


def _select_core(slots: list) -> dict:
    cands = [slot for slot in slots
             if slot.get("status") == "retained"
             and (slot.get("execution") or {}).get("executed")
             and slot["execution"].get("disposition")
             in ("improved", "no_improvement")]
    if not cands:
        reasons = sorted({slot.get("execution", {}).get("reason")
                          or slot.get("reason", "missing") for slot in slots})
        return {"selected": None,
                "reason": "no-candidate: %s" % ",".join(reasons)}
    cands.sort(key=lambda entry: (-entry["execution"]["improvement_u"],
                                  not entry["execution"]["verified"],
                                  entry["slot"]))
    best = cands[0]
    return {"selected": best["slot"],
            "composition_id": best["composition_id"],
            "core_digest": best["core_digest"],
            "adapter_digest": best["adapter_digest"],
            "package_digest": best["package_digest"],
            "improvement_u": best["execution"]["improvement_u"],
            "verified": best["execution"]["verified"],
            "reason": "best-verified-execution"}


def blocked_record(reason: str, **extra) -> dict:
    record = {"blocked": True, "reason": reason, "budget": BUDGET,
              "equal_opportunity": EQUAL_OPPORTUNITY,
              "spent": dict(ZERO_SPENT), "model_output": "none"}
    record.update(extra)
    return record


def has_installed_grant(dsn: str) -> bool:
    from settlement import db as _db

    control = store.get_control(dsn)
    with _db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM grants WHERE version = %s",
                        (int(control.get("authority_version", 0)),))
            found = cur.fetchone() is not None
            conn.commit()
            return found


def _ensure_campaign_allocation(dsn: str, tag: str, plan: list):
    allocation_id = campaign_allocation(tag)
    try:
        status = store.allocation_status(dsn, allocation_id)
    except SettlementError:
        status = None
    if status is None:
        result = store.seed_allocation(
            dsn, Command(request_id="rpr-camp-seed-%s-%s" % (tag, uuid.uuid4().hex[:8]),
                         payload={"allocation_id": allocation_id, "domain": "cpu",
                                  "authorized": required_total(plan)}))
        if result.code != ResultCode.APPLIED:
            return None, blocked_record("insufficient-grant",
                                  detail=result.detail,
                                  allocation_id=allocation_id)
        return allocation_id, None
    outstanding = sum(entry["exposure"] for entry in plan
                      if broker.read_operation(
                          dsn, op_id(tag, entry["arm"], entry["stage"],
                                    entry["slot"])) is None)
    available = int(status["authorized"]) - int(status["consumed"]) \
        - int(status["reserved"])
    if available < outstanding:
        return None, blocked_record("insufficient-grant",
                              detail="allocation %s has %d available but %d"
                                     " outstanding" % (allocation_id, available,
                                                      outstanding),
                              allocation_id=allocation_id)
    return allocation_id, None


def _run_stage(dsn: str, gateway, entries: list, tag: str, model: str,
               allocation_id: str, attempt_id: str) -> list:
    return [construct_slot(dsn, gateway, entry, tag, model, allocation_id,
                           attempt_id) for entry in entries]


def _stage_and_execute(dsn: str, launcher, slots: list, tag: str,
                       staging_root: Path, artifacts_root: Path,
                       manifest: dict, allocation_id: str, attempt_id: str,
                       frozen_core: bytes | None) -> list:
    for slot in slots:
        if slot.get("status") != "retained":
            continue
        if slot["kind"] in ("lessons", "procedure"):
            slot.update(stage_text(dsn, slot, staging_root, artifacts_root))
        else:
            slot.update(stage_composition(dsn, slot, tag, staging_root,
                                          artifacts_root, frozen_core))
        if slot.get("status") == "retained" and slot.get("composition_id"):
            slot["execution"] = execute_candidate(
                dsn, launcher, artifacts_root, slot, tag, manifest,
                allocation_id, attempt_id)
    return slots


def run_campaign(dsn: str, *, tag: str, model: str, grant_units: int, gateway,
                 artifacts_root, staging_root, runs_root, evidence_root,
                 allocation_id: str = "") -> dict:
    for root in (artifacts_root, staging_root, runs_root, evidence_root):
        Path(root).mkdir(parents=True, exist_ok=True)
    problems = freeze.verify_committed()
    if problems:
        raise SettlementError("frozen inputs invalid: %s" % problems)
    source_context, transfer_context = load_contexts()
    plan = plan_prompts(source_context, transfer_context)
    need = required_total(plan)
    reserve = enrichment_reserve(plan)
    if not isinstance(grant_units, int) or grant_units < need:
        return blocked_record("grant-below-requirement", grant_units=grant_units,
                        required_exposure=need)
    if not has_installed_grant(dsn):
        return blocked_record("no-installed-grant",
                        detail="credentials alone do not replace durable"
                               " authority: seed a grant first")
    base = panel_run.ensure_foundation(dsn, tag)
    manifest = base["manifest"]
    panel_run.ensure_episodes(dsn, tag, manifest["lane_b"]["manifest_digest"])
    allocation_id, blocked = _ensure_campaign_allocation(dsn, tag, plan)
    if blocked is not None:
        return blocked
    discovery = gateway.check_discovery()
    if isinstance(discovery, GatewayError):
        return blocked_record("gateway-unreachable", detail=discovery.message)
    auth = gateway.check_auth()
    if isinstance(auth, GatewayError):
        return blocked_record("gateway-auth", detail=auth.message)
    launcher = launcher_local.LocalLauncher(str(runs_root))
    source_entries = [entry for entry in plan if entry["stage"] == "source"]
    source_slots = _run_stage(dsn, gateway, source_entries, tag, model,
                              allocation_id, base["attempt_id"])
    _stage_and_execute(dsn, launcher, source_slots, tag, Path(staging_root),
                       Path(artifacts_root), manifest, base["allocation_id"],
                       base["attempt_id"], None)
    selection = {}
    for arm in ARMS:
        arm_slots = [slot for slot in source_slots if slot["arm"] == arm]
        if arm == "C":
            selection[("C", "source")] = _select_core(arm_slots)
        else:
            selection[(arm, "source")] = _select_text(arm_slots)
    frozen = selection[("C", "source")]
    frozen_digest = frozen.get("core_digest")
    frozen_bytes = None
    if frozen.get("selected") is not None:
        winner = next(slot for slot in source_slots
                      if slot["arm"] == "C"
                      and slot["slot"] == frozen["selected"])
        frozen_bytes = winner["files"]["core.py"].encode()
    live_plan = plan_prompts(source_context, transfer_context, frozen_digest,
                             frozen_bytes)
    live_transfer = [entry for entry in live_plan
                     if entry["stage"] == "transfer"]
    for planned, live in zip([entry for entry in plan
                              if entry["stage"] == "transfer"], live_transfer):
        assert (planned["arm"], planned["stage"], planned["slot"],
                planned["kind"]) == (live["arm"], live["stage"],
                                     live["slot"], live["kind"])
        assert live["exposure"] <= planned["exposure"] \
            + retention.enrichment_reserve(1)
    transfer_slots = _run_stage(dsn, gateway, live_transfer, tag, model,
                                allocation_id, base["attempt_id"])
    _stage_and_execute(dsn, launcher, transfer_slots, tag, Path(staging_root),
                       Path(artifacts_root), manifest, base["allocation_id"],
                       base["attempt_id"], frozen_bytes)
    for arm in ARMS:
        arm_slots = [slot for slot in transfer_slots if slot["arm"] == arm]
        if arm == "C":
            selection[("C", "transfer")] = _select_core(arm_slots)
        else:
            selection[(arm, "transfer")] = _select_text(arm_slots)
    slots = source_slots + transfer_slots
    spent = dict(ZERO_SPENT)
    spent["model_calls"] = sum(1 for slot in slots if "dispatch_state" in slot)
    spent["input_tokens"] = sum(slot.get("input_tokens", 0) for slot in slots)
    spent["output_tokens"] = sum(slot.get("output_tokens", 0) for slot in slots)
    spent["grant_units"] = sum(slot.get("grant_units", 0) for slot in slots)
    acquired = all(selection[(arm, stage)].get("selected") is not None
                   for arm, stage in ((arm, stage) for arm in ARMS
                                      for stage in STAGES))
    frozen_record = retention.freeze_retention(
        tag=tag, model=model, reasoning_effort=REASONING_EFFORT,
        manifest_sha=base["manifest_sha"],
        selectors=manifest["selectors"], selection_tasks=SELECTION_TASK,
        slots=slots, selection=selection, frozen_core_digest=frozen_digest,
        spent=spent, budget=BUDGET, equal_opportunity=EQUAL_OPPORTUNITY,
        campaign_allocation=allocation_id,
        foundation_allocation=base["allocation_id"], transfer_reserve=reserve)
    record = {"blocked": False, "protocol": "rpr-acq-C", "tag": tag,
              "model": model, "reasoning_effort": REASONING_EFFORT,
              "grant_units": grant_units,
              "required_exposure": need, "budget": BUDGET,
              "equal_opportunity": EQUAL_OPPORTUNITY,
              "transfer_enrichment_reserve": reserve,
              "campaign_allocation": allocation_id,
              "foundation_allocation": base["allocation_id"],
              "plan": [{"arm": entry["arm"], "stage": entry["stage"],
                        "slot": entry["slot"], "kind": entry["kind"],
                        "operation_id": op_id(tag, entry["arm"],
                                              entry["stage"], entry["slot"]),
                        "input_tokens": entry["input_tokens"],
                        "exposure": entry["exposure"]} for entry in plan],
              "slots": [{key: slot.get(key) for key in
                         ("arm", "stage", "slot", "kind", "operation_id",
                          "dispatch_state", "status", "reason", "detail",
                          "prompt_digest", "response_digest", "input_tokens",
                          "output_tokens", "grant_units", "exposure",
                          "core_change_refused", "artifact_digest",
                          "file_digest", "composition_id", "package_digest",
                          "core_digest", "adapter_digest", "core_adapted",
                          "adaptation", "frozen_core_digest", "execution")
                         if key in slot} for slot in slots],
              "retention": frozen_record["entries"],
              "retention_path": "campaign/retention-%s.json" % tag,
              "frozen_core_digest": frozen_digest,
              "spent": spent,
              "model_output": "acquired bytes staged, published and executed"
                              " where parsed; all failures retained",
              "disposition": "complete", "acquired": acquired}
    target = Path(evidence_root) / "campaign" / ("%s.json" % tag)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(record, sort_keys=True, indent=2)
                        + "\n").encode())
    frozen_target = Path(evidence_root) / record["retention_path"]
    frozen_target.parent.mkdir(parents=True, exist_ok=True)
    frozen_target.write_bytes((json.dumps(frozen_record, sort_keys=True,
                                          indent=2) + "\n").encode())
    return record
