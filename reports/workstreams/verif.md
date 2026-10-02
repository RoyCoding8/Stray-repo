# T-VERIF independent verification report: EC02 C1 gate + challenges 1–4

Independent re-verifier. No production file, existing test, or other
lane path edited. All claims falsified-first with independently chosen
counterchecks on the merged tip; defects recorded, never fixed.

- Verified base (merged tip): `3d697b8` (branch
  `codex/implementation-executable-coordination-02`); re-verified on
  repair tip `4038e3e` (coordinator VERIF-D1/D2/D3 repairs + M2 stub,
  child of the `dc813d3` verif merge)
- Verif branch: `wt/ec02-verif`, fast-forwarded to `4038e3e`, plus
  owned test amendments (pushed; additive commits, Nightjar identity,
  no force-push)
- Battery: `tests/test_ec02ad_verif.py`, 28 tests, 28 green on the
  repair tip
- Lane DBs: `ec02test_verif` (all PG tests) + `ec02test_verif_sentinel`
  (protection proof only). `ec02test_live` never touched.
- Doubling boundary: labeled recording doubles ONLY at the model seam
  (`VerifRecordingAdapter`, `FlakyGateway`); real PG + real subprocesses
  everywhere else. No live gateway exists in this lane — every endpoint
  that could reach one is doubled, all others are real.

## C1 verdict: PASS (re-verified after repair)

The real public campaign path (`run_cell`/`run_panel` via `entry`,
`main` adapter wiring) admits model output into work, grades submitted
bytes, refuses over-budget attempts before child dispatch, continues
through poisoned reference loaders, recomputes multi-op nonuniform
unions from durable rows, races final capacity deterministically, and
resumes interrupted campaigns without repeating settled effects — all
against isolated PG with independently shaped recording outputs (own
task `c02-t02`, own obligations, own usage 13/17, own UUID markers).
VERIF-D1/D2/D3 were repaired by the coordinator on `4038e3e` and are
re-verified closed below (amended rejecting checks green on the repair
tip). One recorded limitation remains (EC02 panel-level resume); it
does not block the gate.

## Re-verification of VERIF-D1/D2/D3 (repair tip `4038e3e`)

- VERIF-D1 CLOSED. The dead `repairs` branch is deleted from
  `admitted_child_factory`; the factory is now stamp-only.
  Re-verification: `test_verif_d1_stamp_only_channel_after_repair`
  proves a model-supplied repairs map still reaches no submitted bytes
  (the branch is gone, not bypassed) AND the obligation stamp still
  lands on the targeted path. Obligation-stamp stands as the verified
  causal channel.
- VERIF-D2 CLOSED. `run_cell` threads explicit
  `executed_treatment`/`fallback_reason` (`L-acquired` on retained,
  `S-fallback` + reason on none/stop/unsupported, none otherwise).
  Re-verification: `test_verif_d2_run_cell_threads_provenance`
  proves the S-fallback treatment + `model-stop` reason on a model
  stop, the `none-selection` reason on package-less L, and no reason
  on a clean plan.
- VERIF-D3 CLOSED. `stage_record` carries both provenance keys on
  success and failure (defaulting treatment to the scheduled arm).
  Re-verification: `test_verif_d3_staged_success_keeps_fallback_provenance`
  (inverted from the defect-demonstrating shape) proves staged success
  keeps `S-fallback` + reason.
- M2 EC07 triage: NO reproduced regression. `test_coord02_m2_qualification.py`
  is 12/12 green on the repair tip (EC07 in isolation and in-suite);
  exec/state/learning/experiment/m3 (83), m4 (8/8), runtime/workload/
  ecr201_205/ecr202 (54 + 2 skipped) all green — the provenance
  threading breaks no existing battery. The failure the coordinator
  saw was the old stub against the hardened skip contract, already
  repaired by their own stub amendment in `4038e3e`. Residual note
  (not a defect): the amended EC07 stub skips via the `reconciled=None`
  legacy path with a fabricated op id that is never checked against
  durable rows — the explicitly accepted T-STATE legacy rule for
  fixture callers (contract note #2), not new breakage.
- EC02 panel-level resume stays a RECORDED LIMITATION, not a
  gate-blocker: re-confirmed zero `resume` references in
  `experiments/coord02/entry.py` — `run_panel`/`main` re-run
  unconditionally, no `--resume` subcommand, no `resume_plan`
  consumer. Interruption safety holds at the controller seam
  (re-drive repeats nothing; my 3 interrupt tests) and true
  cross-process resume at the AD01 CLI (SIGKILL test); nothing in the
  C2 runbook path I could find consumes `resume_plan` either
  (`main()` has no resume mode), so C2 re-runs remain full-panel
  re-runs. If C2 needs panel resume, the missing call path is
  `main`/`run_panel` → `SE.resume_plan` over saved evidence.

## Material defects (recorded, not fixed — all three now closed above)

- VERIF-D1 (material, CLOSED on `4038e3e`): model-supplied `repairs` maps never reach
  submitted bytes. `entry.admitted_child_factory`
  (`experiments/coord02/entry.py:326-346`) honors `child["repairs"]`,
  but `team._validate_children` (`src/settlement/team.py:95-140`)
  strips every child to five keys, so the interpreted A proposal's
  repairs are dropped at admission. Rejecting evidence:
  `test_verif_d1_model_repairs_map_dropped_at_admission` stages a
  proposal carrying run-unique repair bodies and proves they are absent
  from the restaged tree. The live causal channel is obligation text →
  deterministic stamp (verified), not repair bytes; the lane claim
  "repairs map honored when present" (t-exec.md) is unreachable on the
  public path. Coordinator decides: thread repairs through team
  validation or delete the dead branch.
- VERIF-D2 (minor-ledger, CLOSED on `4038e3e`): `run_cell` computed `fallback_note` but never
  threads `executed_treatment`/`fallback_reason` into
  `SE.build_trial_record` (`experiments/coord02/entry.py:567-578`
  passes neither kwarg), so trial records from the public entry default
  the treatment instead of recording the executed one. The T-EXEC lane
  already flagged this as a contract note awaiting the schema side;
  the schema side exists (`build_trial_record` accepts both kwargs),
  the entry-side write is still missing. Fallback attribution survives
  only as free-text failure markers.
- VERIF-D3 (minor-ledger, CLOSED on `4038e3e`): `entry.stage_record`
  (`experiments/coord02/entry.py:440-475`) drops
  `executed_treatment`/`fallback_reason` — a successfully staged record
  carries no fallback provenance even when its trial does. Rejecting
  evidence: `test_verif_d3_staged_success_drops_fallback_provenance`
  stages valid bytes for an S-fallback trial and proves both keys
  absent from the staged output. Resume does not consume those keys,
  so no resume corruption follows; the ECA-03 "persistent provenance
  independent of grading" closure is schema-side only.
- EC02 public entry has no resume consumer (observation, re-confirmed
  on the repair tip — recorded limitation, not gate-blocking):
  nothing in production calls `SE.resume_plan`;
  `run_panel`/`main` re-run schedules unconditionally and
  `controller.resume_episode` is a same-process alias for
  `run_episode`. Interruption safety was verified at the controller
  seam (re-drive repeats nothing) and true cross-process resume at the
  AD01 CLI; EC02 panel-level resume remains unwired.

## Per-challenge findings

1. Causal path — PASS with VERIF-D1 noted. Two different valid model
   decisions change accepted work (obligation → stamp → distinct
   restaged trees); changed obligation text changes the result;
   rewritten public descriptions leave direct S policy execution
   byte-identical; non-FIXTURE constructor labels raise before any
   dispatch. A fake factory cannot be selected in real mode.
2. State/authority — PASS. Interrupt after recorded probe / after child
   dispatch / after publication, then re-drive the same campaign:
   pre-crash operation identities persist, success-receipt counts per
   op are unchanged (no repeated settled effects), probe observations
   are not re-created, outcome reaches the same terminal state.
   Lineage-guard race admits exactly one valid call (refused twin
   leaves only an invalid marker, no second lineage). A stranded send
   (gateway lost after dispatch) makes the next construction call
   raise naming the stranded op, with call count unchanged. The
   sentinel DB (`ec02test_verif_sentinel`, designated evidence with a
   marker table) refuses evidence→disposable relabel and disposable
   preparation before any mutation; marker rows byte-identical after
   both refusals.
3. Learning/measurement — PASS with VERIF-D3 noted. Valid-but-failing
   policy reports `valid_execution=True` with `solved_count=0` while
   unparsable bytes report `valid_execution=False`; acquired bytes
   trace to a labeled ledger operation while authored bytes trace to
   none; S-fallback trials keep treatment+reason through validate
   round-trips and unstaged grading; the failed/cancelled/shared union
   recomputes exactly with unknown-stays-unknown; selection ignores
   injected future-outcome fields and fallback-alone never selects.
4. Fresh checkout — PASS. All deterministic-path drivers tracked;
   no `.py` source under `experiments/`, `src/settlement/`, or
   `tests/` references worktree or `/tmp` scratch paths (only
   historical `/tmp/ec02-live/` notes in a markdown evidence file);
   a real `git clone` of the tip imports both public entries and
   collects the battery (import + collection only on 2 CPUs, per
   capacity rule — no full panels in the clone).
5. AD01 trajectory resume — PASS (own countercheck, not the lane's
   shape). Genuine SIGKILL mid-`cli run` (6-task mixed-family
   campaign), then `cli resume` in a fresh process: same campaign id,
   settled boundaries reused (`resumed: True`), spend replays recorded
   spend exactly, claimed op identities distinct and non-empty;
   a direct run's spend equals the sum of its boundary spends.

## Original-probe deltas (merged tip vs `fe41fb6` observations)

Re-ran `reviews/probes/ec02_completion_review.py` unmodified on the
merged tip. Flipped fail→pass: `gateway_factory` now
`HttpGatewayAdapter`; `real_record_resume` now skips the unmodified
saved record; `fabricated_digest_record_resume` now runs the invented
digest-only record. Unchanged: fixed model-usage constants
(`_cell_costs` still 100/20/1 — entry-side measurement remains
T-EXEC-owned per the T-STATE change request); `staged_fallback`
shape (`arm=L, outcome=success, failures=[]` — now minor-ledger D3
rather than P1, since trial-side provenance exists);
`unstaged_marker_preserved=true`. The three
`different_A_responses_*`/`repair_equals_unmodified_snapshot=true`
outputs are stale probe shapes, not regressions: the probe feeds
`stop`/`unsupported`, which the merged tip correctly routes to the
S-fallback path with identical bytes — a model stop actually stopping
is the claimed behavior, proven divergent from `plan` by the lane and
re-proven here with plan-vs-plan obligations.

## Rebutted / out-of-scope

- ECA-02 entry-side constants: confirmed still present, already owned
  by T-EXEC per the T-STATE change request; not re-filed.
- No live-gateway, billing, or PG18 claims are made or needed here.
- M4 144-cell study and live acquisition disposition are the
  coordinator's C2 business; this lane makes no verdict on them.

## Commands (all from the worktree root)

- `PYTHONPATH=<worktree> python /tmp/ec02-pytest-progress.py
  /home/ubuntu/AI/Agent-Society-v2/.venv/bin/pytest
  tests/test_ec02ad_verif.py -q` → 27 passed (~60s)
- `PYTHONPATH=<worktree> <venv>/bin/python
  reviews/probes/ec02_completion_review.py` → deltas above
- Fresh-checkout path is exercised in-test (clone + import +
  collection); manual equivalent is `git clone <root> /tmp/fresh &&
  cd /tmp/fresh`.

Everything is completed.
