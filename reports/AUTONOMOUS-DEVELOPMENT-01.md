# Autonomous Development 01 report (C3 construction/use controls via callback learner; C4 incomplete live qualification)

Branch `codex/implementation-executable-coordination-02`, integration lane
`repair/ec02-acquire-continuity`, this revision written at `ccbe25f`,
extending the `bfe1006` report with the granted live C4 execution (C5). The
prior C3 QUALIFIED label was not accepted by the BDF12D5 review
(`reviews/EC02-AD01-BDF12D5-REVIEW.md`): the artifacts were "reproducible
authored trajectory/seed-use fixtures; not the assigned broker-backed model
construction and autonomous trajectory qualification." This revision records
the requalification with corrected accounting and maps every AD gate to its
actual disposition. The prior as-run evidence under
`evidence-ad01/c3-trajectories/` remains committed and unchanged.

## Diagnostic accounting (this batch, `7a4f9eb`)

Three accounting defects the review cycle surfaced are closed:

- Graph diagnostics ran two greedy reductions under independent eight-query
  oracle budgets, discarded both query counts, and booked spend 1. The
  boundary now shares the remaining trajectory query allowance between the
  reductions and books their measured queries (full reductions cost 23–31
  queries each on the frozen tasks, measured).
- Construction-cap refusal returned the seed observation with zero spend
  after the diagnostic had already executed; the boundary now returns the
  executed observation, its queries, and its spend, tagged with the
  diagnostic observation id.
- The fresh-process path derived acquisition queries from
  `campaign["queries"]` alone, so a frozen repertoire accounted zero; the
  repertoire now persists its queries and `cost_union` falls back to the
  durable boundary spends in `attempt_observations`.

The R-arm rotation test previously passed only because graph queries were
never counted; it is resized to the controls' measured cost (160 queries).

## C3 qualification (requalified at merged tip, deterministic doubles)

`evidence-ad01/c3-trajectories-merged/` (committed at `bfe1006`):

- 6 trajectories (3 worlds × I/R), 72 fresh-process use records, exit clean.
- Recording adapter at the learner/constructor seams; doubled gateway only;
  DB `ec02test_c3`; no live calls.
- Every trajectory retains acquired programs: I retains
  `acquired-sw-58d90427`; R retains `acquired-sw-58d90427` and
  `acquired-gr-9fac7a86`.
- Acquisition witness queries now appear in every accounting export: 31 (I)
  and 47 (R) per trajectory, where the prior runs recorded none.
- Boundary spends and dispositions changed where the old accounting had
  silently zeroed the third boundary's budget: the I arm now executes its
  third development under the real remaining budget and ends rejected at the
  lineage cap instead of stopping at "zero construction budget". More real
  work executes and is accounted; both old and new evidence stay committed.

Reproduce: `AD01_AGENDA_AUTHORIZED=1000 python -m
experiments.ad01.run_c3_qualification evidence-ad01/c3-trajectories-merged`
against a disposable PostgreSQL `EC02_C3_DSN`.

Scope (84D2094 IR-02, preserved): this battery proves construction/use
controls, not the full common learner path or outside-menu acquisition.
`run_c3_qualification.py:90` passes `_recording_learner(...)` directly as
`propose`, bypassing the broker/model learner path; I and R receive
different preselected task lists and I carries an extra task-specific
zero-query budget; `ACQUIRED_SW`/`ACQUIRED_GR` are authored wrappers
around existing greedy reducers recorded as test vectors. The public
fresh-process use and the checked 72 records are accepted at that scope.

## AD gate dispositions (C3, deterministic doubles)

| Gate | Disposition | Evidence |
|---|---|---|
| AD-01 initiative | Qualified at callback scope | I reorders a preselected visible set, R follows the frozen rotation, with different preselected lists and an extra I zero-query budget; same recording callback after |
| AD-02 investigation | Qualified | Diagnostics yield attributed observations feeding the next packet, now charged to the trajectory query budget |
| AD-03 executable change | Qualified | Retained bytes execute out-of-process through the bounded profile; zero budget yields explicit no-candidate |
| AD-04 negative knowledge | Qualified | Rejected work inspectable via NegativeLedger (preserved) |
| AD-05 continuity | Qualified | PG resume + fresh-process CLI proof; schedules persisted with payload digests (`5451b8b`) |
| AD-06 retained use | Qualified | 72/72 checker-clean in fresh-process use; retained-byte execution 45/72 with 27 on incumbent (9 fallback under allocation refusal, 18 incumbent from start; INV-E-02) |
| AD-07 fair comparison | Not met as a fair comparison | Benefit rule recomputed per arm, but I/R had non-equivalent initial opportunities and resources, so the no-benefit readout on doubles proves the path ran, not that a fair learning comparison occurred |
| AD-08 agency boundary | Qualified | Charter/decision envelopes preserved; `_target_refusal` refuses cross-split targets (verified live in the R-arm trace: outside-curriculum targets are refused before diagnostic/model work) |

## BDR dispositions (BDF12D5 review)

- BDR-01 (candidates exec in trusted host): closed; `_run_member` routes
  acquired methods through `method_exec.run_member_out_of_process` (bounded
  local-process profile, host-owned query budget, JSON oracle verdicts).
  Local-process is process separation, not hostile containment; real-runsc
  deployment qualification remains separate as designed.
- BDR-02 (same inference identity per child/rework): closed; child operations
  key on `team.child_operation(dsn, plan_id, node)` per node and invocation.
- BDR-03 (accepted targets cross the protected split): closed;
  `_target_refusal` binds every action to the boundary's curriculum item.

## C4 (live AD01, incomplete live qualification, not a completed comparison)

Authority: 260000 agenda units (`AD01_AGENDA_AUTHORIZED`), reasoning effort
high (the gateway route rejects low/medium with 400), model
kilo/kilo-auto/free, fresh disposable DB per retry (settled
learner/construction responses replay by operation ID, so each retry needs
a fresh DB: live4 through live15). The agenda declaration alone does not
establish an aggregate cross-database grant or whole-campaign
reconciliation; per-database identities, per-episode frozen configuration
and source revisions are unrecorded in the traces. Evidence
`evidence-ad01/c4-live/` holds 11 JSON/log pairs, not twelve: nine
readable traces plus zero-byte JSON stubs for live11 and live13 (live13
has a zero-byte log as well). All readable traces are world 0 with zero
retained members and zero use-phase records: one I trace, one baseline R
trace, one resume trace, and R traces live7, live8, live9, live10, live11
(stub), live13 (stub), live14 and live15. No live4/live5/live6/live12
pairs exist in-repo. Per-attempt detail is in
`reports/workstreams/inv-a-c4-ledger.json`. Calls counts durable
model-inference operations (`accounting.total.model_calls` in each
`evidence-ad01/c4-live/<trace>.json`; `resume-w0-R.json` holds 5 over 5
operations, so its row reads 5; INV-E-01).

| Trace | Calls | Dev | Constr | Outcome |
|---|---|---|---|---|
| live7 R | 3 | 0 | 0 | no-candidate throughout: unknown action kind; two curriculum refusals |
| live8 R | 7 | 1 | 4 | one dev episode, construction exhausted without a checkable candidate |
| live9 R | 3 | 0 | 0 | invented basis refs; one inspected; graph/software family mismatch |
| live10 R | 7 | 1 | 4 | malformed basis refs; one dev episode, construction exhausted |
| live11 R | — | — | — | implementation failure, not infrastructure loss: runner crashed (EXIT=1) on an assertion in `controls.diagnostic_resolves` on a mismatched family; empty JSON stub preserved |
| live13 R | — | — | — | unclassified: zero-byte JSON and log stubs, cause unrecorded |
| live14 R | 3 | 0 | 0 | no settled responses on all 3 learner calls, unknown aggregate usage; cause unclassified without transport/provider evidence |
| live15 R | 3 | 0 | 0 | no settled responses on all 3 learner calls, unknown aggregate usage; cause unclassified without transport/provider evidence |
| trace-w0-I | 6 | 1 | 3 | one rejected dev episode, two unsettled learner calls |
| trace-w0-R | 3 | 0 | 0 | baseline R trace: 3 no-candidate episodes, no settled learner responses |
| resume-w0-R | 5 | 1 | 2 | one inspected, one rejected dev episode, one unsettled learner call |

The admission seams held with a named reason: `_target_refusal` refused
outside-curriculum targets before diagnostic/model work (live7, live8,
live10); the import-consequence prompt and exact-basis-refs checks refused
invented references (live9, live10); the family guards refused
diagnostic/development kind mismatches (live9); the construct fence held on
exhausted construction (live8, live10, I, resume). Learner output is
bare-JSON-only with code-fence stripping at the parser. The seq2 curriculum
miss stands accepted as model noise with an ACCEPT verdict; no further
prompt growth for it. Attempt-observations vs observations layering is
pinned NO-BUG by design with a test.

No trace retained a member, so retention stays zero and the use phase stays
unrun: the comparison is incomplete, not a completed negative.
Deterministic replay of the C3 corpus is unaffected (72/72 clean, measured
this batch). These are diagnostic attempts, not the assigned three paired
worlds and 72 protected-use records.

## Next bottlenecks (ranked, ≤3)

1. **Model-facing interface semantics** (AD01/C4, IR-01): construction
   prompts omit the task contract content and the just-produced diagnostic
   is not delivered to construction. Discriminating test: the prompt
   changes when task structure or diagnostic detail changes.
2. **Resource authority continuity** (AD01/C4, IR-03): one authoritative
   remaining allowance at every admitted effect, including diagnostics,
   failure and restart. Discriminating test: construction receives the
   post-diagnostic remainder, never the pre-diagnostic allowance.
3. **Candidate executability** (EC02/C2): lineage 1 probed without ever
   proposing a plan and lineage 2 failed the plan schema. The
   construction prompt needs a plan-proposal obligation, and lineage 2
   needs its own schema failure as repair feedback, before any further
   grant is meaningful.

## Final integrated gate (shared with the EC02 report)

Merged tip `ccbe25f`, serial full suite on disposable DBs: 1329 passed,
1 xfailed in 3453.30 s; the xfail is the unrecoverable `acquire2` import
(see `reports/EC02-CLOSURE.md`). `ec02test_live` receipts remain 16,
untouched and remote (not independently verified here). Declared spend
stayed at EC02 4/4 construction calls on `ec02test_c2live8` and inside the
260000-unit AD01 agenda declaration; with no grant documents, no
per-database spend records and six readable C4 traces at unknown aggregate
tokens, no breach and no total external spend is determined here.
