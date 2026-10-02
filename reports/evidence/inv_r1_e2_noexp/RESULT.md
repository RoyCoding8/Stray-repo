# E2, contrast one: relevant experience versus no experience

The handoff's first E2 contrast: *"Relevant development experience versus no
experience with an equivalent interface and construction allowance."*

Both arms go through the same live `learner.model_propose` path on the
pinned free route, with the same charter, the same world and arm, and the
same construction allowance. The only difference is whether the arm carries
development experience at all.

## Result

Target: `ad01-w1-transfer-gr-00`, a **graph** task.

| arm | observations | question asked | diagnostic | queries requested |
|---|---|---|---|---|
| relevant | 3 graph dev seeds | "How do the graph development tasks perform for relevant vs no experience acquisition?" | **graph** | 3 |
| no experience | **0** | "Proceed with development task ad01-w1-dev-gr-00?" | **software** | 5 |

The no-experience arm, given the same interface and the same allowance, and
shown nothing, proposed a **software** diagnostic for a **graph** task. The
relevant arm, shown three graph seeds, proposed graph.

Directionally this is the mechanism the handoff asks about, and it is
stronger than the E2-relevant-vs-irrelevant result in one respect and weaker
in another:

- **Stronger**: the no-experience arm is not merely worse, it is
  *mis-targeted*. It picked the wrong family with no evidence to go on,
  which is the failure the contrast is designed to expose.
- **Weaker**: this contrast does **not** separate semantic relevance from
  context volume, because the two arms differ in volume by construction —
  3 records against 0. That confound is exactly what the
  relevant-vs-irrelevant contrast exists to remove, and it removes it
  (382 characters each). This contrast answers "does experience help at
  all"; the other answers "does *relevant* experience help more than
  equally long irrelevant experience".

The two results agree in direction and neither substitutes for the other.

## What is not claimed

One target task, one dispatch per arm. The mis-targeting of the
no-experience arm is one observation of a policy choosing a family with
nothing to go on, not an estimate of how often that happens. The
mechanism is consistent across both contrasts; its size is not measured.

Evidence: `contrast.json`.
