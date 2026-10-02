"""M4 offline recomputation for the E1/E2 prospective comparison.

Deterministic file and memory input only. No gateway, database, network,
environment or clock access. Quality is derived from frozen tasks plus
recorded observable behavior; runtime verdict labels are cross-checked,
never trusted. Resource records name a source and a closed measurement
status. Only measured records carry numeric values; unknown billing stays
unknown.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import math

from . import paired_results as pairs
from .live_construct import OUTPUT_PROTOCOL_ID, OUTPUT_STUDY_ROOT
from .paired_results import Attested, Recomputed

ARMS = ("P0", "P1", "P2")
ACQUIRED_ARMS = ("P1", "P2")
E12_PROTOCOL_ID = "invl02-live-e12-v1"
# The verifier is deliberately absent from this list. It re-hashes each path
# and compares against the freeze, so a verifier in the list can never pass:
# any edit to it changes the answer, and no frozen bundle verifies clean at any
# commit afterwards. That is M4's precondition, a baseline that cannot pass
# cannot establish a tamper test. Its own digest is reported by
# `verifier_digest` so a reader can still tell which version judged a bundle.
OUTPUT_CODE_PATHS = (
    "scripts/invl02_live.py",
    "experiments/ad01/live_construct.py",
    "experiments/ad01/frontier.py",
    "src/settlement/gateway_http.py",
)
OUTPUT_SOURCE_PATHS = (
    "experiments/ad01/boolean_rule.py",
    "experiments/ad01/rule_learner.py",
    "experiments/ad01/live_construct.py",
)

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
MEASUREMENT_STATUSES = ("measured", "unknown", "unresolved")

MEASUREMENT_BOUNDARY = (
    "Resource consumption is a runtime attestation named by "
    "accounting[<class>].source with a closed measurement_status. The "
    "offline verifier recounts model dispatches, tool queries and "
    "unresolved exposure from operations, episodes and cost fields. It "
    "cannot independently measure tokens, child compute or billed units. "
    "Only measured status carries a numeric value. Unknown and unresolved "
    "stay unknown. Human interventions require a separate ledger."
)

ARTIFACT_KIND = "learning-policy"
POLICY_ABI = "ad01-policy-step-v1"
M4_SCHEMA = "invl02-m4-bundle-v2"
OUTPUT_SCHEMA = "invl02-output-run-v2"
SCORER_PRIVATE_SCHEMA = "invl02-output-scorer-private-v1"
M4_STUDY_ROOT = "invl02-live-e12"

# The study roots whose authority this verifier can vouch for. Two of
# them are pinned by test fixtures rather than by a recorded study, so
# this set is a floor, not a registry. Growing it needs a study whose
# evidence directory is on record, not one whose test needs to pass.
AUTHORITATIVE_STUDY_ROOTS = frozenset({
    M4_STUDY_ROOT,
    OUTPUT_STUDY_ROOT,
    "invl02-live-e0",
    "invl02-live-e3",
    "invl02-live-json",
    "invl02_m4",
})

FREEZE_REQUIRED = (
    "study_id", "study_root", "arms", "order", "development",
    "assessment", "audit", "construction_allowance", "caps",
    "metric_rule", "resource_rule", "config", "policy_identities",
    "method_repertoires", "arm_contracts", "history_reference", "tasks",
    "freeze_digest",
)

# A bundle's identity is the study it claims. The bundle-level `study`
# predates the freeze's `study_id`, so it is checked against that one.
IDENTITY_KEYS = ("study", "study_id", "study_root")

# The answer-bearing side of a world. A frozen policy source or a method
# repertoire member that names one of these is not a policy; it has been
# handed the held-out answer, and any quality it then scores is a lookup.
# Substring matching is safe here because none of the thirteen policy
# sources in the tree trips any of these; a real false positive would
# show up as a rejected bundle, not as a silent pass.
HIDDEN_ANSWER_MARKERS = (
    "target_tables", "task_answers", "answer_key", "answer_key_",
    "private_answer", "hidden_answer", "heldout_answer", "held_out_answer",
    "ground_truth", "groundtruth", "expected_tables", "scorer_private",
    "oracle_tables", "solution_tables", "answer_table",
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


def select_m4_winner(means: dict[str, float | None], margin: float,
                     tie: str) -> str | None:
    available = {arm: mean for arm, mean in means.items()
                 if mean is not None}
    if not available:
        return None
    ranked = sorted(available, key=lambda arm: (-available[arm], arm))
    leader = ranked[0]
    leaders = [arm for arm in ranked if available[arm] == available[leader]]
    if len(leaders) == 1:
        second = max((available[arm] for arm in ranked[1:]), default=0.0)
        if available[leader] - second >= margin:
            return leader
    return "P0" if tie == "incumbent" else None


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


def _is_unknown_count(value) -> bool:
    return value == "unknown"


def _is_measurement_count(value) -> bool:
    return _is_count(value) or _is_unknown_count(value)


def receipt_measurement_status(receipt: dict) -> str:
    if (receipt.get("outcome") in ("unknown", "unresolved", "conflict")
            or receipt.get("settled") is False
            or receipt.get("dispatch_state") in ("unresolved", "conflict")
            or receipt.get("reconcile_state") in ("unresolved", "conflict")
            or receipt.get("conflict") is True
            or bool(receipt.get("receipt_conflicts"))):
        return "unresolved"
    usage = receipt.get("usage")
    if not isinstance(usage, dict):
        return "unknown"
    values = (usage.get("input_tokens"), usage.get("output_tokens"),
              usage.get("charge_units"), usage.get("charge_scale"),
              usage.get("billed"))
    if any(value is None or value == "unknown" for value in values):
        return "unknown"
    if (any(isinstance(value, bool)
            or not isinstance(value, (int, float))
            for value in values[:4])
            or not isinstance(values[4], bool)):
        return "unknown"
    if any(isinstance(value, float) and not math.isfinite(value)
           for value in values[:4]):
        return "unknown"
    if values[0] < 0 or values[1] < 0 or values[2] < 0 or values[3] <= 0:
        return "unknown"
    if (values[4] and values[2] == 0) or (not values[4] and values[2] != 0):
        return "unknown"
    return "measured"


def _is_unresolved_receipt(receipt) -> bool:
    return isinstance(receipt, dict) and receipt_measurement_status(receipt) \
        == "unresolved"


def _operation_unresolved_count(row: dict) -> int:
    receipts = row.get("receipts", []) if isinstance(row, dict) else []
    unresolved_receipts = sum(
        1 for receipt in receipts if _is_unresolved_receipt(receipt))
    conflicts = row.get("receipt_conflicts") if isinstance(row, dict) else None
    conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
    operation_unresolved = int(
        isinstance(row, dict)
        and (row.get("dispatch_state") in ("unresolved", "conflict")
             or row.get("reconcile_state") in ("unresolved", "conflict")
             or row.get("conflict") is True
             or row.get("settled") is False))
    return max(unresolved_receipts, conflict_count, operation_unresolved)


def unresolved_exposure_count(operations: dict) -> int:
    if not isinstance(operations, dict):
        return 0
    return sum(_operation_unresolved_count(row)
               for row in operations.values()
               if isinstance(row, dict))


def _operation_dispatch_measured(row: dict) -> bool:
    if not isinstance(row, dict) or not row.get("receipts"):
        return False
    if _operation_unresolved_count(row):
        return False
    return True


def dispatch_unresolved_count(dispatch_ledger: list) -> int:
    if not isinstance(dispatch_ledger, list):
        return 0
    return sum(
        1 for entry in dispatch_ledger
        if isinstance(entry, dict)
        and (entry.get("outcome") in ("unknown", "unresolved", "conflict")
             or entry.get("dispatch_state") in ("unresolved", "conflict")
             or entry.get("reconcile_state") in ("unresolved", "conflict")
             or entry.get("conflict") is True))


def _output_usage_state_problems(receipt: dict) -> list:
    problems = []
    status = receipt.get("measurement_status")
    expected = receipt_measurement_status(receipt)
    if status is None:
        problems.append("durable-receipt-measurement-status-missing")
    elif status not in MEASUREMENT_STATUSES:
        problems.append("durable-receipt-measurement-status-invalid")
    elif status != expected:
        problems.append("durable-receipt-measurement-status-mismatch")
    if "settled" not in receipt:
        problems.append("durable-receipt-settled-missing")
    elif receipt.get("settled") is not True:
        if not _is_lost_response_receipt(receipt):
            problems.append("durable-receipt-unsettled")
    elif (_claims_lost_response(receipt)
          and not _is_lost_response_receipt(receipt)):
        problems.append("durable-receipt-unsettled")
    usage = receipt.get("usage")
    if not isinstance(usage, dict):
        problems.append("durable-receipt-usage-state-invalid")
        return problems
    required = {"input_tokens", "output_tokens", "charge_units",
                "charge_scale", "billed"}
    if required - set(usage):
        problems.append("durable-receipt-usage-state-invalid")
    for key in ("input_tokens", "output_tokens", "charge_units",
                "charge_scale"):
        value = usage.get(key)
        if value is None or value == "unknown":
            continue
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or (isinstance(value, float) and not math.isfinite(value))
                or value < 0):
            problems.append("durable-receipt-usage-state-invalid")
    if status in ("unknown", "unresolved"):
        billed = usage.get("billed")
        if not (billed is None or billed == "unknown"
                or isinstance(billed, bool)):
            problems.append("durable-receipt-usage-state-invalid")
    elif not isinstance(usage.get("billed"), bool):
        problems.append("durable-receipt-usage-state-invalid")
    if status == "measured":
        for key in ("input_tokens", "output_tokens", "charge_units",
                    "charge_scale"):
            value = usage.get(key)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or (isinstance(value, float) and not math.isfinite(value))
                    or value < 0 or (key == "charge_scale" and value <= 0)):
                problems.append("durable-receipt-usage-state-invalid")
    if (status == "unresolved" and not _is_lost_response_receipt(receipt)):
        required = {"input_tokens", "output_tokens", "charge_units",
                    "charge_scale", "billed"}
        if (required - set(usage)
                or any(usage.get(key) is not None
                       and usage.get(key) != "unknown"
                       for key in required)):
            problems.append("durable-receipt-usage-state-invalid")
    return problems


_OUTPUT_RECEIPT_BINDING_FIELDS = (
    "operation_id", "receipt_identity", "outcome", "settled", "usage",
    "source_digest", "artifact_digest", "input_digest", "result_digest",
    "dispatch_evidence_digest",
)


def _output_receipt_binding(receipt: dict) -> dict:
    return {key: receipt.get(key) for key in _OUTPUT_RECEIPT_BINDING_FIELDS}


def _claims_lost_response(receipt: dict) -> bool:
    return (isinstance(receipt, dict)
            and (receipt.get("response_class") == "lost-response"
                 or receipt.get("receipt_outcome") == "unknown"
                 or receipt.get("outcome") == "unresolved"))


def _is_lost_response_receipt(receipt: dict) -> bool:
    usage = receipt.get("usage")
    required_usage = {
        "input_tokens", "output_tokens", "charge_units", "charge_scale",
        "billed"}
    return (
        receipt.get("outcome") == "unresolved"
        and receipt.get("receipt_outcome") == "unknown"
        and receipt.get("response_class") == "lost-response"
        and receipt.get("response_received") is False
        and receipt.get("settled") is False
        and isinstance(usage, dict)
        and required_usage <= set(usage)
        and all(usage.get(key) is None or usage.get(key) == "unknown"
                for key in required_usage)
        and _is_count(receipt.get("exposure"))
        and receipt.get("exposure") > 0
        and receipt.get("unresolved_exposure") == receipt.get("exposure")
        and receipt.get("usable_result") is False
        and receipt.get("result") is None)


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
    metric = freeze.get("metric_rule", {})
    margin = metric.get("margin")
    if (metric.get("kind") != "mean-quality"
            or isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not math.isfinite(float(margin))
            or margin < 0
            or metric.get("tie") not in ("incumbent", "none")):
        problems.append("metric-rule-invalid")
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
        if not _is_measurement_count(identity.get("history_tokens")):
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


def _check_arm_contracts(freeze: dict, identities: dict,
                        problems: list) -> None:
    contracts = freeze.get("arm_contracts")
    reference = freeze.get("history_reference")
    if not isinstance(reference, dict):
        problems.append("history-reference-missing")
        reference = {}
    if not isinstance(contracts, dict):
        problems.append("arm-contracts-missing")
        return
    for arm in ARMS:
        contract = contracts.get(arm)
        if not isinstance(contract, dict):
            problems.append("arm-contract-missing %s" % arm)
            continue
        if arm == "P0":
            source = contract.get("source")
            digest = contract.get("source_digest")
            if (contract.get("kind") != "fixed-incumbent"
                    or not isinstance(source, str) or not source
                    or digest != source_digest(source)):
                problems.append("fixed-incumbent-invalid P0")
            identity = identities.get(arm, {})
            if (identity.get("source") != source
                    or identity.get("source_digest") != digest):
                problems.append("fixed-incumbent-mismatch P0")
            continue
        history = contract.get("history")
        if not isinstance(history, list):
            problems.append("history-contract-missing %s" % arm)
            continue
        if arm == "P1":
            expected_history = []
            expected_history_digest = source_digest("[]")
        else:
            expected_history = reference.get("P2")
            expected_history_digest = (
                source_digest(canonical(expected_history))
                if isinstance(expected_history, list) else None)
        if contract.get("history_digest") != source_digest(canonical(history)):
            problems.append("history-contract-digest-mismatch %s" % arm)
        if arm == "P1" and history != expected_history:
            problems.append("p1-history-not-empty")
        if arm == "P2":
            if not isinstance(expected_history, list) or not expected_history:
                problems.append("p2-history-not-permitted")
            if history != expected_history:
                problems.append("p2-history-not-permitted")
            if (expected_history_digest is not None
                    and contract.get("history_digest")
                    != expected_history_digest):
                problems.append("p2-history-digest-mismatch")
        bindings = contract.get("input_bindings")
        prompts = contract.get("prompt_bindings")
        if (not isinstance(bindings, dict) or not bindings
                or not isinstance(prompts, dict) or not prompts):
            problems.append("input-prompt-binding-missing %s" % arm)
        elif set(bindings) != set(prompts):
            problems.append("input-prompt-binding-mismatch %s" % arm)
        elif any(not isinstance(digest, str) or not digest
                 for digest in bindings.values()):
            problems.append("input-binding-invalid %s" % arm)


def _check_task_labels(freeze: dict, problems: list) -> None:
    from . import boolean_rule as rules
    for task_id, task in (freeze.get("tasks") or {}).items():
        if isinstance(task_id, str) and task_id.startswith("rule-") and (
                not isinstance(task, dict)
                or "split" not in task or "seed" not in task):
            problems.append("frozen-task-identity-missing %s" % task_id)
            continue
        if not isinstance(task, dict) or "split" not in task or "seed" not in task:
            continue
        try:
            generated = rules.make_task(str(task["split"]), int(task["seed"]))
        except Exception:
            problems.append("frozen-task-generation-failed %s" % task_id)
            continue
        expected = canonical(list(generated["tables"]))
        if task.get("expected") != expected:
            problems.append("frozen-task-label-mismatch %s" % task_id)
        if task.get("target_digest") != source_digest(expected):
            problems.append("frozen-task-target-mismatch %s" % task_id)


def _check_study_identity(bundle: dict, freeze: dict,
                          problems: list) -> None:
    """A bundle may only claim the study its freeze pins.

    A digest cannot cover a wholesale identity rewrite: swapping every
    identity key and the digests over them leaves an internally
    consistent bundle, so the frozen study root has to name a study this
    verifier recognises.
    """
    for key in IDENTITY_KEYS:
        frozen = freeze.get(key) or (
            freeze.get("study_id") if key == "study" else None)
        if frozen is not None and key in bundle and bundle.get(key) != frozen:
            problems.append("bundle-%s-mismatch" % key)
    study_root = freeze.get("study_root")
    if (isinstance(study_root, str)
            and study_root not in AUTHORITATIVE_STUDY_ROOTS):
        problems.append("foreign-study-identity %s" % study_root)


def _policy_source_arm(freeze: dict) -> dict:
    """Which arm owns which policy source digest.

    The arms are conditions, so no source can serve two of them. Without
    this an arm can run a sibling's bytes with every binding in the
    freeze rewritten to match, and the bundle stays internally
    consistent while measuring the same policy twice.
    """
    owners = {}
    for arm, identity in (freeze.get("policy_identities") or {}).items():
        digest = identity.get("source_digest") if isinstance(
            identity, dict) else None
        if isinstance(digest, str) and digest:
            owners.setdefault(digest, set()).add(arm)
    return owners


def _check_source_exclusivity(freeze: dict, problems: list) -> None:
    for digest, arms in sorted(_policy_source_arm(freeze).items()):
        if len(arms) > 1:
            problems.append("source-shared-between-arms %s %s"
                            % (digest[:12], sorted(arms)))


def _hidden_answer_problems(source, label: str) -> list:
    """Names an answer-bearing field in a policy's own bytes.

    Case-insensitive and substring-based on purpose. The leak a run must
    not have is a held-out answer inside the bytes a policy can read, and
    that leak has no single spelling; a scan that only matched the exact
    names on this list would be defeated by a rename.
    """
    if not isinstance(source, str) or not source:
        return []
    lowered = source.lower()
    found = sorted({marker for marker in HIDDEN_ANSWER_MARKERS
                    if marker in lowered})
    return ["hidden-answer-contamination %s %s" % (label, marker)
            for marker in found]


def _check_no_hidden_answers(freeze: dict, problems: list) -> None:
    identities = freeze.get("policy_identities") or {}
    for arm in sorted(identities):
        identity = identities[arm]
        if not isinstance(identity, dict):
            continue
        problems.extend(_hidden_answer_problems(
            identity.get("source"), "policy %s" % arm))
    repertoires = freeze.get("method_repertoires") or {}
    for arm in sorted(repertoires):
        repertoire = repertoires[arm]
        members = repertoire.get("members") if isinstance(
            repertoire, dict) else None
        for member in members or []:
            source = member.get("method_source") if isinstance(
                member, dict) else None
            problems.extend(_hidden_answer_problems(
                source, "method %s" % arm))


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
            if not _is_measurement_count(episode.get("history_tokens")):
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
        if not _is_measurement_count(entry.get("history_tokens")):
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


def _software_expected_quality(task_id: str) -> str:
    from . import trajectory, worlds
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    report = trajectory._check(task, task)
    if report.get("verdict") != "preserved":
        raise ValueError("frozen software task is not preserved")
    return "preserved"


def _recomputed_quality(freeze: dict, record: dict) -> float | None:
    if record.get("executed") == "incumbent":
        return None
    task = freeze.get("tasks", {}).get(record.get("task_id"), {})
    return 1.0 if record.get("observed") == task.get("expected") else 0.0


def _check_dispatch_ledger(bundle: dict, construction: dict,
                           problems: list) -> list:
    ledger = bundle.get("dispatch_ledger")
    if not isinstance(ledger, list) or not ledger:
        problems.append("missing-physical-dispatch-ledger")
        return []
    operations = bundle.get("operations")
    receipts = bundle.get("child_receipts")
    expected = set()
    for section in ("development", "assessment", "audit"):
        for episode in bundle.get(section) or []:
            if isinstance(episode, dict) and _is_count(
                    episode.get("model_calls")) and episode["model_calls"]:
                expected.update(episode.get("operations") or [])
    for entry in construction.values() if isinstance(construction, dict) else ():
        if isinstance(entry, dict):
            expected.update(entry.get("operations") or [])
    for candidate in bundle.get("candidates") or []:
        if isinstance(candidate, dict):
            expected.update(candidate.get("operation_ids") or [])
    for record in (bundle.get("software") or {}).get("use_records") or []:
        if isinstance(record, dict):
            operation_id = record.get("operation_id")
            if isinstance(operation_id, str):
                expected.add(operation_id)
    expected = {op_id for op_id in expected if isinstance(op_id, str)}
    seen = set()
    actual = set()
    receipt_evidence_seen = {}
    for entry in ledger:
        if not isinstance(entry, dict):
            problems.append("malformed-dispatch-ledger-entry")
            continue
        operation_id = entry.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            problems.append("dispatch-operation-identity-missing")
            continue
        actual.add(operation_id)
        if not isinstance(operations, dict) or operation_id not in operations:
            problems.append("dispatch-operation-unknown %s" % operation_id)
            continue
        dispatch_id = entry.get("dispatch_id") or entry.get("evidence_digest")
        if (not isinstance(dispatch_id, str) or not dispatch_id
                or dispatch_id in seen):
            problems.append("duplicate-physical-dispatch")
        if isinstance(dispatch_id, str):
            seen.add(dispatch_id)
        receipt = receipts.get(operation_id) if isinstance(receipts, dict) else None
        dispatch_evidence = (entry.get("dispatch_evidence_digest")
                             or entry.get("evidence_digest"))
        receipt_evidence = (receipt.get("dispatch_evidence_digest")
                            or receipt.get("evidence_digest")
                            if isinstance(receipt, dict) else None)
        if isinstance(dispatch_evidence, str):
            receipt_evidence_seen.setdefault(operation_id, []).append(
                dispatch_evidence)
        if (entry.get("arm") not in ARMS
                or not isinstance(entry.get("task_id"), str)
                or not _is_count(entry.get("attempt"))
                or not isinstance(receipt, dict)
                or receipt.get("arm") != entry.get("arm")
                or receipt.get("task_id") != entry.get("task_id")):
            problems.append("dispatch-identity-missing %s" % operation_id)
    for operation_id in expected:
        receipt = receipts.get(operation_id) if isinstance(receipts, dict) else None
        receipt_evidence = (receipt.get("dispatch_evidence_digest")
                            or receipt.get("evidence_digest")
                            if isinstance(receipt, dict) else None)
        if receipt_evidence_seen.get(operation_id, []).count(
                receipt_evidence) != 1:
            problems.append(
                "dispatch-receipt-evidence-cardinality %s" % operation_id)
    if actual != expected:
        problems.append("dispatch-model-operation-set-mismatch")
    return ledger


def frozen_boolean_tasks(protocol: dict) -> dict:
    seeds = protocol.get("boolean_seeds")
    if not isinstance(seeds, dict):
        return {}
    tasks = {}
    for split in ("qual", "audit"):
        values = seeds.get(split)
        if not isinstance(values, list) or len(values) != 1:
            return {}
        tasks[split] = int(values[0])
    return tasks


def _check_authoritative_protocol(bundle: dict, freeze: dict,
                                  problems: list) -> None:
    if freeze.get("study_root") != M4_STUDY_ROOT:
        return
    protocol = bundle.get("protocol")
    authority = bundle.get("authority")
    if (bundle.get("schema") != M4_SCHEMA
            or not isinstance(protocol, dict)
            or not isinstance(authority, dict)):
        problems.append("authoritative-protocol-missing")
        return
    body = {key: value for key, value in protocol.items()
            if key != "freeze_digest"}
    expected = {
        "protocol": protocol.get("protocol"),
        "run_id": protocol.get("run_id"),
        "source_identity": protocol.get("source_identity"),
        "study": protocol.get("study"),
        "study_root": protocol.get("study_root"),
        "freeze_digest": protocol.get("freeze_digest"),
        "route_digest": protocol.get("route_digest"),
    }
    if (protocol.get("protocol") != E12_PROTOCOL_ID
            or protocol.get("study") != M4_STUDY_ROOT
            or protocol.get("study_root") != M4_STUDY_ROOT
            or protocol.get("freeze_digest") != source_digest(canonical(body))
            or protocol.get("route_digest") != source_digest(canonical(
                protocol.get("route")))
            or protocol.get("source_identity") != source_digest(canonical({
                "code_digests": protocol.get("code_digests"),
                "source_digests": protocol.get("source_digests")}))):
        problems.append("authoritative-protocol-invalid")
    if authority != expected:
        problems.append("authoritative-ledger-identity-mismatch")
    if bundle.get("source_e12_freeze_digest") != protocol.get("freeze_digest"):
        problems.append("source-protocol-freeze-mismatch")
    boolean_tasks = frozen_boolean_tasks(protocol)
    if not boolean_tasks:
        problems.append("frozen-boolean-task-set-invalid")
        return
    task_ids = {_task_id_for(split, seed)
                for split, seed in boolean_tasks.items()}
    software_tasks = list(protocol.get("software_tasks") or [])
    if (freeze.get("arms") != protocol.get("arms")
            or freeze.get("order") != protocol.get("order")
            or list(freeze.get("software_tasks") or []) != software_tasks
            or set(freeze.get("tasks") or {}) != task_ids | set(software_tasks)
            or freeze.get("history_reference") != {
                "P1": [], "P2": list(
                    (protocol.get("history") or {}).get("P2") or [])}
            or freeze.get("config", {}).get("candidate_schema")
            != "boolean-rule-v1"):
        problems.append("protocol-membership-mismatch")
    assessment_tasks = {
        task for entry in freeze.get("assessment") or []
        if isinstance(entry, dict)
        for task in entry.get("use_tasks") or []}
    audit_tasks = {
        task for entry in freeze.get("audit") or []
        if isinstance(entry, dict)
        for task in entry.get("use_tasks") or []}
    if (assessment_tasks != {_task_id_for("qual", boolean_tasks["qual"])}
            or audit_tasks != {_task_id_for("audit", boolean_tasks["audit"])}):
        problems.append("protocol-split-membership-mismatch")


def _check_boolean_candidates(bundle: dict, freeze: dict,
                              identities: dict, problems: list) -> None:
    if freeze.get("config", {}).get("candidate_schema") != "boolean-rule-v1":
        return
    from . import live_construct as live
    protocol = bundle.get("protocol")
    tasks_by_split = frozen_boolean_tasks(protocol) \
        if isinstance(protocol, dict) else {}
    operations = bundle.get("operations")
    receipts = bundle.get("child_receipts")
    dispatches = bundle.get("dispatch_ledger")
    if (not tasks_by_split or not isinstance(operations, dict)
            or not isinstance(receipts, dict)
            or not isinstance(dispatches, list)):
        problems.append("boolean-candidate-authority-missing")
        return
    candidates = bundle.get("candidates")
    if not isinstance(candidates, list):
        return
    actual_keys = set()
    task_ids_by_split = {_task_id_for(split, seed): split
                         for split, seed in tasks_by_split.items()}
    expected_keys = {
        (arm, task_id)
        for arm in ACQUIRED_ARMS
        if identities.get(arm, {}).get("status") == "available"
        for task_id in task_ids_by_split}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = (candidate.get("arm"), candidate.get("task_id"))
        actual_keys.add(key)
        arm, task_id = key
        if arm not in ACQUIRED_ARMS or task_id not in task_ids_by_split:
            problems.append("candidate-membership-unknown %s-%s" % key)
            continue
        split = task_ids_by_split[task_id]
        seed = tasks_by_split[split]
        history = [] if arm == "P1" else list(
            (protocol.get("history") or {}).get("P2") or [])
        expected_input = boolean_candidate_input_digest(
            task_id, split, seed, history)
        if (candidate.get("split") != split
                or candidate.get("seed") != seed
                or candidate.get("history") != history
                or candidate.get("history_digest") != source_digest(
                    canonical(history))
                or candidate.get("input_digest") != expected_input):
            problems.append("candidate-input-not-frozen %s-%s" % key)
        try:
            predictor = live.extract_and_validate_boolean(
                candidate.get("raw_response"))
        except Exception:
            problems.append(
                "candidate-raw-response-recompute-failed %s-%s" % key)
            continue
        if (candidate.get("raw_response_digest") != source_digest(
                candidate.get("raw_response", ""))
                or candidate.get("predictor") != predictor
                or candidate.get("predictor_digest") != source_digest(
                    canonical(predictor))):
            problems.append("candidate-payload-recompute-failed %s-%s" % key)
        operation_ids = candidate.get("operation_ids")
        operation_id = candidate.get("operation_id")
        if (not isinstance(operation_ids, list) or not operation_ids
                or len(operation_ids) != len(set(operation_ids))
                or operation_id not in operation_ids):
            problems.append("candidate-operation-cardinality-invalid %s-%s"
                            % key)
            continue
        evidence_ids = candidate.get("dispatch_evidence_digests")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            problems.append("candidate-dispatch-cardinality-invalid %s-%s"
                            % key)
            continue
        bound = [entry for entry in dispatches
                 if isinstance(entry, dict)
                 and entry.get("operation_id") in operation_ids
                 and (entry.get("dispatch_evidence_digest")
                      or entry.get("evidence_digest")) in evidence_ids]
        if ({entry.get("operation_id") for entry in bound
                if isinstance(entry, dict)} != set(operation_ids)
                or len(bound) != len(evidence_ids)):
            problems.append("candidate-dispatch-cardinality-invalid %s-%s"
                            % key)
            continue
        accepted = [entry for entry in bound
                    if entry.get("operation_id") == operation_id]
        if (len(accepted) != 1
                or accepted[0].get("raw_response")
                != candidate.get("raw_response")
                or accepted[0].get("response_digest")
                != candidate.get("raw_response_digest")
                or accepted[0].get("prompt_digest")
                != candidate.get("prompt_digest")):
            problems.append("candidate-raw-response-binding-invalid %s-%s"
                            % key)
        receipt = receipts.get(operation_id)
        result = (((receipt.get("details") or {}).get("raw_payload") or {})
                  .get("result") if isinstance(receipt, dict) else None)
        accepted_evidence = ((accepted[0].get("dispatch_evidence_digest")
                             or accepted[0].get("evidence_digest"))
                            if len(accepted) == 1 else None)
        if (not isinstance(receipt, dict)
                or receipt.get("operation_id") != operation_id
                or receipt.get("dispatch_evidence_digest")
                != accepted_evidence
                or not isinstance(result, dict)
                or result.get("raw_response") != candidate.get("raw_response")
                or receipt.get("source_digest") != candidate.get(
                    "predictor_digest")
                or receipt.get("artifact_digest") != candidate.get(
                    "predictor_digest")
                or receipt.get("input_digest") != candidate.get("input_digest")
                or receipt.get("result_digest") != source_digest(
                    canonical(result))):
            problems.append("candidate-receipt-binding-invalid %s-%s" % key)
    if actual_keys != expected_keys:
        problems.append("candidate-task-set-mismatch")


def _check_candidates(bundle: dict, freeze: dict, identities: dict,
                      records: list, assess: set, audit: set,
                      problems: list) -> list:
    candidates = bundle.get("candidates")
    if not isinstance(candidates, list):
        problems.append("candidate-artifacts-missing")
        return []
    by_key = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            problems.append("malformed-candidate-artifact")
            continue
        key = (candidate.get("arm"), candidate.get("task_id"))
        if key in by_key:
            problems.append("duplicate-candidate-artifact %s-%s" % key)
        by_key[key] = candidate
        predictor = candidate.get("predictor")
        if (not isinstance(candidate.get("raw_response"), str)
                or candidate.get("raw_response_digest") != source_digest(
                    candidate.get("raw_response", ""))
                or not isinstance(predictor, dict)
                or candidate.get("predictor_digest") != source_digest(
                    canonical(predictor))
                or not isinstance(candidate.get("input_digest"), str)
                or not isinstance(candidate.get("prompt_digest"), str)):
            problems.append("candidate-digest-invalid %s-%s" % key)
    for arm in ACQUIRED_ARMS:
        identity = identities.get(arm, {})
        if identity.get("status") != "available":
            continue
        expected_tasks = assess | audit
        for task_id in sorted(expected_tasks):
            candidate = by_key.get((arm, task_id))
            if not isinstance(candidate, dict):
                problems.append("candidate-task-missing %s-%s" % (arm, task_id))
                continue
            contract = (freeze.get("arm_contracts") or {}).get(arm, {})
            if (contract.get("input_bindings", {}).get(task_id)
                    != candidate.get("input_digest")
                    or contract.get("prompt_bindings", {}).get(task_id)
                    != candidate.get("prompt_digest")):
                problems.append("candidate-task-binding-mismatch %s-%s"
                                % (arm, task_id))
            identity_map = identity.get("candidate_digests") or {}
            if identity_map.get(task_id) != candidate.get("predictor_digest"):
                problems.append("candidate-identity-mismatch %s-%s"
                                % (arm, task_id))
    for record in records:
        if not isinstance(record, dict):
            continue
        if (record.get("arm") not in ACQUIRED_ARMS
                or record.get("executed") != "candidate"):
            continue
        candidate = by_key.get((record.get("arm"), record.get("task_id")))
        if (isinstance(candidate, dict)
                and record.get("executed_source_digest")
                != candidate.get("predictor_digest")):
            problems.append("candidate-task-binding-mismatch %s-%s"
                            % (record.get("arm"), record.get("task_id")))
    return candidates


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
        if not isinstance(costs, dict):
            problems.append("costs-malformed %s" % rid)
            costs = {}
        queries = costs.get("witness_queries")
        if queries == "unknown" or not _is_count(queries):
            problems.append("unknown-cost %s" % rid if
                            queries == "unknown" else "bad-cost %s" % rid)
        op_ids = record.get("operation_ids")
        if not isinstance(op_ids, list) or not op_ids:
            problems.append("lineage-missing %s" % rid)
        unavailable = isinstance(identities.get(arm), dict) and \
            identities.get(arm, {}).get("status") == "unavailable"
        child_result = record.get("child_result")
        if not isinstance(child_result, dict):
            problems.append("child-result-missing %s" % rid)
        else:
            if child_result.get("observed") != record.get("observed"):
                problems.append("scored-observation-mismatch %s" % rid)
            if record.get("result_digest") != source_digest(
                    canonical(child_result)):
                problems.append("scored-result-digest-mismatch %s" % rid)
            if costs.get("witness_queries") != child_result.get("queries"):
                problems.append("scored-query-count-mismatch %s" % rid)
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
        candidate_digest = record.get("candidate_digest")
        if (candidate_digest and record.get("executed_source_digest")
                != candidate_digest):
            problems.append("candidate-record-digest-mismatch %s" % rid)
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
                      records: list, identities: dict,
                      problems: list) -> tuple:
    operations = bundle.get("operations", {})
    child_receipts = bundle.get("child_receipts", {})
    if not isinstance(operations, dict) or not operations:
        problems.append("missing-authoritative-operations")
        operations = {}
    if not isinstance(child_receipts, dict) or not child_receipts:
        problems.append("missing-authoritative-child-receipts")
        child_receipts = {}
    claimed = set()
    claim_sources = {}

    def claim_operation(op_id, source):
        if not isinstance(op_id, str) or not op_id:
            problems.append("operation-identity-malformed %s" % source)
            return
        if op_id in claim_sources:
            problems.append("dispatch-operation-reused %s" % op_id)
            return
        claim_sources[op_id] = source
        claimed.add(op_id)

    for section, episode in episodes:
        for op_id in episode.get("operations", []) or []:
            claim_operation(op_id, "episode:%s" % episode.get(
                "episode_id", section))
    for arm, entry in construction.items():
        if not isinstance(entry, dict):
            continue
        for op_id in entry.get("operations", []) or []:
            claim_operation(op_id, "construction:%s" % arm)
    for candidate in bundle.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        for op_id in candidate.get("operation_ids", []) or []:
            claim_operation(op_id, "candidate:%s-%s" % (
                candidate.get("arm"), candidate.get("task_id")))
    for record in records:
        if not isinstance(record, dict):
            continue
        for op_id in record.get("operation_ids", []) or []:
            claim_operation(op_id, "record:%s" % record.get(
                "record_id", "?"))
    for record in (bundle.get("software") or {}).get("use_records") or []:
        if (not isinstance(record, dict)
                or record.get("arm") not in ACQUIRED_ARMS):
            continue
        op_id = record.get("operation_id")
        if isinstance(op_id, str):
            claim_operation(op_id, "software:%s" % record.get(
                "record_id", "?"))
    if set(operations) != claimed:
        problems.append("dispatch-operation-set-mismatch")
    if set(child_receipts) != claimed:
        problems.append("dispatch-operation-receipt-bijection")
    expected_lineage = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        for op_id in record.get("operation_ids", []) or []:
            expected_lineage[op_id] = {
                "operation_id": op_id,
                "arm": record.get("arm"),
                "task_id": record.get("task_id"),
                "source_digest": record.get("executed_source_digest"),
                "artifact_digest": record.get("candidate_digest",
                                                record.get("policy_digest")),
                "input_digest": record.get("input_digest"),
                "result_digest": record.get("result_digest"),
                "receipt_identity": record.get("receipt_identity"),
            }
    for op_id in claimed:
        expected_lineage.setdefault(op_id, {"operation_id": op_id})
    receipt_owners = {}

    def claim_receipt(receipt, op_id, *, child_path=False):
        receipt_identity = receipt.get("receipt_identity") \
            if isinstance(receipt, dict) else None
        if not isinstance(receipt_identity, str) or not receipt_identity:
            return
        if receipt_identity.startswith("local:"):
            problems.append("local-receipt-identity %s" % receipt_identity)
        previous = receipt_owners.get(receipt_identity)
        if previous is not None and (previous != op_id or not child_path):
            problems.append("duplicate-receipt-identity %s" %
                            receipt_identity)
        receipt_owners.setdefault(receipt_identity, op_id)

    for op_id, row in operations.items():
        receipts = row.get("receipts", []) if isinstance(row, dict) else []
        for receipt in receipts:
            claim_receipt(receipt, op_id)
    for op_id, receipt in child_receipts.items():
        claim_receipt(receipt, op_id, child_path=True)
    unresolved_receipts = 0
    for op_id in sorted(claimed):
        row = operations.get(op_id)
        if not isinstance(row, dict) or row.get("operation_id") != op_id:
            problems.append("missing-operation %s" % op_id)
            problems.append("missing-receipt for-operation %s" % op_id)
            continue
        receipts = row.get("receipts", [])
        if len(receipts) > 1:
            problems.append("multiple-terminal-receipts %s" % op_id)
        conflicts = row.get("receipt_conflicts")
        if conflicts is not None and not isinstance(conflicts, list):
            problems.append("receipt-conflict-state-invalid %s" % op_id)
        settled = []
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            try:
                from . import frontier
                frontier.validate_evidence_record(receipt)
            except Exception:
                problems.append("receipt-lineage-mismatch %s" % op_id)
                continue
            details = receipt.get("details")
            if not isinstance(details, dict):
                problems.append("receipt-lineage-mismatch %s" % op_id)
                continue
            raw_payload = details.get("raw_payload")
            result = raw_payload.get("result") if isinstance(
                raw_payload, dict) else None
            required = all(receipt.get(key) for key in (
                "arm", "task_id", "source_digest", "artifact_digest",
                "input_digest", "result_digest", "receipt_identity"))
            if (not required or receipt.get("outcome") not in (
                    "success", "failure") or not isinstance(result, dict)
                    or receipt.get("result_digest") != source_digest(
                        canonical(result))):
                problems.append("receipt-lineage-mismatch %s" % op_id)
                continue
            expected = {key: value for key, value
                        in expected_lineage.get(op_id, {}).items()
                        if value is not None}
            if expected and any(receipt.get(key) != value
                                for key, value in expected.items()):
                problems.append("receipt-lineage-mismatch %s" % op_id)
                continue
            settled.append(receipt)
        unresolved_receipts += _operation_unresolved_count(row)
        if not settled:
            problems.append("missing-receipt for-operation %s" % op_id)
        child = child_receipts.get(op_id)
        if child not in settled:
            problems.append("missing-child-receipt %s" % op_id)
    return operations, unresolved_receipts


def _check_absent_usage(bundle: dict, problems: list) -> None:
    """A dispatch that reported no usage did not report zero.

    A measured zero is a claim about the provider, and a claim about the
    provider needs a witness that observed it. So the question is never
    whether the number is zero, only whether the source names a receipt
    that could have put it there.
    """
    receipts = bundle.get("child_receipts")
    receipts = receipts if isinstance(receipts, dict) else {}
    witnessed = any(
        isinstance(receipt, dict)
        and isinstance(receipt.get("usage"), dict)
        and receipt["usage"].get("charge_units") is not None
        and receipt["usage"].get("charge_units") != "unknown"
        for receipt in receipts.values())
    if witnessed:
        return
    accounting = bundle.get("accounting")
    if not isinstance(accounting, dict):
        return
    billed = accounting.get("billed_units")
    if (isinstance(billed, dict) and _is_count(billed.get("measured"))
            and billed["measured"] == 0
            and billed.get("measurement_status") == "measured"
            and not _names_a_provider_witness(billed.get("source"))):
        problems.append("billed-unknown-scored-as-zero")


def _names_a_provider_witness(source) -> bool:
    if not isinstance(source, str) or not source:
        return False
    return any(marker in source.lower() for marker in (
        "receipt", "provider", "gateway", "attested", "invoice"))


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
        status = entry.get("measurement_status")
        source = entry.get("source")
        if status is None:
            problems.append("accounting-measurement-status-missing %s" % key)
        elif status not in MEASUREMENT_STATUSES:
            problems.append("accounting-measurement-status-invalid %s %r"
                            % (key, status))
        if key == "unresolved_exposure":
            if status == "unresolved":
                if not _is_count(measured):
                    problems.append("accounting-unresolved-value-invalid %s"
                                    % key)
            elif measured != "unknown" and not _is_count(measured):
                problems.append("accounting-unmeasured-value-invalid %s" % key)
            if (recomputed_counts.get(key, 0) > 0
                    and status != "unresolved"):
                problems.append("accounting-unresolved-exposure-status %s" % key)
            if (recomputed_counts.get(key, 0) == 0
                    and status == "unresolved"):
                problems.append("accounting-unresolved-exposure-status %s" % key)
        elif status == "measured":
            if not _is_count(measured):
                problems.append("accounting-measured-value-invalid %s" % key)
        elif measured != "unknown":
            problems.append("accounting-unmeasured-value-invalid %s" % key)
        if not isinstance(source, str) or not source:
            problems.append("accounting-source-missing %s" % key)
        if key == "billed_units" and measured == 0 and (
                status != "measured" or not isinstance(source, str)
                or not source):
            problems.append("billed-unknown-scored-as-zero")
        if key in RECOUNTABLE and _is_count(measured) and \
                measured != recomputed_counts.get(key):
            problems.append("accounting-%s-mismatch reported=%r "
                            "recomputed=%d" % (key, measured,
                                               recomputed_counts[key]))


def _check_resume(bundle: dict, total_model: int, problems: list) -> dict:
    """A resume ledger must not lower a count the lineage already proves.

    A resume record says where the run picked up and how many calls had
    been consumed by then. The dispatches in the bundle are the whole
    visible run, so by the time the run reached `resumed_at_dispatch` it
    had already spent at least that many. A carried count below that is
    the count going backwards: a restart that forgot what it had done.
    A carried count above the visible dispatches is the opposite error, a
    run claiming history it did not export, and is checked here.
    """
    resume = bundle.get("resume")
    if resume is None:
        return {}
    if not isinstance(resume, dict):
        problems.append("resume-ledger-malformed")
        return {}
    for key in ("carried_calls", "resumed_at_dispatch"):
        if key in resume and not _is_count(resume[key]):
            problems.append("resume-ledger-field-malformed %s" % key)
    carried = resume.get("carried_calls")
    resumed_at = resume.get("resumed_at_dispatch")
    if not _is_count(carried) or not _is_count(resumed_at):
        return {}
    if carried < min(resumed_at, total_model):
        problems.append("resume-count-rollback carried=%d dispatched=%d"
                        % (carried, min(resumed_at, total_model)))
    if carried > total_model:
        problems.append("resume-count-exceeds-dispatches carried=%d "
                        "dispatched=%d" % (carried, total_model))
    return {"carried_calls": carried, "source": resume.get("source"),
            "resumed_at_dispatch": resumed_at}


def recomputed_accounting(bundle: dict) -> dict:
    """The accounting as typed values, not as loose fields.

    A class the verifier can re-derive from the bundle carries a
    `Recomputed`; a class only the runtime could measure carries an
    `Attested` naming its witness. The mapping is the whole point: an
    attested number cannot be handed to a caller expecting a recount
    without a type error, and a recount cannot be given a source it did
    not have.
    """
    ledger = bundle.get("dispatch_ledger")
    dispatches = sum(1 for entry in ledger
                     if isinstance(entry, dict)
                     and not entry.get("replay", False)) \
        if isinstance(ledger, list) else 0
    witness_acquisition = 0
    for section in ("development", "assessment", "audit"):
        for episode in bundle.get(section) or []:
            if isinstance(episode, dict) and _is_count(
                    episode.get("witness_queries")):
                witness_acquisition += episode["witness_queries"]
    witness_use = 0
    for record in bundle.get("use_records") or []:
        if not isinstance(record, dict):
            continue
        queries = (record.get("costs") or {}).get("witness_queries")
        if _is_count(queries):
            witness_use += queries
    recounted = {
        "model_dispatches": dispatches,
        "tool_queries": witness_acquisition + witness_use,
        "unresolved_exposure": unresolved_exposure_count(
            bundle.get("operations") or {}),
    }
    table = {}
    claimed = bundle.get("accounting")
    claimed = claimed if isinstance(claimed, dict) else {}
    for name in RESOURCE_CLASSES:
        entry = claimed.get(name)
        if name in RECOUNTABLE:
            table[name] = Recomputed(str(recounted[name]))
            continue
        status = entry.get("measurement_status") if isinstance(
            entry, dict) else None
        value = entry.get("measured") if isinstance(entry, dict) else None
        source = (entry.get("source") if isinstance(entry, dict) else "") or ""
        if status == "measured" and _is_count(value):
            table[name] = Attested(value, source or "unattested", status)
        else:
            # An entry too malformed to attest to is reported as unknown
            # rather than raised on. This table is built while the bundle
            # is already failing, and a reporting path that raises erases
            # every problem found so far.
            table[name] = Attested(
                pairs.UNKNOWN, source or "unattested", status or "unknown")
    return table


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
    tie = rule.get("tie")
    winner = None
    status = "incomplete" if missing else "complete"
    if not missing:
        winner = select_m4_winner(means, margin, tie)
    claimed = bundle.get("claimed", {})
    if not isinstance(claimed, dict) or "winner" not in claimed:
        problems.append("comparison-claimed-missing")
    elif (claimed.get("winner") or "none") != (winner or "none"):
        problems.append("comparison-verdict-mismatch")
    return {"status": status, "winner": winner, "missing_arms": missing,
            "means": means, "audit_means": audit_means}


def _verify_software_domain(bundle: dict, freeze: dict) -> tuple[list, dict]:
    tasks = set(freeze.get("software_tasks") or [])
    if not tasks:
        if "software" in bundle:
            return ["software-domain-unexpected"], {}
        return [], {}
    software = bundle.get("software")
    records = software.get("use_records") if isinstance(software, dict) else None
    outcomes = software.get("outcomes") if isinstance(software, dict) else None
    if not isinstance(records, list) or not isinstance(outcomes, list):
        return ["software-domain-shape-invalid"], {}
    receipts = bundle.get("child_receipts")
    if not isinstance(receipts, dict):
        return ["software-domain-lineage-missing"], {}
    problems = []
    recomputed = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            problems.append("software-use-record-malformed")
            continue
        key = (record.get("arm"), record.get("task_id"),
               record.get("operation_id"))
        if key in seen:
            problems.append("software-use-record-duplicate %s" % (key,))
        seen.add(key)
        receipt = receipts.get(record.get("operation_id"))
        result = (((receipt.get("details") or {}).get("raw_payload") or {})
                  .get("result") if isinstance(receipt, dict) else None)
        if (record.get("task_id") not in tasks
                or record.get("arm") not in ARMS
                or not isinstance(receipt, dict)
                or receipt.get("arm") != record.get("arm")
                or receipt.get("task_id") != record.get("task_id")
                or receipt.get("receipt_identity") != record.get(
                    "receipt_identity")
                or receipt.get("input_digest") != record.get("input_digest")
                or receipt.get("result_digest") != record.get("result_digest")
                or not isinstance(result, dict)
                or result.get("observed") != record.get("observed")
                or result.get("queries") != record.get("queries")
                or record.get("child_result") != result
                or receipt.get("result_digest") != source_digest(
                    canonical(result))):
            problems.append("software-use-lineage-mismatch %s" % (
                record.get("record_id", "?")))
            continue
        recomputed.append({
            "arm": record["arm"], "task_id": record["task_id"],
            "expected": record["expected"], "observed": record["observed"],
            "queries": record["queries"]})
    if {row.get("task_id") for row in records if isinstance(row, dict)} != tasks:
        problems.append("software-use-task-set-mismatch")
    expected_keys = {(arm, task_id) for arm in ARMS for task_id in tasks}
    actual_keys = {(row.get("arm"), row.get("task_id"))
                   for row in records if isinstance(row, dict)}
    if actual_keys != expected_keys:
        problems.append("software-arm-task-membership-mismatch")
    for row in records:
        if not isinstance(row, dict):
            continue
        expected_quality = _software_expected_quality(str(row.get("task_id")))
        if row.get("expected") != expected_quality:
            problems.append("software-frozen-quality-mismatch %s" % (
                row.get("record_id", "?")))
    expected = [
        {"arm": row["arm"], "task_id": row["task_id"],
         "expected": row["expected"], "observed": row["observed"],
         "queries": row["queries"]}
        for row in records if isinstance(row, dict)]
    if outcomes != expected:
        problems.append("software-outcome-mismatch")
    return sorted(set(problems)), {
        "software_use_records": len(records),
        "software_outcomes": len(outcomes)}


def _bundle_shape_problems(bundle: dict) -> list:
    problems = []
    expected = {
        "schema": str, "protocol": dict, "authority": dict,
        "construction": dict, "operations": dict, "child_receipts": dict,
        "accounting": dict, "claimed": dict, "development": list,
        "assessment": list, "audit": list, "dispatch_ledger": list,
        "candidates": list, "use_records": list, "software": dict,
    }
    for key, kind in expected.items():
        if key in bundle and not isinstance(bundle[key], kind):
            problems.append("bundle-shape-invalid %s" % key)
    freeze = bundle.get("freeze")
    if freeze is not None and not isinstance(freeze, dict):
        problems.append("bundle-shape-invalid freeze")
    elif isinstance(freeze, dict):
        nested = {
            "policy_identities": dict, "method_repertoires": dict,
            "arm_contracts": dict, "history_reference": dict, "tasks": dict,
            "caps": dict, "metric_rule": dict, "resource_rule": dict,
            "config": dict, "construction_allowance": dict,
        }
        for key, kind in nested.items():
            if key in freeze and not isinstance(freeze[key], kind):
                problems.append("bundle-shape-invalid freeze.%s" % key)
    software = bundle.get("software")
    if isinstance(software, dict):
        for key in ("use_records", "outcomes"):
            if key in software and not isinstance(software[key], list):
                problems.append("bundle-shape-invalid software.%s" % key)
    accounting = bundle.get("accounting")
    if isinstance(accounting, dict):
        for key in RESOURCE_CLASSES:
            if key in accounting and not isinstance(accounting[key], dict):
                problems.append("bundle-shape-invalid accounting.%s" % key)
    return problems


def verify_bundle(bundle: dict, scorer_private: dict | None = None) -> dict:
    try:
        is_bundle = isinstance(bundle, dict)
        protocol = bundle.get("protocol") if is_bundle else None
        if (is_bundle
                and (bundle.get("schema") == OUTPUT_SCHEMA
                     or "candidate_view" in bundle
                     or (isinstance(protocol, dict)
                         and protocol.get("protocol") == OUTPUT_PROTOCOL_ID))):
            verified = _verify_output(bundle, scorer_private)
            verified["verification_scope"] = {
                "dispatch_authority": "bundle-only",
                "external_operation_store_checked": False,
                "sibling_evidence_checked": False,
            }
            return verified
        return _verify_m4_bundle(bundle)
    except (TypeError, AttributeError, KeyError, IndexError, ValueError):
        return {"status": "fail", "problems": ["bundle-shape-invalid"],
                "recomputed": {}}


def _verify_m4_bundle(bundle: dict) -> dict:
    problems: list = []
    if not isinstance(bundle, dict):
        return {"status": "incomplete", "problems": ["empty-bundle"],
                "recomputed": {}}
    problems.extend(_bundle_shape_problems(bundle))
    if problems:
        return {"status": "fail", "problems": sorted(set(problems)),
                "recomputed": {}}
    if not isinstance(bundle.get("freeze"), dict):
        return {"status": "incomplete", "problems": ["missing-freeze"],
                "recomputed": {}}
    freeze = _check_freeze(bundle, problems)
    if freeze is None:
        return {"status": "incomplete",
                "problems": sorted(set(problems)), "recomputed": {}}
    for key, expected in (("study", freeze.get("study")),
                          ("study_root", freeze.get("study_root")),
                          ("freeze_digest", freeze.get("freeze_digest"))):
        if (key in bundle and expected is not None
                and bundle.get(key) != expected):
            problems.append("bundle-%s-mismatch" % key)
    if bundle.get("status") not in (None, "available", "incomplete"):
        problems.append("bundle-status-invalid")
    identities = _check_identities(freeze, problems)
    _check_study_identity(bundle, freeze, problems)
    _check_source_exclusivity(freeze, problems)
    _check_no_hidden_answers(freeze, problems)
    _check_arm_contracts(freeze, identities, problems)
    _check_task_labels(freeze, problems)
    repertoire_digests = _check_repertoires(freeze, problems)
    _dev, assess, audit = _split_tasks(freeze, problems)
    _check_authoritative_protocol(bundle, freeze, problems)
    episodes = _check_episodes(bundle, freeze, identities, problems)
    construction = _check_construction(bundle, freeze, identities,
                                       problems)
    records, qualities = _check_use_records(
        bundle, freeze, identities, repertoire_digests, assess, audit,
        problems)
    _check_candidates(bundle, freeze, identities, records, assess, audit,
                      problems)
    _check_boolean_candidates(bundle, freeze, identities, problems)
    dispatch_ledger = _check_dispatch_ledger(bundle, construction, problems)
    _operations, unresolved_receipts = _check_operations(
        bundle, episodes, construction, records, identities, problems)
    unresolved_receipts = max(
        unresolved_receipts, dispatch_unresolved_count(dispatch_ledger))
    total_model = sum(1 for entry in dispatch_ledger
                      if isinstance(entry, dict)
                      and not entry.get("replay", False))
    total_construction = 0
    for entry in construction.values():
        if isinstance(entry, dict) and _is_count(entry.get("calls")):
            total_construction += entry["calls"]
    for arm in ACQUIRED_ARMS:
        entry = construction.get(arm, {})
        operation_ids = set(entry.get("operations") or []) \
            if isinstance(entry, dict) else set()
        actual = sum(1 for dispatch in dispatch_ledger
                     if isinstance(dispatch, dict)
                     and dispatch.get("operation_id") in operation_ids
                     and not dispatch.get("replay", False))
        if isinstance(entry, dict) and entry.get("calls") != actual:
            problems.append("construction-dispatch-ledger-mismatch %s" % arm)
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
    history_token_values = [e.get("history_tokens") for _, e in episodes]
    for entry in construction.values():
        if isinstance(entry, dict):
            history_token_values.append(entry.get("history_tokens"))
    history_unknown = any(
        value == "unknown" or not _is_count(value)
        for value in history_token_values)
    if not history_unknown:
        history_unknown = any(
            identity.get("history_tokens") == "unknown"
            for identity in identities.values()
            if isinstance(identity, dict))
    history_tokens = ("unknown" if history_unknown
                     else sum(value for value in history_token_values
                              if _is_count(value)))
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
    if _is_count(ceiling) and _is_count(history_tokens) \
            and history_tokens > ceiling:
        problems.append("history-ceiling-exceeded total=%d ceiling=%d"
                        % (history_tokens, ceiling))
    _check_accounting(bundle, {
        "model_dispatches": total_model,
        "tool_queries": witness_acquisition + witness_use,
        "unresolved_exposure": unresolved_receipts}, problems)
    _check_absent_usage(bundle, problems)
    resume = _check_resume(bundle, total_model, problems)
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
    software_problems, software_recomputed = _verify_software_domain(
        bundle, freeze)
    problems.extend(software_problems)
    recomputed = {"model_calls": total_model,
                  "construction_calls": total_construction,
                  "history_tokens": history_tokens,
                  "failed_attempts": failed_attempts,
                  "witness_acquisition": witness_acquisition,
                  "witness_use": witness_use,
                  "use_records": len(records),
                  "worst_case": worst,
                  "quality_by_arm": by_arm,
                  "resume": resume,
                  "accounting": {
                      name: str(value)
                      for name, value in recomputed_accounting(
                          bundle).items()},
                  "comparison": comparison}
    recomputed.update(software_recomputed)
    status = "fail" if problems else (
        "incomplete" if bundle.get("status") == "incomplete" else "pass")
    return {"status": status, "problems": sorted(set(problems)),
            "recomputed": recomputed}


def _output_public_task(split, seed):
    from . import boolean_rule as rules
    from . import rule_learner
    task = rules.make_task(split, int(seed))
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES,
                                                int(seed))
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        learner.observe(pick, session.query(pick))
    return task, session


def boolean_candidate_input_digest(task_id: str, split: str, seed: int,
                                   history: list) -> str:
    _task, session = _output_public_task(split, int(seed))
    return source_digest(canonical({
        "task_id": task_id, "split": split, "seed": int(seed),
        "history": list(history),
        "history_digest": source_digest(canonical(list(history))),
        "public_input": session.output_model_input()}))


def _p0_control_expected(split: str, seed: int) -> dict:
    from . import boolean_rule as rules
    from . import rule_learner
    task = rules.make_task(split, int(seed))
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES,
                                                int(seed))
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        learner.observe(pick, session.query(pick))
    committed = session.commit_predictor(learner.predict(dict(session.queried)))
    predictor = {"specs": [dict(spec) for spec in committed["specs"]],
                 "tables": list(committed["tables"])}
    return {"task_id": task["task_id"], "split": split, "seed": int(seed),
            "score": session.score(committed),
            "predictor_digest": source_digest(canonical(committed)),
            "result_digest": source_digest(canonical(predictor)),
            "predictor": predictor, "queries": len(session.queried)}


def _task_id_for(split: str, seed: Any) -> str:
    """The instrument's own id for a split and seed, read from the generator."""
    from . import boolean_rule as rules
    return rules.make_task(split, int(seed))["task_id"]


def verifier_digest() -> str:
    """This verifier's own digest, reported rather than checked.

    A checker cannot attest its own integrity by re-deriving its hash against
    a value frozen before it was written; it only ever proves that something
    changed. Reporting the digest lets a reader bind a verdict to the version
    that produced it without making the bundle unverifiable by construction.
    """
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _check_output_digest_maps(freeze: dict, root, problems: list) -> None:
    for field, expected_paths in (
            ("code_digests", OUTPUT_CODE_PATHS),
            ("source_digests", OUTPUT_SOURCE_PATHS)):
        digests = freeze.get(field)
        if (not isinstance(digests, dict)
                or set(digests) != set(expected_paths)):
            problems.append("frozen-digest-paths-mismatch %s" % field)
            continue
        for path in expected_paths:
            try:
                actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
            except OSError:
                problems.append("frozen-source-missing %s" % path)
                continue
            if actual != digests[path]:
                problems.append("frozen-source-mismatch %s" % path)


def _output_shape_problems(bundle: dict) -> list:
    problems = []
    if bundle.get("schema") != OUTPUT_SCHEMA:
        problems.append("bundle-shape-invalid schema")
    freeze = bundle.get("protocol")
    if freeze is not None and not isinstance(freeze, dict):
        problems.append("bundle-shape-invalid protocol")
    elif isinstance(freeze, dict):
        for key in ("history", "prompt", "code_digests", "source_digests"):
            if key in freeze and not isinstance(freeze[key], dict):
                problems.append("bundle-shape-invalid protocol.%s" % key)
        prompt = freeze.get("prompt")
        if isinstance(prompt, dict) and "rendered_digests" in prompt \
                and not isinstance(prompt["rendered_digests"], dict):
            problems.append("bundle-shape-invalid protocol.prompt.rendered_digests")
    view = bundle.get("candidate_view")
    if view is not None and not isinstance(view, dict):
        problems.append("bundle-shape-invalid candidate_view")
    elif isinstance(view, dict):
        for key in ("dispatches", "durable_receipts", "incumbent_control"):
            if key in view and not isinstance(view[key], list):
                problems.append("bundle-shape-invalid candidate_view.%s" % key)
    return problems


def _verify_scorer_private(scorer_private: dict | None, freeze: dict,
                           expected_rows: list, problems: list) -> None:
    if scorer_private is None:
        problems.append("scorer-private-missing")
        return
    expected_keys = {
        "schema", "protocol", "study", "study_root", "run_id",
        "source_identity", "freeze_digest", "scores", "envelope_digest"}
    if set(scorer_private) != expected_keys:
        problems.append("scorer-private-schema-invalid")
        return
    if scorer_private.get("schema") != SCORER_PRIVATE_SCHEMA:
        problems.append("scorer-private-schema-invalid")
    if scorer_private.get("protocol") != freeze.get("protocol"):
        problems.append("scorer-private-protocol-mismatch")
    if scorer_private.get("study") != freeze.get("study"):
        problems.append("scorer-private-study-mismatch")
    if scorer_private.get("study_root") != freeze.get("study_root"):
        problems.append("scorer-private-study-root-mismatch")
    if scorer_private.get("run_id") != freeze.get("run_id"):
        problems.append("scorer-private-run-mismatch")
    if scorer_private.get("source_identity") != freeze.get("source_identity"):
        problems.append("scorer-private-source-mismatch")
    if scorer_private.get("freeze_digest") != freeze.get("freeze_digest"):
        problems.append("scorer-private-freeze-mismatch")
    body = {key: value for key, value in scorer_private.items()
            if key != "envelope_digest"}
    if scorer_private.get("envelope_digest") != source_digest(canonical(body)):
        problems.append("scorer-private-envelope-digest-mismatch")
    rows = scorer_private.get("scores")
    if not isinstance(rows, list):
        problems.append("scorer-private-scores-malformed")
        return
    keys = [(row.get("arm"), row.get("task_id"))
            for row in rows if isinstance(row, dict)]
    if len(keys) != len(rows) or len(keys) != len(set(keys)):
        problems.append("scorer-private-score-duplicate")
    sort_key = lambda row: (row.get("arm", ""), row.get("task_id", ""))
    if sorted(rows, key=sort_key) != sorted(expected_rows, key=sort_key):
        problems.append("scorer-private-score-set-mismatch")


def _verify_output(bundle: dict, scorer_private: dict | None = None) -> dict:
    from . import live_construct as live
    problems: list = []
    if not isinstance(bundle, dict):
        return {"status": "incomplete", "problems": ["empty-bundle"]}
    shape_problems = _output_shape_problems(bundle)
    if shape_problems:
        return {"status": "fail", "problems": sorted(set(shape_problems))}
    freeze = bundle.get("protocol")
    if not isinstance(freeze, dict):
        return {"status": "incomplete", "problems": ["missing-freeze"]}
    if freeze.get("protocol") != OUTPUT_PROTOCOL_ID:
        problems.append("protocol-mismatch")
    if freeze.get("study_root") != OUTPUT_STUDY_ROOT:
        problems.append("retired-study-root")
    if freeze.get("freeze_digest") != freeze_digest(freeze):
        problems.append("freeze-digest-mismatch")
    for key in ("protocol_id", "study", "study_root", "run_id",
                "source_identity", "freeze_digest"):
        expected = freeze.get("protocol") if key == "protocol_id" \
            else freeze.get(key)
        if bundle.get(key) != expected:
            problems.append("run-%s-mismatch" % key.replace("_", "-"))
    if bundle.get("status") not in (None, "available", "incomplete"):
        problems.append("bundle-status-invalid")
    if bundle.get("status") in ("incomplete", "unavailable"):
        problems.append("study-incomplete")
        claims = bundle.get("claims")
        if claims is not None and claims != {
                "task_utility": "not-established",
                "transfer": "not-established",
                "recursive_improvement": "not-established"}:
            problems.append("research-claims-invalid")
    if freeze.get("route") != live.OUTPUT_ROUTE:
        problems.append("route-freeze-mismatch")
    if freeze.get("limits") != live.OUTPUT_LIMITS:
        problems.append("limits-freeze-mismatch")
    if freeze.get("tasks") != live.OUTPUT_TASKS:
        problems.append("tasks-freeze-mismatch")
    if (freeze.get("arms") != ["P0", "P1", "P2"]
            or freeze.get("order") != ["P0", "P1", "P2"]):
        problems.append("p0-arm-contract-missing")
    p0 = freeze.get("p0_incumbent")
    from . import boolean_rule as _p0_rules
    expected_p0_source = canonical({
        "kind": "fixed-incumbent", "solver": "VersionSpaceLearner",
        "entrypoint": "experiments.ad01.rule_learner.VersionSpaceLearner",
        "class_digest": _p0_rules.class_digest(), "query_cap": 8})
    if (not isinstance(p0, dict)
            or p0.get("kind") != "fixed-incumbent"
            or p0.get("source") != expected_p0_source
            or p0.get("source_digest") != source_digest(expected_p0_source)):
        problems.append("p0-contract-invalid")
    else:
        seals = p0.get("task_seals")
        for split, seed in live.OUTPUT_TASKS.items():
            task_id = _task_id_for(split, seed)
            _task, session = _output_public_task(split, int(seed))
            expected_seal = {
                "split": split, "seed": int(seed),
                "public_input_digest": source_digest(
                    canonical(session.output_model_input()))}
            if not isinstance(seals, dict) or seals.get(task_id) != expected_seal:
                problems.append("p0-task-seal-mismatch %s" % task_id)
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    _check_output_digest_maps(freeze, root, problems)
    permitted = live.output_permitted_history()
    expected_history = {
        "P1": {"entries": [], "digest": source_digest("[]")},
        "P2": {"digest": source_digest(canonical(permitted))},
    }
    if freeze.get("history") != expected_history:
        problems.append("history-freeze-mismatch")
    prompt = freeze.get("prompt") or {}
    if prompt.get("template_digest") != source_digest(
            live.OUTPUT_PROMPT_TEMPLATE):
        problems.append("prompt-template-digest-mismatch")
    candidate_view = bundle.get("candidate_view") or {}
    durable_receipts = candidate_view.get("durable_receipts")
    if not isinstance(durable_receipts, list):
        problems.append("durable-receipts-missing")
        durable_receipts = []
    durable_pairs = [
        (receipt.get("operation_id"), receipt) for receipt in durable_receipts
        if isinstance(receipt, dict)
        and isinstance(receipt.get("operation_id"), str)]
    durable_operation_ids = [operation_id for operation_id, _receipt
                             in durable_pairs]
    durable_by_operation = dict(durable_pairs)
    duplicate_receipt_operations = {
        operation_id for operation_id in durable_operation_ids
        if durable_operation_ids.count(operation_id) > 1}
    lost_response_disposition = [
        {"operation_id": operation_id,
         "reservation_id": receipt.get("reservation_id"),
         "exposure": receipt["exposure"],
         "unresolved_exposure": receipt["unresolved_exposure"],
         "measurement_status": receipt.get("measurement_status")}
        for operation_id, receipt in sorted(durable_by_operation.items())
        if _is_lost_response_receipt(receipt)]
    dispatches = candidate_view.get("dispatches")
    if not isinstance(dispatches, list):
        problems.append("dispatches-missing")
        dispatches = []
    physical_dispatches = [entry for entry in dispatches
                           if isinstance(entry, dict)
                           and entry.get("replay", False) is False]
    replay_dispatches = [entry for entry in dispatches
                         if isinstance(entry, dict)
                         and entry.get("replay", False) is True]
    for entry in dispatches:
        if (isinstance(entry, dict)
                and not isinstance(entry.get("replay", False), bool)):
            problems.append("dispatch-replay-state-invalid %s"
                            % entry.get("operation_id", "?"))
    if len(physical_dispatches) > live.OUTPUT_LIMITS["max_dispatches"]:
        problems.append("dispatch-ceiling-exceeded")
    if candidate_view.get("dispatch_count") != len(dispatches):
        problems.append("dispatch-count-mismatch")
    if candidate_view.get("physical_dispatch_count") != len(physical_dispatches):
        problems.append("physical-dispatch-count-mismatch")
    if candidate_view.get("replay_count") != len(replay_dispatches):
        problems.append("replay-count-mismatch")
    operation_counts = {}
    for entry in physical_dispatches:
        operation_id = entry.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            problems.append("physical-operation-identity-missing %s"
                            % entry.get("evidence_digest", "?"))
            continue
        operation_counts[operation_id] = operation_counts.get(
            operation_id, 0) + 1
    automatic_retry_count = sum(max(0, count - 1)
                                for count in operation_counts.values())
    if bundle.get("candidate_view", {}).get(
            "automatic_retry_count") != automatic_retry_count:
        problems.append("automatic-retry-count-mismatch")
    if automatic_retry_count != live.OUTPUT_LIMITS["automatic_retries"]:
        problems.append("automatic-retries-exceeded")
    seen_ids = set()
    physical_keys = set()
    operation_bindings = {}
    by_task: dict = {}
    accepted = []
    private_rows = []
    for entry in dispatches:
        if not isinstance(entry, dict):
            problems.append("malformed-dispatch")
            continue
        if (entry.get("replay", False) is False
                and entry.get("new_dispatch") is False):
            problems.append("physical-operation-not-authoritative %s"
                            % entry.get("operation_id", "?"))
        try:
            from . import frontier
            frontier.validate_evidence_record(
                entry, kind="gateway-dispatch")
        except frontier.Refused:
            problems.append("dispatch-evidence-invalid")
        required = {
            "version", "kind", "evidence_digest", "receipt_identity",
            "raw_payload_digest", "details", "outcome",
            "operation_id", "arm", "task_id", "attempt", "requested_model",
            "returned_model", "endpoint", "provider", "tier",
            "requested_output_cap",
            "response_digest", "prompt_digest", "raw_prompt", "raw_response",
            "stop_reason", "usage", "billed", "charge_units",
            "parse_outcome", "accepted_candidate_digest"}
        if required - set(entry):
            problems.append("dispatch-evidence-incomplete")
        if {"score", "target_tables", "private_answer", "scorer_private"} \
                & set(entry):
            problems.append("private-scorer-field-in-candidate-view")
        if entry.get("parse_outcome") not in {
                "pending", "transport-error", "empty", "too-long",
                "parse-failed", "route-refused", "accepted"}:
            problems.append("parse-outcome-invalid")
        if not isinstance(entry.get("usage"), dict):
            problems.append("usage-missing")
        op_id = entry.get("operation_id")
        replay = entry.get("replay", False)
        if not isinstance(op_id, str) or not op_id:
            problems.append("duplicate-or-missing-operation-id")
            continue
        if not isinstance(replay, bool):
            problems.append("dispatch-replay-state-invalid %s" % op_id)
            continue
        dispatch_id = entry.get("evidence_digest")
        if (not isinstance(dispatch_id, str) or not dispatch_id
                or (dispatch_id in seen_ids and not replay)):
            problems.append("duplicate-physical-dispatch")
        if isinstance(dispatch_id, str):
            seen_ids.add(dispatch_id)
        arm = entry.get("arm")
        task_id = entry.get("task_id")
        # The id belongs to the generator. Restating the format here meant
        # that when the worlds made their ids opaque this stopped resolving,
        # every dispatch fell through as `dispatch-identity-unknown`, and the
        # route and response checks below it never ran.
        split = next((key for key, seed in live.OUTPUT_TASKS.items()
                      if task_id == _task_id_for(key, seed)), None)
        if arm not in ("P1", "P2") or split is None:
            problems.append("dispatch-identity-unknown")
            continue
        if entry.get("attempt") not in (1, 2):
            problems.append("dispatch-attempt-invalid")
            continue
        physical_key = (arm, split, entry.get("attempt"))
        if not replay:
            if physical_key in physical_keys:
                problems.append("duplicate-initial-dispatch %s-%s" % (
                    arm, split))
            physical_keys.add(physical_key)
        expected_operation_id = live.output_operation_id(
            arm, split, int(live.OUTPUT_TASKS[split]), entry["attempt"],
            round_run_id=freeze["run_id"])
        if op_id != expected_operation_id:
            problems.append("operation-id-not-frozen %s" % op_id)
        operation_binding = (arm, split, entry.get("attempt"))
        if op_id in operation_bindings and operation_bindings[op_id] != operation_binding:
            problems.append("operation-id-rebound %s" % op_id)
        operation_bindings[op_id] = operation_binding
        if entry.get("requested_model") != live.OUTPUT_ROUTE[
                "requested_model"]:
            problems.append("requested-model-mismatch")
        if entry.get("requested_output_cap") != live.OUTPUT_LIMITS[
                "max_output_tokens"]:
            problems.append("output-cap-mismatch")
        raw_prompt = entry.get("raw_prompt")
        raw_response = entry.get("raw_response")
        if not isinstance(raw_prompt, str) or entry.get("prompt_digest") != \
                source_digest(raw_prompt):
            problems.append("prompt-digest-mismatch")
        # route-refused and transport-error finalize with no observed response, so
        # they carry neither route metadata nor a raw response; a lost response is
        # exempt only when its durable receipt proves that same no-observation fact.
        receipt = durable_by_operation.get(op_id)
        lost_response = _claims_lost_response(receipt)
        if lost_response and not _is_lost_response_receipt(receipt):
            problems.append("durable-receipt-lost-response-invalid %s" % op_id)
        lost_response_exempt = (lost_response
                                and _is_lost_response_receipt(receipt))
        legacy_no_observation = (
            entry.get("parse_outcome") in {"route-refused", "transport-error"}
            and not lost_response)
        if not (legacy_no_observation or lost_response_exempt):
            actual_route = {key: entry.get(key) for key in
                            ("returned_model", "endpoint", "provider", "tier")}
            expected_route = {
                "returned_model": live.OUTPUT_ROUTE["resolved_model"],
                "endpoint": live.OUTPUT_ROUTE["endpoint"],
                "provider": live.OUTPUT_ROUTE["provider"],
                "tier": live.OUTPUT_ROUTE["tier"]}
            if actual_route != expected_route:
                problems.append("route-metadata-mismatch")
            if not isinstance(raw_response, str) or entry.get("response_digest") \
                    != source_digest(raw_response):
                problems.append("response-digest-mismatch")
        if isinstance(raw_response, str) and len(raw_response) > \
                live.OUTPUT_LIMITS["max_response_characters"]:
            problems.append("response-character-cap-exceeded")
        if not replay:
            by_task.setdefault((arm, split), []).append(entry)
        if entry.get("parse_outcome") == "accepted" and not replay:
            accepted.append((arm, split, entry))
    candidate_view = bundle.get("candidate_view") or {}
    dispatch_by_operation = {
        entry.get("operation_id"): entry for entry in dispatches
        if isinstance(entry, dict) and isinstance(entry.get("operation_id"), str)
    }
    durable_by_operation = {}
    receipt_owners = {}
    for receipt in durable_receipts:
        if not isinstance(receipt, dict):
            problems.append("durable-receipt-malformed")
            continue
        operation_id = receipt.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            problems.append("durable-receipt-operation-missing")
            continue
        if operation_id in duplicate_receipt_operations:
            problems.append("multiple-terminal-receipts %s" % operation_id)
            problems.append("duplicate-durable-receipt %s" % operation_id)
        durable_by_operation[operation_id] = receipt
        if operation_id not in dispatch_by_operation:
            problems.append("durable-receipt-unknown-operation %s" % operation_id)
        receipt_identity = receipt.get("receipt_identity")
        if (not isinstance(receipt_identity, str) or not receipt_identity
                or receipt_identity in receipt_owners):
            problems.append("durable-receipt-identity-invalid")
        else:
            receipt_owners[receipt_identity] = operation_id
        required = {
            "operation_id", "receipt_identity", "outcome", "settled",
            "source_digest", "artifact_digest", "input_digest", "result_digest",
            "dispatch_evidence_digest", "dispatch_state", "reconcile_state",
            "usage",
        }
        if required - set(receipt):
            problems.append("durable-receipt-incomplete %s" % operation_id)
        if (not isinstance(receipt.get("receipt_identity"), str)
                or not receipt.get("receipt_identity")
                or not isinstance(receipt.get("usage"), dict)):
            problems.append("durable-receipt-incomplete %s" % operation_id)
        problems.extend(_output_usage_state_problems(receipt))
        if (_claims_lost_response(receipt)
                and not _is_lost_response_receipt(receipt)):
            problems.append("durable-receipt-lost-response-invalid %s"
                            % operation_id)
        if (not _is_lost_response_receipt(receipt)
                and (receipt.get("outcome") in ("unresolved", "conflict")
                     or receipt.get("settled") is False
                     or receipt.get("dispatch_state") in ("unresolved", "conflict")
                     or receipt.get("reconcile_state") in ("unresolved", "conflict")
                     or receipt.get("conflict") is True
                     or receipt.get("receipt_conflicts"))):
            problems.append("durable-receipt-unresolved %s" % operation_id)
        conflicts = receipt.get("receipt_conflicts")
        if conflicts is not None and not isinstance(conflicts, list):
            problems.append("durable-receipt-conflict-state-invalid %s"
                            % operation_id)
        if conflicts:
            if receipt.get("conflict_count") != len(conflicts):
                problems.append("durable-receipt-conflict-count-invalid %s"
                                % operation_id)
            if receipt.get("outcome") != "conflict":
                problems.append("durable-receipt-conflict-outcome-invalid %s"
                                % operation_id)
            for conflict in conflicts:
                if not isinstance(conflict, dict):
                    problems.append("durable-receipt-conflict-malformed %s"
                                    % operation_id)
                    continue
                conflict_usage = conflict.get("usage")
                required_usage = {"input_tokens", "output_tokens", "charge_units",
                                  "charge_scale", "billed"}
                if (not isinstance(conflict.get("receipt_identity"), str)
                        or not conflict.get("receipt_identity")
                        or conflict.get("outcome") not in (
                            "success", "failure", "unknown", "unresolved")
                        or not isinstance(conflict_usage, dict)
                        or required_usage - set(conflict_usage)
                        or not _is_count(conflict.get("unresolved_exposure"))):
                    problems.append("durable-receipt-conflict-usage-invalid %s"
                                    % operation_id)
        if (conflicts and receipt.get("unresolved_exposure")
                != (conflicts[0].get("unresolved_exposure")
                    if isinstance(conflicts[0], dict) else None)):
            problems.append("durable-receipt-conflict-exposure-mismatch %s"
                            % operation_id)
    physical_operation_ids = {
        entry.get("operation_id") for entry in physical_dispatches
        if isinstance(entry.get("operation_id"), str)}
    replay_operation_ids = {
        entry.get("operation_id") for entry in replay_dispatches
        if isinstance(entry.get("operation_id"), str)}
    for entry in replay_dispatches:
        operation_id = entry.get("operation_id")
        if operation_id not in physical_operation_ids:
            problems.append("replay-physical-operation-missing %s"
                            % operation_id)
        if operation_id not in durable_by_operation:
            problems.append("replay-durable-receipt-missing %s" % operation_id)
    for entry in physical_dispatches:
        operation_id = entry.get("operation_id")
        receipt_count = sum(
            1 for receipt in durable_receipts
            if isinstance(receipt, dict)
            and receipt.get("operation_id") == operation_id)
        if receipt_count != 1:
            problems.append("physical-durable-receipt-count-invalid %s"
                            % operation_id)
    dispatch_operation_id_list = [
        entry.get("operation_id") for entry in dispatches
        if isinstance(entry, dict)
        and isinstance(entry.get("operation_id"), str)]
    dispatch_operation_ids = set(dispatch_operation_id_list)
    if len(dispatch_operation_id_list) != len(physical_operation_ids) + len(
            replay_operation_ids):
        problems.append("duplicate-operation-record")
    if dispatch_operation_ids != set(durable_by_operation):
        problems.append("dispatch-operation-receipt-bijection")
    for entry in dispatches:
        if not isinstance(entry, dict):
            continue
        operation_id = entry.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            problems.append("durable-operation-identity-missing")
            continue
        nested = entry.get("durable_receipt")
        receipt = durable_by_operation.get(operation_id)
        if isinstance(nested, list):
            problems.append("durable-nested-receipt-count-invalid %s"
                            % operation_id)
        elif not isinstance(nested, dict):
            problems.append("durable-nested-receipt-missing %s" % operation_id)
        if not isinstance(receipt, dict):
            problems.append("missing-durable-receipt %s" % operation_id)
            continue
        if (isinstance(nested, dict)
                and _output_receipt_binding(nested)
                != _output_receipt_binding(receipt)):
            problems.append("durable-nested-receipt-mismatch %s" % operation_id)
        lineage = {
            "source_digest": entry.get("source_digest"),
            "artifact_digest": entry.get("artifact_digest"),
            "input_digest": entry.get("input_digest"),
            "result_digest": entry.get("result_digest"),
            "dispatch_evidence_digest": (
                entry.get("dispatch_evidence_digest")
                or entry.get("evidence_digest")),
        }
        if any(receipt.get(key) != value for key, value in lineage.items()):
            problems.append("durable-receipt-lineage-mismatch %s" % operation_id)
        if entry.get("parse_outcome") == "accepted":
            if receipt.get("outcome") != "success":
                problems.append("durable-receipt-outcome-mismatch %s"
                                % operation_id)
        elif receipt.get("outcome") not in ("success", "failure", "unresolved"):
            problems.append("durable-receipt-outcome-invalid %s" % operation_id)
        if (not _is_lost_response_receipt(receipt)
                and (receipt.get("dispatch_state") not in (
                    "observed", "reconciled")
                     or receipt.get("reconcile_state") not in (
                        "none", "reconciled"))):
            problems.append("durable-receipt-unresolved %s" % operation_id)
    incumbent_control = (bundle.get("candidate_view") or {}).get(
        "incumbent_control")
    if not isinstance(incumbent_control, list):
        problems.append("p0-control-missing")
        incumbent_control = []
    expected_p0_keys = {_task_id_for(split, seed)
                       for split, seed in live.OUTPUT_TASKS.items()}
    actual_p0_keys = {row.get("task_id") for row in incumbent_control
                      if isinstance(row, dict)}
    if actual_p0_keys != expected_p0_keys or len(incumbent_control) != len(
            expected_p0_keys):
        problems.append("p0-control-task-set-mismatch")
    p0_source_digest = (p0.get("source_digest")
                        if isinstance(p0, dict) else None)
    for row in incumbent_control:
        if not isinstance(row, dict):
            problems.append("malformed-p0-control")
            continue
        task_id = row.get("task_id")
        # The id belongs to the generator. Restating the format here meant
        # that when the worlds made their ids opaque this stopped resolving,
        # every dispatch fell through as `dispatch-identity-unknown`, and the
        # route and response checks below it never ran.
        split = next((key for key, seed in live.OUTPUT_TASKS.items()
                      if task_id == _task_id_for(key, seed)), None)
        if split is None:
            problems.append("p0-control-task-unknown")
            continue
        expected = _p0_control_expected(split, live.OUTPUT_TASKS[split])
        private_rows.append({
            "arm": "P0", "task_id": task_id, "split": split,
            "seed": int(live.OUTPUT_TASKS[split]), "score": expected["score"],
            "queries": expected["queries"],
            "predictor_digest": expected["predictor_digest"],
            "result_digest": expected["result_digest"],
            "source_digest": p0_source_digest})
        forbidden = {"score", "scores", "target_tables", "private_answer",
                     "scorer_private"}
        if forbidden & set(row):
            problems.append("p0-private-scorer-field")
        if (row.get("arm") != "P0" or row.get("executed") != "incumbent"
                or row.get("model_calls") != 0
                or row.get("source_digest") != p0_source_digest
                or row.get("split") != split
                or row.get("seed") != live.OUTPUT_TASKS[split]
                or row.get("predictor") != expected["predictor"]
                or row.get("predictor_digest") != expected["predictor_digest"]
                or row.get("result_digest") != expected["result_digest"]
                or row.get("queries") != expected["queries"]):
            problems.append("p0-control-result-mismatch %s" % task_id)
    if any(isinstance(row, dict) and row.get("arm") != "P0"
           for row in incumbent_control):
        problems.append("p0-control-arm-substitution")
    if any(isinstance(row, dict) and row.get("arm") == "P0"
           for row in dispatches):
        problems.append("p0-model-dispatch-present")
    expected_prompts = {}
    for arm in ("P1", "P2"):
        history = [] if arm == "P1" else permitted
        for split, seed in live.OUTPUT_TASKS.items():
            _task, session = _output_public_task(split, seed)
            for attempt in (1, 2):
                raw = live.render_output_prompt(session.output_model_input(),
                                                history, attempt)
                expected_prompts[(arm, split, attempt)] = raw
                key = "%s:%s:%d:a%d" % (arm, split, seed, attempt)
                if prompt.get("rendered_digests", {}).get(key) != \
                        source_digest(raw):
                    problems.append("frozen-rendered-prompt-mismatch %s" % key)
    for arm in ("P1", "P2"):
        for split, seed in live.OUTPUT_TASKS.items():
            task_id = _task_id_for(split, seed)
            records = by_task.get((arm, split), [])
            initial = [entry for entry in records if entry.get("attempt") == 1]
            repairs = [entry for entry in records if entry.get("attempt") == 2]
            if (len({entry.get("operation_id") for entry in initial}) != 1
                    or len({entry.get("operation_id")
                            for entry in repairs}) > 1):
                problems.append("dispatch-budget-mismatch %s-%s" % (arm, split))
            accepted_records = [entry for entry in records
                                if entry.get("parse_outcome") == "accepted"]
            if len(accepted_records) > 1:
                problems.append("multiple-accepted-candidates %s-%s" % (
                    arm, split))
            initial_accepted = any(
                entry.get("attempt") == 1
                and entry.get("parse_outcome") == "accepted"
                for entry in records)
            if initial_accepted and repairs:
                problems.append("repair-after-accepted %s-%s" % (
                    arm, split))
            if len(repairs) > 1:
                problems.append("repair-limit-exceeded %s-%s" % (
                    arm, split))
            if repairs and initial:
                initial_outcome = initial[0].get("parse_outcome")
                if initial_outcome not in {
                        "parse-failed", "empty", "too-long"}:
                    label = ("route-refused"
                             if initial_outcome == "route-refused"
                             else str(initial_outcome or "unknown"))
                    problems.append("repair-after-%s %s-%s" % (
                        label, arm, split))
            if not records:
                problems.append("missing-dispatch %s-%s" % (arm, split))
                continue
            for entry in records:
                raw_prompt = entry.get("raw_prompt")
                expected = prompt.get("rendered_digests", {}).get(
                    "%s:%s:%d:a%s" % (arm, split, seed, entry.get("attempt")))
                expected_raw = expected_prompts.get(
                    (arm, split, entry.get("attempt")))
                if (expected != source_digest(
                        raw_prompt if isinstance(raw_prompt, str) else "")
                        or raw_prompt != expected_raw):
                    problems.append("rendered-prompt-mismatch %s-%s" % (
                        arm, split))
            record = accepted_records[0] if accepted_records else None
            if record is None:
                continue
            try:
                payload = live.extract_and_validate_boolean(
                    record.get("raw_response"))
                _task, session = _output_public_task(split, seed)
                committed = session.commit_predictor(payload)
                candidate_digest = source_digest(canonical(payload))
                if record.get("accepted_candidate_digest") != candidate_digest:
                    problems.append("candidate-digest-mismatch %s-%s" % (
                        arm, split))
                if (record.get("source_digest") != candidate_digest
                        or record.get("artifact_digest") != candidate_digest):
                    problems.append("candidate-lineage-mismatch %s" % (
                        record.get("operation_id", "?")))
                raw_prompt = record.get("raw_prompt")
                raw_response = record.get("raw_response")
                prompt_digest = (source_digest(raw_prompt)
                                 if isinstance(raw_prompt, str) else None)
                response_digest = (source_digest(raw_response)
                                   if isinstance(raw_response, str) else None)
                if (record.get("input_digest") != prompt_digest
                        or record.get("prompt_digest") != prompt_digest):
                    problems.append("candidate-input-mismatch %s" % (
                        record.get("operation_id", "?")))
                if (record.get("result_digest") != response_digest
                        or record.get("response_digest") != response_digest):
                    problems.append("candidate-result-mismatch %s" % (
                        record.get("operation_id", "?")))
                score = session.score(committed)
                private_rows.append({
                    "arm": arm, "task_id": task_id, "split": split,
                    "seed": int(seed), "score": score,
                    "queries": len(session.queried),
                    "candidate_digest": candidate_digest})
            except Exception:
                problems.append("accepted-response-recompute-failed %s-%s" % (
                    arm, split))
                continue
    if not isinstance(bundle.get("candidate_view"), dict):
        problems.append("candidate-view-missing")
    expected_accepted = {
        (arm, split) for arm in ("P1", "P2")
        for split in live.OUTPUT_TASKS}
    actual_accepted = {(arm, split) for arm, split, _entry in accepted}
    if (bundle.get("status") == "available"
            and actual_accepted != expected_accepted):
        problems.append("accepted-candidate-task-set-mismatch")
    _verify_scorer_private(scorer_private, freeze, private_rows, problems)
    if bundle.get("status") == "incomplete" and set(problems) == {
            "study-incomplete"}:
        status = "incomplete"
    else:
        status = "pass" if not problems else "fail"
    result = {"status": status,
              "problems": sorted(set(problems)),
              "recomputed": {"dispatches": len(dispatches),
                             "accepted_candidates": len(accepted),
                             "lost-response-disposition": (
                                 lost_response_disposition),
                             "tasks": sorted("%s-%s" % key for key in by_task)}}
    return result


def verify_bundle_file(path) -> dict:
    from pathlib import Path
    path = Path(path)
    bundle = json.loads(path.read_text())
    result = verify_bundle(bundle)
    if bundle.get("schema") != OUTPUT_SCHEMA:
        return result
    result["verification_scope"]["sibling_evidence_checked"] = True
    preflight = path.with_name("preflight.json")
    refusal = path.with_name("preflight-refusal.json")
    if preflight.is_file() and refusal.is_file():
        try:
            preflight_record = json.loads(preflight.read_text())
            refusal_record = json.loads(refusal.read_text())
        except (OSError, ValueError):
            preflight_record = None
            refusal_record = None
        if isinstance(preflight_record, dict) and isinstance(
                refusal_record, dict):
            expected_preflight = {
                "protocol": bundle.get("protocol", {}).get("protocol"),
                "study_root": bundle.get("study_root"),
                "run_id": bundle.get("run_id"),
                "source_identity": bundle.get("source_identity"),
                "freeze_digest": bundle.get("freeze_digest"),
                "route": bundle.get("protocol", {}).get("route"),
                "route_digest": source_digest(canonical(
                    bundle.get("protocol", {}).get("route"))),
            }
            identity = {key: expected_preflight[key] for key in (
                "protocol", "study_root", "run_id", "source_identity",
                "freeze_digest")}
            if (preflight_record == expected_preflight
                    and {key: refusal_record.get(key) for key in identity}
                    == identity):
                problems = result.setdefault("problems", [])
                if "preflight-refusal-contradicts-valid-preflight" not in problems:
                    problems.append(
                        "preflight-refusal-contradicts-valid-preflight")
                result["status"] = "fail"
                result["problems"] = sorted(set(problems))
    return result
