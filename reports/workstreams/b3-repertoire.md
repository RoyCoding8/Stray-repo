# B3: the repertoire admits a method acquired on a prior task

## What this lane was for

`RETENTION_BLOCKER` named two things as necessary and neither existed
(`experiments/ad01/w2_retention_campaign.py:176-200`): a repertoire that
admits a method acquired on a prior task, and a reducer whose verdict can
vary. Section (d) of `reports/workstreams/inv-b.md` measured the defect as
`repertoire_closed: true`, `distinct_eligible_sets` of length 1, and
`retained_method_leg_measurable: false`.

**Both were delivered.**

## The two pieces

### Piece one, the arrival path

`assessment_profile.Repertoire` carries arrived members beside the authored
seeds, and `AcquiredMember.admit` decides per task whether one may be
named. `e2_replication.eligible_for(target, repertoire)` derives the
eligible set from the repertoire in hand.

Three refusals are stated at the type rather than at a call site:

- a member is refused on the task it was acquired on, because retention
  means a prior task and admitting it there would let a contrast label a
  cold acquisition's own result as reuse of itself;
- a member may not claim the `seed-` or `ctl-` namespace, for the reasons
  `seeds._KNOWN` and `control_arm.ID_PREFIX` already exist for;
- a member's bytes must pass `method_exec.verify_member`, which is called
  rather than reimplemented, so a member the executor would refuse never
  reaches an eligible list.

The arrived member executes through `method_source` and `entry` beside its
id, because `_resolve_method` resolves a bare `method_id` through the seed
table alone and that function is not this lane's to edit. This is the route
`trajectory._use_retained_method` and every `control_arm` member take.

The seeds stay first and in their own order. `PROMPTED_SHAPE_READER` reads
no further than `eligible[1]`, so appending is what keeps every existing
policy's behaviour identical when a member is present.

### Piece two, a reducer whose verdict can vary

`w2_retention_campaign.retained_leg_verdict(member, authority=)` executes
the member's own bytes through `method_exec.run_member_out_of_process` on
every frozen task in its family and reports the leg measurable only when
the verdicts differ. It refuses without a store, an allocation and an
operation identity, because the executor refuses any execution without
them and a leg reported measurable without an execution was not measured.

The distinction matters and is asserted: a member returning its input is
`preserved` on every task, because the incumbent is preserved by
definition. Admitting it would open the repertoire and leave the leg
exactly as unmeasurable. The test asserts `preserved` only for that member
and `not_preserved, preserved` for the carried one.

## What did not change

`default_repertoire()` still returns exactly the four authored seed ids.
`eligible_for(target)` with no repertoire still returns exactly the two
controls for the family. `method_ids_for` is unchanged, so the panel power
census did not move.

This was measured rather than argued. The single-argument `eligible_for`
was called on all eighteen frozen tasks at `35ba5e9` and at this tip, and
the two JSON payloads are byte-identical: same `default_repertoire`, same
per-task eligible lists, same `closure_default` of
`repertoire_closed: true` with `eligible_counts: [2]`.

**So `tests/test_ad01_w2_retention.py:71-72` still passes unedited.** The
closure genuinely still holds for the cases it was written for, which were
the authored seeds alone, and it was left alone.

## The two B8 tests, updated deliberately

B8 left `test_the_repertoire_is_still_closed_so_opening_it_cannot_happen_
silently` and `test_a_powered_panel_does_not_move_the_retained_method_leg`
failing by design if the repertoire opened. Opening it is this change, so
both were rewritten in this commit rather than deleted:

- the first now asserts both halves. The authored seeds alone are still
  closed, which is what every archived run reproduced, and the four stale
  archives are named.
- the second became
  `test_the_power_census_is_unaffected_by_which_repertoire_a_run_holds`,
  which asserts `method_ids_for` is still the seeds on both families. That
  is the measurement B8's distinction rested on: its census ran over the
  authored grid, so admitting a member could not move a ceiling.

Neither was weakened. Each asserts something that would fail if the wrong
repair were made.

## The four archived reports whose description went stale

Recorded, not edited. All four are immutable history and
`git diff --name-only 35ba5e9 -- reports/evidence/` is empty.

- `reports/evidence/invr1w2retention/report.json`
- `reports/evidence/invr1w2retentionr2/report.json`
- `reports/evidence/invr1w2retention-census/report.json`
- `reports/evidence/invr1b8-panel-census/census.json`

Each read `repertoire_closed: true`, `distinct_eligible_sets` of length 1,
or `retained_method_leg_measurable: false`. Those are true measurements of
the world at `35ba5e9`. `RETENTION_BLOCKER["archived_in"]` now names all
four, and the block's own text is deliberately unedited so a reader
comparing an archive against the present source finds a quotation of what
was repaired rather than a silence.

The census artifact is named in `tests/test_inv_b8_panel_power.py`, which
asserts the list rather than leaving it in a docstring.

## Gate

Real PostgreSQL, WSL, `ubuntu`, claim ledger `/home/ubuntu/claims/b3.jsonl`.

```
tests/test_inv_b3_repertoire.py tests/test_ad01_w2_retention.py tests/test_inv_b8_panel_power.py
1 failed, 64 passed in 349.19s (0:05:49)
S09ISO: dropped 13 database(s) for this run
```

The one failure is
`tests/test_ad01_w2_retention.py::test_both_w2_panels_run_on_a_family_the_
gate_can_read`, and it is pre-existing. `qualification_census()` reports
`readable: 0` at `35ba5e9` too, with an identical assertion and an
identical gate dict. The two owned files at base give
`1 failed, 46 passed`; with this lane's tests they give
`1 failed, 64 passed`. Reproduced in a clean `git archive 35ba5e9` tree,
not inferred.

## Neighbour files that read what changed

`test_inv_b13b_replseed`, `test_s09_e2_scored`, `test_m1_shared_executor`,
`test_inv_a_action_meaning` all use the single-argument `eligible_for` or
read `PROFILES`. Both give `21 failed, 84 passed` at base and at tip, and
the 21 failure ids are identical, diffed line by line.

Those 21 are the pre-existing conditions this lane was told about, not
mine, and are not chased here.

## Honest limits

- The fixture's bytes were written in the test, so their `origin` is
  `fixture-stand-in` and the label is the claim. No live provider wrote
  them. What the fixture proves is the mechanism and the varying verdict,
  which is what B3 was asked to prove offline.
- Opening the repertoire makes the `reuse` decision expressible in
  `method_id`. It does not make a contrast run. B14 still needs a live
  route (B11), a run that acquires a member and hands a later task a
  repertoire holding it, and the adaptation pairing that produced
  `n_pairs: 0`. This lane unblocks it; it does not close it.
- `retained_leg_verdict` executes eight staged runs per member. It is a
  census with real execution, not an analytic argument, and it is the
  reason the offline lane needs a disposable store.
