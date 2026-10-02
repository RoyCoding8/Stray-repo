"""Lane J. Paired comparison, per-family rows, failure classification, and
the units that keep a recount from being divided by a witness.

`Recomputed` and `Attested` are separate types because a recount and a
witness are different kinds of evidence. Neither constructor accepts the
other's payload, so an attested number cannot be relabelled a
recomputation and a recount cannot be given a source it did not have.

A `Cost` names its denomination, and `total` and `ratio` refuse to cross
one. Unknown stays unknown: `total` of a measured and an unknown cost is
unknown, not the measured part, and `ratio` against an unknown or a zero
denominator raises rather than returning zero, infinity or `None` the
caller may forget to read.
"""

from __future__ import annotations

from dataclasses import dataclass

UNIT_MODEL_DISPATCHES = "model-dispatches"
UNIT_RESERVATION_UNITS = "reservation-units"

RECOMPUTABLE = "recomputable"
RUNTIME_ATTESTED = "runtime-attested"

CONSTRUCTION_FAILED = "construction_failed"
EXECUTION_FAILED = "execution_failed"
CONTAMINATED = "contaminated"
INELIGIBLE = "ineligible"
PROVIDER_UNAVAILABLE = "provider_unavailable"

FAILURE_REASONS = (CONSTRUCTION_FAILED, EXECUTION_FAILED, CONTAMINATED,
                   INELIGIBLE, PROVIDER_UNAVAILABLE)

UNKNOWN = "unknown"


class _Measurement:
    """A value that knows which of the two kinds of evidence it is."""

    __slots__ = ()

    def __str__(self) -> str:
        return "%s=%s" % (measurement_kind(self), self.value)


@dataclass(frozen=True, init=False)
class Recomputed(_Measurement):
    """A value re-derived offline from the bundle's own bytes.

    It has no witness. Anything the runtime alone could see -- elapsed
    time, a charge, a token count -- cannot be constructed here.
    """
    value: str

    def __init__(self, value):
        if isinstance(value, _Measurement):
            raise TypeError(
                "an attested value cannot be re-labelled a recomputation")
        if not isinstance(value, str) or not value:
            raise ValueError("a recomputation names the value it re-derived")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, init=False)
class Attested(_Measurement):
    """A runtime claim. Offline verification can carry it, never re-derive it.

    `status` is one of the study's measurement statuses. Only `measured`
    carries a number; `unknown` and `unresolved` carry the string.
    """
    value: int | str
    source: str
    status: str

    def __init__(self, value, source: str, status: str = "measured",
                 *, recomputable_from: str = None):
        if recomputable_from is not None:
            raise TypeError(
                "an attestation is not recomputable; Recomputed is the type "
                "for a value derived from %r" % (recomputable_from,))
        if not source:
            raise ValueError("an attestation names the witness that made it")
        if value != UNKNOWN and (type(value) is not int or value < 0):
            raise TypeError("an attestation is a whole count or %r" % UNKNOWN)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "status", status)


def measurement_kind(value) -> str:
    if isinstance(value, Recomputed):
        return RECOMPUTABLE
    if isinstance(value, Attested):
        return RUNTIME_ATTESTED
    raise TypeError("%r is neither a recomputation nor an attestation"
                    % (value,))


@dataclass(frozen=True)
class Cost:
    value: int | str
    unit: str

    def __post_init__(self) -> None:
        if not self.unit:
            raise ValueError("a cost names its denomination")
        if self.value != UNKNOWN and (
                type(self.value) is not int or self.value < 0):
            raise ValueError("a cost is a whole count or %r" % UNKNOWN)


def total(costs) -> Cost:
    """Sum costs in one denomination. An unknown member makes the total unknown."""
    counted = list(costs)
    if not counted:
        raise ValueError("an empty cost list has no total")
    units = {cost.unit for cost in counted}
    if len(units) != 1:
        raise ValueError("cannot add costs in %s: %s are different "
                         "denominations" % (sorted(units), ", ".join(
                             sorted(unit for unit in units))))
    unit = units.pop()
    if any(cost.value == UNKNOWN for cost in counted):
        return Cost(value=UNKNOWN, unit=unit)
    return Cost(value=sum(cost.value for cost in counted), unit=unit)


def ratio(numerator: Cost, denominator: Cost) -> float:
    """A ratio inside one denomination with a known, non-zero denominator."""
    if numerator.unit != denominator.unit:
        raise ValueError("cannot divide %s by %s: different denominations"
                         % (numerator.unit, denominator.unit))
    if denominator.value == UNKNOWN or numerator.value == UNKNOWN:
        raise ValueError("an unknown quantity cannot be divided; the "
                         "denominator and numerator must both be measured")
    if denominator.value == 0:
        raise ValueError("a ratio against a zero denominator is not a ratio")
    return numerator.value / denominator.value


@dataclass(frozen=True)
class Observation:
    arm: str
    family: str
    task_id: str
    quality: float
    acquisition_lineage: str
    cost: Cost = None

    def __post_init__(self) -> None:
        if self.arm not in ("P0", "P1", "P2"):
            raise ValueError("unknown arm %r" % (self.arm,))
        if not self.family or not self.task_id or not self.acquisition_lineage:
            raise ValueError("an observation names its family, task and "
                             "acquisition lineage")
        if self.cost is not None and not isinstance(self.cost, Cost):
            raise TypeError("a cost is a Cost")


@dataclass(frozen=True)
class Pair:
    task_id: str
    family: str
    acquisition_lineage: str
    treatment: float
    control: float

    @property
    def delta(self) -> float:
        return self.treatment - self.control


@dataclass(frozen=True)
class FamilyRow:
    """One family's result. A family with no shared task has no mean.

    The row holds the observations it was built from because two of its
    properties are about them rather than about the pairs: which tasks
    never met, and what the treatment cost against the control's.
    """
    family: str
    pairs: tuple
    observations: tuple
    treatment: str
    control: str

    @property
    def matched(self) -> bool:
        return bool(self.pairs)

    @property
    def tasks(self) -> int:
        return len(self.pairs)

    @property
    def unmatched_tasks(self) -> tuple:
        paired_tasks = {pair.task_id for pair in self.pairs}
        return tuple(sorted({observation.task_id
                             for observation in self.observations}
                            - paired_tasks))

    @property
    def mean_delta(self):
        if not self.pairs:
            return None
        return sum(pair.delta for pair in self.pairs) / len(self.pairs)

    @property
    def by_lineage(self) -> dict:
        grouped = {}
        for pair in self.pairs:
            deltas, count = grouped.get(pair.acquisition_lineage, (0.0, 0))
            grouped[pair.acquisition_lineage] = (deltas + pair.delta, count + 1)
        return {lineage: (total / count, count)
                for lineage, (total, count) in sorted(grouped.items())}

    @property
    def cost_ratio(self):
        """Treatment cost per unit of control cost, or None."""
        costs = {arm: [observation.cost for observation in self.observations
                       if observation.arm == arm
                       and observation.cost is not None]
                 for arm in (self.treatment, self.control)}
        for members in costs.values():
            if not members:
                return None
        return ratio(total(costs[self.treatment]), total(costs[self.control]))


def paired(observations, *, treatment: str, control: str) -> tuple:
    treated = {observation.task_id: observation
               for observation in observations
               if observation.arm == treatment}
    controlled = {observation.task_id: observation
                  for observation in observations
                  if observation.arm == control}
    shared = sorted(set(treated) & set(controlled))
    return tuple(Pair(task_id=task_id,
                      family=treated[task_id].family,
                      acquisition_lineage=treated[task_id].acquisition_lineage,
                      treatment=treated[task_id].quality,
                      control=controlled[task_id].quality)
                 for task_id in shared)


def summarize(observations, *, treatment: str, control: str) -> "Summary":
    """One row per family. Nothing is pooled across a family boundary."""
    rows = {}
    for observation in observations:
        rows.setdefault(observation.family, []).append(observation)
    family_rows = {
        family: FamilyRow(
            family=family,
            pairs=paired(members, treatment=treatment, control=control),
            observations=tuple(members),
            treatment=treatment, control=control)
        for family, members in sorted(rows.items())}
    return Summary(treatment=treatment, control=control,
                   families=family_rows)


@dataclass(frozen=True)
class Summary:
    treatment: str
    control: str
    families: dict

    @property
    def pairs(self) -> tuple:
        return tuple(pair for row in self.families.values()
                     for pair in row.pairs)

    @property
    def matched(self) -> bool:
        return bool(self.pairs)

    @property
    def mean_delta(self):
        if not self.pairs:
            return None
        return sum(pair.delta for pair in self.pairs) / len(self.pairs)

    @property
    def unmatched_families(self) -> tuple:
        return tuple(sorted(family for family, row in self.families.items()
                            if not row.matched))


@dataclass(frozen=True)
class Failure:
    """Why an arm produced no usable score. The reason is not a quality."""
    arm: str
    family: str
    task_id: str
    reason: str
    detail: str = ""
    quality: None = None

    def __post_init__(self) -> None:
        if self.reason not in FAILURE_REASONS:
            raise ValueError("unknown failure reason %r" % (self.reason,))
        if not self.arm or not self.family or not self.task_id:
            raise ValueError("a failure names its arm, family and task")
        if self.quality is not None:
            raise ValueError(
                "a failure carries a reason, not a score: %r cannot be "
                "scored" % (self.reason,))


def classify(failures) -> dict:
    """Group by reason. A reason with no members is absent, never merged."""
    table = {reason: [] for reason in FAILURE_REASONS}
    for failure in failures:
        if not isinstance(failure, Failure):
            raise TypeError("classify takes Failures, got %r" % (failure,))
        table[failure.reason].append(
            (failure.arm, failure.family, failure.task_id))
    return {reason: tuple(sorted(members))
            for reason, members in table.items() if members}
