# Philosophy to final implementation

This is the mental model, not another task diary. The [project ledger](../../reports/PROJECT-LEDGER.md) gives current evidence; the [worker prompt](../../WORKER-PROMPT.md) gives the next complete assignment.

General autonomous discovery remains the goal. Memory, background development, teams and executable skills are candidate mechanisms. Their value is what they enable the system to learn and do; more machinery alone is not progress.

| Stage | Question or deliverable | Status |
|---|---|---|
| 1. Philosophy | Purpose, generality, growth and relationship to the human | Baseline selected; revisable |
| 2. Intuitive picture | How investigation, remembering and self-development fit together | Baseline selected |
| 3. Precise/formal description | Entities, transitions, obligations, limits and claims | Baseline specified; no proof of intelligence |
| 4. Abstract architecture | Ownership of execution, development and agenda | Baseline selected |
| 5. Representation and technology | Executable packages, state and supporting stack | Provisional choices; revise from evidence |
| 6. Practical specification | Builder protocols and acceptance conditions | Foundation specified |
| 7. Foundation prototype | Durable bounded execution, evidence, trials and continuity | Built; deployment validation remains partial |
| 8. Cognitive-policy refinement | Acquired competence, memory, agenda, representations and teams | Closed at bounded mechanism scope; broader learning questions remain open |
| 9. Architecture consolidation | Compare executable operational and improvement behavior; keep, replace or remove mechanisms | **Active.** All four experiments now have answers and **all four are negative**, though not for the same reason: E1 measured nothing to compare, E2 measured a null the panel cannot express, E3 recomputed its tables and does not show autonomous selection, and E4 ran six live dispatches and admitted no revision. The comparison is not the blocker. |
| 10. Complete system prototype | Connected representations/transfer, autonomous agenda/teams, learner revision and consolidation | Not complete |
| 11. Operational qualification | Supported deployment, containment, recovery and controls | Partial groundwork; not qualified |
| 12. Final implementation/release | Supported infrastructure product with migrations, installation, lifecycle UI and evidence | Not started as a release milestone |

Stages are not a waterfall: an experiment may force a revision to the formal model or technology. Retain sound prototype code rather than rewrite it merely because a later stage is called final.

## The current decision

Stage 9 should tell us which learned executable behaviors are acquired, causally used, reusable and worth their resources. Test relevant experience, autonomous investigation choices and a revision that improves the acquisition process itself. Use multiple task structures so a fixed reducer or Boolean benchmark does not become the architecture.

**The comparison is done and all four answers are negative.** E1 constructed nothing across three campaigns, and its largest cause is the route's 2048-token output budget rather than the route being down. E2's primary statistic was a constant, so every recorded result was void; re-run on the repaired metric the experience contrast is null, and a reachability census shows the panel cannot express a positive delta at all, so the null does not say experience does not help. E3 recomputed its tables from source, the ratio is an identity of its own denominators, and both controls are pre-committed schedules, so it does not show autonomous selection. E4 ran six live dispatches, admitted no revision, and the headroom above its boundary turned out to be a blind-sequence artifact rather than a narrow interface. A stage that read these as "comparison incomplete" would be misreading its own evidence. They are answers, and all four are no.

**§W2 is complete** (`cab9424`). Retention is unmeasurable here -- the repertoire is four
authored seeds and no acquired method can be nameable on any target -- and adaptation found a
**domain effect that is not an experience effect**: every arm loses 0.2692 moving to the
held-out domain while the experience contrast is 0.0 on both sides. The panels measured there
are open, so that null was measured where a positive result was expressible, which the
experience contrast's own panel was not.

What the negatives name is narrower and more useful than the positives would have been.

- **E1's binding constraint is model budget behaviour against the protocol, not the harness.** r1's zero belonged to the harness and was repaired (`3721cd6`). r2's zero belongs to the model: six answered dispatches all ran to the frozen 2048-token ceiling, stopped on `length`, and never emitted the requested 512-character object. The binding constraint is the protocol asking for a small artifact while granting the budget to reason past it. More dispatches of the same shape measure the same thing again. Acquisition exists for exactly one cell, and that width was verified by a census over the parsed source rather than assumed from a naming convention.
- **E4's blocker is the two-element selector, and the headroom read against it is a blind-sequence artifact.** The six refusals were correct and are not a substrate failure: `improve_channel.classify_revision` (`:387`) refuses a revision whose choices equal `_incumbent_choices` or `_reducer_argmax`, and every reply named input 0. Within the frozen decision the choice genuinely does not matter, and the reachable range there is `0.00622`. What stood against that is withdrawn: `0.5017` was a **blind** query sequence, built by `learner_revision.py:966-977` calling `choose_query` and never `learner.observe`, and `choose_query` reads only the keys of `queried`, so the zero vector is inert. An informed sequence reaches 0.8500 on the same cohort at z=+11.38, and +0.2675 at z=+8.38 across splits sharing zero truth tables. **A binary switch is not the argument for widening; a measurement that never calls `observe` is not the argument for anything.** The open question is whether a *descendant* may gather its own evidence, which needs its own freeze.

Two consequences follow for stage 10, and both argue for less machinery rather than more. The acquisition surface is one prompt wide, so the nine-cell representation comparison the design asks for was never run and cannot be run by adding dispatches to the cell that exists. The revision menu has two entries, so the learner cannot yet be shown improving anything.

A null result can justify simplification; a green harness cannot establish learned advantage. Progress to stage 10 when those two boundaries are answered, not when another campaign finishes on the current ones.

The [transfer assessment](../../reviews/STAGE-09-TRANSFER-ASSESSMENT.md) records the material gaps. It predates the E1 r2 run and the E2 instrument repair, so the [project ledger](../../reports/PROJECT-LEDGER.md) is the authority for current status.

## Design references

The [design index](README.md) links philosophy, formal contracts, mechanisms and stack choices. Historical stage-8 tables and superseded stage-9 assignments remain recoverable through [Git history](../HISTORY.md).
