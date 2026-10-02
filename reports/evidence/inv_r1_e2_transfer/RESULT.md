# E2, contrast four: source-to-target adaptation loses to the target-only constructor

The handoff's fourth E2 contrast: *"Retained behavior on held-out families
within a world, and bounded source-to-target adaptation against an equally
budgeted target-only constructor."*

The other four E2 contrasts had a constructor in `learner` waiting. This one
had nothing, so `s09_e2_transfer` is new. Two arms, built by the same
`relevant_experience` call with different source id lists — one code path,
so the arms cannot differ in anything but which family the records name.

## The control, and why it is the strong one

- **adapted** — experience drawn from the *source* family (3 software dev tasks)
- **target-only** — experience drawn from the *target* family (3 graph dev tasks)

Equal record count (3 each) and equal length (382 characters each). Equal
length took an explicit refusal to guarantee: a seed record embeds its task
id, and `ad01-w1-within-sw-00` is three characters longer than
`ad01-w1-dev-gr-00`, so three records made an 18-character difference
between the arms. My first fixture did exactly that and the length assertion
caught it. The refusal is now a test.

The target-only arm is deliberately the **strong** control — building
directly for the target — not a strawman. An adaptation win could not be
read as a win over doing nothing.

## Result: adaptation loses

Target: `ad01-w1-transfer-gr-00`, a **graph** task. Both arms: 382
characters, 3 records, same route, same charter, same allowance.

| arm | question asked | diagnostic | queries |
|---|---|---|---|
| adapted (software experience) | "current capability of the **software** adaptation for task ad01-w1-dev-sw-00" | **software** | 1 |
| target-only (graph experience) | "which **graph** adaptation tasks show the highest discrepancy between source and target distributions" | **graph** | 3 |

The adapted arm is **pulled back to the source family**. Shown three
software records and asked about a graph task, it proposed a software
diagnostic and a smaller budget (1 query rather than 3). The target-only
arm, shown the same *amount* of text about the target family, targeted the
target correctly and asked the more substantive question.

## What this means

**Cross-family experience does not transfer through this construction, and
the transfer arm is worse than the equal-volume target-only arm.** This is
a negative result and it is the handoff's own framing — adaptation is
measured *against* an equally budgeted target-only constructor, and the
point of that control is precisely to catch a case where the adapted arm
looks busy rather than right.

It also sharpens the E2 picture. Relevant experience about the *target*
family helps (the no-experience arm mis-targeted; the relevant arm did
not). Experience about a *different* family is worse than no cross-family
transfer at all — it actively biases the proposal toward the wrong family.

## What is not claimed

One target, one dispatch per arm. The mechanism — source-family experience
drags the proposal back toward the source family — is consistent with the
other contrasts and with the mis-targeting in the no-experience arm, but a
single pair establishes the direction, not its size. A replication across
more target families and lineages is not run.

Evidence: `contrast.json`.
