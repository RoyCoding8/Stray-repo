"""E2, contrast four: bounded source-to-target adaptation.

The handoff's fourth E2 contrast: *"Retained behavior on held-out families
within a world, and bounded source-to-target adaptation against an equally
budgeted target-only constructor."*

The other four E2 contrasts all had a constructor in `learner` waiting to be
driven. This one had nothing, so it is built here. Two arms, equal in
everything except what the experience is about:

- **adapted** — experience drawn from the *source* family (software), the
  target is graph.
- **target-only** — experience drawn from the *target* family (graph), the
  same count, the same length.

The target-only arm is the "equally budgeted target-only constructor" the
handoff names: it is what you get by building for the target directly rather
than adapting from elsewhere. It is deliberately the *strong* control, not a
strawman, so an adaptation win cannot be read as a win over doing nothing.

Both arms carry the same number of records and the same number of
characters, so neither context volume nor record count can be what a
difference is attributed to — which is the confound the relevance contrast
had to remove and this one does not have.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import learner
from . import worlds


@dataclass(frozen=True)
class TransferArm:
    name: str
    experience: dict
    records: int
    chars: int
    family: str

    def as_dict(self) -> dict:
        return {"name": self.name, "records": self.records,
                "chars": self.chars, "family": self.family}


@dataclass(frozen=True)
class TransferContrast:
    target_task_id: str
    target_family: str
    source_family: str
    adapted: TransferArm
    target_only: TransferArm

    @property
    def equal_length(self) -> bool:
        return self.adapted.chars == self.target_only.chars

    @property
    def equal_records(self) -> bool:
        return self.adapted.records == self.target_only.records

    def as_dict(self) -> dict:
        return {"target_task_id": self.target_task_id,
                "target_family": self.target_family,
                "source_family": self.source_family,
                "equal_length": self.equal_length,
                "equal_records": self.equal_records,
                "adapted": self.adapted.as_dict(),
                "target_only": self.target_only.as_dict()}


def build_transfer_contrast(target_task: dict, source_task_ids: list,
                            target_task_ids: list,
                            visible: list | None = None,
                            budget: dict | None = None) -> TransferContrast:
    """Adaptation against an equally budgeted target-only constructor.

    The two arms are built by the same `relevant_experience` call with
    different source id lists, so there is one code path and the arms
    cannot differ in anything but which family the records are about.

    Equal *record count* is necessary and not sufficient. A seed record
    embeds its task id, so `ad01-w1-within-sw-00` is three characters
    longer than `ad01-w1-dev-gr-00` and three of them make an 18-character
    difference between the arms. So the lengths are asserted equal and the
    caller is given the ids, not a fitted control: a test caught this and
    the assertion is the fix. Where a caller cannot choose id lengths that
    match, it must size the control the way `irrelevant_control_for` does
    rather than pass a longer arm as the control.
    """
    if len(source_task_ids) != len(target_task_ids):
        raise ValueError(
            "the two arms must draw the same number of records: %d source "
            "against %d target" % (len(source_task_ids), len(target_task_ids)))
    visible = visible or []
    adapted = learner.relevant_experience(
        target_task, source_task_ids, visible, budget)
    target_only = learner.relevant_experience(
        target_task, target_task_ids, visible, budget)
    contrast = TransferContrast(
        target_task_id=str(target_task.get("task_id", "")),
        target_family=str(target_task.get("family", "")),
        source_family=str(target_task.get("_source_family", "")) or "other",
        adapted=TransferArm("adapted", adapted,
                            len(adapted["observations"]),
                            learner._observation_chars(
                                adapted["observations"]),
                            "source"),
        target_only=TransferArm("target-only", target_only,
                                len(target_only["observations"]),
                                learner._observation_chars(
                                    target_only["observations"]),
                                "target"))
    if not contrast.equal_length:
        raise ValueError(
            "the two arms differ in length by %d characters (%d against %d), "
            "so a difference in what the model returns could be a difference "
            "in how much it was shown. Choose task ids of equal length, or "
            "size the control the way irrelevant_control_for does."
            % (contrast.adapted.chars - contrast.target_only.chars,
               contrast.adapted.chars, contrast.target_only.chars))
    return contrast
