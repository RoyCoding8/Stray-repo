"""M2 inherited improvement behavior through the action interface.

Operational and improvement behavior share one executable package: two
STEP sources under one manifest digest. The improvement entry controls
later acquisition, construction and selection by returning probe,
construct and select actions that the driver executes through real
instruments. Menu selection and prompt advice are not involved.

Two authored controls share their operational bytes and differ in their
improvement bytes. Under matched inputs they request different real
probes. Both stay labeled and never enter acquired treatment arms.
Leaf construction builds the descendant from its parent's own improvement
source with the construction decision substituted at the probed input, so
what a revision chose is what its descendant runs. Adoption binds at a
quiescent boundary with reset private state and explicit retained
evidence plus obligations.

Bounded revision sits below. A revision may change which diagnostic
evidence the learner gathers, and only that. Eligibility, the descendant
metric, the immutability freeze and the three apparatus controls are all
decided here, and the channel's own reachable range is reported so a
study can be told before it is run that the decision has no headroom.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
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

# The two authored controls. Their bytes differ in the input each one
# probes and in nothing else, and they stay that way: lane C2's fixtures
# rewrite the construction binding in these exact sources, so the shape of
# a control is a shared vocabulary rather than something this lane may
# restate. What changed is not the controls but what the constructor does
# with the decision they reach.
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

REVISION_VERSION = "invl02-revision-v1"


def _revision_source(probe) -> str:
    """Build a revision around one evidence-selection rule.

    Takes an authored control as the template and rewrites the input it
    probes, so a revision differs from the incumbent at exactly the
    decision under study and nowhere else. A difference in the descendant
    is then attributable to the evidence choice by construction.

    Both authored procedures are offered, so a revision can be written
    against either one and a descendant inherits whichever its parent ran.
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
INELIGIBLE_OUT_OF_SCOPE = "changes-an-unauthorised-decision"
INELIGIBILITY_REASONS = (
    INELIGIBLE_PROSE, INELIGIBLE_NO_BOUNDARY, INELIGIBLE_SOLVER,
    INELIGIBLE_DELEGATION, INELIGIBLE_FROZEN_WRITE, INELIGIBLE_OUT_OF_SCOPE)


def revision_evidence_choices(source: str, view: dict, *,
                              authority: dict | None = None,
                              operation_id: str | None = None) -> list:
    """Execute revision bytes under one view and read back its choices.

    The revision is a STEP source, so the only honest way to know which
    evidence it selects is to execute it. Scanning the text for a literal
    would miss a computed x, and a computed x is exactly the case that
    decides the improvement.

    The executions run under real authority, like every other execution of
    policy source in this module. This used to catch a bare `Exception` and
    break, which turned a refusal to execute into a revision that had been
    executed and chosen nothing. The two are separated here. A child that ran
    and returned a step it could not use means this revision chose nothing,
    and the caller scores it on its own eligibility. A refusal to execute at
    all, which is what a missing authority or an unsettled receipt produces,
    propagates: a revision nobody executed has not chosen nothing, it has
    not been looked at.
    """
    chosen: list = []
    state: dict = {}
    working = dict(view)
    digest = _frontier.source_digest(source)
    with _execution_ledger(authority, "invl02-revision",
                           operation_id) as held:
        for index in range(int(EXECUTION_LIMITS["max_policy_steps"])):
            try:
                stepped = _run_source(
                    source, working, state, authority=held,
                    operation_id=held["operation_id"] if operation_id
                    else "%s-%d" % (_derived_operation_id(
                        {"package_digest": digest}, "rev", view), index))
            except _method_exec.MethodExecutionError as exc:
                if str(exc).startswith("step-failed"):
                    break
                raise
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


# What a revision is allowed to change, and the decision each site of the
# step belongs to. The refusal names the decision rather than reporting that
# something differs, because "ineligible" alone cannot tell a reader which
# boundary held.
AUTHORISED_DECISION = "probe-input"

_SHAPE_PROBE = "<authorised-change>"


def unauthorised_change(incumbent: str, revision: str) -> dict:
    """The decision a revision moved that it was not authorised to move.

    Compares the two sources with the probed input blanked on both sides, so
    the one change the interface names is invisible to the comparison and
    only the remaining differences are left to account for. A revision that
    rewrites the allocation, the construction choice, the action target or
    the step's own action is a different program from the incumbent at
    exactly one place a reviser does not own, and every such program is
    caught. A revision that rewrites the probed input and nothing else
    normalises to the incumbent exactly, so the one authorised change is
    admitted.

    Blanking rather than comparing similarity is what makes this an
    interface check. There is no threshold and nothing to tune: the question
    is whether the two programs are the same program once the authorised
    change is taken away.
    """
    left, right = _program_shape(incumbent), _program_shape(revision)
    if left is None or right is None:
        raise _frontier.Refused("cannot compare unparseable revision bytes")
    if _same(left, right):
        return {}
    site = _first_difference(left, right)
    return {"decision": site,
            "baseline_shape_digest": _frontier.source_digest(
                ast.dump(left)),
            "revision_shape_digest": _frontier.source_digest(
                ast.dump(right))}


def _program_shape(source: str):
    """The parsed source with every probed input blanked.

    The probed input is the value bound to a key `x` inside a frontier
    action's inputs. Blanking it removes the authorised change from the
    comparison, and blanking it at every site rather than the first is what
    makes a revision that probes in two places comparable at all. The dict
    is matched on the key alone rather than on the dict holding only that
    key, because a revision may carry sibling inputs alongside `x` and
    blanking those sites is what keeps such a revision admissible.

    Returns None rather than raising, so the caller decides what an
    unparseable source means.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for index, key in enumerate(node.keys):
            if isinstance(key, ast.Constant) and key.value == "x":
                node.values[index] = ast.Constant(value=_SHAPE_PROBE)
    return tree


def _same(left, right) -> bool:
    return ast.dump(left) == ast.dump(right)


# Each site names the decision it belongs to. Both the strategy name and
# the construction value are named rather than inferred from the construct
# branch around them, because the choice of what a descendant probes is
# made when that value is bound, not where the branch uses it. Anything
# the map does not name is the step's own skeleton, which is the last name
# because it is the catch-all rather than a claim.
_SITES = {
    "requested_resources": "probe-allocation",
    "target": "probe-target",
    "kind": "step-skeleton",
    "strategy": "candidate-construction",
    "construction": "candidate-construction",
}


def _first_difference(left, right) -> str:
    """The decision the two shapes first differ at, named.

    The walk is structural and in source order, so the reason names the first
    thing a reader would meet reading the two programs side by side.
    """
    if type(left) is not type(right):
        return _SITES["kind"]
    if isinstance(left, ast.Dict):
        if len(left.keys) != len(right.keys):
            return _SITES["kind"]
        for key, lvalue, rvalue in zip(left.keys, left.values,
                                       right.values):
            if isinstance(key, ast.Constant) and key.value in _SITES:
                if not _same(lvalue, rvalue):
                    return _SITES[key.value]
                continue
            found = _first_difference(lvalue, rvalue)
            if found is not None:
                return found
        return None
    if isinstance(left, ast.Assign):
        for target in left.targets:
            if isinstance(target, ast.Name) and target.id in _SITES:
                if not _same(left.value, right.value):
                    return _SITES[target.id]
                return None
        return _first_difference(left.value, right.value)
    if isinstance(left, ast.Constant):
        return None if _same(left, right) else _SITES["kind"]
    children = [child for child in ast.iter_child_nodes(left)]
    other = [child for child in ast.iter_child_nodes(right)]
    if len(children) != len(other):
        return _SITES["kind"]
    for a, b in zip(children, other):
        found = _first_difference(a, b)
        if found is not None:
            return found
    return None if _same(left, right) else _SITES["kind"]


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


def classify_revision(source: str, views: list, *,
                       incumbent: str = None) -> dict:
    """Decide whether revision bytes are an eligible intervention.

    Eligibility is a property of the bytes and the boundary they reach,
    decided before the revision is ever measured, so an ineligible
    revision is refused rather than scored. `views` is a list of
    genuinely different learner views.

    The bytes must differ from the incumbent at the probed input and at
    nothing else. `incumbent` is the improvement source the revision would
    replace, and the channel's own default when a caller does not name one.
    Without that comparison the declared interface is prose: an audit
    measured six variants that rewrote the allocation, the construction or
    the step skeleton and found every one of them eligible
    (reports/workstreams/w4-e4-interface.md §4).

    The scope check runs after the questions that do not need it and before
    the ones that execute the revision. A revision that both moves another
    decision and reproduces the frozen reducer's choice is reported for the
    scope breach, because a scope breach is a property of the bytes while
    the delegation is a property of what they do under these views.

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
    baseline = IMPROVE_LOW_SOURCE if incumbent is None else incumbent
    moved = unauthorised_change(baseline, source)
    if moved:
        return _refused(INELIGIBLE_OUT_OF_SCOPE,
                        "revision changed the %s, and the only change it is"
                        " authorised to make is the %s"
                        % (moved["decision"], AUTHORISED_DECISION))
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
# What a descendant gathers is not the evidence the reviser gathered, and
# it used not to be a property of the reviser either. `leaf_construct`
# replaced the improvement source with a member of a two-entry authored
# menu, so a descendant probed the menu's input however the revision
# selected, and the set of inputs any revision could ever reach was those
# two integers. The module said so itself. That is the fixed research
# script the requirement forbids: "The model constructor is a leaf effect,
# not the owner of a fixed research script."
#
# The construction is now a procedure rather than a table. A descendant
# inherits its parent's improvement source and the decision is substituted
# into the parent's own expression, so what a revision chooses is what its
# descendant runs and the reachable set is a property of the program rather
# than of a dict written beside it. The substitution is at the probed
# input and nowhere else, which is the one decision the interface names,
# so a revision that changes the procedure is still the authorised kind
# and this is not a way around the freeze.

GENERAL_POSITION = (0, 1, 2, 4, 8)


def _descendant_source(parent_source: str, construction: int) -> str:
    """The improvement source a descendant runs, built from its parent's.

    `construction` is the input the revision selected. It is substituted
    into the parent's own probed-input expression, so the descendant is
    the parent's procedure with one decision replaced rather than a member
    of a table chosen beside it.

    The substitution is at the parent's own probed input and nowhere
    else. A parent that writes a literal has exactly those characters
    replaced, so a descendant differs from its parent by one integer and
    is otherwise the same bytes; a parent that computes its input has the
    computed node rebound instead. Either way the result differs at
    exactly the decision under study and at no other.

    A construction naming the input the parent already probes returns the
    parent's bytes rather than a reprint of them. `unparse` is faithful
    but reformats, and a descendant differing from its parent in
    formatting alone would read as a different procedure to anything
    comparing the two as bytes.
    """
    value = int(construction)
    literal = _literal_probe_span(parent_source)
    if literal is not None:
        start, end, current = literal
        if current == value:
            return parent_source
        return parent_source[:start] + str(value) + parent_source[end:]
    try:
        tree = ast.parse(parent_source)
    except (SyntaxError, ValueError, RecursionError):
        raise _frontier.Refused("parent improvement source is unparseable")
    substituted = 0
    for probe_value in _probe_input_sites(tree):
        _replace_node(tree, probe_value, ast.Constant(value=value))
        substituted += 1
    if not substituted:
        raise _frontier.Refused("parent selects no probe input to replace")
    return ast.unparse(ast.fix_missing_locations(tree))


def _literal_probe_span(source: str):
    """The character span of the probed input, when it is one literal.

    A parent that writes its probed input as a literal gets its descendant
    built by replacing exactly those characters rather than by reprinting
    the program. `ast.unparse` is faithful but reformats, and a descendant
    that differed from its parent in formatting alone would read as a
    different procedure to anything comparing the two as bytes. Two
    authored controls that differ only in that literal therefore stay
    comparable as text, which is what inheritance has to mean here.

    Offsets are the difference between this and a naive splice. `ast`
    reports `col_offset` in UTF-8 bytes, so a source carrying any
    non-ASCII before the literal would be cut in the wrong place and the
    descendant would not parse. Decoding each line to characters before
    indexing is what makes the span mean what it says.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "x" \
                    and isinstance(value, ast.Constant) \
                    and type(value.value) is int:
                spans.append((value.lineno, value.col_offset,
                              value.end_lineno, value.end_col_offset,
                              int(value.value)))
    if len(spans) != 1:
        return None
    lineno, start_col, end_lineno, end_col, current = spans[0]
    if lineno != end_lineno:
        return None
    lines = source.splitlines(keepends=True)
    line = lines[lineno - 1].encode("utf-8")
    start = sum(len(item) for item in lines[:lineno - 1]) + \
        len(line[:start_col].decode("utf-8"))
    end = sum(len(item) for item in lines[:lineno - 1]) + \
        len(line[:end_col].decode("utf-8"))
    return start, end, current


def _probe_input_sites(tree) -> list:
    """The nodes this tree binds to a probe's `x`, wherever they are bound.

    Read off the tree that will be rewritten rather than off a second
    parse of the same text, because the two parses produce different node
    objects and an identity check between them never matches.
    """
    bound: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound[target.id] = node.value
    sites: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "x":
                sites.append(_resolve_bound(value, bound, set()))
    return sites


def _resolve_bound(expression, bound: dict, seen: set):
    while isinstance(expression, ast.Name) and expression.id in bound \
            and expression.id not in seen:
        seen.add(expression.id)
        expression = bound[expression.id]
    return expression


def _replace_node(tree, target, replacement) -> bool:
    """Rebind every reference to `target`, in place."""
    replaced = False
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if value is target:
                setattr(parent, field, replacement)
                replaced = True
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if item is target:
                        value[index] = replacement
                        replaced = True
    return replaced


def reachable_evidence(source: str) -> tuple:
    """Every input a program can be made to probe, read out of its bytes.

    What a descendant gathers is a property of the descendant's own
    source, so this is a function of the program rather than a constant
    published beside it. A revision whose construction is substitutable at
    its probed input can therefore reach any input the instrument accepts,
    and two revisions that name different inputs reach different sets.

    A program that binds its probed input to something that is not a plain
    integer expression has no fixed reachable set to report, and saying so
    is more useful than reporting the one input a literal scan happened to
    find in it. The instrument's range is the bound a caller needs.
    """
    nodes = _probe_x_expression(source)
    inputs: set = set()
    for expression in nodes:
        try:
            value = ast.literal_eval(expression)
        except (ValueError, SyntaxError, TypeError, MemoryError,
                RecursionError):
            return tuple(str(x) for x in range(16))
        if type(value) is int:
            inputs.add(int(value))
    if not inputs:
        return ()
    return tuple(str(x) for x in sorted(inputs))


# The evidence the incumbent gathers. It was a literal at two places that
# used it; it is named once so the estimator and the constructor cannot
# disagree about what the incumbent ran.
INCUMBENT_EVIDENCE = (3,)

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


def construction_from_evidence(observations: list) -> int:
    """The input a descendant probes, derived from what the round observed.

    This is the whole of the inheritance. The descendant's construction is
    a function of the evidence the revision gathered, so a revision that
    selected a different input produces a descendant that probes a
    different input, and the choice survives adoption instead of being
    resolved against a table the reviser could not have changed.

    It is the last input the round spent, because that is the input the
    evidence is about: the observation was read back from it. The
    strategy name the construct action still carries is a label, not a
    selection, and is deliberately not read here.
    """
    spent = [o for o in observations if isinstance(o, dict)
             and type(o.get("x")) is int]
    if not spent:
        raise _frontier.Refused("round gathered no evidence to inherit")
    return int(spent[-1]["x"]) % 16


def construction_from_observation(development_probe: int, y) -> int:
    """The construction a descendant of that probe reaches, for the metric.

    Same function as `construction_from_evidence`, read off a probe rather
    than off a list, so the descendant metric follows the path the code
    builds rather than a restatement of it.

    Reading the observation's first bit instead - which is what the menu
    made equivalent, because the menu's two members corresponded to that
    bit - would be measuring a construction the code does not perform.
    """
    return int(development_probe) % 16


def _strategy_descendant(construction, split: str, seed: int) -> dict:
    """Score the descendant one construction input builds.

    Split out from `lineage_descendant_score` so the input a construction
    produces is named separately from the development probe that selects
    it. The selection is the decision under study; what the construction
    then gathers is the substrate, and the two have to be replaceable
    apart.
    """
    return descendant_score([int(construction)], split, int(seed))


def lineage_descendant_score(development_probe: int, split: str,
                             seed: int) -> dict:
    """Score one descendant on the path the code actually builds.

    `drive_improve_round` probes, reads the observation back, and hands
    the pair to `leaf_construct`, which substitutes the construction into
    the parent's own probed input. So the descendant runs the input the
    revision selected, and the frozen reducer sees only what the
    descendant gathers. Scoring the development probe's own evidence here
    would credit the descendant with evidence it never received.
    """
    construction = construction_from_observation(int(development_probe), ())
    return _strategy_descendant(str(construction), split, int(seed))


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
    compared against in an E4 round. What the construction can install is
    reported as `reachable_evidence`, read off the incumbent's own bytes.
    The ceiling over every input the instrument accepts is a wider
    question and this is not it: nothing here bounds the substrate.

    A flag that cannot be true is not a measurement either, so two
    guards here are required for `measurable` to be true: the best probe
    has to beat the incumbent, and the gap has to exceed its own standard
    error, or `measurable` would be reading a cohort that has converged
    as a direction. A caller that wants the raw magnitude without either
    of them has `delta` and `paired_se` here. The second guard is what
    stops the second from being free: a channel with a real effect has a
    positive standard error, so the flag stays available to a planted
    one, which `tests/test_s09_e4_remediation.py` requires it to find.

    A third guard was tried and removed. The incumbent is itself one of
    the inputs the construction can install, so the best of the sixteen
    inputs is at least as good as the incumbent. A "must beat the
    reachable set" condition is therefore unreachable by construction, and
    a guard that cannot refuse is not a guard. The reachable set is
    reported anyway, because it is the number a reader wants, but it does
    not gate anything.
    """
    seeds = list(seeds)
    incumbent_evidence = list(INCUMBENT_EVIDENCE if incumbent_evidence is None
                              else incumbent_evidence)
    if not seeds:
        return {"estimator": ESTIMATOR, "half_cohort_comparison": False,
                "delta": None, "paired_se": None, "paired_sd": None,
                "z": None, "measurable": False, "selection_biased": False,
                "incumbent_mean": None,
                "incumbent_evidence": incumbent_evidence,
                "best_probe": None, "best_mean": None,
                "best_beats_incumbent": False,
                "split_half": {"select": {"n": 0, "seeds": []},
                               "score": {"n": 0, "seeds": []}},
                "split": split, "n": 0,
                "reachable_evidence": list(
                    reachable_evidence(IMPROVE_LOW_SOURCE))}
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
    # The inputs a construction can actually install, read off the
    # incumbent's own bytes rather than off a published menu. Reported
    # because it is the number a reader wants next to the best-probe mean:
    # it is the range the decision is able to express however the revision
    # chose its probe. It gates nothing. A "must beat the reachable set"
    # condition is refused on principle, because the best of the sixteen
    # inputs is a member of that set and so such a guard could never
    # refuse anything.
    reachable = reachable_evidence(IMPROVE_LOW_SOURCE)
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
        "incumbent_evidence": incumbent_evidence,
        "best_probe": best_probe,
        "best_mean": best_mean,
        "best_beats_incumbent": best_mean > incumbent_mean,
        "split_half": {
            "select": {"n": len(select), "seeds": select},
            "score": {"n": len(score), "seeds": score},
        },
        "split": split, "n": len(seeds),
        "reachable_evidence": list(reachable),
    }


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

    The scope check compares against the improvement source the store
    actually has bound, not against a constant. A revision is judged against
    the program it would replace, so a store bound to the high menu member is
    not measured against the low one's bytes.

    The frozen state is captured before the revision is executed at all
    and compared after. That comparison is not a second layer over the
    static check and cannot be one. A revision's bytes run out of
    process, in a bounded child, against a JSON view that carries none
    of the six frozen fields, so nothing those bytes do can reach the
    store compared here. What the comparison does hold is admission
    itself: a write to the store from inside this function is a real
    breach, and it is caught here rather than trusted.

    The reason a revision is refused names the write that was caught,
    so a refusal distinguishes `view.update({"grant": x})` from
    `view["grant"] = x` instead of reporting both as ineligibility.
    """
    before = frozen_state(store)
    breach = _frozen_write_reason(source)
    if breach:
        return _refused(INELIGIBLE_FROZEN_WRITE, breach)
    verdict = classify_revision(source, views,
                                incumbent=bound_improve_source(store))
    if verdict.get("eligibility") != ELIGIBLE:
        return verdict
    after = frozen_state(store)
    if _frontier.canonical(before) != _frontier.canonical(after):
        raise FrozenFieldViolation("frozen state changed during admission")
    verdict["frozen_state_digest"] = _frontier.source_digest(
        _frontier.canonical(before))
    return verdict


def bound_improve_source(store) -> str:
    """The improvement source a revision would replace, read off the store.

    Read from the store rather than assumed, because a revision's scope is
    relative to the program it revises. A store with nothing bound falls back
    to the low menu member, which is the program every authored control is
    written against.
    """
    active = store.active_package
    if isinstance(active, dict) and isinstance(active.get("imp_source"), str):
        return active["imp_source"]
    return IMPROVE_LOW_SOURCE


def _attempts_frozen_write(source: str) -> bool:
    """True when the revision names a frozen field in a write position.

    Read access is legitimate: a learner reads the remaining budget to
    decide what it can still afford. A write is not, so the check is on
    the assignment target rather than on the name alone.

    A write position is read off the parse rather than off a list of
    statement types. Python has five binding statements and an earlier
    version of this check named two of them, so a candidate could write the
    grant as `grant: dict = {}` or `(grant := x)` and pass a check that
    reads as a guarantee. An annotated local is ordinary Python and the
    walrus is how a name is bound inside a conditional expression, so
    neither is an exotic way in.

    Extending that list to four would have closed those two holes and left
    `Subscript.slice`, `Delete`, the `for` and `with` targets and the
    comprehension targets unexamined, since every one of them binds exactly
    as `=` does. The parser already marks every name, attribute and
    subscript it stores into or deletes with a `Store` or `Del` context, so
    asking which of those contexts a node carries is the language's own
    answer and cannot be incomplete the way a hand-kept enumeration is. The
    enumeration is therefore gone rather than extended, and it also covers a
    statement Python adds later without touching this file.

    That rule covers every position that carries a target and it says
    nothing about a position that reaches the same key without one.
    `view.update({"grant": x})` writes the same key `view["grant"] = x`
    writes, and the parser marks no store in it at all, because the write
    happens inside the method rather than at a target. So the method forms
    are read by what they are called with, which is what `_call_writes`
    does. The two questions are kept apart on purpose: a call is examined
    for a named method with a named key, and a target is examined for a
    name, an attribute or a subscript key.
    """
    return bool(_frozen_write_reason(source))


def _frozen_write_reason(source: str) -> str:
    """The reason a revision is refused for writing frozen state, or ''.

    Returns the write that was caught rather than a bare true, because
    `admit_revision_under_freeze` reports a reason to a caller and a caller
    cannot act on "ineligible". Every reason names the form, so
    `view.update({"grant": x})`, `view["grant"] = x` and a key the check
    could not read are three different sentences in the verdict rather than
    one.

    A key this check cannot resolve is refused rather than admitted, and
    that is the honest default rather than a convenient one. Resolving
    `k` in `view[k] = x` means tracking what every name in the program
    binds to, which is a taint analysis over the whole program, and a
    static check that guessed at it would report a verdict it had not
    earned. The previous version of this function deferred that case to a
    second layer, the runtime comparison of frozen state either side of
    admission. That comparison cannot fire: a revision's bytes run out of
    process against a JSON view carrying none of the six fields, against
    disposable stores, never the store compared. The deferral was the
    reason the gap survived every gate, so it is deleted rather than
    documented. There is no runtime backstop and this function is the
    whole of the freeze.

    The two default-deny rules are the ones that close what the target rule
    cannot reach, and both are stated in the reason rather than hidden:

    - an unreadable key on the view. `view[k] = x` names a key the check
      cannot name, so it is refused as unreadable. It is not claimed to be
      frozen. A subscript the revision built for itself, `seen[key] = ...`,
      is not covered by this rule, and neither is a method on one. That is
      the same line the module draws between `eval(...)` and
      `view.eval(...)`, applied to the receiver rather than to the word:
      the check reads the receiver and cannot read the key, so it refuses
      where it knows the container is the view and stays quiet where it
      knows the revision made it.
    - a keyless write to the view. `clear()` and `popitem()` write every
      key they hold and take no key at all, so the only question left is
      whose mapping it is. Same receiver rule, same reason it holds.

    That last rule is coarser than the key-taking forms get, and it is the
    price of closing a write with no name in it. It refuses
    `view.update(...)` with a computed argument and `view.pop(viewed_key)`
    with a computed key, both of which would be admitted if the key were
    spelled out. That is the limit stated in one place rather than spread
    across the cases, because a reader who finds it there will believe the
    rest. The rule also does not reach a mapping the revision reached
    through one hop, `view["frozen_source"]["grant"] = x`, because the
    check reads names and not what they resolve to. The keys this misses
    are keys the revision cannot name either: the view the child receives
    carries `authority_remaining` and `improvement_budget` and none of the
    six frozen fields, so a write through one hop lands on nothing frozen.
    That is a property of the view and not of this function, and if the
    view ever carries a frozen field the receiver rule has to follow it.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return ""
    frozen = set(FROZEN_FIELDS)
    view_names = _names_bound_to_view(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # A call before its own receiver, so `view.update(grant=x)` is
            # answered by the call that writes rather than by the attribute
            # that merely names the method.
            reason = _call_write_reason(node, frozen, view_names)
            if reason:
                return reason
            continue
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)) \
                and isinstance(node.ctx, (ast.Store, ast.Del)):
            reason = _target_frozen_reason(node, frozen, view_names)
            if reason:
                return reason
        # The one binding the parser records as a bare string rather than
        # a node with a context, so the rule above cannot see it.
        if isinstance(node, ast.ExceptHandler) and node.name in frozen:
            return "bound %r as an exception name" % (node.name,)
        if isinstance(node, ast.AugAssign) and _is_view(
                node.target, view_names):
            return "%s |= merges keys into the view it was handed" \
                % (ast.unparse(node.target),)
    return ""


# The names a revision holds the view under, which is `view` plus whatever it
# bound that name to. `v = view` then `v.clear()` is the same write as
# `view.clear()`, and a receiver rule that read only the parameter would miss
# it, so the alias is resolved rather than left to a reader.
#
# One hop. Following `v = w = view` is the same thing and is followed, but a
# name bound from a call's return, `v = dict(view)`, or passed as an
# argument, `helper(view)`, is not followed, and neither is a name bound
# inside a comprehension or a nested function the walk never enters. That is
# stated rather than papered over: a write through an alias this does not
# follow would be missed, and the price of closing it is tracking what every
# binding in the program resolves to, which is the taint analysis the
# computed-key case already declines. What the gap cannot reach is the grant,
# because the view the child receives carries none of the six frozen fields
# (see the limit stated on this function).
_VIEW_PARAMETER = "view"


def _names_bound_to_view(tree) -> frozenset:
    """The view, plus every name bound directly to it in this program."""
    names = {_VIEW_PARAMETER}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if isinstance(value, ast.Starred):
            value = value.value
        if not _is_view(value, names):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return frozenset(names)


# A receiver is the view, or an attribute or subscript of it. A name bound
# to a mapping the revision built is not, and neither is a call: the module
# draws this line already, between `eval(...)` and `view.eval(...)`, and
# this is the same line applied to who owns the object rather than to the
# name of the method on it.
def _is_view(node, names: frozenset) -> bool:
    if isinstance(node, ast.Name):
        return node.id in names
    if isinstance(node, ast.Attribute):
        return _is_view(node.value, names)
    if isinstance(node, ast.Subscript):
        return _is_view(node.value, names)
    return False


def _frozen_write_reason_unreadable_key(node) -> str:
    return "writes view[%s], a key this check cannot resolve to a name" \
        % (ast.unparse(node.slice),)


def _frozen_write_reason_unreadable_arg(node) -> str:
    return "%s writes view with keys this check cannot resolve to names" \
        % (ast.unparse(node.func),)


def _frozen_write_reason_keyless(node) -> str:
    return "%s writes every key of the view it was handed" \
        % (ast.unparse(node.func),)


# The mapping methods that take a key and write it, and the two that take
# no key and write all of them. `update` is here rather than among the
# builtins because it is a method on a mapping, and `view.update(...)` is a
# call on a value rather than a builtin; it is refused on its argument in
# the same way `eval(...)` is refused on its name.
_KEY_WRITING_METHODS = frozenset((
    "update", "setdefault", "pop", "popitem", "clear", "__delitem__"))


# `update` names the keys it writes in the keys of the mapping it is given,
# not in the argument itself: `update({"grant": x})` and `pop("grant")` are
# the same write with two different shapes of argument. Reading both through
# one rule would either miss `update`'s keys or refuse every mapping passed
# to `pop`, so the key-taking methods are split by what their argument is.
_MAPPING_ARG_METHODS = frozenset(("update",))


def _call_write_reason(node, frozen: set, view_names: frozenset) -> str:
    """The reason a call writes frozen state, or ''.

    A bare name and a method are kept apart. `setattr(...)` is the builtin
    and refuses, while `obj.setattr(...)` is an attribute on a type this
    program never sees, and refusing it would be the guard refusing a word
    rather than the act it names.

    `update` takes a mapping and the rest take a key, so `update` is read
    through the keys of its argument rather than through the argument
    itself. `view.update({"grant": x})` and `view.pop("grant")` are the same
    write with two different shapes of argument, and reading both through one
    rule would either miss `update`'s keys or refuse every mapping handed to
    `pop`.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return ("calls %s, which writes a frozen field" % (func.id,)
                if func.id in _BUILTIN_WRITES else "")
    if not isinstance(func, ast.Attribute):
        return ""
    name = func.attr
    if name in _PROTOCOL_WRITES:
        return "%s writes a frozen field" % (ast.unparse(func),)
    if name not in _KEY_WRITING_METHODS:
        return ""
    if not _is_view(func.value, view_names):
        return ""
    if name in ("clear", "popitem"):
        return _frozen_write_reason_keyless(node)
    if name in _MAPPING_ARG_METHODS:
        # Before the positional test below, because `update(grant=x)` names
        # its key in a keyword and has no positional argument to read.
        return _update_write_reason(node, frozen)
    if not node.args:
        return _frozen_write_reason_unreadable_arg(node)
    argument = node.args[0]
    if isinstance(argument, ast.Starred):
        return _frozen_write_reason_unreadable_arg(node)
    if _names_frozen(argument, frozen):
        return "%s writes the frozen field %s" % (
            ast.unparse(func), ast.unparse(argument))
    if _readable_key(argument):
        return ""
    return _frozen_write_reason_unreadable_arg(node)


def _update_write_reason(node, frozen: set) -> str:
    """The reason an `update` writes frozen state, or ''.

    `update` takes a mapping, so the frozen field is named in the keys of
    that mapping rather than in the argument itself. Both spellings of a key
    are read: `update({"grant": x})` and `update(grant=x)` are one write
    written two ways, and reading only the literal form would leave the
    keyword form as a door beside it.

    `**other` merges a mapping built elsewhere and names no key here, and
    neither does a mapping bound to a name. Both are refused as unreadable
    rather than followed, which is the same default-deny the computed-key
    case takes and is stated in the limit on `_frozen_write_reason`.
    """
    for text, key in _keys_named_by_update(node):
        if key in frozen:
            return "%s writes the frozen field %r" % (
                ast.unparse(node.func), key)
        if key is None:
            return _frozen_write_reason_unreadable_arg(node)
    return ""


def _keys_named_by_update(node):
    """Every key an `update` names, as (source text, key or None).

    Both spellings of a key are collected, because `update` takes both at
    once: `update({"harmless": 1}, grant=1)` names one key the check can
    read and one it cannot read only if it is written as a name, and reading
    the positional argument alone would miss the keyword beside it.

    None is the unreadable case and is refused by the caller rather than
    resolved, so this function decides only what can be read. A keyword
    argument names its own key, because `update(grant=x)` and
    `update({"grant": x})` are one write written two ways.
    """
    found: list = []
    if node.args and not isinstance(node.args[0], ast.Starred):
        argument = node.args[0]
        if isinstance(argument, ast.Dict):
            for key in argument.keys:
                if key is not None and _readable_key(key):
                    found.append((ast.unparse(key), key.value))
                else:
                    found.append((ast.unparse(argument), None))
        elif _readable_key(argument):
            found.append((ast.unparse(argument), argument.value))
        else:
            found.append((ast.unparse(argument), None))
    for keyword in node.keywords:
        found.append((keyword.arg or "**%s" % ast.unparse(keyword.value),
                      keyword.arg))
    return found or [(ast.unparse(node), None)]


# A key the check reads, which is a literal string or a tuple or list of
# them. `update({"experience": []})` names a key it can read and it is not
# frozen, so the call is admitted; `update(computed)` names nothing it can
# read, so the call is refused as unreadable. The distinction is the whole
# of what the key-taking forms claim, and collapsing the two would make the
# rule a blanket refusal of every mapping method on the view.
def _readable_key(node) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(_readable_key(item) for item in node.elts)
    return False


def _names_frozen(node, frozen: set) -> bool:
    """True when a key the check can read names a frozen field.

    A `dict.update` key and a `pop` key are the same question as a subscript
    key and are answered by the same rule, including the unanswered case: a
    key the check cannot read returns false here and is refused as
    unreadable by the caller, rather than being resolved or admitted.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value in frozen
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_names_frozen(item, frozen) for item in node.elts)
    return False


# Calls that write to a container or an attribute with no syntactic target
# to inspect. Named rather than derived because a method name belongs to a
# type this program never sees, so the only place the name can come from
# is here.
_BUILTIN_WRITES = frozenset((
    "setattr", "delattr", "exec", "eval", "open"))

# The same acts spelled as a method, which is what the protocol gives them.
# `view["grant"] = x` and `view.__setitem__("grant", x)` write the same
# key, so covering one and not the other would leave the subscript rule
# with a second door beside it.
_PROTOCOL_WRITES = frozenset((
    "__setattr__", "__delattr__", "__setitem__", "__delitem__"))


def _target_frozen_reason(node, frozen: set, view_names: frozenset) -> str:
    """The reason a store target reaches frozen state, or ''.

    The three spellings are the three the parser marks with a context, and
    a check that catches one and not the other is checking a spelling
    rather than the write. The target's own container is followed too:
    `view.grant` is the attribute and `view["grant"]` is the key, and a
    subscript's value is a target when the subscript is.
    """
    if isinstance(node, ast.Attribute):
        if node.attr in frozen:
            return "writes view.%s, a frozen field" % (node.attr,)
        return _target_frozen_reason(node.value, frozen, view_names)
    if isinstance(node, ast.Name):
        return ("binds %r, a frozen field" % (node.id,)
                if node.id in frozen else "")
    if isinstance(node, ast.Subscript):
        if _names_frozen(node.slice, frozen):
            return "writes view[%s], a frozen field" % (ast.unparse(
                node.slice),)
        nested = _target_frozen_reason(node.value, frozen, view_names)
        if nested:
            return nested
        # A key the check cannot read, on the view. `view[k] = x` reaches
        # the view the revision was handed and the key is the one thing
        # here that cannot be resolved, so it is refused rather than
        # resolved. `seen[key] = x` is not, because the revision made it.
        if _is_view(node.value, view_names) \
                and not _readable_key(node.slice):
            return _frozen_write_reason_unreadable_key(node)
        return ""
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            reason = _target_frozen_reason(item, frozen, view_names)
            if reason:
                return reason
    return ""


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

# Every control that is written, which is the assignment's three plus the one
# the apparatus itself built. `channel_controls.CONTROL_BUILDERS` is the
# registry and this is the channel's declaration of the same set; the two are
# checked against each other in the tests rather than restated here as a
# count, because a count passes when one control is renamed and another is
# added. The fourth is `disconnect-bytes`, and it is the only control that
# catches a reviser whose bytes differ and whose behaviour does not.
WRITTEN_CONTROL_ROLES = ("known-effect", "no-op", "disconnect",
                         "disconnect-bytes")


def qualify_apparatus(controls: list) -> dict:
    """The qualification verdict, from the mandatory controls alone.

    No run outcome is an input. A control that produced the wrong effect
    makes the apparatus untrustworthy regardless of how good any run was.

    The three mandatory roles decide the verdict. A fourth control that was
    driven is reported, and a fourth that reports the wrong effect unqualifies
    the apparatus, but its absence does not: the committed E4 artifact
    records three controls, and requiring four would misread that history as
    an incomplete run.
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
    extra: dict = {}
    for role in WRITTEN_CONTROL_ROLES:
        if role in CONTROL_ROLES:
            continue
        control = by_role.get(role)
        if control is None:
            continue
        extra[role] = {"present": True,
                       "passed": bool(control.get("as_expected")),
                       "observed_delta": control.get("delta")}
        passed = passed and bool(control.get("as_expected"))
    verdict = {"qualification": QUALIFIED if passed else UNQUALIFIED,
               "qualified": passed,
               "checks": checks,
               "note": "qualification is a property of the machinery alone; it"
                       " says nothing about any run outcome"}
    if extra:
        verdict["additional_checks"] = extra
    return verdict


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
    if kind == "construct" and "strategy" not in inputs:
        # A construct action still carries the strategy name, because the
        # authored controls and lane C2's fixtures both rewrite that
        # binding. It no longer selects anything: the descendant's
        # construction is derived from the evidence the round gathered.
        # What is required is that the action is a construct request at
        # all, which is what this is.
        raise _frontier.Refused("construct needs a strategy label")
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


def _run_source(source: str, view: dict, state: dict, *, authority: dict,
                 operation_id: str, arm: str | None = None,
                 task_id: str | None = None,
                 artifact_digest: str | None = None,
                 parent_digest: str | None = None,
                 round_no: int | None = None) -> dict:
    """Execute `source` as policy, under an authority the caller holds.

    `authority` is the `{dsn, allocation_id}` the executor settles against
    and `operation_id` names this one execution. Both are named here, and
    every other keyword the executor accepts is named too, so nothing can
    arrive through `**evidence` and slip past the check at this boundary.
    """
    if not isinstance(authority, dict) or not authority.get("dsn") \
            or not authority.get("allocation_id") or not operation_id:
        raise _frontier.Refused(
            "refused: execution needs explicit authority and identity")
    return _method_exec.run_step_out_of_process(
        source, _step_view(view), dict(state),
        dsn=str(authority["dsn"]),
        allocation_id=str(authority["allocation_id"]),
        operation_id=str(operation_id), arm=arm, task_id=task_id,
        artifact_digest=artifact_digest, parent_digest=parent_digest,
        round_no=round_no)


@contextlib.contextmanager
def _disposable_authority(token: str):
    """A disposable store and allocation for one execution, and nothing else.

    The frontier world keeps its authority in its JSON document and has no
    settlement ledger, so there is no store the invl02 world could ask for a
    `dsn`. The executions still have to be attributable, so the honest
    source of authority is the one that actually attributes it: a store
    created here, for this execution, and dropped when it ends. It is
    separate from any live store by construction, because it never existed
    before the execution and does not exist after it, and the work it
    carries was obtained by running the bytes rather than by declining to
    run them.

    Bounded in `sandbox_calls`, the resource a `sandbox-exec` operation
    actually draws on, rather than in a number chosen to be large enough.
    The frontier document remains the authority for how many queries and
    steps a round may spend; this bounds what the executions behind those
    decisions cost in the ledger.
    """
    from . import s09_run_isolation as _isolation
    from settlement import authority as _authority

    admin = _isolation.admin_dsn()
    database = _isolation.create_disposable_db(token, admin_dsn=admin)
    try:
        handle = _authority.authorize_study(
            database.dsn, _isolation.study_root_for(token),
            authorized=1_000_000, allocation_id="%s-alloc" % token,
            ceilings={"sandbox_calls": 1_000})
        yield {"dsn": database.dsn, "allocation_id": handle.allocation_id}
    finally:
        _isolation.drop_disposable_db(database, admin_dsn=admin)


def _derived_operation_id(package: dict, arm: str, view: dict) -> str:
    """One execution's identity, derived rather than minted fresh.

    Derived from what the execution actually is, so a re-entry runs the same
    bytes against the same view under the same identity and a settled
    receipt is read back instead of re-running. It has to carry the view as
    well as the package and the arm, because `classify_revision` executes the
    same revision once per learner view. An identity that omitted the view
    would offer the broker one operation id with a different payload per
    view, which it refuses as a request-identity conflict, and it refuses
    correctly: those executions really are different work.
    """
    return "invl02-%s-%s-v%s" % (
        arm, str(package.get("package_digest", ""))[:16],
        _frontier.source_digest(_frontier.canonical(dict(view)))[:16])


@contextlib.contextmanager
def _execution_ledger(authority: dict | None, token: str,
                      operation_id: str | None):
    """The authority one execution runs under, and its identity.

    A caller that already holds a study store passes it and the execution
    joins that store's ledger. A caller that holds none gets a disposable
    one for the length of the execution. There is no third case: the
    executor refuses an execution with neither, and this is the boundary
    that decides which of the two a caller gets, so the choice is made once
    here rather than restated at each call site.

    `operation_id` is optional only where the caller derives one per
    execution; a caller that names one always has it validated here.
    """
    if authority is not None and (not authority.get("dsn")
                                  or not authority.get("allocation_id")):
        raise _frontier.Refused(
            "refused: execution needs explicit authority and identity")
    held = contextlib.nullcontext(authority) if authority is not None \
        else _disposable_authority(token)
    with held as store_authority:
        yield store_authority if operation_id is None else {
            **store_authority, "operation_id": str(operation_id)}


def _unwrap(outer: dict) -> dict:
    if not isinstance(outer, dict) or not isinstance(
            outer.get("inputs"), dict) or "frontier_action" not in \
            outer["inputs"]:
        raise _frontier.Refused("STEP envelope holds no frontier action")
    return dict(outer["inputs"]["frontier_action"])


def run_operate_step(package: dict, view: dict, state: dict, *,
                     authority: dict | None = None,
                     operation_id: str | None = None) -> dict:
    _frontier.validate_view(view)
    if view["purpose"] != _frontier.OPERATE:
        raise _frontier.Refused("operate runner got a %s view" % (
            view.get("purpose"),))
    with _execution_ledger(authority, "invl02-operate",
                           operation_id or _derived_operation_id(
                               package, "op", view)) as held:
        stepped = _run_source(package["op_source"], view, state,
                              authority=held,
                              operation_id=held["operation_id"])
    action = _frontier.validate_operate_action(_unwrap(
        stepped["action"]))
    return {"action": action, "state": stepped["state"],
            "executed_digest": stepped["source_digest"]}


def run_improve_step(package: dict, view: dict, state: dict, *,
                     authority: dict | None = None,
                     operation_id: str | None = None,
                     receipt_sink=None, arm: str | None = None,
                     task_id: str | None = None,
                     artifact_digest: str | None = None,
                     parent_digest: str | None = None,
                     round_no: int | None = None) -> dict:
    _frontier.validate_view(view)
    if view["purpose"] != _frontier.IMPROVE:
        raise _frontier.Refused("improve runner got a %s view" % (
            view.get("purpose"),))
    with _execution_ledger(authority, "invl02-improve",
                           operation_id or _derived_operation_id(
                               package, "imp", view)) as held:
        stepped = _run_source(package["imp_source"], view, state,
                              authority=held,
                              operation_id=held["operation_id"], arm=arm,
                              task_id=task_id, artifact_digest=artifact_digest,
                              parent_digest=parent_digest, round_no=round_no)
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


def leaf_construct(construction, parent: dict, round_no: int) -> dict:
    """Build the descendant a construction decision names, from its parent.

    `construction` is what the revision selected. It is substituted into
    the parent's own improvement source at the parent's probed input, so
    the descendant inherits its parent's procedure and runs the choice the
    revision made. It used to resolve `_STRATEGY_SOURCE[strategy]`
    instead, which meant a descendant ran a menu member's input however
    the revision selected and the reachable set was a two-member dict
    written at module scope.

    Accepts a bare integer, which is what the caller derives, and refuses
    the removed menu's `low`/`high` labels by name rather than resolving
    them against a table that no longer exists. The pair shape it accepted
    while the caller was mid-migration is gone with the migration.
    """
    if type(construction) is not int:
        raise _frontier.Refused(
            "the construction menu is gone; name the input the evidence"
            " selected instead of %r" % (construction,))
    if not 0 <= int(construction) < _N_INPUTS:
        raise _frontier.Refused("construction input is outside the"
                                " instrument's range")
    imp_source = _descendant_source(parent["imp_source"], int(construction))
    op_source = parent["op_source"]
    control_id = "control-x%d-r%d" % (int(construction), round_no)
    version = int(parent.get("version", 0)) + 1
    return {
        "control_id": control_id,
        "origin": ORIGIN,
        # `source_kind` is provenance, not a description of the selection,
        # and `validate_package` owns it. It says the bytes were authored
        # here rather than returned by a model, which is still true of a
        # descendant built from an authored parent. The procedure it now
        # inherits is carried by `imp_source` itself.
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
                        *, admit_probes: bool = False,
                        authority: dict | None = None) -> dict:
    """Drive one improvement round under an authority the caller can name.

    `authority` is the study store and allocation the round's executions
    settle against. A caller holding none, on a store that names no owner
    either, gets a disposable store for the length of the round. That is the
    fixture boundary, and it is honest there because the store makes no
    durable claim outliving the round.

    A caller holding none on an *owned* store is refused. Such a store records
    which investigation owns its unresolved work, so a round executing against
    a database created and dropped inside the round settles its receipts
    where that investigation cannot reach them. The production live path did
    exactly that and its receipts did not survive the round. A refusal makes
    the omission visible before the round rather than after its evidence.
    """
    granted = authority
    if granted is None and getattr(store, "identity", None) is not None:
        raise _frontier.Refused(
            "refused: an owned store executes under the authority its"
            " investigation authorizes, not under a disposable one")
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
    with contextlib.ExitStack() as ledger:
        for step in range(3):
            view = store.step_view(_frontier.IMPROVE, active)
            view["experience"] = list(round_obs)
            view["round"] = round_no
            operation_id = "invl02-improve-%s-r%d-s%d" % (
                active["package_digest"][:16], int(round_no), step)
            command = store.round_command(int(round_no), step)
            if command is not None:
                if not isinstance(command.get("receipt"), dict):
                    raise _frontier.Refused(
                        "round command receipt is incomplete")
                stepped = {
                    "action": dict(command["action"]),
                    "state": dict(command["state"]),
                    "executed_digest": command["executed_digest"],
                    "receipt": dict(command["receipt"]),
                }
            else:
                if granted is None:
                    # Entered here rather than above, because a round
                    # resumed from its durable command records executes
                    # nothing and so mints no authority, spends no
                    # allocation and creates no store.
                    granted = ledger.enter_context(
                        _disposable_authority("invl02-improve"))
                stepped = run_improve_step(
                    active, view, state, authority=granted,
                    operation_id=operation_id, arm=arm,
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
                # The construct action names a strategy, which no longer
                # selects anything. What selects the descendant is the
                # evidence the revision actually gathered in this round,
                # read here rather than resolved against a menu, so a
                # revision that probed differently reaches a different
                # descendant.
                candidate = leaf_construct(
                    construction_from_evidence(round_obs), active,
                    round_no)
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
        # The entry is appended rather than written through a store method
        # because the store has no round-result writer and `frontier.py` is
        # another lane's. What this closes is the hole the bare append opened:
        # the entry used to reach disk unvalidated and was only checked by
        # `_validate_round_results` at the next open, so a round could save a
        # document its own store refused to reopen. The store's own validator
        # is asked before the save, and the entry withdrawn if it refuses, so
        # nothing invalid is persisted and the refusal is the round's own.
        store._doc["round_results"].append(result)
        try:
            store._validate_round_results()
        except _frontier.Refused:
            store._doc["round_results"].pop()
            raise
    store.save()
    return {"candidate": candidate, "log": log,
            "observations": list(round_obs), "receipts": receipts}


def _round_identity(dsn: str | None, investigation_id: str | None):
    if (dsn is None) != (investigation_id is None):
        raise _frontier.Refused(
            "a fresh round names its store by dsn and investigation_id"
            " together; one of them identifies nothing")
    if dsn is None:
        return None
    return _frontier.StoreIdentity(investigation_id=investigation_id, dsn=dsn)


def fresh_round(store_path: str, round_no: int, *, dsn: str | None = None,
                investigation_id: str | None = None) -> dict:
    """Continue a live store's next improvement round in a fresh process.

    A restart is the same mission continuing, so it opens under the identity the
    store was created with. It used to open namelessly, and `_check_identity`
    refuses that on any document recording an owner, which is every store
    `live_construct.ensure_live_store` creates. The tree's only continuation
    entry could therefore continue only the stores no live run produces. The
    two names travel together for the reason `_live_identity` already gives:
    a `dsn` with no investigation names no row, and an investigation with no
    `dsn` names no row to address it on. Both absent is the fixture boundary
    and stays open.
    """
    store = _frontier.FrontierStore(
        store_path, identity=_round_identity(dsn, investigation_id))
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
    """Drive the argv surface a second process uses to continue a round.

    The two owner names are named options rather than trailing positionals. A
    positional pair made `fresh_round(store_path, round_no)` ambiguous between
    "a nameless store" and "an owned store whose names were forgotten", and it
    put the reader inside `fresh_round` when a call failed. Naming them makes
    the two-argument call the fixture boundary it always was, and makes an
    owned store a store that said so.
    """
    parser = argparse.ArgumentParser(prog="improve_channel")
    parser.add_argument("store_path")
    parser.add_argument("round_no", type=int)
    parser.add_argument("--dsn")
    parser.add_argument("--investigation-id", dest="investigation_id")
    args = parser.parse_args(argv[1:])
    summary = fresh_round(args.store_path, args.round_no, dsn=args.dsn,
                          investigation_id=args.investigation_id)
    sys.stdout.write(json.dumps(summary, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
