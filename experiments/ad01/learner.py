"""Model-backed AD01 learner at the gateway seam.

The learner receives the accumulated packet (charter, visible
opportunities, prior observations with failures, retained members,
remaining budgets) and returns one section-3 action through broker
model inference. Recording doubles serve the same seam in order.

The treatment constructors below build the E2 experience contrasts on
that same seam. They take the same task, the same budget and the same
interface and vary only the experience an arm is given, so an arm is a
dict in the shape `construct.construct_policy` already accepts and no
second construction path exists.
"""

from __future__ import annotations

import json
from typing import Any

from . import packet as _packet

TREATMENT_VERSION = "ad01-experience-treatment-v1"


class LearnerRefused(Exception):
    pass


class TreatmentRefused(LearnerRefused):
    pass


LEARNER_INSTRUCTION = (
    "Reply with ONLY one JSON object and no other text: no prose, "
    "no explanation, no code fences. next_action.kind must always be "
    "present: diagnostic, development, or stop. next_action.diagnostic "
    "must be exactly software or graph. basis_references must be "
    "observation_id strings copied from the observations list exactly, "
    "character for character, never truncated, abbreviated, invented, or "
    "section names like charter or remaining. requested_resources must "
    "be an object mapping a resource name to a nonnegative integer "
    "amount, e.g. {\"queries\": 3}. When curriculum_item is not null, "
    "next_action.task_id must equal curriculum_item. When "
    "curriculum_item is null, next_action.task_id must be one of "
    "visible_opportunities.")


def _extract_json(text: str) -> dict | None:
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        lines = lines[1:] if len(lines) > 1 else []
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


class RecordingGatewayAdapter:
    label = "AD01-RECORDING-GATEWAY"

    def __init__(self, scripts: list):
        from settlement.gateway import Usage
        self._scripts = [dict(s) for s in scripts]
        self._fallback_usage = Usage(input_tokens=5, output_tokens=5)
        self.calls: list = []

    def check_discovery(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        from settlement.gateway import GatewayStatus
        return GatewayStatus.AUTHENTICATED

    def _script(self):
        if len(self.calls) <= len(self._scripts):
            return self._scripts[len(self.calls) - 1]
        return self._scripts[-1]

    def infer(self, request):
        from settlement.gateway import ModelResponse, Usage
        self.calls.append(request)
        script = self._script()
        usage = script.get("usage", None)
        if usage is None:
            usage = self._fallback_usage
        elif isinstance(usage, dict):
            usage = Usage(**usage)
        return ModelResponse(request.operation_id, script.get("text", ""),
                             dict(script.get("meta", {})), usage, "stop")

    def cancel(self, operation_id):
        return False


def learner_request(charter: dict, visible: list, experience: dict,
                    retained: list, remaining: dict,
                    curriculum: str | None,
                    prior_failure: dict | None = None) -> dict:
    packet = _packet.decision_packet(
        charter=charter, visible=visible, experience=experience,
        retained=retained, remaining=remaining, curriculum=curriculum,
        boundary=None)
    if prior_failure is not None:
        packet["prior_failure"] = _packet._strip_value(
            dict(prior_failure))
    return packet


def visible_prompt(charter: dict, visible: list, experience: dict,
                   retained: list, remaining: dict,
                   curriculum: str | None,
                   prior_failure: dict | None = None) -> str:
    from . import packet as _pkt
    cleaned_obs = [o for o in (experience or {}).get("observations", [])
                   if not _pkt._is_sealed_observation(o)]
    cleaned_exp = dict(experience or {}, observations=cleaned_obs)
    packet = _pkt.decision_packet(
        charter=charter, visible=visible, experience=cleaned_exp,
        retained=retained, remaining=remaining, curriculum=curriculum,
        boundary=None)
    prompt = LEARNER_INSTRUCTION + "\n" + json.dumps(packet, sort_keys=True)
    if prior_failure is not None:
        packet["prior_failure"] = _pkt._strip_value(dict(prior_failure))
        # The packet key is the machine-readable form and a reader of the
        # JSON can find it. A model reading the same text cannot: nothing in
        # the prose says this value is the refusal that produced the retry,
        # so it reads as one more field of the experience. The marker existed
        # before the packet carried the value and was dropped with the move.
        prompt = (LEARNER_INSTRUCTION + "\nPRIOR FAILURE (correct it): "
                  + json.dumps(prior_failure, sort_keys=True)
                  + "\n" + json.dumps(packet, sort_keys=True))
    return prompt


def _read_conn(dsn: str):
    from psycopg.rows import dict_row
    from settlement import db
    return db.connect(dsn, row_factory=dict_row)


def record_exposure(dsn: str, batch_id: str, exposed_to: str) -> dict:
    if not batch_id or not exposed_to:
        raise ValueError("exposure needs batch and consumer")
    with _read_conn(dsn) as conn:
        conn.execute(
            "INSERT INTO s09_assessment_exposure"
            " (batch_id, exposed_to, retired_at)"
            " VALUES (%s, %s, now())"
            " ON CONFLICT (batch_id, exposed_to)"
            " DO UPDATE SET retired_at = COALESCE("
            " s09_assessment_exposure.retired_at, now())",
            (batch_id, exposed_to))
        conn.commit()
    return {"batch_id": batch_id, "exposed_to": exposed_to,
            "retired": True}


def is_retired(dsn: str, batch_id: str) -> bool:
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT 1 FROM s09_assessment_exposure"
            " WHERE batch_id = %s AND retired_at IS NOT NULL",
            (batch_id,)).fetchone()
        conn.commit()
        return row is not None


def require_unretired(dsn: str, batch_id: str, consumer: str) -> None:
    if is_retired(dsn, batch_id):
        raise LearnerRefused(
            "assessment batch %r retired for descendant %r"
            % (batch_id, consumer))


def validate_proposal(proposal: dict) -> dict:
    if not isinstance(proposal, dict):
        raise LearnerRefused("learner response is not an object")
    action = proposal.get("next_action")
    if not isinstance(action, dict) or action.get("kind") not in (
            "diagnostic", "development", "use_method", "stop"):
        raise LearnerRefused("unknown action kind")
    if action["kind"] == "use_method" and not isinstance(action.get("method_id"), str):
        raise LearnerRefused("use_method needs a method_id")
    if action["kind"] != "stop" and not isinstance(action.get("task_id"), str):
        raise LearnerRefused("action needs a task_id")
    if "max_queries" in action and (
            type(action["max_queries"]) is not int or action["max_queries"] < 0):
        raise LearnerRefused("max_queries must be a nonnegative integer")
    if "diagnostic" in action and action["diagnostic"] not in (
            "software", "graph", "diagnostic_resolves"):
        raise LearnerRefused("unknown diagnostic")
    resources = proposal.get("requested_resources", {})
    if not isinstance(resources, dict) or any(
            not isinstance(k, str) or type(v) is not int or v < 0
            for k, v in resources.items()):
        raise LearnerRefused("requested_resources must contain nonnegative integers")
    refs = proposal.get("basis_references", [])
    if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs):
        raise LearnerRefused("basis_references must be a list of strings")
    return proposal


def _learner_op_id(cid: str, seq: int, attempt: int = 0) -> str:
    base = "ad01-%s-learner-%d" % (cid, seq)
    return base if not attempt else "%s-c%d" % (base, attempt)


def _settled_text(dsn: str, operation_id: str) -> str | None:
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


def model_propose(dsn: str, *, cid: str, seq: int, gateway: Any,
                  model: str, charter: dict, visible: list,
                  experience: dict, retained: list, remaining: dict,
                  curriculum: str | None, allocation_id: str,
                  prior_failure: dict | None = None,
                  attempt: int = 0) -> dict:
    from settlement import broker
    from settlement.common import ResultCode
    from .trajectory import reasoning_effort
    operation_id = _learner_op_id(cid, seq, attempt)
    settled = _settled_text(dsn, operation_id)
    if settled is None:
        prompt = visible_prompt(
            charter, visible, experience, retained, remaining,
            curriculum, prior_failure)
        ensured = broker.ensure_operation(
            dsn, operation_id=operation_id,
            effect=broker.MODEL_INFERENCE,
            payload={"model": model,
                     "messages": [{"role": "user", "content": prompt}],
                     "max_output_tokens": 2048, "deadline_ms": 300_000,
                     "reasoning_effort": reasoning_effort()},
            allocation_id=allocation_id)
        if ensured.code not in (ResultCode.APPLIED,
                                ResultCode.ALREADY_APPLIED):
            raise LearnerRefused("learner call not admitted: %s"
                                 % ensured.detail)
        broker.dispatch_operation(dsn, operation_id, launchers={},
                                  gateway=gateway)
        settled = _settled_text(dsn, operation_id)
        if settled is None:
            raise LearnerRefused(
                "learner call %s left no settled response" % operation_id)
    proposal = _extract_json(settled)
    if proposal is None:
        raise LearnerRefused("learner response is not JSON")
    return validate_proposal(proposal)


def visible_opportunities(world: int) -> list:
    from . import worlds
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    return sorted(
        t for d in membership[str(world)].get("dev", {}).values()
        for t in d)


def curriculum_item(world: int, arm: str, seq: int) -> str | None:
    if arm != "R":
        return None
    from . import rotation
    schedule = rotation.r_schedule(world)
    if seq >= len(schedule):
        return None
    return schedule[seq]["task_id"]


def _budget(budget: dict | None) -> dict:
    """The construction allowance both arms of a contrast share."""
    if budget is None:
        budget = {}
    if not isinstance(budget, dict):
        raise TreatmentRefused("construction allowance must be an object")
    return dict(budget)


def _arm_experience(task: dict, observations: list, visible: list,
                    retained: list, budget: dict) -> dict:
    """One arm, in the dict shape `construct.construct_policy` accepts."""
    from . import policy_step
    return {
        "boundary": {"seq": 0},
        "task": dict(task or {}),
        "observations": list(observations or []),
        "retained": list(retained or []),
        "visible": sorted(visible or []),
        "remaining": dict(budget or {}),
        "view": policy_step.materialize_view(
            task=dict(task or {}), observations=list(observations or []),
            open_questions=[], last_result=None, eligible_methods=[],
            remaining=dict(budget or {})),
    }


def relevant_experience(task: dict, source_task_ids: list,
                        visible: list, budget: dict | None = None,
                        retained: list | None = None) -> dict:
    """Development experience about the same family as the target task.

    The observations are the seed observations a real trajectory would have
    accumulated, so the arm carries the same shape the live path carries.
    """
    return _arm_experience(task, seed_observations(source_task_ids),
                           visible, retained or [], _budget(budget))


def no_experience_experience(task: dict, source_task_ids: list,
                             visible: list, budget: dict | None = None,
                             retained: list | None = None) -> dict:
    """The same interface, the same allowance, and no experience at all.

    `source_task_ids` is accepted and discarded so a caller cannot forget
    the arms share a task pool: the no-experience arm is defined by having
    the same opportunity to draw experience and not drawing it.
    """
    return _arm_experience(task, [], visible, retained or [], _budget(budget))


def seed_observations(task_ids: list) -> list:
    """The seed observation each task starts with, in the live shape.

    A seed observation is what a trajectory records before anything has
    been measured, so it carries no detail. An arm built only from seeds
    is the honest starting experience, and the relevance contrast sizes
    its control against whatever this produces.
    """
    return [{"observation_id": "obs-%s-seed" % task_id,
             "task_id": task_id,
             "capability_id": "ad01-%s" % _capability_field(task_id),
             "verdict": "unmeasured"}
            for task_id in sorted(task_ids or [])]


def _capability_field(task_id: str) -> str:
    """The capability label a task id carries, without a positional guess.

    This used to be `task_id.split("-")[3]`, which is the fifth field of
    the frozen `ad01-w1-dev-sw-00` shape. The instruments' own ids are
    `rule-<split>-<digest>` and `order-<split>-<digest>` - three fields -
    so a keyed id made the index raise `IndexError` for both, and
    `relevant_experience` therefore failed for every E2 relevance and
    transfer caller.

    A positional index is the wrong shape here anyway: it silently reads
    the wrong field when the id has more fields than expected, which is
    how `substituted_observations` kept working and returned a plausible
    but wrong `ad01-dev` for every task. Splitting off the instrument
    prefix and keeping the remainder says what the label is meant to be
    without caring how many segments follow it.
    """
    parts = str(task_id).split("-")
    if len(parts) > 3:
        return "-".join(parts[3:])
    return parts[-1]


def _growth_pool(filler_task_ids: list) -> list:
    """Filler records about tasks of another family, ready to copy.

    Ordered by id so the same frozen pool always produces the same control.
    """
    from . import worlds
    pool = []
    for task_id in sorted(filler_task_ids or []):
        try:
            task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        except (KeyError, OSError, ValueError):
            continue
        record = dict(seed_observations([task_id])[0])
        record["detail"] = _detail_for(task)
        pool.append(record)
    return pool


def _record_size(observation: dict) -> int:
    return _observation_chars([observation])


def _detail_for(task: dict) -> str:
    """A same-shaped detail drawn only from the task's public fields."""
    public = _packet.public_task_view(task)
    return "template %s seed %s" % (public.get("template", ""),
                                    public.get("seed", ""))


def _observation_chars(observations: list) -> int:
    return len(_packet.canonical(list(observations or [])))


def equal_length_experience_pair(left: dict, right: dict,
                                 enforce: bool = True) -> bool:
    """Whether two experience arms carry the same number of characters.

    The canonical serialisation is the measure, not the prompt, so the
    comparison does not move when the surrounding construction path gains a
    line. It is the same string the rendered prompt embeds.
    """
    left_chars = _observation_chars((left or {}).get("observations"))
    right_chars = _observation_chars((right or {}).get("observations"))
    if not enforce:
        return left_chars == right_chars
    if left_chars != right_chars:
        raise TreatmentRefused(
            "experience arms must carry equal character length: %d against"
            " %d. An unequal control confounds semantic relevance with"
            " context volume." % (left_chars, right_chars))
    return True


# A record needs four fields before `packet._strip_value` will keep it, so
# an experience record has a floor of about this many characters. A control
# cannot be shorter than one of its own records, and a target below this
# has no equal-length partner at all.
_RECORD_FLOOR = 150


def _set_observations(arm: dict, observations: list) -> dict:
    """The same arm with a different experience, or a refusal.

    The length check runs here rather than in the caller, so every route
    to a constructed arm passes through it and a caller cannot build an
    unequal pair by reaching past the contrast constructor.
    """
    observations = list(observations or [])
    for observation in observations:
        if not isinstance(observation, dict) \
                or not str(observation.get("observation_id", "")) \
                or "task_id" not in observation \
                or "verdict" not in observation:
            raise TreatmentRefused(
                "an experience record needs observation_id, task_id and"
                " verdict: %r" % (observation,))
    rebuilt = _arm_experience(
        (arm or {}).get("task", {}), observations,
        (arm or {}).get("visible", []),
        (arm or {}).get("retained", []),
        (arm or {}).get("remaining", {}))
    equal_length_experience_pair(arm, rebuilt)
    return rebuilt


def _resized(records: list, target: int) -> list | None:
    """`records` with their details set so the total is exactly `target`.

    The budget is measured, not modelled. A record spends characters on
    its `detail` key and quotes before any of the string's own content
    counts, and the separators between records are a further cost that a
    per-record sum gets wrong. So the candidate is built at width zero,
    measured, and corrected by the shortfall: one measurement of what the
    serialiser actually produces, rather than an estimate of what it
    should produce. A width that overshoots returns a refusal instead.
    """
    bare = [{key: value for key, value in record.items() if key != "detail"}
            for record in records]
    if target < _observation_chars(bare + [{"detail": ""}]):
        return None
    width = target - _observation_chars(
        [dict(record, detail="") for record in bare])
    candidate = [dict(record, detail=("" if index < len(bare) - 1
                                      else "x" * width))
                 for index, record in enumerate(bare)]
    if _observation_chars(candidate) != target:
        return None
    return candidate


def _marked(record: dict, index: int) -> dict:
    """A pool record whose id says it is a control record.

    The original observation id is replaced rather than prefixed. A
    prefix would spend characters on every control record, and a control
    built from several records could then be longer than any relevant arm
    it is meant to match. The relevant arm's identifiers are the ones a
    model could mistake for real evidence, so those are the ones that get
    overwritten, and `basis_references` still resolves to a real id in
    neither arm.
    """
    return {**record, "observation_id": "ctrl-filler-%d" % index}


def irrelevant_control_for(relevant: dict,
                           filler_task_ids: list | None = None) -> dict:
    """A same-length arm whose experience is about a different family.

    Two things are held constant against the relevant arm: the number of
    characters and the number of records. Character length alone is not
    enough, because a control that padded its way to the right size would
    carry a different volume of material as well, and a contrast that
    varies relevance, volume and record count at once is a contrast nobody
    can read. Where the pool cannot reach the target the constructor
    refuses rather than shipping the nearest size it can build.
    """
    relevant_observations = list((relevant or {}).get("observations") or [])
    target = _observation_chars(relevant_observations)
    count = len(relevant_observations)
    if not count:
        return _set_observations(relevant, [])
    if target < _RECORD_FLOOR:
        raise TreatmentRefused(
            "the relevant arm's %d characters cannot hold an experience"
            " record, so no control of equal length exists" % target)
    pool = _growth_pool(filler_task_ids or [])
    if not pool:
        raise TreatmentRefused(
            "no filler pool: an irrelevant control needs %d tasks of a"
            " different family to draw records from, and %d characters"
            " cannot be filled from nothing" % (count, target))
    if len(pool) < count:
        raise TreatmentRefused(
            "the irrelevant pool holds %d records and the relevant arm"
            " holds %d, so a control of the same size cannot be built"
            % (len(pool), count))
    order = sorted(range(len(pool)), key=lambda i: _record_size(pool[i]))
    # Record count is tried first, because an arm that carries one
    # control record against the relevant arm's two varies volume and
    # count as well as relevance, and a contrast that varies three things
    # is a contrast nobody can read. A different count is only a fallback
    # for a pool too small to match, and the count that was used rides
    # out on the pair so the reader can see which of the two it was.
    sizes = [count] + [size for size in range(1, len(order) + 1)
                       if size != count]
    for size in sizes:
        chosen = [_marked(pool[i], index)
                  for index, i in enumerate(order[:size])]
        fitted = _resized(chosen, target)
        if fitted is not None:
            return _set_observations(relevant, fitted)
    raise TreatmentRefused(
        "no filler reaches the relevant arm's %d characters: the"
        " irrelevant pool offers %d records and the smallest one's"
        " identifiers alone serialise to %d, so no control of that exact"
        " length exists"
        % (target, len(pool),
           _observation_chars([_marked(pool[order[0]], 0)])))




def matched_experience_arms(task: dict, source_task_ids: list,
                           visible: list, *, task_ids: list,
                           budget: dict | None = None,
                           retained: list | None = None) -> dict:
    """The relevance contrast: same length, different semantic relevance."""
    relevant = relevant_experience(task, source_task_ids, visible, budget,
                                   retained)
    control = irrelevant_control_for(relevant, task_ids)
    return {
        "condition": "relevant-versus-shuffled",
        "differs_in": "semantic-relevance-only",
        "relevant": relevant,
        "irrelevant": control,
        "relevant_chars": _observation_chars(relevant["observations"]),
        "irrelevant_chars": _observation_chars(control["observations"]),
    }


def held_out_canary(task: dict | None) -> str:
    """A held-out value of this task, usable as a leak needle.

    A canary that is not in the task proves nothing: a marker no arm
    could contain cannot show that an arm is clean. This returns a value
    the private side really holds, so finding it in an arm is a real
    finding and an empty result is a real clearance.
    """
    values = _packet.held_out_values(task)
    return values[0] if values else ""


def canary_task(task: dict, marker: str | None = None) -> dict:
    """A copy of `task` with a findable answer planted in its private side.

    This is the needle the leak guard is proved against. A guard that has
    never been shown a canary has been shown nothing, and a guard that
    cannot see the canary is not looking in the right place. An explicit
    marker wins over the derived one, and a task whose only private
    string is already public gets a needle derived from its own content,
    because a task that offers no needle is a task whose cleanliness was
    never demonstrated.
    """
    return _packet.with_held_out_canary(
        task, marker if marker else held_out_canary(task)
        or _packet.content_digest(dict(task or {}))[:16])


def require_no_held_out_answers(arms: dict, task: dict) -> dict:
    """Refuse any arm that quotes this task's held-out answer.

    Both arms are checked, not just the control. A leak in the benchmark
    arm is the same defect as a leak in the control: the contrast is
    supposed to separate arms that reason from arms that do not know, and
    an arm that already knows is a third condition nobody declared. The
    refusal names the value so a reader can see which needle fired.
    """
    for name, arm in (arms or {}).items():
        for rendered in _arm_surfaces(arm):
            leaked = _packet.leaked_answers(rendered, task)
            if leaked:
                raise TreatmentRefused(
                    "arm %r carries the held-out answer %r, so the arms"
                    " differ in what they know rather than in what they"
                    " were given" % (name, leaked[0]))
    return dict(arms or {})


def _arm_surfaces(arm: dict) -> list:
    """Every string a model could read off an arm.

    The arm's own `task` field is deliberately absent: it is the full
    task, held-out fields and all, so that a construction call can reach
    its own oracle. A leak check that read it would fire on every arm
    including one that carries no experience at all, and a gate that
    refuses everything is a gate nobody trusts. What the model reads is
    the view and the observation list, and those are what is checked.
    """
    if not isinstance(arm, dict):
        return [_packet.canonical(arm)]
    return [_packet.canonical((arm or {}).get("view") or {}),
            _packet.canonical(list((arm or {}).get("observations") or [])),
            _packet.canonical((arm or {}).get("retained") or [])]


_NON_IDENTITY_FREEZE_FIELDS = ("freeze_digest", "frozen_at")


def treatment_freeze(*, study_id: str, pairs: dict, uses: int,
                     frozen_at: str = "") -> dict:
    """The frozen treatment definitions, addressed by their own content.

    A digest over the whole definition means a treatment cannot be edited
    after outcomes are seen without the digest moving. `frozen_at` is
    excluded for the reason the campaign's own verifier already learned: a
    wall-clock field inside the identity makes an otherwise identical
    freeze recompute differently every time, and a freeze that cannot be
    reproduced is not one.
    """
    if not isinstance(study_id, str) or not study_id:
        raise TreatmentRefused("a freeze needs a study identity")
    if type(uses) is not int or uses <= 0:
        raise TreatmentRefused(
            "a freeze needs a positive declared number of uses, not %r"
            % (uses,))
    if not isinstance(pairs, dict) or not pairs:
        raise TreatmentRefused("a freeze needs at least one contrast")
    freeze = {"version": TREATMENT_VERSION, "study_id": study_id,
              "pairs": pairs, "uses": uses, "frozen_at": frozen_at}
    freeze["freeze_digest"] = _packet.content_digest(
        {key: value for key, value in freeze.items()
         if key not in _NON_IDENTITY_FREEZE_FIELDS})
    return freeze


def verify_treatment_freeze(freeze: dict) -> dict:
    """The freeze, if its digest still recomputes over its own content."""
    if not isinstance(freeze, dict) or "freeze_digest" not in freeze:
        raise TreatmentRefused("no freeze digest to verify against")
    body = {key: value for key, value in freeze.items()
            if key not in _NON_IDENTITY_FREEZE_FIELDS}
    recomputed = _packet.content_digest(body)
    if recomputed != freeze["freeze_digest"]:
        raise TreatmentRefused(
            "freeze_digest %s recomputes to %s: the treatment definition"
            " was altered after the freeze"
            % (freeze["freeze_digest"], recomputed))
    return freeze


def acquisition_cost_arms(task: dict, budget: dict, *,
                           uses: int) -> dict:
    """A retained arm and a cold-reacquisition arm over `uses` uses.

    Both arms spend the same on use; the only difference is whether the
    construction is paid again. The dispatches are kept as counts rather
    than folded into a total here, so the two costs stay separable all
    the way to the report instead of meeting once and never being split
    again.
    """
    from . import s09_route_cost
    allowance = _budget(budget)
    construction = allowance.get("model_calls")
    if type(construction) is not int or construction <= 0:
        raise TreatmentRefused(
            "a cold reacquisition needs a positive model_calls allowance"
            " to construct with, not %r" % (construction,))
    if type(uses) is not int or uses <= 0:
        raise TreatmentRefused(
            "a cost claim needs a positive declared number of uses, not %r"
            % (uses,))
    shared = {"task_id": str(dict(task or {}).get("task_id", "")),
              "task": dict(task or {}), "budget": allowance,
              "uses": uses,
              "dispatches_per_use": int(construction),
              "use_dispatches": uses * int(construction)}
    return {
        "retained": {**shared, "construction_dispatches": 0,
                     "reacquires": False},
        "cold": {**shared, "construction_dispatches": int(construction),
                 "reacquires": True},
        "units_per_dispatch": _reservation_unit(),
    }


def _reservation_unit() -> int:
    """Reservation units for one construction send, from the cap sheet.

    This was a per-dispatch constant in `s09_route_cost`, measured once
    from a 33-character smoke request. A construction call is 4880
    characters and 2048 output tokens, which the broker prices 130 times
    higher, so every cost figure built on the constant understated the
    headroom a run needs. The cap sheet commits the real bounds and the
    broker prices them.
    """
    from . import s09_cap_sheet
    return s09_cap_sheet.load().unit_allowance.per_request


def use_dispatches(arm: dict) -> int:
    return int(arm.get("use_dispatches",
                       int(arm["uses"]) * int(arm["dispatches_per_use"])))


def cost_of(arm: dict) -> dict:
    """One arm's construction and use costs, kept apart and totalled.

    The total is a sum of the two parts rather than a number of its own,
    so a reader who disagrees with a part can rebuild the total and get
    the same disagreement rather than a different figure.
    """
    unit = _reservation_unit()
    construction = int(arm["construction_dispatches"])
    use = use_dispatches(arm)
    parts = {"construction": _spend(construction, unit),
             "use": _spend(use, unit)}
    return {**parts,
            "total": {"dispatches": construction + use,
                      "units": (construction + use) * unit}}


def _spend(dispatches: int, unit: int) -> dict:
    return {"dispatches": dispatches, "units": dispatches * unit}


def total_cost(cost: dict) -> int:
    return sum(part["units"] for key, part in cost.items()
               if key in ("construction", "use"))


def cost_report(arms: dict, *, uses: int) -> dict:
    """Both arms' costs, each split, plus the crossover between them.

    The denomination is named because the number is not money. The route
    reported no charge at all, which is an absence rather than a measured
    zero, so the provider figure is reported as unreported and only the
    reservation unit is countable. Reporting a zero there would claim a
    receipt measured a price, and reporting only the reservation figure
    would understate the headroom a run needs.
    """
    unit = _reservation_unit()
    per_arm = {name: cost_of(arm) for name, arm in arms.items()
               if name in ("retained", "cold")}
    construction = per_arm["cold"]["construction"]["units"]
    per_use = unit * int(arms["retained"]["dispatches_per_use"])
    return {
        "uses": uses,
        "denomination": "reservation-units",
        "units_per_dispatch": unit,
        "provider_charge_units_per_dispatch": None,
        "provider_charge_state": "NOT_REPORTED",
        "source": "reports/cap-sheets/invl02-s09-cap.json",
        "reads_as": ("a reservation the allocator needs in order to admit a"
                     " dispatch, not a charge the provider bills"),
        "arms": per_arm,
        "construction_units": construction,
        "per_use_units": per_use,
        "break_even_uses": -(-construction // per_use) if per_use else None,
        "retained_wins_through_uses":
            (-(-construction // per_use) if per_use else None),
    }


def substituted_observations(task: dict, *, verdict: str) -> list:
    """A real observation record for `task`, carrying `verdict`."""
    task_id = str(dict(task or {}).get("task_id", ""))
    return [{"observation_id": "obs-%s-seed" % task_id,
             "task_id": task_id,
             "capability_id": "ad01-%s" % _capability_field(task_id)
             if task_id else "ad01",
             "verdict": verdict}]


def substitute_observations_for(task: dict, observations: list, *,
                                verdict: str) -> tuple:
    """The same observations with their verdict moved, and the plan.

    Everything except the verdict is held fixed, because the whole claim
    is that the policy's action responds to the evidence. Moving the
    task id at the same time would leave a policy keyed on the identifier
    looking like one that reads its evidence.
    """
    before = list(observations or [])
    if not before:
        raise TreatmentRefused("there is no observation to substitute")
    verdicts = [str(o.get("verdict", "")) for o in before]
    if verdict in verdicts:
        raise TreatmentRefused(
            "substituting the verdict %r changes nothing, so every policy"
            " would pass the gate without being tested" % verdict)
    after = [{**o, "verdict": verdict} for o in before]
    plan = {"task_id": str(dict(task or {}).get("task_id", "")),
            "verdicts_before": verdicts,
            "verdicts_after": [verdict] * len(after),
            "substituted": True}
    return after, plan


def observation_substitution_plan(task_ids: list, selected: list, *,
                                  verdict: str) -> dict:
    """Which tasks get their observation substituted and which do not."""
    known = sorted(str(t) for t in task_ids or [])
    chosen = sorted(str(t) for t in selected or [])
    if not chosen:
        raise TreatmentRefused(
            "a substitution plan must select at least one task, or"
            " nothing is being tested")
    unknown = [t for t in chosen if t not in known]
    if unknown:
        raise TreatmentRefused(
            "substitution plan names tasks that do not exist: %s"
            % ", ".join(unknown))
    return {"tasks": known, "substituted_tasks": chosen,
            "untouched_tasks": [t for t in known if t not in chosen],
            "verdict_before": "not-preserved", "verdict_after": verdict}


def _action_of(source: str, task: dict, observations: list, *,
               authority: dict | None = None) -> dict:
    """The action `source` produces, through the real child executor.

    The policy runs in a child process on the view it would actually be
    given, so the gate exercises the same bytes the study would execute
    rather than a local reimplementation of what it ought to do.

    That is exactly why it needs authority. Executing the policy is
    executing policy source, so it goes through the same store, allocation
    and operation identity every other execution needs, and the comparison
    names a different operation per side. Without it the gate cannot run
    the policy at all, and a caller with no store has no action to compare.
    """
    from . import method_exec, policy_step
    record = policy_step.make_policy_artifact(
        source, origin="authored-control")
    view = policy_step.materialize_view(
        task=dict(task or {}), observations=list(observations or []),
        open_questions=[], last_result=None, eligible_methods=[],
        remaining={"steps": 2, "model_calls": 1, "queries": 4})
    policy_step.verify_policy_record(record)
    if not authority:
        raise TreatmentRefused(
            "substitution gate needs a durable store, an allocation and an"
            " operation identity: it executes the policy source")
    return method_exec.run_step_out_of_process(
        record["policy_source"], view, {}, **authority)["action"]


def substitution_changes_action(source: str, task: dict, original: list,
                                substituted: list, *,
                                authority: dict | None = None) -> bool:
    """Whether the policy's action moved when its evidence did.

    The target is excluded from the comparison. A policy that changed only
    which task it named has not read the observation, and including the
    target in the equality would let one hide behind the other.
    """
    before = _action_of(source, task, original, authority=_side(
        authority, "original"))
    after = _action_of(source, task, substituted, authority=_side(
        authority, "substituted"))
    return _comparable(before) != _comparable(after)


def _side(authority: dict | None, suffix: str) -> dict | None:
    """One side's own operation, so the two runs are two operations.

    Reusing a single operation id would make the second side replay the
    first side's receipt and report the same action, which would read as
    "the evidence did not move it" when nothing was executed twice.
    """
    if not authority:
        return None
    return {**authority, "operation_id": "%s-%s" % (
        authority["operation_id"], suffix)}


def _comparable(action: dict) -> str:
    return _packet.canonical({"kind": action.get("kind"),
                              "target": action.get("target"),
                              "inputs": action.get("inputs"),
                              "evidence_refs": action.get("evidence_refs")})


def substitution_gate(source: str, task: dict, original: list,
                      substituted: list, *,
                      authority: dict | None = None) -> dict:
    """Whether a policy's behaviour is driven by evidence.

    The verdict names which of the two failures it found, because a gate
    that only said no would leave a reader guessing whether the policy
    was blind to the evidence or merely unchanged by accident.
    """
    moved = substitution_changes_action(
        source, task, original, substituted, authority=authority)
    return {"responds_to_evidence": moved,
            "verdict": ("responds-to-evidence" if moved
                        else "responds-only-to-identifier"),
            "original_action": _action_of(source, task, original,
                                          authority=_side(authority,
                                                          "original")),
            "substituted_action": _action_of(source, task, substituted,
                                             authority=_side(authority,
                                                             "substituted"))}


def _eligible_methods(arm: dict) -> list:
    """The capability ids a policy may name for this arm's family.

    Empty everywhere before this, which is why every scored arm reported
    "admitted no action that reaches a method executor": the prompt named
    `eligible_methods` as a field of the view and never said what would be
    in it, so a policy that read the view found nothing to select.
    """
    family = (arm or {}).get("family") or ""
    if not family:
        return []
    try:
        from . import seeds
        return sorted(
            c["capability_id"] for c in seeds.SEED_CAPABILITIES
            if c.get("family") == family or family in c["capability_id"])
    except Exception:  # noqa: BLE001 - a prompt must not raise
        return []


def treatment_prompt(arm: dict, task: dict, experience: dict) -> str:
    """The construction prompt an arm would spend a call on.

    Built from the same `method_exec` contract and `policy_step` vocabulary
    `construct` uses, and carrying the same experience line, so the two
    arms differ in the rendered bytes exactly where the arms differ.
    """
    from . import method_exec, policy_step
    contract = method_exec.step_contract()
    lines = [
        "Write one python policy that decides how to investigate.",
        "Family: %s." % (arm or {}).get("family", ""),
        "Interface: exactly one module-level function STEP(view, state).",
        "The view holds task_content, observations, open_questions,",
        "last_result, eligible_methods, remaining and contract_versions.",
        # The view is a mapping and the model cannot know that. It listed
        # the fields, showed no access syntax, and the model guessed
        # `view.eligible_methods` - so the child died with AttributeError
        # on a dict. Everything else it wrote was right, which is what
        # makes this the prompt's fault and not the model's.
        "The view is a plain python dict, so read it as "
        "view['eligible_methods'] and view['task_content']['task_id'].",
        # `eligible_methods` was named here and left empty everywhere it
        # is built, so no policy could name a method and the scorer
        # reported "admitted no action that reaches a method executor" for
        # every arm. The list is the family's authored controls, which is
        # what the scorer dispatches against.
        "Eligible methods for this task: %s." % (
            ", ".join(_eligible_methods(arm)) or "none"),
        # The dispatcher's first gate is that the action's target is the
        # task in scope - it loads the world by that id. A policy that
        # names anything else is refused as out of scope, which surfaced
        # as "admitted no action that reaches a method executor".
        "Target task id: %s. Every action must carry that id as its "
        "target." % (task or {}).get("task_id", ""),
        # Two envelopes, and the prompt used to state only one of them.
        # The shape below is what the *policy function* must return when it
        # runs. What the *response* must be is `{"entry": "<source>"}` -
        # `packet.parse_construction_response` reads that key, and without
        # it here the model obeyed the prompt and returned bare source,
        # which no parser would accept.
        "The policy function must return exactly "
        "{\"action\": <action>, \"state\": <object>} when it runs.",
        "Send back exactly one JSON object shaped "
        "{\"entry\": \"<the complete python source>\"} and nothing else.",
        "Action kinds: %s." % ", ".join(policy_step.ACTION_KINDS),
        # The kinds are not the shape. The model was told which kinds exist
        # and never shown an action, so it wrote `{"kind", "target"}` and
        # the validator refused it for missing three of the five required
        # fields. The example is the full object, and it validates.
        "An action is exactly %s" % json.dumps({
            "kind": "use_method", "target": "<task id>",
            "inputs": {"method_id": "<one of the eligible methods>",
                       "max_queries": 8},
            "evidence_refs": [], "requested_resources": {"queries": 8}},
            sort_keys=True),
        "Entry: %s with %s." % (contract["entry"], contract["param_rule"]),
        "Source must be %s." % contract["source_rule"],
        "Budget: %s." % _packet.canonical((arm or {}).get("budget", {})),
    ]
    observed = (experience or {}).get("observations") or []
    if observed:
        # `reason` rides along because `verdict` alone is a dead field for
        # every measured record. The oracle that accepts a reducer's trial is
        # the same function that grades its output, so a record earned by a
        # real reducer reads `preserved` whether that reducer found a
        # reduction or handed its input straight back, and the two are
        # `ok-preserved` and `ok-incumbent`. A policy shown only the verdict
        # is shown a constant.
        lines.append("Prior observations: %s" % _packet.canonical(
            [{"task_id": o.get("task_id"), "verdict": o.get("verdict"),
              "reason": o.get("reason")}
             for o in observed[-8:]]))
    return "\n".join(lines)


def propose_from_model(dsn: str, *, cid: str, gateway: Any, model: str,
                       charter: dict, world: int, arm: str,
                       allocation_id: str):
    def _propose(experience: dict, asked: dict) -> dict:
        seq = experience["boundary"]["seq"]
        return model_propose(
            dsn, cid=cid, seq=seq, gateway=gateway, model=model,
            charter=charter, visible=visible_opportunities(world),
            experience=experience,
            retained=list(experience.get("retained", [])),
            remaining=dict(experience.get("remaining", {})),
            curriculum=curriculum_item(world, arm, seq),
            allocation_id=allocation_id,
            prior_failure=experience.get("prior_failure"),
            attempt=int(experience.get("correction_attempt") or 0))

    return _propose
