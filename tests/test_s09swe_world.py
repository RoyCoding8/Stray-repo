from __future__ import annotations

import pytest

from experiments.ad01 import s09_swe_policy as policy
from experiments.ad01 import s09_swe_tasks as tasks
from experiments.ad01 import s09_swe_world as world

_CATALOGUE = tasks.enumerate_instances("held_out")
SEED_OF = {record["task_id"]: index
           for index, record in enumerate(_CATALOGUE)}
SLOW_SAMPLE = 8
PROGRAMS = sorted(_CATALOGUE, key=lambda record: record["task_id"])


def _action(kind, target, inputs=None):
    return {
        "kind": kind,
        "target": target,
        "inputs": {} if inputs is None else inputs,
        "evidence_refs": [],
        "requested_resources": {},
    }


def _session(record):
    return world.SweSession(record)


def test_the_public_failure_symptom_is_observable_without_the_mechanism():
    record = PROGRAMS[0]
    view = _session(record).policy_view()

    assert set(view["symptom"]) == {"coverage", "failing_tests", "observed"}
    assert view["symptom"]["failing_tests"] == []
    assert view["symptom"]["observed"] == []
    assert [case["name"] for case in view["public_tests"]] == \
        [case["name"] for case in record["public_tests"]]
    assert "mechanism" not in view["symptom"]
    for case in view["public_tests"]:
        assert set(case) == {"name", "args"}


def test_a_failing_test_shows_a_mismatch_against_a_public_expectation():
    record = PROGRAMS[0]
    session = _session(record)
    case = record["public_tests"][0]
    session.run_public_test(case["name"])
    view = session.policy_view()

    assert view["symptom"]["failing_tests"] == [{"test": case["name"],
                                                 "kind": "value"}]
    observed = view["symptom"]["observed"][0]
    assert observed["expected"] == case["expected"]
    assert observed["actual"] != case["expected"]


def test_the_location_hint_is_coarser_than_the_repair():
    record = PROGRAMS[0]
    session = _session(record)
    case = record["public_tests"][0]
    session.run_public_test(case["name"])
    evidence = session.localize(case["name"])
    patch_lines = [edit["line"] for edit in record["patch"]]

    assert evidence["executed_lines"]
    assert evidence["span"] == [min(evidence["executed_lines"]),
                                max(evidence["executed_lines"])]
    assert len(evidence["executed_lines"]) > 1
    assert len(record["source"]) > len(evidence["executed_lines"])


def test_a_policy_that_replays_a_fixed_edit_schedule_fails():
    failures = 0
    for record in PROGRAMS:
        edits = [{"line": number, "op": "replace", "text": "    pass"}
                 for number in range(1, len(record["source"]) + 1)]

        result = world.run_episode(lambda _view, edits=edits:
                                   world.repair_action(edits),
                                   split="held_out", seed=SEED_OF[record["task_id"]])
        if result["final"]["outcome"] != "repaired":
            failures += 1

    assert failures == len(PROGRAMS)


def test_a_policy_that_ignores_its_observation_and_patches_line_one_fails():
    def constant(_view):
        return world.repair_action([{"line": 1, "op": "replace",
                                     "text": '    return "x"'}])

    failures = sum(
        world.run_episode(constant, split="held_out", seed=SEED_OF[record["task_id"]])
        ["final"]["outcome"] != "repaired"
        for record in PROGRAMS
    )

    assert failures == len(PROGRAMS)


def test_a_policy_that_replays_a_fixed_action_sequence_fails():
    schedule = [
        _action("observe", "test.run", {"test": "case-01"}),
        _action("observe", "test.run", {"test": "case-02"}),
        _action("construct", "code.localize", {"test": "case-01"}),
        _action("use", "code.repair", {"edits": [
            {"line": 6, "op": "replace", "text": "    pass"}]}),
    ]
    turns = {"n": 0}

    def constant(_view):
        action = schedule[min(turns["n"], len(schedule) - 1)]
        turns["n"] += 1
        return action

    failures = sum(
        world.run_episode(constant, split="held_out", seed=SEED_OF[record["task_id"]])
        ["final"]["outcome"] != "repaired"
        for record in PROGRAMS
    )

    assert failures == len(PROGRAMS)


def test_two_different_observations_admit_two_different_actions():
    record = PROGRAMS[0]
    session = _session(record)
    before = session.policy_view()
    session.run_public_test(record["public_tests"][0]["name"])
    after = session.policy_view()

    assert before != after
    assert _admitted(session, before, record) != \
        _admitted(session, after, record)

    localize = _action("construct", "code.localize",
                       {"test": record["public_tests"][0]["name"]})
    assert not world.admits(session, before, localize)
    assert world.admits(session, after, localize)

    repair = _action("use", "code.repair",
                     {"edits": [{"line": 3, "op": "replace",
                                 "text": "    total = 0"}]})
    assert world.admits(session, before, repair)
    assert world.admits(session, after, repair)


def test_a_spent_budget_stops_admitting_that_tool():
    record = PROGRAMS[0]
    session = _session(record)
    for _ in range(world.BUDGET_LIMITS["probe"]):
        session.try_edit(1, "    pass")

    assert session.policy_view()["remaining"]["probe"] == 0
    assert "code.try" not in _admitted(session, session.policy_view(),
                                       record)
    with pytest.raises(world.ActionRefused, match="probe budget"):
        session.try_edit(1, "    pass")


def _admitted(session, view, record=None):
    names = [case["name"] for case in (record or {}).get("public_tests", [])]
    failing = [item["test"] for item in view["symptom"]["failing_tests"]]
    out = set()
    for kind, target in world.ACTION_TARGETS.items():
        candidates = [target] if isinstance(target, str) else \
            (target if isinstance(target, (list, tuple)) else [target])
        for candidate in candidates:
            inputs = _inputs_for(candidate, names, failing)
            if world.admits(session, view, _action(kind, candidate, inputs)):
                out.add(candidate)
    return out


def _inputs_for(target, names, failing):
    if target == "test.run":
        pending = [name for name in names
                   if name not in {item["test"]
                                   for item in []}] or names
        return {"test": pending[0]}
    if target == "code.localize":
        return {"test": (failing or ["case-01"])[0]}
    if target == "code.try":
        return {"line": 1, "text": "    pass"}
    if target == "code.inspect":
        return {"line": 1}
    if target == "code.repair":
        return {"edits": [{"line": 1, "op": "replace", "text": "    pass"}]}
    return {}


def test_observation_substitution_changes_the_actual_effect():
    record = PROGRAMS[0]
    first = _session(record)
    first.run_public_test(record["public_tests"][1]["name"])
    second = _session(record)
    second.run_public_test(record["public_tests"][0]["name"])

    left = first.policy_view()["symptom"]["observed"]
    right = second.policy_view()["symptom"]["observed"]

    assert [item["test"] for item in left] == [record["public_tests"][1]["name"]]
    assert [item["test"] for item in right] == [record["public_tests"][0]["name"]]
    assert left != right
    assert left[0]["actual"] != right[0]["actual"]


def test_every_held_out_instance_is_repaired_by_a_supplied_edit():
    for record in PROGRAMS:
        session = _session(record)
        world.apply_action(session, world.repair_action(record["patch"]))
        score = session.score()

        assert score["outcome"] == "repaired", record["task_id"]
        assert score["public_passed"] == len(record["public_tests"])


def test_a_searching_policy_repairs_some_but_not_every_instance():
    """The reference search is a real but bounded solver, not an oracle.

    It repairs a strict subset of the held-out split. That number is the
    point: a policy that solved everything would mean the search had been
    handed the answer, and one that solved nothing would mean the world
    gave the observation nothing to work with.
    """
    catalogue = PROGRAMS
    before = dict(world.BUDGET_LIMITS)
    try:
        outcomes = [
            world.run_episode(_searching_driver(), split="held_out",
                              seed=SEED_OF[record["task_id"]])["final"]["outcome"]
            for record in catalogue
        ]
    finally:
        world.BUDGET_LIMITS.update(before)

    repaired = outcomes.count("repaired")

    assert 0 < repaired < len(outcomes)


def _searching_driver():
    """A driver that keeps the policy's own search state between turns.

    `run_episode` hands the callback the view and nothing else, so a policy
    that searches has to carry its state in a closure. Each episode gets
    its own, or the second episode would inherit the first one's search.
    """
    state: dict = {}

    def choose(view):
        return policy.driven(state, view)

    return choose


@pytest.mark.parametrize("name,allowance", sorted(world.BUDGET_LIMITS.items()))
def test_exceeding_any_tool_budget_is_refused(name, allowance):
    record = PROGRAMS[0]
    session = _session(record)
    kind, target, inputs = _probe_for(name, record)
    refused = None
    for _ in range(allowance + 2):
        try:
            world.apply_action(session, _action(kind, target, inputs))
        except world.ActionRefused as exc:
            refused = str(exc)
            break

    assert refused is not None, "%s budget was never enforced" % name
    if name != "test":
        assert "budget" in refused


def _probe_for(name, record):
    if name == "test":
        return "observe", "test.run", {"test": record["public_tests"][0]["name"]}
    if name == "localize":
        return "construct", "code.localize", \
            {"test": record["public_tests"][0]["name"]}
    if name == "inspect":
        return "construct", "code.inspect", {"line": 1}
    if name == "probe":
        return "construct", "code.try", {"line": 1, "text": "    pass"}
    return "use", "code.repair", \
        {"edits": [{"line": 1, "op": "replace", "text": "    pass"}]}


def test_the_test_budget_covers_every_public_test_exactly_once():
    record = PROGRAMS[0]
    session = _session(record)
    names = [case["name"] for case in record["public_tests"]]

    assert world.BUDGET_LIMITS["test"] == len(names)
    for name in names:
        session.run_public_test(name)
        with pytest.raises(world.ActionRefused, match="already been run"):
            session.run_public_test(name)

    assert session.budget()["test"] == 0


def test_the_public_source_is_visible_and_editable_line_by_line():
    record = PROGRAMS[0]
    view = _session(record).policy_view()

    assert [entry["text"] for entry in view["source"]] == record["source_text"]
    assert all(set(entry) == {"line", "text"} for entry in view["source"])
    assert [entry["line"] for entry in view["source"]] == \
        list(range(1, len(record["source"]) + 1))
    assert all(edit["line"] != 1 for edit in record["patch"])


def test_repairing_with_a_harmless_edit_is_scored_honestly():
    record = PROGRAMS[0]
    session = _session(record)
    line = max(edit["line"] for edit in record["patch"])
    original = record["source_text"][line - 1]
    world.apply_action(session, world.repair_action(
        [{"line": line, "op": "replace", "text": original + "  "}]))

    score = session.score()

    assert score["outcome"] in ("unrepaired", "crashed")
    assert score["protected"]["outcome"] == "fail"


def test_a_candidate_edit_that_never_exits_is_refused_not_run():
    program = tasks.PROGRAMS_BY_NAME["scan-net"]
    lines = program.render(tasks.reference_variants(program))
    for number, line in enumerate(lines):
        if line.strip().startswith("while"):
            lines[number] = "    while state >= 0:\n"

    outcome = tasks.run_program(program, ["123", 3], lines)

    assert outcome["kind"] == "error"
    assert outcome["name"] == "NonTerminating"


def test_the_protected_test_is_never_accepted_as_a_public_test_name():
    record = PROGRAMS[0]
    session = _session(record)

    with pytest.raises(world.ActionRefused, match="not a public test"):
        session.run_public_test(record["protected_test"]["name"])
