# E2: relevant experience vs a size-matched irrelevant control

Expansion question 2: *does accumulated experience improve acquisition and
action choice, and does relevant experience beat irrelevant or shuffled
experience?*

## What was missing

`learner.matched_experience_arms` built the relevant-vs-irrelevant pair and
`equal_length_experience_pair` refused an unequal one, but **nothing had
ever called the pair and then scored what came back.** The test suite
exercised `acquisition_cost_arms` — the cost side — not the relevance
contrast. So E2 had a constructor and no result. `s09_e2_relevance` is the
scored contrast: it renders each arm's exact construction prompt,
dispatches both through the real `learner.model_propose` path on the pinned
free route, and compares the two settled acquisitions.

## The design

One graph-family target task (`ad01-w1-transfer-gr-00`).

- **relevant arm** — experience seeded from three *graph dev* tasks
  (`ad01-w1-dev-gr-00/01/02`).
- **irrelevant control** — experience built by `irrelevant_control_for` from
  *software* filler, sized to match the relevant arm exactly.

The two rendered prompts are byte-identical except the trailing
`Prior observations:` line, and both arms carry **382 characters** of
experience. So a difference in what the model returns is attributable to
the *content* of the experience, not to how much text it was shown.

## The result: relevant experience wins, on both axes

| | relevant (graph seeds) | irrelevant (software filler) |
|---|---|---|
| question asked | "capability level for **graph** development tasks" | "status of **software** capability ad01-sw" |
| diagnostic requested | **graph** | **software** |
| queries requested | **3** | **1** |
| basis references | the 3 graph dev seeds | 1 software filler record |

The target task is a **graph** task. Shown graph experience, the model
proposed a graph diagnostic with 3 queries. Shown an equal-length pile of
software experience, it proposed a software diagnostic with 1 query. The
experience content steered both *what* it investigated and *how much* it
spent. `outcome: differs`.

This is a genuine relevance effect on a single live pair. It answers the
second half of question 2 — relevant beats irrelevant at equal context
volume — in the positive.

## What is *not* claimed

- **One pair.** This is a single target task and a single dispatch per arm.
  It is a clean, correctly-controlled positive, not an effect size. The
  direction is what it shows, not the magnitude, and one pair cannot
  estimate variance.
- **It measures proposal content, not downstream utility.** The observable
  is the acquisition the model returns (question, diagnostic, requested
  resources), which is what question 2's "acquisition and action choice"
  asks about. Whether the graph-diagnostic proposal then *scores* better on
  the target task was not run here.
- **The 382-char match is the control doing its job** — it removes context
  volume as a confound — but the two arms also differ in record *count*
  (3 seeds vs 1 fitted filler) as a side effect of equal-length sizing.
  With more tasks the count would be matched too.

Evidence: `reports/evidence/inv_r1_e2_relevance/contrast.json` and
`prompts.txt` (the two rendered prompts, byte-for-byte). Reproduce via
`experiments/ad01/s09_e2_relevance.py`.
