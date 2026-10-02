"""Contamination properties for the SWE world.

Each property from the expansion document is one test. The properties are
the whole point of this instrument, so they are asserted against the
behavior the policy actually receives, not against a description of it.
"""

from __future__ import annotations

import json

import pytest

from experiments.ad01 import s09_swe_policy as policy
from experiments.ad01 import s09_swe_tasks as tasks
from experiments.ad01 import s09_swe_world as world

POLICY_VIEW_FIELDS = (
    "action_schema",
    "entry",
    "instrument",
    "last_effect",
    "max_budget",
    "public_tests",
    "remaining",
    "source",
    "split",
    "structure",
    "symptom",
    "task_id",
)


def _session(split="held_out", template=None, mechanism=None):
    record = tasks.instance(split, template or tasks.HELD_OUT_TEMPLATES[0],
                            mechanism or tasks.HELD_OUT_MECHANISMS[0])
    return world.SweSession(record)


def _texts(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def test_the_policy_view_is_a_pinned_enumerable_field_list():
    session = _session()
    captured = []

    world.run_episode(
        lambda state: captured.append(state) or world.stop_action(),
        split="held_out", seed=0,
    )

    assert len(captured) == 1
    assert tuple(sorted(captured[0])) == POLICY_VIEW_FIELDS


def test_the_policy_view_never_carries_the_injected_fault_label():
    session = _session()
    view = _texts(session.policy_view())

    assert session._record["mechanism"] not in view
    for name in tasks.MECHANISMS:
        assert name not in view
    for program in tasks.PROGRAMS:
        for table in program.variants.values():
            for name in table:
                if name != tasks.REFERENCE_VARIANT and "_" in name:
                    continue
                assert name not in view or name in ("exclusive", "stale",
                                                    "double", "dead",
                                                    "inverted", "wide",
                                                    "reversed", "strided")
    assert tasks.FAULT_LABEL_KEYS.isdisjoint(session.policy_view())
    assert set(session.policy_view()) == set(POLICY_VIEW_FIELDS)


def test_the_policy_view_never_carries_the_hidden_patch():
    session = _session()
    view = _texts(session.policy_view())
    patch = session._record["patch"]

    assert patch
    assert "patch" not in session.policy_view()
    for edit in patch:
        assert edit["text"] not in view
        assert _texts(edit) not in view
    assert _texts(session._record["reference_source"]) not in view


def test_the_policy_view_never_carries_protected_test_answers():
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    session = world.SweSession(record)
    view = _texts(session.policy_view())
    protected = record["protected_test"]

    assert str(protected["expected"]) not in _texts(session.policy_view())
    assert "expected" not in view
    assert "protected" not in view
    public_names = {case["name"] for case in record["public_tests"]}
    assert protected["name"] not in public_names
    assert protected["name"] not in view
    assert _texts(protected["args"]) not in view
    for case in record["public_tests"]:
        assert _texts(case["args"]) in _texts(session.policy_view())


def test_no_tool_output_leaks_the_fault_mechanism_site_or_patch():
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    session = world.SweSession(record)
    leaked = []
    state: dict = {}

    def watcher(view):
        leaked.append(_texts(view))
        return policy.driven(state, view)

    world.run_episode(watcher, split="held_out", seed=0)

    patch = session._record["patch"]
    for text in leaked:
        for mechanism in tasks.MECHANISMS:
            assert mechanism not in text
        for edit in patch:
            assert edit["text"] not in text
        assert record_expected_text(session._record) not in text


def record_expected_text(record) -> str:
    return tasks.render_source(record["reference_source"])


def test_the_task_id_does_not_name_the_fault_mechanism():
    for record in tasks.enumerate_instances("held_out"):
        view = _texts(world.public_view(record))

        assert record["task_id"] not in (
            None, record["mechanism"] + "-only")
        for mechanism in tasks.MECHANISMS:
            assert mechanism not in view
            assert mechanism not in record["task_id"]


def test_localize_returns_coverage_evidence_and_never_source_text():
    session = _session()
    session.run_public_test(session._record["public_tests"][0]["name"])
    evidence = session.localize(session._record["public_tests"][0]["name"])

    assert set(evidence) == {"test", "executed_lines", "span"}
    assert evidence["executed_lines"]
    assert evidence["span"] == [min(evidence["executed_lines"]),
                                max(evidence["executed_lines"])]
    rendered = _texts(evidence)
    for line in session._record["source_text"]:
        assert line not in rendered


def test_repair_applies_the_candidate_edit_the_policy_supplied():
    session = _session()
    line = len(session._record["source"])
    supplied = [{"line": line + 5, "op": "replace", "text": "    total = 1"}]

    with pytest.raises(world.ActionRefused, match="does not exist"):
        world.apply_action(session, world.repair_action(supplied))


def test_a_supplied_edit_is_what_lands_in_the_program():
    session = _session()
    line = 1
    before = list(session.policy_view()["source"])
    supplied = [{"line": line, "op": "replace", "text": "    return 1"}]
    world.apply_action(session, world.repair_action(supplied))
    after = session.policy_view()["source"]

    assert after[line - 1]["text"] == "    return 1"
    assert after != before
    assert all(set(entry) == {"line", "text"} for entry in after)


def test_repair_refuses_to_act_without_a_policy_supplied_edit():
    session = _session()

    for payload in ({}, {"line": 4, "op": "replace"}, {"text": "    total = 1"}):
        with pytest.raises(world.ActionRefused, match="repair needs edits"):
            world.apply_action(session, world.repair_action(payload))


def test_the_module_exposes_no_callable_that_answers_the_repair():
    answerers = [
        name for name in dir(tasks)
        if not name.startswith("_")
        and callable(getattr(tasks, name))
        and name not in tasks.ASSESSOR_ENTRY_POINTS
    ]
    for name in answerers:
        assert "patch" not in name and "answer" not in name
        assert "solve" not in name and "fix" not in name

    for name in dir(world):
        if name.startswith("_") or name in world.ASSESSOR_ENTRY_POINTS:
            continue
        if callable(getattr(world, name)):
            assert "patch" not in name and "suggest" not in name
            assert "auto_repair" not in name


def test_the_policy_cannot_read_sealed_fields_off_the_task_record():
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[1],
                            tasks.HELD_OUT_MECHANISMS[1])
    session = world.SweSession(record)
    view = session.policy_view()

    assert isinstance(view, dict)
    assert view == world.public_view(record)
    assert id(view) != id(record)
    assert "reference_source" not in view
    assert "site" not in view
    for key in tasks.FAULT_LABEL_KEYS:
        assert key not in view
