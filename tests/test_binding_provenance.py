from __future__ import annotations

import json

import pytest

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import frontier as _frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live

# The charter shape `ensure_live_store` accepts, as a fixture. It was a
# production helper with no production caller, deleted in 8d354a5.
from conftest import live_mission


def _make_store(tmp_path, name="store.json"):
    path = tmp_path / name
    store = live.ensure_live_store(
        path, live_mission(
            live.LIVE_MISSION_OBJECTIVE,
            [{"instrument": "boolean-rule-v1",
              "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))
    live.propose_live_work(store, [{
        "opportunity_id": "opp-first",
        "mission_link": live.LIVE_MISSION_OBJECTIVE,
        "question": "what does input 3 reveal",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004",
                         "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}}])
    return store


def _acquired_package(store, parent, control_id, source=None):
    from settlement.gateway import ModelRequest, ModelResponse, Usage

    source = source or channel.IMPROVE_LOW_SOURCE

    class Gateway:
        def infer(self, request):
            return ModelResponse(request.operation_id,
                                 json.dumps({"entry": source}),
                                 {}, Usage(), "stop")

    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    operation_id = "op-%s" % control_id
    raw_prompt = "construct an improver"
    response = guard.infer(ModelRequest(
        model="test-model", messages=({"role": "user", "content": raw_prompt},),
        max_output_tokens=8, deadline_ms=1000, operation_id=operation_id),
        evidence={"arm": "test", "task": "rule-dev-0004", "attempt": 1,
                  "raw_prompt": raw_prompt})
    dispatch = guard.provenance(operation_id)
    package = live.parse_and_build_live_package(
        dict(parent), response.text, control_id, dispatch=dispatch)
    store.record_evidence(dispatch)
    dispatch = guard.finalize_evidence(
        operation_id, parse_outcome="accepted",
        accepted_candidate_digest=package["package_digest"],
        parsed_source_digest=package["imp_digest"],
        package_digest=package["package_digest"],
        parent_digest=package["parent_digest"], round_no=1)
    live.retain_acquired(store, package, dispatch)
    return package


def _model_package(store):
    base = channel.make_control("low")
    store.bind_active(base)
    return _acquired_package(store, base, "acquired-test-r1")


def test_retention_requires_referenced_original_dispatch(tmp_path):
    store = _make_store(tmp_path)
    package = _model_package(store)
    dispatch_digest = package["provenance"]["dispatch_evidence_digest"]
    durable = store._doc["evidence"]
    original = [record for record in durable
                if record.get("evidence_digest") == dispatch_digest]
    final = [record for record in durable
             if record.get("dispatch_evidence_digest") == dispatch_digest
             and record.get("package_digest") == package["package_digest"]]
    assert len(original) == 1
    assert len(final) == 1
    assert original[0]["receipt_identity"] != final[0]["receipt_identity"]
    store._doc["evidence"] = [
        record for record in durable
        if record.get("evidence_digest") != dispatch_digest]
    store.save()
    with pytest.raises(live.LiveRefused, match="original dispatch evidence"):
        live.retain_acquired(store, package, final[0])


def test_leaf_control_never_counts_as_acquired(tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    task = rules.make_task("dev", 4)
    candidate = live.run_live_improve_round(store, task, base, 1)[
        "candidate"]
    assert candidate["origin"] == "authored-control"
    assert candidate["source_kind"] == "fixed-menu"
    with pytest.raises(live.LiveRefused):
        live.adopt_live_revision(store, dict(candidate))
    with pytest.raises(live.LiveRefused):
        live.retain_acquired(store, dict(candidate))


def test_relabelled_control_still_refused(tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    task = rules.make_task("dev", 4)
    candidate = live.run_live_improve_round(store, task, base, 1)[
        "candidate"]
    forged = dict(candidate, origin="acquired")
    with pytest.raises(live.LiveRefused):
        live.adopt_live_revision(store, forged)
    with pytest.raises(live.LiveRefused):
        live.retain_acquired(store, forged)
    genuine = live.bind_retained_acquisition(
        str(store.path),
        {"status": "retained", "arm": "test",
          "control_id": candidate["control_id"],
         "package_digest": candidate["package_digest"]},
        task)
    assert genuine["disposition"] == "retained"


def test_unreadable_store_never_reports_bound(tmp_path):
    store = _make_store(tmp_path)
    package = _model_package(store)
    path = tmp_path / "unreadable.json"
    path.write_text("not-json")
    record = live.bind_retained_acquisition(
        str(path),
        {"status": "retained", "arm": "test",
          "control_id": package["control_id"],
         "package_digest": package["package_digest"]},
        rules.make_task("dev", 4))
    assert record["disposition"] == "retained"
    assert "unreadable" in record["reason"]


def test_digest_mismatch_refuses_adoption(tmp_path):
    store = _make_store(tmp_path)
    package = _model_package(store)
    assert package["source_kind"] == "model-response"
    tampered = dict(package, package_digest="0" * 64)
    with pytest.raises(live.LiveRefused):
        live.adopt_live_revision(store, tampered)
    record = live.bind_retained_acquisition(
        str(tmp_path / "missing.json"),
        {"status": "retained", "arm": "test",
          "control_id": package["control_id"],
         "package_digest": package["package_digest"]},
        rules.make_task("dev", 4))
    assert record["disposition"] == "retained"
    assert "unreadable" in record["reason"]


def test_retained_but_inactive_never_binds(tmp_path):
    store = _make_store(tmp_path)
    package = _model_package(store)
    task = rules.make_task("dev", 4)
    live.adopt_live_revision(store, dict(package), arm="test")
    other = _acquired_package(
        store, package, "acquired-other-r1", channel.IMPROVE_HIGH_SOURCE)
    live.adopt_live_revision(store, other, arm="test")
    store.save()
    with pytest.raises(live.LiveRefused):
        live.bind_live_revision(str(store.path), dict(package), task, "test")
    record = live.bind_retained_acquisition(
        str(store.path),
        {"status": "retained", "arm": "test",
          "control_id": package["control_id"],
         "package_digest": package["package_digest"],
         "response_digest": package["response_digest"]}, task)
    assert record["disposition"] == "retained"
    assert "differs" in record["reason"] or "parent" in record["reason"]


def test_bound_needs_post_restart_citation(tmp_path):
    store = _make_store(tmp_path)
    package = _model_package(store)
    task = rules.make_task("dev", 4)
    bound = live.adopt_live_revision(store, dict(package), arm="test")
    store.save()
    restarted = live.restart_store(str(store.path))
    assert restarted.active_digest == package["package_digest"]
    record = live.bind_retained_acquisition(
        str(store.path),
        {"status": "retained", "arm": "test",
          "control_id": package["control_id"],
         "package_digest": package["package_digest"],
         "response_digest": package["response_digest"]}, task)
    assert record["disposition"] == "bound"
    assert record["package_digest"] == package["package_digest"]
    assert record["executed_digest"] == package["imp_digest"]
    assert bound["package_digest"] == package["package_digest"]
    persisted = live.restart_store(str(store.path)).accepted_revisions[-1]
    assert persisted["receipt"]["operation_id"].startswith(
        "invl02-improve-")
    assert persisted["receipt"]["receipt_identity"] == record[
        "receipt_identity"]
    assert persisted["receipt"]["task_id"] == task["task_id"]


def test_source_log_without_child_receipt_never_binds(tmp_path, monkeypatch):
    store = _make_store(tmp_path)
    package = _model_package(store)
    live.adopt_live_revision(store, dict(package), arm="test")
    store.save()

    def receipt_free_round(*args, **kwargs):
        return {"candidate": {"control_id": "not-used"},
                "log": [{"executed_digest": package["imp_digest"],
                         "result": "observed"}],
                "receipts": []}

    monkeypatch.setattr(live, "run_live_improve_round", receipt_free_round)
    with pytest.raises(live.LiveRefused, match="child receipt"):
        live.bind_live_revision(str(store.path), dict(package),
                                rules.make_task("dev", 4), "test")


def test_noop_candidate_rejected_honestly(tmp_path):
    store = _make_store(tmp_path)
    package = _model_package(store)
    task = rules.make_task("dev", 4)
    live.adopt_live_revision(store, dict(package), arm="test")
    store.save()
    store.spend({"queries": 16, "steps": 12})
    store.save()
    with pytest.raises(live.LiveRefused) as exc:
        live.bind_live_revision(str(store.path), dict(package), task, "test")
    assert str(exc.value).startswith("rejected:")
    record = live.bind_retained_acquisition(
        str(store.path),
        {"status": "retained", "arm": "test",
          "control_id": package["control_id"],
         "package_digest": package["package_digest"],
         "response_digest": package["response_digest"]}, task)
    assert record["disposition"] == "rejected"


def test_forged_response_source_digest_refused(tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    candidate = live.run_live_improve_round(
        store, rules.make_task("dev", 4), base, 1)["candidate"]
    forged = dict(candidate, origin="acquired",
                  source_kind="model-response", response_digest="a" * 64,
                  response_source_digest="b" * 64)
    with pytest.raises(live.LiveRefused):
        live.adopt_live_revision(store, forged)
    with pytest.raises(live.LiveRefused):
        live.retain_acquired(store, forged)


def test_model_response_digest_without_dispatch_evidence_refused(tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    text = json.dumps({"entry": channel.IMPROVE_LOW_SOURCE})
    package = live.parse_and_build_live_package(
        dict(base), text, "acquired-link-r1")
    assert package["source_kind"] == "model-response"
    assert package["response_digest"] == live.response_digest(text)
    assert package["response_source_digest"] == package["imp_digest"]
    assert package["package_digest"] == _frontier.package_digest(package)
    with pytest.raises(live.LiveRefused, match="dispatch evidence"):
        live.retain_acquired(store, package)


def test_acquisition_parser_rejects_extra_response_fields():
    text = json.dumps({"entry": channel.IMPROVE_LOW_SOURCE, "forged": True})

    with pytest.raises(live.LiveRefused, match="only entry"):
        live.parse_live_improver(text)
