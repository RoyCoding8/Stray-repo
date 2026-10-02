"""A panel whose varying observable is the walk, because the answer cannot be.

`TASKS.md` §D records four E2 attempts refused because the treatment arm's
experience was a constant, and prescribes the fix: a panel of tasks the
authored reducers genuinely fail. `WORKER-STAGE-09-PARALLEL-EXPANSION.md:55`
asks for interventions that separate mechanisms, and a treatment that never
sees two outcomes cannot separate any.

**The prescription is not available, and this module is the measurement of
that rather than a fifth attempt at it.** A reducer's oracle and the
campaign's grader are the same function, so both `reduce_software` and
`reduce_graph` accept a deletion only on a trial the checker graded
`preserved` and return either the task itself or a `keep` the oracle already
approved. Both grade `preserved`. `experience_axis` established the identity of
the two functions and measured 540 triples over the committed `ad01` freeze;
`census` measures it again here over a panel built by a different generator,
and the two agree. `not_preserved` and `invalid` are reachable from a task
that does not parse, whose witness does not hold, or whose candidate is not a
legal deletion. A panel of those is grading its own malformity, and a panel
whose tasks are *merely unfamiliar* is what the previous four attempts had.

Difficulty is the wrong axis and it is worth saying why rather than leaving it
implicit. `initial-not-preserved` returns the incumbent byte for byte, and the
incumbent of a well-formed task grades `preserved` by the well-formedness
condition itself. A task that is too hard and a task that is too easy are the
same answer, so making this panel harder cannot make the answer vary. That is
the negative result, and it is the deliverable: a new namespace and a new
freeze were still built, because the gate needs a stream that varies and the
walk is one.

**What varies is the walk, and the walk is what a developing policy read.**
Every trial the reducer asks the oracle about is graded, and the trials a
reduction attempts are the failures. On this panel both authored methods
observe `preserved` and `not_preserved` on every task at the budget the freeze
pins, where the `ad01` world also does. That is the quantity
`control_distinctness.experience_varies` can be given something to count, and
`walk_observations` is the only builder in this campaign that supplies it: the
four attempts built their experience from the candidate a reducer *returned*,
which is a fixpoint, and this one builds it from the trials it was *graded
on*.

The panel is a new namespace, `ad01-panel-v1`, under `worlds_panel`, and it
shares no task id with the frozen `ad01` world. The four retracted evidence
directories are untouched; this module does not read them and cannot write to
them.

**The separations are built, then measured by `audit`.** Development and
assessment draw from disjoint spec tables, so no program structure and no fault
family appears on both sides, and every assessment task is re-salting-rejected
until its content key misses every development task's across all three worlds.
`audit` reads the specs back off the frozen files rather than off the
generator's own tables, so a generator that assigns a spec to both sides is
caught by the artifacts that carry it, and it refuses a panel whose walk is a
constant on any task.

**The instrument's discrimination is proved, not credited, and a reader
qualified elsewhere does not transfer.** The C15 lesson is that a policy
copying verdicts into a key and deciding nothing scored the same as the
reference reader, and the run read it as learning. On this panel a
count-reading policy scores 2.0 and the echoer 1.0 under the real
`s09_e2_scored.Score.measure`. But `e2_replication.PROMPTED_SHAPE_READER` —
which separated on `ad01` — scores 1.0 here, because it switches on whether
*any* observation is `not_preserved` and this stream already holds both. It
separated on `ad01` only because that stream was constant. A panel that varies
its stream invalidates a reader qualified on a constant one, which is why
`COUNT_READS_THE_VERDICTS` lives here rather than being inherited.

Run: python -m experiments.ad01.panel_variation
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

from experiments.representation import checkers, graphs, reducers, software

FREEZE_ID = "ad01-panel-v1"
VERSION = "AD01-PANEL/1"
TASK_PREFIX = "panel"
FROZEN_DIR = Path(__file__).resolve().parent / "worlds_panel"

# The budget the E2 freeze pins (`e2_replication.MAX_QUERIES`). It is named
# rather than passed in, because a budget chosen per call is a budget chosen
# after seeing the answer.
ARM_BUDGET = 8

KINDS = ("dev", "within", "transfer")
WORLDS = (0, 1, 2)
SW_BASE = {"dev": 8101, "use": 8301}
GR_BASE = {"dev": 8201, "use": 8401}

# Development and assessment draw from disjoint spec tables. The three
# development specs below appear in no assessment table and vice versa, which
# is what `audit` re-reads off the frozen files: a spec shared between the two
# sides is the same program template and the same fault family on both, and a
# panel in that state is not a held-out set however the seeds differ.
# Development, within-family assessment and transfer draw from three disjoint
# spec tables, so no program structure and no fault family appears on two
# sides. That is a stronger separation than `ad01` carries, where development
# and `within` share every spec and only `transfer` is held out; the reason is
# that the walk is the observable here, and a `within` task sharing a
# development spec would let a reading be scored on the same structure twice.
#
# Every software spec is paired with a fault its own core can witness under,
# and `core_disagrees` re-checks that at generation. Four of the ten cores
# tried first cannot disagree at all under either fault, and a core that
# cannot disagree makes an ill-formed task rather than a hard one.
DEVELOPMENT_SPECS = (
    ("software", "rd1", "stale-read"),
    ("software", "rd2", "stale-read"),
    ("software", "d1s2", "stale-read"),
    ("graph", "C5+tree", None),
    ("graph", "C7+tree", None),
    ("graph", "C5+disconnected-path", None),
)

WITHIN_SPECS = (
    ("software", "s2", "stale-read"),
    ("software", "s2s", "stale-read"),
    ("software", "s3", "stale-read"),
    ("graph", "C5+isolated", None),
    ("graph", "C5+star-distractor", None),
    ("graph", "C7+path-distractor", None),
)

TRANSFER_SPECS = (
    ("software", "s1c", "stale-clear"),
    ("software", "s2c", "stale-clear"),
    ("software", "s2sc", "stale-clear"),
    ("graph", "C5+shared-edge", None),
    ("graph", "C5+2-trees", None),
    ("graph", "C7+2-trees", None),
)

# The ops each software spec's core contributes, before the witness `get` and
# the slack. Each was checked to carry a reference/faulty disagreement: four of
# the ten cores tried did not, and a core without one produces a task that is
# not well formed rather than a task that is hard. `core_disagrees` is that
# check, and the specs are the ones that pass it.
SW_CORES = {
    # stale-read family: two writes to one key, optionally preceded by a
    # deletion on another key.
    "rd1": [("set", "b", "v1"), ("del", "b"),
            ("set", "a", "v1"), ("set", "a", "v2")],
    "rd2": [("del", "a"), ("set", "a", "v1"), ("set", "a", "v2")],
    "d1s2": [("set", "b", "v1"), ("del", "b"),
             ("set", "a", "v1"), ("set", "a", "v2")],
    "s2": [("set", "a", "v1"), ("set", "a", "v2")],
    "s2s": [("set", "b", "v1"), ("set", "a", "v1"), ("set", "a", "v2")],
    "s3": [("set", "a", "v1"), ("set", "a", "v2"), ("set", "a", "v3")],
    # stale-clear family: the fault only disagrees when a `clear` sits
    # between the writes, which is why every spec here carries one.
    "s1c": [("set", "a", "v1"), ("clear",)],
    "s2c": [("set", "a", "v1"), ("set", "a", "v2"), ("clear",)],
    "s2sc": [("set", "b", "v1"), ("set", "a", "v1"), ("set", "a", "v2"),
             ("clear",)],
}

ROLE_SPECS = {"dev": DEVELOPMENT_SPECS, "within": WITHIN_SPECS,
              "transfer": TRANSFER_SPECS}

# The slack each role carries. It is the axis that moves the terminal
# *reason* between `ok-incumbent` and `ok-preserved`, and it is spanned
# deliberately so a reader is not told only about zero-slack tasks. A graph
# spec that already spends the vertex cap takes none, and `slack` on the task
# is the slack actually placed rather than the slack requested.
SLACK_BY_ROLE = {"dev": 0, "within": 1, "transfer": 2}


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------


def _rng(*parts) -> random.Random:
    key = "-".join(*[str(part) for part in parts]) if False else \
        "-".join(str(part) for part in parts)
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def _seed_for(family: str, world: int, role: str, index: int) -> int:
    base = SW_BASE if family == "software" else GR_BASE
    return base["dev" if role == "dev" else "use"] + world * 100 + index


def _op(entry) -> dict:
    if entry[0] == "clear":
        return {"op": "clear"}
    if entry[0] == "del":
        return {"op": "del", "key": entry[1]}
    return {"op": "set", "key": entry[1], "value": entry[2]}


def _core_ops(spec: str, hero: str, others: list, values: list) -> list:
    """The spec's core, with each named key bound to a physical one.

    The core table is written against two symbolic keys, `a` (the witness
    key) and `b` (the key a deletion is staged on). The generator picks which
    physical key plays each, so a core is *bound* rather than rendered
    literally: `a` becomes `hero` and `b` becomes `others[0]`.

    That binding is the whole correctness of this function. A renderer that
    rewrote only the writes left `set b` and `del b` naming the same physical
    key after a shuffle, the two cancelled, and every task graded
    `missing`/`missing` — ill-formed, which the checker refuses, rather than
    hard, which is what the panel is for.

    Consecutive writes to the hero get consecutive distinct values. Both
    faults need the disagreement, and a repeat makes the faulty run agree
    with the reference: `stale-read` would find nothing pending and
    `stale-clear` would remember a value the `clear` never dropped.
    """
    roles = {"a": hero, "b": others[0]}
    ops = []
    hero_writes = 0
    for entry in SW_CORES[spec]:
        name = entry[0]
        if name == "clear":
            ops.append({"op": "clear"})
            continue
        key = roles[entry[1]]
        if name == "del":
            ops.append({"op": "del", "key": key})
            continue
        ops.append({"op": "set", "key": key,
                    "value": values[hero_writes % len(values)]})
        if key == hero:
            hero_writes += 1
    return ops


def content_key(task: dict):
    """The task's content, with its name left off.

    The same key `ad01` and `ad01-exp-axis` deduplicate on. A generator that
    re-salts a seed and lands on another row's ops has produced a leak with a
    fresh id, and only a content key sees that.
    """
    if task["family"] == "software":
        return ("software", task["fault"],
                tuple((entry["op"], entry.get("key"), entry.get("value"))
                      for entry in task["ops"]),
                json.dumps(task["witness"]["ref"], sort_keys=True),
                json.dumps(task["witness"]["faulty"], sort_keys=True))
    return ("graph", tuple(task["vertices"]),
            tuple(tuple(edge) for edge in task["edges"]))


def core_disagrees(spec: str, fault: str) -> bool:
    """Whether this spec's core alone carries a reference/faulty disagreement.

    Measured with the family's own interpreter and the same renderer the
    generator uses, rather than predicted from the spec table: a spec table
    listing a core which cannot witness is a claim its own generator can be
    wrong about, and the cores this replaced included four that disagree
    under no fault at all.
    """
    ops = _core_ops(spec, "a", ["b", "c"], ["v1", "v2", "v3", "v4"])
    ops.append({"op": "get", "key": "a", "id": "o0"})
    try:
        parsed = software.parse_task(
            {"family": "software", "task_id": "probe", "fault": fault,
             "ops": ops, "witness": {"observation": "o0",
                                     "ref": {"type": "str", "value": "?"},
                                     "faulty": {"type": "str", "value": "?"}}})
        actual = software.actual_witness(parsed["ops"], fault, "o0")
    except software.SoftwareInvalid:
        return False
    return actual["ref"] != actual["faulty"]


def _software_at(world: int, role: str, index: int, spec: str, fault: str,
                 seed: int, salt: int) -> dict:
    rng = _rng("panel-software", seed, world, role, index, salt)
    keys = list(software.KEYS)
    rng.shuffle(keys)
    hero = keys[0]
    others = [key for key in keys if key != hero]
    # Every value is drawn distinct, because the cores need consecutive
    # hero writes to differ and a repeat makes both faults agree with the
    # reference. `software`'s alphabet is four values, so a four-write core
    # exhausts it and a fifth would silently repeat.
    values = ["v%d" % value for value in rng.sample((1, 2, 3, 4), 4)]
    ops = _core_ops(spec, hero, others, values)
    ops.append({"op": "get", "key": hero, "id": "o0"})
    for position in range(SLACK_BY_ROLE[role]):
        ops.append({"op": "set", "key": others[position % len(others)],
                    "value": values[position % len(values)]})
    ops = ops[:software.MAX_OPS]
    reference = software.reference_run(ops)["o0"]
    faulty = software.faulty_run(ops, fault)["o0"]
    task = {"family": "software",
            "task_id": "%s-w%d-%s-sw-%02d" % (TASK_PREFIX, world, role, index),
            "fault": fault, "ops": ops,
            "witness": {"observation": "o0", "ref": reference,
                        "faulty": faulty},
            "template": spec, "slack": SLACK_BY_ROLE[role], "seed": seed}
    return task if software.task_is_valid(task) else None


def _graph_at(world: int, role: str, index: int, spec: str, seed: int,
              slack: int, salt: int) -> dict | None:
    from experiments.representation.splits import _assemble
    from experiments.representation.splits import _rng as split_rng

    rng = split_rng("panel-graph", seed, world, role, index, salt)
    vertices, edges = _assemble(spec, rng)
    anchor = max(vertices)
    placed = 0
    for step in range(slack):
        if len(vertices) >= graphs.MAX_VERTICES:
            break
        fresh = anchor + 1 + step
        vertices.append(fresh)
        edges.append([anchor, fresh])
        placed += 1
    task = {"family": "graph",
            "task_id": "%s-w%d-%s-gr-%02d" % (TASK_PREFIX, world, role, index),
            "vertices": sorted(vertices),
            "edges": [sorted(edge) for edge in edges],
            "template": spec, "slack": placed, "seed": seed}
    try:
        parsed = graphs.parse_graph(task)
    except graphs.GraphInvalid:
        return None
    return task if graphs.witness_holds(parsed) else None


def _specs_for(family: str, role: str) -> list:
    return [spec for spec in ROLE_SPECS[role] if spec[0] == family]


def generate(family: str, world: int, role: str, index: int) -> dict:
    if role not in KINDS:
        raise ValueError("unknown-role %r" % role)
    choices = _specs_for(family, role)
    _family, spec, fault = choices[index % len(choices)]
    seed = _seed_for(family, world, role, index)
    if family == "software":
        if fault is None:
            fault = software.FAULTS[index % len(software.FAULTS)]
        # A spec whose core cannot witness is a generator bug, not a hard
        # task, so it is caught here rather than reaching the freeze.
        if not core_disagrees(spec, fault):
            raise AssertionError("spec %r cannot witness under %r"
                                 % (spec, fault))
        slack = SLACK_BY_ROLE[role]
        if role == "dev":
            return _software_at(world, role, index, spec, fault, seed, 0)
        avoid = _dev_keys(family)
        for salt in range(64):
            task = _software_at(world, role, index, spec, fault, seed, salt)
            if task is not None and content_key(task) not in avoid:
                return task
        raise AssertionError("no software task for %d/%s/%d"
                             % (world, role, index))
    avoid = _dev_keys(family) if role != "dev" else set()
    for salt in range(64):
        task = _graph_at(world, role, index, spec, seed,
                         SLACK_BY_ROLE[role], salt)
        if task is None or content_key(task) in avoid:
            continue
        return task
    raise AssertionError("no graph task for %d/%s/%d" % (world, role, index))


def _dev_keys(family: str) -> set:
    """Every development task's content on this panel, in every world.

    Wider than `ad01`'s within-world rule, for the reason its `_all_dev_keys`
    gives: the three worlds are independent units, so a use task on one that
    reproduces a dev task on another is the same leak by a longer route.
    """
    return {content_key(generate(family, other, "dev", index))
            for other in WORLDS for index in range(3)}


def all_tasks(root: Path | None = None) -> list:
    """Every task in the freeze, read from the frozen files.

    Read from disk rather than regenerated, so the census describes the
    artifacts a run would be handed and not the generator's own idea of them.
    """
    directory = Path(root or FROZEN_DIR)
    return [json.loads(path.read_text())
            for path in sorted(directory.rglob("*.json"))
            if path.name != "manifest.json"]


def specs_by_role(tasks: list) -> dict:
    """The specs each role actually carries, read off the frozen tasks.

    `{"dev": ..., "within": ..., "transfer": ...}`, keyed by the role in the
    task id rather than by a generator table, so a generator that assigned a
    spec to the wrong role is caught by the artifacts that carry it.
    """
    roles: dict = {role: set() for role in KINDS}
    for task in tasks:
        role = task["task_id"].split("-")[2]
        roles.setdefault(role, set()).add((task["family"],
                                           str(task.get("template"))))
    return roles


# ---------------------------------------------------------------------------
# the measurement
# ---------------------------------------------------------------------------


def _oracle(task: dict, budget: int):
    return (checkers.SoftwareOracle(task, max_queries=budget)
            if task["family"] == "software"
            else checkers.GraphOracle(task, max_queries=budget))


def _reducer(task: dict):
    return (reducers.reduce_software if task["family"] == "software"
            else reducers.reduce_graph)


def stream_verdicts(task: dict, method: str, budget: int = ARM_BUDGET) -> list:
    """Every trial verdict the reducer's walk observed, in order.

    This is the varying quantity. It is read off the oracle the reducer
    actually probed with, not simulated, so a change to the checker moves it.
    """
    oracle = _oracle(task, budget)
    _reducer(task)(task, oracle, method=method, max_queries=budget)
    return [row["verdict"] for row in oracle.history]


def terminal_verdict(task: dict, method: str, budget: int) -> str:
    """The verdict of the candidate the reducer returned, graded by the checker."""
    oracle = _oracle(task, budget)
    result = _reducer(task)(task, oracle, method=method, max_queries=budget)
    report = (checkers.check_software(task, result["candidate"])
              if task["family"] == "software"
              else checkers.check_graph(task, result["candidate"]))
    return report["verdict"]


def same_candidate(task: dict, budget: int = ARM_BUDGET) -> bool:
    first = _candidate(task, "ddmin", budget)
    second = _candidate(task, "greedy", budget)
    return first == second


def _candidate(task: dict, method: str, budget: int):
    oracle = _oracle(task, budget)
    return _reducer(task)(task, oracle, method=method,
                          max_queries=budget)["candidate"]


def census(tasks: list, budget: int = ARM_BUDGET) -> dict:
    """What the panel measures: a constant answer and a varying walk.

    Both halves are reported, because the first is the finding and the second
    is the only thing a reader can consume. A panel that reported one without
    the other would be either the four attempts that were retracted or a
    difficulty claim nothing checked.
    """
    stream, terminal = {}, {}
    varying = 0
    identical = 0
    for task in tasks:
        for method in ("ddmin", "greedy"):
            verdicts = stream_verdicts(task, method, budget)
            for verdict in verdicts:
                stream[verdict] = stream.get(verdict, 0) + 1
            key = (task["task_id"], method)
            if len(set(verdicts)) > 1:
                varying += 1
            answer = terminal_verdict(task, method, budget)
            terminal[answer] = terminal.get(answer, 0) + 1
        if same_candidate(task, budget):
            identical += 1
    by_role = specs_by_role(tasks)
    overlap = sorted(
        pair for left, right in (("dev", "within"), ("dev", "transfer"),
                                 ("within", "transfer"))
        for pair in by_role[left] & by_role[right])
    return {
        "version": "ad01-panel-census/1",
        "freeze_id": FREEZE_ID,
        "budget": budget,
        "tasks": len(tasks),
        "terminal_verdicts": sorted(terminal),
        "distinct_terminal_verdicts": len(terminal),
        "stream_verdicts": sorted(stream),
        "distinct_stream_verdicts": len(stream),
        "trials": sum(stream.values()),
        "tasks_with_a_varying_walk": varying,
        "task_method_pairs": len(tasks) * 2,
        "tasks_where_methods_agree": identical,
        "specs_by_role": {role: sorted("%s/%s" % pair for pair in pairs)
                          for role, pairs in sorted(by_role.items())},
        "spec_overlap": sorted("%s/%s" % pair for pair in overlap),
    }


# A reader that counts, and its echo. The two are the pair that certifies the
# instrument, and the reader reads a *count* rather than a membership because
# that is what the flip moves.
#
# `e2_replication.PROMPTED_SHAPE_READER` asks whether any observation is
# `not_preserved`. On the `ad01` world that is the right shape and it
# separates: its stream is all `preserved`, so the predicate is false and the
# flip makes it true. On this panel it is vacuous — the stream already holds
# both verdicts, so the predicate is true either way and the flip moves
# nothing the reader looks at. A panel that varies its stream invalidates a
# reader written for a constant one, and the qualification has to be re-earned
# rather than inherited.
#
# Counting is what survives both. The flip exchanges `preserved` and
# `not_preserved`, so a stream of N records with L losses becomes one with
# N - L, and a policy that compares L against N re-plans. The echoer below
# writes the same verdicts into an input key, which is the C15 shape.
COUNT_READS_THE_VERDICTS = '''def STEP(view, state):
    rows = list(view.get("observations", []))
    losses = len([r for r in rows if str(r.get("verdict")) == "not_preserved"])
    method_id = "seed-sw-greedy" if losses * 2 >= len(rows) else "seed-sw-ddmin"
    return {"action": {"kind": "use_method",
                       "target": view["task_content"]["task_id"],
                       "inputs": {"method_id": method_id, "max_queries": 8},
                       "evidence_refs": [],
                       "requested_resources": {"queries": 8}},
            "state": {"losses": losses}}
'''

# The same writer with the count replaced by nothing: it emits the verdicts
# and decides from its own constant, so the only thing that moves is a string
# it wrote. `s09_e2_scored._evidence` compares the candidate the world
# produced, which no policy can supply, so this scores as a blind policy does.
ECHOES_WITHOUT_READING = '''def STEP(view, state):
    rows = ",".join([str(r.get("verdict", ""))
                     for r in view.get("observations", [])])
    return {"action": {"kind": "use_method",
                       "target": view["task_content"]["task_id"],
                       "inputs": {"method_id": "seed-sw-ddmin",
                                  "max_queries": 8, "read_verdicts": rows},
                       "evidence_refs": [],
                       "requested_resources": {"queries": 8}},
            "state": {}}
'''


def walk_observations(task_ids, budget: int = ARM_BUDGET) -> list:
    """Experience records carrying the outcomes a reducer was graded on.

    The four refused attempts built their arms from the candidate a reducer
    *returned* (`e2_replication.measured_observations`), which is the fixpoint
    this module's first census measures, so every record carried one verdict
    and `experience_varies` refused. These records are the trials instead, and
    a record is kept only where the walk actually earned more than one.

    `method` is carried because the gate reports `methods_named` and an
    experience that cannot say which method earned an outcome is not an
    experience about a method.
    """
    rows = []
    for task_id in sorted(task_ids or []):
        task = next((t for t in all_tasks() if t["task_id"] == task_id), None)
        if task is None:
            raise KeyError("unknown panel task %s" % task_id)
        for method in ("ddmin", "greedy"):
            verdicts = stream_verdicts(task, method, budget)
            if len(set(verdicts)) < 2:
                continue
            for position, verdict in enumerate(verdicts):
                rows.append({"observation_id": "obs-%s-%s-%d"
                             % (task_id, method, position),
                             "task_id": task_id,
                             "method": method,
                             "verdict": verdict,
                             "reason": "trial-%d" % (position % 2),
                             "detail": "trial %d of %d" % (position + 1,
                                                          len(verdicts))})
    return rows


# ---------------------------------------------------------------------------
# the audit
# ---------------------------------------------------------------------------


def audit(*, dev_specs, within_specs, transfer_specs, tasks,
          budget: int = ARM_BUDGET, measure_stream=None) -> list:
    """Every refusal this panel must earn, checked on the frozen tasks.

    Four rules, and the last is the one four campaigns missed. No spec may
    appear on two roles. No assessment task may reproduce a development
    task's content. No task's walk may be a constant, because an arm handed a
    constant stream is a constant whatever the panel's answers are — which is
    the refusal that stopped four dispatches and was a check nowhere.

    `measure_stream` exists so a caller can ask the question about a panel
    other than this one, and so a test can plant a constant walk and be
    refused. The default measures this panel's tasks as frozen.
    """
    measure = measure_stream or stream_verdicts
    problems = []
    tables = {"dev": dev_specs, "within": within_specs,
              "transfer": transfer_specs}
    pairs = {role: {(family, spec) for family, spec, _ in table}
             for role, table in tables.items()}
    for left, right in (("dev", "within"), ("dev", "transfer"),
                        ("within", "transfer")):
        for family, spec in sorted(pairs[left] & pairs[right]):
            problems.append("spec-shared-by-%s-and-%s %s/%s"
                            % (left, right, family, spec))
    dev_keys = {content_key(task) for task in tasks
                if task["task_id"].split("-")[2] == "dev"}
    for task in tasks:
        role = task["task_id"].split("-")[2]
        if role == "dev":
            continue
        if (task["family"], task.get("template")) in pairs["dev"]:
            problems.append("assessment-on-a-development-spec %s"
                            % task["task_id"])
        if content_key(task) in dev_keys:
            problems.append("content-leak %s" % task["task_id"])
        for method in ("ddmin", "greedy"):
            verdicts = set(measure(task, method, budget))
            if len(verdicts) < 2:
                problems.append("constant-walk %s/%s" % (task["task_id"],
                                                         method))
    if len(tasks) != len({task["task_id"] for task in tasks}):
        problems.append("duplicate-task-id")
    return problems


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


AD01_FROZEN_DIR = Path(__file__).resolve().parent / "worlds"


def build_freeze(root=None) -> dict:
    """Write every task, then the manifest `build_manifest` describes.

    One shape, written once. The first version built a manifest here with
    three keys and a second one in `build_manifest` with seven, so the freeze
    verified against itself only after the two had been made to agree by
    hand — and `verify_freeze` reported `manifest-content-mismatch` on a
    freeze that was byte-consistent. The writer now delegates, so the thing
    that is checked is the thing that was written.
    """
    directory = Path(root or FROZEN_DIR)
    for world in WORLDS:
        for family in ("software", "graph"):
            for role in KINDS:
                for index in range(3):
                    task = generate(family, world, role, index)
                    target = directory / ("world-%d" % world) / role / (
                        "%s.json" % task["task_id"])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(
                        (json.dumps(task, sort_keys=True, indent=2)
                         + "\n").encode())
    manifest = build_manifest(directory)
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (directory / "manifest.json").write_bytes(raw)
    (directory / "manifest.sha256").write_text(_digest(raw) + "\n")
    return manifest


def build_manifest(root=None) -> dict:
    """The committed manifest, so a runner can refuse a panel that drifted.

    Rebuilt from the frozen files rather than regenerated, which is the whole
    point: a panel whose manifest and files disagree is the condition the four
    retractions were written under, and a runner that cannot see it will
    reproduce the run that was retracted.
    """
    directory = Path(root or FROZEN_DIR)
    files = []
    for path in sorted(directory.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        raw = path.read_bytes()
        files.append({"path": path.relative_to(directory).as_posix(),
                      "task_id": path.stem, "digest": _digest(raw),
                      "bytes": len(raw)})
    return {"freeze_id": FREEZE_ID, "version": VERSION, "files": files,
            "budget": ARM_BUDGET,
            "development_specs": ["%s/%s" % (family, spec)
                                  for family, spec, _ in DEVELOPMENT_SPECS],
            "within_specs": ["%s/%s" % (family, spec)
                             for family, spec, _ in WITHIN_SPECS],
            "transfer_specs": ["%s/%s" % (family, spec)
                               for family, spec, _ in TRANSFER_SPECS]}


def verify_freeze(root=None) -> list:
    directory = Path(root or FROZEN_DIR)
    try:
        raw = (directory / "manifest.json").read_bytes()
        pinned = (directory / "manifest.sha256").read_text().strip()
    except OSError:
        return ["manifest-missing"]
    if _digest(raw) != pinned:
        return ["manifest-hash-mismatch"]
    problems = []
    manifest = json.loads(raw)
    if manifest.get("freeze_id") != FREEZE_ID:
        problems.append("wrong-freeze-id")
    if manifest != build_manifest(directory):
        problems.append("manifest-content-mismatch")
    for entry in manifest.get("files", []):
        target = directory / entry["path"]
        if not target.is_file():
            problems.append("missing-file %s" % entry["path"])
        elif _digest(target.read_bytes()) != entry["digest"]:
            problems.append("digest-mismatch %s" % entry["path"])
    return problems


def main(argv: list) -> int:
    if "build" in argv:
        manifest = build_freeze()
        print(json.dumps({"wrote": len(manifest["files"]), "freeze": FREEZE_ID},
                         indent=2))
        return 0
    tasks = all_tasks()
    report = census(tasks)
    report["audit"] = audit(dev_specs=DEVELOPMENT_SPECS,
                            within_specs=WITHIN_SPECS,
                            transfer_specs=TRANSFER_SPECS, tasks=tasks)
    report["freeze_problems"] = verify_freeze()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["audit"] or report["freeze_problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
