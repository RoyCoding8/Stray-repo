# Swarm result: three slices, three PASS

Framed in `PLAN-SWARM-STAGE-09-FINAL.md`. Partition, not race: three
independent slices on disjoint files, one worktree each, integration
reserved to the coordinator. Both completed slices are merged and their
claims verified by me rather than accepted.

| slice | verdict | what it produced |
|---|---|---|
| E2 scored observable | **PASS** | `s09_e2_scored.py`; a reader scores 2.0 where an identical blind policy scores 1.0 |
| ordering AST | **PASS** | `ordering_ast_policy.py`; the Boolean refusal is a world binding, not a grammar limit |
| ordering graph | **PASS** | `ordering_graph_policy.py`; a `World` value, not a subclass |

147 tests pass across both slices and the harness they touch.

## The AST slice overturned a conclusion of mine

I had recorded the ordering-world AST refusal (`probe target must be
schedule.compare`) as an expressivity limit. The slice proved that is
wrong, and proved it rather than asserting it: the refusal comes from
`boolean_ast_policy._validate_action` hardcoding the Boolean world's
targets — a **world binding**, not a grammar limit. The same record runs a
real episode through the same frozen node set.

The real missing cell is sharper and more interesting: **the node set has
no symbolic `lt`**. The exact loader refusal is
`$.policy_ast.entry.cond: lt requires two numeric operands`, and the same
document with `eq` loads. So the node set can *identify* a job the world
named but cannot *order* two — a program may choose among orders it wrote
down, never derive one.

The behavioural consequence is on 17 of 40 seeds: the arm commits an order
that contradicts the comparison it just paid for. It scores 0.0 and it
**runs every time**. That is the distinction between "inexpressive" and
"cannot compute a function of its observation", and it reproduces the
Boolean matrix's finding on a second instrument.

## The graph slice found a real bug in code I wrote

`_field_value` returned the **whole view** for a single-segment field, so
`remaining`, `instrument` and `task_id` resolved to a dict where an int was
expected. Every guard naming one of them compared a dict to an int and was
**silently always false** — an arm would take its fallback arm and the
trace would read as a policy decision, not a broken read. No existing arm
guarded on those fields, which is why it survived.

The loader type-checks field names, so admitting one implies it can be
read. `tests/test_s09graph_field_reader.py` now walks the entire admitted
vocabulary and fails if any name is unreadable — and that walk caught two
of my own fixture bugs before it caught the real one, which is what a
vocabulary test is for. Fixing it also exposed a second defect: the
`public_world.*` family names a field *inside* the view's `public_world`
entry, not a walk from the view root.

All nine admitted fields now read correctly against the world's own view.

## A refactor of mine broke a documented behaviour, and the test said so

I parameterised `_python_step_factory` by world. It then reported
`episode-failed` where the suite expected `comparable` — because
`boolean_policy.choose_action` converts a failure inside the step into a
recorded refusal, and my version called its internals directly and lost
that. `test_registration_does_not_validate_the_record_it_is_given` pins
the behaviour and caught it. Reverted to delegation: the contract a policy
must satisfy is not the harness's to restate.

## Still open, and named rather than glossed

The ordering world has **no working STEP arm**: `boolean_policy
.choose_action` is Boolean-typed the same way the AST and graph were. I
parameterised the factory to refuse rather than half-support it, because
the ordering world's validators take a `ScheduleSession` and restating
them in the adapter would create a second source of truth. Wiring the
world to own its own arms is the next build, and it is not this pass.


---

## The E2 slice: an observable that discriminates

`s09_e2_scored.py` replaces the `diagnostic` field that made all five
contrasts void. It scores a returned proposal by **executing** it, through
the real out-of-process step boundary, and reports two legs summing to
[0, 2]:

- **evidence** — the same bytes are stepped twice, once under the arm's
  view and once with every observation's verdict flipped. The leg is the
  fraction of the executed action's non-verbatim input values that move.
- **agreement** — the world grades the candidate with the real
  `representation.checkers`, then compares it against the same checker on
  an authored control for the same task under the same budget.

The test that the old observable could not pass:
`test_two_policies_differing_only_in_whether_they_read_score_differently`
— reader 2.0, otherwise-identical blind policy 1.0, same task, same
checker verdict, same candidate. A context-echoing policy earns neither
leg, pinned by `test_a_policy_that_echoes_its_context_cannot_earn_the
_agreement_leg_by_it`.

`unscored` is never zero. A missing proposal, a gate refusal, a raising
policy, an out-of-scope method or a wrong-target action all produce
`scored=False` with a `detail` naming the stage, and `contract()` returns
the word `unscored` — never a win or a loss.

One design decision I would defend and did not overrule: the score is a
plain **sum**, not a weighted average, because weighting agreement against
evidence is a pre-registration each study must make and this module should
not make it for every study that uses it. The legs ride out separately.

**The E2 contrasts still have to be re-run on it.** Building a
discriminating observable is not the same as producing a result, and the
five contrasts remain unrun on the new scale.
