# Stage 09 r4 reproduction review

**Disposition: the campaign suite is NOT green on this host, and the tamper-test baseline is not established.**

Reviewed tree: `wt/r4-repro` at `dd504e1`, worktree
`/home/ubuntu/AI/Agent-Society-v2/.worktrees/r4-repro`.
Scope: reproduction of the campaign-suite headline, gate integrity, and whether
the reported results are reproducible. Read-only. No source, test or evidence
file was modified. `git status --porcelain` is empty after this review except
for this file.

The handoff states: "The worker reports 691 passed, one skipped and one xfailed
at the reviewed delivery. The reviewer verified the source findings below and the
unchanged historical M3 bundle, but did not independently rerun that suite."
That gap is the subject of this review.

## Verdict summary

| Question | Answer |
|---|---|
| Does `691 passed, 1 skipped, 1 xfailed` reproduce? | **No.** The one run that completed gave **607 passed, 1 failed, 1 skipped, 1 xfailed** over 609 tests, in 81 minutes against a claimed 15m19s. |
| How many of the 693 campaign tests exercised a database? | **194 of 693** (28%). 499 collected nothing. |
| Do all 7 required tamper examples reject? | **5 of 7 reject** against the M4 demo baseline. Two accept a tampered bundle. |
| Is the r4 evidence bundle a green tamper baseline? | **No.** It fails verification before any tampering, so its rejections are uninformative. |
| Is the census vacuous? | **No.** It has a live witness and the ceiling gate bites. |
| Is the xfail honest? | **Yes.** Verified in both directions by removing the store rule. |
| Does 5563 = 3269 + 2294? | **Yes**, and both recomputations are arithmetically right. |

**One environment caveat that applies to every timing number below.** This is a
2-core box with 7 GB RAM and no swap, held at load average 15-21 and
`/proc/pressure/cpu` `some avg10` above 90 for the entire measurement window by
unrelated agent worktrees. The completed run burned `user 3m49s` plus
`sys 0m45s`, so 4.6 minutes of CPU across `real 81m21s`, starved rather than
CPU-bound by a factor of about 18. I can report what the suite did here. I
cannot convert these wall times into the suite's intrinsic cost, and the prior
15m19s figure is not contradicted by mine once that factor is accounted for.

---

## 1. The headline does not reproduce

### How the suite is actually invoked

There is no runner script, tox file or Makefile. `pyproject.toml:26-27` sets only
`testpaths = ["tests"]`. `reports/VERIFICATION.md:7-12` records the historical
invocation shape, `SETTLEMENT_TEST_DSN=... uv run pytest tests/ -q`, and
`reports/STAGE-09-BOSS-STATUS.md` never states the command behind `691`.

`691 + 1 skipped + 1 xfailed = 693`, and the `test_s09*.py` glob collects
**exactly 693** tests. So "the campaign suite" is the `test_s09*` file glob, not
`tests/`. The whole tree collects 3008. Anything reading "691" as a full-suite
result is reading 23% of it.

### Run 1: campaign suite, DSNs unset, 25-minute budget

```
env -u SETTLEMENT_TEST_DSN -u SETTLEMENT_TEST_TRUNCATE_DSN -u INV_B1_DSN \
  PYTHONPATH=.:src:experiments pytest tests/test_s09*.py -q -p no:cacheprovider -rfsxX
```

Result: **`EXIT=124` (timeout) at 31% after 25 minutes.** No summary line. Given
the completed run in the next section took 81 minutes on this host, a 25-minute
budget was never going to finish it. That budget was mine, not the worker's,
and the timeout says nothing about the suite. A timeout is not green.

The environment is a real confound and is quantified in the verdict summary
above. The process used 58 s of CPU across 21 minutes of elapsed time, and
`/proc/pressure/cpu` read `some avg10=93.18`, so it was starved rather than
spinning.

### Run 2: campaign suite minus the slow gate, completed

Deselecting `test_s09_merged_tip_regression.py` (the ~2-minute gate, see
finding F-8), the run completed and printed a full summary:

```
1 failed, 607 passed, 1 skipped, 84 deselected, 1 xfailed in 4865.00s (1:21:04)
```

**Correction to my first report.** I initially read the output file while the
run was still writing and recorded it as killed at 95%. That was wrong. The
run completed, 81 minutes later, and the `exited with code 0` on the wrapper
was its `time` builtin, not pytest. The completed result is above and it is
the one to use.

**Count reconciliation.** `693` collected in the campaign glob, minus the `84`
tests in the deselected regression-gate file, gives `609`. The summary reports
`607 passed + 1 failed + 1 xfailed` = `609`. Exact match, so nothing else was
dropped. My `-k "not isolated"` was a no-op: the only four tests matching
"isolated" by name live in `test_eng_invb_dispatch.py`, `test_s2_artifacts.py`,
`test_team_runtime.py` and `test_team_world.py`, none of which are in the
campaign glob.

**Timing.** `real 81m21s` against `user 3m49s` and `sys 0m45s`, so 4.6 minutes
of CPU in total. The claimed `919.76s (0:15:19)` is about 5.3 times faster in
wall time. Given the sustained load documented above, the claimed duration is
plausible on an idle host and my run does not disprove it. I am not claiming
the 15m19s is wrong.

**What the completed run establishes.** The result is **red**, with one failure:

- `1 failed` is `test_s09_verdict.py::test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run`
  (F-2), reproduced here in a full-file run, confirming the order-dependence
  against a near-complete campaign suite and not only in my narrow bisection.
- `1 skipped` is `test_s09_durable_state.py:31`, the loud module-level skip
  (F-4). Its 5 tests did not run, and the skip names both missing DSNs, which
  is the intended behaviour.
- `1 xfailed` is `test_s09c1_continuity.py::test_settled_receipt_stays_attributable_on_empty_text`,
  the expected strict xfail.

So even with the DB-skip gate removed from the set, the campaign suite is not
green on this host, and the single failure is the one that makes the published
`mechanism: true` verdict host-dependent.

**Three orphan databases.** The run left three `s09iso_*` per-run databases
behind:

```
s09iso_c11956ebf18c_d3a909bfb123
s09iso_cycle_63f88cebfbf4
s09iso_persist_a1b79ec58da4
```

The module-scoped `store` fixtures create these in setup and drop them in
teardown. They survive here because the process was terminated by host
pressure partway through rather than exiting normally, so teardown for the
files still in flight never ran. This is the fixture behaving as designed under
an abnormal exit, not a defect in it.

I did **not** drop them, because the assignment forbids me from creating or
dropping any PostgreSQL database. They are mine and someone should remove them.

### What the failures are

Two distinct failures, both real, neither database-related.

**F-1. `test_db_skip_is_visible_not_silent` fails when DSNs are unset.**
`tests/test_s09_merged_tip_regression.py:347`. This is the gate working exactly
as designed. The report's claim at
`reports/STAGE-09-BOSS-STATUS.md:860-862` is correct on this point: "with both
DSNs set it skips with the database it ran against named, and without them it
fails rather than letting a naive count report the suite green." The claimed
`1 skipped` is therefore the both-DSNs-set branch, which means the run behind
`691` did point at a real database. With DSNs unset the same test is a failure,
which is what I observed.

**F-2. `test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run` fails,
CONFIRMED, order-dependent.**

```
tests/test_s09_verdict.py::test_the_mechanism_verdict_can_be_computed_from_a_real_suite_run
E  AssertionError: assert 'unproven' == 'true'
```

Bisected precisely:

| Invocation | Result |
|---|---|
| `tests/test_s09_verdict.py` alone | **25 passed** |
| `tests/test_s09_vocabulary_census.py` + `test_s09_verdict.py` | **31 passed** |
| `tests/test_s09_frozen_at.py` + `test_s09_verdict.py` | **1 failed, 30 passed** |

This is also the single failure in the completed 609-test campaign run in
section 1, where it was not bisected away by any `-k` filter.

`test_s09_frozen_at.py` is the trigger. The verdict test
(`tests/test_s09_verdict.py:421`) recomputes a subprocess suite per
representation (`experiments/ad01/s09_verdict.py:391-407`) and requires all
three green. The three representation suites pass when I run them directly
(action_graph 12, policy_ast 47, step 10, all `green=True`). But
`tests/test_boolean_ast_arm.py` is red on this box:

```
tests/test_boolean_ast_arm.py::test_a_failing_ast_step_becomes_a_legal_recorded_stop
E  AssertionError: assert 'list index is out of range' in 'wall timeout after 1000 ms'
```

That test asserts on a specific exception string from a forked subprocess
bounded by a hard 1000 ms wall clock
(`experiments/ad01/boolean_ast_policy.py:533-539`, `process.communicate(timeout=timeout_ms/1000)`).
Under host load the child is killed before it can raise, and the refusal reason
becomes the timeout instead. Three consecutive direct runs of that file failed
the same way.

**Severity: high, and it undercuts a headline claim.** `reports/STAGE-09-BOSS-STATUS.md:893`
states "M5 is complete" and the verdicts recompute to mechanism `true`. That
claim is only true on an unloaded host. A 1000 ms wall-clock assertion on a
forked interpreter has no load tolerance, so the mechanism verdict is not
reproducible on a shared machine. This is the same class of defect the report
itself flags as a known flake family (`reports/VERIFICATION.md:140-153`), except
here the flake is load-triggered rather than rare, and it propagates into a
published verdict rather than being annotated.

---

## 2. What the suite actually covers

### The intersection is the right shape, and one exemption is wrong

`campaign_test_intersection()` (`tests/test_s09_merged_tip_regression.py:202-233`)
computes 106 test files reaching a campaign module by import edge, direct or
transitive. That mechanism is sound, because transitivity is handled by a proper
worklist and `_imports_of` walks function bodies so body-only imports count.

**Every campaign module has a covering test.** All 32 campaign modules in
`_campaign_modules()` are reached by at least one test in the intersection.
Zero modules uncovered. That is the check that matters and it passes.

**F-3. The two-file "subprocess driven" exemption is half wrong. CONFIRMED, low
severity but a documentation defect in the gate itself.**

`tests/test_s09_merged_tip_regression.py:321-341` declares both
`tests/test_s09_sibling_imports.py` and `tests/test_s09m34_bind.py` exempt
because they "drive fresh subprocesses and name campaign modules as strings or
file paths, so no import edge connects them."

Measured:

| File | Campaign import edges | Exempt claim |
|---|---|---|
| `tests/test_s09_sibling_imports.py` | **none** (imports only `__future__`, `pathlib`, `subprocess`, `sys`) | **accurate** |
| `tests/test_s09m34_bind.py` | **five**: `s09_run_isolation`, `.DB_PREFIX`, `.create_disposable_db`, `.disposable_db`, `.drop_disposable_db` | **inaccurate** |

`test_s09m34_bind.py` is directly in the intersection. The exemption is a
no-op for it. It does no damage, because the gate only subtracts the exempt set
before checking for a non-empty remainder. But the docstring at line 324-328
asserts a false property of the tree, and a reader auditing coverage reasons
from a claim that is wrong. `test_s09_sibling_imports.py` is genuinely exempt
and is still run.

### One campaign test file collects zero tests

**F-4. `tests/test_s09_durable_state.py` defines 5 tests and collects none.
CONFIRMED, medium.**

```
$ pytest tests/test_s09_durable_state.py --collect-only -q
no tests collected in 3.64s
```

Cause: `tests/test_s09_durable_state.py:20-35` calls
`pytest.skip(..., allow_module_level=True)` at import time when either DSN is
unset, and `:49-50` calls `pytest.fail` unless the database name starts with
`s09_durstate_`. It is in `EXPECTED_CAMPAIGN_TEST_FILES` and it passes the
"has real assertions" structural gate, so every gate is green while 5 campaign
tests never execute.

This is the honest direction of a loud skip and I am not calling it a defect in
intent. But it is invisible in the headline. The 693 collected include neither
its 5 tests nor any indicator they were skipped. A reader of "691 passed" cannot
tell that a pinned campaign file contributed zero.

### `test_s09_migrate_callers.py` also collects nothing

Same effect, different cause: it is in `NON_CAMPAIGN_HELPERS` and defines no
`test_` functions, so it is a helper module despite the `test_` prefix. That one
is correct by design and documented at
`tests/test_s09_merged_tip_regression.py:261-272`.

---

## 3. The DB skip, and how much of the suite touches a database

### The loud gate works

`test_db_skip_is_visible_not_silent` does what it claims, in all three states
(`tests/test_s09_merged_tip_regression.py:354-372`):

| DSN state | Behaviour | Observed |
|---|---|---|
| both unset | `pytest.fail` naming the hole | **confirmed**, F-1 |
| only one set | `pytest.fail` naming the half-set pair | code path read |
| both set | `pytest.skip` naming the database | code path read |

So the one skip in the claimed headline is the third row, which means the DSNs
were both set. That is the good news. It means the 691 run did point at a
database.

### How many tests actually exercised one

**194 of the 693 collected campaign tests (28%).** 499 collected nothing
database-shaped.

Measured by which collected test id lives in a file whose test functions request
`store` / `migrated_db` / `dsn` / `db`:

| File | DB tests / defs |
|---|---|
| test_s09c2b_bind.py | 17/19 |
| test_s09o_cycle.py | 12/13 |
| test_s09c1_continuity.py | 10/12 |
| test_s09m2_construct.py | 8/10 |
| test_s09o_policy_assess.py | 8/9 |
| test_s09_study_preflight.py | 6/48 |
| test_s09c2a_actions.py | 6/7 |
| test_s09m1_state.py, test_s09m2_policy.py, test_s09m34_bind.py, test_s09m34_cycle.py, test_s09m34_exposure.py | all defs |
| test_s09durable_state.py | 5/5 (**collected zero**, F-4) |

**Severity: medium, and it is a framing problem rather than a bug.** The
headline "691 passed" reads as campaign-wide coverage. Just over a quarter of
it exercised a database. The durable-state, exposure-ledger and persistence
guaranteies, which are the ones a live round actually rests on, live in a
minority of the run. The `1 skipped` framing in
`reports/STAGE-09-BOSS-STATUS.md:860-865` is honest about the skip but silent
about this ratio.

---

## 4. The xfail is honest in both directions

**No finding. The claim holds.**

`test_settled_receipt_stays_attributable_on_empty_text`
(`tests/test_s09c1_continuity.py:382-410`) is a `strict=True` xfail. Its
companion is `test_empty_text_is_refused_rather_than_settled` at
`tests/test_s09c1_continuity.py:413-446`.

Direction 1, the tree as it stands. The rule exists at
`src/settlement/store.py:1446-1448`:

```python
if outcome == "success" and (
        not isinstance(content.get("text"), str) or not content["text"].strip()):
    raise SettlementError("successful model receipt needs non-empty response text")
```

Result: `1 passed, 1 xfailed`. The companion passes, the xfail xfails.

Direction 2, with the rule removed. I copied `src`, `experiments`, `scripts`,
`migrations` and `tests` to `/tmp/xfailprobe`, deleted exactly those three lines,
and ran the pair. Result was **2 failed**, on both tests, and for the right
reason.

```
tests/test_s09c1_continuity.py:435
E  AssertionError: assert '' is None
E    +  where '' = _receipt_text(...)
```

The empty text now settles, so the companion catches it. Because the xfail is
`strict=True`, a store that starts admitting empty-text successes turns the
suite red rather than passing quietly, which is the property the report claims.
The "both directions checked by removing the store rule in a scratch worktree"
statement at `reports/STAGE-09-BOSS-STATUS.md:863-865` is accurate, and I
reproduced it independently. Scratch copy deleted; tree unmodified.

---

## 5. Tamper-test baseline integrity

This is the most serious section. I ran all seven required rejecting examples
twice, once against the M4 demo baseline from
`tests/test_m4_offline_recompute.py` and once against the checked-in r4
evidence bundle.

### Against the M4 demo baseline

Baseline first, per M4's own rule that "a baseline that already fails cannot
establish a successful tamper test":

```
BASELINE: pass []
```

| # | Required rejecting example | Result | Problem raised |
|---|---|---|---|
| 1 | doubled receipt in a live lineage | **REJECTS** | `multiple-terminal-receipts`, `receipt-lineage-mismatch` |
| 2 | foreign study identity | **ACCEPTS** | none, status `pass` |
| 3 | source substitution | **REJECTS** | `executed-source-not-frozen`, `candidate-record-digest-mismatch` |
| 4 | disconnected policy | **REJECTS** | `executed-source-not-frozen` |
| 5 | hidden-answer contamination | **REJECTS** | `scored-observation-mismatch` |
| 6 | absent usage treated as zero | **ACCEPTS** | none, status `pass` |
| 7 | resumed-count rollback | **REJECTS** | `accounting-tool_queries-mismatch reported=0 recomputed=17` |

**F-5. The M4 verifier does not reject a foreign study identity. CONFIRMED,
high severity.**

`experiments/ad01/offline_recompute.py` verifies identity bytes thoroughly
(`_check_identities` at line 347, `identity-digest-mismatch` at 373) but never
binds the study to an expected value. I set
`freeze["study_id"] = "other-study"` and `freeze["study_root"] =
"other-study-root"`, recomputed `freeze_digest` as the verifier itself does at
line 324, and the bundle returned `pass` with an empty problem list.

Grepping every use of the two fields in the module settles it. `study_id`
appears exactly once, at line 67, and only as a member of the
`FREEZE_REQUIRED` presence list. It is never compared to anything.
`study_root` is compared only on the two hardcoded protocol paths at lines 739
and 1748, and the demo baseline is on neither.

Three-label probe, each with a self-consistent recomputed digest:

| `study_id` / `study_root` | Result |
|---|---|
| `other-study` | **pass**, no problems |
| `attacker-study-xyz` | **pass**, no problems |
| `invl02-live-e12` | `fail`, `authoritative-protocol-missing` |

The third row is the only rejection, and it fires for an unrelated reason, that
a bundle claiming the E12 protocol must then carry the E12 protocol. It is not
an identity check.

The study identity is a self-attested label, not a checked fact. Anything the
caller supplies is accepted. A bundle from a different study, a different
campaign, or a different participant passes verification as long as its
self-consistency holds.

**F-6. Absent usage scored as zero is only caught for one of two accounting
states. CONFIRMED, medium.**

`experiments/ad01/offline_recompute.py:1270-1273`:

```python
if key == "billed_units" and measured == 0 and (
        status != "measured" or not isinstance(source, str) or not source):
    problems.append("billed-unknown-scored-as-zero")
```

This fires only when `measured == 0`. The demo baseline ships
`billed_units = {"measured": "unknown", ...}` and I rewrote it to
`{"measured": 0, "measurement_status": "measured", "source": "..."}`. Result:
`pass`. The verifier has no notion of a usage block that exists in the receipts
but is absent from the accounting, so a report of zero is indistinguishable
from a report of nothing at all.

Full characterisation of the four shapes, each on a self-consistent bundle:

| `billed_units` accounting | Result |
|---|---|
| `measured: 0`, `status: measured`, source present | **pass**, no problems |
| `measured: 0`, `status: unknown`, source present | `fail`, `billed-unknown-scored-as-zero` |
| `measured: 0`, `status: measured`, source empty | `fail`, `billed-unknown-scored-as-zero` |
| `measured: "unknown"`, `status: unresolved` (baseline) | **pass**, no problems |

**Root cause.** M4 evidence records carry no usage block at all. I dumped the
receipt field names and found no `usage` or `cost` key on any M4 receipt, so
there is nothing for the accounting to be cross-checked against. The accounting
block is self-attested in exactly the way the study identity is in F-5.

The adjacent protections are real and do fire, as rows 2 and 3 show. The hole
is the specific shape "claimed measured, value zero, no receipt-level usage to
contradict it", and for a route that reports unknown usage, such as the free
Nemotron route r4 used, that is the shape a dishonest or buggy writer would
most naturally produce.

### Against the r4 evidence bundle

**F-7. The r4 bundle is not a green baseline, so its tamper rejections prove
nothing. CONFIRMED, high severity, and this is M4's own rule violated.**

```
$ python scripts/s09_verify.py reports/evidence/invl02-output-shape-550b-r4
BASELINE r4 output-run.json: fail   (15 problems)
```

The checked-in `reports/evidence/invl02-output-shape-550b-r4/output-run.json`
fails its own verifier before any tampering:

```
bundle-status-invalid
dispatch-budget-mismatch P1-audit / P1-qual / P2-audit / P2-qual
frozen-source-mismatch experiments/ad01/offline_recompute.py
frozen-source-mismatch scripts/invl02_live.py
frozen-source-mismatch src/settlement/gateway_http.py
missing-dispatch P1-audit / P1-qual / P2-audit / P2-qual
p0-control-task-set-mismatch
scorer-private-missing
study-incomplete
```

I confirmed the three `frozen-source-mismatch` entries are real byte drift
rather than a verifier artifact. Recorded versus actual SHA-256:

| Path | Recorded | Actual |
|---|---|---|
| `experiments/ad01/offline_recompute.py` | `2b54e03339151b79...` | `f8e1971a852c4ffd...` |
| `scripts/invl02_live.py` | `8b412fa9e94c78cf...` | `3c5bb59332e8c688...` |
| `src/settlement/gateway_http.py` | `4a811ab57d5edd3b...` | `ef24a8ae09aac35a...` |
| `experiments/ad01/frontier.py`, `live_construct.py`, `boolean_rule.py`, `rule_learner.py` | match | match |

The other three of the eight `OUTPUT_CODE_PATHS`/`OUTPUT_SOURCE_PATHS` still
match, so the tree drifted after the freeze. That is expected for a bundle
three commits old and is not itself a defect; it is what makes the bundle
unusable as a tamper baseline.

Consequence, when I ran all seven examples against this bundle. All seven
"rejected", and the problem list was **byte-identical to the baseline's 15
problems** in every case. They rejected for pre-existing reasons. A tamper test
run against a red baseline demonstrates nothing, which is precisely M4's
stated precondition.

`tests/test_r4_verify_bundle_authority.py` does not catch this. It exercises a
**synthesized** bundle built by `_lost_response_bundle(tmp_path)` and
`_unavailable_with_preflight(tmp_path)`, never the checked-in evidence
directory. So the green suite and the failing artifact coexist without
anything noticing.

**Severity: high.** The r4 evidence bundle is the artifact the whole liability
argument rests on, and it does not pass its own verifier.

---

## 6. Census honesty

**No finding. The census is self-proving, not vacuous.**

The concern is real: `HAZARD_CEILING = 0` over a pattern that no longer exists
anywhere would pass for the wrong reason. It does not, on three counts.

**A live witness exists.** `safety.census()` returns:

```
files_calling_dropdb: 5
files_with_literal_drops: ["test_s09_test_db_safety.py"]
literal_drop_count: 3
literal_database_names: [s09o_pilot_full, s09o_pilot_rerun_a, s09o_pilot_rerun_b]
```

The census file itself is the witness, and it is the *only* file with literals.
The other four destructive files (`test_ag01_experiment.py`,
`test_eng_close1.py`, `test_r03_flow.py`, `test_rpr07_resume.py`) carry empty
literal sets, so the flagged list is a real signal rather than a constant.

**The indirection shape is still detected.** I planted the exact shape that
caused the original loss into a scratch tree:

```
DB = 's09o_pilot_rerun_a'
def test_planted(): pass
def _teardown():
    subprocess.run(['dropdb', DB])
```

Result: `{'test_planted.py': ['s09o_pilot_rerun_a']}`. The literal never
appears on the destructive line and the check still finds it, which is the
whole point of reading literals from the AST rather than the line.

**The ceiling gate actually bites.** I planted a reintroduced hazard in
`test_s09c1_continuity.py`, one of the `MIGRATED_FILES`:

```
reintroduced hazard flagged: {'test_s09c1_continuity.py': ['s09o_pilot_full']}
others (what HAZARD_CEILING=0 checks): ['test_s09c1_continuity.py']
would len(others) <= 0 be: False -> gate FAILS (good)
```

Both `test_the_hazard_has_not_grown` and `test_a_converted_file_stays_converted`
would go red. The gate is not decorative.

The honest limitation, which the module already states at
`experiments/ad01/s09_test_db_safety.py:56-60`: the check is a superset that
flags any file *mentioning* the words, so a docstring quoting `DROP DATABASE`
counts. `test_a_name_mentioned_in_prose_is_not_a_database_the_suite_drops`
pins that direction rather than pretending the check is exact. That is the
right way to handle it.

---

## 7. Evidence integrity

**No finding. The exposure arithmetic is correct.**

### 5563 decomposes as claimed

`reports/PROJECT-LEDGER.md:303-311` enumerates every non-settled row in the
`reservations` table of `invl02_live`:

| Reservation | Amount | State |
|---|---|---|
| `res-ad01-ad01-w0-I-72-b0-ad01-w0-dev-sw-00-construct-l1-init` | 3269 | uncertain |
| `res-invl02-output-872608eb94c3-P1-audit-0023-a1` (r4) | 2294 | uncertain |
| `res-invl02-output-P1-audit-0023-a1` | 2294 | **settled** |

`3269 + 2294 = 5563`, and the third row is settled so it correctly does not
count. The decomposition holds.

### Both recomputations are arithmetically right

```
4880 // 4 + 1 + 2048 = 3269     # older AD01, matches its reservation row
  981 // 4 + 1 + 2048 = 2294    # r4, matches its reservation row
```

I recomputed both. Both agree with the durable rows, and the evidence files
carry the matching figures
(`reports/evidence/invl02-live/store-reconciliation.json` reservation
`amount: 3269`; `reports/evidence/invl02-output-shape-550b-r4/store-reconciliation.json`
reservation `amount: 2294` and operation `reservation_amount: 2294`). The
formula at `reports/PROJECT-LEDGER.md:225` is
`(sum(floor(len/4)) + 1 + max_output_tokens) * (retries + 1)`, and both rows
have retries 0.

### The r4 store reconciliation is candid about its own under-report

`reports/evidence/invl02-output-shape-550b-r4/store-reconciliation.json` states
`bundle_under_reports_spend_by: 1` and explains the cause: the writer persisted
the unavailable bundle at 00:53:29, before the operation row at 00:53:52 and
the lost-response receipt at 00:54:52. That is a faithful description of a
persistence-ordering defect, and the bundle's own `status: "unavailable"` with
`dispatch_count: 0` is consistent with it. No overclaim found in this file.

This matches the standing memory that the r4 bundle says 0 dispatches while the
store says 1, and that the ceiling must never be derived from a
crash-losable file. The evidence here does not repeat that mistake.

---

## 8. Cost of the intersection gate

**F-8. `campaign_test_intersection()` costs ~123 s of wall time and is called
inside the test that pins the campaign set. CONFIRMED, low severity, but it is
the reason the headline run could not finish.**

Profiling at `dd504e1` gave these phase costs.

```
walk_source_files: 1.0s, 692 files
campaign_modules: 0.2s, 32
imports_of all: 115.6s
full intersection: 122.9s
```

I instrumented `_imports_of` to count calls: **692 calls, 692 distinct files,
maximum 1 repeat per file.** So there is no redundant-work bug. The cost is
`ast.parse` over every `.py` in the repository, which
`tests/test_s09_merged_tip_regression.py:125-150` deliberately includes
("Untracked files are included too"). 51 files take over 0.5 s each, led by
`experiments/ad01/offline_recompute.py` at 2.52 s and
`src/settlement/store.py` at 2.17 s.

It is correct behaviour and a defensible trade. But on a loaded 2-core host it
is the single largest contributor to the run not finishing, and it sits inside
a test that must pass for the campaign set to be considered pinned. Caching the
parse by `(path, mtime, size)` would make the gate cost milliseconds on
subsequent calls without weakening it. I am not treating this as a defect, only
as the mechanical reason a 15-minute budget was not enough here.
---

## What I could not establish

- **Absolute suite timing.** The host was starved throughout, as quantified
  above. The completed run consumed 4.5 minutes of CPU across 81 minutes of
  wall time. I can say the claimed 15m19s is plausible on an idle host and that
  my run does not contradict it. I cannot say what the suite costs unloaded,
  because I never had an idle host.
- **The claimed `691 passed, 1 skipped, 1 xfailed` exactly.** My completed run
  covered 609 of the 693 campaign tests, missing only the 84-test regression
  gate, and came back with one failure. I did not run all 693 to completion,
  so I cannot state the worker's number as either confirmed or refuted. What I
  can state is that the suite is not green here, and that the single failure is
  the mechanism-verdict test.
- **The DB-backed campaign run.** I did not run the 693-test set with DSNs
  configured. The DB-backed files create and drop their own `s09iso_*` per-run
  databases, so this is safe to do, but the contention would have made the
  result uninterpretable anyway. The 194/693 figure is a structural count from
  the collected ids and each file's fixture signatures, not a run-time
  observation of which connections opened.
- **Whether F-2 and F-8 are the worker's own regression or pre-existing.** I
  measured both at `dd504e1` only. Comparing against the earlier tip was out of
  scope for a read-only review on a shared worktree.
- **Any live behaviour.** No model call, no router restart. The only databases
  created were the `s09iso_*` per-run ones the suite's own fixtures create; the
  three orphans named in run 2 are the residue.

## Recommended next actions

1. **Fix F-7 first.** Add a check that the checked-in r4 evidence bundle
   verifies, or re-freeze it against the current tree. Until then the r4
   evidence supports no tamper claim.
2. **Fix F-5 and F-6.** Bind `study_id`/`study_root` to an expected value in
   `_check_freeze`, and make the zero-usage check require receipt-level
   corroboration rather than a `measured == 0` shape test.
3. **Fix F-2.** Give the wall-clock-bounded AST test headroom proportional to
   measured baseline, or assert on a semantic property (the step produced a
   legal recorded stop) rather than on the specific refusal string. The
   mechanism verdict should not be load-dependent.
4. **Correct the exemption docstring** at
   `tests/test_s09_merged_tip_regression.py:324-328` for
   `test_s09m34_bind.py`, which does have import edges.
5. **Report the DB ratio** alongside the headline. 194 of 693 is the honest
   denominator for "campaign coverage".

## On the credential

`sk-cx-local` is present in pushed git history at commits `00473ac` and
`9eaa551`. That is a known, previously reported and accepted condition. I have
not reprinted the value anywhere in this review, and I confirmed the current
working tree carries only the negative assertion `assert "sk-" not in measured`.
