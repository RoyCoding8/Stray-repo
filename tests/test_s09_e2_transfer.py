"""The transfer contrast has to be equal in everything but the family.

The handoff asks for source-to-target adaptation "against an equally
budgeted target-only constructor". Equally budgeted is the whole claim: if
the arms differ in record count or in characters, a difference in what the
model returns could be a difference in how much it was shown rather than in
what the experience was about, and that is the confound the
relevant-vs-irrelevant contrast exists to remove.

These tests pin that the two arms are built by one code path, draw the same
number of records, and carry the same length, and that a caller cannot build
an unequal pair.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from experiments.ad01 import learner
from experiments.ad01 import s09_e2_transfer as transfer


def _target():
    return {"task_id": "ad01-w1-transfer-gr-00", "family": "graph",
            "seed": 5, "template": "graph", "_source_family": "software"}


# Equal-length ids on purpose: a seed record embeds its task id, so
# `ad01-w1-within-sw-00` is three characters longer than
# `ad01-w1-dev-gr-00` and three of them make an 18-character difference.
# `test_unequal_id_lengths_are_refused` pins that refusal.
SOURCE = ["ad01-w1-xxxxx-sw-00", "ad01-w1-xxxxx-sw-01",
          "ad01-w1-xxxxx-sw-02"]
TARGET = ["ad01-w1-devxx-gr-00", "ad01-w1-devxx-gr-01",
          "ad01-w1-devxx-gr-02"]


def test_the_two_arms_are_equal_in_length_and_record_count():
    contrast = transfer.build_transfer_contrast(
        _target(), SOURCE, TARGET)

    assert contrast.equal_length
    assert contrast.equal_records
    assert contrast.adapted.records == contrast.target_only.records == 3
    assert contrast.adapted.chars == contrast.target_only.chars


def test_the_arms_differ_only_in_which_family_the_records_name():
    """Same shape, same count, different task ids in the records.

    Everything about the rendered experience is the same except the task
    each record is about. If the arm shape ever diverges, a result from it
    would be about the shape rather than the family.
    """
    contrast = transfer.build_transfer_contrast(
        _target(), SOURCE, TARGET)
    adapted = contrast.adapted.experience["observations"]
    target_only = contrast.target_only.experience["observations"]

    assert len(adapted) == len(target_only)
    assert all(set(a) == set(b) for a, b in zip(adapted, target_only))
    assert [o["task_id"] for o in adapted] != [o["task_id"] for o in target_only]
    assert all("-sw-" in o["task_id"] for o in adapted)
    assert all("-gr-" in o["task_id"] for o in target_only)
    assert all(len(o["task_id"]) == len(adapted[0]["task_id"])
               for o in target_only), \
        "the fixtures must carry equal-length ids for this contrast"


def test_unequal_id_lengths_are_refused_before_dispatch():
    """Equal record count is not equal length, and the difference is the
    confound this contrast cannot have.

    A seed record embeds its task id, so ids of different lengths make the
    two arms differ in how much text the model was shown. The first draft
    of this fixture did exactly that - 18 characters across three records -
    and the assertion that caught it is the fix.
    """
    with pytest.raises(ValueError, match="differ in length"):
        transfer.build_transfer_contrast(
            _target(),
            ["ad01-w1-within-sw-00", "ad01-w1-within-sw-01",
             "ad01-w1-within-sw-02"],
            TARGET)


def test_unequal_record_counts_are_refused_before_dispatch():
    """An equally budgeted control is the claim; a caller must not skip it."""
    with pytest.raises(ValueError, match="same number of records"):
        transfer.build_transfer_contrast(
            _target(), SOURCE, TARGET[:2])


def test_the_contrast_names_both_families_it_is_about():
    contrast = transfer.build_transfer_contrast(
        _target(), SOURCE, TARGET)

    assert contrast.target_family == "graph"
    assert contrast.source_family == "software"
    assert contrast.adapted.family == "source"
    assert contrast.target_only.family == "target"
