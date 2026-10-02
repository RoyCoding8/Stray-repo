"""Live construction boundary for Investigation Learning 02.

The counting guard pins the model, refuses over-ceiling dispatch before
sending, retries at most three times per call, blocks later calls on
observed nonzero cost, and records usage honestly with unknown staying
unknown. Construction itself reuses construct through broker
model-inference operations. Parsing reuses packet. Checking reuses
method_exec out-of-process child execution. Retention writes acquired
bytes into the frontier store treatment arms. The authored
improve_channel.leaf_construct path stays a labeled control outside this
module and never enters treatment arms.
"""

from __future__ import annotations

import hashlib
import json

LIVE_VERSION = "invl02-live-v1"

OUTPUT_PROTOCOL = "invl02-output-shape-v1"
OUTPUT_ROUTE = {
    "endpoint": "http://localhost:4000/v1",
    "requested_model": "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "resolved_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "provider": "nvidia",
    "tier": "free",
}
OUTPUT_LIMITS = {
    "max_response_characters": 512,
    "max_output_tokens": 2048,
    "max_dispatches": 8,
    "initial_dispatches": 4,
    "repairs_per_task": 1,
    "automatic_retries": 0,
}
OUTPUT_TASKS = {"qual": 11, "audit": 23}
OUTPUT_PROMPT_TEMPLATE = (
    "You are completing one finite Boolean-rule task. "
    "Public task input: {public_input}. "
    "Permitted history: {history}. "
    "Attempt {attempt} of 2. "
    "Reply with exactly one JSON object and nothing else, shaped "
    '{{"specs": [{{"const": 0|1, "mask": 0..15, '
    '"pair": null|[i,j]}} x4]}}. Do not include targets, private answers, '
    "explanations, or code fences. Keep the response under "
    "{max_response_characters} characters."
)

E0_CALL_CEILING = 12
E0_REPAIR_CEILING = 2
STUDY_CALL_CEILING = 80
PER_ARM_RESERVE = 20
PER_ARM_REPAIRS = 2
MAX_RETRIES = 3

APPARATUS_ORIGIN = "authored-control"
ACQUIRED_ORIGIN = "acquired"


class LiveRefused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def response_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def render_output_prompt(public_input: dict, history: list, attempt: int) -> str:
    if type(attempt) is not int or attempt not in (1, 2):
        raise LiveRefused("output attempt must be 1 or 2")
    if not isinstance(public_input, dict) or not isinstance(history, list):
        raise LiveRefused("output prompt inputs are malformed")
    return OUTPUT_PROMPT_TEMPLATE.format(
        public_input=json.dumps(public_input, sort_keys=True,
                                 separators=(",", ":")),
        history=json.dumps(history, sort_keys=True, separators=(",", ":")),
        attempt=attempt,
        max_response_characters=OUTPUT_LIMITS["max_response_characters"])


def output_operation_id(arm: str, split: str, seed: int, attempt: int) -> str:
    if arm not in ("P1", "P2") or split not in OUTPUT_TASKS:
        raise LiveRefused("output operation has an unknown arm or task")
    if int(seed) != OUTPUT_TASKS[split] or attempt not in (1, 2):
        raise LiveRefused("output operation has an unfrozen task or attempt")
    return "invl02-output-%s-%s-%04d-a%d" % (
        arm, split, int(seed), int(attempt))


def output_permitted_history() -> list:
    from . import boolean_rule as rules
    from . import rule_learner
    history = []
    for seed in (3, 7):
        task = rules.make_task("dev", int(seed))
        session = rules.RuleSession(task)
        learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES,
                                                     int(seed))
        while session.remaining > 0:
            pick = learner.choose_query(dict(session.queried))
            if pick is None:
                break
            learner.observe(pick, session.query(pick))
        committed = session.commit_predictor(
            learner.predict(dict(session.queried)))
        score = session.score(committed)
        history.append({
            "task_id": task["task_id"], "split": "dev", "seed": int(seed),
            "queries": len(session.queried),
            "predictor_digest": hashlib.sha256(
                json.dumps(committed, sort_keys=True,
                           separators=(",", ":")).encode()).hexdigest(),
            "score_overall": score["overall"]})
    return history


def classify_error(error) -> dict:
    usage = getattr(error, "usage", None)
    route_error = getattr(error, "route_error", None)
    return {"stage": ("route" if route_error is not None
                      else "transport"),
            "kind": str(getattr(error, "kind", "unknown")),
            "reason": str(getattr(error, "message", error)),
            "retryable": bool(getattr(error, "retryable", False)),
            "response_received": bool(getattr(error, "response_received",
                                              False)),
            "response_status": getattr(error, "response_status", None),
            "response_digest": getattr(error, "response_digest", None),
            "route_error": getattr(route_error, "value", route_error),
            "usage": _usage_snapshot(usage)}


def classify_empty(stop_reason: str) -> dict:
    reason = str(stop_reason or "")
    if "reasoning" in reason or "length" in reason:
        stage = "unfinished-reasoning"
    elif "truncat" in reason:
        stage = "truncation"
    else:
        stage = "empty-completion"
    return {"stage": stage, "kind": "empty", "reason": reason,
            "retryable": True, "usage": _usage_snapshot(None)}


def _usage_snapshot(usage) -> dict:
    if usage is None:
        return {"input_tokens": "unknown", "output_tokens": "unknown",
                "charge_units": "unknown", "charge_scale": "unknown",
                "provider_enforced_ceiling": "unknown", "billed": "unknown"}
    return {
        "input_tokens": ("unknown" if getattr(usage, "input_tokens", None) is None
                         else getattr(usage, "input_tokens")),
        "output_tokens": ("unknown" if getattr(usage, "output_tokens", None) is None
                          else getattr(usage, "output_tokens")),
        "charge_units": ("unknown" if getattr(usage, "charge_units", None) is None
                         else getattr(usage, "charge_units")),
        "charge_scale": ("unknown" if getattr(usage, "charge_scale", None) is None
                         else getattr(usage, "charge_scale")),
        "provider_enforced_ceiling": bool(getattr(
            usage, "provider_enforced_ceiling", False)),
        "billed": ("unknown" if getattr(usage, "billed", None) is None
                   else getattr(usage, "billed")),
    }


class LiveGuard:
    def __init__(self, delegate, *, pinned_model: str, ceiling: int,
                 already_spent: int = 0,
                 automatic_retries: int = MAX_RETRIES,
                 expected_route: dict | None = None) -> None:
        if not pinned_model:
            raise ValueError("pinned model is required")
        if ceiling < 0 or already_spent < 0:
            raise ValueError("ceiling and spent count must be nonnegative")
        if type(automatic_retries) is not int or automatic_retries < 0:
            raise ValueError("automatic retry limit must be nonnegative")
        self.delegate = delegate
        self.pinned_model = pinned_model
        self.ceiling = ceiling
        self.automatic_retries = automatic_retries
        self.expected_route = dict(expected_route) if expected_route else None
        self.dispatch_count = already_spent
        self.refusal_reason = ""
        self.refusal_kind = ""
        self.cost_blocked: str | None = None
        self.ledger: list = []
        self.finalizations: list = []

    def is_cost_blocked(self) -> bool:
        return self.cost_blocked is not None

    def is_ceiling_reached(self) -> bool:
        return self.dispatch_count >= self.ceiling

    def _refuse(self, reason: str, kind: str = ""):
        self.refusal_reason = reason
        if kind:
            self.refusal_kind = kind
        elif self.cost_blocked is not None:
            self.refusal_kind = "cost"
        raise LiveRefused(reason)

    def _record(self, entry: dict) -> None:
        self.ledger.append(entry)

    def _note_cost(self, usage) -> None:
        if usage is None:
            return
        snapshot = _usage_snapshot(usage)
        charge = snapshot["charge_units"]
        billed = snapshot["billed"]
        unknown_billed_zero = charge == 0 and billed is not False
        if (charge not in (0, "unknown") or unknown_billed_zero
                or (charge == "unknown" and billed is True)):
            self.cost_blocked = (
                "response reports nonzero or unknown possible cost: %s;"
                " charge already incurred, later calls blocked" % json.dumps(
                    snapshot, sort_keys=True))

    def _evidence_entry(self, request, response, attempt: int,
                        evidence: dict | None) -> dict:
        source = dict(evidence or {})
        raw_prompt = source.get("raw_prompt")
        if raw_prompt is None:
            raw_prompt = "".join(
                str(message.get("content", "")) for message in request.messages
                if message.get("role") == "user")
        text = getattr(response, "text", None)
        meta = dict(getattr(response, "model_meta", {}) or {})
        from . import frontier
        response_value = response_digest(text) if isinstance(text, str) \
            else None
        usage = _usage_snapshot(getattr(response, "usage", None))
        entry = frontier.make_evidence_record(
            "gateway-dispatch", request.operation_id,
            "success" if isinstance(text, str) and text.strip() else "unknown",
            attempt=int(source.get("attempt", attempt)),
            arm=source.get("arm"), task_id=source.get("task"),
            input_digest=source_digest(raw_prompt),
            result_digest=response_value,
            details={"raw_payload": {"raw_prompt": raw_prompt,
                                     "raw_response": text},
                     "route": meta, "stop_reason": str(getattr(
                         response, "stop_reason", "")),
                     "usage": usage})
        entry.update({
            "requested_model": request.model,
            "returned_model": meta.get("model"),
            "endpoint": meta.get("endpoint"),
            "provider": meta.get("provider"),
            "tier": meta.get("tier"),
            "requested_output_cap": request.max_output_tokens,
            "response_digest": response_value,
            "prompt_digest": source_digest(raw_prompt),
            "raw_prompt": raw_prompt,
            "raw_response": text,
            "stop_reason": str(getattr(response, "stop_reason", "")),
            "usage": usage,
            "billed": usage["billed"],
            "charge_units": usage["charge_units"],
            "parse_outcome": "pending",
            "accepted_candidate_digest": None,
            "route_error": meta.get("route_error"),
        })
        return entry

    def _route_failure(self, entry: dict) -> str | None:
        if self.expected_route is None:
            return None
        route = {key: entry.get(key) for key in
                 ("endpoint", "returned_model", "provider", "tier")}
        expected = {
            "endpoint": self.expected_route.get("endpoint"),
            "returned_model": self.expected_route.get("resolved_model"),
            "provider": self.expected_route.get("provider"),
            "tier": self.expected_route.get("tier"),
        }
        if entry.get("route_error"):
            return str(entry["route_error"])
        if route != expected or any(value is None for value in route.values()):
            return "returned route metadata does not match the frozen route"
        return None

    def infer(self, request, *, evidence: dict | None = None):
        from settlement.gateway import GatewayError
        if self.is_cost_blocked():
            self._refuse(self.cost_blocked, kind="cost")
        if request.model != self.pinned_model:
            self._refuse("request model is not the pinned model %r"
                         % self.pinned_model, kind="model")
        if self.is_ceiling_reached():
            self._refuse("study model-call ceiling %d reached"
                         % self.ceiling, kind="ceiling")
        attempts = 0
        while True:
            attempts += 1
            self.dispatch_count += 1
            try:
                response = self.delegate.infer(request)
            except Exception as exc:
                from . import frontier
                raw_prompt = (evidence or {}).get("raw_prompt")
                if raw_prompt is None:
                    raw_prompt = "".join(
                        str(message.get("content", ""))
                        for message in request.messages
                        if message.get("role") == "user")
                usage = _usage_snapshot(None)
                entry = frontier.make_evidence_record(
                    "gateway-dispatch", request.operation_id, "unresolved",
                    attempt=attempts,
                    arm=(evidence or {}).get("arm"),
                    task_id=(evidence or {}).get("task"),
                    input_digest=source_digest(raw_prompt),
                    details={"raw_payload": {"raw_prompt": raw_prompt,
                                             "raw_response": None},
                             "exception_class": type(exc).__name__,
                             "exception_reason": str(exc),
                             "usage": usage})
                entry.update({"exception_class": type(exc).__name__,
                              "exception_reason": str(exc),
                              "prompt_digest": source_digest(raw_prompt),
                              "raw_prompt": raw_prompt,
                              "raw_response": None,
                              "response_digest": None,
                              "usage": usage})
                self._record(entry)
                raise
            if isinstance(response, GatewayError):
                self._note_cost(response.usage)
                raw_prompt = (evidence or {}).get("raw_prompt")
                if raw_prompt is None:
                    raw_prompt = "".join(
                        str(message.get("content", ""))
                        for message in request.messages
                        if message.get("role") == "user")
                from . import frontier
                usage = _usage_snapshot(response.usage)
                entry = frontier.make_evidence_record(
                    "gateway-dispatch", request.operation_id,
                    "failure" if not response.retryable else "unknown",
                    attempt=attempts,
                    arm=(evidence or {}).get("arm"),
                    task_id=(evidence or {}).get("task"),
                    input_digest=source_digest(raw_prompt),
                    details={"raw_payload": {"raw_prompt": raw_prompt,
                                            "raw_response": None},
                             "diagnosis": classify_error(response),
                             "usage": usage})
                diagnosis = classify_error(response)
                route_error = diagnosis["route_error"]
                entry.update({
                    "diagnosis": diagnosis,
                    "raw_prompt": raw_prompt,
                    "prompt_digest": source_digest(raw_prompt),
                    "raw_response": None,
                    "response_digest": diagnosis["response_digest"],
                    "requested_model": request.model,
                    "returned_model": None,
                    "endpoint": None,
                    "provider": None,
                    "tier": None,
                    "requested_output_cap": request.max_output_tokens,
                    "stop_reason": "",
                    "response_received": diagnosis["response_received"],
                    "response_status": diagnosis["response_status"],
                    "route_error": route_error,
                    "usage": usage,
                    "billed": usage["billed"],
                    "charge_units": usage["charge_units"],
                    "accepted_candidate_digest": None,
                    "parse_outcome": ("route-refused" if route_error is not None
                                      else "transport-error"),
                })
                self._record(entry)
                if response.retryable and attempts <= self.automatic_retries \
                        and not self.is_ceiling_reached() \
                        and not self.is_cost_blocked():
                    continue
                return response
            self._note_cost(response.usage)
            entry = self._evidence_entry(request, response, attempts, evidence)
            if self.cost_blocked is not None:
                entry["cost_blocked"] = self.cost_blocked
            self._record(entry)
            route_failure = self._route_failure(entry)
            if route_failure:
                entry["parse_outcome"] = "route-refused"
                self._refuse(route_failure, kind="route")
            text = getattr(response, "text", "") or ""
            if not text.strip():
                entry["parse_outcome"] = "empty"
                if attempts <= self.automatic_retries \
                        and not self.is_ceiling_reached() \
                        and not self.is_cost_blocked():
                    continue
                return response
            return response

    def provenance(self, operation_id: str) -> dict:
        matches = [entry for entry in self.ledger
                   if entry.get("operation_id") == operation_id
                   and entry.get("kind") == "gateway-dispatch"
                   and entry.get("dispatch_evidence_digest") is None]
        if not matches:
            raise LiveRefused("dispatch evidence is missing")
        return dict(matches[-1])

    def finalized_dispatches(self) -> list:
        final_by_dispatch = {
            entry.get("dispatch_evidence_digest"): entry
            for entry in self.finalizations}
        return [final_by_dispatch.get(entry.get("evidence_digest"), entry)
                for entry in self.ledger]

    def finalize_evidence(self, operation_id: str, *, parse_outcome: str,
                          accepted_candidate_digest=None,
                          parsed_source_digest=None, package_digest=None,
                          parent_digest=None, round_no=None) -> dict:
        previous = self.provenance(operation_id)
        from . import frontier
        details = dict(previous.get("details") or {})
        entry = frontier.make_evidence_record(
            "gateway-dispatch", operation_id, previous["outcome"],
            attempt=previous.get("attempt"),
            arm=previous.get("arm"), task_id=previous.get("task_id"),
            source_digest=parsed_source_digest,
            artifact_digest=package_digest or accepted_candidate_digest,
            input_digest=previous.get("input_digest"),
            result_digest=previous.get("result_digest"),
            package_digest=package_digest, parent_digest=parent_digest,
            round_no=round_no,
            dispatch_evidence_digest=previous["evidence_digest"],
            details=details)
        for key in (
                "requested_model", "returned_model", "endpoint",
                "provider", "tier", "requested_output_cap",
                "response_digest", "prompt_digest", "raw_prompt",
                "raw_response", "stop_reason", "usage", "billed",
                "charge_units", "route_error", "cost_blocked",
                "response_received", "response_status",
                "exception_class", "exception_reason", "diagnosis"):
            if key in previous:
                entry[key] = previous[key]
        entry["parse_outcome"] = str(parse_outcome)
        entry["accepted_candidate_digest"] = accepted_candidate_digest
        self.finalizations.append(entry)
        return dict(entry)

    def check_discovery(self):
        return self.delegate.check_discovery()

    def check_auth(self):
        return self.delegate.check_auth()

    def cancel(self, operation_id):
        return self.delegate.cancel(operation_id)

    def guard_status(self) -> dict:
        if self.cost_blocked is not None:
            kind = "cost"
        else:
            kind = self.refusal_kind
        return {"pinned_model": self.pinned_model,
                "ceiling": self.ceiling,
                "dispatch_count": self.dispatch_count,
                "refusal_reason": self.refusal_reason,
                "refusal_kind": kind,
                "cost_blocked": self.cost_blocked,
                "ceiling_reached": self.is_ceiling_reached(),
                "version": LIVE_VERSION}


def diagnose_construction(failure: Exception, calls_made: int) -> dict:
    text = str(failure)
    for stage in ("transport", "parse", "gate", "execute", "check",
                  "repair-transport"):
        if stage in text:
            return {"stage": stage, "reason": text,
                    "calls_made": calls_made}
    if "exhausted" in text or "cap reached" in text:
        return {"stage": "exhausted", "reason": text,
                "calls_made": calls_made}
    if "unavailable" in text:
        return {"stage": "unavailable", "reason": text,
                "calls_made": calls_made}
    return {"stage": "unknown", "reason": text, "calls_made": calls_made}


def construct_live_policy(dsn: str, *, campaign_id: str, task: dict,
                          experience: dict, budget: dict, gateway,
                          model: str, study_root: str | None = None,
                          parent_digest: str | None = None) -> dict:
    from . import construct
    try:
        member = construct.construct_policy(
            dsn, campaign_id=campaign_id, task=task, experience=experience,
            budget=budget, gateway=gateway, model=model,
            study_root=study_root, parent_digest=parent_digest,
            applicability={"family": task.get("family", ""),
                           "task_id": task.get("task_id", "")})
    except construct.ConstructionFailed as exc:
        raise LiveRefused("live policy acquisition failed: %s"
                          % exc) from exc
    return {**member, "origin": ACQUIRED_ORIGIN,
            "live_version": LIVE_VERSION}


def construct_live_method(dsn: str, *, campaign_id: str, task: dict,
                          experience: dict, budget: dict, gateway,
                          model: str, study_root: str | None = None) -> dict:
    from . import construct
    try:
        member = construct.construct_method(
            dsn, campaign_id=campaign_id, task=task, experience=experience,
            budget=budget, gateway=gateway, model=model,
            study_root=study_root)
    except construct.ConstructionFailed as exc:
        raise LiveRefused("live method acquisition failed: %s"
                          % exc) from exc
    return {**member, "origin": ACQUIRED_ORIGIN,
            "live_version": LIVE_VERSION}


def parse_live_improver(text: str) -> dict:
    from . import method_exec
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines)
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise LiveRefused("live improver is not JSON: %s" % exc) from exc
    source = payload.get("entry") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or set(payload) != {"entry"}:
        raise LiveRefused("live improver must contain only entry source")
    if not isinstance(source, str) or not source.strip():
        raise LiveRefused("live improver holds no entry source")
    try:
        method_exec.verify_step_source(source, "STEP")
    except method_exec.MethodExecutionError as exc:
        raise LiveRefused("live improver fails STEP gate: %s" % exc) from exc
    return {"imp_source": source,
            "imp_digest": source_digest(source),
            "response_digest": response_digest(text)}


BOOLEAN_TOP_KEYS = frozenset({"specs"})
BOOLEAN_SPEC_KEYS = frozenset({"const", "mask", "pair"})
BOOLEAN_PAIRS = frozenset({(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)})


def extract_fenced_json(text: str) -> str:
    body = text or ""
    if "```" not in body:
        return body.strip()
    start = body.index("```") + 3
    first_line_end = body.find("\n", start)
    if first_line_end == -1:
        inner_start = start
    else:
        opener = body[start:first_line_end].strip()
        if opener and set(opener) <= set("jsonJSON \t"):
            inner_start = first_line_end + 1
        else:
            inner_start = start
    end = body.find("```", inner_start)
    if end == -1:
        raise LiveRefused("boolean payload fence never closes")
    return body[inner_start:end].strip()


def validate_boolean_payload(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload.keys()) != \
            BOOLEAN_TOP_KEYS:
        raise LiveRefused("boolean payload fails schema: top needs specs")
    specs = payload.get("specs")
    if type(specs) is not list or len(specs) != 4:
        raise LiveRefused("boolean payload fails schema: specs needs 4")
    for spec in specs:
        if not isinstance(spec, dict) or set(spec.keys()) != \
                BOOLEAN_SPEC_KEYS:
            raise LiveRefused(
                "boolean payload fails schema: spec keys const mask pair")
        const = spec.get("const")
        mask = spec.get("mask")
        pair = spec.get("pair")
        if type(const) is not int or const not in (0, 1):
            raise LiveRefused(
                "boolean payload fails schema: const is 0 or 1")
        if type(mask) is not int or not 0 <= mask <= 15:
            raise LiveRefused(
                "boolean payload fails schema: mask is 0 to 15")
        if pair is None:
            continue
        if type(pair) is not list or len(pair) != 2:
            raise LiveRefused(
                "boolean payload fails schema: pair is null or two indices")
        if any(type(v) is not int for v in pair):
            raise LiveRefused(
                "boolean payload fails schema: pair holds integers")
        if tuple(pair) not in BOOLEAN_PAIRS:
            raise LiveRefused(
                "boolean payload fails schema: unknown pair")
    return payload


def extract_and_validate_boolean(text: str) -> dict:
    try:
        body = extract_fenced_json(text)
    except LiveRefused:
        raise
    except Exception as exc:
        raise LiveRefused("boolean payload fence fails: %s" % exc) from exc
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise LiveRefused("boolean payload is not JSON: %s" % exc) from exc
    return validate_boolean_payload(payload)


def validate_acquired_provenance(package: dict, original: dict,
                                  finalization: dict) -> dict:
    from . import frontier
    try:
        return frontier.validate_acquisition_evidence(
            package, original, finalization)
    except frontier.Refused as exc:
        raise LiveRefused(str(exc)) from exc


def _require_acquisition_package(package, action: str) -> None:
    if not isinstance(package, dict):
        raise LiveRefused("%s requires model provenance" % action)
    if package.get("origin") != ACQUIRED_ORIGIN:
        raise LiveRefused("%s requires an acquired package" % action)
    if package.get("source_kind") != "model-response":
        raise LiveRefused("%s requires model-response source kind" % action)
    if not isinstance(package.get("provenance"), dict):
        raise LiveRefused("%s requires dispatch evidence provenance" % action)


def retain_acquired(store, package: dict,
                    dispatch_evidence: dict | None = None) -> dict:
    from . import frontier as _frontier
    _require_acquisition_package(package, "acquired retention")
    if dispatch_evidence is None:
        raise LiveRefused("acquired retention requires dispatch evidence")
    try:
        _frontier.validate_package(package, grant=dict(store._doc["grant"]))
    except _frontier.Refused as exc:
        raise LiveRefused("invalid acquired package: %s" % exc) from exc
    try:
        store.retain_acquisition(package, dispatch_evidence)
    except _frontier.Refused as exc:
        raise LiveRefused(str(exc)) from exc
    return {"package_digest": package["package_digest"],
            "control_id": package["control_id"]}


def digest_chain(response_text: str, source: str, child_receipt: dict,
                 action: dict, effect: dict) -> dict:
    return {"response_digest": response_digest(response_text),
            "source_digest": source_digest(source),
            "child": {"operation_id": child_receipt.get("operation_id"),
                      "outcome": child_receipt.get("outcome")},
            "action_kind": (action or {}).get("kind"),
            "effect": effect}


LIVE_MISSION_OBJECTIVE = "smaller valid explanatory examples"
LIVE_AUTHORITY = {"queries": 16, "steps": 12}


def live_mission(objective: str, environments: list) -> dict:
    if not isinstance(objective, str) or not objective.strip():
        raise LiveRefused("live mission needs an objective")
    if not isinstance(environments, list) or not environments:
        raise LiveRefused("live mission needs frozen environments")
    return {"objective": objective, "environments": list(environments)}


def ensure_live_store(path, mission: dict, authority: dict):
    from . import frontier as _frontier
    import os
    if os.path.exists(str(path)):
        store = _frontier.FrontierStore(str(path))
        if store._doc.get("mission", {}).get("objective") != \
                mission.get("objective"):
            raise LiveRefused("live store mission mismatch")
        return store
    if not isinstance(mission, dict) or not mission.get("objective") \
            or not isinstance(mission.get("environments"), list):
        raise LiveRefused("live mission needs objective plus environments")
    return _frontier.create_store(
        path, namespace=_frontier.NAMESPACE,
        mission={"objective": mission["objective"],
                 "environments": list(mission["environments"])},
        authority={"queries": int(authority["queries"]),
                   "steps": int(authority["steps"])})


def propose_live_work(store, opportunities: list) -> list:
    admitted = []
    for opportunity in opportunities:
        try:
            record = store.propose(dict(opportunity))
        except Exception as exc:
            from . import frontier as _frontier
            if "already exists" in str(exc):
                continue
            raise LiveRefused("live opportunity refused: %s" % exc) \
                from exc
        admitted.append(record["opportunity_id"])
    return admitted


def live_opportunity(oid: str, task: str, question: str,
                     instrument: str = "boolean-rule-v1",
                     x: int | None = None,
                     queries: int = 1, steps: int = 1) -> dict:
    intervention: dict = {"instrument": instrument, "target": task}
    if x is not None:
        intervention["inputs"] = {"x": int(x)}
    return {
        "opportunity_id": oid,
        "mission_link": LIVE_MISSION_OBJECTIVE,
        "question": question,
        "intervention": intervention,
        "resources": {"queries": int(queries), "steps": int(steps)},
    }


def bind_live_control(store, which: str = "low"):
    from . import frontier as _frontier
    from . import improve_channel as _channel
    package = _channel.make_control(which)
    if package.get("origin") != APPARATUS_ORIGIN:
        raise LiveRefused("live control is not labeled authored-control")
    if store.active_package is None:
        return store.bind_active(package)
    active = store.active_package
    if active.get("package_digest") != package.get("package_digest"):
        raise LiveRefused("live store already binds a different program")
    return active


def choose_next_work(store, package: dict, experience: list) -> dict:
    from . import frontier as _frontier
    from . import improve_channel as _channel
    if not isinstance(package, dict) or not package.get("package_digest"):
        raise LiveRefused("live choice needs the bound package digest")
    if package.get("package_digest") != store.active_digest:
        raise LiveRefused("live choice program is not the bound program")
    view = store.step_view(_frontier.OPERATE, package)
    view["experience"] = list(experience)
    try:
        result = _channel.run_operate_step(package, view, {})
    except _frontier.Refused as exc:
        raise LiveRefused("live frontier choice refused: %s" % exc) \
            from exc
    return {"action": result["action"], "state": result["state"],
            "executed_digest": result["executed_digest"],
            "choice": result["action"].get("inputs", {}).get(
                "opportunity_id")}


def execute_chosen_work(store, action: dict, task=None) -> dict:
    from . import frontier as _frontier
    from . import improve_channel as _channel
    try:
        return _channel.execute_operate_action(store, action, task)
    except _frontier.Refused as exc:
        raise LiveRefused("live effect refused: %s" % exc) from exc


def run_live_improve_round(store, task, package: dict,
                           round_no: int, arm: str | None = None) -> dict:
    from . import frontier as _frontier
    from . import improve_channel as _channel
    if package.get("package_digest") != store.active_digest:
        raise LiveRefused("live improvement program is not bound")
    try:
        return _channel.drive_improve_round(
            store, task, package=dict(package), round_no=int(round_no),
            arm=arm, admit_probes=True)
    except _frontier.Refused as exc:
        raise LiveRefused("live improvement refused: %s" % exc) from exc


def _build_live_package(parent: dict, imp_source: str,
                        control_id: str, provenance=None) -> dict:
    from . import frontier as _frontier
    from . import method_exec as _exec
    if parent.get("package_digest") is None:
        raise LiveRefused("live package needs a bound parent")
    try:
        _exec.verify_step_source(imp_source, "STEP")
    except _exec.MethodExecutionError as exc:
        raise LiveRefused("live improver fails STEP gate: %s" % exc) \
            from exc
    op_source = parent["op_source"]
    version = int(parent.get("version", 0)) + 1
    from . import frontier
    provenance_digest = (None if provenance is None else
                         frontier.source_digest(frontier.canonical(
                             provenance)))
    package = {
        "control_id": control_id,
        "origin": ACQUIRED_ORIGIN,
        "source_kind": "model-response",
        "op_source": op_source,
        "imp_source": imp_source,
        "op_digest": _frontier.source_digest(op_source),
        "imp_digest": _frontier.source_digest(imp_source),
        "parent_digest": parent["package_digest"],
        "provenance": provenance,
        "provenance_digest": provenance_digest,
        "version": version,
        "authority_request": dict(parent.get("authority_request") or {
            "queries": 16, "steps": 12}),
        "obligations": ["re-test probe divergence on new seeds"],
        "channel": parent.get("channel", "invl02-improve-v1"),
    }
    package["package_digest"] = _frontier.package_digest(package)
    return package


def parse_and_build_live_package(parent: dict, response_text: str,
                                 control_id: str,
                                 dispatch: dict | None = None) -> dict:
    from . import frontier
    parsed = parse_live_improver(response_text)
    provenance = None
    if dispatch is not None:
        try:
            evidence = frontier.validate_evidence_record(
                dispatch, kind="gateway-dispatch", outcome="success")
        except frontier.Refused as exc:
            raise LiveRefused("invalid dispatch evidence: %s" % exc) from exc
        raw_payload = evidence["details"].get("raw_payload")
        raw_response = raw_payload.get("raw_response") \
            if isinstance(raw_payload, dict) else None
        if raw_response != response_text or evidence.get("result_digest") != \
                response_digest(response_text) or evidence.get(
                    "input_digest") != response_digest(
                        raw_payload.get("raw_prompt", "")):
            raise LiveRefused("dispatch evidence does not match raw response")
        provenance = {
            "version": frontier.EVIDENCE_VERSION,
            "kind": "gateway-dispatch",
            "operation_id": evidence["operation_id"],
            "prompt_digest": evidence["input_digest"],
            "response_digest": evidence["result_digest"],
            "parsed_source_digest": parsed["imp_digest"],
            "dispatch_evidence_digest": (
                evidence.get("dispatch_evidence_digest")
                or evidence["evidence_digest"]),
        }
    package = _build_live_package(parent, parsed["imp_source"],
                                  control_id, provenance)
    package["response_digest"] = response_digest(response_text)
    package["response_source_digest"] = parsed["imp_digest"]
    return package


def activate_control_revision(store, candidate: dict) -> dict:
    from . import frontier as _frontier
    if not isinstance(candidate, dict) or candidate.get("origin") != \
            APPARATUS_ORIGIN or candidate.get("source_kind") != \
            "fixed-menu":
        raise LiveRefused("control activation admits only"
                          " fixed-menu authored-control packages")
    try:
        bound = store.adopt_revision(candidate)
    except _frontier.Refused as exc:
        raise LiveRefused("control activation refused: %s" % exc) \
            from exc
    return {"activation": "control",
            "package_digest": bound["package_digest"],
            "control_id": bound["control_id"]}


def bind_live_revision(store_path, package: dict, task: dict,
                        arm: str) -> dict:
    from . import frontier as _frontier
    store = _frontier.FrontierStore(str(store_path))
    store._validate_active_package()
    retained = [candidate for candidate in
                store._doc["treatment_arms"]["acquired"]
                if candidate.get("package_digest") == package.get(
                    "package_digest")]
    if not retained:
        raise LiveRefused("retained without binding: package is not retained")
    try:
        _frontier.validate_package(package, grant=store._doc["grant"])
    except _frontier.Refused as exc:
        raise LiveRefused("invalid retained package: %s" % exc) from exc
    if _frontier.canonical(package) != _frontier.canonical(retained[0]):
        raise LiveRefused("retained package differs from durable candidate")
    if store.active_digest == retained[0]["package_digest"]:
        bound = store.active_package
    else:
        bound = adopt_live_revision(store, retained[0], arm=arm)
    restarted = restart_store(str(store_path))
    if restarted.active_digest != bound.get("package_digest"):
        raise LiveRefused("retained without binding: durable active"
                          " digest differs from the retained package")
    try:
        probe = run_live_improve_round(
            restarted, task, package=restarted.active_package,
            round_no=int(bound.get("version", 0)), arm=arm)
    except LiveRefused as exc:
        raise LiveRefused("rejected: post-restart round refused: %s"
                          % exc) from exc
    executed = [entry for entry in probe.get("log", [])
                if entry.get("executed_digest") == bound.get("imp_digest")
                and not str(entry.get("result", "")).startswith("refused")]
    if probe.get("candidate") is None or not executed:
        raise LiveRefused("rejected: post-restart round produced no"
                          " usable candidate under the bound bytes")
    receipts = [receipt for receipt in probe.get("receipts", [])
                if isinstance(receipt, dict)]
    if not receipts:
        raise LiveRefused("rejected: post-restart child receipt is missing")
    receipt = receipts[0]
    try:
        restarted.record_revision_receipt(
            bound["package_digest"], receipt)
    except _frontier.Refused as exc:
        raise LiveRefused("rejected: child receipt lineage mismatch: %s"
                          % exc) from exc
    return {"disposition": "bound",
            "package_digest": bound["package_digest"],
            "control_id": bound["control_id"],
            "release_id": bound["control_id"],
            "executed_digest": bound["imp_digest"],
            "receipt_identity": receipt["receipt_identity"],
            "receipt_evidence_digest": receipt["evidence_digest"]}


def bind_retained_acquisition(store_path, acquisition: dict,
                              task: dict) -> dict:
    from . import frontier as _frontier
    control_id = acquisition.get("control_id", "")
    digest = acquisition.get("package_digest", "")
    try:
        store = _frontier.FrontierStore(str(store_path))
    except (OSError, ValueError, KeyError, TypeError,
            _frontier.Refused) as exc:
        return {"disposition": "retained",
                "reason": "retained without binding: store unreadable:"
                          " %s" % exc,
                "release_id": control_id, "bound_digest": digest}
    matches = [c for c in store._doc["treatment_arms"]["acquired"]
               if c.get("package_digest") == digest]
    if not matches:
        return {"disposition": "retained",
                "reason": "retained package missing from treatment arms",
                "release_id": control_id, "bound_digest": digest}
    if acquisition.get("response_digest") != matches[0].get(
            "response_digest"):
        return {"disposition": "retained",
                "reason": "retained package response digest mismatch",
                "release_id": control_id, "bound_digest": digest}
    try:
        return bind_live_revision(
            str(store_path), matches[0], task, str(acquisition.get("arm", "")))
    except (LiveRefused, _frontier.Refused) as exc:
        message = str(exc)
        if message.startswith("rejected:"):
            return {"disposition": "rejected", "reason": message,
                    "release_id": control_id, "bound_digest": digest}
        return {"disposition": "retained", "reason": message,
                "release_id": control_id, "bound_digest": digest}


def adopt_live_revision(store, candidate: dict,
                        arm: str | None = None) -> dict:
    from . import frontier as _frontier
    _require_acquisition_package(candidate, "live adoption")
    try:
        _frontier.validate_package(candidate, grant=store._doc["grant"])
    except _frontier.Refused as exc:
        raise LiveRefused("invalid acquired package: %s" % exc) from exc
    evidence_digest = candidate["provenance"].get(
        "dispatch_evidence_digest")
    records = store.evidence
    originals = [record for record in records
                 if record.get("evidence_digest") == evidence_digest
                 and record.get("dispatch_evidence_digest") is None]
    finalizations = [record for record in records
                     if record.get("dispatch_evidence_digest") == evidence_digest
                     and record.get("package_digest") == candidate.get(
                         "package_digest")]
    if len(originals) != 1 or len(finalizations) != 1:
        raise LiveRefused(
            "live adoption requires one original dispatch and linked finalization")
    try:
        validate_acquired_provenance(
            candidate, originals[0], finalizations[0])
        return store.adopt_revision(
            candidate, arm=arm, acquisition_evidence=finalizations[0])
    except (LiveRefused, _frontier.Refused) as exc:
        raise LiveRefused("live adoption refused: %s" % exc) from exc


def restart_store(path):
    from . import frontier as _frontier
    return _frontier.FrontierStore(str(path))


def live_frontier_round(store_path, mission: dict, authority: dict,
                        opportunities: list, task, package=None,
                        round_no: int = 1,
                        experience: list | None = None) -> dict:
    store = ensure_live_store(store_path, mission, authority)
    propose_live_work(store, opportunities)
    active = store.active_package
    if active is None:
        active = bind_live_control(store, "low")
    elif package is not None:
        if package.get("package_digest") != active.get("package_digest"):
            raise LiveRefused("live round package is not the bound program")
        active = package
    exp = list(experience) if experience is not None else []
    chosen = choose_next_work(store, active, exp)
    effect: dict = {"status": "choice-only"}
    inner = chosen["action"]
    if inner.get("kind") == "investigate":
        effect = execute_chosen_work(store, inner, task)
    elif inner.get("kind") == "probe":
        effect = execute_chosen_work(store, inner, task)
    improved = run_live_improve_round(store, task, active,
                                      int(round_no))
    candidate = improved["candidate"]
    return {"store_path": str(store_path),
            "active_digest": active["package_digest"],
            "choice": chosen["choice"],
            "action": chosen["action"],
            "executed_digest": chosen["executed_digest"],
            "effect": effect,
            "candidate_id": candidate["control_id"],
            "candidate_digest": candidate["package_digest"],
            "parent_digest": candidate["parent_digest"],
            "executed_imp_digest": active["imp_digest"],
            "observations": improved["observations"],
            "log": improved["log"]}
