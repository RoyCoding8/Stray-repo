# CI failure causes — run 37261826154

**This is the cause map for the 247 distinct failing test IDs in run
`37261826154`.** It extends `reports/evidence/ci-baseline-37172638343.md` (run
`37172638343`, tree `0ee4699`), which left 160 assertion failures explicitly
unrooted.

**Second pass, 2026-10-05: the uploaded artifacts were downloaded and all 59
previously unrooted IDs are now rooted.** The first pass had only the job console
slice. `gh run download 37261826154 -R RoyCoding8/Stray-repo` returns 9
artifacts, all `expired=False`, and three carry the full pytest `suite.log` with
traceback bodies.

Every cause below cites the traceback line or source line it was read from, and
carries an explicit `open` or `repaired-since <sha>` status measured against
**`d4eb4126`, the tree this run actually measured**, not against the current tip.

**Which tree, stated exactly.** The run's `headSha` is `d4eb4126`, not the
`980e3c26` named in the first pass. Checked rather than assumed: `d4eb4126` is an
**ancestor** of `980e3c26`, and the 6 commits between them touch no file under
`tests/` or `src/`, so both labels describe the same failing code and the first
pass's tree label is sound. This pass quotes lines from `d4eb4126` and verified
that the files it cites are byte-identical there and at HEAD.

The tooling is re-runnable and uncommitted, under `.scratch/`: `parse.js` and
`parse-heavy.js` extract the tracebacks, `classify2.js` assigns each ID a cause
and an evidence level, `priorz.js` reconstructs the prior pass's 59, `mkcsv.js`
emits the per-file CSV. Re-running `mkcsv.js` reproduces the delivered CSV
byte-for-byte.

**No `.py` file was edited.** Where a fix is certain it is written as a spec.

## Headline: 59 unrooted becomes 0, and the whole run reconciles to 247

| | Prior pass | This pass |
|---|---|---|
| Distinct failing IDs | 247 | **247** (re-derived, zero intersection) |
| Named causes | 13 | **40** |
| IDs left unrooted | **59** | **0** |
| IDs rooted by traceback or blame line | not distinguished | **182** |
| IDs whose cause is read from the message only | not distinguished | **65, labelled inferred** |

The 247 is derived, not inherited. It is the sum of two independently extracted
ID sets:

```
suite IDs with traceback bodies:  175   (py3.13-1: 29, py3.13-2: 33, py3.13-3: 113)
heavy IDs:                         72
intersection:                       0
DISTINCT TOTAL:                   247
```

## The two evidence levels

| Level | Meaning | IDs |
|---|---|---|
| **rooted** | A traceback body or a pytest blame line naming `file:line` exists for that ID | **182** |
| **inferred** | Only the truncated short-summary message exists | **65** |

An inferred cause is not a guess dressed as a finding. It is the exception type
read off the summary line and nothing more, and it is labelled `inferred` in
every row of the table and in the CSV. They sit in **10 files** and split by
mechanism: **60 across 9 `_heavy_archived` files** whose job printed no traceback
bodies at all, and **5 XPASS in `tests/test_s09_normalizers.py`**, a different
mechanism that does not yield to a log change.

## What the artifacts do and do not contain

The brief's premise was that the artifacts might be gone past retention. **They
are not.** The run was created 2026-10-05 and all 9 artifacts report
`expired=False`. The real constraint is narrower:

| Artifact | Contents |
|---|---|
| `suite-py3.13-1/suite.log` | 296,648 bytes, full tracebacks, 29 failures |
| `suite-py3.13-2/suite.log` | 92,988 bytes, full tracebacks, 33 failures |
| `suite-py3.13-3/suite.log` | 321,363 bytes, full tracebacks, 113 failures |
| `heavy-archived` console + `heavy-failures.txt` | 72 IDs, bodies for 11 of 20 files, covering 12 IDs |
| `suite-py3.12-`, `suite-py3.13-`, `suite-py3.14-`, `suite-py3.13-4` | **progress dots only, 630 to 4,324 bytes, no FAILURES block** |

Those four cancelled jobs are **suite** shards, and they hold **none** of the 65; every
ID assigned to one of them already has a body from a different shard. **The 60
hheavy-side inferred IDs come from the `heavy-archived` job, which is not one of the
cancelled jobs.** The reason is mechanical: that job runs `pytest -q` once per file, and
under `-q` pytest prints a single-line `FileNotFoundError` with no body and no blame
line. The 60 sit in:

**The highest-value fix in this document is a CI-config fix, not a code fix.**
The heavy job runs `pytest -q` once per file, which suppresses the FAILURES block
and prints each ID twice, truncated then full. Dropping `-q`, or archiving the
full stdout, makes the 60 heavy-side inferred IDs rootable on the next run. The
other 5 are `XPASS(strict)`, which pytest reports without a traceback body under any
verbosity, so those need a decision about the xfail markers rather than a log change.
That single change is worth more than any cause below it.

## Three parser bugs, recorded because each produced confident wrong answers

1. **Positional pairing is wrong.** Pairing FAILURES headers to short-summary
   lines by position attributes tracebacks to the wrong test:
   `test_resume_exposure_fidelity.py` failures were attributed to
   `test_r_final_freeze_and_chain.py`. Joining on the test name gives **175 of
   175 joined, 0 unjoined**.
2. **The heavy job has no FAILURES banner.** Banner-anchored parsing found **1 of
   72**. Anchoring on the `<testfile>.py:<n>:` blame line that terminates each
   body found **72 of 72**.
3. **The heavy console needs the `gh` log prefix stripped.** `gh run view --log`
   emits `job\tstep\tISO-8601\tcontent`, and a leading BOM on some lines defeats a
   naive prefix regex. Splitting on tab and indexing fields is reliable.

Anyone re-running this must not pair section headers with summary lines by
position. That mistake yields plausible, wrong, per-file attributions.

## Cause table

Groups are disjoint and sum to **247**. `R` is rooted (traceback or blame line),
`I` is inferred (message only). Status is against `d4eb4126`.

| Cause | IDs | R | I | Status | Evidence anchor |
|---|---|---|---|---|---|
| A `_Store` stub leaked onto the `settlement` package | **82** | 82 | 0 | **repaired-since `f53bec7d`** | `type object '_Store' has no attribute` |
| B `.venv` interpreter path absent | **35** | 0 | 35 | open | `FileNotFoundError ... /.venv/bin/python` |
| D `pg_dump` server version mismatch | **12** | 5 | 7 | open | `pg_dump: error: aborting because of server version mismatch` |
| G Execution-authority refusal | **11** | 10 | 1 | open | `refused: execution needs explicit authority and identity` |
| E PostgreSQL unavailable | **8** | 3 | 5 | open | `connection to server on socket ... failed` |
| H `PolicyNotProved` on bound-use proof | **8** | 0 | 8 | open | `needs a store, an allocation and an operation` |
| C Git pinned-ref unresolvable in a depth-1 clone | **7** | 7 | 0 | open | `CalledProcessError ... exit status 128` |
| I `LiveRefused` on store authority binding | **7** | 7 | 0 | open | `improve_channel.py:2330` |
| N Stale citation line, 7 distinct defects | **7** | 7 | 0 | open | `test_m0_plan_claims.py:82,128,145,163,197,216,318` |
| P Stale claim needing re-derivation | **6** | 6 | 0 | open | `test_final_accept_findings.py:148,242`, `test_evidence_supersession.py:67,159`, `test_r_final_freeze_and_chain.py:207,325` |
| L Regex no-match | **6** | 4 | 2 | open | `AssertionError: Regex pattern did not match` |
| AR XPASS(strict) xfail, no traceback body | **5** | 0 | 5 | open | `[XPASS(strict)] the guard is a value comparison` |
| AA Use path refuses where acquired bytes were expected | **4** | 4 | 0 | open | `test_aleb_construct.py:156`, `test_alec_episode.py:54`, `test_bacq_method.py:75`, `test_aled_campaign.py:272` |
| AD Chain effect row missing | **4** | 4 | 0 | open | `test_a42_chain_demonstration.py:343,379,485`, `test_inv_a_chain.py:259` |
| S Environment or child-adapter contract | **4** | 4 | 0 | open | `test_adv_isolation.py:86`, `test_eacq_repair.py:222`, `test_eng_invb_dispatch.py:194`, `test_s09_n201_claim_ledger.py:257` |
| F DBOS 3.0 config removal | **4** | 2 | 2 | open | `DBOS Error 3` |
| AC Authority or identity conflict | **3** | 3 | 0 | open | `trajectory.py:175`, `test_a41_reuse_id.py:165,199` |
| O Credential scan vacuous, self-refusing | **3** | 3 | 0 | open | `test_inv_b14_retention.py:526,572`, `test_inv_b17_budget_fit.py:229` |
| AM Empty-collection assertion | **3** | 3 | 0 | open | `test_invr1_study_entry.py:233`, `test_output_evidence.py:418`, `test_s09_doubles_forensics.py:240` |
| K Containment preexec, Landlock install | **3** | 3 | 0 | open | `launcher_local.py:1000` via `_child_setup` |
| AB Phase failed binding study authority | **2** | 2 | 0 | open | `test_a40_admission_wired.py:217,328` |
| AE Dispatch receipt invariant | **2** | 2 | 0 | open | `test_ag01_experiment.py:377,775` |
| Q Ledger bottleneck ranking | **2** | 2 | 0 | open | `test_inv_d1_documents.py:543,588` |
| AG Campaign coverage census moved | **2** | 2 | 0 | open | `test_s09_merged_tip_regression.py:376,441` |
| R `run_live_abc` refuses at construction | **2** | 2 | 0 | open | `run_live_abc.py:135,263,417` |
| M Gate kept a private list of inert shapes | **1** | 1 | 0 | open | `test_c8_gate_review.py:150` |
| AK Credential planted-value fixture broken | **1** | 1 | 0 | open | `test_inv_b14_retention.py:547` |
| U Reader census not vacuous | **1** | 1 | 0 | open | `test_inv_z2_red_audit.py:204` |
| AP StopIteration in export scan | **1** | 1 | 0 | open | `test_invc3_export.py:206` |
| AT Control-arm `executed` field | **1** | 1 | 0 | open | `test_invc3_study.py:74`, `scripts/inv01_study.py:725-728` |
| AI Route id lost its provider prefix | **1** | 1 | 0 | open | `test_output_evidence.py:1416` |
| AL Gateway preflight did not raise | **1** | 1 | 0 | open | `test_output_evidence.py:1546` |
| AO `KeyError: qualified_on` | **1** | 1 | 0 | open | `test_p2c_ad01_resweep.py:80` |
| AN Policy view missing `contract_versions` | **1** | 1 | 0 | open | `test_production_execution_authority.py:147` |
| AJ Lane DSN is not a `postgresql://` URL | **1** | 1 | 0 | open | `test_rpr01_db.py:23` |
| AH Matrix terminal row unreachable | **1** | 1 | 0 | open | `test_s09_matrix_size.py:400` |
| AU Audit checker reports 6 problems | **1** | 1 | 0 | open | `test_rpr13_endtoend.py:466` |
| AQ Frontier revision parent not active | **1** | 1 | 0 | open | `live_construct.py:1667` |
| AF Learner run count doubled | **1** | 1 | 0 | open | `test_alee_learner.py:244` |
| T Disposition or exit code mismatch | **1** | 1 | 0 | open | `test_s3_experiment.py:237` |
| **Total** | **247** | **182** | **65** | | |

Per-file distribution for all 77 failing files is in
`reports/evidence/ci-failure-causes-37261826154-files.csv`. One row per file,
columns `test_file,total,categories`. Each category cell is
`CODE=count(evidence source-line)`, where the code is the same letter used in
the table above and the evidence is `rooted` or `inferred`. A `nR/mI` form is
defined for a cause holding both kinds across two files, but this data never
produces it: within any one file each cause is uniformly one kind. The trailing
`file:line` is a pytest blame line: the frame pytest names for that failure, which is
the line to read first but **not always the raising line**. pytest names the deepest
frame it treats as the test's own, so for a fixture-built failure it can be a setup
line. Where the raising site is knowable from the exception text it is named in the
cause table instead: cause `I` raises at `improve_channel.py:2330`, not at the
`live_construct.py` line 1369 frame an earlier draft cited, which is a blank line
docstring. The CSV's per-cause counts sum to 247, and to 182 rooted and 65 inferred.

## The three named clusters, settled

The brief asked whether these are one thing or tests correctly refusing to run
vacuously. **They are neither one thing nor uniformly vacuous.** Each cluster
splits.

### Cluster 1, stale-pin detectors: 7 IDs, and they are 7 distinct defects

All 7 are in `test_m0_plan_claims.py`. The prior pass could only see one message
and suspected a single stale pin. The tracebacks give seven different assertions
failing for seven different reasons:

| Line | Assertion | What is actually wrong |
|---|---|---|
| 82 | `assert [...] == []`, 17 stale rows | Citations moved. `live_construct.py:615` is now `:856` |
| 128 | `assert [] == ['a49a9c5','b74f216','8c535e3']` | `LAST_VERIFIED` not re-pinned after three cited paths moved |
| 145 | `assert {'8c535e3','b74f216'} <= set()` | The path filter returns nothing, so the trigger is broken |
| 163 | `assert False is True` | `9a1884d` is not a descendant of `2b7050a`, so the trigger cannot see the move |
| 197 | `assert (None is not None)` | The demonstration no longer demonstrates anything |
| 216 | `assert ':1230' in ''` | The table stopped citing `1230` |
| 318 | `assert 1 == 0` | `main()` exit status disagrees with the debt it printed |

**Verdict.** Not one cause. Lines 82, 128 and 216 are a stale pin needing a
human re-read and re-pin. Lines 145 and 163 are a **broken detector**: the path
filter returns an empty set, which is the worse failure because a vacuous
detector reports clean. Lines 197 and 318 are tests that have stopped testing.
This is the most valuable cluster in the run, because a broken detector is worse
than a noisy one.

### Cluster 2, credential-vacuity: 3 are correct refusals, 1 is a broken fixture

The prior pass counted 3 and could not tell a refusal from a breakage. Four IDs
are involved and they are not the same thing:

| Line | Message | Verdict |
|---|---|---|
| `test_inv_b14_retention.py:526` | `no credential reachable from this environment` | **Test working correctly.** Self-reporting vacuity, exactly as designed |
| `test_inv_b14_retention.py:572` | `the credential is unreachable, so this scan would pass on an absence` | **Test working correctly.** Says so itself |
| `test_inv_b17_budget_fit.py:229` | `the scan found no credential to search for; it is vacuous (looked in: none)` | **Test working correctly** |
| `test_inv_b14_retention.py:547` | `assert ''` on `test_the_credential_scan_catches_a_planted_value` | **A genuine defect.** This test plants a value and asserts the scan catches it; the scan returns `''` because the fixture that plants the value did not run |

So the prior pass's reading of these as "the tests working correctly" was right
for 3 of 4 and wrong for the fourth, which it had folded in. **The 3 refusals
must not be "fixed".** They are the tests refusing to run vacuously, and the fix
is to configure the credential in CI, not to weaken the assertion.

### Cluster 3, stale-claim re-derivation: 6 IDs, and only 3 need re-reading

The prior pass grouped 8 under "needs a human re-read". **It is 6 IDs, not 8, and
only 3 of those are genuine documentation drift.** An earlier draft of this document
counted `test_r_final_freeze_and_chain.py:207` and `:325` under both "stale" and
"live defect", which is why it said 8. The counts below partition the 6:

- **Genuinely stale claims, 3.** `test_final_accept_findings.py:148` (the B4 freeze
  artifact's own text no longer matches) and `:242` (an archived generator reads
  `channel.REACHABLE_EVIDENCE`, which lane C4 deleted with the fixed menu, and its own
  message says the deletion is correct), and `test_evidence_supersession.py:159`.
- **Unresolvable reference, 1.** `test_evidence_supersession.py:67`:
  `intact_at_ref 'd422c93' is not a commit in this repository`. Not staleness, but a
  marker pointing at a ref that does not exist in this repo.
- **Live defects, 2.** Both in `test_r_final_freeze_and_chain.py`. At `:207` the verdict
  stopped claiming `informs_decision`, so the row that would hide a smuggled write is no
  longer produced and the guard is no longer exercised. At `:325` the protocol opens 0
  connections where 2 were required.

**Verdict.** 3 + 1 + 2 = 6. Reading all 8 as "needs a human re-read" would have left two
live defects unexamined and one unfixable reference looking like a documentation task.

## Cause K: the baseline had already narrowed it; what is new is the raise above the four

**The baseline got here first, and this section should not pretend otherwise.**
`ci-baseline-37172638343.md:94-104` already identified `read_deny` as the
discriminator: *"All three failures declare a read deny list; the passing sibling in
the same file dispatches through the identical helper and declares none.
`_child_setup` (`launcher_local.py:991`) calls `_landlock_restrict` only when
`deny` is non-empty."* It also already grouped the four candidate raising sites
(`prctl` :296, `landlock_create_ruleset` :299, `landlock_add_rule` :312,
`landlock_restrict_self` :318). **An earlier draft of this document claimed the
narrowing as new. That was wrong, and it is corrected here.**

**What this pass adds is a fifth candidate the baseline's four do not include.**
The baseline stopped at "the log cannot say which", correctly, because CPython
discards the child exception before the parent sees it. Reading the source shows a
raise *above* all four syscall sites, before any of them is reached.
`_landlock_restrict` opens with:

```
probe = probe_landlock()
if not probe.available:
    raise OSError(_errno.ENOSYS, probe.reason)
```

at `launcher_local.py:256-258`. A child raising `ENOSYS` there produces exactly the
observed `SubprocessError: Exception occurred in preexec_fn`, without calling a
syscall at all. **The four baseline candidates all sit below that check, so if the
probe is what failed, none of the four is the answer** and the candidate set is five
deep, not four, with the shallowest being a kernel-availability check rather than a
syscall.

All 3 failures also reach the same assertion, `assert outcome.sent is True` at
`test_n36_containment.py:70` and `test_n36_refusal_strand.py:257`, with the refusal
string built at `launcher_local.py:932`. I verified `launcher_local.py` and both n36
test files are byte-identical between `d4eb4126` and HEAD, so the code read is the
code that ran.

**Residual limit, stated plainly.** Which of the five failed cannot be named from any
log, and cannot be, because the child exception is discarded before the parent sees
it. A run that captured child-side stderr, or a run on a kernel where
`probe_landlock()` is known-good, would separate these in a single run. **The
baseline's "not identifiable from this log" still holds; the candidate list is
five, not four.**
## Causes the prior pass classified from the message, re-derived from tracebacks

The prior pass classified D, E, F, G, H, I and J from summary lines. Re-derived:

| Cause | Prior | Now | What moved |
|---|---|---|---|
| A `_Store` stub leak | 82 | **82** | Count holds. Mechanism sharpened, see below |
| B `.venv` path | 35 | **35** | Holds. Now labelled 35 inferred, because the heavy job printed no bodies |
| C pinned-ref | 7 | **7** | Holds. Traceback confirms `exit status 128`, matching the shallow-clone claim |
| D `pg_dump` | 10 | **12** | **Grew by 2.** Tracebacks show the mismatch in 5 IDs that the prior pass counted as `L_regex` or assertion failures |
| E PostgreSQL | 7 | **8** | **Grew by 1.** `test_m2_frontier_inherit.py:452` fails in the same family and was counted as Z |
| F DBOS | 4 | **4** | Holds |
| G exec-authority | 11 | **11** | Holds at 11, in the same files. **Still did not shrink**, the clearest negative result in the run |
| H `PolicyNotProved` | 8 | **8** | Holds. All 8 inferred; no traceback exists for that file |
| I `LiveRefused` | 8 | **7** | **Shrank by 1.** `test_binding_provenance.py` fails with `revision parent is not the active program`, a different defect, now cause AQ |
| AR XPASS | 5 | **5** | Holds. pytest prints no body for XPASS, so these stay inferred; the reason line is authoritative |
| L regex | 8 | **6** | **Shrank by 2**, both reattributed to D |
| K preexec | 3 | **3** | Holds, but narrowed from 4 sites to 1 |

### Cause A, restated in the terms the repair proved

The census said the stub was assigned into `sys.modules`. **The repair showed it
was assigned to `_types["settlement"].store`, an attribute on the `settlement`
package**, which is why it outlived the test that installed it. My traceback
evidence is the strongest form of that claim, because all 82 IDs' messages name
the owning test and the stub's qualified name verbatim:

```
AttributeError: type object '_Store' has no attribute 'seed_allocation'
AttributeError: <class 'test_posix_paths_checkpoint_restore._restore_without_postgres.<locals>._Store'> has no attribute 'operation_receipts'
```

The second form is CPython rendering `monkeypatch.setattr`'s target, and it names
the leaking test directly. **All 9 named attributes still exist on the real
store**, so a lane that migrated production `_Store` would have fixed zero of
these 82. Fixed by `f53bec7d`, which restores the attribute in the existing
`finally` block. Per `f53bec7d`, 1 of 9 store attributes survived before the
repair and 9 of 9 after; I did not run that measurement and attribute it.

## What a repair lane should do, in order

1. **Stop uploading a `-q` heavy log.** One CI-config change makes all 65
   inferred IDs rootable on the next run. Everything below is smaller than this.
2. **Cause A, 82 IDs.** Already repaired in `f53bec7d`. Nothing to do.
3. **Cause B, 35 IDs.** Derive the interpreter from `sys.executable` instead of
   `ROOT / ".venv" / "bin" / "python"` in `test_run_bounded.py:45` and
   `test_s09iso_stale_sweep.py:51`; derive the committed literal at
   `test_ec02ad_verif.py:1165`.
4. **Cause C, 7 IDs.** Add `fetch-depth: 0` to the checkout steps in `ci.yml`.
5. **Cluster 1 lines 145 and 163.** The stale-pin detector's path filter returns
   an empty set. A detector that cannot see a move reports clean, which is worse
   than a noisy one. Fix before re-pinning anything.
6. **Cluster 3 lines 207 and 325.** Two live defects in
   `test_r_final_freeze_and_chain.py`, not stale documentation.
7. **Cause K, 3 IDs.** Landlock install at `launcher_local.py:1000` fails in
   `preexec_fn` on this kernel. Needs a kernel-level answer CI can give.
8. **Cause J, 5 IDs.** Reconcile the `test_s09_normalizers.py` strict xfails with
   the guard's actual behaviour. A semantic decision, so it is left to the owner.
9. **`test_evidence_supersession.py:67`.** Marker names ref `d422c93`, absent from
   the repository. Either point it at a real ref or drop the claim.

## Not verified

Stated so a repair lane does not read these as measured.

- **NOT RUN:** every failure requiring a live database or a POSIX child process.
  Causes D, E, F, G, H, I, K and the inferred IDs in those families are read
  from tracebacks, not reproduced here. GitHub CI runs all of it.
- **The 65 inferred IDs** rest on the truncated summary message. Their cause is
  labelled inferred in every row, and the artifact gap that causes it is named
  above.
- **Cause K's failing syscall** is not identifiable from any log, because CPython
  discards it.
- **`tests/test_evidence_integrity.py`** is owned by lane `wt/e3`. It is
  classified here and **not edited**.
- The `_Store`, `.venv` and socket-DSN mechanisms are read from the source line
  that builds the path or installs the stub. They were not run.





