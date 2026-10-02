"""S09-M5 offline verifier for the N5 prospective pilot bundle.

Reads only the bundle directory. Names every missing or inconsistent
piece of evidence with the exact identity a reviewer must chase.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Run as a script, `sys.path[0]` is `scripts/`, so `experiments` and `src` are
# both unimportable and the run that cross-checks a bundle in a subprocess
# silently fell back to a hardcoded construction ceiling and reported
# `code-ceiling-unreadable`. The sibling scripts here already do this.
_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(_ROOT / "src"), str(_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

ACCOUNTING_CATEGORIES = (
    "construction",
    "rejected_actions",
    "policy_execution",
    "model_requests",
    "use",
    "repair",
)

# The only per-request transport field a bundle persists. A request
# addressed to a model other than the frozen one did not travel the
# declared transport, and no receipt makes the two agree.
REQUEST_IDENTITY_FIELDS = ("model",)

# What the freeze asserts about the transport, checked for self
# consistency only: the bundle persists no per-request adapter or
# endpoint, so these cannot be compared against anything.
GATEWAY_IDENTITY_FIELDS = ("model", "adapter", "api", "endpoint_digest")

# A dispatch label, not source bytes, so a record naming it is not
# claiming a digest of executable code.
INCUMBENT_SOURCE = "incumbent"


def empty_accounting() -> dict:
    return {key: {"measured": "unknown", "source": "unmeasured"}
            for key in ACCOUNTING_CATEGORIES}


def canonical(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


NON_IDENTITY_FREEZE_FIELDS = ("freeze_digest", "frozen_at")


def freeze_digest(freeze: dict) -> str:
    """Digest over what identifies the freeze, not when it was taken.

    ``frozen_at`` is excluded deliberately. A wall-clock field inside the
    identity would make the digest differ on every call for an otherwise
    identical freeze, and a freeze that cannot be reproduced is not a freeze.
    The timestamp still rides in the bundle so a receipt predating it is
    detectable; it just does not name the study.
    """
    body = {key: value for key, value in freeze.items()
            if key not in NON_IDENTITY_FREEZE_FIELDS}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def _is_count(value) -> bool:
    return type(value) is int and value >= 0


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Severity(str, Enum):
    """How a finding bears on the verdict.

    UNPROVEN is not a pass and not a failure. The evidence needed to
    decide is absent from the bundle, so the bundle cannot support the
    claim either way. It is surfaced so a reviewer sees the gap, and it
    is not counted against the bundle.
    """

    REFUSAL = "refusal"
    UNPROVEN = "unproven"

    def __str__(self) -> str:
        return self.value


class Finding(str, Enum):
    """Stable machine-readable reasons a bundle is refused or left open.

    The wire form is the enum value, so a caller that predates a member
    still parses. Members are append-only; names never change meaning.
    """

    REQUEST_MODEL_NOT_FROZEN = "request-model-not-frozen"
    REQUEST_MODEL_MISSING = "request-model-missing"
    GATEWAY_IDENTITY_MISSING = "gateway-identity-missing"
    GATEWAY_CONFIG_MISSING = "gateway-config-missing"
    EXECUTED_SOURCE_UNATTRIBUTED = "executed-source-unattributed"
    EXECUTED_SOURCE_MISMATCH = "executed-source-mismatch"
    BOUND_POLICY_SOURCE_MISSING = "bound-policy-source-missing"
    BOUND_POLICY_DIGEST_MISMATCH = "bound-policy-digest-mismatch"
    EXECUTED_POLICY_NOT_BOUND = "executed-policy-not-bound"
    ACQUIRED_MEMBER_IS_AUTHORED = "acquired-member-is-authored"
    POLICY_EXECUTION_UNPROVEN = "policy-execution-unproven"

    def __str__(self) -> str:
        return self.value

    def severity(self) -> Severity:
        if self in (Finding.POLICY_EXECUTION_UNPROVEN,
                    Finding.ACQUIRED_MEMBER_IS_AUTHORED):
            return Severity.UNPROVEN
        return Severity.REFUSAL


@dataclass(frozen=True)
class Problem:
    """One refusal or one open question, with a branchable reason."""

    reason: Finding
    subject: str
    detail: str = ""

    def wire(self) -> str:
        """The legacy ``"<reason> <subject> <detail>"`` problem string."""
        return " ".join(part for part in
                        (str(self.reason), self.subject, self.detail)
                        if part).strip()


class Refusals:
    """Accumulator for refusals and for what the bundle cannot prove."""

    def __init__(self) -> None:
        self.typed: list = []

    def add(self, reason: Finding, subject: str, detail: str = "") -> Problem:
        problem = Problem(reason, subject, detail)
        self.typed.append(problem)
        return problem

    def refusals(self) -> list:
        return [problem for problem in self.typed
                if problem.reason.severity() is Severity.REFUSAL]

    def unproven(self) -> list:
        return [problem for problem in self.typed
                if problem.reason.severity() is Severity.UNPROVEN]

    def strings(self) -> list:
        return sorted({problem.wire() for problem in self.refusals()})


def _repertoire_digests(freeze: dict, arm) -> set:
    """Method digests the freeze froze for ``arm``."""
    repertoires = freeze.get("method_repertoires")
    if not isinstance(repertoires, dict):
        return set()
    repertoire = repertoires.get(arm)
    if not isinstance(repertoire, dict):
        return set()
    return {member.get("source_digest")
            for member in repertoire.get("members") or []
            if isinstance(member, dict) and isinstance(
                member.get("source_digest"), str)}


def _authored_digests(freeze: dict) -> set:
    """Digests of every source the bundle itself declares authored.

    An arm whose artifact origin names authorship is a constant the
    study wrote rather than a method it acquired.
    """
    digests = set()
    identities = freeze.get("policy_identities")
    for identity in (identities or {}).values():
        if not isinstance(identity, dict):
            continue
        source = identity.get("source")
        artifact = identity.get("artifact")
        origin = artifact.get("origin") if isinstance(artifact, dict) else None
        if isinstance(source, str) and source and origin and \
                "authored" in str(origin):
            digests.add(_sha256_text(source))
    return digests


def _authored_policy_digests(freeze: dict) -> set:
    """Digests of policies the freeze declares to be authored controls."""
    digests = set()
    identities = freeze.get("policy_identities")
    for identity in (identities or {}).values():
        if not isinstance(identity, dict):
            continue
        artifact = identity.get("artifact")
        origin = artifact.get("origin") if isinstance(artifact, dict) else None
        digest = identity.get("source_digest")
        if isinstance(digest, str) and origin and "authored" in str(origin):
            digests.add(digest)
    return digests


def _lineage_episodes(bundle: dict) -> dict:
    """Episodes keyed by campaign id, the builder side of a member."""
    episodes = {}
    for episode in list(bundle.get("development") or []) + list(
            bundle.get("assessment") or []):
        if isinstance(episode, dict) and isinstance(
                episode.get("campaign_id"), str):
            episodes[episode["campaign_id"]] = episode
    return episodes


def _episode_policy(episode) -> str:
    if not isinstance(episode, dict):
        return ""
    for field in ("executed_policy_digest", "policy_digest"):
        value = episode.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def _check_acquired_members(bundle: dict, freeze: dict,
                            refusals: Refusals) -> None:
    """A member labelled acquired must not be an authored constant.

    The label is the claim under test. A member carrying
    ``authored: false`` is asserting the study acquired those bytes from
    a model. Two things falsify that: the bytes are one the freeze itself
    declares authored, or the campaign that built the member ran a policy
    the freeze declares an authored control. Either way the member is a
    constant the study wrote, and a use record citing it as acquired is
    citing the study's own handiwork.
    """
    repertoires = freeze.get("method_repertoires")
    if not isinstance(repertoires, dict):
        return
    authored = _authored_digests(freeze)
    authored_policies = _authored_policy_digests(freeze)
    episodes = _lineage_episodes(bundle)
    for arm in sorted(repertoires):
        repertoire = repertoires.get(arm)
        if not isinstance(repertoire, dict):
            continue
        for index, member in enumerate(repertoire.get("members") or []):
            if not isinstance(member, dict) or member.get("authored"):
                continue
            subject = "%s#%d" % (arm, index)
            digest = member.get("source_digest")
            source = member.get("method_source")
            if isinstance(source, str) and source:
                recomputed = _sha256_text(source)
                if digest != recomputed:
                    refusals.add(Finding.EXECUTED_SOURCE_MISMATCH, subject,
                                 "recorded=%r recomputed=%s" % (digest,
                                                                recomputed))
                    continue
            if isinstance(digest, str) and digest in authored:
                refusals.add(Finding.ACQUIRED_MEMBER_IS_AUTHORED, subject,
                             "declared-authored")
                continue
            construction = member.get("construction")
            campaign = construction.get("campaign_id") if isinstance(
                construction, dict) else None
            builder = _episode_policy(episodes.get(campaign)) if isinstance(
                campaign, str) else ""
            if builder and builder in authored_policies:
                refusals.add(Finding.ACQUIRED_MEMBER_IS_AUTHORED, subject,
                             "built-by-authored-control")


def _frozen_gateway_identity(freeze: dict, refusals: Refusals) -> dict:
    """The transport the freeze declares, keyed by the fields it pins."""
    config = freeze.get("config")
    if not isinstance(config, dict):
        refusals.add(Finding.GATEWAY_CONFIG_MISSING, "config")
        return {}
    identity = {}
    for field in GATEWAY_IDENTITY_FIELDS:
        if field not in config:
            refusals.add(Finding.GATEWAY_IDENTITY_MISSING, "config", field)
            continue
        identity[field] = config[field]
    return identity


def _check_request_provenance(bundle: dict, freeze: dict,
                              refusals: Refusals) -> None:
    """Every persisted model request must name the frozen model.

    A bundle is only a record of a live run if the requests it persists
    were addressed to the model the freeze declared. A request addressed
    elsewhere is a doubled run wearing a live freeze, and no receipt can
    make the two agree.
    """
    identity = _frozen_gateway_identity(freeze, refusals)
    model = identity.get("model")
    construction = bundle.get("construction")
    if not isinstance(construction, dict):
        return
    for arm, entry in sorted(construction.items()):
        if not isinstance(entry, dict):
            continue
        for index, request in enumerate(entry.get(
                "construction_requests") or []):
            subject = "%s#%d" % (arm, index)
            if not isinstance(request, dict):
                refusals.add(Finding.REQUEST_MODEL_MISSING, subject)
                continue
            for field in REQUEST_IDENTITY_FIELDS:
                if field not in request:
                    refusals.add(Finding.REQUEST_MODEL_MISSING, subject,
                                 field)
                    continue
                if model is not None and request.get(field) != model:
                    refusals.add(
                        Finding.REQUEST_MODEL_NOT_FROZEN, subject,
                        "%s=%r" % (field, request.get(field)))


def _check_digest_provenance(bundle: dict, freeze: dict,
                             refusals: Refusals) -> None:
    """Re-derive digests and require every executed source to be claimed.

    Two claims are checked because each fails on its own: a recorded
    digest that does not match the bytes beside it, and an executed
    source no frozen arm offers.

    What is deliberately *not* checked is whether the executed method
    equals the arm's bound policy. It cannot: a bound policy selects a
    method rather than being one, so ``executed_source_digest`` is a
    method digest by construction. Requiring the two to match would
    refuse every well-formed bundle, including one built by the same
    pilot. Whether the bound policy actually governed the use is a
    separate question, handled by ``_check_policy_execution``.
    """
    construction = bundle.get("construction")
    bound = {}
    for arm, entry in sorted((construction or {}).items()
                             if isinstance(construction, dict) else ()):
        if not isinstance(entry, dict) or entry.get("status") != "available":
            continue
        source = entry.get("policy_source")
        subject = str(arm)
        if not isinstance(source, str) or not source:
            refusals.add(Finding.BOUND_POLICY_SOURCE_MISSING, subject)
            continue
        recomputed = _sha256_text(source)
        if entry.get("source_digest") != recomputed:
            refusals.add(
                Finding.BOUND_POLICY_DIGEST_MISMATCH, subject,
                "recorded=%r recomputed=%s" % (entry.get("source_digest"),
                                               recomputed))
        bound[arm] = recomputed

    repertoires = freeze.get("method_repertoires")
    repertoires = repertoires if isinstance(repertoires, dict) else {}
    incumbent = _sha256_text(INCUMBENT_SOURCE)

    use_records = bundle.get("use_records")
    for record in use_records if isinstance(use_records, list) else []:
        if not isinstance(record, dict):
            continue
        subject = str(record.get("record_id", "?"))
        arm = record.get("study_arm")
        source = record.get("executed_source")
        if isinstance(source, str) and source and source != INCUMBENT_SOURCE:
            recomputed = _sha256_text(source)
            recorded = record.get("executed_source_digest")
            if recorded != recomputed:
                refusals.add(Finding.EXECUTED_SOURCE_MISMATCH, subject,
                             "recorded=%r recomputed=%s" % (
                                 recorded, recomputed))
        if not isinstance(arm, str) or arm not in repertoires:
            continue
        if record.get("executed") in ("incumbent", "refused"):
            continue
        executed = record.get("executed_source_digest")
        if not isinstance(executed, str) or not executed:
            continue
        if executed in _repertoire_digests(freeze, arm) or \
                executed in bound.get(arm, set()) or executed == incumbent:
            continue
        refusals.add(Finding.EXECUTED_SOURCE_UNATTRIBUTED, subject,
                     "arm=%s" % arm)


def _check_policy_execution(bundle: dict, freeze: dict,
                            refusals: Refusals) -> None:
    """A claimed executed policy must be corroborated, or left open.

    A use record's ``executed_policy_digest`` is written as
    ``executed or expected``: when the store yields exactly one policy
    digest it is reported, and when the store yields nothing the bound
    digest is copied into its place. The scalar cannot distinguish a
    policy that ran from a bound policy that was merely available, so a
    record carrying it is not evidence that the policy governed the use.

    The disambiguator is the persisted list of digests actually read
    back. A populated list that contains the scalar corroborates the
    claim; a list that does not contain it contradicts it. Where no list
    is persisted the bundle carries no evidence either way, which is
    unproven rather than a failure, and is surfaced so the gap is
    visible instead of silent.
    """
    use_records = bundle.get("use_records")
    for record in use_records if isinstance(use_records, list) else []:
        if not isinstance(record, dict):
            continue
        claimed = record.get("executed_policy_digest")
        if not isinstance(claimed, str) or not claimed:
            continue
        observed = record.get("executed_policy_digests")
        if isinstance(observed, list) and observed:
            if claimed not in observed:
                refusals.add(Finding.EXECUTED_POLICY_NOT_BOUND,
                             str(record.get("record_id", "?")),
                             "not-in-observed-list")
            continue
        refusals.add(Finding.POLICY_EXECUTION_UNPROVEN,
                     str(record.get("record_id", "?")),
                     "no-observed-list")


def verify_bundle(bundle: dict) -> dict:
    problems: list = []
    refusals = Refusals()
    if not isinstance(bundle, dict):
        return {"status": "incomplete", "problems": ["empty-bundle"],
                "findings": [], "recomputed": {}}
    freeze = bundle.get("freeze")
    if not isinstance(freeze, dict):
        return {"status": "incomplete", "problems": ["missing-freeze"],
                "findings": [], "recomputed": {}}
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
        # A record that ran nothing is exempt: it has no executed bytes to
        # attribute. `incumbent` is the old fallback label and `refused` is
        # what replaced it, so both mean the same thing to this check.
        ran_nothing = record.get("executed") in ("incumbent", "refused")
        if not ran_nothing and not record.get("policy_digest"):
            problems.append("executed-record-missing-policy-digest %s" % (
                record.get("record_id", "?")))
        if not ran_nothing:
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

    _check_request_provenance(bundle, freeze, refusals)
    _check_digest_provenance(bundle, freeze, refusals)
    _check_acquired_members(bundle, freeze, refusals)
    _check_policy_execution(bundle, freeze, refusals)
    problems.extend(problem.wire() for problem in refusals.refusals())

    recomputed = {"model_calls": total_model,
                  "construction_calls": total_construction,
                  "witness_acquisition": total_witness,
                  "witness_use": use_queries,
                  "use_records": len(use_records),
                  "worst_case": worst,
                  "claimed_operations": len(claimed_ops)}
    status = "pass" if not problems else "fail"
    return {"status": status, "problems": sorted(set(problems)),
            "findings": [_wire(problem) for problem in sorted(
                refusals.typed,
                key=lambda p: (str(p.reason), p.subject, p.detail))],
            "recomputed": recomputed}


def _wire(problem: Problem) -> dict:
    return {"reason": str(problem.reason),
            "severity": str(problem.reason.severity()),
            "subject": problem.subject,
            "detail": problem.detail}


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
