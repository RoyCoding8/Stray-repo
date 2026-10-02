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
