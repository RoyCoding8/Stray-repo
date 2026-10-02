# W5 review pass 1 — independent adversarial review

Reviewer lane. I wrote none of the code under review. Read-only on the main checkout;
this file is my only write. No commit. No full test suite was run: exactly three named
files, plus offline recomputation commands (`w1_e1_campaign_r2 verify`) and one-tap
`uv run python -c` probes. No live model call, no Jev, no paid route.

Reviewed range: `d42049c..97b320a` on `codex/implementation-development-01`, plus the W0
work on `edee2b6` and earlier. The main checkout has since advanced to `86786cf`
("Bring the ledger and roadmap into exact agreement with the batch"), which is
`97b320a` plus one documentation commit. Findings below are stated against `97b320a`
unless noted, and I checked `86786cf` for the two files it touched.

---

## 1. The seven claims

### Claim 1 — `PR_SET_NO_NEW_PRIVS` was wrong (1 is `PR_SET_PDEATHSIG`); 38 is right

**HOLDS, and it is out of the batch's stated range.**

*Scope correction first, because this matters for how the handback should read.* The
fix is `655feb3` ("Install the child limits the launcher declares, and fix the prctl
constant"), dated 2026-09-29 15:53. `git merge-base --is-ancestor 655feb3 d42049c`
returns true. It is therefore **before** `d42049c`, and outside both `d42049c..97b320a`
and `edee2b6..` — it predates `edee2b6` by 11 commits. The brief lists it as a claim of
this batch. It is a claim of an earlier one. This does not make it wrong, but a handback
that attributes it to the wrong batch is a provenance error, and the brief has already
been burned once by exactly this failure mode (the "2 attempts pending" claim, retracted
in `86786cf`).

*Evidence sufficiency.* Excellent. Three independent layers:

1. Structural. `src/settlement/launcher_local.py:129` `_PR_SET_NO_NEW_PRIVS = 38`,
   `:130` `_PR_GET_NO_NEW_PRIVS = 39`, and every `prctl` call site (`:180`, `:296`) now
   goes through the named constant. `tests/test_launcher_local_bounds.py:440` asserts
   the bare `prctl(1, 1` literal is absent from `_landlock_restrict` by reading the
   source, so a regression cannot reappear quietly.
2. Behavioural, against the kernel. `tests/test_launcher_local_bounds.py:391-427`
   spawns a fresh interpreter and asserts the flag reads back `1`. A fresh interpreter
   starts with the flag clear, so the value is attributable to the module's setter
   alone. This is the right shape of test: it compares the module's behaviour to the
   kernel's, not to a literal.
3. Negative control. `tests/test_launcher_local_bounds.py:492-508` monkeypatches the
   constant back to `1` and asserts `_no_new_privs_settable()` returns `False`, then
   back to `38` and asserts `True`. A test that only asserted `38 == 38` would pass with
   a wrong read-back wired in; this one does not.

*Soundness.* `1` is `PR_SET_PDEATHSIG` and `38` is `PR_SET_NO_NEW_PRIVS` in
`<linux/prctl.h>`; that is not in dispute and the code comments say so at `:126-128`.

*Strongest counter-reading, and it is a real one.* The independent evidence in
`reviews/STAGE-09-OPEN-DECISIONS.md:195-215` and `reviews/STAGE-09-N36-N65.md:105-125`
reports that on the **actual campaign host**, `PR_SET_NO_NEW_PRIVS` returns success and
does nothing for a Python process, verified three ways:

```
C binary, same shell:       rc=0  NoNewPrivs=1
Python process, same shell: rc=0  NoNewPrivs=0
```

So on that host even the corrected call silently does nothing, and `probe_landlock()`
correctly returns `available=False` — which is the *right* outcome, but for a reason
that is not the constant. This means the constant fix did not unblock Landlock; the
read-back is what surfaces the host's behaviour. The completion matrix
(`reports/STAGE-09-COMPLETION-MATRIX.md:80`) already records this correctly
("NOT PROVEN... the denial itself is not [proven]... Needs bare metal or a VM"). The
matrix and the claim are consistent. No correction needed, but the claim should not be
read as "this fixed Landlock", and the commit message does not say that.

*Residual risk, undetermined.* The read-back verifies the flag, not Landlock's own
enforcement. A kernel could accept the flag and still not restrict. The matrix's
"NOT PROVEN" already covers that, and the out-of-band C test in
`reviews/STAGE-09-N36-N65.md:118-125` is the right shape of evidence for it.

### Claim 2 — a `preexec_fn` failure surfaces as `SubprocessError`, which is not an `OSError`

**HOLDS. I reproduced it.**

*Reproduced.* `uv run python -c` on this host:

```
SubprocessError bases: (<class 'subprocess.SubprocessError'>, <class 'Exception'>,
                       <class 'BaseException'>, <class 'object'>)
is OSError subclass: False
is MemoryError subclass: False
```

And the Windows path raises in the parent, outside the child:

```
subprocess.py:857: raise ValueError("preexec_fn is not supported on Windows platforms")
ValueError: preexec_fn is not supported on Windows platforms
```

So the old `except (OSError, MemoryError)` caught neither the POSIX `SubprocessError`
nor the Windows `ValueError`. The commit's diagnosis of the escape is correct.

*The repair's shape.* `src/settlement/launcher_local.py:889` catches `Exception`,
appends a `dispatched: false` claim (`:920-923`), unwinds (`:924`), and returns
`sent=False` with `child-setup-failed`. `claimed()` at `:544-555` scans all lines for
the key and lets the **last** `dispatched` value win, so a retraction is honoured and a
later honest claim is not undone by an earlier retraction. That is the right rule for an
append-only ledger and it is documented in place.

*Test evidence.* `tests/test_launcher_local_preexec.py` — **5 passed, 6 skipped** on this
host. The six skips are honest and specific: four say "a preexec_fn failure needs a
POSIX fork", two say "RLIMIT_CPU is a POSIX enforcement mechanism". So the five that ran
are the platform-independent ones, and the central failure mode is **unverified on this
host**. That is disclosed by the skip reason, not hidden.

*Strongest counter-reading — and this is the one worth acting on.* The new branch catches
`Exception` around a `Popen` that may fail for reasons other than a `preexec_fn` raising:

- `FileNotFoundError` / `PermissionError` from a bad `argv` or `cwd`
- `OSError: [Errno 8] Exec format error` — the **exec itself** failed
- `NotADirectoryError` on the `cwd`

In the exec-failure case the code comments explicitly say "A child that raises in
`preexec_fn` has not exec'd, so no argv of this dispatch ever ran, and the launcher can
prove that instead of asserting it", and contrast that with "a spawn failure, where the
exec itself may be what failed, which is why the two get different reason prefixes". But
**one branch handles both**, and it returns `sent=False` for both. On CPython/Linux, a
`Popen` that fails to exec has already forked; the child exits without exec'ing, so
`sent=False` is defensible. The gap is that the *comment* claims a proof the *code* does
not establish per-case, and a reader of `child-setup-failed: [Errno 8] Exec format
error` is told "the boundary stopped the child" when the boundary was fine and the argv
was wrong. This is a labelling defect, not a correctness defect, and it is cheap to
close by branching on whether the exception is a `SubprocessError`.

I did not construct a case where this strands an operation. `BaseException` is correctly
excluded, so `KeyboardInterrupt` still propagates and the claim is correctly left
standing — that reasoning is sound and is written down.

### Claim 3 — `QUALITY = {"preserved": 1,...}` contaminated E2's primary statistic

**HOLDS, and the arithmetic is forced, not likely.**

*Evidence.* At the pre-fix commit `edee2b6`, `experiments/ad01/s09_e2_scored.py:75-80`
defines `QUALITY`, `:251` computes `quality = float(QUALITY[run["scored"]["verdict"]])`,
and `:271` computes `score=evidence["ratio"] + quality`. `MAX_SCORE = 2` at `:94`.

The proof that `verdict` is always `preserved` for anything reaching a Reading is
structural, not statistical:

- `experiments/representation/checkers.py:66-78` — `check_software` reaches
  `_witness_verdict` only after the candidate is a legal deletion, and
  `_witness_verdict` returns `PRESERVED` at `:88` or `NOT_PRESERVED` at `:83`/`:86`.
  So `not_preserved` is reachable *in principle*.
- `experiments/representation/reducers.py:27` only mutates `keep` on a
  `PRESERVED` verdict — this is the ledger's own citation and I confirmed it is the
  mechanism.
- Therefore the candidate handed to a Reading is either the incumbent (`ok-incumbent` →
  `PRESERVED`, `checkers.py:70`) or an already-accepted trial (`PRESERVED`).

So `quality ∈ {1.0, 0.0}` in general, and `= 1.0` for every candidate a Reading sees.
`score = evidence + quality` with `evidence ∈ {0.0, 1.0}` gives `score ∈ {1.0, 2.0}`.
`paired_report` at `experiments/ad01/e2_replication.py:1247+` subtracts one score from
another, so the contrast could only be `0.0` or `±1.0`, and `±1.0` would require one arm
to have a non-varying verdict. The recorded `deltas: [0, 0, 0]` was arithmetic.

*What the repair did.* `QUALITY` deleted, not renamed. The leg is now
`normalized_reduction` (`s09_e2_scored.py:632-651`), one function over one report dict
(`verdict`, `measure`, `initial_measure`, `reason`), read from a Reading via
`as_report()` (`:703-712`) and from an experience record via the same shape. The
measure is real: `experiments/representation/software.py:233` `measure(ops) = len(ops)`
and `graphs.py:143` `measure = len(vertices) + len(edges)`, so a reducer that removes
ops scores a positive fraction and one that returns its input scores 0.0.

*Test evidence.* `tests/test_s09_e2_benefit_leg.py` — **19 passed** on this host. The
commit records that 16 of them fail on `edee2b6`, including a red proof
(`assert [0.0, 0.0] == [0.5, 0.75]`). I did not re-run the baseline; I take the red
proof as recorded, and the 19 green results are my own.

*Soundness of the new estimator.* I checked this because it is the part that could have
been fixed badly. `paired_report` (`e2_replication.py:1276-1310`) computes
`deltas.append(_reduction_of(a) - _reduction_of(b))` and then passes them to
`learner_revision.paired(deltas, zeros)` with a **zero vector of the same length** as
the second arm. `paired` (`learner_revision.py:865`) then does `r - i` elementwise, so
the zeros are a no-op and the paired standard error is computed against zero. That is
correct and is the standard "difference from zero" form. `_reduction_of`
(`:1315-1326`) reads the recorded `normalized_reduction` key rather than recomputing,
and returns `0.0` for a record that lacks it — documented as "honest about there being
no measured reduction rather than about a zero reduction". That is a defensible choice
and it is stated.

*Strongest counter-reading.* The new leg is not free of the same class of defect it
replaced. `normalized_reduction` is `(initial - measure) / initial`, and both `initial`
and `measure` come from the **same checker** that decides `preserved`. So the leg is
still conditioned on the same fixpoint, just measured continuously instead of
categorically. The fix is real (it can now vary, and it can vary *legitimately*, because
a legal deletion that removes more ops scores higher without the oracle changing), but a
sceptic can say the leg is downstream of the same coupling. The batch does not claim
otherwise, and the structural argument for the fix is sound. I record it as the strongest
counter-reading, not as a defect.

*One documentation defect I found.* The module docstring at
`experiments/ad01/s09_e2_scored.py:17` still reads:

> "Two legs, each in [0, 1], summed into a score in [0, 2]"

and then enumerates **three** legs (1. Evidence, 2. Reduction, 3. Agreement) at
`:18-42`. The score is still `evidence + quality` at `:300` — two terms — so the range
statement is arithmetically right and the count is stale. `MAX_SCORE = 2` at `:95` is
consistent with the code. The docstring says "two" where the same docstring then lists
three. Cosmetic, but it is in the file a reader opens first to understand the metric
that was just repaired, and the repair's own commit message makes a point of the record
saying what it means. `principle-minimize-reader-load` applies.

### Claim 4 — E3's "2.7x" is a sum/mean denominator artifact; the crossover is 20 not 30

**HOLDS. Every number reproduces.**

*Numerator.* `experiments/ad01/agenda_policy.py:424-441` `_score_constant_rules` builds
`scores.append((sum(... for world in worlds), rule))`. It is a **sum** over worlds
`(0,1,2)`. Confirmed by reading the source.

*Denominator.* `experiments/ad01/s09_e3_selection.py:281`:
`"held_out_reduction_mean": sum(reductions) / len(reductions)`. A **mean**. Confirmed.

*The 2.7x.* `reports/evidence/inv_r1_e3_selection/e3-crossover.json`
`$.crossover.per_budget[1].agenda_held_out` reads `0.1568834941383961` at budget 20. I
recomputed:

```
0.419328 / 0.1568834941383961 = 2.6728624467663002   -> 2.7
0.419328 / 3                 = 0.13977599999999998
0.139776 / 0.083721          = 1.6695452753789373
0.139776 / 0.1568834941383961 = 0.8909541489221002   -> agenda ahead
```

All four figures in `reports/workstreams/w3-e3-recompute.md` §4 reproduce to the digit.
The report is unusually honest here: it publishes the *other* comparison
(oracle mean / agenda shared mean = 0.89x, agenda ahead) alongside the flattering one,
and states that the 2.7x mixes a shared-path denominator with a fresh-path numerator.

*The crossover.* From the recomputed table, best-in-space mean by budget is
0.000000 / 0.000000 / 0.139776 / 0.175257 / 0.359281 / 0.414277 at 8/14/20/30/40/60, and
the agenda's fresh mean is 0.000000 / 0.083721 / 0.083721 / 0.111748 / 0.144745 /
0.205876. The first budget at which the agenda is below the oracle is **20**. Confirmed.
The report's explanation of where "30" came from — reading the *default's* crossover
(agenda beats default at 14/20/30, loses at 40/60) as the oracle's — is a plausible
reconstruction, offered as such ("most likely came from"), and I did not disprove it.

*Strongest counter-reading.* The corrected 1.67x is itself fragile, and the report says
so less loudly than it should. The budget-20 row is a **tie-shaped degeneracy**: the
agenda scores `0.083721` at budget 14 and the *identical* `0.083721` at budget 20, with
identical resources (42), choices (6), diagnoses (0) and retained (3). The agenda spent
78 more resources at 20 than at 14 and bought nothing. A "margin" computed at a budget
where one arm is flat and the other jumps is a margin at an artifact of the budget
schedule. The report does flag the 30-cell reversal explicitly (world 2 carries the
pooled sign) but does not flag that 20 is the same shape of problem. A sceptic would say
the crossover correction from 30 to 20 is directionally right and lands on a soft cell.

*Second counter-reading, on the recomputation itself.* The report says its run is
"1176 runs per budget, 368.4 s total" and "No value read off any prose", and states the
counts column "matches the committed table in `reports/STAGE-09-HANDOVER.md:157-158` at
every budget". I did not re-run the 1176 runs. I confirmed the *arithmetic* and the
*source mechanism*. Whether the ladder numbers themselves reproduce is **undetermined**
from what I ran; it rests on the lane's recorded run and its agreement with a committed
table.

### Claim 5 — E4's blocker is the revision boundary: reachable range `0.00622` against `0.0587`–`0.5017`

**HOLDS on the direction. The 0.00622 figure is OVERSTATED as a "reachable range", and
the 70x ratio built on it inherits that.**

*What holds.* `reports/evidence/inv_r1_e4/result.json`:
- `$.ceiling`: `delta: 0.006222222222222222`, `n: 75`, `paired_se: 0.004385985912880197`,
  `z: 1.4186598739292808`, `best_input: 7`, `best_mean: 0.072`, `worst_input: 15`,
  `worst_mean: 0.065778`.
- `$.evidence_ceiling`: `reducer_mean: 0.5016666666666667`,
  `incumbent_mean: 0.05866666666666667`, `paired.delta: 0.443`, `z: 17.425849095344606`,
  `n_seeds: 150`, `decision: "evidence-set-selection"`.
- `$.intervention_boundary`: `improve_channel.STEP.frontier_action.probe.inputs.x`,
  `improve_channel.py:172`.

*The menu is genuinely two elements.* `improve_channel.py:136` `_STRATEGY_SOURCE =
{"low": IMPROVE_LOW_SOURCE, "high": IMPROVE_HIGH_SOURCE}`, and `REACHABLE_EVIDENCE`
at `:489` is derived from it. `headroom.json` records `reachable_evidence: ["3","11"]`.
Confirmed by reading the source. A revision selects a menu entry; it cannot widen the
menu. The claim "a revision is a selector over a two-element set" is exactly right.

*Where it is overstated.* `$.ceiling.delta` is a **max minus min over 16 single-probe
inputs, selected on the same data**. I read the full distribution from
`reports/evidence/inv_r1_e4/headroom.json` `$.ceiling.input_means`:

```
x=0  0.059733   x=4  0.059467   x=8  0.060267   x=12 0.060933
x=1  0.059200   x=5  0.059689   x=9  0.060400   x=13 0.061511
x=2  0.059422   x=6  0.059556   x=10 0.060000   x=14 0.060800
x=3  0.060222   x=7  0.059333   x=11 0.058844   x=15 0.061022
```

Every one of the 16 means lies in `[0.058844, 0.061511]`. The reported spread of
`0.00622` is computed from *different* numbers (`0.072` and `0.0658`) than the
`input_means` in the same file, so `$.ceiling` in `result.json` and `$.ceiling` in
`headroom.json` are **not the same measurement** despite sharing a key name. The
`headroom.json` spread across its own 16 inputs is `0.061511 - 0.058844 = 0.002667`,
and the standard deviation across the 16 means is `0.000729`. Both are *smaller* than
0.00622.

So 0.00622 is a **selection-biased upper bound** — the best of 16 chosen on the same 75
tasks, then re-scored on the same 75. Its own `z` of 1.42 says it is not distinguishable
from zero. `improve_channel.py:743` even carries a `selection_biased` field, set to
`False`, and the docstring at `:735-741` explains why a "must beat the menu" condition
was dropped.

*Does this weaken the claim?* Not the conclusion. The conclusion is "the boundary cannot
express the headroom", and that is supported by something stronger and simpler: the menu
has two members, the two members' inputs are 3 and 11, and both sit inside a
0.0027-wide band of means. Even a *perfect* selection within the full 16-input substrate
moves a descendant by at most a few thousandths, against a `0.443` headroom. The
conclusion survives; the specific number and the "70x" ratio are soft.

*Where the matrix leans on it.*
`reports/STAGE-09-COMPLETION-MATRIX.md:225` calls the 0.5017-vs-0.00622 contrast "the
most decision-relevant number in the batch". `:316` says "The 0.5017-versus-0.00622 gap
is what makes it the highest-value move available." A reader taking 0.00622 at face value
overstates the boundary's weakness by roughly 2.3x (0.00622 vs 0.00267 on the same
file's own inputs). The direction of the recommendation is unchanged and I would not
block on it, but the number should be labelled as a selected upper bound with `z = 1.42`
beside it, or replaced with the unselected spread. This is the one place in the batch
where a headline number carries more weight than its evidence supports.

*Strongest counter-reading to the claim itself.* "The blocker is the boundary, not the
substrate and not the prompt" is asserted; the *evidence* is that six dispatches were
refused. All six produced `x = len(view["experience"])` or `% 16` variants, which
evaluate to `0` on the spending step, and `0` is the frozen reducer's own top pick. But
`0`'s mean is `0.059733` in the table above and the incumbent's is `0.060222` — the
model's answer was *worse* than the incumbent but within the same band. So the six
refusals are consistent with a model that has no better answer to give **on this
interface**, which is the claim, and equally consistent with a model that would have
found `x = 13` (`0.061511`, the best of 16) had it been asked differently. The batch
cannot distinguish these, and the matrix's own counter-reading paragraph concedes as
much. Fine.

### Claim 6 — free-signal split-brain, route-comparison split-brain, and the guard were one defect at three layers

**HOLDS as a diagnosis, and it is the batch's strongest piece of reasoning.** I checked
each layer.

*Layer 1, the free signal.* `2fab0df` deleted `_free_tier` and introduced one
`_free_signal` (`gateway_http.py:338`) called by both halves. The docstring at `:360-367`
explains why `usage.cost` is deliberately **not** a channel, and the reasoning is right:
it cannot refuse before the spend, and no catalog entry carries one, so admitting on it
would make the halves disagree in the other direction. Absence is still a refusal
(`:369-371`). The old incoherence — refusing a lone `tier: "free"` for want of
corroboration while accepting a bare `:free` id with nothing — is fixed at `:379-380`.

*Layer 2, the route comparison.* `3721cd6` introduced `route_matches` at
`gateway_http.py:180` as the one comparison, and made the guard's table
(`live_construct.py` `_RETURNED_ROUTE_FIELDS`) a join rather than a rule. The failure it
fixed is documented concretely: `_route_value_matches` case-folds `provider`, so the
adapter accepted `provider: "Nvidia"` against a frozen `"nvidia"`, and `LiveGuard.
_route_failure` then compared the same four values with raw dict equality and refused
what the adapter had just admitted. Verified: `tests/test_w1_guard_route_owner.py` —
**11 passed** on this host.

*Layer 3, the same shape.* This is the part that makes it one defect rather than three:
each layer was a *second derivation of a fact another layer already owned*, and each
repaired exactly one layer while the derivation split survived one level down. The
commit messages say this in their own words — "This is the same split-brain the
free-signal repair fixed one layer up. That repair unified the derivation and left the
comparison split, so the failure stayed reachable by a second reader."
(`3721cd6`).

*Strongest counter-reading.* The pattern is real but it is a pattern in **this
codebase's route handling specifically**, and naming it "one defect at three layers"
risks freezing the lesson as "route fields are dangerous" rather than the sharper and
more transferable one: *a comparison table that governs how two fields are compared is
not sufficient if the set of fields, or their derivation, is decided elsewhere.* The
`provider` fix (case-folding, in the comparison) and the `tier` fix (derivation) were
both real and neither would have been found by auditing the other layer. The lesson is
"audit both the comparison and the derivation of every cross-boundary field", not
"there were three of the same bug". The matrix gets this right at `:284` ("one owner for
a route field, after three separate repairs failed on the same premise") but the ledger's
"one derivation" framing is narrower. Minor.

### Claim 7 — E1 r2's zero is the model's, not the harness's: 6 of 6 over-length at 2048 tokens against a 512-character limit

**HOLDS on the facts. It is OVERSTATED as a statement about the model.**

*Facts, all verified against the artifacts.* I extracted from
`reports/evidence/w1-e1-boolean-r2/campaign.json` `$.cells[*].verdicts[*]`: six
`invalid-program` with `stop_reason: 'length'`, `usage.output_tokens: 2048`,
`provider: 'Nvidia'`, `tier: 'free'`; two `transport-loss` with `response_status: 502`.
The per-lineage `raw_response` lengths are 5211, 5092, 6590, 5185, 7314, 5323 — 10x to
14x the frozen 512, every one cut mid-sentence. `experiments/ad01/live_construct.py:44-45`
pins `max_response_characters: 512` and `max_output_tokens: 2048`. The dispatch record
carries `requested_output_cap: 2048`. All confirmed.

*The harness is exonerated on the specific charge.* The route repair held: every answered
dispatch carries `provider: "Nvidia"` against a frozen `provider: "nvidia"`,
`route_error: None`. That is the exact contradiction that refused a correct answer in r1,
and it is gone. The 502s are kept distinct from the refusals. Both are right.

*Where it is overstated.* "This time the zero is about the model" and "The finding is a
budget-behaviour finding, not a competence finding" (`RESULTS.md:74`) both read as
"the model could have done it and chose not to". The evidence does not support that. What
the artifacts show is:

- The prompt is 982 characters of dense JSON followed by one sentence of instruction.
- The task gives 8 observations of a 4-bit input and a 4-bit output, over a class of 224
  affine-plus-one-pair hypotheses, and asks for 4 specs.
- The model restates the problem, enumerates the observed points, and reasons. It never
  reaches the object.

A conforming answer is **143 characters** (I measured a well-formed one). So the 512 limit
is not the binding constraint on the *answer*; it is generous by 3.6x. The binding
constraint is the model's willingness to emit the object before reasoning, and *whether
it can do that under any protocol is exactly what six truncated replies cannot tell you*.
A model that reasons before answering would fail this prompt at 4096 tokens too, with a
larger body of prose. The result is a real protocol finding — this model, this prompt,
this budget — and it is not a competence finding either way. `RESULTS.md:78` gets close
("Nothing here shows it cannot state the rule; it shows that under this protocol it does
not") and that is the right sentence. The stronger framing at `:11` ("this time the zero
is about the model") carries more weight than the evidence supports, and it is the framing
the ledger at `reports/PROJECT-LEDGER.md:38` propagated ("The binding constraint is the
model's budget behaviour against the protocol").

*Strongest counter-reading, which is partly mine and partly the batch's.* The word
"model's" is doing work it has not earned. The defect the batch is best at finding is
duplicated derivations of the same fact. Here there is one: the protocol specifies a
512-character answer and a 2048-token budget and does not say what to do when the model
fills the budget. `automatic_retries: 0` and `repairs_planned: 0`
(`campaign.json` `$.planned`) mean the campaign had no second attempt, so a single
budget-exhausting reply ends the lineage. The `attempt` field supports `attempt in (1, 2)`
(`live_construct.py:117-118`) and the prompt says "Attempt 1 of 2", so the protocol
contemplated a second try and the freeze spent none of it. Whether a model that read
"attempt 1 of 2" and then reasoned for 2048 tokens would emit the object on attempt 2 is
unknown and cheap to test. **This is the single most decision-relevant gap in the E1 r2
result, and the batch did not name it.** I am not asserting the retry would have worked.
I am asserting that a negative with an untried in-protocol second attempt is not the
model's verdict, it is the protocol's.

---

## 2. Defects the batch introduced and did not notice

### 2.1 The handback document is factually wrong about the batch it summarises — **highest priority**

`reports/STAGE-09-COMPLETION-MATRIX.md` is the W5 handback and the most-read artifact in
the batch. It is the artifact the batch itself flags as most likely to be read, and it
makes a claim that the batch's own tip commit falsifies.

At line 44, §0:

> **There is no E1 r2.** The brief states "r2 runs on a repaired path". No r2 directory
> exists in any branch, any worktree, or any commit reachable from `--all`
> (`git grep 'boolean-r2' $(git rev-list --all)` returns nothing).

At the tip `97b320a`, which is the commit that **added** r2:

```
$ git ls-tree -r --name-only 97b320a | grep -c "w1-e1-boolean-r2"
13
$ git ls-tree -r --name-only 19fbe69 | grep -c "w1-e1-boolean-r2"
0
```

The matrix was written at `19fbe69` (its own header says so), when the claim was true.
`97b320a` then added thirteen r2 files and did **not** update the matrix. The same stale
claim propagates into three more places:

- `:86` §2 table, "E1 r2 on the repaired path | **NO ARTIFACT**"
- `:251` §4, bottleneck **B2**, "A live construction has never been recorded on the
  repaired path" — with a cost-to-fix that is now done
- `:262`, "The gap is one short live run, and it should be closed before any further E1
  cell is built"

And the E1 row in the §1 matrix still reads `attempted, then specifically blocked`,
`Zero constructions. 6 route-refusal, 2 transport-loss`, when the current evidence is
`0 constructions. 6 invalid-program (over-length), 2 transport-loss`, on a repaired path.

This is the exact failure the batch was formed to prevent, and it is worse than the
stale-ledger problem the batch fixed in `86786cf`, because the ledger is the working
document and the matrix is the handback. §0's third paragraph names it as "the single
largest gap between what was reported to the coordinator and what is on disk" — and then
becomes that gap itself, in the same commit that closed it.

The r2 result *is* correctly reported in `reports/PROJECT-LEDGER.md:38, 53` and in
`reports/evidence/w1-e1-boolean-r2/RESULTS.md`. So the knowledge exists; it did not
reach the handback. `AGENTS.md` says the ledger and roadmap own current status, and
`86786cf` brought both into agreement — but `AGENTS.md` also says the matrix is the
W5 deliverable, and the matrix is the one document now behind.

### 2.2 The offline verifier does not recompute the field every reported number rests on

I ran the shipped verifier against three successively deeper forgeries of
`reports/evidence/w1-e1-boolean-r2/`. Each was caught, and the depth is genuinely good:

| Tamper | Caught by | Error |
|---|---|---|
| 1. Replace the response with a valid object, set `verdict.outcome: constructed` | `frontier.py:329` | `evidence record raw payload digest mismatch` |
| 2. Tamper 1 plus recompute `raw_payload_digest` and `response_digest` | `frontier.py:335` | `evidence record identity digest mismatch` |
| 3. Tamper 2 plus recompute `evidence_digest` via `_evidence_identity_digest` | `live_construct.py:1641` | `preflight response does not match its own dispatch evidence` |
| 4. Tamper 3, setting **both** `raw_response` copies and the candidate digest | `live_construct.py:1662` | `preflight recorded an invalid program that parses` |

The chain is real and every step is a genuine check, not a signature over a file the
verifier also wrote. Baseline: 8 checked, 8 passed, `network_withdrawn: true`, verified
by me. That is a good verifier.

**But I then built a self-consistent forgery the verifier accepts.** I replaced a
lineage's 5211-character response with a 144-character well-formed object that **fails
schema validation** (`"mask": 99`), set `parse_outcome: "parse-failed"`, and recomputed
`raw_payload_digest`, `response_digest` and `evidence_digest` to match:

```
dispatch record validates
verdict recompute: invalid-program
```

The verifier returned a clean pass, because `verify_preflight_record`
(`live_construct.py:1652-1663`) treats an `invalid-program` as attested by a
**disjunction**: either the bytes do not match the dispatch, or they do not parse. My
bytes did not parse, so the disjunction held, and the whole forgery validated.

The specific thing that survives: **the recorded `reason` is never recomputed.** The
lineage's `attempts[0].reason` reads

```
response of 5211 characters exceeds the frozen limit of 512
```

while `attempts[0].raw_response` is 144 characters. The 512-character limit is the frozen
constant the entire E1 r2 finding rests on, and the verifier does not check that the
recorded length claim matches the recorded bytes. `w1_e1_campaign_r2.py:928-938` has a
`_defect_of` helper that *would* derive the defect from the raw response "because the
length is a fact about the bytes and the reason is prose about them" — and
`verify()` does not call it.

**What this means for the handback.** It is not that r2 is false. The eight records are
self-consistent, the digests match, and the raw responses are all present and all
genuinely over-length — I checked all six independently (5092 to 7314 chars, every one
mid-sentence). The finding stands. But the offline-verification story is **thinner than
"the verdict recomputes"**: it recomputes the *taxonomy outcome* and the *digest chain*,
and it does not recompute the *reason*, the *defect classification*, or the *512 limit*
that the report's headline finding names. A record claiming a 5211-character over-length
response, holding a 144-character one, verifies clean. `WORKER-PROMPT.md:100` asks to
"Export enough raw construction, execution and receipt evidence to recompute verdicts
offline"; that is met for the verdict and not met for the reason. §W5's own tamper
requirement (`:99-100`) is met for the E1 r2 verifier, because each of my four tampers
did produce an added failure — but the surviving forgery is a fifth case the requirement
does not cover, and it is the one that would matter if someone wanted a record to read
better than it is.

### 2.3 A real, pre-existing Windows defect that breaks the M4 tamper baseline on this host

`scripts/invl02_live.py:1262-1263` in `_write_output_bundle`:

```python
temporary.replace(path)
directory = os.open(out, os.O_RDONLY)
try:
    os.fsync(directory)
```

Opening a directory with `os.open(..., O_RDONLY)` **fails on Windows**. Reproduced:

```
O_RDONLY on dir FAILS: PermissionError [Errno 13] Permission denied
```

Consequently `tests/test_m4_offline_recompute.py` — the file behind
`reports/evidence/inv_r1_m4_baseline/tamper-results.json`, the artifact §W5's
"clean verifier baseline and each intended tamper produces an added failure" clause
rests on — reports **12 failed, 33 passed** on this host, and I confirmed all 12
`PermissionError`s are this line. Six of the twelve are the tamper-detection tests
themselves, including `test_observed_response_tampering_still_fails_route_and_digest` and
`test_unresolved_receipt_without_lost_marker_still_fails`.

**Why this matters for the handback specifically.** `WORKER-PROMPT.md:99-100` requires
demonstrating a clean verifier baseline and that each tamper adds a failure. The
committed `tamper-results.json` records `baseline_status: "pass"`, `all_fired: true`,
`required_examples: 7`, `live_dispatches: 0` at `source_tip 4a931a9`. That artifact is
**pre-batch** (2026-09-28; `git merge-base --is-ancestor f668656 09b1f2e` confirms the
tamper baseline is not stale relative to its test). It was produced on a host where
directory fsync works. So the claim is not wrong, but **it is not demonstrated on this
host**, and the batch's §2 table lists "verifier baseline" as NOT DISCHARGED without
naming the concrete reason. Anyone who tries to discharge it here will hit 12 failures
that have nothing to do with the verifier's logic and everything to do with a one-line
platform bug. The fix belongs to whoever owns `scripts/invl02_live.py`; it is not mine
and I have not touched it.

### 2.4 Claim 1 is attributed to the wrong batch

Covered in §1.1. Stating it here because it is the same class of error as the "2
attempts pending" retraction in `86786cf`: a fact carried into a brief without checking
its provenance. `655feb3` is 11 commits before `edee2b6` and 5h38m earlier in the day.
The batch fixed one instance of this and introduced another in the same commit range.

### 2.5 Two commit pairs in the batch are the same change twice

`db44622` / `ec89dcd` (preexec unwind) and `2fab0df` / `4e1ed25` (free signal) are each a
worktree commit and its merge. `19fbe69` and `52d398d` are the same pattern for the host
unification. This is the documented workflow, not a defect. I note it only because
`git log --oneline -30` shows 6 of the last 12 lines as pairs, which makes the range read
as 21 changes when it is 15. Nothing to fix.

---

## 3. Does the completion matrix overstate anything?

Yes, in four places, and one of them is disqualifying for a handback.

**3.1 It asserts the absence of r2, at the tip commit that added r2.** §2.1 above. This
is not an overstatement of a number; it is a false statement about the repository, in
the document whose reading rule is "A row is `completed` only where a named artifact
carries the claim and the artifact was read here." By its own rule the E1 row cannot be
`attempted, then specifically blocked` with `6 route-refusal`, because the artifact that
carries the current claim is in the same commit and was not read.

**3.2 Bottleneck B2 is already closed and is still the top-recommended cheap fix.**
`:251-264`. "Cost to fix: One campaign at the already-frozen 8-attempt ceiling, 16 model
calls, no new cap sheet needed. Cheapest item in this document." That campaign ran. It
is `97b320a`. The cost-to-fix has been spent and the finding has moved (from a route
refusal to a model budget-behaviour finding). A reader prioritising from this document
would re-run work that is done.

**3.3 The E4 0.00622 figure carries more weight than its evidence supports.** `:225`
calls the 0.5017-vs-0.00622 contrast "the most decision-relevant number in the batch";
`:271` and `:316` rest on it. §1.5 above: 0.00622 is a selected upper bound (best of 16
inputs chosen on the same 75 tasks) with `z = 1.42`, and the same file's own
`input_means` span 0.00267. The recommendation is right; the multiplier is soft.

**3.4 §3.1 attributes E1 r1's `verification.passed: 8` to a mechanism claim it cannot
support on its own.** `:106-110`: "A model-authored executable program can be dispatched
... **E1 r1 does this eight times with `verification.passed: 8`**". r1 produced **zero
programs** (`6 route-refusal, 2 transport-loss`, per the same document's own §1 row). So
the "mechanism works" evidence is eight dispatches that never reached a program, and the
document's own counter-reading paragraph at `:118-124` says exactly this. It is
disclosed. But `:106` leads with it as support, and the sentence immediately after — "E4
does it six times and classifies all six as `model-acquired`" — is the load-bearing half.
The row would be stronger if it led with E4 and used r1 as the *negative* control that
proves the harness detects a failed construction. As written, a reader skimming §3.1 takes
away "the mechanism is proven eight times over" from eight lineages with no programs in
them.

**What the matrix gets right, and it is a lot.** I looked for overstatement because I
expected to find it and I want to be explicit that most of this document is unusually
disciplined:

- §0 is three premise corrections, one of which (the E1 r1 count) catches the brief
  collapsing `route-refusal or transport-loss` into "all route-refusal".
- §2 has an eight-row "NOT PROVEN" table that includes the batch's own live
  construction gap and its own unrun study, and an "Undetermined, and I could not
  determine it from records" paragraph with four named unknowns.
- §3.3's counter-reading on E2 ("a statistic that was a fixpoint could not have found a
  difference. Recording that is not softening the negative; it is the reason the
  negative cannot be cited") is the right epistemics.
- §6 records the full-suite breaches, the unscoped `pkill`, the broken venv and the two
  lanes that wrote into the coordinator's checkout, unprompted, in the handback. That is
  the opposite of self-serving and it is why I could find the rest of what I found.
- The "**A fourth candidate I am not listing**" paragraph at `:299-302`, refusing to
  list the missing Linux host because it is a deployment fact and not a research
  bottleneck, is a real editorial decision and the right one.

No other row overstates. W0, W2, W3, E2, E3 and E4 rows all name what is not established
in the same row as what is.

---

## 4. Is the tamper / offline-verification story sound, or thinner than claimed?

**Thinner than claimed, in one specific and one general way.** The E1 r2 verifier is
genuinely good and I could not get past it four times (§2.2). The general gap and the
specific gap are different.

**The general gap.** The verifier proves a record is *internally consistent* and that its
*taxonomy outcome* follows from its bytes. It does not prove the record describes a
dispatch that happened. Nothing can, offline — there is no signature over the gateway
call — but the documents should say so plainly, because "re-verified offline with the
network withdrawn" reads to a non-specialist as "proved". The right phrasing is
"recomputed from its own recorded bytes with the network withdrawn, so a swapped response
or a hand-written verdict is caught; a record whose *entire* dispatch block was fabricated
coherently is not distinguishable from one that ran."

**The specific gap** is the `reason` string (§2.2). Six of the eight r2 lineages carry
`reason: "response of N characters exceeds the frozen limit of 512"`. That string is the
finding. The verifier never recomputes it, and I demonstrated a record that says
"5211 characters exceeds the frozen limit of 512" while holding 144 characters, and that
verifies clean. The fix is one line in `verify()`: call the `_defect_of` helper that
already exists at `w1_e1_campaign_r2.py:928` and assert the recorded reason agrees.
I am not applying it; that is the coordinator's.

**W5's tamper clause is not discharged and the matrix says so.** `:62` and `:87` both
mark it NOT DISCHARGED, and §2.2 above gives the concrete reason nobody wrote down (the
Windows directory-fsync bug). That is honest. It is also the reason the clause is still
open: the baseline artifact is from a POSIX host and cannot be re-demonstrated here
without a repair that is out of this batch's scope.

**What I could not check.** I did not run `tests/test_gateway_free_signal.py` or
`tests/test_s09_swe_executor_capability.py`, so the free-signal and SWE-executor test
suites are unverified by me. The free-signal repair I assessed by reading
`gateway_http.py:338-400` and by the E1 r2 route fields in the artifacts, which is
stronger than a test result for the specific claim (the repair held on the live path)
and weaker for the general claim (the three-channel rule's edge cases).

---

## 5. Undetermined

Stated as such, not as findings.

1. **Whether E3's ladder numbers reproduce.** §1.4. I verified the sum/mean mechanism in
   source and all four derived ratios, and the report's counts column matches
   `STAGE-09-HANDOVER.md:157-158` as claimed. I did not re-run 1176 simulations per
   budget. The 368.4 s the lane recorded is plausible for that volume but I did not
   reproduce it.
2. **Whether the E4 `result.json` `$.ceiling` and `headroom.json` `$.ceiling` are meant
   to be the same measurement.** They share a key name and disagree (`0.072`/`0.0658`
   vs a 16-input spread of `0.00267`). One may be a different split. If so, the handback
   cites the wrong one. If not, one is mislabelled. I could not determine which from the
   artifacts, and both are plausible.
3. **Whether `tests/test_gateway_free_signal.py` and
   `tests/test_s09_swe_executor_capability.py` pass.** Not run. Test budget was three
   files; I spent it on the E2 leg, the preexec branch and the guard route owner, plus
   the M4 file for §2.3.
4. **Whether a second E1 attempt would have produced a construction.** §1.7. The
   protocol supports `attempt in (1, 2)`; the freeze spent `repairs_planned: 0`. Not
   tested, and I am not asserting the answer.
5. **The `pkill` blast radius.** The batch discloses it. I cannot determine from here
   whether another agent's processes were actually killed, or whether they would have
   mattered.
6. **Whether the `uv sync` venv break lost anything.** I am running on a working venv;
   the incident is disclosed in two places. No artifact shows a lost write.
7. **Whether `2` unstashed entries matter.** `git stash list` shows `cmp2` and
   `w1-route-refreeze-tmp` on this branch. I did not open either. They may be
   disposable or may hold unmerged work. Not my call and not my files.

---

## 6. What I did not find

Stated explicitly, because a clean review is a result and the instruction was not to
manufacture one.

- **The seven claims are substantively correct.** Six hold outright. The seventh
  (`"the zero is the model's"`) holds on the facts and is overstated on the inference;
  the E4 figure holds on the conclusion and is overstated on the number. I found no
  claim that is simply wrong.
- **The reasoning in the code comments is unusually good and I could not falsify it.**
  The `preexec_fn` branch's `Exception`-not-`BaseException` reasoning, `_free_signal`'s
  exclusion of `usage.cost`, `child_setup_refusal`'s refusal to ask by acting, and
  `paired_report`'s decision to report the decision vector per task rather than average
  it are all correct and all explain *why* in a way that survives my reading.
- **No dead imports, no orphaned branches, no `os.name` predicate left behind.** The
  commit deleted `child_limits_unsupported_reason` rather than leaving it beside the new
  authority, and `child_limits.py:1-52` is a single coherent statement of the host's
  capability. I checked for a second platform predicate and found one owner.
- **The tamper coverage is real, not decorative.** Four escalating forgeries, four
  distinct checks, four distinct errors. This is above-average evidence discipline and it
  is the batch's best engineering.
- **The r2 result is not wrong.** Every raw response is present, every one is genuinely
  over-length and genuinely truncated, every route field is as recorded, and the two
  502s are correctly kept distinct from the six refusals. My §2.2 finding is about what
  the verifier proves, not about what happened.
- **The matrix's "NOT PROVEN" table and §6 self-disclosure are the strongest part of the
  handback** and I could not find them overstating anything.

---

## 7. Summary for the coordinator

**Fix before this document is handed on:**

1. `reports/STAGE-09-COMPLETION-MATRIX.md` §0, §1 E1 row, §2 table, §4 B2 — the matrix
   asserts r2 does not exist at the commit that created it. Thirteen files, four
   locations. This is the most-read artifact in the batch and it is wrong about the
   batch. Everything else in this review is smaller than this.
2. `experiments/ad01/s09_e2_scored.py:17` — "Two legs" where the same docstring then
   lists three. One word.
3. `reports/STAGE-09-COMPLETION-MATRIX.md:225, 271, 316` — label 0.00622 as a selected
   upper bound with `z = 1.42`, or use the same file's own 0.00267 spread. The
   recommendation is unaffected; the 70x is not.
4. The brief's attribution of the `prctl` fix to this batch (`655feb3`, pre-`edee2b6`).

**Consider, not urgent:**

5. `w1_e1_campaign_r2.verify()` does not recompute the `reason` / defect classification,
   and a self-consistent forgery carrying a false length claim verifies clean (§2.2).
6. `scripts/invl02_live.py:1262` cannot run on Windows, which is why
   `tests/test_m4_offline_recompute.py` reports 12 failures here and why W5's verifier-
   baseline clause cannot be discharged on this host (§2.3).
7. The E1 r2 finding should be re-framed as a protocol finding, and the untried in-
   protocol second attempt (`attempt: 2`, `repairs_planned: 0`) named as the cheapest next
   measurement (§1.7).
8. `launcher_local.py:889` catches `Exception` around `Popen`, which also covers exec
   failures that are not `preexec_fn` failures, and labels them `child-setup-failed` with
   a comment claiming a proof that only holds for the `SubprocessError` case.

**Not blocking, for the record:** the seven claims are sound. The batch found real
defects, repaired them at the right layer, deleted rather than deprecated, and disclosed
its own process failures unprompted. My findings are about overstatement in a handback
document and one verification gap, not about the repairs.
