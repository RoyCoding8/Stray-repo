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
| 9. Architecture consolidation | Compare executable operational and improvement behavior; keep, replace or remove mechanisms | **Active, incomplete.** Dispositions as acceptance issued them: mechanism CONFIRMED as to the durable chain, with the freeze half repaired by X3 and the effect-identity half by X4b; acquisition NEGATIVE; utility NEGATIVE and not measurable; transfer NEGATIVE; autonomous selection NOT ESTABLISHED; learner improvement NEGATIVE. **The mechanism result is not evidence for any of the other five.** The write-only mission columns are gone as of `ff5b767`. |
| 10. Complete system prototype | Connected representations/transfer, autonomous agenda/teams, learner revision and consolidation | **Incomplete.** The two investigation rows are still different rows, so the SQL quiescence predicate governs nothing and two predicates remain. M2 is not started, and its central clause reads `False` on the shipped freeze: `observation_dependent` measured the falsifier's own hand, not causal influence. **Its existence does not claim beneficial RSI**: no eligible revision ran, so no learner improved. |
| 11. Operational qualification | Supported deployment, containment, recovery and controls | Partial groundwork; not qualified. Unchanged by the 2026-10-01 batch. |
| 12. Final implementation/release | Supported infrastructure product with migrations, installation, lifecycle UI and evidence | Not started as a release milestone |

Stages are not a waterfall: an experiment may force a revision to the formal model or technology. Retain sound prototype code rather than rewrite it merely because a later stage is called final.

## The current decision

The SQL mission ownership work is **partly done**. The write-only half of the
defect is closed: the five mission columns `migrations/0019` added had no
production reader, and `retained_use` had no writer at all, so
`migrations/0021` drops them forward rather than rewriting `0019`. The AD01
software and graph worlds are removed from the discovery matrix, and the one
world offering interventions is measured degenerate, so M3's supported-cell
count is zero by measurement.

What remains is not a column migration. **The two investigation rows are not the
same row**, so unifying them comes first: the live arm and the campaign mint
different SQL identities, the SQL quiescence predicate has no production caller,
and two quiescence predicates still exist. Until that is repaired, one
definition of readiness cannot govern both live admission and program
adoption, and no connected study can be frozen on top of it.

The [2026-10-04 batch](../../reports/PROJECT-LEDGER.md#mission-ownership-and-instrument-census-2026-10-04)
is the source for this paragraph. Its scope labels are earned: the AD01 worlds
are removed from the discovery matrix on four independent grounds, and the SWE
cell is measured degenerate. M3 closes as a valid null. It does not close
stages 9 or 10, and it says so.

Two facts decide what stage 9 does next, and neither is a stage-10 concern.
**The served output budget is 2048 tokens** (`invr1b12-swe/campaign.json`:
`max_output_tokens`), which is the figure that bounds what the route can return
for a construction attempt. **The Boolean instrument is not powered**: it offers
exactly one hypothesis class against six required, and that class is a
published constant all 72 tasks carry by construction, so no panel choice moves
it. **A two-domain demonstration is not a two-domain result.** Acquisition
returned 0 of 4 lineages on one returned artifact, which is a rate of nothing
rather than a measured zero capability.

The [2026-10-03 researcher review](../../reports/PROJECT-LEDGER.md#researcher-review-and-surgical-closure-2026-10-03)
selected SQL AD01 as the production mission owner and left the migration
unfinished. Finish it, then test program-selected acquisition/reuse and an
inherited acquisition decision. Coarse witness signatures describe a
projection; they do not prove statistical independence. The next study may
report scoped descriptive utility without pretending its cluster count
establishes statistical power.

The [surgical closure](../../reports/PROJECT-LEDGER.md#surgical-closure-and-recoverable-history-2026-10-02)
repairs initial mission admission, actual coverage reporting, source identity
and limited-run lineage summaries. These fixes do not connect the two mission
owners or demonstrate learning. The canonical branch is `codex/agent-society`;
historical snapshots are recoverable from the separate archive.

The [2026-10-02 coordinator review](../../reports/PROJECT-LEDGER.md#coordinator-review-2026-10-02)
assessed source `a7c132c`. Keep the durable effect identity, mandatory execution
authority, bounded program execution and the repaired behavioral scorer.
Converge the separate live JSON mission and SQL mission entry into the selected
AD01 owner before claiming a connected autonomous mission.

The [completion matrix](../../reports/STAGE-09-10-COMPLETION-MATRIX.md) separates
observed no acquisition from unmeasured utility/transfer and unrun learner
improvement. The worker report describes an older source tip. Its claim that all
learning questions are unaskable is limited to its chosen family-cluster protocol.
Minimum attainable sign-flip p-value is not statistical power, and output digest
diversity is not construction independence. Define the claim and experimental
unit before a fresh study; do not alter old evidence or raise alpha to obtain a
favorable result.

The A/B closure batch on `codex/ab-closure-2026-10-02` landed 25 lanes with
workstream reports. The 2026-10-01 consolidation batch behind it ran
`stage09-consolidation-2026-10-01`, its `invr1b12` SWE-construction
investigation, and two search passes; PROJECT-LEDGER.md carries the detail.
The first CI run found the suite had never executed off the author's machine:
23 failures from test DSNs naming a local socket, now repaired at the
isolation plugin.

Next, exercise program-selected investigation, live acquisition, retained use
and inherited acquisition decisions through one restart-safe public mission.
Assess operational quality and complete resources, not only a terminal verdict
that the reducer already guarantees. Valid measured negatives may close a
question. Missing arms, degenerate measurements and unrun studies remain open.

Stages 11 and 12 still require operational containment/recovery qualification
and a supported release. Local bounded child execution is not containment.

## Design references

The [design index](README.md) links philosophy, formal contracts, mechanisms and stack choices. Historical stage-8 tables and superseded stage-9 assignments remain recoverable through [Git history](../HISTORY.md).
