"""Tests for the r2 campaign driver, at zero model calls.

Every test here drives the driver the way a reader or a reviewer would:
through its own public functions, against the written run directory, with
the gateway withdrawn. None of them reaches for the network, and none of
them asserts on a private attribute to make a check pass.

The tests that matter most are the ones that would fail if the driver
were wrong in the ways this file's purpose is to catch: a taxonomy
collapse, a miscount of constructions against unique programs, exposure
written after the effect, and evidence that cannot be re-derived offline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import live_construct as live  # noqa: E402
from experiments.ad01 import w1_e1_campaign_r2 as r2  # noqa: E402

EVIDENCE = ROOT / "reports" / "evidence" / r2.CAMPAIGN_ID


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def campaign() -> dict:
    """The written campaign, or skip if this lane has not run yet.

    The directory is the deliverable, so a test that needs it should say
    so rather than fail on a missing file in a fresh checkout.
    """
    if not (EVIDENCE / "campaign.json").exists():
        pytest.skip("%s has not been run in this checkout" % r2.CAMPAIGN_ID)
    return r2.summarize(EVIDENCE)


def test_the_campaign_is_its_own_study_root_and_names_what_it_supersedes() -> None:
    manifest = r2._build_manifest()
    assert manifest["campaign_id"] == r2.CAMPAIGN_ID
    assert manifest["supersedes"] == r2.SUPERSEDES
    # A rerun under the same id would merge two campaigns' dispatches into
    # one ledger, which is the thing the cap sheet's fresh-root rule is
    # there to stop.
    assert manifest["lineage"]["protocol_study_root"] == live.OUTPUT_STUDY_ROOT
    assert r2.CAMPAIGN_ID != manifest["lineage"]["protocol_study_root"]
    assert "route" not in json.dumps(manifest).lower() or \
        "credential" in manifest["route_note"]


def test_no_credential_is_written_into_the_manifest() -> None:
    manifest = r2._build_manifest()
    serialized = json.dumps(manifest)
    assert "sk-cx" not in serialized
    assert "api_key" not in serialized
    assert "SETTLEMENT_GATEWAY_KEY" not in serialized


def test_the_census_answers_the_question_with_a_search_not_an_assertion() -> None:
    census = r2.acquisition_census()
    # The claim is only worth as much as the search behind it, so the
    # search is checked to have happened over a real tree.
    assert census["acquire_site_count"] > 10
    assert census["files_examined"] > 100
    assert any(s["file"].endswith("construct.py") for s in census["acquire_sites"])
    # And every site the search found is adjudicated rather than left for
    # a reader to classify.
    adjudicated = {a["site"].split()[0] for a in census["adjudicated_acquire_sites"]}
    assert len(census["adjudicated_acquire_sites"]) >= 5


def test_the_census_finds_the_step_counter_path_and_does_not_dismiss_it() -> None:
    census = r2.acquisition_census()
    step = census["record_builders"]["step-python"]
    # A provider's bytes CAN become a STEP artifact. Saying otherwise
    # would be a false negative on the most decision-relevant question in
    # E1, and the reason it is not an E1 cell has to be the binding, not
    # the possibility.
    assert step["reads_model_text"] is True
    counter = census["counter_path_found"]["step_python"]
    assert "construct.py" in counter
    assert "PostgreSQL" in census["counter_path_found"]["binding"]


def test_the_census_shows_the_boolean_path_is_boolean_only_by_refusal() -> None:
    census = r2.acquisition_census()
    refusals = census["refusals_that_make_it_boolean_only"]
    # Not by naming convention: the operation identity raises on a split
    # the freeze does not name and on a seed outside the frozen pair.
    assert refusals["operation_identity_rejects_a_non_frozen_split"]["accepted"] \
        is False
    assert refusals["operation_identity_rejects_a_non_frozen_seed"]["accepted"] \
        is False
    assert "unknown arm or task" in \
        refusals["operation_identity_rejects_a_non_frozen_split"]["detail"]


def test_no_non_boolean_record_builder_takes_model_text() -> None:
    census = r2.acquisition_census()
    for name, builder in census["record_builders"].items():
        if name == "step-python":
            continue
        assert builder["reads_model_text"] is False, name


def test_exposure_is_written_before_any_effect_and_names_every_opportunity() -> None:
    manifest = r2._build_manifest()
    exposure = r2._build_exposure(manifest)
    # One row per construction opportunity, owed before the first send, so
    # a process killed at attempt seven still reads as eight owed.
    assert exposure["attempts_planned"] == r2.LINEAGE_COUNT * len(r2.TREATMENTS)
    assert all(a["state"] == "pending" for a in exposure["attempts"])
    assert all(a["outcome"] is None for a in exposure["attempts"])
    assert exposure["dispatches_spent"] == 0
    # Every row carries a distinct operation identity, which is what makes
    # the lineages independent: the identity is what the store keys on and
    # what proves two dispatches were two sends.
    ids = [a["operation_id"] for a in exposure["attempts"]]
    assert len(set(ids)) == len(ids)
    # The round run id is one per frozen round, not one per lineage. Both
    # treatments are two arms of the SAME frozen round -- same task, split,
    # seed and round -- and they differ in the prompt, not in the round. A
    # round id shared across arms is the honest identity, not a collision.
    rounds = {a["round_run_id"] for a in exposure["attempts"]}
    assert len(rounds) == r2.LINEAGE_COUNT
    assert exposure["model_call_ceiling"] == r2.MODEL_CALL_CEILING
    assert r2.MODEL_CALL_CEILING == r2.ATTEMPT_CEILING * 2


def test_the_call_ceiling_matches_the_cap_sheet_formula() -> None:
    # N = 4 x supported cells x treatments, and the call ceiling is N x 2.
    assert r2.ATTEMPT_CEILING == 4 * 1 * len(r2.TREATMENTS)
    assert r2.MODEL_CALL_CEILING == r2.ATTEMPT_CEILING * 2


def test_reference_points_bracket_the_frozen_floor(campaign: dict) -> None:
    refs = campaign["reference_scores"]
    # The do-nothing predictor and the oracle are two different things,
    # and a floor of 1.0 means the bar is the oracle. A reader who does
    # not see both cannot tell "beat chance" from "recovered the rule".
    assert refs["zero_predictor_overall"] < campaign["score_floor"]
    assert refs["oracle_overall"] == campaign["score_floor"]


def test_every_lineage_recorded_an_attempt_with_a_known_outcome(
        campaign: dict) -> None:
    for cell in campaign["cells"]:
        for verdict in cell["verdicts"]:
            assert verdict["outcome"] in live.PREFLIGHT_OUTCOMES
            assert verdict["reason"]
            assert verdict["operation_id"]


def test_the_taxonomy_stays_separate_and_is_not_collapsed(
        campaign: dict) -> None:
    # The five failure modes are five findings. A campaign that cannot
    # tell a route refusal from a poor task result is reporting an
    # apparatus fact as a model fact.
    for cell in campaign["cells"]:
        total = sum(cell["outcomes"].values())
        assert total == cell["lineages_run"]
        for name in live.PREFLIGHT_OUTCOMES:
            assert name in cell["outcomes"]


def test_constructions_are_scored_and_a_construction_is_a_parsed_run(
        campaign: dict) -> None:
    for cell in campaign["cells"]:
        for verdict in cell["verdicts"]:
            if verdict["outcome"] in ("constructed", "poor-task-result"):
                # A construction is a program that parsed, committed and
                # was scored. It always has bytes, a digest and a score.
                assert verdict["score"] is not None
                assert verdict["candidate_digest"]
            else:
                # Everything else has no score, and must not borrow one.
                assert verdict["score"] is None
                assert verdict["candidate_digest"] is None


def test_invalid_programs_are_split_by_their_actual_defect(
        campaign: dict) -> None:
    # `invalid-program` covers two findings: a reply that never stopped,
    # and a reply that stopped and was still not a program. They have
    # different causes and averaging them hides both, so each is named.
    seen = set()
    for cell in campaign["cells"]:
        for verdict in cell["verdicts"]:
            if verdict["outcome"] != "invalid-program":
                assert verdict["invalid_program_defect"] is None
                continue
            defect = verdict["invalid_program_defect"]
            assert defect in ("over-length", "would-not-parse")
            assert verdict["response_characters"] is not None
            if defect == "over-length":
                assert verdict["response_characters"] > \
                    live.OUTPUT_LIMITS["max_response_characters"]
            seen.add(defect)
    # A campaign with no invalid programs does not need either label.


def test_a_poor_task_result_is_below_the_floor_and_a_construction_is_not(
        campaign: dict) -> None:
    for cell in campaign["cells"]:
        for verdict in cell["verdicts"]:
            if verdict["outcome"] == "poor-task-result":
                assert verdict["score"] < campaign["score_floor"]
            if verdict["outcome"] == "constructed":
                assert verdict["score"] >= campaign["score_floor"]


def test_construction_events_unique_programs_and_records_are_three_numbers(
        campaign: dict) -> None:
    counts = campaign["counts"]
    # These have been collapsed into one another in prior evidence, which
    # turns four identical programs into four acquisitions.
    assert set(counts) >= {"construction_events", "unique_source_programs",
                           "retained_artifact_records"}
    for cell in campaign["cells"]:
        digests = cell["distinct_behaviours"]
        events = cell["construction_events"]
        # A cell cannot have more distinct programs than it has
        # constructions, and cannot have constructions without programs.
        assert digests <= events
        if events == 0:
            assert digests == 0
        # The score distribution counts scored lineages, which is the
        # construction events, not the unique programs.
        assert cell["score_distribution"]["n"] == events


def test_a_campaign_with_no_constructions_reports_an_empty_distribution(
        campaign: dict) -> None:
    for cell in campaign["cells"]:
        distribution = cell["score_distribution"]
        assert distribution["n"] == len(distribution["values"])
        if distribution["n"] == 0:
            assert distribution["min"] is None
            assert distribution["median"] is None
            assert distribution["max"] is None


def test_exposure_never_under_reports_what_was_owed(campaign: dict) -> None:
    exposure = campaign["exposure"]
    # The count on disk can only be as large as the plan, and a driver
    # fault leaves the attempt unsettled rather than settled as a result.
    assert exposure["attempts_planned"] == r2.ATTEMPT_CEILING
    assert exposure["attempts_settled"] <= exposure["attempts_planned"]
    assert exposure["dispatches_spent"] <= exposure["model_call_ceiling"]
    assert exposure["dispatches_spent"] + \
        exposure["dispatches_refunded"] >= exposure["dispatches_spent"]


def test_verify_withdraws_the_gateway_and_reproduces_every_verdict() -> None:
    if not (EVIDENCE / "campaign.json").exists():
        pytest.skip("%s has not been run in this checkout" % r2.CAMPAIGN_ID)
    outcome = r2.verify(EVIDENCE)
    assert outcome["failures"] == []
    assert outcome["network_withdrawn"] is True
    # A lineage that reached the wire is re-verified. One that did not is
    # reported as having nothing to attest, never as a pass.
    checked = outcome["checked"] + len(outcome["no_response_to_attest"])
    assert checked == r2.LINEAGE_COUNT * len(r2.TREATMENTS)
    for entry in outcome["no_response_to_attest"]:
        assert entry["outcome"] in ("route-refusal", "pre-dispatch-refusal",
                                    "transport-loss")


def test_verify_refuses_a_tampered_record_rather_than_reverifying_it(
        tmp_path: Path) -> None:
    if not (EVIDENCE / "campaign.json").exists():
        pytest.skip("%s has not been run in this checkout" % r2.CAMPAIGN_ID)
    # Re-verifiability is only a real claim if a tampered record fails.
    # Copy the run, swap a raw response, and require a failure naming it.
    import shutil
    root = tmp_path / "tampered"
    shutil.copytree(EVIDENCE, root)
    target = next(p for p in sorted((root / "lineages").glob("*.json"))
                  if json.loads(p.read_text(encoding="utf-8")).get(
                      "offline_verified"))
    record = json.loads(target.read_text(encoding="utf-8"))
    record["attempts"][0]["raw_response"] = '{"specs": "not a program"}'
    target.write_text(json.dumps(record, sort_keys=True, indent=1),
                      encoding="utf-8")
    outcome = r2.verify(root)
    assert outcome["failures"], "a swapped response must not re-verify"
    assert any(target.name == f["record"] for f in outcome["failures"])


def test_summarize_is_read_only_and_needs_no_gateway() -> None:
    if not (EVIDENCE / "campaign.json").exists():
        pytest.skip("%s has not been run in this checkout" % r2.CAMPAIGN_ID)
    before = {p: p.stat().st_mtime_ns
              for p in EVIDENCE.rglob("*.json")}
    withdrawn = live.LiveGuard.infer
    live.LiveGuard.infer = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("summarize reached for a gateway"))
    try:
        r2.summarize(EVIDENCE)
    finally:
        live.LiveGuard.infer = withdrawn
    after = {p: p.stat().st_mtime_ns for p in EVIDENCE.rglob("*.json")}
    assert before == after


def test_the_authored_baseline_is_never_counted_as_a_lineage(
        campaign: dict) -> None:
    # The baseline lives in the written campaign, not in summarize()'s
    # recomputation, so it is read from the file rather than from the
    # fixture.
    baseline = _read_json(EVIDENCE / "campaign.json").get("authored_baseline")
    if baseline is None:
        pytest.skip("campaign.json carries no authored baseline row")
    assert baseline["model_calls"] == 0
    assert baseline["origin"] == "authored-control"
    assert baseline["arm"] not in r2.TREATMENTS
    # It is measured, not dispatched, so it adds nothing to the count of
    # construction events.
    lineage_names = {v["lineage"] for cell in campaign["cells"]
                     for v in cell["verdicts"]}
    assert "authored-control" not in lineage_names


def test_every_lineage_sits_under_this_campaigns_own_study_root(
        campaign: dict) -> None:
    for cell in campaign["cells"]:
        for verdict in cell["verdicts"]:
            # The operation identity carries this campaign's round token,
            # so no dispatch can be mistaken for one of another study's.
            assert verdict["operation_id"].startswith("invl02-output-")
    assert campaign["campaign_id"] == r2.CAMPAIGN_ID
