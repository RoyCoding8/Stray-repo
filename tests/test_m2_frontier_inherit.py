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
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live
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


def _probe(store, opportunity_id, x, task):
    """Run one real probe and return the observation the store recorded.

    The verdict on the returned observation is the one the instrument's own
    disagreement earned (`improve_channel.measured_verdict`), so a test that
    passes this into an operate choice is handing over what production hands
    over rather than a verdict typed next to the assertion.
    """
    outcome = channel.execute_operate_action(
        store,
        {"kind": "probe",
         "inputs": {"opportunity_id": opportunity_id, "x": x},
         "requested_resources": {"queries": 1, "steps": 1}},
        task,
    )
    assert outcome["status"] == "observed"
    return outcome


def test_frontier_choice_is_observation_dependent(tmp_path):
    store = _make_store(tmp_path)
    # A second probe on the rule `opp-first` intervenes on, so the second
    # measurement has a prior observation to disagree with. `opp-seed` sorts
    # after the others on cost, so probing it leaves `opp-first` in the
    # frontier and the refuted arm still has somewhere to move to.
    store.propose(_opportunity("opp-seed", "rule-dev-0004", 7))
    package = channel.make_control("low")
    store.bind_active(package)
    task = br.make_task("dev", 4)
    seeded = _probe(store, "opp-seed", 7, task)
    assert seeded["verdict"] == "unknown"
    refuted = _probe(store, "opp-extra", 5, task)
    # The version space fitted to (7, y) predicted a different vector at 5
    # than the instrument returned, so this observation earned `not_preserved`
    # rather than having been typed.
    assert refuted["verdict"] == "not_preserved"
    assert refuted["target"] == "rule-dev-0004"

    first_choice = _operate_choice(store, [seeded])
    second_choice = _operate_choice(store, store.observations)
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
    store.bind_active(package)
    effect = store.accept("opp-first", package["package_digest"])
    task = br.make_task("dev", 4)
    action = {
        "kind": "probe",
        "inputs": {"opportunity_id": "opp-first", "x": 3},
        "requested_resources": {"queries": 1, "steps": 1},
    }
    outcome = channel.execute_operate_action(store, action, task)
    expected = tuple((task["tables"][b] >> 3) & 1 for b in range(4))
    assert outcome["status"] == "observed"
    assert tuple(outcome["y"]) == expected
    assert outcome["observation_id"] == "obs-opp-first-x3"
    observation = next(
        o for o in store.observations
        if o["observation_id"] == outcome["observation_id"])
    assert effect["effect_id"] == "eff-opp-first-0"
    assert effect["expected_identity"]["operation_id"] == "local:eff-opp-first-0"
    assert observation["effect_id"] == effect["effect_id"]
    assert observation["operation_id"] == effect["expected_identity"][
        "operation_id"]
    store.settle(effect["effect_id"], observation)
    assert store.settled_effects[0]["effect_id"] == effect["effect_id"]
    assert store.settled_effects[0]["observation_id"] == observation[
        "observation_id"]
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
    # What the restart has to carry is the measurement itself, so that the
    # measured rule and the verdict earned on it are still there to decide
    # from. The first probe on a rule has no prior evidence to disagree
    # with, so it earns `unknown`; that is a fact about this sequence and not
    # a substitute for a refutation. The choice this test used to assert was
    # reached with no experience at all, so it pinned nothing about the
    # evidence surviving.
    survived = restarted.observations[0]
    assert survived["observation_id"] == "obs-opp-first-x3"
    assert survived["verdict"] == "unknown"
    assert survived["target"] == "rule-dev-0004"
    assert survived["x"] == 3
    assert tuple(survived["y"]) == tuple(
        (task["tables"][b] >> 3) & 1 for b in range(4))


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
    store.observe({"observation_id": "obs-followup",
                   "task": "opp-followup", "verdict": "preserved"})
    store.settle(pending["effect_id"], store.observations[-1])
    store.adopt_revision(candidate)
    assert store.active_digest == candidate["package_digest"]
    restarted = frontier.FrontierStore(str(store.path))
    restarted_pinned = restarted.settled_effects
    assert [effect["program_digest"] for effect in restarted_pinned] == [
        base["package_digest"], base["package_digest"]]
    with pytest.raises(frontier.Refused, match="active program"):
        restarted.accept("opp-extra", base["package_digest"])
    restarted._doc["pending_effects"][0]["program_digest"] = "f" * 64
    restarted.save()
    with pytest.raises(frontier.Refused, match="effect program"):
        frontier.FrontierStore(str(restarted.path))
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


def _revision_package(imp_source, parent, control_id="m2-revision"):
    """A revision differing from `parent` at exactly the probed input.

    A descendant's construction is substituted into its parent's own
    improvement source, so the interesting way to drive a second round is
    from a parent that probes something other than the incumbent. Starting
    from the low control alone would probe 3 in both rounds and the
    inheritance would be a fixed point that never has to substitute
    anything.
    """
    package = {
        "control_id": control_id, "origin": "authored-control",
        "source_kind": "fixed-menu", "op_source": parent["op_source"],
        "imp_source": imp_source,
        "op_digest": frontier.source_digest(parent["op_source"]),
        "imp_digest": frontier.source_digest(imp_source),
        "parent_digest": parent["package_digest"],
        "provenance": None, "provenance_digest": None,
        "version": int(parent["version"]) + 1,
        "authority_request": dict(parent["authority_request"]),
        "obligations": list(parent["obligations"]),
        "channel": parent["channel"], "package_digest": None}
    package["package_digest"] = frontier.package_digest(package)
    return package


def test_second_improvement_round_under_inherited_bytes(tmp_path):
    """The second round runs the first round's bytes, and inherits from them.

    The subject is durability across a restart. A candidate staged by round
    one is saved, the process is replaced by a fresh store read off disk, and
    round two executes the candidate's own bytes, not a reconstructed copy of
    them, and builds its descendant from those bytes as its parent. That part
    is unchanged and is asserted here.

    Three of the old assertions were the removed two-member menu and have been
    re-expressed. The descendant used to be required to equal
    `make_control("high")`'s improvement bytes, and the round to probe 11 and
    read back `[1, 0, 1, 1]`; those were the menu's `low`/`high` split, which
    corresponded to the observation's first bit. The construction is inherited
    instead of resolved, so what a descendant runs is the input the round
    actually probed.

    Inheriting 11 into a parent that probes 3 does reproduce the high
    control's improvement bytes, because the two authored templates differ at
    that one literal and nowhere else. So "the descendant is not a menu
    member" cannot be asserted here and is not asserted: it is a claim about
    bytes, and inheritance reaches the same bytes by a different route. The
    claim that separates the two is about reachability rather than identity,
    and it lives where two revisions are driven rather than one:
    `test_s09rev_boundary.py::test_a_descendant_runs_what_its_own_bytes_reach`
    reads each descendant's own `imp_source` and requires two revisions
    differing only in their probed input to produce descendants that can
    reach different things. A constructor resolving a menu would report one
    set for every revision and fail there.

    A round driven from the low control alone could not carry this test at
    all. It probes 3 in both rounds, so its descendant is byte-identical to
    its parent, the inheritance never has to substitute anything, and the
    cascade it is about would be a fixed point. This drives from a parent that
    probes 11, so the substitution is real and the second round has a
    different procedure to inherit.
    """
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    store.adopt_revision(
        _revision_package(channel._revision_source("11"), base))
    task = br.make_task("dev", 4)

    first = channel.drive_improve_round(store, task, round_no=1)
    candidate = first["candidate"]
    first_probed = [e["inputs"]["x"] for e in first["log"]
                    if e["action"] == "probe"]
    assert first_probed == [11], (
        "the first round did not probe the input the revision selected, so"
        " the second round would inherit a parent that never had a choice"
        " to inherit: %r" % (first_probed,))
    assert channel.reachable_evidence(candidate["imp_source"]) == ("11",), (
        "the first descendant does not run the input the round probed, so"
        " the construction did not reach it: %r"
        % (channel.reachable_evidence(candidate["imp_source"]),))
    assert channel.unauthorised_change(
        store.active_package["imp_source"], candidate["imp_source"]) == {}, (
        "the descendant differs from its parent at a decision other than the"
        " probed input, so the constructor changed more than it was asked to"
        " change: %r" % (channel.unauthorised_change(
            store.active_package["imp_source"], candidate["imp_source"]),))

    store.adopt_revision(candidate)
    store.save()
    restarted = frontier.FrontierStore(str(store.path))
    second = channel.drive_improve_round(restarted, task, round_no=2)

    probed = [e["inputs"]["x"] for e in second["log"] if e["action"] == "probe"]
    assert probed == first_probed, (
        "the second round probed %r rather than the input its inherited"
        " parent runs %r, so the round did not execute the candidate's own"
        " procedure: %r" % (probed, first_probed, candidate["control_id"]))
    assert second["candidate"]["parent_digest"] == candidate[
        "package_digest"], (
        "the second descendant does not descend from the first, so nothing"
        " was inherited: %r" % (second["candidate"]["parent_digest"],))
    executed = {e["executed_digest"] for e in second["log"]}
    assert executed == {candidate["imp_digest"]}, (
        "the second round executed bytes other than the candidate's own, so"
        " the inheritance is a reconstruction rather than a resume: %r"
        % (executed,))
    assert second["observations"][0]["y"] == first["observations"][0]["y"], (
        "the same input read back a different observation on the second"
        " round, so the two rounds are not measuring one procedure: %r vs %r"
        % (second["observations"][0]["y"], first["observations"][0]["y"]))
    assert channel.reachable_evidence(
        second["candidate"]["imp_source"]) == ("11",), (
        "the second descendant does not run the input its parent runs, so"
        " inheritance changed the procedure at a second decision: %r"
        % (channel.reachable_evidence(
            second["candidate"]["imp_source"]),))


def test_fresh_process_inherited_bytes_generate_candidate(tmp_path):
    store = _make_store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    task = br.make_task("dev", 4)
    first = channel.drive_improve_round(store, task, round_no=1)
    store.adopt_revision(first["candidate"])
    store.save()
    active_before = store.active_package
    site_packages = ROOT / ".venv" / "lib" / "python3.12" / "site-packages"
    pythonpath = [str(ROOT), str(ROOT / "src"), str(ROOT / "experiments")]
    if site_packages.exists():
        pythonpath.append(str(site_packages))
    env = {"PYTHONPATH": ":".join(pythonpath)}
    proc = subprocess.run(
        [sys.executable, "-m", "experiments.ad01.improve_channel",
         str(store.path), "2"],
        cwd=str(ROOT),
        # The child resolves its database through the environment, so the
        # environment is copied rather than replaced. A wholesale replacement
        # dropped SETTLEMENT_TEST_DSN and the child fell back to the socket
        # default at s09_run_isolation.py:41, a path the CI service does not
        # have. The copy is also what lets the child find its interpreter.
        env={**os.environ, **env},
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
    assert "rounds" not in reloaded._doc
    assert "improvement_log" not in reloaded._doc
    assert reloaded._doc["round_results"][-1]["candidate"]["control_id"] == \
        summary["candidate_id"]


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
    assert candidate["origin"] == "authored-control"
    assert candidate["source_kind"] == "fixed-menu"
    live.activate_control_revision(store, candidate)
    arm_digests = {c["package_digest"]
                   for c in store.treatment_arms["acquired"]}
    assert candidate["package_digest"] not in arm_digests
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
