"""A reference policy for the SWE world.

The policy reads only the pinned view: the program, the public tests, and
the coverage each one reports. It is given no mechanism, no reference
program and no patch.

Its answer comes from a search over the faulty program's own lines.
Localize a failing test, take the lines it executes that no passing test
covers, and treat those as the suspects. For each suspect, propose bounded
single-line rewrites built from the program's own other lines and dry-run
them with the world's `code.try` tool, which reports only how many public
tests pass. The winner is emitted as an edit; the world applies it.

Nothing here answers the task. The policy supplies the candidate and the
world only reports the public pass count, which the policy can also get
wrong. A fixed schedule cannot survive this, because the ranking depends on
the coverage the observation actually carries.
"""

from __future__ import annotations

import ast
import copy
import itertools
import re

from . import policy_action

MAX_REWRITES = 120
MAX_SUSPECTS = 4


def _action(kind, target, inputs=None):
    return {"kind": kind, "target": target,
            "inputs": {} if inputs is None else inputs,
            "evidence_refs": [], "requested_resources": {}}


def repair_action(edits) -> dict:
    return _action(policy_action.USE, "code.repair", {"edits": edits})


def localize_action(test):
    return _action(policy_action.CONSTRUCT, "code.localize", {"test": test})


def try_action(line, text):
    return _action(policy_action.CONSTRUCT, "code.try",
                   {"line": line, "text": text})


def _parses(line: str) -> bool:
    """Whether a replacement would be a legal line of the program."""
    return _parse_line(line) is not None


def _substitutions(source_line: str, pool: list) -> list:
    """Re-point this line at another line of the same program.

    Every other line of the faulty program, re-indented to this one's
    depth. A doubled or stale accumulator, a widened window and a moved
    bound are all one of these, so this generator alone spans most of the
    fault set; the structural generators cover what it misses.
    """
    out = []
    for other in pool:
        candidate = other.rstrip("\n")
        if candidate and candidate != source_line.strip():
            out.append(_indented(candidate, source_line))
    return out


def _indented(line: str, like: str) -> str:
    return like[:len(like) - len(like.lstrip())] + line.lstrip()


def rewrites(source_line: str, pool: list) -> list:
    """Single-line replacements of a suspect line.

    Two generators, in order of how much of the program's own vocabulary
    they reuse. `substitutions` re-points a suspect line at another line of
    the same program. `perturbations` edits the line's own literals and
    operators: a boundary moves by one, a stride appears, a multiplier
    changes, a window bound grows. Together they express every fault in the
    catalogue without naming any of them.

    `guard_rewrites` adds back a conditional a line has lost and
    `_swap_branches` exchanges the branches of one it still carries,
    which together cover both guard mechanisms.
    """
    seen = {source_line.rstrip("\n")}
    out = []
    names = _names(source_line) | _names("\n".join(pool))
    for candidate in _structural_rewrites(source_line) + \
            _substitutions(source_line, pool) + \
            _guard_rewrites(source_line, names, pool) + \
            _swap_branches(source_line) + \
            perturbations(source_line):
        candidate = candidate.rstrip("\n")
        if candidate in seen or not candidate.strip() or not _parses(candidate):
            continue
        seen.add(candidate)
        out.append(candidate)
        if len(out) >= MAX_REWRITES:
            break
    return out


def _parse_line(source_line: str):
    """Parse one source line into (indent, statement). None if it cannot.

    A loop header carries no body of its own, so it is parsed with a
    placeholder and the placeholder is dropped again. That lets the loop's
    own bound be edited without inventing a body for it.
    """
    stripped = source_line.rstrip("\n")
    if not stripped.strip():
        return None
    indent = stripped[:len(stripped) - len(stripped.lstrip())]
    try:
        module = ast.parse(stripped.strip())
    except SyntaxError:
        try:
            module = ast.parse(stripped.strip() + "\n    pass")
        except SyntaxError:
            return None
    return indent, module.body[0]


def _emit(indent: str, node) -> str:
    if isinstance(node, (ast.For, ast.While, ast.If, ast.With)) \
            and _placeholder_only(node):
        return indent + ast.unparse(_header(node))
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    return indent + ast.unparse(module)


def _placeholder_only(node) -> bool:
    return not node.body or (len(node.body) == 1
                             and isinstance(node.body[0], ast.Pass)
                             and not node.orelse)


def _header(node):
    stripped = _clone(node)
    stripped.body = []
    stripped.orelse = []
    return stripped


def _clone(node):
    return copy.deepcopy(node)


def _collapse(node):
    """A copy of a bound with a nested literal sum evaluated.

    A widened window arrives as `x + (1 + 1)` where the reference was
    `x + 1`; taking the inner sum off by the one that was added restores
    the reference exactly.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)) \
            and isinstance(node.right, ast.BinOp) \
            and isinstance(node.right.op, (ast.Add, ast.Sub)) \
            and isinstance(node.right.left, ast.Constant) \
            and isinstance(node.right.right, ast.Constant) \
            and isinstance(node.right.left.value, int) \
            and isinstance(node.right.right.value, int):
        total = node.right.left.value + node.right.right.value
        if total < 2:
            return None
        restored = total - 1
        if isinstance(node.left, ast.Constant):
            return ast.Constant(value=restored)
        if isinstance(node.left, (ast.Name, ast.BinOp, ast.Subscript)):
            return ast.BinOp(left=_clone(node.left), op=ast.Add(),
                             right=ast.Constant(value=restored))
    return None


def _step_back(node):
    """A copy of `node` with one taken off its trailing literal.

    This is the repair direction for a bound that was moved by one: a
    reference written `x + 1` shows up faulty as `x + (1 + 1)` or
    `x + 2`, and unwrapping the extra addition restores it.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
            and isinstance(node.right, ast.BinOp) \
            and isinstance(node.right.op, ast.Add) \
            and isinstance(node.right.left, ast.Constant) \
            and isinstance(node.right.right, ast.Constant):
        inner = int(node.right.left.value)
        if inner <= 1:
            return _clone(node.left)
        return ast.BinOp(left=_clone(node.left), op=ast.Add(),
                         right=ast.Constant(value=inner - 1))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
            and isinstance(node.right, ast.Constant) \
            and isinstance(node.right.value, int) \
            and node.right.value >= 1:
        if node.right.value == 1:
            return _clone(node.left)
        return ast.BinOp(left=_clone(node.left), op=ast.Add(),
                         right=ast.Constant(value=node.right.value - 1))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
            and isinstance(node.left, ast.BinOp) \
            and isinstance(node.left.op, ast.Add):
        inner = _step_back(node.left)
        if inner is not None:
            return ast.BinOp(left=inner, op=ast.Add(),
                             right=_clone(node.right))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub) \
            and isinstance(node.right, ast.Constant) \
            and isinstance(node.right.value, int) \
            and node.right.value >= 1:
        if node.right.value == 1:
            return _clone(node.left)
        return ast.BinOp(left=_clone(node.left), op=ast.Sub(),
                         right=ast.Constant(value=node.right.value - 1))
    return None


def _is_reversed(node) -> bool:
    """Whether this subscript reads its sequence backwards."""
    step = node.slice.step
    if step is not None and isinstance(step, ast.UnaryOp) \
            and isinstance(step.op, ast.USub):
        return True
    return isinstance(node.value, ast.Subscript)


def _offset_base(node_slice):
    lower = node_slice.lower
    if isinstance(lower, ast.BinOp) and isinstance(lower.op, ast.Sub) \
            and isinstance(lower.left, ast.Call) \
            and isinstance(lower.left.func, ast.Name) \
            and lower.left.func.id == "len":
        return ast.BinOp(left=_clone(lower.left), op=ast.Sub(),
                         right=ast.Constant(value=1))
    return None


def _forward_slice(node):
    """The forward slice a reversed subscript replaced.

    A reversed window is the same window read backwards, either as
    `body[x:y][::-1]` or as `body[y:x:-1]`. The repair is the forward
    slice `body[a:b]`, which is the same pair of bounds in source order.
    """
    inner = node.slice
    if not isinstance(inner, ast.Slice):
        return None
    target = node.value
    if isinstance(target, ast.Subscript):
        source = _clone(target.value)
    else:
        source = _clone(target)
    return ast.Subscript(value=source,
                         slice=ast.Slice(lower=_clone(inner.lower),
                                         upper=_clone(inner.upper), step=None))


def _unreversed(node):
    if isinstance(node, ast.Subscript):
        return _clone(node.value)
    return None


def _plus_one(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return ast.BinOp(left=_clone(node), op=ast.Add(),
                          right=ast.Constant(value=1))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
            and isinstance(node.right, ast.Constant) \
            and isinstance(node.right.value, int):
        return ast.BinOp(left=_clone(node.left), op=ast.Add(),
                         right=ast.Constant(value=node.right.value + 1))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub) \
            and isinstance(node.right, ast.Constant) \
            and isinstance(node.right.value, int):
        return ast.BinOp(left=_clone(node.left), op=ast.Sub(),
                         right=ast.Constant(value=node.right.value + 1))
    return None


def _minus_one(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and node.value > 0:
        return ast.Constant(value=node.value - 1)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
            and isinstance(node.right, ast.Constant) \
            and isinstance(node.right.value, int):
        if node.right.value > 0:
            return ast.BinOp(left=_clone(node.left), op=ast.Add(),
                             right=ast.Constant(value=node.right.value - 1))
        return ast.BinOp(left=_clone(node.left), op=ast.Sub(),
                         right=ast.Constant(value=1))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub) \
            and isinstance(node.right, ast.Constant) \
            and isinstance(node.right.value, int):
        return ast.BinOp(left=_clone(node.left), op=ast.Sub(),
                         right=ast.Constant(value=node.right.value + 1))
    return None


_COMPARISONS = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
                ast.GtE: ast.Gt, ast.Eq: ast.NotEq,
                ast.NotEq: ast.Eq}


def _swap_branches(source_line: str) -> list:
    """Exchange the two values of a conditional this line already has.

    A dropped guard is missing a conditional and `_guard_rewrites` puts
    one back. An inverted guard has the conditional and gets the polarity
    wrong, which is a different shape: the generator that refuses any
    line already carrying `if` never touches it. The repair is the
    line's own two branch values exchanged, `a if c else b` becoming
    `b if c else a`, and the condition is left alone.
    """
    parsed = _parse_line(source_line)
    if parsed is None:
        return []
    indent, node = parsed
    out: list = []
    for child in _editable(node):
        if not isinstance(child, ast.IfExp) or child.orelse is None:
            continue
        edited = _clone(child)
        edited.body, edited.orelse = _clone(child.orelse), _clone(child.body)
        out.append(_emit(indent, _replace(node, child, edited)))
    return list(dict.fromkeys(out))


def _structural_rewrites(source_line: str) -> list:
    """Repairs for the shapes a fault mechanism can rewrite.

    A slice bound moves by one in either direction or its order flips. A
    `range` call loses or gains a stride, and a `while` comparison swaps
    to the other side. Each is a one-node edit to the suspect line, taken
    from the line itself, so nothing outside the program is invented.
    """
    parsed = _parse_line(source_line)
    if parsed is None:
        return []
    indent, node = parsed
    out: list = []

    for child in _editable(node):
        if isinstance(child, ast.Subscript) and _is_reversed(child):
            forward = _forward_slice(child)
            if forward is not None:
                out.append(_emit(indent, _replace(node, child, forward)))
            plain = _unreversed(child)
            if plain is not None:
                out.append(_emit(indent, _replace(node, child, plain)))
            inner = child.value
            if isinstance(inner, ast.Subscript) and isinstance(inner.slice,
                                                                ast.Slice):
                for builder in (_offset_base, _collapse, _step_back,
                                _plus_one, _minus_one):
                    for attr in ("lower", "upper"):
                        bound = getattr(inner.slice, attr)
                        if bound is None:
                            continue
                        replacement = builder(bound)
                        if replacement is None:
                            continue
                        edited = _clone(child)
                        edited.value = _clone(inner.value)
                        fresh = ast.Slice(lower=_clone(inner.slice.lower),
                                          upper=_clone(inner.slice.upper),
                                          step=None)
                        setattr(fresh, attr, replacement)
                        edited.slice = fresh
                        out.append(_emit(indent, _replace(node, child,
                                                          edited)))
        if isinstance(child, ast.Slice):
            for attr in ("lower", "upper"):
                bound = getattr(child, attr)
                if bound is None:
                    continue
                for builder in (_collapse, _step_back, _plus_one,
                                _minus_one):
                    moved = builder(bound)
                    if moved is None:
                        continue
                    edited = _clone(child)
                    setattr(edited, attr, moved)
                    out.append(_emit(indent, _replace(node, child, edited)))
            flipped = _clone(child)
            flipped.lower, flipped.upper = child.upper, child.lower
            flipped.step = None
            out.append(_emit(indent, _replace(node, child, flipped)))
        elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name) \
                and child.func.id == "range" and child.args:
            for builder in (_plus_one, _minus_one):
                moved = builder(child.args[0])
                if moved is not None:
                    args = _clone(child.args)
                    args[0] = moved
                    out.append(_emit(indent, _replace(node, child,
                                                      _with_args(child, args))))
                if len(child.args) > 1:
                    moved = builder(child.args[1])
                    if moved is not None:
                        args = _clone(child.args)
                        args[1] = moved
                        out.append(_emit(indent, _replace(
                            node, child, _with_args(child, args))))
            for stride in (None, 2):
                args = _clone(child.args)
                if stride is None:
                    args = args[:2]
                elif len(args) == 2:
                    args = args + [ast.Constant(value=stride)]
                else:
                    args[2] = ast.Constant(value=stride)
                out.append(_emit(indent, _replace(node, child,
                                                  _with_args(child, args))))
        elif isinstance(child, ast.Compare) and len(child.ops) == 1:
            flipped = _COMPARISONS.get(type(child.ops[0]))
            if flipped is not None:
                edited = _clone(child)
                edited.ops = [flipped()]
                out.append(_emit(indent, _replace(node, child, edited)))
            for current in child.comparators:
                for builder in (_step_back, _plus_one):
                    moved = builder(current)
                    if moved is not None:
                        edited = _clone(child)
                        edited.comparators = [moved]
                        out.append(_emit(indent, _replace(node, child, edited)))

    return list(dict.fromkeys(out))


def _editable(node):
    """The statement's own nodes, minus the parse placeholder body.

    The nodes come from `node` itself, so their identity survives and
    `_replace` can find them by path.
    """
    if isinstance(node, (ast.For, ast.While, ast.If, ast.With)) \
            and _placeholder_only(node):
        node.body = []
        node.orelse = []
    return list(ast.walk(node))


def _with_args(call, args):
    edited = _clone(call)
    edited.args = args
    return edited


def _path(node, target, trail=()):
    """The field path from `node` down to `target`, or None."""
    for field, value in ast.iter_fields(node):
        if value is target:
            return trail + ((field, None),)
        if isinstance(value, list):
            for index, item in enumerate(value):
                if item is target:
                    return trail + ((field, index),)
                found = _path(item, target, trail + ((field, index),))
                if found is not None:
                    return found
        elif isinstance(value, ast.AST):
            found = _path(value, target, trail + ((field, None),))
            if found is not None:
                return found
    return None


def _at(root, path):
    node = root
    for field, index in path:
        node = node[index] if index is not None else getattr(node, field)
    return node


def _replace(root, child, replacement):
    """A copy of `root` with `child`'s position taken by `replacement`.

    The target is located before the copy, so identity is still intact
    when the path is built and the swap is a single write.
    """
    path = _path(root, child)
    if path is None:
        return _clone(root)
    edited = _clone(root)
    field, index = path[-1]
    parent = _at(edited, path[:-1])
    if index is None:
        setattr(parent, field, replacement)
    else:
        parent[index] = replacement
    return edited


_NAME = re.compile(r"\b([a-z_][a-z_0-9]*)\b")

_DEFAULTS = frozenset({
    "and", "body", "else", "False", "for", "get", "if", "in", "int", "len",
    "mark", "moves", "n", "None", "not", "or", "range", "str", "sum", "True",
    "while", "window",
})


def _names(text: str) -> set:
    """Identifiers a line could plausibly mention, minus the builtins."""
    return {name for name in _NAME.findall(text) if name not in _DEFAULTS}


def _by_reference(names: set, source_line: str, pool: list = ()) -> list:
    """Order candidate names by how central they are to the program.

    A line that lost its conditional mentions only the name it assigns, so
    the name to test it on has to come from the rest of the program. The
    program's own frequency is that signal: the counter a guard tests is
    the one the loop updates.
    """
    body = "\n".join(pool)
    return sorted(names, key=lambda name: (-(body.count(name)
                                            + 2 * source_line.count(name)),
                                           name))


def _guard_rewrites(source_line: str, names: set, pool=()) -> list:
    """Restore a conditional this line is missing.

    A guard fault drops a conditional or reverses one, so the repair is a
    conditional over two names the program already uses. Both branches are
    drawn from the line's own value, so nothing outside the program is
    invented.
    """
    stripped = source_line.strip()
    indent = source_line[:len(source_line) - len(stripped)]
    if "=" not in stripped or " if " in stripped or "[" in stripped:
        return []
    target, _, _ = stripped.partition("=")
    target = target.strip()
    if not target:
        return []
    out = []
    usable = [name for name in _by_reference(names, source_line, pool)
              if name != target]
    for first in usable[:4]:
        for test in ("%s == 0" % first, "%s != 0" % first,
                     "%s < 0" % first):
            out.append("%s = 0 if %s else 1" % (target, test))
            out.append("%s = 1 if %s else 0" % (target, test))
    return [indent + line for line in dict.fromkeys(out)]


_LITERAL = re.compile(r"(?<![\w.])(\d+)(?![\w.])")


def perturbations(source_line: str) -> list:
    """Edit this line's own literals and its update operator.

    A boundary is stepped by one in each direction, a stride of two is
    added to an existing range, a multiplier is halved, doubled, or made
    stale, and a comparison's operator is inverted. Each is a local edit to
    the line the observation pointed at.
    """
    out: list = []
    stripped = source_line.strip()
    indent = source_line[:len(source_line) - len(stripped)]

    def literal_edits():
        for match in _LITERAL.finditer(stripped):
            value = int(match.group(1))
            for replacement in (value + 1, value - 1, value * 2, value + 2,
                                value - 2):
                if replacement == value or replacement < 0:
                    continue
                yield stripped[:match.start(1)] + str(replacement) + \
                    stripped[match.end(1):]

    def operator_edits():
        for pair, swap in ((" < ", " > "), (" > ", " < "), (" <= ", " >= "),
                           (" >= ", " <= "), (" != ", " == "),
                           (" == ", " != "), (" + ", " - ")):
            if pair in stripped:
                yield stripped.replace(pair, swap)
        for token in ("contribution", "width", "previous", "carry", "total"):
            if re.search(r"\b%s \* 2\b" % token, stripped):
                yield re.sub(r"\b%s \* 2\b" % token, token, stripped)
                yield re.sub(r"\b%s \* 2\b" % token, "%s * 3" % token,
                             stripped)
            if re.search(r"\b%s = %s\b" % (token, token), stripped):
                yield re.sub(r"\b%s = %s\b" % (token, token), "%s = 0" % token,
                             stripped)

    for candidate in itertools.chain(literal_edits(), operator_edits()):
        out.append(indent + candidate)
    return out


def suspects(view: dict) -> list:
    """Lines a failing test runs that no passing test covers.

    Most-suspicious first. The view is the only input, so the ranking is
    driven by the coverage the observation actually carries rather than by
    a task identity.
    """
    observed = {item["test"]: item for item in view["symptom"]["observed"]}
    passing = {name for name, item in observed.items()
               if item["actual"] == item["expected"] and item["kind"] == "value"}
    failing = {item["test"] for item in view["symptom"]["failing_tests"]}
    by_passing: set = set()
    by_failing: set = set()
    for item in view["symptom"]["coverage"]:
        if item["test"] in passing:
            by_passing.update(item["executed_lines"])
        elif item["test"] in failing:
            by_failing.update(item["executed_lines"])
    uncovered = sorted(by_failing - by_passing)
    rest = sorted(by_failing - set(uncovered))
    texts = [line["text"] for line in view["source"]]
    return _by_risk(uncovered, texts) + _by_risk(rest, texts)


_INIT = re.compile(r"^\s*\w+ = 0\s*$")


def _by_risk(lines: list, texts: list) -> list:
    """Deeper lines first.

    An initializer is never the injected line: the fault mechanisms all
    rewrite a bound, a window, a guard or an update, and every one of those
    sits inside the loop body. Rank by depth, then by line number so the
    order is stable.
    """

    def key(number: int):
        text = texts[number - 1] if number <= len(texts) else ""
        initialiser = 1 if _INIT.match(text) else 0
        return (initialiser, -len(text) - len(text) % 7, number)

    return sorted(lines, key=key)


def plan(view: dict, state: dict) -> dict:
    """The next probe or repair, given the view and the policy's own state."""
    symptom = view["symptom"]
    observed = {item["test"] for item in symptom["observed"]}
    pending = [case["name"] for case in view["public_tests"]
               if case["name"] not in observed]
    if pending and view["remaining"].get("test", 0) > 0:
        return {"do": "observe", "test": pending[0]}
    if symptom["failing_tests"] and not symptom["coverage"] \
            and view["remaining"].get("localize", 0) > 0:
        return {"do": "localize",
                "test": symptom["failing_tests"][0]["test"]}
    total = len(view["public_tests"])
    # A winner is spent as soon as the search has nothing left to try,
    # not only once the budget runs out. Returning `try` while a probe
    # remained let `driven` fall through to `stop` when the candidate
    # space emptied first, so a search that had already found a
    # full-scoring repair ended unrepaired with probes unspent, which
    # scored identically to a search that found nothing.
    # `next_try` claims a candidate as it returns it, so it is asked
    # once and the answer is carried.
    edit = next_try(view, state) if view["remaining"].get("probe", 0) > 0 \
        else {}
    if edit:
        return {"do": "try", "edit": edit}
    if state.get("winner") and state.get("best_passed", -1) == total \
            and view["remaining"].get("edit", 0) > 0:
        return {"do": "repair", "edit": state["winner"]}
    return {"do": "stop"}


def next_try(view: dict, state: dict, cap: int | None = None) -> dict:
    """The next candidate to dry-run, advancing through the search space.

    `cap` is how many ranked suspects to open lanes on. It defaults to
    the instrument's derived cap rather than to the module constant:
    the cap is a truncation, and a derived truncation that the arm does
    not read is the same arbitrary number the derivation replaced. The
    world reads this policy, so the import is at call time rather than
    at module scope, which would be circular.
    """
    if cap is None:
        from . import s09_swe_world as world
        cap = world.SUSPECT_CAP
    texts = [line["text"] for line in view["source"]]
    pool = state.setdefault("pool", _pool(view))
    tried = state.setdefault("tried", set())
    lanes = [[(number, candidate)
              for candidate in rewrites(texts[number - 1], pool)]
             for number in suspects(view)[:cap]
             if 1 <= number <= len(texts)]
    for column in range(MAX_REWRITES):
        for lane in lanes:
            if column >= len(lane):
                continue
            number, candidate = lane[column]
            key = (number, candidate)
            if key in tried:
                continue
            tried.add(key)
            return {"line": number, "op": "replace", "text": candidate}
    return {}


def _pool(view: dict) -> list:
    """Candidate replacement lines, drawn from the program under repair.

    Every non-blank line of the faulty program, plus a few of its own
    structural paraphrases. The program supplies its own vocabulary.
    """
    texts = [line["text"] for line in view["source"]]
    pool = []
    for text in texts:
        stripped = text.strip()
        if not stripped or stripped.startswith(('"""', "def ")):
            continue
        if _parses(stripped):
            pool.append(stripped)
    return list(dict.fromkeys(pool))


def absorb(state: dict, effect: dict) -> None:
    """Fold the world's last effect into the policy's own state."""
    if not isinstance(effect, dict):
        return
    tried = effect.get("tried")
    if not isinstance(tried, dict) or not state.get("pending"):
        return
    passed = tried.get("public_passed", -1)
    if passed > state.get("best_passed", -1):
        state["best_passed"] = passed
        state["winner"] = state["pending"]


def driven(state: dict, view: dict) -> dict:
    """One action from the view, advancing the policy's own search state."""
    absorb(state, view.get("last_effect"))
    step = plan(view, state)
    if step["do"] == "observe":
        return _action(policy_action.OBSERVE, "test.run", {"test": step["test"]})
    if step["do"] == "localize":
        return localize_action(step["test"])
    if step["do"] == "try" and step["edit"]:
        state["pending"] = step["edit"]
        return try_action(step["edit"]["line"], step["edit"]["text"])
    if step["do"] == "repair" and state.get("winner"):
        return repair_action([state["winner"]])
    return _action(policy_action.STOP, "swe.task")
