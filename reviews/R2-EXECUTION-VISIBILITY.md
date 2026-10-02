# R2 — execution and visibility: independent review

Reviewer lane R2. Read-only on the codebase. Every finding below carries a
reproduction I ran against a disposable database (`r2rev_*`, created and dropped
by `/tmp/r2/mkdb.sh`). No file under `src/`, `experiments/`, `tests/`,
`conftest*` or `reports/` was created or modified by this lane. Scratch is under
`/tmp/r2/`.

Tip reviewed: `254f43e`, branch `codex/implementation-investigation-learning-02`.

---

## 1. Findings, most severe first

### N-300 — CRITICAL — a committed evidence artifact is not producible by the code that claims to have written it

`reports/evidence/inv_r1_e3_selection/e3-store-witness.json`, both arms.
Generator: `experiments/ad01/s09_e3_selection.py:419-506` (`store_witness`),
`:377-404` (`read_back`).

**The severed arm holds four receipts and is structurally impossible.**

`store_witness` builds its return value in this order:

```
operations    = list(run.operations)
operation_ids = [record["operation_id"] for record in operations]
"admitted_decisions": [] if sever else admitted,
"bindings":            [] if sever else bindings,      # <- forced, ignores `operations`
"receipts":            read_back(dsn, operation_ids),  # <- from the REAL id list
```

`read_back` short-circuits without querying when the id list is empty
(`s09_e3_selection.py:390-391`, `if not operation_ids: return rows`).

So for a severed arm the generator can only emit:
* `bindings == []` always (hardcoded), **and**
* `receipts == []` whenever the severed run admitted nothing.

The committed file has `bindings: []` and `receipts: 4`. Reproduced:

```
$ .venv/bin/python -c "... read committed file, print len(bindings) vs len(receipts)"
connected  bindings=5 receipts=5  -> consistent with generator? True
severed    bindings=0 receipts=4  -> consistent with generator? False
```

The connected arm is consistent; the severed arm is not.

Three further contradictions in the same file, all checkable by `jq`:

1. `operations_in_store: 0` while the arm carries 4 receipts naming
   `ad01-e3sever-cut-*` operations.
2. All four `refused_decisions` carry `operation_id: ""` — the exact invariant
   `tests/test_s09_e3_sever.py:390` asserts ("a refused decision was given an
   operation id") — yet four receipts exist for the same campaign's operations.
   A decision cannot be simultaneously refused-with-no-id and settled-with-a-receipt.
3. `connected.operations_written_by_the_run: 0` while the same arm holds 5
   settled receipts that the run itself wrote.

**It was never consistent.** `git log` shows one commit, `52235a6`; the file has
never been rewritten.

```
$ git log --oneline -- reports/evidence/inv_r1_e3_selection/e3-store-witness.json
52235a6 E3: the sever control ran, and it exposed a worse gap than the one it fixed
$ for c in $(git log --format=%h -- <file>); do ...; done
52235a6  connected(wrote=0,receipts=5)  severed(wrote=0,receipts=4,refused_with_oid=0)
```

**The generator now emits something different.** Running the same function that
wrote the file, on a fresh database:

```
$ /tmp/r2/mkdb.sh e3g && .venv/bin/python -c "...s.write_sever_evidence(out, dsn)..."
store_witness_connected    wrote=5 in_store=5 admitted=5 receipts=5
store_witness_severed      wrote=0 in_store=0 admitted=0 receipts=0

committed e3-store-witness.json:
connected                  wrote=0 in_store=0 admitted=5 receipts=5
severed                    wrote=0 in_store=0 admitted=0 receipts=4
```

The severed arm of the committed file cannot be regenerated and cannot have been
produced by this generator.

**Impact.** This is the second question in the lane brief — *evidence that exists
without an effect* — in its sharpest form, and it is worse than the ledger records.
N-51's recheck cell and the completion matrix both read `e3-store-witness.json` as
"correct about itself" / "the file named for this purpose". It is neither. A reader
who checks the severed arm concludes the sever control admitted nothing; a reader
who checks the receipts concludes it admitted four things and admitted nothing at
the same time. N-52's causal claim (the severed arm is a strict prefix of the
connected arm, so the arms differ in what *ran*) rests on exactly this artifact.

**Owner:** E3 owner, with the coordinator. This is not a repair-a-line defect; the
artifact needs to be deleted and regenerated, and the reason it was hand-edited
is itself the question.

**Reproduction:** `/tmp/r2/probe_impossible.py`, `/tmp/r2/probe_e3h.py`
(0 receipts produced for a severed arm), and the two-command diff above.

---

### N-301 — CRITICAL — `operations_written_by_the_run` is a global row count, so it attributes a foreign lane's writes to the run

`experiments/ad01/s09_e3_selection.py:407-416` (`_operation_count`) and
`:444-445` (`before = _operation_count(dsn)` … `wrote = _operation_count(dsn) - before`).

The metric the whole N-51 repair rests on is `count(*) FROM operations` across the
**entire database**, before and after. It is not scoped to the run, to a campaign,
or to an operation-id prefix.

Reproduction 1 — a foreign writer is credited to the run:

```
$ .venv/bin/python /tmp/r2/probe_e3.py
before=0 after=1 -> operations_written_by_the_run would report 1
but E3 admitted ZERO operations. The count attributes a foreign lane's row to E3.
rows now: ['a-DIFFERENT-LANE-op']
```

Reproduction 2 — a run that really did admit five operations is credited zero if
anything else already wrote its rows, or if the count moves for any other reason.
On this repository's own numbers the metric has already produced both polarities:
the same code path produced `5` in `e3-admitted-operations.json` and `0` in
`e3-store-witness.json` (N-300).

This matters beyond arithmetic. The N-51 test
`tests/test_s09_e3_sever.py:222` asserts
`run["operations_written_by_the_run"] == len(decided)` and its docstring claims it
"guards the opposite and stronger claim… a counterfactual that admits the same
decisions outside `run_investigations` scores zero here". The test passes only
because the fixture's database is empty and the suite is run alone. It does not
have the property its docstring claims. The lane's own decisions to be explicit
about the severed arm ("a control condition is a control, not a run against a
broken gate") is the right instinct applied to the wrong measurement.

**Impact.** The claim "E3's decisions reach real admitted operations, **written by
the E3 path itself**" — the literal words in `e3-admitted-operations.json` — is not
established by this metric. What *is* established, and what `DecisionRecorder`
genuinely provides, is the `receipts` readback by SELECT plus the
`run_decisions` cross-check; that part holds (I confirmed 5 decisions → 5
admitted operations → 5 receipts with `content.payload.decision` matching the
policy's own choices).

**Owner:** E3 owner. Fix by counting `WHERE operation_id LIKE '<campaign>-%'`, or
better by counting rows whose `operation_id` is in `run.operations`.

---

### N-302 — HIGH — a receipt can be admitted and a reservation settled under a provenance that names a party which produced nothing

`src/settlement/store.py:1656-1716` (`_validate_receipt`) and
`:1845-1901` (`admit_receipt`). Contrast `:453-526`
(`_never_sent_proof` / `_provenance_attested`).

**Yes — a receipt can be admitted whose provenance does not identify its producer.**

`_validate_receipt` requires provenance only when `outcome == "failure"`. For a
`success` receipt it never inspects the string. `_provenance_attested` exists, is
documented as the mechanism that binds a claim to the party that could have made
it, and is called from exactly one place — `_never_sent_proof` (5 call sites at
`store.py:846, 849, 1939, 2025, 2151`). `admit_receipt` never calls it.

Reproduction — an operation dispatched to `local-1`, then a receipt from a party
that never ran, which settles the reservation:

```
$ .venv/bin/python /tmp/r2/probe_q2.py
state=dispatching next=ghost launcher_id='local-1'
admit -> applied | receipt admitted, outcome success
AFTER: state=observed settled=True receipt_provenance='somebody-who-never-ran-anything'
        the operation now reports that 'somebody-who-never-ran-anything' produced its receipt.
        the store never compared that string to operations.launcher_id = 'local-1'
receipts table columns: ['content', 'content_digest', 'created_at', 'operation_id', 'outcome', 'receipt_identity']
```

Compounding it: the `receipts` table has **no `provenance` column at all**. The
single column `operations.receipt_provenance` is overwritten on *every* admission
(`store.py:1866`, `:1899`), and `payload["_receipt_provenance"]` likewise. So with
more than one receipt on an operation the producer of each is not recoverable —
last writer wins.

```
$ .venv/bin/python /tmp/r2/probe_prov4.py
1. after launcher dispatch: receipt_provenance = 'local-1'
2. after admitting a receipt with provenance='broker-inline': receipt_provenance = 'local-1'
   ... (unchanged, because that path is already settled)
   operations.payload['_receipt_provenance'] (last writer wins) = {'prov': 'local-1'}
```

and on a `dispatching` operation, where the write does land:

```
$ .venv/bin/python /tmp/r2/probe_prov5.py
receipt_provenance before: ('', None)
admit: applied receipt admitted, outcome unknown
receipt_provenance after: ('local-1', 'local-1')
```

**Impact.** This is the provenance-completeness question the brief asked about,
and the answer is no. It is bounded: I found no *programmatic* consumer of
`receipt_provenance` anywhere in `src/`, `experiments/` or `scripts/` — the only
non-test references are the writes in `store.py` itself. So the exposure is to a
**human or agent reading the store as evidence**, which is exactly what this
system's evidence contract claims to support. The brief's requirement — "a receipt
can be admitted whose provenance does not identify its producer" — is met, and
the repair already exists in the same file for the sibling case.

**Owner:** settlement. One call to `_provenance_attested(provenance, op["launcher_id"])`
in `_validate_receipt` closes the admission side; a `provenance` column on
`receipts` closes the recoverability side.

---

### N-303 — MEDIUM — the frozen-write check is an AST pattern match with unreported blind spots; the seal itself held

`experiments/ad01/improve_channel.py:836-869` (`_attempts_frozen_write`),
`:811-833` (`admit_revision_under_freeze`), `:177-178` (`FROZEN_FIELDS`).

**The seal held under every attack I ran. The static check did not.**

`_attempts_frozen_write` inspects only `ast.Assign` targets, `ast.AugAssign`
targets, and four forbidden call names. It misses any write that binds a frozen
name through a target form it does not visit:

```
$ .venv/bin/python /tmp/r2/probe_seal.py
  _attempts_frozen_write -> True    documented-test form (Assign)
  _attempts_frozen_write -> True    AugAssign
  _attempts_frozen_write -> False   annotation/record key          (record['sealed_results'] = [])
  _attempts_frozen_write -> True    nested-scope assignment
  _attempts_frozen_write -> False   walrus-free dict.update        (_d.update(sealed_results=[]))
  _attempts_frozen_write -> True    exec()
  _attempts_frozen_write -> False   for-target                    (for sealed_results in ...)
  _attempts_frozen_write -> True    with-as
  _attempts_frozen_write -> False   lambda default
  _attempts_frozen_write -> False   comprehension target
```

An ELIGIBLE revision carrying such a write is admitted as eligible:

```
$ .venv/bin/python /tmp/r2/probe_seal6.py
_attempts_frozen_write -> False
_emits_probe           -> True
_x_is_data_dependent   -> True
admit_revision_under_freeze -> eligible | informs_decision: True
frozen_state unchanged? sealed_results = [{'round': 1, ...'verdict': 'sealed'}]
```

**But the seal did not actually break, and I should say so plainly.** Two layers
held:
* the store is a JSON file, not an object the revision can reach, and
* `method_exec.verify_step_source` (`experiments/ad01/method_exec.py:607-637`)
  refuses `import`, any dunder attribute/name, and `_FORBIDDEN_CALLS`
  (`open`, `exec`, `eval`, `__import__`, `getattr`, `type`, …).

Two attempts to rewrite the whole store file — grant, used and sealed_results —
both died in the child verifier, not in the static check:

```
$ .venv/bin/python /tmp/r2/probe_seal4.py    (via __builtins__ lookup)
_attempts_frozen_write(src) -> False
verify_step_source -> refused: dunder-access-forbidden
AFTER on disk: sealed_results = [{'round': 1, ..., 'verdict': 'sealed'}]  used = {'queries': 7, 'steps': 3}
```

```
$ .venv/bin/python /tmp/r2/probe_seal3.py    (via a real import)
run raised: MethodExecutionError refused: imports-forbidden
```

**The finding is about the defense's stated shape, not a live break.** The module
docstring at `improve_channel.py:803-806` says a revision that tries to reach a
frozen field "is refused before it is measured", and the post-check is described as
the backstop "so a write that slips past the static check is still caught by the
comparison rather than by trust". That backstop does not work: `frozen_state` reads
`store._doc`, and the revision runs in a child process that only ever sees a *copy*
of the view, so no in-child write can ever be observed by the comparison. The
comparison is currently theatre; the real enforcement is `verify_step_source`, which
is a different function in a different module and is not referenced in this one.

**Owner:** E4 owner. Either enumerate the write forms (or use a scope-accurate
check such as a `symtable` pass), or re-point the docstring at the boundary that
actually holds.

---

### N-304 — MEDIUM — a pre-existing red test the ledger records as re-aimed, and the counting rule that hides it

`tests/test_s09rev_boundary.py:186-189`, failing at HEAD. Introduced by
`ac20508` ("E4: the estimator is repaired and the negative survives, sign and all").

```
$ /tmp/r2/mkdb.sh final
$ DSN="dbname=r2rev_final host=/var/run/postgresql user=ubuntu" \
  SETTLEMENT_TEST_DSN=$DSN SETTLEMENT_TEST_TRUNCATE_DSN=$DSN S09ISO_DISABLE=1 \
  .venv/bin/python -m pytest tests/test_s09rev_boundary.py -q -p no:randomly
=========================== short test summary info ============================
FAILED tests/test_s09rev_boundary.py::test_channel_headroom_reports_no_measurable_headroom
1 failed, 31 passed in 12.55s
```

```
E       KeyError: 'reachable_spread'
```

N-70's recheck cell records that this test "is now re-aimed at the real property —
no input beats the incumbent by more than the measured ceiling of 0.00267 — which
is decidable from the raw magnitude rather than from a sign." It was not re-aimed.
It still reads `reachable_spread`, `noise_floor` and `headroom`, three fields
`channel_headroom` no longer returns; the repaired estimator returns `delta`,
`paired_se`, `z` and `estimator`.

**The counting rule reproduced itself live while I measured this**, which is
worth recording because it is the N-42 defect in a second form:

```
$ ... pytest tests/test_s09rev_boundary.py -q -p no:randomly -rN 2>&1 | grep -cE "^FAILED"
0
$ ... pytest tests/test_s09rev_boundary.py -q -p no:randomly 2>&1 | tail -3
1 failed, 31 passed in 8.32s
```

**Owner:** E4 owner. It is a stale pin, not a product defect — the estimator repair
in `ac20508` was correct; the test was left addressing the old field names.

---

### N-305 — LOW — a learner-scope caller can pre-seed the evaluator's hidden-answer namespace

`src/settlement/evidence.py:60-75` (`propose_claim`),
`src/settlement/evaluation.py:61-81` (`propose_hidden_answer`).

`propose_claim` is the public write path and accepts any `access_label` the
evaluator itself is allowed to use, including `"hidden"`. It performs no check
that the claim id belongs to the caller's namespace.

```
$ .venv/bin/python -c "... evidence.propose_claim(dsn, cmd, 's3-answer:dev-9999', ..., access_label='hidden')"
learner writes a hidden answer for an unset task -> applied | claim s3-answer:dev-9999 proposed
evaluator scope then reads back: {'answer': 'LEARNER-CHOSEN', 'task_id': 'dev-9999'}
  evaluator proposal REFUSED: hidden answer s3-answer:dev-9999 already records different content
```

Two properties do hold, and I checked both: the read side is gated
(`hidden_answer` refuses `candidate` and `public` scopes, and serves only
`evaluator`/`operator`), and an existing answer cannot be *overwritten* — the
primary key makes the second write a `UniqueViolation`. The gap is the write side
for a task id the evaluator has not yet set: a learner that writes first fixes the
answer, and the evaluator's real answer is then refused as a conflict.

**Severity is low** because no in-tree caller reaches this path with a hidden
label (`development.py:413` uses the default `"public"`), so it is a
defence-in-depth gap rather than a live exposure. It is worth naming because the
property is stated as a boundary and lives in an unvalidated argument.

**Owner:** settlement / evaluation.

---

## 2. Answers to the two questions, with evidence

### Q1 — can an effect happen without evidence? **Not in the store path. Yes, once, deliberately, at the gateway.**

I could not find a path where a real operation, receipt or settlement occurs and
nothing durable records it. The store commits through `transact` on every
transition, writes `domain_events`, and journals the command. `_settle_amount`
(`store.py:565`) has no branch that moves an allocation without writing a
reservation row. N-47 (outbox stranding) and N-43 (failure evidence) are the
right two places to look for this class and both are closed in source.

The one real effect-without-evidence is the one the lane already recorded, and it
is worse than N-81 states. `reports/evidence/inv_r1_e4/result.json` →
`authority_deviation` records six dispatches through `HttpGatewayAdapter`
directly:

> "What is not available is the durable reservation row those dispatches would
> have written, so these calls are absent from the shared exposure ledger and a
> reconciliation against it will not find them."

`HttpGatewayAdapter.infer` is reachable with no `dsn` and writes nothing —
`_DurableBrokerOutput` (`scripts/invl02_live.py:829`) is an opt-in wrapper, not a
requirement. So the ledger's exposure and the artifacts disagree about what was
spent, permanently, and the expansion doc's line 91 is unenforced in code. The
lane recorded this against itself, which is why it is a finding and not a scandal;
it is still OPEN.

**The related claim that does *not* hold up** is N-51's. "Decisions reach real
admitted operations" is true — I verified 5 decisions → 5 admitted operations → 5
SELECTed receipts, with `content.payload.decision` matching the policy's own
`run_decisions`. But "**written by the E3 path itself**" is measured by N-301, a
global row count, and the artifact carrying that sentence contains an arm
(N-300) that no code path could have written.

### Q2 — can evidence exist without an effect? **Yes. It is the most severe finding in this lane.**

N-300. Four receipts exist in a severed arm whose every decision is recorded as
refused with an empty `operation_id`, in a file whose generator cannot emit that
combination, and which no longer regenerates. This is the exact failure the brief
calls worse: a claim in an artifact that no code path could have produced, in the
one artifact in the tree whose job is to say what the run actually did.

### Q3 — provenance completeness. **A receipt can be admitted whose provenance does not identify its producer.** See N-302.

### Q4 — sealed results. **The seal held; the static check around it did not.** See N-303. Separately worth recording: **there is no durable sealed-results store in the settlement database at all** (no table matching `%seal%`, `%frozen%` or `%hidden%`; hidden answers live in `claims` with `access_label='hidden'`). The E4 `sealed_results` freeze is a property of `experiments/ad01/frontier.py`'s JSON store, and its enforcement is `verify_step_source`, not `admit_revision_under_freeze`.

### Q5 — superseded artifacts / does the codebase have a supersession mechanism?

**No. There is none, at any layer, for evidence artifacts.**

* In the database there are three real supersession mechanisms, all unrelated to
  evidence files: `trials.freeze_protocol` writes a `supersedes` column
  (`src/settlement/trials.py:66-93`); `experiment.py:758` threads `supersedes` for
  an evaluator version; `development.py:970, 1025` supersedes a trial protocol.
  `artifacts.retire_artifact` (`artifacts.py:380`) sets
  `availability='retired'` on a content-addressed artifact. All four are
  content-addressed or database-resident, and none can name a file under
  `reports/evidence/`.
* For evidence files there is only **convention**: hand-written `RESULT.md` and
  `RETRACTED.md` files. There is no manifest, no index, no `retire` script and no
  checker. `scripts/s09_verify.py` reads *one bundle directory* for the N5 pilot
  and never looks at the evidence tree. The only test files that name
  `reports/evidence` do so as fixture paths, not as a consistency check.
* `git log` is the only supersession mechanism that actually functions, and it is
  invisible to a reader of the tree — which is precisely how N-300 happened: a
  file was committed once, was wrong from that commit, and nothing in the
  repository can say so.

**I scanned every evidence directory for the N-79 shape** (two or more committed
JSON files in one directory sharing a `measure_digest`/`digest`/`commitment`
value while disagreeing on any scalar):

```
$ .venv/bin/python /tmp/r2/digest_scan.py
inv_r1_e3_selection  measure_digest=ce5a140aff83bccc  files=[e3-admitted-operations.json,
    e3-crossover.json, e3-sever-control.json, e3-store-witness.json]
      DISAGREE .connected.operations_in_store: 5 vs 0
      DISAGREE .connected.operations_written_by_the_run: 5 vs 0
```

**`inv_r1_e3_selection` is the only directory with the N-79 defect.** N-79 is
correct and, given N-300, understates the problem: it frames the conflict as two
artifacts from two commits, when the older one is internally impossible. Of the
26 evidence directories with results, 3 carry a `RETRACTED.md`
(`inv_r1_e2_noexp`, `inv_r1_e2_relevance`, `inv_r1_e2_transfer`) and
`inv_r1_e3_selection` carries none — N-80 is confirmed as written. 20 directories
carry no `RESULT.md` or `RETRACTED.md` at all, most of them older campaigns
(`invl02-*`, `ag01-demo`, `d02live`); I did not audit their contents.

**N-79 and N-80 are both correct as filed.** N-79's proposed fix (mark the witness
superseded) is the wrong fix — the witness should be deleted, not marked.

---

## 3. Ledger rows I believe are WRONG

1. **N-51's recheck cell is wrong on a load-bearing point.** It states:
   *"`e3-store-witness.json`, the artifact the old row leaned on, still reads
   `operations_written_by_the_run: 0` in both arms, and **it is NOT wrong about
   itself**: it is the separate witness."* It is wrong about itself. The severed arm
   carries 4 receipts with 0 operations and 0 bindings, which its own generator
   cannot produce (N-300). The same cell also says the severed arm ran "0 written
   with 4 refused decisions" — the committed file's severed arm has 4 *receipts*,
   not 4 refused decisions, and those are different claims. N-51's repair to
   `selection.py` is real and I confirmed it; the *defence of the old artifact* is
   what fails.

2. **N-51's test docstring claims a property the test does not have.** It says the
   inverted pin guards "a counterfactual that admits the same decisions outside
   `run_investigations`", but `operations_written_by_the_run` is a global row count
   (N-301) and cannot distinguish writers.

3. **N-70's recheck cell is wrong.** It records the estimator test as "now re-aimed
   at the real property". It is not re-aimed and is red at HEAD (N-304).

4. **N-79 is right but its framing is wrong in a way that matters.** It says "Git
   history explains it — the witness predates the repair." Git history does not
   explain it: the witness has one commit and was never consistent. The proposed
   fix (mark superseded) would preserve a fabricated artifact.

5. **`reports/STAGE-09-COMPLETION-MATRIX.md` §7.4** reaches the right observation
   ("`e3-store-witness.json` … records 0 in *both* arms, while still carrying 5
   receipts connected and 4 severed") and stops one step short. It attributes the
   conflict to commit order. It is not commit order; the severed arm is impossible.

6. **N-54, N-43, N-47, N-48, N-32, N-31, N-49, N-80, N-81, N-82, N-78, N-84, N-85
   — I re-read these and found them accurate.** N-54's four guarded sites really do
   guard with `len(receipts) != 1` and `live_construct.py:1006` really is the one
   that does not. N-43's ten-value evidence set is present at `store.py:1505-1516`
   and the refusal is at 1516, before the prior-receipt guard at 1632. N-82's
   8-queries-vs-1 contrast is confirmed in source (`rule_learner.choose_query`
   takes a `budget: int = br.MAX_QUERIES` default; the incumbent emits a single
   `{"x": 3}` probe).

7. **Two memory items are now stale, in your favour.** `verified-entry-vs-executed-bytes`
   records two defects; **both are repaired**:
   * A: `experiment.py:399` now calls `capabilities.resolve_entry_path(manifest)`,
     the same resolver `capabilities._extract_entry` uses. It no longer takes the
     first `.py`.
   * B: `trajectory._run_member:1320` sets
     `result["executed_source"] = known[0]["method"]` on the seed-hit branch —
     what ran — rather than the member's `method_source` claim.

---

## 4. What I could not test, and why

* **The live gateway path (N-81's six dispatches).** No free-route grant was used
  and I made no model calls. I verified the *structural* claim — `HttpGatewayAdapter`
  takes no `dsn` and `_DurableBrokerOutput` is opt-in — by reading, not by calling.
* **N-01/N-36's 959 ms seed recovery.** Needs a live launcher and a policy. Read
  only: `worlds.py:50` is still `TASK_ID_KEY = b"ad01-task-id-hmac-v1"` in the
  repository, and `launcher_local.py:12` still says the profile "is still
  explicitly not containment". Unchanged.
* **N-83's foreign CPU-hogging process.** Not mine; I did not reap it. Worth noting
  every timing in this report was taken on that same contended box, so I quote
  counts and not durations.
* **Full-suite results.** I ran only `tests/test_s09_e3_sever.py` (13 passed) and
  `tests/test_s09rev_boundary.py` (1 failed, 31 passed), both on disposable
  databases with `S09ISO_DISABLE=1`. N-33's 9-file cluster and the N-42/N-46
  suite measurement are untouched.
* **20 evidence directories with no `RESULT.md`.** I confirmed the absence and
  checked the digest-collision shape mechanically. I did not read their contents
  for internal consistency, which is a per-directory audit I would want a separate
  lane for.
* **Whether N-300 was a hand-edit or a bug in an older generator.** `52235a6`
  changed `selection.py` and the ledger at the same time; I did not read the
  `selection.py` of that commit to see whether a `read_back` variant existed which
  could have returned receipts on an empty id list. The current code cannot, which
  is what I can prove.
