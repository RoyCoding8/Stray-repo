# M3 prospective study: first completed run

`inv_r1_m3_run7`, 2026-09-26, on disposable store `s09iso_m3run7`. 35 settled
successes, 3 unknown, 6 campaigns, 32 model calls, 7 construction calls,
24 use records, 556 witness queries.

## What was acquired

**One.** `repertoire-w0-I.json` holds a member with `authored: False`,
`capability_id: acquired-sw-2074657c`, an `ENTRY` the model composed, qualified
on `ad01-w0-dev-sw-00`. The other five repertoires are empty.

The composed entry was `reduce_graph(task, oracle, method="ddmin",
max_queries=max_queries)`. `ddmin` is one of exactly two methods the constructor
offers and is also the signature default. Zero of the observed constructions
chose `greedy`. The model picked the default every time.

## Why every use record refused

All 24 are `status: refused` with one uniform reason: `use ran with no policy:
the method identity must come from an admitted policy action`. The CLI refuses
a use phase with no policy by design (`cli.py:41`), and `_fresh_use` never
passes `--policy-source`, so `policy` is always `None` (`trajectory.py:1342`).
The guard is correct; the caller is wrong.

Two things then follow, and only the first is a bug.

**The one acquired capability is in the calibration world.** `w0` is
`CALIBRATION_WORLD`; the use phase runs only over `COMPARISON_WORLDS` = `w1, w2`.
So even a correctly wired caller would have found an empty repertoire for every
world it uses. Acquisition and use are over disjoint worlds by construction.

**The receipts persist only the response, not the prompt.** So what the
constructor offered cannot be recovered from this store, and the claim that the
model chose from a two-item menu is inferred from the response, not attested.

## What this run does and does not establish

It establishes that a live model call on the confirmed free route settles
`success` and that the pipeline carries a real response through to a
durable receipt. It does not establish acquisition beyond one member, and that
one chose the default of a two-item menu.

Mechanism `true`. Acquisition `unproven`: one member, default choice, and no
recorded prompt. Task utility `not_comparable`: every use record is a refusal.
Transfer `unproven`: no policy ever reached a use phase.
Recursive improvement `ineligible`: E4's channel has no headroom.
