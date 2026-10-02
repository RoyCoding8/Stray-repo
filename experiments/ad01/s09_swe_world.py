"""The SWE world: an executable program, public symptoms, bounded tools.

The policy sees a program, a public failing-test symptom, and a budget. It
chooses from the shared action vocabulary in ``policy_action``: ``observe``
to run a named public test, ``check`` to run every public test, ``construct``
to inspect or localize, and ``use`` to apply the candidate edit it supplies.
``stop`` ends the episode.

The policy is never given the injected mechanism, the reference program, the
patch, or the protected test's name, arguments or answer. Localization
returns coverage evidence and never source text. Repair applies the edit the
policy supplies and never invents one. Budgets are hard and refusals are
explicit.

The task record is assessor-side. ``public_view`` is the only projection
handed to a policy, and it is an allowlist.
"""

from __future__ import annotations

from . import policy_action
from . import s09_swe_tasks as tasks

INSTRUMENT_ID = "software-fault-repair-v1"
SPLITS = tasks.SPLITS

# A task exposes exactly PUBLIC_CASES public tests, so a test budget above
# that is unreachable; the bound is set to the number of tests the task has.
BUDGET_LIMITS = {"inspect": 4, "test": tasks.PUBLIC_CASES,
                 "localize": 2, "probe": 60, "edit": 1}

# A turn is one action. The turn count is a fourth truncation and the
# one that binds last, because a full probe budget is spent one dry-run
# at a time and the episode stops at whichever bound runs out first. It
# is derived from the probe budget and the fixed preamble rather than
# typed in, so raising the probe budget cannot leave the turn cap
# silently below it. `MAX_TURNS` is set at the bottom of this module.
OBSERVE_TURNS = tasks.PUBLIC_CASES + 1
MAX_TURNS = 80

# How many ranked suspects a search may open candidate lanes on. Like the
# probe budget this is a truncation, and like the probe budget it is
# derived from the panel rather than typed in: the fault line the ranker
# puts furthest down has to still be inside the cap, or the budget
# derivation is describing a search the cap never lets run. Both bounds
# are set at the bottom of this module, once `SweSession` exists.
SUSPECT_CAP = 4


def _panel():
    """One pass over the panel: observe, localize, rank, then walk.

    Yields `(record, view, texts, pool, ordered_suspects)`. Every
    derived bound below reads the same pass, so the cap and the budget
    cannot end up describing two different searches.
    """
    from . import s09_swe_policy as search

    for split in tasks.SPLITS:
        for record in tasks.enumerate_instances(split):
            session = SweSession(record)
            for case in record["public_tests"]:
                session.run_public_test(case["name"])
            session.localize(record["public_tests"][0]["name"])
            view = session.policy_view()
            yield (record, view,
                   [item["text"] for item in view["source"]],
                   search._pool(view), search.suspects(view))


def worst_case_suspect_rank() -> int:
    """How far down the ranked list the furthest fault line sits.

    The ranker scores the fault line the same as it scores every other
    line, and a fault line at rank nine is one it already scored and the
    cap then throws away. Capping past the worst rank the panel produces
    is what makes the budget derivation mean anything: with the cap
    below it, "the budget reaches the fault line" would be a claim about
    a search the cap stops first.
    """
    worst = 0
    for record, _view, _texts, _pool, ordered in _panel():
        fault_line = record["patch"][0]["line"]
        if fault_line in ordered:
            worst = max(worst, ordered.index(fault_line) + 1)
    return worst


def worst_case_probe_cost() -> int:
    """Dry-runs needed to reach the reference repair on the furthest
    instance.

    The `probe` budget is a property of the panel and the search, not a
    number anyone chose. This walks every instance of both splits the
    way the arm walks it - column-major across the suspect lanes, which
    is the order `s09_swe_policy.next_try` spends candidates in - and
    stops at the furthest point any *reference repair* is dry-run. The
    budget is set past that, so it is neither too small for the panel it
    measures nor inflated past it.

    It reaches for the reference line and not merely the reference
    *line's* presence, and the difference is the whole budget. A fault
    line ranked second with forty candidates on it is touched after
    two dry-runs, but its repair is the fortieth candidate in that lane
    and is not dry-run until three hundred. An earlier version of this
    derivation stopped at the line and reported 58 for an instance the
    arm only reached at 302, and the budget it produced was short by a
    third. A derivation has to describe the search it derives a bound
    for, or it is a number about a different program.

    It reads `record["patch"]`, which no policy may see. The asymmetry
    is deliberate and is the same one a benchmark makes when it sets a
    timeout from a reference run: the instrument sizes its own bound
    from the answer it injected, and no arm is handed anything by doing
    so. What the bound buys is that a repair rate is a statement about
    the search rather than about a number someone typed.
    """
    from . import s09_swe_policy as search

    worst = 0
    for record, _view, texts, pool, ordered in _panel():
        reference = record["patch"][0]["text"].rstrip("\n")
        numbers = [number for number in ordered[:SUSPECT_CAP]
                   if 1 <= number <= len(texts)]
        lanes = [search.rewrites(texts[number - 1], pool)
                 for number in numbers]
        spent = 0
        for column in range(search.MAX_REWRITES):
            if not any(column < len(lane) for lane in lanes):
                break
            for lane in lanes:
                if column >= len(lane):
                    continue
                spent += 1
                if lane[column] == reference:
                    worst = max(worst, spent)
                    break
            else:
                continue
            break
    return worst

ACTION_TARGETS = {
    policy_action.OBSERVE: "test.run",
    policy_action.CHECK: "test.run_all",
    policy_action.CONSTRUCT: ("code.inspect", "code.localize",
                              "code.try"),
    policy_action.USE: "code.repair",
    policy_action.STOP: "swe.task",
}

CONSTRUCT_TARGETS = ("code.inspect", "code.localize", "code.try")

POLICY_VIEW_FIELDS = ("action_schema", "entry", "instrument",
                      "last_effect", "max_budget", "public_tests",
                      "remaining", "source", "split", "structure", "symptom",
                      "task_id")

# The session methods that can see the protected answer or the patch.
# Nothing else in this module does, and none of these is reachable from the
# policy view, which is the boundary the contamination tests pin.
ASSESSOR_ENTRY_POINTS = frozenset({
    "SweSession.score", "SweSession.localize", "SweSession.run_public_test",
    "SweSession.run_all_public", "SweSession.reference_source",
})


class ActionRefused(Exception):
    pass


def action_schema() -> dict:
    return {
        "version": 1,
        "format": "s09-swe-action-v1",
        "actions": {
            policy_action.OBSERVE: {"target": "test.run",
                                    "inputs": {"test": "public test name"}},
            policy_action.CHECK: {"target": "test.run_all", "inputs": {}},
            policy_action.CONSTRUCT: {
                "target": "code.inspect | code.localize | code.try",
                "inputs": {"line": "source line number",
                           "text": "replacement line for code.try",
                           "test": "public test name for code.localize"}},
            policy_action.USE: {"target": "code.repair",
                                "inputs": {"edits": "policy-supplied edits"}},
            policy_action.STOP: {"target": "swe.task", "inputs": {}},
        },
        "budget": dict(BUDGET_LIMITS),
    }


def stop_action() -> dict:
    return {"kind": policy_action.STOP, "target": "swe.task",
            "inputs": {}, "evidence_refs": [], "requested_resources": {}}


def repair_action(edits) -> dict:
    return {"kind": policy_action.USE, "target": "code.repair",
            "inputs": {"edits": edits}, "evidence_refs": [],
            "requested_resources": {}}


def public_view(record: dict) -> dict:
    """The only projection a policy may hold of a task record."""
    return {
        "instrument": INSTRUMENT_ID,
        "task_id": record["task_id"],
        "split": record["split"],
        "structure": record["structure"],
        "entry": record["entry"],
        "source": [{"line": number, "text": text}
                   for number, text in enumerate(record["source_text"], 1)],
        "public_tests": [{"name": case["name"], "args": case["args"]}
                         for case in record["public_tests"]],
        "symptom": {"failing_tests": [], "observed": [],
                    "coverage": []},
        "last_effect": None,
        "remaining": dict(BUDGET_LIMITS),
        "max_budget": dict(BUDGET_LIMITS),
        "action_schema": action_schema(),
    }


class SweSession:
    """One episode against one task. Budgets are enforced on every call."""

    def __init__(self, record: dict) -> None:
        self._record = record
        self._program = tasks.PROGRAMS_BY_NAME[record["template"]]
        self._lines = list(record["source"])
        self._used = {name: 0 for name in BUDGET_LIMITS}
        self._results: dict = {}
        self._observed: list = []
        self._coverage: list = []
        self._patches: list = []
        self._repaired = False
        self._last: dict = {}

    def policy_view(self) -> dict:
        view = public_view(self._record) | {
            "last_effect": dict(self._last) if self._last else None,
            "symptom": {"failing_tests": self._failing(),
                        "observed": list(self._observed),
                        "coverage": list(self._coverage)},
            "remaining": self.budget(),
        }
        view["source"] = [{"line": number, "text": text.rstrip("\n")}
                          for number, text in enumerate(self._lines, 1)]
        return view

    def budget(self) -> dict:
        return {name: BUDGET_LIMITS[name] - used
                for name, used in self._used.items()}

    def reference_source(self) -> list:
        return list(self._record["reference_source"])

    def _failing(self) -> list:
        failing = []
        for item in self._observed:
            if item["actual"] != item["expected"] or item["kind"] == "error":
                failing.append({"test": item["test"], "kind": item["kind"]})
        return failing

    def _spend(self, name: str) -> None:
        if self._used[name] >= BUDGET_LIMITS[name]:
            raise ActionRefused("%s budget exhausted" % name)
        self._used[name] += 1

    def _public_case(self, name):
        for case in self._record["public_tests"]:
            if case["name"] == name:
                return case
        raise ActionRefused("%s is not a public test" % name)

    def _observe(self, name: str) -> dict:
        case = self._public_case(name)
        if name in self._results:
            raise ActionRefused("test %s has already been run" % name)
        self._spend("test")
        got = tasks.run_program(self._program, case["args"], self._lines)
        item = {"test": name,
                "expected": case["expected"],
                "actual": got.get("value"),
                "kind": got["kind"]}
        if got["kind"] == "error":
            item["error"] = got["name"]
        self._results[name] = item
        self._observed.append(item)
        return item

    def run_public_test(self, name: str) -> dict:
        return self._observe(name)

    def run_all_public(self) -> dict:
        for case in self._record["public_tests"]:
            if case["name"] not in self._results:
                if self._used["test"] >= BUDGET_LIMITS["test"]:
                    break
                self._observe(case["name"])
        passed = sum(1 for item in self._results.values()
                     if item["actual"] == item["expected"]
                     and item["kind"] == "value")
        return {"passed": passed, "total": len(self._record["public_tests"]),
                "observed": [item["test"] for item in self._observed]}

    def inspect(self, line: int) -> dict:
        """Public inspection: line numbers, indentation and neighbour text."""
        self._spend("inspect")
        if type(line) is not int or line < 1 or line > len(self._lines):
            raise ActionRefused("line %s does not exist" % (line,))
        text = self._lines[line - 1]
        return {"line": line, "indent": len(text) - len(text.lstrip()),
                "length": len(text.rstrip("\n"))}

    def localize(self, test: str) -> dict:
        """Coverage evidence for one public test. Never source text."""
        self._spend("localize")
        case = self._public_case(test)
        executed = tasks.trace_lines(self._program, case["args"], self._lines)
        self._coverage = [item for item in self._coverage
                          if item["test"] != test]
        self._coverage.append({"test": test, "executed_lines": executed,
                               "span": [min(executed), max(executed)]
                               if executed else []})
        return self._coverage[-1]

    def try_edit(self, line: int, text: str) -> dict:
        """Dry-run a candidate edit against the public tests.

        Returns the public pass count the candidate would produce. It does
        not say whether the candidate is right, does not name the fault and
        never returns source text: the caller already wrote `text`.
        """
        self._spend("probe")
        if type(line) is not int or line < 1 or line > len(self._lines):
            raise ActionRefused("line %s does not exist" % (line,))
        if not isinstance(text, str) or not text.strip():
            raise ActionRefused("try needs replacement text")
        _ = text
        trial = tasks.apply_edits(
            self._lines,
            [{"line": line, "op": "replace", "text": text.rstrip("\n")}])
        passed = 0
        for case in self._record["public_tests"]:
            got = tasks.run_program(self._program, case["args"], trial)
            if got["kind"] == "value" and got["value"] == case["expected"]:
                passed += 1
        return {"line": line, "public_passed": passed,
                "public_total": len(self._record["public_tests"])}

    def repair(self, edits) -> dict:
        """Apply the edits the policy supplied. Inventing one is impossible.

        The post-edit pass count is taken from the program itself rather
        than from `run_all_public`. The policy has usually spent the
        `test` budget on its way here, so re-running the public tests
        observes nothing and reports zero for a program that passes all
        of them. A repair's own report and the episode's final score
        then disagree, and neither number is the one a reader wants.
        """
        if not isinstance(edits, list) or not edits:
            raise ActionRefused("repair needs edits from the policy")
        self._spend("edit")
        try:
            lines = tasks.apply_edits(self._lines, edits)
        except tasks.SoftwareTaskInvalid as exc:
            raise ActionRefused(str(exc)) from exc
        before = sum(1 for item in self._results.values()
                     if item["actual"] == item["expected"]
                     and item["kind"] == "value")
        self._lines = lines
        self._patches.append(list(edits))
        self._results.clear()
        self._observed.clear()
        passed = sum(
            1 for case in self._record["public_tests"]
            if self._public_result(case) == "pass")
        total = len(self._record["public_tests"])
        self._repaired = (passed == total)
        return {"edited": [edit.get("line") for edit in edits],
                "passed": passed, "total": total,
                "previously_passing": before}

    def _public_result(self, case: dict) -> str:
        got = tasks.run_program(self._program, case["args"], self._lines)
        return "pass" if got["kind"] == "value" and got["value"] == \
            case["expected"] else "fail"

    def score(self) -> dict:
        report = tasks.score(self._record, self._lines)
        report["patches"] = len(self._patches)
        report["budget"] = self.budget()
        return report

    def is_repaired(self) -> bool:
        return self._repaired


def public_state(session: SweSession) -> dict:
    return session.policy_view()


def _remember(session: SweSession, effect: dict) -> dict:
    session._last = effect
    return effect


def _validate_edit_inputs(inputs: dict) -> list:
    edits = inputs.get("edits")
    if not isinstance(edits, list) or not edits:
        raise ActionRefused("repair needs edits from the policy")
    for edit in edits:
        if not isinstance(edit, dict) or "line" not in edit:
            raise ActionRefused("each edit needs a line number")
    return edits


def apply_action(session: SweSession, action: dict) -> dict:
    try:
        shared = policy_action.parse_action(action)
    except policy_action.ActionRefused as exc:
        raise ActionRefused(str(exc)) from exc
    kind = shared.kind
    if kind == policy_action.OBSERVE and shared.target != "test.run":
        raise ActionRefused("observe target must be test.run")
    if kind == policy_action.CHECK and shared.target != "test.run_all":
        raise ActionRefused("check target must be test.run_all")
    if kind == policy_action.STOP and shared.target != "swe.task":
        raise ActionRefused("stop target must be swe.task")
    if kind == policy_action.OBSERVE:
        name = shared.inputs.get("test")
        if not isinstance(name, str) or not name:
            raise ActionRefused("observe needs a public test name")
        already = name in session.policy_view()["symptom"]["observed"] \
            and any(item["test"] == name
                    for item in session.policy_view()["symptom"]["observed"])
        if already:
            return _remember(session, {"kind": kind, "observed":
                                       session._results[name],
                                       "cached": True})
        return _remember(session, {"kind": kind,
                                   "observed": session.run_public_test(name)})
    if kind == policy_action.CHECK:
        return _remember(session, {"kind": kind,
                                   "public": session.run_all_public()})
    if kind == policy_action.CONSTRUCT:
        if shared.target == "code.localize":
            name = shared.inputs.get("test")
            if not isinstance(name, str) or not name:
                raise ActionRefused("localize needs a public test name")
            return _remember(session, {"kind": kind,
                                       "localized": session.localize(name)})
        if shared.target == "code.try":
            line = shared.inputs.get("line")
            if type(line) is not int:
                raise ActionRefused("try needs an integer line")
            return _remember(session, {"kind": kind, "tried": session.try_edit(
                line, shared.inputs.get("text"))})
        line = shared.inputs.get("line")
        if type(line) is not int:
            raise ActionRefused("construct needs an integer line")
        return _remember(session, {"kind": kind,
                                   "inspected": session.inspect(line)})
    if kind == policy_action.USE:
        if shared.target != "code.repair":
            raise ActionRefused("use target must be code.repair")
        edits = _validate_edit_inputs(shared.inputs)
        return _remember(session, {"kind": kind,
                                   "repaired": session.repair(edits)})
    if kind == policy_action.STOP:
        return _remember(session, {"kind": policy_action.STOP,
                                   "remaining": session.budget()})
    raise ActionRefused("%s has no operation in this world" % kind)


def as_shared_action(world_action: dict) -> dict:
    kind = world_action.get("kind")
    if kind not in policy_action.ACTION_KINDS:
        raise ActionRefused("unknown world action %r" % (kind,))
    return {
        "kind": kind,
        "target": world_action.get("target", "swe.task"),
        "inputs": dict(world_action.get("inputs", {})),
        "evidence_refs": list(world_action.get("evidence_refs", [])),
        "requested_resources": dict(world_action.get("requested_resources", {})),
    }


def is_terminal(session: SweSession) -> bool:
    return session.is_repaired()


def admits(session: SweSession, view: dict, action: dict) -> bool:
    """Whether an action would be admitted right now, without spending."""
    kind = action.get("kind")
    if kind == policy_action.STOP:
        return True
    target = action.get("target")
    allowed = ACTION_TARGETS.get(kind)
    if isinstance(allowed, (list, tuple)):
        allowed = set(allowed)
    if allowed is None or target not in allowed:
        return False
    remaining = view.get("remaining", {})
    need = {policy_action.OBSERVE: "test", policy_action.CHECK: "test",
            policy_action.USE: "edit"}.get(kind)
    if kind == policy_action.OBSERVE:
        name = action.get("inputs", {}).get("test")
        if name in {item["test"]
                    for item in view.get("symptom", {}).get("observed", [])}:
            return True
        return remaining.get("test", 0) > 0
    if need is not None:
        return remaining.get(need, 0) > 0
    if kind != policy_action.CONSTRUCT:
        return False
    if target == "code.localize":
        if remaining.get("localize", 0) <= 0:
            return False
        name = action.get("inputs", {}).get("test")
        return name in {item["test"]
                        for item in view.get("symptom", {}).get("failing_tests",
                                                                [])}
    if target == "code.try":
        return remaining.get("probe", 0) > 0
    return remaining.get("inspect", 0) > 0


def run_episode(choose_action, *, split: str, seed: int) -> dict:
    record = tasks.instances_for_seed(split, int(seed))
    session = SweSession(record)
    trace: list = []
    stopped = False
    while not stopped and not is_terminal(session) and len(trace) < MAX_TURNS:
        view = session.policy_view()
        action = choose_action(view)
        before = {"remaining": session.budget(),
                  "observed": [item["test"] for item in session._observed]}
        try:
            effect = apply_action(session, action)
        except ActionRefused as exc:
            trace.append({"action": action, "refused": str(exc),
                          "state_before": before})
            break
        trace.append({"action": action, "effect": effect,
                      "state_before": before})
        stopped = effect["kind"] == policy_action.STOP
    return {
        "task_id": record["task_id"],
        "split": split,
        "seed": int(seed),
        "template": record["template"],
        "structure": record["structure"],
        "trace": trace,
        "turns": len(trace),
        "repaired": session.is_repaired(),
        "final": session.score(),
        # The harness reads a spend record off the result and refuses a
        # world that publishes none, so the tests it ran are named here.
        # `repair` clears the observation, so this is the set as it stood
        # at the end of the episode, which is the same thing the
        # instrument spends.
        "queried": sorted({item["test"] for item in session._observed}),
    }


# The two truncations are set here, once `SweSession` exists, so both
# are derived from a real walk of the panel rather than a restatement
# of it. The cap is set first: the budget is a cost within the lanes the
# cap allows, so deriving the budget under a smaller cap would describe
# a search the cap never runs.
SUSPECT_CAP = worst_case_suspect_rank()
BUDGET_LIMITS["probe"] = worst_case_probe_cost() + 1

# Every dry-run is a turn, so a probe budget above `MAX_TURNS` is a
# budget the episode cannot spend. The turn cap is the preamble plus the
# whole probe budget plus the closing repair, and the closing repair is
# what makes a reached candidate actionable: without a turn to spend on
# it, a search that found the answer at the last probe scores zero.
MAX_TURNS = OBSERVE_TURNS + BUDGET_LIMITS["probe"] + BUDGET_LIMITS["edit"]
