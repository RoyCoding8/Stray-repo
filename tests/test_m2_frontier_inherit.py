"""M2 durable investigations and inherited improvement behavior.

Failing-first lane. The fixed task panel dictates the next work item no
matter what the program observed, and retained improvement bytes never
reach a later decision. These tests require the durable frontier
(experiments.ad01.frontier) and the improvement channel
(experiments.ad01.improve_channel). They must go red before the fix and
green after. Deterministic only: no network, no database, disposable
namespace invl02_m2.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import boolean_rule as br

FIXED_SEQUENCE = ("opp-first", "opp-followup", "opp-extra")


def fixed_next(seq):
    return FIXED_SEQUENCE[seq % len(FIXED_SEQUENCE)]


def test_fixed_panel_dictates_next_work():
    first = fixed_next(0)
    assert first == "opp-first"
    assert fixed_next(0) == first


def _mission():
    return {
        "objective": "probe boolean rules within eight queries",
        "constraints": ["deterministic only", "no live network"],
        "success_criteria": ["committed predictor"],
        "environments": [
            {"instrument": "boolean-rule-v1", "split": "dev", "seed": 4},
            {"instrument": "boolean-rule-v1", "split": "dev", "seed": 5},
        ],
    }


def _opportunity(oid, task, x, queries=1, steps=1):
    return {
        "opportunity_id": oid,
        "mission_link": "probe boolean rules within eight queries",
        "question": "what does input %d reveal on %s" % (x, task),
        "unknown": "unqueried output bits for input %d" % x,
        "intervention": {
            "instrument": "boolean-rule-v1",
            "target": task,
            "inputs": {"x": x},
        },
        "alternatives": ["probe a different input", "commit predictor"],
        "expected_consequence": "one observation narrows the version space",
        "resources": {"queries": queries, "steps": steps},
        "origin": "authored-control",
    }


def _make_store(tmp_path):
    path = tmp_path / "invl02_m2.json"
    store = frontier.create_store(
        path,
        namespace="invl02_m2",
        mission=_mission(),
        authority={"queries": 16, "steps": 12},
    )
    store.propose(_opportunity("opp-first", "rule-dev-0004", 3))
    store.propose(_opportunity("opp-followup", "rule-dev-0005", 11))
    store.propose(
        _opportunity("opp-extra", "rule-dev-0004", 5, queries=2, steps=2)
    )
    store.save()
    return store


def _operate_choice(store, experience):
    package = channel.make_control("low")
    view = store.step_view("operate", package)
    view["experience"] = list(experience)
    result = channel.run_operate_step(package, view, {})
    return result["action"]


def test_frontier_choice_is_observation_dependent(tmp_path):
    store = _make_store(tmp_path)
    mismatch = [
        {"observation_id": "obs-1", "task": "rule-dev-0004",
         "verdict": "mismatch"}
    ]
    preserved = [
        {"observation_id": "obs-1", "task": "rule-dev-0004",
         "verdict": "preserved"}
    ]
    first_choice = _operate_choice(store, preserved)
    second_choice = _operate_choice(store, mismatch)
    assert first_choice["inputs"]["opportunity_id"] == "opp-first"
    assert second_choice["inputs"]["opportunity_id"] == "opp-followup"
    assert first_choice["inputs"]["opportunity_id"] != second_choice[
        "inputs"]["opportunity_id"]
    admissible = {o["opportunity_id"] for o in store.admissible()}
    assert first_choice["inputs"]["opportunity_id"] in admissible
    assert second_choice["inputs"]["opportunity_id"] in admissible


def test_operate_probe_acquires_real_evidence_within_authority(tmp_path):
    store = _make_store(tmp_path)
    package = channel.make_control("low")
    task = br.make_task("dev", 4)
    action = {
        "kind": "probe",
        "inputs": {"opportunity_id": "opp-first", "x": 3},
        "requested_resources": {"queries": 1, "steps": 1},
    }
    outcome = channel.execute_operate_action(store, action, task)
    expected = tuple((task["tables"][b] >> 3) & 1 for b in range(4))
    assert tuple(outcome["y"]) == expected
    assert outcome["observation_id"] in {
        o["observation_id"] for o in store.observations}
    before = dict(store.authority)
    refused = channel.execute_operate_action(
        store,
        {"kind": "probe",
         "inputs": {"opportunity_id": "opp-first", "x": 4},
         "requested_resources": {"queries": 10_000, "steps": 0}},
        task,
    )
    assert refused["status"] == "refused"
    assert store.authority == before


def test_investigation_survives_restart(tmp_path):
    store = _make_store(tmp_path)
    package = channel.make_control("low")
    store.bind_active(package)
    effect = store.accept("opp-first", package["package_digest"])
    assert store.is_quiescent() is False
    task = br.make_task("dev", 4)
    channel.execute_operate_action(
        store,
        {"kind": "probe",
         "inputs": {"opportunity_id": "opp-first", "x": 3},
         "requested_resources": {"queries": 1, "steps": 1}},
        task,
    )
    store.settle(effect["effect_id"], store.observations[-1])
    store.save()
    digest_before = package["package_digest"]
    restarted = frontier.FrontierStore(str(store.path))
    assert restarted.active_digest == digest_before
    assert len(restarted.observations) == 1
    assert restarted.is_quiescent() is True
    choice = _operate_choice(
        restarted,
        [{"observation_id": restarted.observations[0]["observation_id"],
          "task": "rule-dev-0004", "verdict": "mismatch"}],
    )
    assert choice["inputs"]["opportunity_id"] == "opp-followup"


def test_improvement_channel_known_difference(tmp_path):
    store = _make_store(tmp_path)
    low = channel.make_control("low")
    high = channel.make_control("high")
    assert low["op_source"] == high["op_source"]
    assert low["imp_digest"] != high["imp_digest"]
    view = store.step_view("operate", low)
    same_view = dict(view)
    low_op = channel.run_operate_step(low, same_view, {})
    high_op = channel.run_operate_step(high, dict(view), {})
    assert low_op["action"] == high_op["action"]
    task = br.make_task("dev", 4)
    low_round = channel.drive_improve_round(store, task, package=low)
    probed_low = [e for e in low_round["log"] if e["action"] == "probe"]
    assert [e["inputs"]["x"] for e in probed_low] == [3]
    store2_path = tmp_path / "invl02_m2_b.json"
    fresh = frontier.create_store(
        store2_path,
        namespace="invl02_m2",
        mission=_mission(),
        authority={"queries": 16, "steps": 12},
    )
    high_round = channel.drive_improve_round(fresh, task, package=high)
    probed_high = [e for e in high_round["log"] if e["action"] == "probe"]
    assert [e["inputs"]["x"] for e in probed_high] == [11]
    assert low_round["observations"][0]["y"] == [1, 0, 0, 1]
    assert high_round["observations"][0]["y"] == [1, 0, 1, 1]


def test_adopt_at_quiescent_boundary_pins_history_and_resets_state(
        tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    task = br.make_task("dev", 4)
    effect = store.accept("opp-first", base["package_digest"])
    channel.execute_operate_action(
        store,
        {"kind": "probe",
         "inputs": {"opportunity_id": "opp-first", "x": 3},
         "requested_resources": {"queries": 1, "steps": 1}},
        task,
    )
    store.settle(effect["effect_id"], store.observations[-1])
    candidate = channel.drive_improve_round(store, task)["candidate"]
    assert candidate["parent_digest"] == base["package_digest"]
    store.private_state = {"scratch": "must not migrate"}
    pending = store.accept("opp-followup", base["package_digest"])
    try:
        store.adopt_revision(candidate)
    except frontier.Refused as exc:
        assert "quiescent" in str(exc)
    else:
        raise AssertionError("adoption admitted over pending effects")
    store.settle(pending["effect_id"], {"observation_id": "obs-void",
                                        "task": "rule-dev-0005",
                                        "verdict": "preserved"})
    store.adopt_revision(candidate)
    assert store.active_digest == candidate["package_digest"]
    assert store.private_state == {}
    assert store.retained["evidence_ids"] != []
    pinned = [e for e in store.settled_effects
              if e["program_digest"] == base["package_digest"]]
    assert len(pinned) == 2
    inflated = dict(candidate)
    inflated["authority_request"] = {"queries": 10_000, "steps": 10_000}
    try:
        store.adopt_revision(inflated)
    except frontier.Refused as exc:
        assert "authority" in str(exc)
    else:
        raise AssertionError("adoption admitted expanded authority")


def test_second_improvement_round_under_inherited_bytes(tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    task = br.make_task("dev", 4)
    first = channel.drive_improve_round(store, task, round_no=1)
    candidate = first["candidate"]
    assert candidate["imp_digest"] == channel.make_control("high")[
        "imp_digest"]
    store.adopt_revision(candidate)
    store.save()
    restarted = frontier.FrontierStore(str(store.path))
    second = channel.drive_improve_round(restarted, task, round_no=2)
    probed = [e for e in second["log"] if e["action"] == "probe"]
    assert [e["inputs"]["x"] for e in probed] == [11]
    assert second["candidate"]["parent_digest"] == candidate[
        "package_digest"]
    executed = {e["executed_digest"] for e in second["log"]}
    assert executed == {candidate["imp_digest"]}
    assert second["observations"][0]["y"] == [1, 0, 1, 1]


def test_fresh_process_inherited_bytes_generate_candidate(tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    task = br.make_task("dev", 4)
    first = channel.drive_improve_round(store, task, round_no=1)
    store.adopt_revision(first["candidate"])
    store.save()
    active_before = store.active_package
    env = {
        "PYTHONPATH": ":".join(
            [str(ROOT), str(ROOT / "src"), str(ROOT / "experiments")])
    }
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.improve_channel",
         str(store.path), "2"],
        cwd=str(ROOT),
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": env["PYTHONPATH"]},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["executed_digest"] == active_before["imp_digest"]
    assert summary["parent_digest"] == active_before["package_digest"]
    reloaded = frontier.FrontierStore(str(store.path))
    assert reloaded.active_digest == active_before["package_digest"]
    staged = reloaded._doc["staged_candidate"]
    assert staged["control_id"] == summary["candidate_id"]
    assert staged["parent_digest"] == active_before["package_digest"]
    assert staged["imp_source"] == active_before["imp_source"]
    assert reloaded._doc["rounds"][-1] == {
        "round": 2, "candidate_id": summary["candidate_id"],
        "parent_digest": active_before["package_digest"],
        "executed_digest": active_before["imp_digest"]}


def test_replay_supported_only_where_compatible_and_prediction_separate(
        tmp_path):
    store = _make_store(tmp_path)
    key = {"instrument": "boolean-rule-v1", "inputs": {"x": 3},
           "environment": store.environment_digest}
    store.record_outcome(key, {"y": [0, 1, 0, 1]})
    hit = store.replay({"instrument": "boolean-rule-v1",
                        "inputs": {"x": 3},
                        "environment": store.environment_digest})
    assert hit["class"] == "recorded-replay"
    assert hit["outcome"] == {"y": [0, 1, 0, 1]}
    miss = store.replay({"instrument": "boolean-rule-v1",
                         "inputs": {"x": 4},
                         "environment": store.environment_digest})
    assert miss["class"] == "unsupported"
    wrong_env = store.replay({"instrument": "boolean-rule-v1",
                              "inputs": {"x": 3},
                              "environment": "other"})
    assert wrong_env["class"] == "unsupported"
    guess = store.predict({"instrument": "boolean-rule-v1",
                           "inputs": {"x": 4},
                           "environment": store.environment_digest},
                          {"y": [1, 1, 1, 1]})
    assert guess["class"] == "prediction"
    again = store.replay({"instrument": "boolean-rule-v1",
                          "inputs": {"x": 4},
                          "environment": store.environment_digest})
    assert again["class"] == "unsupported"


def test_controls_labeled_and_outside_treatment_arms(tmp_path):
    store = _make_store(tmp_path)
    for which in ("low", "high"):
        package = channel.make_control(which)
        assert package["origin"] == "authored-control"
        assert package["control_id"].startswith("authored-control-")
    store.bind_active(channel.make_control("low"))
    task = br.make_task("dev", 4)
    candidate = channel.drive_improve_round(store, task)["candidate"]
    assert candidate["origin"] == "acquired"
    store.adopt_revision(candidate)
    arm_digests = {c["package_digest"]
                   for c in store.treatment_arms["acquired"]}
    assert candidate["package_digest"] in arm_digests
    for which in ("low", "high"):
        assert channel.make_control(which)["package_digest"] not in \
            arm_digests


def test_event_driven_readiness(tmp_path):
    store = _make_store(tmp_path)
    events = store.ready_events()
    assert "opportunity-available" in {e["type"] for e in events}
    assert store.is_quiescent() is True
    package = channel.make_control("low")
    store.bind_active(package)
    store.accept("opp-first", package["package_digest"])
    assert store.is_quiescent() is False
    pending = [e for e in store.ready_events()
               if e["type"] == "effect-pending"]
    assert len(pending) == 1
    idle = frontier.FrontierStore(str(store.path))
    assert idle.is_quiescent() is False


def test_step_view_is_purpose_bearing(tmp_path):
    store = _make_store(tmp_path)
    package = channel.make_control("low")
    operate = store.step_view("operate", package)
    assert operate["purpose"] == "operate"
    assert operate["target_digest"] == package["package_digest"]
    assert "frozen_source" not in operate
    improve = store.step_view("improve", package)
    assert improve["purpose"] == "improve"
    assert improve["frozen_source"]["imp_digest"] == package[
        "imp_digest"]
    assert improve["improvement_budget"] != {}
    assert operate["authority_remaining"] == improve[
        "authority_remaining"]
