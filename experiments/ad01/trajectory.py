"""AD01 trajectory: system-chosen investigations over recorded experience.

Scaffolding first: deterministic proposal construction from the experience
the system actually observed. No model calls here.
"""

from __future__ import annotations

import os

from . import controls, seeds, worlds
from . import packet as _packet
from .selection import select_member as _select_member
from .selection import versioned_use_op_id as _versioned_use_op_id


def reasoning_effort() -> str:
    effort = os.environ.get("AD01_REASONING_EFFORT", "low")
    if effort not in ("low", "medium", "high"):
        raise ValueError("AD01_REASONING_EFFORT must be low|medium|high")
    return effort

def _resolve_sw(task_id: str, budget: int = 0) -> dict:
    report = controls.diagnostic_resolves(task_id)
    return {"control_id": report["control_id"], "task_id": task_id,
            "verdict": "%s-vs-%s" % (report["diagnostic_verdict"],
                                     report["nondiagnostic_verdict"]),
            "detail": report}


def _resolve_gr(task_id: str, budget: int = 8) -> dict:
    report = controls.novel_order_unproductive(task_id, budget=budget)
    return {"control_id": report["control_id"], "task_id": task_id,
            "queries": report["queries"],
            "verdict": "%s seed=%d novel=%d" % (
                report["winner"], report["seed_final"],
                report["novel_final"]),
            "detail": report}


_DIAGNOSTICS = {"software": _resolve_sw, "graph": _resolve_gr}


def _family(task_id: str) -> str:
    return worlds.load_task(worlds.FROZEN_DIR, task_id)["family"]


_FAMILY_TAG = {"software": "sw", "graph": "gr"}


def _capability_for(task_id: str, capability_id: str) -> str:
    want = _FAMILY_TAG[_family(task_id)]
    if capability_id.startswith("seed-%s-" % want):
        return capability_id
    return "seed-%s-greedy" % want


def _check(task: dict, candidate: dict) -> dict:
    from experiments.representation import checkers
    if task["family"] == "software":
        return checkers.check_software(task, candidate)
    return checkers.check_graph(task, candidate)


def _size(task: dict, candidate: dict) -> tuple:
    if task["family"] == "software":
        return len(task["ops"]), len(candidate["ops"])
    total = lambda c: len(c["vertices"]) + len(c["edges"])
    return total(task), total(candidate)


NAMESPACE_TOKEN = ""


def set_namespace_token(token: str) -> str:
    """Set the token every campaign id in this process carries.

    Module state rather than a parameter, because the campaign id is built in
    a dozen places and threading a parameter through all of them would leave
    the collision intact in the ones somebody forgets. A run sets it once at
    entry; an unset token reproduces the old behaviour exactly.
    """
    global NAMESPACE_TOKEN
    NAMESPACE_TOKEN = "".join(
        ch for ch in str(token) if ch.isalnum() or ch in "-_")
    return NAMESPACE_TOKEN


def _parse_campaign_id(cid: str) -> tuple:
    """Split a campaign id into world, arm, seq and its namespace token.

    The token is a suffix the id gained when namespaces were introduced, so
    both the four-part and five-part forms are live. Rejecting either shape
    would make ids the system itself mints unresumable.
    """
    parts = cid.split("-")
    if parts[0] != "ad01" or parts[2] not in ("I", "R") or len(parts) < 4:
        raise ValueError("malformed campaign id %r" % (cid,))
    try:
        world, arm, seq = int(parts[1][1:]), parts[2], int(parts[3])
    except ValueError:
        raise ValueError("malformed campaign id %r" % (cid,))
    # Everything after the sequence is the token, and a token may itself carry
    # dashes because the sanitiser keeps them. Splitting on every dash and
    # expecting a fifth part would truncate `tok-9` to `tok`.
    token = "-".join(parts[4:])
    return world, arm, seq, token


def campaign_id(world: int, arm: str, seq: int = 0,
                token: str = "") -> str:
    """A campaign id, namespaced by the run token when one is supplied.

    The token is a suffix so every existing `ad01-` prefix match keeps
    working, which is why it is not a prefix. Without it two runs mint the
    same campaign id, and since receipts are looked up by operation id
    before dispatch, the second run replays the first run's response.
    """
    base = "ad01-w%d-%s-%02d" % (world, arm, seq)
    cleaned = "".join(ch for ch in str(token or NAMESPACE_TOKEN)
                      if ch.isalnum() or ch in "-_")
    return "%s-%s" % (base, cleaned) if cleaned else base


def _alloc_id(cid: str) -> str:
    return "ad01-campaign-%s" % cid


def _attempt_id(cid: str, seq: int) -> str:
    return "att-%s-%d" % (cid, seq)


def _read_conn(dsn: str):
    from psycopg.rows import dict_row
    from settlement import db
    return db.connect(dsn, row_factory=dict_row)


def _campaign_operations(dsn: str, cid: str) -> list:
    prefix = "ad01-%s-" % cid
    with _read_conn(dsn) as conn:
        return conn.execute(
            "SELECT id, payload->>'effect' AS effect FROM operations"
            " WHERE starts_with(id, %s)",
            (prefix,)).fetchall()


def _check_tasks(tasks: list) -> None:
    for task_id in tasks:
        try:
            worlds.load_task(worlds.FROZEN_DIR, task_id)
        except KeyError:
            raise ValueError("unknown task %r" % (task_id,))


def authorize_campaign(dsn: str, cid: str, *, authorized: int,
                       study_root: str | None = None,
                       ceilings: dict | None = None,
                       correction_budget: int = 2) -> dict:
    from settlement import authority as _authority
    root = study_root or cid
    handle = _authority.authorize_study(
        dsn, root, authorized=authorized,
        allocation_id=_alloc_id(cid), ceilings=ceilings,
        correction_budget=correction_budget)
    return {"study_root": handle.study_root,
            "allocation_id": handle.allocation_id,
            "authorized": handle.authorized,
            "store_fingerprint": handle.store_fingerprint}


def _bind_study_authority(dsn: str, study_root: str) -> dict:
    from settlement import authority as _authority
    try:
        handle = _authority.bind_study(dsn, study_root)
    except _authority.MissingAuthority as exc:
        raise ValueError(
            "campaign requires explicit caller agenda authority: %s"
            % exc)
    return {"bound": True, "via": "bind_study",
            "study_root": handle.study_root,
            "allocation_id": handle.allocation_id,
            "authorized": handle.authorized,
            "store_fingerprint": handle.store_fingerprint}


def ensure_campaign(dsn: str, cid: str, world: int, arm: str,
                    charter: dict, caps: dict,
                    tasks: list | None = None,
                    study_root: str | None = None) -> dict:
    from settlement import store
    from settlement.common import Command, ResultCode
    with _read_conn(dsn) as conn:
        schedule = conn.execute(
            "SELECT result_data FROM command_journal WHERE request_id = %s",
            ("schedule-%s" % cid,)).fetchone()
    if tasks is None:
        tasks = (schedule["result_data"]["tasks"] if schedule
                 else _default_tasks(world, arm))
    _check_tasks(tasks)
    study_root = study_root or cid
    authority = _bind_study_authority(dsn, study_root)
    amount = caps.get("agenda_authorized")
    if type(amount) is int and amount > 0 \
            and amount != authority["authorized"]:
        raise ValueError(
            "caps agenda_authorized %d disagrees with granted study"
            " authority %d; the grant governs"
            % (amount, authority["authorized"]))
    plan = store.transact(
        dsn, Command(request_id="schedule-%s" % cid,
                     payload={"tasks": tasks}),
        lambda cur, control: (ResultCode.APPLIED, "campaign schedule recorded",
                              {"tasks": tasks}, [], []))
    if plan.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise ValueError(plan.detail)
    objective = charter.get("objective", "")
    try:
        made = store.admit_commitment(
            dsn, Command(request_id="admit-%s" % cid,
                         payload={"investigation_id": cid,
                                  "objective": objective,
                                  "origin": "ad01-trajectory"}))
    except Exception as exc:
        if "already exists" not in str(exc):
            raise
        made = None
    return {"campaign_id": cid, "world": world, "arm": arm,
            "admitted": made is not None,
            "allocation_id": _alloc_id(cid), "tasks": plan.data["tasks"],
            "study_root": study_root, "authority": authority}


def record_decision(dsn: str, cid: str, seq: int, decision: dict) -> str:
    from settlement import store
    from settlement.common import Command, SettlementError
    aid = _attempt_id(cid, seq)
    store.acquire_work(
        dsn, Command(request_id="acquire-%s" % aid,
                     payload={"investigation_id": cid,
                              "attempt_id": aid,
                              "allocation_id": _alloc_id(cid),
                              "composition": "ad01-boundary",
                              "owner": cid}))
    made = store.submit_observation(
        dsn, Command(request_id="decide-%s" % aid,
                     payload={"attempt_id": aid,
                              "content": {"kind": "decision", "seq": seq,
                                          "decision": decision}}))
    if made.data["attempt_id"] != aid:
        raise SettlementError(
            "store returned decision for unexpected attempt %r" % (
                made.data.get("attempt_id"),))
    return aid


def _effect_operation_id(dsn: str, cid: str, episode: dict) -> str:
    """The operation a boundary's effect ran as, or empty when it ran as none.

    This is the repair to RF-02. The column used to be written with the
    constant `ad01-<cid>-b<seq>-effect`, which named no `operations` row and
    was read back by nothing, so the "admitted effect -> observation" arrow
    was doubly durable and causally unbound: both sides were rows and the only
    thing joining them was `(investigation_id, seq)`.

    The identity is read off the episode the boundary actually produced and
    then checked against the `operations` table. That order is the point. An
    episode can carry any string, and a derivation that trusted the episode
    would make the column true by being written to, which is the defect
    reproduced one level down. So the database has the last word: a name that
    does not resolve to a settled operation is not an identity and returns
    empty.

    Empty is a real answer rather than a fallback. A boundary that runs a
    host-side diagnostic (`controls.diagnostic_resolves` has no dsn and never
    reaches the broker) admits no operation at all, and on such a boundary the
    honest outcome is that the effect is NOT admitted. Writing a synthesized id
    there would restore exactly the defect: a row that looks joined and joins
    nothing. The witness is `test_a_boundary_that_admitted_no_operation_claims_no_effect`.
    """
    candidates = []
    named = str((episode or {}).get("operation_id") or "")
    if named:
        candidates.append(named)
    construction = ((episode or {}).get("executable") or {}).get(
        "construction") or {}
    for key in ("init_operation", "repair_operation"):
        value = str(construction.get(key) or "")
        if value:
            candidates.append(value)
    if not candidates or dsn is None:
        return ""
    with _read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT id FROM operations WHERE id = ANY(%s) AND settled",
            (candidates,)).fetchall()
        conn.commit()
    settled = {row["id"] for row in rows}
    for candidate in candidates:
        if candidate in settled:
            return candidate
    return ""


def _s09_effect_id(dsn: str, cid: str, seq: int) -> str:
    """The effect identity already recorded for this boundary, or empty.

    Read rather than computed, because a computed identity is the defect. A
    boundary adopts an operation identity once, at the moment it admits an
    effect, and a caller that arrives later reads the row instead of deriving
    a second answer that could disagree with the first.
    """
    row = _s09_get(dsn, cid, seq)
    return str((row or {}).get("effect_id") or "")


def _s09_get(dsn: str, cid: str, seq: int):
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT * FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = %s",
            (cid, seq)).fetchone()
        conn.commit()
        return row


def _s09_accept(dsn: str, cid: str, seq: int, *, decision: dict,
                provenance: str, driver_version: str,
                step: dict | None = None) -> None:
    """Record that a boundary accepted an action. The row's first state.

    One function for the insert-or-upgrade of an `accepted` row, because the
    two halves are one decision and disagreed when they were separate.

    The status is written as `accepted` and is not a parameter. An earlier
    revision took `status` from the caller, which moved the write here but
    left the decision there: `agenda_policy` passed `incorporated` for a
    policy step that had refused and whose boundary had never run, so the
    owner stamped a transition it had not observed and could not refuse. A
    caller that can assert a transition is a second authority wearing an
    argument. Incorporation is `_s09_incorporate`, which is reached only by
    the path that ran the effect.

    The upgrade rewrites `accepted_action` and the three policy columns
    together and leaves everything else. Its `WHERE` requires an unresolved
    row twice over: the accepted action must still be `pending`, and the
    effect record must be absent. The second clause is the one that matters
    once `status` is derived -- without it a row whose effect is already
    recorded could be driven back to `accepted` above a settled effect, which
    is the same disagreement this function exists to remove. A row that
    holds any other action was decided already and is left exactly as it is.
    """
    from psycopg.types.json import Json
    with _read_conn(dsn) as conn:
        conn.execute(
            "INSERT INTO s09_policy_state"
            " (investigation_id, seq, attempt_id, effect_id,"
            " policy_input, policy_output, state_transition,"
            " accepted_action, status, provenance, driver_version)"
            " VALUES (%s, %s, %s, '', %s, %s, %s, %s, 'accepted', %s, %s)"
            " ON CONFLICT (investigation_id, seq) DO NOTHING",
            (cid, seq, _attempt_id(cid, seq),
             Json((step or {}).get("policy_input") or {}),
             Json((step or {}).get("policy_output") or {}),
             Json((step or {}).get("state_transition") or {}),
             Json(decision), provenance, driver_version))
        if step is not None:
            conn.execute(
                "UPDATE s09_policy_state SET policy_input = %s,"
                " policy_output = %s, state_transition = %s,"
                " accepted_action = %s, updated_at = now()"
                " WHERE investigation_id = %s AND seq = %s"
                " AND accepted_action->>'status' = 'pending'"
                " AND effect_record IS NULL",
                (Json(step["policy_input"]), Json(step["policy_output"]),
                 Json(step["state_transition"]), Json(decision), cid, seq))
        conn.commit()


def _s09_incorporate(dsn: str, cid: str, seq: int, *, decision: dict,
                     observation: dict, episode: dict, spend: int,
                     provenance: str, effect_record: dict | None = None
                     ) -> None:
    """The `accepted` -> `incorporated` transition, and the effect on the row.

    The boundary's effect has run, so the row stops being an outstanding
    action and starts being a settled one. `status` moves here and nowhere
    else: `policy_step` used to write this column itself for a policy step
    that had been refused and whose boundary had never run, so the same value
    meant "an effect is recorded" and "a policy step ended" depending on which
    module the reader asked.

    `effect_id` is adopted rather than restated, and `effect_record` keeps
    whatever the row already held, so a resumed run cannot overwrite the
    operation identity the first run settled. When `effect_record` is given it
    is this run's fresh effect and it replaces the old one, which is the
    difference between a row that has just been written by `execute_pending`
    and one that is being incorporated from an earlier run's boundary
    observation.

    The mission entry is not released here. Release belongs to the boundary
    that ran, and it is `_s09_release` at the one place that both ran and
    adopted an entry: `execute_pending`. This function is reached from two
    paths, the fresh one at `run_campaign` and the settled-resume one above,
    and on neither does the boundary hold an admitted operation -- the fresh
    path now admits and releases around its own call, and a row incorporated
    from an earlier run has nothing to release. Folding release in here would
    release an operation nobody admitted, which is why the release stayed on
    the path that holds one.
    """
    from psycopg.types.json import Json
    effect_id = _effect_operation_id(dsn, cid, episode or {})
    payload = {"observation": observation, "episode": episode,
               "spend": spend, "decision": decision,
               "effect_operation_id": effect_id}
    with _read_conn(dsn) as conn:
        conn.execute(
            "INSERT INTO s09_policy_state"
            " (investigation_id, seq, attempt_id, effect_id,"
            " policy_input, policy_output, state_transition,"
            " accepted_action, effect_record, status,"
            " provenance, driver_version)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
            " 'incorporated', %s, 's09-m1')"
            " ON CONFLICT (investigation_id, seq) DO NOTHING",
            (cid, seq, _attempt_id(cid, seq),
             effect_id, Json({}), Json({}),
             Json({}), Json(decision), Json(payload), provenance))
        conn.execute(
            "UPDATE s09_policy_state SET status = 'incorporated',"
            " effect_record = CASE WHEN %s::jsonb IS NULL"
            " THEN COALESCE(effect_record, %s::jsonb) ELSE %s::jsonb END,"
            " effect_id = CASE WHEN effect_id = '' THEN %s ELSE effect_id END,"
            " updated_at = now()"
            " WHERE investigation_id = %s AND seq = %s",
            (Json(effect_record) if effect_record is not None else None,
             Json(payload), Json(effect_record) if effect_record is not None
             else None, effect_id, cid, seq))
        conn.commit()


def _s09_release(dsn: str, cid: str, seq: int) -> None:
    """An incorporated operation has run, so it is no longer in flight.

    Leaving it on the mission entry would make a later resume restore work
    that already happened, which is how a recovered crash becomes a
    double-counted effect. Called by the pending-resume path, which is the
    only one holding an admitted operation to release.
    """
    from . import mission

    mission.release_operation(dsn, cid, _attempt_id(cid, seq))


def _decision_task_id(decision: dict) -> str:
    """The task a decision names, or empty when it names none."""
    action = dict(decision or {}).get("next_action")
    return str(action.get("task_id") or "") if isinstance(action, dict) else ""


def accept_action(dsn: str, cid: str, seq: int,
                  decision: dict, *, program_digest: str = "",
                  task_id: str = "", capability_id: str = "seed-sw-greedy"
                  ) -> str:
    """Admit one boundary's action and record the identity it was admitted under.

    `program_digest` is what the admitting caller knows and nothing downstream
    can recover: the bytes of the program that produced this decision. It is
    recorded on the mission entry at the moment of admission, before any
    effect runs, because a restart happens exactly when the effect has not run
    and a record written at effect time would be absent at the moment it is
    needed.

    A caller that admits through the policy consumer passes the consumer's
    digest. A caller that admits a decision directly and names no program is
    recorded as the seed program's identity, which is the program that will
    actually execute it -- see `_admitting_program_digest`. An unrecognised
    digest is a refusal, because a digest that names no known program would be
    recorded as authority it does not have.
    """
    from . import mission

    program_digest = _admitting_program_digest(program_digest)
    task_id = task_id or _decision_task_id(decision)
    existing = _s09_get(dsn, cid, seq)
    if existing is not None:
        attempt_id = existing["attempt_id"]
    else:
        settled, pending = _read_campaign(dsn, cid)
        if seq in settled:
            raise ValueError("boundary %d already settled" % seq)
        if seq in pending and pending[seq].get("decision") != decision:
            raise ValueError("pending effect %d already accepted" % seq)
        _s09_accept(dsn, cid, seq, decision=decision, provenance="s09-m1",
                    driver_version="s09-m1")
        if seq not in pending:
            record_decision(dsn, cid, seq, decision)
        attempt_id = _attempt_id(cid, seq)
    mission.admit_operation(
        dsn, cid, seq=seq, attempt_id=attempt_id, decision=decision,
        program_digest=program_digest, task_id=task_id,
        capability_id=_capability_for(task_id, capability_id)
        if task_id else capability_id)
    return attempt_id


def _admitting_program_digest(named: str) -> str:
    """The digest of the program a decision is admitted under.

    A named digest must be a digest, which is all that can be checked here. A
    stronger check -- that the digest names a program this repository holds --
    would need a registry of programs that does not exist, and refusing an
    authored STEP program for being absent from a seed list would be an
    authority the caller does not have.

    The fallback is the seed program, and that is not a convenience default:
    `execute_pending` runs `seeds.run_seed` under `seed-sw-greedy` when no
    program was attached to the campaign, so that is the program this decision
    will actually run under whether or not the caller said so.
    """
    from . import mission

    if not named:
        return mission.seed_program_digest()
    if len(named) != 64 or any(c not in "0123456789abcdef" for c in named):
        raise mission.MissionRefused(
            "program digest must be a sha256 hex digest, not %r" % named)
    return named


def admit_boundary(dsn: str, cid: str, seq: int, decision: dict, *,
                   capability_id: str, program_digest: str = "") -> str:
    """Hold the operation this boundary just decided, before its effect runs.

    The seam is the line in `_run_boundary` that calls this, and it is not
    `_s09_accept` and not `_s09_incorporate`. `record_decision` makes the
    decision durable and `s09_policy_state` already holds it as `accepted`;
    what neither of them records is that the work is now owed. A crash between
    that write and the effect leaves a boundary whose decision survives and
    whose operation exists nowhere, so a restart re-decides it and the admitted
    identity is gone before anything ran. That window is the one
    `accept_action` was written for, and this is the live path entering it.

    Everything is derived from what the boundary already holds. `seq` and the
    attempt id are positional facts about the boundary; `task_id` and
    `capability_id` are the arguments `_run_boundary` was called with and the
    decision's own `next_action`.

    `program_digest` is passed through, not derived, and no value is invented
    here. `_run_boundary` reaches four different programs -- a control, a seed
    capability, a constructed member's authored source, a retained member's
    source -- and which one runs is not decided until the arm below, so a
    digest taken at this line would name a program that has not been chosen.
    The seed digest therefore stands, which is what
    `_admitting_program_digest` already derived for a caller that names no
    program, and an arm that runs something else says so through the
    `capability_id` it records.

    This adds no writer, which is a claim about this seam rather than about
    the column. `investigations.in_flight` has three writers and all three are
    in `mission`, which owns the column: `admit_operation`, `resume_operation`
    and `release_operation`. The correctness here is that this reaches the
    owning writer through `accept_action` rather than beside it. `mission`
    holds `FOR UPDATE` across its read-then-write, which is what makes a
    writer to this column safe rather than a lost update; that argument
    belongs to each writer's own docstring, not to this one.
    """
    return accept_action(dsn, cid, seq, decision,
                         program_digest=program_digest,
                         task_id=_decision_task_id(decision),
                         capability_id=capability_id)


def mission_held(dsn: str, cid: str, seq: int):
    """The mission entry's record of the operation at this seq, or None."""
    from . import mission

    return mission.held_operation(dsn, cid, _attempt_id(cid, seq))


def _effect_record_for(decision: dict, observation: dict, episode: dict,
                       spend: int, admitted) -> dict:
    """Persist the effect beside the admitted identity that authorized it."""
    payload = {"observation": observation, "episode": episode,
               "spend": spend, "decision": decision}
    if admitted is not None:
        payload["ran_under"] = {
            "program_digest": admitted.program_digest,
            "input_identity": admitted.input_identity,
            "decision_digest": admitted.decision_digest,
            "task_id": admitted.task_id,
            "capability_id": admitted.capability_id}
    return payload


def execute_pending(dsn: str, cid: str, seq: int, *,
                    task_id: str, capability_id: str, caps: dict,
                    seed_obs: dict, charter: dict, boundary: dict,
                    experience: dict, state: dict,
                    study_root: str | None = None,
                    construction=None) -> tuple:
    from . import mission

    row = _s09_get(dsn, cid, seq)
    if row is None:
        raise ValueError("no accepted action for %s %d" % (cid, seq))
    if row["effect_record"] is not None:
        rec = dict(row["effect_record"])
        return (rec["observation"], rec["episode"],
                int(rec["spend"]), rec["decision"])
    admitted = mission_held(dsn, cid, seq)
    decision = dict(row["accepted_action"])
    if admitted is not None:
        # The entry, not the schedule, says what this operation runs. A restart
        # re-invokes the campaign with a caller-supplied capability, and that
        # argument answers what the CALLER would run -- which is how a
        # boundary came to execute one program while the record filed its
        # result under another. Reading the identity here is what makes
        # `ran_under` below a record of the run rather than a copy of the
        # admission.
        #
        # Corrected rather than refused. The admitted program is durable and
        # runnable, so refusing would discard work this store can finish, on
        # the common case of a caller that simply did not repeat its own
        # argument. The cost accepted is that a genuinely stale admitted
        # program still runs; that is visible, because the record names it,
        # where a silent substitution was not.
        task_id = admitted.task_id or task_id
        capability_id = admitted.capability_id or capability_id
        # Having taken the entry's task and capability, this run must run the
        # decision the entry pinned those inputs to. The two digests were
        # written by `admit_operation` and read back by nobody until here; a
        # decision that has moved since admission would otherwise run under
        # inputs the record does not name, and the effect row would file the
        # result under the admission's identity.
        mission.require_admitted_identity(admitted, decision=decision,
                                          task_id=task_id,
                                          capability_id=capability_id)
    journal = {"dsn": dsn, "cid": cid, "decision": decision}
    observation, episode, spend = _run_boundary(
        task_id, capability_id, caps, seed_obs, charter=charter,
        boundary=boundary, experience=experience, state=state,
        construction=construction, accepted=decision,
        journal=journal, study_root=study_root or cid)
    # The entry's record is released once the effect is recorded, so its
    # identity is copied before release and remains available after restart.
    payload = _effect_record_for(decision, observation, episode, spend,
                                admitted)
    _s09_incorporate(dsn, cid, seq, decision=decision,
                     observation=observation, episode=episode, spend=spend,
                     provenance="s09-m1", effect_record=payload)
    return observation, episode, spend, decision


def _read_campaign(dsn: str, cid: str) -> tuple:
    settled, pending = {}, {}
    with _read_conn(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT o.id, o.content FROM attempt_observations o"
                " JOIN attempts a ON a.id = o.attempt_id"
                " WHERE a.investigation_id = %s ORDER BY o.id", (cid,))
            for row in cur.fetchall():
                content = dict(row["content"] or {})
                seq = int(content.get("seq", -1))
                if content.get("kind") == "boundary":
                    settled[seq] = {"row_id": row["id"], **content}
                elif content.get("kind") == "decision":
                    pending.setdefault(seq, {"row_id": row["id"],
                                             **content})
    for seq in settled:
        pending.pop(seq, None)
    return settled, pending


DEV_EPISODE_CAP = 3


def _sequenced_construction_allowance(remaining: int,
                                      diagnostic_spent: int) -> int:
    from settlement.loop import ResourceEnvelope
    return ResourceEnvelope.sequence_construction_allowance(
        remaining, diagnostic_spent)


def _refuse_probe(max_queries: int):
    from settlement import loop as _loop
    envelope = _loop.ResourceEnvelope(
        study_root="ad01-trajectory",
        allocation_id="ad01-trajectory", authorized=1)
    return envelope.admit_probe(
        "", operation_id="ad01-probe-zero",
        amount=int(max_queries),
        probe_allocation_id="ad01-trajectory"
        + _loop.PROBE_ALLOWANCE_SUFFIX)


def _learner_checkpoint_op(dsn: str, cid: str, seq: int) -> str | None:
    with _read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT o.id FROM operations o"
            " WHERE starts_with(o.id, %s)"
            " AND o.payload->>'effect' = 'model-inference'"
            " AND EXISTS (SELECT 1 FROM receipts r"
            " WHERE r.operation_id = o.id"
            " AND r.outcome IN ('success', 'failure'))"
            " ORDER BY o.id DESC",
            ("ad01-%s-learner-%d" % (cid, seq),)).fetchall()
    if not rows:
        return None
    return rows[0]["id"]


def _note_diagnostic_checkpoint(dsn: str, study_root: str,
                                decision_id: str, cid: str, seq: int,
                                observation: dict, seen: dict,
                                state: dict | None) -> None:
    from settlement import authority as _authority
    from settlement.common import SettlementError
    operation_id = _learner_checkpoint_op(dsn, cid, seq)
    if operation_id is None:
        return
    try:
        _authority.note_phase(
            dsn, study_root, decision_id, "diagnostic", operation_id,
            detail={"observation": dict(observation),
                    "remaining": dict((seen or {}).get("remaining") or {}),
                    "state": {key: int((state or {}).get(key, 0))
                              for key in ("model_calls", "construction_calls",
                                          "dev_episodes")}})
    except SettlementError:
        return


def _diagnostic_checkpoint(dsn: str, study_root: str,
                           decision_id: str) -> dict | None:
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT operation_id, detail FROM study_phases"
            " WHERE study_root = %s AND decision_id = %s"
            " AND phase = 'diagnostic'",
            (study_root, decision_id)).fetchone()
    if row is None:
        return None
    detail = dict(row["detail"] or {})
    observation = detail.get("observation")
    remaining = detail.get("remaining")
    saved = detail.get("state")
    if not isinstance(observation, dict) \
            or not isinstance(remaining, dict) \
            or not isinstance(saved, dict):
        return None
    return {"operation_id": row["operation_id"],
            "observation": observation, "remaining": remaining,
            "state": saved}


METHOD_RELEASE_PROTOCOL = "s09-revision-v1"
METHOD_EVALUATOR_VERSION = "ad01-method-eval-01"
"""The evaluator that graded an acquired method, named for the release row.

`bind_revision` requires a pinned evaluator on every row it writes, so a
method release names the one that graded its bytes. The method assessment
is `records.assess_frozen`, which runs the frozen bytes over a frozen panel
through the same checker the use phase verifies with, so this names that
measurement rather than the policy panel's evaluator: a policy release and
a method release are separate artifacts and are graded separately.
"""

METHOD_PANEL_SIZE = 2


def method_release_id(cid: str, digest: str) -> str:
    """The release an acquired method's bytes are pinned under.

    Campaign-scoped, and the shape is the one the policy release already
    uses: `ad01-<cid>-policy-<digest12>`, with `method` in place of
    `policy`. The measurement behind reusing that shape rather than a
    task-shaped or study-shaped one is that this id must name a member
    that is *retained for the campaign* rather than qualified on one
    task, and the campaign id is the only identity on this path that
    spans the boundary from "acquired on task X" to "usable on task Y".
    The member id is derived from the bytes, not the task
    (`construct._member_id` hashes the source), so a task-shaped release
    would name an identity the bytes themselves do not carry and two
    campaigns acquiring the same bytes would collide.

    The digest is in the id so that a rebind of the same campaign under
    different bytes is a different release rather than an overwrite of
    the first, and so a release id names the exact bytes it pins.
    """
    return "ad01-%s-method-%s" % (cid, digest[:12])


def bind_method_release(construction: dict, member: dict,
                        observation: dict, *, boundary: dict,
                        scope: dict, panel_size: int = METHOD_PANEL_SIZE
                        ) -> dict:
    """Pin an acquired method's bytes to a durable release.

    Without this the bytes a campaign acquired are pinned to nothing the
    store holds: `capability_releases` has no row for them and
    `selection.select_member` reads that table only when a `release_id` is
    named, so a fresh-process use of a retained method resolves no binding
    and falls to the family scan. That is the last stage of the chain in
    milestone A -- retention/binding -- and it was not performed.

    The lifecycle is the one `bind_revision` already enforces, run on the
    method's behalf: a revision proposal naming the incumbent the acquired
    bytes revise, the frozen bytes, a sealed assessment of those exact
    bytes over a panel, and then the durable binding. Each step is the
    existing machinery rather than a second one. A method that fails any
    of them is reported as a refusal with its reason, never bound.

    An acquired method has no prior release to name as its parent, so the
    parent it revises is the seed member for its family: that is the
    repertoire entry a member with no acquired ancestor would have been,
    and it is the comparison the incumbent baseline is already measured
    against.
    """
    import hashlib

    from . import records, selection

    dsn = construction["dsn"]
    cid = construction["cid"]
    digest = member["source_digest"]
    protocol_id = METHOD_RELEASE_PROTOCOL
    parent_digest = hashlib.sha256(
        ("seed-%s-greedy" % _FAMILY_TAG[scope["family"]]).encode(
            "utf-8")).hexdigest()
    failure_record = {"task_id": observation["task_id"],
                      "parent_digest": parent_digest,
                      "capability_id": member["capability_id"],
                      "source_digest": digest,
                      "observation_id": observation["observation_id"]}
    try:
        proposal = records.open_revision_proposal(
            dsn, investigation_id=cid, parent_digest=parent_digest,
            failure_record=failure_record, scope=scope,
            protocol_id=protocol_id, allocation_id=_alloc_id(cid),
            opportunity_id="method:%s:%s:%s" % (
                boundary["seq"], member["capability_id"], digest))
        freeze = records.freeze_candidate(
            dsn, proposal_id=proposal["proposal_id"],
            source_bytes=member["method_source"], entry=member["entry"])
        panel = _method_panel(scope["family"], construction["world"],
                              proposal["proposal_id"], panel_size)
        assessment = records.assess_frozen(
            dsn, proposal_id=proposal["proposal_id"],
            tasks=panel["task_ids"], baseline="incumbent",
            evaluator_version=METHOD_EVALUATOR_VERSION,
            protocol_id=protocol_id)
    except ValueError as exc:
        return {"bound": False, "reason": str(exc)}
    if assessment.get("outcome") != "bind":
        return {"bound": False,
                "reason": "method assessment did not bind: %s"
                          % assessment.get("reason", ""),
                "assessment_outcome": assessment.get("outcome"),
                "proposal_id": proposal["proposal_id"]}
    release_id = method_release_id(cid, freeze["candidate_digest"])
    current = selection.active_binding_for(
        dsn, scope["family"], release_id=release_id)
    expected = list(current["versions"]) if current else None
    try:
        selection.bind_revision(
            dsn, release_id=release_id,
            versions=[member["capability_id"]], scope=scope,
            disposition="default", fallback="incumbent",
            expected_versions=expected, policy_version="",
            protocol_id=protocol_id,
            evaluator_version=METHOD_EVALUATOR_VERSION,
            evidence_refs=[assessment["attempt_id"]],
            proposal_id=proposal["proposal_id"],
            candidate_digest=freeze["candidate_digest"])
    except (selection.StaleBind, ValueError) as exc:
        return {"bound": False, "reason": str(exc),
                "release_id": release_id,
                "proposal_id": proposal["proposal_id"]}
    return {"bound": True, "release_id": release_id,
            "versions": [member["capability_id"]],
            "candidate_digest": freeze["candidate_digest"],
            "proposal_id": proposal["proposal_id"],
            "panel": panel["task_ids"],
            "assessment_attempt_id": assessment["attempt_id"],
            "scope": dict(scope)}


def _method_panel(family: str, world: int, seed: str, size: int) -> dict:
    """The development-free tasks a method is assessed over.

    Not the development task the bytes were acquired on. An assessment
    that included it would grade the bytes on the task that produced them
    and could report a bind no fresh task confirms, which is the same
    self-measurement the repertoire already refuses when it declines to
    offer a member on its own acquisition task.
    """
    import hashlib

    from . import worlds
    membership = worlds.world_membership(worlds.FROZEN_DIR)[str(world)]
    candidates = [task_id for task_id
                  in list(membership.get("transfer", {}).get(family, []))
                  + list(membership.get("within", {}).get(family, []))
                  if task_id not in _dev_task_ids()]
    if len(candidates) < size:
        raise ValueError("method assessment needs %d frozen %s tasks, has %d"
                         % (size, family, len(candidates)))
    keyed = sorted(candidates, key=lambda task_id: hashlib.sha256(
        ("%s:%s" % (seed, task_id)).encode("utf-8")).hexdigest())
    return {"task_ids": keyed[:size], "scope": {"family": family},
            "world": world}


def _run_boundary(task_id: str, capability_id: str, caps: dict,
                  seed_obs: dict, propose=None,
                  charter: dict | None = None,
                  boundary: dict | None = None,
                  experience: dict | None = None,
                  state: dict | None = None,
                  construction: dict | None = None,
                  accepted: dict | None = None,
                  journal: dict | None = None,
                  consumer=None,
                  study_root: str | None = None) -> tuple:
    capability_id = _capability_for(task_id, capability_id)
    seed_obs = {**seed_obs, "capability_id": capability_id}
    prior = list((experience or {}).get("observations") or [])
    asked = dict(charter or {})
    if not asked.get("objective"):
        asked["objective"] = "x"
    from .learner import curriculum_item, visible_opportunities
    seen = _packet.decision_packet(
        charter=asked,
        visible=(visible_opportunities(boundary["world"])
                 if boundary is not None else []),
        experience={"observations": prior + [seed_obs]},
        retained=list((experience or {}).get("retained") or []),
        remaining=dict((experience or {}).get("remaining") or {}),
        curriculum=(curriculum_item(boundary["world"], boundary["arm"],
                                    boundary["seq"])
                    if boundary is not None else None),
        boundary=boundary)
    if accepted is not None:
        admitted = {"decision": "admitted", "reason": "resumed-pending",
                    "investigation": accepted}
    else:
        if consumer is None:
            from . import agenda_policy as _policy
            proposer = propose if propose is not None \
                else _policy.scaffolding_proposer(task_id, seed_obs)
            dsn = (journal or {}).get("dsn")
            cid = (journal or {}).get("cid") or ""
            if dsn and cid:
                def admit(proposal, supplied, charter, boundary):
                    return admit_investigation(
                        proposal, supplied, charter, boundary,
                        durable_observations=_durable_observations(dsn, cid),
                        trusted_observation_ids=(seed_obs.get(
                            "observation_id"),))
            else:
                admit = admit_investigation
            consumer = _policy.DecisionConsumer(
                proposer=proposer, admit=admit,
                dsn=dsn, cid=cid,
                policy_version=(
                    _policy.MODEL_POLICY_VERSION
                    if propose is not None
                    else _policy.BASELINE_POLICY_VERSION),
                study_root=study_root or "")
        aid = _attempt_id(journal["cid"], boundary["seq"]) \
            if journal and journal.get("dsn") and journal.get("cid") \
            and boundary is not None else None
        outcome = consumer.decide(seen, asked, boundary=boundary,
                                  experience=seen, aid=aid)
        if journal and journal.get("dsn") and state is not None:
            state["model_calls"] = sum(
                op["effect"] == "model-inference"
                for op in _campaign_operations(journal["dsn"],
                                              journal["cid"]))
            seen["remaining"]["model_calls"] = (
                caps.get("model_calls", 60) - state["model_calls"])
        if outcome.get("status") == "refused":
            episode = {"disposition": "no-candidate",
                       "fallback": "incumbent",
                       "fallback_reason": outcome.get("reason",
                                                      "refused"),
                       "task_id": task_id, "queries": 0}
            return seed_obs, episode, 0
        admitted = {"decision": "admitted", "reason": "consumer-admitted",
                    "investigation": outcome["investigation"]}
    action = dict(admitted["investigation"]["next_action"])
    if action.get("kind") == "stop":
        return None, None, 0
    target = action.get("task_id") or task_id
    if boundary is not None:
        reason = _target_refusal(target, **boundary)
        if reason is not None:
            episode = {"disposition": "no-candidate",
                       "fallback": "incumbent", "fallback_reason": reason,
                       "task_id": task_id, "queries": 0}
            return seed_obs, episode, 0
    if action.get("kind") not in ("diagnostic", "development", "use_method", "policy_revision"):
        episode = {"disposition": "no-candidate",
                   "fallback": "incumbent",
                   "fallback_reason": "unknown action kind %r"
                                      % (action.get("kind"),),
                   "task_id": task_id, "queries": 0}
        return seed_obs, episode, 0
    if action.get("kind") in ("diagnostic", "development"):
        want = {"diagnostic_resolves": "software"}.get(
            action.get("diagnostic", "software"),
            action.get("diagnostic", "software"))
        if want != _family(target):
            episode = {"disposition": "no-candidate",
                       "fallback": "incumbent",
                       "fallback_reason": "diagnostic family %r mismatches "
                                          "task family %r"
                                          % (action.get("diagnostic"),
                                             _family(target)),
                       "task_id": task_id, "queries": 0}
            return seed_obs, episode, 0
    if action["kind"] == "development" and state is not None \
            and int(state.get("dev_episodes", 0)) >= DEV_EPISODE_CAP:
        episode = {"disposition": "no-candidate",
                   "fallback": "incumbent",
                   "fallback_reason": "development episode cap reached"
                                      " (%d/trajectory)" % DEV_EPISODE_CAP,
                   "task_id": task_id, "queries": 0}
        return seed_obs, episode, 0
    if action["kind"] == "development":
        action["max_queries"] = min(
            action.get("max_queries", caps.get("diagnostic_queries", 16)),
            _sequenced_construction_allowance(
                seen["remaining"].get("queries", 16), 0))
    action["task_id"] = target
    investigation = {**admitted["investigation"], "next_action": action}
    if journal is not None:
        journal["decision"] = investigation
        if journal.get("dsn") and accepted is None:
            record_decision(journal["dsn"], journal["cid"], boundary["seq"],
                            investigation)
            admit_boundary(journal["dsn"], journal["cid"], boundary["seq"],
                           investigation, capability_id=capability_id)
    if action["kind"] == "use_method":
        return _use_retained_method(action, experience or {}, seed_obs, journal, boundary)
    if action["kind"] == "policy_revision":
        return _construct_policy_revision(investigation, seen, seed_obs, construction, state)
    diagnostic_budget = _sequenced_construction_allowance(
        seen["remaining"].get("queries", 16), 0)
    checkpoint = None
    if journal is not None and journal.get("dsn") and journal.get("cid") \
            and boundary is not None and study_root:
        checkpoint = _diagnostic_checkpoint(
            journal["dsn"], study_root,
            _attempt_id(journal["cid"], boundary["seq"]))
    if checkpoint is not None:
        observation = checkpoint["observation"]
        seen["remaining"] = dict(checkpoint["remaining"])
        if state is not None:
            for key in ("model_calls", "construction_calls",
                        "dev_episodes"):
                state[key] = int(checkpoint["state"].get(key, 0))
    else:
        observation = run_diagnostic(investigation, seen,
                                     budget=diagnostic_budget)
        if journal is not None and journal.get("dsn") \
                and journal.get("cid") and boundary is not None \
                and study_root:
            _note_diagnostic_checkpoint(
                journal["dsn"], study_root,
                _attempt_id(journal["cid"], boundary["seq"]),
                journal["cid"], boundary["seq"], observation,
                seen, state)
    if action["kind"] == "development":
        action["max_queries"] = min(
            int(action.get("max_queries", diagnostic_budget)),
            _sequenced_construction_allowance(
                seen["remaining"].get("queries", 16),
                observation["queries"]))
    if action["kind"] == "diagnostic":
        episode = {"disposition": "inspected", "kind": "diagnostic",
                   "task_id": target,
                   "queries": observation["queries"]}
        return observation, episode, 1 + observation["queries"]
    member = None
    if construction is not None:
        from . import construct as _construct
        construction_remaining = max(0, _construct.CONSTRUCTION_CALL_CEILING
                                     - int((state or {}).get("construction_calls", 0)))
        if not construction_remaining:
            episode = {"disposition": "no-candidate", "fallback": "incumbent",
                       "fallback_reason": "construction call cap reached (4/trajectory)",
                       "task_id": task_id,
                       "queries": observation["queries"],
                       "diagnostic_observation": observation["observation_id"]}
            return observation, episode, 1 + observation["queries"]
        if state is not None and int(state.get("model_calls", 0)) \
                >= int(construction.get("model_cap", 60)):
            episode = {"disposition": "no-candidate",
                       "fallback": "incumbent",
                       "fallback_reason": "model call cap reached"
                                          " (%d/trajectory)"
                                          % int(construction.get(
                                              "model_cap", 60)),
                       "task_id": task_id,
                       "queries": observation["queries"],
                       "diagnostic_observation": observation["observation_id"]}
            return observation, episode, 1 + observation["queries"]
        if int(action.get("max_queries", 0)) <= 0:
            member = None
        else:
            try:
                construct_kwargs = {}
                if "study_root" in construction:
                    construct_kwargs["study_root"] = construction.get(
                        "study_root")
                member = _construct.construct_method(
                    construction["dsn"], campaign_id=construction["cid"],
                    task=worlds.load_task(worlds.FROZEN_DIR, target),
                    experience={**seen, "observations": [
                        *(seen.get("observations") or []), observation]},
                    budget={**construction.get("budget", {}),
                            "max_queries": action["max_queries"],
                            "model_calls": min(
                                seen["remaining"].get("model_calls", 60),
                                construction_remaining)},
                    gateway=construction["gateway"],
                    model=construction["model"], **construct_kwargs)
            except _construct.ConstructionFailed as exc:
                failed_task = worlds.load_task(worlds.FROZEN_DIR, target)
                episode = {"disposition": "rejected",
                           "reason": "construction failed: %s" % exc,
                           "task_id": task_id,
                           "lineage": [{"capability_id": "acquired-pending",
                                        "authored": False}],
                           "initial_size": _size(failed_task, failed_task)[0],
                           "queries": 0}
                if state is not None:
                    state["model_calls"] += exc.calls_made
                    state["construction_calls"] += exc.calls_made
                    state["dev_episodes"] += 1
                episode["construction_calls"] = exc.calls_made
                episode["queries"] = exc.queries + observation["queries"]
                return observation, episode, 1 + episode["queries"]
            if state is not None:
                state["model_calls"] = int(state.get("model_calls", 0)) \
                    + int(member["lineage"].get("calls_made", 0))
                state["construction_calls"] = int(
                    state.get("construction_calls", 0)) \
                    + int(member["lineage"].get("calls_made", 0))
    episode = dev_episode(
        target, _capability_for(target, capability_id),
        max_queries=int(action.get("max_queries",
                                   caps.get("diagnostic_queries", 16))),
        member=member,
        result=(member or {}).get("validation", {}).get("result"),
        authority=_dev_episode_authority(journal, boundary))
    episode["construction_calls"] = int(
        (member or {}).get("lineage", {}).get("calls_made", 0))
    episode["queries"] += observation["queries"]
    if member is not None and episode.get("disposition") == "retained" \
            and construction is not None and boundary is not None:
        release = bind_method_release(
            construction, member, observation, boundary=boundary,
            scope={"family": member["scope"]["family"]})
        episode["method_release"] = release
        if release.get("bound"):
            episode["method_release_id"] = release["release_id"]
        else:
            episode.setdefault("release_reason", release["reason"])
    if state is not None:
        state["dev_episodes"] = int(state.get("dev_episodes", 0)) + 1
    spend = 1 + episode.get("queries", 0)
    return observation, episode, spend


def _use_retained_method(action: dict, experience: dict, seed_obs: dict,
                         journal: dict | None, boundary: dict | None) -> tuple:
    import hashlib
    from .method_exec import MethodExecutionError
    target, method_id = action["task_id"], action["method_id"]
    member = next((m for m in experience.get("retained", [])
                   if m.get("capability_id") == method_id), None)
    episode = {"kind": "use_method", "task_id": target, "method_id": method_id,
               "construction_calls": 0, "queries": 0, "disposition": "refused"}
    if member is None or member.get("scope", {}).get("family") != _family(target):
        return seed_obs, {**episode, "reason": "no eligible retained method %r" % method_id}, 0
    source = member.get("method_source")
    if not isinstance(source, str) or hashlib.sha256(source.encode()).hexdigest() != member.get("source_digest"):
        return seed_obs, {**episode, "reason": "retained method bytes differ from source digest"}, 0
    task = worlds.load_task(worlds.FROZEN_DIR, target)
    budget = min(int(action.get("max_queries", 16)),
                 int(experience.get("remaining", {}).get("queries", 0)))
    if budget <= 0:
        return seed_obs, {**episode, "reason": "retained use query budget exhausted"}, 0
    authority = {}
    if journal and journal.get("dsn") and boundary is not None:
        authority = {"dsn": journal["dsn"], "allocation_id": _alloc_id(journal["cid"]),
                     "operation_id": _attempt_id(journal["cid"], boundary["seq"]) + "-use"}
    try:
        result = _run_member(member, task, max_queries=budget, **authority)
    except MethodExecutionError as exc:
        return seed_obs, {**episode, "reason": str(exc), "queries": budget,
                          "query_accounting": "upper-bound-on-failure"}, budget
    report = _check(task, result["candidate"])
    initial, final = _size(task, result["candidate"])
    episode = {**episode, "disposition": "used" if report["verdict"] == "preserved" else "rejected",
               "source_digest": member["source_digest"], "check": report,
               "initial_size": initial, "final_size": final, "queries": result["queries"],
               "operation_id": result.get("operation_id")}
    observation = {"observation_id": "obs-%s-%s-use" % (method_id, target),
                   "task_id": target, "capability_id": method_id,
                   "verdict": report["verdict"], "queries": result["queries"], "detail": report}
    return observation, episode, result["queries"]


def _policy_record_for_consumer(consumer) -> dict | None:
    source = getattr(consumer, "_policy_source", None)
    artifact = getattr(consumer, "_policy", None)
    if not isinstance(source, str) or not isinstance(artifact, dict):
        return None
    return {"artifact": dict(artifact), "policy_source": source}


def _persist_policy_refusal(dsn: str, proposal_id: str, outcome: str,
                            reason: str) -> dict:
    from settlement import store
    from settlement.common import Command, ResultCode
    record = {"proposal_id": proposal_id, "outcome": outcome,
              "reason": reason}
    result = store.transact(
        dsn, Command(request_id="s09-policy-refusal-%s" % proposal_id,
                     payload=record),
        lambda cur, control: (ResultCode.APPLIED, outcome, record, [], []))
    if result.code not in (ResultCode.APPLIED, ResultCode.ALREADY_APPLIED):
        raise ValueError("policy refusal not persisted: %s" % result.detail)
    return dict(result.data or record)


def _construct_policy_revision(investigation: dict, seen: dict, seed_obs: dict,
                               construction: dict | None, state: dict | None) -> tuple:
    import hashlib
    from . import (assessment_profile, construct, policy_assess, policy_step,
                   records, selection)
    target = investigation["next_action"]["task_id"]
    request = investigation["revision_proposal"]
    episode = {"kind": "policy_revision", "task_id": target, "queries": 0,
               "construction_calls": 0, "disposition": "refused",
               "fallback": "incumbent"}
    refs = list(investigation.get("basis_references") or [])
    feedback = {o["observation_id"]: o for o in seen["observations"]
                if o.get("verdict") not in (None, "unmeasured")
                and o.get("task_id") in _dev_task_ids()}
    if not refs or any(ref not in feedback for ref in refs):
        return seed_obs, {**episode, "reason": "revision needs attributable operational feedback"}, 0
    if construction is None:
        return seed_obs, {**episode, "reason": "revision needs configured policy construction"}, 0
    task = worlds.load_task(worlds.FROZEN_DIR, target)
    scope = {"family": task["family"]}
    if request.get("scope") and request["scope"] != scope:
        return seed_obs, {**episode, "reason": "revision scope differs from target family"}, 0
    remaining = min(2, int(seen["remaining"].get("model_calls", 0)),
                    construct.CONSTRUCTION_CALL_CEILING - int((state or {}).get("construction_calls", 0)))
    if remaining <= 0:
        return seed_obs, {**episode, "reason": "policy construction call budget exhausted"}, 0
    proposal = records.open_revision_proposal(
        construction["dsn"], investigation_id=construction["cid"],
        parent_digest=request["parent_digest"],
        failure_record={**feedback[refs[-1]], "parent_digest": request["parent_digest"]},
        scope=scope, protocol_id=policy_assess.PANEL_PROTOCOL,
        allocation_id=_alloc_id(construction["cid"]))
    episode["proposal_id"] = proposal["proposal_id"]
    try:
        candidate = construct.construct_policy(
            construction["dsn"], campaign_id=construction["cid"], task=task,
            experience=seen, budget={**construction["budget"], "model_calls": remaining},
            gateway=construction["gateway"], model=construction["model"],
            study_root=construction["study_root"], parent_digest=request["parent_digest"],
            applicability=scope)
    except construct.ConstructionFailed as exc:
        reason = "policy constructor unavailable: %s" % exc
        _persist_policy_refusal(construction["dsn"], proposal["proposal_id"],
                                "unavailable", reason)
        episode.update(disposition="unavailable", reason=reason,
                       assessment_status="unavailable",
                       construction_calls=exc.calls_made)
    else:
        freeze = records.freeze_candidate(
            construction["dsn"], proposal_id=proposal["proposal_id"],
            source_bytes=candidate["policy_source"], entry="STEP")
        episode.update(policy_candidate=candidate, freeze=freeze,
                       construction_calls=candidate["lineage"]["calls_made"])
        incumbent = construction.get("incumbent_policy")
        if incumbent is None:
            reason = "incumbent policy bytes unavailable for assessment"
            _persist_policy_refusal(construction["dsn"], proposal["proposal_id"],
                                    "unavailable", reason)
            episode.update(disposition="unavailable", reason=reason,
                           assessment_status="unavailable")
        else:
            panel = policy_assess.panel_for(
                scope=scope, world=construction["world"],
                seed=proposal["proposal_id"])
            rule = policy_assess.rule_for(resource_ceiling=16)
            protocol = policy_assess.freeze_protocol(
                construction["dsn"], proposal_id=proposal["proposal_id"],
                panel=panel, rule=rule)
            candidate_source = freeze["source"]
            candidate_record = policy_step.make_policy_artifact(
                candidate_source,
                origin=(candidate.get("policy_artifact") or {}).get(
                    "origin") or "fixture-stand-in",
                parent_digest=proposal["parent_digest"],
                applicability=scope)
            policy_step.verify_policy_record(candidate_record)
            incumbent_source = incumbent["policy_source"]
            incumbent_record = dict(incumbent)
            incumbent_digest = hashlib.sha256(
                incumbent_source.encode("utf-8")).hexdigest()
            assessment = assessment_profile.assess_policy(
                construction["dsn"], proposal_id=proposal["proposal_id"],
                candidate_source=candidate_source,
                candidate_digest=freeze["candidate_digest"],
                candidate_artifact=candidate_record,
                incumbent_source=incumbent_source,
                incumbent_digest=incumbent_digest,
                incumbent_artifact=incumbent_record,
                panel=panel, rule=rule, scope=scope,
                protocol_id=policy_assess.PANEL_PROTOCOL,
                evaluator_version=policy_assess.EVALUATOR_VERSION,
                gateway=construction["gateway"],
                allocation_id=_alloc_id(construction["cid"]),
                model=construction["model"])
            stored = records.load_assessment(
                construction["dsn"], proposal["proposal_id"],
                freeze["candidate_digest"])
            if stored is None:
                raise ValueError("policy assessment was not durably journaled")
            assessment = stored
            resources = [dict(assessment["arms"][name]["resources"])
                         for name in ("candidate", "incumbent")]
            assessment_queries = sum(r["queries"] for r in resources)
            assessment_model_calls = sum(r["model_calls"] for r in resources)
            episode.update(assessment=assessment, assessment_status="complete",
                           assessment_queries=assessment_queries,
                           assessment_model_calls=assessment_model_calls,
                           queries=assessment_queries)
            if assessment["outcome"] == "bind":
                release_id = "ad01-%s-policy-%s" % (
                    construction["cid"], freeze["candidate_digest"][:12])
                current = selection.active_binding_for(
                    construction["dsn"], scope["family"],
                    release_id=release_id)
                expected = list(current["versions"]) if current else None
                version_id = candidate["capability_id"]
                try:
                    bound = selection.bind_revision(
                        construction["dsn"], release_id=release_id,
                        versions=[version_id], scope=scope,
                        disposition="default", fallback="incumbent",
                        expected_versions=expected,
                        policy_version=policy_step.POLICY_STEP_VERSION,
                        protocol_id=proposal["protocol_id"],
                        evaluator_version=policy_assess.EVALUATOR_VERSION,
                        evidence_refs=[assessment["attempt_id"]],
                        proposal_id=proposal["proposal_id"],
                        candidate_digest=freeze["candidate_digest"])
                except selection.StaleBind as exc:
                    episode.update(disposition="rejected", reason=str(exc),
                                   fallback="incumbent")
                else:
                    episode.update(disposition="bound", release_id=release_id,
                                   bound_digest=freeze["candidate_digest"],
                                   scope=dict(scope),
                                   binding={"release_id": release_id,
                                            "versions": [version_id]},
                                   fallback="incumbent")
            elif assessment["outcome"] == "reject":
                episode.update(disposition="rejected",
                               reason=assessment.get("reason", ""),
                               fallback="incumbent")
            elif assessment["outcome"] == "unavailable":
                episode.update(disposition="unavailable",
                               reason=assessment.get("reason", ""),
                               fallback="incumbent")
            else:
                raise ValueError("unknown policy assessment outcome %r" %
                                 assessment["outcome"])
    if state is not None:
        state["model_calls"] += episode["construction_calls"] \
            + int(episode.get("assessment_model_calls", 0))
        state["construction_calls"] += episode["construction_calls"]
    observation = {"observation_id": "obs-" + proposal["proposal_id"],
                   "task_id": target, "verdict": episode["disposition"],
                   "queries": episode.get("queries", 0),
                   "detail": {"proposal_id": proposal["proposal_id"],
                              "kind": "policy_revision",
                              "reason": _disposition_reason(episode)}}
    return observation, episode, int(episode.get("queries", 0))


def _disposition_reason(episode: dict) -> str:
    """Why this episode reached its disposition, in words.

    A refusal always has one, and it is kept verbatim. `bound` is the
    disposition that has none - nothing was refused, the assessment
    came back `bind` and the durable binding took - and projecting it as
    `""` writes a recorded outcome with no stated reason, which is the
    one thing an auditor cannot act on: an empty string cannot be
    distinguished from a reason that was meant and lost. The archived
    `invl02-r123` run carries exactly that shape, so it is a shape this
    code has already produced.

    The reason for a binding is therefore the binding itself, named. This
    says nothing about whether the bound bytes can execute; a reason
    states what was decided, and a verdict that carries none of its own
    is not auditable whether or not its program runs.
    """
    reason = episode.get("reason")
    if reason:
        return str(reason)
    disposition = str(episode.get("disposition") or "")
    if disposition == "bound":
        return ("bound: assessment outcome was bind and the durable "
                "binding took under release %r"
                % (episode.get("release_id", ""),))
    return disposition or "no disposition recorded"


def _frozen_policy_origin(dsn: str, candidate_digest: str,
                          source: str) -> str | None:
    """Re-earn the origin of frozen bytes instead of re-reading a label.

    A freeze stores source and digest, never an origin, so a replay that
    wanted to call these bytes `model-acquired` had to write the string. It
    now looks up the operation whose settled response parses to exactly these
    bytes and re-derives the origin from that receipt, so a replay of a
    fixture-served release labels it `fixture-stand-in` and a replay with no
    receipt at all is refused rather than asserted.
    """
    from . import live_construct
    operation_id = live_construct.find_acquisition_operation(
        dsn, candidate_digest)
    if operation_id is None:
        return None
    from . import construct
    return construct.acquisition_origin(dsn, operation_id, source)[
        "origin"]


def _resolve_policy_consumer(dsn: str, release_id: str, family: str, *,
                             cid: str, charter: dict, world: int, arm: str,
                             study_root: str, gateway, model: str):
    import hashlib
    from . import agenda_policy, policy_step, records, selection
    binding = selection.active_binding_for(dsn, family,
                                           release_id=release_id)
    if binding is None:
        return None, "no active policy binding for release %r (family %s)" % (
            release_id, family)
    provenance = selection.binding_provenance(binding)
    proposal_id = provenance.get("proposal_id")
    candidate_digest = provenance.get("candidate_digest")
    freeze = records.load_freeze(dsn, proposal_id) if proposal_id else None
    if freeze is None:
        return None, "policy release %r has no frozen candidate" % release_id
    if freeze.get("candidate_digest") != candidate_digest:
        return None, "policy release %r provenance digest differs from frozen candidate" % release_id
    source = freeze.get("source")
    if not isinstance(source, str) or hashlib.sha256(
            source.encode("utf-8")).hexdigest() != candidate_digest:
        return None, "policy release %r frozen bytes do not match provenance" % release_id
    proposal = records.load_revision_proposal(dsn, proposal_id)
    if proposal is None:
        return None, "policy release %r has no revision proposal" % release_id
    origin = _frozen_policy_origin(dsn, candidate_digest, source)
    if origin is None:
        return None, (
            "policy release %r refused: no settled construction operation "
            "produced its frozen bytes, so the origin is unknown" % release_id)
    try:
        record = policy_step.make_policy_artifact(
            source, origin=origin,
            parent_digest=proposal.get("parent_digest"),
            applicability=dict(proposal.get("scope") or {}))
        policy_step.verify_policy_record(record)
    except (ValueError, LookupError) as exc:
        return None, "policy release %r refused: %s" % (release_id, exc)
    return agenda_policy.step_policy_consumer(
        record, dsn=dsn, cid=cid, charter=charter, world=world, arm=arm,
        allocation_id=_alloc_id(cid), study_root=study_root, gateway=gateway,
        model=model), None


def _activate_bound_policy(episode: dict, consumer, construction: dict | None,
                           *, dsn: str | None, cid: str, charter: dict,
                           world: int, arm: str, study_root: str,
                           gateway, model: str):
    if episode.get("disposition") != "bound" or dsn is None:
        return consumer
    resolved, refusal = _resolve_policy_consumer(
        dsn, episode["release_id"], episode["scope"]["family"], cid=cid,
        charter=charter, world=world, arm=arm, study_root=study_root,
        gateway=gateway, model=model)
    if refusal is not None:
        raise ValueError("bound policy could not be activated: %s" % refusal)
    if construction is not None:
        construction["incumbent_policy"] = _policy_record_for_consumer(resolved)
    return resolved


def _default_tasks(world: int, arm: str = "I") -> list:
    if arm == "R":
        from . import rotation
        return [s["task_id"] for s in rotation.r_schedule(world)]
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    dev = membership[str(world)]["dev"]
    return ["ad01-w%d-dev-sw-%02d" % (world, i) for i in range(3)
            if "ad01-w%d-dev-sw-%02d" % (world, i) in dev["software"]]


def _publish_boundary(dsn: str, cid: str, seq: int, task_id: str,
                      decision: dict, observation: dict, episode: dict,
                      spend: int) -> int:
    from settlement import store
    from settlement.common import Command, SettlementError
    aid = _attempt_id(cid, seq)
    if decision is None:
        store.acquire_work(
            dsn, Command(request_id="acquire-%s" % aid,
                         payload={"investigation_id": cid, "attempt_id": aid,
                                  "allocation_id": _alloc_id(cid),
                                  "composition": "ad01-boundary", "owner": cid}))
    # The backward half of the effect -> observation arrow. This row already
    # carried `seq`, `task_id` and `observation_id`, which is what let a reader
    # bind the two sides by `(investigation_id, seq)` alone. It now carries the
    # identity of the operation that produced the effect, so the row answers
    # "which operation produced this observation" on its own.
    #
    # Read back from `s09_policy_state` rather than derived a second time, and
    # empty when that row admits no operation, so this value and the effect row
    # cannot disagree. A boundary that admitted no operation leaves both empty
    # rather than one of them naming something.
    effect_id = _s09_effect_id(dsn, cid, seq) or \
        _effect_operation_id(dsn, cid, episode)
    made = store.submit_observation(
        dsn, Command(request_id="settle-%s" % aid,
                     payload={"attempt_id": aid,
                              "content": {"kind": "boundary", "seq": seq,
                                          "task_id": task_id,
                                          "decision": decision,
                                          "observation": observation,
                                          "observation_id": observation[
                                              "observation_id"],
                                          "operation_id": effect_id,
                                          "episode": episode,
                                          "spend": spend}}))
    if made.data["attempt_id"] != aid:
        raise SettlementError(
            "store returned boundary for unexpected attempt %r" % (
                made.data.get("attempt_id"),))
    return aid


def run_campaign(world: int, arm: str, charter: dict, caps: dict,
                 tasks: list | None = None,
                 capability_id: str = "seed-sw-greedy",
                 campaign_seq: int = 0, dsn: str | None = None,
                 propose=None, gateway=None, model: str = "",
                 constructor: str = "seed", consumer=None,
                 study_root: str | None = None,
                 policy_release: str | None = None) -> dict:
    cid = campaign_id(world, arm, campaign_seq)
    study_root = study_root or cid
    if consumer is not None and policy_release is not None:
        raise ValueError("consumer and policy_release are mutually exclusive")
    if policy_release is not None and dsn is None:
        raise ValueError("policy release resolution needs a settlement store")
    if gateway is not None and dsn is None:
        raise ValueError("a gateway needs a dsn for broker operations")
    if constructor == "model" and (dsn is None or gateway is None):
        raise ValueError("model construction needs a dsn and a gateway")
    if dsn is not None:
        tasks = ensure_campaign(dsn, cid, world, arm, charter, caps,
                                tasks=tasks,
                                study_root=study_root)["tasks"]
        settled, pending = _read_campaign(dsn, cid)
    else:
        tasks = _default_tasks(world, arm) if tasks is None else tasks
        _check_tasks(tasks)
        settled, pending = {}, {}
    if consumer is None and policy_release is not None:
        family = _family(tasks[0]) if tasks else ""
        consumer, refusal = _resolve_policy_consumer(
            dsn, policy_release, family, cid=cid, charter=charter,
            world=world, arm=arm, study_root=study_root, gateway=gateway,
            model=model)
        if refusal is not None:
            return {"campaign_id": cid, "world": world, "arm": arm,
                    "charter": charter.get("objective", ""),
                    "boundaries": [], "episodes": [],
                    "stop": {"reason": refusal}, "queries": 0,
                    "dev_episodes": 0, "model_calls": 0,
                    "construction_calls": 0, "study_root": study_root}
    experience: dict = {"observations": [], "retained": []}
    boundaries, episodes = [], []
    queries = 0
    state = {"dev_episodes": 0, "model_calls": 0,
             "construction_calls": 0}
    construction = None
    if constructor == "model":
        construction = {"dsn": dsn, "cid": cid, "gateway": gateway,
                        "model": model, "study_root": study_root,
                        "world": world, "arm": arm,
                        "incumbent_policy": _policy_record_for_consumer(consumer),
                        "model_cap": int(caps.get("model_calls", 60)),
                        "budget": {"max_output_tokens": int(
                            caps.get("construction_tokens", 2048))}}
    stop = {"reason": "no admissible work remains"}
    for seq, task_id in enumerate(tasks):
        if seq >= int(caps.get("max_boundaries", 6)):
            stop = {"reason": "boundary cap reached"}
            break
        if queries >= int(caps.get("diagnostic_queries", 16)):
            stop = {"reason": "diagnostic query cap reached"}
            break
        if dsn is not None and seq not in settled:
            ops = [op for op in _campaign_operations(dsn, cid)
                   if not (op["effect"] == "model-inference"
                           and "-construct-" in op["id"]
                           and op["id"].startswith("ad01-%s-b%d-" % (cid, seq)))]
            state["model_calls"] = sum(op["effect"] == "model-inference"
                                       for op in ops)
            state["construction_calls"] = sum(
                op["effect"] == "model-inference" and "-construct-" in op["id"]
                for op in ops)
            if state["model_calls"] >= int(caps.get("model_calls", 60)) \
                    and propose is not None:
                stop = {"reason": "model call cap reached"}
                break
        experience["remaining"] = {
            "queries": int(caps.get("diagnostic_queries", 16)) - queries,
            "boundaries": int(caps.get("max_boundaries", 6)) - seq,
            "dev_episodes": DEV_EPISODE_CAP - state["dev_episodes"],
            "model_calls": int(caps.get("model_calls", 60))
            - state["model_calls"]}
        decision = None
        if seq in settled:
            old = settled[seq]
            if dsn is not None:
                admitted = mission_held(dsn, cid, seq)
                _s09_incorporate(
                    dsn, cid, seq, decision=old["decision"],
                    observation=old["observation"], episode=old["episode"],
                    spend=int(old["spend"]), provenance="s09-m1",
                    effect_record=(
                        _effect_record_for(
                            old["decision"], old["observation"],
                            old["episode"], int(old["spend"]), admitted)
                        if admitted is not None else None))
                _s09_release(dsn, cid, seq)
            queries += int(old["spend"])
            if old["episode"].get("kind", "development") == "development" \
                    and old["episode"]["disposition"] in (
                        "retained", "rejected"):
                state["dev_episodes"] += 1
            state["model_calls"] += int(
                old["episode"].get("construction_calls", 0))
            state["construction_calls"] += int(
                old["episode"].get("construction_calls", 0))
            if old["episode"].get("disposition") == "retained" \
                    and isinstance(old["episode"].get("executable"),
                                   dict):
                experience["retained"].append(
                    old["episode"]["executable"])
            experience["observations"].append(old["observation"])
            episodes.append(old["episode"])
            boundaries.append({"seq": seq, "task_id": old["task_id"],
                               "decision": old["decision"],
                               "decision_id": old["row_id"],
                               "observation_id": old["observation_id"],
                               "spend": old["spend"], "resumed": True})
            continue
        if dsn is not None:
            s09row = _s09_get(dsn, cid, seq)
            pend = pending.get(seq, {}).get("decision")
            pending_step = s09row is not None and dict(
                s09row["accepted_action"] or {}).get("status") == "pending"
            if pending_step and consumer is None:
                raise ValueError("pending STEP requires a policy consumer")
            if (s09row is not None or pend is not None) and not pending_step:
                if s09row is None:
                    _s09_accept(
                        dsn, cid, seq, decision=pend, provenance="legacy-drain",
                        driver_version="s09-m1")
                    s09row = _s09_get(dsn, cid, seq)
                routed = _capability_for(task_id, capability_id)
                seed_obs = {"observation_id": "obs-%s-seed" % task_id,
                            "task_id": task_id, "capability_id": routed,
                            "verdict": "unmeasured"}
                observation, episode, spend, decision = execute_pending(
                    dsn, cid, seq, task_id=task_id,
                    capability_id=routed, caps=caps,
                    seed_obs=seed_obs, charter=charter,
                    boundary={"world": world, "arm": arm, "seq": seq},
                    experience=experience, state=state,
                    construction=construction, study_root=study_root)
                if observation is None:
                    _s09_release(dsn, cid, seq)
                    stop = {"reason": "learner stop"}
                    break
                executed = episode.get("task_id", task_id)
                queries += spend
                if episode.get("disposition") == "retained" \
                        and isinstance(episode.get("executable"), dict):
                    experience["retained"].append(episode["executable"])
                observation = {**observation, "task_id": executed,
                               "capability_id": _capability_for(
                                   executed, routed)}
                experience["observations"].append(observation)
                episodes.append(episode)
                consumer = _activate_bound_policy(
                    episode, consumer, construction, dsn=dsn, cid=cid,
                    charter=charter, world=world, arm=arm,
                    study_root=study_root, gateway=gateway, model=model)
                entry = {"seq": seq, "task_id": executed,
                         "decision": decision,
                         "observation_id": observation["observation_id"],
                         "spend": spend}
                entry["decision_id"] = _publish_boundary(
                    dsn, cid, seq, executed, decision, observation,
                    episode, spend)
                boundaries.append(entry)
                _s09_release(dsn, cid, seq)
                continue
        routed = _capability_for(task_id, capability_id)
        seed_obs = {"observation_id": "obs-%s-seed" % task_id,
                    "task_id": task_id, "capability_id": routed,
                    "verdict": "unmeasured"}
        journal = {"dsn": dsn, "cid": cid, "decision": None}
        observation, episode, spend = _run_boundary(
            task_id, routed, caps, seed_obs, propose=propose,
            charter=charter,
            boundary={"world": world, "arm": arm, "seq": seq},
            experience=experience, state=state,
            construction=construction, journal=journal,
            accepted=pending.get(seq, {}).get("decision"),
            consumer=consumer, study_root=study_root)
        decision = journal["decision"]
        if observation is None:
            stop = {"reason": "learner stop"}
            break
        executed = episode.get("task_id", task_id)
        queries += spend
        if episode.get("disposition") == "retained" \
                and isinstance(episode.get("executable"), dict):
            experience["retained"].append(episode["executable"])
        observation = {**observation, "task_id": executed,
                       "capability_id": _capability_for(executed, routed)}
        experience["observations"].append(observation)
        episodes.append(episode)
        consumer = _activate_bound_policy(
            episode, consumer, construction, dsn=dsn, cid=cid,
            charter=charter, world=world, arm=arm,
            study_root=study_root, gateway=gateway, model=model)
        entry = {"seq": seq, "task_id": executed,
                 "decision": decision,
                 "observation_id": observation["observation_id"],
                 "spend": spend}
        if dsn is not None:
            entry["decision_id"] = _publish_boundary(
                dsn, cid, seq, executed, decision, observation,
                episode, spend)
            admitted = mission_held(dsn, cid, seq)
            _s09_incorporate(
                dsn, cid, seq, decision=decision, observation=observation,
                episode=episode, spend=spend, provenance="s09-m1",
                effect_record=(
                    _effect_record_for(decision, observation, episode,
                                       spend, admitted)
                    if admitted is not None else None))
            _s09_release(dsn, cid, seq)
        boundaries.append(entry)
    else:
        stop = {"reason": "no admissible work remains"}
    return {"campaign_id": cid, "world": world, "arm": arm,
            "charter": charter.get("objective", ""),
            "boundaries": boundaries, "episodes": episodes,
            "stop": stop, "queries": queries,
            "dev_episodes": state["dev_episodes"],
            "model_calls": state["model_calls"],
            "construction_calls": state["construction_calls"],
            "study_root": study_root}


def freeze_repertoire(campaign: dict, path) -> dict:
    import json
    from pathlib import Path
    members = [e["executable"] for e in campaign.get("episodes", [])
               if e.get("disposition") == "retained"
               and isinstance(e.get("executable"), dict)]
    repertoire = {"campaign_id": campaign["campaign_id"],
                  "queries": int(campaign.get("queries", 0)),
                  "members": members}
    Path(path).write_text(json.dumps(repertoire, sort_keys=True,
                                     indent=2) + "\n")
    return repertoire


def load_repertoire(path) -> dict:
    import hashlib
    import json
    from pathlib import Path
    repertoire = json.loads(Path(path).read_text())
    if not isinstance(repertoire.get("members"), list):
        raise ValueError("repertoire holds no member list")
    repertoire.setdefault("queries", 0)
    for member in repertoire["members"]:
        if isinstance(member, dict) and member.get("authored") is False:
            source = member.get("method_source", "")
            if not isinstance(source, str) or not source.strip():
                raise ValueError(
                    "acquired member %r carries no executable bytes" % (
                        member.get("capability_id"),))
            if member.get("source_digest") != hashlib.sha256(
                    source.encode("utf-8")).hexdigest():
                raise ValueError(
                    "acquired member %r bytes do not match their digest" % (
                        member.get("capability_id"),))
            if member.get("capability_id") in seeds._KNOWN:
                raise ValueError(
                    "acquired member %r claims a reserved seed capability id" % (
                        member.get("capability_id"),))
    return repertoire


def _run_member(member: dict, task: dict, *,
                 max_queries: int | None = None,
                 timeout_ms: int | None = None,
                 dsn: str | None = None,
                 allocation_id: str | None = None,
                 operation_id: str | None = None) -> dict:
    known = [c for c in seeds.SEED_CAPABILITIES
             if c["capability_id"] == member["capability_id"]]
    budgeted = int(member.get("params", {}).get("max_queries", 16))
    if max_queries is not None:
        budgeted = min(budgeted, int(max_queries))
    if known:
        result = seeds.run_seed(known[0], task, max_queries=budgeted)
        result["executed_source"] = known[0]["method"]
        # The host's own dispatch table ran this, in this process, with no
        # oracle channel to observe. The control arm is routed around this
        # branch by its `ctl-` ids so the trace it is compared on is
        # measured rather than absent, and a member that does reach here
        # says so rather than reporting an empty walk it did not take.
        result["query_trace"] = None
        return result
    from . import method_exec
    result = method_exec.run_member_out_of_process(
        member, task, max_queries=budgeted, dsn=dsn,
        allocation_id=allocation_id, operation_id=operation_id,
        **({} if timeout_ms is None else {"timeout_ms": timeout_ms}))
    result["executed_source"] = member["method_source"]
    return result


class _UsePolicyRefused(Exception):
    """Never downgraded to a method fallback."""

    def __init__(self, reason: str, *, operation_ids: list | None = None):
        super().__init__(reason)
        self.operation_ids = list(operation_ids or [])


def _use_policy_action(policy, view: dict, state: dict, *,
                       policy_record: dict | None = None,
                       execution: dict | None = None) -> dict:
    """The method identity lives in the admitted action, not in the
    repertoire, so an episode with no action in hand is not one this can
    build. No path out of here supplies a method of its own. A policy that
    raises or returns an action the STEP ABI rejects is a refusal here,
    not an exception out of the use phase: a broken policy must not abort
    an episode the way a missing one must not substitute a method.
    """
    from . import policy_step
    source_record = policy_record
    if source_record is None and isinstance(policy, policy_step.BoundedPolicy):
        source_record = policy.record
    if source_record is not None:
        try:
            stepped = policy_step.run_policy_step(
                source_record, view, state, **(execution or {}))
        except Exception as exc:
            operation_ids = []
            operation_id = getattr(exc, "operation_id", None)
            if operation_id and getattr(exc, "operation_current", False):
                operation_ids = [operation_id]
            raise _UsePolicyRefused(
                "policy raised: %s" % exc,
                operation_ids=operation_ids) from exc
        action = stepped["action"]
    elif policy is None:
        raise _UsePolicyRefused("use ran with no policy: the method identity"
                                " must come from an admitted policy action")
    elif hasattr(policy, "decide"):
        decision = _call(policy.decide, {
            "observations": [{"task_id": view["task_content"]["task_id"]}]},
            state, boundary={"seq": 0}, experience={})
        if not isinstance(decision, dict) \
                or decision.get("status") == "refused":
            raise _UsePolicyRefused("policy refused: %s"
                                    % (decision or {}).get("reason", ""))
        action = decision.get("action")
    else:
        action = _call(policy, view, state)
        if isinstance(action, dict) and "action" in action:
            action = action["action"]
    try:
        return policy_step.validate_action(action)
    except (TypeError, ValueError) as invalid:
        raise _UsePolicyRefused("policy admitted no valid action: %s"
                                % invalid) from invalid


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        raise _UsePolicyRefused("policy raised: %s" % exc) from exc


def _use_admitted_method(action: dict) -> str:
    """A policy admitting a kind that runs no method, or naming no member,
    gets a refusal rather than a substitution the policy never asked for.
    """
    if action.get("kind") != "use_method":
        raise _UsePolicyRefused(
            "admitted %r action runs no task method" % (action.get("kind"),))
    inputs = action.get("inputs")
    method_id = inputs.get("method_id") if isinstance(inputs, dict) else None
    if not isinstance(method_id, str) or not method_id:
        raise _UsePolicyRefused("admitted use_method names no method")
    return method_id


def _member_digest(member: dict) -> str:
    import hashlib

    return str(member.get("source_digest") or hashlib.sha256(
        str(member.get("method_source") or "").encode("utf-8")).hexdigest())


def _use_governed_member(repertoire: dict, task: dict, policy, *,
                         dsn: str | None,
                         allocation_id: str | None,
                         release_id: str | None,
                         policy_record: dict | None = None) -> tuple:
    from . import policy_step
    view = policy_step.materialize_view(
        task=task, observations=[], open_questions=[], last_result=None,
        eligible_methods=[m.get("capability_id")
                          for m in repertoire.get("members", [])],
        remaining={})
    policy_operation_id = None
    policy_operation_admitted = False
    execution = None
    if policy_record is not None and dsn is not None:
        import hashlib
        authority_digest = hashlib.sha256(
            str(allocation_id).encode("utf-8")).hexdigest()[:12]
        policy_operation_id = _versioned_use_op_id(
            repertoire["campaign_id"], task["task_id"],
            "policy-%s-%s" % (
                policy_record["artifact"]["source_digest"][:16],
                authority_digest))
        execution = {"dsn": dsn, "allocation_id": allocation_id,
                     "operation_id": policy_operation_id}
    try:
        action = _use_policy_action(
            policy, view, {}, policy_record=policy_record,
            execution=execution)
        policy_operation_admitted = bool(policy_operation_id)
        method_id = _use_admitted_method(action)
        member = next((m for m in repertoire.get("members", [])
                       if m.get("capability_id") == method_id), None)
        if member is None:
            raise _UsePolicyRefused(
                "admitted %r is absent from the repertoire" % (method_id,))
        if (member.get("scope", {}) or {}).get("family") != task.get("family"):
            raise _UsePolicyRefused(
                "admitted %r is scoped to %r and cannot answer a %s task"
                % (method_id, (member.get("scope") or {}).get("family"),
                   task.get("family")))
        if not _select_member({"members": [member]}, task, dsn=dsn,
                              release_id=release_id):
            raise _UsePolicyRefused(
                "release %r pins bytes %s, which repertoire member %r does not"
                " carry" % (release_id, _member_digest(member)[:12], method_id))
        inputs = action.get("inputs") or {}
        max_queries = inputs.get("max_queries")
        if type(max_queries) is not int or max_queries < 0:
            raise _UsePolicyRefused(
                "admitted use_method carries no query budget")
    except _UsePolicyRefused as refusal:
        if policy_operation_admitted and policy_operation_id \
                and policy_operation_id not in refusal.operation_ids:
                refusal.operation_ids.insert(0, policy_operation_id)
        raise
    policy_operation_ids = []
    if policy_operation_admitted:
        policy_operation_ids = [policy_operation_id]
    return dict(member), max_queries, policy_operation_ids


def _policy_refused_record(repertoire: dict, world: int, arm: str,
                           task_id: str, domain: str, release_id, reason: str,
                           *, operation_ids: list | None = None,
                           policy_source_digest: str | None = None) -> dict:
    """A distinct `status` is the point. `selected` and `executed` both
    read `refused`, so a caller that branches on those alone cannot read
    this as the incumbent an empty repertoire also produces.
    """
    from . import checker
    return {
        "record_id": "%s-%s-%s" % (repertoire["campaign_id"], arm, task_id),
        "world": world, "arm": arm, "task_id": task_id, "domain": domain,
        "freeze": worlds.FREEZE_ID,
        "freeze_digest": checker.freeze_digest(worlds.FROZEN_DIR),
        "release_id": release_id,
        "policy_source_digest": policy_source_digest,
        "status": "refused",
        "verdict": "refused",
        "initial_measure": 0, "final_measure": 0,
        "normalized_reduction": 0.0, "output": {},
        "operation_ids": list(operation_ids or []),
        "costs": {"witness_queries": 0},
        "requested": "refused", "selected": "refused", "executed": "refused",
        "executed_source": "refused", "query_trace": None,
        "fallback_reason": reason,
    }


def _member_refused_record(repertoire: dict, world: int, arm: str,
                           task_id: str, domain: str, release_id,
                           reason: str, *, requested: str, selected: str,
                           operation_ids: list | None = None,
                           policy_source_digest: str | None = None,
                           base_costs: dict | None = None) -> dict:
    """An execution that refused, recorded as a refusal and not as a run.

    `_policy_refused_record` is the shape for a use that never reached a
    method. This is the other refusal: the method was admitted and named,
    and then the executor refused it. `requested` and `selected` name that
    admitted method, because they were real decisions, but `executed` and
    `executed_source` read `refused` because no verified method result exists. `operation_ids`
    keeps what it found: the refusal can follow a durable operation the
    current authority owns, and dropping it would lose the receipt of work
    that did happen.
    """
    from . import checker
    return {
        "record_id": "%s-%s-%s" % (repertoire["campaign_id"], arm, task_id),
        "world": world, "arm": arm, "task_id": task_id, "domain": domain,
        "freeze": worlds.FREEZE_ID,
        "freeze_digest": checker.freeze_digest(worlds.FROZEN_DIR),
        "release_id": release_id,
        "policy_source_digest": policy_source_digest,
        "status": "refused",
        "verdict": "refused",
        "initial_measure": 0, "final_measure": 0,
        "normalized_reduction": 0.0, "output": {},
        "operation_ids": list(operation_ids or []),
        "costs": {**(base_costs or {}), "witness_queries": 0},
        "requested": requested, "selected": selected,
        "executed": "refused", "executed_source": "refused",
        "query_trace": None,
        "fallback_reason": reason,
    }


def _incumbent_baseline(task: dict) -> dict:
    """The incumbent, measured under its own name.

    Declared separately so that wanting the fallback does not mean scoring
    it. This is the same computation the incumbent arm of the study makes,
    so a reader who wants the fallback reads the same numbers that arm would
    have recorded, and a reader who wants the admitted method reads a
    refusal in `executed` rather than this. It costs no query and runs no
    method, so it carries no cost of its own.
    """
    output = controls.incumbent(task)
    report = _check(task, output)
    initial, final = _size(task, output)
    return {"executed": "incumbent", "executed_source": "incumbent",
            "verdict": report["verdict"], "initial_measure": initial,
            "final_measure": final, "normalized_reduction": 0.0,
            "output": output}


def run_use(repertoire: dict, world: int, arm: str, use_tasks: list,
            base_costs: dict, *, policy=None, policy_source: str | None = None,
            policy_origin: str = "authored-control",
            dsn: str | None = None,
            allocation_id: str | None = None,
            release_id: str | None = None) -> list:
    from . import checker
    from . import policy_step
    if policy is not None and policy_source is not None:
        raise ValueError("use accepts policy or policy_source, not both")
    policy_record = None
    if policy_source is not None:
        policy_record = policy_step.make_policy_artifact(
            policy_source, origin=policy_origin)
        policy_step.verify_policy_record(policy_record)
    elif isinstance(policy, policy_step.BoundedPolicy):
        policy_record = policy.record
    if dsn is not None and not allocation_id:
        raise ValueError("use requires explicit execution allocation")
    if dsn is None and release_id is not None:
        raise ValueError("use cannot resolve release %r without a store"
                         % (release_id,))
    _check_tasks(list(use_tasks))
    records = []
    for task_id in use_tasks:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        domain = task["family"]
        try:
            member, method_queries, policy_operation_ids = \
                _use_governed_member(
                    repertoire, task, policy, dsn=dsn,
                    allocation_id=allocation_id, release_id=release_id,
                    policy_record=policy_record)
        except _UsePolicyRefused as refusal:
            records.append(_policy_refused_record(
                repertoire, world, arm, task_id, domain, release_id,
                str(refusal), operation_ids=refusal.operation_ids,
                policy_source_digest=(policy_record or {}).get(
                    "artifact", {}).get("source_digest")))
            continue
        operation_ids = list(policy_operation_ids)
        execution = None
        if dsn is not None:
            execution = {"dsn": dsn, "allocation_id": allocation_id,
                         "operation_id": _versioned_use_op_id(
                             repertoire["campaign_id"], task_id,
                             member["capability_id"])}
        requested = selected = member["capability_id"]
        from .method_exec import MethodExecutionError
        try:
            result = _run_member(member, task, max_queries=method_queries,
                                 **(execution or {}))
        except MethodExecutionError as exc:
            if execution and getattr(exc, "operation_current", False) \
                    and execution["operation_id"] not in operation_ids:
                operation_ids.append(execution["operation_id"])
            refusal = _member_refused_record(
                repertoire, world, arm, task_id, domain, release_id,
                "member execution failed: %s" % exc,
                requested=requested, selected=selected,
                operation_ids=operation_ids,
                policy_source_digest=(policy_record or {}).get(
                    "artifact", {}).get("source_digest"),
                base_costs=base_costs)
            # The incumbent still ran, and it is recorded as itself rather
            # than as the admitted method. It is a separately declared record
            # under `incumbent_baseline`, so a reader of `executed` sees a
            # refusal and a reader who wants the fallback reads that field.
            # It was never the answer to the use that was admitted, so scoring
            # it as one would put a measurement nobody made in its place.
            refusal["incumbent_baseline"] = _incumbent_baseline(task)
            records.append(refusal)
            continue
        output = result["candidate"]
        queries = result["queries"]
        reason = ""
        operation_ids.extend(result.get("operation_ids") or [])
        executed_source = result.get("executed_source")
        report = _check(task, output)
        initial, final = _size(task, output)
        records.append({
            "record_id": "%s-%s-%s" % (repertoire["campaign_id"], arm,
                                       task_id),
            "world": world, "arm": arm, "task_id": task_id,
            "domain": domain, "freeze": worlds.FREEZE_ID,
            "freeze_digest": checker.freeze_digest(worlds.FROZEN_DIR),
            "release_id": release_id,
            "policy_source_digest": (policy_record or {}).get(
                "artifact", {}).get("source_digest"),
            "verdict": report["verdict"],
            "initial_measure": initial, "final_measure": final,
            "normalized_reduction": ((initial - final) / initial
                                     if report["verdict"] == "preserved"
                                     else 0.0),
            "output": output, "operation_ids": operation_ids,
            "costs": {**base_costs, "witness_queries": queries},
            "requested": requested, "selected": selected,
            "executed": selected, "executed_source": executed_source,
            "query_trace": result.get("query_trace"),
            "fallback_reason": reason})
    if dsn is not None:
        for record in records:
            record["costs"] = cost_union(repertoire, [record], dsn=dsn)["use"]
    return records


def cost_union(campaign: dict, use_records: list, *, dsn: str | None = None) -> dict:
    acquisition_ids = set(campaign.get("operation_ids", []))
    if dsn:
        acquisition_ids.update(op["id"] for op in
                               _campaign_operations(dsn, campaign["campaign_id"])
                               if not op["id"].startswith("ad01-%s-use-" % campaign["campaign_id"]))
    use_ids = {op for record in use_records
               for op in record.get("operation_ids", [])}
    operations = {}
    if acquisition_ids | use_ids:
        if not dsn:
            raise ValueError("operation accounting requires a settlement store")
        with _read_conn(dsn) as conn:
            for op_id in sorted(acquisition_ids | use_ids):
                row = conn.execute("SELECT payload FROM operations WHERE id = %s",
                                   (op_id,)).fetchone()
                if row is None:
                    raise ValueError("missing durable operation %s" % op_id)
                receipts = conn.execute(
                    "SELECT content FROM receipts WHERE operation_id = %s"
                    " ORDER BY receipt_identity", (op_id,)).fetchall()
                effect = row["payload"]["effect"]
                usage = next((r["content"]["usage"] for r in receipts
                              if r["content"].get("usage") and not
                              r["content"].get("model_meta", {}).get("simulated")), {})
                model = effect == "model-inference"
                tokens = [usage.get(k) for k in ("input_tokens", "output_tokens")]
                operations[op_id] = {
                    "tokens": (sum(tokens) if all(type(n) is int for n in tokens)
                               else None) if model else 0,
                    "charge_units": usage.get("charge_units") if model else 0,
                    "model_calls": int(model),
                    "sandbox_ops": int(effect == "sandbox-exec")}

    def totals(ids, queries):
        result = {"witness_queries": queries}
        for key in ("tokens", "charge_units", "model_calls", "sandbox_ops"):
            values = [operations[op][key] for op in ids]
            result[key] = None if None in values else sum(values)
        return result

    queries = sum(r["costs"]["witness_queries"] for r in use_records)
    acquisition_queries = campaign.get("queries")
    if acquisition_queries is None and dsn:
        acquisition_queries = sum(
            int(boundary["spend"]) for boundary in
            _read_campaign(dsn, campaign["campaign_id"])[0].values())
    acquisition = totals(acquisition_ids, acquisition_queries or 0)
    use = totals(use_ids, queries)
    total = totals(acquisition_ids | use_ids, acquisition["witness_queries"] + queries)
    episodes = campaign.get("episodes", [])
    return {
        "campaign_id": campaign["campaign_id"],
        "acquisition": acquisition, "use": use, "total": total,
        "operations": operations,
        "shared_operations": sorted(acquisition_ids & use_ids),
        "mechanism": {
            "boundaries": len(campaign.get("boundaries", [])),
            "retained": sum(1 for e in episodes
                            if e.get("disposition") == "retained"),
            "rejected": sum(1 for e in episodes
                            if e.get("disposition") == "rejected"),
            "no_candidate": sum(1 for e in episodes
                                if e.get("disposition") == "no-candidate"),
        },
    }


def resume_campaign(dsn: str, cid: str, charter: dict, caps: dict,
                    tasks: list | None = None,
                    capability_id: str = "seed-sw-greedy",
                    propose=None, gateway=None, model: str = "",
                    constructor: str = "seed", consumer=None,
                    study_root: str | None = None,
                    policy_release: str | None = None) -> dict:
    """Resume a campaign, restoring its held operations before anything runs.

    The restore happens first and separately, because restoration is not
    execution. `mission.resume_operation` reads back each admitted operation's
    program digest and input identity and marks it restored; it runs nothing
    and writes no effect record. `run_campaign` then executes the pending
    boundary through `execute_pending`, which runs the task and capability the
    entry recorded at admission rather than the ones the restarting caller's
    schedule supplies.

    The result reports what was restored under which program, so a caller can
    see the identity a restart resumed with rather than inferring it. That
    report is `resumed_in_flight`; it is the whole answer to "what did this
    restart continue", and it comes from the one record that holds it.
    """
    world, arm, seq, token = _parse_campaign_id(cid)
    if token:
        # The resumed run must be namespaced the same way the id it resumes
        # was minted, or `run_campaign` builds a different campaign id and the
        # equality check below fails for a reason that has nothing to do with
        # the resume. `campaign_id` has appended a token since this parser was
        # written, and without this the tokenized form was write-only.
        set_namespace_token(token)
    from . import mission

    # Read the settled set before the run, not after. `run_campaign`'s own
    # incorporation would make every restored operation look settled, and the
    # report would say nothing about what was still pending when the restart
    # began -- which is the question the report exists to answer.
    settled_attempts = _settled_attempts(dsn, cid)
    restored = mission.resume_operation(dsn, cid)
    out = run_campaign(world, arm, charter, caps, tasks=tasks,
                       capability_id=capability_id,
                       campaign_seq=seq, dsn=dsn,
                       propose=propose, gateway=gateway, model=model,
                       constructor=constructor, consumer=consumer,
                       study_root=study_root,
                       policy_release=policy_release)
    if out["campaign_id"] != cid:
        raise ValueError("resumed unexpected campaign %r" % (
            out.get("campaign_id"),))
    # Reported from what was restored, not from what `run_campaign` returns,
    # so the report says what crossed the restart rather than what came back.
    out["resumed_in_flight"] = [
        {**item.as_json(), "restored": item.attempt_id in settled_attempts}
        for item in restored]
    return out


def _settled_attempts(dsn: str, cid: str) -> set:
    """The attempts whose boundary has an effect record, by attempt id.

    Read before the run rather than after, because the run's own incorporation
    would make every restored operation look settled and the report would say
    nothing about what was still pending when the restart began.
    """
    with _read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT attempt_id FROM s09_policy_state"
            " WHERE investigation_id = %s AND effect_record IS NOT NULL",
            (cid,)).fetchall()
        conn.commit()
    return {row["attempt_id"] for row in rows}


def _dev_episode_authority(journal: dict | None,
                           boundary: dict | None) -> dict:
    """The authority a development episode's constructed member runs under.

    Named per boundary, so each episode is its own operation on the
    campaign's allocation. Empty without a journal, and the episode then
    reports the executor's refusal as a rejection rather than a method that
    ran and failed.
    """
    if not (journal and journal.get("dsn") and journal.get("cid")
            and boundary is not None):
        return {}
    return {"dsn": journal["dsn"], "allocation_id": _alloc_id(journal["cid"]),
            "operation_id": _attempt_id(journal["cid"],
                                        boundary["seq"]) + "-dev"}


def dev_episode(task_id: str, capability_id: str, max_queries: int = 16,
                break_candidate: bool = False,
                member: dict | None = None, result: dict | None = None,
                *, authority: dict | None = None) -> dict:
    """Run one development episode and report what it kept.

    A seed capability runs host-side through `seeds.run_seed` and needs no
    authority, because it is the host's own repertoire rather than authored
    source. A constructed member is authored source, so it executes only
    under the authority its caller supplies; without it the episode reports
    the refusal as a rejection rather than pretending the method ran.
    """
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    initial, _ = _size(task, task)
    if member is None:
        capability = next(c for c in seeds.SEED_CAPABILITIES
                          if c["capability_id"] == capability_id)
        lineage = [{"capability_id": capability_id, "authored": True}]
        executable_base = {"capability_id": capability_id,
                           "method": capability["method"],
                           "authored": True}
    else:
        lineage = [{"capability_id": member["capability_id"],
                    "authored": False,
                    "source_digest": member.get("source_digest", ""),
                    "construction": member.get("lineage", {})}]
        executable_base = {"capability_id": member["capability_id"],
                           "method_source": member["method_source"],
                           "entry": member.get("entry", ""),
                           "source_digest": member.get("source_digest", ""),
                           "construction": member.get("lineage", {}),
                           "authored": False}
    if max_queries <= 0:
        refusal = _refuse_probe(max_queries)
        return {"disposition": "no-candidate",
                "fallback": "incumbent",
                "fallback_reason": refusal.reason,
                "fallback_detail": refusal.detail,
                "task_id": task_id, "lineage": [],
                "initial_size": initial, "queries": 0}
    if result is None:
        if member is None:
            result = seeds.run_seed(capability, task,
                                    max_queries=max_queries)
        else:
            from .method_exec import MethodExecutionError
            try:
                result = _run_member(member, task,
                                     max_queries=max_queries,
                                     **(authority or {}))
            except MethodExecutionError as exc:
                return {"disposition": "rejected",
                        "reason": str(exc), "task_id": task_id,
                        "lineage": lineage, "check": {},
                        "initial_size": initial, "queries": 0}
    candidate = result["candidate"]
    if break_candidate:
        candidate = controls.break_candidate(task)
        lineage.append({"capability_id": "broken-probe",
                        "authored": True})
    report = _check(task, candidate)
    _, final = _size(task, candidate)
    failed = {"task_id": task_id, "lineage": lineage,
              "check": report, "queries": result["queries"]}
    if report["verdict"] != "preserved":
        return {"disposition": "rejected",
                "reason": report.get("reason", report["verdict"]),
                "failed": [failed], "task_id": task_id,
                "lineage": lineage, "check": report,
                "initial_size": initial, "final_size": final,
                "queries": result["queries"]}
    if final >= initial:
        return {"disposition": "no-candidate",
                "fallback": "incumbent",
                "fallback_reason": "no reduction over incumbent",
                "failed": [failed], "task_id": task_id,
                "lineage": lineage, "check": report,
                "initial_size": initial, "final_size": final,
                "queries": result["queries"]}
    return {"disposition": "retained", "task_id": task_id,
            "lineage": lineage, "check": report,
            "initial_size": initial, "final_size": final,
            "queries": result["queries"], "candidate": candidate,
            "executable": {**executable_base,
                           "params": {"max_queries": max_queries},
                           "scope": {"family": task["family"]},
                           "qualified_on": task_id}}


def run_diagnostic(admitted: dict, experience: dict,
                   budget: int | None = None) -> dict:
    from .learner import LearnerRefused
    action = admitted.get("next_action") or {}
    name = action.get("diagnostic", "software")
    if name not in _DIAGNOSTICS:
        if name == "diagnostic_resolves":
            name = "software"
        else:
            raise ValueError("unknown diagnostic %r" % name)
    try:
        family = _family(action.get("task_id"))
    except (KeyError, TypeError):
        raise LearnerRefused("unknown diagnostic target %r" % (
            action.get("task_id"),))
    if name != family:
        raise LearnerRefused(
            "diagnostic family %r mismatches task family %r" % (
                action.get("diagnostic"), family))
    report = (_DIAGNOSTICS[name](action["task_id"])
              if budget is None else
              _DIAGNOSTICS[name](action["task_id"], budget))
    basis = list(admitted.get("basis_references") or [])
    recorded = [o.get("observation_id")
                for o in experience.get("observations") or []]
    return {
        "observation_id": "obs-%s-%s" % (report["control_id"],
                                         report["task_id"]),
        "basis_references": basis,
        "grounded": all(r in recorded for r in basis),
        "task_id": report["task_id"],
        "verdict": report["verdict"],
        "queries": report.get("queries", 0),
        "detail": report,
    }


def next_decision(experience: dict, charter: dict) -> dict:
    observations = list(experience.get("observations") or [])
    if not observations:
        return {"action": "stop",
                "reason": "no admissible work remains"}
    content = sorted((o.get("task_id"), o.get("capability_id"),
                      repr(o.get("verdict")))
                     for o in observations)
    latest = observations[-1]
    return {
        "action": "investigate",
        "question": "why did %s on %s yield %r" % (
            latest["capability_id"], latest["task_id"],
            latest.get("verdict")),
        "next_action": {"kind": "diagnostic",
                        "task_id": latest["task_id"],
                        "capability_id": latest["capability_id"]},
        "evidence_digest": content,
    }


def _dev_task_ids() -> set:
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    return {t for w in membership.values() for d in w.get("dev", {}).values()
            for t in d}


def _world_dev_ids(world: int) -> set:
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    return {t for d in membership[str(world)].get("dev", {}).values()
            for t in d}


def _target_refusal(target: object, *, world: int, arm: str,
                    seq: int) -> str | None:
    from . import rotation
    if not isinstance(target, str) or not target:
        return "no development target proposed"
    try:
        _family, target_world, kind, _index = worlds._parse_task_id(target)
    except (KeyError, IndexError, ValueError):
        return "unknown target %r" % (target,)
    if target_world != world:
        return "target %s is outside world %d" % (target, world)
    if kind != "dev" or target not in _world_dev_ids(world):
        return "protected-use target %s is never a development target" % target
    if arm == "R":
        schedule = rotation.r_schedule(world)
        if seq >= len(schedule):
            return "no curriculum item at boundary %d" % seq
        want = schedule[seq]["task_id"]
        if target != want:
            return "target %s is outside the admitted curriculum item %s" \
                % (target, want)
    return None


def _durable_observations(dsn: str, cid: str) -> dict:
    settled, _pending = _read_campaign(dsn, cid)
    return {row["observation"].get("observation_id"): row["observation"]
            for row in settled.values()
            if isinstance(row.get("observation"), dict)
            and row["observation"].get("observation_id")}


def _observation_is_durable(observation_id, observation, durable) -> bool:
    """Whether an experience observation is the stored one it claims to be.

    The experience list reaching admission is `packet.project_observations`
    output, which is deliberately reduced to five fields so assessor detail
    never reaches a model prompt. Comparing that projection to the stored
    record with `!=` therefore failed for every settled observation and
    reported genuine ones as forged on each resume.

    So the check is on identity and provenance: the id must be in the store,
    and every field the projection preserves must agree with the record.
    A record under a known id whose content was tampered with, or whose task
    or capability was swapped, still fails, and an unknown id still fails.
    """
    if not observation_id or not isinstance(observation, dict):
        return False
    stored = durable.get(observation_id)
    if not isinstance(stored, dict):
        return False
    for field in ("observation_id", "task_id", "capability_id", "verdict"):
        if observation.get(field) != stored.get(field):
            return False
    projected_detail = observation.get("detail")
    stored_detail = stored.get("detail")
    if projected_detail is not None and projected_detail != stored_detail:
        return False
    return True


def admit_investigation(proposal: dict, experience: dict,
                        charter: dict, boundary: dict | None = None,
                        *, durable_observations: dict | None = None,
                        trusted_observation_ids=()) -> dict:
    from .learner import LearnerRefused, validate_proposal
    try:
        validate_proposal(proposal)
    except LearnerRefused as exc:
        return {"decision": "refused", "reason": str(exc)}
    if durable_observations is not None:
        trusted = set(trusted_observation_ids)
        forged = []
        for observation in experience.get("observations") or []:
            observation_id = observation.get("observation_id") \
                if isinstance(observation, dict) else None
            if observation_id in trusted:
                continue
            if not _observation_is_durable(
                    observation_id, observation, durable_observations):
                forged.append(str(observation_id or "malformed"))
        if forged:
            return {"decision": "refused",
                    "reason": "forged experience observations: %s"
                              % ", ".join(sorted(forged))}
    refs = list(proposal.get("basis_references") or [])
    by_id = {o.get("observation_id"): o
             for o in experience.get("observations") or []}
    invented = [r for r in refs if r not in by_id]
    if invented:
        return {"decision": "refused",
                "reason": "invented basis references: %s"
                          % ", ".join(sorted(invented))}
    dev = _dev_task_ids()
    smuggled = sorted({by_id[r].get("task_id") for r in refs}
                      - dev)
    if smuggled:
        return {"decision": "refused",
                "reason": "protected-use feedback cannot drive"
                          " development: %s" % ", ".join(smuggled)}
    if not refs:
        if not proposal.get("unknown") or not charter.get("objective"):
            return {"decision": "refused",
                    "reason": "exploratory option needs charter grounding"
                              " and a stated unknown"}
        return {"decision": "admitted", "reason": "explicit exploratory",
                "investigation": proposal}
    if boundary is not None:
        action = proposal.get("next_action") or {}
        if isinstance(action, dict) and action.get("task_id"):
            reason = _target_refusal(action["task_id"], **boundary)
            if reason is not None:
                return {"decision": "refused", "reason": reason}
    return {"decision": "admitted", "reason": "evidence-grounded",
            "investigation": proposal}


def propose_investigation(experience: dict, charter: dict) -> dict:
    observations = list(experience.get("observations") or [])
    if not observations:
        raise ValueError("proposal needs at least one recorded observation")
    basis = [o["observation_id"] for o in observations]
    first = observations[0]
    return {
        "basis_references": basis,
        "question": "why did %s on %s yield %r" % (
            first["capability_id"], first["task_id"],
            first.get("verdict")),
        "next_action": {"kind": "diagnostic",
                        "task_id": first["task_id"],
                        "capability_id": first["capability_id"]},
        "requested_resources": {"diagnostic_queries": 1},
        "charter": charter.get("objective", ""),
    }
