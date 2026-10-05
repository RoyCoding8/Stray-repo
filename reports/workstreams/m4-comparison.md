# M4's comparison: reachable offline as a mechanism, and not reachable as a benefit

Owner: m4-comparison lane. Base `9c73b149`. No push.
Scope: `tools/m4_mechanism_harness.py`, `tests/test_m4_mechanism_offline.py`,
this report, `reports/evidence/invl02-m4-mechanism/mechanism.json`.
No edit to `learner_revision.py`, `improve_channel.py`, `channel_controls.py`,
`PROJECT-LEDGER.md`, `scripts/invl02_live.py` or `.github/**`.

## The answer

**M4's comparison is reachable without a live model call as far as the
mechanism goes, and is not reachable as a benefit claim at all, for a reason
that has nothing to do with the model.** The acquisition decision is
executable, an eligible revision changes it, the change survives a restart in
a fresh process, the other three controls behave as they declare, and the
program cannot write the six frozen fields. All of that is measured offline,
here, on this host, with no database and no route.

What is not reachable is a parent-versus-revised panel with a non-zero
result, because **no reachable input beats the incumbent by more than the
cohort's own noise.** The best of sixteen is `+0.006667` at `z = 1.49` on 150
audit seeds, against a two-sided 5% bar of 1.96, and the argmax disagrees with
itself across quarters: `9, 12, 4, 4`. So the harness builds no panel and says
which measurement stopped it.

That is a stronger negative than "no eligible revision was acquired", and it
is a different one. It says the acquisition machinery works and the substrate
has nowhere for a win to land.

## What I ran, what I read, what I inferred

**Ran.** Every number below was produced by `tools/m4_mechanism_harness.py`
at base `9c73b149` on this Windows host, and is in
`reports/evidence/invl02-m4-mechanism/mechanism.json` (12,898 bytes). The 23
tests in `tests/test_m4_mechanism_offline.py` were executed by importing the
module and calling each function, because `tests/conftest_isolation.py:751`
acquires a run claim before collection and no local pytest starts on this host
without PostgreSQL. That is the same boundary `m4-eligibility.md:23-28`
recorded. **CI must confirm under the `postgres:18` service container.**

**Read.** `learner_revision.py`, `improve_channel.py`, `channel_controls.py`,
`WORKER-PROMPT.md:119-134`, `reports/workstreams/m4-eligibility.md` in full,
the ledger's `## The CI hang is fixed` section, and the existing
`tests/test_m4_eligibility.py`.

**Inferred, and labelled.** That a fresh model on a free route would now
produce a non-zero `x`. Not measured. No model call was made.

## The base was wrong on arrival, and the brief was wrong about it

The worktree I was given sat at `0ee4699d`, which is **161 commits behind**
`codex/agent-society`, and `9c73b149` was **not** an ancestor of it. The
brief said "`git log --oneline -1` must be at or past `9c73b149`", and it was
not. `RUN_VERSION` on that tree was `invl02-e4-run-v1`, the pre-repair prompt.
Had I built against it, every test would have been green against the prompt
that produced E4's six refusals.

Counted in the command that produced the set:
`git rev-list HEAD..codex/agent-society --count` = 161,
`git rev-list codex/agent-society..HEAD --count` = 0.
Reset to local `codex/agent-society` at `9c73b149`. Nothing was pushed and
`github` was never a reset source.

The two documents the brief named as required reading are at
`reports/workstreams/inv-learning02-m4.md` and
`reports/workstreams/inv-learning02-r123.md`, not the paths given. The m4 one
is a different, earlier workstream about offline recomputation, and its scope
excludes everything here.

## The offline and live boundary, established by execution

I did not read this off the docstrings. I ran each function at `9c73b149`
with no database and recorded what happened.

| Capability | Offline? | Evidence |
|---|---|---|
| module import | yes | imports clean with `PYTHONPATH=src` |
| `_revision_source` construction | yes | 1,105-byte source, `x` expression present |
| gates 1-5 of eligibility | yes | all five return pass |
| gate 6 `delegates-to-unchanged-reducer` | **no** | `OperationalError` from `_execution_ledger` |
| `classify_revision` | **no** | same |
| `drive_improve_round` | **no** | `OperationalError`, round refuses before probing |
| revision `STEP` executed directly | **yes** | returns `x = 12` |
| store persisted and reopened in a new process | **yes** | second interpreter reads `x = 12` |
| descendant scoring, paired comparison | **yes** | `audit` split, 150 seeds, milliseconds |

The database is required by exactly one mechanism: `_execution_ledger` opens
a disposable PostgreSQL for **every** execution of policy source, so that
receipts settle somewhere attributable. That is why gate 6 and
`drive_improve_round` are unavailable here and why `m4-eligibility.md:310-315`
left gate 6 read rather than executed. Five of six gates run. The sixth is
named in the artifact as unexecuted rather than omitted.

The harness does not fake a database or stub the ledger. It executes the
revision's own bytes directly and records `executed_bytes_digest` beside every
decision, so a decision that is not traceable to the bytes that made it cannot
be reported.

## The effectful control, proven rather than asserted

`WORKER-PROMPT.md:124-125` requires the effectful control to change the next
descendant-producing episode **after restart**, and says a cosmetic source
edit is not this control.

The arm is built from
`channel._revision_source('(len(view.get("experience", [])) or 12)')`, the
construction `m4-eligibility.md:130-141` names as gate-passing.

- In process, the incumbent executes `x = 3` and the revision executes
  `x = 12`.
- The store is written to disk, the interpreter exits, and a **second
  `python -c` process** reopens the store with `FrontierStore`, recompiles
  `active_package["imp_source"]`, and reads `x = 12` where the parent's store
  reads `x = 3`. Recorded as
  `restart.effectful_changed_after_restart: true` and
  `restart.effectful_matches_in_process: true`.
- `test_the_effectful_control_is_not_a_cosmetic_source_edit` asserts the
  converse directly: adding a comment changes the digest and changes the
  decision not at all, while the effectful source changes both.

So the claim is a cross-process measurement of a persisted store, not an
assertion that the two strings differ.

## The three other controls, from one starting condition

Every arm adopts over the same parent, the same mission and the same
authority. The frozen digest is taken on both sides of each adoption.

| Control | Executes | Declares | In range | Refused by instrument |
|---|---|---|---|---|
| incumbent | 3 | 3 | yes | no |
| known-effect | 8 | 8 | yes | no |
| no-op | 3 | 3 | yes | no |
| disconnect-bytes | 3 | 3 | yes | no |
| disconnect | 16 | 16 | **no** | **yes** |
| effectful | 12 | 12 | yes | no |

The disconnect's refusal is reproduced, not described: `x = 16` is outside
the task's `0..15`, `_rules.execute_predictor` raises `RuleRefused`
`illegal-input`, and `descendant_built` is `false`. The disconnect-bytes
control shares `x = 3` with the incumbent and differs from it in digest, which
is the C15 shape the module documents.

## The freeze, structurally

`WORKER-PROMPT.md:126` requires that the program cannot alter grants,
accounting, executor limits or sealed assessment. Six writes are attempted on
real bytes the real constructor produced, and each refusal is read back:

| Attack | Refusal |
|---|---|
| `view["grant"] = {}` | `writes view['grant'], a frozen field` |
| `view.update({"used": {}})` | `view.update writes the frozen field 'used'` |
| `view.pop("authority", None)` | `view.pop writes the frozen field 'authority'` |
| `view["execution_limits"] = {}` | `writes view['execution_limits'], a frozen field` |
| `view["sealed_results"] = []` | `writes view['sealed_results'], a frozen field` |
| `view["evaluator"] = "none"` | writes `evaluator`, a frozen field |

The clean source is admitted, so a guard that refused everything would fail
the seventh assertion. `test_the_guard_covers_every_frozen_field_by_name`
requires each of the six field **names** to appear in the refusals, because a
count of six passes against a guard narrowed to one field. That test was
added after the first version passed on a deliberately weakened guard; the
weakened guard now fails two tests.

## The comparison, and why there is none

Paired by seed against the incumbent on the independent `audit` split, 150
seeds, all sixteen reachable inputs:

- ten of sixteen inputs produce a positive delta.
- the largest is `x = 12` at `+0.006667`, `z = +1.49`.
- **no input reaches `|z| >= 1.96`.** The largest `|z|` over all sixteen is
  `1.4889`.
- `channel.noise_floor` over the same cohort reports `resample_spread`
  `0.009778`, and the reachable spread (`0.006667`) **sits inside it**.
- `best_probe_agrees: false`. Half A's best is 12, half B's is 4.
- Four interleaved quarters argmax to `9, 12, 4, 4`.

So the panel rule requires `|z| >= 1.96` per arm, gets zero clearing arms,
and returns `built: false` with `reason: "no reachable input clears the noise
floor"` and `arms: []`. `benefit_measured` is `false`.

This is deliberate and it is the rule, not a hardcoded no.
`test_the_panel_rule_builds_one_when_an_arm_really_clears_the_bar` hands
`panels()` rows that clear the bar and requires arms to come back; a stub
that always refuses fails that test.

Note what this is **not**. It is not "the tasks lack headroom":
`evidence_ceiling` over the same 150 seeds reports a frozen-reducer paired
delta of `+0.000889` at `z = 0.074`, and the incumbent's own mean is
`0.059111`. The reachable range across all sixteen inputs is
`0.056889` to `0.065778`. This decision has a spread of `+0.008889` from its
worst input to its best and the noise floor is `0.009778`. A benefit claim
here is not waiting on a better acquisition; it is waiting on a substrate that
separates.

## Attacking the premise: does the clause need a *learned* revision?

**It requires an inherited change, not a learned one, and it does not
require the change to have come from a model.**

`WORKER-PROMPT.md:128-129` reads "Eligibility is an inherited change to the
acquisition procedure, not a favorable solver score." The word governing
eligibility is *inherited*, not *learned*. The sentence asking for live
acquisition ("Attempt live acquisition of an eligible revised learning
program") is a separate instruction, and the honest negative it reserves is
for the case "If no eligible revision is acquired".

So there are two readings, and they have different consequences:

1. **Authored is sufficient for the mechanism, and that is now measured.**
   The apparatus, the controls, the restart behaviour, the freeze and the
   ceiling are all established without a model. This report is that
   measurement. Nothing here is a claim about acquisition.
2. **Authored is insufficient for the acquisition claim itself.** An authored
   revision has no dispatch, no route, no model and no provenance, so it can
   never enter an acquired arm. `learner_revision.py:1184-1192` keeps the
   controls out of the acquired arm for exactly this reason and that is
   correct.

I hold (1) as delivered and (2) as still open. The boundary is drawn at
provenance, not at effort.

**If the live route is taken, what it must supply.** A reply to
`USER_TEMPLATE` on the pinned route that survives all six gates, of which
gate 6 is the one this host could not execute. Then `run_campaign` drives
the arm and `compare` scores it. The standing authorization in
`WORKER-PROMPT.md:136-143` covers fresh finite experiments on a verified free
route, and token consumption on those routes is not a financial concern. **I
made no model call and no network call.** `test_the_harness_makes_no_network_call`
runs the harness in a stripped environment and asserts it completes.

**And here is the finding that should stop that run before it spends
anything.** A live acquisition would buy a panel whose every arm is inside
the noise floor. The run would report `eligible: 1` and a delta near zero,
and a reader would have to read this file to know that the zero was available
in advance. Acquiring an eligible revision is worth doing, because it closes
the acquisition question the project has been carrying since E4. It is not
worth doing in expectation of a benefit number.

## RUN_VERSION discipline

The artifact carries `run_version: "invl02-e4-run-v2"`, read from
`learner_revision.RUN_VERSION` rather than pinned in the harness, so a harness
copy cannot drift from the run's own freeze. `test_the_harness_reports_the_run_version_it_measured_under`
asserts both the identity and the literal `v2`.

The cross-freeze trap is closed in the direction that matters: an arm acquired
under `-v1` cannot be compared with anything this harness reports, because
the artifact names `-v2` and the prompt text is part of the freeze. The
harness's own arm is additionally pinned to the prompt: `EFFECTFUL_EXPRESSION`
must name the same integer as one of the expressions the current prompt
offers, checked by executed behaviour rather than by string, because the
prompt offers `len(view["experience"]) or 12` and the harness writes the
`.get(...)` spelling of the same decision.

## Red-first verification

Every claim was checked by breaking it and observing the failure, then
restoring the tree. Counted in the command that produced the set.

| Sabotage | Tests that fail |
|---|---|
| revert `eb0538fa` (prompt back to `-v1`) | **2** of 23 |
| narrow `FROZEN_FIELDS` to `('grant',)` | **2** of 23 |
| build the panel from the best input regardless of the bar | **5** of 23 |

On the fixed tree: **23 passed, 0 failed**. On the tree with the prompt
repair reverted: **20 passed, 2 failed**.

The first version of the freeze-guard suite passed against the narrowed
guard, because it asserted a count of six rather than the field names. That
is recorded here rather than quietly fixed: the count was the green that
meant nothing.

## What CI must confirm

1. **All 23 tests under the `postgres:18` service container.** They pass
   locally by direct import; no local pytest starts without a run claim.
2. **Gate 6 executed, not read.** `classify_revision` on
   `_revision_source('(len(view.get("experience", [])) or 12)')` must return
   `eligible`. This is the one gate `m4-eligibility.md:310-315` left open and
   the one this lane could not close. If it refuses, the effectful arm is not
   eligible and the mechanism measurement above describes bytes the rule
   would reject.
3. **`drive_improve_round` under a real authority**, which would replace this
   harness's direct execution with the production path and confirm the
   `x = 12` decision survives the round rather than only the restart.
4. **`test_m4_eligibility.py`'s four tests**, unchanged by this lane and
   still CI-only.

## Open questions for the owner

- **Gate 6's defect stands.** `m4-eligibility.md:280-293` recorded that
  `_reducer_argmax` takes a `view` and never reads it, so gate 6 refuses iff
  the first probe is 0. Confirmed by execution at `9c73b149`:
  `_reducer_argmax(ADMISSION_VIEW) == [0]` for every view. Out of my scope
  and not fixed here.
- **The ledger row.** `PROJECT-LEDGER.md:337` records learner improvement as
  NEGATIVE with "No live revision attempt ran and no revised descendant
  cohort exists." That is still true of acquisition. It is now also true of
  the ceiling: the ceiling is measured, and it does not clear the noise. That
  is a second reason the row is negative, and it is a reason a live run will
  not remove.

## Files

- `tools/m4_mechanism_harness.py` — the apparatus and its stopping rule.
  Rerun with `python tools/m4_mechanism_harness.py --out <path>`.
- `tests/test_m4_mechanism_offline.py` — 23 tests, no database required.
- `reports/evidence/invl02-m4-mechanism/mechanism.json` — the artifact.
