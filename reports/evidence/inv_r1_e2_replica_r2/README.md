# E2 re-run under the corrected instrument

A re-run of `inv_r1_e2_replica` on the same frozen contrast, with the
evidence leg reading the candidate the world produced instead of the action
inputs the policy wrote. The freeze digest is
`27ba14c9cf69bdeb864e4f1f32aad89ae35ef5e07e34ac05076b97a19f2395bb`, identical
to the prior run, so the contrast did not move. Only the instrument did.

Nothing in `reports/evidence/inv_r1_e2_replica/` was modified.

## What the score claimed, and what it claims now

Before, the evidence leg compared the two runs' action inputs, skipping the
five fields in `VERBATIM`. An action input is writable by the policy, and
`method_id` and `max_queries`, the only two fields that reach a method
executor, were both excluded. So the leg measured how much of its own view a
policy copied into its action, and the copy was the only site it could move.

Now the site is the candidate the world produced, compared across the arm's
own verdicts and the flipped ones. It is downstream of the decision, it is
not writable (`assessment_profile._resolve_method` refuses a
policy-supplied `candidate` outright), and the dispatch already ran the
method in a further child, so no new plumbing was needed.

## Files

- `report.json` the run's own artifact, written by `e2_replication.main`.
- `instrument_evidence.json` the reader-against-echoer ordering measured
  three times: as it stands, and under each of two mutations.
- `cost.json` the four currencies, read from the durable store after the
  run.
- `make_instrument_evidence.py`, `make_cost_report.py` the generators.

## The instrument, measured

Baseline, on target `ad01-w0-within-sw-00`:

| policy | score | evidence | candidate moved |
|---|---|---|---|
| reader (re-routes on the verdicts) | 2.00 | 1.0 | yes |
| prompted-shape reader | 2.00 | 1.0 | yes |
| echoer (copies verdicts, decides nothing) | 1.00 | 0.0 | no |
| blind twin | 1.00 | 0.0 | no |
| plan-only reader | 1.00 | 0.0 | no |

Both mutations landed exactly once, asserted before measurement, with the
scorer reloaded from the mutated file.

- `leg-reverted-to-action-inputs` reproduces the recorded defect exactly:
  echoer 2.00, reader 1.00, gap -1, every score within `MAX_SCORE`.
- `candidate-comparison-disabled` flattens the ordering to a tie at 1.00.

The first attempt at the revert was a hybrid that scored the plan-only
reader 3.00, above `MAX_SCORE`. That was the tell that the measurement was
of the edit rather than of the old leg, and `scores_within_max` is now kept
in the artifact so the same drift is visible next time.

## The arms

Three arms over three target tasks, nine scored readings, all `preserved`
on checker `seed-sw-ddmin`, all score 1.00. Both paired contrasts are
delta 0.0 at n=3.

That is a null, and it is reported as one. With the corrected instrument the
scorer now separates a reader from an echoer on authored policies, so the
zero is no longer a zero from an instrument that could not produce a
positive. It is a zero about the acquired model policies, which named
`seed-sw-ddmin` under both verdict exposures and so did not re-route.

Two limits on what this run can support, both structural:

- Two clusters exist in the frozen panel under the `(family, template)`
  rule, so the minimum two-sided sign-sweep p-value is 1/2 and
  `required_at_alpha_1_20` is 6. Every inferential claim here is
  descriptive.
- The acquired arm's bytes are not an authored acquisition. The
  `acquired` arm compares model output against a stand-in control, and
  `control_distinct` in the live lane refuses on 3 tasks whose strategies
  return equal-size candidates. This re-run did not re-measure that and
  does not speak to it.

## Cost, in the four currencies

| currency | value |
|---|---|
| dispatch allowance | cap sheet 19 physical sends; 13 spent (12 constructions, 1 route probe) |
| internal reservation | 29,566 estimated-budget units against 47,006 allowed, headroom 17,440 |
| provider billing | 10 REPORTED, 3 UNCERTAIN, 0 NOT_REPORTED, 0 UNMEASURED; 3,887 input and 7,459 output tokens over 10 model calls |
| held units | 1,000,000 authorized, 22,144 consumed, 7,422 reserved, 977,856 unconsumed |

The three UNCERTAIN operations are the ones that returned
`response_class: lost-response`. Each spent a real request and returned
nothing to bill against. They are uncertain, not zero, and each was retried
once under the declared retry allowance. All 13 operations are priced; none
was skipped for want of a payload.
