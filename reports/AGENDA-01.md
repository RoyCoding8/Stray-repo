> Historical batch report for the Agenda 01 cognitive batch. Its commits do
> not resolve in the current repository. Current scoped status is reconciled in
> [PROJECT-LEDGER.md](PROJECT-LEDGER.md) and
> [STAGE-09-10-COMPLETION-MATRIX.md](STAGE-09-10-COMPLETION-MATRIX.md). Read it
> for the panel and freeze records it kept byte-frozen.

# Agenda 01 — implementation and corrected experiment report

Branch `codex/implementation-cognitive-batch-01`. Current corrected
experiment `AG01-EXP/3`, policies R `AG01-R-1` / Q `AG01-Q-2`, frozen at
manifest v3 `c6ad5d91…` (traces run on the freeze files, strict checker
green 128/128). The v2 experiment (`AG01-EXP/2`) is preserved byte-frozen
in `experiments/agenda01/results_v2/` with its report section below; the
v1 experiment (`AG01-EXP/1`) likewise in `experiments/agenda01/results/`
plus the appendix.

## Corrected panel v3 (AGR2-01/02/03 closed)

Three-gate prompt plus correction assessment `55df063`, all verified
against live PostgreSQL (`reports/DECISIONS.md` AG01-D16..D20):

- Genuine resume (AGR2-01): tick records persist before the progress
  save; resume continues the same database (fresh DBs refused) and
  re-dispatches prepared-but-receiptless operations through the broker.
  Sentinel survival, same-DB identity and exact control-trace equality
  proven (`test_resume_continues_saved_progress`); prepared-op recovery
  proven (`test_prepared_operation_resumed_without_receipt`).
- Decision/time contract (AGR2-02): every new decision charges exactly
  once (charge before the effect-identity check; duplicate data carries
  `dec_op`), replay stays free; paid epoch starts at 0 and due dates
  equal pre-decision epoch plus delay, matching the frozen
  event-ordering rule. Proven on w08–w11 and by the delayed-receipt
  diagnostic (`test_duplicate_effect_decisions_charged`,
  `test_receipt_timing_matches_declared_clock`). Migration
  `0013_agenda01_epoch.sql`. The demo journey counts 4 paid decisions.
- Frozen execution (AGR2-03): scored entry points load a specified
  committed manifest and verify its canonical digest (revision is
  provenance only) plus frozen file/source bytes; traces bind source
  maps; the strict checker rejects incomplete traces, missing/duplicate
  charges, duplicate trajectories and source drift. Mutation coverage
  proven (`test_checker_rejects_gate_mutations`,
  `test_freeze_identity_ignores_revision`).

v3 panel (`experiments/agenda01/results_v3/`, 128 files + `panel.json`,
report `reports/AGENDA-01-checker-v3.json`): 128/128 complete, grades
tie 288–288 in all 64 pairs. Family totals (correct R, correct Q):
f0 (46, 46), f1 (44, 44), f2 (36, 36), f3 (24, 24), f4 (34, 34),
f5 (30, 30), f6 (32, 32), f7 (42, 42). Exploration R 2292, Q 2276
(the 16-unit gap is all family 1: Q declines the
identical-consequence a2 followup R admits, scores tied). 8 of 3072
per-tick decisions differ (the family-1 skips, both ties). Pending
liabilities: 4 trajectories (w11, both arms and ties) each carry one
attributed exposure. Verdict under the stated merit rule: no accuracy
gain, tie clause met on resources — Q merits a broader trial on cost
grounds (authored simulation, not a learning claim). v2 verdict stands
under its frozen report; under v3 rules the preserved v2 traces show
16 `missing-decision-charge` traces (w08–w11) — the fixed defect,
exposed, not backfilled.

Panel: `PYTHONPATH=src .venv/bin/python -m experiments.agenda01.panel
run --base-dsn <dsn> --out-dir experiments/agenda01/results_v3
--manifest experiments/agenda01/manifest_v3.json --manifest-hash-file
experiments/agenda01/manifest_v3.sha256 --workers 4` then `... panel
check --trace-dir ... --report reports/AGENDA-01-checker-v3.json
--manifest .../manifest_v3.json --manifest-hash-file
.../manifest_v3.sha256`.

## What changed since v1 (assessment correction)

An independent assessment confirmed six findings (AGR1-01..06), all verified
against live PostgreSQL behavior and all corrected on this branch; the
corrected experiment does not favor Q on accuracy. Per-finding record:
`reports/DECISIONS.md` AG01-D11..D15.

- Real-attempt substrate (AGR1-01/02): admissions create durable attempts and
  prepared zero-exposure probe operations; a labeled deterministic sim
  launcher dispatches them and its receipts land in the runtime receipt
  store; `record_outcome` resolves by receipt identity only (unknown,
  wrong-operation, conflicting, and stale-support receipts refused).
  Proposals require a pre-existing grant root (no self-authorized roots).
- One qualification definition (AGR1-03): `qualify_continuation` lives in
  `agenda_policy`; the admission fence applies it to Q-armed continuations
  only, mechanical checks to both. Q1 is checkable in the declared language
  (residual-matching decisive in-scope citation plus differing declared
  true/false consequences; before/after strings display-only). Policy Q is
  `AG01-Q-2`; R stays `AG01-R-1`.
- Diagnostics before scoring (AGR1-04): `dev02` (useful followup) and
  `dev03` (wasteful followup) prove the treatment end to end; premature
  stopping cost demonstrated; world distribution reviewed below.
- Checker v2 (AGR1-05): exact panel membership (strict default, explicit
  `--subset` diagnostics), traj/arm/policy-version identity, v2 cost
  equations (settled-union equals consumed; every unsettled reservation
  attributed by a pending liability with operation and reason), all cost
  classes, effect/receipt linkage, conflict rejection, horizon cut on
  outcome epochs. Tamper coverage: alteration, deletion, complete-pair
  deletion, manifest drift, policy rebrand, unattributed exposure.
- Replay and resume (AGR1-06): committed `replay.py` (run/verify) and
  `panel.py` (run/check) CLIs; no driver or evidence lives only under /tmp.
  Fresh-process resume of an interrupted trajectory with pending effects
  reproduces the uninterrupted control trace exactly
  (`test_resume_matches_uninterrupted_control` — superseded: the v2 test
  omitted `--resume`; genuine resume proven in v3 above).

Schema/API mapping: `migrations/0011_agenda01_correction.sql` (receipts
linkage, scored outcomes, trajectory resume state),
`0012_agenda01_resume.sql` (tick log, idle/waiting/liability persistence);
`src/settlement/agenda.py` (grant-first propose, attempt-binding admit,
receipt-identity record, receipts-based continuation);
`experiments/agenda01/launcher.py` (labeled sim launcher),
`replay.py`, `panel.py`, `checker.py`, `manifest.py` (`AG01-EXP/2`).

## Frozen manifest and replay

- `experiments/agenda01/manifest_v2.json` + `manifest_v2.sha256`:
  `99e9d5f6…` (32 worlds, budgets ticks=24/exploration=64/eval=8/
  recovery=16/decision=1, both tie orders, policy versions R-1/Q-2, file
  digests of apparatus plus treatment sources
  `src/settlement/{agenda,agenda_policy,broker,store}.py`).
- Traces: `experiments/agenda01/results_v2/` (128 files + `panel.json`,
  strict checker report at `reports/AGENDA-01-checker-v2.json`). Every trace
  carries `manifest_sha256`; the panel runner refuses manifest drift at
  execution; acceptance checks against the frozen files, never a rebuild.
- Panel: `PYTHONPATH=src .venv/bin/python -m experiments.agenda01.panel run
  --base-dsn <dsn> --out-dir experiments/agenda01/results_v2 --workers 4`
  then `... panel check --trace-dir ... --report ... --manifest
  experiments/agenda01/manifest_v2.json --manifest-hash-file
  experiments/agenda01/manifest_v2.sha256`.
  Demo: `scripts/agenda01.py` (grant → propose → admit → dispatch → record →
  continue journey on scratch DBs, forged receipts refused).
- Freeze history: first freeze `d5e2d79` ran 124/128 — all four w10
  trajectories died recording a receipt dated drive-tick 6 against cursor
  epoch 4. Duplicate-effect idles charge no decision, so the drive clock had
  outrun durable time and the runner minted future-dated receipts the fence
  correctly refused. Refreeze `3b137cf` anchors due dates and ingest gating
  to the durable cursor epoch; second refreeze `c8b9acc` makes the checker
  partition non-trace JSON explicitly. The superseded partial panel was
  never committed. No selective repairs: the rerun is complete from scratch.

## Pair results (64 pairs, grade tied in all)

One row per world at tie t0. Tie t1 is identical in grade and totals
except: w11 (same exposure, traj-embedded operation identity differs) and
w12–w14 (rotation order changes spend 36/idle-19 vs 34/idle-20, grade 3/3
either way, both arms). R−Q grade column is 0 in all 64 pairs.

| world | fam | R | Q | R-Q | exploreR | exploreQ | eval | rec | idleR | idleQ | liab |
|---|---|---|---|---|---|---|---|---|---|---|---|
| w00 | 0 | 6 | 6 | 0 | 38 | 38 | 8 | 0/0 | 20 | 20 | 0 |
| w01 | 0 | 6 | 6 | 0 | 38 | 38 | 8 | 0/0 | 20 | 20 | 0 |
| w02 | 0 | 6 | 6 | 0 | 38 | 38 | 8 | 0/0 | 20 | 20 | 0 |
| w03 | 0 | 5 | 5 | 0 | 38 | 38 | 8 | 0/0 | 20 | 20 | 0 |
| w04 | 1 | 5 | 5 | 0 | 38 | 36 | 8 | 0/0 | 18 | 19 | 0 |
| w05 | 1 | 5 | 5 | 0 | 38 | 36 | 8 | 0/0 | 18 | 19 | 0 |
| w06 | 1 | 5 | 5 | 0 | 38 | 36 | 8 | 0/0 | 18 | 19 | 0 |
| w07 | 1 | 7 | 7 | 0 | 40 | 38 | 8 | 0/0 | 17 | 18 | 0 |
| w08 | 2 | 5 | 5 | 0 | 17 | 17 | 8 | 0/0 | 20 | 20 | 0 |
| w09 | 2 | 5 | 5 | 0 | 26 | 26 | 8 | 0/0 | 19 | 19 | 0 |
| w10 | 2 | 3 | 3 | 0 | 12 | 12 | 8 | 0/0 | 20 | 20 | 0 |
| w11 | 2 | 3 | 3 | 0 | 10 | 10 | 8 | 0/0 | 20 | 20 | 2 |
| w12 | 3 | 3 | 3 | 0 | 36 | 36 | 8 | 0/0 | 19 | 19 | 0 |
| w13 | 3 | 3 | 3 | 0 | 36 | 36 | 8 | 0/0 | 19 | 19 | 0 |
| w14 | 3 | 3 | 3 | 0 | 36 | 36 | 8 | 0/0 | 19 | 19 | 0 |
| w15 | 3 | 3 | 3 | 0 | 36 | 36 | 8 | 0/0 | 19 | 19 | 0 |
| w16 | 4 | 4 | 4 | 0 | 32 | 32 | 8 | 0/0 | 20 | 20 | 0 |
| w17 | 4 | 4 | 4 | 0 | 32 | 32 | 8 | 0/0 | 20 | 20 | 0 |
| w18 | 4 | 4 | 4 | 0 | 40 | 40 | 8 | 0/0 | 16 | 16 | 0 |
| w19 | 4 | 5 | 5 | 0 | 44 | 44 | 8 | 0/0 | 15 | 15 | 0 |
| w20 | 5 | 4 | 4 | 0 | 34 | 34 | 8 | 0/0 | 20 | 20 | 0 |
| w21 | 5 | 4 | 4 | 0 | 34 | 34 | 8 | 0/0 | 20 | 20 | 0 |
| w22 | 5 | 4 | 4 | 0 | 32 | 32 | 8 | 0/0 | 20 | 20 | 0 |
| w23 | 5 | 3 | 3 | 0 | 34 | 34 | 8 | 0/0 | 20 | 20 | 0 |
| w24 | 6 | 4 | 4 | 0 | 34 | 34 | 8 | 0/0 | 20 | 20 | 0 |
| w25 | 6 | 4 | 4 | 0 | 34 | 34 | 8 | 0/0 | 20 | 20 | 0 |
| w26 | 6 | 4 | 4 | 0 | 34 | 34 | 8 | 0/0 | 20 | 20 | 0 |
| w27 | 6 | 4 | 4 | 0 | 34 | 34 | 8 | 0/0 | 20 | 20 | 0 |
| w28 | 7 | 8 | 8 | 0 | 40 | 40 | 8 | 0/0 | 16 | 16 | 0 |
| w29 | 7 | 8 | 8 | 0 | 40 | 40 | 8 | 0/0 | 16 | 16 | 0 |
| w30 | 7 | 2 | 2 | 0 | 28 | 28 | 8 | 0/0 | 22 | 22 | 0 |
| w31 | 7 | 3 | 3 | 0 | 34 | 34 | 8 | 0/0 | 20 | 20 | 0 |

Family totals (correct R, correct Q): f0 (46, 46), f1 (44, 44), f2 (32, 32),
f3 (24, 24), f4 (34, 34), f5 (30, 30), f6 (32, 32), f7 (42, 42).
Exploration totals: R 2144, Q 2128 (the 16-unit gap is all family 1: Q
declines the identical-consequence a2 followup R admits, scores tied).
Recovery spend: 0 in all 128 trajectories. 8 of 3072 per-tick decisions
differ between arms (the family-1 skips, both ties). Pending liabilities: 4
trajectories (w11, both arms and ties) each carry one attributed exposure
(`unresolved unknown receipt retains exposure`, the dud acquisition probe);
checker-verified against the unsettled reservations. Failures: none in the
frozen run (128/128 complete).

## Diagnostics (separate development controls)

- dev02 (useful followup, discriminating consequences): R and Q both admit
  the m1 continuation usefully and score 2/2, explore 10 each.
- dev03 (wasteful followup, identical consequences): R admits m1, Q records
  `unqualified-continuation` in its own evaluated audit and never links m1;
  both score 1/1; explore R 10 vs Q 8 — the fence split end to end on
  identical inputs, with the waste priced at exactly one probe (2 units).
- Premature stopping: dev02 truncated at 1 tick never launches m1 and
  forfeits the p1 task (full run scores 2/2 with p1 sourced from the
  continuation attempt).
- Genuine competition: both arms run every diagnostic to completion; neither
  diagnostic is single-arm.

## World distribution review (eight scenario families)

f0 repeated-expensive-success: caps force choice among costly probes; both
arms score 5–6, spend equal. f1 appealing-uninformative: the treatment's
designed showcase — R takes the appealing but identical-consequence
followup, Q declines; accuracy tied, Q saves 16. f2 missing-instrument:
delayed/absent instruments starve probing (spend 10–34); w10 exercises the
durable-epoch fence through a replication re-sample. f3 duplicate-branched:
rotation order moves spend ±2 with grade fixed — the only tie-sensitive
family. f4 counterexample-negative-history and f5 replication-noisy: history
and noise regimes both arms handle identically here. f6 unresolved-wakeup:
delayed readouts complete through resume-equivalent paths. f7
sparse-stopping: controls w28/w29 at 8/8 plus the sparse worlds; the Q-losing
world w23 ties 3/3 again, so the apparatus can report a Q loss but no
authored world produces one. Coverage gap, stated plainly: no family makes
an unqualified continuation the *only* route to a scored task, so the panel
cannot show Q losing accuracy to its own fence — only dev03-style waste
avoidance. That is a property of this distribution, not of the mechanism.

## Controls and gates

- Positive controls w28/w29: 8/8 on both arms in the frozen run.
- Wrong-answer control: 0/8 on every world (`test_wrong_answer_control_fails_grading`).
- Q-losing world w23: R=3, Q=3 — tied, so this control did not demonstrate
  a Q loss; the apparatus can report one but this world does not produce one
  under either policy.
- Mechanical gates: strict checker `ok=True` over 128 traces, 64 pairs, 0
  violations; manifest hash matches in every trace; determinism pinned by
  `test_agreement_durable_deterministic`; resume equivalence pinned by
  `test_resume_matches_uninterrupted_control` (pending effects present at
  interrupt, full-trace equality after fresh-process resume).
- Verdict under the protocol merit rule: no aggregate primary (accuracy)
  improvement — all 64 pairs tie 284–284 — but the tie clause is met: Q
  spends strictly fewer total resources (2128 vs 2144 exploration, all else
  equal). Q merits a broader trial on resource grounds. This is a
  descriptive reading of authored simulation, not a general learning claim.

## Evidence map

Real PostgreSQL 16 / real processes: grant-first proposals, attempt-binding
admissions, receipt-identity outcomes with conflict/staleness refusal,
dispatch gating (no launcher, rotated grant), receipts-based continuation
with Q-route fence, typed wake matching, budget reservation/consumption
with attributed pending liabilities, cross-arm replay refusal,
duplicate/out-of-order wake single-effect, stale-admit refusal, fresh-process
crash/resume equivalence, and the independent ledger checker — all in
`tests/test_ag01_state.py`, `test_ag01_policy.py`,
`test_ag01_experiment.py` on scratch databases.
Simulated (authored, not learned): observation values (latent bit + noise),
product claims, grader answers, world fixtures, launcher draw outcomes. The
policies never observe latent state:
`test_no_privileged_fields_in_public_fixtures` plus the
observations/grader import-mark guard enforce the boundary; drained
(unscored) observations never reach the fence or the grade; tick entries
carry the compact policy `evaluated` audit.

## What this supports

- Retain Q's qualification fence as a cost control: on this distribution it
  binds exactly where designed (family 1, dev03), never costs accuracy, and
  saves 16 exploration units across the panel.
- Study next: a family where the only route to a scored task is an
  unqualified continuation (the stated coverage gap), and noisier regimes
  where R/Q could separate on accuracy. Do not invent representations,
  teams, or learner revisions on the back of these mechanics passing.
- Limits: 32 authored worlds, one noise/delay regime per world, one budget
  point; the tie is a property of this distribution, and accuracy separation
  is proven only at unit level plus the dev03 behavioral split.

## Verification

Full suite on the final tree (real PostgreSQL 16):
`SETTLEMENT_TEST_DSN="postgresql://ubuntu@/agenda01_exp?host=/var/run/postgresql" .venv/bin/python -m pytest tests/ -q`
— 668 passed, 1 failed; the single failure was the checkpoint test's
hardcoded migration list missing `0011`/`0012` (stale expectation, product
correct). After extending the list, `tests/test_rec_checkpoint.py` passes
4/4 standalone. Panel acceptance is independent of the suite: `panel check`
strict over `results_v2/` with the frozen v2 manifest (128 traces, 64
pairs, 0 violations).
## Appendix: superseded v1 (preserved, byte-frozen)

v1 experiment `AG01-EXP/1`, policies R `AG01-R-1` / Q `AG01-Q-1`, freeze
`fdc354a` (traces run on refreeze `a52f3ed7`), manifest
`experiments/agenda01/manifest.json` (`a52f3ed7…f13fa`), traces
`experiments/agenda01/results/` (128 files). v1 verdict (unchanged record):
all 64 pairs tied with equal resources, so Q did NOT merit a broader trial
under the tie clause. The v1 flaw set (admissions without attempts,
self-asserted observations settling probes, continuation citing loose
strings, Q1 in prose, unchecked panel membership, /tmp-only replay driver)
is the correction's scope above; v1 stays frozen as inactive-treatment
evidence and must not be re-scored.

v1 pair table (t0 rows; t1 rows were copies):

| world | fam | R | Q | R-Q | explore | eval | recovery | idle |
|---|---|---|---|---|---|---|---|---|
| w00 | 0 | 6 | 6 | 0 | 38 | 8 | 0 | 20 |
| w01 | 0 | 6 | 6 | 0 | 38 | 8 | 0 | 20 |
| w02 | 0 | 6 | 6 | 0 | 38 | 8 | 0 | 20 |
| w03 | 0 | 5 | 5 | 0 | 38 | 8 | 0 | 20 |
| w04 | 1 | 5 | 5 | 0 | 38 | 8 | 0 | 18 |
| w05 | 1 | 5 | 5 | 0 | 38 | 8 | 0 | 18 |
| w06 | 1 | 5 | 5 | 0 | 38 | 8 | 0 | 18 |
| w07 | 1 | 7 | 7 | 0 | 40 | 8 | 0 | 17 |
| w08 | 2 | 5 | 5 | 0 | 34 | 8 | 0 | 20 |
| w09 | 2 | 5 | 5 | 0 | 34 | 8 | 0 | 20 |
| w10 | 2 | 5 | 5 | 0 | 34 | 8 | 0 | 20 |
| w11 | 2 | 3 | 3 | 0 | 38 | 8 | 0 | 20 |
| w12 | 3 | 3 | 3 | 0 | 34 | 8 | 0 | 20 |
| w13 | 3 | 3 | 3 | 0 | 34 | 8 | 0 | 20 |
| w14 | 3 | 3 | 3 | 0 | 34 | 8 | 0 | 20 |
| w15 | 3 | 3 | 3 | 0 | 36 | 8 | 0 | 19 |
| w16 | 4 | 4 | 4 | 0 | 32 | 8 | 0 | 20 |
| w17 | 4 | 4 | 4 | 0 | 32 | 8 | 0 | 20 |
| w18 | 4 | 4 | 4 | 0 | 40 | 8 | 0 | 16 |
| w19 | 4 | 5 | 5 | 0 | 44 | 8 | 0 | 15 |
| w20 | 5 | 4 | 4 | 0 | 34 | 8 | 0 | 20 |
| w21 | 5 | 4 | 4 | 0 | 34 | 8 | 0 | 20 |
| w22 | 5 | 4 | 4 | 0 | 32 | 8 | 0 | 20 |
| w23 | 5 | 3 | 3 | 0 | 34 | 8 | 0 | 20 |
| w24 | 6 | 4 | 4 | 0 | 34 | 8 | 0 | 20 |
| w25 | 6 | 4 | 4 | 0 | 34 | 8 | 0 | 20 |
| w26 | 6 | 4 | 4 | 0 | 34 | 8 | 0 | 20 |
| w27 | 6 | 4 | 4 | 0 | 34 | 8 | 0 | 20 |
| w28 | 7 | 8 | 8 | 0 | 40 | 8 | 0 | 16 |
| w29 | 7 | 8 | 8 | 0 | 40 | 8 | 0 | 16 |
| w30 | 7 | 2 | 2 | 0 | 28 | 8 | 0 | 22 |
| w31 | 7 | 3 | 3 | 0 | 32 | 8 | 0 | 21 |

Family totals (correct R, correct Q): f0 (46, 46), f1 (44, 44), f2 (36, 36),
f3 (24, 24), f4 (34, 34), f5 (30, 30), f6 (32, 32), f7 (42, 42).
Liabilities pending at horizon: none in any trajectory. Failures: none in
the frozen run (128/128 complete). 0 of 1536 per-tick decisions differ
between arms.
