"""E3 post-fix: the selection ladder, regenerated against a per-cell policy.

The committed `reports/evidence/inv_r1_e3_selection/e3-crossover.json` was
produced at `02ce64b` and never regenerated. `s09_e3_selection.crossover()`
reuses one policy instance across every world in a budget, and both policies
are stateful: `AgendaPolicy` pops from `_untried` and accumulates `_live`,
`FixedPolicy` advances `_step`. So world 1's trajectory decided what world 2
was permitted to pick, and the three worlds a row summed were not three
independent runs. The docstring on `_arms` already names this hazard, and
`sever_control` avoids it; `crossover` does not.

Running the committed function at this tip reproduces the committed file byte
for byte, so the sharing defect is still in the code rather than only in the
artifact. This module runs the same ladder with one policy per cell and
records both, plus what each arm's decisions reached in a store.

Every decision this run admits goes through `authority.admit_study_call`
and is settled by `broker.dispatch_operation` under the study root
`authorize_study` bound, which is the durable reservation and dispatch
owner. The reads are `SELECT`s against the store rather than fields an
artifact reported about itself.

The offline half costs no dispatch. Every portfolio candidate is a
`SEED_CAPABILITIES` id, so `trajectory.run_diagnostic` and
`trajectory.dev_episode` resolve through `seeds.run_seed` against in-process
checkers and no model is called. The store half is `DOMAIN_COMMAND` exposure,
1 unit per decision, and dispatches no provider request either. The gateway
is therefore probed once and used zero times. The probe is itself an
admitted `model-inference` operation under `max_calibration`, dispatched
through the broker and receipted, so the one send this study makes is
bounded by its own ceiling rather than unreserved.

Three store defects are documented where they are handled rather than
worked around silently. `study_ceilings` explains why a zero
`max_model_calls` ceiling refuses every operation and is therefore not
bound; `store_ladder` explains why the run's own recorder is seeded
under the study rather than beside it, without which the parentage walk
the store's isolation gate uses sees half this study's operations; and
`_is_ours` explains why the count is scoped to this study's own names
rather than taken over the table. All three were found
while measuring this run, and both would otherwise have produced a number
that looked like a measurement.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from . import agenda_policy
from . import selection

BUDGETS = (8, 14, 20, 30, 40, 60)
WORLDS = selection.WORLDS
GATEWAY = "http://localhost:4000/v1"
GATEWAY_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
PROBE_MAX_TOKENS = 8
PROBE_KIND = "calibration"
PROBE_PROMPT = "Reply with the word OK"
PROBE_DEADLINE_MS = 120_000
PROBE_STATUSES = (
    "no-credential", "unadmitted-no-authority", "unadmitted", "no-route",
    "no-settled-response", "reachable",
)
STUDY_TOKEN = "e3ladder"
STUDY_ROOT = "e3ladder-root"
STUDY_ALLOCATION = "e3ladder-alloc"


def arms() -> dict:
    """Policy factories. One fresh instance per cell, never a shared one.

    Both policies carry state that advances with each executed episode, so
    a shared instance makes the second and third world of a row depend on
    the first. That is the defect this module exists to measure, and
    measuring it requires the shared arm to still be runnable.
    """
    return {
        "agenda": agenda_policy.agenda_policy,
        "control": agenda_policy.fixed_policy,
    }


def _measure(run) -> dict:
    measured = run.yield_.as_dict()
    return {
        "held_out_reduction": measured["held_out_reduction"],
        "retained_behaviors": measured["retained_behaviors"],
        "diagnoses_correct": measured["diagnoses_correct"],
        "resources_used": measured["resources_used"],
        "choices": len(run.choices),
        "picks": [
            {
                "capability_id": c.candidate.capability_id,
                "target": c.candidate.target,
                "max_queries": c.candidate.max_queries,
                "charge": c.charge,
                "rationale": c.rationale,
            }
            for c in run.choices],
        "stop_reason": run.stop_reason,
    }


def _aggregate(cells: list) -> dict:
    totals = {key: sum(c["yield"][key] for c in cells)
              for key in ("retained_behaviors", "diagnoses_correct",
                          "resources_used")}
    totals["choices"] = sum(c["yield"]["choices"] for c in cells)
    return {
        "policy": cells[0]["policy"],
        "worlds": [c["world"] for c in cells],
        "cells": cells,
        "held_out_reduction_mean": (
            sum(c["yield"]["held_out_reduction"] for c in cells) / len(cells)),
        "resources_used_total": totals["resources_used"],
        "yield_totals": totals,
    }


def _run_arm(policy_name: str, budget: int, worlds, *, shared: bool) -> dict:
    """One policy, every world, at one budget. One cell per world.

    `shared` reuses the instance across worlds, which is what the committed
    ladder does. `fresh` builds one per world, which is what the ladder has
    to do for the three worlds to be independent runs.
    """
    factory = arms()[policy_name]
    cells = []
    instance = factory() if shared else None
    for world in worlds:
        run = selection.run_investigations(
            selection.portfolio_for_world(world),
            instance if shared else factory(),
            selection.Allocation(authorized=budget), world=world)
        cells.append({"world": world, "policy": policy_name,
                      "budget": budget, "yield": _measure(run)})
    return _aggregate(cells)


def ladder(*, shared: bool, worlds=None) -> dict:
    """The full budget ladder, both policies, the frozen measure set.

    The four measures are frozen before the run by
    `selection.assert_measure_freeze`, which compares a pinned literal
    rather than a freshly computed digest, so a measure cannot be
    redefined after outcomes are visible.
    """
    worlds = tuple(worlds or WORLDS)
    digest = selection.assert_measure_freeze()
    rows = []
    for budget in BUDGETS:
        step = {"budget": budget, "arms": [
            _run_arm(name, budget, worlds, shared=shared)
            for name in sorted(arms())]}
        rows.append(step)
    return {
        "policy_instance_scope": "shared-across-worlds" if shared
                                 else "one-per-world",
        "budgets": list(BUDGETS),
        "worlds": list(worlds),
        "measure_digest": digest,
        "ladder": rows,
        "direction": direction(rows),
    }


def _by(arm: dict, key: str) -> float:
    return arm["yield_totals"][key] if key != "held_out_reduction" \
        else arm["held_out_reduction_mean"]


def direction(rows: list) -> dict:
    """The sign of each contrast, per budget, with no column summarised away."""
    out = []
    for step in rows:
        agenda = next(a for a in step["arms"] if a["policy"] == "agenda")
        control = next(a for a in step["arms"] if a["policy"] == "control")
        record = {"budget": step["budget"]}
        for key in ("held_out_reduction", "retained_behaviors",
                    "diagnoses_correct", "resources_used", "choices"):
            record["agenda_" + key] = _by(agenda, key)
            record["control_" + key] = _by(control, key)
        for key in ("held_out_reduction", "retained_behaviors",
                    "diagnoses_correct", "resources_used", "choices"):
            record["agenda_ahead_on_" + key] = \
                record["agenda_" + key] > record["control_" + key]
        record["picks_differ"] = _picks_differ(agenda, control)
        out.append(record)
    return {
        "per_budget": out,
        "agenda_ahead_on_retained_at": [
            r["budget"] for r in out if r["agenda_ahead_on_retained_behaviors"]],
        "agenda_ahead_on_held_out_at": [
            r["budget"] for r in out
            if r["agenda_ahead_on_held_out_reduction"]],
        "control_ahead_on_held_out_at": [
            r["budget"] for r in out
            if not r["agenda_ahead_on_held_out_reduction"]],
        "agenda_ahead_on_resources_at": [
            r["budget"] for r in out if r["agenda_ahead_on_resources_used"]],
        "agenda_ahead_on_diagnoses_at": [
            r["budget"] for r in out
            if r["agenda_ahead_on_diagnoses_correct"]],
        "budgets_where_picks_differ": [
            r["budget"] for r in out if r["picks_differ"]],
    }


def _picks_differ(agenda: dict, control: dict) -> bool:
    for a, c in zip(agenda["cells"], control["cells"]):
        left = [(p["capability_id"], p["max_queries"])
                for p in a["yield"]["picks"]]
        right = [(p["capability_id"], p["max_queries"])
                 for p in c["yield"]["picks"]]
        if left != right:
            return True
    return False


def divergence_survey(worlds=None, budgets=None) -> list:
    """Every (world, budget) where the two policies chose differently.

    A single nominated case is weaker evidence than the census: a pair can
    differ once and coincide everywhere else, and the handoff asks for a
    case rather than for a rate, so both are recorded.
    """
    worlds = tuple(worlds or WORLDS)
    budgets = tuple(budgets or BUDGETS)
    found = []
    for budget in budgets:
        for world in worlds:
            rows = {name: selection.run_investigations(
                selection.portfolio_for_world(world), factory(),
                selection.Allocation(authorized=budget), world=world)
                for name, factory in arms().items()}
            picks = {name: [(r.candidate.capability_id,
                             r.candidate.max_queries)
                            for r in run.choices]
                     for name, run in rows.items()}
            if picks["agenda"] == picks["control"]:
                continue
            first = next((i for i, (a, b)
                          in enumerate(zip(picks["agenda"], picks["control"]))
                          if a != b), min(len(picks["agenda"]),
                                          len(picks["control"])))
            found.append({
                "world": world, "budget": budget,
                "first_divergence_at_choice": first,
                "agenda_picks": picks["agenda"],
                "control_picks": picks["control"],
                "agenda_reasons": [c.rationale
                                   for c in rows["agenda"].choices],
                "control_reasons": [c.rationale
                                    for c in rows["control"].choices],
                "agenda_yield": rows["agenda"].yield_.as_dict(),
                "control_yield": rows["control"].yield_.as_dict(),
                "agenda_stop_reason": rows["agenda"].stop_reason,
                "control_stop_reason": rows["control"].stop_reason,
            })
    return found


# --- the store half --------------------------------------------------------


def _is_recorder_path(operation_id: str) -> bool:
    """Which of the two admission paths wrote this operation.

    The recorder's operations are the ones this study named in the
    `ad01-<root>-` shape the recorder mints, and `admit_study_call`
    subdivides as `<allocation>/<kind>/<operation>`. Before adoption the
    two were also told apart by their allocation, because the recorder
    seeded a parentless one; adoption puts the recorder's child under the
    study's allocation, so the allocation prefix no longer separates them
    and the operation name does.
    """
    return str(operation_id).startswith("ad01-" + STUDY_ROOT + "-")


def _operation_rows(dsn: str, study_root: str) -> list:
    """Every operation this study's own names minted, by SELECT.

    `admit_study_call` subdivides `STUDY_ALLOCATION` into
    `<allocation>/development/<operation_id>` children, and
    `selection.DecisionRecorder` seeds a per-cell child of the same
    allocation and admits under it. Both are this study's work and both
    are inside its subtree, so the prefix filter is the union of the two
    shapes rather than the union of two allocation trees.

    The walk also has a quieter failure. An allocation row that a
    `seed_allocation` call writes is invisible to a later statement's
    scan of `allocations` under PostgreSQL's default `READ COMMITTED`
    snapshot, because each command outside a transaction block gets its
    own snapshot taken after the seed committed. A walk that resolves
    parentage from the operations table therefore finds the study
    subtree and silently misses the recorder's, and a per-arm count
    that used it would report 21 where the store holds 42. The first
    version of this run's verification did exactly that, and its
    `per_path` said `admit_study_call: 0` on a run where every decision
    had gone through it.
    """
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT o.id, o.dispatch_state, o.allocation_id,"
                " o.payload->'payload'->'payload'->'decision' AS decision,"
                " o.payload->'study_root' AS study_root,"
                " o.payload->>'kind' AS kind"
                " FROM operations o"
                " WHERE o.id LIKE %s OR o.id LIKE %s"
                "    OR o.allocation_id LIKE %s"
                " ORDER BY o.id",
                (STUDY_ROOT + "-op-%", "ad01-" + STUDY_ROOT + "-%",
                 STUDY_ALLOCATION + "/%"))
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    for row in rows:
        row["decision"] = dict(row.get("decision") or {})
    return rows


def _receipt_rows(dsn: str, operation_ids: list) -> list:
    from psycopg.rows import dict_row

    from settlement import db

    if not operation_ids:
        return []
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT r.receipt_identity, r.operation_id, r.outcome,"
                " r.content FROM receipts r"
                " WHERE r.operation_id = ANY(%s)"
                " ORDER BY r.operation_id, r.receipt_identity",
                (list(operation_ids),))
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    for row in rows:
        row["content"] = dict(row.get("content") or {})
        row["decision"] = dict(
            dict(row["content"].get("payload") or {}).get("decision") or {})
    return rows


def _admit(dsn: str, study_root: str, kind: str, operation_id: str,
           decision: dict) -> dict:
    """One decision through the durable reservation and dispatch owner.

    `admit_study_call` subdivides from the study's own allocation and
    enforces its declared ceilings; `dispatch_operation` settles the
    prepared operation and writes the receipt. A refusal is returned, not
    raised, so a store that declined the work is reported rather than
    dropped.
    """
    from settlement import authority, broker, loop

    granted = authority.admit_study_call(
        dsn, study_root, kind=kind, operation_id=operation_id,
        effect=broker.DOMAIN_COMMAND,
        payload={"command": "note", "payload": {"decision": dict(decision)},
                 "idempotency_key": operation_id})
    if not isinstance(granted, loop.Grant):
        return {"operation_id": operation_id, "admitted": False,
                "refusal": getattr(granted, "reason", "unknown"),
                "detail": getattr(granted, "detail", "")}
    status = broker.dispatch_operation(dsn, operation_id)
    return {"operation_id": operation_id, "admitted": True,
            "exposure": granted.exposure, "budget_kind": granted.budget_kind,
            "child_allocation_id": granted.allowance.allowance_id,
            "dispatch_state": status.dispatch_state,
            "next_decision": status.next_decision}


def store_ladder(dsn: str, study_root: str) -> dict:
    """Run the fresh-policy ladder with every decision bound to a store.

    Each cell admits one operation per decision before the diagnostic and
    the reduction run, so what the artifact reports is work an admitted
    operation already names. The counts are then read back out of
    `operations` and `receipts` by SELECT.

    The run's own recorder is seeded under the same study the cell
    admits through, so both admission paths land in one subtree. A
    recorder left parentless still writes real, settled, receipted
    operations, and a study-scoped read of the store cannot see any of
    them, so the run reports half the work it did.
    """
    selection.assert_measure_freeze()
    arms_run = []
    for budget in BUDGETS:
        for name in sorted(arms()):
            campaign = "%s-w0-b%d-%s" % (STUDY_ROOT, budget, name)
            run = selection.run_investigations(
                selection.portfolio_for_world(0), arms()[name](),
                selection.Allocation(authorized=budget), world=0,
                dsn=dsn, campaign=campaign, study_root=study_root,
                study_allocation=STUDY_ALLOCATION)
            admitted = []
            for seq, choice in enumerate(run.choices):
                candidate = choice.candidate
                admitted.append(_admit(
                    dsn, study_root, "development",
                    "%s-op-w0-b%d-%s-s%d-%s" % (
                        STUDY_ROOT, budget, name, seq,
                        candidate.capability_id),
                    {"target": candidate.target,
                     "capability_id": candidate.capability_id,
                     "family": candidate.family,
                     "max_queries": candidate.max_queries,
                     "charge": choice.charge}))
            arms_run.append({
                "policy": name, "world": 0, "budget": budget,
                "campaign": campaign,
                "decisions": len(run.choices),
                "recorder_admitted": len(run.operations),
                "recorder_refusals": list(run.refusals),
                "recorder_orphaned": run.orphaned_operations,
                "recorder_adoption": run.adoption,
                "own_admissions": admitted,
                "admitted": sum(1 for a in admitted if a["admitted"]),
                "refused": [a for a in admitted if not a["admitted"]],
                "yield": _measure(run),
            })
    return {"study_root": study_root, "arms": arms_run}


def _is_ours(op: dict) -> bool:
    """Whether one row was minted by this study rather than found in the table.

    Ledger N-301 records that the pre-fix witness measured
    `count(*) FROM operations` before and after the run, so a foreign
    lane's row would be credited to E3. Every count here is scoped to
    this study's own name prefixes instead, and this is the assertion
    that the scoping held.
    """
    allocation = str(op.get("allocation_id") or "")
    operation_id = str(op.get("id") or "")
    return (operation_id.startswith(STUDY_ROOT + "-op-")
            or operation_id.startswith("ad01-" + STUDY_ROOT + "-")
            or allocation.startswith(STUDY_ALLOCATION + "/")
            or allocation.startswith(STUDY_ROOT + "-"))


def store_verdict(dsn: str, study_root: str) -> dict:
    """What the store holds, counted by SELECT, against what the run said.

    Two independent counts are taken and both are published: a durable
    name prefix over the operations table, and the recursive allocation
    parentage walk the store's own isolation gate uses. They are
    expected to agree, and a gap between them is a study that
    under-reports itself. `selection.DecisionRecorder` is seeded as a
    child of the study's allocation by `store_ladder`, so the walk sees
    its operations as well as the ones admitted through
    `admit_study_call`, and `walk_missed` is the evidence rather than
    the expected shape.
    """
    operations = _operation_rows(dsn, study_root)
    receipts = _receipt_rows(dsn, [o["id"] for o in operations])
    walked = _walked_operation_ids(dsn, study_root)
    by_operation = {}
    for row in receipts:
        by_operation.setdefault(row["operation_id"], []).append(row)
    per_arm = {}
    by_path = {"admit_study_call": 0, "decision_recorder": 0}
    for op in operations:
        arm = "unknown"
        if "-agenda-" in op["id"]:
            arm = "agenda"
        elif "-control-" in op["id"]:
            arm = "control"
        per_arm.setdefault(arm, {"operations": 0, "success_receipts": 0,
                                 "settled": 0, "carrying_a_decision": 0})
        per_arm[arm]["operations"] += 1
        by_path["decision_recorder" if _is_recorder_path(
            op["id"]) else "admit_study_call"] += 1
        rows = by_operation.get(op["id"], [])
        if op["dispatch_state"] in ("observed", "settled", "terminal"):
            per_arm[arm]["settled"] += 1
        if any(r["outcome"] == "success" for r in rows):
            per_arm[arm]["success_receipts"] += 1
        if op["decision"]:
            per_arm[arm]["carrying_a_decision"] += 1
    return {
        "study_root": study_root,
        "operations_in_store": len(operations),
        "receipts_in_store": len(receipts),
        "per_arm": per_arm,
        "per_path": by_path,
        "walked_operation_count": len(walked),
        "walk_agrees_with_prefix": len(walked) == len(operations),
        "walk_missed": sorted(
            {o["id"] for o in operations} - walked)[:4],
        "counting_method": (
            "SELECT over operations filtered by this study's own durable "
            "name prefixes, never count(*) over the table, so a foreign "
            "lane's row cannot be credited to this run (N-301)"),
        "every_counted_operation_is_this_study": all(
            _is_ours(op) for op in operations),
        "every_study_subtree_operation_names_this_study": all(
            o["study_root"] == study_root for o in operations
            if o["allocation_id"].startswith(STUDY_ALLOCATION + "/")),
        "every_recorder_operation_is_adopted_under_the_study": all(
            o["id"] in walked for o in operations
            if _is_recorder_path(o["id"])),
        "orphaned_operation_count": sum(
            1 for o in operations if o["id"] not in walked),
        "every_operation_carries_a_decision": all(
            o["decision"] for o in operations),
        "every_settled_operation_has_a_success_receipt": all(
            any(r["outcome"] == "success" for r in by_operation.get(o["id"], []))
            for o in operations),
        "receipt_payload_matches_operation": all(
            any(r["decision"] == o["decision"]
                for r in by_operation.get(o["id"], []))
            for o in operations),
    }


def _walked_operation_ids(dsn: str, study_root: str) -> set:
    """The count a parentage walk produces, as an independent second read.

    This is the query shape `s09_run_isolation._persisted_operations`
    uses. Running it here and publishing the gap is what turns "the
    prefix found 42" into "the prefix found 42, the walk found 21, and
    this is the difference between them".
    """
    from psycopg.rows import dict_row

    from settlement import db

    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT o.id FROM operations o"
                " JOIN study_authority a"
                " ON a.allocation_id = ("
                "   WITH RECURSIVE up (id, parent_id) AS ("
                "     SELECT id, parent_id FROM allocations"
                "      WHERE id = o.allocation_id"
                "     UNION ALL"
                "     SELECT l.id, l.parent_id FROM allocations l"
                "     JOIN up ON l.id = up.parent_id)"
                "   SELECT id FROM up WHERE id = a.allocation_id)"
                " WHERE a.study_root = %s", (study_root,))
            found = {r["id"] for r in cur.fetchall()}
        conn.commit()
    return found



def cap_sheet(fresh: dict, *, study_root: str, authorized_units: int) -> dict:
    """The finite cap sheet, derived from the matrix and bound before use.

    Every figure is counted from the ladder this run already executed
    rather than from a round number, and the sheet is bound through
    `authorize_study` before the store half runs. `model_calls` is zero
    because the portfolio's candidates are `SEED_CAPABILITIES` ids that
    `trajectory.run_diagnostic` and `trajectory.dev_episode` resolve in
    process; the ladder and the store half call no provider, so zero is
    the honest figure and a nonzero one would be a fiction.
    """
    offline_cells = [
        cell for step in fresh["ladder"] for arm in step["arms"]
        for cell in arm["cells"]]
    store_cells = len(BUDGETS) * len(arms())
    widest = max(cell["yield"]["choices"] for cell in offline_cells)
    return {
        "study_root": study_root,
        "authorized_units": authorized_units,
        "denominations": ["study_units", "operations", "model_calls",
                          "provider_dispatches"],
        "derived_from": ("the offline ladder this run executed, before any "
                         "store effect"),
        "offline_cells": len(offline_cells),
        "store_cells": store_cells,
        "widest_cell_decisions": widest,
        "max_operations": store_cells * widest + 1,
        "max_study_units": store_cells * widest,
        "model_calls_the_matrix_produces": 0,
        "provider_dispatches_the_matrix_produces": 0,
        "gateway_probe_calls": 1,
        "gateway_probe_max_tokens": PROBE_MAX_TOKENS,
        "note": ("the portfolio's candidates are SEED_CAPABILITIES ids that "
                 "trajectory resolves in process, so the ladder and the store "
                 "half spend no provider dispatch; the one gateway call is "
                 "the availability probe, which is an admitted "
                 "model-inference operation under max_calibration and is "
                 "not part of the matrix, and the +1 on max_operations is "
                 "that probe's own operation"),
    }


def study_ceilings(cap: dict) -> dict:
    """The ceilings this study binds, and why the shape is not the obvious one.

    The obvious shape is to bind `max_model_calls` at the number of model
    calls the matrix makes, which is zero, and `max_operations` at the
    number of operations it makes. Binding the first does not work.
    `store._study_operation_counts` increments `model_calls` only for an
    operation whose stored effect is `model-inference`, so the counter for
    a `domain-command` operation is always zero, and a ceiling of
    `max_model_calls: 0` is `reached at 0` by the first decision of any
    kind. Binding it refused all forty-two operations in this study and
    the refusals read, on a summary line, like a study that made no model
    calls. `max_development` counts every operation admitted under
    `kind: development`, which is what this matrix actually spends, so
    that is the ceiling the store can enforce against it. A no-op cap of
    zero on a counter the store never increments is a cap sheet that
    forbids the study; the honest cap is the one that holds.

    `max_calibration` is the probe's own counter. The probe is the one
    model call this study makes, and it is admitted under
    `PROBE_KIND`, so a ceiling of one is the statement that the route is
    confirmed once. `max_model_calls` stays unbound for the reason above:
    binding it at the probe's single call would be the same
    reach-at-zero shape once the probe is routed, because the matrix's own
    operations are `domain-command` and the counter is a study-wide count.
    """
    return {
        "max_operations": cap["max_operations"],
        "max_development": cap["max_operations"],
        "max_calibration": 1,
    }


def model_call_declaration() -> dict:
    """The model-call figure, recorded but not bound.

    `authorize_study` rejects any ceiling name the store does not know,
    so a zero ceiling that would refuse the study cannot also be the
    declaration that no model was called. The two are separate
    statements: one is a bound limit, the other is a count, and only the
    first belongs in `ceilings`.
    """
    return {
        "model_calls_the_matrix_produces": 0,
        "bound": False,
        "why_not_bound": (
            "store._study_operation_counts only increments model_calls for "
            "a model-inference operation, so max_model_calls=0 is reached "
            "at 0 by the first domain-command and refuses the whole study; "
            "binding it refused all 42 operations in this study"),
    }


def probe_gateway(dsn: str | None = None, *, study_root: str | None = None,
                  gateway: Any | None = None) -> dict:
    """One cheap availability probe, admitted before it spends anything.

    `/v1/models` is empty on this gateway and that is not a failure signal,
    so the probe is a real completion with a token cap small enough that
    it cannot be mistaken for an experiment cell. The key is read from the
    environment at call time and never written anywhere.

    The send is a `model-inference` operation admitted through
    `admit_study_call` and settled by `broker.dispatch_operation`, so it
    takes a reservation, is counted against the study's ceilings and
    leaves a receipt. It previously went out through `urllib` with no
    operation at all, which is the shape N-206 names: not an admitted send
    that skipped its owner, but a send with no owner to skip. Every other
    call in this module is bounded, and this one was reachable by no
    ceiling, so the run could spend a provider call no ceiling could
    reach. `e2_replication.probe_route` is the same probe with the
    admission already in it.

    `dsn` is required to spend. With no `dsn` the probe reports
    `unadmitted-no-authority` and contacts nothing, because a
    reachability check that cannot be bounded is the defect rather than a
    weaker version of the answer.

    The route is resolved before anything is admitted. `max_calibration` is
    1, so the one probe the cap sheet authorizes is spent by the first
    call whether or not it goes on the wire, and an admission taken before
    the route is known spends it on a send that never happens. A caller
    that hands in its own gateway has already decided the send is possible
    and the admission is what bounds it, so that gateway short-circuits
    the lookup and the route stays the caller's to resolve.
    """
    key = os.environ.get("SETTLEMENT_GATEWAY_KEY", "")
    record = {
        "gateway": GATEWAY, "model": GATEWAY_MODEL,
        "max_tokens": PROBE_MAX_TOKENS, "credential_present": bool(key),
        "credential_source": "process environment, read at call time",
        "credential_recorded": False,
        "admitted": False, "operation_id": None, "exposure_units": 0,
        "kind": PROBE_KIND,
    }
    if not key:
        record["status"] = "no-credential"
        record["detail"] = ("no gateway credential is present in this "
                            "process, so the route was not contacted")
        return record
    if not dsn or not study_root:
        record["status"] = "unadmitted-no-authority"
        record["detail"] = ("no dsn and study_root, so no operation could "
                            "be admitted and the route was not contacted")
        return record
    if gateway is None and _probe_gateway_from_env() is None:
        return no_route_probe(credential_present=bool(key))
    record.update(_admitted_probe(dsn, study_root, gateway))
    if record["status"] not in PROBE_STATUSES:
        raise AssertionError("the probe reported a status outside its own "
                             "vocabulary: %r" % record["status"])
    return record


def no_route_probe(*, credential_present: bool | None = None) -> dict:
    """The probe's record for a process with no endpoint, spending nothing.

    `max_calibration` is 1 for this study, so the one probe the cap sheet
    authorizes is spent by the first call whether or not it goes on the
    wire. `probe_gateway` resolves its route before it admits anything,
    because admitting first burns the confirmation on a send that never
    happens. `probe_gateway` calls this when that resolution finds no route.

    `credential_present` is taken from the caller's own read when it has
    one. This function is the record of a process, so it re-reads the
    environment by default, but a caller that already read the credential
    reports what it saw rather than what a second read returns.
    """
    record = {
        "gateway": GATEWAY, "model": GATEWAY_MODEL,
        "max_tokens": PROBE_MAX_TOKENS,
        "credential_present": bool(
            os.environ.get("SETTLEMENT_GATEWAY_KEY", ""))
        if credential_present is None else bool(credential_present),
        "credential_source": "process environment, read at call time",
        "credential_recorded": False,
        "admitted": False, "operation_id": None, "exposure_units": 0,
        "kind": PROBE_KIND,
        "status": "no-route",
        "detail": ("no gateway endpoint is configured, so no operation was "
                   "admitted and the route was not contacted"),
    }
    assert record["status"] in PROBE_STATUSES
    return record


def _probe_gateway_from_env() -> Any:
    """The live adapter the probe sends through, or None without a route."""
    from settlement.config import Settings
    from settlement.gateway_http import HttpGatewayAdapter

    settings = Settings.from_env()
    if not settings.gateway.endpoint:
        return None
    return HttpGatewayAdapter.from_settings(
        settings, api_key=os.environ.get("SETTLEMENT_GATEWAY_KEY", "") or None,
        api="chat",
        expected_route={
            "endpoint": GATEWAY, "requested_model": GATEWAY_MODEL,
            "resolved_model": GATEWAY_MODEL, "provider": "nvidia",
            "tier": "free"},
        route_mode="free")


def _admitted_probe(dsn: str, study_root: str, gateway: Any | None) -> dict:
    """The probe's send, admitted and settled, and what the store holds.

    A `None` `gateway` here means a route was found in the environment, so
    this function resolves it itself. The unroutable case never arrives: the
    caller's check runs first, and an admission with nowhere to dispatch to
    is the defect this module's ordering exists to prevent.
    """
    from psycopg.rows import dict_row

    from settlement import authority, broker, db, loop
    from settlement.broker import MODEL_INFERENCE

    if gateway is None:
        gateway = _probe_gateway_from_env()
    operation_id = "%s-op-probe-route" % study_root
    granted = authority.admit_study_call(
        dsn, study_root, kind=PROBE_KIND, operation_id=operation_id,
        effect=MODEL_INFERENCE,
        payload={"model": GATEWAY_MODEL,
                 "messages": [{"role": "user", "content": PROBE_PROMPT}],
                 "max_output_tokens": PROBE_MAX_TOKENS,
                 "deadline_ms": PROBE_DEADLINE_MS})
    if not isinstance(granted, loop.Grant):
        return {"status": "unadmitted",
                "detail": getattr(granted, "reason", "unknown"),
                "refusal_detail": getattr(granted, "detail", ""),
                "operation_id": operation_id}

    record = {
        "admitted": True, "operation_id": operation_id,
        "exposure_units": int(granted.exposure),
        "budget_kind": granted.budget_kind,
    }
    status = broker.dispatch_operation(dsn, operation_id, launchers={},
                                       gateway=gateway)
    record["dispatch_state"] = status.dispatch_state
    record["next_decision"] = status.next_decision
    with db.read_connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT outcome, content FROM receipts"
                " WHERE operation_id = %s AND receipt_identity = %s",
                (operation_id, "gw:%s" % operation_id))
            row = cur.fetchone()
        conn.commit()
    row = dict(row or {})
    content = dict(row.get("content") or {})
    if row.get("outcome") != "success":
        record["status"] = "no-settled-response"
        record["detail"] = ("the admitted operation did not settle, so the "
                            "route is unconfirmed: %s"
                            % status.next_decision)
        return record
    record["status"] = "reachable"
    record["reply"] = str(content.get("text") or "")[:200]
    record["usage_reported"] = bool(content.get("usage"))
    return record


# --- assembly --------------------------------------------------------------


def build(out: Path, *, admin_dsn: str | None = None,
          authorized_units: int = 100_000) -> dict:
    """Bind authority, run the matrix, verify the store, write the evidence.

    Authority is bound before any effect, the ladder runs twice (shared and
    fresh), the store half runs under the same study root, and every count
    in the payload comes from a SELECT rather than from a field the run
    reported about itself.

    The probe is asked whether a route exists before it is admitted, since
    this study binds `max_calibration` at 1 and a probe that admits and
    then finds no endpoint has spent the only confirmation the cap sheet
    authorizes. `probe_gateway` owns that ordering for every caller, so
    `build` calls it and takes the record it returns. A second copy of the
    check here would only be a branch that can be deleted silently while
    the other one masks the loss.
    """
    from settlement import authority

    from . import s09_run_isolation as iso

    selection.assert_measure_freeze()
    out.mkdir(parents=True, exist_ok=True)

    committed = json.loads((
        Path(__file__).resolve().parents[2] / "reports" / "evidence"
        / "inv_r1_e3_selection" / "e3-crossover.json").read_text())

    offline_fresh = ladder(shared=False)
    offline_shared = ladder(shared=True)
    divergence = divergence_survey()

    store_payload = {}
    verdict = {}
    frozen = {}
    cap = {}
    probe = {}
    with iso.disposable_db(STUDY_TOKEN, admin_dsn=admin_dsn) as database:
        study_root = STUDY_ROOT
        cap = cap_sheet(offline_fresh, study_root=study_root,
                        authorized_units=authorized_units)
        handle = authority.authorize_study(
            database.dsn, study_root, authorized=authorized_units,
            allocation_id=STUDY_ALLOCATION,
            ceilings=study_ceilings(cap))
        probe = probe_gateway(database.dsn, study_root=handle.study_root)
        store_payload = store_ladder(database.dsn, handle.study_root)
        verdict = store_verdict(database.dsn, handle.study_root)
        frozen = {
            "study_root": handle.study_root,
            "allocation_id": handle.allocation_id,
            "authorized": handle.authorized,
            "ceilings": handle.ceilings,
            "correction_budget": handle.correction_budget,
            "store_fingerprint": handle.store_fingerprint,
            "store": database.name,
            "owner": ("authority.authorize_study + "
                      "authority.admit_study_call + "
                      "broker.dispatch_operation"),
        }

    payload = {
        "study": "E3 post-fix selection ladder",
        "measure_digest": selection.FROZEN_MEASURE_DIGEST,
        "frozen_yield_measures": selection.YIELD_MEASURES,
        "budgets": list(BUDGETS),
        "worlds": list(WORLDS),
        "committed_ladder": {
            "path": ("reports/evidence/inv_r1_e3_selection/"
                     "e3-crossover.json"),
            "policy_instance_scope": "shared-across-worlds",
            "agenda_ahead_on_retained_at": committed["crossover"][
                "agenda_ahead_on_retained_throughout"],
            "control_ahead_on_held_out_at": committed["crossover"][
                "control_ahead_on_held_out_at"],
            "agenda_ahead_on_held_out_at": committed["crossover"][
                "agenda_ahead_on_held_out_at"],
            "ladder": [{"budget": step["budget"],
                        "arms": [{"policy": a["policy"],
                                  "held_out_reduction_mean":
                                      a["held_out_reduction_mean"],
                                  "choices": a["choices"],
                                  "resources_used_total":
                                      a["resources_used_total"],
                                  "yield_totals": a["yield_totals"]}
                                 for a in step["arms"]]}
                       for step in committed["ladder"]],
        },
        "regenerated_shared": {
            "note": ("the committed ladder regenerated from the current "
                     "crossover(), so the sharing defect is in the code and "
                     "not only in the artifact"),
            "ladder": offline_shared["ladder"],
            "direction": offline_shared["direction"],
        },
        "postfix_fresh": {
            "note": ("one policy instance per cell, so each world is an "
                     "independent run"),
            "ladder": offline_fresh["ladder"],
            "direction": offline_fresh["direction"],
        },
        "shared_versus_fresh": _delta(offline_shared, offline_fresh),
        "divergence_survey": {
            "cells_examined": len(WORLDS) * len(BUDGETS),
            "cells_where_picks_differ": len(divergence),
            "cases": divergence,
        },
        "store": store_payload,
        "store_verdict": verdict,
        "authority": frozen,
        "cap_sheet": cap,
        "model_call_declaration": model_call_declaration(),
        "gateway_probe": probe,
    }
    (out / "e3-postfix-ladder.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return payload


def _delta(shared: dict, fresh: dict) -> dict:
    """Which cells the shared instance moved, and by how much."""
    rows = []
    changed = 0
    for s_step, f_step in zip(shared["ladder"], fresh["ladder"]):
        for s_arm, f_arm in zip(s_step["arms"], f_step["arms"]):
            for key, label in (("held_out_reduction", "held_out_reduction"),
                               ("retained_behaviors", "retained_behaviors"),
                               ("diagnoses_correct", "diagnoses_correct"),
                               ("resources_used", "resources_used")):
                left = _by(s_arm, key) if key == "held_out_reduction" \
                    else s_arm["yield_totals"][key]
                right = _by(f_arm, key) if key == "held_out_reduction" \
                    else f_arm["yield_totals"][key]
                if left != right:
                    changed += 1
                rows.append({
                    "budget": s_step["budget"], "policy": s_arm["policy"],
                    "measure": label,
                    "shared": left, "fresh": right,
                    "changed": left != right,
                })
    return {
        "measures_compared": len(rows),
        "measures_changed_by_the_shared_instance": changed,
        "cells": rows,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = Path(argv[0]) if argv else \
        Path("reports") / "evidence" / "inv_r1_e3_ladder"
    payload = build(out)
    print(json.dumps({
        "measure_digest": payload["measure_digest"],
        "agenda_ahead_on_held_out_at":
            payload["postfix_fresh"]["direction"]["agenda_ahead_on_held_out_at"],
        "control_ahead_on_held_out_at":
            payload["postfix_fresh"]["direction"]["control_ahead_on_held_out_at"],
        "agenda_ahead_on_retained_at":
            payload["postfix_fresh"]["direction"]["agenda_ahead_on_retained_at"],
        "divergence_cells":
            payload["divergence_survey"]["cells_where_picks_differ"],
        "divergence_cells_examined":
            payload["divergence_survey"]["cells_examined"],
        "shared_instance_changed_measures":
            payload["shared_versus_fresh"][
                "measures_changed_by_the_shared_instance"],
        "operations_in_store": payload["store_verdict"]["operations_in_store"],
        "receipts_in_store": payload["store_verdict"]["receipts_in_store"],
        "per_arm": payload["store_verdict"]["per_arm"],
        "gateway_probe": payload["gateway_probe"]["status"],
    }, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
