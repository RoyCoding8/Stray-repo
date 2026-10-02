# Agenda 01 correction assessment

Reviewed `051811fd59ab6d1de0f85a1be8849e94b638ebf5` against the preceding review at `3078018`. Scope: the corrected contracts and v2 evidence. No new broad audit, live model run or architecture redesign.

## What is established, and what remains open

Substantial progress is visible. The preserved v2 panel has **614 actual runtime operation rows**, compared with zero in v1. Admissions use extracted transaction-local attempt/preparation helpers, the broker routes a labeled simulation adapter, outcomes resolve runtime receipt identities, proposal creation requires an existing root, and the extra qualifier is applied to Q rather than both arms. The earlier unrelated-citation shortcut is tightened in the limited observation language. These changes are useful and should be retained; inspection is not a universal proof of every authority/evidence failure mode.

Independent arithmetic over the 128 stored traces confirms **284 correct tasks per arm**, R exploration expenditure **2,144**, Q **2,128**. The 16-unit difference is the reported uninformative-followup family. This is a narrow observable simulated cost saving with tied grades. It is not yet an accepted complete experimental result, because the three gates below remain open. Neither a positive result nor another larger panel is needed to address them.

Checks performed locally:

- `python -m pytest tests/test_ag01_policy.py -q -p no:cacheprovider`: **28 passed**.
- [Correction assessment probe](probes/agenda01_correction_assessment.py): original strict checker reports 128 traces / 64 pairs / no violations; independent cost/grade reconstruction, checker mutations, actual CLI parsing and actual driver execution with an explicit in-memory backend double expose the failures below.
- Results preserved in [AGENDA-01-correction-assessment.json](AGENDA-01-correction-assessment.json). The driver double records calls from the real `_drive` function; it does not simulate PostgreSQL transaction behavior.
- No local PostgreSQL trajectory replay or full-suite run. The worker's current report records **668 passed, 1 failed**, followed by **4 checkpoint tests passing** after the stale migration expectation was corrected. That does not establish a green final-source full suite, but the isolated test-only correction need not itself start another review cycle.

## AGR2-01 — P1: the claimed resume test starts fresh; actual saved progress is inconsistent

Continues AGR1-06 / AG01-09. `tests/test_ag01_experiment.py:422–428` launches `replay run` without `--resume`. The real parser defaults that flag to false (`replay.py:80`). Consequently `run_trajectory` takes its fresh branch, drops the trajectory database and recreates it (`runner.py:1017–1023`). Comparing that output to another fresh run proves determinism, not continuation from pending effects.

There is also a directly reproduced progress-order defect: `_drive` calls `save_state(..., tick + 1, _progress(st))` before appending the current tick to `st['ticks']` (`runner.py:940–947`). A one-tick run of the actual driver against the explicit backend double saves next tick 1, idle count 1, but zero tick records. `_rebuild_state` resumes from the stored tick/log, so merely adding the flag does not establish a correct trace. It also skips prepared links without receipts (`runner.py:757–760`), leaving the pre-dispatch interruption boundary unproven.

Required acceptance: fix the driver/progress boundary, invoke actual resume, and show that a unique sentinel from the partial database survives. Kill and resume around a committed paid decision, prepared operation without a receipt, and pending observation. Verify no database recreation, no missing/duplicated decisions, identical subsequent logical effects and accounting, and preserved pending exposure. Retain the fresh-run determinism test under an accurate name if useful.

## AGR2-02 — P1: distinct decisions become free and simulation time diverges

Continues the AG01-10/11 cost contract. In all 16 traces for w08–w11, there are 24 tick decisions but only 7, 14, 4 and 4 decision charges respectively. Total missing charges across those traces: **268 units**. For example, `w10v2_r_t0` has 24 recorded decisions, 20 with no `dec_op`, and four paid decisions. The current checker accepts this.

The runner calls the policy on each new tick, then handles `ALREADY_APPLIED` as an idle without charging that new decision (`runner.py:876–878`, `921–923`). Deduplicating an effect is correct; making a new planning decision free is not. Transport replay of the *same committed decision* must remain free. These cases need distinct durable identities.

Due dates are now anchored to the paid cursor while exogenous events still advance on drive ticks (`818–827`, `860`, `893`). With free duplicate decisions those clocks drift, altering receipt availability and horizon behavior. Relabeling receipt epochs to satisfy the fence does not resolve that underlying disagreement.

Required acceptance: establish one explicit logical decision/time contract. Every distinct decision, including a duplicate-effect idle, costs its declared unit exactly once. Replay does not advance time or charge again. Event schedules, observation availability and the horizon cut use the declared clock without backdating knowledge. Verify w08–w11 and a delayed-receipt diagnostic before refreezing. Do not patch the saved totals by adding 268: execution timing itself can change.

## AGR2-03 — P1: frozen execution and strict validation remain incomplete

Continues AGR1-05. The checker has improved membership, policy and cost checks, but executable mutations still pass:

- Change `complete` to false: no violation.
- Remove every tick's `dec_op`: no violation.
- Add an exact duplicate trace: strict mode reports **129 traces, ok=true**.
- Change manifest content while keeping the supplied digest: strict mode accepts it.

`check_dir` uses a set for membership and overwrites repeated arm entries instead of rejecting duplicates (`checker.py:190–200`). Presence of the `complete` field is checked, its value is not. Ledger consistency is not sufficient to establish that every decision had its required charge. The above probes use the new signatures and `expect_full=True`.

The executable freeze is still unenforced. `panel.cmd_run` calls `manifest.build()` (`panel.py:44`), accepts no required committed manifest, and uses the rebuilt worlds/digest. `panel.cmd_check` trusts supplied manifest/hash bytes without recomputing their correspondence (`80–87`). `replay.cmd_run` compares the caller's hash to a fresh `build()`; because `build()` includes current HEAD, documentation-only reporting commits can prevent replay of an unchanged frozen apparatus. A hash label is not a verified execution input.

Required acceptance: the scored runner loads a specified committed manifest and verifies its digest, frozen worlds/configuration and source identities before any work. Define portable byte identity explicitly and verify the pinned source files, so an unrelated reporting commit neither changes the experiment nor silently authorizes code drift. The checker must reject incomplete, missing and duplicate trajectories, changed manifest/source, missing decision charges and invalid horizon evidence. Keep subset/development mode explicit. Prove the mutations fail with useful reasons before running the panel.

## Disposition and next step

Accept the substrate and treatment changes as useful prototype progress. Keep Agenda 01 **partially accepted**, with the v2 costs and grades preserved as descriptive evidence. The remaining three gaps materially affect its claimed durability and fixed-budget experiment, so they are not optional production polishing.

Use the [three-gate completion prompt](../WORKER-AGENDA-01-THREE-GATES.md). First reproduce and repair these short gates; then preserve v1/v2, freeze once, and rerun the complete corrected panel. Interpret whatever result occurs. Do not re-audit the entire repository, invent new cognitive subsystems, require Q to win or expand the study to obtain a preferred answer.

This limits the worker's correction assignment. It does not block independent design of representation invention/transfer from the existing stage 8.5 draft. The design role should advance that architectural work while the worker owns the remaining agenda acceptance gates.
