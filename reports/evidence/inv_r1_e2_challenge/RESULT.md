# Pass-3 challenge: the E2 positives do not survive it

The handoff's third engineering pass requires challenging *all positive
conclusions*. I challenged the two E2 positives directly, and **they do not
survive.** The result here retracts the mechanism claim in
`inv_r1_e2_noexp` and `inv_r1_e2_relevance`.

## The challenge

The no-experience arm proposed a *software* diagnostic for a *graph* task,
and I read that as "with nothing to go on, it mis-targets". The obvious
alternative: **`software` is simply the model's default family**, regardless
of what it is shown. One target family cannot tell those apart.

So: a 2×2, same live path, same charter, same allowance, both target
families, both experience conditions.

| cell | target family | diagnostic chosen | |
|---|---|---|---|
| graph target, relevant experience | graph | **software** | MISS |
| graph target, no experience | graph | **software** | MISS |
| software target, relevant experience | software | software | MATCH |
| software target, no experience | software | software | MATCH |

## What this means: the positives were misattributed

**`software` is a default, not a consequence of anything.** It is chosen in
all four cells — with and without experience, for both target families. The
"relevant experience helps" conclusion I drew from
`inv_r1_e2_noexp` and `inv_r1_e2_relevance` does not survive: the arm that
looked evidence-driven was no more responsive to evidence than the arm with
zero observations, because both were answering with a prior.

The pattern is unmistakable: **the model is right on software targets and
wrong on graph targets, in every condition.** The explanation is a
capability difference between the two families, not an experience effect.
Software is in-distribution; graph is not. Experience had nothing to add
because the failure was never about evidence.

This is exactly the failure the handoff's warning describes — *"Do not let
a reviewer rewrite assertions merely to agree with the implementation"* —
inverted: I wrote the assertion, the challenge refuted it, and the
assertion is being withdrawn rather than the challenge dismissed.

## What the other E2 results are now worth

- **relevant vs no experience** — **retracted as a mechanism claim.** The
  one apparent difference was noise on a default.
- **relevant vs size-matched irrelevant** — **retracted as a mechanism
  claim**, same reason. The graph/software split I read as "experience
  steered the diagnostic" is the same default.
- **retained vs cold reacquisition** — **unaffected.** It is a cost result
  derived from the cap sheet; no model behaviour is involved.
- **source-to-target adaptation** — **still negative, and now for a
  stronger reason.** I read the adapted arm's software diagnostic as
  "pulled back to the source family". It was the default. The arm did not
  lose to the target-only constructor; it never left the default. The
  contrast is uninformative about transfer.
- **observation substitution** — **unaffected.** Its result is about
  envelope defects in the acquired bytes, not about which family the model
  prefers.

## The corrected finding

What the campaign has actually established about experience, so far: **not
that experience steers acquisition.** The two cells that discriminate are
identical across conditions, and the single most informative number in this
2×2 is that 2 of 4 cells are wrong regardless of what the model is shown.

The honest next step is not a larger sample of the same contrast. It is a
task family the model can actually do, so that any movement away from the
default is visible — or an instrument whose tasks name their family in the
public view, so a "default" and a "decision" can be told apart at all.

## Methodology note

The prior E2 results are left in place, unedited, as the record of what was
claimed and when. This file is the retraction, and it is a separate
directory so the evidence files are not rewritten after the fact. The handoff
requires preserving nulls and reversals and forbids selecting the
best-looking run after seeing outcomes; a reversal I found by challenging
my own positive is the same discipline applied in the other direction.

## Replication, and the corrected mechanism

The 2×2 left two readings open: `software` was a fixed default, or it was
whatever the model last saw. The second is testable. Six cells, three
software targets, each with and without experience — and the experience
this time is **graph**, the family the model handled badly.

| target | experience shown | diagnostic chosen |
|---|---|---|
| transfer-sw-00 | graph (relevant) | **graph** |
| transfer-sw-00 | none | **graph** |
| transfer-sw-01 | graph (relevant) | **graph** |
| transfer-sw-01 | none | **graph** |
| within-sw-00 | graph (relevant) | **graph** |
| within-sw-00 | none | **graph** |

**Six for six, the model names the family it was shown** — and the `none`
cells agree with the `relevant` ones, because the charter and the arm
record already put graph in front of it either way.

So there is no family default. There is **no discrimination between
experience and no experience at all**: the `none` arm is not receiving zero
context, it is receiving the same context through the charter, and it
copies it just as faithfully. The original 2×2 read as a family default
only because the graph experience in that run happened to be absent from
the software cells, leaving software as the last family mentioned.

## The corrected finding, which is a negative about the instrument

**The `diagnostic` field does not measure what these contrasts were built to
measure.** It echoes the most recent family token in context, and it does so
identically with and without experience. Every E2 contrast that read a
difference in `diagnostic` — including both positives I just retracted —
was reading an echo.

That makes all five contrasts uninformative about experience, with two
exceptions that never touched `diagnostic`:

- **retained vs cold reacquisition** — a cost result from the cap sheet,
  unaffected.
- **observation substitution** — about envelope defects in acquired bytes,
  unaffected.

The handoff asks for contrasts that *"distinguish mechanisms"*. The
mechanism these were meant to isolate — semantic relevance steering
acquisition — is not measurable through a field the model echoes from
context. Measuring it needs an observable that cannot be satisfied by
copying the most recent token: the *quality* of the returned policy scored
on the target task, which is what `inv_r1_e1_comparison` already does for
use-phase behaviour.

## What this pass cost and what it bought

It cost two positive claims and the credibility of a third. It bought a
finding that would have invalidated all three had it not been run: **a
dependent variable that echoes its input cannot support a claim that the
input influenced the output.** Every one of these contrasts had exactly
that shape, and two of them reported a positive.

Recorded in full because a pass that only ever confirms is not a pass. The
next step is to re-run the E2 contrasts against a scored observable, not
another sample of the same one.

## Jev disagreed, and the experiment it called for

I put the echo claim to Jev with the competing interpretation attached, as
the handoff requires at consequential calls. It did not agree:

| question | Jev |
|---|---|
| does the evidence rule out a genuine experience effect? | **0.46** — a coin flip |
| is retraction warranted? | **0.78** — yes |
| how well supported is the claim by the evidence presented? | **weak** (0.82) — *a live alternative remains untested* |

Jev kept the retraction and rejected my confidence in the *mechanism*. Its
objection is specific and fair: every cell so far varied the family token
and the experience together, so "echoes context" and "responds to
experience" predict the same data.

**The experiment that separates them holds the experience fixed and varies
only the prompt.** Software target, graph experience in every cell, and the
charter names a different family:

| charter | experience | diagnostic |
|---|---|---|
| names **graph** | graph (fixed) | **graph** |
| names **software** | graph (fixed) | **graph** |

Changing the prompt's family mention did **not** move the field. So it is
not tracking arbitrary prompt text, and "echoes its input" is too strong a
description of what I measured.

## What survives, stated at the strength the evidence carries

- **The retraction stands** (Jev: 0.78, and the reasoning agrees). The five
  contrasts used a categorical `diagnostic` field where every cell came out
  equal between experience and no experience. They do not discriminate, so
  they cannot support a claim either way — positive or negative.
- **The echo mechanism is now falsified** by the charter test. Whatever
  `diagnostic` tracks, it is not the most recent family token.

What the data actually shows: the field agrees between the experience and
no-experience arms in every condition tested, and it moves with neither the
charter nor — on this evidence — anything measured. That is a **dead
observable** for this question, which is a different and better-grounded
finding than the echo I asserted. A field that carries no signal is not
evidence of an effect in either direction, and calling it an echo invited
a stronger causal story than the measurements support.

The lesson is the one the handoff states: Jev is advice, not proof, and
advice that dissents is worth an experiment rather than a footnote. Had I
consulted it before writing the claim, the charter test would have run
before the claim was ever committed.
