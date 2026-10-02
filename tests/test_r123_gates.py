"""R1 R2 R3 behavioral gates on doubles only, no gateway, no database."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import frontier as _frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live
from experiments.ad01 import offline_recompute as m4
from experiments.ad01 import rule_learner
from scripts import invl02_live as driver


class _ScriptGateway:
    def __init__(self, texts=None, error=None):
        self.texts = list(texts or [])
        self.error = error
        self.requests = []

    def check_discovery(self):
        return "configured"

    def check_auth(self):
        return "authenticated"

    def cancel(self, operation_id):
        return True

    def infer(self, request):
        from settlement.gateway import GatewayError, ModelResponse, Usage
        self.requests.append(request)
        if self.error is not None:
            return self.error
        if not self.texts:
            return ModelResponse(request.operation_id, "", {}, Usage(),
                                 "stop")
        return ModelResponse(request.operation_id, self.texts.pop(0), {},
                             Usage(), "stop")


def _guard(texts=None, ceiling=12, error=None):
    return live.LiveGuard(_ScriptGateway(texts, error),
                          pinned_model="test-model", ceiling=ceiling)


def _mission():
    return {"objective": live.LIVE_MISSION_OBJECTIVE,
            "environments": [{"instrument": "boolean-rule-v1",
                              "split": "dev", "seed": 4}]}


def _opportunity(oid, task, x=3):
    return {"opportunity_id": oid,
            "mission_link": live.LIVE_MISSION_OBJECTIVE,
            "question": "what does input %d reveal on %s" % (x, task),
            "intervention": {"instrument": "boolean-rule-v1",
                             "target": task, "inputs": {"x": x}},
            "resources": {"queries": 1, "steps": 1}}


def _make_store(tmp_path, name="store.json"):
    path = tmp_path / name
    store = live.ensure_live_store(
        path, live.live_mission(
            live.LIVE_MISSION_OBJECTIVE,
            [{"instrument": "boolean-rule-v1",
              "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))
    live.propose_live_work(store, [
        _opportunity("opp-first", "rule-dev-0004", 3),
        _opportunity("opp-followup", "rule-dev-0005", 11)])
    return store


def test_r1_observation_dependent_choice(tmp_path):
    store = _make_store(tmp_path)
    package = channel.make_control("low")
    store.bind_active(package)
    preserved = [{"observation_id": "o1", "task": "rule-dev-0004",
                  "verdict": "preserved"}]
    mismatch = [{"observation_id": "o1", "task": "rule-dev-0004",
                 "verdict": "mismatch"}]
    first = live.choose_next_work(store, package, preserved)
    second = live.choose_next_work(store, package, mismatch)
    assert first["choice"] == "opp-first"
    assert second["choice"] == "opp-followup"
    assert first["choice"] != second["choice"]
    assert first["executed_digest"] == package["op_digest"]


def test_r1_second_round_after_restart(tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    task = rules.make_task("dev", 4)
    first = live.run_live_improve_round(store, task, base, 1)
    assert first["candidate"]["origin"] == "authored-control"
    assert first["candidate"]["source_kind"] == "fixed-menu"
    live.activate_control_revision(store, first["candidate"])
    store.save()
    restarted = live.restart_store(str(store.path))
    assert restarted.active_digest == store.active_digest
    active = restarted.active_package
    second = live.run_live_improve_round(restarted, task, active, 2)
    assert second["candidate"]["parent_digest"] == active[
        "package_digest"]
    assert {e["executed_digest"] for e in second["log"]} == {
        active["imp_digest"]}


def test_r1_disconnect_frontier_changes_effect(tmp_path):
    store = _make_store(tmp_path)
    package = channel.make_control("low")
    store.bind_active(package)
    intact = live.choose_next_work(
        store, package,
        [{"observation_id": "o1", "task": "rule-dev-0004",
          "verdict": "preserved"}])
    assert intact["action"]["kind"] == "investigate"
    empty_path = tmp_path / "empty.json"
    empty = live.ensure_live_store(
        empty_path, live.live_mission(
            live.LIVE_MISSION_OBJECTIVE,
            [{"instrument": "boolean-rule-v1",
              "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))
    empty.bind_active(channel.make_control("low"))
    other = live.choose_next_work(
        empty, empty.active_package,
        [{"observation_id": "o1", "task": "rule-dev-0004",
          "verdict": "preserved"}])
    assert other["action"]["kind"] == "stop"
    assert intact["action"] != other["action"]
    with pytest.raises(live.LiveRefused):
        live.choose_next_work(
            store, {**package, "package_digest": "f" * 64}, [])


def test_r1_disconnect_improvement_refused_or_changes(tmp_path):
    store = _make_store(tmp_path)
    low = channel.make_control("low")
    high = channel.make_control("high")
    assert low["op_source"] == high["op_source"]
    assert low["imp_digest"] != high["imp_digest"]
    task = rules.make_task("dev", 4)
    low_round = channel.drive_improve_round(store, task, package=low)
    assert [e["inputs"]["x"] for e in low_round["log"]
            if e["action"] == "probe"] == [3]
    fresh_path = tmp_path / "fresh.json"
    fresh = live.ensure_live_store(
        fresh_path, live.live_mission(
            live.LIVE_MISSION_OBJECTIVE,
            [{"instrument": "boolean-rule-v1",
              "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))
    high_round = channel.drive_improve_round(fresh, task, package=high)
    assert [e["inputs"]["x"] for e in high_round["log"]
            if e["action"] == "probe"] == [11]
    with pytest.raises(live.LiveRefused):
        live.parse_and_build_live_package(
            low, '{"entry": "import os"}', "acquired-bad-r1")
    with pytest.raises(live.LiveRefused):
        live.parse_and_build_live_package(
            low, '{"entry": "import os"}', "acquired-bad-r2")
    with pytest.raises(live.LiveRefused):
        live.adopt_live_revision(store, dict(low))


def test_r1_driver_routes_through_frontier(tmp_path):
    source = Path(driver.__file__).read_text()
    e0_body = source[source.index("def run_e0"):source.index(
        "def restart_use")]
    e12_body = source[source.index("def run_e12"):source.index(
        "def run_e3")]
    assert "_run_frontier_investigation" in e0_body
    assert "_run_frontier_investigation" in e12_body
    assert "_run_campaign" not in e0_body
    assert "_run_campaign" not in e12_body
    assert "observation_dependent" in e0_body
    freeze = driver.freeze_e0(tmp_path / "e0")
    record = driver._run_frontier_investigation(
        tmp_path / "frontier.json", freeze, "gate",
        guard=None, model="test-model")
    assert record["observation_dependent"] is True
    assert record["second_candidate"] != record["first_candidate"]
    assert record["adopted"]["status"] == "activated-control"


def test_r1_live_improver_via_doubles(tmp_path):
    freeze = driver.freeze_e0(tmp_path / "e0b")
    text = json.dumps({"entry": channel.IMPROVE_HIGH_SOURCE})
    guard = _guard([text], ceiling=12)
    record = driver._run_frontier_investigation(
        tmp_path / "frontier-live.json", freeze, "live",
        guard=guard, model="test-model")
    assert record["acquisition"]["status"] == "retained"
    assert guard.dispatch_count == 1
    bad = _guard(['{"entry": "import os"}'], ceiling=12)
    refused = driver._run_frontier_investigation(
        tmp_path / "frontier-bad.json", freeze, "bad",
        guard=bad, model="test-model")
    assert refused["acquisition"]["status"] == "unavailable"


def test_r2_matched_snapshots(tmp_path):
    permitted = driver._permitted_dev_history([3, 7])
    assert len(permitted) == 2
    model = "test-model"
    budget = {"max_queries": 8, "model_calls": 18, "repairs": 2}
    p1 = driver._arm_snapshot("P1", 11, [], model, budget)
    p2 = driver._arm_snapshot("P2", 11, list(permitted), model, budget)
    assert p1["solver"] == p2["solver"]
    assert p1["archive"] == p2["archive"]
    assert p1["model"] == p2["model"]
    assert p1["budget"] == p2["budget"]
    assert p1["history"] == []
    assert p2["history"] == permitted
    driver._validate_arm_histories([], list(permitted), permitted)


def test_r2_p0_on_same_held_out():
    p0_qual = driver._run_p0_boolean("qual", 11)
    p0_audit = driver._run_p0_boolean("audit", 23)
    for record in (p0_qual, p0_audit):
        assert record["model_calls"] == 0
        assert record["history_entries"] == 0
        assert record["history_tokens"] == "unknown"
        assert record["queries"] <= 8
        assert set(record["score"]) >= {"overall", "queried",
                                        "unqueried"}
        assert len(record["predictor_tables"]) == 4
        assert len(record["target_tables"]) == 4


def test_r2_counts_failures_and_leaves_unmeasured_history_tokens_unknown():
    task = rules.make_task("qual", 11)
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, 11)
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        found = session.query(pick)
        learner.observe(pick, found)
    legal = learner.predict(dict(session.queried))
    legal_json = json.dumps(
        {"specs": [dict(s) for s in legal["specs"]]})
    illegal = json.dumps(
        {"specs": [{"const": 2, "mask": 99, "pair": [0, 0]}] * 4})
    guard = _guard([illegal, legal_json], ceiling=12)
    result = driver.boolean_live_round(
        guard=guard, model="test-model", split="qual", seed=11,
        history=[{"task_id": "rule-dev-0003"}])
    assert result["failed_attempts"] == 1
    assert result["model_calls"] == 2
    assert result["history_entries"] == 1
    assert result["history_input_chars"] > 0
    assert result["history_tokens"] == "unknown"
    assert guard.dispatch_count == 2


def test_r2_swap_or_inject_refused():
    permitted = driver._permitted_dev_history([3, 7])
    with pytest.raises(live.LiveRefused):
        driver._validate_arm_histories(list(permitted), [], permitted)
    with pytest.raises(live.LiveRefused):
        driver._validate_arm_histories(list(permitted),
                                       list(permitted), permitted)
    with pytest.raises(live.LiveRefused):
        driver._validate_arm_histories([], [], permitted)
    fake_digest = "ab" * 32
    injected = list(permitted) + [{"predictor_digest": fake_digest}]
    with pytest.raises(live.LiveRefused):
        driver._validate_arm_histories([], injected, permitted)
    with pytest.raises(live.LiveRefused):
        driver._validate_arm_histories(
            [], [{"predictor_digest": fake_digest}], permitted,
            p1_digest=fake_digest)


def test_r2_driver_has_no_crosstalk(tmp_path):
    source = Path(driver.__file__).read_text()
    e12_body = source[source.index("def run_e12"):source.index(
        "def run_e3")]
    assert "_permitted_dev_history" in e12_body
    assert "_run_p0_boolean" in e12_body
    assert "_validate_arm_histories" in e12_body
    assert "_arm_snapshot" in e12_body
    assert "history = [*history" not in e12_body
    assert 'split="dev"' not in e12_body or 'held' in e12_body


def _fake_e12_bundle(tmp_path):
    out = tmp_path / "e12"
    out.mkdir()
    freeze = driver.freeze_e12(out)
    permitted = driver._permitted_dev_history([3, 7])
    held = [("qual", 11), ("audit", 23)]
    arms = {}
    durable_receipts = []
    for arm in ("P0", "P1", "P2"):
        bools = [driver._run_p0_boolean(s, v) for s, v in held]
        candidate_artifacts = []
        dispatches = []
        for index, row in enumerate(bools, start=1):
            predictor = {"specs": row["predictor_specs"]}
            raw_response = json.dumps(predictor, sort_keys=True,
                                      separators=(",", ":"))
            history = [] if arm == "P1" else permitted
            _task, session = driver._output_public_task(
                row["split"], row["seed"])
            input_digest = driver._digest({
                "task_id": row["task_id"], "split": row["split"],
                "seed": row["seed"], "history": history,
                "history_digest": driver._digest(history),
                "public_input": session.model_input()})
            prompt_digest = driver._digest("prompt:%s:%s" % (
                arm, row["task_id"]))
            evidence_digest = driver._digest("evidence:%s:%s" % (
                arm, row["task_id"]))
            operation_id = "invl02-fake-%s-%d" % (arm, index)
            candidate = {
                "arm": arm, "task_id": row["task_id"],
                "split": row["split"], "seed": row["seed"],
                "raw_response": raw_response,
                "raw_response_digest": hashlib.sha256(
                    raw_response.encode()).hexdigest(),
                "predictor": predictor,
                "predictor_digest": driver._digest(predictor),
                "input_digest": input_digest,
                "prompt_digest": prompt_digest,
                "history": history,
                "history_digest": driver._digest(history),
                "operation_id": operation_id,
                "operation_ids": [operation_id],
                "dispatch_evidence_digests": [evidence_digest]}
            row["candidate_artifact"] = candidate
            if arm in ("P1", "P2"):
                candidate_artifacts.append(candidate)
                dispatches.append({
                    "dispatch_id": "dispatch-%s-%d" % (arm, index),
                    "operation_id": operation_id,
                    "evidence_digest": evidence_digest,
                    "arm": arm, "task_id": row["task_id"],
                    "attempt": 1, "raw_response": raw_response,
                    "response_digest": candidate["raw_response_digest"],
                    "prompt_digest": prompt_digest})
                durable_result = {"raw_response": raw_response}
                durable_receipts.append({
                    "operation_id": operation_id,
                    "receipt_identity": "durable:%s" % operation_id,
                    "outcome": "success",
                    "settled": True,
                    "usable_result": True,
                    "result": durable_result,
                    "dispatch_evidence_digest": evidence_digest,
                    "input_digest": candidate["input_digest"],
                    "result_digest": driver._digest(durable_result),
                    "source_digest": candidate["predictor_digest"],
                    "artifact_digest": candidate["predictor_digest"]})
        if arm in ("P1", "P2"):
            dispatches.append({
                "dispatch_id": "dispatch-%s-3" % arm,
                "operation_id": "op-construct-%s-init" % arm,
                "evidence_digest": driver._digest("construct:%s" % arm),
                "arm": arm, "task_id": "construct-%s" % arm, "attempt": 1})
        hist_tokens = "unknown"
        program_freeze = None
        revision = "absent"
        frontier = {"effects_settled": 0}
        if arm in ("P1", "P2"):
            program_freeze = {
                "arm": arm,
                "package_digest": driver._digest("package:%s" % arm),
                "executable_digest": driver._digest("program:%s" % arm),
                "response_digest": driver._digest("response:%s" % arm),
                "dispatch_evidence_digest": driver._digest(
                    "dispatch:%s" % arm),
                "receipt_identity": "durable:program-%s" % arm,
                "frozen_before": "qualification"}
            program_freeze["freeze_digest"] = driver._digest(program_freeze)
            revision = {
                "disposition": "bound",
                "package_digest": program_freeze["package_digest"],
                "executed_digest": program_freeze["executable_digest"],
                "receipt_identity": program_freeze["receipt_identity"]}
            frontier = {
                "effects_settled": 0,
                "acquisition": {
                    "status": "retained",
                    "response_digest": program_freeze["response_digest"],
                    "dispatch_evidence_digest": program_freeze[
                        "dispatch_evidence_digest"]}}
        arms[arm] = {"status": "available",
                     "campaign_id": "doubles-%s" % arm,
                     "model_calls": 0 if arm == "P0" else 3,
                     "guard": {"pinned_model": "test-model",
                               "ceiling": 20, "dispatch_count": 0,
                               "refusal_reason": "",
                               "cost_blocked": None,
                               "version": "invl02-live-v1"},
                     "revision": revision,
                     "program_freeze": program_freeze,
                     "frontier": frontier,
                     "booleans": bools, "boolean": bools[0],
                     "candidate_artifacts": candidate_artifacts,
                     "dispatch_ledger": dispatches,
                     "snapshot": driver._arm_snapshot(
                         arm, 11,
                         [] if arm in ("P0", "P1") else list(permitted),
                         "test-model",
                         {"max_queries": 8, "model_calls": 18,
                          "repairs": 2}),
                     "history_tokens": hist_tokens,
                     "failed_attempts": 0,
                     "permitted_digest": driver._digest(permitted)}
    e12 = {"protocol": freeze["protocol"],
           "run_id": freeze["run_id"],
           "source_identity": freeze["source_identity"],
           "study": "invl02-live-e12",
           "study_root": driver.STUDY_ROOT_E12,
           "freeze_digest": freeze["freeze_digest"],
           "route": dict(freeze["route"]),
           "route_digest": driver._digest(freeze["route"]),
           "arms": arms,
           "dispatch_ledger": [
               entry for arm in ("P1", "P2")
               for entry in arms[arm]["dispatch_ledger"]],
           "durable_receipts": durable_receipts,
           "permitted_digest": driver._digest(permitted),
           "snapshots": {a: arms[a]["snapshot"] for a in arms},
           "held": [{"split": s, "seed": int(v)} for s, v in held],
           "control_boundaries": 0,
           "control": {"effects_settled": 0},
           "model_total": 6}
    (out / "e12-run.json").write_text(
        json.dumps(e12, sort_keys=True, indent=1, default=str) + "\n")
    return out


def _complete_receipt(op_id, arm, task_id, source_digest, result):
    return _frontier.make_evidence_record(
        "m4-observation", op_id, "success", arm=arm, task_id=task_id,
        source_digest=source_digest, artifact_digest=source_digest,
        input_digest=driver._digest("input:%s" % op_id),
        result_digest=driver._digest(result),
        details={"raw_payload": {"result": result}})


def _write_authoritative_ledger(out):
    e12 = json.loads((out / "e12-run.json").read_text())
    freeze = json.loads((out / "freeze.json").read_text())
    operations = {}
    child_receipts = {}

    def add(op_id, arm, task_id, source_digest, result):
        receipt = _complete_receipt(
            op_id, arm, task_id, source_digest, result)
        operations[op_id] = {"operation_id": op_id, "receipts": [receipt]}
        child_receipts[op_id] = receipt

    sources = {"P0": driver._p0_incumbent()["source_digest"]}
    candidate_sources = {}
    for arm in ("P1", "P2"):
        artifacts = e12["arms"][arm]["candidate_artifacts"]
        candidate_sources[arm] = {
            row["task_id"]: row["predictor_digest"] for row in artifacts}
        source = json.dumps(
            {"arm": arm, "candidates": candidate_sources[arm]},
            sort_keys=True, separators=(",", ":"))
        sources[arm] = live.source_digest(source)
    for index, task_id in enumerate(freeze["software_tasks"]):
        add("op-d-sw-%d" % index, "P0", task_id, sources["P0"], {
            "observed": "reduced-%s" % task_id, "queries": 2})
    for op_id in ("op-a-0", "op-t-0"):
        add(op_id, "P0", op_id.removeprefix("op-"), sources["P0"],
            {"status": "recorded"})
    for arm in ("P1", "P2"):
        op_id = "op-construct-%s-init" % arm
        add(op_id, arm, "construct-%s" % arm, sources[arm],
            {"status": "recorded"})
    for arm in ("P0", "P1", "P2"):
        for entry in e12["held"]:
            task_id = "rule-%s-%04d" % (entry["split"], int(entry["seed"]))
            prefix = "a" if entry["split"] == "qual" else "t"
            op_id = "op-use-%s-%s-%s" % (prefix, arm, task_id)
            record = next(row for row in e12["arms"][arm]["booleans"]
                          if row["task_id"] == task_id)
            observed = json.dumps(record["predictor_tables"],
                                  sort_keys=True, separators=(",", ":"))
            source = (sources[arm] if arm == "P0" else
                      candidate_sources[arm][task_id])
            add(op_id, arm, task_id, source,
                {"observed": observed, "queries": record["queries"]})
    provider_receipts = list(e12["durable_receipts"])
    for projection in provider_receipts:
        op_id = projection["operation_id"]
        result = projection["result"]
        receipt = _frontier.make_evidence_record(
            "gateway-dispatch", op_id, "success",
            receipt_identity=projection["receipt_identity"],
            arm=next(entry["arm"] for entry in e12["dispatch_ledger"]
                     if entry["operation_id"] == op_id),
            task_id=next(entry["task_id"] for entry in e12["dispatch_ledger"]
                         if entry["operation_id"] == op_id),
            source_digest=projection["source_digest"],
            artifact_digest=projection["artifact_digest"],
            input_digest=projection["input_digest"],
            result_digest=projection["result_digest"],
            dispatch_evidence_digest=projection[
                "dispatch_evidence_digest"],
            details={"raw_payload": {"result": result}})
        operations[op_id] = {"operation_id": op_id, "receipts": [receipt]}
        child_receipts[op_id] = receipt
    projections = list(provider_receipts)
    for op_id, receipt in child_receipts.items():
        if any(row["operation_id"] == op_id for row in projections):
            continue
        result = receipt["details"]["raw_payload"]["result"]
        projections.append({
            "operation_id": op_id,
            "receipt_identity": receipt["receipt_identity"],
            "outcome": receipt["outcome"],
            "settled": True,
            "usable_result": True,
            "result": result,
            "dispatch_evidence_digest": receipt[
                "dispatch_evidence_digest"],
            "input_digest": receipt["input_digest"],
            "result_digest": receipt["result_digest"],
            "source_digest": receipt["source_digest"],
            "artifact_digest": receipt["artifact_digest"]})
    e12["durable_receipts"] = projections
    for dispatch in e12["dispatch_ledger"]:
        receipt = child_receipts[dispatch["operation_id"]]
        dispatch["evidence_digest"] = (
            receipt.get("dispatch_evidence_digest")
            or receipt["evidence_digest"])
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    (out / "authoritative-operations.json").write_text(json.dumps({
        "protocol": e12["protocol"], "run_id": e12["run_id"],
        "source_identity": e12["source_identity"],
        "study": driver.STUDY_ROOT_E12,
        "study_root": driver.STUDY_ROOT_E12,
        "freeze_digest": e12["freeze_digest"],
        "route_digest": e12["route_digest"],
        "operations": operations, "child_receipts": child_receipts}) + "\n")


def test_r3_export_refuses_fabricated_success_bundle(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    with pytest.raises(ValueError, match="authoritative operation ledger"):
        driver.export_m4_bundle(out)


def test_r3_export_refuses_retired_or_mismatched_e12_root(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    freeze = json.loads((out / "freeze.json").read_text())
    e12 = json.loads((out / "e12-run.json").read_text())
    freeze["study_root"] = "invl02-live-retired"
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    e12["freeze_digest"] = freeze["freeze_digest"]
    e12["study_root"] = freeze["study_root"]
    (out / "freeze.json").write_text(json.dumps(freeze))
    (out / "e12-run.json").write_text(json.dumps(e12))
    with pytest.raises(ValueError, match="study root"):
        driver.export_m4_bundle(out)


def test_e3_refuses_retired_or_mismatched_e12_root(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    e12_dir = _fake_e12_bundle(tmp_path)
    freeze = json.loads((e12_dir / "freeze.json").read_text())
    e12 = json.loads((e12_dir / "e12-run.json").read_text())
    freeze["study_root"] = "invl02-live-retired"
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    e12["freeze_digest"] = freeze["freeze_digest"]
    e12["study_root"] = freeze["study_root"]
    (e12_dir / "freeze.json").write_text(json.dumps(freeze))
    (e12_dir / "e12-run.json").write_text(json.dumps(e12))
    out = tmp_path / "e3"
    result = driver.run_e3("unused", out, e12_dir)
    assert result["status"] == "unavailable"
    assert "study root" in result["reason"]


def test_authoritative_ledger_refuses_global_receipt_identity_collision(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    path = out / "authoritative-operations.json"
    ledger = json.loads(path.read_text())
    first_id = next(iter(ledger["operations"]))
    second_id = next(op_id for op_id in ledger["operations"]
                     if op_id != first_id)
    first = ledger["operations"][first_id]["receipts"][0]
    second = ledger["operations"][second_id]["receipts"][0]
    second["receipt_identity"] = first["receipt_identity"]
    second["evidence_digest"] = m4.source_digest(m4.canonical({
        key: second.get(key) for key in (
            "version", "kind", "operation_id", "attempt", "outcome", "arm",
            "task_id", "receipt_identity", "source_digest", "artifact_digest",
            "input_digest", "result_digest", "package_digest", "parent_digest",
            "round", "dispatch_evidence_digest", "raw_payload_digest")}))
    ledger["child_receipts"][second_id] = second
    path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match="duplicate receipt identity"):
        driver.export_m4_bundle(out)


def test_r3_export_uses_attested_child_result_not_e12_summary(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    original = e12["arms"]["P2"]["booleans"][0]["predictor_tables"]
    attested = list(original)
    e12["arms"]["P2"]["booleans"][0]["predictor_tables"] = [[
        0b1010, 0b1010, 0b1010, 0b1010]]
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    bundle = driver.export_m4_bundle(out)
    record = next(row for row in bundle["use_records"]
                  if row["arm"] == "P2")
    assert record["observed"] == json.dumps(
        attested, sort_keys=True, separators=(",", ":"))
    assert record["observed"] != json.dumps(
        [[0b1010, 0b1010, 0b1010, 0b1010]],
        sort_keys=True, separators=(",", ":"))


def test_r3_export_recomputes_candidate_from_raw_response(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    artifact = e12["arms"]["P1"]["candidate_artifacts"][0]
    artifact["raw_response"] = '{"specs": [] }'
    artifact["raw_response_digest"] = hashlib.sha256(
        artifact["raw_response"].encode()).hexdigest()
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    with pytest.raises(ValueError, match="candidate|response"):
        driver.export_m4_bundle(out)


def test_r3_export_requires_candidate_durable_dispatch_evidence(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    e12["durable_receipts"] = []
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")

    with pytest.raises(ValueError, match="receipt set.*unresolved"):
        driver.export_m4_bundle(out)


def test_r3_export_refuses_audit_fields_in_program_freeze(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    program = e12["arms"]["P1"]["program_freeze"]
    program["audit_result"] = "forged"
    program["freeze_digest"] = driver._digest({
        key: value for key, value in program.items()
        if key != "freeze_digest"})
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")

    with pytest.raises(ValueError, match="program freeze"):
        driver.export_m4_bundle(out)


def test_r3_export_refuses_duplicate_durable_receipts(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    duplicate = dict(e12["durable_receipts"][0])
    duplicate["operation_id"] = "other-operation"
    e12["durable_receipts"].append(duplicate)
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")

    with pytest.raises(ValueError, match="durable receipt"):
        driver.export_m4_bundle(out)


def test_r3_export_accounts_for_construction_repairs(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    op_id = "op-construct-P2-repair"
    receipt = _complete_receipt(
        op_id, "P2", "construct-P2", driver._digest("construct-repair"),
        {"status": "recorded"})
    ledger = json.loads((out / "authoritative-operations.json").read_text())
    ledger["operations"][op_id] = {
        "operation_id": op_id, "receipts": [receipt]}
    ledger["child_receipts"][op_id] = receipt
    (out / "authoritative-operations.json").write_text(json.dumps(ledger))
    dispatch = {
        "dispatch_id": "dispatch-P2-4", "operation_id": op_id,
        "evidence_digest": receipt.get("dispatch_evidence_digest")
        or receipt["evidence_digest"], "arm": "P2",
        "task_id": "construct-P2", "attempt": 1}
    e12["dispatch_ledger"].append(dispatch)
    e12["arms"]["P2"]["dispatch_ledger"].append(dispatch)
    result = receipt["details"]["raw_payload"]["result"]
    e12["durable_receipts"].append({
        "operation_id": op_id,
        "receipt_identity": receipt["receipt_identity"],
        "outcome": "success",
        "settled": True,
        "usable_result": True,
        "result": result,
        "dispatch_evidence_digest": receipt[
            "dispatch_evidence_digest"],
        "input_digest": receipt["input_digest"],
        "result_digest": receipt["result_digest"],
        "source_digest": receipt["source_digest"],
        "artifact_digest": receipt["artifact_digest"]})
    e12["model_total"] = 7
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")

    bundle = driver.export_m4_bundle(out)

    operations = bundle["construction"]["P2"]["operations"]
    assert {"op-construct-P2-init", "op-construct-P2-repair"} <= set(operations)
    candidate_operations = {
        op_id for row in bundle["candidates"] if row["arm"] == "P2"
        for op_id in row["operation_ids"]}
    assert {"invl02-fake-P2-1", "invl02-fake-P2-2"} <= candidate_operations
    assert candidate_operations.isdisjoint(operations)
    assert m4.verify_bundle(bundle)["status"] == "pass"


def test_r3_export_refuses_program_not_frozen_before_qualification(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12 = json.loads((out / "e12-run.json").read_text())
    del e12["arms"]["P1"]["program_freeze"]
    (out / "e12-run.json").write_text(json.dumps(e12) + "\n")
    with pytest.raises(ValueError, match="frozen before qualification"):
        driver.export_m4_bundle(out)


def test_r3_tamper_identity_fails(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    bundle["freeze"]["policy_identities"]["P1"]["source"] = "tampered"
    bundle["freeze"]["freeze_digest"] = m4.freeze_digest(
        bundle["freeze"])
    assert m4.verify_bundle(bundle)["status"] == "fail"
    assert any(p.startswith("identity-digest-mismatch P1")
               for p in m4.verify_bundle(bundle)["problems"])


def test_r3_tamper_content_fails(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    record = next(r for r in bundle["use_records"]
                  if r["arm"] == "P2")
    record["observed"] = "forged-output"
    result = m4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("quality-mismatch")
               for p in result["problems"])


def test_r3_tamper_membership_fails(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    record = next(r for r in bundle["use_records"]
                  if r["arm"] == "P1")
    record["task_id"] = "elsewhere-task"
    result = m4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("membership-unknown-task")
               for p in result["problems"])


def test_r3_tamper_costs_fails(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    record = next(r for r in bundle["use_records"]
                  if r["arm"] == "P2")
    record["costs"]["witness_queries"] = 99
    result = m4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert any(p.startswith("accounting-tool_queries-mismatch")
               for p in result["problems"])


def test_r3_tamper_results_fails(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    bundle = driver.export_m4_bundle(out)
    bundle["claimed"]["winner"] = "P1" if bundle["claimed"][
        "winner"] != "P1" else "P2"
    result = m4.verify_bundle(bundle)
    assert result["status"] == "fail"
    assert "comparison-verdict-mismatch" in result["problems"]


@pytest.mark.parametrize("runner_name, historical_root", [
    ("run_e0", "invl02-live-json"),
    ("run_e12", "invl02-live"),
])
def test_live_freeze_rejects_historical_study_root_before_authority(
        tmp_path, monkeypatch, runner_name, historical_root):
    out = tmp_path / runner_name
    out.mkdir()
    freeze = driver.freeze_e0(out) if runner_name == "run_e0" else driver.freeze_e12(out)
    freeze["study_root"] = historical_root
    freeze["freeze_digest"] = driver._digest({
        key: value for key, value in freeze.items()
        if key != "freeze_digest"})
    (out / "freeze.json").write_text(json.dumps(freeze))
    monkeypatch.setattr(driver, "_require_grant", lambda: None)
    monkeypatch.setattr(driver, "_live_model",
                        lambda: freeze["route"]["requested_model"])

    def fail_before_authority(*args, **kwargs):
        raise AssertionError("retired study root reached authority or dispatch")

    monkeypatch.setattr(driver, "_authorize", fail_before_authority)
    monkeypatch.setattr(driver, "_live_gateway", fail_before_authority)
    with pytest.raises(ValueError, match="study root"):
        getattr(driver, runner_name)("unavailable", out)


def test_r3_narrow_recompute_is_incomplete_without_dispatch_attribution(tmp_path):
    out = tmp_path / "e0only"
    out.mkdir()
    protocol = driver.freeze_e0(out)
    (out / "e0-run.json").write_text(json.dumps({
        "freeze_digest": protocol["freeze_digest"],
        "status": "available",
        "live": {"model_calls": 1}, "ledger": []}) + "\n")

    result = driver.recompute(out)

    assert result["status"] == "incomplete"
    assert result["scope"] == "E0-only-narrow-checks"
    assert any(problem.startswith("unattributed-model-calls e0-run.json")
               for problem in result["problems"])


def test_m4_recompute_preserves_verifier_fail_for_incomplete_bundle(tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    driver.export_m4_bundle(out)
    path = out / "m4-bundle.json"
    bundle = json.loads(path.read_text())
    bundle["status"] = "incomplete"
    bundle["claimed"]["winner"] = "P1"
    path.write_text(json.dumps(bundle) + "\n")

    result = driver.recompute(out)

    assert result["status"] == "fail"
    assert "comparison-verdict-mismatch" in result["problems"]


def test_m4_export_rejects_extra_e12_receipt_outside_authoritative_ledger(
        tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12_path = out / "e12-run.json"
    e12 = json.loads(e12_path.read_text())
    extra = copy.deepcopy(e12["durable_receipts"][0])
    extra["operation_id"] = "extra-operation"
    extra["receipt_identity"] = "durable:extra-operation"
    e12["durable_receipts"].append(extra)
    e12_path.write_text(json.dumps(e12) + "\n")

    with pytest.raises(ValueError, match="receipt set.*unresolved"):
        driver.export_m4_bundle(out)


def test_m4_export_rejects_missing_e12_receipt_from_authoritative_ledger(
        tmp_path):
    out = _fake_e12_bundle(tmp_path)
    _write_authoritative_ledger(out)
    e12_path = out / "e12-run.json"
    e12 = json.loads(e12_path.read_text())
    e12["durable_receipts"] = e12["durable_receipts"][1:]
    e12_path.write_text(json.dumps(e12) + "\n")

    with pytest.raises(ValueError, match="receipt set.*unresolved"):
        driver.export_m4_bundle(out)
