"""M4 offline recomputation for the E1/E2 prospective comparison.

Deterministic file and memory input only. No gateway, database, network,
environment or clock access. Quality is derived from frozen tasks plus
recorded observable behavior; runtime verdict labels are cross-checked,
never trusted. Resource consumption is a runtime attestation named by
its declared measurement source; unknown billing stays unknown.
"""

from __future__ import annotations

import hashlib
import json

ARMS = ("P0", "P1", "P2")
ACQUIRED_ARMS = ("P1", "P2")

RESOURCE_CLASSES = (
    "model_dispatches",
    "input_tokens",
    "output_tokens",
    "tool_queries",
    "child_compute_ms",
    "billed_units",
    "unresolved_exposure",
    "human_interventions",
)

RECOUNTABLE = ("model_dispatches", "tool_queries", "unresolved_exposure")

MEASUREMENT_BOUNDARY = (
    "Resource consumption is a runtime attestation named by "
    "accounting[<class>].source. The offline verifier recounts model "
    "dispatches, tool queries and unresolved exposure from operations, "
    "episodes and cost fields, and refuses unknown-as-zero billing, but "
    "cannot independently measure tokens, child compute or billed units. "
    "Unknown stays unknown."
)

ARTIFACT_KIND = "learning-policy"
POLICY_ABI = "ad01-policy-step-v1"

FREEZE_REQUIRED = (
    "study_id", "study_root", "arms", "order", "development",
    "assessment", "audit", "construction_allowance", "caps",
    "metric_rule", "resource_rule", "config", "policy_identities",
    "method_repertoires", "tasks", "freeze_digest",
)


def canonical(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def freeze_digest(freeze: dict) -> str:
    body = {key: value for key, value in freeze.items()
            if key != "freeze_digest"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def reserve_allowance(arms, init: int, repair: int) -> dict:
    if type(init) is not int or type(repair) is not int:
        raise ValueError("allowance needs integer init and repair")
    if init < 0 or repair < 0:
        raise ValueError("allowance cannot be negative")
    return {str(arm): {"init": init, "repair": repair} for arm in arms}


def study_worst_case(freeze: dict) -> int:
    episodes = len(freeze.get("development", [])) + len(
        freeze.get("assessment", [])) + len(freeze.get("audit", []))
    per = freeze.get("caps", {}).get("per_episode", {}).get("model_calls", 0)
    allowance = freeze.get("construction_allowance", {})
    reserved = sum(int(allowance.get(arm, {}).get("init", 0))
                   + int(allowance.get(arm, {}).get("repair", 0))
                   for arm in ACQUIRED_ARMS)
    return episodes * per + reserved


def _is_count(value) -> bool:
    return type(value) is int and value >= 0


def _check_freeze(bundle: dict, problems: list) -> dict | None:
    freeze = bundle.get("freeze")
    if not isinstance(freeze, dict):
        problems.append("missing-freeze")
        return None
    for key in FREEZE_REQUIRED:
        if key not in freeze:
            problems.append("freeze-incomplete missing-%s" % key)
    if freeze.get("freeze_digest") != freeze_digest(freeze):
        problems.append("freeze-digest-mismatch")
    if list(freeze.get("arms", [])) != list(ARMS):
        problems.append("arms-mismatch")
    if freeze.get("config", {}).get("artifact_kind") != ARTIFACT_KIND:
        problems.append("policy-artifact-kind-missing")
    if freeze.get("config", {}).get("abi") != POLICY_ABI:
        problems.append("policy-abi-missing")
    allowance = freeze.get("construction_allowance", {})
    if allowance.get("P1") != allowance.get("P2"):
        problems.append("allowance-unequal")
    return freeze


def _check_identities(freeze: dict, problems: list) -> dict:
    identities = freeze.get("policy_identities")
    if not isinstance(identities, dict):
        problems.append("policy-identities-missing")
        return {}
    for arm in ARMS:
        identity = identities.get(arm)
        if not isinstance(identity, dict):
            problems.append("policy-identity-missing %s" % arm)
            continue
        status = identity.get("status")
        if status not in ("available", "unavailable"):
            problems.append("identity-status-missing %s" % arm)
            continue
        if not _is_count(identity.get("history_tokens")):
            problems.append("unknown-history-tokens %s" % arm)
        if not _is_count(identity.get("failed_attempts")):
            problems.append("unknown-failed-attempts %s" % arm)
        if status == "unavailable":
            if not identity.get("reason"):
                problems.append("unavailable-without-reason %s" % arm)
            continue
        source = identity.get("source")
        digest = identity.get("source_digest")
        if not isinstance(source, str) or not source or \
                digest != source_digest(source):
            problems.append("identity-digest-mismatch %s" % arm)
        artifact = identity.get("artifact")
        if not isinstance(artifact, dict) or artifact.get(
                "source_digest") != digest or artifact.get(
                "kind") != ARTIFACT_KIND or artifact.get(
                "abi") != POLICY_ABI:
            problems.append("identity-artifact-mismatch %s" % arm)
    return identities if isinstance(identities, dict) else {}


def _check_repertoires(freeze: dict, problems: list) -> dict:
    repertoires = freeze.get("method_repertoires")
    if not isinstance(repertoires, dict):
        problems.append("method-repertoires-missing")
        return {}
    digests = {}
    for arm in ARMS:
        repertoire = repertoires.get(arm)
        if not isinstance(repertoire, dict):
            problems.append("method-repertoire-missing %s" % arm)
            continue
        found = set()
        for member in repertoire.get("members", []) or []:
            source = member.get("method_source") if isinstance(
                member, dict) else None
            digest = member.get("source_digest") if isinstance(
                member, dict) else None
            if not isinstance(source, str) or digest != source_digest(
                    source):
                problems.append(
                    "method-bytes-digest-mismatch %s" % arm)
            elif digest:
                found.add(digest)
        digests[arm] = found
        if sorted(found) != sorted(
                repertoire.get("member_digests", [])):
            problems.append(
                "method-repertoire-digests-mismatch %s" % arm)
    return digests


def _split_tasks(freeze: dict, problems: list) -> tuple:
    dev = {e.get("task_id") for e in freeze.get("development", [])
           if isinstance(e, dict)}
    assess = {task for e in freeze.get("assessment", [])
              if isinstance(e, dict)
              for task in e.get("use_tasks", []) or []}
    audit = {task for e in freeze.get("audit", [])
             if isinstance(e, dict)
             for task in e.get("use_tasks", []) or []}
    for task in sorted((assess & dev) | (audit & (dev | assess))):
        problems.append("split-overlap %s" % task)
    return dev, assess, audit


def _frozen_episode_ids(entries) -> list:
    return [e.get("episode_id") for e in entries
            if isinstance(e, dict)]


def _check_episodes(bundle: dict, freeze: dict, identities: dict,
                    problems: list) -> tuple:
    caps = freeze.get("caps", {})
    per = caps.get("per_episode", {})
    step_cap = per.get("policy_steps")
    call_cap = per.get("model_calls")
    query_cap = caps.get("diagnostic_queries_per_episode")
    episodes = []
    for section in ("development", "assessment", "audit"):
        frozen_ids = _frozen_episode_ids(freeze.get(section, []))
        records = bundle.get(section, [])
        if not isinstance(records, list):
            problems.append("missing-%s-records" % section)
            continue
        have_ids = [e.get("episode_id") for e in records
                    if isinstance(e, dict)]
        for episode_id in sorted(set(frozen_ids) - set(have_ids)):
            problems.append("missing-%s-episode %s" % (section,
                                                       episode_id))
        for episode_id in sorted(set(have_ids) - set(frozen_ids)):
            problems.append("unexpected-%s-episode %s" % (section,
                                                          episode_id))
        for episode in records:
            if not isinstance(episode, dict):
                problems.append("malformed-episode-record")
                continue
            episodes.append((section, episode))
            episode_id = episode.get("episode_id", "?")
            arm = episode.get("arm")
            identity = identities.get(arm, {}) if isinstance(
                identities.get(arm), dict) else {}
            if identity.get("status") == "unavailable":
                problems.append("episode-for-unavailable-arm %s"
                                % episode_id)
            actions = episode.get("policy_actions")
            if not isinstance(actions, list) or not actions:
                problems.append("policy-actions-missing %s" % episode_id)
            elif not any(isinstance(a, dict) and a.get("kind")
                         for a in actions):
                problems.append("policy-actions-unobservable %s"
                                % episode_id)
            expected = identity.get("source_digest")
            if expected and episode.get("policy_digest") != expected:
                problems.append("policy-digest-frozen-mismatch %s"
                                % episode_id)
            steps = episode.get("policy_steps")
            calls = episode.get("model_calls")
            queries = episode.get("witness_queries")
            if not _is_count(steps) or (
                    _is_count(step_cap) and steps > step_cap):
                problems.append("policy-steps-exceeded %s" % episode_id)
            if not _is_count(calls) or (
                    _is_count(call_cap) and calls > call_cap):
                problems.append("model-calls-exceeded %s" % episode_id)
            if not _is_count(queries):
                problems.append("unknown-witness-queries %s" % episode_id)
            elif _is_count(query_cap) and queries > query_cap:
                problems.append("witness-queries-exceeded %s" % episode_id)
            if not _is_count(episode.get("history_tokens")):
                problems.append("unknown-history-tokens %s" % episode_id)
            if not _is_count(episode.get("failed_attempts")):
                problems.append("unknown-failed-attempts %s" % episode_id)
    return episodes


def _check_construction(bundle: dict, freeze: dict, identities: dict,
                        problems: list) -> dict:
    construction = bundle.get("construction", {})
    if not isinstance(construction, dict):
        problems.append("missing-construction-record")
        return {}
    allowance = freeze.get("construction_allowance", {})
    for arm in ACQUIRED_ARMS:
        entry = construction.get(arm)
        if not isinstance(entry, dict):
            problems.append("missing-construction %s" % arm)
            continue
        identity = identities.get(arm, {}) if isinstance(
            identities.get(arm), dict) else {}
        if entry.get("status") != identity.get("status"):
            problems.append("policy-identity-status-mismatch %s" % arm)
        if entry.get("status") not in ("available", "unavailable"):
            problems.append("construction-status-missing %s" % arm)
            continue
        calls = entry.get("calls")
        if not _is_count(calls):
            problems.append("unknown-construction-calls %s" % arm)
            calls = 0
        allowed = allowance.get(arm, {})
        ceiling = int(allowed.get("init", 0)) + int(
            allowed.get("repair", 0))
        if calls > ceiling:
            problems.append("construction-ceiling-exceeded %s" % arm)
        if not _is_count(entry.get("history_tokens")):
            problems.append("unknown-history-tokens %s" % arm)
        if not _is_count(entry.get("failed_attempts")):
            problems.append("unknown-failed-attempts %s" % arm)
        if entry.get("status") == "unavailable":
            if not entry.get("reason"):
                problems.append("unavailable-without-reason %s" % arm)
            continue
        source = entry.get("policy_source")
        digest = entry.get("source_digest")
        if not isinstance(source, str) or digest != source_digest(
                source):
            problems.append("constructed-policy-bytes-mismatch %s" % arm)
        if identity.get("source") != source or identity.get(
                "source_digest") != digest:
            problems.append("constructed-policy-not-frozen %s" % arm)
    return construction if isinstance(construction, dict) else {}


def _recomputed_quality(freeze: dict, record: dict) -> float | None:
    if record.get("executed") == "incumbent":
        return None
    task = freeze.get("tasks", {}).get(record.get("task_id"), {})
    return 1.0 if record.get("observed") == task.get("expected") else 0.0


def _check_use_records(bundle: dict, freeze: dict, identities: dict,
                       repertoire_digests: dict, assess: set,
                       audit: set, problems: list) -> tuple:
    records = bundle.get("use_records", [])
    if not isinstance(records, list):
        problems.append("missing-use-records")
        return [], {}
    tasks = freeze.get("tasks", {})
    seen = set()
    qualities = {}
    for record in records:
        if not isinstance(record, dict):
            problems.append("malformed-use-record")
            continue
        rid = record.get("record_id", "?")
        key = (record.get("arm"), record.get("task_id"))
        if key in seen:
            problems.append("duplicate-record %s" % rid)
        seen.add(key)
        task_id = record.get("task_id")
        if task_id not in tasks:
            problems.append("membership-unknown-task %s" % rid)
            continue
        if task_id not in assess | audit:
            problems.append("membership-not-assessment %s" % rid)
            continue
        arm = record.get("arm")
        if arm not in ARMS:
            problems.append("arms-mismatch %s" % rid)
            continue
        costs = record.get("costs", {})
        queries = costs.get("witness_queries") if isinstance(
            costs, dict) else None
        if queries == "unknown" or not _is_count(queries):
            problems.append("unknown-cost %s" % rid if
                            queries == "unknown" else "bad-cost %s" % rid)
        op_ids = record.get("operation_ids")
        if not isinstance(op_ids, list) or not op_ids:
            problems.append("lineage-missing %s" % rid)
        unavailable = isinstance(identities.get(arm), dict) and \
            identities.get(arm, {}).get("status") == "unavailable"
        if unavailable and record.get("executed") != "incumbent":
            problems.append("substituted-baseline %s" % rid)
        if record.get("executed") == "incumbent":
            qualities[rid] = None
            continue
        if record.get("policy_artifact_kind") != ARTIFACT_KIND:
            problems.append("wrong-policy-artifact-kind %s" % rid)
        if not record.get("policy_digest"):
            problems.append(
                "executed-record-missing-policy-digest %s" % rid)
        expected = (identities.get(arm) or {}).get("source_digest")
        if expected and record.get("policy_digest") != expected:
            problems.append("policy-digest-frozen-mismatch %s" % rid)
        executed = record.get("executed_source_digest")
        if executed not in repertoire_digests.get(arm, set()):
            problems.append("executed-source-not-frozen %s" % rid)
        quality = _recomputed_quality(freeze, record)
        qualities[rid] = quality
        claimed = record.get("claimed_verdict")
        want = "preserved" if quality == 1.0 else "failed"
        if claimed != want:
            if claimed is None:
                problems.append("result-verdict-missing %s" % rid)
            else:
                problems.append("quality-mismatch %s" % rid)
    for arm in ARMS:
        for task_id in sorted(assess | audit):
            if (arm, task_id) not in seen:
                problems.append("missing-use-record %s-%s" % (arm,
                                                              task_id))
    return records, qualities


def _check_operations(bundle: dict, episodes: list, construction: dict,
                      records: list, problems: list) -> tuple:
    operations = bundle.get("operations", {})
    if not isinstance(operations, dict):
        problems.append("missing-operations-map")
        operations = {}
    claimed = set()
    for _section, episode in episodes:
        for op_id in episode.get("operations", []) or []:
            claimed.add(op_id)
    for entry in construction.values():
        if isinstance(entry, dict):
            for op_id in entry.get("operations", []) or []:
                claimed.add(op_id)
    for record in records:
        if isinstance(record, dict):
            for op_id in record.get("operation_ids", []) or []:
                claimed.add(op_id)
    unknown_receipts = 0
    for op_id in sorted(claimed):
        row = operations.get(op_id)
        if not isinstance(row, dict):
            problems.append("missing-operation %s" % op_id)
            problems.append("missing-receipt for-operation %s" % op_id)
            continue
        receipts = row.get("receipts", [])
        settled = [r for r in receipts if isinstance(r, dict)
                   and r.get("outcome") in ("success", "failure")]
        unknown_receipts += sum(
            1 for r in receipts if isinstance(r, dict)
            and r.get("outcome") == "unknown")
        if not settled:
            problems.append("missing-receipt for-operation %s" % op_id)
    return operations, unknown_receipts


def _check_accounting(bundle: dict, recomputed_counts: dict,
                      problems: list) -> None:
    accounting = bundle.get("accounting", {})
    if not isinstance(accounting, dict):
        problems.append("missing-accounting")
        return
    for key in RESOURCE_CLASSES:
        entry = accounting.get(key)
        if not isinstance(entry, dict):
            problems.append("accounting-missing %s" % key)
            continue
        measured = entry.get("measured")
        if measured != "unknown" and not _is_count(measured):
            problems.append("accounting-malformed %s" % key)
            continue
        if not isinstance(entry.get("source"), str) or not entry.get(
                "source"):
            problems.append("accounting-source-missing %s" % key)
        if key in RECOUNTABLE and measured != "unknown" and \
                measured != recomputed_counts.get(key):
            problems.append("accounting-%s-mismatch reported=%r "
                            "recomputed=%d" % (key, measured,
                                               recomputed_counts[key]))
    billed = accounting.get("billed_units", {})
    source = str(billed.get("source", ""))
    if billed.get("measured") == 0 and any(
            marker in source for marker in ("unresolved", "unknown",
                                            "unmeasured")):
        problems.append("billed-unknown-scored-as-zero")


def _compare(freeze: dict, bundle: dict, records: list,
             qualities: dict, assess: set, audit: set,
             problems: list) -> dict:
    assess_ids = {r.get("record_id") for r in records
                  if isinstance(r, dict) and r.get("task_id") in assess}
    audit_ids = {r.get("record_id") for r in records
                 if isinstance(r, dict) and r.get("task_id") in audit}
    means = {}
    audit_means = {}
    for arm in ARMS:
        arm_assess = [qualities[rid] for rid in assess_ids
                      if next((r for r in records
                               if r.get("record_id") == rid), {}).get(
                          "arm") == arm and qualities.get(rid) is not None]
        arm_audit = [qualities[rid] for rid in audit_ids
                     if next((r for r in records
                              if r.get("record_id") == rid), {}).get(
                         "arm") == arm and qualities.get(rid) is not None]
        means[arm] = (sum(arm_assess) / len(arm_assess)
                      if arm_assess else None)
        audit_means[arm] = (sum(arm_audit) / len(arm_audit)
                            if arm_audit else None)
    identities = freeze.get("policy_identities", {})
    missing = sorted(arm for arm in ACQUIRED_ARMS
                     if isinstance(identities.get(arm), dict)
                     and identities.get(arm, {}).get("status")
                     == "unavailable")
    rule = freeze.get("metric_rule", {})
    margin = rule.get("margin", 0.0)
    winner = None
    status = "incomplete" if missing else "complete"
    if not missing:
        ranked = sorted(((mean, arm) for arm, mean in means.items()
                         if mean is not None), reverse=True)
        if ranked:
            best, second = ranked[0][0], (ranked[1][0]
                                          if len(ranked) > 1 else 0.0)
            winner = ranked[0][1] if best - second >= margin else "P0"
    claimed = bundle.get("claimed", {})
    if not isinstance(claimed, dict) or "winner" not in claimed:
        problems.append("comparison-claimed-missing")
    elif (claimed.get("winner") or "none") != (winner or "none"):
        problems.append("comparison-verdict-mismatch")
    return {"status": status, "winner": winner, "missing_arms": missing,
            "means": means, "audit_means": audit_means}


def verify_bundle(bundle: dict) -> dict:
    problems: list = []
    if not isinstance(bundle, dict):
        return {"status": "incomplete", "problems": ["empty-bundle"],
                "recomputed": {}}
    freeze = _check_freeze(bundle, problems)
    if freeze is None:
        return {"status": "incomplete",
                "problems": sorted(set(problems)), "recomputed": {}}
    identities = _check_identities(freeze, problems)
    repertoire_digests = _check_repertoires(freeze, problems)
    _dev, assess, audit = _split_tasks(freeze, problems)
    episodes = _check_episodes(bundle, freeze, identities, problems)
    construction = _check_construction(bundle, freeze, identities,
                                       problems)
    records, qualities = _check_use_records(
        bundle, freeze, identities, repertoire_digests, assess, audit,
        problems)
    _operations, unknown_receipts = _check_operations(
        bundle, episodes, construction, records, problems)
    total_model = sum(e.get("model_calls", 0) for _, e in episodes
                      if _is_count(e.get("model_calls")))
    total_construction = 0
    for entry in construction.values():
        if isinstance(entry, dict) and _is_count(entry.get("calls")):
            total_model += entry["calls"]
            total_construction += entry["calls"]
    witness_acquisition = sum(e.get("witness_queries", 0)
                              for _, e in episodes
                              if _is_count(e.get("witness_queries")))
    witness_use = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        queries = (record.get("costs") or {}).get("witness_queries")
        if _is_count(queries):
            witness_use += queries
    history_tokens = sum(e.get("history_tokens", 0) for _, e in episodes
                         if _is_count(e.get("history_tokens")))
    for entry in construction.values():
        if isinstance(entry, dict) and _is_count(
                entry.get("history_tokens")):
            history_tokens += entry["history_tokens"]
    failed_attempts = sum(e.get("failed_attempts", 0)
                          for _, e in episodes
                          if _is_count(e.get("failed_attempts")))
    for entry in construction.values():
        if isinstance(entry, dict) and _is_count(
                entry.get("failed_attempts")):
            failed_attempts += entry["failed_attempts"]
    worst = study_worst_case(freeze)
    caps = freeze.get("caps", {})
    if caps.get("study_model_calls") != worst:
        problems.append("study-ceiling-mismatch derived=%d frozen=%r"
                        % (worst, caps.get("study_model_calls")))
    if total_model > worst:
        problems.append("study-ceiling-exceeded total=%d worst=%d"
                        % (total_model, worst))
    ceiling = caps.get("history_token_ceiling")
    if _is_count(ceiling) and history_tokens > ceiling:
        problems.append("history-ceiling-exceeded total=%d ceiling=%d"
                        % (history_tokens, ceiling))
    _check_accounting(bundle, {
        "model_dispatches": total_model,
        "tool_queries": witness_acquisition + witness_use,
        "unresolved_exposure": unknown_receipts}, problems)
    by_arm = {}
    for arm in ARMS:
        arm_qualities = [qualities[r.get("record_id")] for r in records
                         if isinstance(r, dict) and r.get("arm") == arm
                         and r.get("task_id") in assess
                         and qualities.get(r.get("record_id"))
                         is not None]
        by_arm[arm] = (sum(arm_qualities) / len(arm_qualities)
                       if arm_qualities else None)
    comparison = _compare(freeze, bundle, records, qualities, assess,
                          audit, problems)
    recomputed = {"model_calls": total_model,
                  "construction_calls": total_construction,
                  "history_tokens": history_tokens,
                  "failed_attempts": failed_attempts,
                  "witness_acquisition": witness_acquisition,
                  "witness_use": witness_use,
                  "use_records": len(records),
                  "worst_case": worst,
                  "quality_by_arm": by_arm,
                  "comparison": comparison}
    status = "pass" if not problems else "fail"
    return {"status": status, "problems": sorted(set(problems)),
            "recomputed": recomputed}


def verify_bundle_file(path) -> dict:
    from pathlib import Path
    return verify_bundle(json.loads(Path(path).read_text()))
