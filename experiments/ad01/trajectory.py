"""AD01 trajectory: system-chosen investigations over recorded experience.

Scaffolding first: deterministic proposal construction from the experience
the system actually observed. No model calls here.
"""

from __future__ import annotations

from . import controls, seeds, worlds

def _resolve_sw(task_id: str) -> dict:
    report = controls.diagnostic_resolves(task_id)
    return {"control_id": report["control_id"], "task_id": task_id,
            "verdict": "%s-vs-%s" % (report["diagnostic_verdict"],
                                     report["nondiagnostic_verdict"]),
            "detail": report}


def _resolve_gr(task_id: str) -> dict:
    report = controls.novel_order_unproductive(task_id)
    return {"control_id": report["control_id"], "task_id": task_id,
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


def _claimed_ops(cid: str, seq: int) -> list:
    return ["op-%s-%d-diagnostic" % (cid, seq),
            "op-%s-%d-episode" % (cid, seq)]


def _read_conn(dsn: str):
    from psycopg.rows import dict_row
    from settlement import db
    return db.connect(dsn, row_factory=dict_row)


def ensure_campaign(dsn: str, cid: str, world: int, arm: str,
                    charter: dict, caps: dict) -> dict:
    from settlement import db, store
    from settlement.common import Command, ResultCode
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
    with _read_conn(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, authorized FROM allocations WHERE id = %s",
                        (_alloc_id(cid),))
            row = cur.fetchone()
            if row is None:
                cur.execute("INSERT INTO allocations (id, domain, authorized)"
                            " VALUES (%s, 'agenda', 1000)",
                            (_alloc_id(cid),))
        conn.commit()
    return {"campaign_id": cid, "world": world, "arm": arm,
            "admitted": made is not None}


def record_decision(dsn: str, cid: str, seq: int, decision: dict) -> str:
    from settlement import store
    from settlement.common import Command
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
    assert made.data["attempt_id"] == aid
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
                if content.get("kind") == "boundary" and content.get(
                        "claimed_ops"):
                    settled[seq] = {"row_id": row["id"], **content}
                elif content.get("kind") == "decision":
                    pending.setdefault(seq, {"row_id": row["id"],
                                             **content})
    for seq in settled:
        pending.pop(seq, None)
    return settled, pending


def _run_boundary(task_id: str, capability_id: str, caps: dict,
                  seed_obs: dict, propose=None,
                  charter: dict | None = None) -> tuple:
    capability_id = _capability_for(task_id, capability_id)
    seed_obs = {**seed_obs, "capability_id": capability_id}
    seen = {"observations": [seed_obs]}
    asked = dict(charter or {})
    if not asked.get("objective"):
        asked["objective"] = "x"
    if propose is None:
        proposal = propose_investigation({"observations": [seed_obs]}, {})
        proposal["next_action"] = {"kind": "diagnostic",
                                   "diagnostic": _family(task_id),
                                   "task_id": task_id}
    else:
        proposal = propose(seen, asked)
    admitted = admit_investigation(proposal, seen, asked)
    if admitted.get("decision") == "refused":
        episode = {"disposition": "no-candidate", "fallback": "incumbent",
                   "fallback_reason": admitted.get("reason", "refused"),
                   "task_id": task_id, "queries": 0}
        return seed_obs, episode, 0
    action = dict(admitted["investigation"]["next_action"])
    if action.get("kind") == "stop":
        return None, None, 0
    target = action.get("task_id") or task_id
    action["task_id"] = target
    investigation = {**admitted["investigation"], "next_action": action}
    observation = run_diagnostic(investigation, seen)
    episode = dev_episode(
        target, _capability_for(target, capability_id),
        max_queries=int(action.get("max_queries",
                                   caps.get("diagnostic_queries", 16))))
    spend = 1 + episode.get("queries", 0)
    return observation, episode, spend


def _default_tasks(world: int) -> list:
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    dev = membership[str(world)]["dev"]
    return ["ad01-w%d-dev-sw-%02d" % (world, i) for i in range(3)
            if "ad01-w%d-dev-sw-%02d" % (world, i) in dev["software"]]


def _publish_boundary(dsn: str, cid: str, seq: int, task_id: str,
                      decision: dict, observation: dict, episode: dict,
                      spend: int) -> int:
    from settlement import store
    from settlement.common import Command
    aid = _attempt_id(cid, seq)
    try:
        record_decision(dsn, cid, seq, decision)
    except Exception as exc:
        if not any(k in str(exc) for k in ("already exists", "duplicate",
                                           "reused with different payload",
                                           "is not on this team")):
            raise
    made = store.submit_observation(
        dsn, Command(request_id="settle-%s" % aid,
                     payload={"attempt_id": aid,
                              "content": {"kind": "boundary", "seq": seq,
                                          "task_id": task_id,
                                          "decision_id": aid,
                                          "observation_id": observation[
                                              "observation_id"],
                                          "episode": {
                                              "disposition": episode[
                                                  "disposition"],
                                              "queries": episode.get(
                                                  "queries", 0)},
                                          "spend": spend,
                                          "claimed_ops": _claimed_ops(
                                              cid, seq)}}))
    assert made.data["attempt_id"] == aid
    return aid


def run_campaign(world: int, arm: str, charter: dict, caps: dict,
                 tasks: list | None = None,
                 capability_id: str = "seed-sw-greedy",
                 campaign_seq: int = 0, dsn: str | None = None,
                 propose=None) -> dict:
    cid = campaign_id(world, arm, campaign_seq)
    if tasks is None:
        tasks = _default_tasks(world)
    if dsn is not None:
        ensure_campaign(dsn, cid, world, arm, charter, caps)
        settled, _ = _read_campaign(dsn, cid)
    else:
        settled = {}
    experience: dict = {"observations": []}
    boundaries, episodes = [], []
    queries = 0
    stop = {"reason": "no admissible work remains"}
    for seq, task_id in enumerate(tasks):
        if seq >= int(caps.get("max_boundaries", 6)):
            stop = {"reason": "boundary cap reached"}
            break
        decision = next_decision(experience, charter)
        if seq in settled:
            old = settled[seq]
            queries += int(old["spend"])
            experience["observations"].append(
                {"observation_id": old["observation_id"],
                 "task_id": old["task_id"],
                 "capability_id": capability_id,
                 "verdict": old["episode"]["disposition"]})
            episodes.append(old["episode"])
            boundaries.append({"seq": seq, "task_id": old["task_id"],
                               "decision": decision,
                               "decision_id": old["row_id"],
                               "observation_id": old["observation_id"],
                               "spend": old["spend"], "resumed": True})
            continue
        routed = _capability_for(task_id, capability_id)
        seed_obs = {"observation_id": "obs-%s-seed" % task_id,
                    "task_id": task_id, "capability_id": routed,
                    "verdict": "unmeasured"}
        observation, episode, spend = _run_boundary(
            task_id, routed, caps, seed_obs, propose=propose,
            charter=charter)
        if observation is None:
            stop = {"reason": "learner stop"}
            break
        executed = episode.get("task_id", task_id)
        queries += spend
        experience["observations"].append(
            {"observation_id": observation["observation_id"],
             "task_id": executed,
             "capability_id": _capability_for(executed, routed),
             "verdict": observation["verdict"]})
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
        if queries >= 16 * int(caps.get("max_boundaries", 6)):
            stop = {"reason": "diagnostic query cap reached"}
            break
    else:
        stop = {"reason": "no admissible work remains"}
    return {"campaign_id": cid, "world": world, "arm": arm,
            "charter": charter.get("objective", ""),
            "boundaries": boundaries, "episodes": episodes,
            "stop": stop, "queries": queries}


def freeze_repertoire(campaign: dict, path) -> dict:
    import json
    from pathlib import Path
    members = [e["executable"] for e in campaign.get("episodes", [])
               if e.get("disposition") == "retained"
               and isinstance(e.get("executable"), dict)]
    repertoire = {"campaign_id": campaign["campaign_id"],
                  "members": members}
    Path(path).write_text(json.dumps(repertoire, sort_keys=True,
                                     indent=2) + "\n")
    return repertoire


def load_repertoire(path) -> dict:
    import json
    from pathlib import Path
    repertoire = json.loads(Path(path).read_text())
    assert isinstance(repertoire.get("members"), list)
    return repertoire


def _select_member(repertoire: dict, task: dict) -> dict | None:
    for member in repertoire.get("members", []):
        if member.get("scope", {}).get("family") == task["family"]:
            return member
    return None


def _run_member(member: dict, task: dict) -> dict:
    known = [c for c in seeds.SEED_CAPABILITIES
             if c["capability_id"] == member["capability_id"]]
    max_queries = int(member.get("params", {}).get("max_queries", 16))
    if known:
        return seeds.run_seed(known[0], task, max_queries=max_queries)
    from experiments.representation import checkers, reducers
    oracle = (checkers.SoftwareOracle(task, max_queries=max_queries)
              if task["family"] == "software"
              else checkers.GraphOracle(task, max_queries=max_queries))
    namespace: dict = {"reducers": reducers}
    exec(member["method_source"], namespace)
    return namespace[member["entry"]](task, oracle,
                                      max_queries=max_queries)


def run_use(repertoire: dict, world: int, arm: str, use_tasks: list,
            base_costs: dict) -> list:
    from . import checker
    records = []
    for task_id in use_tasks:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        domain = task["family"]
        member = _select_member(repertoire, task)
        if member is None:
            requested = selected = "incumbent"
            output = controls.incumbent(task)
            queries = 0
            reason = "no eligible repertoire member for %s" % domain
            executed_source = "incumbent"
        else:
            requested = selected = member["capability_id"]
            result = _run_member(member, task)
            output = result["candidate"]
            queries = result["queries"]
            reason = ""
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
            "output": output,
            "costs": {**base_costs, "witness_queries": queries},
            "requested": requested, "selected": selected,
            "executed": selected, "executed_source": executed_source,
            "fallback_reason": reason})
    return records


def cost_union(campaign: dict, use_records: list) -> dict:
    from .checker import COST_KEYS
    acquisition = {key: 0 for key in COST_KEYS}
    acquisition["witness_queries"] = campaign.get("queries", 0)
    use = {key: 0 for key in COST_KEYS}
    for record in use_records:
        for key in COST_KEYS:
            use[key] += record["costs"][key]
    total = {key: acquisition[key] + use[key] for key in COST_KEYS}
    episodes = campaign.get("episodes", [])
    return {
        "campaign_id": campaign["campaign_id"],
        "acquisition": acquisition, "use": use, "total": total,
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
                    capability_id: str = "seed-sw-greedy") -> dict:
    settled, pending = _read_campaign(dsn, cid)
    world = int(cid.split("-")[1][1:])
    arm = cid.split("-")[2]
    if tasks is None:
        ordered = sorted(settled) + [s for s in sorted(pending)
                                     if s not in settled]
        if ordered:
            known = {**(settled), **pending}
            tasks = []
            for seq in ordered:
                entry = known[seq]
                tid = entry.get("task_id") or (entry.get("decision") or {}
                                               ).get("next_action", {}
                                                     ).get("task_id")
                if tid and tid not in tasks:
                    tasks.append(tid)
        else:
            tasks = _default_tasks(world)
    out = run_campaign(world, arm, charter, caps, tasks=tasks,
                       capability_id=capability_id,
                       campaign_seq=int(cid.split("-")[-1]), dsn=dsn)
    assert out["campaign_id"] == cid
    return out


def dev_episode(task_id: str, capability_id: str, max_queries: int = 16,
                break_candidate: bool = False) -> dict:
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    capability = next(c for c in seeds.SEED_CAPABILITIES
                      if c["capability_id"] == capability_id)
    initial, _ = _size(task, task)
    lineage = [{"capability_id": capability_id, "authored": True}]
    if max_queries <= 0:
        return {"disposition": "no-candidate",
                "fallback": "incumbent",
                "fallback_reason": "zero construction budget",
                "task_id": task_id, "lineage": lineage,
                "initial_size": initial, "queries": 0}
    result = seeds.run_seed(capability, task, max_queries=max_queries)
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
            "executable": {"capability_id": capability_id,
                           "method": capability["method"],
                           "params": {"max_queries": max_queries},
                           "scope": {"family": task["family"]},
                           "authored": True,
                           "qualified_on": task_id}}


def run_diagnostic(admitted: dict, experience: dict) -> dict:
    action = admitted.get("next_action") or {}
    name = action.get("diagnostic", "software")
    if name not in _DIAGNOSTICS:
        if name == "diagnostic_resolves":
            name = "software"
        else:
            raise ValueError("unknown diagnostic %r" % name)
    report = _DIAGNOSTICS[name](action["task_id"])
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
        "detail": report["detail"],
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


def admit_investigation(proposal: dict, experience: dict,
                        charter: dict) -> dict:
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
