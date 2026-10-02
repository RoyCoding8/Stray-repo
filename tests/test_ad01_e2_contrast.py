"""The E2 contrast's own apparatus, checked without a model and without a store.

Every test here calls the campaign the way its user calls it, and asserts
the value a reader of the report would read. Nothing asserts a stored
`reason` and nothing asserts an implementation detail: the arms are built,
the freeze is checked, the treatment is audited, and the numbers are
recomputed from the panel.

The live path needs WSL, because a policy is stepped in a child process and
CPython refuses `preexec_fn` on Windows. These tests are the ones that do
not need it, which is most of the apparatus.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.ad01 import e2_contrast_campaign as campaign
from experiments.ad01 import e2_contrast_verify as verifier
from experiments.ad01 import e2_replication as replica
from experiments.ad01 import learner
from experiments.ad01 import worlds

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "reports" / "evidence"


def _target() -> dict:
    body = replica.contrast_block()
    return worlds.load_task(worlds.FROZEN_DIR, body["target_task_ids"][0])


def _arms(task: dict | None = None) -> dict:
    body = replica.contrast_block()
    return campaign.build_arms(
        task or _target(), source_task_ids=body["source_task_ids"],
        filler_task_ids=body["filler_task_ids"],
        visible=learner.visible_opportunities(body["cohort_world"]))


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------


def test_the_freeze_verifies_against_the_panel_it_names():
    frozen = campaign.freeze()
    assert campaign.verify_contrast(frozen) == frozen["body"]


def test_an_edited_freeze_is_refused_by_its_own_digest():
    frozen = copy.deepcopy(campaign.freeze())
    frozen["body"]["max_queries"] = 16
    with pytest.raises(campaign.ContrastRefused) as refusal:
        campaign.verify_contrast(frozen)
    assert "records" in str(refusal.value)


def test_a_freeze_whose_body_drifted_is_refused_by_name():
    frozen = campaign.freeze()
    body = copy.deepcopy(frozen["body"])
    body["arms"] = ["relevant"]
    with pytest.raises(campaign.ContrastRefused) as refusal:
        campaign.verify_contrast({"body": body,
                                  "freeze_digest": campaign.replica.digest_of(body)})
    assert "arms" in str(refusal.value)


# ---------------------------------------------------------------------------
# the graded-outcome uniformity defect
# ---------------------------------------------------------------------------


def test_the_frozen_arm_is_uniform_and_this_campaign_is_not():
    """The defect the assignment names, and the construction that answers it.

    The frozen arm grades `ok-preserved` on all three dev software tasks, so
    the three records a policy reads differ only in `task_id`. The
    campaign's own arm does not, and the difference is the whole point.
    """
    body = replica.contrast_block()
    frozen_rows = replica.measured_observations(body["source_task_ids"])
    assert len({(r["verdict"], r["reason"]) for r in frozen_rows}) == 1

    arms = _arms()
    mine = arms["relevant"]["observations"]
    assert len({r["reason"] for r in mine}) > 1
    assert len({r["detail"] for r in mine}) > 1


def test_a_uniform_relevant_arm_is_refused_rather_than_reported():
    frozen_rows = replica.measured_observations(
        replica.contrast_block()["source_task_ids"])
    with pytest.raises(campaign.ContrastRefused) as refusal:
        campaign.require_varying_graded_outcome(
            {"observations": frozen_rows}, {"observations": frozen_rows})
    assert "one graded outcome" in str(refusal.value)


def test_a_uniform_control_arm_is_refused_too():
    """Uniformity against uniformity is not a contrast, and is refused.

    This is the gate that caught the first version of this construction: the
    relevant arm varied and the control did not, so the control carried less
    evidence than the arm it was meant to control. The frozen filler pool
    at the campaign's control budget is uniform, and the control is built at
    a budget where it is not.
    """
    body = replica.contrast_block()
    arms = _arms()
    uniform = campaign._measured_rows(body["filler_task_ids"], max_queries=1)
    with pytest.raises(campaign.ContrastRefused) as refusal:
        campaign.require_varying_graded_outcome(
            arms["relevant"], {"observations": uniform})
    assert "uniformity against uniformity" in str(refusal.value)


def test_the_verdict_is_constant_on_every_arm_the_panel_can_build():
    """The deeper finding, and the reason the narration is in `detail`.

    A sweep of all three worlds, both families, both seed capabilities and
    budgets 1 through 16 produces 1728 `preserved` verdicts and nothing else,
    because both authored reducers only ever emit legal deletions that keep
    the witness. So the graded field the packet projection delivers is
    constant, and the varying one is dropped by that projection.

    The control's records also carry a pad key, which the projection also
    drops. That is the size-matching padding and it is meant to be
    invisible: a pad field inside the allowlist would overwrite the graded
    text, which is the defect the first version of this construction had.
    The relevant arm needs no padding, so it carries no pad key.
    """
    arms = _arms()
    for name in ("relevant", "irrelevant"):
        profile = campaign.graded_outcome_profile(arms[name]["observations"])
        assert profile["verdict_is_constant"]
        assert len(profile["distinct_reasons"]) > 1
        assert not profile["uniform"]
        dropped = profile["fields_dropped_by_projection"]
        assert "reason" in dropped and "reduction" in dropped
    control_keys = {k for row in arms["irrelevant"]["observations"]
                    for k in row} - {k for row in
                                     arms["relevant"]["observations"] for k in row}
    assert control_keys == set(campaign._PAD_KEYS[:1])
    assert control_keys <= set(arms["irrelevant"]["observations"][0])


def test_the_size_padding_cannot_overwrite_the_graded_text():
    """The bug the uniformity gate caught, asserted so it cannot come back.

    `learner._resized` pads the last record's `detail`, which is the one
    graded field a policy receives. Padding it with `x` replaces the
    checker's `reason` and `reduction` with noise, so the control stops
    carrying an outcome at all. The padding therefore goes to a key the
    projection does not deliver.
    """
    from experiments.ad01 import packet

    arms = _arms()
    for name in ("relevant", "irrelevant"):
        rows = arms[name]["observations"]
        projected = packet.project_observations(rows)
        for source, delivered in zip(rows, projected):
            assert campaign._grade_of(source) == campaign._grade_of(delivered)
            assert "x" * 40 not in str(delivered.get("detail"))


# ---------------------------------------------------------------------------
# size matching and the treatment audit
# ---------------------------------------------------------------------------


def test_the_two_arms_carrying_experience_are_size_and_count_matched():
    sized = campaign.require_size_matched(_arms())
    assert sized["relevant"]["characters"] == sized["irrelevant"]["characters"]
    assert sized["relevant"]["records"] == sized["irrelevant"]["records"]
    assert sized["none"]["records"] == 0


def test_unequal_arms_are_refused():
    arms = _arms()
    arms["irrelevant"]["observations"] = arms["irrelevant"]["observations"][:1]
    with pytest.raises(campaign.ContrastRefused) as refusal:
        campaign.require_size_matched(arms)
    assert "not size matched" in str(refusal.value)


def test_every_arm_receives_the_same_interface_and_opportunity():
    """The assignment asks for this explicitly, and a prior bug dropped
    information at three points, so it is asserted rather than described."""
    audit = campaign.treatment_input_audit(_target(), _arms())
    assert audit["interfaces_equal"]
    assert audit["opportunity_equal"]
    arms = audit["arms"]
    assert {tuple(a["eligible_methods"]) for a in arms.values()} == {
        ("seed-sw-ddmin", "seed-sw-greedy")}
    assert arms["none"]["observations"] == 0
    assert arms["relevant"]["observations"] == 3


def test_the_audit_names_the_field_the_prompt_promises_and_the_view_drops():
    """The third of the three drops, and it is still open.

    `reason` is what tells an `ok-preserved` record from an `ok-incumbent`
    one. The prompt names it and `packet.project_observations` drops it, so a
    policy reading the verdicts sees one constant. The audit names it rather
    than letting a reader assume the prompt is the whole delivery.
    """
    audit = campaign.treatment_input_audit(_target(), _arms())
    for name in ("relevant", "irrelevant"):
        assert audit["arms"][name]["named_in_prompt_but_not_delivered"] == ["reason"]
        assert "reason" in audit["arms"][name]["dropped_before_the_policy"]


def test_the_none_arm_is_audited_as_having_no_prior_observation_line():
    audit = campaign.treatment_input_audit(_target(), _arms())
    assert audit["arms"]["none"]["prompt_prior_observation_line"] is None
    assert audit["arms"]["none"]["verdicts_delivered"] == []


# ---------------------------------------------------------------------------
# reachability
# ---------------------------------------------------------------------------


def test_the_default_is_the_ceiling_so_no_positive_delta_is_attainable():
    """The load-bearing finding, asserted rather than described.

    The policy's only lever is the action's decision vector, and on all three
    frozen targets the first eligible method at the frozen budget is already
    the best cell of the whole grid. So the largest positive paired delta the
    panel admits is 0.0, and any positive number this contrast reports would
    have to come from somewhere other than a better decision.
    """
    census = campaign.reachability_census(
        replica.contrast_block()["target_task_ids"],
        method_ids=["seed-sw-ddmin", "seed-sw-greedy"],
        budgets=[4, 8, 12, 16, 24, 32])
    assert census["max_attainable_positive_delta"] == 0.0
    assert all(row["attainable_positive_delta"] == 0.0
               for row in census["rows"])
    assert census["max_attainable_negative_delta"] > 0.0


def test_the_census_reports_more_than_one_reachable_value():
    """The instrument can move. It is the default, not the grid, that is stuck."""
    census = campaign.reachability_census(
        ["ad01-w0-within-sw-00"],
        method_ids=["seed-sw-ddmin", "seed-sw-greedy"], budgets=[4, 8, 16])
    assert len(census["rows"][0]["distinct_values"]) > 1


# ---------------------------------------------------------------------------
# the paired estimator
# ---------------------------------------------------------------------------


def test_a_row_without_the_two_keys_paired_report_reads_measures_nothing():
    """The defect the whole scored-observable choice answers.

    `reading_row` writes nine keys and `paired_report` reads
    `normalized_reduction` and `action`. So a run that keeps the lossy
    projection computes 0.0 by arithmetic, and this campaign keeps
    `Reading.as_dict` instead.
    """
    row = replica.reading_row.__doc__ and None
    assert row is None
    written = _reading_row_fields()
    assert replica.NORMALIZED_REDUCTION not in written
    assert "action" not in written
    assert set(_as_dict_fields()) >= {replica.NORMALIZED_REDUCTION, "action"}


def test_the_frozen_paired_report_computes_a_real_delta_from_as_dict_rows():
    def reading(reduction: float, method: str) -> dict:
        return {"scored": True, "verdict": "preserved", "score": 1.0,
                replica.NORMALIZED_REDUCTION: reduction,
                "action": {"inputs": {"method_id": method, "max_queries": 8}}}

    tasks = ["ad01-w0-within-sw-00", "ad01-w0-within-sw-01"]
    report = replica.paired_report({
        "relevant": {t: reading(r, "seed-sw-ddmin")
                     for t, r in zip(tasks, (0.7, 0.75))},
        "irrelevant": {t: reading(0.0, "seed-sw-greedy") for t in tasks},
        "none": {t: reading(0.0, "seed-sw-greedy") for t in tasks},
    })
    assert report["relevant-minus-none"]["deltas"] == [0.7, 0.75]
    assert report["relevant-minus-none"]["decisions"][tasks[0]]["differs"] is True


def _reading_row_fields() -> set:
    import inspect
    import re

    return set(re.findall(
        r'"(\w+)":', inspect.getsource(replica.reading_row)))


def _as_dict_fields() -> set:
    import inspect
    import re

    from experiments.ad01 import s09_e2_scored as scored

    return set(re.findall(r'"(\w+)":', inspect.getsource(scored.Reading.as_dict)))


# ---------------------------------------------------------------------------
# the verifier, on forgeries
# ---------------------------------------------------------------------------


def _report() -> dict:
    path = EVIDENCE / campaign.NAMESPACE / "report.json"
    if not path.exists():
        pytest.skip("no campaign artifact; run scripts/w2_e2_contrast_run.sh")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_verifier_agrees_with_the_artifact_it_reads():
    outcome = verifier.verify(_report())
    assert outcome["agrees"], outcome["failed"]


def test_the_verifier_rejects_a_reduction_the_measures_do_not_give():
    outcome = verifier.verify(_forged("inflated_reduction"))
    assert "paired" in outcome["failed"]


def test_the_verifier_rejects_a_self_consistent_inflation():
    """The forgery E1 verified clean.

    The reduction is inflated *and* the candidate measure is shrunk to match,
    so the report agrees with itself throughout. Only re-deriving the
    reduction from the checker's own fields catches it.
    """
    outcome = verifier.verify(_forged("self_consistent_inflation"))
    assert "paired" in outcome["failed"]


def test_the_verifier_rejects_a_uniform_arm_the_panel_does_not_have():
    outcome = verifier.verify(_forged("claimed_uniform_arm"))
    assert "evidence" in outcome["failed"]


def test_the_verifier_rejects_a_ceiling_no_decision_reaches():
    outcome = verifier.verify(_forged("inflated_ceiling"))
    assert "reachability" in outcome["failed"]


def _forged(kind: str) -> dict:
    """One self-consistent forgery, built the way `red_proof` builds it.

    `red_proof` is the campaign's own demonstration and returns the
    verifier's verdict on each forgery. This rebuilds the forged report
    itself, so the assertion is on the verifier refusing a document rather
    than on the demonstration agreeing with itself.
    """
    return _rebuild(_report(), kind)


def _rebuild(report: dict, kind: str) -> dict:
    import copy as _copy

    forged = _copy.deepcopy(report)
    readings = dict(forged.get("readings") or {})
    if kind == "inflated_reduction":
        task_id = sorted(readings[replica.ARM_RELEVANT])[0]
        row = dict(readings[replica.ARM_RELEVANT][task_id])
        row[replica.NORMALIZED_REDUCTION] = 0.99
        forged["readings"] = {**readings, replica.ARM_RELEVANT: {
            **readings[replica.ARM_RELEVANT], task_id: row}}
    elif kind == "self_consistent_inflation":
        treatment = dict(readings.get(replica.ARM_RELEVANT) or {})
        task_id = sorted(treatment)[0]
        row = dict(treatment[task_id])
        initial = int(row.get("initial_measure") or 0)
        inflated = 0.99
        row["candidate_measure"] = 0
        row[replica.NORMALIZED_REDUCTION] = inflated
        forged["readings"] = {**readings, replica.ARM_RELEVANT: {
            **treatment, task_id: row}}
        forged["paired"] = replica.paired_report(forged["readings"])
    elif kind == "claimed_uniform_arm":
        forged["graded_outcome_profiles"] = {
            name: {**dict(value or {}), "uniform": True,
                   "delivered_uniform": True, "delivered_grades": 1}
            for name, value in forged["graded_outcome_profiles"].items()}
    elif kind == "inflated_ceiling":
        forged["reachability_census"] = {
            **forged["reachability_census"],
            "max_attainable_positive_delta": 0.5}
    return forged


# ---------------------------------------------------------------------------
# the live path, and the route conflict it runs into
# ---------------------------------------------------------------------------


def test_a_frozen_route_and_a_frozen_dispatch_cannot_both_hold_on_this_route():
    """The conflict this campaign resolved by dropping the effort.

    A frozen route can only be attested on `chat`, because `responses`
    publishes no provider. `chat` refuses a request carrying a
    `reasoning_effort`. The frozen `acquire_one` always sends one. So the
    resolution has to be the dispatch, and the campaign states the effort it
    actually sent rather than the one the cap sheet prices.
    """
    from settlement.gateway_http import HttpGatewayAdapter, _route_contract

    contract = _route_contract({
        "endpoint": "http://127.0.0.1:4100/v1",
        "requested_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "resolved_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "provider": "Nvidia", "tier": "free"})
    assert contract is not None
    adapter = HttpGatewayAdapter(endpoint="http://127.0.0.1:4100/v1/",
                                 api_key="x", api="responses",
                                 expected_route=contract.as_dict())
    # The adapter rstrips the slash, so the contract must not carry one.
    assert adapter.endpoint == "http://127.0.0.1:4100/v1"
    assert campaign.acquire_one.__doc__ is not None
    assert "reasoning_effort" in campaign.acquire_one.__doc__


def test_the_campaign_omits_the_effort_the_frozen_dispatch_sends():
    """Asserted against the payload the two functions build, not the prose.

    The send needs a live route, so what is checked here is the shape of the
    payload each function hands `ensure_operation`. The campaign's carries
    four keys and the frozen one carries five, and
    `broker._validate_model` requires model, messages, max_output_tokens and
    deadline_ms and treats an absent effort as `None`.
    """
    import ast
    import inspect
    import textwrap

    def payload_keys(function) -> set:
        """The keys of the `payload={...}` dict literal the function builds.

        Read from the parsed tree rather than from the text, so a docstring
        mentioning a field cannot be mistaken for the field being sent, which
        is exactly the mistake a substring check makes here.
        """
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and any(getattr(k, "arg", None) == "payload"
                            and isinstance(k.value, ast.Dict)
                            for k in node.keywords)):
                continue
            literal = next(k.value for k in node.keywords
                           if getattr(k, "arg", None) == "payload")
            return {key.value for key in literal.keys
                    if isinstance(key, ast.Constant)}
        raise AssertionError("no payload dict literal in %s"
                             % function.__name__)

    mine = payload_keys(campaign.acquire_one)
    frozen = payload_keys(replica.acquire_one)
    assert "reasoning_effort" not in mine
    assert "reasoning_effort" in frozen
    assert mine <= frozen


# ---------------------------------------------------------------------------
# the artifacts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("namespace", [campaign.NAMESPACE,
                                       campaign.R2_NAMESPACE])
def test_a_written_artifact_carries_no_gateway_key(namespace: str):
    path = EVIDENCE / namespace / "report.json"
    if not path.exists():
        pytest.skip("no artifact for %s" % namespace)
    blob = path.read_text(encoding="utf-8")
    for needle in ("sk-cx-local", "Bearer "):
        assert needle not in blob


@pytest.mark.parametrize("namespace", [campaign.NAMESPACE,
                                       campaign.R2_NAMESPACE])
def test_a_written_artifact_reports_no_cost_from_an_unread_field(namespace: str):
    path = EVIDENCE / namespace / "report.json"
    if not path.exists():
        pytest.skip("no artifact for %s" % namespace)
    report = json.loads(path.read_text(encoding="utf-8"))
    accounting = report["accounting"]
    assert accounting["billed_values_seen"] == ["None"]
    assert accounting["charge_units_values_seen"] == ["None"]
    assert "usage.cost" in accounting["discrepancy"]
    assert report["key_discrepancy"]["usage_cost_reaches_the_store"] is False


def test_the_replication_namespace_declares_its_predecessor():
    path = EVIDENCE / campaign.R2_NAMESPACE / "report.json"
    if not path.exists():
        pytest.skip("no replication artifact")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["campaign_kind"] == "replication"
    assert report["is_replication_of"] == campaign.NAMESPACE
    assert report["shares_with_prior_namespaces"]["mutable_store"] is False
    assert report["shares_with_prior_namespaces"]["operation_ids"] is False


def test_a_run_script_runs_without_launching_anything():
    script = REPO / "scripts" / "w2_e2_contrast_run.sh"
    assert script.exists()
    body = script.read_text(encoding="utf-8")
    assert "S09ISO_DISABLE=1" in body
    assert "PYTHONPATH=" in body
    # It must not unset the isolation guard, and must not fan out into a suite.
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in body
    assert "pytest" not in body


def test_the_run_script_is_executable_and_parses_under_bash():
    script = REPO / "scripts" / "w2_e2_contrast_run.sh"
    if sys.platform == "win32":
        pytest.skip("bash is under WSL")
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
