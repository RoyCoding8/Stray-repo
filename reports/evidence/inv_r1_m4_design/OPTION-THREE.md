# Option three, tested: raising the cap does not work either

Jev scored the remaining option 0.02 and I had left it untested on purpose,
because loosening `extract_fenced_json` changes what the study measures.
Testing what is *recoverable* does not require loosening anything: if the
payload is not in the response, no parser can find it.

## Does a narrated response contain a recoverable payload?

Five calls, same prompt, same route, `max_output_tokens=4096`,
`reasoning_effort=low`:

| call | length | contains `"specs"` |
|---|---|---|
| 0 | 241 | no |
| 1 | 9362 | no |
| 2 | 10164 | **yes** |
| 3 | 13401 | no |
| 4 | 241 | no |

**One in five.** And the response is non-deterministic in a way the earlier
single-shot probes hid: one call emits a `specs` key, four do not, and the
lengths range from 241 to 13401 characters on an identical prompt.

So a relaxed parser would not help reliably. It would parse roughly a fifth
of the dispatches, and M4's tamper test needs a *clean* baseline, not one
that parses intermittently. Raising the cap turns a deterministic failure
into a flaky one.

## The 241-character calls are the interesting part

Two of the five returned 241 characters **with the eight observation rows
still in the prompt**. That is the same length as the "no rows" response
that parses. So the model is bimodal on this prompt: sometimes it narrates
for ten thousand characters, sometimes it answers in 241 — and which it does
is not controlled by the prompt.

That revises the earlier framing once more, and this time the revision cuts
against my own conclusion. I reported that "the narration is triggered by
the data values, not their presence", on the basis that a count-only summary
parses and a summary carrying the data does not. Both observations are
still true and the conclusion still holds as far as it goes — but the
241-character calls show the data is not *sufficient* to trigger narration.
The model reaches for the long form most of the time, not always.

## Where that leaves the three options

| option | parses | valid study design? |
|---|---|---|
| withhold the rows | always, at 167 chars | **no** — a fixed guess the model did not earn (Jev 0.21) |
| summarise | only when the summary discards the data | reduces to the above |
| raise the cap | **1 in 5** | no — flaky, and a clean baseline is the precondition |

All three are now measured, and none of them is mine to choose. The
remaining decision is what this study should claim to measure when the
model's compliance is a 20% event on the prompt the instrument requires.
That is the researcher's call, which is where Jev put it at 0.83.
