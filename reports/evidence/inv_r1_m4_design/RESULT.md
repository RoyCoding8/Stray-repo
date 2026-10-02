# M4's design decision, made explicit and tested

M4's blocker was removed by withholding the observation rows: the response
drops from 5732 characters to 167 and parses. But a predictor committed with
no observations is a fixed guess, and scoring it would measure the
instrument's prior rather than any acquisition. So the withholding fix
raises a question rather than closing one.

I put the question to Jev rather than choosing myself.

| question | Jev |
|---|---|
| best option | **summarise** (0.56; withhold 0.06, raise cap 0.02) |
| is withholding a legitimate design? | **0.21 — no** |
| does this need the researcher's judgement? | **0.83 — yes** |

Jev rejected the option I had found, and said the call is the researcher's
rather than the campaign's. Both are right, and the second one is why what
follows is a measurement rather than a decision.

## Testing the option Jev preferred

`summarise` means replacing the eight rows with information *derived* from
them, so the candidate is earned without the raw data being present. Two
forms, and the difference between them is the finding:

| public view | response | parses |
|---|---|---|
| rows withheld entirely | 167 chars | yes |
| summary: count of observations | 143 chars | yes |
| summary: count plus a "budget spent" note | 167 chars | yes |
| summary: count plus **the actual spend data** | 4818 / 7092 chars | **no** |

**The narration is triggered by the data values, not by their presence.**
A count of eight observations does not trigger it. The eight observations
do, however they are packaged.

That reframes the finding again. It is not that the model cannot handle a
large prompt — 44, 143, 167 and 4818 characters are all the same task. It
is that presented with data it can reason about, this model *reasons*, and
the reasoning is the output.

## What this leaves

The summarise option Jev preferred **does not work as stated**, because a
summary that carries the data is the data. Only a summary that discards it
parses, and a summary that discards the data does not yield an earned
candidate — which is the same position as withholding, reached by a longer
route.

So the honest state is:

1. **Withholding parses and is not a valid design** (Jev 0.21, and I agree).
2. **Summarising parses only when it discards the evidence**, and then it
   is withholding.
3. **The third option — raise the cap — is the one left**, and it has a
   consequence I have not tested: whether a JSON payload can be extracted
   from a response that narrates. I have deliberately not loosened
   `extract_fenced_json`, because doing so changes what the study measures.

Jev's 0.83 stands: the remaining choice is about **what this study should
claim to measure**, not about what the code can do. Three options, all
measured, and the decision is the researcher's.

Evidence: `jev.json`, and the sweeps in
`../inv_r1_m4_baseline/RESULT.md`.
