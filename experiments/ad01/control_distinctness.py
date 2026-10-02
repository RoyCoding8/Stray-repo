"""Three pre-dispatch gates. No dispatch, no database, no network.

The E1, E2 and M3 findings share one cause and this module is the answer
to it. A control that is not a distinct method and an experience that
carries one bit are both invisible to a run: the run reproduces the tie
it was going to reproduce anyway, and the reproduction costs live
dispatches. These three functions refuse that, and they are meant to be
called before anything is dispatched.

    control_distinct()    the two arms executed different policies
    experience_varies()   the treatment saw more than one outcome
    menu_answers_nothing() the child contract still has no default answer

Each reads *executed* evidence: the policy id a record says it ran and
the candidate it returned. None of them reads a declared digest, and
that is the point. `reports/evidence/inv_r1_m3b/repertoires/control-sw.json`
declares `seed-sw-ddmin` and `seed-sw-greedy` with two different
`source_digest` values over one byte-identical `method_source`, and
neither digest is the sha256 of its own source. A distinctness check
built on a digest would have passed that file and caught nothing.

`control_distinct` is a necessary gate, not a sufficient one. Distinct
policy ids are not distinct methods, which is what the E1 records show,
and a gate that stops at the id would have passed them. The frozen world
can separate `ddmin` from `greedy` on 108 of 216 (task, budget) pairs, so
a control column drawn from the two reducers is drawable; whether a given
run's arms landed on two different strategies is what this gate reads.

**A tie on the candidate is not one finding.** Two arms that returned the
same bytes either walked the same way or arrived from different
directions, and those are different defects. The first is the C15 shape:
one program under two names, the thing `same_source` and `same_walk`
exist to catch. The second is a property of the problem. These reducers
are deletion-only over a legal-subobject order with a preserved minimum,
and on this freeze the minimum is unique on 18 of 18 tasks under 40
random deletion orders, so two correct and different methods are expected
to meet on it. Refusing that would make the gate unsatisfiable on any
panel with a unique solution, which is a stricter gate than a reviewer
asked for; it is a gate that cannot pass.

So the walk is recorded by the run, per arm per task, in
`method_exec.serve` on the host side of the oracle channel where the
child cannot rewrite it, and the gate reads it:

    same_walk       both arms asked the same questions, in the same order,
                    and were graded the same way. Refuses.
    converged       byte-identical candidates, different walks. Reported,
                    and not a refusal. Two methods, one answer.
    unmeasured_walk a tie whose walks this run did not observe. Refuses,
                    because a tie the walk cannot classify is exactly the
                    pair the walk was added to classify.

`same_candidate` keeps every tie, so a reader can count the ties and the
convergences separately. The gate refuses on the legs that mean the arms
are the same, which is what it was written to do, and the legs now
include the one that can actually see the difference.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The keys a record may name its executed policy under, in the order they
# are read. `executed` is the one the campaign writes; the others are what
# a reconstructed record carries, and a record that has none of them is
# refused rather than credited with a policy it did not name.
_EXECUTED_KEYS = ("executed", "executed_source", "capability_id", "selected")

# The strategies a reducer can be built around, as a whole word. Matched
# loose on purpose: one record carries the strategy in a quoted literal
# (`method="greedy"`), another carries it as a bare word in a field that
# is itself named `executed_source`. A regex that required the quotes
# would resolve the first and not the second, report them as different
# strategies, and pass the exact column C15 is about.
_STRATEGY = re.compile(r"\b(ddmin|greedy)\b")

# The two values a child wrapper may not answer for the model, and why
# they are not the same question. `method` is the strategy, so a default
# for it is the answer the menu was built to withhold, and it refuses.
# `priority` is the order inside one strategy, and the callee supplies
# the authored priority when a member names none, so a default for it is
# reported rather than refused. The names are spelled here rather than
# matched out of the prose, so renaming a parameter moves the gate with
# the binding instead of silently turning it into a regex over nothing.
_STRATEGY_CHOICE = "method"
_ORDERING_CHOICE = "priority"


class GateRefused(Exception):
    pass


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load(path) -> list:
    """A list of records, from a path or from records already in hand.

    A path that does not exist is a refusal, not an empty file. An empty
    list is a refusal too, everywhere below, because a comparison over
    no records is not a comparison.
    """
    if isinstance(path, (str, Path)):
        try:
            path = Path(path)
        except (TypeError, ValueError) as exc:
            raise GateRefused("refused: unreadable-record-path") from exc
        if not path.exists():
            raise GateRefused("refused: no record file at %s" % path)
        try:
            path = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GateRefused(
                "refused: %s is not readable json" % path) from exc
    if not isinstance(path, list) or not path:
        raise GateRefused("refused: no records to compare")
    for row in path:
        if not isinstance(row, dict):
            raise GateRefused("refused: a record is not an object")
    return path


def executed_policy_id(record: dict) -> str:
    """What a record says it ran, read from the first key that names it.

    The id is taken as written. A record whose only naming of a strategy
    is a `method=` inside a source body is reported as naming none: the
    executed id is the campaign's own label, and a body read here would be
    a second, weaker parse of the same claim.

    A record that fell back names no policy at all. `run_use` writes
    `executed: "incumbent"` and `executed_source: "incumbent"` on a
    fallback, and the body of the *repertoire member* may still sit in
    another field, so a fallback can read as a member that ran. It did:
    the third control-arm run spent its whole ceiling on the acquired
    arm, all eighteen control records fell back, and this function
    returned `incumbent` while `_strategy_of` found `ddmin` in the
    retained body — which made `control_distinct` report
    `distinct: True` over two arms that ran nothing of theirs. A fallback
    is not an executed policy, so it is reported as naming none.
    """
    if str(record.get("fallback_reason") or "").strip():
        return ""
    for key in _EXECUTED_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _strategy_of(record: dict) -> str:
    """The strategy a record shows was run, read from every place.

    A record names its strategy in more than one field and they do not
    agree: in the E1 acquired column `executed` is the capability id
    `acquired-sw-58d90427` and `executed_source` carries the whole policy
    body, whose `method="greedy"` is the only statement of strategy
    anywhere in the record. Reading the first field that has a name and
    stopping would report the id, find no strategy token in it, and call
    the two arms distinct. The id cannot be left out for the same reason:
    the control column says `seed-sw-greedy` and nowhere else says
    anything. So every field is read, and a field whose id names a
    strategy is joined with a field whose body does.

    A record that fell back is read from nothing. `run_use` copies the
    selected member's body onto the record even when execution failed, so
    a fallback whose retained body names `ddmin` would report that
    strategy for a member that never ran. The refusal this produces is the
    correct one: an arm that fell back did not execute a policy, and
    comparing it as though it had is how the third control-arm run
    reported `distinct: True` over eighteen incumbent fallbacks on one
    side and a real member on the other.
    """
    if str(record.get("fallback_reason") or "").strip():
        return ""
    found = set()
    for key in ("method", "executed_source", "method_source", "source",
                "executed", "executed_policy", "capability_id", "selected"):
        value = record.get(key)
        if not isinstance(value, str) or not value:
            continue
        match = _STRATEGY.search(value)
        if match:
            found.add(match.group(1))
    return "/".join(sorted(found))


def _by_task(records: list, *, where: str) -> dict:
    by_task = {}
    for row in records:
        task_id = row.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise GateRefused("refused: a %s record names no task" % where)
        by_task.setdefault(task_id, []).append(row)
    return by_task


def _candidate_of(record: dict) -> dict:
    for key in ("output", "candidate", "data"):
        value = record.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _has_candidate(record: dict) -> bool:
    return any(isinstance(record.get(key), dict)
               for key in ("output", "candidate", "data"))


# The keys a record may carry its walk under, in the order they are read.
# `query_trace` is what the dispatch path writes; the others are what a
# reconstructed record carries, and a record with none of them is reported
# as unmeasured rather than as an arm that asked nothing.
_TRACE_KEYS = ("query_trace", "queries_trace", "trace")


def _trace_of(record: dict):
    """The walk a record says its member took, or `None` if it says none.

    A missing trace and an empty one are different claims and are kept
    apart. `None` is an arm whose walk this run did not observe: a
    durable-receipt replay, a host seed short-circuit, a fallback, or a
    record predating the field. `[]` is an arm that ran and asked nothing.
    Reading both as "the same, because both empty" is how a gate would
    wave through two arms it never watched.

    The `None` in the return is the sentinel, not the empty list, so
    `if _trace_of(row)` cannot collapse the two.
    """
    if str(record.get("fallback_reason") or "").strip():
        return None
    for key in _TRACE_KEYS:
        if key in record:
            value = record.get(key)
            if value is None:
                return None
            if isinstance(value, list):
                return value
    return None


def _walk(rows: list) -> list:
    """Every arm's walk on a task, when all of them have one.

    Returns `None` if any record on the task has no trace, because a
    partial walk is not a shorter walk. Two records on one task that
    disagree are two walks, and that is a disagreement the caller's own
    legs report rather than something this hides by picking one.
    """
    traces = [_trace_of(row) for row in rows]
    if any(trace is None for trace in traces):
        return None
    if any(trace != traces[0] for trace in traces[1:]):
        return None
    return traces[0]


def _trace_digest(trace: list) -> str:
    return _digest([[row.get("candidate_digest"), row.get("verdict"),
                     row.get("reason")] for row in trace])


def control_distinct(control: list, acquired: list) -> dict:
    """The two arms ran different policies, on the same tasks, measured.

    Distinctness is read per task from the executed policy id, the strategy
    that policy actually ran, the source those two names, and the returned
    candidate. Never from a declared digest. Six separate failures are
    reported separately, because a run that tied because the two arms were
    the same strategy is a different defect from one that tied because they
    were the same bytes:

    `same-strategy`  both arms resolved to one strategy, by any of the
                     three places a record can name it. This is the E1
                     finding as recorded. The acquired policy's body is
                     `reduce_software(task, oracle, method="greedy", ...)`
                     and the control column executed `seed-sw-greedy`, so
                     the two ids differ and the two strategies are one.
                     A smaller budget is what made the candidates differ;
                     it is reported under `budget` and is not distinctness.
    `same-executed-policy`  a task where both arms named one policy id.
    `same-source`     a task where both arms ran one byte-identical
                      `executed_source` under different ids. The strategy
                      leg cannot see it: a body naming no strategy
                      resolves to the empty set on both arms and an empty
                      set is not refused, so two members over one source
                      read as distinct. That is the C15 shape.
    `same-candidate`        a task where the ids and the strategies differ
                            but the candidates are byte-identical. See
                            `converged` below for when that is a tie and
                            when it is a property of the problem.
    `same-walk`         a task where both arms asked the same questions, in
                        the same order, and were graded the same way. This
                        is the leg that distinguishes a C15 shape from a
                        real convergence, and it is the one the
                        `same-candidate` leg could not be.
    `converged`         a task whose candidates are byte-identical and whose
                        walks are not. Two different methods that arrived
                        at one answer took one answer's worth of history to
                        get there, and the candidate leg alone cannot say
                        so.
    `unmeasured-walk`   a task where at least one arm's walk this run did
                        not observe. Reported, and refused: an unmeasured
                        pair is not a distinct pair.
    `unnamed-executed-policy`  a task where an arm named no policy at all,
                            which is every fallback.
    `unpaired-tasks`        a task only one arm has. The comparison is
                            paired, so a task the other arm never ran
                            cannot be a tie on that task.
    `one-arm-returned-no-candidate`  a task where exactly one arm carries a
                            candidate. `_candidate_of` answers `{}` for a
                            record with no output, so an arm that returned
                            nothing digested as the empty candidate and the
                            other arm's bytes read as different from it.
                            Absence is not a difference.
    """
    control, acquired = _load(control), _load(acquired)
    left = _by_task(control, where="control")
    right = _by_task(acquired, where="acquired")
    shared = sorted(set(left) & set(right))
    unpaired = sorted(set(left) ^ set(right))
    same_policy, same_candidate, same_strategy, unnamed = [], [], [], []
    same_source, uncandidate, budget = [], [], []
    same_walk, converged, unmeasured = [], [], []
    for task_id in shared:
        left_ids = {executed_policy_id(row) for row in left[task_id]}
        right_ids = {executed_policy_id(row) for row in right[task_id]}
        if not (left_ids | right_ids) - {""}:
            unnamed.append({"task_id": task_id,
                            "executed": {"control": sorted(left_ids),
                                         "acquired": sorted(right_ids)},
                            "fallback": {
                                "control": [row.get("fallback_reason", "")
                                            for row in left[task_id]
                                            if row.get("fallback_reason")],
                                "acquired": [row.get("fallback_reason", "")
                                            for row in right[task_id]
                                            if row.get("fallback_reason")]}})
            continue
        # One arm naming nothing is a refusal, not a pass. The old
        # condition only refused when *both* arms were unnamed, so a task
        # where the control had fallen back to `incumbent` and the
        # acquired arm had run a real member compared a set containing
        # `""` against a set containing a capability id, found them
        # different, and called the task distinct. An arm that fell back
        # did not execute a policy, so there is nothing on that side to
        # compare and the task is unmeasured, not distinct.
        #
        # The task is not skipped. A fallback still returned a candidate
        # and a verdict, and the later checks are what say whether the
        # other failures are present too, so the record keeps the whole
        # picture rather than the first thing that was wrong.
        if not left_ids - {""} or not right_ids - {""}:
            unnamed.append({"task_id": task_id,
                            "executed": {"control": sorted(left_ids),
                                         "acquired": sorted(right_ids)},
                            "fallback": {
                                "control": [row.get("fallback_reason", "")
                                            for row in left[task_id]
                                            if row.get("fallback_reason")],
                                "acquired": [row.get("fallback_reason", "")
                                            for row in right[task_id]
                                            if row.get("fallback_reason")]}})
        if left_ids == right_ids:
            same_policy.append({"task_id": task_id,
                                "executed": sorted(left_ids)})
        # One source under two ids is the C15 shape the module docstring
        # names, and the strategy leg cannot see it: a body that names no
        # strategy resolves to the empty set on both arms, `left_methods`
        # is empty, and `left_methods == right_methods` is only refused
        # when it is non-empty. Two members over one byte-identical source
        # therefore reported distinct, which is the exact column C15 is
        # about. The ids still differ and the candidates may too, so the
        # leg is reported separately and the refusal names it.
        left_sources = {row["executed_source"] for row in left[task_id]
                        if isinstance(row.get("executed_source"), str)
                        and row["executed_source"]}
        right_sources = {row["executed_source"] for row in right[task_id]
                         if isinstance(row.get("executed_source"), str)
                         and row["executed_source"]}
        if left_sources and left_sources == right_sources:
            same_source.append({
                "task_id": task_id,
                "source_digest": [_digest(sorted(left_sources))],
                "executed": {"control": sorted(left_ids),
                             "acquired": sorted(right_ids)}})
        # An arm that returned no candidate cannot be compared with one
        # that did. `_candidate_of` answers `{}` for a record carrying no
        # output at all, so the digest of "nothing" is the digest of an
        # empty candidate and one arm's absence was read as a difference
        # from the other's bytes. That is how a control that returned a
        # candidate and an acquired arm that returned nothing at all came
        # to report `distinct: True`. Absence is now its own leg.
        left_returned = any(_has_candidate(row) for row in left[task_id])
        right_returned = any(_has_candidate(row) for row in right[task_id])
        if left_returned != right_returned:
            uncandidate.append({
                "task_id": task_id,
                "returned": {"control": left_returned,
                             "acquired": right_returned},
                "executed": {"control": sorted(left_ids),
                             "acquired": sorted(right_ids)}})
        left_methods = {_strategy_of(row) for row in left[task_id]} - {""}
        right_methods = {_strategy_of(row) for row in right[task_id]} - {""}
        if left_methods and left_methods == right_methods:
            same_strategy.append({
                "task_id": task_id,
                "strategy": sorted(left_methods),
                "executed": {"control": sorted(left_ids),
                             "acquired": sorted(right_ids)}})
        left_bytes = {_digest(_candidate_of(row)) for row in left[task_id]}
        right_bytes = {_digest(_candidate_of(row)) for row in right[task_id]}
        tied = left_bytes == right_bytes
        if tied:
            same_candidate.append({
                "task_id": task_id,
                "executed": {"control": sorted(left_ids),
                             "acquired": sorted(right_ids)},
                "candidate_digest": sorted(left_bytes)})
        # The walk leg, and the classification it forces on a tie.
        #
        # A tie on the candidate is ambiguous on its own. Two ids running
        # byte-identical walks are the C15 shape: the control arm is not
        # distinct from the acquired arm because it is the same program
        # under another name, and no reader of the candidates can tell
        # that from a pair of different methods that both found the one
        # preserved minimum. The walk is what separates them, and it is
        # recorded by the run rather than reconstructed here.
        left_trace = _walk(left[task_id])
        right_trace = _walk(right[task_id])
        if left_trace is None or right_trace is None:
            # Reported for every task, because a reader should know how
            # much of the comparison rests on walks. It refuses only where
            # the candidates tied, which is the one place the walk is load
            # bearing: a tie with no walk is precisely the pair the walk
            # exists to classify, and refusing it is honest. A task where
            # the ids, the sources, the strategies and the candidates all
            # already disagree is established distinct without the walk,
            # and holding it hostage to a field a record predating this
            # version does not carry would make the gate refuse pairs it
            # can already prove.
            unmeasured.append({
                "task_id": task_id,
                "candidates_tied": tied,
                "walk_observed": {"control": left_trace is not None,
                                  "acquired": right_trace is not None},
                "executed": {"control": sorted(left_ids),
                             "acquired": sorted(right_ids)}})
        elif left_trace == right_trace:
            same_walk.append({
                "task_id": task_id,
                "walk_digest": [_trace_digest(left_trace)],
                "queries": len(left_trace),
                "executed": {"control": sorted(left_ids),
                             "acquired": sorted(right_ids)}})
        elif tied:
            # Different walks, one answer. This is the finding the
            # candidate leg used to report as a failure and the walk leg
            # reports as a property of the problem: the two methods
            # reduced the task by different routes to the same preserved
            # minimum, and a panel whose minimum is unique will produce
            # this on any panel that has one. Refusing it would make the
            # gate unsatisfiable on every well-formed task in the freeze.
            converged.append({
                "task_id": task_id,
                "candidate_digest": sorted(left_bytes),
                "walk_digest": {"control": _trace_digest(left_trace),
                                "acquired": _trace_digest(right_trace)},
                "queries": {"control": len(left_trace),
                            "acquired": len(right_trace)},
                "executed": {"control": sorted(left_ids),
                             "acquired": sorted(right_ids)}})
        spent = {"control": _queries(left[task_id]),
                 "acquired": _queries(right[task_id])}
        if spent["control"] != spent["acquired"]:
            budget.append({"task_id": task_id, "queries": spent})
    if not shared:
        raise GateRefused(
            "refused: the two arms share no task, so nothing was compared")
    unmeasured_ties = [row for row in unmeasured if row.get("candidates_tied")]
    verdict = {
        "version": "ad01-control-distinctness/2",
        "paired_tasks": shared,
        "unpaired_tasks": unpaired,
        "same_strategy": same_strategy,
        "same_executed_policy": same_policy,
        "same_source": same_source,
        "same_candidate": same_candidate,
        "same_walk": same_walk,
        "converged": converged,
        "unmeasured_walk": unmeasured,
        "unnamed_executed_policy": unnamed,
        "one_arm_returned_no_candidate": uncandidate,
        "differing_budget": budget,
        "distinct": not (same_strategy or same_policy or same_walk
                         or same_source or unnamed or unpaired
                         or uncandidate or unmeasured_ties),
    }
    if not verdict["distinct"]:
        verdict["refusal"] = _refusal_text(verdict)
    return verdict


def _queries(rows: list) -> int:
    spent = {int(row.get("costs", {}).get("witness_queries") or 0)
             for row in rows if isinstance(row.get("costs"), dict)}
    return spent.pop() if len(spent) == 1 else -1


def _refusal_text(verdict: dict) -> str:
    reasons = []
    if verdict["same_strategy"]:
        reasons.append("%d task(s) ran one strategy on both arms"
                       % len(verdict["same_strategy"]))
    if verdict["same_executed_policy"]:
        reasons.append("%d task(s) ran one executed policy id on both arms"
                       % len(verdict["same_executed_policy"]))
    if verdict["same_source"]:
        reasons.append("%d task(s) ran one byte-identical source on both arms"
                       % len(verdict["same_source"]))
    if verdict.get("same_walk"):
        reasons.append("%d task(s) took the same walk on both arms"
                       % len(verdict["same_walk"]))
    if verdict.get("unmeasured_walk") and [
            row for row in verdict["unmeasured_walk"]
            if row.get("candidates_tied")]:
        reasons.append("%d tied task(s) have a walk this run did not"
                       " observe" % len([row for row in
                                         verdict["unmeasured_walk"]
                                         if row.get("candidates_tied")]))
    # A tie on the candidate is reported, and it is only a reason when the
    # walk leg is silent about it. Every tie lands in `same_candidate`;
    # the ones whose walks differ are in `converged` and are not a defect
    # in the arm, they are a property of the problem. Naming the split
    # rather than the raw count is the difference between a reader being
    # told the arms are the same and a reader being told which ones are.
    if verdict["same_candidate"]:
        tied = len(verdict["same_candidate"])
        diverged = len(verdict.get("converged") or [])
        if diverged:
            reasons.append("%d task(s) returned a byte-identical candidate on"
                           " both arms, of which %d took different walks and"
                           " are reported as converged"
                           % (tied, diverged))
        else:
            reasons.append("%d task(s) returned a byte-identical candidate on"
                           " both arms" % tied)
    if verdict["unnamed_executed_policy"]:
        reasons.append("%d task(s) named no executed policy on at least"
                       " one arm" % len(verdict["unnamed_executed_policy"]))
    if verdict.get("one_arm_returned_no_candidate"):
        reasons.append("%d task(s) returned a candidate on one arm only"
                       % len(verdict["one_arm_returned_no_candidate"]))
    if verdict["unpaired_tasks"]:
        reasons.append("%d task(s) are on one arm only"
                       % len(verdict["unpaired_tasks"]))
    return ("refused: control is not distinct from the acquired arm: %s"
            % "; ".join(reasons))


def _verdicts(observations: list) -> list:
    return [str(row.get("verdict"))
            for row in observations
            if isinstance(row, dict) and row.get("verdict") is not None]


def _reasons(observations: list) -> list:
    """The bounded reason code each observation earned, where it earned one.

    A record with no `reason` contributes nothing rather than a placeholder,
    so an experience built from a surface that never carried a reason is
    reported as having no reasons and not as having one reason.
    """
    return [str(row.get("reason"))
            for row in observations
            if isinstance(row, dict) and str(row.get("reason") or "") not in
            ("", "none", "None")]


def _outcomes(observations: list) -> list:
    """What the checker graded each observation, as one comparable token.

    The verdict and the reason are one measured quantity, not two, and they
    are reported here joined so a consumer has a single column to count.
    An observation with no reason is its verdict, which is what an experience
    from a surface that never recorded one counted against before.
    """
    rows = []
    for row in observations:
        if not isinstance(row, dict) or row.get("verdict") is None:
            continue
        reason = str(row.get("reason") or "")
        rows.append("%s/%s" % (row.get("verdict"), reason)
                    if reason not in ("", "none", "None")
                    else str(row.get("verdict")))
    return rows


def experience_varies(observations: list, *, minimum: int = 2,
                      arm_name: str = "treatment") -> dict:
    """The arm's experience carried more than one measured outcome.

    The gate counts distinct *outcomes*, and an outcome is the verdict joined
    to the bounded reason the checker's own grading earned. It used to count
    distinct verdicts alone, and that count is a constant on every well-formed
    task in this repository, which `experiments/ad01/experience_axis.py`
    measures rather than argues.

    **Why the verdict alone cannot vary.** The oracle a reducer probes with
    and the grader a record is marked by are the same function:
    `SoftwareOracle.check` returns `check_software(self.task, candidate)` and
    `trajectory._check` returns `checkers.check_software(task, candidate)`.
    Both authored reducers therefore assign their `keep` set only from a trial
    the oracle graded `preserved`, and return the task unchanged on the one
    branch where nothing was accepted. The candidate that comes back is the
    task or an accepted trial, and both grade `preserved`. Measured: 540
    triples over the committed `ad01` freeze and 96000 over adversarially
    generated well-formed tasks, every one `preserved`. The verdicts outside
    `preserved` are reachable only through a task that is not well formed, and
    a panel of those would be grading its own malformity.

    **What the reason adds, and why it is not a weakening.** `ok-incumbent` is
    the arm returning the task unchanged and `ok-preserved` is the arm
    returning a strict reduction. The verdict collapses those into one bit and
    the reason does not, so an arm whose experience is entirely one bit was
    never carrying one: it was carrying one bit because the instrument gave it
    one bit to carry. The axis that moves the reason is how many atoms a single
    deletion can remove, zero being the point where the reducer is stuck at
    any budget, and `ad01-exp-axis` is a panel built to span it.

    **The gate is not merely open.** A constant experience still refuses: the
    committed `ad01` panel at `max_queries: 1` grades all 54 tasks
    `ok-incumbent` and is refused here, and so is an experience whose verdicts
    are all `preserved`. What the change removes is a refusal that no data
    could ever satisfy, and it removes it by reading a field the checker
    already writes. `tests/test_ad01_experience_axis.py` is the battery, and it
    asserts both directions: the panel that must open and the constants that
    must still refuse.

    A pair is also reported for `method`, because a record that never names the
    method that earned its outcome cannot say what the policy learned from.
    That surfaces as `methods_named` and is not by itself a refusal: only the
    outcome count decides variation.
    """
    if not isinstance(observations, list) or not observations:
        raise GateRefused("refused: the %s arm has no experience"
                          % arm_name)
    verdicts = _verdicts(observations)
    if not verdicts:
        raise GateRefused("refused: the %s arm has no measured outcome"
                          % arm_name)
    methods = {row.get("method") for row in observations
               if isinstance(row, dict)}
    named = sorted(str(value) for value in methods
                   if value not in (None, "", "none"))
    reasons = _reasons(observations)
    outcomes = _outcomes(observations)
    distinct = sorted(set(verdicts))
    distinct_outcomes = sorted(set(outcomes))
    distinct_reasons = sorted(set(reasons))
    verdict = {
        "version": "ad01-experience-variation/2",
        "arm": arm_name,
        "observations": len(observations),
        "verdicts": distinct,
        "distinct_verdicts": len(distinct),
        "reasons": distinct_reasons,
        "distinct_reasons": len(distinct_reasons),
        "outcomes": distinct_outcomes,
        "distinct_outcomes": len(distinct_outcomes),
        "methods_named": named,
        "varies": len(distinct_outcomes) >= minimum,
        "counted_on": "verdict-and-reason",
    }
    if not verdict["varies"]:
        verdict["refusal"] = (
            "refused: the %s arm's experience is a constant: %d observation"
            "s, %d distinct outcome(s) %s, minimum %d"
            % (arm_name, len(observations), len(distinct_outcomes),
               distinct_outcomes, minimum))
    return verdict


def _binding_answers(choice: str, signature, profile: dict) -> bool:
    """Whether this wrapper answers `choice` for the model.

    Read off the wrapper's own signature and the callee's binding profile.
    Never off the rendered prose, which is a description of the binding
    and would make the gate a second opinion on a string that a
    renderer can change without changing a call.

    A `None` default is the one ambiguous shape and the callee settles
    it. Where the callee requires the parameter, `None` is a value the
    callee runs on and the model never chose, so it answers. Where the
    callee does not declare the parameter, the `None` is a name check
    inside the adapter, there is no value behind it, and nothing reaches
    the callee, so it does not answer. That is the difference between
    `ddmin_reduce` guarding `method` and a wrapper handing the model
    `ddmin`.

    The wrapper's `inspect.Signature` is the source rather than its
    `__defaults__`/`__kwdefaults__`, for two reasons. The signature
    carries the parameter's kind, so a default bound before the `*` is
    read the same as one after it, and a wrapper that does not build
    raises here instead of reading as a clean empty dict. It is also the
    object the contract's prose is rendered from, so the gate and the
    menu are reading one binding rather than two descriptions of it.
    """
    parameter = signature.parameters.get(choice)
    if parameter is None or parameter.default is parameter.empty:
        return False
    if parameter.default is not None:
        return True
    return choice in profile["required"]


def _bound_binding(contract: dict) -> tuple:
    """The wrappers the child binds, and the profile of each callee."""
    from . import method_exec

    profiles = {}
    for name, spec in contract["callables"].items():
        binding = spec.get("binding")
        if binding:
            profiles[name] = method_exec._binding_profile(
                method_exec._resolve_binding(binding))
    return method_exec._wrapper_signatures(contract), profiles


def menu_answers_nothing(contract: dict | None = None) -> dict:
    """The child menu still has no default answer, and its wrappers build.

    Two checks in one, because they are the same question asked twice. A
    binding whose generated wrapper carries a strategy default is a menu
    that answers itself. A binding that cannot be built at all is a menu
    that lies about being a menu. Both refuse.

    The verdict reads the binding, not the contract's prose. The prose is
    rendered from the wrapper, so a gate that regexed it would be grading
    a description of the gate's own input, and one honest rendering away
    from correct it would refuse every study.
    """
    from . import method_exec

    contract = method_exec.child_contract() if contract is None else contract
    built = method_exec.verify_child_contract(contract)
    wrappers, profiles = _bound_binding(contract)
    defaulting, orderable = [], []
    for name in sorted(profiles):
        signature = wrappers.get(name)
        if signature is None:
            raise GateRefused(
                "refused: %s has a binding but the child binds no wrapper"
                " for it" % name)
        if _binding_answers(_STRATEGY_CHOICE, signature, profiles[name]):
            defaulting.append(name)
        elif _binding_answers(_ORDERING_CHOICE, signature, profiles[name]):
            orderable.append(name)
    verdict = {
        "version": "ad01-menu-openness/1",
        "bound": built["bound"],
        "host_only": built["host_only"],
        "defaulting_strategy": defaulting,
        "defaulting_priority": orderable,
        "wrappers_build": True,
        "open": not defaulting,
        "read_from": "wrapper-signature-and-callee-binding",
        "note": ("a default for `priority` is the order inside one"
                 " strategy, not the strategy, and the member may pass"
                 " its own; a default for `method` is the answer, unless"
                 " the callee declares no such parameter and the default"
                 " is a name check that never reaches it"),
    }
    if defaulting:
        verdict["refusal"] = (
            "refused: %s supplies a value for the choice the menu asks"
            " the model to make" % ", ".join(defaulting))
    return verdict


def probe() -> dict:
    """What the gates say about the artifacts on disk. Dispatch nothing."""
    return {
        "version": "ad01-control-distinctness/2",
        "menu": menu_answers_nothing(),
        "e1_authored_versus_acquired": _gate("E1", control_distinct,
                                             ROOT / "evidence-ad01"
                                             / "c3-authored" / "use-w0-I.json",
                                             ROOT / "evidence-ad01"
                                             / "c3-trajectories-merged"
                                             / "use-w0-I.json"),
    }


def _gate(label: str, gate, control, acquired) -> dict:
    try:
        verdict = gate(control, acquired)
    except GateRefused as refusal:
        return {"label": label, "distinct": False, "refusal": str(refusal)}
    return {"label": label, "distinct": verdict["distinct"],
            "verdict": verdict}


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2, sort_keys=True))
