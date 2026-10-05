"""Third world: a software world with a real executable program.

The incumbents are a boolean reduction and an ordering oracle. This one
exposes a small Python program, a public failing-test symptom, and four
budgeted tools. The policy chooses actions from observations. It is never
told the injected fault, the hidden patch, or the protected answer.

A program is a list of ``(role, text)`` lines. Four roles are faultable:
``bound``, ``window``, ``guard`` and ``update``. Each role carries a table
of named variants, one reference and two faulty. Eight fault mechanisms
map onto those variants, two per role. Injecting a fault and deriving its
patch are that one table read in two directions, so the patch is exactly
the reference and never a hand-typed near miss.

Split hygiene. Nine programs in three structures; development keeps the
first of each structure, assessment keeps the other six, so no program
template is shared. Eight fault mechanisms; development uses three,
assessment uses the other five, so no fault family is shared either. The
assessment split therefore spans all four roles and all three structures.

Only digits reach these programs, and every digit maps to a nonzero
contribution, so a widened, reversed or shortened window always changes the
result. Every faulty variant is checked to be observable, not assumed to be.

``score`` credits a candidate as ``repaired`` only when it is the reference's
own meaning, decided on the program's shape and not on the drawn cases. The
drawn cases say what the candidate was asked to do; they cannot say whether the
candidate is right, because a program can agree with the reference on every
case ever drawn from a set and still be wrong everywhere else. A sweep of the
input domain cannot decide it either, at any width, for the same reason. So
the verdict is a rewriting check against the reference, which holds for every
input or for none, and a candidate that agrees only where it was shown is
refused rather than credited. The check reads the two programs as trees, so a
rename is not equivalence here; see the comment above the rewriting rules.
"""

from __future__ import annotations

import ast
import random
import sys
from contextlib import contextmanager

TEMPLATE_VERSION = "s09-swe-template/2"

STRUCTURES = ("counting", "state_machine", "accumulator")
ROLES = ("bound", "guard", "update", "window")

MECHANISMS = (
    "double_count",
    "dropped_guard",
    "index_drift",
    "inverted_guard",
    "missing_advance",
    "off_by_one",
    "stale_accumulator",
    "swapped_window",
)

MECHANISM_PLAN = {
    "double_count": ("update", "double"),
    "dropped_guard": ("guard", "dead"),
    "index_drift": ("window", "wide"),
    "inverted_guard": ("guard", "inverted"),
    "missing_advance": ("bound", "strided"),
    "off_by_one": ("bound", "exclusive"),
    "stale_accumulator": ("update", "stale"),
    "swapped_window": ("window", "reversed"),
}

REFERENCE_VARIANT = "reference"

DEV_MECHANISMS = ("inverted_guard", "off_by_one", "stale_accumulator")
HELD_OUT_MECHANISMS = ("double_count", "dropped_guard", "index_drift",
                       "missing_advance", "swapped_window")

SPLITS = ("dev", "held_out")

PUBLIC_CASES = 2
PROTECTED_CASES = 1
PLANT = "123"
BODY_RANGE = (4, 6)
N_RANGE = (2, 4)

FAULT_LABEL_KEYS = frozenset({"mechanism", "patch", "reference_source",
                              "reference_text", "site", "role",
                              "protected_test", "variants", "role_plan"})

ASSESSOR_ENTRY_POINTS = frozenset({
    "enumerate_instances", "instance", "make_task", "support", "score",
    "protected_verdict", "run_program", "trace_lines", "rendered",
    "fault_label_keys", "TEMPLATES_BY_NAME", "PROGRAMS_BY_NAME", "PROGRAMS",
})


class SoftwareTaskInvalid(Exception):
    pass


class Program:

    __slots__ = ("name", "structure", "entry", "spec", "variants")

    def __init__(self, name, structure, entry, spec, variants):
        self.name = name
        self.structure = structure
        self.entry = entry
        self.spec = spec
        self.variants = variants

    def render(self, chosen: dict) -> list:
        return [(chosen[role] if role in chosen else text) + "\n"
                for role, text in self.spec]

    def site_line(self, role: str) -> int:
        for number, (name, _) in enumerate(self.spec, start=1):
            if name == role:
                return number
        raise SoftwareTaskInvalid("program %s lacks role %s"
                                  % (self.name, role))


def _program(name, structure, entry, spec, variants):
    seen: dict = {}
    for role, text in spec:
        if role in ROLES:
            seen[role] = seen.get(role, 0) + 1
    for role in ROLES:
        if seen.get(role) != 1:
            raise SoftwareTaskInvalid("program %s role %s occurs %s times"
                                      % (name, role, seen.get(role, 0)))
        table = variants.get(role, {})
        if REFERENCE_VARIANT not in table:
            raise SoftwareTaskInvalid("program %s role %s lacks reference"
                                      % (name, role))
        for mechanism, (planned, variant) in MECHANISM_PLAN.items():
            if planned == role and variant not in table:
                raise SoftwareTaskInvalid("program %s role %s lacks %s"
                                          % (name, role, variant))
    for role, text in spec:
        if role in ROLES and text:
            raise SoftwareTaskInvalid("program %s role %s is not a slot"
                                      % (name, role))
    return Program(name, structure, entry, spec, variants)


def _head(entry: str, doc: str) -> tuple:
    return ("def", "def %s(body, n):" % entry)


def _doc(doc: str) -> tuple:
    return ("doc", '    """%s"""' % doc)


def _wide_window(slot: str) -> str:
    """Extend a half-open slice `x:y` by one element on the right.

    Both bounds are read out of the slice's own AST and the upper one is
    incremented there, so the wide window cannot drift from the narrow one.
    """
    head, _, slice_text = slot.partition("[")
    low_text, _, high_text = slice_text.rstrip("]").rpartition(":")
    low = ast.parse(low_text.strip(), mode="eval")
    high = ast.parse(high_text.strip(), mode="eval")
    if not isinstance(high.body, ast.BinOp) or \
            not isinstance(high.body.op, ast.Add):
        raise SoftwareTaskInvalid("window-bound-not-additive")
    wider = ast.Expression(
        ast.BinOp(left=high.body.left, op=ast.Add(),
                  right=ast.BinOp(left=high.body.right, op=ast.Add(),
                                  right=ast.Constant(value=1))))
    ast.fix_missing_locations(wider)
    return "%s[%s:%s]" % (head, ast.unparse(low), ast.unparse(wider))


def _count_variants(window: str, update: str, wide: str,
                    reversed_window: str) -> dict:
    """Variants for a `for index in range` counting program.

    `contribution` is strictly increasing in `seen`, so any structural
    change that drops, adds or reorders a loop step changes the total.
    """
    return {
        "bound": {REFERENCE_VARIANT: "    for index in range(1, n + 1):",
                  "exclusive": "    for index in range(1, n):",
                  "strided": "    for index in range(1, n + 1, 2):"},
        "window": {REFERENCE_VARIANT: window, "wide": wide,
                   "reversed": reversed_window},
        "guard": {REFERENCE_VARIANT: "        marker = 0 if seen == 0 else 1",
                  "inverted": "        marker = 1 if seen == 0 else 0",
                  "dead": "        marker = 0"},
        "update": {REFERENCE_VARIANT: update,
                   "stale": "        total = total + previous",
                   "double": "        total = total + contribution * 2"},
    }


def _scan_variants(window: str) -> dict:
    return {
        "bound": {REFERENCE_VARIANT: "    while state < n:",
                  "exclusive": "    while state <= n:",
                  "strided": "    while state < n - 1:"},
        "window": {REFERENCE_VARIANT: window, "wide": _wide_window(window),
                   "reversed": "        window = body[::-1][len(body) - state - 2:len(body) - state]"},
        "guard": {REFERENCE_VARIANT: "        marker = 0 if state == 0 else 1",
                  "inverted": "        marker = 1 if state == 0 else 0",
                  "dead": "        marker = 0"},
        "update": {REFERENCE_VARIANT: "        carry = contribution",
                   "stale": "        carry = carry",
                   "double": "        carry = contribution * 2"},
    }


def _acc_variants(window: str) -> dict:
    return {
        "bound": {REFERENCE_VARIANT: "    for start in range(1, n + 1):",
                  "exclusive": "    for start in range(1, n):",
                  "strided": "    for start in range(1, n + 1, 2):"},
        "window": {REFERENCE_VARIANT: window, "wide": _wide_window(window),
                   "reversed": "        window = body[::-1][start:start + 2]"},
        "guard": {REFERENCE_VARIANT: "        marker = 0 if seen == 0 else 1",
                  "inverted": "        marker = 1 if seen == 0 else 0",
                  "dead": "        marker = 0"},
        "update": {REFERENCE_VARIANT: "        total = total + width + seen",
                   "stale": "        total = total + previous",
                   "double": "        total = total + width * 2 + seen"},
    }


_COUNT_A = _program(
    "count-lead-sum", "counting", "lead_sum",
    [_head("lead_sum", ""), _doc("Sum the n leading values of body.")] + [
        ("init", "    total = 0"),
        ("init", "    previous = 0"),
        ("init", "    seen = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        contribution = sum(int(mark) for mark in window) + seen"),
        ("update", ""),
        ("carry", "        previous = contribution"),
        ("carry", "        seen = seen + 1"),
        ("tail", "    return total + seen * 3 + marker * 11"),
    ],
    _count_variants("        window = body[index - 1:index + 2]",
                    "        total = total + contribution",
                    "        window = body[index - 1:index + 3]",
                    "        window = body[index + 2:index - 1]"))

_COUNT_B = _program(
    "count-tail-sum", "counting", "tail_sum",
    [_head("tail_sum", ""), _doc("Sum the leading prefix up to n values.")] + [
        ("init", "    total = 0"),
        ("init", "    previous = 0"),
        ("init", "    seen = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        contribution = sum(int(mark) for mark in window) + seen * 2"),
        ("update", ""),
        ("carry", "        previous = contribution"),
        ("carry", "        seen = seen + 1"),
        ("tail", "    return total + seen * 5 + marker * 11"),
    ],
    _count_variants("        window = body[0:index + 2]",
                    "        total = total + contribution",
                    "        window = body[0:index + 3]",
                    "        window = body[index + 2::-1]"))

_COUNT_C = _program(
    "count-even-sum", "counting", "even_sum",
    [_head("even_sum", ""), _doc("Sum every other leading value of body.")] + [
        ("init", "    total = 0"),
        ("init", "    previous = 0"),
        ("init", "    seen = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        contribution = sum(int(mark) for mark in window) + seen"),
        ("update", ""),
        ("carry", "        previous = contribution"),
        ("carry", "        seen = seen + 1"),
        ("tail", "    return total * 2 + seen + marker * 11"),
    ],
    _count_variants("        window = body[index - 1:index + 1]",
                    "        total = total + contribution",
                    "        window = body[index - 1:index + 2]",
                    "        window = body[index:index - 2]"))

_SCAN_A = _program(
    "scan-depth", "state_machine", "scan_depth",
    [_head("scan_depth", ""), _doc("Depth reached over the first n digits.")] + [
        ("init", "    moves = {\"1\": 2, \"2\": 1, \"3\": 1}"),
        ("init", "    state = 0"),
        ("init", "    seen = 0"),
        ("init", "    carry = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        contribution = sum(moves.get(mark, 0) for mark in window) + seen + 1"),
        ("update", ""),
        ("carry", "        state = state + 1"),
        ("tail", "    return carry + seen * 2 + marker * 11"),
    ],
    _scan_variants("        window = body[state:state + 2]"))

_SCAN_B = _program(
    "scan-net", "state_machine", "scan_net",
    [_head("scan_net", ""), _doc("Net movement over the first n digits.")] + [
        ("init", "    moves = {\"1\": 1, \"2\": 2, \"3\": 3}"),
        ("init", "    state = 0"),
        ("init", "    seen = 0"),
        ("init", "    carry = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        contribution = sum(moves.get(mark, 0) for mark in window) + seen + 2"),
        ("update", ""),
        ("carry", "        state = state + 1"),
        ("tail", "    return carry * 2 + seen * 3 + marker * 11"),
    ],
    _scan_variants("        window = body[state:state + 1]"))

_SCAN_C = _program(
    "scan-climb", "state_machine", "scan_climb",
    [_head("scan_climb", ""), _doc("Rising steps over the first n digits.")] + [
        ("init", "    moves = {\"1\": 3, \"2\": 2, \"3\": 1}"),
        ("init", "    state = 0"),
        ("init", "    seen = 0"),
        ("init", "    carry = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        contribution = sum(moves.get(mark, 0) for mark in window) + seen + 3"),
        ("update", ""),
        ("carry", "        state = state + 1"),
        ("tail", "    return carry + seen * 4 + marker * 11"),
    ],
    _scan_variants("        window = body[state:state + 3]"))

_ACC_A = _program(
    "token-width", "accumulator", "token_width",
    [_head("token_width", ""), _doc("Combined width over the first n digits.")] + [
        ("init", "    total = 0"),
        ("init", "    previous = 0"),
        ("init", "    seen = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        width = 0"),
        ("loop", "        for mark in window:"),
        ("loop", "            width = width + int(mark)"),
        ("compute", "        width = width + seen"),
        ("update", ""),
        ("carry", "        previous = width"),
        ("carry", "        seen = seen + 1"),
        ("tail", "    return total + seen * 6 + marker * 11"),
    ],
    _acc_variants("        window = body[start - 1:start + 2]"))

_ACC_B = _program(
    "token-ends", "accumulator", "token_end_count",
    [_head("token_end_count", ""), _doc("Digit ends over the first n digits.")] + [
        ("init", "    total = 0"),
        ("init", "    previous = 0"),
        ("init", "    seen = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        width = 0"),
        ("loop", "        for mark in window:"),
        ("loop", "            width = width + (1 if mark == \"3\" else 0)"),
        ("compute", "        width = width + seen"),
        ("update", ""),
        ("carry", "        previous = width"),
        ("carry", "        seen = seen + 1"),
        ("tail", "    return total * 3 + seen * 7 + marker * 11"),
    ],
    _acc_variants("        window = body[start:start + 2]"))

_ACC_C = _program(
    "token-gaps", "accumulator", "token_gaps",
    [_head("token_gaps", ""), _doc("Leading gaps over the first n digits.")] + [
        ("init", "    total = 0"),
        ("init", "    previous = 0"),
        ("init", "    seen = 0"),
        ("bound", ""),
        ("window", ""),
        ("guard", ""),
        ("compute", "        width = 0"),
        ("loop", "        for mark in window:"),
        ("loop", "            width = width + (1 if mark == \"1\" else 0)"),
        ("compute", "        width = width + seen"),
        ("update", ""),
        ("carry", "        previous = width"),
        ("carry", "        seen = seen + 1"),
        ("tail", "    return total + seen * 8 + marker * 11"),
    ],
    _acc_variants("        window = body[start - 1:start + 1]"))


PROGRAMS = (_COUNT_A, _COUNT_B, _COUNT_C, _SCAN_A, _SCAN_B, _SCAN_C,
            _ACC_A, _ACC_B, _ACC_C)

DEV_PROGRAMS = (_COUNT_A, _SCAN_A, _ACC_A)
HELDOUT_PROGRAMS = (_COUNT_B, _COUNT_C, _SCAN_B, _SCAN_C, _ACC_B, _ACC_C)

DEV_TEMPLATES = tuple(program.name for program in DEV_PROGRAMS)
HELD_OUT_TEMPLATES = tuple(program.name for program in HELDOUT_PROGRAMS)

PROGRAMS_BY_NAME = {program.name: program for program in PROGRAMS}
_SPLIT_OF_TEMPLATE = {name: ("dev" if name in DEV_TEMPLATES else "held_out")
                      for name in PROGRAMS_BY_NAME}
_MECHANISMS_OF_SPLIT = {"dev": DEV_MECHANISMS, "held_out": HELD_OUT_MECHANISMS}


def chosen_variants(program: Program, mechanism: str) -> dict:
    """The variant table for a program under one mechanism."""
    chosen: dict = {}
    for role in ROLES:
        variant = REFERENCE_VARIANT
        for name, (planned, faulty) in MECHANISM_PLAN.items():
            if name == mechanism and planned == role:
                variant = faulty
        chosen[role] = program.variants[role][variant]
    return chosen


def reference_variants(program: Program) -> dict:
    return {role: program.variants[role][REFERENCE_VARIANT] for role in ROLES}


def render_source(lines: list) -> str:
    return "".join(line if line.endswith("\n") else line + "\n"
                   for line in lines)


def make_task(split: str, template: str, mechanism: str) -> dict:
    """Build one instance: exactly one role's variant is switched."""
    if split not in SPLITS:
        raise SoftwareTaskInvalid("unknown-split")
    if mechanism not in MECHANISMS:
        raise SoftwareTaskInvalid("unknown-mechanism")
    if mechanism not in _MECHANISMS_OF_SPLIT[split]:
        raise SoftwareTaskInvalid("mechanism-not-in-split")
    if _SPLIT_OF_TEMPLATE.get(template) != split:
        raise SoftwareTaskInvalid("template-split-mismatch")
    program = PROGRAMS_BY_NAME.get(template)
    if program is None:
        raise SoftwareTaskInvalid("unknown-template")

    role, _ = MECHANISM_PLAN[mechanism]
    source = program.render(chosen_variants(program, mechanism))
    reference = program.render(reference_variants(program))
    if source == reference:
        raise SoftwareTaskInvalid("fault-not-injected")
    line = program.site_line(role)
    patch = [{"line": line, "op": "replace",
              "text": program.variants[role][REFERENCE_VARIANT] + "\n"}]
    if render_source(apply_edits(source, patch)) != render_source(reference):
        raise SoftwareTaskInvalid("patch-does-not-restore")

    public, protected = _cases(program, template, mechanism, split,
                               source)
    return {
        "task_id": "swe-%s-%s-%s" % (split, program.name,
                                     _opaque(mechanism, template, split)),
        "split": split,
        "template": program.name,
        "structure": program.structure,
        "mechanism": mechanism,
        "entry": program.entry,
        "source": source,
        "source_text": [line.rstrip("\n") for line in source],
        "reference_source": reference,
        "reference_text": [line.rstrip("\n") for line in reference],
        "patch": patch,
        "public_tests": public,
        "protected_test": protected,
    }


def _opaque(mechanism: str, template: str, split: str) -> str:
    """A task-id suffix that does not name the mechanism.

    The id reaches the policy view, so a suffix like `double_count` would
    hand over the fault label the policy is meant to infer.
    """
    import hashlib

    digest = hashlib.sha256("|".join((TEMPLATE_VERSION, split, template,
                                      mechanism)).encode()).hexdigest()
    return digest[:6]


def apply_edits(source: list, edits: list) -> list:
    lines = list(source)
    for edit in edits:
        if not isinstance(edit, dict) or "line" not in edit:
            raise SoftwareTaskInvalid("edit-missing-line")
        number = edit["line"]
        if type(number) is not int or number < 1 or number > len(lines):
            raise SoftwareTaskInvalid("line %s does not exist" % (number,))
        operation = edit.get("op", "replace")
        if operation == "replace":
            text = edit.get("text")
            if not isinstance(text, str):
                raise SoftwareTaskInvalid("replace needs text")
            lines[number - 1] = text if text.endswith("\n") else text + "\n"
        elif operation == "delete":
            del lines[number - 1]
        else:
            raise SoftwareTaskInvalid("unknown-edit-op")
    return lines


def _cases(program: Program, template: str, mechanism: str,
           split: str, faulty: list) -> tuple:
    rng = random.Random("|".join((TEMPLATE_VERSION, program.name, mechanism,
                                  template, split)))
    reference = program.render(reference_variants(program))
    picked: list = []
    used: set = set()
    for _ in range(200):
        if len(picked) == PUBLIC_CASES + PROTECTED_CASES:
            break
        body = "".join(rng.choice(PLANT)
                       for _ in range(rng.randint(*BODY_RANGE)))
        n = rng.randint(*N_RANGE)
        if (body, n) in used:
            continue
        if run_program(program, [body, n], faulty)["kind"] != "value":
            continue
        if run_program(program, [body, n], faulty)["value"] == \
                run_program(program, [body, n], reference)["value"]:
            continue
        used.add((body, n))
        picked.append({"name": "case-%02d" % (len(picked) + 1),
                       "args": [body, n]})
    if len(picked) < PUBLIC_CASES + PROTECTED_CASES:
        raise SoftwareTaskInvalid("fault-not-observable")
    public = [{"name": case["name"], "args": case["args"],
               "expected": _expect(program, case["args"], reference)}
              for case in picked[:PUBLIC_CASES]]
    last = picked[PUBLIC_CASES]
    protected = {"name": "protected-case", "args": last["args"],
                 "expected": _expect(program, last["args"], reference)}
    return public, protected


def _expect(program: Program, args: list, lines: list):
    outcome = run_program(program, args, lines)
    if outcome["kind"] != "value":
        raise SoftwareTaskInvalid("reference-program-errors")
    return outcome["value"]


def run_program(program: Program, args: list, lines: list) -> dict:
    """Execute a candidate program. Returns a value or a public error kind.

    `exec` of the module body can raise something other than
    `SyntaxError`. A single-line candidate moved out of the function
    body - `width = 0` at module scope, say - compiles and then raises
    `NameError` on an undefined `body`, and that escaped this call,
    escaped `try_edit`, and killed the episode. A candidate is
    untrusted input, so every way the module body can fail is an error
    kind here rather than an exception. The bounds below are the ones a
    bad edit can plausibly trigger; anything wilder is still an error
    rather than a crash, because a candidate must not be able to take
    the harness down.
    """
    namespace: dict = {}
    try:
        exec(compile(render_source(lines), "<swe>", "exec"), namespace)
    except SyntaxError as exc:
        return {"kind": "error", "name": "SyntaxError", "text": str(exc)}
    except Exception as exc:
        return {"kind": "error", "name": type(exc).__name__,
                "text": str(exc)[:200]}
    entry = namespace.get(program.entry)
    if not callable(entry):
        return {"kind": "error", "name": "NameError", "text": "missing entry"}
    return _bounded(entry, args)


# A candidate edit can break a loop's exit condition, so every run gets a
# step bound. An unbounded candidate would hang the harness on one bad edit,
# which a bounded tool has to refuse rather than inherit.
MAX_STEPS = 100000


@contextmanager
def _tracing(tracer):
    """Install `tracer`, then put back the tracer that was already there.

    `sys.settrace` returns the tracer it displaced, so restoring from its
    return value looks correct until something was already tracing, when it
    silently installs a different tracer than the one that was there. A
    coverage run or a debugger is exactly that case. The pre-existing tracer
    is read with `sys.gettrace()` before the install instead, which is the
    caller's own and the only value that restores the caller's state.

    Both places in this file that trace go through here, so the restore is
    written once.
    """
    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        yield
    finally:
        sys.settrace(previous)


def _step_bound(budget: list):
    """A trace hook that raises once `budget` runs out. Portable; see `_bounded`."""
    def tracer(_frame, _event, _arg):
        budget[0] -= 1
        if budget[0] <= 0:
            raise _TooLong
        return tracer

    return tracer


def _bounded(entry, args) -> dict:
    """Run the entry point under a step bound, so a bad edit cannot hang.

    `signal.setitimer` is POSIX-only. Behind that `hasattr` it is simply absent
    on win32, which left a candidate that never returned hanging the harness
    on the host that runs this most often. A bound counted in steps is
    portable, so it is the mechanism that decides the verdict on every host.
    The alarm stays as the wall-clock limit on top of it, because a bound
    counted in steps cannot stop a single line that never yields to the
    interpreter.
    """
    import signal

    def on_alarm(_signum, _frame):
        raise _TooLong

    previous = None
    if hasattr(signal, "setitimer"):
        previous = signal.signal(signal.SIGALRM, on_alarm)
        signal.setitimer(signal.ITIMER_REAL, 2.0)
    budget = [MAX_STEPS]
    with _tracing(_step_bound(budget)):
        try:
            return {"kind": "value", "value": entry(*args)}
        except _TooLong:
            return {"kind": "error", "name": "NonTerminating",
                    "text": "no exit"}
        except Exception as exc:
            return {"kind": "error", "name": type(exc).__name__,
                    "text": str(exc)}
        finally:
            if previous is not None:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)


class _TooLong(Exception):
    pass


def trace_lines(program: Program, args: list, lines: list) -> list:
    """Line numbers a candidate program actually executed for these args.

    A candidate that fails at module scope executes nothing, so the
    same broad catch as `run_program` applies: an untrusted edit has to
    come back as no coverage rather than as an exception.
    """
    namespace: dict = {}
    try:
        exec(compile(render_source(lines), "<swe>", "exec"), namespace)
    except Exception:
        return []
    entry = namespace.get(program.entry)
    if not callable(entry):
        return []
    hit: list = []
    code = entry.__code__

    def tracer(frame, event, arg):
        if event == "call" and frame.f_code is code:
            return tracer
        if event == "line" and frame.f_code is code:
            hit.append(frame.f_lineno)
        return tracer

    with _tracing(tracer):
        try:
            entry(*args)
        except Exception:
            pass
    return sorted(set(hit))


def score(record: dict, lines: list) -> dict:
    """Assessor verdict for a candidate program. Never reaches the policy."""
    program = PROGRAMS_BY_NAME[record["template"]]
    public = []
    for case in record["public_tests"]:
        got = run_program(program, case["args"], lines)
        public.append({"test": case["name"],
                       "pass": got["kind"] == "value"
                               and got["value"] == case["expected"],
                       "kind": got["kind"]})
    passed = sum(1 for item in public if item["pass"])
    protected = protected_verdict(program, record, lines)
    # The drawn cases decide what the candidate was asked to do. They cannot
    # decide whether the candidate is right, because a program can agree with
    # the reference on every case drawn and still be wrong everywhere the
    # cases do not reach. The certificate is what makes `repaired` mean a
    # correct repair, which is the claim the intervention experiments rest on.
    # It runs only for a candidate that already cleared the drawn cases,
    # which is rare enough that it does not price the verdict.
    answered = passed == len(public) and protected["outcome"] == "pass"
    equivalent = (equivalence_verdict(record, lines)
                  if answered else {"outcome": "fail"})
    if equivalent["outcome"] == "pass":
        outcome = "repaired"
    elif any(item["kind"] == "error" for item in public):
        outcome = "crashed"
    else:
        outcome = "unrepaired"
    return {"public": public, "public_passed": passed,
            "public_total": len(public), "protected": protected,
            "equivalent": equivalent, "outcome": outcome}


def protected_verdict(program: Program, record: dict, lines: list) -> dict:
    case = record["protected_test"]
    got = run_program(program, case["args"], lines)
    passed = got["kind"] == "value" and got["value"] == case["expected"]
    return {"outcome": "pass" if passed else "fail"}


# Equivalence is decided structurally, on the program's own meaning rather
# than on a sample of its input domain.
#
# A sweep cannot carry this verdict at any width. A candidate that computes
# the reference only inside the box the sweep covers and returns a constant
# outside it agrees on every input ever swept, so widening the box moves the
# boundary a candidate has to gate to rather than closing it, and the drawn
# cases have that same property at any draw size. Measured on the 30 held-out
# instances: a reference gated to the sweep box of the day
# (`len(body) <= 5 and 1 <= n <= 5`) scored `repaired` on 9, and widening the
# box to `len(body) <= 6 and 1 <= n <= 6` put all 30 back, because 6 is where
# the drawn cases reach. Every constant in this file is readable by a
# candidate, so no constant is a certificate.
#
# The reference is the specification, and these programs are small enough to
# decide equality of meaning from their shape: a bounded loop, a fixed table
# of digit weights, integer arithmetic. A candidate is credited when its text
# reduces, by identities that hold for every input rather than on the inputs
# that were tried, to the same term the reference reduces to.
#
# Every rule below is a rewriting identity of Python, unconditional over all
# inputs. That is the whole discipline of this list. A rule that holds only
# because of a fact about one program - a name that happens to be zero exactly
# when another is - is not an identity, it is an agreement on the inputs
# somebody thought to try, so none of them is here and a candidate relying on
# one is refused rather than credited. Every rule also strictly shrinks the
# term it fires on, or moves it to a form no rule fires on again, so the
# reduction terminates rather than toggling.
#
# Measured over the 16,803 single-line rewrites a policy can emit from the
# faulty source, bb40300 credited 7 dev and 68 held-out candidates. This
# credits the same 7 dev and 42 held-out. Every candidate it refuses is one
# that agrees with the reference on all 288 probe inputs and is refused only
# because its equivalence is not an identity this list can state: a guard
# written over a name that happens to be zero when the reference's is, a
# window slice written in another order, and a fault that one line cancels -
# `total` doubled on one line and halved in the tail - which is equivalent
# only jointly and so no per-term rule can reach it.
#
# That is a refusal to call a correct repair correct, and it is deliberate.
# The alternative, sampling, is the failure this replaced: it credits a
# program that is wrong outside the region it was asked about, which is the
# direction that corrupts a repair rate.
#
# The bias of the whole check is in that direction, and it is a bias rather
# than a guarantee. An earlier version of this list claimed it was a lower
# bound on the repairs credited and never an upper bound on the wrong ones.
# That claim was false and was measured false: `_canonical_test` admitted nine
# comparison operators while its own justification held for one, so it
# credited candidates that compute something other than the reference. Over
# 1,673 single-line mutations built from the forward images of these four
# rules, 78 of the 425 credited were wrong on an input outside the drawn
# domain, in four distinct forms. Narrowing the allowlist to `!=` alone does
# not repair that by itself, because the same rule also stripped a `not` and
# swapped the branches and rewrote the operator in one step, which is three
# negations where the conditional had one. Each rule is now the identity it is
# documented as, and the same census credits 230 with none wrong.
#
# The residual bias is the deliberate one above. This refuses correct repairs
# whose equivalence it cannot state, so a repair rate read off it is a lower
# bound on the repairs a policy found; the census is what checks that the
# bound holds in the other direction too, rather than being assumed. It is a
# measurement with a script behind it, not a property of the list.
#
# What this does not decide is alpha-equivalence. The normal form is a tree
# compared with `ast.dump`, so names compare by name: a candidate that
# renames `seen` to `count` everywhere, and so computes exactly what the
# reference computes, is refused rather than credited. That is the same
# deliberate direction as everything else above - a refusal, never a wrong
# credit - and it is stated here rather than only in the history of this file
# because a reader deciding whether to trust a certificate needs the whole
# set of refusals in front of them, not the ones that happened to be found.
def _drop_unit_factor(node):
    """`x * 1` and `1 * x` are `x`, for any `x` Python can multiply."""
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mult):
        return None
    if isinstance(node.left, ast.Constant) and node.left.value == 1:
        return node.right
    if isinstance(node.right, ast.Constant) and node.right.value == 1:
        return node.left
    return None


def _drop_unit_step(node):
    """`range(a, b, 1)` yields what `range(a, b)` yields."""
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Name) or node.func.id != "range":
        return None
    if len(node.args) != 3 or node.keywords:
        return None
    if not isinstance(node.args[2], ast.Constant) or node.args[2].value != 1:
        return None
    node.args = node.args[:2]
    return node


def _fill_missing_slice_bound(node):
    """`x[:b]` is `x[0:b]`. An omitted lower bound already is zero."""
    if not isinstance(node, ast.Subscript):
        return None
    if not isinstance(node.slice, ast.Slice) or node.slice.lower is not None:
        return None
    node.slice.lower = ast.Constant(value=0)
    return node


def _canonical_test(node):
    """Normalise a conditional's predicate to one `==` comparison.

    The normal form is `a if x == y else b`. A conditional reaches it by
    accounting for its negation exactly once, in one of two places, and a
    predicate whose negation lives in neither is left alone rather than forced
    into a form it was never written in.

    In the operator. `a if x != y else b` is `b if x == y else a`: the swap is
    the negation, so the operator is rewritten with it and the branches with
    it. `!=` is the only operator this admits, because it is the only one
    whose negation is `==`.

    In a leading `not`. `a if not (x != y) else b` is `a if x == y else b`: the
    `not` is the negation, so it is peeled and the operator is rewritten with
    it, and the branches are left alone.

    The two are not composed, and composing them is what this rule used to do
    and why it was wrong. On a `not`-stripped predicate it stripped the `not`,
    swapped the branches and rewrote the operator, which is three negations
    where the conditional had one, and it rewrote the operator on all nine
    Python comparison operators while justifying `!=` alone. Stripping the
    `not` and swapping the branches is what makes the operator rewrite sound;
    doing that on a predicate that carried no `not` applies a negation the
    conditional never had.

    The other eight operators are left alone, and that is not a matter of
    taste. `not (x < y)` is `x >= y`, not `x == y`; `not (x is y)` is
    `x is not y`, which is not `x == y` either, because `is` and `==` part
    company on distinct objects of equal value and on a number and its float.
    An allowlist of the operators whose negation is `==` has one member in it.
    """
    if not isinstance(node, ast.IfExp):
        return None
    test = node.test
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = test.operand
        if not isinstance(inner, ast.Compare) or len(inner.ops) != 1 or \
                len(inner.comparators) != 1:
            return None
        if not isinstance(inner.ops[0], ast.NotEq):
            return None
        node.test = ast.Compare(left=inner.left, ops=[ast.Eq()],
                                comparators=inner.comparators)
        return node
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or \
            len(test.comparators) != 1:
        return None
    if not isinstance(test.ops[0], ast.NotEq):
        return None
    node.test = ast.Compare(left=test.left, ops=[ast.Eq()],
                            comparators=test.comparators)
    node.body, node.orelse = node.orelse, node.body
    return node


_NORMALISERS = (_drop_unit_factor, _drop_unit_step,
                _fill_missing_slice_bound, _canonical_test)


def _rewrite(node):
    """Children first, then this node's own rule, over the whole tree."""
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            setattr(node, field, [_rewrite(item) if isinstance(item, ast.AST)
                                  else item for item in value])
        elif isinstance(value, ast.AST):
            setattr(node, field, _rewrite(value))
    for normalise in _NORMALISERS:
        replaced = normalise(node)
        if replaced is not None:
            return replaced
    return node


def _normal_form(lines: list):
    """One program's meaning, reduced to the normal form both sides share.

    None when the program does not parse, which compares unequal to any
    normal form and so fails the check rather than passing it vacuously.
    """
    try:
        tree = ast.parse(render_source(lines))
    except (SyntaxError, ValueError):
        return None
    rewritten = _rewrite(tree)
    if rewritten is None:
        return None
    return ast.dump(ast.fix_missing_locations(rewritten))


def equivalence_verdict(record: dict, lines: list) -> dict:
    """Does this candidate compute what the reference computes, for all inputs?

    Decided on structure, so the answer does not turn on which inputs anyone
    thought to try, and a candidate cannot pass by agreeing on the inputs it
    was shown. Structural, and not alpha-equivalent: a consistent rename of
    the reference's names is refused. Each rule this reduces by is an identity
    over all inputs, which is what makes "all inputs" the claim, and a rewrite
    this list cannot state is a refusal rather than a credit.
    """
    mine = _normal_form(lines)
    theirs = _normal_form(record["reference_source"])
    return {"outcome": "pass" if mine is not None and mine == theirs
            else "fail"}


def instance(split: str, template: str, mechanism: str) -> dict:
    return make_task(split, template, mechanism)


def enumerate_instances(split: str) -> list:
    """Every distinct instance of a split, derived from the catalogue."""
    if split not in SPLITS:
        raise SoftwareTaskInvalid("unknown-split")
    templates = DEV_TEMPLATES if split == "dev" else HELD_OUT_TEMPLATES
    records = []
    for template in templates:
        for mechanism in _MECHANISMS_OF_SPLIT[split]:
            records.append(make_task(split, template, mechanism))
    return records


def instances_for_seed(split: str, seed: int) -> dict:
    """The instance a split and seed name, without exposing the answer."""
    if type(seed) is not int or seed < 0:
        raise SoftwareTaskInvalid("illegal-seed")
    records = enumerate_instances(split)
    return records[seed % len(records)]


def support() -> dict:
    return {
        "templates": len(PROGRAMS),
        "structures": len(STRUCTURES),
        "mechanisms": len(MECHANISMS),
        "dev": len(enumerate_instances("dev")),
        "held_out": len(enumerate_instances("held_out")),
        "dev_templates": set(DEV_TEMPLATES),
        "held_out_templates": set(HELD_OUT_TEMPLATES),
        "dev_families": set(DEV_MECHANISMS),
        "held_out_families": set(HELD_OUT_MECHANISMS),
    }
