# Stage 9 policy revision cycle: status at 4c529ab

Branch `codex/stage-09-opus-completion`, cut from checkpoint `8e05c14`.
Stage 9 is **not** closed. This report separates what is demonstrated from what is not.

## What changed and what it means for the next owner

The public revision path used to stop after freezing candidate policy bytes, leaving
`assessment_status="pending"`. The only callers of `records.assess_frozen` and
`selection.bind_revision` were tests. So the "policy revision cycle" was a cycle only
because test bodies called the missing steps.

Production now owns those steps. One public `run_campaign` call proposes a revision,
constructs `learning-policy` `STEP` bytes, freezes them, freezes a sealed panel and a
finite comparison rule before exposure, runs a policy-specific assessment over both the
incumbent and the candidate, and then binds the exact assessed bytes or records an
explicit durable rejection or unavailability that leaves the incumbent active. A second OS
process given only a release id resolves the same bytes from durable state and decides
through them.

The next engineer inherits three things. A policy assessor that is separate from the
task-method evaluator and cannot be satisfied by a reducer score. A driver whose revision
path has no `pending` terminal state. And a release resolution path that refuses rather
than substitutes when pinned bytes are absent.

## Verified, with the command and the observed result

| Check | Command | Observed |
|---|---|---|
| Pre-change baseline, 15 original Stage 9 files | `gate.sh baseline <15 files>` | 84 passed, exit 0, 648.34s |
| Integrated gate on merged source, 18 files | `gate.sh integrated <18 files>` | 106 passed, exit 0, 337.08s |
| Causal discrimination plus the new suites | `gate.sh causal-verify <5 files>` | 30 passed, exit 0, 144.90s |
| Exploit regressions, red before the fix | `gate.sh boundary-red` | 3 failed, exit 1 |
| Exploit regressions, green after | `gate.sh boundary-green2` | 3 passed, exit 0 |

All runs used WSL Ubuntu, Python 3.14.4, real PostgreSQL 18.6, real child processes, and
provider doubles. `settlement.__file__` was printed inside this checkout on every run. Logs
are in `D:/AI/s09o/logs/`. No live model call has been made.

## The causal claim, and the control that supports it

A digest equality assertion cannot show that policy bytes drive behaviour.
`tests/test_s09o_causal.py` discriminates. Two different bound policies produce different
durably recorded action-kind sequences through the same public path:

- construct policy: `["diagnose", "propose_revision", "construct_method", "stop"]`,
  candidate digest `641ae414...`, `construction_calls == 4`
- use policy: `["diagnose", "propose_revision", "use_method", "stop"]`,
  candidate digest `570742f9...`, `construction_calls == 0`

The negative control is what makes that meaningful. A third policy differing only in
whitespace has a different digest, `fd5c9d3f...`, and produces the **same** sequence as the
construct policy. So the behavioural difference between the first two cannot be explained
by digest identity. The difference also appears in effects, not only in decisions.

## Two demonstrated exploits, found by adversarial review and fixed

ADV-02. `selection.select_member` substituted the release `fallback` member whenever the
pinned candidate bytes were absent from the repertoire. Every disposition that reaches
selection is a promoting one, so that branch could only ever execute unassessed bytes,
while `run_use` still recorded the requested capability as executed with an empty
`fallback_reason`. An export could not reveal that the assessed candidate never ran. The
branch is removed; absent pinned bytes now refuse and `trajectory._use_refusal` reports
why. The reviewer's probe had accepted a `default` release and selected
`unassessed-incumbent`.

ADV-03. `policy_step.materialize_view` copied observations verbatim, so an untrusted STEP
policy could read a sealed answer and place it in a `request_model` prompt and the
persisted policy journal. The reviewer's probe captured `sealed-answer-probe-9f3c` as the
prompt argument. The view now projects observations through
`packet.project_observations`. A test confirms legitimate feedback still reaches the
policy, so the fix did not simply empty the view.

## Jev decision record

`reports/jev/` holds the sanitized requests and responses.

Checkpoint 1, plan coverage. Policy execution 0.93, exact binding scope 0.87, independent
promotion 0.84, experimental isolation 0.77, persistence 0.64. Weakest area
`production_ownership` at 0.78, confidence 0.72. Resolution: raised rigor there and made
the public path refuse an injected consumer, rather than rephrasing the question.

Checkpoint 2, causal and evidence separation, against the integrated source.
`exact_byte_activation` 0.94, `promotion_is_production_owned` 0.90 (up from the 0.78
weakness at checkpoint 1), `patch_leaves_a_bypass` 0.21, `returned_bytes_change_runtime_
decisions` 0.68, `stage_closure_supported` 0.22, largest remaining threat
`comparison_not_rewired` at 0.58 with confidence 0.47.

Two of those changed what I did. The 0.68 on the causal question was an evidence gap, not a
disagreement, so I ran the discriminating control described above instead of arguing. The
0.22 on stage closure matches my own reading, so this report does not claim closure.

## Not verified. What the next owner must still do

1. `records.export_campaign` and `records.verify_campaign` do not export or offline-verify
   the policy assessment record or the release binding. Until they do, the independent
   recomputation does not cover the two things this checkpoint added, and C6's offline
   recomputation requirement is unmet.
2. The three-arm prospective comparison in `scripts/s09_pilot.py` is not rewired to this
   cycle. Jev named this the largest remaining threat, and it is: an experiment that does
   not drive the connected mechanism would not measure it. The C3/N5 schedule is unchanged
   and still has to be honoured.
3. No live study has run. The authorized grant of at most 100 free-model calls is unspent.
   Local and stored usage must be inspected before the first call, and the resolved model,
   effort and endpoint frozen in the durable grant.
4. Jev checkpoints 3 and 4 are not done.
5. A second independent review, following bytes and actions through the public path, is not
   done. The authority, leakage, identity and resume review is done and is at
   `reports/opus-completion/REVIEW-ADVERSARY.md`.

## Boundaries on the evidence

Everything above is deterministic machinery and controlled doubles. Nothing here is live
inference. Nothing here shows that a revised learning policy produces better investigation
outcomes; it shows that a revised policy is assessed on its executed behaviour, activated
only as its exact assessed bytes, and continued across a restart. Whether any benefit
survives the controls and the resource rule is exactly the open empirical question, and a
negative answer would be a valid result.

`tests/test_ad01_traj.py` reports 5 errors from a missing `ec02test_adtr` database owned by
another task. Reproduced identically with my changes stashed: same 5 errors, 26 passed.
Pre-existing, not mine to fix, and not a regression.
