# Stage 9 M0: the call-chain table, one row at a time

Lane S2, read-only. No source file was modified. Nothing here was run; every verdict
comes from reading code and from `git log -S` / `git show`. Branch
`codex/implementation-investigation-learning-02` at `1f592d9`.

The target is the 10-row table at `reports/PLAN-STAGE-09-CONNECTED.md:76-87`. That file
has one commit in its history, `85181b7` "Map the connected study before repairing it"
(2026-09-26). It has not been edited since. So the table records an intent written
before the M3 and M4 repairs landed, and three of its rows now name code that has been
replaced by later work.

**The one fact that colors every verdict below.** `85181b7` is an ancestor of `0fa7971`
("Wire the three real representations") but not of `14f5733` ("Separate launch
qualification from the causal post-effect join") or `f3af21a` ("Keep provider charges,
dispatch counts, and reservation units apart"). The last two sit on a parallel line of
work that converged after the plan was written. So rows 8, 9 and 10 were not made false
by drift. They were written against a moment that a later commit overtook, and the plan
was never re-read against the new code.

## Summary

| # | Edge | Claimed implementation | Verdict |
|---|---|---|---|
| 1 | construction response to acquired artifact | `live_construct.py`, `construct.py` | HOLDS |
| 2 | acquired artifact to selected policy | `learner.py.visible_prompt`, `policy_assess.py` | FALSE |
| 3 | selected policy to child/interpreter | `policy_step` driver, `exec_profile` bound | FALSE |
| 4 | proposed action to admission | `policy_action.admit`, `s09_arm_parity.admit_action` | FALSE |
| 5 | oracle effect to scored result | `boolean_active.run_episode`, `checker.py` | HOLDS |
| 6 | receipt to evidence boundary | `s09_receipt_diagnosability`, `offline_recompute` | FALSE |
| 7 | durable resume to remaining count | `s09_durable_state.resume_or_step` | FALSE |
| 8 | budget units to dispatch count | no correct implementation exists | FALSE (stale, now exists) |
| 9 | representation kind to real executor | only STEP is wired | FALSE (stale, all three wired) |
| 10 | causal policy decision to admitted effect | no proof exists | FALSE (stale, proof exists) |

Six false, four hold. Not one row is UNVERIFIED. I opened every file named in the table
and read the cited symbol's body, so no row carries that label.

The three "stale" rows are the interesting result. The plan presents them as the
assignment, the three missing edges a repair must add. Two of them have been added and
one was never the shape the plan described. The plan is not wrong about the world. It
is out of date about its own subject.

## Row detail

### 1. construction response to acquired artifact — HOLDS

Claim: `experiments/ad01/live_construct.py`, `construct.py` (table line 78).

I opened both. `live_construct.construct_live_policy` at
`experiments/ad01/live_construct.py:605` calls `construct.construct_policy` at
`experiments/ad01/construct.py:398` and stamps the result with
`origin=ACQUIRED_ORIGIN`. Retention is a separate durable step:
`retain_acquired` at `live_construct.py:761` refuses without
`dispatch_evidence`, validates through `frontier.validate_package`, and calls
`store.retain_acquisition`. Called live from `scripts/invl02_live.py:1887`,
`:2053`, `:2531`. The response really does become a retained, validated artifact.

### 2. acquired artifact to selected policy — FALSE

Claim: `learner.py.visible_prompt`, `policy_assess.py` (table line 79).

I opened both. They are not connected, and the table names them as one edge.
`visible_prompt` at `experiments/ad01/learner.py:114` has exactly one caller in the
repo, `model_propose` at `learner.py:240`, and it takes `charter`, `visible`,
`experience`, `retained`, `remaining`, `curriculum`. It never receives an acquired
artifact or a candidate source. `policy_assess.assess_policy` at
`experiments/ad01/policy_assess.py:412` takes `candidate_source`, `candidate_digest`
and `candidate_artifact` and grades them, but its only production caller is
`trajectory.py:871`, which routes through `assessment_profile.assess_policy`, a
different function in `experiments/ad01/assessment_profile.py:499`.

What actually happens instead: the acquired artifact reaches the policy through the
`candidate_source` argument of `policy_assess.assess_policy`, and the prompt that
produced it came from `learner.model_propose`. Two files, two edges, no call between
them. Not stale, wrong as written. `git log -S 'def visible_prompt'` shows no commit
changing this pairing, so this row was not correct when written either.

### 3. selected policy to child/interpreter — FALSE

Claim: "`policy_step` driver, `exec_profile` bound", "exists for STEP only" (table
line 80).

The STEP half is right and the bound executor is wrong. `run_policy_step` at
`experiments/ad01/policy_step.py:424` calls
`method_exec.run_step_out_of_process` at `policy_step.py:437`, not `exec_profile`.
I read that body: `experiments/ad01/method_exec.py:712` builds a work directory, stages
`policy.py`, and constructs `LocalLauncher` at `method_exec.py:769` with
`payload={"profile": PROFILE}` where `PROFILE = "local-process"`
(`src/settlement/launcher_local.py:45`).

`exec_profile` is not on this path. It is imported by `src/settlement/artifacts.py:21`,
`src/settlement/boot.py:102` and `src/settlement/launcher_runsc.py:23`, and by no file
under `experiments/ad01/`. `git log --all -S 'exec_profile' -- experiments/ad01/policy_step.py
experiments/ad01/method_exec.py` returns nothing, so the name was never bound there on
any branch. The cited executor is a module that exists and is real, attached to an edge
it does not touch.

The STEP-only half is also out of date. `_python_step_factory` at
`experiments/ad01/s09_arm_parity.py:480` carries a docstring saying it accepts `world`
and "only `boolean` is served here". `register_typed_ast` at `s09_arm_parity.py:571`
and `register_action_graph` at `:645` both exist and are both wired. See row 9.

### 4. proposed action to admission — FALSE

Claim: `policy_action.admit`, `s09_arm_parity.admit_action` (table line 81).

`s09_arm_parity.admit_action` is real: `experiments/ad01/s09_arm_parity.py:449`, called
at `:710` and `:742`. `policy_action.admit` does not exist. I grepped every occurrence of
`admit` in `experiments/ad01/policy_action.py` and got nothing but a docstring note at
line 4. What `policy_action` actually offers is `parse_action` at `:68` and the
`ACTION_KINDS` tuple at `:32`, and `admit_action` calls `policy_action.parse_action` at
`s09_arm_parity.py:466` under its own name. One of the two cited implementations is
half a name.

The row's own qualifier, "exists, one schema", survives. `ACTION_KINDS` at
`policy_action.py:32` is the single tuple, and `admit_action` checks membership twice
(`s09_arm_parity.py:460` against `ACTION_KINDS`, `:472` against the advertised schema),
so one schema is accurate.

### 5. oracle effect to scored result — HOLDS

Claim: `boolean_active.run_episode`, `checker.py` (table line 82).

I opened both. `run_episode` at `experiments/ad01/boolean_active.py:114` drives a
session, and its return carries `"final": session.score(session._committed)`. The world
is dispatched by name through `_WORLDS` at `experiments/ad01/s09_arm_parity.py:47`, so
the same harness reaches `boolean_active` and `second_active`, which is the "two toys".
`checker.py` at `experiments/ad01/checker.py` is a record verifier, and it does consume
the scored pair: `_verify_quality` at `:129` iterates `("initial", "final")` at `:142`
and rejects `unknown` as unevaluable rather than scoring it zero, per its own docstring
at lines 1-8. The oracle effect is graded, and the grader refuses to invent a number.

The qualifier is now understated rather than wrong. `_WORLDS` names three worlds, the
third being `swe` (`s09_swe_world.run_episode` at `:531`). The row still holds; it
undercounts.

### 6. receipt to evidence boundary — FALSE

Claim: `s09_receipt_diagnosability`, `offline_recompute` (table line 83).

`offline_recompute` is real and heavily used, imported by `scripts/invl02_live.py:60`
and called at seven sites there. `s09_receipt_diagnosability` is not on any production
path. I grepped `src/`, `scripts/` and `experiments/` for the module name and for
`qualif`/`diag.`; the only hits are `tests/test_s09_receipt_diagnosability.py:21` and
`tests/test_s09_merged_tip_regression.py:82`. The module is 574 lines and no production
code imports it.

Worse, the two named halves are not the same edge. `offline_recompute` re-derives study
ids and counts from a freeze; it does not receive a receipt from the diagnosability side
at all. Nothing joins the two. The row names two files as one connected pair where one
is unconnected and the other does different work.

### 7. durable resume to remaining count — FALSE

Claim: `s09_durable_state.resume_or_step` (table line 84).

`resume_or_step` at `experiments/ad01/s09_durable_state.py:251` is real and does what
its name says: `load_step`, return the committed step, else `execute` and
`persist_step`. But it has no production caller. The only two references outside its own
module are `tests/test_s09_durable_state.py:104` and a string list in
`tests/test_s09_merged_tip_regression.py:170`.

The durable path that is live is `agenda_policy`. It calls
`policy_step.load_policy_state` at `experiments/ad01/agenda_policy.py:712` and
`policy_step.persist_step_transition` at `:773`, `:795`, `:834`, `:865`, `:882`, `:890`.
The count the row asks about is computed there and not in `s09_durable_state`:
`_step_remaining` at `agenda_policy.py:493` writes `remaining["policy_steps"]`, and
`agenda_policy.py:747` computes `model_remaining`. And the "remaining count" the row
implies is not carried by the durable record at all: `DurableStep` at
`s09_durable_state.py:75` holds `cid`, `seq`, `binding`, `view_digest`, `action`,
`state`, `attempt_id`, `effect_id`, and no count.

So this row names a function that is unused, points at the wrong module for the count,
and asserts an edge to a field the durable record does not have.

### 8. budget units to dispatch count — FALSE, stale

Claim: "**no correct implementation exists**", CS-01 (table line 85).

This row was true and is now false, in the direction the plan wanted.
`study_ceiling` at `experiments/ad01/s09_study_preflight.py:1230` now returns a dispatch
count and nothing else. Its own docstring records the repair: "Three currencies, one
subtraction." It reads `max_dispatches` off the freeze at `:1247` and stops.
`route_capacity_from_freeze` at `experiments/ad01/s09_exposure_ledger.py:488` no longer
multiplies anything: it returns a `DispatchAllowance` built from `limits["max_dispatches"]`
at `:505`, and `_route_charge` at `:511` says "nothing here multiplies it by a count".

`git log -S 'def study_ceiling'` gives `f3af21a` and `46cedf8`, and
`git merge-base --is-ancestor 85181b7 f3af21a` fails, so the repair landed after the
plan. The plan is still asserting the defect is open.

### 9. representation kind to real executor — FALSE, stale

Claim: "**only STEP is wired**", CS-03 (table line 86).

Also true when written, now false. `REAL_REPRESENTATION_KINDS` at
`experiments/ad01/s09_arm_parity.py:29` is
`frozenset({PYTHON_STEP, TYPED_AST, ACTION_GRAPH})`, not the
`frozenset({PYTHON_STEP})` quoted in the plan's own CS-03 narrative at line 65. Three
registration helpers exist: `register_python_step` at `:542`, `register_typed_ast` at
`:571`, `register_action_graph` at `:645`, each with its own factory
(`_typed_ast_factory` at `:552` routing through `boolean_ast_policy.choose_action` at
`:562`, `_action_graph_factory` at `:581` through `s09_graph_budget.run_graph_step`).
`git log -S 'def register_typed_ast'` gives `0fa7971`, and `85181b7` is an ancestor of
`0fa7971`, so the plan was written first and overtaken.

The plan's own CS-03 claim that "`_run_arm` calls `boolean_active.run_episode` for every
arm regardless of kind" is also out of date: `admit_action`'s neighbours now branch per
kind through the registered `driver_factory`, consumed at `s09_arm_parity.py:688`.

### 10. causal policy decision to admitted effect — FALSE, stale

Claim: "**no proof exists**", CS-02 (table line 87).

The proof exists.
`experiments/ad01/s09_causal_proof.py` is 28,624 bytes, defines `qualify_pre_launch` at
`:561`, and `s09_study_preflight.py:1119` calls it through `qualification(config)`,
which `collect` at `s09_study_preflight.py:1253` invokes at `:1271`. `join_post_effect`
at `s09_causal_proof.py` is called separately at `s09_study_preflight.py:1184`.

The circularity the plan describes is gone by the module's own account. `launch_governance`
at `s09_study_preflight.py:1150` carries a docstring naming the defect the plan called
CS-02 and naming the replacement: "It also qualified launch using the output of the run
being launched, which is circular." The old `probe_policy_execution` does not exist
outside a test asserting its absence, at
`tests/test_s09_study_preflight.py:659`. `git log -S 'def qualify_pre_launch'` gives
`14f5733`, which is not a descendant of `85181b7`.

The plan is now assigning as work something another lane already did.

## The edges nobody checked before this lane

All ten. The table was written by the same lane that then did the work, and re-read by
no one. Four R-lane reviews exist (`reviews/STAGE-09-R1-AUTHORITY.md`,
`-R2-EXECUTION.md`, `-R3-VALIDITY.md`, `-R4-REPRODUCTION.md`); none of them challenges
a row of this table, and I did not take any of their word for a verdict here.

The three rows that had become wrong were the three the plan named as the assignment.
That is the shape of the failure. A document that lists its own defects, is treated as
scoped and closed, and is never re-read against the code that repaired those defects
will keep claiming the work is outstanding. Rows 2, 4, 6 and 7 were not stale; they were
wrong about code that existed when the plan was written, and a reviewer reading the
table rather than the source would never have caught it.

## Is M0 closable on this artifact?

No, and not because the table is bad. It is a good table of an out-of-date moment, and
it is now a liability: three of its ten rows instruct lanes to build what already
exists, and one of those three (row 9) would have lane I re-wire a representation
comparison that `0fa7971` and `136e792` already ran.

Three things are needed, in this order.

1. Re-read rows 1 through 7 against the current tree and correct rows 2, 4, 6 and 7 in
   place. Each correction names the real function. This is a coordinator edit and I did
   not make it.
2. Delete or supersede rows 8, 9 and 10. They are not "closed" rows, they are
   completed work described as outstanding. Keeping them invites a lane to redo it.
3. Give the table an owner and a re-read trigger. The plan names lane I as integration
   owner for the code, and no owner for this document. That gap is why it aged.

The plan's M1 through M4 milestones, ownership table and standing constraints are
unaffected by any of this. Only the 10-row table needs to change.

## Method and limits

Every verdict above comes from `grep` and from reading the cited symbol's body in this
checkout at `1f592d9`. I opened every file the table names, so no row is labelled
UNVERIFIED. I ran no tests, and I treated no failing test as evidence. The brief
mentions `tests/test_s09_store_cleanup.py:421` failing since `3c1e5c5` because
`experiments/ad01/e3_ladder.py` calls `admit_study_call` directly. I read that test
(`:405-424`) and confirmed it parses each file's AST and collects `node.attr`. That
claim is outside this table's ten edges, so it is recorded here as background and
carries no verdict.

What I could not settle by reading: whether `resume_or_step` and
`s09_receipt_diagnosability` are dead code or are reached through `importlib` and
`getattr` on a path my greps would not follow. I checked `s09_arm_parity.py:65`, which
does exactly that for world modules, so the pattern exists in this codebase. Settling
it needs a runtime call trace on the study driver, which this lane was told not to
produce. Both rows 6 and 7 are FALSE on the strength of the misnamed edge, not on the
strength of unreachability, so the verdict does not depend on that trace.
