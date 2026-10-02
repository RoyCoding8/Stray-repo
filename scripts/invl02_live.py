"""Bounded live qualification driver for Investigation Learning 02.

Freeze commands write the exact protocol before any live effect. Run
commands refuse without a frozen protocol and without a human grant. E0
reports model bytes as retained unless a post-restart child proves the
same package bound. E1/E2 compare competent arms on both task structures
with reserved allocations. E3 is an eligibility screen and never executes a
candidate.
Recompute re-derives committed evidence offline with no gateway,
database or secrets. The frozen scripts/s09_pilot.py stays untouched.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

from experiments.ad01.live_construct import LiveGuard as _LiveGuard

STUDY_ROOT_E0 = "invl02-live-e0"
STUDY_ROOT_E12 = "invl02-live-e12"
STUDY_ROOT_OUTPUT = "invl02-output-shape-550b-r1"
E0_PROTOCOL_ID = "invl02-live-e0-v1"
E12_PROTOCOL_ID = "invl02-live-e12-v1"
OUTPUT_PROTOCOL_ID = "invl02-output-shape-550b-r1-v1"
LIVE_CODE_PATHS = (
    "scripts/invl02_live.py",
    "experiments/ad01/live_construct.py",
    "experiments/ad01/frontier.py",
    "experiments/ad01/improve_channel.py",
    "experiments/ad01/method_exec.py",
    "experiments/ad01/trajectory.py",
    "src/settlement/broker.py",
    "src/settlement/common.py",
    "src/settlement/config.py",
    "src/settlement/gateway.py",
    "src/settlement/gateway_http.py",
    "src/settlement/store.py",
)
LIVE_SOURCE_PATHS = (
    "experiments/ad01/boolean_rule.py",
    "experiments/ad01/live_construct.py",
    "experiments/ad01/policy_assess.py",
    "experiments/ad01/policy_step.py",
    "experiments/ad01/rule_learner.py",
)
OUTPUT_CODE_PATHS = (
    "scripts/invl02_live.py",
    "experiments/ad01/live_construct.py",
    "experiments/ad01/offline_recompute.py",
    "experiments/ad01/frontier.py",
    "src/settlement/gateway_http.py",
)
OUTPUT_SOURCE_PATHS = (
    "experiments/ad01/boolean_rule.py",
    "experiments/ad01/rule_learner.py",
    "experiments/ad01/live_construct.py",
)

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 3, "diagnostic_queries": 16,
        "model_calls": 6, "construction_tokens": 2048}

E0_TASKS = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"]
E0_USE_TASKS = ["ad01-w1-within-sw-00"]

E12_SOFTWARE_TASKS = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"]
E12_BOOLEAN_SEEDS = {"dev": [3, 7], "qual": [11], "audit": [23]}


def _canonical(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _digest(data) -> str:
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()


def _p0_incumbent() -> dict:
    from experiments.ad01 import boolean_rule as rules
    source = _canonical({
        "kind": "fixed-incumbent",
        "solver": "VersionSpaceLearner",
        "entrypoint": "experiments.ad01.rule_learner.VersionSpaceLearner",
        "class_digest": rules.class_digest(),
        "query_cap": 8,
    })
    return {"kind": "fixed-incumbent", "source": source,
            "source_digest": hashlib.sha256(source.encode()).hexdigest()}


def _require_grant() -> None:
    import os
    if not os.environ.get("S09_M5_LIVE_GRANT") and not os.environ.get(
            "INVL02_LIVE_GRANT"):
        raise ValueError("live runs require a fresh human grant")


def _live_model() -> str:
    import os
    model = os.environ.get("INVL02_LIVE_MODEL", "")
    if not model:
        raise ValueError("live model identifier is not configured")
    return model


def _live_route() -> dict:
    from experiments.ad01 import live_construct as live
    return dict(live.OUTPUT_ROUTE)


LIVE_ENV_PATH = "/home/ubuntu/.config/agent-society-live.env"


def _load_live_environment() -> None:
    import os
    import shlex
    path = Path(LIVE_ENV_PATH)
    if not path.is_file():
        raise ValueError("live environment file is unavailable")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in {"SETTLEMENT_GATEWAY_ENDPOINT",
                       "SETTLEMENT_GATEWAY_KEY", "INVL02_LIVE_GRANT",
                       "INVL02_LIVE_MODEL"}:
            continue
        parsed = shlex.split(value.strip(), posix=True)
        os.environ[key] = parsed[0] if parsed else ""


def _preflight_record(freeze: dict, route: dict) -> dict:
    return {
        "study_root": freeze.get("study_root"),
        "protocol": freeze.get("protocol"),
        "freeze_digest": freeze.get("freeze_digest"),
        "source_identity": freeze.get("source_identity"),
        "run_id": freeze.get("run_id"),
        "route": dict(route),
        "route_digest": _digest(route),
    }


def preflight_route(out, *, gateway=None) -> dict:
    from settlement.gateway import GatewayError
    from settlement.gateway_http import HttpGatewayAdapter
    out = Path(out)
    freeze_path = out / "freeze.json"
    if not freeze_path.is_file():
        raise ValueError("route preflight requires the frozen run")
    freeze = json.loads(freeze_path.read_text())
    study_root = freeze.get("study_root")
    if study_root in (STUDY_ROOT_E0, STUDY_ROOT_E12):
        _validate_live_freeze(freeze, study_root)
    elif study_root == STUDY_ROOT_OUTPUT:
        _validate_output_freeze(freeze)
    else:
        raise ValueError("route preflight study root is not current")
    route = freeze.get("route")
    if not isinstance(route, dict):
        raise ValueError("frozen route is missing")
    if gateway is None:
        _load_live_environment()
        import os
        endpoint = os.environ.get("SETTLEMENT_GATEWAY_ENDPOINT", "")
        api_key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
        if endpoint != route["endpoint"]:
            raise ValueError("live endpoint is not the frozen endpoint")
        gateway = HttpGatewayAdapter(
            endpoint=endpoint, api_key=api_key, api="responses",
            expected_route=route)
    result = gateway.preflight_route(route)
    if isinstance(result, GatewayError):
        reason = str(result.message)
        _write_preflight_refusal(out, freeze, reason)
        raise ValueError("model route preflight refused: %s" % reason)
    if result != route:
        reason = "preflight returned a different route"
        _write_preflight_refusal(out, freeze, reason)
        raise ValueError("model route %s" % reason)
    out.mkdir(parents=True, exist_ok=True)
    (out / "preflight.json").write_text(json.dumps(
        _preflight_record(freeze, result), sort_keys=True, indent=1) + "\n")
    return {"route": result}


def _live_gateway(expected_route: dict | None = None):
    from settlement.config import Settings
    from settlement.gateway_http import HttpGatewayAdapter
    return HttpGatewayAdapter.from_settings(
        Settings.from_env(), api="responses", expected_route=expected_route)


def _guard(gateway, *, pinned_model: str, ceiling: int,
           already_spent: int, expected_route: dict | None = None,
           automatic_retries: int | None = None):
    from experiments.ad01.live_construct import LiveGuard
    kwargs = {"pinned_model": pinned_model, "ceiling": ceiling,
              "already_spent": already_spent, "expected_route": expected_route}
    if automatic_retries is not None:
        kwargs["automatic_retries"] = automatic_retries
    return _OutputGuard(gateway, **kwargs)


def _already_spent() -> int:
    import os
    return int(os.environ.get("S09_STUDY_CALLS_ALREADY_SPENT", "0"))


class _OutputGuard(_LiveGuard):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replay_count = 0

    def infer(self, request, *, evidence=None):
        before = self.dispatch_count
        try:
            response = super().infer(request, evidence=evidence)
        except Exception:
            if request.operation_id in getattr(
                    self.delegate, "replayed_operation_ids", ()):
                self.dispatch_count = before
                self.replay_count += 1
            raise
        if request.operation_id in getattr(
                self.delegate, "replayed_operation_ids", ()):
            self.dispatch_count = before
            self.replay_count += 1
        return response

    def finalize_evidence(self, operation_id: str, **kwargs):
        entry = super().finalize_evidence(operation_id, **kwargs)
        if operation_id in getattr(
                self.delegate, "replayed_operation_ids", ()):
            entry["replay"] = True
            entry["new_dispatch"] = False
            if self.finalizations:
                self.finalizations[-1].update(
                    {"replay": True, "new_dispatch": False})
        return entry

    def guard_status(self):
        status = super().guard_status()
        status["replay_count"] = self.replay_count
        return status


def freeze_e0(out) -> dict:
    from experiments.ad01 import live_construct as live
    protocol = _live_freeze_fields(STUDY_ROOT_E0, {
        "study": "invl02-live-e0",
        "study_root": STUDY_ROOT_E0,
        "model": "grant-pinned",
        "route": dict(live.OUTPUT_ROUTE),
        "p0_incumbent": _p0_incumbent(),
        "bounds": {"model_calls": live.E0_CALL_CEILING,
                   "repairs": live.E0_REPAIR_CEILING,
                   "retries_per_call": live.MAX_RETRIES},
        "charter": dict(CHARTER), "caps": dict(CAPS),
        "tasks": list(E0_TASKS), "use_tasks": list(E0_USE_TASKS),
        "apparatus": "authored-control",
        "comparison": "live-treatment-vs-apparatus",
        "stop_rule": ("repeated empty responses trigger frozen repair or"
                      " stop, never silent model switch"),
    })
    protocol["route_digest"] = _digest(protocol["route"])
    protocol["freeze_digest"] = _digest(protocol)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "freeze.json").write_text(
        json.dumps(protocol, sort_keys=True, indent=1) + "\n")
    return protocol


def freeze_e12(out) -> dict:
    from experiments.ad01 import live_construct as live
    per_arm = {"init": live.PER_ARM_RESERVE - live.PER_ARM_REPAIRS,
               "repair": live.PER_ARM_REPAIRS}
    protocol = _live_freeze_fields(STUDY_ROOT_E12, {
        "study": STUDY_ROOT_E12,
        "study_root": STUDY_ROOT_E12,
        "model": "grant-pinned",
        "route": dict(live.OUTPUT_ROUTE),
        "p0_incumbent": _p0_incumbent(),
        "bounds": {"model_calls": live.STUDY_CALL_CEILING,
                   "per_arm": {"P1": dict(per_arm), "P2": dict(per_arm)},
                   "retries_per_call": live.MAX_RETRIES},
        "arms": ["P0", "P1", "P2"],
        "order": ["P1", "P2"],
        "software_tasks": list(E12_SOFTWARE_TASKS),
        "boolean_seeds": {k: list(v)
                          for k, v in E12_BOOLEAN_SEEDS.items()},
        "history": {"P1": [], "P2": _permitted_dev_history(
            E12_BOOLEAN_SEEDS["dev"])},
        "charter": dict(CHARTER), "caps": dict(CAPS),
        "comparison": "P1-without-history-vs-P2-with-history-vs-P0-fixed",
        "stop_rule": ("arm order cannot consume another arm's reserve;"
                      " missing candidates stay unavailable"),
    })
    worst = 2 * live.PER_ARM_RESERVE
    protocol["worst_case"] = worst
    if worst > live.STUDY_CALL_CEILING:
        raise ValueError("frozen worst case %d exceeds ceiling %d"
                         % (worst, live.STUDY_CALL_CEILING))
    protocol["route_digest"] = _digest(protocol["route"])
    protocol["freeze_digest"] = _digest(protocol)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "freeze.json").write_text(
        json.dumps(protocol, sort_keys=True, indent=1) + "\n")
    return protocol


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _digest_map(paths: tuple[str, ...], root: Path) -> dict:
    return {path: _file_digest(root / path) for path in paths}


def _live_source_identity(freeze: dict) -> str:
    return _digest({
        "code_digests": freeze.get("code_digests"),
        "source_digests": freeze.get("source_digests")})


def _require_live_digest_maps(freeze: dict, root: Path) -> None:
    for field, expected_paths in (
            ("code_digests", LIVE_CODE_PATHS),
            ("source_digests", LIVE_SOURCE_PATHS)):
        digests = freeze.get(field)
        if (not isinstance(digests, dict)
                or set(digests) != set(expected_paths)):
            raise ValueError("live %s digest paths are not exact" % field)
        for path in expected_paths:
            digest = digests[path]
            if (not isinstance(digest, str) or len(digest) != 64
                    or _file_digest(root / path) != digest):
                raise ValueError("live %s digest changed after freeze: %s" % (
                    field, path))
    if freeze.get("source_identity") != _live_source_identity(freeze):
        raise ValueError("live source identity does not match its digest maps")


def _validate_live_freeze(freeze: dict, study_root: str) -> None:
    protocol = E0_PROTOCOL_ID if study_root == STUDY_ROOT_E0 else E12_PROTOCOL_ID
    if (freeze.get("study") != study_root
            or freeze.get("study_root") != study_root):
        raise ValueError("live study root is retired or mismatched")
    if freeze.get("protocol") != protocol:
        raise ValueError("live protocol does not match the study root")
    if (not isinstance(freeze.get("run_id"), str)
            or not freeze["run_id"]):
        raise ValueError("live freeze run identity is missing")
    if freeze.get("freeze_digest") != _digest(
            {key: value for key, value in freeze.items()
             if key != "freeze_digest"}):
        raise ValueError("live freeze digest mismatch")
    if (freeze.get("route_digest") != _digest(freeze.get("route"))
            or freeze.get("source_identity") != _live_source_identity(freeze)):
        raise ValueError("live freeze route or source identity mismatch")
    _require_live_digest_maps(freeze, _repo_root())


def _live_freeze_fields(study_root: str, protocol: dict) -> dict:
    root = _repo_root()
    fields = {
        "protocol": (E0_PROTOCOL_ID if study_root == STUDY_ROOT_E0
                     else E12_PROTOCOL_ID),
        "run_id": uuid.uuid4().hex,
        "code_digests": _digest_map(LIVE_CODE_PATHS, root),
        "source_digests": _digest_map(LIVE_SOURCE_PATHS, root),
    }
    fields.update(protocol)
    fields["source_identity"] = _live_source_identity(fields)
    return fields


def _output_public_inputs() -> dict:
    from experiments.ad01 import live_construct as live
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import rule_learner
    inputs = {}
    for split, seed in live.OUTPUT_TASKS.items():
        task = rules.make_task(split, int(seed))
        session = rules.RuleSession(task)
        learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES,
                                                     int(seed))
        while session.remaining > 0:
            pick = learner.choose_query(dict(session.queried))
            if pick is None:
                break
            learner.observe(pick, session.query(pick))
        inputs["%s:%d" % (split, int(seed))] = session.model_input()
    return inputs


def _p0_output_incumbent(public_inputs: dict) -> dict:
    from experiments.ad01 import live_construct as live
    contract = _p0_incumbent()
    seals = {}
    for split, seed in live.OUTPUT_TASKS.items():
        task_id = "rule-%s-%04d" % (split, int(seed))
        seals[task_id] = {
            "split": split, "seed": int(seed),
            "public_input_digest": _digest(public_inputs[
                "%s:%d" % (split, int(seed))]),
        }
    contract["task_seals"] = seals
    return contract


def freeze_output(out) -> dict:
    from experiments.ad01 import live_construct as live
    permitted = live.output_permitted_history()
    public_inputs = _output_public_inputs()
    rendered = {}
    for arm, history in (("P1", []), ("P2", permitted)):
        for task_key, public_input in public_inputs.items():
            for attempt in (1, 2):
                rendered["%s:%s:a%d" % (arm, task_key, attempt)] = live.response_digest(
                    live.render_output_prompt(public_input, history, attempt))
    root = Path(__file__).resolve().parents[1]
    code_paths = OUTPUT_CODE_PATHS
    source_paths = OUTPUT_SOURCE_PATHS
    protocol = {
        "protocol": OUTPUT_PROTOCOL_ID,
        "study": STUDY_ROOT_OUTPUT,
        "study_root": STUDY_ROOT_OUTPUT,
        "run_id": uuid.uuid4().hex,
        "route": dict(live.OUTPUT_ROUTE),
        "arms": ["P0", "P1", "P2"],
        "order": ["P0", "P1", "P2"],
        "p0_incumbent": _p0_output_incumbent(public_inputs),
        "tasks": dict(live.OUTPUT_TASKS),
        "history": {
            "P1": {"entries": [], "digest": _digest([])},
            "P2": {"digest": _digest(permitted)},
        },
        "prompt": {
            "template": live.OUTPUT_PROMPT_TEMPLATE,
            "template_digest": live.response_digest(live.OUTPUT_PROMPT_TEMPLATE),
            "rendered_digests": rendered,
        },
        "limits": dict(live.OUTPUT_LIMITS),
        "code_digests": {path: _file_digest(root / path)
                         for path in code_paths},
        "source_digests": {path: _file_digest(root / path)
                           for path in source_paths},
        "stop_rule": ("stop on the first route mismatch, missing evidence, "
                      "or exhausted same-task repair budget; never change "
                      "limits after an effect"),
    }
    protocol["source_identity"] = _live_source_identity(protocol)
    protocol["freeze_digest"] = _digest(protocol)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "freeze.json").write_text(
        json.dumps(protocol, sort_keys=True, indent=1) + "\n")
    return protocol


def _require_output_digest_maps(freeze: dict, root: Path) -> None:
    for field, expected_paths in (
            ("code_digests", OUTPUT_CODE_PATHS),
            ("source_digests", OUTPUT_SOURCE_PATHS)):
        digests = freeze.get(field)
        if (not isinstance(digests, dict)
                or set(digests) != set(expected_paths)):
            raise ValueError("output %s digest paths are not exact" % field)
        for path in expected_paths:
            digest = digests[path]
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("output %s digest is malformed: %s" % (
                    field, path))
            if _file_digest(root / path) != digest:
                raise ValueError("output %s changed after freeze: %s" % (
                    field, path))


def _validate_output_freeze(freeze: dict) -> None:
    from experiments.ad01 import live_construct as live
    if freeze.get("protocol") != OUTPUT_PROTOCOL_ID:
        raise ValueError("run requires the 550b-r1 output-shape protocol")
    if freeze.get("study_root") != STUDY_ROOT_OUTPUT:
        raise ValueError("retired output evidence directory cannot be replayed")
    if (not isinstance(freeze.get("run_id"), str)
            or not freeze["run_id"]):
        raise ValueError("output freeze run identity is missing")
    if (freeze.get("arms") != ["P0", "P1", "P2"]
            or freeze.get("order") != ["P0", "P1", "P2"]):
        raise ValueError("output arm contract must include P0, P1, and P2")
    if freeze.get("freeze_digest") != _digest(
            {k: v for k, v in freeze.items() if k != "freeze_digest"}):
        raise ValueError("output freeze digest mismatch")
    if freeze.get("route") != live.OUTPUT_ROUTE:
        raise ValueError("output route does not match the frozen route")
    if freeze.get("limits") != live.OUTPUT_LIMITS:
        raise ValueError("output limits do not match the frozen protocol")
    if freeze.get("tasks") != live.OUTPUT_TASKS:
        raise ValueError("output tasks do not match the frozen protocol")
    p0 = freeze.get("p0_incumbent")
    expected_p0 = _p0_output_incumbent(_output_public_inputs())
    if (not isinstance(p0, dict)
            or p0.get("kind") != "fixed-incumbent"
            or p0.get("source") != expected_p0.get("source")
            or p0.get("source_digest") != expected_p0.get("source_digest")):
        raise ValueError("P0 incumbent contract is invalid")
    if p0.get("task_seals") != expected_p0.get("task_seals"):
        raise ValueError("P0 task seal changed after freeze")
    permitted = live.output_permitted_history()
    if freeze.get("history") != {
            "P1": {"entries": [], "digest": _digest([])},
            "P2": {"digest": _digest(permitted)}}:
        raise ValueError("output history contract changed after freeze")
    if freeze.get("prompt", {}).get("template_digest") != live.response_digest(
            live.OUTPUT_PROMPT_TEMPLATE):
        raise ValueError("output prompt template changed after freeze")
    root = Path(__file__).resolve().parents[1]
    _require_output_digest_maps(freeze, root)
    if freeze.get("source_identity") != _live_source_identity(freeze):
        raise ValueError("output source identity does not match its digest maps")


def _write_preflight_refusal(out: Path, freeze: dict, reason: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    record = _preflight_record(freeze, dict(freeze.get("route") or {}))
    record.update({"reason": str(reason), "dispatch_count": 0})
    (out / "preflight-refusal.json").write_text(json.dumps(
        record, sort_keys=True, indent=1) + "\n")


def _require_route_preflight(out: Path, freeze: dict, label: str) -> None:
    path = out / "preflight.json"
    if not path.is_file():
        reason = "%s preflight record is missing" % label
        _write_preflight_refusal(out, freeze, reason)
        raise ValueError(reason)
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        reason = "%s preflight record is unreadable: %s" % (label, exc)
        _write_preflight_refusal(out, freeze, reason)
        raise ValueError(reason) from exc
    if record != _preflight_record(
            freeze, dict(freeze.get("route") or {})):
        reason = "%s preflight identity does not match the current run" % label
        _write_preflight_refusal(out, freeze, reason)
        raise ValueError(reason)


def _require_output_preflight(out: Path, freeze: dict) -> None:
    path = out / "preflight.json"
    if not path.is_file():
        _require_route_preflight(out, freeze, "output")
    record = json.loads(path.read_text())
    if record == _preflight_record(freeze, dict(freeze["route"])):
        return
    if (not isinstance(record, dict)
            or record.get("route") != freeze.get("route")
            or record.get("route_digest") != _digest(freeze.get("route"))):
        _require_route_preflight(out, freeze, "output")
    preflight_route(out, gateway=_live_gateway(freeze["route"]))
    _require_route_preflight(out, freeze, "output")


def _receipt_measurement_status(receipt: dict) -> str:
    from experiments.ad01 import offline_recompute as _m4
    return _m4.receipt_measurement_status(receipt)


def _bind_output_dispatches(dispatches: list, durable_receipts: list) -> tuple[list, list]:
    by_operation = {
        entry.get("operation_id"): entry for entry in dispatches
        if isinstance(entry, dict) and isinstance(entry.get("operation_id"), str)
    }
    bound_dispatches = []
    bound_receipts = []
    used = set()
    for dispatch in dispatches:
        if not isinstance(dispatch, dict):
            bound_dispatches.append(dispatch)
            continue
        merged = dict(dispatch)
        operation_id = dispatch.get("operation_id")
        initial = dispatch.get("dispatch_evidence_digest") or dispatch.get(
            "evidence_digest")
        merged["initial_evidence_digest"] = initial
        receipt = next((row for row in durable_receipts
                        if isinstance(row, dict)
                        and row.get("operation_id") == operation_id), None)
        if receipt is None:
            merged["durable_receipt"] = None
            merged["durable_receipt_identity"] = None
        else:
            durable = dict(receipt)
            for key in (
                    "source_digest", "artifact_digest", "input_digest",
                    "result_digest", "dispatch_evidence_digest"):
                if durable.get(key) is None:
                    durable[key] = dispatch.get(key)
            durable["initial_evidence_digest"] = initial
            durable["measurement_status"] = _receipt_measurement_status(
                durable)
            merged["durable_receipt"] = durable
            merged["durable_receipt_identity"] = durable.get(
                "receipt_identity")
            if operation_id not in used:
                bound_receipts.append(durable)
            used.add(operation_id)
        bound_dispatches.append(merged)
    for receipt in durable_receipts:
        if (isinstance(receipt, dict)
                and receipt.get("operation_id") not in used
                and receipt.get("operation_id") not in by_operation):
            durable = dict(receipt)
            durable["initial_evidence_digest"] = None
            durable["measurement_status"] = _receipt_measurement_status(
                durable)
            bound_receipts.append(durable)
    return bound_dispatches, bound_receipts


def _durable_conflict_exports(conflicts, exposure) -> list:
    exported = []
    for row in conflicts or []:
        content = row.get("content") if isinstance(row, dict) else None
        content = content if isinstance(content, dict) else {}
        receipt_content = content.get("receipt_content")
        receipt_content = receipt_content if isinstance(receipt_content, dict) \
            else content
        usage = receipt_content.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        exported.append({
            "receipt_identity": row.get("receipt_identity")
            if isinstance(row, dict) else None,
            "outcome": content.get("outcome"),
            "usage": usage,
            "unresolved_exposure": exposure,
        })
    return exported


class _DurableBrokerOutput:
    def __init__(self, dsn: str, gateway, *, allocation_id: str,
                 expected_route: dict) -> None:
        self.dsn = dsn
        self.gateway = gateway
        self.allocation_id = allocation_id
        self.expected_route = dict(expected_route)
        self.durable_receipts: list[dict] = []
        self.partial_dispatches: list[dict] = []
        self.replayed_operation_ids: set[str] = set()
        self.last_replay = False

    def _record_durable(self, receipt: dict) -> None:
        operation_id = receipt.get("operation_id")
        if receipt.get("outcome") not in ("conflict", "ambiguous", "unresolved"):
            self.durable_receipts = [row for row in self.durable_receipts
                                     if row.get("operation_id") != operation_id]
        self.durable_receipts.append(receipt)

    def infer(self, request):
        self.last_replay = False
        from settlement import broker, store
        from settlement.common import ResultCode
        from settlement.gateway import (
            GatewayError,
            GatewayErrorKind,
            ModelResponse,
            Usage,
        )
        payload = {
            "model": request.model,
            "messages": list(request.messages),
            "max_output_tokens": request.max_output_tokens,
            "deadline_ms": request.deadline_ms,
        }
        prepared = broker.ensure_operation(
            self.dsn,
            operation_id=request.operation_id,
            effect=broker.MODEL_INFERENCE,
            payload=payload,
            allocation_id=self.allocation_id,
            retries=0,
        )
        if prepared.code not in (ResultCode.APPLIED,
                                 ResultCode.ALREADY_APPLIED):
            raise RuntimeError("durable broker refused %s: %s" % (
                request.operation_id, prepared.detail))
        if prepared.code == ResultCode.ALREADY_APPLIED:
            prior = broker.read_operation(self.dsn, request.operation_id) or {}
            prior_receipts = list(store.operation_receipts(
                self.dsn, request.operation_id) or [])
            prior_conflicts = store.operation_receipt_conflicts(
                self.dsn, request.operation_id)
            prior_settled = prior.get("settled") is True
            if prior_settled:
                self.last_replay = True
                self.replayed_operation_ids.add(request.operation_id)
                if len(prior_receipts) != 1 or prior_conflicts:
                    durable = {
                        "operation_id": request.operation_id,
                        "reservation_id": prior.get("reservation_id"),
                        "receipt_identity": None,
                        "receipt_outcome": "conflict",
                        "outcome": "conflict",
                        "usage": {},
                        "exposure": prior.get("exposure"),
                        "unresolved_exposure": prior.get("exposure"),
                        "dispatch_state": prior.get("dispatch_state", "conflict"),
                        "reconcile_state": prior.get("reconcile_state", "conflict"),
                        "settled": True,
                        "unsettled": False,
                        "conflict": True,
                        "conflict_count": len(prior_conflicts),
                        "receipt_conflicts": _durable_conflict_exports(
                            prior_conflicts, prior.get("exposure")),
                    }
                    durable["measurement_status"] = _receipt_measurement_status(
                        durable)
                    self._record_durable(durable)
                    raise RuntimeError(
                        "durable broker replay has multiple terminal receipts")
                row = prior_receipts[0]
                content = row.get("content") or {}
                durable_usage = content.get("usage") or {}
                durable_text = content.get("text")
                durable_result = (
                    {"raw_response": durable_text}
                    if row.get("outcome") == "success"
                    and isinstance(durable_text, str) and durable_text else None)
                durable = {
                    "operation_id": request.operation_id,
                    "reservation_id": prior.get("reservation_id"),
                    "receipt_identity": row.get("receipt_identity"),
                    "receipt_outcome": row.get("outcome"),
                    "outcome": row.get("outcome"),
                    "usable_result": bool(durable_result),
                    "result": durable_result,
                    "result_digest": (_digest(durable_result)
                                      if durable_result is not None else None),
                    "usage": durable_usage,
                    "exposure": 0,
                    "unresolved_exposure": 0,
                    "dispatch_state": prior.get("dispatch_state", "observed"),
                    "reconcile_state": prior.get("reconcile_state", "none"),
                    "settled": True,
                    "unsettled": False,
                    "conflict": False,
                    "conflict_count": 0,
                    "receipt_conflicts": [],
                }
                durable["measurement_status"] = _receipt_measurement_status(
                    durable)
                self._record_durable(durable)
                usage = Usage(
                    input_tokens=durable_usage.get("input_tokens"),
                    output_tokens=durable_usage.get("output_tokens"),
                    charge_units=durable_usage.get("charge_units"),
                    charge_scale=durable_usage.get("charge_scale"),
                    provider_enforced_ceiling=bool(
                        durable_usage.get("provider_enforced_ceiling", False)),
                    billed=durable_usage.get("billed"))
                if row.get("outcome") != "success":
                    return GatewayError(
                        GatewayErrorKind.PROTOCOL,
                        str(content.get("error", "durable replay failure")),
                        False, request.operation_id, usage)
                return ModelResponse(
                    request.operation_id,
                    str(content.get("text", "")),
                    dict(content.get("model_meta") or {}),
                    usage,
                    str(content.get("stop_reason", "")))
        try:
            dispatched = broker.dispatch_operation(
                self.dsn, request.operation_id, gateway=self.gateway)
        except Exception as exc:
            from experiments.ad01 import frontier as _frontier
            prompt = "".join(
                str(message.get("content", ""))
                for message in request.messages
                if message.get("role") == "user")
            partial = _frontier.make_evidence_record(
                "gateway-dispatch", request.operation_id, "unresolved",
                input_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                details={"raw_payload": {"raw_prompt": prompt,
                                         "raw_response": None},
                         "exception_class": type(exc).__name__,
                         "exception_reason": str(exc)})
            partial.update({"prompt_digest": hashlib.sha256(
                prompt.encode("utf-8")).hexdigest(),
                "raw_prompt": prompt, "raw_response": None,
                "response_digest": None,
                "parse_outcome": "transport-error"})
            self.partial_dispatches.append(partial)
            raise
        receipts = list(store.operation_receipts(
            self.dsn, request.operation_id) or [])
        conflicts = store.operation_receipt_conflicts(
            self.dsn, request.operation_id)
        operation = broker.read_operation(self.dsn, request.operation_id) or {}
        receipt_outcomes = {row.get("outcome") for row in receipts
                            if isinstance(row, dict)}
        dispatch_state = getattr(dispatched, "dispatch_state", operation.get(
            "dispatch_state", "unknown"))
        reconcile_state = getattr(dispatched, "reconcile_state", operation.get(
            "reconcile_state", "unknown"))
        conflict = (reconcile_state == "conflict"
                    or dispatch_state == "conflict"
                    or bool(conflicts)
                    or len(receipt_outcomes & {"success", "failure"}) > 1)
        unresolved = (reconcile_state == "unresolved"
                      or dispatch_state == "unresolved"
                      or "unknown" in receipt_outcomes)
        ambiguous = len(receipts) > 1 and not conflict and not unresolved
        exposure = ((prepared.data or {}).get("exposure")
                    or operation.get("exposure"))
        settled = getattr(dispatched, "settled", operation.get(
            "settled", False)) is True
        conflict_exports = _durable_conflict_exports(conflicts, exposure)
        if conflict or unresolved or ambiguous or not settled:
            for row in receipts or [{}]:
                content = row.get("content") or {}
                durable_usage = content.get("usage") or {}
                durable = {
                    "operation_id": request.operation_id,
                    "reservation_id": ((prepared.data or {}).get("reservation_id")
                                       or operation.get("reservation_id")),
                    "receipt_identity": row.get("receipt_identity"),
                    "receipt_outcome": row.get("outcome"),
                    "outcome": ("conflict" if conflict else
                                "ambiguous" if ambiguous else "unresolved"),
                    "usage": durable_usage,
                    "exposure": exposure,
                    "unresolved_exposure": exposure if (
                        conflict or unresolved or ambiguous or not settled) else 0,
                    "dispatch_state": dispatch_state,
                    "reconcile_state": reconcile_state,
                    "settled": settled,
                    "unsettled": not settled,
                    "conflict": bool(conflict),
                    "conflict_count": len(conflicts),
                    "receipt_conflicts": conflict_exports,
                }
                durable["measurement_status"] = _receipt_measurement_status(
                    durable)
                self._record_durable(durable)
            if conflict:
                reason = "receipt conflict"
            elif ambiguous:
                reason = "ambiguous receipt set"
            elif not settled:
                reason = "unsettled or unresolved"
            else:
                reason = "reconciliation is unresolved"
            raise RuntimeError("durable broker %s for %s"
                               % (reason, request.operation_id))
        if not receipts:
            raise RuntimeError("durable broker returned no receipt for %s: %s" % (
                request.operation_id, dispatched.next_decision))
        receipt = receipts[0]
        content = receipt.get("content") or {}
        durable_usage = content.get("usage") or {}
        durable_text = content.get("text")
        durable_result = (
            {"raw_response": durable_text}
            if receipt.get("outcome") == "success"
            and isinstance(durable_text, str) and durable_text else None)
        durable = {
            "operation_id": request.operation_id,
            "reservation_id": ((prepared.data or {}).get("reservation_id")
                               or operation.get("reservation_id")),
            "receipt_identity": receipt.get("receipt_identity"),
            "receipt_outcome": receipt.get("outcome"),
            "outcome": receipt.get("outcome"),
            "usable_result": bool(durable_result),
            "result": durable_result,
            "result_digest": (_digest(durable_result)
                              if durable_result is not None else None),
            "usage": durable_usage,
            "exposure": exposure,
            "unresolved_exposure": 0,
            "dispatch_state": dispatch_state,
            "reconcile_state": reconcile_state,
            "settled": settled,
            "unsettled": False,
            "conflict": False,
            "conflict_count": 0,
            "receipt_conflicts": [],
        }
        durable["measurement_status"] = _receipt_measurement_status(durable)
        self._record_durable(durable)
        usage = Usage(
            input_tokens=durable_usage.get("input_tokens"),
            output_tokens=durable_usage.get("output_tokens"),
            charge_units=durable_usage.get("charge_units"),
            charge_scale=durable_usage.get("charge_scale"),
            provider_enforced_ceiling=bool(
                durable_usage.get("provider_enforced_ceiling", False)),
            billed=durable_usage.get("billed"),
        )
        if receipt.get("outcome") != "success":
            message = str(content.get("error", "durable gateway failure"))
            if "route" in message.lower():
                return ModelResponse(
                    request.operation_id, "",
                    {"adapter": "durable-broker",
                     "endpoint": self.expected_route.get("endpoint"),
                     "model": self.expected_route.get("resolved_model"),
                     "provider": self.expected_route.get("provider"),
                     "tier": self.expected_route.get("tier"),
                     "route_error": message},
                    usage, "route-refused")
            return GatewayError(
                GatewayErrorKind.PROTOCOL, message, False,
                request.operation_id, usage)
        return ModelResponse(
            request.operation_id,
            str(content.get("text", "")),
            dict(content.get("model_meta") or {}),
            usage,
            str(content.get("stop_reason", "")),
        )

    def check_discovery(self):
        return self.gateway.check_discovery()

    def check_auth(self):
        return self.gateway.check_auth()

    def cancel(self, operation_id):
        return self.gateway.cancel(operation_id)


def _output_public_task(split: str, seed: int):
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import rule_learner
    task = rules.make_task(split, int(seed))
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, int(seed))
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        learner.observe(pick, session.query(pick))
    return task, session


def _is_route_refusal(value) -> bool:
    reason = str(getattr(value, "reason", value)).lower()
    return "route" in reason and (
        "refus" in reason or "mismatch" in reason
        or ("returned" in reason and "match" in reason))


def _output_task(guard, *, arm: str, split: str, seed: int,
                 history: list, freeze: dict) -> dict:
    from experiments.ad01 import live_construct as live
    from settlement.gateway import GatewayError, ModelRequest
    task, session = _output_public_task(split, int(seed))
    public_input = session.model_input()
    accepted = None
    score = None
    for attempt in (1, 2):
        prompt = live.render_output_prompt(public_input, history, attempt)
        expected_digest = freeze["prompt"]["rendered_digests"].get(
            "%s:%s:%d:a%d" % (arm, split, int(seed), attempt))
        if live.response_digest(prompt) != expected_digest:
            raise ValueError("output rendered prompt is not frozen")
        operation_id = live.output_operation_id(arm, split, int(seed),
                                                 attempt)
        evidence = {"arm": arm, "task": task["task_id"],
                    "attempt": attempt, "raw_prompt": prompt}
        try:
            response = guard.infer(ModelRequest(
                model=guard.pinned_model,
                messages=({"role": "user", "content": prompt},),
                max_output_tokens=freeze["limits"]["max_output_tokens"],
                deadline_ms=300_000, operation_id=operation_id),
                evidence=evidence)
        except live.LiveRefused as exc:
            return {"accepted": False, "route_refused": _is_route_refusal(exc)}
        if isinstance(response, GatewayError):
            route_refused = _is_route_refusal(response)
            if route_refused:
                finalized = guard.finalized_dispatches()
                if finalized:
                    finalized[-1]["parse_outcome"] = "route-refused"
            return {"accepted": False, "route_refused": route_refused}
        text = response.text
        if len(text) > freeze["limits"]["max_response_characters"]:
            guard.finalize_evidence(operation_id, parse_outcome="too-long")
            continue
        if not text.strip():
            guard.finalize_evidence(operation_id, parse_outcome="empty")
            continue
        try:
            candidate = live.extract_and_validate_boolean(text)
            committed = session.commit_predictor(candidate)
        except Exception:
            guard.finalize_evidence(operation_id, parse_outcome="parse-failed")
            if attempt < 2:
                continue
            return {"accepted": False, "route_refused": False}
        accepted = _digest(candidate)
        score = session.score(committed)
        guard.finalize_evidence(
            operation_id, parse_outcome="accepted",
            accepted_candidate_digest=accepted,
            parsed_source_digest=accepted)
        break
    return {"accepted": accepted is not None,
            "candidate_digest": accepted,
            "score": score,
            "task_id": task["task_id"],
            "queries": len(session.queried),
            "route_refused": False}


def _scorer_private_envelope(freeze: dict, scores: list) -> dict:
    from experiments.ad01 import offline_recompute as offline
    private = {
        "schema": offline.SCORER_PRIVATE_SCHEMA,
        "protocol": freeze["protocol"],
        "study": freeze["study"],
        "study_root": freeze["study_root"],
        "run_id": freeze["run_id"],
        "source_identity": freeze["source_identity"],
        "freeze_digest": freeze["freeze_digest"],
        "scores": list(scores),
    }
    private["envelope_digest"] = offline.source_digest(
        offline.canonical(private))
    return private


def run_output(out, *, gateway, model: str) -> dict:
    from experiments.ad01 import live_construct as live
    from experiments.ad01 import offline_recompute as offline
    out = Path(out)
    freeze = json.loads((out / "freeze.json").read_text())
    _validate_output_freeze(freeze)
    if model != freeze["route"]["requested_model"]:
        raise ValueError("output model does not match the frozen request")
    incumbent_control = []
    private_p0_scores = []
    p0 = freeze["p0_incumbent"]
    for split, seed in freeze["tasks"].items():
        result = _run_p0_boolean(split, int(seed))
        predictor = {"specs": result["predictor_specs"],
                     "tables": result["predictor_tables"]}
        result_digest = hashlib.sha256(
            _canonical(predictor).encode()).hexdigest()
        control = {
            "arm": "P0", "executed": "incumbent",
            "task_id": result["task_id"], "split": split, "seed": int(seed),
            "source_digest": p0["source_digest"],
            "predictor_digest": result["predictor_digest"],
            "result_digest": result_digest, "queries": result["queries"],
            "model_calls": 0, "predictor": predictor,
        }
        incumbent_control.append(control)
        private_p0_scores.append({
            "arm": "P0", "task_id": result["task_id"], "split": split,
            "seed": int(seed), "score": result["score"],
            "queries": result["queries"],
            "predictor_digest": result["predictor_digest"],
            "result_digest": result_digest,
            "source_digest": p0["source_digest"]})
    permitted = live.output_permitted_history()
    guard = _OutputGuard(
        gateway, pinned_model=model,
        ceiling=freeze["limits"]["max_dispatches"],
        automatic_retries=freeze["limits"]["automatic_retries"],
        expected_route=freeze["route"])
    scores = list(private_p0_scores)
    arm_status = {"P0": True}
    study_route_refused = False
    for arm in freeze["order"]:
        if arm == "P0":
            continue
        history = [] if arm == "P1" else list(permitted)
        accepted = 0
        for split, seed in freeze["tasks"].items():
            result = _output_task(
                guard, arm=arm, split=split, seed=int(seed),
                history=history, freeze=freeze)
            if result["accepted"]:
                accepted += 1
                scores.append({"arm": arm, "task_id": result["task_id"],
                               "split": split, "seed": int(seed),
                               "score": result["score"],
                               "queries": result["queries"],
                               "candidate_digest": result["candidate_digest"]})
            if result["route_refused"]:
                study_route_refused = True
                break
        arm_status[arm] = accepted == len(freeze["tasks"])
        if study_route_refused:
            break
    dispatches, durable_receipts = _bind_output_dispatches(
        guard.finalized_dispatches(),
        list(getattr(guard.delegate, "durable_receipts", [])))
    operation_counts = {}
    for dispatch in dispatches:
        if dispatch.get("replay", False):
            continue
        operation_id = dispatch.get("operation_id")
        operation_counts[operation_id] = operation_counts.get(operation_id, 0) + 1
    automatic_retry_count = sum(max(0, count - 1)
                                for count in operation_counts.values())
    physical_dispatch_count = sum(operation_counts.values())
    replay_count = sum(1 for dispatch in dispatches
                       if dispatch.get("replay", False))
    result = {
        "schema": offline.OUTPUT_SCHEMA,
        "protocol": freeze,
        "protocol_id": freeze["protocol"],
        "study": freeze["study"],
        "study_root": freeze["study_root"],
        "run_id": freeze["run_id"],
        "source_identity": freeze["source_identity"],
        "freeze_digest": freeze["freeze_digest"],
        "status": "available" if all(arm_status.values()) else "incomplete",
        "candidate_view": {"protocol": freeze["protocol"],
                           "route": dict(freeze["route"]),
                           "incumbent_control": incumbent_control,
                           "dispatch_count": len(dispatches),
                           "physical_dispatch_count": physical_dispatch_count,
                           "replay_count": replay_count,
                           "automatic_retry_count": automatic_retry_count,
                           "dispatches": dispatches,
                           "durable_receipts": durable_receipts},
    }
    private = _scorer_private_envelope(freeze, scores)
    (out / "output-run.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n")
    (out / "scorer-private.json").write_text(
        json.dumps(private, sort_keys=True, indent=1) + "\n")
    return result


def _output_unavailable(out: Path, freeze: dict, reason: str,
                        durable_receipts: list | None = None,
                        dispatches: list | None = None) -> dict:
    from experiments.ad01 import offline_recompute as offline
    partial = list(dispatches or [])
    result = {
        "schema": offline.OUTPUT_SCHEMA,
        "protocol": freeze,
        "protocol_id": freeze.get("protocol"),
        "study": freeze.get("study"),
        "study_root": freeze.get("study_root"),
        "run_id": freeze.get("run_id"),
        "source_identity": freeze.get("source_identity"),
        "freeze_digest": freeze.get("freeze_digest"),
        "status": "unavailable",
        "reason": reason,
        "candidate_view": {
            "protocol": freeze.get("protocol"),
            "route": dict(freeze.get("route") or {}),
            "incumbent_control": [],
            "dispatch_count": len(partial),
            "physical_dispatch_count": len(partial),
            "replay_count": 0,
            "automatic_retry_count": 0,
            "dispatches": partial,
            "durable_receipts": list(durable_receipts or []),
        },
    }
    (out / "output-run.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n")
    (out / "scorer-private.json").write_text(json.dumps(
        _scorer_private_envelope(freeze, []), sort_keys=True, indent=1) + "\n")
    return result


def run_output_live(dsn: str, out) -> dict:
    _require_grant()
    out = Path(out)
    freeze = json.loads((out / "freeze.json").read_text())
    _validate_output_freeze(freeze)
    model = _live_model()
    if model != freeze["route"]["requested_model"]:
        raise ValueError("output model does not match the frozen request")
    try:
        _require_output_preflight(out, freeze)
    except Exception as exc:
        return _output_unavailable(
            out, freeze, "output preflight unavailable before authority: %s" % exc)
    try:
        authority = _authorize(
            dsn, STUDY_ROOT_OUTPUT,
            200_000,
            {"model_calls": freeze["limits"]["max_dispatches"],
             "construction_calls": 0})
        allocation_id = authority.get("allocation_id")
        if not allocation_id:
            raise ValueError("durable study allocation is unavailable")
        gateway = _live_gateway(freeze["route"])
        endpoint = getattr(gateway, "endpoint", freeze["route"]["endpoint"])
        if endpoint.rstrip("/") != freeze["route"]["endpoint"].rstrip("/"):
            raise ValueError("output preflight route does not match the freeze")
        preflight_route(out, gateway=gateway)
        from settlement import broker
        broker.scan_prepared(dsn, limit=1)
        durable_gateway = _DurableBrokerOutput(
            dsn, gateway, allocation_id=allocation_id,
            expected_route=freeze["route"])
    except Exception as exc:
        return _output_unavailable(
            out, freeze, "durable broker unavailable before inference: %s" % exc)
    try:
        result = run_output(out, gateway=durable_gateway, model=model)
    except Exception as exc:
        if not durable_gateway.durable_receipts:
            return _output_unavailable(
                out, freeze,
                "durable broker unavailable before inference: %s" % exc,
                durable_gateway.durable_receipts,
                durable_gateway.partial_dispatches)
        return _output_unavailable(
            out, freeze,
            "durable broker refused an output dispatch: %s" % exc,
            durable_gateway.durable_receipts,
            durable_gateway.partial_dispatches)
    if any(not isinstance(dispatch.get("durable_receipt"), dict)
           for dispatch in result.get("candidate_view", {}).get(
               "dispatches", [])):
        return _output_unavailable(
            out, freeze,
            "durable broker receipt missing for a physical output dispatch",
            result.get("candidate_view", {}).get("durable_receipts", []),
            result.get("candidate_view", {}).get("dispatches", []))
    return result


def _authorize(dsn: str, study_root: str, authorized: int,
               ceilings: dict) -> dict:
    from experiments.ad01 import trajectory
    return trajectory.authorize_campaign(
        dsn, study_root, authorized=authorized, study_root=study_root,
        ceilings=ceilings)


def _live_environments(freeze: dict) -> list:
    envs = [{"instrument": "boolean-rule-v1", "split": "dev",
             "seed": 4}]
    for task_id in list(freeze.get("tasks") or []) + list(
            freeze.get("use_tasks") or []):
        envs.append({"instrument": "deliberation",
                     "target": str(task_id)})
    for seed in list((freeze.get("boolean_seeds") or {}).get(
            "dev") or []) + list((freeze.get("boolean_seeds") or {}).get(
            "qual") or []):
        envs.append({"instrument": "boolean-rule-v1", "split": "dev",
                     "seed": int(seed)})
    seen = []
    for env in envs:
        if env not in seen:
            seen.append(env)
    return seen


def _live_opportunities(freeze: dict) -> list:
    from experiments.ad01 import live_construct as _live
    opportunities = []
    for idx, task_id in enumerate(list(freeze.get("tasks") or [])):
        opportunities.append(_live.live_opportunity(
            "opp-sw-%d" % idx, str(task_id),
            "examine %s within authority" % task_id,
            instrument="deliberation"))
    for idx, task_id in enumerate(list(freeze.get("use_tasks") or [])):
        opportunities.append(_live.live_opportunity(
            "opp-use-%d" % idx, str(task_id),
            "reuse acquired method on %s" % task_id,
            instrument="deliberation"))
    for seed in list((freeze.get("boolean_seeds") or {}).get(
            "dev") or []) + list((freeze.get("boolean_seeds") or {}).get(
            "qual") or []):
        opportunities.append(_live.live_opportunity(
            "opp-rule-dev-%d" % int(seed), "rule-dev-%04d" % int(seed),
            "what does a probe reveal on rule-dev-%04d" % int(seed),
            instrument="boolean-rule-v1", x=3))
    have_tasks = {o.get("intervention", {}).get("target")
                  for o in opportunities}
    have_ids = {o.get("opportunity_id") for o in opportunities}
    if "opp-first" not in have_ids:
        opportunities.append(_live.live_opportunity(
            "opp-first", "rule-dev-0004",
            "what does input 3 reveal on rule-dev-0004",
            instrument="boolean-rule-v1", x=3))
    if "opp-followup" not in have_ids:
        opportunities.append(_live.live_opportunity(
            "opp-followup", "rule-dev-0005",
            "what does input 11 reveal on rule-dev-0005",
            instrument="boolean-rule-v1", x=11))
    if "rule-dev-0004" not in have_tasks:
        opportunities.append(_live.live_opportunity(
            "opp-rule-dev-4", "rule-dev-0004",
            "what does input 3 reveal on rule-dev-0004",
            instrument="boolean-rule-v1", x=3))
    if "rule-dev-0005" not in have_tasks:
        pass
    if not opportunities:
        opportunities.append(_live.live_opportunity(
            "opp-rule-dev-4", "rule-dev-0004",
            "what does input 3 reveal on rule-dev-0004",
            instrument="boolean-rule-v1", x=3))
    return opportunities


def _run_frontier_investigation(store_path, freeze: dict, label: str, *,
                                guard=None, model: str = "",
                                history: list | None = None) -> dict:
    from experiments.ad01 import boolean_rule as _rules
    from experiments.ad01 import frontier as _frontier
    from experiments.ad01 import improve_channel as _channel
    from experiments.ad01 import live_construct as _live
    mission = _live.live_mission(
        str(freeze.get("charter", {}).get(
            "objective", _live.LIVE_MISSION_OBJECTIVE)),
        _live_environments(freeze))
    store = _live.ensure_live_store(
        store_path, mission, dict(_live.LIVE_AUTHORITY))
    _live.propose_live_work(store, _live_opportunities(freeze))
    if store.active_package is None:
        active = _live.bind_live_control(store, "low")
    else:
        active = store.active_package
    assert active.get("origin") == "authored-control"
    preserved = [{"observation_id": "obs-seed",
                  "task": "rule-dev-0004", "verdict": "preserved"}]
    mismatch = [{"observation_id": "obs-seed",
                 "task": "rule-dev-0004", "verdict": "mismatch"}]
    choice_preserved = _live.choose_next_work(store, active, preserved)
    choice_mismatch = _live.choose_next_work(store, active, mismatch)
    task = _rules.make_task("dev", 4)
    probe_action = {"kind": "probe",
                    "inputs": {"opportunity_id": "opp-rule-dev-4",
                               "x": 3},
                    "requested_resources": {"queries": 1, "steps": 1}}
    try:
        effect = _live.execute_chosen_work(store, probe_action, task)
    except Exception as exc:
        effect = {"status": "refused", "reason": str(exc)}
    first = _live.run_live_improve_round(store, task, active, 1)
    candidate = first["candidate"]
    assert candidate.get("origin") == "authored-control"
    assert candidate.get("source_kind") == "fixed-menu"
    pending = [e for e in store.pending_effects]
    if pending:
        if not store.observations:
            raise _live.LiveRefused(
                "pending effect has no attributable observation")
        for eff in list(pending):
            store.settle(eff["effect_id"], store.observations[-1])
    try:
        activated = _live.activate_control_revision(store, candidate)
        adopted = {"status": "activated-control",
                   "package_digest": activated["package_digest"],
                   "control_id": activated["control_id"]}
    except Exception as exc:
        adopted = {"status": "refused", "reason": str(exc)}
    store.save()
    restarted = _live.restart_store(store_path)
    assert restarted.active_digest == store.active_digest
    active2 = restarted.active_package
    second = _live.run_live_improve_round(restarted, task, active2, 2)
    assert second["candidate"]["parent_digest"] == \
        active2["package_digest"]
    assert {e["executed_digest"] for e in second["log"]} == \
        {active2["imp_digest"]}
    acquisition: dict = {"status": "not-attempted"}
    if guard is not None:
        from settlement.gateway import GatewayError, ModelRequest
        history = list(history or [])
        prompt = ("Reply with exactly one JSON object and nothing else,"
                  " shaped {\"entry\": \"<complete python STEP source>\"}."
                  " STEP must be def STEP(view, state) returning"
                  " {\"action\": <object>, \"state\": <object>}.")
        if history:
            prompt += " Permitted development history: %s." % _canonical(history)
        try:
            operation_id = "invl02-live-imp-%s" % label
            response = guard.infer(ModelRequest(
                model=model, messages=({"role": "user",
                                        "content": prompt},),
                max_output_tokens=2048, deadline_ms=300_000,
                operation_id=operation_id),
                evidence={"arm": label, "task": task["task_id"],
                          "attempt": 1, "raw_prompt": prompt})
            if isinstance(response, GatewayError):
                raise ValueError("live improver transport: %s"
                                 % response.message)
            text = (response.text or "").strip()
            if not text:
                raise ValueError("live improver empty completion")
            dispatch = guard.provenance(operation_id)
            package = _live.parse_and_build_live_package(
                restarted.active_package, response.text,
                "acquired-live-%s-r1" % label, dispatch=dispatch)
            restarted.record_evidence(dispatch)
            dispatch = guard.finalize_evidence(
                operation_id, parse_outcome="accepted",
                accepted_candidate_digest=package["package_digest"],
                parsed_source_digest=package["imp_digest"],
                package_digest=package["package_digest"],
                parent_digest=package["parent_digest"], round_no=1)
            _live.retain_acquired(restarted, package, dispatch)
            acquisition = {
                "status": "retained",
                "arm": label,
                "control_id": package["control_id"],
                "package_digest": package["package_digest"],
                "parent_digest": package["parent_digest"],
                "response_digest": package["response_digest"],
                "response_source_digest": package[
                    "response_source_digest"],
                "dispatch_evidence_digest": dispatch[
                    "dispatch_evidence_digest"]}
        except Exception as exc:
            acquisition = {"status": "unavailable",
                           "reason": str(exc)}
    acquired_digests = {c["package_digest"] for c in
                        restarted.treatment_arms["acquired"]}
    for which in ("low", "high"):
        assert _channel.make_control(
            which)["package_digest"] not in acquired_digests
    return {"label": label,
            "store_path": str(store_path),
            "active_digest": active["package_digest"],
            "choice_preserved": choice_preserved["choice"],
            "choice_mismatch": choice_mismatch["choice"],
            "observation_dependent": (
                choice_preserved["choice"] != choice_mismatch["choice"]),
            "executed_digest": choice_preserved["executed_digest"],
            "effect": effect,
            "first_candidate": candidate["control_id"],
            "first_parent": candidate["parent_digest"],
            "adopted": adopted,
            "second_candidate": second["candidate"]["control_id"],
            "second_parent": second["candidate"]["parent_digest"],
            "second_executed": active2["imp_digest"],
            "acquisition": acquisition,
            "effects_settled": len(restarted.settled_effects),
            "observations": len(restarted.observations)}


def _freeze_arm_program(frontier: dict, revision: object, arm: str) -> dict | None:
    acquisition = frontier.get("acquisition") or {}
    if (not isinstance(revision, dict)
            or revision.get("disposition") != "bound"
            or acquisition.get("status") != "retained"):
        return None
    body = {
        "arm": arm,
        "package_digest": revision.get("package_digest"),
        "executable_digest": revision.get("executed_digest"),
        "response_digest": acquisition.get("response_digest"),
        "dispatch_evidence_digest": acquisition.get("dispatch_evidence_digest"),
        "receipt_identity": revision.get("receipt_identity"),
        "frozen_before": "qualification",
    }
    if any(value is None for value in body.values()):
        return None
    body["freeze_digest"] = _digest(body)
    return body


def _e0_unavailable(out: Path, freeze: dict, reason: str) -> dict:
    result = {
        "study": STUDY_ROOT_E0,
        "study_root": STUDY_ROOT_E0,
        "protocol": freeze.get("protocol"),
        "run_id": freeze.get("run_id"),
        "source_identity": freeze.get("source_identity"),
        "status": "unavailable",
        "reason": reason,
        "freeze_digest": freeze.get("freeze_digest"),
        "route": dict(freeze.get("route") or {}),
        "route_digest": freeze.get("route_digest"),
        "control": {"campaign_id": "frontier-control", "boundaries": 0,
                     "model_calls": 0, "frontier": {}},
        "live": {"campaign_id": "frontier-live", "boundaries": 0,
                  "model_calls": 0, "construction_calls": 0,
                  "frontier": {}},
        "guard": {"dispatch_count": 0, "refusal_reason": reason},
        "ledger": [],
        "durable_receipts": [],
        "revision": "absent",
        "frontier": {"observation_dependent": False,
                      "control_choice": None, "live_choice": None,
                      "second_round": None},
    }
    (out / "e0-run.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n")
    return result


def _e12_unavailable(out: Path, freeze: dict, reason: str) -> dict:
    result = {
        "study": STUDY_ROOT_E12,
        "study_root": STUDY_ROOT_E12,
        "protocol": freeze.get("protocol"),
        "run_id": freeze.get("run_id"),
        "source_identity": freeze.get("source_identity"),
        "status": "unavailable",
        "reason": reason,
        "freeze_digest": freeze.get("freeze_digest"),
        "route": dict(freeze.get("route") or {}),
        "route_digest": freeze.get("route_digest"),
        "arms": {
            arm: {"status": "unavailable", "reason": reason,
                  "model_calls": 0, "candidate_artifacts": [],
                  "history_tokens": "unknown", "dispatch_ledger": []}
            for arm in ("P0", "P1", "P2")
        },
        "dispatch_ledger": [],
        "durable_receipts": [],
        "model_total": 0,
        "m4_export": {"status": "unavailable", "reason": reason},
    }
    (out / "e12-run.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n")
    return result


def run_e0(dsn: str, out) -> dict:
    _require_grant()
    out = Path(out)
    freeze = json.loads((out / "freeze.json").read_text())
    _validate_live_freeze(freeze, STUDY_ROOT_E0)
    model = _live_model()
    if model != freeze["route"]["requested_model"]:
        raise ValueError("E0 model does not match the frozen route")
    if (freeze.get("route") != _live_route()
            or freeze.get("route_digest") != _digest(freeze.get("route"))):
        raise ValueError("E0 route does not match the frozen route")
    try:
        _require_route_preflight(out, freeze, "E0")
    except Exception as exc:
        return _e0_unavailable(out, freeze, str(exc))
    try:
        authority = _authorize(
            dsn, STUDY_ROOT_E0, 200000,
            {"model_calls": freeze["bounds"]["model_calls"],
             "construction_calls": 4})
        allocation_id = authority.get("allocation_id")
        if not allocation_id:
            raise ValueError("durable study allocation is unavailable")
        durable_gateway = _DurableBrokerOutput(
            dsn, _live_gateway(freeze["route"]), allocation_id=allocation_id,
            expected_route=freeze["route"])
    except Exception as exc:
        return _e0_unavailable(
            out, freeze,
            "durable broker unavailable before inference: %s" % exc)
    control = _run_frontier_investigation(
        out / "frontier-control.json", freeze, "control",
        guard=None, model=model)
    guard = _guard(durable_gateway, pinned_model=model,
                   ceiling=freeze["bounds"]["model_calls"],
                   already_spent=_already_spent(),
                   expected_route=freeze["route"])
    live = _run_frontier_investigation(
        out / "frontier-live.json", freeze, "live",
        guard=guard, model=model)
    spent = _already_spent()
    live_calls = max(0, guard.dispatch_count - spent)
    acquisition = live.get("acquisition") or {}
    if acquisition.get("status") == "retained":
        from experiments.ad01 import boolean_rule as _rules
        from experiments.ad01 import live_construct as _live
        revision = _live.bind_retained_acquisition(
            live.get("store_path", ""), acquisition,
            _rules.make_task("dev", 4))
    else:
        revision = "absent"
    live["store_digest"] = _file_digest(Path(live["store_path"]))
    result = {"study": "invl02-live-e0",
              "study_root": STUDY_ROOT_E0,
              "protocol": freeze["protocol"],
              "run_id": freeze["run_id"],
              "source_identity": freeze["source_identity"],
              "status": "available" if (
                  acquisition.get("status") == "retained"
                  and isinstance(revision, dict)
                  and revision.get("disposition") == "bound")
              else "incomplete",
              "freeze_digest": freeze["freeze_digest"],
              "route": dict(freeze["route"]),
              "route_digest": freeze["route_digest"],
              "control": {"campaign_id": "frontier-control",
                          "boundaries": int(control.get(
                              "effects_settled", 0)),
                          "model_calls": 0,
                          "frontier": control},
              "live": {"campaign_id": "frontier-live",
                       "boundaries": int(live.get(
                           "effects_settled", 0)),
                       "model_calls": live_calls,
                       "construction_calls": (
                           1 if live_calls else 0),
                       "frontier": live},
              "guard": guard.guard_status(),
              "ledger": guard.finalized_dispatches(),
              "durable_receipts": list(durable_gateway.durable_receipts),
              "revision": revision,
              "frontier": {
                  "observation_dependent": bool(
                      live.get("observation_dependent")),
                  "control_choice": control.get("choice_mismatch"),
                  "live_choice": live.get("choice_mismatch"),
                  "second_round": live.get("second_candidate")}}
    (out / "e0-run.json").write_text(
        json.dumps(result, sort_keys=True, indent=1, default=str) + "\n")
    (out / "live-campaign.json").write_text(
        json.dumps(live, sort_keys=True, indent=1, default=str) + "\n")
    return result


def restart_use(*, dsn: str, campaign_path, repertoire_path,
                release_id: str, task_id: str, out) -> dict:
    from experiments.ad01 import trajectory
    from settlement import store
    from settlement.common import Command
    campaign = json.loads(Path(campaign_path).read_text())
    repertoire = trajectory.load_repertoire(repertoire_path)
    use_cid = "invl02-live-reuse-%s" % task_id.replace("-", "")[:12]
    store.subdivide_allocation(
        dsn, Command(request_id="subdivide-%s" % use_cid,
                     payload={"parent_id": "ad01-campaign-%s"
                                             % campaign["campaign_id"],
                              "child_id": "ad01-campaign-%s" % use_cid,
                              "domain": "study", "authorized": 30000,
                              "max_occupancy": 8}))
    trajectory.ensure_campaign(
        dsn, use_cid, 1, "I", dict(CHARTER), dict(CAPS), tasks=[task_id],
        study_root=campaign.get("study_root", STUDY_ROOT_E0))
    records = trajectory.run_use(
        repertoire, 1, "I", [task_id], {}, dsn=dsn,
        allocation_id="ad01-campaign-%s" % use_cid,
        release_id=release_id)
    result = {"task_id": task_id, "release_id": release_id,
              "records": records}
    Path(out).write_text(
        json.dumps(result, sort_keys=True, indent=1, default=str) + "\n")
    return result


def tamper_probe(*, repertoire_path, out) -> dict:
    import copy
    from experiments.ad01 import trajectory
    repertoire = trajectory.load_repertoire(repertoire_path)
    tampered = copy.deepcopy(repertoire)
    changed = False
    for member in tampered["members"]:
        source = member.get("method_source")
        if isinstance(source, str) and source:
            member["method_source"] = ("# tampered\n" + source) \
                if source.startswith("def") else (source + "\n# tampered")
            changed = True
            break
    if not changed:
        result = {"probe": "no-acquired-member",
                  "verdict": "refused-absent"}
    else:
        try:
            import hashlib as _hashlib
            for member in tampered["members"]:
                source = member.get("method_source", "")
                if isinstance(member, dict) and member.get(
                        "authored") is False and member.get(
                        "source_digest") != _hashlib.sha256(
                        source.encode("utf-8")).hexdigest():
                    raise ValueError(
                        "acquired member %r bytes do not match their digest"
                        % (member.get("capability_id"),))
            result = {"probe": "substitution-accepted",
                      "verdict": "FAIL-substitution-undetected"}
        except ValueError as exc:
            result = {"probe": "substitution-refused",
                      "verdict": "refused", "reason": str(exc)}
    Path(out).write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n")
    return result


def _permitted_dev_history(dev_seeds=None) -> list:
    from experiments.ad01 import boolean_rule as _rules
    from experiments.ad01 import rule_learner as _learner
    seeds = list(dev_seeds) if dev_seeds is not None else [3, 7]
    history = []
    for seed in seeds:
        task = _rules.make_task("dev", int(seed))
        session = _rules.RuleSession(task)
        learner = _learner.VersionSpaceLearner(
            _rules.CLASS_TABLES, int(seed))
        while session.remaining > 0:
            pick = learner.choose_query(dict(session.queried))
            if pick is None:
                break
            found = session.query(pick)
            learner.observe(pick, found)
        committed = learner.predict(dict(session.queried))
        committed = session.commit_predictor(committed)
        score = session.score(committed)
        history.append({
            "task_id": task["task_id"], "split": "dev",
            "seed": int(seed), "queries": len(session.queried),
            "predictor_digest": hashlib.sha256(
                _canonical(committed).encode()).hexdigest(),
            "score_overall": score["overall"]})
    return history


def _arm_snapshot(arm: str, held_seed: int, history: list, model: str,
                  budget: dict) -> dict:
    from experiments.ad01 import boolean_rule as _rules
    return {"arm": arm,
            "solver": {"learner": "VersionSpaceLearner",
                       "seed": int(held_seed),
                       "class_digest": _rules.class_digest()},
            "archive": [],
            "history": list(history),
            "history_digest": _digest(list(history)),
            "model": model,
            "budget": dict(budget)}


def _validate_arm_histories(p1_history: list, p2_history: list,
                            permitted: list,
                            p1_digest: str | None = None) -> None:
    from experiments.ad01 import live_construct as _live
    if list(p1_history) != []:
        raise _live.LiveRefused(
            "P1 must withhold permitted development history")
    if list(p2_history) != list(permitted):
        raise _live.LiveRefused(
            "P2 must receive exactly the permitted development history")
    blob = _canonical(list(p2_history))
    if p1_digest is not None and p1_digest in blob:
        raise _live.LiveRefused(
            "P2 inputs contain a P1 outcome; cross-arm exposure refused")


def _run_p0_boolean(split: str, seed: int) -> dict:
    from experiments.ad01 import boolean_rule as _rules
    from experiments.ad01 import rule_learner as _learner
    task = _rules.make_task(split, int(seed))
    session = _rules.RuleSession(task)
    learner = _learner.VersionSpaceLearner(
        _rules.CLASS_TABLES, int(seed))
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        found = session.query(pick)
        learner.observe(pick, found)
    committed = learner.predict(dict(session.queried))
    committed = session.commit_predictor(committed)
    score = session.score(committed)
    specs = [dict(s) for s in committed["specs"]]
    return {"task_id": task["task_id"], "split": split,
            "seed": int(seed), "queries": len(session.queried),
            "model_calls": 0, "failed_attempts": 0,
            "history_entries": 0, "history_input_chars": 0,
            "history_tokens": "unknown", "score": score,
            "predictor_digest": hashlib.sha256(
                _canonical(committed).encode()).hexdigest(),
            "predictor_specs": specs,
            "predictor_tables": list(committed["tables"]),
            "target_tables": list(task["tables"])}


def boolean_live_round(*, guard, model: str, split: str, seed: int,
                       history: list | None = None,
                       repairs: int = 2,
                       max_output_tokens: int = 2048,
                       arm: str = "P1") -> dict:
    from experiments.ad01 import boolean_rule as rules
    from experiments.ad01 import live_construct as _live
    from experiments.ad01 import rule_learner
    from settlement.gateway import GatewayError, ModelRequest
    task = rules.make_task(split, seed)
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, seed)
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        found = session.query(pick)
        learner.observe(pick, found)
    queries = len(session.queried)
    history = list(history or [])
    prompt = (_canonical(session.model_input())
              + "\nPermitted history: %s" % _canonical(history)
              + "\nReply with exactly one JSON object shaped "
              '{"specs": [{"const": 0|1, "mask": 0..15, '
              '"pair": null|[i,j]} x4]} and nothing else, optionally '
              "wrapped in one ```json fenced block.")
    prior = None
    manual_attempt = 0
    physical = []
    committed = None
    candidate = None
    raw_response = None
    response_digest = None
    prompt_digest = _digest(prompt)
    while committed is None:
        manual_attempt += 1
        body = prompt if prior is None else "%s\nPRIOR FAILURE: %s" % (
            prompt, prior)
        prompt_digest = _digest(body)
        before = len(guard.finalized_dispatches())
        operation_id = "invl02-boolean-%s-%s-%04d-a%d" % (
            arm, split, int(seed), manual_attempt)
        response = guard.infer(ModelRequest(
            model=model, messages=({"role": "user", "content": body},),
            max_output_tokens=max_output_tokens, deadline_ms=300_000,
            operation_id=operation_id),
            evidence={"arm": arm, "task": task["task_id"],
                      "attempt": manual_attempt, "raw_prompt": body})
        physical.extend(guard.finalized_dispatches()[before:])
        if isinstance(response, GatewayError):
            prior = "transport: %s" % response.message
            if manual_attempt > repairs:
                raise ValueError("boolean construction transport: %s"
                                 % response.message)
            continue
        text = (response.text or "").strip()
        raw_response = response.text
        response_digest = hashlib.sha256(response.text.encode()).hexdigest()
        if not text:
            prior = "empty completion"
            if manual_attempt > repairs:
                raise ValueError("boolean construction empty completion")
            continue
        try:
            candidate = _live.extract_and_validate_boolean(text)
        except _live.LiveRefused as exc:
            prior = str(exc)
            if manual_attempt > repairs:
                raise ValueError("boolean payload invalid: %s" % exc)
            continue
        try:
            committed = session.commit_predictor(candidate)
        except rules.RuleRefused as exc:
            prior = str(exc)
            if manual_attempt > repairs:
                raise ValueError("boolean predictor illegal: %s" % exc)
    if candidate is None or raw_response is None:
        raise ValueError("boolean construction produced no candidate")
    predictor_digest = _digest(candidate)
    physical_dispatch = [entry for entry in physical
                         if not entry.get("replay", False)]
    operation_ids = list(dict.fromkeys(
        entry.get("operation_id") for entry in physical
        if isinstance(entry.get("operation_id"), str)))
    score = session.score(committed)
    specs = [dict(s) for s in committed["specs"]]
    input_binding = {
        "task_id": task["task_id"], "split": split, "seed": int(seed),
        "history": list(history), "history_digest": _digest(list(history)),
        "public_input": session.model_input(),
    }
    candidate_artifact = {
        "arm": arm, "task_id": task["task_id"], "split": split,
        "seed": int(seed), "raw_response": raw_response,
        "raw_response_digest": response_digest, "predictor": candidate,
        "predictor_digest": predictor_digest,
        "input_digest": _digest(input_binding),
        "prompt_digest": prompt_digest,
        "history": list(history), "history_digest": _digest(list(history)),
        "manual_attempt": manual_attempt,
        "operation_id": operation_ids[-1] if operation_ids else None,
        "operation_ids": operation_ids,
        "dispatch_evidence_digests": [
            entry.get("evidence_digest") for entry in physical],
    }
    return {"task_id": task["task_id"], "split": split, "seed": seed,
            "queries": queries, "model_calls": len(physical_dispatch),
            "physical_dispatch_count": len(physical_dispatch),
            "replay_count": len(physical) - len(physical_dispatch),
            "automatic_retry_count": max(0, len(physical_dispatch) - manual_attempt),
            "failed_attempts": manual_attempt - 1,
            "history_entries": len(history),
            "history_input_chars": len(prompt),
            "history_tokens": "unknown",
            "history_digest": _digest(list(history)),
            "input_digest": candidate_artifact["input_digest"],
            "prompt_digest": prompt_digest,
            "score": score, "predictor_digest": predictor_digest,
            "predictor_specs": specs,
            "predictor_tables": list(committed["tables"]),
            "target_tables": list(task["tables"]),
            "raw_response": raw_response, "response_digest": response_digest,
            "candidate_artifact": candidate_artifact,
            "dispatch_ledger": physical}


def _write_e12_revision_receipts(out: Path, freeze_digest: str,
                                 arms: dict) -> None:
    from experiments.ad01 import frontier as _frontier
    operations = {}
    child_receipts = {}
    for arm in ("P1", "P2"):
        info = arms.get(arm) or {}
        if info.get("status") != "available":
            continue
        store_path = (info.get("frontier") or {}).get("store_path")
        if not store_path:
            continue
        store = _frontier.FrontierStore(str(store_path))
        records = [record for record in store.accepted_revisions
                   if record.get("arm") == arm
                   and isinstance(record.get("receipt"), dict)]
        if not records:
            continue
        receipt = _frontier.validate_evidence_record(
            records[-1]["receipt"], kind="child-execution",
            outcome="success")
        operation_id = receipt["operation_id"]
        operations[operation_id] = {
            "operation_id": operation_id, "receipts": [receipt]}
        child_receipts[operation_id] = receipt
    (out / "e12-receipts.json").write_text(json.dumps({
        "study": "invl02-live-e12",
        "freeze_digest": freeze_digest,
        "authority": "local-diagnostic",
        "authoritative": False,
        "operations": operations,
        "child_receipts": child_receipts,
    }, sort_keys=True, indent=1) + "\n")


def run_e12(dsn: str, out) -> dict:
    _require_grant()
    out = Path(out)
    freeze = json.loads((out / "freeze.json").read_text())
    _validate_live_freeze(freeze, STUDY_ROOT_E12)
    model = _live_model()
    if model != freeze["route"]["requested_model"]:
        raise ValueError("E12 model does not match the frozen route")
    if (freeze.get("route") != _live_route()
            or freeze.get("route_digest") != _digest(freeze.get("route"))):
        raise ValueError("E12 route does not match the frozen route")
    try:
        _require_route_preflight(out, freeze, "E12")
    except Exception as exc:
        return _e12_unavailable(out, freeze, str(exc))
    try:
        permitted = _permitted_dev_history(
            (freeze.get("boolean_seeds") or {}).get("dev", [3, 7]))
    except Exception as exc:
        return _e12_unavailable(
            out, freeze, "permitted development history unavailable: %s" % exc)
    frozen_history = freeze.get("history")
    if (not isinstance(frozen_history, dict)
            or frozen_history.get("P1") != []
            or not isinstance(frozen_history.get("P2"), list)
            or list(permitted) != list(frozen_history["P2"])):
        return _e12_unavailable(
            out, freeze, "permitted development history changed after freeze")
    try:
        authority = _authorize(
            dsn, STUDY_ROOT_E12, 400000,
            {"model_calls": freeze["bounds"]["model_calls"],
             "construction_calls": 8})
        allocation_id = authority.get("allocation_id")
        if not allocation_id:
            raise ValueError("durable study allocation is unavailable")
        durable_gateway = _DurableBrokerOutput(
            dsn, _live_gateway(freeze["route"]), allocation_id=allocation_id,
            expected_route=freeze["route"])
    except Exception as exc:
        return _e12_unavailable(
            out, freeze,
            "durable broker unavailable before inference: %s" % exc)
    per_arm = freeze["bounds"]["per_arm"]
    budget = {"max_queries": 8, "model_calls": per_arm["P1"]["init"],
              "repairs": per_arm["P1"]["repair"]}
    permitted_digest = _digest(permitted)
    qual_seed = int((freeze.get("boolean_seeds") or {}).get(
        "qual", [11])[0])
    audit_seeds = list((freeze.get("boolean_seeds") or {}).get(
        "audit", [23]))
    audit_seed = int(audit_seeds[0])
    held = [("qual", qual_seed), ("audit", audit_seed)]
    arms: dict = {}
    spent = _already_spent()
    snapshots: dict = {}
    for order, arm in enumerate(list(freeze["order"])):
        want_history = [] if arm == "P1" else list(permitted)
        if arm == "P1" and list(want_history) != []:
            from experiments.ad01 import live_construct as _live_ref
            raise _live_ref.LiveRefused(
                "P1 must withhold permitted development history")
        if arm == "P2" and list(want_history) != list(permitted):
            from experiments.ad01 import live_construct as _live_ref
            raise _live_ref.LiveRefused(
                "P2 must receive exactly the permitted history")
        snapshots[arm] = _arm_snapshot(
            arm, qual_seed, want_history, model, budget)
        guard = _guard(durable_gateway, pinned_model=model,
                       ceiling=per_arm[arm]["init"]
                       + per_arm[arm]["repair"] + spent,
                       already_spent=spent,
                       expected_route=freeze["route"],
                       automatic_retries=0)
        spent_before = int(spent)
        try:
            frontier = _run_frontier_investigation(
                out / ("frontier-%s.json" % arm), freeze, arm,
                guard=guard, model=model, history=want_history)
            acquisition = frontier.get("acquisition") or {}
            revision: object = "absent"
            if acquisition.get("status") == "retained":
                from experiments.ad01 import boolean_rule as _rules
                from experiments.ad01 import live_construct as _live
                revision = _live.bind_retained_acquisition(
                    frontier.get("store_path", ""), acquisition,
                    _rules.make_task("dev", 4))
            program_freeze = _freeze_arm_program(frontier, revision, arm)
            if acquisition.get("status") == "retained" and program_freeze is None:
                raise ValueError("arm program was not frozen before qualification")
            booleans = []
            for split, seed in held:
                hist = [] if arm == "P1" else list(permitted)
                booleans.append(boolean_live_round(
                    guard=guard, model=model, split=split,
                    seed=int(seed), history=hist, arm=arm,
                    repairs=budget["repairs"]))
            if arm == "P1":
                assert all(b.get("history_entries") == 0
                           for b in booleans)
            if arm == "P2":
                assert all(b.get("history_digest") == permitted_digest
                           for b in booleans)
            arm_calls = int(guard.dispatch_count) - spent_before
            history_tokens = "unknown"
            failed = sum(int(b.get("failed_attempts", 0))
                         for b in booleans)
            arms[arm] = {
                "status": "available" if program_freeze is not None else "unavailable",
                "campaign_id": "frontier-%s" % arm,
                "model_calls": arm_calls,
                "guard": guard.guard_status(),
                "revision": revision,
                "program_freeze": program_freeze,
                "frontier": frontier,
                "booleans": booleans,
                "boolean": booleans[0],
                "candidate_artifacts": [
                    record["candidate_artifact"] for record in booleans],
                "dispatch_ledger": guard.finalized_dispatches(),
                "snapshot": snapshots[arm],
                "history_tokens": history_tokens,
                "failed_attempts": failed,
                "permitted_digest": permitted_digest}
        except Exception as exc:
            arm_calls = int(guard.dispatch_count) - spent_before
            arms[arm] = {"status": "unavailable",
                         "reason": str(exc),
                         "guard": guard.guard_status(),
                         "model_calls": arm_calls,
                         "program_freeze": None,
                         "snapshot": snapshots.get(arm),
                         "candidate_artifacts": [],
                         "dispatch_ledger": guard.finalized_dispatches(),
                         "history_tokens": "unknown",
                         "failed_attempts": arm_calls,
                         "permitted_digest": permitted_digest}
            spent = guard.dispatch_count
            continue
        spent = guard.dispatch_count
        frontier["store_digest"] = _file_digest(Path(
            frontier.get("store_path", "")))
        (out / ("arm-%s.json" % arm)).write_text(
            json.dumps({"frontier": frontier,
                        "booleans": booleans,
                        "snapshot": snapshots[arm]},
                       sort_keys=True, indent=1, default=str) + "\n")
        (out / ("frontier-%s.json" % arm)).write_text(
            json.dumps(frontier, sort_keys=True, indent=1,
                       default=str) + "\n")
    p1_hist = [] if arms.get("P1", {}).get("status") == "available" \
        else None
    p2_hist = list(permitted) if arms.get("P2", {}).get(
        "status") == "available" else None
    if p1_hist is not None and p2_hist is not None:
        p1_digest = (arms["P1"].get("booleans") or [{}])[0].get(
            "predictor_digest")
        _validate_arm_histories(p1_hist, p2_hist, permitted,
                                p1_digest=p1_digest)
    p0_booleans = [_run_p0_boolean(split, int(seed))
                   for split, seed in held]
    arms["P0"] = {
        "status": "available",
        "campaign_id": "fixed-learner-P0",
        "model_calls": 0,
        "guard": {"pinned_model": model, "ceiling": 0,
                  "dispatch_count": 0, "refusal_reason": "",
                  "refusal_kind": "", "cost_blocked": None,
                  "ceiling_reached": True, "version": "invl02-live-v1"},
        "revision": "absent",
        "program_freeze": {
            "arm": "P0", "package_digest": _p0_incumbent()["source_digest"],
            "executable_digest": _p0_incumbent()["source_digest"],
            "frozen_before": "qualification"},
        "booleans": p0_booleans,
        "boolean": p0_booleans[0],
        "snapshot": _arm_snapshot("P0", qual_seed, [], model, budget),
        "history_tokens": "unknown",
        "failed_attempts": 0,
        "permitted_digest": permitted_digest}
    (out / "arm-P0.json").write_text(
        json.dumps({"booleans": p0_booleans,
                    "snapshot": arms["P0"]["snapshot"]},
                   sort_keys=True, indent=1, default=str) + "\n")
    control = _run_frontier_investigation(
        out / "frontier-control-e12.json", freeze, "control",
        guard=None, model=model)
    _write_e12_revision_receipts(
        out, freeze["freeze_digest"], arms)
    total = sum(int(a.get("model_calls", 0)) for a in arms.values())
    raw_dispatch_ledger = []
    for arm in ("P1", "P2"):
        raw_dispatch_ledger.extend(arms[arm].get("dispatch_ledger") or [])
    dispatch_ledger, bound_durable_receipts = _bind_output_dispatches(
        raw_dispatch_ledger, list(durable_gateway.durable_receipts))
    durable_by_operation = {
        row.get("operation_id"): row for row in bound_durable_receipts
        if isinstance(row, dict)}
    physical_dispatch = [row for row in dispatch_ledger
                         if isinstance(row, dict) and not row.get("replay")]
    durable_complete = all(
        isinstance(row, dict)
        and row.get("operation_id") in durable_by_operation
        and durable_by_operation[row.get("operation_id")].get("settled") is True
        for row in physical_dispatch)
    arms_complete = all(
        arms.get(arm, {}).get("status") == "available"
        and isinstance(arms.get(arm, {}).get("program_freeze"), dict)
        for arm in ("P1", "P2"))
    result = {"study": STUDY_ROOT_E12,
              "study_root": STUDY_ROOT_E12,
              "protocol": freeze["protocol"],
              "run_id": freeze["run_id"],
              "source_identity": freeze["source_identity"],
              "status": "available" if arms_complete and durable_complete
              else "incomplete",
              "execution_status": "eligibility-screen" if arms_complete
              else "incomplete",
              "freeze_digest": freeze["freeze_digest"],
              "route": dict(freeze["route"]),
              "route_digest": _digest(freeze["route"]),
              "arms": arms,
              "dispatch_ledger": dispatch_ledger,
              "durable_receipts": bound_durable_receipts,
              "permitted_digest": permitted_digest,
              "snapshots": snapshots,
              "held": [{"split": s, "seed": int(v)} for s, v in held],
              "control_boundaries": int(control.get(
                  "effects_settled", 0)),
              "control": control,
              "model_total": total,
              "m4_export": {
                  "status": "unavailable",
                  "reason": "E12 has no authoritative child-operation ledger"}}
    if total > freeze["bounds"]["model_calls"]:
        raise ValueError("E1/E2 ceiling exceeded: %d" % total)
    (out / "e12-run.json").write_text(
        json.dumps(result, sort_keys=True, indent=1, default=str) + "\n")
    return result


class _DurableE3Authority:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def read(self, operation_id: str) -> dict:
        from settlement import broker, store
        return {
            "operation": broker.read_operation(self.dsn, operation_id),
            "receipts": store.operation_receipts(self.dsn, operation_id),
            "receipt_conflicts": store.operation_receipt_conflicts(
                self.dsn, operation_id),
        }


_E3_LINEAGE_FIELDS = (
    "source_digest", "artifact_digest", "input_digest", "result_digest",
    "package_digest", "parent_digest", "round", "dispatch_evidence_digest",
)


def _durable_e3_receipt(authority, receipt: dict) -> tuple[bool, str]:
    operation_id = receipt.get("operation_id")
    receipt_identity = receipt.get("receipt_identity")
    if (not isinstance(operation_id, str) or not operation_id
            or operation_id.startswith("local:")
            or not isinstance(receipt_identity, str)
            or not receipt_identity or receipt_identity.startswith("local:")):
        return False, "local receipt identity is not durable"
    try:
        snapshot = authority.read(operation_id)
    except Exception as exc:
        return False, "durable operation lookup failed: %s" % exc
    if not isinstance(snapshot, dict):
        return False, "durable operation lookup returned no row"
    operation = snapshot.get("operation")
    if not isinstance(operation, dict):
        return False, "durable operation row is missing"
    if operation.get("id", operation.get("operation_id")) != operation_id:
        return False, "durable operation identity does not match"
    if operation.get("dispatch_state") not in ("observed", "reconciled"):
        return False, "durable operation is not terminal"
    if operation.get("settled") is not True:
        return False, "durable operation is unsettled"
    if operation.get("reconcile_state") not in ("none", "reconciled"):
        return False, "durable operation has unresolved or conflicted state"
    if snapshot.get("receipt_conflicts"):
        return False, "durable operation has receipt conflicts"
    rows = snapshot.get("receipts")
    if not isinstance(rows, list):
        return False, "durable receipt rows are missing"
    matches = [row for row in rows
               if isinstance(row, dict)
               and row.get("receipt_identity") == receipt_identity]
    if len(rows) != 1 or len(matches) != 1:
        return False, "durable receipt identity is missing or duplicated"
    row = matches[0]
    if (row.get("operation_id", operation_id) != operation_id
            or row.get("outcome") != receipt.get("outcome")
            or row.get("outcome") != "success"):
        return False, "durable receipt outcome or operation does not match"
    content = row.get("content")
    if not isinstance(content, dict):
        return False, "durable receipt content is missing"
    lineage = content
    if not any(field in lineage for field in _E3_LINEAGE_FIELDS):
        lineage = content.get("evidence") or content.get("lineage") or {}
    if not isinstance(lineage, dict):
        return False, "durable receipt lineage is missing"
    for field in _E3_LINEAGE_FIELDS:
        if lineage.get(field) != receipt.get(field):
            return False, "durable receipt %s does not match" % field
    local_result = ((receipt.get("details") or {}).get("raw_payload") or {}).get(
        "result")
    durable_result = content.get("result")
    if not isinstance(local_result, dict) or not local_result:
        return False, "local child result is not usable"
    if not isinstance(durable_result, dict) or not durable_result:
        return False, "durable usable result is missing"
    if (durable_result != local_result
            or lineage.get("result_digest") != _digest(durable_result)):
        return False, "durable usable result does not match the local child result"
    return True, "durable operation and usable result match"


def run_e3(dsn: str, out, e12_dir, *, authority=None) -> dict:
    _require_grant()
    from experiments.ad01 import frontier as _frontier
    from experiments.ad01 import live_construct as _live
    out = Path(out)
    e12_dir = Path(e12_dir)
    out.mkdir(parents=True, exist_ok=True)
    reasons = {}
    eligible = []
    freeze_path = e12_dir / "freeze.json"
    run_path = e12_dir / "e12-run.json"
    if not freeze_path.is_file() or not run_path.is_file():
        result = {"study": "invl02-live-e3", "status": "unavailable",
                  "reason": "valid E12 run and freeze are required",
                  "arm_revisions": reasons}
        (out / "e3-run.json").write_text(
            json.dumps(result, sort_keys=True, indent=1) + "\n")
        return result
    try:
        freeze = json.loads(freeze_path.read_text())
        e12 = json.loads(run_path.read_text())
    except (OSError, ValueError) as exc:
        result = {"study": "invl02-live-e3", "status": "unavailable",
                  "reason": "E12 run or freeze is unreadable: %s" % exc,
                  "arm_revisions": reasons}
        (out / "e3-run.json").write_text(
            json.dumps(result, sort_keys=True, indent=1) + "\n")
        return result
    try:
        _validate_live_freeze(freeze, STUDY_ROOT_E12)
    except ValueError as exc:
        result = {"study": "invl02-live-e3", "status": "unavailable",
                  "reason": "E12 freeze identity is invalid: %s" % exc,
                  "arm_revisions": reasons}
        (out / "e3-run.json").write_text(
            json.dumps(result, sort_keys=True, indent=1) + "\n")
        return result
    if (e12.get("study") != STUDY_ROOT_E12
            or e12.get("study_root") != STUDY_ROOT_E12
            or e12.get("protocol") != freeze.get("protocol")
            or e12.get("run_id") != freeze.get("run_id")
            or e12.get("source_identity") != freeze.get("source_identity")
            or e12.get("freeze_digest") != freeze.get("freeze_digest")
            or e12.get("route") != freeze.get("route")
            or e12.get("route_digest") != _digest(freeze.get("route"))):
        result = {"study": "invl02-live-e3", "status": "unavailable",
                  "reason": "E12 run does not match its frozen study root",
                  "arm_revisions": reasons}
        (out / "e3-run.json").write_text(
            json.dumps(result, sort_keys=True, indent=1) + "\n")
        return result
    if authority is None:
        authority = _DurableE3Authority(dsn)
    for arm in ("P1", "P2"):
        e12_arm = (e12.get("arms") or {}).get(arm) or {}
        if e12_arm.get("status") != "available":
            reasons[arm] = "E12 arm is unavailable"
            continue
        frontier_path = e12_dir / ("frontier-%s.json" % arm)
        if not frontier_path.is_file():
            reasons[arm] = "durable frontier record is missing"
            continue
        try:
            summary = json.loads(frontier_path.read_text())
        except (OSError, ValueError) as exc:
            reasons[arm] = "durable frontier record is unreadable: %s" % exc
            continue
        if summary != e12_arm.get("frontier"):
            reasons[arm] = "frontier summary is not bound to the E12 arm"
            continue
        store_path = summary.get("store_path")
        if not store_path:
            reasons[arm] = "durable frontier store is missing"
            continue
        store_path = Path(store_path)
        if (not store_path.is_file()
                or summary.get("store_digest") != _file_digest(store_path)):
            reasons[arm] = "frontier store digest does not match E12"
            continue
        try:
            store = _frontier.FrontierStore(str(store_path))
        except Exception as exc:
            reasons[arm] = "durable frontier store is unreadable: %s" % exc
            continue
        projection = e12_arm.get("revision")
        if (not isinstance(projection, dict)
                or projection.get("disposition") != "bound"
                or projection.get("package_digest") != store.active_digest):
            reasons[arm] = "E12 revision is not bound to the durable store"
            continue
        records = [record for record in store.accepted_revisions
                   if record.get("origin") == "acquired"
                   and record.get("source_kind") == "model-response"
                   and record.get("arm") == arm
                   and record.get("accepted") is True
                   and record.get("retained") is True
                   and record.get("active") is True
                   and record.get("package_digest") == store.active_digest
                   and record.get("usable_result") is True]
        if not records:
            reasons[arm] = "durable accepted revision evidence is missing"
            continue
        record = records[-1]
        retained = [package for package in store.treatment_arms["acquired"]
                    if package.get("package_digest") == record.get(
                        "package_digest")]
        if retained:
            try:
                _frontier.validate_package(
                    retained[0], grant=store._doc["grant"])
            except _frontier.Refused:
                retained = []
        lineage = store._doc.get("lineage") or []
        if (not retained
                or retained[0].get("response_digest") != record.get(
                    "response_digest")
                or retained[0].get("provenance_digest") != record.get(
                    "provenance_digest")
                or not lineage
                or lineage[-1].get("package_digest") != record.get(
                    "package_digest")
                or lineage[-1].get("parent_digest") != record.get(
                    "parent_digest")):
            reasons[arm] = "accepted revision lineage does not match"
            continue
        provenance = retained[0].get("provenance") or {}
        dispatch_digest = provenance.get("dispatch_evidence_digest")
        original_records = [
            evidence for evidence in store.evidence
            if evidence.get("kind") == "gateway-dispatch"
            and evidence.get("evidence_digest") == dispatch_digest]
        final_records = [
            evidence for evidence in store.evidence
            if evidence.get("kind") == "gateway-dispatch"
            and evidence.get("dispatch_evidence_digest") == dispatch_digest
            and evidence.get("package_digest") == record.get(
                "package_digest")]
        if len(original_records) != 1 or len(final_records) != 1:
            reasons[arm] = "durable dispatch provenance is missing"
            continue
        try:
            _live.validate_acquired_provenance(
                retained[0], original_records[0], final_records[0])
        except _live.LiveRefused as exc:
            reasons[arm] = "durable dispatch provenance is invalid: %s" % exc
            continue
        post = record.get("post_restart") or {}
        receipt = record.get("receipt")
        try:
            _frontier.validate_evidence_record(
                receipt, kind="child-execution", outcome="success")
        except _frontier.Refused as exc:
            reasons[arm] = "accepted revision child receipt is invalid: %s" % exc
            continue
        if (post.get("executed") is not True
                or post.get("executable_digest") != record.get("imp_digest")
                or post.get("operation_ids") != [receipt.get("operation_id")]
                or receipt.get("arm") != arm
                or receipt.get("task_id") != post.get("task_id")
                or receipt.get("source_digest") != record.get("imp_digest")
                or receipt.get("artifact_digest") != record.get(
                    "package_digest")
                or receipt.get("package_digest") != record.get(
                    "package_digest")
                or receipt.get("parent_digest") != record.get(
                    "parent_digest")
                or receipt.get("round") != record.get("round")
                or receipt not in (store._doc.get("evidence") or [])):
            reasons[arm] = "post-restart child receipt lineage is missing"
            continue
        matched, reason = _durable_e3_receipt(authority, receipt)
        if not matched:
            reasons[arm] = "durable operation authority: %s" % reason
            continue
        evidence = {"arm": arm,
                    "package_digest": record["package_digest"],
                    "imp_digest": record["imp_digest"],
                    "operation_id": receipt["operation_id"],
                    "receipt_identity": receipt["receipt_identity"]}
        eligible.append({"arm": arm, "evidence": evidence,
                         "evidence_digest": _digest(evidence)})
    if not eligible:
        result = {"study": "invl02-live-e3", "status": "unavailable",
                  "execution": "unavailable",
                  "reason": "no eligible revised improver",
                  "arms": [], "arm_revisions": reasons}
    else:
        result = {"study": "invl02-live-e3",
                  "status": "eligibility-screen",
                  "execution": "unavailable",
                  "eligible": False,
                  "reason": "eligibility evidence passed; no E3 execution is implemented",
                  "arms": eligible,
                  "arm_revisions": reasons}
    (out / "e3-run.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n")
    return result


def _authoritative_operation_ledger(out: Path, *,
                                    freeze: dict) -> tuple[dict, dict, dict]:
    path = out / "authoritative-operations.json"
    if not path.is_file():
        raise ValueError("M4 export requires an authoritative operation ledger")
    try:
        ledger = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("authoritative operation ledger is unreadable: %s"
                         % exc) from exc
    operations = ledger.get("operations") if isinstance(ledger, dict) else None
    child_receipts = ledger.get("child_receipts") if isinstance(
        ledger, dict) else None
    if (not isinstance(operations, dict) or not operations
            or not isinstance(child_receipts, dict) or not child_receipts):
        raise ValueError("authoritative operation ledger is empty")
    identity_fields = (
        "protocol", "run_id", "source_identity", "study", "study_root",
        "freeze_digest", "route_digest")
    ledger_identity = {key: ledger.get(key) for key in identity_fields}
    expected_identity = {
        "protocol": freeze.get("protocol"),
        "run_id": freeze.get("run_id"),
        "source_identity": freeze.get("source_identity"),
        "study": freeze.get("study"),
        "study_root": freeze.get("study_root"),
        "freeze_digest": freeze.get("freeze_digest"),
        "route_digest": freeze.get("route_digest"),
    }
    if any(value is None for value in ledger_identity.values()):
        raise ValueError("authoritative ledger identity fields are required")
    if ledger_identity != expected_identity:
        raise ValueError("authoritative ledger identity mismatch")
    from experiments.ad01 import frontier as _frontier
    receipt_owners = {}

    def claim_receipt(receipt, op_id, *, child_path=False):
        identity = receipt.get("receipt_identity") if isinstance(
            receipt, dict) else None
        if not isinstance(identity, str) or not identity:
            raise ValueError("authoritative receipt identity is missing")
        if identity.startswith("local:"):
            raise ValueError("local receipt identity is not authoritative")
        previous = receipt_owners.get(identity)
        if previous is not None and (previous != op_id or not child_path):
            raise ValueError("duplicate receipt identity %s" % identity)
        receipt_owners[identity] = op_id

    for op_id, row in operations.items():
        if not isinstance(row, dict) or row.get("operation_id") != op_id:
            raise ValueError("authoritative operation identity mismatch")
        receipts = row.get("receipts")
        if not isinstance(receipts, list) or not receipts:
            raise ValueError("authoritative operation receipt is empty")
        if len(receipts) != 1:
            raise ValueError("multiple terminal receipts for %s" % op_id)
        for receipt in receipts:
            try:
                _frontier.validate_evidence_record(receipt)
            except _frontier.Refused as exc:
                raise ValueError(
                    "authoritative operation receipt is mismatched: %s" % exc
                ) from exc
            claim_receipt(receipt, op_id)
            details = receipt.get("details")
            raw_payload = details.get("raw_payload") if isinstance(
                details, dict) else None
            result = raw_payload.get("result") if isinstance(
                raw_payload, dict) else None
            if (receipt.get("operation_id") != op_id
                    or not all(receipt.get(key) for key in (
                        "arm", "task_id", "source_digest", "artifact_digest",
                        "input_digest", "result_digest", "receipt_identity"))
                    or receipt.get("outcome") not in ("success", "failure")
                    or not isinstance(result, dict)
                    or receipt.get("result_digest") != _digest(result)):
                raise ValueError("authoritative operation receipt is mismatched")
    for op_id, receipt in child_receipts.items():
        row = operations.get(op_id)
        try:
            _frontier.validate_evidence_record(receipt)
        except _frontier.Refused as exc:
            raise ValueError(
                "authoritative child receipt is mismatched: %s" % exc
            ) from exc
        claim_receipt(receipt, op_id, child_path=True)
        if (not isinstance(row, dict)
                or not any(r == receipt for r in row.get("receipts", []))):
            raise ValueError("authoritative child receipt is mismatched")
    if set(child_receipts) != set(operations):
        raise ValueError("dispatch-operation-receipt bijection is required")
    return operations, child_receipts, ledger_identity


def _m4_receipt_usage(receipt: dict) -> dict:
    details = receipt.get("details") if isinstance(receipt, dict) else None
    raw = details.get("raw_payload") if isinstance(details, dict) else None
    usage = raw.get("usage") if isinstance(raw, dict) else None
    return usage if isinstance(usage, dict) else {}


def _m4_measurement(values: list, *, unresolved: bool = False) -> tuple:
    if unresolved:
        return "unresolved", "unknown"
    if not values or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in values):
        return "unknown", "unknown"
    return "measured", sum(values)


def _m4_accounting_entry(measured, source: str, status: str) -> dict:
    return {"measured": measured, "source": source,
            "measurement_status": status}


def _count_or_unknown(value):
    if isinstance(value, bool):
        return "unknown"
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    return "unknown"


def _frozen_held_tasks(freeze: dict) -> list[dict]:
    from experiments.ad01 import offline_recompute as offline
    tasks = offline.frozen_boolean_tasks(freeze)
    if not tasks:
        raise ValueError("frozen Boolean task set is invalid")
    return [{"split": split, "seed": int(seed)}
            for split, seed in tasks.items()]


def _validate_candidate_artifact(candidate: dict, *, dispatch_ledger: list,
                                 durable_receipts: list,
                                 tasks: dict,
                                 histories: dict) -> dict:
    from experiments.ad01 import live_construct as _live
    from experiments.ad01 import offline_recompute as _offline
    if not isinstance(candidate, dict):
        raise ValueError("candidate artifact is not an object")
    raw_response = candidate.get("raw_response")
    if (not isinstance(raw_response, str)
            or candidate.get("raw_response_digest") != hashlib.sha256(
                raw_response.encode("utf-8")).hexdigest()):
        raise ValueError("candidate raw response provenance is invalid")
    try:
        predictor = _live.extract_and_validate_boolean(raw_response)
    except Exception as exc:
        raise ValueError("candidate raw response is not a strict Boolean payload") from exc
    if (candidate.get("predictor") != predictor
            or candidate.get("predictor_digest") != _digest(predictor)):
        raise ValueError("candidate predictor does not recompute from raw response")
    task_id = candidate.get("task_id")
    split = next((key for key, seed in tasks.items()
                  if task_id == "rule-%s-%04d" % (key, int(seed))), None)
    if split is None:
        raise ValueError("candidate task is not frozen")
    if not isinstance(durable_receipts, list) or not durable_receipts:
        raise ValueError("candidate durable dispatch evidence is missing")
    if "history" not in candidate:
        raise ValueError("candidate frozen input history is missing")
    history = candidate.get("history")
    if not isinstance(history, list):
        raise ValueError("candidate history is malformed")
    expected_history = histories.get(candidate.get("arm"))
    if not isinstance(expected_history, list) or history != expected_history:
        raise ValueError("candidate history is not the permitted frozen history")
    expected_input = _offline.boolean_candidate_input_digest(
        task_id, split, int(tasks[split]), history)
    if (candidate.get("split") != split
            or candidate.get("seed") != int(tasks[split])
            or candidate.get("history_digest") != _digest(history)
            or candidate.get("input_digest") != expected_input):
        raise ValueError("candidate input does not match the frozen task")
    operation_ids = candidate.get("operation_ids")
    operation_id = candidate.get("operation_id")
    if (not isinstance(operation_ids, list) or not operation_ids
            or len(operation_ids) != len(set(operation_ids))
            or operation_id not in operation_ids):
        raise ValueError("candidate operation cardinality is invalid")
    evidence_ids = candidate.get("dispatch_evidence_digests")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise ValueError("candidate dispatch evidence is missing")
    matches = [entry for entry in dispatch_ledger
               if isinstance(entry, dict)
               and entry.get("operation_id") in operation_ids
               and (entry.get("dispatch_evidence_digest")
                    or entry.get("evidence_digest")) in evidence_ids
               and entry.get("arm") == candidate.get("arm")
               and entry.get("task_id") == task_id]
    accepted = [entry for entry in matches
                if entry.get("operation_id") == operation_id
                and entry.get("raw_response") == raw_response
                and entry.get("response_digest") == candidate.get(
                    "raw_response_digest")
                and entry.get("prompt_digest") == candidate.get(
                    "prompt_digest")]
    if ({entry.get("operation_id") for entry in matches} != set(operation_ids)
            or len(matches) != len(evidence_ids)
            or len(accepted) != 1):
        raise ValueError("candidate raw response has no unique durable dispatch evidence")
    receipts = [row for row in durable_receipts
                if isinstance(row, dict)
                and row.get("operation_id") == operation_id]
    if len(receipts) != 1:
        raise ValueError("candidate durable dispatch evidence is not one-to-one")
    receipt = receipts[0]
    expected_dispatch_digest = (
        accepted[0].get("dispatch_evidence_digest")
        or accepted[0].get("evidence_digest"))
    durable_result = receipt.get("result")
    if (receipt.get("outcome") != "success"
            or receipt.get("usable_result") is not True
            or not isinstance(durable_result, dict)
            or durable_result.get("raw_response") != raw_response
            or receipt.get("result_digest") != _digest(durable_result)):
        raise ValueError(
            "candidate requires one successful durable receipt with a usable result")
    if (receipt.get("settled") is not True
            or receipt.get("dispatch_evidence_digest")
            != expected_dispatch_digest
            or receipt.get("input_digest") != candidate.get("input_digest")
            or receipt.get("source_digest") != candidate.get(
                "predictor_digest")
            or receipt.get("artifact_digest") != candidate.get(
                "predictor_digest")):
        raise ValueError("candidate dispatch lacks one settled durable receipt")
    return predictor


def _software_domain(child_receipts: dict, tasks: list) -> dict:
    task_set = set(tasks)
    records = []
    for op_id, receipt in child_receipts.items():
        if receipt.get("task_id") not in task_set:
            continue
        result = ((receipt.get("details") or {}).get("raw_payload") or {}).get(
            "result")
        if (not isinstance(result, dict) or "observed" not in result
                or receipt.get("result_digest") != _digest(result)):
            raise ValueError("software use receipt has no usable outcome")
        records.append({
            "record_id": "software-%s-%s" % (receipt.get("arm"), op_id),
            "arm": receipt.get("arm"),
            "task_id": receipt.get("task_id"),
            "operation_id": op_id,
            "receipt_identity": receipt.get("receipt_identity"),
            "input_digest": receipt.get("input_digest"),
            "result_digest": receipt.get("result_digest"),
            "observed": result.get("observed"),
            "queries": result.get("queries"),
            "child_result": result,
        })
    missing = sorted(task_set - {row["task_id"] for row in records})
    if missing:
        raise ValueError("software use outcome is missing %s" % missing[0])
    records.sort(key=lambda row: (row["task_id"], row["arm"], row["operation_id"]))
    outcomes = [
        {"arm": row["arm"], "task_id": row["task_id"],
         "observed": row["observed"], "queries": row["queries"]}
        for row in records]
    return {"use_records": records, "outcomes": outcomes}


def export_m4_bundle(out_dir) -> dict:
    from experiments.ad01 import offline_recompute as _m4
    out = Path(out_dir)
    freeze_live = json.loads((out / "freeze.json").read_text())
    e12 = json.loads((out / "e12-run.json").read_text())
    _validate_live_freeze(freeze_live, STUDY_ROOT_E12)
    expected_identity = {
        key: freeze_live.get(key) for key in (
            "protocol", "run_id", "source_identity", "study", "study_root",
            "freeze_digest", "route_digest")
    }
    if any(e12.get(key) != value
           for key, value in expected_identity.items()):
        raise ValueError("E12 run identity is not authoritative")
    if not (out / "authoritative-operations.json").is_file():
        raise ValueError("M4 export requires an authoritative operation ledger")
    held = _frozen_held_tasks(freeze_live)
    if e12.get("held") != held:
        raise ValueError("E12 held task membership differs from protocol")
    e12_arms = e12.get("arms")
    if not isinstance(e12_arms, dict):
        raise ValueError("E12 arms are missing")
    missing_arms = [arm for arm in ("P0", "P1", "P2")
                    if arm not in e12_arms]
    if missing_arms:
        raise ValueError("missing-arm %s" % missing_arms[0])
    operations, child_receipts, authority = _authoritative_operation_ledger(
        out, freeze=freeze_live)
    software = _software_domain(
        child_receipts, list(freeze_live.get("software_tasks") or []))
    dispatch_ledger = e12.get("dispatch_ledger")
    if not isinstance(dispatch_ledger, list) or not dispatch_ledger:
        raise ValueError("M4 export requires an E12 physical dispatch ledger")
    durable_receipts = e12.get("durable_receipts")
    if not isinstance(durable_receipts, list):
        durable_receipts = []
    durable_operations = set()
    durable_identities = set()
    for receipt in durable_receipts:
        if not isinstance(receipt, dict):
            raise ValueError("durable receipt is malformed")
        operation_id = receipt.get("operation_id")
        receipt_identity = receipt.get("receipt_identity")
        if (not isinstance(operation_id, str) or not operation_id
                or operation_id in durable_operations
                or not isinstance(receipt_identity, str)
                or not receipt_identity
                or receipt_identity in durable_identities):
            raise ValueError("durable receipt lineage is not one-to-one")
        durable_operations.add(operation_id)
        durable_identities.add(receipt_identity)
    authoritative_pairs = {
        (op_id, receipt.get("receipt_identity"))
        for op_id, row in operations.items()
        for receipt in row.get("receipts", [])
        if isinstance(receipt, dict)}
    e12_pairs = {
        (receipt.get("operation_id"), receipt.get("receipt_identity"))
        for receipt in durable_receipts}
    if authoritative_pairs != e12_pairs:
        raise ValueError(
            "authoritative/E12 receipt set is unresolved: extra or missing receipts")
    qual_task = "rule-%s-%04d" % (held[0]["split"], int(held[0]["seed"]))
    audit_task = "rule-%s-%04d" % (held[1]["split"], int(held[1]["seed"])) \
        if len(held) > 1 else qual_task
    use_tasks = [qual_task, audit_task]
    candidate_tasks = {entry["split"]: int(entry["seed"])
                      for entry in held}
    candidate_histories = {
        "P1": [], "P2": list((freeze_live.get("history") or {})
                             .get("P2") or [])}
    tasks = {}
    for task_id in list(freeze_live.get("software_tasks") or []):
        tasks[str(task_id)] = {"expected": "software-baseline"}
    from experiments.ad01 import boolean_rule as _rules
    for held_task in held:
        split = str(held_task["split"])
        seed = int(held_task["seed"])
        task = _rules.make_task(split, seed)
        task_id = task["task_id"]
        expected = _canonical(list(task["tables"]))
        tasks[task_id] = {
            "split": split, "seed": seed, "expected": expected,
            "target_digest": hashlib.sha256(expected.encode()).hexdigest(),
            "target_source": "frozen-task-identity",
        }
    per_arm = freeze_live.get("bounds", {}).get("per_arm", {})
    init = int(per_arm.get("P1", {}).get("init", 18))
    repair = int(per_arm.get("P1", {}).get("repair", 2))
    freeze = {
        "study_id": "invl02-live-e12",
        "study_root": STUDY_ROOT_E12,
        "arms": ["P0", "P1", "P2"],
        "order": list(freeze_live.get("order", ["P1", "P2"])),
        "development": [
            {"episode_id": "d-sw-0",
             "task_id": str((freeze_live.get("software_tasks")
                             or ["d-sw-0"])[0])},
            {"episode_id": "d-sw-1",
             "task_id": str((freeze_live.get("software_tasks")
                             or ["d-sw-0", "d-sw-1"])[-1])}],
        "software_tasks": list(freeze_live.get("software_tasks") or []),
        "assessment": [{"episode_id": "a-0",
                        "use_tasks": [qual_task]}],
        "audit": [{"episode_id": "t-0",
                   "use_tasks": [audit_task]}],
        "construction_allowance": _m4.reserve_allowance(
            ["P1", "P2"], init=init, repair=repair),
        "caps": {"per_episode": {"policy_steps": 6,
                                 "model_calls": 4},
                 "diagnostic_queries_per_episode": 8,
                 "study_model_calls": 0,
                 "history_token_ceiling": 10000},
        "metric_rule": {"kind": "mean-quality", "margin": 0.0,
                        "tie": "incumbent"},
        "resource_rule": {"kind": "ceiling",
                          "note": "quality under common ceilings"},
        "config": {"model": str(freeze_live.get("model",
                                                "grant-pinned")),
                   "instruments": ["diagnostic", "construct", "use"],
                   "abi": "ad01-policy-step-v1",
                   "artifact_kind": "learning-policy",
                   "candidate_schema": "boolean-rule-v1"},
        "policy_identities": {},
        "method_repertoires": {},
        "tasks": tasks,
        "route": dict(freeze_live.get("route") or {}),
        "route_digest": _digest(freeze_live.get("route") or {}),
        "p0_incumbent": dict(freeze_live.get("p0_incumbent") or {}),
        "history_reference": {
            "P1": [], "P2": list((freeze_live.get("history") or {})
                                  .get("P2") or [])},
    }
    identities = {}
    repertoires = {}
    arm_contracts = {}
    candidates = []
    for arm in ("P1", "P2"):
        info = e12_arms[arm]
        status = info.get("status")
        if status not in ("available", "unavailable"):
            raise ValueError("missing-status %s" % arm)
        history_tokens = _count_or_unknown(info.get("history_tokens"))
        failed = int(info.get("failed_attempts", 0))
        if status == "unavailable":
            identities[arm] = {"status": "unavailable",
                               "reason": str(info.get("reason",
                                                      "unavailable")),
                               "history_tokens": history_tokens,
                               "failed_attempts": failed}
            repertoires[arm] = {"members": [], "member_digests": []}
            input_bindings = {}
            prompt_bindings = {}
            for task_id in use_tasks:
                input_bindings[task_id] = _digest({
                    "task_id": task_id,
                    "history": [] if arm == "P1" else
                    freeze["history_reference"]["P2"]})
                prompt_bindings[task_id] = _digest({
                    "task_id": task_id, "attempt": 1,
                    "history": [] if arm == "P1" else
                    freeze["history_reference"]["P2"]})
            arm_contracts[arm] = {
                "history": [] if arm == "P1" else list(
                    freeze["history_reference"]["P2"]),
                "history_digest": _digest(
                    [] if arm == "P1" else
                    freeze["history_reference"]["P2"]),
                "input_bindings": input_bindings,
                "prompt_bindings": prompt_bindings}
            continue
        artifacts = info.get("candidate_artifacts") or [
            row.get("candidate_artifact") for row in info.get("booleans", [])
            if isinstance(row, dict) and row.get("candidate_artifact")]
        if len(artifacts) != len(use_tasks):
            raise ValueError("candidate-task-artifacts-missing %s" % arm)
        program_freeze = info.get("program_freeze")
        expected_program_keys = {
            "arm", "package_digest", "executable_digest", "response_digest",
            "dispatch_evidence_digest", "receipt_identity", "frozen_before",
            "freeze_digest",
        }
        if (not isinstance(program_freeze, dict)
                or set(program_freeze) != expected_program_keys
                or program_freeze.get("arm") != arm
                or program_freeze.get("frozen_before") != "qualification"
                or program_freeze.get("freeze_digest") != _digest({
                    key: value for key, value in program_freeze.items()
                    if key != "freeze_digest"})):
            raise ValueError(
                "program freeze was not frozen before qualification")
        revision = info.get("revision")
        frontier = info.get("frontier")
        acquisition = frontier.get("acquisition") if isinstance(
            frontier, dict) else None
        if (not isinstance(revision, dict)
                or revision.get("disposition") != "bound"
                or not isinstance(acquisition, dict)
                or acquisition.get("status") != "retained"
                or any(program_freeze.get(frozen_key) != revision.get(
                       revision_key) for frozen_key, revision_key in (
                           ("package_digest", "package_digest"),
                           ("executable_digest", "executed_digest"),
                           ("receipt_identity", "receipt_identity")))
                or any(program_freeze.get(key) != acquisition.get(key)
                       for key in ("response_digest",
                                   "dispatch_evidence_digest"))):
            raise ValueError("program freeze lineage is not bound to E12")
        for candidate in artifacts:
            _validate_candidate_artifact(
                candidate, dispatch_ledger=dispatch_ledger,
                durable_receipts=durable_receipts,
                tasks=candidate_tasks,
                histories=candidate_histories)
        candidates.extend(artifacts)
        candidate_digests = {}
        input_bindings = {}
        prompt_bindings = {}
        members = []
        for candidate in artifacts:
            task_id = candidate.get("task_id")
            predictor = candidate.get("predictor")
            predictor_digest = candidate.get("predictor_digest")
            candidate_digests[task_id] = predictor_digest
            input_bindings[task_id] = candidate["input_digest"]
            prompt_bindings[task_id] = candidate["prompt_digest"]
            members.append({"method_source": _canonical(predictor),
                            "source_digest": predictor_digest})
        program_source = _canonical(program_freeze)
        program_digest = hashlib.sha256(
            program_source.encode("utf-8")).hexdigest()
        members.insert(0, {"method_source": program_source,
                           "source_digest": program_digest})
        identities[arm] = {"status": "available",
                           "source": program_source,
                           "source_digest": program_digest,
                           "candidate_digests": candidate_digests,
                           "artifact": {"kind": "learning-policy",
                                        "abi": "ad01-policy-step-v1",
                                        "source_digest": program_digest},
                           "history_tokens": history_tokens,
                           "failed_attempts": failed}
        repertoires[arm] = {"members": members,
                           "member_digests": sorted(
                               member["source_digest"] for member in members)}
        arm_contracts[arm] = {
            "history": [] if arm == "P1" else list(
                freeze["history_reference"]["P2"]),
            "history_digest": _digest(
                [] if arm == "P1" else freeze["history_reference"]["P2"]),
            "input_bindings": input_bindings,
            "prompt_bindings": prompt_bindings}
    incumbent = freeze_live.get("p0_incumbent") or _p0_incumbent()
    identities["P0"] = {
        "status": "available", "source": incumbent["source"],
        "source_digest": incumbent["source_digest"],
        "artifact": {"kind": "learning-policy",
                     "abi": "ad01-policy-step-v1",
                     "source_digest": incumbent["source_digest"]},
        "history_tokens": "unknown", "failed_attempts": 0}
    repertoires["P0"] = {"members": [{"method_source": incumbent["source"],
                                    "source_digest": incumbent["source_digest"]}],
                         "member_digests": [incumbent["source_digest"]]}
    arm_contracts["P0"] = {
        "kind": "fixed-incumbent", "source": incumbent["source"],
        "source_digest": incumbent["source_digest"]}
    freeze["policy_identities"] = identities
    freeze["method_repertoires"] = repertoires
    freeze["arm_contracts"] = arm_contracts
    worst = _m4.study_worst_case(freeze)
    freeze["caps"]["study_model_calls"] = worst
    freeze["freeze_digest"] = _m4.freeze_digest(freeze)
    episodes_dev = []
    for entry in freeze["development"]:
        digest = identities["P0"].get("source_digest", "")
        episode_operations = [
            row["operation_id"] for row in software["use_records"]
            if row["arm"] == "P0"
            and row["task_id"] == entry["task_id"]]
        episodes_dev.append({
            "episode_id": entry["episode_id"], "arm": "P0",
            "policy_digest": digest,
            "policy_actions": [{"kind": "diagnose", "target": "t",
                                "inputs": {}, "evidence_refs": [],
                                "requested_resources": {}}],
            "policy_steps": 1, "model_calls": 0,
            "witness_queries": 0, "history_tokens": "unknown",
            "failed_attempts": 0,
            "operations": episode_operations})
    episodes_assess = [{
        "episode_id": "a-0", "arm": "P0",
        "policy_digest": identities["P0"].get("source_digest", ""),
        "policy_actions": [{"kind": "diagnose", "target": "t",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}}],
        "policy_steps": 1, "model_calls": 0,
        "witness_queries": 0, "history_tokens": "unknown",
        "failed_attempts": 0, "operations": ["op-a-0"]}]
    episodes_audit = [{
        "episode_id": "t-0", "arm": "P0",
        "policy_digest": identities["P0"].get("source_digest", ""),
        "policy_actions": [{"kind": "diagnose", "target": "t",
                            "inputs": {}, "evidence_refs": [],
                            "requested_resources": {}}],
        "policy_steps": 1, "model_calls": 0,
        "witness_queries": 0, "history_tokens": "unknown",
        "failed_attempts": 0, "operations": ["op-t-0"]}]
    construction = {}
    for arm in ("P1", "P2"):
        info = e12_arms[arm]
        ops = sorted(
            op_id for op_id, row in operations.items()
            if any(receipt.get("arm") == arm
                   and receipt.get("task_id") == "construct-%s" % arm
                   for receipt in row.get("receipts", [])
                   if isinstance(receipt, dict)))
        if not ops:
            raise ValueError("authoritative operation ledger has no construction %s"
                             % arm)
        operation_ids = set(ops)
        dispatch_count = sum(1 for entry in dispatch_ledger
                             if entry.get("operation_id") in operation_ids
                             and not entry.get("replay", False))
        if info.get("status") != "available":
            construction[arm] = {
                "status": "unavailable",
                "reason": str(info.get("reason", "unavailable")),
                "calls": dispatch_count,
                "history_tokens": _count_or_unknown(info.get("history_tokens")),
                "failed_attempts": int(info.get(
                    "failed_attempts", 0)),
                "operations": ops}
            continue
        ident = identities[arm]
        construction[arm] = {
            "status": "available",
            "policy_source": ident["source"],
            "source_digest": ident["source_digest"],
            "calls": dispatch_count,
            "history_tokens": _count_or_unknown(info.get("history_tokens")),
            "failed_attempts": int(info.get("failed_attempts", 0)),
            "operations": ops}
    records = []
    required_operation_ids = {"op-d-sw-0", "op-d-sw-1", "op-a-0", "op-t-0"}
    if (not required_operation_ids.issubset(operations)
            or any(not any(op_id.startswith("op-construct-%s-" % arm)
                           for op_id in operations)
                   for arm in ("P1", "P2"))):
        raise ValueError("authoritative operation ledger is incomplete")
    for arm in ("P0", "P1", "P2"):
        info = e12_arms[arm]
        for task_id in use_tasks:
            rid = "%s-%s-%s" % (
                "a" if task_id == qual_task else "t", arm, task_id)
            op_id = "op-use-%s" % rid
            if op_id not in operations or op_id not in child_receipts:
                raise ValueError("authoritative operation ledger is missing %s"
                                 % op_id)
            receipt = child_receipts[op_id]
            if (receipt.get("arm") != arm
                    or receipt.get("task_id") != task_id):
                raise ValueError("authoritative receipt has wrong arm or task")
            raw_payload = receipt.get("details", {}).get("raw_payload")
            result = raw_payload.get("result") if isinstance(
                raw_payload, dict) else None
            if not isinstance(result, dict) or "observed" not in result:
                raise ValueError("authoritative receipt has no child result")
            if info.get("status") != "available":
                records.append({
                    "record_id": rid, "arm": arm,
                    "task_id": task_id, "executed": "incumbent",
                    "observed": result["observed"],
                    "child_result": result,
                    "claimed_verdict": "failed",
                    "costs": {"witness_queries": result.get("queries")},
                    "input_digest": receipt["input_digest"],
                    "result_digest": receipt["result_digest"],
                    "receipt_identity": receipt["receipt_identity"],
                    "operation_ids": [op_id]})
                continue
            if arm == "P0":
                candidate_digest = identities[arm]["source_digest"]
            else:
                candidate = next((row for row in candidates
                                  if row.get("arm") == arm
                                  and row.get("task_id") == task_id), None)
                if not isinstance(candidate, dict):
                    raise ValueError("candidate task receipt is unbound")
                candidate_digest = candidate["predictor_digest"]
            source_digest = identities[arm]["source_digest"]
            if (receipt.get("source_digest") != candidate_digest
                    or receipt.get("artifact_digest") != candidate_digest):
                raise ValueError("authoritative receipt has wrong source")
            observed = result["observed"]
            expected = (freeze.get("tasks") or {}).get(
                task_id, {}).get("expected", "")
            claimed = "preserved" if observed == expected else "failed"
            queries = result.get("queries")
            record = {
                "record_id": rid, "arm": arm,
                "task_id": task_id, "executed": "candidate",
                "policy_digest": source_digest,
                "executed_source_digest": candidate_digest,
                "policy_artifact_kind": "learning-policy",
                "observed": observed, "child_result": result,
                "claimed_verdict": claimed,
                "costs": {"witness_queries": queries},
                "input_digest": receipt["input_digest"],
                "result_digest": receipt["result_digest"],
                "receipt_identity": receipt["receipt_identity"],
                "operation_ids": [op_id]}
            if arm != "P0":
                record["candidate_digest"] = candidate_digest
            records.append(record)
    total_model = sum(1 for entry in dispatch_ledger
                      if not entry.get("replay", False))
    witness_acq = sum(int(e.get("witness_queries", 0)) for e in (
        episodes_dev + episodes_assess + episodes_audit))
    witness_use = sum((r.get("costs") or {}).get(
        "witness_queries", 0) for r in records
        if isinstance(r.get("costs"), dict) and isinstance(
            (r.get("costs") or {}).get("witness_queries"), int))
    receipt_rows = [
        receipt for row in operations.values()
        for receipt in row.get("receipts", [])
        if isinstance(receipt, dict)]
    unresolved_count = max(
        _m4.unresolved_exposure_count(operations),
        _m4.dispatch_unresolved_count(dispatch_ledger))
    unresolved_receipts = unresolved_count > 0
    input_values = [_m4_receipt_usage(receipt).get("input_tokens")
                    for receipt in receipt_rows]
    output_values = [_m4_receipt_usage(receipt).get("output_tokens")
                     for receipt in receipt_rows]
    billed_values = []
    for receipt in receipt_rows:
        usage = _m4_receipt_usage(receipt)
        if usage.get("billed") is True:
            billed_values.append(usage.get("charge_units"))
    input_status, input_measured = _m4_measurement(
        input_values, unresolved=unresolved_receipts)
    output_status, output_measured = _m4_measurement(
        output_values, unresolved=unresolved_receipts)
    billed_usage_complete = bool(receipt_rows) and all(
        _m4_receipt_usage(receipt).get("billed") in (True, False)
        and isinstance(_m4_receipt_usage(receipt).get("charge_units"),
                      (int, float))
        and not isinstance(_m4_receipt_usage(receipt).get("charge_units"), bool)
        and isinstance(_m4_receipt_usage(receipt).get("charge_scale"),
                       (int, float))
        and not isinstance(_m4_receipt_usage(receipt).get("charge_scale"), bool)
        for receipt in receipt_rows)
    if billed_usage_complete:
        billed_status = "measured" if not unresolved_receipts else "unresolved"
        billed_measured = sum(billed_values) if billed_values else 0
    else:
        billed_status, billed_measured = _m4_measurement(
            billed_values, unresolved=unresolved_receipts)
    if not receipt_rows:
        input_status = output_status = billed_status = "unknown"
        input_measured = output_measured = billed_measured = "unknown"
    query_values = []
    use_operation_ids = {
        op_id for record in records
        for op_id in record.get("operation_ids", [])
        if isinstance(op_id, str) and op_id in child_receipts
    }
    for op_id in sorted(use_operation_ids):
        receipt = child_receipts[op_id]
        raw = (receipt.get("details") or {}).get("raw_payload") or {}
        result = raw.get("result") if isinstance(raw, dict) else None
        query_values.append(result.get("queries") if isinstance(result, dict)
                            else None)
    query_status, _query_measured = _m4_measurement(
        query_values, unresolved=unresolved_receipts)
    query_measured = (witness_acq + witness_use
                      if query_status == "measured" else "unknown")
    if not query_values:
        query_status = "unknown"
    dispatch_bound = all(
        isinstance(entry, dict)
        and ((isinstance(entry.get("operation_id"), str)
              and entry.get("operation_id") in operations
              and _m4._operation_dispatch_measured(
                  operations[entry["operation_id"]]))
             or isinstance(entry.get("dispatch_id"), str))
        for entry in dispatch_ledger)
    dispatch_status = ("measured" if dispatch_bound and not unresolved_receipts
                       else "unresolved" if dispatch_ledger else "unknown")
    accounting = {
        "model_dispatches": _m4_accounting_entry(
            total_model, "durable-operation-ledger", dispatch_status),
        "input_tokens": _m4_accounting_entry(
            input_measured, "durable-receipt-usage", input_status),
        "output_tokens": _m4_accounting_entry(
            output_measured, "durable-receipt-usage", output_status),
        "tool_queries": _m4_accounting_entry(
            query_measured, "durable-child-result", query_status),
        "child_compute_ms": _m4_accounting_entry(
            "unknown", "durable-receipt-usage", "unknown"),
        "billed_units": _m4_accounting_entry(
            billed_measured, "durable-receipt-usage", billed_status),
        "unresolved_exposure": _m4_accounting_entry(
            unresolved_count if receipt_rows else "unknown",
            "durable-receipt-outcome",
            "unresolved" if unresolved_receipts else
            "measured" if receipt_rows else "unknown"),
        "human_interventions": _m4_accounting_entry(
            "unknown", "human-intervention-ledger:absent", "unknown"),
    }
    means = {}
    for arm in ("P0", "P1", "P2"):
        info = (e12.get("arms") or {}).get(arm) or {}
        if info.get("status") != "available":
            means[arm] = None
            continue
        quals = []
        for record in records:
            if record.get("arm") != arm:
                continue
            expected = (freeze.get("tasks") or {}).get(
                record.get("task_id"), {}).get("expected", "")
            quals.append(1.0 if record.get("observed") == expected
                         else 0.0)
        means[arm] = (sum(quals) / len(quals) if quals else None)
    missing = sorted(
        arm for arm in ("P1", "P2")
        if (e12.get("arms") or {}).get(arm, {}).get(
            "status") != "available")
    winner = None
    if not missing:
        ranked = sorted(((m, a) for a, m in means.items()
                         if m is not None), reverse=True)
        if ranked:
            best = ranked[0][0]
            second = ranked[1][0] if len(ranked) > 1 else 0.0
            winner = ranked[0][1] if best - second >= 0.0 else "P0"
    claimed = {"winner": (winner or "none"),
               "note": "offline recomputed means %s" % _canonical(means)}
    bundle = {"schema": _m4.M4_SCHEMA,
              "status": "available" if not missing and not unresolved_receipts
              and e12.get("status") in (None, "available") else "incomplete",
              "protocol": freeze_live,
              "authority": authority,
              "study": freeze["study_id"],
              "study_root": freeze["study_root"],
              "freeze_digest": freeze["freeze_digest"],
              "source_e12_freeze_digest": freeze_live["freeze_digest"],
              "freeze": freeze,
              "development": episodes_dev,
              "construction": construction,
              "assessment": episodes_assess,
              "audit": episodes_audit,
              "use_records": records,
              "software": software,
              "operations": operations,
              "dispatch_ledger": dispatch_ledger,
              "candidates": candidates,
              "child_receipts": child_receipts,
              "accounting": accounting,
              "claimed": claimed}
    (out / "m4-bundle.json").write_text(
        json.dumps(bundle, sort_keys=True, indent=1,
                   default=str) + "\n")
    return bundle


def verify_m4_bundle(out_dir) -> dict:
    from experiments.ad01 import offline_recompute as _m4
    bundle = json.loads((Path(out_dir) / "m4-bundle.json").read_text())
    result = _m4.verify_bundle(bundle)
    (Path(out_dir) / "m4-verify.json").write_text(
        json.dumps(result, sort_keys=True, indent=1,
                   default=str) + "\n")
    return result


def _artifact_study_root(path: Path):
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    protocol = value.get("protocol")
    if isinstance(protocol, dict):
        root = protocol.get("study_root")
        if isinstance(root, str) and root:
            return root
    freeze = value.get("freeze")
    if isinstance(freeze, dict):
        root = freeze.get("study_root")
        if isinstance(root, str) and root:
            return root
    root = value.get("study_root")
    return root if isinstance(root, str) and root else None


def _write_recompute_result(bundle: Path, name: str, result: dict) -> None:
    (bundle / name).write_text(json.dumps(
        result, sort_keys=True, indent=1, default=str) + "\n")


def recompute(bundle_dir) -> dict:
    from experiments.ad01 import offline_recompute as _m4
    bundle = Path(bundle_dir)
    try:
        freeze = json.loads((bundle / "freeze.json").read_text())
    except (OSError, ValueError) as exc:
        result = {"status": "fail", "problems": [
            "freeze-unreadable %s" % exc], "recomputed": {},
            "verifier": "offline_recompute.verify_bundle"}
        _write_recompute_result(bundle, "recompute.json", result)
        return result
    study_root = freeze.get("study_root") if isinstance(freeze, dict) else None
    artifacts = []
    foreign_roots = []
    for name in ("output-run.json", "m4-bundle.json"):
        path = bundle / name
        if not path.is_file():
            continue
        root = _artifact_study_root(path)
        if root is None:
            continue
        if root == study_root:
            artifacts.append((name, path))
        else:
            foreign_roots.append(root)
    if foreign_roots:
        result = {"status": "fail", "problems": ["mixed-study-artifacts"],
                  "study_root": study_root,
                  "artifact_roots": sorted(set(foreign_roots)),
                  "recomputed": {}, "verifier": "offline_recompute.verify_bundle"}
        _write_recompute_result(bundle, "recompute.json", result)
        return result
    if study_root == STUDY_ROOT_OUTPUT and artifacts:
        name, path = next(
            ((name, path) for name, path in artifacts
             if name == "output-run.json"), artifacts[0])
        output = json.loads(path.read_text())
        private_path = bundle / "scorer-private.json"
        private = (json.loads(private_path.read_text())
                   if private_path.is_file() else None)
        result = _m4.verify_bundle(output, private)
        shaped = {"status": result.get("status"),
                  "study_status": output.get("status"),
                  "artifact": name,
                  "problems": list(result.get("problems") or []),
                  "recomputed": dict(result.get("recomputed") or {}),
                  "verifier": "offline_recompute.verify_bundle"}
        _write_recompute_result(bundle, "output-recompute.json", shaped)
        return shaped
    if artifacts and study_root != STUDY_ROOT_OUTPUT:
        _name, path = next(
            ((name, path) for name, path in artifacts
             if name == "m4-bundle.json"), artifacts[0])
        exported = json.loads(path.read_text())
        result = _m4.verify_bundle(exported)
        shaped = {"status": result.get("status"),
                  "study_status": exported.get("status"),
                  "artifact": path.name,
                  "problems": list(result.get("problems") or []),
                  "recomputed": dict(result.get("recomputed") or {}),
                  "measurement_boundary": _m4.MEASUREMENT_BOUNDARY,
                  "verifier": "offline_recompute.verify_bundle"}
        _write_recompute_result(bundle, "recompute.json", shaped)
        return shaped
    if study_root != STUDY_ROOT_E0:
        result = {"status": "fail",
                  "problems": ["declared-artifact-unavailable"],
                  "study_root": study_root, "recomputed": {},
                  "verifier": "offline_recompute.verify_bundle"}
        _write_recompute_result(bundle, "recompute.json", result)
        return result
    problems: list = []
    incomplete: list = []
    if freeze.get("freeze_digest") != _digest(
            {k: v for k, v in freeze.items()
             if k != "freeze_digest"}):
        problems.append("freeze-digest-mismatch")
    run_files = sorted(bundle.glob("*-run.json"))
    if not run_files:
        problems.append("missing-run-records")
    ceiling = int(((freeze.get("bounds") or {}).get("model_calls", 0)))
    per_arm = ((freeze.get("bounds") or {}).get("per_arm") or {})
    total_claimed = 0
    total_ledger = 0
    total_guard = 0
    for path in run_files:
        run = json.loads(path.read_text())
        if run.get("freeze_digest") != freeze.get("freeze_digest"):
            problems.append("run-freeze-mismatch %s" % path.name)
        claimed = int(run.get("model_total",
                              run.get("live", {}).get("model_calls", 0)))
        total_claimed += claimed
        ledger = run.get("ledger", []) or []
        attributed = sum(
            1 for entry in ledger
            if isinstance(entry, dict)
            and not entry.get("replay", False)
            and isinstance(entry.get("operation_id"), str)
            and isinstance(entry.get("dispatch_evidence_digest")
                           or entry.get("evidence_digest"), str))
        total_ledger += len(ledger)
        if claimed > attributed:
            incomplete.append(
                "unattributed-model-calls %s claimed=%d attributed=%d" % (
                    path.name, claimed, attributed))
        guard_dispatch = (run.get("guard") or {}).get("dispatch_count")
        if isinstance(guard_dispatch, bool):
            guard_dispatch = None
        if isinstance(guard_dispatch, int):
            total_guard += guard_dispatch
        else:
            total_guard += claimed
        if ledger and guard_dispatch is not None \
                and len(ledger) == guard_dispatch \
                and len(ledger) != claimed:
            problems.append("dispatch-miscount %s claimed=%d ledger=%d "
                            "guard=%s" % (path.name, claimed, len(ledger),
                                          guard_dispatch))
        for arm, reserve in per_arm.items():
            info = (run.get("arms") or {}).get(arm)
            if not isinstance(info, dict):
                continue
            arm_calls = int(info.get("model_calls", 0))
            arm_reserve = int(reserve.get("init", 0)) + int(
                reserve.get("repair", 0))
            if arm_calls > arm_reserve:
                problems.append("per-arm-ceiling-exceeded %s %d>%d"
                                % (arm, arm_calls, arm_reserve))
            arm_ledger = info.get("ledger", []) or []
            total_ledger += len(arm_ledger)
            if arm_ledger and arm_calls != len(arm_ledger):
                problems.append("dispatch-miscount %s.%s claimed=%d "
                                "ledger=%d" % (path.name, arm, arm_calls,
                                               len(arm_ledger)))
    counted = max(total_claimed, total_ledger, total_guard)
    if ceiling and counted > ceiling:
        problems.append("ceiling-exceeded counted=%d ceiling=%d"
                        % (counted, ceiling))
    total = counted
    for ledger_path in sorted(bundle.glob("*-run.json")):
        run = json.loads(ledger_path.read_text())
        ledgers = [run.get("ledger", []) or []]
        for info in (run.get("arms") or {}).values():
            if isinstance(info, dict):
                ledgers.append(info.get("ledger", []) or [])
        for ledger in ledgers:
            for entry in ledger:
                usage = entry.get("usage")
                if usage is None:
                    continue
                if not isinstance(usage, dict):
                    problems.append("usage-unstamped %s" % entry.get(
                        "operation_id"))
                    continue
                charge = usage.get("charge_units")
                if isinstance(charge, bool):
                    problems.append("nonzero-cost %s" % entry.get(
                        "operation_id"))
                elif isinstance(charge, (int, float)) and charge != 0:
                    problems.append("nonzero-cost %s" % entry.get(
                        "operation_id"))
                elif usage.get("billed") is True:
                    problems.append("nonzero-cost %s" % entry.get(
                        "operation_id"))
    verdict = ("fail" if problems else
               "incomplete" if incomplete else "pass")
    result = {"status": verdict,
              "problems": sorted(set(problems + incomplete)),
              "scope": "E0-only-narrow-checks",
              "recomputed": {"model_calls": total,
                             "model_claimed": total_claimed,
                             "ledger_entries": total_ledger,
                             "guard_dispatches": total_guard,
                             "ceiling": ceiling,
                             "run_files": [p.name for p in run_files]},
              "trust": ("E0-only narrow checks: freeze digest, run"
                        " matching digest, counted dispatches and observed"
                        " nonzero cost fields. E1/E2 require"
                        " m4-bundle.json verified offline via"
                        " offline_recompute.verify_bundle. Resource classes"
                        " beyond recountable dispatches stay attested"
                        " runtime measurements with unknown preserved.")}
    (bundle / "recompute.json").write_text(
        json.dumps(result, sort_keys=True, indent=1) + "\n")
    return result


def _unknown_usage() -> dict:
    return {"input_tokens": "unknown", "output_tokens": "unknown",
            "charge_units": "unknown", "billed": "unknown"}


def probe(out, *, read_ms: int = 60000, max_tokens: int = 256,
          api: str = "responses") -> dict:
    import time
    from experiments.ad01 import live_construct as _live
    from settlement.config import Settings
    from settlement.gateway import ModelRequest
    from settlement.gateway_http import HttpGatewayAdapter
    _require_grant()
    out = Path(out)
    model = _live_model()
    settings = Settings.from_env()
    adapter = HttpGatewayAdapter(
        endpoint=settings.gateway.endpoint,
        api_key=settings.gateway.api_key_env and __import__(
            "os").environ.get(settings.gateway.api_key_env, ""),
        timeout_read_ms=read_ms, api=api)
    guard = _guard(adapter, pinned_model=model,
                   ceiling=_already_spent() + 1,
                   already_spent=_already_spent())
    prompt = ("Reply with exactly one JSON object and nothing else,"
              " shaped {\"entry\": \"ok\"}.")
    started = time.monotonic()
    try:
        response = guard.infer(ModelRequest(
            model=model, messages=({"role": "user", "content": prompt},),
            max_output_tokens=max_tokens, deadline_ms=read_ms + 30000,
            operation_id="invl02-probe-%d" % read_ms))
    except Exception as exc:
        result = {"probe": "refused", "reason": str(exc),
                  "elapsed_s": round(time.monotonic() - started, 1),
                  "read_ms": read_ms, "usage": _unknown_usage(),
                  "guard": guard.guard_status()}
    else:
        from settlement.gateway import GatewayError
        if isinstance(response, GatewayError):
            result = {"probe": "error", "kind": str(response.kind),
                      "reason": response.message,
                      "elapsed_s": round(time.monotonic() - started, 1),
                      "read_ms": read_ms,
                      "usage": _live._usage_snapshot(response.usage),
                      "guard": guard.guard_status()}
        else:
            from experiments.ad01 import live_construct as _live_text
            result = {"probe": "text",
                      "elapsed_s": round(time.monotonic() - started, 1),
                      "read_ms": read_ms, "text_chars": len(
                          response.text or ""),
                      "response_digest": hashlib.sha256(
                          (response.text or "").encode()).hexdigest(),
                      "stop_reason": str(response.stop_reason),
                      "usage": _live_text._usage_snapshot(response.usage),
                      "guard": guard.guard_status()}
    path = out / ("probe-%s-%d.json" % (api, read_ms))
    path.write_text(json.dumps(result, sort_keys=True, indent=1) + "\n")
    return result


def main(argv: list | None = None) -> int:
    args = list(argv or [])
    if not args:
        print("usage: invl02_live.py preflight|freeze-output|run-output|"
              "freeze-e0|freeze-e12|run-e0|run-e12|"
              "run-e3|recompute|export-m4|verify-m4|restart-use ...",
              file=sys.stderr)
        return 2
    verb = args[0]
    rest = args[1:]
    try:
        if verb == "preflight":
            out = rest[rest.index("--out") + 1]
            result = preflight_route(out)
            print("preflight route=%s" % result["route"]["resolved_model"])
            return 0
        if verb == "freeze-output":
            out = rest[rest.index("--out") + 1]
            protocol = freeze_output(out)
            print("frozen output %s" % protocol["freeze_digest"][:8])
            return 0
        if verb == "run-output":
            dsn = rest[rest.index("--dsn") + 1]
            out = rest[rest.index("--out") + 1]
            result = run_output_live(dsn, out)
            print("output status=%s" % result["status"])
            return 0 if result.get("status") == "available" else 1
        if verb == "freeze-e0":
            out = rest[rest.index("--out") + 1]
            protocol = freeze_e0(out)
            print("frozen e0 %s" % protocol["freeze_digest"][:8])
            return 0
        if verb == "freeze-e12":
            out = rest[rest.index("--out") + 1]
            protocol = freeze_e12(out)
            print("frozen e12 %s" % protocol["freeze_digest"][:8])
            return 0
        if verb == "run-e0":
            dsn = rest[rest.index("--dsn") + 1]
            out = rest[rest.index("--out") + 1]
            result = run_e0(dsn, out)
            print("e0 live=%d guard=%s" % (
                result["live"]["model_calls"],
                result["guard"]["dispatch_count"]))
            return 0 if result.get("status") == "available" else 1
        if verb == "run-e12":
            dsn = rest[rest.index("--dsn") + 1]
            out = rest[rest.index("--out") + 1]
            result = run_e12(dsn, out)
            print("e12 total=%d" % result["model_total"])
            return 0 if result.get("status") == "available" else 1
        if verb == "run-e3":
            dsn = rest[rest.index("--dsn") + 1]
            out = rest[rest.index("--out") + 1]
            e12 = rest[rest.index("--e12") + 1]
            result = run_e3(dsn, out, e12)
            print("e3 %s" % result["status"])
            return 0 if result.get("status") == "eligibility-screen" else 1
        if verb == "recompute":
            bundle = rest[rest.index("--bundle") + 1]
            result = recompute(bundle)
            print("recompute %s problems=%d" % (
                result["status"], len(result["problems"])))
            return 0 if result["status"] == "pass" else 1
        if verb == "export-m4":
            bundle = rest[rest.index("--bundle") + 1]
            exported = export_m4_bundle(bundle)
            print("export-m4 tasks=%d records=%d" % (
                len(exported["freeze"]["tasks"]),
                len(exported["use_records"])))
            return 0 if exported.get("status", "available") == "available" \
                else 1
        if verb == "verify-m4":
            bundle = rest[rest.index("--bundle") + 1]
            result = verify_m4_bundle(bundle)
            print("verify-m4 %s problems=%d" % (
                result["status"], len(result["problems"])))
            comparison = (result.get("recomputed", {}).get("comparison")
                          or {})
            return 0 if (result["status"] == "pass"
                         and comparison.get("status") == "complete") else 1
        if verb == "probe":
            out = rest[rest.index("--out") + 1]
            read_ms = int(rest[rest.index("--read-ms") + 1]
                          if "--read-ms" in rest else 60000)
            api = rest[rest.index("--api") + 1] \
                if "--api" in rest else "responses"
            result = probe(out, read_ms=read_ms, api=api)
            print("probe %s elapsed=%s" % (
                result["probe"], result.get("elapsed_s")))
            return 0 if result.get("probe") == "text" else 1
        if verb == "restart-use":
            kwargs = {}
            for flag in ("--dsn", "--campaign", "--repertoire",
                         "--release", "--task", "--out"):
                kwargs[flag[2:]] = rest[rest.index(flag) + 1]
            result = restart_use(
                dsn=kwargs["dsn"], campaign_path=kwargs["campaign"],
                repertoire_path=kwargs["repertoire"],
                release_id=kwargs["release"], task_id=kwargs["task"],
                out=kwargs["out"])
            print("reuse task=%s records=%d" % (
                result["task_id"], len(result["records"])))
            return 0
    except Exception as exc:
        print("invl02-live refused: %s" % exc, file=sys.stderr)
        return 3
    print("unknown verb %r" % verb, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
