# Stage 9 milestone gaps: what each PARTIAL is missing

Read at `07fb0d5` on `codex/implementation-investigation-learning-02`. Every claim below carries the
file I opened. No test, generator or experiment was run; this lane is read-only plus this file.

**Two corrections to the brief, both from files on disk.** M3 and E2 are each described here
slightly wrong, and both corrections change the work order rather than softening it.

| Milestone | Specific gap | Deliverable that closes it | Size | Model call | Human-only decision |
|---|---|---|---|---|---|
| M0 | No artifact challenges the 10-row call-chain table in `PLAN-STAGE-09-CONNECTED.md:76-87` edge by edge | `reviews/STAGE-09-M0-TASKGRAPH.md`, one row per edge, each with the challenger's own call site | afternoon | no | no |
| M1 | The 8 behaviour checks at `WORKER-STAGE-09-CONNECTED-STUDY.md:43` have tests but no recorded outcome | `reports/evidence/inv_r1_m1_behaviour/gate-results.json`, the M4 `gate-results.json` shape | one hour + one pytest run | no | yes (N-65, and the rule that counts a test run) |
| M2 | No artifact joins policy artifact and method to their own receipts and effects after live execution; no fresh-process retention/reload proof | `reports/evidence/inv_r1_m2_join/join.json` over run 7/8 receipts, plus a fresh-process reload record | a day | no | no |
| M3 | The one acquired member calls the control's own method, so the tie is a tie by construction; no experience treatment; 330 of 360 calls unspent | a run with a method menu whose default is not the answer, prompts attested per response, and an experience arm | one live run | **yes** | no (N-36 constrains) |
| E1 | `typed-ast` and `action-graph` have 0 SWE cells each; the SWE world is off the common path | unify the view, then a full 3-representation SWE matrix on a frozen instrument | a live run after M2 | **yes** | **yes** (the N-58 fork; N-53 means no Jev dissent) |
| E2 | All three scored arms and both substitution arms selected `seed-sw-ddmin`; the treatment never differs from the control. Transfer is `scored: false`, not negative | a scored run whose arms admit an acquired policy, and a transfer contrast that actually scores | one live run | **yes** | no (N-53) |

## M0 — inventory and bounded plan

1. **Definition.** `WORKER-STAGE-09-CONNECTED-STUDY.md:29`: "Write a short task graph and path
   ownership in the existing PLAN. Trace actual calls, not module names: construction response ->
   acquired artifact -> selected policy -> child/interpreter -> proposed action -> admission ->
   oracle effect -> scored result. Locate the existing implementation of each edge before adding
   code. Ask an independent reviewer to challenge that map and the budget denominations."
2. **Exists.** `reports/PLAN-STAGE-09-CONNECTED.md:76-87`, read, is a 10-row table with exactly
   that chain. The reviewers ran: `reviews/R1-AUTHORITY-RECOVERY.md` (28820 B),
   `R2-EXECUTION-VISIBILITY.md` (27392 B), `R3-VALIDITY-R4-REPRODUCTION.md` (30736 B), committed in
   `bff7d96` and `46cedf8`. All three read (heads and greps). `grep` for "task graph", "call
   chain", "edge by edge" across `reviews/*.md` returns zero hits.
3. **Gap.** R1-R4 reviewed subsystems, not the map. Ten edges, no reviewer verdict per edge. R4 has
   no file of its own; it is merged into the R3 file.
4. **Closes it.** One row per edge, each naming the challenger's own call site, in a file that
   exists. Afternoon, no run.
5. **Human-only.** No.
6. **Model call.** No.

## M1 — repair the authority and budget boundary

1. **Definition.** `WORKER-STAGE-09-CONNECTED-STUDY.md:43`, the eight checks verbatim in the brief.
2. **Exists.** `tests/test_s09cs01_budget_denominations.py`, read, 29 `def test_`, and they map one
   for one onto the eight: `:112` zero-vs-unreported, `:151` request-dependent, `:260` dimensional
   separation, `:465` durable resume, `:358` holds survive, `:405` finite allowance launches, `:477`
   cannot exceed, `:139` unmeasured rather than not-reported. No behaviour-check artifact exists
   under `reports/evidence/`.
3. **Gap.** A test file is source. The rule at `STAGE-09-COMPLETION-MATRIX.md:9` requires a named
   artifact demonstrating the claim, and there is none.
4. **Closes it.** `reports/evidence/inv_r1_m1_behaviour/gate-results.json` in the shape M4 already
   uses (`command`, `source_tip`, `file_digests`, `skips_or_xfails`, `result`). One hour plus one
   pytest run against a disposable DB. **This is the one artifact from this whole report.**
5. **Human-only.** One, and it is a rule call, not a fact. **[N-65 was the other and is
   SETTLED at `94443a7`: 18688 is sourced as `4 × 2294 + 4 × 2378`, a pre-flight sizing,
and r4 holds 2294. See `reviews/STAGE-09-N36-N65.md`.]** The superseded text follows.

   **Human-only.** Two. First, N-65 is OPEN and "not resolvable from this branch": the 18688-unit
   liability figure is in no artifact, against 2294 and 5563 which are backed. A cap sheet must
   state a liability, and the coordinator must pick which number. Second, whether a passing
   covering run counts as M1's artifact is a rule call, and it is the single judgement in this lane
   that flips a status.
6. **Model call.** No.

## M2 — connect the existing representations and worlds

1. **Definition.** `WORKER-STAGE-09-CONNECTED-STUDY.md:51` and `:53`, quoted in full in the block
   above. Note line 47: this pilot is scoped to the Boolean and ordering worlds, and "actual SWE
   transfer remains open".
2. **Exists.** `inv_r1_e1_matrix/matrix.json`, read: 5 conditions x 3 arms, every cell
   `comparable: true`, `incompatibilities: []`. `inv_r1_e1_ordering_matrix/matrix.json`, read: 5 x 3,
   every condition `agree: true, all_pairs_comparable: true`. That is 15 comparable cells per world.
   `inv_r1_e1_swe_ceiling/matrix.json`, read: `path_fork.common_path_usable: false`, `refusal:
   "non-contract-action-kind"`, `run_path: s09_swe_world.run_episode`, `missing_from_swe:
   [hypothesis_class, max_queries, observed]`.
4. **Gap, and the brief has it pointed the wrong way.** `common_path_usable: false` is an E1
   problem, not an M2 one. M2's declared pilot is the two toy worlds, and both run all three
   representations comparably. What M2 still asks for and has no artifact for is line 53: the
   post-live join of each policy artifact and each method to its own receipts and byte identity, and
   the fresh-process retention/reload proof from line 51. I did not open
   `test_s09m2_policy.py` or `test_s09m2_construct.py` and ran nothing, so the deterministic
   qualification half is **UNVERIFIED by me**, not absent.
5. **Closes it.** `reports/evidence/inv_r1_m2_join/join.json` over run 7/8 receipts. A day.
6. **Human-only.** No, provided the join lands. N-36 (the hidden target recovered in 959 ms through
   the in-repo HMAC key) does not block a join.
7. **Model call.** No.

## M3 — prospective, informative live pilot

1. **Definition.** `WORKER-STAGE-09-CONNECTED-STUDY.md:59`: "Include a competent authored control
   with the same oracle/action/compute limits."
2. **Exists, and the brief is stale.** `inv_r1_m3b/RESULT.md:44-48` does say "There is no authored
   control in the run" and scores task utility `not_comparable`. But `CONTROL.md`, 2090 bytes,
   committed 28 minutes later in `370ceb9`, supplies the control and moves the verdict to `tie`:
   0.7692307692307693 and 0.700 on both arms, to the digit. The control is `repertoires/
   control-sw-use-policy.py`, `authored: True`.
3. **Gap.** Not the control, which exists. The control is `reduce_software(..., method="ddmin")`
   and so is the acquired member, so the tie is forced. `CONTROL.md` says so itself: "It is the
   authored baseline wearing an acquired label." Also missing: an experience treatment, and a
   cross-arm comparison. 30 of the cap sheet's 360 calls are spent.
4. **Closes it.** A menu whose default is not the answer, the prompt recorded beside each response,
   and an experience arm. `CONTROL.md` names both. One live run.
5. **Human-only.** No. N-36 constrains the world, not the menu.
6. **Model call.** **Yes**, and deliberately: the fix is a constructor change, so the result cannot
   exist without dispatches.

## E1 — connected comparison plus real SWE

1. **Definition.** `WORKER-STAGE-09-PARALLEL-EXPANSION.md:51`: "Target three representations
   across three worlds with at least four independent acquisition lineages per supported cell."
2. **Exists.** `inv_r1_e1_swe/RESULT.md:1-9`, read, carries the INVALID RESULT banner. The
   replacement, `inv_r1_e1_swe_ceiling/matrix.json`, read, has 468 rows, 12 lineages, 3
   representations, 24 per-family entries. `missing_cells` carries 8 for `typed-ast` and 8 for
   `action-graph`, each with a reason. N-77 I recomputed myself: all four use-policy files hash
   `3011991aaae3`, and `db984e74726b` appears in five files, all prose.
3. **Gap.** Two of three representations have no SWE cell, and the one that ran is off the common
   path. N-58 is OPEN and records the fork: normalise the view to eight fields, which costs
   dropping `source`, or widen the harness, which fabricates `hypothesis_class`.
4. **N-77's reach.** It withdraws the byte-identity argument only. `RESULT.md:19` presents two
   digests as different by construction; they are not. The greedy-vs-ddmin outcome table stands on
   the scores, not on the hashes, so the comparison is not retracted.
5. **Closes it.** Resolve the fork, then a full three-representation matrix on a frozen instrument.
   A live run.
6. **Human-only.** **Yes.** Dropping `source` is a contamination decision, and `source` is the
   program under repair, so the alternative is fabricating a field. N-53 means Jev returns 403 and
   no dissent exists for the E1 decision.
7. **Model call.** **Yes** for the matrix, no for the fork.

## E2 — experience, retention and transfer

1. **Definition.** `WORKER-STAGE-09-PARALLEL-EXPANSION.md:59-63`, five named contrasts.
2. **Exists.** `RETRACTED.md` in `_noexp`, `_relevance` and `_transfer`, all three read. Relevance
   and noexp name N-78 and N-400, but in a subordinate "What is not claimed here" section, and
   attribute the invalidity to the echo, not the empty dispatch. N-78's own text notes a reader
   would not learn that nothing was returned. Transfer names neither. Both arms of relevance carry
   `digest: e3b0c442...` and `prompt_chars: 0`, which is `sha256("")`.
3. **Gap, and it is deeper than N-78.** `readings.json` and `remaining-contrasts.json`, read: all
   three scored arms and both substitution arms carry `selected: "seed-sw-ddmin"`. The treatment
   never differs from the control, so the contrasts compare the seed against itself. Transfer is
   `scored: false, agreement: "absent", selected: ""` on both arms, which is unmeasured, not
   negative. N-400's premise failure is real (843 vs 736 committed, R3 measured 166 vs 59).
4. **Closes it.** A scored run whose arms admit an acquired policy, and a transfer contrast that
   scores. One live run.
5. **Human-only.** No. N-53 only.
6. **Model call.** **Yes.** N-78 means the relevance contrast returned nothing, so re-running it
   requires the gateway.

## Corrected tally

**3 COMPLETE (M4, E3, E4), 6 PARTIAL (M0, M1, M2, M3, E1, E2), 0 BLOCKED.** I agree with the
audit's tally.

**Mislabelled, in the reason, not the status.** M2. The matrix grounds its PARTIAL on the SWE path
fork, but `WORKER-STAGE-09-CONNECTED-STUDY.md:47` puts SWE out of M2's pilot scope and M2's two
declared worlds are fully comparable. Its real gap is the missing post-live join and fresh-process
reload proof, which no document names.

**Mislabelled, upward, on one rule.** M1. It is a missing record, not missing work, and the audit
says so. If a passing covering run counts as the artifact, M1 is COMPLETE and the tally is
4/5/0.

**Two briefs corrected.** M3's "no authored control" is stale by 28 minutes and a commit. E2's "N-78
and N-400 are in neither" is nearly right: relevance names both, in a footnote.
