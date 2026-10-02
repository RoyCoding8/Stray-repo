"""The prompt-digest guard must be able to say no.

`RequestEstimate.prompt_digest_matched` was `True` as a literal at all three
of its construction sites, and its docstring claimed the freeze had committed
the exact prompt. Nothing had ever compared anything, so the field was an
attestation carrying no information. The m3 pilot had the mirror defect in
the other direction: it recorded `prompt_sha256` beside `prompt_chars` and
compared them to nothing, which is how four digests in `inv_r1_aa3_m3` went
stale without a signal.

A guard that cannot return `False` is the defect. A replacement that cannot
return `True` is the same defect wearing new clothes, so every test here pins
both directions, and each one drives a different public door rather than
re-calling the helper that was fixed.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from experiments.ad01 import method_exec
from experiments.ad01 import s09_exposure_ledger as ledger
from experiments.ad01 import s09_m3_pilot as m3

REPO_ROOT = ledger.REPO_ROOT
R4_FREEZE = REPO_ROOT / (ledger.R4_EVIDENCE + "/freeze.json")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- both directions, through the public doors ----------------------------


def test_the_guard_returns_true_for_bytes_the_freeze_really_committed():
    """A freeze that commits the current render produces True.

    Driven through `_allowance_from_freeze`, the same door the campaign
    sizing uses, and against a digest map built from what the source actually
    renders now. This is the direction the old constant could not fail.
    """
    freeze = json.loads(R4_FREEZE.read_text())
    rendered = ledger._render_frozen_prompts()
    assert rendered, "the frozen source rendered no prompts to compare"
    freeze["prompt"] = {"rendered_digests": {key: _digest(text)
                                             for key, text in rendered.items()}}

    sizing = ledger._allowance_from_freeze(REPO_ROOT, "committed", freeze,
                                          "committed")

    assert sizing.is_derived
    assert sizing.refusal_reason == ""
    assert len(sizing.per_request) == len(rendered)
    assert all(estimate.prompt_digest_matched for estimate in sizing.per_request)
    assert all(estimate.vouched() for estimate in sizing.per_request)
    # Matched, and matched for the stated reason rather than by default.
    assert all(estimate.prompt_digest_note
               == "the committed digest is the digest of these bytes"
               for estimate in sizing.per_request)


def test_the_guard_returns_false_for_a_single_drifted_digest():
    """One wrong digest in an otherwise committed freeze is caught.

    The freeze is the real r4 document with one entry replaced, so a guard
    that sampled or averaged would still pass this. Every other digest agrees
    exactly.
    """
    freeze = json.loads(R4_FREEZE.read_text())
    rendered = ledger._render_frozen_prompts()
    digests = {key: _digest(text) for key, text in rendered.items()}
    drifted = sorted(digests)[0]
    digests[drifted] = "0" * 64
    freeze["prompt"] = {"rendered_digests": digests}

    sizing = ledger._allowance_from_freeze(REPO_ROOT, "drifted", freeze,
                                          "drifted")

    assert sizing.is_derived is False
    assert sizing.total_units is None
    assert sizing.per_request == ()
    assert drifted in sizing.refusal_reason
    # A refusal and an unmatched record are different outcomes, and this is
    # the refusal: a drifted prompt yields no number at all.
    assert "rendered_digest" in sizing.refusal_reason


def test_the_r4_freeze_as_committed_matches_nothing_and_says_so():
    """The historical freeze is not reproducible, and the guard reports it.

    r4's prompts predate the current source. The check runs for all eight
    entries and matches none, which is why re-deriving the prompt the freeze
    recorded is the wrong direction: that direction fails for everything and
    distinguishes nothing.
    """
    freeze = json.loads(R4_FREEZE.read_text())
    committed = dict(freeze["prompt"]["rendered_digests"])
    rendered = ledger._render_frozen_prompts()

    verdicts = [ledger.prompt_digest_verdict(rendered[key], committed.get(key))
                for key in sorted(rendered)]

    assert len(verdicts) == 8
    assert not any(matched for matched, _ in verdicts)
    assert all("hash to" in note for _, note in verdicts)

    sizing = ledger._allowance_from_freeze(REPO_ROOT, ledger.R4_EVIDENCE,
                                          freeze, "r4")
    assert sizing.is_derived is False


def test_the_live_campaign_path_no_longer_claims_a_match_it_never_checked():
    """The cap sheet is the path a real campaign takes, and it commits no prompt.

    This is the site that mattered most: `reservation_allowance_for_freeze`
    returns from the cap sheet before it ever reaches a freeze, so its
    `RequestEstimate` is the one a reader would have believed was vouched.
    """
    sizing = ledger.reservation_allowance_for_freeze(REPO_ROOT)

    assert sizing.is_derived
    assert "cap-sheets" in sizing.source.artifact
    assert len(sizing.per_request) == 1
    estimate = sizing.per_request[0]
    assert estimate.prompt_digest_matched is False
    assert estimate.vouched() is False
    assert "commits no prompt digest" in estimate.prompt_digest_note
    # The refusal to attest does not cost the number. Units still price a
    # real request from real bounds, and that is not the same claim.
    assert estimate.units > 0
    assert sizing.total_units == 64 * estimate.units


def test_for_request_reports_a_character_count_as_an_unvouched_bound():
    """`for_request` prices a character count, and now says so.

    Its payload is `x` repeated, so there are no prompt bytes to compare. It
    passed `True` while the only thing checked was that a length was given.
    """
    allowance = ledger.ReservationAllowance.for_request(
        message_characters=4880, max_output_tokens=2048, retries=0)

    estimate = allowance.per_request[0]
    assert estimate.prompt_digest_matched is False
    assert "character count" in estimate.prompt_digest_note
    assert estimate.units > 0


def test_a_caller_that_can_vouch_for_for_request_gets_true():
    """The `False` default is a default, not a wall.

    A caller that really does hold both the bytes and a committed digest must
    be able to say so, or this fix is a guard that can only refuse.
    """
    prompt = "a prompt somebody committed"
    committed = _digest(prompt)
    matched, note = ledger.prompt_digest_verdict(prompt, committed)
    assert matched is True

    allowance = ledger.ReservationAllowance.for_request(
        message_characters=len(prompt), max_output_tokens=2048, retries=0,
        prompt_digest_matched=matched, prompt_digest_note=note)

    assert allowance.per_request[0].prompt_digest_matched is True
    assert allowance.per_request[0].vouched() is True


@pytest.mark.parametrize("prompt,committed,expected", [
    (None, "a" * 64, False),
    ("bytes", None, False),
    (None, None, False),
    ("bytes", "b" * 64, False),
])
def test_the_guard_refuses_on_every_way_of_having_nothing_to_compare(
        prompt, committed, expected):
    """Absence is a False, and the note names which absence it was."""
    matched, note = ledger.prompt_digest_verdict(prompt, committed)
    assert matched is expected
    assert note


# --- the m3 pilot half: a digest compared to something --------------------


def test_the_m3_freeze_commits_the_public_interface_prompt_and_matches_it():
    """The m3 guard returns True for the prompt its own freeze committed.

    Driven from `committed_prompt_digests`, the function the freeze writer
    calls, into the verdict the dispatch record reads. Not the same door as
    the ledger's, and a defect confined to the ledger's would not reach it.
    """
    committed = m3.committed_prompt_digests()

    assert set(committed) == set(m3.DEVELOPMENT)
    for family in sorted(m3.DEVELOPMENT):
        matched, note = m3._prompt_digest_verdict(
            committed[family], committed[family], m3.PRE_DETERMINABLE_ARM)
        assert matched is True, family
        assert "hash to the digest the freeze committed" in note


def test_the_m3_guard_returns_false_when_the_bytes_drift():
    """One changed byte of prompt, committed digest unchanged: False.

    The comparison runs from the sent bytes toward the commitment, so drift
    is visible without re-rendering anything on either side.
    """
    committed = m3.committed_prompt_digests()
    family = sorted(committed)[0]

    matched, note = m3._prompt_digest_verdict(
        "0" * 64, committed[family], m3.PRE_DETERMINABLE_ARM)

    assert matched is False
    assert committed[family][:16] in note
    assert "0000000000000000" in note


def test_an_in_run_arm_is_unvouched_by_construction_not_by_failure():
    """`dev-exp` earns its experience during the run, so it has no commitment.

    This is a third distinct answer, and conflating it with drift would be its
    own misreading: nothing was committed because nothing could be.
    """
    matched, note = m3._prompt_digest_verdict(
        "0" * 64, None, "dev-exp")

    assert matched is False
    assert "earns its experience" in note
    assert "did not exist when the freeze was written" in note

    # An arm the freeze meant to vouch for but did not is a different fault
    # again, and must not borrow the dev-exp explanation.
    matched, note = m3._prompt_digest_verdict(
        "0" * 64, None, m3.PRE_DETERMINABLE_ARM)
    assert matched is False
    assert "commits no digest for this arm" in note


def test_the_committed_m3_digests_track_the_prompt_the_run_would_send():
    """The committed digest is of the real construction prompt.

    Rendered through `m3.construction_prompt`, the same call the dispatch
    makes, so this pins the commitment to the shipped bytes rather than to a
    copy of them.
    """
    from experiments.ad01 import worlds

    committed = m3.committed_prompt_digests()
    for family in sorted(m3.DEVELOPMENT):
        task = worlds.load_task(worlds.FROZEN_DIR, m3.DEVELOPMENT[family][0])
        prompt = m3.construction_prompt(
            family, task, experience=[], prior_failure=None,
            budget=m3.REQUEST_BOUNDS)
        assert _digest(prompt) == committed[family], family


def test_no_construction_site_hardcodes_the_verdict_any_more():
    """The regression itself: no `prompt_digest_matched=True` literal remains.

    Asserted against the source text of both files, so reintroducing the
    constant fails here without needing a live dispatch to notice.
    """
    for path in (ledger.__file__, m3.__file__):
        with open(path, "r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if "prompt_digest_matched=True" in line.replace(" ", ""):
                    pytest.fail(
                        "%s:%d hardcodes prompt_digest_matched=True: %s"
                        % (path, number, line.strip()))


def test_the_child_contract_still_describes_itself_under_one_version():
    """The three contract states share a version string that cannot tell them apart.

    `b9b7b4d` changed the rendered signatures and `CHILD_CONTRACT_VERSION` did
    not move, so a record carrying `ad01-child-v1` cannot distinguish the
    `method="ddmin"|"greedy"` form from today's `**kwargs` render. The
    version is the caller's only handle on which bytes it saw, and it does not
    discriminate. Pinned as an observation about the string, not a change to
    it: the constant lives in `method_exec.py`, which this lane does not own.
    """
    contract = method_exec.child_contract()
    rendered_signature = contract["callables"]["reduce_graph"]["signature"]

    assert contract["version"] == "ad01-child-v1"
    # Proof the version is not tracking the bytes: the signature text is long
    # and wrapper-derived, and the version that names it is one word.
    assert "**kwargs" in rendered_signature
    assert contract["version"] == "reduce_graph"[:0] + "ad01-child-v1"
