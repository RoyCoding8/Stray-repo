"""A campaign id the system mints must be resumable, in either shape.

`campaign_id` appends a namespace token, so it mints `ad01-w0-I-<n>-<token>`.
`resume_campaign` parsed exactly four parts, so every tokenized id was
write-only: a study run through the pilot could not be resumed through the
CLI, which is the one production caller of this path.

Both shapes are live ids, so both must parse. A parser that accepts only one
of them makes ids the system itself produces unresumable, which is how this
defect survived the namespace change.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import trajectory


def test_a_plain_campaign_id_parses():
    assert trajectory._parse_campaign_id("ad01-w0-I-51") == (0, "I", 51, "")


def test_a_tokenized_campaign_id_parses_with_its_token():
    assert trajectory._parse_campaign_id("ad01-w0-I-51-pe") == (0, "I", 51, "pe")


def test_the_parser_reads_back_exactly_what_campaign_id_mints():
    """Round-trip, which is the property that was broken."""
    for token in ("", "pe", "m5a", "tok-9"):
        cid = trajectory.campaign_id(1, "R", 7, token)
        world, arm, seq, read_back = trajectory._parse_campaign_id(cid)

        assert (world, arm, seq) == (1, "R", 7)
        assert read_back == token, cid


def test_a_malformed_id_is_still_refused():
    # `ad01-w0-I-51-a-b` is NOT malformed: a token may carry dashes, and the
    # parser takes everything after the sequence for exactly that reason.
    for bad in ("ad01-w0-X-51", "nope-w0-I-51", "ad01-wq-I-51",
                "ad01-w0-I-x", "ad01-w0-I", "w0-I-51"):
        try:
            trajectory._parse_campaign_id(bad)
        except ValueError:
            continue
        raise AssertionError("accepted a malformed id %r" % bad)


def test_resuming_repins_the_namespace_so_the_ids_match():
    """The failure mode was a resumed run building a different id.

    `resume_campaign` compares the id `run_campaign` returns against the one
    asked for. Without re-pinning the token from that id, a tokenized resume
    mints a different campaign and the comparison fails for a reason that has
    nothing to do with the resume.
    """
    original = trajectory.NAMESPACE_TOKEN
    try:
        trajectory.set_namespace_token("resume-me")
        cid = trajectory.campaign_id(0, "I", 51)
        trajectory.set_namespace_token("")
        assert trajectory.campaign_id(0, "I", 51) != cid, (
            "the token is what separates the two, so the premise holds")

        _world, _arm, _seq, token = trajectory._parse_campaign_id(cid)
        trajectory.set_namespace_token(token)
        assert trajectory.campaign_id(0, "I", 51) == cid
    finally:
        trajectory.set_namespace_token(original)
