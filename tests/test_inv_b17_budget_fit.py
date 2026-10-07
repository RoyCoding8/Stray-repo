"""B17 — the budget-fit gate.

Every assertion is a LITERAL read out of this lane's own
`reports/evidence/invr1b17-budgetfit/budget-fit.json` and
`store-rows.json`, never a value recomputed from the driver that wrote
them. A test that passes when the artifact says something else is not a
gate.

The claims being asserted:

* the route is the pinned FREE model and the send count is within the
  19 B12 left unspent;
* no response at or over the served budget was recorded as a complete
  artifact — the load-bearing negative of this lane;
* unknown usage stayed unknown rather than becoming a zero;
* the scan detects a planted canary. CI does not claim the author's live
  credential was present or inspected.

The tamper tests at the end exist because a green gate proves nothing on
its own. Each one breaks one artifact field and asserts the gate that
should catch it does.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVIDENCE = REPO_ROOT / "reports/evidence/invr1b17-budgetfit"
ARTIFACT = EVIDENCE / "budget-fit.json"
STORE_ROWS = EVIDENCE / "store-rows.json"


def artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def store_rows() -> dict:
    return json.loads(STORE_ROWS.read_text(encoding="utf-8"))


# --- the route and the ceiling --------------------------------------------

def test_route_is_the_pinned_free_model():
    assert artifact()["route"]["requested_model"] == (
        "nvidia/nemotron-3-ultra-550b-a55b:free")


def test_model_id_ends_in_free():
    assert artifact()["model_id_ends_free"] is True
    assert artifact()["route"]["requested_model"].endswith(":free")


def test_budget_is_the_measured_served_budget_not_a_bigger_one():
    # B11 measured 2048 serving and 4096 lost. This lane asks what fits
    # inside 2048, so a larger number here would make the whole study
    # about a rung B11 showed is unavailable.
    assert artifact()["max_output_tokens"] == 2048
    assert artifact()["deadline_ms"] == 300000


def test_sends_are_within_the_inherited_ceiling():
    authorisation = artifact()["authorisation"]
    assert authorisation["authorised_physical_sends"] == 19
    assert authorisation["physical_sends_used"] <= 19
    assert authorisation["within_ceiling"] is True


def test_store_operation_count_matches_the_recorded_spend():
    rows = store_rows()
    counted = [row for row in rows["operations"]
               if row["allocation_id"] == "invr1b17-budget-fit-construction"]
    assert artifact()["authorisation"]["physical_sends_used"] == len(counted)
    assert len(counted) <= 19


# --- the load-bearing negative --------------------------------------------

def test_no_response_at_or_over_the_budget_is_a_complete_artifact():
    """No row claims a complete artifact from a budget-exhausted response.

    This is the gate for the finding itself. A response that stopped at
    `stop_reason: length` is a fragment; recording one as a complete
    artifact would be the exact error this lane exists to prevent, and the
    gate names every such row rather than counting them.
    """
    at_budget = []
    for row in artifact()["live_rows"]:
        analysis = row.get("analysis") or {}
        if analysis.get("stop_reason") != "length":
            continue
        at_budget.append(row["operation_id"])
        assert row.get("gate", {}).get("admitted") is not True, (
            "%s stopped at the budget and must not be recorded as a "
            "complete artifact" % row["operation_id"])
        assert analysis["opened_a_step_definition"] is False, (
            "%s stopped at the budget and claims a STEP definition" %
            row["operation_id"])
    assert len(at_budget) == artifact()["responses_ending_at_the_budget"]
    assert artifact()["responses_ending_at_the_budget"] >= 1, (
        "the finding needs at least one response that reached the budget")


def test_no_response_opened_a_step_definition():
    assert artifact()["responses_opening_a_step_definition"] == 0


def test_responses_that_arrived_are_counted_and_measured():
    assert artifact()["responses_returned"] == 2
    for row in artifact()["live_rows"]:
        if row.get("kind") != "text":
            continue
        analysis = row["analysis"]
        assert analysis["characters"] > 0
        assert analysis["stop_reason"] == "length"
        assert analysis["budget"] == 2048


def test_the_compact_witness_fits_the_budget_and_the_b12_cap():
    """(c) is false because a repairing artifact FITS. Assert it fits."""
    compact = artifact()["offline_measurements"]["compact_repairing_policy"]
    assert compact["characters"] == 5551
    assert compact["passes_b12_acceptance_limit"] is True
    assert compact["dev_repaired"] == 3
    assert compact["dev_instances"] == 9
    assert compact["model_calls"] == 0


def test_the_authored_control_is_admitted_by_the_frozen_loader():
    """(d) is false because the loader has no 7000 rule."""
    verdicts = artifact()["offline_measurements"]["loader_verdicts"]
    assert verdicts["authored_control"]["admitted"] is True
    assert verdicts["authored_control"]["characters"] == 22734
    assert verdicts["tiny_policy"]["characters"] == 115
    assert verdicts["tiny_policy"]["admitted"] is True
    assert verdicts["b12_acceptance_limit"] == 7000
    # B12 recorded the control as refused, and the refusal is real — it is
    # just not the loader's refusal.
    assert verdicts["recorded_by_b12"]["admitted"] is False
    assert verdicts["recorded_by_b12"]["defect"] == "over-length"


def test_the_verdict_is_a_not_b_c_not_d():
    verdict = artifact()["verdict"]
    assert verdict["a_prose_not_code"]["supported"] is True
    assert verdict["b_budget_truncated_a_completable_response"]["supported"] \
        is False
    assert verdict["c_protocol_asked_for_more_than_the_budget_carries"][
        "supported"] is False
    assert verdict["d_acceptance_limit_rejected_a_legitimate_artifact"][
        "supported"] is False


def test_b12_rows_are_marked_non_comparable():
    protocol = artifact()["protocol"]
    assert protocol["comparable_with_b12"] is False
    assert protocol["frozen_before_any_send"] is True
    for row in artifact()["live_rows"]:
        assert row["comparable_with_b12"] is False


def test_the_22734_is_not_recorded_as_a_response_length():
    """The misreading this lane exists to prevent, asserted against."""
    for row in artifact()["live_rows"]:
        analysis = row.get("analysis") or {}
        assert analysis.get("characters") != 22734


# --- honest accounting -----------------------------------------------------

def test_unknown_usage_stayed_unknown_on_every_row():
    for row in artifact()["live_rows"]:
        usage = row.get("usage") or {}
        assert usage["charge_units"] == "unknown", row["operation_id"]
        assert usage["charge_scale"] == "unknown", row["operation_id"]
        assert usage["billed"] == "unknown", row["operation_id"]
        assert usage["provider_enforced_ceiling"] == "unknown", \
            row["operation_id"]


def test_no_null_billing_was_written_as_zero():
    for row in store_rows()["receipts"]:
        usage = (row.get("content") or {}).get("usage") or {}
        for field in ("charge_units", "charge_scale", "billed",
                      "provider_enforced_ceiling"):
            assert usage.get(field) is None, (
                "%s.%s is null in the store; the artifact must carry "
                "'unknown' for it and the store must not carry a zero"
                % (row["operation_id"], field))


def test_the_lost_send_is_unresolved_and_not_a_failure():
    rows = {row["id"]: row for row in store_rows()["operations"]}
    lost = rows.get("probe-b17")
    if lost is not None:
        assert lost["settled"] is False
        assert lost["dispatch_state"] == "unresolved"
    receipts = {row["operation_id"]: row
                for row in store_rows()["receipts"]}
    if "probe-b17" in receipts:
        assert receipts["probe-b17"]["outcome"] == "unknown"


def test_failed_sends_are_failures_not_empty_responses():
    rows = artifact()["live_rows"]
    failed = [row for row in rows if "502" in str(row.get("reason", ""))]
    for row in failed:
        assert row.get("response_status") == 502
        assert row["kind"] != "text"


def test_no_sealed_value_reached_a_prompt():
    for row in artifact()["live_rows"]:
        assert row.get("sealed_values_not_in_prompt") == [], row["operation_id"]


# --- the credential scan, and proof that it can fail -----------------------

def test_the_credential_scan_reports_only_the_seeded_test_canary(monkeypatch):
    """CI uses a known test value; a worker secret is not required."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from experiments.ad01 import invr1b17_credential_scan as scan

    monkeypatch.setenv("SETTLEMENT_GATEWAY_KEY", scan.CANARY)
    value, source = scan.candidate_value()
    assert value == scan.CANARY
    assert source == "environment:SETTLEMENT_GATEWAY_KEY"
    written = scan.files_written()
    assert written
    assert scan.scan(value, written) == []


def test_the_credential_scan_is_non_vacuous():
    """The scan must FAIL on a planted value before it may report clean.

    B12's equivalent scan took a vacuous branch under WSL and passed while
    a planted credential sat in a file it had never read. This test is
    the fix: it plants a value the scan cannot miss and asserts the
    catch, then asserts the plant is gone.
    """
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from experiments.ad01 import invr1b17_credential_scan as scan

    result = scan.selfcheck()
    assert result["caught"] is True, (
        "planting %s was not caught; the scan cannot fail and its clean "
        "report means nothing" % result["planted_value"])
    assert result["files_with_planted_value"], result
    assert result["plant_removed"] is True


def test_the_scan_searches_every_environment_the_value_could_be_in():
    """A scan that reads one place is the defect B12 shipped."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from experiments.ad01 import invr1b17_credential_scan as scan

    source = Path(scan.__file__).read_text(encoding="utf-8")
    assert "SETTLEMENT_GATEWAY_KEY" in source
    assert "USERPROFILE" in source
    assert "/mnt/c/" in source, (
        "the Windows home is not searched, which is where the value lives "
        "when this lane runs outside WSL")
    assert "none" in source, (
        "the scan must be able to say it found nothing rather than "
        "passing quietly")


# --- tamper tests ----------------------------------------------------------

def check_no_budget_exhausted_response_is_complete(payload: dict) -> None:
    for row in payload["live_rows"]:
        analysis = row.get("analysis") or {}
        if analysis.get("stop_reason") != "length":
            continue
        assert row.get("gate", {}).get("admitted") is not True, \
            row["operation_id"]


def check_usage_is_unknown(payload: dict) -> None:
    for row in payload["live_rows"]:
        for field in ("charge_units", "charge_scale", "billed",
                      "provider_enforced_ceiling"):
            assert row["usage"][field] == "unknown", row["operation_id"]


def check_no_response_opened_a_step(payload: dict) -> None:
    assert payload["responses_opening_a_step_definition"] == 0


def check_budget_is_the_served_rung(payload: dict) -> None:
    assert payload["max_output_tokens"] == 2048


def check_within_ceiling(payload: dict) -> None:
    assert payload["authorisation"]["physical_sends_used"] <= 19


def check_non_comparable(payload: dict) -> None:
    assert payload["protocol"]["comparable_with_b12"] is False
    for row in payload["live_rows"]:
        assert row["comparable_with_b12"] is False


def check_no_sealed_leak(payload: dict) -> None:
    for row in payload["live_rows"]:
        assert row.get("sealed_values_not_in_prompt") == [], \
            row["operation_id"]


def check_no_opaque_value(text: str, allowed: set) -> None:
    """Reject long opaque runs, minus this lane's own field names.

    A JSON artifact is full of long snake_case KEYS, so the pattern has
    to tell a key from a value. A key sits in quotes before a colon; a
    value does not. Matching on the values alone keeps the check from
    flagging this lane's own vocabulary, which would make it noise rather
    than a gate.
    """
    keys = set(re.findall(r'"([A-Za-z0-9_\-]{40,})"\s*:', text))
    for match in re.findall(r"[A-Za-z0-9_\-]{40,}", text):
        if match in keys:
            continue
        assert match in allowed, (
            "an unexplained long opaque value is in the artifact: %s..."
            % match[:12])


def _tamper(mutate, check) -> None:
    """Break one field, then assert the matching check REJECTS it.

    A tamper test that asserts the tampered payload is still valid proves
    nothing. The assertion has to be that the check fires, which is the
    only thing that makes the passing check above it mean anything.
    """
    payload = artifact()
    baseline_ran = True
    try:
        check(payload)
    except AssertionError:
        baseline_ran = False
    assert baseline_ran, "the check already fails on the untampered artifact"

    mutate(payload)
    raised = False
    try:
        check(payload)
    except AssertionError:
        raised = True
    assert raised, "the tamper was not caught"


def _find_response(payload) -> dict:
    return next(row for row in payload["live_rows"]
                if row.get("kind") == "text")


def test_tamper_marking_a_budget_exhausted_response_complete_is_caught():
    _tamper(lambda p: _find_response(p)["gate"].update({"admitted": True}),
            check_no_budget_exhausted_response_is_complete)


def test_tamper_writing_unknown_usage_as_zero_is_caught():
    _tamper(lambda p: p["live_rows"][0]["usage"].update({"charge_units": 0}),
            check_usage_is_unknown)


def test_tamper_claiming_a_response_opened_a_step_is_caught():
    _tamper(lambda p: p.__setitem__("responses_opening_a_step_definition", 1),
            check_no_response_opened_a_step)


def test_tamper_widening_the_budget_past_the_served_rung_is_caught():
    _tamper(lambda p: p.__setitem__("max_output_tokens", 4096),
            check_budget_is_the_served_rung)


def test_tamper_overspending_the_inherited_ceiling_is_caught():
    _tamper(
        lambda p: p["authorisation"].update({"physical_sends_used": 20}),
        check_within_ceiling)


def test_tamper_marking_b17_comparable_with_b12_is_caught():
    _tamper(
        lambda p: p["protocol"].update({"comparable_with_b12": True}),
        check_non_comparable)


def test_tamper_planting_a_sealed_value_in_a_prompt_is_caught():
    _tamper(
        lambda p: p["live_rows"][0].update(
            {"sealed_values_not_in_prompt": ["off_by_one"]}),
        check_no_sealed_leak)


def test_the_artifact_carries_only_this_lanes_own_digests():
    """No unexplained long opaque value, where a leaked key would sit.

    The digests this lane legitimately records are read out of the
    artifact itself and allowed by value, not by prefix: an allowlist of
    prefixes would be a second thing to keep in step.
    """
    payload = artifact()
    allowed = {
        payload["offline_measurements"]["loader_verdicts"][
            "authored_control_record_digest"],
        payload["offline_measurements"]["loader_verdicts"][
            "authored_control_source_digest"],
    }
    for row in payload["live_rows"]:
        allowed.add(row["prompt_sha256"])
        digest = (row.get("gate") or {}).get("source_digest")
        if digest:
            allowed.add(digest)
    for row in store_rows()["receipts"]:
        if row.get("content_digest"):
            allowed.add(row["content_digest"])
    check_no_opaque_value(ARTIFACT.read_text(encoding="utf-8"), allowed)


def test_tamper_planting_an_opaque_value_is_caught():
    """A value the artifact does not own must be rejected.

    The planted string is deliberately NOT a prefix of any digest this
    lane records: a tamper that reuses a real digest would pass for an
    allowlist hit and prove nothing about the check.
    """
    allowed = set()
    raised = False
    try:
        check_no_opaque_value("b17f2a91c4de77b03f5a6e81d92c4a70be15d38c6",
                              allowed)
    except AssertionError:
        raised = True
    assert raised, "an opaque value the artifact does not own was accepted"


def test_the_artifact_names_no_credential_variable():
    assert "CX_AGENT_API_KEY" not in ARTIFACT.read_text(encoding="utf-8")
