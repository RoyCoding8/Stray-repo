"""Reissue Stage 9 M5's five verdicts from a run's bytes and receipts.

M5 requires five verdicts reported separately, plus a keep/simplify/replace
decision. They were issued against prose, which is why a contaminated run
could issue a confident `true` for live acquisition: the run's own
construction requests record the model as `recorded-double` while the freeze
declares a pinned live model, and its use records persist the repertoire
method as the executed source while the scored difference between arms is
attributed to a policy wrapper that never hashed to those bytes.

Nothing is a literal: every value falls out of a comparison over the
bundle's bytes or over a representation suite's recorded result.

The vocabulary separates three states a verdict must not conflate.

`false`     the evidence shows the thing did not happen.
`unproven`  the evidence cannot show it either way.
`ineligible` the case does not apply, and M4 says why.

A run that fails a provenance leg is `unproven`, never `false` and never
`true`. Contamination is not a negative result; it is the absence of a
result, and reading it as either a capability failure or a capability
success is the error this module exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, ClassVar, Mapping, Sequence

MECHANISM = "mechanism"
LIVE_ACQUISITION = "live_acquisition"
TASK_UTILITY = "task_utility"
TRANSFER = "transfer"
RECURSIVE_IMPROVEMENT = "recursive_improvement"

TRUE = "true"
FALSE = "false"
UNPROVEN = "unproven"
INELIGIBLE = "ineligible"
UNKNOWN = "UNKNOWN"

WIN = "win"
LOSS = "loss"
TIE = "tie"
NOT_COMPARABLE = "not_comparable"

KEEP = "keep"
SIMPLIFY = "simplify"
REPLACE = "replace"
PRIOR_STATE = "prior-state"

BASIS_BUNDLE = "bundle-and-receipts"
BASIS_TESTS = "test-results"
BASIS_NONE = "nothing"

LEG_PASS = "pass"
LEG_FAIL = "fail"
LEG_UNKNOWN = "unknown"

REQUIRED = "required"
OPTIONAL = "optional"

ORIGIN_ACQUIRED = "model-acquired"
ORIGIN_AUTHORED = "authored-control"
ORIGIN_STAND_IN = "fixture-stand-in"

DOMAIN_GRAPH = "graph"


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Basis:
    """What a verdict was computed from."""

    source: str
    detail: str

    def __post_init__(self) -> None:
        if self.source not in (BASIS_BUNDLE, BASIS_TESTS, BASIS_NONE):
            raise ValueError("unknown basis source %r" % self.source)
        if not self.detail:
            raise ValueError("a verdict names what it was computed from")


@dataclass(frozen=True)
class Leg:
    """One check, its per-leg status, and the evidence it read."""

    name: str
    role: str
    status: str
    evidence: str

    def __post_init__(self) -> None:
        if self.role not in (REQUIRED, OPTIONAL):
            raise ValueError("unknown leg role %r" % self.role)
        if self.status not in (LEG_PASS, LEG_FAIL, LEG_UNKNOWN):
            raise ValueError("unknown leg status %r" % self.status)
        if not self.evidence:
            raise ValueError("a leg carries the evidence it read")

    @property
    def is_binding(self) -> bool:
        return self.role == REQUIRED


@dataclass(frozen=True)
class _Verdict:
    name: ClassVar = ""
    value: str
    legs: tuple
    basis: Basis

    def __post_init__(self) -> None:
        if self.basis.source == BASIS_NONE:
            raise ValueError(
                "a verdict with basis %r is unissuable" % BASIS_NONE)
        if not self.legs:
            raise ValueError("a verdict carries evidence legs")
        if not any(leg.evidence for leg in self.legs):
            raise ValueError("a verdict with no evidence reads %s" % UNKNOWN)

    @property
    def failing_legs(self) -> tuple:
        return tuple(leg.name for leg in self.legs
                     if leg.status == LEG_FAIL and leg.is_binding)

    @property
    def all_binding_legs_pass(self) -> bool:
        return all(leg.status == LEG_PASS for leg in self.legs
                   if leg.is_binding)

    def leg(self, name: str) -> Leg:
        for leg in self.legs:
            if leg.name == name:
                return leg
        raise KeyError("no leg named %r on %s" % (name, self.value))

    def summary(self) -> str:
        return "%s=%s basis=%s legs=%s" % (
            self.name, self.value, self.basis.source,
            "; ".join("%s:%s" % (leg.name, leg.status) for leg in self.legs))


# ---------------------------------------------------------------------------
# the five typed verdicts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mechanism(_Verdict):
    name: ClassVar = MECHANISM
    values: ClassVar = (TRUE, FALSE, UNPROVEN)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.value not in self.values:
            raise ValueError("mechanism cannot read %r" % self.value)


@dataclass(frozen=True)
class LiveAcquisition(_Verdict):
    """Did the frozen live model actually produce the bound policy?

    A leg that fails makes the verdict `unproven` and forbids `false`,
    because a contaminated run is not a negative acquisition result.
    """

    name: ClassVar = LIVE_ACQUISITION
    values: ClassVar = (TRUE, FALSE, UNPROVEN)
    required_legs: ClassVar = (
        "declared_model_matches_freeze",
        "bound_equals_candidate",
        "executed_bytes_are_the_bound_policy",
        "dispatch_was_live_not_a_recording",
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.value not in self.values:
            raise ValueError("live_acquisition cannot read %r" % self.value)
        if self.value == TRUE and not self.all_binding_legs_pass:
            raise ValueError(
                "live_acquisition cannot read true while %s fail"
                % (self.failing_legs,))
        if self.value == FALSE and self.failing_legs:
            raise ValueError(
                "a failed provenance leg makes acquisition %s, not %s"
                % (UNPROVEN, FALSE))


@dataclass(frozen=True)
class TaskUtility(_Verdict):
    name: ClassVar = TASK_UTILITY
    values: ClassVar = (WIN, LOSS, TIE, NOT_COMPARABLE, UNPROVEN)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.value not in self.values:
            raise ValueError("task_utility cannot read %r" % self.value)


@dataclass(frozen=True)
class Transfer(_Verdict):
    name: ClassVar = TRANSFER
    values: ClassVar = (TRUE, FALSE, UNPROVEN)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.value not in self.values:
            raise ValueError("transfer cannot read %r" % self.value)


@dataclass(frozen=True)
class RecursiveImprovement(_Verdict):
    name: ClassVar = RECURSIVE_IMPROVEMENT
    values: ClassVar = (TRUE, FALSE, UNPROVEN, INELIGIBLE)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.value not in self.values:
            raise ValueError(
                "recursive_improvement cannot read %r" % self.value)


PROVENANCE_GATE = (
    "A change decision requires the acquisition gate: every required "
    "provenance leg passed and live_acquisition read %s. While the gate is "
    "unsatisfied the acquisition verdict reads %s, no acquisition or utility "
    "claim may be carried forward, and the prior state stands. When the gate "
    "is satisfied, a verified mechanism reads %s, a mechanism that did not "
    "verify reads %s, and a mechanism that verified with a utility or "
    "transfer verdict that is not positive reads %s."
) % (TRUE, UNPROVEN, KEEP, REPLACE, SIMPLIFY)

DECISION_RULE = PROVENANCE_GATE


@dataclass(frozen=True)
class VerdictSet:
    """All five, or none of them."""

    mechanism: Mechanism
    acquisition: LiveAcquisition
    utility: TaskUtility
    transfer: Transfer
    recursive_improvement: RecursiveImprovement

    def as_dict(self) -> dict:
        return {verdict.name: verdict
                for verdict in (self.mechanism, self.acquisition,
                                self.utility, self.transfer,
                                self.recursive_improvement)}


@dataclass(frozen=True)
class Decision:
    outcome: str
    verdicts: VerdictSet
    rationale: tuple
    rule: str = PROVENANCE_GATE

    def __post_init__(self) -> None:
        if self.outcome not in (KEEP, SIMPLIFY, REPLACE, PRIOR_STATE):
            raise ValueError("unknown decision outcome %r" % self.outcome)
        if (self.outcome != PRIOR_STATE
                and self.verdicts.acquisition.value == UNPROVEN):
            raise ValueError(
                "the acquisition provenance gate is unsatisfied, so the "
                "decision cannot change from %r to %r"
                % (self.verdicts.acquisition.value, self.outcome))
        if not self.rationale:
            raise ValueError("a decision carries its rationale")


# ---------------------------------------------------------------------------
# the bundle
# ---------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Bundle:
    root: Path
    freeze: Mapping[str, Any]
    construction: Mapping[str, Any]
    operations: Mapping[str, Any]
    use_records: tuple
    accounting: Mapping[str, Any]
    assessment: tuple

    def basis(self, detail: str) -> Basis:
        return Basis(source=BASIS_BUNDLE, detail=detail)

    def declared_model(self) -> str:
        return str((self.freeze.get("config") or {}).get("model") or "")

    def identities(self) -> dict:
        return dict(self.freeze.get("policy_identities") or {})

    def arm_origin(self, arm: str) -> str:
        """The origin the freeze claims for this arm, unexamined.

        This is the label, and a label is a claim. `earned_origin` is the
        claim checked; every consumer that gates on an origin wants the
        latter, and the difference between the two is the whole defect.
        """
        artifact = (self.identities().get(arm) or {}).get("artifact") or {}
        return str(artifact.get("origin") or "")

    def arm_policy_digest(self, arm: str) -> str:
        return str((self.identities().get(arm) or {}).get("source_digest") or "")

    def arm_scope(self, arm: str) -> dict:
        artifact = (self.identities().get(arm) or {}).get("artifact") or {}
        return dict(artifact.get("applicability") or {})

    def arms_by_origin(self, origin: str) -> tuple:
        return tuple(sorted(arm for arm in self.identities()
                            if self.arm_origin(arm) == origin))

    def earned_origin(self, arm: str) -> str:
        """The origin this arm's own record supports, not the one it claims.

        An arm that claims `model-acquired` has to point at the operation
        that produced its bytes, and that operation's receipt has to say a
        live provider answered. The freeze writes the label, so reading the
        freeze is reading the claim back to itself. This reads the
        construction record and the evidence carried beside it, and where
        there is none the arm is a stand-in, because a bundle that cannot
        show a provider is not evidence of one.

        An arm claiming anything else keeps its claim. `authored-control` is
        a statement about the study, and the study is entitled to make it
        about bytes it wrote itself.
        """
        if self.arm_origin(arm) != ORIGIN_ACQUIRED:
            return self.arm_origin(arm)
        evidence = self.construction_of(arm).get("acquisition_evidence")
        if isinstance(evidence, Mapping) and evidence.get("earned") is True:
            return ORIGIN_ACQUIRED
        return ORIGIN_STAND_IN

    def earned_arms_by_origin(self, origin: str) -> tuple:
        return tuple(sorted(arm for arm in self.identities()
                            if self.earned_origin(arm) == origin))

    def construction_of(self, arm: str) -> dict:
        return dict(self.construction.get(arm) or {})

    def records_for(self, arm: str) -> tuple:
        return tuple(record for record in self.use_records
                     if str(record.get("study_arm") or
                            record.get("arm")) == arm)

    def receipts_for(self, operation_id: str) -> tuple:
        entry = self.operations.get(operation_id) or {}
        return tuple(entry.get("receipts") or ())


def load_bundle(path: os.PathLike | str) -> Bundle:
    root = Path(path)

    def read(name: str) -> Any:
        return json.loads((root / (name + ".json")).read_text())

    return Bundle(
        root=root,
        freeze=read("freeze"),
        construction=read("construction"),
        operations=read("operations"),
        use_records=tuple(read("use_records")),
        accounting=read("accounting"),
        assessment=tuple(read("assessment")),
    )


# ---------------------------------------------------------------------------
# mechanism: representation inventory and recorded suite results
# ---------------------------------------------------------------------------

REPRESENTATION_BINDING = {
    "step": ("experiments/ad01/policy_step.py",
             "tests/test_boolean_policy_bridge.py"),
    "policy_ast": ("experiments/ad01/boolean_ast_policy.py",
                   "tests/test_boolean_ast_arm.py"),
    "action_graph": ("experiments/ad01/boolean_graph_policy.py",
                     "tests/test_boolean_graph_arm.py"),
}

_PYTEST_COUNT = re.compile(r"(\d+) (passed|failed|error)")

#: How long a nested representation suite may take, and the status it reports if
#: it does not finish inside that. The bound is the project's own convention from
#: `docs/LONG-RUNNING-TESTS.md`: a timeout is not a pass, and the value is a
#: child's, not the parent's. `scripts/run_bounded.py --timeout` uses the same
#: reading, where reaching the bound is reported as `timeout` rather than as the
#: child's own status.
#:
#: 280 seconds is the slowest currently-collected file in that document plus
#: margin. The nested suites here are three small files; an hour was the
#: previous effective bound and it was the job's, not this call's.
NESTED_SUITE_TIMEOUT_S = 280
NESTED_SUITE_TIMEOUT_RC = 124  # the project's "our bound was reached" value.


@dataclass(frozen=True)
class SuiteResult:
    test_file: str
    passed: int
    failed: int
    errored: int
    returncode: int

    @property
    def green(self) -> bool:
        return (self.returncode == 0 and self.failed == 0
                and self.errored == 0 and self.passed > 0)


def run_representation_suite(root: os.PathLike | str,
                             test_file: str) -> SuiteResult:
    root = Path(root)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root), str(root / "src"),
         env["PYTHONPATH"] if env.get("PYTHONPATH") else ""])
    # The child reads the repository's own tests, so it needs no database of
    # its own, and it must not claim one. The run token is inherited above
    # because `dict(os.environ)` copies everything, and the nested run then
    # contends with this process for the same per-token advisory lock: the
    # parent holds it for the whole suite, so the child waits forever. Measured
    # in runs 37261826154 and 37277929945, where the four shards that stall are
    # exactly the four that reach this call, and the cancel is followed 24ms
    # later by a `CREATE DATABASE` for this job's own token returning "already
    # exists". `S09ISO_DISABLE` returns from `pytest_configure` before the
    # claim, which is the whole of what a suite that reads test files needs.
    env["S09ISO_DISABLE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", test_file,
             "-q", "--tb=no", "-p", "no:cacheprovider"],
            cwd=str(root), env=env, capture_output=True, text=True,
            timeout=NESTED_SUITE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        # A nested run with no bound is invisible: pytest says nothing about a
        # test that never returns, so the parent waits until the job's own
        # `timeout-minutes` kills it and the whole run reads as `failure`.
        # That is not hypothetical. Nine of the last 25 runs hit exactly the
        # 100-minute limit on the job owning this file, and every one of the
        # nine is recorded as a failure rather than a hang.
        #
        # Returning a result rather than raising keeps the caller's shape: the
        # verdict is computed from the counts, and a suite that did not finish
        # reports zero of each, which `mechanism_verdict` already treats as a
        # leg that cannot pass. A timeout is therefore a verdict input here and
        # not a crash.
        return SuiteResult(test_file=test_file, passed=0, failed=0, errored=0,
                           returncode=NESTED_SUITE_TIMEOUT_RC)
    counts = {"passed": 0, "failed": 0, "error": 0}
    for digits, word in _PYTEST_COUNT.findall(completed.stdout):
        counts[word] = int(digits)
    return SuiteResult(test_file=test_file, passed=counts["passed"],
                       failed=counts["failed"], errored=counts["error"],
                       returncode=completed.returncode)


def mechanism_verdict(root: os.PathLike | str,
                      suites: Mapping[str, SuiteResult] | None = None,
                      ) -> Mechanism:
    """Do the three representations work at their reported scope?

    A bundle is never consulted, so a live run cannot move this verdict in
    either direction.
    """
    root = Path(root)
    legs = []
    for representation in sorted(REPRESENTATION_BINDING):
        module_rel, test_rel = REPRESENTATION_BINDING[representation]
        module = root / module_rel
        result = (suites or {}).get(representation)
        if module.is_file():
            body = module.read_text()
            legs.append(Leg(
                name="implementation_present:%s" % representation,
                role=REQUIRED, status=LEG_PASS,
                evidence="%s sha256=%s lines=%d"
                         % (module_rel, sha256_text(body),
                            len(body.splitlines()))))
        else:
            legs.append(Leg(
                name="implementation_present:%s" % representation,
                role=REQUIRED, status=LEG_FAIL,
                evidence="no module at %s" % module_rel))
        if result is None:
            legs.append(Leg(
                name="suite_passing:%s" % representation,
                role=REQUIRED, status=LEG_UNKNOWN,
                evidence="no recorded result for %s" % test_rel))
        elif result.green:
            legs.append(Leg(
                name="suite_passing:%s" % representation,
                role=REQUIRED, status=LEG_PASS,
                evidence="%s passed %d, failed 0, exit %d"
                         % (test_rel, result.passed, result.returncode)))
        else:
            legs.append(Leg(
                name="suite_passing:%s" % representation,
                role=REQUIRED, status=LEG_FAIL,
                evidence="%s passed %d, failed %d, errored %d, exit %d"
                         % (test_rel, result.passed, result.failed,
                            result.errored, result.returncode)))
    verdict = Mechanism(
        value=TRUE,
        legs=tuple(legs),
        basis=Basis(
            source=BASIS_TESTS,
            detail="representation modules and their own suite results under "
                   "%s; a live bundle is not consulted" % root))
    if all(leg.status == LEG_PASS for leg in legs):
        return verdict
    return Mechanism(value=UNPROVEN, legs=verdict.legs, basis=verdict.basis)


# ---------------------------------------------------------------------------
# live acquisition
# ---------------------------------------------------------------------------


def _model_leg(bundle: Bundle, acquired: Sequence[str]) -> Leg:
    """The model the request names, against the model the route pinned.

    `freeze.config.model` is what the run intended. A request that persisted
    a different name says the run did not ask that route, so the run's own
    declaration of what it asked is what this leg compares. Reading the
    freeze alone would make the leg unfalsifiable: the freeze cannot
    disagree with itself.
    """
    declared = str((bundle.accounting.get("dispatch_guard") or {}).get(
        "pinned_model") or "") or bundle.declared_model()
    requested = str(bundle.freeze.get("config", {}).get("model") or declared)
    requests = []
    for arm in acquired:
        entry = bundle.construction_of(arm)
        for request in entry.get("construction_requests") or ():
            requests.append((arm, str(request.get("operation_id") or ""),
                             str(request.get("model") or "")))
    if not requests:
        return Leg(
            name="declared_model_matches_freeze", role=REQUIRED,
            status=LEG_FAIL,
            evidence="no construction request for an arm claiming origin %r"
                     % ORIGIN_ACQUIRED)
    mismatched = [item for item in requests if item[2] != requested]
    if mismatched:
        sample = mismatched[0]
        return Leg(
            name="declared_model_matches_freeze", role=REQUIRED,
            status=LEG_FAIL,
            evidence="the run pinned model %r; %d of %d construction requests "
                     "persisted %r, first on %s (%s)"
                     % (requested, len(mismatched), len(requests),
                        sample[2], sample[0], sample[1]))
    return Leg(
        name="declared_model_matches_freeze", role=REQUIRED, status=LEG_PASS,
        evidence="all %d construction requests persisted the pinned model %r"
                 % (len(requests), requested))


def _bound_leg(bundle: Bundle, acquired: Sequence[str]) -> Leg:
    parts = []
    agreed = []
    for arm in acquired:
        entry = bundle.construction_of(arm)
        candidate = str(entry.get("candidate_digest") or "")
        bound = str(entry.get("bound_digest") or "")
        source = str(entry.get("policy_source") or "")
        parts.append("%s candidate=%s bound=%s source_digest=%s"
                     % (arm, candidate[:12] or "(none)", bound[:12] or "(none)",
                        str(entry.get("source_digest") or "(none)")[:12]))
        agreed.append(bool(bound) and candidate == bound
                      and sha256_text(source) == bound)
    if all(agreed):
        return Leg(name="bound_equals_candidate", role=REQUIRED,
                   status=LEG_PASS, evidence="; ".join(parts))
    return Leg(name="bound_equals_candidate", role=REQUIRED, status=LEG_FAIL,
               evidence="candidate, bound and source digests disagree: %s"
                        % "; ".join(parts))


def _executed_leg(bundle: Bundle, acquired: Sequence[str]) -> Leg:
    parts = []
    hold = True
    checked = [0]
    for arm in acquired:
        bound = str(bundle.construction_of(arm).get("bound_digest") or "")
        seen = set()
        for record in bundle.records_for(arm):
            source = record.get("executed_source")
            if source in (None, "", "incumbent"):
                continue
            computed = sha256_text(str(source))
            matches = computed == bound
            hold = hold and matches
            checked[0] += 1
            key = (computed, matches)
            if key in seen:
                continue
            seen.add(key)
            parts.append("%s on %s hashes to %s, bound policy is %s"
                         % (arm, record.get("task_id"), computed[:12],
                            bound[:12] or "(none)"))
    if not parts:
        return Leg(name="executed_bytes_are_the_bound_policy", role=REQUIRED,
                   status=LEG_FAIL,
                   evidence="no executed source bytes recorded for an arm "
                            "claiming origin %r" % ORIGIN_ACQUIRED)
    status = LEG_PASS if hold else LEG_FAIL
    return Leg(name="executed_bytes_are_the_bound_policy", role=REQUIRED,
               status=status, evidence="over %d executed records: %s"
                                        % (checked[0], "; ".join(parts)))


def _dispatch_leg(bundle: Bundle, acquired: Sequence[str]) -> Leg:
    parts = []
    recorded = False
    missing = []
    for arm in acquired:
        entry = bundle.construction_of(arm)
        for request in entry.get("construction_requests") or ():
            operation_id = str(request.get("operation_id") or "")
            receipts = bundle.receipts_for(operation_id)
            if not receipts:
                missing.append(operation_id)
                continue
            outcomes = [str(receipt.get("outcome") or "") for receipt
                        in receipts]
            identities = [str(receipt.get("receipt_identity") or "")
                          for receipt in receipts]
            model = str(request.get("model") or "")
            if model == "recorded-double":
                recorded = True
            parts.append("%s outcome=%s identity=%s persisted model=%r"
                         % (operation_id, ",".join(outcomes),
                            ",".join(identities), model))
    if not parts:
        return Leg(name="dispatch_was_live_not_a_recording", role=REQUIRED,
                   status=LEG_FAIL,
                   evidence="no construction receipt for %s"
                            % (", ".join(missing) or "any construction call"))
    if missing:
        return Leg(name="dispatch_was_live_not_a_recording", role=REQUIRED,
                   status=LEG_FAIL,
                   evidence="no receipt for %s; %s"
                            % (", ".join(missing), "; ".join(parts)))
    seen = {}
    for operation_id, entry in bundle.operations.items():
        for receipt in entry.get("receipts") or ():
            seen.setdefault(str(receipt.get("receipt_identity") or ""),
                            []).append(operation_id)
    shared = {identity: ids for identity, ids in seen.items()
              if len(ids) > 1}
    if shared:
        return Leg(name="dispatch_was_live_not_a_recording", role=REQUIRED,
                   status=LEG_FAIL,
                   evidence="%d receipt identities are carried by more than "
                            "one operation (%s); %s"
                            % (len(shared),
                               "; ".join("%s -> %s" % (identity, ", ".join(ids))
                                         for identity, ids in
                                         sorted(shared.items())),
                               "; ".join(parts)))
    if recorded:
        return Leg(name="dispatch_was_live_not_a_recording", role=REQUIRED,
                   status=LEG_FAIL,
                   evidence="the construction request persisted model "
                            "'recorded-double', a replayed recording rather "
                            "than the pinned live model: %s"
                            % "; ".join(parts))
    return Leg(name="dispatch_was_live_not_a_recording", role=REQUIRED,
               status=LEG_PASS, evidence="; ".join(parts))


def _no_earned_acquired_leg(bundle: Bundle) -> Leg:
    """Why no arm survived the check for an earned `model-acquired` origin.

    The two states are different and the message has to tell them apart. An
    arm the freeze never labelled acquired has nothing to demote. An arm it
    did label, and whose own construction record carries no earned
    evidence, is the defect this module exists to catch, and naming it as
    an absence would report the discovery as a null result.
    """
    claimed = bundle.arms_by_origin(ORIGIN_ACQUIRED)
    if not claimed:
        return Leg(name="no_earned_acquired_arm", role=REQUIRED,
                   status=LEG_FAIL,
                   evidence="no arm in the freeze claims artifact origin %r"
                            % ORIGIN_ACQUIRED)
    demoted = []
    for arm in claimed:
        evidence = bundle.construction_of(arm).get("acquisition_evidence")
        if isinstance(evidence, Mapping) and evidence.get("reason"):
            reason = str(evidence["reason"])
        else:
            reason = ("the construction record carries no acquisition "
                      "evidence, so nothing shows a live provider wrote it")
        demoted.append("%s (claims %r, reads %r: %s)"
                       % (arm, ORIGIN_ACQUIRED, ORIGIN_STAND_IN, reason))
    return Leg(name="no_earned_acquired_arm", role=REQUIRED, status=LEG_FAIL,
               evidence="%d arm(s) claim origin %r and none earned it: %s"
                        % (len(claimed), ORIGIN_ACQUIRED, "; ".join(demoted)))


def live_acquisition_verdict(bundle: Bundle) -> LiveAcquisition:
    acquired = bundle.earned_arms_by_origin(ORIGIN_ACQUIRED)
    basis = bundle.basis(
        "acquisition bytes and receipts under %s: freeze policy identities, "
        "construction requests, operation receipts and sealed use records"
        % bundle.root)
    if not acquired:
        # The four provenance legs are asked of the arm that *claimed* to be
        # acquired, not of the empty set. Its receipts are still evidence
        # about that arm, and a reader who has just been told the arm is a
        # stand-in is owed the specific reason rather than one generic
        # sentence repeated four times. A bundle that never claimed an
        # acquired arm has nothing to ask, and says so.
        claimed = bundle.arms_by_origin(ORIGIN_ACQUIRED)
        if claimed:
            legs = (
                _model_leg(bundle, claimed),
                _bound_leg(bundle, claimed),
                _executed_leg(bundle, claimed),
                _dispatch_leg(bundle, claimed),
            )
        else:
            legs = tuple(
                Leg(name=name, role=REQUIRED, status=LEG_FAIL,
                    evidence="no arm in the freeze claims artifact origin %r"
                             % ORIGIN_ACQUIRED)
                for name in LiveAcquisition.required_legs)
        return LiveAcquisition(
            value=UNPROVEN, legs=legs + (_no_earned_acquired_leg(bundle),),
            basis=basis)
    legs = (
        _model_leg(bundle, acquired),
        _bound_leg(bundle, acquired),
        _executed_leg(bundle, acquired),
        _dispatch_leg(bundle, acquired),
    )
    if all(leg.status == LEG_PASS for leg in legs):
        return LiveAcquisition(value=TRUE, legs=legs, basis=basis)
    return LiveAcquisition(value=UNPROVEN, legs=legs, basis=basis)


# ---------------------------------------------------------------------------
# task utility
# ---------------------------------------------------------------------------


def _executed_digest(record: Mapping[str, Any]) -> str:
    source = record.get("executed_source")
    if source in (None, "", "incumbent"):
        return ""
    return sha256_text(str(source))


def _bound_digests(bundle: Bundle, arm: str) -> tuple:
    """The digests an arm's own records may legitimately hash to.

    An arm's `source_digest` is the digest of everything it is bound to, and
    for an arm with one member that is the bytes the record executed. A
    repertoire arm is different: `control_arm.policy_identities` binds the
    concatenation of all its members, and `run_use` executes exactly one of
    them per record, chosen by the selector. Comparing a record's
    `executed_source` against the concatenation fails for every record of
    every multi-member arm, so the leg could not pass for the one arm shape
    the control is.

    `member_digests` is the per-member map the same function writes, keyed by
    capability id, and a record names which member it ran in `executed`. So
    the bound set is the arm's own digest plus those members. An arm with no
    member map is unchanged: the single-source arms in
    `evidence_s09_m3_live` have none, and their contaminated record must keep
    failing.

    The set is per arm and never crosses arms. It widens what counts as an
    arm's own bytes; it does not admit another arm's.
    """
    bound = str(bundle.construction_of(arm).get("bound_digest")
                or bundle.arm_policy_digest(arm) or "")
    members = (bundle.identities().get(arm) or {}).get("member_digests") or {}
    out: list[str] = []
    for digest in [bound] + [str(value) for value in members.values()]:
        if digest and digest not in out:
            out.append(digest)
    return tuple(out)


def _comparability_leg(bundle: Bundle, acquired: Sequence[str],
                       authored: Sequence[str]) -> Leg:
    parts = []
    hold = True
    for arm in tuple(acquired) + tuple(authored):
        allowed = _bound_digests(bundle, arm)
        digests = set()
        for record in bundle.records_for(arm):
            digest = _executed_digest(record)
            if digest:
                digests.add(digest)
        for digest in sorted(digests):
            matches = digest in allowed
            hold = hold and matches
            parts.append("%s executed source hashes to %s, its bound policy "
                         "is %s" % (arm, digest[:12],
                                    (allowed[0] if allowed else "")[:12]
                                    or "(none)"))
    if not parts:
        return Leg(name="arms_execute_their_own_bound_policy", role=REQUIRED,
                   status=LEG_FAIL,
                   evidence="no executed source bytes recorded on either arm")
    status = LEG_PASS if hold else LEG_FAIL
    return Leg(name="arms_execute_their_own_bound_policy", role=REQUIRED,
               status=status, evidence="; ".join(parts))


def _shared_tasks(bundle: Bundle, acquired: Sequence[str],
                  authored: Sequence[str]) -> dict:
    acquired_tasks = {}
    for arm in acquired:
        for record in bundle.records_for(arm):
            acquired_tasks[str(record.get("task_id"))] = record
    authored_tasks = {}
    for arm in authored:
        for record in bundle.records_for(arm):
            authored_tasks[str(record.get("task_id"))] = record
    return {task: (acquired_tasks[task], authored_tasks[task])
            for task in sorted(set(acquired_tasks) & set(authored_tasks))}


def _demotion_note(bundle: Bundle) -> str:
    """Name the arms the freeze calls acquired that did not earn it.

    A comparison that refuses because an arm list is empty reads as a study
    that never built one. When the arm exists and only its provenance
    failed, the reader has to be told that, or the refusal hides the one
    fact worth reading.
    """
    claimed = bundle.arms_by_origin(ORIGIN_ACQUIRED)
    demoted = [arm for arm in claimed
               if bundle.earned_origin(arm) != ORIGIN_ACQUIRED]
    if not demoted:
        return ""
    return ("; the freeze labels %s %r and %s own construction record%s no "
            "evidence that a live provider wrote %s"
            % (", ".join(demoted), ORIGIN_ACQUIRED,
               "its" if len(demoted) == 1 else "their",
               " carries" if len(demoted) == 1 else "s carry",
               "it" if len(demoted) == 1 else "them"))


def task_utility_verdict(bundle: Bundle) -> TaskUtility:
    acquired = bundle.earned_arms_by_origin(ORIGIN_ACQUIRED)
    authored = bundle.earned_arms_by_origin(ORIGIN_AUTHORED)
    metric_rule = dict(bundle.freeze.get("metric_rule") or {})
    basis = bundle.basis(
        "paired sealed-use records under %s, normalized by the freeze's own "
        "metric rule %r" % (bundle.root, metric_rule.get("quality")))
    comparable_leg = _comparability_leg(bundle, acquired, authored)
    rule_leg = Leg(
        name="normalization_rule_stated", role=REQUIRED,
        status=LEG_PASS if metric_rule.get("quality") else LEG_FAIL,
        evidence="freeze metric_rule=%s" % json.dumps(metric_rule, sort_keys=True))
    if not acquired or not authored:
        legs = (comparable_leg, rule_leg,
                Leg(name="shared_tasks_present", role=REQUIRED,
                    status=LEG_FAIL,
                    evidence="acquired arms %s, authored arms %s%s"
                             % (list(acquired), list(authored),
                                _demotion_note(bundle))))
        return TaskUtility(value=NOT_COMPARABLE, legs=legs, basis=basis)
    shared = _shared_tasks(bundle, acquired, authored)
    if not shared:
        legs = (comparable_leg, rule_leg,
                Leg(name="shared_tasks_present", role=REQUIRED,
                    status=LEG_FAIL,
                    evidence="no task sealed to both an acquired and an "
                             "authored arm"))
        return TaskUtility(value=NOT_COMPARABLE, legs=legs, basis=basis)
    shared_leg = Leg(
        name="shared_tasks_present", role=REQUIRED, status=LEG_PASS,
        evidence="%d shared tasks: %s" % (len(shared), ", ".join(shared)))
    legs = (comparable_leg, rule_leg, shared_leg)
    if comparable_leg.status == LEG_FAIL:
        return TaskUtility(value=NOT_COMPARABLE, legs=legs, basis=basis)
    deltas = {}
    for task, (acquired_record, authored_record) in shared.items():
        if acquired_record.get("fallback_reason") or \
                authored_record.get("fallback_reason"):
            legs = legs + (Leg(
                name="no_fallback_on_shared_tasks", role=REQUIRED,
                status=LEG_FAIL,
                evidence="%s was served by a fallback: %r"
                         % (task, acquired_record.get("fallback_reason")
                            or authored_record.get("fallback_reason"))),)
            return TaskUtility(value=NOT_COMPARABLE, legs=legs, basis=basis)
        deltas[task] = (Fraction(str(acquired_record.get(
            "normalized_reduction"))) - Fraction(str(authored_record.get(
                "normalized_reduction"))))
    legs = legs + (Leg(
        name="no_fallback_on_shared_tasks", role=REQUIRED, status=LEG_PASS,
        evidence="no shared task was served by a fallback"),)
    mean = sum(deltas.values(), Fraction(0)) / len(deltas)
    measured = Leg(
        name="paired_normalized_reduction", role=OPTIONAL, status=LEG_PASS,
        evidence="mean acquired-minus-authored normalized reduction %s over "
                 "%d shared tasks: %s"
                 % (mean, len(deltas),
                    ", ".join("%s=%s" % (task, float(delta))
                              for task, delta in sorted(deltas.items()))))
    legs = legs + (measured,)
    if mean == 0:
        return TaskUtility(value=TIE, legs=legs, basis=basis)
    return TaskUtility(value=WIN if mean > 0 else LOSS, legs=legs,
                       basis=basis)


# ---------------------------------------------------------------------------
# transfer
# ---------------------------------------------------------------------------


def transfer_verdict(bundle: Bundle) -> Transfer:
    acquired = bundle.earned_arms_by_origin(ORIGIN_ACQUIRED)
    basis = bundle.basis(
        "graph-domain sealed-use records under %s, with fallback and "
        "uncovered records excluded by the freeze's own rule" % bundle.root)
    if not acquired:
        return Transfer(
            value=UNPROVEN,
            legs=(Leg(name="software_scoped_policy_exists", role=REQUIRED,
                      status=LEG_FAIL,
                      evidence="no arm carries earned origin %r%s"
                               % (ORIGIN_ACQUIRED, _demotion_note(bundle))),),
            basis=basis)
    scopes = ["%s scope=%s" % (arm, json.dumps(bundle.arm_scope(arm),
                                              sort_keys=True))
              for arm in acquired]
    software = [arm for arm in acquired
                if bundle.arm_scope(arm).get("family") == "software"]
    scope_leg = Leg(
        name="software_scoped_policy_exists",
        role=REQUIRED,
        status=LEG_PASS if software else LEG_FAIL,
        evidence="; ".join(scopes))
    records = [record for arm in acquired
               for record in bundle.records_for(arm)
               if str(record.get("domain") or "") == DOMAIN_GRAPH]
    if not records:
        return Transfer(value=UNPROVEN, legs=(scope_leg, Leg(
            name="graph_records_present", role=REQUIRED, status=LEG_FAIL,
            evidence="no graph-domain record for an acquired arm")), basis=basis)
    served = [record for record in records if not record.get("fallback_reason")]
    served_leg = Leg(
        name="graph_records_served_without_fallback", role=REQUIRED,
        status=LEG_PASS if served else LEG_FAIL,
        evidence="%d of %d graph records were served without a fallback; "
                 "reasons: %s"
                 % (len(served), len(records),
                    "; ".join(sorted({str(r.get("fallback_reason"))
                                      for r in records if r.get(
                                          "fallback_reason")})) or "none"))
    qualified = []
    for arm in acquired:
        bound = str(bundle.construction_of(arm).get("bound_digest")
                    or bundle.arm_policy_digest(arm))
        for record in records:
            if record.get("fallback_reason"):
                continue
            if str(record.get("executed_policy_digest") or "") == bound:
                qualified.append("%s on %s" % (arm, record.get("task_id")))
    run_leg = Leg(
        name="graph_execution_of_the_bound_policy", role=REQUIRED,
        status=LEG_PASS if qualified else LEG_FAIL,
        evidence="%d graph records executed the bound software-scoped "
                 "policy: %s" % (len(qualified), ", ".join(qualified)
                                or "none"))
    legs = (scope_leg, served_leg, run_leg)
    if qualified:
        return Transfer(value=TRUE, legs=legs, basis=basis)
    return Transfer(value=UNPROVEN, legs=legs, basis=basis)


# ---------------------------------------------------------------------------
# recursive improvement
# ---------------------------------------------------------------------------

IMPROVEMENT_SELECTION_ACTIONS = ("improve", "revise", "choose_parent",
                                 "choose_successor", "select_experiment",
                                 "stop_improving", "submit_successor")

# M4's first clause is about what the policy decides, so the scan reads the
# policy's own bytes rather than the record that ran it. A policy that only
# emits a method-construction action names none of these.
_SELECTION_WORDS = ("improve", "improver", "improvee", "improvement",
                    "revise", "revision", "successor", "parent_digest",
                    "select_experiment", "stop_improving")


def _excerpt(source: str, width: int = 400) -> str:
    return source if len(source) <= width else source[:width] + " …"

ELIGIBILITY_RULE = (
    "M4 requires an acquired policy that selects what evidence to gather, "
    "what parent to build on, when to check or stop, and which successor to "
    "submit, compared with a strong fixed improver under matched starts. "
    "M4's own text states that a revised task solver alone is not an "
    "improved improver. A policy that only constructs a method for a task "
    "is a task solver, so the case does not apply and the verdict is "
    "%s with the reason, not %s." % (INELIGIBLE, FALSE))


def recursive_improvement_verdict(bundle: Bundle) -> RecursiveImprovement:
    acquired = bundle.earned_arms_by_origin(ORIGIN_ACQUIRED)
    basis = bundle.basis(
        "the acquired policy's own admitted actions under %s, read against "
        "M4's eligibility rule" % bundle.root)
    if not acquired:
        return RecursiveImprovement(
            value=INELIGIBLE,
            legs=(Leg(name="an_acquired_policy_exists", role=REQUIRED,
                      status=LEG_FAIL,
                      evidence="no arm carries earned origin %r%s; M4 admits "
                               "no other candidate"
                               % (ORIGIN_ACQUIRED, _demotion_note(bundle))),),
            basis=basis)
    kinds = set()
    cited = []
    for arm in acquired:
        for record in bundle.records_for(arm):
            for action in record.get("policy_actions") or ():
                kind = str(action.get("kind") or "")
                if kind and kind not in kinds:
                    kinds.add(kind)
                    cited.append("%s on %s emitted %s"
                                 % (arm, record.get("task_id"), kind))
        for name in ("policy_source",):
            source = str(bundle.construction_of(arm).get(name) or "")
            cited.append("%s bound source %s: %s"
                         % (arm, sha256_text(source)[:12] if source
                            else "(none)", _excerpt(source)))
            for word in _SELECTION_WORDS:
                if word in source:
                    kinds.add(word)
    for name in sorted(bundle.identities()):
        identity = bundle.identities()[name]
        for word in _SELECTION_WORDS:
            if word in str(identity.get("source") or ""):
                cited.append("%s freeze source names %r" % (name, word))
    selector = sorted(kinds & set(IMPROVEMENT_SELECTION_ACTIONS))
    selection_leg = Leg(
        name="policy_selects_improvement_actions", role=REQUIRED,
        status=LEG_PASS if selector else LEG_FAIL,
        evidence="improvement-selection markers %s; M4 selection actions "
                 "observed: %s"
                 % (sorted(kinds & set(_SELECTION_WORDS))
                    or ["(none)"],
                    ", ".join(selector) or "none"))
    comparison_leg = Leg(
        name="policy_compared_with_a_fixed_improver", role=OPTIONAL,
        status=LEG_UNKNOWN,
        evidence="no record in the bundle compares an acquired improver "
                 "with a fixed improver under matched starts and budgets")
    legs = (selection_leg, comparison_leg)
    if selector:
        return RecursiveImprovement(value=UNPROVEN, legs=legs, basis=basis)
    legs = legs + (Leg(
        name="task_solver_only", role=REQUIRED, status=LEG_FAIL,
        evidence="; ".join(cited) or "no admitted actions recorded"),)
    return RecursiveImprovement(value=INELIGIBLE, legs=legs, basis=basis)


# ---------------------------------------------------------------------------
# decision
# ---------------------------------------------------------------------------


def decide(verdicts: VerdictSet) -> Decision:
    gate = verdicts.acquisition
    if gate.value == UNPROVEN or not gate.all_binding_legs_pass:
        return Decision(
            outcome=PRIOR_STATE, verdicts=verdicts,
            rationale=("the acquisition provenance gate is unsatisfied, so "
                       "no acquisition or utility claim can be carried: %s"
                       % (", ".join(gate.failing_legs) or "unknown leg"),),
            rule=DECISION_RULE)
    if verdicts.mechanism.value != TRUE:
        return Decision(
            outcome=REPLACE, verdicts=verdicts,
            rationale=("the acquisition gate holds but the mechanism did not "
                       "verify: %s" % verdicts.mechanism.summary(),),
            rule=DECISION_RULE)
    if verdicts.utility.value != WIN or verdicts.transfer.value != TRUE:
        return Decision(
            outcome=SIMPLIFY, verdicts=verdicts,
            rationale=("the mechanism verified but the acquired policy did "
                       "not earn selection: utility=%s transfer=%s"
                       % (verdicts.utility.value, verdicts.transfer.value),),
            rule=DECISION_RULE)
    return Decision(
        outcome=KEEP, verdicts=verdicts,
        rationale=("the mechanism verified, the acquisition gate holds, the "
                   "acquired policy beat the authored baseline and "
                   "transferred: %s" % verdicts.utility.summary(),),
        rule=DECISION_RULE)


def issue(bundle: Bundle, mechanism: Mechanism) -> Decision:
    return decide(VerdictSet(
        mechanism=mechanism,
        acquisition=live_acquisition_verdict(bundle),
        utility=task_utility_verdict(bundle),
        transfer=transfer_verdict(bundle),
        recursive_improvement=recursive_improvement_verdict(bundle),
    ))
