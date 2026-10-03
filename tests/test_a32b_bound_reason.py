"""A bound disposition must carry a stated reason, in words.

`bound` is the one disposition with no refusal behind it: the assessment
came back `bind` and the durable binding took. The projection used to
render that as `reason: ""`, because it read `episode.get("reason", "")`
for every disposition and only the refusing ones ever set one. The
archived `reports/evidence/invl02-r123/e0-run.json` carries exactly that
shape, so the projection had already produced it once.

An empty string is the one value that cannot be audited: it is
indistinguishable from a reason that was meant and lost. These tests pin
that the stated reason survives for `bound`, and that the projection at
the end of the policy-revision episode is what routes it there.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from experiments.ad01 import trajectory

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "reports" / "evidence" / "invl02-r123"


def test_bound_states_its_reason():
    """The disposition that carries no refusal still has to say what it did."""
    reason = trajectory._disposition_reason(
        {"disposition": "bound", "release_id": "acquired-live-live-r1"})

    assert reason
    assert "bound" in reason
    assert "acquired-live-live-r1" in reason


def test_a_present_reason_is_kept_verbatim():
    """A refusal's stated reason is the auditor's evidence; do not restate it."""
    episode = {"disposition": "rejected",
               "reason": "policy construction call budget exhausted"}

    assert trajectory._disposition_reason(episode) == episode["reason"]


def test_an_empty_reason_is_not_silently_kept():
    """A reason that is present but empty is the failure this replaces."""
    assert trajectory._disposition_reason(
        {"disposition": "bound", "reason": "",
         "release_id": "acq-r1"}) != ""


def test_every_disposition_projects_a_non_empty_reason():
    """No disposition may reach the observation as an unstated outcome."""
    for disposition in ("bound", "rejected", "unavailable", "refused"):
        assert trajectory._disposition_reason(
            {"disposition": disposition}), disposition


def test_a_missing_disposition_is_still_stated():
    """An unrecorded disposition is itself a fact worth recording."""
    assert trajectory._disposition_reason({})


def test_the_policy_revision_observation_projects_through_the_helper():
    """Revert the call site and this fails even if the helper survives."""
    source = inspect.getsource(trajectory._construct_policy_revision)

    assert "_disposition_reason(episode)" in source
    assert 'episode.get("reason", "")' not in source


def test_the_archived_empty_reason_is_the_shape_this_replaces():
    """The archive is the counterexample, so read it rather than restate it."""
    record = json.loads(
        (EVIDENCE / "e0-run.json").read_text(encoding="utf-8"))
    revision = record["revision"]

    assert revision["disposition"] == "bound"
    assert revision["reason"] == ""
    assert trajectory._disposition_reason(
        {"disposition": revision["disposition"],
         "release_id": revision["release_id"]})
