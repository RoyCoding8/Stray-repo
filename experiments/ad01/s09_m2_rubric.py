"""Frozen S09-M2 selection rubric for the three representation pilots.

M2 asks an independent design panel to select one representation form
for scale-up across model construction success, executable coverage,
intervention cost, behavior sensitivity and search efficiency, to record
why each other form was rejected, and forbids retrofitting the rubric
once results exist. This module is the rubric as data plus the scoring
function that consumes it, frozen before any arm's comparative numbers
exist.

The new arms are HAND-AUTHORED programs. A typed AST and an action
graph that a person wrote prove the representation can express and
execute the strategy; they are mechanism witnesses. They cannot support
a claim about model acquisition. The campaign doc's second constraint
is therefore structural here, not advisory: an axis declares an evidence
class, and an axis that requires acquisition reads its numerator from
`AcquisitionRecord` alone. A record carrying only an authored program
leaves the axis unmeasured, and an unmeasured acquisition axis
REFUSES the selection rather than scoring it zero. Zero would be a
falsifiable claim ("the model never produced a constructable policy");
absence is not a claim, and a rubric that invents one in the
rubric's absence is worse than no rubric.

`FROZEN_DIGEST` is the SHA-256 over the canonical axis table, the
selection rule and this version string. `verify_frozen()` recomputes it
and `select` calls it, so a table edited after scoring cannot be scored
against silently. A reviewer compares the recorded digest against the
commit that introduced it: equal digests mean the scored table is the
one that was frozen before results existed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

RUBRIC_VERSION = "s09-m2-rubric/1"

REPRESENTATIONS = ("step", "policy_ast", "action_graph")

HIGHER = "higher_is_better"
LOWER = "lower_is_better"

# A witness is an arm whose programs were authored by a person or a
# fixture. Only an arm that ran a real model response can support an
# acquisition claim, and acquisition is what the mechanism-witness
# constraint turns on.
WITNESS = "mechanism-witness"
ACQUIRED = "model-acquired"

KIND_COMPARISON = "cross-representation-comparison"
KIND_ACQUISITION = "acquisition-comparison"
KIND_SELF = "within-representation-cased"

WITNESS_ELIGIBLE = frozenset({KIND_COMPARISON, KIND_SELF})
ACQUISITION_ELIGIBLE = frozenset({KIND_ACQUISITION})

TIE_REFUSE = "refuse"


@dataclass(frozen=True)
class Axis:
    """One pre-committed measurement. `kinds` are the comparisons the axis
    admits; an axis named by no kind is unmeasured, never zero."""

    name: str
    question: str
    numerator: str
    denominator: str
    unit: str
    direction: str
    evidence_class: str
    kinds: frozenset
    may_leave_unmeasured: bool
    ineligible_reason: str


AXES: tuple[Axis, ...] = (
    Axis(
        name="model_construction_success",
        question=(
            "Of the construction attempts whose model response was "
            "acquired under the shared bounded construction budget, how "
            "many produced policy bytes that satisfied the interface "
            "contract's parse, verify and child dry-run and were then "
            "bound?"),
        numerator=(
            "attempts with a non-null `AcquisitionRecord` whose "
            "provenance is `model-acquired`, which passed interface "
            "validation and child dry-run, and whose bound digest "
            "equals the digest of the bytes that ran"),
        denominator=(
            "`ArmEvidence.constructed_attempts`; every attempt counts "
            "whatever its outcome, so a crashed construction or a "
            "malformed model response stays in the denominator"),
        unit="dimensionless ratio in [0, 1]",
        direction=HIGHER,
        evidence_class=ACQUIRED,
        kinds=frozenset({KIND_ACQUISITION}),
        may_leave_unmeasured=False,
        ineligible_reason=(
            "requires acquired model bytes; an authored program is a "
            "mechanism witness, not model construction"),
    ),
    Axis(
        name="executable_coverage",
        question=(
            "Of the strategy's runnable behaviors, how many did the form "
            "actually execute, counting only behaviors whose admitted "
            "actions and executed operations were recorded?"),
        numerator=(
            "behaviors marked `executed` in `ArmEvidence.executed_behaviors`, "
            "each backed by a use record quoting the digest of the bytes "
            "that ran and by the operation receipts for its admitted "
            "actions"),
        denominator=(
            "`ArmEvidence.strategy_behaviors`, the behaviors the shared "
            "strategy was decomposed into before any arm ran; one set "
            "for all arms, never restated per arm"),
        unit="dimensionless ratio in [0, 1]",
        direction=HIGHER,
        evidence_class=WITNESS,
        kinds=WITNESS_ELIGIBLE,
        may_leave_unmeasured=False,
        ineligible_reason="missing use record or operation receipts",
    ),
    Axis(
        name="intervention_cost",
        question=(
            "How many host interventions did the form need per executed "
            "behavior, counting an authored repair as one intervention "
            "exactly as a model's own repair counts one?"),
        numerator=(
            "interventions in `ArmEvidence.intervention_counts` summed "
            "over the categories: host-authored repair, witness "
            "authored after the model failed, intervention count, and "
            "billed units charged on this arm's behalf"),
        denominator=(
            "`ArmEvidence.executed_behaviors`; it equals the coverage "
            "denominator and is frozen once, so cost and coverage are "
            "read on one denominator and cannot drift apart"),
        unit="count and billed units per executed behavior",
        direction=LOWER,
        evidence_class=WITNESS,
        kinds=WITNESS_ELIGIBLE,
        may_leave_unmeasured=False,
        ineligible_reason="unknown or unrecorded intervention category",
    ),
    Axis(
        name="behavior_sensitivity",
        question=(
            "With the same view and the same budget, does the form's "
            "program byte substitution change actual admitted actions "
            "and outcomes, and does a changed view change what runs?"),
        numerator=(
            "the minimum over arms of the fraction of substitution "
            "cases in `ArmEvidence.sensitivity_cases` where substituting "
            "program bytes A and B under one view produced different "
            "admitted actions or different outcomes, on the frozen "
            "denominator of cases"),
        denominator=(
            "the number of substitution cases claimed for the arm; the "
            "axis takes the arm's own minimum and the panel compares "
            "those minima, so the arm with the weaker case split "
            "governs the comparison"),
        unit="dimensionless ratio in [0, 1]",
        direction=HIGHER,
        evidence_class=WITNESS,
        kinds=WITNESS_ELIGIBLE,
        may_leave_unmeasured=False,
        ineligible_reason=(
            "a case without paired action and outcome records, or an arm "
            "claiming fewer cases than the frozen panel minimum"),
    ),
    Axis(
        name="search_efficiency",
        question=(
            "How many environment operations and how many model "
            "dispatches per checker-clean success did the form need?"),
        numerator=(
            "environment operation count and model dispatch count from "
            "the same denominators as executable coverage: operations "
            "and dispatches charged to the arm, successes counted from "
            "the frozen private checkers only"),
        denominator=(
            "checker-clean successes from `ArmEvidence.successes`; when "
            "an arm has no clean success the axis is UNSATISFIABLE, "
            "not infinite, because an efficiency per success is "
            "undefined rather than large"),
        unit="operations and dispatches per checker-clean success",
        direction=LOWER,
        evidence_class=ACQUIRED,
        kinds=frozenset({KIND_ACQUISITION, KIND_SELF}),
        may_leave_unmeasured=True,
        ineligible_reason=(
            "requires acquired model bytes; an authored program is a "
            "mechanism witness, and an unsatisfied efficiency "
            "denominator is undefined, not poor"),
    ),
)

AXES_BY_NAME = {axis.name: axis for axis in AXES}

INTERVENTION_CATEGORIES = (
    "host_authored_repair",
    "authored_witness_after_model_failure",
    "intervention_count",
    "billed_units",
)

# A sensitivity claim below this many cases cannot be checked against a
# deliberate contradicting case, and the M0 design-competition criteria
# name interpretability and arm parity as matters a design panel judges
# on. Both are frozen, never adjudicated after results.
MIN_SENSITIVITY_CASES = 5

SELECTION_RULE = (
    "Only a representation with a measured value for every one of the "
    "five axes is eligible; an arm missing any required axis is "
    "ineligible and is never ranked against eligible arms. Eligible "
    "arms are ranked by a fixed-weight sum of the four scoring axes, "
    "weights frozen as model construction 1/5, executable coverage "
    "2/5, intervention cost 1/5, behavior sensitivity 1/5, and search "
    "efficiency 0/5, which keeps it a reported measurement rather than "
    "a selection lever. A ratio is the arm's value over the best value "
    "any arm measured, except intervention cost, which is 1 minus half "
    "the arm's cost over the worst cost any arm measured. A selection "
    "then needs a pre-registered margin of 0.05 over the runner-up; a "
    "smaller margin is a tie and is refused rather than broken by hand.")

SELECTION_WEIGHTS = {
    "model_construction_success": Fraction(1, 5),
    "executable_coverage": Fraction(2, 5),
    "intervention_cost": Fraction(1, 5),
    "behavior_sensitivity": Fraction(1, 5),
    "search_efficiency": Fraction(0, 5),
}

SELECTION_MARGIN = Fraction(5, 100)


@dataclass(frozen=True)
class AcquisitionRecord:
    attempt_id: str
    provenance: str
    response_digest: str
    validated: bool
    child_dry_run: bool
    bound_digest: str
    executed_digest: str


@dataclass(frozen=True)
class ArmEvidence:
    arm: str
    representation: str
    program_provenance: str
    constructed_attempts: int
    interface_contracts_passed: int
    bound_digest: str
    executed_digest: str
    use_record_refs: tuple
    strategy_behaviors: int
    executed_behaviors: int
    behavior_evidence_refs: tuple
    intervention_counts: dict
    operations: int
    model_dispatches: int
    successes: int
    checker_verdicts: tuple
    sensitivity_cases: tuple
    acquisitions: tuple
    panel_minimum_sensitivity_cases: int = MIN_SENSITIVITY_CASES

    def __post_init__(self) -> None:
        if self.representation not in REPRESENTATIONS:
            raise ValueError("unknown representation %r" % self.representation)
        if self.program_provenance not in (WITNESS, ACQUIRED):
            raise ValueError(
                "program_provenance must be %r or %r"
                % (WITNESS, ACQUIRED))
        missing = [name for name in INTERVENTION_CATEGORIES
                   if name not in self.intervention_counts]
        if missing:
            raise ValueError("intervention_counts is missing %s" % missing)
        extra = [name for name in self.intervention_counts
                 if name not in INTERVENTION_CATEGORIES]
        if extra:
            raise ValueError("intervention_counts has unknown %s" % extra)
        if self.checker_verdicts not in ((), ("clean",), ("dirty",)):
            raise ValueError(
                "checker_verdicts must be (), ('clean',) or ('dirty',) so "
                "a partial checker run cannot read as clean")


def _fingerprint(record: AcquisitionRecord) -> str:
    if record.bound_digest != record.executed_digest:
        return "bound-bytes-differ-from-executed-bytes"
    if not record.validated or not record.child_dry_run:
        return "candidate-never-reached-the-executing-form"
    return "clean"


def canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _frozen_table() -> dict:
    return {
        "version": RUBRIC_VERSION,
        "representations": list(REPRESENTATIONS),
        "axes": [
            {
                "name": axis.name,
                "question": axis.question,
                "numerator": axis.numerator,
                "denominator": axis.denominator,
                "unit": axis.unit,
                "direction": axis.direction,
                "evidence_class": axis.evidence_class,
                "kinds": sorted(axis.kinds),
                "may_leave_unmeasured": axis.may_leave_unmeasured,
                "ineligible_reason": axis.ineligible_reason,
            }
            for axis in AXES
        ],
        "weights": {name: [weight.numerator, weight.denominator]
                    for name, weight in sorted(SELECTION_WEIGHTS.items())},
        "margin": [SELECTION_MARGIN.numerator, SELECTION_MARGIN.denominator],
        "tie": TIE_REFUSE,
        "intervention_categories": list(INTERVENTION_CATEGORIES),
        "min_sensitivity_cases": MIN_SENSITIVITY_CASES,
        "rule": SELECTION_RULE,
    }


FROZEN_TABLE = _frozen_table()
FROZEN_DIGEST = hashlib.sha256(
    canonical(FROZEN_TABLE).encode("utf-8")).hexdigest()

FROZEN_AT_COMMIT = "pending: the digest above is frozen by this commit"


def verify_frozen() -> None:
    """Raise if the rubric moved after its digest was recorded."""
    actual = hashlib.sha256(
        canonical(_frozen_table()).encode("utf-8")).hexdigest()
    if actual != FROZEN_DIGEST:
        raise ValueError(
            "rubric digest drifted: recorded %s, recomputed %s"
            % (FROZEN_DIGEST, actual))


def provenance_of(evidence: ArmEvidence) -> str:
    """What kind of claim an arm's programs can carry at all.

    A `mechanism-witness` arm may be compared on expressiveness,
    executability and sensitivity. It may never be scored on model
    construction, and the panel selection cannot complete on its
    numbers alone.
    """
    return evidence.program_provenance


def _acquisition_axis_value(evidence: ArmEvidence) -> tuple:
    if evidence.program_provenance != ACQUIRED:
        return None, ("arm is a mechanism witness: its program is a %s "
                      "artifact, not a model acquisition record"
                      % evidence.program_provenance)
    if evidence.constructed_attempts < 0:
        return None, "negative-constructed-attempts"
    if evidence.constructed_attempts == 0:
        return None, ("constructed_attempts is zero on an arm claiming "
                      "acquired bytes; the denominator is undefined")
    outcomes = [_fingerprint(record)
                for record in evidence.acquisitions]
    clean = outcomes.count("clean")
    if not outcomes:
        return None, ("no acquisition record for an arm claiming %d "
                      "construction attempts" % evidence.constructed_attempts)
    if evidence.interface_contracts_passed != clean:
        return None, (
            "interface_contracts_passed (%d) disagrees with the acquisition "
            "records (%d) that satisfy the axis numerator; the rubric will "
            "not reconcile them for you"
            % (evidence.interface_contracts_passed, clean))
    if evidence.bound_digest != evidence.executed_digest:
        return None, "bound-bytes-differ-from-executed-bytes"
    return Fraction(clean, evidence.constructed_attempts), None


def _coverage_axis_value(evidence: ArmEvidence) -> tuple:
    if evidence.strategy_behaviors < 0 or evidence.executed_behaviors < 0:
        return None, "negative-behavior-count"
    if evidence.executed_behaviors > evidence.strategy_behaviors:
        return None, "more-executed-behaviors-than-the-strategy-has"
    if evidence.executed_behaviors and not evidence.use_record_refs:
        return None, "executed-behaviors-without-a-use-record"
    if len(evidence.behavior_evidence_refs) < evidence.executed_behaviors:
        return None, "executed-behavior-without-an-evidence-ref"
    if evidence.use_record_refs and not evidence.executed_behaviors:
        return None, "use-record-without-executed-behaviors"
    if evidence.executed_behaviors == 0:
        return Fraction(0, evidence.strategy_behaviors), None
    return Fraction(evidence.executed_behaviors, evidence.strategy_behaviors), None


def _intervention_axis_value(evidence: ArmEvidence) -> tuple:
    if evidence.strategy_behaviors < 0:
        return None, "negative-behavior-count"
    counts = evidence.intervention_counts
    if any(type(counts[name]) is not int for name in INTERVENTION_CATEGORIES):
        return None, "intervention-count-is-not-an-integer"
    if any(counts[name] < 0 for name in INTERVENTION_CATEGORIES):
        return None, "negative-intervention-count"
    total = sum(counts[name] for name in INTERVENTION_CATEGORIES)
    if evidence.executed_behaviors == 0:
        if total:
            return None, ("interventions-charged-with-no-executed-behavior")
        return None, ("no-executed-behavior-denominator; intervention cost "
                      "per executed behavior is undefined, not zero")
    if counts["authored_witness_after_model_failure"] and \
            evidence.program_provenance == ACQUIRED:
        return None, ("authored-witness-after-model-failure-charged-against-"
                      "an-acquired-program; the arms are not separated")
    return Fraction(total, evidence.executed_behaviors), None


def _sensitivity_axis_value(evidence: ArmEvidence) -> tuple:
    cases = evidence.sensitivity_cases
    if not cases:
        return None, "no-substitution-cases"
    if len(cases) < evidence.panel_minimum_sensitivity_cases:
        return None, ("%d substitution cases is below the frozen panel "
                      "minimum of %d"
                      % (len(cases), evidence.panel_minimum_sensitivity_cases))
    distinct = set(cases)
    if not distinct <= {"changed-actions-changed-outcome",
                         "changed-actions-same-outcome",
                         "same-actions-same-outcome"}:
        return None, "unknown-substitution-case-verdict"
    if evidence.executed_digest and not distinct - {"same-actions-same-outcome"}:
        return None, ("every substitution case reads as same-actions; the "
                      "form does not bind its bytes to what runs")
    changed = len([case for case in cases
                   if case != "same-actions-same-outcome"])
    return Fraction(changed, len(cases)), None


def _search_axis_value(evidence: ArmEvidence) -> tuple:
    if evidence.program_provenance != ACQUIRED:
        return None, ("arm is a mechanism witness: resource efficiency is "
                      "not a mechanism-witness claim")
    if evidence.checker_verdicts == ():
        return None, "no-checker-verdict"
    if evidence.successes <= 0:
        return None, ("no-checker-clean-success; efficiency per success is "
                      "undefined, not poor")
    if evidence.operations < 0 or evidence.model_dispatches < 0:
        return None, "negative-resource-count"
    return (Fraction(evidence.operations, evidence.successes),
            Fraction(evidence.model_dispatches, evidence.successes)), None


_VALUE_FNS = {
    "model_construction_success": _acquisition_axis_value,
    "executable_coverage": _coverage_axis_value,
    "intervention_cost": _intervention_axis_value,
    "behavior_sensitivity": _sensitivity_axis_value,
    "search_efficiency": _search_axis_value,
}


@dataclass(frozen=True)
class AxisRecord:
    arm: str
    axis: str
    evidence_class: str
    value: Any
    insufficient_reason: str | None = None
    unsatisfied_reason: str | None = None
    included_in_score: bool = False

    @property
    def is_measured(self) -> bool:
        return self.value is not None

    @property
    def blocks_selection(self) -> bool:
        """An axis the arm could have measured and did not stops selection.

        `may_leave_unmeasured` axes reach an unmeasured state only
        through `unsatisfied_reason`, which the axis itself declares, so
        an exemption is visible on the record rather than assumed.
        """
        return self.insufficient_reason is not None


@dataclass(frozen=True)
class Rejection:
    arm: str
    reason_code: str
    detail: str
    evidence: tuple


@dataclass(frozen=True)
class Decision:
    selected: str
    totals: dict
    normalized: dict
    margin_over_runner_up: Fraction | None
    rejections: tuple
    records: tuple
    rubric_version: str = RUBRIC_VERSION
    rubric_digest: str = FROZEN_DIGEST


@dataclass(frozen=True)
class Insufficient:
    """The frozen rule produced no selection. Every arm is accounted for."""

    rejected_arms: tuple
    records: tuple
    rubric_version: str = RUBRIC_VERSION
    rubric_digest: str = FROZEN_DIGEST

    @property
    def reasons(self) -> dict:
        return {rejection.arm: _rejection_reason(rejection)
                for rejection in self.rejected_arms}


def axis_kind(evidence: ArmEvidence, axis: Axis) -> str:
    if axis.evidence_class == ACQUIRED:
        return KIND_ACQUISITION
    return KIND_COMPARISON


def score_axis(evidence: ArmEvidence, axis: Axis) -> AxisRecord:
    if axis.may_leave_unmeasured and evidence.constructed_attempts == 0:
        return AxisRecord(
            arm=evidence.arm, axis=axis.name,
            evidence_class=axis.evidence_class, value=None,
            unsatisfied_reason=axis.ineligible_reason,
            included_in_score=False)
    kind = axis_kind(evidence, axis)
    if kind not in axis.kinds:
        return AxisRecord(
            arm=evidence.arm, axis=axis.name,
            evidence_class=axis.evidence_class, value=None,
            insufficient_reason=axis.ineligible_reason,
            included_in_score=False)
    value, reason = _VALUE_FNS[axis.name](evidence)
    if reason is not None:
        return AxisRecord(
            arm=evidence.arm, axis=axis.name,
            evidence_class=axis.evidence_class, value=None,
            insufficient_reason=reason, included_in_score=False)
    weight = SELECTION_WEIGHTS[axis.name]
    return AxisRecord(
        arm=evidence.arm, axis=axis.name,
        evidence_class=axis.evidence_class, value=value,
        included_in_score=weight > 0)


def _ratio(value: Fraction, best: Fraction) -> Fraction:
    if value == 0 or best == 0:
        return Fraction(0)
    return value / best


def _reverse_ratio(value: Fraction, worst: Fraction) -> Fraction:
    """A cost in [0, worst] maps to 1 at zero and 0 at the worst cost."""
    if worst <= 0:
        return Fraction(1)
    return 1 - (value / (2 * worst))


def _measured_columns(records: tuple, axis: str) -> list:
    """One column of comparable numbers per slot in an axis's value."""
    columns: list = []
    for record in records:
        if record.axis != axis or not record.is_measured:
            continue
        value = record.value
        if not isinstance(value, tuple):
            value = (value,)
        while len(columns) < len(value):
            columns.append([])
        for index, item in enumerate(value):
            columns[index].append(item)
    return columns


def _rejection_reason(rejection: Rejection) -> str:
    if not rejection.evidence:
        return "%s: %s" % (rejection.reason_code, rejection.detail)
    return "%s: %s (%s)" % (rejection.reason_code, rejection.detail,
                            "; ".join(rejection.evidence))


def _normalized_records(records: tuple) -> tuple:
    """Normalize each measured axis against the arms that measured it.

    Normalization is cross-arm by construction, so it happens once over
    the pooled records rather than per arm. A cost axis normalizes
    against the worst measured value in its own column; every other axis
    against the best. A column no arm measured normalizes to zero, which
    is safe because an unmeasured axis carries weight zero.
    """
    bounds = {axis: [max(column) if column else Fraction(0)
                     for column in _measured_columns(records, axis)]
              for axis in AXES_BY_NAME}
    out = []
    for record in records:
        if not record.is_measured:
            out.append(record)
            continue
        spec = AXES_BY_NAME[record.axis]
        bound = bounds[record.axis]
        value = record.value
        values = value if isinstance(value, tuple) else (value,)
        ratios = tuple(
            _reverse_ratio(item, bound[index]) if spec.direction == LOWER
            else _ratio(item, bound[index])
            for index, item in enumerate(values))
        out.append(replace(record, value=ratios if len(ratios) > 1
                           else ratios[0]))
    return tuple(out)


def _total(record_map) -> Fraction:
    total = Fraction(0)
    for name, record in record_map.items():
        weight = SELECTION_WEIGHTS[name]
        if weight == 0 or not record.is_measured:
            continue
        total += weight * record.value
    return total


def select(evidences) -> Decision | Insufficient:
    """Apply the frozen rule, or refuse."""
    verify_frozen()
    arms = list(evidences)
    names = [evidence.arm for evidence in arms]
    if len(set(names)) != len(names):
        raise ValueError("duplicate arm names %s" % names)
    for evidence in arms:
        if evidence.representation not in REPRESENTATIONS:
            raise ValueError("unknown representation %r"
                             % evidence.representation)
    if len(arms) < 2:
        raise ValueError(
            "a selection needs at least two representations; one arm "
            "cannot be a comparison")
    raw = tuple(score_axis(evidence, axis)
                for evidence in arms for axis in AXES)
    raw = _normalized_records(raw)
    by_arm = {}
    for record in raw:
        by_arm.setdefault(record.arm, {})[record.axis] = record
    rejections = []
    for evidence in arms:
        record_map = by_arm[evidence.arm]
        blocking = [name for name, record in record_map.items()
                    if record.blocks_selection]
        if blocking:
            rejections.append(Rejection(
                arm=evidence.arm, reason_code="incomplete",
                detail="; ".join(blocking),
                evidence=tuple(record_map[name].insufficient_reason
                               for name in blocking)))
    if rejections:
        blocked = {rejection.arm for rejection in rejections}
        for evidence in arms:
            if evidence.arm in blocked:
                continue
            records = by_arm[evidence.arm]
            unsatisfied = [name for name, record in records.items()
                           if record.unsatisfied_reason is not None]
            if unsatisfied:
                rejections.append(Rejection(
                    arm=evidence.arm, reason_code="axis-unsatisfied",
                    detail="; ".join(unsatisfied),
                    evidence=tuple(records[name].unsatisfied_reason
                                   for name in unsatisfied)))
        return Insufficient(rejected_arms=tuple(rejections), records=raw)
    totals = {arm: _total(record_map) for arm, record_map in by_arm.items()}
    normalized = {
        arm: {name: str(record.value) for name, record in record_map.items()
              if record.is_measured}
        for arm, record_map in by_arm.items()}
    if not any(total > 0 for total in totals.values()):
        return Insufficient(
            rejected_arms=tuple(
                Rejection(arm=evidence.arm,
                          reason_code="no-positive-evidence",
                          detail="every normalized ratio is zero on every arm",
                          evidence=()),),
            records=raw)
    ranked = sorted(totals, key=lambda arm: (-totals[arm], arm))
    leader = ranked[0]
    runner_up = ranked[1]
    margin = totals[leader] - totals[runner_up]
    if margin < SELECTION_MARGIN:
        return Insufficient(
            rejected_arms=tuple(
                Rejection(arm=arm, reason_code="tied-within-margin",
                          detail="%s is within %s of %s"
                                 % (arm, SELECTION_MARGIN, leader),
                          evidence=("total %s against %s"
                                    % (totals[arm], totals[leader]),))
                for arm in totals if arm != leader),
            records=raw)
    losers = tuple(Rejection(
        arm=evidence.arm, reason_code="scored-below-selection-margin",
        detail="%s totals %s against %s's %s" % (
            evidence.arm, totals[evidence.arm], leader, totals[leader]),
        evidence=tuple("%s=%s" % (name, normalized[evidence.arm][name])
                        for name in sorted(normalized[evidence.arm])))
        for evidence in arms if evidence.arm != leader)
    return Decision(selected=leader, totals=totals, normalized=normalized,
                    margin_over_runner_up=margin, rejections=losers,
                    records=raw)
