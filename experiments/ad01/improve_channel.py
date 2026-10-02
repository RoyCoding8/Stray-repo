"""M2 inherited improvement behavior through the action interface.

Operational and improvement behavior share one executable package: two
STEP sources under one manifest digest. The improvement entry controls
later acquisition, construction and selection by returning probe,
construct and select actions that the driver executes through real
instruments. Menu selection and prompt advice are not involved.

Two authored controls share their operational bytes and differ in their
improvement bytes. Under matched inputs they request different real
probes. Both stay labeled and never enter acquired treatment arms.
Leaf construction maps a construct request to a revised package whose
improvement source follows the requested strategy. Adoption binds at a
quiescent boundary with reset private state and explicit retained
evidence plus obligations.

Bounded revision sits below. A revision may change which diagnostic
evidence the learner gathers, and only that. Eligibility, the descendant
metric, the immutability freeze and the three apparatus controls are all
decided here, and the channel's own reachable range is reported so a
study can be told before it is run that the decision has no headroom.
"""

from __future__ import annotations

import ast
import json
import statistics
import sys

from . import boolean_rule as _boolean_rule
from . import frontier as _frontier
from . import method_exec as _method_exec

CHANNEL_VERSION = "invl02-improve-v1"

ORIGIN = "authored-control"

CONTROL_LOW_ID = "authored-control-low-01"
CONTROL_HIGH_ID = "authored-control-high-01"

IMPROVE_KINDS = ("probe", "construct", "select", "wait", "stop")

SHARED_OPERATE_SOURCE = """def STEP(view, state):
    frontier = view["frontier"]
    exp = view["experience"]
    rounds = state.get("rounds", 0)
    if not frontier:
        inner = {"kind": "stop",
                 "inputs": {"reason": "no admissible work"},
                 "requested_resources": {}}
        target = "open"
        outer = "stop"
    else:
        last = exp[-1] if exp else None
        if last is not None and last.get("verdict") == "mismatch":
            alt = [o for o in frontier
                   if o.get("task") != last.get("task")]
            choice = alt[0] if alt else frontier[0]
        else:
            choice = frontier[0]
        inner = {"kind": "investigate",
                 "inputs": {"opportunity_id":
                            choice["opportunity_id"]},
                 "requested_resources": {"steps": 1}}
        target = choice["opportunity_id"]
        outer = "diagnose"
    action = {"kind": outer, "target": target,
              "inputs": {"frontier_action": inner},
              "evidence_refs": [],
              "requested_resources": inner["requested_resources"]}
    return {"action": action,
            "state": {"rounds": rounds,
                      "last_choice": target}}
"""

IMPROVE_LOW_SOURCE = """def STEP(view, state):
    step = state.get("step", 0)
    if step == 0:
        inner = {"kind": "probe", "inputs": {"x": 3},
                 "requested_resources": {"queries": 1, "steps": 1}}
        state = {"step": 1}
    else:
        exp = view["experience"]
        if not exp:
            inner = {"kind": "wait",
                     "inputs": {"reason": "probe left no observation"},
                     "requested_resources": {}}
            state = {"step": 1}
        else:
            first = exp[-1].get("y", [0, 0, 0, 0])
            strategy = "high" if first[0] == 1 else "low"
            inner = {"kind": "construct",
                     "inputs": {"strategy": strategy},
                     "requested_resources": {"steps": 1}}
            state = {"step": 2, "strategy": strategy}
    action = {"kind": "diagnose", "target": "rule-improve",
              "inputs": {"frontier_action": inner},
              "evidence_refs": [],
              "requested_resources": inner["requested_resources"]}
    return {"action": action, "state": state}
"""

IMPROVE_HIGH_SOURCE = """def STEP(view, state):
    step = state.get("step", 0)
    if step == 0:
        inner = {"kind": "probe", "inputs": {"x": 11},
                 "requested_resources": {"queries": 1, "steps": 1}}
        state = {"step": 1}
    else:
        exp = view["experience"]
        if not exp:
            inner = {"kind": "wait",
                     "inputs": {"reason": "probe left no observation"},
                     "requested_resources": {}}
            state = {"step": 1}
        else:
            first = exp[-1].get("y", [0, 0, 0, 0])
            strategy = "high" if first[0] == 1 else "low"
            inner = {"kind": "construct",
                     "inputs": {"strategy": strategy},
                     "requested_resources": {"steps": 1}}
            state = {"step": 2, "strategy": strategy}
    action = {"kind": "diagnose", "target": "rule-improve",
              "inputs": {"frontier_action": inner},
              "evidence_refs": [],
              "requested_resources": inner["requested_resources"]}
    return {"action": action, "state": state}
"""

_CONTROLS = {
    "low": (CONTROL_LOW_ID, IMPROVE_LOW_SOURCE),
    "high": (CONTROL_HIGH_ID, IMPROVE_HIGH_SOURCE),
}

_STRATEGY_SOURCE = {"low": IMPROVE_LOW_SOURCE, "high": IMPROVE_HIGH_SOURCE}

REVISION_VERSION = "invl02-revision-v1"


def _revision_source(probe) -> str:
    """Build a revision around one evidence-selection rule.

    Takes the authored control as the template and rewrites only the input
    it probes, so a revision differs from the incumbent at exactly the
    decision under study and nowhere else. A difference in the descendant
    is then attributable to the evidence choice by construction.

    Both authored inputs are offered, so a revision can select either one
    of the two the control family uses, not just the one this template
    happens to start from.
    """
    for template in (IMPROVE_LOW_SOURCE, IMPROVE_HIGH_SOURCE):
        for literal in ("3", "11"):
            anchor = '"x": %s' % literal
            if anchor not in template:
                continue
            candidate = template.replace(anchor, '"x": %s' % probe, 1)
            if candidate != template:
                return candidate
    raise _frontier.Refused("control template has no probe input to"
                            " substitute")


# The intervention boundary. A learner already decides which diagnostic
# evidence to gather: `imp_source` emits `{"kind": "probe", "inputs":
# {"x": ...}}`, `drive_improve_round` spends that input against a real
# instrument, and `leaf_construct` builds the descendant package from the
# observed output. That decision is the boundary, because the probed x is
# read back out of the observation to choose the descendant strategy.
# What a revision may change is exactly that x.
DECISION = "diagnostic-evidence-selection"

# Fields the trusted authority owns. A revision reads the remaining
# budget and never writes these; a store that carried the counters itself
# is what makes the freeze a property rather than a promise.
FROZEN_FIELDS = ("grant", "used", "authority", "evaluator", "sealed_results",
                 "execution_limits")

EVALUATOR_ID = "invl02-frozen-version-space-v1"

EXECUTION_LIMITS = {
    "max_queries": 8,
    "max_policy_steps": 6,
    "step_timeout_ms": 10_000,
    "step_cpu_seconds": 10,
    "step_max_output_bytes": 65_536,
}

ELIGIBLE = "eligible"
INELIGIBLE_PROSE = "prose-recommendation"
INELIGIBLE_NO_BOUNDARY = "no-boundary-action"
INELIGIBLE_SOLVER = "task-solver-not-decision"
INELIGIBLE_DELEGATION = "delegates-to-unchanged-reducer"
INELIGIBLE_FROZEN_WRITE = "mutates-frozen-field"
INELIGIBILITY_REASONS = (
    INELIGIBLE_PROSE, INELIGIBLE_NO_BOUNDARY, INELIGIBLE_SOLVER,
    INELIGIBLE_DELEGATION, INELIGIBLE_FROZEN_WRITE)


def revision_evidence_choices(source: str, view: dict) -> list:
    """Execute revision bytes under one view and read back its choices.

    The revision is a STEP source, so the only honest way to know which
    evidence it selects is to execute it. Scanning the text for a literal
    would miss a computed x, and a computed x is exactly the case that
    decides the improvement.
    """
    chosen: list = []
    state: dict = {}
    working = dict(view)
    for _ in range(int(EXECUTION_LIMITS["max_policy_steps"])):
        try:
            stepped = _run_source(source, working, state)
        except Exception:
            break
        action = stepped.get("action")
        state = stepped.get("state") or {}
        if not isinstance(action, dict):
            break
        inner = action
        if isinstance(action.get("inputs"), dict) and "frontier_action" in \
                action["inputs"]:
            inner = action["inputs"]["frontier_action"]
        if not isinstance(inner, dict):
            break
        kind = inner.get("kind")
        if kind == "probe":
            x = (inner.get("inputs") or {}).get("x")
            if type(x) is int:
                chosen.append(x)
        if kind in ("construct", "select", "wait", "stop"):
            break
        working = dict(working)
        working["experience"] = list(working.get("experience") or [])
    return chosen


def _emits_probe(source: str) -> bool:
    """True when the revision's own bytes can emit a probe action.

    A revision that never emits a probe never selects diagnostic evidence,
    so it cannot change what the learner observes and cannot change any
    descendant. That is a property of the bytes, decided by parsing them
    rather than by running them and hoping.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value == "probe":
                    return True
        if isinstance(node, ast.Constant) and node.value == "probe":
            return True
    return False


def _probe_x_expression(source: str) -> list:
    """Every expression the bytes bind to a probe's `x`, however bound.

    The control template writes the input inline in the probe dict, and a
    revision may bind it to a name first and use the name. Both are the
    decision under study, so both are collected.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return []
    bound: dict = {}
    expressions: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound[target.id] = node.value
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "x":
                    expressions.append(value)
    resolved: list = []
    for expression in expressions:
        seen: set = set()
        while isinstance(expression, ast.Name) \
                and expression.id in bound \
                and expression.id not in seen:
            seen.add(expression.id)
            expression = bound[expression.id]
        resolved.append(expression)
    return resolved


def _x_is_data_dependent(source: str) -> bool:
    """True when the probed input can vary with what the learner has seen.

    A revision that returns the same x under every view is not choosing
    what to observe. This asks the structural question, because the
    interesting case computes x from the view.
    """
    view_names = frozenset(("view", "state", "exp", "experience", "obs",
                            "observations"))
    for expression in _probe_x_expression(source):
        if not isinstance(expression, ast.Constant) and _reads_names(
                expression, view_names):
            return True
    return False


def _reads_names(node, names: frozenset) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in names:
            return True
    return False


def _incumbent_choices(view: dict) -> list:
    """What the unchanged frozen reducer chooses under the same view.

    `rule_learner.VersionSpaceLearner.choose_query` is the incumbent
    evidence selector. It searches every unqueried input, so it does not
    consult the frontier and neither does this. It breaks ties with its own
    seeded RNG, so the sequence is reproduced by driving the real learner
    rather than by recomputing the argmax; recomputing it would compare a
    revision against a tie-break it never had.
    """
    from . import boolean_rule as _rules
    from . import rule_learner as _reducer
    learner = _reducer.VersionSpaceLearner(_rules.CLASS_TABLES, 0)
    observed: set = set()
    chosen: list = []
    for _ in range(_rules.MAX_QUERIES):
        pick = learner.choose_query(
            {x: (0,) * _rules.N_OUTPUTS for x in observed})
        if pick is None:
            break
        chosen.append(pick)
        observed.add(pick)
    return chosen


def _reducer_argmax(view: dict) -> list:
    """The reducer's best-disagreement inputs, ignoring its tie-break.

    A revision that picks the best-disagreement input is delegating to the
    frozen reducer's rule even when it breaks the tie differently, so the
    delegation check accepts a choice drawn from this set.
    """
    from . import boolean_rule as _rules
    from . import rule_learner as _reducer
    learner = _reducer.VersionSpaceLearner(_rules.CLASS_TABLES, 0)
    observed: set = set()
    chosen: list = []
    for _ in range(_rules.MAX_QUERIES):
        scored = [(learner._disagreement(x), x) for x in range(_rules.N_STATES)
                  if x not in observed]
        if not scored:
            break
        best = max(score for score, _ in scored)
        chosen.append(sorted(x for score, x in scored if score == best)[0])
        observed.update(
            x for score, x in scored if score == best)
    return chosen


def delegates_to_frozen_reducer(source: str, view: dict) -> bool:
    """True when the revision's choice is the frozen reducer's own.

    Measured by execution, because the only way to know what a computed x
    evaluates to is to run it under the same view the reducer sees. A
    revision is a delegation when every input it picks is one the reducer
    would also have ranked first, so a different tie-break does not read
    as a different decision.
    """
    choices = revision_evidence_choices(source, view)
    if not choices:
        return False
    for rule in (_incumbent_choices, _reducer_argmax):
        reference = rule(view)[:len(choices)]
        if choices == reference:
            return True
    return all(
        x in _reducer_argmax(view) for x in choices)


def classify_revision(source: str, views: list) -> dict:
    """Decide whether revision bytes are an eligible intervention.

    Eligibility is a property of the bytes and the boundary they reach,
    decided before the revision is ever measured, so an ineligible
    revision is refused rather than scored. `views` is a list of
    genuinely different learner views.

    Eligibility is therefore not a claim that the bytes ran.
    `informs_decision` is that separate claim, and it is derived from
    `selected_evidence` rather than declared. `revision_evidence_choices`
    swallows every exception the step raises and returns an empty list, so
    a revision that never executes is admitted on the strength of its
    static shape having selected nothing. Reporting that as a decision
    would be the verdict asserting a measurement it never made.
    """
    if not isinstance(source, str) or not source.strip():
        return _refused(INELIGIBLE_PROSE,
                        "revision holds no executable bytes")
    try:
        from . import method_exec as _exec
        _exec.verify_step_source(source, "STEP")
    except Exception as exc:
        return _refused(INELIGIBLE_PROSE,
                        "revision is not executable STEP: %s" % exc)
    if not views:
        return _refused(INELIGIBLE_NO_BOUNDARY,
                        "eligibility needs at least one learner view")
    if not _emits_probe(source):
        return _refused(INELIGIBLE_NO_BOUNDARY,
                        "revision never selects diagnostic evidence")
    if not _x_is_data_dependent(source):
        return _refused(INELIGIBLE_SOLVER,
                        "revision picks a fixed input whatever the learner"
                        " has seen, so it answers the task instead of"
                        " choosing what to observe")
    if all(delegates_to_frozen_reducer(source, view) for view in views):
        return _refused(INELIGIBLE_DELEGATION,
                        "revision reproduces the frozen reducer's choice")
    selected = [revision_evidence_choices(source, view) for view in views]
    return {"eligibility": ELIGIBLE, "decision": DECISION,
            "selected_evidence": selected,
            "informs_decision": bool(selected) and all(selected)}


def _refused(reason: str, detail: str) -> dict:
    return {"eligibility": reason, "decision": DECISION, "reason": detail}


def frozen_state(store) -> dict:
    """The trusted state a revision must not be able to write."""
    return {"grant": dict(store._doc["grant"]),
            "used": dict(store._doc["used"]),
            "authority": dict(store.authority),
            "evaluator": EVALUATOR_ID,
            "sealed_results": list(store._doc.get("sealed_results") or []),
            "execution_limits": dict(EXECUTION_LIMITS)}


# --- descendant evaluation ------------------------------------------------
#
# The reviser's own task score is the score of the improve round. The
# improvement claim is about what the packages that round produces, run on
# a fresh cohort they never saw. So the descendant evaluator is separate
# from the reviser by construction: it takes the evidence a revision chose
# and runs the frozen reducer over it on unseen tasks.
#
# The evidence a descendant actually runs is not the evidence the reviser
# gathered. `leaf_construct` replaces the improvement source with a member
# of the authored menu, so a descendant probes the menu's input, not the
# one the revision selected. Scoring the reviser's evidence here would
# measure an improvement no descendant ever receives.

GENERAL_POSITION = (0, 1, 2, 4, 8)


def _menu_probe(source: str) -> int:
    """The input a menu member probes, read out of its own bytes."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        raise _frontier.Refused("menu source is unparseable")
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "x" \
                        and isinstance(value, ast.Constant) \
                        and type(value.value) is int:
                    return value.value
    raise _frontier.Refused("menu source selects no probe input")


# The evidence each menu member gathers, parsed from the menu itself so
# this cannot drift from what `leaf_construct` actually installs.
_STRATEGY_EVIDENCE = {
    "low": _menu_probe(_STRATEGY_SOURCE["low"]),
    "high": _menu_probe(_STRATEGY_SOURCE["high"]),
}

# What a descendant can run, derived from the menu rather than restated.
# The development probe decides which member it gets, and nothing else
# about the revision survives into the descendant.
REACHABLE_EVIDENCE = tuple(
    str(x) for x in sorted(set(_STRATEGY_EVIDENCE.values())))

# The evidence the incumbent gathers, and the two inputs the authored
# menu can install. Both were literals at the two places that used them;
# they are named once so the estimator and the menu cannot disagree about
# what the channel can reach.
INCUMBENT_EVIDENCE = (3,)

MENU_EVIDENCE = tuple(int(x) for x in REACHABLE_EVIDENCE)

_N_INPUTS = 16

# Named so a report carrying a headroom number says which estimator
# produced it. The string changes if the estimator is ever rebuilt again.
ESTIMATOR = "paired best-reachable vs incumbent"


def descendant_score(evidence: list, split: str, seed: int) -> dict:
    """Score one descendant on one unseen task under the frozen evaluator.

    The evaluator never sees the revision. It receives the evidence the
    revision chose and the task, runs the unchanged version-space reducer,
    commits, and returns the instrument's own split-aware score.

    An input the instrument refuses contributes nothing, exactly as it
    would in a run. Refusing to crash is the point: a revision that names
    an unprobeable input is causally disconnected, and the run must
    continue and score the descendant on what it actually learned.
    """
    from . import boolean_rule as _rules
    from . import rule_learner as _reducer
    task = _rules.make_task(split, int(seed))
    session = _rules.RuleSession(task)
    learner = _reducer.VersionSpaceLearner(_rules.CLASS_TABLES, int(seed))
    refused = 0
    for x in evidence:
        try:
            learner.observe(x, session.query(x))
        except _rules.RuleRefused:
            refused += 1
    committed = session.commit_predictor(learner.predict(dict(
        session.queried)))
    result = session.score(committed)
    result["refused_inputs"] = refused
    result["learned_inputs"] = len(session.queried)
    return result


def evaluate_descendants(evidence: list, *, split: str,
                         seeds: list) -> dict:
    """The descendant metric: mean unqueried-input accuracy over the cohort.

    `unqueried` is the frozen rule. A reviser can look good on the inputs
    it probed and leave the rest of the instrument untouched, and the
    reviser's own score does not see that difference.
    """
    if not seeds:
        return {"mean": None, "n": 0, "split": split,
                "evidence": list(evidence)}
    scores = [descendant_score(list(evidence), split, seed) for seed in seeds]
    return {
        "split": split,
        "n": len(seeds),
        "evidence": list(evidence),
        "mean": sum(s["unqueried"] for s in scores) / len(scores),
        "queried_mean": sum(s["queried"] for s in scores) / len(scores),
        "overall_mean": sum(s["overall"] for s in scores) / len(scores),
    }


def _strategy_descendant(strategy: str, split: str, seed: int) -> dict:
    """Score the descendant one authored menu strategy builds.

    Split out from `lineage_descendant_score` so the evidence a strategy
    produces is named separately from the bit that selects it. The
    selection is the decision under study; what the menu then gathers is
    the substrate, and the two have to be replaceable apart.
    """
    return descendant_score([_STRATEGY_EVIDENCE[strategy]], split, int(seed))


def lineage_descendant_score(development_probe: int, split: str,
                             seed: int) -> dict:
    """Score one descendant on the path the code actually builds.

    `drive_improve_round` probes, reads output bit 0, and hands that bit to
    `leaf_construct`, which swaps in a member of the authored menu. So the
    descendant runs the menu's evidence, chosen by the development probe,
    and the frozen reducer sees only what the descendant gathers. Scoring
    the development probe's own evidence here would credit the descendant
    with evidence it never received.
    """
    from . import boolean_rule as _rules
    task = _rules.make_task(split, int(seed))
    bit = (task["tables"][0] >> int(development_probe)) & 1
    strategy = "high" if bit == 1 else "low"
    return _strategy_descendant(strategy, split, int(seed))


def evaluate_lineage(probes: list, *, split: str, seeds: list) -> dict:
    """The descendant metric over the reachable path.

    `probes` are the development inputs a revision chooses; the metric is
    what the descendants those choices produce achieve on the cohort.
    """
    if not seeds or not probes:
        return {"mean": None, "n": 0, "split": split,
                "probes": list(probes)}
    scores = [lineage_descendant_score(int(p), split, seed)
              for seed in seeds for p in probes]
    return {
        "split": split,
        "n": len(seeds) * len(probes),
        "probes": list(probes),
        "mean": sum(s["unqueried"] for s in scores) / len(scores),
        "overall_mean": sum(s["overall"] for s in scores) / len(scores),
    }


def reachable_lineage_spread(*, split: str, seeds: list) -> dict:
    """The whole descendant range a revision can possibly reach.

    If the best and worst reachable descendants are this close, then no
    revision of this decision can be said to improve anything, and that is
    a property of the channel rather than a property of any run.
    """
    best = None
    worst = None
    for probe in range(16):
        result = evaluate_lineage([probe], split=split, seeds=seeds)
        if best is None or result["mean"] > best[1]:
            best = (probe, result["mean"])
        if worst is None or result["mean"] < worst[1]:
            worst = (probe, result["mean"])
    return {"best_probe": best[0], "best": best[1],
            "worst_probe": worst[0], "worst": worst[1],
            "spread": best[1] - worst[1],
            "split": split, "n": len(seeds)}


def noise_floor(*, split: str, seeds: list) -> dict:
    """The same spread, measured between halves of one cohort.

    A signal smaller than this is not a signal. Splitting the cohort in
    two and recomputing the reachable range gives the spread produced by
    sampling alone, with no difference in the decision at all. Comparing
    the two is what lets a null result be reported as a null result
    instead of as a small number someone might quote.
    """
    first = seeds[0::2]
    second = seeds[1::2]
    a = reachable_lineage_spread(split=split, seeds=first)
    b = reachable_lineage_spread(split=split, seeds=second)
    return {"resample_spread": max(a["spread"], b["spread"]),
            "best_probe_agrees": a["best_probe"] == b["best_probe"],
            "half_a": a, "half_b": b,
            "split": split, "n": len(seeds)}


def channel_headroom(*, split: str, seeds: list,
                     incumbent_evidence: list = None) -> dict:
    """Whether this decision can show a descendant improvement at all.

    Headroom is the best descendant a revision can reach minus the
    incumbent, measured as a paired difference over one cohort. The
    previous version compared `reachable_lineage_spread` over the whole
    cohort against `noise_floor` over halves of it, and a spread measured
    on n/2 samples is structurally larger than a spread measured on n, so
    that difference was negative at every cohort size whatever the
    substrate was doing. It reported the estimator's own sample sizes.

    Two things are deliberately not done here, because either one would
    produce a number rather than a measurement. The best probe is chosen
    on one half of the cohort and scored against the incumbent on the
    other, so a channel with any range at all is not reported as
    measurable by its own argmax. And the incumbent is the evidence the
    authored control gathers, which is what a revision is actually
    compared against in an E4 round; the reachable pair of menu inputs
    bounds the set of evidence the decision can express at all and is
    reported as `menu_mean`. The ceiling over every input the instrument
    accepts is a wider question, and `ceiling_over_inputs` answers it.

    A flag that cannot be true is not a measurement either, so two
    guards here are required for `measurable` to be true: the best probe
    has to beat the incumbent, and the gap has to exceed its own standard
    error, or `measurable` would be reading a cohort that has converged
    as a direction. A caller that wants the raw magnitude without either
    of them has `delta` and `paired_se` here. The second guard is what
    stops the second from being free: a channel with a real effect has a
    positive standard error, so the flag stays available to a planted
    one, which `tests/test_s09_e4_remediation.py` requires it to find.

    A third guard was tried and removed. The incumbent is always a member
    of the menu, so the best of the sixteen inputs is at least as good as
    the menu, which is at least as good as the incumbent. A "must beat the
    menu" condition is therefore unreachable by construction, and a guard
    that cannot refuse is not a guard. The menu mean is reported anyway,
    because it is the number a reader wants, but it does not gate
    anything.
    """
    seeds = list(seeds)
    incumbent_evidence = list(INCUMBENT_EVIDENCE if incumbent_evidence is None
                              else incumbent_evidence)
    if not seeds:
        return {"estimator": ESTIMATOR, "half_cohort_comparison": False,
                "delta": None, "paired_se": None, "paired_sd": None,
                "z": None, "measurable": False, "selection_biased": False,
                "incumbent_mean": None, "menu_mean": None,
                "incumbent_evidence": incumbent_evidence,
                "best_probe": None, "best_mean": None,
                "best_beats_incumbent": False,
                "split_half": {"select": {"n": 0, "seeds": []},
                               "score": {"n": 0, "seeds": []}},
                "split": split, "n": 0,
                "reachable_evidence": list(REACHABLE_EVIDENCE)}
    select, score = seeds[0::2], seeds[1::2]
    select_means = {p: evaluate_lineage([p], split=split,
                                        seeds=select)["mean"]
                    for p in range(_N_INPUTS)}
    best_probe = max(sorted(select_means), key=select_means.get)
    best_scores = [lineage_descendant_score(best_probe, split, seed)
                   for seed in score]
    incumbent_scores = [descendant_score(incumbent_evidence, split, seed)
                        for seed in score]
    paired = [b["unqueried"] - i["unqueried"]
              for b, i in zip(best_scores, incumbent_scores)]
    n = len(paired)
    delta = sum(paired) / n
    sd = statistics.pstdev(paired) if n > 1 else 0.0
    se = sd / n ** 0.5 if n else 0.0
    incumbent_mean = sum(s["unqueried"] for s in incumbent_scores) / n
    best_mean = sum(b["unqueried"] for b in best_scores) / n
    # The mean over the two evidence sets the authored menu can install,
    # which is the whole range the decision is able to express however the
    # revision chose its probe. Reported because it is the number a reader
    # wants next to the best-probe mean. It gates nothing; see the docstring
    # for why a "must beat the menu" condition could not refuse anything.
    menu = evaluate_lineage(list(MENU_EVIDENCE), split=split,
                            seeds=seeds)["mean"]
    return {
        "estimator": ESTIMATOR,
        "half_cohort_comparison": False,
        "delta": delta,
        "paired_se": se,
        "paired_sd": sd,
        "z": (delta / se) if se else None,
        "measurable": (delta > 0.0 and (se == 0.0 or abs(delta) > se)),
        "selection_biased": False,
        "incumbent_mean": incumbent_mean,
        "menu_mean": menu,
        "incumbent_evidence": incumbent_evidence,
        "best_probe": best_probe,
        "best_mean": best_mean,
        "best_beats_incumbent": best_mean > incumbent_mean,
        "split_half": {
            "select": {"n": len(select), "seeds": select},
            "score": {"n": len(score), "seeds": score},
        },
        "split": split, "n": len(seeds),
        "reachable_evidence": list(REACHABLE_EVIDENCE),
    }


def ceiling_over_inputs(*, split: str, seeds: list) -> dict:
    """The range over every input the instrument accepts, not the menu.

    `reachable_lineage_spread` bounds what a revision of this decision
    can reach, because `leaf_construct` installs one of two authored
    improvement sources. This bounds the substrate instead, so "the menu
    is too narrow" and "the decision has no range" can be told apart. A
    revision's only lever is choosing a better probe, so this is the
    ceiling on any revision, and on any wider menu, of the same decision.
    """
    if not seeds:
        return {"spread": None, "best_probe": None, "worst_probe": None,
                "split": split, "n": 0}
    means = {p: evaluate_lineage([p], split=split,
                                 seeds=seeds)["mean"]
             for p in range(_N_INPUTS)}
    best = max(sorted(means), key=means.get)
    worst = min(sorted(means), key=means.get)
    return {"spread": means[best] - means[worst], "best_probe": best,
            "worst_probe": worst, "input_means": means,
            "split": split, "n": len(seeds)}


def reviser_own_score(observations: list) -> float:
    """The reviser's own round score, for contrast with the descendant.

    Reported so the two can disagree. A revision that raises this while
    leaving the descendant flat has not improved learning.
    """
    if not observations:
        return 0.0
    known = sum(1 for o in observations
                if all(bit in (0, 1) for bit in o.get("y", ())))
    return known / len(observations)


def descendant_delta(revised: dict, incumbent: dict) -> dict:
    """Signed difference under the frozen rule, with no effect as zero."""
    if revised.get("mean") is None or incumbent.get("mean") is None:
        return {"delta": None, "n": 0, "measured": False}
    return {"delta": revised["mean"] - incumbent["mean"],
            "n": min(revised["n"], incumbent["n"]),
            "measured": True,
            "rule": "unqueried-input accuracy, frozen evaluator"}


# --- immutability ---------------------------------------------------------
#
# The grant, the used-so-far counters, the evaluator identity, the sealed
# results and the execution limits live outside the revision. A revision is
# handed the remaining budget and nothing that writes it. A revision that
# tries to reach one is refused before it is measured, because accepting it
# would make every other measurement in this apparatus untrustworthy.

class FrozenFieldViolation(Exception):
    pass


def admit_revision_under_freeze(store, source: str, views: list) -> dict:
    """Admit revision bytes, or refuse, without letting them touch the seal.

    The frozen-write check runs first, ahead of every eligibility question.
    Ordering matters for a security property: a revision that also happens
    to be an ineligible solver must be reported for the frozen write, or
    the report hides the attempt behind a cheaper verdict.

    The frozen state is captured before the revision is executed at all and
    compared after, so a write that slips past the static check is still
    caught by the comparison rather than by trust.
    """
    before = frozen_state(store)
    if _attempts_frozen_write(source):
        return _refused(INELIGIBLE_FROZEN_WRITE,
                        "revision writes frozen authority state")
    verdict = classify_revision(source, views)
    if verdict.get("eligibility") != ELIGIBLE:
        return verdict
    after = frozen_state(store)
    if _frontier.canonical(before) != _frontier.canonical(after):
        raise FrozenFieldViolation("frozen state changed during admission")
    verdict["frozen_state_digest"] = _frontier.source_digest(
        _frontier.canonical(before))
    return verdict


def _attempts_frozen_write(source: str) -> bool:
    """True when the revision names a frozen field in a write position.

    Read access is legitimate: a learner reads the remaining budget to
    decide what it can still afford. A write is not, so the check is on
    the assignment target rather than on the name alone.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return False
    frozen = set(FROZEN_FIELDS)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if _targets_frozen(target, frozen):
                    return True
        if isinstance(node, ast.AugAssign) and _targets_frozen(
                node.target, frozen):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ("setattr", "delattr", "exec", "eval",
                                     "open"):
            return True
    return False


def _targets_frozen(node, frozen: set) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr in frozen or _targets_frozen(node.value, frozen)
    if isinstance(node, ast.Name):
        return node.id in frozen
    if isinstance(node, ast.Subscript):
        return _targets_frozen(node.value, frozen)
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_targets_frozen(item, frozen) for item in node.elts)
    return False


# --- qualification versus outcome ----------------------------------------
#
# Qualification asks whether the machinery can tell a real effect from
# noise. Outcome asks whether this run improved anything. They are stored
# apart and neither one can supply the other, so a failed run cannot
# retroactively unqualify the controls and a passing qualification cannot
# stand in for a benefit.

QUALIFIED = "apparatus-qualified"
UNQUALIFIED = "apparatus-unqualified"

CONTROL_ROLES = ("known-effect", "no-op", "disconnect")


def qualify_apparatus(controls: list) -> dict:
    """The qualification verdict, from the three mandatory controls alone.

    No run outcome is an input. A control that produced the wrong effect
    makes the apparatus untrustworthy regardless of how good any run was.
    """
    by_role = {c.get("role"): c for c in controls}
    checks: dict = {}
    for role in CONTROL_ROLES:
        control = by_role.get(role)
        checks[role] = {
            "present": control is not None,
            "passed": bool(control and control.get("as_expected")),
            "observed_delta": (None if control is None
                               else control.get("delta")),
        }
    passed = all(c["present"] and c["passed"] for c in checks.values())
    return {"qualification": QUALIFIED if passed else UNQUALIFIED,
            "qualified": passed,
            "checks": checks,
            "note": "qualification is a property of the machinery alone; it"
                    " says nothing about any run outcome"}


def benefit_outcome(delta: dict, acquisition: dict) -> dict:
    """The outcome verdict for one run, over an already-qualified apparatus.

    Qualification is not an input and cannot be inferred from here. A
    caller that has not qualified the apparatus is reading a number with
    nothing behind it, so the caller is the one that has to have done
    that work, and the two verdicts are stored apart.

    An improvement claim requires three things of the run itself: live
    attributable bytes, an eligible revision, and a positive descendant
    delta. A missing piece is reported as what it is, not as a failure.
    """
    blockers = []
    if not acquisition.get("eligible"):
        blockers.append("no eligible revision was acquired")
    if not acquisition.get("live_attributable"):
        blockers.append("no live-acquired attributable model bytes")
    if not delta.get("measured"):
        blockers.append("descendant metric was not measured")
    elif delta.get("delta") is None or delta["delta"] <= 0:
        blockers.append("descendants did not improve under the frozen rule")
    return {"benefit": not blockers,
            "blockers": blockers,
            "delta": delta.get("delta"),
            "scope": ("one successful generation supports bounded"
                      " meta-learning, not unrestricted recursive"
                      " self-improvement") if not blockers else None}


def make_control(which: str) -> dict:
    try:
        control_id, imp_source = _CONTROLS[which]
    except KeyError:
        raise _frontier.Refused("unknown authored control %r" % (which,))
    return {
        "control_id": control_id,
        "origin": ORIGIN,
        "source_kind": "fixed-menu",
        "op_source": SHARED_OPERATE_SOURCE,
        "imp_source": imp_source,
        "op_digest": _frontier.source_digest(SHARED_OPERATE_SOURCE),
        "imp_digest": _frontier.source_digest(imp_source),
        "package_digest": _frontier.package_digest(
            SHARED_OPERATE_SOURCE, imp_source, None, 0, control_id, None),
        "parent_digest": None,
        "provenance": None,
        "provenance_digest": None,
        "version": 0,
        "authority_request": {"queries": 16, "steps": 12},
        "obligations": ["re-test probe divergence on new seeds"],
        "channel": CHANNEL_VERSION,
    }


def validate_improve_action(action: dict) -> dict:
    if not isinstance(action, dict):
        raise _frontier.Refused("improve action must be an object")
    kind = action.get("kind")
    if kind not in IMPROVE_KINDS:
        raise _frontier.Refused("unknown improve action kind %r" % (kind,))
    inputs = action.get("inputs")
    if not isinstance(inputs, dict):
        raise _frontier.Refused("improve action inputs must be an object")
    if kind == "probe" and (not isinstance(inputs.get("x"), int)
                            or not 0 <= inputs["x"] < 16):
        raise _frontier.Refused("probe needs an input x in 0..15")
    if kind == "construct" and inputs.get("strategy") not in (
            "low", "high"):
        raise _frontier.Refused("construct needs a known strategy")
    if kind == "select" and not isinstance(
            inputs.get("candidate_id"), str):
        raise _frontier.Refused("select needs a candidate_id")
    resources = action.get("requested_resources")
    if not isinstance(resources, dict) or any(
            type(v) is not int or v < 0 for v in resources.values()):
        raise _frontier.Refused("improve action requested_resources must"
                                " hold nonnegative integers")
    return action


def _step_view(view: dict) -> dict:
    from . import policy_step as _policy_step
    remaining = dict(view.get("authority_remaining") or {})
    envelope = _policy_step.materialize_view(
        task={"family": "boolean",
              "task_id": (view["frontier"][0]["task"]
                          if view.get("frontier") else "open")},
        observations=list(view.get("experience") or []),
        open_questions=[],
        last_result=None,
        eligible_methods=[],
        remaining={"queries": int(remaining.get("queries", 0)),
                   "steps": int(remaining.get("steps", 0))})
    envelope.update(dict(view))
    return envelope


def _run_source(source: str, view: dict, state: dict, **evidence) -> dict:
    return _method_exec.run_step_out_of_process(
        source, _step_view(view), dict(state), **evidence)


def _unwrap(outer: dict) -> dict:
    if not isinstance(outer, dict) or not isinstance(
            outer.get("inputs"), dict) or "frontier_action" not in \
            outer["inputs"]:
        raise _frontier.Refused("STEP envelope holds no frontier action")
    return dict(outer["inputs"]["frontier_action"])


def run_operate_step(package: dict, view: dict, state: dict) -> dict:
    _frontier.validate_view(view)
    if view["purpose"] != _frontier.OPERATE:
        raise _frontier.Refused("operate runner got a %s view" % (
            view.get("purpose"),))
    stepped = _run_source(package["op_source"], view, state)
    action = _frontier.validate_operate_action(_unwrap(
        stepped["action"]))
    return {"action": action, "state": stepped["state"],
            "executed_digest": stepped["source_digest"]}


def run_improve_step(package: dict, view: dict, state: dict,
                     *, receipt_sink=None, **evidence) -> dict:
    _frontier.validate_view(view)
    if view["purpose"] != _frontier.IMPROVE:
        raise _frontier.Refused("improve runner got a %s view" % (
            view.get("purpose"),))
    stepped = _run_source(package["imp_source"], view, state, **evidence)
    action = validate_improve_action(_unwrap(stepped["action"]))
    result = {"action": action, "state": stepped["state"],
              "executed_digest": stepped["source_digest"],
              "receipt": stepped["receipt"]}
    if receipt_sink is not None:
        receipt_sink(result)
    return result


def _find_admitted_probe_effect(store, opportunity_id: str, x: int,
                                effect_identity: dict | None = None) -> tuple:
    active_package = store._validate_active_package()
    if active_package is None:
        raise _frontier.Refused("probe needs a bound program")
    active = active_package["package_digest"]
    opportunity = store._doc["opportunities"].get(opportunity_id)
    if opportunity is None or opportunity.get("status") not in {
            "admissible", "accepted", "settled", "done"}:
        raise _frontier.Refused("opportunity %r is not admissible" % (
            opportunity_id,))
    declared = opportunity.get("intervention", {}).get("inputs", {}).get("x")
    if declared != x:
        raise _frontier.Refused("probe input differs from admitted effect")
    matches = [effect for effect in store._doc["pending_effects"]
               if effect.get("status") in {"pending", "settled"}
               and effect["opportunity_id"] == opportunity_id
               and effect["program_digest"] == active]
    if effect_identity is not None:
        identity = _frontier._validate_effect_identity(effect_identity)
        matches = [effect for effect in matches
                   if effect["expected_identity"] == identity]
        if not matches and any(
                effect["opportunity_id"] == opportunity_id
                and effect["program_digest"] == active
                and effect.get("status") in {"pending", "settled"}
                for effect in store._doc["pending_effects"]):
            raise _frontier.Refused("probe effect identity differs")
    if len(matches) > 1:
        raise _frontier.Refused("probe effect identity is ambiguous")
    if not matches:
        return None, None
    effect = matches[0]
    if effect["status"] == "pending":
        return effect, None
    observations = [observation for observation in store.observations
                    if observation.get("effect_id") == effect["effect_id"]]
    if len(observations) != 1:
        raise _frontier.Refused("settled probe effect has no unique observation")
    return effect, observations[0]


def _improve_probe_opportunity(store, task: dict, x: int,
                               requested: dict, package_digest: str,
                               round_no: int, step: int) -> str:
    target = task.get("task_id")
    candidates = []
    for opportunity in store._doc["opportunities"].values():
        intervention = opportunity.get("intervention", {})
        inputs = intervention.get("inputs", {})
        if (opportunity.get("status") == "admissible"
                and intervention.get("target") == target
                and inputs.get("x") == x):
            candidates.append(opportunity["opportunity_id"])
    if candidates:
        return sorted(candidates)[0]
    opportunity_id = "improve-%s-r%d-s%d" % (
        package_digest[:16], int(round_no), int(step))
    opportunity = {
        "opportunity_id": opportunity_id,
        "mission_link": store._doc["mission"]["objective"],
        "question": "probe input %d for %s" % (x, target),
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": target, "inputs": {"x": x}},
        "resources": {"queries": int(requested.get("queries", 0)),
                      "steps": int(requested.get("steps", 0))},
    }
    try:
        store.propose(opportunity)
    except _frontier.Refused as exc:
        if "already exists" not in str(exc):
            raise
    existing = store._doc["opportunities"].get(opportunity_id)
    if existing is None or any(
            existing.get(key) != value for key, value in opportunity.items()):
        raise _frontier.Refused("improve probe opportunity is not admissible")
    if existing.get("status") not in {"admissible", "accepted", "done"}:
        raise _frontier.Refused("improve probe opportunity is not admissible")
    return opportunity_id


def execute_operate_action(store, action: dict, task=None) -> dict:
    _frontier.validate_operate_action(action)
    kind = action["kind"]
    inputs = dict(action.get("inputs") or {})
    if kind == "probe":
        if task is None:
            raise _frontier.Refused("probe needs its frozen task")
        try:
            requested = dict(action.get("requested_resources") or {})
            effect, recovered = _find_admitted_probe_effect(
                store, inputs["opportunity_id"], int(inputs["x"]))
            if recovered is not None:
                return {"status": "observed", **recovered}
            if effect is None:
                effect = store.admit_and_spend(
                    inputs["opportunity_id"], store.active_digest, requested)
        except _frontier.Refused as exc:
            return {"status": "refused", "reason": str(exc)}
        session = _boolean_rule.RuleSession(task)
        try:
            found = session.query(int(inputs["x"]))
        except _boolean_rule.RuleRefused as exc:
            return {"status": "refused", "reason": exc.reason}
        observation = {
            "observation_id": "obs-%s-x%d" % (
                inputs["opportunity_id"], inputs["x"]),
            "task": inputs["opportunity_id"],
            "verdict": "observed",
            "x": inputs["x"],
            "y": list(found),
            "effect_id": effect["effect_id"],
            **effect["expected_identity"],
        }
        store.complete_effect(
            effect["effect_id"], observation,
            action_key={"instrument": "boolean-rule-v1",
                        "inputs": {"x": inputs["x"]},
                        "environment": store.environment_digest},
            outcome={"y": list(found)})
        return {"status": "observed", **observation}
    requested = dict(action.get("requested_resources") or {})
    if kind == "investigate":
        active = store.active_digest
        if active is None:
            raise _frontier.Refused("investigation needs a bound program")
        try:
            effect = store.admit_and_spend(
                inputs["opportunity_id"], active, requested)
        except _frontier.Refused as exc:
            return {"status": "refused", "reason": str(exc)}
        return {"status": "accepted", **effect}
    try:
        store.spend(requested)
    except _frontier.Refused as exc:
        return {"status": "refused", "reason": str(exc)}
    if kind in ("wait", "stop"):
        return {"status": kind, "reason": inputs.get("reason", kind)}
    return {"status": "requested", "kind": kind,
            "reason": "deterministic lane records the request; live"
                      " construction stays outside this lane"}


def leaf_construct(strategy: str, parent: dict, round_no: int) -> dict:
    try:
        imp_source = _STRATEGY_SOURCE[strategy]
    except KeyError:
        raise _frontier.Refused("unknown construct strategy %r" % (
            strategy,))
    op_source = parent["op_source"]
    control_id = "control-%s-r%d" % (strategy, round_no)
    version = int(parent.get("version", 0)) + 1
    return {
        "control_id": control_id,
        "origin": ORIGIN,
        "source_kind": "fixed-menu",
        "op_source": op_source,
        "imp_source": imp_source,
        "op_digest": _frontier.source_digest(op_source),
        "imp_digest": _frontier.source_digest(imp_source),
        "package_digest": _frontier.package_digest(
            op_source, imp_source, parent["package_digest"],
            version, control_id, None),
        "parent_digest": parent["package_digest"],
        "provenance": None,
        "provenance_digest": None,
        "version": version,
        "authority_request": dict(parent.get("authority_request") or {
            "queries": 16, "steps": 12}),
        "obligations": ["re-test probe divergence on new seeds"],
        "channel": CHANNEL_VERSION,
    }


def drive_improve_round(store, task, package=None,
                        round_no=None, arm: str | None = None,
                        *, admit_probes: bool = False) -> dict:
    active = dict(package) if package is not None \
        else store.active_package
    if active is None:
        raise _frontier.Refused("improvement needs a bound program")
    if round_no is None:
        previous_rounds = [
            entry.get("round") for entry in store._doc.get("round_journal", [])
            if isinstance(entry, dict)]
        previous_rounds.extend(
            entry.get("round") for entry in store._doc.get("round_results", [])
            if isinstance(entry, dict))
        round_no = max((value for value in previous_rounds
                        if type(value) is int), default=0) + 1
    if admit_probes:
        previous = next((entry for entry in store._doc["round_results"]
                         if entry.get("round") == int(round_no)), None)
        if previous is not None:
            if not isinstance(previous.get("candidate"), dict):
                raise _frontier.Refused("durable improvement result is invalid")
            return {"candidate": dict(previous["candidate"]),
                    "log": list(previous.get("log") or []),
                    "observations": list(previous.get("observations") or []),
                    "receipts": list(previous.get("receipts") or [])}
    session = _boolean_rule.RuleSession(task)
    round_obs: list = []
    log: list = []
    receipts: list = []
    state: dict = {}
    candidate = None
    for step in range(3):
        view = store.step_view(_frontier.IMPROVE, active)
        view["experience"] = list(round_obs)
        view["round"] = round_no
        operation_id = "invl02-improve-%s-r%d-s%d" % (
            active["package_digest"][:16], int(round_no), step)
        command = store.round_command(int(round_no), step)
        if command is not None:
            if not isinstance(command.get("receipt"), dict):
                raise _frontier.Refused("round command receipt is incomplete")
            stepped = {
                "action": dict(command["action"]),
                "state": dict(command["state"]),
                "executed_digest": command["executed_digest"],
                "receipt": dict(command["receipt"]),
            }
        else:
            stepped = run_improve_step(
                active, view, state, operation_id=operation_id, arm=arm,
                task_id=task.get("task_id"),
                artifact_digest=active["package_digest"],
                parent_digest=active.get("parent_digest"),
                round_no=int(round_no),
                receipt_sink=lambda result: store.record_round_command(
                    int(round_no), step, action=result["action"],
                    state=result["state"], receipt=result["receipt"],
                    executed_digest=result["executed_digest"]))
        receipt = stepped["receipt"]
        receipts.append(receipt)
        action = stepped["action"]
        state = stepped["state"]
        requested = dict(action.get("requested_resources") or {})
        probe_opportunity_id = None
        recovered = None
        effect = None
        try:
            if action["kind"] == "probe" and admit_probes:
                probe_opportunity_id = _improve_probe_opportunity(
                    store, task, int(action["inputs"]["x"]), requested,
                    active["package_digest"], int(round_no), step)
                effect, recovered = _find_admitted_probe_effect(
                    store, probe_opportunity_id, int(action["inputs"]["x"]),
                    effect_identity={"operation_id": receipt["operation_id"]})
                if recovered is not None:
                    entry = {"x": int(action["inputs"]["x"]),
                             "y": list(recovered["y"])}
                    round_obs.append(entry)
                    log.append({"round": round_no, "step": step,
                                "action": "probe", "inputs": {"x": entry["x"]},
                                "executed_digest": stepped["executed_digest"],
                                "result": "observed"})
                    continue
                effect = store.admit_and_spend(
                    probe_opportunity_id, active["package_digest"], requested,
                    effect_identity={"operation_id": receipt["operation_id"]})
            else:
                store.spend_round_command(int(round_no), step, requested)
        except _frontier.Refused as exc:
            log.append({"round": round_no, "step": step,
                        "action": action["kind"], "inputs": {},
                        "executed_digest": stepped["executed_digest"],
                        "result": "refused: %s" % exc})
            break
        if action["kind"] == "probe":
            if recovered is not None:
                entry = {"x": int(action["inputs"]["x"]),
                         "y": list(recovered["y"])}
                round_obs.append(entry)
                log.append({"round": round_no, "step": step,
                            "action": "probe", "inputs": {"x": entry["x"]},
                            "executed_digest": stepped["executed_digest"],
                            "result": "observed"})
                continue
            found = session.query(int(action["inputs"]["x"]))
            entry = {"x": int(action["inputs"]["x"]),
                     "y": list(found)}
            if effect is not None:
                observation = {
                    "observation_id": "obs-improve-r%d-s%d-x%d" % (
                        int(round_no), step, entry["x"]),
                    "task": probe_opportunity_id,
                    "verdict": "observed",
                    "x": entry["x"],
                    "y": entry["y"],
                    "effect_id": effect["effect_id"],
                    **effect["expected_identity"],
                }
                store.complete_effect(
                    effect["effect_id"], observation,
                    action_key={"instrument": "boolean-rule-v1",
                                "inputs": {"x": entry["x"]},
                                "environment": store.environment_digest},
                    outcome={"y": list(found)})
            round_obs.append(entry)
            log.append({"round": round_no, "step": step,
                        "action": "probe", "inputs": {"x": entry["x"]},
                        "executed_digest": stepped["executed_digest"],
                        "result": "observed"})
        elif action["kind"] == "construct":
            candidate = leaf_construct(
                action["inputs"]["strategy"], active, round_no)
            candidate = store.stage_round_candidate(
                int(round_no), step, candidate)
            log.append({"round": round_no, "step": step,
                        "action": "construct",
                        "inputs": dict(action["inputs"]),
                        "executed_digest": stepped["executed_digest"],
                        "result": candidate["control_id"]})
        elif action["kind"] == "select":
            wanted = action["inputs"]["candidate_id"]
            staged = store._doc["staged_candidate"] or {}
            if staged.get("control_id") != wanted:
                log.append({"round": round_no, "step": step,
                            "action": "select",
                            "inputs": dict(action["inputs"]),
                            "executed_digest": stepped[
                                "executed_digest"],
                            "result": "unsupported: unknown candidate"})
                break
            log.append({"round": round_no, "step": step,
                        "action": "select",
                        "inputs": dict(action["inputs"]),
                        "executed_digest": stepped["executed_digest"],
                        "result": "selected"})
        else:
            log.append({"round": round_no, "step": step,
                        "action": action["kind"],
                        "inputs": dict(action.get("inputs") or {}),
                        "executed_digest": stepped["executed_digest"],
                        "result": "round-ended"})
            break
    if candidate is None:
        raise _frontier.Refused("improve round left no candidate")
    if admit_probes:
        result = {
            "round": int(round_no), "candidate": dict(candidate),
            "log": list(log), "observations": list(round_obs),
            "receipts": list(receipts),
        }
        result["result_digest"] = _frontier.round_result_digest(result)
        store._doc["round_results"].append(result)
    store.save()
    return {"candidate": candidate, "log": log,
            "observations": list(round_obs), "receipts": receipts}


def fresh_round(store_path: str, round_no: int) -> dict:
    store = _frontier.FrontierStore(store_path)
    active = store.active_package
    if active is None:
        raise _frontier.Refused("fresh process found no bound program")
    environment = dict(store._doc["environments"][0])
    task = _boolean_rule.make_task(environment["split"],
                                   environment["seed"])
    result = drive_improve_round(
        store, task, round_no=int(round_no), admit_probes=True)
    candidate = result["candidate"]
    return {"candidate_id": candidate["control_id"],
            "parent_digest": candidate["parent_digest"],
            "executed_digest": active["imp_digest"],
            "imp_source_digest": candidate["imp_digest"],
            "round": int(round_no)}


def main(argv) -> int:
    store_path, round_no = argv[1], int(argv[2])
    summary = fresh_round(store_path, round_no)
    sys.stdout.write(json.dumps(summary, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
