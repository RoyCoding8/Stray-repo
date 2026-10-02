# Pass 2 search and repair

Lane `p2-search`. Pass 1 found one live production defect and recorded two
related gaps. This pass was told to chase the generalisation rather than
repeat the search, and to report the honest count.

I found **three material defects**, all live production code, all fixed with
a failing-first regression. Two are the same lock-asymmetry pattern pass 1
named, found in writers pass 1 did not reach. One is the gap pass 1 recorded
and left unowned.

## Findings

| file:line | defect | why it matters to a CLAIM | status |
|---|---|---|---|
| `experiments/ad01/mission.py:446` (`_replace`, deleted) and `:532` (`release_operation`) | The fourth writer of `investigations.in_flight` rewrote the whole column from a list computed by `read_in_flight` on a **separate connection with no lock**. Three sibling writers take `FOR UPDATE`. | Milestone C claims "one mission entry with one resume owner, an enforced freeze". A settled operation that survives its own release reads back as in flight, and a later `resume_operation` restores an effect that already ran. The module's own docstring says that is the double-count it exists to prevent. Live caller `trajectory._s09_mark_incorporated:331`, per incorporated boundary. | **fixed** |
| `experiments/ad01/improve_channel.py:1211` (`_attempts_frozen_write`) | The frozen-write check matched only `ast.Assign` and `ast.AugAssign`. `ast.AnnAssign` (`grant: dict = {}`) and `ast.NamedExpr` (`(grant := x)`) wrote a `FROZEN_FIELDS` entry unchecked. | Milestone A claims "mandatory authority". A candidate revision can write the grant, the authority, or the sealed results through either form. `admit_revision_under_freeze` refuses **before** the bytes run, so the dynamic before/after comparison cannot see a write the static check let past. This is pass 1's finding 3, unowned until now. | **fixed** |
| `src/settlement/authority.py:537` (`take_correction`) | `SELECT ... FOR UPDATE` over `(study_root, decision_key)` locks nothing when the row is absent, which it is on the first correction. Two first corrections to one decision key both read `used = 0` and both admit. | The correction budget is the ceiling on how many times a learner is told it was wrong. Measured: a budget of 1 admitted **2**, and both returned `used: 1`, so the store and the answer disagreed. Live caller `loop._spend_correction:396`, which also reads `used` on a separate connection first. | **fixed** |

### Recorded, not fixed

- **`improve_channel.py:1243` `_targets_frozen` Subscript region.** Pass 1
  recorded this and another lane owns it. **Not present in this worktree**:
  I measured `view["grant"] = {}` returning `False` against `_attempts_frozen_write`
  here. My widening of `_attempts_frozen_write` does not reach it, and my
  regression deliberately does not assert on it, so the two diffs stay
  disjoint. Whoever lands the Subscript fix must re-run
  `tests/test_inv_p2_frozen_write_binding_forms.py`; its third test asserts
  only the Assign and `setattr` forms.
- **`src/settlement/broker.py:1424` `init_dbos` sets `database_url`.** Two tests
  in `tests/test_r02_authority.py` error at setup under installed DBOS 3.0,
  which removed that key. Present at HEAD (`git show HEAD:src/settlement/broker.py`),
  not in my diff, outside my lane. Recorded, not touched.

## The lock-asymmetry sweep

The question: anywhere an owning module takes `FOR UPDATE` or an advisory
lock, is there a **second writer on the same row or table that does not**?

What I checked. Every `FOR UPDATE` and `pg_advisory_lock` in the repository
(11 `FOR UPDATE` sites across `src/settlement/`, plus `experiments/ad01/mission.py`,
`experiments/ad01/selection.py`, `experiments/coord02/experience.py`). Every
`INSERT INTO`/`UPDATE`/`DELETE FROM` in `src/settlement/` grouped by table, to
the owning function, then classified by whether that function runs under
`store.transact()` (which takes the control-row lock at `store.py:270`) or
opens its own connection. Then every `with ... connect(` block in
`src/settlement/` and every `def` in `experiments/ad01/`, checked for writes
that bypass the transaction.

What that produced. Roughly eighty write sites. The overwhelming majority are
helpers invoked under `transact()`, or `ON CONFLICT DO NOTHING` inserts whose
conflict is its own lock, or counter updates keyed by `id = 1` where the
control row already serialises them. Two rows above are genuine
second-writer asymmetries on a column/row another module locks.

What remains unlocked, and why I left it. `artifacts.py:441` purges by digest
under a fresh re-read of `protection_count`; `capabilities.py:63` pins an
attempt under `ON CONFLICT DO NOTHING`; `evidence.py:220` writes a support
cache keyed by claim; `trials.py:91` stamps `supersedes` on a protocol with
`autocommit=True` in `amend_protocol`, which is a two-step read-then-write
across two connections and so has the same shape as the defect I fixed. That
one is a genuine candidate but it is `amend_protocol`'s own authority path, it
is not part of any milestone claim in this batch, and amending a protocol is
an operator action rather than a concurrent one. Recorded rather than fixed,
on the grounds that I could not show it against a CLAIM.

### The shape worth naming

All three of pass 1's and this pass's findings are one pattern, across three
lanes and two repositories-worth of code: **a lock taken on a row the writing
code path may not have created yet, or a read and a write split across two
connections.** `release_operation` read on one connection and wrote on
another. `take_correction` locked a row that does not exist on the first call.
`run._hold_on_mission_entry` (pass 1) read and wrote in one transaction but
without the lock its three siblings take. A census that asks "does this
writer lock?" answers yes for all of them. The census that finds them asks
"do the lock and the read-modify-write cover the same rows, in the same
transaction?".

## Two headline claims, recomputed

Both recomputed from the evidence directories, not from the reports.

**Milestone B, panel power.** `reports/evidence/invr1b8-panel-census/census.json`
claims `graph:dev+transfer` is powered at 6 clusters, ceiling `0.285714`, and
that `required_clusters` is 6. I re-ran `panel_power_verdict()` from source and
diffed it against the shipped census. `required_clusters` 6 vs 6.
`powered_with_positive_ceiling` agrees exactly: `['graph:dev+transfer',
'graph:within+transfer', 'graph:dev+within+transfer']`. `unpowered` agrees,
11 vs 11. `powered_but_blind` empty in both. `graph:dev+transfer` measures
clusters 6, ceiling 0.285714, 6 open rows, min_p 1/32. **Agrees.**

One wording discrepancy, not a number error. The batch brief says
"`graph:dev+transfer` is the only powered panel". The census and every report
say **three** panels are powered, and `graph:dev+transfer` is the *smallest*
of the three, which is why B13 and B14 name it. `b8-panel.md:76` states this
correctly ("Three combinations reach it, and the smallest of them...").
`b13b-replseed.md:123` says "the only powered panel" and is the one place the
shorter phrase survives. Recorded; I did not edit another lane's report.

**Milestone B, B12 acquisition.** `reports/evidence/invr1b12-swe/` claims B12
acquired 0 of 4 lineages and says so. Recomputed from the artifacts:
`summary.acquired_lineages` 0, `independent_acquired_lineages` 0,
`distinct_acquisition_digests` 0, `lineages_attempted` 4,
`no_acquisition_lineages` 4. Every one of the four `lineages[i].acquisition_digest`
is `null`. All four `use.json` rows read `outcome: no-acquisition` with the
defect named (`already-spent` x3, `loader-refused` x1). Dispatch accounting
reconciles: 5 construction dispatches, 5 physical sends, 5 operations and 5
receipts in `store-rows.json`, `operations_not_accounted_by_a_lineage_row` is
empty with an explanation for the 2 unaccounted sends. **Agrees, and the zero
is a stated zero rather than a missing one.**

I also recomputed the retention leg as a cross-check:
`invr1b14-retention/retention.json` claims 0 of 3 live-acquired members
measurable over 27 executions. Recomputed: 3 members x 9 rows = 27, and each
member's `distinct_verdicts` is `["preserved"]` with
`retained_method_leg_measurable: false`. **Agrees.** (The strategy arms show
`ok-incumbent` in their `reason` on 3 of 36 rows, but `distinct_verdicts` is
`["preserved"]` on all four, so `strategy_measurable: 0` holds as reported.)

## Regression tests

| test | watches what fail |
|---|---|
| `tests/test_inv_p2_mission_release_lock.py` `test_two_concurrent_releases_keep_each_others_operations` | two concurrent `release_operation` calls on one entry; before the fix the first settled attempt reads back still present |
| `tests/test_inv_p2_frozen_write_binding_forms.py` `test_an_annotated_binding_of_a_frozen_field_is_a_frozen_write` | `ast.AnnAssign` writing a frozen field |
| `tests/test_inv_p2_frozen_write_binding_forms.py` `test_a_walrus_binding_of_a_frozen_field_is_a_frozen_write` | `ast.NamedExpr` writing a frozen field |
| `tests/test_inv_p2_frozen_write_binding_forms.py` `test_the_freeze_still_admits_a_reader_and_still_refuses_the_plain_forms` | the widening did not become a blanket refusal; distinguishes a correct widening from "refuse everything" |
| `tests/test_inv_p2_correction_budget_race.py` `test_two_concurrent_first_corrections_do_not_both_spend_the_budget` | two concurrent first corrections to one decision key; before the fix a budget of 1 admitted 2 |

All three are real PostgreSQL with real threads and a `threading.Barrier`, not
a mocked scheduler, because the race is a property of the transaction. Each
was watched failing before the fix. The correction-budget failure printed
`[True, True]`; the release failure printed
`['att-ad01-w0-I-83-0', 'att-ad01-w0-I-83-2']` against an expected
`['att-ad01-w0-I-83-2']`; the two binding tests both raised
`an annotated binding of a frozen field passed the freeze` and its walrus
equivalent.

The tamper-test discipline the brief asks for: the correction-budget test is
a countercheck against a clean baseline in the sense that matters here. Its
baseline is the store's own durable counter, and it asserts
`int(durable["used"]) == len(admitted)` as well as `len(admitted) == 1`. The
pre-fix failure showed why both are needed: the store held `used = 1` while
two callers were admitted, so a test that checked only the counter would have
passed against a real defect.

## Exact pytest summaries

Command for every line below (real PostgreSQL, WSL, `ubuntu` user):

```
wsl -d Ubuntu -u ubuntu -- bash -lc 'mkdir -p /home/ubuntu/claims;
  export SETTLEMENT_CLAIM_LEDGER=/home/ubuntu/claims/p2.jsonl;
  cd /mnt/d/AI/Agent-Society-v2/.worktrees/p2-search &&
  PYTHONPATH=/mnt/d/AI/Agent-Society-v2/.worktrees/p2-search/src
  timeout 1500 /home/ubuntu/.venvs/as9/bin/python -m pytest <files>
  -q -p no:cacheprovider -rs'
```

| file set | summary |
|---|---|
| `tests/test_inv_p2_mission_release_lock.py` (after fix) | `1 passed in 20.73s` (with the C6 and P1 neighbours) |
| `tests/test_inv_p2_frozen_write_binding_forms.py` `+ test_inv_c4_inheritable_construction.py` | `16 passed in 3.94s` |
| `tests/test_inv_p2_correction_budget_race.py` `+ test_invc2_correction_budget.py` | `2 passed in 21.25s` |
| the three new files together | `5 passed in 13.52s` |
| `test_r02_authority.py` | `18 passed, 2 deselected in 23.42s` — the 2 deselected are the pre-existing DBOS 3.0 errors, recorded above |
| all milestone neighbours: C4, C6, C7, A4b, B13b, P1, C2, R02 | `67 passed, 2 errors in 80.13s` — the 2 errors are the pre-existing DBOS ones |

**Zero skips reported in any run.** `-rs` was on every invocation. The 2
errors are collection-time fixture failures in `tests/test_r02_authority.py`,
not skips, and they reproduce at HEAD without my diff.

## Evidence immutability

```
git diff --name-only f919431 HEAD -- reports/evidence/
```
is empty. No file under `reports/evidence/` was read-modified, moved, or
overwritten. Both discrepancy findings above were recorded here instead.

## Not found

Recorded so a later pass does not re-sweep them. No `pytest.skip`,
`xfail`, or conditional skip in `src/` or `experiments/` — the `xfail` hits
in `m1_behaviour_gate.py` are a counter that *refuses* a run carrying skips, not
a marker. No `except: pass` or exception-swallowed-to-value in `src/` or
`experiments/`. The `or 0` accounting collapses in `records.py:581` and
`representation/acquire/campaign.py:328` both report unknown usage as zero in
a way the surrounding evidence already names as a discrepancy
(`invl02-swe/accounting.billed = "null on every receipt"`), and
`records.py:578` guards on `usage.get("billed")` before adding, so the zero
only lands on a receipt that claims to be billed. `campaign.py:331` gates the
same way on `usage.get("billed", False)`. Recorded, not fixed: neither is on a
claim in this batch, and both are in paths a fixture-only lane owns.