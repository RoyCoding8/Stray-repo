"""The authored control arm the study was missing, as a pilot.

M3-2 documented four blockers between `run_study_v1` and a control arm and
deleted the function that would have supplied one. This module is the other
answer: it builds the control repertoire, the selector that chooses within
it, and the freeze block that names the arm, and the study writes what this
returns rather than computing it inline.

Four decisions, each measured rather than argued.

**The id namespace is `ctl-`, and that is the whole of blocker 2.**
`trajectory._run_member` looks a member's `capability_id` up in
`seeds.SEED_CAPABILITIES` and, on a hit, calls `seeds.run_seed` in the host
and returns without staging the source. A `seed-` id therefore measures the
host's dispatch table: `executed_source` comes back as the method name
(`"greedy"`) rather than the bytes, and a member whose source raises on
execution still returns a result. `ctl-` is in no such table, so the source
is staged and run. `_run_member` is unchanged; the arm is routed around the
short-circuit by choosing ids that do not collide with it, which is what
`load_repertoire` already refuses for acquired members
(`acquired member %r claims a reserved seed capability id`).

**The selector resolves a family claimed by two members by task feature, not
by position.** The existing `_v1_use_policy_fallback` refuses that case by
design, and the rule it protects is real: `eligible[0]` was a position, and
in `repertoire-w1-I.json` position zero is the graph member, so all three
software tasks were refused as family-mismatched (commit `28c3e65`). What
that rule protects is *unfounded* selection — a pick with no basis in
anything the world said. A control arm has two members per family by
construction, so "ambiguous" is the normal case, and refusing it would
refuse the arm.

The replacement keeps everything the original rule was for and gives the
ambiguous case a basis the original could not have: the public task view.
`packet.PUBLIC_TASK_FIELDS` carries `family`, `template`, and the public
`ops`/`vertices`/`edges`, so the selector can read the shape of the task
before it runs anything, and pick by that. It never looks at list order, and
it never reads a sealed field — a selector that read the answer would be a
governance smell of exactly the kind `77001fc` removed. What it reads is
declared in the generated source as a `by_template` table followed by a
feature fallback, so a reader sees the whole rule in the artifact rather than
inferring it from code. A family no member claims, a family whose members
are all unscoped, and a family whose tie the feature rule cannot break are
all still refusals, because those are the three cases where there is
genuinely nothing to select on.

**The members name their strategy in their own bytes.** The C15 defect was
one `method_source` with a `params.method` field beside it, so
`control_distinctness._strategy_of` found no strategy on either arm and read
two members as one. The sources here differ in the reducer call itself, and
`source_digest` is the sha256 of the source it names, so every digest in the
repertoire is a digest of bytes that execute.

**The budget is derived, not raised.** The ceilings in `_v1_admit` are
typed literals and a control arm on every combination exceeds two of them.
`use_budget()` returns what this arm costs on the tasks it will actually
run, and the study ceiling is `acquired_use_budget() + control_use_budget()`.
A study-level ceiling should be spendable by the arms that run under it: a
ceiling no combination of the study's own arms can spend is not a bound, it
is a guess.

Measured on this branch at `9c00de1`, budget 4, over all 36 frozen use
tasks: ddmin and greedy return byte-distinct candidates on 36 of 36, and
they differ in size on 23. The byte-distinctness is what `control_distinct`
refuses on; the size difference is what the frozen world can see.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

# The id prefix. `trajectory.load_repertoire` refuses a member whose
# `capability_id` is in `seeds._KNOWN`, so this namespace cannot collide
# with the host's `run_seed` short-circuit by construction and not by
# convention. See the module docstring, blocker 2.
ID_PREFIX = "ctl-"

ORIGIN_AUTHORED = "authored-control"

# The two strategies a control member can be built around. One member per
# strategy per family, so a family with two members is the expected shape
# and not the anomaly the selector used to refuse.
STRATEGIES = ("ddmin", "greedy")

# The reducer each family calls. Named here rather than derived from a
# suffix, for the reason `_adapter_for` carries: a suffix match is what
# mistook `ddmin_reduce` for a dispatcher of `method=ddmin`.
_REDUCERS = {"software": "reduce_software", "graph": "reduce_graph"}

# The budget every control member runs at. Pinned rather than derived so
# the two arms of a comparison are measured at the same witness budget:
# `control_distinct` reports a budget difference under `differing_budget`,
# and a difference it reports is a difference the reader has to discount.
# The acquired arm's members are given the same value in `control_tasks`.
BUDGET = 4


def _member_source(family: str, method: str) -> str:
    """Bytes that differ between the two members of a family.

    The strategy is inside the reducer call, not beside it. A `params`
    field naming the method would be a label the record carries and the
    child never reads, which is the C15 shape: two ids, one source, no
    strategy anywhere `control_distinct` can see.
    """
    return (
        "def ENTRY(task, oracle, max_queries=16):\n"
        "    return reducers.%s(task, oracle, method='%s',"
        " max_queries=max_queries)\n" % (_REDUCERS[family], method)
    )


def _member(capability_id: str, family: str, method: str) -> dict:
    source = _member_source(family, method)
    return {
        "capability_id": capability_id,
        "authored": True,
        "origin": ORIGIN_AUTHORED,
        "entry": "ENTRY",
        "method_source": source,
        "source_digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "scope": {"family": family},
        "strategy": method,
    }


def control_repertoire(campaign_id: str, families=("software", "graph"),
                       *, strategies=STRATEGIES) -> dict:
    """A repertoire carrying two byte-distinct members per family.

    `campaign_id` is the control arm's own campaign identity. It is not a
    study campaign id, so the control's records never collide with an
    acquired arm's and `records.verify_study`'s duplicate checks cannot see
    two arms as one campaign.
    """
    members = []
    for family in families:
        for method in strategies:
            members.append(_member(
                "%s%s-%s" % (ID_PREFIX, family, method), family, method))
    return {"campaign_id": campaign_id, "members": members, "queries": 0}


def eligible(repertoire: dict) -> list:
    """The `by_family` view the study's selector builder reads."""
    return [{"capability_id": m.get("capability_id"),
             "family": (m.get("scope") or {}).get("family"),
             "strategy": m.get("strategy")}
            for m in (repertoire.get("members") or [])
            if m.get("capability_id")]


# ---------------------------------------------------------------------------
# the selector
# ---------------------------------------------------------------------------


def _feature_key(view: dict) -> str:
    """A key into the per-family feature table, read off the public view.

    The key is the task's own shape, and nothing else. `template` is a
    public field the freeze publishes, and the atom counts behind it are
    the same public fields `strip_task` keeps, so the key is finer than the
    template name where two tasks share a template and differ in size. No
    sealed field is read and no oracle is consulted: the selector decides
    before anything executes, so a key that depended on a witness would be
    a decision made with the answer in hand.
    """
    task = dict(view or {})
    template = task.get("template")
    if not isinstance(template, str) or not template:
        template = "unshaped"
    for field, noun in (("ops", "ops"), ("vertices", "vertices")):
        atoms = task.get(field)
        if isinstance(atoms, list) and atoms:
            edges = task.get("edges")
            suffix = ("e%d" % len(edges)
                      if isinstance(edges, list) and edges else "")
            return "template:%s|%s:%d%s" % (template, noun, len(atoms),
                                            suffix)
    return "template:%s" % template


def selector_source(repertoire: dict, *, features: dict | None = None,
                    coarse: dict | None = None) -> str:
    """A STEP selector that answers a family two members both claim.

    Four rules, in order, and the first that fires decides:

    1. A family with exactly one member answers for itself. This is the
       case `_v1_use_policy_fallback` already handled and it is kept
       verbatim, so an acquired arm's use phase is unchanged by this.
    2. A family with two members is decided by `by_shape`: a table of
       public task shape to capability id, built from the measured
       separation of the two strategies over the frozen use tasks.
    3. A shape the fine table does not cover falls back to `by_template`:
       the same measurement aggregated over the template name alone. Two
       of the study's eighteen use tasks return a same-size candidate
       under both strategies, so the fine table has no honest row for
       them, and the template-level table is a measurement rather than a
       guess. Which level answered is named in `evidence_refs`.
    4. A family whose members are all scoped but which neither table
       covers is a refusal. The tables are finite and the rules that made
       them were measured, so a task outside the measurement is not
       answered by inventing an answer for it.

    Every admitted action's `evidence_refs` names the rule that fired, the
    shape it read, and the scope of every member that was not picked. A
    reader can reconstruct the decision from the record without executing
    the policy.

    This refuses rather than falling back to position. That is the bug
    `28c3e65` fixed, and it is not reintroduced here: `eligible[0]` is
    never read, and a refusal is still a refusal.
    """
    by_family: dict = {}
    for entry in eligible(repertoire):
        capability_id = entry["capability_id"]
        family = entry.get("family")
        if isinstance(family, str) and family:
            by_family.setdefault(family, []).append(capability_id)
    measured = _measure(repertoire) if features is None else {
        "shape": dict(features),
        "template": dict(coarse or {}),
    }
    if coarse is not None and features is None:
        measured["template"] = dict(coarse)
    scoped = {family: {key: capability_id
                       for key, capability_id in rows.items()
                       if capability_id in by_family.get(family, [])}
              for family, rows in measured["shape"].items()}
    if not by_family and not scoped:
        return ""
    return "\n".join([
        "def STEP(view, state):",
        "    by_family = %s" % json.dumps(
            {f: sorted(ids) for f, ids in sorted(by_family.items())},
            sort_keys=True),
        "    by_shape = %s" % json.dumps(
            {f: dict(sorted(rows.items()))
             for f, rows in sorted(scoped.items())}, sort_keys=True),
        "    by_template = %s" % json.dumps(
            {f: dict(sorted(rows.items()))
             for f, rows in sorted(measured["template"].items())},
            sort_keys=True),
        "    eligible = list(view.get('eligible_methods') or [])",
        "    task = dict(view.get('task_content') or {})",
        "    family = task.get('family')",
        "    named = list(by_family.get(family) or [])",
        "    if not named:",
        "        raise ValueError(",
        "            'no repertoire member is scoped to %r' % (family,))",
        "    if len(named) == 1:",
        "        picked = named[0]",
        "        rule = 'sole-member'",
        "        feature = 'n/a'",
        "    else:",
        "        table = by_shape.get(family) or {}",
        "        template = task.get('template')",
        "        if not isinstance(template, str) or not template:",
        "            template = 'unshaped'",
        "        key = 'template:%s' % template",
        "        for field, noun in (('ops', 'ops'),",
        "                          ('vertices', 'vertices')):",
        "            atoms = task.get(field)",
        "            if isinstance(atoms, list) and atoms:",
        "                edges = task.get('edges')",
        "                suffix = ('e%d' % len(edges)",
        "                          if isinstance(edges, list) and edges",
        "                          else '')",
        "                key = '%s|%s:%d%s' % (key, noun, len(atoms),",
        "                                       suffix)",
        "                break",
        "        picked = table.get(key)",
        "        rule = 'shape-table' if picked else 'template-table'",
        "        if picked is None:",
        "            picked = (by_template.get(family) or {}).get(",
        "                'template:%s' % template)",
        "        feature = key",
        "        if picked is None:",
        "            raise ValueError(",
        "                'no member of family %r is keyed to public shape'"
        " ' %r among %s' % (family, key, sorted(table)))",
        "    if picked not in eligible:",
        "        raise ValueError(",
        "            'selected %r is not among the eligible methods'",
        "            % (picked,))",
        "    why = ['family=%s' % (family,),",
        "           'rule=%s' % (rule,),",
        "           'feature=%s' % (feature,),",
        "           'scope[%s]=%s' % (picked, family)]",
        "    for other in sorted(named):",
        "        if other != picked:",
        "            why.append('not-picked[%s]=%s'",
        "                       % (other, family))",
        "    return {'action': {'kind': 'use_method',",
        "                     'target': task['task_id'],",
        "                     'inputs': {'method_id': picked,",
        "                                'max_queries': %d}," % BUDGET,
        "                     'evidence_refs': why,",
        "                     'requested_resources': {'queries': %d}},"
        % BUDGET,
        "            'state': {'picked': picked, 'why': why}}\n"])


def _measure(repertoire: dict) -> dict:
    """Both feature tables, from one pass over the frozen use tasks.

    For every public task shape in the frozen worlds, both members of the
    family run at `BUDGET` and the shape is keyed to whichever strategy
    produced the smaller candidate. This is the basis the selector uses in
    place of list position, and it is measured from the world rather than
    from an opinion about which strategy is usually better.

    Two levels come out of the same pass. `shape` is keyed on template
    name plus public atom counts; `template` is keyed on the template name
    alone. A shape the two members do not separate on is omitted from the
    fine table rather than keyed, because keying it would assert a choice
    the world declined to make, and the template-level table is where such
    a task is answered instead.

    The tasks are loaded from the freeze and reduced in the host here, at
    study-build time, so no dispatch is spent building the table and the
    arm's own executions are the only ones that count against its budget.
    """
    from experiments.ad01 import packet, worlds
    from experiments.representation import checkers, reducers

    members = {m["capability_id"]: m
               for m in (repertoire.get("members") or [])}
    by_family: dict = {}
    for member in members.values():
        family = (member.get("scope") or {}).get("family")
        if family:
            by_family.setdefault(family, {})[
                member.get("strategy")] = member["capability_id"]
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    shape: dict = {}
    coarse: dict = {}
    coarse_tally: dict = {}
    for world in sorted(membership):
        kinds = membership[str(world)]
        for split in ("within", "transfer"):
            for family, reducer_name in sorted(_REDUCERS.items()):
                strategies = by_family.get(family) or {}
                if len(strategies) < 2:
                    continue
                for task_id in kinds[split][family]:
                    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                    sizes = {}
                    for strategy, capability_id in strategies.items():
                        oracle = (checkers.SoftwareOracle(
                            task, max_queries=BUDGET) if family == "software"
                            else checkers.GraphOracle(
                                task, max_queries=BUDGET))
                        reducer = getattr(reducers, reducer_name)
                        result = reducer(task, oracle, method=strategy,
                                         max_queries=BUDGET)
                        candidate = result["candidate"]
                        sizes[capability_id] = len(
                            candidate.get("ops") if family == "software"
                            else candidate.get("vertices") or [])
                    if len(set(sizes.values())) < 2:
                        continue
                    winner = min(sorted(sizes), key=lambda cid: sizes[cid])
                    view = packet.strip_task(task)
                    shape.setdefault(family, {})[
                        _feature_key(view)] = winner
                    template = "template:%s" % view.get("template")
                    tally = coarse_tally.setdefault(
                        (family, template), Counter())
                    tally[winner] += 1
    for (family, template), tally in coarse_tally.items():
        top = tally.most_common()
        if top and (len(top) < 2 or top[0][1] > top[1][1]):
            coarse.setdefault(family, {})[template] = top[0][0]
    return {"shape": shape, "template": coarse}


def measured_tables(repertoire: dict) -> dict:
    """The two feature tables, measured once and reusable."""
    return _measure(repertoire)


# ---------------------------------------------------------------------------
# the budget
# ---------------------------------------------------------------------------


def control_tasks(world: int) -> list:
    """The tasks the control arm runs, which are the acquired arm's tasks.

    The two arms must be paired on the same task ids or the comparison is
    not one, so this is the study's own `_use_tasks` reached through the
    freeze rather than a second list that could drift from it.
    """
    from experiments.ad01 import trajectory
    membership = trajectory.worlds.world_membership(
        trajectory.worlds.FROZEN_DIR)
    kinds = membership[str(world)]
    tasks = []
    for domain in ("software", "graph"):
        tasks.extend(kinds["within"][domain][:2])
        tasks.extend(kinds["transfer"][domain][:1])
    return tasks


def arm_budget(worlds_, *, per_task_queries: int = BUDGET,
               per_task_units: int = 111) -> dict:
    """What one arm's use phase costs over the worlds it runs.

    `witness_queries` is the per-task budget times the task count, which
    is what the member actually spends when it runs to its budget.
    `execution_units` is the study's own per-task sandbox charge, taken
    from the `need` the use loop already passes to `_v1_admit`, so the two
    stay the same number rather than drifting apart.
    """
    tasks = sum(len(control_tasks(world)) for world in worlds_)
    return {"tasks": tasks,
            "witness_queries": tasks * int(per_task_queries),
            "execution_units": tasks * int(per_task_units)}


def study_ceilings(arms: int = 2, *, worlds_=None, per_task_units: int = 111
                   ) -> dict:
    """The study-level ceiling, derived from the arms that run under it.

    The acquired side is what the current hard-coded 960/5328 were sized
    for; the control is one more arm of the same shape. A ceiling a study
    cannot spend is not a bound, so this is the sum over arms and a caller
    that runs a different number of arms passes that number.
    """
    if worlds_ is None:
        from scripts import inv01_study as study
        worlds_ = study._v1_use_worlds()
    one = arm_budget(worlds_, per_task_units=per_task_units)
    return {"arms": int(arms), "tasks_per_arm": one["tasks"],
            "max_witness_queries": one["witness_queries"] * int(arms),
            "max_execution_units": one["execution_units"] * int(arms)}


# ---------------------------------------------------------------------------
# the freeze block
# ---------------------------------------------------------------------------


def policy_identities(arm: str, repertoire: dict) -> dict:
    """The freeze entry the verdict layer reads an arm through.

    `s09_verdict.Bundle.arm_origin` reads
    `freeze["policy_identities"][arm]["artifact"]["origin"]`, and
    `task_utility_verdict` needs at least one arm on each of
    `model-acquired` and `authored-control` before it will compare
    anything. `arm_policy_digest` reads the sibling `source_digest`, and
    `_comparability_leg` holds the arm to it: every `executed_source` a
    record carries must hash to the digest the freeze bound. So the digest
    here is over the member source that will actually execute, and the
    study writes the per-member digests as the arm's own.
    """
    members = [m for m in (repertoire.get("members") or [])]
    source = "".join(m.get("method_source") or "" for m in members)
    return {
        arm: {
            "artifact": {
                "kind": "method-repertoire",
                "origin": ORIGIN_AUTHORED,
                "entry": "ENTRY",
                "members": [m["capability_id"] for m in members],
                "applicability": {
                    "families": sorted({
                        (m.get("scope") or {}).get("family", "")
                        for m in members if m.get("scope")}),
                },
            },
            "source_digest": hashlib.sha256(source.encode(
                "utf-8")).hexdigest(),
            "member_digests": {m["capability_id"]: m["source_digest"]
                               for m in members},
        }
    }


def acquisition_identity(arm: str, member_ids: list, digests: dict, *,
                         acquisition_evidence: dict | None = None) -> dict:
    """The same block for the acquired arm, with the digest the run bound.

    The verdict layer refuses a comparison whose arms did not execute their
    own bound policy, so the acquired arm's entry is keyed to the digest of
    the bytes its records actually carried rather than to a digest of the
    repertoire file.

    There is no `origin` key unless the caller hands over the evidence that
    earned one. This function is given member ids and digests, so it can see
    nothing about who wrote the bytes, and a member record with no `origin`
    field is the honest description of that. It used to write
    `model-acquired` unconditionally, which is how a recording double's
    authored constant reached a freeze as a model's. The verdict layer reads
    a missing origin as unknown rather than as acquired, so an arm that
    cannot show a receipt cannot be compared as though it had.
    """
    artifact = {
        "kind": "method-repertoire",
        "entry": "ENTRY",
        "members": list(member_ids),
        "applicability": {"families": []},
    }
    if isinstance(acquisition_evidence, dict) \
            and acquisition_evidence.get("earned") is True:
        artifact["origin"] = "model-acquired"
    return {
        arm: {
            "artifact": artifact,
            "source_digest": hashlib.sha256(json.dumps(
                sorted(digests.items()), sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest(),
            "member_digests": dict(digests),
        }
    }
