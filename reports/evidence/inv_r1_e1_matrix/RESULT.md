# E1: three representations, one decision, five tasks

Expansion question 1: *which representations can the system acquire and
execute, and which fail for language, construction or runtime reasons?*

Before this, all three representations were registered in
`s09_arm_parity` (`python-step`, `typed-ast`, `action-graph`) but had
never been compared against each other. `compare_arms` refuses three arms
of one kind and had only ever been exercised with a real arm against a test
double. The AST and the graph had no record constructor outside their own
test files. So the honest state was: three representations, zero
cross-representation runs.

`s09_representation_matrix` now writes the *same decision* — probe x=3,
then commit a fixed four-member predictor — in all three notations and runs
each under one `ComparisonConditions`. Every arm is a real executor
(`is_test_double=False`); a matrix of doubles would report `incomparable`
on its own terms and could not show agreement.

## The result

Five Boolean-world tasks, one query budget (8) each, all `comparable`:

| task | step | ast | graph |
|---|---|---|---|
| dev/4  | 0.1875 | 0.1875 | 0.1875 |
| qual/3 | 0.0625 | 0.0625 | 0.0625 |
| dev/11 | 0.0625 | 0.0625 | **None** |
| dev/7  | 0.125  | 0.125  | **None** |
| audit/1| 0.0    | 0.0    | 0.0    |

`step` and `ast` agree to the digit on every task. `graph` agrees on three
and returns `None` on two.

## The `None` is a real divergence, not a defect

The action graph encodes "if the row I observed equals the row I expect,
commit it" — its `commit` node's guard reads `observed.0.y.0` and compares
it to a hardcoded first bit. When the task's hidden row at x=3 does not
match that hardcoded bit, the guard is false, the fallback arm is `stop`,
and the graph **stops without ever committing a predictor**. The world
returns no `final` for an arm that stopped without a commit, so the score
is `None`. The step and ast arms have no such guard — they commit their
constant unconditionally after the one probe — so they always produce a
number.

So on a task whose observation does not match the graph's baked-in
expectation, the graph representation loses to the other two. That is a
legitimate representation-level behavioural difference: the graph's
data-dependent guard is strictly more fragile than the other two's
unconditional commit. It is recorded, not worked around.

This is also a concrete instance of the campaign's central hazard: the
graph's first draft committed a *hardcoded* `COMMIT_Y` constant that
happened to equal the observed row on dev/4 and scored 0.1875 — a score
that looks like learning but was authored. `COMMIT_Y` is now explicitly a
fixed guess, and the module's comment says why no representation can
legitimately turn one observation into a whole 16-bit table.

## What had to be fixed to get the AST to run at all

The AST had never run under `compare_arms`. Three separate shape
mismatches, each surfacing as an opaque `illegal-hypothesis`:

1. **View arity.** The parity harness hands every arm a six-field contract
   view. `boolean_ast_policy._shared_view` required the world's own
   eight-field state, so it refused with `public state missing:
   hypothesis_class, max_queries, split`. The graph survived only because
   `boolean_graph_policy.make_view` calls `boolean_policy._shared_view`
   and swallows the exception. Fixed by making the AST's `_shared_view`
   re-nest the three fields from `public_world` when exactly those are
   missing.
2. **Schema rename not idempotent.** The harness renames the world's
   `commit` to the shared `construct` before handing over a view. Both
   `_shared_schema` (AST) and `_shared_action_schema` (boolean_policy)
   then tried to rename `commit` → `construct` *again*, found nothing to
   pop, and refused with `action schema must advertise commit`. Fixed in
   both: if the schema is already in the shared spelling, return it.
3. **Inputs are expressions, not values.** In the AST grammar `inputs` and
   `state` must be expression nodes. Wrapping the whole `{"specs": [...]}`
   dict in a single `const` handed `rules.execute_all` a node where a table
   belongs, which reported `illegal-hypothesis` with nothing pointing at
   the notation. Fixed by lifting the dict into `{"op":"obj"}` field by
   field, passing through values that are already expression nodes.

Each was a real defect that would have made the AST look like a
representation that cannot execute, when the truth is it can. All three
are now regression-tested (`tests/test_s09_representation_matrix.py`, 6
tests) and 84 existing AST/graph/bridge tests still pass.

## What is *not* claimed

- This is five tasks on one world family, with an authored policy in each
  notation. It shows the three representations can express and execute the
  same decision and that step and ast are behaviourally identical here. It
  does not show they are identical in general, and it does not test
  whether a *model* can author policies in these notations — that is the
  acquisition question, separate from this executability question.
- The graph's fragility is measured on tasks where its guard mismatches.
  Whether that is common or a property of how this particular guard was
  written is not established by five points.

Reproduce: `experiments/ad01/s09_representation_matrix.py`; evidence at
`reports/evidence/inv_r1_e1_matrix/matrix.json`.
