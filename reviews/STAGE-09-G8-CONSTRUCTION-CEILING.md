# G8: what a study-level construction ceiling is allowed to bind

**Status:** the defect is repaired in `src/settlement/store.py`,
`src/settlement/broker.py`, `src/settlement/authority.py`, and
`experiments/ad01/construct.py`. The argument below is the reason, and it is
encoded in `_counters_spent_by` and `_study_operation_counts`, which are the two
places any future reader of a ceiling will land.

## The three sentences

No. A study-level ceiling may only be spent by a phase the ceiling names,
because a ceiling exists to bound the resource of one named phase, and a
ceiling another phase can drain is not a bound on that phase but an ordering
accident that reads as one. The defect was that `construction_calls` was
charged to every `model-inference` operation, so it was a second spelling of
`model_calls` rather than a bound on construction at all, and the S09 pilot ran
its four development episodes first, spent all four of its construction calls
on methods it acquired while developing, and arrived at P1 and P2 with no
authority left to construct the arms the ceiling exists to bound. The repair
makes the ceiling name its resource on the operation envelope, and makes the
charge and the credit read that one predicate, so a phase that asks a model a
question spends `model_calls` and only a construction spends
`construction_calls`.

## What was measured, before anything was changed

`tests/test_s09o_pilot.py` at `0f3a6da`: **6 failed / 3 passed**. The attribution
lane could not see the origin because the bundle is built in a fixture. Reading
the pilot's own output directory showed the refusal on both arms:

```
P1 | status= unavailable | calls= 0
    reason= 'policy constructor unavailable: construction call not admitted:
             study s09-m5-pilot-g8 ceiling construction_calls=4 reached at 4'
P2 | status= unavailable | calls= 0
    reason= (identical)
```

The four construction operations were the four development episodes, not the
arms:

```
development   model-inference= 16  -construct-= 16  -policy-l= 0
construction  model-inference=  2  -construct-=  0  -policy-l= 2
```

`DEV_SPECS` runs at `scripts/s09_pilot.py:1118`, before `_construct_arm` is
called at `:1134` and `:1137`, so the counter was exhausted by a phase the
ceiling does not name.

## The charge/credit asymmetry, which is the actual defect

Two predicates counted the same thing and disagreed:

- `_counters_spent_by` charged `construction_calls` to **every**
  `model-inference` operation.
- `_study_operation_counts` credited it only when `"-construct-"` appeared in
  the operation **id**.

An operation can therefore be charged without being credited. The pilot's own
accounting showed `construction.measured: 0` while the store had refused at 4.
Neither predicate was wrong on its own terms. Together they made the counter
unreadable in both directions, which is why the review could not establish the
origin from the test.

The repair replaces both with one predicate on the envelope key `resource`.
The effect schemas are closed by `_no_extra` in `broker.py`, so the resource
rides on the stored envelope beside `budget_kind`, not inside `payload`. It is
deliberately not called `kind`: `authority.KINDS` already uses that word for
the study phase, and a phase and a resource are different axes.

## What raising the constant would have done

The brief offered `CONSTRUCTION_CALLS = 12` in `scripts/s09_pilot.py`. Measured,
that is a tuning change and not a repair:

| ceiling | P1 | P2 | complete |
|---|---|---|---|
| 4 (before) | unavailable | unavailable | False |
| 12 (brief) | available | available | True |
| 16 (before) | unavailable | unavailable | False |
| 17 (after) | available | available | True |

Two readings of that table. Under the brief's 12 the arms come back, so it
appears sufficient. But 16 fails and 17 succeeds, which means the ceiling is
being spent by something other than the two constructions it names, and 12 only
worked in the runs measured because a different phase's spend had not yet
reached it. With the repair in place **the ceiling stays at 4** and both arms
are available, because the counter now counts constructions and there are two.
A constant raised to accommodate a mis-scoped counter is a number that has to
be re-raised whenever a study's schedule changes.

## Red before green, with the mutation confirmed

Every mutation below was confirmed to land by reading the changed line back.

**The charge predicate.** Reverting `store._counters_spent_by` to
`spent |= {"model_calls", "construction_calls"}` and rerunning
`tests/test_s09o_pilot.py`:

```
E       AssertionError: assert 'unavailable' == 'available'
FAILED tests/test_s09o_pilot.py::test_bound_policy_releases_drive_the_covered_domain
6 failed, 3 passed in 41.92s
```

**The credit predicate.** Reverting `payload.get("resource")` to
`"-construct-" in id`: the same six failures return.

**The producer tag.** Removing `resource="construction_calls"` from
`construct._call` in `experiments/ad01/construct.py`:

```
P1 unavailable | reason: 'policy constructor unavailable: model-inference
                 rejects unknown keys ['kind']'
```

This one earned its own line in the log, because the first attempt put
`kind` inside `payload` and the broker refused it. The refusal is correct and
is the reason the key rides on the envelope.

**The verifier's import path.** Removing the `sys.path` block from
`scripts/s09_verify.py`:

```
E       assert 1 == 0
E        CompletedProcess(args=['.../s09_verify.py', '.../full0'], ...)
... "problems":["code-ceiling-unreadable"] ...
```

Green with all four in place:

```
9 passed
```

## Two tests that had encoded the defect

`tests/test_authority_recovery_hardening.py::test_construction_calls_are_enforced_from_durable_operations`
and `tests/test_store_authority_invariants.py::test_construction_calls_are_a_durable_study_counter`
both passed under the old rule and both were asserting it. The second read
`"-construct-" in id` and expected one credit from two model calls; the first
refused a second call for being a second model call rather than a second
construction. Both now declare `resource="construction_calls"` and pin the
corrected semantics, and the first gained a control: a development call with no
construction resource is admitted **after** the ceiling is spent. A test that
went green because it stopped asserting would have looked identical here, so the
control is the assertion that carries the repair.

`tests/test_store_authority_invariants.py` also gained
`test_a_model_call_that_draws_no_construction_resource_is_not_charged`, which
pins the charge half on its own, so the two halves of the predicate cannot drift
again.

## The second defect in this group, which is unrelated to the ceiling

`scripts/s09_verify.py` never put the repository root on `sys.path`. Run as a
script, `sys.path[0]` is `scripts/`, so `from experiments.ad01 import construct`
raised `ModuleNotFoundError`, the verifier fell back to a hardcoded ceiling of
4, and every offline verification reported `code-ceiling-unreadable` and exited
1. The in-process verifier returned `pass` on the same bundle. **Two verifiers
of one bundle disagreed, and the one running in a subprocess was the crippled
one.** Every other script in `scripts/` already does this. Fixed the same way.

This defect was invisible while the ceiling was 4, because the fallback happened
to equal the real constant. It became visible the moment the arms came back and
the recomputed `construction_calls` reached 2 against a fallback of 4.
