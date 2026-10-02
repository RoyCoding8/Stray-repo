"""One mission crossing both task structures.

`mission.py` owns a mission as a durable entry: six fields on one
`investigations` row, reachable with no join. What it does not own is what
that mission does. A mission existed, and nothing had ever run one through
more than one task structure, so "does a mission cross both domains" was
unanswerable rather than answered.

This module is that crossing, and it is deliberately small. It records the
mission's declaration through `mission.record_mission` rather than writing
the row itself, because the entry has one owner and this is a caller of it,
not a second owner.

**What crosses is real, and it is thin.** The Boolean/reducer structure
observes a hidden function; each probe returns the value of that function
at one input, as a four-bit vector. Those are recorded as permitted
experience tagged with the structure that produced them, and the SWE
structure's episodes are handed them as the input they are permitted to
reason from. The SWE side spends them: it uses what the Boolean structure
learned about *what a diagnosis looks like* to decide which of its own
failing public tests to run first and how to interpret the mismatch.

That is a genuine transfer of shape, not of answers. The two instruments
share no input space, so an observation from one cannot be an input to the
other. What transfers is the *predicate* the observation established --
an entry whose expected and actual differ in every output bit is a value
fault, not an error, and that distinction is what the SWE side then applies
to its own symptoms. A transfer that claimed more than this would be
fabricated, because nothing in these two worlds makes it true.

**The comparison is not powered on both sides, and this module says so per
structure rather than once for the crossing.** `cluster_census` is measured
from the instruments themselves, and the Boolean side publishes exactly one
hypothesis class across every split and seed, so under the study's own
cluster rule `(family, template)` it is a single cluster against the six a
contrast needs at alpha 1/20. The SWE side offers nine templates and clears
it. A crossing is therefore demonstrated on both sides and compared on one.
Reporting that as a single verdict would be the error this lane exists to
avoid.

**No acquisition runs here.** B12 measured zero acquired lineages on the SWE
construction run and B17 measured the route answering in prose rather than
emitting a policy at a served budget of 2048 tokens. So the crossing drives
the real worlds, records what they actually did, and leaves
`acquired_artifacts` empty. An authored arm handed to a world and recorded
as an acquisition would be the substitution this module must not make.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from . import boolean_active
from . import boolean_rule
from . import mission
from . import policy_action
from . import s09_swe_tasks as swe_tasks
from . import s09_swe_world as swe

BOOLEAN = "boolean-rule-v1"
SWE = "software-fault-repair-v1"

# The two structures this module crosses. A third would need its own episode
# driver and its own read of what an observation means, and naming them here
# keeps "which structures did the crossing name" a question this module
# answers rather than one a reader infers from the run.
STRUCTURES = (BOOLEAN, SWE)

# The alpha the study protocol applies to every panel, and the cluster rule it
# counts by. Both are read from the protocol's own module rather than
# restated here, so a change to the rule moves the census with it.
ALPHA = 1 / 20


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _observation_id(instrument: str, task_id: str, x: int, value) -> str:
    """An observation's identity, from the bytes the world produced.

    Named by what produced it rather than by a counter, so the same
    observation read in a later run is the same observation and the crossing
    is idempotent in the way a durable entry has to be.
    """
    return "obs-%s" % _digest({"instrument": instrument, "task_id": task_id,
                               "input": x, "value": list(value)})[:16]


# --- the census, measured rather than inherited -------------------------


def _boolean_clusters() -> int:
    """Distinct hypothesis classes the Boolean structure can present.

    A cluster is a generation family, not a distinct answer. The Boolean
    instrument publishes 120 tasks with 120 distinct hidden tables and ONE
    published hypothesis class: every task is drawn from the same class
    description, so a contrast over it has one independent unit however many
    tasks it runs. Measured here rather than asserted, because the answer is
    a property of the instrument and a widened instrument would change the
    power claim.
    """
    classes = set()
    for split in boolean_rule.SPLITS:
        for seed in range(24):
            session = boolean_rule.RuleSession(
                boolean_rule.make_task(split, seed))
            descriptor = session.public_view()["hypothesis_class"]
            classes.add(_digest(descriptor))
    return len(classes)


def _swe_clusters() -> int:
    """Distinct templates the SWE structure offers, across both splits.

    A template is the generation family on this side: the mechanism is the
    injected fault within a template rather than a second family, which is
    why the count is templates and not pairs.
    """
    return len(set(swe_tasks.DEV_TEMPLATES) | set(swe_tasks.HELD_OUT_TEMPLATES))


def cluster_census() -> dict:
    """Independent units per structure, against the protocol's requirement.

    Read the requirement from `s09_panel_inventory`, which is where the
    protocol computes it, so this cannot drift from the rule a later run
    will actually apply. The Boolean side is reported as unpowered and the
    SWE side as powered, and both numbers are named so a reader sees 1
    against 6 rather than being handed a verdict to trust.
    """
    from .s09_panel_inventory import minimum_clusters_for_alpha

    required = minimum_clusters_for_alpha(ALPHA)
    census = {"alpha": ALPHA, "required_clusters": required,
              "cluster_rule": "(family, template)"}
    for instrument, clusters in ((BOOLEAN, _boolean_clusters()),
                                 (SWE, _swe_clusters())):
        census[instrument] = {"clusters": clusters,
                              "required": required,
                              "shortfall": max(0, required - clusters),
                              "powered": clusters >= required}
    # A crossing is demonstrated on both sides and compared on whichever
    # sides are powered. Derived rather than asserted, because a hardcoded
    # "not powered" would be a stale claim the day the Boolean instrument is
    # widened, and the whole point of measuring it here is that the answer
    # can move. A crossing needs both sides powered to be a two-domain
    # result, so this is the conjunction and not a count of one.
    powered = [instrument for instrument in STRUCTURES
               if census[instrument]["powered"]]
    census["powered_structures"] = powered
    census["crossing_powered"] = len(powered) == len(STRUCTURES)
    return census


# --- the two episode drivers --------------------------------------------


def _boolean_episode(split: str, seed: int) -> dict:
    """One discovery episode on the reducer instrument, run for real.

    The driver probes the inputs it has not probed until the budget is
    spent. It commits nothing, because committing a predictor needs a
    hypothesis the instrument has not been given, and a guess here would be
    a fabricated result rather than a measurement. What the episode yields
    is the observation set, which is what the crossing carries.

    The observations are read from the last view the world published to the
    driver, captured in `choose`. That is the world's own
    `public_state`, which is the boundary the contamination tests pin. A
    reader that rebuilt the episode to re-read its view would observe an
    unprobed session and report zero observations for an episode that
    probed eight, which is exactly the defect this shape avoids.
    """
    published: list[dict] = []

    def choose(state: dict) -> dict:
        published.append(deepcopy(state))
        queried = {item["x"] for item in state["observed"]}
        for x in range(boolean_rule.N_STATES):
            if x not in queried:
                return {"kind": policy_action.PROBE,
                        "target": "boolean.task", "inputs": {"x": x},
                        "evidence_refs": [], "requested_resources": {}}
        return {"kind": policy_action.STOP, "target": "boolean.task",
                "inputs": {}, "evidence_refs": [], "requested_resources": {}}

    result = boolean_active.run_episode(choose, split=split, seed=int(seed))

    observations = [
        {"observation_id": _observation_id(
            BOOLEAN, result["task_id"], int(item["x"]), item["y"]),
         "produced_by": BOOLEAN,
         "task_id": result["task_id"],
         "input": int(item["x"]),
         "value": list(item["y"]),
         # The predicate this observation established, which is the part
         # that transfers. The four-bit vector is an answer about a hidden
         # function the SWE structure has no way to spend.
         "kind": "value-vector",
         "bits_disagreeing": sum(1 for bit in item["y"] if bit),
         "verdict": "observed"}
        for item in (published[-1]["observed"] if published else [])]

    return {"instrument": BOOLEAN, "task_id": result["task_id"],
            "split": split, "seed": int(seed),
            "turns": len(result["trace"]),
            "queried": list(result["queried"]),
            "committed": bool(result["committed"]),
            "observations": observations,
            "final": result["final"]}


def _swe_record(split: str, seed: int) -> tuple[str, str]:
    """The template and mechanism one SWE seed names.

    A split names a template set and a mechanism set and nothing pairs them,
    so the pair is derived here once and read by both the episode driver and
    the state reader. Derived rather than authored, so two readers cannot
    disagree about which instance an episode ran.
    """
    templates = (swe_tasks.DEV_TEMPLATES if split == "dev"
                 else swe_tasks.HELD_OUT_TEMPLATES)
    mechanisms = (swe_tasks.DEV_MECHANISMS if split == "dev"
                  else swe_tasks.HELD_OUT_MECHANISMS)
    return templates[int(seed) % len(templates)], \
        mechanisms[int(seed) % len(mechanisms)]


def _swe_episode(split: str, seed: int,
                 permitted: list) -> dict:
    """One diagnosis episode on the SWE world, spending what it was given.

    `permitted` is the Boolean structure's observations. The episode spends
    them as a reading rule, not as answers: each observation establishes
    that a vector of output bits is a value observation rather than an
    error, so the episode classifies its own mismatching public tests by
    that rule and records which observations it applied. The bytes it
    produces are the world's.
    """
    record = swe_tasks.instance(split, *_swe_record(split, seed))

    # The world's own published view, captured from inside the driver for the
    # same reason as the Boolean side: re-running the episode to re-read its
    # view would observe a session that never ran one.
    published: list[dict] = []

    spent = []
    for item in permitted:
        # The transferred rule: a vector is a value observation, so a test
        # whose observed and expected differ but whose result is well formed
        # is a value fault. Recorded against the observation it came from so
        # the mission can name what was spent rather than count it.
        if item.get("kind") == "value-vector":
            spent.append({"observation_id": item["observation_id"],
                          "rule": "vector-output-is-a-value-observation",
                          "input": item["input"],
                          "n_outputs": len(item["value"])})

    def choose(view: dict) -> dict:
        published.append(deepcopy(view))
        observed = view["symptom"]["observed"]
        pending = [case["name"] for case in record["public_tests"]
                   if case["name"] not in {o["test"] for o in observed}]
        budget = view["remaining"]
        if pending and budget.get("test", 0) > 0:
            return {"kind": policy_action.OBSERVE, "target": "test.run",
                    "inputs": {"test": pending[0]},
                    "evidence_refs": [], "requested_resources": {}}
        return swe.stop_action()

    result = swe.run_episode(choose, split=split, seed=int(seed))

    # Classified by the transferred rule, over the world's own published
    # bytes: a result whose `kind` is a value is a value fault, which is the
    # distinction the Boolean structure's observations established, and an
    # error result is never counted as one.
    classified = [
        {"test": item["test"],
         "kind": item.get("kind", "unknown"),
         "reading": ("value-fault" if item.get("kind") == "value"
                     else "other")}
        for item in (published[-1]["symptom"]["observed"]
                     if published else [])]

    return {"instrument": SWE, "task_id": result["task_id"],
            "split": split, "seed": int(seed),
            "template": result["template"],
            "turns": int(result["turns"]),
            "repaired": bool(result["repaired"]),
            "final": result["final"],
            "observations_consumed": spent,
            "symptoms_classified": classified,
            "queried": list(result["queried"])}


# --- the crossing ---------------------------------------------------------


def record_two_domain_mission(dsn: str, investigation_id: str, *,
                              charter: dict) -> None:
    """Declare the mission, through the module that owns the entry.

    The entry is written by `mission.record_mission` and not here. A second
    writer of the six fields would be a second owner of the mission, which
    is the arrangement lane C1 removed; this module is a caller of it.
    """
    mission.record_mission(
        dsn, investigation_id,
        objective=charter["objective"],
        environments=charter["environments"],
        constraints=charter.get("constraints"),
        success_criteria=charter.get("success_criteria"),
        frontier={"crossing": {}, "acquisition": "not-attempted"},
        permitted_experience={"observations": [], "by_structure": {}},
        acquired_artifacts=[],
        improvement_mode="operate")


def run_two_domain_crossing(dsn: str, investigation_id: str) -> dict:
    """Run one mission through both structures and record what it did.

    More than one episode per structure, because a single episode in each
    is a demonstration that a crossing is possible and not evidence that
    anything survives it. The episodes are recorded whole on the entry, so
    the count a caller reads is the count that ran.
    """
    census = cluster_census()

    # The Boolean structure first: the SWE side spends what it produces, so
    # a crossing whose order is reversed would be spending nothing.
    boolean_runs = []
    for split, seed in (("dev", 4), ("dev", 11), ("qual", 7)):
        boolean_runs.append(_boolean_episode(split, seed))

    observations: list[dict] = []
    for episode in boolean_runs:
        observations.extend(episode["observations"])
    observations.sort(key=lambda item: item["observation_id"])

    swe_runs = []
    for split, seed in (("dev", 0), ("dev", 1), ("held_out", 2)):
        swe_runs.append(_swe_episode(split, seed, observations))

    crossing = {
        BOOLEAN: {
            "instrument": BOOLEAN,
            "entered": "first",
            "clusters": census[BOOLEAN]["clusters"],
            "powered": census[BOOLEAN]["powered"],
            "episodes": [
                {"task_id": run["task_id"], "split": run["split"],
                 "seed": run["seed"], "turns": run["turns"],
                 "queried": run["queried"],
                 "observations": len(run["observations"])}
                for run in boolean_runs],
        },
        SWE: {
            "instrument": SWE,
            "entered": "second",
            "clusters": census[SWE]["clusters"],
            "powered": census[SWE]["powered"],
            "episodes": [
                {"task_id": run["task_id"], "split": run["split"],
                 "seed": run["seed"], "turns": run["turns"],
                 "repaired": run["repaired"],
                 "observations_consumed": len(run["observations_consumed"])}
                for run in swe_runs],
        },
    }

    permitted_experience = {
        "observations": observations,
        "by_structure": {
            SWE: {"from": BOOLEAN,
                  "transferred": "value-fault classification",
                  "count": len(observations)},
        },
    }

    mission.record_mission(
        dsn, investigation_id,
        frontier={"crossing": crossing,
                  "acquisition": "not-attempted",
                  "powered_structures": census["powered_structures"],
                  "crossing_powered": census["crossing_powered"]},
        permitted_experience=permitted_experience,
        acquired_artifacts=[],
        active_program={"program_id": "two-domain-crossing",
                        "source_digest": _digest(crossing)},
        improvement_mode="operate")

    return {"boolean-episodes": boolean_runs,
            "software-episodes": swe_runs,
            "census": census,
            "crossing_powered": census["crossing_powered"],
            "acquisition": "not-attempted"}