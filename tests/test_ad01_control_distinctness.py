"""The control must be a distinct method, and the experience must vary.

Four things are asserted here, and each replaces something that could not
have failed.

`test_inv_r1_method_menu.py::test_no_offered_reducer_defaults_to_one_strategy`
is written `assert "method=" not in signature or "ddmin" not in
signature`. That is true of every signature with no `method=` at all, and
`ddmin_reduce` has none, so it passed on the defect it was written for.
The replacement is `test_no_offered_binding_supplies_a_strategy`, below,
which reads the generated wrapper source rather than the contract's prose
and fails when a wrapper hands the callee a `method` value.

The rest are new. `control_distinct` reads the executed policy id and the
returned candidate, never a declared digest, because
`reports/evidence/inv_r1_m3b/repertoires/control-sw.json` declares two
different `source_digest` values over one byte-identical `method_source`
and neither is the sha256 of its own source. A digest-based check passes
that file. `experience_varies` counts distinct verdicts, which is the check
E2's all-`preserved` experience would have failed.

This file is new and was not in the collection of the full-suite run that
was in flight when it was written, so it is not part of that
measurement.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import control_distinctness as gates  # noqa: E402
from experiments.ad01 import method_exec  # noqa: E402

CONTROL_SW = ROOT / "reports" / "evidence" / "inv_r1_m3b" / "repertoires" / \
    "control-sw.json"

OPS = [("a", "set", "v1"), ("b", "set", "v2"), ("c", "set", "v3"),
       ("d", "set", "v4"), ("e", "set", "v5"), ("o0", "get", None)]

# The predicate a real task's checker supplies, read off the witness: a
# candidate is preserved when it still witnesses the faulty read, which
# `o0` does and no other op does. Dropping any of `a`..`e` is safe, so
# both strategies drive the candidate down to `[0, 5]`. They differ in
# what it costs to get there, 13 queries against 9, and that is the only
# sense in which the two columns are two columns.
_REQUIRED = {("a", "set"), ("o0", "get")}


def _task(task_id: str, **overrides) -> dict:
    record = {
        "task_id": task_id,
        "arm": "R",
        "executed": "seed-sw-greedy",
        "executed_source": "greedy",
        "final_measure": 3,
        "output": {"family": "software", "ops": [{"key": "a", "op": "get"}]},
    }
    record.update(overrides)
    return record


def _software_task() -> dict:
    return {
        "family": "software", "task_id": "t", "fault": "stale-read",
        "ops": [{"key": key, "op": op, **({"value": value}
                                          if value is not None else {}),
                 **({"id": key} if op == "get" else {})}
                for key, op, value in OPS],
        "witness": {"faulty": {"type": "str", "value": "v1"},
                    "observation": "o0",
                    "ref": {"type": "str", "value": "v3"}},
    }


class _Oracle:
    """The real checker behind the host's protocol, so a reducer drives it.

    `experiments.representation.checkers.SoftwareOracle.query` is what the
    child driver answers with, and a hand-written predicate here would
    have been a second implementation of the verdict. Whatever predicate
    this test needs is expressed as a software task the real checker
    grades, not as a stand-in for one.
    """

    def __init__(self, task, max_queries=64, check=None):
        from experiments.representation import checkers
        self.oracle = checkers.SoftwareOracle(task, max_queries=max_queries)
        self._check = check
        self.queries = 0

    def query(self, candidate):
        self.queries += 1
        if self._check is not None:
            return self._check(candidate)
        self.oracle.query(candidate)
        return {"verdict": "preserved", "measure": 0, "reason": "test"}


# --- the menu -------------------------------------------------------------


def test_no_offered_binding_supplies_a_strategy():
    """The replacement for the vacuous signature test.

    It reads the bytes the child actually executes. A wrapper that passes
    `method=...` gives every acquisition the authored answer without its
    model choosing one, which is what the old assertion could not see: it
    read the contract's prose, and the prose for `reduce_software` already
    said there was no default while the wrapper said `ddmin`.
    """
    source = method_exec._child_wrapper_source()
    for name in ("reduce_software", "reduce_graph"):
        wrapper = _wrapper_of(source, name)
        assert not re.search(r"method\s*=\s*[^,\n)]+", wrapper), (
            "%s defaults the strategy: %s" % (name, wrapper))
    for method, primitive in method_exec._STRATEGY_METHODS.items():
        others = [other for other in method_exec._STRATEGY_METHODS
                  if other != method]
        for other in others:
            wrapper = _wrapper_of(source, primitive)
            assert not re.search(
                r"method\s*=\s*[\"']%s[\"']" % other, wrapper), (
                "%s defaults to %s: %s" % (primitive, other, wrapper))
        composed = _wrapper_of(source, "%s__%s" % (method, primitive))
        assert "method=%r" % method in composed, (
            "the composed entry for %s does not commit to it: %s"
            % (method, composed))


def _wrapper_of(source: str, name: str) -> str:
    match = re.search(r"^def %s\(.*?(?=\n\ndef |\Z)" % re.escape(name),
                      source, re.M | re.S)
    assert match is not None, (
        "no wrapper generated for %s:\n%s" % (name, source))
    return match.group(0)


def test_a_member_omitting_the_strategy_fails_and_naming_it_works():
    """The refusal the contract promises, measured by calling the wrapper.

    `reduce_software(task, oracle)` used to return a greedy reduction. It
    now raises, because the only value for `method` is the model's. A
    test asserting the callable exists could never have caught that, and
    this one fails if anyone puts a default back.
    """
    wrappers = _namespace()
    task = _software_task()

    try:
        wrappers["reduce_software"](task, _Oracle(task), max_queries=16)
    except TypeError as exc:
        assert "method" in str(exc), (
            "the wrapper failed for the wrong reason: %s" % exc)
    else:
        raise AssertionError(
            "reduce_software(task, oracle, max_queries=16) returned a"
            " candidate with no method named; the wrapper still answers"
            " for the model")

    for method in ("ddmin", "greedy"):
        result = wrappers["reduce_software"](
            task, _Oracle(task), max_queries=16, method=method)
        assert result["candidate"]["family"] == "software", method


def test_the_frozen_world_separates_the_two_strategies():
    """The world can tell the two strategies apart, so a control can too.

    The measurement that matters for E1: across the 54-task frozen world
    at budgets 8, 16, 32 and 64, `ddmin` and `greedy` reach different
    candidates on 108 of 216 pairs and cost a different number of queries
    on 119. A control column drawn from these two reducers can therefore
    separate them, at every budget measured, so the E1 tie is not a
    property of the world.

    This is the check that caught a defect in this lane. The adapter
    built here first wrapped the oracle report in a second
    `{"verdict": ...}`; the reducers subscript `probe(...)["verdict"]`
    and compare it with the string `preserved`, so the comparison was
    always false, every primitive returned the incumbent after one query,
    and all 54 tasks looked identical. `experiments/ad01/method_exec.py`
    `__probe` now passes the report through, as `reduce_software` does.
    The assertion is on the count, so a regression to the double-wrap
    fails here rather than being read as a property of the world.
    """
    from experiments.ad01 import method_exec, worlds
    from experiments.representation import checkers, reducers

    namespace = {"reducers": reducers}
    exec(method_exec._child_wrapper_source(), namespace)  # noqa: S102
    differing, query_differing, compared = [], 0, 0
    for task_id in sorted(_frozen_task_ids()):
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        family = task.get("family")
        run = {}
        for budget in (8, 16, 32, 64):
            for method in ("ddmin", "greedy"):
                name = "%s__%s" % (method,
                                   method_exec._STRATEGY_METHODS[method])
                oracle = (checkers.SoftwareOracle(task, max_queries=budget)
                          if family == "software"
                          else checkers.GraphOracle(task, max_queries=budget))
                result = namespace[name](task, oracle, max_queries=budget)
                run[(budget, method)] = (
                    json.dumps(result["candidate"], sort_keys=True),
                    oracle.queries_used)
        for budget in (8, 16, 32, 64):
            compared += 1
            if run[(budget, "ddmin")][0] != run[(budget, "greedy")][0]:
                differing.append("%s@%d" % (task_id, budget))
            if run[(budget, "ddmin")][1] != run[(budget, "greedy")][1]:
                query_differing += 1
    assert query_differing >= 110, (
        "the two strategies cost the same on %d of %d (task, budget) pairs;"
        " the probe is probably wrapping the oracle report twice"
        % (compared - query_differing, compared))
    assert len(differing) >= 100, (
        "ddmin and greedy reached different candidates on only %d of %d"
        " (task, budget) pairs: %s" % (len(differing), compared, differing))


def _frozen_task_ids() -> list:
    from experiments.ad01 import worlds
    manifest = json.loads(
        (Path(worlds.FROZEN_DIR) / "manifest.json").read_text())
    return sorted(entry["task_id"] for entry in manifest["files"])


def _namespace() -> dict:
    """The child's wrapper namespace, built the way the driver builds it."""
    from experiments.representation import reducers
    namespace = {"reducers": reducers}
    exec(method_exec._child_wrapper_source(), namespace)  # noqa: S102
    return namespace


def test_the_two_primitives_are_reachable_through_the_adapter():
    """The menu's wider half is callable, not merely declared.

    `ddmin_reduce` and `greedy_reduce` take `(count, build, probe)`, which
    the child does not hold, so they were offered under a signature no
    callee had. They are now reached through the family adapter, and this
    calls them the way a member would, on a task the real checker grades
    rather than on a hand-built one.
    """
    from experiments.ad01 import worlds

    wrappers = _namespace()
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")
    for name in ("ddmin_reduce", "greedy_reduce"):
        result = wrappers[name](task, _Oracle(task), family="software",
                                max_queries=16)
        assert result["candidate"]["family"] == "software", name
        assert result["status"] in ("locally-irreducible",
                                    "budget-exhausted"), (name, result)
        assert result["candidate"]["ops"] != task["ops"], (
            "%s returned the whole task; the adapter removed nothing, which"
            " is what a probe wrapping the oracle report twice looks like"
            % name)


def test_a_binding_needing_an_unoffered_value_refuses():
    """The refusal path, exercised rather than assumed.

    A contract whose binding names a callable taking a different shape
    under the same name must be refused at build time, with the callable
    named. Without this, the refusal is a branch nothing reaches.
    """
    contract = json.loads(json.dumps(method_exec.child_contract()))
    contract["callables"]["reduce_software"]["binding"] = \
        "reducers.software_atoms"
    try:
        method_exec.verify_child_contract(contract)
    except method_exec.MethodExecutionError as exc:
        assert "refused" in str(exc) and "software_atoms" in str(exc), str(exc)
    else:
        raise AssertionError(
            "a binding whose callable takes a different shape was offered"
            " under the name reduce_software without a refusal")


def test_the_two_strategies_are_reachable_by_name_without_reduce():
    """A control column is drawable from names the menu offers.

    `reports/evidence/inv_r1_m3b/repertoires/control-sw.json` declares
    `seed-sw-ddmin` and `seed-sw-greedy` with different digests over
    byte-identical sources. The two names have to come from somewhere a
    study can name, so both composed entries must be in the menu and
    callable, and each must commit to its own strategy.
    """
    wrappers = _namespace()
    names = set(method_exec.child_contract()["callables"])
    for method, primitive in method_exec._STRATEGY_METHODS.items():
        composed = "%s__%s" % (method, primitive)
        assert composed in names, (
            "%s is not offered, so a control column cannot name it" % composed)
        assert callable(wrappers[composed]), composed
        wrapper = _wrapper_of(method_exec._child_wrapper_source(), composed)
        assert "method=%r" % method in wrapper, wrapper
        task = _software_task()
        result = wrappers[composed](task, _Oracle(task), max_queries=64)
        assert result["candidate"]["family"] == "software", composed


# --- the control ----------------------------------------------------------


def test_the_control_being_the_acquired_policy_is_refused():
    """The inverted control, on real E1 records.

    The acquired arm's policy body is
    `reduce_software(task, oracle, method="greedy", max_queries=...)`, so
    the acquired arm and the `greedy` control arm execute the same
    reduction while their `executed` ids differ. The ids disagree, so a
    check that trusted them would pass, and the strategies agree.

    The byte-identical candidates in these two files are the six graph
    tasks, not the software ones: both arms fell back to `incumbent` on
    every graph task, so the candidates are the same empty incumbent
    output, while the software tasks ran at different budgets (16 against
    4) and returned different bytes. An earlier version of this test
    asserted `same_candidate` named the software tasks, which it never
    did.
    """
    verdict = gates.control_distinct(
        ROOT / "evidence-ad01" / "c3-authored" / "use-w0-I.json",
        ROOT / "evidence-ad01" / "c3-trajectories-merged" / "use-w0-I.json")
    assert not verdict["distinct"], (
        "greedy against greedy was read as distinct:\n%s" % verdict)
    assert verdict["same_strategy"], (
        "the six software tasks ran one strategy under two names, which is"
        " the E1 finding, and no strategy leg was raised")
    assert {row["task_id"] for row in verdict["same_strategy"]} == {
        "ad01-w0-within-sw-00", "ad01-w0-within-sw-01",
        "ad01-w0-within-sw-02", "ad01-w0-transfer-sw-00",
        "ad01-w0-transfer-sw-01", "ad01-w0-transfer-sw-02"}
    assert verdict["refusal"], "a non-distinct control refused no reason"


def test_the_e1_arms_ran_one_strategy_under_two_names():
    """The E1 headline, on the real records, caught by the strategy leg.

    The two `executed` ids are `seed-sw-greedy` and
    `acquired-sw-58d90427`, so a check reading ids says the arms are two
    policies. The acquired arm's own `executed_source` is
    `reduce_software(task, oracle, method="greedy", max_queries=4)`. The
    two ran one strategy at two budgets, 14/16/15 queries against 4, and
    the smaller budget is what made their candidates differ. That is the
    23-against-23 tie read as a result.
    """
    root = ROOT / "evidence-ad01"

    def rows(path):
        return [row for row in json.loads(path.read_text())
                if row.get("domain") == "software"
                and "within" in row["task_id"]]

    verdict = gates.control_distinct(
        rows(root / "c3-authored" / "use-w0-I.json"),
        rows(root / "c3-trajectories-merged" / "use-w0-I.json"))
    assert not verdict["distinct"], (
        "greedy against greedy was read as distinct:\n%s" % verdict)
    assert not verdict["same_executed_policy"], (
        "the ids differ, which is why the id leg alone missed this")
    assert [row["strategy"] for row in verdict["same_strategy"]] == [
        ["greedy"], ["greedy"], ["greedy"]], verdict["same_strategy"]
    assert verdict["differing_budget"], (
        "the arms ran one strategy at two budgets and the budget is the"
        " only thing that separated them: %s" % verdict)


def test_a_hoaxed_digest_does_not_make_an_identical_control_distinct():
    """The M2 file, read by the gate that does not read digests.

    `control-sw.json` declares two different `source_digest` values over
    one byte-identical `method_source`, and neither is the sha256 of its
    own source. Distinctness is read from the executed id and the returned
    candidate, so the file cannot pass by declaring a difference.
    """
    members = json.loads(CONTROL_SW.read_text(encoding="utf-8"))["members"]
    sources = {member["method_source"] for member in members}
    digests = {member["source_digest"] for member in members}
    assert len(sources) == 1 and len(digests) == 2, (
        "the M2 defect changed shape: %d source(s), %d digest(s)"
        % (len(sources), len(digests)))

    control = [_task("t-0", executed=member["capability_id"],
                     source_digest=member["source_digest"])
               for member in members]
    verdict = gates.control_distinct(control, control)
    assert not verdict["distinct"]
    assert verdict["same_executed_policy"], verdict


def test_a_genuinely_distinct_control_passes():
    """The other direction, so the gate is not a refusal machine.

    Without this, a gate that always refused would pass every test here
    and would refuse every real run.
    """
    control = [_task("t-0", executed="seed-sw-ddmin",
                     output={"family": "software",
                             "ops": [{"key": "a", "op": "set"}]})]
    acquired = [_task("t-0", executed="acquired-sw-58d90427",
                      executed_source='return reducers.reduce_software'
                                      '(task, oracle, method="ddmin")')]
    verdict = gates.control_distinct(control, acquired)
    assert verdict["distinct"], verdict


def test_tasks_on_one_arm_only_are_not_a_comparison():
    verdict = gates.control_distinct(
        [_task("t-0", executed="seed-sw-ddmin"),
         _task("t-1", executed="seed-sw-ddmin")],
        [_task("t-0", executed="seed-sw-greedy")])
    assert not verdict["distinct"]
    assert verdict["unpaired_tasks"] == ["t-1"], verdict


# --- the experience -------------------------------------------------------


def test_an_all_preserved_experience_is_refused():
    """The E2 experience: 108 pairs, one verdict, no signal."""
    observations = [
        {"observation_id": "obs-%d" % index, "task_id": "t-%d" % index,
         "capability_id": "seed-sw-ddmin", "verdict": "preserved"}
        for index in range(108)]
    verdict = gates.experience_varies(observations)
    assert not verdict["varies"], verdict
    assert verdict["distinct_verdicts"] == 1, verdict
    assert verdict["refusal"], "a constant experience refused no reason"


def test_a_varied_experience_passes():
    observations = [
        {"task_id": "t-0", "capability_id": "seed-sw-ddmin",
         "verdict": "preserved", "method": "ddmin"},
        {"task_id": "t-1", "capability_id": "seed-sw-ddmin",
         "verdict": "not_preserved", "method": "ddmin"}]
    verdict = gates.experience_varies(observations)
    assert verdict["varies"], verdict
    assert verdict["methods_named"] == ["ddmin"], verdict


def test_the_rendered_experience_names_no_method_to_choose_from():
    """The E2 surface: the prompt renders two fields and both are there.

    Every observation in the scored E2 run graded `preserved`, and the
    prompt renders `task_id` and `verdict` only. This reads the real
    renderer, so a future prompt that does name the method is picked up
    and one that stops naming the verdicts is not mistaken for a pass.
    """
    from experiments.ad01 import learner

    rendered = learner.treatment_prompt(
        {"family": "software", "budget": {"max_queries": 8}},
        {"task_id": "t-0"},
        {"observations": [
            {"task_id": "t-0", "capability_id": "seed-sw-ddmin",
             "verdict": "preserved", "method": "ddmin"}]})
    observations_line = next(
        line for line in rendered.splitlines()
        if line.startswith("Prior observations:"))
    assert "seed-sw-ddmin" not in observations_line, (
        "the prompt now names the capability; update the check")
    assert "method" not in observations_line, observations_line
    assert "preserved" in observations_line, observations_line
