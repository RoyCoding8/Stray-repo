from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live


def _store(tmp_path, name="store.json"):
    return live.ensure_live_store(
        tmp_path / name,
        live.live_mission(
            live.LIVE_MISSION_OBJECTIVE,
            [{"instrument": "boolean-rule-v1", "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))


def _model_package(store, control_id="acquired-authority-r1"):
    from settlement.gateway import ModelRequest, ModelResponse, Usage

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id,
                json.dumps({"entry": channel.IMPROVE_LOW_SOURCE}),
                {}, Usage(), "stop")

    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    operation_id = "op-%s" % control_id
    prompt = "construct an improver"
    response = guard.infer(ModelRequest(
        model="test-model",
        messages=({"role": "user", "content": prompt},),
        max_output_tokens=8,
        deadline_ms=1000,
        operation_id=operation_id,
    ), evidence={"arm": "test", "task": "rule-dev-0004", "attempt": 1,
                 "raw_prompt": prompt})
    dispatch = guard.provenance(operation_id)
    package = live.parse_and_build_live_package(
        store.active_package, response.text, control_id, dispatch=dispatch)
    store.record_evidence(dispatch)
    finalization = guard.finalize_evidence(
        operation_id,
        parse_outcome="accepted",
        accepted_candidate_digest=package["package_digest"],
        parsed_source_digest=package["imp_digest"],
        package_digest=package["package_digest"],
        parent_digest=package["parent_digest"],
        round_no=1)
    live.retain_acquired(store, package, finalization)
    return package


def _initial_model_package(store):
    from settlement.gateway import ModelRequest, ModelResponse, Usage

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id,
                json.dumps({"entry": channel.IMPROVE_LOW_SOURCE}),
                {}, Usage(), "stop")

    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    operation_id = "op-acquired-initial"
    prompt = "construct an initial improver"
    response = guard.infer(ModelRequest(
        model="test-model",
        messages=({"role": "user", "content": prompt},),
        max_output_tokens=8,
        deadline_ms=1000,
        operation_id=operation_id,
    ), evidence={"arm": "test", "task": "rule-dev-0004", "attempt": 1,
                 "raw_prompt": prompt})
    dispatch = guard.provenance(operation_id)
    package = live.parse_and_build_live_package(
        channel.make_control("low"), response.text,
        "acquired-initial", dispatch=dispatch)
    package["parent_digest"] = None
    package["version"] = 0
    package["package_digest"] = frontier.package_digest(package)
    finalization = guard.finalize_evidence(
        operation_id,
        parse_outcome="accepted",
        accepted_candidate_digest=package["package_digest"],
        parsed_source_digest=package["imp_digest"],
        package_digest=package["package_digest"],
        parent_digest=None,
        round_no=0)
    store.record_evidence(dispatch)
    store.record_evidence(finalization)
    return package, finalization


def _mutate_active_acquisition(store, package, field):
    mutated = dict(package)
    replacement = (channel.IMPROVE_HIGH_SOURCE if field == "imp_source"
                   else channel.SHARED_OPERATE_SOURCE + "\n")
    mutated[field] = replacement
    digest_field = "op_digest" if field == "op_source" else "imp_digest"
    mutated[digest_field] = frontier.source_digest(mutated[field])
    mutated["package_digest"] = frontier.package_digest(mutated)
    store._doc["active_package"] = dict(mutated)
    store._doc["lineage"][-1].update({
        "package_digest": mutated["package_digest"],
        "package": dict(mutated),
    })
    treatment = next(
        item for item in store._doc["treatment_arms"]["acquired"]
        if item.get("control_id") == package["control_id"])
    treatment.clear()
    treatment.update(mutated)
    revision = next(
        item for item in store._doc["accepted_revisions"]
        if item.get("package_digest") == package["package_digest"])
    revision["package_digest"] = mutated["package_digest"]
    revision["imp_digest"] = mutated["imp_digest"]
    store.save()
    return mutated


def test_bind_active_refuses_relabelled_acquired_without_evidence(tmp_path):
    store = _store(tmp_path)
    forged = dict(channel.make_control("low"),
                  origin="acquired", source_kind="model-response",
                  provenance={"authored": True})
    forged["provenance_digest"] = frontier.source_digest(
        frontier.canonical(forged["provenance"]))
    forged["package_digest"] = frontier.package_digest(forged)

    with pytest.raises(frontier.Refused, match="acquisition evidence"):
        store.bind_active(forged)

    assert store.active_package is None
    assert store.treatment_arms["acquired"] == []


def test_bind_active_accepts_acquired_only_with_durable_evidence(tmp_path):
    store = _store(tmp_path)
    package, finalization = _initial_model_package(store)

    bound = store.bind_active(
        package, acquisition_evidence=finalization)

    assert bound["package_digest"] == package["package_digest"]
    assert store.treatment_arms["acquired"] == [package]
    assert live.restart_store(store.path).active_digest == package[
        "package_digest"]


@pytest.mark.parametrize("field", ["op_source", "imp_source"])
def test_restart_refuses_coordinated_active_acquisition_mutation(
        tmp_path, field):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    mutated = _mutate_active_acquisition(store, package, field)

    with pytest.raises(
            frontier.Refused,
            match="operational lineage|acquisition evidence"):
        live.restart_store(store.path)
    result = live.bind_retained_acquisition(
        store.path,
        {"status": "retained", "arm": "test",
         "control_id": mutated["control_id"],
         "package_digest": mutated["package_digest"],
         "response_digest": mutated["response_digest"]},
        rules.make_task("dev", 4))

    assert result["disposition"] == "retained"


def test_restart_revalidates_active_bytes_against_retained_candidate(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    store.save()
    store._doc["active_package"]["op_source"] += "\n# changed"
    store.save()

    with pytest.raises(frontier.Refused, match="active package"):
        live.restart_store(store.path)
    result = live.bind_retained_acquisition(
        store.path,
        {"status": "retained", "arm": "test",
         "control_id": package["control_id"],
         "package_digest": package["package_digest"],
         "response_digest": package["response_digest"]},
        rules.make_task("dev", 4))
    assert result["disposition"] == "retained"


def test_adoption_requires_original_dispatch_and_linked_finalization(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    root_digest = package["provenance"]["dispatch_evidence_digest"]
    store._doc["evidence"] = [
        record for record in store.evidence
        if record.get("evidence_digest") != root_digest]
    store.save()

    with pytest.raises(live.LiveRefused, match="original dispatch"):
        live.adopt_live_revision(store, package, arm="test")


def test_authored_metadata_cannot_enter_acquired_treatment_arms(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    candidate = live.run_live_improve_round(
        store, rules.make_task("dev", 4), base, 1)["candidate"]
    forged = dict(candidate, origin="acquired", source_kind="model-response")

    with pytest.raises(frontier.Refused):
        store.adopt_revision(forged)

    assert store.treatment_arms["acquired"] == []


def test_evidence_identity_includes_receipt_identity(tmp_path):
    store = _store(tmp_path)
    first = frontier.make_evidence_record(
        "m4-observation", "op-same", "success", receipt_identity="receipt-a",
        task_id="rule-dev-0004", result_digest="a" * 64)
    second = frontier.make_evidence_record(
        "m4-observation", "op-same", "success", receipt_identity="receipt-b",
        task_id="rule-dev-0004", result_digest="a" * 64)

    assert first["evidence_digest"] != second["evidence_digest"]
    assert store.record_evidence(first)["receipt_identity"] == "receipt-a"
    assert store.record_evidence(second)["receipt_identity"] == "receipt-b"
    assert len(store.evidence) == 2


def test_settlement_rejects_observation_for_another_effect(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    for opportunity_id in ("opp-a", "opp-b"):
        store.propose({
            "opportunity_id": opportunity_id,
            "mission_link": live.LIVE_MISSION_OBJECTIVE,
            "question": "observe",
            "intervention": {"instrument": "boolean-rule-v1",
                             "target": "rule-dev-0004", "inputs": {}},
            "resources": {"queries": 1, "steps": 1}})
    effect_a = store.accept(
        "opp-a", base["package_digest"],
        effect_identity={"operation_id": "local:effect-a"})
    effect_b = store.accept("opp-b", base["package_digest"])

    with pytest.raises(frontier.Refused, match="target"):
        store.observe({
            "observation_id": "obs-b",
            "effect_id": effect_a["effect_id"],
            "operation_id": "local:effect-a",
            "task": "opp-b",
            "verdict": "observed"})

    observation = store.observe({
        "observation_id": "obs-b",
        "effect_id": effect_b["effect_id"],
        "operation_id": effect_b["expected_identity"]["operation_id"],
        "task": "opp-b",
        "verdict": "observed"})

    with pytest.raises(frontier.Refused, match="effect identity"):
        store.settle(effect_a["effect_id"], observation)


def test_restart_refuses_mutated_original_acquisition_evidence(tmp_path):
    store = _store(tmp_path)
    package, finalization = _initial_model_package(store)
    store.bind_active(package, acquisition_evidence=finalization)
    original = next(
        record for record in store._doc["evidence"]
        if record.get("evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    raw_payload = dict(original["details"]["raw_payload"])
    raw_payload["raw_response"] = json.dumps({"entry": channel.IMPROVE_HIGH_SOURCE})
    original["details"] = dict(original["details"], raw_payload=raw_payload)
    original["raw_payload_digest"] = frontier.source_digest(
        frontier.canonical(raw_payload))
    store.save()

    with pytest.raises(frontier.Refused, match="source anchor"):
        live.restart_store(store.path)


def test_restart_refuses_source_anchor_mutation_or_loss(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    original = next(
        record for record in store._doc["evidence"]
        if record.get("evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    anchor_path = store._source_anchor_path(original["operation_id"])
    anchor = json.loads(open(anchor_path, encoding="utf-8").read())
    anchor["raw_response"] = json.dumps({"entry": channel.IMPROVE_HIGH_SOURCE})
    open(anchor_path, "w", encoding="utf-8").write(
        frontier.canonical(anchor) + "\n")

    with pytest.raises(frontier.Refused, match="source anchor"):
        live.restart_store(store.path)

    Path(anchor_path).unlink()
    with pytest.raises(frontier.Refused, match="source anchor"):
        live.restart_store(store.path)


def test_restart_refuses_missing_initial_acquired_revision(tmp_path):
    store = _store(tmp_path)
    package, finalization = _initial_model_package(store)
    store.bind_active(package, acquisition_evidence=finalization)
    store._doc["accepted_revisions"] = []
    store.save()

    with pytest.raises(frontier.Refused, match="accepted revision"):
        live.restart_store(store.path)


def test_accept_refuses_unbound_effect(tmp_path):
    store = _store(tmp_path)
    store.propose({
        "opportunity_id": "opp-unbound",
        "mission_link": live.LIVE_MISSION_OBJECTIVE,
        "question": "observe",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {}},
        "resources": {"queries": 1, "steps": 1}})

    with pytest.raises(frontier.Refused, match="bound program"):
        store.accept("opp-unbound", "f" * 64)


def test_observation_cannot_relabel_effect_target(tmp_path):
    store = _store(tmp_path)
    package = channel.make_control("low")
    store.bind_active(package)
    for opportunity_id in ("opp-a", "opp-b"):
        store.propose({
            "opportunity_id": opportunity_id,
            "mission_link": live.LIVE_MISSION_OBJECTIVE,
            "question": "observe",
            "intervention": {"instrument": "boolean-rule-v1",
                             "target": "rule-dev-0004", "inputs": {}},
            "resources": {"queries": 1, "steps": 1}})
    effect_a = store.accept("opp-a", package["package_digest"],
                            effect_identity={"operation_id": "op-a"})
    store.accept("opp-b", package["package_digest"])

    with pytest.raises(frontier.Refused, match="target"):
        store.observe({
            "observation_id": "obs-a",
            "effect_id": effect_a["effect_id"],
            "operation_id": "op-a",
            "task": "opp-b",
            "verdict": "observed"})


@pytest.mark.parametrize("field", ["control_id", "authority_request",
                                   "obligations"])
def test_restart_refuses_coordinated_rewrite_of_material_acquisition_fields(
        tmp_path, field):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    mutated = dict(package)
    if field == "control_id":
        mutated[field] = "forged-control"
    elif field == "authority_request":
        mutated[field] = {"queries": 1, "steps": 1}
    else:
        mutated[field] = ["forged obligation"]
    mutated["package_digest"] = frontier.package_digest(mutated)
    store._doc["active_package"] = dict(mutated)
    store._doc["lineage"][-1].update({
        "package_digest": mutated["package_digest"],
        "package": dict(mutated),
    })
    treatment = next(
        item for item in store._doc["treatment_arms"]["acquired"]
        if item.get("package_digest") == package["package_digest"])
    treatment.clear()
    treatment.update(mutated)
    store.save()

    with pytest.raises(frontier.Refused, match="acquisition evidence|manifest"):
        live.restart_store(store.path)


def test_restart_refuses_rewritten_treatment_identity(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    record = next(
        item for item in store._doc["accepted_revisions"]
        if item["package_digest"] == package["package_digest"])
    record["arm"] = "forged-treatment"
    store.save()

    with pytest.raises(frontier.Refused, match="treatment|accepted revision"):
        live.restart_store(store.path)


def test_restart_refuses_rewritten_finalization_lineage(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    finalization = next(
        record for record in store._doc["evidence"]
        if record.get("dispatch_evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"]
        and record.get("package_digest") == package["package_digest"])
    finalization["round"] = 99
    finalization["evidence_digest"] = frontier._evidence_identity_digest(
        finalization)
    store.save()

    with pytest.raises(frontier.Refused, match="finalization|acquisition evidence"):
        live.restart_store(store.path)


def test_restart_revalidates_durable_child_receipt_result_bytes(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    store.propose({
        "opportunity_id": "opp-post-restart",
        "mission_link": live.LIVE_MISSION_OBJECTIVE,
        "question": "observe",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}})
    result = live.bind_retained_acquisition(
        str(store.path), {"status": "retained", "arm": "test",
                          "control_id": package["control_id"],
                          "package_digest": package["package_digest"],
                          "response_digest": package["response_digest"]},
        rules.make_task("dev", 4))
    assert result["disposition"] == "bound"
    store = live.restart_store(store.path)
    record = next(
        item for item in store._doc["accepted_revisions"]
        if item["package_digest"] == package["package_digest"])
    receipt = record["receipt"]
    raw_payload = dict(receipt["details"]["raw_payload"])
    raw_payload["action"] = {"kind": "stop", "inputs": {},
                            "requested_resources": {}}
    receipt["details"] = dict(receipt["details"], raw_payload=raw_payload)
    receipt["raw_payload_digest"] = frontier.source_digest(
        frontier.canonical(raw_payload))
    receipt["result_digest"] = frontier.source_digest(frontier.canonical({
        "action": raw_payload["action"], "state": raw_payload["state"]}))
    receipt["evidence_digest"] = frontier._evidence_identity_digest(receipt)
    store.save()

    with pytest.raises(frontier.Refused, match="child receipt|raw payload"):
        live.restart_store(store.path)


def test_restart_revalidates_post_restart_operation_and_executable_identity(
        tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    store.propose({
        "opportunity_id": "opp-post-restart",
        "mission_link": live.LIVE_MISSION_OBJECTIVE,
        "question": "observe",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}})
    live.bind_retained_acquisition(
        str(store.path), {"status": "retained", "arm": "test",
                          "control_id": package["control_id"],
                          "package_digest": package["package_digest"],
                          "response_digest": package["response_digest"]},
        rules.make_task("dev", 4))
    store = live.restart_store(store.path)
    record = next(
        item for item in store._doc["accepted_revisions"]
        if item["package_digest"] == package["package_digest"])
    record["post_restart"]["operation_ids"] = ["op-forged"]
    record["post_restart"]["executable_digest"] = "f" * 64
    store.save()

    with pytest.raises(frontier.Refused, match="post-restart|child receipt"):
        live.restart_store(store.path)
