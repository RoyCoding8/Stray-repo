import json
from dataclasses import replace
from fractions import Fraction

import pytest

from experiments.ad01 import s09_panel_inventory as panel_inventory
from experiments.ad01 import s09_study_protocol as proto


PANEL = proto.worlds.FROZEN_DIR


def _bundle(**overrides):
    bundle = proto.PROTOCOL.freeze.as_bundle()
    bundle.update(overrides)
    return bundle


def _resign(**overrides):
    """A bundle whose digest is recomputed over the tampered body."""
    bundle = _bundle(**overrides)
    body = {key: value for key, value in bundle.items()
            if key != "freeze_digest"}
    bundle["freeze_digest"] = proto.digest(body)
    return bundle


def _outcome(**overrides):
    fields = {
        "freeze_matched": True,
        "preconditions_satisfied": True,
        "acquisition": proto.classify_acquisition(
            [{"provenance": proto.ACQUIRED, "is_reuse": False,
              "model": proto.REQUESTED_MODEL}]),
        "within_delta": Fraction(3, 10),
        "transfer_delta": Fraction(0),
        "arm_measurements": {arm: Fraction(1, 2) for arm in proto.ARMS},
    }
    fields.update(overrides)
    return proto.Outcome(**fields)


def test_the_frozen_study_root_carries_the_run_namespace():
    freeze = proto.PROTOCOL.freeze

    assert freeze.study_root == "reports/evidence/s09-live-study-r1-%s" \
        % freeze.namespace.token
    assert freeze.namespace.token in freeze.study_root
    assert freeze.namespace.token == proto.run_token(freeze.run_id)
    assert all(freeze.namespace.qualifies(campaign)
               for campaign in freeze.campaign_ids)
    assert all(freeze.namespace.qualifies(identifier)
               for identifier in freeze.operation_ids)


def test_episodes_are_the_frozen_worlds_domains_splits_in_order():
    episodes = proto.PROTOCOL.freeze.episodes

    assert len(episodes) == 36
    assert [(episode.world, episode.domain, episode.split)
            for episode in episodes] == [
        (world, domain, split)
        for world in (1, 2) for domain in ("software", "graph")
        for split in ("dev", "within", "transfer")
        for _index in range(3)]
    assert episodes[0].task_id == "ad01-w1-dev-sw-00"
    assert episodes[-1].task_id == "ad01-w2-transfer-gr-02"
    assert all(episode.arms == ("P0", "P1", "P2") for episode in episodes)


def test_cells_state_the_per_cell_task_ids_and_counts():
    cells = {(cell.arm, cell.world, cell.domain): cell
             for cell in proto.PROTOCOL.cells}

    assert len(proto.PROTOCOL.cells) == 12
    assert cells[("P1", 1, "graph")].count == 9
    assert cells[("P0", 2, "software")].task_ids == (
        "ad01-w2-dev-sw-00", "ad01-w2-dev-sw-01", "ad01-w2-dev-sw-02",
        "ad01-w2-transfer-sw-00", "ad01-w2-transfer-sw-01",
        "ad01-w2-transfer-sw-02", "ad01-w2-within-sw-00",
        "ad01-w2-within-sw-01", "ad01-w2-within-sw-02")


def test_validate_accepts_the_protocols_own_freeze_and_the_digest_round_trips():
    freeze = proto.PROTOCOL.freeze
    bundle = freeze.as_bundle()

    assert proto.PROTOCOL.validate(bundle).matched
    assert freeze.freeze_digest == proto.digest(freeze.body())
    assert bundle["freeze_digest"] == proto.digest(
        {key: value for key, value in bundle.items()
         if key != "freeze_digest"})
    assert json.loads(proto.canonical(freeze.body()))["episodes"] == \
        json.loads(proto.canonical(bundle))["episodes"]
    assert proto.PROTOCOL.require_match(bundle) is freeze


def test_validate_refuses_a_freeze_whose_model_differs():
    tampered = _resign(model="openrouter/nvidia/nemotron-3-ultra-550b-a55b")

    disposition = proto.PROTOCOL.validate(tampered)

    assert not disposition.matched
    assert "model-differs-from-protocol" in disposition.reasons


def test_validate_refuses_a_freeze_whose_namespace_token_is_absent():
    collidable = _resign(study_root="reports/evidence/s09-live-study-r1",
                         run_id="not-this-run",
                         namespace={"token": "not-this-run",
                                    "run_id": "not-this-run"})

    disposition = proto.PROTOCOL.validate(collidable)

    assert not disposition.matched
    assert "namespace-token-absent-from-study-root" in disposition.reasons
    assert "namespace-token-absent-from-this-run" in disposition.reasons


def test_validate_refuses_operation_ids_outside_the_frozen_set():
    borrowed = _resign(
        operation_ids=list(proto.PROTOCOL.freeze.operation_ids) + [
            "invl02-output-872608eb94c3-P1-audit-0023-a1"])

    disposition = proto.PROTOCOL.validate(borrowed)

    assert not disposition.matched
    assert "operation-id-outside-the-frozen-set" in disposition.reasons


def test_the_power_position_is_the_frozen_panels_own_cluster_count():
    power = proto.PROTOCOL.power
    inventory = proto._panel_cells(PANEL)

    assert power.required_clusters == 6
    assert power.total_clusters == 10
    assert [(domain.domain, domain.cluster_count,
             domain.minimum_p, domain.powered)
            for domain in power.all_domains] == [
        ("software", 4, Fraction(1, 8), False),
        ("graph", 6, Fraction(1, 32), True),
    ]
    assert power.domain("software").cluster_templates == (
        "stale-clear-core", "stale-clear-del-core", "stale-read-2chain",
        "stale-read-3chain")
    assert power.minimum_p_rule.startswith("2^(1-n)")
    assert power.cluster_rule == panel_inventory.CLUSTER_RULE
    assert sorted(cell.template for cell in inventory) != []


def test_the_frozen_panel_cannot_support_a_significance_claim():
    power = proto.PROTOCOL.power
    claim = proto.PROTOCOL.claim

    assert power.supports_significance is False
    assert proto.PROTOCOL.supports_significance is False
    assert power.unpowered_domains == ("software",)
    assert power.powered_domains == ("graph",)
    assert power.shortfall == 2
    assert claim.is_significant is False
    assert claim.as_dict()["significant"] is False
    assert claim.as_dict()["cluster_shortfall"] == 2
    assert claim.as_dict()["unpowered_domains"] == ["software"]


def test_minimum_sign_flip_p_matches_the_panel_inventory_rule():
    for count in range(0, 12):
        mine = proto.minimum_sign_flip_p(count)
        theirs = panel_inventory.minimum_sign_flip_p(count)
        assert (None if mine is None else float(mine)) == theirs
    assert proto.minimum_sign_flip_p(0) is None
    assert proto.minimum_clusters_for_alpha(Fraction(1, 20)) == 6


def test_the_stopping_rule_refuses_rather_than_invents_a_ceiling():
    refusal = proto.PROTOCOL.ceiling(None)

    assert isinstance(refusal, proto.Refusal)
    assert refusal.reason == "unknown-budget-input"
    assert proto.PROTOCOL.ceiling(None).detail == refusal.detail


def test_the_stopping_rule_derives_the_ceiling_when_both_inputs_are_known():
    ceiling = proto.PROTOCOL.ceiling(3)

    assert isinstance(ceiling, proto.DispatchCeiling)
    assert ceiling.hard_ceiling == proto.PROTOCOL.freeze.dispatch_ceiling
    assert ceiling.already_dispatched == 3
    assert ceiling.remaining == ceiling.hard_ceiling - 3
    assert ceiling.as_dict()["remaining"] == ceiling.remaining
    assert ceiling.as_dict()["sources"]["already_dispatched"].startswith(
        "the count of operations")


def test_the_stopping_rule_refuses_a_store_that_is_already_over_ceiling():
    over = proto.PROTOCOL.freeze.dispatch_ceiling + 1

    refusal = proto.PROTOCOL.ceiling(over)

    assert isinstance(refusal, proto.Refusal)
    assert refusal.reason == "already-over-ceiling"


def test_a_zero_dispatch_ceiling_is_refused_rather_than_defaulted():
    zeroed = replace(proto.PROTOCOL, stopping_rule=replace(
        proto.PROTOCOL.stopping_rule, default_ceiling=0))

    ceiling = zeroed.ceiling(0)

    assert isinstance(ceiling, proto.DispatchCeiling)
    assert ceiling.hard_ceiling == 0
    assert ceiling.remaining == 0


def test_every_precondition_must_be_reported_and_passed():
    passing = proto.evaluate_preconditions(
        proto.PreconditionReport(code=item.code, passed=True)
        for item in proto.PRECONDITIONS)
    skipped = proto.evaluate_preconditions(
        proto.PreconditionReport(code=item.code, passed=True)
        for item in proto.PRECONDITIONS if item.code != "disposable-database")
    failed = proto.evaluate_preconditions(
        [proto.PreconditionReport(code=item.code, passed=True)
         for item in proto.PRECONDITIONS[:-1]]
        + [proto.PreconditionReport(
            code=proto.PRECONDITIONS[-1].code, passed=False,
            detail="executed bytes are the authored fixture's")])

    assert passing.satisfied
    assert not skipped.satisfied
    assert skipped.unreported == ("disposable-database",)
    assert not failed.satisfied
    assert failed.unsatisfied[0].code == "executed-bytes-are-the-bound-bytes"


def test_an_unproven_acquisition_is_reported_rather_than_hidden():
    unproven = proto.classify_acquisition(
        [{"provenance": "authored-control", "is_reuse": False}])
    contaminated = proto.classify_acquisition(
        [{"provenance": "model-acquired", "is_reuse": False,
          "model": "recorded-double"}])
    unavailable = proto.classify_acquisition([])

    assert unproven.state == proto.ACQ_UNPROVEN
    assert contaminated.state == proto.ACQ_CONTAMINATED
    assert unavailable.state == proto.ACQ_UNAVAILABLE
    verdict = proto.PROTOCOL.decide(_outcome(acquisition=contaminated))
    assert verdict.acquisition == proto.ACQ_CONTAMINATED
    assert verdict.primary == proto.ACQ_CONTAMINATED


def test_the_decision_rule_covers_every_named_outcome():
    acquired = proto.classify_acquisition(
        [{"provenance": proto.ACQUIRED, "is_reuse": False,
          "model": proto.REQUESTED_MODEL}])

    cases = {
        "demonstrated": _outcome(acquisition=acquired),
        "unproven": _outcome(acquisition=proto.classify_acquisition(
            [{"provenance": "authored-control"}])),
        "benefit": _outcome(within_delta=Fraction(3, 10),
                            transfer_delta=Fraction(3, 10)),
        "tie": _outcome(within_delta=Fraction(1, 100)),
        "no-benefit": _outcome(within_delta=Fraction(-1, 10)),
        "transfer": _outcome(transfer_delta=Fraction(1, 4)),
        "no-transfer": _outcome(transfer_delta=Fraction(0)),
        "ineligible": _outcome(freeze_matched=False),
    }

    assert (cases["demonstrated"].acquisition.demonstrated,
            proto.PROTOCOL.decide(cases["demonstrated"]).acquisition) == (
        True, proto.ACQ_DEMONSTRATED)
    assert proto.PROTOCOL.decide(cases["unproven"]).acquisition \
        == proto.ACQ_UNPROVEN
    assert (proto.PROTOCOL.decide(cases["benefit"]).within,
            proto.PROTOCOL.decide(cases["benefit"]).transfer) == (
        proto.VERDICT_BENEFIT, proto.VERDICT_TRANSFER)
    assert proto.PROTOCOL.decide(cases["tie"]).within == proto.VERDICT_TIE
    assert proto.PROTOCOL.decide(cases["no-benefit"]).within \
        == proto.VERDICT_NO_BENEFIT
    assert proto.PROTOCOL.decide(cases["no-transfer"]).transfer \
        == proto.VERDICT_NO_TRANSFER
    assert proto.PROTOCOL.decide(cases["ineligible"]).primary \
        == proto.VERDICT_INELIGIBLE


def test_an_arm_with_no_measurement_is_named_on_the_verdict():
    partial = dict.fromkeys(proto.ARMS, Fraction(1, 2))
    partial["P2"] = None

    verdict = proto.PROTOCOL.decide(_outcome(
        arm_measurements=partial, within_delta=None))

    assert verdict.unavailable_arms == ("P2",)
    assert verdict.within == proto.VERDICT_UNAVAILABLE
    assert verdict.as_dict()["unavailable_arms"] == ["P2"]
    assert "cannot be reported by omission" in proto.VERDICT_STATEMENT


def test_the_freeze_refuses_a_rebuilt_body_whose_digest_was_recorded_first():
    frozen = proto.PROTOCOL.freeze

    with pytest.raises(proto.ProtocolRefused) as caught:
        replace(frozen, freeze_digest="0" * 64)

    assert caught.value.reason == "freeze-digest-mismatch"


def test_the_endpoint_digest_is_over_the_endpoint_and_the_route_is_the_free_one():
    route = proto.FROZEN_ROUTE

    assert route.endpoint_digest == proto.digest(
        "http://localhost:4000/v1")
    assert route.requested_model == proto.REQUESTED_MODEL
    assert route.provider == "nvidia"
    assert route.tier == "free"
    with pytest.raises(proto.ProtocolRefused) as caught:
        proto.Route(endpoint=route.endpoint,
                    requested_model=route.requested_model,
                    resolved_model=route.resolved_model,
                    provider="openrouter", tier=route.tier,
                    endpoint_digest=route.endpoint_digest)
    assert caught.value.reason == "route-provider-not-the-confirmed-free-route"


def test_the_serialized_protocol_states_the_ceiling_and_the_power_shortfall():
    body = proto.PROTOCOL.as_dict()

    assert body["dispatch_ceiling"] == 96
    assert body["power"]["supports_significance"] is False
    assert body["claim"]["significant"] is False
    assert len(body["preconditions"]) == 6
    assert [(arm["name"], arm["role"], arm["control"], arm["benchmark"])
            for arm in body["arms"]] == [
        ("P0", "authored-control", True, False),
        ("P1", "acquisition", False, False),
        ("P2", "improvement", False, True)]
    assert "verified entry" not in proto.canonical(body).lower()


def test_a_verdict_can_never_carry_a_significance_claim():
    verdicts = [
        proto.PROTOCOL.decide(_outcome()),
        proto.PROTOCOL.decide(_outcome(freeze_matched=False)),
        proto.PROTOCOL.decide(_outcome(
            arm_measurements=dict.fromkeys(proto.ARMS, None),
            within_delta=None, transfer_delta=None)),
    ]

    assert all(verdict.claim.is_significant is False for verdict in verdicts)
    assert all(verdict.as_dict()["claim"]["significant"] is False
               for verdict in verdicts)
