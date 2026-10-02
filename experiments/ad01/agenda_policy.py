"""AD01 agenda policy: versioned decision-policy selection and one consumer.

Experiment entry selects tasks and treatments here; the shared runtime
owns lifecycle semantics. Two policies share the packet/action contract:
a fixed baseline proposer and the model policy. The DecisionConsumer is
the one gate every boundary decision passes: propose, admit, bounded
correction of the same decision, then continuation or stopping. Replacing
or disconnecting the consumer changes both domain runs; a raw proposer
callback alone can never close the gate because admission always runs
inside the consumer.
"""

from __future__ import annotations

BASELINE_POLICY_VERSION = "ad01-policy-baseline-v1"
MODEL_POLICY_VERSION = "ad01-policy-model-v1"
MAX_CORRECTIONS = 2

_TARGET_RELEASE_MARKERS = (
    "outside the admitted curriculum item",
    "outside world",
    "protected-use target",
    "unknown target",
    "no development target",
    "no curriculum item")


def _releases_pin(reason: str) -> bool:
    return any(marker in (reason or "")
               for marker in _TARGET_RELEASE_MARKERS)


def select_tasks(world: int, arm: str, tasks: list | None) -> list:
    if tasks is not None:
        return list(tasks)
    from . import trajectory as _trajectory
    return _trajectory._default_tasks(world, arm)


def scaffolding_proposer(task_id: str, seed_obs: dict):
    def _propose(seen: dict, asked: dict) -> dict:
        from . import trajectory as _trajectory
        proposal = _trajectory.propose_investigation(
            {"observations": [seed_obs]}, {})
        proposal["next_action"] = {
            "kind": "diagnostic",
            "diagnostic": _trajectory._family(task_id),
            "task_id": task_id}
        return proposal
    return _propose


def _correction_rows(dsn: str, aid: str) -> list:
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT content FROM attempt_observations"
            " WHERE attempt_id = %s ORDER BY id",
            (aid,)).fetchall()
        conn.commit()
    return [dict(r["content"] or {}) for r in rows
            if dict(r.get("content") or {}).get("kind") == "correction"]


def _restored_correction(rows: list) -> dict | None:
    for row in reversed(rows):
        failure = row.get("failure")
        if isinstance(failure, dict) and failure:
            return dict(failure)
    return None


def _boundary_calls(dsn: str, cid: str, seq: int) -> int:
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM operations o"
            " WHERE (starts_with(o.id, %s)"
            " OR starts_with(o.id, %s))"
            " AND o.payload->>'effect' = 'model-inference'",
            ("ad01-%s-learner-%d" % (cid, seq),
             "ad01-%s-b%d-" % (cid, seq))).fetchone()
        conn.commit()
    return int(row["n"])


class DecisionConsumer:
    """Shared propose/admit/correct gate for one campaign."""

    def __init__(self, *, proposer=None, admit=None, dsn=None,
                 cid="", charter=None, world=0, arm="I",
                 allocation_id="", study_root="",
                 gateway=None, model="",
                 max_corrections=MAX_CORRECTIONS,
                 policy_version=MODEL_POLICY_VERSION):
        self._proposer = proposer
        self._admit = admit
        self._dsn = dsn
        self._cid = cid
        self._charter = charter or {}
        self._world = world
        self._arm = arm
        self._allocation_id = allocation_id
        self._study_root = study_root
        self._gateway = gateway
        self._model = model
        self._disconnected = None
        self._max_corrections = max_corrections
        self.policy_version = policy_version
        self.decided: list = []

    def _corrections_used(self, aid: str | None) -> int:
        if self._dsn is None or aid is None:
            return 0
        return len(_correction_rows(self._dsn, aid))

    def _journal_correction(self, aid: str, number: int,
                            failure: dict) -> None:
        if self._dsn is None or aid is None:
            return
        from . import trajectory as _trajectory
        from settlement import store
        from settlement.common import Command
        store.acquire_work(
            self._dsn, Command(
                request_id="acquire-%s" % aid,
                payload={"investigation_id": self._cid,
                         "attempt_id": aid,
                         "allocation_id": _trajectory._alloc_id(
                             self._cid),
                         "composition": "ad01-boundary",
                         "owner": self._cid}))
        store.submit_observation(
            self._dsn, Command(
                request_id="correct-%s-%d" % (aid, number),
                payload={"attempt_id": aid,
                         "content": {"kind": "correction",
                                     "number": number,
                                     "failure": failure}}))

    def _refuse(self, reason: str, corrections: int) -> dict:
        return {"status": "refused", "reason": reason,
                "corrections": corrections}

    def _note_refusal(self, corrente: int, failure: dict,
                      aid: str | None) -> dict | None:
        if corrente >= self._max_corrections:
            return self._refuse(
                "admission refused after %d bounded correction(s): %s"
                % (corrente, failure["reason"]), corrente)
        self._journal_correction(aid, corrente + 1, failure)
        return None

    def decide(self, seen: dict, asked: dict, *, boundary,
               experience: dict, aid: str | None = None) -> dict:
        if self._disconnected is not None:
            return self._refuse(
                "decision consumer disconnected: %s"
                % self._disconnected, 0)
        proposer = self._proposer
        if proposer is None and self._gateway is not None \
                and self._dsn is not None:
            from .learner import propose_from_model
            proposer = propose_from_model(
                self._dsn, cid=self._cid, gateway=self._gateway,
                model=self._model, charter=dict(self._charter),
                world=self._world, arm=self._arm,
                allocation_id=self._allocation_id)
        admit = self._admit
        if admit is None:
            from .trajectory import admit_investigation
            admit = admit_investigation
        if proposer is None:
            return self._refuse("decision consumer has no proposer", 0)
        made = self._corrections_used(aid)
        if made >= self._max_corrections:
            return self._refuse(
                "correction budget exhausted (%d/%d corrections used)"
                % (made, self._max_corrections), made)
        prior = None
        required_target = None
        if made and self._dsn is not None and aid is not None:
            prior = _restored_correction(
                _correction_rows(self._dsn, aid))
            if isinstance(prior, dict):
                required_target = prior.get("target")
        resumed = prior is not None
        entry_made = made
        pending_allowance = 0
        if resumed and aid is not None:
            seq = (boundary or {}).get("seq")
            if isinstance(seq, int):
                pending_allowance = _boundary_calls(
                    self._dsn, self._cid, seq)
        while True:
            attempt_seen = dict(seen)
            if prior is not None:
                attempt_seen["prior_failure"] = prior
            if pending_allowance:
                remaining = dict(attempt_seen.get("remaining") or {})
                if isinstance(remaining.get("model_calls"), int):
                    remaining["model_calls"] += pending_allowance
                    attempt_seen["remaining"] = remaining
            attempt_seen["correction_attempt"] = made
            try:
                proposal = proposer(attempt_seen, asked)
            except Exception as exc:
                reason = str(exc) or type(exc).__name__
                if resumed and made == entry_made \
                        and "left no settled response" in reason:
                    made += 1
                    continue
                failure = {"target": required_target,
                           "reason": reason, "attempt": made}
                ended = self._note_refusal(made, failure, aid)
                if ended is not None:
                    return ended
                made += 1
                prior = failure
                continue
            admitted = admit(proposal, experience, asked,
                               boundary)
            if admitted.get("decision") == "admitted":
                investigation = admitted["investigation"]
                target = (investigation.get("next_action") or {}).get(
                    "task_id")
                if required_target is not None \
                        and target != required_target \
                        and not _releases_pin(prior["reason"]):
                    reason = ("correction-changed-target: %r is not the"
                              " refused %r" % (target, required_target))
                    failure = {"target": required_target,
                               "reason": reason, "attempt": made}
                    ended = self._note_refusal(made, failure, aid)
                    if ended is not None:
                        return ended
                    made += 1
                    prior = failure
                    continue
                self.decided.append(target)
                return {"status": "admitted",
                        "investigation": investigation,
                        "corrections": made}
            reason = admitted.get("reason", "refused")
            action = proposal.get("next_action") or {}
            target = action.get("task_id")
            if required_target is None:
                required_target = target
            elif target != required_target:
                if _releases_pin(reason):
                    required_target = target
                else:
                    reason = ("correction-changed-target: %r is not the"
                              " refused %r" % (target, required_target))
            failure = {"target": required_target, "reason": reason,
                       "attempt": made}
            ended = self._note_refusal(made, failure, aid)
            if ended is not None:
                return ended
            made += 1
            prior = failure


def disconnected_consumer(reason: str) -> DecisionConsumer:
    consumer = DecisionConsumer()
    consumer._disconnected = reason
    return consumer


def step_policy_version() -> str:
    from . import policy_step
    return policy_step.POLICY_STEP_VERSION


_STEP_TO_LEGACY = {
    "diagnose": "diagnostic",
    "construct_method": "development",
    "use_method": "use_method",
}


def _step_remaining(seen: dict, steps_left: int) -> dict:
    remaining = dict((seen or {}).get("remaining") or {})
    remaining["policy_steps"] = int(steps_left)
    return remaining


def _step_proposal(action: dict, seen: dict, asked: dict,
                   boundary: dict | None, family: str | None) -> dict:
    inputs = dict(action.get("inputs") or {})
    target = action.get("target")
    kind = action.get("kind")
    question = inputs.get("question") or "policy step %s on %s" % (
        kind, target)
    proposal = {
        "basis_references": list(action.get("evidence_refs") or []),
        "question": question,
        "unknown": inputs.get("unknown") or question,
        "requested_resources": dict(
            action.get("requested_resources") or {}),
        "charter": (asked or {}).get("objective", ""),
    }
    if kind == "diagnose":
        proposal["next_action"] = {
            "kind": "diagnostic",
            "diagnostic": inputs.get("diagnostic", "software"),
            "task_id": target}
    else:
        development = {
            "kind": _STEP_TO_LEGACY[kind],
            "diagnostic": family or inputs.get("diagnostic",
                                               "software"),
            "task_id": target}
        if type(inputs.get("max_queries")) is int \
                and inputs["max_queries"] >= 0:
            development["max_queries"] = inputs["max_queries"]
        if kind == "use_method" and isinstance(
                inputs.get("method_id"), str):
            development["method_id"] = inputs["method_id"]
        proposal["next_action"] = development
    return proposal


def _step_family(target: object) -> str | None:
    from . import trajectory as _trajectory
    try:
        return _trajectory._family(target)
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def _policy_settled_text(dsn: str, operation_id: str) -> str | None:
    from settlement import db
    with db.connect(dsn) as conn:
        row = conn.execute(
            "SELECT content FROM receipts WHERE operation_id = %s"
            " AND receipt_identity = %s AND outcome = 'success'",
            (operation_id, "gw:%s" % operation_id)).fetchone()
        conn.commit()
    if row is None:
        return None
    return str(dict(row[0] or {}).get("text", ""))


def _cached_policy_decision(cached: dict | None,
                           source_digest: str) -> dict | None:
    if cached is None:
        return None
    output = dict(cached["policy_output"] or {})
    results = list(output.get("results") or [])
    accepted = dict(cached["accepted_action"] or {})
    if not results or not accepted:
        return None
    if output.get("source_digest") != source_digest:
        raise ValueError("cached STEP state source digest mismatch")
    if accepted.get("status") == "pending":
        return {"status": "pending", "investigation": accepted,
                "cached": cached}
    if isinstance(accepted.get("next_action"), dict):
        return {"status": "admitted", "investigation": accepted,
                "corrections": len(results) - 1}
    if accepted.get("status") == "refused":
        return {"status": "refused", "reason": accepted.get(
            "reason", "refused"), "corrections": len(results)}
    return None


class StepPolicyConsumer(DecisionConsumer):
    """Trusted gate for versioned STEP policy artifacts.

    The artifact source never runs in this process and never becomes a
    proposer callback. Each STEP call executes in the bounded child
    through method_exec; every returned action passes the same trusted
    admission as any other proposal; model requests become broker
    operations whose settled responses return as next-step
    observations. Admission, evaluation and grants stay driver-owned.
    """

    def __init__(self, *, policy: dict, dsn=None, cid="",
                 charter=None, world=0, arm="I", allocation_id="",
                 study_root="", gateway=None, model="",
                 max_policy_steps=6, timeout_ms=None,
                 cpu_seconds=None, max_output_bytes=None,
                 policy_version=None):
        from . import policy_step
        super().__init__(
            proposer=None, admit=None, dsn=dsn, cid=cid,
            charter=charter, world=world, arm=arm,
            allocation_id=allocation_id, study_root=study_root,
            gateway=gateway, model=model,
            policy_version=policy_version
            or policy_step.POLICY_STEP_VERSION)
        self._policy = policy_step.verify_policy_record(policy)
        self._policy_source = policy["policy_source"]
        self._max_policy_steps = max_policy_steps
        self._timeout_ms = timeout_ms or policy_step.STEP_TIMEOUT_MS
        self._cpu_seconds = cpu_seconds or policy_step.STEP_CPU_SECONDS
        self._max_output_bytes = max_output_bytes \
            or policy_step.STEP_MAX_OUTPUT_BYTES

    def _model_request(self, action: dict, remaining: dict,
                       step_index: int) -> tuple:
        from settlement import broker
        from settlement.common import ResultCode
        from . import policy_step
        from . import trajectory as _trajectory
        inputs = dict(action.get("inputs") or {})
        prompt = inputs.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.strip():
            return None, {"status": "error",
                          "reason": "model request needs a prompt"}
        if len(prompt.encode()) > policy_step.MODEL_PROMPT_LIMIT_CHARS:
            return None, {"status": "error",
                          "reason": "model prompt exceeds %d chars"
                          % policy_step.MODEL_PROMPT_LIMIT_CHARS}
        operation_id = "ad01-%s-policy-s%d-model-k%d" % (
            self._cid, self._seq, step_index)
        settled = (_policy_settled_text(self._dsn, operation_id)
                   if self._dsn is not None else None)
        existing = (broker.read_operation(self._dsn, operation_id) is not None
                    if self._dsn is not None else False)
        if settled is None and not existing and int(
                remaining.get("model_calls", 0)) <= 0:
            return None, {"status": "refused",
                          "reason": "model call cap reached",
                          "operation_id": operation_id}
        if self._dsn is None or (settled is None and self._gateway is None):
            return None, {"status": "refused",
                          "reason": "policy requested model reasoning"
                          " without a gateway and store"}
        tokens = inputs.get("max_output_tokens", 256)
        if type(tokens) is not int or tokens <= 0 or tokens > 2048:
            return None, {"status": "error",
                          "reason": "max_output_tokens must be 1..2048"}
        if settled is None:
            ensured = broker.ensure_operation(
                self._dsn, operation_id=operation_id,
                effect=broker.MODEL_INFERENCE,
                payload={"model": self._model or "policy-request",
                         "messages": [{"role": "user",
                                       "content": prompt}],
                         "max_output_tokens": tokens,
                         "deadline_ms": 300_000,
                         "reasoning_effort":
                         _trajectory.reasoning_effort()},
                allocation_id=self._allocation_id
                or _trajectory._alloc_id(self._cid))
            if ensured.code not in (ResultCode.APPLIED,
                                    ResultCode.ALREADY_APPLIED):
                return None, {"status": "refused",
                              "reason": "model call not admitted: %s"
                              % ensured.detail,
                              "operation_id": operation_id}
            broker.dispatch_operation(
                self._dsn, operation_id, launchers={},
                gateway=self._gateway)
            settled = _policy_settled_text(self._dsn, operation_id)
            if settled is None:
                return None, {"status": "refused",
                              "reason": "model call %s left no settled"
                              " response" % operation_id,
                              "operation_id": operation_id}
        import hashlib
        try:
            body = settled if isinstance(settled, str) else str(settled)
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        except Exception:
            body = ""
            digest = hashlib.sha256(b"").hexdigest()
        shown = body[:policy_step.MODEL_RESPONSE_VIEW_CHARS]
        return {"operation_id": operation_id, "digest": digest,
                "text": shown,
                "truncated": len(body) > len(shown)}, None

    def decide(self, seen: dict, asked: dict, *, boundary,
               experience: dict, aid: str | None = None) -> dict:
        from . import policy_step
        from . import trajectory as _trajectory
        from . import worlds as _worlds
        if self._disconnected is not None:
            return self._refuse(
                "decision consumer disconnected: %s"
                % self._disconnected, 0)
        seq = (boundary or {}).get("seq", 0)
        self._seq = int(seq) if isinstance(seq, int) else 0
        observations = list((seen or {}).get("observations") or [])
        if not observations:
            return self._refuse("policy step needs a seed observation",
                                0)
        task_id = observations[-1].get("task_id")
        try:
            task = _worlds.load_task(_worlds.FROZEN_DIR, task_id)
        except (KeyError, TypeError):
            return self._refuse("unknown policy task %r" % (task_id,),
                                0)
        eligible = sorted({m.get("capability_id")
                           for m in (seen or {}).get("retained") or []
                           if isinstance(m, dict)
                           and m.get("capability_id")})
        source_digest = self._policy["source_digest"]
        cached = policy_step.load_policy_state(
            self._dsn, self._cid, self._seq) \
            if self._dsn is not None else None
        resumed = _cached_policy_decision(cached, source_digest)
        if resumed is not None and resumed["status"] != "pending":
            return resumed
        open_questions: list = []
        last_result = None
        state: dict = policy_step.load_prior_final_state(
            self._dsn, self._cid, self._seq)
        views: list = []
        results: list = []
        transitions: list = []
        resume_action = None
        start_index = 0
        if resumed is not None:
            cached = resumed["cached"]
            payload = dict(cached["policy_input"] or {})
            views = list(payload.get("views") or [])
            results = list(dict(cached["policy_output"] or {}).get(
                "results", []) or [])
            transition = dict(cached["state_transition"] or {})
            transitions = list(transition.get("transitions") or [])
            state = dict(transition.get("final_state") or {})
            resume_action = dict(resumed["investigation"]["next_action"])
            start_index = len(results) - 1
        packet_allowance = int(
            (dict((seen or {}).get("remaining") or {}).get(
                "model_calls", 6)))
        entry_model = policy_step.durable_model_calls(
            self._dsn, self._cid, self._seq)
        for index in range(start_index, self._max_policy_steps):
            durable_now = policy_step.durable_model_calls(
                self._dsn, self._cid, self._seq)
            spent = durable_now - entry_model
            model_remaining = min(packet_allowance - spent,
                                  6 - durable_now)
            steps_remaining = self._max_policy_steps - index
            remaining = _step_remaining(seen, steps_remaining)
            remaining["model_calls"] = max(int(model_remaining), 0)
            operation_id = "ad01-%s-policy-s%d-k%d" % (
                self._cid, self._seq, index)
            if resume_action is None:
                view = policy_step.materialize_view(
                    task=task, observations=observations,
                    open_questions=open_questions, last_result=last_result,
                    eligible_methods=eligible, remaining=remaining)
                try:
                    stepped = policy_step.run_policy_step(
                        {"artifact": self._policy,
                         "policy_source": self._policy_source},
                        view, state, timeout_ms=self._timeout_ms,
                        cpu_seconds=self._cpu_seconds,
                        max_output_bytes=self._max_output_bytes,
                        dsn=self._dsn,
                        allocation_id=self._allocation_id
                        or _trajectory._alloc_id(self._cid),
                        operation_id=operation_id
                        if self._dsn is not None else None)
                except Exception as exc:
                    views.append(view)
                    policy_step.persist_step_transition(
                        self._dsn, self._cid, self._seq, views=views,
                        results=results, transitions=transitions,
                        investigation={"status": "refused",
                                       "reason": "policy step failed: %s"
                                       % exc},
                        source_digest=source_digest,
                        status="incorporated")
                    return self._refuse("policy step failed: %s" % exc,
                                        index)
                action = stepped["action"]
                previous = dict(state)
                state = dict(stepped["state"])
                views.append(view)
                results.append({"action": action, "state": state,
                                "operation_id": operation_id})
                transitions.append({"previous": previous, "next": state})
            else:
                action = resume_action
                resume_action = None
            kind = action["kind"]
            if kind == "request_model":
                policy_step.persist_step_transition(
                    self._dsn, self._cid, self._seq, views=views,
                    results=results, transitions=transitions,
                    investigation={"status": "pending",
                                   "next_action": action,
                                   "operation_id":
                                   "ad01-%s-policy-s%d-model-k%d" % (
                                       self._cid, self._seq, index)},
                    source_digest=source_digest)
                response, failure = self._model_request(
                    action, remaining, index)
                if failure is not None:
                    last_result = dict(failure)
                    last_result.setdefault(
                        "operation_id",
                        "ad01-%s-policy-s%d-model-k%d" % (
                            self._cid, self._seq, index))
                    open_questions.append(last_result.get(
                        "reason", "refused"))
                    continue
                last_result = {"kind": "model_response",
                               "digest": response["digest"],
                               "text": response["text"],
                               "truncated": response["truncated"],
                               "operation_id": response["operation_id"]}
                continue
            if kind in _STEP_TO_LEGACY:
                proposal = _step_proposal(
                    action, seen, asked, boundary,
                    _step_family(action.get("target")))
                admitted = _trajectory.admit_investigation(
                    proposal, seen, asked, boundary)
                if admitted.get("decision") != "admitted":
                    last_result = {"status": "refused",
                                   "reason": admitted.get(
                                       "reason", "refused")}
                    open_questions.append(last_result["reason"])
                    continue
                investigation = admitted["investigation"]
                policy_step.persist_step_transition(
                    self._dsn, self._cid, self._seq, views=views,
                    results=results, transitions=transitions,
                    investigation=investigation,
                    source_digest=stepped["source_digest"])
                self.decided.append(
                    (investigation.get("next_action") or {}).get(
                        "task_id"))
                return {"status": "admitted",
                        "investigation": investigation,
                        "corrections": index}
            if kind == "propose_revision":
                inputs = dict(action.get("inputs") or {})
                investigation = {
                    "basis_references": [
                        r for r in action.get("evidence_refs") or []
                        if isinstance(r, str)],
                    "question": inputs.get("question")
                    or "policy proposed revision",
                    "revision_proposal": {
                        "scope": inputs.get("scope", {}),
                        "parent_digest":
                        self._policy["source_digest"],
                        "motivation": inputs.get("motivation", ""),
                    },
                    "next_action": {
                        "kind": "policy_revision",
                        "task_id": action.get("target"),
                        "reason": inputs.get(
                            "reason", "policy proposed revision")},
                }
                policy_step.persist_step_transition(
                    self._dsn, self._cid, self._seq, views=views,
                    results=results, transitions=transitions,
                    investigation=investigation,
                    source_digest=stepped["source_digest"])
                return {"status": "admitted",
                        "investigation": investigation,
                        "corrections": index}
            investigation = {
                "basis_references": [],
                "question": dict(action.get("inputs") or {}).get(
                    "reason", "policy stop"),
                "next_action": {"kind": "stop",
                                "reason": dict(
                                    action.get("inputs") or {}).get(
                                    "reason", "policy stop")},
            }
            policy_step.persist_step_transition(
                self._dsn, self._cid, self._seq, views=views,
                results=results, transitions=transitions,
                investigation=investigation,
                source_digest=stepped["source_digest"])
            return {"status": "admitted",
                    "investigation": investigation,
                    "corrections": index}
        policy_step.persist_step_transition(
            self._dsn, self._cid, self._seq, views=views,
            results=results, transitions=transitions,
            investigation={"status": "refused",
                           "reason": "policy step budget exhausted"
                           " (%d steps)" % self._max_policy_steps},
            source_digest=source_digest,
            status="incorporated")
        return self._refuse("policy step budget exhausted (%d steps)"
                            % self._max_policy_steps,
                            self._max_policy_steps)


def step_policy_consumer(policy: dict, **kwargs) -> StepPolicyConsumer:
    return StepPolicyConsumer(policy=policy, **kwargs)
