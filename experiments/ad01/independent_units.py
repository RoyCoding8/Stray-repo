"""How many independent units each task structure can actually present.

`s09_panel_inventory` counts `(family, template)` pairs, so it answers
"how many templates does this panel name". It does not answer the question
the sign-flip test asks: *if a contrast treated every template as one
cluster, would those clusters have been different draws?*

Two generators can mint a hundred templates that are one unit, and the
cluster rule would report a hundred. The rule is not wrong about what it
counts. It is silent about whether the count is worth having, because a
template is a generation family by naming convention and nothing checks
that the naming is honest.

This module measures that. It derives, from the generator source rather
than from any report, how many *observationally distinct* behaviours each
family can produce: the distinct `(fault, reference_type, faulty_type)`
signatures a family's witness can take, where the types come from the
world's own published observation vocabulary.

The measurement is deliberately separate from the power decision. It does
not decide whether six is the right threshold and it does not lower one.
It reports a fact the threshold is silent about, so the two can be read
together.

**The result, measured not assumed.** The frozen software panel offers 4
templates and reaches exactly 2 observable signatures: `stale-read` always
yields `str` against `str`, and `stale-clear` always yields `missing`
against `str`. Both are forced by the fault branches themselves, not by the
templates. So four software clusters are two units wearing four names, and
no software generator that reuses those two branches can close the
shortfall, however many templates it adds.

The graph family is **not measured here.** `s09_panel_inventory` records its
`signature_count` as `None` with the note that no observable-behaviour
measure is defined for it, so whether the six graph templates are six
independent units is unproven rather than established. Read the ceiling
spread before relying on it.

A family whose signatures collapse is not a panel that can be powered by
adding to it. It is a panel where two rows are the same row.
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
        "%d templates carry %d distinct observable behaviours, so %d "
        "templates are duplicate names for behaviour already present."
        % (observation.template_count, observation.signature_count,
           observation.surplus_templates))
    return report