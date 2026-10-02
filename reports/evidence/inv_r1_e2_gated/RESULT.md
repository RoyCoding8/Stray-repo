# E2, stopped at the gate

`experience_varies` refuses. The relevant arm's experience is a constant:
three observations, one distinct verdict, `['preserved']`. E2's core contrast
is "relevant experience versus no experience", and the relevant arm carries
nothing for a policy to be relevant to.

Nothing was dispatched. `live_dispatches: 0`, no database was created, no
gateway call was made, and the API key was never read into a process. The
result is a refusal, produced by the gate that exists to catch exactly this,
before the budget was spent rediscovering it.

Regenerate with:

    .venv/bin/python -m experiments.ad01.e2_gate_report

## The three gates

Run first, before anything else, per the lane's instruction.

| Gate | Result | Refusal |
|---|---|---|
| `experience_varies` (relevant) | **refused** | 3 observations, 1 distinct verdict `['preserved']`, minimum 2 |
| `experience_varies` (irrelevant) | **refused** | 3 observations, 1 distinct verdict `['preserved']`, minimum 2 |
| `control_distinct` (relevant vs none) | **refused** | 3 task(s) named no executed policy |
| `control_distinct` (relevant vs irrelevant) | **refused** | 3 task(s) named no executed policy |
| `menu_answers_nothing` | **pass** | open: true, no callable defaults a `method` |

Two gates refuse for two different reasons, and they are not the same defect.

**`experience_varies` refuses because the world is saturated.** The authored
reducers solve every task the arms draw experience from, so the checker
grades all of them `preserved` and the arm's experience is one bit. This is a
property of the seeded reducers on this panel, not of the prompt. Sweeping
every split of all three frozen worlds at four budgets
(`reachable_verdicts`, 216 task-budget pairs) returns:

    verdicts: {"preserved": 216}
    reasons:  {"ok-preserved": 120, "ok-incumbent": 96}

The `verdict` is constant everywhere. The `reason` is not: at `max_queries: 1`
every task grades `ok-incumbent` (the reducer returned the task unchanged) and
by `max_queries: 64` every task grades `ok-preserved`. The reducer's behaviour
does vary with the budget. The experience does not carry that variation,
because the prompt renders `verdict` alone and `reason` is not rendered. The
information the policy would need to tell those two situations apart exists in
the record and is not shown to it.

This is the constant the gate was written to catch, and it is not fixable by
choosing different source tasks. Every task in the world grades `preserved`.

**`control_distinct` refuses because the record names nothing.** E2 is a
construction arm. `e2_replication` writes an `operation_id`, a
`response_digest` and a `prompt_chars`, and never an executed policy id. The
gate does not credit a record with a policy it did not name, so it refuses
rather than infer one. This is the E1 defect one namespace up: nobody wrote
down what ran.

## The echo test

The brief asks whether the policy's output changes when the evidence changes,
or only when the task label does. On this panel the answer is that neither is
observable, and the substitution contrast is what shows it.

Substituting the alternate view's verdicts *does* change the prompt. The
scored prompt is 1663 characters and the substituted one is 1675, differing by
the verdict tokens alone:

    - "verdict":"preserved"   (x3)
    + "verdict":"not_preserved" (x3)

So the apparatus can substitute. It cannot distinguish, because the three
policies that matter write the same string:

    reader  inputs["read_verdicts"] = "preserved,preserved,preserved"
    echoer  inputs["read_verdicts"] = "preserved,preserved,preserved"
    ignorer inputs["read_verdicts"] = "preserved,preserved,preserved"

`reader_equals_echoer: true`, `reader_equals_ignorer: true`,
`echo_excluded: false`. The `relevant-echoes` cell in
`inv_r1_e2_replica/report.json:707` scored 2.0 against the reference reader's
2.0 precisely because an echo earns the evidence leg here by copying a
constant. That run read the block as learning. It is the same string three
times, and this run confirms the confound was never excluded.

`169c341` already recorded this for the other contrasts ("the apparent
family-drag was the diagnostic field echoing its input"). This run does not
repeat it against live dispatches. It shows the confound is structural to an
experience of one verdict, which is the condition `experience_varies` refuses.

## Transfer is scored, and the gaps doc is wrong

`reports/evidence/inv_r1_e2_scored/transfer.json` carries `"scored": true`
twice, on both the `adapted` and `target_only` arms, with
`agreement: "pass"`, `score: 1.0` and `selected: "seed-gr-ddmin"` on each.
Zero occurrences of `scored: false`.

The file was created by `169c341`, whose commit message states it "overturns
my earlier negative". `git log --follow` shows that commit as the file's only
entry, so the scored version has never been contradicted.

`reports/STAGE-09-MILESTONE-GAPS.md:16` and `:132` still record transfer as
`scored: false, agreement: "absent", selected: ""`. That document's only
commit, `1f592d9`, is dated 2026-09-28, a day *after* `169c341`. The stale
claim is therefore not a pre-existing note that the re-run failed to update. It
is a newer document asserting a state the file contradicts, and it will keep
propagating until it is corrected. This is a documentation defect, not a
measurement defect, and it is left in place: correcting a shared gaps document
is outside this lane's file ownership.

## The fresh freeze

Frozen before the gates ran, and intact under `verify_freeze`:

    freeze_digest  27ba14c9cf69bdeb864e4f1f32aad89ae35ef5e07e34ac05076b97a19f2395bb
    intact         true
    supersedes     inv_r1_e2_replica

The digest equals the replica's, because the contrast block is unchanged. The
cohort, arms, source, filler and target task ids and the estimator are the
same contrast. What supersedes it is the gate verdict, not the panel: the
replica's arms were frozen under a harness whose records cannot name an
executed policy, and a freeze that does not name what ran is not a frozen
contrast. This namespace records the refusal against the same digest rather
than editing the contrast to look different.

## What E2 can and cannot claim

**Cannot claim.** E2 has no result this run. The relevant / none / irrelevant
contrast was not measured, because the relevant arm carries an experience with
one distinct verdict and the gate refuses it. No dispatch was spent.

**Can claim, from measurement.**

1. The experience is a constant, and the world is why. Across 216 task-budget
   pairs over three worlds and four budgets the authored reducers grade
   `preserved` every time. The reducer's *reason* varies with budget
   (`ok-incumbent` to `ok-preserved`) and the *verdict* does not, so no choice
   of source tasks fixes this.
2. The echo confound is not excluded by the substitution contrast, because a
   reader, an echoer and a hardcoded ignorer write the identical string when
   the experience holds one verdict. The apparatus can substitute; it cannot
   discriminate.
3. E2 records cannot name an executed policy, so `control_distinct` refuses
   them on the same grounds it refuses the E1 records.

**What would have to change before a run is worth dispatching.** Two, and
neither is a dispatch.

The experience must carry at least two verdicts. That means the world has to
contain tasks the authored reducers do not solve, so the arm's experience has
a failure to learn from. This is a change to the panel, and the panel is
frozen, so it is a new namespace with its own freeze.

The construction prompt must render the `reason` alongside the `verdict`, or
the scored observable must read something the reducer's budget actually
changes. Otherwise a varied experience still renders as a constant and the
echo returns.

The second is the smaller fix and the more diagnostic: it would let a
constant-verdict, varying-reason experience be distinguished from a
constant-verdict, constant-reason one. Until it lands, any experience this
panel can produce is a constant at the surface the policy reads.

## What was not done

No existing artifact under `reports/evidence/` or `evidence-ad01/` was
modified or deleted. No gateway call was made, so the free-route availability
and the 128-model surface were neither confirmed nor used. No database was
created. The full test suite was not run.
