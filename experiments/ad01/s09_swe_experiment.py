"""E1 on the SWE world: three representations, four lineages each.

The instrument (`s09_swe_world`, `s09_swe_tasks`, `s09_swe_policy`) was
written and qualified but never pointed at anything, so it had no
experimental evidence. This module is the experiment: it builds the
cells, runs every lineage over both splits, and reports every outcome
including the ones that fail.

What the three representations can express on this world is the finding,
and all three cells now build. Two were missing for different measured
reasons and both reasons were bindings rather than limits:

* `python-step` runs the shared bounded child. The view is the SWE
  policy view, so the program under repair and the coverage evidence
  are both readable, and the search is real. Whether the child can be
  spawned is the host's business and is now reported per row rather
  than swallowed: a step that cannot run records a `bridge_refusal`
  naming the reason, and the ledger counts that refusal separately from
  an episode that ran and repaired nothing.
* `typed-ast` is a projection over `boolean_ast_policy`, the same shape
  of work `ordering_ast_policy` does for the ordering world: a view
  projection and the world's own action rules, with the frozen loader,
  node set and interpreter borrowed unchanged. The cell builds, and it
  is labelled `fixture-stand-in` on every record because no provider
  wrote any of it.
* `action-graph` runs the real `ordering_graph_policy` executor against
  `s09_swe_binding.SWE_WORLD`. `World` was always a value rather than a
  subclass, so a SWE world is a binding and the executor needed no
  change.

The two cells still cannot repair, and the reasons are limits of the
representations rather than of the study:

* the typed AST's frozen `_VIEW_TYPES` publishes no field for the
  program under repair, so it cannot choose an edit line from what it
  observed. It does build replacement source text — a document whose
  edit payload is assembled by `obj` and `list` nodes loads and the SWE
  world runs the resulting repair — so only the reading half is a limit;
* the action graph's `_parse_action` deep-copies the raw action node, so
  a value a guard just read never reaches an action input, and
  `code.localize` is admitted only for a test the world has already seen
  fail, which the load-time `static_view` never has.

Both are recorded as data in `s09_swe_ast.missing_cells()` and attached
to the lineage, so a zero repair rate is not left to be misread as a
broken arm.

A lineage is one independently built policy artifact executed over the
whole panel. Independence is the record digest, and every lineage is
reported whether it repaired anything or not.

Two measured constraints decide how every repair rate below reads, and
both are reported beside them rather than folded into it.

`probe_reach` asks whether the `code.try` budget reaches the injected
fault line at all. A solver that never dry-runs the faulty line cannot
repair it, so a low reach rate makes the repair rate a statement about
the budget. The budget is now derived from the panel rather than typed
in, and reach is 30 of 30 held-out.

`search_span` asks the harder question, whether the candidate set
contains the reference repair *at all*. Reach and expressiveness are
different facts, and a family the generator cannot express is
unreachable for a reason no budget fixes. Ten instances across both
splits are in that state, and naming them is worth more than a rate
that pools them with the truncated ones.

Both figures live in the written evidence rather than in this
docstring, because they moved every time a bound was corrected and a
number copied into prose goes stale.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from . import boolean_ast_policy
from . import boolean_policy
from . import ordering_graph_policy
from . import policy_action
from . import policy_step
from . import s09_swe_policy as search
from . import s09_swe_tasks as tasks
from . import s09_swe_world as world

PYTHON_STEP = "python-step"
TYPED_AST = "typed-ast"
ACTION_GRAPH = "action-graph"
REPRESENTATIONS = (PYTHON_STEP, TYPED_AST, ACTION_GRAPH)

# How many independently built artifacts each supported cell gets. The
# handoff asks for at least four, and "independent" is the record digest
# rather than a name: four lineages whose records hash alike would be one
# lineage wearing four names.
LINEAGES_PER_CELL = 4

OUTCOMES = ("repaired", "unrepaired", "crashed", "refused")


@dataclass(frozen=True)
class Lineage:
    """One independently built policy artifact."""

    name: str
    representation_kind: str
    record: dict
    built_ok: bool
    build_error: str = ""
    policy_source: str = ""

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.record, sort_keys=True, default=str).encode()
        ).hexdigest()

    def as_dict(self) -> dict:
        return {"name": self.name,
                "representation_kind": self.representation_kind,
                "digest": self.digest,
                "built": self.built_ok,
                "build_error": self.build_error}


@dataclass(frozen=True)
class SweRow:
    """One episode of one lineage against one instance."""

    representation_kind: str
    lineage: str
    lineage_digest: str
    task_id: str
    split: str
    structure: str
    fault_mechanism: str
    outcome: str
    public_passed: int
    public_total: int
    protected: str
    turns: int
    refused: str = ""
    actions_emitted: tuple = ()

    def as_dict(self) -> dict:
        """The row with its trace and refusal inline.

        Kept whole on purpose. `result_payload` is what writes evidence,
        and it references the repeated fields instead of restating them;
        this stays the faithful view of one row, which is what the round
        trip is checked against.
        """
        return {
            "representation_kind": self.representation_kind,
            "lineage": self.lineage,
            "lineage_digest": self.lineage_digest,
            "task_id": self.task_id,
            "split": self.split,
            "structure": self.structure,
            "fault_mechanism": self.fault_mechanism,
            "outcome": self.outcome,
            "public_passed": self.public_passed,
            "public_total": self.public_total,
            "protected": self.protected,
            "turns": self.turns,
            "refused": self.refused,
            "actions_emitted": list(self.actions_emitted),
        }


@dataclass(frozen=True)
class FamilyTable:
    structure: str
    fault_mechanism: str
    instances: int
    repaired: int
    representations: tuple

    @property
    def rate(self) -> float:
        return self.repaired / self.instances if self.instances else 0.0

    def as_dict(self) -> dict:
        return {"structure": self.structure,
                "fault_mechanism": self.fault_mechanism,
                "instances": self.instances,
                "repaired": self.repaired,
                "rate": round(self.rate, 4),
                "representations": list(self.representations)}


@dataclass(frozen=True)
class LineageLedgerEntry:
    name: str
    representation_kind: str
    digest: str
    episodes: int
    repairs: int
    refusals: int
    build_error: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name,
                "representation_kind": self.representation_kind,
                "digest": self.digest,
                "episodes": self.episodes,
                "repairs": self.repairs,
                "refusals": self.refusals,
                "build_error": self.build_error}


@dataclass(frozen=True)
class PairedComparison:
    left: SweRow
    right: SweRow

    def as_dict(self) -> dict:
        return {"task_id": self.left.task_id,
                "structure": self.left.structure,
                "fault_mechanism": self.left.fault_mechanism,
                "left": {"representation_kind": self.left.representation_kind,
                         "lineage": self.left.lineage,
                         "outcome": self.left.outcome},
                "right": {"representation_kind": self.right.representation_kind,
                          "lineage": self.right.lineage,
                          "outcome": self.right.outcome},
                "agree": self.left.outcome == self.right.outcome}


@dataclass
class MatrixResult:
    rows: list = field(default_factory=list)
    lineages_run: int = 0
    missing_cells: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def by_split(self, split: str) -> list:
        return [row for row in self.rows if row.split == split]


# --- the STEP lineage source ---------------------------------------------
#
# The search the reference policy performs, written in the STEP language
# and run by the shared bounded child. It reads the SWE policy view: the
# program under repair, the public tests and the coverage a failing test
# reports. It is given no mechanism, no reference program and no patch,
# and it names none: `test_the_step_lineage_policy_source_never_mentions
# _a_fault_mechanism` checks the source text itself.
#
# Each lineage differs in the order it works the candidate edits, which
# is the only knob that changes without changing what the policy is
# allowed to know. Two lineages with the same order would be the same
# policy, and the digest test catches that.

_STEP_HEADER = '''MAX_REWRITES = 120
MAX_SUSPECTS = @CAP@
ORDER = @ORDER@

PAIRS = ((" < ", " > "), (" > ", " < "), (" <= ", " >= "),
         (" >= ", " <= "), (" == ", " != "), (" != ", " == "),
         (" + ", " - "))
TOKENS = ("contribution", "width", "previous", "carry", "total")


def act(kind, target, inputs):
    return {"kind": kind, "target": target, "inputs": inputs,
            "evidence_refs": [], "requested_resources": {}}


def indent_of(line):
    cut = 0
    while cut < len(line) and line[cut] == " ":
        cut = cut + 1
    return line[:cut]


def parses(line):
    body = line.strip()
    if not body:
        return False
    if body.startswith(("def ", '"""')):
        return False
    depth = 0
    quote = ""
    for index in range(len(body)):
        char = body[index]
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\\"":
            quote = char
        elif char in "([{":
            depth = depth + 1
        elif char in ")]}":
            depth = depth - 1
            if depth < 0:
                return False
    return depth == 0 and not quote


def lines_of(view):
    out = []
    for entry in view["source"]:
        out.append(entry["text"])
    return out


def pool_of(view):
    out = []
    for text in lines_of(view):
        stripped = text.strip()
        if parses(stripped) and stripped not in out:
            out.append(stripped)
    return out


def digit_spans(text):
    out = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isdigit():
            before_ok = index == 0 or not (text[index - 1].isalnum()
                                           or text[index - 1] == ".")
            start = index
            while index < len(text) and text[index].isdigit():
                index = index + 1
            after_ok = index >= len(text) or not (text[index].isalnum()
                                                  or text[index] == ".")
            if before_ok and after_ok:
                out.append((start, index, int(text[start:index])))
        else:
            index = index + 1
    return out


def perturbations(source_line):
    stripped = source_line.strip()
    lead = indent_of(source_line)
    out = []
    for start, end, value in digit_spans(stripped):
        for step in (1, 2, 3):
            if value + step != value:
                out.append(lead + stripped[:start] + str(value + step)
                           + stripped[end:])
        if value > 0:
            out.append(lead + stripped[:start] + str(value - 1)
                       + stripped[end:])
    for pair, swap in PAIRS:
        if pair in stripped:
            out.append(lead + stripped.replace(pair, swap))
    for token in TOKENS:
        if token + " * 2" in stripped:
            out.append(lead + stripped.replace(token + " * 2", token))
    return out


def substitutions(source_line, pool):
    out = []
    lead = indent_of(source_line)
    for other in pool:
        if other and other != source_line.strip():
            out.append(lead + other)
    return out


DEFAULTS = ("and", "body", "else", "False", "for", "get", "if", "in",
            "int", "len", "mark", "moves", "n", "None", "not", "or",
            "range", "str", "sum", "True", "while", "window")


def name_set(text, out):
    """Identifiers `text` could mention, minus the builtins. The child
    forbids imports, so a set is built by hand and returned."""
    if out is None:
        out = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isalpha() or char == "_":
            start = index
            while index < len(text) and (text[index].isalnum()
                                         or text[index] == "_"):
                index = index + 1
            word = text[start:index]
            if word not in DEFAULTS and word not in out:
                out.append(word)
        else:
            index = index + 1
    return out


def by_reference(names, source_line, pool):
    """Order candidate names by how central they are to the program.

    A line that lost its conditional mentions only the name it assigns,
    so the name to test a restored guard on has to come from the rest of
    the program. The program's own frequency is that signal. `str` and
    `join` are available here, unlike a regular expression.
    """
    body = join_text(pool)
    ordered = []
    for name in names:
        weight = 0
        index = 0
        while True:
            found = body.find(name, index)
            if found < 0:
                break
            weight = weight + 1
            index = found + 1
        weight = weight + 2 * count_word(source_line, name)
        ordered.append((-weight, name, name))
    ordered.sort()
    out = []
    for item in ordered:
        out.append(item[2])
    return out


def join_text(items):
    out = ""
    for item in items:
        out = out + item + "\\n"
    return out


def count_word(text, name):
    total = 0
    index = 0
    while True:
        found = text.find(name, index)
        if found < 0:
            return total
        before_ok = found == 0 or not (text[found - 1].isalnum()
                                       or text[found - 1] == "_")
        after = found + len(name)
        after_ok = after >= len(text) or not (text[after].isalnum()
                                              or text[after] == "_")
        if before_ok and after_ok:
            total = total + 1
        index = found + 1


def guard_rewrites(source_line, names, pool):
    """Restore a conditional this line is missing.

    A guard fault drops a conditional or reverses one, so the repair is a
    conditional over two names the program already uses. Both branches
    are drawn from the line's own assigned name, so nothing outside the
    program is invented. This is the same generator the reference policy
    uses at module scope; it is restated here because the child forbids
    imports, and without it the two guard families are unreachable for
    a reason no budget explains.
    """
    stripped = source_line.strip()
    if "=" not in stripped or " if " in stripped or "[" in stripped:
        return []
    target = stripped.split("=")[0].strip()
    if not target:
        return []
    out = []
    for name in by_reference(names, source_line, pool)[:4]:
        if name == target:
            continue
        for test in (name + " == 0", name + " != 0", name + " < 0"):
            out.append(target + " = 0 if " + test + " else 1")
            out.append(target + " = 1 if " + test + " else 0")
    fresh = []
    for line in out:
        if line not in fresh:
            fresh.append(line)
    return [indent_of(source_line) + line for line in fresh]


COMPARISONS = ((" < ", " > "), (" > ", " < "), (" <= ", " >= "),
               (" >= ", " <= "), (" == ", " != "), (" != ", " == "))

# `state <= n` also reads as `state < n + 1`, so a bound that gained a
# one is repaired either by taking the `=` off or by adding the `+ 1`
# back. Both are edits to the operator the line already carries.
TIGHTEN = ((" <= ", " < "), (">= ", "< "), (" < ", " <= "), (" > ", " >= "))


def comparison_rewrites(source_line):
    """Flip or tighten the comparison this line already carries.

    A bound that moved by one arrives as `<=` where the reference wrote
    `<`, or as `< n - 1` where the reference wrote `< n`. Both are one
    edit to the line's own operator or its own trailing subtraction,
    and both are edges a solver has from the text in front of it.
    Nothing here consults a reference.
    """
    stripped = source_line.strip()
    lead = indent_of(source_line)
    out = []
    for pair, swap in COMPARISONS:
        if pair in stripped:
            out.append(lead + stripped.replace(pair, swap))
    for pair, tighter in TIGHTEN:
        if pair in stripped:
            out.append(lead + stripped.replace(pair, tighter))
    out.append(lead + drop_smallest_subtraction(stripped))
    fresh = []
    for line in out:
        if line not in fresh and parses(line.strip()):
            fresh.append(line)
    return fresh


def drop_smallest_subtraction(stripped):
    """`x - 1` becomes `x`: the smallest term a bound gained is removed.

    A bound that was moved by one and then expressed as a subtraction
    reads `state < n - 1` where the reference reads `state < n`. Taking
    the trailing literal subtraction off restores the reference for any
    operand, and it is the smallest term the program uses, so a
    subtraction of anything larger is left alone.
    """
    if " - " not in stripped:
        return stripped
    for value in (" - 1", " - 2"):
        if value in stripped:
            return stripped.replace(value, "")
    return stripped


def range_rewrites(source_line):
    """A `range` call loses or gains a stride.

    A stride of two on a `range` that had none is one argument to drop,
    and dropping the last argument of a `range` is the whole edit. The
    reference search reaches the same candidate by rebuilding the call
    with fewer arguments; here the call's own text carries the count.
    """
    stripped = source_line.strip()
    lead = indent_of(source_line)
    if "range(" not in stripped:
        return []
    open_at = stripped.index("range(") + len("range")
    close_at = find_close(stripped, open_at)
    if close_at < 0:
        return []
    inner = stripped[open_at + 1:close_at]
    if "," not in inner:
        return []
    fresh = []
    for drop in split_args(inner):
        candidate = lead + stripped[:open_at + 1] + drop + stripped[close_at:]
        if parses(candidate.strip()) and candidate not in fresh:
            fresh.append(candidate)
    return fresh


def split_args(inner):
    """Every shorter prefix of a call's comma-separated arguments.

    `range(1, n + 1, 2)` yields the two-argument and the
    one-argument forms, so the three-argument call reaches the two-
    argument one the panel's stride fault needs.
    """
    args = []
    depth = 0
    current = ""
    for char in inner:
        if char in "([{":
            depth = depth + 1
        elif char in ")]}":
            depth = depth - 1
        if char == "," and depth == 0:
            args.append(current)
            current = ""
        else:
            current = current + char
    args.append(current)
    out = []
    for size in range(len(args) - 1, 0, -1):
        out.append(", ".join(part.strip() for part in args[:size]))
    return out


def find_close(text, open_at):
    depth = 0
    index = open_at
    while index < len(text):
        if text[index] == "(":
            depth = depth + 1
        elif text[index] == ")":
            depth = depth - 1
            if depth == 0:
                return index
        index = index + 1
    return -1


def collapse_sums(stripped):
    """`x + (1 + 1)` becomes `x + 1`.

    A widened window arrives as a nested sum whose inner total is the
    outer literal plus one. Taking the inner sum off by exactly that one
    restores the reference, and it is the only reading of the line that
    does, so nothing is chosen: the parenthesised run of digits is
    replaced by its value less one and its parentheses go with it.
    """
    out = [stripped]
    index = 0
    while True:
        found = stripped.find("(", index)
        if found < 0:
            return out
        close = find_close(stripped, found)
        if close < 0:
            return out
        inner = stripped[found + 1:close]
        if " + " in inner and all(part.strip().isdigit()
                                  for part in inner.split(" + ")):
            total = sum(int(part) for part in inner.split(" + "))
            if total >= 2:
                out.append(stripped[:found].rstrip()
                           + (" " if stripped[found - 1:found] == " " else "")
                           + str(total - 1) + stripped[close + 1:])
        index = found + 1


def slice_rewrites(source_line):
    """Repair a subscript this line already carries.

    Three shapes, all of them one edit to the line's own slice: a
    widened bound arrives as a nested `+ (1 + 1)` and taking the inner
    sum off by the one that was added restores it; a reversed window
    arrives as `[::-1][a:b]` or as `a:b:-1` and dropping the reversal
    restores the forward slice; a slice whose bounds were swapped is
    the same slice with its two bounds exchanged.

    The text operations are the reference search's AST edits spelled
    over the line's own characters, so the child produces the same
    candidates the in-process search does without an import.
    """
    stripped = source_line.strip()
    lead = indent_of(source_line)
    out = []
    for candidate in collapse_sums(stripped):
        out.append(lead + candidate)
    for forward in unreverse(stripped):
        out.append(lead + forward)
        out.append(lead + swap_slice_bounds(forward))
    out.append(lead + swap_slice_bounds(stripped))
    fresh = []
    for line in out:
        body = line.strip()
        if line not in fresh and parses(body):
            fresh.append(line)
    return fresh


def unreverse(stripped):
    """The forward reads of a window that was read backwards.

    A reversed window is the same window read the other way, written
    either as a leading `[::-1]` or as a trailing `::-1` step. Both are
    one deletion over text the line already holds, and both leave the
    bounds exactly where they were.
    """
    out = []
    if "[::-1]" in stripped:
        out.append(stripped.replace("[::-1]", "", 1))
    if "::-1]" in stripped:
        out.append(stripped.replace("::-1]", "]", 1))
    return out


def swap_slice_bounds(stripped):
    """Exchange the two bounds of the first `[a:b]` this line carries.

    The forward slice of a reversed one is the same pair in source
    order, so swapping them is a single textual transposition of text
    the line already has.
    """
    open_at = stripped.find("[")
    if open_at < 0:
        return stripped
    close_at = find_close(stripped, open_at)
    if close_at < 0:
        return stripped
    inner = stripped[open_at + 1:close_at]
    if ":" not in inner:
        return stripped
    low, _, high = inner.partition(":")
    if not low.strip() or not high.strip():
        return stripped
    swapped = high.strip() + ":" + low.strip()
    return stripped[:open_at + 1] + swapped + stripped[close_at:]


def structural_rewrites(source_line):
    """The shape edits, then the literal edits, on the line's own text.

    Comparison flips, stride removal and slice repair are the shapes a
    fault mechanism can produce that no re-pointing at another line
    reaches. Every candidate is assembled from characters the line
    already holds.
    """
    out = comparison_rewrites(source_line) + range_rewrites(source_line) + \\
        slice_rewrites(source_line)
    fresh = []
    for line in out:
        stripped = line.strip()
        if not stripped or stripped in fresh or not parses(stripped):
            continue
        fresh.append(stripped)
    return [indent_of(source_line) + line for line in fresh]


def swap_branches(source_line):
    """Exchange the two values of a conditional this line already has.

    A dropped guard is missing a conditional and `guard_rewrites` puts
    one back. An inverted guard has the conditional and gets the polarity
    wrong, which is a different shape: the generator that refuses any
    line already carrying `if` never touches it. The repair is the
    line's own two values exchanged, `a if c else b` becoming
    `b if c else a`, and the condition is left alone.

    Split the assignment from the value, then split the value on the
    ` if ` and ` else ` this line already contains, so the swap is the
    line's own text and nothing is invented. A line that is not a
    one-line conditional assignment of a single bare name yields
    nothing.
    """
    stripped = source_line.strip()
    if " if " not in stripped or " else " not in stripped:
        return []
    target, assign, value = stripped.partition("=")
    target = target.strip()
    value = value.strip()
    if not assign.strip() or not target or not value:
        return []
    if not target.replace("_", "a").isalnum():
        return []
    head, _, rest = value.partition(" if ")
    condition, _, tail = rest.partition(" else ")
    head, condition, tail = head.strip(), condition.strip(), tail.strip()
    if not head or not condition or not tail:
        return []
    if " if " in tail or " else " in head:
        return []
    if not parses(stripped):
        return []
    return [indent_of(source_line) + target + " = " + tail + " if "
            + condition + " else " + head]


def rewrites(source_line, pool):
    seen = {source_line.strip()}
    out = []
    names = name_set(source_line, name_set(join_text(pool), []))
    for candidate in structural_rewrites(source_line) + \\
            perturbations(source_line) + substitutions(source_line, pool) + \\
            guard_rewrites(source_line, names, pool) + \\
            swap_branches(source_line):
        # Keep the indentation. Stripping it here produced candidates
        # like `total = total + contribution` for a line that lives
        # inside the function, and every one of those is an
        # IndentationError - so `code.try` reported 0 of 2 for the
        # *correct* repair and the search could never win. The dedup key
        # is still the stripped form, so two spellings of the same line
        # collapse.
        dedup = candidate.strip()
        if not dedup or dedup in seen or not parses(dedup):
            continue
        seen.add(dedup)
        out.append(indent_of(source_line) + dedup)
        if len(out) >= MAX_REWRITES:
            break
    return out


def initialiser(text):
    body = text.strip()
    if not body.endswith("= 0"):
        return False
    name = body[:-3]
    if not name or not name.replace("_", "a").isalnum():
        return False
    for char in name:
        if not (char.isalnum() or char == "_"):
            return False
    return True


def suspects(view):
    observed = {}
    for item in view["symptom"]["observed"]:
        observed[item["test"]] = item
    passing = []
    failing = []
    for item in view["symptom"]["observed"]:
        if item["actual"] == item["expected"] and item["kind"] == "value":
            passing.append(item["test"])
        else:
            failing.append(item["test"])
    by_passing = []
    by_failing = []
    for item in view["symptom"]["coverage"]:
        if item["test"] in passing:
            for line in item["executed_lines"]:
                if line not in by_passing:
                    by_passing.append(line)
        elif item["test"] in failing:
            for line in item["executed_lines"]:
                if line not in by_failing:
                    by_failing.append(line)
    uncovered = []
    for line in by_failing:
        if line not in by_passing:
            uncovered.append(line)
    rest = []
    for line in by_failing:
        if line in by_passing and line not in rest:
            rest.append(line)
    lines = lines_of(view)
    ranked = uncovered + rest
    clean = []
    for number in ranked:
        text = lines[number - 1] if number < len(lines) else ""
        if not initialiser(text):
            clean.append(number)
    # Rank by depth, not by line number. Sorting the numbers ascending
    # puts the fault last on a program whose tail is the return, and the
    # four-suspect cap then drops it before it is ever tried - which is
    # what made every supported episode score zero. The reference search
    # orders by "deeper first, initialiser last, then by number".
    ordered = sorted(clean, key=lambda number: risk_key(lines, number))
    if ORDER % 2 == 1:
        ordered = list(reversed(ordered))
    return ordered[:MAX_SUSPECTS]


def risk_key(lines, number):
    """Deeper lines first, initialisers last, then by number.

    This runs inside the STEP child, which forbids imports, so it is
    also restated at module scope as `_risk_key`. The two are pinned to
    agree by `test_the_module_level_risk_key_agrees_with_the_step_source`.
    """
    text = lines[number - 1] if number <= len(lines) else ""
    body = text.strip()
    is_init = body.endswith("= 0") and body[:-3].replace("_", "a").isalnum()
    return (1 if is_init else 0, -len(text), number)


def STEP(view, state):
    """One action for the observation the world just produced."""
    symptom = view["symptom"]
    seen = []
    for item in symptom["observed"]:
        seen.append(item["test"])
    pending = []
    for case in view["public_tests"]:
        if case["name"] not in seen:
            pending.append(case["name"])
    remaining = view["remaining"]

    if pending and remaining.get("test", 0) > 0:
        return {"action": act("observe", "test.run",
                              {"test": pending[0]}), "state": state}
    if symptom["failing_tests"] and not symptom["coverage"] \\
            and remaining.get("localize", 0) > 0:
        return {"action": act("construct", "code.localize",
                              {"test": symptom["failing_tests"][0]["test"]}),
                "state": state}
    if remaining.get("probe", 0) > 0:
        pool = state.get("pool")
        if pool is None:
            pool = pool_of(view)
            state["pool"] = pool
        tried = state.get("tried")
        if tried is None:
            tried = state["tried"] = []
        lines = lines_of(view)
        for number in suspects(view):
            if number < 0 or number >= len(lines):
                continue
            for candidate in rewrites(lines[number], pool):
                tag = str(number) + "|" + candidate
                if tag in tried:
                    continue
                tried.append(tag)
                state["pending"] = [number + 1, candidate]
                return {"action": act("construct", "code.try",
                                      {"line": number + 1,
                                       "text": candidate}),
                        "state": state}
    total = len(view["public_tests"])
    winner = state.get("winner")
    if winner and state.get("best", -1) == total \\
            and remaining.get("edit", 0) > 0:
        return {"action": act("use", "code.repair",
                              {"edits": [{"line": winner[0],
                                          "op": "replace",
                                          "text": winner[1]}]}),
                "state": state}
    return {"action": act("stop", "swe.task", {}), "state": state}
'''


def step_source(order: int) -> str:
    """The STEP source for one lineage.

    The `order` seam rotates which suspect line is tried first, so two
    lineages differ in their search order without either knowing
    anything the other does not. The suspect cap is a truncation like
    the probe budget, so it is filled in from the instrument's own
    derivation rather than typed into the source. The placeholders are
    tokens rather than `%d` because the source itself is full of `%`
    remainder operators, and `%`-formatting it would read them as
    conversions.
    """
    return (_STEP_HEADER
            .replace("@CAP@", str(world.SUSPECT_CAP))
            .replace("@ORDER@", str(order)))


def _absorb_bridge(state: dict, effect) -> None:
    """Fold the world's last effect into the policy's own best-so-far.

    The STEP child is one process per turn and returns only the state it
    was handed, so the effect the world produced this turn reaches the
    driver on the *next* turn inside `view["last_effect"]`. The absorb
    has to happen before the step reads `state["best"]`, which is why it
    lives in the driver rather than inside the step source.
    """
    if not isinstance(effect, dict):
        return
    tried = effect.get("tried")
    pending = state.get("pending")
    if not isinstance(tried, dict) or not pending:
        return
    passed = tried.get("public_passed", -1)
    if passed > state.get("best", -1):
        state["best"] = passed
        state["winner"] = list(pending)


def build_step_lineages() -> list:
    lineages = []
    for index in range(LINEAGES_PER_CELL):
        source = step_source(index)
        name = "%s-L%d" % (PYTHON_STEP, index)
        try:
            record = policy_step.make_policy_artifact(
                source, origin="authored-control",
                applicability={"world": 2, "arm": "E1", "lineage": index})
            policy_step.verify_policy_record(record)
            built, error = True, ""
        except Exception as exc:
            record, built = {"source": source}, False
            error = "%s: %s" % (type(exc).__name__, exc)
        lineages.append(Lineage(
            name=name, representation_kind=PYTHON_STEP, record=record,
            built_ok=built, build_error=error, policy_source=source))
    return lineages


def build_ast_lineages() -> list:
    """The typed-AST cell: a projection over the frozen authored executor.

    Four records, each loaded by the frozen loader before it is returned,
    so a document that no longer parses is refused at construction rather
    than at the first step of an episode.

    The origin is a stand-in and is written on every record. This cell
    delegates to `boolean_ast_policy`'s frozen loader, type system, node
    set, interpreter and bounded child, and adds a view projection; no
    provider produced any of it, so claiming `model-acquired` would be
    C15 in a new place — a label no receipt supports.

    What the cell still cannot do is recorded on the lineage rather than
    inferred from a zero: the node set publishes no view field for the
    program under repair and builds no replacement source text, so this
    arm cannot repair. The witness is the loader's own refusal.
    """
    from . import s09_swe_ast as swe_ast

    lineages = []
    for index in range(LINEAGES_PER_CELL):
        name = "%s-L%d" % (TYPED_AST, index)
        try:
            record = swe_ast.lineage_record(name, index=index)
            built, error = True, swe_ast.missing_cells()["typed-ast"]["witness"]
        except Exception as exc:
            record, built = {"policy_id": name}, False
            error = "%s: %s" % (type(exc).__name__, exc)
        lineages.append(Lineage(
            name=name, representation_kind=TYPED_AST, record=record,
            built_ok=built, build_error=error))
    return lineages


def _ast_record(policy_id: str, document: dict) -> dict:
    return {
        "artifact": {
            "kind": "learning-policy",
            "representation": "typed-ast",
            "version": boolean_ast_policy._REPRESENTATION,
            "policy_id": policy_id,
            "ast_digest": hashlib.sha256(
                boolean_ast_policy._canonical(document)).hexdigest(),
        },
        "policy_ast": document,
    }


def _edit_expr() -> dict:
    return {"op": "obj", "fields": {
        "line": {"op": "const", "value": 1},
        "op": {"op": "const", "value": "replace"},
        "text": {"op": "const", "value": "    total = 0"}}}


def _ast_repair_document(policy_id: str) -> dict:
    """A repair in the frozen grammar, with no world name in it.

    `inputs` has to be an object node and `evidence_refs` and
    `requested_resources` have to be raw JSON rather than nodes; getting
    either wrong produces a refusal that looks like a grammar limit and
    is not one. The payload itself is a nested object holding the edit
    the policy would supply.
    """
    return {
        "policy_id": policy_id,
        "entry": {
            "op": "return_action", "kind": "use", "target": "code.repair",
            "inputs": {"op": "obj", "fields": {
                "edits": {"op": "list", "items": [_edit_expr()]}}},
            "evidence_refs": [],
            "requested_resources": {},
            "state": {"op": "const", "value": {}},
        },
    }


def _ast_probe_view() -> dict:
    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    return world.SweSession(record).policy_view()


def _repair_probe_action() -> dict:
    return {"kind": "use", "target": "code.repair",
            "inputs": {"edits": [{"line": 1, "op": "replace",
                                  "text": "    pass"}]},
            "evidence_refs": [], "requested_resources": {}}


def build_graph_lineages() -> list:
    """The action-graph cell: four real records over the SWE `World`.

    `ordering_graph_policy.World` was always a value rather than a
    subclass, which is what makes a second world a binding and not a
    re-shape. `s09_swe_binding` supplies that value, so the record below
    is admitted by the real `load_policy` and its guard is decided by the
    real `_evaluate_guard` on 30 of 30 held-out instances.

    The lineage records what the cell still cannot do, because the missing
    part is not the binding: `_parse_action` deep-copies the raw action
    node, so a guard value the evaluator just read never reaches an action
    input. A graph arm localizes a test only by naming it in the record.
    """
    from . import s09_swe_ast as swe_ast
    from . import s09_swe_binding as swe_binding

    missing = swe_ast.missing_cells()["action-graph"]["witness"]
    lineages = []
    for index in range(LINEAGES_PER_CELL):
        name = "%s-L%d" % (ACTION_GRAPH, index)
        record = swe_binding.swe_graph_record(name)
        try:
            ordering_graph_policy.load_policy(record,
                                              world=swe_binding.SWE_WORLD)
            built, error = True, missing
        except Exception as exc:
            record, built = {"policy_id": name}, False
            error = "%s: %s" % (type(exc).__name__, exc)
        lineages.append(Lineage(
            name=name, representation_kind=ACTION_GRAPH,
            record=record | {"unfillable_cell": missing},
            built_ok=built, build_error=error))
    return lineages


def _risk_key(lines, number):
    """The STEP source's `risk_key`, restated at module scope.

    The child interpreter forbids imports, so the ranking exists twice.
    This copy is the one the driver measures with, and
    `test_the_module_level_risk_key_agrees_with_the_step_source` fails
    if the two ever disagree, because a driver that reports a ranking
    the policy does not use is reporting something else.
    """
    text = lines[number - 1] if number <= len(lines) else ""
    body = text.strip()
    is_init = body.endswith("= 0") and body[:-3].replace("_", "a").isalnum()
    return (1 if is_init else 0, -len(text), number)


LINEAGES = tuple(build_step_lineages() + build_ast_lineages()
                 + build_graph_lineages())


def supported_lineages(kind: str = PYTHON_STEP) -> tuple:
    return tuple(lineage for lineage in LINEAGES
                 if lineage.representation_kind == kind
                 and lineage.built_ok)


def _step_refusal(exc: Exception) -> dict:
    """A step that could not run, named rather than dropped.

    The STEP cell used to answer any exception with a bare `world.stop_action()`.
    That action is indistinguishable from the policy deciding it was done, so a
    host that cannot spawn the bounded child, a staged-source digest mismatch
    and a policy that genuinely gave up all produced one `unrepaired` row with
    a one-turn trace. The E1 matrix reports repair rates, and an executor that
    never ran is not a policy that failed to repair: the first number has to
    carry the second or the study measures the host.

    The three arms in this file each already record a refusal this way, in the
    shared `bridge_refusal` shape `boolean_policy._refusal` defines and
    `s09_swe_ast._refusal` restates for this world. The STEP arm was the one
    cell that did not, so it is brought onto the same shape rather than left as
    a fourth convention. A refusal is still a `stop`: the episode ends, and the
    reason rides in the action's inputs where `run_episode`'s trace keeps it.
    """
    return {
        "kind": policy_action.STOP,
        "target": world.ACTION_TARGETS[policy_action.STOP],
        "inputs": {"bridge_refusal": {
            "stage": "swe-step-policy-step",
            "reason": (str(exc) or type(exc).__name__)[:500],
        }},
        "evidence_refs": [],
        "requested_resources": {},
    }


def lineage_driver(lineage: Lineage) -> Callable:
    """A fresh driver for one episode, in that lineage's own executor.

    Each episode gets its own closure, so no lineage inherits a previous
    episode's search state. Replaying one retained policy across the
    panel is the named way to fake replication, and this is what stops
    it.

    The executor is chosen by the cell rather than assumed, because the
    three cells do not share one: the STEP cell runs the bounded child,
    the typed AST runs the frozen AST interpreter in the bounded child,
    and the graph runs the graph executor's own cursor. A single driver
    would silently run all three through the STEP child and the matrix
    would compare three names over one policy.
    """
    if lineage.representation_kind == TYPED_AST:
        return swe_ast_driver(lineage)
    if lineage.representation_kind == ACTION_GRAPH:
        return swe_graph_driver(lineage)

    state: dict = {}
    record = lineage.record

    def choose(view: dict) -> dict:
        _absorb_bridge(state, view.get("last_effect"))
        try:
            result = boolean_policy._run_shared_policy_step(
                record, view, state,
                timeout_ms=policy_step.STEP_TIMEOUT_MS,
                cpu_seconds=policy_step.STEP_CPU_SECONDS,
                max_output_bytes=policy_step.STEP_MAX_OUTPUT_BYTES,
                memory_bytes=None)
            action, next_state = policy_action.parse_step_result(result)
        except Exception as exc:
            return _step_refusal(exc)
        policy_step.validate_state(next_state)
        return action.as_dict()

    return choose


def swe_ast_driver(lineage: Lineage) -> Callable:
    """One typed-AST episode callback, fresh per episode.

    The study holds the origin beside the loader's artifact, so the
    driver unwraps the record the frozen loader is willing to read.
    """
    from . import s09_swe_ast as swe_ast
    return swe_ast.choose_action(lineage.record["ast_record"])


def swe_graph_driver(lineage: Lineage) -> Callable:
    """One action-graph episode callback, fresh per episode.

    The graph executor keeps its own cursor across turns and exposes it as
    `s09_cursor`, which is how an out-of-process step resumes mid-episode.
    In process the closure carries it, and a fresh driver per episode is
    what keeps one instance's position out of the next.
    """
    from . import s09_swe_binding as swe_binding
    policy = {key: value for key, value in lineage.record.items()
              if key != "unfillable_cell"}
    return ordering_graph_policy.choose_action(policy,
                                              world=swe_binding.SWE_WORLD)


def search_driver(lineage: Lineage) -> Callable:
    """The in-process reference search, as a driver for one episode.

    The same `s09_swe_policy` the instrument ships, run in this process
    rather than in the bounded child. It scores identically because the
    world scores the final program either way; what it does not exercise
    is the child's compute bound. Tests that assert on *scoring* use
    this and the experiment run uses `lineage_driver`, so the bound is
    tested once rather than once per assertion.
    """
    state: dict = {}

    def choose(view: dict) -> dict:
        search.absorb(state, view.get("last_effect"))
        return search.driven(state, view)

    return choose


def run_episode(driver: Callable, split: str, seed: int) -> dict:
    return world.run_episode(driver, split=split, seed=seed)


def _outcome(final: dict) -> str:
    outcome = final.get("outcome")
    return outcome if outcome in OUTCOMES else "refused"


def in_process_driver_factory(lineage: Lineage) -> Callable:
    """A driver factory for scoring assertions that avoids the child.

    The scoring path is identical; only the compute bound differs, and
    the bound is pinned separately by the lineage's own build and by the
    experiment run itself.
    """
    return search_driver(lineage)


def run_matrix(*, splits=("dev", "held_out"),
               lineages=None,
               driver_factory: Callable | None = None
               ) -> MatrixResult:
    """Run every lineage over every instance of every split.

    An exception from a driver is a row with `outcome="refused"` and the
    refusal text, never a dropped episode: a lineage that vanishes is
    indistinguishable from one that was never run.
    """
    lineages = tuple(lineages) if lineages is not None else LINEAGES
    result = MatrixResult()
    for split in splits:
        catalogue = tasks.enumerate_instances(split)
        for lineage in lineages:
            result.lineages_run += 1
            if not lineage.built_ok:
                result.missing_cells.append({
                    "lineage": lineage.name,
                    "representation_kind": lineage.representation_kind,
                    "reason": lineage.build_error,
                })
            for seed, record in enumerate(catalogue):
                if not lineage.built_ok:
                    result.rows.append(SweRow(
                        representation_kind=lineage.representation_kind,
                        lineage=lineage.name, lineage_digest=lineage.digest,
                        task_id=record["task_id"], split=split,
                        structure=record["structure"],
                        fault_mechanism=record["mechanism"],
                        outcome="refused", public_passed=0,
                        public_total=len(record["public_tests"]),
                        protected="unknown", turns=0,
                        refused=lineage.build_error))
                    continue
                build = driver_factory or lineage_driver
                try:
                    driver = build(lineage)
                    episode = run_episode(driver, split, seed)
                    result.rows.append(_row(lineage, record, split, episode))
                except Exception as exc:
                    result.rows.append(SweRow(
                        representation_kind=lineage.representation_kind,
                        lineage=lineage.name, lineage_digest=lineage.digest,
                        task_id=record["task_id"], split=split,
                        structure=record["structure"],
                        fault_mechanism=record["mechanism"],
                        outcome="refused", public_passed=0,
                        public_total=len(record["public_tests"]),
                        protected="unknown", turns=0,
                        refused="%s: %s" % (type(exc).__name__, exc)))
    return result


def _row(lineage: Lineage, record: dict, split: str,
         episode: dict) -> SweRow:
    final = episode["final"]
    emitted = []
    refused = ""
    for turn in episode["trace"]:
        action = turn.get("action")
        if not isinstance(action, dict):
            continue
        emitted.append({"kind": action.get("kind"),
                        "target": action.get("target")})
        # A cell that could not run says so on its own row. The executor's
        # refusal rides in the stop action's inputs, so it is read back off
        # the trace here rather than recomputed. Without this the row is an
        # `unrepaired` attempt and the payload reports a repair rate measured
        # over episodes the host never ran.
        bridge = action.get("inputs", {}).get("bridge_refusal")
        if isinstance(bridge, dict) and not refused:
            refused = "%s: %s" % (bridge.get("stage", ""),
                                  bridge.get("reason", ""))
    return SweRow(
        representation_kind=lineage.representation_kind,
        lineage=lineage.name, lineage_digest=lineage.digest,
        task_id=record["task_id"], split=split,
        structure=record["structure"], fault_mechanism=record["mechanism"],
        outcome=_outcome(final),
        public_passed=final.get("public_passed", 0),
        public_total=final.get("public_total", len(record["public_tests"])),
        protected=final.get("protected", {}).get("outcome", "unknown"),
        turns=episode["turns"], refused=refused,
        actions_emitted=tuple(emitted))


def per_family_table(result: MatrixResult) -> dict:
    """One row per (structure, fault mechanism), with no family dropped.

    A family that never repairs keeps its zero, because a table that
    omitted a failed domain would read as a smaller panel rather than a
    failure.
    """
    tally: dict = {}
    for row in result.rows:
        if row.outcome == "refused":
            continue
        key = (row.structure, row.fault_mechanism)
        entry = tally.get(key)
        if entry is None:
            entry = tally[key] = {"instances": 0, "repaired": 0,
                                  "representations": set()}
        entry["instances"] += 1
        entry["repaired"] += int(row.outcome == "repaired")
        entry["representations"].add(row.representation_kind)
    return {key: FamilyTable(
        structure=key[0], fault_mechanism=key[1], instances=value["instances"],
        repaired=value["repaired"],
        representations=tuple(sorted(value["representations"])))
        for key, value in sorted(tally.items())}


def paired_comparisons(result: MatrixResult) -> list:
    """Pair the same instance across representations, never across tasks."""
    by_task: dict = {}
    for row in result.rows:
        by_task.setdefault(row.task_id, []).append(row)
    pairs = []
    for task_id in sorted(by_task):
        rows = by_task[task_id]
        for index, left in enumerate(rows):
            for right in rows[index + 1:]:
                if left.representation_kind != right.representation_kind:
                    pairs.append(PairedComparison(left, right))
    return pairs


def lineage_ledger(result: MatrixResult) -> list:
    """Every lineage that was run, with what it did, including nothing.

    Keyed on (name, digest) rather than on name. Two cells can each
    carry a lineage called `L0`, and keying on the name alone would sum
    a STEP arm's repairs into the AST arm's row, which is the one way a
    ledger like this can quietly overstate a result.

    A refusal is counted from the row's own recorded refusal text, not
    from its outcome. The two differ, and the difference is the whole
    point of recording it: a lineage whose executor refused is scored by
    the world as `unrepaired`, because the world scored a program nobody
    proposed, so an outcome-keyed count would report a host that never
    ran a child as a lineage that ran every episode and repaired nothing.
    """
    order = {(lineage.name, lineage.digest): lineage for lineage in LINEAGES}
    tally: dict = {}
    for row in result.rows:
        key = (row.lineage, row.lineage_digest)
        entry = tally.get(key)
        if entry is None:
            built = order.get(key)
            entry = tally[key] = {
                "kind": row.representation_kind,
                "episodes": 0, "repairs": 0, "refusals": 0,
                "build_error": built.build_error if built else "",
            }
        entry["episodes"] += 1
        entry["repairs"] += int(row.outcome == "repaired")
        entry["refusals"] += int(bool(row.refused) or row.outcome == "refused")
    return [LineageLedgerEntry(
        name=key[0], representation_kind=entry["kind"], digest=key[1],
        episodes=entry["episodes"], repairs=entry["repairs"],
        refusals=entry["refusals"], build_error=entry["build_error"])
        for key, entry in sorted(tally.items())]


def probe_reach(split: str = "held_out", lineage: Lineage | None = None
                ) -> dict:
    """How often the probe budget even reaches the injected fault line.

    This is a diagnostic, not a score. The `code.try` budget is 60 and
    the candidate set on a well-ranked wrong line is larger than that,
    so a search that walks suspects in rank order can spend its whole
    budget above the fault. Whether that is what happens is a property
    of the panel and the budget, and it decides how to read every
    repair rate below: an arm that repairs 6 of 30 is not a weak solver,
    it is a solver that was pointed away from the answer.

    The true line is the assessor's `patch` line. It is used here and
    only here, to describe the panel, never by a policy.
    """
    lineage = lineage or supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    by_mechanism: dict = {}
    reached = 0
    total = 0
    for record in tasks.enumerate_instances(split):
        session = world.SweSession(record)
        for case in record["public_tests"]:
            session.run_public_test(case["name"])
        session.localize(record["public_tests"][0]["name"])
        view = session.policy_view()
        pool = namespace["pool_of"](view)
        lines = namespace["lines_of"](view)
        budget = world.BUDGET_LIMITS["probe"]
        true_line = record["patch"][0]["line"]
        hit = False
        for number in namespace["suspects"](view):
            for candidate in namespace["rewrites"](lines[number - 1], pool):
                if budget <= 0:
                    break
                budget -= 1
                if number == true_line:
                    hit = True
            if budget <= 0:
                break
        total += 1
        reached += int(hit)
        entry = by_mechanism.setdefault(record["mechanism"], [0, 0])
        entry[0] += int(hit)
        entry[1] += 1
    return {
        "split": split,
        "instances": total,
        "fault_line_reached": reached,
        "rate": round(reached / total, 4) if total else 0.0,
        "probe_budget": world.BUDGET_LIMITS["probe"],
        "by_mechanism": {name: {"reached": hit, "instances": count}
                         for name, (hit, count) in sorted(by_mechanism.items())},
    }


def search_span(split: str = "held_out", lineage: Lineage | None = None
                ) -> dict:
    """What the search can and cannot reach, per instance and per mechanism.

    Two ceilings, measured separately so neither is read as the other.
    One is the budget: how many `code.try` dry-runs it costs, walking
    suspects in the order the arm walks them, to reach the injected
    fault line. The other is the generator: whether the candidate set
    the arm actually produces contains the reference repair at all. A
    family the budget cannot reach is a truncation; a family the
    generator cannot express is unreachable for a reason no budget
    fixes, and calling the second a budget problem would be wrong.

    Both ceilings are properties of the panel and the instrument, so
    this is a diagnostic and not a score. The reach diagnostic
    (`probe_reach`) asks the budget question alone; this one carries the
    generator question beside it, and where a family fails only the
    generator is named as the blocker.

    The walk is row-major per suspect line, because that is the order
    the STEP source spends candidates in. The in-process reference
    search walks column-major across lanes and the probe budget is
    derived against that order, so the two orders are not
    interchangeable and a cost from one is not a cost from the other.
    This report describes the child lineage it is given.
    """
    lineage = lineage or supported_lineages()[0]
    namespace: dict = {}
    exec(compile(lineage.policy_source, "<lineage>", "exec"), namespace)
    per_instance: dict = {}
    by_mechanism: dict = {}
    for record in tasks.enumerate_instances(split):
        session = world.SweSession(record)
        for case in record["public_tests"]:
            session.run_public_test(case["name"])
        session.localize(record["public_tests"][0]["name"])
        view = session.policy_view()
        pool = namespace["pool_of"](view)
        lines = namespace["lines_of"](view)
        budget = world.BUDGET_LIMITS["probe"]
        true_line = record["patch"][0]["line"]
        reference = record["patch"][0]["text"].rstrip("\n")
        cost_to_line: int | None = None
        generated = False
        for number in namespace["suspects"](view):
            for candidate in namespace["rewrites"](lines[number - 1], pool):
                if budget <= 0:
                    break
                budget -= 1
                if number == true_line:
                    if cost_to_line is None:
                        cost_to_line = world.BUDGET_LIMITS["probe"] - budget
                    if candidate == reference:
                        generated = True
            if budget <= 0:
                break
        reachable = cost_to_line is not None
        repairable = reachable and generated
        per_instance[record["task_id"]] = {
            "template": record["template"],
            "mechanism": record["mechanism"],
            "probe_cost_to_fault_line": cost_to_line,
            "reference_generated": generated,
            "fault_line_reached": reachable,
            "repairable_in_budget": repairable,
        }
        entry = by_mechanism.setdefault(record["mechanism"], {
            "instances": 0, "fault_line_reached": 0,
            "reference_generated": 0, "instances_reachable": 0,
        })
        entry["instances"] += 1
        entry["fault_line_reached"] += int(reachable)
        entry["reference_generated"] += int(generated)
        entry["instances_reachable"] += int(repairable)
    instances = len(per_instance)
    costs = [item["probe_cost_to_fault_line"] for item in per_instance.values()
             if item["probe_cost_to_fault_line"] is not None]
    worst = max(costs) if costs else 0
    reached = sum(1 for item in per_instance.values()
                  if item["fault_line_reached"])
    return {
        "split": split,
        "instances": instances,
        "probe_budget": world.BUDGET_LIMITS["probe"],
        "derived_budget": world.worst_case_probe_cost() + 1,
        "worst_case_probe_cost": worst,
        "instances_reaching_fault_line": reached,
        "instances_generator_can_reach": sum(
            1 for item in per_instance.values() if item["reference_generated"]),
        "instances_repairable_in_budget": sum(
            1 for item in per_instance.values() if item["repairable_in_budget"]),
        "by_mechanism": {name: by_mechanism[name]
                         for name in sorted(by_mechanism)},
        "per_instance": per_instance,
        "ceiling": {
            "budget_blocked": sorted(
                task_id for task_id, item in per_instance.items()
                if not item["fault_line_reached"]),
            "generator_blocked": sorted(
                task_id for task_id, item in per_instance.items()
                if item["fault_line_reached"] and not item["reference_generated"]),
        },
    }


def support() -> dict:
    """The finite panel, counted rather than asserted."""
    held = tasks.enumerate_instances("held_out")
    dev = tasks.enumerate_instances("dev")
    return {
        "held_out_instances": len(held),
        "dev_instances": len(dev),
        "structures": len(tasks.STRUCTURES),
        "mechanisms": len(tasks.MECHANISMS),
        "held_out_mechanisms": len(tasks.HELD_OUT_MECHANISMS),
        "dev_mechanisms": len(tasks.DEV_MECHANISMS),
        "held_out_templates": len(tasks.HELD_OUT_TEMPLATES),
        "dev_templates": len(tasks.DEV_TEMPLATES),
        "held_out_families": len({(r["structure"], r["mechanism"])
                                  for r in held}),
        "distinct_faulty_programs": len(
            {tasks.render_source(r["source"]) for r in held}),
        "lineages_per_cell": LINEAGES_PER_CELL,
        "supported_representations": [PYTHON_STEP, TYPED_AST, ACTION_GRAPH],
        "missing_representations": [],
        "comparable_through_compare_arms": False,
        "why_not_comparable": (
            "all three lineages build and each cell is bound to its own "
            "real executor, but compare_arms does not reach a comparable "
            "result on this world: the step driver factory takes no step "
            "budget argument, and the typed AST emits a boolean stop target "
            "the swe world refuses. The graph cell's observation view is "
            "closed. The earlier diagnosis blamed the contract view for "
            "carrying no symptom key, and that was wrong: the contract "
            "already published the guarded observations as observed, and "
            "the swe binding's projection read symptom instead and wrote "
            "its empty default over them, so the guard on observed.0.kind "
            "resolved {}['0'] and raised. That projection now re-indexes "
            "the list it is handed, and the guard is decided. What still "
            "holds the graph cell is the budget's shape, one layer below. "
            "contract_view publishes remaining as the scalar the contract "
            "requires by a declared read of ('remaining', 'test'), while "
            "the swe world publishes a per-dimension mapping and its own "
            "admits calls .get on it, so the turn the guard now reaches is "
            "refused with 'int' object has no attribute 'get'. The map is "
            "not recoverable from what the contract carries, because "
            "action_schema.budget holds the ceiling and the live count is "
            "already spent, and republishing a mapping under remaining "
            "would be widening the contract rather than reading one. Named "
            "with its refusals in tests/test_inv_b9_graph_driver.py, "
            "tests/test_inv_b1_swe_view.py and "
            "tests/test_inv_b18_view_contract.py"),
        "repair_rate_note": (
            "the three cells still repair nothing as built; that zero is "
            "about the records and the harness, not about the world, which "
            "admits use/code.repair"),
    }


def path_fork() -> dict:
    """Where this run's path sits relative to the common one.

    The common harness used to refuse a SWE arm outright: `contract_view`
    demanded exactly eight public-state fields and the SWE world publishes
    twelve, so every E1 number here was produced by the world's own driver
    and none of them was comparable with the boolean or ordering worlds.

    The contract is now declared per world, so the fork is closed and the
    field list below is a record of what was reconciled rather than a live
    blocker. What is still not comparable is a separate and narrower
    thing, and it is not this: the two representations' SWE cells are
    missing for an executor reason. `s09_swe_ast.expressivity` and
    `s09_swe_binding` record it, and no projection of this view changes it.

    The three disputed fields, and the one answer each got:

    * `observed` is `symptom.observed`, the record the world already
      publishes. The two worlds were describing one thing.
    * `max_queries` and `remaining` are the `test` budget. The contract
      requires `0 <= remaining <= max_queries` and the schema to agree,
      and the SWE world has one dimension an observation spends, so the
      scalar is that budget. The two other projections answered with the
      probe budget and with the sum of all five, and neither pair is
      consistent.
    * `hypothesis_class` is `{"structure", "editable_lines"}`, both read
      from fields the world already publishes. The fork probe's earlier
      answer listed the fault mechanisms, which is the injected answer
      and the leak the contamination tests forbid.
    """
    from . import s09_arm_parity as parity

    record = tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                            tasks.HELD_OUT_MECHANISMS[0])
    view = world.SweSession(record).policy_view()
    issue = parity.admit_world_view(view, arm_name="swe-probe")
    declared = sorted(parity.VIEW_CONTRACT_FIELDS["software-fault-repair-v1"])
    contract = parity.contract_view(view)
    return {
        "run_path": "world driver (experiments.ad01.s09_swe_world.run_episode)",
        "common_path": "s09_arm_parity.compare_arms via contract_view",
        "common_path_usable": issue is None,
        "refusal": None if issue is None else str(issue.reason),
        "fields_required_by_harness": declared,
        "fields_published_by_swe": sorted(view),
        "missing_from_swe": sorted(set(declared) - set(view)),
        "extra_in_swe": sorted(set(view) - set(declared)),
        "contract_max_queries": contract["public_world"]["max_queries"],
        "contract_remaining": contract["remaining"],
        "contract_hypothesis_class":
            contract["public_world"]["hypothesis_class"],
        "scope_of_result": (
            "the SWE world is admitted by the common harness and its view "
            "is normalised to the six contract fields; the numbers are NOT "
            "comparable with the boolean or ordering worlds, which ran "
            "against different tasks, and the two representations' SWE "
            "cells remain missing for an executor reason recorded in "
            "s09_swe_ast.expressivity"),
        "fork": {
            "resolved": "the view contract is declared per world in "
                        "s09_arm_parity, exactly rather than as a superset",
            "still_refused": (
                "a union of two vocabularies, an undeclared world, and a "
                "view whose instrument and schema format disagree"),
        },
    }


def _lineage_index(rows: list) -> dict:
    """One entry per distinct lineage, keyed by a short id.

    The name, the digest and the representation repeat on every row,
    and the digest is what says a lineage is independent, so the three
    travel together once here rather than 468 times in the rows.
    """
    index: dict = {}
    order: list = []
    for row in rows:
        key = (row.lineage, row.lineage_digest, row.representation_kind)
        if key not in index:
            index[key] = "L%02d" % len(order)
            order.append(key)
    return {"ids": index,
            "entries": [{"id": index[key], "name": key[0], "digest": key[1],
                         "representation_kind": key[2]} for key in order]}


def _intern(value) -> str:
    """A short stable name for a value, so equal values share an entry."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str)
        .encode()).hexdigest()[:16]


def _trace_runs(actions) -> list:
    """Compress a trace to runs of `[kind, target, repeat]`.

    A trace is ~300 actions drawn from a handful of kinds, and the long
    stretches of one action are why the expanded table was still
    360 KB. The runs expand back to the original list exactly; that is
    checked against a real run, not against this function.
    """
    runs: list = []
    for action in actions:
        pair = [action.get("kind"), action.get("target")]
        if runs and runs[-1][0] == pair[0] and runs[-1][1] == pair[1]:
            runs[-1][2] += 1
        else:
            runs.append([pair[0], pair[1], 1])
    return runs


def _trace_table(rows: list) -> dict:
    """One entry per distinct non-empty trace, keyed by its fingerprint.

    The empty trace is not interned: a row that ran nothing says so with
    a null reference, so the table holds only sequences a lineage
    actually emitted. On the measured panel that is 16 entries for the
    156 traced rows, against 468 inline copies.
    """
    table: dict = {}
    for row in rows:
        if not row.actions_emitted:
            continue
        table.setdefault(_intern(list(row.actions_emitted)),
                         _trace_runs(row.actions_emitted))
    return table


def _refusal_table(rows: list) -> dict:
    """One entry per distinct refusal, keyed by its fingerprint.

    An unsupported representation carries the same refusal on every
    instance, so 312 rows hold two strings.
    """
    table: dict = {}
    for row in rows:
        if row.refused:
            table.setdefault(_intern(row.refused), row.refused)
    return table


def _row_for_payload(row: SweRow, lineage_ids: dict) -> dict:
    """The row as written, with everything that repeats referenced.

    Three fields are per-lineage rather than per-row and a fourth is
    per-panel: the trace, the refusal, and the lineage's name, digest
    and representation. Naming them here is what keeps the file a
    function of the panel and not of how long a solver walked.
    """
    written = row.as_dict()
    written["lineage_id"] = lineage_ids[
        (row.lineage, row.lineage_digest, row.representation_kind)]
    written["trace_sequence"] = (
        _intern(list(row.actions_emitted)) if row.actions_emitted else None)
    written["refusal"] = _intern(row.refused) if row.refused else None
    for repeated in ("actions_emitted", "refused", "lineage",
                     "lineage_digest", "representation_kind"):
        del written[repeated]
    return written


def _paired_block(pairs: list) -> dict:
    """Agreement per instance, grouped so the group is named once.

    `structure` and `fault_mechanism` are properties of the instance, so
    naming them on all 1872 pairs restated them 1872 times. Each pair
    carries both sides' lineages and outcomes, because `agree` is a
    claim about two rows and a bare boolean would assert a comparison
    nobody could check.
    """
    grouped: dict = {}
    for pair in pairs:
        entry = grouped.setdefault(
            pair.left.task_id,
            {"structure": pair.left.structure,
             "fault_mechanism": pair.left.fault_mechanism, "pairs": []})
        entry["pairs"].append([pair.left.lineage, pair.right.lineage,
                               pair.left.outcome, pair.right.outcome,
                               pair.as_dict()["agree"]])
    return grouped


def _paired_agree(pairs: list) -> dict:
    """The agreement rate and the breakdown that explains it.

    One number here is a statement about the whole panel, so it travels
    with the per-representation-pair counts it is made of.
    """
    tally: dict = {}
    for pair in pairs:
        key = "%s/%s" % (pair.left.representation_kind,
                         pair.right.representation_kind)
        entry = tally.setdefault(key, {"pairs": 0, "agree": 0})
        entry["pairs"] += 1
        entry["agree"] += int(pair.as_dict()["agree"])
    for entry in tally.values():
        entry["rate"] = entry["agree"] / entry["pairs"] if entry["pairs"] \
            else 0.0
    total = sum(entry["pairs"] for entry in tally.values())
    agree = sum(entry["agree"] for entry in tally.values())
    return {"pairs": total, "agree": agree,
            "rate": agree / total if total else 0.0,
            "by_representation_pair": tally}


def result_payload(result: MatrixResult) -> dict:
    table = per_family_table(result)
    pairs = paired_comparisons(result)
    lineage_index = _lineage_index(result.rows)
    return {
        "instrument": world.INSTRUMENT_ID,
        "world_module": "experiments.ad01.s09_swe_world",
        "template_version": tasks.TEMPLATE_VERSION,
        "representations": list(REPRESENTATIONS),
        "support": support(),
        "lineages": [entry.as_dict() for entry in lineage_ledger(result)],
        "lineage_index": lineage_index["entries"],
        "missing_cells": list(result.missing_cells),
        "per_family": {("%s/%s" % key): value.as_dict()
                       for key, value in table.items()},
        "paired": _paired_block(pairs),
        "paired_agree": _paired_agree(pairs),
        "rows": [_row_for_payload(row, lineage_index["ids"])
                 for row in result.rows],
        "trace_sequences": _trace_table(result.rows),
        "trace_sequence_fields": ["kind", "target", "repeat"],
        "refusals": _refusal_table(result.rows),
        "path_fork": path_fork(),
        "probe_budget_reach": {
            split: probe_reach(split) for split in ("dev", "held_out")},
        "search_span": {
            split: search_span(split) for split in ("dev", "held_out")},
        "derived_bounds": {
            "probe_budget": world.BUDGET_LIMITS["probe"],
            "probe_budget_worst_case": world.worst_case_probe_cost(),
            "suspect_cap": world.SUSPECT_CAP,
            "suspect_cap_worst_rank": world.worst_case_suspect_rank(),
            "max_turns": world.MAX_TURNS,
        },
        "notes": list(result.notes),
    }


def write_evidence(result: MatrixResult, out_dir: str) -> dict:
    """Write the machine-readable evidence and return what was written."""
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "matrix.json")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(result_payload(result), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return {"json": json_path, "dir": out_dir}


def main(argv=None) -> int:
    """Run the full matrix and write the evidence.

    Every lineage in `LINEAGES` runs over both splits, so the two
    refused cells appear as rows rather than as an absence. The
    denominator a reviewer should check is `len(result.rows)`, which is
    `splits x instances x lineages` and nothing smaller.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(
        "reports", "evidence", "inv_r1_e1_swe"))
    parser.add_argument("--splits", default="dev,held_out")
    parser.add_argument("--limit-lineages", type=int, default=None)
    args = parser.parse_args(argv)

    lineages = LINEAGES if args.limit_lineages is None \
        else LINEAGES[:args.limit_lineages]
    splits = tuple(part for part in args.splits.split(",") if part)
    result = run_matrix(splits=splits, lineages=lineages)
    written = write_evidence(result, args.out)
    print("rows: %d" % len(result.rows))
    print("lineages run: %d" % result.lineages_run)
    print("missing cells: %d" % len(result.missing_cells))
    for entry in lineage_ledger(result):
        print("  %-18s %-13s episodes %3d repairs %3d refusals %3d"
              % (entry.name, entry.representation_kind, entry.episodes,
                 entry.repairs, entry.refusals))
    print("written: %s" % written["json"])
    fork = path_fork()
    print("run path: %s" % fork["run_path"])
    print("common path usable: %s (%s)"
          % (fork["common_path_usable"], fork["refusal"]))
    print("scope: %s" % fork["scope_of_result"])
    return 0


if __name__ == "__main__":  # pragma: no cover - the run is the entry point
    raise SystemExit(main())
