"""AD01 trajectory: system-chosen investigations over recorded experience.

Scaffolding first: deterministic proposal construction from the experience
the system actually observed. No model calls here.
"""

from __future__ import annotations

import os

from . import controls, seeds, worlds
from . import packet as _packet


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


def campaign_id(world: int, arm: str, seq: int = 0) -> str:
    return "ad01-w%d-%s-%02d" % (world, arm, seq)


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
            consumer = _policy.DecisionConsumer(
                proposer=proposer, admit=admit_investigation,
                dsn=(journal or {}).get("dsn"),
                cid=(journal or {}).get("cid") or "",
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
    if action.get("kind") not in ("diagnostic", "development"):
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
        result=(member or {}).get("validation", {}).get("result"))
    episode["construction_calls"] = int(
        (member or {}).get("lineage", {}).get("calls_made", 0))
    episode["queries"] += observation["queries"]
    if state is not None:
        state["dev_episodes"] = int(state.get("dev_episodes", 0)) + 1
    spend = 1 + episode.get("queries", 0)
    return observation, episode, spend


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
    made = store.submit_observation(
        dsn, Command(request_id="settle-%s" % aid,
                     payload={"attempt_id": aid,
                              "content": {"kind": "boundary", "seq": seq,
                                          "task_id": task_id,
                                          "decision": decision,
                                          "observation": observation,
                                          "observation_id": observation[
                                              "observation_id"],
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
                 study_root: str | None = None) -> dict:
    cid = campaign_id(world, arm, campaign_seq)
    study_root = study_root or cid
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
    experience: dict = {"observations": [], "retained": []}
    boundaries, episodes = [], []
    queries = 0
    state = {"dev_episodes": 0, "model_calls": 0,
             "construction_calls": 0}
    construction = None
    if constructor == "model":
        construction = {"dsn": dsn, "cid": cid, "gateway": gateway,
                        "model": model, "study_root": study_root,
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
        entry = {"seq": seq, "task_id": executed,
                 "decision": decision,
                 "observation_id": observation["observation_id"],
                 "spend": spend}
        if dsn is not None:
            entry["decision_id"] = _publish_boundary(
                dsn, cid, seq, executed, decision, observation,
                episode, spend)
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
    return repertoire


def _select_member(repertoire: dict, task: dict) -> dict | None:
    for member in repertoire.get("members", []):
        if member.get("scope", {}).get("family") == task["family"]:
            return member
    return None


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
        return seeds.run_seed(known[0], task, max_queries=budgeted)
    from . import method_exec
    return method_exec.run_member_out_of_process(
        member, task, max_queries=budgeted, dsn=dsn,
        allocation_id=allocation_id, operation_id=operation_id,
        **({} if timeout_ms is None else {"timeout_ms": timeout_ms}))


def run_use(repertoire: dict, world: int, arm: str, use_tasks: list,
            base_costs: dict, *, dsn: str | None = None,
            allocation_id: str | None = None) -> list:
    from . import checker
    if dsn is not None and not allocation_id:
        raise ValueError("use requires explicit execution allocation")
    _check_tasks(list(use_tasks))
    records = []
    for task_id in use_tasks:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        domain = task["family"]
        member = _select_member(repertoire, task)
        operation_ids = []
        execution = None
        if member is not None and dsn is not None:
            execution = {"dsn": dsn, "allocation_id": allocation_id,
                         "operation_id": "ad01-%s-use-%s"
                                         % (repertoire["campaign_id"], task_id)}
        if member is None:
            requested = selected = "incumbent"
            output = controls.incumbent(task)
            queries = 0
            reason = "no eligible repertoire member for %s" % domain
            executed_source = "incumbent"
        else:
            requested = selected = member["capability_id"]
            from .method_exec import MethodExecutionError
            try:
                result = _run_member(member, task, **(execution or {}))
            except MethodExecutionError as exc:
                if execution:
                    from settlement import broker
                    if broker.read_operation(dsn, execution["operation_id"]) is not None:
                        operation_ids = [execution["operation_id"]]
                output = controls.incumbent(task)
                report = _check(task, output)
                initial, final = _size(task, output)
                records.append({
                    "record_id": "%s-%s-%s" % (repertoire["campaign_id"],
                                               arm, task_id),
                    "world": world, "arm": arm, "task_id": task_id,
                    "domain": domain, "freeze": worlds.FREEZE_ID,
                    "freeze_digest": checker.freeze_digest(
                        worlds.FROZEN_DIR),
                    "verdict": report["verdict"],
                    "initial_measure": initial, "final_measure": final,
                    "normalized_reduction": 0.0,
                    "output": output, "operation_ids": operation_ids,
                    "costs": {**base_costs, "witness_queries": 0},
                    "requested": requested, "selected": selected,
                    "executed": "incumbent",
                    "executed_source": "incumbent",
                    "fallback_reason": "member execution failed: %s"
                                       % exc})
                continue
            output = result["candidate"]
            queries = result["queries"]
            reason = ""
            operation_ids = list(result.get("operation_ids") or [])
            executed_source = member.get("method_source")
            if executed_source is None:
                known = next(c for c in seeds.SEED_CAPABILITIES
                             if c["capability_id"]
                             == member["capability_id"])
                executed_source = known["method"]
        report = _check(task, output)
        initial, final = _size(task, output)
        records.append({
            "record_id": "%s-%s-%s" % (repertoire["campaign_id"], arm,
                                       task_id),
            "world": world, "arm": arm, "task_id": task_id,
            "domain": domain, "freeze": worlds.FREEZE_ID,
            "freeze_digest": checker.freeze_digest(worlds.FROZEN_DIR),
            "verdict": report["verdict"],
            "initial_measure": initial, "final_measure": final,
            "normalized_reduction": ((initial - final) / initial
                                     if report["verdict"] == "preserved"
                                     else 0.0),
            "output": output, "operation_ids": operation_ids,
            "costs": {**base_costs, "witness_queries": queries},
            "requested": requested, "selected": selected,
            "executed": selected, "executed_source": executed_source,
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
                    study_root: str | None = None) -> dict:
    parts = cid.split("-")
    if len(parts) != 4 or parts[0] != "ad01" or parts[2] not in ("I", "R"):
        raise ValueError("malformed campaign id %r" % (cid,))
    try:
        world = int(parts[1][1:])
        seq = int(parts[3])
    except ValueError:
        raise ValueError("malformed campaign id %r" % (cid,))
    out = run_campaign(world, parts[2], charter, caps, tasks=tasks,
                       capability_id=capability_id,
                       campaign_seq=seq, dsn=dsn,
                       propose=propose, gateway=gateway, model=model,
                       constructor=constructor, consumer=consumer,
                       study_root=study_root)
    if out["campaign_id"] != cid:
        raise ValueError("resumed unexpected campaign %r" % (
            out.get("campaign_id"),))
    return out


def dev_episode(task_id: str, capability_id: str, max_queries: int = 16,
                break_candidate: bool = False,
                member: dict | None = None, result: dict | None = None) -> dict:
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
                "fallback_reason": "%s: %s" % (refusal.reason,
                                               refusal.detail),
                "task_id": task_id, "lineage": [],
                "initial_size": initial, "queries": 0}
    if result is None:
        result = (seeds.run_seed(capability, task, max_queries=max_queries)
                  if member is None else
                  _run_member(member, task, max_queries=max_queries))
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


def admit_investigation(proposal: dict, experience: dict,
                        charter: dict, boundary: dict | None = None) -> dict:
    from .learner import LearnerRefused, validate_proposal
    try:
        validate_proposal(proposal)
    except LearnerRefused as exc:
        return {"decision": "refused", "reason": str(exc)}
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
