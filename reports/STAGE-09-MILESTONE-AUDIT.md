# Stage 9 milestone audit

Audits `reports/STAGE-09-COMPLETION-MATRIX.md` against files on disk at `d8436f0`
(`codex/implementation-investigation-learning-02`). Definitions taken from
`WORKER-STAGE-09-CONNECTED-STUDY.md:25-73` (M0-M4) and
`WORKER-STAGE-09-PARALLEL-EXPANSION.md:45-83` (E1-E4). Lane is read-only; no
experiment, generator or suite was re-run. Every status below names a file I opened.

## The headline

The matrix's own header says it was read at tip `dad929a` (`STAGE-09-COMPLETION-MATRIX.md:3`).
Nine commits landed after that tip and are ancestors of HEAD. The largest of them
(`111ec3a`, "E4: a qualified negative") closed the single row the brief predicted would
be wrong, and `3c1e5c5` did the same for E3's ladder. The matrix is not slightly stale; its
two worst rows describe work that has since been done.

`ISSUES`

| Milestone | Matrix claim | Verdict | Strongest evidence | Read |
|---|---|---|---|---|
| M0 | PARTIAL | **PARTIAL** (agree) | `reports/PLAN-STAGE-09-CONNECTED.md:113-117` assigns R1-R4 read-only; no artifact shows a reviewer challenging the task graph edge by edge | read |
| M1 | COMPLETE | **PARTIAL** | `tests/test_s09cs01_budget_denominations.py` — 29 tests, incl. `test_the_prior_exposure_is_still_5563_in_the_same_terms:323`, `test_resume_spends_dispatches_and_never_looks_at_units:465`; but `reports/evidence/` holds **no** behaviour-check artifact (`find` for `*cs01*`/`*behavio*`/`*denomination*` returns nothing) | read |
| M2 | PARTIAL | **PARTIAL** (agree) | `experiments/ad01/s09_arm_parity.py:29` `REAL_REPRESENTATION_KINDS` = 3 kinds; `inv_r1_e1_swe_ceiling/matrix.json` `path_fork.common_path_usable: false` | read |
| M3 | PARTIAL | **PARTIAL** (agree) | `reports/evidence/inv_r1_m3b/RESULT.md:44-48` — "no authored control in the run"; the one member's `ddmin` is the signature default | read |
| M4 | COMPLETE | **COMPLETE** (agree) | `reports/evidence/inv_r1_m4_baseline/tamper-results.json` — `baseline_status: "pass"`, `all_fired: true`, `baseline_deterministic: true`, all 7 examples `expected_problem_fired: true`; `tests/test_s09an_evidence.py` present, 29 `def test_` | read |
| E1 | PARTIAL | **PARTIAL** (agree) | `inv_r1_e1_swe_ceiling/RESULT.md:23-28` — 0 of 24 families in the retracted run; `matrix.json` 468 rows | read |
| E2 | PARTIAL | **PARTIAL** (agree) | `inv_r1_e2_relevance/contrast.json` — both arms `digest: e3b0c442…`, `prompt_chars: 0` (sha256 of empty string) | read |
| E3 | PARTIAL | **COMPLETE as a negative** | `reports/evidence/inv_r1_e3_ladder/RESULT.md:45-49` — "The verdict is INACTIVE on held-out quality"; `e3-postfix-ladder.json` `store_verdict.operations_in_store: 84` | read |
| E4 | PARTIAL, "two files, no result artifact" | **COMPLETE as a negative** | `reports/evidence/inv_r1_e4/result.json` (24403 bytes) `verdicts.acquisition: "no-eligible-revision-acquired"`, `benefit: false` | read |

## Where I disagree with the matrix

**E4 — the brief's suspicion is stale. This is the most important row.**
The matrix's E4 cell says "`inv_r1_e4/` has exactly two files" and section 7.8 repeats it
(`STAGE-09-COMPLETION-MATRIX.md:36,151,403`). As of `d8436f0` the directory holds five
tracked files: `make_result.py`, `result.json` (24.4 KB), `headroom.json`, `make_evidence.py`,
and a `run/` subdirectory with 13 files. `result.json` was added in `111ec3a` at
2026-09-28 01:44:57, an hour after the matrix was committed (`200fee7`, 01:10:24) and both
ancestors of HEAD.

It is a complete result, and a well-evidenced negative. The live campaign **did** run:
6 dispatches, 6/6 returned executable STEP bytes, all 6 refused with
`eligibility: "delegates-to-unchanged-reducer"`. The three apparatus controls all passed.
The null is bounded on both sides — reachable range 0.00622 over 75 unseen tasks, and the
wider evidence decision sits at 0.5017 against the incumbent's 0.0587, so the blocker is
named as the boundary, not the substrate. The matrix's "the live campaign was not run" is
false against disk. Its conclusion (no benefit claim) is unchanged and is now better
supported. Per the hard rules a negative is a complete result, so **E4 is COMPLETE**.

One thing travels with it: `result.json` records an **authority deviation** — the six
dispatches went through `HttpGatewayAdapter` directly, not the durable
reservation/dispatch owner that `WORKER-STAGE-09-PARALLEL-EXPANSION.md:91` forbids. The
result text argues the measurements survive this; I have no way to check that from disk, and
it is why E4 is COMPLETE as an experiment but not as an authority-conformant run.

**E3 — the retracted ladder was regenerated, and the verdict is a negative.**
The matrix's E3 cell (`:35`) says the ladder "has not been regenerated" and that
`e3-crossover.json` sits unannotated. Both were true at `dad929a`. At HEAD:
`inv_r1_e3_selection/RETRACTED.md` (added `4df45b2`) annotates the withdrawal with three
independent causes — N-80, N-405, N-413 — and names what survives. The replacement is at
`reports/evidence/inv_r1_e3_ladder/`: `RESULT.md` plus a 165 KB `e3-postfix-ladder.json`
and a 22-test gate at `tests/test_s09_e3_ladder.py`.

The result is a real negative with a direction that reverses: the agenda leads on
held-out quality at budgets 14, 20, 30 and the control leads at 8, 40, 60, with the
control's margin growing (0.359 / 0.391 against 0.145 / 0.206). `RESULT.md:45` calls the
treatment INACTIVE on held-out quality. The treatment itself is active — 18 of 18 cells
diverge on first choice — which is precisely the check
`WORKER-STAGE-09-PARALLEL-EXPANSION.md:73` demands before a benefit claim, and it is why
this is a complete result rather than an inactive arm. **E3 is COMPLETE as a negative.**

**M1 — the one downgrade, and it is a rule application, not a discovery.**
The matrix calls M1 COMPLETE on the strength of a cap sheet, a freeze, accounting, and
source at `s09_route_cost.py:42`. The claim that keeps it there is the matrix's own
concession: "Not established: that any of the required behaviour checks were re-run."
`WORKER-STAGE-09-CONNECTED-STUDY.md:43` lists eight required behaviour checks
(null-versus-zero billing, request-dependent reservation estimates, dimensional
separation, durable resume consuming only the remaining count, old uncertain holds
surviving, a finite new allowance launching without settling holds, launches unable to
exceed the allowance, an unsuccessful response recorded as an attempted effect).

Tests for these exist and are specific — `tests/test_s09cs01_budget_denominations.py`
names them one for one. But a test file is source, not a result: under the stated rule
that COMPLETE requires a *named file demonstrating the claim*, and that lane self-reports
do not count, M1's behaviour checks have no artifact anywhere under
`reports/evidence/`. Per that rule M1 is **PARTIAL**. The missing artifact, by name: a
behaviour-check result under `reports/evidence/` (none exists; `reports/evidence/inv_r1_m3/`
holds the cap sheet and accounting, not a check outcome).

I want to be exact about the weight of this. It is a downgrade the matrix's own text
invites, on a milestone whose substance is genuinely repaired — the four denominations
are separated in types and in the committed cap sheet, and the eight behaviours are
covered by 29 named tests. If a passing test run is acceptable as the artifact, M1 is
COMPLETE and my tally is 4 COMPLETE. On the rule as written, it is PARTIAL.

**Rows I did not change.** M0, M2, M3, E1, E2 keep their PARTIAL status, and I agree with
the reasoning, which is the matrix's strongest work.

## The named suspicions, checked

- **E4 missing result artifact — no longer true.** See above. The brief's "verify rather
  than trust" instruction was correct to give; the answer is that it was repaired.
- **E1 / N-77 — does not retract E1.** I recomputed all three digests: `sha256sum` over
  `acquired-greedy-use-policy.py`, `control-sw-use-policy.py`, `m3-fallback-use-policy.py`
  returns `3011991aaae335d9…` for all three. That confirms N-77 exactly. But
  `inv_r1_e1_comparison/RESULT.md:19` claims `cfadd1a52120` and `db984e74726b`, and
  `grep -rl db984e74726b` finds it in four files, all of them prose
  (`RESULT.md`, the matrix, the findings ledger, R3) — **no artifact reproduces it**.
  N-77 is OPEN and unretracted; it withdraws the *byte-identity argument*, not the
  outcome table, which stands on other evidence. E1's PARTIAL rests on a different and
  firmer ground (two of three representations have no SWE cell).
- **E2 / N-78 and N-400 — both confirmed, neither annotated.** `contrast.json` records
  `digest: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` and
  `prompt_chars: 0` in both arms, and asserts `relevant_chars: 382, irrelevant_chars: 382`.
  The first is sha256(""); the second is contradicted by the committed prompts (843 vs
  736, per N-400). `RETRACTED.md` names neither cause. E2's PARTIAL is correct.
- **E3 / N-79 — still unannotated.** `e3-store-witness.json` and
  `e3-admitted-operations.json` share a `measure_digest` and disagree (0 vs 5 operations).
  The new `RETRACTED.md` does not mention N-79. The ladder run supplies the modern
  replacement (`store_verdict.operations_in_store: 84`, verified by SELECT), so the
  substantive gap is closed, but the N-79 pair is still unmarked.

## Milestones with no artifact at all

None, at this tip. Every one of the nine rows resolves to a file I opened. The two
predictions of a missing artifact were both false at HEAD: E4's `result.json` and E3's
`inv_r1_e3_ladder/` both exist.

The closest thing to a genuine absence is M1's behaviour-check outcome, which has no
`reports/evidence/` artifact — but it has 29 covering tests, so it is a missing record
rather than missing work.

## Corrected tally

**3 COMPLETE, 6 PARTIAL, 0 BLOCKED, 0 UNVERIFIED.**

(M4, E3, E4 COMPLETE; M0, M1, M2, M3, E1, E2 PARTIAL. If M1's covering test run is
accepted as its artifact: 4 COMPLETE, 5 PARTIAL.)

Against the matrix's 2 / 7 / 0: E3 and E4 move up on artifacts that landed after its tip,
and M1 moves down on the rule the matrix itself adopted and did not apply to itself.
