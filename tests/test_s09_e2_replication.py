"""The two things a second E2 namespace has to be: independent, and paired.

`WORKER-STAGE-09-PARALLEL-EXPANSION.md:67` asks for two campaign namespaces
that share neither mutable state nor assessment feedback. Namespace
independence is a property of names and of the artifacts a run reads, so it
is asserted over the names this module mints and over every path it opens,
not over a comment. The pairing is a property of the estimator, so it is
asserted over the numbers: an unpaired member must be refused rather than
averaged into a zero.

The instrument tests are here because the replica's negative is only readable
if the instrument can produce a positive. Two defects in the first
namespace's apparatus are pinned by the tests below, each shown to fail by
inverting it.
"""

from __future__ import annotations

import json

import pytest

from experiments.ad01 import e2_replication as replica
from experiments.ad01 import learner
from experiments.ad01 import worlds
from execution_authority import execution_store


@pytest.fixture(scope="module")
def authority():
    """The store the instrument qualification executes against.

    `replica.qualify_instrument` steps five policies, so it cannot run
    without a store, and the four tests below called it with none. Every row
    came back `scored: false`, so the ordering they assert was never measured
    and the literals they pinned were values no execution had produced.
    """
    with execution_store("e2replication") as store:
        yield store


def _target(task_id: str = None) -> dict:
    body = replica.freeze()["body"]
    return worlds.load_task(
        worlds.FROZEN_DIR, task_id or body["target_task_ids"][0])


def _body() -> dict:
    return replica.freeze()["body"]


def _relevant_observations() -> list:
    return replica.measured_observations(_body()["source_task_ids"])


# ---------------------------------------------------------------------------
# namespace independence
# ---------------------------------------------------------------------------


def test_the_replica_mints_names_no_first_campaign_operation_could_collide():
    ids = replica.campaign_ids()

    assert ids["campaign_id"].startswith("s09iso-%s-" % replica.STORE_TOKEN)
    assert ids["allocation_id"] != ids["campaign_id"]
    assert "inv_r1_e2_scored" not in json.dumps(ids)
    for value in ids.values():
        assert "scored" not in value


def test_an_operation_id_names_the_replica_campaign_the_task_and_the_arm():
    cid = replica.campaign_ids()["campaign_id"]
    first = replica.operation_id_for(cid, "ad01-w0-within-sw-00",
                                    replica.ARM_RELEVANT)
    retry = replica.operation_id_for(cid, "ad01-w0-within-sw-00",
                                     replica.ARM_RELEVANT, attempt=1)

    assert cid in first
    assert "ad01-w0-within-sw-00" in first
    assert replica.ARM_RELEVANT in first
    assert retry != first
    assert retry.endswith("-c1")


def test_two_namespaces_never_produce_the_same_operation_id():
    cid = replica.campaign_ids()["campaign_id"]
    mine = replica.operation_id_for(cid, "t", replica.ARM_NONE)

    theirs = "ad01-%s-learner-0" % "t"
    assert mine != theirs


def test_the_replica_reads_the_first_namespace_only_to_agree_with_it():
    body = replica.contrast_block()

    assert body["independent_of"] == "inv_r1_e2_scored"
    assert body["cohort_world"] == 0
    first = json.loads(
        (replica.ARTIFACT_ROOT / "inv_r1_e2_scored/readings.json")
        .read_text(encoding="utf-8"))
    assert set(first) == set(replica.ARMS)
    assert replica.read_first_namespace() == first


def test_a_frozen_contrast_names_a_cohort_the_first_campaign_never_ran_on():
    body = _body()

    assert body["target_task_ids"]
    for task_id in body["target_task_ids"]:
        assert task_id.startswith("ad01-w0-")
        assert not task_id.startswith("ad01-w1-")


def test_an_edited_freeze_is_refused_rather_than_run():
    frozen = replica.freeze()
    frozen["body"]["arms"] = [replica.ARM_RELEVANT]

    with pytest.raises(replica.ReplicaRefused, match="edited after it was frozen"):
        replica.verify_freeze(frozen)


def test_a_freeze_whose_digest_is_recomputed_over_a_drifted_body_is_refused():
    frozen = replica.freeze()
    frozen["body"]["target_split"] = "transfer"
    frozen["freeze_digest"] = replica.digest_of(frozen["body"])

    with pytest.raises(replica.ReplicaRefused, match="no longer matches the panel"):
        replica.verify_freeze(frozen)


# ---------------------------------------------------------------------------
# the arms
# ---------------------------------------------------------------------------


def test_the_three_arms_differ_in_experience_and_nothing_else_in_their_shape():
    target = _target()
    body = _body()
    visible = learner.visible_opportunities(body["cohort_world"])
    arms = replica.arms_for(
        target, source_task_ids=body["source_task_ids"],
        filler_task_ids=body["filler_task_ids"], visible=visible)

    assert set(arms) == set(replica.ARMS)
    for name, arm in arms.items():
        assert arm["family"] == target["family"]
        assert arm["task"] == target
        prompt = replica.prompt_for(name, target, arm)
        assert "Eligible methods for this task: seed-sw-ddmin" in prompt
        assert 'Target task id: %s' % target["task_id"] in prompt
    assert arms[replica.ARM_NONE]["observations"] == []
    assert arms[replica.ARM_RELEVANT]["observations"]
    assert arms[replica.ARM_IRRELEVANT]["observations"]


def test_the_irrelevant_control_is_matched_to_the_relevant_arm_in_size_and_count():
    target = _target()
    body = _body()
    arms = replica.arms_for(
        target, source_task_ids=body["source_task_ids"],
        filler_task_ids=body["filler_task_ids"],
        visible=learner.visible_opportunities(body["cohort_world"]))
    relevant = arms[replica.ARM_RELEVANT]["observations"]
    control = arms[replica.ARM_IRRELEVANT]["observations"]

    assert learner._observation_chars(relevant) == learner._observation_chars(control)
    assert len(relevant) == len(control)
    assert [r["task_id"] for r in relevant] != [c["task_id"] for c in control]


def test_an_arm_whose_verdicts_the_alternate_view_cannot_flip_is_refused():
    unflippable = [{"observation_id": "o", "task_id": "t",
                    "capability_id": "ad01-sw", "verdict": "unmeasured",
                    "detail": ""}]

    with pytest.raises(replica.ReplicaRefused, match="cannot change"):
        replica.require_measurable_verdicts(unflippable)


def test_the_measured_arm_carries_a_verdict_a_real_reducer_earned():
    from experiments.ad01 import seeds
    from experiments.representation import checkers

    rows = _relevant_observations()
    source_id = rows[0]["task_id"]
    task = worlds.load_task(worlds.FROZEN_DIR, source_id)
    capability = next(c for c in seeds.SEED_CAPABILITIES
                      if c["capability_id"] == "seed-sw-ddmin")
    expected = checkers.check_software(
        task, seeds.run_seed(capability, task, max_queries=8)["candidate"])

    assert all(row["verdict"] == expected["verdict"] for row in rows)


# ---------------------------------------------------------------------------
# the instrument
# ---------------------------------------------------------------------------


def test_the_repaired_leg_separates_a_reader_from_an_identical_blind_policy(
        authority):
    target = _target()
    result = replica.qualify_instrument(
        target, _relevant_observations(),
        eligible_methods=replica.eligible_for(target), authority=authority)

    assert result["separates_reader_from_blind"]
    assert result["reader"]["scored"] and result["blind"]["scored"]
    # Measured, not carried forward. These rows pinned `2.0` and `1.0` while
    # the qualification ran with no store and scored nothing, so the numbers
    # were never produced by an execution. The reader earns its whole score
    # from the candidate comparison and the benefit leg; the blind policy
    # earns the benefit leg alone.
    assert result["reader"]["score"] == 1.7
    assert result["blind"]["score"] == 0.7
    assert result["reader"]["evidence"] == 1.0
    assert result["blind"]["evidence"] == 0.0


def test_a_reader_scores_above_an_echoer_that_reads_nothing(authority):
    """The ordering the old leg inverted.

    The echoer copies the verdicts into an input key and then runs the same
    method it would have run anyway. The reader re-routes on them. Under
    the input-comparing leg the echoer scored 2.00 and the reader 1.00,
    because the echoed string was the only site a policy could move and
    `method_id` was excluded outright.
    """
    target = _target()
    result = replica.qualify_instrument(
        target, _relevant_observations(),
        eligible_methods=replica.eligible_for(target), authority=authority)

    assert result["reader"]["scored"] and result["echoer"]["scored"]
    assert result["reader"]["score"] > result["echoer"]["score"]
    assert result["echoer"]["evidence"] == 0.0
    assert result["echoer"]["score"] == 0.7


def test_a_read_that_never_reaches_the_world_scores_beside_an_echoer(authority):
    """`READS_THE_VERDICT`, retained because it is the sharpest row here.

    It reads the verdicts and re-plans, and the two keys it moves are named
    in no resolver, so the world runs the same method under both exposures.
    The leg now says so.
    """
    target = _target()
    result = replica.qualify_instrument(
        target, _relevant_observations(),
        eligible_methods=replica.eligible_for(target), authority=authority)

    plan_only = result["plan_only_reader"]
    assert plan_only["scored"]
    assert plan_only["evidence"] == 0.0
    assert plan_only["score"] == result["echoer"]["score"]


def test_a_reader_confined_to_the_prompted_action_shape_earns_its_evidence(
        authority):
    """The row the old leg reported as a zero over an empty denominator.

    The prompted shape admits only `method_id` and `max_queries`, and the
    old leg excluded both, so a policy that demonstrably read and re-routed
    scored 0.0 for want of any site. The corrected leg reads the candidate,
    so the same policy's read is visible.
    """
    target = _target()
    result = replica.qualify_instrument(
        target, _relevant_observations(),
        eligible_methods=replica.eligible_for(target), authority=authority)
    prompted = result["prompted_shape_reader"]

    assert result["prompted_shape_earns_evidence"]
    assert prompted["scored"]
    assert prompted["evidence"] == 1.0
    assert prompted["score"] == 1.7


def test_the_added_prompt_line_asks_for_a_decision_not_a_copy():
    """The line exists to stop steering the arms at the echo.

    It used to instruct the model to put the verdicts into a
    `read_verdicts` input key, which is the one shape the old leg rewarded
    and the corrected leg cannot distinguish from a blind policy.
    """
    line = replica.prompt_delta()["added_line"]

    assert "read_verdicts" not in line
    assert "method_id" in line


def test_the_two_reference_policies_differ_only_in_the_act_of_reading():
    import difflib

    reader = replica.READS_THE_VERDICT.splitlines(keepends=True)
    blind = replica.IGNORES_THE_VERDICT.splitlines(keepends=True)
    changed = [(old, new) for old, new in zip(reader, blind) if old != new]

    assert len(reader) == len(blind)
    assert changed == [("    kept = _kept(view)\n", "    kept = []\n")]
    assert [line for line in difflib.ndiff(reader, blind)
            if line.startswith("- ")] == ["-     kept = _kept(view)\n"]


def test_a_campaign_refuses_to_dispatch_on_an_instrument_that_cannot_separate():
    """The refusal is what stops the run, and it happens before any send.

    `qualify_instrument` is stubbed rather than weakened, so the test turns
    on the guard in `run_campaign` and not on a scoring failure that would
    reach the store.
    """
    from experiments.ad01 import s09_e2_scored

    blind = {"reader": {"scored": False, "score": 0.0, "evidence": 0.0,
                        "evidence_varied": 0, "evidence_total": 0,
                        "agreement": "absent", "selected": "", "verdict": "",
                        "detail": "stubbed"},
             "blind": {"scored": False, "score": 0.0, "evidence": 0.0,
                       "evidence_varied": 0, "evidence_total": 0,
                       "agreement": "absent", "selected": "", "verdict": "",
                       "detail": "stubbed"},
             "prompted_shape_reader": {"scored": False, "score": 0.0,
                                       "evidence": 0.0, "evidence_varied": 0,
                                       "evidence_total": 0, "agreement": "absent",
                                       "selected": "", "verdict": "",
                                       "detail": "stubbed"},
             "separates_reader_from_blind": False,
             "prompted_shape_earns_evidence": False, "note": "stubbed"}
    original = replica.qualify_instrument
    sent = []
    try:
        replica.qualify_instrument = lambda *a, **k: blind
        with pytest.raises(replica.ReplicaRefused, match="does not score"):
            replica.run_campaign(
                dsn="dbname=unused", gateway=_NeverGateway(sent), model="m",
                allocation_id="a", campaign_id="c",
                targets=[_body()["target_task_ids"][0]])
    finally:
        replica.qualify_instrument = original
    assert sent == []


class _NeverGateway:
    def __init__(self, sent):
        self._sent = sent

    def infer(self, request):
        self._sent.append(request)
        raise AssertionError("the gateway was reached before the guard")


def test_a_campaign_qualifies_its_instrument_before_it_dispatches_anything():
    import inspect

    source = inspect.getsource(replica.run_campaign)

    assert source.index("qualify_instrument(") < source.index(
        "acquire_with_retry(")
    assert "if not qualification:" in source
    assert "if not qualification[\"separates_reader_from_blind\"]:" in source


# ---------------------------------------------------------------------------
# the pairing
# ---------------------------------------------------------------------------


def test_a_paired_difference_carries_its_own_standard_error():
    import statistics

    result = replica.paired_differences([1.0, 0.0, 1.0], [0.0, 0.0, 0.0])
    expected_se = statistics.pstdev([1.0, 0.0, 1.0]) / 3 ** 0.5

    assert result["measured"] is True
    assert result["n"] == 3
    assert result["delta"] == pytest.approx(2 / 3)
    assert result["paired_se"] == pytest.approx(expected_se)
    assert result["z"] == pytest.approx((2 / 3) / expected_se)


def test_unpaired_members_are_refused_rather_than_broadcast_to_fill():
    with pytest.raises(replica.ReplicaRefused, match="one reading per arm"):
        replica.paired_differences([1.0, 0.0], [0.0])


def test_an_unmeasured_pair_is_reported_absent_rather_than_as_a_zero():
    result = replica.paired_differences([], [])

    assert result["measured"] is False
    assert result["delta"] is None
    assert result["n"] == 0


def test_the_paired_report_drops_an_unscored_task_and_names_it():
    readings = {
        replica.ARM_RELEVANT: {"t1": {"scored": True, "score": 2.0,
                                      "normalized_reduction": 0.5},
                               "t2": {"scored": True, "score": 1.0,
                                      "normalized_reduction": 0.25}},
        replica.ARM_NONE: {"t1": {"scored": True, "score": 1.0,
                                  "normalized_reduction": 0.25},
                           "t2": {"scored": False, "score": 0.0,
                                  "normalized_reduction": 0.0}},
    }
    report = replica.paired_report(readings)["relevant-minus-none"]

    assert report["tasks"] == ["t1", "t2"]
    assert report["unscored_tasks"] == ["t2"]
    assert report["deltas"] == [0.25]
    assert report["paired"]["delta"] == 0.25
    assert report["estimator"] == replica.ESTIMATOR


def test_the_replica_reports_itself_descriptive_because_two_clusters_cannot_reach_alpha():
    census = replica.cluster_census()
    sweep = replica.sign_flip_p([1.0, 1.0])

    assert census["cluster_count"] == 2
    assert census["minimum_p"] == "1/2"
    assert census["required_at_alpha_1_20"] == 6
    assert sweep["corrected"] is False
    assert sweep["alpha"] == replica.ALPHA
    assert "descriptive" in sweep["note"]


def test_a_sign_sweep_over_no_pairs_reports_no_p_value_rather_than_one():
    assert replica.sign_flip_p([])["minimum_p"] is None
    assert replica.sign_flip_p([])["n_pairs"] == 0


# ---------------------------------------------------------------------------
# the evidence boundary
# ---------------------------------------------------------------------------


def _acquired(arm: str, source_chars: int) -> replica.Acquired:
    return replica.Acquired(arm=arm, task_id="t", operation_id="op",
                            prompt_chars=10, digest="d" * 64,
                            source_chars=source_chars, parse_problem="",
                            detail="")


def test_a_null_dispatch_is_preserved_and_refused_from_comparison():
    good = [_acquired(replica.ARM_RELEVANT, 400),
            _acquired(replica.ARM_NONE, 0)]
    empty = [_acquired(replica.ARM_NONE, 0)]

    replica.require_no_empty_dispatch_is_compared(good)
    nulls = replica.null_dispatches(good)
    assert len(nulls) == 1
    assert nulls[0]["arm"] == replica.ARM_NONE
    assert nulls[0]["source_chars"] == 0
    with pytest.raises(replica.ReplicaRefused, match="every dispatch"):
        replica.require_no_empty_dispatch_is_compared(empty)


def test_a_retry_spends_its_allowance_only_on_an_empty_dispatch():
    plan = replica.RETRIES
    calls = []

    def fake(dsn, **kwargs):
        calls.append(kwargs["attempt"])
        return replica.Acquired(
            arm=kwargs["arm"], task_id=kwargs["task_id"],
            operation_id="op%d" % kwargs["attempt"], prompt_chars=1,
            digest="d" * 64,
            source_chars=0 if len(calls) == 1 else 400,
            parse_problem="" if len(calls) > 1 else "lost-response",
            detail="", attempt=kwargs["attempt"])

    original = replica.acquire_one
    try:
        replica.acquire_one = fake
        last, attempts = replica.acquire_with_retry(
            dsn="x", campaign_id="c", allocation_id="a", arm="relevant",
            task_id="t", prompt="p", gateway=None, model="m",
            max_output_tokens=2048, retries=plan)
    finally:
        replica.acquire_one = original

    assert [a.attempt for a in attempts] == [0, 1]
    assert attempts[0].source_chars == 0
    assert last.source_chars == 400
    assert len(attempts) == plan + 1


def test_an_artifact_carrying_the_gateway_key_is_not_written():
    key = "sk-not-a-real-key-but-a-string"
    bundle = {"readings": {}, "acquired": [
        {"arm": "relevant", "detail": key}]}

    with pytest.raises(replica.ReplicaRefused, match="carries the gateway key"):
        replica.build_report(bundle, key=key)


def test_a_clean_artifact_passes_the_same_check():
    bundle = {"readings": {}, "acquired": [{"arm": "relevant",
                                            "detail": "fine"}],
              "freeze": replica.freeze()}

    report = replica.build_report(bundle, key="sk-not-a-real-key")

    assert report["namespace"] == replica.NAMESPACE
    assert not any(report["shares_with_first_namespace"].values())


def test_the_cap_sheet_counts_the_matrix_and_bounds_the_unit_allowance():
    body = _body()
    sheet = replica.cap_sheet()

    assert sheet["matrix"]["target_tasks"] == 3
    assert sheet["matrix"]["arms"] == 3
    assert sheet["allowance"]["construction_dispatches"] == 18
    assert sheet["allowance"]["physical_sends_ceiling"] == 19
    assert sheet["unit_allowance"]["requests"] == 19
    assert sheet["unit_allowance"]["units"] == (
        sheet["unit_allowance"]["per_request_units"] * 19)
    assert sheet["bounds"]["message_characters"] == replica.longest_prompt_chars(body)
    assert sheet["unit_allowance"]["unit_kind"] == "estimated-budget"
    assert sheet["freeze_digest"] == replica.freeze()["freeze_digest"]
    assert "broker.ensure_operation" in sheet["authority"]["owner"]


def test_the_cap_sheet_carries_no_key_and_no_endpoint_verbatim():
    sheet = replica.cap_sheet()
    blob = json.dumps(sheet)

    assert "SETTLEMENT_GATEWAY_KEY" not in blob
    assert "http" not in blob
