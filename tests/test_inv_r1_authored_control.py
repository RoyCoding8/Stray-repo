"""A control arm is not a label, and the study has none.

Run 8 produced three acquired executions and no baseline, so utility was not
comparable: a claim that an acquired capability is *useful* is a claim about a
difference, and there was nothing to take the difference against. That gap is
real and it is still open. What is closed here is the claim that the
repository had a control arm. It did not.

`_v1_control_repertoire` was called by two sites, both in this file, and by
nothing else. Its members named `run_seed`, which is not in the child
namespace, so `run_member_out_of_process` raised
`NameError: name 'run_seed' is not defined` on first real use; the two members
carried byte-identical `method_source` and differed only in a `params.method`
field, which is the C15 defect this milestone exists to remove; and
`source_digest` was the sha256 of the capability id, not of the source it
declared. Three tests asserted `authored is True` and
`capability_id.startswith("seed-")` and passed against a function that could
not run. The function is deleted rather than wired, and the tests below
execute the bytes a control arm would have to execute, so the deletion cannot
be undone by a label.

What a control arm would need, measured rather than asserted. Both are in
`reviews/STAGE-09-M3-CONTROL.md`.
"""

from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

SOFTWARE_TASK = "ad01-w0-within-sw-00"
GRAPH_TASK = "ad01-w0-within-gr-00"

# A control member that names its strategy in its own body. The two members
# differ in these bytes, not in a field beside them, so the pair is distinct
# by the only measure `control_distinct` reads that is not a declared digest.
MEMBER_SOURCE = (
    "def ENTRY(task, oracle, max_queries=16):\n"
    "    return {reducer}(task, oracle, method='{method}',"
    " max_queries=max_queries)\n"
)
BUDGET = 4


def _member(capability_id: str, family: str, method: str) -> dict:
    from experiments.ad01 import method_exec

    source = MEMBER_SOURCE.format(
        reducer="reduce_software" if family == "software" else "reduce_graph",
        method=method)
    return {
        "capability_id": capability_id,
        "entry": "ENTRY",
        "method_source": source,
        "source_digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
    }


def _execute(member: dict, task_id: str):
    from experiments.ad01 import method_exec, worlds

    return method_exec.run_member_out_of_process(
        member, worlds.load_task(worlds.FROZEN_DIR, task_id),
        max_queries=BUDGET)


def test_the_study_declares_no_control_repertoire():
    """The gap stays visible, so it cannot be closed by a rename."""
    from scripts import inv01_study as S

    assert not hasattr(S, "_v1_control_repertoire")
    assert not hasattr(S, "_v1_family_world")
    assert "run_seed" not in inspect.getsource(S)
    assert "control_repertoire" not in inspect.getsource(S.run_study_v1)


def test_an_authored_control_member_executes_under_the_child_contract():
    """The bytes run, return a candidate, and spend the budget asked for."""
    for family, task_id, greedy_ops in (("software", SOFTWARE_TASK, 8),
                                        ("graph", GRAPH_TASK, 5)):
        result = _execute(_member("control-%s-greedy" % family, family,
                                  "greedy"), task_id)

        assert result["queries"] == BUDGET, (
            "%s: the member spent %d witness queries, the budget was %d"
            % (family, result["queries"], BUDGET))
        candidate = result["candidate"]
        assert candidate["task_id"] == task_id
        assert candidate["family"] == family
        if family == "software":
            assert candidate["fault"] == "stale-read"
            assert len(candidate["ops"]) == greedy_ops
        else:
            assert len(candidate["vertices"]) == greedy_ops
            assert len(candidate["edges"]) == greedy_ops


def test_the_two_control_members_are_byte_distinct_and_measure_differently():
    """C15 in one test: distinct bytes, and a difference the world can see."""
    from experiments.ad01 import control_distinctness

    for family, task_id, greedy_ops in (("software", SOFTWARE_TASK, 8),
                                        ("graph", GRAPH_TASK, 5)):
        members = [_member("control-%s-%s" % (family, method), family, method)
                   for method in ("ddmin", "greedy")]

        assert members[0]["method_source"] != members[1]["method_source"]
        assert (members[0]["source_digest"] != members[1]["source_digest"])
        for member in members:
            assert member["source_digest"] == hashlib.sha256(
                member["method_source"].encode("utf-8")).hexdigest()

        results = [_execute(member, task_id) for member in members]
        digests = [control_distinctness._digest(
            result["candidate"]) for result in results]
        assert digests[0] != digests[1], (
            "%s: both strategies returned a byte-identical candidate, so the "
            "control column is the same method twice" % family)
        assert results[0]["queries"] == results[1]["queries"] == BUDGET
        greedy = results[1]["candidate"]
        size = (len(greedy["ops"]) if family == "software"
                else len(greedy["vertices"]))
        assert size == greedy_ops, (
            "%s: greedy reduced to %d at a budget of %d, expected %d, so the "
            "budget is not reaching the reducer"
            % (family, size, BUDGET, greedy_ops))


def test_the_distinctness_gate_reads_two_real_control_records_as_distinct():
    """The gate, on executed evidence, with a control that ran."""
    from experiments.ad01 import control_distinctness, method_exec, worlds

    task_id = SOFTWARE_TASK
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    control, acquired = [], []
    for method in ("ddmin", "greedy"):
        member = _member("control-software-%s" % method, "software", method)
        result = method_exec.run_member_out_of_process(
            member, task, max_queries=BUDGET)
        control.append({
            "task_id": task_id, "executed": member["capability_id"],
            "executed_source": member["method_source"],
            "output": result["candidate"],
            "costs": {"witness_queries": result["queries"]}})
    acquired_member = _member("acquired-software-greedy", "software", "greedy")
    acquired_result = method_exec.run_member_out_of_process(
        acquired_member, task, max_queries=BUDGET)
    acquired.append({
        "task_id": task_id, "executed": acquired_member["capability_id"],
        "executed_source": acquired_member["method_source"],
        "output": acquired_result["candidate"],
        "costs": {"witness_queries": acquired_result["queries"]}})

    verdict = control_distinctness.control_distinct(control, acquired)

    assert verdict["paired_tasks"] == [task_id]
    assert verdict["same_executed_policy"] == []
    assert verdict["same_candidate"] == []
    assert verdict["differing_budget"] == []


def test_the_current_control_repertoire_bytes_are_what_the_gate_refuses():
    """Why the deleted function was the defect, as a red gate rather than prose.

    `control-sw.json` declared two members over one byte-identical source. The
    members here are those bytes, executed, and the gate refuses them.
    """
    import json

    import pytest

    from experiments.ad01 import control_distinctness, method_exec, worlds

    recorded = json.loads(
        (ROOT / "reports" / "evidence" / "inv_r1_m3b" / "repertoires"
         / "control-sw.json").read_text(encoding="utf-8"))
    source = recorded["members"][0]["method_source"]
    task_id = SOFTWARE_TASK
    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
    control = []
    for capability in recorded["members"]:
        with pytest.raises(method_exec.MethodExecutionError) as failure:
            method_exec.run_member_out_of_process(
                {"capability_id": capability["capability_id"],
                 "entry": capability["entry"],
                 "method_source": capability["method_source"],
                 "source_digest": capability["source_digest"]},
                task, max_queries=BUDGET)
        assert "run_seed" in str(failure.value)
        control.append({
            "task_id": task_id, "executed": capability["capability_id"],
            "executed_source": capability["method_source"],
            "output": {}, "costs": {"witness_queries": 0}})
    control[0]["method_source"] = source

    verdict = control_distinctness.control_distinct(control, control)

    assert verdict["distinct"] is False
    assert verdict["same_executed_policy"] == [
        {"task_id": task_id,
         "executed": sorted(m["capability_id"] for m in
                            recorded["members"])}]
    assert verdict["same_candidate"]
    assert "not distinct" in verdict["refusal"]
    assert control_distinctness._strategy_of(
        {"method_source": source}) == "", (
        "the recorded control source names no strategy, which is why the gate "
        "cannot separate two members built from it")


def test_the_seed_capabilities_are_authored_and_cover_both_families():
    """The supplied reducers, and the reason they cannot serve as a control.

    A member carrying a `seed-` id never runs its own bytes:
    `trajectory._run_member` looks the id up in `SEED_CAPABILITIES` and calls
    `seeds.run_seed` in the host instead, so the source is never staged and
    the `executed_source` on the record is the method name, not the bytes.
    That is why the deleted function's members would have measured the host's
    dispatch rather than anything in its repertoire.
    """
    from experiments.ad01 import seeds, trajectory, worlds

    families = {c["family"] for c in seeds.SEED_CAPABILITIES}
    methods = {c["method"] for c in seeds.SEED_CAPABILITIES}

    assert families == {"software", "graph"}
    assert methods == {"ddmin", "greedy"}
    assert all(c["authored"] is True for c in seeds.SEED_CAPABILITIES)

    task = worlds.load_task(worlds.FROZEN_DIR, SOFTWARE_TASK)
    result = trajectory._run_member(
        {"capability_id": "seed-sw-ddmin", "entry": "ENTRY",
         "method_source": "def ENTRY(task, oracle, max_queries=16):\n"
                          "    raise RuntimeError('these bytes must not run')\n",
         "source_digest": "0" * 64}, task, max_queries=BUDGET)

    assert result["executed_source"] == "ddmin"
    assert result["queries"] == BUDGET
