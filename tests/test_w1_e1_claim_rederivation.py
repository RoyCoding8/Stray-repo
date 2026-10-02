"""The campaign verifier must not believe a record's own explanations.

A lineage record mixes observations and claims. The route, `stop_reason`,
the usage snapshot and the HTTP status are observations: they are the
gateway event, and nothing offline can re-derive them. The taxonomy
`outcome`, the `reason` prose, `candidate_digest`, `score` and `attempt`
are claims about those bytes, and a claim is a string anyone can write.

Before this file's subject was fixed, `verify_preflight_record` attested
an `invalid-program` by a disjunction -- "the bytes do not match the
dispatch, or they do not parse". A record holding 144 bytes and a reason
reading "response of 5211 characters exceeds the frozen limit of 512"
satisfied it. Four escalating forgeries were caught by four distinct
checks; that was the fifth, and it was the one that mattered.

Each test here builds a forgery the shape a motivated reader would build,
seals the digest chain over it so the chain cannot be what catches it, and
requires a failure naming the claim that does not re-derive. No gateway is
reached and no model is called.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import frontier  # noqa: E402
from experiments.ad01 import live_construct as live  # noqa: E402
from experiments.ad01 import w1_e1_campaign_r2 as r2  # noqa: E402

EVIDENCE = ROOT / "reports" / "evidence" / r2.CAMPAIGN_ID

# Short, and a schema failure rather than a length failure. The two
# together are the reviewer's forgery: the bytes are well under the 512
# limit and do not parse, so the old disjunction held, while the reason
# they carried was a length fact about 5211 bytes. The exact payload is
# not the reviewer's, and does not need to be; the shape is the point.
SHORT_UNPARSEABLE = (
    '{"specs": [{"const": 0, "mask": 99, "pair": null}, '
    '{"const": 0, "mask": 0, "pair": null}, '
    '{"const": 0, "mask": 0, "pair": null}, '
    '{"const": 0, "mask": 0, "pair": null}]}')


def _copy_run(root: Path, tmp_path: Path) -> Path:
    if not (EVIDENCE / "campaign.json").exists():
        pytest.skip("%s has not been run in this checkout" % r2.CAMPAIGN_ID)
    copy = tmp_path / "forged"
    shutil.copytree(EVIDENCE, copy)
    return copy


def _over_length_lineage(root: Path) -> Path:
    """The answered lineage whose reason is the frozen-limit one."""
    for path in sorted((root / "lineages").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not record.get("offline_verified"):
            continue
        if "exceeds the frozen limit" in str(
                record["attempts"][0].get("reason")):
            return path
    raise AssertionError("no over-length lineage in %s" % root)


def _seal(record: dict) -> dict:
    """Recompute every digest that covers the forged bytes.

    A forgery caught by its own arithmetic demonstrates nothing about
    whether a claim is re-derived. This pays the whole digest-chain cost
    -- response digest, result digest, raw payload digest, identity
    digest -- so the only thing left that can catch the forgery is the
    re-derivation of a claim from the bytes beside it.
    """
    for entry in record.get("attempts", []):
        dispatch = entry.get("dispatch")
        if not isinstance(dispatch, dict):
            continue
        raw = entry.get("raw_response")
        dispatch["raw_response"] = raw
        details = dispatch.get("details")
        if isinstance(details, dict) and isinstance(
                details.get("raw_payload"), dict):
            details["raw_payload"]["raw_response"] = raw
        if raw is not None:
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            dispatch["response_digest"] = digest
            dispatch["result_digest"] = digest
        dispatch["raw_payload_digest"] = frontier._digest_text(
            frontier.canonical(
                (dispatch.get("details") or {}).get("raw_payload")))
        dispatch["route_digest"] = frontier._digest_text(
            frontier.canonical((dispatch.get("details") or {}).get("route")))
        dispatch["evidence_digest"] = frontier._evidence_identity_digest(
            dispatch)
    return record


def _write(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, sort_keys=True, indent=1),
                    encoding="utf-8")


def test_a_reason_that_describes_bytes_the_record_does_not_hold_is_refused(
        tmp_path: Path) -> None:
    root = _copy_run(EVIDENCE, tmp_path)
    path = _over_length_lineage(root)
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["attempts"][0]
    original = entry["raw_response"]
    assert len(original) > live.OUTPUT_LIMITS["max_response_characters"]

    entry["raw_response"] = SHORT_UNPARSEABLE
    _seal(record)
    _write(path, record)

    # The chain is now internally consistent: it is a record whose own
    # digests all agree about the short bytes it holds.
    assert len(SHORT_UNPARSEABLE) < live.OUTPUT_LIMITS[
        "max_response_characters"]
    failures = [f for f in r2.verify(root)["failures"]
                if f["record"] == path.name]
    assert failures, "a reason that contradicts the stored bytes must fail"
    assert "reason" in failures[0]["error"], failures[0]["error"]
    # And it must fail on the claim, not on the arithmetic.
    assert "digest" not in failures[0]["error"], failures[0]["error"]


def test_a_forged_score_and_candidate_digest_are_refused(
        tmp_path: Path) -> None:
    """Turn a lineage that produced nothing into an acquisition.

    This is the forgery the E1 r2 handback is most exposed to. The
    campaign's central negative is 8 records with 0 programs, and a
    candidate digest written into an entry is the one edit that turns
    that into 1 program and a perfect score without touching a single
    byte the gateway sent.
    """
    root = _copy_run(EVIDENCE, tmp_path)
    path = _over_length_lineage(root)
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["attempts"][0]
    entry["candidate_digest"] = live.source_digest('{"specs": []}')
    entry["score"] = {"overall": 1.0}
    _write(path, record)

    failures = [f for f in r2.verify(root)["failures"]
                if f["record"] == path.name]
    assert failures, "a forged candidate digest must fail"
    assert "candidate_digest" in failures[0]["error"], failures[0]["error"]


def test_a_verdict_that_restates_a_gateway_observation_is_refused(
        tmp_path: Path) -> None:
    """Restate `stop_reason: length` as `stop`, with the bytes untouched.

    `stop_reason` is an observation, so the verifier's job is not to
    re-derive it but to refuse a record whose narrative column disagrees
    with its own dispatch evidence. The verdict is a copy of the
    attempt's claims plus the dispatch's observations, so re-deriving it
    whole is what catches a restatement.
    """
    root = _copy_run(EVIDENCE, tmp_path)
    path = _over_length_lineage(root)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["verdict"]["stop_reason"] == "length"
    record["verdict"]["stop_reason"] = "stop"
    _write(path, record)

    failures = [f for f in r2.verify(root)["failures"]
                if f["record"] == path.name]
    assert failures, "a restated observation must fail"
    assert "stop_reason" in failures[0]["error"], failures[0]["error"]


def test_an_over_length_reply_relabelled_a_route_refusal_is_refused(
        tmp_path: Path) -> None:
    """Say the repair failed, on a record that proves it held.

    The batch's claim is `route_error: None` on every answered dispatch,
    so relabelling an over-length `invalid-program` as a `route-refusal`
    is the forgery that would make the E1 result a harness fact again.
    The bytes are untouched, so only re-deriving `outcome` catches it.
    """
    root = _copy_run(EVIDENCE, tmp_path)
    path = _over_length_lineage(root)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["attempts"][0]["dispatch"].get("route_error") is None
    entry = record["attempts"][0]
    entry["outcome"] = "route-refusal"
    entry["reason"] = "returned route metadata does not match the frozen route"
    record["verdict"]["outcome"] = "route-refusal"
    record["verdict"]["reason"] = entry["reason"]
    _write(path, record)

    failures = [f for f in r2.verify(root)["failures"]
                if f["record"] == path.name]
    assert failures, "a relabelled outcome must fail"
    assert "outcome" in failures[0]["error"], failures[0]["error"]


def test_a_second_attempt_claimed_for_a_campaign_that_spent_one_is_refused(
        tmp_path: Path) -> None:
    """The unspent repair allowance, spent on paper.

    The protocol supports `attempt in (1, 2)` and the freeze recorded
    `repairs_planned: 0`, so the cheapest next measurement in the E1 r2
    result is whether a second attempt constructs. A record that claims
    the second attempt ran is claiming a dispatch the exposure ledger
    says was never made. `attempt` is in the entry and in the verdict and
    nowhere in the dispatch evidence, so it re-derives from the operation
    identity, which ends `-a1`.
    """
    root = _copy_run(EVIDENCE, tmp_path)
    path = _over_length_lineage(root)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["attempts"][0]["attempt"] = 2
    record["verdict"]["attempt"] = 2
    _write(path, record)

    failures = [f for f in r2.verify(root)["failures"]
                if f["record"] == path.name]
    assert failures, "a claimed second attempt must fail"
    assert "attempt" in failures[0]["error"], failures[0]["error"]


def test_the_untouched_run_still_verifies_every_record(tmp_path: Path) -> None:
    """The fix must not make the real campaign unverifiable.

    A re-derivation that rejects the genuine records has replaced a gap
    with a different one, so the baseline is asserted with the same
    severity as each forgery.
    """
    root = _copy_run(EVIDENCE, tmp_path)
    outcome = r2.verify(root)
    assert outcome["failures"] == [], outcome["failures"]
    assert outcome["checked"] == r2.LINEAGE_COUNT * len(r2.TREATMENTS)
    assert outcome["passed"] == outcome["checked"]


def test_every_claim_a_record_makes_re_derives_from_its_own_bytes() -> None:
    """Walk the real records and re-derive each claim individually.

    The five forgeries above each move one claim. This walks all eight
    genuine lineages through the same ladder and asserts every claim
    matches, so a future change to the ladder that silently alters a
    reason string fails here rather than in a reader's face.
    """
    if not (EVIDENCE / "campaign.json").exists():
        pytest.skip("%s has not been run in this checkout" % r2.CAMPAIGN_ID)
    _, session = r2._frozen_task()
    seen = 0
    for path in sorted((EVIDENCE / "lineages").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        for entry in record["attempts"]:
            decided = live.preflight_claims_agree(entry, session=session)
            assert entry["outcome"] == decided["outcome"]
            assert entry["reason"] == decided["reason"]
            assert entry["candidate_digest"] == decided["candidate_digest"]
            assert entry["score"] == decided["score"]
            assert entry["attempt"] == live.output_operation_attempt(
                entry["operation_id"])
            seen += 1
    assert seen == r2.LINEAGE_COUNT * len(r2.TREATMENTS)


def test_the_reason_is_derived_from_the_bytes_and_not_the_other_way_round(
        tmp_path: Path) -> None:
    """`summarize` must not read a length off the reason string.

    The results table prints `response_characters` beside `stop_reason`,
    and the over-length finding names both. If the count came from the
    reason, a forged reason would silently become a forged measurement in
    the campaign summary, which is the artifact the handback cites.
    """
    root = _copy_run(EVIDENCE, tmp_path)
    path = _over_length_lineage(root)
    record = json.loads(path.read_text(encoding="utf-8"))
    entry = record["attempts"][0]
    entry["raw_response"] = SHORT_UNPARSEABLE
    _seal(record)
    _write(path, record)

    summary = r2.summarize(root)
    lineage = next(v for cell in summary["cells"] for v in cell["verdicts"]
                   if v["lineage"] == record["lineage"])
    # What the summary reports is what the bytes say, and the verdict
    # still fails, so the two cannot drift apart in the artifact either.
    assert lineage["response_characters"] == len(SHORT_UNPARSEABLE)
    assert lineage["invalid_program_defect"] == "would-not-parse"
    failures = [f for f in r2.verify(root)["failures"]
                if f["record"] == path.name]
    assert failures
