# E2, the three remaining contrasts on the scored observable

The relevant/none/irrelevant triple is in `RESULT.md`. These are the other
three, run through the same scored observable and the same live route.

## Observation substitution: the policy does not read its evidence

Two acquisitions of the same policy, identical except that every
observation's verdict is flipped:

| acquisition | scored | score | evidence | agreement | selected |
|---|---|---|---|---|---|
| original verdicts | **true** | 1.0 | **0.0** | pass | `seed-sw-ddmin` |
| flipped verdicts | **true** | 1.0 | **0.0** | pass | `seed-sw-ddmin` |

`responds_to_evidence: false`. The same prompt, the same model, the same
selected method — and the scored observable's evidence leg is **0.0 on
both**. The leg compares the executed action under the two views, and it
does not move.

This is the campaign's original concern, measured on the observable built
for it. The N-01 finding was that a policy could score full marks from the
task id alone; the question since has been whether a policy reads its
evidence at all. On this acquisition, at this scale, it does not.

**The apparatus discriminates** — the swarm's test has a reader at 2.0
against an identical blind policy at 1.0 — so this is a property of the
acquisition and not of the instrument.

## Retained versus cold reacquisition: crossover at 5 uses

| arm | construction dispatches | use dispatches | unit |
|---|---|---|---|
| retained | 0 | 5 | 3269 |
| cold | 1 | 5 | 3269 |

Unchanged from the earlier costing, and unchanged because it is a cost
result: the unit price comes from the cap sheet and nothing about the
scored observable touches it. **Crossover at 5 uses** — below it the cold
arm is cheaper, at it they are equal, above it retention wins.

This is the one contrast of the five that never depended on model
behaviour, and it is the only one whose answer cannot be retracted by a
better dependent variable.

## Source-to-target adaptation: a tie, and the earlier negative was a staging artifact

The first attempt returned `unscored` for both arms while the identical
acquisition scored cleanly on its own. Re-run on its own budget — and I had
dropped its database mid-run, which is the likeliest reason — both arms
score. Target `ad01-w1-transfer-gr-00`, a **graph** task, 382 characters
and 3 records per arm:

| arm | experience shown | scored | score | evidence | selected |
|---|---|---|---|---|---|
| adapted | **software** | true | 1.0 | 0.0 | `seed-gr-ddmin` |
| target-only | **graph** | true | 1.0 | 0.0 | `seed-gr-ddmin` |

**A tie, and the tie overturns my earlier reading.** I had recorded this
contrast as a *negative*: that cross-family experience is worse than none
because it drags the proposal back to the source family. On the scored
observable the adapted arm selects `seed-gr-**ddmin**` — a **graph**
method — and so does the target-only arm.

The earlier negative was almost certainly the echo I had already
diagnosed: on the `diagnostic` field, a software-experience arm appeared
to name software. On an observable that executes the policy, the same
arm names a graph method. The apparent family-drag was the field echoing
its input, exactly as `inv_r1_e2_challenge` concluded for the other
contrasts.

**The corrected claim is weaker and better supported**: cross-family
experience neither helps nor hurts here; the model selects the target
family's method under both. Whether adaptation ever *helps* is not
established — one task, one dispatch per arm, and a tie is not a
difference in either direction.

## All five, on one observable

| contrast | result |
|---|---|
| relevant vs no experience | tie at 1.0; both 0.0 on evidence |
| relevant vs size-matched irrelevant | tie at 1.0; both 0.0 on evidence |
| retained vs cold reacquisition | crossover at 5 uses (cost, not behaviour) |
| source-to-target adaptation | tie at 1.0; both select a graph method |
| observation substitution | no response to flipped verdicts; 0.0 evidence both |

Four of the five are behavioural and **all four are ties or non-responses**
against an observable verified to separate a reader from a blind policy.
That is the campaign's E2 answer, and it is negative: on this substrate
and at this scale, experience did not measurably change what the model
acquired.
