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
OUTPUT_ROUND = 4
OUTPUT_STUDY_ROOT = "invl02-output-shape-550b-r%d" % OUTPUT_ROUND
OUTPUT_PROTOCOL_ID = "invl02-output-shape-550b-r%d-v1" % OUTPUT_ROUND
# Re-frozen 2026-09-29 for the W1/E1 study root. The 2026-09-26 freeze named
# `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`, and that spelling no
# longer exists in the live 255-entry catalog: the aggregator moved the
# prefix. The same model answers today under the bare id, and the route
# validator accepts it. This is configuration drift, not model unavailability.
#
# Changing this constant invalidates every frozen bundle that pinned the old
# one, by design: `offline_recompute` and `invl02_live` both compare against
# this dict. Old results are retained under their own freeze and are never
# mixed with results produced under this one. See
# reports/cap-sheets/w1-e1-cap.md for the lineage.
OUTPUT_ROUTE = {
    "endpoint": "http://localhost:4000/v1",
    "requested_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
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


class PreGatewayRefusal(Exception):
    """Raised by a delegate for a request it never put on the wire.

    A delegate decides this before contacting the gateway, so the attempt
    spent nothing. The guard cannot derive it: ``infer`` either returns or
    raises, and a raise after a send looks identical. Claiming it is the
    delegate's responsibility, and a delegate that claims it wrongly has
    exempted itself from the ceiling.
    """


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


def output_operation_id(arm: str, split: str, seed: int, attempt: int, *,
                        round_run_id: str) -> str:
    if arm not in ("P1", "P2") or split not in OUTPUT_TASKS:
        raise LiveRefused("output operation has an unknown arm or task")
    if int(seed) != OUTPUT_TASKS[split] or attempt not in (1, 2):
        raise LiveRefused("output operation has an unfrozen task or attempt")
    if not isinstance(round_run_id, str) or not round_run_id:
        raise LiveRefused("output operation has no frozen round identity")
    round_token = hashlib.sha256(round_run_id.encode("utf-8")).hexdigest()[:12]
    return f"invl02-output-{round_token}-{arm}-{split}-{int(seed):04d}-a{int(attempt)}"


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


ACQUISITION_EVIDENCE_VERSION = "invl02-acquisition-evidence-v1"

# A receipt that names a model, a provider and a route the adapter itself
# stamped. `simulated` is the field every adapter in this repo is required to
# set on a fixture response (`experiments/doubles.py` forces it True last, so
# a scripted script cannot clear it), so its absence is the signal that no
# fixture produced these bytes.
_LIVE_META_FIELDS = ("model", "provider", "tier")

# A router serves a model under an aggregator-prefixed id and reports the
# vendor's own id back. `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`
# is how a study asks for `nvidia/nemotron-3-ultra-550b-a55b:free`, which is
# how the receipt names it. Those are one model, and this repository has
# already settled that they differ: `tests/test_inv_r1_live_route_pin.py`
# records that a guard requiring the two fields to be equal refused every
# real route.
#
# So the check has to join the two forms rather than pick one. It is still a
# narrow check, and narrowing it further would defeat it: a prefix is only
# stripped when what remains is itself a namespaced id, so a bare model name
# has to match the resolved name exactly and a doubled prefix cannot match.
# This is a spelling join, not a model-identity claim -- the route contract
# (`provider`, `tier`, and the catalog preflight) is what establishes that a
# live provider answered, and this function requires all of that too.
_MODEL_PREFIXES = ("openrouter/", "kilo/")


def _same_model(requested: object, resolved: object) -> bool:
    """Whether these two names are one model written two ways.

    `requested` is what the study dispatched and `resolved` is what the
    adapter stamped on the receipt. They are different route fields, so
    equality is the wrong question; whether they denote the same model is
    the right one.
    """
    if not isinstance(requested, str) or not isinstance(resolved, str):
        return False
    if requested == resolved:
        return True
    if "/" not in resolved:
        return False
    return any(requested.startswith(prefix)
               and requested[len(prefix):] == resolved
               for prefix in _MODEL_PREFIXES)


def _receipt_meta(content: dict) -> dict:
    meta = (content or {}).get("model_meta")
    return dict(meta) if isinstance(meta, dict) else {}


def read_acquisition_evidence(dsn: str, operation_id: str,
                             response_text: str) -> dict:
    """What the store can prove about who produced these bytes.

    `origin` used to be a literal the construction path wrote unconditionally,
    so a record could say `model-acquired` with no model anywhere in its
    history. This reads the operation's own committed prompt and its settled
    receipt, and reports whether a live provider answered. The prompt is
    committed by `broker.ensure_operation` before the send, so the bytes the
    member claims to be built from and the bytes a provider was asked about
    are the same bytes.

    The verdict is deliberately narrow. `model` matching is not enough: a
    caller that pinned its own model to the double's label would pass it. So
    `earned` also requires route metadata that only an HTTP adapter emits,
    and `simulated` to be absent rather than merely false.
    """
    import hashlib as _hashlib
    from psycopg.rows import dict_row
    from settlement import db
    if not isinstance(operation_id, str) or not operation_id:
        raise LiveRefused("acquisition evidence needs an operation identity")
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT payload FROM operations WHERE id = %s",
                        (operation_id,))
            op = cur.fetchone()
            cur.execute(
                "SELECT receipt_identity, outcome, content FROM receipts"
                " WHERE operation_id = %s AND outcome = 'success'"
                " ORDER BY receipt_identity",
                (operation_id,))
            receipts = cur.fetchall()
            conn.commit()
    if op is None:
        return {"operation_id": operation_id, "earned": False,
                "reason": "no committed operation %r" % operation_id,
                "prompt_digest": None, "receipt_identity": None,
                "route": {}, "simulated": None, "response_digest": None}
    payload = dict(dict(op.get("payload") or {}).get("payload") or {})
    messages = [m for m in (payload.get("messages") or [])
                if isinstance(m, dict) and m.get("role") == "user"]
    prompt = "".join(str(m.get("content", "")) for m in messages)
    prompt_digest = _hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    requested_model = payload.get("model")
    if not receipts:
        return {"operation_id": operation_id, "earned": False,
                "reason": "operation %r has no settled success receipt"
                          % operation_id,
                "prompt_digest": prompt_digest, "receipt_identity": None,
                "route": {}, "simulated": None, "response_digest": None,
                "requested_model": requested_model}
    receipt = receipts[0]
    content = dict(receipt.get("content") or {})
    meta = _receipt_meta(content)
    text = content.get("text")
    response_digest = _hashlib.sha256(
        str(text).encode("utf-8")).hexdigest() if isinstance(text, str) \
        else None
    route = {field: meta.get(field) for field in _LIVE_META_FIELDS}
    simulated = meta.get("simulated")
    evidence = {
        "operation_id": operation_id,
        "version": ACQUISITION_EVIDENCE_VERSION,
        "prompt_digest": prompt_digest,
        "requested_model": requested_model,
        "receipt_identity": receipt.get("receipt_identity"),
        "response_digest": response_digest,
        "route": route,
        "simulated": simulated,
    }
    if response_digest != _hashlib.sha256(
            str(response_text).encode("utf-8")).hexdigest():
        evidence.update(earned=False,
                        reason="member bytes are not the settled response")
        return evidence
    if simulated is not None:
        evidence.update(earned=False, reason="response is marked simulated")
        return evidence
    missing = [field for field, value in route.items()
               if not isinstance(value, str) or not value]
    if missing:
        evidence.update(
            earned=False,
            reason="response carries no route metadata for %s"
                   % ", ".join(missing))
        return evidence
    if meta.get("adapter") != "http":
        evidence.update(
            earned=False,
            reason="response adapter is %r, not http" % meta.get("adapter"))
        return evidence
    if not _same_model(requested_model, route["model"]):
        evidence.update(
            earned=False,
            reason="requested model %r is not the resolved %r"
                   % (requested_model, route["model"]))
        return evidence
    evidence.update(earned=True, reason="live provider response")
    return evidence


def find_acquisition_operation(dsn: str, source_digest: str) -> str | None:
    """The settled construction operation whose response yielded these bytes.

    A replay rebuilds the artifact from a freeze, long after the send, and
    has to answer the same question the construction path answered: which
    operation produced this exact source. So the search is over the response
    receipts themselves, parsing each candidate response back to its entry
    source and comparing digests. A release whose bytes no operation produced
    has no origin to claim, and the caller is told so rather than guessing.
    """
    import hashlib as _hashlib
    from psycopg.rows import dict_row
    from settlement import db
    if not isinstance(source_digest, str) or not source_digest:
        raise LiveRefused("acquisition search needs a source digest")
    from . import packet as _packet
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT r.operation_id, r.content FROM receipts r"
                " WHERE r.outcome = 'success'"
                "   AND r.receipt_identity = 'gw:' || r.operation_id"
                "   AND (r.operation_id LIKE 'ad01-%-construct-l%'"
                "        OR r.operation_id LIKE 'ad01-%-policy-l%')")
            rows = cur.fetchall()
            conn.commit()
    found = None
    for row in rows:
        text = (dict(row.get("content") or {}).get("text"))
        if not isinstance(text, str):
            continue
        source, problem = _packet.parse_construction_response(text)
        if problem or not isinstance(source, str):
            continue
        if _hashlib.sha256(source.encode("utf-8")).hexdigest() == source_digest:
            found = row["operation_id"]
            break
    return found


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
        "provider_enforced_ceiling": (
            "unknown" if getattr(usage, "provider_enforced_ceiling", None) is None
            else getattr(usage, "provider_enforced_ceiling")),
        "billed": ("unknown" if getattr(usage, "billed", None) is None
                   else getattr(usage, "billed")),
    }


def _refresh_evidence_digest(entry: dict) -> dict:
    from . import frontier
    entry["evidence_digest"] = frontier._evidence_identity_digest(entry)
    return entry


def _unreached_entry(request, exc, attempt: int,
                     evidence: dict | None) -> dict:
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
        attempt=attempt,
        arm=(evidence or {}).get("arm"),
        task_id=(evidence or {}).get("task"),
        input_digest=source_digest(raw_prompt),
        parse_outcome="transport-error",
        accepted_candidate_digest=None,
        details={"raw_payload": {"raw_prompt": raw_prompt,
                                 "raw_response": None},
                 "exception_class": type(exc).__name__,
                 "exception_reason": str(exc),
                 "pre_gateway_refusal": True,
                 "usage": usage})
    entry.update({"exception_class": type(exc).__name__,
                  "exception_reason": str(exc),
                  "prompt_digest": source_digest(raw_prompt),
                  "raw_prompt": raw_prompt,
                  "raw_response": None,
                  "response_digest": None,
                  "pre_gateway_refusal": True,
                  "usage": usage})
    return entry


class LiveGuard:
    """A ceiling on sends.

    `ceiling` and the spend it is checked against are one currency: a send
    that reached the gateway. The store counts it the way the store counts
    it: `SELECT COUNT(*) FROM operations`, and a prepare the store refused
    inserted no row. Counting the guard's ledger instead would add the
    pre-gateway refusals the guard deliberately exempts, which is a
    different number and a worse one.

    A guard bound to a store reads its position from that store on every
    check, through `spend_reader`. It is not a cache of a number the
    caller passed in, so it moves as sends happen and it survives a
    resume: a process that never sent anything still sees the sends an
    earlier process made, and a send admitted a moment ago is counted
    without anyone incrementing anything here. That is what closes the
    second counter, which was `is_ceiling_reached` reading an integer this
    object maintained beside the broker's own.

    `dispatch_count` remains, and it is not the ceiling. It is the length
    of the attempt ledger, which `offline_recompute` reads as
    `candidate_view["dispatch_count"] == len(dispatches)` and which counts
    refused attempts as well as sends. Two counters of the send count was
    the defect; one counter of the attempt count beside the store's counter
    of the send count is two different facts.
    """

    def __init__(self, delegate, *, pinned_model: str, ceiling: int,
                 already_spent: int = 0,
                 automatic_retries: int = MAX_RETRIES,
                 expected_route: dict | None = None,
                 spend_reader=None) -> None:
        if not pinned_model:
            raise ValueError("pinned model is required")
        if ceiling < 0 or already_spent < 0:
            raise ValueError("ceiling and spent count must be nonnegative")
        if type(automatic_retries) is not int or automatic_retries < 0:
            raise ValueError("automatic retry limit must be nonnegative")
        if spend_reader is not None and not callable(spend_reader):
            raise ValueError("spend_reader must be a callable or omitted")
        self.delegate = delegate
        self.pinned_model = pinned_model
        self.ceiling = ceiling
        self.automatic_retries = automatic_retries
        self.expected_route = dict(expected_route) if expected_route else None
        self.spend_reader = spend_reader
        self.dispatch_count = already_spent
        self.refunded_dispatches = 0
        self.refusal_reason = ""
        self.refusal_kind = ""
        self.cost_blocked: str | None = None
        self.ledger: list = []
        self.finalizations: list = []

    @property
    def spent_dispatches(self) -> int:
        """Sends this study has made, in the currency the ceiling is in.

        With a store, that is the store's count and nothing else. The
        store already excludes the refusals the guard exempts, because a
        refused prepare wrote no row, so the refund arithmetic below does
        not apply to it: subtracting it here would count the refusal a
        second time. Without a store there is nothing to ask, so the
        in-process count stands and the refund that keeps a pre-gateway
        refusal off the ceiling still applies.
        """
        if self.spend_reader is not None:
            return int(self.spend_reader())
        return self.dispatch_count - self.refunded_dispatches

    def is_cost_blocked(self) -> bool:
        return self.cost_blocked is not None

    def is_ceiling_reached(self) -> bool:
        return self.spent_dispatches >= self.ceiling

    def _refuse(self, reason: str, kind: str = ""):
        self.refusal_reason = reason
        if kind:
            self.refusal_kind = kind
        elif self.cost_blocked is not None:
            self.refusal_kind = "cost"
        raise LiveRefused(reason)

    def _record(self, entry: dict) -> None:
        _refresh_evidence_digest(entry)
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
            parse_outcome="pending",
            accepted_candidate_digest=None,
            round_no=source.get("round"),
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
            "route_error": meta.get("route_error"),
        })
        return entry

    # The guard reads the fields a dispatch record carries, and a dispatch
    # record calls the served model `returned_model` where a response calls
    # it `model`. This table is the answer to "which recorded field is
    # which field of a returned route", and it is a join rather than a rule:
    # the comparison itself belongs to `route_matches`, which is also what
    # the catalog half and the response half use. Spelling `provider` here
    # is what cost the E1 campaign eight attempts and zero constructions, so
    # a route field this guard does not carry is refused rather than
    # skipped.
    _RETURNED_ROUTE_FIELDS = (
        ("endpoint", "endpoint"),
        ("returned_model", "model"),
        ("provider", "provider"),
        ("tier", "tier"),
    )

    def _route_failure(self, entry: dict) -> str | None:
        if self.expected_route is None:
            return None
        if entry.get("route_error"):
            return str(entry["route_error"])
        from settlement.gateway_http import route_matches
        if not route_matches(
                {route_key: entry.get(name)
                 for name, route_key in self._RETURNED_ROUTE_FIELDS},
                self.expected_route):
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
            except PreGatewayRefusal as exc:
                self.refunded_dispatches += 1
                self._record(_unreached_entry(request, exc, attempts, evidence))
                raise
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
                    parse_outcome="transport-error",
                    accepted_candidate_digest=None,
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
                    parse_outcome=("route-refused"
                                   if classify_error(response).get(
                                       "route_error") is not None
                                   else "transport-error"),
                    accepted_candidate_digest=None,
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
            from . import frontier
            if route_failure:
                entry["parse_outcome"] = "route-refused"
                entry["evidence_digest"] = frontier._evidence_identity_digest(
                    entry)
                self._refuse(route_failure, kind="route")
            text = getattr(response, "text", "") or ""
            if not text.strip():
                entry["parse_outcome"] = "empty"
                entry["evidence_digest"] = frontier._evidence_identity_digest(
                    entry)
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
        if (round_no is None or type(round_no) is not int
                or round_no < 0):
            raise LiveRefused("finalization needs a valid round")
        if (package_digest is not None and accepted_candidate_digest is not None
                and package_digest != accepted_candidate_digest):
            raise LiveRefused("finalization package identity conflicts")
        existing = [entry for entry in self.finalizations
                    if entry.get("dispatch_evidence_digest") == previous[
                        "evidence_digest"]]
        if existing:
            current = existing[-1]
            if current.get("package_digest") != package_digest:
                raise LiveRefused("finalization already recorded for dispatch")
            if (current.get("source_digest") != parsed_source_digest
                    or current.get("accepted_candidate_digest")
                    != accepted_candidate_digest
                    or current.get("parent_digest") != parent_digest
                    or current.get("round") != round_no
                    or current.get("parse_outcome") != str(parse_outcome)):
                raise LiveRefused("finalization conflicts with durable identity")
            return dict(current)
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
            driver_digest=previous.get("driver_digest"),
            operation_payload_digest=previous.get("operation_payload_digest"),
            parse_outcome=parse_outcome,
            accepted_candidate_digest=accepted_candidate_digest,
            details=details)
        for key in frontier.EVIDENCE_RESPONSE_FIELDS:
            if key in previous:
                entry[key] = previous[key]
        _refresh_evidence_digest(entry)
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
                "spent_dispatch_count": self.spent_dispatches,
                "refunded_dispatch_count": self.refunded_dispatches,
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


def _construct_receipts(probe: dict, round_no) -> list:
    """The step receipts of a round whose attested action is `construct`.

    A round is probe, construct, construct, so the receipt list is not one
    receipt. Position 0 is the probe, and certifying the probe would attest
    an execution that never built the package being bound. Selection is by
    the action the receipt itself attests, not by position, so the receipt
    that built the package is found whatever order the steps ran in.
    """
    found = []
    for receipt in probe.get("receipts", []):
        if not isinstance(receipt, dict):
            continue
        details = receipt.get("details")
        raw = details.get("raw_payload") if isinstance(details, dict) else None
        action = raw.get("action") if isinstance(raw, dict) else None
        frontier_action = action.get("inputs", {}).get(
            "frontier_action") if isinstance(action, dict) else None
        if not isinstance(frontier_action, dict) \
                or frontier_action.get("kind") != "construct":
            continue
        if int(receipt.get("round", -1)) != int(round_no):
            continue
        found.append(receipt)
    return found


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
    receipts = _construct_receipts(probe, bound.get("version", 0))
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


PREFLIGHT_VERSION = "invl02-live-preflight-v1"
PREFLIGHT_SCHEMA = "invl02-live-preflight-run-v1"
PREFLIGHT_RUN_ID = "invl02-preflight-w1"

# The five outcomes the assignment requires to stay apart. They are
# distinguishable facts about one attempt, not a verdict plus a reason
# string, so the run record carries the value and the evidence that
# produced it. A run that reported one boolean for all five would make a
# route refusal indistinguishable from a model that wrote bad code, which
# is the confusion that lets a failed preflight be reported as model
# inability.
PREFLIGHT_OUTCOMES = (
    "constructed",       # a program parsed, executed and scored above the bar
    "poor-task-result",  # a valid program that did not solve the task
    "invalid-program",   # content that will not parse as a Boolean policy
    "empty-content",     # HTTP 200 with a blank or whitespace-only body
    "route-refusal",     # the gateway refused, or the route did not match
    "transport-loss",    # no response: timeout, reset, unreachable
    "pre-dispatch-refusal",  # refused before the wire; nothing was sent
)

# A candidate program is worth keeping only if it beats doing nothing. The
# zero predictor scores 1/16 on a four-output task, and a program that
# cannot clear that is a failure dressed as a result. The bar is a
# literal, not a threshold tuned on any observed attempt.
PREFLIGHT_SCORE_FLOOR = 1.0


def _preflight_task():
    """The frozen task the preflight constructs against.

    Returns the public task, the session with its query budget already
    spent (the same shape the output study prompts with, so the model is
    asked to commit rather than probe) and the prompt. Reusing the frozen
    `OUTPUT_TASKS` entry and `render_output_prompt` is the point: a
    preflight that rendered its own prompt would be testing a second
    construction protocol, not the shipped one.
    """
    from . import boolean_rule as rules
    from . import rule_learner
    split = "qual"
    seed = int(OUTPUT_TASKS[split])
    task = rules.make_task(split, seed)
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, seed)
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        learner.observe(pick, session.query(pick))
    return task, session


def preflight_operation_id(arm: str, attempt: int) -> str:
    """The dispatch identity, from the shipped operation-id function."""
    return output_operation_id(arm, "qual", int(OUTPUT_TASKS["qual"]),
                               attempt, round_run_id=PREFLIGHT_RUN_ID)


class _DurablePreflightGateway:
    """A gateway adapter whose sends are durable operations.

    `preflight_run` used to hand a hand-built `ModelRequest` to
    `LiveGuard.infer`, which called the wrapped adapter directly. The
    operation id was minted by `preflight_operation_id` and never
    admitted anywhere, so a preflight send had no operation row, no
    reservation, no receipt and no exposure: it was a claim in a study
    record with nothing behind it.

    This is the adapter the preflight wraps instead. Every send goes
    through `broker.ensure_operation` and `broker.dispatch_operation`,
    which is the same pair `experiments/ad01/construct.py:_call` and
    `experiments/ad01/learner_revision.py:_dispatch` make. The store
    holds the identity and the allocation, and the broker writes the
    receipt and settles the reservation.

    Two properties fall out of that placement rather than out of any
    bookkeeping here. A second dispatch of one operation id finds a
    settled operation and returns the settled text without reaching the
    gateway, so identity is what stops a second send. And the number of
    sends is `COUNT(*) FROM operations` under the allocation, which is a
    fact the store holds after a crash, a resume or another process.

    The guard stays in place and stays the outer object. It owns the
    route check, the cost block and the evidence ledger, all of which
    are per-attempt observations of one send. What it no longer owns is
    the send's admission.
    """

    def __init__(self, dsn: str, delegate, *, allocation_id: str) -> None:
        self.dsn = dsn
        self.delegate = delegate
        self.allocation_id = allocation_id
        self.replayed_operation_ids: set[str] = set()
        self._refusal = PreGatewayRefusal

    def infer(self, request):
        from settlement import broker, store
        from settlement.common import ResultCode

        payload = {"model": request.model,
                   "messages": list(request.messages),
                   "max_output_tokens": request.max_output_tokens,
                   "deadline_ms": request.deadline_ms}
        ensured = broker.ensure_operation(
            self.dsn, operation_id=request.operation_id,
            effect=broker.MODEL_INFERENCE, payload=payload,
            allocation_id=self.allocation_id, retries=0,
            resource="construction_calls")
        if ensured.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
            # The store refused before the wire. The guard exempts this
            # marker from the ceiling, which is right: no send happened,
            # so there is nothing to spend.
            raise self._refusal(
                "preflight operation %s not admitted: %s"
                % (request.operation_id, ensured.detail))
        receipts = list(store.operation_receipts(
            self.dsn, request.operation_id) or [])
        if len(receipts) == 1 and not store.operation_receipt_conflicts(
                self.dsn, request.operation_id):
            self.replayed_operation_ids.add(request.operation_id)
            return _response_from_receipt(request.operation_id, receipts[0])
        status = broker.dispatch_operation(
            self.dsn, request.operation_id, gateway=self.delegate)
        settled = broker.read_operation(self.dsn, request.operation_id) or {}
        if settled.get("settled") is not True or status.dispatch_state in (
                "conflict", "unresolved"):
            raise self._refusal(
                "preflight operation %s did not settle (state=%s, next=%s)"
                % (request.operation_id, settled.get("dispatch_state"),
                   status.next_decision))
        receipts = list(store.operation_receipts(
            self.dsn, request.operation_id) or [])
        if len(receipts) != 1:
            raise self._refusal(
                "preflight operation %s holds %d receipts, so what came "
                "back from it is not one answer"
                % (request.operation_id, len(receipts)))
        return _response_from_receipt(request.operation_id, receipts[0])

    def check_discovery(self):
        return self.delegate.check_discovery()

    def check_auth(self):
        return self.delegate.check_auth()

    def cancel(self, operation_id):
        return self.delegate.cancel(operation_id)


def _response_from_receipt(operation_id: str, receipt: dict):
    """The guard's response, rebuilt from what the store settled.

    A durable send ends in a receipt rather than a return value, so the
    guard needs one reconstructed before it can read the route out of it.
    A `success` receipt carries the text; every other outcome is an error
    the guard already classifies, and the fields it reads are the ones the
    broker wrote into the receipt for exactly this reason.
    """
    from settlement.gateway import (
        GatewayError,
        GatewayErrorKind,
        GatewayRouteError,
        ModelResponse,
        Usage,
    )

    content = receipt.get("content") or {}
    raw_usage = content.get("usage")
    raw_usage = raw_usage if isinstance(raw_usage, dict) else {}
    usage = Usage(
        input_tokens=raw_usage.get("input_tokens"),
        output_tokens=raw_usage.get("output_tokens"),
        charge_units=raw_usage.get("charge_units"),
        charge_scale=raw_usage.get("charge_scale"),
        provider_enforced_ceiling=raw_usage.get("provider_enforced_ceiling"),
        billed=raw_usage.get("billed"))
    if receipt.get("outcome") == "success":
        return ModelResponse(
            operation_id, str(content.get("text", "")),
            dict(content.get("model_meta") or {}), usage,
            str(content.get("stop_reason", "")))
    route_error = content.get("route_error")
    return GatewayError(
        kind=_error_kind(content.get("error_kind")),
        message=str(content.get("error") or content.get("response_class")
                    or "the preflight send did not settle"),
        retryable=bool(content.get("retryable")),
        operation_id=operation_id,
        usage=usage,
        response_received=bool(content.get("response_received")),
        response_status=content.get("response_status"),
        response_digest=content.get("response_digest"),
        route_error=(GatewayRouteError(route_error)
                     if route_error else None))


def _error_kind(value) -> GatewayErrorKind:
    from settlement.gateway import GatewayErrorKind

    try:
        return GatewayErrorKind(str(value))
    except ValueError:
        return GatewayErrorKind.TRANSPORT


def spent_dispatches(dsn: str, allocation_id: str) -> int:
    """Sends the store holds under one allocation.

    This is the currency the ceiling is enforced in: `SELECT COUNT(*)
    FROM operations`, and a prepare the store refused inserted no row, so
    it counts sends that reached the store rather than attempts. It is
    the same read `scripts/invl02_live.py:_already_spent` makes and the
    same one `s09_study_preflight.already_spent_in_store` made after
    `9a1884d`.

    An unreadable store raises rather than returning zero. A zero here
    reads as "nothing spent", which is how a ceiling gets enforced against
    a fiction: the guard would believe it had the whole allowance on a
    store it had not been able to ask.
    """
    from psycopg.rows import dict_row
    from settlement import db

    try:
        with db.read_connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT COUNT(*) AS spent FROM operations"
                    " WHERE allocation_id = %s", (allocation_id,))
                spent = cur.fetchone()["spent"]
            conn.commit()
    except Exception as exc:
        raise LiveRefused(
            "the spend count is the store's and the store was not "
            "readable: %s: %s" % (type(exc).__name__, exc)) from exc
    return int(spent)


def preflight_dispatch_gateway(dsn: str, gateway, *, allocation_id: str):
    """The durable adapter, built by the one constructor callers use."""
    return _DurablePreflightGateway(dsn, gateway, allocation_id=allocation_id)


def _preflight_dispatch(guard, *, arm: str, attempt: int,
                        dsn: str | None = None,
                        allocation_id: str | None = None) -> dict:
    """One dispatch through the shipped guard, prompt and parser.

    The response is not inspected here. Every branch of the taxonomy is
    decided by a function this module already owns: `LiveGuard.infer`
    for the route and transport cases, `extract_and_validate_boolean`
    for a program that will not parse, and `RuleSession.score` for one
    that does. A preflight with its own transport, prompt or parser would
    be a second authority for construction.

    `dsn` and `allocation_id` make the send durable. With them the guard
    is handed an adapter that admits the operation and dispatches it
    through the broker, so the send carries a row, a reservation and a
    receipt, and a second call on one operation id settles nothing and
    sends nothing. Both are required together, because an operation
    admitted without an allocation is a row the store cannot charge.
    """
    if (dsn is None) != (allocation_id is None):
        raise ValueError(
            "a preflight send is durable or it is not: dsn and "
            "allocation_id are required together")
    from settlement.gateway import GatewayError, ModelRequest
    task, session = _preflight_task()
    history = [] if arm == "P1" else output_permitted_history()
    prompt = render_output_prompt(session.output_model_input(), history,
                                  attempt)
    operation_id = preflight_operation_id(arm, attempt)
    evidence = {"arm": arm, "task": task["task_id"], "attempt": attempt,
                "raw_prompt": prompt, "round": OUTPUT_ROUND}
    request = ModelRequest(
        model=guard.pinned_model,
        messages=({"role": "user", "content": prompt},),
        max_output_tokens=OUTPUT_LIMITS["max_output_tokens"],
        deadline_ms=300_000, operation_id=operation_id)
    try:
        response = guard.infer(request, evidence=evidence)
    except LiveRefused as exc:
        # The guard raises rather than returns for two unrelated reasons,
        # and they are not the same fact. A `route` refusal is a response
        # that came back and named a different route, so it has dispatch
        # evidence. A refusal of any other kind was decided before the
        # wire: the model was not the pinned one, the ceiling was
        # reached, or cost blocked a later call. Collapsing the second
        # into the first would charge a send that never happened.
        kind = guard.refusal_kind or "unknown"
        recorded = next((entry for entry in guard.ledger
                         if entry.get("operation_id") == operation_id), None)
        return {"outcome": ("route-refusal" if kind == "route"
                            else "pre-dispatch-refusal"),
                "operation_id": operation_id, "reason": str(exc),
                "refusal_kind": kind,
                "text": None, "raw_response": None, "dispatch": recorded}
    if isinstance(response, GatewayError):
        diagnosis = classify_error(response)
        recorded = next((entry for entry in guard.ledger
                         if entry.get("operation_id") == operation_id), None)
        # Whether a send that came back an error is a refusal or a lost
        # send is decided by `preflight_decision`, from the diagnosis the
        # guard recorded. Deciding it here as well would be a second
        # derivation of the same fact.
        entry = {"arm": arm, "attempt": attempt,
                 "operation_id": operation_id, "raw_response": None,
                 "candidate_digest": None, "score": None,
                 "dispatch": recorded, "diagnosis": diagnosis}
        decided = preflight_decision(entry, session=session)
        return {"outcome": decided["outcome"], "operation_id": operation_id,
                "reason": decided["reason"], "diagnosis": diagnosis,
                "text": None, "raw_response": None, "dispatch": recorded}
    text = response.text
    dispatch = guard.provenance(operation_id)
    over_length = len(text) > OUTPUT_LIMITS["max_response_characters"]
    if over_length:
        guard.finalize_evidence(operation_id, round_no=OUTPUT_ROUND,
                                parse_outcome="too-long")
    if not text.strip():
        guard.finalize_evidence(operation_id, round_no=OUTPUT_ROUND,
                                parse_outcome="empty")
        entry = {"arm": arm, "attempt": attempt,
                 "operation_id": operation_id, "raw_response": text,
                 "candidate_digest": None, "score": None,
                 "dispatch": dispatch}
        decided = preflight_decision(entry, session=session)
        return {"outcome": decided["outcome"], "operation_id": operation_id,
                "reason": decided["reason"], "text": text,
                "raw_response": text, "dispatch": dispatch}
    try:
        extract_and_validate_boolean(text)
        parses = True
    except Exception:
        parses = False
    if not parses:
        guard.finalize_evidence(operation_id, round_no=OUTPUT_ROUND,
                                parse_outcome="parse-failed")
    entry = {"arm": arm, "attempt": attempt, "operation_id": operation_id,
             "raw_response": text, "candidate_digest": None, "score": None,
             "dispatch": dispatch}
    decided = preflight_decision(entry, session=session)
    if parses:
        guard.finalize_evidence(
            operation_id, round_no=OUTPUT_ROUND, parse_outcome="accepted",
            accepted_candidate_digest=decided["candidate_digest"],
            parsed_source_digest=decided["candidate_digest"])
    return {"outcome": decided["outcome"], "operation_id": operation_id,
            "reason": decided["reason"], "text": text, "raw_response": text,
            "dispatch": dispatch,
            "candidate_digest": decided["candidate_digest"],
            "score": decided["score"]}


def preflight_verdict(attempt: dict) -> dict:
    """The taxonomy value plus the evidence that chose it.

    Derived from the written run record, never from a live call. The
    reason a verdict can be recomputed offline is that every input to it
    is in the record: the raw response, its digest, the stop reason, the
    route fields and the usage snapshot. A record missing one of them
    cannot yield a verdict, and says so instead of guessing.
    """
    if not isinstance(attempt, dict) or attempt.get("outcome") not in \
            PREFLIGHT_OUTCOMES:
        raise LiveRefused("preflight attempt carries no known outcome")
    verdict = {"outcome": attempt["outcome"],
               "operation_id": attempt.get("operation_id"),
               "reason": attempt.get("reason"),
               "attempt": output_operation_attempt(
                   attempt.get("operation_id")),
               "arm": attempt.get("arm")}
    dispatch = attempt.get("dispatch")
    if not isinstance(dispatch, dict):
        verdict["recomputable"] = False
        verdict["reason"] = "no dispatch evidence was recorded"
        return verdict
    verdict["recomputable"] = True
    verdict["response_digest"] = dispatch.get("response_digest")
    verdict["requested_model"] = dispatch.get("requested_model")
    verdict["returned_model"] = dispatch.get("returned_model")
    verdict["provider"] = dispatch.get("provider")
    verdict["tier"] = dispatch.get("tier")
    verdict["endpoint"] = dispatch.get("endpoint")
    verdict["stop_reason"] = dispatch.get("stop_reason")
    verdict["usage"] = dispatch.get("usage")
    verdict["prompt_digest"] = dispatch.get("prompt_digest")
    verdict["route_error"] = dispatch.get("route_error")
    return verdict


def output_operation_attempt(operation_id: str) -> int:
    """The attempt an operation identity was minted for, read back off it.

    `output_operation_id` ends every identity with `-a<attempt>`, so the
    attempt a dispatch was made on is a fact about the identity rather
    than a field the record asserts about itself. A lineage entry carries
    `attempt` beside it, and that field is a claim: nothing in the digest
    chain covers it, so a record could claim a second attempt of a
    campaign that spent one. Reading it off the identity is the
    re-derivation, and it is the same string the guard used to mint it.

    Raises `LiveRefused` for an identity that is not one of this
    operation's, because an identity this cannot read is an identity this
    cannot attest.
    """
    if not isinstance(operation_id, str) or not operation_id.startswith(
            "invl02-output-"):
        raise LiveRefused("operation identity is not an output dispatch")
    tail = operation_id.rsplit("-a", 1)
    if len(tail) != 2 or not tail[1].isdigit():
        raise LiveRefused("operation identity names no attempt")
    return int(tail[1])


def preflight_defect(attempt: dict) -> str:
    """Why this attempt's bytes are not a program, read off the bytes.

    `invalid-program` is one taxonomy value covering two different
    findings, and a reader needs to tell them apart: a reply that never
    stopped talking, and a reply that stopped and was still not a program.
    They have different causes -- one is the model's budget behaviour, the
    other is its output discipline -- and averaging them would hide both.

    Derived from the recorded `raw_response` rather than from the reason
    string, because the length is a fact about the bytes and the reason is
    prose about them. A record that carries a `reason` stating a length
    the bytes do not have is describing bytes it does not hold, and
    nothing downstream of this function can tell.

    `parses-but-was-classified-invalid` is reachable and is the shape of
    the forgery this exists to catch: an entry whose `outcome` says
    invalid-program while its own response is a program the frozen scorer
    would have run.
    """
    raw = attempt.get("raw_response")
    if not isinstance(raw, str):
        return "no-response-text"
    if len(raw) > OUTPUT_LIMITS["max_response_characters"]:
        return "over-length"
    try:
        extract_and_validate_boolean(raw)
    except Exception:
        return "would-not-parse"
    return "parses-but-was-classified-invalid"


def preflight_decision(entry: dict, session=None) -> dict:
    """Every claim an attempt entry makes, re-derived from its own fields.

    A lineage record mixes two kinds of field. An **observation** is a
    thing that happened at the gateway and is carried as-is: the route,
    `stop_reason`, the usage snapshot, the HTTP status. Nothing offline
    can re-derive those, because they are the event itself. A **claim** is
    a statement about the observations -- the taxonomy `outcome`, the
    `reason` prose, the `candidate_digest`, the `score`, the defect. A
    claim is worth nothing unless it is re-derived from the observations
    beside it, because a claim is a string anyone can write.

    This function is the one owner of the second kind. The driver calls it
    to decide an attempt and the offline verifier calls it to check one,
    so there is no second derivation for a record to disagree with, and
    the ladder it walks is the same ladder in both directions.

    `session` is the frozen task's scorer, and is required for any claim
    that needs a score. A record whose bytes parse but that does not
    supply one is refused rather than trusted.
    """
    raw = entry.get("raw_response")
    dispatch = entry.get("dispatch")
    if not isinstance(raw, str):
        return _preflight_decision_without_response(entry, dispatch)
    if len(raw) > OUTPUT_LIMITS["max_response_characters"]:
        return {"outcome": "invalid-program", "defect": "over-length",
                "candidate_digest": None, "score": None,
                "reason": "response of %d characters exceeds the frozen "
                          "limit of %d"
                          % (len(raw),
                             OUTPUT_LIMITS["max_response_characters"])}
    if not raw.strip():
        return {"outcome": "empty-content", "defect": "empty-content",
                "candidate_digest": None, "score": None,
                "reason": "gateway returned 200 with no content"}
    try:
        candidate = extract_and_validate_boolean(raw)
    except Exception as exc:
        return {"outcome": "invalid-program", "defect": "would-not-parse",
                "candidate_digest": None, "score": None,
                "reason": str(exc)}
    if session is None:
        raise LiveRefused(
            "preflight record bytes parse but carry no scorer to re-derive "
            "the score from")
    score = session.score(session.commit_predictor(candidate))
    candidate_digest = source_digest(json.dumps(
        candidate, sort_keys=True, separators=(",", ":")))
    below = score["overall"] < PREFLIGHT_SCORE_FLOOR
    return {"outcome": "poor-task-result" if below else "constructed",
            "defect": None, "candidate_digest": candidate_digest,
            "score": score,
            "reason": ("valid program scored %.4f against a frozen floor of "
                       "%.1f" % (score["overall"], PREFLIGHT_SCORE_FLOOR))
                      if below else "valid program solved the frozen task"}


def _preflight_decision_without_response(entry: dict,
                                          dispatch) -> dict:
    """The no-response branch. Nothing was said, so nothing can be parsed.

    Whether a send that came back an error is a refusal or a lost send is
    not a fact about a response, because there is no response. It is
    decided by the status the gateway recorded, which is an observation
    this reads rather than re-derives.
    """
    diagnosis = (dispatch or {}).get("diagnosis")
    if isinstance(diagnosis, dict):
        refused = diagnosis.get("route_error") is not None or (
            diagnosis.get("response_status") is not None
            and 400 <= diagnosis["response_status"] < 500
            and diagnosis.get("kind") != "timeout")
        return {"outcome": "route-refusal" if refused else "transport-loss",
                "defect": "no-response-text", "candidate_digest": None,
                "score": None, "reason": diagnosis.get("reason")}
    if (dispatch or {}).get("parse_outcome") == "transport-error":
        return {"outcome": "transport-loss", "defect": "no-response-text",
                "candidate_digest": None, "score": None,
                "reason": "%s: %s" % ((dispatch or {}).get("exception_class"),
                                       (dispatch or {}).get(
                                           "exception_reason"))}
    raise LiveRefused(
        "preflight attempt carries neither a response nor a diagnosis")


def preflight_claims_agree(entry: dict, session=None) -> dict:
    """Every claim an attempt makes, checked against the same ladder.

    Returns the re-derived decision so a caller can report what the bytes
    actually say. Raises `LiveRefused` naming the first claim that does
    not re-derive, because a record that fails here does not attest to
    what it claims and a caller that swallowed the error would be
    re-attesting to it.

    The four fields checked are all of the claims an attempt entry makes
    about its bytes. There is deliberately no fifth check here on the
    defect: an `invalid-program` whose bytes parse does not re-derive as
    `invalid-program` at all, and one whose bytes are over-length
    re-derives the length the reason then has to match, so the `outcome`
    and `reason` comparisons above already carry it. A separate defect
    check would be a second reading of the same bytes, and it is the kind
    of check that disagrees with the data.

    `attempt` is checked too, against the operation identity rather than
    against itself. It is a claim about which dispatch this was, and the
    identity is the observation it has to agree with.
    """
    decided = preflight_decision(entry, session=session)
    for field in ("outcome", "reason", "candidate_digest", "score"):
        if field not in entry:
            raise LiveRefused(
                "preflight attempt makes no %s claim, so nothing re-derives"
                % field)
        if entry[field] != decided[field]:
            raise LiveRefused(
                "preflight %s claim %r does not re-derive as %r"
                % (field, entry[field], decided[field]))
    if "attempt" not in entry:
        raise LiveRefused("preflight attempt makes no attempt claim, so "
                          "nothing re-derives")
    minted = output_operation_attempt(entry.get("operation_id"))
    if entry["attempt"] != minted:
        raise LiveRefused(
            "preflight attempt claim %r does not re-derive as %r, which its "
            "operation identity names" % (entry["attempt"], minted))
    return decided


def verify_preflight_record(record: dict) -> dict:
    """Re-derive the verdict from a run record, with no network.

    This is the check that makes the evidence worth keeping. It reads
    the raw response out of the dispatch, confirms the digest matches the
    bytes, re-runs the shipped parser over those bytes, and recomputes
    the taxonomy value. If the record had been written by hand, or if the
    response had been swapped, the recomputed value and the recorded one
    would part company here.

    A score claim is re-derived here, not read, which is the
    difference between checking a record and believing it. That needs a
    scorer, and the scorer is not a parameter because it is not a choice:
    the frozen preflight task is the only task these records can have
    been measured on, so a caller-supplied scorer would be a way to make a
    record verify against something other than the frozen protocol. The
    scorer is therefore rebuilt from `_preflight_task` at zero model calls
    whenever one is needed.
    """
    from . import frontier as _frontier
    attempt = record.get("attempts")
    if not isinstance(attempt, list) or not attempt:
        raise LiveRefused("preflight record carries no attempt")
    for entry in attempt:
        _frontier.validate_evidence_record(
            entry["dispatch"], kind="gateway-dispatch")
    first = attempt[0]
    recorded = record.get("verdict")
    if not isinstance(recorded, dict):
        raise LiveRefused("preflight record carries no verdict")
    raw_response = first.get("raw_response")
    dispatch = first.get("dispatch")
    if raw_response is not None:
        if not isinstance(raw_response, str) or raw_response != dispatch.get(
                "raw_response"):
            raise LiveRefused(
                "preflight response does not match its own dispatch evidence")
    if raw_response is not None and response_digest(raw_response) != dispatch.get(
            "response_digest"):
        raise LiveRefused("preflight response digest does not match")
    session = _preflight_task()[1]
    # The taxonomy value, the reason prose, the candidate digest and the
    # score are all claims about the bytes. Each is re-derived here from
    # the bytes rather than read, and a claim that does not re-derive is
    # the forgery this check exists to refuse. The old check was a
    # disjunction -- an `invalid-program` was attested by "the bytes do
    # not parse" -- and a record that failed to parse while carrying a
    # reason about 5211 characters satisfied it. One claim per field,
    # each re-derived, leaves no internally consistent forgery that the
    # bytes do not support.
    #
    # Only an attempt that carries a response is re-derived. An attempt
    # that never received one -- a pre-dispatch refusal, a lost send --
    # makes no claim about bytes, so there is nothing to re-derive, and
    # the dispatch digest chain above is what attests it.
    if isinstance(raw_response, str):
        for entry in attempt:
            preflight_claims_agree(entry, session)
    recomputed = preflight_verdict(first)
    if recomputed["outcome"] != recorded.get("outcome"):
        raise LiveRefused(
            "preflight verdict %r does not recompute as %r"
            % (recorded.get("outcome"), recomputed["outcome"]))
    # The verdict is a copy of the attempt's claims plus the dispatch's
    # observations, so it is re-derived whole. A record whose verdict
    # restates a gateway observation its own dispatch contradicts is
    # refused even when every attempt-level claim checks out. This is the
    # gate the shipped preflight never had: it compared `outcome` and
    # `response_digest` and let the other thirteen fields through on
    # trust.
    if not recomputed.get("recomputable"):
        return recomputed
    for field, value in recomputed.items():
        if field not in recorded:
            raise LiveRefused("preflight verdict makes no %s claim" % field)
        if recorded[field] != value:
            raise LiveRefused(
                "preflight verdict %s %r does not re-derive as %r"
                % (field, recorded[field], value))
    return recomputed


def preflight_run(out, gateway, *, dsn: str | None = None,
                  allocation_id: str | None = None) -> dict:
    """Drive one live construction through the shipped path and keep it.

    One dispatch, one Boolean task from the frozen worlds. With a `dsn`
    and an `allocation_id` the dispatch is a durable operation: the send
    is admitted, allocated, dispatched through the broker and left with a
    receipt and an exposure, and the ceiling is read from the store. With
    neither it is the bare send this used to be, which is only honest on
    a path that has no store to write to.

    The run record written to `out` holds the raw prompt, the raw
    response, the response digest, the route fields, the stop
    reason, the usage snapshot and the taxonomy value, which is what
    `verify_preflight_record` needs to reproduce the verdict offline.
    """
    from pathlib import Path
    out = Path(out)
    arm, attempt = "P1", 1
    task, session = _preflight_task()
    history = [] if arm == "P1" else output_permitted_history()
    prompt = render_output_prompt(session.output_model_input(), history,
                                  attempt)
    operation_id = preflight_operation_id(arm, attempt)
    record = {
        "schema": PREFLIGHT_SCHEMA,
        "version": PREFLIGHT_VERSION,
        "run_id": PREFLIGHT_RUN_ID,
        "study_root": OUTPUT_STUDY_ROOT,
        "protocol": OUTPUT_PROTOCOL_ID,
        "route": dict(OUTPUT_ROUTE),
        "task_id": task["task_id"],
        "split": "qual",
        "seed": int(OUTPUT_TASKS["qual"]),
        "queries_spent": len(session.queried),
        "max_output_tokens": OUTPUT_LIMITS["max_output_tokens"],
        "score_floor": PREFLIGHT_SCORE_FLOOR,
        "attempts": [],
    }
    spent = spent_dispatches(dsn, allocation_id) if dsn else 0
    guard = LiveGuard(preflight_dispatch_gateway(
        dsn, gateway, allocation_id=allocation_id) if dsn else gateway,
        pinned_model=OUTPUT_ROUTE["requested_model"],
        ceiling=1 + spent, automatic_retries=0,
        expected_route=dict(OUTPUT_ROUTE),
        spend_reader=(lambda: spent_dispatches(dsn, allocation_id))
        if dsn else None)
    result = _preflight_dispatch(guard, arm=arm, attempt=attempt, dsn=dsn,
                                 allocation_id=allocation_id)
    entry = {"arm": arm, "attempt": attempt,
             "operation_id": result["operation_id"],
             "outcome": result["outcome"], "reason": result["reason"],
             "raw_response": result.get("raw_response"),
             "candidate_digest": result.get("candidate_digest"),
             "score": result.get("score"),
             "dispatch": result.get("dispatch")}
    record["attempts"].append(entry)
    record["verdict"] = preflight_verdict(entry)
    record["guard_status"] = guard.guard_status()
    out.mkdir(parents=True, exist_ok=True)
    (out / "preflight.json").write_text(json.dumps(
        record, sort_keys=True, indent=1) + "\n")
    verify_preflight_record(record)
    return record
