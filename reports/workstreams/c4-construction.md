# c4-construction — the construction procedure is inheritable, not a menu

Lane C4. Branch `wt/c4-construction`, forked from `160f8e4`. OFFLINE lane:
no live model call, no network, fixture gateway only.

## The premise, re-verified in source rather than trusted

`experiments/ad01/improve_channel.py:137` declared

```python
_STRATEGY_SOURCE = {"low": IMPROVE_LOW_SOURCE, "high": IMPROVE_HIGH_SOURCE}
```

and lines 659-660 built `REACHABLE_EVIDENCE` as the sorted set of that
dict's values. `leaf_construct` (then `:1535`) resolved the program it
installed with `imp_source = _STRATEGY_SOURCE[strategy]`. So the reachable
evidence of any revision was those two integers regardless of what any
revision decided, which is exactly what `reports/workstreams/inv-c.md` §A.3
records and what the assignment names as the earliest wrong boundary of
milestone C.

## What changed

`experiments/ad01/improve_channel.py`, the strategy/construction selection
region only. No other module was touched.

**Deleted.** `_STRATEGY_SOURCE`, `_STRATEGY_EVIDENCE`, `REACHABLE_EVIDENCE`,
`MENU_EVIDENCE`, `_menu_probe` and the `menu_mean` headroom key. The menu
is gone rather than widened. A three-member dict is the same defect with a
larger number on it.

**Added.** A descendant is now built from its own parent's bytes.

- `construction_from_evidence(observations)` derives the input a
  descendant probes from the evidence the round actually gathered. This
  is the inheritance: a revision that probed differently produces a
  descendant that probes differently.
- `_descendant_source(parent_source, construction)` substitutes that input
  into the parent's own probed-input expression and returns the parent's
  bytes with exactly those characters replaced. When the parent's input is
  a literal the splice is textual, so a descendant differs from its parent
  by one integer and is otherwise byte-identical.
- `reachable_evidence(source)` reports what a given program can be made to
  probe. It is a function of the program, not a constant published beside
  it, so it is asked rather than read.

`leaf_construct` now takes the derived integer and refuses the removed
`low`/`high` labels by name. `validate_improve_action` still requires the
`strategy` key a construct action carries, because the authored controls
emit it and lane C2's fixtures rewrite that binding, but the name no longer
selects anything.

## Two deliberate limits, and why

**The two authored controls are byte-identical to their previous form.**
`IMPROVE_LOW_SOURCE` and `IMPROVE_HIGH_SOURCE` are unchanged. An earlier
revision of this lane rewrote their construction binding, and that
regressed 23 tests, because `tests/test_inv_c2_freeze.py` and
`tests/test_inv_c3_fixture_repair.py` rewrite the literal string
`strategy = "high" if first[0] == 1 else "low"` in those exact sources as
their fixtures. A control's shape is a shared vocabulary between lanes, not
something this lane may restate. What changed is the constructor, not the
controls.

**`source_kind` stays `"fixed-menu"`.** It is provenance owned by
`frontier.validate_package:429`, which refuses anything else for an
`authored-control` origin, and six other files read it. It says the bytes
were authored here rather than returned by a model, which is still true of
a descendant built from an authored parent. Renaming it would have broken
adoption everywhere to describe a selection that no longer exists.

## Two bugs found in this lane's own code, both by its tests

**An identity check across two parses never matches.** The first
`_descendant_source` compared nodes from `ast.parse(parent)` against nodes
from a second `_probe_x_expression(parent)` call. The two parses produce
different node objects, so `is` was always false and every construction
raised "parent selects no probe input to replace". `_probe_input_sites`
now reads the sites off the tree that will actually be rewritten.

**`ast` column offsets are UTF-8 bytes, not characters.** The literal
splice used `col_offset` to index a `str`, which cut the source in the
wrong place whenever anything non-ASCII preceded the literal; the
descendant was unparseable and several tests failed for a reason that had
nothing to do with construction. `_literal_probe_span` now decodes each
line before indexing.

## Two pre-existing gaps found, not fixed, not mine to fix

`_attempts_frozen_write` treats `view["grant"] = {...}` as legal. It
recurses into `Subscript.value`, which is the object being subscripted,
and never inspects the key, so an assignment to a frozen name through a
subscript is not caught. Lane C2's own fixtures write a bare name and are
caught. My test therefore uses a bare `grant = {...}` binding, and asserts
`_attempts_frozen_write` on the fixture before relying on the refusal. The
gap is real and worth a lane of its own; closing it here would have meant
changing C2's region.

## Gate

Reproduce from the worktree:

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims;
export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/c4final.jsonl;
cd /mnt/d/AI/Agent-Society-v2/.worktrees/c4-construction &&
PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/c4-construction/src timeout 2400
/home/ubuntu/.venvs/as9/bin/python -m pytest tests/test_s09rev_boundary.py
tests/test_s09_e4_channel.py tests/test_s09_e4_qualification.py
tests/test_s09_learner_revision.py tests/test_s09_e4_evidence.py
tests/test_s09_e4_remediation.py tests/test_inv_c2_freeze.py
tests/test_inv_c3_fixture_repair.py
tests/test_inv_c4_inheritable_construction.py
tests/test_m2_frontier_inherit.py tests/test_provenance_authority.py
-q -p no:cacheprovider -rf'
```

```
24 failed, 200 passed in 558.61s (0:09:18)
```

`tests/test_inv_c4_inheritable_construction.py` alone: `13 passed`.

**The 14 pre-existing failures are unchanged, same ids as at base.** All
share one cause: `method_exec` refuses a policy source with no successful
durable receipt on this host, so every test that executes a step fails.
At base, before any edit of mine, the same command reported `14 failed,
197 passed`. None of them is in a region this lane changed.

Note on the assignment's expectation of `20 passed` for
`tests/test_inv_c2_freeze.py`: at base on this host it reports 14 passed
and 6 failed, not 20 passed, for that execution reason alone. Lane C2's
report records `20 passed` on a host that could execute steps. The count
is unchanged by this lane in either reading.

## The 10 new failures, and why each is a consequence rather than a defect

Every one of them asserts the deleted two-member menu. None is edited:
editing another lane's test to accommodate this change is what the
standing rule forbids, and the coordinator's call.

| test | what it asserts |
|---|---|
| `test_s09rev_boundary.py::test_a_descendant_only_ever_runs_the_authored_menu` | `_STRATEGY_EVIDENCE == {"low": 3, "high": 11}` and `REACHABLE_EVIDENCE == {"3","11"}` |
| `test_s09rev_boundary.py::test_channel_headroom_reports_no_measurable_headroom` | `reachable_evidence == ["3","11"]` |
| `test_s09_e4_evidence.py::test_the_artifact_agrees_with_a_live_run_of_the_module` | live headroom equals the immutable artifact, whose `reachable_evidence` is `["3","11"]` |
| `test_s09_e4_evidence.py::test_both_reachable_descendants_were_measured` | the artifact's reachable set is `{"3","11"}` |
| `test_s09_e4_remediation.py` (3 tests) | patch `_STRATEGY_EVIDENCE` to plant a substrate effect |
| `test_s09_e4_qualification.py::test_the_decoy_input_is_one_the_decision_could_otherwise_reach` | input 7 is the ceiling's argmax |
| `test_m2_frontier_inherit.py::test_second_improvement_round_under_inherited_bytes` | a descendant's digest equals `make_control("high")`'s |
| `test_provenance_authority.py::test_restart_revalidates_historical_accepted_revisions` | `leaf_construct("high", ...)` then `("low", ...)`, now refused by name |

Two of these are worth a coordinator's attention rather than a quiet
repair. The m2 test says a descendant's improvement bytes equal a menu
member's, which is the claim this lane exists to falsify: the descendant
of the low control at construction 3 is the low control's own bytes, not
the high member's, because the menu's `low`/`high` split corresponded to
the observation's first bit and the inherited construction does not. And
`leaf_construct` now refuses `"high"` and `"low"` by name, so that
provenance test must be re-expressed against the derived construction.

## Does a revision change its descendant's construction?

Yes. `drive_improve_round` passes the evidence the round actually gathered
to `leaf_construct`, which substitutes it into the parent's own probed
input, so a revision that selected a different input produces a descendant
with different bytes probing a different input. Asserted by comparing
bytes, through `unauthorised_change`, in
`test_descendant_source_differs_from_parent_source`.

The reachable set is now all sixteen inputs the instrument accepts, rather
than two. Measured over the audit cohort of 150 seeds, the descendant a
revision can reach has argmax 12, argmin 9, a spread of 0.00933 across
inputs, and thirteen distinct values across the sixteen probes, against
the two-member menu's two values and 0.00622. That is the range L7 was
for. Note that a wider reachable range is not a benefit result: whether any
revision of this decision improves a learner is lane L8's measurement, and
the six-dispatch negative's cause is changed but not yet re-run.

## Composition with lane C2

The two lanes compose rather than compete. C2's `unauthorised_change` is
what says a revision may change the probed input and nothing else. This
lane's `test_descendant_source_differs_from_parent_source` uses that same
instrument to grade a construction, so a descendant is provably its
parent's procedure with one decision substituted. A revision that changes
the construction procedure is precisely the authorised kind C2 keeps
eligible, so this is not a way around the freeze. C2's freeze was not
weakened, its tests not edited, and its registry untouched.

## Undetermined

- **Whether the inherited construction is the right arithmetic.** It takes
  the last input the round spent. That is a procedure a reviser can
  change and a descendant inherits, which is what the requirement asks
  for. Whether it is a *good* construction is a measurement nobody has
  made, and this lane does not claim it is.
- **Whether the six-dispatch negative should be re-run.** Its cause has
  changed. Re-running it needs a new freeze, because a changed freeze does
  not make old and new comparable. That is L9, and it is not this lane.
- **Whether the ten tests above should be re-expressed or the change
  reconsidered.** They are the coordinator's call. Three of them
  (`test_s09_e4_remediation.py`) plant a substrate effect by patching a
  module attribute that no longer exists, so they need a new seam to do
  what they did.