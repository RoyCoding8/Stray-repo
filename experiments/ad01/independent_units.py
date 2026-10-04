"""Count coarse software witness signatures, not statistical independence.

The projection is `(fault, reference_type, faulty_type)`. It omits values,
operation graphs, intervention responses and the generator's sampling law.
Shared signatures do not establish duplicate tasks or dependent samples;
distinct signatures do not establish independence. The module name remains
for existing callers, but its output cannot justify an experimental unit.

The frozen software panel spans two signatures across four template names.
The bounded enumeration helper covers only the programs supplied by its caller.
Neither that count nor the minimum attainable sign-flip p-value measures
prospective statistical power. Graph behavior is not measured here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from experiments.representation import software

from .worlds import FROZEN_DIR

# The published observation vocabulary. A software witness is one
# `{"type", "value"}` pair, and `parse_ops` admits no third type, so the
# whole observable space is this product. Read from the module rather than
# restated so a new observation type cannot pass unnoticed.
OBSERVATION_TYPES = (software.MISSING, software.PRESENT)


@dataclass(frozen=True, order=True)
class Signature:
    """One observable behaviour: what a correct run saw and what a faulty one saw."""

    fault: str
    reference_type: str
    faulty_type: str

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.fault, self.reference_type, self.faulty_type)

    @classmethod
    def parse(cls, value: Sequence[str]) -> "Signature":
        fault, reference_type, faulty_type = value
        return cls(fault, reference_type, faulty_type)


@dataclass(frozen=True)
class FamilyObservation:
    """What one family can be observed to do, and whether its templates agree."""

    family: str
    template_count: int
    signatures: tuple[Signature, ...]
    signatures_by_template: Mapping[str, tuple[Signature, ...]]

    @property
    def signature_count(self) -> int:
        return len(self.signatures)

    @property
    def templates_per_signature(self) -> int:
        """How many template names ride on each distinct behaviour."""
        return self.template_count

    @property
    def collapses(self) -> bool:
        """True when more than one template names one behaviour."""
        return self.signature_count < self.template_count

    @property
    def surplus_templates(self) -> int:
        return self.template_count - self.signature_count

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "template_count": self.template_count,
            "signature_count": self.signature_count,
            "collapses": self.collapses,
            "surplus_templates": self.surplus_templates,
            "signatures": [list(s.as_tuple()) for s in self.signatures],
            "templates": {name: [list(s.as_tuple()) for s in sigs]
                          for name, sigs in sorted(
                              self.signatures_by_template.items())},
        }


def signature_of(task: Mapping[str, Any]) -> Signature:
    """The observable behaviour one software task exhibits.

    Reads the witness through the world's own runners rather than the task's
    recorded values, so a task whose stored witness disagrees with what its
    operations actually produce is reported by what it does, not by what it
    claims. That disagreement is exactly the class of defect this module
    exists to make visible.
    """
    ops = software.parse_ops(task["ops"])
    observation = task["witness"]["observation"]
    reference = software.reference_run(ops)[observation]
    faulty = software.faulty_run(ops, task["fault"])[observation]
    return Signature(task["fault"], reference["type"], faulty["type"])


def _frozen_software_tasks(root: Path) -> list[dict]:
    tasks = []
    for path in sorted(Path(root).rglob("*-sw-*.json")):
        tasks.append(json.loads(path.read_text()))
    return tasks


def software_family_observation(
        root: Path | str = FROZEN_DIR) -> FamilyObservation:
    """Measure the frozen software panel's observable behaviour count."""
    by_template: dict[str, set[Signature]] = {}
    for task in _frozen_software_tasks(root):
        by_template.setdefault(task["template"], set()).add(
            signature_of(task))
    per_template = {name: tuple(sorted(sigs))
                    for name, sigs in by_template.items()}
    every: set[Signature] = set()
    for sigs in per_template.values():
        every.update(sigs)
    return FamilyObservation(
        family="software",
        template_count=len(per_template),
        signatures=tuple(sorted(every)),
        signatures_by_template=per_template,
    )


def reachable_software_signatures(ops: Iterable[Sequence[Mapping[str, Any]]],
                                  faults: Sequence[str] = software.FAULTS,
                                  ) -> set[Signature]:
    """Every signature a set of candidate op programs can exhibit.

    Exhaustive over the programs it is given, not sampled. It is the tool
    that answers "is there a template shape nobody has written yet which
    would move the count", and a sampled search could not answer that.
    """
    found: set[Signature] = set()
    for candidate in ops:
        try:
            parsed = software.parse_ops(list(candidate))
        except software.SoftwareInvalid:
            continue
        observations = [entry["id"] for entry in parsed
                        if entry["op"] == "get"]
        if not observations:
            continue
        reference = software.reference_run(parsed)
        for fault in faults:
            try:
                faulty = software.faulty_run(parsed, fault)
            except software.SoftwareInvalid:
                continue
            for observation in observations:
                if reference[observation] == faulty[observation]:
                    continue
                found.add(Signature(fault, reference[observation]["type"],
                                    faulty[observation]["type"]))
    return found


def observable_space(faults: Sequence[str] = software.FAULTS) -> set[Signature]:
    """Every signature the observation vocabulary permits, reachable or not."""
    return {Signature(fault, reference, faulty)
            for fault in faults
            for reference in OBSERVATION_TYPES
            for faulty in OBSERVATION_TYPES}


def software_report(root: Path | str = FROZEN_DIR) -> dict[str, Any]:
    """The software family's templates, its behaviours, and the gap between."""
    observation = software_family_observation(root)
    report = observation.as_dict()
    reached = set(observation.signatures)
    report["unreachable_in_observable_space"] = sorted(
        s.as_tuple() for s in observable_space() - reached)
    report["reading"] = (
        "%d template names span %d coarse witness signatures. "
        "This projection does not measure statistical independence."
        % (observation.template_count, observation.signature_count))
    return report
