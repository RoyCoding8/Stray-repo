# E2 experience contrast, measured

The relevant / none / irrelevant triple, on the frozen panel, with the
scored observable repaired on the campaign side. Two independent
namespaces. One null, and a bound on what any positive could have been.

## The result

`normalized_reduction` **does not separate the three arms**. In both
namespaces the two experience arms chose the same method as the
no-experience arm on every target where they scored, so both paired
contrasts are 0.0 or the same non-zero value in both arms.

### `invr1e2contrast`, the first contrast

| arm | target | normalized_reduction | scored | selected |
|---|---|---|---|---|
| relevant | within-sw-00 | 0.7000 | true | `seed-sw-ddmin` |
| relevant | within-sw-01 | 0.7692 | true | `seed-sw-ddmin` |
| relevant | within-sw-02 | 0.7273 | true | `seed-sw-ddmin` |
| none | within-sw-01 | 0.7692 | true | `seed-sw-ddmin` |
| none | within-sw-02 | 0.7273 | true | `seed-sw-ddmin` |
| irrelevant | within-sw-00 | 0.7000 | true | `seed-sw-ddmin` |
| irrelevant | within-sw-01 | 0.7692 | true | `seed-sw-ddmin` |
| irrelevant | within-sw-02 | 0.7273 | true | `seed-sw-ddmin` |

| contrast | deltas | n | delta | se | z | unscored |
|---|---|---|---|---|---|---|
| relevant − none | [0.0] | 1 | 0.0 | 0.0 | null | within-sw-02 |
| irrelevant − none | [0.0] | 1 | 0.0 | 0.0 | null | within-sw-02 |

Denominator 1 of 3. The `none` arm lost both its dispatches on
within-sw-02 and both on within-sw-00, so four nulls, all in that arm. The
instrument's own rule drops an unscored task from the pair and names it,
which is what the run did. The 0.0 is a measurement over one pair, not a
zero written in place of three.

### `invr1e2contrastr2`, the replication

| arm | target | normalized_reduction | scored | selected |
|---|---|---|---|---|
| relevant | within-sw-00 | 0.7000 | true | `seed-sw-ddmin` |
| relevant | within-sw-01 | 0.7692 | true | `seed-sw-ddmin` |
| relevant | within-sw-02 | 0.4545 | true | `seed-sw-greedy` |
| none | within-sw-00 | 0.7000 | true | `seed-sw-ddmin` |
| none | within-sw-01 | 0.7692 | true | `seed-sw-ddmin` |
| none | within-sw-02 | 0.7273 | true | `seed-sw-ddmin` |
| irrelevant | within-sw-00 | 0.7000 | true | `seed-sw-ddmin` |
| irrelevant | within-sw-01 | 0.7692 | true | `seed-sw-ddmin` |
| irrelevant | within-sw-02 | 0.4545 | true | `seed-sw-greedy` |

| contrast | deltas | n | delta | sd | z | unscored |
|---|---|---|---|---|---|---|
| relevant − none | [0.0, 0.0, −0.2727] | 3 | −0.0909 | 0.1575 | −1.225 | none |
| irrelevant − none | [0.0, 0.0, −0.2727] | 3 | −0.0909 | 0.1575 | −1.225 | none |

Denominator 3 of 3. Nine of nine dispatches scored, three nulls all
recovered by the declared retry.

**The replication is the informative one, and what it shows is the null.**
On within-sw-02 both experience arms switched to `seed-sw-greedy` and the
control did not, so the delta is −0.2727 in both contrasts. The two
experience arms moved **identically**, and neither tracked the control. So
the contrast separates the arms from the no-experience arm on one target
and does not separate relevant from irrelevant on any target. `z = −1.225`
against a minimum attainable p of 1/2 at two clusters, so no inferential
claim is available and none is made.

**Relevant experience and irrelevant experience are indistinguishable from
each other in both namespaces.** That is the finding, and it is stronger
than the first namespace's, because here the graded outcomes genuinely
vary, the observable is not silently zero, and the arms are size-matched.

The null is the answer. Experience, relevant or not, did not improve the
decision over naming the first eligible method.

## The bound: no positive delta was attainable

This is the finding that makes the null legible. The policy's only lever on
this instrument is the action's decision vector, `(method_id,
max_queries)`. The `reachability_census` enumerates the whole grid with no
model and no dispatch, and on all three frozen `within` targets the
zero-information default, the first eligible method at the frozen budget,
is already the best cell:

| target | `ddmin@8` (default) | `greedy@8` | best in grid | attainable positive | attainable negative |
|---|---|---|---|---|---|
| within-sw-00 | 0.7000 | 0.5000 | 0.7000 | **0.0** | 0.5000 |
| within-sw-01 | 0.7692 | 0.4615 | 0.7692 | **0.0** | 0.4615 |
| within-sw-02 | 0.7273 | 0.4545 | 0.7273 | **0.0** | 0.4545 |

**No decision available to a policy beats writing down the first eligible
method.** The positive side of this contrast is 0.0 by construction, and
the negative side reaches 0.538. So the instrument can report a policy that
does worse and cannot report one that does better. A positive number here
would have had to come from somewhere other than a better decision, which is
the same defect the prior namespaces found in the evidence leg, one level
down.

This is a property of the panel, not of the model, and it is measured
offline. The instrument can move: the grid reaches six distinct values on
within-sw-00 across methods and budgets. It is the default, not the
instrument, that is stuck at the ceiling.

## Four defects, found before any dispatch, none patched

`e2_replication` is not this lane's to edit. Each of these is a defect of
the frozen instrument and each still stands in it.

**1. The estimator reads two keys the campaign's own row does not write.**
`reading_row` writes nine fields. `paired_report` reads
`normalized_reduction` and `action`, through `_reduction_of` and
`_decision_of`. Neither is among the nine. So `_reduction_of` returns 0.0
for every reading, `_decision_of` returns `{'', None}` for every reading,
every paired delta is 0.0 by arithmetic, and every `decisions[*].differs`
is `False`. **The frozen replica's recorded `deltas: [1, 1, 1]` came from
`score`, and its `decisions` block reported no difference on all three
tasks while the arms demonstrably selected different methods.**

`Reading.as_dict` carries both keys. Keeping the `Reading` makes the frozen
`paired_report` work unchanged, and that is what this campaign does. The
estimator is correct; the projection feeding it was lossy.

**2. The relevant arm's graded outcome is uniform.** At `MAX_QUERIES = 8`
the authored ddmin grades `ok-preserved` on all three dev software tasks, so
the three records a policy reads differ only in `task_id`. The same reducer
at `max_queries = 3` grades `ok-preserved / ok-incumbent / ok-preserved`.

**3. `verdict` is constant across the whole panel.** A sweep of all three
worlds, both families, both seed capabilities and budgets 1 through 16
produces **1728 `preserved` verdicts and nothing else**, and only two
reasons (`ok-preserved` 1329, `ok-incumbent` 399). The cause is in the
reducers: both only ever emit legal deletions that keep the witness, so a
reducer's output cannot fail. The checker can say `not_preserved` and
`invalid`; hand it a candidate that drops the witness and it does. The
instrument's route experience to the policy therefore has one value, always.

**4. The prompt names `reason` and the view drops it.**
`packet.project_observations` is a five-key allowlist. `reason` and
`reduction` are outside it. The prompt renders `reason` in its prior-
observation line and the policy never receives it. This is the third
instance of the same drop, after the two the prior repair fixed on the
prompt side.

## What each treatment actually received

The assignment asks for this and a prior bug dropped information at three
points, so it is derived from the rendered bytes and the projected view
rather than asserted.

| arm | prompt chars | observations | verdicts delivered | dropped before the policy | named in prompt, not delivered |
|---|---|---|---|---|---|
| relevant | 1774 | 3 | `preserved` | `reason`, `reduction` | `reason` |
| irrelevant | 1774 | 3 | `preserved` | `p`, `reason`, `reduction` | `reason` |
| none | 1518 | 0 | none | none | none |

`interfaces_equal: true`. `opportunity_equal: true`. All three arms render
the same eligible methods and the same allowance; the two that carry
experience carry 3 records each, size-matched at **770 characters**,
asserted before dispatch rather than described afterwards.

The `none` arm is stepped under an empty observation list, which is the
honest scoring of a policy shown nothing, and its 1518 characters against
1774 is the experience the other two were shown.

## The graded-outcome uniformity defect, and how it is answered

The campaign builds its own evidence. **This is a campaign-side construction,
not a repair.** `e2_replication` is not edited and this campaign cannot
change what the frozen instrument measures; the same defect still stands
there. What the construction buys is that the contrast has a chance to be
read at all.

Three things differ from `e2_replication.run_campaign`:

**The relevant arm's records are built here, at a budget where the graded
outcome varies.** `EVIDENCE_MAX_QUERIES = 3`, frozen in the contrast body
and verified before dispatch. The reducer is the campaign's own
`seeds.run_seed`; the grading is the campaign's own `checkers`. Only the
budget moved.

**The graded outcome is narrated into `detail`.** Because `verdict` is
constant and `reason` is dropped, `detail` is the one graded field a policy
receives. It reads
`"ad01-software on ad01-w0-dev-sw-00 at 3 queries: ok-preserved, reduction 0.5"`,
which is a re-derivable function of the record's other fields, so the
offline verifier can check it.

**The control's budget differs on purpose.** `CONTROL_MAX_QUERIES = 6` is
the smallest whole budget at which the graph pool's own graded outcome
varies. A control whose profile matched the treatment's would confound
relevance with the informativeness of the experience. What the control must
match is subject matter, size and record count; what both arms must have is
a varied outcome. Both are gated, and a uniform arm on either side is
**refused** rather than reported.

### Two bugs the gate caught in this lane's own construction

Both are recorded because a reviewer will ask whether the construction was
tuned until it passed.

**Padding `detail` destroyed the control's graded text.** The first
version refitted the control to the treatment's character count with
`learner._resized`, which pads the last record's `detail` with `x`. That
overwrote `ok-incumbent, reduction 0.211` with a row of `x`, so the control
stopped carrying any outcome. The uniformity gate refused the campaign. The
padding now goes to a key outside the five-key allowlist, so it is counted
by the serialiser the size matcher measures and delivered to no policy.

**Counting distinct `detail` strings measured identity, not outcome.** The
`detail` this campaign writes embeds `task_id`, so three records all saying
`ok-incumbent, reduction 0` produce three distinct strings. The first
version of the profile counted those and reported variation that was not
there. It now splits the template on its last colon and counts the graded
half, which is the half a policy can act on.

## Is a campaign-side construction a legitimate answer?

Yes, with a stated limit, and this is the reasoning.

The defect is a defect of the *instrument*, and the honest response to an
instrument defect you do not own is to report it. That is done, in the
artifact and above. What the construction adds is a measurement the frozen
instrument would have refused to make: a contrast whose arms differ in
their graded outcome, whose scored observable is not silently zero, and
whose treatment delivery is audited rather than assumed.

What the construction cannot do, and this is the limit, is change the panel.
The reachability census is a property of the frozen tasks, not of the
campaign, and it says the positive side is closed regardless of how the
arms are built. A better-constructed contrast on this panel would still be
able to report a negative and not a positive.

A reviewer should therefore read the null as what it is: the repair to the
scored observable and the treatment delivery were necessary and were made,
and the answer is still a null, and the panel could not have produced a
positive one.

## The instrument qualifies before any dispatch

`qualify_instrument` is run before the first send, and the campaign refuses
if it does not separate a reader from a blind policy.

| policy | score | evidence |
|---|---|---|
| reader (re-routes on the verdicts) | 1.7 | 1.0 |
| prompted-shape reader | 1.7 | 1.0 |
| blind (ignores the view) | 0.7 | 0.0 |
| echoer (copies, decides nothing) | 0.7 | 0.0 |
| plan-only reader (reads, re-plans, reaches no executor) | 0.7 | 0.0 |

The echo gaps are 0.0 under both exposures, so the leg no longer pays for
echoing. The plan-only reader scoring beside a blind one is retained as a
measurement: a read that never reaches the world earns nothing, which is
the claim the leg now makes on purpose. The scores are 0.7 rather than the
2.0 the frozen test expects because `normalized_reduction` is now the
benefit leg and `quality` carries the reduction itself.

**Note for the frozen test.** `tests/test_s09_e2_replication.py` has three
failures under WSL on this base (`prompted_shape_reader["score"] == 1.7`,
asserted 2.0). The frozen replica's own RESULT.md records 1.7 in the table
and 2.0 in the agreement table for the same arm, so the artifact and its
test disagree. Reported, not patched; `test_s09_e2_replication.py` is not
this lane's file.

## Two namespaces, and which is the replication

| namespace | kind | store | operation ids | dispatches | nulls | scored readings |
|---|---|---|---|---|---|---|
| `invr1e2contrast` | first contrast | `s09iso_invr1e2contrast_*` | own prefix | 10 | 4 | 8 of 9 |
| `invr1e2contrastr2` | **replication of the above** | `s09iso_invr1e2contrastr2_*` | own prefix | 12 | 3 | 9 of 9 |

`invr1e2contrastr2` is the genuine replication: a fresh store, fresh
operation ids, a fresh allocation, a fresh evidence directory, and the
first run left supported arms, which is the assignment's condition. It is
not a rerun after an apparatus failure, because the first run completed and
its arms were supported.

It is also the better measurement. The first namespace's denominator is 1
because four of its ten dispatches returned nothing, all in the `none` arm.
The replication's denominator is 3, and the difference between the two
namespaces is route availability, not model behaviour. That is worth
stating plainly: **the first namespace's 0.0 is underpowered and the
replication's is not**, so the replication is the number to read.

The earlier attempts in this lane's transcript are reruns, not replications.
Four of them failed pre-send on route-contract grounds before any token was
spent on a construction, and two produced artifacts that were later
replaced after the padding and profile defects above were fixed. Only the
two namespaces in the table are reported.

Both namespaces ran the same freeze,
`845b9f6db78c96412f797c07e0a397e26d7893cfba9f1bfbd60f0e1768e4d92a`, and
`verify_contrast` recomputes it against the module and the panel, so an
edited body is refused rather than reported.

## Exposure, billing, and the 502s

| line | namespace 1 | namespace 2 |
|---|---|---|
| construction dispatches | 10 of 18 | 12 of 18 |
| null dispatches (recovered by the declared retry) | 4 | 3 |
| input+output tokens | 10,862 | 13,186 |
| receipts with outcome `success` | 8 of 9 | 9 of 9 |
| estimated-budget units spent, ceiling | 47,348 | 47,348 |

Ceiling across both namespaces: 36 constructions and 2 route probes, 94,696
estimated-budget units. Units come from the broker's exposure schedule.
**They are not a price and not a dispatch count**, and the cap sheet says so
in the artifact.

**The billing discrepancy, stated rather than resolved.** This route states
its price as `usage.cost`. The adapter reads `charge_units` and `billed`.
The `usage` object on each receipt is the adapter's own normalised `Usage`,
not the provider's raw payload, so it always carries all five keys and the
three the route does not supply are `null` rather than missing. The
consequence is that `billed` and `charge_units` are **indistinguishable here
from a provider that returned them as `null`**, and `usage.cost` never
reaches the store at all.

So exposure is counted in dispatches, token counts and estimated-budget
units, and **no cost figure is asserted from this route in either
direction.** It is not a statement that the route is free, and not a
statement that it is not. Every campaign this batch left `billed` and
`charge_units` as `unknown`; here they are measured and the answer is
`null`, which is a real reading and a different one.

The route's availability is the largest single cause of lost measurement.
Seven of 22 dispatches returned nothing across the two namespaces, and
`billed` aside, that is what cost namespace 1 its denominator. A 502 is
recorded as `no settled response` with the operation id, and never as a
worse policy.

## The verifier, and its red proof

`experiments/ad01/e2_contrast_verify.py` re-derives every claim from the
observations stored beside it, using the campaign's own reducer and checker.
Seven checks: `freeze`, `evidence`, `size_matching`, `reachability`,
`paired`, `accounting`, `no_key`. All seven agree on both artifacts.

The observation/claim split is `live_construct.preflight_decision`'s. An
**observation** is recomputable from the panel: the arms are rebuilt, the
evidence is re-measured, the reachability grid is re-enumerated, the paired
deltas are recomputed through the frozen estimator, and each reading's
`normalized_reduction` is re-derived from the `initial_measure`,
`candidate_measure` and `verdict` that the same reading stores. A **claim**
is a statement about those, and is reported with both.

Four forgeries, each self-consistent, each caught:

| forgery | what it changes | caught by |
|---|---|---|
| `inflated_reduction` | a reading's `normalized_reduction` | `paired` |
| `self_consistent_inflation` | the reduction **and** the candidate measure it follows from, and the deltas recomputed to match | `paired` |
| `claimed_uniform_arm` | an evidence profile claiming a uniform arm | `evidence` |
| `inflated_ceiling` | a reachability ceiling above any decision | `reachability` |

The second is the forgery that verified clean in E1. Inflating the
reduction *and* shrinking the candidate so the report agrees with itself
throughout is exactly the shape that passed before. Only re-deriving the
reduction from the checker's own measures catches it, and it does.

## Cap sheet and authority

Derived from the frozen matrix before any effect and bound through the
durable owner (`settlement.broker.ensure_operation` +
`dispatch_operation`, under `authority.authorize_study` via
`s09_run_isolation.RunIsolation`).

| line | value |
|---|---|
| target tasks | 3 |
| arms | 3 |
| constructions per arm per task | 2 (1 + 1 declared retry) |
| planned constructions | 18 |
| route probe dispatches | 1 (up to 4 attempts on a provider failure) |
| message characters, widest prompt | 1774, measured by rendering every arm |
| `reasoning_effort` on the wire | **none-sent** |

The retry is spent only on emptiness. Four of namespace 1's five nulls were
retries, and each first attempt rides out in the record beside its retry, so
a reader sees that a first answer was replaced rather than that a first
answer was quietly discarded.

### The route conflict, and what it forced

Two adapter constraints are both correct and both frozen, and they
contradict each other on this route:

* a frozen route can only be attested on `chat`, because `responses`
  publishes no provider and the adapter refuses to infer one from the
  requested model id (`gateway_http.py:924`);
* `chat` refuses a request carrying a `reasoning_effort`
  (`gateway_http.py:960`).

`replica.acquire_one` always sends one, so the frozen dispatch and a frozen
route cannot both hold. The resolution is the dispatch, not the route: this
campaign's `acquire_one` is the frozen path with the effort omitted, which
`broker._validate_model` accepts as `None`. The cap sheet records the effort
as `none-sent` and separately records the `low` that the exposure schedule
prices a request at, so the receipt cannot be read as claiming a control the
wire never applied.

Two further pre-send refusals were found and fixed in the route contract, and
both are the adapter's own pre-send gates doing their job:
`RouteContract.from_mapping` requires all five fields including `provider`
and `endpoint`, the endpoint must carry no trailing slash because the
adapter `rstrip`s its own copy, and the `provider` must be the string the
**response body** names (`Nvidia`), not the catalog's `owned_by`
(`Kilo API`).

## What E2 now shows, and what it does not

E2 now measures the experience contrast on an observable that is not
silently zero: the relevant arm's records genuinely vary in their graded
outcome, the control is size-matched and varies too, and each reading's
reduction is re-derived from the measures it stores. Measured that way
across two namespaces, relevant experience and irrelevant experience are
**indistinguishable from each other** on every target, and neither beats
naming the first eligible method. E2 does not show that experience does
not help, because the panel closes the positive side entirely: the
zero-information default is the best of twelve reachable decisions on all
three targets, so the largest positive delta this panel admits is 0.0 while
the negative side reaches 0.538. E2 also does not show that the frozen
instrument is repaired: four defects stand in `e2_replication`, including
an estimator fed a projection that omits both keys it reads, which makes
that instrument's contrast 0.0 by arithmetic rather than by measurement.

## Reproduce

```
bash scripts/w2_e2_contrast_run.sh              # invr1e2contrast
bash scripts/w2_e2_contrast_run.sh --rerun      # invr1e2contrastr2
python3 -m experiments.ad01.e2_contrast_verify \
  reports/evidence/invr1e2contrast/report.json --red-proof
python3 -m experiments.ad01.e2_contrast_diagnose   # the four defects, offline
python3 -m experiments.ad01.e2_contrast_gate       # the qualification gate
pytest tests/test_ad01_e2_contrast.py -q           # WSL only
```

Live runs need WSL. `child_limits` refuses a host that cannot limit a child
before exec, and CPython refuses `preexec_fn` on Windows.
