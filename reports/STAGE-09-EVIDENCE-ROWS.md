# Stage 09 — the four evidence-integrity rows, and what a supersession marker owes them

B1, B2, B6 and B8 of `TASKS.md` §B. A prior pass landed findings for all four;
this pass verified each one against the committed bytes, corrected one cause that
was wrong, and answered the two questions the prior write-ups left open.

**Nothing under `reports/evidence/` was modified, moved, renamed or deleted, and
nothing anywhere was deleted.** Five files were added, all of them prose:

| file | row |
|---|---|
| `reports/evidence/inv_r1_e3_selection/ANNOTATION-B1-CAUSE.md` | B1 |
| `reports/evidence/inv_r1_e1_swe_ceiling/ANNOTATION-B2-EDIT-INTENT.md` | B2 |
| `reports/evidence/inv_r1_e3_ladder/ANNOTATION-B6-REACHABILITY.md` | B6 |
| `reports/evidence/inv_r1_m4_baseline/PROVENANCE.md` | B8 |
| `reports/STAGE-09-EVIDENCE-ROWS.md` | this file |

Every number below was measured against the committed blobs at `633d3fb`, not
read off a prior document. Where a prior document was wrong, that is said.

---

## B1 — the severed arm's four receipts were made, not orphaned

**What is true.** `e3-store-witness.json` records `severed.bindings: []` beside
four populated receipts, and four `refused_decisions` each carrying
`"operation_id": ""`. The prior annotation
(`ANNOTATION-B1-B5.md`) attributes this to *"`bindings` was the only source of
the receipt id list, so severing it emptied the list passed to `read_back`."*

**That is wrong, and wrong in the direction that matters.** Under that cause the
receipts could never have been written. They were written. At `52235a6` the loop
that fills `bindings` (`s09_e3_selection.py:534`) has **no `sever` guard at
all**; it runs on `run.executions` in both arms and calls
`broker.ensure_operation` and `broker.dispatch_operation` for each. Measured from
the committed file, all four severed receipts carry `outcome: "success"` against
four distinct operation ids in the `ad01-e3sever-cut-*` namespace.

`sever` was applied only at serialization, and asymmetrically:

```
"bindings": [] if sever else bindings,                                   # :609
"receipts": read_back(dsn, [b["operation_id"] for b in bindings]),      # :611
```

Line 609 hides the local list. Line 611 reads it, and it is still full. The state
is not unreachable. It is what that one asymmetry produces.

**The artifact disagrees with the commit that introduced it.** `read_back`
short-circuits on an empty id list (`:462`), so a run of `52235a6` as committed
could not have produced four severed receipts; it would have produced
`bindings: []` and `receipts: []`. This is a stronger finding than a corrupted
record. The file is a record the committed code cannot produce.

**What I did.** Added a sibling annotation naming the correct cause. The existing
annotation is untouched: it is one of the four findings this row is about, and it
is not wrong about the artifact, only about the cause.

**Why not edit.** Editing the file to `receipts: []` would delete the only proof
the defect existed. The replacement at
`reports/evidence/inv_r1_e3_selection_regen_v2/e3-store-witness-v2.json` is
unaffected by this correction and remains correct, because it records
`bindings: 0` **and** `receipts: 0` together.

**The rule this is an instance of.** A counterfactual field and a measured field
must not be serialized from different sources. The artifact gave the
counterfactual `0`, the measurement `0`, and a third field the truth.

---

## B2 — the edit's rule, and that regenerating moves no quoted number

**The task row's figures are the census, not the edit.** The row says 124
`repaired` rows lost their terminal `stop` and 28 `unrepaired` kept it. The
measured edit is **60 rows, 56 `repaired` and 4 `unrepaired`**. 124 is the number
of `repaired` rows after the edit.

**What the edit was trying to achieve.** The rule fits all 468 rows with no
residue:

> Strip the trailing `stop` from every row whose trace contains a
> `use code.repair`. Leave a row that never applied a repair alone.

60 rows contain a `use code.repair` and all 60 were edited. 28 rows end in a
`stop` with no `use code.repair` anywhere, and all 28 were left alone. 312 rows
have empty `actions_emitted` and none were touched. It was not a compaction.

The edit tried to make one sentence true of the artifact: *a trace ends in a
`stop` if and only if the arm never applied a repair.* That sentence is false of
the run.

**Why it is false.** `run_episode` (`s09_swe_world.py:531`, unchanged at HEAD)
exits three ways, and `is_terminal` is `session.is_repaired()`, which is set at
`:381` **only by a successful `repair()`**. A successful repair is therefore
always the last thing in a trace. That gives a law independent of the edit:

> Every non-empty trace ends in `stop` or in `use/code.repair`, and a trace
> ending in `use/code.repair` has `outcome: "repaired"`.

| file | rows violating the law |
|---|---|
| `d422c93` and `d183cbe^` (as generated) | **0 of 468** |
| `d183cbe` and HEAD (hand-edited) | **4 of 468** |

The 4 are `swe-held_out-token-gaps-6bcae7` under `python-step-L0/L1/L2/L3`, each
`unrepaired` with a trace ending in `use/code.repair`. The edit did not merely
lose information. It produced a state the generator cannot produce.

**Would regenerating change a number a report quotes? No.** Of 15 top-level keys,
only `rows` differs. `per_family`, `paired` (1,872 entries), `derived_bounds`,
`search_span`, `support`, `lineages`, `missing_cells` and the rest are
byte-identical. The outcome census is **124 / 32 / 312 on both sides**, so *16 of
24 families fully repaired* stands, as does every per-family rate. Total actions
move from 47,320 to 47,260 and no report quotes that.

`RESULT.md` quotes no per-row `turns` value. Its numbers are `468`, `24 families`,
`16 of 24`, `124`, `156`, `60`, `302`, `303`, `307`, `269`, and a worked example
at `turn 112` / `turn 125` on `swe-held_out-count-tail-sum-1fdc31`, which the edit
did not touch in any of its four lineages. Searching `reports/` for a claim
depending on trace termination, by three patterns, returns only
`ANNOTATION-B2.md` and `reports/STAGE-09-EVIDENCE-FINDINGS.md`, and both already
state both censuses side by side. **Regeneration would make two documents newly
correct, not newly wrong.**

**Is the edit still needed? No, and it cannot be.** `d422c93` and `d183cbe^` are
byte-identical (5,167,881 B, sha256 `5928d4e1f66119aeef5345c7b96f1518e5180a34af80e92a9408fcb600d66781`),
so restoring the pre-edit file is a `git cat-file`, not a re-run. A re-run at HEAD
is the wrong route: `5e368eb` changed the writer's row shape, so it would produce
a structurally different file rather than a corrected one, and a real 468-row
matrix is hours of wall clock.

**The guard.** `test_a_real_matrix_ends_every_episode_where_the_loop_allows`
(`2bacba3`) is red against the committed file on purpose, for the right reason. It
should also assert the direction that discriminates: *a row whose trace ends in
`use/code.repair` has `outcome: "repaired"`*. Both that and
`turns == len(actions_emitted)` are invariant under a 60-row trace edit, which is
why both survived.

---

## B6 — annotated, reproducible, and still not reachable from the artifact

**What is true.** The prior pass's work is sound. `RETRACTED.md` and
`committed-ladder-status.json` exist in the directory, and the marker reproduces:
re-running `experiments/regen_v2/regen_e3_ladder_status.py` at this tip produces
`committed-ladder-status.json` identical to the committed one in every field
except `measured_at`. I ran it and compared.

**What is still open** is the reachability requirement: a reader who opens the
ladder should learn it was retracted without already knowing. A reader who opens
it does not learn it. Over the committed tree, **zero of the five** directories
carrying a `RETRACTED.md` have any sibling artifact mentioning the retraction,
and `e3-postfix-ladder.json` contains none of `retract`, `withdrawn`, `invalid`
or `superseded` across 165 KB. Its 18 top-level keys include `committed_ladder`
and no marker key, and the withdrawn result is nested two levels down under a key
that reads as a result name.

**The convention that would close it exists in this repo.** Two committed
artifacts carry a `supersedes` field written by their own generator:
`e2_gate_report.py:242` emits `freeze.supersedes`, and `e2_reason_probe.py:160`
emits a top-level `supersedes`. A consumer that parses the JSON sees those without
knowing to look for a second file, which is stronger than a sibling.

**It cannot be applied here, and the reason is the constraint itself.** Both
`supersedes` fields are in artifacts their writer produces. Adding one to the
ladder means regenerating and overwriting the committed artifact, which is the
prohibited act. The convention is available to the next artifact and unavailable
to this one. That is a property of the case.

**The field shape the next regeneration needs** is recorded in the annotation,
and its load-bearing part is that `withdrawn_by` must name a **document** and
`valid_for` must carry the surviving positive claim. `$.committed_ladder` is not
wrong, it is **scoped**: it is the pre-fix/post-fix bridge, deleting it would
break the comparison permanently, and a marker that can only say "retracted"
cannot say that.

---

## B8 — the premise is wrong, and that is the finding

**The task row calls `inv_r1_m4_baseline/output-run.json` "r4's 8 raw
responses."** It is not r4's responses, and the correction changes what the file
may be used for.

| | this file | the r4 run |
|---|---|---|
| `run_id` | `f9bd21ad28d8…` | `8a7d3ef94f9b…` |
| `freeze_digest` | `6b709c6365f6…` | `ad4188300eae…` |
| `source_identity` | `472ddedc7d29…` | `954ddd7b27b7…` |
| namespace | `invl02-output-b21c612ec436-*` | `invl02-output-872608eb94c3-*` |
| `status` | `incomplete` | `unavailable` |
| dispatches | 8 | **0** |

`source_identity` decides it. The value `954ddd7b2…` is the one r4's own
`grant-binding.json:bound_study.source_identity` records, so this run is **not**
the run r4's grant authorized.

**r4 produced no responses at all.** Its bundle reads `status: "unavailable"`,
`dispatch_count: 0`, and the reason *"durable broker unavailable before
inference: output preflight route does not match the freeze."* The file is
duplicated byte for byte at `output-run.pre-dispatch-crash.json`.

r4 did spend one dispatch, and `store-reconciliation.json` records it as a
**lost response**: `response_received: false`, `response_digest: null`,
`error_kind: "timeout"`, reservation `amount: 2294`, `state: "uncertain"`. A lost
response has no text to keep, so there was never anything to file under r4. That
is the 2294, and it is untouched.

**The consequence.** Naming these eight responses r4's would attach an
**18,708-unit** spend to a study whose one dispatch is a timeout. Three numbers,
three things: 2294 is r4's single uncertain reservation; 18,708 is this run's
settled exposure (4 × 2294 and 4 × 2383, because a later revision prices it
differently, so 2294 is not a constant); 18,688 is the pre-flight sizing settled
at `94443a7`, not held liability.

**Filed, not moved, and the argument.** The obvious move is to relocate the file
to a directory named for the run. Three measured reasons say no.

1. **It is the only copy.** All 8 responses are distinct, and no other file under
   `reports/` contains any of them. `git log --all --diff-filter=D` on the path
   is empty, so nothing was ever withdrawn. Only `git mv` preserves that.
2. **A move changes a liability calculation.** `_settled_study`
   (`s09_exposure_ledger.py:1013`) iterates `sorted(rglob("output-run.json"))` and
   **returns on the first match**. The resolution order today is this file, then
   r3, then r4. A rename that reorders them changes which file answers first, in
   the module that produces the exposure ceiling, and **nothing tests that
   order**.
3. **The wrong directory is the evidence.** The M4 lane ran
   `freeze-output → preflight → run-output` to get a baseline for
   `offline_recompute.verify_bundle()` and wrote it into the directory it was
   working in. `RESOLUTION.md:15` says the bundle is the output-shape cell's and
   that `verify_bundle()` routes it to `_verify_output`, not `_verify_m4_bundle`.
   The mis-filing is the finding, and the wrong directory is the only trace that
   M4 measured the wrong cell. Relocating it would erase the mistake's trace and
   leave its consequence.

So the file stays where it was produced and `PROVENANCE.md` points. A record of
what ran should remain where it ran.

---

## B7 — the shape a supersession marker would need

**Do not build it.** This is what the four cases require, stated as shape.

**Why a marker cannot be one bit.** The four rows are four different relations,
and a single `superseded: true` collapses three of them.

| row | the artifact | what is wrong | what survives |
|---|---|---|---|
| B1 | wrong in place | severed receipts with no binding | nothing in that arm |
| B2 | wrong in place | 60 rows edited post-generation | all 468 rows, recoverable at a ref |
| B6 | **right** | one sub-key is a withdrawn result | the file, and the key, for a comparison |
| B8 | **right** | the directory name, not the file | the whole file |

B1 and B2 want "this file is void". B6 and B8 want "this file is valid, and here
is the part or the name that is not". A marker that can only void a file is
useless for half the cases, and **a marker that can only bless a file is useless
for the other half**, because B6 and B8 must not void anything.

### The five things it must express

1. **Scope of the verdict.** B6's verdict is on `$.committed_ladder`, not on
   `e3-postfix-ladder.json`. Without a JSON pointer the marker is a claim about
   the file, and the file is fine.
2. **Direction: void or superseded-by.** B1 and B2 point forward to a
   replacement. B2 additionally points *backward* to a ref that holds the
   pre-edit bytes, and that is a stronger recovery than any successor. A
   one-directional `supersedes` cannot say "correct as of `d422c93`, damaged as
   of `d183cbe`".
3. **The surviving positive claim.** B6's `$.committed_ladder` is scoped, not
   wrong. A marker that says only "retracted" would tell a reader to distrust the
   one thing that makes the post-fix ladder comparable to the pre-fix one, and the
   correct action is narrower than distrust.
4. **A non-path referent.** B8's referent is a **directory name**, and the file
   itself is correct. Any mechanism keyed on paths cannot express "this file is
   fine, its container lies". `PROVENANCE.md` is the whole of the answer here,
   and a JSON field in the bundle could not be added without editing evidence.
5. **Reachability from the artifact.** Measured: **zero of five** directories with
   a `RETRACTED.md` have any sibling artifact mentioning it, and the B6 ladder
   contains none of the four marker words. A marker a reader must already know to
   open does not close B6.

### What already exists, and what is actually missing

The repo has **two** conventions and they are the two halves of what is needed:

- `RETRACTED.md`, four instances plus B6's fifth. Correct, hand-run, and
  **unreachable from the artifacts they describe**.
- a `supersedes` field in generated JSON (`e2_gate_report.py:242`,
  `e2_reason_probe.py:160`). Correct and reachable, but only for artifacts a
  generator can rewrite, so it is structurally unavailable to every one of these
  four cases.

**The gap is not a marker, it is a way to reach a marker.** Both halves exist;
neither is discoverable from the artifact it describes.

### The smallest shape, if one is wanted later

A sidecar per artifact, named so it sorts beside the file and is matched by
stem, carrying:

```json
{
  "artifact": "reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json",
  "artifact_digest": "<sha256 of the committed bytes>",
  "verdict": "partially_void",
  "void_scope": [{"pointer": "$.committed_ladder", "reason": "N-80"}],
  "superseded_by": "reports/evidence/inv_r1_e3_selection_regen_v2/",
  "void_since_ref": null,
  "valid_at_ref": "d422c93",
  "valid_for": "the pre-fix/post-fix comparison only",
  "container_mislabelled": false
}
```

`artifact_digest` is what makes the marker checkable rather than decorative: a
marker whose digest does not match the file beside it is stale, and a checker can
say so. `verdict` needs at least `void` and `partially_void` to tell B1 from B6.
`valid_at_ref` is B2's backward edge, which no existing convention carries.
`container_mislabelled` is B8, and it is the one field with no precedent in the
repo at all.

**Enforce it with a check, not with discipline.** The marker is what a check
reads, so the check is worth more than the marker. Two predicates, each
falsifiable today:

- every JSON artifact whose `measure_digest` or `run_id` matches another file in
  its directory has a sidecar naming the other
- every sidecar's `artifact_digest` matches the file beside it

The first is the N-79 shape and would have caught B5. The second catches a stale
marker. Both are cheap and neither requires a run.

**The honest limit.** Even this does not make a retraction visible to someone who
opens only the JSON and parses no sibling. That case is B6's, and closing it
requires the artifact to carry the marker, which requires the writer to emit it,
which is unavailable for exactly the files that most need it. A mechanism that
cannot reach a committed artifact can only ever be a convention, and the
convention has to be run by hand. Say so rather than implying otherwise.

---

## Constraint confirmation

- **This pass deleted nothing, and modified no committed evidence file.** The
  five files it added are new prose. Every artifact named above is
  byte-identical to its committed state.
- For completeness, one deletion exists in this branch's history and it is not
  mine: `4b365ed` removed
  `reports/evidence/invl02_liveacq_r2/arm_sw00_r1_refused.json`. It is named
  because a blanket "nothing was ever deleted here" claim would be false, and
  because that file is exactly the kind of record the standing rule protects.
- The pre-edit matrix (`d422c93`) was read with `git cat-file` and never written.
- `ec02test_live` was never contacted. No database was created or dropped.
- Targeted verification only. No test suite was run beyond the single B6 marker
  regeneration, which touches no database.
- The `evidence_s09_e4` tree named in the brief as live under another lane does
  not exist in this worktree, in any of the three other worktrees, or anywhere on
  this filesystem. B1's tree (`inv_r1_e3_selection`) was annotated; no E4 tree was
  touched.
