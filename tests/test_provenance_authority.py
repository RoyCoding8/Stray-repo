from __future__ import annotations

import json

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


def test_identical_evidence_replay_returns_the_durable_record(tmp_path):
    store = _store(tmp_path)
    record = frontier.make_evidence_record(
        "m4-observation", "op-replay", "success",
        receipt_identity="receipt-replay", task_id="rule-dev-0004",
        result_digest="a" * 64)

    assert store.record_evidence(record) == record
    assert store.record_evidence(dict(record)) == record
    assert store.evidence == [record]


def test_repeated_acquisition_retention_is_idempotent(tmp_path):
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    package = _model_package(store)
    finalization = next(
        record for record in store.evidence
        if record.get("dispatch_evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    evidence_before = list(store.evidence)

    result = live.retain_acquired(store, package, finalization)

    assert result == {
        "package_digest": package["package_digest"],
        "control_id": package["control_id"]}
    assert store.evidence == evidence_before
    assert store.treatment_arms["acquired"] == [package]


@pytest.mark.parametrize("field,value", [
    ("kind", "m4-observation"),
    ("operation_id", "op-other"),
    ("attempt", 2),
    ("outcome", "failure"),
    ("arm", "P2"),
    ("task_id", "rule-dev-0005"),
    ("receipt_identity", "receipt-other"),
    ("source_digest", "1" * 64),
    ("artifact_digest", "2" * 64),
    ("input_digest", "3" * 64),
    ("result_digest", "4" * 64),
    ("package_digest", "5" * 64),
    ("parent_digest", "6" * 64),
    ("round_no", 4),
    ("dispatch_evidence_digest", "7" * 64),
    ("driver_digest", "8" * 64),
    ("operation_payload_digest", "9" * 64),
    ("parse_outcome", "parse-failed"),
    ("accepted_candidate_digest", "a" * 64),
    ("details", {"raw_payload": {"value": "other"}, "route": {}}),
])
def test_finalization_identity_digest_covers_each_identity_field(
        field, value):
    identity = {
        "kind": "gateway-dispatch",
        "operation_id": "op-finalization",
        "attempt": 1,
        "outcome": "success",
        "arm": "P1",
        "task_id": "rule-dev-0004",
        "receipt_identity": "receipt-finalization",
        "source_digest": "a" * 64,
        "artifact_digest": "b" * 64,
        "input_digest": "c" * 64,
        "result_digest": "d" * 64,
        "package_digest": "e" * 64,
        "parent_digest": "f" * 64,
        "round_no": 3,
        "dispatch_evidence_digest": "0" * 64,
        "driver_digest": "1" * 64,
        "operation_payload_digest": "2" * 64,
        "parse_outcome": "accepted",
        "accepted_candidate_digest": "3" * 64,
        "details": {"raw_payload": {"value": "first"}, "route": {
            "endpoint": "local"}},
    }
    first = frontier.make_evidence_record(**identity)
    changed = frontier.make_evidence_record(
        **{**identity, field: value})

    assert first["evidence_digest"] != changed["evidence_digest"]


@pytest.mark.parametrize("field,value", [
    ("requested_model", "other-model"),
    ("returned_model", "other-model"),
    ("endpoint", "http://other"),
    ("provider", "other"),
    ("tier", "paid"),
    ("requested_output_cap", 99),
    ("response_digest", "a" * 64),
    ("prompt_digest", "b" * 64),
    ("raw_prompt", "other prompt"),
    ("raw_response", "other response"),
    ("stop_reason", "length"),
    ("usage", {"input_tokens": 1, "output_tokens": 2,
               "charge_units": 1, "charge_scale": 1,
               "provider_enforced_ceiling": False, "billed": True}),
    ("billed", True),
    ("charge_units", 1),
    ("route_error", "other"),
    ("cost_blocked", "blocked"),
    ("response_received", True),
    ("response_status", 500),
    ("exception_class", "OtherError"),
    ("exception_reason", "other"),
    ("diagnosis", {"stage": "other"}),
])
def test_restart_refuses_mutated_finalization_response_evidence(
        tmp_path, field, value):
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    package = _model_package(store)
    finalization = next(
        record for record in store._doc["evidence"]
        if record.get("dispatch_evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    before = frontier._evidence_identity_digest(finalization)
    mutated = {**finalization, field: value}

    assert frontier._evidence_identity_digest(mutated) != before

    finalization.clear()
    finalization.update(mutated)
    finalization["evidence_digest"] = frontier._evidence_identity_digest(
        finalization)
    store.save()

    with pytest.raises(frontier.Refused, match="identity|acquisition|dispatch"):
        live.restart_store(store.path)


@pytest.mark.parametrize("usage_kwargs", [
    {"input_tokens": "not-a-number"},
    {"charge_units": "not-a-number"},
    {"billed": "not-a-boolean"},
    {"provider_enforced_ceiling": "not-a-boolean"},
])
def test_record_evidence_rejects_malformed_gateway_usage(
        tmp_path, usage_kwargs):
    from settlement.gateway import ModelRequest, ModelResponse, Usage

    store = _store(tmp_path)

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id, "response", {}, Usage(**usage_kwargs),
                "stop")

    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    request = ModelRequest(
        model="test-model", messages=(), max_output_tokens=8,
        deadline_ms=1000, operation_id="op-malformed-usage")
    guard.infer(request)
    dispatch = guard.provenance(request.operation_id)

    with pytest.raises(frontier.Refused, match="usage|charge|billed"):
        store.record_evidence(dispatch)

    assert store.evidence == []


def test_record_evidence_rejects_malformed_top_level_gateway_usage(
        tmp_path):
    store = _store(tmp_path)
    dispatch = frontier.make_evidence_record(
        "gateway-dispatch", "op-top-level-usage", "success",
        receipt_identity="receipt-top-level-usage",
        task_id="rule-dev-0004", result_digest="a" * 64,
        details={"raw_payload": {"raw_prompt": "prompt", "raw_response": "ok"}})
    dispatch["charge_units"] = "not-a-number"
    dispatch["evidence_digest"] = frontier._evidence_identity_digest(dispatch)

    with pytest.raises(frontier.Refused, match="charge"):
        store.record_evidence(dispatch)

    assert store.evidence == []


def test_restart_refuses_changed_finalization_parse_outcome(tmp_path):
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    package = _model_package(store)
    finalization = next(
        record for record in store._doc["evidence"]
        if record.get("dispatch_evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    finalization["parse_outcome"] = "parse-failed"
    store.save()

    with pytest.raises(frontier.Refused, match="identity|parse|acquisition"):
        live.restart_store(store.path)


def test_restart_revalidates_historical_accepted_revisions(tmp_path):
    """Two adopted generations, then a tampered response digest on the first.

    The subject is the restart revalidating a lineage it did not witness, so
    the two generations have to be real ones the store adopted, not a doctored
    document. It used to manufacture them with `leaf_construct("high", ...)`
    then `("low", ...)`, the two names the removed construction menu answered
    to. `leaf_construct` now refuses those names by name rather than resolving
    them against a table that no longer exists, and the pair shape it accepted
    while its caller was mid-migration is gone with the migration.

    The two generations are named the way the current constructor names one,
    by the input the construction selects, and each is read back off the
    bytes it actually built rather than off a table, so a constructor that
    resolved a menu again would build the same generation twice and the
    lineage would have nothing to revalidate.
    """
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    incumbent_x = int(channel.INCUMBENT_EVIDENCE[0])
    other_x = (incumbent_x + 1) % 16
    first = channel.leaf_construct(other_x, base, 1)
    store.adopt_revision(first)
    second = channel.leaf_construct(incumbent_x, first, 2)
    store.adopt_revision(second)

    assert first["imp_source"] != second["imp_source"], (
        "both generations built the same improvement bytes, so the lineage"
        " restart revalidates has nothing to revalidate: %r"
        % (first["control_id"],))
    assert second["parent_digest"] == first["package_digest"], (
        "the second generation does not descend from the first, so this is"
        " two unrelated adoptions rather than a lineage: %r"
        % (second["parent_digest"],))

    store._doc["accepted_revisions"][0]["response_digest"] = "f" * 64
    store.save()

    with pytest.raises(frontier.Refused, match="accepted revision|lineage"):
        live.restart_store(store.path)


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
    """The two refusals the anchor made, restated against the durable record.

    Mutation and loss are properties of the recorded raw bytes, not of a
    sibling file. The sidecar was a second file the transaction wrote with no
    share of the document's lock; the record already held the same bytes, so
    both halves now act on it.

    The forged record is resealed everywhere a competent tamperer would
    reseal -- `raw_payload_digest` and `evidence_digest` included -- which
    leaves `input_digest` and `result_digest` as the only fields standing
    between the raw bytes and a restart that believes them.
    """
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    original = next(
        record for record in store._doc["evidence"]
        if record.get("evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    live.restart_store(store.path)

    def reseal():
        original["evidence_digest"] = frontier._evidence_identity_digest(
            original)
        store._doc["evidence_projection"] = [
            {"evidence_digest": record["evidence_digest"],
             "receipt_identity": record["receipt_identity"]}
            for record in store._doc["evidence"]]

    payload = dict(original["details"]["raw_payload"])
    payload["raw_response"] = json.dumps({"entry": channel.IMPROVE_HIGH_SOURCE})
    original["details"] = dict(original["details"], raw_payload=payload)
    original["raw_payload_digest"] = frontier.source_digest(
        frontier.canonical(payload))
    reseal()
    store.save()

    with pytest.raises(frontier.Refused, match="source anchor"):
        live.restart_store(store.path)

    del original["details"]["raw_payload"]
    original["raw_payload_digest"] = frontier.source_digest(
        frontier.canonical(None))
    reseal()
    store.save()

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

    with pytest.raises(frontier.Refused, match="acquisition evidence|manifest|retained"):
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

    with pytest.raises(frontier.Refused, match="finalization|acquisition evidence|accepted revision"):
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


def _reseal_evidence(record):
    record["raw_payload_digest"] = frontier.source_digest(
        frontier.canonical(record["details"].get("raw_payload")))
    record["route_digest"] = frontier.source_digest(
        frontier.canonical(record["details"].get("route")))
    record["evidence_digest"] = frontier._evidence_identity_digest(record)
    return record


@pytest.mark.parametrize("field,value", [
    ("task_id", "task-forged"),
    ("attempt", 2),
    ("route", {"endpoint": "forged"}),
])
def test_restart_refuses_finalization_lineage_drift(tmp_path, field, value):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    record = next(
        item for item in store._doc["evidence"]
        if item.get("dispatch_evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    if field == "route":
        record["details"] = dict(record["details"], route=value)
    else:
        record[field] = value
    _reseal_evidence(record)
    store.save()

    with pytest.raises(frontier.Refused, match="dispatch evidence|acquisition evidence|projection|accepted revision"):
        live.restart_store(store.path)


def test_restart_refuses_rewritten_original_route(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    original = next(
        item for item in store._doc["evidence"]
        if item.get("evidence_digest") == package["provenance"][
            "dispatch_evidence_digest"])
    original["details"] = dict(original["details"], route={"endpoint": "forged"})
    _reseal_evidence(original)
    store.save()

    with pytest.raises(frontier.Refused, match="dispatch evidence|acquisition evidence|projection|accepted revision"):
        live.restart_store(store.path)


def test_restart_refuses_fabricated_local_post_restart_replacement(tmp_path):
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    package = _model_package(store)
    live.adopt_live_revision(store, package, arm="test")
    bound = live.bind_retained_acquisition(
        str(store.path), {"status": "retained", "arm": "test",
                          "control_id": package["control_id"],
                          "package_digest": package["package_digest"],
                          "response_digest": package["response_digest"]},
        rules.make_task("dev", 4))
    assert bound["disposition"] == "bound"
    store = live.restart_store(store.path)
    record = next(
        item for item in store._doc["accepted_revisions"]
        if item["package_digest"] == package["package_digest"])
    fabricated = dict(record["receipt"])
    fabricated["receipt_identity"] = "local:" + fabricated["receipt_identity"]
    _reseal_evidence(fabricated)
    store._doc["evidence"].append(fabricated)
    store.save()

    with pytest.raises(frontier.Refused, match="local|rollback|receipt|evidence"):
        live.restart_store(store.path)


@pytest.mark.parametrize("field,value", [
    ("retained", {"evidence_ids": ["missing"], "obligations": []}),
    ("obligations", ["valid", 3]),
    ("outcomes", {"not-canonical": 3}),
    ("mission", {"objective": "forged", "environments": []}),
])
def test_restart_revalidates_retained_projections(tmp_path, field, value):
    store = _store(tmp_path)
    if field == "retained":
        store._doc[field] = value
    elif field == "obligations":
        store._doc[field] = value
    elif field == "outcomes":
        store._doc[field] = value
    else:
        store._doc[field] = value
        store._doc["environments"] = []
        store._doc["environment_digest"] = frontier.environment_digest([])
    store.save()

    with pytest.raises(frontier.Refused, match="retained|obligation|outcome|mission"):
        live.restart_store(store.path)


def test_restart_rejects_missing_durable_evidence_projection(tmp_path):
    store = _store(tmp_path)
    evidence = frontier.make_evidence_record(
        "m4-observation", "op-projection", "success",
        task_id="rule-dev-0004", result_digest="a" * 64)
    store.record_evidence(evidence)
    store._doc["evidence"] = []
    store.save()

    with pytest.raises(frontier.Refused, match="evidence"):
        live.restart_store(store.path)
