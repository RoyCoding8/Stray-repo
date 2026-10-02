"""S09-M5 offline verifier for the N5 prospective pilot bundle.

Reads only the bundle directory. Names every missing or inconsistent
piece of evidence with the exact identity a reviewer must chase.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ACCOUNTING_CATEGORIES = (
    "construction",
    "rejected_actions",
    "policy_execution",
    "model_requests",
    "use",
    "repair",
)


def empty_accounting() -> dict:
    return {key: {"measured": "unknown", "source": "unmeasured"}
            for key in ACCOUNTING_CATEGORIES}


def canonical(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def freeze_digest(freeze: dict) -> str:
    body = {key: value for key, value in freeze.items()
            if key != "freeze_digest"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def _is_count(value) -> bool:
    return type(value) is int and value >= 0


def verify_bundle(bundle: dict) -> dict:
    problems: list = []
    if not isinstance(bundle, dict):
        return {"status": "incomplete", "problems": ["empty-bundle"],
                "recomputed": {}}
    freeze = bundle.get("freeze")
    if not isinstance(freeze, dict):
        return {"status": "incomplete", "problems": ["missing-freeze"],
                "recomputed": {}}
    for key in ("study_id", "study_root", "arms", "order", "development",
                "construction_allowance", "assessment", "caps",
                "metric_rule", "resource_rule", "config",
                "policy_identities", "method_repertoires", "freeze_digest"):
        if key not in freeze:
            problems.append("freeze-incomplete missing-%s" % key)
    if freeze.get("freeze_digest") != freeze_digest(freeze):
        problems.append("freeze-digest-mismatch")
    if freeze.get("artifact_kind") != "learning-policy":
        problems.append("policy-artifact-kind-missing")
    if freeze.get("policy_abi") != "ad01-policy-step-v1":
        problems.append("policy-abi-missing")
    identities = freeze.get("policy_identities")
    if not isinstance(identities, dict):
        identities = {}
        problems.append("policy-identities-missing")
    for arm in freeze.get("arms", []):
        identity = identities.get(arm)
        if not isinstance(identity, dict):
            problems.append("policy-identity-missing %s" % arm)
            continue
        status = identity.get("status")
        if status not in ("available", "unavailable"):
            problems.append("policy-identity-status-missing %s" % arm)
        if status == "available":
            source = identity.get("source")
            digest = identity.get("source_digest")
            artifact = identity.get("artifact")
            if not isinstance(source, str) or not source.strip():
                problems.append("policy-source-missing %s" % arm)
            if not isinstance(digest, str) or digest != hashlib.sha256(
                    source.encode()).hexdigest():
                problems.append("policy-source-digest-mismatch %s" % arm)
            if not isinstance(artifact, dict) or artifact.get(
                    "source_digest") != digest:
                problems.append("policy-artifact-mismatch %s" % arm)
    repertoires = freeze.get("method_repertoires")
    if not isinstance(repertoires, dict):
        repertoires = {}
        problems.append("method-repertoires-missing")
    repertoire_digests = {}
    for arm in freeze.get("arms", []):
        repertoire = repertoires.get(arm)
        if not isinstance(repertoire, dict):
            problems.append("method-repertoire-missing %s" % arm)
            continue
        members = repertoire.get("members")
        if not isinstance(members, list):
            problems.append("method-repertoire-members-missing %s" % arm)
            continue
        digests = []
        for member in members:
            source = member.get("method_source") if isinstance(
                member, dict) else None
            digest = member.get("source_digest") if isinstance(
                member, dict) else None
            if not isinstance(source, str) or digest != hashlib.sha256(
                    source.encode()).hexdigest():
                problems.append("method-bytes-digest-mismatch %s" % arm)
            elif digest:
                digests.append(digest)
        repertoire_digests[arm] = set(digests)
        if sorted(digests) != sorted(repertoire.get("member_digests", [])):
            problems.append("method-repertoire-digests-mismatch %s" % arm)
    caps = freeze.get("caps") if isinstance(
        freeze.get("caps"), dict) else {}
    per_episode = caps.get("per_episode") if isinstance(
        caps.get("per_episode"), dict) else {}
    step_cap = per_episode.get("policy_steps")
    call_cap = per_episode.get("model_calls")

    frozen_dev = [e.get("episode_id") for e in
                  freeze.get("development", [])
                  if isinstance(e, dict)]
    frozen_assess = [e.get("episode_id") for e in
                     freeze.get("assessment", [])
                     if isinstance(e, dict)]
    frozen_use: dict = {}
    for entry in freeze.get("assessment", []):
        if not isinstance(entry, dict):
            continue
        for task in entry.get("use_tasks", []) or []:
            frozen_use["%s-%s" % (entry.get("episode_id"), task)] = (
                entry.get("episode_id"), task)

    development = bundle.get("development", [])
    assessment = bundle.get("assessment", [])
    dev_ids = [e.get("episode_id") for e in development
               if isinstance(e, dict)]
    assess_ids = [e.get("episode_id") for e in assessment
                  if isinstance(e, dict)]
    if len(set(dev_ids)) != len(dev_ids):
        problems.append("duplicate-development-episode")
    if len(set(assess_ids)) != len(assess_ids):
        problems.append("duplicate-assessment-episode")
    for episode_id in sorted(set(frozen_dev) - set(dev_ids)):
        problems.append("missing-development-episode %s" % episode_id)
    for episode_id in sorted(set(dev_ids) - set(frozen_dev)):
        problems.append("unexpected-development-episode %s" % episode_id)
    for episode_id in sorted(set(frozen_assess) - set(assess_ids)):
        problems.append("missing-assessment-episode %s" % episode_id)
    for episode_id in sorted(set(assess_ids) - set(frozen_assess)):
        problems.append("unexpected-assessment-episode %s" % episode_id)

    total_model = 0
    total_construction = 0
    total_witness = 0
    claimed_ops: set = set()
    for episode in list(development) + list(assessment):
        if not isinstance(episode, dict):
            problems.append("malformed-episode-record")
            continue
        episode_id = episode.get("episode_id", "?")
        steps = episode.get("policy_steps")
        calls = episode.get("model_calls")
        if not _is_count(steps) or (
                _is_count(step_cap) and steps > step_cap):
            problems.append("policy-steps-exceeded %s" % episode_id)
        if not _is_count(calls) or (
                _is_count(call_cap) and calls > call_cap):
            problems.append("model-calls-exceeded %s" % episode_id)
        if _is_count(calls):
            total_model += calls
        queries = episode.get("witness_queries")
        if _is_count(queries):
            total_witness += queries
        else:
            problems.append("unknown-witness-queries %s" % episode_id)
        query_cap = caps.get("diagnostic_queries_per_episode")
        if _is_count(queries) and _is_count(query_cap) and \
                queries > query_cap:
            problems.append("witness-queries-exceeded %s" % episode_id)
        for op_id in episode.get("operations", []) or []:
            claimed_ops.add(op_id)
        digest = episode.get("policy_digest")
        if episode.get("status", "complete") != "unavailable":
            if not isinstance(digest, str) or len(digest) != 64:
                problems.append("policy-digest-missing %s" % episode_id)
            actions = episode.get("policy_actions")
            if not isinstance(actions, list) or not actions:
                problems.append("policy-actions-missing %s" % episode_id)
            elif not any(isinstance(a, dict) and a.get("kind") for a in actions):
                problems.append("policy-actions-unobservable %s" % episode_id)
            expected = (identities.get(episode.get("arm")) or {}).get(
                "source_digest")
            if expected and digest != expected:
                problems.append("policy-digest-frozen-mismatch %s" % episode_id)

    construction = bundle.get("construction", {})
    if not isinstance(construction, dict):
        problems.append("missing-construction-record")
        construction = {}
    allowance = freeze.get("construction_allowance", {})
    if not isinstance(allowance, dict):
        allowance = {}
    for arm, entry in construction.items():
        if not isinstance(entry, dict):
            problems.append("malformed-construction %s" % arm)
            continue
        allowed = allowance.get(arm, {})
        if not isinstance(allowed, dict):
            allowed = {}
        calls = entry.get("calls", 0)
        if not _is_count(calls):
            problems.append("unknown-construction-calls %s" % arm)
            continue
        total_model += calls
        total_construction += calls
        if calls > int(allowed.get("init", 1)) + int(
                allowed.get("repair", 1)):
            problems.append("construction-ceiling-exceeded %s" % arm)
        if entry.get("status") not in ("available", "unavailable"):
            problems.append("construction-status-missing %s" % arm)
        if entry.get("status") == "unavailable" and not entry.get(
                "reason"):
            problems.append("unavailable-without-reason %s" % arm)
        identity = identities.get(arm) or {}
        if entry.get("status") != identity.get("status"):
            problems.append("policy-identity-status-mismatch %s" % arm)
        if entry.get("status") == "available":
            source = entry.get("policy_source")
            digest = entry.get("source_digest")
            if not isinstance(source, str) or digest != hashlib.sha256(
                    source.encode()).hexdigest():
                problems.append("constructed-policy-bytes-mismatch %s" % arm)
            if identity.get("source") != source or identity.get(
                    "source_digest") != digest:
                problems.append("constructed-policy-not-frozen %s" % arm)
        for op_id in entry.get("operations", []) or []:
            claimed_ops.add(op_id)

    use_records = bundle.get("use_records", [])
    if not isinstance(use_records, list):
        problems.append("missing-use-records")
        use_records = []
    record_ids = [r.get("record_id") for r in use_records
                  if isinstance(r, dict)]
    if len(set(record_ids)) != len(record_ids):
        problems.append("duplicate-record %s" % sorted(record_ids))
    for rid in sorted(set(frozen_use) - set(record_ids)):
        problems.append("missing-use-record %s" % rid)
    for rid in sorted(set(record_ids) - set(frozen_use)):
        problems.append("unexpected-use-record %s" % rid)
    use_queries = 0
    unavailable_arms = {arm for arm, entry in construction.items()
                        if isinstance(entry, dict) and entry.get(
                            "status") == "unavailable"}
    for record in use_records:
        if not isinstance(record, dict):
            problems.append("malformed-use-record")
            continue
        queries = (record.get("costs") or {}).get("witness_queries")
        if _is_count(queries):
            use_queries += queries
        else:
            problems.append("unknown-cost %s" % (
                record.get("record_id", "?")))
        for op_id in record.get("operation_ids", []) or []:
            claimed_ops.add(op_id)
        if record.get("arm") in unavailable_arms and record.get(
                "executed") != "incumbent":
            problems.append("substituted-baseline %s" % (
                record.get("record_id", "?")))
        if record.get("policy_artifact_kind") not in (
                "learning-policy", None):
            problems.append("wrong-policy-artifact-kind %s" % (
                record.get("record_id", "?")))
        if record.get("executed") != "incumbent" and not record.get(
                "policy_digest"):
            problems.append("executed-record-missing-policy-digest %s" % (
                record.get("record_id", "?")))
        if record.get("executed") != "incumbent":
            executed_digest = record.get("executed_source_digest")
            if not isinstance(executed_digest, str) or not executed_digest:
                problems.append("executed-source-digest-missing %s" % (
                    record.get("record_id", "?")))
            elif executed_digest not in repertoire_digests.get(
                    record.get("study_arm"), set()):
                problems.append("executed-source-not-frozen %s" % (
                    record.get("record_id", "?")))

    operations = bundle.get("operations", {})
    if not isinstance(operations, dict):
        problems.append("missing-operations-map")
        operations = {}
    for op_id in sorted(claimed_ops):
        row = operations.get(op_id)
        if not isinstance(row, dict):
            problems.append("missing-operation %s" % op_id)
            problems.append(
                "missing-receipt for-operation %s" % op_id)
            continue
        receipts = row.get("receipts", [])
        settled = [r for r in receipts if isinstance(r, dict)
                   and r.get("outcome") in ("success", "failure")]
        if not settled:
            problems.append(
                "missing-receipt for-operation %s" % op_id)

    try:
        from experiments.ad01 import construct as _construct
        construction_ceiling = int(
            _construct.CONSTRUCTION_CALL_CEILING)
    except Exception:
        construction_ceiling = 4
        problems.append("code-ceiling-unreadable")
    episodes = len(frozen_dev) + len(frozen_assess)
    worst = episodes * (call_cap if _is_count(call_cap) else 0) \
        + construction_ceiling
    if caps.get("study_model_calls") != worst:
        problems.append("study-ceiling-mismatch derived=%d frozen=%r"
                        % (worst, caps.get("study_model_calls")))
    if total_model > worst:
        problems.append("study-ceiling-exceeded total=%d worst=%d"
                        % (total_model, worst))

    accounting = bundle.get("accounting", {})
    if not isinstance(accounting, dict):
        problems.append("missing-accounting")
        accounting = {}
    for key in ACCOUNTING_CATEGORIES:
        entry = accounting.get(key)
        if not isinstance(entry, dict):
            problems.append("accounting-missing %s" % key)
            continue
        measured = entry.get("measured")
        if measured != "unknown" and not _is_count(measured):
            problems.append("accounting-malformed %s" % key)
    model_accounted = (accounting.get("model_requests") or {}).get(
        "measured")
    if model_accounted != "unknown" and model_accounted != total_model:
        problems.append("accounting-model-mismatch reported=%r "
                        "recomputed=%d" % (model_accounted, total_model))
    use_accounted = (accounting.get("use") or {}).get("measured")
    if use_accounted != "unknown" and use_accounted != len(
            use_records):
        problems.append("accounting-use-mismatch reported=%r "
                        "records=%d" % (use_accounted, len(use_records)))

    for probe in bundle.get("refusal_probes", []) or []:
        if not isinstance(probe, dict):
            problems.append("malformed-refusal-probe")
            continue
        if probe.get("observed_new_ops", ["unread"]) != []:
            problems.append("probe-created-effects %s" % (
                probe.get("probe_id", "?")))
        if not probe.get("refused", False):
            problems.append("probe-not-refused %s" % (
                probe.get("probe_id", "?")))

    conformance = bundle.get("conformance_replay", {})
    if not isinstance(conformance, dict) or conformance.get(
            "status") != "conformance":
        problems.append("replay-misused-as-experiment")
    else:
        if conformance.get("identity") != "supported":
            problems.append("conformance-identity-not-supported")
        if conformance.get("changed") == "supported":
            problems.append("conformance-changed-supported")

    recomputed = {"model_calls": total_model,
                  "construction_calls": total_construction,
                  "witness_acquisition": total_witness,
                  "witness_use": use_queries,
                  "use_records": len(use_records),
                  "worst_case": worst,
                  "claimed_operations": len(claimed_ops)}
    status = "pass" if not problems else "fail"
    return {"status": status, "problems": sorted(set(problems)),
            "recomputed": recomputed}


def verify_bundle_dir(path) -> dict:
    root = Path(path)
    bundle = {}
    for name in ("freeze", "development", "construction", "assessment",
                 "use_records", "operations", "accounting",
                 "refusal_probes", "conformance_replay"):
        text = (root / ("%s.json" % name)).read_text()
        bundle[name] = json.loads(text)
    return verify_bundle(bundle)


def verify_campaign_file(path) -> dict:
    """Verify a campaign export without opening a provider or database."""
    root = Path(path)
    export = json.loads(root.read_text())
    from experiments.ad01 import records
    return records.verify_campaign(export, export.get("use_records", []))


def main(argv: list | None = None) -> int:
    args = list(argv or [])
    if len(args) != 1:
        print("usage: s09_verify.py <bundle-dir-or-campaign-export>",
              file=sys.stderr)
        return 2
    try:
        target = Path(args[0])
        if target.is_file():
            out = verify_campaign_file(target)
            output_path = target.with_name(target.stem + ".verify.json")
        else:
            out = verify_bundle_dir(target)
            output_path = target / "verify.json"
    except Exception as exc:
        print("s09-verify refused: %s" % exc, file=sys.stderr)
        return 3
    print(canonical(out))
    output_path.write_text(json.dumps(out, sort_keys=True, indent=1) + "\n")
    return 0 if out["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
