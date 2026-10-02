"""Agency-boundary data surface (AD01 §8 AD-08).

Human-set fields (objective, environment, capabilities, limits, rules,
interventions) and system-chosen fields (opportunities, diagnostics,
candidates, reuse) live in structurally distinct namespaces with explicit
provenance tags. This module owns the schema; T-ADTR drives population
through the trajectory entry.
"""

from __future__ import annotations

AGENCY_SCHEMA = {
    "human_set": ("objective", "freeze_id", "freeze_digest",
                  "seed_capabilities", "allocation_caps",
                  "benefit_rule_digest", "stop_conditions",
                  "interventions"),
    "system_chosen": ("selected_opportunity", "competing_explanation",
                      "diagnostic", "candidate_lineage", "abandoned",
                      "reuse_decision", "next_allocation"),
}


def make_envelope(charter: dict, trajectory: dict) -> dict:
    human, chosen = (set(AGENCY_SCHEMA["human_set"]),
                     set(AGENCY_SCHEMA["system_chosen"]))
    if set(charter) - human:
        raise ValueError("charter-holds-system-or-unknown-fields %s"
                         % sorted(set(charter) - human))
    if set(trajectory) - chosen:
        raise ValueError("trajectory-holds-human-or-unknown-fields %s"
                         % sorted(set(trajectory) - chosen))
    if set(charter) & set(trajectory):
        raise ValueError("shared-keys-across-namespaces")
    envelope = {
        "charter": {key: {"value": charter[key], "set_by": "human"}
                    for key in charter},
        "trajectory": {key: {"value": trajectory[key], "set_by": "system"}
                       for key in trajectory},
    }
    envelope["charter"].setdefault("interventions",
                                   {"value": [], "set_by": "human"})
    return envelope


def record_intervention(envelope: dict, kind: str, reason: str) -> dict:
    if kind not in ("stop", "amend"):
        raise ValueError("unknown-intervention %r" % kind)
    if not reason:
        raise ValueError("intervention-requires-reason")
    updated = {"charter": dict(envelope["charter"]),
               "trajectory": dict(envelope["trajectory"])}
    log = list(updated["charter"]["interventions"]["value"])
    log.append({"kind": kind, "reason": reason, "set_by": "human"})
    updated["charter"]["interventions"] = {"value": log,
                                           "set_by": "human"}
    return updated


EXPORT_VERSION = "inv01-export-v1"
PROTOCOL = "broker-v1"
PROFILE = "local-process"


def _dbname(dsn: str) -> str:
    for part in dsn.split():
        if part.startswith("dbname="):
            return part.split("=", 1)[1]
    return "unknown"


def _read_conn(dsn: str):
    from psycopg.rows import dict_row
    from settlement import db
    return db.connect(dsn, row_factory=dict_row)


def _operations_for(dsn: str, cid: str) -> list:
    prefix = "ad01-%s-" % cid
    with _read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT id, payload, dispatch_state, launcher_id,"
            " provider_id, execution_version, settled"
            " FROM operations WHERE starts_with(id, %s) ORDER BY id",
            (prefix,)).fetchall()
        return [dict(r) for r in rows]


def _receipts_for(dsn: str, operation_id: str) -> list:
    with _read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT receipt_identity, operation_id, content, outcome"
            " FROM receipts WHERE operation_id = %s"
            " ORDER BY receipt_identity",
            (operation_id,)).fetchall()
        return [dict(r) for r in rows]


def _allocation(dsn: str, cid: str) -> dict:
    from settlement import store
    try:
        return store.allocation_status(dsn, "ad01-campaign-%s" % cid)
    except Exception:
        return {}


def _source_identity() -> dict:
    import subprocess
    from pathlib import Path
    try:
        root = Path(__file__).resolve().parents[2]
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(root),
            text=True, timeout=10).strip()
    except Exception:
        sha = "unknown"
    return {"export_version": EXPORT_VERSION, "git_sha": sha}


def _effective_config(model: str, charter: dict, caps: dict) -> dict:
    from . import trajectory as _traj
    try:
        effort = _traj.reasoning_effort()
    except Exception:
        effort = "unknown"
    freeze = _freeze_identities()
    return {"model": str(model or "recorded-double"),
            "charter": dict(charter), "caps": dict(caps),
            "reasoning_effort": effort,
            "packet_version": str(freeze["packet_version"]),
            "protocol": PROTOCOL, "profile": PROFILE,
            "freeze_id": freeze["freeze_id"],
            "freeze_digest": str(freeze["freeze_digest"])}


def _corrections_for(dsn: str, cid: str, seq: int) -> list:
    with _read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT content FROM attempt_observations"
            " WHERE attempt_id = %s ORDER BY id",
            ("att-%s-%d" % (cid, seq),)).fetchall()
    corrections = []
    for row in rows:
        content = dict((row["content"] or {}))
        if content.get("kind") == "correction":
            corrections.append({"number": int(content.get("number", 0)),
                                "failure": dict(
                                    content.get("failure") or {})})
    return sorted(corrections, key=lambda c: c["number"])


def _delivered_requests(ops: list, seq_ops: list) -> list:
    import hashlib
    by_id = {r["id"]: r for r in ops}
    delivered = []
    for op_id in sorted(seq_ops):
        row = by_id.get(op_id) or {}
        body = dict(row.get("payload") or {})
        inner = dict(body.get("payload") or {})
        messages = list(inner.get("messages") or [])
        prompt = ""
        if messages and isinstance(messages[-1], dict):
            prompt = str(messages[-1].get("content", ""))
        delivered.append({
            "operation_id": op_id,
            "effect": str(body.get("effect", "")),
            "model": str(inner.get("model", "")),
            "prompt": prompt,
            "prompt_digest": hashlib.sha256(
                prompt.encode("utf-8")).hexdigest() if prompt else "",
            "dispatch_state": str(row.get("dispatch_state", "")),
            "settled": bool(row.get("settled", False))})
    return delivered


def _freeze_identities() -> dict:
    from . import checker, worlds
    from . import packet as _packet
    return {"packet_version": _packet.PACKET_VERSION,
            "freeze_id": worlds.FREEZE_ID,
            "freeze_digest": checker.freeze_digest(worlds.FROZEN_DIR)}


def _learner_op_ids(cid: str, seq: int) -> tuple:
    base = "ad01-%s-learner-%d" % (cid, seq)
    return base, base + "-c"


def _seq_ops_for(ops: list, cid: str, seq: int) -> list:
    base, correction = _learner_op_ids(cid, seq)
    prefix = "ad01-%s-" % cid
    marker = "-b%d-" % seq
    return sorted(
        r["id"] for r in ops
        if r["id"] == base or r["id"].startswith(correction)
        or (r["id"].startswith(prefix) and marker in r["id"]))


def _proposal_from_decision(decision: dict | None, episode: dict,
                            task_id: str, versions: dict) -> dict:
    if isinstance(decision, dict) and isinstance(
            decision.get("next_action"), dict):
        action = dict(decision["next_action"])
        basis = list(decision.get("basis_references") or [])
        requested = dict(decision.get("requested_resources") or {})
        question = str(decision.get("question", ""))
        target = str(action.get("task_id") or task_id)
        instrument = str(action.get("kind") or "diagnostic")
        diagnostic = str(action.get("diagnostic") or "")
        max_queries = action.get("max_queries")
    else:
        target = str(episode.get("task_id") or task_id)
        instrument = "diagnostic"
        diagnostic = ""
        max_queries = 0
        basis = []
        requested = {}
        question = str(episode.get("fallback_reason", "no-candidate"))
    try:
        family_target = target
    except Exception:
        family_target = task_id
    inputs = {"model": versions["model"],
              "packet_version": versions["packet_version"],
              "protocol": versions["protocol"],
              "profile": versions["profile"],
              "freeze_digest": versions["freeze_digest"],
              "task_id": family_target,
              "diagnostic": diagnostic,
              "max_queries": max_queries if isinstance(
                  max_queries, int) else 0,
              "question": question,
              "basis_references": list(basis)}
    return {"target": target, "instrument": instrument,
            "inputs": inputs, "dependencies": list(basis),
            "requested": dict(requested)}


def _packet_for(charter: dict, world: int, arm: str, seq: int,
                task_id: str, observations: list, retained: list,
                remaining: dict) -> dict:
    from . import learner
    from . import packet as _packet
    from . import trajectory as _traj
    routed = _traj._capability_for(task_id, "seed-sw-greedy")
    seed_obs = {"observation_id": "obs-%s-seed" % task_id,
                "task_id": task_id, "capability_id": routed,
                "verdict": "unmeasured"}
    curriculum = learner.curriculum_item(world, arm, seq)
    visible = learner.visible_opportunities(world)
    return _packet.decision_packet(
        charter=charter, visible=visible,
        experience={"observations": list(observations) + [seed_obs]},
        retained=list(retained), remaining=dict(remaining),
        curriculum=curriculum,
        boundary={"world": world, "arm": arm, "seq": seq})



def _journal_positions(dsn: str, request_ids: list[str]) -> dict:
    wanted = [rid for rid in request_ids if rid]
    if not wanted:
        return {}
    with _read_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT request_id, row_number() OVER (ORDER BY created_at,"
            " request_id) AS position FROM command_journal"
            " WHERE request_id = ANY(%s)", (wanted,)).fetchall()
    return {str(row["request_id"]): int(row["position"]) for row in rows}


def _release_for(dsn: str, release_id: str | None) -> dict | None:
    if not release_id:
        return None
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT id, protocol_id, versions, scope, disposition, fallback,"
            " policy_version, invalidation, evidence_refs, evaluator_version,"
            " created_at FROM capability_releases WHERE id = %s",
            (release_id,)).fetchone()
    return dict(row) if row is not None else None


def _seed_output(task: dict, kind: str) -> dict | None:
    if kind not in ("construct_method", "use_method"):
        return None
    from . import seeds
    method_id = "seed-%s-greedy" % ("sw" if task["family"] == "software"
                                     else "gr")
    capability = next((item for item in seeds.SEED_CAPABILITIES
                       if item["capability_id"] == method_id), None)
    if capability is None:
        return None
    try:
        return seeds.run_seed(capability, task, max_queries=16).get("candidate")
    except Exception:
        return None


def _narrow_assessment_arm(arm: dict) -> dict:
    cleaned = dict(arm)
    effects = []
    for raw_effect in list(cleaned.get("effects") or []):
        effect = {
            key: raw_effect.get(key)
            for key in (
                "kind", "accepted", "reason", "queries", "model_calls",
                "wall_ms", "owner", "destination", "selected_identity",
                "accounting", "source_digest", "scope", "bound")
            if key in raw_effect
        }
        if not isinstance(effect.get("accepted"), bool):
            effect["accepted"] = bool(effect.get("accepted"))
        effects.append(effect)
    cleaned["effects"] = effects
    return cleaned


def _narrow_assessment_effects(episode: dict) -> dict:
    cleaned = dict(episode)
    assessment = cleaned.get("assessment")
    if not isinstance(assessment, dict):
        return cleaned
    assessment = dict(assessment)
    arms = assessment.get("arms")
    if isinstance(arms, dict):
        assessment["arms"] = {
            name: _narrow_assessment_arm(dict(arm or {}))
            for name, arm in arms.items()
        }
    cleaned["assessment"] = assessment
    return cleaned


def _arm_export(arm: dict, task_ids: list[str], rule: dict,
                evaluator_version: str, assessment_position: int | None,
                world: int) -> dict:
    from . import trajectory, worlds
    decisions = []
    for decision in list(arm.get("decisions") or []):
        item = dict(decision)
        if assessment_position is not None:
            item["journal_position"] = assessment_position
        decisions.append(item)
    effects = list(_narrow_assessment_arm(arm).get("effects") or [])
    outputs = []
    for task_id in task_ids:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        task_decisions = [d for d in decisions if d.get("task_id") == task_id]
        kind = next((d.get("kind") for d in task_decisions
                     if d.get("kind") in ("construct_method", "use_method")),
                    None)
        output = _seed_output(task, kind)
        if isinstance(output, dict):
            output = {key: value for key, value in output.items()
                      if key not in ("witness", "fault", "seed")}
        if output is None:
            report = {"verdict": "failed", "reason": "no task output"}
            initial = trajectory._size(task, task)[0]
            final = initial
        else:
            report = trajectory._check(task, output)
            initial, final = trajectory._size(task, output)
        outputs.append({"task_id": task_id, "output": output,
                        "report": report, "initial": initial, "final": final})
    return {"panel_task_ids": list(task_ids),
            "rule_id": rule.get("rule_id"),
            "evaluator_version": evaluator_version,
            "decisions": decisions,
            "action_kinds": [str(d.get("kind", "")) for d in decisions],
            "effects": effects,
            "quality": dict(arm.get("quality") or {}),
            "resources": dict(arm.get("resources") or {}),
            "outputs": outputs}


def _policy_refusal(dsn: str, proposal_id: str, episode: dict,
                    assessment: dict | None) -> dict | None:
    if not proposal_id:
        return None
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT result_data FROM command_journal WHERE request_id = %s",
            ("s09-policy-refusal-%s" % proposal_id,)).fetchone()
    if row is not None:
        return {**dict(row["result_data"] or {}), "durable": True}
    if assessment is not None and assessment.get("outcome") in (
            "reject", "unavailable"):
        return {"proposal_id": proposal_id,
                "outcome": assessment.get("outcome"),
                "reason": assessment.get("reason", ""),
                "durable": True, "source": "assessment"}
    if episode.get("disposition") in ("rejected", "unavailable"):
        return {"proposal_id": proposal_id,
                "outcome": episode.get("disposition"),
                "reason": episode.get("reason", ""),
                "durable": False}
    return None


def _policy_section(dsn: str, episode: dict, world: int,
                    campaign_tasks: list[str]) -> tuple[dict | None, list]:
    if not isinstance(episode, dict) or episode.get("kind") != "policy_revision":
        return None, []
    import hashlib
    proposal_id = str(episode.get("proposal_id", ""))
    proposal = load_revision_proposal(dsn, proposal_id) if proposal_id else None
    freeze = dict(episode.get("freeze") or {})
    candidate = dict(episode.get("policy_candidate") or {})
    source = candidate.get("policy_source") or freeze.get("source")
    artifact = dict(candidate.get("policy_artifact") or {})
    assessment = dict(episode.get("assessment") or {}) or None
    request_ids = []
    if proposal_id:
        request_ids.extend([_proposal_request_id(proposal_id),
                            _freeze_request_id(proposal_id),
                            "s09-policy-protocol-%s" % proposal_id])
    if assessment and assessment.get("attempt_id"):
        request_ids.append(str(assessment["attempt_id"]))
    refusal = _policy_refusal(dsn, proposal_id, episode, assessment)
    if refusal is not None:
        request_ids.append("s09-policy-refusal-%s" % proposal_id)
    release_id = episode.get("release_id")
    binding = _release_for(dsn, str(release_id) if release_id else None)
    if binding is not None:
        binding = {key: value for key, value in binding.items()
                   if key not in ("created_at",)} | {
                       "created_at": str(binding.get("created_at"))}
    positions = _journal_positions(dsn, request_ids)
    panel = dict((assessment or {}).get("panel") or {})
    rule = dict((assessment or {}).get("rule") or {})
    task_ids = list(panel.get("task_ids") or [])
    arms = {}
    if assessment is not None:
        assessment_position = positions.get(str(assessment.get("attempt_id")))
        for name in ("candidate", "incumbent"):
            arms[name] = _arm_export(
                dict((assessment.get("arms") or {}).get(name) or {}),
                task_ids, rule, str(assessment.get("evaluator_version", "")),
                assessment_position, world)
    digest = (hashlib.sha256(source.encode("utf-8")).hexdigest()
              if isinstance(source, str) else "")
    policy = {"proposal": {
                  "proposal_id": proposal_id,
                  "parent_digest": (proposal or {}).get("parent_digest"),
                  "scope": dict((proposal or {}).get("scope") or {}),
                  "protocol_id": (proposal or {}).get("protocol_id", "")},
              "source": source if isinstance(source, str) else "",
              "source_digest": digest,
              "artifact": artifact,
              "freeze": {"proposal_id": freeze.get("proposal_id", proposal_id),
                         "candidate_digest": freeze.get("candidate_digest", ""),
                         "entry": freeze.get("entry", ""),
                         "bytes": freeze.get("bytes", 0)},
              "panel": {"panel_id": panel.get("panel_id", ""),
                        "task_ids": task_ids,
                        "panel_digest": panel.get("panel_digest", "")},
              "rule": {key: rule.get(key) for key in (
                  "rule_id", "margin", "min_preserved", "resource_ceiling",
                  "max_steps", "tie")},
              "assessment": ({"attempt_id": assessment.get("attempt_id"),
                              "outcome": assessment.get("outcome"),
                              "reason": assessment.get("reason", ""),
                              "protocol_id": assessment.get("protocol_id", ""),
                              "evaluator_version": assessment.get(
                                  "evaluator_version", ""),
                              "scope": dict(assessment.get("scope") or {}),
                              "candidate_digest": assessment.get(
                                  "candidate_digest", ""),
                              "journal_position": positions.get(str(
                                  assessment.get("attempt_id")))}
                             if assessment is not None else None),
              "arms": arms,
              "binding": binding,
              "refusal": refusal,
              "journal": {"proposal": positions.get(
                              _proposal_request_id(proposal_id)),
                          "freeze": positions.get(
                              _freeze_request_id(proposal_id)),
                          "protocol": positions.get(
                              "s09-policy-protocol-%s" % proposal_id),
                          "assessment": positions.get(str(
                              (assessment or {}).get("attempt_id", "")))},
              "campaign_task_ids": list(campaign_tasks)}
    uses = []
    if binding is not None and assessment is not None:
        with _read_conn(dsn) as conn:
            rows = conn.execute(
                "SELECT seq, policy_output, effect_record FROM s09_policy_state"
                " WHERE investigation_id = %s ORDER BY seq",
                (str((proposal or {}).get("investigation_id", "")),)
                ).fetchall()
        for row in rows:
            output = dict(row["policy_output"] or {})
            if output.get("source_digest") != binding.get(
                    "invalidation", {}).get("candidate_digest"):
                continue
            uses.append({"record_id": "policy-use-%s-%s" % (
                             (proposal or {}).get("investigation_id", ""),
                             row["seq"]),
                         "release_id": binding.get("id"),
                         "executed_source_digest": output.get("source_digest"),
                         "fallback_reason": "",
                         "costs": {"witness_queries": 0}})
    return policy, uses


def export_campaign(dsn: str, campaign: dict, *, model: str,
                    charter: dict, caps: dict) -> dict:
    import hashlib
    from settlement.common import payload_digest
    from . import trajectory as _traj
    if not isinstance(campaign, dict) or not campaign.get("campaign_id"):
        raise ValueError("export needs a campaign with campaign_id")
    cid = str(campaign["campaign_id"])
    world = int(campaign.get("world", 0))
    arm = str(campaign.get("arm", "I"))
    freeze = _freeze_identities()
    versions = {"model": str(model or "recorded-double"),
                "packet_version": str(freeze["packet_version"]),
                "protocol": PROTOCOL, "profile": PROFILE,
                "freeze_digest": str(freeze["freeze_digest"])}
    ops = _operations_for(dsn, cid)
    receipts_by_op: dict = {}
    for row in ops:
        receipts_by_op[row["id"]] = _receipts_for(dsn, row["id"])
    settled, _pending = _traj._read_campaign(dsn, cid)
    boundaries = list(campaign.get("boundaries", []))
    episodes = list(campaign.get("episodes", []))
    by_seq = {int(b.get("seq", i)): b for i, b in enumerate(boundaries)}
    transitions: list = []
    observations: list = []
    retained: list = []
    queries_so_far = 0
    dev_so_far = 0
    model_so_far = 0
    order = sorted(set(list(settled.keys()) + list(by_seq.keys())))
    for seq in order:
        durable = settled.get(seq, {})
        entry = by_seq.get(seq, {})
        task_id = str(durable.get("task_id") or entry.get(
            "task_id") or "")
        decision = durable.get("decision", entry.get("decision"))
        observation = durable.get("observation") or {}
        episode = durable.get("episode") or (
            episodes[seq] if seq < len(episodes) else {})
        if isinstance(episode, dict):
            episode = _narrow_assessment_effects(episode)
        remaining = {
            "queries": int(caps.get("diagnostic_queries", 16))
            - queries_so_far,
            "boundaries": int(caps.get("max_boundaries", 6)) - seq,
            "dev_episodes": _traj.DEV_EPISODE_CAP - dev_so_far,
            "model_calls": int(caps.get("model_calls", 60))
            - model_so_far}
        packet = _packet_for(dict(charter), world, arm, seq, task_id,
                             list(observations), list(retained),
                             dict(remaining))
        digest = payload_digest(packet)
        proposal = _proposal_from_decision(
            decision if isinstance(decision, dict) else None,
            episode if isinstance(episode, dict) else {}, task_id,
            versions)
        learner_op, _correction_prefix = _learner_op_ids(cid, seq)
        seq_ops = _seq_ops_for(ops, cid, seq)
        seq_receipts: list = []
        raw_responses: list = []
        results: list = []
        unknown: list = []
        measured_charge = 0
        for op_id in seq_ops:
            for receipt in receipts_by_op.get(op_id, []):
                seq_receipts.append(receipt)
                results.append(str(receipt["receipt_identity"]))
                content = dict(receipt.get("content") or {})
                usage = dict(content.get("usage") or {})
                if receipt.get("outcome") == "unknown":
                    unknown.append(str(receipt["receipt_identity"]))
                if usage.get("billed"):
                    try:
                        measured_charge += int(
                            usage.get("charge_units", 0) or 0)
                    except (TypeError, ValueError):
                        unknown.append(str(
                            receipt["receipt_identity"]))
                text = content.get("text")
                if isinstance(text, str) and text:
                    raw_responses.append(
                        {"operation_id": op_id,
                         "receipt_identity": str(
                             receipt["receipt_identity"]),
                         "text": text,
                         "simulated": bool((content.get(
                             "model_meta") or {}).get("simulated", False)),
                         "digest": hashlib.sha256(
                             text.encode("utf-8")).hexdigest()})
        spend = int(durable.get("spend", entry.get("spend", 0)))
        queries_so_far += spend
        if isinstance(episode, dict) and episode.get(
                "kind", "development") == "development" and episode.get(
                "disposition") in ("retained", "rejected"):
            dev_so_far += 1
        model_so_far += int((episode if isinstance(
            episode, dict) else {}).get("construction_calls", 0))
        model_so_far += sum(
            1 for o in seq_ops if o == learner_op
            or o.startswith(_correction_prefix))
        retained_bytes: list = []
        executable = (episode if isinstance(episode, dict) else {}).get(
            "executable")
        if isinstance(executable, dict) and executable.get(
                "method_source"):
            source = str(executable["method_source"])
            retained_bytes.append({
                "capability_id": str(executable.get(
                    "capability_id", "")),
                "source_digest": str(executable.get(
                    "source_digest", "")),
                "computed_digest": hashlib.sha256(
                    source.encode("utf-8")).hexdigest(),
                "bytes": len(source.encode("utf-8"))})
            retained.append(executable)
        if isinstance(observation, dict) and observation.get(
                "observation_id"):
            observations.append(observation)
        transitions.append({
            "index": seq, "packet_digest": digest, "packet": packet,
            "packet_source": "reconstructed",
            "proposal": proposal, "decision": decision,
            "observation": observation, "episode": episode,
            "corrections": _corrections_for(dsn, cid, seq),
            "delivered_requests": _delivered_requests(ops, seq_ops),
            "operations": sorted(seq_ops), "results": sorted(results),
            "costs_measured": {
                "measured_charge_units": measured_charge,
                "model_calls": sum(
                    1 for o in seq_ops if "-learner-" in o
                    or "-construct-" in o),
                "witness_queries": int((episode if isinstance(
                    episode, dict) else {}).get("queries", 0))},
            "costs_unknown": sorted(unknown),
            "receipts": seq_receipts,
            "raw_responses": raw_responses,
            "retained_bytes": retained_bytes,
            "spend": spend})
    policy_revisions = []
    policy_use_records = []
    campaign_task_ids = [str(t.get("task_id", "")) for t in transitions
                         if isinstance(t.get("task_id"), str)]
    for transition in transitions:
        policy, uses = _policy_section(
            dsn, dict(transition.get("episode") or {}), world,
            campaign_task_ids)
        if policy is not None:
            policy_revisions.append(policy)
            policy_use_records.extend(uses)
    allocation = _allocation(dsn, cid)
    liabilities = [r["id"] for r in ops
                   if r.get("dispatch_state") in (
                       "prepared", "dispatching", "sent", "unresolved")]
    for row in ops:
        for receipt in receipts_by_op.get(row["id"], []):
            if receipt.get("outcome") == "unknown" and row["id"] \
                    not in liabilities:
                liabilities.append(row["id"])
    run_id = payload_digest({"campaign_id": cid, "db": _dbname(dsn),
                             "freeze_digest": versions["freeze_digest"],
                             "model": versions["model"],
                             "packet_version": versions[
                                 "packet_version"]})[:16]
    return {"export_version": EXPORT_VERSION, "run_id": run_id,
            "campaign_id": cid, "world": world, "arm": arm,
            "db": _dbname(dsn),
            "identities": {"versions": versions,
                           "freeze_id": freeze["freeze_id"],
                           "freeze_digest": str(
                               freeze["freeze_digest"]),
                           "charter": dict(charter), "caps": dict(caps),
                           "allocation": allocation,
                           "source": _source_identity(),
                           "effective": _effective_config(
                               versions["model"], charter, caps)},
            "transitions": transitions,
            "operations": ops,
            "allocation": allocation,
            "policy": policy_revisions[-1] if policy_revisions else None,
            "policy_revisions": policy_revisions,
            "use_records": policy_use_records,
            "unknown_exposure": sorted(set(liabilities))}


def write_export(export: dict, path) -> dict:
    import json
    from pathlib import Path
    text = json.dumps(export, sort_keys=True, indent=1,
                      default=str) + "\n"
    Path(path).write_text(text)
    return export


def load_export(path) -> dict:
    import json
    from pathlib import Path
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or not data.get("transitions"):
        raise ValueError("export holds no transitions")
    if data.get("export_version") != EXPORT_VERSION:
        raise ValueError("unsupported export %r" % (
            data.get("export_version"),))
    return data


def verify_byte_chain(export: dict, use_records: list | None = None) -> dict:
    import hashlib
    import json
    from . import checker
    problems: list = []
    checked = 0
    transitions = list(export.get("transitions", []))
    for transition in transitions:
        receipts = {r["receipt_identity"]: r
                    for r in transition.get("receipts", [])}
        raws = list(transition.get("raw_responses", []))
        for raw in raws:
            receipt = receipts.get(raw.get("receipt_identity"))
            if receipt is None:
                problems.append("missing-receipt %s" % (
                    raw.get("receipt_identity"),))
                continue
            content = dict(receipt.get("content") or {})
            text = content.get("text", "")
            if text != raw.get("text"):
                problems.append("receipt-bytes-mismatch %s" % (
                    raw.get("receipt_identity"),))
                continue
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != \
                    raw.get("digest"):
                problems.append("raw-digest-mismatch %s" % (
                    raw.get("receipt_identity"),))
                continue
            checked += 1
        for retained in transition.get("retained_bytes", []):
            source = None
            executable = (transition.get("episode") or {}).get(
                "executable", {})
            if isinstance(executable, dict):
                source = executable.get("method_source")
            if not isinstance(source, str) or not source:
                problems.append("missing-retained-source %s" % (
                    transition.get("index"),))
                continue
            computed = hashlib.sha256(
                source.encode("utf-8")).hexdigest()
            if computed != retained.get("computed_digest"):
                problems.append("retention-digest-mismatch %s" % (
                    retained.get("capability_id"),))
                continue
            if computed != retained.get("source_digest"):
                problems.append("retained-digest-mismatch %s" % (
                    retained.get("capability_id"),))
                continue
            try:
                from . import method_exec
                method_exec.verify_member(
                    {"method_source": source,
                     "entry": executable.get("entry", "")})
            except Exception as exc:
                problems.append("validation-bytes-rejected %s: %s" % (
                    retained.get("capability_id"), exc))
                continue
            found = False
            for raw in raws:
                try:
                    payload = json.loads(raw.get("text", ""))
                except ValueError:
                    continue
                if isinstance(payload, dict) and payload.get(
                        "entry") == source:
                    found = True
                    break
            if not found and raws:
                problems.append("settled-bytes-not-retained %s" % (
                    retained.get("capability_id"),))
                continue
            checked += 1
    if use_records is not None:
        by_capability: dict = {}
        for transition in transitions:
            executable = (transition.get("episode") or {}).get(
                "executable", {})
            if isinstance(executable, dict) and executable.get(
                    "capability_id"):
                by_capability[str(executable.get(
                    "capability_id"))] = str(executable.get(
                    "method_source", ""))
        for record in use_records:
            selected = str(record.get("selected", ""))
            executed = str(record.get("executed_source", ""))
            # A refusal ran nothing, so there are no bytes to bind to a
            # retained member. `77001fc` made refusal the only outcome
            # besides execution, and left the check below reading every
            # non-incumbent record as one that ran -- so a refused episode
            # was reported as `use-without-retained`, an export failing
            # over a use phase that was told to stand down. It is checked
            # for the shape a refusal must still carry instead, which is
            # what `checker._verify_refusal` already holds the records to.
            if record.get("status") == "refused":
                problems.extend(checker._verify_refusal(
                    record, str(record.get("record_id", "?"))))
                checked += 1
                continue
            if selected == "incumbent":
                if executed != "incumbent":
                    problems.append("incumbent-bytes-mismatch %s" % (
                        record.get("record_id"),))
                checked += 1
                continue
            retained_source = by_capability.get(selected)
            if retained_source is None:
                problems.append("use-without-retained %s" % (
                    record.get("record_id"),))
                continue
            if executed != retained_source:
                problems.append("fresh-process-bytes-mismatch %s" % (
                    record.get("record_id"),))
                continue
            checked += 1
    return {"checked": checked, "problems": problems}


def recompute_accounting(export: dict, use_records: list) -> dict:
    model_calls = 0
    construction_calls = 0
    witness_queries = 0
    for transition in export.get("transitions", []):
        costs = dict(transition.get("costs_measured") or {})
        model_calls += int(costs.get("model_calls", 0))
        episode = dict(transition.get("episode") or {})
        construction_calls += int(episode.get("construction_calls", 0))
        witness_queries += int(episode.get("queries", 0))
    use_queries = sum(int(r.get("costs", {}).get(
        "witness_queries", 0) or 0) for r in use_records)
    return {"campaign_id": export.get("campaign_id"),
            "total": {"model_calls": model_calls,
                      "construction_calls": construction_calls,
                      "witness_queries": witness_queries + use_queries,
                      "use_records": len(use_records)},
            "acquisition": {"model_calls": model_calls,
                            "construction_calls": construction_calls,
                            "witness_queries": witness_queries},
            "use": {"witness_queries": use_queries,
                    "use_records": len(use_records)}}


def _is_count(value) -> bool:
    return type(value) is int and value >= 0


def recompute_from_corpus(export: dict, use_records: list | None) -> dict:
    operations = {r.get("id"): r for r in export.get("operations", [])
                  if isinstance(r, dict)}
    model_calls = 0
    construction_ops = 0
    witness_acquisition = 0
    unknown: list = []
    for transition in export.get("transitions", []):
        for op_id in transition.get("operations", []) or []:
            row = operations.get(op_id)
            if row is None:
                continue
            effect = str(dict(row.get("payload") or {}).get("effect", ""))
            if effect == "model-inference" and (
                    "-learner-" in op_id or "-construct-" in op_id):
                model_calls += 1
            if effect == "model-inference" and (
                    "-construct-" in op_id or "-policy-" in op_id):
                construction_ops += 1
        queries = (transition.get("episode") or {}).get("queries")
        if _is_count(queries):
            witness_acquisition += queries
        else:
            unknown.append("unknown-queries transition-%s" % (
                transition.get("index")))
    use_queries = 0
    use_count = 0
    if isinstance(use_records, list):
        use_count = len(use_records)
        for record in use_records:
            queries = (record.get("costs") or {}).get("witness_queries")
            if _is_count(queries):
                use_queries += queries
            elif queries == "unknown":
                unknown.append("unknown-cost %s" % (
                    record.get("record_id", "?")))
            else:
                unknown.append("bad-cost %s" % (
                    record.get("record_id", "?")))
    return {"model_calls": model_calls,
            "construction_ops": construction_ops,
            "witness_acquisition": witness_acquisition,
            "witness_use": use_queries,
            "witness_total": witness_acquisition + use_queries,
            "use_records": use_count,
            "unknown": sorted(set(unknown))}


def verify_campaign(export: dict, use_records: list | None,
                    expected: dict | None = None) -> dict:
    from . import checker, worlds
    problems: list = []
    if not isinstance(export, dict) or not export.get("transitions") \
            or not isinstance(export.get("operations"), list) \
            or not isinstance(export.get("identities"), dict):
        return {"status": "incomplete", "problems": ["incomplete-export"],
                "recomputed": recompute_from_corpus(
                    export if isinstance(export, dict) else {}, [])}
    supplied_use_records = list(use_records or []) if isinstance(
        use_records, list) else []
    problems.extend(_verify_policy_export(export, supplied_use_records))
    use_records = [record for record in supplied_use_records
                   if not isinstance(record, dict)
                   or not record.get("release_id")]
    expected = dict(expected or {})
    freeze = export.get("identities", {})
    if freeze.get("freeze_id") != worlds.FREEZE_ID or freeze.get(
            "freeze_digest") != checker.freeze_digest(worlds.FROZEN_DIR):
        problems.append("freeze-mismatch %s" % (export.get("campaign_id")))
    if expected.get("campaign_id") and export.get("campaign_id") != \
            expected["campaign_id"]:
        problems.append("campaign-mismatch %s" % (
            export.get("campaign_id")))
    transitions = list(export.get("transitions", []))
    indices = [t.get("index") for t in transitions]
    if len(set(indices)) != len(indices):
        problems.append("duplicate-transition %s" % (sorted(indices),))
    want_seqs = list(expected.get("seqs", []))
    if want_seqs:
        for seq in sorted(set(want_seqs) - set(indices)):
            problems.append("missing-transition %s" % (seq,))
        for seq in sorted(set(indices) - set(want_seqs)):
            problems.append("unexpected-transition %s" % (seq,))
    elif indices != list(range(len(transitions))):
        problems.append("phase-incomplete indices=%s" % (sorted(indices),))
    op_ids = [r.get("id") for r in export.get("operations", [])]
    if len(set(op_ids)) != len(op_ids):
        problems.append("duplicate-operation")
    op_set = set(op_ids)
    seen_ops: set = set()
    for transition in transitions:
        seq = transition.get("index")
        for key in ("decision", "observation", "episode", "operations",
                    "receipts", "raw_responses", "delivered_requests",
                    "corrections", "packet"):
            if key not in transition:
                problems.append("phase-incomplete transition-%s"
                                " missing-%s" % (seq, key))
        if transition.get("packet_source") != "reconstructed":
            problems.append("packet-unlabeled transition-%s" % (seq,))
        for op_id in transition.get("operations", []) or []:
            if op_id not in op_set:
                problems.append("unattributed-operation %s" % (op_id,))
            if op_id in seen_ops:
                problems.append("duplicate-operation-across-transitions"
                                " %s" % (op_id,))
            seen_ops.add(op_id)
        receipts = {r.get("receipt_identity"): r
                    for r in transition.get("receipts", []) or []}
        for receipt in transition.get("receipts", []) or []:
            if receipt.get("operation_id") not in (
                    transition.get("operations", []) or []):
                problems.append("receipt-attribution %s" % (
                    receipt.get("receipt_identity"),))
        for raw in transition.get("raw_responses", []) or []:
            receipt = receipts.get(raw.get("receipt_identity"))
            if receipt is None:
                problems.append("missing-receipt %s" % (
                    raw.get("receipt_identity"),))
        delivered = {d.get("operation_id") for d in
                     transition.get("delivered_requests", []) or []}
        for op_id in transition.get("operations", []) or []:
            if op_id not in delivered:
                problems.append("missing-delivered-request %s" % (op_id,))
            if not [r for r in transition.get("receipts", []) or []
                    if r.get("operation_id") == op_id]:
                problems.append("missing-receipt for-operation %s" % (
                    op_id,))
        base, correction = _learner_op_ids(
            str(export.get("campaign_id")), int(seq))
        learner_ops = [o for o in transition.get("operations", []) or []
                       if o == base or o.startswith(correction)]
        if len(learner_ops) != len(
                [d for d in transition.get("delivered_requests", [])
                 or [] if d.get("operation_id") == base or d.get(
                     "operation_id", "").startswith(correction)]):
            problems.append("correction-delivery-mismatch"
                            " transition-%s" % (seq,))
        corrections = list(transition.get("corrections", []) or [])
        correction_ops = [o for o in learner_ops if o.startswith(
            correction)]
        if len(corrections) != len(correction_ops):
            problems.append("correction-count-mismatch transition-%s"
                            " corrections=%d operations=%d" % (
                                seq, len(corrections),
                                len(correction_ops)))
        costs = dict(transition.get("costs_measured") or {})
        episode = dict(transition.get("episode") or {})
        if costs.get("witness_queries") != episode.get("queries"):
            problems.append("query-total-mismatch transition-%s" % (seq,))
    top_learner = [o for o in op_ids if "-learner-" in o]
    for op_id in top_learner:
        if op_id not in seen_ops:
            problems.append("missing-correction-operation %s" % (op_id,))
    recomputed = recompute_from_corpus(export, use_records)
    reported_model = sum(int(dict(t.get("costs_measured") or {}).get(
        "model_calls", 0)) for t in transitions)
    if reported_model != recomputed["model_calls"]:
        problems.append("model-call-mismatch reported=%d recomputed=%d"
                        % (reported_model, recomputed["model_calls"]))
    reported_construction = sum(int(dict(t.get("episode") or {}).get(
        "construction_calls", 0) or 0) for t in transitions)
    if reported_construction != recomputed["construction_ops"]:
        problems.append("construction-call-mismatch reported=%d"
                        " recomputed=%d" % (
                            reported_construction,
                            recomputed["construction_ops"]))
    record_ids = [r.get("record_id") for r in use_records]
    if len(set(record_ids)) != len(record_ids):
        problems.append("duplicate-record %s" % (sorted(record_ids),))
    want_uses = list(expected.get("use_record_ids", []))
    if want_uses:
        for rid in sorted(set(want_uses) - set(record_ids)):
            problems.append("missing-use-record %s" % (rid,))
        for rid in sorted(set(record_ids) - set(want_uses)):
            problems.append("unexpected-use-record %s" % (rid,))
    for record in use_records:
        if record.get("freeze") != worlds.FREEZE_ID or record.get(
                "freeze_digest") != checker.freeze_digest(
                    worlds.FROZEN_DIR):
            problems.append("wrong-freeze-reference %s" % (
                record.get("record_id"),))
    chain = verify_byte_chain(export, use_records=use_records)
    problems.extend(chain.get("problems", []))
    if recomputed.get("unknown"):
        for marker in recomputed["unknown"]:
            if marker.startswith("bad-cost"):
                problems.append(marker)
    status = "pass" if not problems else "fail"
    return {"status": status, "problems": sorted(set(problems)),
            "recomputed": recomputed}


def verify_study(exports: list, use_records: list | None,
                 expected: dict | None = None) -> dict:
    problems: list = []
    if not isinstance(exports, list) or not exports:
        return {"status": "incomplete",
                "problems": ["incomplete-study-exports"],
                "recomputed": {}}
    if not isinstance(use_records, list):
        return {"status": "incomplete",
                "problems": ["incomplete-use-evidence"],
                "recomputed": {}}
    expected = dict(expected or {})
    campaign_ids = [e.get("campaign_id") for e in exports]
    if len(set(campaign_ids)) != len(campaign_ids):
        problems.append("duplicate-trajectory %s" % (
            sorted(campaign_ids),))
    want_campaigns = list(expected.get("campaign_ids", []))
    if want_campaigns:
        for cid in sorted(set(want_campaigns) - set(campaign_ids)):
            problems.append("missing-trajectory %s" % (cid,))
        for cid in sorted(set(campaign_ids) - set(want_campaigns)):
            problems.append("unexpected-trajectory %s" % (cid,))
    totals = {"model_calls": 0, "construction_ops": 0,
              "witness_total": 0, "use_records": len(use_records)}
    for export in exports:
        result = verify_campaign(
            export, [], expected={"campaign_id": export.get(
                "campaign_id")})
        problems.extend("%s: %s" % (export.get("campaign_id"), p)
                        for p in result.get("problems", []))
        recomputed = result.get("recomputed", {})
        totals["model_calls"] += int(recomputed.get("model_calls", 0))
        totals["construction_ops"] += int(recomputed.get(
            "construction_ops", 0))
        totals["witness_total"] += int(recomputed.get(
            "witness_acquisition", 0))
    record_ids = [r.get("record_id") for r in use_records]
    if len(set(record_ids)) != len(record_ids):
        problems.append("duplicate-record %s" % (sorted(record_ids),))
    want_uses = list(expected.get("use_record_ids", []))
    if want_uses:
        for rid in sorted(set(want_uses) - set(record_ids)):
            problems.append("missing-use-record %s" % (rid,))
    use_queries = 0
    for record in use_records:
        queries = (record.get("costs") or {}).get("witness_queries")
        if _is_count(queries):
            use_queries += queries
    totals["witness_total"] += use_queries
    totals["use_queries"] = use_queries
    chain_problems = []
    for export in exports:
        chain = verify_byte_chain(export, use_records=use_records
                                  if len(exports) == 1 else None)



        chain_problems.extend(chain.get("problems", []))
    problems.extend(chain_problems)
    status = "pass" if not problems else "fail"
    return {"status": status, "problems": sorted(set(problems)),
            "recomputed": totals}


def _walk_values(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _sensitive_literals(task: dict) -> set[str]:
    import json
    values: set[str] = set()
    for key in ("sealed", "protected"):
        if key in task:
            for value in _walk_values(task[key]):
                if isinstance(value, str) and value:
                    values.add(value)
    if "witness" in task:
        values.add(json.dumps(task["witness"], sort_keys=True,
                              separators=(",", ":")))
    return values


def _policy_decision(candidate: dict, incumbent: dict, rule: dict) -> str:
    cq = candidate["quality"]
    iq = incumbent["quality"]
    if cq["preserved"] < rule["min_preserved"]:
        return "reject"
    if cq["reduced"] - iq["reduced"] < rule["margin"]:
        return "reject"
    candidate_cost = candidate["resources"]["queries"] + candidate[
        "resources"]["model_calls"]
    incumbent_cost = incumbent["resources"]["queries"] + incumbent[
        "resources"]["model_calls"]
    if candidate_cost - incumbent_cost > rule["resource_ceiling"]:
        return "reject"
    return "bind"


def _verify_policy_export(export: dict, use_records: list) -> list:
    """Verify bytes, conformance, quality and leakage offline.

    Resource measurements are runtime attestations and cannot be recomputed
    offline. Byte identity, artifact conformance, quality and leakage are
    independently recomputable from the export and the frozen corpus.
    """
    import hashlib
    import json
    from . import method_exec, packet, policy_step, trajectory, worlds
    policies = list(export.get("policy_revisions") or [])
    if not policies and isinstance(export.get("policy"), dict):
        policies = [export["policy"]]
    problems = []
    serialized = json.dumps(export, sort_keys=True, separators=(",", ":"),
                           default=str)
    known_keys = set(packet.SEALED_KEYS) | {"protected_answer", "sealed_value"}
    for value in _walk_values(export):
        if isinstance(value, dict):
            for key in value:
                if key in known_keys:
                    problems.append("V9a: sealed key %s is exported" % key)
    for policy in policies:
        if not isinstance(policy, dict):
            problems.append("V1: policy revision is not an object")
            continue
        assessment = policy.get("assessment")
        refusal = policy.get("refusal")
        outcome = ((assessment or {}).get("outcome") or
                   (refusal or {}).get("outcome"))
        source = policy.get("source")
        source_digest = (hashlib.sha256(source.encode("utf-8")).hexdigest()
                         if isinstance(source, str) else "")
        freeze = dict(policy.get("freeze") or {})
        proposal = dict(policy.get("proposal") or {})
        artifact = dict(policy.get("artifact") or {})
        binding = policy.get("binding")
        provenance = dict((binding or {}).get("invalidation") or {})
        if outcome != "unavailable" and isinstance(source, str) and source:
            digest_fields = [("policy source", source_digest),
                             ("policy source_digest", policy.get(
                                 "source_digest")),
                             ("freeze candidate_digest", freeze.get(
                                 "candidate_digest")),
                             ("assessment candidate_digest", (assessment or {}).get(
                                 "candidate_digest"))]
            if binding is not None:
                digest_fields.append(("binding provenance candidate_digest",
                                      provenance.get("candidate_digest")))
            for field, value in digest_fields:
                if value != source_digest:
                    problems.append("V1: %s digest mismatch" % field)
            if artifact.get("kind") != "learning-policy":
                problems.append("V2: artifact kind")
            if artifact.get("entry") != "STEP":
                problems.append("V2: artifact entry")
            if artifact.get("abi") != policy_step.POLICY_STEP_VERSION:
                problems.append("V2: artifact abi")
            if artifact.get("parent_digest") != proposal.get("parent_digest"):
                problems.append("V2: artifact parent_digest")
            if dict(artifact.get("applicability") or {}) != dict(
                    proposal.get("scope") or {}):
                problems.append("V2: artifact applicability")
            try:
                method_exec.verify_step_source(source, artifact.get("entry"))
            except Exception as exc:
                problems.append("V3: static STEP source validation: %s" % exc)
        if assessment is None:
            if outcome is None:
                problems.append("V4: assessment missing")
                continue
            if outcome in ("reject", "unavailable"):
                refusal = policy.get("refusal")
                if not isinstance(refusal, dict) or not refusal.get("reason"):
                    problems.append("V7: durable refusal record")
            continue
        panel = dict(policy.get("panel") or {})
        rule = dict(policy.get("rule") or {})
        task_ids = list(panel.get("task_ids") or [])
        journal = dict(policy.get("journal") or {})
        protocol_position = journal.get("protocol")
        assessment_position = journal.get("assessment")
        if not isinstance(protocol_position, int) or not isinstance(
                assessment_position, int) or protocol_position >= assessment_position:
            problems.append("V4: panel/rule freeze journal position")
        for name in ("candidate", "incumbent"):
            arm = dict((policy.get("arms") or {}).get(name) or {})
            for decision in arm.get("decisions") or []:
                if not isinstance(decision.get("journal_position"), int) or \
                        decision["journal_position"] <= protocol_position:
                    problems.append("V4: %s assessment step journal position" % name)
            arm_tasks = list(arm.get("panel_task_ids") or [])
            if arm_tasks != task_ids:
                problems.append("V11: %s panel task ids" % name)
            if arm.get("rule_id") != rule.get("rule_id"):
                problems.append("V11: %s rule id" % name)
            if arm.get("evaluator_version") != (assessment.get(
                    "evaluator_version", "")):
                problems.append("V11: %s evaluator version" % name)
            resources = dict(arm.get("resources") or {})
            steps = resources.get("step_calls")
            if not isinstance(steps, int) or steps <= 0:
                problems.append("V11: %s step_calls" % name)
            if len(arm.get("decisions") or []) != steps:
                problems.append("V6: %s decisions length" % name)
            if len(arm.get("action_kinds") or []) != steps:
                problems.append("V12: %s action sequence length" % name)
            for index, decision in enumerate(arm.get("decisions") or []):
                if index >= len(arm.get("action_kinds") or []) or \
                        arm["action_kinds"][index] != decision.get("kind"):
                    problems.append("V12: %s action sequence" % name)
            effects = list(arm.get("effects") or [])
            if len(effects) != len(arm.get("decisions") or []):
                problems.append("V12: %s effects length" % name)
            for index, effect in enumerate(effects):
                if not isinstance(effect.get("accepted"), bool):
                    problems.append("V12: %s effect accepted flag" % name)
                if index < len(arm.get("decisions") or []) and \
                        effect.get("kind") != arm["decisions"][index].get("kind"):
                    problems.append("V12: %s effect sequence" % name)
            if outcome in ("bind", "reject"):
                outputs = list(arm.get("outputs") or [])
                if [item.get("task_id") for item in outputs] != task_ids:
                    problems.append("V5a: %s output task ids" % name)
                preserved = reduced = 0
                for item in outputs:
                    task_id = item.get("task_id")
                    try:
                        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                        output = item.get("output")
                        if output is None:
                            report = {"verdict": "failed"}
                            initial = final = trajectory._size(task, task)[0]
                        else:
                            report = trajectory._check(task, output)
                            initial, final = trajectory._size(task, output)
                        if report.get("verdict") == "preserved":
                            preserved += 1
                            if final < initial:
                                reduced += 1
                    except Exception as exc:
                        problems.append("V5a: %s output %s: %s" % (
                            name, task_id, exc))
                recomputed_quality = {"tasks": len(outputs),
                                      "preserved": preserved,
                                      "reduced": reduced,
                                      "failed": len(outputs) - preserved}
                if recomputed_quality != dict(arm.get("quality") or {}):
                    problems.append("V5a: %s quality counts" % name)
        candidate_arm = dict((policy.get("arms") or {}).get("candidate") or {})
        incumbent_arm = dict((policy.get("arms") or {}).get("incumbent") or {})
        if outcome in ("bind", "reject"):
            if _policy_decision(candidate_arm, incumbent_arm, rule) != outcome:
                problems.append("V5a: recorded outcome")
        if outcome == "bind":
            if not isinstance(binding, dict):
                problems.append("V7: binding row missing")
            else:
                refs = list(binding.get("evidence_refs") or [])
                attempt_id = assessment.get("attempt_id")
                if attempt_id not in refs:
                    problems.append("V7: binding evidence refs")
                for field in ("protocol_id", "evaluator_version"):
                    if binding.get(field) != assessment.get(field):
                        problems.append("V7: binding %s" % field)
                if dict(binding.get("scope") or {}) != dict(
                        assessment.get("scope") or {}):
                    problems.append("V7: binding scope")
        elif outcome in ("reject", "unavailable") and binding is not None:
            problems.append("V7: refusal has a release binding")
        if outcome in ("reject", "unavailable"):
            refusal = policy.get("refusal")
            if not isinstance(refusal, dict) or not refusal.get("reason"):
                problems.append("V7: durable refusal record")
        panel_values = set()
        for task_id in task_ids:
            try:
                task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                panel_values.update(_sensitive_literals(task))
            except Exception as exc:
                problems.append("V9a: panel task %s unavailable: %s" % (
                    task_id, exc))
        for value in panel_values:
            if value in serialized:
                problems.append("V9a: sealed value leaked")
                break
        campaign_task_ids = set(policy.get("campaign_task_ids") or [])
        if set(task_ids) & campaign_task_ids:
            problems.append("V10: panel overlaps campaign task list")
        development_ids = {str(t.get("task_id")) for t in export.get(
            "transitions", []) if dict(t.get("episode") or {}).get(
                "kind", "development") == "development"}
        if set(task_ids) & development_ids:
            problems.append("V10: panel overlaps development tasks")
    for record in use_records:
        if not isinstance(record, dict) or not record.get("release_id"):
            continue
        matching = [p for p in policies if isinstance(p.get("binding"), dict)
                    and p["binding"].get("id") == record.get("release_id")]
        if not matching:
            problems.append("V8: use record release binding")
            continue
        digest = dict(matching[0].get("binding", {}).get(
            "invalidation") or {}).get("candidate_digest")
        if record.get("executed_source_digest") != digest and not str(
                record.get("fallback_reason") or ""):
            problems.append("V8: use record executed digest/fallback_reason")
    return problems
REVISION_PROTOCOL = "s09-revision-v1"


def proposal_id_for(investigation_id: str, parent_digest: str,
                    task_id: str, scope: dict) -> str:
    import hashlib
    import json
    raw = json.dumps({"investigation": investigation_id,
                      "parent": parent_digest,
                      "task": task_id,
                      "scope": dict(scope or {})},
                     sort_keys=True).encode()
    return "s09-rev-%s-%s" % (investigation_id,
                              hashlib.sha256(raw).hexdigest()[:12])


def _proposal_request_id(proposal_id: str) -> str:
    return "s09-rev-%s" % proposal_id


def _freeze_request_id(proposal_id: str) -> str:
    return "s09-freeze-%s" % proposal_id


def open_revision_proposal(dsn: str, *, investigation_id: str,
                           parent_digest: str,
                           failure_record: dict,
                           scope: dict,
                           protocol_id: str = REVISION_PROTOCOL,
                           allocation_id: str = "") -> dict:
    from settlement import store
    from settlement.common import Command, ResultCode
    if not investigation_id or not parent_digest:
        raise ValueError("proposal needs an investigation and parent digest")
    if not isinstance(failure_record, dict) or not failure_record.get(
            "task_id"):
        raise ValueError("proposal needs a pinned operational failure")
    pinned = str(failure_record.get("parent_digest", "")
                 or failure_record.get("source_digest", "")
                 or failure_record.get("digest", ""))
    if pinned and pinned != parent_digest:
        raise ValueError("failure pins %r, not parent %r"
                         % (pinned, parent_digest))
    task_id = str(failure_record["task_id"])
    proposal_id = proposal_id_for(investigation_id, parent_digest,
                                  task_id, scope)
    proposal = {"proposal_id": proposal_id,
                "investigation_id": investigation_id,
                "parent_digest": parent_digest,
                "failure_record": dict(failure_record),
                "scope": dict(scope or {}),
                "protocol_id": protocol_id,
                "allocation_id": allocation_id,
                "status": "open"}
    result = store.transact(
        dsn, Command(request_id=_proposal_request_id(proposal_id),
                     payload=proposal),
        lambda cur, control: (ResultCode.APPLIED, "revision proposed",
                              proposal, [], []))
    if result.code not in (ResultCode.APPLIED,
                           ResultCode.ALREADY_APPLIED):
        raise ValueError("proposal not persisted: %s" % result.detail)
    return dict(result.data) if result.data else proposal


def load_revision_proposal(dsn: str, proposal_id: str) -> dict | None:
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT result_data FROM command_journal WHERE request_id = %s",
            (_proposal_request_id(proposal_id),)).fetchone()
        conn.commit()
        return dict(row["result_data"]) if row is not None else None


def freeze_candidate(dsn: str, *, proposal_id: str,
                     source_bytes: str, entry: str) -> dict:
    import hashlib
    from settlement import store
    from settlement.common import Command, ResultCode
    if not proposal_id or not source_bytes or not entry:
        raise ValueError("freeze needs a proposal, bytes and entry")
    proposal = load_revision_proposal(dsn, proposal_id)
    if proposal is None:
        raise ValueError("no persisted proposal %r" % (proposal_id,))
    candidate_digest = hashlib.sha256(
        source_bytes.encode("utf-8")).hexdigest()
    freeze = {"proposal_id": proposal_id,
              "candidate_digest": candidate_digest,
              "entry": entry,
              "bytes": len(source_bytes.encode("utf-8")),
              "source": source_bytes}
    existing = load_freeze(dsn, proposal_id)
    if existing is not None:
        if existing.get("candidate_digest") != candidate_digest:
            raise ValueError(
                "proposal %r already froze %r; open a new revision"
                " for different bytes" % (
                    proposal_id, existing.get("candidate_digest")))
        return existing
    result = store.transact(
        dsn, Command(request_id=_freeze_request_id(proposal_id),
                     payload={"proposal_id": proposal_id,
                              "candidate_digest": candidate_digest,
                              "entry": entry}),
        lambda cur, control: (ResultCode.APPLIED, "candidate frozen",
                              freeze, [], []))
    if result.code not in (ResultCode.APPLIED,
                           ResultCode.ALREADY_APPLIED):
        raise ValueError("freeze not persisted: %s" % result.detail)
    return dict(result.data) if result.data else freeze


def load_freeze(dsn: str, proposal_id: str) -> dict | None:
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT result_data FROM command_journal WHERE request_id = %s",
            (_freeze_request_id(proposal_id),)).fetchone()
        conn.commit()
        return dict(row["result_data"]) if row is not None else None


def assessment_attempt_id(proposal_id: str,
                          candidate_digest: str) -> str:
    return "s09-assess-%s-%s" % (proposal_id, candidate_digest[:12])


def assessment_request_id(proposal_id: str,
                          candidate_digest: str) -> str:
    return assessment_attempt_id(proposal_id, candidate_digest)


def load_assessment(dsn: str, proposal_id: str,
                    candidate_digest: str) -> dict | None:
    with _read_conn(dsn) as conn:
        row = conn.execute(
            "SELECT result_data FROM command_journal WHERE request_id = %s",
            (assessment_request_id(proposal_id, candidate_digest),)
            ).fetchone()
        conn.commit()
        return dict(row["result_data"]) if row is not None else None


def _verdict_view(record: dict) -> dict:
    view = {"proposal_id": record.get("proposal_id"),
            "outcome": record.get("outcome"),
            "reason": record.get("reason", ""),
            "attempt_id": record.get("attempt_id"),
            "candidate_digest": record.get("candidate_digest"),
            "scope": dict(record.get("scope") or {}),
            "evaluator_version": record.get("evaluator_version", ""),
            "protocol_id": record.get("protocol_id", ""),
            "tasks": list(record.get("tasks") or [])}
    if record.get("queries") is not None:
        view["queries"] = record["queries"]
    if record.get("checked") is not None:
        view["checked"] = record["checked"]
    return view


def execution_identity(*, investigation_id: str, logical_action: str,
                       policy_version: str, method_version: str,
                       attempt: str) -> str:
    return "%s:%s:%s:%s:%s" % (investigation_id, logical_action,
                               policy_version, method_version, attempt)


def assess_frozen(dsn: str, *, proposal_id: str, tasks: list,
                  baseline: str = "incumbent", evaluator_version: str = "",
                  protocol_id: str = "") -> dict:
    from settlement import store
    from settlement.common import Command, ResultCode
    if not tasks:
        raise ValueError("assess needs a non-empty task panel")
    freeze = load_freeze(dsn, proposal_id)
    if freeze is None:
        raise ValueError("assess needs frozen bytes for %r" % (
            proposal_id,))
    proposal = load_revision_proposal(dsn, proposal_id) or {}
    effective_protocol = protocol_id or str(proposal.get("protocol_id", ""))
    digest = freeze.get("candidate_digest", "")
    stored = load_assessment(dsn, proposal_id, digest)
    if stored is not None:
        if (stored.get("protocol_id") != effective_protocol or
                stored.get("evaluator_version") != evaluator_version or
                list(stored.get("tasks") or []) != list(tasks)):
            raise ValueError("assessment request differs from stored attempt")
        return _verdict_view(stored)
    verdict = _execute_assessment(
        proposal_id, list(tasks), baseline, freeze)
    record = {**verdict, "candidate_digest": digest,
              "scope": dict(proposal.get("scope") or {}),
              "evaluator_version": evaluator_version,
              "protocol_id": effective_protocol,
              "tasks": list(tasks)}
    result = store.transact(
        dsn, Command(
            request_id=assessment_request_id(proposal_id, digest),
            payload={"proposal_id": proposal_id,
                     "candidate_digest": digest,
                     "evaluator_version": evaluator_version,
                     "protocol_id": record["protocol_id"],
                     "tasks": list(tasks)}),
        lambda cur, control: (ResultCode.APPLIED, verdict["outcome"],
                              record, [], []))
    if result.code == ResultCode.ALREADY_APPLIED and result.data:
        return _verdict_view(dict(result.data))
    if result.code not in (ResultCode.APPLIED,
                            ResultCode.ALREADY_APPLIED):
        raise ValueError("assessment not persisted: %s" % result.detail)
    return _verdict_view(record)


def _execute_assessment(proposal_id: str, tasks: list,
                        baseline: str, freeze: dict) -> dict:
    from . import method_exec, worlds
    source = freeze.get("source", "")
    entry = freeze.get("entry", "")
    try:
        method_exec.verify_member(
            {"method_source": source, "entry": entry})
    except method_exec.MethodExecutionError as exc:
        return {"proposal_id": proposal_id, "outcome": "reject",
                "reason": "frozen bytes invalid: %s" % exc,
                "attempt_id": assessment_attempt_id(
                    proposal_id, freeze.get("candidate_digest", ""))}
    wins = 0
    checked = 0
    queries = 0
    for task_id in tasks:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        member = {"capability_id": "assess-%s" % proposal_id,
                  "method_source": source, "entry": entry,
                  "params": {"max_queries": 4},
                  "scope": {"family": task["family"]},
                  "authored": False}
        try:
            result = method_exec.run_member_out_of_process(
                member, task, max_queries=4)
        except method_exec.MethodExecutionError as exc:
            return {"proposal_id": proposal_id, "outcome": "reject",
                    "reason": "execution failed on %s: %s" % (
                        task_id, exc),
                    "attempt_id": assessment_attempt_id(
                        proposal_id, freeze.get(
                            "candidate_digest", ""))}
        from .trajectory import _check, _size
        report = _check(task, result["candidate"])
        queries += int(result.get("queries", 0))
        if report.get("verdict") != "preserved":
            return {"proposal_id": proposal_id, "outcome": "reject",
                    "reason": "not preserved on %s: %s" % (
                        task_id, report.get("reason", "")),
                    "attempt_id": assessment_attempt_id(
                        proposal_id, freeze.get(
                            "candidate_digest", "")),
                    "queries": queries}
        checked += 1
        _, final = _size(task, result["candidate"])
        initial, _ = _size(task, task)
        if final < initial:
            wins += 1
    _ = baseline
    if wins > 0:
        outcome = "bind"
        reason = "preserved with reduction on %d/%d" % (wins, checked)
    else:
        outcome = "reject"
        reason = "preserved without reduction"
    return {"proposal_id": proposal_id, "outcome": outcome,
            "reason": reason,
            "attempt_id": assessment_attempt_id(
                proposal_id, freeze.get("candidate_digest", "")),
            "queries": queries, "checked": checked}
