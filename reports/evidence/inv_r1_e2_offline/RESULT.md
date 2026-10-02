# E2 offline: the arms that never differ, and why the instrument cannot fix it

No gateway, no dispatch, no store. Every number here comes out of one run of
`make_evidence.py` against the committed evidence and the frozen world.

**The brief's claim is verified.** All three scored arms in `readings.json`,
both substitution arms in `remaining-contrasts.json`, and all nine replica
rows selected `seed-sw-ddmin`. The transfer half of the claim is stale, and
the replica's own separation is real but is not a learning effect.

## 1. The claim, file by file

Every `selected` value in the three files the gap names:

| file | arm | selected | scored |
|---|---|---|---|
| `readings.json` | relevant | `seed-sw-ddmin` | true |
| `readings.json` | none | `seed-sw-ddmin` | true |
| `readings.json` | irrelevant | `seed-sw-ddmin` | true |
| `remaining-contrasts.json` | substitution/original | `seed-sw-ddmin` | true |
| `remaining-contrasts.json` | substitution/flipped | `seed-sw-ddmin` | true |
| `remaining-contrasts.json` | transfer/adapted | `""` | **false** |
| `remaining-contrasts.json` | transfer/target_only | `""` | **false** |
| `transfer.json` | adapted | `seed-gr-ddmin` | **true** |
| `transfer.json` | target_only | `seed-gr-ddmin` | **true** |

The five rows the gap quotes are exactly right. The claim is verified.

**The transfer half of the claim is stale.** The gap reads
`scored: false` and quotes `remaining-contrasts.json`, which still holds
that copy. `transfer.json` was rewritten by `169c341` (2026-09-27) with both
arms scored, one commit after `2d48dea` (2026-09-27) wrote the combined
file. The transfer contrast is scored today. That half of the gap is closed
by a run that already happened.

## 2. The replica selected one method too, and its arms still differed

`inv_r1_e2_replica/report.json` records `selected: "seed-sw-ddmin"` in all
nine rows, so the gap's claim holds for this file as well. But the same file
also records a clean separation:

| arm | mean score | evidence |
|---|---|---|
| relevant | 2.0 | 1.0 |
| irrelevant | 2.0 | 1.0 |
| none | 1.0 | 0.0 |

`paired.delta` is 1.0 on both `relevant-minus-none` and
`irrelevant-minus-none`, over three target tasks, with no unscored task.

So the claim and the separation are both true of the replica, and they sit
together: three arms named the same method and two of them scored a full
point above the third. The difference is entirely in the evidence leg, and
section 3 says what earned it. This is why "the treatment never differs from
the control" is a stronger claim than the evidence supports, and why reading
it off the `selected` column alone would have missed a separation that is
real, measured, and not a learning effect.

## 3. The separation is an echo, and the replica already recorded why

Recomputed here rather than quoted. Three authored policies on the same
target, under an arm with three observations and an arm with none:

| policy | reads the view | relevant | none |
|---|---|---|---|
| reader | decides from the verdicts | **2.0** | 1.0 |
| echoes | copies verdicts into `inputs`, decides nothing | **2.0** | 1.0 |
| ignores | names the same method, reads nothing | 1.0 | 1.0 |

The echoer and the reader tie at 2.0. Both name `seed-sw-ddmin`, the same
method the ignorer names, and the echoer differs from the ignorer only by
copying a string into an input key.

So the replica's `+1.0` evidence leg is earned by echoing. The replica named
this itself in its own `echo_confound` block, in words that were correct, and
then read the block as a learning effect in `paired`. This is the E1 acquired-
vs-control shape the coordinator flagged: a control that is a wrapper over a
default rather than a distinct policy.

## 4. Why no dispatch would have produced a learning effect

Three structural facts, each measured, none of them a sampling limit.

**Every authored verdict in the frozen world is the same word.** All 54 tasks
under both authored methods, 108 pairs, graded by
`experiments.representation.checkers`: `{'preserved': 108}`. The
`ddmin`/`greedy` spread is real and large — normalized reduction 0.700 against
0.500 on the target below — but it lives in the *measure*, which no verdict
records.

**The prompt shows verdicts without the method that earned them.** The
relevant arm's whole contribution to its prompt is one line:

```
Prior observations: [{"task_id":"ad01-w0-dev-sw-00","verdict":"preserved"}]
```

`learner.treatment_prompt` (`experiments/ad01/learner.py:988`) renders
`task_id` and `verdict` and nothing else. The relevant and irrelevant arms
differ by exactly that line, both of length 1663 characters, and both render
`preserved` three times over a target whose two eligible methods are
`seed-sw-ddmin` and `seed-sw-greedy`. Nothing in the rendered bytes names the
method or the reduction, so a policy reading them perfectly learns a constant.

**The score ties the better method to the worse one.** Two authored policies,
identical except for the method they name, scored through
`s09_e2_scored.score_response`:

| method | score | evidence | candidate measure | normalized reduction |
|---|---|---|---|---|
| `seed-sw-ddmin` | 1.0 | 0.0 | 3 | **0.700** |
| `seed-sw-greedy` | 1.0 | 0.0 | 5 | **0.500** |

A policy that learned to pick the better method scores exactly what one that
picked the worse one scores. The agreement leg is a shared verdict, and
`check_software` returns `preserved` for both, so the score cannot move.
This is the observation the brief asked for: the comparison has to be one
where a policy that learned something is distinguishable from one that did
not, and on the current observable it is not.

## 5. The live route is blocked, so the run could not have happened anyway

`src/settlement/gateway_http.py:697`:

```python
or route["provider"] != expected.get("provider")
```

The two comparisons above it, at lines 330 and 341, both lower-case both
sides. Line 697 does not. `SETTLEMENT_EXPECTED_ROUTE` records `"provider":
"nvidia"`. `reports/cap-sheets/invl02-live-grant.md` records `Nvidia`
observed. The response is spent, then refused as `RESPONSE_METADATA`.

I confirmed the coordinator's diagnosis against the source and did not
repair it, because changing route verification changes what every prior run's
validity means.

## What was dispatched, and what it cost

**Nothing. Zero dispatches.** No operation was admitted, no reservation was
made, no receipt was written, no store was created. The free route costs
nothing per call and was not called. This is the whole of the store
accounting, and it is different from the model-call accounting only because
there is no model call either.

## What a result looks like now

Not a run. A repair, in this order, each step cheap relative to the dispatches
it would save:

1. Fix the provider comparison at line 697 so the route can complete a send.
   This is a validity question for every prior run and is not this lane's to
   decide.
2. Re-freeze the experience so a record names the method that earned it and
   the reduction it reached. Without that, the treatment arm is shown a
   constant and no acquisition can respond to it.
3. Re-score on normalized reduction, which separates 0.700 from 0.500, in
   place of the agreement leg, which cannot separate them.
4. Exclude the echoer, or admit it as the control it is, so a policy that
   copies its context cannot earn the leg.

Only after 1 through 4 is a dispatch worth spending, and only then is a tie
informative.

Evidence: `result.json`, produced by `make_evidence.py`.
