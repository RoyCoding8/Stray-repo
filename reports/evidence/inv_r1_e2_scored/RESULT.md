# E2 re-run on the scored observable: a three-way tie

The five contrasts were void because their dependent variable did not
discriminate. `s09_e2_scored` replaces it with one that executes the
returned policy and measures what it does. This is the first run on it.

## Result

Target `ad01-w1-transfer-sw-00`, three arms, all on the live free route:

| arm | scored | score | evidence | agreement | selected | verdict |
|---|---|---|---|---|---|---|
| relevant (3 graph seeds) | **true** | 1.0 | 0.0 | pass | `seed-sw-ddmin` | preserved |
| none (0 observations) | **true** | 1.0 | 0.0 | pass | `seed-sw-ddmin` | preserved |
| irrelevant (3 software seeds) | **true** | 1.0 | 0.0 | pass | `seed-sw-ddmin` | preserved |

**A three-way tie, and the tie is the finding.** All three arms scored —
which is the first time any arm has — and all three earned the agreement
leg alone. **Every arm scored 0.0 on evidence**: none of the three
acquired policies changed its action when the observation verdicts were
flipped. The scored view differs from the alternate view in nothing but the
verdicts, so an evidence score of zero means the policy was not reading
them.

All three selected `seed-sw-ddmin` — the first eligible method — which is
consistent with the evidence leg: a policy that ignores its observations
takes the first option every time.

## What this is, and what it is not

**It is a real, discriminating measurement, and it is negative.** The
observable is the one the swarm built and verified: reader 2.0 against
identical blind policy 1.0. Against it, three live acquisitions all
behaved identically and none responded to evidence.

**It is one task and one dispatch per arm.** It does not establish that
experience never helps; it establishes that on this task, with these
observations, the model did not produce a policy that reads them. The
sample is the limit, and it is a small one.

**It is not a re-run of the five contrasts.** This is the relevant/none/
irrelevant triple — the first two contrasts, live, on the scored scale.
The retained-vs-cold, source-to-target and observation-substitution
contrasts are not re-run.

## Five defects had to be closed first

Getting here took five repairs, all presenting as the same opaque refusal
("admitted no action that reaches a method executor") and four of them
mine:

1. `score_response` forwarded `**kwargs` to the `Score` constructor
   instead of to `measure`, so `eligible_methods` could not reach the view.
2. The construction prompt quoted the **step** envelope, not the
   **response** envelope the parser reads.
3. `eligible_methods` was named as a view field and left empty everywhere.
4. The prompt never showed a complete action; `ACTION_REQUIRED` is five
   fields and the model wrote two.
5. The prompt never said the view is a dict, so the model guessed
   `view.eligible_methods` and the child raised `AttributeError`.

A hand-written known-good policy scored 1.0 through the same path at every
step, which is what established each break as wiring rather than the model.

Evidence: `readings.json`.
