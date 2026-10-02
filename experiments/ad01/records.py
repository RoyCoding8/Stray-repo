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
                if "-construct-" in op_id:
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
    if not isinstance(use_records, list):
        return {"status": "incomplete",
                "problems": ["incomplete-use-evidence"],
                "recomputed": recompute_from_corpus(export, [])}
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
