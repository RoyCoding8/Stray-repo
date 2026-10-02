from __future__ import annotations

from pathlib import Path

import pytest

from settlement import agenda
from settlement.agenda_policy import (
    OBS_GRAMMAR_VERSION,
    POLICY_Q_VERSION,
    POLICY_R_VERSION,
    advance_cursor,
    decide_Q,
    decide_R,
    eligible,
    match_wake,
    parse_observations,
    qualify_continuation,
    rotation_order,
)
from settlement.common import SettlementError, payload_digest


def _state(**kw):
    base = {"epoch": 5, "dep_versions": {"dep-a": 3}, "spent": {},
            "caps": {}, "remaining": 64, "pending": [], "negatives": []}
    base.update(kw)
    return base


def _obs(**kw):
    base = {"prop": "p1", "scope": "s1", "dep": "dep-a", "dep_version": 3,
            "value": "true", "source_attempt": "w1", "receipt": "r1",
            "epoch": 5}
    base.update(kw)
    return base


def _question(**kw):
    base = {"prop": "p1", "scope": "s1", "dep": "dep-a"}
    base.update(kw)
    return base


def _probe(**kw):
    base = {"id": "probe-1", "question": _question(),
            "outcomes": [{"value": "true", "consequence": "go"},
                         {"value": "false", "consequence": "stop"}]}
    base.update(kw)
    return base


def _cont(**kw):
    base = {"parent_attempt": "w1", "cited": [], "decision_before": "hold",
            "decision_after": "go", "residual_question": _question(),
            "next_probe": _probe(), "cap": 8,
            "stop_condition": "either-outcome", "replication": None,
            "scope": "s1"}
    base.update(kw)
    return base


def _cite(**kw):
    base = {"prop": "p1", "scope": "s1", "dep": "dep-a", "dep_version": 3}
    base.update(kw)
    return base


def _option(**kw):
    base = {"id": "o1", "seed_class": "bottleneck", "scope": "s1",
            "kind": "initial", "disposition": "open", "prerequisites": [],
            "allocation_root": "root-a", "spent": 0, "cap": 64, "cost": 2,
            "probe_id": "probe-1"}
    base.update(kw)
    return base


def _input(candidates, observations, state, cursor=0):
    return {"candidates": candidates, "observations": observations,
            "state": state, "cursor": cursor}


def test_versions():
    assert OBS_GRAMMAR_VERSION == "AG01-OBS-1"
    assert POLICY_R_VERSION == "AG01-R-1"
    assert POLICY_Q_VERSION == "AG01-Q-2"


def test_parse_accepts_valid_and_preserves_unknown_and_simulated():
    parsed = parse_observations(
        [_obs(), _obs(prop="p2", value="unknown"),
         _obs(prop="p3", simulated=True)], 5)
    assert parsed["grammar"] == OBS_GRAMMAR_VERSION
    assert parsed["rejected"] == []
    assert parsed["conflicts"] == []
    assert [o["value"] for o in parsed["observations"]] == ["true", "unknown", "true"]
    assert parsed["observations"][2]["simulated"] is True


def test_parse_accepts_bool_values():
    parsed = parse_observations([_obs(value=True), _obs(prop="p2", value=False)], 5)
    assert [o["value"] for o in parsed["observations"]] == ["true", "false"]


def test_parse_preserves_conflict():
    parsed = parse_observations([_obs(value="true"), _obs(value="false")], 5)
    assert len(parsed["observations"]) == 2
    assert len(parsed["conflicts"]) == 1
    assert parsed["conflicts"][0]["values"] == ["false", "true"]


def test_parse_rejects_malformed_and_future_epoch():
    parsed = parse_observations(
        [{"prop": "p1"}, _obs(value="maybe"), _obs(epoch=9),
         _obs(dep_version=-1), _obs(prop="  "), "nope"], 5)
    assert len(parsed["observations"]) == 0
    assert len(parsed["rejected"]) == 6
    assert "future-epoch" in {r["reason"] for r in parsed["rejected"]}


def test_parse_rejects_non_list():
    parsed = parse_observations({"prop": "p1"}, 5)
    assert parsed["observations"] == []
    assert len(parsed["rejected"]) == 1


def test_fixture_irrelevant_observation_does_not_qualify():
    cont = _cont(cited=[_cite(scope="elsewhere")],
                 next_probe=_probe(outcomes=[{"value": "true",
                                              "consequence": "go"}]))
    obs = [_obs(scope="elsewhere")]
    verdict = qualify_continuation(cont, obs, _state())
    assert verdict == {"qualified": False, "route": None,
                       "reasons": verdict["reasons"]}
    assert not verdict["qualified"]


def test_fixture_settled_distinction_does_not_qualify():
    cont = _cont(decision_before="go", decision_after="go")
    obs = [_obs()]
    verdict = qualify_continuation(cont, obs, _state())
    assert not verdict["qualified"]
    assert any("q1:probe-misses-residual-question" in r or "q1:no-residual-matching" in r
               or "q2:no-current-decisive-in-scope-citation" in r
               for r in verdict["reasons"])


def test_fixture_off_residual_signal_fails_q1_but_anchored_probe_takes_q2():
    cont = _cont(cited=[_cite(prop="p-weak")])
    obs = [_obs(prop="p-weak")]
    verdict = qualify_continuation(cont, obs, _state())
    assert verdict["qualified"] and verdict["route"] == "Q2"
    stale = _cont(cited=[_cite(prop="p-weak", dep_version=2)])
    denied = qualify_continuation(
        stale, [_obs(prop="p-weak", dep_version=2)], _state())
    assert not denied["qualified"]
    assert any("q1:no-residual-matching-citation" in r for r in denied["reasons"])


def test_fixture_negative_observation_in_scope_qualifies_q1():
    cont = _cont(cited=[_cite()], decision_before="pursue",
                 decision_after="abandon-scope")
    obs = [_obs(value="false")]
    verdict = qualify_continuation(cont, obs, _state())
    assert verdict["qualified"] and verdict["route"] == "Q1"


def test_fixture_stale_negative_does_not_qualify():
    cont = _cont(cited=[_cite(dep_version=2)], decision_before="pursue",
                 decision_after="abandon-scope",
                 next_probe=_probe(outcomes=[{"value": "true",
                                              "consequence": "go"}]))
    obs = [_obs(dep_version=2, value="false")]
    verdict = qualify_continuation(cont, obs, _state())
    assert not verdict["qualified"]


def test_fixture_remaining_replication_qualifies_q3():
    cont = _cont(decision_before="hold", decision_after="hold",
                 next_probe=_probe(outcomes=[{"value": "true",
                                              "consequence": "go"}]),
                 replication={"protocol": "rep-p", "total": 4,
                              "completed": 1,
                              "declared_before_first_sample": True,
                              "stop_reached": False})
    verdict = qualify_continuation(cont, [], _state())
    assert verdict["qualified"] and verdict["route"] == "Q3"


def test_fixture_exhausted_replication_does_not_qualify():
    cont = _cont(decision_before="hold", decision_after="hold",
                 next_probe=_probe(outcomes=[{"value": "true",
                                              "consequence": "go"}]),
                 replication={"protocol": "rep-p", "total": 4,
                              "completed": 4,
                              "declared_before_first_sample": True,
                              "stop_reached": False})
    assert not qualify_continuation(cont, [], _state())["qualified"]
    stopped = _cont(decision_before="hold", decision_after="hold",
                    next_probe=_probe(outcomes=[{"value": "true",
                                                 "consequence": "go"}]),
                    replication={"protocol": "rep-p", "total": 4,
                                 "completed": 1,
                                 "declared_before_first_sample": True,
                                 "stop_reached": True})
    assert not qualify_continuation(stopped, [], _state())["qualified"]
    undeclared = _cont(decision_before="hold", decision_after="hold",
                       next_probe=_probe(outcomes=[{"value": "true",
                                                    "consequence": "go"}]),
                       replication={"protocol": "rep-p", "total": 4,
                                    "completed": 1,
                                    "declared_before_first_sample": False,
                                    "stop_reached": False})
    assert not qualify_continuation(undeclared, [], _state())["qualified"]


def test_paraphrase_new_id_time_passage_renamed_alternatives_fail():
    paraphrase = _cont(decision_before="hold", decision_after="hold",
                       next_probe=_probe(outcomes=[{"value": "true",
                                                    "consequence": "go"}]))
    assert not qualify_continuation(paraphrase, [], _state())["qualified"]
    new_id = _cont(cited=[_cite(prop="ghost")],
                   decision_before="hold", decision_after="hold",
                   next_probe=_probe(outcomes=[{"value": "true",
                                                "consequence": "go"}]))
    assert not qualify_continuation(new_id, [_obs()], _state())["qualified"]
    later = qualify_continuation(paraphrase, [], _state(epoch=9))
    assert not later["qualified"]
    renamed = _cont(decision_before="route-A", decision_after="route-A",
                    next_probe=_probe(outcomes=[{"value": "true",
                                                 "consequence": "go"}]))
    assert not qualify_continuation(renamed, [_obs()], _state())["qualified"]


def test_discriminating_probe_without_citation_does_not_qualify():
    cont = _cont(decision_before="hold", decision_after="hold")
    verdict = qualify_continuation(cont, [], _state())
    assert not verdict["qualified"]
    assert any("q2:no-current-decisive-in-scope-citation" in r
               for r in verdict["reasons"])


def test_discriminating_followup_with_parent_anchor_qualifies_q2():
    cont = _cont(cited=[_cite(prop="p-parent")],
                residual_question=_question(prop="p-new"),
                next_probe=_probe(question=_question(prop="p-new")),
                decision_before="hold", decision_after="hold")
    obs = [_obs(prop="p-parent")]
    verdict = qualify_continuation(cont, obs, _state())
    assert verdict["qualified"] and verdict["route"] == "Q2"


def test_changed_dependency_invalidates_old_negative():
    option = _option()
    state = _state(negatives=[{"probe": "probe-1", "scope": "s1",
                               "dep": "dep-a", "dep_version": 3}])
    blocked = eligible(option, state)
    assert not blocked["eligible"]
    assert any("negative-history-current" in r for r in blocked["reasons"])
    moved = eligible(option, _state(
        dep_versions={"dep-a": 4},
        negatives=[{"probe": "probe-1", "scope": "s1",
                    "dep": "dep-a", "dep_version": 3}]))
    assert moved["eligible"]
    assert any("stale-negative-invalidated" in r for r in moved["reasons"])
    cont = _cont(cited=[_cite()], decision_before="pursue",
                 decision_after="abandon-scope")
    assert qualify_continuation(cont, [_obs(value="false")], _state())["qualified"]
    assert not qualify_continuation(
        cont, [_obs(value="false")],
        _state(dep_versions={"dep-a": 4}))["qualified"]


def test_eligible_carries_reasons_for_every_block():
    assert eligible(_option(), _state())["eligible"]
    assert eligible(_option(), _state())["reasons"]
    cases = [
        (_option(disposition="dormant"), "disposition-dormant"),
        (_option(disposition="retired"), "disposition-retired"),
        (_option(expiry_epoch=3), "expired"),
        (_option(prerequisites=[{"dep": "dep-a", "min_version": 9}]),
         "prerequisite-missing"),
        (_option(spent=63, cost=4), "cap-exhausted"),
        (_option(cost=4), "insufficient-authority"),
        (_option(effect_identity="e1"), "pending-effect-replay"),
    ]
    states = [_state(), _state(), _state(epoch=5), _state(), _state(),
              _state(remaining=2), _state(pending=["e1"])]
    for (option, needle), state in zip(cases, states):
        result = eligible(option, state)
        assert not result["eligible"]
        assert any(needle in r for r in result["reasons"])


def test_rotation_agrees_with_seed_order():
    candidates = [{"id": f"p{i}", "seed_class": c} for i, c in
                  enumerate(["speculative", "bottleneck", "transfer",
                             "instrument-gaps", "bottleneck"])]
    for cursor in range(4):
        ours = rotation_order(list(candidates), cursor=cursor)
        theirs = agenda.seed_order(
            [{"id": c["id"], "seed_class": c["seed_class"]}
             for c in candidates], cursor=cursor)
        assert [c["id"] for c in ours["ordered"]] == \
            [c["id"] for c in theirs["ordered"]]
        assert ours["next_cursor"] == theirs["next_cursor"]


def test_rotation_rejects_unknown_class_and_bad_shape():
    with pytest.raises(SettlementError):
        rotation_order([{"id": "x", "seed_class": "fashionable"}])
    with pytest.raises(SettlementError):
        rotation_order([{"id": "x"}])


def test_advance_cursor():
    assert advance_cursor(0) == 1
    assert advance_cursor(3) == 0
    assert advance_cursor(1, 3) == 0


def test_decisions_are_deterministic_with_stable_digest():
    candidate = _option(kind="continuation", cost=2,
                        continuation=_cont(cited=[_cite()]))
    policy_input = _input([candidate], [_obs()], _state())
    first, second = decide_Q(policy_input), decide_Q(policy_input)
    assert first == second
    assert first["policy_version"] == POLICY_Q_VERSION
    assert first["decision"] == "select"
    assert first["selection"]["route"] == "Q1"
    assert first["input_digest"] == payload_digest(
        {"candidates": policy_input["candidates"],
         "observations": policy_input["observations"],
         "state": policy_input["state"], "cursor": 0,
         "tie_order": None, "grammar": OBS_GRAMMAR_VERSION})


def test_digest_changes_when_input_changes():
    candidate = _option(kind="continuation",
                        continuation=_cont(cited=[_cite()]))
    base = _input([candidate], [_obs()], _state())
    other = _input([candidate], [_obs(value="false")], _state())
    assert decide_Q(base)["input_digest"] != decide_Q(other)["input_digest"]


def test_r_and_q_diverge_only_on_continuation_qualification():
    stale = _option(kind="continuation", cost=2,
                    continuation=_cont(
                        cited=[_cite(dep_version=2)],
                        decision_before="pursue",
                        decision_after="abandon-scope",
                        next_probe=_probe(outcomes=[{"value": "true",
                                                     "consequence": "go"}])))
    policy_input = _input([stale], [_obs(dep_version=2, value="false")],
                          _state())
    chosen = decide_R(policy_input)
    held = decide_Q(policy_input)
    assert chosen["decision"] == "select"
    assert chosen["selection"]["route"] is None
    assert held["decision"] == "idle"
    assert held["selection"] is None
    assert chosen["input_digest"] == held["input_digest"]
    assert chosen["policy_version"] == POLICY_R_VERSION
    assert held["policy_version"] == POLICY_Q_VERSION
    assert any("unqualified-continuation" in str(e)
               for e in held["evaluated"])


def test_q_selectivity_loses_a_real_finding():
    pending = _option(kind="continuation", cost=2,
                      continuation=_cont(cited=[_cite()],
                                        decision_before="hold",
                                        decision_after="go"))
    first = _input([pending],
                   [_obs(value="unknown")], _state())
    assert decide_R(first)["decision"] == "select"
    assert decide_Q(first)["decision"] == "idle"
    later_obs = [_obs(value="unknown"), _obs(value="true")]
    assert qualify_continuation(
        pending["continuation"], later_obs, _state())["qualified"]
    assert not qualify_continuation(
        pending["continuation"], [_obs(value="unknown")],
        _state())["qualified"]


def test_q_applies_qualification_to_continuations_not_initials():
    fresh = _option(kind="initial")
    out = decide_Q(_input([fresh], [], _state()))
    assert out["decision"] == "select"
    assert out["selection"]["route"] is None


def test_match_wake_typed_predicates():
    assert match_wake({"type": "prerequisite-version", "name": "tool-x",
                       "min_version": 2},
                      {"kind": "prerequisite-available", "name": "tool-x",
                       "version": 3})["matched"]
    assert not match_wake({"type": "prerequisite-version", "name": "tool-x",
                           "min_version": 2},
                          {"kind": "prerequisite-available", "name": "tool-x",
                           "version": 1})["matched"]
    assert match_wake({"type": "evidence-change", "dep": "dep-a",
                       "known_version": 3},
                      {"kind": "evidence-changed", "dep": "dep-a",
                       "version": 4})["matched"]
    assert not match_wake({"type": "evidence-change", "dep": "dep-a",
                           "known_version": 3},
                          {"kind": "evidence-changed", "dep": "dep-a",
                           "version": 3})["matched"]
    assert match_wake({"type": "authorized-scan-due", "scan_id": "scan-1",
                       "due_epoch": 6},
                      {"kind": "scan-authorized", "scan_id": "scan-1",
                       "epoch": 7})["matched"]
    assert not match_wake({"type": "authorized-scan-due", "scan_id": "scan-1",
                           "due_epoch": 6},
                          {"kind": "scan-authorized", "scan_id": "scan-1",
                           "epoch": 5})["matched"]
    assert not match_wake({"type": "prerequisite-version", "name": "tool-x",
                           "min_version": 2},
                          {"kind": "evidence-changed", "dep": "dep-a",
                           "version": 9})["matched"]
    assert not match_wake({"type": "timer"}, {"kind": "tick"})["matched"]
    assert not match_wake("nope", {"kind": "tick"})["matched"]
    assert not match_wake({"type": "prerequisite-version"},
                          {"kind": "prerequisite-available",
                           "name": "tool-x", "version": 3})["matched"]


def test_policy_imports_no_hidden_state():
    import sys

    import settlement.agenda_policy as policy

    hidden = [name for name in sys.modules
              if name.startswith("settlement")
              and ("grader" in name or "latent" in name)]
    assert hidden == []
    source = Path(policy.__file__).read_text()
    assert "grader" not in source
    assert "latent" not in source
