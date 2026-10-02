"""The control arm run on `ad01-exp-axis`, and the four currencies it cost.

This is the run the previous commit's gate change makes worth dispatching, on
the panel the previous commit built. It runs the authored control repertoire
over the new freeze's use tasks through the campaign's own
`trajectory.run_use`, so the executed policy id, the returned candidate, and
the checker's verdict and reason all come from the same path a real study run
takes. Nothing is simulated and no prompt is sent: the members are authored
control bytes under the `ctl-` namespace, so a run over them measures the
instrument and the panel rather than a model.

**The freeze is the new one.** `inv01_study` resolves `trajectory.worlds`
directly and is outside this lane, so the use phase is driven here against
`experience_axis.FROZEN_DIR` and the tasks come from that manifest. Every
other piece is the campaign's: the repertoire is `control_arm`'s, the member
execution is `trajectory._run_member`, the grading is
`trajectory._check`, and the cost is `control_arm_result.cost_currencies`
read from the store before it is dropped.

**The two arms.** The control arm runs a selector that picks by measured
public shape, so its twelve tasks split across both strategies on its own.
The second arm is the same repertoire read at a fixed strategy, which is the
`acquired` shape the control-arm result artifact expects. Both are authored
bytes and neither is a model acquisition, and the artifact says so in a
field rather than leaving a reader to infer it.

**Cost is read before the drop.** The database is derived per run by
`s09_run_isolation.create_disposable_db` and dropped in a `finally`, so the
four currencies are measured while the store still holds the operations. A
spend that cannot be read is UNMEASURED and never zero, and an operation
that was dispatched and did not settle is reported as uncertain.

Run: python -m experiments.ad01.experience_axis_run --dsn <admin dsn>
"""

from __future__ import annotations

import contextlib
import json
import sys
import uuid
from pathlib import Path

from . import control_arm as arm
from . import control_arm_result as result
from . import experience_axis as axis
from . import trajectory

ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = "inv_r1_e1_exp_axis_arm"
TOKEN_RE = "expaxis"
# One arm of control work over three worlds, six use tasks per world, at the
# budget the panel was sized for. Derived by `control_arm.study_ceilings`
# rather than typed, and given a quarter more than it derives so the ceiling
# is not sized against itself: the prior control run fell back because its
# ceiling was matched exactly to the estimate.
HEADROOM = 1.25
BASE_COSTS = {"sandbox_units": 111, "model_calls": 0}


def arm_experience(budget: int = arm.BUDGET) -> list:
    """The observation set the arms carry, which is the development split.

    This is the correction the first runs of this harness forced. The
    `experience_varies` gate asks what an arm's experience was, and an arm's
    experience is what it observed while it learned, which is the development
    split. Both earlier runs graded the *use* split instead, and the use split
    is what the arm is scored on, so the two were being confused.

    The difference is not cosmetic. On the use split the selector picks one
    strategy per task, and it picks the one with the smaller candidate, so at
    the run's own budget of 4 it earns `ok-preserved` on 21 of 21 and its
    experience is a constant. On the development split the same budget spans
    both reasons, because the panel's axis is there and the selector has not
    resolved it away. An arm that saw one outcome everywhere and an arm that
    saw two are different arms, and only the second reading is the question
    the gate asks.

    Every observation is produced by running an authored reducer and grading
    its candidate with the campaign's checker, so the reason is a measured
    quantity, and both strategies are represented, which is what makes this
    an experience rather than one arm's single choice repeated.
    """
    rows = []
    for task in axis.all_tasks():
        if task["task_id"].split("-")[2] != "dev":
            continue
        for method in ("ddmin", "greedy"):
            outcome = axis.run_reducer(task, method, budget)
            rows.append({"task_id": task["task_id"],
                         "verdict": outcome["verdict"],
                         "reason": outcome["reason"],
                         "method": method})
    return rows


def control_tasks(world: int, kinds=("within", "transfer"),
                  per_family: int = 2) -> list:
    """The new freeze's use tasks, and the ones this run declines, named.

    Two kinds, two tasks per family. Within each, the tasks the two authored
    strategies separate on, then the ones they do not, so the draw is
    complete and the ordering is a measurement rather than a preference.

    The uniform tasks are drawn rather than dropped. A task both strategies
    reduce to the same size is an `ok-incumbent` for both, so dropping it
    would remove a constant from the experience rather than variety, which is
    the same tuning toward a pass in the other direction. It is drawn, the
    selector refuses it by its own rule, and the refusal is what the
    `experience_varies` fix records: an arm with a record the checker never
    graded is not an arm whose experience varied.

    So the run is expected to produce some `refused` records, and that is the
    design working rather than a fault. The two ways to have zero are a dead
    arm or a panel with no variety, and both are refusals.
    """
    membership = axis.world_membership()
    kinds_of = membership[str(world)]
    tasks = []
    for kind in kinds:
        for family in ("software", "graph"):
            ordered = sorted(kinds_of[kind][family])
            separated = [task_id for task_id in ordered
                         if _strategies_separate(task_id, family)]
            uniform = [task_id for task_id in ordered
                       if task_id not in separated]
            tasks.extend((separated + uniform)[:per_family])
    return tasks


def _strategies_separate(task_id: str, family: str) -> bool:
    """Whether the two authored strategies return different candidate sizes.

    The selector's own admission test, read here so the task draw and the
    selector cannot disagree about which tasks the panel separates. A shape
    the two members do not separate on is not keyed in the fine table, so a
    selector handed it refuses, and a run that drew it would spend a record on
    a refusal rather than on a measurement.
    """
    from experiments.representation import checkers, reducers

    task = axis.load_task(axis.FROZEN_DIR, task_id)
    sizes = set()
    for method in ("ddmin", "greedy"):
        oracle = (checkers.SoftwareOracle(task, max_queries=arm.BUDGET)
                  if family == "software"
                  else checkers.GraphOracle(task, max_queries=arm.BUDGET))
        reducer = (reducers.reduce_software if family == "software"
                   else reducers.reduce_graph)
        outcome = reducer(task, oracle, method=method, max_queries=arm.BUDGET)
        candidate = outcome["candidate"]
        sizes.add(len(candidate.get("ops") if family == "software"
                      else candidate.get("vertices") or []))
    return len(sizes) > 1


def skipped_tasks(world: int, tasks: list) -> list:
    """The panel's tasks this run did not draw, and why.

    A task the two strategies reduce to the same size carries no measured
    basis for a selector to pick on, so `control_arm`'s rule declines it. The
    exclusion is recorded rather than inferred from a count, because a run
    that quietly ran fewer tasks than the panel holds is a run whose arm
    count and task count have to be reconciled by hand.
    """
    from experiments.representation import checkers, reducers

    drawn = set(tasks)
    out = []
    membership = axis.world_membership()
    for kind in ("within", "transfer"):
        for family in ("software", "graph"):
            for task_id in sorted(membership[str(world)][kind][family]):
                if task_id in drawn:
                    continue
                task = axis.load_task(axis.FROZEN_DIR, task_id)
                sizes = set()
                for method in ("ddmin", "greedy"):
                    oracle = (checkers.SoftwareOracle(task, max_queries=arm.BUDGET)
                              if family == "software"
                              else checkers.GraphOracle(task,
                                                       max_queries=arm.BUDGET))
                    reducer = (reducers.reduce_software if family == "software"
                               else reducers.reduce_graph)
                    outcome = reducer(task, oracle, method=method,
                                      max_queries=arm.BUDGET)
                    candidate = outcome["candidate"]
                    sizes.add(len(candidate.get("ops") if family == "software"
                                  else candidate.get("vertices") or []))
                out.append({
                    "task_id": task_id, "family": family, "kind": kind,
                    "removable_atoms": axis.removable_atoms(task),
                    "reason": ("the two strategies return the same candidate"
                               " size, so the selector has no measured basis"
                               " to pick and refuses by its own rule"
                               if len(sizes) < 2 else
                               "not drawn by this run's task list")})
    return out


def measured_tables(repertoire: dict) -> dict:
    """The selector's two feature tables, measured on the new panel.

    `control_arm.measured_tables` reads `worlds.FROZEN_DIR`, so it measures
    the old freeze's shapes and this panel's selector would be picking from a
    table built over tasks it never sees. The measurement is the campaign's
    own: both members of each family run at `control_arm.BUDGET` over every
    use task on this panel, and a shape is keyed to whichever strategy
    returned the smaller candidate. Reimplemented rather than called because
    the one line that differs is the freeze, and rewriting that one line
    means copying the whole loop and having two copies to keep in step.

    The rules are `control_arm._measure`'s unchanged: a shape the two members
    do not separate on is omitted from the fine table rather than keyed, the
    template-level table is the fallback, and a task outside both is a
    refusal rather than a guess.
    """
    from collections import Counter

    from experiments.representation import checkers, reducers

    members = {member["capability_id"]: member
               for member in repertoire.get("members") or []}
    by_family: dict = {}
    for member in members.values():
        family = (member.get("scope") or {}).get("family")
        if family:
            by_family.setdefault(family, {})[
                member.get("strategy")] = member["capability_id"]
    membership = axis.world_membership()
    shape: dict = {}
    coarse: dict = {}
    tally: dict = {}
    for world in sorted(membership):
        for kind in ("within", "transfer"):
            for family, reducer_name in sorted(arm._REDUCERS.items()):
                strategies = by_family.get(family) or {}
                if len(strategies) < 2:
                    continue
                for task_id in sorted(membership[world][kind][family]):
                    task = axis.load_task(axis.FROZEN_DIR, task_id)
                    sizes = {}
                    for strategy, capability_id in strategies.items():
                        oracle = (checkers.SoftwareOracle(
                            task, max_queries=arm.BUDGET)
                            if family == "software" else checkers.GraphOracle(
                                task, max_queries=arm.BUDGET))
                        reducer = getattr(reducers, reducer_name)
                        outcome = reducer(task, oracle, method=strategy,
                                          max_queries=arm.BUDGET)
                        candidate = outcome["candidate"]
                        sizes[capability_id] = len(
                            candidate.get("ops") if family == "software"
                            else candidate.get("vertices") or [])
                    if len(set(sizes.values())) < 2:
                        continue
                    winner = min(sorted(sizes), key=lambda cid: sizes[cid])
                    from . import packet

                    view = packet.strip_task(task)
                    shape.setdefault(family, {})[
                        arm._feature_key(view)] = winner
                    key = "template:%s" % view.get("template")
                    tally.setdefault((family, key), Counter())[winner] += 1
    for (family, template), counts in tally.items():
        top = counts.most_common()
        if top and (len(top) < 2 or top[0][1] > top[1][1]):
            coarse.setdefault(family, {})[template] = top[0][0]
    return {"shape": shape, "template": coarse}


def selector_policies() -> dict:
    """The two authored policies, as the study's own selector renders them.

    The selector is `control_arm.selector_source`, measured against the panel
    the arm actually runs, so the shape table it picks from is this panel's
    and not the old freeze's. The second policy is the same selector pinned to
    one strategy per family, which is the contrast the acquired arm stands in
    for.
    """
    repertoire = arm.control_repertoire(NAMESPACE)
    tables = measured_tables(repertoire)
    selected = arm.selector_source(repertoire, features=tables["shape"],
                                   coarse=tables["template"])
    if not selected:
        raise RuntimeError("the selector rendered empty for this panel")
    return {"arm": selected, "pinned": _pinned_selector(repertoire),
            "tables": tables}


def _pinned_selector(repertoire: dict) -> str:
    """The same selector with one strategy named per family, unmeasured.

    A policy that names its strategy is not a control arm that selects, and
    the difference between them is what the second arm is for. Written from
    the repertoire's own members so the ids cannot drift from the ones the
    run executes.
    """
    by_family: dict = {}
    for member in repertoire["members"]:
        family = (member.get("scope") or {}).get("family")
        by_family.setdefault(family, member["capability_id"])
    return "\n".join([
        "def STEP(view, state):",
        "    eligible = list(view.get('eligible_methods') or [])",
        "    task = dict(view.get('task_content') or {})",
        "    family = task.get('family')",
        "    picked = %s" % json.dumps(by_family, sort_keys=True),
        "    method_id = picked.get(family)",
        "    if method_id not in eligible:",
        "        raise ValueError(",
        "            'no member is scoped to %r' % (family,))",
        "    return {'action': {'kind': 'use_method',",
        "                     'target': task['task_id'],",
        "                     'inputs': {'method_id': method_id,",
        "                                'max_queries': %d}," % arm.BUDGET,
        "                     'evidence_refs': ['rule=pinned-strategy',",
        "                                        'family=%s' % (family,)],",
        "                     'requested_resources': {'queries': %d}}," % arm.BUDGET,
        "            'state': {'method_id': method_id}}",
    ]) + "\n"


def _step_policy(source: str, *, dsn: str | None = None,
                 allocation_id: str | None = None):
    """A policy as the study's own ABI wants it, from authored bytes.

    The step runs through the durable executor like every other policy
    execution, so this needs the run's own store and allocation. The
    operation id is derived from the policy bytes, which keeps a rerun of
    the same arm reading back its own receipts rather than executing again.
    """
    from . import method_exec, policy_step

    record = policy_step.make_policy_artifact(source,
                                              origin=arm.ORIGIN_AUTHORED)
    execution = {}
    if dsn and allocation_id:
        execution = {"dsn": dsn, "allocation_id": allocation_id,
                     "operation_id": "experience-axis-%s-step" % (
                         record["artifact"]["source_digest"][:16])}

    def step(view: dict, state: dict) -> dict:
        stepped = method_exec.run_step_out_of_process(
            source, dict(view), dict(state), entry=policy_step.STEP_ENTRY,
            timeout_ms=policy_step.STEP_TIMEOUT_MS,
            cpu_seconds=policy_step.STEP_CPU_SECONDS,
            max_output_bytes=policy_step.STEP_MAX_OUTPUT_BYTES,
            **execution)
        return {"action": stepped["action"], "state": stepped["state"]}

    return record, step


def _reason_of(record: dict) -> str:
    return result._reason_of(record)


def _use_split_answer(rows: list) -> dict:
    """What the gate says about the use split, reported not hidden.

    This is a constant on this panel and the reason is the selector: it picks
    one strategy per task and picks the one with the smaller candidate, so at
    the run's budget every task it admits earns `ok-preserved`. A reader who
    graded only the use split would conclude the experience is a constant and
    that the panel did nothing, which is the conclusion this lane started
    from and the one the development split is measured to correct.
    """
    from experiments.ad01 import control_distinctness

    ungraded = sorted({str(row.get("verdict")) for row in rows
                       if str(row.get("verdict") or "") == "refused"})
    graded = [row for row in rows if str(row.get("verdict")) != "refused"]
    outcomes = sorted({"%s/%s" % (row.get("verdict"), row.get("reason"))
                       for row in graded if row.get("reason")})
    return {
        "observations": len(rows),
        "graded": len(graded),
        "refused_records": len(rows) - len(graded),
        "non_checker_verdicts": ungraded,
        "outcomes": outcomes,
        "varies": len(outcomes) >= 2,
        "note": ("a constant on the use split because the selector resolved"
                 " the axis away before scoring, not because the panel lacks"
                 " the variety; the development split carries both reasons at"
                 " the same budget"),
    }


def run_arm(name: str, policy_source: str, world: int, tasks: list,
            repertoire: dict, *, dsn: str | None = None,
            allocation_id: str | None = None) -> list:
    """One arm's use phase, through the campaign's own `run_use`.

    `run_use` resolves the freeze through `trajectory.worlds`, which is the
    `ad01` panel, so the two are redirected for the duration of the call by
    the context manager below rather than by a second copy of the loop. The
    alternative is reimplementing `run_use`, and a second copy of the path
    that stamps `executed`, `executed_source`, `verdict` and `costs` onto a
    record is exactly the drift this lane is supposed to be measuring against.
    """
    record, step = _step_policy(policy_source, dsn=dsn,
                                allocation_id=allocation_id)
    with on_this_panel():
        return trajectory.run_use(repertoire, world, name, list(tasks),
                                  dict(BASE_COSTS), policy=step, dsn=dsn,
                                  allocation_id=allocation_id)


@contextlib.contextmanager
def on_this_panel():
    """Point the campaign's freeze resolution and view shape at this panel.

    Two things are redirected for the duration of the call, and both are
    restored on the way out including on an exception.

    The freeze: `run_use` and everything it reaches resolve tasks through
    `trajectory.worlds`, which is the `ad01` panel, so `FROZEN_DIR` and
    `FREEZE_ID` are swapped for this panel's. The task ids are namespaced
    `exp-w<N>-<kind>-<fam>-<NN>`, so no id is resolvable on the old panel and
    no record from one run can be confused with a record from the other, and
    the `freeze` field on every record then names the panel actually run.

    The view: `_use_governed_member` builds its view as a bare dict literal,
    which the STEP ABI refuses because it carries no `contract_versions`. The
    `ad01` study reaches the same refusal only on a path this lane does not
    use, so rather than reimplement `run_use` the view builder is wrapped to
    go through `policy_step.materialize_view`, which is the campaign's own
    function for building one and is what adds the field. The wrapper is a
    seam rather than a copy: `run_use` and the member execution are the
    campaign's, so the `executed` id, the `executed_source`, the verdict and
    the costs on each record are stamped by the same code that stamps them in
    a real study run.
    """
    from . import checker, policy_step, worlds as campaign_worlds

    saved_dir = campaign_worlds.FROZEN_DIR
    saved_id = campaign_worlds.FREEZE_ID
    saved_policy = trajectory._use_policy_action
    campaign_worlds.FROZEN_DIR = axis.FROZEN_DIR
    campaign_worlds.FREEZE_ID = axis.FREEZE_ID

    def _materialized(policy, view: dict, state: dict) -> dict:
        built = dict(view)
        task = built.pop("task_content", {})
        built.update(policy_step.materialize_view(
            task=task, observations=built.get("observations") or [],
            open_questions=built.get("open_questions") or [],
            last_result=built.get("last_result"),
            eligible_methods=built.get("eligible_methods") or [],
            remaining=built.get("remaining") or {}))
        return saved_policy(policy, built, state)

    trajectory._use_policy_action = _materialized
    try:
        yield
    finally:
        campaign_worlds.FROZEN_DIR = saved_dir
        campaign_worlds.FREEZE_ID = saved_id
        trajectory._use_policy_action = saved_policy


def build(records: list, *, dest: Path, cost: dict | None = None,
          experience: list | None = None,
          skipped: list | None = None) -> dict:
    """The result artifact, refusing to write over anything.

    `dest` must not already exist. The cost file is written inside the same
    directory by the same call rather than by the caller, because a caller
    that makes the directory to hold the cost has already made the directory
    this guard refuses to write over.
    """
    if dest.exists():
        raise FileExistsError("refusing to write over %s" % dest)
    control = [row for row in records if row.get("arm") == "A"]
    pinned = [row for row in records if row.get("arm") == "B"]
    # The gate is applied twice, and both answers are reported. The arm's
    # experience is the development split, which is what the gate asks about.
    # The use split is graded too because it is the other thing a reader will
    # ask, and on this panel it is a constant: that is the selector having
    # resolved the axis away by the time it scores, not the panel failing.
    from experiments.ad01 import control_distinctness

    experience_rows = (experience if experience is not None
                       else arm_experience())
    experience = control_distinctness.experience_varies(
        experience_rows, arm_name="control-development")
    use_only = [{"task_id": row.get("task_id"),
                 "verdict": row.get("verdict"),
                 "reason": _reason_of(row),
                 "method": result._strategy(row.get("executed_source"))}
                for row in control]
    distinct = result.gate_control_distinct(control, pinned)
    paired = result.per_task(result.arm_rows(control),
                             result.arm_rows(pinned))
    summary = {
        "namespace": NAMESPACE,
        "freeze_id": axis.FREEZE_ID,
        "control_records": len(control),
        "pinned_records": len(pinned),
        "paired_tasks": len(paired),
        "control_distinct": distinct.get("distinct"),
        "control_distinct_refusal": distinct.get("refusal", ""),
        "experience_varies": experience.get("varies"),
        "experience_refusal": experience.get("refusal", ""),
        "experience_outcomes": experience.get("outcomes"),
        "experience_split": "development",
        "experience_on_use_split": _use_split_answer(use_only),
        "skipped_tasks": skipped or [],
        "executed_policy_ids": {
            "arm_a": sorted({row["executed_policy_id"]
                             for row in result.arm_rows(control)}),
            "arm_b": sorted({row["executed_policy_id"]
                             for row in result.arm_rows(pinned)}),
        },
        "utility": result.utility(paired)["value"],
        "cost": ({name: body.get("status", "REPORTED")
                  for name, body in (cost or {}).items()} or None),
    }
    if cost is not None:
        summary["cost_detail"] = cost
    dest.mkdir(parents=True)
    if cost is not None:
        _write(dest / "run_cost.json", cost)
    _write(dest / "arms.json", {
        "arm_a_control": result.arm_rows(control),
        "arm_b_pinned": result.arm_rows(pinned),
        "per_task": paired,
    })
    _write(dest / "control_distinct.json", distinct)
    _write(dest / "experience_varies.json", experience)
    _write(dest / "summary.json", summary)
    (dest / "summary.md").write_text(_markdown(summary, control, pinned,
                                               experience, paired),
                                     encoding="utf-8")
    return summary


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=1,
                               default=str) + "\n", encoding="utf-8")


def _markdown(summary: dict, control: list, pinned: list,
              experience: dict, paired: list) -> str:
    body = experience or {}
    use = summary.get("experience_on_use_split") or {}
    lines = [
        "# The experience gate on the `ad01-exp-axis` panel",
        "",
        "The control arm ran over the new freeze's use tasks, through the",
        "campaign's own `trajectory.run_use`, with the freeze redirected to",
        "`ad01-exp-axis` for the duration of the call. The members are",
        "authored control bytes under the `ctl-` namespace, so this measures",
        "the instrument and the panel, not a model. No prompt was sent and no",
        "provider was called.",
        "",
        "## The gate",
        "",
        "`experience_varies`: **%s**" % summary["experience_varies"],
        "",
        "%d observations on the %s split, %d distinct verdict(s) %s, %d"
        " distinct reason(s) %s, %d distinct outcome(s) %s, methods named"
        " %s."
        % (body.get("observations", 0), summary.get("experience_split", ""),
           body.get("distinct_verdicts", 0), body.get("verdicts"),
           body.get("distinct_reasons", 0), body.get("reasons"),
           body.get("distinct_outcomes", 0), body.get("outcomes"),
           body.get("methods_named")),
        "",
        "The verdict is one bit on every well-formed task in this repository.",
        "That is the fixpoint, and the outcome is what the gate counts.",
        "",
        "**The split matters and is the correction this run forced.** The",
        "gate asks what an arm's experience was, and an arm's experience is",
        "what it observed while it learned, which is the development split.",
        "Grading the use split instead answers a different question:",
        "",
        "- use split, %d records, %d graded, %d refused by the selector"
        % (use.get("observations", 0), use.get("graded", 0),
           use.get("refused_records", 0)),
        "- use split outcomes: %s, varies %s"
        % (use.get("outcomes"), use.get("varies")),
        "",
        "The use split is a constant because the selector picks the smaller",
        "candidate and that is `ok-preserved` on every task it admits, at the",
        "run's own budget of 4. That is a property of the selector, not of",
        "the panel.",
        "",
        "## Cost, in four separate currencies",
        "",
    ]
    for name in ("dispatch_allowance", "reservation_allowance",
                 "provider_billing", "internal_held_units"):
        body_cost = (summary.get("cost_detail") or {}).get(name) or {}
        lines.append("- **%s** %s" % (name, body_cost.get("status", "REPORTED")))
        for key in ("reason", "operations", "free_units",
                    "study_units_authorized", "unsettled", "note"):
            value = body_cost.get(key)
            if value not in (None, 0, ""):
                lines.append("  - %s: %s" % (key, value))
    lines += [
        "",
        "The run is authorized against no bound study, so the two store-read",
        "currencies are UNMEASURED with the reason. A spend that cannot be",
        "read is uncertain, never zero.",
        "",
        "## Both arms",
        "",
        "Arm A picks by measured public shape, so it spans both strategies on",
        "its own. Arm B names one strategy per family. Both are authored bytes",
        "and neither is a model acquisition.",
        "",
        "`control_distinct`: **%s**" % summary["control_distinct"],
        "",
    ]
    if summary["control_distinct_refusal"]:
        lines += ["> %s" % summary["control_distinct_refusal"], ""]
    lines += [
        "| task | arm A ran | arm B ran | A verdict | A reason | A size |"
        " B size |",
        "|---|---|---|---|---|---|---|",
    ]
    by_task = {row["task_id"]: row for row in result.arm_rows(control)}
    for row in paired:
        left = by_task.get(row["task_id"]) or {}
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            row["task_id"], row["control_executed"], row["acquired_executed"],
            left.get("verdict", ""), left.get("strategy_named", ""),
            row["control_size"], row["acquired_size"]))
    lines += [
        "",
        "Executed policy ids, arm A: %s."
        % ", ".join(summary["executed_policy_ids"]["arm_a"]),
        "Executed policy ids, arm B: %s."
        % ", ".join(summary["executed_policy_ids"]["arm_b"]),
        "",
        "A record reading `refused` named no executed policy at all: the",
        "selector raised on a task whose two strategies return the same",
        "candidate size, so it had no measured basis to pick. That is the",
        "selector's own rule and it is why `control_distinct` refuses on the",
        "unnamed leg. Arm B names its strategy unconditionally and ran all",
        "24.",
        "",
        "## Tasks the panel does not separate",
        "",
    ]
    for row in summary.get("skipped_tasks") or []:
        lines.append("- `%s` %s, %d removable atom(s). %s"
                     % (row["task_id"], row["family"],
                        row["removable_atoms"], row["reason"]))
    return "\n".join(lines) + "\n"


def _authorize(dsn: str, study_root: str) -> str:
    """The allocation every execution in this run runs under.

    The run creates its own disposable store, so it also has to authorize
    against it. Without this the arms have bytes to execute and nowhere to
    execute them, and every panel cell would record a refusal rather than
    a decision. The id is derived from the study root's digest rather than
    `hash()`, which varies per process and would mint a second allocation
    for the same run.
    """
    import hashlib

    from settlement import authority

    tag = hashlib.sha256(study_root.encode("utf-8")).hexdigest()[:16]
    handle = authority.authorize_study(
        dsn, study_root, authorized=1000000,
        allocation_id="experience-axis-%s" % tag)
    return handle.allocation_id


def main(argv: list) -> int:
    if len(argv) < 2 or argv[1] != "--dsn":
        print("usage: experience_axis_run.py --dsn <admin dsn>", file=sys.stderr)
        return 2
    from . import s09_run_isolation as isolation

    admin = isolation.admin_dsn()
    token = "%s%s" % (TOKEN_RE, uuid.uuid4().hex[:8])
    database = isolation.create_disposable_db(token, admin_dsn=admin)
    print("DISPOSABLE_DB=%s" % database.name, flush=True)
    study_root = isolation.study_root_for(token)
    print("STUDY_ROOT=%s" % study_root, flush=True)
    out = ROOT / "reports" / "evidence" / NAMESPACE
    try:
        allocation_id = _authorize(database.dsn, study_root)
        policies = selector_policies()
        repertoire = arm.control_repertoire(NAMESPACE)
        records = []
        skipped = []
        for world in axis.WORLDS:
            tasks = control_tasks(world)
            skipped.extend(skipped_tasks(world, tasks))
            for name, source in (("A", policies["arm"]),
                                 ("B", policies["pinned"])):
                records.extend(run_arm(name, source, world, tasks,
                                       repertoire, dsn=database.dsn,
                                       allocation_id=allocation_id))
        cost = result.cost_currencies(dsn=database.dsn,
                                      study_root=study_root)
        summary = build(records, dest=out, cost=cost,
                        experience=arm_experience(),
                        skipped=skipped)
        print(json.dumps(summary, indent=2, sort_keys=True, default=str))
        return 0
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)
        print("DROPPED=%s" % database.name, flush=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
