# Superseded: the E3 store witness. Replacement in `_regen_v2/`

`e3-store-witness.json` and `e3-sever-control.json` are superseded. Both are
kept **unedited** because they are the only surviving record that these
defects existed, and deleting them would destroy the evidence for their own
retraction. Nothing in this directory was modified, moved, renamed or deleted
in producing the replacement.

- **Replacement:** `reports/evidence/inv_r1_e3_selection_regen_v2/e3-store-witness-v2.json`
- **Generator:** `experiments/regen_v2/regen_e3_store_witness.py`, which calls
  the committed `experiments/ad01/s09_e3_selection.py:419` `store_witness`
  through the committed `write_sever_evidence` at line 517.
- **Write-up:** `reports/STAGE-09-EVIDENCE-FINDINGS.md`, items B1 and B5.

## B1 / N-300 — the severed arm records four receipts against an empty binding list

`$.severed.bindings` is `[]` while `$.severed.receipts` holds four populated
receipts, and `$.severed.operations_in_store` reads `0` beside them. The same
contradiction is duplicated under `$.store_witness_severed` in
`e3-sever-control.json`. Every `refused_decisions` entry in that arm carries
`"operation_id": ""`, so the arm simultaneously claims four settled successful
operations and a refusal of every decision.

**Cause.** Not a hand edit. At `52235a6`, `bindings` was the only source of the
receipt id list, so severing it emptied the list passed to `read_back` while
the receipts already in flight were still written. The current generator
derives `receipts` from `run.operations` at
`s09_e3_selection.py:501`, and `read_back` short-circuits on an empty list at
line 390, so `bindings: []` and `receipts: []` now travel together.

## B1, second half — the connected arm's `0` was a sampling-order artifact

`$.connected.operations_written_by_the_run` and `$.connected.operations_in_store`
both read `0` beside **5** settled receipts. The write-up recorded this as the
half that regeneration alone would not fix, and it was right to say so about
the code as it stood at `52235a6`: the count was taken at line 529, the run at
line 530 and the count again at line 532, all before the binding loop at line
534 that called `broker.ensure_operation`. A correct run of *that* generator
produces `0`.

**HEAD is not that code.** The writes moved inside the run
(`run_policy(..., dsn=dsn)` at line 444, admitted through
`selection.DecisionRecorder` inside `selection._run_development`), so the count
is now taken across a run that has already written. Measured on an isolated
database, the committed generator produces `5` against its own 5 receipts.

So both halves are closed, but not by regeneration alone. The severed arm was a
generator defect that a later commit fixed. The connected arm's `0` was an
ordering defect in `52235a6` that only a later commit could fix, and it did.

## B5 / N-79 — five files shared one `measure_digest` and reported two answers

Ten `measure_digest` sites across five committed files all equal
`ce5a140aff83bccc…`, while `operations_written_by_the_run` reads `0`, `0` and
`5` in them. The digest freezes the measure set, so it is identical across
every artifact of the study **by construction** and cannot discriminate two
runs. A reader invited to treat a shared digest as a shared measurement has no
way to tell the files apart.

The replacement publishes `run_digest` beside it, a digest over the run's own
operation ids, and both arms' values are in the artifact. They differ.

## What is still wrong in this directory

`RETRACTED.md`'s "What survives" bullet (line 70) says the severed arm "admitted 0
and wrote 0". That is the contradicted half of the contradiction: this
directory's own `e3-store-witness.json` records 4 receipts for that arm. The
retraction notice is not edited, per the brief for this lane, so a reader who
trusts it will still trust the witness. Read it with this file.

The `_regen_v2` artifact does not retract `e3-crossover.json`, which is
covered by `RETRACTED.md` cause 1 (N-80), nor `$.committed_ladder` inside the
post-fix ladder, which is annotated separately. See
`reports/evidence/inv_r1_e3_ladder/RETRACTED.md`.
