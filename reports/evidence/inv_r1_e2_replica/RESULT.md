# E2, replicated in a second campaign namespace

`WORKER-STAGE-09-PARALLEL-EXPANSION.md:67` requires two independent campaign
namespaces for a replication, sharing neither mutable state nor assessment
feedback. `inv_r1_e2_scored` is the first. This directory is the second, and
the two share no store, no allocation, no operation id and no evidence
directory.

## What was replicated, and why those arms

The relevant / none / irrelevant triple, because those are the only
behavioural arms in the first namespace carrying a result on a scored
observable (`reports/evidence/inv_r1_e2_scored/readings.json`: three arms, all
`scored: true`, all `score: 1.0`, all `evidence: 0.0`, all
`selected: seed-sw-ddmin`).

The other two contrasts were not replicated. Retention is arithmetic over a
cap sheet and involves no model behaviour, so a second namespace cannot
re-measure it. Observation substitution re-scores one acquisition twice, so it
is not a fresh cohort. `inv_r1_e2_relevance` was **not** re-run: it compared
two empty dispatches (`sha256("")`, `prompt_chars: 0`) and is retracted.

## The cohort is fresh, and the contrast was frozen first

Cohort world **0**. The first namespace ran world 1. Targets are the three
`ad01-w0-within-sw-*` tasks, development experience from the three
`ad01-w0-dev-sw-*` tasks, and the irrelevant control is sized from the three
`ad01-w0-dev-gr-*` graph tasks. The contrast is frozen at
`freeze_digest` `27ba14c9cf69bdeb864e4f1f...` and `verify_freeze` refuses an
edited or drifted freeze.

## Two defects in the first namespace's instrument, found before the run

**The evidence leg could not be earned.** `s09_e2_scored.VERBATIM` excludes
`method_id` and `max_queries`, and the construction prompt's worked example
builds an action whose `inputs` are exactly those two keys. A policy that
names a repertoire member through the shape the prompt shows has **no measured
input site at all**: `evidence_total` is 0 and the leg is `0 / 0 == 0.0`. The
first namespace's `evidence: 0.0` on every arm is that ratio, not a measurement
of a policy that ignored its verdicts. Its discrimination claim (reader 2.0,
blind 1.0) is real, but was demonstrated on a policy that also wrote `plan`
and `witness` into `inputs` — a shape no prompt asked for.

**The verdict flip was a no-op on seed experience.** `VERDICT_FLIP` has no
entry for `unmeasured`, and every record `learner.seed_observations` builds
carries `verdict: "unmeasured"`. For the arms the first namespace actually ran,
the "scored" and "alternate" views were byte-identical. **Its evidence leg had
no contrast to measure, by construction.**

Both are defects of the instrument, not of the model. This namespace repairs
them: experience records carry a verdict a real reducer earned (run the
authored reducer, grade with the campaign's own checker), and the prompt adds
one line telling the model it may put a third key in `inputs`
(`prompt_delta` in `report.json` is that line).

## The result: the relevant-minus-none difference is an artifact

Nine dispatches, nine scored readings, no nulls, no retries spent.

| arm | task | scored | quality | evidence | varied | selected |
|---|---|---|---|---|---|---|
| relevant | within-sw-00/01/02 | true | 1.0 | **1.0** | 1/1 | `seed-sw-ddmin` |
| none | within-sw-00/01/02 | true | 1.0 | **0.0** | 0/1 | `seed-sw-ddmin` |
| irrelevant | within-sw-00/01/02 | true | 1.0 | **1.0** | 1/1 | `seed-sw-ddmin` |

Paired by target task, through `learner_revision.paired` (the repository's
paired estimator, `ESTIMATOR = "paired best-reachable vs incumbent"`):

| contrast | delta | n | paired sd | paired se | z |
|---|---|---|---|---|---|
| relevant − none | **+1.0** | 3 | 0.0 | 0.0 | null |
| irrelevant − none | **+1.0** | 3 | 0.0 | 0.0 | null |

**The +1.0 is carried entirely by the evidence leg. The quality leg is 1.0 for
all nine readings, and all nine selected the same method.** Nothing about what
the policy *did* differed.

`instrument_qualification.echo_confound` shows why. Two authored controls,
under two exposures:

| | ignores the view | echoes the verdicts |
|---|---|---|
| relevant (3 observations) | 1.0 | **2.0** |
| none (0 observations) | 1.0 | **1.0** |

A policy that copies the verdicts into an input key and then acts exactly as
it would have anyway — reads nothing, decides nothing — earns the full
evidence leg under a non-empty arm and nothing under an empty one. **The
evidence leg separates an echoer from an ignorer only when the arm has
observations to echo.** So a +1.0 evidence gap between a relevant and an
empty arm measures echoing, not reading, and this replication's positive
number is not evidence that experience helped.

**Corrected for multiple comparisons: no, and no correction is offered.** With
two `(family, template)` clusters on the `within` split, the minimum
two-sided sign-sweep p-value is 1/2 against the 1/20 the protocol names, and
6 clusters are required. No p-value this contrast can produce is inferential,
so every number above is descriptive. `census` in `report.json` states this in
the artifact.

## Agreement with the first namespace

**Partly reverses it, on the instrument rather than on the model.**

| field | first namespace | replica |
|---|---|---|
| scored | true | true |
| verdict | preserved | preserved |
| agreement | pass | pass |
| selected | `seed-sw-ddmin` | `seed-sw-ddmin` |
| score | 1.0 | **2.0 (relevant, irrelevant) / 1.0 (none)** |
| evidence | 0.0 | **1.0 / 0.0** |
| evidence_total | *not recorded* | 1 |

The two namespaces agree on every behavioural field that both recorded. They
differ on the score and the evidence leg, and the difference is the first
namespace's instrument, not the model: with the leg made measurable, the same
model writes the `read_verdicts` key the prompt now asks for and the leg moves.
All nine replica readings selected `seed-sw-ddmin`, exactly as the first
namespace's three did.

**What survives from the first namespace is the negative, and it is now
better founded.** The first namespace's finding — that experience did not
measurably change what the model acquired — is not overturned, because the
replica's only positive difference is a difference about echoing. Both
namespaces agree that **all policies select the first eligible method and all
candidates grade `preserved`.** Whether that is "no effect of experience" or
"an observable that cannot see one" remains open, and this replication
sharpens the second reading: the instrument as built cannot distinguish
reading from echoing.

## Cap sheet and authority

Derived from the frozen matrix before any effect, and bound through the
durable owner (`settlement.broker.ensure_operation` +
`dispatch_operation`, under `authority.authorize_study` via
`s09_run_isolation.RunIsolation`).

| line | value |
|---|---|
| construction dispatches | 18 (3 tasks × 3 arms × (1 + 1 retry)) |
| route probe dispatches | 1 |
| physical sends ceiling | 19 |
| units per request | 2464 (estimated-budget) |
| total units | 46816 |

Spent: 10 dispatches, all through the durable owner. One cheap probe
(`max_output_tokens: 8`, 16 units) confirmed the route before any effect; its
receipt records the resolved model and `tier: free`. The retry allowance was
declared and unspent on the final run. `dispatch_attempts` in `report.json`
lists every operation id, and each has a reservation and a receipt in the
store.

## What could not run, and why

- **The graph family.** The `within` split offers two software templates
  across three worlds, so a graph arm would have been a single cluster. The
  census is already unpowered at two clusters; adding a second family would
  double the dispatches without reaching the six clusters the protocol needs.
- **Any inferential claim.** Two clusters cannot produce a p-value below 1/2.
  Making this contrast powered needs six `(family, template)` clusters, which
  the frozen panel does not contain for `within` on either family.
- **A repaired evidence leg.** Distinguishing reading from echoing needs the
  leg to compare the two candidates, not the two action inputs. `s09_e2_scored`
  is outside this namespace's ownership, so the repair is reported here and
  not made.
- **`inv_r1_e2_relevance`.** Deliberately not re-run: it is a retracted
  apparatus campaign, and re-running it would reproduce a defect.

Evidence: `report.json`. Reproduce via
`experiments/ad01/e2_replication.py`.
