# X2 — the declared freeze now reaches a frozen field by subscript

Lane C2 made `FROZEN_FIELDS` the enforced freeze. The check was an AST walk
over assignment targets, and it enumerated the statement types it knew about
rather than asking the parse which positions bind. Two holes followed from
that shape, and the second is the one the brief named.

## What was wrong

`_targets_frozen` recursed into `Subscript.value` and never read
`Subscript.slice`. So `view.grant = ...` was refused and
`view["grant"] = ...` was admitted as eligible. The gap was invisible
because every fixture in the repository writes a bare name, `grant = ...`,
which the `Name` branch catches.

Reproduced before the fix, on the untouched tip:

```
view["grant"] = 1        -> False
view["used"] += 1        -> False
del view["sealed_results"] -> False
view["grant"]: dict = {} -> False
grant: dict = {}         -> False
if (grant := {}): pass   -> False
for grant in (...): pass -> False
del grant                -> False
```

## The repair, and why it is not seven more branches

Listing the seven missing statements would have closed today's holes and
left the same shape behind: a hand-kept list treated as the language. The
fix asks the parse instead. CPython marks every `Name`, `Attribute` and
`Subscript` it stores into or deletes with an `ast.Store` or `ast.Del`
context, so one rule covers `Assign`, `AugAssign`, `AnnAssign`, `Delete`,
the walrus, the `for` and `with` targets, the comprehension targets,
chained targets and starred targets — and covers a statement added to the
language later without this file being touched.

The `Subscript` branch now reads the key as well as the value. Three
residuals remain, and each is stated rather than papered over:

- `except ... as grant` binds a name the parser records as a bare string
  with no context, so it is one explicit branch.
- `setattr`/`delattr`/`exec`/`eval`/`open` and the four `__setitem__`
  style protocol methods write with no syntactic target at all. Builtins
  and protocol methods are kept in separate sets so `view.eval(...)` is
  not refused for sharing a word with the builtin.
- A computed key is not resolved. Resolving it means tracking what every
  name in the program binds to, which is a taint analysis. The
  before-and-after comparison of `frozen_state` in
  `admit_revision_under_freeze` is the layer that catches a computed-key
  write, and this is noted in the docstring so the gap is not silent.

One form was checked and is unreachable: a walrus cannot target a
subscript or an attribute. `ast.parse` rejects both. The test file asserts
that rejection rather than leaving it to a reader's imagination, because a
guard case for an impossible form is a guard testing its own imagination.

## Detected now, and not before

`Assign`, `AugAssign`, `AnnAssign`, `Delete`, the walrus, `for`, `with`
(`__enter__`), comprehensions, `except ... as`, chained and starred
targets, in each of the three spellings: bare name, attribute, subscript
key. Plus `setattr`, `delattr`, `exec`, `eval`, `open`,
`__setattr__`, `__delattr__`, `__setitem__`, `__delitem__`.

## Not detected, by decision

A computed subscript key. Stated above. A read is still a read:
`remaining = view["grant"]` and `x = view["used"]["queries"]` are not
flagged, and a write to a key that is not frozen is not flagged.

## The other direction

The authorised revision stays eligible. `_revision_source` with the
construction-procedure input, all four authored controls, and a
constructed descendant at x=3, 8 and 11 all pass `_attempts_frozen_write`
and classify `ELIGIBLE`. The refusal suite and the eligibility suite cannot
both pass by the guard being broad, which is the point of both being here.

C2's six unauthorised variants still refuse as `changes-an-unauthorised-decision`
with their own decision named. A frozen-write refusal on any of them would
have meant the widened guard had started refusing for the wrong reason, so
each is asserted against the decision it moved rather than against
ineligibility.

## Gates

Fixed tip, `tests/test_inv_x2_subscript_freeze.py` + C2 + C4:

```
91 passed in 119.15s (0:01:59)
```

Per file: `test_inv_c2_freeze.py` 20 passed, `test_inv_c4_inheritable_construction.py`
13 passed, `test_inv_x2_subscript_freeze.py` 58 passed. Neither C2 nor C4
regressed.

A six-file comparison set was run twice, once on `a82baca`'s source and once
on the fixed source, so the pre-existing reds are measured rather than
asserted:

```
baseline a82baca:  3 failed, 92 passed
fixed:            3 failed, 92 passed
```

Identical failures, all three belonging to the two-member menu C4 deleted:

- `test_s09rev_boundary.py::test_a_descendant_only_ever_runs_the_authored_menu`
- `test_s09rev_boundary.py::test_channel_headroom_reports_no_measurable_headroom`
- `test_m2_frontier_inherit.py::test_second_improvement_round_under_inherited_bytes`

Left red, not fixed. That is another lane's decision.

## Note on two fixtures that were wrong, not the source

Two cases failed on the first run against a correct fix. A walrus on a
subscript does not parse, so that case was unreachable rather than missed;
it is now an assertion that the language rejects the form. A chained
`view["grant"] = view["used"] = x` replaced it. Both were mine and both are
recorded here rather than quietly dropped.

## Untouched

`git diff --name-only a82baca -- reports/evidence/` is empty. No existing
test was weakened, skipped or xfailed. No credential appears in the diff.
No live model call, no network.
