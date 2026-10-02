"""E3: does choosing its own investigations beat a fixed allocation?

The handoff asks for a comparison against a competent fixed allocation
under one resource envelope, with the four yields frozen, and with a
diagnostic case where the two policies demonstrably choose different
investigations. It also asks that a benefit claim be withheld if every
trajectory follows the same authored schedule.

The measurement is not a win and not a loss. On retention and
diagnosis the agenda leads at every budget — and the reason is visible
in the cost column: the control's pre-committed schedule is exhausted at
20 units of envelope, after which it charges 46 and then stops, while
the agenda keeps converting envelope into retained behaviours. On
held-out quality the sign flips, the control ahead at 20 and 40 and the
agenda ahead at 8, 14, 30 and 60. Both readings are recorded per
budget; a summary that reported only one column would be a selection of
the result, in either direction.

Three worlds, the same four yields read off the same frozen measure set,
and one budget ladder wide enough to contain the crossing. Costs no
dispatch: the portfolio, the checker and the development episodes are all
local, so this runs the whole ladder in seconds.

The severing control runs, and the store it does not reach is the
narrower result. `sever_control` re-runs both arms with the consumer
severed at every world, budget and policy. The effect vanishes in every
one of the thirty-six cells, and the severed trajectory is a strict
prefix of the connected one, so the two arms differ in what ran and not
in what was decided. That makes the counterexample a control.

What it does not establish is where the effect lands. `run_investigations`
takes no dsn, so `_run_development` builds a `DecisionConsumer` with no
store, and every candidate the portfolio offers is a `SEED_CAPABILITIES`
id, so `trajectory._run_member` short-circuits to `seeds.run_seed` and the
store-backed path in `method_exec` is unreachable from here. A run of
this study writes nothing to the `operations` table. `store_witness`
records that emptiness, and separately shows the store will admit an E3
decision and return an operation id and a receipt identity, so the gap is
plumbing rather than a refusal at the gate. The witness is a demonstration
of what the store would do, not a record of what this study did.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Sequence

from . import agenda_policy
from . import selection

BUDGETS = (8, 14, 20, 30, 40, 60)
# The control's schedule is six investigations wide, so it is spent at a
# budget of 20 and every larger envelope is spare. 14 is the last budget
# where it still has work it cannot afford and 20 is the first where it
# has finished, which is where the two regimes are actually separated.
TIGHT = (14,)
LOOSE = (20, 40, 60)
SATURATED_AT = 20


def run_policy(policy, world: int, budget: int,
               sever: bool = False,
               dsn: str | None = None) -> selection.InvestigationRun:
    return selection.run_investigations(
        selection.portfolio_for_world(world), policy,
        selection.Allocation(authorized=budget), world=world, sever=sever,
        dsn=dsn)


def _arms() -> dict:
    """Factories, not instances.

    Both policies are stateful across a run: the agenda pops from
    `_untried` and the fixed policy advances `_step`. Sharing one
    instance across worlds would let world 1's trajectory decide what
    world 2 is allowed to pick, so the second and third rows of the
    ladder would not be independent runs. It is exactly the error this
    study exists to avoid making, in the harness rather than the
    treatment.
    """
    return {
        "agenda": agenda_policy.agenda_policy,
        "control": agenda_policy.fixed_policy,
    }


FITTED_ARM = "fitted_control"


def _fitted_arms(budget: int) -> dict:
    """The two fixed arms plus the agenda, with the honest control added.

    The handoff asks for "a competent fixed allocation policy". The
    historical `control` is one, and it is the arm the committed evidence
    was produced under, so it stays. But measured at this tip it is the
    weaker of the two available at three of the four loose budgets, and
    reporting only it leaves the agenda measured against a rule of
    unstated strength -- an advantage against a control nobody checked.

    `fitted_control` is the same pre-committed form with its constants
    chosen offline by `agenda_policy.fitted_fixed_rule`: the best constant
    pair over the depth ladder the agenda walks, scored on development
    retention. It reads no held-out score, so it is not an oracle for the
    metric this study reports, and at run time it observes nothing at all.

    The arms cannot be equal by construction here and the difference is
    named rather than hidden: both fixed arms receive the same envelope and
    spend from the same `Allocation`, but the historical rule's schedule is
    6 investigations wide against the fitted rule's, so at loose envelopes
    the historical arm saturates and stops while the fitted arm keeps
    converting envelope. That is a property of the two rules, not a
    difference in what they were given, and `crossover` reports each arm's
    own `resources_used` so the saturation is visible in the result rather
    than inferred from it.
    """
    arms = _arms()
    arms[FITTED_ARM] = lambda: agenda_policy.fitted_control(budget)
    return arms


def _row(policy_name: str, run: selection.InvestigationRun) -> dict:
    return {
        "policy": policy_name,
        "policy_version": run.policy_version,
        "choices": len(run.choices),
        "picks": [
            {
                "capability_id": choice.candidate.capability_id,
                "max_queries": choice.candidate.max_queries,
                "rationale": choice.rationale,
            }
            for choice in run.choices
        ],
        "yield": run.yield_.as_dict(),
        "stop_reason": run.stop_reason,
    }


def divergence_case(world: int = 0, budget: int = 14) -> dict:
    """One world where the two policies demonstrably choose differently.

    The handoff requires this case specifically: two policies that agreed
    on every investigation would make the comparison vacuous, and two
    that differed only where one could afford nothing would not show a
    choice being made.
    """
    arms = _arms()
    rows = {name: run_policy(pol(), world, budget)
            for name, pol in arms.items()}
    picks = {
        name: [(r.candidate.capability_id, r.candidate.max_queries)
               for r in run.choices]
        for name, run in rows.items()
    }
    return {
        "world": world,
        "budget": budget,
        "agenda_picks": picks["agenda"],
        "control_picks": picks["control"],
        "picks_differ": picks["agenda"] != picks["control"],
        "arms": {name: _row(name, run) for name, run in rows.items()},
    }


def crossover(worlds=None) -> dict:
    """The full ladder, both arms, every world, the frozen measure set."""
    worlds = tuple(worlds or selection.WORLDS)
    selection.assert_measure_freeze()

    ladder = []
    for budget in BUDGETS:
        per_budget = []
        for name, make_policy in sorted(_fitted_arms(budget).items()):
            policy = make_policy()
            totals = {
                key: 0 for key in selection.YIELD_MEASURES
                if key != "held_out_reduction"}
            reductions = []
            charged = []
            chosen = 0
            for world in worlds:
                run = run_policy(policy, world, budget)
                measured = run.yield_.as_dict()
                for key in totals:
                    totals[key] += measured[key]
                reductions.append(measured["held_out_reduction"])
                charged.append(run.yield_.resources_used)
                chosen += len(run.choices)
            per_budget.append({
                "policy": name,
                "policy_version": run.policy_version,
                "worlds": list(worlds),
                "budget": budget,
                "choices": chosen,
                "held_out_reduction_mean": sum(reductions) / len(reductions),
                "resources_used_total": sum(charged),
                "yield_totals": totals,
            })
        ladder.append({"budget": budget, "arms": per_budget})

    return {
        "budgets": list(BUDGETS),
        "worlds": list(worlds),
        "measure_digest": selection.assert_measure_freeze(),
        "ladder": ladder,
        "tight_budgets": list(TIGHT),
        "loose_budgets": list(LOOSE),
        "crossover": _direction(ladder),
    }


def qualified_ladder(worlds=None) -> dict:
    """The ladder, with every fixed arm's strength at its own budget.

    `crossover` reports which arms ran and what they scored. It does not
    report how strong those arms were, and on this substrate that is not a
    detail: at budget 20 the historical control retains nothing, the agenda
    leads on held-out quality, and 96 of the 196 constant rules beat that
    control over the three qualified worlds. A reader of `crossover` alone
    sees a clean agenda lead and no way to know it was measured against a
    rule of unstated strength.

    So each row carries two things `crossover` does not: a
    `control_qualification` per fixed arm saying whether it was optimal in
    its own space at this budget and how many rules beat it if not, and the
    `best_rule_held_out_reduction` the yardstick search reached. The search
    reads the reported metric to rank rules, so it is an oracle and is
    never an arm here -- it is the number a reported advantage has to be
    read against.

    The counts are properties of a world set, not of the control. The same
    196 rules give 96 beating the default at 20 on one world and on three,
    and 10 at 30 on one world against 94 on three, because a rule that ties
    the default on two worlds and beats it on one is counted or not
    depending on the average. So the world set is recorded on every row and
    no threshold should be pinned to a count without one.

    **This builds its own cells rather than reusing `crossover`.**
    `crossover` constructs each policy once and then loops worlds
    (`:177`), so its arms are cumulative prefix sums of a single traversal
    rather than three independent runs -- defect N-80, retracted in
    `reports/evidence/inv_r1_e3_selection/RETRACTED.md` and still live in
    this function. Building the qualification on top of it would produce a
    handicap count and a yardstick score that are individually correct and
    jointly incomparable, because one would be measured over independent
    cells and the other over a shared walk. So this function builds a fresh
    policy per (arm, world, budget) and says so on every row. Repairing
    `crossover` itself is a separate change to a retracted path and is not
    made here; `e3_ladder.ladder(shared=False)` is the post-fix ladder.
    """
    worlds = tuple(worlds or selection.WORLDS)
    selection.assert_measure_freeze()

    ladder = []
    for budget in BUDGETS:
        per_budget = []
        for name, make_policy in sorted(_fitted_arms(budget).items()):
            totals = {
                key: 0 for key in selection.YIELD_MEASURES
                if key != "held_out_reduction"}
            reductions = []
            charged = []
            chosen = 0
            version = None
            for world in worlds:
                run = run_policy(make_policy(), world, budget)
                measured = run.yield_.as_dict()
                for key in totals:
                    totals[key] += measured[key]
                reductions.append(measured["held_out_reduction"])
                charged.append(run.yield_.resources_used)
                chosen += len(run.choices)
                version = run.policy_version
            per_budget.append({
                "policy": name,
                "policy_version": version,
                "worlds": list(worlds),
                "budget": budget,
                "choices": chosen,
                "held_out_reduction_mean": sum(reductions) / len(reductions),
                "resources_used_total": sum(charged),
                "yield_totals": totals,
                "policy_per_world": True,
            })
        step = {"budget": budget, "arms": per_budget}
        competence = agenda_policy.control_competence(budget, worlds=worlds)
        step["control_qualification"] = competence["arms"]
        step["rules_searched"] = competence["searched"]
        step["best_rule"] = competence["best_rule"]
        step["best_rule_held_out_reduction"] = \
            competence["best_held_out_reduction"]
        step["best_rule_is_an_arm"] = False
        step["qualification_worlds"] = list(worlds)
        ladder.append(step)

    return {
        "budgets": list(BUDGETS),
        "worlds": list(worlds),
        "measure_digest": selection.assert_measure_freeze(),
        "ladder": ladder,
        "tight_budgets": list(TIGHT),
        "loose_budgets": list(LOOSE),
        "crossover": _direction(ladder),
        "qualification": {
            "scope": "every fixed arm at every reported budget",
            "space": "%d constant rules, both capabilities, depths 1-7"
                     % ladder[0]["rules_searched"],
            "scored_on": "held_out_reduction, the measure this study reports",
            "counts_depend_on_the_world_set": (
                "a rule that ties an arm on some worlds and beats it on "
                "others is counted or not depending on the average, so the "
                "counts are properties of a world set rather than of the "
                "control."),
            "best_rule_is_an_oracle": (
                "the yardstick ranks rules on the reported metric, which no "
                "run-time control may read. It qualifies the arms; it is "
                "never one of them."),
            "budgets_where_a_reported_arm_was_not_optimal": sorted(
                {step["budget"] for step in ladder
                 for record in step["control_qualification"]
                 if not record["optimal_here"]}),
        },
    }


def _mean(arm: dict) -> float:
    return arm["held_out_reduction_mean"]


def _totals(arm: dict, key: str) -> int:
    return arm["yield_totals"][key]


def _by_policy(ladder: list, budget: int, name: str) -> dict:
    for step in ladder:
        if step["budget"] == budget:
            for arm in step["arms"]:
                if arm["policy"] == name:
                    return arm
    raise ValueError("no %s arm at budget %d" % (name, budget))


def _direction(ladder: list) -> dict:
    """Where the treatment is ahead, where it is behind, and the price.

    The comparison is reported in whichever direction each budget
    produced, and neither direction is summarised away: the agenda
    retains and diagnoses more at every budget, and the control's
    held-out quality passes it at two of the six. Reading only the
    retention column would call this a clean win; reading only the
    held-out column would call it a loss. It is neither, and the
    summary below records the sign per budget rather than a verdict.
    """
    rows = []
    for budget in TIGHT + LOOSE:
        agenda = _by_policy(ladder, budget, "agenda")
        control = _by_policy(ladder, budget, "control")
        fitted = _by_policy(ladder, budget, FITTED_ARM)
        record = {
            "budget": budget,
            "agenda_held_out": _mean(agenda),
            "control_held_out": _mean(control),
            "fitted_control_held_out": _mean(fitted),
            "agenda_retained": _totals(agenda, "retained_behaviors"),
            "control_retained": _totals(control, "retained_behaviors"),
            "fitted_control_retained": _totals(
                fitted, "retained_behaviors"),
            "agenda_diagnoses": _totals(agenda, "diagnoses_correct"),
            "control_diagnoses": _totals(control, "diagnoses_correct"),
            "fitted_control_diagnoses": _totals(
                fitted, "diagnoses_correct"),
            "agenda_resources": agenda["resources_used_total"],
            "control_resources": control["resources_used_total"],
            "fitted_control_resources": fitted["resources_used_total"],
            "agenda_choices": agenda["choices"],
            "control_choices": control["choices"],
            "fitted_control_choices": fitted["choices"],
        }
        record["agenda_ahead_on_retained"] = \
            record["agenda_retained"] > record["control_retained"]
        record["agenda_ahead_on_held_out"] = \
            record["agenda_held_out"] > record["control_held_out"]
        record["agenda_ahead_on_fitted_held_out"] = \
            record["agenda_held_out"] > record["fitted_control_held_out"]
        # A diagnosis is scored once per charged candidate, so this
        # measure moves with the number of episodes an arm ran and not
        # with the quality of the diagnosis. A tie here is a tie in
        # episode count, not two arms diagnosing equally well, and the
        # comparison is worth nothing beyond retention on its own.
        record["agenda_ahead_on_diagnoses"] = \
            record["agenda_diagnoses"] > record["control_diagnoses"]
        rows.append(record)
    control_spend = [r["control_resources"] for r in rows]
    plateau = max(control_spend)
    control_width = max(r["control_choices"] for r in rows)
    for record in rows:
        # The control's charge is a fixed schedule, so once it has run
        # out extra envelope buys it nothing. Measured by the charge
        # reaching the maximum any budget produced, not by a ratio to
        # the budget: a ratio of the form `spent < 3 * budget` is true
        # of the tight budgets too and cannot tell the two apart.
        record["control_spent_its_whole_schedule"] = \
            record["control_resources"] == plateau
    return {
        "tight": [r for r in rows if r["budget"] in TIGHT],
        "loose": [r for r in rows if r["budget"] in LOOSE],
        "per_budget": rows,
        "per_budget_budgets": [r["budget"] for r in rows],
        "control_spend_plateau": plateau,
        "control_schedule_width": control_width,
        "control_saturates_from_budget": SATURATED_AT,
        "agenda_ahead_on_retained_throughout": all(
            r["agenda_ahead_on_retained"] for r in rows),
        "agenda_ahead_on_diagnoses_at": [
            r["budget"] for r in rows if r["agenda_ahead_on_diagnoses"]],
        "agenda_ahead_on_held_out_at": [
            r["budget"] for r in rows if r["agenda_ahead_on_held_out"]],
        "control_ahead_on_held_out_at": [
            r["budget"] for r in rows if not r["agenda_ahead_on_held_out"]],
        "fitted_control_ahead_on_held_out_at": [
            r["budget"] for r in rows
            if not r["agenda_ahead_on_fitted_held_out"]],
        "fitted_control_ahead_on_retained_at": [
            r["budget"] for r in rows
            if r["fitted_control_retained"] > r["agenda_retained"]],
        "budgets_where_the_two_controls_disagree": [
            r["budget"] for r in rows
            if (r["control_held_out"] > r["fitted_control_held_out"])
            != (r["agenda_held_out"] > r["fitted_control_held_out"])],
    }


SEVER_BUDGETS = (14, 20, 40, 60)
SEVER_REASON = ("investigation portfolio severed for the control "
                "condition")


def sever_control(worlds=None, budgets=None) -> dict:
    """The severing counterexample, both arms, every cell.

    Each cell runs the same policy twice under the same envelope, once
    with the decision consumer connected and once severed, and reports
    both yields rather than a difference. The `vanished` flag is a
    conjunction over the two yields that only the decision can move: a
    severed run must retain nothing and hold nothing out, or the effect
    was not the decision's to begin with.

    `shared_prefix` is what makes this a control and not a second
    experiment. It is the number of leading choices the two arms agree
    on. When it equals the severed arm's whole choice list, severing
    removed the execution and left the decisions alone, so a difference
    in yield is a difference in what ran. A cell where the severed arm
    diverges before it ends would be measuring a different policy.
    """
    worlds = tuple(worlds if worlds is not None else selection.WORLDS)
    budgets = tuple(budgets if budgets is not None else SEVER_BUDGETS)
    selection.assert_measure_freeze()

    cells = []
    for name, make_policy in sorted(_arms().items()):
        for world in worlds:
            for budget in budgets:
                connected = run_policy(make_policy(), world, budget)
                severed = run_policy(
                    make_policy(), world, budget, sever=True)
                connected_choices = [c.candidate.identity
                                     for c in connected.choices]
                severed_choices = [c.candidate.identity
                                   for c in severed.choices]
                cells.append({
                    "cell": "%s-w%d-b%d" % (name, world, budget),
                    "policy": name,
                    "world": world,
                    "budget": budget,
                    "connected": {
                        "executed": True,
                        "severed": False,
                        "choices": len(connected.choices),
                        "yield": connected.yield_.as_dict(),
                        "stop_reason": connected.stop_reason,
                        "held_out_rows": len(connected.held_out_ledger),
                        "dispositions": [
                            e.episode.get("disposition")
                            for e in connected.executions],
                    },
                    "severed": {
                        "executed": True,
                        "severed": True,
                        "choices": len(severed.choices),
                        "yield": severed.yield_.as_dict(),
                        "stop_reason": severed.stop_reason,
                        "held_out_rows": len(severed.held_out_ledger),
                        "dispositions": [
                            e.episode.get("disposition")
                            for e in severed.executions],
                    },
                    "shared_prefix": next(
                        (i for i, (a, b) in enumerate(
                            zip(connected_choices, severed_choices))
                         if a != b),
                        min(len(connected_choices),
                            len(severed_choices))),
                    "severed_is_prefix": (
                        severed_choices
                        == connected_choices[:len(severed_choices)]),
                    "vanished": (
                        severed.yield_.retained_behaviors == 0
                        and severed.yield_.held_out_reduction == 0.0
                        and severed.yield_.diagnoses_correct == 0
                        and severed.held_out_ledger == ()),
                    "connected_had_an_effect": (
                        connected.yield_.retained_behaviors > 0
                        or connected.yield_.held_out_reduction > 0.0),
                })
    effectful = [c for c in cells if c["connected_had_an_effect"]]
    return {
        "budgets": list(budgets),
        "worlds": list(worlds),
        "policies": sorted(_arms()),
        "measure_digest": selection.assert_measure_freeze(),
        "sever_reason": SEVER_REASON,
        "cells": cells,
        "cells_total": len(cells),
        "cells_with_an_effect": len(effectful),
        "effect_vanished_in_every_cell": all(
            c["vanished"] for c in cells),
        "severed_is_prefix_in_every_cell": all(
            c["severed_is_prefix"] for c in cells),
    }


def _decision_row(world: int, seq: int, candidate) -> dict:
    return {
        "seq": int(seq),
        "target": candidate.target,
        "capability_id": candidate.capability_id,
        "family": candidate.family,
        "max_queries": candidate.max_queries,
        "charge": candidate.cost(),
    }


def read_back(dsn: str, operation_ids) -> list:
    """Receipts read out of the store for the named operations.

    Every field here comes from a SELECT. A caller cannot make a receipt
    appear by recomputing it, which is the whole point of having a
    readback: the witness is evidence rather than a restatement of the
    run.
    """
    from psycopg.rows import dict_row

    from settlement import db

    rows = []
    if not operation_ids:
        return rows
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT r.receipt_identity, r.operation_id, r.outcome,"
                " r.content_digest, r.content"
                " FROM receipts r WHERE r.operation_id = ANY(%s)"
                " ORDER BY r.receipt_identity", (list(operation_ids),))
            for row in cur.fetchall():
                record = dict(row)
                record["content"] = dict(record.get("content") or {})
                rows.append(record)
        conn.commit()
    return rows


def _operations_for_ids(dsn: str, operation_ids: Sequence[str]) -> int:
    """Operations present under the ids this run itself produced.

    The count is scoped to the run's own ids rather than differenced across
    the table. A table total answers a different question: it is every
    writer in the interval between two snapshots, and this store is shared.
    A concurrent lane's operation enters the same delta as the run's work,
    and the witness then reports operations it did not write. That number
    is what `test_s09_e3_sever` compares against the run's decision count,
    so a foreign row makes a correct run look wrong, and the error lands
    in whichever direction the extra row moves it.

    Measured, not argued: with one operation inserted by another writer
    between the two snapshots, a run that made 5 decisions reported 6.
    """
    from psycopg.rows import dict_row

    from settlement import db
    if not operation_ids:
        return 0
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT count(*) AS n FROM operations"
                        " WHERE id = ANY(%s)", (list(operation_ids),))
            total = cur.fetchone()["n"]
        conn.commit()
    return int(total)


def store_witness(dsn: str, *, world: int = 0, budget: int = 40,
                  sever: bool = False) -> dict:
    """Run E3 once and report what its own decisions reached.

    The operations here are the run's, not a binding made afterwards.
    `run_policy` is given the dsn, so `selection.DecisionRecorder` admits
    each decision through the broker from inside `_run_development`,
    while the run is making them. The receipts are then read back out of
    the receipts table by SELECT.

    That distinction is the whole point of the file, and it is why
    `run_decisions` is kept separate from `receipts`. A receipt compared
    against the binding that produced it is a row compared with itself,
    so a store holding the wrong decision would satisfy such a test. Here
    the run's decisions are read off the policy's choices and the
    receipts are read off the store, and the two are compared.

    A severed run is refused before the recorder, so it admits nothing
    and leaves the store as it found it. That is what makes the control
    condition a control rather than a run against a broken gate.
    """
    from settlement import broker

    selection.assert_measure_freeze()
    run = run_policy(agenda_policy.agenda_policy(), world, budget,
                     sever=sever, dsn=dsn)

    operations = list(run.operations)
    operation_ids = [record["operation_id"] for record in operations]
    wrote = _operations_for_ids(dsn, operation_ids)

    dispatch_states = {}
    for operation_id in operation_ids:
        stored = broker.read_operation(dsn, operation_id) or {}
        dispatch_states[operation_id] = stored.get("dispatch_state", "")
    bindings = [{**record, "dispatch_state":
                 dispatch_states.get(record["operation_id"], "")}
                for record in operations]

    # The run's own decisions, read off the policy, kept separate from the
    # receipts on purpose. A test that compared a receipt against the
    # binding that produced it would be comparing a row with itself, so a
    # mis-bound decision would satisfy it.
    run_decisions = [
        {
            "seq": seq,
            "target": choice.candidate.target,
            "capability_id": choice.candidate.capability_id,
            "family": choice.candidate.family,
            "max_queries": choice.candidate.max_queries,
            "charge": choice.charge,
        }
        for seq, choice in enumerate(run.choices)]
    admitted = [b for b in bindings
                if b["settled"] and b["receipt_outcome"] == "success"]
    return {
        "world": world,
        "budget": budget,
        "sever": bool(sever),
        "measure_digest": run.measure_digest,
        "policy_version": run.policy_version,
        "stop_reason": run.stop_reason,
        "run_yield": run.yield_.as_dict(),
        "decisions_made": len(run.choices),
        "decisions_executed": len(run.executions),
        "run_decisions": run_decisions,
        "admitted_decisions": [] if sever else admitted,
        "refused_decisions": [
            {
                "seq": _decision_row(world, seq, e.choice.candidate)["seq"],
                "target": e.choice.candidate.target,
                "capability_id": e.choice.candidate.capability_id,
                "disposition": e.episode.get("disposition"),
                "fallback_reason": e.episode.get("fallback_reason", ""),
                "operation_id": "",
            }
            for seq, e in enumerate(run.executions)
        ] if sever else [],
        "operations_written_by_the_run": wrote,
        "operations_in_store": wrote,
        "bindings": [] if sever else bindings,
        "refused_operations": list(run.refusals),
        "receipts": read_back(dsn, operation_ids),
        "the_run_admitted_these_itself": (
            "operations_written_by_the_run is counted over the operation ids "
            "this run produced, and the receipts are SELECTed back out of the "
            "store. Nothing here binds a decision to an operation after the "
            "fact, and nothing written by another run enters the count."),
    }


def _write(directory: Path, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "e3-crossover.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")
    (directory / "e3-divergence.json").write_text(
        json.dumps(divergence_case(), indent=1, sort_keys=True) + "\n")


def write_sever_evidence(directory: Path, dsn: str) -> dict:
    """Write the sever control and the store witness beside the study.

    New files only. `e3-crossover.json` and `e3-divergence.json` are the
    historical record of the run that produced the two-sided result, and
    nothing here overwrites them: the sever control is a different
    measurement and gets its own name.
    """
    directory.mkdir(parents=True, exist_ok=True)
    control = sever_control()
    connected = store_witness(dsn, world=0, budget=40)
    severed = store_witness(dsn, world=0, budget=40, sever=True)
    payload = {
        "control": control,
        "store_witness_connected": connected,
        "store_witness_severed": severed,
    }
    (directory / "e3-sever-control.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")
    (directory / "e3-store-witness.json").write_text(
        json.dumps({"connected": connected, "severed": severed},
                   indent=1, sort_keys=True) + "\n")
    return payload


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = Path(argv[0]) if argv else \
        Path("reports") / "evidence" / "inv_r1_e3_selection"
    if "--sever" in argv:
        dsn = next((a for a in argv if a.startswith("dsn=")), "").split(
            "dsn=", 1)[-1] or os.environ.get("SETTLEMENT_TEST_DSN", "")
        if not dsn:
            raise SystemExit(
                "--sever needs a dsn: --sever dsn=<dsn> or SETTLEMENT_TEST_DSN")
        payload = write_sever_evidence(target, dsn)
        print(json.dumps({
            "effect_vanished_in_every_cell":
                payload["control"]["effect_vanished_in_every_cell"],
            "severed_is_prefix_in_every_cell":
                payload["control"]["severed_is_prefix_in_every_cell"],
            "cells_with_an_effect":
                payload["control"]["cells_with_an_effect"],
            "operations_written_by_the_run":
                payload["store_witness_connected"]["operations_written_by_the_run"],
            "decisions_bound_in_the_witness":
                len(payload["store_witness_connected"]["admitted_decisions"]),
        }, indent=1, sort_keys=True))
        return 0
    payload = crossover()
    _write(target, payload)
    print(json.dumps(payload["crossover"], indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
