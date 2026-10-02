# Stage 09: retired evidence, written up before anything is annotated

Branch `codex/implementation-investigation-learning-02` at `1f592d9`. Lane R4. Read-only on
`reports/evidence/`; nothing there was modified, moved, deleted, renamed or annotated. Every
figure below was measured against the file at this tip, not against a status document.

---

## B3 — N-77, E1 acquired-vs-control byte digests

**1. Files.** `reports/evidence/inv_r1_e1_comparison/RESULT.md`, `acquired-greedy.json`,
`control-sw.json`, `acquired-greedy-use-policy.py`, `control-sw-use-policy.py`,
`m3-fallback-use-policy.py` — all six on disk. Two further use-policy files outside that
directory also on disk and also identical: `reports/evidence/inv_r1_m3b/repertoires/control-sw-use-policy.py`
and `.../repertoire-w2-I-use-policy.py`.

**2. Offending data.** `RESULT.md:15` and `RESULT.md:16`. The digests themselves: the three
`.py` files in that directory, whole file. `control-sw.json:16` and `:30` for the declared
`source_digest` fields.

**3. Literal evidence.** `RESULT.md:15-16` reads "Bytes hashed `cfadd1a52120`." and
"the authored `seed-sw-ddmin`, bytes hashed `db984e74726b`." Measured with `sha256sum`:
all five use-policy files on disk return `3011991aaae335d9d060a25d75096697243e17f33f986d64ee92738933246a06`.
`sha256(method_source)` over the two `control-sw.json` members returns `c9f1f7f70d58…` for
both, against declared `e2ca3cf190c2…` and `0ba85e817788…`. A repository-wide hash sweep
found no file matching `db984e74726b`. `grep -rl` finds that string in **7** files, all
prose: `reports/evidence/inv_r1_e1_comparison/RESULT.md`,
`reports/STAGE-09-COMPLETION-MATRIX.md`, `reports/STAGE-09-EVIDENCE-FINDINGS.md`,
`reports/STAGE-09-MILESTONE-AUDIT.md`, `reports/STAGE-09-MILESTONE-GAPS.md`,
`reviews/STAGE-09-FINDINGS.md`, `reviews/R3-VALIDITY-R4-REPRODUCTION.md`. The prior
audit's count of four, and the sibling lane's five, are both stale at this tip.

**4. Provenance.** `git log --diff-filter=A` puts `RESULT.md` and all three `.py` files at
`4512c78` (2026-09-26 21:22:57). The commit message asserts it: "The acquired policy and
the authored control executed different bytes (cfadd1a52120 against db984e74726b)".
`m3-fallback-use-policy.py` arrived later at `4baa299`. So `db984e74726b` was never
computed from a file; it entered the record in the commit message and was copied into
prose. `cfadd1a52120` by contrast **does** verify, as `sha256(method_source)` over
`acquired-greedy.json:16`.

**5. What is unsupported.** The heading sentence "Different bytes, different per-task
outcomes, identical total" (`RESULT.md:27`) asserts byte distinctness that no artifact
shows. Worse, the two repertoires were never textually distinct to begin with: both
`control-sw.json` members carry byte-identical `method_source` and differ only in a
`params` field.

**The audit's reading is half right, and I am refining it.** The claim that N-77
withdraws the byte-identity argument and not the outcome does not hold at the table's
level. Measured against every committed use record on the three tasks:

- Acquired column (`5`, `10`, `8`) is backed. `evidence-ad01/c3-trajectories-merged/use-w1-I.json`
  records `final_measure` 5 / 10 / 8 for `ad01-w1-within-sw-00` / `-01` / `ad01-w1-transfer-sw-00`,
  with `normalized_reduction` 0.375 / 0.23076923076923078 / 0.2727272727272727, matching
  the table's four-decimal figures exactly.
- Control column (`6`, `9`, `8`) is **not** backed by anything. Across
  `evidence-ad01/*/use-*.json` and `reports/evidence/**/use_records*.json`, no record for
  those three tasks carries `final_measure` 6 or 9; the only software-baseline records on
  them (`evidence-ad01/c3-authored/use-w1-I.json`) give 3 / 3 / 3 executing `seed-sw-greedy`.
  A search for any committed use record whose JSON mentions `ddmin` on these tasks returns
  **zero**.

The control column is at least internally coherent: with the correct `initial_measure`
values 8, 13, 11, the claimed finals imply reductions 0.2500, 0.3077, 0.2727, which match
the printed parentheticals. So it is unattested rather than arithmetically invented, but
the tie (23 against 23) rests entirely on that unattested half. N-77 should therefore
withdraw **the whole table**, not only the byte argument.

**6. What a correct artifact would contain.** Two `source_digest` values recomputed and
committed beside the repertoires; the control's `method_source` text that is actually
distinct from the acquired one, or an explicit statement that both reduce to the same
source and differ only in `params`; and use records for the control arm, with
`record_id`, `executed_source`, `final_measure` and `normalized_reduction`, on disk. A
verdict line that separates "the arms chose differently" (supported) from "the arms
executed different bytes" (not supported).

**7. Safe to touch?** Yes, for annotation. Nothing here is load-bearing for a
regeneration decision, and the `RESULT.md` sentence is self-contained prose. Deleting the
directory is not necessary and I do not recommend it: the acquired column is real data
and the two repertoires are the only record of the menu design. I would not regenerate
either — the run that produced the control column left no committed record, so
regeneration would produce a different comparison, not a corrected one.

---

## B4 — N-78 / N-400, E2 relevance contrast

**1. Files.** `reports/evidence/inv_r1_e2_relevance/{RESULT.md, contrast.json, prompts.txt, RETRACTED.md}`
— all four on disk. `reports/evidence/inv_r1_e2_transfer/{RESULT.md, contrast.json, RETRACTED.md}` —
all three on disk. `reports/evidence/inv_r1_e2_noexp/{RESULT.md, contrast.json, RETRACTED.md}` —
all three on disk. The coordinator's correction is confirmed by reading the files.

**2. Offending data.** `_relevance/contrast.json` key path `$.relevant.digest`,
`$.irrelevant.digest`, `$.relevant.prompt_chars`, `$.irrelevant.prompt_chars`,
`$.relevant_chars`, `$.irrelevant_chars`. `RESULT.md:27-30` is the sentence that leans on
the equal-length claim.

**3. Literal evidence.** Both arms, quoted:
```
"digest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
"prompt_chars": 0,
```
That digest is `sha256("")`. `contrast.json` asserts `"relevant_chars": 382` and
`"irrelevant_chars": 382`. Measured from `prompts.txt` by splitting on the two
`=== ARM ===` markers and stripping the `Prior observations:` line: relevant block 843
characters, irrelevant 736, both 656 with that line removed, experience payloads 165 and
58. So the blocks are unequal by 107, and the payload is lopsided by 107.

**4. Provenance.** `contrast.json`, `prompts.txt` and `RESULT.md` all added at `9f76c75`
("Score the E2 relevance contrast on the live route"). The retraction files were added at
`567efae`, and `RETRACTED.md` in `_relevance` was rewritten at `4df45b2`.

**5. What each retraction does and does not cover.**
- `_relevance/RETRACTED.md` is complete for this directory. N-78 and N-400 are **top-level**
  causes, at lines 11 and 29, each with its own `##` heading. It also has a section at
  line 74, "What the previous notice got right, and what it got wrong", which explicitly
  **rejects** the echo attribution: "That was wrong, and it named a different defect with
  a different fix". Any write-up attributing this directory's invalidity to the
  `diagnostic` echo would contradict the file. It does not restate the 843/736 measurement
  as its own claim, and line 92 records N-78 and N-400 as "recorded, not repaired".
- `_transfer/RETRACTED.md` names **neither** N-78 nor N-400 — `grep` returns zero hits. Its
  only cause is the `diagnostic` echo, and it is byte-identical to `_noexp/RETRACTED.md`
  (both 15 lines, same body). `_transfer/contrast.json` does carry the same unsupported
  number: `"chars": 382` in both arms with `"equal_length": true` (lines 18, 23, 28). The
  arm ids differ in length — `ad01-w1-dev-sw-00` against `ad01-w1-dev-gr-00` — which the
  directory's own `RESULT.md:19-20` names as the reason the first fixture failed. Unlike
  `_relevance`, `_transfer` commits no `prompts.txt`, so the N-400 defect is **unmeasurable
  there** from committed bytes, not merely unannotated. It records no `digest` or
  `prompt_chars` field, so N-78 cannot be assessed for `_transfer` at all.

**6. What a correct artifact would contain.** For `_transfer`: the rendered prompt blocks
committed alongside `contrast.json`, as `_relevance` did, so the equal-length invariant is
checkable; and, if N-400 applies, the character count recomputed from those bytes.

**7. Safe to touch?** `_relevance` needs nothing; it is correctly annotated and further
annotation would be noise. `_transfer` is safe to annotate now — its files are read-only
evidence and no lane is regenerating them. I recommend annotating, not deleting: the 2×2
in `_e2_challenge/RESULT.md` is the refutation and the directory is its input.

---

## B6 — N-80, E3 retracted ladder unannotated

**1. Files.** `reports/evidence/inv_r1_e3_selection/RETRACTED.md` and
`reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json` — both on disk.
`reports/evidence/inv_r1_e3_ladder/` has `RESULT.md` and `e3-postfix-ladder.json` and
**no** `RETRACTED.md`.

**2. The unannotated artifact, and whether it is N-80's.** It is a **different one**.
N-80 names `inv_r1_e3_selection/e3-crossover.json`, and that file is now covered: its
directory's `RETRACTED.md` Cause 1 (line 11) names the file by name at line 24, and the
measure I ran on it confirms Cause 1 — the control's `resources_used_total` series in
`e3-crossover.json` is flat at 46 from budget 20 onward, the signature of one stateful
instance. The genuinely unannotated withdrawn ladder is embedded **inside the post-fix
file**, at JSON key path `$.committed_ladder` in
`reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json`.

**3. Literal evidence.** `$.committed_ladder` carries
`"policy_instance_scope": "shared-across-worlds"` and
`"path": "reports/evidence/inv_r1_e3_selection/e3-crossover.json"`, plus its own
`"agenda_ahead_on_held_out_at": [14, 60]` and `"control_ahead_on_held_out_at": [20, 40]`.
I compared it against `e3-crossover.json`: the `choices`, `held_out_reduction_mean`,
`resources_used_total` and `yield_totals` values are **identical at all six budgets**, and
`e3-postfix-ladder.json`'s top-level `measure_digest` equals `e3-crossover.json`'s
(`ce5a140aff83bccc55a916958fdbaf568cb7c576d5c6a66361510181c83cf7e8`), and both match
`$.regenerated_shared`. So it is a byte-level re-embedding of the withdrawn ladder. The
file contains no retraction marker: string counts over the whole 165 KB document are
`retract` 0, `withdrawn` 0, `invalid` 0, `superseded` 0.

**4. Provenance.** `e3-postfix-ladder.json` added at `3c1e5c5` ("E3 post-fix ladder:
treatment INACTIVE…"). `inv_r1_e3_selection/RETRACTED.md` added at `4df45b2`, which is an
ancestor of HEAD.

**5. Why it is unsupported.** `$.committed_ladder` is a withdrawn result, re-serialised
under a key that names no withdrawal. A reader who opens the post-fix artifact and reads
`committed_ladder` sees the pre-fix numbers with a `path` pointer, and the directory's
`RESULT.md` does explain the withdrawal in prose (lines 3-5 and 11-26) — but the data
itself carries nothing. This is the B7 structural gap in its concrete form: git history
records that the ladder was withdrawn, and the artifact does not.

**6. What a correct artifact would contain.** A marker in the data. Either
`"status": "withdrawn"` with the superseding path, or the same fields the sibling
retraction uses. The prose in `RESULT.md` is not sufficient, because the JSON is what a
machine reads.

**7. Safe to touch?** Yes, and it is the safest of the three. Adding `RETRACTED.md` to
`inv_r1_e3_ladder/` and a status key to `$.committed_ladder` changes no measurement. I
would **not** delete `$.committed_ladder`: it is the bridge that lets a reader compare
pre-fix against post-fix, and deleting it would break that comparison permanently.

---

## Artifacts I did not read

- `reports/evidence/inv_r1_e1_swe_ceiling/RESULT.md` and `matrix.json`, and the whole of
  `reports/evidence/inv_r1_e1_swe/`, `inv_r1_e1_matrix/`, `inv_r1_e1_ordering_matrix/`,
  `inv_r1_e1_second_world/`. I read the first 60 lines of `_swe_ceiling/RESULT.md` and
  grepped all four for the digests; none mentions `db984e74726b`, `cfadd1a52120` or
  `3011991aaae3`. **UNREAD in full.** The brief names `_swe_ceiling` as a comparison
  directory; on inspection it is the SWE-ceiling re-run and has no byte-identity claim, so
  the brief's pointer appears to be off by one directory. Flagging rather than assuming.
- `reports/evidence/inv_r1_e3_selection/{e3-store-witness.json, e3-admitted-operations.json,
  e3-sever-control.json, e3-divergence.json}`. These are B5's and B1's, owned by another
  lane. I read `e3-crossover.json` in full and the directory's `RETRACTED.md` in full.
- `reports/evidence/inv_r1_e2_challenge/*.json` (three files) and its `RESULT.md` beyond
  the `grep` for `382`, which returned no hits. I did not verify the 2×2 the retractions
  cite; that is a claim I inherited, not one I measured.
- `evidence-ad01/c3-authored/` in full. I read the single `ad01-w1-within-sw-00` record
  and enumerated `final_measure` across all its use files.
- `reviews/*.md` and the other `reports/*.md` were read only at the lines quoted, by
  `grep` and `sed`. I did not read them whole.

## Are all three safe to annotate?

Yes. The precondition this lane existed to establish is met. Every file cited is on disk
and unedited at `1f592d9`, the git history for each is pinned above, and no artifact
needs to be regenerated for the annotation to be written — the defect is in prose or in an
unmarked key, not in bytes a regeneration would change. Of the three, B3 is the one that
should change a decision: `TASKS.md` B3 currently reads "withdraw the byte-identity
claim", and the measurement says the outcome table's control column is unattested too, so
the correct scope is the whole table. B4 needs no action in `_relevance` and one
annotation in `_transfer`. B6 is unblocked in both directions.
