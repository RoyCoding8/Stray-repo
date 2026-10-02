# w4-e4-interface: what a revisable learner decision actually is today

Lane `w4-e4-interface`. Read-only scoping audit, no implementation. Branch `codex/implementation-development-01` at `d42049c`. Host: Windows 11, Python 3.13.

`WORKER-PROMPT.md:86-90` asks for a revisable decision that changes how new capabilities are acquired, a frozen interface the reviser cannot cross, a three-part qualification, and an acquisition attempt through the real model path. This report establishes what exists so someone can decide whether E4 is a runnable experiment or a blocked one. It does not choose the experiment.

## The short answer

The mechanism is real and it does change behaviour. It has already been run once, live, and it produced a documented negative. The negative is sound, and its cause is the boundary, not the prompt and not the substrate.

Three things the ledger does not currently say, each established below:

1. **E4 has already been attempted.** A six-dispatch live campaign exists in this branch's history, with a committed result. `reports/PROJECT-LEDGER.md:44` records W4/E4 as "NOT STARTED". The line is stale, not wrong about the evidence, and the coordinator owns fixing it.
2. **The frozen interface is not enforced where the code claims it is.** `improve_channel.FROZEN_FIELDS` is checked by an AST scan for assignment targets, and nothing checks the decision the interface is *about*. A revision can change probe allocation, candidate construction and the probe target, and every one of those is admitted as `eligible`.
3. **The acquisition machinery is not structurally incapable of carrying a revision.** It carried one, six times. What it cannot do is express one, because the descendant discards the revision's choice.

---

## 1. What revision mechanism exists today

There are two modules, and they own different things. Both are real code on the branch under review.

`experiments/ad01/improve_channel.py` owns the decision and the gate. `improve_channel.py:172` names it:

```
DECISION = "diagnostic-evidence-selection"
```

`learner_revision.py:65` names the single field a revision may change:

```
REVISION_INTERFACE = "improve_channel.STEP.frontier_action.probe.inputs.x"
```

`experiments/ad01/learner_revision.py:1-9` states the design: a model proposes an executable change to a real learning decision, and the module "decides whether the bytes it returned are an eligible intervention, drives a real improve round with the accepted bytes, and scores the descendants the round produced".

**It changes behaviour, it does not merely report.** The chain is real end to end:

- `learner_revision.py:1202` dispatches to a pinned route and refuses without one (`:318-322`).
- `improve_channel.py:1012-1014` runs the returned bytes **out of process**, in a sandbox, through `method_exec.run_step_out_of_process`.
- `improve_channel.py:1295-1298` spends the chosen input against a real instrument and reads an observation back.
- `improve_channel.py:1196` `leaf_construct` turns the observation into a descendant package.
- `learner_revision.py:841` scores that descendant on a fresh cohort.

A comparison helper could not do that. This is a mechanism.

The distinction worth drawing is between `improve_channel` and the estimator the assignment's hint points at. `e2_replication.py:650` imports `learner_revision.paired`, which is `learner_revision.py:860` — a paired difference with a standard error. **That is a reporting helper and nothing more.** It computes a number from two lists. It is not the revision mechanism, and reading E4 through it would be the mistake the assignment warns about in its last sentence.

### It has already run

`git log -- reports/evidence/inv_r1_e4/` returns three commits, the newest being `111ec3a` "E4: a qualified negative, with two findings against the lane's own claims". `git merge-base --is-ancestor 111ec3a HEAD` confirms it is an ancestor of this branch. The artifact is at `reports/evidence/inv_r1_e4/result.json` and the raw campaign at `reports/evidence/inv_r1_e4/run/campaign.json`.

Reading `campaign.json` directly:

```
n dispatches 6
--- 0 op invl02-e4-revision-0001 acq model-acquired reason: revision reproduces the frozen reducer's choice
--- 1 op invl02-e4-revision-0002 acq model-acquired reason: revision reproduces the frozen reducer's choice
--- 2 op invl02-e4-revision-0003 acq model-acquired reason: revision reproduces the frozen reducer's choice
--- 3 op invl02-e4-revision-0004 acq model-acquired reason: revision reproduces the frozen reducer's choice
--- 4 op invl02-e4-revision-0005 acq model-acquired reason: revision reproduces the frozen reducer's choice
--- 5 op invl02-e4-revision-0006 acq model-acquired reason: revision reproduces the frozen reducer's choice
```

All six returned executable STEP bytes off a free Nvidia route. All six were refused as `delegates-to-unchanged-reducer`. The refusals are correct. Dispatch 1's reply computes `x` as `len(view.get("experience", []))`, which is `0` on the step that spends the probe, and `0` is the frozen reducer's own top-ranked input. Dispatch 3's `% 16` variant is the same answer. The model produced a selector in syntax and a constant in behaviour, and `improve_channel.py:367` `delegates_to_frozen_reducer` caught all six by executing them.

The result artifact's own conclusion is right, and it is the most useful sentence in the repository for this decision:

> "The learner has large headroom, and this boundary cannot express it, because a descendant runs the authored menu's single input rather than the revision's choice. The blocker is the boundary, not the substrate and not the prompt."

`evidence_ceiling` in `result.json` puts the two numbers side by side: the frozen reducer reaches `0.5017` unqueried-input accuracy against the incumbent's `0.0587`, a paired delta of `0.443` at `z = 17.4`. The E4 boundary's own reachable range is `0.00622`. The headroom is 70x the boundary's expressive range.

## 2. The four candidate decisions, ranked

All four named in `WORKER-PROMPT.md:86`. Ranked by how cleanly a reviser changes the learner rather than adding text to a prompt. The ordering is the deliverable; the locations are the evidence.

### 1. Diagnostic evidence selection — real, live, but the descendant discards it

`improve_channel.py:172`, reached through `improve_channel.py:80` where `IMPROVE_LOW_SOURCE` emits `{"kind": "probe", "inputs": {"x": 3}}`.

A reviser changes the input. It is genuinely consulted at `improve_channel.py:1295-1298`, and the input really reaches the instrument.

The defect is downstream and it is structural. `improve_channel.py:454-458` states it in the module's own comment: the evidence a descendant actually runs is not the evidence the reviser gathered, because `leaf_construct` replaces the improvement source with a member of the authored menu. `_STRATEGY_SOURCE` (`improve_channel.py:136`) has exactly two members, so `REACHABLE_EVIDENCE` (`:489`) is a two-element tuple whatever the reviser does. Confirmed against the committed result: both the known-effect arm and the no-op arm built `control-high-r1`. The reviser's integer chooses *which* menu member; it never widens the menu.

This is why the campaign's six replies could not have helped. The boundary is a selector over a two-element set, and the campaign's null is a real finding about that set.

### 2. Probe allocation — real, and currently **outside** the freeze

`improve_channel.py:80-81`, the `requested_resources` on the probe action.

A reviser changes how much it asks for. It alters the learner's behaviour directly: the request flows to `store.admit_and_spend` at `improve_channel.py:1311`, which enforces the grant at `frontier.py:1796-1802` via `_check_spend` (`frontier.py:1736`).

The important finding is that this is **not** in the frozen set, and the gate does not catch it. Measured on this branch:

```
baseline selector (x=8/3)            -> eligible
asks 8 queries/8 steps               -> eligible
asks 0 queries/0 steps               -> eligible
candidate ctor forced high           -> eligible
construction decision rewritten       -> eligible
probe target rewritten               -> eligible
never probes; jumps to construct     -> eligible
```

Every line above is `classify_revision` (`improve_channel.py:387`) returning `eligible`, against a real store built the way `learner_revision.py:1336` `_admit` builds one. The base is `learner_revision._selector(improve_channel._revision_source("8"), "8", "3")`, so the view-dependence gate is satisfied by construction and cannot be the reason for any line.

An eight-query request is over the `EXECUTION_LIMITS` ceiling of 8 queries in total (`improve_channel.py:183`) and is still admitted. The grant catches it later, at spend time, and the refusal is recorded as a round log entry (`improve_channel.py:1319-1323`) rather than an eligibility refusal.

This ranks second, not first, because the grant does stop the over-spend. But the *interface* does not, and the assignment says the reviser "cannot modify grants, accounting, execution limits". The declared freeze and the enforced freeze disagree here.

### 3. Candidate construction — real, and currently **outside** the freeze

`improve_channel.py:91-95`, where the observation bit selects `strategy`, and `improve_channel.py:1196` `leaf_construct`, which installs the candidate.

A reviser changes how the candidate is built. Ranked third for a specific reason: on the current substrate the two menu members differ only in which single input they probe (`_STRATEGY_SOURCE`, `improve_channel.py:136`), so construction has almost nothing to decide. `improve_channel.py:981-983` confirms the reachable set is `("low", "high")` and nothing else.

That is a substrate limitation, not an interface one. A reviser that rewrote construction is admitted as eligible today (measured above), and on a richer menu it would be the strongest of the four. The `construct` kind is already in `IMPROVE_KINDS` (`improve_channel.py:42`), so the vocabulary is there.

### 4. Development-only repair policy — not a decision in this substrate

`src/settlement/development.py` has the production machinery: `select` at `:982` decides select-or-reject on development checks, and `construct` at `:700` builds a candidate through a real sandbox.

But there is no revisable *policy* there to revise. `select` is not a policy: `development.py:1000-1003` computes `passed` from `grade_outcome` and a `match` flag and then writes `{"decision": "select" if passed else "reject"}` inline. There is no indirection between the checks and the decision, so there is nothing for a reviser to own.

Ranked last on reachability as much as substance. `improve_channel` is reachable from production-shaped entry points — `live_construct.py:1116` and `scripts/invl02_live.py:1878` both call `drive_improve_round`. `development.py` is reachable from `run_dev_episode.py` and `run_live_abc.py`, and **not** from `ad01.cli`, which is the E4 study's own entry surface. A reviser wired to the E4 apparatus would reach one and not the other.

## 3. The allowed interface: prose, plus two real mechanisms, minus the check that matters

The forbidden list in `WORKER-PROMPT.md:88` is grants, accounting, execution limits, evaluators, sealed assessments. `improve_channel.py:177` declares:

```
FROZEN_FIELDS = ("grant", "used", "authority", "evaluator", "sealed_results",
                 "execution_limits")
```

Enforcement is layered, and the layers differ sharply in strength. Measured rather than assumed:

**Enforced by process isolation (strong).** `verify_step_source` (`method_exec.py:1248`) refuses imports (`:1269`), dunder access (`:1271-1274`) and a set of reflective calls (`_FORBIDDEN_CALLS`, `method_exec.py:38-42`). The bytes then run in a separate process. I dumped the view a step actually receives:

```
view keys: ['authority_remaining', 'contract_versions', 'environment_digest',
 'environments', 'experience', 'frontier', 'frozen_source', 'improvement_budget',
 'instruments', 'mission', 'obligations', 'purpose', 'retained', 'target_digest']
any store/authority handle: []
```

The sandboxed learner cannot reach the store, the grant object or the evaluator even if its bytes tried, because none of them cross the process boundary. This is the real reason grants and accounting are safe, and it is not the reason the code gives.

**Enforced by an AST scan (narrow).** `_attempts_frozen_write` (`improve_channel.py:838`) walks the tree and refuses a *write position* on a frozen name. It works on the case it names:

```
attempts_frozen_write: True
```

for bytes assigning `grant["used"]`. It is a real check and I confirmed it fires. Its blind spot is that it only knows assignment targets and the five forbidden call names.

**Not enforced at all: the decision the interface is about.** Nothing checks that a revision changed only `probe.inputs.x`. `classify_revision` (`improve_channel.py:387`) checks five things: the bytes parse as STEP, a view exists, the bytes emit a probe, `x` is view-dependent, and the choice is not the frozen reducer's. None of those is "and nothing else changed". A revision that keeps a valid view-dependent `x` while rewriting `requested_resources`, the construction branch, the probe target or the whole step skeleton is eligible, as the six measured lines above show.

**The one enforcement that is genuinely redundant, helpfully.** `admit_revision_under_freeze` (`improve_channel.py:811`) captures frozen state before and after and raises `FrozenFieldViolation` at `:832` if it moved. `learner_revision.py:818` `check_frozen` does the same around adoption. Belt and braces, and the redundancy is justified by a cross-process boundary the AST scan cannot see.

Verdict: **partially enforced.** Grants, accounting and the evaluator are protected by isolation, which is real and strong. Execution limits are protected by the grant at spend time, not by the interface. The scope of the revision itself is prose only.

## 4. The three-part qualification

All three are present, and the module is honest that it built a fourth.

**Known-effect revision — present.** `learner_revision.py:497` `reviewer_revision()`, written independently of any model, with its effect written down in advance at `:466-474` (`REVIEWER_WHY`). It names input 8, the ceiling's argmax on the audit cohort. It works. From `result.json`:

```
ARM known-effect | x_probed 8 | cand control-high-r1 | elig eligible | refused false
   paired: delta -0.00133 z -0.5577 measured true mean_rev 0.0609 mean_inc 0.0622
```

**No-op control — present.** `learner_revision.py:517` `no_op_revision()`. Same view read as the known-effect control, differing only in the integers named, so the two differ at the decision and nowhere else. From `result.json`:

```
ARM no-op | x_probed 3 | cand control-high-r1 | elig eligible
   changed: changed_decision false
   paired: delta 0 measured true
```

Exactly zero by construction, as `:531-537` claims.

**Disconnect counterexample — present, and there are two of them.** `learner_revision.py:544` `disconnect_revision()` names input 16, which `validate_improve_action` (`improve_channel.py:978-980`) refuses at the range check. From `result.json`:

```
ARM disconnect | x_probed -1 | refused true
   error: the round's own action validator refused the arm: probe needs an input x in 0..15
   paired: no_descendant true
```

`learner_revision.py:599` `disconnect_bytes_revision()` is the subtler one and it is the better control. It produces **different bytes, admitted as eligible, that change nothing**, because `view["experience"]` is empty on the step that spends the probe so the `else 3` arm runs. That is the C15 shape, and its docstring at `:611-613` states the point: "an eligibility rule cannot tell a revision that chooses from one that merely contains a choice."

**Which of the three catches a reviser that does nothing?** The **disconnect-bytes** control, and only it. Reasoning:

- The known-effect control proves the machinery *can* carry a change. A do-nothing reviser still passes it; it is a positive control.
- The no-op control proves a change-free revision reads as exactly zero. A do-nothing reviser also passes this, and would read as zero. It cannot distinguish "correctly decided the same thing" from "never ran", which `learner_revision.py:551-553` says explicitly.
- The disconnect-bytes control is the only one keyed on `changed_decision`. `qualify` (`learner_revision.py:1031-1032`) requires `changed_decision is False` **and** bytes that are not the incumbent's. A do-nothing reviser that returns the incumbent verbatim is caught earlier, by `acquire`'s identity check (`learner_revision.py:428`). But a reviser that returns *different bytes* that change nothing passes the identity check and is caught only by disconnect-bytes.

So the apparatus's own fourth control is load-bearing, and `improve_channel.CONTROL_ROLES` (`improve_channel.py:888`) lists only three roles. The fourth lives in `learner_revision.CONTROL_BUILDERS` (`:645-650`) and is in `qualify`'s iteration but not in the channel's declared role tuple. Worth aligning; not a defect in the run.

## 5. The trap: can the acquisition machinery carry a revision?

**It can. E4 is a real experiment, not a blocked one.** The evidence that settles it is the committed campaign itself: six dispatches reached a free route, six returned executable STEP bytes, and six passed `judge_acquisition` (`learner_revision.py:221`) as `model-acquired`. The pipeline carries model-authored revision bytes all the way through parsing, verification, sandboxed execution, probe spend, observation read-back and descendant construction.

The assignment's warning is well taken and the prior evidence is accurate. The ledger records the M3 campaign as "6 attempts, 3 acquired ENTRY wrappers using authored ddmin" (`reports/PROJECT-LEDGER.md:34`) and its task utility as negative at `-0.153` (`:35`). That is a **task solver**, and `improve_channel.py:419-422` already encodes the distinction as a refusal reason:

```
INELIGIBLE_SOLVER = "task-solver-not-decision"
```

with the text "revision picks a fixed input whatever the learner has seen, so it answers the task instead of choosing what to observe." I confirmed that gate fires: the incumbent's own bytes, submitted unmodified, are refused as `task-solver-not-decision`. The code can tell a solver from a reviser, and it refused one.

**The negative is real and correctly attributed.** Six live replies, all refused for naming the reducer's own top input, all recorded with their operation id, route, model and response digest. `live_attributable` (`learner_revision.py:1389`) re-derives attribution from the dispatches rather than trusting the verdict, and `make_result.py`'s `live_claim` walks the dispatches again refusing to write an artifact whose live claim does not survive. That is the correct posture and it is why the artifact is trustworthy.

**So the single most valuable thing to hand over is this.** E4 is not blocked, and it is not a repeat of the M3 trap. It is a *completed negative* whose cause is a boundary that cannot express the decision. The blocker is specific and locatable:

- `improve_channel.py:136` `_STRATEGY_SOURCE` has two members, so `REACHABLE_EVIDENCE` at `:489` is two integers wide.
- `improve_channel.py:454-458` states that the descendant runs the menu's evidence, not the revision's.
- The ceiling (`result.json`) is `0.00622` and the headroom (`evidence_ceiling`) is `0.443`.

A perfect revision of this boundary moves a descendant by about 0.0062 against a headroom of 0.443. **No prompt, model or dispatch budget changes that number.** It is arithmetic on the menu.

That is a completed question, not a blocked one, and `WORKER-PROMPT.md:103` says "A negative valid study can complete its question". This one qualifies. What the assignment asks for next, "If no revision is admissible, report that observed result and retain the qualified mechanism separately", is what already happened: the observed result is committed, and the qualified mechanism is retained and independently tested.

## 6. Host blocker, unrelated to the design

Worth recording because it bounds what can be re-run from this machine.

Every child-process test fails here, and the reason is a named platform refusal rather than a defect. Discovered by dispatching a trivial `print(1)` through the same launcher:

```
refused_reason: child-limit-unavailable: child limit(s) cpu_seconds cannot be
enforced on Windows: CPython refuses preexec_fn, so the child cannot limit itself
before exec. Run on a supported Linux host or record this deployment limitation.
The child was NOT run unbounded.
```

`src/settlement/launcher_local.py:869-877` raises this deliberately, and the refusal is correct: running unbounded would be worse. `method_exec.py:1466` then surfaces it as `refused: child receipt identity is missing`, which is a lossy message. All 15 tests in `tests/test_s09_e4_qualification.py` fail on that single cause:

```
15 failed in 13.54s
```

with `child receipt identity is missing` as the only distinct error. This is host-level, not E4-level: the incumbent's own `IMPROVE_LOW_SOURCE` fails identically, with no revision in the picture.

Two consequences. First, **E4 cannot be re-run from this host**; the arms drive real children at `learner_revision.py:820`. Second, the qualification the result artifact reports was produced on a host that could spawn, and the test file that would re-verify it cannot run here. The committed result stands on its own evidence, but a coordinator re-running it on Linux should know the 15 failures are the host, not a regression.

Unrelated note: `pytest` needs `S09ISO_DISABLE=1` here anyway, or `tests/conftest_isolation.py:705` aborts collection trying to reach a Postgres admin DSN that is not running.

## 7. Findings for the coordinator

Ordered by how much they change the E4 decision. Not edits. Another lane owns each of these files.

1. **`reports/PROJECT-LEDGER.md:44` is stale.** It records W4/E4 as "NOT STARTED" and `:34` as the learner-revision line. A completed live campaign with a committed result is in this branch (`111ec3a`). The ledger should record the negative and its cause, not the absence.

2. **The interface is not enforced against the thing it names.** Six measured variants at `improve_channel.classify_revision` (`improve_channel.py:387`) return `eligible` while changing probe allocation, candidate construction, the probe target, or the step skeleton. `WORKER-PROMPT.md:88` says the reviser "cannot modify ... execution limits". The grant stops the over-spend at `frontier.py:1736`, but the interface does not, and a report claiming a frozen interface would be describing prose. The fix belongs at the earliest wrong boundary, which is `classify_revision`, not in a downstream validator.

3. **The reason string for the child refusal is lossy.** `method_exec.py:1466` reports a missing receipt identity where the launcher already refused with a full explanation. A coordinator reading a test failure here will not find the Windows `preexec_fn` reason without re-deriving it. Threading `refused_reason` through would cost little and would have saved this audit an hour.

4. **`improve_channel.CONTROL_ROLES` (`:888`) omits `disconnect-bytes`.** `qualify` uses it, `learner_revision.CONTROL_BUILDERS` defines it, and it is the only control that catches a do-nothing reviser. The channel's declared role tuple and the run's actual controls disagree.

5. **The four candidate decisions are not equally reachable.** `improve_channel` is reachable from `live_construct.py:1116` and `scripts/invl02_live.py:1878`. `settlement/development.py` is not reachable from `ad01.cli`. If a future E4 wires its reviser to the production path, the choice of decision constrains the entry surface.

## 8. Undetermined

Stated as undetermined rather than guessed.

- **Whether a wider menu would produce a positive.** The headroom is real (`0.443`) and the boundary is narrow (`0.0062`), so a menu with more than two members should raise the ceiling. Whether it rises above the noise floor is a measurement nobody has made. `improve_channel.channel_headroom` (`:649`) is the estimator that would answer it, and it has a `measurable` flag with guards, so the instrument exists.
- **Why every model reply chose input 0.** All six computed an `x` that evaluates to 0 on the first step, and 0 is the reducer's top pick. Whether the free route is capable of choosing 5, 8 or 11 when asked, or whether something about the prompt makes 0 attractive, is untested. Six dispatches from one model on one prompt is one data point about a model, not about acquisition.
- **Whether the eligible-but-out-of-scope variants above would have produced measurable descendant differences.** They were admitted and never run. The gate admitted them; what they would have done downstream is unmeasured, and the `0.0062` ceiling suggests several would have read as flat.
- **Whether the C15 control's result generalises.** It is one control on one substrate. It demonstrates that an eligibility rule cannot distinguish choosing from containing, which is a fact about the rule, not a rate.
- **Whether the ledger's E2 "NOT STARTED" and E3 "NOT STARTED" have the same stale-ness as E4.** I checked E4's history because it was my assignment. I did not audit E2 or E3.
