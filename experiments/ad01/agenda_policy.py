"""AD01 agenda policy: versioned decision-policy selection and one consumer.

Experiment entry selects tasks and treatments here; the shared runtime
owns lifecycle semantics. Two policies share the packet/action contract:
a fixed baseline proposer and the model policy. The DecisionConsumer is
the one gate every boundary decision passes: propose, admit, bounded
correction of the same decision, then continuation or stopping. Replacing
or disconnecting the consumer changes both domain runs; a raw proposer
callback alone can never close the gate because admission always runs
inside the consumer.
"""

from __future__ import annotations

BASELINE_POLICY_VERSION = "ad01-policy-baseline-v1"
MODEL_POLICY_VERSION = "ad01-policy-model-v1"
MAX_CORRECTIONS = 2

_TARGET_RELEASE_MARKERS = (
    "outside the admitted curriculum item",
    "outside world",
    "protected-use target",
    "unknown target",
    "no development target",
    "no curriculum item")


def _releases_pin(reason: str) -> bool:
    return any(marker in (reason or "")
               for marker in _TARGET_RELEASE_MARKERS)


def select_tasks(world: int, arm: str, tasks: list | None) -> list:
    if tasks is not None:
        return list(tasks)
    from . import trajectory as _trajectory
    return _trajectory._default_tasks(world, arm)


PORTFOLIO_POLICY_VERSION = "ad01-policy-portfolio-agenda-v1"
FIXED_POLICY_VERSION = "ad01-policy-portfolio-fixed-v1"

# What one unit of an E3 allocation is, stated because this repo has four
# budget currencies that never mix and an unmeasured cost is not zero.
#
# The E3 envelope is spent in *allocation units*: `Candidate.cost()` is
# `1 + diagnose_queries + max_queries`, a count of query allowance
# requested from the local instrument substrate. It is not a dispatch
# allowance, not an internal reservation, and not provider billing. Those
# are three other currencies and this study spends none of them:
# `selection.py` contains no gateway import, and both arms' diagnostics and
# reductions run through `trajectory.run_diagnostic` and
# `trajectory.dev_episode`, which are local and consult no provider.
#
# So the honest statement is that provider billing here is *not zero and
# not measured* -- it is absent by construction, and no E3 number in this
# module should be read as a cost figure in any other currency. `cost` is
# derived from the request rather than the outcome, so a failed operation
# still charges, which is what lets the envelope bind.
ALLOCATION_UNIT = "query-allowance count from Candidate.cost()"


class PortfolioPolicy:
    """Base for policies that read a portfolio and name the next candidate.

    A policy is handed the agenda state and returns a proposal or None.
    It never touches the store, never charges anything, and never learns
    the outcome of its own choice except through the state the run feeds
    back on the next turn.
    """

    version_id = PORTFOLIO_POLICY_VERSION

    def version(self) -> str:
        return self.version_id

    def stop_reason(self) -> str:
        return "policy declined"

    def propose(self, agenda) -> dict | None:
        raise NotImplementedError

    def observe(self, agenda, candidate, episode) -> None:
        """Read back the episode the run just executed. Default: ignore."""
        return None

    @staticmethod
    def _proposal(candidate, rationale) -> dict:
        return {"candidate": candidate, "rationale": rationale}


class AgendaPolicy(PortfolioPolicy):
    """Decide from run-time evidence: probe every capability, then deepen.

    The policy observes two things and nothing else: whether a candidate's
    development episode was retained, and how much the envelope is left.
    It never sees a held-out score. It tries every capability in a line
    once at the floor depth before retiring that line, because on this
    substrate a capability that fails at the floor can still retain with
    more room and one that holds at the floor can stop holding with more.
    """

    version_id = PORTFOLIO_POLICY_VERSION

    def __init__(self, *, families=("software", "graph"),
                 floor_queries=2):
        from . import selection
        self.families = tuple(families)
        self.floor_queries = int(floor_queries)
        self._untried = {family: list(selection.METHODS)
                         for family in self.families}
        self._live = {}
        self._stop = "portfolio exhausted"

    def stop_reason(self) -> str:
        return self._stop

    def _next_probe(self, agenda):
        """The next untried (family, capability) at the floor depth.

        A line is retired only once every capability in it has been tried
        and none retained, because on this substrate a capability that
        fails at the floor can still retain with more room and one that
        holds at the floor can stop holding with more. A line that retains
        is not probed again: it is deepened, which is the better use of
        the next unit.
        """
        for family in self.families:
            if family in self._live:
                continue
            methods = self._untried.get(family)
            if not methods:
                continue
            row = agenda.untried(family, methods[0], self.floor_queries) \
                or agenda.cheapest(family, methods[0], self.floor_queries)
            if row is not None:
                return family, methods[0], row
            methods.pop(0)
        return None

    def propose(self, agenda) -> dict | None:
        if self.floor_queries not in agenda.depths:
            raise ValueError(
                "floor_queries %d is not on the portfolio's depth ladder %r"
                % (self.floor_queries, agenda.depths))
        probe = self._next_probe(agenda)
        if probe is not None:
            family, method, row = probe
            if not agenda.afford(row):
                self._stop = "budget exhausted"
                return None
            return self._proposal(
                row, "untried capability %s in the %s line"
                     % (method, family))
        for family in sorted(self._live):
            state = self._live[family]
            depths = [d for d in agenda.depths if d > state["queries"]]
            if not depths:
                del self._live[family]
                continue
            deeper = agenda.cheapest(family, state["method"], depths[0])
            if not agenda.afford(deeper):
                self._stop = "budget exhausted"
                return None
            return self._proposal(
                deeper, "%s/%s is retained at %d queries, so deepen while "
                        "the envelope allows"
                        % (family, state["method"], state["queries"]))
        return None

    def observe(self, agenda, candidate, episode) -> None:
        family = candidate.family
        method = candidate.capability_id.rsplit("-", 1)[-1]
        if episode.get("disposition") != "retained":
            self._live.pop(family, None)
            methods = self._untried.get(family)
            if methods and method in methods:
                methods.remove(method)
            return
        state = self._live.setdefault(
            family, {"method": method, "queries": 0})
        state["method"] = method
        state["queries"] = candidate.max_queries


class FixedPolicy(PortfolioPolicy):
    """A pre-committed allocation: one capability and depth per family.

    `rule` may name a different constant pair per budget, which is what
    `fitted_fixed_rule` supplies. A rule fitted on development retention
    alone stays a control: it is chosen before the run from a signal the
    agenda never reads, so it is blind in the sense that matters, and it is
    not a strawman, because it is the best its own search space can do on
    that signal.

    `DEFAULT_RULE` is retained because committed evidence and
    `test_s09_e3_selection` were produced under it, and it is no longer
    claimed to be the strongest rule its search space contains. It was not
    at this tip, at any budget: an exhaustive search over both
    capabilities and depths 1-7 finds a higher-scoring pair at budgets 20,
    30 and 60 and none at 40. `fitted_fixed_rule` is the honest control and
    this constant is the historical one; `tests/test_s09_e3_fitted_control.py`
    measures the distance rather than leaving it in a docstring.

    The control observes nothing at run time. That is the property under
    test, not a handicap, and it is demonstrated rather than asserted in
    `test_the_control_cannot_observe_run_time_state`.
    """

    version_id = FIXED_POLICY_VERSION

    DEFAULT_RULE = {"software": ("ddmin", 5), "graph": ("ddmin", 1)}

    def __init__(self, rule=None, *, budget=None):
        from . import selection
        if rule is None and budget is not None:
            rule = fitted_fixed_rule(budget)["rule"]
        self.rule = dict(rule or self.DEFAULT_RULE)
        for family in selection.FAMILIES:
            method, queries = self.rule[family]
            if method not in selection.METHODS:
                raise ValueError("unknown method %r" % (method,))
            if not isinstance(queries, int) or queries < 1:
                raise ValueError("max_queries must be a positive integer")
        self._step = 0
        self._stop = "pre-committed schedule complete"

    def version(self) -> str:
        return "%s:%s" % (self.version_id,
                          ";".join("%s=%s/%d" % (family, *self.rule[family])
                                   for family in sorted(self.rule)))

    def stop_reason(self) -> str:
        return self._stop

    def plan(self) -> list:
        """The schedule this control commits to, in order.

        Each family's capability is deepened one query at a time up to its
        committed depth, and the families are interleaved so a control
        under a tight envelope still qualifies both of them rather than
        spending everything on whichever sorts first.
        """
        steps = []
        depth = max(depth for _method, depth in self.rule.values())
        for step in range(1, depth + 1):
            for family in sorted(self.rule):
                method, committed = self.rule[family]
                if step <= committed:
                    steps.append((family, method, step, committed))
        return steps

    def propose(self, agenda) -> dict | None:
        plan = self.plan()
        if self._step >= len(plan):
            return None
        family, method, step, depth = plan[self._step]
        row = agenda.cheapest(family, method, step)
        if row is None:
            self._stop = "portfolio does not offer %s/%s at depth %d" % (
                family, method, step)
            return None
        if not agenda.afford(row):
            self._stop = "budget exhausted"
            return None
        self._step += 1
        return self._proposal(
            row, "pre-committed %s/%s step %d of %d" % (family, method,
                                                        step, depth))


def agenda_policy(**kwargs) -> AgendaPolicy:
    return AgendaPolicy(**kwargs)


def fixed_policy(rule=None, *, budget=None) -> FixedPolicy:
    """The control arm. `budget` selects the fitted rule for that envelope.

    With neither argument the historical `DEFAULT_RULE` is used, which is
    what the committed evidence was produced under. With `budget` the rule
    is the development-fitted one for that envelope.
    """
    return FixedPolicy(rule, budget=budget)


FITTED_DEPTHS = (1, 2, 3, 4, 5, 6, 7)
FITTED_OBJECTIVE = "retained_behaviors"
FITTED_RULE_VERSION = "ad01-policy-portfolio-fixed-fitted-v1"
_FITTED_CACHE: dict = {}


def fitted_fixed_rule(budget: int, *, worlds=None,
                      objective: str = FITTED_OBJECTIVE) -> dict:
    """The best pre-committed rule for `budget`, fitted on development yield.

    The search space is every (capability, depth) pair over both families,
    the same ladder the agenda walks, and the objective is
    `retained_behaviors`: development episodes the checker returned
    preserved for. It is deliberately *not* `held_out_reduction`. Fitting
    on the reported metric would make the control an oracle for the metric
    the comparison reads, and the comparison would then measure a held-out
    score against itself -- the circularity C15 records, one level up.

    The distinction is the whole point of this function, and it is
    measurable rather than asserted. At budget 60 the development-fitted
    rule reaches 0.187032 mean held-out reduction where an exhaustive
    held-out search reaches 0.414277, so the fit is nowhere near the
    oracle and is not secretly one. A development signal that could not
    see held-out quality would not produce that gap.

    The rule is a function of `budget` and the world list only. Both are
    fixed before the run -- the envelope is a property of the study, the
    worlds are the qualified set -- so the control's allocation cannot
    depend on anything the agenda chose. `blindness` reports that
    dependency explicitly so a test can assert on it rather than trust it.

    `budget` is an allocation-unit count, not a dispatch count. See
    `ALLOCATION_UNIT`.
    """
    from . import selection
    worlds = tuple(worlds or selection.WORLDS)
    key = (int(budget), worlds, objective)
    cached = _FITTED_CACHE.get(key)
    if cached is not None:
        return _copy_fitted(cached)
    best = None
    for sw_method in selection.METHODS:
        for gr_method in selection.METHODS:
            for sw_depth in FITTED_DEPTHS:
                for gr_depth in FITTED_DEPTHS:
                    rule = {"software": (sw_method, sw_depth),
                            "graph": (gr_method, gr_depth)}
                    score = 0
                    for world in worlds:
                        run = selection.run_investigations(
                            None, FixedPolicy(rule),
                            selection.Allocation(authorized=budget),
                            world=world)
                        score += getattr(run.yield_, objective)
                    if best is None or score > best[0]:
                        best = (score, rule)
    payload = {
        "rule": best[1],
        "budget": int(budget),
        "objective": objective,
        "objective_reads_held_out": objective == "held_out_reduction",
        "worlds": list(worlds),
        "depths": list(FITTED_DEPTHS),
        "fitted_retained": best[0],
        "version": FITTED_RULE_VERSION,
        "inputs_are_fixed_before_the_run": ["budget", "worlds", "depths",
                                             "methods", "objective"],
        "blindness": (
            "the rule is a function of the envelope, the qualified world "
            "list and the search grid. It never reads an agenda, a "
            "candidate ranking, a diagnostic observation or a held-out "
            "score, so no decision the treatment made can reach it."),
    }
    _FITTED_CACHE[key] = payload
    return _copy_fitted(payload)


def _copy_fitted(payload: dict) -> dict:
    """A copy deep enough that a caller cannot edit the cached rule.

    `rule` maps a family to a tuple, so a shallow `dict(payload)` would hand
    out the cached dict itself and let one caller rewrite the arm every
    later caller receives. A control whose constants a test or a run could
    mutate in place is not pre-committed, which is the property this whole
    module exists to establish.
    """
    out = dict(payload)
    out["rule"] = {family: tuple(value)
                   for family, value in payload["rule"].items()}
    out["worlds"] = list(payload["worlds"])
    out["depths"] = list(payload["depths"])
    out["inputs_are_fixed_before_the_run"] = list(
        payload["inputs_are_fixed_before_the_run"])
    return out


def constant_rule_search(budget: int, *, worlds=None,
                         depths: tuple = FITTED_DEPTHS,
                         objective: str = "held_out_reduction") -> dict:
    """Every constant rule in the space, scored at one budget. The yardstick.

    `fitted_fixed_rule` picks the best rule on `retained_behaviors`, a
    signal a control is allowed to see. This walks the identical space on
    `held_out_reduction`, the signal the study *reports*, and keeps all
    196 scores rather than only the winner.

    The distinction matters because the two answers disagree. A control
    can be optimal on the objective it was fitted to and still be beaten
    on the reported one, and when that happens the arm that "lost" did not
    lose to the best available rule -- it lost to a worse one. Reporting
    a comparison without the best score in the space makes every
    advantage an advantage over an opponent of unstated strength.

    It is an oracle by construction and says so: it reads the reported
    metric to rank rules, which no run-time control may do. It exists to
    qualify other controls, never to be an arm. The
    `reads_the_reported_metric` flag is the machine-readable version of
    that, so a caller wiring this into a ladder cannot do so by accident.
    """
    from . import selection
    worlds = tuple(worlds or selection.WORLDS)
    scores = _score_constant_rules(budget, worlds, depths, objective)
    best_score, best_rule = max(
        scores, key=lambda pair: (pair[0], _rule_key(pair[1])))
    return {
        "budget": int(budget),
        "objective": objective,
        "worlds": list(worlds),
        "depths": list(depths),
        "searched": len(scores),
        "best_score": best_score,
        "best_rule": {family: tuple(value)
                      for family, value in best_rule.items()},
        "reads_the_reported_metric": objective == "held_out_reduction",
        "use": "qualify a control; never an arm in a reported ladder",
    }


def _score_constant_rules(budget: int, worlds: tuple, depths: tuple,
                          objective: str) -> list:
    """[(mean score, rule)] over the whole constant space, in a stable order.

    The aggregation is a mean over `worlds`, and it has to be. Every consumer
    of this function reads the score beside a per-arm mean over the same
    worlds: `e3_ladder._aggregate` divides by its cell count, and
    `qualified_ladder` publishes `held_out_reduction_mean` next to the
    yardstick this function produces. A sum there is three times the scale of
    everything it is read against, and the consequence is not a scale
    difference that cancels -- a sum grows with the length of `worlds`, so
    the same rule scored differently on a three-world search and a one-world
    search. `rules_beating_it` and `gap_to_best` are counted off these
    numbers, so the handicap that qualifies every reported E3 arm was partly
    a count of worlds.

    A mean is invariant to how many times a value is folded in, which is the
    property that lets two searches over different world sets be compared at
    all. The mean is also what `held_out_reduction` already is on the
    instrument: `selection.Yield` types it a rate in `[0, 1]`, so a score
    above 1.0 is a sum and a score in range is a mean.
    """
    from . import selection
    scores = []
    for sw_method in selection.METHODS:
        for gr_method in selection.METHODS:
            for sw_depth in depths:
                for gr_depth in depths:
                    rule = {"software": (sw_method, sw_depth),
                            "graph": (gr_method, gr_depth)}
                    scores.append((sum(
                        selection.run_investigations(
                            None, FixedPolicy(rule),
                            selection.Allocation(authorized=budget),
                            world=world).yield_.as_dict()[objective]
                        for world in worlds) / len(worlds), rule))
    return scores


def _rule_key(rule: dict) -> str:
    """A hashable, order-stable identity for a rule.

    Comparing rules by dict equality would be enough inside this module,
    but the counts here are reported and then re-derived by a reader, so
    the identity has to survive being written down and read back.
    """
    import json
    return json.dumps([rule["software"], rule["graph"]], sort_keys=True)


def control_competence(budget: int, *, worlds=None,
                       depths: tuple = FITTED_DEPTHS) -> dict:
    """How strong each fixed arm actually is at `budget`, against the space.

    This is the measurement `TASKS.md` C18 was opened for. It answers one
    question per control -- "how many of the 196 constant rules beat
    this one, here" -- and it answers it for every budget in the ladder,
    not for the single budget a module constant happened to name.

    The per-budget counts are the sharp form of the claim. "The default is
    not optimal at 20 and 30" is a claim about two budgets a reader has to
    re-derive; "96 and 94 of 196 rules beat it" is a number that either
    still holds or has visibly moved, and it moves if the substrate
    changes underneath the claim.

    Both fixed arms are scored from one pass over the space. The search
    runs 196 rules over three worlds and dominates everything else here,
    so scoring the arms separately would double the cost to re-derive two
    numbers the search already has.
    """
    from . import selection
    worlds = tuple(worlds or selection.WORLDS)
    scores = _score_constant_rules(budget, worlds, depths,
                                   "held_out_reduction")
    by_rule = {_rule_key(rule): score for score, rule in scores}
    best = max(by_rule.values())
    best_key = next(key for key, value in by_rule.items() if value == best)
    best_rule = next(rule for _score, rule in scores
                     if _rule_key(rule) == best_key)
    rows = []
    for name, rule in (("control", FixedPolicy.DEFAULT_RULE),
                       ("fitted_control", fitted_fixed_rule(budget)["rule"])):
        key = _rule_key(rule)
        score = by_rule[key]
        beaten = sum(1 for other, value in by_rule.items()
                     if other != key and value > score)
        rows.append({
            "arm": name,
            "rule": {family: tuple(value)
                     for family, value in rule.items()},
            "held_out_reduction": score,
            "rules_beating_it": beaten,
            "optimal_here": beaten == 0,
            "gap_to_best": best - score,
        })
    return {
        "budget": int(budget),
        "searched": len(scores),
        "best_rule": {family: tuple(value)
                      for family, value in best_rule.items()},
        "best_held_out_reduction": best,
        "arms": rows,
    }


def fitted_control(budget: int, **kwargs) -> FixedPolicy:
    """The fitted control for one envelope, as a policy instance.

    The fit is memoized because it is a pure function of its arguments and
    the crossover builds one policy per (budget, arm); re-running a
    196-combination search per cell bought nothing and made the ladder slow
    enough to discourage adding the arm at all.
    """
    return FixedPolicy(fitted_fixed_rule(budget, **kwargs)["rule"])


def scaffolding_proposer(task_id: str, seed_obs: dict):
    def _propose(seen: dict, asked: dict) -> dict:
        from . import trajectory as _trajectory
        proposal = _trajectory.propose_investigation(
            {"observations": [seed_obs]}, {})
        proposal["next_action"] = {
            "kind": "diagnostic",
            "diagnostic": _trajectory._family(task_id),
            "task_id": task_id}
        return proposal
    return _propose


def _correction_rows(dsn: str, aid: str) -> list:
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT content FROM attempt_observations"
            " WHERE attempt_id = %s ORDER BY id",
            (aid,)).fetchall()
        conn.commit()
    return [dict(r["content"] or {}) for r in rows
            if dict(r.get("content") or {}).get("kind") == "correction"]


def _restored_correction(rows: list) -> dict | None:
    for row in reversed(rows):
        failure = row.get("failure")
        if isinstance(failure, dict) and failure:
            return dict(failure)
    return None


def _boundary_calls(dsn: str, cid: str, seq: int) -> int:
    from psycopg.rows import dict_row
    from settlement import db
    with db.connect(dsn, row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM operations o"
            " WHERE (starts_with(o.id, %s)"
            " OR starts_with(o.id, %s))"
            " AND o.payload->>'effect' = 'model-inference'",
            ("ad01-%s-learner-%d" % (cid, seq),
             "ad01-%s-b%d-" % (cid, seq))).fetchone()
        conn.commit()
    return int(row["n"])


class DecisionConsumer:
    """Shared propose/admit/correct gate for one campaign."""

    def __init__(self, *, proposer=None, admit=None, dsn=None,
                 cid="", charter=None, world=0, arm="I",
                 allocation_id="", study_root="",
                 gateway=None, model="",
                 max_corrections=MAX_CORRECTIONS,
                 policy_version=MODEL_POLICY_VERSION):
        self._proposer = proposer
        self._admit = admit
        self._dsn = dsn
        self._cid = cid
        self._charter = charter or {}
        self._world = world
        self._arm = arm
        self._allocation_id = allocation_id
        self._study_root = study_root
        self._gateway = gateway
        self._model = model
        self._disconnected = None
        self._max_corrections = max_corrections
        self.policy_version = policy_version
        self.decided: list = []

    def _corrections_used(self, aid: str | None) -> int:
        if self._dsn is None or aid is None:
            return 0
        return len(_correction_rows(self._dsn, aid))

    def _journal_correction(self, aid: str, number: int,
                            failure: dict) -> None:
        if self._dsn is None or aid is None:
            return
        from . import trajectory as _trajectory
        from settlement import store
        from settlement.common import Command
        store.acquire_work(
            self._dsn, Command(
                request_id="acquire-%s" % aid,
                payload={"investigation_id": self._cid,
                         "attempt_id": aid,
                         "allocation_id": _trajectory._alloc_id(
                             self._cid),
                         "composition": "ad01-boundary",
                         "owner": self._cid}))
        store.submit_observation(
            self._dsn, Command(
                request_id="correct-%s-%d" % (aid, number),
                payload={"attempt_id": aid,
                         "content": {"kind": "correction",
                                     "number": number,
                                     "failure": failure}}))

    def _refuse(self, reason: str, corrections: int) -> dict:
        return {"status": "refused", "reason": reason,
                "corrections": corrections}

    def _note_refusal(self, corrente: int, failure: dict,
                      aid: str | None) -> dict | None:
        if corrente >= self._max_corrections:
            return self._refuse(
                "admission refused after %d bounded correction(s): %s"
                % (corrente, failure["reason"]), corrente)
        self._journal_correction(aid, corrente + 1, failure)
        return None

    def decide(self, seen: dict, asked: dict, *, boundary,
               experience: dict, aid: str | None = None) -> dict:
        if self._disconnected is not None:
            return self._refuse(
                "decision consumer disconnected: %s"
                % self._disconnected, 0)
        proposer = self._proposer
        if proposer is None and self._gateway is not None \
                and self._dsn is not None:
            from .learner import propose_from_model
            proposer = propose_from_model(
                self._dsn, cid=self._cid, gateway=self._gateway,
                model=self._model, charter=dict(self._charter),
                world=self._world, arm=self._arm,
                allocation_id=self._allocation_id)
        admit = self._admit
        if admit is None:
            from .trajectory import admit_investigation
            admit = admit_investigation
        if proposer is None:
            return self._refuse("decision consumer has no proposer", 0)
        made = self._corrections_used(aid)
        if made >= self._max_corrections:
            return self._refuse(
                "correction budget exhausted (%d/%d corrections used)"
                % (made, self._max_corrections), made)
        prior = None
        required_target = None
        if made and self._dsn is not None and aid is not None:
            prior = _restored_correction(
                _correction_rows(self._dsn, aid))
            if isinstance(prior, dict):
                required_target = prior.get("target")
        resumed = prior is not None
        entry_made = made
        pending_allowance = 0
        if resumed and aid is not None:
            seq = (boundary or {}).get("seq")
            if isinstance(seq, int):
                pending_allowance = _boundary_calls(
                    self._dsn, self._cid, seq)
        while True:
            attempt_seen = dict(seen)
            if prior is not None:
                attempt_seen["prior_failure"] = prior
            if pending_allowance:
                remaining = dict(attempt_seen.get("remaining") or {})
                if isinstance(remaining.get("model_calls"), int):
                    remaining["model_calls"] += pending_allowance
                    attempt_seen["remaining"] = remaining
            attempt_seen["correction_attempt"] = made
            try:
                proposal = proposer(attempt_seen, asked)
            except Exception as exc:
                reason = str(exc) or type(exc).__name__
                if resumed and made == entry_made \
                        and "left no settled response" in reason:
                    made += 1
                    continue
                failure = {"target": required_target,
                           "reason": reason, "attempt": made}
                ended = self._note_refusal(made, failure, aid)
                if ended is not None:
                    return ended
                made += 1
                prior = failure
                continue
            admitted = admit(proposal, experience, asked,
                               boundary)
            if admitted.get("decision") == "admitted":
                investigation = admitted["investigation"]
                target = (investigation.get("next_action") or {}).get(
                    "task_id")
                if required_target is not None \
                        and target != required_target \
                        and not _releases_pin(prior["reason"]):
                    reason = ("correction-changed-target: %r is not the"
                              " refused %r" % (target, required_target))
                    failure = {"target": required_target,
                               "reason": reason, "attempt": made}
                    ended = self._note_refusal(made, failure, aid)
                    if ended is not None:
                        return ended
                    made += 1
                    prior = failure
                    continue
                self.decided.append(target)
                return {"status": "admitted",
                        "investigation": investigation,
                        "corrections": made}
            reason = admitted.get("reason", "refused")
            action = proposal.get("next_action") or {}
            target = action.get("task_id")
            if required_target is None:
                required_target = target
            elif target != required_target:
                if _releases_pin(reason):
                    required_target = target
                else:
                    reason = ("correction-changed-target: %r is not the"
                              " refused %r" % (target, required_target))
            failure = {"target": required_target, "reason": reason,
                       "attempt": made}
            ended = self._note_refusal(made, failure, aid)
            if ended is not None:
                return ended
            made += 1
            prior = failure


def disconnected_consumer(reason: str) -> DecisionConsumer:
    consumer = DecisionConsumer()
    consumer._disconnected = reason
    return consumer


def step_policy_version() -> str:
    from . import policy_step
    return policy_step.POLICY_STEP_VERSION


_STEP_TO_LEGACY = {
    "diagnose": "diagnostic",
    "construct_method": "development",
    "use_method": "use_method",
}


def _step_remaining(seen: dict, steps_left: int) -> dict:
    remaining = dict((seen or {}).get("remaining") or {})
    remaining["policy_steps"] = int(steps_left)
    return remaining


def _step_proposal(action: dict, seen: dict, asked: dict,
                   boundary: dict | None, family: str | None) -> dict:
    inputs = dict(action.get("inputs") or {})
    target = action.get("target")
    kind = action.get("kind")
    question = inputs.get("question") or "policy step %s on %s" % (
        kind, target)
    proposal = {
        "basis_references": list(action.get("evidence_refs") or []),
        "question": question,
        "unknown": inputs.get("unknown") or question,
        "requested_resources": dict(
            action.get("requested_resources") or {}),
        "charter": (asked or {}).get("objective", ""),
    }
    if kind == "diagnose":
        proposal["next_action"] = {
            "kind": "diagnostic",
            "diagnostic": inputs.get("diagnostic", "software"),
            "task_id": target}
    else:
        development = {
            "kind": _STEP_TO_LEGACY[kind],
            "diagnostic": family or inputs.get("diagnostic",
                                               "software"),
            "task_id": target}
        if type(inputs.get("max_queries")) is int \
                and inputs["max_queries"] >= 0:
            development["max_queries"] = inputs["max_queries"]
        if kind == "use_method" and isinstance(
                inputs.get("method_id"), str):
            development["method_id"] = inputs["method_id"]
        proposal["next_action"] = development
    return proposal


def _step_family(target: object) -> str | None:
    from . import trajectory as _trajectory
    try:
        return _trajectory._family(target)
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def _policy_settled_text(dsn: str, operation_id: str) -> str | None:
    from settlement import db
    with db.connect(dsn) as conn:
        row = conn.execute(
            "SELECT content FROM receipts WHERE operation_id = %s"
            " AND receipt_identity = %s AND outcome = 'success'",
            (operation_id, "gw:%s" % operation_id)).fetchone()
        conn.commit()
    if row is None:
        return None
    return str(dict(row[0] or {}).get("text", ""))


def _cached_policy_decision(cached: dict | None,
                           source_digest: str) -> dict | None:
    if cached is None:
        return None
    output = dict(cached["policy_output"] or {})
    results = list(output.get("results") or [])
    accepted = dict(cached["accepted_action"] or {})
    if not results or not accepted:
        return None
    if output.get("source_digest") != source_digest:
        raise ValueError("cached STEP state source digest mismatch")
    if accepted.get("status") == "pending":
        return {"status": "pending", "investigation": accepted,
                "cached": cached}
    if isinstance(accepted.get("next_action"), dict):
        return {"status": "admitted", "investigation": accepted,
                "corrections": len(results) - 1}
    if accepted.get("status") == "refused":
        return {"status": "refused", "reason": accepted.get(
            "reason", "refused"), "corrections": len(results)}
    return None


class StepPolicyConsumer(DecisionConsumer):
    """Trusted gate for versioned STEP policy artifacts.

    The artifact source never runs in this process and never becomes a
    proposer callback. Each STEP call executes in the bounded child
    through method_exec; every returned action passes the same trusted
    admission as any other proposal; model requests become broker
    operations whose settled responses return as next-step
    observations. Admission, evaluation and grants stay driver-owned.
    """

    def __init__(self, *, policy: dict, dsn=None, cid="",
                 charter=None, world=0, arm="I", allocation_id="",
                 study_root="", gateway=None, model="",
                 max_policy_steps=6, timeout_ms=None,
                 cpu_seconds=None, max_output_bytes=None,
                 policy_version=None):
        from . import policy_step
        super().__init__(
            proposer=None, admit=None, dsn=dsn, cid=cid,
            charter=charter, world=world, arm=arm,
            allocation_id=allocation_id, study_root=study_root,
            gateway=gateway, model=model,
            policy_version=policy_version
            or policy_step.POLICY_STEP_VERSION)
        self._policy = policy_step.verify_policy_record(policy)
        self._policy_source = policy["policy_source"]
        self._max_policy_steps = max_policy_steps
        self._timeout_ms = timeout_ms or policy_step.STEP_TIMEOUT_MS
        self._cpu_seconds = cpu_seconds or policy_step.STEP_CPU_SECONDS
        self._max_output_bytes = max_output_bytes \
            or policy_step.STEP_MAX_OUTPUT_BYTES

    def _model_request(self, action: dict, remaining: dict,
                       step_index: int) -> tuple:
        from settlement import broker
        from settlement.common import ResultCode
        from . import policy_step
        from . import trajectory as _trajectory
        inputs = dict(action.get("inputs") or {})
        prompt = inputs.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.strip():
            return None, {"status": "error",
                          "reason": "model request needs a prompt"}
        if len(prompt.encode()) > policy_step.MODEL_PROMPT_LIMIT_CHARS:
            return None, {"status": "error",
                          "reason": "model prompt exceeds %d chars"
                          % policy_step.MODEL_PROMPT_LIMIT_CHARS}
        operation_id = "ad01-%s-policy-s%d-model-k%d" % (
            self._cid, self._seq, step_index)
        settled = (_policy_settled_text(self._dsn, operation_id)
                   if self._dsn is not None else None)
        existing = (broker.read_operation(self._dsn, operation_id) is not None
                    if self._dsn is not None else False)
        if settled is None and not existing and int(
                remaining.get("model_calls", 0)) <= 0:
            return None, {"status": "refused",
                          "reason": "model call cap reached",
                          "operation_id": operation_id}
        if self._dsn is None or (settled is None and self._gateway is None):
            return None, {"status": "refused",
                          "reason": "policy requested model reasoning"
                          " without a gateway and store"}
        tokens = inputs.get("max_output_tokens", 256)
        if type(tokens) is not int or tokens <= 0 or tokens > 2048:
            return None, {"status": "error",
                          "reason": "max_output_tokens must be 1..2048"}
        if settled is None:
            ensured = broker.ensure_operation(
                self._dsn, operation_id=operation_id,
                effect=broker.MODEL_INFERENCE,
                payload={"model": self._model or "policy-request",
                         "messages": [{"role": "user",
                                       "content": prompt}],
                         "max_output_tokens": tokens,
                         "deadline_ms": 300_000,
                         "reasoning_effort":
                         _trajectory.reasoning_effort()},
                allocation_id=self._allocation_id
                or _trajectory._alloc_id(self._cid))
            if ensured.code not in (ResultCode.APPLIED,
                                    ResultCode.ALREADY_APPLIED):
                return None, {"status": "refused",
                              "reason": "model call not admitted: %s"
                              % ensured.detail,
                              "operation_id": operation_id}
            broker.dispatch_operation(
                self._dsn, operation_id, launchers={},
                gateway=self._gateway)
            settled = _policy_settled_text(self._dsn, operation_id)
            if settled is None:
                return None, {"status": "refused",
                              "reason": "model call %s left no settled"
                              " response" % operation_id,
                              "operation_id": operation_id}
        import hashlib
        try:
            body = settled if isinstance(settled, str) else str(settled)
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        except Exception:
            body = ""
            digest = hashlib.sha256(b"").hexdigest()
        shown = body[:policy_step.MODEL_RESPONSE_VIEW_CHARS]
        return {"operation_id": operation_id, "digest": digest,
                "text": shown,
                "truncated": len(body) > len(shown)}, None

    def decide(self, seen: dict, asked: dict, *, boundary,
               experience: dict, aid: str | None = None) -> dict:
        from . import policy_step
        from . import trajectory as _trajectory
        from . import worlds as _worlds
        if self._disconnected is not None:
            return self._refuse(
                "decision consumer disconnected: %s"
                % self._disconnected, 0)
        seq = (boundary or {}).get("seq", 0)
        self._seq = int(seq) if isinstance(seq, int) else 0
        observations = list((seen or {}).get("observations") or [])
        if not observations:
            return self._refuse("policy step needs a seed observation",
                                0)
        task_id = observations[-1].get("task_id")
        try:
            task = _worlds.load_task(_worlds.FROZEN_DIR, task_id)
        except (KeyError, TypeError):
            return self._refuse("unknown policy task %r" % (task_id,),
                                0)
        eligible = sorted({m.get("capability_id")
                           for m in (seen or {}).get("retained") or []
                           if isinstance(m, dict)
                           and m.get("capability_id")})
        source_digest = self._policy["source_digest"]
        cached = policy_step.load_policy_state(
            self._dsn, self._cid, self._seq) \
            if self._dsn is not None else None
        resumed = _cached_policy_decision(cached, source_digest)
        if resumed is not None and resumed["status"] != "pending":
            return resumed
        open_questions: list = []
        last_result = None
        state: dict = policy_step.load_prior_final_state(
            self._dsn, self._cid, self._seq)
        views: list = []
        results: list = []
        transitions: list = []
        resume_action = None
        start_index = 0
        if resumed is not None:
            cached = resumed["cached"]
            payload = dict(cached["policy_input"] or {})
            views = list(payload.get("views") or [])
            results = list(dict(cached["policy_output"] or {}).get(
                "results", []) or [])
            transition = dict(cached["state_transition"] or {})
            transitions = list(transition.get("transitions") or [])
            state = dict(transition.get("final_state") or {})
            resume_action = dict(resumed["investigation"]["next_action"])
            start_index = len(results) - 1
        packet_allowance = int(
            (dict((seen or {}).get("remaining") or {}).get(
                "model_calls", 6)))
        entry_model = policy_step.durable_model_calls(
            self._dsn, self._cid, self._seq)
        for index in range(start_index, self._max_policy_steps):
            durable_now = policy_step.durable_model_calls(
                self._dsn, self._cid, self._seq)
            spent = durable_now - entry_model
            model_remaining = min(packet_allowance - spent,
                                  6 - durable_now)
            steps_remaining = self._max_policy_steps - index
            remaining = _step_remaining(seen, steps_remaining)
            remaining["model_calls"] = max(int(model_remaining), 0)
            operation_id = "ad01-%s-policy-s%d-k%d" % (
                self._cid, self._seq, index)
            if resume_action is None:
                view = policy_step.materialize_view(
                    task=task, observations=observations,
                    open_questions=open_questions, last_result=last_result,
                    eligible_methods=eligible, remaining=remaining)
                try:
                    stepped = policy_step.run_policy_step(
                        {"artifact": self._policy,
                         "policy_source": self._policy_source},
                        view, state, timeout_ms=self._timeout_ms,
                        cpu_seconds=self._cpu_seconds,
                        max_output_bytes=self._max_output_bytes,
                        dsn=self._dsn,
                        allocation_id=self._allocation_id
                        or _trajectory._alloc_id(self._cid),
                        operation_id=operation_id
                        if self._dsn is not None else None)
                except Exception as exc:
                    views.append(view)
                    policy_step.persist_step_transition(
                        self._dsn, self._cid, self._seq, views=views,
                        results=results, transitions=transitions,
                        investigation={"status": "refused",
                                       "reason": "policy step failed: %s"
                                       % exc},
                        source_digest=source_digest,
                        status="incorporated")
                    return self._refuse("policy step failed: %s" % exc,
                                        index)
                action = stepped["action"]
                previous = dict(state)
                state = dict(stepped["state"])
                views.append(view)
                results.append({"action": action, "state": state,
                                "operation_id": operation_id})
                transitions.append({"previous": previous, "next": state})
            else:
                action = resume_action
                resume_action = None
            kind = action["kind"]
            if kind == "request_model":
                policy_step.persist_step_transition(
                    self._dsn, self._cid, self._seq, views=views,
                    results=results, transitions=transitions,
                    investigation={"status": "pending",
                                   "next_action": action,
                                   "operation_id":
                                   "ad01-%s-policy-s%d-model-k%d" % (
                                       self._cid, self._seq, index)},
                    source_digest=source_digest)
                response, failure = self._model_request(
                    action, remaining, index)
                if failure is not None:
                    last_result = dict(failure)
                    last_result.setdefault(
                        "operation_id",
                        "ad01-%s-policy-s%d-model-k%d" % (
                            self._cid, self._seq, index))
                    open_questions.append(last_result.get(
                        "reason", "refused"))
                    continue
                last_result = {"kind": "model_response",
                               "digest": response["digest"],
                               "text": response["text"],
                               "truncated": response["truncated"],
                               "operation_id": response["operation_id"]}
                continue
            if kind in _STEP_TO_LEGACY:
                proposal = _step_proposal(
                    action, seen, asked, boundary,
                    _step_family(action.get("target")))
                admitted = _trajectory.admit_investigation(
                    proposal, seen, asked, boundary)
                if admitted.get("decision") != "admitted":
                    last_result = {"status": "refused",
                                   "reason": admitted.get(
                                       "reason", "refused")}
                    open_questions.append(last_result["reason"])
                    continue
                investigation = admitted["investigation"]
                policy_step.persist_step_transition(
                    self._dsn, self._cid, self._seq, views=views,
                    results=results, transitions=transitions,
                    investigation=investigation,
                    source_digest=stepped["source_digest"])
                self.decided.append(
                    (investigation.get("next_action") or {}).get(
                        "task_id"))
                return {"status": "admitted",
                        "investigation": investigation,
                        "corrections": index}
            if kind == "propose_revision":
                inputs = dict(action.get("inputs") or {})
                investigation = {
                    "basis_references": [
                        r for r in action.get("evidence_refs") or []
                        if isinstance(r, str)],
                    "question": inputs.get("question")
                    or "policy proposed revision",
                    "revision_proposal": {
                        "scope": inputs.get("scope", {}),
                        "parent_digest":
                        self._policy["source_digest"],
                        "motivation": inputs.get("motivation", ""),
                    },
                    "next_action": {
                        "kind": "policy_revision",
                        "task_id": action.get("target"),
                        "reason": inputs.get(
                            "reason", "policy proposed revision")},
                }
                policy_step.persist_step_transition(
                    self._dsn, self._cid, self._seq, views=views,
                    results=results, transitions=transitions,
                    investigation=investigation,
                    source_digest=stepped["source_digest"])
                return {"status": "admitted",
                        "investigation": investigation,
                        "corrections": index}
            investigation = {
                "basis_references": [],
                "question": dict(action.get("inputs") or {}).get(
                    "reason", "policy stop"),
                "next_action": {"kind": "stop",
                                "reason": dict(
                                    action.get("inputs") or {}).get(
                                    "reason", "policy stop")},
            }
            policy_step.persist_step_transition(
                self._dsn, self._cid, self._seq, views=views,
                results=results, transitions=transitions,
                investigation=investigation,
                source_digest=stepped["source_digest"])
            return {"status": "admitted",
                    "investigation": investigation,
                    "corrections": index}
        policy_step.persist_step_transition(
            self._dsn, self._cid, self._seq, views=views,
            results=results, transitions=transitions,
            investigation={"status": "refused",
                           "reason": "policy step budget exhausted"
                           " (%d steps)" % self._max_policy_steps},
            source_digest=source_digest,
            status="incorporated")
        return self._refuse("policy step budget exhausted (%d steps)"
                            % self._max_policy_steps,
                            self._max_policy_steps)


def step_policy_consumer(policy: dict, **kwargs) -> StepPolicyConsumer:
    return StepPolicyConsumer(policy=policy, **kwargs)
