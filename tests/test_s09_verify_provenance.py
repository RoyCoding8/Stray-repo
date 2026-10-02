"""S09R-03 provenance gate: the verifier must refuse a mislabelled run.

The live bundle in ``evidence_s09_m3_live`` is preserved byte for byte.
Its contamination is the evidence, so these tests read it and assert the
refusals rather than repairing it.

Two of the original allegations were measured and did not survive. A
use record's ``executed_source_digest`` is a method digest, not a policy
digest: the bound policy selects a method, so demanding the two match
would refuse every well-formed bundle. And a clean bundle built by the
same pilot is byte-identical to the live one in ``use_records``, so no
check over that field can separate them. The check that does separate
them is the persisted request model against the frozen one.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts import s09_verify as V

LIVE = ROOT / "evidence_s09_m3_live"
BUNDLE_FILES = ("freeze", "development", "construction", "assessment",
                "use_records", "operations", "accounting",
                "refusal_probes", "conformance_replay")

LIVE_MODEL = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
DOUBLED_MODEL = "recorded-double"
P1_BOUND = "b71a7f8f39ad1655555f0ac47ab2ab81321a78d98ac90f1079944fc626194706"
P0_AUTHORED = ("f92058cf6c0417f5f87e60ee544d608e9bdd604d6830fe7f0e9af3"
               "06d7a1ad0f")
ACQUIRED_METHOD = "3834317f66d4fb086d9e4cc93c36c0b08e4a108478dd26b776de" \
                  "66ea04c58685"


def _bundle(name: str = "evidence_s09_m3_live") -> dict:
    return {key: json.loads((ROOT / name / ("%s.json" % key)).read_text())
            for key in BUNDLE_FILES}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reasons(result: dict) -> set:
    return {finding["reason"] for finding in result["findings"]}


def _for(result: dict, reason: str) -> list:
    return sorted(f["subject"] for f in result["findings"]
                  if f["reason"] == reason)


def test_live_bundle_is_refused():
    result = V.verify_bundle(_bundle())
    assert result["status"] == "fail"


def test_live_freeze_declares_live_model():
    """The freeze under examination claims a live model."""
    freeze = json.loads((LIVE / "freeze.json").read_text())
    assert freeze["config"]["mode"] == "live"
    assert freeze["config"]["model"] == LIVE_MODEL


def test_construction_requests_name_the_doubled_model():
    """S09R-01: every persisted request was addressed elsewhere."""
    construction = json.loads((LIVE / "construction.json").read_text())
    models = {request["model"]
              for entry in construction.values()
              for request in entry["construction_requests"]}
    assert models == {DOUBLED_MODEL}
    assert DOUBLED_MODEL != LIVE_MODEL


def test_live_bundle_refuses_every_mismatched_request():
    result = V.verify_bundle(_bundle())
    assert _for(result, str(V.Finding.REQUEST_MODEL_NOT_FROZEN)) == [
        "P1#0", "P2#0", "P2#1"]


def test_request_mismatch_is_a_refusal_not_a_warning():
    """A mislabelled model must fail the bundle, not decorate it."""
    result = V.verify_bundle(_bundle())
    assert V.Finding.REQUEST_MODEL_NOT_FROZEN.severity() is V.Severity.REFUSAL
    assert any(problem.startswith(str(V.Finding.REQUEST_MODEL_NOT_FROZEN))
               for problem in result["problems"])


def test_matching_request_model_is_not_refused():
    """The same bundle passes once its requests name the frozen model."""
    result = V.verify_bundle(_clean_requests(_bundle()))
    assert _for(result, str(V.Finding.REQUEST_MODEL_NOT_FROZEN)) == []


def test_acquired_member_labelled_false_is_flagged():
    """The one 'acquired' method is an authored constant, per every arm."""
    result = V.verify_bundle(_bundle())
    assert _for(result, str(V.Finding.ACQUIRED_MEMBER_IS_AUTHORED)) == [
        "P0#0", "P0#1", "P1#0", "P1#1", "P2#0", "P2#1"]


def test_acquired_member_really_carries_the_false_label():
    freeze = json.loads((LIVE / "freeze.json").read_text())
    members = freeze["method_repertoires"]["P1"]["members"]
    assert [m["authored"] for m in members] == [False, False]
    assert {m["source_digest"] for m in members} == {ACQUIRED_METHOD}


def test_acquired_member_was_built_by_the_authored_control():
    """Not merely labelled wrong: its builder ran the P0 authored policy."""
    bundle = _bundle()
    campaigns = {e["campaign_id"]: e
                 for e in bundle["development"] + bundle["assessment"]}
    member = bundle["freeze"]["method_repertoires"]["P1"]["members"][0]
    builder = campaigns[member["construction"]["campaign_id"]]
    assert builder["executed_policy_digest"] == P0_AUTHORED


def test_authored_set_is_derived_from_the_bundle_not_hardcoded():
    """The check reads the freeze's own declaration of what is authored."""
    freeze = json.loads((LIVE / "freeze.json").read_text())
    assert freeze["policy_identities"]["P0"]["artifact"]["origin"] == \
        "authored-control"
    assert V._authored_digests(freeze) == {_sha(
        freeze["policy_identities"]["P0"]["source"])}
    assert _sha("") not in V._authored_digests(freeze)


def test_tampered_member_digest_fails_re_derivation():
    """A recorded digest that does not match its own bytes is refused."""
    bundle = _bundle()
    member = bundle["freeze"]["method_repertoires"]["P1"]["members"][0]
    member["source_digest"] = "0" * 64
    result = V.verify_bundle(bundle)
    assert _for(result, str(V.Finding.EXECUTED_SOURCE_MISMATCH)) == [
        "P1#0"]


def test_tampered_record_digest_fails_re_derivation():
    """Re-derivation is from the recorded bytes, not from the label."""
    bundle = _bundle()
    record = next(r for r in bundle["use_records"]
                  if r["executed_source"] not in ("", "incumbent"))
    record["executed_source_digest"] = "0" * 64
    result = V.verify_bundle(bundle)
    assert record["record_id"] in _for(
        result, str(V.Finding.EXECUTED_SOURCE_MISMATCH))


def _clean_requests(bundle: dict) -> dict:
    """The live bundle with its requests corrected to the frozen model.

    Everything else is untouched, so what a check reports here is what
    that check would say about a run whose model label is honest.
    """
    for entry in bundle["construction"].values():
        for request in entry["construction_requests"]:
            request["model"] = LIVE_MODEL
    return bundle


def test_control_arm_is_not_refused_for_having_no_bound_policy():
    """P0 and P2 legitimately run no bound policy of their own."""
    bundle = _clean_requests(_bundle())
    identities = bundle["freeze"]["policy_identities"]
    assert identities["P2"]["status"] == "unavailable"
    result = V.verify_bundle(bundle)
    assert not [f for f in result["findings"]
                if f["reason"] == str(V.Finding.EXECUTED_POLICY_NOT_BOUND)]


def test_p2_records_carry_no_policy_claim_at_all():
    """The unavailable arm's records claim nothing, so nothing is unproven."""
    bundle = _clean_requests(_bundle())
    result = V.verify_bundle(bundle)
    p2 = [f for f in result["findings"]
          if f["reason"] == str(V.Finding.POLICY_EXECUTION_UNPROVEN)
          and f["subject"].startswith("assess-P2")]
    assert p2 == []


def test_p0_records_are_claimed_but_uncorroborated():
    """P0 does name a policy, so its execution is the open question."""
    bundle = _clean_requests(_bundle())
    result = V.verify_bundle(bundle)
    unproven = [f for f in result["findings"]
                if f["reason"] == str(V.Finding.POLICY_EXECUTION_UNPROVEN)
                and f["subject"].startswith("assess-P0")]
    assert len(unproven) == 8


def test_unproven_execution_is_reported_without_failing():
    """No persisted observed list means unknown, not pass and not fail."""
    result = V.verify_bundle(_bundle())
    reasons = _for(result, str(V.Finding.POLICY_EXECUTION_UNPROVEN))
    assert len(reasons) == 16
    severities = {f["severity"] for f in result["findings"]
                  if f["reason"] == str(V.Finding.POLICY_EXECUTION_UNPROVEN)}
    assert severities == {str(V.Severity.UNPROVEN)}


def test_unproven_never_enters_the_problem_list():
    """An unknown is surfaced, not counted against the bundle."""
    result = V.verify_bundle(_bundle())
    assert not [p for p in result["problems"]
                if p.startswith(str(V.Finding.POLICY_EXECUTION_UNPROVEN))]


def test_observed_list_corroborates_the_claimed_policy():
    """A persisted observed list containing the scalar proves execution."""
    bundle = _bundle()
    claimed = next(r for r in bundle["use_records"]
                   if r["executed_policy_digest"])
    claimed["executed_policy_digests"] = [claimed["executed_policy_digest"]]
    result = V.verify_bundle(bundle)
    assert claimed["record_id"] not in _for(
        result, str(V.Finding.POLICY_EXECUTION_UNPROVEN))


def test_observed_list_contradicting_the_claim_is_a_refusal():
    bundle = _bundle()
    record = next(r for r in bundle["use_records"]
                  if r["executed_policy_digest"])
    record["executed_policy_digests"] = ["f" * 64]
    result = V.verify_bundle(bundle)
    assert record["record_id"] in _for(
        result, str(V.Finding.EXECUTED_POLICY_NOT_BOUND))


def test_executed_source_digest_is_a_method_not_the_bound_policy():
    """Why no check demands the method equal the bound policy.

    Every arm's repertoire is the same development table, so a method
    digest that matched a bound policy could not be a test of anything.
    """
    bundle = _bundle()
    digests = {r["executed_source_digest"] for r in bundle["use_records"]}
    assert ACQUIRED_METHOD in digests
    assert P1_BOUND not in digests
    assert P0_AUTHORED not in digests


def test_clean_bundle_also_carries_the_mislabelled_member():
    """A clean doubles run has the same repertoire and reports it the same way.

    The member labelled authored false was built by a dev campaign running the
    P0 authored control, and every arm shares that repertoire, so this is a
    property of the study design rather than of the live run. It is reported
    as UNPROVEN and never as a refusal, so a clean bundle still verifies while
    a reviewer still sees the gap. The test pins the severity so nobody
    promotes it back into a failure or deletes it.
    """
    result = V.verify_bundle(_clean_requests(_bundle()))
    assert result["status"] == "pass"
    assert result["problems"] == []
    assert _for(result, str(V.Finding.ACQUIRED_MEMBER_IS_AUTHORED)) == [
        "P0#0", "P0#1", "P1#0", "P1#1", "P2#0", "P2#1"]
    assert _for(result, str(V.Finding.REQUEST_MODEL_NOT_FROZEN)) == []
    assert V.Finding.ACQUIRED_MEMBER_IS_AUTHORED.severity() is V.Severity.UNPROVEN


def test_findings_expose_a_branchable_reason_and_severity():
    result = V.verify_bundle(_bundle())
    for finding in result["findings"]:
        assert finding["reason"] in set(V.Finding)
        assert finding["severity"] in set(V.Severity)


def test_legacy_problem_strings_are_unchanged_for_old_reasons():
    """A caller parsing the old strings still sees the old reasons."""
    result = V.verify_bundle(_bundle())
    assert not [p for p in result["problems"]
                if p.startswith("freeze-incomplete")
                or p.startswith("missing-use-record")]


def test_the_old_bundle_is_untouched():
    """The evidence must survive the gate that reads it."""
    tracked = subprocess_git_status()
    assert not [line for line in tracked if "evidence_s09_m3_live" in line]


def subprocess_git_status() -> list:
    import subprocess
    out = subprocess.run(["git", "status", "--porcelain", "--",
                          "evidence_s09_m3_live"],
                         cwd=str(ROOT), capture_output=True, text=True,
                         timeout=60)
    return [line for line in out.stdout.splitlines() if line.strip()]
