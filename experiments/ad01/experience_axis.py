"""Why the verdict is a fixpoint, and what varies instead.

`experience_varies` refuses on 18 observations and one distinct verdict. The
brief for that gate was to build a panel the authored reducers can fail, and
this module is the measurement that says they cannot be failed, on any panel,
in any namespace, at any budget.

**The fixpoint.** A reducer's oracle and the campaign's grader are the same
function. `SoftwareOracle.check` returns `check_software(self.task, candidate)`
and `trajectory._check` returns `checkers.check_software(task, candidate)`, so
the verdict a trial is accepted on is the verdict the output is graded on. Both
authored reducers then hold one invariant over their whole walk:

    `ddmin_reduce` and `greedy_reduce` assign `keep` only from the set of
    indices the oracle graded `preserved`, and return `build(keep)`.

`build` is monotone and `build(all_indices)` is the task itself, so the
returned candidate is one of exactly two things.

    the whole task, on the `initial-not-preserved` branch, where the reducer
    returns before it has changed anything. The grader reads
    `candidate["ops"] == task["ops"]` and reports `ok-incumbent` when the
    witness holds — which is the definition of a well-formed task.

    a `keep` the oracle already graded `preserved`, on every other branch.

Both are `preserved`. `not_preserved` and `invalid` are reachable only through
a task that does not parse, whose witness does not hold, or whose candidate is
not a legal deletion, and a walk that only ever deletes atoms cannot produce
any of those from a well-formed task.

**The panel is not too easy, and making it harder cannot help.** Two
independent arms of evidence, both in this module and both rerunnable:

    `frozen_census`   the committed `ad01` freeze, 54 tasks, six budgets, two
                      strategies. Every triple grades `preserved`.

    `adversarial_search`  thousands of well-formed tasks generated from a
                      different distribution than the freeze's, swept over
                      eight budgets and two strategies. Every triple grades
                      `preserved`.

A task that is *too hard* does not escape either. `initial-not-preserved`
returns the incumbent byte for byte, and the incumbent of a well-formed task
is `preserved` by the well-formedness condition itself, with reason
`ok-incumbent`. Difficulty and triviality are the same answer.

**What varies is the reason, and it varies for a reason worth naming.**
`ok-incumbent` is the arm returning the task unchanged and `ok-preserved` is
the arm returning a strict reduction. The verdict collapses those two into
one bit and the reason does not. The axis that moves it is how many atoms a
single deletion can remove: at zero removable atoms the reducer is stuck at
any budget, and at one or more it has somewhere to go. `slack_panel` is a
panel built on that axis, and `axis_census` is its measurement.

So the panel this repository needed was not a harder one. It was one that
spans zero and non-zero slack, which is what `slack_panel` is and what the
new freeze under `worlds_exp` holds.

`experience_varies` therefore counts the outcome rather than the verdict
alone. The gate change and its mutation battery are in
`control_distinctness.experience_varies` and in
`tests/test_ad01_experience_axis.py`; this module is the evidence behind it
and the place to re-run it.

Run: python -m experiments.ad01.experience_axis
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

from experiments.representation import checkers, graphs, reducers, software

ROOT = Path(__file__).resolve().parents[2]

FREEZE_ID = "ad01-exp-axis"
VERSION = "AD01-EXP-AXIS/1"
FROZEN_DIR = Path(__file__).resolve().parent / "worlds_exp"
TASK_PREFIX = "exp"
WORLDS = (0, 1, 2)
KINDS = ("dev", "within", "transfer")
SW_BASE = {"dev": 7101, "use": 7301}
GR_BASE = {"dev": 7201, "use": 7401}
SW_TRANSFER_TEMPLATES = frozenset({"stale-read-3chain", "stale-clear-del-core"})
GR_TRANSFER_TEMPLATES = frozenset({"C9+tree", "C5+shared-edge",
                                   "C5+joined-by-path"})
GR_DEV_TEMPLATES = frozenset({"C5+tree", "C7+tree", "C5+shared-vertex"})

# The budgets this panel is measured at. `1` is the budget at which every
# task in every panel is `ok-incumbent`, so it is the budget at which the
# experience is a constant whichever panel is used. `4` is the budget the
# control arm pins, and the one this panel was sized for. Both are named here
# rather than passed in, because a budget chosen per call is a budget chosen
# after seeing the answer.
CENSUS_BUDGETS = (1, 2, 4, 8, 16)
ARM_BUDGET = 4

# The slack the generator builds each task at. Index zero carries no slack and
# no removable atom, which is the end of the axis that makes the reason move.
# The transfer rows carry one more than their within counterparts so a reader
# can see the axis continue past the development range rather than stop at it.
SLACK_BY_KIND = {"dev": (0, 1, 2), "within": (0, 1, 3), "transfer": (1, 2, 4)}


def _rng(*parts) -> random.Random:
    key = "-".join(str(part) for part in parts)
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def _seed_for(family: str, world: int, kind: str, index: int) -> int:
    base = SW_BASE if family == "software" else GR_BASE
    return base["dev" if kind == "dev" else "use"] + world * 100 + index


def _content_key(task: dict):
    if task["family"] == "software":
        return ("software", task["fault"],
                tuple((entry["op"], entry.get("key"), entry.get("value"))
                      for entry in task["ops"]),
                json.dumps(task["witness"]["ref"], sort_keys=True),
                json.dumps(task["witness"]["faulty"], sort_keys=True))
    return ("graph", tuple(task["vertices"]),
            tuple(tuple(edge) for edge in task["edges"]))


# ---------------------------------------------------------------------------
# the panel
# ---------------------------------------------------------------------------


def generate_software(world: int, kind: str, index: int) -> dict:
    """A well-formed software task carrying a measured number of slack atoms.

    The dev core is three ops and nothing can protect it: deleting either
    `set` collapses the witness disagreement and deleting the `get` removes
    the observation, so a dev row at zero slack has zero removable atoms. Each
    slack op is a `set` on another key written after the witness `get`, and
    each is removable on its own because nothing after it reads that key.

    The transfer core is not equally protected and the task does not pretend
    it is. A three-`set` stale-read chain has one removable atom at its
    head, because dropping the first `set` leaves a two-`set` chain with the
    same disagreement, so `slack` on a transfer row counts only the padding
    this function added and the removable count is one higher. That is
    recorded rather than hidden: `removable_atoms` measures the truth from
    the checker and the census reports the measured value, and the axis the
    panel is built to span is the measured one.

    The content of a use row is kept off every dev row's content by the same
    re-salting the graph arm uses. Two dev and within rows draw the same
    slack and can otherwise land on the same ops, which `audit` catches.
    """
    slack = SLACK_BY_KIND[kind][index % 3]
    seed = _seed_for("software", world, kind, index)
    if kind == "dev":
        return _software_at(world, kind, index, seed, slack, 0)
    avoid = _all_dev_keys("software")
    for salt in range(64):
        task = _software_at(world, kind, index, seed, slack, salt)
        if _content_key(task) in avoid:
            continue
        return task
    raise AssertionError("no valid software task for %d/%s/%d"
                         % (world, kind, index))


def _all_dev_keys(family: str) -> set:
    """The content of every development task on this panel, in every world.

    Wider than the `ad01` freeze's rule, which compares within a world. The
    three worlds are independent units here, so a use task on one that
    reproduces a dev task's content on another is the same leakage by a
    longer route, and the wider rule costs nothing: the dev set is nine
    tasks and the salt range is 64.
    """
    if family == "software":
        return {_content_key(generate_software(other, "dev", index))
                for other in WORLDS for index in range(3)}
    return {_content_key(generate_graph(other, "dev", index))
            for other in WORLDS for index in range(3)}


def _software_at(world: int, kind: str, index: int, seed: int, slack: int,
                 salt: int) -> dict:
    rng = _rng("exp-axis-software", seed, world, kind, index, salt)
    keys = list(software.KEYS)
    rng.shuffle(keys)
    hero, others = keys[0], keys[1:]
    fault = software.FAULTS[index % 2]
    values = ["v%d" % rng.randint(1, 4) for _ in range(2)]
    while values[1] == values[0]:
        values[1] = "v%d" % rng.randint(1, 4)
    ops = [{"op": "set", "key": hero, "value": values[0]}]
    if fault == "stale-read":
        ops.append({"op": "set", "key": hero, "value": values[1]})
        if kind == "transfer":
            ops.append({"op": "set", "key": hero, "value": "v%d" % (
                1 + (int(values[1][1:]) % 3))})
    else:
        if kind == "transfer":
            ops.append({"op": "del", "key": others[0]})
        ops.append({"op": "clear"})
    witness_id = "o0"
    ops.append({"op": "get", "key": hero, "id": witness_id})
    template = ("stale-read-3chain" if kind == "transfer" and
                fault == "stale-read" else
                "stale-clear-del-core" if kind == "transfer" else
                "stale-read-2chain" if fault == "stale-read" else
                "stale-clear-core")
    for position in range(slack):
        ops.append({"op": "set", "key": others[position % len(others)],
                    "value": "v%d" % (position % 4 + 1)})
    ops = ops[:software.MAX_OPS]
    reference = software.reference_run(ops)[witness_id]
    faulty = software.faulty_run(ops, fault)[witness_id]
    if reference == faulty:
        raise AssertionError("witness does not disagree at %d/%s/%d"
                             % (world, kind, index))
    task = {"family": "software",
            "task_id": "%s-w%d-%s-sw-%02d" % (TASK_PREFIX, world, kind, index),
            "fault": fault, "ops": ops,
            "witness": {"observation": witness_id, "ref": reference,
                        "faulty": faulty},
            "template": template, "slack": slack, "seed": seed}
    if not software.task_is_valid(task):
        raise AssertionError("generated task is not well formed: %s"
                             % task["task_id"])
    return task


def generate_graph(world: int, kind: str, index: int) -> dict:
    """A well-formed graph task carrying pendant vertices, bounded by the cap.

    A pendant vertex contributes two removable units, the vertex and its
    edge, so the graph arm of the panel steps the axis in twos. That is
    recorded rather than hidden: `axis_census` reports the measured
    removable count per task, and the software arm is the one that reaches
    every integer on the axis.

    The requested slack is bounded by the family's own vertex cap rather
    than dropped when it does not fit, because a dev template that already
    spends nine of the ten vertices would otherwise leave the transfer rows
    with no headroom at all. `slack` on the task is the slack actually
    placed, and the census measures the removable count independently of it.
    """
    requested = SLACK_BY_KIND[kind][index % 3]
    seed = _seed_for("graph", world, kind, index)
    specs = GR_TRANSFER_TEMPLATES if kind == "transfer" else GR_DEV_TEMPLATES
    spec = sorted(specs)[index % len(specs)]
    from experiments.representation.splits import _assemble, _rng as split_rng
    # The dev and within rows draw the same spec and the same slack, so on
    # their own they regenerate the same graph and the use row leaks a
    # development task. The `ad01` freeze avoided this by rejecting any
    # candidate whose content key matched a dev task and re-salting until
    # one did not; this carries the same rule over every world rather than
    # the one the task belongs to, for the reason `_all_dev_keys` gives.
    if kind == "dev":
        return _graph_at(world, kind, index, seed, spec, requested, 0)
    avoid = _all_dev_keys("graph")
    for salt in range(64):
        task = _graph_at(world, kind, index, seed, spec, requested, salt)
        if task is None or _content_key(task) in avoid:
            continue
        return task
    raise AssertionError("no valid graph for %d/%s/%d" % (world, kind, index))


def _graph_at(world: int, kind: str, index: int, seed: int, spec: str,
              requested: int, salt: int) -> dict | None:
    from experiments.representation.splits import _assemble, _rng as split_rng

    rng = split_rng("exp-axis-graph", seed, world, kind, index, salt)
    vertices, edges = _assemble(spec, rng)
    anchor = max(vertices)
    placed = 0
    for step in range(requested):
        if len(vertices) >= graphs.MAX_VERTICES:
            break
        fresh = anchor + 1 + step
        vertices.append(fresh)
        edges.append([anchor, fresh])
        placed += 1
    task = {"family": "graph",
            "task_id": "%s-w%d-%s-gr-%02d" % (TASK_PREFIX, world, kind, index),
            "vertices": sorted(vertices),
            "edges": [sorted(edge) for edge in edges],
            "template": spec, "slack": placed, "seed": seed}
    try:
        parsed = graphs.parse_graph(task)
    except graphs.GraphInvalid:
        return None
    return task if graphs.witness_holds(parsed) else None


def generate(family: str, world: int, kind: str, index: int) -> dict:
    if kind not in KINDS:
        raise ValueError("unknown-kind %r" % kind)
    if family == "software":
        return generate_software(world, kind, index)
    if family == "graph":
        return generate_graph(world, kind, index)
    raise ValueError("unknown-family %r" % family)


# ---------------------------------------------------------------------------
# the measurement
# ---------------------------------------------------------------------------


def removable_atoms(task: dict) -> int:
    """How many single-atom deletions this task accepts, measured.

    Read off the checker rather than predicted from the generator, because a
    panel whose difficulty is a claim about its own construction is a claim
    the construction could be wrong about.
    """
    if task["family"] == "software":
        build, _ = reducers.software_atoms(task)
        count = len(task["ops"])
        return sum(1 for position in range(count)
                   if checkers.check_software(
                       task, build([index for index in range(count)
                                    if index != position]))["verdict"]
                   == checkers.PRESERVED)
    build, _ = reducers.graph_atoms(task)
    units = len(task["vertices"]) + len(task["edges"])
    return sum(1 for position in range(units)
               if checkers.check_graph(
                   task, build([index for index in range(units)
                                if index != position]))["verdict"]
               == checkers.PRESERVED)


def grade(task: dict, candidate) -> dict:
    if task["family"] == "software":
        return checkers.check_software(task, candidate)
    return checkers.check_graph(task, candidate)


def run_reducer(task: dict, method: str, budget: int) -> dict:
    oracle = (checkers.SoftwareOracle(task, max_queries=budget)
              if task["family"] == "software"
              else checkers.GraphOracle(task, max_queries=budget))
    reducer = (reducers.reduce_software if task["family"] == "software"
               else reducers.reduce_graph)
    result = reducer(task, oracle, method=method, max_queries=budget)
    report = grade(task, result["candidate"])
    return {"verdict": report["verdict"], "reason": report["reason"],
            "queries": int(result.get("queries") or 0),
            "accepted": int(result.get("accepted") or 0),
            "status": str(result.get("status") or ""),
            "candidate": result["candidate"]}


def axis_census(budget: int = ARM_BUDGET, *, root: Path | None = None) -> dict:
    """Every task in the panel, both strategies, at one budget.

    The removable count and the reason are reported side by side, because
    the claim is that the second is a function of the first and the first is
    the only thing about a task the generator controls.
    """
    rows = []
    for task in all_tasks(root):
        removable = removable_atoms(task)
        entry = {"task_id": task["task_id"], "family": task["family"],
                 "kind": task["task_id"].split("-")[2],
                 "removable_atoms": removable,
                 "declared_slack": int(task.get("slack", 0)),
                 "strategies": {}}
        for method in ("ddmin", "greedy"):
            outcome = run_reducer(task, method, budget)
            entry["strategies"][method] = {
                "verdict": outcome["verdict"], "reason": outcome["reason"],
                "queries": outcome["queries"], "accepted": outcome["accepted"]}
        rows.append(entry)
    verdicts = sorted({entry["strategies"][method]["verdict"]
                       for entry in rows for method in entry["strategies"]})
    reasons = sorted({entry["strategies"][method]["reason"]
                      for entry in rows for method in entry["strategies"]})
    by_removable: dict = {}
    for entry in rows:
        bucket = by_removable.setdefault(str(entry["removable_atoms"]), {})
        for method in entry["strategies"]:
            reason = entry["strategies"][method]["reason"]
            bucket[reason] = bucket.get(reason, 0) + 1
    zero = [entry["task_id"] for entry in rows
            if entry["removable_atoms"] == 0]
    return {
        "version": "ad01-exp-axis-census/1",
        "freeze_id": FREEZE_ID, "budget": budget,
        "tasks": len(rows),
        "verdicts": verdicts, "distinct_verdicts": len(verdicts),
        "reasons": reasons, "distinct_reasons": len(reasons),
        "reason_by_removable_atoms": dict(sorted(
            by_removable.items(), key=lambda item: int(item[0]))),
        "tasks_with_zero_removable_atoms": sorted(zero),
        "zero_removable_count": len(zero),
        "verdict_is_constant": len(verdicts) == 1,
        "reason_varies": len(reasons) > 1,
    }


# ---------------------------------------------------------------------------
# the fixpoint
# ---------------------------------------------------------------------------


def oracle_is_the_grader() -> dict:
    """Whether a reducer's oracle and the campaign's grader are one function.

    Read off the call graph rather than off the import list, because two
    modules can import the same name and still drift. The oracle's `check`
    is unwrapped and its body compared against the checker's, and
    `trajectory._check` is stepped for the family it routes to.
    """
    from experiments.ad01 import trajectory

    def unwrap(function) -> str:
        import inspect
        return inspect.getsource(function)

    return {
        "version": "ad01-exp-axis-identity/1",
        "software_oracle_returns_checker": (
            "check_software(self.task, candidate)"
            in unwrap(checkers.SoftwareOracle.check)),
        "graph_oracle_returns_checker": (
            "check_graph(self.task, candidate)"
            in unwrap(checkers.GraphOracle.check)),
        "trajectory_routes_to_checker": bool(
            "check_software" in unwrap(trajectory._check)
            and "check_graph" in unwrap(trajectory._check)),
        "reducers_accept_only_preserved": {
            name: sorted(line.strip() for line in unwrap(getattr(
                reducers, name)).splitlines()
                if "PRESERVED" in line
                and (line.strip().endswith("PRESERVED:") or
                     '== PRESERVED"' in line))
            for name in ("ddmin_reduce", "greedy_reduce")},
        "note": ("the verdict a trial is accepted on is the verdict the"
                 " output is graded on, and both reducers assign `keep`"
                 " only from an accepted trial or return the task unchanged,"
                 " so the graded verdict is `preserved` on both branches"),
    }


def frozen_census(budgets=CENSUS_BUDGETS) -> dict:
    """The committed `ad01` freeze, swept. Not a new panel: the old one."""
    from experiments.ad01 import worlds

    membership = worlds.world_membership(worlds.FROZEN_DIR)
    verdicts: dict = {}
    reasons: dict = {}
    tasks = 0
    triples = 0
    for world in sorted(membership):
        for split, families in sorted(membership[world].items()):
            if not isinstance(families, dict):
                continue
            for family, task_ids in sorted(families.items()):
                for task_id in sorted(task_ids):
                    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                    tasks += 1
                    for budget in budgets:
                        for method in ("ddmin", "greedy"):
                            outcome = run_reducer(task, method, budget)
                            verdicts[outcome["verdict"]] = \
                                verdicts.get(outcome["verdict"], 0) + 1
                            reasons[outcome["reason"]] = \
                                reasons.get(outcome["reason"], 0) + 1
                            triples += 1
    return {
        "version": "ad01-exp-axis-frozen/1",
        "freeze_id": worlds.FREEZE_ID, "tasks": tasks,
        "budgets": list(budgets), "strategies": ["ddmin", "greedy"],
        "triples": triples, "verdicts": dict(sorted(verdicts.items())),
        "reasons": dict(sorted(reasons.items())),
        "verdict_is_constant": len(verdicts) == 1,
    }


def _adversarial_software(seed: int) -> dict | None:
    """A well-formed software task from a different distribution than the freeze's.

    The freeze's tasks are a fault core with a distractor prefix and a
    distractor suffix. This one puts a random prefix, a randomly faulted core
    of three to five ops, and a random suffix, so nothing about its shape is
    inherited from the generator above.
    """
    rng = random.Random(seed)
    fault = rng.choice(software.FAULTS)
    keys = list(software.KEYS)
    rng.shuffle(keys)
    hero, others = keys[0], keys[1:]
    ids = iter(range(1000))

    def value() -> str:
        return "v%d" % rng.randint(1, 4)

    ops = []
    for _ in range(rng.randint(0, 4)):
        ops.append(_random_op(rng, rng.choice(others), next(ids), value))
    if fault == "stale-read":
        ops.append({"op": "set", "key": hero, "value": value()})
        ops.append({"op": "set", "key": hero, "value": value()})
        if rng.random() < 0.5:
            ops.append({"op": "set", "key": hero, "value": value()})
    else:
        ops.append({"op": "set", "key": hero, "value": value()})
        if rng.random() < 0.6:
            ops.append({"op": "clear"})
        if rng.random() < 0.4:
            ops.append({"op": "del", "key": rng.choice(others)})
    witness_id = "o%d" % next(ids)
    ops.append({"op": "get", "key": hero, "id": witness_id})
    for _ in range(rng.randint(0, 5)):
        ops.append(_random_op(rng, rng.choice(keys), next(ids), value))
    ops = ops[:software.MAX_OPS]
    reference = software.reference_run(ops).get(witness_id)
    faulty = software.faulty_run(ops, fault).get(witness_id)
    if reference is None or faulty is None or reference == faulty:
        return None
    task = {"family": "software", "task_id": "adv-sw-%d" % seed,
            "fault": fault, "ops": ops,
            "witness": {"observation": witness_id, "ref": reference,
                        "faulty": faulty}, "seed": seed}
    return task if software.task_is_valid(task) else None


def _random_op(rng: random.Random, key: str, identifier: int,
               value) -> dict:
    kind = rng.choice(["set", "get", "clear", "del"])
    if kind == "set":
        return {"op": "set", "key": key, "value": value()}
    if kind == "get":
        return {"op": "get", "key": key, "id": "o%d" % identifier}
    if kind == "clear":
        return {"op": "clear"}
    return {"op": "del", "key": key}


def _adversarial_graph(seed: int) -> dict | None:
    """A well-formed graph task from a different distribution than the freeze's."""
    rng = random.Random(seed)
    length = rng.choice([5, 7, 9, 11, 13])
    vertices = list(range(length))
    edges = [[index, (index + 1) % length] for index in range(length)]
    for _ in range(rng.randint(0, 6)):
        edges.append([rng.choice(vertices), max(vertices) + 1])
        vertices.append(max(vertices) + 1)
    for _ in range(rng.randint(0, 3)):
        root = rng.choice(vertices)
        first, second = max(vertices) + 1, max(vertices) + 2
        vertices.extend([first, second])
        edges.extend([[root, first], [first, second]])
    for _ in range(rng.randint(0, 3)):
        if edges:
            edges.pop(rng.randrange(len(edges)))
    task = {"family": "graph", "task_id": "adv-gr-%d" % seed,
            "vertices": sorted(vertices),
            "edges": [sorted(edge) for edge in edges], "seed": seed}
    try:
        parsed = graphs.parse_graph(task)
    except graphs.GraphInvalid:
        return None
    return task if graphs.witness_holds(parsed) else None


def adversarial_search(samples: int = 6000, *, budgets=(1, 2, 3, 4, 5, 8, 16, 64)
                       ) -> dict:
    """Thousands of well-formed tasks, swept, and what they grade.

    The search is the falsification attempt. If any well-formed task could
    earn a reducer a non-`preserved` grade, a panel built from it would open
    the gate on the data rather than on the gate, which is the outcome this
    module exists to rule out.
    """
    verdicts: dict = {}
    reasons: dict = {}
    well_formed = {"software": 0, "graph": 0}
    triples = 0
    counterexample = None
    for seed in range(int(samples)):
        for family, builder in (("software", _adversarial_software),
                                ("graph", _adversarial_graph)):
            task = builder(seed)
            if task is None:
                continue
            well_formed[family] += 1
            for budget in budgets:
                for method in ("ddmin", "greedy"):
                    outcome = run_reducer(task, method, budget)
                    verdicts[outcome["verdict"]] = \
                        verdicts.get(outcome["verdict"], 0) + 1
                    reasons[outcome["reason"]] = \
                        reasons.get(outcome["reason"], 0) + 1
                    triples += 1
                    if (outcome["verdict"] != checkers.PRESERVED
                            and counterexample is None):
                        counterexample = {"task_id": task["task_id"],
                                          "budget": budget, "method": method,
                                          "verdict": outcome["verdict"]}
    return {
        "version": "ad01-exp-axis-adversarial/1",
        "samples": int(samples), "budgets": list(budgets),
        "well_formed_tasks": well_formed, "triples": triples,
        "verdicts": dict(sorted(verdicts.items())),
        "reasons": dict(sorted(reasons.items())),
        "verdict_is_constant": len(verdicts) == 1,
        "counterexample": counterexample,
    }


def malformed_escapes() -> dict:
    """What a task that is not well formed grades, and why that is not a panel.

    Both hatches out of the fixpoint land on `invalid`, which is a grade of
    the task rather than of the arm's conduct. A panel built out of these
    would open the gate by removing the task's own well-formedness, which is
    the same defect in a new hat: the constant would have become `invalid`
    rather than become varied.
    """
    cases = []
    triangle = {"family": "graph", "task_id": "esc-gr-triangle",
                "vertices": [0, 1, 2, 3],
                "edges": [[0, 1], [1, 2], [2, 0], [2, 3]], "seed": 1}
    cases.append(("graph-with-triangle", triangle))
    lying = {"family": "software", "task_id": "esc-sw-lying-witness",
             "fault": "stale-read",
             "ops": [{"op": "set", "key": "a", "value": "v1"},
                     {"op": "get", "key": "a", "id": "o0"}],
             "witness": {"observation": "o0",
                         "ref": {"type": "str", "value": "v9"},
                         "faulty": {"type": "str", "value": "v1"}},
             "seed": 2}
    cases.append(("software-witness-does-not-hold", lying))
    rows = []
    for label, task in cases:
        for budget in (1, 4, 64):
            for method in ("ddmin", "greedy"):
                outcome = run_reducer(task, method, budget)
                rows.append({"case": label, "budget": budget,
                             "method": method,
                             "verdict": outcome["verdict"],
                             "reason": outcome["reason"]})
    verdicts: dict = {}
    for row in rows:
        verdicts[row["verdict"]] = verdicts.get(row["verdict"], 0) + 1
    return {
        "version": "ad01-exp-axis-escapes/1",
        "cases": [label for label, _ in cases], "rows": rows,
        "verdicts": dict(sorted(verdicts.items())),
        "verdict": ("the only verdicts outside `preserved` are reached by a"
                    " task that is not well formed, so a panel that opened"
                    " the gate that way would be grading its own malformity"),
    }


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------


def all_tasks(root: Path | None = None) -> list:
    root = FROZEN_DIR if root is None else Path(root)
    out = []
    for world in WORLDS:
        for kind in KINDS:
            for index in range(3):
                out.append(generate("software", world, kind, index))
                out.append(generate("graph", world, kind, index))
    return out


def audit(tasks: list) -> list:
    """The panel's own invariants, checked against the panel.

    Carried over from the `ad01` freeze's rules and not weakened: the ids
    re-derive, the seeds re-derive, every task regenerates byte for byte,
    the world holds its counts, no use task leaks a dev task's content, and
    the transfer rows are the transfer templates.
    """
    problems = []
    by_world: dict = {}
    for task in tasks:
        parts = task["task_id"].split("-")
        if len(parts) != 5 or parts[0] != TASK_PREFIX:
            problems.append("bad-task-id %s" % task["task_id"])
            continue
        world, kind, token, index = int(parts[1][1:]), parts[2], parts[3], \
            int(parts[4])
        family = {"sw": "software", "gr": "graph"}.get(token)
        if family is None:
            problems.append("bad-family-token %s" % task["task_id"])
            continue
        if task["family"] != family:
            problems.append("family-mismatch %s" % task["task_id"])
        if task["seed"] != _seed_for(family, world, kind, index):
            problems.append("seed-mismatch %s" % task["task_id"])
        if task != generate(family, world, kind, index):
            problems.append("regeneration-mismatch %s" % task["task_id"])
        by_world.setdefault(world, []).append((kind, task))
    for world, members in sorted(by_world.items()):
        dev = [task for kind, task in members if kind == "dev"]
        within = [task for kind, task in members if kind == "within"]
        transfer = [task for kind, task in members if kind == "transfer"]
        if len(dev) != 6 or len(within) != 6 or len(transfer) != 6:
            problems.append("world-%d-counts dev=%d within=%d transfer=%d"
                            % (world, len(dev), len(within), len(transfer)))
        dev_content = {_content_key(task) for task in dev}
        for task in within + transfer:
            if _content_key(task) in dev_content:
                problems.append("dev-use-leakage %s" % task["task_id"])
        for kind, task in members:
            if kind not in ("dev", "transfer"):
                continue
            template = task.get("template")
            if task["family"] == "software":
                is_transfer = template in SW_TRANSFER_TEMPLATES
            else:
                is_transfer = template in GR_TRANSFER_TEMPLATES
            if (kind == "transfer") != is_transfer:
                problems.append("transfer-separation %s" % task["task_id"])
    return problems


def build_freeze(root) -> dict:
    root = Path(root)
    manifest = {"freeze_id": FREEZE_ID, "version": VERSION, "files": [],
                "worlds": {}}
    for world in WORLDS:
        by_kind: dict = {}
        for task in all_tasks():
            if not task["task_id"].startswith("%s-w%d-" % (TASK_PREFIX, world)):
                continue
            kind = task["task_id"].split("-")[2]
            target = root / ("world-%d" % world) / kind / (
                "%s.json" % task["task_id"])
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = (json.dumps(task, sort_keys=True, indent=2) + "\n").encode()
            target.write_bytes(raw)
            manifest["files"].append(
                {"path": target.relative_to(root).as_posix(),
                 "task_id": task["task_id"],
                 "digest": hashlib.sha256(raw).hexdigest(),
                 "bytes": len(raw)})
            by_kind.setdefault(kind, {}).setdefault(
                task["family"], []).append(task["task_id"])
        manifest["worlds"][str(world)] = by_kind
    manifest["files"].sort(key=lambda entry: entry["path"])
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (root / "manifest.json").write_bytes(raw)
    (root / "manifest.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "\n")
    return manifest


def verify_freeze(root) -> list:
    root = Path(root)
    try:
        raw = (root / "manifest.json").read_bytes()
        pinned = (root / "manifest.sha256").read_text().strip()
    except OSError:
        return ["manifest-missing"]
    if hashlib.sha256(raw).hexdigest() != pinned:
        return ["manifest-hash-mismatch"]
    manifest = json.loads(raw)
    if manifest.get("freeze_id") != FREEZE_ID:
        problems = ["wrong-freeze-id"]
    else:
        problems = []
    seen = set()
    for entry in manifest.get("files", []):
        path = entry.get("path", "")
        if path in seen:
            problems.append("duplicate-file %s" % path)
        seen.add(path)
        target = root / path
        if not target.is_file():
            problems.append("missing-file %s" % path)
            continue
        if hashlib.sha256(target.read_bytes()).hexdigest() != \
                entry.get("digest"):
            problems.append("digest-mismatch %s" % path)
    return problems


def verify_committed() -> list:
    return verify_freeze(FROZEN_DIR)


def load_manifest(root=None) -> dict:
    return json.loads((Path(FROZEN_DIR if root is None else root)
                       / "manifest.json").read_text(encoding="utf-8"))["worlds"]


def world_membership(root=None) -> dict:
    return load_manifest(root)


def load_task(root, task_id: str) -> dict:
    for path in Path(root).rglob("%s.json" % task_id):
        return json.loads(path.read_text())
    raise KeyError(task_id)


def reader_echoer(target: dict, observations: list, *,
                  authority: dict) -> dict:
    """Whether the instrument can tell a reader from an echoer, both ways.

    `authority` is `{dsn, allocation_id}` for a store the caller holds. Every
    step here executes policy source, so this function does not get to run
    without one: it used to hold none, every step was refused, and each policy
    came back as `{"scored": False}` — a reading about the missing authority
    that the tests then read as a property of the policy.

    The brief for this lane named the confound: holding the task fixed and
    flipping verdicts, reader and echoer both score 2.0, because `VERBATIM`
    excludes `method_id` and `max_queries` and the echoed string is the only
    measured input site. Both directions are measured here, on the new panel's
    experience, which is the first one to carry a varying outcome at all.

    **Direction one, verdicts flipped.** Both policies move their inputs, and
    the echoer scores the same 2.0 the reader does, because the evidence leg
    counts the echoed string as a site that varied and the echoed string did
    vary. The two are not separable here and no panel fixes it. The
    instrument reads actions, and an echo is an action.

    **Direction two, verdicts held fixed and the candidates compared.** A
    policy that re-routes its method on the verdicts returns a different
    candidate; an echoer returns the same candidate whatever it wrote into
    its inputs, because it decided nothing. The evidence leg compares inputs
    and never compares candidates, so it cannot see this. The candidate does
    differ, and it differs in the same direction a reader's does, which is
    the comparison the instrument does not make.

    So the separation is available and the instrument does not take it. That
    is reported as a measurement with a number, not as a change to
    `s09_e2_scored`, which is outside this lane.
    """
    from . import e2_replication as replica
    from . import s09_e2_scored as scored

    def measure(source: str, rows: list):
        proposal = scored.Score({"policy_source": source},
                                "authored-control", "reader-echoer")
        record = proposal.record()
        views = scored.build_views(
            dict(target), rows,
            eligible_methods=replica.eligible_for(target),
            remaining={"steps": 1})
        # One operation identity per view, derived in `scored._execute` from
        # the policy digest, the view digest and the label. A shared identity
        # would return the scored view's action under the alternate view and
        # compare a run with itself.
        return {name: scored._execute(
            proposal, record, views[name], proposal.digest, authority)
            for name in ("scored", "alternate")}

    flipped = [dict(row, verdict=scored.VERDICT_FLIP.get(
        str(row.get("verdict")), row.get("verdict"))) for row in observations]
    rows = {}
    for name, source in (("reader", replica.READS_THE_VERDICT),
                         ("prompted-shape-reader",
                          replica.PROMPTED_SHAPE_READER),
                         ("echoer", replica.ECHOES_WITHOUT_READING),
                         ("ignores-the-verdict",
                          replica.IGNORES_THE_VERDICT),
                         ("ignores-the-view", replica.IGNORES_THE_VIEW)):
        runs = measure(source, observations)
        scored_run, alternate_run = runs["scored"], runs["alternate"]
        if scored_run is None or alternate_run is None:
            rows[name] = {"scored": False}
            continue
        leg = scored._evidence(scored_run, alternate_run)
        inputs_moved = (dict(scored_run["action"].get("inputs") or {})
                        != dict(alternate_run["action"].get("inputs") or {}))
        candidates_moved = (_digest(scored_run["candidate"])
                            != _digest(alternate_run["candidate"]))
        graded = scored._grade(dict(target), scored_run["candidate"],
                               raw=True)
        reduction = scored.normalized_reduction({
            "scored": True, "verdict": graded["verdict"],
            "measure": graded["measure"],
            "initial_measure": graded["initial_measure"]})
        rows[name] = {
            "scored": True,
            "inputs_moved": inputs_moved,
            "candidates_moved": candidates_moved,
            "evidence_varied": leg["varied"],
            "evidence_total": leg["total"],
            "evidence_sites": leg["sites"],
            # The benefit leg is the checker's measure, read through
            # `scored.normalized_reduction` and not through a verdict bit.
            # It was `leg["ratio"] + scored.QUALITY[verdict]`, and the bit
            # was 1.0 for every run that reached here, so this table's
            # `score` was a constant and its `separable` claim below could
            # not have been earned by a difference in reduction.
            "score": leg["ratio"] + reduction,
            "normalized_reduction": reduction,
            "verdict": scored_run["verdict"],
            "method_under_scored": str(
                (scored_run["action"].get("inputs") or {}).get("method_id")),
            "method_under_alternate": str(
                (alternate_run["action"].get("inputs") or {}).get("method_id")),
            "candidate_digest_scored": _digest(scored_run["candidate"]),
            "candidate_digest_alternate": _digest(alternate_run["candidate"]),
        }
    reader = rows.get("reader") or {}
    echoer = rows.get("echoer") or {}
    prompted = rows.get("prompted-shape-reader") or {}
    return {
        "version": "ad01-exp-axis-reader-echoer/1",
        "directions": {
            "one_verdicts_flipped": {
                "reader_score": reader.get("score"),
                "echoer_score": echoer.get("score"),
                "reader_inputs_moved": reader.get("inputs_moved"),
                "echoer_inputs_moved": echoer.get("inputs_moved"),
                "separable": (reader.get("score")
                              != echoer.get("score")),
            },
            "two_candidates_compared": {
                "reader_candidates_moved": reader.get("candidates_moved"),
                "echoer_candidates_moved": echoer.get("candidates_moved"),
                "reader_separable": (reader.get("candidates_moved")
                                     and not echoer.get("candidates_moved")),
                "echoer_separable": (echoer.get("candidates_moved")
                                     and not reader.get("candidates_moved")),
                "prompted_shape_reader_candidates_moved":
                    prompted.get("candidates_moved"),
            },
        },
        "policies": rows,
        "verdict": ("the evidence leg compares action inputs and never the"
                    " candidates, so an echoer that copies the verdicts into"
                    " an input scores the same 2.0 a reader scores. The"
                    " candidate is where the two differ: a policy that"
                    " re-routes on the verdict returns a different candidate"
                    " and an echoer returns the same one. The separation"
                    " exists and the instrument does not read it"),
    }


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        default=str).encode("utf-8")).hexdigest()


def report(*, samples: int = 6000) -> dict:
    return {
        "version": "ad01-exp-axis-report/1",
        "identity": oracle_is_the_grader(),
        "frozen_world": frozen_census(),
        "adversarial": adversarial_search(samples=samples),
        "escapes": malformed_escapes(),
        "new_panel": axis_census(),
        "freeze": {"freeze_id": FREEZE_ID, "dir": str(FROZEN_DIR),
                   "intact": verify_committed(),
                   "audit": audit(all_tasks())},
    }


def main(argv: list) -> int:
    if len(argv) == 3 and argv[1] == "build":
        build_freeze(argv[2])
        return 0
    if len(argv) == 2 and argv[1] == "verify":
        problems = verify_committed() + audit(all_tasks())
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    if len(argv) == 2 and argv[1] == "census":
        print(json.dumps(axis_census(), indent=2, sort_keys=True))
        return 0
    print(json.dumps(report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
