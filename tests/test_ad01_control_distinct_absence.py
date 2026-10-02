"""Two ways `control_distinct` reported distinct over a non-distinct pair.

Each test here is a hole that was measured on the real gate before this
file existed, and each is a case where the gate got WEAKER, not stricter.
A gate that opens because the comparison weakened is worse than a gate that
refuses, so the fix here is bounded to the two holes and the first test is
the proof that the new legs did not cost the gate its teeth.

`test_an_identical_arm_is_still_refused_on_every_leg` is that proof. It
builds the strongest possible non-distinct pair, one arm against a copy of
itself, and asserts every leg fires. If a future change weakens any leg so
that this pair passes, the gate has become vacuous and the test says so.

`test_two_ids_over_one_source_are_not_distinct` is the C15 shape. Two
different capability ids over one byte-identical `executed_source`, with
different candidates so the candidate leg cannot see it. The strategy leg
cannot see it either, because a body that names no strategy resolves to
the empty set on both arms and an empty set is not a refusal. This is the
exact column C15 is about and it reported `distinct: True`.

`test_one_arm_returning_nothing_is_not_a_difference` is the absence hole.
`_candidate_of` answers `{}` for a record carrying no output at all, so an
arm that returned nothing digested as the empty candidate and the other
arm's real bytes read as different from it. Absence is not a difference,
and the leg is now its own refusal.

`test_genuinely_distinct_arms_still_pass` is the regression in the other
direction. Two arms with different ids, different sources, and different
candidates must still report distinct, or the new legs have made the gate
refuse everything.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import control_distinctness as gates  # noqa: E402

DDMIN_SOURCE = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method='ddmin',"
    " max_queries=max_queries)\n"
)
GREEDY_SOURCE = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method='greedy',"
    " max_queries=max_queries)\n"
)
# A body that names no strategy, which is what the real acquired member is.
SILENT_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return task\n"
)


def _row(task_id, capability_id, source, output):
    return {"task_id": task_id, "executed": capability_id,
            "executed_source": source, "output": output,
            "costs": {"witness_queries": 4}}


def test_an_identical_arm_is_still_refused_on_every_leg():
    """The mutation proof: the strongest non-distinct pair still refuses.

    An arm against a copy of itself is non-distinct in every way a record
    can express. Every leg must fire, so a change that weakened any of
    them shows up here rather than in a run.
    """
    row = _row("t-0", "ctl-software-ddmin", DDMIN_SOURCE, {"ops": []})

    verdict = gates.control_distinct([row], [dict(row)])

    assert verdict["distinct"] is False
    assert verdict["same_executed_policy"], verdict
    assert verdict["same_source"], verdict
    assert verdict["same_candidate"], verdict
    assert verdict["same_strategy"], verdict
    assert "not distinct" in verdict["refusal"]


def test_two_ids_over_one_source_are_not_distinct():
    """C15: different ids, one byte-identical source, different candidates.

    The candidates differ, so the candidate leg is silent. The source names
    no strategy, so the strategy leg is silent too. Before `same_source`
    this reported `distinct: True` over two members of one program, which
    is the shape the module docstring says a digest check would have
    passed and this gate is meant to refuse.
    """
    control = [_row("t-0", "ctl-software-ddmin", SILENT_SOURCE, {"ops": [1]})]
    acquired = [_row("t-0", "acquired-sw-b0bd83b7", SILENT_SOURCE,
                     {"ops": [2]})]

    verdict = gates.control_distinct(control, acquired)

    assert verdict["distinct"] is False
    assert verdict["same_candidate"] == [], (
        "the candidates differ, so this test would be vacuous if the leg "
        "fired for the wrong reason")
    assert verdict["same_strategy"] == [], (
        "the source names no strategy, so the strategy leg cannot fire here")
    assert verdict["same_source"], verdict
    assert "byte-identical source" in verdict["refusal"]


def test_one_arm_returning_nothing_is_not_a_difference():
    """Absence is not a difference, and the gate used to read it as one.

    The control returned a candidate and the acquired arm returned no
    output at all. `_candidate_of` answers `{}` for the missing side, so
    the digests differed and the task read as distinct.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN_SOURCE, {"ops": [1]})]
    acquired = [{"task_id": "t-0", "executed": "acquired-sw-b0bd83b7",
                 "executed_source": SILENT_SOURCE,
                 "costs": {"witness_queries": 4}}]

    verdict = gates.control_distinct(control, acquired)

    assert verdict["distinct"] is False
    assert verdict["one_arm_returned_no_candidate"], verdict
    assert verdict["one_arm_returned_no_candidate"][0]["returned"] == {
        "control": True, "acquired": False}
    assert "one arm only" in verdict["refusal"]


def test_both_arms_returning_nothing_is_still_a_tie():
    """Two absent candidates are a byte-identical tie, not a pass.

    The absence leg fires when exactly one arm returned a candidate. When
    neither did, the candidate leg still refuses, so the pair is not
    waved through by the new leg.
    """
    control = [{"task_id": "t-0", "executed": "ctl-software-ddmin",
                "executed_source": DDMIN_SOURCE,
                "costs": {"witness_queries": 4}}]
    acquired = [{"task_id": "t-0", "executed": "acquired-sw-b0bd83b7",
                 "executed_source": SILENT_SOURCE,
                 "costs": {"witness_queries": 4}}]

    verdict = gates.control_distinct(control, acquired)

    assert verdict["distinct"] is False
    assert verdict["one_arm_returned_no_candidate"] == []
    assert verdict["same_candidate"], verdict


def test_genuinely_distinct_arms_still_pass():
    """The regression in the other direction.

    Different ids, byte-different sources naming different strategies, and
    different candidates. If the new legs fire here, the gate refuses
    everything and measures nothing.
    """
    control = [_row("t-0", "ctl-software-ddmin", DDMIN_SOURCE, {"ops": [1]})]
    acquired = [_row("t-0", "acquired-sw-b0bd83b7", SILENT_SOURCE,
                     {"ops": [2]})]

    verdict = gates.control_distinct(control, acquired)

    assert verdict["distinct"] is True, verdict.get("refusal")
    assert verdict["same_source"] == []
    assert verdict["one_arm_returned_no_candidate"] == []


def test_the_recorded_run_still_refuses_on_the_candidate_leg():
    """The gate against the run it was written for, at its own numbers.

    `reports/evidence/inv_r1_e1_control_arm/use_records.json` is the run
    that produced 12 byte-identical candidates. The new legs must not have
    changed that count, and the run must not be silently reclassified as
    distinct.
    """
    import json

    path = (ROOT / "reports" / "evidence" / "inv_r1_e1_control_arm"
            / "use_records.json")
    if not path.exists():
        return
    records = json.loads(path.read_text(encoding="utf-8"))
    control = [r for r in records if r.get("arm") == "C"]
    acquired = [r for r in records if r.get("arm") == "I"]

    verdict = gates.control_distinct(control, acquired)

    assert len(verdict["paired_tasks"]) == 18, verdict["paired_tasks"]
    assert verdict["distinct"] is False
    assert len(verdict["same_candidate"]) == 12, verdict["same_candidate"]
    assert len(verdict["same_source"]) == 0, (
        "the run's two arms ran byte-different sources, so `same_source` "
        "must not fire on it")
    assert len(verdict["one_arm_returned_no_candidate"]) == 0
