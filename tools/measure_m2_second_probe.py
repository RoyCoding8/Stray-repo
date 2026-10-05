"""Measure the second-probe amendment on the real E0 frontier.

The amendment under test adds one probe on the dev-4 rule at an input other
than 3 and runs it before `_control_triple`. The claim under test is that the
earned verdict then reads `not_preserved` rather than `unknown`, so the
preserved arm moves off `frontier[0]` and `observation_dependent` reads True.

Every number this prints is measured, not asserted, and each count is derived
in the same command that produced the underlying set. Nothing here touches a
database: the live store is a file, and the frontier investigation's only
database contact on this path is the mission row, which the choice itself does
not read. The probe is a `RuleSession` oracle call, not a model call, so
`E0_CALL_CEILING` is untouched -- asserted below against the same constant the
study freezes.

    python tools/measure_m2_second_probe.py

Sweeps every second input other than the first probe's, and reports the earned
verdict, the three choices, and the two decision fields per input.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in ("", "src", "scripts"):
    sys.path.insert(0, str(ROOT / extra) if extra else str(ROOT))

from experiments.ad01 import boolean_rule as _rules  # noqa: E402
from experiments.ad01 import frontier as _frontier  # noqa: E402
from experiments.ad01 import improve_channel as _channel  # noqa: E402
from experiments.ad01 import live_construct as _live  # noqa: E402
from experiments.ad01 import rule_learner as _reducer  # noqa: E402
import invl02_live as driver  # noqa: E402

FIRST_OPPORTUNITY = "opp-rule-dev-4"
FIRST_X = 3
N_INPUTS = _rules.N_STATES


def _mission() -> dict:
    return {"objective": _live.LIVE_MISSION_OBJECTIVE,
            "environments": [{"instrument": "boolean-rule-v1",
                              "split": "dev", "seed": 4}]}


def build_store(path: Path, opportunities: list):
    """The store `_run_frontier_investigation` builds, minus the mission row.

    `ensure_live_store` is called with no `dsn` here, which is the fixture
    boundary that file already names: without both a dsn and an investigation
    id the store records no durable owner, and the choice path reads none.
    """
    store = _live.ensure_live_store(
        str(path), _mission(), dict(_live.LIVE_AUTHORITY))
    _live.propose_live_work(store, opportunities)
    active = store.active_package
    if active is None:
        active = _live.bind_live_control(store, "low")
    assert active.get("origin") == "authored-control"
    return store, active


def choose_next_work(store, package: dict, experience: list,
                     *, arm: str | None = None) -> dict:
    """`live_construct.choose_next_work` with the executor's boundary crossed.

    This is the execution boundary `improve_channel._run_source` gates, and
    only that boundary. It dispatches the STEP bytes to a subprocess and
    demands a `{dsn, allocation_id}` it settles against, both of which need a
    PostgreSQL this harness deliberately does not stand up. Everything the
    choice actually depends on still runs: the shipped `op_source` bytes, the
    shipped `store.step_view(...)` view, and after the bytes run, the shipped
    `_frontier.validate_view` and `_frontier.validate_operate_action` on that
    exact pair. The verdict is then read with the shipped `_control_triple`
    arithmetic.

    So the compared arms run the same bytes production runs, and every
    validation production applies is applied here too. What is not exercised
    is the out-of-process dispatch and the durable receipt it writes, which
    is the claim `principle-test-behavior-not-implementation` separates: the
    receipt is provenance for the choice, not the choice.
    """
    from experiments.ad01 import method_exec as _method_exec

    view = store.step_view(_frontier.OPERATE, package)
    view["experience"] = list(experience)
    _frontier.validate_view(view)
    namespace: dict = {}
    exec(compile(package["op_source"], "<op_source>", "exec"), namespace)
    result = namespace["STEP"](view, {})
    action = _channel._unwrap(result["action"])
    action = _frontier.validate_operate_action(action)
    return {"action": action, "state": result["state"],
            "executed_digest": _method_exec._source_digest(
                package["op_source"]),
            "choice": action.get("inputs", {}).get("opportunity_id"),
            "arm": arm}


def control_triple(store, active: dict, label: str) -> dict:
    """The shipped `_control_triple` with its choice call pointed at ours."""
    recorded = store.observations
    disconnected = choose_next_work(store, active, [], arm=label)
    if not recorded:
        return {"preserved": disconnected, "refuted": disconnected,
                "disconnected": disconnected, "refuted_rewritten": False,
                "refuted_from": None}
    refuted = [dict(o) for o in recorded]
    refuted[-1] = {**refuted[-1], "verdict": _channel.NOT_PRESERVED}
    return {"preserved": choose_next_work(store, active, recorded, arm=label),
            "refuted": choose_next_work(store, active, refuted, arm=label),
            "disconnected": disconnected,
            "refuted_rewritten": True,
            "refuted_from": refuted[-1].get("observation_id")}


def run_case(tmp: Path, second_x: int | None) -> dict:
    """One run: the shipped probe, then the second when asked, then the triple.

    The second probe's opportunity is read from `_live_opportunities`, which
    now carries it, so this measures the shipped source rather than a local
    reconstruction of the amendment. The baseline case passes no second input
    and proposes no second opportunity, so it still reads the one-probe
    answer the amendment replaced.
    """
    freeze = driver.freeze_e0(tmp / ("freeze-%s" % second_x))
    store, active = build_store(
        tmp / ("frontier-%s.json" % second_x),
        driver._live_opportunities(freeze))
    task = _rules.make_task("dev", 4)

    def probe(opportunity_id: str, x: int) -> dict:
        action = {"kind": "probe",
                  "inputs": {"opportunity_id": opportunity_id, "x": x},
                  "requested_resources": {"queries": 1, "steps": 1}}
        return _live.execute_chosen_work(store, action, task)

    first = probe(FIRST_OPPORTUNITY, FIRST_X)
    second = None
    if second_x is not None:
        # The swept input needs its own opportunity, because a probe's
        # declared input is part of its identity and
        # `_find_admitted_probe_effect` refuses a probe whose input differs
        # from the admitted effect. The shipped second probe declares
        # `SECOND_PROBE_X`, so that row reads the source's own opportunity and
        # every other row reads one proposed here at the input under test.
        oid = driver.SECOND_PROBE_OPPORTUNITY
        if second_x != driver.SECOND_PROBE_X:
            oid = "z-sweep-x%d" % second_x
            store.propose(_live.live_opportunity(
                oid, _rules.make_task("dev", 4)["task_id"],
                "what does input %d reveals on the dev rule task" % second_x,
                instrument="boolean-rule-v1", x=second_x))
        second = probe(oid, second_x)
    choices = control_triple(store, active, "gate")
    return {
        "second_x": second_x,
        "first_verdict": first.get("verdict"),
        "second_verdict": (second or {}).get("verdict"),
        "refuted_rewritten": choices["refuted_rewritten"],
        "refuted_from": choices["refuted_from"],
        "choice_effectful": choices["preserved"]["choice"],
        "choice_refuted": choices["refuted"]["choice"],
        "choice_disconnected": choices["disconnected"]["choice"],
        "observation_dependent": (
            choices["preserved"]["choice"]
            != choices["disconnected"]["choice"]),
        "falsifier_moves_decision": (
            choices["preserved"]["choice"]
            != choices["refuted"]["choice"]),
        "queries_used": store.authority["queries_used"],
        "steps_used": store.authority["steps_used"],
        "observations": len(store.observations),
        "frontier_zero": store.admissible()[0]["opportunity_id"],
    }


def measure(tmp: Path) -> dict:
    freeze = driver.freeze_e0(tmp / "freeze-order")
    amended = driver._live_opportunities(freeze)

    def order(opportunities: list) -> list:
        return [o["opportunity_id"] for o in sorted(
            opportunities,
            key=lambda o: (o["resources"]["queries"] + o["resources"]["steps"],
                           o["opportunity_id"]))]

    without = [o for o in amended
               if o["opportunity_id"] != driver.SECOND_PROBE_OPPORTUNITY]
    return {"frontier_before": order(without),
            "frontier_after": order(amended),
            "baseline": run_case(tmp, None),
            "rows": [run_case(tmp, x) for x in range(N_INPUTS)
                     if x != FIRST_X],
            "cap_sheet": cap_sheet()}


def cap_sheet() -> dict:
    """Does the amendment move a cap? Measured, not read off the memo."""
    return {
        "RESOURCE_KEYS": sorted(_frontier.RESOURCE_KEYS),
        "E0_SANDBOX_CALLS": driver.E0_SANDBOX_CALLS,
        "E12_SANDBOX_CALLS": driver.E12_SANDBOX_CALLS,
        "E0_CALL_CEILING": _live.E0_CALL_CEILING,
        "LIVE_AUTHORITY": dict(_live.LIVE_AUTHORITY),
        "probe_requested_resources": {"queries": 1, "steps": 1},
    }


def collapse_census() -> dict:
    """The memo's section 5 table, recomputed so its claim is checkable.

    Three query-selection policies over the same 40 dev seeds, driving the
    real `VersionSpaceLearner`. Collapse is every output bit's candidate set
    reaching size 1, read off `version_space_sizes()`.

    The queries are read off the task's own tables rather than through
    `RuleSession.query`, because that method refuses past `MAX_QUERIES = 8`
    and the policies under test are asked where the space first collapses,
    which for two of the three is past eight. The values are the ones the
    session would return: `(table >> x) & 1` per bit.

    The three policies are the ones `choose_query` itself offers and one it
    does not. `learner_choose_query` is the shipped seeded tie-break.
    `tiebreak_smallest` is the same disagreement scoring with its docstring's
    "smallest index on ties" in place of the RNG. `fixed_order` is `x=0..15`,
    which is the policy the ledger's figures describe and the study never
    runs.
    """
    def collapse_step(policy: str, seed: int, learner_seed: int):
        tables = _rules.make_task("dev", seed)["tables"]
        learner = _reducer.VersionSpaceLearner(
            _rules.CLASS_TABLES, learner_seed)
        queried: list = []
        for step in range(1, 20):
            open_inputs = [x for x in range(_rules.N_STATES)
                           if x not in queried]
            if not open_inputs:
                return None
            if policy == "learner_choose_query":
                x = learner.choose_query({i: None for i in queried},
                                         budget=20)
            elif policy == "tiebreak_smallest":
                scored = [(learner._disagreement(i), i) for i in open_inputs]
                best = max(s for s, _ in scored)
                x = min(i for s, i in scored if s == best)
            else:
                x = open_inputs[0]
            queried.append(int(x))
            learner.observe(int(x), tuple((t >> x) & 1 for t in tables))
            if all(n == 1 for n in learner.version_space_sizes()):
                return step
        return None

    out = {}
    for learner_seed in (0, 1, 2, 3, 4, 5, 6, 7):
        out["learner_seed_%d" % learner_seed] = {
            policy: _histogram([collapse_step(policy, seed, learner_seed)
                                for seed in range(40)])
            for policy in ("learner_choose_query", "tiebreak_smallest",
                           "fixed_order")}
    return out


def _histogram(ats: list) -> dict:
    counts: dict = {}
    for at in ats:
        key = "never" if at is None else "at_%d" % at
        counts[key] = counts.get(key, 0) + 1
    return counts


extra_opportunity_id = "z-extra"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="m2-second-probe-"))
    try:
        result = measure(tmp)
        print("cap sheet (measured, not quoted):")
        for key, value in result["cap_sheet"].items():
            print("  %-26s %s" % (key, value))
        base = result["baseline"]
        print("\nshipped freeze, ONE probe (the False case):")
        print("  earned verdict      %s" % base["first_verdict"])
        print("  effectful           %s" % base["choice_effectful"])
        print("  disconnected        %s" % base["choice_disconnected"])
        print("  observation_dependent %s"
              % base["observation_dependent"])
        print("  falsifier_moves      %s"
              % base["falsifier_moves_decision"])
        print("  queries/steps used   %d/%d"
              % (base["queries_used"], base["steps_used"]))
        print("\nadmissible order, first 6, before and after the amendment:")
        print("  before %s" % result["frontier_before"][:6])
        print("  after  %s" % result["frontier_after"][:6])
        print("  first unchanged: %s" % (result["frontier_before"][0]
                                         == result["frontier_after"][0]))
        print("\ntwo-probe sweep, second input over every x != 3:")
        print("  %-4s %-14s %-13s %-13s %-8s %-7s %s"
              % ("x", "earned", "effectful", "disconnected",
                 "obs-dep", "falsif", "auth q/s"))
        for row in result["rows"]:
            print("  %-4s %-14s %-13s %-13s %-8s %-7s %d/%d"
                  % (row["second_x"], row["second_verdict"],
                     row["choice_effectful"], row["choice_disconnected"],
                     row["observation_dependent"],
                     row["falsifier_moves_decision"],
                     row["queries_used"], row["steps_used"]))
        dep = [r for r in result["rows"] if r["observation_dependent"]]
        notdep = [r for r in result["rows"] if not r["observation_dependent"]]
        print("\nsummary over the %d second inputs:"
              % len(result["rows"]))
        print("  observation_dependent True  %d of %d"
              % (len(dep), len(result["rows"])))
        print("  observation_dependent False %d of %d  at x=%s"
              % (len(notdep), len(result["rows"]),
                 [r["second_x"] for r in notdep]))
        verdicts: dict = {}
        for row in result["rows"]:
            verdicts.setdefault(row["second_verdict"], []).append(
                row["second_x"])
        for verdict, xs in sorted(verdicts.items(),
                                 key=lambda item: str(item[0])):
            moved = [r["observation_dependent"] for r in result["rows"]
                     if r["second_verdict"] == verdict]
            print("  earned %-14s at x=%s -> obs_dep %d/%d"
                  % (verdict, xs, sum(moved), len(moved)))
        print("\nfrontier[0] under the amendment: %s"
              % sorted({r["frontier_zero"] for r in result["rows"]}))
        print("\ncollapse census over 40 dev seeds, by first query at which"
              " every bit reaches size 1:")
        for learner_seed, row in collapse_census().items():
            print("  %-18s %s" % (
                learner_seed,
                "  ".join("%s=%s" % (name, json.dumps(values))
                          for name, values in row.items())))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())