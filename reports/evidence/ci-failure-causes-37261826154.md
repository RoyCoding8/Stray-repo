# CI failure causes — run 37261826154

**This is the cause map for the 247 distinct failing test IDs in run
`37261826154`, at tree `980e3c26`.** It extends
`reports/evidence/ci-baseline-37172638343.md` (run `37172638343`, tree
`0ee4699`), which left 160 assertion failures explicitly unrooted and said
assigning causes "would be invention". This pass is that later pass. Measured
2026-10-05 from the downloaded logs in `.a53-ci2/`.

**No `.py` file was edited.** Where a fix is certain it is written as a spec.

## Method and its limits

Distinct test IDs were derived in Python with `re`, matching the
`job\tSTEP\ttimestamp\t FAILED <id> - <msg>` shape of each shard log. The
derived set is **byte-identical to `CUR.failures`** (247 IDs, zero symmetric
difference), so the denominator is verified rather than assumed.

The shard logs carry only the pytest short-summary lines and a 25-line tail.
**No traceback bodies were uploaded** (`ci.yml:99-107` uploads `suite.log` and
`failures.txt`; the console slice at `:96` is what survives in these artifacts).
Each failure therefore yields one truncated message line, median 87 characters.
Where that line is enough to name a cause, the cause is stated. Where it is not,
the failure is counted as unrooted rather than assigned a plausible story.

Three causes were established by **running** the mechanism locally rather than
by reading the message. Each is reproduced below with its command output.

## The headline: `_Store` is not production drift

The baseline called `_Store` API drift the largest cause (60) and split off a
16-ID "test-fixture drift" subfamily in the same file. **That split is wrong,
and the direction of the fix is wrong.** There is one cause and it is 82 IDs,
and it is not the production store at all.

`experiments/ad01/store.py` **does not exist**, and `class _Store` is defined in
**exactly one file in the entire tree** (verified by an exhaustive walk of all
1024 `.py` files for the token `_Store`, and by scanning every installed
package for a class of that name, which returned none):

```
tests/test_posix_paths_checkpoint_restore.py:110:    class _Store:
tests/test_posix_paths_checkpoint_restore.py:131:    _types["settlement"].store = _Store
```

That `_Store` is a local stub defining one method, `restore_fence`. Line 131
assigns it into `sys.modules["settlement"].store`, **and the `finally` block at
lines 134-138 restores `restore.*` and deletes the `psycopg` module entries but
never restores `settlement.store`.** The stub leaks out of the fixture and
outlives the test.

Every one of the nine attributes named in the failure messages still exists on
the real store. Measured on the worktree at `980e3c26`:

```
real module defines seed_grant: True
real module defines seed_allocation: True
real module defines operation_receipts: True
real module defines subdivide_allocation: True
real module defines is_ceiling_name: True
real module defines _study_root_for_allocation: True
real module defines reconcile_operation: True
real module defines allocation_free: True
real module defines is_ceiling_enforced: True
```

They are module-level functions taking `dsn: str`, defined in
`src/settlement/store.py` (`seed_grant:693`, `seed_allocation:804`,
`operation_receipts:2133`, `subdivide_allocation:831`, `is_ceiling_name:129`).
**Nothing was renamed or dropped.** A lane that migrated production `_Store`
would have fixed zero of these 82.

The leak mechanism reproduces the CI message exactly:

```
after leak, 'from settlement import store' binds: <class '__main__._Store'>
  seed_grant -> AttributeError: type object '_Store' has no attribute 'seed_grant'
  seed_allocation -> AttributeError: type object '_Store' has no attribute 'seed_allocation'
```

The 82 split into two message forms, and both are the same cause. CPython
renders `Class.attr` as `type object 'X' has no attribute` but renders
`pytest.MonkeyPatch.setattr(target, name, ...)` as `<class 'X'> has no
attribute` using the target's `__name__`. Measured on this host's Python
3.13.14 with a real `pytest.MonkeyPatch`:

```
message -> <class '__main__.factory.<locals>._Store'> has no attribute 'operation_receipts'
```

So **66** failures are tests calling `store.seed_grant(...)` on the leaked
stub, and **16** are tests calling `monkeypatch.setattr(store, "operation_receipts", ...)`
on it. The 16 name the leaking file in the message text itself
(`test_posix_paths_checkpoint_restore._restore_without_postgres.<locals>._Store`),
which the baseline correctly read as "a different subfamily". It is the same
stub.

Every victim file sorts **after** the leaking file in `tests/` collection
order. The leak is at index 207 of 408; all 17 victim files are at 213-292.

The two forms carry different attribute distributions, so the per-attribute
table is split by form. Direct-call form, 66 IDs:

| Missing attribute | IDs |
|---|---|
| `seed_grant` | 28 |
| `seed_allocation` | 13 |
| `subdivide_allocation` | 10 |
| `operation_receipts` | 9 |
| `is_ceiling_name` | 2 |
| `allocation_free` | 1 |
| `is_ceiling_enforced` | 1 |
| `_study_root_for_allocation` | 1 |
| `reconcile_operation` | 1 |
| **Total** | **66** |

`monkeypatch.setattr` form, 16 IDs: all 16 are `operation_receipts`, across
`test_resume_exposure_fidelity.py` (7), `test_route_refusal_fidelity.py` (5)
and `test_r4_live_blockers.py` (4).

So `operation_receipts` totals 25 across both forms, and the two forms together
give **82 IDs across 17 victim files**. Every one of the 17 sorts after the
leaking file in `tests/` collection order (leak at index 207 of 408; victims at
213-292).

## Cause table

Groups are disjoint and reconcile to 247.

| # | Cause | IDs | Heavy | Suite | Fix side |
|---|---|---|---|---|---|
| A | `_Store` stub leaked into `sys.modules` | **82** | 0 | 82 | **test** |
| B | `.venv` interpreter path absent | **35** | 35 | 0 | **test** |
| C | Git pinned-ref unresolvable in CI (shallow clone) | **7** | 0 | 7 | **CI config** |
| D | `pg_dump` server version mismatch | **10** | 8 | 2 | **environment** |
| E | PostgreSQL unavailable | **7** | 5 | 2 | **test** |
| F | DBOS 3.0 config removal | **4** | 2 | 2 | production |
| G | Execution-authority refusal | **11** | 1 | 10 | production |
| H | `PolicyNotProved` on bound-use proof | **8** | 8 | 0 | test/production |
| I | `LiveRefused` on store authority binding | **8** | 0 | 8 | test/production |
| J | XPASS(strict) xfail | **5** | 0 | 5 | **test** |
| K | Containment preexec | **3** | 3 | 0 | not identifiable |
| L | Regex no-match | **8** | 2 | 6 | needs traceback |
| Z | **Assertion-only, still unrooted** | **59** | 9 | 50 | **unknown** |
| | **Total** | **247** | **72** | **175** | |

Per-file distribution for all 77 failing files is in
`reports/evidence/ci-failure-causes-37261826154-files.csv`.

## Every mechanically rootable failure

### A. `_Store` stub leak — 82 IDs — TEST-side fix

**Cause.** `tests/test_posix_paths_checkpoint_restore.py:131` installs a
one-method stub at `sys.modules["settlement"].store` and never restores it.

**Fix (test-side, one line of intent).** Save and restore the attribute in the
existing `finally` block, alongside the `restore.*` originals already being
restored there:

```python
real_store = _types["settlement"].store
...
finally:
    ...
    _types["settlement"].store = real_store
```

**Per-failure detail.** 82 test IDs across 17 files, all in the `py3.133`
shard. Attribution by missing attribute is in the table above. The 16
`monkeypatch.setattr` cases name the leaking file verbatim in the message and
are attributed to the same single fix.

This is a **test-side** fix. No production file is implicated, and the nine
named attributes need no change.

### B. Hardcoded `.venv` path — 35 IDs — TEST-side fix

**Cause.** Two files hardcode a `ROOT`-relative `.venv/bin/python`, and
`.venv` is never created in the heavy job (`ci.yml:143-147` runs `pip install
-e` only). Two distinct absolute paths appear across the 35 IDs:

| Path | IDs | Source |
|---|---|---|
| `/home/runner/work/Stray-repo/Stray-repo/.venv/bin/python` | 34 | `tests/_heavy_archived/test_run_bounded.py:45` (`PY = str(ROOT / ".venv" / "bin" / "python")`) and `test_s09iso_stale_sweep.py:51` (`VENV_PYTHON = REPO / ".venv" / "bin" / "python"`) |
| `/home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest` | 1 | `tests/_heavy_archived/test_ec02ad_verif.py:1165` — a developer's home path committed as a literal |

The `Stray-repo` component is the fork's own repository name, so
`ROOT`-derived paths resolve to the runner checkout and simply do not exist
there. This is environment-shaped, not a code defect in the runner.

**Fix (test-side).** Resolve the interpreter from the running process rather
than from the repository layout, i.e. `sys.executable`, and skip where the test
genuinely requires a distinct interpreter. The `test_ec02ad_verif.py:1165`
literal is a hardcoded developer path and should be derived like the others.

### C. Git pinned-ref unresolvable — 7 IDs — CI-config fix

**Cause.** `actions/checkout@v4` is used with **no `fetch-depth`** in all three
jobs (`ci.yml:57`, `:137`, `:191`), so the clone is depth 1. Three pinned SHAs
lie 180 to 201 commits behind `HEAD` and are absent from a depth-1 clone. The
baseline attributed these to "pinned git refs that no longer resolve"; **all
three SHAs resolve fine locally.** `git cat-file -e <sha>:<path>` returns 0 for
every one. The failure is a shallow clone, not a missing commit.

Reproduced by taking a real depth-1 clone and reading the same paths:

```
shallow? true
commits visible: 1
  git show b1fca48:experiments/ad01/trajectory.py           rc=128
      fatal: invalid object name 'b1fca48'.
  git show 794520f:reports/cap-sheets/b-live-cap.md         rc=128
      fatal: invalid object name '794520f'.
  git show d183cbe:reports/evidence/inv_r1_e1_swe_ceiling/m rc=128
      fatal: invalid object name 'd183cbe'.
```

Exit status 128 and message `fatal: invalid object name` match the CI
`CalledProcessError` exactly. (`git rev-parse <sha>^{commit}` fails locally too
in this bare-ish worktree context, but `cat-file blob` succeeds, which is the
operation the tests actually perform.)

| SHA | Distance behind HEAD | IDs | Callers |
|---|---|---|---|
| `b1fca48` | 180 | 1 | `tests/test_a17_policy_state_owner.py:288` (`git show`) |
| `794520f` | 201 | 4 | `tests/test_inv_b14_retention.py:90` (3 tests, `git diff`/`git cat-file`) and `tests/test_inv_d1_documents.py:388` (1 test, `git cat-file`) |
| `d183cbe` | 201 | 2 | `tests/test_s09_matrix_size.py` (2 tests, `git show d183cbe^:…`) |

**Fix (CI config).** Add `fetch-depth: 0` to the `actions/checkout@v4` steps, or
at minimum enough depth to contain the oldest pinned SHA. Alternatively pin
these tests to a full-clone job. Note `tests/worktree_checkouts.py:46` already
defines `_GIT = ("git", "-c", "safe.directory=*")`; the depth is the missing
half.

### D. `pg_dump` version mismatch — 10 IDs — environment

Unchanged from baseline. 9 raise `SystemExit: pg_dump failed: ... aborting
because of server version mismatch`, 1 is an `AssertionError` carrying the same
text. The suite runs `postgres:18` (`ci.yml:39`) while the runner's `pg_dump`
is older. **NOT RUN** locally; no PostgreSQL on this host. Not a code fix.

### E. PostgreSQL unavailable — 7 IDs — mixed

| IDs | Message | Reading |
|---|---|---|
| 4 | `connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed` | `tests/_heavy_archived/test_rec_restore.py` uses a socket DSN; the CI service listens on TCP `127.0.0.1:5432`. **test-side**, DSN should come from `SETTLEMENT_TEST_DSN`. |
| 1 | `psycopg.errors.UndefinedObject: role "ubuntu" does not exist` | `test_rpr07_resume.py` assumes a local socket role. **test-side**. |
| 2 | `database "ec02test_p2c_unused" does not exist` | `tests/test_p2c_ad01_resweep.py` deliberately binds a `_unused` database to force a refusal; `conftest_isolation.py:39-40` documents that it must **not** be created. **environment**, correct as written. |

### F. DBOS 3.0 config removal — 4 IDs — production

`dbos._error.DBOSInitializationError: DBOS Error 3: ... DBOSConfig sets
database_url, which was removed`. 2 in `test_broker_dbos.py`, 2 in
`test_r02_authority.py`. Unchanged from baseline. **NOT RUN** locally.

### G. Execution-authority refusal — 11 IDs — production

Unchanged at 11, matching the baseline exactly, in the same five files
(`test_s09_policy_governance.py` 5, `test_ad01_live_acquired_ddmin.py` 3,
`test_s09_run_use_policy.py` 1, `test_inv_r1_use_policy.py` 1,
`test_s09_bound_use_proof.py` 1). **This category did not shrink**, contrary to
the expectation recorded in the brief. Seven of these also surface wrapped in
`GovernanceRefused` or `_UsePolicyRefused`; they are counted here once and not
double-counted under I.

Note the three tests asserting on the *absence* of an older message are in the
unrooted set and are likely the same defect seen from the other side:
`test_s09_policy_governance.py` asserts `"unknown policy action kind: 'use'" in
'refused: execution needs explicit authority and identity'`, so the guard now
refuses earlier and for a different reason than the test expects.

### H. `PolicyNotProved` — 8 IDs

All 8 in `tests/_heavy_archived/test_s09_bound_use_proof.py`, message
`this proof executes the bound policy, so it needs a store, an allocation and an
operation`. Unchanged from baseline. Mix of fixture and production; not
resolved without a traceback.

### I. `LiveRefused` on store authority binding — 8 IDs

5 in `test_evidence_integrity.py`, 2 in `test_r123_gates.py`, 1 in
`test_binding_provenance.py`. Message: `retained without binding: the round
refused before it executed anything: ... an owned store executes under the
authority its investigation authorizes, not under a disposable one`.

**Classified, not diagnosed.** These 5 `test_evidence_integrity.py` failures
are the file the brief flagged as owned by lane `wt/e3`. **Do not edit it.** No
`.py` file was edited in this pass. The 8 all carry the same refusal string, so
they are one family, but whether the fix is a fixture that admits an owned store
or a production change to the binding check is **not determinable from the log**.

### J. XPASS(strict) — 5 IDs — TEST-side fix

All 5 in `tests/test_s09_normalizers.py`, and all 5 are in `NEW.failures`:
these are new since the baseline. Message form:
`[XPASS(strict)] the guard is a value comparison, so 1.0 is admitted`.

The tests are marked `xfail(strict=True)` expecting the guard to **refuse**
`True` and float constants, and the guard now **passes** them, which strict
xfail reports as a failure. The xfail marker encodes an expectation the code no
longer violates.

| Test | Param |
|---|---|
| `test_a_unit_factor_refuses_a_bool_constant_on_either_side` | `[left-hand]`, `[right-hand]` |
| `test_a_unit_factor_refuses_a_float_constant_on_either_side` | `[left-hand]`, `[right-hand]` |
| `test_a_unit_range_step_refuses_a_float_step` | — |

**Fix (test-side, spec only).** Decide which is correct: if the guard should
refuse non-integer constants, the guard is still a value comparison and that is
the defect; if `1.0`/`True` are legitimately admissible, remove the strict
xfail. Either way the xfail and the guard must be reconciled. **This is a
semantic decision, not a mechanical one**, so it is left to the owning lane.

### K. Containment preexec — 3 IDs — still not identifiable

2 in `test_n36_containment.py`, 1 in `test_n36_refusal_strand.py`. Message:
`AssertionError: child-setup-failed: SubprocessError: Exception occurred in
preexec_fn.`

Unchanged from baseline. The baseline narrowed it to four raising sites in
`launcher_local.py` (`:296`, `:299`, `:312`, `:318`) and said the log cannot
say which, because CPython discards the child exception. **That still holds.**
The three failures still declare a read deny list while the passing sibling
declares none. Not resolved.

## The honest unrooted remainder: 59

Down from the baseline's 160. Spread over 38 files. Each has a truncated
message line only, and the cause is not determinable from it. I am not
assigning them.

Seven of the 59 form two clusters worth naming, without claiming a cause:

**Stale-pin detectors (7).** `tests/test_m0_plan_claims.py` contributes all 7.
These fire on any commit touching a cited path and the tree has moved since
they were pinned. The baseline named two members of this cluster; it is now all
seven in one file. `test_evidence_supersession.py` (2) is the same shape.

**Credential-vacuity (3).** `test_inv_b14_retention.py` (2) and
`test_inv_b17_budget_fit.py` (1) fail with `the credential is unreachable, so
this scan would pass on an absence` and `the scan found no credential to search
for; it is vacuous (looked in: none)`. These are **self-reporting**: the tests
detect that they cannot run honestly in an environment with no credential
configured, and refuse. That is the tests working correctly. Reading it as a
defect would be wrong.

**Stale-claim / re-derivation needed (8).** `test_final_accept_findings.py` (2),
`test_inv_d1_documents.py` (2), `test_r_final_freeze_and_chain.py` (2),
`test_evidence_supersession.py` (2). Messages name their own staleness, e.g.
`amend_protocol no longer opens two connections; re-derive RF-03` and `the
ledger no longer names its bottleneck section`. Each needs a human re-read of
the claim against the current tree.

The remaining 41 are ordinary assertion failures needing a traceback to
attribute.

## Before and after: `0ee4699` vs `980e3c26`

The baseline's table is at `0ee4699` and totals 259. This run totals 247.
Comparing by category **definition** rather than by name, since cause A was
misnamed:

| Cause | Baseline `0ee4699` | Now `980e3c26` | Delta |
|---|---|---|---|
| `_Store` (baseline: "API drift" 60 + "fixture drift" 16) | 76 | **82** | **+6** |
| `.venv` interpreter path absent | 35 | 35 | 0 |
| `pg_dump` server version mismatch | 10 | 10 | 0 |
| Execution-authority refusal | 11 | **11** | **0** |
| `PolicyNotProved` on bound-use proof | 8 | 8 | 0 |
| Regex no-match | 8 | 8 | 0 |
| Git pinned-ref (baseline: "missing") | 7 | 7 | 0 |
| PostgreSQL unavailable | 3 | **7** | **+4** |
| DBOS 3.0 config removal | 4 | 4 | 0 |
| Containment preexec | 3 | 3 | 0 |
| XPASS(strict) | 0 | **5** | **+5** |
| `LiveRefused` (not a baseline category) | 0 | 8 | +8 |
| Assertion-only unrooted | 160 | **59** | **−101** |

**What moved.** Only the unrooted bucket shrank, by 101, and most of that is
this pass classifying it rather than the tree improving. Cause A grew by 6.

**What did not move.** Every category the brief expected to shrink did not.
Execution-authority refusal is 11 at both trees, in the same five files. That
is the clearest negative result here, and it contradicts the expectation that
recorded in the brief.

**What grew.** PostgreSQL unavailable 3 to 7, `LiveRefused` 0 to 8 (the baseline
had no such row), XPASS(strict) 0 to 5.

**Why the totals do not reconcile arithmetically.** 247 + 40 gone = 287 against
a baseline of 259. The two runs did not measure the same universe: the baseline
had four cancelled jobs including py3.13 group 4, so a test sharded only into
group 4 or running unsharded was invisible to it. `NEW.failures` is 5 and
`GONE.failures` is 40, both measured against the previous run's ID list, not
against the baseline's. **A per-category delta between the two tables is only
meaningful for categories I could measure on both sides**, which is every row
above, and each of those is a like-for-like comparison of a definition applied
to a log.

## Contradictions with the baseline's own accounting

1. **`_Store` API drift is not API drift.** The baseline's central claim, that
   60 failures come from production `_Store` methods that were renamed or
   dropped, is false. `experiments/ad01/store.py` does not exist, no `class
   _Store` is defined anywhere but one test file, and all nine named attributes
   still exist on the real module store. The cause is a test-local stub leaking
   through `sys.modules`. **A lane acting on the baseline's diagnosis would have
   edited production code and fixed nothing.** The baseline's own warning that
   the 16-ID subfamily "must not be merged" is also wrong: they merge, because
   they are the same stub reached by two different call forms.

2. **The pinned-ref failures are not missing refs.** All three SHAs resolve
   locally; `git cat-file blob` returns the content. The cause is a depth-1
   `actions/checkout` with no `fetch-depth`.

3. **The baseline's arithmetic does not close.** Its table totals 259, its
   per-job rows total 90 + 169 = 259, and the headline says "259 distinct
   failing test IDs: 245 FAILED, 14 ERROR" while 245 + 14 = 259. Those are
   consistent. But `reports/evidence/ci-run-37251210268.md:231` in the same
   directory reports "Deleted-symbol cascade on `_Store` | 82" for run
   `37251210268`, which is the count this pass independently measures as the
   stub leak. **The 82 figure was already correct there and was labelled
   "deleted-symbol cascade on `_Store`",** which points at production again. Two
   documents in the same directory now both mislabel the same 82.

## Not verified

Stated so a repair lane does not read these as measured:

- **NOT RUN:** every failure requiring a database. No PostgreSQL on this host
  (`reports/workstreams/windows-env.md`). Categories D, E, F, G, H, I and most
  of Z are classified from the log message, not reproduced.
- **NOT RUN:** pytest at all, on this host, by standing rule.
- **Containment preexec (3)** is not attributable from the log. The baseline's
  four-candidate narrowing still stands and is not narrowed further here.
- **No traceback bodies exist** in the downloaded artifacts. Every per-failure
  detail above rests on the one truncated summary line. Category L (8 regex
  no-match failures) and the 41 unattributed assertion failures cannot advance
  without `suite.log` uploaded in full.
- The `.venv` and socket-DSN causes are read from the source line that builds
  the path. They were not run.

## What a repair lane should do, in order

1. **Cause A, 82 IDs, one line.** Restore `settlement.store` in the `finally`
   at `tests/test_posix_paths_checkpoint_restore.py:134-138`. Largest win in the
   run and it is a test file.
2. **Cause C, 7 IDs.** Add `fetch-depth: 0` to the checkout steps in
   `ci.yml`.
3. **Cause B, 35 IDs.** Replace `ROOT / ".venv" / "bin" / "python"` with
   `sys.executable` in `test_run_bounded.py:45` and
   `test_s09iso_stale_sweep.py:51`; derive the literal at
   `test_ec02ad_verif.py:1165`. (`experiments/ad01/m1_behaviour_gate.py:366`
   carries the same shape but is **not** among this run's failures.)
4. **Cause E, 5 IDs.** Give `test_rec_restore.py` and `test_rpr07_resume.py` the
   CI DSN instead of a socket path.
5. **Cause J, 5 IDs.** Reconcile the `test_s09_normalizers.py` strict xfails
   with the guard's actual behaviour. Needs a semantic call.
6. **Categories D, F, G, H, I (41 IDs)** are production or fixture questions
   needing a live database. Route to the owning lanes; `test_evidence_integrity.py`
   belongs to `wt/e3`.
7. **The 59 unrooted** need `suite.log` uploaded in full. `ci.yml:99-107` already
   uploads it, so the artifact exists; this download only has the console slice.