"""Two runs must never mint the same operation id.

The reuse branch in `construct._settled_text` looks a receipt up by operation
id before dispatching, and returns it if one is settled. That is correct for a
genuine retry within one run. It is a defect when two different runs produce
the same id, because the second run then reports the first run's response as
its own. That is exactly how a freeze declaring a live model persisted
`model: "recorded-double"`.

The property is two-sided and both halves are pinned here: different runs must
differ, and a retry within one run must still find its own earlier receipt.
A test that only proves the first would pass against a scheme that simply
randomises every call, which would break the retry it is meant to preserve.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import trajectory
from scripts import s09_pilot as pilot

TOKEN_A = "alpha01"
TOKEN_B = "bravo02"


def test_a_run_without_a_token_is_refused():
    """The token is mandatory, not defaulted.

    Defaulting it would preserve exactly the collision this removes, and the
    caller would never know.
    """
    for empty in ("", "   ", "///"):
        try:
            pilot.study_identity(empty)
        except ValueError as exc:
            assert "namespace token" in str(exc)
        else:
            raise AssertionError("token %r was accepted" % empty)


def test_two_runs_get_distinct_study_roots():
    first = pilot.study_identity(TOKEN_A)
    second = pilot.study_identity(TOKEN_B)

    assert first[0] != second[0]
    assert first[1] != second[1]
    assert first[1] == "%s-%s" % (pilot.STUDY_ROOT, TOKEN_A)
    assert first[1].startswith("s09-m5-pilot-")


def test_two_runs_get_distinct_campaign_ids():
    first = trajectory.campaign_id(0, "I", 54, TOKEN_A)
    second = trajectory.campaign_id(0, "I", 54, TOKEN_B)

    assert first != second
    assert first == "ad01-w0-I-54-%s" % TOKEN_A


def test_the_token_is_a_suffix_so_prefix_matching_still_works():
    """Many call sites match on `ad01-`, so a prefix token would break them."""
    namespaced = trajectory.campaign_id(0, "I", 54, TOKEN_A)

    assert namespaced.startswith("ad01-")
    assert namespaced.split("-alpha01")[0] == "ad01-w0-I-54"


def test_operation_ids_inherit_the_campaign_token():
    """The property that matters: the id a receipt is looked up by differs."""
    base_a = trajectory._alloc_id(trajectory.campaign_id(0, "I", 54, TOKEN_A))
    base_b = trajectory._alloc_id(trajectory.campaign_id(0, "I", 54, TOKEN_B))

    assert base_a != base_b
    assert base_a.endswith(TOKEN_A)
    assert base_b.endswith(TOKEN_B)


def test_a_retry_within_one_run_still_finds_its_own_receipt():
    """Same token, same call, same id. The reuse branch must keep working."""
    first = trajectory.campaign_id(0, "I", 54, TOKEN_A)
    retry = trajectory.campaign_id(0, "I", 54, TOKEN_A)

    assert first == retry, "a retry inside one run must be a stable id"


def test_the_token_is_sanitised_into_an_id_safe_form():
    hostile = "a/b;c d"

    study_id, root = pilot.study_identity(hostile)

    assert "/" not in root and ";" not in root and " " not in root
    assert study_id.endswith("-abcd")
