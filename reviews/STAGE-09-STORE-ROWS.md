# Stage 09 store rows: A4, C3, C8, C13

Four rows were referred for reproduction and repair. One is a real defect and is
fixed. Three were already closed, or are not defects, and the reason is recorded
here with the evidence rather than a commit message that says so.

Two of the three were referred against a description of the code that no longer
matches the tree. The line numbers in the referrals had moved, and in one case
the named line had been deleted outright. That is not a quibble. A row that says
"line 845 does `int(bundle["dispatch_count"])`" and gets re-litigated every pass
because nobody checks whether it is still true costs a lane the same
investigation twice. Each row below states what the tree actually says, and the
reproduction is against the tree.

Nothing under `reports/evidence/` was modified. Nothing contacted a gateway. The
`ec02test_live` database was never named. No `r03flow_*` database was dropped.

---

## C3 — fixed. The count was the whole table, not the run

**The defect was real and is closed at `13d304c`.**

`store_witness` in `experiments/ad01/s09_e3_selection.py` reported
`operations_written_by_the_run` as the difference between two
`SELECT count(*) FROM operations` totals, one taken before the run and one
after. A table total is every writer in the interval between two snapshots, and
this store is shared across lanes. Any operation committed inside that interval
by another process is charged to this run.

**Root cause, by reading.** The function being called, `_operation_count`, took
no argument naming a run, so it could not scope its answer even in principle. The
question the field claims to answer — how many operations did *this* run write —
is not a question a table total can answer, because the table has no notion of a
run. The run's identity is in its operation ids, and they were being ignored.

**Which key bounds a run.** Two candidates were named in the referral. The
receipt's operation id is the right one. `DecisionRecorder._operation_id` mints
`ad01-<campaign>-op<seq>-<target>-<capability>-<queries>`, and
`selection._default_campaign` is uuid-derived per run, so no other run can
produce one of this run's ids. The command journal's `request_id` cannot bound a
run: the recorder builds a fresh uuid per settlement call
(`DecisionRecorder._authorize`), so a request id bounds a call.

**Measured, not argued.** One operation row inserted by another writer between
the two snapshots, on a disposable database:

    PASS 1  decisions_made      = 5
    PASS 1  written_by_the_run  = 5
    PASS 2  a second run with the alien present reports wrote = 6
    PASS 2  that run's own operation_ids = 5
    VERDICT UNSCOPED: the count moved by a row the run never wrote

**Why the upward direction is the dangerous one.** `test_s09_e3_sever` requires
this count to equal the run's decision count. A foreign row inflates it and fails
a correct run, which is noisy and gets looked at. A run that made one fewer
decision than its neighbour has its difference supplied by another writer's row
and passes, having written no operation for that decision. An over-count is
loud; an under-counted decision is quiet.

**Red before green.** The first version of the test went green against the
unscoped count, because it inserted the foreign row outside the measurement
window. That is worth recording: the test asserted something true and proved
nothing. Wrapping `run_policy` places the commit where a concurrent lane's lands.

    AssertionError: the run made 5 decisions and reported 6 operations, with a
    concurrent writer's row inside the measurement window
    assert 6 == 5

**The fix can fail.** The scope clause was removed, restoring the whole-table
count. The mutation was confirmed landed by grep before running.

    AssertionError: assert 5 == 0
     +  where 5 = <function _operations_for_ids>(dsn, ['no-such-operation'])
    2 failed, 1 passed

Restored: 3 passed. The 13 pre-existing tests in `test_s09_e3_sever.py`, which
compare this field against the decision count, still pass.

---

## A4 — already closed, and the stronger rule is wrong here

**The factual claim in the referral is true and the conclusion drawn from it is
not.** `_provenance_attested` has exactly one caller in `src/`, at
`store.py:505`, inside `_never_sent_proof`. It is never called from
`admit_receipt`. The referral is correct about the surface.

What is also true is that the admission half was already repaired. `_validate_receipt`
at `store.py:1822` requires a non-blank `provenance` for **every** outcome, not
only `failure`, and `migrations/0018_receipt_provenance.sql` added a `provenance`
column to `receipts` so each admitted row carries its own rather than the
last-writer-wins value on the operation. `tests/test_s09_n302_provenance.py`
passes 6/6 at HEAD.

**The stronger rule — holding a receipt's provenance to the operation's
`launcher_id` — was measured, and it breaks real dispatch paths.** I re-ran that
measurement rather than inheriting it, driving each of the three real broker
routes and reading back the `launcher_id` the store actually recorded:

    gateway  provenance=gateway                  launcher_id=gateway        rule_would_ACCEPT
    inline   provenance=broker-inline            launcher_id=broker-inline  rule_would_ACCEPT
    inline   provenance=broker                   launcher_id=broker-inline  rule_would_REFUSE
    inline   provenance=broker-fence             launcher_id=broker-inline  rule_would_REFUSE
    local    provenance=local-1-recovery         launcher_id=local-1        rule_would_REFUSE
    local    provenance=local-1:prove_never_sent  launcher_id=local-1        rule_would_ACCEPT

This corrects the record in `test_s09_n302_provenance.py`, which says all five
broker vocabularies arrive on operations whose `launcher_id` is not the
provenance. Two of them (`gateway`, `broker-inline`) arrive on operations whose
`launcher_id` is exactly that string, because `broker.py:663` and `broker.py:809`
admit with those ids. Three would be refused: `broker` and `broker-fence`, which
are written on an inline operation, and `<launcher>-recovery`.

I then enforced the rule in `_validate_receipt` and ran the controls file, whose
docstring names N-43/N-47/N-48 as the controls it holds. Baseline 23 passed.

    FAILED test_a_fenced_unknown_and_a_decided_receipt_both_survive_on_one_operation
    FAILED test_a_consumer_reading_only_the_first_receipt_reads_the_fence_not_the_decision
    FAILED test_c_delivered_outbox_strands_the_operation_for_every_dispatch_pending_pass
    FAILED test_c_the_stranding_reproduction_is_now_unreachable
    FAILED test_c_an_unbacked_reset_is_now_refused_and_the_stall_is_unreachable
    5 failed, 18 passed in 66.09s

**The store was restored and the mutation confirmed gone by grep.** The working
tree carries no trace of the experiment.

**What `_provenance_attested` should protect, and where the rule belongs.**

It protects a *never-sent proof*, and it is correct there. A proof is a claim
about something that did not happen, made by whoever was given the work; a proof
aimed at a different launcher was not produced by the one that was given it, and
an operation admitted to no launcher has nothing that could attest for it. The
proof's consequence is large: consuming one releases a reservation and returns
the operation to `prepared`, the state a second execution starts from. So the
proof is held to the admitted launcher, and then held again to a capability the
admitted launcher minted, because a launcher id is caller-readable and a
capability is an HMAC over a secret.

A receipt is a different claim. It is a *report of what happened*, and a report
has more than one legitimate author. The gateway writes a `success` receipt for
an inference it performed. The broker writes `broker-inline` for work it ran
itself, and writes `broker` and `broker-fence` on that same operation to record a
lost response and a generation fence. None of these is a launcher, and none
should be: they are the components doing the reporting. Requiring a receipt's
provenance to name the operation's `launcher_id` would assert that only the
launcher ever reports on the work, which is false, and would refuse the fence
receipt that the stranded-dispatch recovery depends on.

The store also cannot ask who wrote a receipt. It holds a string the caller
supplied. So the part of N-302 the store can establish is the part that is
enforced: a receipt names someone. The identity behind that name is a judgement
about the caller, and the file that settles N-302 says so in terms rather than
pretending otherwise.

**Enforcement belongs in `_validate_receipt`, where it already is.** Not in
`admit_receipt`, which composes validation with persistence, and not in
`attestation.py`, which holds a launcher-keyed capability registry that has
nothing to say about receipts. I did not change the code here: the rule is
present, it is at the right layer, and the stronger alternative is measurably
wrong.

**One thing the referral gets right and the tree does not do.** The durability
half of N-302 was genuinely open at some point. It is closed now
(`migrations/0018_receipt_provenance.sql`), and
`test_each_receipt_row_carries_its_own_provenance` pins it.

---

## C8 — already closed at both sites

**The named line no longer exists.** At `c7d2952` the file was shorter and line
845 was inside `_parse_ledger_arithmetic`. At `b74f216` line 845 is
`def _dispatch_count(value: Any) -> int | str:` — the function that *is* the fix.
At HEAD it is a field assignment in `resume_dispatch_budget`. There is no
`int(bundle["dispatch_count"])` in the file.

Both sites the original row could have meant are fixed, by `b74f216`:

- `_r4_study` reads it through `_dispatch_count`, which passes a nonnegative
  count through as `int` and anything else through as the string it wrote.
- `_settled_study` reads `candidate_view.dispatch_count` the same way. This is
  the reachable half: `candidate_view` is the key
  `_OutputDispatchAccounting.candidate_fields` writes `"unknown"` into.

`tests/test_c8_unreconciled_dispatch_count.py` passes 6/6, and
`tests/test_s09_exposure_ledger.py` passes alongside it, 26 total in 0.57s. No
committed bundle carries the value yet, which is why the crash was latent when it
was reported and why it is still latent: `_r4_study(ROOT, None).max_dispatch_claims
== 1` and `dispatch_count_disputed is True` both hold at HEAD.

**What a caller should do with an unmeasurable count: carry it, and do not let
it become a number.** Refusing is defensible and the file does it elsewhere
(`launch_plan` refuses when a half cannot be stated), but refusing is wrong *here*
for a specific reason. The count's job is to be compared against the durable
store's. If a bundle declines to state its count and the ledger refuses to
report, the one artifact the study has is suppressed and the operator is left
with less than they started with. The store's figure is still readable and is
still the one to trust. The claim propagates so both positions are on the record
and the reader can see which one is a number.

The dangerous repair is the obvious one. Coercing `"unknown"` to `0` would enter
`max_dispatch_claims`, which is the figure a ceiling may be read from, and a
zero from a file that knows nothing would outrank the store's real count. The
file gets this right in three places and the reason is load-bearing:

- `DispatchClaim.counted` returns `None` for a non-int, so the value is excluded
  from the max rather than counted as zero.
- `dispatch_count_disputed` counts only counted claims, so one position being
  unknown is not two positions and does not manufacture a conflict saying the
  reservation "may understate real sends".
- `max_dispatch_claims` returns `0` for an all-unknown set, and the docstring
  says why that is not the same as coercing: no source claiming a count is not
  evidence of a send. An empty max is a floor on a ceiling, which is the safe
  direction, because it under-claims rather than over-claims.

This is the same four-currency discipline the brief described, and it is already
in place: `ProviderCharge` makes an absence a state, `already_spent_in_store`
returns `None`, and `offline_recompute` carries the string through. The ledger
agrees with itself.

---

## C13 — not a defect, and the audit holds

**The asymmetry is real in the source and has no instance.** `store.py:2413`,
`:2428` and `:2439`, `context.py:1140`, `agenda.py:158` and `:211` all read
`dispatch_state IN ('dispatching', 'sent', 'unresolved')`. `reset_dispatch` at
`store.py:2163` accepts only `('dispatching', 'unresolved')`.

I re-derived the census rather than inheriting it.

- Every `dispatch_state` writer in `src/`, read line by line: `dispatching`
  (1733), `unresolved` (2008, 2038, 2105), `cancelled` (2121), `prepared`
  (1701, 2188), `observed` (2052), `reconciled` (2326, 2335). The two
  parameterized writers resolve to closed two-value sets computed on the line
  above. `sent` is assigned nowhere.
- `git log --all -S"dispatch_state = 'sent'"` returns only `f0b17be`, the commit
  that wrote the audit. No revision on any ref ever assigned the literal.
- A census of every local database, excluding `r03flow_*`:

      databases scanned: 708 hits: 0

**So the premise of the row, "a dispatch can be reset into a state the
reconciliation query will not see", cannot occur.** `reset_dispatch` cannot reset
*into* any state; it resets *out* of `dispatching`/`unresolved` into `prepared`,
and `prepared` is not in the readers' set by design — a prepared operation is
pending work, not stranded exposure. The row has the direction backwards. The
narrowing in `reset_dispatch` is the fail-closed half and it agrees with
`reconcile_operation:2296`, which gates the same `reconciled` resolution on the
same pair for the same reason: a `never_sent_proof` is only admissible when
nothing was sent.

**Two cosmetic items remain**, both from `reviews/STAGE-09-C13-AUDIT.md` §4 and
both real:

- `store.py:2164` raises `"is {state}, not dispatching"` while accepting two
  states. The message misreports the accepted set.
- `tests/test_s09_n202_resend.py:174` asserts `state in ("sent", "observed")`
  where the value is always `observed`. The `"sent"` arm is dead and keeps the
  ghost state in the test surface.

I did not apply either. The first is a message in `src/settlement/store.py`,
which I own, and it is a one-line change; I left it because neither is a defect
and the row is not mine to close. **This is a recommendation, not an omission**,
and it should be taken or declined deliberately.

---

## What I found and did not fix

**The referral's line numbers are stale for all four rows.** Line 845 in
`s09_exposure_ledger.py` has held three different statements across three
commits, and the `int()` cast it named is gone. `store.py:2382` and
`store.py:2164` in C13's row do not point at the reconciliation query and the
error message respectively. A row whose coordinates have drifted will be
re-investigated every pass. TASKS.md already records the corrected status for C8
and C13; A4's row still says `OPEN` and is wrong to.

**A4's own test file carries a claim this pass refutes.** The docstring of
`tests/test_s09_n302_provenance.py` says all five broker receipt vocabularies
arrive on operations whose `launcher_id` is not the provenance. Two of them do
not. The conclusion it draws is right and the evidence for it is wrong, which is
the more expensive kind of wrong, because the next person to check the evidence
will find the argument does not hold and may re-open a correct fix. The file is
outside my owned paths, so it is reported rather than edited.

**C3's test file, `tests/test_s09_e3_sever.py`, is outside my owned paths** and
I did not edit it. It consumes the field I changed and its 13 tests pass, so no
coordination was needed — but a reader should know the assertion at line 248 is
what made the unscoped count load-bearing rather than merely untidy.

**Two live lanes collided with my staging area during this session.**
`tests/test_coord02_m4_frozen.py` and `experiments/ad01/s09_e3_selection.py`
both appeared in the shared index and the working tree while I worked. I
unstaged the foreign path before committing and verified my own diff contained
only my change, so `13d304c` names two files and both are mine. The shared index
is a live hazard for any lane committing here.
